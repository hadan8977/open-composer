from __future__ import annotations

import copy
import json
import math

import numpy as np
import pandas as pd
import pytest

from open_composer.research import scorecard_v2 as sc

CFG = sc.load_config()
DATES = pd.bdate_range("2017-10-02", "2026-09-17")


def _phases(last="2026-09-17"):
    recent = DATES[DATES >= pd.Timestamp(CFG["recent_window_start"])]
    cuts = np.array_split(np.arange(len(recent)), 4)
    out = []
    for i, c in enumerate(cuts):
        out.append(
            {
                "id": f"P{i + 1:02d}",
                "start": str(recent[c[0]].date()),
                "end": str(recent[c[-1]].date()),
            }
        )
    return out


def _make_family(
    n_var=3,
    n_off=5,
    daily_mean=0.0008,
    sd=0.004,
    cost2x_mean=None,
    seed=7,
    override=None,
):
    """Long frame of daily series per variant and offset: common factor plus own noise."""
    rng = np.random.default_rng(seed)
    common = rng.standard_normal(len(DATES))
    rows, crows = [], []
    for vi in range(n_var):
        for k in range(n_off):
            eps = 0.6 * common + 0.8 * rng.standard_normal(len(DATES))
            net = pd.Series(daily_mean + sd * eps, index=DATES)
            if override is not None:
                net = override(net, vi, k)
            c2 = net - (daily_mean - (cost2x_mean if cost2x_mean is not None else daily_mean * 0.9))
            for series, store in ((net, rows), (c2, crows)):
                store.append(
                    pd.DataFrame(
                        {
                            "date": DATES,
                            "variant": f"V{vi}",
                            "offset": k,
                            "net": series.to_numpy(),
                            "gross": series.to_numpy() + 0.0001,
                        }
                    )
                )
    return pd.concat(rows, ignore_index=True), pd.concat(crows, ignore_index=True)


def _score(returns, cost2x, **kw):
    bil = pd.Series(0.00005, index=DATES)
    state = pd.Series("up_mid", index=DATES)
    kw.setdefault("phases", _phases())
    kw.setdefault("attestations", {f"V{i}": {"V1": True, "V2": True} for i in range(3)})
    rng = np.random.default_rng(3)
    kw.setdefault(
        "placebo",
        {
            f"V{i}": {"net": rng.normal(0, 0.4, 100), "gross": rng.normal(0, 0.4, 100)}
            for i in range(3)
        },
    )
    kw.setdefault(
        "signal_ls",
        {
            f"V{i}": pd.Series(
                0.002 + 0.004 * np.random.default_rng(i).standard_normal(len(DATES)), index=DATES
            )
            for i in range(3)
        },
    )
    return sc.score_family(returns, cost2x, bil, state=state, **kw)


# ---- DSR / PSR ------------------------------------------------------------------------------
def test_expected_max_null_matches_reference_value():
    # coordinator's check: var_SR 0.175, N_eff 3.88 -> E[max null] 0.43
    assert sc.expected_max_null(0.175, 3.88) == pytest.approx(0.43, abs=0.01)


def test_dsr_equals_psr_when_n_eff_is_one():
    r = np.random.default_rng(1).normal(0.0005, 0.01, 700)
    d = sc.dsr(r, var_sr_annual=0.2, n_eff=1.0)
    assert d["dsr"] == pytest.approx(d["psr0"], abs=1e-12)


def test_dsr_is_monotone_decreasing_in_n_eff():
    r = np.random.default_rng(2).normal(0.0006, 0.01, 700)
    vals = [sc.dsr(r, var_sr_annual=0.2, n_eff=n)["dsr"] for n in (1, 2, 3, 5, 8, 20)]
    assert all(a >= b for a, b in zip(vals, vals[1:], strict=False))
    assert vals[0] > vals[-1]


def test_psr_normal_closed_form():
    # normal returns: skew 0, kurtosis 3 -> denominator sqrt(1 + SR_pp^2 / 2)
    rng = np.random.default_rng(5)
    r = rng.normal(0.0005, 0.01, 200000)
    sr = r.mean() / r.std(ddof=1)
    want = sc._N.cdf(sr * math.sqrt(len(r) - 1) / math.sqrt(1 + sr**2 / 2))
    assert sc.psr(r) == pytest.approx(want, abs=2e-3)


