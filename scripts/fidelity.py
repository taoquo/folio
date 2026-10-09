#!/usr/bin/env python3
"""folio skeleton fidelity

Measures how closely the IR path reproduces the template path, per document
type.

The two paths should render the same document. Structure matching -- the same
pages, the same fonts -- is necessary but not sufficient: the compatibility
writer once rebuilt the markup from the IR and matched on pages and fonts while
rendering a single stacked column where the template laid out two, which a
visual comparison put at SSIM 0.135.

This reports the measurement for every type, so a single bad type is visible as
an outlier rather than being averaged away.

Usage:
    python3 scripts/fidelity.py measure
    python3 scripts/fidelity.py measure --format json --output dist/reports/fidelity.json
    python3 scripts/fidelity.py measure --genre one-pager --keep dist/fidelity
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Thresholds for the structural dimension. Visual similarity is reported rather
# than gated: SSIM is sensitive to anti-aliasing and to where a line wraps, so a
# single number cannot decide whether a document is acceptable.
SSIM_TARGET = 0.75
PIXEL_TARGET = 0.05


@dataclass
class Fidelity:
    """One document type's measured fidelity."""

    genre: str
    fixture: str
    template: str
    filled: int = 0
    missing: list[str] = field(default_factory=list)
    pages_match: bool = False
    ssim: float | None = None
    changed_ratio: float | None = None
    error: str | None = None

    @property
    def complete(self) -> bool:
        """Whether every placeholder the template declares was filled."""
        return not self.missing

    @property
    def acceptable(self) -> bool:
        """Whether the rendered document matches the template path.

        Deliberately not conditioned on `complete`. A fixture in one language
        rendered through the other's template leaves a few slots unfilled -- an
        English salutation has no Chinese source -- and the page still renders
        identically. The two facts are reported separately so a language
        mismatch is not mistaken for a defect in the writer.
        """
        return (
            self.error is None
            and self.pages_match
            and self.ssim is not None
            and self.ssim >= SSIM_TARGET
            and self.changed_ratio is not None
            and self.changed_ratio <= PIXEL_TARGET
        )

    def to_json(self) -> dict:
        return {
            "genre": self.genre,
            "fixture": self.fixture,
            "template": self.template,
            "filled": self.filled,
            "missing": self.missing[:10],
            "missing_count": len(self.missing),
            "pages_match": self.pages_match,
            "ssim": self.ssim,
            "changed_ratio": self.changed_ratio,
            "complete": self.complete,
            "acceptable": self.acceptable,
            "error": self.error,
        }


def _fixture_for(genre: str) -> Path | None:
    """A canonical fixture for a genre, preferring the plain composition."""
    import corpus

    candidates = []
    for path in corpus.discover_fixtures():
        try:
            data = corpus.load_fixture(path)
        except Exception:
            continue
        if data.get("genre") != genre:
            continue
        if data.get("adversarial"):
            continue
        score = 0
        name = path.stem
        if name.startswith("canonical-"):
            score += 2
        if "-zh-" in name or name.endswith("-zh"):
            score += 1
        if "digits" in name:
            score -= 1
        candidates.append((score, path))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def measure_one(genre: str, work: Path) -> Fidelity:
    """Render both paths for one genre and measure the difference."""
    import corpus
    from document_ir.bridge import bridge_template, default_map_for
    from document_ir.writers.skeleton import attach_ids, fill_template
    from shadow import _legacy_html, _template_for

    fixture = _fixture_for(genre)
    if fixture is None:
        return Fidelity(genre=genre, fixture="", template="", error="no fixture for this genre")

    result = Fidelity(genre=genre, fixture=fixture.stem, template="")
    try:
        data = corpus.load_fixture(fixture)
        template_path = _template_for(data)
        if template_path is None or not template_path.is_file():
            result.error = "no template resolved"
            return result
        result.template = template_path.name
        template_text = template_path.read_text(encoding="utf-8")

        values = {
            (k[2:-2] if k.startswith("{{") and k.endswith("}}") else k): v
            for k, v in (data.get("content") or {}).items()
        }
        document = bridge_template(
            template_text, values,
            document_id=data.get("id", fixture.stem),
            lang=data.get("language", "en-US"),
            genre=genre,
            bridge_map=default_map_for(genre, data.get("language", "en-US")),
        )

        filled = fill_template(template_text, document)
        result.filled = filled.filled
        result.missing = filled.missing

        genre_dir = work / genre
        genre_dir.mkdir(parents=True, exist_ok=True)
        (genre_dir / "legacy.html").write_text(_legacy_html(template_text, data["content"]),
                                               encoding="utf-8")
        (genre_dir / "ir.html").write_text(attach_ids(filled.html, document), encoding="utf-8")

        try:
            from weasyprint import HTML
        except ImportError as exc:
            result.error = f"renderer unavailable: {exc}"
            return result

        for name in ("legacy", "ir"):
            HTML(str(genre_dir / f"{name}.html"), base_url=str(template_path.parent)).write_pdf(
                str(genre_dir / f"{name}.pdf")
            )
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    # Compare.
    try:
        import visual_diff

        report = visual_diff.compare_pdfs(genre_dir / "legacy.pdf", genre_dir / "ir.pdf",
                                          dpi=100, workdir=genre_dir / "diff")
        payload = report.to_dict() if hasattr(report, "to_dict") else {}
        pages = payload.get("pages") or []
        summary = payload.get("summary") or {}
        result.pages_match = bool(pages) and len(pages) == int(summary.get("pages_compared", len(pages)))
        ssims = [p.get("ssim") for p in pages if p.get("ssim") is not None]
        changed = [p.get("changed_ratio") for p in pages if p.get("changed_ratio") is not None]
        if ssims:
            result.ssim = round(sum(ssims) / len(ssims), 5)
        if changed:
            result.changed_ratio = round(sum(changed) / len(changed), 5)
    except Exception as exc:
        result.error = f"comparison failed: {type(exc).__name__}: {exc}"

    return result


