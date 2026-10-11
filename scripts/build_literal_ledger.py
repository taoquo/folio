#!/usr/bin/env python3
"""folio template-literal ledger

Records which palette entry each hand-written colour literal stands for.

Some markup paints a colour rather than reading a variable: a diagram template
states `fill="#B83D2E"` in an SVG attribute, a document template draws its chart
the same way, and the homepage stylesheet declares its canvas in `:root`.
Measured: this renderer ignores a CSS rule that would override a presentation
attribute and does not resolve `var()` inside one, so the literal has to be
replaced in the markup.

The map is recorded rather than derived, because the default theme is the thing
being changed and cannot be its own reference. Entries disappear as templates are
converted to variables; `color_sources.py check` fails when a recorded literal is
no longer in the file it came from, so the ledger cannot quietly rot.

    python3 scripts/build_literal_ledger.py
    python3 scripts/build_literal_ledger.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

LEDGER = ROOT / "references" / "theme" / "template-literal-ledger.json"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")

# Markup and stylesheets a reader or a renderer opens directly. `generated` holds
# rebuilt artifacts, whose colours come from their templates rather than being
# authored, so it is skipped.
DIRECTORIES = (
    "assets/templates", "assets/diagrams", "assets/demos", "references/fixtures/hosting",
    "index.html", "index-zh.html", "styles.css",
)
SUFFIXES = {".html", ".svg", ".css"}
SKIP_PARTS = {"generated", "__pycache__"}


def palette() -> dict[str, str]:
    import yaml

    path = ROOT / "references" / "profiles" / "theme" / "folio-classic-v1.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    bodies = data.get("profiles") or {}
    default = next((body for body in bodies.values() if body.get("default")), None)
    if default is None:
        default = next(iter(bodies.values()), {})
    return {name: str(value).upper() for name, value in (default.get("palette") or {}).items()}


ORDER = ("color.text.", "color.surface.", "color.accent.", "color.border.",
         "color.status.", "color.series.")


def role_for(value: str, style) -> str | None:
    """The role a colour means, where a scheme-independent one exists.

    Several roles can share a value; the preference order picks the semantic
    meaning rather than, say, a chart slot that happens to hold the same colour.
    """
    candidates = [path for path, entry in style.values.items()
                  if path.startswith("color.") and str(entry.value).upper() == value.upper()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda path: next(
        (index for index, prefix in enumerate(ORDER) if path.startswith(prefix)), 99))[0]


def scan() -> dict:
    import style_resolver

    profile = palette()
    by_value = {value: name for name, value in profile.items()}
    style = style_resolver.resolve()
    shipped: dict[str, dict] = {}
    unmatched: dict[str, list[str]] = {}

    for target in DIRECTORIES:
        path = ROOT / target
        paths = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        for candidate in paths:
            if candidate.suffix.lower() not in SUFFIXES:
                continue
            if SKIP_PARTS & set(candidate.parts):
                continue
            relative = str(candidate.relative_to(ROOT))
            text = candidate.read_text(encoding="utf-8", errors="ignore")
            for value in sorted({h.upper() for h in HEX.findall(text)}):
                if value in by_value:
                    body = shipped.setdefault(
                        value,
                        {"target": role_for(value, style) or f"palette:{by_value[value]}",
                         "files": []},
                    )
                    body["files"].append(relative)
                else:
                    unmatched.setdefault(value, []).append(relative)

    return {
        "shipped": {value: body["target"] for value, body in sorted(shipped.items())},
        "files": {value: sorted(set(body["files"])) for value, body in sorted(shipped.items())},
        "unmatched": {value: sorted(set(paths)) for value, paths in sorted(unmatched.items())},
    }


def write(ledger: dict) -> None:
    LEDGER.write_text(json.dumps({
        "note": (
            "What each hand-written colour literal in a pre-palette template means. "
            "A target is a role path (`color.text.secondary`), which every scheme "
            "defines, or `palette:<name>` for a colour no scheme defines -- a chart's "
            "up-candle green, say. Recorded rather than derived: the default scheme is "
            "the thing being changed, so its values cannot serve as the reference. "
            "Entries disappear as templates are converted to variables."
        ),
        **ledger,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    parser.add_argument("--check", action="store_true",
                        help="fail when the ledger is behind; write nothing")
    args = parser.parse_args(argv)

    ledger = scan()

    if args.check:
        # A literal the ledger has not recorded is one that silently stops
        # following a colour scheme: the substitution has nothing to map it by.
        # Nothing else catches that, so the ledger is compared to a fresh scan.
        if not LEDGER.is_file():
            print(f"ERROR: {LEDGER.relative_to(ROOT)}: missing")
            return 1
        recorded = json.loads(LEDGER.read_text(encoding="utf-8"))
        if recorded.get("shipped") != ledger["shipped"]:
            added = sorted(set(ledger["shipped"]) - set(recorded.get("shipped") or {}))
            removed = sorted(set(recorded.get("shipped") or {}) - set(ledger["shipped"]))
            if added:
                print(f"ERROR: {len(added)} literal(s) are in a template and not in the ledger: "
                      f"{', '.join(added[:6])}")
            if removed:
                print(f"ERROR: {len(removed)} recorded literal(s) are no longer in any template: "
                      f"{', '.join(removed[:6])}")
            return 1
        print(f"OK: the ledger records all {len(ledger['shipped'])} literal(s)")
        return 0
    if args.format == "json":
        print(json.dumps(ledger, indent=2, ensure_ascii=False))
    else:
        roles = sum(1 for target in ledger["shipped"].values() if target.startswith("color."))
        print(f"  {len(ledger['shipped'])} literal(s) mapped: {roles} to a role, "
              f"{len(ledger['shipped']) - roles} to a palette entry")
        print(f"  {len(ledger['unmatched'])} literal(s) belong to no entry")
        for value, paths in sorted(ledger["unmatched"].items()):
            print(f"    {value}  {len(paths)} file(s)")
        if not args.dry_run:
            write(ledger)
            print(f"OK: wrote {LEDGER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
