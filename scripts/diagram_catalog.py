#!/usr/bin/env python3
"""Render the registered Folio Drawing DSL catalog into review artifacts."""
from __future__ import annotations

import argparse
import hashlib
from html import escape as html_escape
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "references" / "fixtures" / "diagram-catalog.json"
DEFAULT_OUTPUT = ROOT / "assets" / "diagrams" / "generated" / "catalog"
DEFAULT_CONTACT_SHEET = ROOT / "assets" / "demos" / "drawing-dsl-v5-all-types.png"
DEFAULT_SUPPORTED_SHEET = ROOT / "assets" / "demos" / "drawing-dsl-v5-supported-types.png"
PLACEHOLDER_RE = re.compile(r"\{\{([^{}]+)\}\}")
VISUAL_BASELINE_SCHEMA_VERSION = "1.0"


def load_catalog(path: Path = FIXTURE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_catalog(payload)
    return payload


def validate_catalog(payload: dict[str, Any]) -> None:
    diagrams = payload.get("diagrams")
    if payload.get("schema_version") not in {"1.0", "3.0"} or not isinstance(diagrams, list):
        raise ValueError("diagram catalog must use schema_version 1.0 or 3.0 and contain a diagrams list")
    kinds = [str(item.get("kind", "")) for item in diagrams]
    if not kinds or len(set(kinds)) != len(kinds):
        raise ValueError("diagram catalog must contain unique diagram kinds")
    for item in diagrams:
        if item.get("mode") not in {"drawing-dsl", "drawing-dsl-v2", "drawing-dsl-v3", "html-template"}:
            raise ValueError(f"unknown catalog mode for {item.get('kind')}")
        if not item.get("source") or not item.get("label"):
            raise ValueError(f"catalog entry is missing source or label: {item.get('kind')}")
    if payload.get("schema_version") == "3.0":
        sys.path.insert(0, str(SCRIPTS))
        from drawing.compiler import DEFAULT_COMPILER_REGISTRY

        registered = set(DEFAULT_COMPILER_REGISTRY.kinds)
        catalog = set(kinds)
        if catalog != registered:
            missing = ", ".join(sorted(registered - catalog)) or "none"
            extra = ", ".join(sorted(catalog - registered)) or "none"
            raise ValueError(
                f"catalog must match compiler registry (missing: {missing}; extra: {extra})"
            )


def fill_template(source: str, replacements: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in replacements:
            return match.group(0)
        return html_escape(str(replacements[key]), quote=True)

    return PLACEHOLDER_RE.sub(replace, source)


def render_catalog(
    payload: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    build_dsl: bool = True,
    contact_sheet: Path = DEFAULT_CONTACT_SHEET,
    supported_sheet: Path = DEFAULT_SUPPORTED_SHEET,
    catalog_fixture: Path = FIXTURE,
) -> dict[str, Any]:
    from PIL import Image

    png_dir = output_dir / "png"
    svg_dir = output_dir / "svg"
    pdf_dir = output_dir / "pdf"
    for artifact_dir in (png_dir, svg_dir, pdf_dir):
        artifact_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for item in payload["diagrams"]:
        kind = item["kind"]
        output_png = png_dir / f"{kind}.png"
        compilation: dict[str, Any] | None = None
        if item["mode"] in {"drawing-dsl", "drawing-dsl-v3"}:
            source_size, compilation = _render_dsl_fixture(
                item, output_png, svg_dir / f"{kind}.svg", pdf_dir / f"{kind}.pdf"
            )
            unresolved = []
        elif item["mode"] == "drawing-dsl-v2":
            if build_dsl:
                _run([sys.executable, str(SCRIPTS / "build.py"), item["build_target"]])
            source_png = ROOT / item["preview"]
            if not source_png.exists():
                raise FileNotFoundError(f"DSL preview was not generated: {source_png}")
            with Image.open(source_png) as image:
                source_size = [image.width, image.height]
                _save_standard_preview(image, output_png)
            unresolved: list[str] = []
        else:
            unresolved = _render_html_template(item, output_png)
            with Image.open(output_png) as image:
                source_size = [image.width, image.height]

        evidence = _image_evidence(output_png)
        errors = [item for item in evidence["diagnostics"] if item["level"] == "ERROR"]
        if errors:
            raise ValueError(f"{kind} page-preview failed bounds validation: {errors[0]['message']}")
        records.append({
            "kind": kind,
            "label": item["label"],
            "mode": item["mode"],
            "source": item["source"],
            "png": _portable_path(output_png),
            "svg": _portable_path(svg_dir / f"{kind}.svg") if compilation else None,
            "pdf": _portable_path(pdf_dir / f"{kind}.pdf") if compilation else None,
            "profile": "page-preview",
            "compiler_contract": "3.0" if item["mode"].startswith("drawing-dsl") else "static-parity",
            "registry_key": compilation["registry_key"] if compilation else None,
            "semantic_ids": compilation["semantic_ids"] if compilation else [],
            "baseline_category": "generator-parity" if item["mode"] in {"drawing-dsl", "drawing-dsl-v3"} else "legacy-parity",
            "approval_state": "approved" if item["mode"] in {"drawing-dsl", "drawing-dsl-v3"} else "reference-only",
            "dimensions": {"source": source_size, "output": evidence["size"]},
            "content_bounds": evidence["content_bounds"],
            "diagnostics": evidence["diagnostics"],
            "metrics": {**evidence["metrics"], **(compilation["metrics"] if compilation else {})},
            "digests": {"png": _sha256(output_png), **(compilation["digests"] if compilation else {})},
            "unresolved_placeholders": unresolved,
        })

    _write_contact_sheet(payload["title"], records, contact_sheet)
    _write_supported_sheet(
        "Drawing DSL V5 · Generator-backed Types",
        [item for item in records if item["mode"] in {"drawing-dsl", "drawing-dsl-v3"}],
        supported_sheet,
    )
    manifest = {
        "schema_version": "3.0",
        "versions": {"catalog_fixture": payload["schema_version"], "drawing_core": "3.0"},
        "catalog_fixture": _portable_path(catalog_fixture),
        "coverage": {
            "catalog_types": len(records),
            "drawing_dsl": sum(item["mode"] in {"drawing-dsl", "drawing-dsl-v3"} for item in records),
            "drawing_dsl_v2": sum(item["mode"] == "drawing-dsl-v2" for item in records),
            "drawing_dsl_v3": sum(item["mode"] == "drawing-dsl-v3" for item in records),
            "html_template_baseline": sum(item["mode"] == "html-template" for item in records),
        },
        "contact_sheets": [
            {"path": _portable_path(contact_sheet), "sha256": _sha256(contact_sheet)},
            {"path": _portable_path(supported_sheet), "sha256": _sha256(supported_sheet)},
        ],
        "diagrams": records,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def create_visual_baseline(
    manifest: dict[str, Any],
    approval_reason: str,
    *,
    max_changed_channel_ratio: float = 0.01,
    bounds_tolerance_px: int = 2,
) -> dict[str, Any]:
    reason = approval_reason.strip()
    if not reason:
        raise ValueError("visual baseline approval requires a non-empty reason")
    if not 0 <= max_changed_channel_ratio <= 1:
        raise ValueError("max_changed_channel_ratio must be between 0 and 1")
    if bounds_tolerance_px < 0:
        raise ValueError("bounds_tolerance_px must be non-negative")
    return {
        "schema_version": VISUAL_BASELINE_SCHEMA_VERSION,
        "catalog_schema_version": manifest.get("schema_version"),
        "approval_state": "approved",
        "approval_reason": reason,
        "visual_policy": {
            "method": "exact-rgba-no-resize",
            "max_changed_channel_ratio": max_changed_channel_ratio,
            "bounds_tolerance_px": bounds_tolerance_px,
        },
        "coverage": dict(manifest.get("coverage", {})),
        "contact_sheets": list(manifest.get("contact_sheets", [])),
        "diagrams": [
            {
                "kind": record["kind"],
                "profile": record["profile"],
                "registry_key": record["registry_key"],
                "png": record["png"],
                "semantic_ids": list(record.get("semantic_ids", [])),
                "dimensions": record["dimensions"],
                "content_bounds": record["content_bounds"],
                "digests": record["digests"],
                "approval_state": "approved",
                "approval_reason": reason,
            }
            for record in manifest.get("diagrams", [])
        ],
    }


def compare_visual_baseline(
    manifest: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    comparisons: list[dict[str, Any]] = []
    if baseline.get("schema_version") != VISUAL_BASELINE_SCHEMA_VERSION:
        issues.append("baseline schema_version must be 1.0")
    if baseline.get("approval_state") != "approved" or not str(baseline.get("approval_reason", "")).strip():
        issues.append("baseline must have an approval state and non-empty approval reason")

    policy = baseline.get("visual_policy", {})
    max_ratio = float(policy.get("max_changed_channel_ratio", 0))
    bounds_tolerance = int(policy.get("bounds_tolerance_px", 0))
    for key in ("catalog_types", "drawing_dsl", "drawing_dsl_v3", "drawing_dsl_v2", "html_template_baseline"):
        if key not in manifest.get("coverage", {}) and key not in baseline.get("coverage", {}):
            continue
        if manifest.get("coverage", {}).get(key) != baseline.get("coverage", {}).get(key):
            issues.append(f"coverage mismatch for {key}")

    current_records = {record["kind"]: record for record in manifest.get("diagrams", [])}
    baseline_records = {record["kind"]: record for record in baseline.get("diagrams", [])}
    if set(current_records) != set(baseline_records):
        missing = sorted(set(baseline_records) - set(current_records))
        added = sorted(set(current_records) - set(baseline_records))
        if missing:
            issues.append(f"baseline diagram(s) missing from current catalog: {', '.join(missing)}")
        if added:
            issues.append(f"current catalog has unapproved diagram(s): {', '.join(added)}")

    for kind in sorted(set(current_records) & set(baseline_records)):
        current = current_records[kind]
        expected = baseline_records[kind]
        prefix = f"{kind}:"
        if expected.get("approval_state") != "approved" or not str(expected.get("approval_reason", "")).strip():
            issues.append(f"{prefix} baseline entry is not approved with a reason")
        for key in ("profile", "registry_key", "dimensions", "semantic_ids"):
            if current.get(key) != expected.get(key):
                issues.append(f"{prefix} {key} changed")
        current_bounds = current.get("content_bounds", [])
        expected_bounds = expected.get("content_bounds", [])
        if (
            len(current_bounds) != 4
            or len(expected_bounds) != 4
            or any(abs(int(a) - int(b)) > bounds_tolerance for a, b in zip(current_bounds, expected_bounds))
        ):
            issues.append(f"{prefix} content bounds changed beyond {bounds_tolerance}px")
        for digest_name in ("input", "svg"):
            if current.get("digests", {}).get(digest_name) != expected.get("digests", {}).get(digest_name):
                issues.append(f"{prefix} {digest_name} digest changed")

        current_png = _record_path(str(current.get("png", "")))
        baseline_png = _record_path(str(expected.get("png", "")))
        comparison = {
            "kind": kind,
            "png_digest_match": current.get("digests", {}).get("png") == expected.get("digests", {}).get("png"),
            "changed_channel_ratio": None,
        }
        if not current_png.is_file() or not baseline_png.is_file():
            missing_paths = [str(path) for path in (current_png, baseline_png) if not path.is_file()]
            issues.append(f"{prefix} visual artifact missing: {', '.join(missing_paths)}")
        else:
            dimensions_match, changed_ratio = _image_diff_ratio(baseline_png, current_png)
            comparison["changed_channel_ratio"] = changed_ratio
            if not dimensions_match:
                issues.append(f"{prefix} PNG dimensions changed")
            elif changed_ratio > max_ratio:
                issues.append(
                    f"{prefix} unapproved visual difference {changed_ratio:.6f} exceeds {max_ratio:.6f}"
                )
        comparisons.append(comparison)

    return {
        "schema_version": VISUAL_BASELINE_SCHEMA_VERSION,
        "method": policy.get("method", "exact-rgba-no-resize"),
        "passed": not issues,
        "issues": issues,
        "diagrams": comparisons,
    }


def _image_diff_ratio(baseline_path: Path, current_path: Path) -> tuple[bool, float]:
    from PIL import Image, ImageChops

    with Image.open(baseline_path) as baseline_image, Image.open(current_path) as current_image:
        baseline = baseline_image.convert("RGBA")
        current = current_image.convert("RGBA")
    if baseline.size != current.size:
        return False, 1.0
    diff = ImageChops.difference(baseline, current)
    histogram = diff.histogram()
    changed = sum(value for index, value in enumerate(histogram) if index % 256 != 0)
    channels = max(1, current.width * current.height * 4)
    return True, round(changed / channels, 6)


def _render_dsl_fixture(
    item: dict[str, Any], output_png: Path, output_svg: Path, output_pdf: Path
) -> tuple[list[int], dict[str, Any]]:
    sys.path.insert(0, str(SCRIPTS))
    from diagram_export import export_pdf
    from drawing.compiler import DEFAULT_COMPILER_REGISTRY
    from renderers.svg import render_svg

    source_path = ROOT / item["source"]
    source = json.loads(source_path.read_text(encoding="utf-8"))
    result = DEFAULT_COMPILER_REGISTRY.compile_payload(source, "page-preview")
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_svg.write_text(render_svg(result.scene, "page-preview"), encoding="utf-8")
    export_pdf(output_svg, output_pdf, result.scene.title.text, result.scene.language, "page-preview")
    _pdf_to_png(output_pdf, output_png)
    digests = {"input": _sha256(source_path), "svg": _sha256(output_svg), "pdf": _sha256(output_pdf)}
    metadata = result.metadata
    return [result.scene.width, result.scene.height], {
        "registry_key": metadata.registry_key if metadata else None,
        "metrics": result.metrics.to_dict(),
        "semantic_ids": list(result.scene.reading_order),
        "digests": digests,
    }


def _render_html_template(item: dict[str, Any], output_png: Path) -> list[str]:
    sys.path.insert(0, str(SCRIPTS))
    import build
    from drawing.output import apply_html_output_profile

    source_path = ROOT / item["source"]
    filled = fill_template(source_path.read_text(encoding="utf-8"), item.get("replacements", {}))
    filled = apply_html_output_profile(filled, "page-preview")
    unresolved = sorted(set(PLACEHOLDER_RE.findall(filled)))
    if unresolved:
        raise ValueError(f"{item['kind']} still has unresolved placeholders: {', '.join(unresolved)}")

    HTML, _PdfReader, dep_error = build._load_pdf_build_deps()
    if dep_error or HTML is None:
        raise RuntimeError(dep_error or "WeasyPrint is unavailable")
    with tempfile.TemporaryDirectory(prefix="folio-diagram-catalog-") as temp_dir:
        temp = Path(temp_dir)
        pdf_path = temp / f"{item['kind']}.pdf"
        HTML(string=filled, base_url=str(source_path.parent)).write_pdf(str(pdf_path))
        _pdf_to_png(pdf_path, output_png)
    return unresolved


def _pdf_to_png(pdf_path: Path, output_png: Path) -> None:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm is required to render catalog previews")
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_prefix = output_png.with_suffix("")
    _run([
        pdftoppm,
        "-f", "1",
        "-l", "1",
        "-singlefile",
        "-r", "150",
        "-png",
        str(pdf_path),
        str(output_prefix),
    ])


def _save_standard_preview(image: Any, output_png: Path) -> None:
    from PIL import Image, ImageOps

    canvas_size = (1241, 1754)
    canvas = Image.new("RGB", canvas_size, "#F6F0EA")
    contained = ImageOps.contain(image.convert("RGB"), canvas_size)
    offset = ((canvas.width - contained.width) // 2, (canvas.height - contained.height) // 2)
    canvas.paste(contained, offset)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_png, optimize=True)


def _image_evidence(path: Path) -> dict[str, Any]:
    from PIL import Image, ImageChops

    with Image.open(path) as image:
        rgb = image.convert("RGB")
    parchment = Image.new("RGB", rgb.size, "#F6F0EA")
    paper = Image.new("RGB", rgb.size, "#FFFFFF")
    parchment_difference = ImageChops.difference(rgb, parchment).convert("L")
    paper_difference = ImageChops.difference(rgb, paper).convert("L")
    foreground = ImageChops.darker(parchment_difference, paper_difference).point(
        lambda value: 255 if value > 8 else 0
    )
    bounds = foreground.getbbox()
    diagnostics: list[dict[str, str]] = []
    if bounds is None:
        diagnostics.append({"level": "ERROR", "code": "CAT001", "message": "preview contains no visible content"})
        content_bounds = [0, 0, 0, 0]
    else:
        content_bounds = list(bounds)
        if bounds[0] <= 0 or bounds[1] <= 0 or bounds[2] >= rgb.width or bounds[3] >= rgb.height:
            diagnostics.append({"level": "ERROR", "code": "CAT002", "message": "preview content touches a page boundary"})
    bbox_area = max(0, content_bounds[2] - content_bounds[0]) * max(0, content_bounds[3] - content_bounds[1])
    return {
        "size": [rgb.width, rgb.height],
        "content_bounds": content_bounds,
        "diagnostics": diagnostics,
        "metrics": {
            "content_width": max(0, content_bounds[2] - content_bounds[0]),
            "content_height": max(0, content_bounds[3] - content_bounds[1]),
            "bounding_box_ratio": round(bbox_area / max(1, rgb.width * rgb.height), 6),
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_contact_sheet(
    title: str,
    records: list[dict[str, Any]],
    output_path: Path,
    *,
    columns: int = 3,
) -> None:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    card_width = 540
    thumb_width = 500
    thumb_height = 708
    gap = 24
    margin = 36
    title_height = 106
    label_height = 52
    card_height = label_height + thumb_height + 20
    rows = math.ceil(len(records) / columns)
    width = margin * 2 + columns * card_width + (columns - 1) * gap
    height = title_height + margin + rows * card_height + max(0, rows - 1) * gap + margin
    canvas = Image.new("RGB", (width, height), "#F6F0EA")
    draw = ImageDraw.Draw(canvas)
    regular_path = ROOT / "assets" / "fonts" / "LXGWWenKai-Regular.ttf"
    medium_path = ROOT / "assets" / "fonts" / "LXGWWenKai-Medium.ttf"
    title_font = ImageFont.truetype(str(medium_path), 34) if medium_path.exists() else ImageFont.load_default()
    label_font = ImageFont.truetype(str(medium_path), 18) if medium_path.exists() else ImageFont.load_default()
    meta_font = ImageFont.truetype(str(regular_path), 14) if regular_path.exists() else ImageFont.load_default()
    draw.text((margin, 28), title, fill="#191514", font=title_font)
    draw.text(
        (margin, 72),
        "Cinnabar badge = generator-backed Drawing DSL V5",
        fill="#5A4A43",
        font=meta_font,
    )

    for index, record in enumerate(records):
        row, column = divmod(index, columns)
        x = margin + column * (card_width + gap)
        y = title_height + margin + row * (card_height + gap)
        draw.rectangle((x, y, x + card_width, y + card_height), fill="#FBF7F3", outline="#E6D9D1", width=2)
        is_dsl = record["mode"] in {"drawing-dsl", "drawing-dsl-v3"}
        badge = "DSL V5" if is_dsl else "LEGACY"
        badge_color = "#B83D2E" if is_dsl else "#85776F"
        draw.rounded_rectangle((x + 20, y + 14, x + 126, y + 40), radius=4, fill=badge_color)
        draw.text((x + 28, y + 18), badge, fill="#FBF7F3", font=meta_font)
        draw.text((x + 142, y + 14), record["label"], fill="#191514", font=label_font)
        with Image.open(_record_path(record["png"])) as image:
            preview = ImageOps.contain(image.convert("RGB"), (thumb_width, thumb_height))
        px = x + (card_width - preview.width) // 2
        py = y + label_height + (thumb_height - preview.height) // 2
        canvas.paste(preview, (px, py))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def _write_supported_sheet(title: str, records: list[dict[str, Any]], output_path: Path) -> None:
    from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

    columns = 3
    margin = 36
    gap = 24
    title_height = 104
    card_width = 540
    card_height = 400
    rows = math.ceil(len(records) / columns)
    width = margin * 2 + columns * card_width + (columns - 1) * gap
    height = title_height + margin + rows * card_height + max(0, rows - 1) * gap + margin
    canvas = Image.new("RGB", (width, height), "#F6F0EA")
    draw = ImageDraw.Draw(canvas)
    regular_path = ROOT / "assets" / "fonts" / "LXGWWenKai-Regular.ttf"
    medium_path = ROOT / "assets" / "fonts" / "LXGWWenKai-Medium.ttf"
    title_font = ImageFont.truetype(str(medium_path), 34) if medium_path.exists() else ImageFont.load_default()
    label_font = ImageFont.truetype(str(medium_path), 20) if medium_path.exists() else ImageFont.load_default()
    meta_font = ImageFont.truetype(str(regular_path), 14) if regular_path.exists() else ImageFont.load_default()
    draw.text((margin, 26), title, fill="#191514", font=title_font)
    draw.text((margin, 70), "Native diagram content, cropped from the page-preview canvas for visual review", fill="#5A4A43", font=meta_font)

    for index, record in enumerate(records):
        row, column = divmod(index, columns)
        x = margin + column * (card_width + gap)
        y = title_height + margin + row * (card_height + gap)
        draw.rectangle((x, y, x + card_width, y + card_height), fill="#FBF7F3", outline="#E6D9D1", width=2)
        draw.rounded_rectangle((x + 20, y + 14, x + 126, y + 42), radius=4, fill="#B83D2E")
        draw.text((x + 28, y + 19), "DSL V5", fill="#FBF7F3", font=meta_font)
        draw.text((x + 144, y + 14), record["label"], fill="#191514", font=label_font)
        with Image.open(_record_path(record["png"])) as image:
            rgb = image.convert("RGB")
            parchment = Image.new("RGB", rgb.size, "#F6F0EA")
            paper = Image.new("RGB", rgb.size, "#FFFFFF")
            foreground = ImageChops.darker(
                ImageChops.difference(rgb, parchment).convert("L"),
                ImageChops.difference(rgb, paper).convert("L"),
            ).point(lambda value: 255 if value > 8 else 0)
            bounds = foreground.getbbox()
            cropped = rgb.crop(bounds) if bounds else rgb
            preview = ImageOps.contain(cropped, (card_width - 40, card_height - 82))
        px = x + (card_width - preview.width) // 2
        py = y + 62 + (card_height - 72 - preview.height) // 2
        canvas.paste(preview, (px, py))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, optimize=True)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {command}")
    if result.stdout.strip():
        print(result.stdout.strip())


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _record_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-dsl-build", action="store_true", help="Reuse legacy previews; registered fixtures always compile.")
    parser.add_argument("--contact-sheet", type=Path, default=DEFAULT_CONTACT_SHEET)
    parser.add_argument("--supported-sheet", type=Path, default=DEFAULT_SUPPORTED_SHEET)
    baseline_group = parser.add_mutually_exclusive_group()
    baseline_group.add_argument("--baseline", type=Path, help="Compare the rendered catalog with an approved visual baseline.")
    baseline_group.add_argument("--write-baseline", type=Path, help="Write an approved visual baseline from this render.")
    parser.add_argument("--approval-reason", help="Required reason when writing an approved visual baseline.")
    parser.add_argument("--baseline-report", type=Path, help="Optional JSON report path for baseline comparison.")
    args = parser.parse_args(argv)
    if args.write_baseline and not str(args.approval_reason or "").strip():
        parser.error("--write-baseline requires --approval-reason")
    if args.baseline_report and not args.baseline:
        parser.error("--baseline-report requires --baseline")
    payload = load_catalog(args.fixture)
    manifest = render_catalog(
        payload,
        args.output_dir,
        build_dsl=not args.skip_dsl_build,
        contact_sheet=args.contact_sheet,
        supported_sheet=args.supported_sheet,
        catalog_fixture=args.fixture,
    )
    if args.write_baseline:
        baseline = create_visual_baseline(manifest, args.approval_reason)
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.write_baseline.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"OK: wrote approved visual baseline to {args.write_baseline}")
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report = compare_visual_baseline(manifest, baseline)
        if args.baseline_report:
            args.baseline_report.parent.mkdir(parents=True, exist_ok=True)
            args.baseline_report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if not report["passed"]:
            for issue in report["issues"]:
                print(f"ERROR: visual baseline: {issue}")
            return 1
        print(f"OK: visual baseline: {len(report['diagrams'])} diagrams passed")
    print(
        "OK: diagram catalog: "
        f"{manifest['coverage']['catalog_types']} types, "
        f"{manifest['coverage']['drawing_dsl']} Drawing DSL, "
        f"{manifest['coverage']['html_template_baseline']} HTML baselines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
