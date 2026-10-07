"""Toy-array tests of the small-capital construction (scripts/book_v12_small.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import book_v12_small as sm


def _book():
    virt = np.array([10.0, 5.0, 2.0, 1.0, -8.0, -4.0, -2.0, -1.0, 0.0])
    p = np.ones(len(virt)) * 10.0
    return virt, p


def test_r1_keeps_k_names_and_side_gross():
    virt, p = _book()
    out, _ = sm.concentrate(virt, p, "R1", 2)
    assert (out > 0).sum() == 2 and (out < 0).sum() == 2
    assert np.isclose((out * p)[out > 0].sum(), (virt * p)[virt > 0].sum())
    assert np.isclose((out * p)[out < 0].sum(), (virt * p)[virt < 0].sum())
    assert out[0] > 0 and out[1] > 0 and out[4] < 0 and out[5] < 0


def test_r1_k_none_is_noop():
    virt, p = _book()
    out, _ = sm.concentrate(virt, p, "R1", None)
    assert np.array_equal(out, virt)
    out2, _ = sm.concentrate(virt, p, "R1", 100)
    assert np.array_equal(out2, virt)


def test_r3_zeroes_only_shorts():
    virt, p = _book()
    out, _ = sm.concentrate(virt, p, "R3", None)
    assert np.array_equal(out[virt > 0], virt[virt > 0])
    assert (out[virt < 0] == 0).all()


def test_r1b_hurdle_swaps_only_at_125():
    p = np.ones(5) * 1.0
    d1 = np.array([10.0, 8.0, 6.0, 1.0, 0.0])
    _, held = sm.concentrate(d1, p, "R1B", 2, {}, 1.25)
    assert list(np.flatnonzero(held[1])) == [0, 1]
    # name 2 rises to 9.9: 9.9 < 1.25 * 8 = 10 -> no swap
    d2 = np.array([10.0, 8.0, 9.9, 1.0, 0.0])
    out, held = sm.concentrate(d2, p, "R1B", 2, held, 1.25)
    assert list(np.flatnonzero(held[1])) == [0, 1]
    # name 2 reaches 10.0 = 1.25 * 8 -> swap with the smallest held (name 1)
    d3 = np.array([10.0, 8.0, 10.0, 1.0, 0.0])
    out, held = sm.concentrate(d3, p, "R1B", 2, held, 1.25)
    assert list(np.flatnonzero(held[1])) == [0, 2]
    assert (out > 0).sum() == 2
    # plain R1 would have picked the same two at a tie-free larger gap, never more than K
    d4 = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    out, held = sm.concentrate(d4, p, "R1B", 3, held, 1.25)
    assert held[1].sum() <= 3 and (out > 0).sum() <= 3


def test_r1b_drops_names_that_leave_the_side():
    p = np.ones(4)
    _, held = sm.concentrate(np.array([5.0, 4.0, 3.0, -2.0]), p, "R1B", 2, {}, 1.25)
    out, held = sm.concentrate(np.array([-5.0, 4.0, 3.0, 2.0]), p, "R1B", 2, held, 1.25)
    assert not held[1][0] and held[1].sum() == 2


def test_prand_priority_fixed_for_seed_and_ignores_size():
    u1 = np.random.default_rng(sm.PRAND_BASE_SEED + 3).random(9)
    u2 = np.random.default_rng(sm.PRAND_BASE_SEED + 3).random(9)
    assert np.array_equal(u1, u2)
    assert not np.array_equal(u1, np.random.default_rng(sm.PRAND_BASE_SEED + 4).random(9))
    virt, p = _book()
    a, _ = sm.concentrate(virt, p, "PRAND", 2, None, None, u1)
    b, _ = sm.concentrate(virt * 1.0, p, "PRAND", 2, None, None, u2)
    assert np.array_equal(a, b)
    longs = np.flatnonzero(virt > 0)
    expected = set(longs[np.argsort(-u1[longs])[:2]])
    assert set(np.flatnonzero(a > 0)) == expected
    assert np.isclose((a * p)[a > 0].sum(), (virt * p)[virt > 0].sum())


def test_rounding_rule_fractional_long_whole_short():
    target = np.array([0.04, 2.37, 0.0, -2.4, -0.4, -3.6])
    qty = np.zeros(6)
    p = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    post, order, dropped = sm.round_orders(target, qty, p)
    # 0.04 * 10 = $0.40 < $1 -> dropped; 2.37 fractional kept
    assert dropped[0] and post[0] == 0.0
    assert np.isclose(post[1], 2.37)
    assert post[3] == -2.0 and post[4] == 0.0 and post[5] == -4.0
    # a short whose change is under one share is not traded
    post2, order2, dropped2 = sm.round_orders(np.array([-2.4]), np.array([-2.0]), np.array([10.0]))
    assert post2[0] == -2.0 and order2[0] == 0.0 and not dropped2[0]
    # fractional long order of exactly $1 goes
    post3, _, d3 = sm.round_orders(np.array([0.1]), np.array([0.0]), np.array([10.0]))
    assert post3[0] == 0.1 and not d3[0]


def test_rehedge_value_matches_negative_exposure():
    q = np.array([3.0, -2.0, 0.5])
    p = np.array([10.0, 20.0, 40.0])
    beta = np.array([1.0, 1.5, 0.5])
    assert np.isclose(sm.rehedge_value(q, p, beta), -(30.0 - 60.0 + 10.0))
    # names without a price do not count
    p2 = np.array([10.0, np.nan, 40.0])
    assert np.isclose(sm.rehedge_value(q, p2, beta), -(30.0 + 10.0))


def test_dense_beta_alignment_like_tranche_target():
    symbols = pd.Index(["A", "B", "C", "D"])
    beta = pd.Series({"A": 5.0, "B": -3.0, "X": 2.0})
    out = sm.dense_beta(beta, pd.Index(["A", "B", "C", "X"]), symbols)
    assert list(out) == [4.0, -1.0, 1.0, 1.0]


def test_config_table_counts():
    t = sm.config_table()
    assert sum(1 for v in t.values() if v.get("family") == "cand") == 16
    assert sum(1 for v in t.values() if v.get("family") == "tier") == 20
    assert sum(1 for v in t.values() if v.get("family") == "placebo") == 40
    assert len(t) == 76 + 6


def test_names_without_price_pass_through():
    virt = np.array([10.0, 5.0, 2.0, -3.0, -1.0])
    p = np.array([1.0, 1.0, np.nan, 1.0, 0.0])
    for method, k in (("R1", 1), ("R3", None)):
        out, _ = sm.concentrate(virt, p, method, k)
        assert out[2] == 2.0 and out[4] == -1.0


def test_bootstrap_and_te_ratio_identities():
    rng = np.random.default_rng(1)
    x = rng.normal(0.0005, 0.01, 300)
    ci = sm.stationary_bootstrap_diff(x, x, draws=50)
    assert ci["lo90"] == 0.0 and ci["hi90"] == 0.0
    s = pd.Series(x, index=pd.bdate_range("2024-01-01", periods=300))
    assert sm.te_ratio(s * 0.4, s) < 1e-12
    assert sm.te_ratio(s * 0.4 + pd.Series(rng.normal(0, 0.005, 300), index=s.index), s) > 0.1
    assert sm.percentile_among(1.0, [0.0, 2.0, 1.0, 0.5]) == 0.625


def _cfg(sharpe, stress, ret, ret_s, te, v2, x2=0.1):
    return {
        "windows": {"recent": {"sharpe": sharpe}, "stress": {"sharpe": stress}},
        "retention": {"recent": ret, "stress": ret_s},
        "te_ratio": {"full": te},
        "v2": {"v2_pass": v2},
        "implementation": {"ann_excess_recent_2x_cost": x2},
    }


def test_decide_form_contract_order():
    cfgs = {}
    for k in ("50", "100", "200", "300", "all"):
        cfgs[f"F1_R1_K{k}"] = _cfg(1.0, 0.5, 0.9, 0.7, 0.2, k in ("50", "100", "200"))
    cfgs["F1_R1B_K200"] = _cfg(0.95, 0.5, 0.85, 0.7, 0.2, True)
    cfgs["F1_R1B_K100"] = _cfg(0.95, 0.5, 0.85, 0.7, 0.2, True)
    cfgs["F1_R3"] = _cfg(0.5, 0.2, 0.5, 0.3, 0.2, True)
    for c in (25000, 100000):
        for k in ("50", "100", "200", "300", "all"):
            cfgs[f"F1_R1_K{k}_C{c}"] = _cfg(1.0, 0.5, 0.9, 0.7, 0.2, c == 100000)
    res = {
        "configs": cfgs,
        "placebo": {"F1": {"recent_sharpes": [0.1] * 20}},
        "dsr_family": {"dsr": {}},
    }
    d = sm.decide_form("F1", res)
    t = d["tiers"]["50000"]
    assert t["K_star"] == 200 and t["X"] == "F1_R1_K200"  # R1B sharpe below R1
    assert t["deploy"] == "F1_R1_K200" and t["status"] == "same_strategy"
    assert d["mechanical_status"] == "deployable_same" and d["min_capital_tier"] == 50000
    assert d["tiers"]["25000"]["status"] == "infeasible"
    # R3 preferred when it keeps 0.80 and X is less than 0.10 better
    cfgs["F1_R3"] = _cfg(0.95, 0.5, 0.85, 0.7, 0.2, True)
    assert sm.decide_form("F1", res)["tiers"]["50000"]["deploy"] == "F1_R3"
    # high tracking error -> related, needs DSR and placebo
    cfgs["F1_R1_K200"] = _cfg(1.0, 0.5, 0.9, 0.7, 0.4, True)
    cfgs["F1_R3"] = _cfg(0.5, 0.2, 0.5, 0.3, 0.2, True)
    r = sm.decide_form("F1", res)
    assert r["mechanical_status"] == "not_deployable_at_50k"
    res["dsr_family"]["dsr"]["F1_R1_K200"] = 0.8
    r = sm.decide_form("F1", res)
    assert r["mechanical_status"] == "deployable_related_pending_stage_b"
