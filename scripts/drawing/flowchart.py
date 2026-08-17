from __future__ import annotations

from collections import defaultdict
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .connectors.postprocess import clean_polyline
from .connectors.labels import place_edge_labels
from .layout.models import LayoutBox, LayoutEdge, LayoutResult
from .scene import ArrowGeometry, ResolvedScene, SceneBox, SceneEdge, SceneNode, SceneStyle, SceneText
from .theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from .typography.measure import measure_text
from .typography.roles import TextRole, resolve_text_style
from .schema import flowchart_payload_issues
from .validation import validate_canvas, validate_scene_accessibility, validate_scene_geometry, validate_scene_primitives
from .validation.models import DrawingDiagnostic, raise_for_errors


FLOW_NODE_TYPES = {"step", "decision", "terminal", "data", "subprocess"}
FLOW_EDGE_TYPES = {"sequence-flow", "conditional-flow", "exception-flow"}
FLOW_PATTERNS = {"linear", "branching", "loop"}


@dataclass(frozen=True)
class FlowchartSemanticNode:
    id: str
    label: str
    role: str
    description: str | None = None


@dataclass(frozen=True)
class FlowchartSemanticEdge:
    id: str
    source: str
    target: str
    relation: str
    label: str | None = None


@dataclass(frozen=True)
class FlowchartSemanticDiagram:
    title: str
    nodes: tuple[FlowchartSemanticNode, ...]
    edges: tuple[FlowchartSemanticEdge, ...]
    focus: str | None = None
    width: int = 960
    height: int = 540
    language: str = "en"
    axis: str = "top-down"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FlowchartComposition:
    pattern: str
    axis: str
    spine: tuple[str, ...] = ()


@dataclass(frozen=True)
class FlowchartNodePlan:
    id: str
    archetype: str
    label: str
    emphasis: str = "normal"


@dataclass(frozen=True)
class FlowchartEdgePlan:
    id: str
    source: str
    target: str
    channel: str
    label: str | None = None


@dataclass(frozen=True)
class FlowchartDrawingPlan:
    kind: str
    title: str
    composition: FlowchartComposition
    nodes: tuple[FlowchartNodePlan, ...]
    edges: tuple[FlowchartEdgePlan, ...]
    width: int = 960
    height: int = 540
    language: str = "en"
    schema_version: str = "2.0"
    explanation: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def semantic_from_flowchart_payload(payload: dict[str, Any]) -> FlowchartSemanticDiagram:
    nodes = tuple(
        FlowchartSemanticNode(item["id"], item["label"], item.get("type", "step"), item.get("description"))
        for item in payload.get("nodes", ())
    )
    edges = tuple(
        FlowchartSemanticEdge(
            item.get("id", f"flow:{index}:{item['source']}->{item['target']}"),
            item["source"], item["target"], item.get("kind", "sequence-flow"), item.get("label"),
        )
        for index, item in enumerate(payload.get("edges", ()))
    )
    title = str(payload.get("title", "Flowchart"))
    language = str(payload.get("language") or ("zh" if any("\u4e00" <= char <= "\u9fff" for char in title + "".join(n.label for n in nodes)) else "en"))
    return FlowchartSemanticDiagram(
        title, nodes, edges, payload.get("focus"), int(payload.get("width", 960)), int(payload.get("height", 540)),
        language, str(payload.get("axis", "top-down")),
    )


