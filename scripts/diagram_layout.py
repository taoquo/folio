from __future__ import annotations

import json
import heapq
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from diagram_models import ArchitectureDiagramSpec, DiagramSpec, UmlClassDiagramSpec


ROOT = Path(__file__).resolve().parents[1]
ELK_RUNNER = ROOT / "scripts" / "diagram_elk_runner.js"
ELK_BUNDLED = ROOT / "scripts" / "vendor" / "elk.bundled.js"
GRID = 4


@dataclass(frozen=True)
class LayoutBox:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class LayoutEdge:
    source: str
    target: str
    points: list[tuple[int, int]]
    label: str | None = None
    label_box: LayoutBox | None = None


@dataclass(frozen=True)
class LayoutResult:
    boxes: dict[str, LayoutBox]
    edges: list[LayoutEdge]
    bounds: LayoutBox
    warnings: list[str] = field(default_factory=list)


def elk_available() -> bool:
    return shutil.which("node") is not None and ELK_RUNNER.exists() and ELK_BUNDLED.exists()


def layout_diagram(spec: DiagramSpec) -> LayoutResult:
    if getattr(spec, "kind", None) == "architecture":
        return layout_architecture(spec)
    if getattr(spec, "kind", None) == "uml-class":
        return layout_uml_class(spec)
    raise TypeError(f"unsupported spec type: {type(spec)!r}")


def layout_architecture(spec: ArchitectureDiagramSpec) -> LayoutResult:
    graph = _architecture_elk_graph(spec)
    result = _layout_with_retries(graph, spec.width, spec.height, allow_scale=True, strict=False)
    if spec.layout == "horizontal-layers":
        result = _normalize_architecture_layers(spec, result)
    issues = validate_layout(result, spec.width, spec.height)
    if issues:
        raise RuntimeError("diagram geometry validation failed: " + "; ".join(issues))
    return result


_ARCH_NODE_W = 176
_ARCH_NODE_H = 72
_ARCH_NODE_SPACING = "48"
_ARCH_LAYER_SPACING = "96"
_ARCH_PADDING = "[top=80,left=96,bottom=72,right=96]"


def _architecture_elk_graph(spec: ArchitectureDiagramSpec) -> dict[str, Any]:
    layer_order = [layer.id for layer in spec.layers]
    layer_index = {layer_id: index for index, layer_id in enumerate(layer_order)}

    def resolve_layer(node: Any) -> str:
        layer = node.layer or "default"
        return layer if layer in layer_index else f"unlayered:{layer}"

    options = {
        "elk.algorithm": "layered",
        "elk.direction": "DOWN",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.layered.spacing.nodeNodeBetweenLayers": _ARCH_LAYER_SPACING,
        "elk.spacing.nodeNode": _ARCH_NODE_SPACING,
        "elk.spacing.edgeNode": "24",
        "elk.spacing.edgeEdge": "18",
        "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
        "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
        "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
        "elk.layered.layering.strategy": "NETWORK_SIMPLEX",
        "elk.padding": _ARCH_PADDING,
        "elk.width": str(spec.width),
        "elk.height": str(spec.height),
    }
    graph: dict[str, Any] = {
        "id": "root",
        "layoutOptions": options,
        "children": [],
        "edges": [],
    }
    for node in spec.nodes:
        child: dict[str, Any] = {
            "id": node.id,
            "width": _ARCH_NODE_W,
            "height": _ARCH_NODE_H,
            "layoutOptions": {
                **_node_port_options(),
                "elk.portLabels.hide": "true",
                "elk.layered.layering.layerId": resolve_layer(node),
            },
            "ports": _ports_for_node(node.id),
        }
        graph["children"].append(child)

    for index, edge in enumerate(spec.edges):
        source_layer = next((resolve_layer(n) for n in spec.nodes if n.id == edge.source), "default")
        target_layer = next((resolve_layer(n) for n in spec.nodes if n.id == edge.target), "default")
        source_port, target_port = _architecture_edge_ports(edge, source_layer, target_layer, layer_index)
        elk_edge: dict[str, Any] = {
            "id": f"arch:{index}:{edge.source}->{edge.target}",
            "sources": [source_port],
            "targets": [target_port],
        }
        graph["edges"].append(elk_edge)
    return graph


