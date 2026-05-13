#!/usr/bin/env python3
"""folio build & check

Usage:
    python3 scripts/build.py                      # build all examples (HTML + diagrams + PPTX)
    python3 scripts/build.py resume               # build one template, print pages + fonts
    python3 scripts/build.py --check              # scan templates for CSS rule violations
    python3 scripts/build.py --check -v           # verbose (show each scanned file)
    python3 scripts/build.py --sync               # check CSS token drift across templates
    python3 scripts/build.py --doctor             # check local PDF/PPTX/diagram dependencies
    python3 scripts/build.py --verify             # build all + page count + font checks
    python3 scripts/build.py --verify resume-en   # single target full verification
    python3 scripts/build.py --check-placeholders path/to/doc.html
    python3 scripts/build.py --check-orphans      # scan example PDFs for orphan text
    python3 scripts/build.py --check-orphans path/to/doc.pdf
    python3 scripts/build.py --check-rhythm       # warn on monotonous slide sequences
    python3 scripts/build.py --check-rhythm slides slides-en
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import contextlib
import io
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from diagram_models import load_diagram_spec_file
from diagram_render_svg import render_diagram_svg
from diagram_semantic_planning import plan_architecture_from_text
from shared import (
    COOL_GRAY_BLOCKLIST,
    DIAGRAMS,
    DEMOS,
    EXAMPLES,
    GENERATED_DIAGRAM_PDF,
    GENERATED_DIAGRAM_PNG,
    GENERATED_DIAGRAM_SVG,
    ROOT,
    TEMPLATES,
    TOKENS_FILE,
)


@dataclass(frozen=True)
class PageSpec:
    source: str
    min_pages: int
    max_pages: int


# name -> page spec
HTML_TARGETS: dict[str, PageSpec] = {
    # Chinese
    "one-pager":    PageSpec("one-pager.html", 1, 1),
    "letter":       PageSpec("letter.html", 1, 1),
    "long-doc":     PageSpec("long-doc.html", 5, 9),
    "portfolio":    PageSpec("portfolio.html", 4, 8),
    "resume":       PageSpec("resume.html", 2, 2),
    # English
    "one-pager-en": PageSpec("one-pager-en.html", 1, 1),
    "letter-en":    PageSpec("letter-en.html", 1, 1),
    "long-doc-en":  PageSpec("long-doc-en.html", 5, 9),
    "portfolio-en": PageSpec("portfolio-en.html", 4, 8),
    "resume-en":    PageSpec("resume-en.html", 2, 2),
    # Equity Report
    "equity-report":    PageSpec("equity-report.html", 2, 3),
    "equity-report-en": PageSpec("equity-report-en.html", 2, 3),
    # Changelog
    "changelog":    PageSpec("changelog.html", 1, 2),
    "changelog-en": PageSpec("changelog-en.html", 1, 2),
}
PPTX_TARGETS: dict[str, PageSpec] = {
    "slides":    PageSpec("slides.py", 4, 10),
    "slides-en": PageSpec("slides-en.py", 4, 10),
}

# Diagram HTMLs live in a separate directory and have no page-count contract.
DIAGRAM_TARGETS: dict[str, str] = {
    "diagram-architecture": "architecture.html",
    "diagram-flowchart":    "flowchart.html",
    "diagram-quadrant":     "quadrant.html",
    "diagram-bar-chart":    "bar-chart.html",
    "diagram-line-chart":   "line-chart.html",
    "diagram-donut-chart":  "donut-chart.html",
    "diagram-state-machine": "state-machine.html",
    "diagram-timeline":      "timeline.html",
    "diagram-swimlane":      "swimlane.html",
    "diagram-tree":          "tree.html",
    "diagram-layer-stack":   "layer-stack.html",
    "diagram-venn":          "venn.html",
    "diagram-candlestick":   "candlestick.html",
    "diagram-waterfall":     "waterfall.html",
}
DIAGRAM_ARTIFACT_TARGETS: dict[str, dict[str, str]] = {
    "artifact-architecture-demo": {
        "text": "references/fixtures/architecture-demo.txt",
        "title": "Agent Runtime",
        "svg": "agent-runtime-demo.svg",
        "png": "agent-runtime-demo.png",
        "pdf": "agent-runtime-demo.pdf",
        "showcase": {
            "basename": "demo-architecture",
            "eyebrow": "Architecture Demo",
            "heading": "Agent Runtime",
            "alt": "Agent runtime architecture",
            "caption": "A request-driven agent runtime showing gateway ingress, planning, model execution, tool use, retrieval memory, and observability in Folio's warm editorial language.",
        },
    },
    "artifact-workflow-engine-demo": {
        "text": "references/fixtures/workflow-engine-demo.txt",
        "title": "Workflow Engine",
        "svg": "workflow-engine-demo.svg",
        "png": "workflow-engine-demo.png",
        "pdf": "workflow-engine-demo.pdf",
        "showcase": {
            "basename": "demo-workflow-engine",
            "eyebrow": "Architecture Demo",
            "heading": "Workflow Engine",
            "alt": "Workflow engine architecture",
            "caption": "A workflow orchestration case showing gateway ingress, orchestration, worker execution, state persistence, and event-based continuation.",
        },
    },
    "artifact-data-platform-demo": {
        "text": "references/fixtures/data-platform-demo.txt",
        "title": "Data Platform",
        "svg": "data-platform-demo.svg",
        "png": "data-platform-demo.png",
        "pdf": "data-platform-demo.pdf",
        "showcase": {
            "basename": "demo-data-platform",
            "eyebrow": "Architecture Demo",
            "heading": "Data Platform",
            "alt": "Data platform architecture",
            "caption": "A policy-driven data platform diagram showing stream ingest, transform, warehouse serving, and supporting read paths through one reusable grammar.",
        },
    },
    "artifact-uml-class-demo": {
        "spec": "references/fixtures/uml-class-demo.json",
        "svg": "uml-class-demo.svg",
        "png": "uml-class-demo.png",
        "pdf": "uml-class-demo.pdf",
        "showcase": {
            "basename": "demo-uml-class",
            "eyebrow": "UML Class Demo",
            "heading": "Agent Session Model",
            "alt": "Agent session model UML class diagram",
            "caption": "A standalone UML class artifact covering session ownership, runnable step interfaces, tool-call execution, retrieval memory, and enum-backed lifecycle state.",
        },
    },
}

_PDF_BUILD_DEPS: tuple[Any | None, Any | None, str | None] | None = None


def _dependency_fix_hint() -> str:
    return (
        "Fix: macOS: brew install pango librsvg poppler; "
        "Debian/Ubuntu: sudo apt-get install -y libpango-1.0-0 "
        "libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 libglib2.0-0 "
        "shared-mime-info librsvg2-bin poppler-utils fonts-noto-cjk; "
        "Python: python3 -m pip install weasyprint pypdf python-pptx"
    )


def _format_dependency_error(message: str) -> str:
    return f"dependency load failed: {message}. {_dependency_fix_hint()}"


def _load_diagram_exporters():
    from diagram_export import export_pdf, export_png

    return export_pdf, export_png


# ------------------------- build -------------------------

def infer_author() -> str:
    """Infer author name from git config or environment.

    Priority:
    1. git config user.name
    2. FOLIO_AUTHOR env var
    3. fallback to "Folio"
    """
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass

    if env_author := os.environ.get("FOLIO_AUTHOR"):
        return env_author

    return "Folio"


def set_pdf_metadata(pdf_path: Path, author: str | None = None) -> None:
    """Set PDF metadata using pypdf, only if placeholders are still present."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return

    if not pdf_path.exists():
        return

    reader = PdfReader(str(pdf_path))

    # Read existing metadata from WeasyPrint
    existing = reader.metadata or {}

    # Check if we need to update anything
    needs_update = False
    metadata = dict(existing)  # Copy all existing metadata

    # Only override author if it's still a placeholder
    if author and existing.get("/Author"):
        author_value = str(existing["/Author"])
        if "{{" in author_value and "}}" in author_value:
            metadata["/Author"] = author
            needs_update = True

    # Always set Producer and Creator to Folio
    if metadata.get("/Producer") != "Folio":
        metadata["/Producer"] = "Folio"
        needs_update = True
    if metadata.get("/Creator") != "Folio":
        metadata["/Creator"] = "Folio"
        needs_update = True

    if not needs_update:
        return

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    writer.add_metadata(metadata)

    with open(pdf_path, "wb") as f:
        writer.write(f)


