from __future__ import annotations

"""Pure geometry helpers for measuring resolved scene content.

These helpers are shared by the visual quality gate and the output viewport.
They never inspect diagram semantics, so they stay safe for every compiler.
"""

from math import isfinite
from typing import Iterable

from .scene import (
    ResolvedScene,
    SceneBox,
    SceneCircle,
    SceneClip,
    SceneGroup,
    SceneLine,
    ScenePath,
    ScenePolyline,
    SceneRect,
    SceneText,
)
from .typography.measure import measure_text
from .validation.primitives import path_geometry_points


def flatten_primitives(primitives: Iterable[object]) -> Iterable[object]:
    for item in primitives:
        if isinstance(item, SceneGroup):
            yield from flatten_primitives(item.children)
        else:
            yield item


def primitive_box(item: object) -> SceneBox | None:
    if isinstance(item, (SceneRect, SceneClip)):
        return item.box
    if isinstance(item, SceneCircle):
        return SceneBox(item.cx - item.r, item.cy - item.r, item.r * 2, item.r * 2)
    if isinstance(item, SceneLine):
        return points_box((item.start, item.end))
    if isinstance(item, ScenePolyline):
        return points_box(item.points)
    if isinstance(item, ScenePath):
        try:
            return points_box(path_geometry_points(item.d))
        except ValueError:
            return None
    return None


def text_box(item: SceneText) -> SceneBox:
    width = max(1, int(round(measure_text(item.text, item.size, item.family))))
    x = item.x - width if item.anchor == "end" else item.x - width // 2 if item.anchor == "middle" else item.x
    height = max(1, int(round(item.size * 1.25)))
    return SceneBox(int(round(x)), int(round(item.y - height)), width, height)


def points_box(points: Iterable[tuple[float, float]]) -> SceneBox:
    values = tuple(points)
    if not values:
        return SceneBox(0, 0, 0, 0)
    xs = [point[0] for point in values if isfinite(float(point[0]))]
    ys = [point[1] for point in values if isfinite(float(point[1]))]
    if not xs or not ys:
        return SceneBox(0, 0, 0, 0)
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    return SceneBox(int(left), int(top), max(1, int(right - left)), max(1, int(bottom - top)))


def union_boxes(boxes: Iterable[SceneBox]) -> SceneBox:
    values = tuple(boxes)
    left = min(item.x for item in values)
    top = min(item.y for item in values)
    right = max(item.x + item.w for item in values)
    bottom = max(item.y + item.h for item in values)
    return SceneBox(left, top, right - left, bottom - top)


def scene_content_boxes(scene: ResolvedScene) -> list[SceneBox]:
    """Every box that carries ink below the diagram title."""
    boxes: list[SceneBox] = [node.box for node in scene.nodes]
    boxes.extend(region.box for region in scene.regions if region.box)
    boxes.extend(annotation.box for annotation in scene.annotations)
    if scene.legend:
        boxes.append(scene.legend.box)
    for edge in scene.edges:
        boxes.append(points_box(edge.points))
        if edge.label_box:
            boxes.append(edge.label_box)
    for item in flatten_primitives(scene.primitives):
        if isinstance(item, SceneClip):
            continue
        box = primitive_box(item)
        if box:
            boxes.append(box)
        elif isinstance(item, SceneText):
            boxes.append(text_box(item))
    return [box for box in boxes if box.w >= 0 and box.h >= 0]


def scene_ink_box(scene: ResolvedScene) -> SceneBox | None:
    """Content bounds including the diagram title, or None for an empty scene."""
    boxes = scene_content_boxes(scene)
    boxes.append(text_box(scene.title))
    for region in scene.regions:
        boxes.append(text_box(region.label))
    for node in scene.nodes:
        boxes.extend(text_box(item) for item in node.text_runs)
    for edge in scene.edges:
        if edge.label:
            boxes.append(text_box(edge.label))
    boxes = [box for box in boxes if box.w > 0 and box.h > 0]
    if not boxes:
        return None
    return union_boxes(boxes)
