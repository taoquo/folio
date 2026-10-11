#!/usr/bin/env python3
"""folio demo showcase build

The showcase images in `assets/demos/` had no build target, and the commit that
rebuilt them by hand said so: *"They are historical artifacts with no build
target, so nothing had refreshed them."* They went stale again -- seventeen of
twenty-one PDFs and every PNG still carried the hairline and the muted grey the
colour work had retired.

Each demo is an HTML source, rendered to PDF and captured to PNG. That is what
this does, using the capture recipes the repository documents.

    python3 scripts/build_demos.py            # rebuild every demo that has a source
    python3 scripts/build_demos.py --check    # report which are behind, change nothing
    python3 scripts/build_demos.py --only demo-tesla

Seven demos have **no source in the repository** -- the `-zh` showcases, added in
`50471fd` from content that was never committed. They cannot be rebuilt, and the
check names them rather than passing over them.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ROOT / "assets" / "demos"

# The capture recipes, as `AGENTS.md` states them. A portrait document is its
# first page at 150dpi; a landscape deck is the first two, stacked and extended to
# the same canvas so the showcase grid stays even.
PORTRAIT = ("pdftoppm", "-r", "150", "-f", "1", "-l", "1", "-png")
LANDSCAPE = ("pdftoppm", "-r", "150", "-f", "1", "-l", "2", "-png")
CANVAS = (1241, 1754)

# Sources with no counterpart: named in the report rather than skipped, because a
# silent skip is how they went stale in the first place.
SOURCELESS = (
    "demo-agent-ops-longdoc-zh",
    "demo-agent-slides-zh",
    "demo-chendu-portfolio-zh",
    "demo-folio-changelog-zh",
    "demo-model-review-letter-zh",
    "demo-qinglan-onepager-zh",
    "demo-zhouxu-resume-zh",
)


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", "/tmp/fc-cache")
    return env


def sources() -> list[Path]:
    return sorted(DEMOS.glob("demo-*.html"))


def render_pdf(source: Path, out: Path) -> None:
    from weasyprint import HTML

    HTML(filename=str(source), base_url=str(source.parent.resolve())).write_pdf(str(out))


def is_landscape(pdf: Path) -> bool:
    result = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, env=_env())
    match = re.search(r"Page size:\s+([0-9.]+) x ([0-9.]+)", result.stdout)
    if not match:
        return False
    return float(match.group(1)) > float(match.group(2))


def capture(pdf: Path, out: Path) -> None:
    """One page for a document, two stacked for a deck."""
    prefix = Path("/tmp") / f"folio-demo-{pdf.stem}"
    for stale in Path("/tmp").glob(f"{prefix.name}-*.png"):
        stale.unlink()
    recipe = LANDSCAPE if is_landscape(pdf) else PORTRAIT
    subprocess.run([*recipe, str(pdf), str(prefix)], capture_output=True, env=_env())
    pages = sorted(Path("/tmp").glob(f"{prefix.name}-*.png"))
    if not pages:
        raise RuntimeError(f"pdftoppm produced no page for {pdf.name}")
    if len(pages) == 1:
        out.write_bytes(pages[0].read_bytes())
        return

    from PIL import Image

    first = Image.open(pages[0]).convert("RGB")
    second = Image.open(pages[1]).convert("RGB")
    height = 867
    first = first.resize((round(first.width * height / first.height), height), Image.LANCZOS)
    second = second.resize((round(second.width * height / second.height), height), Image.LANCZOS)
    gap = 20
    sheet = Image.new("RGB", (max(first.width, second.width), height * 2 + gap), (246, 240, 234))
    sheet.paste(first, (0, 0))
    sheet.paste(second, (0, height + gap))
    canvas = Image.new("RGB", CANVAS, (246, 240, 234))
    canvas.paste(sheet, ((CANVAS[0] - sheet.width) // 2, (CANVAS[1] - sheet.height) // 2))
    canvas.save(out)


def retired_colours(png: Path) -> dict[str, int]:
    """Colours the scheme no longer produces, still visible in an artifact.

    Cheap and environment-independent: it does not compare two renders, it asks
    whether a published image still shows a value the palette retired.
    """
    from collections import Counter

    from PIL import Image

    retired = {"#E9DED4": "hairline", "#E8DED6": "soft hairline", "#85776F": "muted text"}
    counts = Counter(Image.open(png).convert("RGB").getdata())
    found: dict[str, int] = {}
    for value, label in retired.items():
        target = tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
        # Exact, not approximate: these pages are flat colour, so a retired value
        # that is really there covers thousands of pixels, while anti-aliased text
        # passes near it without ever landing on it. A tolerance matched the blend.
        hits = counts.get(target, 0)
        if hits > 100:
            found[label] = hits
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="report stale artifacts and sourceless demos; write nothing")
    parser.add_argument("--only", default=None, help="one demo by stem")
    args = parser.parse_args(argv)

    chosen = [p for p in sources() if args.only is None or p.stem == args.only]
    if not chosen:
        print(f"ERROR: no demo source matches {args.only!r}")
        return 1

    stale: list[str] = []
    for source in chosen:
        pdf = DEMOS / f"{source.stem}.pdf"
        png = DEMOS / f"{source.stem}.png"
        if args.check:
            if not png.is_file():
                stale.append(f"{source.stem}: no artifact")
                continue
            found = retired_colours(png)
            if found:
                stale.append(f"{source.stem}: shows {', '.join(sorted(found))}")
            continue
        render_pdf(source, pdf)
        capture(pdf, png)
        print(f"  {source.stem}: rebuilt")

    if args.check:
        for name in stale:
            print(f"  STALE {name}")
        for name in SOURCELESS:
            print(f"  NO-SOURCE {name}: added in 50471fd, its content was never committed")
        if stale:
            print(f"\nERROR: {len(stale)} demo(s) behind")
            return 1
        print(f"\nOK: {len(chosen)} demo(s) current, {len(SOURCELESS)} with no source")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
