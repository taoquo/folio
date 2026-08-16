from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from math import ceil, cos, floor, log10, pi, sin
from typing import Any, Iterable

from .scene import (
    ResolvedScene,
    SceneBox,
    SceneCircle,
    SceneGroup,
    SceneAnnotation,
    SceneLine,
    ScenePath,
    ScenePolyline,
    SceneRect,
    SceneStyle,
    SceneText,
)
from .theme.folio import DEFAULT_FOLIO_THEME
from .typography.roles import TextRole, resolve_text_style
from .typography.measure import measure_text
from .v3_common import (
    common_payload_diagnostics,
    dimensions,
    finite_number,
    infer_language,
    object_list,
    require_no_errors,
    validate_object_fields,
    validate_item_strings,
    validate_resolved_scene,
    validate_unique_ids,
    wrap_text,
)
from .validation import DrawingDiagnostic


SUPPORTED_LOCALES = {"en-US", "en-GB", "zh-CN", "zh-TW"}

# Series keys sit in the right gutter. The canvas is 960 wide and the keys start
# at 844, so the text must fit inside 100px to keep ink inside the canvas.
SERIES_KEY_X = 844
SERIES_KEY_WIDTH = 100


def _series_key_primitives(label: str, top: int, color: str, theme) -> list[object]:
    """Right-gutter series key, wrapped so long labels never overflow the canvas."""
    lines = wrap_text(str(label), SERIES_KEY_WIDTH, 9, theme.serif, max_lines=2)
    return [
        SceneText(line, SERIES_KEY_X, top + index * 11, color, 9, theme.serif)
        for index, line in enumerate(lines)
    ]


@dataclass(frozen=True)
class ScalePlan:
    domain_min: float
    domain_max: float
    ticks: tuple[float, ...]
    include_zero: bool
    unit: str | None = None


@dataclass(frozen=True)
class ValueFormatPlan:
    precision: int | None = None
    compact: bool = True
    grouping: bool = False
    unit_position: str = "auto"


@dataclass(frozen=True)
class DataSemantic:
    kind: str
    title: str
    marks: tuple[dict[str, Any], ...]
    language: str
    locale: str
    source: str | None = None

    @property
    def nodes(self):
        return self.marks

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class BarPlan:
    kind: str
    title: str
    categories: tuple[str, ...]
    series: tuple[dict[str, Any], ...]
    scale: ScalePlan
    focus_series: str | None
    mode: str
    reference_lines: tuple[dict[str, Any], ...]
    annotations: tuple[dict[str, Any], ...]
    value_format: ValueFormatPlan
    width: int
    height: int
    language: str
    locale: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class LinePlan:
    kind: str
    title: str
    categories: tuple[str, ...]
    series: tuple[dict[str, Any], ...]
    scale: ScalePlan
    focus_series: str | None
    missing_policy: str
    x_scale: str
    reference_lines: tuple[dict[str, Any], ...]
    annotations: tuple[dict[str, Any], ...]
    value_format: ValueFormatPlan
    width: int
    height: int
    language: str
    locale: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DonutPlan:
    kind: str
    title: str
    segments: tuple[dict[str, Any], ...]
    total: float
    focus_segment: str | None
    unit: str | None
    width: int
    height: int
    language: str
    locale: str
    value_format: ValueFormatPlan
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CandlestickPlan:
    kind: str
    title: str
    periods: tuple[dict[str, Any], ...]
    scale: ScalePlan
    annotations: tuple[dict[str, Any], ...]
    value_format: ValueFormatPlan
    width: int
    height: int
    language: str
    locale: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class WaterfallPlan:
    kind: str
    title: str
    start: float
    contributions: tuple[dict[str, Any], ...]
    end: float
    scale: ScalePlan
    width: int
    height: int
    language: str
    locale: str
    value_format: ValueFormatPlan
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ChartLayout:
    plot: SceneBox
    scale: ScalePlan | None
    marks: dict[str, Any]
    x_positions: tuple[int, ...] = ()


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)


def _bar_id(series_id: str, category: str) -> str:
    token = sha256(category.encode("utf-8")).hexdigest()[:10]
    return f"bar:{series_id}:{token}"


def _point_id(series_id: str, category: str) -> str:
    token = sha256(category.encode("utf-8")).hexdigest()[:10]
    return f"point:{series_id}:{token}"


def _title(title: str, width: int) -> SceneText:
    theme = DEFAULT_FOLIO_THEME
    style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    return SceneText(title, width // 2, 40, style.color, style.size, style.family, "middle")


def nice_scale(values: Iterable[float], *, include_zero: bool, unit: str | None = None, tick_count: int = 5) -> ScalePlan:
    numbers = [float(value) for value in values]
    if not numbers:
        numbers = [0.0, 1.0]
    low, high = min(numbers), max(numbers)
    if include_zero:
        low, high = min(0.0, low), max(0.0, high)
    if low == high:
        padding = abs(low) * 0.1 or 1.0
        low -= padding
        high += padding
    rough = (high - low) / max(2, tick_count - 1)
    magnitude = 10 ** floor(log10(abs(rough)))
    normalized = rough / magnitude
    step = (1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10) * magnitude
    domain_min = floor(low / step) * step
    domain_max = ceil(high / step) * step
    ticks: list[float] = []
    value = domain_min
    while value <= domain_max + step * 0.01 and len(ticks) < 12:
        ticks.append(round(value, 10))
        value += step
    return ScalePlan(domain_min, domain_max, tuple(ticks), include_zero, unit)


def _y(value: float, scale: ScalePlan, plot: SceneBox) -> int:
    ratio = (float(value) - scale.domain_min) / (scale.domain_max - scale.domain_min)
    return _grid(plot.y + plot.h - ratio * plot.h)


def _format(
    value: float,
    unit: str | None = None,
    locale: str = "en-US",
    value_format: ValueFormatPlan | None = None,
) -> str:
    formatting = value_format or ValueFormatPlan()
    precision = formatting.precision
    if formatting.compact:
        digits = 1 if precision is None else precision
        if locale.startswith("zh") and abs(value) >= 100_000_000:
            text = f"{value / 100_000_000:.{digits}f}亿"
        elif locale.startswith("zh") and abs(value) >= 10_000:
            text = f"{value / 10_000:.{digits}f}万"
        elif abs(value) >= 1_000_000:
            text = f"{value / 1_000_000:.{digits}f}M"
        elif abs(value) >= 1_000:
            text = f"{value / 1_000:.{digits}f}K"
        elif precision is not None:
            text = f"{value:.{precision}f}"
        elif float(value).is_integer():
            text = str(int(value))
        else:
            text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        digits = precision if precision is not None else (0 if float(value).is_integer() else 2)
        text = f"{value:,.{digits}f}" if formatting.grouping else f"{value:.{digits}f}"
    position = formatting.unit_position
    if position == "prefix" or (position == "auto" and unit in {"$", "¥", "€", "£"}):
        return f"{unit or ''}{text}"
    return f"{text}{unit or ''}"


def _axes(
    plot: SceneBox,
    scale: ScalePlan,
    categories: tuple[str, ...] = (),
    locale: str = "en-US",
    category_positions: tuple[int, ...] = (),
    value_format: ValueFormatPlan | None = None,
) -> list[object]:
    theme = DEFAULT_FOLIO_THEME
    result: list[object] = []
    for index, tick in enumerate(scale.ticks):
        y = _y(tick, scale, plot)
        result.append(SceneLine(f"grid:{index}", (plot.x, y), (plot.x + plot.w, y), SceneStyle(stroke=theme.border, stroke_width=0.8)))
        result.append(SceneText(_format(tick, scale.unit, locale, value_format), plot.x - 12, y + 4, theme.stone, 8, theme.mono, "end"))
    result.append(SceneLine("axis:y", (plot.x, plot.y), (plot.x, plot.y + plot.h), SceneStyle(stroke=theme.olive, stroke_width=1)))
    result.append(SceneLine("axis:x", (plot.x, plot.y + plot.h), (plot.x + plot.w, plot.y + plot.h), SceneStyle(stroke=theme.olive, stroke_width=1)))
    if categories:
        if category_positions and len(category_positions) != len(categories):
            raise ValueError("category positions must match category count")
        for index, label in enumerate(categories):
            x = category_positions[index] if category_positions else _grid(plot.x + (index + 0.5) * plot.w / len(categories))
            result.append(SceneText(label, x, plot.y + plot.h + 24, theme.olive, 8, theme.mono, "middle"))
    return result


def _common_chart(
    payload: dict[str, Any],
    *,
    kind: str,
    extra_allowed: set[str],
    required: tuple[str, ...],
    code: str,
) -> list[DrawingDiagnostic]:
    diagnostics = common_payload_diagnostics(
        payload, kind=kind,
        allowed={"schema_version", "kind", "title", "unit", "locale", "source", "value_format", "width", "height", "language", *extra_allowed},
        required=("schema_version", "kind", "title", *required), code=code,
    )
    for field in ("unit", "locale", "source"):
        if payload.get(field) is not None and not isinstance(payload[field], str):
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{field} must be a string or null"))
    if isinstance(payload.get("unit"), str) and len(payload["unit"]) > 12:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "unit must contain at most 12 characters"))
    if payload.get("locale") is not None and payload.get("locale") not in SUPPORTED_LOCALES:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "locale must be one of en-US, en-GB, zh-CN, or zh-TW"))
    if isinstance(payload.get("source"), str) and len(payload["source"]) > 256:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "source must contain at most 256 characters"))
    if isinstance(payload.get("title"), str) and len(payload["title"].strip()) > 64:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "title must contain at most 64 characters"))
    if "value_format" in payload and payload["value_format"] is None:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "value_format must be an object"))
    else:
        _validate_value_format(payload.get("value_format"), diagnostics, code)
    if payload.get("width", 960) != 960 or payload.get("height", 540) != 540:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "data chart canvas must be exactly 960x540; use an output profile or host contract to resize"))
    return diagnostics


def _validate_value_format(value: Any, diagnostics: list[DrawingDiagnostic], code: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        diagnostics.append(DrawingDiagnostic("ERROR", code, "value_format must be an object"))
        return
    unknown = sorted(set(value) - {"precision", "compact", "grouping", "unit_position"})
    if unknown:
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"value_format has unknown field: {unknown[0]}"))
    precision = value.get("precision")
    if "precision" in value and (not isinstance(precision, int) or isinstance(precision, bool) or not 0 <= precision <= 4):
        diagnostics.append(DrawingDiagnostic("ERROR", code, "value_format.precision must be an integer from 0 to 4"))
    for field in ("compact", "grouping"):
        if field in value and not isinstance(value[field], bool):
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"value_format.{field} must be boolean"))
    if value.get("unit_position", "auto") not in {"auto", "prefix", "suffix"}:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "value_format.unit_position must be auto, prefix, or suffix"))


def _value_format(payload: dict[str, Any]) -> ValueFormatPlan:
    value = payload.get("value_format") or {}
    return ValueFormatPlan(
        value.get("precision"), value.get("compact", True),
        value.get("grouping", False), value.get("unit_position", "auto"),
    )


