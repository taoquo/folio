#!/usr/bin/env python3
"""folio determinism check

Renders the same source repeatedly, each in a fresh process, and compares what
the reader actually receives: page count, embedded fonts, rasterised page, and
extracted text.

PDF bytes are deliberately not the signal. WeasyPrint's zlib streams differ
between processes, so a byte digest reports compression noise as a regression
while the visible page is identical. Comparing content keeps the check honest.

Rendering in a separate process matters too: repeating the render inside one
interpreter measures in-process caching, not reproducibility.

Usage:
    python3 scripts/determinism.py                      # every HTML target, 3 repeats
    python3 scripts/determinism.py resume-en            # one target
    python3 scripts/determinism.py --repeat 5 --format json
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from page_contracts import HTML_TARGETS  # noqa: E402

TEMPLATES = ROOT / "assets" / "templates"
DEFAULT_DPI = 160

# Rendered in a child process so each repeat starts from a clean interpreter.
_RENDER_CHILD = """
import sys
from pathlib import Path
from weasyprint import HTML

source, output = Path(sys.argv[1]), Path(sys.argv[2])
HTML(str(source), base_url=str(source.parent)).write_pdf(str(output))
"""


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_once(source: Path, out: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _RENDER_CHILD, str(source), str(out)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    if result.returncode != 0 or not out.is_file():
        detail = (result.stderr or result.stdout or "render failed").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "render failed")


def _page_count(pdf: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return None


def _font_names(pdf: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["pdffonts", str(pdf)], capture_output=True, text=True, check=False, timeout=30
        )
        names = []
        for line in (out.stdout or "").splitlines()[2:]:
            if line.strip():
                names.append(line.split()[0])
        return sorted(names)
    except (OSError, subprocess.SubprocessError):
        return []


def _raster_digest(pdf: Path, workdir: Path, dpi: int) -> str | None:
    prefix = workdir / f"{pdf.stem}-raster"
    try:
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", "-f", "1", "-l", "1", str(pdf), str(prefix)],
            capture_output=True,
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    pages = sorted(workdir.glob(f"{pdf.stem}-raster*.png"))
    return _sha256_file(pages[0]) if pages else None


def _text_digest(pdf: Path) -> str | None:
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or "").strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


@dataclass
class DeterminismResult:
    target: str
    source: str
    repeats: int
    pages: list[int | None] = field(default_factory=list)
    fonts: list[list[str]] = field(default_factory=list)
    rasters: list[str | None] = field(default_factory=list)
    texts: list[str | None] = field(default_factory=list)
    pdf_digests: list[str] = field(default_factory=list)
    error: str | None = None

    def _varying(self, values: list) -> bool:
        return len({json.dumps(v, sort_keys=True) for v in values}) > 1

    @property
    def deterministic(self) -> bool:
        if self.error or len(self.pages) < 2:
            return False
        return not any(
            self._varying(values)
            for values in (self.pages, self.fonts, self.rasters, self.texts)
        )

    @property
    def byte_stable(self) -> bool:
        """Whether PDF bytes also matched. Compression makes this advisory."""
        return len(set(self.pdf_digests)) == 1 and bool(self.pdf_digests)

    def unstable_signals(self) -> list[str]:
        signals = []
        for name, values in (
            ("pages", self.pages),
            ("fonts", self.fonts),
            ("raster", self.rasters),
            ("text", self.texts),
        ):
            if self._varying(values):
                signals.append(name)
        return signals

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "source": self.source,
            "repeats": self.repeats,
            "deterministic": self.deterministic,
            "byte_stable": self.byte_stable,
            "unstable_signals": self.unstable_signals(),
            "pages": self.pages,
            "pdf_digests": [d[:16] for d in self.pdf_digests],
            "error": self.error,
        }


def check_target(target: str, repeats: int, workdir: Path, dpi: int) -> DeterminismResult:
    spec = HTML_TARGETS[target]
    source = TEMPLATES / spec.source
    result = DeterminismResult(target=target, source=spec.source, repeats=repeats)

    if not source.is_file():
        result.error = f"template not found: {source}"
        return result

    for index in range(repeats):
        out = workdir / f"{target}-{index}.pdf"
        try:
            _render_once(source, out)
        except Exception as exc:
            result.error = str(exc)[:200]
            return result

        result.pages.append(_page_count(out))
        result.fonts.append(_font_names(out))
        result.rasters.append(_raster_digest(out, workdir, dpi))
        result.texts.append(_text_digest(out))
        result.pdf_digests.append(_sha256_file(out) or "")

    return result


def render_text(results: list[DeterminismResult], repeats: int) -> str:
    lines = [f"Determinism check ({repeats} fresh renders per target, compared on content)", ""]
    failed = []
    for item in results:
        if item.error:
            lines.append(f"  FAIL {item.target:<18} {item.error}")
            failed.append(item)
            continue
        if item.deterministic:
            note = "" if item.byte_stable else "  (pdf bytes vary; content identical)"
            lines.append(f"  OK   {item.target:<18} pages {item.pages}{note}")
        else:
            lines.append(f"  FAIL {item.target:<18} unstable: {', '.join(item.unstable_signals())}")
            failed.append(item)

    lines.append("")
    if failed:
        lines.append(f"ERROR: {len(failed)} of {len(results)} target(s) are not deterministic")
    else:
        lines.append(f"OK: all {len(results)} target(s) are deterministic across {repeats} runs")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="target names (default: every HTML target)")
    parser.add_argument("--repeat", type=int, default=3, help="renders per target (default: 3)")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="raster DPI for comparison")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--keep", type=Path, help="keep rendered PDFs in this directory")
    args = parser.parse_args(argv)

    if args.repeat < 2:
        print("ERROR: --repeat must be at least 2 to compare anything")
        return 2

    targets = args.targets or list(HTML_TARGETS)
    unknown = [t for t in targets if t not in HTML_TARGETS]
    if unknown:
        print(f"ERROR: unknown target(s): {', '.join(unknown)}")
        return 2

    os.environ.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())

    results: list[DeterminismResult] = []
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        for target in targets:
            results.append(check_target(target, args.repeat, args.keep, args.dpi))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            for target in targets:
                results.append(check_target(target, args.repeat, workdir, args.dpi))

    if args.format == "json":
        print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
    else:
        print(render_text(results, args.repeat))

    return 0 if all(r.deterministic for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
