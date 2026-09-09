"""Step 12 Group B (recent-regime, high-hit-rate) metrics.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 1. These are the metrics the recent-regime contract needs that
``open_composer.research.kernel.mechanism_eval`` does not already compute --
per-holding-period hit rate/profit factor (mechanism_eval works entirely in
daily return streams, never in discrete holding periods) and calendar-
quarter/calendar-week framing for the disclosure section. CAGR, max
drawdown, and Sharpe are reused directly from ``mechanism_eval`` and
``campaign_statistics`` by ``gates.py`` rather than reimplemented here.

Every function takes plain ``Sequence[float]``/``pd.Series`` inputs and
raises on empty input rather than returning a sentinel -- an empty holding-
period list or return window is a caller bug (an experiment with zero
trades/zero recent-window rows should never reach gate evaluation), not a
number to silently paper over.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd


def hit_rate(holding_period_net_returns: Sequence[float]) -> float:
    """Fraction of holding periods with net return > 0.

    ``holding_period_net_returns`` must already exclude flat/no-position
    periods (plan section 1: "空仓期不计入分母") -- callers build this list
    only from periods where the strategy actually held a position (a
    completed trade, a week with a non-BIL-only allocation, or a session
    with a realized intraday position), never from a daily mark-to-market
    series that includes zero-return flat days.
    """
    if not holding_period_net_returns:
        raise ValueError("hit_rate requires at least one holding period")
    wins = sum(1 for value in holding_period_net_returns if value > 0.0)
    return wins / len(holding_period_net_returns)


def profit_factor(holding_period_net_returns: Sequence[float]) -> float:
    """Sum of winning holding-period returns / abs(sum of losing ones).

    Same holding-period list as :func:`hit_rate`. Returns ``math.inf`` when
    there are gains and zero losses (genuinely undefined upside, not an
    error) and ``0.0`` when there are losses but no gains.
    """
    if not holding_period_net_returns:
        raise ValueError("profit_factor requires at least one holding period")
    gains = math.fsum(value for value in holding_period_net_returns if value > 0.0)
    losses = math.fsum(-value for value in holding_period_net_returns if value < 0.0)
    if math.isclose(losses, 0.0, abs_tol=1e-15):
        return math.inf if gains > 0.0 else 0.0
    return gains / losses


def _compound(returns: pd.Series) -> float:
    return float(np.prod(1.0 + returns.to_numpy())) - 1.0


def quarterly_returns(daily_returns: pd.Series) -> dict[str, float]:
    """Compounded net return per natural calendar quarter, keyed ``"YYYYQn"``."""
    if daily_returns.empty:
        raise ValueError("quarterly_returns requires at least one observation")
    grouped = daily_returns.groupby([daily_returns.index.year, daily_returns.index.quarter])
    return {f"{int(year)}Q{int(quarter)}": _compound(group) for (year, quarter), group in grouped}


def positive_quarter_fraction(daily_returns: pd.Series) -> float:
    """Fraction of natural calendar quarters with a positive compounded return."""
    quarters = quarterly_returns(daily_returns)
    positive = sum(1 for value in quarters.values() if value > 0.0)
    return positive / len(quarters)


def return_skewness(daily_returns: pd.Series) -> float:
    """Sample skewness (Fisher-Pearson, bias-corrected) of the return series.

    Negative values flag the "small wins, occasional large loss" shape the
    plan requires the report to quantify for high-hit-rate candidates
    (plan section 0: "高胜率策略常伴随负偏度（小赚多次、偶尔大亏）").
    """
    if len(daily_returns) < 3:
        raise ValueError("return_skewness requires at least 3 observations")
    return float(pd.Series(daily_returns).skew())


def weekly_returns(daily_returns: pd.Series) -> list[float]:
    """Compounded return per calendar week -- the holding-period unit for a
    mechanism that is always invested in something (F2's cash-switched
    momentum book, F5's beta router) and therefore has no flat period to
    exclude the way a discrete-trade mechanism (F1, F3) does: every week is
    a holding period.
    """
    if daily_returns.empty:
        raise ValueError("weekly_returns requires at least one observation")
    weekly = daily_returns.groupby(pd.PeriodIndex(daily_returns.index, freq="W")).apply(_compound)
    return weekly.tolist()


def worst_single_week_return(daily_returns: pd.Series) -> float:
    """Worst compounded return over any single calendar week present."""
    if daily_returns.empty:
        raise ValueError("worst_single_week_return requires at least one observation")
    weekly = daily_returns.groupby(pd.PeriodIndex(daily_returns.index, freq="W")).apply(_compound)
    return float(weekly.min())


def annualized_trade_count(trade_count: int, *, years: float) -> float:
    """Trade count normalized to trades/year, for the turnover disclosure item."""
    if years <= 0:
        raise ValueError("years must be positive")
    return trade_count / years


def window_years(daily_returns: pd.Series) -> float:
    """Elapsed calendar span of ``daily_returns``, in years (365.25-day)."""
    if daily_returns.empty:
        raise ValueError("window_years requires at least one observation")
    span_days = (daily_returns.index.max() - daily_returns.index.min()).days
    return max(span_days, 1) / 365.25


def replay_year_return(daily_returns: pd.Series, year: int) -> float | None:
    """Compounded return for one specific calendar year, or ``None`` if absent.

    Plan section 1's "如果 2022 年再来一次会怎样" disclosure: reports the
    strategy's own already-realized calendar-year return from its
    continuous walk-forward stream, not a re-optimized replay.
    """
    year_returns = daily_returns.loc[daily_returns.index.year == year]
    if year_returns.empty:
        return None
    return _compound(year_returns)
