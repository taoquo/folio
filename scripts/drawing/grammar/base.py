from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpacingGrammar:
    grid: int = 4
    stage_left: int = 72
    stage_top: int = 76
    stage_right: int = 72
    stage_bottom: int = 56
