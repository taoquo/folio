#!/usr/bin/env python3
"""folio diagnostic codes

Error codes are a public surface: a caller writes a check against one, a
dashboard groups by one, and a runbook says "when you see this, do that". So
they need one shape, one place they are declared, and a rule about renaming.

The repository has two shapes today. The validator writes `DOC.IR.ID.DUPLICATE`
and the asset checker writes `ASSET-MISSING`. Both are readable; together they
are not a convention.

The convention here follows the plan: an uppercase domain, a hyphen, then a
dotted path within that domain.

    DOC.IR.ID.DUPLICATE
    ASSET.ARTIFACT.MISSING
    LAYOUT.HEADING.ORPHANED

A code, once used outside this repository, is not renamed. A better name gets a
new code and the old one is listed as a replacement, because a renamed code
breaks every check that looked for it and the breakage is silent.

Usage:
    python3 scripts/diagnostics.py list
    python3 scripts/diagnostics.py check
    python3 scripts/diagnostics.py explain DOC.IR.ID.DUPLICATE
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# The domain prefixes the plan names, and what each one covers.
DOMAINS: dict[str, str] = {
    "DOC": "the semantic model, its structure and its references",
    "STYLE": "profile resolution and style values",
    "LAYOUT": "pagination, keep rules, overflow and space",
    "FONT": "missing glyphs, fallback and embedding",
    "ASSET": "figures, diagrams and their rendered files",
    "RENDER": "backend errors and capability mismatches",
    "A11Y": "accessible structure: headings, alternatives, reading order",
    "QA": "baselines, determinism and visual difference",
}

# The shape a code has to match: an uppercase domain, a hyphen, then a dotted
# path. Segments may contain an underscore so a two-word condition stays one
# segment, which keeps a category distinct from a condition.
CODE_PATTERN = re.compile(
    r"^(?P<domain>[A-Z][A-Z0-9]*)-(?P<path>[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*)*)$"
)

# Codes that were in use before the convention and are kept working. Each names
# what replaced it, so a caller can migrate without guessing.
LEGACY: dict[str, str] = {
    "DOC.IR.ASSET.MISSING": "DOC-ASSET.MISSING",
    "DOC.IR.CITE.UNKNOWN": "DOC-CITE.UNKNOWN",
    "DOC.IR.CONTENT.EMPTY": "DOC-CONTENT.EMPTY",
    "DOC.IR.FOOTNOTE.MISSING": "DOC-FOOTNOTE.MISSING",
    "DOC.IR.FOOTNOTE.ORPHAN": "DOC-FOOTNOTE.ORPHAN",
    "DOC.IR.HEADING.LEVEL": "DOC-HEADING.LEVEL",
    "DOC.IR.ID.COLLISION": "DOC-ID.COLLISION",
    "DOC.IR.ID.DUPLICATE": "DOC-ID.DUPLICATE",
    "DOC.IR.ID.INVALID": "DOC-ID.INVALID",
    "DOC.IR.ID.MISSING": "DOC-ID.MISSING",
    "DOC.IR.LANG.MISSING": "DOC-LANG.MISSING",
    "DOC.IR.RAWFALLBACK.EXCESSIVE": "DOC-FALLBACK.EXCESSIVE",
    "DOC.A11Y.MISSING_ALT": "A11Y-IMAGE.MISSING_ALT",
    "ASSET-MISSING": "ASSET-ARTIFACT.MISSING",
    "ASSET-CHANGED": "ASSET-ARTIFACT.CHANGED",
    "ASSET-NO-ARTIFACT": "ASSET-ARTIFACT.EMPTY",
    "ASSET-SOURCE-MISSING": "ASSET-SOURCE.MISSING",
    "DOC.IR.TITLE.MISSING": "DOC-TITLE.MISSING",
    "DOC.IR.TEXT.EMPTY": "DOC-TEXT.EMPTY",
    "DOC.IR.REF.EMPTY": "DOC-REF.EMPTY",
    "DOC.IR.REF.BROKEN": "DOC-REF.BROKEN",
    "DOC.A11Y.HEADING_SKIP": "A11Y-HEADING.SKIP",
    "DOC.IR.TABLE.NO_COLUMNS": "DOC-TABLE.NO_COLUMNS",
    "DOC.IR.TABLE.RAGGED": "DOC-TABLE.RAGGED",
    "DOC.IR.RAWFALLBACK.REASON": "DOC-FALLBACK.REASON",
    "DOC.IR.METADATA.MISSING": "DOC-METADATA.MISSING",
    "DOC.IR.BIBLIOGRAPHY.MISSING": "DOC-BIBLIOGRAPHY.MISSING",
    "DOC.IR.LIST.EMPTY": "DOC-LIST.EMPTY",
    "DOC.IR.SCHEMA.UNKNOWN": "DOC-SCHEMA.UNKNOWN",
    "ASSET-SOURCE-CHANGED": "ASSET-SOURCE.CHANGED",
}


@dataclass
class Finding:
    """One code that does not follow the convention."""

    code: str
    file: str
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "file": self.file, "reason": self.reason}


@dataclass
class CodeInventory:
    """Every code the repository emits."""

    by_domain: dict[str, list[str]] = field(default_factory=dict)
    off_convention: list[Finding] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.by_domain.values())

    def to_json(self) -> dict[str, Any]:
        return {
            "domains": {k: sorted(set(v)) for k, v in sorted(self.by_domain.items())},
            "total": self.total,
            "off_convention": [f.to_json() for f in self.off_convention],
        }


def conforms(code: str) -> bool:
    return bool(CODE_PATTERN.match(code))


def replaced_by(code: str) -> str | None:
    return LEGACY.get(code)


def scan() -> CodeInventory:
    """Find every diagnostic code the repository writes.

    A code is recognised by its shape rather than by where it is used, so a new
    module is covered without being added to a list.
    """
    inventory = CodeInventory()
    pattern = re.compile(r'"([A-Z][A-Z0-9]*(?:[-.][A-Z0-9_.]+)+)"')

    for path in sorted((ROOT / "scripts").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        # This module declares the legacy mapping; scanning it would report the
        # declaration itself as a misuse.
        if path.name == "diagnostics.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in pattern.finditer(text):
            code = match.group(1)
            # Skip values that are clearly not diagnostics.
            if code.startswith(("UTF", "ISO", "RFC", "HTTP", "PDF", "PNG", "SVG")):
                continue
            if len(code) < 6 or code.count(".") + code.count("-") == 0:
                continue

            domain = code.split("-", 1)[0].split(".", 1)[0]
            if domain not in DOMAINS:
                continue

            inventory.by_domain.setdefault(domain, []).append(code)
            if not conforms(code) and code not in LEGACY:
                inventory.off_convention.append(
                    Finding(code=code, file=str(path.relative_to(ROOT)),
                            reason="does not match DOMAIN-PATH; see this module")
                )
            elif code in LEGACY:
                inventory.off_convention.append(
                    Finding(code=code, file=str(path.relative_to(ROOT)),
                            reason=f"legacy spelling; use {LEGACY[code]}")
                )
    return inventory


def explain(code: str) -> dict[str, Any]:
    """What a code means, and whether it should be spelled differently."""
    domain = code.split("-", 1)[0].split(".", 1)[0]
    return {
        "code": code,
        "domain": domain,
        "domain_meaning": DOMAINS.get(domain, "unknown domain"),
        "conforms": conforms(code),
        "replaced_by": replaced_by(code),
        "note": (
            "Once a code is used outside this repository it is not renamed; a "
            "better name is added and the old one is kept as a replacement."
        ),
    }


def render_text(inventory: CodeInventory) -> str:
    lines = ["Diagnostic codes", ""]
    lines.append(f"  {'domain':<10} {'codes':>6}  meaning")
    lines.append("  " + "-" * 62)
    for domain, meaning in DOMAINS.items():
        count = len(set(inventory.by_domain.get(domain, [])))
        lines.append(f"  {domain:<10} {count:>6}  {meaning[:44]}")

    lines.append("")
    lines.append(f"  {inventory.total} code reference(s) across {len(inventory.by_domain)} domain(s)")

    if inventory.off_convention:
        lines.append("")
        lines.append(f"  {len(inventory.off_convention)} code(s) do not follow the convention:")
        for finding in inventory.off_convention[:12]:
            lines.append(f"    {finding.code}")
            lines.append(f"      {finding.reason}")
    else:
        lines.append("")
        lines.append("  Every code follows DOMAIN-PATH.")

    lines.append("")
    lines.append("  A code is a public surface. It is not renamed once it is used")
    lines.append("  outside the repository, because a rename breaks checks silently.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="every code, by domain")
    listing.add_argument("--format", choices=("text", "json"), default="text")

    check = sub.add_parser("check", help="report codes that break the convention")
    check.add_argument("--format", choices=("text", "json"), default="text")

    exp = sub.add_parser("explain", help="what one code means")
    exp.add_argument("code")

    args = parser.parse_args(argv)

    if args.command == "explain":
        print(json.dumps(explain(args.code), indent=2, ensure_ascii=False))
        return 0

    inventory = scan()
    if args.format == "json":
        print(json.dumps(inventory.to_json(), indent=2, ensure_ascii=False))
    else:
        print(render_text(inventory))

    if args.command == "check":
        return 1 if inventory.off_convention else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
