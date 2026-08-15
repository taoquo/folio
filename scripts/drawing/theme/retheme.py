from __future__ import annotations

"""Deterministic palette swap on a resolved scene.

Compilers always paint with FolioTheme tokens, so a theme profile change is a
value substitution on the color-bearing fields of the scene tree. Layout,
geometry, text measurement and reading order are untouched, which keeps every
geometry and accessibility assertion valid across profiles.
"""

from dataclasses import fields, is_dataclass, replace
from typing import Any

from ..scene import ResolvedScene
from .folio import DEFAULT_FOLIO_THEME, FolioTheme
from .profiles import theme_token_map

COLOR_FIELDS = frozenset({"fill", "stroke", "background"})


def retheme_scene(scene: ResolvedScene, theme: FolioTheme, *, source: FolioTheme | None = None) -> ResolvedScene:
    source = source or DEFAULT_FOLIO_THEME
    if theme == source:
        return scene
    mapping = theme_token_map(source, theme)
    if not mapping:
        return scene
    return _walk(scene, mapping)


def _swap(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(value.lower(), value)


def _walk(value: Any, mapping: dict[str, str], *, color: bool = False) -> Any:
    if isinstance(value, str):
        return _swap(value, mapping) if color else value
    if is_dataclass(value) and not isinstance(value, type):
        updates: dict[str, Any] = {}
        for item in fields(value):
            current = getattr(value, item.name)
            updated = _walk(current, mapping, color=color or item.name in COLOR_FIELDS)
            if updated is not current:
                updates[item.name] = updated
        return replace(value, **updates) if updates else value
    if isinstance(value, tuple):
        items = tuple(_walk(item, mapping, color=color) for item in value)
        return items if any(new is not old for new, old in zip(items, value)) else value
    if isinstance(value, list):
        items = [_walk(item, mapping, color=color) for item in value]
        return items if any(new is not old for new, old in zip(items, value)) else value
    if isinstance(value, dict):
        items = {key: _walk(item, mapping, color=color) for key, item in value.items()}
        return items if any(items[key] is not value[key] for key in value) else value
    return value

