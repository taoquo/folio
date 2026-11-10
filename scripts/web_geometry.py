#!/usr/bin/env python3
"""Host-level checks for Web figures.

Scene geometry is the Drawing DSL's job: `drawing.validation.geometry` already
validates anchors, orthogonality, crossings, labels, legends and budgets, and the
build fails on an ERROR. What remains here is the host: is the figure inline,
does it sit on the 960 stage and inside the page's height band, does it carry
its provenance, and is the slot height sane.

    python3 scripts/web_geometry.py dist/web/x/module/index.html
    python3 scripts/web_geometry.py dist/web/x/module/index.html --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402

from drawing.stage import MIN_STAGE_WIDTH  # noqa: E402

DEFAULT_SLOT_WIDTH = float(C.FIGURE["slot"])
FIGURE = re.compile(r"<figure\b([^>]*)>([\s\S]*?)</figure>")
SVG = re.compile(r"<svg\b[\s\S]*?</svg>")


@dataclass(frozen=True)
class Finding:
    code: str
    figure: str
    detail: str
    # An ERROR stops the check. A REVIEW states a fact the page cannot fix
    # without the drawing changing family -- it is reported, not gated.
    level: str = "ERROR"


def figures_in(text: str) -> list[tuple[str, dict[str, str], list[tuple[str, str]]]]:
    """(figure id, attributes, [(variant, svg), ...]) for every figure on the page.

    A figure carries one plate per class, so the host audit sees them all and
    holds each to the same plate contract.
    """
    out = []
    for index, match in enumerate(FIGURE.finditer(text), start=1):
        attrs_text, body = match.groups()
        attrs = dict(re.findall(r'([a-z-]+)="([^"]*)"', attrs_text))
        figure_id = attrs.get("data-folio-drawing", f"figure-{index}")
        plates = []
        for svg in SVG.finditer(body):
            markup = svg.group(0)
            variant = re.search(r'data-folio-plate="([^"]*)"', markup)
            vattrs = re.search(r"<svg\b([^>]*)>", markup)
            stage = re.search(r'data-folio-stage="([^"]*)"', vattrs.group(1)) if vattrs else None
            plates.append((variant.group(1) if variant else "", markup,
                           stage.group(1) if stage else ""))
        out.append((figure_id, attrs, plates))
    return out


def _stage(raw: str, width: float) -> tuple[float, float]:
    """The authored canvas, from the plate's `data-folio-stage` or its viewBox."""
    if "x" in raw:
        w, _, h = raw.partition("x")
        try:
            return float(w), float(h)
        except ValueError:
            pass
    return width, 0.0


def _view_box(svg: str) -> tuple[float, float] | None:
    match = re.search(r'viewBox="([^"]+)"', svg)
    if not match:
        return None
    parts = match.group(1).split()
    if len(parts) != 4:
        return None
    return float(parts[2]), float(parts[3])


def audit_host(text: str, *, slot_width: float = DEFAULT_SLOT_WIDTH) -> list[Finding]:
    findings: list[Finding] = []
    figures = figures_in(text)
    if not figures:
        return [Finding("GEOH000", "-", "page has no figure")]

    for figure_id, attrs, plates in figures:
        if not plates:
            findings.append(Finding("GEOH001", figure_id, "figure has no inline <svg>"))
            continue
        seen = [variant for variant, _svg, _stage in plates]
        single = attrs.get("data-folio-single") == "true"
        # Either one plate per class, or -- for a family that composes on one
        # stage only -- a single plate every class shows.
        if single:
            if seen != ["all"]:
                findings.append(Finding("GEOH009", figure_id,
                                        f"single-plate figure declares plates {seen}"))
        elif sorted(seen) != sorted(C.FIGURE_VARIANT_KEYS):
            findings.append(Finding("GEOH009", figure_id,
                                    f"plates {seen} are not one per class"))
        for variant, svg, stage_raw in plates:
            where = f"{figure_id}[{variant or '?'}]"
            box = _view_box(svg)
            if box is None:
                findings.append(Finding("GEOH002", where, "svg has no usable viewBox"))
                continue
            width, height = box
            # The viewBox is the framed (ink-cropped) plate; the stage is the
            # canvas it was composed on. They differ because the plate is
            # cropped, and the stage is a host input now rather than 960.
            stage_width, stage_height = _stage(stage_raw, width)
            if (not MIN_STAGE_WIDTH <= stage_width <= C.FIGURE["width"]
                    or stage_width % 4):
                findings.append(Finding(
                    "GEOH003", where,
                    f"stage width {stage_width:.0f} is not a composed stage "
                    f"({MIN_STAGE_WIDTH}-{C.FIGURE['width']}, multiple of 4)"))
            # The height band is a 960-unit measurement like the rest of the
            # geometry, so on a composed stage its floor travels with the stage:
            # a canvas narrowed for a band no longer fills the authored height,
            # and holding the 960 floor here would fail a plate for being
            # correctly shaped. What refuses a canvas too short for its content
            # is the layout, which reports nodes and regions outside it.
            low, high = C.FIGURE["view_box_height"]
            floor = low * stage_width / C.FIGURE["width"]
            canvas_height = stage_height or height
            if not floor - 1 <= canvas_height <= high:
                findings.append(Finding("GEOH004", where,
                                        f"canvas height {canvas_height:.0f} outside "
                                        f"{floor:.0f}-{high} for a {stage_width:.0f}-unit stage"))
            # Shape, not pixels: the plate is delivered at the band it was
            # composed for, so its proportions are what travels across widths.
            aspect = height / width if width else 0.0
            low, high = C.FIGURE["rendered_aspect"]
            if not low <= aspect <= high:
                findings.append(Finding(
                    "GEOH005", where,
                    f"plate aspect {aspect:.2f} outside {low:g}-{high:g}"
                    + ("; this family composes on one stage" if single else ""),
                    "REVIEW" if single else "ERROR"))
            if "<title" not in svg or "<desc" not in svg:
                findings.append(Finding("GEOH006", where, "svg is missing title or description"))
            if not re.search(r'data-folio-sha="', svg):
                findings.append(Finding("GEOH007", where, "plate has no data-folio-sha"))
        if not attrs.get("data-kind"):
            findings.append(Finding("GEOH008", figure_id, "figure has no data-kind"))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--slot-width", type=float, default=DEFAULT_SLOT_WIDTH)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    findings = audit_host(args.path.read_text(encoding="utf-8"), slot_width=args.slot_width)
    if args.format == "json":
        print(json.dumps([item.__dict__ for item in findings], ensure_ascii=False, indent=2))
    else:
        if not findings:
            print(f"OK: host checks clean in {args.path}")
        for item in findings:
            print(f"{item.level} {item.code} {item.figure}: {item.detail}")
    return 0 if not [item for item in findings if item.level == "ERROR"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
