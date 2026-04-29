from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import re

from diagram_models import load_diagram_spec


@dataclass(frozen=True)
class MatchRule:
    pattern: str
    score: int


@dataclass(frozen=True)
class NodeRule:
    id: str
    label: str
    kind: str
    role: str
    layer: str
    sublabel: str
    importance: str
    state_owner: bool
    lifecycle_phase: str
    description: Optional[str] = None
    rules: tuple[MatchRule, ...] = ()
    min_score: int = 3


@dataclass(frozen=True)
class EdgeRule:
    source: str
    target: str
    kind: str
    flow: str
    interaction: str
    label: str
    priority: str
    source_port: str
    target_port: str
    route_hint: str
    phase: str
    rules: tuple[MatchRule, ...] = ()
    min_score: int = 3


NODE_RULES = (
    NodeRule(
        id="input",
        label="Input Router",
        kind="external",
        role="entry",
        layer="surface",
        sublabel="events",
        importance="secondary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\binput router\b", 6),
            MatchRule(r"\bkeyboard\b", 4),
            MatchRule(r"\bgamepad\b", 4),
            MatchRule(r"\buser input\b", 4),
            MatchRule(r"\bplayer input\b", 4),
        ),
    ),
    NodeRule(
        id="scene",
        label="Scene Loader",
        kind="external",
        role="resource-loader",
        layer="surface",
        sublabel="prefabs · assets",
        importance="secondary",
        state_owner=False,
        lifecycle_phase="bootstrap",
        rules=(
            MatchRule(r"\bscene loader\b", 6),
            MatchRule(r"\bscene loading\b", 5),
            MatchRule(r"\bprefab", 4),
            MatchRule(r"\basset", 3),
        ),
    ),
    NodeRule(
        id="gateway",
        label="API Gateway",
        kind="external",
        role="entry",
        layer="surface",
        sublabel="request ingress",
        importance="secondary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bapi gateway\b", 7),
            MatchRule(r"\bgateway\b", 4),
            MatchRule(r"\bclient requests enter\b", 4),
            MatchRule(r"\brequests enter\b", 3),
        ),
    ),
    NodeRule(
        id="scheduler",
        label="Frame Scheduler",
        kind="service",
        role="scheduler",
        layer="runtime",
        sublabel="fixed tick",
        importance="primary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bfixed[- ]tick scheduler\b", 7),
            MatchRule(r"\bscheduler\b", 4),
            MatchRule(r"\beach frame\b", 3),
            MatchRule(r"\bfixed tick\b", 3),
        ),
    ),
    NodeRule(
        id="planner",
        label="Task Planner",
        kind="service",
        role="orchestrator",
        layer="runtime",
        sublabel="coordination",
        importance="primary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\btask planner\b", 7),
            MatchRule(r"\bplanner\b", 4),
            MatchRule(r"\bcoordinates a model runtime\b", 5),
        ),
    ),
    NodeRule(
        id="orchestrator",
        label="Workflow Orchestrator",
        kind="service",
        role="orchestrator",
        layer="runtime",
        sublabel="step coordination",
        importance="primary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bworkflow orchestrator\b", 8),
            MatchRule(r"\borchestrator\b", 4),
            MatchRule(r"\bworkflow state\b", 3),
            MatchRule(r"\bworker steps\b", 3),
        ),
    ),
    NodeRule(
        id="runtime",
        label="Model Runtime",
        kind="service",
        role="orchestrator",
        layer="runtime",
        sublabel="execution core",
        importance="primary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bmodel runtime\b", 8),
            MatchRule(r"\bruntime\b", 2),
        ),
        min_score=4,
    ),
    NodeRule(
        id="workers",
        label="Worker Pool",
        kind="service",
        role="executor",
        layer="runtime",
        sublabel="step execution",
        importance="secondary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bworker pool\b", 8),
            MatchRule(r"\bworker steps\b", 5),
            MatchRule(r"\bworkers\b", 4),
            MatchRule(r"\bstep execution\b", 4),
        ),
    ),
    NodeRule(
        id="processor",
        label="Stream Processor",
        kind="service",
        role="executor",
        layer="runtime",
        sublabel="transform stage",
        importance="primary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bstream processor\b", 8),
            MatchRule(r"\btransforms records\b", 5),
            MatchRule(r"\btransform\b", 3),
        ),
    ),
    NodeRule(
        id="world",
        label="ECS World",
        kind="service",
        role="world",
        layer="runtime",
        sublabel="entity orchestration",
        importance="primary",
        state_owner=True,
        lifecycle_phase="runtime",
        description="Owns entity lifetimes and component registration",
        rules=(
            MatchRule(r"\becs world\b", 8),
            MatchRule(r"\bthe world owns\b", 6),
            MatchRule(r"\bentity lifetimes\b", 5),
            MatchRule(r"\bcomponent registration\b", 5),
        ),
    ),
    NodeRule(
        id="systems",
        label="System Pipeline",
        kind="service",
        role="executor",
        layer="runtime",
        sublabel="execution band",
        importance="primary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bsystem pipeline\b", 8),
            MatchRule(r"\bsystems query\b", 6),
            MatchRule(r"\bcomponent masks\b", 4),
            MatchRule(r"\bsystems do not own persistent state\b", 4),
        ),
    ),
    NodeRule(
        id="tools",
        label="Tool Runtime",
        kind="service",
        role="tool-runtime",
        layer="runtime",
        sublabel="tool execution",
        importance="secondary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\btool runtime\b", 8),
            MatchRule(r"\btool execution\b", 4),
            MatchRule(r"\binvokes a tool runtime\b", 5),
        ),
    ),
    NodeRule(
        id="stores",
        label="Component Stores",
        kind="store",
        role="storage",
        layer="data",
        sublabel="dense arrays",
        importance="secondary",
        state_owner=True,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bcomponent stores\b", 8),
            MatchRule(r"\bdense arrays\b", 4),
            MatchRule(r"\bmutate component stores\b", 6),
        ),
    ),
    NodeRule(
        id="memory",
        label="Memory Store",
        kind="store",
        role="storage",
        layer="data",
        sublabel="retrieval state",
        importance="secondary",
        state_owner=True,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bmemory store\b", 8),
            MatchRule(r"\bretrieval context\b", 4),
        ),
    ),
    NodeRule(
        id="state-store",
        label="State Store",
        kind="store",
        role="storage",
        layer="data",
        sublabel="workflow state",
        importance="secondary",
        state_owner=True,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bstate store\b", 8),
            MatchRule(r"\bworkflow state\b", 6),
            MatchRule(r"\bpersists workflow state\b", 7),
        ),
    ),
    NodeRule(
        id="kafka",
        label="Kafka Bus",
        kind="cloud",
        role="event-bus",
        layer="data",
        sublabel="event stream",
        importance="primary",
        state_owner=True,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bkafka\b", 8),
            MatchRule(r"\bpublish events to kafka\b", 7),
            MatchRule(r"\bevent stream\b", 4),
        ),
    ),
    NodeRule(
        id="event-bus",
        label="Event Bus",
        kind="cloud",
        role="event-bus",
        layer="data",
        sublabel="retries · continuations",
        importance="background",
        state_owner=True,
        lifecycle_phase="background",
        rules=(
            MatchRule(r"\bevent bus\b", 8),
            MatchRule(r"\bretries\b", 4),
            MatchRule(r"\basync continuations\b", 5),
        ),
    ),
    NodeRule(
        id="warehouse",
        label="Warehouse",
        kind="store",
        role="storage",
        layer="data",
        sublabel="analytics state",
        importance="secondary",
        state_owner=True,
        lifecycle_phase="runtime",
        rules=(MatchRule(r"\bwarehouse\b", 8),),
    ),
    NodeRule(
        id="serving-api",
        label="Serving API",
        kind="service",
        role="entry",
        layer="surface",
        sublabel="query access",
        importance="secondary",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(MatchRule(r"\bserving api\b", 8),),
    ),
    NodeRule(
        id="dashboards",
        label="Dashboards",
        kind="external",
        role="entry",
        layer="surface",
        sublabel="analyst queries",
        importance="background",
        state_owner=False,
        lifecycle_phase="runtime",
        rules=(
            MatchRule(r"\bdashboards\b", 6),
            MatchRule(r"\banalysts query dashboards\b", 7),
        ),
    ),
    NodeRule(
        id="cache",
        label="Resource Cache",
        kind="cloud",
        role="cache",
        layer="data",
        sublabel="shared assets",
        importance="background",
        state_owner=True,
        lifecycle_phase="background",
        rules=(
            MatchRule(r"\bresource cache\b", 8),
            MatchRule(r"\bcache\b", 3),
            MatchRule(r"\bstream resources\b", 4),
        ),
    ),
    NodeRule(
        id="observability",
        label="Observability",
        kind="cloud",
        role="event-bus",
        layer="data",
        sublabel="logs · traces",
        importance="background",
        state_owner=True,
        lifecycle_phase="background",
        rules=(
            MatchRule(r"\bobservability\b", 8),
            MatchRule(r"\btelemetry\b", 5),
            MatchRule(r"\blogs\b", 3),
            MatchRule(r"\btraces\b", 3),
            MatchRule(r"\bpipeline health\b", 4),
        ),
    ),
)


