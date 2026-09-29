"""Unit tests for h20260929_20_news_nonews_drop_reversal: synthetic data
only, no network, no real market panel."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_h20260929_20_events as build_mod  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import run_h20260929_20_drop_reversal as run_mod  # noqa: E402


def _trading_days(periods: int = 10) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-02-05", periods=periods)  # includes a normal week, no DST edge


# --------------------------------------------------------------------- news/8-K session bucketing


def test_news_after_close_of_t_is_not_counted_for_day_t():
    days = _trading_days(5)
    closes_utc = build_mod.session_close_utc(days)
    # session_close(t=days[2]) is 2024-02-07 16:00 America/New_York (EST, UTC-5) = 21:00 UTC.
    one_minute_after_close = pd.Series(pd.Timestamp("2024-02-07 21:01:00", tz="UTC"), index=[0])
    bucket = build_mod.bucket_to_trading_day(one_minute_after_close, closes_utc, days)
    assert pd.Timestamp(bucket[0]) == days[3], (
        "a news item 1 minute after t's close must bucket to t+1, not t"
    )

    one_minute_before_close = pd.Series(pd.Timestamp("2024-02-07 20:59:00", tz="UTC"), index=[0])
    bucket2 = build_mod.bucket_to_trading_day(one_minute_before_close, closes_utc, days)
    assert pd.Timestamp(bucket2[0]) == days[2], (
        "a news item before t's close must still bucket to t"
    )

    exactly_at_close = pd.Series(pd.Timestamp("2024-02-07 21:00:00", tz="UTC"), index=[0])
    bucket3 = build_mod.bucket_to_trading_day(exactly_at_close, closes_utc, days)
    assert pd.Timestamp(bucket3[0]) == days[2], (
        "a news item exactly at t's close counts for t (half-open interval)"
    )


def test_news_bucketing_handles_dst_transition_correctly():
    # 2024-03-08 is EST (UTC-5, close=21:00 UTC); 2024-03-11 is the first EDT
    # trading day after the spring-forward (UTC-4, close=20:00 UTC). A biased
    # fixed-offset implementation would mis-bucket news filed between 20:00
    # and 21:00 UTC on the EDT day.
    days = pd.DatetimeIndex(
        [pd.Timestamp("2024-03-08"), pd.Timestamp("2024-03-11"), pd.Timestamp("2024-03-12")]
    )
    closes_utc = build_mod.session_close_utc(days)
    assert closes_utc[1] == pd.Timestamp("2024-03-11 20:00:00", tz="UTC")
    ts_after_edt_close = pd.Series(pd.Timestamp("2024-03-11 20:30:00", tz="UTC"), index=[0])
    bucket = build_mod.bucket_to_trading_day(ts_after_edt_close, closes_utc, days)
    assert pd.Timestamp(bucket[0]) == days[2]


# --------------------------------------------------------------------- entry timing / no look-ahead


def _one_event(
    symbol: str, event_date: pd.Timestamp, tier: int = 1, adj_ret: float = -0.06
) -> pd.DataFrame:
    return pd.DataFrame(
        [{"symbol": symbol, "event_date": event_date, "adj_ret": adj_ret, "tier": tier}]
    )


def test_entry_is_at_the_open_of_t_plus_1():
    days = _trading_days(8)
    events = _one_event("X", days[3])
    weights, _cost, _borrow, trades = run_mod.run_book(
        events, days, h=2, sign=1.0, borrow=False, cost_multiplier=1.0
    )
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["entry_idx"] == 4, "entry must be at day index t+1"
    assert row["exit_idx"] == 5, "h=2 sessions means exit at entry_idx + h - 1"
    # no weight on the signal day itself or any day before entry
    for i in range(0, 4):
        assert weights.iloc[i]["X"] == 0.0, f"day {i} (<= signal day) must carry zero weight for X"
    assert weights.iloc[4]["X"] != 0.0
    assert weights.iloc[5]["X"] != 0.0
    assert weights.iloc[6]["X"] == 0.0, "position must be flat again the day after exit"


def test_no_position_uses_information_after_its_entry():
    """Truncating the price/event data to end exactly at a trade's exit day
    must not change that trade's weights up to and including the exit day --
    i.e. nothing about the book before/at exit depends on data after exit."""
    days = _trading_days(10)
    events = _one_event("X", days[2])
    weights_full, _c1, _b1, trades_full = run_mod.run_book(
        events, days, h=3, sign=1.0, borrow=False, cost_multiplier=1.0
    )
    exit_idx = int(trades_full.iloc[0]["exit_idx"])
    truncated_days = days[: exit_idx + 1]
    weights_trunc, _c2, _b2, trades_trunc = run_mod.run_book(
        events, truncated_days, h=3, sign=1.0, borrow=False, cost_multiplier=1.0
    )
    pd.testing.assert_frame_equal(
        weights_full.loc[truncated_days, sorted(weights_trunc.columns)],
        weights_trunc[sorted(weights_trunc.columns)],
    )
    assert len(trades_trunc) == 1


def test_no_pyramiding_same_symbol_while_position_open():
    days = _trading_days(10)
    events = pd.concat(
        [_one_event("X", days[1]), _one_event("X", days[2])], ignore_index=True
    )  # second event fires while the first trade (h=5) is still open
    _weights, _cost, _borrow, trades = run_mod.run_book(
        events, days, h=5, sign=1.0, borrow=False, cost_multiplier=1.0
    )
    assert len(trades) == 1, "a symbol with an already-open position must not accept a second entry"


def test_capacity_cap_admits_largest_drop_first():
    days = _trading_days(6)
    events = pd.concat(
        [
            _one_event("A", days[1], adj_ret=-0.05),
            _one_event("B", days[1], adj_ret=-0.09),
            _one_event("C", days[1], adj_ret=-0.07),
        ],
        ignore_index=True,
    )
    old_cap = run_mod.MAX_POSITIONS
    run_mod.MAX_POSITIONS = 2
    try:
        _weights, _cost, _borrow, trades = run_mod.run_book(
            events, days, h=1, sign=1.0, borrow=False, cost_multiplier=1.0
        )
    finally:
        run_mod.MAX_POSITIONS = old_cap
    assert set(trades["symbol"]) == {"B", "C"}, (
        "largest drops (B then C) must be admitted first, A skipped"
    )


# --------------------------------------------------------------------- engine parity


def test_synthetic_always_spy_book_reproduces_spy_close_to_close():
    days = _trading_days(12)
    n = len(days)
    rng = np.random.default_rng(0)
    spy = 400.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.01, n))
    open_spy = spy * (1.0 + rng.normal(0.0, 0.002, n))
    cash = np.full(n, 100.0)
    # salvage.simulate hardcodes its cash column name to CASH ("SHY"); use
    # that name here purely so the frozen engine's own cash lookup works --
    # this iteration's own book uses "BIL" as its cash sleeve (see
    # cost-contract.json), which is orthogonal to this parity check.
    close = pd.DataFrame({"SPY": spy, salvage.CASH: cash}, index=days)
    open_ = pd.DataFrame({"SPY": open_spy, salvage.CASH: cash}, index=days)
    leg_open, leg_close = salvage.legs(close, open_)

    weights = pd.DataFrame(0.0, index=days, columns=["SPY", salvage.CASH])
    weights.loc[days[0] :, "SPY"] = 1.0
    weights[salvage.CASH] = 1.0 - weights["SPY"]
    cost_bps = pd.DataFrame(0.0, index=days, columns=["SPY", salvage.CASH])
    borrow = pd.DataFrame(0.0, index=days, columns=["SPY", salvage.CASH])

    mine_ret, mine_turn = run_mod.simulate_tiered(weights, leg_open, leg_close, cost_bps, borrow)
    frozen_ret, frozen_turn = salvage.simulate(weights, leg_open, leg_close, np.ones(n), 0.0)

    # Regression against the frozen, unedited S3 engine: with zero cost and
    # zero borrow, my generalized simulator must match it exactly.
    np.testing.assert_allclose(mine_ret.to_numpy(), frozen_ret.to_numpy(), atol=1e-12)
    np.testing.assert_allclose(mine_turn.to_numpy(), frozen_turn.to_numpy(), atol=1e-12)

    # And it must track SPY's own close-to-close growth closely (the engine's
    # additive leg-sum convention omits the tiny open/close cross term, so
    # this is a close-tracking check, not bit-for-bit equality to pct_change).
    equity_mine = (1.0 + mine_ret).cumprod()
    equity_spy = close["SPY"] / close["SPY"].iloc[0]
    assert abs(equity_mine.iloc[-1] / equity_spy.iloc[-1] - 1.0) < 0.01


def test_tiered_cost_matches_manual_calc_on_two_symbol_book():
    days = _trading_days(4)
    close = pd.DataFrame({"A": [10.0, 10.0, 11.0, 11.0], "B": [10.0, 10.0, 10.0, 10.0]}, index=days)
    open_ = pd.DataFrame({"A": [10.0, 10.0, 10.0, 11.0], "B": [10.0, 10.0, 10.0, 10.0]}, index=days)
    leg_open, leg_close = salvage.legs(close, open_)
    weights = pd.DataFrame({"A": [0.0, 1.0, 1.0, 0.0], "B": [0.0, 0.0, 0.0, 0.0]}, index=days)
    cost_bps = pd.DataFrame({"A": [0.0, 12.0, 0.0, 12.0], "B": [0.0, 0.0, 0.0, 0.0]}, index=days)
    borrow = pd.DataFrame(0.0, index=days, columns=["A", "B"])
    ret, turn = run_mod.simulate_tiered(weights, leg_open, leg_close, cost_bps, borrow)
    # day index 1: turnover |1-0| = 1.0, cost = 1.0 * 12 / 10000
    assert turn.iloc[1] == pytest.approx(1.0)
    expected_cost_day1 = 1.0 * 12.0 / 10000.0
    gross_day1 = 0.0 * leg_open["A"].iloc[1] + 1.0 * leg_close["A"].iloc[1]
    assert ret.iloc[1] == pytest.approx(gross_day1 - expected_cost_day1)


def test_candidate_grid_matches_candidate_manifest():
    import json

    manifest_path = (
        Path(__file__).resolve().parents[1]
        / "reports/research/iterations/h20260929_20_news_nonews_drop_reversal"
        / "candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text())
    manifest_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    code_ids = sorted(c["id"] for c in run_mod.CANDIDATES)
    assert manifest_ids == code_ids
    assert len(run_mod.CANDIDATES) == 12
