# ruff: noqa: E501
"""Evaluation helpers: Newey-West t, window metrics, K1 logic, placebo permutation, K2 via screen_lane."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import evaluate as ev

ROOT = Path(__file__).resolve().parents[1]


def test_newey_west_t_matches_iid_t_for_white_noise_and_grows_for_ar1() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(0.001, 0.01, 4000)
    t_nw = ev.newey_west_t(x)
    t_iid = x.mean() / (x.std(ddof=0) / np.sqrt(len(x)))
    assert abs(t_nw - t_iid) < 0.3
    # positive autocorrelation inflates the long-run variance -> smaller t than iid
    e = rng.normal(0, 0.01, 4000)
    ar = np.zeros(4000)
    for i in range(1, 4000):
        ar[i] = 0.5 * ar[i - 1] + e[i]
    ar += 0.0005
    assert ev.newey_west_t(ar) < ar.mean() / (ar.std(ddof=0) / np.sqrt(len(ar)))


def test_window_metrics_hand_values() -> None:
    idx = pd.bdate_range("2024-01-08", periods=100)
    rng = np.random.default_rng(1)
    spy = pd.Series(rng.normal(0.0004, 0.01, 100), index=idx)
    net = 0.5 * spy + 0.0002
    rf = pd.Series(0.0001, index=idx)
    m = ev.window_metrics(net, rf, spy, ("2024-01-08", "2026-09-17"))
    ex = net - rf
    assert m["sharpe"] == pytest.approx(ex.mean() / ex.std(ddof=1) * np.sqrt(252))
    assert m["ann_excess_return"] == pytest.approx(ex.mean() * 252)
    assert m["beta_spy"] == pytest.approx(0.5)
    assert m["corr_spy"] == pytest.approx(1.0)
    assert m["max_dd"] <= 0


def test_k1_check_parts() -> None:
    ok = {
        "anchor": {"sharpe": 1.3, "ann_excess_return": 0.1},
        "stress": {"sharpe": 0.7, "ann_excess_return": 0.05},
    }
    bad20 = {"anchor": {"ann_excess_return": -0.01}, "stress": {"ann_excess_return": 0.01}}
    good20 = {"anchor": {"ann_excess_return": 0.03}, "stress": {"ann_excess_return": 0.01}}
    assert ev.k1_check(ok, good20)["pass"] is True
    r = ev.k1_check(ok, bad20)
    assert r["pass"] is False and r["parts"]["anchor_excess_positive_2x_cost"] is False
    low = {"anchor": {"sharpe": 1.0}, "stress": {"sharpe": 0.7}}
    assert ev.k1_check(low, good20)["parts"]["anchor_sharpe_ge_1.19"] is False


def test_permute_within_date_keeps_nan_and_row_values() -> None:
    rng = np.random.default_rng(2)
    a = pd.DataFrame(rng.normal(size=(30, 40)), index=pd.bdate_range("2024-01-02", periods=30))
    a.iloc[3, 5] = np.nan
    a.iloc[7, :10] = np.nan
    p = ev.permute_within_date(a, seed=5)
    assert p.isna().equals(a.isna())
    for i in range(30):
        assert np.allclose(np.sort(p.iloc[i].dropna()), np.sort(a.iloc[i].dropna()))
    assert not np.allclose(p.fillna(0).to_numpy(), a.fillna(0).to_numpy())
    # deterministic per seed, different across seeds
    assert p.equals(ev.permute_within_date(a, seed=5))
    assert not p.equals(ev.permute_within_date(a, seed=6))
    # long form agrees on the invariants
    long = a.stack().rename("alpha").reset_index()
    long.columns = ["trade_date", "symbol", "alpha"]
    pl = ev.permute_within_date_long(long, "alpha", seed=1)
    assert (
        pl.groupby("trade_date")["alpha"]
        .apply(lambda s: np.sort(s.to_numpy()).sum())
        .round(9)
        .equals(
            long.groupby("trade_date")["alpha"]
            .apply(lambda s: np.sort(s.to_numpy()).sum())
            .round(9)
        )
    )


def test_deflated_sharpe_wrapper_runs() -> None:
    idx = pd.bdate_range("2024-01-08", periods=400)
    rng = np.random.default_rng(3)
    net = pd.Series(rng.normal(0.0008, 0.005, 400), index=idx)
    rf = pd.Series(0.0001, index=idx)
    p = ev.deflated_sharpe(net, rf, ("2024-01-08", "2026-09-17"))
    assert p is not None and 0.0 <= p <= 1.0


HAVE_SIP = (ROOT / "data/sip/daily").exists()


@pytest.mark.skipif(not HAVE_SIP, reason="SIP daily not available")
def test_k2_edges_call_screen_lane_and_flag_thresholds() -> None:
    ctx = ev.load_s3_context()
    # a candidate equal to S3 itself adds no diversification: edge near 0, never >= 0.05
    k2 = ev.k2_edges(ctx.s3_ret10, ctx)
    assert set(k2["edge"]) == {"stress", "anchor"}
    assert all(abs(v) < 0.05 for v in k2["edge"].values())
    assert k2["pass_0.05"] is False and k2["pass_0.10"] is False
    # an uncorrelated positive-Sharpe candidate lifts the combination
    idx = ctx.s3_ret10.index
    rng = np.random.default_rng(4)
    cand = pd.Series(
        ctx.rf.reindex(idx).fillna(0.0).to_numpy() + rng.normal(0.0006, 0.006, len(idx)), index=idx
    )
    k2b = ev.k2_edges(cand, ctx)
    assert k2b["edge"]["anchor"] > 0.05


@pytest.mark.skipif(not HAVE_SIP, reason="SIP daily not available")
def test_session_convention_guard_rejects_a_series_shifted_by_one_session() -> None:
    ctx = ev.load_s3_context()
    ev.assert_session_convention(ctx.s3_ret10, ctx)  # S3 against itself is fine
    shifted = ctx.s3_ret10.shift(1).fillna(0.0)  # the h20260929_12 failure mode
    with pytest.raises(ValueError, match="one session off"):
        ev.assert_session_convention(shifted, ctx)
