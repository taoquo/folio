from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Iterable

from .connectors.postprocess import clean_polyline
from .connectors.labels import place_edge_labels
from .layout.models import LayoutBox, LayoutEdge, LayoutResult
from .scene import (
    ArrowGeometry,
    ResolvedScene,
    SceneBox,
    SceneEdge,
    SceneNode,
    SceneRegion,
    SceneStyle,
    SceneText,
)
from .theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from .typography.measure import measure_text
from .typography.roles import TextRole, resolve_text_style
from .validation import (
    DrawingDiagnostic,
    raise_for_errors,
    validate_canvas,
    validate_scene_accessibility,
    validate_scene_geometry,
    validate_scene_primitives,
)


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


def common_payload_diagnostics(
    payload: dict[str, Any],
    *,
    kind: str,
    allowed: set[str],
    required: Iterable[str],
    code: str,
) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    if payload.get("schema_version") != "3.0":
        diagnostics.append(DrawingDiagnostic("ERROR", code, "schema_version must be 3.0"))
    if payload.get("kind") != kind:
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"kind must be {kind}"))
    for name in required:
        if name not in payload:
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"missing required field: {name}"))
    for name in sorted(set(payload) - allowed):
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"unknown field: {name}"))
    if not isinstance(payload.get("title"), str) or not payload.get("title", "").strip():
        diagnostics.append(DrawingDiagnostic("ERROR", code, "title must be a non-empty string"))
    for name in ("width", "height"):
        value = payload.get(name, 960 if name == "width" else 540)
        minimum = 320 if name == "width" else 240
        if not isinstance(value, int) or value < minimum:
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name} must be an integer of at least {minimum}"))
    if payload.get("language") is not None and (not isinstance(payload["language"], str) or not payload["language"].strip()):
        diagnostics.append(DrawingDiagnostic("ERROR", code, "language must be a non-empty string"))
    return diagnostics


def object_list(
    payload: dict[str, Any],
    name: str,
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> list[dict[str, Any]]:
    value = payload.get(name, [])
    if not isinstance(value, list):
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name} must be an array"))
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}] must be an object"))
        else:
            result.append(item)
    return result


def validate_object_fields(
    items: list[dict[str, Any]],
    *,
    name: str,
    allowed: set[str],
    required: Iterable[str],
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> None:
    for index, item in enumerate(items):
        for field in required:
            if field not in item:
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}] missing required field: {field}"))
        for field in sorted(set(item) - allowed):
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}] unknown field: {field}"))


def validate_item_strings(
    items: list[dict[str, Any]],
    fields: Iterable[str],
    *,
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> None:
    for item in items:
        for field in fields:
            if field in item and item[field] is not None and (not isinstance(item[field], str) or not item[field].strip()):
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"{field} must be a non-empty string", str(item.get("id"))))


def validate_unique_ids(
    items: list[dict[str, Any]],
    *,
    name: str,
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> set[str]:
    ids: list[str] = []
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}].id must be a non-empty string"))
        else:
            ids.append(item_id)
    for item_id, count in Counter(ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"duplicate {name} id", item_id))
    return set(ids)


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def infer_language(title: str, labels: Iterable[str], explicit: Any = None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    text = title + "".join(labels)
    return "zh" if any("\u4e00" <= char <= "\u9fff" for char in text) else "en"


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)


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


def plan_node_size(plan: GraphPlan, node: GraphNodePlan) -> tuple[int, int]:
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


def layout_layered_graph(plan: GraphPlan) -> LayoutResult:
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
        cursor = _grid((width - total_width) / 2)
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
                y = _grid((height - total) / 2)
            else:
                y = _grid(band_top + (band_bottom - band_top - total) / 2)
            for node, item_height in zip(nodes, heights):
                item_width, _ = plan_node_size(plan, node)
                x = _grid(level_x[level] + (level_widths[level] - item_width) / 2)
                boxes[node.id] = LayoutBox(x, y, item_width, item_height)
                y += item_height + gap
    else:
        level_heights = {level: max(plan_node_size(plan, node)[1] for node in nodes) for level, nodes in bands.items()}
        vertical_gap = gap
        total_height = sum(level_heights.values()) + max(0, len(level_heights) - 1) * vertical_gap
        level_y: dict[int, int] = {}
        cursor = max(72, _grid((height - total_height) / 2 + 16))
        for level in sorted(bands):
            level_y[level] = cursor
            cursor += level_heights[level] + vertical_gap
        for level, nodes in sorted(bands.items()):
            widths = [plan_node_size(plan, node)[0] for node in nodes]
            total = sum(widths) + max(0, len(nodes) - 1) * gap
            x = _grid((width - total) / 2)
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


