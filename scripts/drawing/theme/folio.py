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
    # A chart's series colours, named for the donut because it paints all six in
    # order. The values are the ones these charts already use -- `series_3` is
    # `neutral_mid` and so on -- so introducing them moves nothing. The point is
    # that `folio` now reads them from the document scheme, which is what makes a
    # chart follow it. A line chart strokes 1, 2 and 6 at 1.6px, so those three
    # carry a non-text contrast obligation; 3, 4 and 5 are fills that always ship
    # beside a labelled key.
    series_1: str = "#5A4A43"
    series_2: str = "#74665F"
    series_3: str = "#B9ACA3"
    series_4: str = "#D7CBC2"
    series_5: str = "#F7E6E1"
    series_6: str = "#8B8078"
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
    "brand_tint": "color.accent.brand-tint",
    "border": "color.border.default",
    "series_1": "color.series.1",
    "series_2": "color.series.2",
    "series_3": "color.series.3",
    "series_4": "color.series.4",
    "series_5": "color.series.5",
    "series_6": "color.series.6",
}


def shared_from_document_theme(theme: str | None = None) -> dict[str, str]:
    """The colours both themes state, read from the document theme.

    Returns an empty mapping when the profile layer cannot be read, so the
    literals above stay in force and a diagram can always be drawn. A role that
    does not resolve is reported rather than dropped: dropping it put the literal
    back in force without saying so, which is how a role rename here went
    unnoticed and left the accent tint on the default value.
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

    name = theme or (os.environ.get("FOLIO_THEME") or "").strip() or None
    try:
        style = style_resolver.resolve(names={"theme": name} if name else None)
    except Exception:  # pragma: no cover - a broken profile must not stop a drawing
        return {}

    out: dict[str, str] = {}
    unresolved: list[str] = []
    for field, role in _SHARED_WITH_DOCUMENT.items():
        value = style.get(role)
        text = str(value).strip() if value is not None else ""
        if text.startswith("#"):
            out[field] = text
        else:
            unresolved.append(f"{field} <- {role}")
    if unresolved and os.environ.get("FOLIO_STRICT_THEME"):
        raise ValueError(
            "the drawing theme names roles the document theme does not carry: "
            + ", ".join(unresolved)
        )
    return out


def folio_theme_for(theme: str | None = None) -> FolioTheme:
    """The folio drawing theme as a named document scheme would produce it.

    The rest of the fields keep their literals: only the shared tokens follow a
    scheme, and the series are six of them.
    """
    return FolioTheme(**shared_from_document_theme(theme))


DEFAULT_FOLIO_THEME = folio_theme_for()
