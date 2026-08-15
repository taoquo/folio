from __future__ import annotations

from dataclasses import replace

from ..layout.models import LayoutBox, LayoutEdge
from ..theme.folio import DEFAULT_FOLIO_THEME
from ..typography.measure import measure_text


LABEL_GAP = 8
LABEL_HEIGHT = 16
CANVAS_MARGIN = 8
NODE_CLEARANCE = 4
PERPENDICULAR_OFFSETS = (LABEL_GAP, 24, 40, 56, 72)
# Sliding the label along its own segment keeps it attached to the connector it names. Without
# this the placer falls back to a distant stub segment as soon as the midpoint is blocked.
ALONG_FRACTIONS = (0.5, 0.38, 0.62, 0.26, 0.74)


def place_edge_labels(
    edges: list[LayoutEdge],
    node_boxes: list[LayoutBox],
    width: int,
    height: int,
    obstacles: tuple[LayoutBox, ...] = (),
) -> list[LayoutEdge]:
    """Place connector labels beside segments without using an opaque line mask."""
    segments = [segment for edge in edges for segment in zip(edge.points, edge.points[1:])]
    occupied: list[LayoutBox] = list(obstacles)
    result: list[LayoutEdge] = []
    for edge in edges:
        if not edge.label:
            result.append(edge)
            continue
        box = _label_box(edge.label, edge.points, node_boxes, occupied, segments, width, height)
        result.append(replace(edge, label_box=box))
        if box:
            occupied.append(box)
    return result


def _label_box(
    label: str,
    points: list[tuple[int, int]],
    node_boxes: list[LayoutBox],
    occupied: list[LayoutBox],
    segments: list[tuple[tuple[int, int], tuple[int, int]]],
    width: int,
    height: int,
) -> LayoutBox | None:
    label_width = _grid_width(max(32, min(160, measure_text(label, 8, DEFAULT_FOLIO_THEME.mono) + 8)))
    ranked = sorted(
        zip(points, points[1:]),
        key=lambda pair: (-(abs(pair[1][0] - pair[0][0]) + abs(pair[1][1] - pair[0][1])), pair),
    )
    candidates: list[LayoutBox] = []
    for start, end in ranked:
        if start[1] == end[1]:
            low, high = sorted((start[0], end[0]))
            for fraction in ALONG_FRACTIONS:
                center = _grid(low + (high - low) * fraction)
                if center - label_width // 2 < low - label_width or center + label_width // 2 > high + label_width:
                    continue
                for offset in PERPENDICULAR_OFFSETS:
                    candidates.extend((
                        LayoutBox(center - label_width // 2, start[1] - offset - LABEL_HEIGHT, label_width, LABEL_HEIGHT),
                        LayoutBox(center - label_width // 2, start[1] + offset, label_width, LABEL_HEIGHT),
                    ))
        elif start[0] == end[0]:
            low, high = sorted((start[1], end[1]))
            for fraction in ALONG_FRACTIONS:
                center = _grid(low + (high - low) * fraction)
                for offset in PERPENDICULAR_OFFSETS:
                    candidates.extend((
                        LayoutBox(start[0] + offset, center - LABEL_HEIGHT // 2, label_width, LABEL_HEIGHT),
                        LayoutBox(start[0] - offset - label_width, center - LABEL_HEIGHT // 2, label_width, LABEL_HEIGHT),
                    ))
    for candidate in candidates:
        if not _inside(candidate, width, height):
            continue
        if any(_overlap(candidate, node, padding=NODE_CLEARANCE) for node in node_boxes):
            continue
        if any(_overlap(candidate, obstacle, padding=NODE_CLEARANCE) for obstacle in occupied):
            continue
        if any(_box_segment_distance(candidate, start, end) < LABEL_GAP for start, end in segments):
            continue
        return candidate
    return None


def _inside(box: LayoutBox, width: int, height: int) -> bool:
    return (
        box.x >= CANVAS_MARGIN
        and box.y >= CANVAS_MARGIN
        and box.x + box.w <= width - CANVAS_MARGIN
        and box.y + box.h <= height - CANVAS_MARGIN
    )


def _overlap(left: LayoutBox, right: LayoutBox, padding: int = 0) -> bool:
    return not (
        left.x + left.w + padding <= right.x
        or right.x + right.w + padding <= left.x
        or left.y + left.h + padding <= right.y
        or right.y + right.h + padding <= left.y
    )


def _box_segment_distance(box: LayoutBox, start: tuple[int, int], end: tuple[int, int]) -> int:
    if start[1] == end[1]:
        low, high = sorted((start[0], end[0]))
        horizontal_gap = max(box.x - high, low - (box.x + box.w), 0)
        vertical_gap = max(box.y - start[1], start[1] - (box.y + box.h), 0)
        return horizontal_gap + vertical_gap
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        horizontal_gap = max(box.x - start[0], start[0] - (box.x + box.w), 0)
        vertical_gap = max(box.y - high, low - (box.y + box.h), 0)
        return horizontal_gap + vertical_gap
    return 0


def _grid(value: float) -> int:
    return int(round(value / 4) * 4)


def _grid_width(value: float) -> int:
    """Keep centered label boxes and their text anchors on the 4-unit grid."""
    return int(round(value / 8) * 8)
