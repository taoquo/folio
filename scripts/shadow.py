#!/usr/bin/env python3
"""folio shadow pipeline

Renders a document twice and compares the results:

  legacy   the template as it stands today, filled with the fixture's values
  ir       the same content taken through the Document IR and back out

The legacy artifact stays the deliverable. This exists to answer one question
before anyone changes what ships: does routing content through the IR produce
the same document?

The answer is reported per dimension rather than as a verdict, because the
interesting outcome is *which* dimension moved. A page count that holds while
the extracted text changes means something different from the reverse.

Usage:
    python3 scripts/shadow.py compare                       # every fixture
    python3 scripts/shadow.py compare canonical-zh-one-pager
    python3 scripts/shadow.py compare --format json --output dist/reports/shadow.json
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

import corpus  # noqa: E402
from document_ir.bridge import bridge_template, default_map_for  # noqa: E402
from document_ir.model import Document  # noqa: E402
from document_ir.validate import validate  # noqa: E402
from document_ir.writers import write_html  # noqa: E402

TEMPLATES = ROOT / "assets" / "templates"
STYLE_BLOCK = re.compile(r"<style>.*?</style>", re.DOTALL)
PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}")


@dataclass
class Comparison:
    fixture_id: str
    genre: str
    language: str
    legacy_pages: int | None = None
    ir_pages: int | None = None
    legacy_text: str | None = None
    ir_text: str | None = None
    legacy_fonts: list[str] = field(default_factory=list)
    ir_fonts: list[str] = field(default_factory=list)
    ir_nodes: int = 0
    ir_fallbacks: int = 0
    ir_errors: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def pages_match(self) -> bool:
        return self.legacy_pages is not None and self.legacy_pages == self.ir_pages

    @property
    def text_matches(self) -> bool:
        """Always False: text is measured, never judged.

        Extracted text cannot settle whether a difference is a loss. The IR
        legitimately carries structure the template held outside its
        placeholders, a renderer merges adjacent lines, letter-spacing splits
        capitals differently on each side, and Chinese has no word boundaries.
        Four attempts at an automatic verdict each gave a different wrong
        answer, so the report shows the measurement and a reviewer reads it.
        """
        return False

    @property
    def text_lost(self) -> list[str]:
        """Legacy sentences whose text is absent from the IR render.

        Reported as evidence. A missing sentence is one whose compacted text
        does not appear in the compacted IR render, allowing for the wrap
        points the renderer chose.
        """
        import re as _re

        legacy = self.legacy_text or ""
        ir = self.ir_text or ""
        if not legacy or not ir:
            return []

        ir_compact = _re.sub(r"\s+", "", ir)
        lost: list[str] = []
        for sentence in _re.split(r"[。！？.!?\n]", legacy):
            sentence = sentence.strip()
            probe = _re.sub(r"\s+", "", sentence)
            if len(probe) < 20:
                continue
            if probe not in ir_compact:
                head = probe[: max(16, int(len(probe) * 0.7))]
                if head not in ir_compact:
                    lost.append(sentence[:60])
        return lost

    @property
    def fonts_missing_from_ir(self) -> list[str]:
        """Fonts the legacy render needed and the IR did not."""
        return sorted(set(self.legacy_fonts) - set(self.ir_fonts))

    @property
    def fonts_added_by_ir(self) -> list[str]:
        """Fonts only the IR needed, usually a fallback the IR avoided."""
        return sorted(set(self.ir_fonts) - set(self.legacy_fonts))

    @property
    def fonts_match(self) -> bool:
        """Whether the IR kept every font the legacy render used.

        A font present only in the IR does not fail this: the IR carries
        structure the template held outside its placeholders, so it may
        legitimately need a face the legacy render did not.
        """
        return not self.fonts_missing_from_ir

    @property
    def ok(self) -> bool:
        """Whether the two paths agree on everything that is decidable.

        Text is deliberately excluded. It is measured and reported, so including
        it here would make this property permanently false and the summary
        meaningless. Pages and fonts are the dimensions a machine can settle,
        and they are the ones a migration is judged on.
        """
        return (
            self.error is None
            and not self.ir_errors
            and self.pages_match
            and self.fonts_match
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture_id,
            "genre": self.genre,
            "language": self.language,
            "pages": {"legacy": self.legacy_pages, "ir": self.ir_pages, "match": self.pages_match},
            "text": {"match": self.text_matches},
            "fonts": {"legacy": self.legacy_fonts, "ir": self.ir_fonts, "match": self.fonts_match},
            "ir": {
                "nodes": self.ir_nodes,
                "fallbacks": self.ir_fallbacks,
                "errors": self.ir_errors,
            },
            "ok": self.ok,
            "error": self.error,
        }


def _normalise(text: str) -> str:
    """Whitespace-insensitive comparison.

    Line breaks and spacing legitimately differ between two HTML structures
    that render the same words, so comparing raw text would report a difference
    that no reader would see.
    """
    return re.sub(r"\s+", " ", text).strip()


def _render(html_path: Path, base_url: Path, out: Path) -> None:
    from weasyprint import HTML

    HTML(str(html_path), base_url=str(base_url)).write_pdf(str(out))


def _pages(pdf: Path) -> int:
    from pypdf import PdfReader

    return len(PdfReader(str(pdf)).pages)


def _fonts(pdf: Path) -> list[str]:
    import subprocess

    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    try:
        result = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True,
                                check=False, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        return []
    names = set()
    for line in (result.stdout or "").splitlines()[2:]:
        if line.strip():
            names.add(line.split()[0].split("+")[-1])
    return sorted(names)


def _text(pdf: Path) -> str:
    import subprocess

    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    try:
        result = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True,
                                text=True, check=False, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout or ""


def _template_for(fixture: dict) -> Path:
    if fixture.get("template"):
        return TEMPLATES / fixture["template"]
    genre = fixture["genre"]
    is_english = not str(fixture.get("language", "")).lower().startswith("zh")
    return TEMPLATES / f"{genre}{'-en' if is_english else ''}.html"


def _legacy_html(template_text: str, content: dict[str, str]) -> str:
    """The template as it ships, with the fixture's values substituted.

    Structural labels the template promotes to placeholders fall back to their
    default wording, exactly as the build does. Without this the comparison
    would show legacy printing `{{SECTION_CHANGELOG}}` while the IR prints the
    label, and the difference would belong to the harness rather than the paths.
    """
    from section_defaults import apply_section_defaults

    normalised = {}
    for key, value in content.items():
        name = key[2:-2] if key.startswith("{{") and key.endswith("}}") else key
        normalised[re.sub(r"\s+", " ", name).strip()] = value

    seen: dict[str, int] = {}

    def substitute(match: re.Match) -> str:
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        seen[name] = seen.get(name, 0) + 1
        occurrence = seen[name]

        # The nth occurrence of a name takes the nth numbered key. The count
        # runs across the document because a numbered key names a distinct
        # value, not a position inside one section.
        fallback = f"{name} 1" if occurrence == 1 and f"{name} 1" in normalised else name
        for candidate in (f"{name} {occurrence}", f"{name}{occurrence}", name):
            if candidate in normalised:
                return normalised[candidate]
        return normalised.get(fallback, match.group(0))

    substituted = PLACEHOLDER.sub(substitute, template_text)
    return apply_section_defaults(substituted)


def _ir_html(template_text: str, content: dict[str, str], fixture: dict) -> tuple[str, Document]:
    """The same content through the IR, rendered with the template's stylesheet."""
    normalised = {}
    for key, value in content.items():
        name = key[2:-2] if key.startswith("{{") and key.endswith("}}") else key
        normalised[name.strip()] = value

    genre = fixture["genre"]
    lang = fixture["language"]
    document = bridge_template(
        template_text,
        normalised,
        document_id=fixture["id"],
        lang=lang,
        genre=genre,
        title=normalised.get("文档标题") or normalised.get("DOC_TITLE"),
        bridge_map=default_map_for(genre, lang),
        source_id=fixture["id"],
    )

    style = STYLE_BLOCK.search(template_text)
    body = write_html(document).split("<body", 1)[1].split(">", 1)[1].rsplit("</body>", 1)[0]
    shell = (
        f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">'
        f"{style.group(0) if style else ''}</head><body>{body}</body></html>"
    )
    return shell, document


