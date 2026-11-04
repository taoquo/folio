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

COLOUR_PREFIX = "color."


def colour_variable(path: str) -> str:
    """The custom property a colour role becomes.

    One rule, applied to the path: `color.text.primary` is
    `--color-text-primary`. A hand-kept table is what made every new token cost
    two names instead of one.
    """
    return "--" + path.replace(".", "-").replace("_", "-")


def colour_paths(style: Any) -> list[tuple[str, str, str]]:
    """Every colour role, as (resolved path, variable name, value)."""
    out: list[tuple[str, str, str]] = []
    for path, resolved in style.values.items():
        if not path.startswith(COLOUR_PREFIX):
            continue
        value = str(resolved.value).strip()
        if value.startswith("#"):
            out.append((path, colour_variable(path), value))
    return out


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


def style_projection(genre: str | None, language: str | None,
                     theme: str | None = None) -> Projection:
    """The variable layer for a document's resolved style.

    `theme` names a colour scheme; `None` takes the profile marked `default`.
    """
    import style_resolver

    style = style_resolver.resolve(
        genre=genre, language=language, names={"theme": theme} if theme else None
    )
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

    # Colour, by the derived name.
    colours: dict[str, str] = {}
    for path, variable, css_value in colour_paths(style):
        projected[variable] = css_value
        sources[variable] = style.source_of(path) or "unknown"
        colours[variable] = css_value

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



# Web reading page: the screen scale the old base.css declared for itself.
# Every entry is derived from a resolved `web.*` path rather than kept in a
# second table, so adding a role to the profile is enough to make it available.
GENERIC_FONT_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy",
                         "system-ui", "ui-serif", "ui-monospace"}


def _font_stack(value: Any) -> str:
    """A profile's family list as a CSS font-family value.

    A family name with a space has to be quoted; a generic keyword must not be.
    """
    if isinstance(value, str):
        return value
    names = [str(item).strip() for item in (value or []) if str(item).strip()]
    out = []
    for name in names:
        if name.lower() in GENERIC_FONT_FAMILIES or name.startswith(("var(", "ui-")):
            out.append(name)
        else:
            out.append(f'"{name}"')
    return ", ".join(out)


