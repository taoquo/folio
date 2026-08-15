from __future__ import annotations

import subprocess
import re
import shutil
import tempfile
from html import escape as html_escape
from pathlib import Path
from typing import Optional

HTML = None
_WEASYPRINT_IMPORT_ERROR: Optional[Exception] = None


def _get_weasyprint_html():
    global HTML, _WEASYPRINT_IMPORT_ERROR
    if HTML is not None:
        return HTML
    if _WEASYPRINT_IMPORT_ERROR is not None:
        return None
    try:
        from weasyprint import HTML as weasy_html
    except (ImportError, OSError) as exc:
        _WEASYPRINT_IMPORT_ERROR = exc
        return None
    HTML = weasy_html
    _WEASYPRINT_IMPORT_ERROR = None
    return HTML


def export_png(
    svg_path: str | Path,
    png_path: str | Path,
    width: int = 1920,
    *,
    profile: str = "artifact",
    title: str = "Folio Drawing",
    language: str = "en",
    background: str = "#F6F0EA",
) -> None:
    from drawing.output import normalize_output_profile

    profile = normalize_output_profile(profile)
    svg = Path(svg_path)
    png = Path(png_path)
    png.parent.mkdir(parents=True, exist_ok=True)
    if profile == "page-preview":
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            raise RuntimeError("pdftoppm is required for page-preview PNG export")
        with tempfile.TemporaryDirectory(prefix="folio-page-preview-") as temp_dir:
            pdf_path = Path(temp_dir) / "preview.pdf"
            prefix = Path(temp_dir) / "preview"
            export_pdf(svg, pdf_path, title, language, profile, background)
            result = subprocess.run(
                [pdftoppm, "-f", "1", "-l", "1", "-singlefile", "-r", "150", "-png", str(pdf_path), str(prefix)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "pdftoppm failed")
            shutil.copyfile(prefix.with_suffix(".png"), png)
        return
    result = subprocess.run(
        ["rsvg-convert", "-w", str(width), str(svg), "-o", str(png)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "rsvg-convert failed")


def export_pdf(
    svg_path: str | Path,
    pdf_path: str | Path,
    title: str,
    language: str = "en",
    profile: str = "page-preview",
    background: str = "#F6F0EA",
) -> None:
    from drawing.output import normalize_output_profile

    profile = normalize_output_profile(profile)
    svg = Path(svg_path)
    pdf = Path(pdf_path)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    safe_title = html_escape(title, quote=True)
    safe_language = html_escape(language or "en", quote=True)
    safe_background = html_escape(background or "#F6F0EA", quote=True)
    svg_source = svg.read_text(encoding="utf-8")
    page_rule = "size: A4; margin: 12mm;"
    canvas_rule = "display: flex; align-items: center; justify-content: center;"
    if profile in {"artifact", "embed"}:
        width, height = _svg_dimensions(svg_source)
        width_in, height_in = width / 96, height / 96
        page_rule = f"size: {width_in:.4f}in {height_in:.4f}in; margin: 0;"
        canvas_rule += f" width: {width_in:.4f}in; height: {height_in:.4f}in;"
    html = f"""<!DOCTYPE html>
<html lang="{safe_language}">
<head>
  <meta charset="UTF-8">
  <title>{safe_title}</title>
  <style>
    @page {{ {page_rule} }}
    body {{ margin: 0; background: {safe_background}; }}
    .canvas {{ {canvas_rule} }}
    svg {{ width: 100%; height: auto; display: block; }}
  </style>
</head>
<body>
  <div class="canvas">{svg_source}</div>
</body>
</html>"""
    html_builder = _get_weasyprint_html()
    if html_builder is not None:
        html_builder(string=html, base_url=str(svg.parent)).write_pdf(str(pdf))
        return

    fallback = Path(__file__).resolve().parents[1] / ".venv-weasy" / "bin" / "python"
    if not fallback.exists():
        raise RuntimeError(f"weasyprint unavailable: {_WEASYPRINT_IMPORT_ERROR}")

    script = (
        "from weasyprint import HTML\n"
        "import pathlib, sys\n"
        "html_path = pathlib.Path(sys.argv[1])\n"
        "pdf_path = pathlib.Path(sys.argv[2])\n"
        "base_url = sys.argv[3]\n"
        "HTML(string=html_path.read_text(encoding='utf-8'), base_url=base_url).write_pdf(str(pdf_path))\n"
    )
    html_path = pdf.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    try:
        result = subprocess.run(
            [str(fallback), "-c", script, str(html_path), str(pdf), str(svg.parent)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        html_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "weasyprint fallback failed")


def _svg_dimensions(source: str) -> tuple[int, int]:
    match = re.search(r'viewBox=["\']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)\s*["\']', source)
    if not match:
        return 960, 540
    width, height = float(match.group(1)), float(match.group(2))
    if width <= 0 or height <= 0:
        raise ValueError("SVG viewBox dimensions must be positive")
    return int(round(width)), int(round(height))