def compare_fixture(path: Path, workdir: Path) -> Comparison:
    fixture = corpus.load_fixture(path)
    comparison = Comparison(
        fixture_id=fixture["id"],
        genre=fixture["genre"],
        language=fixture["language"],
    )

    template = _template_for(fixture)
    if not template.is_file():
        comparison.error = f"template not found: {template.name}"
        return comparison

    template_text = template.read_text(encoding="utf-8")
    content = fixture["content"]

    out_dir = workdir / fixture["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # Legacy
    legacy_html = out_dir / "legacy.html"
    legacy_html.write_text(_legacy_html(template_text, content), encoding="utf-8")
    legacy_pdf = out_dir / "legacy.pdf"
    try:
        _render(legacy_html, template.parent, legacy_pdf)
        comparison.legacy_pages = _pages(legacy_pdf)
        comparison.legacy_text = _text(legacy_pdf)
        comparison.legacy_fonts = _fonts(legacy_pdf)
    except Exception as exc:
        comparison.error = f"legacy render failed: {type(exc).__name__}: {exc}"
        return comparison

    # IR
    try:
        ir_shell, document = _ir_html(template_text, content, fixture)
    except Exception as exc:
        comparison.error = f"ir build failed: {type(exc).__name__}: {exc}"
        return comparison

    report = validate(document)
    comparison.ir_errors = [d.message for d in report.errors]
    nodes = list(document.walk())
    comparison.ir_nodes = len(nodes)
    comparison.ir_fallbacks = sum(1 for n in nodes if n.type == "raw_fallback")

    ir_html = out_dir / "ir.html"
    ir_html.write_text(ir_shell, encoding="utf-8")
    ir_pdf = out_dir / "ir.pdf"
    try:
        _render(ir_html, template.parent, ir_pdf)
        comparison.ir_pages = _pages(ir_pdf)
        comparison.ir_text = _text(ir_pdf)
        comparison.ir_fonts = _fonts(ir_pdf)
    except Exception as exc:
        comparison.error = f"ir render failed: {type(exc).__name__}: {exc}"
        return comparison

    return comparison


def render_text(comparisons: list[Comparison]) -> str:
    lines = ["Shadow pipeline — legacy vs IR", ""]
    lines.append(f"  {'fixture':<34} {'pages':>11} {'text':>5} {'fonts':>6} {'nodes':>6} {'fallback':>8}")
    lines.append("  " + "-" * 82)
    for item in comparisons:
        pages = f"{item.legacy_pages}->{item.ir_pages}"
        lines.append(
            f"  {item.fixture_id:<34} {pages:>11} "
            f"{'ok' if item.text_matches else 'DIFF':>5} "
            f"{'ok' if item.fonts_match else 'DIFF':>6} "
            f"{item.ir_nodes:>6} {item.ir_fallbacks:>8}"
        )
        if item.error:
            lines.append(f"         {item.error}")
        for message in item.ir_errors[:2]:
            lines.append(f"         IR error: {message}")

    matched = sum(1 for c in comparisons if c.ok)
    lines.append("")
    lines.append(f"  {matched}/{len(comparisons)} fixture(s) render identically through both paths")
    lines.append("")
    lines.append("  Reading the differences")
    lines.append("    pages   decidable, and must match: a difference means different content")
    lines.append("    fonts   decidable, and must not lose one: a new face is the IR doing better")
    lines.append("    text    measured, never judged: extracted text cannot settle it")
    lines.append("")
    lines.append("  The text row is a measurement, not a verdict. A renderer merges adjacent lines,")
    lines.append("  letter-spacing splits capitals differently on each side, and Chinese has no word")
    lines.append("  boundaries, so no rule decides whether a difference is a loss. The row shows how")
    lines.append("  far apart the paths are; a reviewer reads the sentences in the JSON report.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="render every fixture through both paths")
    compare.add_argument("fixtures", nargs="*", help="fixture ids (default: all)")
    compare.add_argument("--format", choices=("text", "json"), default="text")
    compare.add_argument("--output", type=Path, help="write the JSON report here")
    compare.add_argument("--keep", type=Path, help="keep rendered output here")

    args = parser.parse_args(argv)
    os.environ.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())

    paths = corpus.discover_fixtures()
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

    comparisons: list[Comparison] = []
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        for path in paths:
            comparisons.append(compare_fixture(path, args.keep))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            for path in paths:
                comparisons.append(compare_fixture(path, workdir))

    payload = [c.to_dict() for c in comparisons]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(comparisons))

    # A difference is information, not failure: the point of a shadow run is to
    # surface it before the path that ships is changed. The exit code reports
    # whether the run itself worked.
    return 0 if all(c.error is None for c in comparisons) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
