from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from typing import Any

from .canvas_contract import GRAPH_CANVAS, canvas_mode
from .layout.graph_geometry import DEFAULT_GRAPH_GEOMETRY, GraphGeometry, graph_geometry_for_stage
from .layout.models import LayoutBox
from .scene import ResolvedScene, SceneBox, ScenePolyline, SceneRegion, SceneStyle
from .stage import current as current_stage
from .theme.folio import DEFAULT_FOLIO_THEME
from .typography.fit import _wrap as _staged_wrap
from .typography.fit import fit_wrap_width
from .typography.measure import measure_text
from .typography.roles import TextRole, resolve_text_style, role_text
from .v3_common import (
    GraphComposition,
    GraphEdgePlan,
    GraphNodePlan,
    GraphPlan,
    choose_graph_composition,
    common_payload_diagnostics,
    cycle_exists,
    dimensions,
    fit_layered_graph_height,
    graph_axis_fits,
    graph_depths,
    infer_language,
    layout_layered_graph,
    layout_result,
    object_list,
    reachable,
    require_no_errors,
    resolve_graph_scene,
    route_graph_edges,
    validate_distinguishable_parallel_edges,
    validate_item_strings,
    validate_no_self_edges,
    validate_object_fields,
    validate_resolved_scene,
    validate_unique_ids,
)
from .validation import DrawingDiagnostic


