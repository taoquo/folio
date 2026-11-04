#!/usr/bin/env python3
"""Render a Web reading-page figure through the Drawing DSL.

The page never carries hand-authored SVG: a figure is a fixture, compiled and
validated by the drawing compiler, then serialized with the shared SVG renderer.
The document theme reaches the figure through `folio_theme_for`, registered once
per page theme, so a forest or slate page gets a forest or slate diagram.

The drawing's type tiers are 7 / 9 / 12 units, then framed to its ink
(`page-preview`) so the page does not carry the canvas's empty margin. A figure
composed on the 960-unit stage and rendered into the 660px column delivers those
tiers at 5.7-6.6px. Passing `band=` searches for a stage that delivers them at
7px or more (`compose_for_band`): chrome shrinks with the stage while the type
scale does not, so the same tiers arrive larger. The stage is never a payload
field -- the host declares where the figure will be shown and the compiler
composes into it.

The manifest records the band, the stage, the ink box, the delivered viewBox,
the ink coverage and every drawn tier, so a checker can judge the figure on both
of its obligations -- legible type *and* a filled plate. Enlarging the plate
alone was tried and rejected: it raised the type and the empty margin by the
same factor.

    from web_figures import render_figure
    figure = render_figure(path, "transformer", page_theme="folio-classic-v1", band=660)

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

from drawing.bounds import (  # noqa: E402
    intersect_box,
    largest_empty_band,
    scene_content_boxes,
    scene_ink_box,
)
from drawing.compiler import DEFAULT_COMPILER_REGISTRY  # noqa: E402
from drawing.output.viewport import scene_viewport as drawing_viewport  # noqa: E402
from drawing.scene import ResolvedScene, SceneGroup, SceneText  # noqa: E402
from drawing.stage import DEFAULT_STAGE, MIN_STAGE_WIDTH, STAGE_AWARE, StageSpec  # noqa: E402
from drawing.stage import use as use_stage  # noqa: E402
from drawing.theme.contrast import contrast_ratio  # noqa: E402
from drawing.theme.folio import folio_theme_for  # noqa: E402
from drawing.theme.profiles import register_theme_profile, resolve_theme  # noqa: E402
from drawing.validation.models import DrawingCompilationError, DrawingDiagnostic  # noqa: E402
from renderers.svg import render_svg  # noqa: E402

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
    # The title's size in stage units and the pixels it is delivered at. The
    # units are recorded so a checker can recompute the delivery at any band,
    # the way `text_sizes` lets it recompute the floor.
    title_units: float
    title_px: float
    text_sizes: tuple[float, ...]
    band: float | None
    stage: tuple[int, int]
    ink_box: tuple[int, int, int, int] | None
    view_box: tuple[int, int, int, int]
    coverage: float
    margin_ratio: float
    # The tallest band inside the drawing that nothing crosses. Coverage reads
    # the ink's bounding box, which cannot see a hole the drawing contains.
    empty_band_units: int
    empty_band_ratio: float
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
            # Delivered in the contract slot (660px), computed on the framed
            # viewBox rather than the 960-unit stage.
            "min_font_px": round(self.min_font_px, 2),
            # The figure title is a page heading in all but name: these two
            # numbers are what `fit_verdict` compares with H2 and H3.
            "title_units": round(self.title_units, 2),
            "title_px": round(self.title_px, 2),
            "text_sizes": [round(size, 2) for size in self.text_sizes],
            # The band the figure was composed for, when the host declared one.
            # `min_font_px` is delivered at this band, not at a nominal slot.
            "band": round(self.band, 1) if self.band is not None else None,
            "stage": list(self.stage),
            "ink_box": list(self.ink_box) if self.ink_box else None,
            "view_box": list(self.view_box),
            "coverage": round(self.coverage, 4),
            "margin_ratio": round(self.margin_ratio, 4),
            # The hole the bounding box cannot show: the tallest horizontal
            # band inside the content with nothing drawn in it.
            "empty_band_units": self.empty_band_units,
            "empty_band_ratio": round(self.empty_band_ratio, 4),
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


# A family that cannot compose on another stage has one composition to offer,
# and the page shows it at every width. The plate is marked `all` so the
# stylesheet has a stable name for "the only plate", and the manifest says
# `single` so a checker knows the missing classes are a property of the family
# rather than a build that forgot to emit them.
SINGLE_PLATE = C.FIGURE_SINGLE_PLATE


def composes_per_band(fixture: str | Path) -> bool:
    """Whether this drawing's family can be recomposed for another stage."""
    payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
    return str(payload.get("kind") or "") in STAGE_AWARE


