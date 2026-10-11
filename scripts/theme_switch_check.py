#!/usr/bin/env python3
"""folio theme switch check

Proves the claim the colour architecture rests on: a scheme is stated in one
place, and changing it moves every artifact.

The check edits one palette entry, rebuilds the artifacts that carry colour,
and asks of each whether it changed. It then restores the profile and confirms
the artifacts come back, so a run leaves nothing behind.

    python3 scripts/theme_switch_check.py
    python3 scripts/theme_switch_check.py --keep   # leave the edit in place

What is checked, and why each one:

  one-pager        a document, rendered through the projection
  diagram-bar-chart  a diagram template, whose literals are retargeted
  slides           a PPTX, whose writer reads the theme directly

Before the palette existed these three disagreed: changing the theme profile
left the PDF byte-identical, the diagram kept its own literals, and the deck had
a private palette whose ink and rule appeared nowhere else.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "references" / "profiles" / "theme" / "folio-classic-v1.yaml"

# The entry to move, and the value to move it to. A colour no other palette entry
# holds, so a substitution cannot be confused with an existing value.
ENTRY = "cinnabar-600"
FROM = "B83D2E"
TO = "1F5FEB"

ARTIFACTS = {
    "one-pager": ("scripts/build.py", "one-pager", "assets/examples/one-pager.pdf"),
    "diagram": ("scripts/build.py", "diagram-bar-chart", "assets/examples/diagram-bar-chart.pdf"),
    "slides": ("scripts/build.py", "slides", "assets/examples/slides.pptx"),
}


def _rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def colour_presence(path: Path, value: str) -> int:
    """How much of the artifact carries a colour.

    A PDF is rendered and its pixels counted; a PPTX is unzipped and its XML
    searched, because a deck stores the hex rather than a raster. Either way the
    question is whether the colour is there, which a file hash cannot answer --
    a PDF's object id and a deck's timestamp both differ between identical
    rebuilds.
    """
    if not path.is_file():
        return -1
    hex_value = value.upper()
    if path.suffix.lower() == ".pptx":
        hits = 0
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith(".xml"):
                    hits += archive.read(name).decode("utf-8", "ignore").upper().count(hex_value)
        return hits

    scratch = path.with_suffix(".themecheck")
    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", "/tmp/fc-cache")
    subprocess.run(["pdftoppm", "-r", "60", "-png", "-f", "1", "-l", "1", str(path), str(scratch)],
                   env=env, capture_output=True, check=False)
    produced = scratch.with_name(scratch.name + "-1.png")
    if not produced.is_file():
        return -1
    from PIL import Image

    image = Image.open(produced).convert("RGB")
    target = _rgb(hex_value)
    count = 0
    for pixel in image.getdata():
        if all(abs(a - b) <= 40 for a, b in zip(pixel, target)):
            count += 1
    produced.unlink(missing_ok=True)
    return count


def build(target: str) -> None:
    subprocess.run(
        [sys.executable, "scripts/build.py", target],
        cwd=ROOT, check=False, capture_output=True,
    )


def snapshot() -> dict[str, tuple[int, int]]:
    """For each artifact: how much of the old colour and how much of the new."""
    out = {}
    for name, (_script, target, artifact) in ARTIFACTS.items():
        build(target)
        path = ROOT / artifact
        out[name] = (colour_presence(path, FROM), colour_presence(path, TO))
    return out


def rewrite(value: str) -> None:
    text = PROFILE.read_text(encoding="utf-8")
    pattern = re.compile(rf"({re.escape(ENTRY)}: )'#[0-9A-Fa-f]{{6}}'")
    if not pattern.search(text):
        raise SystemExit(f"ERROR: no palette entry named {ENTRY}")
    PROFILE.write_text(pattern.sub(rf"\g<1>'#{value}'", text, count=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", action="store_true",
                        help="leave the palette edit in place instead of restoring it")
    args = parser.parse_args(argv)

    backup = PROFILE.read_text(encoding="utf-8")
    try:
        print(f"  palette.{ENTRY}: #{FROM} -> #{TO}\n")
        before = snapshot()

        rewrite(TO)
        after = snapshot()

        print(f"\n  {'artifact':<12} {'old colour before':>18} {'after':>8} "
              f"{'new colour before':>18} {'after':>8}  verdict")
        print("  " + "-" * 84)
        failures = 0
        for name in ARTIFACTS:
            old_before, new_before = before[name]
            old_after, new_after = after[name]
            moved = old_after == 0 and new_after > 0
            if not moved:
                failures += 1
            print(f"  {name:<12} {old_before:>18} {old_after:>8} "
                  f"{new_before:>18} {new_after:>8}  {'moved' if moved else 'UNCHANGED'}")

        if args.keep:
            print(f"\n  --keep: {PROFILE.name} left on #{TO}")
            return 1 if failures else 0

        PROFILE.write_text(backup, encoding="utf-8")
        restored = snapshot()
        print()
        for name in ARTIFACTS:
            old_back, new_back = restored[name]
            back = old_back > 0 and new_back == 0
            if not back:
                failures += 1
            print(f"  {name:<12} restored: old colour {old_back}, new colour {new_back} "
                  f"{'yes' if back else 'NO'}")

        print()
        if failures:
            print(f"ERROR: {failures} artifact(s) did not follow the palette")
            return 1
        print("OK: one palette entry moved every artifact, and restoring it moved them back")
        return 0
    finally:
        if not args.keep:
            PROFILE.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