def plan_flowchart(semantic: FlowchartSemanticDiagram) -> FlowchartDrawingPlan:
    decision_count = sum(node.role == "decision" for node in semantic.nodes)
    has_loop = _has_cycle(semantic)
    pattern = "loop" if has_loop else "branching" if decision_count else "linear"
    spine = _longest_path(semantic)
    nodes = tuple(
        FlowchartNodePlan(node.id, node.role, node.label, "focal" if node.id == semantic.focus else "normal")
        for node in semantic.nodes
    )
    edges = tuple(FlowchartEdgePlan(edge.id, edge.source, edge.target, edge.relation, edge.label) for edge in semantic.edges)
    plan = FlowchartDrawingPlan(
        "flowchart", semantic.title, FlowchartComposition(pattern, semantic.axis, spine), nodes, edges,
        semantic.width, semantic.height, semantic.language,
        explanation=(
            f"composition: {pattern}; reason: {'cycle detected' if has_loop else f'{decision_count} decision nodes detected'}",
            f"spine: {' -> '.join(spine)}; reason: longest acyclic reading path",
        ),
    )
    levels = max(_depths(plan).values(), default=0) + 1
    depth = _depths(plan)
    rows: dict[int, list[FlowchartNodePlan]] = defaultdict(list)
    for node in plan.nodes:
        rows[depth[node.id]].append(node)
    if semantic.axis == "left-right":
        required_height = max(
            (
                sum(88 if node.archetype == "decision" else 64 for node in nodes)
                + max(0, len(nodes) - 1) * 48
                + 144
            )
            for nodes in rows.values()
        ) if rows else plan.height
        width = max(plan.width, 160 + levels * 192)
        height = max(plan.height, required_height)
    else:
        required_width = max(
            (
                sum(192 if node.archetype == "decision" else 160 for node in nodes)
                + max(0, len(nodes) - 1) * 48
                + 144
            )
            for nodes in rows.values()
        ) if rows else plan.width
        width = max(plan.width, required_width)
        height = max(plan.height, 160 + levels * 112)
        # A top-down flow is naturally narrow. Fit the canvas to the widest row instead of
        # stranding the column inside a 16:9 frame, which starves canvas utilization.
        width = max(480, min(width, required_width))
    return FlowchartDrawingPlan(
        plan.kind, plan.title, plan.composition, plan.nodes, plan.edges,
        width, height, plan.language,
        plan.schema_version, plan.explanation,
    )


def compile_flowchart_payload(payload: dict[str, Any]) -> tuple[FlowchartSemanticDiagram, FlowchartDrawingPlan, LayoutResult, ResolvedScene]:
    if "schema_version" not in payload:
        raise_for_errors("schema", (DrawingDiagnostic("ERROR", "FC000", "flowchart requires an explicit schema_version"),))
    schema_issues = flowchart_payload_issues(payload)
    raise_for_errors("schema", (DrawingDiagnostic("ERROR", code, message) for code, message in schema_issues))
    semantic = semantic_from_flowchart_payload(payload)
    plan = plan_flowchart(semantic)
    diagnostics = validate_flowchart(semantic, plan)
    raise_for_errors("plan", diagnostics)
    try:
        layout = layout_flowchart(plan)
    except (KeyError, TypeError, ValueError) as exc:
        raise_for_errors("layout", (DrawingDiagnostic("ERROR", "FC100", str(exc)),))
        raise AssertionError("unreachable") from exc
    try:
        scene = resolve_flowchart_scene(plan, layout)
    except (KeyError, TypeError, ValueError) as exc:
        raise_for_errors("scene", (DrawingDiagnostic("ERROR", "FC101", str(exc)),))
        raise AssertionError("unreachable") from exc
    raise_for_errors("scene", [
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene),
    ])
    return semantic, plan, layout, scene


