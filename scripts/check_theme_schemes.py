#!/usr/bin/env python3
"""folio theme scheme check

Every colour scheme has to clear the same bar, whichever one a document selects.

The mechanism for a second scheme existed before a second scheme did, so nothing
had ever asked whether one could ship unreadable. This runs the questions that
decide it, for every profile in `references/profiles/theme/`:

  shape         the roles a template reads are all present
  contrast      text clears 4.5:1 on both surfaces; a hairline stays visible
  scale         within a palette family, a higher number is darker
  reach         no palette entry is defined and then never used
  default       exactly one scheme is marked default

    python3 scripts/check_theme_schemes.py
    python3 scripts/check_theme_schemes.py --theme folio-slate-v1
    python3 scripts/check_theme_schemes.py --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.theme.contrast import contrast_ratio  # noqa: E402

# A template reads these. A scheme that omits one renders a page with a hole in
# it, so the list is a contract rather than a suggestion.
REQUIRED_ROLES = (
    "color.surface.page", "color.surface.card",
    "color.text.primary", "color.text.secondary", "color.text.muted", "color.text.warm",
    "color.border.default", "color.border.soft",
    "color.accent.brand", "color.accent.brand-tint",
    "color.status.positive", "color.status.caution", "color.status.negative",
    "color.status.caution-tint",
    # The drawing theme reads these. A scheme that omits one leaves that chart
    # series on a literal, which is the failure the bridge exists to prevent.
    "color.series.1", "color.series.2", "color.series.3",
    "color.series.4", "color.series.5", "color.series.6",
)

# (foreground, background, minimum, purpose). Both surfaces a document uses, so a
# scheme cannot be readable on the canvas and unreadable on a card.
CONTRAST_PAIRS = (
    ("color.text.primary", "color.surface.page", 4.5, "body on canvas"),
    ("color.text.primary", "color.surface.card", 4.5, "body on card"),
    ("color.text.secondary", "color.surface.page", 4.5, "secondary on canvas"),
    ("color.text.secondary", "color.surface.card", 4.5, "secondary on card"),
    ("color.text.muted", "color.surface.page", 4.5, "muted on canvas"),
    ("color.text.muted", "color.surface.card", 4.5, "muted on card"),
    ("color.text.warm", "color.surface.page", 4.5, "warm on canvas"),
    ("color.text.warm", "color.surface.card", 4.5, "warm on card"),
    ("color.accent.brand", "color.surface.page", 4.5, "accent on canvas"),
    ("color.accent.brand", "color.surface.card", 4.5, "accent on card"),
    ("color.status.positive", "color.surface.page", 4.5, "positive on canvas"),
    ("color.status.caution", "color.surface.page", 4.5, "caution on canvas"),
    ("color.status.negative", "color.surface.page", 4.5, "negative on canvas"),
    ("color.border.default", "color.surface.page", 1.2, "hairline on canvas"),
    ("color.border.soft", "color.surface.page", 1.2, "soft hairline on canvas"),
)

BANDS = ((0.85, 50), (0.72, 100), (0.55, 200), (0.40, 300), (0.28, 400),
         (0.18, 500), (0.11, 600), (0.06, 700), (0.03, 800))
STEP = 50
NAMED = {"parchment", "ivory", "sand", "ink"}


def _yaml():
    import yaml

    return yaml


def profiles() -> dict[str, dict[str, Any]]:
    """Every scheme in every file, so a second file is checked the day it lands."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((ROOT / "references" / "profiles" / "theme").glob("*.yaml")):
        data = _yaml().safe_load(path.read_text(encoding="utf-8")) or {}
        out.update(data.get("profiles") or {})
    return out


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


def ledger_entries() -> set[str]:
    """Palette entries the template-literal ledger maps a shipped colour to."""
    path = ROOT / "references" / "theme" / "template-literal-ledger.json"
    if not path.is_file():
        return set()
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - a broken ledger must not stop a check
        return set()
    # Only the palette-form targets name an entry here; a role target is reached
    # by the role itself, which the palette table already counts.
    return {target.split(":", 1)[1] for target in (ledger.get("shipped") or {}).values()
            if target.startswith("palette:")}


def _resolve(name: str):
    import style_resolver

    return style_resolver.resolve(names={"theme": name})



def drawing_bridge_findings(name: str) -> list[dict[str, str]]:
    """Whether a scheme's drawing theme can be swapped without losing a meaning.

    Every diagram artefact is painted with the `folio` drawing theme and then
    rethemed by substituting colour values, so the map from `folio` onto each
    other theme has to be a function: one source colour, one target colour. Two
    tokens sharing a value in the source collapse into a single entry, and the
    later field wins -- which is correct only when both name the same target.
    """
    from dataclasses import asdict

    from drawing.theme.folio import folio_theme_for
    from drawing.theme.profiles import THEME_PROFILE_NAMES, resolve_theme

    themed = folio_theme_for(name)
    source = asdict(themed)
    groups: dict[str, list[str]] = {}
    for field, value in source.items():
        if isinstance(value, str) and value.startswith("#"):
            groups.setdefault(value.lower(), []).append(field)

    findings: list[dict[str, str]] = []
    for target_name in THEME_PROFILE_NAMES:
        if target_name == "folio":
            continue
        target = asdict(resolve_theme(target_name))
        for value, fields in sorted(groups.items()):
            if len(fields) < 2:
                continue
            targets = {target[field] for field in fields}
            if len(targets) > 1:
                findings.append({
                    "kind": "bridge", "subject": value,
                    "detail": (f"{' and '.join(fields)} share {value} under {name}, but "
                               f"{target_name} gives them {sorted(targets)}; one of them "
                               f"would lose its meaning"),
                })
    return findings


