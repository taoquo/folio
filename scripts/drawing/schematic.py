from __future__ import annotations

from dataclasses import asdict, dataclass
from math import cos, pi, sin
from typing import Any

from .scene import (
    ResolvedScene,
    SceneBox,
    SceneCircle,
    SceneGroup,
    SceneLine,
    ScenePath,
    ScenePolyline,
    SceneRect,
    SceneStyle,
    SceneText,
)
from .theme.folio import DEFAULT_FOLIO_THEME
from .typography.roles import TextRole, resolve_text_style
from .v3_common import (
    common_payload_diagnostics,
    dimensions,
    infer_language,
    object_list,
    require_no_errors,
    validate_item_strings,
    validate_object_fields,
    validate_resolved_scene,
    validate_unique_ids,
    wrap_text,
)
from .validation import DrawingDiagnostic


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)


def _title(title: str, width: int) -> SceneText:
    theme = DEFAULT_FOLIO_THEME
    style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    return SceneText(title, width // 2, 40, style.color, style.size, style.family, "middle")


def _focal_ids(items: list[dict[str, Any]], focus: Any) -> tuple[str, ...]:
    result: list[str] = []
    if isinstance(focus, list):
        result.extend(str(value) for value in focus)
    for item in items:
        if item.get("emphasis") == "focal" and str(item.get("id")) not in result:
            result.append(str(item.get("id")))
    return tuple(result)


def _focus_list(payload: dict[str, Any]) -> Any:
    """Accept focus as a single id string or a list of ids, per the type schemas."""
    focus = payload.get("focus", [])
    if focus is None:
        return []
    if isinstance(focus, str):
        return [focus]
    return focus


PYRAMID_LEFT = 80
PYRAMID_MAX_WIDTH = 580
PYRAMID_TOP = 96
PYRAMID_BOTTOM = 484
PYRAMID_DETAIL_X = 700
PYRAMID_DETAIL_WIDTH = 216


@dataclass(frozen=True)
class PyramidSemantic:
    title: str
    levels: tuple[dict[str, Any], ...]
    orientation: str
    focus: tuple[str, ...]
    language: str

    @property
    def nodes(self):
        return self.levels

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PyramidPlan:
    kind: str
    title: str
    levels: tuple[dict[str, Any], ...]
    orientation: str
    focus: tuple[str, ...]
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    @property
    def items(self):
        return self.levels

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PyramidLayout:
    bands: dict[str, tuple[tuple[int, int], ...]]
    label_positions: dict[str, tuple[int, int]]
    detail_positions: dict[str, tuple[int, int]]
    leaders: dict[str, tuple[tuple[int, int], tuple[int, int]]]

    def to_dict(self):
        return asdict(self)


def compile_pyramid_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload, kind="pyramid",
        allowed={"schema_version", "kind", "title", "levels", "orientation", "focus", "width", "height", "language"},
        required=("schema_version", "kind", "title", "levels"), code="PY000",
    )
    levels = object_list(payload, "levels", diagnostics, "PY000")
    validate_object_fields(levels, name="levels", allowed={"id", "label", "detail", "emphasis"}, required=("id", "label"), diagnostics=diagnostics, code="PY000")
    validate_item_strings(levels, ("label", "detail"), diagnostics=diagnostics, code="PY000")
    level_ids = validate_unique_ids(levels, name="pyramid level", diagnostics=diagnostics, code="PY001")
    if not 3 <= len(levels) <= 6:
        diagnostics.append(DrawingDiagnostic("ERROR", "PY002", "pyramid requires between three and six levels"))
    orientation = payload.get("orientation", "up")
    if orientation not in {"up", "down"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "PY003", "orientation must be up or down"))
    for item in levels:
        if item.get("emphasis") is not None and item.get("emphasis") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "PY004", "emphasis must be focal or normal", str(item.get("id"))))
    focus = _focus_list(payload)
    if not isinstance(focus, list) or any(value not in level_ids for value in focus):
        diagnostics.append(DrawingDiagnostic("ERROR", "PY005", "focus must reference known pyramid level ids"))
        focus = []
    focal = _focal_ids(levels, focus)
    if len(focal) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "PY006", "pyramid supports at most one focal level", ",".join(focal)))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in levels), payload.get("language"))
    semantic = PyramidSemantic(payload["title"], tuple(levels), orientation, focal, language)
    plan = PyramidPlan("pyramid", payload["title"], tuple(levels), orientation, focal, width, height, language)
    layout = _layout_pyramid(plan)
    scene = _resolve_pyramid(plan, layout)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_pyramid(plan: PyramidPlan) -> PyramidLayout:
    count = len(plan.levels)
    band_height = (PYRAMID_BOTTOM - PYRAMID_TOP) / count
    center = PYRAMID_LEFT + PYRAMID_MAX_WIDTH // 2
    bands: dict[str, tuple[tuple[int, int], ...]] = {}
    label_positions: dict[str, tuple[int, int]] = {}
    detail_positions: dict[str, tuple[int, int]] = {}
    leaders: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    for index, item in enumerate(plan.levels):
        top = _grid(PYRAMID_TOP + index * band_height)
        bottom = _grid(PYRAMID_TOP + (index + 1) * band_height) - 4
        steps = (index, index + 1) if plan.orientation == "up" else (count - index, count - index - 1)
        top_ratio = 0.22 + 0.78 * steps[0] / count
        bottom_ratio = 0.22 + 0.78 * steps[1] / count
        top_width = _grid(PYRAMID_MAX_WIDTH * top_ratio)
        bottom_width = _grid(PYRAMID_MAX_WIDTH * bottom_ratio)
        bands[item["id"]] = (
            (center - top_width // 2, top),
            (center + top_width // 2, top),
            (center + bottom_width // 2, bottom),
            (center - bottom_width // 2, bottom),
        )
        middle = _grid((top + bottom) / 2)
        label_positions[item["id"]] = (center, middle + 4)
        detail_positions[item["id"]] = (PYRAMID_DETAIL_X, middle - 2)
        edge = max(top_width, bottom_width)
        leaders[item["id"]] = ((center + edge // 2 + 12, middle), (PYRAMID_DETAIL_X - 16, middle))
    return PyramidLayout(bands, label_positions, detail_positions, leaders)


def _resolve_pyramid(plan: PyramidPlan, layout: PyramidLayout) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = []
    reading: list[str] = []
    for index, item in enumerate(plan.levels):
        item_id = item["id"]
        focal = item_id in plan.focus
        points = layout.bands[item_id]
        path = "M " + " L ".join(f"{x} {y}" for x, y in points) + " Z"
        fill = theme.brand_tint if focal else (theme.ivory if index % 2 == 0 else theme.parchment)
        stroke = theme.brand if focal else theme.border
        children: list[object] = [
            ScenePath(f"band:{item_id}", path, SceneStyle(fill, stroke, 1.2 if focal else 1)),
        ]
        label_x, label_y = layout.label_positions[item_id]
        children.append(SceneText(item["label"], label_x, label_y, theme.brand if focal else theme.near_black, 12, theme.serif, "middle", weight="500"))
        detail = item.get("detail")
        if isinstance(detail, str) and detail.strip():
            start, end = layout.leaders[item_id]
            children.append(SceneLine(f"leader:{item_id}", start, end, SceneStyle(stroke=theme.border, stroke_width=1)))
            detail_x, detail_y = layout.detail_positions[item_id]
            lines = wrap_text(detail, PYRAMID_DETAIL_WIDTH, 9, theme.serif, max_lines=2)
            for line_index, line in enumerate(lines):
                children.append(SceneText(line, detail_x, detail_y + line_index * 14, theme.olive, 9, theme.serif))
        primitives.append(SceneGroup(item_id, tuple(children)))
        reading.append(item_id)
    description = ("Funnel " if plan.orientation == "down" else "Pyramid ") + plan.title + ". " + "; ".join(
        f"{index + 1}. {item['label']}" + (f": {item['detail']}" if isinstance(item.get("detail"), str) else "")
        for index, item in enumerate(plan.levels)
    )
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )




LOOP_CENTER_X = 336
LOOP_CENTER_Y = 300
LOOP_RING_RADIUS = 168
LOOP_STAGE_RADIUS = 56
LOOP_DETAIL_X = 596
LOOP_DETAIL_WIDTH = 300


@dataclass(frozen=True)
class LoopFlywheelSemantic:
    title: str
    stages: tuple[dict[str, Any], ...]
    hub: str | None
    focus: tuple[str, ...]
    language: str

    @property
    def nodes(self):
        return self.stages

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class LoopFlywheelPlan:
    kind: str
    title: str
    stages: tuple[dict[str, Any], ...]
    hub: str | None
    focus: tuple[str, ...]
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    @property
    def items(self):
        return self.stages

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class LoopFlywheelLayout:
    centers: dict[str, tuple[int, int]]
    arcs: dict[str, tuple[tuple[int, int], tuple[int, int]]]
    arrows: dict[str, tuple[tuple[int, int], ...]]
    detail_positions: dict[str, tuple[int, int]]

    def to_dict(self):
        return asdict(self)


def compile_loop_flywheel_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload, kind="loop-flywheel",
        allowed={"schema_version", "kind", "title", "stages", "hub", "focus", "width", "height", "language"},
        required=("schema_version", "kind", "title", "stages"), code="LF000",
    )
    stages = object_list(payload, "stages", diagnostics, "LF000")
    validate_object_fields(stages, name="stages", allowed={"id", "label", "detail", "emphasis"}, required=("id", "label"), diagnostics=diagnostics, code="LF000")
    validate_item_strings(stages, ("label", "detail"), diagnostics=diagnostics, code="LF000")
    stage_ids = validate_unique_ids(stages, name="loop-flywheel stage", diagnostics=diagnostics, code="LF001")
    if not 3 <= len(stages) <= 6:
        diagnostics.append(DrawingDiagnostic("ERROR", "LF002", "loop-flywheel requires between three and six stages"))
    hub = payload.get("hub")
    if hub is not None and (not isinstance(hub, str) or not hub.strip()):
        diagnostics.append(DrawingDiagnostic("ERROR", "LF003", "hub must be a non-empty string"))
        hub = None
    for item in stages:
        if item.get("emphasis") is not None and item.get("emphasis") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "LF004", "emphasis must be focal or normal", str(item.get("id"))))
    focus = _focus_list(payload)
    if not isinstance(focus, list) or any(value not in stage_ids for value in focus):
        diagnostics.append(DrawingDiagnostic("ERROR", "LF005", "focus must reference known stage ids"))
        focus = []
    focal = _focal_ids(stages, focus)
    if len(focal) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "LF006", "loop-flywheel supports at most one focal stage", ",".join(focal)))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in stages), payload.get("language"))
    semantic = LoopFlywheelSemantic(payload["title"], tuple(stages), hub, focal, language)
    plan = LoopFlywheelPlan("loop-flywheel", payload["title"], tuple(stages), hub, focal, width, height, language)
    layout = _layout_loop_flywheel(plan)
    scene = _resolve_loop_flywheel(plan, layout)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_loop_flywheel(plan: LoopFlywheelPlan) -> LoopFlywheelLayout:
    count = len(plan.stages)
    step = 2 * pi / count
    gap = min(step * 0.34, 0.44)
    centers: dict[str, tuple[int, int]] = {}
    arcs: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    arrows: dict[str, tuple[tuple[int, int], ...]] = {}
    detail_positions: dict[str, tuple[int, int]] = {}
    angles: list[float] = []
    for index, item in enumerate(plan.stages):
        angle = -pi / 2 + index * step
        angles.append(angle)
        centers[item["id"]] = _point_on_ring(angle)
        detail_positions[item["id"]] = (LOOP_DETAIL_X, _grid(140 + index * (300 / max(1, count - 1))))
    for index, item in enumerate(plan.stages):
        start_angle = angles[index] + gap
        end_angle = angles[(index + 1) % count] - gap
        if end_angle < start_angle:
            end_angle += 2 * pi
        arcs[item["id"]] = (_point_on_ring(start_angle), _point_on_ring(end_angle))
        arrows[item["id"]] = _arrow_head(end_angle)
    return LoopFlywheelLayout(centers, arcs, arrows, detail_positions)


