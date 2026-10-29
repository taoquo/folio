#!/usr/bin/env python3
"""Folio Web reading-page contracts.

Single source of truth for the Web reading-page scenario: page types, regions,
the closed status vocabulary, title rules, numbering, figure-caption grammar,
density limits, the C2 concept-to-series mapping, figure budgets, and the
16-item acceptance list.

Nothing here renders. `scripts/check_web.py` enforces it, `scripts/build_web.py`
consumes the delivery constants, and `references/web/web-acceptance.md` cites the
same ids. A rule that is not in this module is not a rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- page types

PAGE_TYPES: dict[str, dict] = {
    "module-archive": {
        "body_class": "module-archive",
        "required": ("topbar", "doc-head", "toc", "chapter", "doc-nav"),
        "optional": ("kpi-row", "phase-seg", "insight", "multi-card", "tbl", "figure", "prose-list", "rail"),
    },
    "series-index": {
        "body_class": "series-index",
        "required": ("doc-head", "module-grid"),
        "optional": ("topbar", "doc-nav", "rail"),
    },
}

# After the document head, these must not appear: their information already has
# a primary home in the index block and the body.
FORBIDDEN_AFTER_HEAD = ("status-row", "identity-kpi", "evidence-note")

TOPBAR_LINKS = 1

# ------------------------------------------------------- closed vocabulary

# The page language follows the series, so the vocabulary is bilingual. Both
# lists are closed: a status outside them is still a defect, and each group is
# the same statement in two languages rather than a second set of meanings.
STATUS_VOCAB = (
    "已实现", "代码验证", "规范", "引擎对照", "规划中",
    "Implemented", "Code-verified", "Spec", "Engine parity", "Planned",
)

# Package state and integration state are separate statements.
STATUS_GROUPS = {
    "package": ("已实现", "代码验证", "Implemented", "Code-verified"),
    "integration": ("规范", "引擎对照", "规划中", "Spec", "Engine parity", "Planned"),
}

# ------------------------------------------------------------ title rules

# A title names a thing. Arrows, operators, long dashes, "vs" and middle dots
# mark a sentence, not a name. figcaption is the one exemption.
TITLE_BANNED = ("→", "←", "↔", "——", " vs ", "·", " + ", " × ", " = ", " ≠ ")
TITLE_BANNED_CHARS = ("→", "←", "↔", "——", "·")
FIGCAPTION_EXEMPT_ENDS = ("figcaption",)

# ---------------------------------------------------------------- numbering

CHAPTER_NUM = re.compile(r"^\s*(\d{2})\b")
FIGURE_NUM = re.compile(r"^(?:图|Figure) ([A-Z]?-?\d+) · ")

# figcaption grammar: 图 / Figure 前缀-N · 图意 · composition: X · axis: Y
FIGCAPTION = re.compile(
    r"^(?:图|Figure) [A-Z]?-?\d+ · .+? · "
    r"(?:composition: (layered|pipeline|hub)|kind: ([a-z-]+))"
    r" · axis: (top-down|left-right)$"
)

# ----------------------------------------------------------------- density

# All values derive from the engine ladder (pt x 1.33) and the engine spacing
# scale; the ranges below are the Web reading-page band.
DENSITY: dict[str, tuple[float, float]] = {
    "page_padding_x": (24.0, 40.0),
    "body_size": (15.0, 20.0),
    "h2_size": (26.0, 34.0),
    "card_padding": (14.0, 24.0),
    "table_row_height": (28.0, 40.0),
    "dead_zone": (0.0, 24.0),
}

MEASURE_CHARS = (60.0, 95.0)

# ------------------------------------------------------- C2 concept mapping

# The ten meanings a page component may declare with `data-role`. A phase bar
# or a semantic mark must name one; an unlabelled mark cannot use a semantic
# colour, because no one can say which meaning it carries.
SEMANTIC_ROLES = (
    "delivered", "info", "component", "passed", "attention",
    "enhance", "risk", "change", "input", "pending",
)

# Ten content concepts, six drawing series. A concept keeps its series across
# documents; the two that share a series are never adjacent in one figure.
CONCEPT_TO_SERIES = {
    "delivered": 1,
    "info": 2,
    "component": 3,
    "passed": 4,
    "attention": 5,
    "pending": 6,
    "enhance": 5,
    "change": 2,
    "input": 3,
    "risk": 6,
}

# Figures may use semantic or series variables; nothing else.
FIGURE_COLOR_PREFIX = ("--color-semantic-", "--color-series-")
FIGURE_MAX_COLORS = 4

# ------------------------------------------------------------ figure budgets

FIGURE = {
    "width": 960,
    # The drawing DSL's canvas bands: graphs 500-800, charts 400-720, notations 480-800.
    "view_box_height": (400, 800),
    # The page's content width. The reading page is one column, so a figure is
    # exactly as wide as the text.
    "slot": 660,
    # Rendered at that slot (660px / 960 units): the same bands in page pixels.
    "rendered_height": (275, 550),
    "architecture_nodes_max": 9,
    "rows_max": 10,
    "focal_max": 2,
    "colour_max": 4,
}

# Plan figures declare a composition; data figures declare their kind.
COMPOSITIONS = ("layered", "pipeline", "hub")
AXES = ("top-down", "left-right")

FIGURE_KINDS = (
    "architecture", "bar-chart", "candlestick", "donut-chart", "er-diagram",
    "flowchart", "gantt", "heatmap", "layer-stack", "line-chart",
    "loop-flywheel", "org-chart", "pyramid", "quadrant", "scatter",
    "sequence", "state-machine", "swimlane", "timeline", "tree",
    "uml-class", "venn", "waterfall",
)

# --------------------------------------------------- componentization scan

# Text features that must become a component. Order matters: the first match
# names the component the checker asserts.
COMPONENT_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("circled-step", r"[①②③④⑤]", "prose-list"),
    ("numbered-step", r"(?m)^\s*\d{1,2}[.、]\s+(?!\d)\S", "prose-list"),
    ("arrow-flow", r"(?:→.*){2,}→", "figure"),
    ("metric", r"\d+(?:\.\d+)?\s*(?:BLEU|GPUs?|days?|hours?|steps?|%|ms|tokens?)", "kpi-row"),
    ("stage", r"(?:阶段|档位|warmup|schedule)", "phase-seg"),
    ("mapping", r"(?:映射|对照|字段|参数)", "tbl"),
)

# ------------------------------------------------------------- acceptance

@dataclass(frozen=True)
class Acceptance:
    """One acceptance item; `kind` says who can decide it."""

    key: str
    title: str
    kind: str  # machine | semi | manual


ACCEPTANCE: tuple[Acceptance, ...] = (
    Acceptance("zero-deletion", "源文档小节/表格/代码/数值零删减", "machine"),
    Acceptance("componentized", "扫描判据命中项全部组件化", "machine"),
    Acceptance("no-purple", "无紫块当列表头/长紫块/多子句堆砌/新旧重复块", "semi"),
    Acceptance("no-header-trio", "页头无三件套", "machine"),
    Acceptance("table-shape", "表格首列垂直居中；td 内流程已列表化", "machine"),
    Acceptance("figures", "图表合同：composition/axis/节点档/focal/元数据/图注", "machine"),
    Acceptance("geometry", "几何审计归零", "machine"),
    Acceptance("numbering", "图号全篇连续；小节编号连续无撞号", "machine"),
    Acceptance("title-symbols", "标题禁用符号归零", "machine"),
    Acceptance("links", "标签配对、JS 平衡、外链可达", "machine"),
    Acceptance("colour", "L1/L2 与引擎样式合规；语义色可区分；单图彩色不超过 4", "machine"),
    Acceptance("evidence", "实证齐全：文件行号 / Sources / 引擎对照章", "semi"),
    Acceptance("reading-rail", "右侧章节刻度存在、随滚动激活、hover 显示标题", "semi"),
    Acceptance("figure-provenance", "每张图可追到 DSL fixture 与 sha", "machine"),
    Acceptance("figure-dsl", "图表由 DSL 编译且 ERROR 诊断为零", "machine"),
    Acceptance("online", "线上验证逐项 PASS", "manual"),
)

ACCEPTANCE_BY_KEY = {item.key: item for item in ACCEPTANCE}

# ------------------------------------------------------------- delivery

DELIVERY = {
    "stylesheet_links": 0,
    "script_srcs": 0,
    "download_attributes": 0,
}

SERIES_FILE = "series.json"


def is_allowed_status(value: str) -> bool:
    return value in STATUS_VOCAB


def concept_series(concept: str) -> int:
    return CONCEPT_TO_SERIES[concept]
