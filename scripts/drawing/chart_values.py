"""Shared value scales and locale formatting, independent of scene rendering."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil, floor, log10


@dataclass(frozen=True)
class ScalePlan:
    domain_min: float
    domain_max: float
    ticks: tuple[float, ...]
    include_zero: bool
    unit: str | None = None


@dataclass(frozen=True)
class ValueFormatPlan:
    precision: int | None = None
    compact: bool = True
    grouping: bool = False
    unit_position: str = "auto"


def nice_scale(values: Iterable[float], *, include_zero: bool, unit: str | None = None, tick_count: int = 5) -> ScalePlan:
    numbers = [float(value) for value in values]
    if not numbers:
        numbers = [0.0, 1.0]
    low, high = min(numbers), max(numbers)
    if include_zero:
        low, high = min(0.0, low), max(0.0, high)
    if low == high:
        padding = abs(low) * 0.1 or 1.0
        low -= padding
        high += padding
    rough = (high - low) / max(2, tick_count - 1)
    magnitude = 10 ** floor(log10(abs(rough)))
    normalized = rough / magnitude
    step = (1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10) * magnitude
    domain_min = floor(low / step) * step
    domain_max = ceil(high / step) * step
    ticks: list[float] = []
    value = domain_min
    while value <= domain_max + step * 0.01 and len(ticks) < 12:
        ticks.append(round(value, 10))
        value += step
    return ScalePlan(domain_min, domain_max, tuple(ticks), include_zero, unit)


def format_value(
    value: float,
    unit: str | None = None,
    locale: str = "en-US",
    value_format: ValueFormatPlan | None = None,
) -> str:
    formatting = value_format or ValueFormatPlan()
    precision = formatting.precision
    if formatting.compact:
        digits = 1 if precision is None else precision
        if locale.startswith("zh") and abs(value) >= 100_000_000:
            text = f"{value / 100_000_000:.{digits}f}亿"
        elif locale.startswith("zh") and abs(value) >= 10_000:
            text = f"{value / 10_000:.{digits}f}万"
        elif abs(value) >= 1_000_000:
            text = f"{value / 1_000_000:.{digits}f}M"
        elif abs(value) >= 1_000:
            text = f"{value / 1_000:.{digits}f}K"
        elif precision is not None:
            text = f"{value:.{precision}f}"
        elif float(value).is_integer():
            text = str(int(value))
        else:
            text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        digits = precision if precision is not None else (0 if float(value).is_integer() else 2)
        text = f"{value:,.{digits}f}" if formatting.grouping else f"{value:.{digits}f}"
    position = formatting.unit_position
    if position == "prefix" or (position == "auto" and unit in {"$", "¥", "€", "£"}):
        return f"{unit or ''}{text}"
    return f"{text}{unit or ''}"