def _point_on_ring(angle: float) -> tuple[int, int]:
    return (
        _grid(LOOP_CENTER_X + LOOP_RING_RADIUS * cos(angle)),
        _grid(LOOP_CENTER_Y + LOOP_RING_RADIUS * sin(angle)),
    )


def _arrow_head(angle: float) -> tuple[tuple[int, int], ...]:
    tip_x = LOOP_CENTER_X + LOOP_RING_RADIUS * cos(angle)
    tip_y = LOOP_CENTER_Y + LOOP_RING_RADIUS * sin(angle)
    tangent = angle + pi / 2
    back_x = tip_x - 13 * cos(tangent)
    back_y = tip_y - 13 * sin(tangent)
    normal_x = cos(angle)
    normal_y = sin(angle)
    return (
        (int(round(back_x + 6 * normal_x)), int(round(back_y + 6 * normal_y))),
        (int(round(tip_x)), int(round(tip_y))),
        (int(round(back_x - 6 * normal_x)), int(round(back_y - 6 * normal_y))),
    )


def _resolve_loop_flywheel(plan: LoopFlywheelPlan, layout: LoopFlywheelLayout) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = []
    reading: list[str] = []
    for item in plan.stages:
        start, end = layout.arcs[item["id"]]
        path = f"M {start[0]} {start[1]} A {LOOP_RING_RADIUS} {LOOP_RING_RADIUS} 0 0 1 {end[0]} {end[1]}"
        primitives.append(ScenePath(f"arc:{item['id']}", path, SceneStyle("none", theme.muted_stroke, 1)))
        points = layout.arrows[item["id"]]
        head = "M " + " L ".join(f"{x} {y}" for x, y in points) + " Z"
        primitives.append(ScenePath(f"arrow:{item['id']}", head, SceneStyle(theme.muted_stroke, "none", 0)))
    if plan.hub:
        hub_lines = wrap_text(plan.hub, 132, 11, theme.serif, max_lines=2)
        hub_children: list[object] = [
            SceneCircle("hub-disc", LOOP_CENTER_X, LOOP_CENTER_Y, 72, SceneStyle(theme.ivory, theme.border, 1)),
        ]
        for line_index, line in enumerate(hub_lines):
            hub_children.append(SceneText(line, LOOP_CENTER_X, int(round(LOOP_CENTER_Y + 4 + (line_index - (len(hub_lines) - 1) / 2) * 15)), theme.olive, 11, theme.serif, "middle"))
        primitives.append(SceneGroup("hub", tuple(hub_children)))
    for index, item in enumerate(plan.stages):
        item_id = str(item["id"])
        cx, cy = layout.centers[item_id]
        focal = item_id in plan.focus
        fill = theme.brand_tint if focal else theme.ivory
        stroke = theme.brand if focal else theme.border
        children: list[object] = [
            SceneCircle(f"stage:{item_id}", cx, cy, LOOP_STAGE_RADIUS, SceneStyle(fill, stroke, 1.2 if focal else 1)),
        ]
        lines = wrap_text(str(item["label"]), LOOP_STAGE_RADIUS * 2 - 24, 11, theme.serif, max_lines=2)
        for line_index, line in enumerate(lines):
            children.append(SceneText(line, cx, int(round(cy + 4 + (line_index - (len(lines) - 1) / 2) * 14)), theme.brand if focal else theme.near_black, 11, theme.serif, "middle", weight="500"))
        primitives.append(SceneGroup(item_id, tuple(children)))
        reading.append(item_id)
        detail = item.get("detail")
        if isinstance(detail, str) and detail.strip():
            detail_x, detail_y = layout.detail_positions[item_id]
            detail_children: list[object] = [
                SceneText(f"{index + 1}", detail_x, detail_y, theme.stone, 9, theme.mono),
                SceneText(str(item["label"]), detail_x + 20, detail_y, theme.near_black, 10, theme.serif),
            ]
            for line_index, line in enumerate(wrap_text(detail, LOOP_DETAIL_WIDTH - 20, 9, theme.serif, max_lines=2)):
                detail_children.append(SceneText(line, detail_x + 20, detail_y + 16 + line_index * 13, theme.olive, 9, theme.serif))
            primitives.append(SceneGroup(f"note:{item_id}", tuple(detail_children)))
    description = "Flywheel " + plan.title + ". " + (f"Hub: {plan.hub}. " if plan.hub else "") + "; ".join(
        f"{index + 1}. {item['label']}" + (f": {item['detail']}" if isinstance(item.get("detail"), str) else "")
        for index, item in enumerate(plan.stages)
    )
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )


