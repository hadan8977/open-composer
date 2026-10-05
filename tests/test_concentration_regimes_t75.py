"""Small synthetic-data tests for scripts/concentration_regimes_t75.py (T-20261004-75)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import concentration_regimes_t75 as t75  # noqa: E402


def _idx(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def test_ols_nw_recovers_betas_and_r2():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(2000, 2))
    y = 0.001 + 1.5 * x[:, 0] - 0.5 * x[:, 1] + rng.normal(scale=0.1, size=2000)
    out = t75.ols_nw(y, x)
    assert abs(out["beta"][0] - 1.5) < 0.02
    assert abs(out["beta"][1] + 0.5) < 0.02
    assert out["r2"] > 0.98
    assert abs(out["t"][0]) > 50


def test_orthogonalize_is_uncorrelated_with_regressor():
    rng = np.random.default_rng(1)
    idx = _idx(500)
    spy = pd.Series(rng.normal(size=500), index=idx)
    smh = 1.3 * spy + pd.Series(rng.normal(size=500), index=idx)
    res = t75.orthogonalize(smh, spy)
    assert abs(np.corrcoef(res, spy)[0, 1]) < 1e-10
    assert abs(res.mean()) < 1e-10


def test_exposure_regression_loads_on_smh_orth_only_for_semis_book():
    rng = np.random.default_rng(2)
    idx = _idx(900)
    spy = pd.Series(rng.normal(scale=0.01, size=900), index=idx)
    qqq = 1.1 * spy + pd.Series(rng.normal(scale=0.003, size=900), index=idx)
    smh = 1.4 * spy + pd.Series(rng.normal(scale=0.01, size=900), index=idx)
    smh_o = t75.orthogonalize(smh, spy)
    book = 0.5 * spy + 0.8 * smh_o + pd.Series(rng.normal(scale=0.001, size=900), index=idx)
    out = t75.exposure_regression(book, spy, qqq, smh, (str(idx[0].date()), str(idx[-1].date())))
    assert out["names"][2] == "SMH_orth_to_SPY"
    assert abs(out["beta"][2] - 0.8) < 0.05
    assert out["r2"] > 0.9


def test_state_labels_use_previous_close_and_flag_small_cells():
    idx = _idx(400)
    spy = pd.Series(np.linspace(100, 200, 400), index=idx)
    smh = spy * 2.0
    vix = pd.Series(12.0, index=idx)
    vix.iloc[300:] = 30.0
    lab = t75.state_labels(spy, smh, vix)
    assert lab["spy_200d"].iloc[:200].isna().all()  # no SMA yet, then shift(1)
    assert lab["vix"].iloc[300] == "<15"  # day 300 sees the previous close (12)
    assert lab["vix"].iloc[301] == ">25"
    ret = pd.Series(0.001, index=idx)
    tab = t75.state_table(
        ret, pd.Series(0.0, index=idx), lab, (str(idx[0].date()), str(idx[-1].date()))
    )
    assert tab["vix"][">25"]["n"] == 99
    assert tab["vix"][">25"]["small_sample"] is False
    tab2 = t75.state_table(
        ret, pd.Series(0.0, index=idx), lab, (str(idx[0].date()), str(idx[320].date()))
    )
    assert tab2["vix"][">25"]["small_sample"] is True


def test_segment_resolution_and_stats():
    idx = pd.bdate_range("2018-08-01", "2019-02-28")
    px = pd.Series(100.0, index=idx)
    peak, trough = pd.Timestamp("2018-09-20"), pd.Timestamp("2018-12-24")
    px.loc[peak] = 120.0
    px.loc[trough] = 80.0
    segs = [s for s in t75.resolve_segments_for(px, [t75.SEGMENTS[0]])]
    assert segs[0]["spy_peak_close_date"] == "2018-09-20"
    assert segs[0]["spy_trough_close_date"] == "2018-12-24"
    ret = px.pct_change()
    st = t75.segment_stats(ret, ret, segs[0])
    assert abs(st["return"] - (80.0 / 120.0 - 1.0)) < 1e-12
    assert st["max_dd"] <= st["return"] + 1e-12


def test_contributions_reproduce_salvage_simulate_and_semis_decomposition():
    import run_h20260922_05_salvage as salvage

    rng = np.random.default_rng(3)
    idx = _idx(60)
    cols = ["BIL", "SHY", "SMH", "XLK", "TQQQ"]
    cash = salvage.CASH
    lo = pd.DataFrame(rng.normal(0, 0.004, (60, 5)), index=idx, columns=cols)
    lc = pd.DataFrame(rng.normal(0, 0.01, (60, 5)), index=idx, columns=cols)
    w = pd.DataFrame(0.0, index=idx, columns=cols)
    w[cash] = 1.0
    w.iloc[10:30] = 0.0
    w.loc[w.index[10:30], "SMH"] = 0.5
    w.loc[w.index[10:30], "XLK"] = 0.5
    w.loc[w.index[30:], "TQQQ"] = 1.0
    w.loc[w.index[30:], cash] = 0.0
    scale = np.where(np.arange(60) % 7 == 0, 0.6, 1.0)
    ret, _ = salvage.simulate(w, lo, lc, scale, 10.0)
    contrib, cost, held = t75.contributions(w, lo, lc, scale, 10.0, cash)
    assert np.allclose(contrib.sum(axis=1) - cost, ret.to_numpy(), atol=1e-12)
    dec = t75.semis_decomposition(contrib, cost, held, lo["SMH"], lc["SMH"], 0.4)
    assert np.allclose(dec["pure_semis"], contrib["SMH"])
    # embedded part is f * w * SMH legs for XLK only (no TECL column here)
    wx = held["XLK"]
    expect = 0.4 * (wx.shift(1).fillna(0.0) * lo["SMH"] + wx * lc["SMH"])
    assert np.allclose(dec["lookthrough"], expect)
    share = t75.semis_share(dec, (str(idx[0].date()), str(idx[-1].date())))
    assert share["n"] == 60


def test_semis_share_undefined_when_gross_nonpositive():
    idx = _idx(5)
    dec = pd.DataFrame(
        {
            "gross": -0.01,
            "cost": 0.0,
            "pure_semis": 0.0,
            "lookthrough": 0.0,
            "exp_pure": 0.0,
            "exp_look": 0.0,
        },
        index=idx,
    )
    out = t75.semis_share(dec, (str(idx[0].date()), str(idx[-1].date())))
    assert out["share_pure"] is None and out["over_half_theme_pure_plus_lookthrough"] is None


def test_max_drawdown_and_sharpe():
    r = pd.Series([0.1, -0.5, 0.2])
    assert abs(t75.max_drawdown(r) - (-0.5)) < 1e-12
    assert t75.sharpe_excess(pd.Series([0.01, 0.01, 0.01]), pd.Series([0.0, 0.0, 0.0])) is None