def _validate_text_budget(
    items: list[dict[str, Any]],
    fields: tuple[str, ...],
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> None:
    for item in items:
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and len(value.strip()) > 64:
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"{field} must contain at most 64 characters", str(item.get("id"))))


def _reference_lines(payload: dict[str, Any], diagnostics: list[DrawingDiagnostic], code: str) -> list[dict[str, Any]]:
    items = object_list(payload, "reference_lines", diagnostics, code)
    validate_object_fields(
        items, name="reference_lines", allowed={"id", "label", "value"},
        required=("id", "label", "value"), diagnostics=diagnostics, code=code,
    )
    validate_item_strings(items, ("label",), diagnostics=diagnostics, code=code)
    validate_unique_ids(items, name="reference line", diagnostics=diagnostics, code=code)
    if len(items) > 3:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "reference_lines supports at most 3 items"))
    for item in items:
        if not finite_number(item.get("value")):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "reference line value must be finite", str(item.get("id"))))
        if isinstance(item.get("label"), str) and len(item["label"].strip()) > 24:
            diagnostics.append(DrawingDiagnostic("ERROR", code, "reference line label must contain at most 24 characters", str(item.get("id"))))
    return items


def _mark_annotations(
    payload: dict[str, Any],
    *,
    allowed: set[str],
    required: tuple[str, ...],
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> list[dict[str, Any]]:
    items = object_list(payload, "annotations", diagnostics, code)
    validate_object_fields(
        items, name="annotations", allowed={"id", "text", *allowed},
        required=("id", "text", *required), diagnostics=diagnostics, code=code,
    )
    validate_item_strings(items, ("text",), diagnostics=diagnostics, code=code)
    validate_unique_ids(items, name="annotation", diagnostics=diagnostics, code=code)
    if len(items) > 3:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "annotations supports at most 3 items"))
    for item in items:
        text = item.get("text")
        if isinstance(text, str) and (len(text.strip()) > 48 or measure_text(text.strip(), 8, DEFAULT_FOLIO_THEME.serif) > 176):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "annotation text exceeds the bounded one-line label budget", str(item.get("id"))))
    return items


def _validate_reference_domain(items: list[dict[str, Any]], scale: ScalePlan, diagnostics: list[DrawingDiagnostic], code: str) -> None:
    for item in items:
        value = item.get("value")
        if finite_number(value) and not scale.domain_min <= float(value) <= scale.domain_max:
            diagnostics.append(DrawingDiagnostic("ERROR", code, "reference line must remain inside the chart data domain", str(item.get("id"))))


def _reference_primitives(items: tuple[dict[str, Any], ...], plot: SceneBox, scale: ScalePlan) -> tuple[list[object], list[str]]:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = []
    reading: list[str] = []
    used: list[int] = []
    rule_ys = [_y(float(item["value"]), scale, plot) for item in items]
    for item in items:
        item_id = f"reference:{item['id']}"
        y = _y(float(item["value"]), scale, plot)
        primitives.append(SceneLine(item_id, (plot.x, y), (plot.x + plot.w, y), SceneStyle(stroke=theme.stone, stroke_width=1, dash=(6, 4))))
        # Right-align the label inside the plot: the left edge collides with the y-axis ticks.
        # Then pick the first vertical slot that clears every rule and every label already placed,
        # so neither the dashes nor a neighbouring caption strikes through the text.
        def _clear(candidate: int) -> bool:
            # An 8pt label sits roughly between baseline-8 and baseline+2.
            top, bottom = candidate - 8, candidate + 2
            return (
                plot.y + 8 <= candidate <= plot.y + plot.h - 4
                and all(not top <= rule <= bottom for rule in rule_ys)
                and all(abs(candidate - taken) >= 12 for taken in used)
            )

        label_y = next(
            (_grid(y + offset) for offset in (16, -8, 28, -20, 40, -32) if _clear(_grid(y + offset))),
            _grid(y + 16),
        )
        used.append(label_y)
        primitives.append(SceneText(str(item["label"]), plot.x + plot.w - 8, label_y, theme.stone, 8, theme.mono, "end"))
        reading.append(item_id)
    return primitives, reading


def _overlap(left: SceneBox, right: SceneBox) -> bool:
    return not (
        left.x + left.w <= right.x or right.x + right.w <= left.x
        or left.y + left.h <= right.y or right.y + right.h <= left.y
    )


def _scene_annotations(
    items: tuple[dict[str, Any], ...],
    anchors: dict[str, tuple[int, int]],
    plot: SceneBox,
    obstacles: tuple[SceneBox, ...] = (),
) -> tuple[SceneAnnotation, ...]:
    theme = DEFAULT_FOLIO_THEME
    placed: list[SceneAnnotation] = []
    for item in items:
        target_id = str(item["target_id"])
        if target_id not in anchors:
            raise ValueError(f"annotation target has no resolved mark: {target_id}")
        raw_x, raw_y = anchors[target_id]
        anchor_x, anchor_y = _grid(raw_x), _grid(raw_y)
        width = max(96, min(192, _grid(measure_text(str(item["text"]), 8, theme.serif) + 20)))
        height = 40
        # Try the four cardinal offsets first, then walk further out vertically. A callout that
        # sits on top of a bar or candle hides the very number it explains, so data marks are
        # treated as obstacles when a clear slot exists.
        candidates = tuple(
            SceneBox(_grid(anchor_x + dx if dx > 0 else anchor_x - width + dx), _grid(anchor_y + dy), width, height)
            for dy in (-52, 12, 28, -72, -92, 52, -132, 92, -172, 132)
            for dx in (32, -32, 96, -96, 168, -168)
        )

        def _fits(candidate: SceneBox) -> bool:
            return (
                candidate.x >= plot.x and candidate.y >= plot.y
                and candidate.x + candidate.w <= plot.x + plot.w
                and candidate.y + candidate.h <= plot.y + plot.h
                and all(not _overlap(candidate, existing.box) for existing in placed)
            )

        box = next((c for c in candidates if _fits(c) and all(not _overlap(c, block) for block in obstacles)), None)
        if box is None:
            box = next((c for c in candidates if _fits(c)), None)
        if box is None:
            raise ValueError(f"annotation cannot be placed without overlap: {item['id']}")
        end_x = box.x if anchor_x < box.x else box.x + box.w
        end_y = _grid(box.y + box.h / 2)
        placed.append(SceneAnnotation(
            f"annotation:{item['id']}", box,
            SceneStyle(theme.ivory, theme.brand, 1, radius=4),
            SceneText(str(item["text"]), box.x + 8, box.y + 24, theme.near_black, 8, theme.serif),
            ((anchor_x, anchor_y), (end_x, anchor_y), (end_x, end_y)),
        ))
    return tuple(placed)


