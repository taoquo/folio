#!/usr/bin/env python3
"""Render a Web reading-page figure through the Drawing DSL.

The page never carries hand-authored SVG: a figure is a fixture, compiled and
validated by the drawing compiler, then serialized with the shared SVG renderer.
The document theme reaches the figure through `folio_theme_for`, registered once
per page theme, so a forest or slate page gets a forest or slate diagram.

    from web_figures import render_figure
    figure = render_figure(path, "transformer", page_theme="folio-classic-v1")
    figure.svg, figure.manifest_entry()

A compilation ERROR raises; WARNING and TASTE diagnostics are recorded in the
manifest for the page checker to report.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402

from drawing.compiler import DEFAULT_COMPILER_REGISTRY  # noqa: E402
from drawing.theme.contrast import contrast_ratio  # noqa: E402
from drawing.theme.folio import folio_theme_for  # noqa: E402
from drawing.theme.profiles import register_theme_profile, resolve_theme  # noqa: E402
from drawing.validation.models import DrawingCompilationError  # noqa: E402
from renderers.svg import render_svg  # noqa: E402

# The page slot is the content width of `.page`; the contract owns the number.
DEFAULT_SLOT_WIDTH = float(C.FIGURE["slot"])

LAYOUT_COMPOSITION = {
    "horizontal-layers": "layered",
    "vertical-stack": "pipeline",
    "hub-and-spoke": "hub",
}

# The layout string names the geometry, so the axis follows the planner's own
# mapping in `drawing/planner.py`: horizontal layers stack top-down, a vertical
# stack of nodes reads left-right along its pipeline.
LAYOUT_AXIS = {
    "horizontal-layers": "top-down",
    "vertical-stack": "left-right",
    "hub-and-spoke": "top-down",
}

KIND_COMPOSITION = {
    "architecture": "layered",
    "flowchart": "pipeline",
    "swimlane": "pipeline",
    "sequence": "pipeline",
    "state-machine": "pipeline",
}


@dataclass(frozen=True)
class RenderedFigure:
    figure_id: str
    fixture: str
    kind: str
    composition: str | None
    axis: str
    svg: str
    diagnostics: tuple[dict[str, str], ...]
    node_sizes: tuple[tuple[int, int], ...]
    colour_count: int
    min_font_px: float
    view_box: tuple[int, int]
    fixture_sha: str
    svg_sha: str

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture,
            "fixture_sha": self.fixture_sha,
            "svg_sha": self.svg_sha,
            "kind": self.kind,
            "composition": self.composition,
            "axis": self.axis,
            "node_sizes": [list(size) for size in self.node_sizes],
            "colour_count": self.colour_count,
            "min_font_px": round(self.min_font_px, 2),
            "view_box": list(self.view_box),
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


def _darken(value: str, backgrounds: tuple[str, ...], minimum: float) -> str:
    """Move a colour toward black until it clears a contrast floor everywhere."""
    red, green, blue = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    for _ in range(240):
        current = f"#{red:02X}{green:02X}{blue:02X}"
        if min(contrast_ratio(current, background) or 0 for background in backgrounds) + 1e-9 >= minimum:
            return current
        red = max(0, round(red * 0.97))
        green = max(0, round(green * 0.97))
        blue = max(0, round(blue * 0.97))
    return current


def drawing_theme_for(page_theme: str | None) -> str:
    """A drawing theme that follows the page's document scheme."""
    if not page_theme:
        return "folio"
    name = f"doc-{page_theme}"
    try:
        resolve_theme(name)
        return name
    except ValueError:
        pass
    theme = folio_theme_for(page_theme)
    # A scheme's second series step is also a text colour (the node eyebrow).
    # Make it clear the normal-text floor on both surfaces before registering.
    theme = replace(
        theme,
        series_2=_darken(theme.series_2, (theme.parchment, theme.ivory), 4.5),
    )
    try:
        register_theme_profile(name, theme)
    except ValueError as exc:  # a scheme that cannot back a readable diagram
        raise RuntimeError(f"page theme {page_theme} cannot back a drawing theme: {exc}") from exc
    return name


