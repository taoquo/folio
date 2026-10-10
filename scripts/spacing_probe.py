#!/usr/bin/env python3
"""folio spacing probe

Measures the space a document actually leaves between its blocks, and compares
that with what the spacing model says it should be.

Why measure rather than impose. The spacing model can state a gap, and a
differential experiment showed what happens when a stated gap replaces the
template's own: changing `margin-top` to `padding-top` at a single site moved
the rendering to SSIM 0.90, because the two are not the same thing. Replacing 505
declarations on that evidence would be reckless.

What is safe, and what this does, is read the rendered page. Line geometry gives
the distance between two blocks directly. Comparing it with the rule turns the
model from a document nobody reads into a check that runs, and a rule that no
longer matches its template becomes visible.

A probe reports; it does not gate. The measurement infers block boundaries from
line spacing, and an inference is a candidate, not a fact, so a difference is
reported with the numbers behind it and a person decides what it means.

Usage:
    python3 scripts/spacing_probe.py measure assets/examples/long-doc.pdf
    python3 scripts/spacing_probe.py compare --genre long-doc
    python3 scripts/spacing_probe.py compare --all --format json
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

# A gap is treated as a block gap when it exceeds the document's own line
# spacing by this factor. Measured on a real page: body leading 18.5pt, block
# gaps above 27pt, so 1.5 separates them without needing a threshold per genre.
BLOCK_GAP_FACTOR = 1.5

# A gap this close to a rule's preferred value counts as agreement. The bound is
# in points because the measurement is in points; a percentage would be stricter
# for small gaps than for large ones for no reason.
AGREEMENT_TOLERANCE_PT = 1.5


@dataclass
class ObservedGap:
    """One gap found in a rendered page."""

    page: int
    size_pt: float
    above: str
    below: str

    def to_json(self) -> dict[str, Any]:
        return {"page": self.page, "size_pt": round(self.size_pt, 2),
                "above": self.above[:40], "below": self.below[:40]}


@dataclass
class Probe:
    """What a document's spacing looks like when read back."""

    document: str
    pages: int = 0
    lines: int = 0
    baseline_pt: float | None = None
    gaps: list[ObservedGap] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def surplus_pt(self, gap: ObservedGap) -> float:
        """The space a gap adds beyond the document's own leading.

        A rule states a margin; the probe measures the distance between two
        baselines. The two are only comparable after the leading is removed.
        """
        if not self.baseline_pt:
            return gap.size_pt
        return max(gap.size_pt - self.baseline_pt, 0.0)

    @property
    def block_gaps(self) -> list[ObservedGap]:
        return self.gaps

    def sizes(self) -> list[float]:
        return sorted({round(g.size_pt, 1) for g in self.gaps})

    def to_json(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "pages": self.pages,
            "lines": self.lines,
            "baseline_pt": round(self.baseline_pt, 2) if self.baseline_pt else None,
            "block_gap_count": len(self.gaps),
            "block_gap_sizes": self.sizes(),
            "gaps": [g.to_json() for g in self.gaps[:24]],
            "notes": self.notes,
        }


@dataclass
class Comparison:
    """One rule, and what the page shows for it."""

    pair: str
    declared_pt: float
    observed_pt: float | None
    status: str
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        out = {"pair": self.pair, "declared_pt": self.declared_pt,
               "observed_pt": self.observed_pt, "status": self.status}
        if self.note:
            out["note"] = self.note
        return out


def _page_lines(pdf: Path, page: int):
    """The lines of one page, in reading order."""
    import artifact_inspector

    words, _ = artifact_inspector._words_by_page(pdf)
    if page < 1 or page > len(words):
        return []
    return artifact_inspector._group_lines(words[page - 1], page)


