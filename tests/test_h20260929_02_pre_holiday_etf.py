"""Synthetic-data tests for `scripts/screen_batches/h20260929_02_pre_holiday_
etf.py`. No real market data is read (importing the module and constructing
`CANDIDATES` never touches duckdb or the local panel; only the calendar
helpers below are exercised on synthetic `pd.DatetimeIndex` values).

Covers: candidate ids/count match the preregistered manifest (18); holiday-
gap detection depends only on the calendar, not prices; entry/exit signal
dates land exactly `hold` sessions apart at the right offsets; the RAND
placebo is deterministic, price-independent, frequency-matched, and never
overlaps a real entry date; no look-ahead (mutating future prices never
changes an already-decided `asof`'s weight).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260929_02_pre_holiday_etf as batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _close_frame(index: pd.DatetimeIndex, prices: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(prices, index=index)


def _calendar_with_one_holiday() -> pd.DatetimeIndex:
    """A synthetic trading calendar: ordinary business days, but Thursday
    2024-01-11 is followed directly by Monday 2024-01-15 (a 4-day gap, not
    explained by the weekend-only 1-day gap a Thursday would normally have)
    -- i.e. Wed 2024-01-10 is a Wed with normal Thu follow, and Thu 2024-01-11
    is the pre-holiday day (Fri 2024-01-12 is the synthetic holiday)."""
    days = list(pd.bdate_range("2024-01-01", "2024-01-11"))  # Mon 01-01 .. Thu 01-11
    days += list(pd.bdate_range("2024-01-15", "2024-01-31"))  # skip Fri 01-12 (holiday)
    return pd.DatetimeIndex(sorted(set(days)))


# --------------------------------------------------------------------------
# CANDIDATES shape matches the preregistered manifest exactly
# --------------------------------------------------------------------------


def test_candidate_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260929_02_pre_holiday_etf"
        / "candidate-manifest.json"
    )
    if not manifest_path.exists():
        pytest.skip("T-20260929-02 manifest not written yet (round breakpoint)")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(c.id for c in batch.CANDIDATES)
    assert module_ids == manifest_ids
    assert len(module_ids) == 18


def test_candidates_are_screen_candidate_d_freq_single_symbol() -> None:
    for c in batch.CANDIDATES:
        assert isinstance(c, lane.ScreenCandidate)
        assert c.freq == "D"
        assert len(c.universe) == 1
        assert callable(c.weights_fn)
        assert callable(c.signal_dates_fn)


def test_primary_and_placebo_counts() -> None:
    primary = [c for c in batch.CANDIDATES if c.id.endswith(("_H1", "_H2"))]
    placebo = [c for c in batch.CANDIDATES if c.id.endswith("_RAND")]
    assert len(primary) == 12
    assert len(placebo) == 6


# --------------------------------------------------------------------------
# Holiday-gap detection: calendar only, not price-dependent
# --------------------------------------------------------------------------


def test_pre_holiday_positions_finds_the_synthetic_holiday() -> None:
    index = _calendar_with_one_holiday()
    positions = batch.pre_holiday_positions(index)
    flagged_days = {index[i] for i in positions}
    assert pd.Timestamp("2024-01-11") in flagged_days  # Thursday before the gap
    # ordinary Friday->Monday weekend transitions must NOT be flagged.
    assert pd.Timestamp("2024-01-05") not in flagged_days  # Friday, normal weekend


def test_entry_and_exit_dates_are_hold_sessions_apart() -> None:
    index = _calendar_with_one_holiday()
    entries = batch.entry_signal_dates(index)
    assert pd.Timestamp("2024-01-10") in entries  # Wed, day before the pre-holiday Thu
    exits_h1 = batch.exit_dates_from_entries(index, entries, 1)
    exits_h2 = batch.exit_dates_from_entries(index, entries, 2)
    entry = pd.Timestamp("2024-01-10")
    pos = list(index).index(entry)
    # hold=1: exit signal at position pos+1 (the pre-holiday day itself).
    assert index[pos + 1] in exits_h1
    assert index[pos + 1] == pd.Timestamp("2024-01-11")
    # hold=2: exit signal at position pos+2 (first day after the reopen).
    assert index[pos + 2] in exits_h2
    assert index[pos + 2] == pd.Timestamp("2024-01-15")


def test_weights_fn_buys_at_entry_and_stays_flat_otherwise() -> None:
    index = _calendar_with_one_holiday()
    close = _close_frame(index, {"SPY": [100.0 + i for i in range(len(index))]})
    fn = batch._make_weights_fn("SPY", batch.entry_signal_dates)
    entry = pd.Timestamp("2024-01-10")
    assert fn(close, entry) == {"SPY": 1.0}
    non_entry = pd.Timestamp("2024-01-03")
    assert fn(close, non_entry) == {}


def test_signal_dates_fn_includes_entry_and_matching_exit() -> None:
    index = _calendar_with_one_holiday()
    sig_fn = batch._make_signal_dates_fn(batch.entry_signal_dates, 1)
    dates = set(sig_fn(index))
    assert pd.Timestamp("2024-01-10") in dates  # entry
    assert pd.Timestamp("2024-01-11") in dates  # exit (hold=1)


# --------------------------------------------------------------------------
# RAND placebo: deterministic, price-independent, frequency-matched,
# never a real entry date
# --------------------------------------------------------------------------


def test_rand_entry_dates_deterministic_and_price_independent() -> None:
    index = pd.bdate_range("2024-01-01", periods=200)
    d1 = batch.rand_entry_dates(index, "SPY")
    d2 = batch.rand_entry_dates(index, "SPY")
    assert d1 == d2  # deterministic, no price argument at all


def test_rand_entry_dates_excludes_real_entries_and_is_symbol_specific() -> None:
    index = pd.bdate_range("2024-01-01", periods=400)
    real = set(batch.entry_signal_dates(index))
    rand_spy = set(batch.rand_entry_dates(index, "SPY"))
    rand_qqq = set(batch.rand_entry_dates(index, "QQQ"))
    assert rand_spy.isdisjoint(real)
    assert rand_qqq.isdisjoint(real)
    # different tickers hash differently -> not required to be identical.
    assert rand_spy != rand_qqq or (not rand_spy and not rand_qqq)


def test_rand_entry_dates_are_frequency_matched_to_real_rate() -> None:
    index = pd.bdate_range("2024-01-01", periods=2000)
    rate = batch.real_trigger_rate(index)
    rand = batch.rand_entry_dates(index, "SPY")
    got_rate = len(rand) / float(len(index))
    # within a generous tolerance (deterministic hash draws are not exactly
    # rate * n, but should be close over 2000 sessions).
    assert abs(got_rate - rate) < 0.02


# --------------------------------------------------------------------------
# No look-ahead: mutating rows strictly after `asof` never changes the
# already-decided weight at `asof`.
# --------------------------------------------------------------------------


def test_no_lookahead_on_future_price_history() -> None:
    index = _calendar_with_one_holiday()
    prices_a = [100.0 + i for i in range(len(index))]
    prices_b = [100.0 + i for i in range(len(index))]
    decided_at = pd.Timestamp("2024-01-10")
    decided_pos = list(index).index(decided_at)
    for i in range(decided_pos + 1, len(index)):
        prices_b[i] = prices_b[i] * 5.0 + 999.0
    close_a = _close_frame(index, {"SPY": prices_a})
    close_b = _close_frame(index, {"SPY": prices_b})
    fn = batch._make_weights_fn("SPY", batch.entry_signal_dates)
    for d in list(index)[: decided_pos + 1]:
        assert fn(close_a, d) == fn(close_b, d)


def test_no_lookahead_holds_for_rand_placebo_too() -> None:
    index = pd.bdate_range("2024-01-01", periods=60)
    prices_a = [100.0 + i for i in range(len(index))]
    prices_b = [100.0 - i for i in range(len(index))]  # wildly different trend
    close_a = _close_frame(index, {"SPY": prices_a})
    close_b = _close_frame(index, {"SPY": prices_b})
    entries_fn = lambda idx: batch.rand_entry_dates(idx, "SPY")  # noqa: E731
    fn = batch._make_weights_fn("SPY", entries_fn)
    for d in index:
        assert fn(close_a, d) == fn(close_b, d)  # never reads a price at all
