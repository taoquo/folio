from __future__ import annotations

"""Semantic pattern vocabulary for Drawing DSL V5.

This module owns the mapping from communication intent to diagram families.
It never touches pixels, scenes, or layout. The router in ``route.py`` uses
these tables to produce a deterministic, explainable recommendation.
"""


SEMANTIC_PATTERNS: tuple[str, ...] = (
    "architecture",
    "comparison",
    "data",
    "flow",
    "hierarchy",
    "relationship",
    "state",
    "time",
)


# Ordered candidate kinds per pattern. Order encodes the default preference,
# which keeps routing deterministic when scores tie.
PATTERN_KINDS: dict[str, tuple[str, ...]] = {
    "architecture": ("architecture", "layer-stack"),
    "comparison": ("bar-chart", "quadrant", "venn", "heatmap"),
    "data": ("bar-chart", "line-chart", "donut-chart", "waterfall", "candlestick", "scatter"),
    "flow": ("flowchart", "swimlane", "sequence", "loop-flywheel"),
    "hierarchy": ("tree", "layer-stack", "org-chart", "pyramid"),
    "relationship": ("er-diagram", "uml-class", "venn"),
    "state": ("state-machine",),
    "time": ("timeline", "candlestick", "line-chart", "gantt"),
}


# Lowercase keyword cues per pattern. English and Chinese share one table so a
# mixed-language brief routes the same way in both directions.
PATTERN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "architecture": (
        "architecture", "system", "service", "component", "platform", "deployment",
        "架构", "系统", "服务", "组件", "平台", "部署",
    ),
    "comparison": (
        "compare", "comparison", "versus", " vs ", "ranking", "tradeoff", "overlap",
        "heatmap", "heat map", "matrix", "density",
        "对比", "比较", "排名", "权衡", "重叠", "热力图", "矩阵", "热度",
    ),
    "data": (
        "metric", "metrics", "revenue", "growth", "distribution", "share", "trend", "scatter",
        "指标", "数据", "营收", "增长", "分布", "占比", "趋势", "散点",
    ),
    "flow": (
        "flow", "process", "pipeline", "workflow", "step", "handoff", "request",
        "flywheel", "virtuous",
        "流程", "流转", "管道", "步骤", "交接", "请求", "飞轮",
    ),
    "hierarchy": (
        "hierarchy", "tree", "breakdown", "taxonomy", "reporting", "layer",
        "funnel", "pyramid", "org chart", "headcount",
        "层级", "树", "拆解", "分类", "组织", "汇报", "分层", "漏斗", "金字塔",
    ),
    "relationship": (
        "relationship", "entity", "schema", "class", "correlation", "association",
        "关系", "实体", "模型", "类图", "相关", "关联",
    ),
    "state": (
        "state", "status", "transition", "lifecycle", "machine", "retry",
        "状态", "转移", "生命周期", "状态机", "重试",
    ),
    "time": (
        "timeline", "milestone", "schedule", "roadmap", "quarter", "history", "gantt",
        "时间线", "里程碑", "排期", "路线图", "季度", "历史", "甘特",
    ),
}


# Audience cues bias the ramp between dense and simplified kinds.
AUDIENCES: tuple[str, ...] = ("executive", "general", "practitioner")

# Communication goals bias which candidate inside a pattern wins.
GOALS: tuple[str, ...] = ("compare", "convince", "explain", "track")


def normalize_pattern(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text if text in SEMANTIC_PATTERNS else None


def pattern_of_kind(kind: str) -> str | None:
    for pattern in SEMANTIC_PATTERNS:
        if kind in PATTERN_KINDS[pattern]:
            return pattern
    return None
