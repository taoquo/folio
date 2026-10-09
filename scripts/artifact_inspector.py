#!/usr/bin/env python3
"""folio artifact inspector

Extracts measurable facts from a rendered PDF: page geometry, per-word
positions, line structure, and the paragraph metrics that decide whether a
document reads well.

This is the measurement half of the quality model. It reports what the page
actually contains; it does not decide whether that is good. Thresholds belong
to a contract, and the contract is calibrated against these numbers rather than
guessed at.

Word geometry comes from `pdftotext -bbox`, which Poppler already provides, so
no new dependency is introduced.

Usage:
    python3 scripts/artifact_inspector.py report.pdf
    python3 scripts/artifact_inspector.py report.pdf --format json
    python3 scripts/artifact_inspector.py --suite dist/reports/suite.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]

# A line break is inferred when the vertical gap between two words exceeds this
# fraction of the median glyph height on the page. Using a ratio rather than a
# fixed point value keeps the rule valid across font sizes.
LINE_BREAK_RATIO = 1.45

# Words closer than this fraction of the median word height are treated as part
# of the same visual line even if their baselines differ slightly (super- and
# subscripts, inline code, mixed CJK/Latin).
SAME_LINE_RATIO = 0.62

# A line whose right edge falls this far short of the text block edge counts as
# a short line. Used for the last-line ratio, not for every line.
SHORT_LINE_TOLERANCE = 2.0


@dataclass
class Word:
    text: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def width(self) -> float:
        return self.x_max - self.x_min


@dataclass
class Line:
    page: int
    words: list[Word]
    y: float
    left: float
    right: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def y_max(self) -> float:
        return max(w.y_max for w in self.words)


@dataclass
class InspectorReport:
    path: str
    pages: int = 0
    page_size: tuple[float, float] | None = None
    fonts: list[str] = field(default_factory=list)
    lines: int = 0
    words: int = 0
    text_chars: int = 0
    # Paragraph metrics
    paragraph_count: int = 0
    hyphenated_line_count: int = 0
    max_consecutive_hyphens: int = 0
    short_last_line_count: int = 0
    last_line_ratios: list[float] = field(default_factory=list)
    line_fill_ratios: list[float] = field(default_factory=list)
    # Pagination metrics
    page_line_counts: list[int] = field(default_factory=list)
    page_fill_ratios: list[float] = field(default_factory=list)
    page_fill_cv: float | None = None
    # Widow: a paragraph's last line lands alone at the top of a page.
    # Orphan: a paragraph's first line is stranded at the bottom of a page.
    widow_count: int = 0
    orphan_count: int = 0
    # A heading left alone at the foot of a page with no body text under it.
    isolated_heading_count: int = 0
    # Paragraphs that span a page boundary, so widow/orphan rates have a
    # denominator that means something.
    paragraphs_spanning_pages: int = 0
    notes: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "pages": self.pages,
            "page_size": list(self.page_size) if self.page_size else None,
            "fonts": self.fonts,
            "lines": self.lines,
            "words": self.words,
            "text_chars": self.text_chars,
            "typography": {
                "paragraph_count": self.paragraph_count,
                "hyphenated_line_count": self.hyphenated_line_count,
                "max_consecutive_hyphens": self.max_consecutive_hyphens,
                "short_last_line_count": self.short_last_line_count,
                "last_line_ratio_mean": _mean(self.last_line_ratios),
                "line_fill_ratio_mean": _mean(self.line_fill_ratios),
                "line_fill_ratio_cv": _cv(self.line_fill_ratios),
            },
            "pagination": {
                "page_line_counts": self.page_line_counts,
                "page_fill_ratio_mean": _mean(self.page_fill_ratios),
                "page_fill_ratio_cv": self.page_fill_cv,
                "widow_count": self.widow_count,
                "orphan_count": self.orphan_count,
                "isolated_heading_count": self.isolated_heading_count,
                "paragraphs_spanning_pages": self.paragraphs_spanning_pages,
                "widow_rate_per_1000": (
                    round(self.widow_count / self.paragraphs_spanning_pages * 1000, 1)
                    if self.paragraphs_spanning_pages else None
                ),
                "orphan_rate_per_1000": (
                    round(self.orphan_count / self.paragraphs_spanning_pages * 1000, 1)
                    if self.paragraphs_spanning_pages else None
                ),
            },
            "notes": self.notes,
            "unresolved": self.unresolved,
        }


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def _cv(values: list[float]) -> float | None:
    """Coefficient of variation: spread relative to the mean."""
    if len(values) < 2:
        return None
    mean = statistics.fmean(values)
    if mean == 0:
        return None
    return round(statistics.pstdev(values) / mean, 4)


def _run(argv: list[str]) -> str:
    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False,
                                timeout=180, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"{argv[0]} unavailable: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"{argv[0]} failed")
    return result.stdout or ""


def _words_by_page(pdf: Path) -> tuple[list[list[Word]], list[tuple[float, float]]]:
    """Word boxes and page sizes, from Poppler's XHTML output."""
    text = _run(["pdftotext", "-bbox", str(pdf), "-"])
    # The document declares a namespace; strip it so element names are plain.
    text = re.sub(r'\sxmlns="[^"]+"', "", text, count=1)
    root = ElementTree.fromstring(text)

    pages: list[list[Word]] = []
    sizes: list[tuple[float, float]] = []
    for page in root.iter("page"):
        widths = float(page.get("width", 0) or 0)
        heights = float(page.get("height", 0) or 0)
        sizes.append((widths, heights))
        words: list[Word] = []
        for word in page.iter("word"):
            content = (word.text or "").strip()
            if not content:
                continue
            words.append(
                Word(
                    text=content,
                    x_min=float(word.get("xMin", 0) or 0),
                    y_min=float(word.get("yMin", 0) or 0),
                    x_max=float(word.get("xMax", 0) or 0),
                    y_max=float(word.get("yMax", 0) or 0),
                )
            )
        pages.append(words)
    return pages, sizes


