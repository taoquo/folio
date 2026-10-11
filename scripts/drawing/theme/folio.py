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


DEFAULT_FOLIO_THEME = FolioTheme()