def figure_manifest_entry(variants: dict[str, RenderedFigure],
                          uncomposed: tuple[str, ...] = ()) -> dict[str, Any]:
    """One figure's manifest entry, with a record per composed band.

    The fixture, kind and composition do not depend on the band, so they are
    stated once at the top; everything that does depend on it -- the stage, the
    plate, the axis, the delivered tiers -- is recorded per variant.

    The axis is usually one fact for the whole figure and stays at the top. A
    composition may flip a narrow band to the other axis while the wide plate
    keeps the authored one, and then the figure has no single reading direction:
    the top-level axis names the wide plate (the one the page carries as its
    fallback), and every plate states its own.
    """
    first = variants[next(iter(variants))]
    wide = variants.get("wide", first)
    axes = {figure.axis for figure in variants.values()}
    shared = ("fixture", "fixture_sha", "kind", "composition", "axis")
    if len(axes) > 1:
        shared = tuple(name for name in shared if name != "axis")
    entry = {
        "fixture": first.fixture,
        "fixture_sha": first.fixture_sha,
        "kind": first.kind,
        "composition": first.composition,
        "axis": wide.axis,
        "variants": {
            key: {name: value for name, value in figure.manifest_entry().items()
                  if name not in shared}
            for key, figure in variants.items()
        },
    }
    if tuple(entry["variants"]) == (SINGLE_PLATE,):
        entry["single"] = True
        entry["uncomposed"] = list(uncomposed)
    return entry


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


def scene_text_sizes(scene: ResolvedScene) -> tuple[float, ...]:
    """Every text size the scene draws, not only the node labels.

    A figure's smallest type is often a region label or an annotation, which
    sits on the scene rather than inside a node. The report has to see those
    too, or it quotes a floor the reader never gets.
    """
    sizes: list[float] = []

    def walk(item: object) -> None:
        if isinstance(item, SceneText):
            sizes.append(float(item.size))
        elif isinstance(item, SceneGroup):
            for child in item.children:
                walk(child)

    def text(item: object) -> None:
        if isinstance(item, SceneText):
            sizes.append(float(item.size))

    text(scene.title)
    for region in scene.regions:
        text(region.label)
    for edge in scene.edges:
        text(edge.label)
    for node in scene.nodes:
        sizes.extend(float(run.size) for run in node.text_runs)
    for primitive in scene.primitives:
        walk(primitive)
    for annotation in scene.annotations:
        walk(annotation.text)
    if scene.legend:
        text(scene.legend.title)
        for item in scene.legend.items:
            text(item.label)
    return tuple(sorted({round(size, 2) for size in sizes}))


def _planned_composition(result: Any) -> Any:
    """The composition the compiler actually planned, when it planned one."""
    composition = getattr(getattr(result, "plan", None), "composition", None)
    return composition if getattr(composition, "pattern", None) else None


def _compile(payload: dict[str, Any], theme: str, profile: str, stage: StageSpec,
             title_units: float | None = None) -> Any:
    """Compile one stage; a non-default stage is refused for a family that cannot scale."""
    try:
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(
            payload, profile, theme, "full", "practitioner",
            stage=stage, title_units=title_units)
    except DrawingCompilationError as exc:
        raise DrawingCompilationError("web-figure", tuple(exc.diagnostics)) from exc
    errors = tuple(item for item in result.diagnostics if item.level == "ERROR")
    if errors:
        raise DrawingCompilationError("web-figure", errors)
    return result


# The band a composed plate leaves between its last row and its legend, in stage
# units. Below this the legend crowds the drawing; above it the canvas is paying
# for air nobody sees, because the legend is pinned to the bottom edge and the
# viewBox cannot crop a hole between the two.
CANVAS_SLACK = 40


def _unused_height(scene: Any) -> int:
    """Stage units of canvas above the legend that no mark occupies."""
    base = scene.legend.box.y if scene.legend else scene.height
    boxes = scene_content_boxes(scene)
    if scene.legend:
        boxes = [box for box in boxes if box != scene.legend.box]
    return max(0, base - max((box.y + box.h for box in boxes), default=base))


