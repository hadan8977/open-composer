from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "wikipedia_pageview_ic",
    Path(__file__).resolve().parents[1] / "scripts" / "wikipedia_pageview_ic.py",
)
assert _SPEC and _SPEC.loader
ic = importlib.util.module_from_spec(_SPEC)
sys.modules["wikipedia_pageview_ic"] = ic
_SPEC.loader.exec_module(ic)


def test_vc7_28_formula_and_validity() -> None:
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    views = pd.DataFrame({"A": 100.0, "LOW": 5.0}, index=idx)
    views.loc[idx[50:57], "A"] = 300.0  # 7-day surge
    sig = ic.vc7_28(views)
    d = idx[56]
    expected = np.log((7 * 300.0 + 1) / (7 * 100.0 + 1))
    assert abs(sig.loc[d, "A"] - expected) < 1e-12
    assert sig["LOW"].isna().all()  # prior-28d mean below 20 views/day
    assert sig["A"].iloc[:34].isna().all()  # not enough history


def test_signal_uses_no_future_day() -> None:
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    views = pd.DataFrame({"A": 100.0}, index=idx)
    base = ic.vc7_28(views)
    views2 = views.copy()
    views2.iloc[50] = 1e6  # future spike must not change earlier values
    changed = ic.vc7_28(views2)
    assert base.iloc[:50].equals(changed.iloc[:50]) or np.allclose(
        base.iloc[:50].to_numpy(), changed.iloc[:50].to_numpy(), equal_nan=True
    )


def test_drop_list_flags_rename_break() -> None:
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    views = pd.DataFrame({"OK": 100.0, "BROKEN": 100.0}, index=idx)
    views.loc[idx[150:], "BROKEN"] = 3.0
    dropped = ic.drop_list(views)
    assert "BROKEN" in dropped and "OK" not in dropped
    assert dropped["BROKEN"]["min_ratio_28d_mean_vs_90d_earlier"] < 0.1


def test_nw_t_matches_iid_t_for_white_noise_and_grows_with_mean() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(0.0, 1.0, 4000)
    assert abs(ic.nw_t(x)) < 4
    shifted = x + 0.2
    assert ic.nw_t(shifted) > 6
    assert np.isnan(ic.nw_t(np.array([1.0, 2.0])))


def test_rank_ic_rows_perfect_and_masking() -> None:
    rng = np.random.default_rng(1)
    exc = rng.normal(size=(6, 150))
    sig = exc * 3.0 + 1.0
    out = ic.rank_ic_rows(sig, exc)
    assert np.allclose(out, 1.0)
    sig2 = -sig
    assert np.allclose(ic.rank_ic_rows(sig2, exc), -1.0)
    sig3 = sig.copy()
    sig3[0, 60:] = np.nan  # only 60 valid names in row 0 -> NaN
    res = ic.rank_ic_rows(sig3, exc)
    assert np.isnan(res[0]) and np.allclose(res[1:], 1.0)


def test_formation_frame_uses_next_open_and_lag() -> None:
    dates = pd.bdate_range("2024-01-02", periods=30)
    open_ = np.tile(np.arange(30, dtype=float)[:, None] + 100.0, (1, 3))
    open_[:, 2] = 100.0  # column 2 = "SPY" flat
    t, exc = ic.formation_frame(dates, open_, spy_col=2, offset=1, lag=0)
    assert t[0] == 1
    # fill at open[t+1]=102, exit at open[t+6]=107 -> return 107/102-1, SPY flat
    assert abs(exc[0, 0] - (107 / 102 - 1)) < 1e-12
    t1, exc1 = ic.formation_frame(dates, open_, spy_col=2, offset=1, lag=1)
    assert abs(exc1[0, 0] - (108 / 103 - 1)) < 1e-12
    assert t1[0] == 1
    assert (t + 6 < len(dates)).all()


def test_gate_requires_all_three_conditions() -> None:
    def mk(ic1, ic2, t2):
        return {
            "seg_2016_07_to_2023_12": {"ic_mean_median_offset": ic1, "nw_t_median_offset": 1.0},
            "seg_2024_01_08_onward": {"ic_mean_median_offset": ic2, "nw_t_median_offset": t2},
        }

    assert ic.gate(mk(0.01, 0.02, 3.0), 0.01)["pass"]
    assert not ic.gate(mk(-0.01, 0.02, 3.0), 0.01)["pass"]
    assert not ic.gate(mk(0.01, 0.02, 2.4), 0.01)["pass"]
    assert not ic.gate(mk(0.01, 0.02, 3.0), 0.03)["pass"]
    assert not ic.gate(mk(0.01, -0.02, -3.0), 0.01)["pass"]


def test_ic_for_recovers_planted_signal_and_placebo_kills_it() -> None:
    rng = np.random.default_rng(2)
    dates = pd.bdate_range("2016-08-01", "2025-06-30")
    T, N = len(dates), 150
    ret_w = rng.normal(0, 0.02, size=(T, N))
    open_ = 100 * np.cumprod(1 + np.hstack([ret_w, rng.normal(0, 0.005, size=(T, 1))]), axis=0)
    # plant: signal at t equals the excess return over the following window (entry t+1)
    sig = np.full((T, N), np.nan)
    for t in range(T - 6):
        with np.errstate(invalid="ignore"):
            sig[t] = open_[t + 6, :N] / open_[t + 1, :N] - 1 + rng.normal(0, 0.05, N)
    per = ic.ic_for(dates, open_, N, sig, list(range(N)), lag=0)
    med = ic.median_over_offsets(per)
    assert med["seg_2024_01_08_onward"]["ic_mean_median_offset"] > 0.2
    perm = rng.permutation(N)
    med_p = ic.median_over_offsets(ic.ic_for(dates, open_, N, sig, list(range(N)), 0, perm))
    assert abs(med_p["seg_2024_01_08_onward"]["ic_mean_median_offset"]) < 0.05
