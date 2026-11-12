from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .bounds import text_box
from .connectors.contract import assign_bridges
from .connectors.grammar import resolve_connector_style
from .connectors.postprocess import clean_polyline
from .grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR, ArchitectureGrammar
from .layout.models import LayoutResult
from .layout.regions import region_frames
from .legend import LEGEND_ITEM_GAP, LEGEND_ROW_PITCH, legend_band
from .models import DrawingPlan
from .scene import (
    ArrowGeometry,
    ResolvedScene,
    SceneAnnotation,
    SceneBox,
    SceneEdge,
    SceneLegend,
    SceneLegendItem,
    SceneNode,
    ScenePictogram,
    SceneRegion,
    SceneStyle,
    SceneText,
)
from .stage import current as current_stage
from .theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from .typography.fit import fit_node_content
from .typography.measure import measure_text
from .typography.roles import TextRole, resolve_text_style


def _text(text: str, x: int, y: int, role: TextRole, theme: FolioTheme, **overrides: object) -> SceneText:
    style = resolve_text_style(role, theme)
    # Every anchor sits on the 4-unit grid. At the default stage the call sites
    # already land there; on a scaled stage the offsets move with the boxes, and
    # snapping here is what keeps the geometry contract true without teaching
    # every call site about the stage.
    return SceneText(
        text=text,
        x=_snap(x),
        y=_snap(y),
        fill=str(overrides.get("fill", style.color)),
        size=float(overrides.get("size", style.size)),
        family=str(overrides.get("family", style.family)),
        anchor=str(overrides.get("anchor", style.anchor)),
        tracking=float(overrides.get("tracking", style.tracking)),
        weight=str(overrides.get("weight", style.weight)) if overrides.get("weight", style.weight) is not None else None,
        klass=str(overrides["klass"]) if "klass" in overrides else None,
    )


def _snap(value: float | int, grid: int = 4) -> int:
    return int(round(float(value) / grid) * grid)


def _arrow(points: tuple[tuple[int, int], ...], size: int) -> ArrowGeometry:
    (x1, y1), (x2, y2) = points[-2], points[-1]
    half = size // 2
    if x2 > x1:
        arrow = ((x2 - size, y2 - half), (x2, y2), (x2 - size, y2 + half))
    elif x2 < x1:
        arrow = ((x2 + size, y2 - half), (x2, y2), (x2 + size, y2 + half))
    elif y2 > y1:
        arrow = ((x2 - half, y2 - size), (x2, y2), (x2 + half, y2 - size))
    else:
        arrow = ((x2 - half, y2 + size), (x2, y2), (x2 + half, y2 + size))
    return ArrowGeometry(arrow)


def _pictogram(node_id: str, pictogram: str | None, x: int, y: int, stroke: str) -> ScenePictogram | None:
    if not pictogram:
        return None
    paths = {
        "client": (f"M {x} {y} h 12 v 8 h -12 z", f"M {x + 3} {y + 11} h 6"),
        "gateway": (f"M {x} {y + 4} h 12", f"M {x + 8} {y} l 4 4 l -4 4"),
        "compute": (f"M {x + 1} {y + 1} h 10 v 10 h -10 z",),
        "queue": (f"M {x} {y + 2} h 12", f"M {x} {y + 6} h 12", f"M {x} {y + 10} h 12"),
        "database": (f"M {x} {y + 2} c 0 -3 12 -3 12 0 v 8 c 0 3 -12 3 -12 0 z",),
        "cache": (f"M {x} {y + 2} c 0 -3 12 -3 12 0 v 8 c 0 3 -12 3 -12 0 z", f"M {x + 3} {y + 6} h 6"),
        "storage": (f"M {x} {y} h 12 v 12 h -12 z", f"M {x + 2} {y + 4} h 8"),
        "cloud": (f"M {x} {y + 9} c -3 -1 -2 -6 2 -6 c 2 -4 7 -2 7 1 c 5 -1 5 6 1 6 h -10",),
        "security": (f"M {x + 6} {y} l 5 2 v 4 c 0 4 -3 6 -5 7 c -2 -1 -5 -3 -5 -7 v -4 z",),
        "observability": (f"M {x} {y + 6} c 3 -5 9 -5 12 0 c -3 5 -9 5 -12 0", f"M {x + 6} {y + 4} v 4"),
        "network": (f"M {x + 6} {y} v 5 M {x} {y + 12} l 6 -7 l 6 7",),
        "external-system": (f"M {x} {y} h 9 v 9 h -9 z", f"M {x + 5} {y + 5} l 7 -5 M {x + 8} {y} h 4 v 4"),
    }[pictogram]
    return ScenePictogram(f"pictogram:{node_id}", paths, stroke)