def _fit_canvas(
    payload: dict[str, Any],
    theme: str,
    profile: str,
    stage: StageSpec,
    result: Any,
    title_units: float | None = None,
) -> Any:
    """The same composition on the shortest canvas that still holds it.

    A stage narrowed for a band inherits the height the drawing was authored at,
    and a legend pinned to the bottom edge turns that inherited height into a
    hole between the last row and the legend -- invisible to a bounding-box
    coverage number, plainly visible on the page. The width is the host's
    decision, so the height has to follow it: the authored height is the
    ceiling, and the floor is whatever the compiler will still place.

    The authored stage keeps its canvas untouched; this only runs where the
    stage already differs from it.
    """
    if stage.is_default:
        return result
    for _ in range(4):
        scene = result.scene
        unused = _unused_height(scene)
        if unused <= CANVAS_SLACK:
            break
        wanted = scene.height - (unused - CANVAS_SLACK)
        wanted -= wanted % 4
        if wanted >= scene.height:
            break
        # The family's own band bounds how short its canvas may be, and that
        # floor belongs to the family, not to this composer. So ask: the shortest
        # height that still compiles, found by bisection between the wanted
        # height and the one that already did.
        heights = list(range(wanted, scene.height + 4, 4))
        low, high, shorter = 0, len(heights) - 1, None
        while low <= high:
            middle = (low + high) // 2
            try:
                with use_stage(stage):
                    candidate = _compile({**payload, "height": heights[middle]},
                                         theme, profile, stage, title_units)
            except DrawingCompilationError:
                low = middle + 1
                continue
            shorter, high = candidate, middle - 1
        if shorter is None:
            break
        result = shorter
    return result


def _delivered(result: Any, view: tuple[int, int, int, int], band: float) -> tuple[float, float]:
    """(smallest tier in px, rendered height in px) when this drawing fills ``band``."""
    tiers = scene_text_sizes(result.scene)
    if not tiers or not view[2]:
        return 0.0, 0.0
    scale = float(band) / float(view[2])
    return tiers[0] * scale, view[3] * scale