def _group_lines(words: list[Word], page_index: int) -> list[Line]:
    """Group words into visual lines using vertical position."""
    if not words:
        return []
    heights = [w.height for w in words if w.height > 0]
    median_height = statistics.median(heights) if heights else 10.0
    same_line_tolerance = median_height * SAME_LINE_RATIO

    ordered = sorted(words, key=lambda w: (w.y_min, w.x_min))
    lines: list[list[Word]] = []
    for word in ordered:
        placed = False
        for line in reversed(lines):
            reference = line[-1]
            # Same visual line when the vertical overlap is large relative to
            # glyph height; this tolerates super/subscripts and mixed scripts.
            if abs(word.y_min - reference.y_min) <= same_line_tolerance:
                line.append(word)
                placed = True
                break
        if not placed:
            lines.append([word])

    out: list[Line] = []
    for line_words in lines:
        line_words.sort(key=lambda w: w.x_min)
        out.append(
            Line(
                page=page_index,
                words=line_words,
                y=min(w.y_min for w in line_words),
                left=min(w.x_min for w in line_words),
                right=max(w.x_max for w in line_words),
            )
        )
    out.sort(key=lambda line: (line.y, line.left))
    return out


def _starts_new_paragraph(nxt: Line, previous: Line, measure: float) -> bool:
    """Whether the line after a page break begins a new paragraph.

    Uses the vertical position of the first line on the next page relative to
    the page's own top margin. A continuation resumes at the top of the flow;
    a new paragraph usually follows a heading or a deliberate gap, which shows
    up as either a short preceding line or a larger leading space.
    """
    # Recovering paragraph boundaries from a rendered page is not reliably
    # possible, and this function does not pretend otherwise.
    #
    # Two approaches were tried and both failed on real Folio output:
    #   * treating every page edge as a paragraph edge reports zero spanning
    #     paragraphs, so widow and orphan rates have no denominator;
    #   * treating a short preceding line as a paragraph end marks every page
    #     edge as a new paragraph, because every Folio page ends with a short
    #     footer line.
    #
    # The reliable method is to carry the source id into the artifact, and
    # WeasyPrint does not preserve HTML `data-*` attributes into the PDF. So
    # paragraph-level pagination is measured from the HTML and the rendered
    # line geometry together by `scripts/paragraph_map.py`, and this function
    # returns False -- "unknown" -- rather than guessing.
    return False


def _is_hyphenated(line: Line) -> bool:
    text = line.text.rstrip()
    return text.endswith("-") or text.endswith("\u2010")


def _extract_fonts(pdf: Path) -> list[str]:
    try:
        out = _run(["pdffonts", str(pdf)])
    except RuntimeError:
        return []
    names = []
    for line in out.splitlines()[2:]:
        if line.strip():
            names.append(line.split()[0].split("+")[-1])
    return sorted(set(names))


def _page_count(pdf: Path) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return 0


