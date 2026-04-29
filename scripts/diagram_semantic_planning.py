from __future__ import annotations

from typing import Any

from diagram_models import load_diagram_spec


NODE_CATALOG = [
    {
        "id": "input",
        "label": "Input Router",
        "kind": "external",
        "role": "entry",
        "layer": "surface",
        "sublabel": "events",
        "importance": "secondary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["input", "keyboard", "gamepad", "events"],
    },
    {
        "id": "scene",
        "label": "Scene Loader",
        "kind": "external",
        "role": "resource-loader",
        "layer": "surface",
        "sublabel": "prefabs · assets",
        "importance": "secondary",
        "state_owner": False,
        "lifecycle_phase": "bootstrap",
        "keywords": ["scene", "prefab", "asset", "loading", "loader"],
    },
    {
        "id": "gateway",
        "label": "API Gateway",
        "kind": "external",
        "role": "entry",
        "layer": "surface",
        "sublabel": "request ingress",
        "importance": "secondary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["gateway", "api gateway", "client requests", "request"],
    },
    {
        "id": "scheduler",
        "label": "Frame Scheduler",
        "kind": "service",
        "role": "scheduler",
        "layer": "runtime",
        "sublabel": "fixed tick",
        "importance": "primary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["scheduler", "fixed-tick", "fixed tick", "frame"],
    },
    {
        "id": "planner",
        "label": "Task Planner",
        "kind": "service",
        "role": "orchestrator",
        "layer": "runtime",
        "sublabel": "coordination",
        "importance": "primary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["planner", "task planner", "coordinates", "coordinate"],
    },
    {
        "id": "runtime",
        "label": "Model Runtime",
        "kind": "service",
        "role": "orchestrator",
        "layer": "runtime",
        "sublabel": "execution core",
        "importance": "primary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["model runtime", "runtime"],
    },
    {
        "id": "world",
        "label": "ECS World",
        "kind": "service",
        "role": "world",
        "layer": "runtime",
        "sublabel": "entity orchestration",
        "description": "Owns entity lifetimes and component registration",
        "importance": "primary",
        "state_owner": True,
        "lifecycle_phase": "runtime",
        "keywords": ["ecs world", "world", "entity lifetimes", "component registration"],
    },
    {
        "id": "systems",
        "label": "System Pipeline",
        "kind": "service",
        "role": "executor",
        "layer": "runtime",
        "sublabel": "execution band",
        "importance": "primary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["systems", "system pipeline", "query entities", "component masks"],
    },
    {
        "id": "tools",
        "label": "Tool Runtime",
        "kind": "service",
        "role": "tool-runtime",
        "layer": "runtime",
        "sublabel": "tool execution",
        "importance": "secondary",
        "state_owner": False,
        "lifecycle_phase": "runtime",
        "keywords": ["tool runtime", "tool", "tools"],
    },
    {
        "id": "stores",
        "label": "Component Stores",
        "kind": "store",
        "role": "storage",
        "layer": "data",
        "sublabel": "dense arrays",
        "importance": "secondary",
        "state_owner": True,
        "lifecycle_phase": "runtime",
        "keywords": ["component stores", "stores", "dense arrays", "components"],
    },
    {
        "id": "memory",
        "label": "Memory Store",
        "kind": "store",
        "role": "storage",
        "layer": "data",
        "sublabel": "retrieval state",
        "importance": "secondary",
        "state_owner": True,
        "lifecycle_phase": "runtime",
        "keywords": ["memory store", "memory"],
    },
    {
        "id": "cache",
        "label": "Resource Cache",
        "kind": "cloud",
        "role": "cache",
        "layer": "data",
        "sublabel": "shared assets",
        "importance": "background",
        "state_owner": True,
        "lifecycle_phase": "background",
        "keywords": ["cache", "resource cache", "resources"],
    },
    {
        "id": "observability",
        "label": "Observability",
        "kind": "cloud",
        "role": "event-bus",
        "layer": "data",
        "sublabel": "logs · traces",
        "importance": "background",
        "state_owner": True,
        "lifecycle_phase": "background",
        "keywords": ["observability", "telemetry", "events", "logs", "traces"],
    },
]


