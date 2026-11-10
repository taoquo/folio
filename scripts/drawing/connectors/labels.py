from __future__ import annotations

from dataclasses import replace

from ..layout.models import LayoutBox, LayoutEdge
from ..theme.folio import DEFAULT_FOLIO_THEME
from ..typography.measure import measure_text

LABEL_GAP = 8
LABEL_HEIGHT = 16
CANVAS_MARGIN = 8
NODE_CLEARANCE = 4
# A connector label longer than this is not drawn: a word that needs half the
# row to say itself stops being a label and becomes a caption. The same rule
# sizes the row it has to live in, so the two cannot disagree.
EDGE_LABEL_MAX_CHARS = 14
PERPENDICULAR_OFFSETS = (LABEL_GAP, 24, 40, 56, 72)
# How far a label may drift from the connector it names. Twice the label's own
# height is still "beside the line"; beyond that the word labels nothing, and a
# plate that cannot keep it closer shows no connector labels at all.
LABEL_REACH = LABEL_HEIGHT * 2
# Sliding the label along its own segment keeps it attached to the connector it names. Without
# this the placer falls back to a distant stub segment as soon as the midpoint is blocked.
ALONG_FRACTIONS = (0.5, 0.38, 0.62, 0.26, 0.74)


def compact_edge_label(label: str | None) -> str | None:
    """The text a connector label is drawn as, or None when it is too long."""
    if not label:
        return None
    compact = " ".join(label.split()).upper()
    return compact if len(compact) <= EDGE_LABEL_MAX_CHARS else None


def label_width(text: str, size: float = 8) -> int:
    """The box a connector label occupies, on the grid the placer uses.

    Exposed because the layout has to reserve this width *before* the label is
    placed: a row gap measured at one width and drawn at another is how a
    connector loses its label.
    """
    return _grid_width(max(32, min(200, measure_text(text, size, DEFAULT_FOLIO_THEME.mono) + 8)))


def place_edge_labels(
    edges: list[LayoutEdge],
    node_boxes: list[LayoutBox],
    width: int,
    height: int,
    obstacles: tuple[LayoutBox, ...] = (),
    boundaries: tuple[LayoutBox, ...] = (),
    reach: int | None = None,
    size: float = 8,
) -> list[LayoutEdge]:
    """Place connector labels beside segments without using an opaque line mask.

    ``obstacles`` are solid: nothing may be drawn over them. ``boundaries`` are
    outlines: a label may live inside or outside a group boundary, but not
    across its edge, because the rule would run through the word. ``reach``
    bounds how far from its own connector a label may sit.
    """
    segments = [segment for edge in edges for segment in zip(edge.points, edge.points[1:])]
    occupied: list[LayoutBox] = list(obstacles)
    result: list[LayoutEdge] = []
    for edge in edges:
        if not edge.label:
            result.append(edge)
            continue
        box = _label_box(
            edge.label, edge.points, node_boxes, occupied, segments, width, height,
            boundaries, reach, size,
        )
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
    boundaries: tuple[LayoutBox, ...] = (),
    reach: int | None = None,
    size: float = 8,
) -> LayoutBox | None:
    # The box is measured at the size the label is drawn at: a 9-unit label in
    # a box sized for 8 overflows it, and the collision checks then approve a
    # placement that visibly overlaps.
    box_width = label_width(label, size)
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
                if center - box_width // 2 < low - box_width or center + box_width // 2 > high + box_width:
                    continue
                for offset in PERPENDICULAR_OFFSETS:
                    candidates.extend((
                        LayoutBox(center - box_width // 2, start[1] - offset - LABEL_HEIGHT, box_width, LABEL_HEIGHT),
                        LayoutBox(center - box_width // 2, start[1] + offset, box_width, LABEL_HEIGHT),
                    ))
        elif start[0] == end[0]:
            low, high = sorted((start[1], end[1]))
            for fraction in ALONG_FRACTIONS:
                center = _grid(low + (high - low) * fraction)
                for offset in PERPENDICULAR_OFFSETS:
                    candidates.extend((
                        LayoutBox(start[0] + offset, center - LABEL_HEIGHT // 2, box_width, LABEL_HEIGHT),
                        LayoutBox(start[0] - offset - box_width, center - LABEL_HEIGHT // 2, box_width, LABEL_HEIGHT),
                    ))
    for candidate in candidates:
        if not _inside(candidate, width, height):
            continue
        if any(_overlap(candidate, node, padding=NODE_CLEARANCE) for node in node_boxes):
            continue
        if reach is not None and _distance_to_route(candidate, points) > reach:
            continue
        if any(_overlap(candidate, obstacle, padding=NODE_CLEARANCE) for obstacle in occupied):
            continue
        if any(_crosses_outline(candidate, frame) for frame in boundaries):
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


def _crosses_outline(box: LayoutBox, frame: LayoutBox, padding: int = NODE_CLEARANCE) -> bool:
    """Whether a label straddles a boundary's edge.

    A label wholly inside or wholly outside the frame is fine -- connectors run
    in and out of groups all the time. Only a label the frame's own line would
    cut through is a defect.
    """
    inside = (
        box.x >= frame.x + padding
        and box.y >= frame.y + padding
        and box.x + box.w <= frame.x + frame.w - padding
        and box.y + box.h <= frame.y + frame.h - padding
    )
    outside = (
        box.x + box.w + padding <= frame.x
        or frame.x + frame.w + padding <= box.x
        or box.y + box.h + padding <= frame.y
        or frame.y + frame.h + padding <= box.y
    )
    return not (inside or outside)


def _distance_to_route(box: LayoutBox, points: list[tuple[int, int]]) -> int:
    return min((_box_segment_distance(box, a, b) for a, b in zip(points, points[1:])), default=0)


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
