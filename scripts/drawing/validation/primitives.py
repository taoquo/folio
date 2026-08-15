from __future__ import annotations

from collections import Counter
from math import atan2, cos, isfinite, pi, radians, sin, sqrt
import re

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
    SceneText,
)
from .models import DrawingDiagnostic


PATH_DATA_RE = re.compile(r"^[MmZzLlHhVvCcSsQqTtAa0-9eE+.,\-\s]+$")
PATH_TOKEN_RE = re.compile(r"[A-Za-z]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def _inside(box: SceneBox, width: int, height: int) -> bool:
    return box.x >= 0 and box.y >= 0 and box.w >= 0 and box.h >= 0 and box.x + box.w <= width and box.y + box.h <= height


def _finite(values: tuple[float | int, ...]) -> bool:
    return all(isfinite(float(value)) for value in values)


def _text_inside(item: SceneText, width: int, height: int) -> bool:
    return _finite((item.x, item.y, item.size)) and 0 <= item.x <= width and 0 <= item.y <= height and item.size > 0


def validate_scene_primitives(scene: ResolvedScene) -> list[DrawingDiagnostic]:
    diagnostics: list[DrawingDiagnostic] = []
    primitive_ids, clip_ids, clip_refs = _primitive_references(scene.primitives)
    svg_ids = [
        *(node.id for node in scene.nodes), *(item.id for item in scene.annotations),
        *primitive_ids, "drawing-title", "drawing-description",
    ]
    for item_id, count in Counter(svg_ids).items():
        if count > 1:
            diagnostics.append(DrawingDiagnostic("ERROR", "PV001", "duplicate SVG element id", item_id))
    for clip_ref in clip_refs:
        if clip_ref not in clip_ids:
            diagnostics.append(DrawingDiagnostic("ERROR", "PV002", "group references unknown clip", clip_ref))
    _validate_primitives(scene.primitives, scene.width, scene.height, diagnostics)
    return diagnostics


def _validate_primitives(
    primitives: tuple[object, ...],
    width: int,
    height: int,
    diagnostics: list[DrawingDiagnostic],
) -> None:
    for item in primitives:
        if isinstance(item, (SceneRect, SceneClip)):
            if not _inside(item.box, width, height):
                diagnostics.append(DrawingDiagnostic("ERROR", "PV100", "primitive box outside canvas", item.id))
        elif isinstance(item, SceneCircle):
            if not _finite((item.cx, item.cy, item.r)) or item.r <= 0 or item.cx - item.r < 0 or item.cy - item.r < 0 or item.cx + item.r > width or item.cy + item.r > height:
                diagnostics.append(DrawingDiagnostic("ERROR", "PV101", "circle outside canvas or invalid", item.id))
        elif isinstance(item, SceneLine):
            if any(not _finite((x, y)) or not (0 <= x <= width and 0 <= y <= height) for x, y in (item.start, item.end)):
                diagnostics.append(DrawingDiagnostic("ERROR", "PV102", "line outside canvas", item.id))
        elif isinstance(item, ScenePolyline):
            if len(item.points) < 2 or any(not _finite((x, y)) or not (0 <= x <= width and 0 <= y <= height) for x, y in item.points):
                diagnostics.append(DrawingDiagnostic("ERROR", "PV103", "polyline outside canvas or incomplete", item.id))
        elif isinstance(item, ScenePath):
            path_data = item.d.strip()
            if not path_data or not path_data[0].isalpha() or not PATH_DATA_RE.fullmatch(path_data):
                diagnostics.append(DrawingDiagnostic("ERROR", "PV104", "path data is empty or invalid", item.id))
            else:
                try:
                    points = path_geometry_points(path_data)
                except ValueError:
                    diagnostics.append(DrawingDiagnostic("ERROR", "PV104", "path command structure is invalid", item.id))
                else:
                    if any(not _finite(point) or not (0 <= point[0] <= width and 0 <= point[1] <= height) for point in points):
                        diagnostics.append(DrawingDiagnostic("ERROR", "PV107", "path geometry outside canvas", item.id))
        elif isinstance(item, SceneText):
            if not _text_inside(item, width, height):
                diagnostics.append(DrawingDiagnostic("ERROR", "PV105", "primitive text outside canvas", item.text))
        elif isinstance(item, SceneGroup):
            _validate_primitives(item.children, width, height, diagnostics)
        else:
            diagnostics.append(DrawingDiagnostic("ERROR", "PV106", "unknown resolved primitive", type(item).__name__))


def path_geometry_points(path_data: str) -> tuple[tuple[float, float], ...]:
    tokens = PATH_TOKEN_RE.findall(path_data.replace(",", " "))
    command = ""
    index = 0
    current = (0.0, 0.0)
    subpath = current
    points: list[tuple[float, float]] = []
    counts = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}
    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
            if command.upper() == "Z":
                current = subpath
                points.append(current)
                continue
        if not command or command.upper() not in counts:
            raise ValueError("unsupported or missing path command")
        count = counts[command.upper()]
        if index + count > len(tokens) or any(value.isalpha() for value in tokens[index:index + count]):
            raise ValueError("incomplete path command")
        values = [float(value) for value in tokens[index:index + count]]
        index += count
        relative = command.islower()

        def point(x: float, y: float) -> tuple[float, float]:
            return (x + current[0], y + current[1]) if relative else (x, y)

        kind = command.upper()
        if kind in {"M", "L", "T"}:
            current = point(values[0], values[1])
            points.append(current)
            if kind == "M":
                subpath = current
                command = "l" if relative else "L"
        elif kind == "H":
            current = (values[0] + current[0] if relative else values[0], current[1])
            points.append(current)
        elif kind == "V":
            current = (current[0], values[0] + current[1] if relative else values[0])
            points.append(current)
        elif kind == "C":
            controls = (point(values[0], values[1]), point(values[2], values[3]), point(values[4], values[5]))
            points.extend(controls)
            current = controls[-1]
        elif kind in {"S", "Q"}:
            controls = (point(values[0], values[1]), point(values[2], values[3]))
            points.extend(controls)
            current = controls[-1]
        elif kind == "A":
            if values[3] not in {0.0, 1.0} or values[4] not in {0.0, 1.0}:
                raise ValueError("arc flags must be zero or one")
            end = point(values[5], values[6])
            arc_points = _arc_points(current, end, abs(values[0]), abs(values[1]), values[2], bool(values[3]), bool(values[4]))
            points.extend(arc_points)
            current = end
    return tuple(points)


