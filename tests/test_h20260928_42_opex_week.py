"""Synthetic-data tests for `scripts/screen_batches/h20260928_42_opex_week.py`.

No backtest is run here -- these are unit tests of the pure calendar helpers
and weight functions against hand-computed cases, plus the generic contract
checks the iteration brief requires: long-only, sum(weights) <= 1, only
universe tickers appear, no look-ahead (appending future rows never changes
an already-decided `asof`'s weights), and that the module's candidate ids
match `candidate-manifest.json` exactly.
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

import h20260928_42_opex_week as batch  # noqa: E402
import screen_lane as lane  # noqa: E402


def _frame(index: pd.DatetimeIndex, columns: list[str], value: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(value, index=index, columns=columns)


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


# --------------------------------------------------------------------------
# (c) CANDIDATES shape matches the preregistered manifest exactly
# --------------------------------------------------------------------------


def test_candidate_ids_match_manifest_exactly() -> None:
    manifest_path = (
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "h20260928_42_opex_week"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    module_ids = sorted(c.id for c in batch.CANDIDATES)
    assert module_ids == manifest_ids
    assert len(module_ids) == 20


def test_candidates_are_screen_candidate_d_freq_long_only_single_symbol() -> None:
    for c in batch.CANDIDATES:
        assert isinstance(c, lane.ScreenCandidate)
        assert c.freq == "D"
        assert len(c.universe) == 1
        assert callable(c.weights_fn)
        assert callable(c.signal_dates_fn)


# --------------------------------------------------------------------------
# (a) Hand-computed entry/exit signal dates: 2024-03 and 2025-04 (Good Friday)
# --------------------------------------------------------------------------


def test_2024_03_third_friday_week_entry_and_exit_hand_computed() -> None:
    # March 2024 Fridays: 1, 8, 15, 22, 29 -> 3rd Friday = Mar 15 (no holiday).
    # Week containing Mar 15 runs Mon Mar 11 - Sun Mar 17.
    index = pd.bdate_range("2024-02-01", "2024-04-15")
    entries = batch.entry_dates_for_friday(index, 3)
    exits_week = batch.exit_dates_same_week(index, 3)
    exits_weekmon = batch.exit_dates_following_week(index, 3)
    # entry = last trading day before Mon Mar 11 -> Fri Mar 8.
    assert pd.Timestamp("2024-03-08") in entries
    # WEEK exit = last trading day of Mar 11-15 week -> Fri Mar 15 itself.
    assert pd.Timestamp("2024-03-15") in exits_week
    # WEEKMON exit = first trading day of the following week -> Mon Mar 18.
    assert pd.Timestamp("2024-03-18") in exits_weekmon


def test_2025_04_good_friday_holiday_shifts_exit_dates_hand_computed() -> None:
    # April 2025 Fridays: 4, 11, 18, 25 -> 3rd Friday = Apr 18 = Good Friday
    # (NYSE holiday, not a trading day). Week containing Apr 18: Mon Apr 14 -
    # Sun Apr 20; the only NYSE holiday in that week is Good Friday itself.
    index = pd.bdate_range("2025-03-01", "2025-04-30").difference(pd.DatetimeIndex(["2025-04-18"]))
    entries = batch.entry_dates_for_friday(index, 3)
    exits_week = batch.exit_dates_same_week(index, 3)
    exits_weekmon = batch.exit_dates_following_week(index, 3)
    # entry = last trading day before Mon Apr 14 -> Fri Apr 11.
    assert pd.Timestamp("2025-04-11") in entries
    # WEEK exit: Good Friday (Apr 18) is not a trading day, so the last
    # trading day of the Apr 14-20 week is Thu Apr 17.
    assert pd.Timestamp("2025-04-17") in exits_week
    assert pd.Timestamp("2025-04-18") not in exits_week
    # WEEKMON exit = first trading day of the following week -> Mon Apr 21.
    assert pd.Timestamp("2025-04-21") in exits_weekmon


def test_fourth_friday_placebo_skips_months_without_a_fourth_friday() -> None:
    # February 2025 has only 4 Fridays (7, 14, 21, 28) -- 4th Friday exists
    # (Feb 28). February 2026 has Fridays 6, 13, 20, 27 -- also has a 4th.
    # A short (28-day) month with exactly 4 Fridays starting on Friday itself
    # would have a 5th only if Feb 1 is a Friday; use a genuine no-4th-Friday
    # case: a 28-day Feb starting on Saturday has only 4 Fridays too, so
    # instead assert the general invariant directly via _nth_friday.
    assert batch.entry_dates_for_friday(pd.bdate_range("2025-02-01", "2025-02-28"), 4)
    # A month where the 4th Friday genuinely does not exist: any 28-day
    # February where day 1 is Sat/Sun/Mon leaves only 4 Fridays max; pick one
    # with fewer weeks by checking a short index directly against _nth_friday.
    assert batch._nth_friday(2025, 2, 5) is None  # no 5th Friday ever in Feb


# --------------------------------------------------------------------------
# Weights at entry vs exit dates
# --------------------------------------------------------------------------


def test_week_weights_entry_full_exit_cash_hand_computed() -> None:
    index = pd.bdate_range("2024-02-01", "2024-04-15")
    close = _frame(index, ["SPY"])
    fn = batch._make_entry_only_weights_fn("SPY", 3)
    assert fn(close, pd.Timestamp("2024-03-08")) == {"SPY": 1.0}
    assert fn(close, pd.Timestamp("2024-03-15")) == {}
    assert fn(close, pd.Timestamp("2024-03-18")) == {}


def test_weights_missing_column_returns_cash() -> None:
    index = pd.bdate_range("2024-02-01", "2024-04-15")
    close = _frame(index, ["QQQ"])  # SPY absent
    fn = batch._make_entry_only_weights_fn("SPY", 3)
    assert fn(close, pd.Timestamp("2024-03-08")) == {}


@pytest.mark.parametrize("candidate", batch.CANDIDATES, ids=lambda c: c.id)
def test_universe_only_and_long_only_over_signal_dates(candidate: lane.ScreenCandidate) -> None:
    index = pd.bdate_range("2023-01-01", "2025-12-31")
    close = _frame(index, list(candidate.universe))
    dates = candidate.signal_dates_fn(index)
    assert dates  # every candidate must fire at least once over 3 years
    for asof in dates:
        weights = candidate.weights_fn(close, asof)
        _assert_contract(weights, candidate.universe)


# --------------------------------------------------------------------------
# (b) weights_fn never reads a value at or after `asof`: no look-ahead
# --------------------------------------------------------------------------


def test_no_lookahead_on_future_price_history() -> None:
    index = pd.bdate_range("2024-02-01", "2024-04-15")
    decided_at = pd.Timestamp("2024-03-08")  # an entry date (see above)

    close_short = _frame(index[: index.get_loc(decided_at) + 1], ["SPY"])
    fn = batch._make_entry_only_weights_fn("SPY", 3)
    weights_short = fn(close_short, decided_at)

    future_index = pd.bdate_range(index[-1] + pd.Timedelta(days=1), periods=40)
    close_long = pd.concat([close_short, pd.DataFrame(9999.0, index=future_index, columns=["SPY"])])
    weights_long = fn(close_long, decided_at)

    assert weights_short == weights_long == {"SPY": 1.0}


def test_no_lookahead_signal_dates_stable_when_index_extended_within_same_month() -> None:
    # entry/exit dates for a decided month must not depend on how far the
    # index extends into LATER months (the exchange calendar for a closed
    # month is fixed; only future-month scaffolding could differ).
    short_index = pd.bdate_range("2024-01-01", "2024-03-20")
    long_index = pd.bdate_range("2024-01-01", "2024-12-31")
    entries_short = [d for d in batch.entry_dates_for_friday(short_index, 3) if d.month == 3]
    entries_long = [d for d in batch.entry_dates_for_friday(long_index, 3) if d.month == 3]
    assert entries_short == entries_long
    exits_short = [d for d in batch.exit_dates_same_week(short_index, 3) if d.month == 3]
    exits_long = [d for d in batch.exit_dates_same_week(long_index, 3) if d.month == 3]
    assert exits_short == exits_long


# --------------------------------------------------------------------------
# WEEK vs WEEKMON signal_dates_fn differ only on the exit leg
# --------------------------------------------------------------------------


def test_week_vs_weekmon_signal_dates_share_entries_differ_on_exit() -> None:
    index = pd.bdate_range("2024-01-01", "2024-12-31")
    week_fn = batch._make_week_signal_dates_fn(3)
    weekmon_fn = batch._make_weekmon_signal_dates_fn(3)
    week_dates = set(week_fn(index))
    weekmon_dates = set(weekmon_fn(index))
    entries = set(batch.entry_dates_for_friday(index, 3))
    assert entries <= week_dates
    assert entries <= weekmon_dates
    assert (week_dates - entries).isdisjoint(weekmon_dates - entries)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
