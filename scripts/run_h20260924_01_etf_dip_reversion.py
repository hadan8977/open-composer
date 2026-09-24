"""H-20260924-01: short-term index-ETF dip reversion (IBS, Connors/turtle RSI(2)).

Dossier: reports/research/iterations/h20260924_01_etf_dip_reversion/
Brief:   reports/research/hypotheses/H-20260924-01-etf-dip-reversion.md

Nothing about the measurement protocol is re-invented here. The four windows,
the metric definitions (``Metrics``/``window_metrics``) and the 10/20 bp cost
levels come from ``scripts/run_h20260918_05_recent_menu.py``; the G1-G5 gate
thresholds come from ``scripts/run_h20260922_02_s3_voltarget.py`` (as already
copied verbatim into ``scripts/run_giants_sweep.py``); Wilder's RSI is
identical to ``scripts/run_giants_sweep.py::_wilder_rsi`` /
``scripts/run_h20260922_04_rsi_branch.py::wilder_rsi``. This file adds the six
dip-reversion rules (event-driven entry/exit, not scheduled rebalancing, so
the giants-sweep ``Panel``/``Interpreter`` machinery does not fit) plus the
T0/T1/T2 timing conventions, the trade-level research-admission rule, the two
placebo families, and the 2016-2026 persistence table.

Two independent stages:

* Stage A (daily bars only, ``data/sip/daily/*/*.parquet``): T0 and T2 for
  all 24 candidates, the split/dividend sanity check, and the 2016-2026
  persistence table. Runs standalone with ``--stage a``.
* Stage B (QQQ/SPY minute bars, ``data/sip-hist/minute`` through 2022 and
  ``data/sip/minute`` 2023+ per-month layout): T1, the primary timing
  convention, for all 24 candidates. Runs standalone with ``--stage b`` once
  Stage A has produced ``stage_a.json`` in the iteration directory. This
  script never guesses whether a ``scripts/run_capped.sh`` slot is free --
  that check is the caller's responsibility (see decision-record.md).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402

ITER_ID = "h20260924_01_etf_dip_reversion"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
DAILY_GLOB = "data/sip/daily/*/*.parquet"
MINUTE_GLOB_HIST = "data/sip-hist/minute"
MINUTE_GLOB_CURRENT = "data/sip/minute"

COST_BPS_PRIMARY = base.COST_BPS_PRIMARY  # 10.0
COST_BPS_STRESS = base.COST_BPS_STRESS  # 20.0
WINDOWS = base.WINDOWS

# gate thresholds -- copied verbatim from run_h20260922_02_s3_voltarget.py via
# scripts/run_giants_sweep.py; not re-derived here.
GATE_G1_CAGR = 0.50
GATE_G1_MAXDD = -0.35
GATE_G1ALT_SHARPE = 2.0
GATE_G1ALT_CAGR = 0.30
GATE_G2_SHARPE = 1.0
GATE_G3_PLACEBO = 0.10

RANDOM_ENTRY_SEEDS = 60
CALENDAR_SHIFT_SEEDS = 20
RESEARCH_ADMISSION_T_STAT = 2.0
RESEARCH_ADMISSION_T1_OVER_T0 = 0.60

SIGNAL_UNDERLYINGS = ("QQQ", "SPY")
EXECUTION_INSTRUMENT = {
    ("QQQ", "1x"): "QQQ",
    ("QQQ", "3x"): "TQQQ",
    ("SPY", "1x"): "SPY",
    ("SPY", "3x"): "UPRO",
}
PERSISTENCE_SYMBOLS = ("QQQ", "SPY", "IWM", "DIA")

Timing = Literal["T0", "T1", "T2"]

# --------------------------------------------------------------- primitives


def ibs(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """IBS_t = (close_t - low_t) / (high_t - low_t), 0.5 if high_t == low_t."""
    rng = high - low
    out = (close - low) / rng
    return out.where(rng != 0, 0.5)


def ema(close: pd.Series, window: int) -> pd.Series:
    """Standard EMA (alpha = 2/(window+1)), matching Pine's ``ta.ema``."""
    return close.ewm(span=window, adjust=False, min_periods=window).mean()


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def _wilder_rsi_state(close: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    return avg_gain, avg_loss


def _wilder_rsi_from_state(avg_gain: pd.Series, avg_loss: pd.Series) -> pd.Series:
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    return rsi.where(avg_loss.notna() & (avg_loss > 0), 100.0).where(avg_gain.notna())


def wilder_rsi(close: pd.Series, window: int) -> pd.Series:
    """Identical to run_giants_sweep._wilder_rsi / run_h20260922_04_rsi_branch.wilder_rsi."""
    avg_gain, avg_loss = _wilder_rsi_state(close, window)
    return _wilder_rsi_from_state(avg_gain, avg_loss)


# ------------------------------------------------------- T1 one-step-ahead


def _ema_one_step_proxy(ema_official: pd.Series, proxy_close: pd.Series, window: int) -> pd.Series:
    """EMA value a decision at the proxy would show, from the prior OFFICIAL state.

    ``ema_official`` is the plain recursive EMA on official closes. Day D+1's
    own official EMA state is always advanced from day D's OFFICIAL close (once
    known), never from day D's proxy -- this one extra step is a throwaway,
    single-day side computation used only for day D's own T1 decision.
    """
    alpha = 2.0 / (window + 1.0)
    return alpha * proxy_close + (1.0 - alpha) * ema_official.shift(1)


def _sma_one_step_proxy(
    close_official: pd.Series, proxy_close: pd.Series, window: int
) -> pd.Series:
    prior_sum = close_official.shift(1).rolling(window - 1, min_periods=window - 1).sum()
    return (prior_sum + proxy_close) / window


def _wilder_one_step_proxy(
    close_official: pd.Series,
    proxy_close: pd.Series,
    avg_gain_official: pd.Series,
    avg_loss_official: pd.Series,
    window: int,
) -> pd.Series:
    delta_proxy = proxy_close - close_official.shift(1)
    gain_proxy = delta_proxy.clip(lower=0.0)
    loss_proxy = (-delta_proxy).clip(lower=0.0)
    alpha = 1.0 / window
    avg_gain_proxy = avg_gain_official.shift(1) * (1.0 - alpha) + gain_proxy * alpha
    avg_loss_proxy = avg_loss_official.shift(1) * (1.0 - alpha) + loss_proxy * alpha
    return _wilder_rsi_from_state(avg_gain_proxy, avg_loss_proxy)


# ------------------------------------------------------------- bundle build


@dataclass
class Bundle:
    """Everything a rule function needs, already resolved for one timing convention.

    ``close``/``high``/``low``/``ibs``/``ema*``/``sma*``/``rsi2`` are "today's"
    values: the official same-bar value for T0/T2, or the T1 proxy (prior
    official state plus today's 15:50 ET proxy bar) for T1. The lagged ``h1..
    h3``/``l1..l3``/``r1..r3`` fields are ALWAYS the official prior sessions'
    values, for every timing convention, because by the time "today" is being
    decided, the prior sessions are already fully known regardless of how
    "today" itself is being read.
    """

    close: pd.Series
    high: pd.Series
    low: pd.Series
    ibs: pd.Series
    ema220: pd.Series
    ema200: pd.Series
    ema5: pd.Series
    sma200: pd.Series
    sma5: pd.Series
    rsi2: pd.Series
    h1: pd.Series
    h2: pd.Series
    h3: pd.Series
    l1: pd.Series
    l2: pd.Series
    l3: pd.Series
    r1: pd.Series
    r2: pd.Series
    r3: pd.Series
    index: pd.DatetimeIndex


def build_bundle(
    official: pd.DataFrame,
    timing: Timing,
    proxy: pd.DataFrame | None = None,
) -> Bundle:
    """``official``/``proxy`` have columns open/high/low/close, one symbol.

    ``proxy`` (required for timing="T1") has columns high/low/close for every
    session date that has a computable 15:50 ET proxy; sessions missing from
    ``proxy`` get NaN today-values (T1 has no decision that day), matching a
    fail-closed posture for missing minute data rather than silently
    substituting the official value.
    """
    close_o, high_o, low_o = official["close"], official["high"], official["low"]
    ema220_o = ema(close_o, 220)
    ema200_o = ema(close_o, 200)
    ema5_o = ema(close_o, 5)
    sma200_o = sma(close_o, 200)
    sma5_o = sma(close_o, 5)
    gain_o, loss_o = _wilder_rsi_state(close_o, 2)
    rsi2_o = _wilder_rsi_from_state(gain_o, loss_o)

    if timing in ("T0", "T2"):
        close_t, high_t, low_t = close_o, high_o, low_o
        ema220_t, ema200_t, ema5_t = ema220_o, ema200_o, ema5_o
        sma200_t, sma5_t = sma200_o, sma5_o
        rsi2_t = rsi2_o
    elif timing == "T1":
        if proxy is None:
            raise ValueError("T1 timing requires a proxy frame")
        proxy = proxy.reindex(official.index)
        close_t, high_t, low_t = proxy["close"], proxy["high"], proxy["low"]
        ema220_t = _ema_one_step_proxy(ema220_o, close_t, 220)
        ema200_t = _ema_one_step_proxy(ema200_o, close_t, 200)
        ema5_t = _ema_one_step_proxy(ema5_o, close_t, 5)
        sma200_t = _sma_one_step_proxy(close_o, close_t, 200)
        sma5_t = _sma_one_step_proxy(close_o, close_t, 5)
        rsi2_t = _wilder_one_step_proxy(close_o, close_t, gain_o, loss_o, 2)
    else:  # pragma: no cover - guarded by Timing literal
        raise ValueError(f"unknown timing {timing}")

    ibs_t = ibs(high_t, low_t, close_t)

    return Bundle(
        close=close_t,
        high=high_t,
        low=low_t,
        ibs=ibs_t,
        ema220=ema220_t,
        ema200=ema200_t,
        ema5=ema5_t,
        sma200=sma200_t,
        sma5=sma5_t,
        rsi2=rsi2_t,
        h1=high_o.shift(1),
        h2=high_o.shift(2),
        h3=high_o.shift(3),
        l1=low_o.shift(1),
        l2=low_o.shift(2),
        l3=low_o.shift(3),
        r1=rsi2_o.shift(1),
        r2=rsi2_o.shift(2),
        r3=rsi2_o.shift(3),
        index=official.index,
    )


_BUNDLE_SERIES_FIELDS = tuple(name for name in Bundle.__dataclass_fields__ if name != "index")


def reindex_bundle(bundle: Bundle, index: pd.DatetimeIndex) -> Bundle:
    """Reindex every series field of ``bundle`` onto ``index``.

    Used to align a signal underlying's indicator bundle (built once from its
    own full history, so lookback windows never see a truncated series) onto
    the trading calendar actually shared with a given execution instrument.
    """
    fields = {name: getattr(bundle, name).reindex(index) for name in _BUNDLE_SERIES_FIELDS}
    return Bundle(index=index, **fields)


# --------------------------------------------------------------------- rules


@dataclass
class Rule:
    rule_id: str
    entry: Callable[[Bundle], pd.Series]
    exit: Callable[[Bundle], pd.Series]
    eligible: Callable[[Bundle], pd.Series]
    max_hold: int | None
    fixed_hold: int | None = None


def _d1_entry(underlying: str) -> Callable[[Bundle], pd.Series]:
    threshold = 0.09 if underlying == "QQQ" else 0.11
    trend_window = 220 if underlying == "QQQ" else 200

    def fn(b: Bundle) -> pd.Series:
        trend = b.ema220 if trend_window == 220 else b.ema200
        return (b.ibs <= threshold) & (b.close > trend)

    return fn


def _d1_exit(underlying: str) -> Callable[[Bundle], pd.Series]:
    threshold = 0.985 if underlying == "QQQ" else 0.995

    def fn(b: Bundle) -> pd.Series:
        return b.ibs >= threshold

    return fn


def _d1_eligible(underlying: str) -> Callable[[Bundle], pd.Series]:
    trend_window = 220 if underlying == "QQQ" else 200

    def fn(b: Bundle) -> pd.Series:
        trend = b.ema220 if trend_window == 220 else b.ema200
        return (b.close > trend).fillna(False)

    return fn


def _d2_entry(b: Bundle) -> pd.Series:
    return b.ibs < 0.20


def _d2_exit(b: Bundle) -> pd.Series:  # pragma: no cover - fixed_hold bypasses this
    return pd.Series(False, index=b.index)


def _d2_eligible(b: Bundle) -> pd.Series:
    return pd.Series(True, index=b.index)


def _d3_entry(b: Bundle) -> pd.Series:
    falling = (b.rsi2 < b.r1) & (b.r1 < b.r2) & (b.r2 < b.r3)
    return (b.close > b.ema200) & falling & (b.r3 < 60) & (b.rsi2 < 10)


def _d3_exit(b: Bundle) -> pd.Series:
    prior = b.rsi2.shift(1)
    return (b.rsi2 > 70) & (prior <= 70)


def _d3_eligible(b: Bundle) -> pd.Series:
    return (b.close > b.ema200).fillna(False)


def _d4_entry(b: Bundle) -> pd.Series:
    return (b.close > b.sma200) & (b.rsi2 <= 5)


def _d4_exit(b: Bundle) -> pd.Series:
    return b.close > b.sma5


def _d4_eligible(b: Bundle) -> pd.Series:
    return (b.close > b.sma200).fillna(False)


def _d5_entry(b: Bundle) -> pd.Series:
    lower_highs = (b.high < b.h1) & (b.h1 < b.h2) & (b.h2 < b.h3)
    lower_lows = (b.low < b.l1) & (b.l1 < b.l2) & (b.l2 < b.l3)
    return (b.close > b.ema200) & (b.close < b.ema5) & lower_highs & lower_lows


def _d5_exit(b: Bundle) -> pd.Series:
    prior = b.close.shift(1)
    ema5_prior = b.ema5.shift(1)
    return (b.close > b.ema5) & (prior <= ema5_prior)


def _d5_eligible(b: Bundle) -> pd.Series:
    return (b.close > b.ema200).fillna(False)


def _d6_entry(b: Bundle) -> pd.Series:
    return _d4_entry(b) & (b.ibs < 0.20)


RULES: dict[str, dict[str, Rule]] = {}
for _u in SIGNAL_UNDERLYINGS:
    RULES.setdefault("D1", {})[_u] = Rule(
        "D1", _d1_entry(_u), _d1_exit(_u), _d1_eligible(_u), max_hold=14
    )
    RULES.setdefault("D2", {})[_u] = Rule(
        "D2", _d2_entry, _d2_exit, _d2_eligible, max_hold=None, fixed_hold=1
    )
    RULES.setdefault("D3", {})[_u] = Rule("D3", _d3_entry, _d3_exit, _d3_eligible, max_hold=None)
    RULES.setdefault("D4", {})[_u] = Rule("D4", _d4_entry, _d4_exit, _d4_eligible, max_hold=None)
    RULES.setdefault("D5", {})[_u] = Rule("D5", _d5_entry, _d5_exit, _d5_eligible, max_hold=None)
    RULES.setdefault("D6", {})[_u] = Rule("D6", _d6_entry, _d4_exit, _d4_eligible, max_hold=None)
RULE_IDS = ("D1", "D2", "D3", "D4", "D5", "D6")


# ---------------------------------------------------------------- simulation


@dataclass
class Trade:
    entry_idx: int
    exit_idx: int
    entry_active_start: int
    exit_active_end: int
    entry_price: float
    exit_price: float
    hold_sessions: int
    gross_return: float
    net_return: float


def _leg_series(open_: pd.Series, close: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    prev_close = close.shift(1)
    leg_open = (open_ / prev_close - 1.0).to_numpy(dtype=float)
    leg_close = (close / open_ - 1.0).to_numpy(dtype=float)
    return leg_open, leg_close


def _decision_fill(
    timing: Timing, i: int, n: int, close: np.ndarray, open_: np.ndarray
) -> tuple[int, float] | None:
    """Fill price for a decision made using day ``i``'s bar, or None if unfillable.

    T0/T1: filled at the execution instrument's own official close of session
    ``i`` (the MOC convention for T1; the unexecutable same-close convention
    for T0). T2: filled at session ``i + 1``'s official open. This same
    function serves both entries and exits: the fill mechanics ("decide using
    day i, fill per the timing convention") are identical either way.
    """
    if timing in ("T0", "T1"):
        if not np.isfinite(close[i]):
            return None
        return i, float(close[i])
    if i + 1 >= n or not np.isfinite(open_[i + 1]):
        return None
    return i + 1, float(open_[i + 1])


def simulate_rule(
    rule: Rule,
    signal_bundle: Bundle,
    exec_open: pd.Series,
    exec_close: pd.Series,
    timing: Timing,
    cost_bps: float,
    *,
    entry_override: np.ndarray | None = None,
    exit_override: np.ndarray | None = None,
) -> tuple[pd.Series, pd.Series, list[Trade]]:
    """Event-driven single-instrument on/off simulation.

    Returns ``(daily_net_return, daily_turnover, trades)``.

    ``signal_bundle`` supplies the entry/exit booleans (from the SIGNAL
    underlying's own OHLC); ``exec_open``/``exec_close`` are the EXECUTION
    instrument's own daily bars (identical to the signal underlying for the
    1x case, TQQQ/UPRO for the 3x case). T0/T1 fill at the execution
    instrument's own official close of the decision session; T2 fills at its
    next-session official open. Cost is one ``cost_bps`` charge per side.
    """
    index = signal_bundle.index
    n = len(index)
    entry_signal = (
        entry_override
        if entry_override is not None
        else rule.entry(signal_bundle).fillna(False).to_numpy()
    )
    exit_signal = (
        exit_override
        if exit_override is not None
        else rule.exit(signal_bundle).fillna(False).to_numpy()
    )
    close_arr = exec_close.to_numpy(dtype=float)
    open_arr = exec_open.to_numpy(dtype=float)
    leg_open, leg_close = _leg_series(exec_open, exec_close)

    rets = np.zeros(n)
    turns = np.zeros(n)
    trades: list[Trade] = []

    i = 0
    while i < n:
        if not entry_signal[i]:
            i += 1
            continue
        fill = _decision_fill(timing, i, n, close_arr, open_arr)
        if fill is None:
            i += 1
            continue
        _, entry_price = fill
        # Exposure always starts the session AFTER the decision session,
        # whether the fill itself lands on that same session's close
        # (T0/T1) or that session's open (T2, which is index i+1 too).
        active_start = i + 1

        # scan forward for the exit
        j = i
        hold = 0
        exit_idx = None
        if rule.fixed_hold is not None:
            exit_idx = min(i + rule.fixed_hold, n - 1)
        else:
            j = i + 1
            while j < n:
                hold = j - i
                if exit_signal[j]:
                    exit_idx = j
                    break
                if rule.max_hold is not None and hold >= rule.max_hold:
                    exit_idx = j
                    break
                j += 1
            if exit_idx is None:
                i += 1
                continue  # position never closes within the data window; drop it

        exit_fill = _decision_fill(timing, exit_idx, n, close_arr, open_arr)
        if exit_fill is None:
            i = exit_idx + 1
            continue
        _, exit_price = exit_fill
        if timing in ("T0", "T1"):
            active_end = exit_idx
        else:
            active_end = exit_idx + 1

        if active_end < active_start or active_end >= n:
            i = exit_idx + 1
            continue

        gross_return = exit_price / entry_price - 1.0
        net_return = gross_return - 2.0 * cost_bps / 10_000.0
        trades.append(
            Trade(
                entry_idx=i,
                exit_idx=exit_idx,
                entry_active_start=active_start,
                exit_active_end=active_end,
                entry_price=entry_price,
                exit_price=exit_price,
                hold_sessions=exit_idx - i,
                gross_return=gross_return,
                net_return=net_return,
            )
        )

        # -- daily return accounting --
        entry_cost = cost_bps / 10_000.0
        exit_cost = cost_bps / 10_000.0
        for k in range(active_start, active_end + 1):
            both_legs = True
            if timing == "T2" and k == active_start:
                both_legs = False  # bought at this day's open: close-leg only
            if timing == "T2" and k == active_end and active_end != active_start:
                # sold at this day's open: open-leg (the overnight gap) only
                rets[k] += leg_open[k]
                turns[k] += 1.0 if k == active_start else 0.0
                continue
            if both_legs:
                rets[k] += leg_open[k] + leg_close[k]
            else:
                rets[k] += leg_close[k]
            turns[k] += 1.0 if k in (active_start, active_end) else 0.0
        rets[active_start] -= entry_cost
        rets[active_end] -= exit_cost
        i = exit_idx + 1

    return pd.Series(rets, index=index), pd.Series(turns, index=index), trades


# ------------------------------------------------------------------ placebos


def _shift_bool_array(arr: np.ndarray, shift: int) -> np.ndarray:
    """Shift a boolean array forward by ``shift`` sessions, zero-filling the
    boundary (``shifted[k] = arr[k - shift]`` for ``k >= shift``), matching
    ``pd.Series.shift(shift).fillna(False)`` without ever putting the series
    through an intermediate NaN-holding dtype."""
    out = np.zeros_like(arr, dtype=bool)
    if shift == 0:
        out[:] = arr
    elif shift > 0:
        if shift < arr.size:
            out[shift:] = arr[:-shift]
    else:
        if -shift < arr.size:
            out[:shift] = arr[-shift:]
    return out


def random_entry_placebo(
    rule: Rule,
    signal_bundle: Bundle,
    exec_open: pd.Series,
    exec_close: pd.Series,
    timing: Timing,
    cost_bps: float,
    real_trades: list[Trade],
    seed: int,
) -> tuple[pd.Series, pd.Series, list[Trade]]:
    """Same trade count and holding-period multiset as ``real_trades``.

    Entry days are drawn (without replacement) from the pool of sessions
    that satisfy the rule's own trend filter (``rule.eligible``), matching
    the brief's "sample only among days that satisfy the rule's trend filter
    where it has one." Holding periods are a random permutation of the real
    trades' own holding periods, so the multiset (not just the count) is
    matched. Placebo trades are pushed forward to the next eligible day when
    a draw would overlap a previously placed trade, keeping the synthetic
    book a coherent single on/off position like the real one. Returns
    ``(daily_net_return, daily_turnover, trades)``; turnover is currently
    always zero (no gate reads it) but kept for interface symmetry with
    ``simulate_rule``.
    """
    index = signal_bundle.index
    n = len(index)
    if not real_trades:
        return pd.Series(0.0, index=index), pd.Series(0.0, index=index), []
    rng = np.random.default_rng(seed)
    eligible = rule.eligible(signal_bundle).fillna(False).to_numpy()
    eligible_idx = np.flatnonzero(eligible)
    if eligible_idx.size == 0:
        return pd.Series(0.0, index=index), pd.Series(0.0, index=index), []

    holds = rng.permutation([t.hold_sessions if t.hold_sessions > 0 else 1 for t in real_trades])
    close_arr = exec_close.to_numpy(dtype=float)
    open_arr = exec_open.to_numpy(dtype=float)
    leg_open, leg_close = _leg_series(exec_open, exec_close)
    rets = np.zeros(n)
    trades: list[Trade] = []
    cursor = 0
    pool = eligible_idx[eligible_idx < n - 1]
    for hold in holds:
        candidates = pool[pool >= cursor]
        if candidates.size == 0:
            break
        i = int(rng.choice(candidates))
        exit_idx = min(i + int(hold), n - 1)
        fill = _decision_fill(timing, i, n, close_arr, open_arr)
        exit_fill = _decision_fill(timing, exit_idx, n, close_arr, open_arr)
        if fill is None or exit_fill is None or exit_idx <= i:
            cursor = i + 1
            continue
        _, entry_price = fill
        _, exit_price = exit_fill
        active_start = i + 1
        active_end = exit_idx if timing in ("T0", "T1") else exit_idx + 1
        if active_end < active_start or active_end >= n:
            cursor = exit_idx + 1
            continue
        gross_return = exit_price / entry_price - 1.0
        net_return = gross_return - 2.0 * cost_bps / 10_000.0
        trades.append(
            Trade(
                i,
                exit_idx,
                active_start,
                active_end,
                entry_price,
                exit_price,
                exit_idx - i,
                gross_return,
                net_return,
            )
        )
        entry_cost = cost_bps / 10_000.0
        exit_cost = cost_bps / 10_000.0
        for k in range(active_start, active_end + 1):
            if timing == "T2" and k == active_start and active_end != active_start:
                rets[k] += leg_close[k]
            elif timing == "T2" and k == active_end and active_end != active_start:
                rets[k] += leg_open[k]
            else:
                rets[k] += leg_open[k] + leg_close[k]
        rets[active_start] -= entry_cost
        rets[active_end] -= exit_cost
        cursor = exit_idx + 1
    return pd.Series(rets, index=index), pd.Series(0.0, index=index), trades


def calendar_shift_placebo(
    rule: Rule,
    signal_bundle: Bundle,
    exec_open: pd.Series,
    exec_close: pd.Series,
    timing: Timing,
    cost_bps: float,
    seed: int,
) -> tuple[pd.Series, pd.Series, list[Trade]]:
    """Shift the boolean entry/exit signal by a random 1-20 session offset.

    Identical convention to the shift placebo in
    scripts/run_h20260918_05_recent_menu.py / scripts/run_giants_sweep.py:
    the signal itself is shifted, not the underlying indicator windows.
    """
    rng = np.random.default_rng(seed)
    shift = int(rng.integers(1, 21))
    # A plain ``pd.Series.shift`` on a boolean series introduces real NaN at
    # the boundary, upcasting to object dtype; filling that back down to
    # bool via ``.fillna()`` is exactly the "downcast object dtype on
    # fillna" behavior pandas is deprecating. Shifting the boolean numpy
    # array directly (shift is always >=1 here) sidesteps the dtype
    # gymnastics entirely instead of chasing the warning through fillna.
    entry = _shift_bool_array(rule.entry(signal_bundle).fillna(False).to_numpy(dtype=bool), shift)
    exit_ = _shift_bool_array(rule.exit(signal_bundle).fillna(False).to_numpy(dtype=bool), shift)
    return simulate_rule(
        rule,
        signal_bundle,
        exec_open,
        exec_close,
        timing,
        cost_bps,
        entry_override=entry,
        exit_override=exit_,
    )


# --------------------------------------------------------------------- gates


@dataclass
class GateResult:
    G1: bool
    G1_alt: bool
    G2: bool
    G3: bool
    G4: bool
    G5: bool
    all_gates: bool
    placebo_beat_frac_worst: float


def evaluate_gates(
    wm_primary: dict[str, base.Metrics],
    wm_stress: dict[str, base.Metrics],
    placebo_beat_fracs: dict[str, float],
) -> GateResult:
    g1 = bool(
        wm_primary["anchor"].cagr >= GATE_G1_CAGR and wm_primary["anchor"].max_dd >= GATE_G1_MAXDD
    )
    g1alt = bool(
        wm_primary["anchor"].sharpe >= GATE_G1ALT_SHARPE
        and wm_primary["anchor"].cagr >= GATE_G1ALT_CAGR
    )
    g2 = bool(wm_primary["holdout"].sharpe >= GATE_G2_SHARPE and wm_primary["holdout"].cagr > 0)
    worst = (
        float(np.nanmax(list(placebo_beat_fracs.values()))) if placebo_beat_fracs else float("nan")
    )
    g3 = bool(np.isfinite(worst) and worst <= GATE_G3_PLACEBO)
    g4 = bool(
        (wm_stress["anchor"].cagr >= GATE_G1_CAGR and wm_stress["anchor"].max_dd >= GATE_G1_MAXDD)
        or (
            wm_stress["anchor"].sharpe >= GATE_G1ALT_SHARPE
            and wm_stress["anchor"].cagr >= GATE_G1ALT_CAGR
        )
    )
    g5 = True  # long-only spot US ETFs on the existing Alpaca daily cron
    return GateResult(g1, g1alt, g2, g3, g4, g5, bool((g1 or g1alt) and g2 and g3 and g4), worst)


@dataclass
class ResearchAdmission:
    mean_trade_select: float
    mean_trade_holdout: float
    mean_return_positive: bool
    t_stat: float
    t_stat_pass: bool
    placebo_p95: float
    beats_placebo_p95: bool
    t1_over_t0_fraction: float
    t1_over_t0_pass: bool
    admitted: bool


def _trades_in_window(trades: list[Trade], index: pd.DatetimeIndex, window: str) -> list[Trade]:
    a, b = WINDOWS[window]
    out = []
    for t in trades:
        d = index[t.entry_idx]
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            out.append(t)
    return out


def _trade_t_stat(returns: list[float]) -> float:
    arr = np.asarray(returns, dtype=float)
    if arr.size < 2:
        return float("nan")
    sd = arr.std(ddof=1)
    if not sd or not np.isfinite(sd):
        return float("nan")
    return float(arr.mean() / sd * math.sqrt(arr.size))


def evaluate_research_admission(
    real_trades: list[Trade],
    placebo_trades_by_seed: list[list[Trade]],
    t0_trades: list[Trade],
    index: pd.DatetimeIndex,
) -> ResearchAdmission:
    select_trades = _trades_in_window(real_trades, index, "select")
    holdout_trades = _trades_in_window(real_trades, index, "holdout")
    combined = select_trades + holdout_trades
    mean_select = (
        float(np.mean([t.net_return for t in select_trades])) if select_trades else float("nan")
    )
    mean_holdout = (
        float(np.mean([t.net_return for t in holdout_trades])) if holdout_trades else float("nan")
    )
    mean_positive = bool(
        np.isfinite(mean_select)
        and np.isfinite(mean_holdout)
        and mean_select > 0
        and mean_holdout > 0
    )
    t_stat = _trade_t_stat([t.net_return for t in combined])
    t_pass = bool(np.isfinite(t_stat) and t_stat >= RESEARCH_ADMISSION_T_STAT)

    placebo_means = []
    for seed_trades in placebo_trades_by_seed:
        combo = _trades_in_window(seed_trades, index, "select") + _trades_in_window(
            seed_trades, index, "holdout"
        )
        if combo:
            placebo_means.append(float(np.mean([t.net_return for t in combo])))
    p95 = float(np.percentile(placebo_means, 95)) if placebo_means else float("nan")
    real_mean_combined = (
        float(np.mean([t.net_return for t in combined])) if combined else float("nan")
    )
    beats_p95 = bool(
        np.isfinite(p95) and np.isfinite(real_mean_combined) and real_mean_combined >= p95
    )

    t0_combined = _trades_in_window(t0_trades, index, "select") + _trades_in_window(
        t0_trades, index, "holdout"
    )
    t0_gross_mean = (
        float(np.mean([t.gross_return for t in t0_combined])) if t0_combined else float("nan")
    )
    t1_gross_mean = float(np.mean([t.gross_return for t in combined])) if combined else float("nan")
    if np.isfinite(t0_gross_mean) and t0_gross_mean > 0:
        fraction = t1_gross_mean / t0_gross_mean
    else:
        fraction = float("nan")
    fraction_pass = bool(np.isfinite(fraction) and fraction >= RESEARCH_ADMISSION_T1_OVER_T0)

    admitted = bool(mean_positive and t_pass and beats_p95 and fraction_pass)
    return ResearchAdmission(
        mean_select,
        mean_holdout,
        mean_positive,
        t_stat,
        t_pass,
        p95,
        beats_p95,
        fraction,
        fraction_pass,
        admitted,
    )


def deflated_sharpe_ratio(
    best_sharpe: float,
    trial_sharpes: list[float],
    n_returns: int,
    skew: float,
    kurtosis: float,
) -> float:
    """Bailey & Lopez de Prado (2014) deflated Sharpe ratio of the best of N trials.

    SR0 (the expected maximum Sharpe under a null of zero skill, given the
    number of trials and the cross-sectional variance of the trials' own
    Sharpe ratios) uses the standard extreme-value approximation for the
    expected max of N iid standard normal draws; DSR is then the
    skew/kurtosis-adjusted probabilistic Sharpe ratio (PSR) of the best
    Sharpe against SR0. Returns NaN if fewer than 2 trials are available.
    """
    trials = np.asarray(trial_sharpes, dtype=float)
    trials = trials[np.isfinite(trials)]
    n_trials = trials.size
    if n_trials < 2 or n_returns < 2:
        return float("nan")
    sr_std = float(trials.std(ddof=1))
    if sr_std <= 0:
        return float("nan")
    euler_mascheroni = 0.5772156649015329
    # E[max of N iid N(0,1)] approximation (Bailey & Lopez de Prado 2014, eq. 8)
    expected_max = (1.0 - euler_mascheroni) * _norm_ppf(
        1.0 - 1.0 / n_trials
    ) + euler_mascheroni * _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    sr0 = sr_std * expected_max
    denom = math.sqrt(
        max(1e-12, 1.0 - skew * best_sharpe + (kurtosis - 1.0) / 4.0 * best_sharpe**2)
    )
    z = (best_sharpe - sr0) * math.sqrt(n_returns - 1) / denom
    return float(_norm_cdf(z))


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    # Acklam's rational approximation to the inverse normal CDF.
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    p_low, p_high = 0.02425, 1 - 0.02425
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        )
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


# ----------------------------------------------------------------- data I/O


def load_daily_panel(symbols: list[str]) -> dict[str, pd.DataFrame]:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='700MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, high, low, close, volume, trade_count
        FROM read_parquet('{DAILY_GLOB}')
        WHERE symbol IN ({in_list})
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    out: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        sub = frame.loc[frame["symbol"] == symbol].sort_values("d")
        if sub.empty:
            continue
        idx = pd.to_datetime(sub["d"])
        out[symbol] = pd.DataFrame(
            {
                "open": sub["open"].to_numpy(dtype=float),
                "high": sub["high"].to_numpy(dtype=float),
                "low": sub["low"].to_numpy(dtype=float),
                "close": sub["close"].to_numpy(dtype=float),
            },
            index=idx,
        )
    return out


def split_dividend_check(
    panels: dict[str, pd.DataFrame], threshold: float = 0.20
) -> list[dict[str, Any]]:
    """Flag overnight open/prior-close ratio jumps that look like unadjusted
    corporate actions rather than ordinary overnight moves.

    This is a heuristic sanity check, not a corporate-actions database: a
    flagged day means "look at this," not "this is definitely unadjusted."
    """
    flags: list[dict[str, Any]] = []
    for symbol, frame in panels.items():
        prev_close = frame["close"].shift(1)
        ratio = frame["open"] / prev_close - 1.0
        hits = ratio.loc[(ratio.abs() > threshold) & ratio.notna()]
        for d, value in hits.items():
            flags.append(
                {
                    "symbol": symbol,
                    "date": str(d.date()),
                    "overnight_open_vs_prev_close": float(value),
                }
            )
    return flags


def align_execution(
    signal_symbol: str, exec_symbol: str, panels: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    if exec_symbol == signal_symbol:
        return panels[signal_symbol]
    common = panels[signal_symbol].index.intersection(panels[exec_symbol].index)
    return panels[exec_symbol].loc[common]


def _skew_kurtosis(returns: pd.Series) -> tuple[float, float]:
    r = returns.dropna().to_numpy(dtype=float)
    if r.size < 3:
        return 0.0, 3.0
    sd = r.std(ddof=1)
    if not sd or not np.isfinite(sd):
        return 0.0, 3.0
    z = (r - r.mean()) / sd
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    return skew, kurt


def evaluate_candidate(
    rule: Rule,
    bundle: Bundle,
    exec_open: pd.Series,
    exec_close: pd.Series,
    timing: Timing,
    rf: pd.Series,
) -> dict[str, Any]:
    """T0 or T2 diagnostic pass for one candidate: metrics, gates, placebos."""
    rets, turns, trades = simulate_rule(
        rule, bundle, exec_open, exec_close, timing, COST_BPS_PRIMARY
    )
    rets_stress, turns_stress, _ = simulate_rule(
        rule, bundle, exec_open, exec_close, timing, COST_BPS_STRESS
    )
    wm = base.window_metrics(rets, rf.reindex(rets.index).fillna(0.0), turns)
    wm_stress = base.window_metrics(
        rets_stress, rf.reindex(rets_stress.index).fillna(0.0), turns_stress
    )

    placebo_beat: dict[str, float] = {}
    placebo_rows: list[dict[str, float]] = []
    real_select_sharpe = wm["select"].sharpe
    if trades:
        re_seeds = []
        for seed in range(RANDOM_ENTRY_SEEDS):
            p_rets, _, _ = random_entry_placebo(
                rule, bundle, exec_open, exec_close, timing, COST_BPS_PRIMARY, trades, seed
            )
            p_wm = base.window_metrics(
                p_rets, rf.reindex(p_rets.index).fillna(0.0), pd.Series(0.0, index=p_rets.index)
            )
            re_seeds.append(p_wm["select"].sharpe)
            placebo_rows.append(
                {"placebo": "random_entry", "seed": seed, "select_sharpe": p_wm["select"].sharpe}
            )
        finite = [s for s in re_seeds if np.isfinite(s)]
        placebo_beat["random_entry"] = (
            float(np.mean([s >= real_select_sharpe for s in finite]))
            if finite and np.isfinite(real_select_sharpe)
            else float("nan")
        )
    cs_seeds = []
    for seed in range(CALENDAR_SHIFT_SEEDS):
        p_rets, p_turns, _ = calendar_shift_placebo(
            rule, bundle, exec_open, exec_close, timing, COST_BPS_PRIMARY, seed
        )
        p_wm = base.window_metrics(p_rets, rf.reindex(p_rets.index).fillna(0.0), p_turns)
        cs_seeds.append(p_wm["select"].sharpe)
        placebo_rows.append(
            {"placebo": "calendar_shift", "seed": seed, "select_sharpe": p_wm["select"].sharpe}
        )
    finite = [s for s in cs_seeds if np.isfinite(s)]
    placebo_beat["calendar_shift"] = (
        float(np.mean([s >= real_select_sharpe for s in finite]))
        if finite and np.isfinite(real_select_sharpe)
        else float("nan")
    )

    gates = evaluate_gates(wm, wm_stress, placebo_beat)
    return {
        "rets": rets,
        "trades": trades,
        "wm": wm,
        "wm_stress": wm_stress,
        "gates": gates,
        "placebo_beat": placebo_beat,
        "placebo_rows": placebo_rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["a", "b", "all"], default="a")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    daily_symbols = sorted({"QQQ", "SPY", "TQQQ", "UPRO", "IWM", "DIA", "BIL"})
    panels = load_daily_panel(daily_symbols)
    missing = [s for s in daily_symbols if s not in panels]
    if missing:
        raise SystemExit(f"missing symbols in the SIP daily archive: {missing}")
    print(f"loaded daily panels for {sorted(panels)}", flush=True)

    flags = split_dividend_check(panels)
    (OUT_DIR / "split-dividend-check.json").write_text(
        json.dumps(flags, indent=2), encoding="utf-8"
    )
    print(f"split/dividend overnight-jump flags: {len(flags)}", flush=True)

    rf = panels["BIL"]["close"].pct_change(fill_method=None).fillna(0.0)

    rows: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    placebo_ledger: list[dict[str, Any]] = []
    for rule_id in RULE_IDS:
        for underlying in SIGNAL_UNDERLYINGS:
            rule = RULES[rule_id][underlying]
            bundle_full = build_bundle(panels[underlying], "T0")
            for execution in ("1x", "3x"):
                instrument = EXECUTION_INSTRUMENT[(underlying, execution)]
                exec_panel = align_execution(underlying, instrument, panels)
                bundle = reindex_bundle(bundle_full, exec_panel.index)
                cid = f"{rule_id.lower()}_{underlying.lower()}_{execution}"

                t0 = evaluate_candidate(
                    rule, bundle, exec_panel["open"], exec_panel["close"], "T0", rf
                )
                t2 = evaluate_candidate(
                    rule, bundle, exec_panel["open"], exec_panel["close"], "T2", rf
                )

                record: dict[str, Any] = {
                    "cell_id": cid,
                    "rule_id": rule_id,
                    "underlying": underlying,
                    "execution": execution,
                    "execution_instrument": instrument,
                }
                for tag, res in (("t0", t0), ("t2", t2)):
                    for w, m in res["wm"].items():
                        for k, v in asdict(m).items():
                            record[f"{tag}_{w}_{k}"] = v
                    for w, m in res["wm_stress"].items():
                        for k, v in asdict(m).items():
                            record[f"{tag}stress_{w}_{k}"] = v
                    gate = res["gates"]
                    for gname in ("G1", "G1_alt", "G2", "G3", "G4", "G5", "all_gates"):
                        record[f"{tag}_{gname}"] = getattr(gate, gname)
                    record[f"{tag}_placebo_beat_frac_worst"] = gate.placebo_beat_frac_worst
                    for kind, frac in res["placebo_beat"].items():
                        record[f"{tag}_placebo_beat_frac_{kind}"] = frac
                    record[f"{tag}_trade_count"] = len(res["trades"])
                    trade_returns_net = [t.net_return for t in res["trades"]]
                    record[f"{tag}_mean_net_return_per_trade"] = (
                        float(np.mean(trade_returns_net)) if trade_returns_net else float("nan")
                    )
                rows.append(record)

                for t in t0["trades"]:
                    ledger.append(
                        {
                            "cell_id": cid,
                            "timing": "T0",
                            "entry_date": str(exec_panel.index[t.entry_idx].date()),
                            "exit_date": str(exec_panel.index[t.exit_idx].date()),
                            "hold_sessions": t.hold_sessions,
                            "gross_return": t.gross_return,
                            "net_return": t.net_return,
                        }
                    )
                for t in t2["trades"]:
                    ledger.append(
                        {
                            "cell_id": cid,
                            "timing": "T2",
                            "entry_date": str(exec_panel.index[t.entry_idx].date()),
                            "exit_date": str(exec_panel.index[t.exit_idx].date()),
                            "hold_sessions": t.hold_sessions,
                            "gross_return": t.gross_return,
                            "net_return": t.net_return,
                        }
                    )
                for row in t0["placebo_rows"]:
                    placebo_ledger.append({"cell_id": cid, "timing": "T0", **row})
                print(
                    f"cell {cid}: T0 anchor Sharpe {t0['wm']['anchor'].sharpe:.2f} "
                    f"trades {len(t0['trades'])} all_gates={t0['gates'].all_gates}",
                    flush=True,
                )

    summary = pd.DataFrame(rows)
    summary.to_parquet(OUT_DIR / "stage_a_summary.parquet", index=False)
    pd.DataFrame(placebo_ledger).to_parquet(OUT_DIR / "stage_a_placebo.parquet", index=False)
    with (OUT_DIR / "trial-ledger.jsonl").open("w", encoding="utf-8") as fh:
        for row in ledger:
            fh.write(json.dumps(row) + "\n")

    # ------------------------------------------------- deflated Sharpe (T0)
    t0_anchor_sharpes = [
        r["t0_anchor_sharpe"] for r in rows if np.isfinite(r.get("t0_anchor_sharpe", float("nan")))
    ]
    dsr_t0 = float("nan")
    if t0_anchor_sharpes and rows:
        best_row_idx = int(np.nanargmax([r.get("t0_anchor_sharpe", float("-inf")) for r in rows]))
        best_cid = rows[best_row_idx]["cell_id"]
        # Recover that candidate's anchor-window T0 daily returns for skew/kurtosis.
        best_rule_id, best_underlying_lc, best_execution = best_cid.split("_")
        best_underlying = best_underlying_lc.upper()
        best_rule = RULES[best_rule_id.upper()][best_underlying]
        best_instrument = EXECUTION_INSTRUMENT[(best_underlying, best_execution)]
        best_exec_panel = align_execution(best_underlying, best_instrument, panels)
        best_bundle = reindex_bundle(
            build_bundle(panels[best_underlying], "T0"), best_exec_panel.index
        )
        best_rets, _, _ = simulate_rule(
            best_rule,
            best_bundle,
            best_exec_panel["open"],
            best_exec_panel["close"],
            "T0",
            COST_BPS_PRIMARY,
        )
        a, b = WINDOWS["anchor"]
        anchor_rets = best_rets.loc[(best_rets.index >= a) & (best_rets.index <= b)]
        skew, kurt = _skew_kurtosis(anchor_rets)
        dsr_t0 = deflated_sharpe_ratio(
            best_sharpe=float(rows[best_row_idx]["t0_anchor_sharpe"]),
            trial_sharpes=t0_anchor_sharpes,
            n_returns=int(anchor_rets.shape[0]),
            skew=skew,
            kurtosis=kurt,
        )
        print(
            f"T0 diagnostic deflated Sharpe of the best of {len(t0_anchor_sharpes)} trials "
            f"({best_cid}): {dsr_t0:.4f}",
            flush=True,
        )

    # ---------------------------------------------------------- persistence
    persistence_rows: list[dict[str, Any]] = []
    for rule_id in RULE_IDS:
        for symbol in PERSISTENCE_SYMBOLS:
            if symbol not in panels:
                continue
            # Rules are only parameterized for QQQ/SPY (D1's IBS thresholds
            # and EMA window differ by underlying); IWM/DIA context rows
            # reuse the SPY parameterization, disclosed here rather than
            # silently assumed.
            rule = RULES[rule_id].get(symbol, RULES[rule_id]["SPY"])
            frame = panels[symbol]
            bundle = build_bundle(frame, "T0")
            rets, _turns, trades = simulate_rule(
                rule, bundle, frame["open"], frame["close"], "T0", COST_BPS_PRIMARY
            )
            years = sorted({d.year for d in frame.index if 2016 <= d.year <= 2026})
            for year in years:
                mask = (rets.index >= f"{year}-01-01") & (rets.index <= f"{year}-12-31")
                year_ret = rets.loc[mask]
                if year_ret.empty:
                    continue
                n_trades_year = sum(1 for t in trades if frame.index[t.entry_idx].year == year)
                equity = float((1.0 + year_ret).prod() - 1.0)
                persistence_rows.append(
                    {
                        "rule_id": rule_id,
                        "symbol": symbol,
                        "parameterization_source": symbol if symbol in RULES[rule_id] else "SPY",
                        "year": year,
                        "return": equity,
                        "trade_count": n_trades_year,
                    }
                )
    pd.DataFrame(persistence_rows).to_parquet(
        OUT_DIR / "persistence-2016-2026.parquet", index=False
    )
    print(f"persistence table rows: {len(persistence_rows)}", flush=True)

    stage_a_state = {
        "iter_id": ITER_ID,
        "stage": "a",
        "daily_symbols": daily_symbols,
        "split_dividend_flags": len(flags),
        "cells": len(rows),
        "cells_all_gates_pass_t0": int(sum(1 for r in rows if r.get("t0_all_gates"))),
        "cells_all_gates_pass_t2": int(sum(1 for r in rows if r.get("t2_all_gates"))),
        "t0_deflated_sharpe_best_of_24": dsr_t0,
        "persistence_rows": len(persistence_rows),
    }
    (OUT_DIR / "stage_a.json").write_text(json.dumps(stage_a_state, indent=2), encoding="utf-8")
    print(json.dumps(stage_a_state, indent=2), flush=True)

    if args.stage in ("b", "all"):
        print("Stage B (T1, minute bars) is not implemented in this pass; ", file=sys.stderr)
        print(
            "see scripts/run_h20260924_01_etf_dip_reversion.py module docstring.", file=sys.stderr
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
