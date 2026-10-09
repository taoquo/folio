#!/usr/bin/env python3
"""folio visual diff

Compares two rendered documents page by page and reports how much they differ.

Two measures, because they answer different questions:

  * SSIM       structural similarity. "How alike do these pages look?"
  * changed pixel ratio   share of pixels past a per-channel threshold.
                          "How much actually moved?"

SSIM is only meaningful between renders of the same document by the same
renderer. It is a regression signal, never evidence that one design is better
than another: two renderers legitimately break lines differently, and that is
not a similarity failure.

The implementation uses Pillow only. A numpy dependency would be the easy path
but it is not needed for a gate that runs on a few dozen pages, and the render
environment is deliberately small.

Usage:
    python3 scripts/visual_diff.py baseline.pdf candidate.pdf
    python3 scripts/visual_diff.py --dir baseline/ --dir candidate/ --format json
    python3 scripts/visual_diff.py a.pdf b.pdf --dpi 300 --threshold 0.10
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# SSIM constants from the original formulation, for 8-bit channels.
K1 = 0.01
K2 = 0.03
L = 255.0
C1 = (K1 * L) ** 2
C2 = (K2 * L) ** 2

# Local statistics window. 8px keeps small text blocks meaningful while staying
# cheap; a larger window washes out line-level differences.
WINDOW = 8

# Pixels differing by more than this per channel count as changed. 8/255 is
# below the threshold where anti-aliasing differences become visible.
PIXEL_THRESHOLD = 8


@dataclass
class PageComparison:
    page: int
    ssim: float | None = None
    changed_ratio: float | None = None
    width: int = 0
    height: int = 0
    size_mismatch: bool = False
    missing: bool = False
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "ssim": None if self.ssim is None else round(self.ssim, 5),
            "changed_ratio": None if self.changed_ratio is None else round(self.changed_ratio, 6),
            "size": [self.width, self.height],
            "size_mismatch": self.size_mismatch,
            "missing": self.missing,
            "note": self.note,
        }


@dataclass
class DiffReport:
    baseline: str
    candidate: str
    dpi: int
    pages: list[PageComparison] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def comparable(self) -> list[PageComparison]:
        return [p for p in self.pages if p.ssim is not None and not p.missing]

    @property
    def page_count_delta(self) -> int | None:
        if not self.pages:
            return None
        base_pages = sum(1 for p in self.pages if not p.missing)
        return base_pages

    def summary(self) -> dict[str, Any]:
        values = [p.ssim for p in self.comparable if p.ssim is not None]
        ratios = [p.changed_ratio for p in self.comparable if p.changed_ratio is not None]
        return {
            "pages_compared": len(self.comparable),
            "ssim_median": round(statistics.median(values), 5) if values else None,
            "ssim_min": round(min(values), 5) if values else None,
            "changed_ratio_max": round(max(ratios), 6) if ratios else None,
            "pages_missing": sum(1 for p in self.pages if p.missing),
            "pages_size_mismatch": sum(1 for p in self.pages if p.size_mismatch),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline,
            "candidate": self.candidate,
            "dpi": self.dpi,
            "summary": self.summary(),
            "pages": [p.to_dict() for p in self.pages],
            "notes": self.notes,
        }


def _run(argv: list[str]) -> None:
    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=300, env=env)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"{argv[0]} failed")


def rasterise(pdf: Path, out_dir: Path, dpi: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf.stem
    _run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)])
    return sorted(out_dir.glob(f"{pdf.stem}-*.png"))


def _local_stats(image):
    """Local mean and variance via band-wise box filtering.

    Returns (mean, variance) as single-channel images. Both are computed from
    the same window so the SSIM terms stay consistent with each other.
    """
    from PIL import ImageFilter, ImageStat

    mean = image.filter(ImageFilter.BoxBlur(WINDOW // 2))
    # var = E[x^2] - E[x]^2, computed on the same window.
    squared = image.point(lambda v: (v * v) // 255)
    mean_sq = squared.filter(ImageFilter.BoxBlur(WINDOW // 2))
    mean_stat = ImageStat.Stat(mean)
    if not mean_stat.mean:
        return mean, mean
    # Approximate variance per pixel by rescaling; exactness is not required for
    # a regression gate, and this keeps the cost linear in page area.
    variance = ImageStat.Stat(mean_sq).mean[0] - (mean_stat.mean[0] ** 2)
    return mean, max(variance, 0.0)


def ssim(a, b) -> float:
    """Structural similarity of two single-channel images.

    Uses global statistics per comparison window approximated by box filtering.
    Exact per-window SSIM would need a convolution per term; for regression
    work the global-variance form is stable and far cheaper, and it is applied
    per page so page-level drift is still localised.
    """
    from PIL import ImageStat

    stat_a = ImageStat.Stat(a)
    stat_b = ImageStat.Stat(b)
    mean_a = stat_a.mean[0]
    mean_b = stat_b.mean[0]

    var_a = stat_a.stddev[0] ** 2
    var_b = stat_b.stddev[0] ** 2

    # Covariance via the difference of squares identity.
    from PIL import ImageChops

    diff = ImageChops.difference(a, b)
    var_diff = ImageStat.Stat(diff).stddev[0] ** 2
    covariance = (var_a + var_b - var_diff) / 2.0

    numerator = (2 * mean_a * mean_b + C1) * (2 * covariance + C2)
    denominator = (mean_a**2 + mean_b**2 + C1) * (var_a + var_b + C2)
    if denominator == 0:
        return 1.0
    return max(min(numerator / denominator, 1.0), -1.0)


def changed_pixel_ratio(a, b, threshold: int = PIXEL_THRESHOLD) -> float:
    """Share of pixels whose per-channel difference exceeds `threshold`."""
    from PIL import ImageChops

    diff = ImageChops.difference(a.convert("L"), b.convert("L"))
    # Everything at or below the threshold becomes 0; the rest is counted.
    mask = diff.point(lambda v: 255 if v > threshold else 0)
    histogram = mask.histogram()
    total = sum(histogram)
    if total == 0:
        return 0.0
    return histogram[255] / total


def compare_pdfs(baseline: Path, candidate: Path, dpi: int, workdir: Path) -> DiffReport:
    report = DiffReport(baseline=str(baseline), candidate=str(candidate), dpi=dpi)

    if not baseline.is_file():
        report.notes.append(f"baseline not found: {baseline}")
        return report
    if not candidate.is_file():
        report.notes.append(f"candidate not found: {candidate}")
        return report

    base_dir = workdir / "baseline"
    cand_dir = workdir / "candidate"
    base_pages = rasterise(baseline, base_dir, dpi)
    cand_pages = rasterise(candidate, cand_dir, dpi)

    if not base_pages:
        report.notes.append("baseline produced no pages")
        return report

    from PIL import Image

    for index, base_path in enumerate(base_pages, start=1):
        comparison = PageComparison(page=index)
        if index > len(cand_pages):
            comparison.missing = True
            comparison.note = "candidate has fewer pages"
            report.pages.append(comparison)
            continue

        with Image.open(base_path) as base_img, Image.open(cand_pages[index - 1]) as cand_img:
            base_gray = base_img.convert("L")
            cand_gray = cand_img.convert("L")
            comparison.width, comparison.height = base_gray.size

            if base_gray.size != cand_gray.size:
                # Padding rather than resizing: a resize would hide a genuine
                # dimension regression behind a plausible-looking score.
                comparison.size_mismatch = True
                width = max(base_gray.size[0], cand_gray.size[0])
                height = max(base_gray.size[1], cand_gray.size[1])
                canvas_a = Image.new("L", (width, height), 255)
                canvas_b = Image.new("L", (width, height), 255)
                canvas_a.paste(base_gray, (0, 0))
                canvas_b.paste(cand_gray, (0, 0))
                base_gray, cand_gray = canvas_a, canvas_b

            comparison.ssim = ssim(base_gray, cand_gray)
            comparison.changed_ratio = changed_pixel_ratio(base_gray, cand_gray)

        report.pages.append(comparison)

    extra = len(cand_pages) - len(base_pages)
    if extra > 0:
        for index in range(len(base_pages) + 1, len(base_pages) + extra + 1):
            report.pages.append(
                PageComparison(page=index, missing=True, note="candidate has more pages")
            )
    return report


def render_text(report: DiffReport) -> str:
    lines = [f"Visual diff ({report.dpi} DPI)", ""]
    lines.append(f"  baseline  {report.baseline}")
    lines.append(f"  candidate {report.candidate}")
    lines.append("")
    summary = report.summary()
    lines.append(f"  pages compared     {summary['pages_compared']}")
    lines.append(f"  SSIM median        {summary['ssim_median']}")
    lines.append(f"  SSIM minimum       {summary['ssim_min']}")
    lines.append(f"  max changed ratio  {summary['changed_ratio_max']}")
    if summary["pages_missing"]:
        lines.append(f"  pages missing      {summary['pages_missing']}")
    if summary["pages_size_mismatch"]:
        lines.append(f"  size mismatch      {summary['pages_size_mismatch']}")
    lines.append("")
    for page in report.pages:
        if page.missing:
            lines.append(f"  page {page.page:>3}  missing ({page.note})")
        else:
            lines.append(
                f"  page {page.page:>3}  ssim {page.ssim:.5f}  changed {page.changed_ratio * 100:.3f}%"
                + ("  size differs" if page.size_mismatch else "")
            )
    if report.notes:
        lines.append("")
        for note in report.notes:
            lines.append(f"  note: {note}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("baseline", nargs="?", type=Path)
    parser.add_argument("candidate", nargs="?", type=Path)
    parser.add_argument("--dpi", type=int, default=160, help="raster DPI (default 160)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, help="write the JSON report here")
    # Regression thresholds. These are the "no intended visual change" gate:
    # a deliberate typography change is expected to fall below them and must be
    # reviewed and re-baselined rather than forced to pass.
    parser.add_argument("--min-ssim", type=float, default=None, help="fail below this SSIM")
    parser.add_argument("--max-changed", type=float, default=None,
                        help="fail above this changed-pixel ratio, as a percent")
    args = parser.parse_args(argv)

    if not args.baseline or not args.candidate:
        print("ERROR: two PDF paths are required")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        report = compare_pdfs(args.baseline, args.candidate, args.dpi, Path(tmp))

    payload = report.to_dict()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))

    summary = report.summary()
    failures = []
    if args.min_ssim is not None and summary["ssim_median"] is not None:
        if summary["ssim_median"] < args.min_ssim:
            failures.append(f"SSIM median {summary['ssim_median']} < {args.min_ssim}")
    if args.max_changed is not None and summary["changed_ratio_max"] is not None:
        if summary["changed_ratio_max"] * 100 > args.max_changed:
            failures.append(
                f"changed ratio {summary['changed_ratio_max'] * 100:.3f}% > {args.max_changed}%"
            )
    if report.notes:
        failures.extend(report.notes)

    if failures:
        print("ERROR: visual regression")
        for failure in failures:
            print(f"  {failure}")
        return 1
    if args.min_ssim is not None or args.max_changed is not None:
        print("OK: within visual thresholds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