def inspect(pdf: Path, *, text_block_height: float | None = None) -> InspectorReport:
    """Measure one rendered PDF.

    `text_block_height` lets a caller supply the flow height for fill-ratio
    purposes. Without it, the widest observed line span is used as a proxy, and
    the report says so in `unresolved` rather than inventing precision.
    """
    report = InspectorReport(path=str(pdf))
    if not pdf.is_file():
        report.notes.append(f"file not found: {pdf}")
        return report

    report.pages = _page_count(pdf)
    report.fonts = _extract_fonts(pdf)

    try:
        pages, sizes = _words_by_page(pdf)
    except RuntimeError as exc:
        report.notes.append(str(exc))
        report.unresolved.append("word geometry")
        return report

    if sizes:
        report.page_size = sizes[0]

    all_lines: list[Line] = []
    for index, words in enumerate(pages, start=1):
        page_lines = _group_lines(words, index)
        all_lines.extend(page_lines)
        report.page_line_counts.append(len(page_lines))

    report.lines = len(all_lines)
    report.words = sum(len(page) for page in pages)
    report.text_chars = sum(len(w.text) for page in pages for w in page)

    # Consecutive-hyphen runs are counted within a page, since a break at a page
    # boundary is a page-turn rather than a run of hyphenated lines.
    run = 0
    max_run = 0
    for index, line in enumerate(all_lines):
        same_page_predecessor = index > 0 and all_lines[index - 1].page == line.page
        if _is_hyphenated(line) and (same_page_predecessor or run == 0):
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1 if _is_hyphenated(line) else 0
        if _is_hyphenated(line):
            report.hyphenated_line_count += 1
    report.max_consecutive_hyphens = max_run

    # Widest line span approximates the measure when the caller cannot supply
    # one. It is a proxy, and is flagged as such.
    measure = max((line.width for line in all_lines), default=0.0)
    if measure <= 0:
        report.unresolved.append("line measure")
        return report

    # The text block height is derived from the rendered lines rather than from
    # a declared margin: the margin is a source-level intent, while the span
    # between the first and last line is what the page actually used. The
    # busiest page defines the usable height, so fill ratio is measured against
    # the fullest column the document produced.
    derived_block_height: float | None = None
    if report.page_size and all_lines:
        page_height = report.page_size[1]
        per_page_span: list[float] = []
        for page_index in range(1, report.pages + 1):
            page_lines = [line for line in all_lines if line.page == page_index]
            if not page_lines:
                continue
            top = min(line.y for line in page_lines)
            bottom = max(line.y_max for line in page_lines)
            per_page_span.append(max(bottom - top, 0.0))
        if per_page_span:
            derived_block_height = max(per_page_span)
        # A span covering almost the whole sheet means the margin guess is
        # meaningless; fall back to the sheet height and say so.
        if derived_block_height and derived_block_height > page_height * 0.98:
            derived_block_height = page_height
            report.unresolved.append("text block height (span covers the page)")

    effective_height = text_block_height or derived_block_height
    if effective_height is None:
        report.unresolved.append("text block height")

    if text_block_height is None and derived_block_height is not None:
        report.notes.append(
            f"text block height derived from rendered lines: {derived_block_height:.1f}pt"
        )

    for line in all_lines:
        if measure > 0:
            report.line_fill_ratios.append(line.width / measure)

    # A paragraph ends at the last line before a noticeably larger vertical gap,
    # or at the end of a page. Last-line ratio is measured per paragraph.
    # Paragraphs are allowed to span page boundaries: a paragraph that broke
    # across two pages is exactly the case widow and orphan counting exists for.
    # Breaking the group at every page edge would make the denominator zero and
    # the metric meaningless.
    paragraphs: list[list[Line]] = []
    current: list[Line] = []
    for index, line in enumerate(all_lines):
        current.append(line)
        nxt = all_lines[index + 1] if index + 1 < len(all_lines) else None
        if nxt is None:
            paragraphs.append(current)
            current = []
            continue
        if nxt.page != line.page:
            # A page edge is not automatically a paragraph edge: a paragraph
            # that broke across pages is what widow and orphan counting exists
            # for. The continuation is recognised by where the next page's text
            # begins -- a paragraph resumed after a break starts at the top of
            # the flow, while a new paragraph follows a heading or a larger
            # leading gap.
            if _starts_new_paragraph(nxt, line, measure):
                paragraphs.append(current)
                current = []
            continue
        gap = nxt.y - line.y
        if gap > measure * 0.045:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)

    report.paragraph_count = len(paragraphs)

    # Paragraph grouping cannot be recovered reliably from a PDF alone: without
    # source ids, consecutive paragraphs separated by a page break are
    # indistinguishable from one long paragraph. The counts below are therefore
    # reported but flagged, so a downstream consumer does not treat them as
    # precise. `references/baselines/document-v1/known-defects.md` records this.
    if report.pages > 1:
        report.unresolved.append(
            "paragraph boundaries (grouped by line geometry; no source ids in the PDF)"
        )
    for paragraph in paragraphs:
        last = paragraph[-1]
        # Only paragraphs that wrapped are meaningful for last-line ratio.
        if len(paragraph) < 2:
            continue
        ratio = last.width / measure if measure else 0.0
        report.last_line_ratios.append(ratio)
        if ratio < 0.25:
            report.short_last_line_count += 1


    # Pagination craft: widow, orphan and heading isolation.
    #
    # Widow and orphan are properties of a paragraph that crosses a page
    # boundary, so only spanning paragraphs are counted. Treating every
    # paragraph as eligible would inflate the denominator with paragraphs that
    # never had a chance to break badly.
    for paragraph in paragraphs:
        pages_in_paragraph: dict[int, int] = {}
        for line in paragraph:
            pages_in_paragraph[line.page] = pages_in_paragraph.get(line.page, 0) + 1
        # A group that spans pages is only meaningful as a paragraph when it
        # actually looks like one: a page boundary alone does not make a
        # paragraph, and counting every crossing would inflate the rate.
        if len(pages_in_paragraph) < 2:
            continue
        report.paragraphs_spanning_pages += 1
        ordered_pages = sorted(pages_in_paragraph)
        # Last line of the paragraph alone on its page: a widow.
        if pages_in_paragraph[ordered_pages[-1]] == 1:
            report.widow_count += 1
        # First line of the paragraph alone at the foot of its page: an orphan.
        if pages_in_paragraph[ordered_pages[0]] == 1:
            report.orphan_count += 1

    # A heading is isolated when it is the last line on its page and the
    # paragraph it introduces continues on the next page. Detecting it from the
    # artifact rather than from markup is deliberate: the reader receives the
    # page, not the source.
    #
    # The condition is narrow on purpose. Any short line at the foot of a page
    # is usually an ordinary paragraph ending, so counting every short last
    # line would report one "isolated heading" per page and mean nothing.
    paragraph_ends = {id(paragraph[-1]) for paragraph in paragraphs}
    lines_by_page: dict[int, list[Line]] = {}
    for line in all_lines:
        lines_by_page.setdefault(line.page, []).append(line)

    for page_lines in lines_by_page.values():
        if not page_lines:
            continue
        last_line = page_lines[-1]
        if id(last_line) in paragraph_ends:
            # The page ends where a paragraph ends; nothing was orphaned.
            continue
        if measure and last_line.width / measure < 0.45:
            report.isolated_heading_count += 1

    if effective_height:
        for page_index in range(1, report.pages + 1):
            page_lines = [line for line in all_lines if line.page == page_index]
            if not page_lines:
                report.page_fill_ratios.append(0.0)
                continue
            top = min(line.y for line in page_lines)
            bottom = max(line.y_max for line in page_lines)
            span = max(bottom - top, 0.0)
            report.page_fill_ratios.append(min(span / effective_height, 1.0))
        report.page_fill_cv = _cv(report.page_fill_ratios)

    return report