@dataclass(frozen=True)
class StateMachineSemantic:
    title: str
    states: tuple[dict[str, Any], ...]
    transitions: tuple[dict[str, Any], ...]
    persistent: bool
    submachine: bool
    language: str

    @property
    def nodes(self) -> tuple[dict[str, Any], ...]:
        return self.states

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SwimlaneSemantic:
    title: str
    lanes: tuple[dict[str, Any], ...]
    steps: tuple[dict[str, Any], ...]
    flows: tuple[dict[str, Any], ...]
    language: str

    @property
    def nodes(self) -> tuple[dict[str, Any], ...]:
        return self.steps

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TreeSemantic:
    title: str
    nodes: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...]
    focus_root: str | None
    language: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LayerStackSemantic:
    title: str
    layers: tuple[dict[str, Any], ...]
    flows: tuple[dict[str, Any], ...]
    language: str

    @property
    def nodes(self) -> tuple[dict[str, Any], ...]:
        return self.layers

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_state_machine_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload,
        kind="state-machine",
        allowed={"schema_version", "kind", "title", "states", "transitions", "persistent", "submachine", "axis", "focus", "width", "height", "language"},
        required=("schema_version", "kind", "title", "states", "transitions"),
        code="SM000",
    )
    states = object_list(payload, "states", diagnostics, "SM000")
    transitions = object_list(payload, "transitions", diagnostics, "SM000")
    validate_object_fields(
        states, name="states", allowed={"id", "type", "label", "description", "emphasis"},
        required=("id", "type"), diagnostics=diagnostics, code="SM000",
    )
    validate_object_fields(
        transitions, name="transitions", allowed={"id", "source", "target", "event", "guard", "action", "channel"},
        required=("id", "source", "target"), diagnostics=diagnostics, code="SM000",
    )
    validate_item_strings(states, ("label", "description"), diagnostics=diagnostics, code="SM000")
    validate_item_strings(transitions, ("event", "guard", "action"), diagnostics=diagnostics, code="SM000")
    state_ids = validate_unique_ids(states, name="state", diagnostics=diagnostics, code="SM001")
    validate_unique_ids(transitions, name="transition", diagnostics=diagnostics, code="SM002")
    if not states or len(states) > 9:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM003", "state machine requires 1-9 visual states"))
    if len(transitions) > 14:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM004", "state machine exceeds 14 transitions"))
    state_types = {"state", "initial", "final", "choice"}
    for item in states:
        if item.get("type") not in state_types:
            diagnostics.append(DrawingDiagnostic("ERROR", "SM005", "unknown state type", str(item.get("id"))))
        if item.get("type") not in {"initial", "final"} and (not isinstance(item.get("label"), str) or not item.get("label", "").strip()):
            diagnostics.append(DrawingDiagnostic("ERROR", "SM006", "visible states require a label", str(item.get("id"))))
        if item.get("emphasis", "normal") not in {"focal", "normal", "background"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SM007", "invalid state emphasis", str(item.get("id"))))
    initial = [item["id"] for item in states if item.get("type") == "initial" and isinstance(item.get("id"), str)]
    finals = [item["id"] for item in states if item.get("type") == "final" and isinstance(item.get("id"), str)]
    choices = [item for item in states if item.get("type") == "choice"]
    if len(choices) > 2:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM019", "state machine permits at most two choices"))
    if not payload.get("submachine") and len(initial) != 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM008", "state machine requires exactly one initial entry"))
    if not payload.get("persistent") and not finals:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM009", "state machine requires a final state or persistent=true"))
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in transitions:
        source, target = item.get("source"), item.get("target")
        if source not in state_ids or target not in state_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "SM010", "transition references unknown state", str(item.get("id"))))
        if item.get("channel", "normal") not in {"normal", "exceptional", "reset", "focal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SM011", "invalid transition channel", str(item.get("id"))))
        if isinstance(source, str):
            outgoing[source].append(item)
    for final in finals:
        if any(item.get("channel", "normal") == "normal" for item in outgoing[final]):
            diagnostics.append(DrawingDiagnostic("ERROR", "SM012", "final states cannot have ordinary outgoing transitions", final))
    for choice in choices:
        guards = [str(item.get("guard", "")).strip() for item in outgoing.get(choice.get("id"), [])]
        if len(guards) < 2 or any(not guard for guard in guards) or len(guards) != len(set(guards)):
            diagnostics.append(DrawingDiagnostic("ERROR", "SM013", "choice exits require unique non-empty guards", str(choice.get("id"))))
    edge_pairs = [(str(item.get("source")), str(item.get("target"))) for item in transitions]
    reached = reachable(initial, edge_pairs)
    for state_id in state_ids - reached if initial else set():
        diagnostics.append(DrawingDiagnostic("ERROR", "SM014", "unreachable state", state_id))
    if finals and not any(item in reached for item in finals):
        diagnostics.append(DrawingDiagnostic("ERROR", "SM015", "no final state is reachable"))
    focus = payload.get("focus")
    if focus is not None and focus not in state_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM016", "focus references unknown state", str(focus)))
    focal_ids = [item.get("id") for item in states if item.get("emphasis") == "focal"]
    if focus:
        focal_ids.append(focus)
    if len(set(focal_ids)) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM017", "state machine permits one focal state"))
    visible_labels = sum(bool(item.get("event") or item.get("guard")) for item in transitions)
    if visible_labels > 6:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM018", "state machine exceeds 6 visible transition labels"))
    if _maximum_cycle_rank(state_ids, edge_pairs) > 2:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM020", "state machine exceeds cycle nesting depth 2"))
    for field in ("persistent", "submachine"):
        if field in payload and not isinstance(payload[field], bool):
            diagnostics.append(DrawingDiagnostic("ERROR", "SM021", f"{field} must be boolean"))
    axis = payload.get("axis", "left-right")
    if axis not in {"left-right", "top-down"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "SM022", "state-machine axis must be left-right or top-down"))
    validate_distinguishable_parallel_edges(
        transitions, diagnostics=diagnostics, code="SM023", label_fields=("event", "guard", "action"),
    )
    validate_no_self_edges(transitions, diagnostics=diagnostics, code="SM024")
    require_no_errors("schema", diagnostics)

    language = infer_language(payload["title"], (str(item.get("label", "")) for item in states), payload.get("language"))
    semantic = StateMachineSemantic(payload["title"], tuple(states), tuple(transitions), bool(payload.get("persistent")), bool(payload.get("submachine")), language)
    node_plans = tuple(
        GraphNodePlan(
            item["id"], str(item.get("label", "")), str(item["type"]),
            "focal" if item.get("id") == focus else str(item.get("emphasis", "normal")),
            str(item.get("description")) if item.get("description") else None,
        )
        for item in states
    )
    edge_plans = tuple(
        GraphEdgePlan(
            item["id"], item["source"], item["target"], str(item.get("channel", "normal")),
            _state_transition_label(item),
        )
        for item in transitions
    )
    width, height = dimensions(payload)
    graph_cycles = cycle_exists(state_ids, edge_pairs)
    branching = any(item.get("type") == "choice" for item in states)
    pattern = "cyclic" if graph_cycles else "branching" if branching else "linear"
    plan = GraphPlan("state-machine", payload["title"], GraphComposition(pattern, axis, tuple(initial)), node_plans, edge_plans, width, height, language)
    stage = current_stage()
    geometry = graph_geometry_for_stage(stage)
    composition_axis, fold = axis, 0
    if stage.is_default:
        if "height" not in payload:
            # A left-right lifecycle occupies one band. Trim the default 16:9 canvas to the band it
            # needs so the diagram is not stranded in the vertical middle of empty parchment.
            plan = replace(plan, height=fit_layered_graph_height(plan))
    else:
        composition_axis, fold = choose_graph_composition(
            plan, geometry, width, GRAPH_CANVAS.ceiling(canvas_mode(payload)))
        if not graph_axis_fits(
                plan, geometry, composition_axis, fold, width,
                GRAPH_CANVAS.ceiling(canvas_mode(payload))):
            diagnostics.append(DrawingDiagnostic(
                "ERROR", "SM025", "state machine cannot compose on this stage", "state-machine"))
            require_no_errors("stage", diagnostics)
        if composition_axis != axis:
            plan = replace(
                plan, composition=GraphComposition(pattern, composition_axis, tuple(initial)))
        fitted = fit_layered_graph_height(
            plan, geometry, axis=composition_axis, fold=fold)
        plan = replace(plan, height=max(fitted, GRAPH_CANVAS.minimum_at(width)))
    layout = layout_layered_graph(
        plan, geometry, axis=composition_axis, fold=fold)
    scene = resolve_graph_scene(
        plan, layout, description=_state_description(semantic), geometry=geometry)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _state_transition_label(item: dict[str, Any]) -> str | None:
    parts = []
    if item.get("event"):
        parts.append(str(item["event"]))
    if item.get("guard"):
        parts.append(f"[{item['guard']}]")
    if item.get("action"):
        parts.append(f"/ {item['action']}")
    return " ".join(parts) or None


def _maximum_cycle_rank(node_ids: set[str], edges: list[tuple[str, str]]) -> int:
    remaining = set(node_ids)
    maximum = 0
    while remaining:
        seed = min(remaining)
        from_seed = reachable([seed], edges)
        component = {node for node in remaining if node in from_seed and seed in reachable([node], edges)}
        remaining -= component
        internal_edges = sum(source in component and target in component for source, target in edges)
        if len(component) > 1 or any(source == target and source in component for source, target in edges):
            maximum = max(maximum, internal_edges - len(component) + 1)
    return maximum


def _state_description(semantic: StateMachineSemantic) -> str:
    labels = ", ".join(str(item.get("label") or item.get("type")) for item in semantic.states)
    return f"State machine {semantic.title}. States: {labels}."


