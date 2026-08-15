from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from diagram_models import ArchitectureDiagramSpec, DiagramSpec, UmlClassDiagramSpec
from drawing.grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR
from drawing.layout.models import LayoutBox, LayoutEdge, LayoutResult
from drawing.validation.layout import validate_layout


ROOT = Path(__file__).resolve().parents[1]
ELK_RUNNER = ROOT / "scripts" / "diagram_elk_runner.js"
ELK_BUNDLED = ROOT / "scripts" / "vendor" / "elk.bundled.js"
_ARCH_GRAMMAR = DEFAULT_ARCHITECTURE_GRAMMAR.geometry
GRID = _ARCH_GRAMMAR.grid


def elk_available() -> bool:
    return shutil.which("node") is not None and ELK_RUNNER.exists() and ELK_BUNDLED.exists()


def layout_diagram(spec: DiagramSpec) -> LayoutResult:
    if getattr(spec, "kind", None) == "architecture":
        return layout_architecture(spec)
    if getattr(spec, "kind", None) == "uml-class":
        return layout_uml_class(spec)
    raise TypeError(f"unsupported spec type: {type(spec)!r}")


def layout_architecture(spec: ArchitectureDiagramSpec) -> LayoutResult:
    from drawing.pipeline import drawing_plan_from_spec
    from drawing.layout.elk import layout_drawing

    return layout_drawing(drawing_plan_from_spec(spec))


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


def _edge_labels(label: str | None) -> list[dict[str, Any]]:
    if not label:
        return []
    return [{"text": label, "width": max(44, len(label) * 7 + 14), "height": 14}]


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


def _legacy_validate_layout(result: LayoutResult, width: int, height: int) -> list[str]:
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
