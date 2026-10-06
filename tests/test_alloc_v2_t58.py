"""Synthetic-data tests for scripts/run_alloc_v2_t58.py (T-20261004-58)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_alloc_v2_t58 as m  # noqa: E402


def _rand_cov(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = rng.normal(size=(n, n))
    return a @ a.T + 0.5 * np.eye(n)


def test_risk_budget_solver_hits_budgets():
    for n, seed in ((4, 1), (6, 2)):
        cov = _rand_cov(n, seed)
        b = np.random.default_rng(seed + 10).dirichlet(np.ones(n))
        w = m.rb_weights(cov, b)
        assert abs(w.sum() - 1.0) < 1e-12
        assert np.all(w > 0)
        assert np.max(np.abs(m.risk_shares(w, cov) - b)) < 1e-8
        # ERC special case
        w_erc = m.rb_weights(cov, np.full(n, 1.0 / n))
        assert np.max(np.abs(m.risk_shares(w_erc, cov) - 1.0 / n)) < 1e-8


def test_erc_equal_weights_for_scaled_identity():
    cov = 0.0004 * np.eye(5)
    w = m.rb_weights(cov, np.full(5, 0.2))
    assert np.allclose(w, 0.2, atol=1e-9)


def test_cap2_returns_p0_or_exact_cap():
    cov = np.array([[0.04, 0.012], [0.012, 0.01]])
    p0 = np.array([0.642, 0.358])
    s = float(m.risk_shares(p0, cov)[0])
    assert s > 0.5
    # cap above the P0 share: unchanged
    assert np.array_equal(m.cap2_weights(cov, min(0.99, s + 0.01), p0), p0)
    # cap below: the S3 share is exactly c
    w = m.cap2_weights(cov, 0.5, p0)
    assert abs(float(m.risk_shares(w, cov)[0]) - 0.5) < 1e-8
    w = m.cap2_weights(cov, s - 0.05, p0)
    assert abs(float(m.risk_shares(w, cov)[0]) - (s - 0.05)) < 1e-8


def test_samevol_formula():
    rng = np.random.default_rng(3)
    n = 500
    rf = np.full(n, 0.0001)
    ex_p = rng.normal(0.0004, 0.01, n)
    # k = 1: raw excess Sharpe of R
    ex_r = ex_p.copy()
    x, k = m.samevol_x(ex_r, ex_p, rf)
    assert abs(k - 1.0) < 1e-12
    assert abs(m.sharpe(x) - m.sharpe(ex_r)) < 1e-12
    # k > 1 (R has half the volatility): debit spread subtracted, k scales
    ex_half = 0.5 * ex_p
    x2, k2 = m.samevol_x(ex_half, ex_p, rf)
    assert abs(k2 - 2.0) < 1e-12
    expected = 2.0 * ex_half - (m.DEBIT_D - rf)
    assert np.allclose(x2, expected)
    # k < 1 (R more volatile): scaled down, no debit term
    x3, k3 = m.samevol_x(2.0 * ex_p, ex_p, rf)
    assert abs(k3 - 0.5) < 1e-12
    assert np.allclose(x3, 0.5 * 2.0 * ex_p)


def _synthetic_ctx(n: int = 700, seed: int = 5) -> m.Ctx:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2016-01-04", periods=n)
    cols = {}
    for s in m.SLEEVES:
        cols[s] = rng.normal(0.0005, 0.01, n)
    panel = pd.DataFrame({f"sel__{s}": cols[s] for s in m.ETF}, index=idx)
    panel["F1"] = cols["F1"]
    panel["F2"] = cols["F2"]
    panel["CASH"] = 0.0001
    panel["G_F1"] = 1.2
    panel["G_F2"] = 1.1
    return m.Ctx(panel, "sel")


def test_margin_filter_flags_levered_3x_mix_and_passes_cash_mix():
    ctx = _synthetic_ctx()
    n = len(ctx.pidx)
    reb = np.zeros(n, dtype=bool)
    reb[0] = True
    # levered mix: k = 1.6 with S3 weight 1.0 -> maintenance 0.75 * 1.6 = 1.2 > 0.9
    h = np.zeros((n, 8))
    h[:, 2] = 1.6
    wt = h.copy()
    head_maint, head_init = m.margin_headroom(ctx, h, wt, reb)
    assert head_maint < 0 and head_init < 0
    # cash mix: 0.3 each in S1, S2, C2 and 0.1 S3 -> well inside
    h = np.zeros((n, 8))
    h[:, 0] = 0.3
    h[:, 1] = 0.3
    h[:, 3] = 0.3
    h[:, 2] = 0.1
    wt = h.copy()
    head_maint, head_init = m.margin_headroom(ctx, h, wt, reb)
    assert head_maint > 0 and head_init > 0


def test_mincap_drops_small_sleeve_and_resolves_on_rest():
    ctx = _synthetic_ctx()
    i = ctx.pos0 + 10
    # CAP2 with a very high cap -> P0 weights 0.642 / 0.358
    spec = m.rule_spec("T58_CAP2_0.80")
    w = m.solve_weights(ctx, spec, i)
    row = np.zeros(6)
    for name, x in w.items():
        row[m.SLEEVES.index(name)] = x
    # A = 20k, k = 1: S3 gets 12.8k (>=10k), C2 gets 7.2k (<10k) -> C2 dropped, S3 = 1.0
    out, dropped = m.apply_mincap(ctx, spec, row, i, 1.0, 20_000)
    assert dropped
    assert out[m.SLEEVES.index("C2")] == 0.0
    assert abs(out[m.SLEEVES.index("S3")] - 1.0) < 1e-12
    # A = 50k: nothing dropped, weights unchanged
    out2, dropped2 = m.apply_mincap(ctx, spec, row, i, 1.0, 50_000)
    assert not dropped2 and np.allclose(out2, row)
    # F sleeves need 250k: at 100k a F1/F2 weight is dropped for E6 ERC
    spec6 = m.rule_spec("T58_ERC_E6")
    w6 = m.solve_weights(ctx, spec6, i)
    row6 = np.zeros(6)
    for name, x in w6.items():
        row6[m.SLEEVES.index(name)] = x
    out6, dropped6 = m.apply_mincap(ctx, spec6, row6, i, 1.0, 100_000)
    assert dropped6
    assert out6[4] == 0.0 and out6[5] == 0.0
    assert abs(out6.sum() - 1.0) < 1e-12


def test_stationary_bootstrap_deterministic_and_mean_preserving():
    n, horizon, paths = 300, 126, 200
    a = m.stationary_bootstrap_indices(n, horizon, paths, 21, np.random.default_rng(7))
    b = m.stationary_bootstrap_indices(n, horizon, paths, 21, np.random.default_rng(7))
    assert np.array_equal(a, b)
    assert a.min() >= 0 and a.max() < n
    ex = np.random.default_rng(8).normal(0.001, 0.01, n)
    base = m.scenario_base(ex, 0.0007, 0.00012)
    assert abs(base.mean() - (0.0007 + 0.00012)) < 1e-12


def test_cap2_ex_ante_share_never_above_cap_on_synthetic_ctx():
    ctx = _synthetic_ctx()
    rows = m.rebal_positions(ctx, m.OFFS)
    for c in (0.8, 0.5):
        spec = m.rule_spec(f"T58_CAP2_{c:.2f}")
        _, rc = m.build_targets(ctx, spec, rows)
        assert np.nanmax(rc[:, 2]) <= c + 1e-6


def test_run_path_matches_dd30_path_static():
    rng = np.random.default_rng(11)
    n = 120
    idx = pd.bdate_range("2020-01-01", periods=n)
    rets = rng.normal(0.0004, 0.01, size=(n, 5))
    w = np.array([0.5, 0.3, 0.1, 0.1, 0.0, -0.0])
    full = np.column_stack([rets, np.full(n, m.dd30.DEBIT_RATE / 252.0)])
    mine, _, _ = m.run_path(np.tile(w, (n, 1)), full, m.dd30.rebalance_mask(idx, 3))
    ref = m.dd30.path(w, rets, idx, 3)
    assert np.max(np.abs(mine - ref.to_numpy())) < 1e-12


def test_decide_statuses():
    def d(**kw):
        base = {
            "blend_recent": 0.0,
            "blend_stress": 0.0,
            "median_recent": 0.0,
            "median_stress": 0.0,
            "offsets_positive_recent": 0,
            "placebo_quantile_recent": 0.5,
            "cost2x_delta_recent": 0.0,
            "six_segment_mean_change_pp": 0.0,
            "es975_stress_change": 0.01,
        }
        base.update(kw)
        return base

    deltas = {r: d() for r in m.RULES}
    assert m.decide(deltas, m.SMALL_RULES)["status"] == "keep_p0"
    deltas["T58_CAP2_0.70"] = d(blend_recent=-0.05, blend_stress=0.0, es975_stress_change=-0.001)
    deltas["T58_CAP2_0.50"] = d(
        blend_recent=-0.05, blend_stress=-0.01, six_segment_mean_change_pp=1.2
    )
    out = m.decide(deltas, m.SMALL_RULES)
    assert out["status"] == "d2_cap:0.50"
    deltas["T58_IV_E4"] = d(
        blend_recent=0.2,
        blend_stress=0.2,
        median_recent=0.2,
        median_stress=0.2,
        offsets_positive_recent=5,
        placebo_quantile_recent=0.9,
        cost2x_delta_recent=0.05,
    )
    assert m.decide(deltas, m.SMALL_RULES)["status"] == "d1_replace:T58_IV_E4"