ORG_LEFT = 40
ORG_RIGHT = 920
ORG_TOP = 88
ORG_BOTTOM = 500


@dataclass(frozen=True)
class OrgChartSemantic:
    title: str
    units: tuple[dict[str, Any], ...]
    focus: tuple[str, ...]
    language: str

    @property
    def nodes(self):
        return self.units

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class OrgChartPlan:
    kind: str
    title: str
    units: tuple[dict[str, Any], ...]
    focus: tuple[str, ...]
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    @property
    def items(self):
        return self.units

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class OrgChartLayout:
    boxes: dict[str, SceneBox]
    depths: dict[str, int]
    connectors: dict[str, tuple[tuple[int, int], ...]]

    def to_dict(self):
        return asdict(self)


def compile_org_chart_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload, kind="org-chart",
        allowed={"schema_version", "kind", "title", "units", "focus", "width", "height", "language"},
        required=("schema_version", "kind", "title", "units"), code="OC000",
    )
    units = object_list(payload, "units", diagnostics, "OC000")
    validate_object_fields(units, name="units", allowed={"id", "label", "role", "parent", "emphasis"}, required=("id", "label"), diagnostics=diagnostics, code="OC000")
    validate_item_strings(units, ("label", "role", "parent"), diagnostics=diagnostics, code="OC000")
    unit_ids = validate_unique_ids(units, name="org-chart unit", diagnostics=diagnostics, code="OC001")
    if not 3 <= len(units) <= 16:
        diagnostics.append(DrawingDiagnostic("ERROR", "OC002", "org-chart requires between three and sixteen units"))
    roots = [item for item in units if not item.get("parent")]
    if len(roots) != 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "OC003", "org-chart requires exactly one root unit"))
    for item in units:
        parent = item.get("parent")
        if parent is not None and parent not in unit_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "OC004", "parent must reference a known unit id", str(item.get("id"))))
        if parent is not None and parent == item.get("id"):
            diagnostics.append(DrawingDiagnostic("ERROR", "OC005", "unit cannot be its own parent", str(item.get("id"))))
        if item.get("emphasis") is not None and item.get("emphasis") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "OC006", "emphasis must be focal or normal", str(item.get("id"))))
    focus = _focus_list(payload)
    if not isinstance(focus, list) or any(value not in unit_ids for value in focus):
        diagnostics.append(DrawingDiagnostic("ERROR", "OC007", "focus must reference known unit ids"))
        focus = []
    focal = _focal_ids(units, focus)
    if len(focal) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "OC008", "org-chart supports at most one focal unit", ",".join(focal)))
    require_no_errors("schema", diagnostics)

    depths = _org_depths(units)
    if max(depths.values()) > 3:
        diagnostics.append(DrawingDiagnostic("ERROR", "OC009", "org-chart supports at most four levels"))
    leaves = [item["id"] for item in units if not any(other.get("parent") == item["id"] for other in units)]
    if len(leaves) > 8:
        diagnostics.append(DrawingDiagnostic("ERROR", "OC010", "org-chart supports at most eight leaf units"))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload)
    language = infer_language(payload["title"], (str(item["label"]) for item in units), payload.get("language"))
    semantic = OrgChartSemantic(payload["title"], tuple(units), focal, language)
    plan = OrgChartPlan("org-chart", payload["title"], tuple(units), focal, width, height, language)
    layout = _layout_org_chart(plan)
    scene = _resolve_org_chart(plan, layout)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _org_depths(units: list[dict[str, Any]]) -> dict[str, int]:
    parents = {str(item["id"]): item.get("parent") for item in units}
    depths: dict[str, int] = {}
    for item_id in parents:
        depth = 0
        cursor = parents[item_id]
        seen = {item_id}
        while cursor:
            if cursor in seen:
                raise ValueError("org-chart contains a parent cycle")
            seen.add(cursor)
            depth += 1
            cursor = parents.get(cursor)
        depths[item_id] = depth
    return depths