def _architecture_edge_ports(
    edge: Any,
    source_layer: str,
    target_layer: str,
    layer_index: dict[str, int],
) -> tuple[str, str]:
    source_side = edge.source_port
    target_side = edge.target_port
    source_idx = layer_index.get(source_layer, -1)
    target_idx = layer_index.get(target_layer, -1)
    if source_side not in {"top", "right", "bottom", "left"} or target_side not in {"top", "right", "bottom", "left"}:
        if target_idx > source_idx:
            source_side = source_side or "bottom"
            target_side = target_side or "top"
        elif target_idx < source_idx:
            source_side = source_side or "top"
            target_side = target_side or "bottom"
        else:
            source_side = source_side or "right"
            target_side = target_side or "left"
    return (
        f"{edge.source}:{_side_name(source_side)}",
        f"{edge.target}:{_side_name(target_side)}",
    )


def layout_uml_class(spec: UmlClassDiagramSpec) -> LayoutResult:
    if all(item.x is not None and item.y is not None for item in spec.types):
        boxes = {
            item.id: LayoutBox(item.x or 0, item.y or 0, 220, 62 + 18 * len(item.attributes) + 18 * len(item.methods))
            for item in spec.types
        }
        edges = _uml_manual_edges(spec, boxes)
        bounds = _bounds_for(boxes, edges)
        boxes, edges, bounds = _fit_to_stage(boxes, edges, bounds, spec.width, spec.height, allow_scale=False)
        result = LayoutResult(boxes=boxes, edges=edges, bounds=bounds)
        issues = validate_layout(result, spec.width, spec.height)
        if issues:
            raise RuntimeError("diagram geometry validation failed: " + "; ".join(issues))
        return result

    nodes = []
    for item in spec.types:
        body_h = 62 + 18 * len(item.attributes) + 18 * len(item.methods)
        node: dict[str, Any] = {
            "id": item.id,
            "width": 220,
            "height": body_h,
            "layoutOptions": _node_port_options(),
            "ports": _ports_for_node(item.id),
        }
        if item.x is not None and item.y is not None:
            node["x"] = item.x
            node["y"] = item.y
            node["layoutOptions"]["elk.position"] = f"({item.x},{item.y})"
        nodes.append(node)

    graph = _base_elk_graph(spec.width, spec.height, direction="RIGHT")
    graph["children"] = nodes
    graph["edges"] = [
        {
            "id": f"r{index}:{rel.source}->{rel.target}",
            "sources": [f"{rel.source}:east"],
            "targets": [f"{rel.target}:west"],
            "labels": _edge_labels(rel.label),
        }
        for index, rel in enumerate(spec.relationships)
    ]
    return _layout_with_retries(graph, spec.width, spec.height, allow_scale=False)


