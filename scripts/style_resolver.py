#!/usr/bin/env python3
"""folio style resolver

Turns a document's profile references into one resolved style, and records
where every value came from.

The profiles are already separated by domain -- typography, page, language,
theme, taste -- and `extends` chains are already flattened. What was missing is
the step that combines them and can answer a question the plan treats as
central: why is this paragraph this size, and which profile decided it?

Two rules shape the design.

First, a domain only writes the fields it owns. Typography decides type size and
leading; page decides geometry; theme decides colour; language decides shaping
and line-breaking needs. A language rule cannot recolour a document, and a theme
cannot reflow one.

Second, every resolved value carries its origin. A resolver that returns the
right number but cannot say where it came from is not auditable, and the first
question asked about an unexpected page break is which profile caused it.

Usage:
    python3 scripts/style_resolver.py resolve --genre one-pager --lang zh-Hans-CN
    python3 scripts/style_resolver.py explain body.size_pt --genre one-pager
    python3 scripts/style_resolver.py domains
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "assets" / "templates"
sys.path.insert(0, str(ROOT / "scripts"))

# Which profile kind owns which top-level field. A domain that writes a field it
# does not own is a configuration error: it means the separation the profiles
# claim to have is not real.
DOMAIN_FIELDS: dict[str, frozenset[str]] = {
    "typography": frozenset({
        "body", "paragraph", "roles", "headings", "numbers", "leading",
        "size_pt", "alignment", "hyphenation", "tracking", "genre", "language",
    }),
    "page": frozenset({
        "page", "margins_mm", "columns", "pagination", "page_count", "regions",
        "size", "orientation", "genre",
    }),
    "language": frozenset({
        "tag", "script", "direction", "font_fallback", "line_break",
        "punctuation", "hyphenation", "tracking", "notes",
    }),
    "theme": frozenset({
        "palette", "colors", "accent", "decoration", "invariants", "overridable",
        # What a value means, and what a chart series is. Both are colour
        # decisions, so both belong to the theme rather than to a template.
        "status", "data",
        "genre",
    }),
    "taste": frozenset({
        "context", "hard_requirements", "soft_objectives", "taste", "genre",
    }),
}

# Fields that more than one domain may carry, because they describe the
# document rather than the domain.
SHARED_FIELDS = frozenset({"genre", "language", "notes", "extends"})


class StyleError(ValueError):
    """Raised when a style cannot be resolved."""


@dataclass(frozen=True)
class ResolvedValue:
    """One resolved field, with the chain that produced it."""

    path: str
    value: Any
    source: str
    chain: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"path": self.path, "value": self.value, "source": self.source,
                "chain": list(self.chain)}


@dataclass
class ResolvedStyle:
    """The combined style for one document, with every value traceable."""

    document_id: str
    values: dict[str, ResolvedValue] = field(default_factory=dict)
    domains: dict[str, str] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)

    def get(self, path: str, default: Any = None) -> Any:
        found = self.values.get(path)
        return found.value if found else default

    def source_of(self, path: str) -> str | None:
        found = self.values.get(path)
        return found.source if found else None

    def explain(self, path: str) -> str:
        found = self.values.get(path)
        if not found:
            return f"{path}: not set by any profile"
        chain = " <- ".join(found.chain) if found.chain else found.source
        return f"{path} = {found.value!r}\n  from {chain}"

    def to_json(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "domains": dict(sorted(self.domains.items())),
            "violations": list(self.violations),
            "values": {k: v.to_json() for k, v in sorted(self.values.items())},
        }


def _load_profiles() -> tuple[dict[str, dict[str, dict]], dict[str, dict]]:
    """Every profile, flattened, plus each file's shared `defaults`.

    Returns the profiles by kind and the defaults by kind. The defaults are the
    base of the precedence chain: a value declared there applies to every
    profile in the file unless one overrides it.
    """
    import profile_check
    from corpus import _parse_yaml

    loaded = profile_check.load_profiles()
    resolved: dict[str, dict[str, dict]] = {}
    defaults: dict[str, dict] = {}

    for kind, profiles in loaded.items():
        if not isinstance(profiles, dict):
            continue
        resolved[kind] = profile_check._resolve_extends(profiles, kind, None)

        directory = Path(profile_check.PROFILES) / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            try:
                data = _parse_yaml(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            shared = data.get("defaults")
            if isinstance(shared, dict):
                defaults.setdefault(kind, {}).update(shared)
    return resolved, defaults


def _walk(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    """Flatten a mapping into dotted paths, keeping leaves only."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk(item, path)
    elif isinstance(value, (list, tuple)):
        yield prefix, list(value)
    else:
        yield prefix, value


