from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .connectors.grammar import resolve_connector_style
from .connectors.postprocess import clean_polyline
from .grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from .layout.models import LayoutResult
from .models import DrawingPlan
from .scene import (
    ArrowGeometry,
    ResolvedScene,
    SceneBox,
    SceneEdge,
    SceneLegend,
    SceneLegendItem,
    SceneNode,
    ScenePictogram,
    SceneAnnotation,
    SceneRegion,
    SceneStyle,
    SceneText,
)
from .theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from .typography.fit import fit_node_content
from .typography.roles import TextRole, resolve_text_style


def _text(text: str, x: int, y: int, role: TextRole, theme: FolioTheme, **overrides: object) -> SceneText:
    style = resolve_text_style(role, theme)
    return SceneText(
        text=text,
        x=x,
        y=y,
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


def _region_scenes(
    drawing: DrawingPlan,
    layout: LayoutResult,
    grammar: ArchitectureGrammar,
    theme: FolioTheme,
) -> tuple[SceneRegion, ...]:
    regions: list[SceneRegion] = []
    layers = [region for region in drawing.regions if region.treatment == "layer-band"]
    layer_bounds: list[tuple[object, int, int]] = []
    for region in layers:
        boxes = [layout.boxes[item] for item in region.members if item in layout.boxes]
        if boxes:
            layer_bounds.append((region, min(box.y for box in boxes), max(box.y + box.h for box in boxes)))
    for index, (region, top, bottom) in enumerate(layer_bounds):
        separator = None
        if index < len(layer_bounds) - 1:
            line_y = (bottom + layer_bounds[index + 1][1]) // 2
            separator = ((120, line_y), (drawing.width - 56, line_y))
        regions.append(
            SceneRegion(
                id=region.id,
                treatment="layer-band",
                label=_text(region.label.upper(), 32, _snap((top + bottom) / 2), TextRole.REGION_LABEL, theme),
                separator=separator,
                style=SceneStyle(stroke=theme.border, stroke_width=1),
            )
        )
    for region in drawing.regions:
        if region.treatment not in {"soft-boundary", "trust-boundary", "phase-band"}:
            continue
        boxes = [layout.boxes[item] for item in region.members if item in layout.boxes]
        if len(boxes) < 2:
            continue
        geometry = grammar.geometry
        left = min(box.x for box in boxes) - geometry.group_pad_x
        top = min(box.y for box in boxes) - geometry.group_pad_top
        right = max(box.x + box.w for box in boxes) + geometry.group_pad_x
        bottom = max(box.y + box.h for box in boxes) + geometry.group_pad_bottom
        regions.append(
            SceneRegion(
                id=region.id,
                treatment=region.treatment,
                label=_text(region.label.upper(), left + 16, top + 16, TextRole.REGION_LABEL, theme, size=8, tracking=0.12),
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
    if not drawing.legend:
        return None
    title_width, item_gap = 64, 28
    widths = [20 + 8 + len(item.label) * 7 for item in drawing.legend.items]
    width = int(round(max(264, 16 + title_width + 16 + sum(widths) + item_gap * max(0, len(widths) - 1) + 16) / 8) * 8)
    if width > drawing.width - 32:
        raise ValueError(f"legend exceeds canvas width: required {width}, available {drawing.width - 32}")
    x, y = _snap((drawing.width - width) / 2), drawing.height - 60
    cursor_x, baseline_y = x + 88, y + 24
    items = []
    for index, item in enumerate(drawing.legend.items):
        if index:
            cursor_x += item_gap
        stroke = theme.brand if item.channel == "primary-flow" else theme.stone if item.channel == "async-flow" else theme.olive
        line = ((cursor_x, baseline_y), (cursor_x + 20, baseline_y))
        items.append(SceneLegendItem(_text(item.label, cursor_x + 28, baseline_y + 4, TextRole.LEGEND, theme), line, _arrow(line, grammar.geometry.arrow_size), stroke))
        cursor_x = _snap(cursor_x + widths[index])
    return SceneLegend(
        SceneBox(x, y, width, 44),
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

    bridge_map: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for index, upper in enumerate(scene_edges):
        for lower in scene_edges[index + 1:]:
            if {upper.source, upper.target} & {lower.source, lower.target}:
                continue
            crossing = _first_crossing(upper.points, lower.points)
            if crossing:
                bridge_map[lower.id].append(crossing)
    scene_edges = [replace(edge, bridges=tuple(sorted(set(bridge_map[edge.id])))) for edge in scene_edges]

    scene_nodes = []
    warnings = list(layout.warnings)
    for node in drawing.nodes:
        box = layout.boxes[node.id]
        fitted = fit_node_content(node.content, box.w, box.h, reserve_right=24 if node.pictogram else 0)
        warnings.extend(f"{node.id}: {warning}" for warning in fitted.warnings)
        fill = theme.brand_tint if node.emphasis == "focal" else theme.ivory
        strokes = {"external": theme.stone, "component": theme.near_black, "datastore": theme.olive, "cloud": theme.border}
        stroke = theme.brand if node.emphasis == "focal" else strokes[node.archetype]
        eyebrow_fill = theme.brand if node.emphasis == "focal" else theme.stone
        runs = [_text((node.content.eyebrow or node.archetype).upper(), box.x + 20, box.y + 20, TextRole.NODE_EYEBROW, theme, fill=eyebrow_fill)]
        if len(fitted.title) == 1:
            runs.append(_text(fitted.title[0], box.x + box.w // 2, box.y + 40, TextRole.NODE_TITLE, theme))
        else:
            first_baseline = box.y + min(36, box.h - 16)
            runs.extend(_text(line, box.x + box.w // 2, first_baseline + index * 12, TextRole.NODE_TITLE, theme) for index, line in enumerate(fitted.title))
        if fitted.metadata:
            runs.append(_text(fitted.metadata, box.x + box.w // 2, box.y + 56, TextRole.NODE_META, theme))
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
        regions=_region_scenes(drawing, layout, grammar, theme),
        edges=tuple(scene_edges),
        nodes=tuple(scene_nodes),
        annotations=_annotation_scenes(drawing, layout, theme),
        legend=_legend_scene(drawing, grammar, theme),
        warnings=tuple(warnings),
        description=drawing.caption or drawing.subtitle or drawing.title,
        language=drawing.language,
        reading_order=tuple(node.id for node in drawing.nodes),
    )


def _first_crossing(
    left: tuple[tuple[int, int], ...],
    right: tuple[tuple[int, int], ...],
) -> tuple[int, int] | None:
    for a, b in zip(left, left[1:]):
        for c, d in zip(right, right[1:]):
            if a[0] == b[0] and c[1] == d[1]:
                if min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1]):
                    return (a[0], c[1])
            elif a[1] == b[1] and c[0] == d[0]:
                if min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1]):
                    return (c[0], a[1])
    return None