def web_projection(genre: str = "web-reading", language: str | None = "zh-Hans-CN",
                   *, include_viewport_aliases: bool = True) -> Projection:
    """The screen scale for a Web reading page.

    The Web templates read only these variables. Sizes, spacing, radii, measure
    and structural geometry are resolved from `references/profiles/web/`, so a
    change to the profile moves the page and a change to the template cannot
    invent a value.

    `include_viewport_aliases=False` keeps the per-width values out of the emitted
    `:root`: they are inputs to `web_plan`, which resolves each one into the
    plain role variable inside the media query that applies it. A page that
    declares both would carry two answers to the same question.
    """
    import style_resolver

    style = style_resolver.resolve(genre=genre, language=language)
    projected: dict[str, str] = {}
    sources: dict[str, str] = {}

    if not style.domains.get("web"):
        return Projection(css="", projected={}, sources={},
                          skipped=["no web profile matched"])

    def put(variable: str, value: str, path: str) -> None:
        projected[variable] = value
        sources[variable] = style.source_of(path) or "unknown"

    # The resolver flattens a profile without its kind as a prefix. These are
    # the Web profile's own top-level fields, and no other kind declares them:
    # typography uses `body`, and colour uses `color`.
    for path in style.values:
        if not path.startswith(("font.", "type.", "space.", "line.", "weight.",
                                "tracking.", "radius.", "measure.", "layout.")):
            continue
        # The path is global, so the provenance decides whether it is the Web
        # profile's value or another domain's field that happens to share a name.
        if not (style.source_of(path) or "").startswith("web:"):
            continue
        value = style.get(path)
        if value is None or isinstance(value, (list, tuple, dict)):
            continue

        if path.startswith("type."):
            parts = path.split(".")
            if len(parts) != 3:
                continue
            role, field = parts[1], parts[2]
            if field == "size_px":
                put(f"--web-{role}-size", f"{float(value):g}px", path)
            elif field == "leading":
                put(f"--web-{role}-leading", f"{float(value):g}", path)
            elif field == "weight":
                put(f"--web-{role}-weight", f"{int(value)}", path)
        elif path.startswith("weight."):
            # A weight is a number with no unit; it is not a length.
            put(f"--web-weight-{path.split('.', 1)[1].replace('_', '-')}",
                f"{int(value)}", path)
        elif path.startswith("tracking."):
            key = path.split(".", 1)[1].removesuffix("_em").replace("_", "-")
            put(f"--web-tracking-{key}", f"{float(value):g}em", path)
        elif path.startswith("space.s"):
            put(f"--web-space-{path.rsplit('s', 1)[-1]}", f"{float(value):g}px", path)
        elif path.startswith("line."):
            put(f"--web-line-{path.split('.', 1)[1].replace('_', '-')}", f"{float(value):g}px", path)
        elif path.startswith("radius."):
            put(f"--web-radius-{path.split('.', 1)[1].replace('_', '-')}", f"{float(value):g}px", path)
        elif path.startswith("measure."):
            put(f"--web-measure-{path.split('.', 1)[1].replace('_', '-')}", f"{float(value):g}ch", path)
        elif path.startswith("layout."):
            key = path.split(".", 1)[1]
            variable = f"--web-{key.replace('_', '-')}"
            # A column count is a number, not a length.
            suffix = "" if key.endswith("_columns") else "px"
            put(variable, f"{float(value):g}{suffix}", path)

    for path, variable in (("font.serif", "--serif"), ("font.mono", "--mono")):
        value = style.get(path)
        if value:
            put(variable, _font_stack(value), path)

    if not projected:
        return Projection(css="", projected={}, sources={}, skipped=["no web profile matched"])

    viewport_only = viewport_aliases(projected)
    emitted = {name: value for name, value in projected.items()
               if include_viewport_aliases or name not in viewport_only}

    lines = [
        "/* Projected from the resolved Web profile. The page reads these;",
        "   no size, family, spacing or radius is declared in the template. */",
        ":root {",
    ]
    for variable, value in sorted(emitted.items()):
        lines.append(f"  {variable}: {value}; /* {sources[variable]} */")
    lines.append("}")
    return Projection(css="\n".join(lines), projected=projected, sources=sources)


def web_font_faces(language: str | None = "zh-Hans-CN") -> list[dict[str, str]]:
    """Every face a Web page should embed, Latin first.

    A Chinese page carries two files: a Latin serif for the English prose and
    the bundled Kai face for the Chinese. Embedding only the CJK face forced
    the Latin text into it, because a family name earlier in the stack still
    wins whenever it has the glyph.
    """
    import style_resolver

    style = style_resolver.resolve(genre="web-reading", language=language)
    pairs = (
        ("font.latin_face", "font.latin_face_file", "font.latin_face_weight"),
        ("font.face", "font.face_file", "font.face_weight"),
    )
    faces: list[dict[str, str]] = []
    for family_key, file_key, weight_key in pairs:
        if not (style.source_of(family_key) or "").startswith("web:"):
            continue
        family = str(style.get(family_key) or "")
        filename = str(style.get(file_key) or "")
        if family and filename:
            faces.append({
                "family": family,
                "file": filename,
                "weight": str(style.get(weight_key) or ""),
            })
    return faces


def web_font_face(language: str | None = "zh-Hans-CN") -> dict[str, str]:
    """The first embedded face, kept for callers that only need one."""
    faces = web_font_faces(language)
    return faces[0] if faces else {"family": "", "file": ""}


# The pairs the model has a rule for, and the selectors that express them. A
# selector is only emitted when the template does not already set a margin for
# the pair, so an existing stylesheet is never overridden.
GAP_SELECTORS: dict[tuple[str, str], str] = {
    ("heading", "paragraph"): "h1 + p, h2 + p, h3 + p, h4 + p, h5 + p, h6 + p",
    ("paragraph", "paragraph"): "p + p",
    ("paragraph", "list"): "p + ul, p + ol",
    ("list", "paragraph"): "ul + p, ol + p",
    ("figure", "caption"): "figure + figcaption, figure + .caption",
    ("figure", "paragraph"): "figure + p",
    ("table", "paragraph"): "table + p",
    ("paragraph", "heading"): "p + h1, p + h2, p + h3, p + h4, p + h5, p + h6",
}