EDGE_RULES = [
    {
        "source": "input",
        "target": "scheduler",
        "kind": "secondary",
        "flow": "event",
        "interaction": "emits",
        "label": "events",
        "priority": "secondary",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "runtime",
    },
    {
        "source": "scene",
        "target": "cache",
        "kind": "secondary",
        "flow": "stream",
        "interaction": "loads",
        "label": "stream",
        "priority": "background",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "bootstrap",
    },
    {
        "source": "scene",
        "target": "world",
        "kind": "secondary",
        "flow": "write",
        "interaction": "loads",
        "label": "spawn",
        "priority": "secondary",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "bootstrap",
    },
    {
        "source": "gateway",
        "target": "planner",
        "kind": "primary",
        "flow": "control",
        "interaction": "routes",
        "label": "route",
        "priority": "primary",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "runtime",
    },
    {
        "source": "planner",
        "target": "runtime",
        "kind": "primary",
        "flow": "control",
        "interaction": "coordinates",
        "label": "plan",
        "priority": "primary",
        "source_port": "right",
        "target_port": "left",
        "route_hint": "straight",
        "phase": "runtime",
    },
    {
        "source": "runtime",
        "target": "tools",
        "kind": "secondary",
        "flow": "read",
        "interaction": "invokes",
        "label": "tool use",
        "priority": "secondary",
        "source_port": "right",
        "target_port": "left",
        "route_hint": "straight",
        "phase": "runtime",
    },
    {
        "source": "tools",
        "target": "memory",
        "kind": "secondary",
        "flow": "read",
        "interaction": "reads",
        "label": "retrieve",
        "priority": "secondary",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "runtime",
    },
    {
        "source": "tools",
        "target": "observability",
        "kind": "secondary",
        "flow": "write",
        "interaction": "writes",
        "label": "events",
        "priority": "background",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "background",
    },
    {
        "source": "scheduler",
        "target": "world",
        "kind": "primary",
        "flow": "control",
        "interaction": "schedules",
        "label": "tick",
        "priority": "primary",
        "source_port": "right",
        "target_port": "left",
        "route_hint": "straight",
        "phase": "runtime",
    },
    {
        "source": "world",
        "target": "systems",
        "kind": "primary",
        "flow": "query",
        "interaction": "queries",
        "label": "query",
        "priority": "primary",
        "source_port": "right",
        "target_port": "left",
        "route_hint": "straight",
        "phase": "runtime",
    },
    {
        "source": "systems",
        "target": "stores",
        "kind": "secondary",
        "flow": "write",
        "interaction": "mutates",
        "label": "write",
        "priority": "secondary",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "runtime",
    },
    {
        "source": "systems",
        "target": "cache",
        "kind": "secondary",
        "flow": "stream",
        "interaction": "reads",
        "label": "stream",
        "priority": "background",
        "source_port": "bottom",
        "target_port": "top",
        "route_hint": "drop_to_lower_layer",
        "phase": "runtime",
    },
]


FOCUS_PRIORITIES = ["world", "planner", "runtime", "scheduler", "systems", "tools", "gateway"]


def extract_architecture_semantics(text: str) -> dict[str, Any]:
    lowered = text.lower()
    nodes = _extract_nodes(lowered)
    node_ids = {node["id"] for node in nodes}
    edges = [rule.copy() for rule in EDGE_RULES if rule["source"] in node_ids and rule["target"] in node_ids]

    layers = _build_layers(nodes)
    groups = _build_groups(node_ids)
    focus_node = _choose_focus_node(node_ids)
    focus_path = _choose_focus_path(node_ids)
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


