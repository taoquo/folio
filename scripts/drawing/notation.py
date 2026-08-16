from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .scene import (
    ResolvedScene,
    SceneBox,
    SceneGroup,
    SceneLine,
    ScenePath,
    ScenePolyline,
    SceneRect,
    SceneStyle,
    SceneText,
)
from .theme.folio import DEFAULT_FOLIO_THEME
from .canvas_contract import CANVAS_WIDTH, NOTATION_CANVAS
from .typography.roles import TextRole, resolve_text_style
from .typography.measure import measure_text
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
)
from .validation import DrawingDiagnostic


@dataclass(frozen=True)
class NotationSemantic:
    kind: str
    title: str
    marks: tuple[dict[str, Any], ...]
    language: str

    @property
    def nodes(self):
        return self.marks

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NotationPlan:
    kind: str
    title: str
    items: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...]
    width: int
    height: int
    language: str
    schema_version: str = "3.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NotationLayout:
    boxes: dict[str, SceneBox]
    relations: dict[str, tuple[tuple[int, int], ...]]


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)


# Width stays fixed because every gutter constant (the 60..900 grid band, the 232-unit box width,
# the sequence header pitch) is measured against the shared 960-unit canvas. Height is a real knob
# inside NOTATION_CANVAS: the notation grid and the sequence message band are derived from it, so
# taller or shorter diagrams keep the same title chrome and bottom margin.
NOTATION_WIDTH = CANVAS_WIDTH
SEQUENCE_HEIGHT_DEFAULT = 540
BOX_NOTATION_HEIGHT_DEFAULT = NOTATION_CANVAS.default


def _title(title: str, width: int) -> SceneText:
    theme = DEFAULT_FOLIO_THEME
    style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    return SceneText(title, width // 2, 40, style.color, style.size, style.family, "middle")


def _common(payload: dict[str, Any], kind: str, allowed: set[str], required: tuple[str, ...], code: str, height: int) -> list[DrawingDiagnostic]:
    diagnostics = common_payload_diagnostics(
        payload, kind=kind,
        allowed={"schema_version", "kind", "title", "language", "width", "height", *allowed},
        required=("schema_version", "kind", "title", *required), code=code,
        band=NOTATION_CANVAS, default_height=height,
    )
    if isinstance(payload.get("title"), str) and len(payload["title"].strip()) > 64:
        diagnostics.append(DrawingDiagnostic("ERROR", code, "title must contain at most 64 characters"))
    return diagnostics


def _bounded_text(items: Iterable[dict[str, Any]], fields: tuple[str, ...], diagnostics: list[DrawingDiagnostic], code: str, limit: int = 64) -> None:
    for item in items:
        for field in fields:
            value = item.get(field)
            if isinstance(value, str) and len(value.strip()) > limit:
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"{field} must contain at most {limit} characters", str(item.get("id"))))


def _chevron(item_id: str, start: tuple[int, int], end: tuple[int, int], color: str) -> ScenePolyline:
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        points = ((x2 - 8 if x2 > x1 else x2 + 8, y2 - 4), (x2, y2), (x2 - 8 if x2 > x1 else x2 + 8, y2 + 4))
    else:
        points = ((x2 - 4, y2 - 8 if y2 > y1 else y2 + 8), (x2, y2), (x2 + 4, y2 - 8 if y2 > y1 else y2 + 8))
    return ScenePolyline(item_id, points, SceneStyle("none", color, 1.2))