# ---- primitives -----------------------------------------------------------------------------
def test_blend_offsets_equal_weight_on_common_dates():
    d = pd.bdate_range("2024-01-01", periods=4)
    rows = []
    for k, vals in enumerate([[1, 2, 3, 4], [3, 4, 5, np.nan]]):
        rows.append(
            pd.DataFrame({"date": d, "variant": "A", "offset": k, "net": vals, "gross": vals})
        )
    out = sc.blend_offsets(pd.concat(rows), "net")["A"]
    assert list(out.index) == list(d[:3])
    assert out.tolist() == [2.0, 3.0, 4.0]


def test_sharpe_z_formula():
    z = sc.sharpe_z(0.2, 63, 1.0, 676)
    se = math.sqrt((1 + 1.0**2 / 2) / (63 / 252) + (1 + 1.0**2 / 2) / (676 / 252))
    assert z == pytest.approx((0.2 - 1.0) / se)


def test_sharpe_z_is_not_bounded_by_short_window_sharpe():
    # with SE_short taken at the observed short Sharpe |z| stays below 1 whatever happens; here a
    # 63-session collapse to SR -8 against a main SR of 1 must reach the veto line of -3
    assert sc.sharpe_z(-8.0, 63, 1.0, 676) < CFG["vetoes"]["recent_break_z_veto"]


def test_newey_west_t_close_to_iid_for_white_noise():
    x = np.random.default_rng(4).normal(0.01, 0.1, 5000)
    s = sc.signal_t_stats(x)
    assert s["t_newey_west"] == pytest.approx(s["t_iid"], rel=0.15)


def test_placebo_percentile():
    assert sc.placebo_percentile(1.0, [0.0, 0.5, 2.0, 3.0]) == 0.5
    assert sc.placebo_percentile(1.0, None) is None


def test_dd_thresholds_ordered_and_scale_with_vol():
    a = sc.dd_thresholds(0.5, 0.06, 126, n_sims=4000, seed=1)
    b = sc.dd_thresholds(0.5, 0.12, 126, n_sims=4000, seed=1)
    assert a["p99"] > a["p95"] > 0
    assert b["p95"] == pytest.approx(2 * a["p95"], rel=1e-9)  # same normals, scaled drift and sd


# ---- tier boundaries ------------------------------------------------------------------------
def _metrics(**kw):
    base = {
        "dsr": 0.70,
        "signal_t": 0.0,
        "placebo_net_pct": 0.90,
        "placebo_gross_pct": 0.0,
        "robustness_score": 3,
    }
    base.update(kw)
    return base


def test_tier_p1_boundary():
    assert sc._tier(CFG, _metrics(), [], [])[0] == "P1"
    assert sc._tier(CFG, _metrics(dsr=0.6999), [], [])[0] == "none"
    assert sc._tier(CFG, _metrics(placebo_net_pct=0.8999), [], [])[0] == "none"
    assert sc._tier(CFG, _metrics(robustness_score=2), [], [])[0] == "none"
    assert sc._tier(CFG, _metrics(placebo_net_pct=None), [], [])[0] == "none"


def test_tier_p2_boundary():
    m = _metrics(
        dsr=0.80, signal_t=3.0, placebo_net_pct=0.95, placebo_gross_pct=0.95, robustness_score=5
    )
    assert sc._tier(CFG, m, [], [])[0] == "P2"
    for key, bad in (
        ("dsr", 0.7999),
        ("signal_t", 2.99),
        ("placebo_net_pct", 0.9499),
        ("placebo_gross_pct", 0.9499),
        ("robustness_score", 4),
    ):
        tier = sc._tier(CFG, {**m, key: bad}, [], [])[0]
        # a P2 miss falls back to P1 only if the P1 conditions still hold
        assert tier in ("P1", "none")
        assert tier != "P2"
    assert sc._tier(CFG, m, ["V3"], [])[0] == "none"
    assert sc._tier(CFG, m, [], ["V2"])[0] == "none"