def check_scheme(name: str) -> dict[str, Any]:
    """Everything asked of one scheme."""
    findings: list[dict[str, str]] = []
    style = _resolve(name)
    if style.domains.get("theme") != name:
        return {"theme": name, "findings": [{
            "kind": "load", "subject": name,
            "detail": f"the profile does not resolve to itself: {style.violations}",
        }], "values": {}, "metrics": {}}

    def value(path: str) -> str:
        resolved = style.get(path)
        return str(resolved).strip() if resolved is not None else ""

    for role in REQUIRED_ROLES:
        if not value(role).startswith("#"):
            findings.append({"kind": "shape", "subject": role,
                             "detail": "a template reads this and the scheme does not define it"})

    for foreground, background, minimum, purpose in CONTRAST_PAIRS:
        front, back = value(foreground), value(background)
        if not front.startswith("#") or not back.startswith("#"):
            continue
        ratio = contrast_ratio(front, back)
        if ratio + 1e-9 < minimum:
            findings.append({
                "kind": "contrast", "subject": purpose,
                "detail": f"{front} on {back} is {ratio:.2f}:1, below {minimum}",
            })

    palette = {path.split(".", 1)[1]: value(path) for path in style.values
               if path.startswith("palette.") and value(path).startswith("#")}
    # Reachable two ways: a role points at it, or a template paints it as a
    # literal the ledger maps to it. Both are real readers.
    used = {entry.chain[-1].split("palette.")[-1] for entry in style.values.values()
            if "palette." in entry.chain[-1]}
    used |= ledger_entries()

    for entry, colour in sorted(palette.items()):
        if entry in NAMED:
            continue
        head, _, tail = entry.rpartition("-")
        if not head or not tail.isdigit():
            findings.append({"kind": "scale", "subject": entry,
                             "detail": "not a ramp step and not a named colour"})
            continue
        number = int(tail)
        light = luminance(colour)
        if abs(number - band(light)) > STEP:
            findings.append({
                "kind": "scale", "subject": entry,
                "detail": f"number {number} does not match lightness {light:.3f}",
            })

    families: dict[str, list[tuple[str, int, float]]] = {}
    for entry, colour in palette.items():
        if entry in NAMED:
            continue
        head, _, tail = entry.rpartition("-")
        if head and tail.isdigit():
            families.setdefault(head, []).append((entry, int(tail), luminance(colour)))
    for family, members in sorted(families.items()):
        ordered = sorted(members, key=lambda item: -item[2])
        numbers = [item[1] for item in ordered]
        if numbers != sorted(numbers):
            findings.append({"kind": "scale", "subject": family,
                             "detail": "a higher number must be darker"})

    for entry in sorted(set(palette) - used):
        findings.append({"kind": "reach", "subject": entry,
                         "detail": "no role points at it, so nothing can reach this colour"})

    findings.extend(drawing_bridge_findings(name))

    return {
        "theme": name,
        "findings": findings,
        "values": {**{f"palette.{k}": v for k, v in palette.items()},
                   **{role: value(role) for role in REQUIRED_ROLES}},
        "metrics": {"palette": len(palette), "roles": len([p for p in style.values
                                                           if p.startswith("color.")])},
    }


def check_all() -> dict[str, Any]:
    names = sorted(profiles())
    results = [check_scheme(name) for name in names]
    findings = [{"theme": result["theme"], **finding}
                for result in results for finding in result["findings"]]

    defaults = [name for name, body in profiles().items() if body.get("default")]
    if len(defaults) != 1:
        findings.append({
            "theme": "—", "kind": "default", "subject": "default",
            "detail": f"exactly one scheme must be marked default; found {defaults}",
        })
    return {"themes": names, "results": results, "findings": findings,
            "ok": not findings}


def render(report: dict[str, Any]) -> str:
    lines = ["Theme schemes", ""]
    for result in report["results"]:
        metrics = result["metrics"]
        status = "OK  " if not result["findings"] else "FAIL"
        lines.append(f"  {status} {result['theme']:<22} "
                     f"{metrics.get('palette', 0)} palette, {metrics.get('roles', 0)} roles, "
                     f"{len(result['findings'])} finding(s)")
    lines.append("")
    for finding in report["findings"]:
        lines.append(f"  {finding['kind'].upper():<9} {finding['theme']} · "
                     f"{finding['subject']}: {finding['detail']}")
    if report["ok"]:
        lines.append("  Every scheme clears the same bar.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme", default=None, help="check one scheme")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.theme:
        result = check_scheme(args.theme)
        report = {"themes": [args.theme], "results": [result],
                  "findings": [{"theme": args.theme, **f} for f in result["findings"]],
                  "ok": not result["findings"]}
    else:
        report = check_all()

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
