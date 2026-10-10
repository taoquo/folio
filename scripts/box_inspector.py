#!/usr/bin/env python3
"""folio box inspector

Reads a document's paragraph and line structure from the renderer's own box
tree, instead of inferring it from the geometry of a finished PDF.

Why this exists. The artifact inspector estimates paragraph boundaries from line
spacing, because a PDF carries no source identifiers. On a long document the
estimate saturates: every paragraph that crossed a page boundary scored as a
widow, which made the widow rate 100% and the measurement useless for deciding
whether the layout is good.

The box tree has the answer directly. A `BlockBox` carries its element, a
`LineBox` is a line, and the nesting says which paragraph a line belongs to. So
the counts are read rather than guessed.

    PageBox
      BlockBox <html>
        BlockBox <body>
          BlockBox <p>          the paragraph
            LineBox <p>         a line of it
              TextBox <p> "..."
            LineBox <p>
          BlockBox <p>

A page break inside a paragraph is visible as a paragraph with lines on more
than one page, which is what widow and orphan counting needs.

Usage:
    python3 scripts/box_inspector.py inspect <file.html>
    python3 scripts/box_inspector.py compare <file.html>
    python3 scripts/box_inspector.py inspect <file.html> --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Block-level elements that count as a paragraph for widow and orphan purposes.
PARAGRAPH_TAGS = ("p", "li", "blockquote", "dd", "dt", "figcaption", "td", "th")
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

# Elements that carry text directly but are also used as containers. They count
# as a paragraph only when they hold lines of their own: `resume` builds entries
# from `div`, and refusing the tag outright reported zero paragraphs, which
# reads as a clean document rather than an unmeasured one.
CONTAINER_TAGS = ("div", "section", "article", "aside")


@dataclass
class BoxParagraph:
    """One paragraph, as the renderer laid it out."""

    tag: str
    page: int
    lines: int
    text: str
    is_heading: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "tag": self.tag, "page": self.page, "lines": self.lines,
            "heading": self.is_heading, "text": self.text[:60],
        }


@dataclass
class BoxReport:
    """What the box tree says about a document."""

    source: str
    pages: int = 0
    paragraphs: list[BoxParagraph] = field(default_factory=list)
    widows: int = 0
    orphans: int = 0
    isolated_headings: int = 0
    spanning: int = 0
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "pages": self.pages,
            "paragraphs": len(self.paragraphs),
            "lines": sum(p.lines for p in self.paragraphs),
            "paragraphs_spanning_pages": self.spanning,
            "widows": self.widows,
            "orphans": self.orphans,
            "isolated_headings": self.isolated_headings,
            "detail": [p.to_json() for p in self.paragraphs[:40]],
            "notes": self.notes,
            "method": "renderer box tree; paragraph boundaries are read, not inferred",
        }


def _line_count(box: Any) -> int:
    """The lines directly inside a block box."""
    return sum(
        1 for child in (getattr(box, "children", None) or [])
        if type(child).__name__ == "LineBox"
    )


def _text_of(box: Any) -> str:
    """The text a box holds, read from the leaves that carry it.

    A `LineBox` reports no text of its own; the characters are in its `TextBox`
    children. Reading only the line box returned an empty string for every
    paragraph, which broke the content-based way a continued paragraph is
    recognised.
    """
    own = getattr(box, "text", None)
    if isinstance(own, str) and own:
        return own

    parts: list[str] = []
    for child in getattr(box, "children", None) or []:
        parts.append(_text_of(child))
    return "".join(parts).strip()


def _walk_blocks(box: Any, page: int, out: list[BoxParagraph]) -> None:
    """Collect block boxes that carry lines, with the page they landed on."""
    tag = getattr(box, "element_tag", None)
    # A container counts only when it holds lines of its own; the blocks inside
    # it are visited separately and counted there.
    if tag in PARAGRAPH_TAGS or tag in HEADING_TAGS or tag in CONTAINER_TAGS:
        lines = _line_count(box)
        if lines:
            out.append(BoxParagraph(
                tag=str(tag), page=page, lines=lines, text=_text_of(box),
                is_heading=str(tag) in HEADING_TAGS,
            ))
    for child in getattr(box, "children", None) or []:
        _walk_blocks(child, page, out)


def inspect(source: Path) -> BoxReport:
    """Lay a document out and read its structure from the box tree."""
    report = BoxReport(source=str(source))

    if not source.is_file():
        report.notes.append(f"not found: {source}")
        return report

    try:
        from weasyprint import HTML
    except ImportError as exc:
        report.notes.append(f"renderer unavailable: {exc}")
        return report

    try:
        document = HTML(str(source)).render()
    except Exception as exc:
        report.notes.append(f"layout failed: {type(exc).__name__}: {exc}")
        return report

    report.pages = len(document.pages)
    collected: list[BoxParagraph] = []
    for index, page in enumerate(document.pages, start=1):
        page_box = getattr(page, "_page_box", None)
        if page_box is None:
            continue
        _walk_blocks(page_box, index, collected)

    report.paragraphs = collected

    # A paragraph is identified by its text: the same paragraph continued on
    # another page appears as another box with the same content, and a different
    # paragraph has different content.
    # Keyed by the paragraph's opening words rather than the whole text: a
    # paragraph that crosses a page is laid out as several boxes, and the later
    # ones do not repeat the opening.
    by_text: dict[str, list[BoxParagraph]] = {}
    for paragraph in collected:
        if paragraph.is_heading or not paragraph.text:
            continue
        key = paragraph.text[:24]
        by_text.setdefault(key, []).append(paragraph)

    for group in by_text.values():
        pages = {p.page for p in group}
        if len(pages) < 2:
            continue
        report.spanning += 1
        ordered = sorted(group, key=lambda p: p.page)
        if ordered[-1].lines == 1:
            report.widows += 1
        if ordered[0].lines == 1:
            report.orphans += 1

    # A heading with no following line on its page is isolated.
    for index, paragraph in enumerate(collected):
        if not paragraph.is_heading:
            continue
        same_page_after = [
            p for p in collected[index + 1:]
            if p.page == paragraph.page and not p.is_heading
        ]
        if not same_page_after:
            report.isolated_headings += 1

    if not collected:
        report.notes.append("no block boxes with lines were found")
    return report


def compare(source: Path) -> dict[str, Any]:
    """Compare the box-tree measurement with the geometry-based estimate.

    The two are reported side by side rather than one replacing the other: the
    difference is the point, and it shows how far the estimate can be trusted.
    """
    import artifact_inspector

    report = inspect(source)
    payload: dict[str, Any] = {"source": str(source), "box": report.to_json()}

    pdf = source.with_suffix(".pdf")
    if pdf.is_file():
        estimate = artifact_inspector.inspect(pdf)
        payload["geometry"] = {
            "pages": estimate.pages,
            "paragraphs": estimate.paragraph_count,
            "paragraphs_spanning_pages": estimate.paragraphs_spanning_pages,
            "widows": estimate.widow_count,
            "orphans": estimate.orphan_count,
            "isolated_headings": estimate.isolated_heading_count,
            "caveat": (
                "paragraph boundaries are inferred from line spacing; the box "
                "tree reads them"
            ),
        }
    else:
        payload["geometry"] = None
        payload["note"] = f"no rendered PDF beside {source.name}; render it to compare"

    return payload


def render_text(payload: dict[str, Any], command: str) -> str:
    if command == "inspect":
        report = payload
        lines = [f"Box tree — {Path(report['source']).name}", ""]
        lines.append(f"  pages                    {report['pages']}")
        lines.append(f"  paragraphs with lines    {report['paragraphs']}")
        lines.append(f"  lines                    {report['lines']}")
        lines.append(f"  paragraphs spanning      {report['paragraphs_spanning_pages']}")
        lines.append(f"  widows                   {report['widows']}")
        lines.append(f"  orphans                  {report['orphans']}")
        lines.append(f"  isolated headings        {report['isolated_headings']}")
        for note in report["notes"]:
            lines.append("")
            lines.append(f"  {note}")
        lines.append("")
        lines.append(f"  {report['method']}")
        return "\n".join(lines)

    box = payload["box"]
    geometry = payload.get("geometry")
    lines = [f"Measurement comparison — {Path(payload['source']).name}", ""]
    lines.append(f"  {'measure':<26} {'box tree':>10} {'geometry':>10}")
    lines.append("  " + "-" * 50)
    pairs = [
        ("pages", box["pages"], geometry["pages"] if geometry else None),
        ("paragraphs", box["paragraphs"], geometry["paragraphs"] if geometry else None),
        ("spanning paragraphs", box["paragraphs_spanning_pages"],
         geometry["paragraphs_spanning_pages"] if geometry else None),
        ("widows", box["widows"], geometry["widows"] if geometry else None),
        ("orphans", box["orphans"], geometry["orphans"] if geometry else None),
        ("isolated headings", box["isolated_headings"],
         geometry["isolated_headings"] if geometry else None),
    ]
    for label, a, b in pairs:
        lines.append(f"  {label:<26} {str(a):>10} {str(b) if b is not None else '-':>10}")

    lines.append("")
    if geometry:
        lines.append("  " + geometry["caveat"])
        lines.append("")
        lines.append("  Where the two disagree, the box tree is the accurate one: it reads")
        lines.append("  the paragraph the renderer laid out, rather than guessing at it.")
    else:
        lines.append(f"  {payload.get('note', '')}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("inspect", "read a document's structure from the box tree"),
                            ("compare", "compare the box tree with the geometry estimate")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("source", type=Path)
        cmd.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    source = args.source if args.source.is_absolute() else ROOT / args.source
    payload = inspect(source).to_json() if args.command == "inspect" else compare(source)

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(payload, args.command))
    return 0 if not (payload.get("notes") or []) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