def compile_swimlane_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload,
        kind="swimlane",
        allowed={"schema_version", "kind", "title", "lanes", "steps", "flows", "axis", "parallel_starts", "focus_lane", "focus_path", "width", "height", "language"},
        required=("schema_version", "kind", "title", "lanes", "steps", "flows"),
        code="SW000",
    )
    lanes = object_list(payload, "lanes", diagnostics, "SW000")
    steps = object_list(payload, "steps", diagnostics, "SW000")
    flows = object_list(payload, "flows", diagnostics, "SW000")
    validate_object_fields(lanes, name="lanes", allowed={"id", "label", "emphasis"}, required=("id", "label"), diagnostics=diagnostics, code="SW000")
    validate_object_fields(steps, name="steps", allowed={"id", "label", "type", "lane", "emphasis"}, required=("id", "label", "type", "lane"), diagnostics=diagnostics, code="SW000")
    validate_object_fields(flows, name="flows", allowed={"id", "source", "target", "channel", "label"}, required=("id", "source", "target"), diagnostics=diagnostics, code="SW000")
    validate_item_strings(lanes, ("label",), diagnostics=diagnostics, code="SW000")
    validate_item_strings(steps, ("label",), diagnostics=diagnostics, code="SW000")
    validate_item_strings(flows, ("label",), diagnostics=diagnostics, code="SW000")
    lane_ids = validate_unique_ids(lanes, name="lane", diagnostics=diagnostics, code="SW001")
    step_ids = validate_unique_ids(steps, name="step", diagnostics=diagnostics, code="SW002")
    validate_unique_ids(flows, name="flow", diagnostics=diagnostics, code="SW003")
    if not 2 <= len(lanes) <= 5:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW004", "swimlane requires 2-5 lanes"))
    if not steps or len(steps) > 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW005", "swimlane requires 1-12 steps"))
    step_types = {"action", "decision", "data", "terminal"}
    step_lane: dict[str, str] = {}
    for item in steps:
        if item.get("lane") not in lane_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "SW006", "step references unknown lane", str(item.get("id"))))
        if item.get("type") not in step_types:
            diagnostics.append(DrawingDiagnostic("ERROR", "SW007", "unknown step type", str(item.get("id"))))
        if item.get("emphasis", "normal") not in {"focal", "normal", "background"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SW018", "invalid step emphasis", str(item.get("id"))))
        if isinstance(item.get("id"), str) and isinstance(item.get("lane"), str):
            step_lane[item["id"]] = item["lane"]
    if sum(item.get("type") == "decision" for item in steps) > 3:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW008", "swimlane exceeds 3 decisions"))
    incoming: Counter[str] = Counter()
    handoffs = 0
    edge_pairs: list[tuple[str, str]] = []
    for item in flows:
        source, target = item.get("source"), item.get("target")
        if source not in step_ids or target not in step_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "SW009", "flow references unknown step", str(item.get("id"))))
        channel = item.get("channel", "sequence")
        if channel not in {"sequence", "request", "response", "async"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SW010", "invalid handoff channel", str(item.get("id"))))
        if source in step_lane and target in step_lane and step_lane[source] != step_lane[target]:
            handoffs += 1
            if channel == "sequence":
                diagnostics.append(DrawingDiagnostic("ERROR", "SW011", "cross-lane flow requires request, response, or async channel", str(item.get("id"))))
        if isinstance(source, str) and isinstance(target, str):
            edge_pairs.append((source, target))
            incoming[target] += 1
    if handoffs > 8:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW012", "swimlane exceeds 8 handoffs"))
    starts = [item["id"] for item in steps if item.get("id") not in incoming]
    parallel_starts = payload.get("parallel_starts", False)
    if not isinstance(parallel_starts, bool):
        diagnostics.append(DrawingDiagnostic("ERROR", "SW013", "parallel_starts must be boolean"))
    elif (not parallel_starts and len(starts) != 1) or (parallel_starts and not starts):
        diagnostics.append(DrawingDiagnostic("ERROR", "SW013", "swimlane requires one connected start unless parallel_starts=true"))
    reached = reachable(starts if parallel_starts else starts[:1], edge_pairs)
    for step_id in step_ids - reached:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW014", "unreachable swimlane step", step_id))
    focus_lane = payload.get("focus_lane")
    if focus_lane is not None and focus_lane not in lane_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW015", "focus_lane references unknown lane", str(focus_lane)))
    for lane in lanes:
        if lane.get("emphasis", "normal") not in {"focal", "normal"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "SW019", "invalid lane emphasis", str(lane.get("id"))))
    focus_path = payload.get("focus_path", [])
    if not isinstance(focus_path, list) or any(item not in step_ids for item in focus_path):
        diagnostics.append(DrawingDiagnostic("ERROR", "SW016", "focus_path references unknown steps"))
    axis = payload.get("axis", "left-right")
    if axis not in {"left-right", "top-down"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "SW017", "swimlane axis must be left-right or top-down"))
    validate_distinguishable_parallel_edges(flows, diagnostics=diagnostics, code="SW020")
    validate_no_self_edges(flows, diagnostics=diagnostics, code="SW021")
    require_no_errors("schema", diagnostics)

    language = infer_language(payload["title"], [str(item["label"]) for item in [*lanes, *steps]], payload.get("language"))
    semantic = SwimlaneSemantic(payload["title"], tuple(lanes), tuple(steps), tuple(flows), language)
    node_plans = tuple(
        GraphNodePlan(
            item["id"], item["label"], "decision" if item["type"] == "decision" else item["type"],
            "focal" if item["id"] in focus_path else str(item.get("emphasis", "normal")), lane=item["lane"],
        )
        for item in steps
    )
    edge_plans = tuple(GraphEdgePlan(item["id"], item["source"], item["target"], str(item.get("channel", "sequence")), item.get("label")) for item in flows)
    width, height = dimensions(payload)
    plan = GraphPlan("swimlane", payload["title"], GraphComposition("lanes", axis, tuple(starts)), node_plans, edge_plans, width, height, language)
    stage = current_stage()
    geometry = graph_geometry_for_stage(stage)
    composition_axis = axis
    if not stage.is_default:
        composition_axis = _choose_swimlane_axis(
            plan, lanes, geometry, width, GRAPH_CANVAS.ceiling(canvas_mode(payload)))
        if composition_axis != axis:
            plan = replace(
                plan, composition=GraphComposition("lanes", composition_axis, tuple(starts)))
        fitted = _swimlane_height(plan, lanes, geometry, composition_axis)
        plan = replace(plan, height=max(fitted, GRAPH_CANVAS.minimum_at(width)))
    layout, regions = _layout_swimlane(
        plan, lanes, focus_lane, geometry, composition_axis)
    if not stage.is_default:
        need_width, _need_height = _swimlane_extent(
            plan, lanes, geometry, composition_axis)
        if need_width > plan.width:
            diagnostics.append(DrawingDiagnostic(
                "ERROR", "SW024", "swimlane cannot compose on this stage", "swimlane"))
        regions_by_id = {region.id: region for region in regions}
        for node in plan.nodes:
            box = layout.boxes[node.id]
            region = regions_by_id.get(node.lane or "")
            if region is None or region.box is None:
                continue
            if box.y < region.box.y or box.y + box.h > region.box.y + region.box.h:
                diagnostics.append(DrawingDiagnostic(
                    "ERROR", "SW022", "step leaves its lane", node.id))
        captions = [region.label for region in regions]
        for index, first in enumerate(captions):
            first_left, first_right = _caption_span(first)
            for second in captions[index + 1:]:
                second_left, second_right = _caption_span(second)
                if first_left < second_right and second_left < first_right:
                    diagnostics.append(DrawingDiagnostic(
                        "ERROR", "SW023", "lane names collide", second.text))
        require_no_errors("stage", diagnostics)
    scene = resolve_graph_scene(
        plan, layout, regions=regions,
        description=_swimlane_description(semantic), geometry=geometry)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def _layout_swimlane(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    focus_lane: str | None,
    geometry: GraphGeometry = DEFAULT_GRAPH_GEOMETRY,
    axis: str | None = None,
):
    if not geometry.is_default:
        return _layout_swimlane_composed(plan, lanes, focus_lane, geometry, axis or plan.composition.axis)
    theme = DEFAULT_FOLIO_THEME
    lane_count = len(lanes)
    depths = graph_depths(plan)
    max_depth = max(depths.values(), default=0)
    boxes: dict[str, LayoutBox] = {}
    lane_index = {item["id"]: index for index, item in enumerate(lanes)}
    regions: list[SceneRegion] = []
    if plan.composition.axis == "left-right":
        top, bottom = 80, plan.height - 40
        lane_height = (bottom - top) // lane_count
        dense = len(plan.nodes) > 8
        for node in plan.nodes:
            width, height = ((72, 60) if node.archetype == "decision" else (56, 48)) if dense else ((88, 72) if node.archetype == "decision" else (128, 56))
            x = _grid((92 if dense else 136) + depths[node.id] * ((plan.width - (184 if dense else 304)) / max(1, max_depth)))
            y = _grid(top + lane_index[node.lane or ""] * lane_height + (lane_height - height) / 2)
            boxes[node.id] = LayoutBox(x, y, width, height)
        for index, lane in enumerate(lanes):
            y = _grid(top + index * lane_height)
            box = SceneBox(72, y, plan.width - 112, _grid(lane_height - 8))
            focal = lane["id"] == focus_lane
            regions.append(SceneRegion(
                lane["id"], "lane", role_text(lane["label"], 84, y + 20, TextRole.LANE_LABEL, theme, emphasis="focal" if focal else "normal", tracking=0),
                box, SceneStyle(theme.brand_tint if focal else "none", theme.muted_stroke if focal else theme.border, 1, radius=6, fill_opacity=0.32 if focal else None),
            ))
    else:
        left, right = 72, plan.width - 40
        lane_width = (right - left) // lane_count
        for node in plan.nodes:
            width, height = (88, 72) if node.archetype == "decision" else (128, 56)
            x = _grid(left + lane_index[node.lane or ""] * lane_width + (lane_width - width) / 2)
            y = _grid(112 + depths[node.id] * ((plan.height - 224) / max(1, max_depth)))
            boxes[node.id] = LayoutBox(x, y, width, height)
        for index, lane in enumerate(lanes):
            x = _grid(left + index * lane_width)
            box = SceneBox(x, 72, _grid(lane_width - 8), plan.height - 112)
            focal = lane["id"] == focus_lane
            regions.append(SceneRegion(
                lane["id"], "lane", role_text(lane["label"], x + 12, 92, TextRole.LANE_LABEL, theme, emphasis="focal" if focal else "normal", tracking=0),
                box, SceneStyle(theme.brand_tint if focal else "none", theme.muted_stroke if focal else theme.border, 1, radius=6, fill_opacity=0.32 if focal else None),
            ))
    # Lane bands are drawn as filled rectangles, so an edge label parked on a band border reads as
    # if it belongs to the wrong lane. Reserve a thin strip along every border and the lane caption.
    label_obstacles: list[LayoutBox] = []
    for region in regions:
        label_obstacles.append(LayoutBox(region.box.x, region.box.y - 2, region.box.w, 4))
        label_obstacles.append(LayoutBox(region.box.x, region.box.y + region.box.h - 2, region.box.w, 4))
        caption = region.label
        label_obstacles.append(LayoutBox(caption.x - 4, caption.y - 12, 7 * len(caption.text) + 8, 18))
    # Keep labels inside the lane stack. A label parked in the margin below the last lane looks
    # detached from the flow it annotates.
    if regions:
        lane_top = min(region.box.y for region in regions)
        lane_bottom = max(region.box.y + region.box.h for region in regions)
        lane_left = min(region.box.x for region in regions)
        lane_right = max(region.box.x + region.box.w for region in regions)
        label_obstacles.append(LayoutBox(0, lane_bottom, plan.width, max(4, plan.height - lane_bottom)))
        label_obstacles.append(LayoutBox(0, 0, plan.width, max(4, lane_top)))
        label_obstacles.append(LayoutBox(0, 0, max(4, lane_left), plan.height))
        label_obstacles.append(LayoutBox(lane_right, 0, max(4, plan.width - lane_right), plan.height))
    edges = route_graph_edges(plan, boxes, plan.width, plan.height, tuple(label_obstacles))
    return layout_result(boxes, edges), tuple(regions)


