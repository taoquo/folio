from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

from diagram_models import ArchitectureDiagramSpec, DiagramSpec, UmlClassDiagramSpec
from diagram_layout import LayoutBox, layout_diagram


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


def _as_box(box: LayoutBox) -> Box:
    return Box(box.x, box.y, box.w, box.h)


def render_diagram_svg(spec: DiagramSpec) -> str:
    if getattr(spec, "kind", None) == "architecture":
        return render_architecture_svg(spec)
    if getattr(spec, "kind", None) == "uml-class":
        return render_uml_class_svg(spec)
    raise TypeError(f"unsupported spec type: {type(spec)!r}")


def render_architecture_svg(spec: ArchitectureDiagramSpec) -> str:
    layout = layout_diagram(spec)
    boxes = {node_id: _as_box(box) for node_id, box in layout.boxes.items()}
    focus_pairs = {
        (spec.focus_path[index], spec.focus_path[index + 1])
        for index in range(len(spec.focus_path) - 1)
    }
    edge_fragments = []
    group_fragments = _architecture_group_fragments(spec, boxes)
    layout_edges = {(edge.source, edge.target): edge for edge in layout.edges}
    for edge in spec.edges:
        layout_edge = layout_edges.get((edge.source, edge.target))
        if layout_edge is None:
            continue
        points = layout_edge.points
        stroke, stroke_width = _edge_style(edge.kind, edge.priority, (edge.source, edge.target) in focus_pairs)
        classes = ["arch-edge", f"arch-edge--{edge.kind}"]
        if (edge.source, edge.target) in focus_pairs:
            classes.append("arch-edge--focus")
        dash = ' stroke-dasharray="5 4"' if edge.dashed or edge.kind == "async" else ""
        edge_fragments.append(
            f'<path class="{" ".join(classes)}" d="{_path_from_points(points)}" fill="none" '
            f'stroke="{stroke}" stroke-width="{stroke_width}"{dash} />'
        )
        edge_fragments.append(_chevron_for_segment(points[-2], points[-1], stroke, stroke_width=stroke_width))
    node_fragments = []
    layer_fragments = []
    legend_fragments = _architecture_legend_fragments(spec)
    if spec.layout == "horizontal-layers" and spec.layers:
        layer_rows = _architecture_layer_rows(spec, boxes)
        for index, (layer, (top, bottom)) in enumerate(layer_rows):
            center_y = (top + bottom) // 2
            layer_fragments.append(
                f'<text x="32" y="{center_y}" fill="{STONE}" font-size="11" '
                'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.08em">'
                f"{escape(layer.label.upper())}</text>"
            )
            if index < len(layer_rows) - 1:
                next_top = layer_rows[index + 1][1][0]
                line_y = (bottom + next_top) // 2
                layer_fragments.append(
                    f'<line x1="120" y1="{line_y}" x2="{spec.width - 56}" y2="{line_y}" stroke="{BORDER}" stroke-width="1" />'
                )

    for node in spec.nodes:
        box = boxes[node.id]
        is_focus = node.id == spec.focus
        fill = BRAND_TINT if is_focus else IVORY
        stroke = BRAND if is_focus else _node_stroke(node.kind)
        kind_fill = BRAND if is_focus else STONE
        node_fragments.append(
            f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width="1" />'
        )
        node_fragments.append(
            f'<text x="{box.x + 18}" y="{box.y + 18}" fill="{kind_fill}" font-size="7" '
            'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.15em">'
            f"{escape(node.kind.upper())}</text>"
        )
        node_fragments.append(
            f'<text x="{box.x + box.w // 2}" y="{box.y + 38}" fill="{NEAR_BLACK}" font-size="12" '
            'font-family="Charter, Georgia, serif" font-weight="500" text-anchor="middle">'
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
        f'{"".join(layer_fragments)}{"".join(group_fragments)}{"".join(edge_fragments)}'
        f'{"".join(node_fragments)}{"".join(legend_fragments)}</svg>'
    )


