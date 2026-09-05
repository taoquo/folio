"""Payload checks every diagram family needs, whatever it draws.

Identifier uniqueness, unknown fields, self edges, indistinguishable parallel edges: none of
these depend on a family's geometry, so all twenty-three kinds share one implementation. Kept
apart from the geometry validators so a family importing these does not also inherit a graph
layout engine it has no use for.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from math import isfinite
from typing import Any

from ..canvas_contract import GRAPH_CANVAS, CanvasBand, canvas_issues
from ..scene import ResolvedScene
from .accessibility import validate_scene_accessibility
from .canvas import validate_canvas
from .geometry import validate_scene_geometry
from .models import DrawingDiagnostic, raise_for_errors
from .primitives import validate_scene_primitives


def common_payload_diagnostics(
    payload: dict[str, Any],
    *,
    kind: str,
    allowed: set[str],
    required: Iterable[str],
    code: str,
    band: CanvasBand = GRAPH_CANVAS,
    default_height: int | None = None,
) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    if payload.get("schema_version") != "3.0":
        diagnostics.append(DrawingDiagnostic("ERROR", code, "schema_version must be 3.0"))
    if payload.get("kind") != kind:
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"kind must be {kind}"))
    for name in required:
        if name not in payload:
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"missing required field: {name}"))
    # "canvas" belongs to the canvas contract rather than to any one family's vocabulary, the
    # same way "width" and "height" do, so it is allowed here instead of in 23 separate lists.
    for name in sorted(set(payload) - allowed - {"canvas"}):
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"unknown field: {name}"))
    if not isinstance(payload.get("title"), str) or not payload.get("title", "").strip():
        diagnostics.append(DrawingDiagnostic("ERROR", code, "title must be a non-empty string"))
    for issue in canvas_issues(payload, kind=kind, band=band, default_height=default_height):
        diagnostics.append(DrawingDiagnostic("ERROR", code, issue))
    if payload.get("language") is not None and (not isinstance(payload["language"], str) or not payload["language"].strip()):
        diagnostics.append(DrawingDiagnostic("ERROR", code, "language must be a non-empty string"))
    return diagnostics


def object_list(
    payload: dict[str, Any],
    name: str,
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> list[dict[str, Any]]:
    value = payload.get(name, [])
    if not isinstance(value, list):
        diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name} must be an array"))
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}] must be an object"))
        else:
            result.append(item)
    return result


def validate_object_fields(
    items: list[dict[str, Any]],
    *,
    name: str,
    allowed: set[str],
    required: Iterable[str],
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> None:
    for index, item in enumerate(items):
        for field in required:
            if field not in item:
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}] missing required field: {field}"))
        for field in sorted(set(item) - allowed):
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}] unknown field: {field}"))


def validate_item_strings(
    items: list[dict[str, Any]],
    fields: Iterable[str],
    *,
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> None:
    for item in items:
        for field in fields:
            if field in item and item[field] is not None and (not isinstance(item[field], str) or not item[field].strip()):
                diagnostics.append(DrawingDiagnostic("ERROR", code, f"{field} must be a non-empty string", str(item.get("id"))))


def validate_unique_ids(
    items: list[dict[str, Any]],
    *,
    name: str,
    diagnostics: list[DrawingDiagnostic],
    code: str,
) -> set[str]:
    ids: list[str] = []
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"{name}[{index}].id must be a non-empty string"))
        else:
            ids.append(item_id)
    for item_id, count in Counter(ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", code, f"duplicate {name} id", item_id))
    return set(ids)


def validate_no_self_edges(
    items: list[dict[str, Any]],
    *,
    diagnostics: list[DrawingDiagnostic],
    code: str,
    source_field: str = "source",
    target_field: str = "target",
) -> None:
    """Reject edges that start and end on the same node.

    Folio routes connectors between distinct boxes, so a self edge has nowhere to go: the polyline
    collapses behind its own node and only an orphan label survives. Sequence, ER, UML, and tree
    diagrams already refuse them; graph diagrams must fail the same way instead of shipping ink
    the reader cannot follow.
    """
    for item in items:
        source = item.get(source_field)
        if source is not None and source == item.get(target_field):
            diagnostics.append(DrawingDiagnostic(
                "ERROR", code, "edge cannot start and end on the same node", str(item.get("id")),
            ))


def validate_distinguishable_parallel_edges(
    items: list[dict[str, Any]],
    *,
    diagnostics: list[DrawingDiagnostic],
    code: str,
    label_fields: Iterable[str] = ("label",),
    channel_field: str | None = "channel",
) -> None:
    """Reject parallel edges a reader cannot tell apart.

    Two edges between the same pair are legitimate when something distinguishes them: a different
    label or a different channel. When the labels repeat, or are all missing, and the channel is the
    same too, the extra edge only adds ink and the diagram silently loses meaning.
    """
    fields = tuple(label_fields)
    seen: dict[tuple[str, str, str], set[str]] = {}
    for item in items:
        channel = str(item.get(channel_field)) if channel_field else ""
        pair = (str(item.get("source")), str(item.get("target")), channel)
        signature = edge_label_signature(item, fields)
        bucket = seen.setdefault(pair, set())
        if signature in bucket:
            diagnostics.append(DrawingDiagnostic(
                "ERROR", code,
                "parallel edges between the same pair need a distinct label or channel",
                str(item.get("id")),
            ))
        bucket.add(signature)


def edge_label_signature(item: dict[str, Any], fields: Iterable[str]) -> str:
    parts = [str(item[field]).strip() for field in fields if isinstance(item.get(field), str) and item[field].strip()]
    return "\u001f".join(parts)


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def validate_resolved_scene(scene: ResolvedScene) -> tuple[DrawingDiagnostic, ...]:
    diagnostics = tuple([
        *validate_canvas(scene),
        *validate_scene_primitives(scene),
        *validate_scene_accessibility(scene),
        *validate_scene_geometry(scene),
    ])
    raise_for_errors("scene", diagnostics)
    return diagnostics


def require_no_errors(stage: str, diagnostics: Iterable[DrawingDiagnostic]) -> tuple[DrawingDiagnostic, ...]:
    result = tuple(diagnostics)
    raise_for_errors(stage, result)
    return result


def reachable(starts: Iterable[str], edges: Iterable[tuple[str, str]]) -> set[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        graph[source].append(target)
    result = set(starts)
    pending = list(starts)
    while pending:
        for target in graph[pending.pop()]:
            if target not in result:
                result.add(target)
                pending.append(target)
    return result


def cycle_exists(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> bool:
    graph: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        graph[source].append(target)
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

    return any(visit(node) for node in nodes)
