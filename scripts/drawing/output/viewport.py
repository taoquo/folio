from __future__ import annotations

"""Output viewport contract.

The scene keeps one logical canvas. Output profiles decide how much of that
canvas is framed. The artifact and embed profiles always frame the full canvas
so existing hosts and fixed aspect ratios stay stable. The page-preview profile
frames the ink bounds with a uniform safety margin, so a diagram placed on an A4
page is not shrunk by empty scene padding.
"""

from ..scene import ResolvedScene
from .profiles import normalize_output_profile

PAGE_PREVIEW_MARGIN = 24


def scene_viewport(scene: ResolvedScene, profile: str) -> tuple[int, int, int, int]:
    """Return the (min_x, min_y, width, height) viewBox for this profile."""
    profile = normalize_output_profile(profile)
    full = (0, 0, scene.width, scene.height)
    if profile != "page-preview" or scene.width <= 0 or scene.height <= 0:
        return full
    from ..bounds import scene_ink_box

    ink = scene_ink_box(scene)
    if ink is None or ink.w <= 0 or ink.h <= 0:
        return full
    left = max(0, ink.x - PAGE_PREVIEW_MARGIN)
    top = max(0, ink.y - PAGE_PREVIEW_MARGIN)
    right = min(scene.width, ink.x + ink.w + PAGE_PREVIEW_MARGIN)
    bottom = min(scene.height, ink.y + ink.h + PAGE_PREVIEW_MARGIN)
    width = max(1, right - left)
    height = max(1, bottom - top)
    if width >= scene.width and height >= scene.height:
        return full
    return (left, top, width, height)
