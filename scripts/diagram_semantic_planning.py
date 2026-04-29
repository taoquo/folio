from __future__ import annotations

import re
from typing import Any

from diagram_models import load_diagram_spec


def extract_architecture_semantics(text: str) -> dict[str, Any]:
    lowered = text.lower()
    is_ecs = "ecs" in lowered and "world" in lowered and "system" in lowered

    if is_ecs:
        return {
            "layers": [
                {"id": "surface", "label": "Surface", "purpose": "Input and scene ingress", "order": 1},
                {"id": "runtime", "label": "Runtime", "purpose": "Frame execution", "order": 2},
                {"id": "data", "label": "Data", "purpose": "State and resource ownership", "order": 3},
            ],
            "groups": [
                {
                    "id": "runtime-loop",
                    "label": "Runtime Loop",
                    "kind": "runtime-loop",
                    "layer": "runtime",
                    "members": ["scheduler", "world", "systems"],
                    "summary": "Main per-frame path",
                }
            ],
            "nodes": [
                {
                    "id": "input",
                    "kind": "external",
                    "label": "Input Router",
                    "role": "entry",
                    "layer": "surface",
                    "sublabel": "events",
                    "importance": "secondary",
                    "state_owner": False,
                    "lifecycle_phase": "runtime",
                },
                {
                    "id": "scene",
                    "kind": "external",
                    "label": "Scene Loader",
                    "role": "resource-loader",
                    "layer": "surface",
                    "sublabel": "prefabs",
                    "importance": "secondary",
                    "state_owner": False,
                    "lifecycle_phase": "bootstrap",
                },
                {
                    "id": "scheduler",
                    "kind": "service",
                    "label": "Frame Scheduler",
                    "role": "scheduler",
                    "layer": "runtime",
                    "group": "runtime-loop",
                    "sublabel": "fixed tick",
                    "importance": "primary",
                    "state_owner": False,
                    "lifecycle_phase": "runtime",
                },
                {
                    "id": "world",
                    "kind": "service",
                    "label": "ECS World",
                    "role": "world",
                    "layer": "runtime",
                    "group": "runtime-loop",
                    "sublabel": "entity orchestration",
                    "description": "Owns entity lifetimes and component registration",
                    "importance": "primary",
                    "state_owner": True,
                    "lifecycle_phase": "runtime",
                },
                {
                    "id": "systems",
                    "kind": "service",
                    "label": "System Pipeline",
                    "role": "executor",
                    "layer": "runtime",
                    "group": "runtime-loop",
                    "sublabel": "frame systems",
                    "importance": "primary",
                    "state_owner": False,
                    "lifecycle_phase": "runtime",
                },
                {
                    "id": "stores",
                    "kind": "store",
                    "label": "Component Stores",
                    "role": "storage",
                    "layer": "data",
                    "sublabel": "dense arrays",
                    "importance": "secondary",
                    "state_owner": True,
                    "lifecycle_phase": "runtime",
                },
                {
                    "id": "cache",
                    "kind": "cloud",
                    "label": "Resource Cache",
                    "role": "cache",
                    "layer": "data",
                    "sublabel": "meshes · textures",
                    "importance": "background",
                    "state_owner": True,
                    "lifecycle_phase": "background",
                },
            ],
            "edges": [
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
            ],
            "focus_node": "world",
            "focus_path": ["scheduler", "world", "systems"],
            "focus_reason": "World owns runtime state while systems execute frame work.",
            "legend": [
                {"flow": "control", "label": "Frame control", "reason": "Scheduler advances world"},
                {"flow": "query", "label": "Runtime query path", "reason": "Systems read world views"},
                {"flow": "write", "label": "State mutation", "reason": "Systems update component storage"},
            ],
        }

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


def _choose_layout(semantics: dict[str, Any]) -> str:
    layer_ids = [layer["id"] for layer in semantics.get("layers", [])]
    if {"surface", "runtime", "data"}.issubset(set(layer_ids)):
        return "horizontal-layers"
    if re.search(r"foundation|interface|core", " ".join(layer_ids)):
        return "vertical-stack"
    return "horizontal-layers"
