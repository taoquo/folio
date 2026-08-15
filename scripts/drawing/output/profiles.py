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