def _layout_org_chart(plan: OrgChartPlan) -> OrgChartLayout:
    units = list(plan.units)
    depths = _org_depths(units)
    children: dict[str, list[str]] = {str(item["id"]): [] for item in units}
    for item in units:
        parent = item.get("parent")
        if parent:
            children[str(parent)].append(str(item["id"]))
    root = next(str(item["id"]) for item in units if not item.get("parent"))
    slots: dict[str, float] = {}
    counter = [0]

    def assign(node: str) -> None:
        kids = children[node]
        if not kids:
            slots[node] = float(counter[0])
            counter[0] += 1
            return
        for kid in kids:
            assign(kid)
        slots[node] = (slots[kids[0]] + slots[kids[-1]]) / 2

    assign(root)
    leaf_count = max(1, counter[0])
    slot_width = (ORG_RIGHT - ORG_LEFT) / leaf_count
    box_width = _grid(min(184, max(88, slot_width - 24)))
    rows = max(depths.values()) + 1
    row_height = (ORG_BOTTOM - ORG_TOP) / rows
    box_height = _grid(min(76, max(48, row_height - 32)))
    boxes: dict[str, SceneBox] = {}
    for item in units:
        item_id = str(item["id"])
        center = ORG_LEFT + (slots[item_id] + 0.5) * slot_width
        top = _grid(ORG_TOP + depths[item_id] * row_height)
        boxes[item_id] = SceneBox(_grid(center - box_width / 2), top, box_width, box_height)
    connectors: dict[str, tuple[tuple[int, int], ...]] = {}
    for item in units:
        item_id = str(item["id"])
        parent = item.get("parent")
        if not parent:
            continue
        parent_box = boxes[str(parent)]
        box = boxes[item_id]
        start = (parent_box.x + parent_box.w // 2, parent_box.y + parent_box.h)
        end = (box.x + box.w // 2, box.y)
        middle = _grid((start[1] + end[1]) / 2)
        connectors[item_id] = ((start[0], start[1]), (start[0], middle), (end[0], middle), (end[0], end[1]))
    return OrgChartLayout(boxes, depths, connectors)


def _resolve_org_chart(plan: OrgChartPlan, layout: OrgChartLayout) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = []
    reading: list[str] = []
    for item in plan.units:
        item_id = str(item["id"])
        if item_id not in layout.connectors:
            continue
        primitives.append(ScenePolyline(f"link:{item_id}", layout.connectors[item_id], SceneStyle(stroke=theme.muted_stroke, stroke_width=1)))
    ordered = sorted(plan.units, key=lambda item: (layout.depths[str(item["id"])], layout.boxes[str(item["id"])].x))
    for item in ordered:
        item_id = str(item["id"])
        box = layout.boxes[item_id]
        focal = item_id in plan.focus
        fill = theme.brand_tint if focal else theme.ivory
        stroke = theme.brand if focal else theme.border
        center = box.x + box.w // 2
        children: list[object] = [
            SceneRect(f"box:{item_id}", box, SceneStyle(fill, stroke, 1.2 if focal else 1, radius=6)),
        ]
        lines = wrap_text(str(item["label"]), box.w - 16, 12, theme.serif, max_lines=2)
        label_top = box.y + (26 if len(lines) == 1 and not item.get("role") else 22)
        for line_index, line in enumerate(lines):
            children.append(SceneText(line, center, label_top + line_index * 15, theme.brand if focal else theme.near_black, 12, theme.serif, "middle", weight="500"))
        role = item.get("role")
        if isinstance(role, str) and role.strip():
            role_lines = wrap_text(role, box.w - 12, 9, theme.mono, max_lines=1)
            children.append(SceneText(role_lines[0], center, box.y + box.h - 12, theme.olive, 9, theme.mono, "middle"))
        primitives.append(SceneGroup(item_id, tuple(children)))
        reading.append(item_id)
    description = "Org chart " + plan.title + ". " + "; ".join(
        f"{item['label']}" + (f" ({item['role']})" if isinstance(item.get("role"), str) else "") + (f" reports to {item['parent']}" if item.get("parent") else " leads the organisation")
        for item in plan.units
    )
    return ResolvedScene(
        plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (),
        description=description, language=plan.language, reading_order=tuple(reading), primitives=tuple(primitives),
    )