# ---- end to end: vetoes, scoring, config ------------------------------------------------------
def test_strong_family_reaches_p2_and_has_full_scorecard():
    ret, c2 = _make_family()
    out = _score(ret, c2)
    card = out["variants"]["V0"]
    assert card["tier"] == "P2", card["tier_detail"]
    assert card["vetoes_triggered"] == []
    assert card["robustness_score"] == 6
    assert card["config_version"] == CFG["version"]
    assert out["family"]["n_variants"] == 3
    assert out["family"]["n_eff"] == pytest.approx(
        1 + 2 * (1 - out["family"]["mean_pairwise_corr"])
    )
    assert card["L1"]["status"] == "not_evaluable"
    assert card["pass_flags"]["research_pass"] is True
    json.dumps(out, default=str)  # scorecard must be JSON-serialisable


def test_missing_placebo_and_signal_blocks_tier():
    ret, c2 = _make_family()
    out = _score(ret, c2, placebo={}, signal_ls={})
    card = out["variants"]["V0"]
    assert card["tier"] == "none"
    assert card["placebo"]["status"] == "missing"
    assert card["signal"]["status"] == "missing"
    assert card["robustness"]["f_gross_placebo"]["status"] == "missing"


def test_unattested_v1_v2_blocks_tier_but_is_not_a_trigger():
    ret, c2 = _make_family()
    out = _score(ret, c2, attestations={})
    card = out["variants"]["V0"]
    assert card["tier"] == "none"
    assert card["vetoes_triggered"] == []
    assert set(card["vetoes_unassessed"]) == {"V1", "V2"}
    assert card["pass_flags"]["workflow_pass"] is None


def test_v1_v2_attested_false_trigger():
    ret, c2 = _make_family()
    out = _score(ret, c2, attestations={"V0": {"V1": False, "V2": True}})
    assert "V1" in out["variants"]["V0"]["vetoes_triggered"]
    assert out["variants"]["V0"]["tier"] == "none"


def test_v3_cost2x_veto_fires():
    ret, c2 = _make_family(cost2x_mean=-0.0003)
    out = _score(ret, c2)
    card = out["variants"]["V0"]
    assert "V3" in card["vetoes_triggered"]
    assert card["vetoes"]["V3"]["annual_excess"] <= 0
    assert card["tier"] == "none"


def test_v4_stress_crash_veto_fires():
    crash_start = pd.Timestamp("2020-02-20")

    def crash(net, vi, k):
        net = net.copy()
        w = net.index[(net.index >= crash_start)][:21]
        net.loc[w] -= 0.01  # 21 sessions of -1%/day on a 0.4% daily sd
        return net

    ret, c2 = _make_family(override=crash)
    out = _score(ret, c2)
    v4 = out["variants"]["V0"]["vetoes"]["V4"]
    assert v4["triggered"] is True
    assert v4["windows"]["21"]["loss_in_sigma"] > CFG["vetoes"]["stress_21d_loss_sigma_veto"]
    assert out["variants"]["V0"]["tier"] == "none"


def test_v4_warn_band_does_not_veto():
    # two-sided check on the warn / veto thresholds read from the config
    ret, c2 = _make_family()
    v4 = sc._veto_v4(
        sc._window(sc.blend_offsets(ret, "net")["V0"], *CFG["vetoes"]["stress_window"]), CFG
    )
    assert v4["triggered"] is False
    # forcing a very tight veto in a copied config makes the same data trigger
    cfg2 = copy.deepcopy(CFG)
    cfg2["vetoes"]["stress_21d_loss_sigma_veto"] = 0.1
    s = sc.blend_offsets(ret, "net")["V0"]
    assert sc._veto_v4(sc._window(s, *cfg2["vetoes"]["stress_window"]), cfg2)["triggered"] is True


def test_v5_recent_break_veto_fires():
    def break_last(net, vi, k):
        net = net.copy()
        net.iloc[-63:] -= 0.012
        return net

    ret, c2 = _make_family(override=break_last)
    out = _score(ret, c2)
    card = out["variants"]["V0"]
    assert card["vetoes"]["V5"]["triggered"] is True
    assert card["vetoes"]["V5"]["z_min"] < CFG["vetoes"]["recent_break_z_veto"]
    assert card["robustness"]["e_recent_consistency"]["pass"] is False


def test_robustness_check_d_offsets_counts_positive_offsets():
    def weak_offsets(net, vi, k):
        # offsets 0 and 1 lose money
        return net - 0.003 if k < 2 else net

    ret, c2 = _make_family(override=weak_offsets)
    chk = _score(ret, c2)["variants"]["V0"]["robustness"]["d_offsets"]
    assert chk["value"] == 3
    assert chk["pass"] is False


