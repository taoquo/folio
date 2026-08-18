from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

from ..scene import (
    ResolvedScene,
    SceneBox,
    SceneCircle,
    SceneClip,
    SceneGroup,
    SceneLine,
    ScenePath,
    ScenePolyline,
    SceneRect,
    SceneStyle,
    SceneText,
)
from ..theme.contrast import (
    GRAPHIC_MINIMUM,
    LARGE_TEXT_MINIMUM,
    NORMAL_TEXT_MINIMUM,
    composite as _composite,
    contrast_ratio,
    parse_hex as _parse_hex,
)
from ..theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from ..typography.measure import measure_text
from .models import DrawingDiagnostic
from .primitives import path_geometry_points


@dataclass(frozen=True)
class _PaintedShape:
    object_id: str
    box: SceneBox
    fill: str
    opacity: float


def validate_scene_quality(
    scene: ResolvedScene,
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
) -> list[DrawingDiagnostic]:
    """Run type-neutral, machine-executable visual quality checks.

    These checks intentionally inspect only resolved geometry and paint. They do
    not infer diagram semantics and therefore remain safe at the registry result
    boundary for every current and future compiler.
    """
    diagnostics: list[DrawingDiagnostic] = []
    diagnostics.extend(_validate_canvas_use(scene))
    diagnostics.extend(_validate_accent_budget(scene, theme))
    diagnostics.extend(_validate_compartments(scene))
    diagnostics.extend(_validate_contrast(scene))
    diagnostics.extend(_validate_text_collisions(scene))
    return diagnostics


def _validate_canvas_use(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    if scene.width <= 0 or scene.height <= 0:
        return []
    boxes = _content_boxes(scene)
    if not boxes:
        return [DrawingDiagnostic(
            "ERROR", "VQ100", "scene has no visible content below the title",
            hint="Add a meaningful mark, node, relationship, or annotation.",
        )]
    bounds = _union(boxes)
    canvas_area = scene.width * scene.height
    bounds_area = max(0, bounds.w) * max(0, bounds.h)
    utilization = bounds_area / canvas_area
    diagnostics: list[DrawingDiagnostic] = []
    if utilization < 0.08:
        diagnostics.append(DrawingDiagnostic(
            "TASTE", "VQ101",
            f"content uses only {utilization:.1%} of the canvas bounding area",
            hint="Use the available canvas or choose a smaller output size.",
        ))

    margins = {
        "left": bounds.x / scene.width,
        "right": (scene.width - bounds.x - bounds.w) / scene.width,
        "top": bounds.y / scene.height,
        "bottom": (scene.height - bounds.y - bounds.h) / scene.height,
    }
    largest_name, largest = max(margins.items(), key=lambda item: item[1])
    opposite = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}[largest_name]
    if largest > 0.45 and largest - margins[opposite] > 0.20:
        diagnostics.append(DrawingDiagnostic(
            "TASTE", "VQ102",
            f"content leaves an unusually large {largest_name} margin ({largest:.1%})",
            hint="Rebalance the layout unless the asymmetry carries meaning.",
        ))
    return diagnostics


def _validate_accent_budget(
    scene: ResolvedScene,
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
) -> list[DrawingDiagnostic]:
    brand = theme.brand.lower()
    accent_ids: set[str] = set()
    accent_area = 0.0

    for node in scene.nodes:
        if _style_uses(node.style, brand):
            accent_ids.add(node.id)
        if node.style.fill.lower() == brand:
            accent_area += node.box.w * node.box.h * _opacity(node.style)
    for edge in scene.edges:
        if _style_uses(edge.style, brand):
            accent_ids.add(edge.id)
    for region in scene.regions:
        if region.style and _style_uses(region.style, brand):
            accent_ids.add(region.id)
        if region.box and region.style and region.style.fill.lower() == brand:
            accent_area += region.box.w * region.box.h * _opacity(region.style)
    for annotation in scene.annotations:
        if _style_uses(annotation.style, brand):
            accent_ids.add("annotation")
        if annotation.style.fill.lower() == brand:
            accent_area += annotation.box.w * annotation.box.h * _opacity(annotation.style)

    for item in _flatten(scene.primitives):
        style = getattr(item, "style", None)
        item_id = getattr(item, "id", None)
        if isinstance(style, SceneStyle) and isinstance(item_id, str) and _style_uses(style, brand):
            accent_ids.add(_semantic_accent_id(item_id))
            if style.fill.lower() == brand:
                box = _primitive_box(item)
                if box:
                    factor = 0.35 if isinstance(item, ScenePath) else 1.0
                    accent_area += box.w * box.h * _opacity(style) * factor

    diagnostics: list[DrawingDiagnostic] = []
    if len(accent_ids) > 2:
        diagnostics.append(DrawingDiagnostic(
            "TASTE", "VQ103",
            f"scene contains {len(accent_ids)} accent-bearing visual elements; preferred maximum is 2",
            hint="Concentrate cinnabar-coral on one or two focal elements.",
            related_ids=tuple(sorted(accent_ids)),
        ))
    canvas_area = max(1, scene.width * scene.height)
    ratio = accent_area / canvas_area
    if ratio > 0.05:
        diagnostics.append(DrawingDiagnostic(
            "TASTE", "VQ104",
            f"solid accent fill covers approximately {ratio:.1%} of the canvas; preferred maximum is 5%",
            hint="Reduce saturated fill area or use the neutral/tint palette.",
        ))
    return diagnostics


