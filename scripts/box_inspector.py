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
    # A continuation is recognised by its opening text repeating on a later
    # page. Matching text alone is not enough: a table label such as `P/E`
    # appears on every page it is used, and counting those repeats made short
    # labels look like paragraphs spanning pages, and then like widows.
    #
    # A real continuation also has to be substantial -- a paragraph long enough
    # that part of it can sit at the foot of one page and the rest at the head
    # of the next. A single-line label cannot.
    MIN_CONTINUATION_LINES = 2

    by_text: dict[str, list[BoxParagraph]] = {}
    for paragraph in collected:
        if paragraph.is_heading or not paragraph.text:
            continue
        if paragraph.lines < MIN_CONTINUATION_LINES:
            continue
        by_text.setdefault(paragraph.text[:24], []).append(paragraph)

    for group in by_text.values():
        pages = {p.page for p in group}
        if len(pages) < 2:
            continue
        ordered = sorted(group, key=lambda p: p.page)
        # The pages must be consecutive: a phrase that reappears three pages
        # later is repetition, not a paragraph that continued.
        if ordered[-1].page - ordered[0].page != len(ordered) - 1:
            continue
        report.spanning += 1
        if ordered[-1].lines == 1:
            report.widows += 1
        if ordered[0].lines == 1:
            report.orphans += 1

    # A heading is isolated when it sits at the foot of a page whose content has
    # ended, separated from the text it introduces. A heading that *opens* a page
    # is a different thing: nothing precedes it and its text follows by design,
    # which is how this template puts a contents page on its own.
    for index, paragraph in enumerate(collected):
        if not paragraph.is_heading:
            continue
        same_page_before = [
            p for p in collected[:index] if p.page == paragraph.page
        ]
        if not same_page_before:
            # The heading opens the page; it is not stranded at the foot of one.
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



GENRES = ("one-pager", "letter", "resume", "changelog", "long-doc",
          "portfolio", "equity-report")


def audit(genres: tuple[str, ...] = GENRES) -> dict[str, Any]:
    """Measure pagination for every document type.

    Reports rather than gates: a defect count depends on the content, so a
    threshold would fail on a longer paragraph rather than on a layout problem.
    """
    from style_resolver import template_for_genre

    rows: list[dict[str, Any]] = []
    total = {"paragraphs": 0, "widows": 0, "orphans": 0, "isolated_headings": 0,
             "spanning": 0, "pages": 0}

    for genre in genres:
        template = template_for_genre(genre)
        if template is None or not Path(template).is_file():
            rows.append({"genre": genre, "error": "no template"})
            continue
        report = inspect(Path(template))
        row = {
            "genre": genre,
            "template": Path(template).name,
            "pages": report.pages,
            "paragraphs": len(report.paragraphs),
            "lines": sum(p.lines for p in report.paragraphs),
            "spanning": report.spanning,
            "widows": report.widows,
            "orphans": report.orphans,
            "isolated_headings": report.isolated_headings,
        }
        rows.append(row)
        for key in ("pages", "paragraphs", "spanning", "widows", "orphans",
                    "isolated_headings"):
            total[key] += row[key]

    defect_total = total["widows"] + total["orphans"] + total["isolated_headings"]
    return {
        "rows": rows,
        "totals": total,
        "defects": defect_total,
        "rate": round(defect_total / total["paragraphs"], 5) if total["paragraphs"] else 0.0,
        "note": (
            "Reported, not gated. A defect count depends on the content: a "
            "longer paragraph produces a widow where a shorter one does not."
        ),
    }


def render_audit(payload: dict[str, Any]) -> str:
    lines = ["Pagination audit", ""]
    lines.append(f"  {'genre':<15}{'pages':>7}{'para':>7}{'span':>7}{'widow':>7}{'orphan':>7}{'head':>7}")
    lines.append("  " + "-" * 57)
    for row in payload["rows"]:
        if "error" in row:
            lines.append(f"  {row['genre']:<15}  {row['error']}")
            continue
        lines.append(
            f"  {row['genre']:<15}{row['pages']:>7}{row['paragraphs']:>7}"
            f"{row['spanning']:>7}{row['widows']:>7}{row['orphans']:>7}"
            f"{row['isolated_headings']:>7}"
        )
    totals = payload["totals"]
    lines.append("  " + "-" * 57)
    lines.append(
        f"  {'total':<15}{totals['pages']:>7}{totals['paragraphs']:>7}"
        f"{totals['spanning']:>7}{totals['widows']:>7}{totals['orphans']:>7}"
        f"{totals['isolated_headings']:>7}"
    )
    lines.append("")
    lines.append(f"  defects {payload['defects']} across {totals['paragraphs']} paragraph(s)"
                 f"  ({payload['rate'] * 100:.2f}%)")
    lines.append("")
    lines.append("  " + payload["note"])
    return "\n".join(lines)


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

    audit_cmd = sub.add_parser("audit", help="measure pagination across every document type")
    audit_cmd.add_argument("--format", choices=("text", "json"), default="text")
    audit_cmd.add_argument("--output", type=Path)

    args = parser.parse_args(argv)

    if args.command == "audit":
        payload = audit()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        if args.format == "json":
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(render_audit(payload))
        return 0

    source = args.source if args.source.is_absolute() else ROOT / args.source
    payload = inspect(source).to_json() if args.command == "inspect" else compare(source)

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(payload, args.command))
    return 0 if not (payload.get("notes") or []) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
