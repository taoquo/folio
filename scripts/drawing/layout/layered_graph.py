"""Layered graph layout and routing for the structural families.

State machine, swimlane, tree and layer stack all describe the same shape: nodes assigned to
bands, connectors running between them. They share this module rather than each growing a
private copy, and they satisfy the connector contract by calling into
``connectors.contract`` instead of restating its rules.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any

from ..connectors.contract import approach_needs_rerouting, perpendicular_approach
from ..connectors.labels import LABEL_REACH, place_edge_labels
from ..connectors.postprocess import clean_polyline
from ..layout.models import LayoutBox, LayoutEdge, LayoutResult
from ..scene import (
    ArrowGeometry,
    ResolvedScene,
    SceneBox,
    SceneEdge,
    SceneNode,
    SceneRegion,
    SceneStyle,
    SceneText,
)
from ..theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from ..typography.fit import _wrap as _staged_wrap
from ..typography.fit import fit_wrap_width
from ..typography.measure import measure_text
from ..typography.roles import TextRole, resolve_text_style
from ..typography.text import wrap_text
from .graph_geometry import DEFAULT_GRAPH_GEOMETRY, MARK_ARCHETYPES, GraphGeometry
from .grid import grid


@dataclass(frozen=True)
class GraphComposition:
    pattern: str
    axis: str
    spine: tuple[str, ...] = ()




@dataclass(frozen=True)
class GraphNodePlan:
    id: str
    label: str
    archetype: str
    emphasis: str = "normal"
    subtitle: str | None = None
    lane: str | None = None




@dataclass(frozen=True)
class GraphEdgePlan:
    id: str
    source: str
    target: str
    channel: str = "normal"
    label: str | None = None




@dataclass(frozen=True)
class GraphPlan:
    kind: str
    title: str
    composition: GraphComposition
    nodes: tuple[GraphNodePlan, ...]
    edges: tuple[GraphEdgePlan, ...]
    width: int = 960
    height: int = 540
    language: str = "en"
    schema_version: str = "3.0"
    explanation: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def graph_depths(plan: GraphPlan) -> dict[str, int]:
    incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in plan.edges:
        incoming[edge.target] += 1
        outgoing[edge.source].append(edge.target)
    starts = [node.id for node in plan.nodes if incoming[node.id] == 0]
    if not starts and plan.nodes:
        starts = [plan.nodes[0].id]
    depth = {node.id: 0 for node in plan.nodes}
    pending = deque(starts)
    visited: set[str] = set()
    while pending:
        source = pending.popleft()
        visited.add(source)
        for target in outgoing[source]:
            candidate = depth[source] + 1
            if target not in visited and candidate > depth[target]:
                depth[target] = min(candidate, len(plan.nodes) - 1)
                pending.append(target)
    return depth


def node_size(archetype: str) -> tuple[int, int]:
    return {
        "initial": (16, 16),
        "final": (20, 20),
        "choice": (56, 56),
        "decision": (88, 72),
        "terminal": (128, 48),
        "data": (144, 56),
        "leaf": (128, 48),
        "layer": (720, 56),
    }.get(archetype, (144, 64))


def _subtitle_safe_height(node: GraphNodePlan, width: int, height: int) -> int:
    """Grow a node box when a wrapped two-line title would collide with its subtitle.

    resolve_graph_scene draws the title block centred and pins the subtitle to
    ``box.y + box.h - 8``, so a two-line title needs at least 64 units of height to keep a
    12 unit gap between the last title baseline and the subtitle baseline.
    """
    if not node.subtitle or node.archetype in {"initial", "final"}:
        return height
    style = resolve_text_style(TextRole.NODE_TITLE, DEFAULT_FOLIO_THEME)
    lines = wrap_text(node.label, max(48, width - 24), style.size, style.family, 2)
    return max(height, 64) if len(lines) > 1 else height


def plan_node_size(
    plan: GraphPlan,
    node: GraphNodePlan,
    geometry: GraphGeometry = DEFAULT_GRAPH_GEOMETRY,
) -> tuple[int, int]:
    if not geometry.is_default:
        return _composed_node_size(node, geometry)
    width, height = node_size(node.archetype)
    if len(plan.nodes) <= 8:
        return width, _subtitle_safe_height(node, width, height)
    if node.archetype in {"initial", "final"}:
        return width, height
    if node.archetype in {"choice", "decision"}:
        return min(width, 72), min(height, 60)
    if node.archetype == "leaf":
        return 104, _subtitle_safe_height(node, 104, 44)
    return min(width, 112), _subtitle_safe_height(node, min(width, 112), min(height, 56))


def _composed_node_size(node: GraphNodePlan, geometry: GraphGeometry) -> tuple[int, int]:
    """A node box that holds its own text at the type scale, never a shrunk one.

    The authored layout could trust 144 units because it was measured at 960.
    Composed for a column, a box is only as wide as its longest unbreakable word
    -- the composer refuses to cut a word in half -- plus two insets, and only
    as tall as the lines it draws.
    """
    width, height = geometry.node_size(node.archetype)
    if node.archetype in MARK_ARCHETYPES:
        return width, height
    title = resolve_text_style(TextRole.NODE_TITLE, DEFAULT_FOLIO_THEME)
    # A box that would need a third line is widened until two hold the whole
    # label, because the wrap caps at two and drops the rest.
    width = fit_wrap_width(
        node.label, width, title.size, 2, geometry.title_wrap_inset)
    if node.subtitle:
        meta = resolve_text_style(TextRole.NODE_META, DEFAULT_FOLIO_THEME)
        # The subtitle wraps like the title. Sizing the box to the whole sentence
        # instead would make "running visual checks" the widest node in a
        # six-state chain and leave the chain no stage narrow enough to compose.
        words = node.subtitle.split()
        widest = measure_text(node.subtitle, meta.size, meta.family) if len(words) <= 1 else max(
            measure_text(word, meta.size, meta.family) for word in words)
        width = max(width, grid(widest + 2 * geometry.subtitle_inset))
        width = fit_wrap_width(
            node.subtitle, width, meta.size, 2, 2 * geometry.subtitle_inset)
        subtitle_lines = _staged_wrap(
            node.subtitle, max(48, width - 2 * geometry.subtitle_inset), meta.size)
        height = max(
            height,
            geometry.node_subtitle_height
            + max(0, len(subtitle_lines) - 1) * geometry.subtitle_pitch)
    lines = _staged_wrap(node.label, max(48, width - geometry.title_wrap_inset), title.size)
    if len(lines) > 1:
        height = max(
            height,
            geometry.node_height_floor + (len(lines) - 1) * geometry.fan_pitch)
    return grid(width), grid(height)


def layout_layered_graph(
    plan: GraphPlan,
    geometry: GraphGeometry = DEFAULT_GRAPH_GEOMETRY,
    *,
    axis: str | None = None,
    fold: int = 0,
) -> LayoutResult:
    if not geometry.is_default or fold > 1:
        return _layout_composed(plan, geometry, axis or plan.composition.axis, fold)
    depth = graph_depths(plan)
    bands: dict[int, list[GraphNodePlan]] = defaultdict(list)
    for node in plan.nodes:
        bands[depth[node.id]].append(node)
    width, height = plan.width, plan.height
    boxes: dict[str, LayoutBox] = {}
    gap = 32 if len(plan.nodes) > 8 else 48
    if plan.composition.axis == "left-right":
        level_widths = {level: max(plan_node_size(plan, node)[0] for node in nodes) for level, nodes in bands.items()}
        horizontal_gap = gap
        total_width = sum(level_widths.values()) + max(0, len(level_widths) - 1) * horizontal_gap
        level_x: dict[int, int] = {}
        cursor = grid((width - total_width) / 2)
        for level in sorted(bands):
            level_x[level] = cursor
            cursor += level_widths[level] + horizontal_gap
        band_top = graph_band_top(plan, depth)
        band_bottom = max(band_top + 64, height - 48)
        for level, nodes in sorted(bands.items()):
            heights = [plan_node_size(plan, node)[1] for node in nodes]
            total = sum(heights) + max(0, len(nodes) - 1) * gap
            # Center the band inside the area below the title and above the bottom margin so a
            # single-row graph does not strand the whole diagram in the vertical middle.
            if total >= band_bottom - band_top:
                y = grid((height - total) / 2)
            else:
                y = grid(band_top + (band_bottom - band_top - total) / 2)
            for node, item_height in zip(nodes, heights):
                item_width, _ = plan_node_size(plan, node)
                x = grid(level_x[level] + (level_widths[level] - item_width) / 2)
                boxes[node.id] = LayoutBox(x, y, item_width, item_height)
                y += item_height + gap
    else:
        level_heights = {level: max(plan_node_size(plan, node)[1] for node in nodes) for level, nodes in bands.items()}
        vertical_gap = gap
        total_height = sum(level_heights.values()) + max(0, len(level_heights) - 1) * vertical_gap
        level_y: dict[int, int] = {}
        cursor = max(72, grid((height - total_height) / 2 + 16))
        for level in sorted(bands):
            level_y[level] = cursor
            cursor += level_heights[level] + vertical_gap
        for level, nodes in sorted(bands.items()):
            widths = [plan_node_size(plan, node)[0] for node in nodes]
            total = sum(widths) + max(0, len(nodes) - 1) * gap
            x = grid((width - total) / 2)
            y = level_y[level]
            for node, item_width in zip(nodes, widths):
                # Every node in a band shares the band height so mixed one-line and two-line
                # titles still produce a flush row of boxes.
                boxes[node.id] = LayoutBox(x, y, item_width, level_heights[level])
                x += item_width + gap
    edges = route_graph_edges(plan, boxes, width, height)
    return layout_result(boxes, edges)


def graph_has_feedback(plan: GraphPlan, depth: dict[str, int]) -> bool:
    return any(edge.source != edge.target and depth[edge.target] <= depth[edge.source] for edge in plan.edges)


def graph_band_top(plan: GraphPlan, depth: dict[str, int]) -> int:
    # Feedback edges are routed in a lane above the row, so reserve extra space for them.
    return 176 if graph_has_feedback(plan, depth) else 96


def fit_layered_graph_height(
    plan: GraphPlan,
    geometry: GraphGeometry = DEFAULT_GRAPH_GEOMETRY,
    *,
    axis: str | None = None,
    fold: int = 0,
) -> int:
    """Shrink a left-right graph canvas to the height its single band actually needs."""
    if not geometry.is_default or fold > 1:
        return _composed_height(plan, geometry, axis or plan.composition.axis, fold)
    if plan.composition.axis != "left-right" or not plan.nodes:
        return plan.height
    depth = graph_depths(plan)
    bands: dict[int, list[GraphNodePlan]] = defaultdict(list)
    for node in plan.nodes:
        bands[depth[node.id]].append(node)
    gap = 32 if len(plan.nodes) > 8 else 48
    row = max(
        sum(plan_node_size(plan, node)[1] for node in nodes) + max(0, len(nodes) - 1) * gap
        for nodes in bands.values()
    )
    return max(240, min(plan.height, grid(graph_band_top(plan, depth) + row + 48)))


def route_graph_edges(
    plan: GraphPlan,
    boxes: dict[str, LayoutBox],
    width: int,
    height: int,
    label_obstacles: tuple[LayoutBox, ...] = (),
    geometry: GraphGeometry = DEFAULT_GRAPH_GEOMETRY,
    *,
    axis: str | None = None,
    fold: int = 0,
) -> list[LayoutEdge]:
    if not geometry.is_default or fold > 1:
        return _route_composed(
            plan, boxes, width, height, geometry, axis or plan.composition.axis, fold, label_obstacles)
    # Forward and reverse edges leave a node from different sides (top/bottom versus left/right),
    # so they must be fanned out independently. Mixing them shifts a lone forward connector off
    # centre and leaves a visible kink.
    def _forward(edge: GraphEdgePlan) -> bool:
        source, target = boxes[edge.source], boxes[edge.target]
        return target.x > source.x if plan.composition.axis == "left-right" else target.y > source.y

    outgoing: dict[tuple[str, bool], list[str]] = defaultdict(list)
    incoming: dict[tuple[str, bool], list[str]] = defaultdict(list)
    for edge in plan.edges:
        outgoing[(edge.source, _forward(edge))].append(edge.id)
        incoming[(edge.target, _forward(edge))].append(edge.id)
    # Rank fan-out by where the other endpoint actually sits, not by edge id. Alphabetical ranks
    # hand the leftmost child a right-hand attachment point, which makes sibling connectors cross.
    def _cross(value: LayoutBox) -> int:
        return value.y + value.h // 2 if plan.composition.axis == "left-right" else value.x + value.w // 2

    by_id = {edge.id: edge for edge in plan.edges}
    for ids in outgoing.values():
        ids.sort(key=lambda edge_id: (_cross(boxes[by_id[edge_id].target]), edge_id))
    for ids in incoming.values():
        ids.sort(key=lambda edge_id: (_cross(boxes[by_id[edge_id].source]), edge_id))

    results: list[LayoutEdge] = []
    for edge in plan.edges:
        source, target = boxes[edge.source], boxes[edge.target]
        source_ids = outgoing[(edge.source, _forward(edge))]
        target_ids = incoming[(edge.target, _forward(edge))]
        source_rank = source_ids.index(edge.id)
        target_rank = target_ids.index(edge.id)
        source_offset = grid((source_rank - (len(source_ids) - 1) / 2) * 16)
        target_offset = grid((target_rank - (len(target_ids) - 1) / 2) * 16)
        if plan.composition.axis == "left-right":
            source_offset = max(-source.h // 2 + 2, min(source.h // 2 - 2, source_offset))
            target_offset = max(-target.h // 2 + 2, min(target.h // 2 - 2, target_offset))
        else:
            source_offset = max(-source.w // 2 + 2, min(source.w // 2 - 2, source_offset))
            target_offset = max(-target.w // 2 + 2, min(target.w // 2 - 2, target_offset))
        if edge.source == edge.target:
            start = (source.x + source.w, grid(source.y + source.h / 2 - 8))
            end = (source.x + source.w, grid(source.y + source.h / 2 + 8))
            lane_x = min(width - 24, source.x + source.w + 40)
            points = [start, (lane_x, start[1]), (lane_x, end[1]), end]
        elif plan.composition.axis == "left-right" and target.x > source.x:
            start = (source.x + source.w, grid(source.y + source.h / 2 + source_offset))
            end = (target.x, grid(target.y + target.h / 2 + target_offset))
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = grid(start[0] + (rank + 1) * (end[0] - start[0]) / (count + 1))
            points = [start, (lane, start[1]), (lane, end[1]), end]
            # Neighbouring lanes can leave only a few units between two faces while the rows sit
            # far apart vertically. Landing in that sliver gives the arrowhead no room, so enter
            # through the face that actually has clearance.
            if approach_needs_rerouting((lane, end[1]), end):
                detour = perpendicular_approach(start, target)
                if detour:
                    points = [start, *detour]
        elif plan.composition.axis == "left-right":
            start = (grid(source.x + source.w / 2 + source_offset), source.y)
            end = (grid(target.x + target.w / 2 + target_offset), target.y)
            lane = max(64, min(source.y, target.y) - 40 - 12 * len(results))
            points = [start, (start[0], lane), (end[0], lane), end]
        elif target.y > source.y:
            start = (grid(source.x + source.w / 2 + source_offset), source.y + source.h)
            end = (grid(target.x + target.w / 2 + target_offset), target.y)
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = grid(start[1] + (rank + 1) * (end[1] - start[1]) / (count + 1))
            points = [start, (start[0], lane), (end[0], lane), end]
        else:
            # Reverse (bottom-up) flow: run the feedback lane down whichever gutter still has
            # room. Wide bands such as layer-stack leave no usable space on the left, and a lane
            # clamped to the canvas edge reads as a stray line outside the diagram.
            left_lane = min(source.x, target.x) - 40 - 12 * len(results)
            if left_lane >= 32:
                start = (source.x, grid(source.y + source.h / 2 + source_offset))
                end = (target.x, grid(target.y + target.h / 2 + target_offset))
                lane = grid(left_lane)
            else:
                start = (source.x + source.w, grid(source.y + source.h / 2 + source_offset))
                end = (target.x + target.w, grid(target.y + target.h / 2 + target_offset))
                lane = grid(min(width - 32, max(source.x + source.w, target.x + target.w) + 40 + 12 * len(results)))
            points = [start, (lane, start[1]), (lane, end[1]), end]
        points = list(clean_polyline(points))
        label = edge.label if edge.label and len(edge.label) <= 24 else None
        results.append(LayoutEdge(edge.source, edge.target, points, label, None, edge.id))
    return place_edge_labels(results, list(boxes.values()), width, height, label_obstacles,
                             reach=LABEL_REACH)


def layout_result(boxes: dict[str, LayoutBox], edges: list[LayoutEdge]) -> LayoutResult:
    points = [point for edge in edges for point in edge.points]
    xs = [box.x for box in boxes.values()] + [box.x + box.w for box in boxes.values()] + [x for x, _ in points]
    ys = [box.y for box in boxes.values()] + [box.y + box.h for box in boxes.values()] + [y for _, y in points]
    bounds = LayoutBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)) if xs else LayoutBox(0, 0, 0, 0)
    return LayoutResult(boxes, edges, bounds)


def arrow_for(points: tuple[tuple[int, int], ...]) -> ArrowGeometry:
    if len(points) < 2:
        return ArrowGeometry(((0, 0), (0, 0), (0, 0)))
    before, tip = points[-2], points[-1]
    if tip[0] > before[0]:
        wings = ((tip[0] - 8, tip[1] - 4), tip, (tip[0] - 8, tip[1] + 4))
    elif tip[0] < before[0]:
        wings = ((tip[0] + 8, tip[1] - 4), tip, (tip[0] + 8, tip[1] + 4))
    elif tip[1] > before[1]:
        wings = ((tip[0] - 4, tip[1] - 8), tip, (tip[0] + 4, tip[1] - 8))
    else:
        wings = ((tip[0] - 4, tip[1] + 8), tip, (tip[0] + 4, tip[1] + 8))
    return ArrowGeometry(wings)


def resolve_graph_scene(
    plan: GraphPlan,
    layout: LayoutResult,
    *,
    regions: tuple[SceneRegion, ...] = (),
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
    description: str | None = None,
    geometry: GraphGeometry = DEFAULT_GRAPH_GEOMETRY,
) -> ResolvedScene:
    scene_nodes: list[SceneNode] = []
    for node in plan.nodes:
        box = layout.boxes[node.id]
        focal = node.emphasis == "focal"
        background = node.emphasis == "background"
        fill = theme.brand_tint if focal else theme.parchment if background else theme.ivory
        stroke = theme.brand if focal else theme.muted_stroke if background else theme.near_black
        texts: list[SceneText] = []
        if node.archetype not in {"initial", "final"}:
            title_style = resolve_text_style(TextRole.NODE_TITLE, theme)
            lines = _wrap_for_stage(
                node.label, max(48, box.w - geometry.title_wrap_inset),
                title_style.size, title_style.family, 2, geometry.is_default)
            baseline = grid(box.y + box.h / 2 - (len(lines) - 1) * 8 + (0 if node.subtitle else 4))
            texts.extend(
                SceneText(line, grid(box.x + box.w / 2), baseline + index * 16, title_style.color, title_style.size, title_style.family, "middle", weight=title_style.weight)
                for index, line in enumerate(lines)
            )
            if node.subtitle:
                meta = resolve_text_style(TextRole.NODE_META, theme)
                if geometry.is_default:
                    texts.append(SceneText(
                        node.subtitle, grid(box.x + box.w / 2),
                        box.y + box.h - geometry.subtitle_inset,
                        meta.color, meta.size, meta.family, "middle"))
                else:
                    meta_lines = _staged_wrap(
                        node.subtitle, max(48, box.w - 2 * geometry.subtitle_inset), meta.size)
                    bottom = box.y + box.h - geometry.subtitle_inset
                    texts.extend(
                        SceneText(
                            line, grid(box.x + box.w / 2),
                            bottom - (len(meta_lines) - 1 - index) * geometry.subtitle_pitch,
                            meta.color, meta.size, meta.family, "middle")
                        for index, line in enumerate(meta_lines))
        shape = {
            "choice": "diamond", "decision": "diamond", "terminal": "pill", "data": "data",
            "initial": "circle", "final": "double-circle",
        }.get(node.archetype, "rect")
        scene_nodes.append(SceneNode(
            node.id, SceneBox(box.x, box.y, box.w, box.h),
            SceneStyle(fill, stroke, 1.2, radius=geometry.node_radius), tuple(texts), shape=shape))

    route_by_id = {edge.id: edge for edge in layout.edges if edge.id}
    scene_edges: list[SceneEdge] = []
    for edge in plan.edges:
        route = route_by_id.get(edge.id)
        if route is None:
            raise ValueError(f"{plan.kind} edge has no route: {edge.id}")
        points = tuple(route.points)
        focal = edge.channel == "focal"
        exceptional = edge.channel in {"exceptional", "reset", "response", "async"}
        stroke = theme.brand if focal else theme.label if exceptional else theme.olive
        label = None
        label_box = SceneBox(**asdict(route.label_box)) if route.label_box else None
        if route.label and route.label_box:
            style = resolve_text_style(TextRole.EDGE_LABEL, theme)
            size = style.size if geometry.is_default else geometry.edge_label_size
            label = SceneText(route.label, grid(route.label_box.x + route.label_box.w / 2), grid(route.label_box.y + 12), style.color, size, style.family, "middle")
        scene_edges.append(SceneEdge(
            edge.id, edge.source, edge.target, points,
            SceneStyle(stroke=stroke, stroke_width=1.4, dash=(6, 4) if exceptional else ()),
            arrow_for(points), f"{plan.kind}-edge {plan.kind}-edge--{edge.channel}", label, label_box,
        ))
    title_style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    title = SceneText(
        plan.title, grid(plan.width / 2), geometry.title_baseline,
        title_style.color, title_style.size, title_style.family, "middle")
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, title, regions, tuple(scene_edges), tuple(scene_nodes),
        description=description or f"{plan.kind}: {plan.title}", language=plan.language,
        reading_order=tuple(node.id for node in plan.nodes),
    )


# --- Composed stages -------------------------------------------------------
#
# Everything below runs only when the host has named a stage narrower than the
# canvas the graph was authored on. The authored path above is untouched, so a
# 960-unit artifact cannot move by a rounding step.

def _wrap_for_stage(
    text: str,
    width: int,
    size: float,
    family: str,
    max_lines: int,
    is_default: bool,
) -> tuple[str, ...]:
    """The authored wrap, or the staged one that refuses to cut a word in half."""
    if is_default:
        return wrap_text(text, width, size, family, max_lines)
    return _staged_wrap(text, width, size)


def _graph_bands(plan: GraphPlan) -> tuple[dict[str, int], dict[int, list[GraphNodePlan]]]:
    depth = graph_depths(plan)
    bands: dict[int, list[GraphNodePlan]] = defaultdict(list)
    for node in plan.nodes:
        bands[depth[node.id]].append(node)
    return depth, dict(sorted(bands.items()))


def _composed_gap(plan: GraphPlan, geometry: GraphGeometry) -> int:
    return geometry.dense_node_gap if len(plan.nodes) > geometry.dense_threshold else geometry.node_gap


def _feedback_edges(plan: GraphPlan, depth: dict[str, int]) -> list[GraphEdgePlan]:
    """Edges that leave a node for one no further along the flow.

    Same-depth returns count: they are drawn in the same lane above the row,
    and the row's top has to clear them.
    """
    return [
        edge for edge in plan.edges
        if edge.source != edge.target and depth[edge.target] <= depth[edge.source]
    ]


def _composed_band_top(plan: GraphPlan, depth: dict[str, int], geometry: GraphGeometry) -> int:
    """The top of the first band: the title's clearance plus any feedback lanes.

    The lanes sit in the band between the title and the first row, so the row
    starts below them rather than sharing their space. Reserving only the
    larger of the two put a lane inside the title at narrow stages.
    """
    feedback = len(_feedback_edges(plan, depth))
    reserve = geometry.title_clearance
    if feedback:
        reserve += geometry.label_lane_offset + geometry.label_lane_pitch * feedback
    return reserve


def _band_sizes(
    plan: GraphPlan,
    bands: dict[int, list[GraphNodePlan]],
    geometry: GraphGeometry,
) -> tuple[dict[int, list[tuple[int, int]]], dict[int, int], dict[int, int]]:
    gap = _composed_gap(plan, geometry)
    sizes: dict[int, list[tuple[int, int]]] = {}
    widths: dict[int, int] = {}
    heights: dict[int, int] = {}
    for level, nodes in bands.items():
        items = [plan_node_size(plan, node, geometry) for node in nodes]
        sizes[level] = items
        widths[level] = max(width for width, _height in items)
        heights[level] = sum(height for _width, height in items) + max(0, len(nodes) - 1) * gap
    return sizes, widths, heights


def _row_metrics(
    bands: dict[int, list[GraphNodePlan]],
    sizes: dict[int, list[tuple[int, int]]],
    gap: int,
) -> tuple[list[int], list[int]]:
    """Row width and row height for a top-down band, in band order.

    A band on the top-down axis is a row: its width is the sum of its nodes
    plus the gaps between them, and its height is the tallest node. The
    column form `_band_sizes` returns (max width, summed height) is the
    transpose and cannot be reused for both.
    """
    widths: list[int] = []
    heights: list[int] = []
    for level in bands:
        items = sizes[level]
        widths.append(
            sum(width for width, _height in items)
            + max(0, len(items) - 1) * gap)
        heights.append(max((height for _width, height in items), default=0))
    return widths, heights


def _fold_cell(index: int, fold: int) -> tuple[int, int]:
    """One position on a serpentine grid: rows alternate so the chain never turns back."""
    row, slot = divmod(index, fold)
    return row, (slot if row % 2 == 0 else fold - 1 - slot)


def _fold_rows(count: int, fold: int) -> int:
    return -(-count // fold) if fold > 1 else 1


def _fold_metrics(
    plan: GraphPlan,
    bands: dict[int, list[GraphNodePlan]],
    sizes: dict[int, list[tuple[int, int]]],
    fold: int,
) -> tuple[list[tuple[GraphNodePlan, tuple[int, int], tuple[int, int]]], dict[int, int], dict[int, int]]:
    """Place one *node* per cell, not one band.

    A band can hold two siblings. Folding bands rather than nodes stacked the
    siblings in one cell, and a connector to the lower one ran straight through
    the upper one -- a crossing the layout asked for, not the router. One node
    per cell gives every connector a free row or gutter to arrive in.
    """
    items = [
        (node, size, _fold_cell(index, fold))
        for index, (node, size) in enumerate(
            (node, size)
            for level in bands
            for node, size in zip(bands[level], sizes[level])
        )
    ]
    rows = _fold_rows(len(items), fold)
    col_widths = {column: 0 for column in range(fold)}
    row_heights = {row: 0 for row in range(rows)}
    for _node, (width, height), (row, column) in items:
        col_widths[column] = max(col_widths[column], width)
        row_heights[row] = max(row_heights[row], height)
    return items, col_widths, row_heights


def _place_columns(
    plan: GraphPlan,
    bands: dict[int, list[GraphNodePlan]],
    sizes: dict[int, list[tuple[int, int]]],
    widths: dict[int, int],
    heights: dict[int, int],
    geometry: GraphGeometry,
    band_top: int,
) -> dict[str, LayoutBox]:
    levels = list(bands)
    gap = _composed_gap(plan, geometry)
    side = geometry.side_margin
    available = plan.width - 2 * side
    spread = gap
    if len(levels) > 1:
        spread = max(gap, grid((available - sum(widths.values())) / (len(levels) - 1)))
    total = sum(widths.values()) + spread * (len(levels) - 1)
    cursor = side if total <= available else grid((plan.width - total) / 2)
    tallest = max(heights.values())
    boxes: dict[str, LayoutBox] = {}
    for level in levels:
        y = band_top + max(0, (tallest - heights[level]) // 2)
        for node, (width, height) in zip(bands[level], sizes[level]):
            boxes[node.id] = LayoutBox(
                grid(cursor + (widths[level] - width) / 2), grid(y), width, height)
            y += height + gap
        cursor += widths[level] + spread
    return boxes


def _place_rows(
    plan: GraphPlan,
    bands: dict[int, list[GraphNodePlan]],
    sizes: dict[int, list[tuple[int, int]]],
    geometry: GraphGeometry,
) -> dict[str, LayoutBox]:
    levels = list(bands)
    gap = _composed_gap(plan, geometry)
    side = geometry.side_margin
    available = plan.width - 2 * side
    y = max(geometry.top_down_origin, geometry.title_clearance)
    boxes: dict[str, LayoutBox] = {}
    for level in levels:
        items = sizes[level]
        count = len(items)
        # A row is the opposite of a column: its width is the sum of its nodes
        # and its height is the tallest of them. `widths`/`heights` carry the
        # column form (max width, summed height), so reusing them here made the
        # row as wide as its widest node and gave every node the whole stack's
        # height -- nodes overlapped their neighbours and left the canvas.
        row_width = sum(width for width, _height in items)
        row_height = max((height for _width, height in items), default=0)
        spread = gap
        if count > 1:
            spread = max(gap, grid((available - row_width) / (count - 1)))
        total = row_width + spread * (count - 1)
        cursor = side if total <= available else grid((plan.width - total) / 2)
        for node, (width, height) in zip(bands[level], items):
            # Each box keeps its own height; the row is centred on the tallest.
            boxes[node.id] = LayoutBox(
                grid(cursor), grid(y + (row_height - height) // 2), width, height)
            cursor += width + spread
        y += row_height + gap
    return boxes


def _place_folded(
    plan: GraphPlan,
    bands: dict[int, list[GraphNodePlan]],
    sizes: dict[int, list[tuple[int, int]]],
    geometry: GraphGeometry,
    fold: int,
) -> dict[str, LayoutBox]:
    items, col_widths, row_heights = _fold_metrics(plan, bands, sizes, fold)
    gap = _composed_gap(plan, geometry)
    row_gap = max(gap, geometry.min_row_gap)
    side = geometry.side_margin
    available = plan.width - 2 * side
    spread = max(gap, grid((available - sum(col_widths.values())) / (fold - 1))) if fold > 1 else gap
    needed = sum(col_widths.values()) + spread * (fold - 1)
    if needed > available:
        spread = gap
        needed = sum(col_widths.values()) + spread * (fold - 1)
    cursor = side if needed <= available else grid((plan.width - needed) / 2)
    col_x: dict[int, int] = {}
    for column in range(fold):
        col_x[column] = cursor
        cursor += col_widths[column] + spread
    top = geometry.title_clearance
    row_y: dict[int, int] = {}
    cursor = top
    for row in range(len(row_heights)):
        row_y[row] = cursor
        cursor += row_heights[row] + row_gap
    boxes: dict[str, LayoutBox] = {}
    for node, (width, height), (row, column) in items:
        boxes[node.id] = LayoutBox(
            grid(col_x[column] + (col_widths[column] - width) / 2),
            grid(row_y[row] + (row_heights[row] - height) / 2),
            width, height)
    return boxes


def _layout_composed(
    plan: GraphPlan,
    geometry: GraphGeometry,
    axis: str,
    fold: int,
) -> LayoutResult:
    depth, bands = _graph_bands(plan)
    sizes, widths, heights = _band_sizes(plan, bands, geometry)
    if axis == "left-right" and fold > 1 and len(plan.nodes) > fold:
        boxes = _place_folded(plan, bands, sizes, geometry, fold)
    elif axis == "left-right":
        boxes = _place_columns(
            plan, bands, sizes, widths, heights, geometry,
            _composed_band_top(plan, depth, geometry))
    else:
        boxes = _place_rows(plan, bands, sizes, geometry)
    edges = route_graph_edges(
        plan, boxes, plan.width, plan.height, (),
        geometry=geometry, axis=axis, fold=fold)
    return layout_result(boxes, edges)


def _composed_height(
    plan: GraphPlan,
    geometry: GraphGeometry,
    axis: str,
    fold: int,
) -> int:
    """The canvas the composition actually needs, on the 4-unit grid."""
    depth, bands = _graph_bands(plan)
    sizes, widths, heights = _band_sizes(plan, bands, geometry)
    side = geometry.side_margin
    if axis == "left-right" and fold > 1 and len(plan.nodes) > fold:
        _items, _col_widths, row_heights = _fold_metrics(plan, bands, sizes, fold)
        rows = len(row_heights)
        row_gap = max(_composed_gap(plan, geometry), geometry.min_row_gap)
        body = sum(row_heights.values()) + (rows - 1) * row_gap
        return grid(geometry.title_clearance + body + side)
    if axis == "left-right":
        return grid(_composed_band_top(plan, depth, geometry) + max(heights.values()) + side)
    gap = _composed_gap(plan, geometry)
    origin = max(geometry.top_down_origin, geometry.title_clearance)
    _row_widths, row_heights = _row_metrics(bands, sizes, gap)
    return grid(origin + sum(row_heights) + max(0, len(row_heights) - 1) * gap + side)


def graph_extent(
    plan: GraphPlan,
    geometry: GraphGeometry,
    axis: str,
    fold: int,
) -> tuple[int, int]:
    """The width and height this composition needs at minimum."""
    depth, bands = _graph_bands(plan)
    sizes, widths, heights = _band_sizes(plan, bands, geometry)
    side = geometry.side_margin
    # The gap the placement will really use, not the bare `min_gap`: a fit
    # measured with a smaller gap than the layout draws puts the first column at
    # a negative x and the nodes leave the canvas.
    gap = _composed_gap(plan, geometry)
    row_gap = max(gap, geometry.min_row_gap)
    if axis == "left-right" and fold > 1 and len(plan.nodes) > fold:
        _items, col_widths, row_heights = _fold_metrics(plan, bands, sizes, fold)
        rows = len(row_heights)
        width = 2 * side + sum(col_widths.values()) + (fold - 1) * gap
        height = (
            geometry.title_clearance + sum(row_heights.values())
            + (rows - 1) * row_gap + side)
        return width, height
    if axis == "left-right":
        width = 2 * side + sum(widths.values()) + (len(bands) - 1) * gap
        height = _composed_band_top(plan, depth, geometry) + max(heights.values()) + side
        return width, height
    row_widths, row_heights = _row_metrics(bands, sizes, gap)
    width = 2 * side + max(row_widths, default=0)
    origin = max(geometry.top_down_origin, geometry.title_clearance)
    height = origin + sum(row_heights) + max(0, len(row_heights) - 1) * gap + side
    return width, height


def graph_axis_fits(
    plan: GraphPlan,
    geometry: GraphGeometry,
    axis: str,
    fold: int,
    width: int,
    max_height: int,
) -> bool:
    need_width, need_height = graph_extent(plan, geometry, axis, fold)
    return need_width <= width and need_height <= max_height


def choose_graph_composition(
    plan: GraphPlan,
    geometry: GraphGeometry,
    width: int,
    max_height: int,
) -> tuple[str, int]:
    """The authored axis, a folded authored axis, or the perpendicular one.

    A narrow plate cannot hold a six-level chain sideways: the node title is 12
    units and a word cannot be cut, so the chain is folded into a serpentine
    before the reading direction is changed. Folding preserves the reading
    order; the axis is the last resort because it rewrites the direction the
    author chose.
    """
    authored = plan.composition.axis
    levels = len({*graph_depths(plan).values()})
    options: list[tuple[str, int]] = [(authored, 0)]
    if authored == "left-right":
        options.extend((authored, fold) for fold in range(2, min(5, levels)))
    perpendicular = "top-down" if authored == "left-right" else "left-right"
    options.append((perpendicular, 0))
    if perpendicular == "left-right":
        options.extend((perpendicular, fold) for fold in range(2, min(5, levels)))
    for axis, fold in options:
        if graph_axis_fits(plan, geometry, axis, fold, width, max_height):
            return axis, fold
    return authored, 0


def _route_composed(
    plan: GraphPlan,
    boxes: dict[str, LayoutBox],
    width: int,
    height: int,
    geometry: GraphGeometry,
    axis: str,
    fold: int,
    label_obstacles: tuple[LayoutBox, ...],
) -> list[LayoutEdge]:
    depth = graph_depths(plan)

    def _forward(edge: GraphEdgePlan) -> bool:
        if depth[edge.target] != depth[edge.source]:
            return depth[edge.target] > depth[edge.source]
        return boxes[edge.target].x >= boxes[edge.source].x

    outgoing: dict[tuple[str, bool], list[str]] = defaultdict(list)
    incoming: dict[tuple[str, bool], list[str]] = defaultdict(list)
    for edge in plan.edges:
        outgoing[(edge.source, _forward(edge))].append(edge.id)
        incoming[(edge.target, _forward(edge))].append(edge.id)

    def _cross(value: LayoutBox) -> int:
        return value.y + value.h // 2 if axis == "left-right" else value.x + value.w // 2

    # Every return on a left-right row shares one band above the row, and each
    # takes a lane in it. The band's height is fixed before routing, so the
    # lane index is counted from the far side of the band rather than from the
    # row: counting down from the row put the first return inside the title.
    single_row = axis == "left-right" and not (fold > 1 and len(plan.nodes) > fold)
    feedback_total = (
        sum(1 for edge in plan.edges
            if edge.source != edge.target and not _forward(edge))
        if single_row else 0)

    # A row corridor leaves and enters through the top or bottom face, so a
    # forward connector and the return that answers it share that face. They
    # were fanned out in separate direction groups, which gave both the same
    # attach point and drew one down the other's line. One group per face,
    # ordered by where the other end sits, keeps them apart.
    def _row_faces(edge: GraphEdgePlan) -> tuple[tuple[str, str], ...]:
        if edge.source == edge.target:
            return ()
        start, end = boxes[edge.source], boxes[edge.target]
        different = (
            end.y >= start.y + start.h or end.y + end.h <= start.y)
        if not (different and (axis == "top-down" or fold > 1)):
            return ()
        downward = end.y > start.y
        return (
            (edge.source, "bottom" if downward else "top"),
            (edge.target, "top" if downward else "bottom"),
        )

    face_groups: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for grouped_edge in plan.edges:
        for node_id, face in _row_faces(grouped_edge):
            other = (grouped_edge.target if grouped_edge.source == node_id
                     else grouped_edge.source)
            face_groups[(node_id, face)].append((boxes[other].x, grouped_edge.id))
    for ids in face_groups.values():
        ids.sort()

    def _face_offset(node_id: str, face: str, edge_id: str) -> int:
        ids = [item_id for _x, item_id in face_groups.get((node_id, face), [])] or [edge_id]
        rank = ids.index(edge_id)
        return grid((rank - (len(ids) - 1) / 2) * geometry.fan_pitch)

    by_id = {edge.id: edge for edge in plan.edges}
    for ids in outgoing.values():
        ids.sort(key=lambda edge_id: (_cross(boxes[by_id[edge_id].target]), edge_id))
    for ids in incoming.values():
        ids.sort(key=lambda edge_id: (_cross(boxes[by_id[edge_id].source]), edge_id))

    results: list[LayoutEdge] = []
    feedback = 0
    for edge in plan.edges:
        source, target = boxes[edge.source], boxes[edge.target]
        source_ids = outgoing[(edge.source, _forward(edge))]
        target_ids = incoming[(edge.target, _forward(edge))]
        source_rank = source_ids.index(edge.id)
        target_rank = target_ids.index(edge.id)
        source_offset = grid((source_rank - (len(source_ids) - 1) / 2) * geometry.fan_pitch)
        target_offset = grid((target_rank - (len(target_ids) - 1) / 2) * geometry.fan_pitch)
        # The faces a port sits on follow the geometry, whatever the direction.
        horizontal = (
            target.x >= source.x + source.w or target.x + target.w <= source.x)
        clamp_height = horizontal
        # A backward edge never runs inline. A return that spans more than one
        # column would otherwise draw its lane between source and target, which
        # is through the columns in between -- the default router only ever ran
        # the forward direction inline and sent every return to the outside
        # lane. Drawn inline here, `reset` crossed the nodes it points past.
        forward = _forward(edge)
        horizontal_right = forward and target.x >= source.x + source.w
        horizontal_left = forward and target.x + target.w <= source.x
        # A forward edge and its return share one gutter. Give each direction its
        # own lane, or the two polylines land on the same y and read as one line.
        pair_gap = geometry.min_gap
        mirrored = clamp_height and any(
            other.id != edge.id and other.source == edge.target and other.target == edge.source
            for other in plan.edges)
        if mirrored:
            source_offset += pair_gap if _forward(edge) else -pair_gap
            target_offset += pair_gap if _forward(edge) else -pair_gap
        limit = source.h if clamp_height else source.w
        source_offset = max(-limit // 2 + 2, min(limit // 2 - 2, source_offset))
        limit = target.h if clamp_height else target.w
        target_offset = max(-limit // 2 + 2, min(limit // 2 - 2, target_offset))
        # A folded chain or an upright lane stack moves down the page, so a
        # connector owns the gutter between two rows and travels along it. Giving
        # the row corridor priority keeps every horizontal segment out of the row
        # itself, where a node's mid-height is shared by unrelated connectors.
        different_row = (
            target.y >= source.y + source.h or target.y + target.h <= source.y)
        row_corridor = different_row and (axis == "top-down" or fold > 1)
        if edge.source == edge.target:
            start = (source.x + source.w, grid(source.y + source.h / 2 - 8))
            end = (source.x + source.w, grid(source.y + source.h / 2 + 8))
            lane_x = min(
                width - geometry.label_lane_margin,
                source.x + source.w + geometry.label_lane_offset)
            points = [start, (lane_x, start[1]), (lane_x, end[1]), end]
        elif row_corridor:
            downward = target.y > source.y
            start = (
                grid(source.x + source.w / 2 + _face_offset(
                    edge.source, "bottom" if downward else "top", edge.id)),
                source.y + source.h if downward else source.y)
            end = (
                grid(target.x + target.w / 2 + _face_offset(
                    edge.target, "top" if downward else "bottom", edge.id)),
                target.y if downward else target.y + target.h)
            # Several connectors can leave one face for the same next row. Order
            # their corridors by how far they travel sideways, so the edge that
            # turns soonest turns first and no corridor is cut by another's riser.
            peers = [
                other for other in plan.edges
                if other.source == edge.source and (
                    downward and boxes[other.target].y >= source.y + source.h
                    or not downward
                    and boxes[other.target].y + boxes[other.target].h <= source.y)
            ]
            peers.sort(key=lambda item: (
                abs(boxes[item.target].x - source.x), item.id))
            rank = [item.id for item in peers].index(edge.id)
            pitch = geometry.label_lane_pitch
            # The lane is held back from the target face by a whole arrowhead:
            # clamped only to the row gap, it leaves the tip on the corner it
            # turned at, which draws as a kink (DG137).
            if downward:
                lane = grid(source.y + source.h + pitch * (rank + 1))
                lane = min(lane, target.y - geometry.approach_min)
                lane = max(lane, source.y + source.h)
            else:
                lane = grid(source.y - pitch * (rank + 1))
                lane = max(lane, target.y + target.h + geometry.approach_min)
                lane = min(lane, source.y)
            points = [start, (start[0], lane), (end[0], lane), end]
        elif horizontal_right:
            start = (source.x + source.w, grid(source.y + source.h / 2 + source_offset))
            end = (target.x, grid(target.y + target.h / 2 + target_offset))
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = grid(start[0] + (rank + 1) * (end[0] - start[0]) / (count + 1))
            points = [start, (lane, start[1]), (lane, end[1]), end]
            if approach_needs_rerouting((lane, end[1]), end):
                detour = perpendicular_approach(start, target)
                if detour:
                    points = [start, *[(grid(x), grid(y)) for x, y in detour]]
        elif horizontal_left:
            start = (source.x, grid(source.y + source.h / 2 + source_offset))
            end = (target.x + target.w, grid(target.y + target.h / 2 + target_offset))
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = grid(start[0] - (rank + 1) * (start[0] - end[0]) / (count + 1))
            points = [start, (lane, start[1]), (lane, end[1]), end]
        elif target.y > source.y:
            start = (grid(source.x + source.w / 2 + source_offset), source.y + source.h)
            end = (grid(target.x + target.w / 2 + target_offset), target.y)
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = grid(start[1] + (rank + 1) * (end[1] - start[1]) / (count + 1))
            # Same floor as the row corridor: ordering the fan can push the lane
            # to within an arrowhead of the target face.
            lane = max(min(lane, end[1] - geometry.approach_min), start[1])
            points = [start, (start[0], lane), (end[0], lane), end]
        else:
            feedback += 1
            if single_row:
                # A return on a row runs in a lane above it. A side lane between
                # source and target would be a straight horizontal line through
                # every column in between -- the return has to leave the row.
                # Only a true single row: a folded composition is several rows,
                # and a lane above the first one crosses the rows beneath it.
                start = (grid(source.x + source.w / 2 + source_offset), source.y)
                end = (grid(target.x + target.w / 2 + target_offset), target.y)
                lane = grid(
                    geometry.title_clearance
                    + geometry.label_lane_pitch * (feedback_total - feedback + 1))
                points = [start, (start[0], lane), (end[0], lane), end]
            else:
                left_lane = (
                    min(source.x, target.x) - geometry.label_lane_offset
                    - geometry.label_lane_pitch * feedback)
                if left_lane >= geometry.side_margin + geometry.min_gap:
                    start = (source.x, grid(source.y + source.h / 2 + source_offset))
                    end = (target.x, grid(target.y + target.h / 2 + target_offset))
                    lane = grid(left_lane)
                else:
                    start = (source.x + source.w, grid(source.y + source.h / 2 + source_offset))
                    end = (target.x + target.w, grid(target.y + target.h / 2 + target_offset))
                    lane = grid(min(
                        width - geometry.side_margin,
                        max(source.x + source.w, target.x + target.w)
                        + geometry.label_lane_offset + geometry.label_lane_pitch * feedback))
                points = [start, (lane, start[1]), (lane, end[1]), end]
        points = list(clean_polyline(points))
        label = edge.label if edge.label and len(edge.label) <= 24 else None
        results.append(LayoutEdge(edge.source, edge.target, points, label, None, edge.id))
    return place_edge_labels(
        results, list(boxes.values()), width, height, label_obstacles,
        reach=LABEL_REACH, size=geometry.edge_label_size)