def _owned_by(kind: str, path: str) -> bool:
    """Whether a domain is allowed to set this field."""
    top = path.split(".", 1)[0]
    if top in SHARED_FIELDS:
        return True
    return top in DOMAIN_FIELDS.get(kind, frozenset())


def resolve(
    *,
    document_id: str = "document",
    genre: str | None = None,
    language: str | None = None,
    names: Mapping[str, str] | None = None,
    template: str | None = None,
) -> ResolvedStyle:
    """Combine the five profile kinds into one style.

    `names` maps a profile kind to the profile to use. Anything omitted is
    selected by genre and language, which is how the templates are chosen today.
    """
    profiles, defaults = _load_profiles()
    style = ResolvedStyle(document_id=document_id)

    # The shared defaults are the base of the chain, so a rule declared once in
    # the file is visible and traceable like any other.
    for kind, body in defaults.items():
        for path, value in _walk(body):
            if not _owned_by(kind, path):
                continue
            style.values[path] = ResolvedValue(
                path=path, value=value, source=f"{kind}:defaults",
                chain=(f"{kind}:defaults",),
            )
    for kind in defaults:
        style.domains.setdefault(f"{kind} (defaults)", "defaults")

    # A caller who states a language has decided; one who does not is answered
    # from the template, which is where the document's language actually lives.
    # The template is found from the genre when it was not passed, otherwise the
    # inference never runs for the common case of naming only a genre.
    template_path = template or (template_for_genre(genre, language) if genre else None)
    effective_language = language or (
        language_of_template(template_path) if template_path else None
    )

    selected: dict[str, str] = dict(names or {})
    if not selected:
        selected = _select_by_genre(profiles, genre, effective_language)

    # Order matters: later domains may refine a shared field, and the order is
    # the documented precedence rather than an accident of iteration.
    precedence = ("typography", "page", "language", "theme", "taste")

    for kind in precedence:
        name = selected.get(kind)
        if not name:
            continue
        body = profiles.get(kind, {}).get(name)
        if body is None:
            style.violations.append(f"{kind}: profile '{name}' not found")
            continue

        style.domains[kind] = name
        for path, value in _walk(body):
            if not _owned_by(kind, path):
                style.violations.append(
                    f"{kind}.{path} is outside this domain's ownership "
                    f"({name} sets a field it does not own)"
                )
                continue
            # A later domain with a value for the same path wins, and the chain
            # records that it did.
            previous = style.values.get(path)
            chain = (previous.chain + (f"{kind}:{name}",)) if previous else (f"{kind}:{name}",)
            style.values[path] = ResolvedValue(
                path=path, value=value, source=f"{kind}:{name}", chain=chain
            )

    return style



# The template states the document's language on its root element, which is what
# a profile should follow.
_TEMPLATE_LANG = re.compile(r"<html[^>]*\blang=[\"']([^\"']+)[\"']", re.IGNORECASE)


def language_of_template(template_path: str | Path) -> str | None:
    """The language a template declares, or None when it declares none."""
    path = Path(template_path)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _TEMPLATE_LANG.search(text)
    return match.group(1).strip() if match else None


def template_for_genre(genre: str, language: str | None = None) -> Path | None:
    """The template a genre and language resolve to, if one exists."""
    if not genre:
        return None
    suffix = ""
    if language and not language.lower().startswith("zh"):
        suffix = "-en"
    candidate = TEMPLATES / f"{genre}{suffix}.html"
    if candidate.is_file():
        return candidate
    fallback = TEMPLATES / f"{genre}.html"
    return fallback if fallback.is_file() else None


