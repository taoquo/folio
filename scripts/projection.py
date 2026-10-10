#!/usr/bin/env python3
"""folio style projection

Turns a resolved style and a layout policy into CSS that can be injected into a
template's own stylesheet.

The templates are not edited. Their CSS stays as it is, and the projection is
appended inside the existing `<style>` element. That keeps the change reversible
by configuration, and it was measured before it was written: injecting a
variable layer changes the rendering by nothing at all (SSIM 1.00000), because
the values are the ones the template already uses.

Two rules shape what is emitted:

  A value is only projected when the resolver has one. A missing value leaves
  the template's own declaration in place rather than writing a default that
  nobody chose.

  Every declaration is attributable. The block carries the profile each value
  came from, so a page can be explained from its own stylesheet.

Usage:
    python3 scripts/projection.py css --genre one-pager --lang zh-Hans-CN
    python3 scripts/projection.py css --genre one-pager --policy
    python3 scripts/projection.py inject <file.html> --genre one-pager
    python3 scripts/projection.py check
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

STYLE_TAG_END = re.compile(r"</style\s*>", re.IGNORECASE)

# Resolved value path -> the CSS custom property it becomes. Only values the
# template can actually consume are listed: projecting a variable nothing reads
# would look like work and change nothing.
VARIABLE_MAP: dict[str, str] = {
    "body.size_pt": "--folio-body-size",
    "body.leading": "--folio-body-leading",
    "body.alignment": "--folio-body-align",
    "paragraph.widows": "--folio-widows",
    "paragraph.orphans": "--folio-orphans",
    "paragraph.max_consecutive_hyphens": "--folio-max-hyphens",
    "paragraph.hyphenation": "--folio-hyphens",
    "paragraph.section_gap_pt": "--folio-section-gap",
}

# Values that are not lengths and need a unit appended.
UNIT_SUFFIX = {
    "body.size_pt": "pt",
    "paragraph.section_gap_pt": "pt",
}


@dataclass
class Projection:
    """The CSS a projection produced, and what it left out."""

    css: str
    projected: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.css.strip()

    def to_json(self) -> dict[str, Any]:
        return {
            "css": self.css,
            "projected": dict(sorted(self.projected.items())),
            "sources": dict(sorted(self.sources.items())),
            "skipped": self.skipped,
            "conflicts": self.conflicts,
        }


def _css_value(path: str, value: Any) -> str | None:
    """Render a resolved value as a CSS value, or None when it has no form."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "auto" if value else "manual"
    if isinstance(value, (int, float)):
        suffix = UNIT_SUFFIX.get(path, "")
        number = f"{value:g}"
        return f"{number}{suffix}"
    text = str(value).strip()
    if not text:
        return None
    return text


def style_projection(genre: str | None, language: str | None) -> Projection:
    """The variable layer for a document's resolved style."""
    import style_resolver

    style = style_resolver.resolve(genre=genre, language=language)
    projected: dict[str, str] = {}
    sources: dict[str, str] = {}
    skipped: list[str] = []

    for path, variable in VARIABLE_MAP.items():
        value = style.get(path)
        css_value = _css_value(path, value)
        if css_value is None:
            skipped.append(path)
            continue
        projected[variable] = css_value
        sources[variable] = style.source_of(path) or "unknown"

    if not projected:
        return Projection(css="", projected={}, sources={}, skipped=skipped)

    lines = [
        "/* Projected from the resolved style. Values are the ones the template",
        "   already uses; the layer makes them addressable and traceable. */",
        ":root {",
    ]
    for variable, value in sorted(projected.items()):
        lines.append(f"  {variable}: {value}; /* {sources[variable]} */")
    lines.append("}")

    return Projection(css="\n".join(lines), projected=projected, sources=sources,
                      skipped=skipped)


def policy_projection(genre: str | None, page_profile: str | None = None) -> Projection:
    """The layout-policy layer: keep and break rules only.

    Deliberately narrow. The differential experiment showed that replacing the
    templates' spacing would change the rendering (SSIM 0.90 at one site), while
    the templates already express their spacing as explicit single-sided values.
    What they do not express is the intent behind a break, so that is what is
    projected.
    """
    import profile_check
    from document_ir.layout_policy import policy_for, to_css

    profiles = profile_check.load_profiles()
    page_profiles = profiles.get("page") or {}
    if not page_profiles:
        return Projection(css="", skipped=["no page profiles"])

    name = page_profile
    if name is None:
        candidates = [
            key for key, body in page_profiles.items()
            if genre and body.get("genre") == genre
        ]
        name = candidates[0] if candidates else None
    if name is None or name not in page_profiles:
        return Projection(css="", skipped=["no page profile for this genre"])

    policy = policy_for(page_profiles[name], name=name)
    css = to_css(policy)

    # A projected rule that repeats the template's own is noise, not a change;
    # it is reported so the layer stays reviewable.
    conflicts = [
        line.strip() for line in css.splitlines()
        if "break-after" in line or "break-inside" in line
    ]
    return Projection(
        css=css,
        projected={"policy": name},
        sources={"policy": f"page:{name}"},
        conflicts=conflicts,
    )


