from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260929_81_ipo_aftermarket as m  # noqa: E402


def _cal(start="2024-01-02", n=60):
    return pd.bdate_range(start, periods=n)


def test_qp_index_is_first_session_on_or_after_26_calendar_days():
    dates = _cal("2024-01-02", 60)  # Tue 2024-01-02 first trading day (index 0)
    # 2024-01-02 + 26 days = 2024-01-28 (Sunday) -> next session Monday 2024-01-29
    q = m.qp_index(dates, 0)
    assert dates[q] == pd.Timestamp("2024-01-29")
    # target lands on a trading day: 2024-01-03 + 26 = 2024-01-29 (Monday) -> that day itself
    q2 = m.qp_index(dates, 1)
    assert dates[q2] == pd.Timestamp("2024-01-29")
    # 25 calendar days is NOT enough (day 25 = 2024-01-27 Saturday would roll to same Monday,
    # but a Friday first session: 2024-01-05 + 26 = 2024-01-31)
    q3 = m.qp_index(dates, 3)
    assert dates[q3] == pd.Timestamp("2024-01-31")


def test_qp_index_past_end_returns_minus_one():
    dates = _cal("2024-01-02", 10)
    assert m.qp_index(dates, 0) == -1


def test_d10_uses_eleven_calendar_days():
    dates = _cal("2024-01-02", 30)
    q10 = m.qp_index(dates, 0, m.D10_CALENDAR_DAYS)
    assert dates[q10] == pd.Timestamp("2024-01-15")  # 2024-01-13 is Saturday -> Monday 15th


def test_window_returns_entry_open_to_exit_close_and_missing():
    o = np.array([[10.0, 11.0, 12.0, 13.0], [5.0, np.nan, 6.0, 7.0]])
    c = np.array([[10.5, 11.5, 12.5, 13.5], [5.5, 5.6, 6.6, 7.7]])
    out = m.window_returns(o, c, np.array([1, 1]), np.array([3, 3]))
    assert np.isclose(out[0], 13.5 / 11.0 - 1.0)
    assert np.isnan(out[1])  # entry open missing
    beyond = m.window_returns(o, c, np.array([1, 1]), np.array([4, 3]))
    assert np.isnan(beyond[0])


def test_bench_window_returns_equal_weight():
    bo = np.array([[100.0, 100.0, 100.0], [50.0, 50.0, 50.0]])
    bc = np.array([[101.0, 102.0, 110.0], [50.0, 51.0, 55.0]])
    out = m.bench_window_returns(bo, bc, np.array([0]), np.array([2]))
    assert np.isclose(out[0], 0.5 * (0.10) + 0.5 * (0.10))


def test_calendar_days_between():
    dates = pd.DatetimeIndex(["2024-01-05", "2024-01-08", "2024-01-09"])
    out = m.calendar_days_between(dates, np.array([0]), np.array([2]))
    assert out[0] == 4.0


def test_tier_bps_and_borrow():
    assert m.tier_bps(10) == 3.0
    assert m.tier_bps(500) == 3.0
    assert m.tier_bps(501) == 6.0
    assert m.tier_bps(1500) == 12.0
    assert m.tier_bps(1501) == 25.0
    assert m.tier_bps(float("nan")) == 25.0
    assert m.borrow_rate(1500) == 0.03
    assert m.borrow_rate(1501) == 0.25
    assert m.borrow_rate(float("nan")) == 0.25


def test_clustered_mean_t_matches_manual():
    v = np.array([1.0, 1.0, 3.0, 3.0])
    c = np.array([0, 0, 1, 1])
    res = m.clustered_mean_t(v, c)
    assert res["n"] == 4 and res["n_clusters"] == 2
    assert np.isclose(res["mean"], 2.0)
    # cluster sums of deviations: -2, +2 -> se = sqrt(8)/4 * sqrt(2/1) = 1.0
    assert np.isclose(res["t"], 2.0)


def test_leave_out_top_winners():
    v = np.array([0.5, 0.4, 0.3, 0.1, -0.1])
    assert np.isclose(m.leave_out_top_winners(v, 3), 0.0)
    assert m.leave_out_top_winners(np.array([1.0, 2.0]), 3) is None
