from __future__ import annotations

"""Deterministic semantic-pattern routing for Drawing DSL V5.

The router sits in front of the compiler registry. It turns a short authoring
brief into one recommended diagram kind plus an explainable trace. It reads
only semantics: text cues, audience, goal, and coarse data shape. It never
reads or writes geometry, so the semantic and visual layers stay separate.

Routing is pure and deterministic: the same brief always yields the same
decision, alternatives, trace, and diagnostics.
"""

from dataclasses import dataclass, field
from typing import Any

from ..validation import DrawingDiagnostic
from .patterns import (
    AUDIENCES,
    GOALS,
    PATTERN_KEYWORDS,
    PATTERN_KINDS,
    SEMANTIC_PATTERNS,
    normalize_pattern,
    pattern_of_kind,
)


KEYWORD_WEIGHT = 3
SHAPE_WEIGHT = 2
HINT_WEIGHT = 12
AMBIGUITY_MARGIN = 2


@dataclass(frozen=True)
class DataShape:
    """Coarse, pixel-free description of the material to be drawn."""

    node_count: int = 0
    edge_count: int = 0
    series_count: int = 0
    category_count: int = 0
    depth: int = 0
    has_time_axis: bool = False
    has_cycle: bool = False
    has_actors: bool = False
    numeric: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "series_count": self.series_count,
            "category_count": self.category_count,
            "depth": self.depth,
            "has_time_axis": self.has_time_axis,
            "has_cycle": self.has_cycle,
            "has_actors": self.has_actors,
            "numeric": self.numeric,
        }


@dataclass(frozen=True)
class RouteRequest:
    """One routing question. ``content`` is the author brief, not a payload."""

    content: str = ""
    audience: str = "general"
    goal: str = "explain"
    pattern_hint: str | None = None
    kind_hint: str | None = None
    shape: DataShape = field(default_factory=DataShape)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "audience": self.audience,
            "goal": self.goal,
            "pattern_hint": self.pattern_hint,
            "kind_hint": self.kind_hint,
            "shape": self.shape.to_dict(),
        }


@dataclass(frozen=True)
class RouteStep:
    stage: str
    detail: str
    score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "detail": self.detail, "score": self.score}


@dataclass(frozen=True)
class RouteDecision:
    pattern: str | None
    kind: str | None
    confidence: str
    scores: tuple[tuple[str, int], ...]
    alternatives: tuple[str, ...]
    trace: tuple[RouteStep, ...]
    diagnostics: tuple[DrawingDiagnostic, ...]

    @property
    def routable(self) -> bool:
        return self.kind is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "kind": self.kind,
            "confidence": self.confidence,
            "scores": [{"pattern": name, "score": score} for name, score in self.scores],
            "alternatives": list(self.alternatives),
            "trace": [step.to_dict() for step in self.trace],
            "diagnostics": [
                {
                    "level": item.level,
                    "code": item.code,
                    "message": item.message,
                    "hint": item.hint or "",
                }
                for item in self.diagnostics
            ],
        }


def _shape_bonus(pattern: str, shape: DataShape) -> tuple[int, tuple[str, ...]]:
    reasons: list[str] = []
    score = 0
    if pattern == "data" and shape.numeric and shape.series_count:
        score += SHAPE_WEIGHT
        reasons.append(f"numeric series present ({shape.series_count})")
    if pattern == "time" and shape.has_time_axis:
        score += SHAPE_WEIGHT
        reasons.append("time axis present")
    if pattern == "hierarchy" and shape.depth >= 2 and not shape.has_cycle:
        score += SHAPE_WEIGHT
        reasons.append(f"acyclic depth {shape.depth}")
    if pattern == "state" and shape.has_cycle and shape.node_count:
        score += SHAPE_WEIGHT
        reasons.append("cyclic transitions present")
    if pattern == "flow" and shape.edge_count >= shape.node_count > 0:
        score += SHAPE_WEIGHT
        reasons.append("edge count matches or exceeds node count")
    if pattern == "relationship" and shape.node_count and shape.edge_count and not shape.has_time_axis:
        score += SHAPE_WEIGHT
        reasons.append("static entity graph")
    if pattern == "architecture" and shape.node_count >= 4 and shape.edge_count:
        score += SHAPE_WEIGHT
        reasons.append(f"{shape.node_count} connected components")
    if pattern == "comparison" and shape.category_count >= 2 and shape.numeric:
        score += SHAPE_WEIGHT
        reasons.append(f"{shape.category_count} comparable categories")
    return score, tuple(reasons)