def _uml_manual_edges(spec: UmlClassDiagramSpec, boxes: dict[str, LayoutBox]) -> list[LayoutEdge]:
    edges = []
    for relation in spec.relationships:
        source = boxes[relation.source]
        target = boxes[relation.target]
        points = _uml_simple_route(source, target)
        label_box = None
        if relation.label:
            label_x, label_y = _edge_label_anchor(points)
            label_box = LayoutBox(label_x - max(44, len(relation.label) * 7 + 14) // 2, label_y - 18, max(44, len(relation.label) * 7 + 14), 14)
            label_box = _avoid_label_nodes(label_box, boxes, {relation.source, relation.target})
        edges.append(LayoutEdge(source=relation.source, target=relation.target, points=points, label=relation.label, label_box=label_box))
    return edges


def _uml_simple_route(source: LayoutBox, target: LayoutBox) -> list[tuple[int, int]]:
    if source.x + source.w <= target.x:
        start = (source.x + source.w, source.y + source.h // 2)
        end = (target.x, target.y + target.h // 2)
        mid_x = _grid((start[0] + end[0]) // 2)
        return [start, (mid_x, start[1]), (mid_x, end[1]), end]
    if target.x + target.w <= source.x:
        start = (source.x, source.y + source.h // 2)
        end = (target.x + target.w, target.y + target.h // 2)
        mid_x = _grid((start[0] + end[0]) // 2)
        return [start, (mid_x, start[1]), (mid_x, end[1]), end]
    if source.y <= target.y:
        start = (source.x + source.w // 2, source.y + source.h)
        end = (target.x + target.w // 2, target.y)
    else:
        start = (source.x + source.w // 2, source.y)
        end = (target.x + target.w // 2, target.y + target.h)
    mid_y = _grid((start[1] + end[1]) // 2)
    return [start, (start[0], mid_y), (end[0], mid_y), end]


def _base_elk_graph(width: int, height: int, direction: str) -> dict[str, Any]:
    return {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": direction,
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.layered.spacing.nodeNodeBetweenLayers": "72",
            "elk.spacing.nodeNode": "56",
            "elk.spacing.edgeNode": "24",
            "elk.spacing.edgeEdge": "18",
            "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
            "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
            "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
            "elk.padding": "[top=84,left=96,bottom=72,right=96]",
            "elk.width": str(width),
            "elk.height": str(height),
        },
        "children": [],
        "edges": [],
    }


def _node_port_options() -> dict[str, str]:
    return {
        "elk.portConstraints": "FIXED_SIDE",
        "elk.port.side": "EAST",
    }


def _ports_for_node(node_id: str) -> list[dict[str, Any]]:
    return [
        {"id": f"{node_id}:north", "width": 2, "height": 2, "layoutOptions": {"elk.port.side": "NORTH"}},
        {"id": f"{node_id}:east", "width": 2, "height": 2, "layoutOptions": {"elk.port.side": "EAST"}},
        {"id": f"{node_id}:south", "width": 2, "height": 2, "layoutOptions": {"elk.port.side": "SOUTH"}},
        {"id": f"{node_id}:west", "width": 2, "height": 2, "layoutOptions": {"elk.port.side": "WEST"}},
    ]


def _side_name(side: str) -> str:
    return {"top": "north", "right": "east", "bottom": "south", "left": "west"}[side]


def _edge_labels(label: str | None) -> list[dict[str, Any]]:
    if not label:
        return []
    return [{"text": label, "width": max(44, len(label) * 7 + 14), "height": 14}]


def _normalize_architecture_layers(spec: ArchitectureDiagramSpec, result: LayoutResult) -> LayoutResult:
    rows = _architecture_rows(spec)
    if not rows:
        return result

    stage_left, stage_top = 72, 88
    stage_right = spec.width - 72
    stage_bottom = spec.height - (112 if spec.legend else 56)
    node_gap = 48
    node_h = max((box.h for box in result.boxes.values()), default=_ARCH_NODE_H)
    row_gap = 0
    if len(rows) > 1:
        row_gap = (stage_bottom - stage_top - node_h) / (len(rows) - 1)

    boxes: dict[str, LayoutBox] = {}
    source_order = result.boxes
    for row_index, (_layer_id, node_ids) in enumerate(rows):
        ordered = sorted(node_ids, key=lambda node_id: (source_order.get(node_id, LayoutBox(0, 0, 0, 0)).x, node_id))
        widths = [source_order.get(node_id, LayoutBox(0, 0, _ARCH_NODE_W, _ARCH_NODE_H)).w for node_id in ordered]
        total_w = sum(widths) + max(0, len(widths) - 1) * node_gap
        available = stage_right - stage_left
        gap = node_gap
        if total_w > available and len(widths) > 1:
            gap = max(24, (available - sum(widths)) // (len(widths) - 1))
            total_w = sum(widths) + max(0, len(widths) - 1) * gap
        x = _grid(stage_left + max(0, (available - total_w) / 2))
        y = _grid(stage_top + row_index * row_gap)
        for node_id, node_w in zip(ordered, widths):
            old = source_order.get(node_id, LayoutBox(0, 0, _ARCH_NODE_W, _ARCH_NODE_H))
            boxes[node_id] = LayoutBox(x, y, old.w, old.h)
            x += old.w + gap

    edges = _route_architecture_edges(spec, boxes)
    bounds = _bounds_for(boxes, edges)
    boxes, edges, bounds = _fit_to_stage(boxes, edges, bounds, spec.width, spec.height, allow_scale=False)
    return LayoutResult(boxes=boxes, edges=edges, bounds=bounds, warnings=result.warnings)


def _architecture_rows(spec: ArchitectureDiagramSpec) -> list[tuple[str, list[str]]]:
    layer_order = [layer.id for layer in spec.layers] or ["default"]
    rows: list[tuple[str, list[str]]] = []
    assigned: set[str] = set()
    for layer_id in layer_order:
        node_ids = [node.id for node in spec.nodes if (node.layer or "default") == layer_id]
        if node_ids:
            rows.append((layer_id, node_ids))
            assigned.update(node_ids)
    unlayered = [node.id for node in spec.nodes if node.id not in assigned]
    if unlayered:
        rows.append(("unlayered", unlayered))
    return rows


def _route_architecture_edges(spec: ArchitectureDiagramSpec, boxes: dict[str, LayoutBox]) -> list[LayoutEdge]:
    layer_order = [layer.id for layer in spec.layers]
    layer_index = {layer_id: index for index, layer_id in enumerate(layer_order)}
    node_layer = {node.id: node.layer or "default" for node in spec.nodes}
    edges: list[LayoutEdge] = []
    for edge in spec.edges:
        if edge.source not in boxes or edge.target not in boxes:
            continue
        source_layer = node_layer.get(edge.source, "default")
        target_layer = node_layer.get(edge.target, "default")
        source_side, target_side = _architecture_edge_sides(edge, source_layer, target_layer, layer_index, boxes)
        points = _route_between_boxes(
            boxes[edge.source],
            boxes[edge.target],
            source_side,
            target_side,
            boxes,
            {edge.source, edge.target},
            spec.width,
            spec.height,
        )
        edges.append(LayoutEdge(source=edge.source, target=edge.target, points=points))
    return edges


def _architecture_edge_sides(
    edge: Any,
    source_layer: str,
    target_layer: str,
    layer_index: dict[str, int],
    boxes: dict[str, LayoutBox],
) -> tuple[str, str]:
    source_side = edge.source_port if edge.source_port in {"top", "right", "bottom", "left"} else None
    target_side = edge.target_port if edge.target_port in {"top", "right", "bottom", "left"} else None
    if source_side and target_side:
        return source_side, target_side

    source_idx = layer_index.get(source_layer, -1)
    target_idx = layer_index.get(target_layer, -1)
    if target_idx > source_idx:
        return "bottom", "top"
    if target_idx < source_idx:
        return "top", "bottom"

    source = boxes[edge.source]
    target = boxes[edge.target]
    if source.x <= target.x:
        return "right", "left"
    return "left", "right"


def _route_between_boxes(
    source: LayoutBox,
    target: LayoutBox,
    source_side: str,
    target_side: str,
    boxes: dict[str, LayoutBox] | None = None,
    allowed: set[str] | None = None,
    width: int = 960,
    height: int = 540,
) -> list[tuple[int, int]]:
    start = _anchor(source, source_side)
    end = _anchor(target, target_side)
    if start[0] == end[0] or start[1] == end[1]:
        simple = [start, end]
    elif source_side in {"top", "bottom"} and target_side in {"top", "bottom"}:
        mid_y = _grid((start[1] + end[1]) / 2)
        simple = [start, (start[0], mid_y), (end[0], mid_y), end]
    elif source_side in {"left", "right"} and target_side in {"left", "right"}:
        mid_x = _grid((start[0] + end[0]) / 2)
        simple = [start, (mid_x, start[1]), (mid_x, end[1]), end]
    else:
        simple = [start, _grid_point((start[0], end[1])), end]

    if not boxes or not _route_crosses_blocked(simple, boxes, allowed or set()):
        return simple

    routed = _orthogonal_grid_route(start, end, boxes, allowed or set(), width, height)
    return routed or simple


def _route_crosses_blocked(points: list[tuple[int, int]], boxes: dict[str, LayoutBox], allowed: set[str]) -> bool:
    return any(
        node_id not in allowed and _polyline_crosses_box(points, box)
        for node_id, box in boxes.items()
    )


def _orthogonal_grid_route(
    start: tuple[int, int],
    end: tuple[int, int],
    boxes: dict[str, LayoutBox],
    allowed: set[str],
    width: int,
    height: int,
) -> list[tuple[int, int]] | None:
    padding = 20
    min_x, max_x = 48, width - 48
    min_y, max_y = 64, height - 48
    obstacles = [
        LayoutBox(box.x - 8, box.y - 8, box.w + 16, box.h + 16)
        for node_id, box in boxes.items()
        if node_id not in allowed
    ]
    xs = {min_x, max_x, start[0], end[0]}
    ys = {min_y, max_y, start[1], end[1]}
    for box in obstacles:
        xs.update({_grid(box.x - padding), _grid(box.x + box.w + padding), _grid(box.x + box.w / 2)})
        ys.update({_grid(box.y - padding), _grid(box.y + box.h + padding), _grid(box.y + box.h / 2)})
    xs = {x for x in xs if min_x <= x <= max_x}
    ys = {y for y in ys if min_y <= y <= max_y}
    nodes = {(x, y) for x in xs for y in ys}
    nodes.add(start)
    nodes.add(end)

    def clear(a: tuple[int, int], b: tuple[int, int]) -> bool:
        if a == b:
            return False
        if a[0] != b[0] and a[1] != b[1]:
            return False
        return not any(_segment_crosses_box(a, b, obstacle) for obstacle in obstacles)

    heap: list[tuple[int, int, tuple[int, int], str | None]] = [(0, 0, start, None)]
    best: dict[tuple[tuple[int, int], str | None], int] = {(start, None): 0}
    previous: dict[tuple[tuple[int, int], str | None], tuple[tuple[int, int], str | None]] = {}
    counter = 1
    end_state: tuple[tuple[int, int], str | None] | None = None

    while heap:
        cost, _counter, point, direction = heapq.heappop(heap)
        state = (point, direction)
        if cost != best.get(state):
            continue
        if point == end:
            end_state = state
            break
        for candidate in nodes:
            if candidate == point or not clear(point, candidate):
                continue
            next_direction = "h" if candidate[1] == point[1] else "v"
            distance = abs(candidate[0] - point[0]) + abs(candidate[1] - point[1])
            turn_penalty = 80 if direction and direction != next_direction else 0
            next_cost = cost + distance + turn_penalty
            next_state = (candidate, next_direction)
            if next_cost < best.get(next_state, 10**9):
                best[next_state] = next_cost
                previous[next_state] = state
                heapq.heappush(heap, (next_cost, counter, candidate, next_direction))
                counter += 1

    if end_state is None:
        return None

    path = []
    state = end_state
    while True:
        path.append(state[0])
        if state[0] == start:
            break
        state = previous[state]
    return _simplify_polyline(list(reversed(path)))


def _segment_crosses_box(start: tuple[int, int], end: tuple[int, int], box: LayoutBox) -> bool:
    if start[0] == end[0]:
        x = start[0]
        y1, y2 = sorted([start[1], end[1]])
        return box.x < x < box.x + box.w and y1 < box.y + box.h and y2 > box.y
    if start[1] == end[1]:
        y = start[1]
        x1, x2 = sorted([start[0], end[0]])
        return box.y < y < box.y + box.h and x1 < box.x + box.w and x2 > box.x
    return False


def _simplify_polyline(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    simplified: list[tuple[int, int]] = []
    for point in points:
        if simplified and simplified[-1] == point:
            continue
        simplified.append(point)
        while len(simplified) >= 3:
            a, b, c = simplified[-3:]
            if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
                simplified.pop(-2)
            else:
                break
    return simplified


def _anchor(box: LayoutBox, side: str) -> tuple[int, int]:
    if side == "top":
        return (_grid(box.x + box.w / 2), box.y)
    if side == "right":
        return (box.x + box.w, _grid(box.y + box.h / 2))
    if side == "bottom":
        return (_grid(box.x + box.w / 2), box.y + box.h)
    if side == "left":
        return (box.x, _grid(box.y + box.h / 2))
    raise ValueError(f"unsupported side: {side}")


def _grid_point(point: tuple[int, int]) -> tuple[int, int]:
    return (_grid(point[0]), _grid(point[1]))


def _edge_label_anchor(points: list[tuple[int, int]]) -> tuple[int, int]:
    start, end = max(
        zip(points, points[1:]),
        key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]),
    )
    return (_grid((start[0] + end[0]) // 2), _grid((start[1] + end[1]) // 2))


def _avoid_label_nodes(label: LayoutBox, boxes: dict[str, LayoutBox], allowed: set[str]) -> LayoutBox:
    current = label
    for node_id, box in boxes.items():
        if node_id in allowed and _boxes_overlap(current, box, padding=4):
            current = _shift_box(current, 0, -28)
    for _ in range(4):
        collision = False
        for node_id, box in boxes.items():
            if node_id in allowed:
                continue
            if _boxes_overlap(current, box, padding=4):
                current = _shift_box(current, 0, -18)
                collision = True
                break
        if not collision:
            return current
    return current


def _layout_with_retries(
    graph: dict[str, Any],
    width: int,
    height: int,
    allow_scale: bool = True,
    strict: bool = True,
) -> LayoutResult:
    if not elk_available():
        raise RuntimeError("ELK layout unavailable: require node and scripts/vendor/elk.bundled.js")
    spacing = 56
    last_result: LayoutResult | None = None
    last_issues: list[str] = []
    for _attempt in range(3):
        graph["layoutOptions"]["elk.spacing.nodeNode"] = str(spacing)
        graph["layoutOptions"]["elk.layered.spacing.nodeNodeBetweenLayers"] = str(spacing + 16)
        raw = _run_elk(graph)
        result = _extract_layout(raw, width, height, allow_scale=allow_scale)
        issues = validate_layout(result, width, height)
        if not issues:
            return result
        last_result = result
        last_issues = issues
        spacing += 24
    if last_result is None:
        raise RuntimeError("ELK layout failed before producing a result")
    if not strict:
        return LayoutResult(
            boxes=last_result.boxes,
            edges=last_result.edges,
            bounds=last_result.bounds,
            warnings=last_issues,
        )
    raise RuntimeError("diagram geometry validation failed: " + "; ".join(last_issues))


def _run_elk(graph: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(ELK_RUNNER)],
        input=json.dumps(graph),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "elk runner failed")
    return json.loads(result.stdout)


def _extract_layout(raw: dict[str, Any], width: int, height: int, allow_scale: bool = True) -> LayoutResult:
    boxes: dict[str, LayoutBox] = {}
    port_points: dict[str, tuple[int, int]] = {}
    _collect_boxes(raw, 0, 0, boxes, port_points)
    edges = _collect_edges(raw, port_points)
    bounds = _bounds_for(boxes, edges)
    boxes, edges, bounds = _fit_to_stage(boxes, edges, bounds, width, height, allow_scale=allow_scale)
    return LayoutResult(boxes=boxes, edges=edges, bounds=bounds)


def _collect_boxes(
    node: dict[str, Any],
    offset_x: float,
    offset_y: float,
    boxes: dict[str, LayoutBox],
    port_points: dict[str, tuple[int, int]],
) -> None:
    x = offset_x + float(node.get("x", 0))
    y = offset_y + float(node.get("y", 0))
    if "width" in node and "height" in node and node.get("id") != "root" and not str(node.get("id", "")).startswith("group:"):
        boxes[node["id"]] = LayoutBox(_grid(x), _grid(y), _grid(node["width"]), _grid(node["height"]))
    for port in node.get("ports", []):
        port_points[port["id"]] = (_grid(x + float(port.get("x", 0))), _grid(y + float(port.get("y", 0))))
    for child in node.get("children", []):
        _collect_boxes(child, x, y, boxes, port_points)


def _collect_edges(raw: dict[str, Any], port_points: dict[str, tuple[int, int]]) -> list[LayoutEdge]:
    edges = []
    for edge in raw.get("edges", []):
        sections = edge.get("sections") or []
        if not sections:
            continue
        section = sections[0]
        points = [_point(section["startPoint"])]
        for bend in section.get("bendPoints", []):
            points.append(_point(bend))
        points.append(_point(section["endPoint"]))
        source = _node_id_from_port(edge["sources"][0])
        target = _node_id_from_port(edge["targets"][0])
        label = None
        label_box = None
        labels = edge.get("labels") or []
        if labels:
            raw_label = labels[0]
            label = raw_label.get("text")
            if "x" in raw_label and "y" in raw_label:
                label_box = LayoutBox(
                    _grid(raw_label["x"]),
                    _grid(raw_label["y"]),
                    _grid(raw_label.get("width", 44)),
                    _grid(raw_label.get("height", 14)),
                )
        edges.append(LayoutEdge(source=source, target=target, points=points, label=label, label_box=label_box))
    return edges


def _node_id_from_port(port_id: str) -> str:
    return port_id.split(":", 1)[0]


def _point(raw: dict[str, Any]) -> tuple[int, int]:
    return (_grid(raw["x"]), _grid(raw["y"]))


def _bounds_for(boxes: dict[str, LayoutBox], edges: list[LayoutEdge]) -> LayoutBox:
    xs: list[int] = []
    ys: list[int] = []
    for box in boxes.values():
        xs.extend([box.x, box.x + box.w])
        ys.extend([box.y, box.y + box.h])
    for edge in edges:
        for x, y in edge.points:
            xs.append(x)
            ys.append(y)
        if edge.label_box:
            xs.extend([edge.label_box.x, edge.label_box.x + edge.label_box.w])
            ys.extend([edge.label_box.y, edge.label_box.y + edge.label_box.h])
    if not xs or not ys:
        return LayoutBox(0, 0, 0, 0)
    return LayoutBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _fit_to_stage(
    boxes: dict[str, LayoutBox],
    edges: list[LayoutEdge],
    bounds: LayoutBox,
    width: int,
    height: int,
    allow_scale: bool = True,
) -> tuple[dict[str, LayoutBox], list[LayoutEdge], LayoutBox]:
    stage_left, stage_top = 72, 76
    stage_right, stage_bottom = width - 72, height - 56
    stage_w = stage_right - stage_left
    stage_h = stage_bottom - stage_top
    if allow_scale and (bounds.w > stage_w or bounds.h > stage_h):
        scale = min(stage_w / max(1, bounds.w), stage_h / max(1, bounds.h))
        scale = min(1.0, scale)
        boxes = {key: _scale_box(box, bounds, scale) for key, box in boxes.items()}
        edges = [_scale_edge(edge, bounds, scale) for edge in edges]
        bounds = _bounds_for(boxes, edges)
    target_x = (stage_left + stage_right) // 2
    target_y = (stage_top + stage_bottom) // 2
    current_x = bounds.x + bounds.w // 2
    current_y = bounds.y + bounds.h // 2
    dx = _grid(target_x - current_x)
    dy = _grid(target_y - current_y)
    shifted = _shift_box(bounds, dx, dy)
    if shifted.x < stage_left:
        dx += _grid(stage_left - shifted.x)
    if shifted.y < stage_top:
        dy += _grid(stage_top - shifted.y)
    if shifted.x + shifted.w > stage_right:
        dx -= _grid(shifted.x + shifted.w - stage_right)
    if shifted.y + shifted.h > stage_bottom:
        dy -= _grid(shifted.y + shifted.h - stage_bottom)
    if dx or dy:
        boxes = {key: _shift_box(box, dx, dy) for key, box in boxes.items()}
        edges = [_shift_edge(edge, dx, dy) for edge in edges]
        bounds = _shift_box(bounds, dx, dy)
    return boxes, edges, bounds


def _scale_box(box: LayoutBox, origin: LayoutBox, scale: float) -> LayoutBox:
    return LayoutBox(
        _grid((box.x - origin.x) * scale),
        _grid((box.y - origin.y) * scale),
        max(GRID, _grid(box.w * scale)),
        max(GRID, _grid(box.h * scale)),
    )


def _scale_edge(edge: LayoutEdge, origin: LayoutBox, scale: float) -> LayoutEdge:
    label_box = _scale_box(edge.label_box, origin, scale) if edge.label_box else None
    return LayoutEdge(
        source=edge.source,
        target=edge.target,
        points=[(_grid((x - origin.x) * scale), _grid((y - origin.y) * scale)) for x, y in edge.points],
        label=edge.label,
        label_box=label_box,
    )


def _shift_box(box: LayoutBox, dx: int, dy: int) -> LayoutBox:
    return LayoutBox(box.x + dx, box.y + dy, box.w, box.h)


def _shift_edge(edge: LayoutEdge, dx: int, dy: int) -> LayoutEdge:
    label_box = _shift_box(edge.label_box, dx, dy) if edge.label_box else None
    return LayoutEdge(
        source=edge.source,
        target=edge.target,
        points=[(x + dx, y + dy) for x, y in edge.points],
        label=edge.label,
        label_box=label_box,
    )


def validate_layout(result: LayoutResult, width: int, height: int) -> list[str]:
    issues: list[str] = []
    boxes = result.boxes
    items = list(boxes.items())
    for index, (left_id, left) in enumerate(items):
        if left.x < 0 or left.y < 0 or left.x + left.w > width or left.y + left.h > height:
            issues.append(f"{left_id} outside canvas")
        for right_id, right in items[index + 1:]:
            if _boxes_overlap(left, right, padding=8):
                issues.append(f"{left_id} overlaps {right_id}")
    for edge in result.edges:
        if len(edge.points) < 2:
            issues.append(f"{edge.source}->{edge.target} has no route")
            continue
        target_box = boxes.get(edge.target)
        if target_box and not _point_touches_box(edge.points[-1], target_box):
            issues.append(f"{edge.source}->{edge.target} arrow does not terminate on target")
        for node_id, box in boxes.items():
            if node_id in {edge.source, edge.target}:
                continue
            if _polyline_crosses_box(edge.points, box):
                issues.append(f"{edge.source}->{edge.target} crosses {node_id}")
        if edge.label_box:
            if edge.label_box.x < 0 or edge.label_box.y < 0 or edge.label_box.x + edge.label_box.w > width or edge.label_box.y + edge.label_box.h > height:
                issues.append(f"{edge.source}->{edge.target} label outside canvas")
            for node_id, box in boxes.items():
                if _boxes_overlap(edge.label_box, box, padding=2):
                    issues.append(f"{edge.source}->{edge.target} label overlaps {node_id}")

    edge_list = result.edges
    for i, left in enumerate(edge_list):
        for right in edge_list[i + 1:]:
            if {left.source, left.target} == {right.source, right.target}:
                continue
            if left.source in {right.source, right.target} or left.target in {right.source, right.target}:
                continue
            if _polylines_collinear_overlap(left.points, right.points):
                issues.append(f"{left.source}->{left.target} overlaps edge {right.source}->{right.target}")
    return issues


def _polylines_collinear_overlap(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> bool:
    left_segs = list(zip(left, left[1:]))
    right_segs = list(zip(right, right[1:]))
    for ls, le in left_segs:
        for rs, re in right_segs:
            if _segments_collinear_overlap(ls, le, rs, re):
                return True
    return False


def _segments_collinear_overlap(
    a1: tuple[int, int],
    a2: tuple[int, int],
    b1: tuple[int, int],
    b2: tuple[int, int],
) -> bool:
    if a1[0] == a2[0] and b1[0] == b2[0] and abs(a1[0] - b1[0]) < 8:
        lo = max(min(a1[1], a2[1]), min(b1[1], b2[1]))
        hi = min(max(a1[1], a2[1]), max(b1[1], b2[1]))
        return hi - lo > 8
    if a1[1] == a2[1] and b1[1] == b2[1] and abs(a1[1] - b1[1]) < 8:
        lo = max(min(a1[0], a2[0]), min(b1[0], b2[0]))
        hi = min(max(a1[0], a2[0]), max(b1[0], b2[0]))
        return hi - lo > 8
    return False


def _boxes_overlap(left: LayoutBox, right: LayoutBox, padding: int = 0) -> bool:
    return not (
        left.x + left.w + padding <= right.x
        or right.x + right.w + padding <= left.x
        or left.y + left.h + padding <= right.y
        or right.y + right.h + padding <= left.y
    )


def _point_touches_box(point: tuple[int, int], box: LayoutBox) -> bool:
    x, y = point
    return box.x - 6 <= x <= box.x + box.w + 6 and box.y - 6 <= y <= box.y + box.h + 6


def _polyline_crosses_box(points: list[tuple[int, int]], box: LayoutBox) -> bool:
    padded = LayoutBox(box.x - 4, box.y - 4, box.w + 8, box.h + 8)
    for start, end in zip(points, points[1:]):
        if start[0] == end[0]:
            x = start[0]
            y1, y2 = sorted([start[1], end[1]])
            if padded.x < x < padded.x + padded.w and y1 < padded.y + padded.h and y2 > padded.y:
                return True
        elif start[1] == end[1]:
            y = start[1]
            x1, x2 = sorted([start[0], end[0]])
            if padded.y < y < padded.y + padded.h and x1 < padded.x + padded.w and x2 > padded.x:
                return True
    return False


def _grid(value: float | int) -> int:
    return int(round(float(value) / GRID) * GRID)


if __name__ == "__main__":
    if not elk_available():
        print("ERROR: ELK unavailable", file=sys.stderr)
        raise SystemExit(1)
    print("OK: ELK available")
