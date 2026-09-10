"""Step 13-P A3: Reversal Trend hourly-bar strategy mechanism.

docs/plan-step-13p-reversal-trend-pine-factor-and-strategy-2026-09-09.zh.md
section 2 (A3). Turns ``compute_reversal_trend`` signal columns on 1h bars
into a portfolio of discrete long trades under a preregistered 18-cell grid
(holding period x exit rule x signal set), then into the daily return
streams ``open_composer.research.regime.gates.evaluate_recent_high_return_candidate``
needs.

**Two-phase design** (why: the exit-rule simulation is entirely per-symbol,
but the position-count cap is portfolio-wide, so mixing them into one pass
would require re-deriving per-symbol state on every portfolio-level
decision):

1. ``generate_symbol_candidates`` walks *one symbol's* bars once and produces
   every candidate trade it would take with *unlimited* capacity (a symbol
   never holds two positions at once, so this is a simple non-overlapping
   walk). Costs are deliberately not applied here -- costs never change
   which bar a trade enters/exits on, only its net P&L (see
   :func:`net_return`), so one candidate list serves both the base and
   stress cost variants.
2. ``admit_by_capacity`` merges every symbol's candidates, sorts by
   (entry_time, -adx_at_entry), and greedily admits up to
   ``max_positions`` concurrently-open trades -- ties at the same entry bar
   resolve in ADX-descending order, which is exactly "超额信号按 ADX 高者
   优先" (plan section 2): the priority rule only bites when multiple
   symbols signal on the same bar and slots are scarce, never as a
   preemption of an already-open position.

**Fill convention**: every discretionary decision (entry, time-stop exit,
reverse-signal exit) is decided at a bar's close and filled at the *next*
bar's open (plan: "信号 bar 收盘确认 -> 下一个 1h bar 开盘成交"). The ATR
trailing stop is the one exception -- a protective stop is checked
intrabar and fills within the same bar it is breached (at the stop level,
or at that bar's open if price gapped through it), which is the standard
convention for stop orders in bar-level backtests and is *not* the same
kind of decision as the discretionary entry/exit rules.

``holding_bars`` is a cap shared by all three exit rules, not a separate
"do-nothing-until-a-rule-fires" mode: "time_stop" only ever exits at the
cap, "time_stop_or_reverse" and "atr_trailing_2x" can exit earlier but never
later. This is what makes the 3 (holding) x 3 (exit rule) x 2 (signal set)
grid a genuine cross product of independently meaningful cells rather than
having the exit-rule dimension override holding_bars for two of three rules.

**Daily P&L reconstruction (disclosed simplification)**: a portfolio built
from hourly-triggered trades is marked to market once per *calendar day*
(the gate contract only ever needs daily returns), using each symbol's own
last hourly close of the day as the interior-day checkpoint and the trade's
real fill price at the entry/exit boundary days (:func:`trade_daily_returns`)
-- real daily closes, not a synthetic equal split of the trade's total
return, so a trade's realized path (and its contribution to drawdown) is not
smoothed away. Position weight is 10% of portfolio NAV *at the start of its
entry day* (fixed in dollar terms then, drifting afterward) -- proper
weight-drift buy-and-hold, matching the pattern the Step 13 Track M ledger
hygiene fix (commit 30879b4, this same effort) established as correct versus
a daily-rebalance-to-constant-weight bug.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

ExitRule = Literal["time_stop", "time_stop_or_reverse", "atr_trailing_2x"]
SignalSet = Literal["bull_only", "bull_and_recl"]

HOLDING_BARS_GRID: tuple[int, ...] = (6, 13, 26)
EXIT_RULES: tuple[ExitRule, ...] = ("time_stop", "time_stop_or_reverse", "atr_trailing_2x")
SIGNAL_SETS: tuple[SignalSet, ...] = ("bull_only", "bull_and_recl")

#: Plan section 2 (A3): "成本 5 bp/边（个股）、2 bp/边（ETF）；压力 2.5x".
ETF_SYMBOLS: frozenset[str] = frozenset({"SPY", "QQQ", "IWM", "TQQQ"})
STOCK_COST_BPS_PER_SIDE = 5.0
ETF_COST_BPS_PER_SIDE = 2.0
STRESS_COST_MULTIPLIER = 2.5

MAX_POSITIONS = 10
POSITION_WEIGHT = 0.10

REQUIRED_SYMBOL_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "atr",
    "adx",
    "f_bull",
    "f_bear",
    "f_recl",
)


def cost_bps_for_symbol(symbol: str, *, stress: bool = False) -> float:
    """Per-side cost in bps for ``symbol`` (plan section 2)."""
    base = ETF_COST_BPS_PER_SIDE if symbol in ETF_SYMBOLS else STOCK_COST_BPS_PER_SIDE
    return base * STRESS_COST_MULTIPLIER if stress else base


def net_return(entry_price: float, exit_price: float, cost_bps_per_side: float) -> float:
    """Round-trip net return: pay ``cost_bps_per_side`` on entry (buy higher)
    and again on exit (sell lower), multiplicatively."""
    cost = cost_bps_per_side / 10_000.0
    effective_entry = entry_price * (1.0 + cost)
    effective_exit = exit_price * (1.0 - cost)
    return effective_exit / effective_entry - 1.0


@dataclass(frozen=True)
class TradeCandidate:
    """One symbol's hypothetical trade under unlimited portfolio capacity."""

    symbol: str
    entry_bar: int
    entry_time: pd.Timestamp
    entry_price: float
    exit_bar: int
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: Literal["time_stop", "reverse_signal", "atr_trailing_stop"]
    adx_at_entry: float


