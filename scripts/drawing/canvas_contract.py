"""Shared canvas contract for every Drawing DSL family.

Every payload renders into the same 960-unit stage, so gutters, label columns, and legend
constants are all measured against that width. Height is a real knob on the 4-unit grid:
hosts trade air for density without leaving the design system. The three families keep
different height bands because their layout math needs different floors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CANVAS_WIDTH = 960


@dataclass(frozen=True)
class CanvasBand:
    """One family's bounded height knob, always on the 4-unit grid."""

    minimum: int
    maximum: int
    default: int

    def accepts(self, value: Any) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and self.minimum <= value <= self.maximum
            and value % 4 == 0
        )

    def resolve(self, payload: dict[str, Any], default: int | None = None) -> int:
        """Return a layout-safe height, falling back when the payload value is out of band.

        Callers report the bad value through :func:`canvas_issues`; this only keeps the
        layout math sane until the diagnostics are raised.
        """
        fallback = self.default if default is None else default
        value = payload.get("height", fallback)
        return value if self.accepts(value) else fallback


# Graph families (architecture, flowchart, structural, positional) need 500 units before the
# radial and quadrant label rings start colliding, and lose canvas utilization past 800.
GRAPH_CANVAS = CanvasBand(500, 800, 540)
# Charts reserve fixed top and bottom chrome, so a 400-unit stage still leaves a usable band.
CHART_CANVAS = CanvasBand(400, 720, 540)
# Box notations need room for member rows; sequence needs room for the message band.
NOTATION_CANVAS = CanvasBand(480, 800, 640)


def canvas_issues(
    payload: dict[str, Any],
    *,
    kind: str,
    band: CanvasBand,
    default_height: int | None = None,
) -> list[str]:
    """Report the canvas contract breaches for one payload."""
    issues: list[str] = []
    if payload.get("width", CANVAS_WIDTH) != CANVAS_WIDTH:
        issues.append(f"{kind} canvas width must be exactly {CANVAS_WIDTH}; use an output profile to rescale")
    fallback = band.default if default_height is None else default_height
    if not band.accepts(payload.get("height", fallback)):
        issues.append(f"{kind} canvas height must be a multiple of 4 from {band.minimum} to {band.maximum}")
    return issues

