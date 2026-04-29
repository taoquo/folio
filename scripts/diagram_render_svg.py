from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

from diagram_models import ArchitectureDiagramSpec, DiagramSpec, UmlClassDiagramSpec


PARCHMENT = "#F6F0EA"
IVORY = "#FBF7F3"
NEAR_BLACK = "#191514"
OLIVE = "#5A4A43"
STONE = "#85776F"
BRAND = "#B83D2E"
BRAND_TINT = "#F7E6E1"
BORDER = "#E9DED4"


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


def render_diagram_svg(spec: DiagramSpec) -> str:
    if getattr(spec, "kind", None) == "architecture":
        return render_architecture_svg(spec)
    if getattr(spec, "kind", None) == "uml-class":
        return render_uml_class_svg(spec)
    raise TypeError(f"unsupported spec type: {type(spec)!r}")


def render_architecture_svg(spec: ArchitectureDiagramSpec) -> str:
    boxes = _architecture_boxes(spec)
    edge_fragments = []
    for edge in spec.edges:
        start = boxes[edge.source]
        end = boxes[edge.target]
        points = _route_architecture_edge(start, end)
        (x1, y1), (x2, y2) = points[0], points[-1]
        stroke = BRAND if edge.kind == "primary" else OLIVE
        edge_fragments.append(
            f'<path d="{_path_from_points(points)}" fill="none" stroke="{stroke}" stroke-width="1.4" />'
        )
        edge_fragments.append(_chevron_for_segment(points[-2], points[-1], stroke))
        if edge.label:
            label_x, label_y = _label_point(points)
            edge_fragments.append(
                f'<rect x="{label_x - 24}" y="{label_y - 18}" width="48" height="12" rx="2" fill="{PARCHMENT}" />'
            )
            edge_fragments.append(
                f'<text x="{label_x}" y="{label_y - 9}" fill="{stroke}" font-size="8" '
                'font-family="\'JetBrains Mono\', monospace" text-anchor="middle">'
                f"{escape(edge.label)}</text>"
            )

    node_fragments = []
    layer_fragments = []
    if spec.layout == "horizontal-layers" and spec.layers:
        rows = _architecture_layer_rows(spec, boxes)
        for layer, (top, bottom) in rows:
            center_y = (top + bottom) // 2
            layer_fragments.append(
                f'<text x="32" y="{center_y}" fill="{STONE}" font-size="11" '
                'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.08em">'
                f"{escape(layer.label.upper())}</text>"
            )
            layer_fragments.append(
                f'<line x1="70" y1="{bottom + 18}" x2="{spec.width - 40}" y2="{bottom + 18}" stroke="{BORDER}" stroke-width="1" />'
            )

    for node in spec.nodes:
        box = boxes[node.id]
        is_focus = node.id == spec.focus
        fill = BRAND_TINT if is_focus else IVORY
        stroke = BRAND if is_focus else _node_stroke(node.kind)
        kind_fill = BRAND if is_focus else STONE
        node_fragments.append(
            f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1" />'
        )
        node_fragments.append(
            f'<text x="{box.x + 18}" y="{box.y + 18}" fill="{kind_fill}" font-size="7" '
            'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.15em">'
            f"{escape(node.kind.upper())}</text>"
        )
        node_fragments.append(
            f'<text x="{box.x + box.w // 2}" y="{box.y + 38}" fill="{NEAR_BLACK}" font-size="12" '
            'font-family="Charter, Georgia, serif" font-weight="600" text-anchor="middle">'
            f"{escape(node.label)}</text>"
        )
        if node.sublabel:
            node_fragments.append(
                f'<text x="{box.x + box.w // 2}" y="{box.y + 54}" fill="{OLIVE}" font-size="9" '
                'font-family="\'JetBrains Mono\', monospace" text-anchor="middle">'
                f"{escape(node.sublabel)}</text>"
            )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width} {spec.height}">'
        f'<rect width="{spec.width}" height="{spec.height}" fill="{PARCHMENT}" />'
        f'<text x="{spec.width // 2}" y="40" fill="{NEAR_BLACK}" font-size="24" '
        'font-family="Charter, Georgia, serif" text-anchor="middle">'
        f"{escape(spec.title)}</text>"
        f'{"".join(layer_fragments)}{"".join(edge_fragments)}{"".join(node_fragments)}</svg>'
    )