def composition_for(payload: dict[str, Any]) -> str | None:
    kind = str(payload.get("kind") or "")
    layout = str(payload.get("layout") or "")
    if layout in LAYOUT_COMPOSITION:
        return LAYOUT_COMPOSITION[layout]
    return KIND_COMPOSITION.get(kind)


def axis_for(payload: dict[str, Any]) -> str:
    layout = str(payload.get("layout") or "")
    if layout in LAYOUT_AXIS:
        return LAYOUT_AXIS[layout]
    axis = str(payload.get("axis") or "")
    return axis if axis in {"top-down", "left-right"} else "top-down"


def _planned_composition(result: Any) -> Any:
    """The composition the compiler actually planned, when it planned one."""
    composition = getattr(getattr(result, "plan", None), "composition", None)
    return composition if getattr(composition, "pattern", None) else None


def render_figure(
    fixture: str | Path,
    figure_id: str,
    *,
    page_theme: str | None = None,
    profile: str = "embed",
    slot_width: float = DEFAULT_SLOT_WIDTH,
    composition: str | None = None,
) -> RenderedFigure:
    fixture = Path(fixture)
    raw = fixture.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    theme = drawing_theme_for(page_theme)

    try:
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(
            payload, profile, theme, "full", "practitioner"
        )
    except DrawingCompilationError as exc:
        raise DrawingCompilationError("web-figure", tuple(exc.diagnostics)) from exc

    errors = tuple(item for item in result.diagnostics if item.level == "ERROR")
    if errors:
        raise DrawingCompilationError("web-figure", errors)

    fixture_sha = hashlib.sha256(raw).hexdigest()[:16]
    svg = render_svg(result.scene, profile, namespace=f"web-{figure_id}-{fixture_sha}")
    svg_sha = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:16]

    scale = slot_width / result.scene.width if result.scene.width else 1.0
    sizes = tuple(sorted({(int(node.box.w), int(node.box.h)) for node in result.scene.nodes}))
    text_sizes = [run.size for node in result.scene.nodes for run in node.text_runs]
    min_font_px = (min(text_sizes) * scale) if text_sizes else 12.0 * scale
    # Count only chromatic marks: neutrals and the canvas are structure, not
    # another colour in the figure's budget.
    theme_tokens = folio_theme_for(page_theme)
    neutral = {
        value.lower()
        for name, value in vars(theme_tokens).items()
        if name not in {"brand", "brand_tint"} and not name.startswith("series_")
    }
    colours = {
        value.lower() for value in re.findall(r"#[0-9A-Fa-f]{6}", svg)
    } - neutral

    # The caption states what the page shows, so the axis comes from the plan
    # that produced the geometry. A series override may still name the pattern
    # (a fan-in drawn on horizontal layers is a hub), but it never moves the
    # reading direction. Only the three page compositions reach the caption;
    # other plan patterns (`cyclic`, `lanes`) are named by their kind instead.
    planned = _planned_composition(result)
    planned_axis = getattr(planned, "axis", None)
    planned_pattern = getattr(planned, "pattern", None)
    if planned_pattern not in C.COMPOSITIONS:
        planned_pattern = None
    return RenderedFigure(
        figure_id=figure_id,
        fixture=str(fixture),
        kind=str(payload.get("kind") or ""),
        composition=composition or planned_pattern or composition_for(payload),
        axis=planned_axis if planned_axis in {"top-down", "left-right"} else axis_for(payload),
        svg=svg,
        diagnostics=tuple(
            {"level": item.level, "code": item.code, "message": item.message}
            for item in result.diagnostics
        ),
        node_sizes=sizes,
        colour_count=len(colours),
        min_font_px=min_font_px,
        view_box=(result.scene.width, result.scene.height),
        fixture_sha=fixture_sha,
        svg_sha=svg_sha,
    )
