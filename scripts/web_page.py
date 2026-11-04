#!/usr/bin/env python3
"""The Web page as a model: chapters and the blocks directly inside them.

The reading page has no page-break geometry to solve; what it needs from a model
is simpler and stricter: *what is on the page*. Today the builder treats the
fragment as a string and recovers chapters with a regex, so the builder, the
checker and the rail script each keep their own idea of what a chapter is.

This module reads the fragment once and returns a frozen list of top-level
blocks with a role from a closed vocabulary. It never rewrites the DOM: a block
is identified by the source span of its start tag, and annotation inserts one
attribute into that tag. The fragment stays the skeleton, the way the print
template does.

    from web_page import scan, validate, annotate
    page = scan(fragment)
    problems = validate(page)

`FOLIO_WEB_MODEL` selects the mode: `off` skips the model, `shadow` builds and
validates it without annotating, `on` annotates. Shadow mode exists so the
migration can be proven byte-identical before anything touches the page.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

# The closed vocabulary of blocks a chapter may hold at its top level. A tag
# outside this table is a defect, not something to guess at: the page's
# components are a contract, and a new one has to be declared here first.
BLOCK_ROLES: dict[tuple[str, str], str] = {
    ("h2", ""): "chapter-title",
    ("h3", ""): "section-title",
    ("p", ""): "paragraph",
    ("p", "lead"): "lead",
    ("p", "formula"): "formula",
    ("p", "src-note"): "source-note",
    ("ul", "prose-list"): "list",
    ("ul", "kpi-row"): "kpi-row",
    ("ul", "phase-seg"): "phase-seg",
    ("div", "insight"): "insight",
    ("div", "multi-card"): "card-grid",
    ("div", "tbl-wrap"): "table",
    ("table", "tbl"): "table",
}

# A table is a wrapped object: `.tbl-wrap` scrolls it on a narrow screen. A bare
# table at the top level would overflow the page instead.
UNWRAPPED = {"table": "table must sit inside .tbl-wrap"}

FIGURE_PLACEHOLDER = re.compile(r"<!--FOLIO:FIGURE:([a-z0-9-]+)-->")

# The chapter heading carries its own number span. Everything after the span is
# the title as the page prints it.
HEADING = re.compile(r'<h2[^>]*>\s*<span class="num">(\d+)</span>(.*?)</h2>', re.S)

MODES = ("off", "shadow", "on")


@dataclass(frozen=True)
class Block:
    id: str
    role: str
    tag: str
    css: str
    start: int
    end: int
    line: int
    # Set for a figure placeholder, which the builder replaces with markup.
    figure: str | None = None


@dataclass(frozen=True)
class Chapter:
    id: str
    number: str
    title: str
    summary: str
    start: int
    end: int
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Page:
    chapters: tuple[Chapter, ...]
    # What the scanner could not classify. The caller decides whether it is
    # fatal; `validate()` folds it in.
    problems: tuple[str, ...] = ()

    def blocks(self) -> tuple[Block, ...]:
        return tuple(block for chapter in self.chapters for block in chapter.blocks)

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for block in self.blocks():
            counts[block.role] = counts.get(block.role, 0) + 1
        return counts


class _Scanner(HTMLParser):
    """Collects chapters and their direct children, with source offsets."""

    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        self.line_starts = [0]
        for match in re.finditer(r"\n", text):
            self.line_starts.append(match.end())
        self.chapters: list[dict] = []
        self.depth = 0
        self.current: dict | None = None
        self.chapter_depth = 0
        self.counter = 0
        self.problems: list[str] = []

    def _abs_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def close_tag(self, start: int) -> int:
        end = self.text.find(">", start)
        return len(self.text) if end < 0 else end + 1

    def handle_starttag(self, tag: str, attrs_list) -> None:
        attrs = dict(attrs_list)
        classes = (attrs.get("class") or "").split()
        start = self._abs_offset()
        self.depth += 1

        if tag == "section" and "chapter" in classes:
            self.current = {
                "id": attrs.get("id", ""),
                "summary": attrs.get("data-sum", ""),
                "start": start,
                "end": len(self.text),
                "blocks": [],
            }
            self.chapter_depth = self.depth
            return

        if self.current is None or self.depth != self.chapter_depth + 1:
            return

        primary = classes[0] if classes else ""
        role = BLOCK_ROLES.get((tag, primary)) or BLOCK_ROLES.get((tag, ""))
        if role is None:
            self.problems.append(
                f"line {self.getpos()[0]}: <{tag} class=\"{' '.join(classes)}\"> "
                f"is not a known block")
            return
        if tag in UNWRAPPED:
            self.problems.append(f"line {self.getpos()[0]}: {UNWRAPPED[tag]}")

        self.counter += 1
        self.current["blocks"].append({
            "id": f"{self.current['id']}-{role}-{self.counter}",
            "role": role,
            "tag": tag,
            "css": " ".join(classes),
            "start": start,
            "end": self.close_tag(start),
            "line": self.getpos()[0],
            "figure": None,
        })

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if (tag == "section" and self.current is not None
                and self.depth == self.chapter_depth):
            self.current["end"] = self.close_tag(self._abs_offset())
            self.chapters.append(self.current)
            self.current = None
        self.depth = max(0, self.depth - 1)

    def handle_comment(self, data: str) -> None:
        # A comment is a sibling: unlike a start tag it does not raise the
        # depth, so a top-level comment sits at the chapter's own depth.
        if self.current is None or self.depth != self.chapter_depth:
            return
        match = FIGURE_PLACEHOLDER.search(f"<!--{data}-->")
        if not match:
            return
        start = self._abs_offset()
        self.counter += 1
        self.current["blocks"].append({
            "id": f"{self.current['id']}-figure-{self.counter}",
            "role": "figure",
            "tag": "figure",
            "css": "figure",
            "start": start,
            "end": self.close_tag(start),
            "line": self.getpos()[0],
            "figure": match.group(1),
        })


def scan(fragment: str) -> Page:
    """Read the fragment into a frozen page. Never rewrites the source."""
    scanner = _Scanner(fragment)
    scanner.feed(fragment)
    scanner.close()
    if scanner.current is not None:  # an unclosed chapter: fail closed
        scanner.chapters.append(scanner.current)
    chapters = []
    for raw in scanner.chapters:
        blocks = tuple(Block(**block) for block in raw["blocks"])
        number, title = _heading(fragment, blocks, raw["end"])
        chapters.append(Chapter(
            id=raw["id"],
            number=number,
            title=title,
            summary=raw["summary"],
            start=raw["start"],
            end=raw["end"],
            blocks=blocks,
        ))
    return Page(chapters=tuple(chapters), problems=tuple(scanner.problems))


def _heading(fragment: str, blocks: tuple[Block, ...], chapter_end: int) -> tuple[str, str]:
    """The chapter's number and title, from its own h2 markup.

    The rail and the TOC used to recover these with a regex over the whole
    fragment, which meant any attribute added to the h2 silently emptied the
    navigation. The heading belongs to the model; the markup supplies the text.
    A block's `end` is the end of its start tag, so the element runs to the next
    block's start.
    """
    for index, block in enumerate(blocks):
        if block.role != "chapter-title":
            continue
        stop = blocks[index + 1].start if index + 1 < len(blocks) else chapter_end
        match = HEADING.match(fragment[block.start:stop])
        if match:
            return match.group(1), match.group(2).strip()
    return "", ""


def validate(page: Page) -> list[str]:
    """Fail-closed structural checks over the model."""
    problems = list(page.problems)
    seen: set[str] = set()
    for chapter in page.chapters:
        if not chapter.id:
            problems.append("a <section class=\"chapter\"> has no id")
        elif chapter.id in seen:
            problems.append(f"duplicate chapter id {chapter.id!r}")
        seen.add(chapter.id)
        if not any(block.role == "chapter-title" for block in chapter.blocks):
            problems.append(f"chapter {chapter.id!r} has no h2")
        ids = [block.id for block in chapter.blocks]
        if len(ids) != len(set(ids)):
            problems.append(f"chapter {chapter.id!r} has duplicate block ids")
        # A figure already owns a caption: the builder writes it from
        # `series.json` into the `<figcaption>`. A source-note directly after
        # the plate is a second caption in a second voice, and the page ends up
        # numbering and describing the same drawing twice.
        for previous, block in zip(chapter.blocks, chapter.blocks[1:]):
            if previous.role == "figure" and block.role == "source-note":
                problems.append(
                    f"chapter {chapter.id!r} line {block.line}: a source-note after a figure "
                    f"repeats its caption; the caption belongs to the figure")
    if not page.chapters:
        problems.append("the fragment declares no chapters")
    return problems


def annotate(fragment: str, page: Page) -> str:
    """Insert `data-folio-role` into each block's start tag.

    Figure placeholders are comments and carry their attributes when the builder
    expands them; annotating a comment would corrupt it.
    """
    inserts = [
        (block.end - 1, f' data-folio-role="{block.role}" data-folio-id="{block.id}"')
        for block in page.blocks()
        if block.tag != "figure"
    ]
    out = fragment
    for offset, addition in sorted(inserts, reverse=True):
        out = out[:offset] + addition + out[offset:]
    return out


def mode() -> str:
    value = os.environ.get("FOLIO_WEB_MODEL", "on").strip().lower()
    return value if value in MODES else "on"


def model_fragment(fragment: str, *, mode_name: str | None = None) -> tuple[str, Page]:
    """Apply the configured mode: return the fragment to render and the model."""
    chosen = mode_name or mode()
    if chosen == "off":
        return fragment, Page(chapters=())
    page = scan(fragment)
    problems = validate(page)
    if problems:
        raise SystemExit("ERROR: page model:\n  " + "\n  ".join(problems))
    if chosen == "shadow":
        return fragment, page
    return annotate(fragment, page), page


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fragment", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--annotate", action="store_true", help="print the annotated fragment")
    parser.add_argument("--mode", choices=MODES, default=None)
    args = parser.parse_args(argv)

    text = args.fragment.read_text(encoding="utf-8")
    page = scan(text)
    problems = validate(page)
    if args.annotate:
        print(annotate(text, page))
    elif args.json:
        import json
        print(json.dumps({
            "chapters": [
                {"id": c.id, "blocks": [{"id": b.id, "role": b.role, "line": b.line}
                                        for b in c.blocks]}
                for c in page.chapters
            ],
            "counts": page.counts(),
            "problems": problems,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"{len(page.chapters)} chapter(s), {len(page.blocks())} block(s)")
        for chapter in page.chapters:
            roles = ", ".join(f"{b.role}" for b in chapter.blocks)
            print(f"  {chapter.id}: {roles}")
        for problem in problems:
            print(f"ERROR: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
