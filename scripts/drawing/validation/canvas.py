from __future__ import annotations

from math import isfinite
from collections import Counter

from ..scene import (
    ResolvedScene,
    SceneBox,
    SceneText,
)
from .models import DrawingDiagnostic


def _inside(box: SceneBox, width: int, height: int) -> bool:
    return box.x >= 0 and box.y >= 0 and box.w >= 0 and box.h >= 0 and box.x + box.w <= width and box.y + box.h <= height


def _finite(values: tuple[float | int, ...]) -> bool:
    return all(isfinite(float(value)) for value in values)


def _text_inside(item: SceneText, width: int, height: int) -> bool:
    return _finite((item.x, item.y, item.size)) and 0 <= item.x <= width and 0 <= item.y <= height and item.size > 0


def validate_canvas(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    """Validate type-neutral canvas bounds, finite geometry, ids, and logical order."""
    diagnostics: list[DrawingDiagnostic] = []
    if scene.width <= 0 or scene.height <= 0:
        diagnostics.append(DrawingDiagnostic("ERROR", "CV001", "canvas dimensions must be positive"))
        return diagnostics

    node_ids = [node.id for node in scene.nodes]
    for node_id, count in Counter(node_ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "CV002", "duplicate scene node id", node_id))
    edge_ids = [edge.id for edge in scene.edges]
    for edge_id, count in Counter(edge_ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "CV003", "duplicate scene edge id", edge_id))

    for node in scene.nodes:
        box = node.box
        if not _finite((box.x, box.y, box.w, box.h)) or not _inside(box, scene.width, scene.height):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV100", "node outside canvas", node.id))
    for edge in scene.edges:
        if len(edge.points) < 2 or not all(_finite(point) for point in edge.points):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV101", "edge path is missing or non-finite", edge.id))
        elif any(not (0 <= x <= scene.width and 0 <= y <= scene.height) for x, y in edge.points):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV102", "edge path outside canvas", edge.id))
        if len(edge.arrow.points) != 3 or not all(_finite(point) for point in edge.arrow.points):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV103", "arrow geometry must contain three finite points", edge.id))
        elif any(not (0 <= x <= scene.width and 0 <= y <= scene.height) for x, y in edge.arrow.points):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV104", "arrow geometry outside canvas", edge.id))
        if edge.label_box and not _inside(edge.label_box, scene.width, scene.height):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV105", "edge label outside canvas", edge.id))
    for region in scene.regions:
        if region.box and not _inside(region.box, scene.width, scene.height):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV106", "region outside canvas", region.id))
    for item in scene.annotations:
        if not _inside(item.box, scene.width, scene.height):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV107", "annotation outside canvas", item.id))
        if item.leader and any(not (0 <= x <= scene.width and 0 <= y <= scene.height) for x, y in item.leader):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV108", "annotation leader outside canvas", item.id))
    if scene.legend and not _inside(scene.legend.box, scene.width, scene.height):
        diagnostics.append(DrawingDiagnostic("ERROR", "CV109", "legend outside canvas", "legend"))
    texts = [scene.title]
    texts.extend(region.label for region in scene.regions)
    texts.extend(text for node in scene.nodes for text in node.text_runs)
    texts.extend(edge.label for edge in scene.edges if edge.label)
    texts.extend(item.text for item in scene.annotations)
    if scene.legend:
        texts.append(scene.legend.title)
        texts.extend(item.label for item in scene.legend.items)
    for item in texts:
        if not _text_inside(item, scene.width, scene.height):
            diagnostics.append(DrawingDiagnostic("ERROR", "CV110", "text anchor outside canvas", item.text))

    return diagnostics
