from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from .scene import (
    ResolvedScene,
    SceneBox,
    SceneCircle,
    SceneGroup,
    SceneLine,
    SceneRect,
    SceneStyle,
    SceneText,
)
from .theme.folio import DEFAULT_FOLIO_THEME
from .typography.measure import measure_text
from .typography.roles import TextRole, resolve_text_style
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


@dataclass(frozen=True)
class TimelineSemantic:
    title: str
    events: tuple[dict[str, Any], ...]
    scale: str
    focus: str | None
    language: str

    @property
    def nodes(self):
        return self.events

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TimelinePlan:
    kind: str
    title: str
    events: tuple[dict[str, Any], ...]
    scale: str
    focus: str | None
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class TimelineLayout:
    positions: dict[str, tuple[int, int]]
    label_boxes: dict[str, SceneBox]
    axis: tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class QuadrantSemantic:
    title: str
    axes: dict[str, Any]
    items: tuple[dict[str, Any], ...]
    preferred_region: str | None
    language: str

    @property
    def nodes(self):
        return self.items

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class QuadrantPlan:
    kind: str
    title: str
    axes: dict[str, Any]
    items: tuple[dict[str, Any], ...]
    preferred_region: str | None
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class QuadrantLayout:
    plot: SceneBox
    positions: dict[str, tuple[int, int]]
    label_boxes: dict[str, SceneBox]
    legend_items: tuple[str, ...]


@dataclass(frozen=True)
class VennSemantic:
    title: str
    sets: tuple[dict[str, Any], ...]
    intersections: tuple[dict[str, Any], ...]
    focus: tuple[str, ...]
    language: str

    @property
    def nodes(self):
        return self.sets

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class VennPlan:
    kind: str
    title: str
    sets: tuple[dict[str, Any], ...]
    intersections: tuple[dict[str, Any], ...]
    focus: tuple[str, ...]
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class VennLayout:
    circles: dict[str, tuple[int, int, int]]
    text_positions: dict[str, tuple[int, int]]
    legend: tuple[str, ...]


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)


def _title(title: str, width: int) -> SceneText:
    theme = DEFAULT_FOLIO_THEME
    style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    return SceneText(title, width // 2, 40, style.color, style.size, style.family, "middle")


def compile_timeline_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload, kind="timeline",
        allowed={"schema_version", "kind", "title", "events", "scale", "focus", "width", "height", "language"},
        required=("schema_version", "kind", "title", "events"), code="TL000",
    )
    events = object_list(payload, "events", diagnostics, "TL000")
    validate_object_fields(events, name="events", allowed={"id", "date", "label", "description", "importance"}, required=("id", "date", "label"), diagnostics=diagnostics, code="TL000")
    validate_item_strings(events, ("date", "label", "description"), diagnostics=diagnostics, code="TL000")
    event_ids = validate_unique_ids(events, name="timeline event", diagnostics=diagnostics, code="TL001")
    if not 3 <= len(events) <= 10:
        diagnostics.append(DrawingDiagnostic("ERROR", "TL002", "timeline requires 3-10 events"))
    dates: list[date] = []
    for item in events:
        try:
            dates.append(date.fromisoformat(str(item.get("date"))))
        except ValueError:
            diagnostics.append(DrawingDiagnostic("ERROR", "TL003", "event date must be ISO YYYY-MM-DD", str(item.get("id"))))
        if item.get("importance", "normal") not in {"focal", "normal", "background"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "TL004", "invalid event importance", str(item.get("id"))))
    if dates and dates != sorted(dates):
        diagnostics.append(DrawingDiagnostic("ERROR", "TL005", "timeline events must be in chronological order"))
    scale = payload.get("scale", "temporal")
    if scale not in {"temporal", "ordinal"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "TL006", "timeline scale must be temporal or ordinal"))
    focus = payload.get("focus")
    if focus is not None and focus not in event_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "TL007", "focus references unknown event", str(focus)))
    if sum(item.get("importance") == "focal" for item in events) + (1 if focus else 0) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "TL008", "timeline permits one focal event"))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in events), payload.get("language"))
    semantic = TimelineSemantic(payload["title"], tuple(events), scale, focus, language)
    plan = TimelinePlan("timeline", payload["title"], tuple(events), scale, focus, width, height, language)
    layout = _layout_timeline(plan)
    label_boxes = list(layout.label_boxes.values())
    if any(_overlap(left, right) for index, left in enumerate(label_boxes) for right in label_boxes[index + 1:]):
        diagnostics.append(DrawingDiagnostic("ERROR", "TL009", "timeline label lanes cannot resolve all collisions"))
        require_no_errors("layout", diagnostics)
    scene = _resolve_timeline(plan, layout)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_timeline(plan: TimelinePlan) -> TimelineLayout:
    left, right, axis_y = 72, plan.width - 72, _grid(plan.height / 2)
    parsed = [date.fromisoformat(item["date"]) for item in plan.events]
    span = max(1, (parsed[-1] - parsed[0]).days)
    positions: dict[str, tuple[int, int]] = {}
    boxes: dict[str, SceneBox] = {}
    lane_h = 72
    # Keep both label lanes a fixed 56 units clear of the axis: far enough for the leader lines to
    # read, close enough that the alternating rows stay one composition instead of two stripes
    # separated by dead space. Both lanes stay clamped inside shorter embed canvases.
    top_lane = _grid(max(76, axis_y - 56 - lane_h))
    bottom_lane = _grid(min(axis_y + 56, plan.height - lane_h - 12))
    for index, (item, item_date) in enumerate(zip(plan.events, parsed)):
        ratio = index / max(1, len(plan.events) - 1) if plan.scale == "ordinal" else (item_date - parsed[0]).days / span
        x = _grid(left + ratio * (right - left))
        lane_y = top_lane if index % 2 == 0 else bottom_lane
        positions[item["id"]] = (x, axis_y)
        boxes[item["id"]] = SceneBox(max(8, x - 64), lane_y, 128, lane_h)
    return TimelineLayout(positions, boxes, ((left, axis_y), (right, axis_y)))