def render_uml_class_svg(spec: UmlClassDiagramSpec) -> str:
    layout = layout_diagram(spec)
    boxes = {node_id: _as_box(box) for node_id, box in layout.boxes.items()}
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width} {spec.height}">',
        f'<rect width="{spec.width}" height="{spec.height}" fill="{PARCHMENT}" />',
        f'<text x="{spec.width // 2}" y="40" fill="{NEAR_BLACK}" font-size="24" '
        'font-family="Charter, Georgia, serif" text-anchor="middle">'
        f"{escape(spec.title)}</text>",
    ]
    relation_fragments = []
    layout_edges = {(edge.source, edge.target): edge for edge in layout.edges}
    for relation in spec.relationships:
        layout_edge = layout_edges.get((relation.source, relation.target))
        if layout_edge is None:
            continue
        path_points = layout_edge.points
        start, end = path_points[0], path_points[-1]
        line_start, line_end = start, end
        if relation.kind in {"aggregation", "composition"}:
            diamond, line_start = _diamond_at_point(start, end, filled=relation.kind == "composition")
            relation_fragments.append(diamond)
        if relation.kind == "inheritance":
            triangle, line_end = _triangle_at_point(end, start)
            relation_fragments.append(triangle)
        if line_start != start or line_end != end:
            path_points = [line_start, *path_points[1:-1], line_end]
        relation_fragments.append(
            f'<path class="uml-edge" d="{_path_from_points(path_points)}" fill="none" stroke="{OLIVE}" stroke-width="1.2" />'
        )
        if relation.kind == "association":
            relation_fragments.append(_chevron_for_segment(path_points[-2], path_points[-1], OLIVE, klass="uml-edge-head"))
        if relation.label:
            label_x, label_y = _layout_label_point(layout_edge.label_box, path_points)
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
        box = boxes[item.id]
        x, y = box.x, box.y
        body_h = box.h
        width = box.w
        scale = width / 220
        header_h = int(34 * scale)
        row_h = max(12, int(18 * scale))
        stroke = BRAND if item.id == spec.focus else NEAR_BLACK
        fragments.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{body_h}" rx="5" fill="{IVORY}" stroke="{stroke}" stroke-width="1" />'
        )
        fragments.append(
            f'<line x1="{x}" y1="{y + header_h}" x2="{x + width}" y2="{y + header_h}" stroke="{BORDER}" stroke-width="1" />'
        )
        attr_divider_y = y + header_h + row_h + row_h * max(1, len(item.attributes))
        fragments.append(
            f'<line x1="{x}" y1="{attr_divider_y}" x2="{x + width}" y2="{attr_divider_y}" stroke="{BORDER}" stroke-width="1" />'
        )
        fragments.append(
            f'<text x="{x + width // 2}" y="{y + max(16, int(22 * scale))}" fill="{NEAR_BLACK}" font-size="{max(10, int(13 * scale))}" '
            'font-family="Charter, Georgia, serif" font-weight="500" text-anchor="middle">'
            f"{escape(item.name)}</text>"
        )
        attr_y = y + header_h + row_h
        for attr in item.attributes:
            fragments.append(
                f'<text x="{x + max(8, int(12 * scale))}" y="{attr_y}" fill="{OLIVE}" font-size="{max(8, int(10 * scale))}" '
                'font-family="\'JetBrains Mono\', monospace">'
                f"{escape(attr)}</text>"
            )
            attr_y += row_h
        method_y = attr_divider_y + row_h
        for method in item.methods:
            fragments.append(
                f'<text x="{x + max(8, int(12 * scale))}" y="{method_y}" fill="{NEAR_BLACK}" font-size="{max(8, int(10 * scale))}" '
                'font-family="\'JetBrains Mono\', monospace">'
                f"{escape(method)}</text>"
            )
            method_y += row_h
    fragments.append("</svg>")
    return "".join(fragments)


