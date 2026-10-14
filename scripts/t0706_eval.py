# ruff: noqa: E501
"""T-20261007-06 shared evaluation: metrics, V4, DSR inputs, candidate evaluation (v2.1 + 5b).

Series are daily arrays over a master date index covering 2016..2026-09-15; masks come from
t15_engine.window_masks (recent = 2024-01-08 onward)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15_stats as T  # noqa: E402


def r4(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def sr(x: np.ndarray, mask: np.ndarray) -> float:
    return float(T.sr_rows(np.asarray(x)[None, :], mask)[0])


def group_dsr_args(rec_series: list[np.ndarray], n_trials: int) -> dict:
    X = np.stack(rec_series)
    srs = T.sr_rows(X, np.ones(X.shape[1], bool))
    var_sr = float(np.nanvar(srs, ddof=1)) if len(srs) > 1 else 0.0
    c = np.nan_to_num(X, nan=0.0)
    c = c[np.std(c, axis=1) > 0]
    rho = float(np.mean(np.corrcoef(c)[np.triu_indices(len(c), 1)])) if len(c) > 1 else 1.0
    return {
        "variants": len(X),
        "var_sr": var_sr,
        "mean_corr": rho,
        "n_trials": n_trials,
        "n_eff": 1 + (n_trials - 1) * (1 - rho),
    }


def v4_check(net: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    m = (dates >= pd.Timestamp("2017-10-02")) & (dates <= pd.Timestamp("2023-08-31"))
    raw = net[m]
    if np.isfinite(raw).sum() < 0.8 * m.sum():
        return {
            "done": False,
            "sessions_finite": int(np.isfinite(raw).sum()),
            "sessions": int(m.sum()),
        }
    x = np.nan_to_num(raw, nan=0.0)
    out = {"done": True, "sessions": int(m.sum())}
    sd = x.std(ddof=1)
    for w, name, veto, warn in ((21, "21d", 5.0, 4.0), (63, "63d", 4.0, 3.0)):
        c = np.convolve(x, np.ones(w), mode="valid")
        worst = float(c.min())
        vol = sd * math.sqrt(w)
        ratio = -worst / vol if vol > 0 else float("nan")
        out[name] = {
            "worst_sum": r4(worst),
            "vol_over_window": r4(vol),
            "loss_over_vol": r4(ratio),
            "veto": bool(ratio > veto),
            "warn": bool(ratio > warn),
        }
    out["sr_net_2017_2023"] = r4(sr(net, m))
    return out


def metrics(
    nets: dict[float, np.ndarray],
    gross: np.ndarray,
    trades: np.ndarray,
    gross_per_trade_bp: float | None,
    masks: dict,
    extra_mults=(0.5, 1.0, 2.0, 4.0),
) -> dict:
    rec = masks["recent"]
    n1 = nets[1.0]
    d = {
        "gross_bp_day": r4(np.nanmean(gross[rec]) * 1e4),
        "net_bp_day": r4(np.nanmean(n1[rec]) * 1e4),
        "cost_bp_day": r4((np.nanmean(gross[rec]) - np.nanmean(n1[rec])) * 1e4),
        "sr_net_recent": {f"x{m}": r4(sr(nets[m], rec)) for m in extra_mults if m in nets},
        "sr_gross_recent": r4(sr(gross, rec)),
        "phase_sr_net": {f"P{i:02d}": r4(sr(n1, masks[f"P{i:02d}"])) for i in range(1, 12)},
        "trades_per_day": r4(np.nanmean(trades[rec])),
        "trade_days": int(np.nansum(trades[rec] > 0)),
        "gross_bp_per_trade": r4(gross_per_trade_bp),
        "ann_net_ret": r4(np.nanmean(n1[rec]) * 252),
    }
    gb, cb = d["gross_bp_day"], d["cost_bp_day"]
    d["cost_share_of_gross"] = r4(cb / gb) if gb and gb > 0 else None
    t = T.nw(n1[rec])
    d["t_newey_west"] = r4(t["t_newey_west"])
    d["t_iid"] = r4(t["t_iid"])
    return d


def eval_candidate(
    label, nets, gross, masks, dates, net_pl, gross_pl, dsr_args, phase_nets=None
) -> dict:
    """nets: {mult: series}; net_pl/gross_pl: placebo series (seeds x days) or None; phase_nets: [ph0, ph1, ph2] net series."""
    rec = masks["recent"]
    net1, net2 = nets[1.0], nets[2.0]
    sr_net = sr(net1, rec)
    sr_gross = sr(gross, rec)
    net_pct = T.placebo_pct(sr_net, T.sr_rows(net_pl, rec)) if net_pl is not None else None
    gr_pct = T.placebo_pct(sr_gross, T.sr_rows(gross_pl, rec)) if gross_pl is not None else None
    rob = T.robustness(net1, net2, dates, masks, gr_pct)
    if phase_nets:
        ph = [sr(p, rec) for p in phase_nets]
        rob["d_phase_sharpes"] = [r4(x) for x in ph]
        rob["d_ok"] = bool(sum(1 for x in ph if x == x and x > 0) >= 2)
        rob["d_offsets"] = "0,+1,+2 minutes"
        rob["score"] = int(rob["score"]) + int(rob["d_ok"])
    d = T.dsr_of(net1[rec], dsr_args["var_sr"], dsr_args["n_eff"])
    v4 = v4_check(net1, dates)
    out = {
        "label": label,
        "sr_net_recent": r4(sr_net),
        "sr_gross_recent": r4(sr_gross),
        "net_placebo_pct": r4(net_pct),
        "gross_placebo_pct": r4(gr_pct),
        "dsr": r4(d["dsr"]),
        "sr0_annual_null": r4(d["sr0_annual"]),
        "robustness": rob,
        "V3_cost2x_recent_ann_net_gt0": bool(np.nanmean(net2[rec]) * 252 > 0),
        "V4": v4,
    }
    vetoes = []
    if not out["V3_cost2x_recent_ann_net_gt0"]:
        vetoes.append("cost2x")
    if v4.get("done") and (v4["21d"]["veto"] or v4["63d"]["veto"]):
        vetoes.append("V4_stress")
    if rob["e_z"] and min(rob["e_z"]) <= -3.0:
        vetoes.append("recent_break")
    out["vetoes"] = vetoes
    out["v4_missing"] = not v4.get("done")
    tier = T.tier_p1(d["dsr"], net_pct, rob["score"])
    tier["P1_paper_incubation"] = bool(
        tier["P1_paper_incubation"] and not vetoes and v4.get("done")
    )
    out["tier"] = tier
    # observation-sleeve rule of the brief: no veto, cost x2 net positive, net placebo pct >= 0.9
    out["observation_sleeve_eligible"] = bool(
        not vetoes
        and out["V3_cost2x_recent_ann_net_gt0"]
        and net_pct is not None
        and net_pct >= 0.9
    )
    return out


def median_of_top3(srs: dict) -> str:
    """Selection rule: the median-Sharpe key among the three highest finite recent net Sharpes."""
    items = [(k, v) for k, v in srs.items() if v == v]
    items.sort(key=lambda kv: kv[1], reverse=True)
    return items[min(1, len(items) - 1)][0] if items else None