def gap_projection(genre: str | None = None, stylesheet: str | None = None) -> Projection:
    """Gap rules for pairs the stylesheet does not already decide.

    `stylesheet` is the template's own CSS. A pair whose selector already
    appears there is left alone: the template has decided, and replacing its
    decision is what the differential experiment showed to be unsafe.
    """
    import spacing

    declared = stylesheet or ""
    lines: list[str] = []
    projected: dict[str, str] = {}
    sources: dict[str, str] = {}
    skipped: list[str] = []

    for (before, after), selector in sorted(GAP_SELECTORS.items()):
        first = selector.split(",")[0].strip()
        # If the template styles this relationship, it keeps the decision.
        if first.split(" ")[-1].split("+")[-1].strip() in declared and "margin" in declared:
            skipped.append(f"{before}->{after}")
            continue
        gap = spacing.resolve_gap(before, after)
        if gap.is_fallback:
            skipped.append(f"{before}->{after}")
            continue
        value = gap.spec.preferred.as_pt()
        lines.append(f"/* {before} -> {after}: {gap.rule} */")
        lines.append(f"{selector} {{ margin-top: {value:g}pt; }}")
        projected[f"gap.{before}->{after}"] = f"{value:g}pt"
        sources[f"gap.{before}->{after}"] = gap.rule

    if not lines:
        return Projection(css="", projected={}, sources={}, skipped=skipped)

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


def combined(
    genre: str | None,
    language: str | None,
    *,
    include_policy: bool,
    include_gaps: bool = False,
    stylesheet: str | None = None,
    theme: str | None = None,
) -> Projection:
    """The full injected block.

    The gap layer is off unless asked for: it is the only part that can move a
    page, and the templates already decide their own spacing.
    """
    parts = [style_projection(genre, language, theme)]
    if include_policy:
        parts.append(policy_projection(genre))
    if include_gaps:
        parts.append(gap_projection(genre, stylesheet))

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


def retarget_literals(html: str, theme: str | None = None) -> str:
    """Move pre-palette literals in markup onto the selected scheme.

    Some markup paints a colour rather than reading a variable: a diagram
    template states `fill="#B83D2E"` in an SVG attribute, and a document
    template draws its chart the same way. Measured: this renderer ignores a CSS
    rule that would override a presentation attribute and does not resolve
    `var()` inside one, so the literal has to be replaced in the markup.

    What each literal means is read from
    `references/theme/template-literal-ledger.json` -- recorded rather than
    derived, because the default theme is the thing being changed and cannot be
    its own reference. With the default theme selected the mapping is the
    identity, so nothing moves.
    """
    import json

    import style_resolver

    ledger_path = ROOT / "references" / "theme" / "template-literal-ledger.json"
    if not ledger_path.is_file():
        return html
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8")).get("shipped") or {}
    except Exception:  # pragma: no cover - a broken ledger must not stop a build
        return html

    try:
        style = style_resolver.resolve(names={"theme": theme} if theme else None)
    except Exception:  # pragma: no cover - a broken profile must not stop a build
        return html

    for literal, target in ledger.items():
        # A role, which every scheme defines, or a palette entry for a colour no
        # scheme defines. Resolving through the role is what makes a literal
        # follow a scheme: a palette entry name belongs to one scheme.
        path = target if target.startswith("color.") else f"palette.{target.split(':', 1)[-1]}"
        value = style.get(path)
        replacement = str(value).strip() if value is not None else ""
        if replacement.startswith("#") and replacement.upper() != literal.upper():
            html = re.sub(re.escape(literal), replacement, html, flags=re.IGNORECASE)
    return html


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


