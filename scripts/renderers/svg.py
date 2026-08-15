from __future__ import annotations

from hashlib import sha256
import json
import re
from xml.sax.saxutils import escape

from drawing.scene import (
    ArrowGeometry,
    ResolvedScene,
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
from drawing.output import scene_viewport, svg_root_attributes, variant_defs


def _attribute(value: str) -> str:
    return escape(value, {'"': "&quot;", "'": "&apos;"})


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _style(style: SceneStyle) -> str:
    parts = [f'fill="{style.fill}"', f'stroke="{style.stroke}"', f'stroke-width="{_number(style.stroke_width)}"']
    if style.dash:
        parts.append(f'stroke-dasharray="{" ".join(_number(item) for item in style.dash)}"')
    if style.fill_opacity is not None:
        parts.append(f'fill-opacity="{style.fill_opacity}"')
    return " ".join(parts)


def _text(item: SceneText) -> str:
    attrs = [f'x="{item.x}"', f'y="{item.y}"', f'fill="{item.fill}"', f'font-size="{_number(item.size)}"', f'font-family="{item.family}"']
    if item.anchor != "start":
        attrs.append(f'text-anchor="{item.anchor}"')
    if item.tracking:
        attrs.append(f'letter-spacing="{item.tracking}em"')
    if item.weight:
        attrs.append(f'font-weight="{item.weight}"')
    if item.klass:
        attrs.append(f'class="{item.klass}"')
    return f'<text {" ".join(attrs)}>{escape(item.text)}</text>'


def _polyline_path(points: tuple[tuple[int, int], ...]) -> str:
    return "M " + " L ".join(f"{x} {y}" for x, y in points)


def _rounded_path(
    points: tuple[tuple[int, int], ...],
    radius: int,
    bridges: tuple[tuple[int, int], ...] = (),
) -> str:
    if len(points) < 3 and not bridges:
        return _polyline_path(points)
    commands = [f"M {points[0][0]} {points[0][1]}"]
    current = points[0]
    for index in range(1, len(points)):
        corner = points[index]
        is_corner = index < len(points) - 1
        target = corner
        if is_corner:
            incoming = max(1, abs(corner[0] - current[0]) + abs(corner[1] - current[1]))
            used = min(radius, incoming // 2)
            if corner[0] == current[0]:
                target = (corner[0], corner[1] - used if corner[1] > current[1] else corner[1] + used)
            else:
                target = (corner[0] - used if corner[0] > current[0] else corner[0] + used, corner[1])
        _append_segment(commands, current, target, bridges)
        if is_corner:
            after = points[index + 1]
            outgoing = max(1, abs(after[0] - corner[0]) + abs(after[1] - corner[1]))
            used = min(radius, outgoing // 2)
            if after[0] == corner[0]:
                exit_point = (corner[0], corner[1] + used if after[1] > corner[1] else corner[1] - used)
            else:
                exit_point = (corner[0] + used if after[0] > corner[0] else corner[0] - used, corner[1])
            commands.append(f"Q {corner[0]} {corner[1]} {exit_point[0]} {exit_point[1]}")
            current = exit_point
        else:
            current = target
    return " ".join(commands)


def _append_segment(
    commands: list[str],
    start: tuple[int, int],
    end: tuple[int, int],
    bridges: tuple[tuple[int, int], ...],
) -> None:
    horizontal = start[1] == end[1]
    candidates = [point for point in bridges if (point[1] == start[1] if horizontal else point[0] == start[0])]
    low, high = sorted((start[0], end[0]) if horizontal else (start[1], end[1]))
    candidates = [point for point in candidates if low + 8 < (point[0] if horizontal else point[1]) < high - 8]
    candidates.sort(key=lambda point: point[0] if horizontal else point[1], reverse=(end[0] < start[0] if horizontal else end[1] < start[1]))
    direction = 1 if (end[0] > start[0] if horizontal else end[1] > start[1]) else -1
    for x, y in candidates:
        if horizontal:
            commands.append(f"L {x - 7 * direction} {y}")
            commands.append(f"C {x - 4 * direction} {y - 8} {x + 4 * direction} {y - 8} {x + 7 * direction} {y}")
        else:
            commands.append(f"L {x} {y - 7 * direction}")
            commands.append(f"C {x + 8} {y - 4 * direction} {x + 8} {y + 4 * direction} {x} {y + 7 * direction}")
    commands.append(f"L {end[0]} {end[1]}")


def _arrow(arrow: ArrowGeometry, stroke: str, width: float, klass: str | None = None) -> str:
    class_attr = f' class="{klass}"' if klass else ""
    return f'<path{class_attr} d="{_polyline_path(arrow.points)}" fill="none" stroke="{stroke}" stroke-width="{_number(width)}" stroke-linecap="round" />'


def _class_attr(value: str | None) -> str:
    return f' class="{_attribute(value)}"' if value else ""


def _reading_attr(item_id: str, reading_order: dict[str, int]) -> str:
    if item_id not in reading_order:
        return ""
    return f' role="listitem" data-reading-order="{reading_order[item_id]}"'


def _safe_namespace(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    if not normalized:
        raise ValueError("SVG namespace must contain at least one safe character")
    if not normalized[0].isalpha():
        normalized = "folio-" + normalized
    return normalized


def _scene_namespace(scene: ResolvedScene) -> str:
    payload = json.dumps(scene.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "folio-" + sha256(payload.encode("utf-8")).hexdigest()[:12]


def _dom_id(namespace: str, item_id: str) -> str:
    return f"{namespace}--{item_id}"


def _id_attrs(namespace: str, item_id: str) -> str:
    return f'id="{_attribute(_dom_id(namespace, item_id))}" data-folio-id="{_attribute(item_id)}"'


def _primitive(item: object, reading_order: dict[str, int], namespace: str) -> str:
    if isinstance(item, SceneRect):
        return (
            f'<rect {_id_attrs(namespace, item.id)}{_class_attr(item.klass)}{_reading_attr(item.id, reading_order)} x="{item.box.x}" y="{item.box.y}" '
            f'width="{item.box.w}" height="{item.box.h}" rx="{item.style.radius}" {_style(item.style)} />'
        )
    if isinstance(item, SceneLine):
        return (
            f'<line {_id_attrs(namespace, item.id)}{_class_attr(item.klass)}{_reading_attr(item.id, reading_order)} x1="{item.start[0]}" y1="{item.start[1]}" '
            f'x2="{item.end[0]}" y2="{item.end[1]}" {_style(item.style)} />'
        )
    if isinstance(item, ScenePolyline):
        points = " ".join(f"{x},{y}" for x, y in item.points)
        return f'<polyline {_id_attrs(namespace, item.id)}{_class_attr(item.klass)}{_reading_attr(item.id, reading_order)} points="{points}" {_style(item.style)} />'
    if isinstance(item, ScenePath):
        return f'<path {_id_attrs(namespace, item.id)}{_class_attr(item.klass)}{_reading_attr(item.id, reading_order)} d="{_attribute(item.d)}" {_style(item.style)} />'
    if isinstance(item, SceneCircle):
        return (
            f'<circle {_id_attrs(namespace, item.id)}{_class_attr(item.klass)}{_reading_attr(item.id, reading_order)} cx="{item.cx}" cy="{item.cy}" '
            f'r="{item.r}" {_style(item.style)} />'
        )
    if isinstance(item, SceneText):
        return _text(item)
    if isinstance(item, SceneClip):
        return (
            f'<defs><clipPath {_id_attrs(namespace, item.id)}><rect x="{item.box.x}" y="{item.box.y}" '
            f'width="{item.box.w}" height="{item.box.h}" /></clipPath></defs>'
        )
    if isinstance(item, SceneGroup):
        clip = f' clip-path="url(#{_attribute(_dom_id(namespace, item.clip_id))})"' if item.clip_id else ""
        return f'<g {_id_attrs(namespace, item.id)}{_class_attr(item.klass)}{_reading_attr(item.id, reading_order)}{clip}>{"".join(_primitive(child, reading_order, namespace) for child in item.children)}</g>'
    raise TypeError(f"unsupported resolved scene primitive: {type(item).__name__}")


def render_svg(
    scene: ResolvedScene,
    profile: str = "artifact",
    *,
    namespace: str | None = None,
    variant: str = "plain",
) -> str:
    namespace = _safe_namespace(namespace or _scene_namespace(scene))
    title_id = _dom_id(namespace, "drawing-title")
    description_id = _dom_id(namespace, "drawing-description")
    reading_order = {node_id: index for index, node_id in enumerate(scene.reading_order)}
    view_x, view_y, view_width, view_height = scene_viewport(scene, profile)
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" {svg_root_attributes(profile, view_width, view_height)} viewBox="{view_x} {view_y} {view_width} {view_height}" role="img" aria-labelledby="{_attribute(title_id)} {_attribute(description_id)}" lang="{_attribute(scene.language)}" data-folio-namespace="{_attribute(namespace)}" data-folio-variant="{_attribute(variant)}">',
        f'<title id="{_attribute(title_id)}" data-folio-id="drawing-title">{escape(scene.title.text)}</title>',
        f'<desc id="{_attribute(description_id)}" data-folio-id="drawing-description">{escape(scene.description or scene.title.text)}</desc>',
        variant_defs(variant, namespace, len(scene.reading_order) + len(scene.nodes)),
        f'<rect data-folio-role="canvas" x="{view_x}" y="{view_y}" width="{view_width}" height="{view_height}" fill="{scene.background}" />',
        _text(scene.title),
    ]
    for region in scene.regions:
        if region.box and region.style:
            fragments.append(f'<rect class="arch-group" x="{region.box.x}" y="{region.box.y}" width="{region.box.w}" height="{region.box.h}" rx="{region.style.radius}" {_style(region.style)} />')
        fragments.append(_text(region.label))
        if region.separator and region.style:
            start, end = region.separator
            fragments.append(f'<line x1="{start[0]}" y1="{start[1]}" x2="{end[0]}" y2="{end[1]}" stroke="{region.style.stroke}" stroke-width="{_number(region.style.stroke_width)}" />')
    fragments.extend(_primitive(item, reading_order, namespace) for item in scene.primitives)
    for edge in scene.edges:
        fragments.append(f'<path {_id_attrs(namespace, edge.id)} class="{edge.klass}" d="{_rounded_path(edge.points, edge.corner_radius, edge.bridges)}" {_style(edge.style)} stroke-linecap="round" stroke-linejoin="round" />')
        fragments.append(_arrow(edge.arrow, edge.style.stroke, edge.style.stroke_width))
        if edge.label:
            fragments.append(_text(edge.label))
    for fallback_index, node in enumerate(scene.nodes, start=len(reading_order)):
        fragments.append(f'<g {_id_attrs(namespace, node.id)} data-reading-order="{reading_order.get(node.id, fallback_index)}">')
        if node.shape == "diamond":
            cx, cy = node.box.x + node.box.w // 2, node.box.y + node.box.h // 2
            fragments.append(f'<path d="M {cx} {node.box.y} L {node.box.x + node.box.w} {cy} L {cx} {node.box.y + node.box.h} L {node.box.x} {cy} Z" {_style(node.style)} />')
        elif node.shape == "data":
            offset = 12
            fragments.append(f'<path d="M {node.box.x + offset} {node.box.y} L {node.box.x + node.box.w} {node.box.y} L {node.box.x + node.box.w - offset} {node.box.y + node.box.h} L {node.box.x} {node.box.y + node.box.h} Z" {_style(node.style)} />')
        elif node.shape == "circle":
            radius = min(node.box.w, node.box.h) // 2
            fragments.append(f'<circle cx="{node.box.x + node.box.w // 2}" cy="{node.box.y + node.box.h // 2}" r="{radius}" fill="{node.style.fill}" stroke="{node.style.stroke}" stroke-width="{_number(node.style.stroke_width)}" />')
        elif node.shape == "double-circle":
            radius = min(node.box.w, node.box.h) // 2
            fragments.append(f'<circle cx="{node.box.x + node.box.w // 2}" cy="{node.box.y + node.box.h // 2}" r="{radius}" fill="none" stroke="{node.style.stroke}" stroke-width="{_number(node.style.stroke_width)}" />')
            fragments.append(f'<circle cx="{node.box.x + node.box.w // 2}" cy="{node.box.y + node.box.h // 2}" r="{max(2, radius - 4)}" fill="{node.style.fill}" stroke="none" />')
        else:
            radius = node.box.h // 2 if node.shape == "pill" else node.style.radius
            fragments.append(f'<rect x="{node.box.x}" y="{node.box.y}" width="{node.box.w}" height="{node.box.h}" rx="{radius}" {_style(node.style)} />')
        fragments.extend(_text(item) for item in node.text_runs)
        if node.pictogram:
            fragments.append('<g aria-hidden="true">')
            fragments.extend(f'<path d="{path}" fill="none" stroke="{node.pictogram.stroke}" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" />' for path in node.pictogram.paths)
            fragments.append('</g>')
        fragments.append('</g>')
    if scene.legend:
        legend = scene.legend
        fragments.append(f'<rect class="arch-legend" x="{legend.box.x}" y="{legend.box.y}" width="{legend.box.w}" height="{legend.box.h}" rx="{legend.style.radius}" {_style(legend.style)} />')
        fragments.append(_text(legend.title))
        for item in legend.items:
            start, end = item.line
            fragments.append(f'<line x1="{start[0]}" y1="{start[1]}" x2="{end[0]}" y2="{end[1]}" stroke="{item.stroke}" stroke-width="1.4" stroke-linecap="round" />')
            fragments.append(_arrow(item.arrow, item.stroke, 1.4))
            fragments.append(_text(item.label))
    for item in scene.annotations:
        fragments.append(f'<g {_id_attrs(namespace, item.id)}{_reading_attr(item.id, reading_order)}>')
        if item.leader:
            fragments.append(f'<path d="{_rounded_path(item.leader, 4)}" fill="none" stroke="{item.style.stroke}" stroke-width="1" />')
        fragments.append(f'<rect x="{item.box.x}" y="{item.box.y}" width="{item.box.w}" height="{item.box.h}" rx="{item.style.radius}" {_style(item.style)} />')
        fragments.append(_text(item.text))
        fragments.append("</g>")
    fragments.append("</svg>")
    return "".join(fragments)
