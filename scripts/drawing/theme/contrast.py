from __future__ import annotations

"""Color math shared by theme profiles and the visual quality gate.

Keeping this module dependency-free lets both the theme registry and the
validation layer use the same WCAG relative-luminance implementation without an
import cycle.
"""

LARGE_TEXT_MINIMUM = 3.0
NORMAL_TEXT_MINIMUM = 4.5
GRAPHIC_MINIMUM = 3.0


def parse_hex(value: str) -> tuple[int, int, int] | None:
    token = value.strip().lstrip("#")
    if len(token) == 3:
        token = "".join(character * 2 for character in token)
    if len(token) != 6:
        return None
    try:
        return tuple(int(token[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def luminance(color: tuple[int, int, int]) -> float:
    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float | None:
    foreground_rgb = parse_hex(foreground)
    background_rgb = parse_hex(background)
    if foreground_rgb is None or background_rgb is None:
        return None
    high, low = sorted((luminance(foreground_rgb), luminance(background_rgb)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def composite(foreground: str, background: str, opacity: float) -> str:
    if foreground.lower() == "none":
        return background
    fg = parse_hex(foreground)
    bg = parse_hex(background)
    if fg is None or bg is None:
        return background
    mixed = tuple(round(channel * opacity + base * (1 - opacity)) for channel, base in zip(fg, bg))
    return "#" + "".join(f"{channel:02X}" for channel in mixed)