def compile_bar_payload(payload: dict[str, Any]):
    diagnostics = _common_chart(
        payload, kind="bar-chart",
        extra_allowed={"categories", "series", "focus_series", "order", "mode", "reference_lines", "annotations"},
        required=("categories", "series"), code="BC000",
    )
    categories = payload.get("categories")
    if not isinstance(categories, list) or not 1 <= len(categories) <= 8 or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 64 for item in categories):
        diagnostics.append(DrawingDiagnostic("ERROR", "BC001", "bar categories must contain 1-8 non-empty labels"))
        categories = []
    if len(categories) != len(set(categories)):
        diagnostics.append(DrawingDiagnostic("ERROR", "BC002", "bar categories must be unique"))
    series = object_list(payload, "series", diagnostics, "BC000")
    validate_object_fields(series, name="series", allowed={"id", "label", "values"}, required=("id", "label", "values"), diagnostics=diagnostics, code="BC000")
    validate_item_strings(series, ("label",), diagnostics=diagnostics, code="BC000")
    _validate_text_budget(series, ("id", "label"), diagnostics, "BC000")
    series_ids = validate_unique_ids(series, name="bar series", diagnostics=diagnostics, code="BC003")
    if not 1 <= len(series) <= 3:
        diagnostics.append(DrawingDiagnostic("ERROR", "BC004", "bar chart requires 1-3 series"))
    values: list[float] = []
    for item in series:
        item_values = item.get("values")
        if not isinstance(item_values, list) or len(item_values) != len(categories) or any(not finite_number(value) for value in item_values):
            diagnostics.append(DrawingDiagnostic("ERROR", "BC005", "series values must be finite and match category count", str(item.get("id"))))
        else:
            values.extend(float(value) for value in item_values)
    focus = payload.get("focus_series")
    if focus is not None and focus not in series_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "BC006", "focus_series references unknown series", str(focus)))
    order = payload.get("order", "input")
    if isinstance(order, list):
        if len(order) != len(categories) or len(set(order)) != len(order) or set(order) != set(categories):
            diagnostics.append(DrawingDiagnostic("ERROR", "BC007", "explicit bar order must list every category exactly once"))
    elif order not in {"input", "value"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "BC007", "bar order must be input, value, or an explicit category list"))
    mode = payload.get("mode", "grouped")
    if mode not in {"grouped", "stacked"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "BC009", "bar mode must be grouped or stacked"))
    reference_lines = _reference_lines(payload, diagnostics, "BC010")
    annotations = _mark_annotations(
        payload, allowed={"series", "category"}, required=("series", "category"),
        diagnostics=diagnostics, code="BC011",
    )
    annotation_targets: set[tuple[str, str]] = set()
    for item in annotations:
        target = (str(item.get("series")), str(item.get("category")))
        if target[0] not in series_ids or target[1] not in categories:
            diagnostics.append(DrawingDiagnostic("ERROR", "BC012", "bar annotation references an unknown series or category", str(item.get("id"))))
        if target in annotation_targets:
            diagnostics.append(DrawingDiagnostic("ERROR", "BC013", "bar annotations must target distinct marks", str(item.get("id"))))
        annotation_targets.add(target)
    require_no_errors("schema", diagnostics)

    if order == "value" and len(series) != 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "BC008", "value order requires a single series"))
        require_no_errors("schema", diagnostics)
    if order == "value":
        ordering = sorted(range(len(categories)), key=lambda index: (-float(series[0]["values"][index]), index))
        categories = [categories[index] for index in ordering]
        series = [{**item, "values": [item["values"][index] for index in ordering]} for item in series]
    elif isinstance(order, list):
        source_index = {category: index for index, category in enumerate(categories)}
        ordering = [source_index[category] for category in order]
        categories = list(order)
        series = [{**item, "values": [item["values"][index] for index in ordering]} for item in series]
    scale_values = values
    if mode == "stacked":
        scale_values = []
        for index in range(len(categories)):
            category_values = [float(item["values"][index]) for item in series]
            scale_values.extend((sum(value for value in category_values if value > 0), sum(value for value in category_values if value < 0)))
    scale = nice_scale(scale_values, include_zero=True, unit=payload.get("unit"))
    _validate_reference_domain(reference_lines, scale, diagnostics, "BC014")
    require_no_errors("schema", diagnostics)
    width, height = dimensions(payload)
    language = infer_language(payload["title"], [*categories, *(str(item["label"]) for item in series)], payload.get("language"))
    marks = tuple({"id": _bar_id(item["id"], category), "series": item["id"], "category": category, "value": float(item["values"][index])} for item in series for index, category in enumerate(categories))
    locale = str(payload.get("locale") or ("zh-CN" if language.startswith("zh") else "en-US"))
    semantic = DataSemantic("bar-chart", payload["title"], marks, language, locale, payload.get("source"))
    resolved_annotations = tuple({**item, "target_id": _bar_id(str(item["series"]), str(item["category"]))} for item in annotations)
    plan = BarPlan(
        "bar-chart", payload["title"], tuple(categories), tuple(series), scale, focus,
        mode, tuple(reference_lines), resolved_annotations, _value_format(payload),
        width, height, language, locale,
    )
    layout = _layout_bars(plan)
    scene = _resolve_bars(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_bars(plan: BarPlan) -> ChartLayout:
    plot = SceneBox(100, 80, 720, 340)
    baseline = _y(0, plan.scale, plot)
    group_width = plot.w / len(plan.categories)
    # V5: slimmer grouped bars keep editorial air and hold the solid-accent budget (VQ104).
    bar_width = max(12, min(56 if plan.mode == "stacked" else 32, _grid(
        group_width * 0.56 if plan.mode == "stacked" else (group_width - 24) / len(plan.series)
    )))
    marks: dict[str, SceneBox] = {}
    positive = [0.0] * len(plan.categories)
    negative = [0.0] * len(plan.categories)
    for series_index, item in enumerate(plan.series):
        for category_index, value in enumerate(item["values"]):
            center = plot.x + (category_index + 0.5) * group_width
            if plan.mode == "stacked":
                x = _grid(center - bar_width / 2)
                start = positive[category_index] if float(value) >= 0 else negative[category_index]
                end = start + float(value)
                if float(value) >= 0:
                    positive[category_index] = end
                else:
                    negative[category_index] = end
                start_y, end_y = _y(start, plan.scale, plot), _y(end, plan.scale, plot)
                marks[_bar_id(item["id"], plan.categories[category_index])] = SceneBox(x, min(start_y, end_y), max(8, bar_width - 4), max(1, abs(start_y - end_y)))
            else:
                x = _grid(center - len(plan.series) * bar_width / 2 + series_index * bar_width)
                value_y = _y(float(value), plan.scale, plot)
                marks[_bar_id(item["id"], plan.categories[category_index])] = SceneBox(x, min(value_y, baseline), max(8, bar_width - 4), max(1, abs(value_y - baseline)))
    return ChartLayout(plot, plan.scale, marks)


def _resolve_bars(plan: BarPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = _axes(layout.plot, plan.scale, plan.categories, plan.locale, value_format=plan.value_format)
    reference_primitives, reference_reading = _reference_primitives(plan.reference_lines, layout.plot, plan.scale)
    primitives.extend(reference_primitives)
    reading: list[str] = []
    # A dashed reference rule crossing a value label strikes the number through. Moving the label
    # further out would detach it from its bar, so it slides sideways instead and keeps the
    # vertical position that ties it to the bar top.
    rule_ys = [_y(float(item["value"]), plan.scale, layout.plot) for item in plan.reference_lines]
    value_label_boxes: list[SceneBox] = []

    def _struck(label_y: int) -> bool:
        return any(label_y - 8 <= rule <= label_y + 2 for rule in rule_ys)

    palette = (theme.olive, theme.stone, theme.neutral_mid)
    for series_index, item in enumerate(plan.series):
        color = theme.brand if item["id"] == plan.focus_series or (plan.focus_series is None and series_index == 0) else palette[min(series_index, 2)]
        for category_index, value in enumerate(item["values"]):
            mark_id = _bar_id(item["id"], plan.categories[category_index])
            box = layout.marks[mark_id]
            primitives.append(SceneRect(mark_id, box, SceneStyle(color, "none", radius=2)))
            if plan.mode == "grouped" and box.w >= 20:
                label_y = max(72, box.y - 8) if float(value) >= 0 else min(layout.plot.y + layout.plot.h - 4, box.y + box.h + 14)
                label_y = _grid(label_y)
                text_value = _format(float(value), plan.scale.unit, plan.locale, plan.value_format)
                label_w = max(24, int(measure_text(text_value, 8, theme.mono)))
                label_x = box.x + box.w // 2
                if _struck(label_y):
                    # Reference rules span the whole plot, so the label cannot step aside. Knock a
                    # parchment gap into the dashes instead and keep the label on top of its bar.
                    primitives.append(SceneRect(
                        f"{mark_id}:label-knockout",
                        SceneBox(label_x - label_w // 2 - 3, label_y - 10, label_w + 6, 13),
                        SceneStyle(theme.parchment, "none"),
                    ))
                primitives.append(SceneText(text_value, label_x, label_y, theme.near_black, 8, theme.mono, "middle"))
                value_label_boxes.append(SceneBox(label_x - label_w // 2, label_y - 10, label_w, 14))
            reading.append(mark_id)
        primitives.extend(_series_key_primitives(item["label"], 112 + series_index * 24, theme.brand if color == theme.brand else theme.near_black, theme))
    if plan.mode == "stacked":
        group_width = layout.plot.w / len(plan.categories)
        for category_index in range(len(plan.categories)):
            values = [float(item["values"][category_index]) for item in plan.series]
            positive = sum(value for value in values if value > 0)
            negative = sum(value for value in values if value < 0)
            x = _grid(layout.plot.x + (category_index + 0.5) * group_width)
            if positive:
                primitives.append(SceneText(
                    _format(positive, plan.scale.unit, plan.locale, plan.value_format),
                    x, max(72, _y(positive, plan.scale, layout.plot) - 8),
                    theme.near_black, 8, theme.mono, "middle",
                ))
            if negative:
                primitives.append(SceneText(
                    _format(negative, plan.scale.unit, plan.locale, plan.value_format),
                    x, min(layout.plot.y + layout.plot.h - 4, _y(negative, plan.scale, layout.plot) + 14),
                    theme.near_black, 8, theme.mono, "middle",
                ))
    anchors = {
        mark_id: (box.x + box.w // 2, box.y if next(float(value) for item in plan.series for index, value in enumerate(item["values"]) if _bar_id(item["id"], plan.categories[index]) == mark_id) >= 0 else box.y + box.h)
        for mark_id, box in layout.marks.items()
    }
    annotations = _scene_annotations(plan.annotations, anchors, layout.plot, tuple(layout.marks.values()) + tuple(value_label_boxes))
    description = _data_description(plan.title, ((item["label"], plan.categories, item["values"]) for item in plan.series), source)
    if plan.reference_lines:
        description += ". References: " + "; ".join(f"{item['label']} {item['value']}" for item in plan.reference_lines)
    if plan.annotations:
        description += ". Annotations: " + "; ".join(str(item["text"]) for item in plan.annotations)
    reading.extend(reference_reading)
    reading.extend(item.id for item in annotations)
    return ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), annotations, description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives))


def compile_line_payload(payload: dict[str, Any]):
    diagnostics = _common_chart(
        payload, kind="line-chart",
        extra_allowed={"categories", "series", "focus_series", "missing_policy", "x_scale", "reference_lines", "annotations"},
        required=("categories", "series"), code="LC000",
    )
    categories = payload.get("categories")
    if not isinstance(categories, list) or not 2 <= len(categories) <= 12 or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 64 for item in categories):
        diagnostics.append(DrawingDiagnostic("ERROR", "LC001", "line categories must contain 2-12 labels"))
        categories = []
    if len(categories) != len(set(categories)):
        diagnostics.append(DrawingDiagnostic("ERROR", "LC011", "line categories must be unique"))
    series = object_list(payload, "series", diagnostics, "LC000")
    validate_object_fields(series, name="series", allowed={"id", "label", "values"}, required=("id", "label", "values"), diagnostics=diagnostics, code="LC000")
    validate_item_strings(series, ("label",), diagnostics=diagnostics, code="LC000")
    _validate_text_budget(series, ("id", "label"), diagnostics, "LC000")
    series_ids = validate_unique_ids(series, name="line series", diagnostics=diagnostics, code="LC002")
    if not 1 <= len(series) <= 3:
        diagnostics.append(DrawingDiagnostic("ERROR", "LC003", "line chart requires 1-3 series"))
    missing_policy = payload.get("missing_policy", "gap")
    if missing_policy not in {"gap", "zero", "carry-forward", "error"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "LC004", "invalid missing_value policy"))
    values: list[float] = []
    normalized_series: list[dict[str, Any]] = []
    for item in series:
        item_values = item.get("values")
        if not isinstance(item_values, list) or len(item_values) != len(categories) or any(value is not None and not finite_number(value) for value in item_values):
            diagnostics.append(DrawingDiagnostic("ERROR", "LC005", "line values must be finite/null and match category count", str(item.get("id"))))
            continue
        if missing_policy == "error" and any(value is None for value in item_values):
            diagnostics.append(DrawingDiagnostic("ERROR", "LC006", "missing values are not allowed by policy", str(item.get("id"))))
        resolved: list[float | None] = []
        previous: float | None = None
        for value in item_values:
            if value is None and missing_policy == "zero":
                value = 0.0
            elif value is None and missing_policy == "carry-forward":
                value = previous
            resolved.append(float(value) if value is not None else None)
            if value is not None:
                previous = float(value)
                values.append(float(value))
        normalized_series.append({**item, "values": resolved})
    focus = payload.get("focus_series")
    if focus is not None and focus not in series_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "LC007", "focus_series references unknown series", str(focus)))
    if payload.get("x_scale", "ordinal") not in {"ordinal", "time"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "LC008", "x_scale must be ordinal or time"))
    if payload.get("x_scale") == "time":
        try:
            parsed_categories = [date.fromisoformat(value) for value in categories]
        except ValueError:
            diagnostics.append(DrawingDiagnostic("ERROR", "LC009", "time scale categories must use ISO YYYY-MM-DD dates"))
        else:
            if parsed_categories != sorted(parsed_categories) or len(set(parsed_categories)) != len(parsed_categories):
                diagnostics.append(DrawingDiagnostic("ERROR", "LC010", "time scale categories must be unique and ascending"))
    reference_lines = _reference_lines(payload, diagnostics, "LC012")
    annotations = _mark_annotations(
        payload, allowed={"series", "category"}, required=("series", "category"),
        diagnostics=diagnostics, code="LC013",
    )
    annotation_targets: set[tuple[str, str]] = set()
    for item in annotations:
        target = (str(item.get("series")), str(item.get("category")))
        if target[0] not in series_ids or target[1] not in categories:
            diagnostics.append(DrawingDiagnostic("ERROR", "LC014", "line annotation references an unknown series or category", str(item.get("id"))))
        elif item_values := next((series_item.get("values") for series_item in normalized_series if series_item.get("id") == target[0]), None):
            category_index = categories.index(target[1])
            if item_values[category_index] is None:
                diagnostics.append(DrawingDiagnostic("ERROR", "LC015", "line annotation cannot target an unresolved missing value", str(item.get("id"))))
        if target in annotation_targets:
            diagnostics.append(DrawingDiagnostic("ERROR", "LC016", "line annotations must target distinct marks", str(item.get("id"))))
        annotation_targets.add(target)
    require_no_errors("schema", diagnostics)

    scale = nice_scale(values, include_zero=False, unit=payload.get("unit"))
    _validate_reference_domain(reference_lines, scale, diagnostics, "LC017")
    require_no_errors("schema", diagnostics)
    width, height = dimensions(payload)
    language = infer_language(payload["title"], [*categories, *(str(item["label"]) for item in normalized_series)], payload.get("language"))
    marks = tuple({"id": _point_id(item["id"], categories[index]), "series": item["id"], "category": categories[index], "value": value} for item in normalized_series for index, value in enumerate(item["values"]) if value is not None)
    locale = str(payload.get("locale") or ("zh-CN" if language.startswith("zh") else "en-US"))
    semantic = DataSemantic("line-chart", payload["title"], marks, language, locale, payload.get("source"))
    resolved_annotations = tuple({**item, "target_id": _point_id(str(item["series"]), str(item["category"]))} for item in annotations)
    plan = LinePlan(
        "line-chart", payload["title"], tuple(categories), tuple(normalized_series), scale,
        focus, missing_policy, payload.get("x_scale", "ordinal"), tuple(reference_lines),
        resolved_annotations, _value_format(payload), width, height, language, locale,
    )
    layout = _layout_lines(plan)
    scene = _resolve_lines(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_lines(plan: LinePlan) -> ChartLayout:
    plot = SceneBox(100, 80, 720, 340)
    if plan.x_scale == "time":
        parsed = [date.fromisoformat(value) for value in plan.categories]
        span = max(1, (parsed[-1] - parsed[0]).days)
        x_values = [_grid(plot.x + (value - parsed[0]).days / span * plot.w) for value in parsed]
    else:
        x_values = [_grid(plot.x + index * plot.w / max(1, len(plan.categories) - 1)) for index in range(len(plan.categories))]
    marks: dict[str, tuple[int, int]] = {}
    for item in plan.series:
        for index, value in enumerate(item["values"]):
            if value is None:
                continue
            x = x_values[index]
            marks[_point_id(item["id"], plan.categories[index])] = (x, _y(value, plan.scale, plot))
    return ChartLayout(plot, plan.scale, marks, tuple(x_values))


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _resolve_lines(plan: LinePlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = _axes(layout.plot, plan.scale, plan.categories, plan.locale, layout.x_positions, plan.value_format)
    reference_primitives, reference_reading = _reference_primitives(plan.reference_lines, layout.plot, plan.scale)
    primitives.extend(reference_primitives)
    reading: list[str] = []
    # Line series are drawn at 1.6px, so every palette entry must clear the WCAG
    # non-text contrast bar on its own. Bars carry a labeled key instead.
    palette = (theme.olive, theme.stone, theme.neutral_deep)
    for series_index, item in enumerate(plan.series):
        color = theme.brand if item["id"] == plan.focus_series or (plan.focus_series is None and series_index == 0) else palette[min(series_index, 2)]
        dash = (6, 4) if series_index == 2 else (4, 3) if series_index == 1 else ()
        run: list[tuple[int, int]] = []
        run_index = 0
        for index, value in enumerate(item["values"]):
            if value is None:
                if len(run) >= 2:
                    primitives.append(ScenePolyline(f"line:{item['id']}:{run_index}", tuple(run), SceneStyle("none", color, 1.6, dash=dash)))
                    run_index += 1
                run = []
                continue
            mark_id = _point_id(item["id"], plan.categories[index])
            point = layout.marks[mark_id]
            run.append(point)
            primitives.append(SceneCircle(mark_id, point[0], point[1], 4, SceneStyle(theme.parchment, color, 1.4)))
            reading.append(mark_id)
        if len(run) >= 2:
            primitives.append(ScenePolyline(f"line:{item['id']}:{run_index}", tuple(run), SceneStyle("none", color, 1.6, dash=dash)))
        primitives.extend(_series_key_primitives(item["label"], 112 + series_index * 24, theme.brand if color == theme.brand else theme.near_black, theme))
    # Reference rules span the plot, so a callout box that lands on one gets a line through its
    # middle. Treat each rule and each plotted point as an obstacle.
    rule_bands = tuple(
        SceneBox(layout.plot.x, _y(float(item["value"]), plan.scale, layout.plot) - 3, layout.plot.w, 6)
        for item in plan.reference_lines
    )
    point_bands = tuple(SceneBox(x - 6, y - 6, 12, 12) for x, y in layout.marks.values())
    annotations = _scene_annotations(plan.annotations, layout.marks, layout.plot, rule_bands + point_bands)
    description = _data_description(plan.title, ((item["label"], plan.categories, item["values"]) for item in plan.series), source)
    if plan.reference_lines:
        description += ". References: " + "; ".join(f"{item['label']} {item['value']}" for item in plan.reference_lines)
    if plan.annotations:
        description += ". Annotations: " + "; ".join(str(item["text"]) for item in plan.annotations)
    reading.extend(reference_reading)
    reading.extend(item.id for item in annotations)
    return ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), annotations, description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives))