def fit_layered_graph_height(plan: GraphPlan) -> int:
    """Shrink a left-right graph canvas to the height its single band actually needs."""
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
    return max(240, min(plan.height, _grid(graph_band_top(plan, depth) + row + 48)))


def route_graph_edges(
    plan: GraphPlan,
    boxes: dict[str, LayoutBox],
    width: int,
    height: int,
    label_obstacles: tuple[LayoutBox, ...] = (),
) -> list[LayoutEdge]:
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
    for key, ids in outgoing.items():
        ids.sort(key=lambda edge_id: (_cross(boxes[by_id[edge_id].target]), edge_id))
    for key, ids in incoming.items():
        ids.sort(key=lambda edge_id: (_cross(boxes[by_id[edge_id].source]), edge_id))

    results: list[LayoutEdge] = []
    for edge in plan.edges:
        source, target = boxes[edge.source], boxes[edge.target]
        source_ids = outgoing[(edge.source, _forward(edge))]
        target_ids = incoming[(edge.target, _forward(edge))]
        source_rank = source_ids.index(edge.id)
        target_rank = target_ids.index(edge.id)
        source_offset = _grid((source_rank - (len(source_ids) - 1) / 2) * 16)
        target_offset = _grid((target_rank - (len(target_ids) - 1) / 2) * 16)
        if plan.composition.axis == "left-right":
            source_offset = max(-source.h // 2 + 2, min(source.h // 2 - 2, source_offset))
            target_offset = max(-target.h // 2 + 2, min(target.h // 2 - 2, target_offset))
        else:
            source_offset = max(-source.w // 2 + 2, min(source.w // 2 - 2, source_offset))
            target_offset = max(-target.w // 2 + 2, min(target.w // 2 - 2, target_offset))
        if edge.source == edge.target:
            start = (source.x + source.w, _grid(source.y + source.h / 2 - 8))
            end = (source.x + source.w, _grid(source.y + source.h / 2 + 8))
            lane_x = min(width - 24, source.x + source.w + 40)
            points = [start, (lane_x, start[1]), (lane_x, end[1]), end]
        elif plan.composition.axis == "left-right" and target.x > source.x:
            start = (source.x + source.w, _grid(source.y + source.h / 2 + source_offset))
            end = (target.x, _grid(target.y + target.h / 2 + target_offset))
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = _grid(start[0] + (rank + 1) * (end[0] - start[0]) / (count + 1))
            points = [start, (lane, start[1]), (lane, end[1]), end]
        elif plan.composition.axis == "left-right":
            start = (_grid(source.x + source.w / 2 + source_offset), source.y)
            end = (_grid(target.x + target.w / 2 + target_offset), target.y)
            lane = max(64, min(source.y, target.y) - 40 - 12 * len(results))
            points = [start, (start[0], lane), (end[0], lane), end]
        elif target.y > source.y:
            start = (_grid(source.x + source.w / 2 + source_offset), source.y + source.h)
            end = (_grid(target.x + target.w / 2 + target_offset), target.y)
            if len(source_ids) >= len(target_ids):
                rank, count = source_rank, len(source_ids)
            else:
                rank, count = target_rank, len(target_ids)
            lane = _grid(start[1] + (rank + 1) * (end[1] - start[1]) / (count + 1))
            points = [start, (start[0], lane), (end[0], lane), end]
        else:
            # Reverse (bottom-up) flow: run the feedback lane down whichever gutter still has
            # room. Wide bands such as layer-stack leave no usable space on the left, and a lane
            # clamped to the canvas edge reads as a stray line outside the diagram.
            left_lane = min(source.x, target.x) - 40 - 12 * len(results)
            if left_lane >= 32:
                start = (source.x, _grid(source.y + source.h / 2 + source_offset))
                end = (target.x, _grid(target.y + target.h / 2 + target_offset))
                lane = _grid(left_lane)
            else:
                start = (source.x + source.w, _grid(source.y + source.h / 2 + source_offset))
                end = (target.x + target.w, _grid(target.y + target.h / 2 + target_offset))
                lane = _grid(min(width - 32, max(source.x + source.w, target.x + target.w) + 40 + 12 * len(results)))
            points = [start, (lane, start[1]), (lane, end[1]), end]
        points = list(clean_polyline(points))
        label = edge.label if edge.label and len(edge.label) <= 24 else None
        results.append(LayoutEdge(edge.source, edge.target, points, label, None, edge.id))
    return place_edge_labels(results, list(boxes.values()), width, height, label_obstacles)


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
            lines = wrap_text(node.label, max(48, box.w - 24), title_style.size, title_style.family, 2)
            baseline = _grid(box.y + box.h / 2 - (len(lines) - 1) * 8 + (0 if node.subtitle else 4))
            texts.extend(
                SceneText(line, box.x + box.w // 2, baseline + index * 16, title_style.color, title_style.size, title_style.family, "middle", weight=title_style.weight)
                for index, line in enumerate(lines)
            )
            if node.subtitle:
                meta = resolve_text_style(TextRole.NODE_META, theme)
                texts.append(SceneText(node.subtitle, box.x + box.w // 2, box.y + box.h - 8, meta.color, meta.size, meta.family, "middle"))
        shape = {
            "choice": "diamond", "decision": "diamond", "terminal": "pill", "data": "data",
            "initial": "circle", "final": "double-circle",
        }.get(node.archetype, "rect")
        scene_nodes.append(SceneNode(node.id, SceneBox(box.x, box.y, box.w, box.h), SceneStyle(fill, stroke, 1.2, radius=6), tuple(texts), shape=shape))

    route_by_id = {edge.id: edge for edge in layout.edges if edge.id}
    scene_edges: list[SceneEdge] = []
    for edge in plan.edges:
        route = route_by_id.get(edge.id)
        if route is None:
            raise ValueError(f"{plan.kind} edge has no route: {edge.id}")
        points = tuple(route.points)
        focal = edge.channel == "focal"
        exceptional = edge.channel in {"exceptional", "reset", "response", "async"}
        stroke = theme.brand if focal else theme.stone if exceptional else theme.olive
        label = None
        label_box = SceneBox(**asdict(route.label_box)) if route.label_box else None
        if route.label and route.label_box:
            style = resolve_text_style(TextRole.EDGE_LABEL, theme)
            label = SceneText(route.label, _grid(route.label_box.x + route.label_box.w / 2), _grid(route.label_box.y + 12), style.color, style.size, style.family, "middle")
        scene_edges.append(SceneEdge(
            edge.id, edge.source, edge.target, points,
            SceneStyle(stroke=stroke, stroke_width=1.4, dash=(6, 4) if exceptional else ()),
            arrow_for(points), f"{plan.kind}-edge {plan.kind}-edge--{edge.channel}", label, label_box,
        ))
    title_style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    title = SceneText(plan.title, plan.width // 2, 40, title_style.color, title_style.size, title_style.family, "middle")
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, title, regions, tuple(scene_edges), tuple(scene_nodes),
        description=description or f"{plan.kind}: {plan.title}", language=plan.language,
        reading_order=tuple(node.id for node in plan.nodes),
    )


def validate_resolved_scene(scene: ResolvedScene) -> tuple[DrawingDiagnostic, ...]:
    diagnostics = tuple([
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene),
    ])
    raise_for_errors("scene", diagnostics)
    return diagnostics


def wrap_text(text: str, width: int, size: float, family: str, max_lines: int = 2) -> tuple[str, ...]:
    if measure_text(text, size, family) <= width:
        return (text,)
    words = text.split()
    if len(words) <= 1:
        limit = max(2, int(width / max(1, size)))
        return tuple(text[index:index + limit] for index in range(0, min(len(text), limit * max_lines), limit))
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and measure_text(candidate, size, family) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return tuple(lines[:max_lines])


def require_no_errors(stage: str, diagnostics: Iterable[DrawingDiagnostic]) -> tuple[DrawingDiagnostic, ...]:
    result = tuple(diagnostics)
    raise_for_errors(stage, result)
    return result


def reachable(starts: Iterable[str], edges: Iterable[tuple[str, str]]) -> set[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        graph[source].append(target)
    result = set(starts)
    pending = list(starts)
    while pending:
        for target in graph[pending.pop()]:
            if target not in result:
                result.add(target)
                pending.append(target)
    return result


def cycle_exists(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        graph[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in graph[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in nodes)


def dimensions(payload: dict[str, Any], default_height: int = 540) -> tuple[int, int]:
    return int(payload.get("width", 960)), int(payload.get("height", default_height))
