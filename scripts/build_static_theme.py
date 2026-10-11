#!/usr/bin/env python3
"""folio static theme build

Bakes a colour scheme into the pages a reader opens directly.

`index.html`, `index-zh.html` and `assets/demos/*.html` are served as they are:
a browser opens them, so there is no build step at view time and no profile to
read. Their colours have to be written in, and until now they were written in by
hand -- 105 literals in each homepage, and forty-odd in a demo -- which is why
`AGENTS.md` pitfall 8 had to ask a person to copy a diagram fix into two files.

This writes them from the theme, using `references/theme/template-literal-ledger.json`
to know what each literal means. The ledger is a record rather than a derivation
because the default theme is the thing being changed and cannot be its own
reference.

    python3 scripts/build_static_theme.py            # apply the selected theme
    python3 scripts/build_static_theme.py --check     # report only, change nothing
    FOLIO_THEME=other python3 scripts/build_static_theme.py

Replacing a value by its palette entry keeps one entry's value from being
confused with another's: `palette` holds each colour once, and a check enforces
that. Files that hold a colour no palette entry claims are left alone -- a demo
may carry its own.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

LEDGER = ROOT / "references" / "theme" / "template-literal-ledger.json"

# What was written into the static pages last time, by palette entry. The marker
# in each page names the theme; this records the values, which is what an
# in-place colour edit needs.
BAKE = ROOT / "references" / "theme" / "static-bake.json"

# The pages a reader opens rather than a renderer reads. `index.html` and
# `index-zh.html` are a translated pair, so they are treated together.
#
# Diagram templates and host fixtures are deliberately absent: `build.py`
# renders them, and the ledger retargets their literals at render time. Writing
# them here would duplicate that and break the ledger check, which asserts a
# recorded literal is still present in its template.
STATIC_SOURCES = (
    "index.html",
    "index-zh.html",
    "assets/demos",
)


MARKER = "<!-- folio-theme: {name} -->"
MARKER_PATTERN = re.compile(r"<!--\s*folio-theme:\s*([A-Za-z0-9._-]+)\s*-->")


def _style(theme: str | None):
    import style_resolver

    return style_resolver.resolve(names={"theme": theme} if theme else None)


def _default_name() -> str | None:
    import style_resolver

    return style_resolver.default_theme_name()


def _palette(style) -> dict[str, str]:
    out: dict[str, str] = {}
    for path, value in style.values.items():
        if path.startswith("palette.") and str(value.value).startswith("#"):
            out[path.split(".", 1)[1]] = str(value.value).upper()
    return out


def baked_theme(text: str) -> str | None:
    """The theme a page holds, from its marker. None means the default."""
    match = MARKER_PATTERN.search(text)
    return match.group(1) if match else None


def targets() -> list[Path]:
    """Every static page the ledger knows about."""
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    names: set[str] = set()
    for paths in (ledger.get("files") or {}).values():
        names.update(paths)
    out: list[Path] = []
    for name in sorted(names):
        if not any(name == source or name.startswith(f"{source}/") for source in STATIC_SOURCES):
            continue
        path = ROOT / name
        if path.is_file() and path.suffix.lower() in {".html", ".svg"}:
            out.append(path)
    return out


def read_bake() -> dict[str, Any]:
    if not BAKE.is_file():
        return {}
    try:
        return json.loads(BAKE.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover - a broken sidecar must not stop a build
        return {}


def substitution_for(target_theme: str | None) -> dict[str, str]:
    """Value -> value, per palette entry, from what is written to what is wanted.

    The reference is the sidecar when there is one, and the default theme's
    palette otherwise -- which is what the pages held before this existed.
    """
    recorded = (read_bake().get("palette") or {})
    source = recorded or _palette(_style(_default_name()))
    target = _palette(_style(target_theme))
    out: dict[str, str] = {}
    for entry, value in source.items():
        replacement = target.get(entry)
        if replacement and str(replacement).upper() != str(value).upper():
            out[str(value).upper()] = replacement
    return out


def apply(target_theme: str | None, check: bool = False) -> int:
    wanted = target_theme or _default_name()
    if not wanted:
        print("ERROR: no theme selected and none marked default")
        return 1

    substitution = substitution_for(wanted)
    changed = 0
    for path in targets():
        text = path.read_text(encoding="utf-8")
        held = baked_theme(text)
        touched = sum(len(re.findall(re.escape(value), text, flags=re.IGNORECASE))
                      for value in substitution)
        if held == wanted and not touched:
            continue
        if check:
            print(f"  {path.relative_to(ROOT)}  holds {held or '(default)'}, "
                  f"{touched} literal(s) behind {wanted}")
            changed += 1
            continue

        for value, replacement in substitution.items():
            text = re.sub(re.escape(value), replacement, text, flags=re.IGNORECASE)

        marker = MARKER.format(name=wanted)
        if MARKER_PATTERN.search(text):
            text = MARKER_PATTERN.sub(marker, text, count=1)
        else:
            # After the doctype, before anything a reader sees.
            # A doctype may be written in any case, and this repository has both.
            text = re.sub(r"(<!doctype html>[^\n]*\n)", rf"\1{marker}\n", text,
                          count=1, flags=re.IGNORECASE)
        path.write_text(text, encoding="utf-8")
        changed += 1
        print(f"  {path.relative_to(ROOT)}  {'would move' if check else 'moved'} "
              f"{(held or '(default)')} -> {wanted}  ({touched} literal(s))")

    if not check:
        BAKE.write_text(json.dumps({
            "note": (
                "The palette as last written into index.html, index-zh.html and "
                "assets/demos/*.html. A substitution is recorded value -> wanted "
                "value, per palette entry, which covers a scheme switch and an "
                "in-place colour edit alike."
            ),
            "theme": wanted,
            "palette": {k: v for k, v in sorted(_palette(_style(wanted)).items())},
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    verb = "differ" if check else "updated"
    print(f"\n  {changed} file(s) {verb}")
    return 1 if (check and changed) else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="report which files differ from the selected theme")
    parser.add_argument("--theme", default=None, help="a theme profile name")
    args = parser.parse_args(argv)

    import os

    theme = args.theme or (os.environ.get("FOLIO_THEME") or "").strip() or None
    return apply(theme, check=args.check)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