def compile_donut_payload(payload: dict[str, Any]):
    diagnostics = _common_chart(payload, kind="donut-chart", extra_allowed={"segments", "focus_segment", "percent_total", "tolerance"}, required=("segments",), code="DN000")
    segments = object_list(payload, "segments", diagnostics, "DN000")
    validate_object_fields(segments, name="segments", allowed={"id", "label", "value"}, required=("id", "label", "value"), diagnostics=diagnostics, code="DN000")
    validate_item_strings(segments, ("label",), diagnostics=diagnostics, code="DN000")
    _validate_text_budget(segments, ("id", "label"), diagnostics, "DN000")
    segment_ids = validate_unique_ids(segments, name="donut segment", diagnostics=diagnostics, code="DN001")
    if not 2 <= len(segments) <= 6:
        diagnostics.append(DrawingDiagnostic("ERROR", "DN002", "donut requires 2-6 segments"))
    values: list[float] = []
    for item in segments:
        if not finite_number(item.get("value")) or float(item["value"]) <= 0:
            diagnostics.append(DrawingDiagnostic("ERROR", "DN003", "donut values must be positive finite numbers", str(item.get("id"))))
        else:
            values.append(float(item["value"]))
    total = sum(values)
    if total <= 0:
        diagnostics.append(DrawingDiagnostic("ERROR", "DN004", "donut total must be positive"))
    tolerance = payload.get("tolerance", 0.01)
    if not finite_number(tolerance) or float(tolerance) < 0:
        diagnostics.append(DrawingDiagnostic("ERROR", "DN005", "tolerance must be a non-negative finite number"))
    if payload.get("percent_total") and abs(total - 100) > float(tolerance):
        diagnostics.append(DrawingDiagnostic("ERROR", "DN006", "percent donut must total 100 within tolerance"))
    focus = payload.get("focus_segment")
    if focus is not None and focus not in segment_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "DN007", "focus_segment references unknown segment", str(focus)))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in segments), payload.get("language"))
    marks = tuple({"id": f"segment:{item['id']}", "label": item["label"], "value": float(item["value"])} for item in segments)
    locale = str(payload.get("locale") or ("zh-CN" if language.startswith("zh") else "en-US"))
    semantic = DataSemantic("donut-chart", payload["title"], marks, language, locale, payload.get("source"))
    plan = DonutPlan("donut-chart", payload["title"], tuple(segments), total, focus, payload.get("unit"), width, height, language, locale, _value_format(payload))
    layout = _layout_donut(plan)
    scene = _resolve_donut(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_donut(plan: DonutPlan) -> ChartLayout:
    angles: dict[str, tuple[float, float]] = {}
    start = -90.0
    for item in plan.segments:
        sweep = float(item["value"]) / plan.total * 360
        angles[f"segment:{item['id']}"] = (start, start + sweep)
        start += sweep
    return ChartLayout(SceneBox(60, 104, 380, 380), None, angles)


def _donut_path(cx: int, cy: int, outer: int, inner: int, start: float, end: float) -> str:
    start_rad, end_rad = start * pi / 180, end * pi / 180
    outer_start = (cx + outer * cos(start_rad), cy + outer * sin(start_rad))
    outer_end = (cx + outer * cos(end_rad), cy + outer * sin(end_rad))
    inner_end = (cx + inner * cos(end_rad), cy + inner * sin(end_rad))
    inner_start = (cx + inner * cos(start_rad), cy + inner * sin(start_rad))
    large = 1 if end - start > 180 else 0
    return (
        f"M {outer_start[0]:.3f} {outer_start[1]:.3f} "
        f"A {outer} {outer} 0 {large} 1 {outer_end[0]:.3f} {outer_end[1]:.3f} "
        f"L {inner_end[0]:.3f} {inner_end[1]:.3f} "
        f"A {inner} {inner} 0 {large} 0 {inner_start[0]:.3f} {inner_start[1]:.3f} Z"
    )


def _resolve_donut(plan: DonutPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    palette = (theme.olive, theme.stone, theme.neutral_mid, theme.neutral_light, theme.brand_tint, theme.neutral_deep)
    primitives: list[object] = []
    reading: list[str] = []
    # The donut sits left of a right-hand legend column. Both are pushed toward the canvas edges so
    # the chart fills its frame instead of floating in the middle third.
    # outer stays <= 192 so a single 50% brand segment keeps its bounding box under the VQ104 budget.
    cx, cy, outer, inner = 250, 296, 190, 108
    legend_step = 72 if len(plan.segments) <= 5 else 60
    legend_top = max(120, int(cy - (len(plan.segments) - 1) * legend_step / 2) - 12)
    for index, item in enumerate(plan.segments):
        mark_id = f"segment:{item['id']}"
        start, end = layout.marks[mark_id]
        color = theme.brand if item["id"] == plan.focus_segment or (plan.focus_segment is None and index == 0) else palette[index]
        primitives.append(ScenePath(mark_id, _donut_path(cx, cy, outer, inner, start, end), SceneStyle(color, theme.parchment, 1)))
        percent = float(item["value"]) / plan.total * 100
        row = legend_top + index * legend_step
        primitives.append(SceneRect(f"legend-mark:{item['id']}", SceneBox(596, row, 12, 12), SceneStyle(color, "none", radius=2)))
        primitives.append(SceneText(item["label"], 624, row + 12, theme.near_black, 11, theme.serif))
        value_text = _format(float(item['value']), plan.unit, plan.locale, plan.value_format)
        # When the unit is already a percentage the formatted value and the computed share say the
        # same thing, so only append the share for non-percentage units.
        legend_text = value_text if (plan.unit or "").strip() == "%" else f"{value_text} · {percent:.1f}%"
        primitives.append(SceneText(legend_text, 624, row + 30, theme.stone, 9, theme.mono))
        reading.append(mark_id)
    primitives.append(SceneText(_format(plan.total, plan.unit, plan.locale, plan.value_format), cx, cy - 2, theme.brand, 22, theme.serif, "middle", weight="500"))
    primitives.append(SceneText("TOTAL", cx, cy + 26, theme.stone, 9, theme.mono, "middle", tracking=0.16))
    description = "Donut " + plan.title + ". " + "; ".join(f"{item['label']}: {item['value']}" for item in plan.segments) + (f". Source: {source}" if source else "")
    return ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives))

