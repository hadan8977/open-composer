"""T-20261001-01 dash-for-cash settlement window on SPY, for
`scripts/screen_batch.py --batch t20261001_01_dash_for_cash --iteration
t20261001_01_dash_for_cash_settlement`.

Preregistration: `reports/research/iterations/t20261001_01_dash_for_cash_settlement/
hypotheses.md` ("预注册全文"). Mechanism: Etula et al. (RFS 2020) and Nathan,
Suominen, Tasa (2026): month-end cash needs force institutions to sell by the
settlement deadline b; prices rebound once the new month's cash comes back.

Definitions (trading-day calendar of SPY):
  tau   last trading day of a calendar month (only for months that are
        complete in the index: the last month of the data is skipped unless
        the index reaches the last weekday of that month -- a calendar fact,
        never a price).
  b     tau - 4 for tau < 2024-05-28 (T+2), tau - 3 from 2024-05-28 (T+1).
        Era-aligned (`era_aligned=True`) only; FIX4 controls use tau - 4 always.
  exit  tau + 3 (third trading day of the next month).
Signal at the close of b: long SPY (conditional version: only if the SPY return
close(b-6) -> close(b) is < 0). Signal at the close of tau + 3: flat. The lane
fills at the next open.

Imports `h20260928_20_recent_opt` (E0 factory) and `h20260928_05_batch2`
(`month_end_signal_dates`) unedited for the E0_REF reproduction candidate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as b2  # noqa: E402
import h20260928_20_recent_opt as opt  # noqa: E402

REFORM_DATE = pd.Timestamp("2024-05-28")
PRE_WINDOW_SESSIONS = 6
EXIT_OFFSET = 3  # exit signal at tau + 3

_SCHEDULE_CACHE: dict[tuple, list[dict]] = {}


def _month_is_complete(index: pd.DatetimeIndex, month_last_day: pd.Timestamp) -> bool:
    """True when `index` reaches the last weekday of `month_last_day`'s month.
    Only the final month of the data can fail this."""
    cal_end = month_last_day + pd.offsets.MonthEnd(0)
    last_weekday = cal_end
    while last_weekday.weekday() >= 5:
        last_weekday -= pd.Timedelta(days=1)
    return index[-1] >= last_weekday


def holding_sessions(tau: pd.Timestamp, era_aligned: bool) -> int:
    """Trading days held per window: tau+3 minus b."""
    return 6 if (era_aligned and tau >= REFORM_DATE) else 7


def month_schedule(index: pd.DatetimeIndex, era_aligned: bool) -> list[dict]:
    """One dict per complete month: tau, b, exit (None when the index ends
    before tau+3), L (sessions held). Uses the trading-day calendar only."""
    key = (len(index), index[0], index[-1], era_aligned)
    cached = _SCHEDULE_CACHE.get(key)
    if cached is not None:
        return cached
    out: list[dict] = []
    ser = pd.Series(np.arange(len(index)), index=index)
    for _, grp in ser.groupby([index.year, index.month]):
        tau_pos = int(grp.iloc[-1])
        tau = index[tau_pos]
        if not _month_is_complete(index, tau):
            continue
        shift = 3 if (era_aligned and tau >= REFORM_DATE) else 4
        b_pos = tau_pos - shift
        if b_pos < 0:
            continue
        exit_pos = tau_pos + EXIT_OFFSET
        out.append(
            {
                "tau": tau,
                "b": index[b_pos],
                "b_pos": b_pos,
                "exit": index[exit_pos] if exit_pos < len(index) else None,
                "L": holding_sessions(tau, era_aligned),
            }
        )
    if len(_SCHEDULE_CACHE) > 8:
        _SCHEDULE_CACHE.clear()
    _SCHEDULE_CACHE[key] = out
    return out


def pre_window_return(close: pd.DataFrame, asof: pd.Timestamp, symbol: str = "SPY") -> float | None:
    """SPY return close(asof - 6 sessions) -> close(asof); uses closes up to asof."""
    hist = close.loc[:asof, symbol].dropna()
    if len(hist) <= PRE_WINDOW_SESSIONS or hist.index[-1] != asof:
        return None
    p0 = float(hist.iloc[-1 - PRE_WINDOW_SESSIONS])
    p1 = float(hist.iloc[-1])
    if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
        return None
    return p1 / p0 - 1.0


def make_dfc(era_aligned: bool, conditional: bool):
    """Return `(signal_dates_fn, fn)` for one dash-for-cash variant."""

    def signal_dates_fn(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        dates: list[pd.Timestamp] = []
        for m in month_schedule(index, era_aligned):
            dates.append(m["b"])
            if m["exit"] is not None:
                dates.append(m["exit"])
        return sorted(set(dates))

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if "SPY" not in close.columns:
            return {}
        entries = {m["b"] for m in month_schedule(close.index, era_aligned)}
        if asof not in entries:
            return {}
        if conditional:
            r = pre_window_return(close, asof)
            if r is None or not (r < 0.0):
                return {}
        return {"SPY": 1.0}

    return signal_dates_fn, fn


def _spec(id_: str, name: str, era_aligned: bool, conditional: bool) -> dict[str, object]:
    dates_fn, fn = make_dfc(era_aligned, conditional)
    return {
        "id": id_,
        "name": name,
        "source_card": "etula_2020_dash_for_cash_month_end_reversal",
        "universe": ("SPY",),
        "freq": "D",
        "signal_dates_fn": dates_fn,
        "fn": fn,
    }


SPECS: list[dict[str, object]] = [
    _spec("DFC_U", "Dash-for-cash SPY: b..tau+3, era-aligned b, unconditional", True, False),
    _spec(
        "DFC_C", "Dash-for-cash SPY: b..tau+3, era-aligned b, only if pre-window < 0", True, True
    ),
    _spec("DFC_U_FIX4", "Dash-for-cash SPY control: b = tau-4 always, unconditional", False, False),
    _spec("DFC_C_FIX4", "Dash-for-cash SPY control: b = tau-4 always, pre-window < 0", False, True),
    {
        "id": "E0_REF",
        "name": "E0 reproduction: 4th-Friday-to-month-end SPY return < 0 -> long next month",
        "source_card": "graziani2024_ssrn_eom_reversal_primary_tsrtv",
        "universe": ("SPY",),
        "freq": "D",
        "signal_dates_fn": b2.month_end_signal_dates,
        "fn": opt.make_eom_reversal_fn(),
    },
]
