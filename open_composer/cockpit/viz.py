"""Chart geometry for the cockpit's instruments (2026-09-24 redesign).

Pure numbers only -- percentages, levels, labels, tooltips. The templates
turn these into plain HTML elements positioned with CSS (see the
"instruments" section of ``static/css/cockpit.css``), which keeps every mark
crisp at any width: nothing here is an SVG that a changing column width
could stretch.

Mark rules (the dataviz spec this redesign follows): columns end in a small
rounded data-end at the value and are anchored to the baseline; the latest
real value is the only emphasized mark; grid lines are hairlines with their
labels in text tokens; every mark carries a tooltip; days or buckets without
an observation stay visible as gaps, never interpolated.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from open_composer.cockpit.data.activity import ActivityField
from open_composer.cockpit.data.paper import AccountEquityHistory


@dataclass(frozen=True)
class EquityColumn:
    day: date
    kind: str  # "up" | "down" | "flat" | "gap"
    bottom: float  # percent of plot height, from the bottom
    height: float  # percent of plot height
    value: float | None
    is_last: bool
    label: str | None  # x-axis label, only on a few columns
    title: str


@dataclass(frozen=True)
class GridLine:
    pct: float  # percent from the bottom
    label: str
    is_base: bool


@dataclass(frozen=True)
class EquityColumns:
    columns: tuple[EquityColumn, ...]
    grid: tuple[GridLine, ...]
    base: float


@dataclass(frozen=True)
class LedColumn:
    level: int  # lit dots, 0..rows
    value: int
    title: str
    is_now: bool


@dataclass(frozen=True)
class Bar:
    pct: float  # percent of the peak
    value: int
    title: str
    lit: bool  # inside the highlighted window


def _nice_step(span: float, target: int) -> float:
    raw = max(span / max(target, 1), 1e-9)
    power = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 2.5, 5, 10):
        if multiple * power >= raw:
            return multiple * power
    return 10 * power


def _money_tick(value: float, step: float) -> str:
    if step >= 1000:
        return f"{value / 1000:g}k"
    return f"{value:,.0f}"


def equity_columns(history: AccountEquityHistory, *, ticks: int = 4) -> EquityColumns | None:
    """One column per calendar day relative to the first observation."""
    if history.first is None or not history.days:
        return None
    base = history.first.equity
    values = [day.point.equity for day in history.days if day.point is not None]
    low, high = min(values + [base]), max(values + [base])
    span = (high - low) or max(abs(base) * 0.01, 1.0)
    low, high = low - span * 0.10, high + span * 0.14
    step = _nice_step(high - low, ticks)

    def pct(value: float) -> float:
        return (value - low) / (high - low) * 100.0

    grid: list[GridLine] = [GridLine(pct=pct(base), label=_money_tick(base, step), is_base=True)]
    tick = math.ceil(low / step) * step
    while tick < high:
        if abs(tick - base) > step * 0.35:
            grid.append(GridLine(pct=pct(tick), label=_money_tick(tick, step), is_base=False))
        tick += step

    count = len(history.days)
    labelled = {0, count - 1} | ({count // 2} if count >= 5 else set())
    last_index = max(i for i, day in enumerate(history.days) if day.point is not None)
    base_pct = pct(base)
    columns: list[EquityColumn] = []
    for index, day in enumerate(history.days):
        label = f"{day.day:%b} {day.day.day}" if index in labelled else None
        heading = f"{day.day:%a} {day.day:%b} {day.day.day}"
        if day.point is None:
            columns.append(
                EquityColumn(
                    day.day, "gap", base_pct, 0.0, None, False, label, f"{heading} · no snapshot"
                )
            )
            continue
        value = day.point.equity
        delta = value - base
        title = f"{heading} · ${value:,.2f} · {delta:+,.0f} vs start · {day.point.at:%H:%M}Z"
        if abs(delta) < 0.005:
            kind, bottom, height = "flat", base_pct, 0.0
        elif delta > 0:
            kind, bottom, height = "up", base_pct, pct(value) - base_pct
        else:
            kind, bottom, height = "down", pct(value), base_pct - pct(value)
        columns.append(
            EquityColumn(day.day, kind, bottom, height, value, index == last_index, label, title)
        )
    grid.sort(key=lambda line: line.pct)
    return EquityColumns(columns=tuple(columns), grid=tuple(grid), base=base)


def _bucket_label(start: datetime, minutes: int) -> str:
    end = start + timedelta(minutes=minutes)
    return f"{start:%H:%M}–{end:%H:%M}Z"


def led_columns(field: ActivityField, *, rows: int = 7, group: int = 1) -> tuple[LedColumn, ...]:
    """The activity meter: one column per `group` buckets, lit dots linear in calls."""
    group = max(1, group)
    sums = [sum(field.calls[i : i + group]) for i in range(0, len(field.calls), group)]
    peak = max(sums) if sums else 0
    columns: list[LedColumn] = []
    for index, value in enumerate(sums):
        level = 0 if value <= 0 or peak <= 0 else max(1, math.ceil(rows * value / peak))
        start = field.bucket_start(index * group)
        when = _bucket_label(start, field.bucket_minutes * group)
        what = f"{value:,} call{'s' * (value != 1)}" if value else "idle"
        columns.append(LedColumn(level, value, f"{when} · {what}", index == len(sums) - 1))
    return tuple(columns)


def fresh_bars(
    field: ActivityField, *, last: int | None = None, lit_last: int = 0
) -> tuple[Bar, ...]:
    """Fresh tokens per bucket; the last `lit_last` buckets are highlighted."""
    values: Sequence[int] = field.fresh if last is None else field.fresh[-last:]
    offset = len(field.fresh) - len(values)
    peak = max(values) if values else 0
    bars: list[Bar] = []
    for index, value in enumerate(values):
        start = field.bucket_start(offset + index)
        tokens = f"{value / 1000:,.1f}k fresh" if value else "idle"
        bars.append(
            Bar(
                pct=(value / peak * 100.0) if peak else 0.0,
                value=value,
                title=f"{_bucket_label(start, field.bucket_minutes)} · {tokens}",
                lit=index >= len(values) - lit_last,
            )
        )
    return tuple(bars)


__all__ = [
    "Bar",
    "EquityColumn",
    "EquityColumns",
    "GridLine",
    "LedColumn",
    "equity_columns",
    "fresh_bars",
    "led_columns",
]
