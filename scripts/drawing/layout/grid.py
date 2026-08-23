"""The 4-unit grid every coordinate snaps to."""

from __future__ import annotations

GRID = 4


def grid(value: float | int, size: int = GRID) -> int:
    """Snap a coordinate to the shared grid, which every geometry check assumes."""
    return int(round(float(value) / size) * size)