def compile_candlestick_payload(payload: dict[str, Any]):
    diagnostics = _common_chart(payload, kind="candlestick", extra_allowed={"periods", "annotations"}, required=("periods",), code="CS000")
    periods = object_list(payload, "periods", diagnostics, "CS000")
    validate_object_fields(periods, name="periods", allowed={"id", "date", "open", "high", "low", "close"}, required=("id", "date", "open", "high", "low", "close"), diagnostics=diagnostics, code="CS000")
    validate_unique_ids(periods, name="candlestick period", diagnostics=diagnostics, code="CS001")
    _validate_text_budget(periods, ("id", "date"), diagnostics, "CS001")
    if not 1 <= len(periods) <= 30:
        diagnostics.append(DrawingDiagnostic("ERROR", "CS002", "candlestick requires 1-30 periods"))
    parsed_dates: list[date] = []
    prices: list[float] = []
    for item in periods:
        try:
            parsed_dates.append(date.fromisoformat(str(item.get("date"))))
        except ValueError:
            diagnostics.append(DrawingDiagnostic("ERROR", "CS003", "period date must be ISO YYYY-MM-DD", str(item.get("id"))))
        fields = [item.get(name) for name in ("open", "high", "low", "close")]
        if any(not finite_number(value) for value in fields):
            diagnostics.append(DrawingDiagnostic("ERROR", "CS004", "OHLC values must be finite", str(item.get("id"))))
            continue
        open_value, high, low, close = (float(value) for value in fields)
        if not low <= open_value <= high or not low <= close <= high:
            diagnostics.append(DrawingDiagnostic("ERROR", "CS005", "candlestick requires low <= open/close <= high", str(item.get("id"))))
        prices.extend((low, high))
    if parsed_dates and (parsed_dates != sorted(parsed_dates) or len(set(parsed_dates)) != len(parsed_dates)):
        diagnostics.append(DrawingDiagnostic("ERROR", "CS006", "candlestick periods must be unique and ascending"))
    annotations = _mark_annotations(
        payload, allowed={"period", "field"}, required=("period",),
        diagnostics=diagnostics, code="CS007",
    )
    period_ids = {str(item.get("id")) for item in periods}
    annotation_targets: set[tuple[str, str]] = set()
    for item in annotations:
        field = item.get("field", "close")
        target = (str(item.get("period")), str(field))
        if target[0] not in period_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "CS008", "candlestick annotation references an unknown period", str(item.get("id"))))
        if field not in {"open", "high", "low", "close"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "CS009", "candlestick annotation field must be open, high, low, or close", str(item.get("id"))))
        if target in annotation_targets:
            diagnostics.append(DrawingDiagnostic("ERROR", "CS010", "candlestick annotations must target distinct period fields", str(item.get("id"))))
        annotation_targets.add(target)
    require_no_errors("schema", diagnostics)

    scale = nice_scale(prices, include_zero=False, unit=payload.get("unit"))
    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["date"]) for item in periods), payload.get("language"))
    marks = tuple({"id": f"candle:{item['id']}", **item} for item in periods)
    locale = str(payload.get("locale") or ("zh-CN" if language.startswith("zh") else "en-US"))
    semantic = DataSemantic("candlestick", payload["title"], marks, language, locale, payload.get("source"))
    resolved_annotations = tuple({
        **item,
        "field": item.get("field", "close"),
        "target_id": f"candle:{item['period']}:{item.get('field', 'close')}",
    } for item in annotations)
    plan = CandlestickPlan("candlestick", payload["title"], tuple(periods), scale, resolved_annotations, _value_format(payload), width, height, language, locale)
    layout = _layout_candles(plan)
    scene = _resolve_candles(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_candles(plan: CandlestickPlan) -> ChartLayout:
    plot = SceneBox(100, 80, 720, 340)
    parsed = [date.fromisoformat(str(item["date"])) for item in plan.periods]
    span = max(1, (parsed[-1] - parsed[0]).days) if len(parsed) > 1 else 1
    inner_left, inner_width = plot.x + 12, plot.w - 24
    x_values = [
        _grid(inner_left + ((item_date - parsed[0]).days / span if len(parsed) > 1 else 0.5) * inner_width)
        for item_date in parsed
    ]
    gaps = [right - left for left, right in zip(x_values, x_values[1:]) if right > left]
    body_width = max(8, min(20, _grid((min(gaps) if gaps else 40) * 0.45)))
    marks: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(plan.periods):
        x = x_values[index]
        open_y, close_y = _y(float(item["open"]), plan.scale, plot), _y(float(item["close"]), plan.scale, plot)
        marks[f"candle:{item['id']}"] = {
            "x": x,
            "high_y": _y(float(item["high"]), plan.scale, plot),
            "low_y": _y(float(item["low"]), plan.scale, plot),
            "body": SceneBox(x - body_width // 2, min(open_y, close_y), body_width, max(2, abs(open_y - close_y))),
        }
    return ChartLayout(plot, plan.scale, marks)


def _resolve_candles(plan: CandlestickPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = _axes(layout.plot, plan.scale, locale=plan.locale, value_format=plan.value_format)
    reading: list[str] = []
    label_every = max(1, ceil(len(plan.periods) / 6))
    for index, item in enumerate(plan.periods):
        mark_id = f"candle:{item['id']}"
        mark = layout.marks[mark_id]
        up = float(item["close"]) >= float(item["open"])
        color = theme.near_black if up else theme.stone
        children = (
            SceneLine(f"wick:{item['id']}", (mark["x"], mark["high_y"]), (mark["x"], mark["low_y"]), SceneStyle(stroke=color, stroke_width=1.2)),
            SceneRect(f"body:{item['id']}", mark["body"], SceneStyle(color if up else theme.parchment, color, 1.2, radius=1)),
        )
        primitives.append(SceneGroup(mark_id, children))
        if index % label_every == 0 or index == len(plan.periods) - 1:
            primitives.append(SceneText(item["date"], mark["x"], layout.plot.y + layout.plot.h + 24, theme.stone, 8, theme.mono, "middle"))
        reading.append(mark_id)
    period_by_id = {str(item["id"]): item for item in plan.periods}
    anchors = {
        str(item["target_id"]): (
            layout.marks[f"candle:{item['period']}"]["x"],
            _y(float(period_by_id[str(item["period"])][str(item["field"])]), plan.scale, layout.plot),
        )
        for item in plan.annotations
    }
    candle_bands = tuple(
        SceneBox(mark["body"].x, min(mark["high_y"], mark["low_y"]), mark["body"].w, abs(mark["high_y"] - mark["low_y"]) or 1)
        for mark in layout.marks.values()
    )
    annotations = _scene_annotations(plan.annotations, anchors, layout.plot, candle_bands)
    description = "Candlestick " + plan.title + ". " + "; ".join(f"{item['date']} O {item['open']} H {item['high']} L {item['low']} C {item['close']}" for item in plan.periods) + (f". Source: {source}" if source else "")
    if plan.annotations:
        description += ". Annotations: " + "; ".join(str(item["text"]) for item in plan.annotations)
    reading.extend(item.id for item in annotations)
    return ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), annotations, description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives))


