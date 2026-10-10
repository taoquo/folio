#!/usr/bin/env python3
"""folio review pair

Builds a blind A/B comparison from two rendered documents.

The protocol it implements is in `docs/architecture/review-protocol.md`. The
part that has to be mechanical is this one: a reviewer should not know which
page is the new one, and the person preparing the comparison should not be able
to bias it by choosing the labels after seeing the result.

So the assignment is random and the answer is written to a separate file that is
meant to be opened afterwards. That is a small piece of discipline, and it is
the difference between a preference and a guess about which one looked newer.

Usage:
    python3 scripts/review_pair.py --before a.pdf --after b.pdf --out dist/review
    python3 scripts/review_pair.py --before a.pdf --after b.pdf --out dist/review --reveal
    python3 scripts/review_pair.py --score a.pdf b.pdf
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# The labels a reviewer sees. Two is the least that still hides which is which.
LABELS = ("A", "B")


@dataclass
class Pair:
    """One prepared comparison."""

    out_dir: Path
    labels: dict[str, Path]
    answer: dict[str, str]
    score: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "labels": {k: str(v) for k, v in self.labels.items()},
            "side_by_side": str(self.out_dir / "side-by-side.png"),
            "score": self.score,
            "note": (
                "Which label is the new version is in answer.json. Read it after "
                "choosing, not before."
            ),
        }


def rasterize(pdf: Path, out_prefix: Path, *, dpi: int = 150, pages: int = 2) -> list[Path]:
    """Render a PDF's first pages to PNG."""
    import os
    import tempfile

    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-f", "1", "-l", str(pages), "-png", str(pdf), str(out_prefix)],
        check=False, capture_output=True, env=env,
    )
    return sorted(out_prefix.parent.glob(f"{out_prefix.name}-*.png"))


def score(before: Path, after: Path, *, dpi: int = 100) -> dict[str, Any]:
    """Quantify the difference so a reviewer knows whether to look closely."""
    import tempfile

    import visual_diff

    with tempfile.TemporaryDirectory(prefix="folio-review-score-") as tmp:
        report = visual_diff.compare_pdfs(before, after, dpi=dpi, workdir=Path(tmp))
        payload = report.to_dict()

    pages = payload.get("pages") or []
    values = [p.get("ssim") for p in pages if p.get("ssim") is not None]
    changed = [p.get("changed_ratio") for p in pages if p.get("changed_ratio") is not None]
    return {
        "pages": len(pages),
        "ssim_mean": round(sum(values) / len(values), 5) if values else None,
        "ssim_min": round(min(values), 5) if values else None,
        "changed_ratio_max": round(max(changed), 5) if changed else None,
        "identical": bool(values) and min(values) >= 0.99999,
    }


def compose_side_by_side(left: Path, right: Path, out: Path) -> Path | None:
    """Place two pages next to each other, for a reviewer to compare directly."""
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        a, b = Image.open(left).convert("RGB"), Image.open(right).convert("RGB")
    except Exception:
        return None

    gap = 20
    width = a.width + b.width + gap
    height = max(a.height, b.height)
    canvas = Image.new("RGB", (width, height), (246, 240, 234))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + gap, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def build(before: Path, after: Path, out_dir: Path, *, seed: int | None = None) -> Pair:
    """Prepare a blind pair from two documents."""
    rng = random.Random(seed)
    order = list(LABELS)
    rng.shuffle(order)

    sources = {order[0]: before, order[1]: after}
    out_dir.mkdir(parents=True, exist_ok=True)

    labels: dict[str, Path] = {}
    for label, pdf in sources.items():
        pages = rasterize(pdf, out_dir / label)
        labels[label] = pages[0] if pages else pdf

    if len(labels) == 2:
        left, right = labels["A"], labels["B"]
        compose_side_by_side(left, right, out_dir / "side-by-side.png")

    answer = {label: ("after" if pdf == after else "before") for label, pdf in sources.items()}
    (out_dir / "answer.json").write_text(
        json.dumps({
            "answer": answer,
            "note": "Read this after choosing. Knowing which is new before looking defeats the comparison.",
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return Pair(out_dir=out_dir, labels=labels, answer=answer, score=score(before, after))


def reveal(out_dir: Path) -> dict[str, Any]:
    """Read back the mapping, for after a choice has been made."""
    path = out_dir / "answer.json"
    if not path.is_file():
        return {"error": f"no answer file at {path}"}
    return json.loads(path.read_text(encoding="utf-8"))


def render_text(pair: Pair) -> str:
    lines = ["Review pair", ""]
    lines.append(f"  prepared in  {pair.out_dir}")
    for label in LABELS:
        if label in pair.labels:
            lines.append(f"  {label}            {pair.labels[label].name}")
    if pair.score:
        s = pair.score
        lines.append("")
        lines.append(f"  pages compared   {s['pages']}")
        lines.append(f"  SSIM mean        {s['ssim_mean']}")
        lines.append(f"  SSIM min         {s['ssim_min']}")
        lines.append(f"  changed ratio    {s['changed_ratio_max']}")
        if s["identical"]:
            lines.append("")
            lines.append("  The two are visually identical. A review is not needed unless the")
            lines.append("  change was meant to be visible.")
    lines.append("")
    lines.append("  Which label is new is in answer.json. Read it after choosing.")
    lines.append("  The protocol is in docs/architecture/review-protocol.md.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build", help="prepare a blind pair")
    build_cmd.add_argument("--before", type=Path, required=True)
    build_cmd.add_argument("--after", type=Path, required=True)
    build_cmd.add_argument("--out", type=Path, default=ROOT / "dist" / "review")
    build_cmd.add_argument("--seed", type=int, help="fix the label assignment")
    build_cmd.add_argument("--format", choices=("text", "json"), default="text")

    reveal_cmd = sub.add_parser("reveal", help="read back the mapping")
    reveal_cmd.add_argument("--out", type=Path, default=ROOT / "dist" / "review")

    score_cmd = sub.add_parser("score", help="quantify a difference")
    score_cmd.add_argument("before", type=Path)
    score_cmd.add_argument("after", type=Path)
    score_cmd.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    if args.command == "reveal":
        print(json.dumps(reveal(args.out), indent=2, ensure_ascii=False))
        return 0

    if args.command == "score":
        before = args.before if args.before.is_absolute() else ROOT / args.before
        after = args.after if args.after.is_absolute() else ROOT / args.after
        payload = score(before, after)
        if args.format == "json":
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("Difference score")
            print("")
            for key, value in payload.items():
                print(f"  {key:<18} {value}")
        return 0

    before = args.before if args.before.is_absolute() else ROOT / args.before
    after = args.after if args.after.is_absolute() else ROOT / args.after
    for path in (before, after):
        if not path.is_file():
            print(f"ERROR: not found: {path}")
            return 2

    pair = build(before, after, args.out, seed=args.seed)
    if args.format == "json":
        print(json.dumps(pair.to_json(), indent=2, ensure_ascii=False))
    else:
        print(render_text(pair))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
