from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

try:
    from weasyprint import HTML
    _WEASYPRINT_IMPORT_ERROR: Optional[Exception] = None
except (ImportError, OSError) as exc:
    HTML = None
    _WEASYPRINT_IMPORT_ERROR = exc


def export_png(svg_path: str | Path, png_path: str | Path, width: int = 1920) -> None:
    svg = Path(svg_path)
    png = Path(png_path)
    png.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["rsvg-convert", "-w", str(width), str(svg), "-o", str(png)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "rsvg-convert failed")


def export_pdf(svg_path: str | Path, pdf_path: str | Path, title: str) -> None:
    svg = Path(svg_path)
    pdf = Path(pdf_path)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{title}</title>
  <style>
    @page {{ size: A4; margin: 12mm; }}
    body {{ margin: 0; background: #F6F0EA; }}
    .canvas {{ display: flex; align-items: center; justify-content: center; }}
    svg {{ width: 100%; height: auto; display: block; }}
  </style>
</head>
<body>
  <div class="canvas">{svg.read_text(encoding="utf-8")}</div>
</body>
</html>"""
    if HTML is not None:
        HTML(string=html, base_url=str(svg.parent)).write_pdf(str(pdf))
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