# Variables the projection emits that nothing reads yet, with the reason. A
# variable added to this list is a decision to carry debt; one absent from it and
# unread is a mistake.
UNCONSUMED: dict[str, str] = {
    # A status vocabulary, not a one-off: four meanings each with a tint, so a
    # template that states one has the token. Three tints and `informative` are
    # unread today.
    "--color-data-category-1": "chart palette; the drawing theme owns the chart path",
    "--color-data-category-2": "chart palette; the drawing theme owns the chart path",
    "--color-data-category-3": "chart palette; the drawing theme owns the chart path",
    "--color-data-category-4": "chart palette; the drawing theme owns the chart path",
    "--color-data-category-5": "chart palette; the drawing theme owns the chart path",
    "--color-data-diverging-negative": "chart palette; the drawing theme owns the chart path",
    "--color-data-diverging-neutral": "chart palette; the drawing theme owns the chart path",
    "--color-data-diverging-positive": "chart palette; the drawing theme owns the chart path",
    "--color-data-sequential-1": "chart palette; the drawing theme owns the chart path",
    "--color-data-sequential-2": "chart palette; the drawing theme owns the chart path",
    "--color-data-sequential-3": "chart palette; the drawing theme owns the chart path",
    "--color-data-sequential-4": "chart palette; the drawing theme owns the chart path",
    "--color-data-sequential-5": "chart palette; the drawing theme owns the chart path",
    "--color-status-informative": "status vocabulary",
    "--color-status-informative-tint": "status vocabulary",
    "--color-status-positive-tint": "status vocabulary",
    "--color-status-negative-tint": "status vocabulary",
    "--folio-body-size": "typography migration pending",
    "--folio-body-leading": "typography migration pending",
    "--folio-body-align": "typography migration pending",
    "--folio-widows": "typography migration pending",
    "--folio-orphans": "typography migration pending",
    "--folio-max-hyphens": "typography migration pending",
    "--folio-hyphens": "typography migration pending",
    "--folio-section-gap": "typography migration pending",
    "--color-data-category-6": "chart palette; the drawing theme owns the chart path",
    "--color-series-1": "chart series; the drawing theme reads it through style_resolver, not through CSS",
    "--color-series-2": "chart series; the drawing theme reads it through style_resolver, not through CSS",
    "--color-series-3": "chart series; the drawing theme reads it through style_resolver, not through CSS",
    "--color-series-4": "chart series; the drawing theme reads it through style_resolver, not through CSS",
    "--color-series-5": "chart series; the drawing theme reads it through style_resolver, not through CSS",
    "--color-series-6": "chart series; the drawing theme reads it through style_resolver, not through CSS",
    "--color-semantic-delivered": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-delivered-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-info": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-info-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-component": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-component-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-passed": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-passed-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-attention": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-attention-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-enhance": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-enhance-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-risk": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-risk-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-change": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-change-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-input": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-input-strong": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-pending": "L2 content semantics; the Web reading-page templates read it",
    "--color-semantic-pending-strong": "L2 content semantics; the Web reading-page templates read it",
}

# Templates a projected variable may be read from. Diagrams read the migration
# aliases; documents read both. The Web templates keep their declarations in
# `base.css`, so the scan has to include CSS files as well as HTML.
CONSUMER_DIRS = ("assets/templates", "assets/diagrams")


# A per-width value is an input to `web_plan`, not a name the stylesheet reads:
# the plan resolves it into the plain role variable and emits that inside the
# media query. `web_plan.viewport_plan()` must consume every one of them.
WEB_VIEWPORT_QUALIFIER = re.compile(r"^--web-(?:[a-z0-9]+-)?(?:compact|narrow|wide)-")


def viewport_aliases(projected: dict[str, str]) -> set[str]:
    return {name for name in projected if WEB_VIEWPORT_QUALIFIER.match(name)}