def _keyword_hits(pattern: str, text: str) -> tuple[str, ...]:
    return tuple(word for word in PATTERN_KEYWORDS[pattern] if word.strip() and word in text)


def _select_kind(pattern: str, request: RouteRequest) -> tuple[str, str]:
    """Pick one kind inside a pattern, with the reason recorded for the trace."""
    candidates = PATTERN_KINDS[pattern]
    shape = request.shape
    cues = f" {request.content.strip().lower()} "

    def said(*words: str) -> bool:
        return any(word in cues for word in words)

    if request.kind_hint in candidates:
        return request.kind_hint, "author kind hint inside the routed pattern"
    if pattern == "data":
        if said("scatter", "散点", "correlation", "versus", "相关性"):
            return "scatter", "two numeric axes compared point by point"
        if shape.has_time_axis:
            return "line-chart", "numeric values move along a time axis"
        if shape.series_count == 1 and 0 < shape.category_count <= 5 and request.goal == "compare":
            return "donut-chart", "single series split into few shares"
        return "bar-chart", "discrete categories compared by magnitude"
    if pattern == "time":
        if said("gantt", "甘特", "sprint", "workstream", "工作流排期"):
            return "gantt", "tasks occupy spans across shared periods"
        if shape.numeric and shape.series_count:
            return "line-chart", "time series carries numeric values"
        return "timeline", "discrete dated events"
    if pattern == "flow":
        if said("flywheel", "飞轮", "virtuous", "self-reinforcing") or (shape.has_cycle and not shape.has_actors):
            return "loop-flywheel", "stages reinforce each other in a closed loop"
        if shape.has_actors:
            return "sequence" if request.audience == "practitioner" else "swimlane", (
                "actors exchange ordered messages"
                if request.audience == "practitioner"
                else "actors own parallel lanes of work"
            )
        return "flowchart", "single ordered path with branches"
    if pattern == "hierarchy":
        if said("funnel", "pyramid", "漏斗", "金字塔"):
            return "pyramid", "stacked tiers that narrow toward one apex"
        if said("org chart", "headcount", "reporting line", "组织架构", "汇报线"):
            return "org-chart", "reporting lines under a single root"
        if shape.depth and shape.depth <= 2 and shape.edge_count == 0:
            return "layer-stack", "shallow stack without cross links"
        return "tree", "parent-child breakdown"
    if pattern == "comparison":
        if said("heatmap", "heat map", "matrix", "density", "热力图", "矩阵", "热度"):
            return "heatmap", "one measure graded across two categorical axes"
        if shape.numeric and shape.category_count >= 2:
            return "bar-chart", "numeric magnitudes across categories"
        if shape.node_count and shape.node_count <= 3:
            return "venn", "few sets with shared members"
        return "quadrant", "positions along two qualitative axes"
    if pattern == "relationship":
        if request.audience == "practitioner" and shape.numeric:
            return "uml-class", "typed structures with members"
        if shape.node_count and shape.node_count <= 3 and shape.edge_count == 0:
            return "venn", "overlapping sets without directed links"
        return "er-diagram", "entities linked by cardinality"
    if pattern == "architecture":
        if shape.depth >= 3 and shape.edge_count <= shape.node_count:
            return "layer-stack", "stacked responsibilities with vertical calls"
        return "architecture", "components grouped into regions"
    return candidates[0], "only candidate for the pattern"


