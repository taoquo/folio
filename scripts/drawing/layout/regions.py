from __future__ import annotations

from ..grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR, ArchitectureGrammar
from ..models import DrawingPlan
from .models import LayoutBox

# The treatments that wrap a group of nodes in a drawn boundary. A layer band
# is not one of them: it is a separator rule and a header, not a frame.
BOUNDARY_TREATMENTS = frozenset({"soft-boundary", "trust-boundary", "phase-band"})


def region_frames(
    drawing: DrawingPlan,
    boxes: dict[str, LayoutBox],
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> tuple[tuple[object, LayoutBox], ...]:
    """Every drawn group boundary, as the rectangle it will be drawn as.

    Both passes that care about a boundary need the same rectangle: the render
    pass draws it, and the layout pass has to keep connector labels off it,
    because a dashed rule through a word reads as a strikethrough. Computing it
    in one place is what stops the two from disagreeing about where the border
    is -- the disagreement that let a label be placed on a line drawn later.
    """
    geometry = grammar.geometry
    frames: list[tuple[object, LayoutBox]] = []
    for region in drawing.regions:
        if region.treatment not in BOUNDARY_TREATMENTS:
            continue
        members = [boxes[item] for item in region.members if item in boxes]
        if len(members) < 2:
            continue
        left = min(box.x for box in members) - geometry.group_pad_x
        top = min(box.y for box in members) - geometry.group_pad_top
        right = max(box.x + box.w for box in members) + geometry.group_pad_x
        bottom = max(box.y + box.h for box in members) + geometry.group_pad_bottom
        frames.append((region, LayoutBox(left, top, right - left, bottom - top)))
    return tuple(frames)


def region_label_bands(
    frames: tuple[tuple[object, LayoutBox], ...],
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
) -> tuple[LayoutBox, ...]:
    """The strip inside a boundary's top padding where its own name is set.

    That strip belongs to the boundary, not to a connector that happens to
    cross it, so the label placer treats it as occupied. Without that, a
    connector label can take the slot and leave the region name nowhere to go
    but on top of it.
    """
    pad = grammar.geometry.group_pad_top
    return tuple(LayoutBox(frame.x, frame.y, frame.w, pad) for _region, frame in frames)