def _annotation_scenes(drawing: DrawingPlan, layout: LayoutResult, theme: FolioTheme) -> tuple[SceneAnnotation, ...]:
    resolved = []
    occupied = [SceneBox(box.x, box.y, box.w, box.h) for box in layout.boxes.values()]

    def free(candidate: SceneBox) -> bool:
        inside = 16 <= candidate.x and 64 <= candidate.y and candidate.x + candidate.w <= drawing.width - 16 and candidate.y + candidate.h <= drawing.height - 16
        clear = all(candidate.x + candidate.w <= old.x or old.x + old.w <= candidate.x or candidate.y + candidate.h <= old.y or old.y + old.h <= candidate.y for old in occupied)
        return inside and clear

    for index, item in enumerate(drawing.annotations):
        target = layout.boxes.get(item.target)
        if target:
            width = _snap(min(200, max(96, len(item.text) * 7 + 24)))
            candidates = (
                SceneBox(_snap(target.x + target.w + 24), _snap(target.y), width, 40),
                SceneBox(_snap(target.x - width - 24), _snap(target.y), width, 40),
                SceneBox(_snap(target.x + (target.w - width) / 2), _snap(target.y + target.h + 24), width, 40),
                SceneBox(_snap(target.x + (target.w - width) / 2), _snap(target.y - 64), width, 40),
            )
            box = next((candidate for candidate in candidates if free(candidate)), candidates[-1])
            target_center = (_snap(target.x + target.w / 2), _snap(target.y + target.h / 2))
            box_center = (_snap(box.x + box.w / 2), _snap(box.y + box.h / 2))
            leader = (target_center, box_center)
        else:
            width = _snap(min(240, max(120, len(item.text) * 7 + 24)))
            box = SceneBox(drawing.width - width - 24, 68 + index * 48, width, 40)
            leader = ()
        while not free(box) and box.y + box.h + 48 <= drawing.height - 16:
            box = SceneBox(box.x, box.y + 48, box.w, box.h)
        if not free(box):
            raise ValueError(f"annotation cannot be placed without overlap: {item.id}")
        occupied.append(box)
        resolved.append(
            SceneAnnotation(
                item.id,
                box,
                SceneStyle(theme.parchment, theme.border, 1, radius=4),
                _text(item.text, box.x + 12, box.y + 24, TextRole.ANNOTATION, theme),
                leader,
            )
        )
    return tuple(resolved)


def _segment_hits_box(
    start: tuple[int, int], end: tuple[int, int], box: SceneBox
) -> bool:
    """Whether an axis-aligned connector segment passes through ``box``."""
    left, right = min(start[0], end[0]), max(start[0], end[0])
    top, bottom = min(start[1], end[1]), max(start[1], end[1])
    return not (right < box.x or box.x + box.w < left or bottom < box.y or box.y + box.h < top)


def _label_clear(box: SceneBox, other: SceneBox, gap: int = 8) -> bool:
    """Whether two pieces of type can sit on the same line without reading as one."""
    return (
        box.x + box.w + gap <= other.x
        or other.x + other.w + gap <= box.x
        or box.y + box.h <= other.y
        or other.y + other.h <= box.y
    )


