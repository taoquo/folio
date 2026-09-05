from __future__ import annotations


OUTPUT_PROFILE_NAMES = ("artifact", "embed", "page-preview")


def normalize_output_profile(profile: str) -> str:
    if profile not in OUTPUT_PROFILE_NAMES:
        raise ValueError(f"unknown drawing output profile: {profile}")
    return profile


def svg_root_attributes(profile: str, width: int, height: int) -> str:
    profile = normalize_output_profile(profile)
    if profile == "artifact":
        return f'width="{width}" height="{height}"'
    return 'width="100%" style="display:block;width:100%;height:auto"'


def placement_advisory(width: int, height: int, safe_width: float, safe_height: float) -> str | None:
    """Return advice when a figure is taller than the slot it is being placed into.

    This describes width-fit overflow before contain fitting. Host placement separately
    rejects poster mode and excessive shrinking; smaller fit adjustments remain advisory.
    """
    if width <= 0 or safe_width <= 0 or safe_height <= 0:
        return None
    placed_height = safe_width * (height / width)
    if placed_height <= safe_height:
        return None
    return (
        f"canvas {width}x{height} scales to {placed_height / safe_height:.1f}x the slot height; "
        "shorten the canvas or split the diagram before embedding it"
    )


def apply_html_output_profile(source: str, profile: str) -> str:
    profile = normalize_output_profile(profile)
    if profile == "artifact":
        return source
    responsive = """
  /* Folio Drawing DSL output profile */
  .frame { width: 100% !important; max-width: 100% !important; }
  svg { width: 100% !important; min-width: 0 !important; max-width: 100% !important; height: auto !important; }
"""
    if profile == "page-preview":
        responsive += """
  @page { size: A4; margin: 12mm; }
  html, body { width: auto !important; min-width: 0 !important; }
  body { min-height: 0 !important; padding: 12mm 8mm !important; overflow: visible !important; }
"""
    marker = "</style>"
    if marker not in source:
        raise ValueError("diagram HTML has no style block for output-profile injection")
    return source.replace(marker, responsive + marker, 1)
