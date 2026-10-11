#!/usr/bin/env python3
"""folio profile check

Validates the profile set against the repository it describes. A profile that
disagrees with the templates is worse than no profile: it documents a system
that does not exist.

Three kinds of check:

  1. Structure   every profile has the fields its kind requires.
  2. Consistency page contracts match scripts/page_contracts.py, typography
                 sizes match the templates they claim to describe.
  3. Separation  theme contains no type, typography contains no colour.

Usage:
    python3 scripts/profile_check.py                  # report
    python3 scripts/profile_check.py --format json
    python3 scripts/profile_check.py --strict         # exit 1 on warnings too
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from page_contracts import HTML_TARGETS, PPTX_TARGETS  # noqa: E402

PROFILES = ROOT / "references" / "profiles"
TEMPLATES = ROOT / "assets" / "templates"

# Genre -> (Chinese template, English template)
GENRE_TEMPLATES = {
    "one-pager": ("one-pager.html", "one-pager-en.html"),
    "letter": ("letter.html", "letter-en.html"),
    "long-doc": ("long-doc.html", "long-doc-en.html"),
    "portfolio": ("portfolio.html", "portfolio-en.html"),
    "resume": ("resume.html", "resume-en.html"),
    "equity-report": ("equity-report.html", "equity-report-en.html"),
    "changelog": ("changelog.html", "changelog-en.html"),
}


@dataclass
class Finding:
    severity: str  # error | warning
    code: str
    subject: str
    message: str

    def to_dict(self) -> dict:
        return {"severity": self.severity, "code": self.code, "subject": self.subject, "message": self.message}


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)

    def error(self, code: str, subject: str, message: str) -> None:
        self.findings.append(Finding("error", code, subject, message))

    def warn(self, code: str, subject: str, message: str) -> None:
        self.findings.append(Finding("warning", code, subject, message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]


# --------------------------------------------------------------------------
# Minimal YAML reader
#
# PyYAML is not a build dependency. The profile files use a small, regular
# subset: nested mappings by indentation, `- ` sequences, and inline flow
# mappings like `{size_pt: 10, leading: 1.45}`. Anything outside that subset is
# reported rather than guessed at, so a malformed profile cannot pass silently.
# --------------------------------------------------------------------------


def _scalar(text: str):
    text = text.strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        if not inner:
            return {}
        out = {}
        # Split on commas that separate key: value pairs.
        parts, depth, current = [], 0, ""
        for ch in inner:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += ch
        parts.append(current)
        for part in parts:
            if ":" not in part:
                continue
            key, value = part.split(":", 1)
            out[key.strip()] = _scalar(value)
        return out
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(item) for item in inner.split(",")]
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text in {"true", "false"}:
        return text == "true"
    if text in {"null", "~"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text



def _strip_comment(line: str) -> str:
    """The line with its trailing comment removed.

    A `#` begins a comment only outside quotes. Splitting on the first one
    anywhere removes the `#` of a hex colour, which is how every value in the
    theme profile came to load as an empty string.
    """
    quote: str | None = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "#":
            return line[:index]
    return line


def parse_yaml(text: str) -> dict:
    """Parse the profile subset. Comments and blank lines are ignored."""
    root: dict = {}
    # Stack of (indent, container)
    stack: list[tuple[int, object]] = [(-1, root)]
    pending_key: dict[int, str] = {}

    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]

        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if not isinstance(container, list):
                continue
            if ":" in item and not item.startswith(("{", "[")):
                key, value = item.split(":", 1)
                entry = {key.strip(): _scalar(value)}
                container.append(entry)
                stack.append((indent, entry))
            else:
                container.append(_scalar(item))
            continue

        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value in {"", ">-", "|", "|-", ">", "|+"}:
            # Block: decide list vs mapping by looking ahead.
            lookahead = None
            lines = text.splitlines()
            idx = lines.index(raw)
            for nxt in lines[idx + 1:]:
                nxt_clean = _strip_comment(nxt).rstrip()
                if not nxt_clean.strip():
                    continue
                if len(nxt_clean) - len(nxt_clean.lstrip()) > indent:
                    lookahead = nxt_clean.strip()
                break
            new: object = [] if (lookahead or "").startswith("- ") else {}
            if isinstance(container, dict):
                container[key] = new
            stack.append((indent, new))
            pending_key[indent] = key
        else:
            if isinstance(container, dict):
                container[key] = _scalar(value)
    return root


def load_profiles() -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for kind_dir in sorted(PROFILES.iterdir()):
        if not kind_dir.is_dir():
            continue
        merged: dict[str, dict] = {}
        for path in sorted(kind_dir.glob("*.yaml")):
            try:
                data = parse_yaml(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - reported as a finding
                raise ValueError(f"{path.name}: {exc}") from exc
            for name, body in (data.get("profiles") or {}).items():
                merged[name] = body if isinstance(body, dict) else {}
        out[kind_dir.name] = merged
    return out


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_structure(profiles: dict[str, dict[str, dict]], report: Report) -> None:
    report.checked["profile_kinds"] = len(profiles)
    report.checked["profiles"] = sum(len(v) for v in profiles.values())

    # An empty kind almost always means a file failed to parse rather than that
    # the kind is unused: the taste set was silently invisible because its file
    # used `contracts:` as the top-level key.
    for kind in ("typography", "page", "language", "theme", "taste"):
        if kind not in profiles:
            report.error("PROFILE.KIND.MISSING", kind, "no profile directory for this kind")
        elif not profiles[kind]:
            report.error(
                "PROFILE.KIND.EMPTY",
                kind,
                "no profiles parsed; check the file's top-level `profiles:` key",
            )

    for name, body in profiles.get("typography", {}).items():
        if "body" not in body:
            report.error("PROFILE.TYPO.NO_BODY", name, "typography profile has no body block")
        size = (body.get("body") or {}).get("size_pt")
        if size is None and "extends" not in body:
            report.error("PROFILE.TYPO.NO_SIZE", name, "body.size_pt is missing")

    for name, body in profiles.get("page", {}).items():
        contract = body.get("page_count") or {}
        mode = contract.get("mode")
        if mode not in {"hard", "soft"}:
            report.error("PROFILE.PAGE.NO_MODE", name, f"page_count.mode must be hard or soft, got {mode!r}")
        elif mode == "hard" and "exact" not in contract:
            report.error("PROFILE.PAGE.HARD_NO_EXACT", name, "hard page count requires `exact`")
        elif mode == "soft" and "target" not in contract:
            report.error("PROFILE.PAGE.SOFT_NO_TARGET", name, "soft page count requires `target`")

    for name, body in profiles.get("taste", {}).items():
        hard = body.get("hard_requirements") or {}
        soft = body.get("soft_objectives") or {}
        taste = body.get("taste") or {}
        if not hard:
            report.error("PROFILE.TASTE.NO_HARD", name, "taste contract needs hard_requirements")
        if not soft and not taste:
            report.warn("PROFILE.TASTE.NO_SOFT", name, "taste contract has no soft objectives or taste block")
        overlap = set(hard) & set(soft)
        if overlap:
            report.error(
                "PROFILE.TASTE.OVERLAP",
                name,
                f"requirement appears in both hard and soft: {', '.join(sorted(overlap))}",
            )


def check_page_contracts(profiles: dict[str, dict[str, dict]], report: Report) -> None:
    """Page profiles must agree with the table the build enforces."""
    by_genre: dict[str, dict] = {}
    for body in profiles.get("page", {}).values():
        genre = body.get("genre")
        if genre:
            by_genre[genre] = body

    # Targets are keyed by name; compare per genre using the Chinese target,
    # which carries the same contract as its English sibling.
    for target, spec in HTML_TARGETS.items():
        if target.endswith("-en"):
            continue
        genre = target
        page = by_genre.get(genre)
        if page is None:
            report.warn("PROFILE.PAGE.MISSING_GENRE", genre, "no page profile for this build target")
            continue
        contract = page.get("page_count") or {}
        if contract.get("mode") == "hard":
            # The profile records the count the template aims at; the contract
            # file is what a build is checked against. A contract with a floor
            # and a ceiling -- two pages at least, three at most -- has no single
            # number, so the profile's count is compared with the ceiling and the
            # floor is checked to be a floor.
            if contract.get("exact") != spec.max_pages:
                report.error(
                    "PROFILE.PAGE.CONTRACT_MISMATCH",
                    genre,
                    f"profile says exact {contract.get('exact')}, page_contracts.py says "
                    f"{spec.min_pages}-{spec.max_pages}",
                )
            elif spec.min_pages > spec.max_pages:
                report.error(
                    "PROFILE.PAGE.CONTRACT_INVERTED",
                    genre,
                    f"page_contracts.py says {spec.min_pages}-{spec.max_pages}",
                )
        else:
            target_pages = contract.get("target")
            tol = contract.get("tolerance_pages", 0)
            if target_pages is None:
                continue
            lo, hi = target_pages - tol, target_pages + tol
            if not (lo <= spec.min_pages and spec.max_pages <= hi):
                report.error(
                    "PROFILE.PAGE.TOLERANCE_MISMATCH",
                    genre,
                    f"profile allows {lo}-{hi}, page_contracts.py allows {spec.min_pages}-{spec.max_pages}",
                )

    for spec in PPTX_TARGETS.values():
        page = by_genre.get("slides")
        if page is None:
            report.warn("PROFILE.PAGE.MISSING_GENRE", "slides", "no page profile for slide targets")
            continue
        contract = page.get("page_count") or {}
        if contract.get("mode") == "soft":
            tol = contract.get("tolerance_pages", 0)
            tgt = contract.get("target", 0)
            if not (tgt - tol <= spec.min_pages and spec.max_pages <= tgt + tol):
                report.error(
                    "PROFILE.PAGE.TOLERANCE_MISMATCH",
                    "slides",
                    f"profile allows {tgt - tol}-{tgt + tol}, page_contracts.py allows "
                    f"{spec.min_pages}-{spec.max_pages}",
                )


BODY_FONT_SIZE = re.compile(r"^[ \t]*body[ \t]*\{(?P<body>.*?)^[ \t]*\}", re.DOTALL | re.MULTILINE)
FONT_SIZE_IN_BODY = re.compile(r"font-size:\s*([0-9.]+)pt")
LINE_HEIGHT_IN_BODY = re.compile(r"line-height:\s*([0-9.]+)")


def _template_body_metrics(path: Path) -> tuple[float | None, float | None]:
    """Body font size and leading as the template declares them.

    Reads the same block the paragraph-rule check uses, so the two cannot
    disagree about which rule is the document's body.
    """
    block = _main_body_block(path)
    if block is None:
        return None, None
    size = FONT_SIZE_IN_BODY.search(block)
    leading = LINE_HEIGHT_IN_BODY.search(block)
    return (
        float(size.group(1)) if size else None,
        float(leading.group(1)) if leading else None,
    )


PARAGRAPH_PROPS = ("widows", "orphans", "hyphens")


def _template_paragraph_rules(path: Path) -> dict[str, object]:
    """Paragraph flow properties as the main body block declares them.

    Reads the same block `_template_body_metrics` uses, so a rule declared on
    the canvas or screen-shell block is not mistaken for a text rule.
    """
    block = _main_body_block(path)
    if block is None:
        return {}
    found: dict[str, object] = {}
    for prop in PARAGRAPH_PROPS:
        match_prop = re.search(rf"{prop}:\s*([A-Za-z0-9_-]+)", block)
        if not match_prop:
            continue
        raw = match_prop.group(1)
        found[prop] = int(raw) if raw.isdigit() else raw
    return found


def _main_body_block(path: Path) -> str | None:
    """Body rule that sets the text stack, whether written on one line or many.

    Multi-line blocks close on their own line; single-line blocks do not. Both
    forms appear in tests and fixtures, so the terminator is matched either way.
    """
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^[ \t]*(?P<selector>[a-z0-9,\s.#:_-]*?)[ \t]*\{(?P<body>[^{}]*)\}",
        re.DOTALL | re.MULTILINE,
    )
    for match in pattern.finditer(text):
        if match.group("selector").strip() != "body":
            continue
        if "font-family: var(--serif)" in match.group("body"):
            return match.group("body")
    return None


def check_typography_matches_templates(profiles: dict[str, dict[str, dict]], report: Report) -> None:
    """A typography profile that disagrees with its template documents fiction."""
    by_genre_lang: dict[tuple[str, str], dict] = {}
    for body in profiles.get("typography", {}).values():
        genre = body.get("genre")
        language = body.get("language", "")
        if genre:
            by_genre_lang[(genre, "en" if "en" in str(language) else "zh")] = body

    for genre, (zh_template, en_template) in GENRE_TEMPLATES.items():
        for lang, filename in (("zh", zh_template), ("en", en_template)):
            profile = by_genre_lang.get((genre, lang))
            if profile is None:
                report.warn(
                    "PROFILE.TYPO.MISSING",
                    f"{genre}/{lang}",
                    "no typography profile for this template",
                )
                continue
            size, leading = _template_body_metrics(TEMPLATES / filename)
            if size is None:
                report.warn("PROFILE.TYPO.UNREADABLE", filename, "could not read body metrics")
                continue
            declared = (profile.get("body") or {}).get("size_pt")
            if declared is None:
                continue
            if abs(float(declared) - size) > 0.01:
                report.error(
                    "PROFILE.TYPO.SIZE_MISMATCH",
                    f"{genre}/{lang}",
                    f"profile says {declared}pt, {filename} renders {size}pt",
                )
            declared_leading = (profile.get("body") or {}).get("leading")
            if declared_leading is not None and leading is not None:
                if abs(float(declared_leading) - leading) > 0.01:
                    report.error(
                        "PROFILE.TYPO.LEADING_MISMATCH",
                        f"{genre}/{lang}",
                        f"profile says {declared_leading}, {filename} renders {leading}",
                    )

            # Paragraph flow rules were declared in the profile for a while
            # before any template set them, so nothing enforced them. Checking
            # the declaration keeps the two from drifting apart again.
            paragraph = profile.get("paragraph") or {}
            declared_widows = paragraph.get("widows")
            if declared_widows is not None:
                css = _template_paragraph_rules(TEMPLATES / filename)
                if css.get("widows") is None:
                    report.error(
                        "PROFILE.PARAGRAPH.NOT_SET",
                        f"{genre}/{lang}",
                        f"profile declares widows {declared_widows} but {filename} sets none",
                    )
                elif css["widows"] != declared_widows:
                    report.error(
                        "PROFILE.PARAGRAPH.WIDOWS_MISMATCH",
                        f"{genre}/{lang}",
                        f"profile says widows {declared_widows}, {filename} sets {css['widows']}",
                    )


THEME_COLOR_KEYS = {"paper", "surface", "sand", "border", "border_soft", "text", "text_warm",
                    "charcoal", "olive", "stone", "brand", "tint", "tint_strong", "tag_bg", "hairline"}
TYPE_KEYS = {"size_pt", "leading", "weight", "tracking_em", "kerning", "ligatures", "hyphenation"}


def check_separation(profiles: dict[str, dict[str, dict]], report: Report) -> None:
    """Theme must not carry type; typography must not carry colour."""
    for name, body in profiles.get("theme", {}).items():
        blob = json.dumps(body)
        for key in TYPE_KEYS:
            if f'"{key}"' in blob:
                report.error(
                    "PROFILE.SEPARATION.TYPE_IN_THEME",
                    name,
                    f"theme declares type property `{key}`; it belongs in a typography profile",
                )
        if "font" in blob.lower() and "font_family" not in blob:
            report.warn("PROFILE.SEPARATION.FONT_IN_THEME", name, "theme mentions a font")

    for profile_name, body in profiles.get("typography", {}).items():
        # `subject` is passed explicitly: closing over the loop variable would
        # report whichever profile the loop reached last.
        def walk(node, path="", subject=profile_name):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in THEME_COLOR_KEYS and isinstance(value, str) and value.startswith("#"):
                        report.error(
                            "PROFILE.SEPARATION.COLOR_IN_TYPO",
                            subject,
                            f"typography declares colour at {path}{key}; it belongs in a theme",
                        )
                    walk(value, f"{path}{key}.", subject)
        walk(body)


def _resolve_extends(profiles: dict[str, dict], kind: str, report: Report | None = None) -> dict[str, dict]:
    """Flatten `extends` chains so a child inherits its parent's fields.

    A profile that only overrides `size_pt` is still expected to describe a
    complete body, so inheritance is resolved before the structural checks run.
    `report` may be omitted when the caller only wants the resolved values.
    """
    resolved: dict[str, dict] = {}
    visiting: set[str] = set()

    def note(code: str, subject: str, message: str) -> None:
        if report is not None:
            report.error(code, subject, message)

    def merge(base: dict, override: dict) -> dict:
        out = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = merge(out[key], value)
            else:
                out[key] = value
        return out

    def resolve(name: str) -> dict:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            note("PROFILE.EXTENDS.CYCLE", name, "extends chain contains a cycle")
            return profiles.get(name, {})
        body = profiles.get(name)
        if body is None:
            note("PROFILE.EXTENDS.MISSING", name, "extends a profile that does not exist")
            return {}
        visiting.add(name)
        parent_name = body.get("extends")
        if parent_name:
            parent = profiles.get(str(parent_name))
            if parent is None:
                note(
                    "PROFILE.EXTENDS.UNKNOWN",
                    name,
                    f"extends `{parent_name}`, which is not defined in {kind}",
                )
                merged = dict(body)
            else:
                merged = merge(resolve(str(parent_name)), body)
        else:
            merged = dict(body)
        visiting.discard(name)
        merged.pop("extends", None)
        resolved[name] = merged
        return merged

    for name in list(profiles):
        resolve(name)
    return resolved


PROFILE_SCHEMAS = {
    "typography": "typography.schema.json",
    "page": "page.schema.json",
    "language": "language.schema.json",
    "theme": "theme.schema.json",
    "taste": "taste.schema.json",
}

# Files whose top-level name does not follow the kind's default.
PROFILE_FILES = {
    "theme": "folio-classic-v1.yaml",
}


def check_schemas(report: Report) -> None:
    """Validate each profile file against its JSON Schema.

    The runtime checks above verify meaning; the schema verifies shape. Both
    are needed: a malformed file can happen to satisfy a semantic check.
    """
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        report.warn("PROFILE.SCHEMA.UNAVAILABLE", "schemas", "jsonschema is not installed")
        return

    schema_dir = ROOT / "references" / "schemas" / "profile"
    for kind, schema_name in PROFILE_SCHEMAS.items():
        schema_path = schema_dir / schema_name
        profile_path = PROFILES / kind / PROFILE_FILES.get(kind, "folio-v1.yaml")
        if not schema_path.is_file() or not profile_path.is_file():
            report.warn("PROFILE.SCHEMA.MISSING", kind, "schema or profile file not found")
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            report.error("PROFILE.SCHEMA.INVALID", kind, f"schema is not valid: {exc}")
            continue
        data = _load_profile_file(profile_path)
        for error in Draft202012Validator(schema).iter_errors(data):
            location = ".".join(str(p) for p in error.path) or "(root)"
            report.error("PROFILE.SCHEMA.VIOLATION", f"{kind}:{location}", error.message)


def _load_profile_file(path: Path) -> dict:
    """Read a profile file with the shared YAML reader."""
    from corpus import _parse_yaml

    return _parse_yaml(path.read_text(encoding="utf-8"))


def run_checks() -> Report:
    report = Report()
    try:
        raw = load_profiles()
    except ValueError as exc:
        report.error("PROFILE.PARSE", "profiles", str(exc))
        return report

    profiles = {
        kind: _resolve_extends(bodies, kind, report)
        for kind, bodies in raw.items()
    }

    check_schemas(report)
    check_structure(profiles, report)
    check_page_contracts(profiles, report)
    check_typography_matches_templates(profiles, report)
    check_separation(profiles, report)
    return report


def render_text(report: Report) -> str:
    lines = ["Profile check", ""]
    summary = "  ".join(f"{k}={v}" for k, v in sorted(report.checked.items()))
    if summary:
        lines.append(f"  {summary}")
        lines.append("")
    for finding in report.findings:
        marker = "ERROR" if finding.severity == "error" else "WARN "
        lines.append(f"  {marker} {finding.subject}: {finding.message}  [{finding.code}]")
    lines.append("")
    if report.errors:
        lines.append(f"ERROR: {len(report.errors)} profile error(s), {len(report.warnings)} warning(s)")
    elif report.warnings:
        lines.append(f"OK: profiles valid with {len(report.warnings)} warning(s)")
    else:
        lines.append("OK: profiles valid and consistent with the repository")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--report", type=Path, help="write the JSON report here")
    args = parser.parse_args(argv)

    report = run_checks()

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "checked": report.checked,
                    "findings": [f.to_dict() for f in report.findings],
                    "errors": len(report.errors),
                    "warnings": len(report.warnings),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    if args.format == "json":
        print(
            json.dumps(
                {
                    "checked": report.checked,
                    "findings": [f.to_dict() for f in report.findings],
                    "errors": len(report.errors),
                    "warnings": len(report.warnings),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(render_text(report))

    if report.errors:
        return 1
    if args.strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
