from __future__ import annotations

from ..scene import ResolvedScene, SceneBox
from ..typography.measure import measure_text
from .models import DrawingDiagnostic


def _overlap(left: SceneBox, right: SceneBox) -> bool:
    return not (left.x + left.w <= right.x or right.x + right.w <= left.x or left.y + left.h <= right.y or right.y + right.h <= left.y)


def _spacing(left: SceneBox, right: SceneBox) -> int | None:
    vertical_overlap = min(left.y + left.h, right.y + right.h) > max(left.y, right.y)
    horizontal_overlap = min(left.x + left.w, right.x + right.w) > max(left.x, right.x)
    if vertical_overlap:
        return max(right.x - (left.x + left.w), left.x - (right.x + right.w))
    if horizontal_overlap:
        return max(right.y - (left.y + left.h), left.y - (right.y + right.h))
    return None


def _on_edge(point: tuple[int, int], box: SceneBox) -> bool:
    x, y = point
    vertical = x in {box.x, box.x + box.w} and box.y <= y <= box.y + box.h
    horizontal = y in {box.y, box.y + box.h} and box.x <= x <= box.x + box.w
    return vertical or horizontal


def _segment_crosses_box(start: tuple[int, int], end: tuple[int, int], box: SceneBox) -> bool:
    if start[0] == end[0]:
        x = start[0]
        low, high = sorted((start[1], end[1]))
        return box.x < x < box.x + box.w and low < box.y + box.h and high > box.y
    if start[1] == end[1]:
        y = start[1]
        low, high = sorted((start[0], end[0]))
        return box.y < y < box.y + box.h and low < box.x + box.w and high > box.x
    return False


def _segments_overlap(
    a: tuple[int, int], b: tuple[int, int], c: tuple[int, int], d: tuple[int, int]
) -> bool:
    if a[1] == b[1] == c[1] == d[1]:
        return min(max(a[0], b[0]), max(c[0], d[0])) > max(min(a[0], b[0]), min(c[0], d[0]))
    if a[0] == b[0] == c[0] == d[0]:
        return min(max(a[1], b[1]), max(c[1], d[1])) > max(min(a[1], b[1]), min(c[1], d[1]))
    return False


def _box_segment_distance(box: SceneBox, start: tuple[int, int], end: tuple[int, int]) -> int:
    if start[1] == end[1]:
        low, high = sorted((start[0], end[0]))
        return max(box.x - high, low - (box.x + box.w), 0) + max(box.y - start[1], start[1] - (box.y + box.h), 0)
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        return max(box.x - start[0], start[0] - (box.x + box.w), 0) + max(box.y - high, low - (box.y + box.h), 0)
    return 0


