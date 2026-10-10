#!/usr/bin/env python3
"""folio document build

Builds a finished document from content, choosing the path by configuration.

Two different operations live in this repository and they should not be
confused:

  build.py            renders a *template* to a PDF. The template still contains
                      its `{{...}}` fields, so the result is a structural
                      example: it shows where content goes.
  document_build.py   renders *content* to a finished document. The fields are
                      filled, and the result is what a reader receives.

The pipeline variable selects how the second one is produced:

  FOLIO_PIPELINE=legacy      fill the template and render it
  FOLIO_PIPELINE=ir-shadow   deliver the template result, also build the IR one
                             and compare them
  FOLIO_PIPELINE=ir          build from the Document IR (the default)

Both paths are real, both are runnable, and the choice is one variable. That is
what makes a migration safe: the fallback is a configuration change, not a
revert.

Usage:
    python3 scripts/document_build.py build --fixture references/fixtures/document/canonical/canonical-zh-one-pager.yaml
    python3 scripts/document_build.py build --genre one-pager --lang zh-Hans-CN --out dist/
    python3 scripts/document_build.py compare --fixture <path> --keep dist/compare
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = ROOT / "references" / "fixtures" / "document"


@dataclass
class BuildOutcome:
    """What a document build produced."""

    document_id: str
    path: str
    pipeline: str
    primary: str
    pages: int | None = None
    filled: int = 0
    missing: list[str] = field(default_factory=list)
    shadow_path: str | None = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "document_id": self.document_id,
            "path": self.path,
            "pipeline": self.pipeline,
            "primary": self.primary,
            "filled": self.filled,
            "missing_count": len(self.missing),
        }
        if self.pages is not None:
            out["pages"] = self.pages
        if self.shadow_path:
            out["shadow_path"] = self.shadow_path
        if self.error:
            out["error"] = self.error
        return out


def _content_of(fixture: dict[str, Any]) -> dict[str, str]:
    """A fixture's values, keyed the way the bridge expects them."""
    return {
        (k[2:-2] if k.startswith("{{") and k.endswith("}}") else k): v
        for k, v in (fixture.get("content") or {}).items()
    }


def _template_for(fixture: dict[str, Any]) -> Path:
    from shadow import _template_for

    path = _template_for(fixture)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"no template for genre={fixture.get('genre')}")
    return path


def build_legacy(fixture: dict[str, Any], output: Path) -> BuildOutcome:
    """Fill the template and render it, without the IR.

    This is the path the migration falls back to, so it is kept working and
    kept independent of the IR modules.
    """
    from shadow import _legacy_html
    from weasyprint import HTML

    template_path = _template_for(fixture)
    template_text = template_path.read_text(encoding="utf-8")
    html = _legacy_html(template_text, fixture.get("content") or {})

    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(template_path.parent)).write_pdf(str(output))
    return BuildOutcome(
        document_id=str(fixture.get("id", output.stem)),
        path=str(output), pipeline="legacy", primary="template",
        pages=_page_count(output),
    )


def build_ir(fixture: dict[str, Any], output: Path) -> BuildOutcome:
    """Build from the Document IR.

    The document is constructed through the bridge, validated, and projected by
    the skeleton writer, which fills the template's own markup. The IR is the
    input; the template is the renderer's business.
    """
    from document_ir.bridge import bridge_template, default_map_for
    from document_ir.validate import validate
    from document_ir.writers.skeleton import attach_ids, fill_template
    from weasyprint import HTML

    template_path = _template_for(fixture)
    template_text = template_path.read_text(encoding="utf-8")
    genre = str(fixture.get("genre", ""))
    language = str(fixture.get("language", "en-US"))

    document = bridge_template(
        template_text,
        _content_of(fixture),
        document_id=str(fixture.get("id", output.stem)),
        lang=language,
        genre=genre,
        bridge_map=default_map_for(genre, language),
    )
    report = validate(document)
    if report.errors:
        return BuildOutcome(
            document_id=document.id, path=str(output), pipeline="ir", primary="ir",
            error=f"validation failed: {report.errors[0].code}",
        )

    filled = fill_template(template_text, document)
    html = attach_ids(filled.html, document)

    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(template_path.parent)).write_pdf(str(output))
    return BuildOutcome(
        document_id=document.id, path=str(output), pipeline="ir", primary="ir",
        pages=_page_count(output), filled=filled.filled, missing=filled.missing,
    )


