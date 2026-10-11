#!/usr/bin/env python3
"""Write a colour scheme that clears the bar, rather than one that is hoped to.

A scheme is a palette and the roles that point at it, and the numbers have to
satisfy rules that are easy to get wrong by hand: text at 4.5:1 on two surfaces,
a hairline that stays visible, and ramp numbers that follow lightness. This takes
a description of the hue families and solves for values that pass, then writes
the profile and runs the check over it.

    python3 scripts/scaffold_theme_scheme.py --list
    python3 scripts/scaffold_theme_scheme.py --name folio-slate-v1

The catalogue in `SCHEMES` is a demonstration, not a decision: it exists so the
mechanism can be exercised and looked at, and the profile it writes is the whole
of a scheme.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.theme.contrast import contrast_ratio  # noqa: E402

BANDS = ((0.85, 50), (0.72, 100), (0.55, 200), (0.40, 300), (0.28, 400),
         (0.18, 500), (0.11, 600), (0.06, 700), (0.03, 800))


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


def number_for(value: str) -> int:
    return band(luminance(value))


def darken_until(value: str, surfaces: tuple[str, ...], floor: float) -> str:
    """Move a colour toward black until it clears `floor` on every surface."""
    red, green, blue = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    for _ in range(200):
        current = f"#{red:02X}{green:02X}{blue:02X}"
        if min(contrast_ratio(current, surface) for surface in surfaces) + 1e-9 >= floor:
            return current
        red = max(0, round(red * 0.975))
        green = max(0, round(green * 0.975))
        blue = max(0, round(blue * 0.975))
    raise SystemExit(f"ERROR: could not darken {value} to {floor}")


# Each scheme: a canvas, an ink, a neutral ramp, an accent, and the status hues.
# `mix` is how much of the accent to blend into the neutral ramp, so the ramp
# belongs to the scheme rather than being a plain grey.
SCHEMES = {
    "folio-slate-v1": {
        "note": "Cool neutral canvas, deep azure accent. Institutional research.",
        "canvas": "#F1F3F6",
        "card": "#FAFBFC",
        "ink": "#14181D",
        "accent": "#1F4E8C",
        "accent_light": "#E4EBF4",
        "accent_mid": "#C3D2E6",
        "caution": "#8A5A16",
        "caution_light": "#F5EBD8",
        "negative": "#5C6672",
        "warm_step": "#C9D1DA",
        "soft_step": "#DFE4EA",
        "neutral_hue": (0x5A, 0x64, 0x70),
    },
    "folio-forest-v1": {
        "note": "Warm bone canvas, deep forest accent. Editorial and long-form.",
        "canvas": "#F5F2EA",
        "card": "#FCFAF5",
        "ink": "#161813",
        "accent": "#2F5D46",
        "accent_light": "#E3EDE6",
        "accent_mid": "#BFD5C7",
        "caution": "#8A5A16",
        "caution_light": "#F5EBD8",
        "negative": "#6A6157",
        "warm_step": "#CFC8B8",
        "soft_step": "#E2DCCC",
        "neutral_hue": (0x63, 0x6B, 0x5E),
    },
}


def build(name: str, spec: dict) -> dict:
    """Solve for a palette that clears the bar, and name every entry it needs."""
    canvas, card = spec["canvas"], spec["card"]
    surfaces = (canvas, card)
    ink = spec["ink"]

    def blend(step: float) -> str:
        """The ink stepped toward the canvas: the scheme's own neutral ramp."""
        return "#" + "".join(
            f"{round(int(ink[1 + i:3 + i], 16) + (int(canvas[1 + i:3 + i], 16) - int(ink[1 + i:3 + i], 16)) * step):02X}"
            for i in (0, 2, 4))

    # Warm is darkest because it carries headings, then secondary, then muted --
    # the lightest level that still has to clear 4.5:1.
    warm_raw, secondary_raw, muted_raw = blend(0.20), blend(0.34), blend(0.46)
    # Two borders, the stronger line first, both darkened only to stay visible.
    border_raw, border_soft_raw = blend(0.78), blend(0.88)

    family = name.split("-")[1]
    accent_family = {"folio-slate-v1": "azure", "folio-forest-v1": "forest"}[name]

    # Darkened only as far as the floor requires, so the hierarchy survives.
    warm = darken_until(warm_raw, surfaces, 4.5)
    secondary = darken_until(secondary_raw, surfaces, 4.5)
    muted = darken_until(muted_raw, surfaces, 4.5)
    border = darken_until(border_raw, surfaces, 1.30)
    border_soft = darken_until(border_soft_raw, surfaces, 1.21)
    accent = darken_until(spec["accent"], surfaces, 4.5)
    caution = darken_until(spec["caution"], surfaces, 4.5)
    negative = darken_until(spec["negative"], surfaces, 4.5)

    def numbered(base: str, value: str) -> str:
        return f"{base}-{number_for(value)}"

    entries = {
        "parchment": canvas,
        "ivory": card,
        "ink": ink,
        numbered(family, secondary): secondary,
        numbered(family, muted): muted,
        numbered(family, warm): warm,
        numbered(family, border): border,
        numbered(family, border_soft): border_soft,
        numbered(accent_family, accent): accent,
        numbered(accent_family, spec["accent_mid"]): spec["accent_mid"],
        numbered(accent_family, spec["accent_light"]): spec["accent_light"],
        numbered("amber", caution): caution,
        numbered("amber", spec["caution_light"]): spec["caution_light"],
        numbered(family, negative): negative,
    }

    return {
        "palette": entries,
        "roles": {
            "surface.page": "parchment",
            "surface.card": "ivory",
            "text.primary": "ink",
            "text.secondary": numbered(family, secondary),
            "text.muted": numbered(family, muted),
            "text.warm": numbered(family, warm),
            "border.default": numbered(family, border),
            "border.soft": numbered(family, border_soft),
            "border.warm": numbered(family, border_soft),
            "accent.brand": numbered(accent_family, accent),
            "accent.brand-tint": numbered(accent_family, spec["accent_light"]),
            "accent.tag": numbered(accent_family, spec["accent_mid"]),
            "status.positive": numbered(accent_family, accent),
            "status.caution": numbered("amber", caution),
            "status.caution-tint": numbered("amber", spec["caution_light"]),
            "status.negative": numbered(family, negative),
        },
    }