def layout_flowchart(plan: FlowchartDrawingPlan) -> LayoutResult:
    depth = _depths(plan)
    rows: dict[int, list[str]] = defaultdict(list)
    for node in plan.nodes:
        rows[depth[node.id]].append(node.id)
    boxes: dict[str, LayoutBox] = {}
    node_by_id = {node.id: node for node in plan.nodes}
    if plan.composition.axis == "left-right":
        left, right = 72, plan.width - 232
        column_gap = 0 if len(rows) <= 1 else (right - left) / (max(rows) or 1)
        for level, ids in sorted(rows.items()):
            heights = [88 if node_by_id[node_id].archetype == "decision" else 64 for node_id in ids]
            gap = 48
            total = sum(heights) + max(0, len(ids) - 1) * gap
            x = _grid(left + level * column_gap)
            y = _grid((plan.height - total) / 2)
            for node_id, height in zip(ids, heights):
                width = 192 if node_by_id[node_id].archetype == "decision" else 160
                boxes[node_id] = LayoutBox(x, y, width, height)
                y += height + gap
    else:
        top, bottom = 88, plan.height - 72
        row_gap = 0 if len(rows) <= 1 else (bottom - top - 72) / (max(rows) or 1)
        for level, ids in sorted(rows.items()):
            widths = [192 if node_by_id[node_id].archetype == "decision" else 160 for node_id in ids]
            gap = 48
            total = sum(widths) + max(0, len(ids) - 1) * gap
            x = _grid((plan.width - total) / 2)
            y = _grid(top + level * row_gap)
            for node_id, width in zip(ids, widths):
                height = 88 if node_by_id[node_id].archetype == "decision" else 64
                boxes[node_id] = LayoutBox(x, y, width, height)
                x += width + gap
    edges = _flow_edges(plan, boxes)
    points = [point for edge in edges for point in edge.points]
    xs = [box.x for box in boxes.values()] + [box.x + box.w for box in boxes.values()] + [x for x, _ in points]
    ys = [box.y for box in boxes.values()] + [box.y + box.h for box in boxes.values()] + [y for _, y in points]
    bounds = LayoutBox(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)) if xs else LayoutBox(0, 0, 0, 0)
    return LayoutResult(boxes, edges, bounds)


def _flow_edges(plan: FlowchartDrawingPlan, boxes: dict[str, LayoutBox]) -> list[LayoutEdge]:
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in plan.edges:
        outgoing[edge.source].append(edge.id)
        incoming[edge.target].append(edge.id)
    results = []
    for edge in plan.edges:
        source, target = boxes[edge.source], boxes[edge.target]
        source_edges = sorted(outgoing[edge.source])
        offset = (source_edges.index(edge.id) - (len(source_edges) - 1) / 2) * 20
        target_edges = sorted(incoming[edge.target])
        target_offset = (target_edges.index(edge.id) - (len(target_edges) - 1) / 2) * 20
        if plan.composition.axis == "left-right" and target.x > source.x:
            start = (source.x + source.w, _grid(source.y + source.h / 2 + offset))
            end = (target.x, _grid(target.y + target.h / 2 + target_offset))
            lane = _grid((start[0] + end[0]) / 2 + offset)
            points = [start, (lane, start[1]), (lane, end[1]), end]
        elif plan.composition.axis == "left-right":
            start = (_grid(source.x + source.w / 2 + offset), source.y + source.h)
            end = (_grid(target.x + target.w / 2 + target_offset), target.y + target.h)
            lane = plan.height - 32
            points = [start, (start[0], lane), (end[0], lane), end]
        elif target.y > source.y:
            start = (_grid(source.x + source.w / 2 + offset), source.y + source.h)
            end = (_grid(target.x + target.w / 2 + target_offset), target.y)
            lane = _grid((start[1] + end[1]) / 2 + offset)
            points = [start, (start[0], lane), (end[0], lane), end]
        else:
            start = (source.x, _grid(source.y + source.h / 2 + offset))
            end = (target.x, _grid(target.y + target.h / 2 + target_offset))
            lane = 32
            points = [start, (lane, start[1]), (lane, end[1]), end]
        label = edge.label.upper() if edge.label and len(edge.label) <= 14 else None
        results.append(LayoutEdge(edge.source, edge.target, list(clean_polyline(points)), label, None, edge.id))
    return place_edge_labels(results, list(boxes.values()), plan.width, plan.height)


