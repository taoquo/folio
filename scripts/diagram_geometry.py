from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


SVG_NS = "{http://www.w3.org/2000/svg}"


@dataclass(frozen=True)
class SvgBox:
    x: float
    y: float
    w: float
    h: float


def validate_diagram_html(path: Path) -> list[str]:
    issues: list[str] = []
    html = path.read_text(encoding="utf-8")
    if "marker-end" in html or "<marker" in html:
        issues.append("SVG marker arrows are not allowed; use manual chevrons")
    svg_match = re.search(r"<svg\b[\s\S]*?</svg>", html)
    if not svg_match:
        return issues
    try:
        svg = ElementTree.fromstring(svg_match.group(0))
    except ElementTree.ParseError as exc:
        return issues

    width, height = _svg_size(svg)
    for index, rect in enumerate(svg.iter(f"{SVG_NS}rect")):
        box = _rect_box(rect)
        if box is None or box.w <= 0 or box.h <= 0:
            continue
        if box.w >= width and box.h >= height:
            continue
        if not _inside(box, width, height):
            issues.append(f"{path.name}: {rect.get('class') or 'rect'} outside svg bounds")

    for index, text in enumerate(svg.iter(f"{SVG_NS}text")):
        if text.get("transform"):
            continue
        box = _text_box(text)
        if box is None:
            continue
        if not _inside(box, width, height):
            issues.append(f"{path.name}: text outside svg bounds: {text.text or index}")
    return issues


def _svg_size(svg: ElementTree.Element) -> tuple[float, float]:
    view_box = svg.get("viewBox")
    if view_box:
        parts = [float(part) for part in view_box.split()]
        if len(parts) == 4:
            return parts[2], parts[3]
    width = float(re.sub(r"[^0-9.]", "", svg.get("width", "960")) or 960)
    height = float(re.sub(r"[^0-9.]", "", svg.get("height", "540")) or 540)
    return width, height


def _rect_box(rect: ElementTree.Element) -> SvgBox | None:
    try:
        return SvgBox(
            float(rect.get("x", "0")),
            float(rect.get("y", "0")),
            float(rect.get("width", "0")),
            float(rect.get("height", "0")),
        )
    except ValueError:
        return None


def _text_box(text: ElementTree.Element) -> SvgBox | None:
    content = "".join(text.itertext()).strip()
    if not content:
        return None
    try:
        x = float(text.get("x", "0"))
        y = float(text.get("y", "0"))
        font_size = float(text.get("font-size", "10"))
    except ValueError:
        return None
    width = max(8, len(content) * font_size * 0.58)
    anchor = text.get("text-anchor")
    if anchor == "middle":
        x -= width / 2
    elif anchor == "end":
        x -= width
    return SvgBox(x, y - font_size, width, font_size * 1.25)


def _inside(box: SvgBox, width: float, height: float) -> bool:
    return box.x >= -1 and box.y >= -1 and box.x + box.w <= width + 1 and box.y + box.h <= height + 1
