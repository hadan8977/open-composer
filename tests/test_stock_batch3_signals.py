"""Stock batch 3 (H-20260928-06): synthetic-data unit tests, no network, no
market panel. Checks the two properties the brief requires: every score uses
only data up to the signal date (appending future rows leaves past scores
unchanged), and each long-only leg selects the intended end of the ranking.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260928_06_stock_batch3 as batch3  # noqa: E402

from open_composer.research.signal_card import book_returns, hold, topk_cohorts  # noqa: E402

# --------------------------------------------------------------- fixtures


def _synthetic_index(periods: int = 90) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=periods)


def _synthetic_etf_panel(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SPY/QQQ grow steadily, SHY is flat cash; `open[i] = close[i-1]` (no
    overnight gap) so the whole day's move is earned by the weight effective
    at that day's open, matching the frozen next-open-fill convention."""
    n = len(index)
    spy = 100.0 * (1.0008 ** np.arange(n))
    qqq = 100.0 * (1.0012 ** np.arange(n))
    shy = np.full(n, 100.0)
    close = pd.DataFrame({"SPY": spy, "QQQ": qqq, "SHY": shy}, index=index)
    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0]
    return close, open_


# ----------------------------------------------- topk_cohorts / hold PIT


def test_topk_cohorts_uses_only_data_up_to_signal_date() -> None:
    """Appending future rows to the signal matrix must not change an earlier
    session's cohort selection (no lookahead in the top-k formation itself)."""
    rng = np.random.default_rng(20260928)
    n_days, n_syms = 40, 12
    signal = rng.normal(size=(n_days, n_syms)).astype(np.float32)
    eligible = np.ones((n_days, n_syms), dtype=bool)

    cohorts_full = topk_cohorts(signal, eligible, k=3)

    truncated_signal = signal[:20].copy()
    truncated_eligible = eligible[:20]
    cohorts_truncated = topk_cohorts(truncated_signal, truncated_eligible, k=3)

    np.testing.assert_array_equal(cohorts_full[:20], cohorts_truncated)


def test_topk_cohorts_selects_the_highest_signal_names() -> None:
    """The long-only leg must select the intended end of the ranking: the
    largest raw signal values (direction is applied by the caller before this
    function is called, so topk_cohorts itself always picks the max)."""
    signal = np.array([[5.0, 1.0, 4.0, 2.0, 3.0]], dtype=np.float32)
    eligible = np.ones_like(signal, dtype=bool)
    cohorts = topk_cohorts(signal, eligible, k=2, chunk=1)
    # MIN_NAMES gate (30) would normally suppress a 5-name universe; bypass it
    # here by monkeypatching is unnecessary since we only check the mechanics
    # of argpartition selection directly.
    from open_composer.research import signal_card as sc

    old_min_names = sc.MIN_NAMES
    sc.MIN_NAMES = 2
    try:
        cohorts = topk_cohorts(signal, eligible, k=2, chunk=1)
    finally:
        sc.MIN_NAMES = old_min_names
    picked = np.nonzero(cohorts[0] > 0)[0]
    assert set(picked) == {0, 2}  # signal values 5.0 and 4.0, the top two


def test_dist_from_252d_high_direction_picks_names_nearest_the_high() -> None:
    """skew_52wk_high_k95 uses direction=+1 (no negation) on
    dist_from_252d_high, whose convention is in [-1, 0] with 0 = at the high.
    Confirm that raw-value top-k under that convention picks the names
    CLOSEST to their 52-week high (least negative), not farthest -- the
    direction this round's primary source requires (see
    reports/harness/source_cards/h20260928_06_registry_stock_batch3.jsonl,
    claim_id pwb_skewness_52wk_high_2017)."""
    from open_composer.research import signal_card as sc

    dist = np.array([[-0.30, -0.02, -0.15, -0.01, -0.40]], dtype=np.float32)
    eligible = np.ones_like(dist, dtype=bool)
    old_min_names = sc.MIN_NAMES
    sc.MIN_NAMES = 2
    try:
        cohorts = topk_cohorts(dist, eligible, k=2, chunk=1)
    finally:
        sc.MIN_NAMES = old_min_names
    picked = np.nonzero(cohorts[0] > 0)[0]
    assert set(picked) == {1, 3}  # -0.02 and -0.01, nearest zero (the high)


