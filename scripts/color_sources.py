#!/usr/bin/env python3
"""folio colour source check

Colour is declared in four places: the templates' `:root` blocks, the token
table, the theme profile and the drawing theme. They agree today because someone
kept them in step, and the survey found one name that had quietly stopped
meaning the same thing -- `stone` was `#85776F` in the document theme and
`#74665F` in the drawing theme.

This checks the connections rather than the values. A theme that changes a
colour should change it everywhere, and a name that means two things should be
two names.

The check reports rather than gates on the values themselves: a drawing theme
may legitimately hold a colour the document theme does not, and saying which is
a judgement. What it will not accept is two sources disagreeing about one name.

Usage:
    python3 scripts/color_sources.py check
    python3 scripts/color_sources.py inventory
    python3 scripts/color_sources.py check --format json
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

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")

# The name each source uses for one meaning. A mismatch here is the failure the
# survey found: two spellings of the same idea that drifted apart.
# A meaning both themes must agree on: the document role, and the drawing
# theme's name for it. The drawing theme is a twelve-token swap unit and keeps
# its own field names, so the mapping is stated rather than derived.
SHARED = {
    "surface.page": "parchment",
    "surface.card": "ivory",
    "text.primary": "near_black",
    "text.muted": "stone",
    "text.secondary": "olive",
    "accent.brand": "brand",
    "accent.tint": "brand_tint",
    "border.default": "border",
}


@dataclass
class Finding:
    subject: str
    detail: str
    severity: str = "error"

    def to_json(self) -> dict[str, Any]:
        return {"subject": self.subject, "detail": self.detail, "severity": self.severity}


@dataclass
class Report:
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not [f for f in self.findings if f.severity == "error"]

    def to_json(self) -> dict[str, Any]:
        return {
            "sources": {k: len(v) for k, v in sorted(self.sources.items())},
            "findings": [f.to_json() for f in self.findings],
            "ok": self.ok,
        }


def _template_declarations() -> dict[str, str]:
    """Every colour a template declares, keyed by its variable name."""
    out: dict[str, str] = {}
    for path in sorted((ROOT / "assets" / "templates").glob("*.html")):
        text = path.read_text(encoding="utf-8")
        marker = re.search(r":root\s*\{", text)
        if not marker:
            continue
        end = text.index("}", marker.end())
        block = text[marker.end():end]
        for name, value in re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})", block):
            out.setdefault(name, value.upper())
    return out


def _theme_declarations() -> dict[str, str]:
    """The theme profile's colours, through the resolver."""
    import style_resolver

    style = style_resolver.resolve(genre="one-pager")
    out: dict[str, str] = {}
    for key, resolved in style.values.items():
        if resolved.value and HEX.fullmatch(str(resolved.value)):
            out[key] = str(resolved.value).upper()
    return out


def _drawing_declarations() -> dict[str, str]:
    """The drawing theme's colours, by field name."""
    import dataclasses

    from drawing.theme.folio import DEFAULT_FOLIO_THEME

    out: dict[str, str] = {}
    for f in dataclasses.fields(DEFAULT_FOLIO_THEME):
        value = getattr(DEFAULT_FOLIO_THEME, f.name)
        if isinstance(value, str) and HEX.fullmatch(value):
            out[f.name] = value.upper()
    return out


def _token_declarations() -> dict[str, str]:
    path = ROOT / "references" / "tokens.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k.lstrip("-").replace("-", "_"): str(v).upper() for k, v in data.items()}


def check() -> Report:
    report = Report()
    report.sources = {
        "template": _template_declarations(),
        "theme": _theme_declarations(),
        "drawing": _drawing_declarations(),
        "tokens": _token_declarations(),
    }

    theme, drawing, tokens = (report.sources["theme"], report.sources["drawing"],
                              report.sources["tokens"])

    # A meaning shared by two sources must have one value.
    for theme_name, drawing_name in SHARED.items():
        tv = theme.get(f"color.{theme_name}")
        dv = drawing.get(drawing_name)
        if tv and dv and tv != dv:
            report.findings.append(Finding(
                subject=f"{drawing_name}",
                detail=(
                    f"the document theme calls it {tv} and the drawing theme "
                    f"{dv}; one meaning needs one value, or two names"
                ),
            ))

    # The token table exists to be the single list; a value it does not carry is
    # a value no consumer of the table can reach.
    for name, value in sorted(tokens.items()):
        if value not in set(theme.values()) | set(drawing.values()):
            report.findings.append(Finding(
                subject=str(name),
                detail=f"the token table declares {value}, which no theme carries",
                severity="warning",
            ))

    report.findings.extend(ledger_findings())
    return report


