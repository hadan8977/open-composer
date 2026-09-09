"""F2: 12-1 momentum top-50 + SPY trend filter/cash switch, optional
volatility targeting (Step 12 Group B).

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2, F2: "A 组 B1 的 12-1 动量前 50 等权,叠加市场状态:SPY > SMA
{100,200} 时持有,否则全部转 BIL;可选波动率目标 {none, 15%}...在
RankingStrategy.score 外层加状态开关,不改 loop.py,写在 B 组自己的模块里".

This module supplies only the overlay: it reuses Group A's own
``open_composer.research.kernel.baseline_strategies.MomentumFactorStrategy``
(B1, unmodified) and
``open_composer.research.kernel.loop.build_weight_schedule``/
``returns_from_weight_schedule`` (unmodified) to get the pure momentum
ranking's weight schedule, then applies the trend-filter/vol-target switch
**after** that schedule already exists -- one call to
:func:`apply_regime_overlay` per grid cell, rather than reaching inside
``RankingStrategy.score()`` (which only ranks symbols; it has no concept of
a cash sleeve at all) or modifying ``loop.py``. This is also the efficient
choice: the expensive walk-forward ranking computation runs once; the 4
grid cells (2 trend-filter SMA lengths x 2 vol-target choices) are cheap
schedule-level derivatives of that one run.

Grid (preregistered, 2x2=4 cells, :data:`PARAMETER_SPACE`):
    trend_sma_days in {100, 200}: SPY close > its own trailing SMA -> stay
        invested in the momentum book; otherwise the whole book switches to
        BIL for that week.
    target_vol_annual in {None, 0.15}: when set, equity exposure for a
        risk-on week is scaled to ``min(1.0, target_vol_annual /
        trailing_realized_vol)`` of the momentum book's own trailing
        20-session annualized realized volatility (lagged one session), the
        residual going to BIL. Capped at 1.0 -- this overlay only ever
        de-risks toward cash, it never levers the un-levered momentum book
        above 100% equity exposure.

Walk-forward selection among the 4 cells (which cell is "live" each
calendar quarter) reuses
``open_composer.research.regime.etf_pullback_mean_reversion.select_cells_by_quarter``/
``materialize_composite`` -- those functions are mechanism-agnostic (any
``Mapping[str, pd.Series]`` of daily returns), despite living in the F1
module; see that module's docstring for the walk-forward selection
methodology this shares with F1.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import product

import pandas as pd

from open_composer.research.kernel.loop import RebalanceEvent

CASH_SYMBOL = "BIL"
COST_BPS_PER_SIDE = 10.0
STRESS_COST_BPS_PER_SIDE = 25.0
SMA_DAYS_CHOICES: tuple[int, ...] = (100, 200)
TARGET_VOL_CHOICES: tuple[float | None, ...] = (None, 0.15)
TRAILING_VOL_LOOKBACK_DAYS = 20
#: This overlay only ever de-risks toward cash -- it never levers the
#: un-levered momentum book above 100% equity exposure.
MAX_VOL_TARGET_EQUITY_WEIGHT = 1.0
LOOKBACK_MONTHS = 24

#: 4-cell preregistered grid (2 trend-filter SMA lengths x 2 vol-target
#: choices). Order is fixed (itertools.product) so cell_id "f2_cellNNN"
#: always names the same configuration across runs.
PARAMETER_SPACE: list[dict[str, int | float | None]] = [
    {"trend_sma_days": sma_days, "target_vol_annual": target_vol}
    for sma_days, target_vol in product(SMA_DAYS_CHOICES, TARGET_VOL_CHOICES)
]


def cell_id(index: int) -> str:
    return f"f2_cell{index:03d}"


def compute_risk_on_flags(
    spy_close: pd.Series, sma_days: int, rebalance_dates: Sequence[pd.Timestamp]
) -> pd.Series:
    """SPY close > its own trailing SMA(sma_days), read at each rebalance
    date's own close (the signal date) -- the SMA at date t already only
    uses data through t, so reading it at that same t is the same "signal
    computed at close" convention F1/F5 use, not a lookahead.
    """
    sma = spy_close.rolling(sma_days, min_periods=sma_days).mean()
    index = pd.DatetimeIndex(rebalance_dates)
    aligned_close = spy_close.reindex(index)
    aligned_sma = sma.reindex(index)
    risk_on = aligned_close > aligned_sma
    return risk_on.fillna(False)


def compute_equity_weight(
    risk_on: pd.Series,
    target_vol_annual: float | None,
    trailing_vol_annual: pd.Series | None = None,
) -> pd.Series:
    """Per-rebalance-date equity exposure in [0, 1].

    ``target_vol_annual=None``: a pure binary switch -- 1.0 when
    ``risk_on``, 0.0 (all BIL) otherwise.

    ``target_vol_annual`` set: ``min(1.0, target/trailing)`` on a risk-on
    date (0.0 when ``trailing_vol_annual`` is missing/non-positive there --
    conservative: an unmeasurable trailing vol never licenses full
    exposure), 0.0 on a risk-off date regardless of vol.
    """
    if target_vol_annual is None:
        weight = pd.Series(1.0, index=risk_on.index)
    else:
        if trailing_vol_annual is None:
            raise ValueError("target_vol_annual requires trailing_vol_annual")
        aligned_vol = trailing_vol_annual.reindex(risk_on.index)
        measurable = aligned_vol.notna() & (aligned_vol > 0.0)
        weight = (target_vol_annual / aligned_vol).clip(upper=MAX_VOL_TARGET_EQUITY_WEIGHT)
        weight = weight.where(measurable, 0.0)
    return weight.where(risk_on, 0.0)


def apply_regime_overlay(
    schedule: Sequence[RebalanceEvent],
    equity_weight: Mapping[pd.Timestamp, float],
    cash_symbol: str = CASH_SYMBOL,
) -> list[RebalanceEvent]:
    """Scale each event's momentum weights by that date's equity exposure
    and route the residual to ``cash_symbol`` -- the "state switch outside
    RankingStrategy.score()" the plan asks for, applied at the schedule
    level (after ``build_weight_schedule`` has already produced the pure
    momentum ranking) rather than inside ``.score()`` itself, so the
    expensive walk-forward ranking runs once and every grid cell is a cheap
    derivative of it (see module docstring).
    """
    overlaid: list[RebalanceEvent] = []
    for event in schedule:
        date = pd.Timestamp(event.date)
        weight = float(equity_weight.get(date, 0.0))
        scaled = {symbol: value * weight for symbol, value in event.selected.items()}
        if weight < 1.0:
            scaled[cash_symbol] = scaled.get(cash_symbol, 0.0) + (1.0 - weight)
        overlaid.append(
            RebalanceEvent(
                date=event.date,
                universe_size=event.universe_size,
                selected=scaled,
                portfolio_beta=event.portfolio_beta,
            )
        )
    return overlaid