EDGE_RULES = (
    EdgeRule("input", "scheduler", "secondary", "event", "emits", "events", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\binput events\b", 5), MatchRule(r"\bevents\b", 2))),
    EdgeRule("scene", "cache", "secondary", "stream", "loads", "stream", "background", "bottom", "top", "drop_to_lower_layer", "bootstrap", rules=(MatchRule(r"\bstream resources\b", 4), MatchRule(r"\bassets\b", 3))),
    EdgeRule("scene", "world", "secondary", "write", "loads", "spawn", "secondary", "bottom", "top", "drop_to_lower_layer", "bootstrap", rules=(MatchRule(r"\bscene loading\b", 5), MatchRule(r"\bfeed\b", 2))),
    EdgeRule("gateway", "planner", "primary", "control", "routes", "route", "primary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\btask planner\b", 5), MatchRule(r"\bapi gateway\b", 4))),
    EdgeRule("planner", "runtime", "primary", "control", "coordinates", "plan", "primary", "right", "left", "straight", "runtime", rules=(MatchRule(r"\bcoordinates a model runtime\b", 7), MatchRule(r"\bmodel runtime\b", 4))),
    EdgeRule("gateway", "orchestrator", "primary", "control", "routes", "start", "primary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bworkflow orchestrator\b", 6), MatchRule(r"\brequests enter\b", 3))),
    EdgeRule("orchestrator", "workers", "primary", "control", "schedules", "steps", "primary", "right", "left", "straight", "runtime", rules=(MatchRule(r"\bschedules worker steps\b", 7), MatchRule(r"\bworker steps\b", 4))),
    EdgeRule("orchestrator", "state-store", "secondary", "write", "writes", "state", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bpersists workflow state\b", 8), MatchRule(r"\bstate store\b", 4))),
    EdgeRule("orchestrator", "event-bus", "secondary", "event", "publishes", "events", "background", "bottom", "top", "drop_to_lower_layer", "background", rules=(MatchRule(r"\bpublishes events to an event bus\b", 8), MatchRule(r"\bretries\b", 3), MatchRule(r"\basync continuations\b", 3))),
    EdgeRule("gateway", "kafka", "secondary", "event", "publishes", "events", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bpublish events to kafka\b", 8), MatchRule(r"\bkafka\b", 3))),
    EdgeRule("kafka", "processor", "primary", "stream", "feeds", "stream", "primary", "top", "bottom", "rise_to_upper_layer", "runtime", rules=(MatchRule(r"\bstream processor\b", 5), MatchRule(r"\btransforms records\b", 5))),
    EdgeRule("processor", "warehouse", "secondary", "write", "writes", "load", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bwrites them\s+into a warehouse\b", 8), MatchRule(r"\bwarehouse\b", 3))),
    EdgeRule("dashboards", "serving-api", "secondary", "read", "queries", "query", "background", "left", "right", "straight", "runtime", rules=(MatchRule(r"\banalysts query dashboards through a serving api\b", 9), MatchRule(r"\bserving api\b", 3))),
    EdgeRule("serving-api", "warehouse", "secondary", "read", "reads", "serve", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bserving api\b", 3), MatchRule(r"\bwarehouse\b", 3))),
    EdgeRule("runtime", "tools", "secondary", "read", "invokes", "tool use", "secondary", "right", "left", "straight", "runtime", rules=(MatchRule(r"\binvokes a tool runtime\b", 8), MatchRule(r"\btool runtime\b", 4))),
    EdgeRule("tools", "memory", "secondary", "read", "reads", "retrieve", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\breads a memory store\b", 8), MatchRule(r"\bretrieval context\b", 4))),
    EdgeRule("tools", "observability", "secondary", "write", "writes", "events", "background", "bottom", "top", "drop_to_lower_layer", "background", rules=(MatchRule(r"\bwrites observability events\b", 8), MatchRule(r"\bbackground\b", 2))),
    EdgeRule("scheduler", "world", "primary", "control", "schedules", "tick", "primary", "right", "left", "straight", "runtime", rules=(MatchRule(r"\badvances the ecs world each frame\b", 9), MatchRule(r"\bfixed-tick scheduler\b", 4))),
    EdgeRule("world", "systems", "primary", "query", "queries", "query", "primary", "right", "left", "straight", "runtime", rules=(MatchRule(r"\bsystems query entities\b", 8), MatchRule(r"\bcomponent masks\b", 4))),
    EdgeRule("systems", "stores", "secondary", "write", "mutates", "write", "secondary", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bmutate component stores\b", 8),)),
    EdgeRule("systems", "cache", "secondary", "stream", "reads", "stream", "background", "bottom", "top", "drop_to_lower_layer", "runtime", rules=(MatchRule(r"\bstream resources through a cache\b", 8),)),
)


ROLE_PRIORITY = {"world": 8, "orchestrator": 7, "scheduler": 6, "tool-runtime": 5, "executor": 5, "event-bus": 4, "storage": 4, "entry": 3, "cache": 2}
IMPORTANCE_PRIORITY = {"primary": 5, "secondary": 3, "background": 1}


def collect_architecture_evidence(text: str) -> dict[str, dict[str, Any]]:
    lowered = text.lower()
    evidence: dict[str, dict[str, Any]] = {}
    for rule in NODE_RULES:
        score = 0
        reasons = []
        for matcher in rule.rules:
            if re.search(matcher.pattern, lowered):
                score += matcher.score
                reasons.append(matcher.pattern)
        evidence[rule.id] = {"score": score, "reasons": reasons, "node_rule": rule}
    return evidence


def select_architecture_nodes(evidence: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = []
    for node_id, item in evidence.items():
        rule: NodeRule = item["node_rule"]
        score = item["score"]
        if score < rule.min_score:
            continue
        node = {
            "id": rule.id,
            "label": rule.label,
            "kind": rule.kind,
            "role": rule.role,
            "layer": rule.layer,
            "sublabel": rule.sublabel,
            "importance": rule.importance,
            "state_owner": rule.state_owner,
            "lifecycle_phase": rule.lifecycle_phase,
        }
        if rule.description:
            node["description"] = rule.description
        nodes.append(node)
    return nodes


def extract_architecture_semantics(text: str) -> dict[str, Any]:
    evidence = collect_architecture_evidence(text)
    nodes = select_architecture_nodes(evidence)
    node_ids = {node["id"] for node in nodes}
    edges = _select_edges(text, node_ids)
    layers = _build_layers(nodes)
    groups = _build_groups(node_ids)
    focus_node = _choose_focus_node(evidence, node_ids)
    focus_path = _choose_focus_path(node_ids, edges)
    focus_reason = _focus_reason(focus_node, focus_path)
    legend = _build_legend(edges)

    if not nodes:
        return {
            "layers": [{"id": "core", "label": "Core", "purpose": "Main system band", "order": 1}],
            "groups": [],
            "nodes": [{"id": "core", "kind": "service", "label": "Core Service", "role": "orchestrator", "layer": "core"}],
            "edges": [],
            "focus_node": "core",
            "focus_path": ["core"],
            "focus_reason": "Fallback single-core architecture.",
            "legend": [],
        }

    return {
        "layers": layers,
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
        "focus_node": focus_node,
        "focus_path": focus_path,
        "focus_reason": focus_reason,
        "legend": legend,
    }


def plan_architecture_from_text(text: str, title: str) -> Any:
    semantics = extract_architecture_semantics(text)
    payload = {
        "kind": "architecture",
        "title": title,
        "layout": _choose_layout(semantics),
        "focus": semantics["focus_node"],
        "focus_path": semantics["focus_path"],
        "focus_reason": semantics["focus_reason"],
        "layers": semantics["layers"],
        "groups": semantics["groups"],
        "nodes": semantics["nodes"],
        "edges": semantics["edges"],
        "legend": semantics["legend"],
    }
    return load_diagram_spec(payload)


def _select_edges(text: str, node_ids: set[str]) -> list[dict[str, Any]]:
    lowered = text.lower()
    edges = []
    for rule in EDGE_RULES:
        if rule.source not in node_ids or rule.target not in node_ids:
            continue
        score = 0
        for matcher in rule.rules:
            if re.search(matcher.pattern, lowered):
                score += matcher.score
        if score < rule.min_score:
            continue
        edges.append(
            {
                "source": rule.source,
                "target": rule.target,
                "kind": rule.kind,
                "flow": rule.flow,
                "interaction": rule.interaction,
                "label": rule.label,
                "priority": rule.priority,
                "source_port": rule.source_port,
                "target_port": rule.target_port,
                "route_hint": rule.route_hint,
                "phase": rule.phase,
            }
        )
    return edges


def _build_layers(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layer_order = ["surface", "runtime", "data"]
    definitions = {
        "surface": {"label": "Surface Layer", "purpose": "Ingress and external interfaces", "order": 1},
        "runtime": {"label": "Runtime Layer", "purpose": "Execution and orchestration", "order": 2},
        "data": {"label": "Data Layer", "purpose": "State and background ownership", "order": 3},
    }
    present = {node["layer"] for node in nodes}
    return [{"id": layer, **definitions[layer]} for layer in layer_order if layer in present]


def _build_groups(node_ids: set[str]) -> list[dict[str, Any]]:
    groups = []
    candidates = [
        ("runtime-loop", "Runtime Loop", "runtime-loop", "runtime", ["scheduler", "world", "systems"], "Main per-frame execution path"),
        ("control-core", "Control Core", "subsystem", "runtime", ["gateway", "planner", "runtime", "tools"], "Request orchestration and tool execution"),
        ("workflow-core", "Workflow Core", "subsystem", "runtime", ["gateway", "orchestrator", "workers"], "Workflow routing and step execution"),
        ("data-pipeline", "Data Pipeline", "subsystem", "runtime", ["kafka", "processor", "warehouse"], "Streaming ingest and analytics load path"),
    ]
    for group_id, label, kind, layer, members, summary in candidates:
        present = [member for member in members if member in node_ids]
        if len(present) >= 2:
            groups.append({"id": group_id, "label": label, "kind": kind, "layer": layer, "members": present, "summary": summary})
    return groups


def _choose_focus_node(evidence: dict[str, dict[str, Any]], node_ids: set[str]) -> str:
    scored = []
    for node_id in node_ids:
        item = evidence[node_id]
        rule: NodeRule = item["node_rule"]
        score = item["score"] + ROLE_PRIORITY.get(rule.role, 0) + IMPORTANCE_PRIORITY.get(rule.importance, 0)
        scored.append((score, node_id))
    scored.sort(reverse=True)
    return scored[0][1]


def _choose_focus_path(node_ids: set[str], edges: list[dict[str, Any]]) -> list[str]:
    candidates = [
        ["scheduler", "world", "systems"],
        ["gateway", "orchestrator", "workers"],
        ["gateway", "planner", "runtime"],
        ["planner", "runtime", "tools"],
        ["kafka", "processor", "warehouse"],
        ["dashboards", "serving-api", "warehouse"],
    ]
    edge_pairs = {(edge["source"], edge["target"]) for edge in edges}
    for path in candidates:
        if all(node in node_ids for node in path) and all((path[i], path[i + 1]) in edge_pairs for i in range(len(path) - 1)):
            return path
    return sorted(node_ids)[:1]


def _focus_reason(focus_node: str, focus_path: list[str]) -> str:
    if focus_node == "world":
        return "World owns runtime state while systems execute frame work."
    if focus_node == "orchestrator":
        return "Orchestrator coordinates long-running workflow state and worker execution."
    if focus_node == "planner":
        return "Planner coordinates request flow and hands execution to the runtime."
    if focus_node == "runtime":
        return "Runtime is the execution hub between orchestration and tools."
    if focus_node == "processor":
        return "Processor is the transformation hinge between ingest and warehouse state."
    return f"Primary path centers on {' -> '.join(focus_path)}."


def _build_legend(edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    reasons = {
        "control": "Control flow advances the main execution path",
        "query": "Query flow exposes runtime state to executors",
        "write": "Write flow mutates or records state",
        "read": "Read flow retrieves supporting context",
        "stream": "Stream flow carries data through the pipeline",
        "event": "Event flow carries asynchronous signals",
    }
    seen = []
    for edge in edges:
        if edge["flow"] not in seen:
            seen.append(edge["flow"])
    return [{"flow": flow, "label": flow.replace("-", " ").title(), "reason": reasons.get(flow)} for flow in seen]


def _choose_layout(semantics: dict[str, Any]) -> str:
    layer_ids = [layer["id"] for layer in semantics.get("layers", [])]
    if {"surface", "runtime", "data"}.issubset(set(layer_ids)):
        return "horizontal-layers"
    if "runtime" in layer_ids and "data" in layer_ids:
        return "horizontal-layers"
    if "surface" in layer_ids:
        return "vertical-stack"
    return "horizontal-layers"