def _swimlane_node_size(node: GraphNodePlan, geometry: GraphGeometry) -> tuple[int, int]:
    """A lane node box sized by its own title, on the composed type scale."""
    width, height = (
        (geometry.lane_decision_width, geometry.lane_decision_height)
        if node.archetype == "decision"
        else (geometry.lane_node_width, geometry.lane_node_height)
    )
    title = resolve_text_style(TextRole.NODE_TITLE, DEFAULT_FOLIO_THEME)
    width = max(width, geometry.lane_node_width_floor)
    width = fit_wrap_width(node.label, width, title.size, 2, geometry.title_wrap_inset)
    height = max(height, geometry.lane_node_height_floor)
    lines = _staged_wrap(node.label, max(48, width - geometry.title_wrap_inset), title.size)
    if len(lines) > 1:
        height = max(height, geometry.node_subtitle_height)
    return _grid(width), _grid(height)


def _swimlane_sizes(plan: GraphPlan, geometry: GraphGeometry) -> dict[str, tuple[int, int]]:
    return {node.id: _swimlane_node_size(node, geometry) for node in plan.nodes}


def _swimlane_lane_widths(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    geometry: GraphGeometry,
) -> list[int]:
    """The narrowest lane that holds its widest step, before any spreading."""
    sizes = _swimlane_sizes(plan, geometry)
    needs: list[int] = []
    for lane in lanes:
        widths = [sizes[node.id][0] for node in plan.nodes if node.lane == lane["id"]]
        base = max(widths) if widths else geometry.lane_node_width
        needs.append(_grid(base + 2 * geometry.lane_pad))
    return needs