def _resolve_timeline(plan: TimelinePlan, layout: TimelineLayout) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = [SceneLine("timeline-axis", *layout.axis, SceneStyle(stroke=theme.border, stroke_width=1))]
    reading_order: list[str] = []
    for index, item in enumerate(plan.events):
        item_id = item["id"]
        x, y = layout.positions[item_id]
        box = layout.label_boxes[item_id]
        focal = item_id == plan.focus or item.get("importance") == "focal"
        direction = 1 if box.y > y else -1
        children: list[object] = [
            SceneLine(f"tick:{item_id}", (x, y - 8), (x, y + 8), SceneStyle(stroke=theme.brand if focal else theme.stone, stroke_width=1.2)),
            SceneLine(f"leader:{item_id}", (x, y + direction * 8), (x, box.y if direction > 0 else box.y + box.h), SceneStyle(stroke=theme.border, stroke_width=1)),
            SceneCircle(f"mark:{item_id}", x, y, 5 if focal else 4, SceneStyle(theme.brand if focal else theme.ivory, theme.brand if focal else theme.olive, 1.2)),
            SceneText(item["date"], x, box.y + 16, theme.brand if focal else theme.stone, 8, theme.mono, "middle"),
        ]
        label_lines = wrap_text(item["label"], 120, 11, theme.serif, 2)
        children.extend(SceneText(line, x, box.y + 36 + line_index * 16, theme.near_black, 11, theme.serif, "middle", weight="500") for line_index, line in enumerate(label_lines))
        primitives.append(SceneGroup(item_id, tuple(children)))
        reading_order.append(item_id)
    scene = ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description="Timeline " + plan.title + ". " + "; ".join(f"{item['date']} {item['label']}" for item in plan.events),
        language=plan.language, reading_order=tuple(reading_order), primitives=tuple(primitives),
    )
    return scene