def render_uml_class_svg(spec: UmlClassDiagramSpec) -> str:
    boxes = _uml_boxes(spec)
    source_side_counts: dict[tuple[str, str], int] = {}
    target_side_counts: dict[tuple[str, str], int] = {}
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width} {spec.height}">',
        f'<rect width="{spec.width}" height="{spec.height}" fill="{PARCHMENT}" />',
        f'<text x="{spec.width // 2}" y="40" fill="{NEAR_BLACK}" font-size="24" '
        'font-family="Charter, Georgia, serif" text-anchor="middle">'
        f"{escape(spec.title)}</text>",
    ]
    relation_fragments = []
    for relation in spec.relationships:
        source = boxes[relation.source]
        target = boxes[relation.target]
        source_side, target_side = _uml_sides(source, target)
        source_key = (relation.source, source_side)
        target_key = (relation.target, target_side)
        source_slot = source_side_counts.get(source_key, 0)
        target_slot = target_side_counts.get(target_key, 0)
        source_side_counts[source_key] = source_slot + 1
        target_side_counts[target_key] = target_slot + 1
        start, end = _uml_anchors(source, target, source_side, target_side, source_slot, target_slot)
        line_start, line_end = start, end
        if relation.kind in {"aggregation", "composition"}:
            diamond, line_start = _diamond_at_point(start, end, filled=relation.kind == "composition")
            relation_fragments.append(diamond)
        if relation.kind == "inheritance":
            triangle, line_end = _triangle_at_point(end, start)
            relation_fragments.append(triangle)

        relation_fragments.append(
            f'<path class="uml-edge" d="{_path_from_points([line_start, line_end])}" fill="none" stroke="{OLIVE}" stroke-width="1.2" />'
        )
        if relation.kind == "association":
            relation_fragments.append(_chevron_for_segment(line_start, line_end, OLIVE, klass="uml-edge-head"))
        if relation.label:
            label_x, label_y = _label_point([line_start, line_end])
            relation_fragments.append(
                f'<text x="{label_x}" y="{label_y - 8}" fill="{STONE}" font-size="9" font-family="\'JetBrains Mono\', monospace" text-anchor="middle">{escape(relation.label)}</text>'
            )
        if relation.source_multiplicity:
            relation_fragments.append(
                f'<text x="{line_start[0] - 10}" y="{line_start[1] - 6}" fill="{STONE}" font-size="9" font-family="\'JetBrains Mono\', monospace" text-anchor="end">{escape(relation.source_multiplicity)}</text>'
            )
        if relation.target_multiplicity:
            relation_fragments.append(
                f'<text x="{line_end[0] + 10}" y="{line_end[1] - 6}" fill="{STONE}" font-size="9" font-family="\'JetBrains Mono\', monospace">{escape(relation.target_multiplicity)}</text>'
            )

    fragments.extend(relation_fragments)

    for item in spec.types:
        x, y = boxes[item.id].x, boxes[item.id].y
        body_h = 62 + 18 * len(item.attributes) + 18 * len(item.methods)
        stroke = BRAND if item.id == spec.focus else NEAR_BLACK
        fragments.append(
            f'<rect x="{x}" y="{y}" width="220" height="{body_h}" rx="6" fill="{IVORY}" stroke="{stroke}" stroke-width="1" />'
        )
        fragments.append(
            f'<line x1="{x}" y1="{y + 34}" x2="{x + 220}" y2="{y + 34}" stroke="{BORDER}" stroke-width="1" />'
        )
        attr_divider_y = y + 52 + 18 * max(1, len(item.attributes))
        fragments.append(
            f'<line x1="{x}" y1="{attr_divider_y}" x2="{x + 220}" y2="{attr_divider_y}" stroke="{BORDER}" stroke-width="1" />'
        )
        fragments.append(
            f'<text x="{x + 110}" y="{y + 22}" fill="{NEAR_BLACK}" font-size="13" '
            'font-family="Charter, Georgia, serif" font-weight="600" text-anchor="middle">'
            f"{escape(item.name)}</text>"
        )
        attr_y = y + 52
        for attr in item.attributes:
            fragments.append(
                f'<text x="{x + 12}" y="{attr_y}" fill="{OLIVE}" font-size="10" '
                'font-family="\'JetBrains Mono\', monospace">'
                f"{escape(attr)}</text>"
            )
            attr_y += 18
        method_y = attr_divider_y + 18
        for method in item.methods:
            fragments.append(
                f'<text x="{x + 12}" y="{method_y}" fill="{NEAR_BLACK}" font-size="10" '
                'font-family="\'JetBrains Mono\', monospace">'
                f"{escape(method)}</text>"
            )
            method_y += 18
    fragments.append("</svg>")
    return "".join(fragments)