def _load_pdf_build_deps() -> tuple[Any | None, Any | None, str | None]:
    global _PDF_BUILD_DEPS
    if _PDF_BUILD_DEPS is not None:
        return _PDF_BUILD_DEPS
    try:
        from weasyprint import HTML
        from pypdf import PdfReader
    except ImportError:
        _PDF_BUILD_DEPS = (None, None, "missing deps: pip install weasyprint pypdf --break-system-packages")
        return _PDF_BUILD_DEPS
    except OSError as exc:
        _PDF_BUILD_DEPS = (None, None, _format_dependency_error(str(exc)))
        return _PDF_BUILD_DEPS
    _PDF_BUILD_DEPS = (HTML, PdfReader, None)
    return _PDF_BUILD_DEPS


def page_count_issue(name: str, count: int, min_pages: int, max_pages: int) -> str | None:
    expected = str(min_pages) if min_pages == max_pages else f"{min_pages}-{max_pages}"
    if count < min_pages:
        return f"page underflow: {count} pages (expected {expected})"
    if count > max_pages:
        hint = ""
        if "resume" in name and count == max_pages + 1:
            hint = '; add class="resume--dense" to <body> or tighten .proj-text line-height to 1.38'
        return f"page overflow: {count} pages (expected {expected}){hint}"
    return None


def build_html(name: str, source: str, min_pages: int, max_pages: int,
               src_dir: Path = TEMPLATES) -> bool:
    HTML, PdfReader, dep_error = _load_pdf_build_deps()
    if dep_error:
        print(f"ERROR: {dep_error}")
        return False

    src = src_dir / source
    if not src.exists():
        print(f"ERROR: {name}: source not found ({src})")
        return False

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    out = EXAMPLES / f"{name}.pdf"

    # weasyprint resolves @font-face relative to CWD. Run from the source dir
    # so fonts placed next to the HTML are found.
    try:
        HTML(str(src), base_url=str(src.parent)).write_pdf(str(out))
    except Exception as exc:
        print(f"ERROR: {name}: render failed ({exc})")
        return False

    # Set PDF metadata (only replaces placeholders, preserves filled values)
    author = infer_author()
    set_pdf_metadata(out, author=author)

    n = len(PdfReader(str(out)).pages)
    issue = page_count_issue(name, n, min_pages, max_pages)
    if issue:
        print(f"ERROR: {name}: {issue}")
        return False
    print(f"OK: {name}: {n} pages")
    return True