def test_robustness_check_c_single_phase_dominance():
    ph = _phases()
    first_end = pd.Timestamp(ph[0]["end"])

    def front_loaded(net, vi, k):
        net = net.copy()
        net[net.index > first_end] = net[net.index > first_end] * 0.0 + 0.0
        net[net.index <= first_end] += 0.003
        return net

    ret, c2 = _make_family(override=front_loaded)
    chk = _score(ret, c2)["variants"]["V0"]["robustness"]["c_single_phase"]
    assert chk["pass"] is False
    assert chk["value"] > CFG["robustness_checks"]["c_max_single_phase_share_of_recent_pnl"]


def test_thresholds_come_from_config_not_code(tmp_path):
    ret, c2 = _make_family()
    assert _score(ret, c2)["variants"]["V0"]["tier"] == "P2"

    cfg = copy.deepcopy(CFG)
    cfg["tiers"]["P2_live_candidate"]["signal_t_min"] = 1e6
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg))
    assert _score(ret, c2, config_path=p)["variants"]["V0"]["tier"] == "P1"

    cfg["tiers"]["P1_paper_incubation"]["dsr_min"] = 1.1
    p.write_text(json.dumps(cfg))
    assert _score(ret, c2, config_path=p)["variants"]["V0"]["tier"] == "none"

    cfg = copy.deepcopy(CFG)
    cfg["version"] = "v-test"
    p.write_text(json.dumps(cfg))
    assert _score(ret, c2, config_path=p)["config_version"] == "v-test"


def test_forward_record_enables_l1_when_attested():
    ret, c2 = _make_family()
    fwd = {"V0": pd.Series(0.0008 + 0.004 * np.random.default_rng(9).standard_normal(30))}
    fwd["V0"].index = pd.bdate_range("2026-09-18", periods=30)
    out = _score(ret, c2, forward=fwd, execution_acceptance={"V0": True}, review_ok={"V0": True})
    card = out["variants"]["V0"]
    assert card["forward"]["status"] == "evaluated"
    assert card["L1"]["status"] == "evaluated"
    assert card["L2"]["met"] is False  # < 6 months of forward record


def test_v21_l1_counts_real_paper_sessions_and_needs_the_review():
    """Owner 2026-10-04: forward record stitched from 09-01, >= 10 real paper sessions, P1 enough
    for a pilot proposal, plus the balanced-window and logic review."""
    cfg = CFG["tiers"]["L1_live_pilot_proposal"]
    assert cfg["requires"] == "P1" and cfg["paper_sessions_min"] == 10 and cfg["review_required"]
    assert CFG["tiers"]["L2_scale_up"]["requires"] == "P2"
    ret, c2 = _make_family()
    fwd = {"V0": pd.Series(0.0008 + 0.004 * np.random.default_rng(9).standard_normal(30))}
    fwd["V0"].index = pd.bdate_range("2026-09-01", periods=30)
    few = _score(
        ret,
        c2,
        forward=fwd,
        execution_acceptance={"V0": True},
        review_ok={"V0": True},
        paper_sessions={"V0": 4},
    )
    assert few["variants"]["V0"]["L1"]["conditions"]["paper_sessions"] is False
    enough = _score(
        ret,
        c2,
        forward=fwd,
        execution_acceptance={"V0": True},
        review_ok={"V0": True},
        paper_sessions={"V0": 10},
    )
    assert enough["variants"]["V0"]["L1"]["conditions"]["paper_sessions"] is True
    unreviewed = _score(
        ret, c2, forward=fwd, execution_acceptance={"V0": True}, paper_sessions={"V0": 10}
    )
    l1 = unreviewed["variants"]["V0"]["L1"]
    assert l1["status"] == "not_evaluable" and "balanced_and_logic_review" in l1["reason"]


def test_contribution_test():
    rng = np.random.default_rng(11)
    idx = pd.bdate_range("2024-01-08", periods=700)
    base = pd.Series(0.0002 + 0.004 * rng.standard_normal(700), index=idx)
    better = base + 0.0008 + 0.001 * rng.standard_normal(700)
    res = sc.contribution_test(better, base, var_sr_annual=0.1, n_eff=2.0)
    assert res["dsr_with"] > res["dsr_without"]
    assert res["pass"] is (res["nw_t_difference"] >= res["min_t"])
