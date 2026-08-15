from __future__ import annotations

import unicodedata


def measure_text(text: str, font_size: float, family: str = "serif") -> float:
    mono = "mono" in family.lower()
    width = 0.0
    for char in text:
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            width += font_size
        else:
            width += font_size * (0.62 if mono else 0.55)
    return width