def validate_scene_geometry(
    scene: ResolvedScene,
    grid: int | object = 4,
) -> list[DrawingDiagnostic]:
    if not isinstance(grid, int):
        grid = int(getattr(getattr(grid, "geometry", None), "grid", 4))
    if grid <= 0:
        raise ValueError("scene validation grid must be positive")
    diagnostics: list[DrawingDiagnostic] = []
    boxes = {node.id: node.box for node in scene.nodes}
    nodes = list(scene.nodes)
    for index, node in enumerate(nodes):
        box = node.box
        if box.x < 0 or box.y < 0 or box.x + box.w > scene.width or box.y + box.h > scene.height:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG100", "node outside canvas", node.id))
        if any(value % grid for value in (box.x, box.y, box.w, box.h)):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG101", "node geometry is off the 4-unit grid", node.id))
        for other in nodes[index + 1:]:
            if _overlap(box, other.box):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG102", f"node overlaps {other.id}", node.id))
            else:
                spacing = _spacing(box, other.box)
                if spacing is not None and spacing < 12:
                    diagnostics.append(DrawingDiagnostic("WARNING", "DG117", f"node spacing to {other.id} is under 12 units", node.id))
        for text in node.text_runs:
            if not (box.x <= text.x <= box.x + box.w and box.y <= text.y <= box.y + box.h):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG108", "text baseline is outside node", node.id))
                continue
            text_width = measure_text(text.text, text.size, text.family)
            left = text.x - text_width / 2 if text.anchor == "middle" else text.x
            if left < box.x or left + text_width > box.x + box.w:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG111", "text width exceeds node bounds", node.id))
    for edge in scene.edges:
        source, target = boxes.get(edge.source), boxes.get(edge.target)
        if source and not _on_edge(edge.points[0], source):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG103", "edge source endpoint is detached", edge.id))
        if target and not _on_edge(edge.points[-1], target):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG104", "edge target endpoint is detached", edge.id))
        if len(edge.points) < 2 or all(point == edge.points[0] for point in edge.points[1:]):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG105", "zero-length edge", edge.id))
        if any(value % grid for point in edge.points for value in point):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG120", "connector geometry is off the 4-unit grid", edge.id))
        if any(start[0] != end[0] and start[1] != end[1] for start, end in zip(edge.points, edge.points[1:])):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG113", "connector contains a non-orthogonal segment", edge.id))
        for node_id, box in boxes.items():
            if node_id in {edge.source, edge.target}:
                continue
            if any(_segment_crosses_box(start, end, box) for start, end in zip(edge.points, edge.points[1:])):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG109", f"edge crosses unrelated node {node_id}", edge.id))
        if len(edge.arrow.points) != 3:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG110", "arrowhead requires exactly three points", edge.id))
        else:
            tip = edge.arrow.points[1]
            if not (0 <= tip[0] <= scene.width and 0 <= tip[1] <= scene.height):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG110", "arrowhead outside canvas", edge.id))
        if edge.label_box and (
            edge.label_box.x < 8
            or edge.label_box.y < 8
            or edge.label_box.x + edge.label_box.w > scene.width - 8
            or edge.label_box.y + edge.label_box.h > scene.height - 8
        ):
            diagnostics.append(DrawingDiagnostic("WARNING", "DG114", "edge label is near the canvas boundary", edge.id))
        if edge.label_box and any(value % grid for value in (edge.label_box.x, edge.label_box.y, edge.label_box.w, edge.label_box.h)):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG121", "edge label geometry is off the 4-unit grid", edge.id))
        if edge.label and not edge.label_box:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG132", "edge label has no collision-free placement", edge.id))
        if edge.label_box:
            if any(_overlap(edge.label_box, box) for box in boxes.values()):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG133", "edge label overlaps a node", edge.id))
            other_segments = [
                segment
                for candidate in scene.edges
                if candidate.id != edge.id
                for segment in zip(candidate.points, candidate.points[1:])
            ]
            own_distances = [
                _box_segment_distance(edge.label_box, start, end)
                for start, end in zip(edge.points, edge.points[1:])
            ]
            if (own_distances and min(own_distances) < 8) or any(
                _box_segment_distance(edge.label_box, start, end) < 8 for start, end in other_segments
            ):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG134", "edge label is less than 8 units from a connector", edge.id))
    for index, edge in enumerate(scene.edges):
        if edge.label_box:
            for other in scene.edges[index + 1:]:
                if other.label_box and _overlap(edge.label_box, other.label_box):
                    diagnostics.append(DrawingDiagnostic("ERROR", "DG135", f"edge label overlaps label {other.id}", edge.id))
        for other in scene.edges[index + 1:]:
            if any(
                _segments_overlap(a, b, c, d)
                for a, b in zip(edge.points, edge.points[1:])
                for c, d in zip(other.points, other.points[1:])
            ):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG112", f"connector overlaps {other.id}", edge.id))
    attach_points: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for edge in scene.edges:
        for node_id, point in ((edge.source, edge.points[0]), (edge.target, edge.points[-1])):
            box = boxes.get(node_id)
            if box is None:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG129", "edge endpoint references missing scene node", edge.id))
                continue
            side = "left" if point[0] == box.x else "right" if point[0] == box.x + box.w else "top" if point[1] == box.y else "bottom"
            attach_points.setdefault((node_id, side), []).append(point)
    for (node_id, _side), points in attach_points.items():
        ordered = sorted(set(points))
        if len(ordered) != len(points):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG115", "connectors share an attach point", node_id))
            continue
        if any(abs(a[0] - b[0]) + abs(a[1] - b[1]) < 12 for a, b in zip(ordered, ordered[1:])):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG116", "connector attach points are less than 12 units apart", node_id))
    for region in scene.regions:
        if region.box and (region.box.x < 0 or region.box.y < 0 or region.box.x + region.box.w > scene.width or region.box.y + region.box.h > scene.height):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG106", "region outside canvas", region.id))
        if region.box and any(value % grid for value in (region.box.x, region.box.y, region.box.w, region.box.h)):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG107", "region geometry is off the 4-unit grid", region.id))
    for annotation in scene.annotations:
        if any(value % grid for value in (annotation.box.x, annotation.box.y, annotation.box.w, annotation.box.h)):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG123", "annotation geometry is off the 4-unit grid", annotation.id))
        if annotation.box.x < 0 or annotation.box.y < 0 or annotation.box.x + annotation.box.w > scene.width or annotation.box.y + annotation.box.h > scene.height:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG124", "annotation outside canvas", annotation.id))
        if any(value % grid for point in annotation.leader for value in point):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG125", "annotation leader is off the 4-unit grid", annotation.id))
        for node_id, box in boxes.items():
            if _overlap(annotation.box, box):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG126", f"annotation overlaps node {node_id}", annotation.id))
        if scene.legend and _overlap(annotation.box, scene.legend.box):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG127", "annotation overlaps legend", annotation.id))
    for index, annotation in enumerate(scene.annotations):
        for other in scene.annotations[index + 1:]:
            if _overlap(annotation.box, other.box):
                diagnostics.append(DrawingDiagnostic("ERROR", "DG128", f"annotation overlaps {other.id}", annotation.id))
    texts = [scene.title, *(annotation.text for annotation in scene.annotations)]
    texts.extend(region.label for region in scene.regions)
    texts.extend(text for node in scene.nodes for text in node.text_runs)
    texts.extend(edge.label for edge in scene.edges if edge.label)
    if scene.legend:
        texts.extend([scene.legend.title, *(item.label for item in scene.legend.items)])
        if any(value % grid for value in (scene.legend.box.x, scene.legend.box.y, scene.legend.box.w, scene.legend.box.h)):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG122", "legend geometry is off the 4-unit grid", "legend"))
        if (
            scene.legend.box.x < 0
            or scene.legend.box.y < 0
            or scene.legend.box.x + scene.legend.box.w > scene.width
            or scene.legend.box.y + scene.legend.box.h > scene.height
        ):
            diagnostics.append(DrawingDiagnostic("ERROR", "DG130", "legend outside canvas", "legend"))
        for item in scene.legend.items:
            text_width = measure_text(item.label.text, item.label.size, item.label.family)
            if item.label.x < scene.legend.box.x or item.label.x + text_width > scene.legend.box.x + scene.legend.box.w:
                diagnostics.append(DrawingDiagnostic("ERROR", "DG131", "legend item text exceeds legend bounds", item.label.text))
    for text in texts:
        if text.x % grid or text.y % grid:
            diagnostics.append(DrawingDiagnostic("ERROR", "DG119", "text anchor is off the 4-unit grid", text.text))
    return diagnostics
