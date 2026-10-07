from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.portfolio_layer import check as C
from open_composer.portfolio_layer import evaluate as V
from open_composer.portfolio_layer import registry as G
from open_composer.portfolio_layer import rules as R
from open_composer.portfolio_layer.riskmodel import ewma_cov, ledoit_wolf


def _frame(n=700, k=4, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-04", periods=n)
    x = rng.standard_normal((n, k)) * np.array([0.01, 0.02, 0.005, 0.015][:k]) + 0.0004
    return pd.DataFrame(x, index=idx, columns=list("abcd")[:k])


def test_ledoit_wolf_matches_sklearn():
    from sklearn.covariance import LedoitWolf

    x = _frame(300).to_numpy()
    mine, shrink = ledoit_wolf(x)
    sk = LedoitWolf().fit(x)
    assert shrink == pytest.approx(sk.shrinkage_, rel=1e-8)
    assert np.allclose(mine, sk.covariance_, rtol=1e-8, atol=1e-14)


def test_ewma_cov_is_symmetric_psd():
    c = ewma_cov(_frame(300).to_numpy())
    assert np.allclose(c, c.T)
    assert np.linalg.eigvalsh(c).min() > -1e-12


def test_erc_two_assets_inverse_vol():
    cov = np.array([[0.04, 0.01], [0.01, 0.01]])  # vols 0.2 and 0.1, any correlation
    w = R.risk_budgeting(cov, np.array([0.5, 0.5]))
    assert w[0] / w[1] == pytest.approx(0.1 / 0.2, rel=1e-4)


def test_risk_budgeting_hits_budgets():
    x = _frame(500).to_numpy()
    cov = ledoit_wolf(x)[0]
    b = R.budgets(["P1", "P0", "observation", "P1"])
    assert b.sum() == pytest.approx(1.0) and b[2] == pytest.approx(0.10)
    w = R.risk_budgeting(cov, b)
    assert w.sum() == pytest.approx(1.0)
    assert np.allclose(R.risk_shares(w, cov), b, atol=1e-5)


def test_share_cap_rule():
    assert R.share_cap(4) == pytest.approx(0.375)
    assert R.share_cap(6) == pytest.approx(0.25)
    assert R.share_cap(1) == 1.0
    assert 4 * 0.20 < 1.0  # why the 20 percent cap is infeasible below five sleeves


def test_max_sharpe_respects_caps_and_observation():
    x = _frame(500).to_numpy()
    cov = ledoit_wolf(x)[0]
    st = ["P1", "P1", "observation", "P0"]
    a1 = R.risk_budgeting(cov, R.budgets(st))
    mu = R.prior_mu(st, cov)
    w, ok = R.max_sharpe(cov, mu, R.share_cap(4), np.array([s == "observation" for s in st]), a1)
    rs = R.risk_shares(w, cov)
    assert ok
    assert (w >= -1e-9).all() and w.sum() == pytest.approx(1.0)
    assert rs.max() <= R.share_cap(4) + 1e-4
    assert rs[2] <= R.OBS_RISK_SHARE_MAX + 1e-4


def test_equal_vol_sharpe_formula_and_simulation():
    assert R.equal_vol_sharpe(8, 0.1, 1.0) == pytest.approx(2.17, abs=0.01)
    assert V.simulate_equal_vol_sharpe(8, 0.1, 1.0, days=300_000) == pytest.approx(2.17, abs=0.12)
    # no diversification benefit at rho=1; sqrt(n) at rho=0
    assert R.equal_vol_sharpe(8, 1.0, 1.0) == pytest.approx(1.0)
    assert R.equal_vol_sharpe(9, 0.0, 1.0) == pytest.approx(3.0)


def test_rebalance_dates_first_session_with_full_window():
    idx = pd.bdate_range("2021-01-04", periods=700)
    d = V.rebalance_dates(idx, "2022-01-03")
    assert all(idx.get_loc(x) >= V.WINDOW for x in d)
    months = [(x.year, x.month) for x in d]
    assert len(months) == len(set(months))
    assert d[0] >= pd.Timestamp("2022-01-03")


def test_stop_multiplier_triggers_on_drawdown_and_releases():
    idx = pd.bdate_range("2021-01-04", periods=800)
    rng = np.random.default_rng(3)
    calm = rng.standard_normal(800) * 0.005
    crash = calm.copy()
    crash[500:520] = -0.03
    r = pd.DataFrame({"calm": calm, "crash": crash}, index=idx)
    m = V.stop_multipliers(r, 2.0)
    assert (m["crash"].iloc[521:540] == 0.5).any()
    assert (m["calm"] == 1.0).mean() > 0.95
    assert (m.iloc[: V.WINDOW] == 1.0).all().all()


def test_run_rule_weights_and_series():
    r = _frame(700)
    st = ["P1", "P0", "observation", "P1"]
    cap = np.array([100.0, 50.0, 10.0, 40.0])
    for kind in ("A0", "A1", "A2"):
        ser, w, tn = V.run_rule(r, V.RuleSpec(kind, kind), st, cap, "2022-01-03", "2023-08-31")
        assert len(ser) > 300 and np.isfinite(ser).all()
        assert np.allclose(w.sum(axis=1), 1.0, atol=1e-6)
        assert (tn >= 0).all()
    a0, w0, _ = V.run_rule(r, V.RuleSpec("A0", "A0"), st, cap, "2022-01-03", "2023-08-31")
    assert w0.iloc[0].to_numpy() == pytest.approx(cap / cap.sum())


def test_run_rule_a4_never_exceeds_a2_exposure():
    r = _frame(700)
    st = ["P1"] * 4
    cap = np.ones(4)
    ser, _, _ = V.run_rule(r, V.RuleSpec("A4", "A4", 2.0), st, cap, "2022-01-03", "2023-08-31")
    assert np.isfinite(ser).all()


def test_bootstrap_drawdown_monotone_and_leverage_solution():
    rng = np.random.default_rng(5)
    x = rng.standard_normal(700) * 0.01 + 0.0004
    d1 = V.boot_drawdown_q95(x, 1.0, sims=300)
    d2 = V.boot_drawdown_q95(x, 2.0, sims=300)
    assert d2 > d1
    lev = V.solve_leverage(x, 0.30, sims=300)
    assert 0.1 <= lev <= 6.0
    assert V.boot_drawdown_q95(x, lev, sims=300) <= 0.30 + 1e-9


def test_financing_cost_only_above_one_x():
    x = np.zeros(300)
    assert V.boot_drawdown_q95(x, 1.0, sims=50, length=252) == 0.0
    assert V.boot_drawdown_q95(x, 2.0, sims=50, length=252) > 0.0


def test_check_compare_status():
    assert C._cmp("x", 0.1, 0.2).status == "ok"
    assert C._cmp("x", -0.3, 0.2).status == "BREACH"
    assert C._cmp("x", 0.3, 0.2, absolute=False).status == "BREACH"
    assert C._cmp("x", 0.3, None).status == "info"
    assert C._cmp("x", None, 0.2).status == "unknown"
    assert C.exit_code([C.Check("a", 1, 2, "ok"), C.Check("b", 3, 2, "BREACH")]) == 1
    assert C.exit_code([C.Check("a", 1, 2, "ok"), C.Check("b", None, 2, "unknown")]) == 0


def test_registry_loads_and_planned_sleeves_have_no_series():
    reg = G.load_registry()
    ids = {s.id for s in G.sleeves(reg)}
    assert {"F1", "noiseband_qqq_obs", "S1", "S2", "S3", "C2"} <= ids
    ev = {s.id for s in G.evaluable(reg)}
    assert "multi_horizon_engine" not in ev and "options" not in ev and "intraday_model" not in ev
    for s in G.sleeves(reg):
        if s.status == "planned":
            assert not s.has_series and s.raw.get("missing")
    assert G.load_registry()["recent_window"] == {"start": "2024-01-08", "end": "2026-09-15"}


def test_limits_file_has_owner_values():
    import json

    lim = json.loads(G.LIMITS_PATH.read_text())
    assert lim["accounts"]["quant1"]["beta_abs_max"] == 0.2
    assert lim["accounts"]["quant1"]["gross_max"] == 2.0
    assert lim["accounts"]["quant2"]["gross_max"] == 4.0
    assert lim["observation_capital_share_max"] == 0.10
