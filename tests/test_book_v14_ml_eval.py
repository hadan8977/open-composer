"""Synthetic tests for scripts/book_v14_ml_eval.py (no market data)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import optimize as op
from scripts import book_v14_ml_eval as ev
from scripts import realism_ladder_book_ls as T25


@pytest.fixture()
def pred_path(tmp_path):
    d1, d2 = pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")
    rows = []
    for d, vals in ((d1, [0.3, -1.0, 2.0, np.nan, 0.5]), (d2, [1.0, 2.0, 3.0, 4.0, 5.0])):
        for s, v in zip(list("ABCDE"), vals, strict=True):
            rows.append({"trade_date": d, "symbol": s, "m0": v, "m2": v * 2.0})
    p = tmp_path / "pred.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def test_prediction_source_rank_normal_and_nan(pred_path):
    src = ev.PredictionSource(pred_path, "m0")
    universe = pd.Index(["A", "B", "C", "D", "E", "Z"])
    out = src(pd.Timestamp("2024-01-02"), None, universe)
    raw = pd.Series([0.3, -1.0, 2.0, np.nan, 0.5, np.nan], index=universe)
    pd.testing.assert_series_equal(out, op.rank_normal(raw))
    assert out[["D", "Z"]].isna().all()
    assert out.drop(["D", "Z"]).notna().all()
    assert abs(out.dropna().sum()) < 1e-12  # rank-normal scores are symmetric


def test_prediction_source_missing_date_is_nan_and_recorded(pred_path):
    src = ev.PredictionSource(pred_path, "m0")
    out = src(pd.Timestamp("2024-02-01"), None, pd.Index(["A", "B"]))
    assert out.isna().all()
    assert src.missing_dates == ["2024-02-01"]


def test_placebo_is_within_date_permutation_and_reproducible(pred_path):
    universe = pd.Index(list("ABCDE"))
    t = pd.Timestamp("2024-01-03")
    plain = ev.PredictionSource(pred_path, "m0")(t, None, universe)
    a = ev.PredictionSource(pred_path, "m0", placebo_seed=3)(t, None, universe)
    a2 = ev.PredictionSource(pred_path, "m0", placebo_seed=3)(t, None, universe)
    b = ev.PredictionSource(pred_path, "m0", placebo_seed=4)(t, None, universe)
    pd.testing.assert_series_equal(a, a2)
    assert sorted(a.round(12)) == sorted(plain.round(12))
    assert not np.allclose(a.to_numpy(), plain.to_numpy()) or not np.allclose(
        b.to_numpy(), plain.to_numpy()
    )
    assert not np.allclose(a.to_numpy(), b.to_numpy())


def test_restart_positions_equal_v12_calendar_after_start():
    dates = pd.bdate_range("2017-10-02", periods=700)
    last = len(dates) - 3
    start_v12 = int(dates.searchsorted(pd.Timestamp(T25.START)))
    for o in range(5):
        v12 = T25.decision_positions(len(dates), start_v12, last, T25.WEEK, o)
        mine = ev.restart_positions(dates, "2019-01-02", last, o)
        first = int(dates.searchsorted(pd.Timestamp("2019-01-02")))
        assert mine == [p for p in v12 if p >= first]
        assert mine and mine[0] >= first and all(p % 5 == o for p in mine)


def test_vol_matched_difference_zero_mean_when_candidate_is_double():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=300)
    base = pd.Series(rng.normal(0.0005, 0.01, 300), index=idx)
    d = ev.vol_matched_diff(2.0 * base, base)
    assert abs(d.mean()) < 1e-15 and d.abs().max() < 1e-15
    # an independent candidate at the same vol has a non-trivial difference
    other = pd.Series(rng.normal(0.0, 0.03, 300), index=idx)
    d2 = ev.vol_matched_diff(other, base)
    assert abs(d2.std(ddof=1) - np.sqrt(2) * base.std(ddof=1)) < 0.4 * base.std(ddof=1)
    assert ev.hac_t(d.to_numpy())["mean"] == pytest.approx(0.0, abs=1e-15)


def test_offsets_improved_counting_and_eligibility_and_selection():
    n, diffs = ev.count_offsets_improved([1.0, 0.9, 1.2, 1.1, 0.5], [0.9, 1.0, 1.0, 1.0, 0.5])
    assert n == 3
    assert diffs == pytest.approx([0.1, -0.1, 0.2, 0.1, 0.0])
    ok = {
        "recent": {"beta_ols": 0.1, "beta_dimson": -0.14},
        "stress_ml": {"beta_ols": 0.0, "beta_dimson": 0.1},
    }
    assert ev.eligibility(0.10, 0.12, 4, 5, ok, True)["all"]
    assert not ev.eligibility(0.0999, 0.12, 4, 5, ok, True)["E1"]
    assert not ev.eligibility(0.2, 0.2, 3, 5, ok, True)["E2"]
    bad = {**ok, "recent": {"beta_ols": 0.16, "beta_dimson": 0.0}}
    assert not ev.eligibility(0.2, 0.2, 5, 5, bad, True)["E4"]
    assert not ev.eligibility(0.2, 0.2, 5, 5, ok, False)["all"]
    rec = {"a": 1.50, "b": 1.505, "c": 1.2}
    stl = {"a": 0.7, "b": 0.6, "c": 0.9}
    assert ev.select_candidate(["a", "b", "c"], rec, stl) == "a"  # tie <= 0.01: higher stress
    assert ev.select_candidate(["b", "c"], rec, stl) == "b"
    assert ev.select_candidate([], rec, stl) is None


def test_run_tasks_pool_respects_expired_deadline_and_compare_identity():
    import time

    calls: list = []
    ev.run_tasks([("B0r", 0), ("m0", 1)], 2, None, time.time() - 1.0, lambda *a: calls.append(a))
    assert calls == []  # the deadline already passed: no pass started, no Context loaded

    idx = pd.bdate_range("2019-01-03", periods=10)
    a = pd.DataFrame(
        {
            c: np.linspace(0.0, 1.0, 10)
            for c in ("gross", "borrow", "hedge_size", "vix_scale", "spy", "turnover", "cost")
        },
        index=idx,
    )
    a["gross_exposure"] = 1.0
    a["net"] = a["gross"] - a["cost"] - a["borrow"]
    saved = a.drop(columns=["gross_exposure"]).copy()
    saved.loc[idx[0], "cost"] += 0.5  # the first decision date may differ
    saved.loc[idx[0], "turnover"] += 0.5
    saved.loc[idx[0], "net"] -= 0.5
    ok = ev.compare_identity(0, a, a.copy(), saved, None)
    assert ok["pass"] and ok["worst_b_vs_a"] == 0.0
    saved2 = saved.copy()
    saved2.loc[idx[4], "gross"] += 1e-9
    assert not ev.compare_identity(0, a, a.copy(), saved2, None)["check_a_vs_r6"]