def compile_sequence_payload(payload: dict[str, Any]):
    diagnostics = _common(payload, "sequence", {"participants", "messages", "focus_participant"}, ("participants", "messages"), "SQ000", SEQUENCE_HEIGHT_DEFAULT)
    participants = object_list(payload, "participants", diagnostics, "SQ000")
    validate_object_fields(participants, name="participants", allowed={"id", "label", "kind"}, required=("id", "label", "kind"), diagnostics=diagnostics, code="SQ000")
    validate_item_strings(participants, ("label",), diagnostics=diagnostics, code="SQ000")
    participant_ids = validate_unique_ids(participants, name="sequence participant", diagnostics=diagnostics, code="SQ001")
    _bounded_text(participants, ("id", "label"), diagnostics, "SQ001", 40)
    if not 2 <= len(participants) <= 6:
        diagnostics.append(DrawingDiagnostic("ERROR", "SQ002", "sequence requires 2-6 participants"))
    for item in participants:
        if item.get("kind") not in {"actor", "system", "store"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SQ003", "participant kind must be actor, system, or store", str(item.get("id"))))

    messages = object_list(payload, "messages", diagnostics, "SQ000")
    validate_object_fields(messages, name="messages", allowed={"id", "source", "target", "label", "kind"}, required=("id", "source", "target", "label", "kind"), diagnostics=diagnostics, code="SQ000")
    validate_item_strings(messages, ("source", "target", "label"), diagnostics=diagnostics, code="SQ000")
    validate_unique_ids(messages, name="sequence message", diagnostics=diagnostics, code="SQ004")
    _bounded_text(messages, ("id", "label"), diagnostics, "SQ004", 48)
    if not 1 <= len(messages) <= 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "SQ005", "sequence requires 1-12 messages"))
    for item in messages:
        if item.get("source") not in participant_ids or item.get("target") not in participant_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "SQ006", "message references an unknown participant", str(item.get("id"))))
        if item.get("source") == item.get("target"):
            diagnostics.append(DrawingDiagnostic("ERROR", "SQ007", "self messages are not supported", str(item.get("id"))))
        if item.get("kind") not in {"sync", "async", "return"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SQ008", "message kind must be sync, async, or return", str(item.get("id"))))
    focus = payload.get("focus_participant")
    if focus is not None and (not isinstance(focus, str) or focus not in participant_ids):
        diagnostics.append(DrawingDiagnostic("ERROR", "SQ009", "focus_participant references an unknown participant", str(focus)))
    if 2 <= len(participants) <= 6:
        positions = [_grid(100 + index * 760 / max(1, len(participants) - 1)) for index in range(len(participants))]
        x_by_id = {item["id"]: x for item, x in zip(participants, positions) if isinstance(item.get("id"), str)}
        for item in participants:
            if isinstance(item.get("label"), str) and measure_text(item["label"], 10, DEFAULT_FOLIO_THEME.serif) > 112:
                diagnostics.append(DrawingDiagnostic("ERROR", "SQ010", "participant label does not fit the bounded header", str(item.get("id"))))
        for item in messages:
            if item.get("source") in x_by_id and item.get("target") in x_by_id and isinstance(item.get("label"), str):
                available = abs(x_by_id[item["target"]] - x_by_id[item["source"]]) - 16
                if measure_text(item["label"], 8, DEFAULT_FOLIO_THEME.mono) > available:
                    diagnostics.append(DrawingDiagnostic("ERROR", "SQ011", "message label does not fit between its participants", str(item.get("id"))))
    require_no_errors("schema", diagnostics)

    width, height = dimensions(payload, SEQUENCE_HEIGHT_DEFAULT, NOTATION_CANVAS)
    language = infer_language(payload["title"], [*(str(item["label"]) for item in participants), *(str(item["label"]) for item in messages)], payload.get("language"))
    marks = tuple(
        [*({**item, "id": f"participant:{item['id']}"} for item in participants), *({**item, "id": f"message:{item['id']}"} for item in messages)]
    )
    semantic = NotationSemantic("sequence", payload["title"], marks, language)
    plan = NotationPlan("sequence", payload["title"], tuple(participants), tuple(messages), width, height, language)
    layout, scene = _resolve_sequence(plan, focus)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _resolve_sequence(plan: NotationPlan, focus: str | None) -> tuple[NotationLayout, ResolvedScene]:
    theme = DEFAULT_FOLIO_THEME
    count = len(plan.items)
    positions = [_grid(100 + index * 760 / max(1, count - 1)) for index in range(count)]
    boxes = {item["id"]: SceneBox(x - 64, 72, 128, 44) for item, x in zip(plan.items, positions)}
    relations: dict[str, tuple[tuple[int, int], ...]] = {}
    primitives: list[object] = []
    first_message_y = 152
    message_band = max(0, plan.height - 96 - first_message_y)
    message_pitch = 28 if len(plan.relations) < 2 else int(min(64, max(28, message_band // (len(plan.relations) - 1))) // 4 * 4)
    last_message_y = first_message_y + max(0, len(plan.relations) - 1) * message_pitch
    lifeline_end = min(plan.height - 48, last_message_y + 32)
    for item, x in zip(plan.items, positions):
        color = theme.brand if item["id"] == focus else theme.near_black
        group_id = f"participant:{item['id']}"
        primitives.append(SceneGroup(group_id, (
            SceneRect(f"participant-box:{item['id']}", boxes[item["id"]], SceneStyle(theme.ivory, color, 1, radius=4)),
            SceneText(str(item["label"]), x, 98, color, 10, theme.serif, "middle", weight="500"),
            SceneText(str(item["kind"]).upper(), x, 110, theme.stone, 7, theme.mono, "middle", tracking=0.1),
        )))
        primitives.append(SceneLine(f"lifeline:{item['id']}", (x, 116), (x, lifeline_end), SceneStyle(stroke=theme.muted_stroke, stroke_width=1, dash=(6, 4))))
    x_by_id = {item["id"]: x for item, x in zip(plan.items, positions)}
    for index, item in enumerate(plan.relations):
        y = first_message_y + index * message_pitch
        start, end = (x_by_id[item["source"]], y), (x_by_id[item["target"]], y)
        relations[item["id"]] = (start, end)
        color = theme.near_black if item["kind"] == "sync" else theme.stone if item["kind"] == "return" else theme.olive
        dash = (5, 4) if item["kind"] == "return" else ()
        head = _chevron(f"message-head:{item['id']}", start, end, color)
        primitives.append(SceneGroup(f"message:{item['id']}", (
            SceneLine(f"message-line:{item['id']}", start, end, SceneStyle(stroke=color, stroke_width=1.2, dash=dash)),
            head,
            SceneText(str(item["label"]), _grid((start[0] + end[0]) / 2), y - 6, theme.near_black, 8, theme.mono, "middle"),
        )))
    description = "Sequence " + plan.title + ". Participants: " + ", ".join(str(item["label"]) for item in plan.items) + ". Messages: " + "; ".join(f"{item['source']} to {item['target']}: {item['label']} ({item['kind']})" for item in plan.relations)
    reading = tuple([*(f"participant:{item['id']}" for item in plan.items), *(f"message:{item['id']}" for item in plan.relations)])
    scene = ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), description=description, language=plan.language, reading_order=reading, primitives=tuple(primitives))
    return NotationLayout(boxes, relations), scene


def compile_uml_class_payload(payload: dict[str, Any]):
    diagnostics = _common(payload, "uml-class", {"layout", "types", "relationships", "focus"}, ("types", "relationships"), "UC000", BOX_NOTATION_HEIGHT_DEFAULT)
    if payload.get("layout", "class-grid") != "class-grid":
        diagnostics.append(DrawingDiagnostic("ERROR", "UC001", "uml-class layout must be class-grid"))
    types = object_list(payload, "types", diagnostics, "UC000")
    validate_object_fields(types, name="types", allowed={"id", "kind", "name", "attributes", "methods"}, required=("id", "kind", "name"), diagnostics=diagnostics, code="UC000")
    validate_item_strings(types, ("name",), diagnostics=diagnostics, code="UC000")
    type_ids = validate_unique_ids(types, name="UML type", diagnostics=diagnostics, code="UC002")
    _bounded_text(types, ("id", "name"), diagnostics, "UC002", 40)
    if not 1 <= len(types) <= 8:
        diagnostics.append(DrawingDiagnostic("ERROR", "UC003", "uml-class requires 1-8 types"))
    for item in types:
        if item.get("kind") not in {"class", "interface", "enum"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "UC004", "UML type kind must be class, interface, or enum", str(item.get("id"))))
        for field, limit in (("attributes", 6), ("methods", 5)):
            values = item.get(field, [])
            if not isinstance(values, list) or len(values) > limit or any(not isinstance(value, str) or not value.strip() or len(value.strip()) > 56 for value in values):
                diagnostics.append(DrawingDiagnostic("ERROR", "UC005", f"{field} must contain at most {limit} bounded strings", str(item.get("id"))))
        if isinstance(item.get("name"), str) and measure_text(item["name"], 11, DEFAULT_FOLIO_THEME.serif) > 212:
            diagnostics.append(DrawingDiagnostic("ERROR", "UC014", "UML type name does not fit the bounded header", str(item.get("id"))))
        members = [
            value
            for field in ("attributes", "methods")
            for value in (item.get(field, []) if isinstance(item.get(field, []), list) else [])
        ]
        for value in members:
            if isinstance(value, str) and measure_text(value, 8, DEFAULT_FOLIO_THEME.mono) > 212:
                diagnostics.append(DrawingDiagnostic("ERROR", "UC015", "UML member text does not fit the bounded type box", str(item.get("id"))))
    relationships = object_list(payload, "relationships", diagnostics, "UC000")
    validate_object_fields(relationships, name="relationships", allowed={"id", "source", "target", "kind", "label", "source_multiplicity", "target_multiplicity"}, required=("id", "source", "target", "kind"), diagnostics=diagnostics, code="UC000")
    validate_item_strings(relationships, ("source", "target", "kind", "label", "source_multiplicity", "target_multiplicity"), diagnostics=diagnostics, code="UC000")
    validate_unique_ids(relationships, name="UML relationship", diagnostics=diagnostics, code="UC006")
    if len(relationships) > 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "UC007", "uml-class supports at most 12 relationships"))
    pairs: set[tuple[str, str]] = set()
    for item in relationships:
        pair = (str(item.get("source")), str(item.get("target")))
        if pair[0] not in type_ids or pair[1] not in type_ids or pair[0] == pair[1]:
            diagnostics.append(DrawingDiagnostic("ERROR", "UC008", "relationship must reference two distinct known types", str(item.get("id"))))
        if pair in pairs:
            diagnostics.append(DrawingDiagnostic("ERROR", "UC009", "parallel directed UML relationships are not supported", str(item.get("id"))))
        pairs.add(pair)
        if item.get("kind") not in {"inheritance", "association", "aggregation", "composition"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "UC010", "unsupported UML relationship kind", str(item.get("id"))))
        _bounded_text((item,), ("id", "label", "source_multiplicity", "target_multiplicity"), diagnostics, "UC011", 40)
    focus = payload.get("focus")
    if focus is not None and (not isinstance(focus, str) or focus not in type_ids):
        diagnostics.append(DrawingDiagnostic("ERROR", "UC012", "focus references an unknown UML type", str(focus)))
    canvas_height = NOTATION_CANVAS.resolve(payload, BOX_NOTATION_HEIGHT_DEFAULT)
    _validate_grid_capacity(types, diagnostics, "UC013", er=False, canvas_height=canvas_height)
    require_no_errors("schema", diagnostics)

    boxes = _uml_grid(types, canvas_height)
    routes = {item["id"]: _box_route(boxes[item["source"]], boxes[item["target"]]) for item in relationships}
    language = infer_language(payload["title"], [*(str(item["name"]) for item in types), *(str(item.get("label", "")) for item in relationships)], payload.get("language"))
    marks = tuple([*({**item, "id": f"type:{item['id']}"} for item in types), *({**item, "id": f"relationship:{item['id']}"} for item in relationships)])
    semantic = NotationSemantic("uml-class", payload["title"], marks, language)
    plan = NotationPlan("uml-class", payload["title"], tuple(types), tuple(relationships), NOTATION_WIDTH, canvas_height, language)
    layout = NotationLayout(boxes, routes)
    diagnostics.extend(_validate_box_layout(plan, layout, "UC100"))
    scene = _resolve_box_notation(plan, layout, focus, er=False)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _grid_rows(count: int) -> tuple[int, int]:
    columns = 3 if count > 4 else 2
    return columns, max(1, (count + columns - 1) // columns)


def _cell_height(canvas_height: int, rows: int) -> float:
    """Row pitch inside the grid band: 76 units of title chrome on top, 64 of margin below."""
    return (canvas_height - 140) / rows


def _max_box_height(canvas_height: int, rows: int) -> float:
    return min(220, _cell_height(canvas_height, rows) - 36)


def _notation_grid(items: list[dict[str, Any]], height_of, canvas_height: int) -> dict[str, SceneBox]:
    columns, rows = _grid_rows(len(items))
    cell_h = _cell_height(canvas_height, rows)
    box_w = 232
    # Spread columns edge to edge across the 60..900 band instead of centering each box inside
    # its cell. The grid then fills the canvas and relationship routes gain room for labels.
    gutter = (840 - columns * box_w) / max(1, columns - 1)
    result = {}
    for index, item in enumerate(items):
        column, row = index % columns, index // columns
        height = min(_max_box_height(canvas_height, rows), height_of(item))
        result[item["id"]] = SceneBox(
            _grid(60 + column * (box_w + gutter)),
            _grid(76 + row * cell_h + (cell_h - height) / 2),
            box_w, _grid(height),
        )
    return result


def _uml_grid(types: list[dict[str, Any]], canvas_height: int) -> dict[str, SceneBox]:
    return _notation_grid(types, _uml_box_height, canvas_height)


def compile_er_payload(payload: dict[str, Any]):
    diagnostics = _common(payload, "er-diagram", {"entities", "relationships", "focus_entity"}, ("entities", "relationships"), "ER000", BOX_NOTATION_HEIGHT_DEFAULT)
    entities = object_list(payload, "entities", diagnostics, "ER000")
    validate_object_fields(entities, name="entities", allowed={"id", "name", "fields"}, required=("id", "name", "fields"), diagnostics=diagnostics, code="ER000")
    validate_item_strings(entities, ("name",), diagnostics=diagnostics, code="ER000")
    entity_ids = validate_unique_ids(entities, name="ER entity", diagnostics=diagnostics, code="ER001")
    _bounded_text(entities, ("id", "name"), diagnostics, "ER001", 40)
    if not 2 <= len(entities) <= 8:
        diagnostics.append(DrawingDiagnostic("ERROR", "ER002", "ER diagram requires 2-8 entities"))
    for entity in entities:
        fields = entity.get("fields")
        if not isinstance(fields, list) or not 1 <= len(fields) <= 8:
            diagnostics.append(DrawingDiagnostic("ERROR", "ER003", "entity requires 1-8 fields", str(entity.get("id"))))
            continue
        validate_object_fields(fields, name=f"entity {entity.get('id')} fields", allowed={"id", "name", "type", "primary_key", "foreign_key", "nullable"}, required=("id", "name", "type"), diagnostics=diagnostics, code="ER004")
        validate_item_strings(fields, ("name", "type"), diagnostics=diagnostics, code="ER004")
        validate_unique_ids(fields, name=f"entity {entity.get('id')} field", diagnostics=diagnostics, code="ER004")
        _bounded_text(fields, ("id", "name", "type"), diagnostics, "ER004", 32)
        if not any(item.get("primary_key") is True for item in fields):
            diagnostics.append(DrawingDiagnostic("ERROR", "ER005", "each entity requires at least one primary key", str(entity.get("id"))))
        for field in fields:
            for flag in ("primary_key", "foreign_key", "nullable"):
                if flag in field and not isinstance(field[flag], bool):
                    diagnostics.append(DrawingDiagnostic("ERROR", "ER006", f"{flag} must be boolean", str(field.get("id"))))
            if field.get("primary_key") is True and field.get("nullable") is True:
                diagnostics.append(DrawingDiagnostic("ERROR", "ER018", "primary key fields cannot be nullable", str(field.get("id"))))
        if isinstance(entity.get("name"), str) and measure_text(entity["name"], 11, DEFAULT_FOLIO_THEME.serif) > 212:
            diagnostics.append(DrawingDiagnostic("ERROR", "ER015", "entity name does not fit the bounded header", str(entity.get("id"))))
        for field in fields:
            if isinstance(field.get("name"), str) and measure_text(field["name"], 8, DEFAULT_FOLIO_THEME.mono) > 112:
                diagnostics.append(DrawingDiagnostic("ERROR", "ER016", "field name does not fit the bounded field row", str(field.get("id"))))
            if isinstance(field.get("type"), str) and measure_text(field["type"], 8, DEFAULT_FOLIO_THEME.mono) > 64:
                diagnostics.append(DrawingDiagnostic("ERROR", "ER017", "field type does not fit the bounded field row", str(field.get("id"))))
    relationships = object_list(payload, "relationships", diagnostics, "ER000")
    validate_object_fields(relationships, name="relationships", allowed={"id", "source", "target", "label", "source_cardinality", "target_cardinality"}, required=("id", "source", "target", "label", "source_cardinality", "target_cardinality"), diagnostics=diagnostics, code="ER000")
    validate_item_strings(relationships, ("source", "target", "label", "source_cardinality", "target_cardinality"), diagnostics=diagnostics, code="ER000")
    validate_unique_ids(relationships, name="ER relationship", diagnostics=diagnostics, code="ER007")
    if not 1 <= len(relationships) <= 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "ER008", "ER diagram requires 1-12 relationships"))
    pairs: set[tuple[str, str]] = set()
    cardinalities = {"one", "zero-or-one", "many", "one-or-many"}
    for item in relationships:
        pair = (str(item.get("source")), str(item.get("target")))
        if pair[0] not in entity_ids or pair[1] not in entity_ids or pair[0] == pair[1]:
            diagnostics.append(DrawingDiagnostic("ERROR", "ER009", "relationship must reference two distinct known entities", str(item.get("id"))))
        if pair in pairs:
            diagnostics.append(DrawingDiagnostic("ERROR", "ER010", "parallel directed ER relationships are not supported", str(item.get("id"))))
        pairs.add(pair)
        if item.get("source_cardinality") not in cardinalities or item.get("target_cardinality") not in cardinalities:
            diagnostics.append(DrawingDiagnostic("ERROR", "ER011", "relationship cardinality is invalid", str(item.get("id"))))
        _bounded_text((item,), ("id", "label"), diagnostics, "ER012", 40)
    focus = payload.get("focus_entity")
    if focus is not None and (not isinstance(focus, str) or focus not in entity_ids):
        diagnostics.append(DrawingDiagnostic("ERROR", "ER013", "focus_entity references an unknown entity", str(focus)))
    canvas_height = NOTATION_CANVAS.resolve(payload, BOX_NOTATION_HEIGHT_DEFAULT)
    _validate_grid_capacity(entities, diagnostics, "ER014", er=True, canvas_height=canvas_height)
    require_no_errors("schema", diagnostics)

    boxes = _entity_grid(entities, canvas_height)
    routes = {item["id"]: _box_route(boxes[item["source"]], boxes[item["target"]]) for item in relationships}
    language = infer_language(payload["title"], [*(str(item["name"]) for item in entities), *(str(item["label"]) for item in relationships)], payload.get("language"))
    marks = tuple([*({**item, "id": f"entity:{item['id']}"} for item in entities), *({**item, "id": f"relationship:{item['id']}"} for item in relationships)])
    semantic = NotationSemantic("er-diagram", payload["title"], marks, language)
    plan = NotationPlan("er-diagram", payload["title"], tuple(entities), tuple(relationships), NOTATION_WIDTH, canvas_height, language)
    layout = NotationLayout(boxes, routes)
    diagnostics.extend(_validate_box_layout(plan, layout, "ER100"))
    scene = _resolve_box_notation(plan, layout, focus, er=True)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _entity_grid(entities: list[dict[str, Any]], canvas_height: int) -> dict[str, SceneBox]:
    return _notation_grid(entities, lambda item: 52 + 24 * len(item["fields"]), canvas_height)