def _select_by_genre(
    profiles: Mapping[str, Mapping[str, dict]], genre: str | None, language: str | None
) -> dict[str, str]:
    """Find the profile of each kind that matches a genre and language."""
    chosen: dict[str, str] = {}
    is_zh = bool(language and language.lower().startswith("zh"))

    for kind in ("typography", "page", "language", "theme", "taste"):
        candidates = profiles.get(kind) or {}
        if not candidates:
            continue
        exact, ambiguous = _best_match(candidates, genre, is_zh, language)
        if exact:
            chosen[kind] = exact
        elif ambiguous:
            # Two profiles fit equally and nothing says which. Choosing one would
            # be a guess presented as a resolved style, so the candidates are
            # recorded for the caller to settle.
            chosen[f"__ambiguous__{kind}"] = ", ".join(ambiguous)

    # Theme and language have a single shared profile in this repository, so a
    # genre match is not required for them.
    for kind in ("theme", "language"):
        if kind in chosen or not (profiles.get(kind) or {}):
            continue
        chosen[kind] = next(iter(sorted(profiles[kind])))

    return chosen


def _best_match(
    candidates: Mapping[str, dict],
    genre: str | None,
    is_zh: bool,
    language: str | None = None,
) -> tuple[str | None, list[str]]:
    """The profile that fits best, and the candidates that tied for it.

    Scoring is unchanged; what changed is the tie. Two profiles that match the
    genre and differ only by language used to be separated by the profile's name,
    which made `-en` win by alphabet and produced English typography for a
    Chinese document. A tie with no language to settle it is now reported.

    Returns `(choice, tied)` where `tied` is empty when the choice was clear.
    """
    scored: list[tuple[int, str]] = []
    for name, body in candidates.items():
        score = 0
        declared_genre = body.get("genre")
        if genre and declared_genre == genre:
            score += 4
        elif genre and declared_genre:
            continue

        blob = json.dumps(body, ensure_ascii=False).lower()
        # A stated language earns its profile a point. No language earns nobody
        # anything, which is what leaves two profiles tied instead of letting
        # the alphabet decide.
        if language:
            if is_zh and ("zh" in name.lower() or "zh" in blob):
                score += 2
            elif not is_zh and ("-en" in name.lower() or "en-" in name.lower()):
                score += 2
        scored.append((score, name))

    if not scored:
        return None, []

    best = max(score for score, _ in scored)
    winners = sorted(name for score, name in scored if score == best)

    if len(winners) == 1:
        return winners[0], []

    # Nothing distinguished the winners. If a language was given and exactly one
    # winner matches it, that is a basis to choose; otherwise report the tie.
    if language:
        matches = [name for name in winners if language.split("-")[0].lower() in name.lower()]
        if len(matches) == 1:
            return matches[0], []

    return None, winners


def render_text(style: ResolvedStyle) -> str:
    lines = [f"Resolved style — {style.document_id}", ""]
    lines.append("  profiles in use")
    for kind, name in sorted(style.domains.items()):
        lines.append(f"    {kind:<12} {name}")
    lines.append("")
    lines.append(f"  resolved values  {len(style.values)}")
    if style.violations:
        lines.append("")
        lines.append("  domain violations")
        for item in style.violations[:8]:
            lines.append(f"    {item}")
    lines.append("")
    lines.append("  Every value records the profile that set it, so an unexpected")
    lines.append("  page break can be traced to a decision rather than guessed at.")
    lines.append("")
    lines.append("  Try: style_resolver.py explain body.size_pt --genre one-pager")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    resolve_cmd = sub.add_parser("resolve", help="resolve a style")
    resolve_cmd.add_argument("--genre")
    resolve_cmd.add_argument("--lang")
    resolve_cmd.add_argument("--format", choices=("text", "json"), default="text")

    explain = sub.add_parser("explain", help="show where one value came from")
    explain.add_argument("path")
    explain.add_argument("--genre")
    explain.add_argument("--lang")

    sub.add_parser("domains", help="show which domain owns which field")

    args = parser.parse_args(argv)

    if args.command == "domains":
        print("Field ownership by profile kind")
        print("")
        for kind, fields in DOMAIN_FIELDS.items():
            print(f"  {kind}")
            print(f"    {', '.join(sorted(fields))}")
        print("")
        print(f"  shared: {', '.join(sorted(SHARED_FIELDS))}")
        return 0

    style = resolve(genre=args.genre, language=args.lang)

    if args.command == "explain":
        print(style.explain(args.path))
        return 0

    if args.format == "json":
        print(json.dumps(style.to_json(), indent=2, ensure_ascii=False))
    else:
        print(render_text(style))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