def _swimlane_header(geometry: GraphGeometry) -> int:
    """The lane-caption strip above a top-down lane stack.

    One line, centred over its lane. A caption a few units wider than the lane
    overflows into the gutter between captions, which is why the check is that
    the captions do not collide, not that each is inside its own lane.
    """
    return _grid(max(
        geometry.lane_header,
        geometry.title_clearance + geometry.lane_pad
        + geometry.subtitle_pitch + geometry.lane_pad))


def _swimlane_extent(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    geometry: GraphGeometry,
    axis: str,
) -> tuple[int, int]:
    """The smallest canvas that holds this lane composition on ``axis``."""
    sizes = _swimlane_sizes(plan, geometry)
    depths = graph_depths(plan)
    levels = max(depths.values(), default=0) + 1
    if axis == "left-right":
        level_widths: dict[int, int] = {}
        lane_needs: dict[str, int] = {}
        for node in plan.nodes:
            level_widths[depths[node.id]] = max(
                level_widths.get(depths[node.id], 0), sizes[node.id][0])
            lane_needs[node.lane or ""] = max(
                lane_needs.get(node.lane or "", 0), sizes[node.id][1])
        body = sum(
            max(lane_needs.get(lane["id"], 0), geometry.lane_header) + geometry.lane_pad
            for lane in lanes)
        width = (
            geometry.lane_step_left + sum(level_widths.values())
            + max(0, levels - 1) * geometry.min_gap + geometry.lane_right)
        return _grid(width), _grid(geometry.lane_top + body + geometry.lane_bottom)
    widths = _swimlane_lane_widths(plan, lanes, geometry)
    level_heights: dict[int, int] = {}
    for node in plan.nodes:
        level_heights[depths[node.id]] = max(
            level_heights.get(depths[node.id], 0), sizes[node.id][1])
    gap = max(geometry.min_gap, geometry.node_gap)
    side = geometry.min_side_margin
    width = 2 * side + sum(widths)
    height = (
        _swimlane_header(geometry)
        + sum(level_heights.values()) + max(0, levels - 1) * gap + geometry.lane_bottom)
    return _grid(width), _grid(height)


def _swimlane_fits(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    geometry: GraphGeometry,
    axis: str,
    width: int,
    max_height: int,
) -> bool:
    need_width, need_height = _swimlane_extent(plan, lanes, geometry, axis)
    return need_width <= width and need_height <= max_height


def _choose_swimlane_axis(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    geometry: GraphGeometry,
    width: int,
    max_height: int,
) -> str:
    """Keep the authored axis when it fits; turn the lanes upright when it does not.

    A horizontal lane is a row: four lanes need five steps' worth of columns,
    which a narrow plate cannot hold. Turned upright each lane needs one step's
    width, so the same flow reads down the page instead of across it.
    """
    authored = plan.composition.axis
    if _swimlane_fits(plan, lanes, geometry, authored, width, max_height):
        return authored
    perpendicular = "top-down" if authored == "left-right" else "left-right"
    if _swimlane_fits(plan, lanes, geometry, perpendicular, width, max_height):
        return perpendicular
    return authored


def _swimlane_height(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    geometry: GraphGeometry,
    axis: str,
) -> int:
    return _swimlane_extent(plan, lanes, geometry, axis)[1]