def resolve_flowchart_scene(plan: FlowchartDrawingPlan, layout: LayoutResult, theme: FolioTheme = DEFAULT_FOLIO_THEME) -> ResolvedScene:
    scene_nodes = []
    for node in plan.nodes:
        box = layout.boxes[node.id]
        role = resolve_text_style(TextRole.NODE_TITLE, theme)
        lines = _wrap_title(node.label, max(80, box.w - 48), role.size, role.family)
        baseline = _grid(box.y + box.h // 2 - (len(lines) - 1) * 8 + 4)
        texts = tuple(SceneText(line, box.x + box.w // 2, baseline + index * 16, role.color, role.size, role.family, "middle", weight=role.weight) for index, line in enumerate(lines))
        shape = {"decision": "diamond", "terminal": "pill", "data": "data"}.get(node.archetype, "rect")
        fill = theme.brand_tint if node.emphasis == "focal" else theme.ivory
        stroke = theme.brand if node.emphasis == "focal" else theme.near_black
        scene_nodes.append(SceneNode(node.id, SceneBox(box.x, box.y, box.w, box.h), SceneStyle(fill, stroke, 1, radius=5), texts, shape=shape))
    edge_by_id = {edge.id: edge for edge in layout.edges if edge.id}
    edge_by_pair: dict[tuple[str, str], list[LayoutEdge]] = defaultdict(list)
    for item in layout.edges:
        edge_by_pair[(item.source, item.target)].append(item)
    scene_edges = []
    for edge in plan.edges:
        route = edge_by_id.get(edge.id)
        if route is None:
            matches = edge_by_pair.get((edge.source, edge.target), [])
            if not matches:
                raise ValueError(f"flowchart edge has no layout route: {edge.id}")
            route = matches.pop(0)
        points = tuple(route.points)
        stroke = theme.near_black if edge.channel == "conditional-flow" else theme.stone if edge.channel == "exception-flow" else theme.olive
        dash = (6, 4) if edge.channel == "exception-flow" else ()
        arrow = _arrow(points)
        label = None
        if route.label and route.label_box:
            style = resolve_text_style(TextRole.EDGE_LABEL, theme)
            label = SceneText(route.label, _grid(route.label_box.x + route.label_box.w / 2), route.label_box.y + 12, style.color, style.size, style.family, "middle", klass="flow-edge-label")
        scene_edges.append(SceneEdge(edge.id, edge.source, edge.target, points, SceneStyle(stroke=stroke, stroke_width=1.4, dash=dash), arrow, f"flow-edge flow-edge--{edge.channel}", label, SceneBox(**asdict(route.label_box)) if route.label_box else None))
    title_style = resolve_text_style(TextRole.DIAGRAM_TITLE, theme)
    title = SceneText(plan.title, plan.width // 2, 40, title_style.color, title_style.size, title_style.family, "middle")
    return ResolvedScene(plan.width, plan.height, theme.parchment, title, (), tuple(scene_edges), tuple(scene_nodes), description=f"Flowchart: {plan.title}", language=plan.language, reading_order=_reading_order(plan))


def validate_flowchart(semantic: FlowchartSemanticDiagram, plan: FlowchartDrawingPlan) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    node_ids = [node.id for node in semantic.nodes]
    edge_ids = [edge.id for edge in semantic.edges]
    known = set(node_ids)
    if not semantic.nodes:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC010", "flowchart requires at least one node"))
    for item, count in Counter(node_ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC011", "duplicate flowchart node id", item))
    for item, count in Counter(edge_ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC012", "duplicate flowchart edge id", item))
    if len(node_ids) > 12:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC001", "flowchart exceeds 12 visual nodes"))
    decisions = [node for node in semantic.nodes if node.role == "decision"]
    if len(decisions) > 4:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC002", "flowchart exceeds 4 decisions"))
    if semantic.axis not in {"top-down", "left-right"}:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC009", "flowchart axis must be top-down or left-right"))
    outgoing: dict[str, list[FlowchartSemanticEdge]] = defaultdict(list)
    incoming: dict[str, int] = defaultdict(int)
    for edge in semantic.edges:
        if edge.source not in known or edge.target not in known:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC003", "edge references unknown node", edge.id))
        outgoing[edge.source].append(edge)
        incoming[edge.target] += 1
        if edge.relation not in FLOW_EDGE_TYPES:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC004", "unknown flow edge type", edge.id))
    for node in semantic.nodes:
        if node.role not in FLOW_NODE_TYPES:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC005", "unknown flow node type", node.id))
        if node.role == "decision" and len(outgoing[node.id]) < 2:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC006", "decision requires at least two exits", node.id))
        if node.role == "decision" and len(outgoing[node.id]) >= 2:
            if any(edge.relation != "conditional-flow" for edge in outgoing[node.id]):
                diagnostics.append(DrawingDiagnostic("ERROR", "FC013", "decision exits must use conditional-flow", node.id))
            if any(not edge.label or not edge.label.strip() for edge in outgoing[node.id]):
                diagnostics.append(DrawingDiagnostic("ERROR", "FC014", "decision exits require readable labels", node.id))
            if not _branches_converge_or_terminate(node.id, outgoing[node.id], semantic):
                diagnostics.append(DrawingDiagnostic("ERROR", "FC015", "decision branches must converge or terminate explicitly", node.id))
        if node.role == "terminal" and incoming[node.id] > 0 and outgoing[node.id]:
            diagnostics.append(DrawingDiagnostic("ERROR", "FC016", "terminal with incoming flow cannot have outgoing flow", node.id))
    starts = [node.id for node in semantic.nodes if incoming[node.id] == 0]
    if semantic.nodes and len(starts) != 1:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC008", "flowchart requires one connected start", ",".join(starts)))
    reachable = _reachable(starts[:1], semantic.edges)
    for node_id in known - reachable:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC007", "unreachable flowchart node", node_id))
    if semantic.focus is not None and semantic.focus not in known:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC017", "focus references an unknown node", semantic.focus))
    if _loop_complexity(semantic) > 2:
        diagnostics.append(DrawingDiagnostic("ERROR", "FC018", "flowchart exceeds nested loop depth 2"))
    branch_labels = sum(bool(edge.label) for edge in semantic.edges if edge.relation == "conditional-flow")
    if branch_labels > 8:
        diagnostics.append(DrawingDiagnostic("WARNING", "FC108", "flowchart exceeds 8 visible branch labels"))
    if plan.composition.pattern == "branching" and len(plan.composition.spine) > 7:
        diagnostics.append(DrawingDiagnostic("TASTE", "FC201", "primary flow path is long"))
    return diagnostics


def _branches_converge_or_terminate(
    decision_id: str,
    exits: list[FlowchartSemanticEdge],
    semantic: FlowchartSemanticDiagram,
) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    outgoing_count: dict[str, int] = defaultdict(int)
    roles = {node.id: node.role for node in semantic.nodes}
    for edge in semantic.edges:
        graph[edge.source].append(edge.target)
        outgoing_count[edge.source] += 1

    def reachable(start: str) -> set[str]:
        result = {start}
        pending = [start]
        while pending:
            for target in graph[pending.pop()]:
                if target not in result:
                    result.add(target)
                    pending.append(target)
        return result

    branch_reach = [reachable(edge.target) for edge in exits]
    common = set.intersection(*branch_reach) if branch_reach else set()
    common.discard(decision_id)
    if common:
        return True
    for nodes in branch_reach:
        sinks = [node_id for node_id in nodes if outgoing_count[node_id] == 0]
        if not sinks or any(roles.get(node_id) != "terminal" for node_id in sinks):
            return False
    return True


def _loop_complexity(semantic: FlowchartSemanticDiagram) -> int:
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in semantic.edges:
        graph[edge.source].append(edge.target)
    index = 0
    stack: list[str] = []
    active: set[str] = set()
    indexes: dict[str, int] = {}
    low: dict[str, int] = {}
    maximum = 0

    def visit(node: str) -> None:
        nonlocal index, maximum
        indexes[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for target in graph[node]:
            if target not in indexes:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in active:
                low[node] = min(low[node], indexes[target])
        if low[node] == indexes[node]:
            component: list[str] = []
            while stack:
                item = stack.pop()
                active.remove(item)
                component.append(item)
                if item == node:
                    break
            internal_edges = sum(target in component for source in component for target in graph[source])
            if len(component) > 1 or internal_edges:
                maximum = max(maximum, max(1, internal_edges - len(component) + 1))

    for node in semantic.nodes:
        if node.id not in indexes:
            visit(node.id)
    return maximum


def _reading_order(plan: FlowchartDrawingPlan) -> tuple[str, ...]:
    depth = _depths(plan)
    position = {node.id: index for index, node in enumerate(plan.nodes)}
    return tuple(sorted(position, key=lambda node_id: (depth[node_id], position[node_id])))


def _has_cycle(semantic: FlowchartSemanticDiagram) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in semantic.edges:
        graph[edge.source].append(edge.target)
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(target) for target in graph[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False
    return any(visit(node.id) for node in semantic.nodes)


def _longest_path(semantic: FlowchartSemanticDiagram) -> tuple[str, ...]:
    graph: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, int] = defaultdict(int)
    for edge in semantic.edges:
        graph[edge.source].append(edge.target)
        incoming[edge.target] += 1
    starts = [node.id for node in semantic.nodes if incoming[node.id] == 0] or ([semantic.nodes[0].id] if semantic.nodes else [])
    def walk(node: str, seen: tuple[str, ...]) -> tuple[str, ...]:
        targets = [target for target in graph[node] if target not in seen]
        if not targets:
            return (*seen, node)
        return max((walk(target, (*seen, node)) for target in targets), key=lambda path: (len(path), path))
    return max((walk(start, ()) for start in starts), key=lambda path: (len(path), path), default=())


def _depths(plan: FlowchartDrawingPlan) -> dict[str, int]:
    depth = {node.id: 0 for node in plan.nodes}
    spine_index = {node_id: index for index, node_id in enumerate(plan.composition.spine)}
    for _ in range(len(plan.nodes)):
        changed = False
        for edge in plan.edges:
            if edge.source in spine_index and edge.target in spine_index and spine_index[edge.target] <= spine_index[edge.source]:
                continue
            candidate = min(len(plan.nodes) - 1, depth[edge.source] + 1)
            if candidate > depth[edge.target]:
                depth[edge.target] = candidate
                changed = True
        if not changed:
            break
    return depth


def _reachable(starts: list[str], edges: tuple[FlowchartSemanticEdge, ...]) -> set[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        graph[edge.source].append(edge.target)
    result = set(starts)
    pending = list(starts)
    while pending:
        for target in graph[pending.pop()]:
            if target not in result:
                result.add(target)
                pending.append(target)
    return result


def _arrow(points: tuple[tuple[int, int], ...]) -> ArrowGeometry:
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if y2 > y1:
        return ArrowGeometry(((x2 - 4, y2 - 8), (x2, y2), (x2 + 4, y2 - 8)))
    if y2 < y1:
        return ArrowGeometry(((x2 - 4, y2 + 8), (x2, y2), (x2 + 4, y2 + 8)))
    if x2 > x1:
        return ArrowGeometry(((x2 - 8, y2 - 4), (x2, y2), (x2 - 8, y2 + 4)))
    return ArrowGeometry(((x2 + 8, y2 - 4), (x2, y2), (x2 + 8, y2 + 4)))


def _wrap_title(text: str, width: int, size: float, family: str) -> tuple[str, ...]:
    if measure_text(text, size, family) <= width:
        return (text,)
    words = text.split()
    if len(words) <= 1:
        midpoint = max(1, len(text) // 2)
        return (text[:midpoint], text[midpoint:])
    lines = [""]
    for word in words:
        candidate = f"{lines[-1]} {word}".strip()
        if lines[-1] and measure_text(candidate, size, family) > width:
            lines.append(word)
        else:
            lines[-1] = candidate
    return tuple(lines[:2])


def _grid(value: float | int) -> int:
    return int(round(float(value) / 4) * 4)
