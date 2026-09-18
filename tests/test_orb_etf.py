"""Tests for the pure trade-construction and equity-simulation logic in
``scripts/run_h20260918_02_orb_etf.py`` -- the parts that don't need the real
minute-bar archive: opening-candle/doji/entry-bar detection, stop/target/close
exit resolution (``build_day_records``), and position sizing with the
leverage cap (``simulate_equity``). DuckDB shard reads are exercised by
actually running the script's ``load`` stage against the real archive
(matching the convention of sibling ``build_*_features.py`` / ORB scripts:
no per-script unit test for the data-touching functions either).

Calls the module's own functions directly
(``importlib.import_module("scripts.run_h20260918_02_orb_etf")``), matching
the idiom in ``tests/test_build_hourly_bars.py``.
"""

from __future__ import annotations

import importlib
import math
from datetime import date, time

import pandas as pd
import pytest

orb_etf = importlib.import_module("scripts.run_h20260918_02_orb_etf")


def _bars(rows: list[tuple[time, float, float, float, float]]) -> pd.DataFrame:
    """``rows`` are ``(ny_time, open, high, low, close)`` tuples."""
    return pd.DataFrame(
        [{"ny_time": t, "open": o, "high": h, "low": low_, "close": c} for t, o, h, low_, c in rows]
    )


def _primary(records: list[dict]) -> dict:
    return next(r for r in records if r["anchor"] == orb_etf.PRIMARY_ANCHOR)


# --------------------------------------------------------------------------
# build_day_records: opening candle, doji, entry, stop/target/close exits
# --------------------------------------------------------------------------


def test_long_day_hits_10r_target() -> None:
    # Opening candle 09:30-09:34: open 100.0 -> close 100.8, high 100.9, low
    # 99.8 -- close-open (0.8) well above the 5%*(high-low) doji band (0.055),
    # so direction is long. R = entry(100.8) - stop(99.8) = 1.0, target = 110.8.
    rows = [
        (time(9, 30), 100.0, 100.5, 99.8, 100.2),
        (time(9, 31), 100.2, 100.6, 100.1, 100.4),
        (time(9, 32), 100.4, 100.7, 100.3, 100.5),
        (time(9, 33), 100.5, 100.8, 100.4, 100.6),
        (time(9, 34), 100.6, 100.9, 100.5, 100.8),
        (time(9, 35), 100.8, 101.0, 100.7, 100.9),  # entry bar, no hit yet
        (time(9, 36), 100.9, 111.0, 100.8, 110.0),  # high 111 >= target 110.8
    ]
    records = orb_etf.build_day_records(date(2024, 6, 3), _bars(rows))
    row = _primary(records)
    assert row["missing"] is False
    assert row["direction_real"] == 1
    assert row["entry_price"] == pytest.approx(100.8)
    assert row["long_stop"] == pytest.approx(99.8)
    assert row["long_R"] == pytest.approx(1.0)
    assert row["long_target"] == pytest.approx(110.8)
    assert row["long_exit_reason"] == "target"
    assert row["long_exit_price"] == pytest.approx(110.8)
    assert row["long_holding_min"] == 2


def test_long_day_stopped_out() -> None:
    rows = [
        (time(9, 30), 100.0, 100.5, 99.8, 100.2),
        (time(9, 31), 100.2, 100.4, 100.0, 100.3),
        (time(9, 32), 100.3, 100.5, 100.1, 100.35),
        (time(9, 33), 100.35, 100.5, 100.2, 100.4),
        (time(9, 34), 100.4, 100.5, 100.3, 100.45),
        (time(9, 35), 100.45, 100.6, 100.3, 100.4),  # entry bar, no hit
        (time(9, 36), 100.4, 100.5, 99.5, 99.6),  # low 99.5 <= stop 99.8
    ]
    records = orb_etf.build_day_records(date(2024, 6, 4), _bars(rows))
    row = _primary(records)
    assert row["direction_real"] == 1
    assert row["long_stop"] == pytest.approx(99.8)
    assert row["long_exit_reason"] == "stop"
    assert row["long_exit_price"] == pytest.approx(99.8)
    # the "1 bp worse fill" variant is a separate, worse (lower) long exit.
    assert row["long_exit_price_slip"] == pytest.approx(99.8 * 0.9999)
    assert row["long_exit_price_slip"] < row["long_exit_price"]
    assert row["long_holding_min"] == 2


