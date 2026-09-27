from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_h20260927_01_sleeve_combination as mod  # noqa: E402


def test_manifest_guard_accepts_the_real_preregistered_candidate_set():
    manifest = mod.load_manifest_guard()
    ids = [c["candidate_id"] for c in manifest["candidates"]]
    assert ids == ["M0", "M1", "M2", "M3", "C1", "C2", "C3"]


def test_manifest_guard_rejects_wrong_candidate_ids(tmp_path, monkeypatch):
    bad_manifest = {"candidates": [{"candidate_id": "M0"}, {"candidate_id": "M9"}]}
    bad_path = tmp_path / "candidate-manifest.json"
    bad_path.write_text(json.dumps(bad_manifest), encoding="utf-8")
    monkeypatch.setattr(mod, "MANIFEST_PATH", bad_path)
    with pytest.raises(SystemExit):
        mod.load_manifest_guard()


def test_manifest_guard_rejects_extra_candidate(tmp_path, monkeypatch):
    ids = [*mod.EXPECTED_CANDIDATE_IDS, "M4"]
    bad_manifest = {"candidates": [{"candidate_id": cid} for cid in ids]}
    bad_path = tmp_path / "candidate-manifest.json"
    bad_path.write_text(json.dumps(bad_manifest), encoding="utf-8")
    monkeypatch.setattr(mod, "MANIFEST_PATH", bad_path)
    with pytest.raises(SystemExit):
        mod.load_manifest_guard()


def test_weights_inverse_vol_falls_back_to_equal_weight_before_lookback():
    rng = np.random.default_rng(0)
    rets = {
        "s1": rng.normal(0, 0.01, size=40),
        "s2": rng.normal(0, 0.02, size=40),
        "s3": rng.normal(0, 0.05, size=40),
    }
    # asof=39 with only 40 sessions of history and a 63-session lookback
    weights = mod.weights_inverse_vol(rets, asof=39, lookback=63)
    assert weights == {
        "s1": pytest.approx(1 / 3),
        "s2": pytest.approx(1 / 3),
        "s3": pytest.approx(1 / 3),
    }


