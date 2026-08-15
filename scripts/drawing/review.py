from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from diagram_export import export_pdf, export_png
from renderers.svg import render_svg


def write_review_bundle(
    semantic: Any,
    drawing: Any,
    layout: Any,
    scene: Any,
    output_dir: str | Path,
    baseline_png: str | Path | None = None,
    *,
    diagnostics: Any = (),
    metrics: Any = None,
    profile: str = "artifact",
    normalized_input: Any = None,
    compilation_metadata: Any = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _json(output / "input.json", normalized_input)
    _json(output / "semantic.json", semantic.to_dict() if semantic else None)
    _json(output / "drawing.json", drawing.to_dict())
    _json(output / "layout.json", asdict(layout))
    _json(output / "scene.json", scene.to_dict())
    svg_path = output / "drawing.svg"
    png_path = output / "drawing.png"
    pdf_path = output / "drawing.pdf"
    svg_path.write_text(render_svg(scene, profile), encoding="utf-8")
    export_png(
        svg_path, png_path, width=1920, profile=profile,
        title=drawing.title, language=getattr(drawing, "language", "en"),
    )
    export_pdf(svg_path, pdf_path, drawing.title, getattr(drawing, "language", "en"), profile)
    dimensions = _image_dimensions(png_path)
    layout_selection = _layout_selection(drawing)
    manifest: dict[str, Any] = {
        "schema_version": "3.0",
        "compiler_contract": "3.0",
        "compilation": compilation_metadata.to_dict() if compilation_metadata is not None else None,
        "kind": drawing.kind,
        "profile": profile,
        "dimensions": {"scene": [scene.width, scene.height], "png": list(dimensions)},
        "content_bounds": _content_bounds(scene),
        "layout_selection": layout_selection,
        "diagnostics": [asdict(item) for item in diagnostics],
        "metrics": metrics.to_dict() if metrics is not None else None,
        "artifacts": ["input.json", "semantic.json", "drawing.json", "layout.json", "scene.json", "drawing.svg", "drawing.png", "drawing.pdf"],
        "visual_diff": None,
        "baseline_category": "visual-regression" if baseline_png else None,
        "approval_state": "pending-review" if baseline_png else "not-applicable",
    }
    if baseline_png:
        manifest["visual_diff"] = _visual_diff(Path(baseline_png), png_path, output / "diff.png")
        manifest["artifacts"].append("diff.png")
    manifest["digests"] = {
        name: _sha256(output / name)
        for name in manifest["artifacts"]
        if (output / name).exists()
    }
    _json(output / "manifest.json", manifest)
    return manifest


def _json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _visual_diff(baseline_path: Path, current_path: Path, diff_path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise RuntimeError("Pillow is required for visual diff review") from exc
    baseline = Image.open(baseline_path).convert("RGBA")
    current = Image.open(current_path).convert("RGBA")
    baseline_size = baseline.size
    current_size = current.size
    dimensions_match = baseline_size == current_size
    if not dimensions_match:
        size = (max(baseline.width, current.width), max(baseline.height, current.height))
        baseline_canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        current_canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        baseline_canvas.paste(baseline, (0, 0))
        current_canvas.paste(current, (0, 0))
        baseline, current = baseline_canvas, current_canvas
    diff = ImageChops.difference(baseline, current)
    diff.save(diff_path)
    histogram = diff.convert("RGB").histogram()
    changed = sum(value for index, value in enumerate(histogram) if index % 256 != 0)
    pixels = max(1, current.width * current.height * 3)
    return {
        "baseline": str(baseline_path),
        "method": "exact-rgba-no-resize",
        "baseline_size": list(baseline_size),
        "current_size": list(current_size),
        "dimensions_match": dimensions_match,
        "changed_channel_ratio": round(changed / pixels, 6),
    }


def _image_dimensions(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as image:
        return image.size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_bounds(scene: Any) -> list[int]:
    boxes = [node.box for node in scene.nodes]
    boxes.extend(region.box for region in scene.regions if region.box)
    boxes.extend(item.box for item in scene.annotations)
    if scene.legend:
        boxes.append(scene.legend.box)
    points = [point for edge in scene.edges for point in (*edge.points, *edge.arrow.points)]
    primitive_boxes, primitive_points = _primitive_geometry(getattr(scene, "primitives", ()))
    boxes.extend(primitive_boxes)
    points.extend(primitive_points)
    xs = [box.x for box in boxes] + [box.x + box.w for box in boxes] + [point[0] for point in points]
    ys = [box.y for box in boxes] + [box.y + box.h for box in boxes] + [point[1] for point in points]
    if not xs:
        return [0, 0, 0, 0]
    return [min(xs), min(ys), max(xs), max(ys)]


def _primitive_geometry(primitives: Any) -> tuple[list[Any], list[tuple[int, int]]]:
    from .scene import SceneCircle, SceneClip, SceneGroup, SceneLine, ScenePath, ScenePolyline, SceneRect, SceneText
    from .validation.primitives import path_geometry_points

    boxes: list[Any] = []
    points: list[tuple[int, int]] = []
    for item in primitives:
        if isinstance(item, (SceneRect, SceneClip)):
            boxes.append(item.box)
        elif isinstance(item, SceneCircle):
            points.extend(((item.cx - item.r, item.cy - item.r), (item.cx + item.r, item.cy + item.r)))
        elif isinstance(item, SceneLine):
            points.extend((item.start, item.end))
        elif isinstance(item, ScenePolyline):
            points.extend(item.points)
        elif isinstance(item, ScenePath):
            points.extend(path_geometry_points(item.d))
        elif isinstance(item, SceneText):
            points.append((item.x, item.y))
        elif isinstance(item, SceneGroup):
            child_boxes, child_points = _primitive_geometry(item.children)
            boxes.extend(child_boxes)
            points.extend(child_points)
    return boxes, points


def _layout_selection(drawing: Any) -> dict[str, Any]:
    if getattr(drawing, "kind", None) != "architecture":
        return {"selected": "type-owned", "score": [], "candidates": {}}
    from .layout.candidates import rank_layout_candidates

    ranked = rank_layout_candidates(drawing)
    selected = ranked[0]
    return {
        "selected": selected.name,
        "score": list(selected.score),
        "candidates": {item.name: list(item.score) for item in ranked},
    }