def ledger_findings() -> list[Finding]:
    """Problems with the record of what a template literal means.

    The ledger is recorded rather than derived, because the default theme cannot
    be its own reference while it is the thing being changed. That makes it
    rot-able in two ways: a palette entry it names could be renamed, or a
    template could be edited so the literal it records is gone. Both are checked,
    so the bridge cannot quietly stop substituting.
    """
    import yaml

    ledger_path = ROOT / "references" / "theme" / "template-literal-ledger.json"
    if not ledger_path.is_file():
        return [Finding("template-literal-ledger.json", "missing", severity="warning")]

    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    shipped = ledger.get("shipped") or {}
    files = ledger.get("files") or {}

    profile_path = ROOT / "references" / "profiles" / "theme" / "folio-classic-v1.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    bodies = (profile.get("profiles") or {})
    default = next((body for body in bodies.values() if body.get("default")), None)
    palette = set((default or {}).get("palette") or {})

    findings: list[Finding] = []
    for literal, entry in sorted(shipped.items()):
        if entry not in palette:
            findings.append(Finding(
                literal,
                f"the ledger points at palette.{entry}, which no longer exists",
            ))
        for name in files.get(literal, []):
            path = ROOT / name
            if not path.is_file():
                findings.append(Finding(literal, f"recorded file is gone: {name}"))
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").upper()
            if literal.upper() not in text:
                findings.append(Finding(
                    literal,
                    f"{name} no longer contains it; the template was converted or edited",
                ))
    return findings


def inventory() -> dict[str, Any]:
    report = Report()
    report.sources = {
        "template": _template_declarations(),
        "theme": _theme_declarations(),
        "drawing": _drawing_declarations(),
        "tokens": _token_declarations(),
    }

    by_value: dict[str, list[str]] = {}
    for source, values in report.sources.items():
        for name, value in values.items():
            by_value.setdefault(value, []).append(f"{source}:{name}")

    return {
        "counts": {k: len(v) for k, v in sorted(report.sources.items())},
        "shared": {v: names for v, names in sorted(by_value.items()) if len(names) > 1},
        "single_source": {v: names[0] for v, names in sorted(by_value.items()) if len(names) == 1},
    }


def render_check(report: Report) -> str:
    lines = ["Colour sources", ""]
    for source, values in sorted(report.sources.items()):
        lines.append(f"  {source:<12} {len(values):>4} colour(s)")
    lines.append("")
    if report.findings:
        for finding in report.findings:
            mark = "ERROR" if finding.severity == "error" else "WARN "
            lines.append(f"  {mark} {finding.subject}")
            lines.append(f"        {finding.detail}")
    else:
        lines.append("  Every meaning shared by two sources has one value.")
    lines.append("")
    lines.append("  A source may hold a colour another does not: a diagram label and")
    lines.append("  a body colour are different jobs. What is not allowed is two")
    lines.append("  sources disagreeing about one name.")
    return "\n".join(lines)


def render_inventory(payload: dict[str, Any]) -> str:
    lines = ["Colour inventory", ""]
    for source, count in payload["counts"].items():
        lines.append(f"  {source:<12} {count:>4}")
    lines.append("")
    lines.append(f"  values in 2+ sources   {len(payload['shared'])}")
    lines.append(f"  values in 1 source     {len(payload['single_source'])}")
    lines.append("")
    lines.append("  Values only one source carries:")
    for value, owner in list(payload["single_source"].items())[:10]:
        lines.append(f"    {value}  {owner}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "inventory"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.command == "inventory":
        payload = inventory()
        if args.format == "json":
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(render_inventory(payload))
        return 0

    report = check()
    if args.format == "json":
        print(json.dumps(report.to_json(), indent=2, ensure_ascii=False))
    else:
        print(render_check(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
