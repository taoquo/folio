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

DEFAULT_SLOT_WIDTH = float(C.FIGURE["slot"])
FIGURE = re.compile(r"<figure\b([^>]*)>([\s\S]*?)</figure>")
SVG = re.compile(r"<svg\b[\s\S]*?</svg>")


@dataclass(frozen=True)
class Finding:
    code: str
    figure: str
    detail: str


def figures_in(text: str) -> list[tuple[str, dict[str, str], str]]:
    """(figure id, attributes, svg) for every figure on the page."""
    out = []
    for index, match in enumerate(FIGURE.finditer(text), start=1):
        attrs_text, body = match.groups()
        attrs = dict(re.findall(r'([a-z-]+)="([^"]*)"', attrs_text))
        svg = SVG.search(body)
        figure_id = attrs.get("data-folio-drawing", f"figure-{index}")
        out.append((figure_id, attrs, svg.group(0) if svg else ""))
    return out


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

    for figure_id, attrs, svg in figures:
        if not svg:
            findings.append(Finding("GEOH001", figure_id, "figure has no inline <svg>"))
            continue
        box = _view_box(svg)
        if box is None:
            findings.append(Finding("GEOH002", figure_id, "svg has no usable viewBox"))
            continue
        width, height = box
        if width != C.FIGURE["width"]:
            findings.append(Finding("GEOH003", figure_id, f"stage width {width:.0f}, expected {C.FIGURE['width']}"))
        low, high = C.FIGURE["view_box_height"]
        if not low <= height <= high:
            findings.append(Finding("GEOH004", figure_id, f"canvas height {height:.0f} outside {low}-{high}"))
        rendered = height * slot_width / width if width else height
        low, high = C.FIGURE["rendered_height"]
        if not low <= rendered <= high:
            findings.append(Finding("GEOH005", figure_id, f"rendered height {rendered:.0f}px outside {low}-{high}"))
        if "<title" not in svg or "<desc" not in svg:
            findings.append(Finding("GEOH006", figure_id, "svg is missing title or description"))
        if not attrs.get("data-folio-sha"):
            findings.append(Finding("GEOH007", figure_id, "figure has no data-folio-sha"))
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
            print(f"ERROR {item.code} {item.figure}: {item.detail}")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