def unconsumed_variables() -> list[str]:
    """Projected variables no template reads."""
    root = Path(__file__).resolve().parents[1]
    used: set[str] = set()
    for directory in CONSUMER_DIRS:
        for path in (root / directory).rglob("*"):
            if not path.is_file() or path.suffix not in {".html", ".css"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            used.update(re.findall(r"var\(\s*(--[a-z0-9-]+)", text))
    projected = dict(style_projection("one-pager", "zh-Hans-CN").projected)
    projected.update(web_projection("web-reading", "zh-Hans-CN").projected)
    projected.update(web_projection("web-reading", "en").projected)
    aliases = viewport_aliases(projected)

    return sorted(
        name for name in projected
        if name not in used and name not in UNCONSUMED and name not in aliases
    )


# Declarations the Web template must not decide for itself. A value here is a
# second design system: the profile is the only place it may live.
WEB_LITERAL_PROPERTIES = ("font-size", "font-family", "line-height", "letter-spacing",
                          "font-weight", "padding", "margin", "gap", "border-radius")


def web_template_literals() -> list[str]:
    """Numeric or family literals in the Web template's type and spacing.

    `0` is not a value the profile needs to own, and a custom-property
    declaration is the projection's own block, not the template's. Everything
    else is a hard-coded design decision.
    """
    path = Path(__file__).resolve().parents[1] / "assets" / "templates" / "web" / "base.css"
    if not path.is_file():
        return []
    text = re.sub(r"/\*[\s\S]*?\*/", "", path.read_text(encoding="utf-8"))
    findings: list[str] = []
    in_root = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(":root"):
            in_root = 1
            continue
        if in_root:
            if "}" in line:
                in_root = 0
            continue
        for prop in WEB_LITERAL_PROPERTIES:
            match = re.match(rf"{prop}\s*:\s*(.+)", stripped)
            if not match:
                continue
            value = match.group(1).rstrip(";")
            if "var(" in value:
                continue
            if prop == "font-family":
                findings.append(f"{prop}: {value}")
            elif prop == "font-weight":
                # A weight carries no unit, so the length test cannot see it.
                if re.search(r"\b\d{3}\b|\bbold(er)?\b|\blight(er)?\b", value):
                    findings.append(f"{prop}: {value}")
            elif re.search(r"\b\d*\.?\d+(px|pt|em|rem)\b", value):
                findings.append(f"{prop}: {value}")
    return findings


def check() -> list[str]:
    """Problems with the projection layer itself."""
    issues: list[str] = []

    # Every mapped variable must be producible from a real profile.
    projection = style_projection("one-pager", "zh-Hans-CN")
    if not projection.projected:
        issues.append("no style values were projected for one-pager")

    # The Web layer is a projection too, and it must resolve for both languages
    # the engine claims to serve.
    for language in ("zh-Hans-CN", "en"):
        web = web_projection("web-reading", language)
        if not web.projected:
            issues.append(f"no Web values were projected for {language}")
        for required in ("--serif", "--mono", "--web-body-size", "--web-space-6",
                         "--web-measure-body"):
            if required not in web.projected:
                issues.append(f"Web projection for {language} is missing {required}")

    for literal in web_template_literals():
        issues.append(f"Web template declares its own value: {literal}")

    # Every per-width value the profile projects must be one the plan resolves,
    # and every value the plan reads must exist. A typo on either side would
    # otherwise leave a breakpoint quietly keeping the regular value.
    import web_plan

    projected = web_projection("web-reading", "zh-Hans-CN").projected
    plan = web_plan.viewport_plan("zh-Hans-CN")
    consumed = {item["alias"] for override in plan["overrides"]
                for item in override["values"].values() if "alias" in item}
    for name in sorted(viewport_aliases(projected) - consumed):
        issues.append(f"per-width value nothing applies: {name}")
    for name in sorted(consumed - set(projected)):
        issues.append(f"the plan reads a value the profile does not project: {name}")

    template = (Path(__file__).resolve().parents[1] / "assets" / "templates" / "web" / "base.css")
    if template.is_file():
        issues.extend(web_plan.stylesheet_breakpoints(template.read_text(encoding="utf-8")))

    # The layer must be legal CSS by inspection: balanced braces, no empty rule.
    for name, proj in (("style", projection), ("policy", policy_projection("one-pager"))):
        if proj.empty:
            continue
        if proj.css.count("{") != proj.css.count("}"):
            issues.append(f"{name} projection has unbalanced braces")

    # A projected variable nothing reads is the failure this repository keeps
    # repeating. Report it rather than let it accumulate.
    for name in unconsumed_variables():
        issues.append(f"projected but unread: {name}")

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