def compile_waterfall_payload(payload: dict[str, Any]):
    diagnostics = _common_chart(payload, kind="waterfall", extra_allowed={"start", "contributions", "end", "tolerance"}, required=("start", "contributions"), code="WF000")
    if not finite_number(payload.get("start")):
        diagnostics.append(DrawingDiagnostic("ERROR", "WF001", "waterfall start must be finite"))
    contributions = object_list(payload, "contributions", diagnostics, "WF000")
    validate_object_fields(contributions, name="contributions", allowed={"id", "label", "value", "kind"}, required=("id", "label", "value"), diagnostics=diagnostics, code="WF000")
    validate_item_strings(contributions, ("label",), diagnostics=diagnostics, code="WF000")
    _validate_text_budget(contributions, ("id", "label"), diagnostics, "WF000")
    validate_unique_ids(contributions, name="waterfall contribution", diagnostics=diagnostics, code="WF002")
    if not 1 <= len(contributions) <= 8:
        diagnostics.append(DrawingDiagnostic("ERROR", "WF003", "waterfall requires 1-8 contributions"))
    for item in contributions:
        if not finite_number(item.get("value")):
            diagnostics.append(DrawingDiagnostic("ERROR", "WF004", "waterfall contributions must be finite", str(item.get("id"))))
        if item.get("kind", "delta") not in {"delta", "subtotal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "WF007", "waterfall contribution kind must be delta or subtotal", str(item.get("id"))))
    tolerance = payload.get("tolerance", 0.01)
    if not finite_number(tolerance) or float(tolerance) < 0:
        diagnostics.append(DrawingDiagnostic("ERROR", "WF005", "waterfall tolerance must be non-negative"))
    valid_start = finite_number(payload.get("start"))
    valid_tolerance = finite_number(tolerance) and float(tolerance) >= 0
    calculated = None
    if valid_start:
        calculated = float(payload["start"])
        for item in contributions:
            if not finite_number(item.get("value")):
                continue
            if item.get("kind", "delta") == "subtotal":
                if valid_tolerance and abs(float(item["value"]) - calculated) > float(tolerance):
                    diagnostics.append(DrawingDiagnostic("ERROR", "WF008", "waterfall subtotal does not match the running total", str(item.get("id"))))
            else:
                calculated += float(item["value"])
    end = payload.get("end", calculated)
    if calculated is not None and valid_tolerance:
        if not finite_number(end) or abs(float(end) - calculated) > float(tolerance):
            diagnostics.append(DrawingDiagnostic("ERROR", "WF006", "displayed end total does not match calculated total"))
    require_no_errors("schema", diagnostics)

    running = float(payload["start"])
    levels = [0.0, running]
    for item in contributions:
        if item.get("kind", "delta") == "delta":
            running += float(item["value"])
        levels.append(running)
    scale = nice_scale(levels, include_zero=True, unit=payload.get("unit"))
    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in contributions), payload.get("language"))
    marks = ({"id": "waterfall:start", "label": "Start", "value": float(payload["start"]), "kind": "total"}, *({"id": f"waterfall:{item['id']}", "kind": item.get("kind", "delta"), **item} for item in contributions), {"id": "waterfall:end", "label": "End", "value": float(end), "kind": "total"})
    locale = str(payload.get("locale") or ("zh-CN" if language.startswith("zh") else "en-US"))
    semantic = DataSemantic("waterfall", payload["title"], tuple(marks), language, locale, payload.get("source"))
    plan = WaterfallPlan("waterfall", payload["title"], float(payload["start"]), tuple(contributions), float(end), scale, width, height, language, locale, _value_format(payload))
    layout = _layout_waterfall(plan)
    scene = _resolve_waterfall(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_waterfall(plan: WaterfallPlan) -> ChartLayout:
    plot = SceneBox(100, 80, 720, 340)
    count = len(plan.contributions) + 2
    step = plot.w / count
    bar_width = max(24, min(56, _grid(step * 0.56)))
    marks: dict[str, dict[str, Any]] = {}
    baseline = _y(0, plan.scale, plot)
    start_y = _y(plan.start, plan.scale, plot)
    marks["waterfall:start"] = {"box": SceneBox(_grid(plot.x + step * 0.22), min(start_y, baseline), bar_width, max(2, abs(start_y - baseline))), "from": 0.0, "to": plan.start}
    running = plan.start
    for index, item in enumerate(plan.contributions, start=1):
        if item.get("kind", "delta") == "subtotal":
            next_value = running
            value_y = _y(next_value, plan.scale, plot)
            marks[f"waterfall:{item['id']}"] = {
                "box": SceneBox(_grid(plot.x + index * step + step * 0.22), min(value_y, baseline), bar_width, max(2, abs(value_y - baseline))),
                "from": 0.0, "to": next_value,
            }
        else:
            next_value = running + float(item["value"])
            top, bottom = _y(max(running, next_value), plan.scale, plot), _y(min(running, next_value), plan.scale, plot)
            marks[f"waterfall:{item['id']}"] = {"box": SceneBox(_grid(plot.x + index * step + step * 0.22), top, bar_width, max(2, bottom - top)), "from": running, "to": next_value}
            running = next_value
    end_y = _y(plan.end, plan.scale, plot)
    marks["waterfall:end"] = {"box": SceneBox(_grid(plot.x + (count - 1) * step + step * 0.22), min(end_y, baseline), bar_width, max(2, abs(end_y - baseline))), "from": 0.0, "to": plan.end}
    return ChartLayout(plot, plan.scale, marks)


def _resolve_waterfall(plan: WaterfallPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = _axes(layout.plot, plan.scale, locale=plan.locale, value_format=plan.value_format)
    reading: list[str] = []
    step_width = layout.plot.w / (len(plan.contributions) + 2)
    entries = [
        ("waterfall:start", "Start", plan.start, "total"),
        *((
            f"waterfall:{item['id']}", item["label"], float(item["value"]),
            "subtotal" if item.get("kind", "delta") == "subtotal" else "positive" if float(item["value"]) >= 0 else "negative",
        ) for item in plan.contributions),
        ("waterfall:end", "End", plan.end, "total"),
    ]
    for index, (mark_id, label, value, role) in enumerate(entries):
        mark = layout.marks[mark_id]
        color = (
            theme.brand if mark_id == "waterfall:end"
            else theme.near_black if role in {"total", "subtotal"}
            else theme.olive if role == "positive"
            else theme.stone
        )
        primitives.append(SceneRect(mark_id, mark["box"], SceneStyle(color, "none", radius=2)))
        # Category labels get one column of room each. Wrap to two lines instead of letting long
        # phrases such as "Invited a teammate" collide with their neighbours.
        center = mark["box"].x + mark["box"].w // 2
        for line_index, line in enumerate(wrap_text(label, max(48, int(step_width) - 8), 8, theme.mono, max_lines=2)):
            primitives.append(SceneText(line, center, layout.plot.y + layout.plot.h + 24 + line_index * 12, theme.olive, 8, theme.mono, "middle"))
        primitives.append(SceneText(_format(value, plan.scale.unit, plan.locale, plan.value_format), mark["box"].x + mark["box"].w // 2, max(72, mark["box"].y - 8), theme.near_black, 8, theme.mono, "middle"))
        if index < len(entries) - 1:
            next_mark = layout.marks[entries[index + 1][0]]
            level_y = _y(mark["to"], plan.scale, layout.plot)
            primitives.append(SceneLine(f"connector:{index}", (mark["box"].x + mark["box"].w, level_y), (next_mark["box"].x, level_y), SceneStyle(stroke=theme.neutral_mid, stroke_width=0.8, dash=(4, 3))))
        reading.append(mark_id)
    description = f"Waterfall {plan.title}. Start {plan.start}; " + "; ".join(f"{item['label']} {item['value']}" for item in plan.contributions) + f"; end {plan.end}" + (f". Source: {source}" if source else "")
    return ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives))


def _data_description(title: str, series: Iterable[tuple[str, Iterable[str], Iterable[Any]]], source: str | None) -> str:
    parts = []
    for label, categories, values in series:
        parts.append(label + ": " + ", ".join(f"{category} {value if value is not None else 'missing'}" for category, value in zip(categories, values)))
    return title + ". " + "; ".join(parts) + (f". Source: {source}" if source else "")


SCATTER_PLOT = SceneBox(104, 88, 656, 344)
SCATTER_LEGEND_X = 792
SCATTER_LEGEND_WIDTH = 152


@dataclass(frozen=True)
class ScatterPlan:
    kind: str
    title: str
    points: tuple[dict[str, Any], ...]
    x_axis: dict[str, Any]
    y_axis: dict[str, Any]
    x_scale: ScalePlan
    y_scale: ScalePlan
    focus_series: str | None
    value_format: ValueFormatPlan
    width: int
    height: int
    language: str
    locale: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


def compile_scatter_payload(payload: dict[str, Any]):
    code = "SC000"
    diagnostics = _common_chart(
        payload, kind="scatter",
        extra_allowed={"points", "x_axis", "y_axis", "focus"},
        required=("points", "x_axis", "y_axis"), code=code,
    )
    points = object_list(payload, "points", diagnostics, code)
    validate_object_fields(points, name="points", allowed={"id", "label", "x", "y", "emphasis"}, required=("id", "label", "x", "y"), diagnostics=diagnostics, code=code)
    validate_item_strings(points, ("label",), diagnostics=diagnostics, code=code)
    point_ids = validate_unique_ids(points, name="scatter point", diagnostics=diagnostics, code=code)
    _validate_text_budget(points, ("label",), diagnostics, code)
    if not 3 <= len(points) <= 14:
        diagnostics.append(DrawingDiagnostic("ERROR", "SC001", "scatter requires between three and fourteen points"))
    for item in points:
        for field in ("x", "y"):
            if not finite_number(item.get(field)):
                diagnostics.append(DrawingDiagnostic("ERROR", "SC002", f"point {field} must be a finite number", str(item.get("id"))))
        if item.get("emphasis") is not None and item.get("emphasis") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SC003", "emphasis must be focal or normal", str(item.get("id"))))
    for name in ("x_axis", "y_axis"):
        axis = payload.get(name)
        if not isinstance(axis, dict):
            diagnostics.append(DrawingDiagnostic("ERROR", "SC004", f"{name} must be an object"))
            continue
        for field in sorted(set(axis) - {"label", "unit", "include_zero"}):
            diagnostics.append(DrawingDiagnostic("ERROR", "SC004", f"{name} has unknown field: {field}"))
        if not isinstance(axis.get("label"), str) or not axis.get("label", "").strip():
            diagnostics.append(DrawingDiagnostic("ERROR", "SC004", f"{name}.label must be a non-empty string"))
        if axis.get("unit") is not None and (not isinstance(axis["unit"], str) or len(axis["unit"]) > 12):
            diagnostics.append(DrawingDiagnostic("ERROR", "SC004", f"{name}.unit must be a string of at most 12 characters"))
        if axis.get("include_zero") is not None and not isinstance(axis["include_zero"], bool):
            diagnostics.append(DrawingDiagnostic("ERROR", "SC004", f"{name}.include_zero must be boolean"))
    focus = payload.get("focus")
    if focus is not None and focus not in point_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "SC005", "focus must reference a known point id"))
        focus = None
    focal = [str(item["id"]) for item in points if item.get("emphasis") == "focal"]
    if focus and focus not in focal:
        focal.append(str(focus))
    if len(focal) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "SC006", "scatter supports at most one focal point", ",".join(focal)))
    require_no_errors("schema", diagnostics)

    x_axis = dict(payload["x_axis"])
    y_axis = dict(payload["y_axis"])
    x_scale = nice_scale((float(item["x"]) for item in points), include_zero=bool(x_axis.get("include_zero", False)), unit=x_axis.get("unit"), tick_count=5)
    y_scale = nice_scale((float(item["y"]) for item in points), include_zero=bool(y_axis.get("include_zero", False)), unit=y_axis.get("unit"), tick_count=5)
    width, height = dimensions(payload)
    locale = payload.get("locale") or ("zh-CN" if infer_language(payload["title"], (str(item["label"]) for item in points)) == "zh" else "en-US")
    language = infer_language(payload["title"], (str(item["label"]) for item in points), payload.get("language"))
    semantic = DataSemantic("scatter", payload["title"], tuple(points), language, locale, payload.get("source"))
    plan = ScatterPlan(
        "scatter", payload["title"], tuple(points), x_axis, y_axis, x_scale, y_scale,
        focal[0] if focal else None, _value_format(payload), width, height, language, locale,
    )
    layout = _layout_scatter(plan)
    scene = _resolve_scatter(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _x(value: float, scale: ScalePlan, plot: SceneBox) -> int:
    ratio = (float(value) - scale.domain_min) / (scale.domain_max - scale.domain_min)
    return _grid(plot.x + ratio * plot.w)


def _layout_scatter(plan: ScatterPlan) -> ChartLayout:
    plot = SCATTER_PLOT
    marks: dict[str, Any] = {}
    occupied: list[SceneBox] = []
    offsets = ((10, -10), (10, 2), (-10, -10), (-10, 2), (0, -18), (0, 14))
    for item in plan.points:
        item_id = str(item["id"])
        cx = _x(float(item["x"]), plan.x_scale, plot)
        cy = _y(float(item["y"]), plan.y_scale, plot)
        label_width = _grid(min(132, measure_text(str(item["label"]), 8, DEFAULT_FOLIO_THEME.serif) + 8))
        placement = None
        for dx, dy in offsets:
            anchor = "start" if dx >= 0 else "end"
            left = cx + dx if anchor == "start" else cx + dx - label_width
            candidate = SceneBox(_grid(left), _grid(cy + dy - 8), label_width, 16)
            if candidate.x < plot.x - 4 or candidate.y < plot.y or candidate.x + candidate.w > plot.x + plot.w or candidate.y + candidate.h > plot.y + plot.h:
                continue
            if any(_boxes_overlap(candidate, other) for other in occupied):
                continue
            placement = (candidate, anchor, cx + dx, _grid(cy + dy + 3))
            break
        if placement is not None:
            occupied.append(placement[0])
        marks[item_id] = {"cx": cx, "cy": cy, "placement": placement}
    return ChartLayout(plot, plan.y_scale, marks)


def _boxes_overlap(left: SceneBox, right: SceneBox) -> bool:
    return not (left.x + left.w <= right.x or right.x + right.w <= left.x or left.y + left.h <= right.y or right.y + right.h <= left.y)


def _resolve_scatter(plan: ScatterPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    plot = layout.plot
    primitives: list[object] = _axes(plot, plan.y_scale, (), plan.locale, (), plan.value_format)
    for index, tick in enumerate(plan.x_scale.ticks):
        x = _x(tick, plan.x_scale, plot)
        primitives.append(SceneText(_format(tick, plan.x_scale.unit, plan.locale, plan.value_format), x, plot.y + plot.h + 20, theme.stone, 8, theme.mono, "middle"))
    primitives.append(SceneText(str(plan.x_axis["label"]), plot.x + plot.w // 2, plot.y + plot.h + 44, theme.olive, 9, theme.serif, "middle"))
    primitives.append(SceneText(str(plan.y_axis["label"]), plot.x, plot.y - 16, theme.olive, 9, theme.serif))
    legend: list[str] = []
    reading: list[str] = []
    for item in plan.points:
        item_id = str(item["id"])
        mark = layout.marks[item_id]
        focal = item_id == plan.focus_series
        mark_id = _point_id("scatter", item_id)
        children: list[object] = [
            SceneCircle(f"dot:{item_id}", mark["cx"], mark["cy"], 7 if focal else 5, SceneStyle(theme.brand if focal else theme.ivory, theme.brand if focal else theme.olive, 1.2)),
        ]
        placement = mark["placement"]
        if placement is not None:
            _box, anchor, text_x, text_y = placement
            children.append(SceneText(str(item["label"]), text_x, text_y, theme.brand if focal else theme.near_black, 8, theme.serif, anchor))
        else:
            legend.append(f"{len(legend) + 1}. {item['label']}")
            children.append(SceneText(str(len(legend)), mark["cx"], mark["cy"] + 3, theme.parchment if focal else theme.near_black, 7, theme.mono, "middle"))
        primitives.append(SceneGroup(mark_id, tuple(children)))
        reading.append(mark_id)
    for index, entry in enumerate(legend):
        for line_index, line in enumerate(wrap_text(entry, SCATTER_LEGEND_WIDTH, 8, theme.serif, max_lines=2)):
            primitives.append(SceneText(line, SCATTER_LEGEND_X, 112 + index * 26 + line_index * 11, theme.olive, 8, theme.serif))
    description = f"Scatter {plan.title}. " + "; ".join(
        f"{item['label']}: {plan.x_axis['label']} {item['x']}, {plan.y_axis['label']} {item['y']}" for item in plan.points
    ) + (f". Source: {source}" if source else "")
    if source:
        primitives.append(SceneText(f"Source: {source}", plot.x, 508, theme.stone, 8, theme.mono))
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )


GANTT_LABEL_X = 40
GANTT_LABEL_WIDTH = 176
# The plot stops at x=840 so the right-hand track column (8pt mono, up to 88 units wide) still
# fits inside the 960-unit canvas instead of being clipped by the right edge.
GANTT_PLOT = SceneBox(232, 104, 608, 356)
GANTT_TRACK_WIDTH = 88


@dataclass(frozen=True)
class GanttPlan:
    kind: str
    title: str
    periods: tuple[str, ...]
    tasks: tuple[dict[str, Any], ...]
    milestones: tuple[dict[str, Any], ...]
    focus_series: str | None
    width: int
    height: int
    language: str
    locale: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


def compile_gantt_payload(payload: dict[str, Any]):
    code = "GA000"
    diagnostics = _common_chart(
        payload, kind="gantt",
        extra_allowed={"periods", "tasks", "milestones", "focus"},
        required=("periods", "tasks"), code=code,
    )
    periods = payload.get("periods")
    if not isinstance(periods, list) or not periods or any(not isinstance(value, str) or not value.strip() for value in periods):
        diagnostics.append(DrawingDiagnostic("ERROR", "GA001", "periods must be a non-empty array of non-empty strings"))
        periods = []
    if len(periods) > 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "GA002", "gantt supports at most twelve periods"))
    tasks = object_list(payload, "tasks", diagnostics, code)
    validate_object_fields(tasks, name="tasks", allowed={"id", "label", "start", "span", "track", "emphasis"}, required=("id", "label", "start", "span"), diagnostics=diagnostics, code=code)
    validate_item_strings(tasks, ("label", "track"), diagnostics=diagnostics, code=code)
    task_ids = validate_unique_ids(tasks, name="gantt task", diagnostics=diagnostics, code=code)
    _validate_text_budget(tasks, ("label",), diagnostics, code)
    if not 3 <= len(tasks) <= 10:
        diagnostics.append(DrawingDiagnostic("ERROR", "GA003", "gantt requires between three and ten tasks"))
    for item in tasks:
        start, span = item.get("start"), item.get("span")
        valid = isinstance(start, int) and not isinstance(start, bool) and isinstance(span, int) and not isinstance(span, bool)
        if not valid or start < 0 or span < 1 or (periods and start + span > len(periods)):
            diagnostics.append(DrawingDiagnostic("ERROR", "GA004", "task start and span must be integers inside the period range", str(item.get("id"))))
        if item.get("emphasis") is not None and item.get("emphasis") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "GA005", "emphasis must be focal or normal", str(item.get("id"))))
    milestones = object_list(payload, "milestones", diagnostics, code)
    validate_object_fields(milestones, name="milestones", allowed={"id", "label", "at"}, required=("id", "label", "at"), diagnostics=diagnostics, code=code)
    validate_item_strings(milestones, ("label",), diagnostics=diagnostics, code=code)
    validate_unique_ids(milestones, name="gantt milestone", diagnostics=diagnostics, code=code)
    if len(milestones) > 3:
        diagnostics.append(DrawingDiagnostic("ERROR", "GA006", "gantt supports at most three milestones"))
    for item in milestones:
        at = item.get("at")
        if not isinstance(at, int) or isinstance(at, bool) or at < 0 or (periods and at > len(periods)):
            diagnostics.append(DrawingDiagnostic("ERROR", "GA007", "milestone at must be an integer period boundary", str(item.get("id"))))
        if isinstance(item.get("label"), str) and len(item["label"].strip()) > 24:
            diagnostics.append(DrawingDiagnostic("ERROR", "GA008", "milestone label must contain at most 24 characters", str(item.get("id"))))
    focus = payload.get("focus")
    if focus is not None and focus not in task_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "GA009", "focus must reference a known task id"))
        focus = None
    focal = [str(item["id"]) for item in tasks if item.get("emphasis") == "focal"]
    if focus and focus not in focal:
        focal.append(str(focus))
    if len(focal) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "GA010", "gantt supports at most one focal task", ",".join(focal)))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    locale = payload.get("locale") or ("zh-CN" if infer_language(payload["title"], (str(item["label"]) for item in tasks)) == "zh" else "en-US")
    language = infer_language(payload["title"], (str(item["label"]) for item in tasks), payload.get("language"))
    semantic = DataSemantic("gantt", payload["title"], tuple(tasks), language, locale, payload.get("source"))
    plan = GanttPlan("gantt", payload["title"], tuple(periods), tuple(tasks), tuple(milestones), focal[0] if focal else None, width, height, language, locale)
    layout = _layout_gantt(plan)
    scene = _resolve_gantt(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_gantt(plan: GanttPlan) -> ChartLayout:
    plot = GANTT_PLOT
    column = plot.w / len(plan.periods)
    rows = len(plan.tasks)
    row_height = plot.h / rows
    bar_height = _grid(min(28, max(16, row_height - 16)))
    marks: dict[str, Any] = {}
    for index, item in enumerate(plan.tasks):
        item_id = str(item["id"])
        top = _grid(plot.y + index * row_height + (row_height - bar_height) / 2)
        left = _grid(plot.x + int(item["start"]) * column)
        right = _grid(plot.x + (int(item["start"]) + int(item["span"])) * column)
        marks[item_id] = {
            "box": SceneBox(left + 2, top, max(12, right - left - 4), bar_height),
            "row_center": top + bar_height // 2,
        }
    positions = tuple(_grid(plot.x + (index + 0.5) * column) for index in range(len(plan.periods)))
    return ChartLayout(plot, None, marks, positions)


def _resolve_gantt(plan: GanttPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    plot = layout.plot
    column = plot.w / len(plan.periods)
    primitives: list[object] = []
    for index in range(len(plan.periods) + 1):
        x = _grid(plot.x + index * column)
        primitives.append(SceneLine(f"gridline:{index}", (x, plot.y), (x, plot.y + plot.h), SceneStyle(stroke=theme.border, stroke_width=0.8)))
    primitives.append(SceneLine("axis:x", (plot.x, plot.y), (plot.x + plot.w, plot.y), SceneStyle(stroke=theme.olive, stroke_width=1)))
    for index, label in enumerate(plan.periods):
        primitives.append(SceneText(label, layout.x_positions[index], plot.y - 12, theme.stone, 8, theme.mono, "middle"))
    reading: list[str] = []
    for item in plan.tasks:
        item_id = str(item["id"])
        mark = layout.marks[item_id]
        focal = item_id == plan.focus_series
        box = mark["box"]
        children: list[object] = [
            SceneRect(f"bar:{item_id}", box, SceneStyle(theme.brand if focal else theme.ivory, theme.brand if focal else theme.muted_stroke, 1, radius=3)),
        ]
        label_lines = wrap_text(str(item["label"]), GANTT_LABEL_WIDTH, 10, theme.serif, max_lines=1)
        children.append(SceneText(label_lines[0], GANTT_LABEL_X, mark["row_center"] + 4, theme.brand if focal else theme.near_black, 10, theme.serif))
        track = item.get("track")
        if isinstance(track, str) and track.strip():
            children.append(SceneText(wrap_text(track, GANTT_TRACK_WIDTH, 8, theme.mono, max_lines=1)[0], plot.x + plot.w + 12, mark["row_center"] + 4, theme.stone, 8, theme.mono))
        primitives.append(SceneGroup(item_id, tuple(children)))
        reading.append(item_id)
    for item in plan.milestones:
        x = _grid(plot.x + int(item["at"]) * column)
        primitives.append(SceneLine(f"milestone-line:{item['id']}", (x, plot.y), (x, plot.y + plot.h), SceneStyle(stroke=theme.olive, stroke_width=1, dash=(4, 3))))
        primitives.append(ScenePath(f"milestone-mark:{item['id']}", f"M {x} {plot.y + plot.h + 4} L {x + 6} {plot.y + plot.h + 12} L {x} {plot.y + plot.h + 20} L {x - 6} {plot.y + plot.h + 12} Z", SceneStyle(theme.olive, "none", 0)))
        primitives.append(SceneText(str(item["label"]), x + 10, plot.y + plot.h + 16, theme.olive, 8, theme.serif))
    if source:
        primitives.append(SceneText(f"Source: {source}", GANTT_LABEL_X, 508, theme.stone, 8, theme.mono))
    description = f"Gantt {plan.title}. Periods: " + ", ".join(plan.periods) + ". " + "; ".join(
        f"{item['label']} runs {plan.periods[int(item['start'])]} to {plan.periods[int(item['start']) + int(item['span']) - 1]}" for item in plan.tasks
    ) + ("; " + "; ".join(f"milestone {item['label']}" for item in plan.milestones) if plan.milestones else "") + (f". Source: {source}" if source else "")
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )


HEATMAP_LABEL_X = 40
HEATMAP_PLOT = SceneBox(232, 112, 560, 340)
HEATMAP_LEGEND_X = 808
HEATMAP_LEGEND_VALUE_X = 832
# Cells are capped instead of stretched so a 3x3 matrix keeps editorial cell
# proportions and the focal row never exceeds the 5% saturated-accent budget.
HEATMAP_MAX_CELL_W = 96
HEATMAP_MAX_CELL_H = 48
HEATMAP_RAMP_STEPS = 5
HEATMAP_FOCAL_OPACITY = (0.16, 0.3, 0.46, 0.65, 0.85)


def _heatmap_ramp(theme) -> tuple[str, ...]:
    """Single-hue neutral ramp; ADR 0006 keeps one accent and forbids colormaps."""
    return (theme.ivory, theme.border, theme.neutral_light, theme.neutral_mid, theme.neutral_deep)


def _heatmap_bucket(value: float, scale: ScalePlan) -> int:
    span = scale.domain_max - scale.domain_min
    if span <= 0:
        return HEATMAP_RAMP_STEPS // 2
    ratio = (float(value) - scale.domain_min) / span
    return max(0, min(HEATMAP_RAMP_STEPS - 1, int(ratio * HEATMAP_RAMP_STEPS)))


def _cell_span(available: int, count: int, maximum: int) -> int:
    return max(16, int(min(maximum, available / count) // 4 * 4))


@dataclass(frozen=True)
class HeatmapPlan:
    kind: str
    title: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    x_axis: dict[str, Any]
    y_axis: dict[str, Any]
    scale: ScalePlan
    focus_series: str | None
    value_format: ValueFormatPlan
    width: int
    height: int
    language: str
    locale: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


def compile_heatmap_payload(payload: dict[str, Any]):
    code = "HM000"
    diagnostics = _common_chart(
        payload, kind="heatmap",
        extra_allowed={"columns", "rows", "x_axis", "y_axis", "focus"},
        required=("columns", "rows", "x_axis", "y_axis"), code=code,
    )
    columns = payload.get("columns")
    if not isinstance(columns, list) or not columns or any(not isinstance(value, str) or not value.strip() for value in columns):
        diagnostics.append(DrawingDiagnostic("ERROR", "HM001", "columns must be a non-empty array of non-empty strings"))
        columns = []
    if columns and not 3 <= len(columns) <= 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "HM002", "heatmap requires between three and twelve columns"))
    for label in columns:
        if len(label.strip()) > 12:
            diagnostics.append(DrawingDiagnostic("ERROR", "HM003", "column label must contain at most 12 characters", label))
    rows = object_list(payload, "rows", diagnostics, code)
    validate_object_fields(rows, name="rows", allowed={"id", "label", "values", "emphasis"}, required=("id", "label", "values"), diagnostics=diagnostics, code=code)
    validate_item_strings(rows, ("label",), diagnostics=diagnostics, code=code)
    row_ids = validate_unique_ids(rows, name="heatmap row", diagnostics=diagnostics, code=code)
    _validate_text_budget(rows, ("label",), diagnostics, code)
    if not 3 <= len(rows) <= 10:
        diagnostics.append(DrawingDiagnostic("ERROR", "HM004", "heatmap requires between three and ten rows"))
    for item in rows:
        values = item.get("values")
        if not isinstance(values, list) or (columns and len(values) != len(columns)) or any(not finite_number(value) for value in values or []):
            diagnostics.append(DrawingDiagnostic("ERROR", "HM005", "row values must be finite numbers matching the column count", str(item.get("id"))))
        if item.get("emphasis") is not None and item.get("emphasis") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "HM006", "emphasis must be focal or normal", str(item.get("id"))))
    for name in ("x_axis", "y_axis"):
        axis = payload.get(name)
        if not isinstance(axis, dict):
            diagnostics.append(DrawingDiagnostic("ERROR", "HM007", f"{name} must be an object"))
            continue
        for field in sorted(set(axis) - {"label", "unit"}):
            diagnostics.append(DrawingDiagnostic("ERROR", "HM007", f"{name} has unknown field: {field}"))
        if not isinstance(axis.get("label"), str) or not axis.get("label", "").strip():
            diagnostics.append(DrawingDiagnostic("ERROR", "HM007", f"{name}.label must be a non-empty string"))
        if axis.get("unit") is not None and (not isinstance(axis["unit"], str) or len(axis["unit"]) > 12):
            diagnostics.append(DrawingDiagnostic("ERROR", "HM007", f"{name}.unit must be a string of at most 12 characters"))
    focus = payload.get("focus")
    if focus is not None and focus not in row_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "HM008", "focus must reference a known row id"))
        focus = None
    focal = [str(item["id"]) for item in rows if item.get("emphasis") == "focal"]
    if focus and focus not in focal:
        focal.append(str(focus))
    if len(focal) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "HM009", "heatmap supports at most one focal row", ",".join(focal)))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    labels = [str(item["label"]) for item in rows] + [str(value) for value in columns]
    locale = payload.get("locale") or ("zh-CN" if infer_language(payload["title"], labels) == "zh" else "en-US")
    language = infer_language(payload["title"], labels, payload.get("language"))
    scale = nice_scale(
        (float(value) for item in rows for value in item["values"]),
        include_zero=False, unit=payload.get("unit"), tick_count=5,
    )
    semantic = DataSemantic("heatmap", payload["title"], tuple(rows), language, locale, payload.get("source"))
    plan = HeatmapPlan(
        "heatmap", payload["title"], tuple(str(value) for value in columns), tuple(rows),
        dict(payload["x_axis"]), dict(payload["y_axis"]), scale, focal[0] if focal else None,
        _value_format(payload), width, height, language, locale,
    )
    layout = _layout_heatmap(plan)
    scene = _resolve_heatmap(plan, layout, payload.get("source"))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_heatmap(plan: HeatmapPlan) -> ChartLayout:
    plot = HEATMAP_PLOT
    cell_w = _cell_span(plot.w, len(plan.columns), HEATMAP_MAX_CELL_W)
    cell_h = _cell_span(plot.h, len(plan.rows), HEATMAP_MAX_CELL_H)
    grid_w = cell_w * len(plan.columns)
    grid_h = cell_h * len(plan.rows)
    origin_x = _grid(plot.x + (plot.w - grid_w) / 2)
    origin_y = _grid(plot.y + (plot.h - grid_h) / 2)
    label_x = origin_x - 16
    marks: dict[str, Any] = {}
    for row_index, item in enumerate(plan.rows):
        top = origin_y + row_index * cell_h
        marks[str(item["id"])] = {
            "boxes": tuple(
                SceneBox(origin_x + column_index * cell_w, top, cell_w, cell_h)
                for column_index in range(len(plan.columns))
            ),
            "row_center": top + cell_h // 2,
            "label_x": label_x,
        }
    positions = tuple(origin_x + column_index * cell_w + cell_w // 2 for column_index in range(len(plan.columns)))
    return ChartLayout(plot, plan.scale, marks, positions)


def _resolve_heatmap(plan: HeatmapPlan, layout: ChartLayout, source: str | None) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    ramp = _heatmap_ramp(theme)
    boxes = [box for mark in layout.marks.values() for box in mark["boxes"]]
    grid_top = min(box.y for box in boxes)
    grid_bottom = max(box.y + box.h for box in boxes)
    grid_left = min(box.x for box in boxes)
    grid_right = max(box.x + box.w for box in boxes)
    label_x = layout.marks[str(plan.rows[0]["id"])]["label_x"]
    label_width = max(96, label_x - HEATMAP_LABEL_X)
    primitives: list[object] = []
    for index, label in enumerate(plan.columns):
        text = wrap_text(label, max(16, layout.marks[str(plan.rows[0]["id"])]["boxes"][0].w - 4), 8, theme.mono, max_lines=1)[0]
        primitives.append(SceneText(text, layout.x_positions[index], grid_top - 12, theme.stone, 8, theme.mono, "middle"))
    primitives.append(SceneText(str(plan.y_axis["label"]), HEATMAP_LABEL_X, grid_top - 32, theme.olive, 9, theme.serif))
    primitives.append(SceneText(str(plan.x_axis["label"]), (grid_left + grid_right) // 2, grid_bottom + 40, theme.olive, 9, theme.serif, "middle"))
    reading: list[str] = []
    for item in plan.rows:
        row_id = str(item["id"])
        mark = layout.marks[row_id]
        focal = row_id == plan.focus_series
        children: list[object] = []
        for index, value in enumerate(item["values"]):
            bucket = _heatmap_bucket(float(value), plan.scale)
            style = (
                SceneStyle(theme.brand, theme.parchment, 1, fill_opacity=HEATMAP_FOCAL_OPACITY[bucket])
                if focal else SceneStyle(ramp[bucket], theme.parchment, 1)
            )
            children.append(SceneRect(f"segment:{row_id}:{index}", mark["boxes"][index], style))
        label_lines = wrap_text(str(item["label"]), label_width, 10, theme.serif, max_lines=1)
        children.append(SceneText(
            label_lines[0], mark["label_x"], mark["row_center"] + 4,
            theme.brand if focal else theme.near_black, 10, theme.serif, "end",
        ))
        primitives.append(SceneGroup(row_id, tuple(children)))
        reading.append(row_id)
    legend_top = _grid(HEATMAP_PLOT.y + (HEATMAP_PLOT.h - HEATMAP_RAMP_STEPS * 20 + 4) / 2)
    primitives.append(SceneText("INTENSITY", HEATMAP_LEGEND_X, legend_top - 12, theme.stone, 8, theme.mono))
    for index in range(HEATMAP_RAMP_STEPS):
        top = legend_top + (HEATMAP_RAMP_STEPS - 1 - index) * 20
        primitives.append(SceneRect(f"legend-step:{index}", SceneBox(HEATMAP_LEGEND_X, top, 16, 16), SceneStyle(ramp[index], theme.parchment, 1)))
        if index in (0, HEATMAP_RAMP_STEPS - 1):
            bound = plan.scale.domain_max if index == HEATMAP_RAMP_STEPS - 1 else plan.scale.domain_min
            primitives.append(SceneText(
                _format(bound, plan.scale.unit, plan.locale, plan.value_format),
                HEATMAP_LEGEND_VALUE_X, top + 12, theme.stone, 8, theme.mono,
            ))
    if source:
        primitives.append(SceneText(f"Source: {source}", HEATMAP_LABEL_X, 508, theme.stone, 8, theme.mono))
    description = f"Heatmap {plan.title}. {plan.x_axis['label']}: " + ", ".join(plan.columns) + ". " + "; ".join(
        f"{item['label']}: " + ", ".join(
            f"{plan.columns[index]} {_format(float(value), plan.scale.unit, plan.locale, plan.value_format)}"
            for index, value in enumerate(item["values"])
        )
        for item in plan.rows
    ) + (f". Source: {source}" if source else "")
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )
