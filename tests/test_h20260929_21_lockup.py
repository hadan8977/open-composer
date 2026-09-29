"""Tests for T-20260929-21's two scripts:

``scripts/build_h20260929_21_lockups.py``
    Lockup-date arithmetic (IPO date + N calendar days, rolled forward to
    the next date in the panel's own trading calendar) and the no-lookahead
    guard (a 424B4 filing's own filing date must never be after the signal
    date the event uses).
``scripts/run_h20260929_21_lockup_books.py``
    Short-return sign and borrow-cost application (a short that rises in
    price must show a negative P&L contribution, and borrow cost must
    further reduce it, never improve it), and the close-to-close return
    convention, checked directly against ``run_h20260922_05_salvage``'s own
    engine -- the actual frozen engine ``screen_lane.s3_incumbent`` is built
    from -- for a synthetic single-asset book, not just "looks similar".

Run only this file: ``uv run pytest tests/test_h20260929_21_lockup.py -q``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_h20260929_21_lockups as build_mod  # noqa: E402
import run_h20260922_05_salvage as salvage_mod  # noqa: E402
import run_h20260929_21_lockup_books as books_mod  # noqa: E402

# ------------------------------------------------------------------ build


def test_roll_forward_holiday_weekend_roll_uses_panel_calendar():
    """``roll_forward`` must move a lockup date that lands on a day absent
    from the panel's own trading calendar (weekend/holiday, or simply a day
    the panel has no row for) to the next date the calendar actually
    contains -- not to the literal calendar-day arithmetic result, and not
    via any external holiday table."""
    calendar = pd.DatetimeIndex(
        ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-08", "2024-01-09"]
    )
    # 2024-01-05/06/07 (Fri/Sat/Sun) are absent from this synthetic calendar
    # (simulating a holiday-shortened week); the first present date at or
    # after 2024-01-05 is 2024-01-08.
    rolled = build_mod.roll_forward(pd.Timestamp("2024-01-05"), calendar)
    assert rolled == pd.Timestamp("2024-01-08")
    # A date already present in the calendar rolls to itself.
    assert build_mod.roll_forward(pd.Timestamp("2024-01-03"), calendar) == pd.Timestamp(
        "2024-01-03"
    )
    # Past the calendar's end must raise rather than silently fabricate a date.
    try:
        build_mod.roll_forward(pd.Timestamp("2024-02-01"), calendar)
        raise AssertionError("expected ValueError for a date past the calendar's end")
    except ValueError:
        pass


def test_lockup_date_is_ipo_date_plus_180_days_rolled_forward():
    """End-to-end arithmetic check: IPO date + 180 calendar days, rolled to
    the panel's own next trading day, matches a hand-computed expectation."""
    calendar = pd.bdate_range("2024-01-02", periods=400)  # business-day proxy calendar
    ipo_date = pd.Timestamp("2024-03-21")  # e.g. RDDT's real 2024 IPO date
    raw_l = ipo_date + pd.Timedelta(days=180)
    assert raw_l == pd.Timestamp("2024-09-17")
    rolled = build_mod.roll_forward(raw_l, pd.DatetimeIndex(calendar))
    assert rolled >= raw_l
    assert rolled in calendar
    # 2024-09-17 is itself a Tuesday (a business day), so it should roll to itself.
    assert rolled == pd.Timestamp("2024-09-17")


def test_no_event_uses_a_424b4_filing_dated_after_its_own_signal_date():
    """No-lookahead guard: for a 424b4_confirmed event, the entry SIGNAL
    date (close of L-5, the earliest signal any candidate in this iteration
    uses) must never be earlier than the 424B4 filing's own filing date --
    i.e. the filing (which is what makes the IPO date knowable at all) must
    already be public by the time any signal derived from it fires. This is
    checked structurally: filing_date <= ipo_date (by construction, a
    424B4 prices/registers the IPO on or immediately before the IPO date),
    and ipo_date + lockup_days - 5_trading_days_worth_of_calendar_slack is,
    for any realistic lockup_days (>= 10 per ``parse_lockup_days``'s own
    sanity band), far later than filing_date -- so filing_date is always
    <= the earliest signal date derived from it."""
    calendar = pd.DatetimeIndex(pd.bdate_range("2024-01-02", periods=400))
    filing_date = pd.Timestamp("2024-03-20")
    ipo_date = pd.Timestamp("2024-03-21")  # filing at or before the IPO date
    assert filing_date <= ipo_date
    lockup_days = 180
    l_raw = ipo_date + pd.Timedelta(days=lockup_days)
    L = build_mod.roll_forward(l_raw, calendar)
    # Earliest signal used anywhere in this iteration's candidates is L-5
    # trading sessions (short_L5_L1's entry signal).
    l_pos = calendar.get_indexer([L])[0]
    entry_signal_date = calendar[l_pos - 5]
    assert filing_date <= entry_signal_date, (
        "a 424B4 filing dated after the signal it feeds would be lookahead; "
        "with a >=10-day minimum lockup period this must never happen"
    )