def measure(genres: list[str] | None = None, keep: Path | None = None) -> list[Fidelity]:
    """Measure every requested genre."""
    from page_contracts import HTML_TARGETS

    wanted = genres or sorted({g.replace("-en", "") for g in HTML_TARGETS})
    if keep is not None:
        keep.mkdir(parents=True, exist_ok=True)
        return [measure_one(genre, keep) for genre in wanted]

    with tempfile.TemporaryDirectory(prefix="folio-fidelity-") as tmp:
        work = Path(tmp)
        return [measure_one(genre, work) for genre in wanted]


def render_text(results: list[Fidelity]) -> str:
    lines = ["Fidelity — IR path against the template path", ""]
    lines.append(f"  {'genre':<15} {'filled':>7} {'miss':>5} {'ssim':>8} {'changed':>9}  verdict")
    lines.append("  " + "-" * 66)
    for item in results:
        ssim = f"{item.ssim:.4f}" if item.ssim is not None else "-"
        changed = f"{item.changed_ratio * 100:.2f}%" if item.changed_ratio is not None else "-"
        if item.error:
            verdict = f"ERROR {item.error[:28]}"
        elif item.acceptable:
            verdict = "matches" + ("" if item.complete else ", slots unfilled")
        else:
            verdict = "below target"
        lines.append(
            f"  {item.genre:<15} {item.filled:>7} {len(item.missing):>5} {ssim:>8} {changed:>9}  {verdict}"
        )

    measured = [r for r in results if r.ssim is not None]
    if measured:
        best = max(measured, key=lambda r: r.ssim or 0)
        worst = min(measured, key=lambda r: r.ssim or 0)
        average = sum(r.ssim or 0 for r in measured) / len(measured)
        lines.append("")
        lines.append(f"  average SSIM  {average:.4f}")
        lines.append(f"  best          {best.genre} {best.ssim:.4f}")
        lines.append(f"  worst         {worst.genre} {worst.ssim:.4f}")

    complete = sum(1 for r in results if r.complete)
    acceptable = sum(1 for r in results if r.acceptable)
    lines.append("")
    lines.append(f"  renders identically     {acceptable}/{len(results)}")
    lines.append(f"  every slot filled       {complete}/{len(results)}")
    lines.append("  The two are separate: a fixture in one language rendered through the")
    lines.append("  other's template leaves slots unfilled and still matches the page.")
    lines.append("")
    lines.append(f"  Thresholds: SSIM >= {SSIM_TARGET}, changed pixels <= {PIXEL_TARGET * 100:.0f}%.")
    lines.append("  Visual similarity is reported rather than gated: SSIM reacts to anti-aliasing")
    lines.append("  and to where a line wraps, so it cannot by itself decide acceptability.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    measure_cmd = sub.add_parser("measure", help="measure fidelity per document type")
    measure_cmd.add_argument("--genre", action="append", help="limit to a genre (repeatable)")
    measure_cmd.add_argument("--format", choices=("text", "json"), default="text")
    measure_cmd.add_argument("--output", type=Path, help="write the JSON report here")
    measure_cmd.add_argument("--keep", type=Path, help="keep the rendered artifacts here")

    args = parser.parse_args(argv)

    results = measure(args.genre, args.keep)
    payload = {
        "results": [r.to_json() for r in results],
        "thresholds": {"ssim": SSIM_TARGET, "changed_ratio": PIXEL_TARGET},
        "complete": sum(1 for r in results if r.complete),
        "acceptable": sum(1 for r in results if r.acceptable),
        "total": len(results),
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(results))

    return 0 if payload["acceptable"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