def _free_label_x(
    text: str,
    baseline: int,
    left: int,
    right: int,
    edges: tuple[SceneEdge, ...],
    theme: FolioTheme,
    *,
    size: float | None = None,
    tracking: float | None = None,
    occupied: tuple[SceneBox, ...] = (),
) -> int | None:
    """The first x at which a region label clears everything else near its row.

    A composed stage has no gutter, so a band header sits above its row and a
    group label sits inside its boundary -- exactly where connectors enter, and
    where a connector's own label may already sit. Both read as defects: a rule
    through the middle of a word is a strikethrough, and two labels a few units
    apart read as one phrase. The label therefore takes the first position
    (reading left to right) that no segment crosses and no placed type crowds.
    """
    overrides: dict[str, object] = {}
    if size is not None:
        overrides["size"] = size
    if tracking is not None:
        overrides["tracking"] = tracking
    sample = _text(text, 0, baseline, TextRole.REGION_LABEL, theme, **overrides)
    width = text_box(sample).w
    if width >= right - left:
        return None
    for x in range(left, right - width + 1, 4):
        box = text_box(_text(text, x, baseline, TextRole.REGION_LABEL, theme, **overrides))
        # A word set flush against a rule reads as touching it; the scan keeps a
        # few units of air on every side, not merely a non-intersection.
        probe = SceneBox(box.x - 4, box.y, box.w + 8, box.h)
        if any(
            _segment_hits_box(a, b, probe)
            for edge in edges
            for a, b in zip(edge.points, edge.points[1:])
        ):
            continue
        if any(not _label_clear(box, other) for other in occupied):
            continue
        return x
    return None


def _band_header_x(
    text: str,
    top: int,
    left: int,
    right: int,
    edges: tuple[SceneEdge, ...],
    theme: FolioTheme,
    occupied: tuple[SceneBox, ...] = (),
) -> int | None:
    """A band header's place above its row, or None when the row is too busy."""
    return _free_label_x(text, top - 6, left, right, edges, theme, occupied=occupied)


def _region_scenes(
    drawing: DrawingPlan,
    layout: LayoutResult,
    grammar: ArchitectureGrammar,
    theme: FolioTheme,
    edges: tuple[SceneEdge, ...] = (),
) -> tuple[SceneRegion, ...]:
    regions: list[SceneRegion] = []
    layers = [region for region in drawing.regions if region.treatment == "layer-band"]
    layer_bounds: list[tuple[object, int, int]] = []
    for region in layers:
        boxes = [layout.boxes[item] for item in region.members if item in layout.boxes]
        if boxes:
            layer_bounds.append((region, min(box.y for box in boxes), max(box.y + box.h for box in boxes)))
    # On the default stage a layer's name sits in the left gutter, beside its
    # row. A composed stage has no gutter to spare -- the row is as wide as the
    # canvas -- so the name moves above its row and becomes a band header. The
    # type size does not change; only where it is allowed to sit.
    stage = current_stage()
    gutter = stage.is_default
    left = grammar.geometry.frame_left
    right = drawing.width - grammar.geometry.frame_right
    # A plate shows its band names or it does not. One header that cannot clear
    # the connectors means every header goes -- the same rule the descriptors
    # follow, and for the same reason: a figure with one labelled band and one
    # unlabelled band reads as a mistake, not as a reduction.
    header_xs: list[int | None] = []
    # Connector labels are placed by the layout, before the bands are known, so
    # a header has to steer around them here rather than the other way round.
    placed_labels = tuple(edge.label_box for edge in edges if edge.label_box)
    if not gutter:
        header_xs = [
            _band_header_x(region.label.upper(), top, left, right, edges, theme, placed_labels)
            for region, top, _bottom in layer_bounds
        ]
        # A header nudged a few units to clear a connector still reads as the
        # band's own label; one pushed to the middle of the row does not.
        if any(x is None or x - left > 8 for x in header_xs):
            header_xs = [None] * len(header_xs)
    for index, (region, top, bottom) in enumerate(layer_bounds):
        separator = None
        if index < len(layer_bounds) - 1:
            line_y = (bottom + layer_bounds[index + 1][1]) // 2
            # The rule stops short of the right edge by a right-margin's worth;
            # that margin is chrome, so it scales like the frame does.
            inset = 56 if gutter else _snap(56 * stage.scale)
            separator = ((120 if gutter else 0, line_y), (drawing.width - inset, line_y))
        if gutter:
            label = _text(region.label.upper(), 32, _snap((top + bottom) / 2),
                          TextRole.REGION_LABEL, theme)
        else:
            x = header_xs[index]
            # An empty label keeps the band in the model while the plate shows
            # the separator rule alone.
            label = _text(region.label.upper() if x is not None else "",
                          left if x is None else x, top - 6,
                          TextRole.REGION_LABEL, theme)
        regions.append(
            SceneRegion(
                id=region.id,
                treatment="layer-band",
                label=label,
                separator=separator,
                style=SceneStyle(stroke=theme.border, stroke_width=1),
            )
        )
    geometry = grammar.geometry
    for region, frame in region_frames(drawing, layout.boxes, grammar):
        left, top = frame.x, frame.y
        right, bottom = frame.x + frame.w, frame.y + frame.h
        # A group label sits inside the boundary's top padding, which is where
        # the connectors entering the group come down. On a composed stage it
        # takes the first position along that line that no segment crosses; the
        # authored stage keeps the position its artifacts were drawn with. When
        # no position is free the boundary keeps its shape and loses its name,
        # rather than setting two labels on top of each other.
        x: int | None = left + 16
        if not current_stage().is_default:
            x = _free_label_x(region.label.upper(), top + 16, left + 16,
                              right - 16, edges, theme, size=8, tracking=0.12,
                              occupied=placed_labels)
        regions.append(
            SceneRegion(
                id=region.id,
                treatment=region.treatment,
                label=_text(region.label.upper() if x is not None else "",
                            left + 16 if x is None else x, top + 16,
                            TextRole.REGION_LABEL, theme, size=8, tracking=0.12),
                box=SceneBox(left, top, right - left, bottom - top),
                style=SceneStyle(
                    theme.ivory,
                    theme.brand if region.treatment == "trust-boundary" else theme.border,
                    1,
                    (8, 4) if region.treatment == "trust-boundary" else (5, 4),
                    geometry.group_radius,
                    0.28 if region.treatment != "phase-band" else 0.16,
                ),
            )
        )
    return tuple(regions)


