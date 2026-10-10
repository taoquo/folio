#!/usr/bin/env python3
"""folio corpus matrix

The plan lists twelve coverage classes for the regression corpus. The set that
exists covers composition and a few boundary cases well, and leaves nine classes
with nothing at all, which means those behaviours have no protection.

This module states the matrix, measures the corpus against it, and fills the
gaps. The number of fixtures is not the goal: each entry names the behaviour it
protects, and a class with no fixture is reported as a gap rather than averaged
away by a total.

Usage:
    python3 scripts/corpus_matrix.py report
    python3 scripts/corpus_matrix.py report --format json
    python3 scripts/corpus_matrix.py gaps
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

FIXTURES = ROOT / "references" / "fixtures" / "document"


@dataclass(frozen=True)
class CoverageClass:
    """One row of the plan's matrix."""

    name: str
    purposes: tuple[str, ...]
    target: int
    why: str

    def to_json(self) -> dict[str, Any]:
        return {"class": self.name, "target": self.target, "why": self.why,
                "purposes": list(self.purposes)}


# The plan's matrix, with the purpose tags that satisfy each class. A class is
# satisfied by behaviour, not by a count: two fixtures that exercise nested
# lists protect more than twenty that repeat a paragraph.
MATRIX: tuple[CoverageClass, ...] = (
    CoverageClass(
        "body-rhythm", ("canonical", "one-page-density"), 15,
        "Short and long paragraphs, emphasis, URLs, long words.",
    ),
    CoverageClass(
        "heading-hierarchy", ("heading-structure", "deep-heading", "heading-at-page-bottom"), 12,
        "A heading immediately before body, at a page foot, and deep nesting.",
    ),
    CoverageClass(
        "lists", ("nested-list", "long-marker", "list-page-break"), 10,
        "Nested lists, long markers, a list crossing a page, multi-paragraph items.",
    ),
    CoverageClass(
        "tables", ("wide-table", "spanning-table", "numeric-alignment", "table-page-break"), 15,
        "Wide tables, long cells, numeric alignment, repeated headers.",
    ),
    CoverageClass(
        "figures", ("figure-caption", "figure-page-break", "missing-asset", "long-legend"), 12,
        "A caption near its figure, a figure crossing a page, SVG, a missing asset.",
    ),
    CoverageClass(
        "code-equations", ("code-wrap", "long-code-line", "math-inline", "math-block"), 12,
        "Long lines, line numbers, inline code, breakable and unbreakable expressions.",
    ),
    CoverageClass(
        "references", ("footnote", "citation", "cross-ref", "broken-ref"), 12,
        "Several footnotes, crowded notes, a missing reference, a cross-reference.",
    ),
    CoverageClass(
        "page-geometry", ("mirrored-margin", "running-header", "chapter-opening", "blank-page"), 10,
        "Recto and verso, mirrored margins, running heads, a chapter opening.",
    ),
    CoverageClass(
        "mixed-languages", ("mixed-script-baseline", "font-fallback", "cjk-line-break", "kinsoku"), 18,
        "Chinese, English, mixed composition, digits, punctuation rules.",
    ),
    CoverageClass(
        "complex-scripts", ("rtl", "bidi", "combining-mark"), 8,
        "Right-to-left text, numbers inside it, combining marks.",
    ),
    CoverageClass(
        "unicode-fallback", ("emoji", "variation-selector", "unmapped-glyph"), 10,
        "Emoji, variation selectors, characters no bundled font covers.",
    ),
    CoverageClass(
        "accessibility", ("heading-structure", "alt-text", "table-semantics", "reading-order"), 8,
        "Heading structure, image alternatives, table headers, reading order.",
    ),
    CoverageClass(
        "long-document", ("academic-paper", "api-reference", "financial-report"), 10,
        "Archetypes that stress pagination across many pages.",
    ),
)


def _purposes() -> dict[str, list[str]]:
    """Every purpose tag in the corpus, with the fixtures that carry it."""
    import corpus

    found: dict[str, list[str]] = {}
    for path in corpus.discover_fixtures():
        try:
            data = corpus.load_fixture(path)
        except Exception:
            continue
        for purpose in data.get("purpose") or []:
            found.setdefault(str(purpose), []).append(path.stem)
    return found


@dataclass
class ClassReport:
    coverage: CoverageClass
    fixtures: list[str] = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        return bool(self.fixtures)

    @property
    def at_target(self) -> bool:
        return len(self.fixtures) >= self.coverage.target

    def to_json(self) -> dict[str, Any]:
        return {
            **self.coverage.to_json(),
            "covered_by": sorted(set(self.fixtures))[:8],
            "count": len(set(self.fixtures)),
            "satisfied": self.satisfied,
            "at_target": self.at_target,
        }


def report() -> list[ClassReport]:
    purposes = _purposes()
    out: list[ClassReport] = []
    for coverage in MATRIX:
        fixtures: list[str] = []
        for purpose in coverage.purposes:
            fixtures.extend(purposes.get(purpose, ()))
        out.append(ClassReport(coverage=coverage, fixtures=sorted(set(fixtures))))
    return out


def gaps() -> list[ClassReport]:
    return [item for item in report() if not item.satisfied]


def render_text(items: list[ClassReport]) -> str:
    lines = ["Corpus coverage against the plan's matrix", ""]
    lines.append(f"  {'class':<20} {'fixtures':>8} {'target':>7}  status")
    lines.append("  " + "-" * 62)
    for item in items:
        count = len(set(item.fixtures))
        if not item.satisfied:
            status = "GAP — nothing protects this"
        elif item.at_target:
            status = "at target"
        else:
            status = "below target"
        lines.append(
            f"  {item.coverage.name:<20} {count:>8} {item.coverage.target:>7}  {status}"
        )

    missing = [i for i in items if not i.satisfied]
    lines.append("")
    if missing:
        lines.append(f"  {len(missing)} class(es) have no fixture at all:")
        for item in missing:
            lines.append(f"    {item.coverage.name}: {item.coverage.why}")
    else:
        lines.append("  Every class has at least one fixture.")

    lines.append("")
    lines.append("  A class is satisfied by behaviour, not by a count. The target is a")
    lines.append("  planning figure; a gap is the finding that matters.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    rep = sub.add_parser("report", help="coverage against the matrix")
    rep.add_argument("--format", choices=("text", "json"), default="text")
    rep.add_argument("--output", type=Path)

    sub.add_parser("gaps", help="classes with no fixture")

    args = parser.parse_args(argv)

    items = report()
    if args.command == "gaps":
        missing = [i for i in items if not i.satisfied]
        if not missing:
            print("OK: every coverage class has a fixture")
            return 0
        for item in missing:
            print(f"{item.coverage.name}: {item.coverage.why}")
        return 1

    payload = [item.to_json() for item in items]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(items))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
