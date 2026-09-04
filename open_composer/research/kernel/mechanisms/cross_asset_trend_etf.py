"""Cross-asset ETF time-series momentum with a cash overlay, a "GTAA"/dual-
momentum-style tactical allocation after Moskowitz, Ooi, and Pedersen ("Time
Series Momentum", Journal of Financial Economics 104(2), 2012,
https://doi.org/10.1016/j.jfineco.2011.11.003) and Hurst, Ooi, and Pedersen
("A Century of Evidence on Trend-Following Investing", Journal of Portfolio
Management 44(1), 2017, https://doi.org/10.3905/jpm.2017.44.1.015); both are
source-carded in
``reports/harness/source_cards/step10_w1_cross_asset_trend.jsonl``.

Why this is a standalone kernel mechanism instead of a
``core_beta_satellite_router`` label (see
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 4.2,
which asks to check that router first): it cannot express this mechanism.
Concretely (``open_composer/research/core_beta_satellite_core.py``):

* ``core_route_label`` hard-codes the literal strings ``"onTQQQ..."``,
  ``"neuQQQ..."`` and ``"offCASH0"`` into an f-string -- ``core_variant`` only
  ever selects a *weight* (0.5/0.75/1.0), never a symbol. There is no way to
  make the "core" leg BIL, or to remove it, which this mechanism requires (it
  has no QQQ/TQQQ leveraged core at all).
* ``load_core_beta_satellite_dataset`` unconditionally requires
  ``QQQ, TQQQ, SQQQ, SMH`` regardless of what universe a spec declares --
  ``universe_mode`` is stored only as a descriptive label in
  ``CoreBetaSatelliteParams.label`` and is never read inside
  ``_target_snapshot``; it has no behavior-changing presets.
* The satellite sleeve is a small additive tilt on top of the core
  (``satellite_budget`` defaults to 0.1, i.e. 10% of book) via
  ``per_symbol = min(max_symbol_weight, satellite_budget * scale / len(selected))``,
  not the dominant/exclusive portfolio construction this mechanism needs (up
  to 100% risky exposure split across the selected ETFs).
* ``_theme_gate_ok`` gates the whole satellite sleeve on a single hard-coded
  symbol's (default ``SMH``, semiconductors) trend/momentum -- unrelated to
  this mechanism's per-asset independent time-series-momentum filter across
  ten cross-asset ETFs.
* The core's own "risk-off" leg is ``offCASH0`` -- a literal 0% return, not
  BIL's actual realized return, which this mechanism relies on for its cash
  overlay.

None of this is fixable without rewriting core router logic, which is out of
scope for a routing-fit check. So F2 is evaluated standalone (research track
only) via ``scripts/evaluate_cross_asset_trend_sip.py``, not through the
router engine -- it is therefore **not** paper-account-executable this week.
A future product mapping would need either a new router mode or a
generalized "core" leg in ``core_beta_satellite_core`` that accepts an
arbitrary symbol/weight pair instead of the hard-coded QQQ/TQQQ pair.

Mechanism, exactly as specified in the plan (section 4.2), with one
implementation choice the plan leaves open (documented below):

On the last trading day of each calendar month, for each ETF in
``UNIVERSE`` (SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ), compute its
own trailing total return over the prior ``lookback_months`` calendar months
(a time-series-momentum sign filter -- one asset judged against its own
history, not ranked against the others). ETFs with a positive trailing
return are "eligible". From the eligible set, rank by trailing return
descending and select up to ``top_n`` of them.

**Implementation choice** (the plan specifies "top_n in {3, 5, all}, weight
in {equal, inverse-vol}, the rest stays in BIL" but does not spell out how
"top_n" and "the rest" interact when fewer than ``top_n`` ETFs are eligible,
or when ``top_n`` is smaller than the eligible count): this module treats
``top_n`` as a **slot count** -- 1/top_n of the book per slot under equal
weighting -- following the standard GTAA/dual-momentum convention (e.g. Faber
2007, "A Quantitative Approach to Tactical Asset Allocation"): an unfilled
slot (fewer eligible ETFs than ``top_n``, or ``top_n="all"`` i.e. 10 slots
covering an eligible count below 10) holds BIL instead, at the same 1/top_n
weight the slot would have held a risky asset at. Inverse-volatility
weighting redistributes the SAME aggregate risky/cash split among the
selected names by their trailing 60-trading-day realized daily-return
volatility -- it never changes how many slots are filled, only the split
across filled slots. This is a researcher's-degree-of-freedom judgment call,
recorded here rather than silently assumed.

Costs: 5bps per side (``cost_bps_per_side``, plan section 4.2's stated
convention), charged once per month-end rebalance on total absolute weight
change across every leg (all ten ETFs plus BIL) -- i.e.
``turnover = sum(abs(new_weight[s] - old_weight[s]) for s in ALL_SYMBOLS)``,
``cost = turnover * cost_bps_per_side / 10_000``, deducted from the first
held day's return following that rebalance.

No lookahead: the weights decided using data available *as of* a month-end
close are held starting the next trading day, never the same day the
decision was made.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

UNIVERSE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ")
CASH_SYMBOL = "BIL"
ALL_SYMBOLS: tuple[str, ...] = (*UNIVERSE, CASH_SYMBOL)
COST_BPS_PER_SIDE = 5.0
VOLATILITY_LOOKBACK_DAYS = 60


def _month_end_positions(index: pd.DatetimeIndex) -> list[int]:
    """Integer positions in ``index`` of each calendar month's last trading day."""
    frame = pd.DataFrame({"pos": np.arange(len(index))}, index=index)
    grouped = frame.groupby([index.year, index.month])["pos"].max()
    return sorted(int(pos) for pos in grouped.to_numpy())