def test_hold_event_book_uses_only_data_up_to_signal_date() -> None:
    """A 13D-style event a few sessions apart: appending a future event must
    not change an earlier session's held weights."""
    n_days, n_syms = 20, 4
    events = np.zeros((n_days, n_syms), dtype=np.float32)
    events[2, 0] = 1.0
    events[5, 1] = 1.0
    held_full = hold(events, h=6, normalize=True)

    events_future = events.copy()
    events_future[15, 2] = 1.0  # an event far in the future
    held_with_future_event = hold(events_future, h=6, normalize=True)

    np.testing.assert_array_equal(held_full[:12], held_with_future_event[:12])


def test_hold_event_enters_at_next_session_open_not_the_event_day() -> None:
    n_days, n_syms = 10, 2
    events = np.zeros((n_days, n_syms), dtype=np.float32)
    events[3, 0] = 1.0
    held = hold(events, h=2, normalize=True)
    # Row 3 (the event/visible day itself) must NOT yet be held -- entry is
    # at the next session's open, i.e. weight first appears on row 4.
    assert held[3, 0] == 0.0
    assert held[4, 0] > 0.0
    assert held[5, 0] > 0.0
    assert held[6, 0] == 0.0  # h=2 sessions of hold, then flat


def test_book_returns_charges_turnover_cost() -> None:
    held = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 0.0]], dtype=np.float32)
    ret = np.array([[0.0, 0.0], [0.02, 0.0], [0.03, 0.0], [0.0, 0.0]], dtype=np.float32)
    net, turnover = book_returns(held, ret, cost_bps=10.0)
    # Turnover of 1.0 on entry (row 1) and 1.0 on exit (row 3), 0 in between.
    np.testing.assert_allclose(turnover, [0.0, 1.0, 0.0, 1.0])
    np.testing.assert_allclose(net[1], 0.02 - 1.0 * 10.0 / 1e4)
    np.testing.assert_allclose(net[2], 0.03)
    np.testing.assert_allclose(net[3], 0.0 - 1.0 * 10.0 / 1e4)


# ---------------------------------------------------- ETF-timing candidates


def test_monday_afternoon_returns_uses_only_close_and_open_up_to_signal_date() -> None:
    index = _synthetic_index(40)
    close, open_ = _synthetic_etf_panel(index)
    ret_full, _turn_full = batch3.monday_afternoon_returns(close, open_, "SPY", 10.0)

    truncated_index = index[:25]
    close_t, open_t = close.loc[truncated_index], open_.loc[truncated_index]
    ret_truncated, _ = batch3.monday_afternoon_returns(close_t, open_t, "SPY", 10.0)

    pd.testing.assert_series_equal(
        ret_full.loc[truncated_index[:-1]], ret_truncated.loc[truncated_index[:-1]]
    )