def compile_quadrant_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload, kind="quadrant",
        allowed={"schema_version", "kind", "title", "axes", "items", "preferred_region", "width", "height", "language"},
        required=("schema_version", "kind", "title", "axes", "items"), code="QD000",
    )
    axes = payload.get("axes")
    if not isinstance(axes, dict) or set(axes) != {"x", "y"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "QD001", "axes must contain x and y"))
        axes = {"x": {}, "y": {}}
    for axis in ("x", "y"):
        value = axes.get(axis, {})
        if not isinstance(value, dict) or any(not isinstance(value.get(field), str) or not value.get(field, "").strip() for field in ("label", "low", "high")):
            diagnostics.append(DrawingDiagnostic("ERROR", "QD002", f"{axis} axis requires label, low, and high"))
    items = object_list(payload, "items", diagnostics, "QD000")
    validate_object_fields(items, name="items", allowed={"id", "label", "x", "y", "emphasis"}, required=("id", "label", "x", "y"), diagnostics=diagnostics, code="QD000")
    validate_item_strings(items, ("label",), diagnostics=diagnostics, code="QD000")
    validate_unique_ids(items, name="quadrant item", diagnostics=diagnostics, code="QD003")
    if not 4 <= len(items) <= 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "QD004", "quadrant requires 4-12 items"))
    for item in items:
        if not finite_number(item.get("x")) or not 0 <= float(item["x"]) <= 1 or not finite_number(item.get("y")) or not 0 <= float(item["y"]) <= 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "QD005", "quadrant values must be finite and normalized to 0-1", str(item.get("id"))))
        if item.get("emphasis", "normal") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "QD006", "invalid item emphasis", str(item.get("id"))))
    if sum(item.get("emphasis") == "focal" for item in items) > 2:
        diagnostics.append(DrawingDiagnostic("ERROR", "QD007", "quadrant permits at most two focal items"))
    preferred = payload.get("preferred_region")
    if preferred is not None and preferred not in {"top-left", "top-right", "bottom-left", "bottom-right"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "QD008", "invalid preferred_region"))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in items), payload.get("language"))
    semantic = QuadrantSemantic(payload["title"], axes, tuple(items), preferred, language)
    plan = QuadrantPlan("quadrant", payload["title"], axes, tuple(items), preferred, width, height, language)
    layout = _layout_quadrant(plan)
    positions = list(layout.positions.values())
    if any((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2 < 12 ** 2 for index, left in enumerate(positions) for right in positions[index + 1:]):
        diagnostics.append(DrawingDiagnostic("ERROR", "QD009", "quadrant points must remain at least 12 visible units apart"))
        require_no_errors("layout", diagnostics)
    scene = _resolve_quadrant(plan, layout)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_quadrant(plan: QuadrantPlan) -> QuadrantLayout:
    plot = SceneBox(136, 88, 616, 368)
    positions: dict[str, tuple[int, int]] = {}
    label_boxes: dict[str, SceneBox] = {}
    occupied: list[SceneBox] = []
    fallback: list[str] = []
    offsets = ((12, -24), (12, 8), (-116, -24), (-116, 8), (-52, -40), (-52, 16), (20, -8), (-124, -8))
    for item in plan.items:
        x = _grid(plot.x + float(item["x"]) * plot.w)
        y = _grid(plot.y + (1 - float(item["y"])) * plot.h)
        positions[item["id"]] = (x, y)
        label_width = _grid(min(112, max(48, measure_text(item["label"], 9, DEFAULT_FOLIO_THEME.serif) + 12)))
        selected = None
        for dx, dy in offsets:
            candidate = SceneBox(_grid(x + dx), _grid(y + dy), label_width, 20)
            if candidate.x < plot.x or candidate.y < plot.y or candidate.x + candidate.w > plot.x + plot.w or candidate.y + candidate.h > plot.y + plot.h:
                continue
            if not any(_overlap(candidate, other) for other in occupied):
                selected = candidate
                break
        if selected is None:
            fallback.append(item["id"])
            selected = SceneBox(x + 8, y - 12, 24, 20)
        label_boxes[item["id"]] = selected
        occupied.append(selected)
    return QuadrantLayout(plot, positions, label_boxes, tuple(fallback))


def _overlap(left: SceneBox, right: SceneBox) -> bool:
    return not (left.x + left.w <= right.x or right.x + right.w <= left.x or left.y + left.h <= right.y or right.y + right.h <= left.y)


def _resolve_quadrant(plan: QuadrantPlan, layout: QuadrantLayout) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    plot = layout.plot
    primitives: list[object] = []
    if plan.preferred_region:
        left = plan.preferred_region.endswith("left")
        top = plan.preferred_region.startswith("top")
        primitives.append(SceneRect("preferred-region", SceneBox(plot.x if left else plot.x + plot.w // 2, plot.y if top else plot.y + plot.h // 2, plot.w // 2, plot.h // 2), SceneStyle(theme.brand_tint, "none", fill_opacity=0.55)))
    primitives.extend([
        SceneRect("quadrant-frame", plot, SceneStyle("none", theme.border, 1)),
        SceneLine("quadrant-x-mid", (plot.x, plot.y + plot.h // 2), (plot.x + plot.w, plot.y + plot.h // 2), SceneStyle(stroke=theme.border, stroke_width=1)),
        SceneLine("quadrant-y-mid", (plot.x + plot.w // 2, plot.y), (plot.x + plot.w // 2, plot.y + plot.h), SceneStyle(stroke=theme.border, stroke_width=1)),
        SceneText(plan.axes["x"]["low"], plot.x, plot.y + plot.h + 24, theme.stone, 8, theme.mono),
        SceneText(plan.axes["x"]["high"], plot.x + plot.w, plot.y + plot.h + 24, theme.stone, 8, theme.mono, "end"),
        SceneText(plan.axes["x"]["label"], plot.x + plot.w // 2, plot.y + plot.h + 44, theme.olive, 9, theme.serif, "middle"),
        SceneText(plan.axes["y"]["high"], plot.x - 12, plot.y + 8, theme.stone, 8, theme.mono, "end"),
        SceneText(plan.axes["y"]["low"], plot.x - 12, plot.y + plot.h, theme.stone, 8, theme.mono, "end"),
    ])
    fallback_index = {item_id: index + 1 for index, item_id in enumerate(layout.legend_items)}
    for item in plan.items:
        item_id = item["id"]
        x, y = layout.positions[item_id]
        box = layout.label_boxes[item_id]
        focal = item.get("emphasis") == "focal"
        fallback = item_id in fallback_index
        label = str(fallback_index[item_id]) if fallback else item["label"]
        children = (
            SceneCircle(f"point:{item_id}", x, y, 8 if fallback else 6 if focal else 4, SceneStyle(theme.brand if focal else theme.ivory, theme.brand if focal else theme.olive, 1.2)),
            SceneText(label, x, y + 3, theme.parchment, 7, theme.mono, "middle") if fallback else
            SceneText(label, box.x + 4, box.y + 14, theme.brand if focal else theme.near_black, 9, theme.serif),
        )
        primitives.append(SceneGroup(item_id, children))
    for index, item_id in enumerate(layout.legend_items):
        item = next(value for value in plan.items if value["id"] == item_id)
        primitives.append(SceneText(f"{index + 1}. {item['label']}", 780, 112 + index * 24, theme.olive, 9, theme.serif))
    scene = ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description="Quadrant " + plan.title + ". " + "; ".join(f"{item['label']}: x {item['x']}, y {item['y']}" for item in plan.items),
        language=plan.language, reading_order=tuple(item["id"] for item in plan.items), primitives=tuple(primitives),
    )
    return scene


def compile_venn_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload, kind="venn",
        allowed={"schema_version", "kind", "title", "sets", "intersections", "focus", "width", "height", "language"},
        required=("schema_version", "kind", "title", "sets", "intersections"), code="VN000",
    )
    sets = object_list(payload, "sets", diagnostics, "VN000")
    intersections = object_list(payload, "intersections", diagnostics, "VN000")
    validate_object_fields(sets, name="sets", allowed={"id", "label", "exclusive"}, required=("id", "label", "exclusive"), diagnostics=diagnostics, code="VN000")
    validate_object_fields(intersections, name="intersections", allowed={"id", "sets", "items"}, required=("id", "sets", "items"), diagnostics=diagnostics, code="VN000")
    validate_item_strings(sets, ("label",), diagnostics=diagnostics, code="VN000")
    set_ids = validate_unique_ids(sets, name="venn set", diagnostics=diagnostics, code="VN001")
    validate_unique_ids(intersections, name="venn intersection", diagnostics=diagnostics, code="VN002")
    if len(sets) not in {2, 3}:
        diagnostics.append(DrawingDiagnostic("ERROR", "VN003", "venn supports exactly two or three sets"))
    for item in sets:
        if not isinstance(item.get("exclusive"), list) or any(not isinstance(value, str) or not value.strip() for value in item.get("exclusive", [])):
            diagnostics.append(DrawingDiagnostic("ERROR", "VN004", "set exclusive items must be non-empty strings", str(item.get("id"))))
    seen_combinations: set[tuple[str, ...]] = set()
    for item in intersections:
        members = item.get("sets")
        if not isinstance(members, list) or len(members) not in {2, 3} or any(value not in set_ids for value in members) or len(set(members)) != len(members):
            diagnostics.append(DrawingDiagnostic("ERROR", "VN005", "intersection must reference two or three unique known sets", str(item.get("id"))))
        else:
            key = tuple(sorted(members))
            if key in seen_combinations:
                diagnostics.append(DrawingDiagnostic("ERROR", "VN006", "duplicate venn intersection", str(item.get("id"))))
            seen_combinations.add(key)
        if not isinstance(item.get("items"), list) or any(not isinstance(value, str) or not value.strip() for value in item.get("items", [])):
            diagnostics.append(DrawingDiagnostic("ERROR", "VN007", "intersection items must be strings", str(item.get("id"))))
    focus = payload.get("focus", [])
    if not isinstance(focus, list) or any(item not in set_ids for item in focus) or len(focus) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "VN008", "focus must contain at most one known set id"))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in sets), payload.get("language"))
    semantic = VennSemantic(payload["title"], tuple(sets), tuple(intersections), tuple(focus), language)
    plan = VennPlan("venn", payload["title"], tuple(sets), tuple(intersections), tuple(focus), width, height, language)
    layout = _layout_venn(plan)
    scene = _resolve_venn(plan, layout)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_venn(plan: VennPlan) -> VennLayout:
    labels = {str(item["id"]): str(item["label"]) for item in plan.sets}
    if len(plan.sets) == 2:
        circles = {plan.sets[0]["id"]: (352, 264, 176), plan.sets[1]["id"]: (608, 264, 176)}
        positions = {plan.sets[0]["id"]: (304, 256), plan.sets[1]["id"]: (656, 256)}
    else:
        circles = {
            plan.sets[0]["id"]: (376, 192, 136),
            plan.sets[1]["id"]: (584, 192, 136),
            plan.sets[2]["id"]: (480, 320, 136),
        }
        positions = {plan.sets[0]["id"]: (272, 176), plan.sets[1]["id"]: (688, 176), plan.sets[2]["id"]: (480, 416)}
    legend: list[str] = []
    for item in plan.sets:
        if len(item["exclusive"]) > 2:
            legend.extend(f"{item['label']}: {value}" for value in item["exclusive"][2:])
    for item in plan.intersections:
        key = " + ".join(labels.get(str(value), str(value)) for value in item["sets"])
        if len(plan.sets) == 3 and len(item["sets"]) == 2:
            pair = frozenset(item["sets"])
            first, second, third = (value["id"] for value in plan.sets)
            positions[item["id"]] = {
                frozenset((first, second)): (480, 152),
                frozenset((first, third)): (392, 292),
                frozenset((second, third)): (568, 292),
            }[pair]
        else:
            positions[item["id"]] = (480, 236 if len(plan.sets) == 3 else 256)
        if len(item["items"]) > 2:
            legend.extend(f"{key}: {value}" for value in item["items"][2:])
    return VennLayout(circles, positions, tuple(legend))


def _resolve_venn(plan: VennPlan, layout: VennLayout) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = []
    reading: list[str] = []
    for index, item in enumerate(plan.sets):
        cx, cy, radius = layout.circles[item["id"]]
        focal = item["id"] in plan.focus
        fill = theme.brand_tint if focal or index == 0 else theme.ivory
        stroke = theme.brand if focal else theme.stone
        x, y = layout.text_positions[item["id"]]
        children: list[object] = [
            SceneCircle(f"circle:{item['id']}", cx, cy, radius, SceneStyle(fill, stroke, 1.2, fill_opacity=0.58)),
            SceneText(item["label"], cx, cy - radius + 24, theme.brand if focal else theme.near_black, 11, theme.serif, "middle", weight="500"),
        ]
        for line_index, value in enumerate(item["exclusive"][:2]):
            children.append(SceneText(value, x, y + line_index * 16, theme.olive, 9, theme.serif, "middle"))
        primitives.append(SceneGroup(f"set:{item['id']}", tuple(children)))
        reading.append(f"set:{item['id']}")
    for item in plan.intersections:
        x, y = layout.text_positions[item["id"]]
        children = tuple(SceneText(value, x, y + index * 16, theme.brand, 9, theme.serif, "middle") for index, value in enumerate(item["items"][:2]))
        primitives.append(SceneGroup(f"intersection:{item['id']}", children))
        reading.append(f"intersection:{item['id']}")
    for index, value in enumerate(layout.legend):
        primitives.append(SceneText(value, 120 + (index % 2) * 360, 480 + (index // 2) * 16, theme.olive, 8, theme.serif))
    description = "Venn " + plan.title + ". " + "; ".join(
        [*(f"{item['label']} exclusive: {', '.join(item['exclusive']) or 'empty'}" for item in plan.sets), *(f"intersection {','.join(item['sets'])}: {', '.join(item['items']) or 'empty'}" for item in plan.intersections)]
    )
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )
