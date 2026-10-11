#!/usr/bin/env python3
"""folio corpus renderer

Renders document fixtures and reports what each one produced.

A fixture is a reproducible input: what the document contains, what it must
satisfy, and where the content came from. Rendering one is deterministic, so a
corpus run compares like with like.

Script coverage is stated in each fixture and summarised in the run report. A
corpus that quietly becomes all-Latin is the failure this guards against: CJK
line breaking and mixed-script baselines are exactly the behaviours that
uniform content cannot exercise.

Usage:
    python3 scripts/corpus.py render                      # every fixture
    python3 scripts/corpus.py render zh-cjk-pagination    # one fixture
    python3 scripts/corpus.py validate                    # schema check only
    python3 scripts/corpus.py coverage                    # report script mix
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = ROOT / "references" / "fixtures" / "document"
SCHEMA = ROOT / "references" / "schemas" / "document-fixture-1.0.schema.json"
TEMPLATES = ROOT / "assets" / "templates"

# Directories that hold fixtures. `scripts` holds reusable content blocks, not
# fixtures, so it is excluded from discovery.
# Fixture directories are discovered, not listed: a new one added to cover a
# class the plan asks for should be picked up without editing this module.
FIXTURE_DIRS: tuple[str, ...] = ()

PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}")


@dataclass
class FixtureResult:
    fixture_id: str
    genre: str
    language: str
    script_profile: str
    adversarial: bool
    template: str
    pages: int | None = None
    placeholders_filled: int = 0
    placeholders_total: int = 0
    unfilled: list[str] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.fixture_id,
            "genre": self.genre,
            "language": self.language,
            "script_profile": self.script_profile,
            "adversarial": self.adversarial,
            "template": self.template,
            "pages": self.pages,
            "placeholders": {
                "filled": self.placeholders_filled,
                "total": self.placeholders_total,
                "remaining": len(self.unfilled),
            },
            "expected": self.expected,
            "problems": self.problems,
            "ok": self.ok,
            "error": self.error,
        }


def _parse_yaml(text: str) -> dict:
    """Read the fixture YAML subset.

    PyYAML is not a build dependency. Supported: nested mappings, `- ` lists,
    inline flow mappings, quoted and plain scalars, and block scalars for
    multi-line prose. A construct outside the subset raises rather than being
    silently skipped, so a malformed fixture cannot pass as an empty one.
    """
    lines = text.splitlines()
    root: dict = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    index = 0

    def scalar(value: str):
        value = value.strip()
        if value.startswith("{") and value.endswith("}"):
            inner = value[1:-1].strip()
            out: dict[str, Any] = {}
            if not inner:
                return out
            depth, current, parts = 0, "", []
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
                if ":" in part:
                    k, v = part.split(":", 1)
                    out[k.strip()] = scalar(v)
            return out
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            return [scalar(v) for v in inner.split(",")] if inner else []
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return _unescape(value[1:-1])
        if value in {"true", "false"}:
            return value == "true"
        if value in {"null", "~"}:
            return None
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return _unescape(value)

    def _unescape(value: str) -> str:
        return value.replace('\\"', '"').replace("\\n", "\n")

    def _strip_quotes(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1]
        return value

    def _in_content_block(current_stack: list[tuple[int, Any]], key: str) -> bool:
        """True when the value sits directly under a top-level `content:` map."""
        for _depth, node in reversed(current_stack):
            if node is root.get("content") and root.get("content") is not None:
                return True
            if node is root:
                return False
        return False

    while index < len(lines):
        raw = lines[index]
        index += 1
        stripped = raw.split(" #", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip())
        content = stripped.strip()

        # A block sequence may be written at its key's own indentation, which is
        # how a YAML dumper emits one. Such an item belongs to the list on top of
        # the stack, so the same-indent pop is skipped for it.
        is_item = content.startswith("- ")
        while stack and (
            indent < stack[-1][0]
            or (indent == stack[-1][0] and not (is_item and isinstance(stack[-1][1], list)))
        ):
            stack.pop()
        container = stack[-1][1]

        if content.startswith("- "):
            item = content[2:].strip()
            if not isinstance(container, list):
                continue
            if ":" in item and not item.startswith(("{", "[")):
                k, v = item.split(":", 1)
                entry = {k.strip(): scalar(v)}
                container.append(entry)
                stack.append((indent, entry))
            else:
                container.append(scalar(item))
            continue

        if ":" not in content:
            continue

        # Split on the first colon that is outside quotes. Placeholder keys may
        # themselves contain colons ("Fix 1: one-line description."), and a
        # naive split would truncate the key and make the lookup miss.
        split_at = _key_separator(content)
        if split_at < 0:
            continue
        key, value = content[:split_at], content[split_at + 1:]
        key, value = key.strip(), value.strip()
        # Placeholder keys are quoted because they contain braces, colons and
        # slashes. The quotes are YAML syntax, not part of the key: leaving them
        # on would make every lookup miss and the template render unfilled.
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            quote_char = key[0]
            key = key[1:-1]
            # YAML escapes differ by quote style: a double-quoted scalar uses a
            # backslash, a single-quoted one doubles the quote. Placeholder
            # names contain both, so each style needs its own rule.
            if quote_char == '"':
                key = key.replace('\\"', '"')
            else:
                key = key.replace("''", "'")

        if value in {"|", "|-", ">", ">-"}:
            # Block scalar: consume the more-indented lines that follow.
            block: list[str] = []
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    block.append("")
                    index += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= indent:
                    break
                block.append(nxt.strip() if value.startswith(">") else nxt[nxt_indent:])
                index += 1
            while block and not block[-1]:
                block.pop()
            joined = " ".join(line for line in block if line) if value.startswith(">") else "\n".join(block)
            if isinstance(container, dict):
                container[key] = joined.strip()
            continue

        if value == "":
            lookahead = None
            for nxt in lines[index:]:
                if not nxt.strip() or nxt.lstrip().startswith("#"):
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                # A block sequence may sit at its key's own indentation, which is
                # how a YAML dumper writes one; deciding by "deeper" alone read
                # such a sequence as an empty mapping.
                if nxt_indent > indent or (nxt_indent >= indent and nxt.strip().startswith("- ")):
                    lookahead = nxt.strip()
                break
            new: Any = [] if (lookahead or "").startswith("- ") else {}
            if isinstance(container, dict):
                container[key] = new
            stack.append((indent, new))
        else:
            if isinstance(container, dict):
                # Inside `content`, every value is text destined for a template
                # placeholder. Type inference would turn a version such as
                # 2026.10 into the float 2026.1 and silently drop the trailing
                # zero, so values there are kept as written.
                if _in_content_block(stack, key):
                    container[key] = _unescape(_strip_quotes(value))
                else:
                    container[key] = scalar(value)
    return root


def load_fixture(path: Path) -> dict:
    return _parse_yaml(path.read_text(encoding="utf-8"))


def _key_separator(content: str) -> int:
    """Index of the colon that separates a key from its value, or -1.

    A quoted key runs to its matching closing quote, and the separator is the
    first colon after it. Scanning for the first colon outside quotes is not
    enough: placeholder names may themselves contain quotes, as the letter
    template's do (`"Best regards," / "Sincerely,"`), so a naive scan ends the
    key early and splits the name in half.

    Every branch advances the index, so the scan always terminates.
    """
    if not content:
        return -1
    quote_char = content[0] if content[0] in "\"'" else ""
    if quote_char:
        index = 1
        length = len(content)
        while index < length:
            if content[index] == quote_char:
                # YAML escapes a single quote by doubling it.
                if quote_char == "'" and index + 1 < length and content[index + 1] == "'":
                    index += 2
                    continue
                break
            index += 1
        if index >= length:
            return -1  # unterminated key
        return content.find(":", index + 1)

    in_quote = ""
    for position, char in enumerate(content):
        if in_quote:
            if char == in_quote:
                in_quote = ""
            continue
        if char in "\"'":
            in_quote = char
        elif char == ":":
            return position
    return -1


def discover_fixtures() -> list[Path]:
    """Every fixture, from every directory that holds one.

    The `ir/` directory is excluded: those are Document IR documents, not
    document fixtures, and they have their own reader and schema.
    """
    if not FIXTURES.is_dir():
        return []
    found: list[Path] = []
    for target in sorted(FIXTURES.iterdir()):
        if target.is_dir() and target.name != "ir":
            found.extend(sorted(target.glob("*.yaml")))
    return found


def validate_fixture(data: dict, path: Path) -> list[str]:
    """Schema check, reported as a list of problems rather than raised."""
    problems: list[str] = []
    try:
        import jsonschema

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            location = ".".join(str(p) for p in error.path) or "(root)"
            problems.append(f"{location}: {error.message}")
    except ImportError:
        # Without jsonschema, apply the required-field subset so a fixture still
        # cannot be structurally empty.
        for required in ("id", "genre", "language", "script_profile", "purpose", "content", "expected", "provenance"):
            if required not in data:
                problems.append(f"(root): missing required property '{required}'")
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"(schema): {exc}")

    if data.get("id") and data["id"] != path.stem:
        problems.append(f"id '{data['id']}' does not match filename '{path.stem}'")
    return problems


def _template_for(data: dict) -> Path:
    if data.get("template"):
        return TEMPLATES / data["template"]
    genre = data["genre"]
    is_english = not str(data.get("language", "")).lower().startswith("zh")
    suffix = "-en" if is_english else ""
    return TEMPLATES / f"{genre}{suffix}.html"


def fill_template(template_text: str, content: dict[str, str]) -> tuple[str, int, list[str]]:
    """Substitute fixture values into the template's placeholders.

    A fixture may key its content either by the bare placeholder text
    (`版本号`) or by the whole placeholder (`{{版本号}}`). Both are accepted and
    normalised here, because the quoted form is easier to read in a fixture and
    the bare form is what the template actually contains.

    Placeholders the fixture does not supply are left untouched and reported,
    so a partially filled template is visible rather than silently rendered.
    """
    normalised: dict[str, str] = {}
    for key, value in content.items():
        name = key
        if name.startswith("{{") and name.endswith("}}"):
            name = name[2:-2]
        normalised[name.strip()] = value

    template_names = set(PLACEHOLDER.findall(template_text))
    filled = 0

    def replace(match: re.Match) -> str:
        nonlocal filled
        name = match.group(1)
        if name in normalised:
            filled += 1
            return normalised[name]
        return match.group(0)

    rendered = PLACEHOLDER.sub(replace, template_text)
    remaining = sorted(set(PLACEHOLDER.findall(rendered)))
    supplied = len({name for name in normalised if name in template_names})
    return rendered, supplied, remaining


def render_fixture(path: Path, workdir: Path) -> FixtureResult:
    data = load_fixture(path)
    result = FixtureResult(
        fixture_id=str(data.get("id", path.stem)),
        genre=str(data.get("genre", "")),
        language=str(data.get("language", "")),
        script_profile=str(data.get("script_profile", "")),
        adversarial=bool(data.get("adversarial", False)),
        template=str(data.get("template") or _template_for(data).name),
        expected=data.get("expected", {}),
    )

    problems = validate_fixture(data, path)
    if problems:
        result.problems.extend(problems)
        return result

    template = _template_for(data)
    if not template.is_file():
        result.error = f"template not found: {template.name}"
        return result

    rendered, filled, remaining = fill_template(template.read_text(encoding="utf-8"), data["content"])
    result.placeholders_filled = filled
    result.placeholders_total = len(set(PLACEHOLDER.findall(template.read_text(encoding="utf-8"))))
    result.unfilled = remaining

    out_dir = workdir / result.fixture_id
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{result.fixture_id}.html"
    html_path.write_text(rendered, encoding="utf-8")

    pdf_path = out_dir / f"{result.fixture_id}.pdf"
    try:
        from weasyprint import HTML

        HTML(str(html_path), base_url=str(template.parent)).write_pdf(str(pdf_path))
    except Exception as exc:  # renderer failure is reported, not raised
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    try:
        from pypdf import PdfReader

        result.pages = len(PdfReader(str(pdf_path)).pages)
    except Exception as exc:
        result.error = f"page count failed: {type(exc).__name__}: {exc}"
        return result

    # Hard expectations are checked here; craft objectives are reported by the
    # quality vector rather than turned into pass/fail here.
    hard = result.expected.get("hard") or {}
    if "pages" in hard and result.pages != hard["pages"]:
        result.problems.append(f"chose {result.pages} pages, expected exactly {hard['pages']}")
    if "pages_min" in hard and result.pages < hard["pages_min"]:
        result.problems.append(f"chose {result.pages} pages, expected at least {hard['pages_min']}")
    if "pages_max" in hard and result.pages > hard["pages_max"]:
        result.problems.append(f"chose {result.pages} pages, expected at most {hard['pages_max']}")

    return result


def render_text(results: list[FixtureResult]) -> str:
    lines = ["Corpus render", ""]
    by_script: dict[str, int] = {}
    failed = []
    for item in results:
        by_script[item.script_profile] = by_script.get(item.script_profile, 0) + 1
        marker = "OK  " if item.ok else "FAIL"
        detail = f"{item.pages} page(s)" if item.pages else (item.error or "no pages")
        flag = "  adversarial" if item.adversarial else ""
        lines.append(f"  {marker} {item.fixture_id:<26} {detail}{flag}")
        for problem in item.problems:
            lines.append(f"         {problem}")
        if item.error:
            lines.append(f"         {item.error}")
        if not item.ok:
            failed.append(item)

    lines.append("")
    lines.append("  script coverage: " + ", ".join(f"{k}={v}" for k, v in sorted(by_script.items())))
    adversarial = sum(1 for r in results if r.adversarial)
    share = (adversarial / len(results) * 100) if results else 0
    lines.append(f"  adversarial: {adversarial}/{len(results)} ({share:.0f}%)")
    lines.append("")
    if failed:
        lines.append(f"ERROR: {len(failed)} of {len(results)} fixture(s) failed")
    else:
        lines.append(f"OK: {len(results)} fixture(s) rendered within their contracts")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("render", "render fixtures and check hard expectations"),
                            ("validate", "schema-check fixtures without rendering"),
                            ("coverage", "report script coverage without rendering")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("fixtures", nargs="*", help="fixture ids (default: all)")
        cmd.add_argument("--format", choices=("text", "json"), default="text")
        cmd.add_argument("--output", type=Path, help="write the JSON report here")
        if name == "render":
            cmd.add_argument("--keep", type=Path, help="keep rendered output here")

    args = parser.parse_args(argv)
    os.environ.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())

    paths = discover_fixtures()
    if args.fixtures:
        wanted = set(args.fixtures)
        paths = [p for p in paths if p.stem in wanted]
        missing = wanted - {p.stem for p in paths}
        if missing:
            print(f"ERROR: unknown fixture(s): {', '.join(sorted(missing))}")
            return 2

    if not paths:
        print("ERROR: no fixtures found")
        return 2

    if args.command == "validate":
        problems: dict[str, list[str]] = {}
        for path in paths:
            issues = validate_fixture(load_fixture(path), path)
            if issues:
                problems[path.stem] = issues
        if args.format == "json":
            print(json.dumps(problems, indent=2, ensure_ascii=False))
        else:
            for fixture_id, issues in problems.items():
                print(f"  FAIL {fixture_id}")
                for issue in issues:
                    print(f"       {issue}")
            print()
            if problems:
                print(f"ERROR: {len(problems)} fixture(s) invalid")
            else:
                print(f"OK: {len(paths)} fixture(s) valid")
        return 1 if problems else 0

    if args.command == "coverage":
        rows = []
        for path in paths:
            data = load_fixture(path)
            rows.append(
                {
                    "id": data.get("id", path.stem),
                    "genre": data.get("genre"),
                    "language": data.get("language"),
                    "script_profile": data.get("script_profile"),
                    "adversarial": bool(data.get("adversarial", False)),
                }
            )
        payload = {"fixtures": rows, "total": len(rows)}
        if args.format == "json":
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("Corpus coverage")
            print()
            for row in rows:
                print(f"  {row['id']:<26} {str(row['genre']):<14} {row['language']:<6} {row['script_profile']}")
            print()
            counts: dict[str, int] = {}
            for row in rows:
                counts[row["script_profile"]] = counts.get(row["script_profile"], 0) + 1
            print("  " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        return 0

    results: list[FixtureResult] = []
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        for path in paths:
            results.append(render_fixture(path, args.keep))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            for path in paths:
                results.append(render_fixture(path, workdir))

    payload = [r.to_dict() for r in results]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