def _trailing_total_return(
    wealth: pd.DataFrame, symbol: str, end_pos: int, start_pos: int
) -> float:
    start_value = wealth[symbol].iloc[start_pos]
    end_value = wealth[symbol].iloc[end_pos]
    if start_value <= 0 or not np.isfinite(start_value) or not np.isfinite(end_value):
        return float("nan")
    return float(end_value / start_value - 1.0)


def _target_weights(
    returns_panel: pd.DataFrame,
    wealth: pd.DataFrame,
    *,
    rebalance_pos: int,
    lookback_months: int,
    lookback_start_pos: int,
    top_n_effective: int,
    weighting: str,
) -> dict[str, float]:
    momentum = {
        symbol: _trailing_total_return(wealth, symbol, rebalance_pos, lookback_start_pos)
        for symbol in UNIVERSE
    }
    eligible = [symbol for symbol, value in momentum.items() if np.isfinite(value) and value > 0]
    eligible.sort(key=lambda symbol: momentum[symbol], reverse=True)
    selected = eligible[:top_n_effective]

    weights: dict[str, float] = dict.fromkeys(ALL_SYMBOLS, 0.0)
    if not selected:
        weights[CASH_SYMBOL] = 1.0
        return weights

    slot_weight = 1.0 / top_n_effective
    risky_total = slot_weight * len(selected)
    if weighting == "equal":
        for symbol in selected:
            weights[symbol] = slot_weight
    elif weighting == "inverse_vol_60d":
        window_start = max(0, rebalance_pos - VOLATILITY_LOOKBACK_DAYS + 1)
        vols = {
            symbol: float(returns_panel[symbol].iloc[window_start : rebalance_pos + 1].std(ddof=0))
            for symbol in selected
        }
        # A zero or non-finite trailing vol (degenerate/flat window) cannot be
        # inverted; fall back to equal weight for that name rather than
        # dividing by zero or dropping it silently.
        inverse = {
            symbol: (1.0 / vol if np.isfinite(vol) and vol > 0 else 1.0)
            for symbol, vol in vols.items()
        }
        inverse_sum = sum(inverse.values())
        for symbol in selected:
            weights[symbol] = risky_total * inverse[symbol] / inverse_sum
    else:
        raise ValueError(
            f"unsupported weighting={weighting!r}; expected 'equal' or 'inverse_vol_60d'"
        )

    weights[CASH_SYMBOL] = 1.0 - sum(weights[symbol] for symbol in selected)
    return weights