def test_classify_fallback_candidate_excludes_spac_units_and_shells():
    ok, reason = build_mod.classify_fallback_candidate("ABCU", 10.0)
    assert not ok
    assert "spac" in reason

    ok, reason = build_mod.classify_fallback_candidate("ABCW", 10.0)
    assert not ok

    ok, reason = build_mod.classify_fallback_candidate("XYZ", 0.50)
    assert not ok
    assert "close" in reason

    ok, reason = build_mod.classify_fallback_candidate("XYZ", 12.0)
    assert ok
    assert reason == "ok"


# ------------------------------------------------------------------ books


def test_stock_legs_matches_salvage_legs_formula():
    dates = pd.bdate_range("2023-01-02", periods=10)
    rng = np.random.default_rng(21)
    close = rng.uniform(90.0, 110.0, size=(len(dates), 3))
    open_ = rng.uniform(90.0, 110.0, size=(len(dates), 3))
    leg_open, leg_close = books_mod.stock_legs(open_, close)

    close_df = pd.DataFrame(close, index=dates, columns=["a", "b", "c"])
    open_df = pd.DataFrame(open_, index=dates, columns=["a", "b", "c"])
    expected_leg_open, expected_leg_close = salvage_mod.legs(close_df, open_df)

    np.testing.assert_allclose(leg_open[1:], expected_leg_open.to_numpy()[1:], atol=1e-12)
    np.testing.assert_allclose(leg_close, expected_leg_close.to_numpy(), atol=1e-12)


def test_simulate_book_matches_salvage_simulate_close_to_close_convention():
    """Direct numeric check (not "looks similar"): with zero borrow, this
    iteration's ``simulate_book`` must exactly reproduce
    ``run_h20260922_05_salvage.simulate`` -- the actual frozen engine
    ``screen_lane.s3_incumbent`` is built from -- for a synthetic
    single-instrument book, confirming the close-to-close realization
    convention matches exactly, not just approximately."""
    dates = pd.bdate_range("2023-01-02", periods=60)
    rng = np.random.default_rng(23)
    px = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=len(dates)))), index=dates)
    close_df = pd.DataFrame({"SPY": px, salvage_mod.CASH: 1.0}, index=dates)
    open_df = pd.DataFrame(
        {
            "SPY": px * (1.0 + rng.normal(0.0, 0.002, size=len(dates))),
            salvage_mod.CASH: 1.0,
        },
        index=dates,
    )
    leg_open_df, leg_close_df = salvage_mod.legs(close_df, open_df)

    weights_df = pd.DataFrame(
        {"SPY": np.ones(len(dates)), salvage_mod.CASH: np.zeros(len(dates))}, index=dates
    )
    scale = np.ones(len(dates))
    expected_ret, expected_turn = salvage_mod.simulate(
        weights_df, leg_open_df, leg_close_df, scale, cost_bps=10.0
    )

    cols = ["SPY", salvage_mod.CASH]
    weights_arr = weights_df[cols].to_numpy(dtype=np.float64)
    leg_open_arr = leg_open_df[cols].to_numpy(dtype=np.float64)
    leg_close_arr = leg_close_df[cols].to_numpy(dtype=np.float64)
    cost_bps_arr = np.array([10.0, 10.0])
    borrow_arr = np.zeros(2)
    got_ret, got_turn_plus_borrow = books_mod.simulate_book(
        weights_arr, leg_open_arr, leg_close_arr, cost_bps_arr, borrow_arr
    )

    np.testing.assert_allclose(got_ret, expected_ret.to_numpy(), atol=1e-12)
    np.testing.assert_allclose(got_turn_plus_borrow, expected_turn.to_numpy(), atol=1e-12)


def test_short_position_that_rises_shows_negative_pnl_before_costs():
    """A short position (negative weight) in an instrument whose price
    rises must show a NEGATIVE gross contribution -- never positive."""
    # Monotonically rising price: open == close == prior close * 1.02 each day.
    close = np.array([[100.0], [102.0], [104.04], [106.1208], [108.243216]])
    open_ = close.copy()  # no intraday move, all gain is overnight
    leg_open, leg_close = books_mod.stock_legs(open_, close)

    weights = np.full((5, 1), -1.0)  # fully short throughout
    cost_bps = np.array([0.0])
    borrow = np.array([0.0])
    net, _ = books_mod.simulate_book(weights, leg_open, leg_close, cost_bps, borrow)

    # Every day after the first (which has a NaN-filled zero overnight leg,
    # i.e. no exposure realized yet) must show a strictly negative return:
    # the price rose, the position is short, so P&L must be negative.
    assert np.all(net[1:] < 0.0), net


