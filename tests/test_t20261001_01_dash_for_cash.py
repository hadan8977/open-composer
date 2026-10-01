"""Pure-function tests for `scripts/screen_batches/t20261001_01_dash_for_cash.py`
on a synthetic NYSE-like calendar (no market data)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import t20261001_01_dash_for_cash as dfc  # noqa: E402

HOLIDAYS = pd.to_datetime(
    [
        "2023-11-23",
        "2023-12-25",
        "2024-01-01",
        "2024-01-15",
        "2024-02-19",
        "2024-03-29",
        "2024-05-27",
        "2024-06-19",
        "2024-07-04",
    ]
)


def calendar(end: str = "2024-07-31") -> pd.DatetimeIndex:
    idx = pd.bdate_range("2023-11-01", end)
    return idx[~idx.isin(HOLIDAYS)]


def close_frame(index: pd.DatetimeIndex, values: np.ndarray | None = None) -> pd.DataFrame:
    vals = np.linspace(100.0, 120.0, len(index)) if values is None else values
    return pd.DataFrame({"SPY": vals}, index=index)


def by_tau(index: pd.DatetimeIndex, era_aligned: bool) -> dict[str, dict]:
    return {str(m["tau"].date()): m for m in dfc.month_schedule(index, era_aligned)}


def test_b_for_2024_04_and_2024_05_era_aligned():
    sched = by_tau(calendar(), True)
    assert sched["2024-04-30"]["b"] == pd.Timestamp("2024-04-24")  # tau-4
    assert sched["2024-05-31"]["b"] == pd.Timestamp("2024-05-28")  # tau-3
    assert sched["2024-04-30"]["L"] == 7
    assert sched["2024-05-31"]["L"] == 6


def test_fix4_keeps_tau_minus_4_after_reform():
    sched = by_tau(calendar(), False)
    assert sched["2024-05-31"]["b"] == pd.Timestamp("2024-05-24")
    assert sched["2024-05-31"]["L"] == 7


def test_exit_is_third_trading_day_of_next_month_with_holiday():
    sched = by_tau(calendar(), True)
    # Jan 1 2024 is a holiday: Jan 2, 3, 4 -> tau+3 = 2024-01-04
    assert sched["2023-12-29"]["exit"] == pd.Timestamp("2024-01-04")
    assert sched["2024-04-30"]["exit"] == pd.Timestamp("2024-05-03")


def test_conditional_holds_only_when_pre_window_negative():
    idx = calendar()
    sig, fn = dfc.make_dfc(True, True)
    b = pd.Timestamp("2024-04-24")
    pos = idx.get_loc(b)
    falling = np.linspace(120.0, 100.0, len(idx))
    rising = np.linspace(100.0, 120.0, len(idx))
    assert fn(close_frame(idx, falling), b) == {"SPY": 1.0}
    assert fn(close_frame(idx, rising), b) == {}
    # flat window: return exactly 0 is not < 0
    flat = rising.copy()
    flat[pos - 6 : pos + 1] = 110.0
    assert fn(close_frame(idx, flat), b) == {}
    # unconditional ignores the pre-window
    _, fn_u = dfc.make_dfc(True, False)
    assert fn_u(close_frame(idx, rising), b) == {"SPY": 1.0}
    assert b in sig(idx)


def test_exit_and_other_days_return_empty_weights():
    idx = calendar()
    _, fn = dfc.make_dfc(True, False)
    frame = close_frame(idx)
    assert fn(frame, pd.Timestamp("2024-05-03")) == {}  # tau+3 of April
    assert fn(frame, pd.Timestamp("2024-04-30")) == {}  # tau itself


def test_last_month_without_tau_plus_3_returns_only_b():
    idx = calendar("2024-06-04")  # May complete, but tau+3 = 2024-06-05 not in data
    sig, _ = dfc.make_dfc(True, False)
    dates = sig(idx)
    assert pd.Timestamp("2024-05-28") in dates
    assert pd.Timestamp("2024-06-05") not in dates
    assert dates[-1] == pd.Timestamp("2024-05-28")  # incomplete June adds nothing


def test_incomplete_final_month_is_skipped_and_no_lookahead():
    idx_full = calendar("2024-07-31")
    idx_short = calendar("2024-06-12")
    sig_full, _ = dfc.make_dfc(True, False)
    sig_short, _ = dfc.make_dfc(True, False)
    short = set(sig_short(idx_short))
    assert max(short) < pd.Timestamp("2024-06-12")
    # earlier months' dates are unchanged when later rows are appended
    assert short <= set(sig_full(idx_full))