def test_short_day_exits_at_session_close() -> None:
    # candle_open=100.0, candle_close=98.8 -> short; stop = candle_high
    # (100.3), target = 98.8 - 15 = 83.8, never reached in the short path
    # given here, so it exits at the close of the last bar supplied.
    rows = [
        (time(9, 30), 100.0, 100.3, 99.5, 99.7),
        (time(9, 31), 99.7, 99.9, 99.4, 99.5),
        (time(9, 32), 99.5, 99.7, 99.2, 99.3),
        (time(9, 33), 99.3, 99.5, 99.0, 99.1),
        (time(9, 34), 99.1, 99.3, 98.9, 98.8),
        (time(9, 35), 98.8, 99.0, 98.6, 98.7),  # entry bar
        (time(9, 36), 98.7, 98.9, 98.5, 98.6),
        (time(9, 37), 98.6, 98.8, 98.4, 98.5),  # last bar of (truncated) session
    ]
    records = orb_etf.build_day_records(date(2024, 6, 5), _bars(rows))
    row = _primary(records)
    assert row["direction_real"] == -1
    assert row["entry_price"] == pytest.approx(98.8)
    assert row["short_stop"] == pytest.approx(100.3)
    assert row["short_exit_reason"] == "close"
    assert row["short_exit_price"] == pytest.approx(98.5)
    assert row["short_holding_min"] == 3


def test_doji_day_is_skipped_but_outcomes_still_computed_for_controls() -> None:
    # |close - open| = 0.02 <= 0.05 * (high - low) = 0.05 -- doji.
    rows = [
        (time(9, 30), 100.00, 100.5, 99.5, 100.00),
        (time(9, 31), 100.00, 100.3, 99.7, 100.00),
        (time(9, 32), 100.00, 100.2, 99.8, 100.00),
        (time(9, 33), 100.00, 100.2, 99.8, 100.00),
        (time(9, 34), 100.00, 100.2, 99.8, 100.02),
        (time(9, 35), 100.02, 100.2, 99.9, 100.05),
        (time(9, 36), 100.05, 100.2, 99.9, 100.10),
    ]
    records = orb_etf.build_day_records(date(2024, 6, 6), _bars(rows))
    row = _primary(records)
    assert row["missing"] is False
    assert math.isnan(row["direction_real"])
    # still computed so the long-only random-day control (which ignores the
    # doji filter) can use this day.
    assert not math.isnan(row["long_R"])
    assert not math.isnan(row["short_R"])


def test_missing_entry_bar_is_reported_as_missing() -> None:
    rows = [
        (time(9, 30), 100.0, 100.5, 99.8, 100.2),
        (time(9, 31), 100.2, 100.6, 100.1, 100.4),
        (time(9, 32), 100.4, 100.7, 100.3, 100.5),
        (time(9, 33), 100.5, 100.8, 100.4, 100.6),
        (time(9, 34), 100.6, 100.9, 100.5, 100.8),
        # 09:35 entry bar missing entirely.
    ]
    records = orb_etf.build_day_records(date(2024, 6, 7), _bars(rows))
    row = _primary(records)
    assert row["missing"] is True
    assert math.isnan(row["direction_real"])
    assert math.isnan(row["long_R"])