def _validate_compartments(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    for group in _groups(scene.primitives):
        rectangles = [item for item in _flatten(group.children) if isinstance(item, SceneRect)]
        texts = [item for item in _flatten(group.children) if isinstance(item, SceneText)]
        dividers = [
            item for item in _flatten(group.children)
            if isinstance(item, SceneLine)
            and "divider" in item.id.lower()
            and "header" not in item.id.lower()
            and item.start[1] == item.end[1]
        ]
        for divider in dividers:
            container = next((
                item for item in rectangles
                if item.box.x <= min(divider.start[0], divider.end[0])
                and item.box.x + item.box.w >= max(divider.start[0], divider.end[0])
                and item.box.y < divider.start[1] < item.box.y + item.box.h
            ), None)
            if container is None:
                continue
            above = [text for text in texts if container.box.y < text.y < divider.start[1]]
            below = [text for text in texts if divider.start[1] < text.y < container.box.y + container.box.h]
            if not above or not below:
                diagnostics.append(DrawingDiagnostic(
                    "ERROR", "VQ105", "divider creates an empty visual compartment", divider.id,
                    hint="Remove the divider or populate both compartments.",
                    related_ids=(group.id, container.id),
                ))
    return diagnostics


def _validate_contrast(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    background = scene.background

    def check_text(item: SceneText, local_background: str, object_id: str) -> None:
        ratio = contrast_ratio(item.fill, local_background)
        if ratio is None:
            return
        weight = str(item.weight or "").lower()
        large = item.size >= 18 or (item.size >= 14 and weight in {"500", "600", "700", "bold"})
        minimum = LARGE_TEXT_MINIMUM if large else NORMAL_TEXT_MINIMUM
        if ratio + 1e-9 < minimum:
            diagnostics.append(DrawingDiagnostic(
                "ERROR", "VQ106",
                f"text contrast is {ratio:.2f}:1; WCAG minimum is {minimum:.1f}:1", object_id,
                hint="Use a darker text token or a lighter local background.",
            ))

    check_text(scene.title, background, "scene-title")
    for node in scene.nodes:
        local = _composite(node.style.fill, background, _opacity(node.style))
        for index, text in enumerate(node.text_runs):
            check_text(text, local, f"{node.id}:text:{index}")
        if node.style.stroke_width > 1:
            _check_graphic(diagnostics, node.style.stroke, local, node.id)
    for edge in scene.edges:
        if edge.style.stroke_width > 1:
            _check_graphic(diagnostics, edge.style.stroke, background, edge.id)
        if edge.label:
            check_text(edge.label, background, f"{edge.id}:label")
    for region in scene.regions:
        local = background
        if region.style:
            local = _composite(region.style.fill, background, _opacity(region.style))
            if region.style.stroke_width > 1:
                _check_graphic(diagnostics, region.style.stroke, local, region.id)
        check_text(region.label, local, f"{region.id}:label")
    for annotation in scene.annotations:
        local = _composite(annotation.style.fill, background, _opacity(annotation.style))
        check_text(annotation.text, local, f"{annotation.id}:text")
        if annotation.style.stroke_width > 1:
            _check_graphic(diagnostics, annotation.style.stroke, local, annotation.id)
    if scene.legend:
        local = _composite(scene.legend.style.fill, background, _opacity(scene.legend.style))
        check_text(scene.legend.title, local, "legend:title")
        for index, item in enumerate(scene.legend.items):
            check_text(item.label, local, f"legend:item:{index}")
            # Legend samples are decorative keys unless drawn with a stronger
            # stroke elsewhere in the scene; text still carries the meaning.

    shapes: list[_PaintedShape] = []
    for item in _flatten(scene.primitives):
        if isinstance(item, (SceneRect, SceneCircle)):
            box = _primitive_box(item)
            if box and item.style.fill.lower() != "none" and _parse_hex(item.style.fill):
                shapes.append(_PaintedShape(item.id, box, item.style.fill, _opacity(item.style)))
        if isinstance(item, SceneText):
            local = _background_at(item.x, item.y, shapes, background)
            check_text(item, local, f"primitive-text:{item.text}")
        style = getattr(item, "style", None)
        item_id = getattr(item, "id", None)
        if isinstance(style, SceneStyle) and isinstance(item_id, str):
            local = background
            box = _primitive_box(item)
            if box:
                local = _background_at(box.x + box.w / 2, box.y + box.h / 2, shapes[:-1], background)
            if style.stroke_width > 1:
                _check_graphic(diagnostics, style.stroke, local, item_id)
    return _dedupe(diagnostics)


def _check_graphic(
    diagnostics: list[DrawingDiagnostic],
    foreground: str,
    background: str,
    object_id: str,
) -> None:
    if foreground.lower() == "none":
        return
    ratio = contrast_ratio(foreground, background)
    if ratio is not None and ratio + 1e-9 < GRAPHIC_MINIMUM:
        diagnostics.append(DrawingDiagnostic(
            "WARNING", "VQ107",
            f"graphic contrast is {ratio:.2f}:1; WCAG non-text target is {GRAPHIC_MINIMUM:.1f}:1", object_id,
            hint="Confirm the low-contrast stroke is decorative, or use a darker token.",
        ))


def _validate_text_collisions(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    """Reject scenes where two text runs paint over each other.

    Boxes are measured on the ink band only (cap height above the baseline, no
    line-height padding), so stacked lines inside a node stay clean and only real
    glyph overlap is reported.
    """
    labelled = _labelled_texts(scene)
    diagnostics: list[DrawingDiagnostic] = []
    for index, (left_id, left) in enumerate(labelled):
        for right_id, right in labelled[index + 1:]:
            if _ink_overlap(left, right):
                diagnostics.append(DrawingDiagnostic(
                    "ERROR", "VQ108",
                    f"text overlaps {right_id}", left_id,
                    hint="Shift one label to a free slot or shorten the text.",
                    related_ids=(right_id,),
                ))
    return diagnostics


def _labelled_texts(scene: ResolvedScene) -> list[tuple[str, SceneText]]:
    items: list[tuple[str, SceneText]] = [("scene-title", scene.title)]
    for node in scene.nodes:
        items.extend((f"{node.id}:text:{index}", text) for index, text in enumerate(node.text_runs))
    for edge in scene.edges:
        if edge.label:
            items.append((f"{edge.id}:label", edge.label))
    items.extend((f"{region.id}:label", region.label) for region in scene.regions)
    items.extend((f"{annotation.id}:text", annotation.text) for annotation in scene.annotations)
    if scene.legend:
        items.append(("legend:title", scene.legend.title))
        items.extend((f"legend:item:{index}", item.label) for index, item in enumerate(scene.legend.items))
    items.extend(
        (f"primitive-text:{item.text}", item)
        for item in _flatten(scene.primitives)
        if isinstance(item, SceneText)
    )
    return [item for item in items if item[1].text.strip()]


def _ink_box(item: SceneText) -> SceneBox:
    width = measure_text(item.text, item.size, item.family)
    if item.tracking:
        width += item.tracking * item.size * max(0, len(item.text) - 1)
    width = max(1.0, width)
    x = item.x - width if item.anchor == "end" else item.x - width / 2 if item.anchor == "middle" else item.x
    return SceneBox(int(round(x)), int(round(item.y - item.size * 0.80)), int(round(width)), int(round(item.size)))


def _ink_overlap(left: SceneText, right: SceneText) -> bool:
    first, second = _ink_box(left), _ink_box(right)
    horizontal = min(first.x + first.w, second.x + second.w) - max(first.x, second.x)
    vertical = min(first.y + first.h, second.y + second.h) - max(first.y, second.y)
    return horizontal > 0 and vertical > 0


def _content_boxes(scene: ResolvedScene) -> list[SceneBox]:
    boxes: list[SceneBox] = [node.box for node in scene.nodes]
    boxes.extend(region.box for region in scene.regions if region.box)
    boxes.extend(annotation.box for annotation in scene.annotations)
    if scene.legend:
        boxes.append(scene.legend.box)
    for edge in scene.edges:
        boxes.append(_points_box(edge.points))
        if edge.label_box:
            boxes.append(edge.label_box)
    for item in _flatten(scene.primitives):
        if isinstance(item, SceneClip):
            continue
        box = _primitive_box(item)
        if box:
            boxes.append(box)
        elif isinstance(item, SceneText):
            boxes.append(_text_box(item))
    return [box for box in boxes if box.w >= 0 and box.h >= 0]


def _primitive_box(item: object) -> SceneBox | None:
    if isinstance(item, (SceneRect, SceneClip)):
        return item.box
    if isinstance(item, SceneCircle):
        return SceneBox(item.cx - item.r, item.cy - item.r, item.r * 2, item.r * 2)
    if isinstance(item, SceneLine):
        return _points_box((item.start, item.end))
    if isinstance(item, ScenePolyline):
        return _points_box(item.points)
    if isinstance(item, ScenePath):
        try:
            return _points_box(path_geometry_points(item.d))
        except ValueError:
            return None
    return None


def _text_box(item: SceneText) -> SceneBox:
    width = max(1, int(round(measure_text(item.text, item.size, item.family))))
    x = item.x - width if item.anchor == "end" else item.x - width // 2 if item.anchor == "middle" else item.x
    height = max(1, int(round(item.size * 1.25)))
    return SceneBox(int(round(x)), int(round(item.y - height)), width, height)


def _points_box(points: Iterable[tuple[float, float]]) -> SceneBox:
    values = tuple(points)
    if not values:
        return SceneBox(0, 0, 0, 0)
    xs = [point[0] for point in values if isfinite(float(point[0]))]
    ys = [point[1] for point in values if isfinite(float(point[1]))]
    if not xs or not ys:
        return SceneBox(0, 0, 0, 0)
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    return SceneBox(int(left), int(top), max(1, int(right - left)), max(1, int(bottom - top)))


def _union(boxes: Iterable[SceneBox]) -> SceneBox:
    values = tuple(boxes)
    left = min(item.x for item in values)
    top = min(item.y for item in values)
    right = max(item.x + item.w for item in values)
    bottom = max(item.y + item.h for item in values)
    return SceneBox(left, top, right - left, bottom - top)


def _flatten(primitives: Iterable[object]) -> Iterable[object]:
    for item in primitives:
        if isinstance(item, SceneGroup):
            yield from _flatten(item.children)
        else:
            yield item


def _groups(primitives: Iterable[object]) -> Iterable[SceneGroup]:
    for item in primitives:
        if isinstance(item, SceneGroup):
            yield item
            yield from _groups(item.children)


_SERIES_MARK_PREFIXES = {"bar", "point", "candle", "segment", "line", "body", "wick"}


def _semantic_accent_id(item_id: str) -> str:
    parts = item_id.split(":")
    if parts[0] in _SERIES_MARK_PREFIXES and len(parts) > 1:
        # One highlighted data series is a single accent voice even when it renders
        # as several mark types (line plus points, candle body plus wick).
        return f"series:{parts[1]}"
    return item_id


def _style_uses(style: SceneStyle, color: str) -> bool:
    return style.fill.lower() == color or style.stroke.lower() == color


def _opacity(style: SceneStyle) -> float:
    return 1.0 if style.fill_opacity is None else max(0.0, min(1.0, style.fill_opacity))


def _background_at(x: float, y: float, shapes: list[_PaintedShape], fallback: str) -> str:
    candidates = [shape for shape in shapes if _contains(shape.box, x, y)]
    if not candidates:
        return fallback
    shape = min(candidates, key=lambda item: item.box.w * item.box.h)
    return _composite(shape.fill, fallback, shape.opacity)


def _contains(box: SceneBox, x: float, y: float) -> bool:
    return box.x <= x <= box.x + box.w and box.y <= y <= box.y + box.h


def _dedupe(diagnostics: Iterable[DrawingDiagnostic]) -> list[DrawingDiagnostic]:
    seen: set[tuple[object, ...]] = set()
    result: list[DrawingDiagnostic] = []
    for item in diagnostics:
        key = (item.level, item.code, item.message, item.object_id, item.path, item.hint, item.related_ids)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