def build_slides(name: str = "slides") -> bool:
    spec = PPTX_TARGETS.get(name)
    if spec is None:
        print(f"ERROR: {name}: unknown slides target")
        return False
    src = TEMPLATES / spec.source
    if not src.exists():
        print(f"ERROR: {name}: source not found ({src})")
        return False

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    out = EXAMPLES / f"{name}.pptx"
    result = subprocess.run(
        [sys.executable, str(src)],
        cwd=str(src.parent),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: {name}: {result.stderr.strip() or 'script failed'}")
        return False
    # The script writes output.pptx in cwd; move to examples/ under our name.
    generated = src.parent / "output.pptx"
    if generated.exists():
        generated.replace(out)
        print(f"OK: {name}: generated {out.name}")
        return True
    print(f"ERROR: {name}: output.pptx not produced")
    return False


def build_diagram_artifact(name: str) -> bool:
    config = DIAGRAM_ARTIFACT_TARGETS.get(name)
    if config is None:
        print(f"ERROR: {name}: unknown diagram artifact target")
        return False

    try:
        if "text" in config:
            text = (ROOT / config["text"]).read_text(encoding="utf-8")
            spec = plan_architecture_from_text(text, config["title"])
        else:
            spec = load_diagram_spec_file(ROOT / config["spec"])
        svg = render_diagram_svg(spec)

        GENERATED_DIAGRAM_SVG.mkdir(parents=True, exist_ok=True)
        GENERATED_DIAGRAM_PNG.mkdir(parents=True, exist_ok=True)
        GENERATED_DIAGRAM_PDF.mkdir(parents=True, exist_ok=True)

        svg_path = GENERATED_DIAGRAM_SVG / config["svg"]
        png_path = GENERATED_DIAGRAM_PNG / config["png"]
        pdf_path = GENERATED_DIAGRAM_PDF / config["pdf"]

        svg_path.write_text(svg, encoding="utf-8")
        export_pdf, export_png = _load_diagram_exporters()
        export_png(svg_path, png_path)
        export_pdf(svg_path, pdf_path, spec.title)
        _sync_diagram_showcase(config, png_path, pdf_path)
    except Exception as exc:
        print(f"ERROR: {name}: artifact build failed ({exc})")
        return False

    print(f"OK: {name}: generated {svg_path.name}, {png_path.name}, {pdf_path.name}")
    return True


def _showcase_demo_html(showcase: dict[str, str], generated_png_name: str) -> str:
    eyebrow = escape(showcase["eyebrow"])
    heading = escape(showcase["heading"])
    alt = escape(showcase["alt"])
    caption = escape(showcase["caption"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{heading} Demo</title>
<style>
  :root {{
    --parchment: #F6F0EA;
    --ivory: #FBF7F3;
    --near-black: #191514;
    --olive: #5A4A43;
    --stone: #85776F;
    --brand: #B83D2E;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    padding: 32px 24px;
    background: var(--parchment);
    color: var(--near-black);
    font-family: Charter, Georgia, serif;
  }}

  main {{
    max-width: 1000px;
    margin: 0 auto;
  }}

  .eyebrow {{
    margin: 0 0 8px;
    color: var(--stone);
    font-size: 12px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }}

  h1 {{
    margin: 0 0 16px;
    font-size: 30px;
    font-weight: 500;
    line-height: 1.15;
  }}

  .frame {{
    padding: 20px;
    background: var(--ivory);
    border: 1px solid #E9DED4;
  }}

  img {{
    display: block;
    width: 100%;
    height: auto;
  }}

  .caption {{
    margin: 14px 0 0;
    color: var(--olive);
    font-size: 15px;
  }}
</style>
</head>
<body>
  <main>
    <p class="eyebrow">{eyebrow}</p>
    <h1>{heading}</h1>
    <div class="frame">
      <img src="../diagrams/generated/png/{escape(generated_png_name)}" alt="{alt}">
    </div>
    <p class="caption">{caption}</p>
  </main>
</body>
</html>"""


def _write_showcase_png(source_png: Path, target_png: Path) -> None:
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required to build A4 showcase PNGs") from exc

    canvas_size = (1241, 1754)
    parchment = (246, 240, 234)
    ivory = (251, 247, 243)
    border = (233, 222, 212)
    pad_x = 88
    pad_top = 130
    frame_pad = 34
    frame_w = canvas_size[0] - pad_x * 2

    with Image.open(source_png) as image:
        image = image.convert("RGB")
        inner_w = frame_w - frame_pad * 2
        inner_h = int(inner_w * image.height / image.width)
        resized = ImageOps.contain(image, (inner_w, inner_h))

        frame_h = resized.height + frame_pad * 2
        frame_x = pad_x
        frame_y = pad_top
        image_x = frame_x + frame_pad + (inner_w - resized.width) // 2
        image_y = frame_y + frame_pad

        canvas = Image.new("RGB", canvas_size, parchment)
        frame = Image.new("RGB", (frame_w, frame_h), ivory)
        canvas.paste(frame, (frame_x, frame_y))

        # Draw a single warm hairline without relying on platform fonts.
        for x in range(frame_x, frame_x + frame_w):
            canvas.putpixel((x, frame_y), border)
            canvas.putpixel((x, frame_y + frame_h - 1), border)
        for y in range(frame_y, frame_y + frame_h):
            canvas.putpixel((frame_x, y), border)
            canvas.putpixel((frame_x + frame_w - 1, y), border)

        canvas.paste(resized, (image_x, image_y))
        target_png.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(target_png)


def _sync_diagram_showcase(config: dict[str, Any], png_path: Path, pdf_path: Path) -> None:
    showcase = config.get("showcase")
    if not showcase:
        return

    DEMOS.mkdir(parents=True, exist_ok=True)
    basename = showcase["basename"]
    demo_png = DEMOS / f"{basename}.png"
    demo_pdf = DEMOS / f"{basename}.pdf"
    demo_html = DEMOS / f"{basename}.html"

    _write_showcase_png(png_path, demo_png)
    demo_pdf.write_bytes(pdf_path.read_bytes())
    demo_html.write_text(_showcase_demo_html(showcase, config["png"]), encoding="utf-8")


def build_all() -> int:
    failures = 0
    for name, spec in HTML_TARGETS.items():
        if not build_html(name, spec.source, spec.min_pages, spec.max_pages):
            failures += 1
    for name, source in DIAGRAM_TARGETS.items():
        if not build_html(name, source, 1, 9999, src_dir=DIAGRAMS):
            failures += 1
    for name in DIAGRAM_ARTIFACT_TARGETS:
        if not build_diagram_artifact(name):
            failures += 1
    for name in PPTX_TARGETS:
        if not build_slides(name):
            failures += 1
    return failures


def build_single(name: str) -> int:
    if name in HTML_TARGETS:
        spec = HTML_TARGETS[name]
        ok = build_html(name, spec.source, spec.min_pages, spec.max_pages)
        if ok:
            show_fonts(EXAMPLES / f"{name}.pdf")
        return 0 if ok else 1
    if name in DIAGRAM_TARGETS:
        source = DIAGRAM_TARGETS[name]
        ok = build_html(name, source, 1, 9999, src_dir=DIAGRAMS)
        return 0 if ok else 1
    if name in DIAGRAM_ARTIFACT_TARGETS:
        return 0 if build_diagram_artifact(name) else 1
    if name in PPTX_TARGETS:
        return 0 if build_slides(name) else 1
    known = list(HTML_TARGETS) + list(DIAGRAM_TARGETS) + list(DIAGRAM_ARTIFACT_TARGETS) + list(PPTX_TARGETS)
    print(f"ERROR: unknown target: {name}. Known: {', '.join(known)}")
    return 2


def show_fonts(pdf: Path) -> None:
    if not pdf.exists():
        return
    try:
        out = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True, check=False)
        if out.returncode == 0:
            print("--- pdffonts ---")
            print(out.stdout.rstrip())
    except FileNotFoundError:
        pass  # pdffonts not installed; silent


# ------------------------- doctor -------------------------

def _doctor_import(label: str, module: str, package: str | None = None) -> tuple[bool, str | None]:
    install_name = package or module
    try:
        with open(os.devnull, "w") as devnull:
            saved_stdout_fd = os.dup(1)
            saved_stderr_fd = os.dup(2)
            try:
                os.dup2(devnull.fileno(), 1)
                os.dup2(devnull.fileno(), 2)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    __import__(module)
            finally:
                os.dup2(saved_stdout_fd, 1)
                os.dup2(saved_stderr_fd, 2)
                os.close(saved_stdout_fd)
                os.close(saved_stderr_fd)
    except ImportError as exc:
        return False, f"ERROR: {label}: missing Python package ({exc}). Run: python3 -m pip install {install_name}"
    except OSError as exc:
        return False, f"ERROR: {label}: {exc}. {_dependency_fix_hint()}"
    return True, None


def _doctor_command(label: str, command: str, install_hint: str) -> tuple[bool, str | None]:
    if shutil.which(command):
        return True, None
    return False, f"ERROR: {label}: '{command}' not found. {install_hint}"


def run_doctor() -> int:
    checks: list[tuple[str, bool, str | None]] = []

    ok, msg = _doctor_import("WeasyPrint", "weasyprint")
    checks.append(("WeasyPrint", ok, msg))
    ok, msg = _doctor_import("pypdf", "pypdf")
    checks.append(("pypdf", ok, msg))
    ok, msg = _doctor_import("python-pptx", "pptx", "python-pptx")
    checks.append(("python-pptx", ok, msg))

    ok, msg = _doctor_command(
        "rsvg-convert",
        "rsvg-convert",
        "macOS: brew install librsvg; Debian/Ubuntu: sudo apt-get install -y librsvg2-bin",
    )
    checks.append(("rsvg-convert", ok, msg))
    ok, msg = _doctor_command(
        "pdffonts",
        "pdffonts",
        "macOS: brew install poppler; Debian/Ubuntu: sudo apt-get install -y poppler-utils",
    )
    checks.append(("pdffonts", ok, msg))

    required_fonts = [
        ROOT / "assets" / "fonts" / "LXGWWenKai-Regular.ttf",
        ROOT / "assets" / "fonts" / "LXGWWenKai-Medium.ttf",
    ]
    missing_fonts = [path.relative_to(ROOT) for path in required_fonts if not path.exists()]
    if missing_fonts:
        checks.append((
            "LXGW WenKai fonts",
            False,
            "ERROR: LXGW WenKai fonts: missing "
            + ", ".join(str(path) for path in missing_fonts)
            + ". Run the font recovery curl commands in SKILL.md before building Chinese PDFs.",
        ))
    else:
        checks.append(("LXGW WenKai fonts", True, None))

    failures = 0
    for label, ok, msg in checks:
        if ok:
            print(f"OK: {label}")
        else:
            failures += 1
            print(msg)

    return 0 if failures == 0 else 1


# ------------------------- sync -------------------------

ROOT_BLOCK = re.compile(r":root\s*\{([^}]*)\}", re.DOTALL)
CSS_VAR = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")
PY_RGB = re.compile(
    r"^([A-Z][A-Z_]+)\s*=\s*RGBColor\(\s*0x([0-9a-fA-F]{2})\s*,"
    r"\s*0x([0-9a-fA-F]{2})\s*,\s*0x([0-9a-fA-F]{2})\s*\)",
    re.MULTILINE,
)
# Python const name -> tokens.json key. Only constants that mirror a CSS token.
PY_TOKEN_MAP = {
    "PARCHMENT": "--parchment",
    "IVORY": "--ivory",
    "BRAND": "--brand",
    "NEAR_BLACK": "--near-black",
    "DARK_WARM": "--dark-warm",
    "CHARCOAL": "--charcoal",
    "OLIVE": "--olive",
    "STONE": "--stone",
}


def sync_check(verbose: bool = False) -> int:
    if not TOKENS_FILE.exists():
        print(f"ERROR: tokens.json not found at {TOKENS_FILE.relative_to(ROOT)}")
        return 1

    try:
        canonical: dict[str, str] = json.loads(TOKENS_FILE.read_text())
    except json.JSONDecodeError as exc:
        print(f"ERROR: tokens.json is malformed: {exc}")
        return 1

    targets: list[Path] = list(TEMPLATES.glob("*.html"))
    if DIAGRAMS.exists():
        targets.extend(DIAGRAMS.glob("*.html"))
    py_targets: list[Path] = list(TEMPLATES.glob("*.py"))

    drift: list[tuple[str, str, str, str]] = []  # (file, token, expected, actual)

    for path in sorted(targets):
        text = path.read_text(encoding="utf-8", errors="replace")
        block_match = ROOT_BLOCK.search(text)
        if not block_match:
            if verbose:
                print(f"  (skip {path.name}: no :root block)")
            continue
        root_block = block_match.group(1)
        found: dict[str, str] = {
            m.group(1): m.group(2).strip()
            for m in CSS_VAR.finditer(root_block)
        }
        rel = path.relative_to(ROOT)
        for token, expected in canonical.items():
            name = token.lstrip("-")
            actual = found.get(name)
            # Only flag if the template defines the token but with a wrong value.
            # Templates that don't use a token don't need to define it.
            if actual is not None and actual.lower() != expected.lower():
                drift.append((str(rel), token, expected, actual))

    for path in sorted(py_targets):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT)
        for m in PY_RGB.finditer(text):
            name = m.group(1)
            token = PY_TOKEN_MAP.get(name)
            if token is None:
                continue
            expected = canonical.get(token)
            if expected is None:
                continue
            actual = f"#{m.group(2)}{m.group(3)}{m.group(4)}"
            if actual.lower() != expected.lower():
                drift.append((str(rel), token, expected, actual))

    if not drift:
        scanned = len(targets) + len(py_targets)
        print(f"OK: tokens in sync across {scanned} template(s)")
        return 0

    print(f"\n[token-drift] {len(drift)}")
    for file, token, expected, actual in drift:
        print(f"  {file}: {token} expected {expected}, got {actual}")

    return 1


# ------------------------- verify -------------------------

PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")

# Primary fonts expected in embedded PDF font names
CN_PRIMARY_FONTS = {"LXGWWenKai"}
EN_PRIMARY_FONTS = {"Charter"}


def _font_name_contains(font_name: str, expected: set[str]) -> bool:
    """Match embedded PDF font names after subsetting and separator changes."""
    subsetless = font_name.split("+", 1)[-1]
    normalized = re.sub(r"[^a-z0-9]+", "", subsetless.lower())
    return any(
        re.sub(r"[^a-z0-9]+", "", item.lower()) in normalized
        for item in expected
    )


def _pdf_font_names(pdf_path: Path) -> set[str]:
    def _resolve_pdf_obj(obj):
        if obj is None:
            return None
        try:
            return obj.get_object() if hasattr(obj, "get_object") else obj
        except Exception:
            return obj

    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        fonts: set[str] = set()
        for page in reader.pages:
            resources = _resolve_pdf_obj(page.get("/Resources"))
            if resources is None or not hasattr(resources, "get"):
                continue
            font_dict = _resolve_pdf_obj(resources.get("/Font"))
            if font_dict is None or not hasattr(font_dict, "values"):
                continue
            for obj in font_dict.values():
                resolved = _resolve_pdf_obj(obj)
                if resolved is None or not hasattr(resolved, "get"):
                    continue
                base = resolved.get("/BaseFont")
                if base:
                    fonts.add(str(base).lstrip("/"))
        return fonts
    except Exception as exc:
        print(f"  WARN: could not read font names from PDF: {exc}")
        return set()


def _check_font_sources(html_path: Path) -> list[str]:
    """Return list of local @font-face src files that are missing on disk."""
    text = html_path.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    for block in re.findall(r"@font-face\s*\{[^}]*\}", text, flags=re.IGNORECASE | re.DOTALL):
        for url in re.findall(r"""url\(["']?([^"')]+)["']?\)""", block):
            if url.startswith(("http://", "https://", "data:")):
                continue
            resolved = (html_path.parent / url).resolve()
            if not resolved.exists():
                missing.append(url)
    return missing


def verify_target(name: str, source: str, min_pages: int, max_pages: int, src_dir: Path) -> list[str]:
    issues: list[str] = []
    src = src_dir / source
    if not src.exists():
        issues.append(f"source not found: {src}")
        return issues

    HTML, PdfReader, dep_error = _load_pdf_build_deps()
    if dep_error:
        issues.append(dep_error)
        return issues

    EXAMPLES.mkdir(parents=True, exist_ok=True)
    out = EXAMPLES / f"{name}.pdf"

    # Warn about missing local font files before rendering
    missing_fonts = _check_font_sources(src)
    for mf in missing_fonts:
        print(f"  [FONT MISS] {name}: {mf} not found — render will fall back to Source Han Serif SC → Noto Serif CJK SC → Songti SC → Georgia")

    try:
        HTML(str(src), base_url=str(src.parent)).write_pdf(str(out))
    except Exception as exc:
        issues.append(f"render failed: {exc}")
        return issues

    # Set PDF metadata (only replaces placeholders, preserves filled values)
    author = infer_author()
    set_pdf_metadata(out, author=author)

    # page count check
    n = len(PdfReader(str(out)).pages)
    issue = page_count_issue(name, n, min_pages, max_pages)
    if issue:
        issues.append(issue)

    # font check
    embedded = _pdf_font_names(out)
    fallback_present = any(
        _font_name_contains(font, {"Georgia", "Palatino", "LXGWWenKai", "LXGW WenKai", "SourceHan", "Noto", "Charter", "Songti"})
        for font in embedded
    )

    # Diagram templates are language-neutral and often rely on fallback stacks,
    # so only enforce that at least one recognizable serif/sans fallback exists.
    is_diagram = src_dir == DIAGRAMS
    if is_diagram:
        if not fallback_present:
            issues.append(f"no recognizable font embedded in {out.name}")
        return issues

    is_en = name.endswith("-en")
    expected = EN_PRIMARY_FONTS if is_en else CN_PRIMARY_FONTS
    if not any(_font_name_contains(font_name, expected) for font_name in embedded):
        primary = next(iter(expected))
        if not fallback_present:
            issues.append(f"no recognizable font embedded in {out.name}")
        else:
            issues.append(f"primary font ({primary}) not embedded; using fallback")

    return issues


def _pptx_slide_count(pptx_path: Path) -> int:
    from xml.etree import ElementTree
    from zipfile import ZipFile

    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    with ZipFile(pptx_path) as archive:
        root = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
    slide_list = root.find("p:sldIdLst", ns)
    return 0 if slide_list is None else len(list(slide_list))


def verify_slides_target(name: str) -> list[str]:
    spec = PPTX_TARGETS.get(name)
    if spec is None:
        return ["slides target not found"]
    if not build_slides(name):
        return ["slides build failed"]
    out = EXAMPLES / f"{name}.pptx"
    if not out.exists():
        return ["slides output not found"]
    count = _pptx_slide_count(out)
    issue = page_count_issue(name, count, spec.min_pages, spec.max_pages)
    return [issue] if issue else []


def verify_all(target: str | None = None) -> int:
    targets_to_run: dict[str, tuple[str, str, int, int, Path] | None] = {}
    if target:
        if target in HTML_TARGETS:
            spec = HTML_TARGETS[target]
            targets_to_run[target] = ("html", spec.source, spec.min_pages, spec.max_pages, TEMPLATES)
        elif target in DIAGRAM_TARGETS:
            targets_to_run[target] = ("diagram", DIAGRAM_TARGETS[target], 1, 9999, DIAGRAMS)
        elif target in DIAGRAM_ARTIFACT_TARGETS:
            targets_to_run[target] = ("artifact", "", 1, 1, ROOT)
        elif target in PPTX_TARGETS:
            targets_to_run[target] = None
        else:
            print(f"ERROR: unknown target: {target}")
            return 2
    else:
        for name, spec in HTML_TARGETS.items():
            targets_to_run[name] = ("html", spec.source, spec.min_pages, spec.max_pages, TEMPLATES)
        for name, src in DIAGRAM_TARGETS.items():
            targets_to_run[name] = ("diagram", src, 1, 9999, DIAGRAMS)
        for name in DIAGRAM_ARTIFACT_TARGETS:
            targets_to_run[name] = ("artifact", "", 1, 1, ROOT)
        for name in PPTX_TARGETS:
            targets_to_run[name] = None

    failures = 0
    rows: list[tuple[str, str]] = []
    for name, config in targets_to_run.items():
        if config is None:
            issues = verify_slides_target(name)
        else:
            target_kind, source, min_pages, max_pages, src_dir = config
            if target_kind == "artifact":
                issues = [] if build_diagram_artifact(name) else ["artifact build failed"]
            else:
                issues = verify_target(name, source, min_pages, max_pages, src_dir)
        if issues:
            rows.append((f"ERROR: {name}", "; ".join(issues)))
            failures += 1
        else:
            rows.append((f"OK: {name}", "ok"))

    for status, detail in rows:
        print(f"{status}: {detail}")

    return 0 if failures == 0 else 1


def check_placeholders(paths: list[str]) -> int:
    if not paths:
        print("ERROR: provide at least one HTML file to scan")
        return 2

    failures = 0
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            print(f"ERROR: {raw}: file not found")
            failures += 1
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = list(dict.fromkeys(PLACEHOLDER.findall(text)))
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        if hits:
            print(f"ERROR: {rel}: unfilled placeholder(s): {', '.join(hits)}")
            failures += 1
        else:
            print(f"OK: {rel}: no placeholders")

    return 0 if failures == 0 else 1


# ------------------------- orphan check -------------------------

def check_orphans(paths: list[str]) -> int:
    """Scan PDF for text blocks whose last line has <= 2 words and < 15 chars."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF required: pip install pymupdf --break-system-packages")
        return 2

    if not paths:
        # Default: scan all example PDFs
        if EXAMPLES.exists():
            paths = [str(p) for p in sorted(EXAMPLES.glob("*.pdf"))]
        if not paths:
            print("ERROR: no PDF files to scan")
            return 2

    total = 0
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            print(f"ERROR: {raw}: not found")
            continue
        doc = fitz.open(str(path))
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        for page_num in range(len(doc)):
            page = doc[page_num]
            blocks = page.get_text("blocks")
            for bx0, by0, bx1, by1, text, block_no, block_type in blocks:
                if block_type != 0:  # text blocks only
                    continue
                lines = text.strip().splitlines()
                if len(lines) < 2:
                    continue
                last = lines[-1].strip()
                words = last.split()
                if len(words) <= 2 and len(last) < 15:
                    total += 1
                    print(f"  {rel} p{page_num + 1}: orphan: \"{last}\" ({len(words)} word(s), {len(last)} chars)")
        doc.close()

    if total == 0:
        print(f"OK: no orphans found across {len(paths)} PDF(s)")
        return 0

    print(f"\n{total} orphan(s) found across {len(paths)} PDF(s)")
    return 1


# ------------------------- check -------------------------

RGBA_BG_DIRECT = re.compile(r"background(?:-color)?\s*:\s*[^;]*rgba\s*\(", re.IGNORECASE)
RGBA_VAR_DEF = re.compile(r"--([\w-]+)\s*:\s*[^;]*rgba\s*\(", re.IGNORECASE)
BG_VAR_USE = re.compile(r"background(?:-color)?\s*:\s*[^;]*var\s*\(\s*--([\w-]+)", re.IGNORECASE)
RGBA_BORDER_DIRECT = re.compile(r"border(?:-\w+)?\s*:\s*[^;]*rgba\s*\(", re.IGNORECASE)
BORDER_VAR_USE = re.compile(r"border(?:-\w+)?\s*:\s*[^;]*var\s*\(\s*--([\w-]+)", re.IGNORECASE)
LINE_HEIGHT_LOOSE = re.compile(r"line-height\s*:\s*1\.[6-9]\d*", re.IGNORECASE)
UNICODE_ARROW = re.compile(r"→")  # U+2192; should not appear in EN template body
HEX_ANY = re.compile(r"#[0-9a-fA-F]{3,6}\b")
SVG_MARKER = re.compile(r"<marker\b|marker-(?:start|mid|end)\s*=", re.IGNORECASE)
SVG_MARKER_ORIENT = re.compile(r"orient\s*=\s*['\"]auto", re.IGNORECASE)
ITALIC_STYLE = re.compile(r"font-style\s*[:=]\s*['\"]?italic", re.IGNORECASE)
# Thin closed border: border shorthand (not single-side) with sub-1pt width — pitfall #2
THIN_CLOSED_BORDER = re.compile(
    r"border(?!-(?:left|right|top|bottom))\s*:\s*[^;]*0\.\d+pt",
    re.IGNORECASE,
)
BORDER_RADIUS_PROP = re.compile(r"border-radius\s*:", re.IGNORECASE)


@dataclass
class Finding:
    file: Path
    line: int
    rule: str
    excerpt: str


def scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # Pass 1: collect variable names that hold rgba(...) so the tag-background
    # bug can be detected through one level of indirection.
    rgba_vars: set[str] = set()
    for raw in lines:
        m = RGBA_VAR_DEF.search(raw)
        if m:
            rgba_vars.add(m.group(1))

    is_en = path.name.endswith("-en.html")

    # Pass 2: per-line rule checks
    for i, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        if RGBA_BG_DIRECT.search(raw):
            findings.append(Finding(path, i, "rgba-background",
                                    "rgba() used directly on background (tag double-rectangle bug)"))

        bg_var = BG_VAR_USE.search(raw)
        if bg_var and bg_var.group(1) in rgba_vars:
            findings.append(Finding(path, i, "rgba-background",
                                    f"background: var(--{bg_var.group(1)}) resolves to rgba() (tag double-rectangle bug)"))

        if RGBA_BORDER_DIRECT.search(raw):
            findings.append(Finding(path, i, "rgba-border",
                                    "rgba() used on border (violates solid-color invariant)"))

        border_var = BORDER_VAR_USE.search(raw)
        if border_var and border_var.group(1) in rgba_vars:
            findings.append(Finding(path, i, "rgba-border",
                                    f"border: var(--{border_var.group(1)}) resolves to rgba() (solid-color invariant)"))

        if is_en and UNICODE_ARROW.search(raw):
            # skip CSS comment lines (/* ... */) and the arrow-in-CSS-content patterns
            stripped = raw.lstrip()
            if not stripped.startswith("/*") and not stripped.startswith("*") and "content:" not in raw:
                findings.append(Finding(path, i, "arrow-unicode-in-en",
                                        "→ (U+2192) in English template; use 'to' or '->' per patterns §2"))

        m = LINE_HEIGHT_LOOSE.search(raw)
        if m:
            findings.append(Finding(path, i, "line-height-too-loose",
                                    f"{m.group(0)} exceeds 1.55 ceiling"))

        for hex_match in HEX_ANY.finditer(raw):
            h = hex_match.group(0).lower()
            if h in COOL_GRAY_BLOCKLIST:
                findings.append(Finding(path, i, "cool-gray",
                                        f"{h} is a cool / neutral gray, use warm undertone"))

        if path.parent == DIAGRAMS and SVG_MARKER.search(raw):
            findings.append(Finding(path, i, "svg-marker-arrow",
                                    "SVG marker arrows are not reliable in WeasyPrint; draw manual chevrons"))

        if path.parent == DIAGRAMS and SVG_MARKER_ORIENT.search(raw):
            findings.append(Finding(path, i, "svg-marker-orient-auto",
                                    "orient=\"auto\" is ignored by WeasyPrint; draw manual chevrons"))

        if ITALIC_STYLE.search(raw):
            findings.append(Finding(path, i, "font-style-italic",
                                    "italic is forbidden in Folio templates and demos"))

    # Pass 3: thin-border-radius block scan (pitfall #2 double-ring).
    # For each thin closed border line, scan backward to the block open and
    # forward to the block close, checking for border-radius in the same block.
    for i, raw in enumerate(lines):
        if not THIN_CLOSED_BORDER.search(raw):
            continue
        if "skip-thin-border-radius" in raw:
            continue
        found = False
        # Scan backward; stop at { or } (entering/leaving a block).
        for j in range(i - 1, max(0, i - 6) - 1, -1):
            if "{" in lines[j] or "}" in lines[j]:
                break
            if BORDER_RADIUS_PROP.search(lines[j]):
                found = True
                break
        # Scan forward; stop at } (leaving the block).
        if not found:
            for j in range(i + 1, min(len(lines), i + 6)):
                if "}" in lines[j]:
                    break
                if BORDER_RADIUS_PROP.search(lines[j]):
                    found = True
                    break
        if found:
            findings.append(Finding(path, i + 1, "thin-border-radius",
                "thin border (<1pt) with border-radius -- pitfall #2 double-ring risk"))
    return findings


def check_all(verbose: bool) -> int:
    targets: list[Path] = []
    for p in TEMPLATES.glob("*.html"):
        targets.append(p)
    for p in TEMPLATES.glob("*.py"):
        targets.append(p)
    if DIAGRAMS.exists():
        for p in DIAGRAMS.glob("*.html"):
            targets.append(p)

    findings: list[Finding] = []
    for p in sorted(targets):
        file_findings = scan_file(p)
        findings.extend(file_findings)
        if verbose:
            print(f"scanned {p.relative_to(ROOT)}: {len(file_findings)} finding(s)")

    if not findings:
        print(f"OK: no violations across {len(targets)} templates")
        return 0

    by_rule: dict[str, list[Finding]] = {}
    for f in findings:
        by_rule.setdefault(f.rule, []).append(f)

    print(f"ERROR: {len(findings)} violation(s) across {len({f.file for f in findings})} file(s)")
    for rule, items in by_rule.items():
        print(f"\n[{rule}] {len(items)}")
        for f in items:
            rel = f.file.relative_to(ROOT)
            print(f"  {rel}:{f.line}  {f.excerpt}")
    return 1


# ------------------------- rhythm check -------------------------

# Layout functions that count as "divider" slides (break monotony).
_DIVIDER_FUNCS = {"chapter_slide"}
# Layout functions that count as "density variation" slides.
_DENSITY_VARIATION_FUNCS = {"quote_slide", "metrics_slide"}
# Layout function call pattern in slides.py source.
_SLIDE_CALL = re.compile(r"^\s*(\w+_slide)\s*\(")


def _parse_slide_sequence(src: Path) -> list[str]:
    """Return the ordered list of slide-function names called in main()."""
    text = src.read_text(encoding="utf-8", errors="replace")
    in_main = False
    sequence: list[str] = []
    for line in text.splitlines():
        if re.match(r"^def main\s*\(", line):
            in_main = True
            continue
        if in_main and re.match(r"^def \w", line):
            break
        if in_main:
            m = _SLIDE_CALL.match(line)
            if m:
                sequence.append(m.group(1))
    return sequence


def check_rhythm(targets: list[str]) -> int:
    """Scan slide templates for monotony: too many consecutive content_slides,
    missing dividers, and missing density variation.

    Usage: python3 scripts/build.py --check-rhythm [slides] [slides-en]
    When no targets are given, checks all PPTX_TARGETS.
    """
    names = targets if targets else list(PPTX_TARGETS.keys())
    failures = 0

    for name in names:
        spec = PPTX_TARGETS.get(name)
        if spec is None:
            print(f"ERROR: {name}: not a known slides target")
            failures += 1
            continue
        src = TEMPLATES / spec.source
        if not src.exists():
            print(f"ERROR: {name}: source not found ({src})")
            failures += 1
            continue

        seq = _parse_slide_sequence(src)
        if not seq:
            print(f"WARN: {name}: no slide calls found in main()")
            continue

        issues: list[str] = []

        # Rule 1: no run of more than 5 consecutive content_slides.
        run = 0
        max_run = 0
        for fn in seq:
            if fn == "content_slide":
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        if max_run > 5:
            issues.append(f"longest content_slide run is {max_run} (limit 5)")

        # Rule 2: decks >= 12 slides need at least one chapter_slide divider.
        if len(seq) >= 12 and not any(fn in _DIVIDER_FUNCS for fn in seq):
            issues.append(f"{len(seq)} slides with no chapter_slide divider")

        # Rule 3: deck must contain at least one density-variation slide.
        if not any(fn in _DENSITY_VARIATION_FUNCS for fn in seq):
            issues.append("no quote_slide or metrics_slide for density variation")

        if issues:
            for issue in issues:
                print(f"WARN: {name}: {issue}")
            failures += 1
        else:
            print(f"OK: {name}: rhythm ok ({len(seq)} slides, max run {max_run})")

    return 0 if failures == 0 else 1


# ------------------------- entry -------------------------

def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args:
        return build_all()
    if args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if args[0] == "--check":
        verbose = "-v" in args[1:] or "--verbose" in args[1:]
        css_result = check_all(verbose)
        sync_result = sync_check(verbose)
        return max(css_result, sync_result)
    if args[0] == "--sync":
        verbose = "-v" in args[1:] or "--verbose" in args[1:]
        return sync_check(verbose)
    if args[0] == "--doctor":
        return run_doctor()
    if args[0] == "--verify":
        target = args[1] if len(args) > 1 and not args[1].startswith("-") else None
        return verify_all(target)
    if args[0] == "--check-orphans":
        return check_orphans(args[1:])
    if args[0] in ("--check-placeholders", "--verify-filled"):
        return check_placeholders(args[1:])
    if args[0] == "--check-rhythm":
        slide_targets = [a for a in args[1:] if not a.startswith("-")]
        return check_rhythm(slide_targets)
    return build_single(args[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
