from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape

from diagram_models import ArchitectureDiagramSpec, DiagramSpec, UmlClassDiagramSpec
from diagram_layout import LayoutBox, layout_diagram
from drawing.pipeline import compile_architecture
from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.theme.folio import DEFAULT_FOLIO_THEME
from renderers.svg import render_svg
from drawing.flowchart import compile_flowchart_payload


PARCHMENT = DEFAULT_FOLIO_THEME.parchment
IVORY = DEFAULT_FOLIO_THEME.ivory
NEAR_BLACK = DEFAULT_FOLIO_THEME.near_black
OLIVE = DEFAULT_FOLIO_THEME.olive
STONE = DEFAULT_FOLIO_THEME.stone
BRAND = DEFAULT_FOLIO_THEME.brand
BRAND_TINT = DEFAULT_FOLIO_THEME.brand_tint
BORDER = DEFAULT_FOLIO_THEME.border


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
    result = DEFAULT_COMPILER_REGISTRY.compile_architecture_spec(spec)
    return render_svg(result.scene, result.profile)


def render_flowchart_svg(payload: dict[str, object]) -> str:
    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    return render_svg(result.scene, result.profile)


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


def _path_from_points(points: list[tuple[int, int]]) -> str:
    return "M " + " L ".join(f"{x} {y}" for x, y in points)


def _label_point(points: list[tuple[int, int]]) -> tuple[int, int]:
    segments = list(zip(points, points[1:]))
    if not segments:
        return points[0]
    start, end = max(segments, key=lambda pair: abs(pair[0][0] - pair[1][0]) + abs(pair[0][1] - pair[1][1]))
    return ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)


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
