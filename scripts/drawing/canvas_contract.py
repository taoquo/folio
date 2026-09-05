"""Shared canvas contract for every Drawing DSL family.

Every payload renders into the same 960-unit stage, so gutters, label columns, and legend
constants are all measured against that width. Height is a real knob on the 4-unit grid:
hosts trade air for density without leaving the design system. The three families keep
different height bands because their layout math needs different floors.

A payload also declares what it is for. A ``figure`` is an illustration inside a column of
text, so it keeps the tight height band and the editorial node budget. A ``poster`` is the
artifact itself, so it may grow downward until its content is placed. Width never moves in
either mode: it is what makes an embedded diagram fit its column, and every gutter and
legend constant in the system is measured against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CANVAS_WIDTH = 960

CANVAS_MODES = ("figure", "poster")
DEFAULT_CANVAS_MODE = "figure"

# A 960-unit stage places five nodes across before the sixth overflows, measured. Width is
# the constraint that never moves, so this bounds every row in every mode.
NODES_PER_ROW = 5
# Chrome is 92 above the first band and 72 below the last, both constant in placed scenes,
# plus the 64-unit node box the first row occupies.
ROW_CHROME = 164 + 64
# The layout spreads rows evenly over whatever height it is given, so what bounds capacity is
# the pitch below which it reports an overlap. Measured at 72: every height from 500 to 3000
# places exactly (height - ROW_CHROME) // 72 + 1 rows, and one row more fails.
# test_drawing_canvas_modes pins this against the ten measured heights.
MIN_ROW_PITCH = 72

# Operational limits for the existing fixed-size Architecture router. These do not
# certify readability; the independent complexity diagnostics still apply.
POSTER_MAX_NODES = 265
POSTER_MAX_EDGES = 530


def rows_for_height(height: int) -> int:
    """Return how many node rows a canvas of this height places without overlapping."""
    return max(1, (height - ROW_CHROME) // MIN_ROW_PITCH + 1)


def height_for_rows(rows: int) -> int:
    """Return the shortest 4-unit canvas that places this many rows."""
    height = ROW_CHROME + max(0, rows - 1) * MIN_ROW_PITCH
    return height + (-height % 4)


def canvas_mode(payload: dict[str, Any]) -> str:
    """Return the declared canvas mode, falling back to the bounded default.

    An unknown value resolves to ``figure`` so layout math stays sane; the caller reports
    the bad value through :func:`canvas_issues`.
    """
    value = payload.get("canvas", DEFAULT_CANVAS_MODE)
    return value if value in CANVAS_MODES else DEFAULT_CANVAS_MODE


@dataclass(frozen=True)
class CanvasBand:
    """One family's bounded height knob, always on the 4-unit grid.

    ``maximum`` and ``poster_maximum`` are different kinds of rule. The floor is layout
    math: below it a family's label rings and bands collide, in any mode. The figure
    ceiling protects canvas utilisation, which only matters for a diagram that has to sit
    inside something else, so a poster is measured against the larger ceiling instead.
    """

    minimum: int
    maximum: int
    default: int
    poster_maximum: int

    def ceiling(self, mode: str = DEFAULT_CANVAS_MODE) -> int:
        return self.poster_maximum if mode == "poster" else self.maximum

    def accepts(self, value: Any, mode: str = DEFAULT_CANVAS_MODE) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and self.minimum <= value <= self.ceiling(mode)
            and value % 4 == 0
        )

    def resolve(self, payload: dict[str, Any], default: int | None = None) -> int:
        """Return a layout-safe height, falling back when the payload value is out of band.

        Callers report the bad value through :func:`canvas_issues`; this only keeps the
        layout math sane until the diagnostics are raised.
        """
        fallback = self.default if default is None else default
        value = payload.get("height", fallback)
        return value if self.accepts(value, canvas_mode(payload)) else fallback


# Graph families (architecture, flowchart, structural, positional) need 500 units before the
# radial and quadrant label rings start colliding, and lose canvas utilization past 800 --
# the floor is layout math, the ceiling is utilisation, so only the ceiling moves for posters.
GRAPH_CANVAS = CanvasBand(500, 800, 540, poster_maximum=4000)
# Charts reserve fixed top and bottom chrome, so a 400-unit stage still leaves a usable band.
# A chart's plot area stretches rather than paginating, so its poster ceiling stays lower.
CHART_CANVAS = CanvasBand(400, 720, 540, poster_maximum=2400)
# Box notations need room for member rows; sequence needs room for the message band.
NOTATION_CANVAS = CanvasBand(480, 800, 640, poster_maximum=4000)


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
    declared = payload.get("canvas", DEFAULT_CANVAS_MODE)
    if declared not in CANVAS_MODES:
        issues.append(f"{kind} canvas must be one of {', '.join(CANVAS_MODES)}")
    mode = canvas_mode(payload)
    fallback = band.default if default_height is None else default_height
    requested = payload.get("height", fallback)
    if not band.accepts(requested, mode):
        ceiling = band.ceiling(mode)
        issues.append(f"{kind} canvas height must be a multiple of 4 from {band.minimum} to {ceiling}")
        # Only a height that clears the figure ceiling has anything to gain from poster mode.
        # An off-grid or below-floor height is wrong in either mode, and saying otherwise
        # would send an author to change modes when they needed to change the number.
        outgrew_figure = (
            mode != "poster"
            and isinstance(requested, int)
            and not isinstance(requested, bool)
            and requested > band.maximum
            and requested <= band.poster_maximum
            and requested % 4 == 0
        )
        if outgrew_figure:
            issues.append(f'{kind} needs "canvas": "poster" for a height above {band.maximum}')
    return issues

def row_capacity(payload: dict[str, Any], *, figure_ceiling: int, band: CanvasBand | None = None) -> int:
    """Return how many stacked rows one payload may hold, at unchanged density.

    This is the rule for elastic content -- chart rows, which the layout compresses to fit
    rather than placing at a fixed size. Their editorial ceiling protects density, not
    placement: forty gantt rows fit inside 668 units, and are unreadable there. So a poster
    earns proportionally more rows because it has proportionally more room, and each row keeps
    the height it had in a figure.

    Fixed-size content uses :func:`rows_for_height` instead, because a node box does not
    shrink and what bounds it is the pitch at which the layout reports an overlap.
    """
    if canvas_mode(payload) != "poster":
        return figure_ceiling
    height = payload.get("height")
    if not isinstance(height, int) or isinstance(height, bool):
        return figure_ceiling
    reference = (band or CHART_CANVAS).default
    return max(figure_ceiling, figure_ceiling * height // reference)


def height_for_row_capacity(
    rows: int,
    *,
    figure_ceiling: int,
    band: CanvasBand | None = None,
) -> int:
    """Return the shortest grid-aligned canvas that preserves a figure's row density."""
    target = band or CHART_CANVAS
    if rows <= figure_ceiling:
        return target.default
    height = -(-rows * target.default // figure_ceiling)
    return height + (-height % 4)