def test_monday_afternoon_holds_only_after_a_positive_monday_session() -> None:
    """Construct one Monday with a positive close-vs-open session and one
    with a negative session; confirm the position is held (nonzero SPY
    weight) only in the week following the positive Monday."""
    index = _synthetic_index(20)
    n = len(index)
    close_vals = np.full(n, 100.0)
    open_vals = np.full(n, 100.0)
    mondays = [d for d in index if d.weekday() == 0]
    assert len(mondays) >= 2
    pos_monday, neg_monday = mondays[0], mondays[1]
    pos_i, neg_i = index.get_loc(pos_monday), index.get_loc(neg_monday)
    open_vals[pos_i], close_vals[pos_i] = 100.0, 101.0  # positive session
    open_vals[neg_i], close_vals[neg_i] = 100.0, 99.0  # negative session
    close = pd.DataFrame({"SPY": close_vals, "SHY": np.full(n, 100.0)}, index=index)
    open_ = pd.DataFrame({"SPY": open_vals, "SHY": np.full(n, 100.0)}, index=index)

    weights = base.weights_from_selection(
        index,
        [pos_monday, neg_monday],
        {
            pos_monday: ["SPY"]
            if close.at[pos_monday, "SPY"] > open_.at[pos_monday, "SPY"]
            else [],
            neg_monday: ["SPY"]
            if close.at[neg_monday, "SPY"] > open_.at[neg_monday, "SPY"]
            else [],
        },
        ["SPY", "SHY"],
    )
    day_after_pos = index[pos_i + 1]
    day_after_neg = index[neg_i + 1]
    assert weights.at[day_after_pos, "SPY"] == 1.0
    assert weights.at[day_after_neg, "SPY"] == 0.0
    assert weights.at[day_after_neg, "SHY"] == 1.0


def test_overnight_only_returns_ignores_intraday_move_and_charges_round_trip_cost() -> None:
    index = _synthetic_index(6)
    close = pd.DataFrame({"SPY": [100.0, 101.0, 101.0, 103.0, 103.0, 106.0]}, index=index)
    open_ = pd.DataFrame({"SPY": [100.0, 100.5, 102.0, 101.5, 105.0, 103.5]}, index=index)
    ret, turnover = batch3.overnight_only_returns(close, open_, "SPY", cost_bps=10.0)
    # Session 1: overnight = open[1]/close[0]-1 = 100.5/100-1 = 0.5%, regardless
    # of the day's intraday move (close[1]=101 vs open[1]=100.5 is ignored).
    expected_overnight_1 = 100.5 / 100.0 - 1.0
    assert np.isclose(ret.iloc[1] + 2 * 10.0 / 1e4, expected_overnight_1)
    # Every session pays the 2x round-trip cost, not the 1x per-side default.
    assert (turnover == 2.0).all()


def test_overnight_only_returns_uses_only_data_up_to_signal_date() -> None:
    index = _synthetic_index(30)
    close, open_ = _synthetic_etf_panel(index)
    ret_full, _ = batch3.overnight_only_returns(close, open_, "QQQ", 10.0)
    truncated_index = index[:15]
    ret_truncated, _ = batch3.overnight_only_returns(
        close.loc[truncated_index], open_.loc[truncated_index], "QQQ", 10.0
    )
    pd.testing.assert_series_equal(ret_full.loc[truncated_index], ret_truncated)


# --------------------------------------------------------------- k1 / k2


def _net(sharpe: float, cagr: float) -> dict:
    return {
        "anchor": {"sharpe": sharpe, "cagr": cagr},
        "stress": {"sharpe": sharpe, "cagr": cagr},
    }


def test_k1_verdict_requires_both_sharpe_and_cagr_bars() -> None:
    net10 = {"anchor": {"sharpe": 1.5}, "stress": {"sharpe": 0.9}}
    net20 = {"anchor": {"cagr": 0.10}, "stress": {"cagr": 0.05}}
    verdict = batch3.k1_verdict(net10, net20)
    assert verdict["sharpe_bar_pass"] is True
    assert verdict["cagr_bar_pass"] is True
    assert verdict["pass"] is True

    net10_fail = {"anchor": {"sharpe": 1.0}, "stress": {"sharpe": 0.9}}
    verdict_fail = batch3.k1_verdict(net10_fail, net20)
    assert verdict_fail["sharpe_bar_pass"] is False
    assert verdict_fail["pass"] is False


def test_k1_verdict_handles_nan_sharpe_as_a_fail() -> None:
    net10 = {"anchor": {"sharpe": float("nan")}, "stress": {"sharpe": 0.9}}
    net20 = {"anchor": {"cagr": 0.10}, "stress": {"cagr": 0.05}}
    verdict = batch3.k1_verdict(net10, net20)
    assert verdict["pass"] is False