def _box_route(source: SceneBox, target: SceneBox) -> tuple[tuple[int, int], ...]:
    source_center = (_grid(source.x + source.w / 2), _grid(source.y + source.h / 2))
    target_center = (_grid(target.x + target.w / 2), _grid(target.y + target.h / 2))
    if target.y >= source.y + source.h:
        start = (source_center[0], source.y + source.h)
        end = (target_center[0], target.y)
        middle = _grid((start[1] + end[1]) / 2)
        return _normalize_route((start, (start[0], middle), (end[0], middle), end))
    if source.y >= target.y + target.h:
        start = (source_center[0], source.y)
        end = (target_center[0], target.y + target.h)
        middle = _grid((start[1] + end[1]) / 2)
        return _normalize_route((start, (start[0], middle), (end[0], middle), end))
    if abs(target_center[0] - source_center[0]) >= abs(target_center[1] - source_center[1]):
        start = (source.x + source.w if target_center[0] > source_center[0] else source.x, source_center[1])
        end = (target.x if target_center[0] > source_center[0] else target.x + target.w, target_center[1])
        middle = _grid((start[0] + end[0]) / 2)
        return _normalize_route((start, (middle, start[1]), (middle, end[1]), end))
    start = (source_center[0], source.y + source.h if target_center[1] > source_center[1] else source.y)
    end = (target_center[0], target.y if target_center[1] > source_center[1] else target.y + target.h)
    middle = _grid((start[1] + end[1]) / 2)
    return _normalize_route((start, (start[0], middle), (end[0], middle), end))