def daily_cross_asset_trend_returns(
    returns_panel: pd.DataFrame,
    params: Mapping[str, Any],
    *,
    rebalance_sink: list[dict[str, Any]] | None = None,
) -> pd.Series:
    """One row per trading day: this mechanism's realized daily return (post-cost).

    If ``rebalance_sink`` is given, one dict per month-end rebalance is
    appended to it (``date``, ``weights``, ``turnover``, ``cost``) -- a
    non-invasive hook so a caller can derive trading-activity diagnostics
    (time-in-market, turnover, average holding period) from the exact same
    decisions this function actually traded, without re-deriving the
    rebalance loop a second time.

    ``returns_panel`` must have one column per symbol in :data:`ALL_SYMBOLS`
    (``SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ, BIL``), a
    ``DatetimeIndex`` of trading days (naive, matching
    ``open_composer.research.kernel.benchmark_returns.daily_returns_on_naive_
    dates``'s convention), and daily total returns as values -- no prices, so
    there is no separate adjustment code path to keep in sync with the rest
    of the project's benchmark math.

    Parameters (``params``):
        lookback_months: int -- trailing total-return window, in calendar
            months, for the time-series-momentum sign filter (plan: 6 or 12).
        top_n: int | None -- slot count; ``None`` means "all"
            (``len(UNIVERSE)`` = 10 slots, i.e. every ETF is its own slot).
        weighting: str -- ``"equal"`` or ``"inverse_vol_60d"``.
        cost_bps_per_side: float -- override for :data:`COST_BPS_PER_SIDE`.
    """
    missing = [symbol for symbol in ALL_SYMBOLS if symbol not in returns_panel.columns]
    if missing:
        raise ValueError(f"returns_panel is missing required symbols: {missing}")

    lookback_months = int(params["lookback_months"])
    top_n = params.get("top_n")
    top_n_effective = len(UNIVERSE) if top_n is None else int(top_n)
    if not (1 <= top_n_effective <= len(UNIVERSE)):
        raise ValueError(f"top_n must be between 1 and {len(UNIVERSE)} (or None for 'all')")
    weighting = str(params["weighting"])
    cost_bps_per_side = float(params.get("cost_bps_per_side", COST_BPS_PER_SIDE))
    cost_rate = 2.0 * cost_bps_per_side / 10_000.0  # both sides of the changed notional

    panel = returns_panel.sort_index()
    wealth = (1.0 + panel[list(UNIVERSE)]).cumprod()
    month_end_positions = _month_end_positions(panel.index)

    # A rebalance is eligible only once at least lookback_months PRIOR
    # month-ends exist to look back across -- this must be filtered by month
    # INDEX (position within month_end_positions), not by the raw trading-day
    # position: comparing a day-position to a month count let an early
    # month-end through with too few prior months, and then
    # month_end_positions[month_idx - lookback_months] silently wrapped
    # around to the END of the list (Python negative indexing) instead of
    # raising, corrupting that rebalance's lookback window rather than
    # skipping it.
    rebalance_positions = [
        pos for idx, pos in enumerate(month_end_positions) if idx - lookback_months >= 0
    ]
    if not rebalance_positions:
        raise ValueError(
            f"no month-end has {lookback_months} prior calendar month-ends of trailing history"
        )
    # lookback_start_pos for the k-th rebalance is the month-end position
    # lookback_months calendar months earlier -- i.e. an *earlier entry* in
    # month_end_positions, not a fixed trading-day offset (calendar months
    # have variable trading-day counts).
    position_index = {pos: idx for idx, pos in enumerate(month_end_positions)}

    daily_returns: dict[pd.Timestamp, float] = {}
    previous_weights: dict[str, float] = dict.fromkeys(ALL_SYMBOLS, 0.0)
    previous_weights[CASH_SYMBOL] = 1.0
    first_cost_applied_dates: set[pd.Timestamp] = set()

    for k, rebalance_pos in enumerate(rebalance_positions):
        month_idx = position_index[rebalance_pos]
        lookback_start_pos = month_end_positions[month_idx - lookback_months]
        weights = _target_weights(
            panel,
            wealth,
            rebalance_pos=rebalance_pos,
            lookback_months=lookback_months,
            lookback_start_pos=lookback_start_pos,
            top_n_effective=top_n_effective,
            weighting=weighting,
        )
        turnover = sum(abs(weights[s] - previous_weights[s]) for s in ALL_SYMBOLS)
        cost = turnover * cost_rate
        if rebalance_sink is not None:
            rebalance_sink.append(
                {
                    "date": panel.index[rebalance_pos],
                    "weights": dict(weights),
                    "turnover": turnover,
                    "cost": cost,
                }
            )

        holding_start = rebalance_pos + 1
        holding_end = (
            rebalance_positions[k + 1] if k + 1 < len(rebalance_positions) else len(panel) - 1
        )
        if holding_start > holding_end:
            previous_weights = weights
            continue
        for day_pos in range(holding_start, holding_end + 1):
            date = panel.index[day_pos]
            day_return = sum(weights[s] * float(panel[s].iloc[day_pos]) for s in ALL_SYMBOLS)
            if date not in first_cost_applied_dates and day_pos == holding_start:
                day_return -= cost
                first_cost_applied_dates.add(date)
            daily_returns[date] = day_return
        previous_weights = weights

    if not daily_returns:
        raise ValueError("no holding period produced any returns")
    index = pd.DatetimeIndex(sorted(daily_returns))
    return pd.Series([daily_returns[ts] for ts in index], index=index, name="cross_asset_trend_etf")


#: 2 (lookback_months) x 3 (top_n) x 2 (weighting) = 12-combination fixed grid,
#: per docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 4.2.
PARAMETER_SPACE: list[dict[str, Any]] = [
    {"lookback_months": lookback_months, "top_n": top_n, "weighting": weighting}
    for lookback_months in (6, 12)
    for top_n in (3, 5, None)
    for weighting in ("equal", "inverse_vol_60d")
]