def test_borrow_cost_further_reduces_short_pnl_never_improves_it():
    """With a flat price (zero gross P&L), adding a borrow cost on a held
    short position must make net P&L MORE negative, never less negative or
    positive -- borrow is a pure cost, it can never help."""
    close = np.full((5, 1), 100.0)  # flat price: zero gross P&L either way
    open_ = close.copy()
    leg_open, leg_close = books_mod.stock_legs(open_, close)
    weights = np.full((5, 1), -1.0)  # fully short throughout

    cost_bps = np.array([0.0])
    net_no_borrow, _ = books_mod.simulate_book(
        weights, leg_open, leg_close, cost_bps, np.array([0.0])
    )
    net_with_borrow, _ = books_mod.simulate_book(
        weights, leg_open, leg_close, cost_bps, np.array([0.05 / 360.0])
    )

    np.testing.assert_allclose(net_no_borrow, 0.0, atol=1e-12)
    assert np.all(net_with_borrow < net_no_borrow - 1e-15), (net_with_borrow, net_no_borrow)
    # And borrow must scale with the (unsigned) short notional: doubling the
    # weight magnitude doubles the borrow drag.
    weights_2x = np.full((5, 1), -2.0)
    net_2x, _ = books_mod.simulate_book(
        weights_2x, leg_open, leg_close, cost_bps, np.array([0.05 / 360.0])
    )
    drag_1x = net_no_borrow - net_with_borrow
    drag_2x = net_no_borrow - net_2x
    np.testing.assert_allclose(drag_2x[1:], 2.0 * drag_1x[1:], atol=1e-10)


def test_adv_tier_bps_and_borrow_annual_rate_tiers():
    assert books_mod.adv_tier_bps(1.0) == 3.0
    assert books_mod.adv_tier_bps(500.0) == 3.0
    assert books_mod.adv_tier_bps(501.0) == 6.0
    assert books_mod.adv_tier_bps(1000.0) == 6.0
    assert books_mod.adv_tier_bps(1001.0) == 12.0
    assert books_mod.adv_tier_bps(1500.0) == 12.0
    assert books_mod.adv_tier_bps(1501.0) == 25.0
    assert books_mod.adv_tier_bps(float("nan")) == 25.0

    assert books_mod.borrow_annual_rate(1500.0) == books_mod.BORROW_ANNUAL_TOP1500
    assert books_mod.borrow_annual_rate(1501.0) == books_mod.BORROW_ANNUAL_BEYOND
    assert books_mod.borrow_annual_rate(float("nan")) == books_mod.BORROW_ANNUAL_BEYOND


def test_shift_events_actually_moves_entry_and_exit_indices():
    """Regression test for a real bug found in this iteration's first
    backtest run: an earlier version of ``shift_events`` computed
    ``width_before``/``width_after`` AFTER reassigning ``l_idx``, which
    algebraically cancelled the shift and left ``entry_sig_idx``/
    ``exit_sig_idx`` unchanged -- silently turning the date-shift placebo
    into a copy of the real trade (observed as ``mean_diff == 0.0`` and
    ``t_stat`` NaN for every paired trade in the first run's
    results.json). The fixed version must actually move both indices by
    exactly ``shift_sessions``."""
    admitted = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "lockup_date": [pd.Timestamp("2024-06-03"), pd.Timestamp("2024-07-01")],
            "l_idx": [100, 150],
            "entry_sig_idx": [95, 149],  # offsets: AAA=5, BBB=1
            "exit_sig_idx": [101, 155],  # offsets: AAA=1, BBB=5
        }
    )
    shifted = books_mod.shift_events(admitted, 60, n_sessions=1000)
    assert shifted["l_idx"].tolist() == [160, 210]
    assert shifted["entry_sig_idx"].tolist() == [155, 209]
    assert shifted["exit_sig_idx"].tolist() == [161, 215]
    # Window widths (offset_before/offset_after) must be preserved exactly.
    assert (shifted["l_idx"] - shifted["entry_sig_idx"]).tolist() == [5, 1]
    assert (shifted["exit_sig_idx"] - shifted["l_idx"]).tolist() == [1, 5]

    shifted_neg = books_mod.shift_events(admitted, -60, n_sessions=1000)
    assert shifted_neg["l_idx"].tolist() == [40, 90]
    assert shifted_neg["entry_sig_idx"].tolist() == [35, 89]
    assert shifted_neg["exit_sig_idx"].tolist() == [41, 95]