def render(name: str, spec: dict, built: dict) -> str:
    lines = [
        "# Theme profile",
        "#",
        f"# {spec['note']}",
        "#",
        "# A demonstration scheme. Nothing selects it unless FOLIO_THEME names it.",
        "#",
        "# `palette` holds each raw colour once and `color` points the roles at it.",
        "# A number is a position on a lightness ladder: within a family, a higher",
        "# number is darker. `scripts/check_theme_schemes.py` runs the same bar over",
        "# every scheme -- the roles a template reads, contrast on both surfaces, the",
        "# ladder, and whether every entry can be reached.",
        "",
        "version: 2",
        "profiles:",
        f"  {name}:",
        "    palette:",
    ]
    for entry, value in sorted(built["palette"].items()):
        lines.append(f"      {entry}: '{value}'")
    lines.append("    color:")

    tree: dict = {}
    for role, entry in sorted(built["roles"].items()):
        head, _, tail = role.partition(".")
        if tail:
            tree.setdefault(head, {})[tail] = entry
        else:
            tree[head] = entry

    def emit(node: dict, indent: int) -> None:
        pad = " " * indent
        for key, value in node.items():
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                emit(value, indent + 2)
            else:
                lines.append(f"{pad}{key}:")
                lines.append(f"{pad}  palette: {value}")

    emit(tree, 6)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default=None, help="a scheme in the catalogue")
    parser.add_argument("--list", action="store_true", help="list the catalogue")
    args = parser.parse_args(argv)

    if args.list or not args.name:
        for key, spec in SCHEMES.items():
            print(f"  {key:<20} {spec['note']}")
        return 0

    if args.name not in SCHEMES:
        raise SystemExit(f"ERROR: {args.name} is not in the catalogue")
    built = build(args.name, SCHEMES[args.name])
    print(f"  {args.name}: {len(built['palette'])} palette entries")
    print(render(args.name, SCHEMES[args.name], built))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
