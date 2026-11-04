"""Where the legend sits, measured once.

The legend is anchored to the canvas bottom, and a drawing has to end above it.
The layout used to reserve a fixed band for it, which is right only while the
legend fits on one row: at a narrow stage the items wrap, the box grows, and
its top moves up into the drawing. The plate then fails a geometry check whose
cause is a band the layout guessed.

Both the layout and the scene therefore ask this module. The layout uses
``Band.top`` as the floor its rows must stay above; the scene draws the box at
the same width, height and row packing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import DrawingPlan
from .stage import current as current_stage
from .theme.folio import DEFAULT_FOLIO_THEME, FolioTheme
from .typography.measure import measure_text
from .typography.roles import TextRole, resolve_text_style

# The box is inset from the canvas edge, and the title column sits left of the
# items when the row is inline.
LEGEND_MARGIN = 16
LEGEND_TITLE_WIDTH = 64
LEGEND_ITEM_GAP = 28
LEGEND_ROW_PITCH = 36
LEGEND_INLINE_HEIGHT = 44
LEGEND_TITLE_ROW = 20
LEGEND_MIN_WIDTH = 264


@dataclass(frozen=True)
class LegendBand:
    """The legend's box and the item rows it holds."""

    width: int
    height: int
    rows: tuple[tuple[int, ...], ...]
    inline: bool

    def top(self, canvas_height: int) -> int:
        return canvas_height - self.height - LEGEND_MARGIN


def legend_rows(widths: list[int], available: int, gap: int) -> list[list[int]]:
    """Pack legend items into rows that fit ``available`` stage units."""
    rows: list[list[int]] = [[]]
    used = 0
    for index, width in enumerate(widths):
        extra = width if not rows[-1] else width + gap
        if rows[-1] and used + extra > available:
            rows.append([index])
            used = width
        else:
            rows[-1].append(index)
            used += extra
    return rows


def legend_band(
    drawing: DrawingPlan,
    theme: FolioTheme = DEFAULT_FOLIO_THEME,
) -> LegendBand | None:
    """The legend box at this drawing's width, or None when it has no legend."""
    if not drawing.legend:
        return None
    composed = not current_stage().is_default
    if composed:
        # The items are type, and type is what the measurer knows. Charging a
        # fixed seven units a character overshoots the real advance by a fifth,
        # which wraps a row that would have fitted and buys the plate height it
        # does not need.
        style = resolve_text_style(TextRole.LEGEND, theme)
        widths = [20 + 8 + int(round(measure_text(item.label, style.size, style.family)))
                  for item in drawing.legend.items]
    else:
        # The authored legend keeps the pitch its artifacts were drawn with, so
        # the published stage keeps its bytes.
        widths = [20 + 8 + len(item.label) * 7 for item in drawing.legend.items]
    available = drawing.width - 32
    inline_width = (LEGEND_MARGIN + LEGEND_TITLE_WIDTH + LEGEND_MARGIN
                    + sum(widths) + LEGEND_ITEM_GAP * max(0, len(widths) - 1)
                    + LEGEND_MARGIN)
    if inline_width <= available:
        width = int(round(max(LEGEND_MIN_WIDTH, inline_width) / 8) * 8)
        return LegendBand(width, LEGEND_INLINE_HEIGHT, (tuple(range(len(widths))),), True)
    rows = legend_rows(widths, available - 32, LEGEND_ITEM_GAP)
    height = LEGEND_TITLE_ROW + LEGEND_ROW_PITCH * len(rows)
    if any(sum(widths[i] for i in row) + LEGEND_ITEM_GAP * (len(row) - 1) > available - 32
           for row in rows):
        raise ValueError(f"legend item wider than the canvas: available {available - 32}")
    return LegendBand(available, height, tuple(tuple(row) for row in rows), False)