def route_semantic_pattern(request: RouteRequest) -> RouteDecision:
    text = f" {request.content.strip().lower()} "
    trace: list[RouteStep] = []
    diagnostics: list[DrawingDiagnostic] = []

    if request.audience not in AUDIENCES:
        diagnostics.append(DrawingDiagnostic(
            "WARNING", "RT010", "unknown audience; falling back to general",
            hint="use one of: " + ", ".join(AUDIENCES),
        ))
        request = RouteRequest(request.content, "general", request.goal, request.pattern_hint, request.kind_hint, request.shape)
    if request.goal not in GOALS:
        diagnostics.append(DrawingDiagnostic(
            "WARNING", "RT011", "unknown goal; falling back to explain",
            hint="use one of: " + ", ".join(GOALS),
        ))
        request = RouteRequest(request.content, request.audience, "explain", request.pattern_hint, request.kind_hint, request.shape)

    hint = normalize_pattern(request.pattern_hint)
    if request.pattern_hint and hint is None:
        diagnostics.append(DrawingDiagnostic(
            "ERROR", "RT003", "unknown semantic pattern hint", str(request.pattern_hint),
            hint="use one of: " + ", ".join(SEMANTIC_PATTERNS),
        ))
        return RouteDecision(None, None, "none", (), (), tuple(trace), tuple(diagnostics))

    kind_pattern = pattern_of_kind(request.kind_hint) if request.kind_hint else None
    if request.kind_hint and kind_pattern is None:
        diagnostics.append(DrawingDiagnostic(
            "ERROR", "RT004", "kind hint belongs to no semantic pattern", str(request.kind_hint),
        ))
        return RouteDecision(None, None, "none", (), (), tuple(trace), tuple(diagnostics))

    scores: dict[str, int] = {}
    for pattern in SEMANTIC_PATTERNS:
        hits = _keyword_hits(pattern, text)
        score = KEYWORD_WEIGHT * len(hits)
        if hits:
            trace.append(RouteStep("keyword", f"{pattern}: " + ", ".join(hits), KEYWORD_WEIGHT * len(hits)))
        bonus, reasons = _shape_bonus(pattern, request.shape)
        score += bonus
        for reason in reasons:
            trace.append(RouteStep("shape", f"{pattern}: {reason}", SHAPE_WEIGHT))
        if pattern == hint:
            score += HINT_WEIGHT
            trace.append(RouteStep("hint", f"{pattern}: author pattern hint", HINT_WEIGHT))
        elif pattern == kind_pattern:
            score += HINT_WEIGHT
            trace.append(RouteStep("hint", f"{pattern}: implied by kind hint", HINT_WEIGHT))
        scores[pattern] = score

    ranked = tuple(sorted(scores.items(), key=lambda item: (-item[1], SEMANTIC_PATTERNS.index(item[0]))))
    top, top_score = ranked[0]

    if top_score <= 0:
        diagnostics.append(DrawingDiagnostic(
            "ERROR", "RT001", "no semantic pattern matched; the brief may not be drawable",
            hint="add structure cues, or state the pattern explicitly with a hint",
        ))
        trace.append(RouteStep("reject", "all patterns scored zero", 0))
        return RouteDecision(None, None, "none", ranked, (), tuple(trace), tuple(diagnostics))

    runner_up, runner_score = ranked[1]
    ambiguous = top_score - runner_score < AMBIGUITY_MARGIN
    if ambiguous:
        diagnostics.append(DrawingDiagnostic(
            "WARNING", "RT002", "two semantic patterns scored within the ambiguity margin",
            top, related_ids=(top, runner_up),
            hint=f"confirm {top} over {runner_up}, or pass an explicit pattern hint",
        ))

    kind, reason = _select_kind(top, request)
    trace.append(RouteStep("pattern", f"{top} wins with score {top_score}", top_score))
    trace.append(RouteStep("kind", f"{kind}: {reason}"))

    confidence = "low" if ambiguous else ("high" if top_score >= runner_score + 2 * AMBIGUITY_MARGIN else "medium")
    alternatives = tuple(item for item in PATTERN_KINDS[top] if item != kind)
    return RouteDecision(top, kind, confidence, ranked, alternatives, tuple(trace), tuple(diagnostics))


def route_from_dict(payload: dict[str, Any]) -> RouteDecision:
    """Route an explicit JSON request. Unknown keys are rejected up front."""
    allowed = {"content", "audience", "goal", "pattern_hint", "kind_hint", "shape"}
    extra = sorted(set(payload) - allowed)
    if extra:
        raise ValueError("unknown routing fields: " + ", ".join(extra))
    raw_shape = payload.get("shape") or {}
    if not isinstance(raw_shape, dict):
        raise ValueError("shape must be an object")
    shape_fields = set(DataShape().to_dict())
    unknown_shape = sorted(set(raw_shape) - shape_fields)
    if unknown_shape:
        raise ValueError("unknown shape fields: " + ", ".join(unknown_shape))
    shape = DataShape(**raw_shape)
    return route_semantic_pattern(RouteRequest(
        content=str(payload.get("content", "")),
        audience=str(payload.get("audience", "general")),
        goal=str(payload.get("goal", "explain")),
        pattern_hint=payload.get("pattern_hint"),
        kind_hint=payload.get("kind_hint"),
        shape=shape,
    ))
