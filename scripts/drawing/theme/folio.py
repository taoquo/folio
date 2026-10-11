from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FolioTheme:
    parchment: str = "#F6F0EA"
    ivory: str = "#FBF7F3"
    near_black: str = "#191514"
    olive: str = "#5A4A43"
    # Deep enough to hold an edge at diagram scale, where a label sits on the
    # parchment canvas rather than on paper-white. Named `label` rather than
    # `stone` because it is not the document stone (#85776F), and calling it
    # the same thing hid a real difference between the two themes.
    label: str = "#74665F"
    brand: str = "#B83D2E"
    brand_tint: str = "#F7E6E1"
    border: str = "#E9DED4"
    muted_stroke: str = "#9C8470"
    neutral_mid: str = "#B9ACA3"
    neutral_light: str = "#D7CBC2"
    neutral_deep: str = "#8B8078"
    # The repository ships Source Serif 4; listing it first is what makes a
    # diagram render the same on a machine that has never seen Charter.
    serif: str = '"Source Serif 4", Charter, Georgia, serif'
    mono: str = "'JetBrains Mono', monospace"


# Drawing token -> the document theme role it mirrors. The rest of the fields are
# the drawing theme's own and stay literal.
_SHARED_WITH_DOCUMENT = {
    "parchment": "color.surface.page",
    "ivory": "color.surface.card",
    "near_black": "color.text.primary",
    "olive": "color.text.secondary",
    "brand": "color.accent.brand",
    "brand_tint": "color.accent.tint",
    "border": "color.border.default",
}


def shared_from_document_theme() -> dict[str, str]:
    """The colours both themes state, read from the document theme.

    Returns an empty mapping when the profile layer cannot be read, so the
    literals above stay in force and a diagram can always be drawn.
    """
    import os
    import sys
    from pathlib import Path as _Path

    scripts = _Path(__file__).resolve().parents[2]
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        import style_resolver
    except Exception:  # pragma: no cover - depends on the host layout
        return {}

    name = (os.environ.get("FOLIO_THEME") or "").strip() or None
    try:
        style = style_resolver.resolve(names={"theme": name} if name else None)
    except Exception:  # pragma: no cover - a broken profile must not stop a drawing
        return {}

    out: dict[str, str] = {}
    for field, role in _SHARED_WITH_DOCUMENT.items():
        value = style.get(role)
        text = str(value).strip() if value is not None else ""
        if text.startswith("#"):
            out[field] = text
    return out


DEFAULT_FOLIO_THEME = FolioTheme(**shared_from_document_theme())
