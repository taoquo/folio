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
    manifest_path: str | None = None
    projected_values: int = 0
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
        if self.manifest_path:
            out["manifest_path"] = self.manifest_path
        if self.projected_values:
            out["projected_values"] = self.projected_values
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

    # The resolved style and the layout policy are projected into the document
    # rather than edited into the template, so the change is one configuration
    # value away from being undone.
    projected = _project(genre, language, fixture)
    if projected is not None:
        html = _inject(html, projected)

    output.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(template_path.parent)).write_pdf(str(output))

    manifest_path = None
    if _projection_enabled("FOLIO_BUILD_MANIFEST", default=True):
        manifest_path = _write_manifest(output, document.id, template_path)

    outcome = BuildOutcome(
        document_id=document.id, path=str(output), pipeline="ir", primary="ir",
        pages=_page_count(output), filled=filled.filled, missing=filled.missing,
    )
    if manifest_path:
        outcome.manifest_path = str(manifest_path)
    if projected is not None:
        outcome.projected_values = len(projected.projected)
    return outcome


def _projection_enabled(name: str, *, default: bool) -> bool:
    """Whether a projection stage is on.

    Read at call time rather than import time so a test can exercise both
    settings in one process, which is how the off switch is proven to work.
    """
    import os

    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"off", "0", "false", "no"}


def _project(genre: str, language: str, fixture: dict[str, Any]):
    """The projection for this document, or None when it is switched off.

    On by default. Seven document types were measured with it on and off and
    produced the same pages at SSIM 1.00000, because the values projected are
    the ones the templates already use. The switch remains so the next change to
    a projection can be compared against this behaviour.
    """
    if not _projection_enabled("FOLIO_STYLE_PROJECTION", default=True):
        return None
    import projection

    include_policy = _projection_enabled("FOLIO_LAYOUT_POLICY", default=True)
    return projection.combined(genre, language, include_policy=include_policy)


def _inject(html: str, projected: Any) -> str:
    import projection

    return projection.inject(html, projected)


def _write_manifest(pdf: Path, document_id: str, template_path: Path) -> Path:
    """Record what produced this artifact.

    Written beside the artifact so the two travel together. A manifest that is
    separate from its artifact is one that gets separated from it.
    """
    import build_manifest

    manifest = build_manifest.capture({
        "document_id": document_id,
        "template": template_path.name,
    })
    path = pdf.with_suffix(pdf.suffix + ".manifest.json")
    path.write_text(
        __import__("json").dumps(manifest.to_json(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


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
    """The fixture a genre is built from.

    Delegates to `fidelity._fixture_for` rather than scoring its own candidates.
    Two choosers meant two answers: this one and the fidelity one selected
    different documents for the same genre, so comparing the two build paths
    compared two different documents and reported a difference that belonged to
    the harness rather than to the engine.
    """
    import fidelity

    return fidelity._fixture_for(genre, language)


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
    if outcome.projected_values:
        lines.append(f"  projected   {outcome.projected_values} style value(s)")
    if outcome.manifest_path:
        lines.append(f"  manifest    {Path(outcome.manifest_path).name}")
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