def _layout_swimlane_composed(
    plan: GraphPlan,
    lanes: list[dict[str, Any]],
    focus_lane: str | None,
    geometry: GraphGeometry,
    axis: str,
):
    theme = DEFAULT_FOLIO_THEME
    sizes = _swimlane_sizes(plan, geometry)
    depths = graph_depths(plan)
    max_depth = max(depths.values(), default=0)
    lane_index = {item["id"]: index for index, item in enumerate(lanes)}
    lane_widths = _swimlane_lane_widths(plan, lanes, geometry)
    boxes: dict[str, LayoutBox] = {}
    regions: list[SceneRegion] = []
    if axis == "left-right":
        top, bottom = geometry.lane_top, plan.height - geometry.lane_bottom
        lane_needs: dict[str, int] = {}
        for node in plan.nodes:
            lane_needs[node.lane or ""] = max(
                lane_needs.get(node.lane or "", 0), sizes[node.id][1])
        lane_height = max(
            max((max(lane_needs.get(lane["id"], 0), geometry.lane_header)
                 + geometry.lane_pad for lane in lanes), default=geometry.lane_header),
            (bottom - top) // max(1, len(lanes)))
        level_widths: dict[int, int] = {}
        for node in plan.nodes:
            level_widths[max(0, depths[node.id])] = max(
                level_widths.get(max(0, depths[node.id]), 0), sizes[node.id][0])
        left = geometry.lane_step_left
        available = plan.width - left - geometry.lane_right
        spread = geometry.min_gap
        if max_depth > 0:
            spread = max(
                geometry.min_gap,
                _grid((available - sum(level_widths.values())) / max_depth))
        for node in plan.nodes:
            level = max(0, depths[node.id])
            width, height = sizes[node.id]
            cursor = left + sum(
                level_widths.get(item, 0) + spread for item in range(level))
            x = _grid(cursor + (level_widths.get(level, width) - width) / 2)
            y = _grid(
                top + lane_index[node.lane or ""] * lane_height
                + max(0, (lane_height - height) / 2))
            boxes[node.id] = LayoutBox(x, y, width, height)
        for index, lane in enumerate(lanes):
            y = _grid(top + index * lane_height)
            focal = lane["id"] == focus_lane
            regions.append(SceneRegion(
                lane["id"], "lane",
                role_text(lane["label"], geometry.lane_label_x,
                          y + geometry.lane_label_offset, TextRole.LANE_LABEL,
                          theme, emphasis="focal" if focal else "normal", tracking=0),
                SceneBox(geometry.lane_box_x, y,
                         plan.width - geometry.lane_box_width_pad,
                         max(geometry.lane_header, _grid(lane_height - geometry.lane_pad))),
                SceneStyle(theme.brand_tint if focal else "none",
                           theme.muted_stroke if focal else theme.border,
                           1, radius=6, fill_opacity=0.32 if focal else None),
            ))
    else:
        side = max(geometry.min_side_margin, (plan.width - sum(lane_widths)) // 2)
        widths = lane_widths
        header = _swimlane_header(geometry)
        gap = max(geometry.min_gap, geometry.node_gap)
        level_heights: dict[int, int] = {}
        for node in plan.nodes:
            level_heights[max(0, depths[node.id])] = max(
                level_heights.get(max(0, depths[node.id]), 0), sizes[node.id][1])
        level_y: dict[int, int] = {}
        cursor = header
        for level in range(max_depth + 1):
            level_y[level] = _grid(cursor)
            cursor += level_heights.get(level, 0) + gap
        lane_x: dict[str, int] = {}
        cursor = side
        for lane, width in zip(lanes, widths):
            lane_x[lane["id"]] = _grid(cursor)
            cursor += width
        for node in plan.nodes:
            lane = node.lane or ""
            width, height = sizes[node.id]
            lane_width = widths[lane_index.get(lane, 0)]
            boxes[node.id] = LayoutBox(
                _grid(lane_x.get(lane, side)
                      + max(0, (lane_width - width) / 2)),
                _grid(level_y[max(0, depths[node.id])]), width, height)
        for lane, width in zip(lanes, widths):
            x = lane_x[lane["id"]]
            focal = lane["id"] == focus_lane
            caption = role_text(
                lane["label"], _grid(x + width / 2),
                geometry.title_clearance + geometry.lane_pad + geometry.subtitle_pitch,
                TextRole.LANE_LABEL, theme,
                emphasis="focal" if focal else "normal", anchor="middle", tracking=0)
            regions.append(SceneRegion(
                lane["id"], "lane", caption,
                SceneBox(x, geometry.title_clearance, max(4, width - geometry.lane_pad),
                         plan.height - geometry.title_clearance - geometry.lane_bottom),
                SceneStyle(theme.brand_tint if focal else "none",
                           theme.muted_stroke if focal else theme.border,
                           1, radius=6, fill_opacity=0.32 if focal else None),
            ))
    label_obstacles: list[LayoutBox] = []
    for region in regions:
        label_obstacles.append(
            LayoutBox(region.box.x, region.box.y - 2, region.box.w, 4))
        label_obstacles.append(
            LayoutBox(region.box.x, region.box.y + region.box.h - 2, region.box.w, 4))
        caption = region.label
        caption_width = int(measure_text(
            caption.text, caption.size, caption.family)) + 8
        label_obstacles.append(
            LayoutBox(caption.x - 4, caption.y - 12, caption_width, 18))
    if regions:
        lane_top = min(region.box.y for region in regions)
        lane_bottom = max(region.box.y + region.box.h for region in regions)
        lane_left = min(region.box.x for region in regions)
        lane_right = max(region.box.x + region.box.w for region in regions)
        label_obstacles.append(
            LayoutBox(0, lane_bottom, plan.width, max(4, plan.height - lane_bottom)))
        label_obstacles.append(LayoutBox(0, 0, plan.width, max(4, lane_top)))
        label_obstacles.append(LayoutBox(0, 0, max(4, lane_left), plan.height))
        label_obstacles.append(
            LayoutBox(lane_right, 0, max(4, plan.width - lane_right), plan.height))
    edges = route_graph_edges(
        plan, boxes, plan.width, plan.height, tuple(label_obstacles),
        geometry, axis=axis)
    return layout_result(boxes, edges), tuple(regions)


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)


def _caption_span(label) -> tuple[float, float]:
    width = measure_text(label.text, label.size, label.family) + (
        label.tracking * label.size * len(label.text))
    if label.anchor == "middle":
        return label.x - width / 2, label.x + width / 2
    return label.x, label.x + width


def _swimlane_description(semantic: SwimlaneSemantic) -> str:
    return f"Swimlane {semantic.title}. Lanes: {', '.join(item['label'] for item in semantic.lanes)}."


TREE_BUS_LINK_PREFIX = "link:"


def _dedupe_points(points: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    kept: list[tuple[int, int]] = []
    for point in points:
        if not kept or kept[-1] != point:
            kept.append(point)
    return tuple(kept) if len(kept) >= 2 else points[:2]


TREE_TRUNK_SNAP = 12


def _tree_bus_scene(scene: ResolvedScene, plan: GraphPlan) -> ResolvedScene:
    """Replace per-edge tree routes with one shared horizontal bus per parent.

    Siblings drop from a single trunk instead of fanning out from offset
    anchors, which matches the hierarchy convention: parent stub, shared
    horizontal bus, short vertical drop into each child's top edge.
    """
    boxes = {node.id: node.box for node in scene.nodes}
    theme = DEFAULT_FOLIO_THEME
    groups: dict[str, list[str]] = defaultdict(list)
    for edge in plan.edges:
        if edge.source in boxes and edge.target in boxes:
            groups[edge.source].append(edge.target)
    links: list[ScenePolyline] = []
    arrows: list[ScenePolyline] = []
    style = SceneStyle(stroke=theme.olive, stroke_width=1)
    for parent_id in sorted(groups, key=lambda item: (boxes[item].y, boxes[item].x)):
        child_ids = sorted(groups[parent_id], key=lambda item: boxes[item].x)
        parent_box = boxes[parent_id]
        trunk_x = parent_box.x + parent_box.w // 2
        trunk_y = parent_box.y + parent_box.h
        bus_y = _grid((trunk_y + min(boxes[item].y for item in child_ids)) / 2)
        bus_y = max(trunk_y, min(bus_y, scene.height))
        for child_id in child_ids:
            box = boxes[child_id]
            drop_x = box.x + box.w // 2
            if abs(drop_x - trunk_x) <= TREE_TRUNK_SNAP:
                # A near-aligned single drop reads as one straight stem, not a jog.
                drop_x = trunk_x
            drop_y = box.y
            points = _dedupe_points((
                (trunk_x, trunk_y), (trunk_x, bus_y), (drop_x, bus_y), (drop_x, drop_y),
            ))
            links.append(ScenePolyline(f"{TREE_BUS_LINK_PREFIX}{child_id}", points, style, klass="tree-edge tree-edge--branch"))
            wing = max(0, min(4, drop_y - bus_y))
            if wing:
                arrows.append(ScenePolyline(
                    f"arrow:{child_id}",
                    ((drop_x - wing, drop_y - wing), (drop_x, drop_y), (drop_x + wing, drop_y - wing)),
                    style, klass="tree-arrow",
                ))
    if not links:
        return scene
    return replace(scene, edges=(), primitives=(*links, *arrows, *scene.primitives))


def compile_tree_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload,
        kind="tree",
        allowed={"schema_version", "kind", "title", "nodes", "relations", "focus_root", "width", "height", "language"},
        required=("schema_version", "kind", "title", "nodes", "relations"),
        code="TR000",
    )
    nodes = object_list(payload, "nodes", diagnostics, "TR000")
    relations = object_list(payload, "relations", diagnostics, "TR000")
    validate_object_fields(nodes, name="nodes", allowed={"id", "label", "subtitle"}, required=("id", "label"), diagnostics=diagnostics, code="TR000")
    validate_object_fields(relations, name="relations", allowed={"id", "parent", "child"}, required=("id", "parent", "child"), diagnostics=diagnostics, code="TR000")
    validate_item_strings(nodes, ("label", "subtitle"), diagnostics=diagnostics, code="TR000")
    node_ids = validate_unique_ids(nodes, name="tree node", diagnostics=diagnostics, code="TR001")
    validate_unique_ids(relations, name="tree relation", diagnostics=diagnostics, code="TR002")
    if not nodes or len(nodes) > 15:
        diagnostics.append(DrawingDiagnostic("ERROR", "TR003", "tree requires 1-15 nodes"))
    parents: Counter[str] = Counter()
    children: dict[str, list[str]] = defaultdict(list)
    edge_pairs: list[tuple[str, str]] = []
    for item in relations:
        parent, child = item.get("parent"), item.get("child")
        if parent not in node_ids or child not in node_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "TR004", "relation references unknown node", str(item.get("id"))))
        if isinstance(parent, str) and isinstance(child, str):
            parents[child] += 1
            children[parent].append(child)
            edge_pairs.append((parent, child))
    roots = [node_id for node_id in node_ids if parents[node_id] == 0]
    if len(roots) != 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "TR005", "tree requires exactly one root"))
    for node_id, count in parents.items():
        if count != 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "TR006", "non-root node must have exactly one parent", node_id))
    if cycle_exists(node_ids, edge_pairs):
        diagnostics.append(DrawingDiagnostic("ERROR", "TR007", "tree cannot contain a cycle"))
    if any(len(items) > 5 for items in children.values()):
        diagnostics.append(DrawingDiagnostic("ERROR", "TR008", "tree branch exceeds 5 children"))
    focus_root = payload.get("focus_root")
    if focus_root is not None and focus_root not in node_ids:
        diagnostics.append(DrawingDiagnostic("ERROR", "TR009", "focus_root references unknown node", str(focus_root)))
    if len(roots) == 1 and not cycle_exists(node_ids, edge_pairs):
        pending = [(roots[0], 0)]
        maximum_depth = 0
        while pending:
            node_id, depth = pending.pop()
            maximum_depth = max(maximum_depth, depth)
            pending.extend((child, depth + 1) for child in children[node_id])
        if maximum_depth > 4:
            diagnostics.append(DrawingDiagnostic("ERROR", "TR010", "tree exceeds maximum depth 4"))
    require_no_errors("schema", diagnostics)

    language = infer_language(payload["title"], (str(item["label"]) for item in nodes), payload.get("language"))
    semantic = TreeSemantic(payload["title"], tuple(nodes), tuple(relations), focus_root, language)
    descendants = reachable([focus_root], edge_pairs) if focus_root else set()
    node_plans = tuple(
        GraphNodePlan(
            item["id"], item["label"], "root" if item["id"] in roots else "leaf" if not children[item["id"]] else "branch",
            "focal" if item["id"] == focus_root else "background" if focus_root and item["id"] not in descendants else "normal",
            item.get("subtitle"),
        )
        for item in nodes
    )
    edge_plans = tuple(GraphEdgePlan(item["id"], item["parent"], item["child"]) for item in relations)
    width, height = dimensions(payload)
    plan = GraphPlan("tree", payload["title"], GraphComposition("hierarchy", "top-down", tuple(roots)), node_plans, edge_plans, width, height, language)
    layout = layout_layered_graph(plan)
    scene = resolve_graph_scene(plan, layout, description=f"Tree {semantic.title} with root {roots[0]}.")
    scene = _tree_bus_scene(scene, plan)
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])


