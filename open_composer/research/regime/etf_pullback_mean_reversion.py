"""F1: multi-ETF pullback mean reversion (Step 12 Group B).

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 2, F1. A classic high-hit-rate family: buy a short-term oversold dip
in an uptrending ETF, exit on mean reversion or a hold-period cap.

Universe: SPY, QQQ, IWM, XLK, SMH, XLF, XLE, XLV, XLY, XLI (10 symbols) plus
BIL as the cash sleeve for uninvested capital. Each symbol owns a fixed,
dedicated 1/10 slot of the book: when a symbol's entry rule fires it takes
its own slot at weight 1/10 (never shared with or reduced by other symbols
triggering the same day -- with 10 dedicated slots for 10 symbols, "多标的
同时触发时等权分配现金" (plan section 2) reduces to each of them simply
taking its own already-equal-weight slot); any slot not currently in a
position earns BIL's return. This is a documented, deliberately simple
sizing convention (not the only possible reading of the plan's one-line
sizing rule), chosen because it is unambiguous, path-independent per
symbol, and does not require a separate cash-reallocation-on-exit rule.

Entry (all three require an uptrend filter, ``close > SMA200``):
    rsi2_oversold        -- RSI(2) < 10
    down_streak_3        -- 3 consecutive down closes
    close_below_sma5_atr -- close < SMA5 - 1.0 x ATR14

Exit (either condition, whichever comes first, plus a hold-period cap):
    close_above_sma5 | rsi2_overbought (RSI(2) > 70), OR max_hold_days elapsed

Grid: 3 entry rules x 2 exit rules x 2 hold-day caps (3, 5) = 12 cells,
preregistered in :data:`PARAMETER_SPACE` -- plan section 2's "网格已在此
预注册，不得增加".

Timing (no lookahead): every indicator at bar t uses only data through and
including close[t]; the entry/exit decision made at close[t] fills at
open[t+1] (plan section 1: "信号日收盘算、次日开盘成交"). Following
``open_composer.research.kernel.loop.returns_from_weight_schedule``'s
``execution="next_open"`` convention exactly (see that function's
docstring): the fill day itself earns zero return under the new position
(cost is charged there instead) because an order filled at today's open
cannot capture a move that already happened by the time of the fill: the
position's realized return window is open-to-open returns for every day
from (entry_fill_date + 1) through exit_fill_date inclusive -- the exit
fill day's own open-to-open return IS included, since the position is still
held through last night's close and is only sold at today's open. For BIL
weight bookkeeping this means a slot is "in BIL" (earns BIL's open-to-open
return) on the entry fill day itself and returns to being "in BIL" the day
after the exit fill day -- it is "in equity" for exactly the same window
its equity return is realized, so the two bookkeeping legs never overlap
and never leave a gap.

"Training" for this rule family (plan section 1) means walk-forward
*selection* among the 12 preregistered grid cells, never fitting a
continuous parameter: :func:`select_cells_by_quarter` picks, at the start
of each calendar quarter, whichever cell had the best trailing daily
Sharpe over the preceding ``lookback_months`` (24) of its own
already-computed portfolio return stream, then :func:`materialize_composite`
applies that cell's actual returns/trades for the upcoming quarter. This
runs across the *entire* available history (as far back as a full 24-month
lookback past the SMA200 warmup allows), not only the recent gated window --
the earlier quarters become the mandatory 2018-2023 disclosure evidence,
using the exact same procedure as the gated 2024+ quarters, not a
differently-built number.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from open_composer.research.kernel.datamodel import ResearchDataModel

SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "IWM", "XLK", "SMH", "XLF", "XLE", "XLV", "XLY", "XLI")
CASH_SYMBOL = "BIL"
COST_BPS_PER_SIDE = 10.0
STRESS_COST_BPS_PER_SIDE = 25.0
SMA_TREND_DAYS = 200
SMA_EXIT_DAYS = 5
RSI_PERIOD = 2
ATR_PERIOD = 14
RSI_OVERSOLD = 10.0
RSI_OVERBOUGHT = 70.0
ATR_MULTIPLIER = 1.0
LOOKBACK_MONTHS = 24

ENTRY_RULES: tuple[str, ...] = ("rsi2_oversold", "down_streak_3", "close_below_sma5_atr")
EXIT_RULES: tuple[str, ...] = ("close_above_sma5", "rsi2_overbought")
MAX_HOLD_DAYS_CHOICES: tuple[int, ...] = (3, 5)

#: 12-cell preregistered grid (3 entry x 2 exit x 2 hold-day cap). Order is
#: fixed and deterministic (itertools.product over the tuples above) so
#: cell_id "cellNNN" always names the same configuration across runs.
PARAMETER_SPACE: list[dict[str, Any]] = [
    {"entry_rule": entry_rule, "exit_rule": exit_rule, "max_hold_days": max_hold_days}
    for entry_rule, exit_rule, max_hold_days in product(
        ENTRY_RULES, EXIT_RULES, MAX_HOLD_DAYS_CHOICES
    )
]


def cell_id(index: int) -> str:
    return f"f1_cell{index:03d}"


@dataclass(frozen=True)
class TradeRecord(ResearchDataModel):
    """One completed (or, at the end of the sample, force-closed) trade."""

    symbol: str
    cell_id: str
    entry_signal_date: str
    entry_fill_date: str
    exit_signal_date: str
    exit_fill_date: str
    net_return: float
    forced_close_at_sample_end: bool = False


def _wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder-smoothed RSI (Connors RSI(2) convention). NaN until warmup,
    which pandas/numpy comparisons (``<``, ``>``) already treat as False --
    no separate warmup mask is needed by callers.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 with avg_gain > 0: pure uptrend over the window, RSI=100.
    # avg_loss == 0 and avg_gain == 0: perfectly flat, conventionally RSI=50.
    rsi = rsi.mask((avg_loss == 0.0) & (avg_gain > 0.0), 100.0)
    rsi = rsi.mask((avg_loss == 0.0) & (avg_gain == 0.0), 50.0)
    return rsi


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def compute_indicators(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """``frame`` must have columns open/high/low/close, DatetimeIndex, sorted.

    Every series is computed causally (uses data through row t only); a
    value at row t never depends on row t+1 or later.
    """
    close = frame["close"]
    down_streak_3 = (close.diff() < 0).rolling(3, min_periods=3).sum() == 3
    return {
        "open": frame["open"],
        "close": close,
        "sma200": close.rolling(SMA_TREND_DAYS, min_periods=SMA_TREND_DAYS).mean(),
        "sma5": close.rolling(SMA_EXIT_DAYS, min_periods=SMA_EXIT_DAYS).mean(),
        "rsi2": _wilder_rsi(close, RSI_PERIOD),
        "atr14": _wilder_atr(frame["high"], frame["low"], close, ATR_PERIOD),
        "down_streak_3": down_streak_3,
    }


def _entry_signal(entry_rule: str, ind: Mapping[str, pd.Series]) -> pd.Series:
    above_trend = ind["close"] > ind["sma200"]
    if entry_rule == "rsi2_oversold":
        condition = ind["rsi2"] < RSI_OVERSOLD
    elif entry_rule == "down_streak_3":
        condition = ind["down_streak_3"]
    elif entry_rule == "close_below_sma5_atr":
        condition = ind["close"] < (ind["sma5"] - ATR_MULTIPLIER * ind["atr14"])
    else:
        raise ValueError(f"unknown entry_rule {entry_rule!r}")
    return (above_trend & condition).fillna(False)


def _exit_signal(exit_rule: str, ind: Mapping[str, pd.Series]) -> pd.Series:
    if exit_rule == "close_above_sma5":
        condition = ind["close"] > ind["sma5"]
    elif exit_rule == "rsi2_overbought":
        condition = ind["rsi2"] > RSI_OVERBOUGHT
    else:
        raise ValueError(f"unknown exit_rule {exit_rule!r}")
    return condition.fillna(False)


def simulate_symbol(
    symbol: str,
    cell: str,
    frame: pd.DataFrame,
    params: Mapping[str, Any],
    cost_bps_per_side: float,
) -> tuple[pd.Series, pd.Series, list[TradeRecord]]:
    """Compute indicators/signals for one symbol and run its state machine.

    Returns ``(equity_return, active, trades)`` -- see
    :func:`run_state_machine` for the exact meaning of each; this function
    only adds the entry/exit signal computation in front of it.
    """
    ind = compute_indicators(frame)
    entry_signal = _entry_signal(params["entry_rule"], ind)
    exit_signal = _exit_signal(params["exit_rule"], ind)
    return run_state_machine(
        symbol,
        cell,
        frame["open"],
        entry_signal,
        exit_signal,
        max_hold_days=int(params["max_hold_days"]),
        cost_bps_per_side=cost_bps_per_side,
    )


def run_state_machine(
    symbol: str,
    cell: str,
    open_: pd.Series,
    entry_signal: pd.Series,
    exit_signal: pd.Series,
    *,
    max_hold_days: int,
    cost_bps_per_side: float,
) -> tuple[pd.Series, pd.Series, list[TradeRecord]]:
    """One symbol's entry/exit/hold-cap state machine, independent of how
    ``entry_signal``/``exit_signal`` were computed -- factored out from
    :func:`simulate_symbol` so it can be unit-tested against hand-built
    signal series without needing 200 days of SMA200 warmup data.

    Returns ``(equity_return, active, trades)``: ``equity_return`` is this
    symbol's own 100%-notional open-to-open return, zero outside its active
    window, already net of the two per-trade cost debits (charged on the
    entry and exit fill days); ``active`` is True on exactly the days
    counted in ``equity_return``'s window (see module docstring's timing
    section); ``trades`` is the list of completed round trips. Callers
    combine several symbols' ``equity_return``/``active`` series plus BIL
    into a portfolio return (see :func:`simulate_cell_portfolio`) rather
    than this function assuming any particular slot weight.
    """
    cost_rate = cost_bps_per_side / 10_000.0
    dates = open_.index
    n = len(dates)
    open_to_open = open_.pct_change()

    equity_return = pd.Series(0.0, index=dates)
    active = pd.Series(False, index=dates)
    trades: list[TradeRecord] = []

    held = False
    entry_signal_idx = entry_fill_idx = None
    days_held = 0
    for t in range(n - 1):
        if held:
            days_held += 1
            if bool(exit_signal.iloc[t]) or days_held >= max_hold_days:
                exit_fill_idx = t + 1
                window = slice(entry_fill_idx + 1, exit_fill_idx + 1)
                active.iloc[window] = True
                equity_return.iloc[window] = equity_return.iloc[window] + open_to_open.iloc[window]
                equity_return.iloc[entry_fill_idx] -= cost_rate
                equity_return.iloc[exit_fill_idx] -= cost_rate
                trade_return = (
                    open_.iloc[exit_fill_idx] / open_.iloc[entry_fill_idx] - 1.0
                ) - 2.0 * cost_rate
                trades.append(
                    TradeRecord(
                        symbol=symbol,
                        cell_id=cell,
                        entry_signal_date=dates[entry_signal_idx].date().isoformat(),
                        entry_fill_date=dates[entry_fill_idx].date().isoformat(),
                        exit_signal_date=dates[t].date().isoformat(),
                        exit_fill_date=dates[exit_fill_idx].date().isoformat(),
                        net_return=float(trade_return),
                    )
                )
                held = False
        elif bool(entry_signal.iloc[t]):
            entry_signal_idx = t
            entry_fill_idx = t + 1
            held = True
            days_held = 0

    if held:
        # Open position at the end of the available sample: force-close it
        # at the last available open for return-series honesty (it must not
        # silently vanish from the series), but flag it so callers can
        # exclude it from realized-trade hit-rate/profit-factor accounting
        # -- its outcome was never actually observed under this rule.
        exit_fill_idx = n - 1
        if exit_fill_idx > entry_fill_idx:
            window = slice(entry_fill_idx + 1, exit_fill_idx + 1)
            active.iloc[window] = True
            equity_return.iloc[window] = equity_return.iloc[window] + open_to_open.iloc[window]
        equity_return.iloc[entry_fill_idx] -= cost_rate
        equity_return.iloc[exit_fill_idx] -= cost_rate
        trade_return = (
            open_.iloc[exit_fill_idx] / open_.iloc[entry_fill_idx] - 1.0
        ) - 2.0 * cost_rate
        trades.append(
            TradeRecord(
                symbol=symbol,
                cell_id=cell,
                entry_signal_date=dates[entry_signal_idx].date().isoformat(),
                entry_fill_date=dates[entry_fill_idx].date().isoformat(),
                exit_signal_date=dates[-1].date().isoformat(),
                exit_fill_date=dates[exit_fill_idx].date().isoformat(),
                net_return=float(trade_return),
                forced_close_at_sample_end=True,
            )
        )

    return equity_return.fillna(0.0), active, trades


def combine_slots(
    equity_by_symbol: Mapping[str, pd.Series],
    active_by_symbol: Mapping[str, pd.Series],
    bil_open_to_open: pd.Series,
    n_slots: float,
) -> pd.Series:
    """Pure combination arithmetic, factored out of
    :func:`simulate_cell_portfolio` so it can be unit-tested with tiny
    hand-built Series (no OHLC data, no SMA200 warmup): each symbol owns a
    fixed ``1/n_slots`` slot, earning its own equity return while
    ``active`` and BIL's return otherwise (module docstring's timing
    section -- the two legs never overlap and never leave a gap by
    construction of ``active``).
    """
    index = bil_open_to_open.index
    equity_total = pd.Series(0.0, index=index)
    active_count = pd.Series(0.0, index=index)
    for symbol in equity_by_symbol:
        equity_total = equity_total + equity_by_symbol[symbol]
        active_count = active_count + active_by_symbol[symbol].astype(float)
    bil_weight = 1.0 - (active_count / n_slots)
    return (equity_total / n_slots) + bil_weight * bil_open_to_open


def simulate_cell_portfolio(
    cell: str,
    bars: Mapping[str, pd.DataFrame],
    bil_frame: pd.DataFrame,
    params: Mapping[str, Any],
    cost_bps_per_side: float,
) -> tuple[pd.Series, list[TradeRecord]]:
    """Combine every symbol's independent state machine into one cell-level
    daily portfolio return series (fixed 1/N slot per symbol, see module
    docstring), plus the pooled list of completed trades across symbols.

    ``bars``/``bil_frame`` must already share one common ``DatetimeIndex``
    (see :func:`load_common_bars`); this function does not itself align
    across symbols.
    """
    symbols = list(bars)
    index = bil_frame.index
    bil_open_to_open = bil_frame["open"].pct_change().reindex(index).fillna(0.0)

    equity_by_symbol: dict[str, pd.Series] = {}
    active_by_symbol: dict[str, pd.Series] = {}
    trades: list[TradeRecord] = []
    for symbol in symbols:
        equity_return, active, symbol_trades = simulate_symbol(
            symbol, cell, bars[symbol], params, cost_bps_per_side
        )
        equity_by_symbol[symbol] = equity_return
        active_by_symbol[symbol] = active
        trades.extend(symbol_trades)

    portfolio_return = combine_slots(
        equity_by_symbol, active_by_symbol, bil_open_to_open, float(len(symbols))
    )
    portfolio_return.name = cell
    return portfolio_return, trades


@dataclass(frozen=True)
class QuarterSelection(ResearchDataModel):
    quarter_start: str
    quarter_end: str
    selected_cell: str
    trailing_daily_sharpe: float | None


def _quarter_bounds(index: pd.DatetimeIndex) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    starts = pd.date_range(index.min().normalize(), index.max().normalize(), freq="QS", tz=index.tz)
    bounds: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] - pd.Timedelta(days=1) if i + 1 < len(starts) else index.max()
        bounds.append((start, end))
    return bounds


def select_cells_by_quarter(
    cell_returns: Mapping[str, pd.Series],
    *,
    warmup_complete_date: pd.Timestamp,
    lookback_months: int = LOOKBACK_MONTHS,
) -> list[QuarterSelection]:
    """Walk-forward grid selection: at each calendar quarter, pick whichever
    cell had the best trailing daily Sharpe (mean/std of daily returns,
    unannualized -- monotonically equivalent to the annualized figure for
    ranking purposes, so annualizing would not change any selection) over
    the preceding ``lookback_months``. A quarter is only eligible once its
    full lookback window starts on or after ``warmup_complete_date`` --
    plan section 1's "训练/选参窗口为紧邻的前 24 个月" requires that window
    to be genuine cell performance, not SMA200-warmup NaN/zero padding.

    Deterministic tie-break: iteration order of ``cell_returns`` (its keys
    should be the fixed ``PARAMETER_SPACE`` order), first strict max wins.
    """
    any_series = next(iter(cell_returns.values()))
    index = any_series.index
    selections: list[QuarterSelection] = []
    for start, end in _quarter_bounds(index):
        lookback_start = start - pd.DateOffset(months=lookback_months)
        if lookback_start < warmup_complete_date:
            continue
        best_cell: str | None = None
        best_score = -math.inf
        for cell, returns in cell_returns.items():
            window = returns.loc[(returns.index >= lookback_start) & (returns.index < start)]
            if len(window) < 2:
                score = -math.inf
            else:
                std = float(window.std(ddof=1))
                score = float(window.mean() / std) if std > 0.0 else -math.inf
            if score > best_score:
                best_score = score
                best_cell = cell
        selections.append(
            QuarterSelection(
                quarter_start=start.date().isoformat(),
                quarter_end=end.date().isoformat(),
                selected_cell=best_cell or next(iter(cell_returns)),
                trailing_daily_sharpe=(best_score if math.isfinite(best_score) else None),
            )
        )
    return selections


def materialize_composite(
    cell_returns: Mapping[str, pd.Series],
    cell_trades: Mapping[str, Sequence[TradeRecord]],
    selection_log: Sequence[QuarterSelection],
) -> tuple[pd.Series, list[TradeRecord]]:
    """Apply a precomputed ``selection_log`` (see :func:`select_cells_by_quarter`)
    to any cell-keyed return/trade mapping -- used to build both the base-cost
    and stress-cost composites from the *same* selection decisions, since
    which cell "wins" a quarter must be decided once, on base-cost trailing
    performance, not re-decided per cost assumption.
    """
    parts: list[pd.Series] = []
    trades: list[TradeRecord] = []
    for selection in selection_log:
        start = pd.Timestamp(selection.quarter_start, tz="UTC")
        end = pd.Timestamp(selection.quarter_end, tz="UTC")
        returns = cell_returns[selection.selected_cell]
        window = returns.loc[(returns.index >= start) & (returns.index <= end)]
        parts.append(window)
        for trade in cell_trades[selection.selected_cell]:
            exit_ts = pd.Timestamp(trade.exit_fill_date, tz="UTC")
            if start <= exit_ts <= end and not trade.forced_close_at_sample_end:
                trades.append(trade)
    composite = pd.concat(parts).sort_index() if parts else pd.Series(dtype=float)
    return composite, trades


def load_common_bars(raw_frame: pd.DataFrame, symbols: Sequence[str]) -> dict[str, pd.DataFrame]:
    """Pivot a long ``open_composer.adapters.data.sip_parquet.load_sip_bars``
    -shaped frame (columns ``symbol, timestamp, open, high, low, close, ...``)
    into one OHLC frame per symbol, all reindexed onto the shared
    intersection of trading dates present for every requested symbol -- so
    every entry in the returned dict (including a cash/BIL "symbol" if
    passed in ``symbols``) can be zipped together index-for-index without
    any one symbol's own holiday/listing gap producing a misaligned row.
    """
    per_symbol: dict[str, pd.DataFrame] = {}
    common_index: pd.DatetimeIndex | None = None
    for symbol in symbols:
        rows = raw_frame.loc[raw_frame["symbol"] == symbol].sort_values("timestamp")
        indexed = rows.set_index(pd.DatetimeIndex(rows["timestamp"]))[
            ["open", "high", "low", "close"]
        ]
        per_symbol[symbol] = indexed
        common_index = (
            indexed.index if common_index is None else common_index.intersection(indexed.index)
        )
    if common_index is None or common_index.empty:
        raise ValueError("no common trading dates across the requested symbols")
    return {symbol: frame.reindex(common_index) for symbol, frame in per_symbol.items()}


def compute_warmup_complete_date(bars: Mapping[str, pd.DataFrame]) -> pd.Timestamp:
    """The earliest date by which every symbol in ``bars`` has a valid
    SMA200 -- the latest of each symbol's own SMA200 first-valid date, since
    the trend filter needs all of them simultaneously.
    """
    latest: pd.Timestamp | None = None
    for symbol, frame in bars.items():
        sma200 = frame["close"].rolling(SMA_TREND_DAYS, min_periods=SMA_TREND_DAYS).mean()
        first_valid = sma200.first_valid_index()
        if first_valid is None:
            raise ValueError(f"{symbol}: insufficient history to warm up SMA{SMA_TREND_DAYS}")
        if latest is None or first_valid > latest:
            latest = first_valid
    assert latest is not None  # bars is non-empty by construction of every caller
    return latest