def _layout_label_point(label_box: LayoutBox | None, points: list[tuple[int, int]]) -> tuple[int, int]:
    if label_box:
        return (label_box.x + label_box.w // 2, label_box.y + label_box.h)
    return _label_point(points)


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


def _architecture_group_fragments(spec: ArchitectureDiagramSpec, boxes: dict[str, Box]) -> list[str]:
    fragments = []
    for group in spec.groups:
        group_boxes = [boxes[member] for member in group.members if member in boxes]
        if len(group_boxes) < 2:
            continue
        left = min(box.x for box in group_boxes) - 18
        top = min(box.y for box in group_boxes) - 24
        right = max(box.x + box.w for box in group_boxes) + 18
        bottom = max(box.y + box.h for box in group_boxes) + 18
        width = right - left
        height = bottom - top
        fragments.append(
            f'<rect class="arch-group" x="{left}" y="{top}" width="{width}" height="{height}" rx="10" '
            f'fill="{IVORY}" fill-opacity="0.28" stroke="{BORDER}" stroke-width="1" stroke-dasharray="5 4" />'
        )
        fragments.append(
            f'<text x="{left + 14}" y="{top + 16}" fill="{STONE}" font-size="8" '
            'font-family="\'JetBrains Mono\', monospace" letter-spacing="0.12em">'
            f"{escape(group.label.upper())}</text>"
        )
    return fragments


def _architecture_legend_metrics(spec: ArchitectureDiagramSpec) -> dict[str, object] | None:
    if not spec.legend:
        return None
    title_width = 64
    item_gap = 28
    items = []
    total_width = 14 + title_width + 18
    for item in spec.legend:
        item_width = 20 + 8 + len(item.label) * 7
        items.append({"flow": item.flow, "label": item.label, "width": item_width})
        total_width += item_width
    total_width += item_gap * max(0, len(items) - 1) + 14
    width = max(260, total_width)
    height = 42
    x = (spec.width - width) // 2
    y = spec.height - 58
    cursor_x = x + 14 + title_width + 6
    baseline_y = y + 25
    laid_out = []
    for index, item in enumerate(items):
        if index:
            cursor_x += item_gap
        laid_out.append(
            {
                "flow": item["flow"],
                "label": item["label"],
                "x": cursor_x,
                "text_x": cursor_x + 28,
                "y": baseline_y,
            }
        )
        cursor_x += item["width"]
    return {"x": x, "y": y, "width": width, "height": height, "items": laid_out}


def _architecture_legend_fragments(spec: ArchitectureDiagramSpec) -> list[str]:
    metrics = _architecture_legend_metrics(spec)
    if metrics is None:
        return []
    fragments = [
        f'<rect class="arch-legend" x="{metrics["x"]}" y="{metrics["y"]}" width="{metrics["width"]}" height="{metrics["height"]}" rx="4" fill="{PARCHMENT}" stroke="{BORDER}" stroke-width="1" />',
        f'<text x="{metrics["x"] + 14}" y="{metrics["y"] + 16}" fill="{STONE}" font-size="8" font-family="\'JetBrains Mono\', monospace" letter-spacing="0.12em">LEGEND</text>',
    ]
    for item in metrics["items"]:
        sample_color = _legend_flow_color(item["flow"])
        row_y = item["y"]
        fragments.append(
            f'<line x1="{item["x"]}" y1="{row_y}" x2="{item["x"] + 20}" y2="{row_y}" stroke="{sample_color}" stroke-width="1.4" stroke-linecap="round" />'
        )
        fragments.append(_chevron_for_segment((item["x"], row_y), (item["x"] + 20, row_y), sample_color, stroke_width=1.4))
        fragments.append(
            f'<text x="{item["text_x"]}" y="{row_y + 3}" fill="{NEAR_BLACK}" font-size="9" '
            'font-family="\'JetBrains Mono\', monospace">'
            f"{escape(item['label'])}</text>"
        )
    return fragments


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


def _edge_style(kind: str, priority: str | None, is_focus: bool) -> tuple[str, float]:
    if is_focus:
        return BRAND, 1.8
    if kind == "primary" or priority == "primary":
        return BRAND, 1.4
    if priority == "background":
        return STONE, 1.0
    return OLIVE, 1.2


def _legend_flow_color(flow: str) -> str:
    return {
        "control": BRAND,
        "query": NEAR_BLACK,
        "write": OLIVE,
        "read": STONE,
        "stream": OLIVE,
        "event": STONE,
    }.get(flow, OLIVE)


def _chevron_for_segment(
    start: tuple[int, int],
    end: tuple[int, int],
    stroke: str,
    klass: Optional[str] = None,
    stroke_width: float = 1.4,
) -> str:
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
    return f'<path{class_attr} d="{d}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" stroke-linecap="round" />'


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