def generate_symbol_candidates(
    symbol: str,
    bars: pd.DataFrame,
    *,
    holding_bars: int,
    exit_rule: ExitRule,
    signal_set: SignalSet,
    entry_mask: np.ndarray | None = None,
    signal_bar_indices: np.ndarray | None = None,
) -> list[TradeCandidate]:
    """Every candidate trade ``symbol`` would take, ignoring portfolio
    capacity (a symbol is never pyramided: a signal that fires while a
    hypothetical position is still open is skipped for *this* symbol).

    ``bars`` must be one symbol's rows from ``compute_reversal_trend``'s
    output, sorted ascending by timestamp, columns
    :data:`REQUIRED_SYMBOL_COLUMNS`.

    ``entry_mask``: optional boolean array aligned to ``bars`` (e.g. the
    SPY-200-day trend gate) ANDed onto the real signal columns; ignored when
    ``signal_bar_indices`` is given.

    ``signal_bar_indices``: when given, used verbatim as the decision bars
    instead of reading ``f_bull``/``f_recl`` -- this is the placebo's entry
    point (see :func:`random_signal_bar_indices`), so the *same* exit-rule
    simulation and cost model apply to both the real and placebo strategies.
    """
    missing = [c for c in REQUIRED_SYMBOL_COLUMNS if c not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing required columns: {missing}")
    n = len(bars)
    if n == 0:
        return []

    open_ = bars["open"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    atr = bars["atr"].to_numpy(dtype=float)
    adx = bars["adx"].to_numpy(dtype=float)
    timestamps = bars["timestamp"].to_numpy()
    reverse_signal = bars["f_bear"].to_numpy(dtype=bool)

    if signal_bar_indices is not None:
        candidate_bars = np.asarray(sorted(signal_bar_indices))
    else:
        if signal_set == "bull_only":
            signal = bars["f_bull"].to_numpy(dtype=bool)
        else:
            signal = (bars["f_bull"] | bars["f_recl"]).to_numpy(dtype=bool)
        if entry_mask is not None:
            signal = signal & np.asarray(entry_mask, dtype=bool)
        candidate_bars = np.flatnonzero(signal)

    candidates: list[TradeCandidate] = []
    blocked_until = -1
    for signal_bar in candidate_bars:
        signal_bar = int(signal_bar)
        if signal_bar <= blocked_until:
            continue
        entry_bar = signal_bar + 1
        if entry_bar >= n:
            continue
        entry_price = float(open_[entry_bar])
        entry_adx = float(adx[signal_bar])
        time_stop_bar = min(entry_bar + holding_bars - 1, n - 1)

        exit_bar: int | None = None
        exit_price: float | None = None
        exit_reason: str | None = None

        if exit_rule == "atr_trailing_2x":
            highest_close = close[entry_bar]
            stop_level = highest_close - 2.0 * atr[entry_bar]
            for b in range(entry_bar, time_stop_bar + 1):
                if b > entry_bar:
                    highest_close = max(highest_close, close[b])
                    stop_level = max(stop_level, highest_close - 2.0 * atr[b])
                if not np.isnan(stop_level) and low[b] <= stop_level:
                    exit_bar = b
                    exit_price = stop_level if open_[b] > stop_level else open_[b]
                    exit_reason = "atr_trailing_stop"
                    break
        elif exit_rule == "time_stop_or_reverse":
            for b in range(entry_bar, time_stop_bar + 1):
                if reverse_signal[b]:
                    exit_decision_bar = b
                    exit_reason = "reverse_signal"
                    break
            else:
                exit_decision_bar = time_stop_bar
                exit_reason = "time_stop"
            exit_fill_bar = exit_decision_bar + 1
            if exit_fill_bar < n:
                exit_bar = exit_fill_bar
                exit_price = float(open_[exit_fill_bar])
        else:  # "time_stop"
            exit_fill_bar = time_stop_bar + 1
            if exit_fill_bar < n:
                exit_bar = exit_fill_bar
                exit_price = float(open_[exit_fill_bar])
                exit_reason = "time_stop"

        if exit_rule == "atr_trailing_2x" and exit_bar is None:
            # Time cap reached with no breach: falls back to a time-based
            # exit at the next bar's open, same as the "time_stop" rule.
            exit_fill_bar = time_stop_bar + 1
            if exit_fill_bar < n:
                exit_bar = exit_fill_bar
                exit_price = float(open_[exit_fill_bar])
                exit_reason = "time_stop"

        if exit_bar is None:
            # No next bar available to fill the exit (data's right edge):
            # drop the incomplete trade rather than fabricate a close-out
            # price outside the fill convention.
            continue

        candidates.append(
            TradeCandidate(
                symbol=symbol,
                entry_bar=entry_bar,
                entry_time=pd.Timestamp(timestamps[entry_bar]),
                entry_price=entry_price,
                exit_bar=exit_bar,
                exit_time=pd.Timestamp(timestamps[exit_bar]),
                exit_price=float(exit_price),
                exit_reason=exit_reason,  # type: ignore[arg-type]
                adx_at_entry=entry_adx,
            )
        )
        blocked_until = exit_bar

    return candidates


def random_signal_bar_indices(n_bars: int, count: int, *, rng: np.random.Generator) -> np.ndarray:
    """``count`` distinct random bar indices in ``[0, n_bars - 2]`` (never the
    last bar -- it has no next bar to fill an entry at). The placebo's "same
    symbol, same count, random dates" (plan section 2): draws from every
    eligible bar uniformly, independent of where the real signals fell.
    """
    eligible = max(n_bars - 1, 0)
    count = min(count, eligible)
    if count <= 0:
        return np.array([], dtype=np.int64)
    return rng.choice(eligible, size=count, replace=False)


def admit_by_capacity(
    candidates: list[TradeCandidate], *, max_positions: int = MAX_POSITIONS
) -> list[TradeCandidate]:
    """Greedily admit candidates in (entry_time, -adx_at_entry) order, up to
    ``max_positions`` concurrently open. A position exiting at bar time T
    frees its slot for a new entry at that same T (both are "fills at this
    bar's open" events)."""
    ordered = sorted(candidates, key=lambda c: (c.entry_time, -c.adx_at_entry))
    admitted: list[TradeCandidate] = []
    open_exit_times: list[pd.Timestamp] = []
    for candidate in ordered:
        open_exit_times = [t for t in open_exit_times if t > candidate.entry_time]
        if len(open_exit_times) < max_positions:
            admitted.append(candidate)
            open_exit_times.append(candidate.exit_time)
    return admitted


@dataclass(frozen=True)
class Trade:
    """An admitted candidate plus its realized net return under one cost
    variant."""

    candidate: TradeCandidate
    cost_bps_per_side: float
    net_return: float

    @property
    def symbol(self) -> str:
        return self.candidate.symbol

    @property
    def entry_time(self) -> pd.Timestamp:
        return self.candidate.entry_time

    @property
    def exit_time(self) -> pd.Timestamp:
        return self.candidate.exit_time


def trades_with_cost(candidates: list[TradeCandidate], *, stress: bool) -> list[Trade]:
    """Apply :func:`cost_bps_for_symbol` to each admitted candidate. Costs
    never change *which* trades were admitted (see module docstring), so the
    same admitted candidate list is reused for both cost variants."""
    trades = []
    for candidate in candidates:
        cost_bps = cost_bps_for_symbol(candidate.symbol, stress=stress)
        r = net_return(candidate.entry_price, candidate.exit_price, cost_bps)
        trades.append(Trade(candidate=candidate, cost_bps_per_side=cost_bps, net_return=r))
    return trades


def daily_last_close(bars: pd.DataFrame) -> pd.Series:
    """One symbol's last hourly close per calendar date (America/New_York),
    used as interior-day mark-to-market checkpoints in
    :func:`trade_daily_returns`."""
    local_date = bars["timestamp"].dt.tz_convert("America/New_York").dt.normalize()
    return bars.groupby(local_date)["close"].last()


def trade_daily_returns(daily_close: pd.Series, trade: Trade) -> pd.Series:
    """Daily returns (index: date, value: pct return) spanning one trade's
    holding period. Entry day starts at the real entry fill price and ends
    at that day's close; interior days are close-to-close; the exit day
    starts at the previous close and ends at the real exit fill price. A
    same-day entry+exit collapses to one row equal to the trade's whole
    ``net_return``.
    """
    entry_day = trade.entry_time.tz_convert("America/New_York").normalize()
    exit_day = trade.exit_time.tz_convert("America/New_York").normalize()
    span = daily_close.loc[entry_day:exit_day]
    if span.empty:
        return pd.Series({entry_day: trade.net_return})
    marks = span.copy()
    marks.iloc[-1] = trade.candidate.exit_price
    prev_marks = marks.shift(1)
    prev_marks.iloc[0] = trade.candidate.entry_price
    daily = marks / prev_marks - 1.0
    # Rescale so the compounded path exactly equals the (cost-adjusted)
    # trade net_return -- the checkpoints above are gross-of-cost, cost is a
    # single round-trip drag that belongs on the trade as a whole, not
    # double-applied per day. The adjustment factor must be distributed as
    # an n-th root, not applied to every day directly: multiplying each of
    # n days by the same `scale` compounds to `scale**n`, not `scale` --
    # applying `scale ** (1/n)` per day instead makes the *product* of
    # adjustments equal `scale`, which is what actually preserves the
    # trade's total net_return regardless of how many days it spans (this
    # was a real bug here, caught by
    # test_trade_daily_returns_multi_day_compounds_exactly_to_net_return
    # asserting the *actual* net_return, not a value copied from a first,
    # wrong run of this function).
    gross_total = float((1.0 + daily).prod() - 1.0)
    if not np.isclose(1.0 + gross_total, 0.0):
        scale = (1.0 + trade.net_return) / (1.0 + gross_total)
        per_day_scale = scale ** (1.0 / len(daily))
        daily = (1.0 + daily) * per_day_scale - 1.0
    return daily


@dataclass(frozen=True)
class PortfolioResult:
    trades: list[Trade]
    daily_returns: pd.Series  # full calendar-day index, 0.0 on flat days
    invested_day: pd.Series  # bool, aligned to daily_returns.index


def build_portfolio(
    trades: list[Trade],
    daily_close_by_symbol: dict[str, pd.Series],
    calendar: pd.DatetimeIndex,
    *,
    position_weight: float = POSITION_WEIGHT,
) -> PortfolioResult:
    """Sequential day-by-day NAV walk (module docstring: "Daily P&L
    reconstruction"). ``calendar`` is the full trading-day index the output
    must cover (e.g. SPY's daily bars in the evaluation window) so flat days
    with zero open positions are represented as real 0.0 return rows, not
    silently absent.
    """
    per_trade_daily: dict[int, pd.Series] = {}
    starts: dict[pd.Timestamp, list[int]] = defaultdict(list)
    ends: dict[pd.Timestamp, list[int]] = defaultdict(list)
    open_span: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}

    for i, trade in enumerate(trades):
        daily_close = daily_close_by_symbol.get(trade.symbol)
        if daily_close is None or daily_close.empty:
            continue
        series = trade_daily_returns(daily_close, trade)
        per_trade_daily[i] = series
        entry_day = series.index.min()
        exit_day = series.index.max()
        starts[entry_day].append(i)
        ends[exit_day].append(i)
        open_span[i] = (entry_day, exit_day)

    nav = 1.0
    nav_by_day: dict[pd.Timestamp, float] = {}
    invested_by_day: dict[pd.Timestamp, bool] = {}
    position_value: dict[int, float] = {}

    for day in calendar:
        day_start_nav = nav
        for trade_id in starts.get(day, []):
            position_value[trade_id] = position_weight * day_start_nav
        day_pnl = 0.0
        any_open = False
        for trade_id in list(position_value.keys()):
            series = per_trade_daily[trade_id]
            if day not in series.index:
                continue
            any_open = True
            r = float(series.loc[day])
            new_value = position_value[trade_id] * (1.0 + r)
            day_pnl += new_value - position_value[trade_id]
            position_value[trade_id] = new_value
        nav = day_start_nav + day_pnl
        for trade_id in ends.get(day, []):
            position_value.pop(trade_id, None)
        nav_by_day[day] = nav
        invested_by_day[day] = any_open

    nav_series = pd.Series(nav_by_day).sort_index()
    daily_returns = nav_series.pct_change()
    daily_returns.iloc[0] = nav_series.iloc[0] - 1.0  # first day's return vs the NAV=1.0 base
    invested = (
        pd.Series(invested_by_day).sort_index().reindex(daily_returns.index, fill_value=False)
    )
    return PortfolioResult(trades=trades, daily_returns=daily_returns, invested_day=invested)


def weekly_holding_period_net_returns(result: PortfolioResult) -> list[float]:
    """Compounded return per ISO week, restricted to weeks with at least one
    invested day (gate contract's ``hit_rate_weekly`` note: "counted only
    over weeks the candidate was invested")."""
    weekly_period = pd.PeriodIndex(result.daily_returns.index, freq="W")
    compounded = (1.0 + result.daily_returns).groupby(weekly_period).prod() - 1.0
    invested_weekly = result.invested_day.groupby(weekly_period).any()
    return compounded.loc[invested_weekly].tolist()


def rebalances_with_change_per_year(trades: list[Trade]) -> dict[int, int]:
    """{calendar_year: count of distinct ISO weeks with >=1 entry or exit}
    -- the activity-floor input (plan/gate contract note: "trend gate
    switching the whole book to BIL counts as a change"; this strategy has
    no trend-gate-driven book-wide switch, so entries/exits are the only
    change events)."""
    changed_weeks: set[tuple[int, int]] = set()
    for trade in trades:
        for ts in (trade.entry_time, trade.exit_time):
            iso = ts.isocalendar()
            changed_weeks.add((int(iso.year), int(iso.week)))
    counts: dict[int, int] = defaultdict(int)
    for year, _week in changed_weeks:
        counts[year] += 1
    return dict(counts)