def test_half_day_is_flagged_and_exits_at_the_early_close_bar() -> None:
    # 2024-07-03 is a confirmed NYSE early close (13:00 ET). The caller
    # (stage_load) is what truncates a day's bars to `< session_close`
    # before calling build_day_records; this test feeds an already-truncated
    # day (last bar 12:59) to isolate build_day_records's own half-day
    # detection and close-of-last-bar exit behavior.
    rows = [
        (time(9, 30), 100.0, 100.5, 99.8, 100.2),
        (time(9, 31), 100.2, 100.6, 100.1, 100.4),
        (time(9, 32), 100.4, 100.7, 100.3, 100.5),
        (time(9, 33), 100.5, 100.8, 100.4, 100.6),
        (time(9, 34), 100.6, 100.9, 100.5, 100.8),
        (time(9, 35), 100.8, 100.9, 100.7, 100.85),  # entry bar
        (time(12, 59), 100.85, 100.95, 100.8, 100.9),  # last bar before 13:00 close
    ]
    records = orb_etf.build_day_records(date(2024, 7, 3), _bars(rows))
    row = _primary(records)
    assert row["is_half_day"] is True
    assert row["direction_real"] == 1
    assert row["long_exit_reason"] == "close"
    assert row["long_exit_price"] == pytest.approx(100.9)


# --------------------------------------------------------------------------
# simulate_equity: position sizing and the leverage cap
# --------------------------------------------------------------------------


def test_position_size_cap_binds_at_leverage_one() -> None:
    # entry=100, R=0.5 -> risk-based notional = 0.01 * 1.0 * 100 / 0.5 = 2.0,
    # which exceeds the leverage=1 cap of 1.0 * equity = 1.0. The capped
    # notional (1.0) implies shares = 0.01, not the uncapped 0.02.
    trade = {
        "date": date(2024, 1, 2),
        "direction": 1,
        "entry_price": 100.0,
        "R": 0.5,
        "exit_price": 105.0,
        "exit_price_slip": 105.0,
        "exit_reason": "close",
        "holding_min": 5.0,
    }
    returns, trade_rows = orb_etf.simulate_equity(
        [trade],
        [trade["date"]],
        leverage=1,
        cost_bps=0.0,
        stop_variant="exact",
    )
    assert len(trade_rows) == 1
    capped_shares = (1.0 * 1.0) / 100.0  # leverage * equity / entry_price
    expected_pnl = capped_shares * (105.0 - 100.0)
    assert trade_rows[0]["net_pnl"] == pytest.approx(expected_pnl)
    assert returns.iloc[0] == pytest.approx(expected_pnl / 1.0)

    # At leverage=4 the same trade is not cap-bound (uncapped notional 2.0 <=
    # cap 4.0), so it earns strictly more than the leverage=1, cap-bound row.
    returns_lev4, trade_rows_lev4 = orb_etf.simulate_equity(
        [trade],
        [trade["date"]],
        leverage=4,
        cost_bps=0.0,
        stop_variant="exact",
    )
    assert trade_rows_lev4[0]["net_pnl"] > trade_rows[0]["net_pnl"]


def test_short_trade_pays_borrow_fee_and_long_does_not() -> None:
    long_trade = {
        "date": date(2024, 1, 2),
        "direction": 1,
        "entry_price": 100.0,
        "R": 1.0,
        "exit_price": 100.0,
        "exit_price_slip": 100.0,
        "exit_reason": "close",
        "holding_min": 390.0,
    }
    short_trade = {**long_trade, "direction": -1}
    _, long_rows = orb_etf.simulate_equity(
        [long_trade], [long_trade["date"]], leverage=1, cost_bps=0.0, stop_variant="exact"
    )
    _, short_rows = orb_etf.simulate_equity(
        [short_trade], [short_trade["date"]], leverage=1, cost_bps=0.0, stop_variant="exact"
    )
    # Flat exit (entry == exit) means gross P&L is zero for both; the short
    # leg alone must show a strictly negative net P&L from the borrow fee.
    assert long_rows[0]["net_pnl"] == pytest.approx(0.0)
    assert short_rows[0]["net_pnl"] < 0.0