def _legend_scene(drawing: DrawingPlan, grammar: ArchitectureGrammar, theme: FolioTheme) -> SceneLegend | None:
    band = legend_band(drawing, theme)
    if band is None:
        return None
    comp = not current_stage().is_default
    style = resolve_text_style(TextRole.LEGEND, theme)
    widths = [20 + 8 + int(round(measure_text(item.label, style.size, style.family)))
              for item in drawing.legend.items] if comp else [
        20 + 8 + len(item.label) * 7 for item in drawing.legend.items]
    x, y = _snap((drawing.width - band.width) / 2), band.top(drawing.height)
    items = []
    for row_index, row in enumerate(band.rows):
        baseline_y = y + (40 if not band.inline else 24) + row_index * LEGEND_ROW_PITCH
        cursor_x = x + (88 if band.inline else 16)
        for position, index in enumerate(row):
            item = drawing.legend.items[index]
            if position:
                cursor_x += LEGEND_ITEM_GAP
            stroke = theme.brand if item.channel == "primary-flow" else theme.label if item.channel == "async-flow" else theme.olive
            line = ((cursor_x, baseline_y), (cursor_x + 20, baseline_y))
            items.append(SceneLegendItem(_text(item.label, cursor_x + 28, baseline_y + 4, TextRole.LEGEND, theme), line, _arrow(line, grammar.geometry.arrow_size), stroke))
            cursor_x = _snap(cursor_x + widths[index])
    return SceneLegend(
        SceneBox(x, y, band.width, band.height),
        SceneStyle(theme.parchment, theme.border, 1, radius=4),
        _text(drawing.legend.title.upper(), x + 16, y + 16, TextRole.REGION_LABEL, theme, size=8, tracking=0.12),
        tuple(items),
    )


