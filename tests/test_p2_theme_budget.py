"""T-20261005-32: synthetic-data tests for the theme-risk-share machinery. No market data."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import p2_theme_budget as p2  # noqa: E402

WIN = 100
COLS = ["SPY", "SMH", "SOXL", "UPRO", "SSO", "SHY", "BIL", "QQQ"]


def _returns(n: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    spy = rng.normal(0.0004, 0.010, n)
    th = rng.normal(0.0, 0.012, n)  # theme-specific
    smh = 1.3 * spy + th
    data = {
        "SPY": spy,
        "SMH": smh,
        "SOXL": 3.0 * smh + rng.normal(0, 0.003, n),
        "UPRO": 3.0 * spy + rng.normal(0, 0.002, n),
        "SSO": 2.0 * spy + rng.normal(0, 0.001, n),
        "SHY": rng.normal(0.0001, 0.0005, n),
        "BIL": rng.normal(0.0001, 0.0001, n),
        "QQQ": 1.1 * spy + 0.4 * th + rng.normal(0, 0.003, n),
    }
    return pd.DataFrame(data, index=pd.bdate_range("2020-01-01", periods=n))[COLS]


def _view() -> tuple[p2.RiskStats, p2.ThemeView, pd.DataFrame]:
    ret = _returns()
    rs = p2.RiskStats(ret, window=WIN)
    return rs, p2.ThemeView(rs, "SMH"), ret


def _w(rs: p2.RiskStats, **kw: float) -> np.ndarray:
    w = np.zeros(rs.K)
    for k, v in kw.items():
        w[rs.ci[k]] = v
    return w


def test_trs_matches_ols_euler_share():
    rs, view, ret = _view()
    t = 200
    w = _w(rs, QQQ=0.5, SOXL=0.2, SPY=0.1)
    part = view.parts(w, t)
    x = ret.iloc[t - WIN + 1 : t + 1]
    p = x.to_numpy() @ w
    beta = np.cov(x["SMH"], x["SPY"], ddof=1)[0, 1] / np.var(x["SPY"], ddof=1)
    f = x["SMH"].to_numpy() - beta * x["SPY"].to_numpy()
    design = np.column_stack([np.ones(WIN), x["SPY"].to_numpy(), f])
    coef, *_ = np.linalg.lstsq(design, p, rcond=None)
    b_th = coef[2]
    expect = b_th**2 * np.var(f, ddof=1) / np.var(p, ddof=1)
    assert abs(part["trs"][0] - expect) < 1e-10
    assert abs(part["b_th"][0] - b_th) < 1e-10
    # Euler shares of the two factors plus the residual sum to one
    b_m = coef[1]
    resid = p - design @ coef
    total = (
        b_m**2 * np.var(x["SPY"], ddof=1) + b_th**2 * np.var(f, ddof=1) + np.var(resid, ddof=1)
    ) / np.var(p, ddof=1)
    assert abs(total - 1.0) < 1e-9


def test_all_cash_has_zero_trs_and_short_window_is_skipped():
    rs, view, _ = _view()
    assert view.parts(_w(rs), 200)["trs"][0] == 0.0
    assert view.parts(_w(rs, QQQ=1.0), WIN - 5) is None  # fewer than WIN returns


def _sub_k(rs: p2.RiskStats) -> dict[int, int]:
    out = {}
    for col, i in rs.ci.items():
        if col in p2.NO_MOVE or col in ("SHY", "BIL"):
            out[i] = i
        else:
            out[i] = rs.ci[p2.SUB.get(col, "SPY")]
    return out


def test_cap_returns_smallest_s_and_zero_when_not_binding():
    rs, view, _ = _view()
    t = 200
    sub_k = _sub_k(rs)
    cash_k = {rs.ci["SHY"], rs.ci["BIL"]}
    w = _w(rs, SOXL=0.6, QQQ=0.4)
    trs0 = view.parts(w, t)["trs"][0]
    assert trs0 > 0.3
    c = 0.30
    new, s, info = p2.cap_row(view, t, w, c, sub_k, cash_k)
    assert info["bound"] and not info["flag"] and 0.0 < s < 1.0
    assert view.parts(new, t)["trs"][0] <= c
    prev = np.array(w, dtype=float)
    for i in np.flatnonzero(w > 0):
        if sub_k[i] != i:
            prev[i] = w[i] * (1 - (s - 0.01))
            prev[sub_k[i]] += w[i] * (s - 0.01)
    assert view.parts(prev, t)["trs"][0] > c  # one grid step smaller fails
    assert abs(new.sum() - w.sum()) < 1e-12
    # not binding: s = 0 and weights untouched
    new2, s2, info2 = p2.cap_row(view, t, w, 0.999, sub_k, cash_k)
    assert s2 == 0.0 and not info2["bound"] and np.array_equal(new2, w)


def test_cap_level_one_leaves_weights_unchanged():
    rs, view, _ = _view()
    w = _w(rs, SOXL=0.5, SMH=0.3, QQQ=0.2)
    new, s, _ = p2.cap_row(view, 200, w, 1.0, _sub_k(rs), {rs.ci["SHY"], rs.ci["BIL"]})
    assert s == 0.0 and np.array_equal(new, w)


def test_h1_overlay_brings_trs_to_c():
    rs, view, _ = _view()
    t = 200
    w = _w(rs, SOXL=0.5, QQQ=0.5)
    part = view.parts(w, t)
    c = 0.20
    assert part["trs"][0] > c
    h = p2.h1_size(part, view.vs[t], view.vf[t], c)
    assert h > 0
    w2 = w.copy()
    w2[rs.ci["SMH"]] -= h
    w2[rs.ci["SPY"]] += h * view.beta[t]
    assert abs(view.parts(w2, t)["trs"][0] - c) < 1e-9
    # below the cap: no hedge
    assert p2.h1_size(part, view.vs[t], view.vf[t], 0.99) == 0.0


def test_h2_solve_reproduces_target_loadings():
    bth_s, bm_s, bth_u, bm_u = -2.0, -1.4, 0.05, 3.0
    h = 0.3
    n, u = p2.h2_solve(bth_s, bm_s, bth_u, bm_u, h)
    assert n >= 0 and u >= 0
    assert abs(n * bth_s + u * bth_u + h) < 1e-12
    assert abs(n * bm_s + u * bm_u) < 1e-12
    # a negative solution is rejected
    assert p2.h2_solve(2.0, 1.4, 0.05, 3.0, 0.3) is None


def test_same_vol_k_one_and_half_scaled_series():
    rng = np.random.default_rng(3)
    r0 = rng.normal(0.001, 0.01, 500)
    rf = np.full(500, 0.0001)
    m = np.ones(500, dtype=bool)
    st = p2.window_stats(r0, r0, rf, m)
    assert abs(st["k"] - 1.0) < 1e-12 and abs(st["dsr"]) < 1e-12
    half = 0.5 * r0
    st2 = p2.window_stats(half, r0, rf, m)
    assert abs(st2["k"] - 2.0) < 1e-12
    # same-vol series = r0 - rf - (0.065/252) - ... : debit effect only
    xs = p2.samevol_excess(half, rf, 2.0)
    expect = r0 - 2 * rf - p2.DEBIT_RATE / 252.0 + rf
    # 2*(0.5 r0 - rf) - (debit - rf) = r0 - 2 rf - debit + rf
    assert np.allclose(xs, expect, atol=1e-15)
    assert abs(st2["dsr"] - (p2.sharpe(xs) - p2.sharpe(r0 - rf))) < 1e-12


def test_margin_bisection_result_is_feasible_and_maximal():
    lev2 = np.array([False, False, True, False])
    lev3 = np.array([False, False, False, True])

    def pos(lam: float) -> np.ndarray:
        # 0.5 in a 3x ETF, 0.4 cash-like 1x, hedge short 1x scales with lam, 1x long hedge leg
        return np.array([0.4 + 1.2 * lam, -1.0 * lam, 0.0, 0.5])

    feas = lambda lam: p2.margin_ok(pos(lam), lev2, lev3)  # noqa: E731
    assert feas(0.0)
    assert not feas(1.0)
    lam = p2.bisect_lambda(feas)
    assert 0.0 < lam < 1.0
    assert feas(lam)
    assert not feas(lam + 2e-4)
    # both inequalities hold at the solution
    p = pos(lam)
    long, short = np.clip(p, 0, None), np.clip(-p, 0, None)
    assert 0.5 * (long.sum() + short.sum()) <= 1.0 + 1e-12
    maint = 0.30 * long[[0, 1]].sum() + 0.75 * long[3] + 0.30 * short.sum()
    assert maint <= 0.9 + 1e-12


def test_decision_rule_mechanics():
    def row(d, rep, es):
        return {"dsr_recent": d, "replay_mean_change": rep, "es_stress_rel": es}

    grid = {
        "CAP": {
            "40": row(-0.02, 0.02, 1.0),
            "30": row(-0.08, 0.02, 1.0),
            "20": row(-0.30, 0.02, 1.0),
            "10": row(-0.05, 0.02, 1.0),  # cost_ok but not monotone
        },
        "H2F": {t: row(-0.5, 0.0, 1.0) for t in ("40", "30", "20", "10")},
        "H1F": {
            "40": row(-0.01, 0.0, 1.0),
            "30": row(-0.02, 0.0, 0.9),
            "20": row(-0.03, 0.0, 0.9),
            "10": row(-0.04, 0.0, 0.9),
        },
    }
    out = p2.decision_rule(grid)
    assert out["decision"]["CAP"]["selected"] == 0.30
    assert out["decision"]["CAP"]["10"]["monotone"] is False
    assert out["pilot_limit"] == {"version": "CAP", "c": 0.30}
    assert out["alternatives"] == [{"version": "H1F", "c": 0.10}]
    assert out["status"] == "pilot_limit_selected"
    bad = {v: {t: row(-0.5, 0.0, 1.0) for t in ("40", "30", "20", "10")} for v in grid}
    assert p2.decision_rule(bad)["status"] == "no_level_within_cost"
    ok_nobenefit = {v: {t: row(-0.01, 0.0, 1.0) for t in ("40", "30", "20", "10")} for v in grid}
    assert p2.decision_rule(ok_nobenefit)["status"] == "cost_ok_no_benefit_monitor_only"
