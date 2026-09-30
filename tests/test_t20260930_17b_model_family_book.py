"""Pure-function tests for scripts/run_t20260930_17b_model_family_book.py."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from scripts import run_t20260930_17b_model_family_book as s


def test_verdict_three_inputs_plus_refuted() -> None:
    assert s.verdict(False, True, True) == "parity_failed"
    assert s.verdict(True, True, False) == "pass_pending_spreads"  # K1 only
    assert s.verdict(True, False, True) == "pass_pending_spreads"  # K2 only
    assert s.verdict(True, False, False) == "refuted"


def test_k1_pass_boundaries() -> None:
    assert s.k1_pass(0.65, 1.19, 0.01, 0.01) is True
    assert s.k1_pass(0.6499, 1.19, 0.01, 0.01) is False
    assert s.k1_pass(0.65, 1.1899, 0.01, 0.01) is False
    # annualised return exactly zero at 20 bp is not > 0
    assert s.k1_pass(0.65, 1.19, 0.0, 0.01) is False
    assert s.k1_pass(0.65, 1.19, 0.01, 0.0) is False
    assert s.k1_pass(float("nan"), 1.19, 0.01, 0.01) is False


def test_k2_pass_needs_both_windows() -> None:
    assert s.k2_pass(0.05, 0.05) is True
    assert s.k2_pass(0.05, 0.0499) is False
    assert s.k2_pass(float("nan"), 0.2) is False


def test_parity_rankic_tolerance() -> None:
    diff, ok = s.parity_rankic_ok(0.0531, 0.0530)
    assert ok is True and diff == pytest.approx(0.0001)
    assert s.parity_rankic_ok(0.0551, 0.0530)[1] is False
    assert s.parity_rankic_ok(0.0549, 0.0530)[1] is True
    assert s.parity_rankic_ok(None, 0.05) == (None, False)


def test_parity_book_tolerance() -> None:
    assert s.parity_book_ok(0.462, 0.327) is True
    assert s.parity_book_ok(0.52, 0.327) is False
    assert s.parity_book_ok(0.462, 0.275) is False
    assert s.parity_book_ok(float("nan"), 0.327) is False


def test_placebo_panel_keys_assertion() -> None:
    a = pd.DataFrame({"trade_date": pd.to_datetime(["2020-01-02"] * 2), "symbol": ["A", "B"]})
    same = a.iloc[::-1].reset_index(drop=True)
    s.assert_same_panel_keys({"x": a, "y": same})
    other = pd.DataFrame({"trade_date": pd.to_datetime(["2020-01-02"] * 2), "symbol": ["A", "C"]})
    with pytest.raises(AssertionError):
        s.assert_same_panel_keys({"x": a, "y": other})
    shorter = a.iloc[:1]
    with pytest.raises(AssertionError):
        s.assert_same_panel_keys({"x": a, "y": shorter})


def test_test_quarter_days_covers_whole_quarter() -> None:
    calendar = pd.bdate_range("2020-01-01", "2020-12-31")
    # test formation date late in Q2: whole of Q2 is covered, nothing else
    days = s.test_quarter_days(calendar, [pd.Timestamp("2020-06-30")])
    assert days[0] == pd.Timestamp("2020-04-01")
    assert days[-1] == pd.Timestamp("2020-06-30")
    assert all(d.quarter == 2 for d in days)


def test_parity_stage2_mean_window_and_win_rate() -> None:
    val_ic = pd.DataFrame(
        {
            "formation_date": pd.to_datetime(
                ["2016-04-29", "2016-05-02", "2020-01-31", "2023-09-01"]
            ),
            "rho": [0.9, 0.02, 0.04, 0.9],
        }
    )
    mean, n = s.parity_stage2_mean(val_ic)
    assert n == 2 and mean == pytest.approx(0.03)
    assert s.win_rate(1.0, [0.5, 1.5, float("nan"), 0.9]) == pytest.approx(2 / 3)
    assert math.isnan(s.win_rate(float("nan"), [0.5]))


def test_modal_cost_from_ledger_sums_exact_job() -> None:
    lines = [
        json.dumps({"job": "t20260930-19-real", "actual_cost_usd_estimate": 0.5}),
        json.dumps({"job": "t20260930-19-real2", "actual_cost_usd_estimate": 9.0}),
        json.dumps({"job": "t20260930-19-real", "actual_cost_usd_estimate": 0.25}),
        "",
    ]
    assert s.modal_cost_from_ledger(lines, "t20260930-19-real") == pytest.approx(0.75)
    assert s.modal_cost_from_ledger(lines, "missing") is None
