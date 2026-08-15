from __future__ import annotations

"""Named theme profiles.

A theme profile is a full palette swap. Every color a compiler can emit comes
from a FolioTheme token, so a profile change is a deterministic token-for-token
substitution on the resolved scene. Typography tokens are intentionally not part
of the swap: text is measured during layout with the Folio families, so changing
the family after layout would invalidate every measured box.

Every profile must pass WCAG contrast for the token pairs the compilers actually
use, so a theme override can never ship an unreadable diagram.
"""

from dataclasses import asdict, replace

from .contrast import GRAPHIC_MINIMUM, LARGE_TEXT_MINIMUM, NORMAL_TEXT_MINIMUM, contrast_ratio
from .folio import DEFAULT_FOLIO_THEME, FolioTheme

THEME_PROFILE_NAMES = ("folio", "dark", "terminal")

DARK_THEME = FolioTheme(
    parchment="#16120F",
    ivory="#221C18",
    near_black="#F5EEE7",
    olive="#E2D3C6",
    stone="#C9B7A9",
    brand="#F08A72",
    brand_tint="#4A2A22",
    border="#33291F",
    muted_stroke="#8A7568",
    neutral_mid="#A99383",
    neutral_light="#8A7565",
    neutral_deep="#CBBAAB",
)

TERMINAL_THEME = FolioTheme(
    parchment="#0C1110",
    ivory="#161D1B",
    near_black="#E6F2EA",
    olive="#C7E6D2",
    stone="#A9D2B8",
    brand="#6BE39B",
    brand_tint="#1D3A2B",
    border="#22302B",
    muted_stroke="#6E8C7B",
    neutral_mid="#8FB49E",
    neutral_light="#6F9280",
    neutral_deep="#B6D9C3",
)

_PROFILES: dict[str, FolioTheme] = {
    "folio": DEFAULT_FOLIO_THEME,
    "dark": DARK_THEME,
    "terminal": TERMINAL_THEME,
}

# Token pairs the compilers actually paint. Each entry is
# (foreground token, background token, minimum ratio, role).
_TEXT_ON_SURFACE = (
    ("near_black", "parchment", NORMAL_TEXT_MINIMUM, "body text on canvas"),
    ("near_black", "ivory", NORMAL_TEXT_MINIMUM, "body text on card"),
    ("near_black", "brand_tint", NORMAL_TEXT_MINIMUM, "body text on accent tint"),
    ("olive", "parchment", NORMAL_TEXT_MINIMUM, "secondary text on canvas"),
    ("olive", "ivory", NORMAL_TEXT_MINIMUM, "secondary text on card"),
    ("stone", "parchment", NORMAL_TEXT_MINIMUM, "muted text on canvas"),
    ("stone", "ivory", NORMAL_TEXT_MINIMUM, "muted text on card"),
    ("brand", "parchment", NORMAL_TEXT_MINIMUM, "accent text on canvas"),
    ("brand", "ivory", NORMAL_TEXT_MINIMUM, "accent text on card"),
    ("brand", "brand_tint", LARGE_TEXT_MINIMUM, "accent text on accent tint"),
    ("parchment", "brand", LARGE_TEXT_MINIMUM, "reverse text on accent fill"),
    ("parchment", "olive", LARGE_TEXT_MINIMUM, "reverse text on olive fill"),
    ("parchment", "stone", LARGE_TEXT_MINIMUM, "reverse text on muted fill"),
)

_GRAPHIC_ON_SURFACE = (
    ("muted_stroke", "parchment", GRAPHIC_MINIMUM, "hairline stroke on canvas"),
    ("neutral_deep", "parchment", GRAPHIC_MINIMUM, "series stroke on canvas"),
    ("brand", "parchment", GRAPHIC_MINIMUM, "accent stroke on canvas"),
    ("olive", "parchment", GRAPHIC_MINIMUM, "structural stroke on canvas"),
    ("stone", "parchment", GRAPHIC_MINIMUM, "structural stroke on canvas"),
)

# neutral_mid and neutral_light are fill-only ramp steps. They paint bar, donut
# and mark bodies that always ship with an adjacent labeled key, and they are
# never used for text or for a stroke wider than one pixel, so WCAG non-text
# contrast is carried by the label rather than by the fill.


def theme_profile_names() -> tuple[str, ...]:
    return tuple(sorted(_PROFILES))


def normalize_theme_profile(name: str) -> str:
    if name not in _PROFILES:
        raise ValueError(f"unknown drawing theme profile: {name}")
    return name


def resolve_theme(name: str) -> FolioTheme:
    return _PROFILES[normalize_theme_profile(name)]


def contrast_violations(theme: FolioTheme) -> tuple[tuple[str, str, str, float, float], ...]:
    """Return (role, foreground token, background token, ratio, minimum) failures."""
    tokens = asdict(theme)
    violations: list[tuple[str, str, str, float, float]] = []
    for foreground, background, minimum, role in (*_TEXT_ON_SURFACE, *_GRAPHIC_ON_SURFACE):
        ratio = contrast_ratio(tokens[foreground], tokens[background])
        if ratio is None:
            violations.append((role, foreground, background, 0.0, minimum))
        elif ratio + 1e-9 < minimum:
            violations.append((role, foreground, background, round(ratio, 2), minimum))
    return tuple(violations)


def register_theme_profile(name: str, theme: FolioTheme) -> None:
    """Register a safe theme override. Rejects unreadable palettes."""
    if not name or not name.replace("-", "").isalnum():
        raise ValueError("theme profile name must be alphanumeric with optional dashes")
    if name in _PROFILES:
        raise ValueError(f"theme profile already registered: {name}")
    violations = contrast_violations(theme)
    if violations:
        detail = "; ".join(f"{role} {ratio}:1 < {minimum}:1" for role, _fg, _bg, ratio, minimum in violations)
        raise ValueError(f"theme profile {name} fails WCAG contrast: {detail}")
    _PROFILES[name] = theme


def unregister_theme_profile(name: str) -> None:
    if name in {"folio", "dark", "terminal"}:
        raise ValueError("built-in theme profiles cannot be removed")
    _PROFILES.pop(name, None)


def theme_token_map(source: FolioTheme, target: FolioTheme) -> dict[str, str]:
    """Map source color values to target color values, keyed lowercase."""
    source_tokens, target_tokens = asdict(source), asdict(target)
    mapping: dict[str, str] = {}
    for key, value in source_tokens.items():
        if isinstance(value, str) and value.startswith("#"):
            mapping[value.lower()] = target_tokens[key]
    return mapping


def with_tokens(theme: FolioTheme, **overrides: str) -> FolioTheme:
    return replace(theme, **overrides)
