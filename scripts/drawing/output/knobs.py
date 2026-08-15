"""Output knobs for size, detail, and audience.

Knobs are an output-layer concern. They never enter the authoring payload
schema and never add accent-carrying elements (see ADR 0006).
"""
from __future__ import annotations

from dataclasses import replace

from ..scene import ResolvedScene, SceneGroup, SceneText

OUTPUT_SIZE_NAMES = ("compact", "standard", "wide")
OUTPUT_DETAIL_NAMES = ("essential", "standard", "full")
OUTPUT_AUDIENCE_NAMES = ("executive", "general", "practitioner")

_SIZE_WIDTHS = {"compact": 1280, "standard": 1920, "wide": 2560}
_GRID_PREFIXES = ("grid:", "gridline:")
_EXECUTIVE_BUMP_BELOW = 10.0


def normalize_output_size(name: str) -> str:
    if name not in OUTPUT_SIZE_NAMES:
        raise ValueError(f"unknown drawing output size: {name}")
    return name


def size_export_width(name: str) -> int:
    return _SIZE_WIDTHS[normalize_output_size(name)]


def normalize_output_detail(name: str) -> str:
    if name not in OUTPUT_DETAIL_NAMES:
        raise ValueError(f"unknown drawing output detail: {name}")
    return name


def normalize_output_audience(name: str) -> str:
    if name not in OUTPUT_AUDIENCE_NAMES:
        raise ValueError(f"unknown drawing output audience: {name}")
    return name


def apply_output_knobs(
    scene: ResolvedScene,
    *,
    detail: str = "full",
    audience: str = "general",
) -> ResolvedScene:
    """Apply detail and audience knobs to a resolved scene."""
    scene = _apply_detail(scene, normalize_output_detail(detail))
    return _apply_audience(scene, normalize_output_audience(audience))


def _is_grid(item: object) -> bool:
    item_id = getattr(item, "id", None)
    return isinstance(item_id, str) and item_id.startswith(_GRID_PREFIXES)


def _apply_detail(scene: ResolvedScene, detail: str) -> ResolvedScene:
    if detail == "full":
        return scene
    kept: list[object] = []
    dropped: list[str] = []
    grid_index = 0
    for item in scene.primitives:
        if _is_grid(item):
            if detail == "standard" and grid_index % 2 == 0:
                kept.append(item)
            else:
                dropped.append(item.id)
            grid_index += 1
            continue
        kept.append(item)
    annotations = scene.annotations
    if detail == "essential" and annotations:
        dropped.extend(item.id for item in annotations)
        annotations = ()
    if not dropped:
        return scene
    removed = set(dropped)
    return replace(
        scene,
        primitives=tuple(kept),
        annotations=annotations,
        reading_order=tuple(item for item in scene.reading_order if item not in removed),
    )


def _apply_audience(scene: ResolvedScene, audience: str) -> ResolvedScene:
    if audience != "executive":
        return scene
    return replace(scene, primitives=tuple(_bump_text(item) for item in scene.primitives))


def _bump_text(item: object) -> object:
    if isinstance(item, SceneGroup):
        return replace(item, children=tuple(_bump_text(child) for child in item.children))
    if isinstance(item, SceneText) and item.size < _EXECUTIVE_BUMP_BELOW:
        return replace(item, size=item.size + 1)
    return item
