"""Render variants: sketchy texture and motion reveal.

Variants are renderer-level decoration. They never enter the scene IR, never
change geometry, colour, or reading order, and never add accent-carrying
elements (ADR 0006). Static rasterisers that ignore CSS animation degrade to
the plain variant automatically.
"""
from __future__ import annotations

OUTPUT_VARIANT_NAMES = ("plain", "sketchy", "motion")

SKETCHY_BASE_FREQUENCY = 0.02
SKETCHY_DISPLACEMENT = 2.5
MOTION_DURATION_MS = 420
MOTION_STAGGER_MS = 70
MOTION_MAX_DELAY_MS = 700


def normalize_output_variant(name: str) -> str:
    if name not in OUTPUT_VARIANT_NAMES:
        raise ValueError(f"unknown drawing output variant: {name}")
    return name


def variant_defs(variant: str, namespace: str, reading_order_size: int) -> str:
    """Return the <defs> payload a variant needs, or an empty string."""
    variant = normalize_output_variant(variant)
    if variant == "sketchy":
        return _sketchy_defs(namespace)
    if variant == "motion":
        return _motion_defs(reading_order_size)
    return ""


def _sketchy_defs(namespace: str) -> str:
    filter_id = f"{namespace}--sketchy"
    return (
        f'<defs><filter id="{filter_id}" x="-6%" y="-6%" width="112%" height="112%">'
        f'<feTurbulence type="fractalNoise" baseFrequency="{SKETCHY_BASE_FREQUENCY}" numOctaves="3" seed="7" result="folio-sketchy-noise" />'
        f'<feDisplacementMap in="SourceGraphic" in2="folio-sketchy-noise" scale="{SKETCHY_DISPLACEMENT}" xChannelSelector="R" yChannelSelector="G" />'
        f"</filter><style>"
        f'rect:not([data-folio-role]),circle,line,polyline,path{{filter:url(#{filter_id})}}'
        f"</style></defs>"
    )


def _motion_defs(reading_order_size: int) -> str:
    delays = "".join(
        f'[data-reading-order="{index}"]{{animation-delay:{min(index * MOTION_STAGGER_MS, MOTION_MAX_DELAY_MS)}ms}}'
        for index in range(max(reading_order_size, 0))
    )
    return (
        "<defs><style>@media (prefers-reduced-motion: no-preference){"
        "@keyframes folio-reveal{from{opacity:0}to{opacity:1}}"
        f"[data-reading-order]{{animation:folio-reveal {MOTION_DURATION_MS}ms ease-out both}}"
        f"{delays}"
        "}</style></defs>"
    )

