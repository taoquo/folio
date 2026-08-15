from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FolioTheme:
    parchment: str = "#F6F0EA"
    ivory: str = "#FBF7F3"
    near_black: str = "#191514"
    olive: str = "#5A4A43"
    stone: str = "#74665F"
    brand: str = "#B83D2E"
    brand_tint: str = "#F7E6E1"
    border: str = "#E9DED4"
    muted_stroke: str = "#9C8470"
    neutral_mid: str = "#B9ACA3"
    neutral_light: str = "#D7CBC2"
    neutral_deep: str = "#8B8078"
    serif: str = "Charter, Georgia, serif"
    mono: str = "'JetBrains Mono', monospace"


DEFAULT_FOLIO_THEME = FolioTheme()
