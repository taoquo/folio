from __future__ import annotations

from collections import Counter

from ..scene import ResolvedScene, SceneGroup
from .models import DrawingDiagnostic


def validate_scene_accessibility(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    if not scene.title.text.strip():
        diagnostics.append(DrawingDiagnostic("ERROR", "AX001", "scene title must be non-empty"))
    if not (scene.description or scene.title.text).strip():
        diagnostics.append(DrawingDiagnostic("ERROR", "AX002", "scene description must be non-empty"))
    if not scene.language.strip():
        diagnostics.append(DrawingDiagnostic("ERROR", "AX003", "scene language must be non-empty"))

    node_ids = [node.id for node in scene.nodes]
    primitive_id_list = _primitive_id_list(scene.primitives)
    primitive_ids = set(primitive_id_list)
    annotation_ids = [item.id for item in scene.annotations]
    semantic_ids = [
        *node_ids,
        *(item_id for item_id in scene.reading_order if item_id in primitive_ids or item_id in annotation_ids),
    ]
    order = scene.reading_order
    for node_id, count in Counter(order).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "AX200", "logical reading order contains duplicate ids", node_id))
    missing = [node_id for node_id in semantic_ids if node_id not in order]
    known = set(node_ids) | set(annotation_ids) | primitive_ids
    unknown = [node_id for node_id in order if node_id not in known]
    if missing:
        diagnostics.append(DrawingDiagnostic("ERROR", "AX201", "logical reading order omits scene nodes", ",".join(missing)))
    if unknown:
        diagnostics.append(DrawingDiagnostic("ERROR", "AX202", "logical reading order references unknown scene nodes", ",".join(unknown)))
    all_ids = [*node_ids, *primitive_id_list, *annotation_ids]
    duplicates = sorted(item_id for item_id, count in Counter(all_ids).items() if count > 1)
    if duplicates:
        diagnostics.append(DrawingDiagnostic("ERROR", "AX203", "scene contains duplicate SVG ids", ",".join(duplicates)))
    return diagnostics


def _primitive_id_list(primitives: tuple[object, ...]) -> list[str]:
    result: list[str] = []
    for item in primitives:
        item_id = getattr(item, "id", None)
        if isinstance(item_id, str):
            result.append(item_id)
        if isinstance(item, SceneGroup):
            result.extend(_primitive_id_list(item.children))
    return result
