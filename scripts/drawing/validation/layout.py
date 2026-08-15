from __future__ import annotations

from ..layout.models import LayoutBox, LayoutResult


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
        target = boxes.get(edge.target)
        if target and not _point_touches_box(edge.points[-1], target):
            issues.append(f"{edge.source}->{edge.target} arrow does not terminate on target")
        for node_id, box in boxes.items():
            if node_id not in {edge.source, edge.target} and _polyline_crosses_box(edge.points, box):
                issues.append(f"{edge.source}->{edge.target} crosses {node_id}")
        if edge.label_box:
            label = edge.label_box
            if label.x < 0 or label.y < 0 or label.x + label.w > width or label.y + label.h > height:
                issues.append(f"{edge.source}->{edge.target} label outside canvas")
            for node_id, box in boxes.items():
                if _boxes_overlap(label, box, padding=2):
                    issues.append(f"{edge.source}->{edge.target} label overlaps {node_id}")
    for index, left in enumerate(result.edges):
        for right in result.edges[index + 1:]:
            if left.source in {right.source, right.target} or left.target in {right.source, right.target}:
                continue
            if _polylines_collinear_overlap(left.points, right.points):
                issues.append(f"{left.source}->{left.target} overlaps edge {right.source}->{right.target}")
    return issues


def _boxes_overlap(left: LayoutBox, right: LayoutBox, padding: int = 0) -> bool:
    return not (
        left.x + left.w + padding <= right.x
        or right.x + right.w + padding <= left.x
        or left.y + left.h + padding <= right.y
        or right.y + right.h + padding <= left.y
    )


def _point_touches_box(point: tuple[int, int], box: LayoutBox) -> bool:
    x, y = point
    vertical = x in {box.x, box.x + box.w} and box.y <= y <= box.y + box.h
    horizontal = y in {box.y, box.y + box.h} and box.x <= x <= box.x + box.w
    return vertical or horizontal


def _polyline_crosses_box(points: list[tuple[int, int]], box: LayoutBox) -> bool:
    padded = LayoutBox(box.x - 4, box.y - 4, box.w + 8, box.h + 8)
    for start, end in zip(points, points[1:]):
        if start[0] == end[0]:
            low, high = sorted((start[1], end[1]))
            if padded.x < start[0] < padded.x + padded.w and low < padded.y + padded.h and high > padded.y:
                return True
        elif start[1] == end[1]:
            low, high = sorted((start[0], end[0]))
            if padded.y < start[1] < padded.y + padded.h and low < padded.x + padded.w and high > padded.x:
                return True
    return False


def _polylines_collinear_overlap(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> bool:
    return any(
        _segments_collinear_overlap(a, b, c, d)
        for a, b in zip(left, left[1:])
        for c, d in zip(right, right[1:])
    )


def _segments_collinear_overlap(
    a1: tuple[int, int], a2: tuple[int, int], b1: tuple[int, int], b2: tuple[int, int]
) -> bool:
    if a1[0] == a2[0] and b1[0] == b2[0] and abs(a1[0] - b1[0]) < 8:
        return min(max(a1[1], a2[1]), max(b1[1], b2[1])) - max(min(a1[1], a2[1]), min(b1[1], b2[1])) > 8
    if a1[1] == a2[1] and b1[1] == b2[1] and abs(a1[1] - b1[1]) < 8:
        return min(max(a1[0], a2[0]), max(b1[0], b2[0])) - max(min(a1[0], a2[0]), min(b1[0], b2[0])) > 8
    return False