def _arc_points(
    start: tuple[float, float],
    end: tuple[float, float],
    rx: float,
    ry: float,
    rotation: float,
    large_arc: bool,
    sweep: bool,
) -> tuple[tuple[float, float], ...]:
    if rx == 0 or ry == 0 or start == end:
        return (end,)
    phi = radians(rotation % 360)
    cos_phi, sin_phi = cos(phi), sin(phi)
    dx, dy = (start[0] - end[0]) / 2, (start[1] - end[1]) / 2
    x1 = cos_phi * dx + sin_phi * dy
    y1 = -sin_phi * dx + cos_phi * dy
    scale = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if scale > 1:
        factor = sqrt(scale)
        rx *= factor
        ry *= factor
    numerator = max(0.0, rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1)
    denominator = max(1e-12, rx * rx * y1 * y1 + ry * ry * x1 * x1)
    sign = -1 if large_arc == sweep else 1
    coefficient = sign * sqrt(numerator / denominator)
    cx1 = coefficient * (rx * y1 / ry)
    cy1 = coefficient * (-ry * x1 / rx)
    cx = cos_phi * cx1 - sin_phi * cy1 + (start[0] + end[0]) / 2
    cy = sin_phi * cx1 + cos_phi * cy1 + (start[1] + end[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        return atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    ux, uy = (x1 - cx1) / rx, (y1 - cy1) / ry
    vx, vy = (-x1 - cx1) / rx, (-y1 - cy1) / ry
    start_angle = angle(1, 0, ux, uy)
    delta = angle(ux, uy, vx, vy)
    if not sweep and delta > 0:
        delta -= 2 * pi
    elif sweep and delta < 0:
        delta += 2 * pi
    return tuple(
        (
            cx + cos_phi * rx * cos(start_angle + delta * step / 32) - sin_phi * ry * sin(start_angle + delta * step / 32),
            cy + sin_phi * rx * cos(start_angle + delta * step / 32) + cos_phi * ry * sin(start_angle + delta * step / 32),
        )
        for step in range(33)
    )


def _primitive_references(
    primitives: tuple[object, ...],
) -> tuple[list[str], set[str], list[str]]:
    ids: list[str] = []
    clips: set[str] = set()
    clip_refs: list[str] = []
    for item in primitives:
        item_id = getattr(item, "id", None)
        if isinstance(item_id, str):
            ids.append(item_id)
        if isinstance(item, SceneClip):
            clips.add(item.id)
        if isinstance(item, SceneGroup):
            if item.clip_id:
                clip_refs.append(item.clip_id)
            child_ids, child_clips, child_refs = _primitive_references(item.children)
            ids.extend(child_ids)
            clips.update(child_clips)
            clip_refs.extend(child_refs)
    return ids, clips, clip_refs