def compose_for_band(
    payload: dict[str, Any],
    theme: str,
    profile: str,
    band: float,
    *,
    target_px: float | None = None,
    aspect_band: tuple[float, float] | None = None,
    tolerance: float | None = None,
    max_steps: int = 16,
    title_units: float | None = None,
    start_stage: StageSpec | None = None,
) -> tuple[Any, tuple[int, int, int, int], StageSpec]:
    """The stage that composes this drawing for a host band of ``band`` CSS pixels.

    The drawing's type stays at 7 / 9 / 12 units while the geometry shrinks, so a
    *smaller* stage delivers *larger* type in a fixed-width band. That makes the
    floor reachable at any band -- but it is not free: a smaller stage wraps
    rows, which makes the plate taller, and takes it further from the
    proportions it was designed at.

    So the rule is the *largest* stage that still clears the floor. At the wide
    band that is the author's own 960 stage, delivered unchanged; at a narrower
    band it is the stage that shrinks the drawing just enough. The point of the
    mechanism is to rescue the narrow bands, not to enlarge the wide ones, and
    this rule changes nothing the floor does not require.

    Both obligations are measured on the framed plate, so the shape check is
    an aspect rather than a pixel height: the plate is later delivered at
    whatever band the host shows it in, and scaling a shape does not change
    the shape.

    The walk starts at the widest stage the band allows and steps down by
    however much the measured overshoot needs, so it settles in two or three
    compiles. ``max_steps`` bounds a pathological case; the verdict is
    deterministic either way.
    """
    target = float(C.FIGURE_FIT["delivered_target_px"] if target_px is None else target_px)
    tolerance = float(
        C.FIGURE_FIT["delivered_tolerance_px"] if tolerance is None else tolerance)
    low_aspect, high_aspect = C.FIGURE["rendered_aspect"] if aspect_band is None else aspect_band
    if band < MIN_STAGE_WIDTH:
        raise DrawingCompilationError("web-figure", (
            DrawingDiagnostic(
                "ERROR", "CP005",
                f"a {band:g}px band is narrower than the {MIN_STAGE_WIDTH}-unit stage floor",
                hint="the host is asking for a figure smaller than any composition can be"),
        ))
    # The widest stage the drawing can be composed on, which is also the one
    # closest to the proportions it was designed at. A caller that already
    # found a stage -- the title recompile -- starts there instead of walking
    # the whole ladder again, so a title change does not double the build.
    stage = start_stage or DEFAULT_STAGE
    attempted: list[str] = []

    for _ in range(max_steps):
        try:
            with use_stage(stage):
                result = _compile(payload, theme, profile, stage, title_units)
                view = drawing_viewport(result.scene, profile)
        except DrawingCompilationError as exc:
            attempted.append(f"{stage.width}: {exc.diagnostics[0].code if exc.diagnostics else 'failed'}")
            # A stage that cannot hold the drawing says nothing about a smaller
            # one: less room means more wrapping, and a composition that does
            # not resolve at 464 can resolve at 352. The feasible stages are
            # therefore not an interval, and ending the search at the first
            # refusal throws away the band's whole purpose. Bisect toward the
            # floor instead.
            below = (MIN_STAGE_WIDTH + stage.width) // 2 // 4 * 4
            if below <= MIN_STAGE_WIDTH or below >= stage.width:
                break
            stage = StageSpec(below)
            continue

        min_px, _height = _delivered(result, view, band)
        if min_px + tolerance < target:
            attempted.append(f"{stage.width}: {min_px:.2f}px type, aspect {float(view[3]) / float(view[2]):.2f}")
            # Scale the stage by the frame width the floor asks for. The frame
            # does not move one-for-one with the stage (node boxes have floors),
            # so this is a step, not a solution; the next pass measures again.
            needed = float(view[2]) * min_px / target
            step = max(4, int((stage.width * (1 - needed / float(view[2]))) // 4) * 4)
            if stage.width - step < MIN_STAGE_WIDTH:
                break
            stage = StageSpec(stage.width - step)
            continue
        # The floor is met, so the canvas is worth fitting: the shape is measured
        # on the plate the host will actually show, and a canvas inherited from
        # the authored height leaves a hole above a bottom-pinned legend. Doing
        # this only on stages that clear the floor keeps the search cheap -- the
        # floor depends on the framed width alone, and the fit cannot move it.
        with use_stage(stage):
            result = _fit_canvas(payload, theme, profile, stage, result, title_units)
            view = drawing_viewport(result.scene, profile)
        aspect = (float(view[3]) / float(view[2])) if view[2] else 0.0
        if low_aspect <= aspect <= high_aspect:
            return result, view, stage
        attempted.append(f"{stage.width}: {min_px:.2f}px type, aspect {aspect:.2f}")
        if aspect > high_aspect:
            # A plate can grow *taller* as the stage grows: the chrome scales
            # with the stage while a composition that hugs its own content keeps
            # its width, so the ratio rises. A too-tall verdict at one stage is
            # therefore not proof the drawing has no stage: step down and let
            # the shorter chrome square it up, bounded by the same step budget.
            smaller = max(MIN_STAGE_WIDTH, stage.width - max(4, stage.width // 4))
            smaller -= smaller % 4
            if smaller >= stage.width:
                break
            stage = StageSpec(smaller)
            continue
        # Too flat: wrapping rows into a smaller stage squares the plate up, and
        # a smaller stage also raises the type, so the floor stays satisfied.
        # Step by the width the band asks for, the same way the floor branch
        # does; creeping four units at a time spends the whole step budget on a
        # deficit of a few percent.
        wanted = float(view[2]) * aspect / low_aspect
        step = max(4, int((stage.width * (1 - wanted / float(view[2]))) // 4) * 4)
        if stage.width - step < MIN_STAGE_WIDTH:
            break
        stage = StageSpec(stage.width - step)

    raise DrawingCompilationError("web-figure", (
        DrawingDiagnostic(
            "ERROR", "CP005",
            f"no stage composes this drawing for a {band:g}px band with its smallest "
            f"tier at {target:g}px and its plate aspect inside "
            f"{low_aspect:g}-{high_aspect:g}",
            hint="the composition needs a different arrangement for this band, "
                 "not a smaller number; tried " + ", ".join(attempted[-6:]),
        ),
    ))


def _title_tier(
    scene: ResolvedScene,
    view_width: float,
    band_range: tuple[float, float],
    px_range: tuple[float, float],
) -> float:
    """The largest title tier whose widest delivery stays under the H2 ceiling.

    ``band_range`` is the class the plate is shown in -- its design band and
    the band at the class's widest viewport. The plate scales with that band,
    so the title's largest delivery is at the upper end, and that is where the
    ceiling binds. Choosing the largest tier that clears it also gives the
    largest delivery at the design band, which is what keeps the title above
    H3; the floor is then a verdict rather than a second search.
    """
    _floor_px, ceiling_px = px_range
    if not view_width:
        return float(scene.title.size)
    step = int(C.FIGURE_FIT["title_tier_step"])
    top = int(C.FIGURE_FIT["title_tier_max"])
    bottom = int(C.FIGURE_FIT["title_tier_floor"])
    widest = max(band_range)
    for units in range(top, bottom - 1, -step):
        if units * widest / view_width <= ceiling_px:
            return float(units)
    return float(bottom)


def render_figure(
    fixture: str | Path,
    figure_id: str,
    *,
    page_theme: str | None = None,
    profile: str = "page-preview",
    composition: str | None = None,
    band: float | None = None,
    stage: StageSpec | None = None,
    band_range: tuple[float, float] | None = None,
    title_px: tuple[float, float] | None = None,
) -> RenderedFigure:
    """Compile and serialize one figure.

    ``band`` is the CSS width the host will deliver the figure in. The drawing
    is then composed on whichever stage satisfies both its type floor and the
    host's rendered-height band (`compose_for_band`). Passing ``stage`` instead
    pins one stage, which the tests use to prove the mechanism. Without either
    the figure keeps the default 960-unit stage, as the artifact and the catalog
    still require.

    ``band_range`` and ``title_px`` are the host's heading hierarchy: the class
    the plate is shown across, and the title's allowed delivered pixels -- H3's
    floor and H2's ceiling. With them the title is set at the largest tier whose
    widest delivery stays under the ceiling; without them it keeps the authored
    24 units, which is what a standalone artifact needs.
    """
    if band is not None and stage is not None:
        raise ValueError("pass a band or a stage, not both")
    if band_range is not None and band is None:
        raise ValueError("a title band range only means something with a band")
    fixture = Path(fixture)
    raw = fixture.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    theme = drawing_theme_for(page_theme)

    if band is not None:
        result, (view_x, view_y, view_width, view_height), stage = compose_for_band(
            payload, theme, profile, band)
        # The title is set after the plate is framed, and recomposing at the
        # chosen tier is not optional: the title's own width is part of the
        # ink the frame is cropped to, so a smaller title can move the frame.
        # Two rounds is the budget the plan allows; a third has never moved the
        # tier in practice, and `fit_verdict` would catch it if it did.
        if band_range is not None and title_px is not None:
            units = _title_tier(result.scene, view_width, band_range, title_px)
            for _ in range(2):
                if units == float(result.scene.title.size):
                    break
                result, (view_x, view_y, view_width, view_height), stage = compose_for_band(
                    payload, theme, profile, band, title_units=units,
                    start_stage=stage)
                follow = _title_tier(result.scene, view_width, band_range, title_px)
                if follow == units:
                    break
                units = follow
    else:
        stage = stage or DEFAULT_STAGE
        with use_stage(stage):
            result = _compile(payload, theme, profile, stage)
            view_x, view_y, view_width, view_height = drawing_viewport(result.scene, profile)

    # The stage stays in scope for the render, not only the compile: the SVG's
    # own viewBox is computed while serializing, and the manifest's is computed
    # here. Both must frame with the same margin for the two to agree.
    with use_stage(stage):
        fixture_sha = hashlib.sha256(raw).hexdigest()[:16]
        # One page carries one plate per class, so the namespace has to differ
        # per stage or three plates share DOM ids inside one document.
        svg = render_svg(
            result.scene, profile,
            namespace=f"web-{figure_id}-{fixture_sha}-{stage.width}")
        svg_sha = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:16]

    sizes = tuple(sorted({(int(node.box.w), int(node.box.h)) for node in result.scene.nodes}))
    text_sizes = scene_text_sizes(result.scene)
    ink = scene_ink_box(result.scene)
    framed = max(1, view_width * view_height)
    # The plate draws inside its canvas and the viewBox is clamped to it, so a
    # text box that reaches past the canvas edge is clipped, not shown. Measure
    # the ink the reader can see: an unclipped estimate makes coverage exceed 1
    # and hides the one thing the number exists to catch.
    visible = (
        intersect_box(ink, (0, 0, result.scene.width, result.scene.height))
        if ink else None
    )
    if visible is not None and (visible.w <= 0 or visible.h <= 0):
        visible = None
    ink_area = (visible.w * visible.h) if visible else 0
    empty_units, content_height = largest_empty_band(result.scene)
    margins = (
        (visible.x - view_x if visible else view_width),
        (visible.y - view_y if visible else view_height),
        (view_x + view_width - (visible.x + visible.w) if visible else view_width),
        (view_y + view_height - (visible.y + visible.h) if visible else view_height),
    )
    # `min_font_px` is the delivered size at the band the host named, or at the
    # contract slot when it named none; the drawing is scaled by the delivered
    # viewBox, so the framed width is the divisor. The drawn tiers travel
    # separately, so a probe can recompute for any width.
    delivered_width = float(band) if band is not None else float(C.FIGURE["slot"])
    min_font_px = (
        (text_sizes[0] * delivered_width / view_width) if text_sizes
        else 12.0 * delivered_width / view_width)
    title_units = float(result.scene.title.size)
    title_delivered = title_units * delivered_width / view_width if view_width else 0.0
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
        title_units=title_units,
        title_px=title_delivered,
        text_sizes=text_sizes,
        band=band,
        stage=(result.scene.width, result.scene.height),
        ink_box=(visible.x, visible.y, visible.w, visible.h) if visible else None,
        view_box=(view_x, view_y, view_width, view_height),
        coverage=(ink_area / framed) if ink_area else 0.0,
        margin_ratio=(max(margins) / max(view_width, view_height)) if ink else 1.0,
        empty_band_units=empty_units,
        empty_band_ratio=(empty_units / content_height) if content_height else 0.0,
        fixture_sha=fixture_sha,
        svg_sha=svg_sha,
    )


def render_plates(
    fixture: str | Path,
    figure_id: str,
    *,
    bands: dict[str, float],
    max_bands: dict[str, float] | None = None,
    title_px: tuple[float, float] | None = None,
    page_theme: str | None = None,
    profile: str = "page-preview",
    composition: str | None = None,
) -> tuple[dict[str, RenderedFigure], tuple[str, ...]]:
    """The plates one figure carries, and the classes it could not compose for.

    A figure carries one plate per class only when every class composes: the
    stylesheet shows one plate at a time, so a class that is missing has no
    plate to show at that width. When any class fails, the figure falls back to
    the authored stage and carries a single plate every class shows, and the
    classes it could not compose for are returned so the manifest can state
    them rather than leave the reader to guess.

    The fallback is not a pass. `web_plan.fit_verdict` reports the delivered
    size at each class, and `STAGE_AWARE` is what a family has to earn for the
    fallback to stop happening.
    """
    options = {"page_theme": page_theme, "profile": profile, "composition": composition}
    plates: dict[str, RenderedFigure] = {}
    uncomposed: list[str] = []
    if composes_per_band(fixture):
        for key, band in bands.items():
            # A class is shown from its design band to the band at its widest
            # viewport; the title's ceiling binds at the upper end.
            widest = (max_bands or {}).get(key, band)
            try:
                plates[key] = render_figure(
                    fixture, figure_id, band=band,
                    band_range=(band, widest), title_px=title_px, **options)
            except DrawingCompilationError:
                uncomposed.append(key)
        if not uncomposed:
            return plates, ()

    floor_band = min(bands.values())
    figure = render_figure(fixture, figure_id, **options)
    framed = float(figure.view_box[2]) or 1.0
    delivered = (figure.text_sizes[0] * floor_band / framed) if figure.text_sizes else 0.0
    missing = tuple(uncomposed) if uncomposed else tuple(bands)
    return ({SINGLE_PLATE: replace(figure, band=floor_band, min_font_px=delivered)},
            missing)