def _normalize_route(points: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    return tuple(result)


def _validate_grid_capacity(items: list[dict[str, Any]], diagnostics: list[DrawingDiagnostic], code: str, *, er: bool, canvas_height: int) -> None:
    _, rows = _grid_rows(len(items))
    maximum_height = _max_box_height(canvas_height, rows)
    for item in items:
        if er:
            fields = item.get("fields", [])
            required = 52 + 16 * (len(fields) if isinstance(fields, list) else 0)
        else:
            attributes, methods = item.get("attributes", []), item.get("methods", [])
            required = _uml_box_height({"attributes": attributes, "methods": methods})
        if required > maximum_height:
            diagnostics.append(DrawingDiagnostic(
                "ERROR", code,
                "item content density cannot fit the bounded notation grid; split the diagram or reduce members",
                str(item.get("id")),
            ))


def _touches_box(point: tuple[int, int], box: SceneBox) -> bool:
    x, y = point
    return (
        (x in {box.x, box.x + box.w} and box.y <= y <= box.y + box.h)
        or (y in {box.y, box.y + box.h} and box.x <= x <= box.x + box.w)
    )


def _boxes_overlap(left: SceneBox, right: SceneBox, padding: int = 8) -> bool:
    return not (
        left.x + left.w + padding <= right.x
        or right.x + right.w + padding <= left.x
        or left.y + left.h + padding <= right.y
        or right.y + right.h + padding <= left.y
    )


def _segment_crosses_box(start: tuple[int, int], end: tuple[int, int], box: SceneBox) -> bool:
    if start[0] == end[0]:
        low, high = sorted((start[1], end[1]))
        return box.x < start[0] < box.x + box.w and low < box.y + box.h and high > box.y
    if start[1] == end[1]:
        low, high = sorted((start[0], end[0]))
        return box.y < start[1] < box.y + box.h and low < box.x + box.w and high > box.x
    return True


def _validate_box_layout(plan: NotationPlan, layout: NotationLayout, code: str) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    boxes = list(layout.boxes.items())
    for index, (item_id, box) in enumerate(boxes):
        if box.x < 0 or box.y < 0 or box.x + box.w > plan.width or box.y + box.h > plan.height:
            diagnostics.append(DrawingDiagnostic("ERROR", code, "notation item is outside the canvas", item_id))
        if any(value % 4 for value in (box.x, box.y, box.w, box.h)):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "notation item is off the 4-unit grid", item_id))
        for other_id, other in boxes[index + 1:]:
            if _boxes_overlap(box, other):
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"notation item overlaps {other_id}", item_id))
    relation_by_id = {item["id"]: item for item in plan.relations}
    for relation_id, route in layout.relations.items():
        relation = relation_by_id[relation_id]
        if len(route) < 2 or any(start == end for start, end in zip(route, route[1:])):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "relationship route is empty or contains a zero-length segment", relation_id))
            continue
        if any(value % 4 for point in route for value in point):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "relationship route is off the 4-unit grid", relation_id))
        if any(start[0] != end[0] and start[1] != end[1] for start, end in zip(route, route[1:])):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "relationship route must be orthogonal", relation_id))
        if not _touches_box(route[0], layout.boxes[relation["source"]]) or not _touches_box(route[-1], layout.boxes[relation["target"]]):
            diagnostics.append(DrawingDiagnostic("ERROR", code, "relationship endpoint is detached", relation_id))
        for item_id, box in boxes:
            if item_id in {relation["source"], relation["target"]}:
                continue
            if any(_segment_crosses_box(start, end, box) for start, end in zip(route, route[1:])):
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"relationship crosses unrelated item {item_id}", relation_id))
        label = relation.get("label")
        if isinstance(label, str):
            longest = max(abs(end[0] - start[0]) + abs(end[1] - start[1]) for start, end in zip(route, route[1:]))
            if measure_text(label, 8, DEFAULT_FOLIO_THEME.mono) > max(0, longest - 8):
                diagnostics.append(DrawingDiagnostic("ERROR", code, "relationship label does not fit its route", relation_id))
    return diagnostics