def render_text(reports: list[InspectorReport]) -> str:
    lines = ["Artifact inspection", ""]
    for report in reports:
        payload = report.to_dict()
        lines.append(f"  {Path(report.path).name}")
        lines.append(f"    pages {payload['pages']}  lines {payload['lines']}  "
                     f"words {payload['words']}  paragraphs {payload['typography']['paragraph_count']}")
        typ = payload["typography"]
        lines.append(f"    last-line ratio mean {typ['last_line_ratio_mean']}  "
                     f"short last lines {typ['short_last_line_count']}")
        lines.append(f"    hyphenated lines {typ['hyphenated_line_count']}  "
                     f"max consecutive {typ['max_consecutive_hyphens']}")
        pag = payload["pagination"]
        lines.append(f"    page fill CV {pag['page_fill_ratio_cv']}  "
                     f"lines/page {pag['page_line_counts']}")
        lines.append(f"    widows {pag['widow_count']}  orphans {pag['orphan_count']}  "
                     f"isolated headings {pag['isolated_heading_count']}  "
                     f"(spanning paragraphs {pag['paragraphs_spanning_pages']})")
        if payload["unresolved"]:
            lines.append(f"    unresolved: {', '.join(payload['unresolved'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", nargs="*", type=Path, help="PDF files to inspect")
    parser.add_argument("--suite", type=Path, help="inspect every PDF listed in a JSON array of paths")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)

    paths = list(args.pdf)
    if args.suite:
        if not args.suite.is_file():
            print(f"ERROR: no suite file at {args.suite}")
            return 2
        listed = json.loads(args.suite.read_text(encoding="utf-8"))
        paths.extend(Path(p) for p in listed)

    if not paths:
        print("ERROR: no input; pass PDF paths or --suite")
        return 2

    reports = [inspect(path) for path in paths]
    payload = [r.to_dict() for r in reports]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(reports))

    return 0 if all(r.pages > 0 for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
