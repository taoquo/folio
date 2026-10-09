#!/usr/bin/env python3
"""folio quality vector

Turns measurements from a rendered document into a quality vector, then asks a
contract which of those dimensions are gates.

There is deliberately no overall score. A single number hides trade-offs: a
document can gain even line texture and lose page balance, and collapsing that
into "87/100" destroys the only information a reviewer needs. Dimensions are
reported separately and each is PASS, REVIEW or FAIL on its own terms.

Correctness and taste stay apart. A missing glyph fails the build; "ornament is
minimal" is a judgement and never blocks a release.

Usage:
    python3 scripts/quality_vector.py doc.pdf --genre resume
    python3 scripts/quality_vector.py doc.pdf --genre long-doc --format json
    python3 scripts/quality_vector.py --suite dist/reports/suite.json
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

from artifact_inspector import InspectorReport, inspect  # noqa: E402
from page_contracts import HTML_TARGETS, PPTX_TARGETS  # noqa: E402

# Thresholds are Folio's own starting points, calibrated against the baseline
# capture (see docs/audits/metric-calibration.md). They are not industry
# standards. A value here without a calibration note is provisional.
DEFAULTS = {
    # Below this mean, paragraphs routinely end with a short stub. The letter
    # template sits just under it (0.2167) and is flagged on purpose.
    "last_line_ratio_min": 0.25,
    # Share of paragraphs whose last line stubs. One target sits just below.
    "short_last_line_rate_max": 0.20,
    # Only reached when a template opts into automatic hyphenation.
    "consecutive_hyphens_max": 2,
    # Calibrated, not guessed: the provisional 0.12 flagged 11 of 14 targets.
    # The observed distribution separates whole-page content (0.01-0.11) from
    # naturally short last pages (0.23) from content much shorter than the page
    # budget (0.49-0.76). 0.35 keeps the first two passing and asks a human
    # about the third.
    "page_fill_cv_max": 0.35,
    # A page carrying less than this share of the busiest page's lines.
    "thin_page_ratio": 0.35,
    # Widow and orphan rates, per 1000 spanning paragraphs. The blueprints name
    # 2 as the craft target; Folio's current documents exceed it, which is
    # recorded rather than quietly relaxed.
    "widow_rate_max": 2.0,
    "orphan_rate_max": 2.0,
    "isolated_heading_max": 0,
    "pages_compared_min": 1,
}

SEVERITY = ("PASS", "REVIEW", "FAIL")


@dataclass
class Dimension:
    """One axis of quality, judged on its own."""

    name: str
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    gate: str = "craft"  # correctness | craft | context | preference
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.name,
            "status": self.status,
            "gate": self.gate,
            "metrics": self.metrics,
            "detail": self.detail,
        }


@dataclass
class QualityVector:
    path: str
    genre: str | None = None
    dimensions: list[Dimension] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, dimension: Dimension) -> None:
        self.dimensions.append(dimension)

    @property
    def correctness_failures(self) -> list[Dimension]:
        return [d for d in self.dimensions if d.gate == "correctness" and d.status == "FAIL"]

    @property
    def reviews(self) -> list[Dimension]:
        return [d for d in self.dimensions if d.status == "REVIEW"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "genre": self.genre,
            # No "score" key exists on purpose: see the module docstring.
            "dimensions": [d.to_dict() for d in self.dimensions],
            "correctness_failures": [d.name for d in self.correctness_failures],
            "reviews": [d.name for d in self.reviews],
            "notes": self.notes,
        }


def _judge(value: float | None, *, warn_below: float | None = None,
           fail_below: float | None = None, warn_above: float | None = None,
           fail_above: float | None = None) -> str:
    if value is None:
        return "REVIEW"
    if fail_below is not None and value < fail_below:
        return "FAIL"
    if fail_above is not None and value > fail_above:
        return "FAIL"
    if warn_below is not None and value < warn_below:
        return "REVIEW"
    if warn_above is not None and value > warn_above:
        return "REVIEW"
    return "PASS"


def correctness_dimension(report: InspectorReport, expected_pages: tuple[int, int] | None,
                          fonts: list[str] | None = None,
                          manifest: dict | None = None) -> Dimension:
    """Hard requirements: things that make a document wrong, not ugly."""
    metrics: dict[str, Any] = {"pages": report.pages}
    problems: list[str] = []

    if report.pages <= 0:
        problems.append("document has no pages")

    if expected_pages is not None:
        low, high = expected_pages
        metrics["pages_expected"] = [low, high]
        if not (low <= report.pages <= high):
            problems.append(f"pages {report.pages} outside contract {low}-{high}")

    if fonts is not None and manifest:
        import build  # reused deliberately: one definition of a bad substitution

        unsanctioned = build.find_unsanctioned_fonts(set(fonts), manifest)
        if unsanctioned:
            metrics["unsanctioned_fonts"] = unsanctioned
            problems.append(f"unapproved font substitution: {', '.join(unsanctioned)}")

    metrics["problems"] = problems
    return Dimension(
        name="correctness",
        status="FAIL" if problems else "PASS",
        metrics=metrics,
        gate="correctness",
        detail="; ".join(problems) if problems else None,
    )


def typography_dimension(report: InspectorReport, thresholds: dict[str, float]) -> Dimension:
    """Craft: how the text reads. Reported, not gated."""
    payload = report.to_dict()["typography"]
    metrics = dict(payload)

    wrapped = report.paragraph_count - report.short_last_line_count
    short_rate = None
    if report.paragraph_count:
        # Rate over wrapped paragraphs only: a one-line paragraph has no last
        # line to stub, so counting it would flatter the number.
        wrapped_total = max(report.paragraph_count - 0, 1)
        short_rate = report.short_last_line_count / wrapped_total
    metrics["last_line_ratio_mean"] = payload["last_line_ratio_mean"]
    metrics["short_last_line_rate"] = round(short_rate, 4) if short_rate is not None else None
    metrics["wrapped_paragraphs"] = wrapped

    status = _judge(
        payload["max_consecutive_hyphens"],
        warn_above=thresholds["consecutive_hyphens_max"],
    )
    if payload["last_line_ratio_mean"] is not None:
        if payload["last_line_ratio_mean"] < thresholds["last_line_ratio_min"]:
            status = "REVIEW"
    if short_rate is not None and short_rate > thresholds["short_last_line_rate_max"]:
        status = "REVIEW"

    return Dimension(name="typography", status=status, metrics=metrics, gate="craft")


def pagination_dimension(report: InspectorReport, thresholds: dict[str, float]) -> Dimension:
    """How the document sits on the page: balance, orphans, isolation."""
    payload = report.to_dict()["pagination"]
    counts = payload["page_line_counts"] or []
    metrics = {
        "page_line_counts": counts,
        "page_fill_ratio_cv": payload["page_fill_ratio_cv"],
        "pages": len(counts),
        "widow_count": payload.get("widow_count", 0),
        "orphan_count": payload.get("orphan_count", 0),
        "isolated_heading_count": payload.get("isolated_heading_count", 0),
        "spanning_paragraphs": payload.get("paragraphs_spanning_pages", 0),
        "widow_rate_per_1000": payload.get("widow_rate_per_1000"),
        "orphan_rate_per_1000": payload.get("orphan_rate_per_1000"),
    }

    # A page carrying very few lines while its neighbours are full is the
    # signature of an unbalanced break, even when the total page count is right.
    thin_pages = []
    if len(counts) > 1:
        busiest = max(counts)
        for index, count in enumerate(counts, start=1):
            if busiest > 0 and count / busiest < thresholds.get("thin_page_ratio", 0.35):
                thin_pages.append(index)
    metrics["thin_pages"] = thin_pages

    status = "PASS"
    if len(counts) <= 1:
        # A single page has nothing to balance against. Absence of variance is
        # not a finding, so this passes rather than asking for a review it can
        # never resolve.
        metrics["page_fill_ratio_cv"] = None
        metrics["single_page"] = True
    elif payload["page_fill_ratio_cv"] is None:
        status = "REVIEW"
    elif payload["page_fill_ratio_cv"] > thresholds.get("page_fill_cv_max", 0.35):
        status = "REVIEW"
    if thin_pages:
        status = "REVIEW"

    # Widow and orphan are craft signals, never gates: a document with a widow
    # is still correct, and turning this into a failure would block releases
    # over a typographic preference.
    spanning = metrics["spanning_paragraphs"]
    if spanning:
        if (metrics["widow_rate_per_1000"] or 0) > thresholds.get("widow_rate_max", 2.0):
            status = "REVIEW"
            metrics["widow_exceeds_target"] = True
        if (metrics["orphan_rate_per_1000"] or 0) > thresholds.get("orphan_rate_max", 2.0):
            status = "REVIEW"
            metrics["orphan_exceeds_target"] = True
    if metrics["isolated_heading_count"] > thresholds.get("isolated_heading_max", 0):
        status = "REVIEW"

    return Dimension(name="pagination", status=status, metrics=metrics, gate="craft")


def accessibility_dimension(report: InspectorReport) -> Dimension:
    """Semantic accessibility that can be judged without a PDF/UA validator.

    Text extraction is the proxy available here: a document whose text cannot be
    read out at all is inaccessible regardless of tagging. Full PDF/UA
    validation needs an external validator and is a separate gate.
    """
    metrics = {
        "text_chars": report.text_chars,
        "words": report.words,
        "extractable": report.text_chars > 0,
    }
    status = "PASS" if report.text_chars > 0 else "FAIL"
    return Dimension(
        name="accessibility",
        status=status,
        metrics=metrics,
        gate="correctness" if status == "FAIL" else "craft",
        detail=None if status == "PASS" else "no extractable text",
    )


def unresolved_dimension(report: InspectorReport) -> Dimension:
    """What could not be measured, reported rather than assumed to be fine.

    A metric that silently defaults to zero turns "we did not check" into "it
    passed", which is the failure mode this dimension exists to prevent.
    """
    status = "PASS" if not report.unresolved else "REVIEW"
    return Dimension(
        name="measurement",
        status=status,
        metrics={"unresolved": report.unresolved},
        gate="craft",
        detail="; ".join(report.unresolved) if report.unresolved else None,
    )


def evaluate(pdf: Path, genre: str | None, thresholds: dict[str, float],
             manifest: dict | None = None) -> QualityVector:
    report = inspect(pdf)
    vector = QualityVector(path=str(pdf), genre=genre)

    expected: tuple[int, int] | None = None
    if genre:
        spec = HTML_TARGETS.get(genre) or PPTX_TARGETS.get(genre)
        if spec is not None:
            expected = (spec.min_pages, spec.max_pages)

    vector.add(correctness_dimension(report, expected, fonts=report.fonts, manifest=manifest))
    vector.add(typography_dimension(report, thresholds))
    vector.add(pagination_dimension(report, thresholds))
    vector.add(accessibility_dimension(report))
    vector.add(unresolved_dimension(report))

    for note in report.notes:
        vector.notes.append(note)
    return vector


def render_text(vectors: list[QualityVector]) -> str:
    lines = ["Quality vector", ""]
    for vector in vectors:
        lines.append(f"  {Path(vector.path).name}" + (f"  [{vector.genre}]" if vector.genre else ""))
        for dimension in vector.dimensions:
            lines.append(f"    {dimension.status:<6} {dimension.name}")
            for key in sorted(dimension.metrics):
                value = dimension.metrics[key]
                if isinstance(value, list) and len(value) > 8:
                    value = f"[{len(value)} values]"
                lines.append(f"             {key}: {value}")
            if dimension.detail:
                lines.append(f"             detail: {dimension.detail}")
        if vector.correctness_failures:
            lines.append(f"    ERROR: correctness failures: "
                         f"{', '.join(d.name for d in vector.correctness_failures)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", nargs="?", type=Path)
    parser.add_argument("--genre", help="target name, so the page contract applies")
    parser.add_argument("--suite", type=Path, help="JSON array of {path, genre} entries")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    parser.add_argument("--strict", action="store_true", help="fail on REVIEW as well as FAIL")
    args = parser.parse_args(argv)

    entries: list[tuple[Path, str | None]] = []
    if args.suite:
        if not args.suite.is_file():
            print(f"ERROR: no suite file at {args.suite}")
            return 2
        for item in json.loads(args.suite.read_text(encoding="utf-8")):
            if isinstance(item, str):
                entries.append((Path(item), None))
            else:
                entries.append((Path(item["path"]), item.get("genre")))
    elif args.pdf:
        entries.append((args.pdf, args.genre))
    else:
        print("ERROR: pass a PDF path or --suite")
        return 2

    try:
        import build

        manifest = build.load_font_manifest()
    except Exception:
        manifest = {}

    vectors = [evaluate(path, genre, DEFAULTS, manifest) for path, genre in entries]
    payload = [v.to_dict() for v in vectors]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(vectors))

    failed = [v for v in vectors if v.correctness_failures]
    if failed:
        return 1
    if args.strict and any(v.reviews for v in vectors):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
