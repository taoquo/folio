from __future__ import annotations

from dataclasses import dataclass, replace

from ..grammar.architecture import ArchitectureGrammar, DEFAULT_ARCHITECTURE_GRAMMAR
from ..models import DrawingPlan
from ..semantics.models import SemanticDiagram
from .elk import layout_drawing
from .models import LayoutResult


@dataclass(frozen=True)
class LayoutCandidate:
    name: str
    layout: LayoutResult
    score: tuple[int, int, int, int, int, int, str]


def select_layout(
    drawing: DrawingPlan,
    semantic: SemanticDiagram | None = None,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
    limit: int = 8,
) -> LayoutResult:
    """Evaluate a bounded deterministic candidate set and return the least costly layout."""
    return rank_layout_candidates(drawing, semantic, grammar, limit)[0].layout


def rank_layout_candidates(
    drawing: DrawingPlan,
    semantic: SemanticDiagram | None = None,
    grammar: ArchitectureGrammar = DEFAULT_ARCHITECTURE_GRAMMAR,
    limit: int = 8,
) -> tuple[LayoutCandidate, ...]:
    variants = [("declared", drawing)]
    if any(len(region.members) > 1 for region in drawing.regions):
        variants.append(
            (
                "region-order-reversed",
                replace(
                    drawing,
                    regions=tuple(
                        replace(region, members=tuple(reversed(region.members)))
                        if len(region.members) > 1
                        else region
                        for region in drawing.regions
                    ),
                ),
            )
        )
    candidates = []
    for name, variant in variants[: max(1, min(limit, 8))]:
        layout = layout_drawing(variant, semantic, grammar)
        candidates.append(LayoutCandidate(name, layout, _score(name, layout, drawing)))
    return tuple(sorted(candidates, key=lambda item: item.score))


def _score(name: str, layout: LayoutResult, drawing: DrawingPlan) -> tuple[int, int, int, int, int, int, str]:
    violations = sum(" overlaps " in item or " crosses " in item for item in layout.warnings)
    crossings = _crossing_count(layout)
    bends = sum(max(0, len(edge.points) - 2) for edge in layout.edges)
    spine_pairs = set(zip(drawing.composition.spine, drawing.composition.spine[1:]))
    spine_bends = sum(
        max(0, len(edge.points) - 2)
        for edge in layout.edges
        if (edge.source, edge.target) in spine_pairs
    )
    return len(layout.warnings), violations, crossings, spine_bends, bends, _spacing_variance(layout), name


def _crossing_count(layout: LayoutResult) -> int:
    count = 0
    for index, left in enumerate(layout.edges):
        for right in layout.edges[index + 1:]:
            if {left.source, left.target} & {right.source, right.target}:
                continue
            if any(
                _segments_cross(a, b, c, d)
                for a, b in zip(left.points, left.points[1:])
                for c, d in zip(right.points, right.points[1:])
            ):
                count += 1
                break
    return count


def _segments_cross(
    a: tuple[int, int], b: tuple[int, int], c: tuple[int, int], d: tuple[int, int]
) -> bool:
    if a[0] == b[0] and c[1] == d[1]:
        return min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1])
    if a[1] == b[1] and c[0] == d[0]:
        return min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1])
    return False


def _spacing_variance(layout: LayoutResult) -> int:
    rows: dict[int, list[object]] = {}
    for box in layout.boxes.values():
        rows.setdefault(box.y, []).append(box)
    gaps: list[int] = []
    for boxes in rows.values():
        ordered = sorted(boxes, key=lambda box: box.x)
        gaps.extend(max(0, right.x - (left.x + left.w)) for left, right in zip(ordered, ordered[1:]))
    return max(gaps) - min(gaps) if len(gaps) > 1 else 0
