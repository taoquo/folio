"""Render a Document IR to PPTX.

The slide decks were produced by a standalone script holding its own design
constants. That made them the one document type the IR could not express, and
therefore the one type that could not be compared, measured or migrated.

This writer closes that gap. It reads the same IR the HTML writer reads and
produces a deck, so slides join the rest of the document model rather than
sitting outside it.

Slide text is emitted as text frames. Geometry is derived from the slide size
and a small set of layout roles, because a deck's meaning is its sequence and
its emphasis, not its coordinates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The colour roles a deck paints with. The values come from the theme profile,
# so a deck and a page from the same document agree -- they did not before: this
# module kept a private palette whose ink and rule appeared nowhere else in the
# repository, and a deck came out in a different colour from its PDF.
PALETTE_ROLES = {
    "canvas": "color.surface.page",
    "ink": "color.text.primary",
    "muted": "color.text.muted",
    "accent": "color.accent.brand",
    "rule": "color.border.default",
}


def palette(theme: str | None = None) -> dict[str, str]:
    """The deck's colours, resolved from the theme.

    Hex without the leading `#`, which is what python-pptx takes.
    """
    import os
    import sys

    scripts = Path(__file__).resolve().parents[2]
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import style_resolver

    name = (theme or os.environ.get("FOLIO_THEME") or "").strip() or None
    style = style_resolver.resolve(names={"theme": name} if name else None)
    out: dict[str, str] = {}
    for key, role in PALETTE_ROLES.items():
        value = style.get(role)
        text = str(value).strip() if value is not None else ""
        out[key] = text.lstrip("#").upper() if text.startswith("#") else ""
    return out

SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5

MARGIN_IN = 0.9
CONTENT_TOP_IN = 1.9


class PptxWriterError(RuntimeError):
    """Raised when a document cannot be rendered as a deck."""


@dataclass(frozen=True, slots=True)
class Slide:
    """One slide's content, derived from the IR.

    Derived rather than stored: the IR states what the document says, and this
    groups it into slides the way a reader would.
    """

    index: int
    title: str = ""
    subtitle: str = ""
    bullets: tuple[str, ...] = ()
    body: str = ""
    eyebrow: str = ""
    kind: str = "content"


def _text_of(node: Any) -> str:
    """The plain text of a node's inline content.

    Inline content lives in `payload["content"]`, not on the node, so reading
    the attribute would return empty for every heading and paragraph.
    """
    if hasattr(node, "text"):
        try:
            text = node.text()
            if text:
                return str(text).strip()
        except Exception:
            pass

    payload = getattr(node, "payload", {}) or {}
    parts: list[str] = []
    for item in payload.get("content", ()) or ():
        value = getattr(item, "value", None)
        if value:
            parts.append(str(value))
            continue
        nested = getattr(item, "content", ()) or ()
        parts.append("".join(str(getattr(x, "value", "") or "") for x in nested))
    if not parts:
        # A node may carry its text directly, as a code block or table cell does.
        for key in ("value", "label", "alt", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
    return "".join(parts).strip()


def slides_from(document: Any) -> list[Slide]:
    """Group a document's blocks into slides.

    A level-1 heading opens a slide; everything until the next one belongs to
    it. That is the same rule a person applies when reading an outline, and it
    keeps the writer independent of any layout vocabulary.
    """
    slides: list[Slide] = []
    current_title = ""
    subtitle = ""
    eyebrow = ""
    bullets: list[str] = []
    body_parts: list[str] = []
    started = False

    def flush() -> None:
        nonlocal bullets, body_parts, subtitle, eyebrow, started
        if not started and not current_title:
            return
        slides.append(
            Slide(
                index=len(slides) + 1,
                title=current_title,
                subtitle=subtitle,
                bullets=tuple(bullets),
                body=" ".join(body_parts).strip(),
                eyebrow=eyebrow,
                kind="title" if len(slides) == 0 else "content",
            )
        )
        bullets = []
        body_parts = []
        subtitle = ""
        eyebrow = ""

    def visit(blocks: Sequence[Any]) -> None:
        nonlocal current_title, subtitle, eyebrow, started
        for node in blocks:
            node_type = getattr(node, "type", "")
            payload = getattr(node, "payload", {}) or {}

            if node_type == "section":
                visit(payload.get("blocks", ()) or ())
                continue

            if node_type == "heading":
                level = int(payload.get("level", 2))
                text = _text_of(node)
                if level == 1:
                    if started or current_title:
                        flush()
                    current_title = text
                    started = True
                else:
                    bullets.append(text)
                continue

            if node_type == "eyebrow":
                eyebrow = _text_of(node)
                continue

            if node_type == "subtitle":
                subtitle = _text_of(node)
                continue

            if node_type in {"paragraph", "callout", "quote"}:
                text = _text_of(node)
                if text:
                    body_parts.append(text)
                continue

            if node_type == "list":
                for item in payload.get("items", ()) or ():
                    text = _text_of(item)
                    if not text:
                        # A list item may hold its content in `content` rather
                        # than exposing text(), so read the payload directly.
                        text = "".join(
                            str(getattr(x, "value", "") or "")
                            for x in ((item.get("content", ()) if isinstance(item, dict)
                                       else getattr(item, "payload", {}).get("content", ())) or ())
                        ).strip()
                    if text:
                        bullets.append(text)
                continue

            if node_type == "table":
                # Columns and rows are model objects, not mappings, so they are
                # read by attribute. A `.get` here would raise on real input.
                def field_of(item: Any, name: str, default: Any = None) -> Any:
                    if isinstance(item, dict):
                        return item.get(name, default)
                    return getattr(item, name, default)

                headers = [
                    "".join(str(getattr(x, "value", "") or "") for x in (field_of(c, "label", ()) or ()))
                    for c in (payload.get("columns", ()) or ())
                ]
                if any(headers):
                    bullets.append(" · ".join(h for h in headers if h))

                for row in payload.get("rows", ()) or ():
                    cells = []
                    for cell in field_of(row, "cells", ()) or ():
                        cells.append("".join(str(getattr(x, "value", "") or "") for x in (cell or ())))
                    if any(cells):
                        bullets.append(" · ".join(cells))
                continue

            if node_type in {"figure", "diagram"}:
                alt = payload.get("alt")
                if alt:
                    bullets.append(str(alt))
                continue

            # Anything else contributes its text if it has any, so content is
            # not silently dropped from the deck.
            text = _text_of(node)
            if text:
                body_parts.append(text)

    # `walk()` is the reliable traversal: a section node records the boundary
    # rather than owning its children, so iterating `blocks` would see only the
    # section and stop there.
    visit(list(document.walk()))
    if started or current_title:
        flush()
    return slides


def _add_background(slide: Any, rgb: Any) -> None:
    from pptx.util import Inches

    shape = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(SLIDE_WIDTH_IN), Inches(SLIDE_HEIGHT_IN))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb
    shape.line.fill.background()
    shape.shadow.inherit = False
    # Send it behind everything else.
    slide.shapes._spTree.remove(shape._element)
    slide.shapes._spTree.insert(2, shape._element)


def _add_text(
    slide: Any,
    text: str,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    size: float,
    bold: bool = False,
    color: Any = None,
    align: Any = None,
    font_name: str = "Charter",
) -> None:
    from pptx.util import Inches, Pt

    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    frame.text = text
    for index, paragraph in enumerate(frame.paragraphs):
        if index == 0:
            paragraph.text = text
        if align is not None:
            paragraph.alignment = align
        for run in paragraph.runs:
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.name = font_name
            if color is not None:
                run.font.color.rgb = color


def write_pptx(document: Any, output: Path) -> Path:
    """Render a document to a deck."""
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.util import Inches, Pt
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise PptxWriterError(f"python-pptx is required: {exc}") from exc

    slides = slides_from(document)
    if not slides:
        raise PptxWriterError("document produced no slides")

    colours = palette()
    missing = [key for key, value in colours.items() if not value]
    if missing:
        raise PptxWriterError(f"theme did not supply: {', '.join(sorted(missing))}")
    canvas = RGBColor.from_string(colours["canvas"])
    ink = RGBColor.from_string(colours["ink"])
    muted = RGBColor.from_string(colours["muted"])
    accent = RGBColor.from_string(colours["accent"])

    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_WIDTH_IN)
    presentation.slide_height = Inches(SLIDE_HEIGHT_IN)
    blank = presentation.slide_layouts[6]

    for slide_model in slides:
        slide = presentation.slides.add_slide(blank)
        _add_background(slide, canvas)

        y = MARGIN_IN
        if slide_model.eyebrow:
            _add_text(slide, slide_model.eyebrow, left=MARGIN_IN, top=y, width=6.0, height=0.35,
                      size=12, color=accent)
            y += 0.45

        if slide_model.title:
            _add_text(slide, slide_model.title, left=MARGIN_IN, top=y, width=11.5, height=1.1,
                      size=30, bold=True, color=ink)
            y += 1.15

        if slide_model.subtitle:
            _add_text(slide, slide_model.subtitle, left=MARGIN_IN, top=y, width=11.5, height=0.6,
                      size=16, color=muted)
            y += 0.7

        body_top = max(y, CONTENT_TOP_IN)
        if slide_model.bullets:
            height = min(0.5 * len(slide_model.bullets), SLIDE_HEIGHT_IN - body_top - MARGIN_IN)
            box = slide.shapes.add_textbox(Inches(MARGIN_IN), Inches(body_top),
                                           Inches(11.5), Inches(max(height, 0.5)))
            frame = box.text_frame
            frame.word_wrap = True
            for index, bullet in enumerate(slide_model.bullets):
                paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
                paragraph.text = f"· {bullet}"
                for run in paragraph.runs:
                    run.font.size = Pt(18)
                    run.font.name = "Charter"
                    run.font.color.rgb = ink
        elif slide_model.body:
            _add_text(slide, slide_model.body, left=MARGIN_IN, top=body_top, width=11.5,
                      height=SLIDE_HEIGHT_IN - body_top - MARGIN_IN, size=18, color=ink)

    output.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(output))
    return output


def slide_count(document: Any) -> int:
    """How many slides this document would produce."""
    return len(slides_from(document))
