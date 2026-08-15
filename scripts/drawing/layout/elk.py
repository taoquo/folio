from __future__ import annotations

import json
import shutil
import subprocess
from collections import defaultdict
from dataclasses import replace
from math import cos, pi, sin
from pathlib import Path
from typing import Any

from ..connectors import route_orthogonal
from ..connectors.labels import place_edge_labels
from ..grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from ..models import DrawingPlan, VisualEdgePlan
from ..semantics.models import SemanticDiagram
from ..validation.layout import validate_layout
from .constraints import compile_layout_constraints
from .models import LayoutBox, LayoutConstraintSet, LayoutEdge, LayoutResult, PortPreference


ROOT = Path(__file__).resolve().parents[3]
ELK_RUNNER = ROOT / "scripts" / "diagram_elk_runner.js"
ELK_BUNDLED = ROOT / "scripts" / "vendor" / "elk.bundled.js"
GRID = 4
FAN_GAP = 12


def layout_drawing(
    drawing: DrawingPlan,
    semantic: SemanticDiagram | None = None,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> LayoutResult:
    """Lay out a DrawingPlan without converting it back to the legacy diagram spec."""
    del semantic  # Semantics have already been resolved into DrawingPlan constraints.
    constraints = compile_layout_constraints(drawing, grammar)
    _require_elk()
    seed_boxes = _elk_seed_layout(drawing, constraints)
    boxes = _compose(drawing, constraints, seed_boxes)
    edges = _route_edges(drawing, constraints, boxes)
    bounds = _bounds_for(boxes, edges)
    result = LayoutResult(boxes=boxes, edges=edges, bounds=bounds)
    issues = validate_layout(result, drawing.width, drawing.height)
    if issues:
        result = LayoutResult(boxes=boxes, edges=edges, bounds=bounds, warnings=issues)
    return result


def _require_elk() -> None:
    if shutil.which("node") is None or not ELK_RUNNER.exists() or not ELK_BUNDLED.exists():
        raise RuntimeError("ELK layout unavailable: require node and scripts/vendor/elk.bundled.js")


def _elk_seed_layout(drawing: DrawingPlan, constraints: LayoutConstraintSet) -> dict[str, LayoutBox]:
    """Ask ELK for topology-aware ordering; Folio composition then snaps it to its grammar."""
    direction = "RIGHT" if constraints.axis == "left-right" else "DOWN"
    ordered_ids = _ordered_node_ids(drawing, constraints)
    graph: dict[str, Any] = {
        "id": "root",
        "layoutOptions": {
            "elk.algorithm": "layered",
            "elk.direction": direction,
            "elk.edgeRouting": "ORTHOGONAL",
            "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
            "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
            "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
            "elk.layered.spacing.nodeNodeBetweenLayers": str(constraints.layer_gap),
            "elk.spacing.nodeNode": str(constraints.node_gap),
            "elk.spacing.edgeNode": str(constraints.edge_node_gap),
            "elk.spacing.edgeEdge": str(constraints.edge_edge_gap),
            "elk.padding": "[top=80,left=96,bottom=72,right=96]",
        },
        "children": [
            {
                "id": node_id,
                "width": constraints.node_sizes[node_id][0],
                "height": constraints.node_sizes[node_id][1],
            }
            for node_id in ordered_ids
        ],
        "edges": [
            {
                "id": edge.id,
                "sources": [edge.source],
                "targets": [edge.target],
                "layoutOptions": {
                    "elk.layered.priority.straightness": "20"
                    if (edge.source, edge.target) in constraints.preferred_adjacency
                    else "1"
                },
            }
            for edge in drawing.edges
        ],
    }
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
    raw = json.loads(result.stdout)
    return {
        item["id"]: LayoutBox(
            _grid(item.get("x", 0)),
            _grid(item.get("y", 0)),
            _grid(item.get("width", constraints.node_sizes[item["id"]][0])),
            _grid(item.get("height", constraints.node_sizes[item["id"]][1])),
        )
        for item in raw.get("children", [])
    }


def _ordered_node_ids(drawing: DrawingPlan, constraints: LayoutConstraintSet) -> list[str]:
    known = {node.id for node in drawing.nodes}
    ordered: list[str] = []

    def add(node_id: str) -> None:
        if node_id in known and node_id not in ordered:
            ordered.append(node_id)

    for node_id in constraints.spine:
        add(node_id)
        for sidecar in constraints.sidecars.get(node_id, ()):
            add(sidecar)
    for layer_id in constraints.layer_order:
        for node_id in constraints.node_order.get(layer_id, ()):
            add(node_id)
    for node in drawing.nodes:
        add(node.id)
    return ordered


def _compose(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
) -> dict[str, LayoutBox]:
    if drawing.composition.pattern == "pipeline":
        return _pipeline_boxes(drawing, constraints, seed)
    if drawing.composition.pattern == "hub":
        return _hub_boxes(drawing, constraints, seed)
    return _layered_boxes(drawing, constraints, seed)


def _layered_boxes(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
) -> dict[str, LayoutBox]:
    rows: list[tuple[str, list[str]]] = []
    assigned: set[str] = set()
    for layer_id in constraints.layer_order:
        members = [node_id for node_id in constraints.node_order.get(layer_id, ()) if node_id in seed]
        if members:
            rows.append((layer_id, members))
            assigned.update(members)
    remainder = [node.id for node in drawing.nodes if node.id not in assigned]
    if remainder:
        rows.append(("unlayered", remainder))
    if not rows:
        rows = [("default", [node.id for node in drawing.nodes])]

    top, bottom, left, right = 92, drawing.height - 64, 72, drawing.width - 72
    row_step = 0 if len(rows) == 1 else (bottom - top - 72) / (len(rows) - 1)
    boxes: dict[str, LayoutBox] = {}
    for row_index, (_layer, members) in enumerate(rows):
        requested = list(members)
        requested_rank = {node_id: index for index, node_id in enumerate(requested)}
        ordered = sorted(
            members,
            key=lambda node_id: (
                requested_rank.get(node_id, 10_000),
                seed.get(node_id, LayoutBox(0, 0, 0, 0)).x,
                node_id,
            ),
        )
        widths = [constraints.node_sizes[node_id][0] for node_id in ordered]
        available = right - left
        gap = constraints.node_gap
        if len(ordered) > 1:
            gap = min(gap, max(16, (available - sum(widths)) // (len(ordered) - 1)))
        total = sum(widths) + max(0, len(ordered) - 1) * gap
        x = _grid(left + max(0, (available - total) / 2))
        y = _grid(top + row_index * row_step)
        for node_id, node_w in zip(ordered, widths):
            node_h = constraints.node_sizes[node_id][1]
            boxes[node_id] = LayoutBox(x, y, node_w, node_h)
            x = _grid(x + node_w + gap)
    return _align_secondary_rows(drawing, boxes, left, right)


def _align_secondary_rows(
    drawing: DrawingPlan,
    boxes: dict[str, LayoutBox],
    left: int,
    right: int,
) -> dict[str, LayoutBox]:
    result = dict(boxes)
    regions = {node.id: node.region for node in drawing.nodes}
    members: dict[str | None, list[str]] = defaultdict(list)
    for node in drawing.nodes:
        members[node.region].append(node.id)
    spine_pairs = set(zip(drawing.composition.spine, drawing.composition.spine[1:]))
    for edge in drawing.edges:
        if (edge.source, edge.target) in spine_pairs or regions.get(edge.source) == regions.get(edge.target):
            continue
        source_region = regions.get(edge.source)
        target_region = regions.get(edge.target)
        source_members = members[source_region]
        target_members = members[target_region]
        movable_region = source_region if len(source_members) <= len(target_members) else target_region
        movable_id = edge.source if movable_region == source_region else edge.target
        fixed_id = edge.target if movable_id == edge.source else edge.source
        dx = result[fixed_id].x - result[movable_id].x
        shifted = [
            LayoutBox(result[node_id].x + dx, result[node_id].y, result[node_id].w, result[node_id].h)
            for node_id in members[movable_region]
        ]
        if shifted and min(box.x for box in shifted) >= left and max(box.x + box.w for box in shifted) <= right:
            for node_id, box in zip(members[movable_region], shifted):
                result[node_id] = box
    return result


def _pipeline_boxes(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
) -> dict[str, LayoutBox]:
    ordered = list(constraints.spine) or _ordered_node_ids(drawing, constraints)
    ordered = [node_id for node_id in ordered if node_id in seed]
    remainder = [node_id for node_id in _ordered_node_ids(drawing, constraints) if node_id not in ordered]
    left, right = 64, drawing.width - 64
    boxes: dict[str, LayoutBox] = {}
    pipeline_nodes = [*ordered, *remainder]
    chunks = [pipeline_nodes[index:index + 4] for index in range(0, len(pipeline_nodes), 4)] or [[]]
    first_y = _grid(drawing.height * (0.34 if len(chunks) > 1 else 0.42))
    for row_index, chunk in enumerate(chunks):
        widths = [constraints.node_sizes[node_id][0] for node_id in chunk]
        gap = constraints.node_gap
        if len(chunk) > 1:
            gap = min(gap, max(12, (right - left - sum(widths)) // (len(chunk) - 1)))
        total = sum(widths) + max(0, len(chunk) - 1) * gap
        x = _grid(left + max(0, (right - left - total) / 2))
        y = _grid(first_y + row_index * 148)
        row = chunk if row_index % 2 == 0 else list(reversed(chunk))
        for node_id in row:
            w, h = constraints.node_sizes[node_id]
            boxes[node_id] = LayoutBox(x, y, w, h)
            x = _grid(x + w + gap)

    return boxes


def _hub_boxes(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    seed: dict[str, LayoutBox],
) -> dict[str, LayoutBox]:
    focus = drawing.hierarchy.focus_node or (constraints.spine[0] if constraints.spine else None)
    if focus not in seed:
        focus = _ordered_node_ids(drawing, constraints)[0]
    focus_w, focus_h = constraints.node_sizes[focus]
    center_x = _grid(drawing.width / 2)
    center_y = _grid(drawing.height / 2 + 16)
    boxes = {focus: LayoutBox(_grid(center_x - focus_w / 2), _grid(center_y - focus_h / 2), focus_w, focus_h)}
    satellites = [node_id for node_id in _ordered_node_ids(drawing, constraints) if node_id != focus]
    radius_x = min(320, max(220, drawing.width // 3))
    radius_y = min(176, max(132, drawing.height // 3))
    for index, node_id in enumerate(satellites):
        angle = -pi / 2 + (2 * pi * index / max(1, len(satellites)))
        w, h = constraints.node_sizes[node_id]
        x = _grid(center_x + radius_x * cos(angle) - w / 2)
        y = _grid(center_y + radius_y * sin(angle) - h / 2)
        boxes[node_id] = LayoutBox(x, y, w, h)
    return boxes


def _route_edges(
    drawing: DrawingPlan,
    constraints: LayoutConstraintSet,
    boxes: dict[str, LayoutBox],
) -> list[LayoutEdge]:
    preferences = {
        edge.id: _spatial_preference(
            edge,
            constraints.port_preferences[edge.id],
            boxes,
            preserve_layers=drawing.composition.pattern == "layered",
        )
        for edge in drawing.edges
    }
    incidents: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for edge in drawing.edges:
        preference = preferences[edge.id]
        incidents[(edge.source, preference.source)].append((edge.id, "source"))
        incidents[(edge.target, preference.target)].append((edge.id, "target"))
    vertical_edges = [
        edge.id
        for edge in drawing.edges
        if preferences[edge.id].source in {"top", "bottom"}
        and preferences[edge.id].target in {"top", "bottom"}
    ]
    lane_offsets = {
        edge_id: _grid((index - (len(vertical_edges) - 1) / 2) * FAN_GAP)
        for index, edge_id in enumerate(vertical_edges)
    }
    anchors: dict[tuple[str, str], tuple[int, int]] = {}
    for (node_id, side), entries in incidents.items():
        for index, (edge_id, endpoint) in enumerate(sorted(entries)):
            anchors[(edge_id, endpoint)] = _fan_anchor(boxes[node_id], side, index, len(entries))

    results: list[LayoutEdge] = []
    for edge in drawing.edges:
        start = anchors[(edge.id, "source")]
        end = anchors[(edge.id, "target")]
        preference = preferences[edge.id]
        start_stub = _outward_stub(start, preference.source, constraints.edge_node_gap // 2)
        end_stub = _outward_stub(end, preference.target, constraints.edge_node_gap // 2)
        middle = _preferred_middle_route(start_stub, end_stub, preference, lane_offsets.get(edge.id, 0))
        if _route_crosses_nodes(middle, boxes, {edge.source, edge.target}):
            middle = route_orthogonal(
                start_stub,
                end_stub,
                boxes,
                set(),
                drawing.width,
                drawing.height,
                clearance=constraints.edge_node_gap,
            )
        points = _simplify_points([start, *middle, end])
        label = _compact_edge_label(edge.label)
        results.append(LayoutEdge(edge.source, edge.target, points, label, None, edge.id))
    placed = place_edge_labels(results, list(boxes.values()), drawing.width, drawing.height)
    return [edge if edge.label_box else replace(edge, label=None) for edge in placed]


def _outward_stub(point: tuple[int, int], side: str, distance: int) -> tuple[int, int]:
    x, y = point
    return {
        "top": (x, y - distance),
        "right": (x + distance, y),
        "bottom": (x, y + distance),
        "left": (x - distance, y),
    }[side]


def _preferred_middle_route(
    start: tuple[int, int],
    end: tuple[int, int],
    preference: PortPreference,
    lane_offset: int,
) -> list[tuple[int, int]]:
    if start[0] == end[0] or start[1] == end[1]:
        return [start, end]
    vertical = {preference.source, preference.target} <= {"top", "bottom"}
    horizontal = {preference.source, preference.target} <= {"left", "right"}
    if vertical:
        middle = _grid((start[1] + end[1]) / 2 + lane_offset)
        return [start, (start[0], middle), (end[0], middle), end]
    if horizontal:
        middle = _grid((start[0] + end[0]) / 2)
        return [start, (middle, start[1]), (middle, end[1]), end]
    return [start, (end[0], start[1]), end]


def _route_crosses_nodes(
    points: list[tuple[int, int]],
    boxes: dict[str, LayoutBox],
    allowed: set[str],
) -> bool:
    return any(
        node_id not in allowed
        and any(_segment_crosses_box(start, end, box) for start, end in zip(points, points[1:]))
        for node_id, box in boxes.items()
    )


def _segment_crosses_box(start: tuple[int, int], end: tuple[int, int], box: LayoutBox) -> bool:
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        return box.x < start[0] < box.x + box.w and low < box.y + box.h and high > box.y
    if start[1] == end[1]:
        low, high = sorted((start[0], end[0]))
        return box.y < start[1] < box.y + box.h and low < box.x + box.w and high > box.x
    return False


def _simplify_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for point in points:
        if result and point == result[-1]:
            continue
        result.append(point)
        while len(result) >= 3:
            a, b, c = result[-3:]
            if a[0] == b[0] == c[0] or a[1] == b[1] == c[1]:
                result.pop(-2)
            else:
                break
    return result


def _spatial_preference(
    edge: VisualEdgePlan,
    default: PortPreference,
    boxes: dict[str, LayoutBox],
    preserve_layers: bool,
) -> PortPreference:
    source = boxes[edge.source]
    target = boxes[edge.target]
    dx = (target.x + target.w / 2) - (source.x + source.w / 2)
    dy = (target.y + target.h / 2) - (source.y + source.h / 2)
    if source.y + source.h <= target.y or target.y + target.h <= source.y:
        return PortPreference("bottom", "top") if dy >= 0 else PortPreference("top", "bottom")
    if preserve_layers and default.source in {"top", "bottom"} and default.target in {"top", "bottom"}:
        return PortPreference("bottom", "top") if dy >= 0 else PortPreference("top", "bottom")
    if abs(dx) > abs(dy) * 1.2:
        return PortPreference("right", "left") if dx >= 0 else PortPreference("left", "right")
    if abs(dy) > abs(dx) * 1.2:
        return PortPreference("bottom", "top") if dy >= 0 else PortPreference("top", "bottom")
    return default


def _fan_anchor(box: LayoutBox, side: str, index: int, count: int) -> tuple[int, int]:
    horizontal = side in {"top", "bottom"}
    length = box.w if horizontal else box.h
    if count == 1:
        offset = length / 2
    else:
        span = min(length - 24, max(FAN_GAP * (count - 1), length * 0.6))
        offset = (length - span) / 2 + index * span / (count - 1)
    offset = _grid(offset)
    if side == "top":
        return (_grid(box.x + offset), box.y)
    if side == "right":
        return (box.x + box.w, _grid(box.y + offset))
    if side == "bottom":
        return (_grid(box.x + offset), box.y + box.h)
    return (box.x, _grid(box.y + offset))


def _compact_edge_label(label: str | None) -> str | None:
    if not label:
        return None
    compact = " ".join(label.split()).upper()
    return compact if len(compact) <= 14 else None


def _bounds_for(boxes: dict[str, LayoutBox], edges: list[LayoutEdge]) -> LayoutBox:
    xs: list[int] = []
    ys: list[int] = []
    for box in boxes.values():
        xs.extend((box.x, box.x + box.w))
        ys.extend((box.y, box.y + box.h))
    for edge in edges:
        for x, y in edge.points:
            xs.append(x)
            ys.append(y)
        if edge.label_box:
            xs.extend((edge.label_box.x, edge.label_box.x + edge.label_box.w))
            ys.extend((edge.label_box.y, edge.label_box.y + edge.label_box.h))
    if not xs:
        return LayoutBox(0, 0, 0, 0)
    return LayoutBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _grid(value: float | int) -> int:
    return int(round(float(value) / GRID) * GRID)