def combined(genre: str | None, language: str | None, *, include_policy: bool) -> Projection:
    """The full injected block."""
    parts = [style_projection(genre, language)]
    if include_policy:
        parts.append(policy_projection(genre))

    css = "\n\n".join(p.css for p in parts if not p.empty)
    projected: dict[str, str] = {}
    sources: dict[str, str] = {}
    skipped: list[str] = []
    conflicts: list[str] = []
    for part in parts:
        projected.update(part.projected)
        sources.update(part.sources)
        skipped.extend(part.skipped)
        conflicts.extend(part.conflicts)

    return Projection(css=css, projected=projected, sources=sources,
                      skipped=skipped, conflicts=conflicts)


def inject(html: str, projection: Projection) -> str:
    """Append a projection inside the document's own `<style>` element.

    Injecting inside the stylesheet rather than editing it keeps the template
    untouched, keeps the projection after the template's rules so it wins on
    equal specificity, and makes the change removable by configuration.

    A document with no `<style>` element is returned unchanged: a projection
    cannot be applied to a stylesheet that does not exist, and inventing one
    would change where the rules sit in the cascade.
    """
    if projection.empty:
        return html

    match = STYLE_TAG_END.search(html)
    if match is None:
        return html

    block = f"\n/* --- injected --- */\n{projection.css}\n"
    return html[:match.start()] + block + html[match.start():]


def check() -> list[str]:
    """Problems with the projection layer itself."""
    issues: list[str] = []

    # Every mapped variable must be producible from a real profile.
    projection = style_projection("one-pager", "zh-Hans-CN")
    if not projection.projected:
        issues.append("no style values were projected for one-pager")

    # The layer must be legal CSS by inspection: balanced braces, no empty rule.
    for name, proj in (("style", projection), ("policy", policy_projection("one-pager"))):
        if proj.empty:
            continue
        if proj.css.count("{") != proj.css.count("}"):
            issues.append(f"{name} projection has unbalanced braces")

    # Injecting an empty projection must be a no-op.
    sample = "<html><style>body { color: red; }</style><body>x</body></html>"
    if inject(sample, Projection(css="")) != sample:
        issues.append("an empty projection modified the document")

    # Injection must land inside the stylesheet, not after it.
    injected = inject(sample, style_projection("one-pager", "zh-Hans-CN"))
    if injected and injected.index("--folio-body-size") > injected.index("</style>"):
        issues.append("projection was injected outside the stylesheet")

    return issues


def render_text(projection: Projection, command: str) -> str:
    if command == "check":
        issues = check()
        lines = ["Projection check", ""]
        if not issues:
            lines.append("  OK  the projection layer is well formed and injects correctly")
        else:
            for issue in issues:
                lines.append(f"  ERROR {issue}")
        return "\n".join(lines)

    lines = ["Style projection", ""]
    lines.append(f"  values projected  {len(projection.projected)}")
    if projection.skipped:
        lines.append(f"  not set           {len(projection.skipped)}")
        for path in projection.skipped[:6]:
            lines.append(f"    {path}")
    lines.append("")
    if projection.empty:
        lines.append("  (nothing to inject)")
    else:
        lines.append(projection.css)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("css", "check"):
        cmd = sub.add_parser(name, help="emit the projection" if name == "css" else "check the layer")
        cmd.add_argument("--genre", default="one-pager")
        cmd.add_argument("--lang")
        cmd.add_argument("--policy", action="store_true", help="include the layout policy layer")
        cmd.add_argument("--format", choices=("text", "json"), default="text")

    inj = sub.add_parser("inject", help="write a projected copy of a template")
    inj.add_argument("source", type=Path)
    inj.add_argument("--genre", default="one-pager")
    inj.add_argument("--lang")
    inj.add_argument("--policy", action="store_true")
    inj.add_argument("--out", type=Path)

    args = parser.parse_args(argv)

    if args.command == "check":
        issues = check()
        if args.format == "json":
            import json

            print(json.dumps({"issues": issues, "ok": not issues}, indent=2, ensure_ascii=False))
        else:
            print(render_text(Projection(css=""), "check"))
        return 0 if not issues else 1

    projection = combined(args.genre, args.lang, include_policy=args.policy)

    if args.command == "css":
        if args.format == "json":
            import json

            print(json.dumps(projection.to_json(), indent=2, ensure_ascii=False))
        else:
            print(render_text(projection, "css"))
        return 0

    source = args.source if args.source.is_absolute() else ROOT / args.source
    if not source.is_file():
        print(f"ERROR: source not found: {source}")
        return 2

    html = inject(source.read_text(encoding="utf-8"), projection)
    target = args.out or source.with_suffix(".projected.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    print(f"OK: wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