def _page_count(pdf: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return None


def build(
    fixture: dict[str, Any], output: Path, *, pipeline: str | None = None, keep: Path | None = None
) -> BuildOutcome:
    """Build one document through the configured path.

    `ir-shadow` delivers the template result and also builds the IR one, so the
    comparison runs in production conditions rather than only in a test.
    """
    import pipeline as pipeline_module

    selected = pipeline_module.resolve(pipeline)

    if selected.mode == "ir":
        return build_ir(fixture, output)

    if selected.mode == "ir-shadow":
        delivered = build_legacy(fixture, output)
        shadow_dir = keep or Path(tempfile.mkdtemp(prefix="folio-shadow-"))
        shadow_dir.mkdir(parents=True, exist_ok=True)
        shadow = build_ir(fixture, shadow_dir / output.name)
        delivered.shadow_path = shadow.path
        delivered.pipeline = "ir-shadow"
        return delivered

    return build_legacy(fixture, output)


def _fixture_for_genre(genre: str, language: str | None) -> Path | None:
    import corpus

    best: tuple[int, Path] | None = None
    for path in corpus.discover_fixtures():
        try:
            data = corpus.load_fixture(path)
        except Exception:
            continue
        if data.get("genre") != genre or data.get("adversarial"):
            continue
        if language and not str(data.get("language", "")).startswith(language[:2]):
            continue
        score = 2 if path.stem.startswith("canonical-") else 1
        if best is None or score > best[0]:
            best = (score, path)
    return best[1] if best else None


def render_text(outcome: BuildOutcome) -> str:
    lines = [f"Document build — {outcome.document_id}", ""]
    lines.append(f"  pipeline    {outcome.pipeline} ({outcome.primary})")
    lines.append(f"  output      {outcome.path}")
    if outcome.pages is not None:
        lines.append(f"  pages       {outcome.pages}")
    lines.append(f"  filled      {outcome.filled} placeholder(s)")
    if outcome.missing:
        lines.append(f"  unfilled    {len(outcome.missing)} (a language mismatch, not a defect)")
    if outcome.shadow_path:
        lines.append(f"  shadow      {outcome.shadow_path}")
    if outcome.error:
        lines.append("")
        lines.append(f"  ERROR: {outcome.error}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    import corpus
    import pipeline as pipeline_module

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("build", "build one document"),
                            ("compare", "build both paths and compare")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--fixture", type=Path)
        cmd.add_argument("--genre")
        cmd.add_argument("--lang")
        cmd.add_argument("--out", type=Path, default=ROOT / "dist" / "documents")
        cmd.add_argument("--pipeline", choices=pipeline_module.MODES)
        cmd.add_argument("--keep", type=Path)
        cmd.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    fixture_path = args.fixture
    if fixture_path is None:
        if not args.genre:
            print("ERROR: give --fixture or --genre")
            return 2
        fixture_path = _fixture_for_genre(args.genre, args.lang)
        if fixture_path is None:
            print(f"ERROR: no fixture for genre={args.genre}")
            return 2
    if not fixture_path.is_absolute():
        fixture_path = ROOT / fixture_path
    if not fixture_path.is_file():
        print(f"ERROR: fixture not found: {fixture_path}")
        return 2

    data = corpus.load_fixture(fixture_path)
    name = f"{data.get('id', fixture_path.stem)}.pdf"

    if args.command == "build":
        output = args.out / name
        outcome = build(data, output, pipeline=args.pipeline, keep=args.keep)
        if args.format == "json":
            print(json.dumps(outcome.to_json(), indent=2, ensure_ascii=False))
        else:
            print(render_text(outcome))
        return 0 if not outcome.error else 1

    # compare: both paths, side by side, in production conditions.
    work = args.keep or Path(tempfile.mkdtemp(prefix="folio-compare-"))
    work.mkdir(parents=True, exist_ok=True)
    legacy = build_legacy(data, work / "legacy" / name)
    ir = build_ir(data, work / "ir" / name)

    payload: dict[str, Any] = {
        "fixture": fixture_path.stem,
        "legacy": legacy.to_json(),
        "ir": ir.to_json(),
        "pages_match": legacy.pages == ir.pages and legacy.pages is not None,
        "kept_at": str(work),
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"Compare — {fixture_path.stem}")
        print("")
        print(f"  legacy   {legacy.path}  pages={legacy.pages}")
        print(f"  ir       {ir.path}  pages={ir.pages}  filled={ir.filled}")
        print(f"  pages match   {'yes' if payload['pages_match'] else 'NO'}")
        print(f"  artifacts kept at {work}")

    return 0 if payload["pages_match"] and not ir.error else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
