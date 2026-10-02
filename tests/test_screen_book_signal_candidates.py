"""Synthetic tests of the T-20261002-24 screen rules; no panel, prediction or feature data."""

from __future__ import annotations

import numpy as np
import pytest

from scripts import screen_book_signal_candidates as scr


def test_asof_latest_never_uses_a_later_row() -> None:
    # symbol 0 has rows on days 1, 3, 10 (the day-10 value is huge); symbol 1 only on day 8
    codes = np.array([0, 0, 0, 1])
    days = np.array([1, 3, 10, 8])
    vals = np.array([1.0, 3.0, 1e9, 8.0])
    q_codes = np.array([0, 0, 0, 0, 1, 1])
    q_days = np.array([0, 1, 5, 10, 7, 9])
    v, age = scr.asof_latest(codes, days, vals, q_codes, q_days)
    assert np.isnan(v[0]) and age[0] == -1  # before the first row
    assert v[1] == 1.0 and age[1] == 0
    assert v[2] == 3.0 and age[2] == 2  # latest row <= day 5 is day 3, not day 10
    assert v[3] == 1e9 and age[3] == 0  # day 10 allowed once the query reaches it
    assert np.isnan(v[4])  # symbol 1 first appears on day 8 (> 7)
    assert v[5] == 8.0 and age[5] == 1


def test_asof_latest_symbols_do_not_leak_into_each_other() -> None:
    codes = np.array([0, 2])
    days = np.array([1, 1])
    v, _ = scr.asof_latest(codes, days, np.array([5.0, 7.0]), np.array([1, 2]), np.array([9, 9]))
    assert np.isnan(v[0]) and v[1] == 7.0  # symbol 1 has no rows at all


def test_incremental_residual_is_orthogonal_and_keeps_only_the_new_part() -> None:
    rng = np.random.default_rng(0)
    n = 4000
    base = rng.normal(size=n)
    new = rng.normal(size=n)
    cand = 0.9 * base + 0.3 * new
    y = new + rng.normal(size=n) * 2.0  # y is related to the candidate only through `new`
    res = scr.incremental_residual(cand, base)
    ok = np.isfinite(res)
    assert ok.all()
    assert abs(np.corrcoef(res, base)[0, 1]) < 1e-9  # orthogonal to the base composite
    assert abs(res.mean()) < 1e-9
    # the residual keeps the part of the candidate that predicts y, the candidate as a whole has
    # a weaker rank IC against the base-dominated part
    ic_res, _ = scr.rank_ic(res, y)
    assert ic_res > 0.2
    # a candidate that is a monotone transform of the base composite leaves ~no residual
    res_same = scr.incremental_residual(base**3, base)
    assert res_same.std() < 0.1


def test_incremental_residual_handles_nan_rows() -> None:
    cand = np.array([1.0, np.nan, 3.0, 2.0, 5.0, 4.0])
    base = np.array([1.0, 2.0, np.nan, 2.0, 5.0, 3.5])
    res = scr.incremental_residual(cand, base)
    assert np.isnan(res[1]) and np.isnan(res[2])
    assert np.isfinite(res[[0, 3, 4, 5]]).all()


def test_score_ml_pv_averages_present_models_and_keeps_nan() -> None:
    preds = np.array(
        [
            [1.0, 1.0, 1.0],
            [2.0, 2.0, np.nan],
            [3.0, np.nan, np.nan],
            [np.nan, np.nan, np.nan],
        ]
    )
    s = scr.score_ml_pv(preds)
    assert np.isnan(s[3])  # missing everywhere stays NaN, not 0
    assert np.isfinite(s[:3]).all()
    assert s[0] < s[1] < s[2]


def test_score_alpha158_needs_enough_factors() -> None:
    v = np.arange(40, dtype=float).reshape(20, 2)
    s = scr.score_alpha158(v, min_factors=2)
    assert np.isfinite(s).all() and np.all(np.diff(s) > 0)
    v[0, 1] = np.nan
    s = scr.score_alpha158(v, min_factors=2)
    assert np.isnan(s[0]) and np.isfinite(s[1:]).all()


def test_near_high_uses_only_rows_up_to_the_date() -> None:
    close = np.full((300, 2), 10.0)
    close[260, 0] = 99.0  # a spike after p = 250 must not change the ratio at p
    close[250, 1] = 20.0
    r = scr.near_high_from_matrix(close, 250)
    assert r[0] == pytest.approx(1.0)
    assert r[1] == pytest.approx(1.0)
    close2 = close.copy()
    close2[100, 0] = 50.0  # inside the 252-session window ending at 250
    assert scr.near_high_from_matrix(close2, 250)[0] == pytest.approx(10.0 / 50.0)
    close3 = close.copy()
    close3[:, 1] = np.nan
    assert np.isnan(scr.near_high_from_matrix(close3, 250)[1])  # too few observations


def test_admission_rule_mechanics() -> None:
    def blk(t: float, mean: float = 0.01) -> dict:
        return {"t_nw2": t, "mean_ic": mean}

    good = {
        "ic": {"anchor": blk(3.0), "stress": blk(1.0)},
        "corr_m1": {"all": 0.2},
        "incremental": {"anchor": blk(2.5)},
    }
    a = scr.admission(good, 4, placebo_p95=1.8)
    assert a["status"] == "admitted" and a["failing"] == [] and a["bonferroni_z"] == 2.498
    bad = {
        "ic": {"anchor": blk(2.4), "stress": blk(-1.0, -0.01)},
        "corr_m1": {"all": 0.6},
        "incremental": {"anchor": blk(1.0)},
    }
    a = scr.admission(bad, 4, placebo_p95=3.0)
    assert a["status"] == "rejected" and len(a["failing"]) == 5