def measure(pdf: Path, *, max_gaps: int = 40) -> Probe:
    """Read a document's spacing back off its pages."""
    if not pdf.is_file():
        return Probe(document=str(pdf), notes=[f"not found: {pdf}"])

    probe = Probe(document=str(pdf))
    all_gaps: list[float] = []

    # One page is enough to see a document's spacing: the values repeat, and
    # reading every page would multiply the cost without adding a distinct gap.
    for page in range(1, 4):
        lines = _page_lines(pdf, page)
        if not lines:
            continue
        probe.pages += 1
        probe.lines += len(lines)
        for above, below in zip(lines, lines[1:]):
            distance = abs(below.y - above.y)
            if distance > 0:
                all_gaps.append(distance)

    if not all_gaps:
        probe.notes.append("no line geometry could be extracted")
        return probe

    # The baseline leading is the smallest distance that repeats often; a gap
    # above it is space the document chose to leave.
    from collections import Counter

    counted = Counter(round(g, 1) for g in all_gaps)
    # The leading is the distance that repeats most: it is what separates one
    # line of body text from the next. The smallest gap is not it -- that is a
    # heading sitting close to its subtitle -- and using it would make almost
    # every gap look like a block gap.
    baseline = max(counted, key=lambda size: (counted[size], -size))
    probe.baseline_pt = baseline

    threshold = baseline * BLOCK_GAP_FACTOR
    for page in range(1, 4):
        lines = _page_lines(pdf, page)
        for above, below in zip(lines, lines[1:]):
            distance = abs(below.y - above.y)
            if distance > threshold:
                probe.gaps.append(ObservedGap(
                    page=page, size_pt=distance,
                    above=above.text.strip(), below=below.text.strip(),
                ))
                if len(probe.gaps) >= max_gaps:
                    break

    if not probe.gaps:
        probe.notes.append(
            f"no gap exceeded {threshold:.1f}pt; this document may set all its "
            "spacing at or below its line spacing"
        )
    return probe


def _fixture_pdf(genre: str) -> Path | None:
    """The built example for a genre, which is what a probe can read."""
    for name in (genre, f"{genre}-en"):
        candidate = ROOT / "assets" / "examples" / f"{name}.pdf"
        if candidate.is_file():
            return candidate
    return None


def _rule_value(pair: str) -> float | None:
    """The declared preferred value for a pair, in points."""
    import spacing

    if "->" not in pair:
        return None
    left, right = (part.strip() for part in pair.split("->", 1))
    spec = spacing.BASE_RULES.get((left, right))
    if spec is None:
        return None
    return spec.preferred.as_pt()


def compare(genre: str) -> dict[str, Any]:
    """Compare a genre's rendered spacing with the model's rules."""
    import spacing

    pdf = _fixture_pdf(genre)
    if pdf is None:
        return {"genre": genre, "error": "no built example for this genre"}

    probe = measure(pdf)
    # Compare the surplus over the leading, not the raw baseline distance: a
    # rule describes the space added between blocks, not the distance between
    # the lines themselves.
    observed = sorted({
        round(probe.surplus_pt(gap), 1)
        for gap in probe.gaps
    })

    comparisons: list[Comparison] = []
    for (left, right), spec in sorted(spacing.BASE_RULES.items()):
        declared = spec.preferred.as_pt()
        # A rule is matched to an observed gap if one is within tolerance.
        match = next(
            (size for size in observed if abs(size - declared) <= AGREEMENT_TOLERANCE_PT),
            None,
        )
        if match is not None:
            status = "agrees"
            note = ""
        elif observed:
            status = "not observed"
            note = (
                "no gap of this size appears on the page; the pair may not occur "
                "in this document, or the template decides it another way"
            )
        else:
            status = "not measurable"
            note = "no block gaps were found on the page"

        comparisons.append(Comparison(
            pair=f"{left} -> {right}", declared_pt=round(declared, 2),
            observed_pt=round(match, 2) if match else None,
            status=status, note=note,
        ))

    agreeing = sum(1 for c in comparisons if c.status == "agrees")
    return {
        "genre": genre,
        "pdf": str(pdf.relative_to(ROOT)),
        "probe": probe.to_json(),
        "observed_surplus_pt": observed,
        "comparisons": [c.to_json() for c in comparisons],
        "rules_checked": len(comparisons),
        "rules_agreeing": agreeing,
        "note": (
            "A probe reads the page; it does not gate. Block boundaries are "
            "inferred from line spacing, so a difference is a candidate for a "
            "person to judge, not a confirmed defect."
        ),
    }


