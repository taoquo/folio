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

# figcaption grammar: 图 / Figure 前缀-N · 图意.
# The composition and the reading axis are figure facts, carried by
# `data-composition` / `data-axis` and compared with the manifest by W-FIG-01.
# They are not printed under the plate: a caption is read, not parsed.
FIGCAPTION = re.compile(r"^(?:图|Figure) [A-Z]?-?\d+ · (?!.*\b(?:composition|axis):).+$")

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
    # The text column's width. The reading page is one column, so a figure is
    # exactly as wide as the text.
    "slot": 660,
    # The plate's shape: framed height over framed width. A figure composed for
    # a band is delivered at that band's size, so its proportions -- not its
    # pixels -- are what the contract can hold across viewports. A narrow
    # composition wraps its rows and arrives portrait (1.0-1.4); a wide one
    # arrives landscape (0.5-0.8). The band rejects both the strip and the
    # column-tall plate.
    "rendered_aspect": (0.45, 1.50),
    "architecture_nodes_max": 9,
    "rows_max": 10,
    "focal_max": 2,
    "colour_max": 4,
    # The drawing's type tiers are 7 / 9 / 12 units. On a stage composed for the
    # band, those units arrive as pixels, so the smallest tier is exactly the
    # legibility floor rather than a target the page could widen its way to.
    "title_min_px": 11,
    "tier_min_px": 7,
}

# A figure has two obligations. Legibility alone is gameable by making the
# plate larger; a filled plate alone is gameable by cropping a tiny drawing.
# Both are measured on the delivered viewBox, not on the 960-unit stage.
FIGURE_FIT = {
    # Ink area / plate area. Cropping the attention figures raises this from
    # 0.54-0.66 to 0.86, so 0.75 separates a framed drawing from a padded one.
    "coverage_min": 0.75,
    # The largest of the four margins, over the plate's longer side. The 24-unit
    # framing margin lands at 3.0-3.5% on these drawings.
    "margin_ratio_max": 0.04,
    # The smallest tier, delivered at the narrowest band the page serves. The
    # drawing is composed for a band, so this floor is met by the composition
    # rather than by the page's width.
    "delivered_target_px": 7.0,
    # The floor is a rounded floor. A stage moves in 4-unit steps, which at the
    # narrowest band is 0.08px of delivered type, so a composition can sit a
    # hundredth below the target with no stage between it and the one that
    # clears it. Half a step is noise, not a defect; a full step is a defect,
    # and this tolerance is smaller than one.
    "delivered_tolerance_px": 0.05,

    # A figure title is a page heading in all but name: it has to read below
    # H2 and above H3. A plate is shown across its whole class, so the binding
    # number is the title's delivery at the class's *widest* band -- the
    # largest the reader ever sees it -- and the title tier is the largest one
    # whose widest delivery stays under this share of H2. The tiers step by two
    # units; each step moves the delivered title by about a pixel at the design
    # band, which is why the H3 floor is read with a half-step tolerance.
    "title_h2_ratio": 0.9,
    "title_tier_max": 24,
    # The node title is 12 units. A figure title two units above it is still
    # the largest type in the drawing rather than a second node label.
    "title_tier_floor": 14,
    "title_tier_step": 2,
    "title_floor_tolerance_px": 1.0,

    # Coverage reads the ink's bounding box, so it cannot see a hole the
    # drawing contains: two rows at the top and one at the bottom still fill
    # the plate. This is the tallest horizontal band inside the content that
    # nothing crosses, in stage units.
    #
    # Derived from the type, not picked: a node title is 12 units and its line
    # box is 1.25x that, so six lines is 90 units. A gap taller than six lines
    # of a node's own title is no longer row spacing; it reads as a missing
    # part of the drawing. Measured on the 24 plates the page serves, the
    # largest real band is 40 units (the strip above a bottom-pinned legend);
    # the 108-unit hole this rule exists to catch sits well above the limit.
    "empty_band_max": 90,
}

# A figure is composed for the band it will be shown at, and the composition
# changes with that band: a 320px column wraps rows a 660px column does not.
# One SVG therefore cannot serve the whole page, so each figure is emitted once
# per class and CSS shows the one that matches the viewport.
#
# The design band is the band at the *narrowest* viewport the class serves,
# because the type floor binds there: a composition that delivers 7px at its
# narrow end delivers more at the wide end, which is a floor being met, not a
# target being missed. `375` is the narrowest viewport a current phone reports;
# below it the column is narrower than any composition that holds the floor at
# a plate shape a reader would accept, and that is a different drawing, not a
# smaller number. The page's own reviewed set starts at 390.
# The classes are cut where the *band*, not the viewport, doubles less than a
# quarter: a plate composed at one end of its class is delivered 1.25x larger
# at the other, so no reader gets type twice the size another reader gets.
# `481-588` and `589-768` split the tablet range at the geometric mean of its
# bands (433..676 -> 541 at 589px of viewport), which is why there are four
# classes and not the three the page's own typography uses.
FIGURE_VARIANTS = (
    {"key": "narrow", "min_viewport": 375, "max_viewport": 480},
    {"key": "compact", "min_viewport": 481, "max_viewport": 588},
    {"key": "medium", "min_viewport": 589, "max_viewport": 768},
    {"key": "wide", "min_viewport": 769, "max_viewport": None},
)
FIGURE_VARIANT_KEYS = tuple(item["key"] for item in FIGURE_VARIANTS)

# The plate name used when a family cannot compose for a band at all: the
# drawing rides the authored stage and every class shows the same plate.
FIGURE_SINGLE_PLATE = "all"

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
