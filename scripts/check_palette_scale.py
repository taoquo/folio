#!/usr/bin/env python3
"""folio palette scale check

A palette entry's number says where it sits on a lightness ladder, so two names
tell you which colour is darker. The numbers here used to record when a colour
was added instead: `warm-900` was lighter than `warm-800`, `warm-50` sat between
`warm-100` and `warm-200`, and `cinnabar` had no number at all while its
neighbours did.

Two rules, both checked:

  Within a family, a higher number is darker. This is the one that matters --
  it is what makes `teal-600` and `teal-800` comparable at a glance.

  A number sits in the band its lightness belongs to, within one step. The bands
  run ten steps from 50 at the lightest to 900 at the darkest, so two families'
  numbers are roughly comparable too.

A family of one has no order to check and is only asked to be in its band.
Colours that are not ramp steps keep their names and are skipped.

Usage:
    python3 scripts/check_palette_scale.py
    python3 scripts/check_palette_scale.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# A palette entry that is a name rather than a step: the document's vocabulary
# for its canvas and its ink.
NAMED = {"parchment", "ivory", "sand", "ink"}

BANDS = ((0.85, 50), (0.72, 100), (0.55, 200), (0.40, 300), (0.28, 400),
         (0.18, 500), (0.11, 600), (0.06, 700), (0.03, 800))
STEP = 50


def luminance(value: str) -> float:
    text = value.lstrip("#")
    channels = [int(text[i:i + 2], 16) for i in (0, 2, 4)]

    def linear(channel: float) -> float:
        channel /= 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    return (0.2126 * linear(channels[0]) + 0.7152 * linear(channels[1])
            + 0.0722 * linear(channels[2]))


def band(light: float) -> int:
    for floor, number in BANDS:
        if light >= floor:
            return number
    return 900


def palette() -> dict[str, str]:
    import yaml

    path = ROOT / "references" / "profiles" / "theme" / "folio-classic-v1.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    bodies = data.get("profiles") or {}
    default = next((body for body in bodies.values() if body.get("default")), None)
    if default is None:
        default = next(iter(bodies.values()), {})
    return {name: str(value) for name, value in (default.get("palette") or {}).items()}


def check() -> list[dict[str, Any]]:
    entries = palette()
    families: dict[str, list[tuple[str, int, float]]] = {}
    findings: list[dict[str, Any]] = []

    for name, value in sorted(entries.items()):
        if name in NAMED:
            continue
        head, _, tail = name.rpartition("-")
        if not head or not tail.isdigit():
            findings.append({
                "entry": name,
                "problem": "not a ramp step and not a named colour: a family and a number",
                "severity": "error",
            })
            continue
        number = int(tail)
        light = luminance(value)
        expected = band(light)
        if abs(number - expected) > STEP:
            findings.append({
                "entry": name,
                "problem": (f"number {number} does not match its lightness "
                            f"{light:.3f}; band {expected} expected"),
                "severity": "error",
            })
        families.setdefault(head, []).append((name, number, light))

    for family, members in sorted(families.items()):
        # Lightest first: a higher number is darker, so the numbers must rise.
        ordered = sorted(members, key=lambda item: -item[2])
        numbers = [item[1] for item in ordered]
        if numbers != sorted(numbers):
            detail = ", ".join(f"{n}(L={light:.2f})" for n, _, light in ordered)
            findings.append({
                "entry": family,
                "problem": f"a higher number must be darker: {detail}",
                "severity": "error",
            })

    return findings


def render(findings: list[dict[str, Any]]) -> str:
    entries = palette()
    families: dict[str, list[tuple[str, str, float]]] = {}
    for name, value in entries.items():
        if name in NAMED:
            continue
        head = name.rpartition("-")[0]
        families.setdefault(head, []).append((name, value, luminance(value)))

    lines = ["Palette scale", ""]
    for family, members in sorted(families.items()):
        members.sort(key=lambda item: -item[2])
        ordered = "  ".join(f"{n.split('-')[-1]}:{v}" for n, v, _ in members)
        lines.append(f"  {family:<10} {ordered}")
    lines.append("")
    lines.append("  Within a family, a higher number is darker.")
    lines.append("")
    if findings:
        for finding in findings:
            lines.append(f"  ERROR {finding['entry']}: {finding['problem']}")
    else:
        lines.append("  Every family's numbers follow its lightness.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    findings = check()
    if args.format == "json":
        print(json.dumps({"findings": findings, "ok": not findings}, indent=2, ensure_ascii=False))
    else:
        print(render(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
