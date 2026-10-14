"""Observable past-only structure for the decision policy, no fitted model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean

from decision_system import Anchor


@dataclass(frozen=True)
class Day:
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None


def ema(values: list[float], n: int) -> float:
    result = values[0]
    for v in values[1:]:
        result += 2 / (n + 1) * (v - result)
    return result


def pivots(days: list[Day], left: int, right: int) -> list[tuple[int, int, str]]:
    out = []
    for i in range(left, len(days) - right):
        window = days[i - left : i + right + 1]
        if (
            days[i].high == max(d.high for d in window)
            and sum(d.high == days[i].high for d in window) == 1
        ):
            out.append((i, i + right, "high"))
        if (
            days[i].low == min(d.low for d in window)
            and sum(d.low == days[i].low for d in window) == 1
        ):
            out.append((i, i + right, "low"))
    return out


def avwap(days: list[Day], start: int, end: int) -> float | None:
    rows = days[start : end + 1]
    if not rows or any(d.vwap is None or d.volume <= 0 for d in rows):
        return None
    return sum(d.vwap * d.volume for d in rows) / sum(d.volume for d in rows)


def context(
    history: list[Day],
    as_of: datetime,
    p: dict,
    *,
    frozen_origin: datetime | None = None,
    invalid_origins: frozenset[datetime] = frozenset(),
) -> dict:
    # Dropping future rows before any pivot, base or anchor computation is a
    # substantive invariant, not a promise about how callers slice an array.
    days = [d for d in history if d.end <= as_of]
    if any(a.end >= b.end for a, b in zip(days, days[1:], strict=False)):
        raise ValueError("daily records must have unique monotonic closes")
    if len(days) < p["adr_sessions"]:
        return dict(status="insufficient_ADR_history", available_at=as_of)
    closes = [d.close for d in days]
    ranges = [(d.high - d.low) / d.close for d in days]
    adr = fmean(ranges[-p["adr_sessions"] :])
    if adr <= 0:
        return dict(status="no_positive_range", available_at=as_of)
    eps = {n: ema(closes, n) for n in p["ema_periods"]}
    pp = pivots(days, p["pivot_left"], p["pivot_right"])
    eligible_highs = [
        (i, known)
        for i, known, kind in pp
        if kind == "high"
        and p["base_min_sessions"] <= len(days) - 1 - i <= p["base_max_sessions"]
        and days[i].end not in invalid_origins
        and (frozen_origin is None or days[i].end == frozen_origin)
    ]
    selected = (
        max(eligible_highs, key=lambda t: (days[t[0]].high, -t[0])) if eligible_highs else None
    )
    start = selected[0] if selected else None
    shape_ok = False
    lows = []
    contraction = None
    depth = None
    if start is not None:
        base = days[start:]
        lows = [i for i, known, kind in pp if kind == "low" and i >= start]
        higher_lows = len(lows) >= 2 and days[lows[-1]].low > days[lows[-2]].low
        contraction = fmean(ranges[-3:]) / max(1e-12, fmean(ranges[start : start + 3]))
        depth = (max(d.high for d in base) - min(d.low for d in base)) / (closes[-1] * adr)
        shape_ok = (
            higher_lows
            and contraction <= p["contraction_ratio_max"]
            and depth <= p["base_max_depth_ADR"]
        )
    # Three economically motivated anchor classes, with known recognition
    # dates. Gap thresholds are local adaptations rather than source constants.
    origins = []
    for kind in ("high", "low"):
        found = [
            (i, known)
            for i, known, k in pp
            if k == kind and len(days) - 1 - i <= p["base_max_sessions"]
        ]
        if found:
            i, known = found[-1]
            origins.append((i, known, kind))
    gap = []
    for i in range(p["adr_sessions"], len(days)):
        mean_volume = fmean(d.volume for d in days[i - 20 : i])
        then_adr = fmean(ranges[i - p["adr_sessions"] : i])
        if (
            abs(days[i].open / days[i - 1].close - 1) > then_adr
            and days[i].volume >= 2 * mean_volume
        ):
            gap.append(i)
    if gap:
        origins.append((gap[-1], gap[-1], "impulse"))
    anchors = []
    for i, known, kind in origins:
        price = avwap(days, i, len(days) - 1)
        if price is None:
            continue
        touches = []
        for j in range(max(known, i, len(days) - p["anchor_touch_lookback"]), len(days)):
            a = avwap(days, i, j)
            if a is not None and days[j].low <= a <= days[j].high and days[j].close >= a:
                touches.append(days[j].end)
        anchors.append(
            Anchor(
                f"{kind}:{days[i].end.isoformat()}",
                days[known].end,
                price,
                len(touches),
                touches[-1] if touches else None,
            )
        )
    return dict(
        status="observed",
        available_at=days[-1].end,
        adr=adr,
        ema=eps,
        previous_ema={n: ema(closes[:-1], n) for n in p["ema_periods"]},
        close=closes[-1],
        prior_return=closes[-1] / closes[-2] - 1,
        strength="lead"
        if eps[9] > eps[21] > eps[50]
        else "lag"
        if eps[9] < eps[21] < eps[50]
        else "mediocre",
        return30=closes[-1] / closes[-min(len(closes), p["leadership_sessions"] + 1)] - 1,
        average_dollar_volume=fmean(d.close * d.volume for d in days[-20:]),
        base_start=days[start].end if start is not None else None,
        base_recognized_at=days[selected[1]].end if selected else None,
        shape_ok=shape_ok,
        base_age=len(days) - 1 - start if start is not None else None,
        base_floor=min(d.low for d in days[start : selected[1] + 1]) if start is not None else None,
        higher_lows_indices=lows,
        contraction=contraction,
        depth_ADR=depth,
        anchors=tuple(anchors),
        base_breakout_level=max(d.high for d in days[start : selected[1] + 1])
        if start is not None
        else None,
        price_basis=(
            "Caller must bind homogeneous raw/action-consistent units; not certif"
            "ied by this function"
        ),
        EMA_seed=(
            "First observed close in provided past history, seed length recorded;"
            " no IPO-origin requirement"
        ),
        history_sessions=len(days),
        short_leadership_history=len(days) <= p["leadership_sessions"],
    )