def _resolve_box_notation(plan: NotationPlan, layout: NotationLayout, focus: str | None, *, er: bool) -> ResolvedScene:
    theme = DEFAULT_FOLIO_THEME
    primitives: list[object] = []
    for relation in plan.relations:
        route = layout.relations[relation["id"]]
        children: list[object] = [ScenePolyline(f"relationship-line:{relation['id']}", route, SceneStyle("none", theme.olive, 1.2))]
        if er:
            children.extend([
                SceneText(_cardinality(str(relation["source_cardinality"])), route[0][0] + 8, route[0][1] - 6, theme.stone, 8, theme.mono),
                SceneText(_cardinality(str(relation["target_cardinality"])), route[-1][0] - 8, route[-1][1] - 6, theme.stone, 8, theme.mono, "end"),
            ])
        else:
            kind = relation["kind"]
            if kind == "association":
                children.append(_chevron(f"relationship-head:{relation['id']}", route[-2], route[-1], theme.olive))
            elif kind == "inheritance":
                children.append(_triangle(f"relationship-head:{relation['id']}", route[-2], route[-1], theme.parchment, theme.olive))
            elif kind in {"aggregation", "composition"}:
                children.append(_diamond(f"relationship-head:{relation['id']}", route[1], route[0], theme.olive if kind == "composition" else theme.parchment, theme.olive))
            if relation.get("source_multiplicity"):
                children.append(SceneText(str(relation["source_multiplicity"]), route[0][0] + 8, route[0][1] - 6, theme.stone, 8, theme.mono))
            if relation.get("target_multiplicity"):
                children.append(SceneText(str(relation["target_multiplicity"]), route[-1][0] - 8, route[-1][1] - 6, theme.stone, 8, theme.mono, "end"))
        if relation.get("label"):
            middle = _longest_segment_midpoint(route)
            children.append(SceneText(str(relation["label"]), middle[0], middle[1] - 8, theme.stone, 8, theme.mono, "middle"))
        primitives.append(SceneGroup(f"relationship:{relation['id']}", tuple(children)))
    for item in plan.items:
        box = layout.boxes[item["id"]]
        color = theme.brand if item["id"] == focus else theme.near_black
        children: list[object] = [
            SceneRect(f"item-box:{item['id']}", box, SceneStyle(theme.ivory, color, 1, radius=4)),
            SceneLine(f"item-header:{item['id']}", (box.x, box.y + 36), (box.x + box.w, box.y + 36), SceneStyle(stroke=theme.border, stroke_width=1)),
            SceneText(str(item.get("name")), box.x + box.w // 2, box.y + 24, color, 11, theme.serif, "middle", weight="500"),
        ]
        if er:
            for index, field in enumerate(item["fields"]):
                y = box.y + 58 + index * 24
                key = "PK" if field.get("primary_key") else "FK" if field.get("foreign_key") else ""
                nullable = "?" if field.get("nullable") else ""
                children.append(SceneText(key, box.x + 10, y, theme.brand if key == "PK" else theme.stone, 7, theme.mono))
                children.append(SceneText(str(field["name"]), box.x + 38, y, theme.near_black, 8, theme.mono))
                children.append(SceneText(str(field["type"]) + nullable, box.x + box.w - 10, y, theme.stone, 8, theme.mono, "end"))
        else:
            attributes = item.get("attributes", [])
            methods = item.get("methods", [])
            children.append(SceneText(f"«{item['kind']}»", box.x + box.w // 2, box.y + 12, theme.stone, 7, theme.mono, "middle"))
            for index, value in enumerate(attributes):
                children.append(SceneText(str(value), box.x + 10, box.y + 52 + index * 18, theme.olive, 8, theme.mono))
            methods_y = box.y + 52 + len(attributes) * 18
            if attributes and methods:
                divider = methods_y - 4
                children.append(SceneLine(f"item-divider:{item['id']}", (box.x, divider), (box.x + box.w, divider), SceneStyle(stroke=theme.border, stroke_width=1)))
                methods_y += 8
            for index, value in enumerate(methods):
                children.append(SceneText(str(value), box.x + 10, methods_y + index * 18, theme.near_black, 8, theme.mono))
        primitives.append(SceneGroup(("entity:" if er else "type:") + str(item["id"]), tuple(children)))
    item_label = "Entities" if er else "Types"
    description = f"{'ER diagram' if er else 'UML class diagram'} {plan.title}. {item_label}: " + "; ".join(_item_description(item, er) for item in plan.items) + ". Relationships: " + "; ".join(_relation_description(item, er) for item in plan.relations)
    reading = tuple([*(("entity:" if er else "type:") + str(item["id"]) for item in plan.items), *(f"relationship:{item['id']}" for item in plan.relations)])
    return ResolvedScene(plan.width, plan.height, theme.parchment, _title(plan.title, plan.width), (), (), (), description=description, language=plan.language, reading_order=reading, primitives=tuple(primitives))


def _longest_segment_midpoint(route: tuple[tuple[int, int], ...]) -> tuple[int, int]:
    start, end = max(
        zip(route, route[1:]),
        key=lambda pair: abs(pair[1][0] - pair[0][0]) + abs(pair[1][1] - pair[0][1]),
    )
    return _grid((start[0] + end[0]) / 2), _grid((start[1] + end[1]) / 2)


def _uml_box_height(item: dict[str, Any]) -> int:
    attributes = item.get("attributes", [])
    methods = item.get("methods", [])
    attribute_count = len(attributes) if isinstance(attributes, list) else 0
    method_count = len(methods) if isinstance(methods, list) else 0
    divider_space = 8 if attribute_count and method_count else 0
    return max(64, 56 + 18 * (attribute_count + method_count) + divider_space)


def _cardinality(value: str) -> str:
    return {"one": "1", "zero-or-one": "0..1", "many": "*", "one-or-many": "1..*"}[value]


def _item_description(item: dict[str, Any], er: bool) -> str:
    if er:
        return f"{item['name']} with fields " + ", ".join(f"{field['name']} {field['type']}" for field in item["fields"])
    return f"{item['name']} ({item['kind']}) with attributes " + ", ".join(item.get("attributes", []) or ["none"]) + " and methods " + ", ".join(item.get("methods", []) or ["none"])


def _relation_description(item: dict[str, Any], er: bool) -> str:
    if er:
        return f"{item['source']} {item['source_cardinality']} to {item['target']} {item['target_cardinality']}: {item['label']}"
    return f"{item['source']} to {item['target']}: {item['kind']}" + (f" {item['label']}" if item.get("label") else "")


def _triangle(item_id: str, toward: tuple[int, int], tip: tuple[int, int], fill: str, stroke: str) -> ScenePath:
    x1, y1 = toward
    x2, y2 = tip
    if abs(x2 - x1) >= abs(y2 - y1):
        base_x = x2 - 12 if x2 > x1 else x2 + 12
        points = ((x2, y2), (base_x, y2 - 7), (base_x, y2 + 7))
    else:
        base_y = y2 - 12 if y2 > y1 else y2 + 12
        points = ((x2, y2), (x2 - 7, base_y), (x2 + 7, base_y))
    return ScenePath(item_id, "M " + " L ".join(f"{x} {y}" for x, y in points) + " Z", SceneStyle(fill, stroke, 1.2))


def _diamond(item_id: str, toward: tuple[int, int], tip: tuple[int, int], fill: str, stroke: str) -> ScenePath:
    x1, y1 = toward
    x2, y2 = tip
    if abs(x2 - x1) >= abs(y2 - y1):
        sign = 1 if x1 > x2 else -1
        points = ((x2, y2), (x2 + sign * 8, y2 - 5), (x2 + sign * 16, y2), (x2 + sign * 8, y2 + 5))
    else:
        sign = 1 if y1 > y2 else -1
        points = ((x2, y2), (x2 - 5, y2 + sign * 8), (x2, y2 + sign * 16), (x2 + 5, y2 + sign * 8))
    return ScenePath(item_id, "M " + " L ".join(f"{x} {y}" for x, y in points) + " Z", SceneStyle(fill, stroke, 1.2))
