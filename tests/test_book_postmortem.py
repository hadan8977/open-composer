"""Unit tests of the T-20261001-19 post-mortem runner and analysis helpers (no market data)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts import eval_book_postmortem as ep
from scripts import run_book_postmortem as rp


def test_pm_paths_are_the_30_preregistered_ids() -> None:
    paths = rp.pm_paths()
    assert len(paths) == 30 == len(set(paths))
    assert paths[0] == "PM_L1_M0_A_o0" and paths[-1] == "PM_L2a_M1_C_o4"
    assert {rp.parse_pm_path(p)["rung"] for p in paths} == {"L1", "L2c", "L2a"}


def test_parse_pm_path_rejects_bad_ids() -> None:
    assert rp.parse_pm_path("PM_L0_M0_A_o3")["offset"] == 3
    for bad in ("PM_L3_M0_A_o0", "PM_L1_M0_A_o5", "M0_A_o0_close", "PM_L1_M2_A_o0"):
        with pytest.raises(ValueError):
            rp.parse_pm_path(bad)


def test_rung_settings() -> None:
    l0, l1, l2c, l2a = (rp.rung_settings(r) for r in rp.RUNGS)
    assert l0["style_cap"] == 0.25 and l0["exec"] == "close"
    assert l1["style_cap"] is None and l1["exec"] == "close"
    assert (l2c["exec"], l2c["opt"], l2c["cost"]) == ("open", "open", "open")
    assert (l2a["exec"], l2a["opt"], l2a["cost"]) == ("open", "close", "close")
    assert l2a["style_cap"] is None and l2c["style_cap"] is None


def test_share_at_cap_and_style_summary() -> None:
    assert ep.share_at_cap(np.array([0.25, -0.25, 0.1, 0.2499999]), 0.25) == 0.75
    n_groups = 2
    rows = [
        [0.0, 0.0, 0.0, -0.10, 0.25, 0.0],
        [0.0, 0.0, 0.0, 0.05, -0.25, 0.1],
    ]
    rec = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-10", "2024-01-17"]),
            "exposures_target": [json.dumps(r) for r in rows],
        }
    )
    out = ep.style_summary(
        rec, n_groups, ["size", "beta", "momentum"], ("2024-01-08", "2024-12-31")
    )
    assert out["n"] == 2
    assert out["size"]["share_at_ref_cap"] == 0.5
    assert out["beta"]["share_at_ref_cap"] == 1.0
    assert out["beta"]["mean"] == 0.0 and out["momentum"]["mean"] == pytest.approx(0.05)


def test_transfer_coefficient_plain_and_risk_adjusted() -> None:
    idx = pd.Index(list("abcdef"))
    score = pd.Series([2.0, 1.0, 0.0, -1.0, -2.0, np.nan], index=idx)
    w = pd.Series({"a": 0.2, "e": -0.2})
    out = ep.transfer_coefficient(w, score, pd.Series(1.0, index=idx))
    assert out["n_universe"] == 5 and out["n_held"] == 2
    wv = np.array([0.2, 0.0, 0.0, 0.0, -0.2])
    assert out["tc"] == pytest.approx(np.corrcoef(wv, score.dropna().to_numpy())[0, 1])
    assert out["tc_risk_adjusted"] == pytest.approx(out["tc"])  # unit sigma
    sigma = pd.Series([2.0, 1.0, 1.0, 1.0, 1.0, 1.0], index=idx)
    ra = ep.transfer_coefficient(w, score, sigma)["tc_risk_adjusted"]
    assert ra == pytest.approx(np.corrcoef(wv * sigma.iloc[:5].to_numpy(), score.dropna())[0, 1])


def test_transfer_coefficient_perfect_alignment() -> None:
    score = pd.Series(np.linspace(-1, 1, 20), index=[f"s{i}" for i in range(20)])
    assert ep.transfer_coefficient(score * 0.01, score)["tc"] == pytest.approx(1.0)


def test_attribute_day_components_sum_to_stock_return() -> None:
    names = ["a", "b", "c", "d"]
    factors = ["market", "g1", "g2", "size", "beta"]
    x = pd.DataFrame(
        [[1, 1, 0, 0.5, 1.0], [1, 0, 1, -0.5, 0.2], [1, 1, 0, 1.0, -1.0]],
        index=["a", "b", "c"],
        columns=factors,
        dtype=float,
    )
    f = pd.Series([0.001, 0.002, -0.001, 0.003, 0.0005], index=factors)
    w = pd.Series([0.1, -0.05, 0.2, 0.03], index=names)  # "d" has no exposure row
    ret = pd.Series([0.01, -0.02, 0.005, 0.04], index=names)
    out = ep.attribute_day(w, ret, x, f, factors, ["g1", "g2"], ["size", "beta"])
    total = float((w * ret).sum())
    assert sum(out.values()) == pytest.approx(total, abs=1e-15)
    assert out["market"] == pytest.approx((0.1 - 0.05 + 0.2) * 0.001)
    assert out["style_size"] == pytest.approx((0.1 * 0.5 + 0.05 * 0.5 + 0.2 * 1.0) * 0.003)
    # the unmodelled name d goes entirely to specific
    xs = x.copy()
    only_d = ep.attribute_day(
        pd.Series({"d": 1.0}), ret, xs, f, factors, ["g1", "g2"], ["size", "beta"]
    )
    assert only_d["specific"] == pytest.approx(0.04) and only_d["market"] == 0.0


def _med(net: dict[str, float], gross: dict[str, float]) -> dict[str, dict[str, float]]:
    return {"net_sharpe": net, "gross_sharpe": gross}


def test_ladder_decisions_thresholds() -> None:
    def rung(net_a: float, net_s: float, gross_a: float, gross_s: float) -> dict:
        return {
            v: _med({"A": net_a, "stress": net_s}, {"A": gross_a, "stress": gross_s})
            for v in ep.VARIANTS
        }

    med = {
        "L0": rung(0.6, 0.0, 1.0, 0.1),
        "L1": rung(0.8, -0.1, 1.31, -0.15),  # gross A +0.31, stress -0.25
        "L2c": rung(0.96, -0.1, 1.5, 0.0),  # net A +0.16 vs L1, stress 0
        "L2a": rung(0.94, 0.0, 1.5, 0.0),
    }
    d = ep.ladder_decisions(med)
    assert d["D1"]["both_variants"] and d["D2"]["both_variants"]
    assert not d["D2a"]["both_variants"]  # +0.14 < 0.15
    assert d["D3"]["M0_A"]["cost_drag_A"] == pytest.approx(0.51) and d["D3"]["both_variants"]
    med["L1"]["M1_C"]["gross_sharpe"]["stress"] = -0.25  # stress change -0.35
    assert not ep.ladder_decisions(med)["D1"]["both_variants"]


def test_median_blocks_nests_and_ignores_bools() -> None:
    blocks = [{"a": {"x": 1.0, "ok": True}}, {"a": {"x": 3.0, "ok": False}}, {"a": {"x": 2.0}}]
    assert ep.median_blocks(blocks) == {"a": {"x": 2.0}}


def test_style_vs_specific_sums_styles(tmp_path, monkeypatch) -> None:
    from scripts import report_book_postmortem as rep

    idx = pd.bdate_range("2024-01-08", periods=60)
    rng = np.random.default_rng(0)
    cols = {
        c: rng.normal(0.0005, 0.01, len(idx))
        for c in (
            "market",
            "industry",
            "style_a",
            "style_b",
            "specific",
            "etf_leg",
            "tbill_leg",
            "costs",
            "unreconciled",
            "gross_reported",
            "net_reported",
        )
    }
    df = pd.DataFrame(cols, index=idx)
    for rung in ("L0", "L1"):
        for v in ep.VARIANTS:
            df.to_parquet(tmp_path / f"attrib_{rung}_{v}.parquet")
    monkeypatch.setattr(rep, "PM_DIR", tmp_path)
    out = rep.style_vs_specific(["a", "b"])
    got = out["L1_M0_A"]["A"]["style_total"]["ann_contribution"]
    want = float((df["style_a"] + df["style_b"]).mean() * 252)
    assert abs(got - want) < 1e-12
    assert (
        abs(out["L0_M1_C"]["A"]["style_a"]["ann_contribution"] - df["style_a"].mean() * 252) < 1e-12
    )