def _architecture_boxes(spec: ArchitectureDiagramSpec) -> dict[str, Box]:
    if spec.layout == "vertical-stack":
        y = 100
        boxes = {}
        for node in spec.nodes:
            boxes[node.id] = Box(320, y, 320, 64)
            y += 96
        return boxes

    if spec.layout == "hub-and-spoke":
        positions = [(380, 210), (120, 80), (640, 80), (120, 340), (640, 340)]
        boxes = {}
        for index, node in enumerate(spec.nodes):
            x, y = positions[min(index, len(positions) - 1)]
            boxes[node.id] = Box(x, y, 200, 64)
        return boxes

    rows = []
    layer_order = [layer.id for layer in spec.layers]
    if layer_order:
        for layer_id in layer_order:
            rows.append([node for node in spec.nodes if node.layer == layer_id])
        unlayered = [node for node in spec.nodes if node.layer not in layer_order]
        if unlayered:
            rows.append(unlayered)
    else:
        rows.append(list(spec.nodes))

    boxes = {}
    row_gap = 118
    start_y = 96
    for row_index, row_nodes in enumerate(rows):
        if not row_nodes:
            continue
        count = len(row_nodes)
        width = 160
        gap = 40
        total = count * width + (count - 1) * gap
        x = max(84, (spec.width - total) // 2)
        y = start_y + row_index * row_gap
        for node in row_nodes:
            boxes[node.id] = Box(x, y, width, 64)
            x += width + gap
    return boxes


def _route_architecture_edge(start: Box, end: Box) -> list[tuple[int, int]]:
    same_row = abs(start.y - end.y) < 8
    if same_row:
        if start.x <= end.x:
            return [
                (start.x + start.w, start.y + start.h // 2),
                (end.x, end.y + end.h // 2),
            ]
        return [
            (start.x, start.y + start.h // 2),
            (end.x + end.w, end.y + end.h // 2),
        ]

    downward = start.y < end.y
    start_point = (start.x + start.w // 2, start.y + start.h if downward else start.y)
    end_point = (end.x + end.w // 2, end.y if downward else end.y + end.h)
    mid_y = (start_point[1] + end_point[1]) // 2
    return [
        start_point,
        (start_point[0], mid_y),
        (end_point[0], mid_y),
        end_point,
    ]


def _architecture_layer_rows(spec: ArchitectureDiagramSpec, boxes: dict[str, Box]) -> list[tuple[object, tuple[int, int]]]:
    rows = []
    for layer in spec.layers:
        layer_boxes = [boxes[node.id] for node in spec.nodes if node.layer == layer.id and node.id in boxes]
        if not layer_boxes:
            continue
        top = min(box.y for box in layer_boxes)
        bottom = max(box.y + box.h for box in layer_boxes)
        rows.append((layer, (top, bottom)))
    return rows


def _uml_boxes(spec: UmlClassDiagramSpec) -> dict[str, Box]:
    boxes: dict[str, Box] = {}
    x = 80
    y = 100
    for item in spec.types:
        body_h = 62 + 18 * len(item.attributes) + 18 * len(item.methods)
        boxes[item.id] = Box(x, y, 220, body_h)
        x += 280
        if x + 220 > spec.width:
            x = 80
            y += 220
    return boxes


def _uml_sides(source: Box, target: Box) -> tuple[str, str]:
    if source.x + source.w <= target.x:
        return "right", "left"
    if target.x + target.w <= source.x:
        return "left", "right"
    if source.y < target.y:
        return "bottom", "top"
    return "top", "bottom"


def _uml_anchors(
    source: Box,
    target: Box,
    source_side: str,
    target_side: str,
    source_slot: int,
    target_slot: int,
) -> tuple[tuple[int, int], tuple[int, int]]:
    return (
        _box_anchor(source, source_side, source_slot),
        _box_anchor(target, target_side, target_slot),
    )


def _box_anchor(box: Box, side: str, slot: int) -> tuple[int, int]:
    slot_positions = [0.34, 0.66, 0.5]
    ratio = slot_positions[slot % len(slot_positions)]
    if side == "right":
        return (box.x + box.w, box.y + int(box.h * ratio))
    if side == "left":
        return (box.x, box.y + int(box.h * ratio))
    if side == "bottom":
        return (box.x + int(box.w * ratio), box.y + box.h)
    return (box.x + int(box.w * ratio), box.y)


def _path_from_points(points: list[tuple[int, int]]) -> str:
    return "M " + " L ".join(f"{x} {y}" for x, y in points)


def _label_point(points: list[tuple[int, int]]) -> tuple[int, int]:
    segments = list(zip(points, points[1:]))
    if not segments:
        return points[0]
    start, end = max(segments, key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]))
    return ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)


def _node_stroke(kind: str) -> str:
    return {
        "external": STONE,
        "service": NEAR_BLACK,
        "store": OLIVE,
        "cloud": BORDER,
    }.get(kind, NEAR_BLACK)


def _chevron_for_segment(start: tuple[int, int], end: tuple[int, int], stroke: str, klass: Optional[str] = None) -> str:
    x1, y1 = start
    x2, y2 = end
    if x2 > x1:
        d = f"M {x2 - 8} {y2 - 4} L {x2} {y2} L {x2 - 8} {y2 + 4}"
    elif x2 < x1:
        d = f"M {x2 + 8} {y2 - 4} L {x2} {y2} L {x2 + 8} {y2 + 4}"
    elif y2 > y1:
        d = f"M {x2 - 4} {y2 - 8} L {x2} {y2} L {x2 + 4} {y2 - 8}"
    else:
        d = f"M {x2 - 4} {y2 + 8} L {x2} {y2} L {x2 + 4} {y2 + 8}"
    class_attr = f' class="{klass}"' if klass else ""
    return f'<path{class_attr} d="{d}" fill="none" stroke="{stroke}" stroke-width="1.4" stroke-linecap="round" />'


def _diamond_at_point(start: tuple[int, int], end: tuple[int, int], filled: bool) -> tuple[str, tuple[int, int]]:
    x1, y1 = start
    x2, y2 = end
    fill = OLIVE if filled else PARCHMENT
    if x2 > x1:
        points = [(x1, y1), (x1 + 8, y1 - 5), (x1 + 16, y1), (x1 + 8, y1 + 5)]
        line_start = (x1 + 16, y1)
    elif x2 < x1:
        points = [(x1, y1), (x1 - 8, y1 - 5), (x1 - 16, y1), (x1 - 8, y1 + 5)]
        line_start = (x1 - 16, y1)
    elif y2 > y1:
        points = [(x1, y1), (x1 - 5, y1 + 8), (x1, y1 + 16), (x1 + 5, y1 + 8)]
        line_start = (x1, y1 + 16)
    else:
        points = [(x1, y1), (x1 - 5, y1 - 8), (x1, y1 - 16), (x1 + 5, y1 - 8)]
        line_start = (x1, y1 - 16)
    polygon = " ".join(f"{x},{y}" for x, y in points)
    return (
        f'<polygon class="uml-diamond" points="{polygon}" fill="{fill}" stroke="{OLIVE}" stroke-width="1.2" />',
        line_start,
    )


def _triangle_at_point(tip: tuple[int, int], toward: tuple[int, int]) -> tuple[str, tuple[int, int]]:
    x1, y1 = toward
    x2, y2 = tip
    if x2 > x1:
        points = [(x2, y2), (x2 - 12, y2 - 6), (x2 - 12, y2 + 6)]
        line_end = (x2 - 12, y2)
    elif x2 < x1:
        points = [(x2, y2), (x2 + 12, y2 - 6), (x2 + 12, y2 + 6)]
        line_end = (x2 + 12, y2)
    elif y2 > y1:
        points = [(x2, y2), (x2 - 6, y2 - 12), (x2 + 6, y2 - 12)]
        line_end = (x2, y2 - 12)
    else:
        points = [(x2, y2), (x2 - 6, y2 + 12), (x2 + 6, y2 + 12)]
        line_end = (x2, y2 + 12)
    polygon = " ".join(f"{x},{y}" for x, y in points)
    return (
        f'<polygon class="uml-triangle" points="{polygon}" fill="{PARCHMENT}" stroke="{OLIVE}" stroke-width="1.2" />',
        line_end,
    )
