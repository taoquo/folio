from __future__ import annotations

from dataclasses import dataclass
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
        x1 = start.x + start.w
        y1 = start.y + start.h // 2
        x2 = end.x
        y2 = end.y + end.h // 2
        stroke = BRAND if edge.kind == "primary" else OLIVE
        edge_fragments.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="1.4" />'
        )
        edge_fragments.append(_chevron(x2, y2, stroke))
        if edge.label:
            label_x = (x1 + x2) // 2
            edge_fragments.append(
                f'<rect x="{label_x - 24}" y="{y1 - 18}" width="48" height="12" rx="2" fill="{PARCHMENT}" />'
            )
            edge_fragments.append(
                f'<text x="{label_x}" y="{y1 - 9}" fill="{stroke}" font-size="8" '
                'font-family="\'JetBrains Mono\', monospace" text-anchor="middle">'
                f"{escape(edge.label)}</text>"
            )

    node_fragments = []
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
        f'{"".join(edge_fragments)}{"".join(node_fragments)}</svg>'
    )


def render_uml_class_svg(spec: UmlClassDiagramSpec) -> str:
    fragments = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {spec.width} {spec.height}">',
        f'<rect width="{spec.width}" height="{spec.height}" fill="{PARCHMENT}" />',
        f'<text x="{spec.width // 2}" y="40" fill="{NEAR_BLACK}" font-size="24" '
        'font-family="Charter, Georgia, serif" text-anchor="middle">'
        f"{escape(spec.title)}</text>",
    ]
    x = 80
    y = 100
    for item in spec.types:
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
        x += 280
        if x + 220 > spec.width:
            x = 80
            y += 220
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

    x = 60
    boxes = {}
    for node in spec.nodes:
        boxes[node.id] = Box(x, 220, 160, 64)
        x += 200
    return boxes


def _node_stroke(kind: str) -> str:
    return {
        "external": STONE,
        "service": NEAR_BLACK,
        "store": OLIVE,
        "cloud": BORDER,
    }.get(kind, NEAR_BLACK)


def _chevron(x: int, y: int, stroke: str) -> str:
    d = f"M {x - 8} {y - 4} L {x} {y} L {x - 8} {y + 4}"
    return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="1.4" stroke-linecap="round" />'