def resolve_scene(
    drawing: DrawingPlan,
    layout: LayoutResult,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
) -> ResolvedScene:
    edge_by_pair: dict[tuple[str, str], list[object]] = defaultdict(list)
    for item in layout.edges:
        edge_by_pair[(item.source, item.target)].append(item)
    scene_edges = []
    for edge in drawing.edges:
        matches = edge_by_pair.get((edge.source, edge.target), [])
        if not matches:
            raise ValueError(f"edge has no matching layout route: {edge.id}")
        resolved = matches.pop(0)
        points = clean_polyline(resolved.points, grammar.geometry.grid)
        style = resolve_connector_style(edge.channel, edge.emphasis, theme)
        klass = f"arch-edge arch-edge--{edge.channel.replace('-flow', '').replace('secondary', 'secondary').replace('primary', 'primary').replace('async', 'async')}"
        if edge.emphasis == "focal":
            klass += " arch-edge--focus"
        label = None
        label_box = None
        if resolved.label and resolved.label_box:
            box = resolved.label_box
            label_box = SceneBox(box.x, box.y, box.w, box.h)
            label = _text(
                resolved.label,
                box.x + box.w // 2,
                box.y + 12,
                TextRole.EDGE_LABEL,
                theme,
                anchor="middle",
                klass="arch-edge-label",
            )
        scene_edges.append(
            SceneEdge(
                edge.id,
                edge.source,
                edge.target,
                points,
                SceneStyle(stroke=style.stroke, stroke_width=style.width, dash=style.dash),
                _arrow(points, grammar.geometry.arrow_size),
                klass,
                label,
                label_box,
                8,
            )
        )

    scene_edges = assign_bridges(scene_edges)
    scene_nodes = []
    warnings = list(layout.warnings)

    # A composed plate either carries the descriptors or it does not. On a
    # narrow stage a node box can hold the title but not the line under it, and
    # dropping it for that node alone leaves a figure where two boxes have a
    # second line and two do not -- which reads as a rendering fault, not as a
    # deliberate reduction. A plate therefore decides once: if any node loses
    # its descriptor, the plate shows titles only. The authored stage keeps the
    # per-node answer, because that rendering is what the artifact and the
    # catalog publish and it must stay byte-identical.
    fitted_by_id = {}
    for node in drawing.nodes:
        box = layout.boxes[node.id]
        fitted_by_id[node.id] = fit_node_content(
            node.content, box.w, box.h, reserve_right=24 if node.pictogram else 0)
    if not current_stage().is_default and any(
            node.content.metadata and not fitted_by_id[node.id].metadata
            for node in drawing.nodes):
        required = {node.id for node in drawing.nodes if node.content.metadata_required}
        fitted_by_id = {
            node_id: fitted if node_id in required else replace(fitted, metadata=())
            for node_id, fitted in fitted_by_id.items()
        }

    for node in drawing.nodes:
        box = layout.boxes[node.id]
        fitted = fitted_by_id[node.id]
        warnings.extend(f"{node.id}: {warning}" for warning in fitted.warnings)
        fill = theme.brand_tint if node.emphasis == "focal" else theme.ivory
        strokes = {"external": theme.label, "component": theme.near_black, "datastore": theme.olive, "cloud": theme.border}
        stroke = theme.brand if node.emphasis == "focal" else strokes[node.archetype]
        eyebrow_fill = theme.brand if node.emphasis == "focal" else theme.label
        runs = [_text((node.content.eyebrow or node.archetype).upper(), box.x + 20, box.y + 20, TextRole.NODE_EYEBROW, theme, fill=eyebrow_fill)]
        if len(fitted.title) == 1:
            runs.append(_text(fitted.title[0], box.x + box.w // 2, box.y + 40, TextRole.NODE_TITLE, theme))
        else:
            first_baseline = box.y + min(36, box.h - 16)
            runs.extend(_text(line, box.x + box.w // 2, first_baseline + index * 12, TextRole.NODE_TITLE, theme) for index, line in enumerate(fitted.title))
        for index, line in enumerate(fitted.metadata):
            runs.append(_text(line, box.x + box.w // 2, box.y + 56 + index * 12,
                              TextRole.NODE_META, theme))
        scene_nodes.append(
            SceneNode(
                node.id,
                SceneBox(box.x, box.y, box.w, box.h),
                SceneStyle(fill, stroke, 1, radius=grammar.geometry.node_radius),
                tuple(runs),
                _pictogram(node.id, node.pictogram, box.x + box.w - 30, box.y + 14, stroke),
            )
        )

    return ResolvedScene(
        width=drawing.width,
        height=drawing.height,
        background=theme.parchment,
        title=_text(drawing.title, drawing.width // 2, 40, TextRole.DIAGRAM_TITLE, theme),
        regions=_region_scenes(drawing, layout, grammar, theme, tuple(scene_edges)),
        edges=tuple(scene_edges),
        nodes=tuple(scene_nodes),
        annotations=_annotation_scenes(drawing, layout, theme),
        legend=_legend_scene(drawing, grammar, theme),
        warnings=tuple(warnings),
        description=drawing.caption or drawing.subtitle or drawing.title,
        language=drawing.language,
        reading_order=tuple(node.id for node in drawing.nodes),
    )