def _extract_nodes(lowered: str) -> list[dict[str, Any]]:
    nodes = []
    for item in NODE_CATALOG:
        if any(keyword in lowered for keyword in item["keywords"]):
            node = {key: value for key, value in item.items() if key != "keywords"}
            nodes.append(node)
    return nodes


def _build_layers(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layer_order = ["surface", "runtime", "data"]
    definitions = {
        "surface": {"label": "Surface Layer", "purpose": "Ingress and bootstrap interfaces", "order": 1},
        "runtime": {"label": "Runtime Layer", "purpose": "Main execution and orchestration", "order": 2},
        "data": {"label": "Data Layer", "purpose": "State and background ownership", "order": 3},
    }
    present = {node["layer"] for node in nodes}
    return [{"id": layer, **definitions[layer]} for layer in layer_order if layer in present]


def _build_groups(node_ids: set[str]) -> list[dict[str, Any]]:
    groups = []
    runtime_loop = [node_id for node_id in ["scheduler", "world", "systems"] if node_id in node_ids]
    if len(runtime_loop) >= 2:
        groups.append(
            {
                "id": "runtime-loop",
                "label": "Runtime Loop",
                "kind": "runtime-loop",
                "layer": "runtime",
                "members": runtime_loop,
                "summary": "Main per-frame execution path",
            }
        )
    control_core = [node_id for node_id in ["gateway", "planner", "runtime", "tools"] if node_id in node_ids]
    if len(control_core) >= 2:
        groups.append(
            {
                "id": "control-core",
                "label": "Control Core",
                "kind": "subsystem",
                "layer": "runtime",
                "members": control_core,
                "summary": "Request orchestration and tool execution",
            }
        )
    return groups


def _choose_focus_node(node_ids: set[str]) -> str:
    for candidate in FOCUS_PRIORITIES:
        if candidate in node_ids:
            return candidate
    return sorted(node_ids)[0]


def _choose_focus_path(node_ids: set[str]) -> list[str]:
    candidates = [
        ["scheduler", "world", "systems"],
        ["gateway", "planner", "runtime"],
        ["planner", "runtime", "tools"],
        ["runtime", "tools", "memory"],
    ]
    for path in candidates:
        if all(node in node_ids for node in path):
            return path
    return [node for node in FOCUS_PRIORITIES if node in node_ids][:3] or sorted(node_ids)[:1]


def _focus_reason(focus_node: str, focus_path: list[str]) -> str:
    if focus_node == "world":
        return "World owns runtime state while systems execute frame work."
    if focus_node == "planner":
        return "Planner coordinates request flow and hands execution to the runtime."
    if focus_node == "runtime":
        return "Runtime is the execution hub between orchestration and tools."
    return f"Primary path centers on {' -> '.join(focus_path)}."


def _build_legend(edges: list[dict[str, Any]]) -> list[dict[str, str]]:
    flow_reasons = {
        "control": "Control flow advances the main execution path",
        "query": "Query flow exposes runtime state to executors",
        "write": "Write flow mutates or records state",
        "read": "Read flow retrieves supporting context",
        "stream": "Stream flow loads or shares background resources",
        "event": "Event flow carries ingress signals",
    }
    seen = []
    for edge in edges:
        flow = edge["flow"]
        if flow in seen:
            continue
        seen.append(flow)
    return [{"flow": flow, "label": flow.replace("-", " ").title(), "reason": flow_reasons.get(flow)} for flow in seen]


def _choose_layout(semantics: dict[str, Any]) -> str:
    layer_ids = [layer["id"] for layer in semantics.get("layers", [])]
    if {"surface", "runtime", "data"}.issubset(set(layer_ids)):
        return "horizontal-layers"
    if "runtime" in layer_ids and "data" in layer_ids:
        return "horizontal-layers"
    if "surface" in layer_ids:
        return "vertical-stack"
    return "horizontal-layers"
