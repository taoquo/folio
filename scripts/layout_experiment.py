#!/usr/bin/env python3
"""folio layout experiment

The plan puts a gate in front of any self-built layout algorithm: the backend
must first be shown to fail, repeatedly and systematically, on cases that matter.
Writing a paragraph composer because a page looked wrong is how a project ends
up maintaining a second typesetting engine for no gain.

This module runs that experiment. It measures the defects the plan names, on the
documents that exist, and reports whether the evidence justifies building
something.

A defect is counted only when the measurement can be trusted. The plan is
explicit that a heuristic detection is a candidate, not a fact, so each one
carries the method that found it and a note on how it can be wrong.

The stopping rule is fixed before the numbers are read:

  a candidate algorithm is worth prototyping when a target defect class appears
  in at least 30% of the documents that can exhibit it.

Below that, the defects are occasional, and occasional defects in a mature
backend are not a reason to replace it.

Usage:
    python3 scripts/layout_experiment.py run
    python3 scripts/layout_experiment.py run --format json --output dist/reports/layout-experiment.json
    python3 scripts/layout_experiment.py verdict
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

# The threshold that decides whether to prototype. Stated here rather than
# chosen after seeing the result, because a threshold chosen afterwards always
# supports the conclusion someone wanted.
PROTOTYPE_THRESHOLD = 0.30


@dataclass
class DefectClass:
    """One kind of layout defect the plan names."""

    name: str
    method: str
    how_it_can_be_wrong: str
    # Whether the detection itself can be trusted. A class whose measurement is
    # known to be unsound is reported but excluded from the decision; letting it
    # in would let a broken metric justify building an engine.
    trustworthy: bool = True
    documents: int = 0
    total: int = 0
    examples: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.documents / self.total if self.total else 0.0

    @property
    def worth_prototyping(self) -> bool:
        return self.trustworthy and self.rate >= PROTOTYPE_THRESHOLD

    def to_json(self) -> dict[str, Any]:
        return {
            "defect": self.name,
            "method": self.method,
            "false_positive_note": self.how_it_can_be_wrong,
            "documents_affected": self.documents,
            "documents_examined": self.total,
            "rate": round(self.rate, 4),
            "worth_prototyping": self.worth_prototyping,
            "examples": self.examples[:5],
        }


def _targets() -> list[tuple[str, Path]]:
    """Documents to measure: the built examples, one per target."""
    from page_contracts import HTML_TARGETS

    out: list[tuple[str, Path]] = []
    for name in sorted(HTML_TARGETS):
        pdf = ROOT / "assets" / "examples" / f"{name}.pdf"
        if pdf.is_file():
            out.append((name, pdf))
    return out


def run() -> list[DefectClass]:
    """Measure the named defects across the documents that exist."""
    import artifact_inspector

    targets = _targets()

    classes = {
        # Also excluded. The rule is "a short last line that is not a paragraph
        # end", and it fires on six of seven pages of the long document. That
        # rate describes how many pages end with a short line, which is normal
        # typography, not how many headings were orphaned.
        "heading-at-page-bottom": DefectClass(
            "heading-at-page-bottom",
            "the last line on a page is short and the paragraph it starts continues",
            "the rule fires on most pages of a normal document, so it measures "
            "page endings rather than orphaned headings",
            trustworthy=False,
        ),
        # Widow and orphan are excluded from the decision. The measurement
        # groups lines into paragraphs by geometry, because a rendered page
        # carries no source ids, and on the long document that grouping scores
        # every spanning paragraph as a widow. A metric that saturates on a
        # normal document cannot show a systematic backend defect.
        "widow": DefectClass(
            "widow",
            "a paragraph's final line lands alone on the next page",
            "paragraph boundaries are inferred from line geometry, not source ids, "
            "and the inference saturates: every spanning paragraph scored as a widow",
            trustworthy=False,
        ),
        "orphan": DefectClass(
            "orphan",
            "a paragraph's first line is stranded at a page foot",
            "same inference as widow; unreliable for the same reason",
            trustworthy=False,
        ),
        "thin-page": DefectClass(
            "thin-page",
            "a page carries far fewer lines than the busiest page",
            "a deliberately short closing page is not a defect; a closing page "
            "with two lines is the document ending, not a layout failure",
            trustworthy=False,
        ),
        "short-last-line": DefectClass(
            "short-last-line",
            "the last line of a paragraph is much shorter than the measure",
            "a short last line is normal prose; the count is real but the "
            "threshold that makes it a defect is a design choice, not a finding",
            trustworthy=False,
        ),
        "hyphen-streak": DefectClass(
            "hyphen-streak",
            "more than two consecutive hyphenated line ends",
            "hyphenation may be intentional for the language",
        ),
    }

    for name, pdf in targets:
        try:
            report = artifact_inspector.inspect(pdf)
        except Exception:
            continue

        for defect in classes.values():
            defect.total += 1

        if report.isolated_heading_count > 0:
            classes["heading-at-page-bottom"].documents += 1
            classes["heading-at-page-bottom"].examples.append(name)
        if report.widow_count > 0:
            classes["widow"].documents += 1
            classes["widow"].examples.append(name)
        if report.orphan_count > 0:
            classes["orphan"].documents += 1
            classes["orphan"].examples.append(name)
        if report.page_fill_cv and report.page_fill_cv > 0.35:
            classes["thin-page"].documents += 1
            classes["thin-page"].examples.append(name)
        if report.short_last_line_count > 0:
            classes["short-last-line"].documents += 1
            classes["short-last-line"].examples.append(name)
        if report.max_consecutive_hyphens > 2:
            classes["hyphen-streak"].documents += 1
            classes["hyphen-streak"].examples.append(name)

    # The total is the number of documents examined, which is the same for each
    # class; kept per class so a class measured on a subset is not overstated.
    return list(classes.values())


def verdict(classes: list[DefectClass]) -> dict[str, Any]:
    """Whether the evidence justifies building a layout algorithm."""
    candidates = [c for c in classes if c.worth_prototyping]
    trustworthy = [c for c in classes if c.trustworthy]
    examined = max((c.total for c in classes), default=0)

    if examined == 0:
        return {
            "decision": "cannot-decide",
            "reason": "no documents were examined",
            "threshold": PROTOTYPE_THRESHOLD,
        }

    if candidates:
        return {
            "decision": "prototype-warranted",
            "reason": (
                f"{len(candidates)} defect class(es) affect at least "
                f"{int(PROTOTYPE_THRESHOLD * 100)}% of documents: "
                + ", ".join(c.name for c in candidates)
            ),
            "threshold": PROTOTYPE_THRESHOLD,
            "candidates": [c.to_json() for c in candidates],
            "scope": (
                "Start with the smallest independently verifiable piece: a "
                "paragraph quality estimator, not a page composer. The plan "
                "requires the prototype to beat the current path on the named "
                "defects without regressing any hard correctness gate."
            ),
        }

    return {
        "decision": "keep-the-backend",
        "reason": (
            f"no trustworthy defect class reaches "
            f"{int(PROTOTYPE_THRESHOLD * 100)}% of the {examined} document(s) examined "
            f"({len(trustworthy)} class(es) were measurable)"
        ),
        "threshold": PROTOTYPE_THRESHOLD,
        "scope": (
            "The backend handles the documents Folio actually produces. Effort "
            "belongs in the quality engine and the corpus, not in a second "
            "typesetting engine."
        ),
    }


def render_text(classes: list[DefectClass], decision: dict[str, Any]) -> str:
    lines = ["Layout experiment", ""]
    lines.append(f"  {'defect':<24} {'docs':>6} {'examined':>9} {'rate':>7}  verdict")
    lines.append("  " + "-" * 66)
    for defect in sorted(classes, key=lambda c: -c.rate):
        verdict_text = "prototype" if defect.worth_prototyping else "occasional"
        lines.append(
            f"  {defect.name:<24} {defect.documents:>6} {defect.total:>9} "
            f"{defect.rate * 100:>6.1f}%  {verdict_text}"
        )

    excluded = [c for c in classes if not c.trustworthy]
    if excluded:
        lines.append("")
        lines.append("  Excluded from the decision (measurement unsound):")
        for defect in excluded:
            lines.append(f"    {defect.name}: {defect.how_it_can_be_wrong[:60]}")

    lines.append("")
    lines.append(f"  Decision: {decision['decision']}")
    lines.append(f"  {decision['reason']}")
    if decision.get("scope"):
        lines.append("")
        for chunk in _wrap(decision["scope"], 72):
            lines.append(f"  {chunk}")

    lines.append("")
    lines.append(f"  The threshold ({int(PROTOTYPE_THRESHOLD * 100)}%) is fixed before the numbers are")
    lines.append("  read. Every detection here is a heuristic, and each says how it")
    lines.append("  can be wrong; a candidate defect is not a confirmed one.")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("run", "measure the named defects"),
                            ("verdict", "report the decision only")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--format", choices=("text", "json"), default="text")
        cmd.add_argument("--output", type=Path)

    args = parser.parse_args(argv)

    classes = run()
    decision = verdict(classes)

    payload = {
        "threshold": PROTOTYPE_THRESHOLD,
        "classes": [c.to_json() for c in classes],
        "decision": decision,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.command == "verdict":
        print(f"Decision: {decision['decision']}")
        print(f"  {decision['reason']}")
    else:
        print(render_text(classes, decision))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