def compile_layer_stack_payload(payload: dict[str, Any]):
    diagnostics = common_payload_diagnostics(
        payload,
        kind="layer-stack",
        allowed={"schema_version", "kind", "title", "layers", "flows", "width", "height", "language"},
        required=("schema_version", "kind", "title", "layers", "flows"),
        code="LS000",
    )
    layers = object_list(payload, "layers", diagnostics, "LS000")
    flows = object_list(payload, "flows", diagnostics, "LS000")
    validate_object_fields(layers, name="layers", allowed={"id", "label", "responsibility", "emphasis"}, required=("id", "label", "responsibility"), diagnostics=diagnostics, code="LS000")
    validate_object_fields(flows, name="flows", allowed={"id", "source", "target", "channel", "label"}, required=("id", "source", "target", "channel"), diagnostics=diagnostics, code="LS000")
    validate_item_strings(layers, ("label", "responsibility"), diagnostics=diagnostics, code="LS000")
    validate_item_strings(flows, ("label",), diagnostics=diagnostics, code="LS000")
    layer_ids = validate_unique_ids(layers, name="layer", diagnostics=diagnostics, code="LS001")
    validate_unique_ids(flows, name="layer flow", diagnostics=diagnostics, code="LS002")
    if not 3 <= len(layers) <= 7:
        diagnostics.append(DrawingDiagnostic("ERROR", "LS003", "layer stack requires 3-7 layers"))
    if sum(item.get("emphasis") == "focal" for item in layers) > 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "LS004", "layer stack permits one focal layer"))
    for item in layers:
        if item.get("emphasis", "normal") not in {"focal", "normal", "background"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "LS008", "invalid layer emphasis", str(item.get("id"))))
    order = {item["id"]: index for index, item in enumerate(layers) if isinstance(item.get("id"), str)}
    for item in flows:
        source, target = item.get("source"), item.get("target")
        if source not in layer_ids or target not in layer_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "LS005", "flow references unknown layer", str(item.get("id"))))
        elif abs(order[source] - order[target]) != 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "LS006", "layer flows must connect adjacent layers", str(item.get("id"))))
        if item.get("channel") not in {"request", "response"}:
            diagnostics.append(DrawingDiagnostic("ERROR", "LS007", "layer flow channel must be request or response", str(item.get("id"))))
    validate_distinguishable_parallel_edges(flows, diagnostics=diagnostics, code="LS009")
    validate_no_self_edges(flows, diagnostics=diagnostics, code="LS010")
    require_no_errors("schema", diagnostics)

    language = infer_language(payload["title"], (str(item["label"]) for item in layers), payload.get("language"))
    semantic = LayerStackSemantic(payload["title"], tuple(layers), tuple(flows), language)
    show_responsibility = len(layers) <= 5
    nodes = tuple(
        GraphNodePlan(
            item["id"], item["label"], "layer", str(item.get("emphasis", "normal")),
            item["responsibility"] if show_responsibility else None,
        )
        for item in layers
    )
    edges = tuple(GraphEdgePlan(item["id"], item["source"], item["target"], item["channel"], item.get("label")) for item in flows)
    width, height = dimensions(payload)
    plan = GraphPlan("layer-stack", payload["title"], GraphComposition("bands", "top-down", tuple(item["id"] for item in layers)), nodes, edges, width, height, language)
    boxes: dict[str, LayoutBox] = {}
    band_height = 56 if len(nodes) <= 5 else 48
    gap = 16
    total = len(nodes) * band_height + max(0, len(nodes) - 1) * gap
    y = _grid((height - total) / 2 + 16)
    for node in nodes:
        boxes[node.id] = LayoutBox(120, y, 720, band_height)
        y += band_height + gap
    routed = route_graph_edges(plan, boxes, width, height)
    layout = layout_result(boxes, routed)
    scene = resolve_graph_scene(plan, layout, description=f"Layer stack {semantic.title}: " + ", ".join(item["label"] for item in layers))
    scene_diagnostics = validate_resolved_scene(scene)
    return semantic, plan, layout, scene, tuple([*diagnostics, *scene_diagnostics])
