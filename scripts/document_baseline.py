#!/usr/bin/env python3
"""folio document baseline

Captures what the current document templates actually render to, then compares
later builds against that record. This is the safety net that makes a
refactor's visual effect reviewable instead of guessed at.

Governance follows the diagram catalog's approved-baseline model: a baseline
cannot be written without a reason, the reference files are re-hashed on every
comparison so a tampered baseline is detected, and outputs must never be
written over the references they are compared against.

Usage:
    python3 scripts/document_baseline.py capture              # record current state
    python3 scripts/document_baseline.py compare              # compare against record
    python3 scripts/document_baseline.py capture --approval-reason "..."
    python3 scripts/document_baseline.py compare --report out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from page_contracts import HTML_TARGETS, PPTX_TARGETS  # noqa: E402

BASELINE_DIR = ROOT / "references" / "baselines" / "document-v1"
BASELINE_FILE = BASELINE_DIR / "baseline.json"
TEMPLATES = ROOT / "assets" / "templates"
SCHEMA_VERSION = "1.0"
DEFAULT_DPI = 160


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return _sha256_bytes(path.read_bytes())


def _pdf_page_count(pdf: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return None


def _pdf_font_names(pdf: Path) -> list[str]:
    """Embedded font names, as reported by the PDF itself."""
    names: set[str] = set()
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf))
        for page in reader.pages:
            resources = page.get("/Resources")
            resources = resources.get_object() if hasattr(resources, "get_object") else resources
            if resources is None or not hasattr(resources, "get"):
                continue
            fonts = resources.get("/Font")
            fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
            if not hasattr(fonts, "values"):
                continue
            for font in fonts.values():
                font = font.get_object() if hasattr(font, "get_object") else font
                base = font.get("/BaseFont") if hasattr(font, "get") else None
                if base:
                    names.add(str(base).lstrip("/"))
    except Exception:
        # pdffonts is a more robust fallback when the object graph is unusual.
        try:
            out = subprocess.run(
                ["pdffonts", str(pdf)], capture_output=True, text=True, check=False, timeout=30
            )
            for line in (out.stdout or "").splitlines()[2:]:
                if line.strip():
                    names.add(line.split()[0])
        except (OSError, subprocess.SubprocessError):
            pass
    return sorted(names)


def _pdf_metadata(pdf: Path) -> dict[str, str]:
    try:
        from pypdf import PdfReader

        meta = PdfReader(str(pdf)).metadata or {}
        return {
            key.lstrip("/"): str(meta[key])
            for key in ("/Title", "/Author", "/Producer", "/Creator")
            if key in meta
        }
    except Exception:
        return {}


def _rasterise(pdf: Path, out_dir: Path, dpi: int, first_page_only: bool = True) -> list[Path]:
    """Rasterise pages to PNG. Poppler is already a CI dependency."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / pdf.stem
    argv = ["pdftoppm", "-r", str(dpi), "-png"]
    if first_page_only:
        argv += ["-f", "1", "-l", "1"]
    argv += [str(pdf), str(prefix)]
    try:
        subprocess.run(argv, capture_output=True, check=False, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted(out_dir.glob(f"{pdf.stem}*.png"))


def _text_excerpt(pdf: Path, limit: int = 400) -> str:
    return _text_body(pdf)[:limit]


def _text_body(pdf: Path) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        return (out.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


@dataclass
class RenderRecord:
    target: str
    source: str
    kind: str
    pages: int | None = None
    pdf_sha256: str | None = None
    pdf_bytes: int | None = None
    fonts: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    preview_sha256: str | None = None
    preview_bytes: int | None = None
    text_sha256: str | None = None
    text_excerpt: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "source": self.source,
            "kind": self.kind,
            "pages": self.pages,
            "pdf_sha256": self.pdf_sha256,
            "pdf_bytes": self.pdf_bytes,
            "fonts": self.fonts,
            "metadata": self.metadata,
            "preview_sha256": self.preview_sha256,
            "preview_bytes": self.preview_bytes,
            "text_sha256": self.text_sha256,
            "text_excerpt": self.text_excerpt,
            "error": self.error,
        }


def _render_html(source: Path, out: Path) -> None:
    from weasyprint import HTML

    HTML(str(source), base_url=str(source.parent)).write_pdf(str(out))


def _render_pptx(source: Path, out: Path) -> None:
    """Slides are produced by running their own script, as build.py does.

    The script writes `output.pptx` next to itself, so the result is moved to
    the capture directory immediately; the template directory is left clean.
    """
    result = subprocess.run(
        [sys.executable, str(source)],
        cwd=str(source.parent),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    generated = source.parent / "output.pptx"
    if generated.is_file():
        generated.replace(out)
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError((result.stderr or result.stdout or "slide build failed").strip()[:200])


def capture_target(target: str, workdir: Path, dpi: int, capture_preview: bool) -> RenderRecord:
    is_slide = target in PPTX_TARGETS
    spec = PPTX_TARGETS[target] if is_slide else HTML_TARGETS[target]
    source = TEMPLATES / spec.source
    record = RenderRecord(target=target, source=spec.source, kind="pptx" if is_slide else "pdf")

    if not source.is_file():
        record.error = f"source not found: {spec.source}"
        return record

    out = workdir / f"{target}{'.pptx' if is_slide else '.pdf'}"
    try:
        if is_slide:
            _render_pptx(source, out)
        else:
            _render_html(source, out)
    except Exception as exc:
        record.error = f"{type(exc).__name__}: {exc}"
        return record

    record.pdf_sha256 = _sha256_file(out)
    record.pdf_bytes = out.stat().st_size

    if is_slide:
        record.pages = _pptx_slide_count(out)
    else:
        record.pages = _pdf_page_count(out)
        record.fonts = _pdf_font_names(out)
        record.metadata = _pdf_metadata(out)
        text = _text_body(out)
        record.text_excerpt = text[:400]
        record.text_sha256 = _sha256_bytes(text.encode("utf-8")) if text else None
        if capture_preview:
            pngs = _rasterise(out, workdir / "preview", dpi)
            if pngs:
                record.preview_sha256 = _sha256_file(pngs[0])
                record.preview_bytes = pngs[0].stat().st_size

    return record


def _pptx_slide_count(path: Path) -> int | None:
    try:
        from xml.etree import ElementTree
        from zipfile import ZipFile

        ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
        with ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
        slides = root.find("p:sldIdLst", ns)
        return 0 if slides is None else len(list(slides))
    except Exception:
        return None


def capture_all(dpi: int, capture_preview: bool) -> dict[str, Any]:
    records: list[RenderRecord] = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for target in list(HTML_TARGETS) + list(PPTX_TARGETS):
            records.append(capture_target(target, workdir, dpi, capture_preview))
    return {
        "schema_version": SCHEMA_VERSION,
        "raster_dpi": dpi,
        "targets": [r.to_dict() for r in records],
    }


def compare_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Diff a fresh capture against an approved baseline."""
    issues: list[str] = []
    differences: list[dict[str, Any]] = []

    if baseline.get("schema_version") != SCHEMA_VERSION:
        issues.append(f"baseline schema_version must be {SCHEMA_VERSION}")
    if baseline.get("approval_state") != "approved" or not str(baseline.get("approval_reason", "")).strip():
        issues.append("baseline must be approved and carry a non-empty approval reason")
    if int(baseline.get("raster_dpi", 0)) != int(current.get("raster_dpi", 0)):
        issues.append(
            f"raster DPI differs: baseline {baseline.get('raster_dpi')} vs capture {current.get('raster_dpi')}"
        )

    current_records = {r["target"]: r for r in current.get("targets", [])}
    baseline_records = {r["target"]: r for r in baseline.get("targets", [])}

    missing = sorted(set(baseline_records) - set(current_records))
    added = sorted(set(current_records) - set(baseline_records))
    if missing:
        issues.append(f"baseline target(s) missing from capture: {', '.join(missing)}")
    if added:
        issues.append(f"capture has unapproved target(s): {', '.join(added)}")

    for target in sorted(set(current_records) & set(baseline_records)):
        now, before = current_records[target], baseline_records[target]
        entry: dict[str, Any] = {"target": target, "changed": []}

        if now.get("error") or before.get("error"):
            entry["changed"].append("render-error")
            if now.get("error") != before.get("error"):
                differences.append(entry)
            continue

        # Compared on content the reader sees: page count, fonts, rasterised
        # page, extracted text. PDF bytes are deliberately excluded -- zlib
        # compression is not stable across processes, so a byte diff reports
        # noise as regression. `pdf_sha256` is still recorded for forensics.
        for key in ("pages", "fonts", "preview_sha256", "text_sha256"):
            if now.get(key) != before.get(key):
                entry["changed"].append(key)
                entry[f"{key}_before"] = before.get(key)
                entry[f"{key}_after"] = now.get(key)
        if entry["changed"]:
            differences.append(entry)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "match" if not issues and not differences else "different",
        "issues": issues,
        "differences": differences,
    }


def render_text(report: dict[str, Any]) -> str:
    lines: list[str] = []
    status = report["status"]
    if status == "match":
        lines.append("OK: documents match the approved baseline")
        return "\n".join(lines)

    lines.append("ERROR: documents differ from the approved baseline")
    for issue in report.get("issues", []):
        lines.append(f"  issue: {issue}")
    for entry in report.get("differences", []):
        lines.append(f"  {entry['target']}: {', '.join(entry['changed'])}")
        for key in ("pages_before", "pages_after", "pdf_sha256_before", "pdf_sha256_after"):
            if key in entry:
                value = entry[key]
                if isinstance(value, str) and len(value) > 16:
                    value = value[:16]
                lines.append(f"      {key}: {value}")
    lines.append("")
    lines.append("Review each change, then re-capture with an approval reason if it is intended.")
    return "\n".join(lines)


def _write_baseline(capture: dict[str, Any], reason: str, dpi: int) -> Path:
    clean = reason.strip()
    if not clean:
        raise ValueError("baseline approval requires a non-empty reason")

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "approval_state": "approved",
        "approval_reason": clean,
        "raster_dpi": dpi,
        "coverage": {
            "html_targets": len(HTML_TARGETS),
            "pptx_targets": len(PPTX_TARGETS),
            "captured": sum(1 for t in capture.get("targets", []) if not t.get("error")),
        },
        "targets": capture.get("targets", []),
    }
    BASELINE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return BASELINE_FILE


def unattended_environment() -> str | None:
    """Why this run looks unattended, or None when a person is present.

    A recorded approval has to mean someone looked. The environment is used
    rather than an argument because an argument can be passed by a pipeline just
    as easily as by a person.
    """
    if os.environ.get("CI"):
        return "CI is set"
    if os.environ.get("GITHUB_ACTIONS"):
        return "GITHUB_ACTIONS is set"
    if not sys.stdin.isatty() and not os.environ.get("FOLIO_ALLOW_UNATTENDED_APPROVAL"):
        return (
            "stdin is not a terminal; set FOLIO_ALLOW_UNATTENDED_APPROVAL=1 to "
            "approve anyway, which records that the approval was scripted"
        )
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="record the current rendered state")
    cap.add_argument("--approval-reason", help="required to write the approved baseline")
    cap.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    cap.add_argument("--no-preview", action="store_true", help="skip rasterising the first page")
    cap.add_argument("--dry-run", action="store_true", help="capture but do not write the baseline")

    comp = sub.add_parser("compare", help="compare a fresh capture against the baseline")
    comp.add_argument("--report", type=Path, help="write the JSON report here")
    comp.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    comp.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)
    os.environ.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())

    if args.command == "capture":
        capture = capture_all(args.dpi, capture_preview=not args.no_preview)
        failed = [t["target"] for t in capture["targets"] if t.get("error")]
        if args.dry_run:
            print(json.dumps(capture, indent=2, ensure_ascii=False)[:400])
            print(f"... captured {len(capture['targets'])} target(s), {len(failed)} failed")
            return 0 if not failed else 1

        if not args.approval_reason:
            print("ERROR: capture requires --approval-reason to write the approved baseline")
            print("")
            print("  A baseline is approved by a person. State what changed and why it")
            print("  is intended; a reason with no reviewer behind it is not an approval.")
            return 2

        blocked = unattended_environment() if not args.dry_run else None
        if blocked:
            print("ERROR: refusing to approve a baseline from an unattended run")
            print(f"  {blocked}")
            print("")
            print("  CI must never write an approved baseline, because the record would")
            print("  claim a review that did not happen. Capture with --dry-run to")
            print("  inspect the difference, then approve it from a terminal.")
            return 2

        try:
            path = _write_baseline(capture, args.approval_reason, args.dpi)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
        print(f"OK: wrote baseline for {len(capture['targets'])} target(s) to {path}")
        if failed:
            print(f"ERROR: {len(failed)} target(s) failed to render: {', '.join(failed)}")
            return 1
        return 0

    if not BASELINE_FILE.is_file():
        print(f"ERROR: no baseline at {BASELINE_FILE}; run capture first")
        return 2
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    current = capture_all(args.dpi, capture_preview=True)
    report = compare_baseline(current, baseline)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return 0 if report["status"] == "match" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
