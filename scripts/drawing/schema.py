from __future__ import annotations

from copy import deepcopy
from collections import Counter
from typing import Any

from .canvas_contract import GRAPH_CANVAS, canvas_issues


SCHEMA_VERSION = "2.0"


def migrate_v1_payload(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(payload)
    version = str(migrated.get("schema_version", "1.0"))
    if version == SCHEMA_VERSION:
        return migrated
    if not version.startswith("1."):
        raise ValueError(f"unsupported DrawingPlan schema major version: {version}")
    migrated["schema_version"] = SCHEMA_VERSION
    migrated.setdefault("language", "en")
    if migrated.get("kind") == "flowchart":
        return migrated
    for node in migrated.get("nodes", []):
        node.setdefault("size_tier", "regular")
        node.setdefault("pictogram", None)
        node.setdefault("content", {}).setdefault("metadata_required", False)
    annotations = []
    for index, item in enumerate(migrated.get("annotations", [])):
        if isinstance(item, str):
            annotations.append(
                {
                    "id": f"annotation:{index}",
                    "target": "diagram",
                    "target_kind": "diagram",
                    "kind": "note",
                    "text": item,
                    "emphasis": "normal",
                }
            )
        else:
            annotations.append(item)
    migrated["annotations"] = annotations
    legend = migrated.get("legend")
    if isinstance(legend, list):
        migrated["legend"] = {"title": "LEGEND", "items": legend} if legend else None
    return migrated


def validate_plan_payload(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if payload.get("kind") == "flowchart":
        for required in ("schema_version", "kind", "title", "nodes", "edges"):
            if required not in payload:
                issues.append(f"missing required field: {required}")
        if str(payload.get("schema_version", "")).split(".", 1)[0] != "2":
            issues.append("schema_version must use major version 2")
        if not isinstance(payload.get("nodes", []), list) or not isinstance(payload.get("edges", []), list):
            issues.append("nodes and edges must be arrays")
            return issues
        return [*issues, *_validate_flowchart_payload(payload)]
    allowed = {
        "schema_version", "kind", "title", "composition", "hierarchy", "regions", "nodes", "edges",
        "annotations", "legend", "width", "height", "subtitle", "caption", "explanation", "reductions", "language",
    }
    unknown = sorted(set(payload) - allowed)
    issues.extend(f"unknown field: {name}" for name in unknown)
    required_fields = ["schema_version", "kind", "title", "nodes", "edges"]
    if payload.get("kind") == "architecture":
        required_fields.extend(("composition", "hierarchy"))
    for required in required_fields:
        if required not in payload:
            issues.append(f"missing required field: {required}")
    if str(payload.get("schema_version", "")).split(".", 1)[0] != "2":
        issues.append("schema_version must use major version 2")
    if payload.get("kind") not in {"architecture", "flowchart"}:
        issues.append("kind must be architecture or flowchart")
    if not isinstance(payload.get("nodes", []), list) or not isinstance(payload.get("edges", []), list):
        issues.append("nodes and edges must be arrays")
        return issues
    if not isinstance(payload.get("title"), str) or not payload.get("title", "").strip():
        issues.append("title must be a non-empty string")
    _validate_canvas_dimensions(payload, issues)
    _validate_architecture_intent(payload, issues)
    node_allowed = {"id", "archetype", "emphasis", "region", "content", "pictogram", "size_tier"}
    for index, node in enumerate(payload.get("nodes", [])):
        if not isinstance(node, dict):
            issues.append(f"nodes[{index}] must be an object")
            continue
        issues.extend(f"nodes[{index}]: unknown field: {name}" for name in sorted(set(node) - node_allowed))
        for required in ("id", "archetype", "emphasis", "content"):
            if required not in node:
                issues.append(f"nodes[{index}]: missing required field: {required}")
        if not isinstance(node.get("id"), str) or not node.get("id", "").strip():
            issues.append(f"nodes[{index}].id must be a non-empty string")
        if node.get("size_tier", "regular") not in {"compact", "regular", "wide"}:
            issues.append(f"nodes[{index}].size_tier is invalid")
        if node.get("archetype") not in {"component", "datastore", "external", "cloud"}:
            issues.append(f"nodes[{index}].archetype is invalid")
        if node.get("emphasis") not in {"focal", "normal", "background"}:
            issues.append(f"nodes[{index}].emphasis is invalid")
        if node.get("pictogram") is not None and node.get("pictogram") not in {
            "client", "gateway", "compute", "queue", "database", "cache", "storage", "cloud",
            "security", "observability", "network", "external-system",
        }:
            issues.append(f"nodes[{index}].pictogram is invalid")
        content = node.get("content", {})
        content_allowed = {"eyebrow", "title", "metadata", "description", "metadata_required"}
        if not isinstance(content, dict):
            issues.append(f"nodes[{index}].content must be an object")
        else:
            issues.extend(f"nodes[{index}].content: unknown field: {name}" for name in sorted(set(content) - content_allowed))
            if "title" not in content:
                issues.append(f"nodes[{index}].content: missing required field: title")
    edge_allowed = {"id", "source", "target", "channel", "emphasis", "label", "direction", "route_policy"}
    for index, edge in enumerate(payload.get("edges", [])):
        if not isinstance(edge, dict):
            issues.append(f"edges[{index}] must be an object")
            continue
        issues.extend(f"edges[{index}]: unknown field: {name}" for name in sorted(set(edge) - edge_allowed))
        for required in ("id", "source", "target", "channel", "emphasis"):
            if required not in edge:
                issues.append(f"edges[{index}]: missing required field: {required}")
        for field in ("id", "source", "target"):
            if not isinstance(edge.get(field), str) or not edge.get(field, "").strip():
                issues.append(f"edges[{index}].{field} must be a non-empty string")
        if edge.get("channel") not in {"primary-flow", "secondary-flow", "async-flow"}:
            issues.append(f"edges[{index}].channel is invalid")
        if edge.get("emphasis") not in {"focal", "normal", "background"}:
            issues.append(f"edges[{index}].emphasis is invalid")
        if edge.get("direction", "forward") != "forward":
            issues.append(f"edges[{index}].direction is unsupported")
        if edge.get("route_policy", "auto") != "auto":
            issues.append(f"edges[{index}].route_policy is unsupported")
    annotation_allowed = {"id", "target", "target_kind", "kind", "text", "emphasis"}
    for index, item in enumerate(payload.get("annotations", [])):
        if not isinstance(item, dict):
            issues.append(f"annotations[{index}] must be an object")
            continue
        issues.extend(f"annotations[{index}]: unknown field: {name}" for name in sorted(set(item) - annotation_allowed))
        if item.get("target_kind", "diagram") not in {"node", "edge", "region", "diagram"}:
            issues.append(f"annotations[{index}].target_kind is invalid")
        if item.get("kind", "note") not in {"note", "constraint", "risk", "navigation"}:
            issues.append(f"annotations[{index}].kind is invalid")
        if not isinstance(item.get("text"), str) or not item.get("text", "").strip():
            issues.append(f"annotations[{index}].text must be a non-empty string")
    _validate_architecture_regions(payload, issues)
    _validate_reductions(payload, issues)
    _validate_architecture_collections(payload, issues)
    return issues


def _validate_flowchart_payload(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    allowed = {"schema_version", "kind", "title", "focus", "nodes", "edges", "width", "height", "language", "axis"}
    issues.extend(f"unknown field: {name}" for name in sorted(set(payload) - allowed))
    if payload.get("axis", "top-down") not in {"top-down", "left-right"}:
        issues.append("axis must be top-down or left-right")
    if not isinstance(payload.get("title"), str) or not payload.get("title", "").strip():
        issues.append("title must be a non-empty string")
    _validate_canvas_dimensions(payload, issues)
    node_allowed = {"id", "type", "label", "description"}
    for index, node in enumerate(payload.get("nodes", [])):
        if not isinstance(node, dict):
            issues.append(f"nodes[{index}] must be an object")
            continue
        issues.extend(f"nodes[{index}]: unknown field: {name}" for name in sorted(set(node) - node_allowed))
        if node.get("type", "step") not in {"step", "decision", "terminal", "data", "subprocess"}:
            issues.append(f"nodes[{index}].type is invalid")
        for required in ("id", "label"):
            if required not in node:
                issues.append(f"nodes[{index}]: missing required field: {required}")
        if not isinstance(node.get("id"), str) or not node.get("id", "").strip():
            issues.append(f"nodes[{index}].id must be a non-empty string")
        if not isinstance(node.get("label"), str) or not node.get("label", "").strip():
            issues.append(f"nodes[{index}].label must be a non-empty string")
    edge_allowed = {"id", "source", "target", "kind", "label"}
    for index, edge in enumerate(payload.get("edges", [])):
        if not isinstance(edge, dict):
            issues.append(f"edges[{index}] must be an object")
            continue
        issues.extend(f"edges[{index}]: unknown field: {name}" for name in sorted(set(edge) - edge_allowed))
        if edge.get("kind", "sequence-flow") not in {"sequence-flow", "conditional-flow", "exception-flow"}:
            issues.append(f"edges[{index}].kind is invalid")
        for required in ("source", "target"):
            if required not in edge:
                issues.append(f"edges[{index}]: missing required field: {required}")
        for field in ("source", "target"):
            if not isinstance(edge.get(field), str) or not edge.get(field, "").strip():
                issues.append(f"edges[{index}].{field} must be a non-empty string")
        if "id" in edge and (not isinstance(edge.get("id"), str) or not edge.get("id", "").strip()):
            issues.append(f"edges[{index}].id must be a non-empty string")
    node_ids = [item.get("id") for item in payload.get("nodes", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    edge_ids = [item.get("id") for item in payload.get("edges", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    issues.extend(f"duplicate node id: {item}" for item in _duplicates(node_ids))
    issues.extend(f"duplicate edge id: {item}" for item in _duplicates(edge_ids))
    known = set(node_ids)
    for index, edge in enumerate(payload.get("edges", [])):
        if not isinstance(edge, dict):
            continue
        if edge.get("source") not in known:
            issues.append(f"edges[{index}].source references an unknown node")
        if edge.get("target") not in known:
            issues.append(f"edges[{index}].target references an unknown node")
    if payload.get("focus") is not None and payload.get("focus") not in known:
        issues.append("focus references an unknown node")
    return issues


def _duplicates(values: list[Any]) -> list[Any]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _validate_canvas_dimensions(payload: dict[str, Any], issues: list[str]) -> None:
    """Plan payloads share the graph canvas band with the V3 grammars.

    Flowchart layout still narrows the stage to its widest row, but the declared canvas has to
    start from the same 960-unit contract so hosts get one predictable input shape.
    """
    kind = str(payload.get("kind") or "diagram")
    issues.extend(canvas_issues(payload, kind=kind, band=GRAPH_CANVAS))


def _validate_architecture_intent(payload: dict[str, Any], issues: list[str]) -> None:
    composition = payload.get("composition")
    if not isinstance(composition, dict):
        issues.append("composition must be an object")
    else:
        allowed = {"pattern", "axis", "density", "spine", "sidecars"}
        issues.extend(f"composition: unknown field: {name}" for name in sorted(set(composition) - allowed))
        if composition.get("pattern") not in {"layered", "pipeline", "hub"}:
            issues.append("composition.pattern is invalid")
        if composition.get("axis") not in {"top-down", "left-right"}:
            issues.append("composition.axis is invalid")
        if composition.get("density", "restrained") not in {"restrained", "balanced", "dense"}:
            issues.append("composition.density is invalid")
        if not isinstance(composition.get("spine", []), list):
            issues.append("composition.spine must be an array")
        if not isinstance(composition.get("sidecars", {}), dict):
            issues.append("composition.sidecars must be an object")
    hierarchy = payload.get("hierarchy")
    if not isinstance(hierarchy, dict):
        issues.append("hierarchy must be an object")
    else:
        allowed = {"focus_node", "focus_path", "background_nodes"}
        issues.extend(f"hierarchy: unknown field: {name}" for name in sorted(set(hierarchy) - allowed))
        if not isinstance(hierarchy.get("focus_path", []), list):
            issues.append("hierarchy.focus_path must be an array")
        if not isinstance(hierarchy.get("background_nodes", []), list):
            issues.append("hierarchy.background_nodes must be an array")


def _validate_architecture_collections(payload: dict[str, Any], issues: list[str]) -> None:
    node_ids = [item.get("id") for item in payload.get("nodes", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    edge_ids = [item.get("id") for item in payload.get("edges", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    region_ids = [item.get("id") for item in payload.get("regions", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    annotation_ids = [item.get("id") for item in payload.get("annotations", []) if isinstance(item, dict) and isinstance(item.get("id"), str)]
    issues.extend(f"duplicate node id: {item}" for item in _duplicates(node_ids))
    issues.extend(f"duplicate edge id: {item}" for item in _duplicates(edge_ids))
    issues.extend(f"duplicate region id: {item}" for item in _duplicates(region_ids))
    issues.extend(f"duplicate annotation id: {item}" for item in _duplicates(annotation_ids))
    known_nodes = set(node_ids)
    known_edges = set(edge_ids)
    known_regions = set(region_ids)
    for index, node in enumerate(payload.get("nodes", [])):
        if isinstance(node, dict) and node.get("region") is not None and node.get("region") not in known_regions:
            issues.append(f"nodes[{index}].region references an unknown region")
    for index, edge in enumerate(payload.get("edges", [])):
        if not isinstance(edge, dict):
            continue
        if edge.get("source") not in known_nodes:
            issues.append(f"edges[{index}].source references an unknown node")
        if edge.get("target") not in known_nodes:
            issues.append(f"edges[{index}].target references an unknown node")
    composition = payload.get("composition") if isinstance(payload.get("composition"), dict) else {}
    for item in composition.get("spine", []) if isinstance(composition.get("spine", []), list) else []:
        if item not in known_nodes:
            issues.append(f"composition.spine references an unknown node: {item}")
    sidecars = composition.get("sidecars", {}) if isinstance(composition.get("sidecars", {}), dict) else {}
    for owner, members in sidecars.items():
        if owner not in known_nodes:
            issues.append(f"composition.sidecars owner is unknown: {owner}")
        if not isinstance(members, list):
            issues.append(f"composition.sidecars[{owner}] must be an array")
        else:
            issues.extend(f"composition.sidecars[{owner}] references an unknown node: {item}" for item in members if item not in known_nodes)
    hierarchy = payload.get("hierarchy") if isinstance(payload.get("hierarchy"), dict) else {}
    for field in ("focus_path", "background_nodes"):
        values = hierarchy.get(field, []) if isinstance(hierarchy.get(field, []), list) else []
        issues.extend(f"hierarchy.{field} references an unknown node: {item}" for item in values if item not in known_nodes)
    if hierarchy.get("focus_node") is not None and hierarchy.get("focus_node") not in known_nodes:
        issues.append("hierarchy.focus_node references an unknown node")
    for index, item in enumerate(payload.get("annotations", [])):
        if not isinstance(item, dict):
            continue
        known = known_nodes | known_edges | known_regions | {"diagram"}
        if item.get("target", "diagram") not in known:
            issues.append(f"annotations[{index}].target references an unknown object")
    legend = payload.get("legend")
    if legend is not None:
        if not isinstance(legend, dict) or not isinstance(legend.get("items", []), list):
            issues.append("legend must be an object with an items array")
        else:
            for index, item in enumerate(legend.get("items", [])):
                if not isinstance(item, dict) or item.get("channel") not in {"primary-flow", "secondary-flow", "async-flow"} or not isinstance(item.get("label"), str):
                    issues.append(f"legend.items[{index}] is invalid")


def _validate_architecture_regions(payload: dict[str, Any], issues: list[str]) -> None:
    regions = payload.get("regions", [])
    if not isinstance(regions, list):
        issues.append("regions must be an array")
        return
    allowed = {"id", "role", "label", "members", "treatment"}
    treatments = {"layer-band", "soft-boundary", "trust-boundary", "phase-band", "none"}
    for index, item in enumerate(regions):
        if not isinstance(item, dict):
            issues.append(f"regions[{index}] must be an object")
            continue
        issues.extend(f"regions[{index}]: unknown field: {name}" for name in sorted(set(item) - allowed))
        for field in ("id", "role", "label"):
            if not isinstance(item.get(field), str) or not item.get(field, "").strip():
                issues.append(f"regions[{index}].{field} must be a non-empty string")
        if not isinstance(item.get("members"), list) or not all(isinstance(value, str) and value for value in item.get("members", [])):
            issues.append(f"regions[{index}].members must be an array of ids")
        if item.get("treatment") not in treatments:
            issues.append(f"regions[{index}].treatment is invalid")


def _validate_reductions(payload: dict[str, Any], issues: list[str]) -> None:
    reductions = payload.get("reductions", [])
    if not isinstance(reductions, list):
        issues.append("reductions must be an array")
        return
    allowed = {"action", "targets", "reason", "applied"}
    for index, item in enumerate(reductions):
        if not isinstance(item, dict):
            issues.append(f"reductions[{index}] must be an object")
            continue
        issues.extend(f"reductions[{index}]: unknown field: {name}" for name in sorted(set(item) - allowed))
        if item.get("action") not in {"merge", "drop", "background", "split"}:
            issues.append(f"reductions[{index}].action is invalid")
        if not isinstance(item.get("targets"), list):
            issues.append(f"reductions[{index}].targets must be an array")
        if not isinstance(item.get("reason"), str) or not item.get("reason", "").strip():
            issues.append(f"reductions[{index}].reason must be a non-empty string")
        if not isinstance(item.get("applied"), bool):
            issues.append(f"reductions[{index}].applied must be boolean")


def normalize_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    migrated = migrate_v1_payload(payload)
    issues = validate_plan_payload(migrated)
    if issues:
        raise ValueError("invalid DrawingPlan: " + "; ".join(issues))
    return migrated