def render_text(payload: dict[str, Any], command: str) -> str:
    if "error" in payload:
        return f"ERROR: {payload['error']}"

    if command == "measure":
        probe = payload
        lines = [f"Spacing probe — {Path(probe['document']).name}", ""]
        lines.append(f"  pages examined   {probe['pages']}")
        lines.append(f"  lines            {probe['lines']}")
        base = probe["baseline_pt"]
        lines.append(f"  baseline leading {base}pt" if base else "  baseline leading unknown")
        lines.append(f"  block gaps       {probe['block_gap_count']}")
        if probe.get("block_gap_sizes") and base:
            surplus = sorted({round(max(s - base, 0), 1) for s in probe["block_gap_sizes"]})
            lines.append(f"  surplus over leading {surplus}")
        if probe["block_gap_sizes"]:
            lines.append(f"  distinct sizes   {probe['block_gap_sizes']}")
        if probe["gaps"]:
            lines.append("")
            lines.append("  Largest gaps")
            for gap in sorted(probe["gaps"], key=lambda g: -g["size_pt"])[:6]:
                lines.append(f"    {gap['size_pt']:>6.1f}pt  page {gap['page']}  {gap['above'][:26]}")
        for note in probe["notes"]:
            lines.append("")
            lines.append(f"  {note}")
        return "\n".join(lines)

    lines = [f"Spacing comparison — {payload['genre']}", ""]
    lines.append(f"  {'rule':<30} {'declared':>9} {'observed':>9}  status")
    lines.append("  " + "-" * 66)
    for item in payload["comparisons"]:
        observed = f"{item['observed_pt']:.1f}" if item["observed_pt"] else "-"
        lines.append(
            f"  {item['pair']:<30} {item['declared_pt']:>9.1f} {observed:>9}  {item['status']}"
        )
    lines.append("")
    lines.append(
        f"  {payload['rules_agreeing']}/{payload['rules_checked']} rule(s) match a gap on the page"
    )
    if payload.get("observed_surplus_pt"):
        surplus = payload["observed_surplus_pt"]
        lines.append(f"  observed surplus over leading: {surplus}")
    lines.append("")
    lines.append("  A probe reads the page; it does not gate. Block boundaries are inferred")
    lines.append("  from line spacing, so a difference is a candidate for a person to read.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    measure_cmd = sub.add_parser("measure", help="read a document's spacing back")
    measure_cmd.add_argument("pdf", type=Path)
    measure_cmd.add_argument("--format", choices=("text", "json"), default="text")

    compare_cmd = sub.add_parser("compare", help="compare a genre's spacing with the rules")
    compare_cmd.add_argument("--genre")
    compare_cmd.add_argument("--all", action="store_true")
    compare_cmd.add_argument("--format", choices=("text", "json"), default="text")
    compare_cmd.add_argument("--output", type=Path)

    args = parser.parse_args(argv)

    if args.command == "measure":
        path = args.pdf if args.pdf.is_absolute() else ROOT / args.pdf
        probe = measure(path)
        if args.format == "json":
            print(json.dumps(probe.to_json(), indent=2, ensure_ascii=False))
        else:
            print(render_text(probe.to_json(), "measure"))
        return 0

    genres = (
        ["one-pager", "letter", "resume", "long-doc", "portfolio", "equity-report", "changelog"]
        if args.all else [args.genre or "one-pager"]
    )

    results = [compare(genre) for genre in genres]
    payload: Any = results if args.all else results[0]

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(payload, "compare"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