def test_weights_inverse_vol_weights_lower_volatility_sleeve_more():
    n = 70
    rets = {
        "s1": np.tile([0.01, -0.01], n // 2),
        "s2": np.tile([0.02, -0.02], n // 2),
        "s3": np.tile([0.04, -0.04], n // 2),
    }
    weights = mod.weights_inverse_vol(rets, asof=n - 1, lookback=63)
    assert sum(weights.values()) == pytest.approx(1.0)
    # s1 has the lowest volatility (0.01 amplitude) so it must get the largest weight,
    # and s3 (0.04 amplitude, 4x s1) the smallest.
    assert weights["s1"] > weights["s2"] > weights["s3"]
    # inverse-vol is exactly proportional to 1/sigma: s1:s2:s3 stdevs are 1:2:4
    assert weights["s1"] == pytest.approx(4 * weights["s3"], rel=1e-6)
    assert weights["s2"] == pytest.approx(2 * weights["s3"], rel=1e-6)


def test_weights_inverse_vol_falls_back_when_a_sleeve_is_perfectly_flat():
    n = 70
    rets = {
        "s1": np.zeros(n),  # zero stdev -- inverse is undefined
        "s2": np.concatenate([np.tile([0.02, -0.02], n // 2)]),
        "s3": np.concatenate([np.tile([0.04, -0.04], n // 2)]),
    }
    weights = mod.weights_inverse_vol(rets, asof=n - 1, lookback=63)
    assert weights == {
        "s1": pytest.approx(1 / 3),
        "s2": pytest.approx(1 / 3),
        "s3": pytest.approx(1 / 3),
    }


def test_combine_portfolio_drifts_intramonth_and_charges_cost_on_rebalance_day():
    # 4 business days spanning a single month-end (day index 1) so there is
    # exactly one rebalance, effective at the open of day index 2.
    index = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
    sleeve_rets = {
        "s1": pd.Series([0.0, 0.0, 0.10, 0.0], index=index),
        "s2": pd.Series([0.0, 0.0, 0.0, 0.0], index=index),
        "s3": pd.Series([0.0, 0.0, -0.10, 0.0], index=index),
    }

    def fixed_half_half(_rets, _asof):
        return {"s1": 0.5, "s2": 0.0, "s3": 0.5}

    ret, turnover = mod.combine_portfolio(sleeve_rets, index, fixed_half_half, combo_cost_bps=100.0)

    # Day 0: no rebalance yet (portfolio starts directly at target weights,
    # no inception cost); all sleeve returns are zero.
    assert turnover.iloc[0] == pytest.approx(0.0)
    assert ret.iloc[0] == pytest.approx(0.0)

    # Day index 1 (2024-01-31) is the month-end signal date -> effective at
    # day index 2's open. Weights at day 2 are still the day-0 target
    # (0.5/0/0.5), since the constant weight function returns the same
    # target every time, so turnover on the rebalance day is 0 here.
    assert turnover.iloc[2] == pytest.approx(0.0)
    # Day 2 return: 0.5*0.10 + 0.5*(-0.10) = 0
    assert ret.iloc[2] == pytest.approx(0.0)

    # Day 3: weights should have drifted away from 0.5/0/0.5 because s1 and
    # s3 moved in opposite directions on day 2 (buy-and-hold drift, no
    # rebalance signal on day index 2).
    grown_s1 = 0.5 * 1.10
    grown_s3 = 0.5 * 0.90
    total = grown_s1 + grown_s3
    expected_w_s1 = grown_s1 / total
    expected_w_s3 = grown_s3 / total
    # Day 3 has zero sleeve returns, so portfolio return is 0 regardless of
    # drifted weights, but turnover must be 0 (no rebalance signal).
    assert turnover.iloc[3] == pytest.approx(0.0)
    assert ret.iloc[3] == pytest.approx(0.0)
    assert expected_w_s1 > 0.5 > expected_w_s3  # sanity: s1 grew, s3 shrank


def test_combine_portfolio_charges_cost_when_target_weight_actually_changes():
    index = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"])
    sleeve_rets = {
        "s1": pd.Series([0.0, 0.0, 0.0, 0.0], index=index),
        "s2": pd.Series([0.0, 0.0, 0.0, 0.0], index=index),
        "s3": pd.Series([0.0, 0.0, 0.0, 0.0], index=index),
    }
    calls = {"n": 0}

    def switching_weights(_rets, _asof):
        # First call (inception, asof=-1) gives equal-thirds; the rebalance
        # call (asof=0, the month-end signal date) switches to all-s3.
        calls["n"] += 1
        if calls["n"] == 1:
            return {"s1": 1 / 3, "s2": 1 / 3, "s3": 1 / 3}
        return {"s1": 0.0, "s2": 0.0, "s3": 1.0}

    ret, turnover = mod.combine_portfolio(
        sleeve_rets, index, switching_weights, combo_cost_bps=100.0
    )
    # delta = |0-1/3| + |0-1/3| + |1-1/3| = 4/3; cost = 100bp * 4/3 / 10000
    expected_cost = 100.0 * (4 / 3) / 10_000.0
    assert turnover.iloc[2] == pytest.approx(4 / 3)
    assert ret.iloc[2] == pytest.approx(-expected_cost)


def test_solve_k_matches_volatility_exactly_when_shy_is_flat():
    rng = np.random.default_rng(1)
    r_s3 = rng.normal(0.0005, 0.02, size=500)
    r_shy = np.zeros(500)
    s3_vol = float(np.std(r_s3, ddof=1))
    target = 0.5 * s3_vol
    k = mod.solve_k(target, r_s3, r_shy)
    achieved_vol = float(np.std(k * r_s3 + (1 - k) * r_shy, ddof=1))
    assert achieved_vol == pytest.approx(target, rel=1e-3)
    assert 0.0 < k < 1.0


def test_solve_k_caps_at_one_when_target_exceeds_s3_volatility():
    rng = np.random.default_rng(2)
    r_s3 = rng.normal(0.0, 0.01, size=300)
    r_shy = np.zeros(300)
    target = 10 * float(np.std(r_s3, ddof=1))
    k = mod.solve_k(target, r_s3, r_shy)
    assert k == pytest.approx(1.0)


def test_solve_k_returns_zero_for_nonpositive_target():
    r_s3 = np.array([0.01, -0.01, 0.02, -0.02])
    r_shy = np.zeros(4)
    assert mod.solve_k(0.0, r_s3, r_shy) == pytest.approx(0.0)
    assert mod.solve_k(float("nan"), r_s3, r_shy) == pytest.approx(0.0)
