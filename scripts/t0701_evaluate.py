#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261007-01: evaluation of the preregistered grid from parquets only (no market data).

    uv run python scripts/t0701_evaluate.py --stage grid     # points, deltas vs B0, G1/G2/G4, selection, power
    uv run python scripts/t0701_evaluate.py --stage score    # selected point: placebo G3, net placebo, DSR, tier (after placebo files exist)

Contract: ``reports/research/iterations/t20261007_01_cost_aware_engine/hypotheses.md`` sections 3-6.
Series: ``data/research/t0701/T_<variant>_o<k>.parquet`` (I3 points have o0 only).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import realism_ladder_book_ls as T25  # noqa: E402
from scripts import t0701_engine as eng  # noqa: E402
from scripts.book_v14_ml_eval import (  # noqa: E402
    hac_t,
    vol_matched_diff,
    window_block,
)

ITER = eng.ITER
DATA = eng.OUT_DATA
OFFSETS = T25.OFFSETS
WINDOWS = {
    "recent": ("2024-01-08", "2026-09-15"),
    "stress": ("2017-10-02", "2023-08-31"),
    "stress_ml": ("2019-01-02", "2023-08-31"),
    "full": ("2017-10-02", "2026-09-15"),
    "full_ml": ("2019-01-02", "2026-09-15"),
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-15"),
}
G1_MIN = 0.10
G4_MAX_DROP = 0.20
RECENT_DAYS = 674


def jdump(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=1, default=float))


def load_frames(vid: str, base: Path = DATA) -> list[pd.DataFrame]:
    spec = eng.spec_by_id(vid)
    offs = (0,) if spec.daily else OFFSETS
    return [pd.read_parquet(eng.t_path(vid, o, base)) for o in offs]


def blend(frames: list[pd.DataFrame]) -> pd.DataFrame:
    return frames[0] if len(frames) == 1 else T25.blend(frames)


def sharpe_by_offset(frames: list[pd.DataFrame], w: tuple[str, str]) -> list[float]:
    return [T25.series_metrics(f, w)["net_sharpe"] for f in frames]


def stress_key(spec: eng.Spec) -> str:
    return "stress" if spec.start == eng.START_S0 else "stress_ml"


def full_key(spec: eng.Spec) -> str:
    return "full" if spec.start == eng.START_S0 else "full_ml"


def power_block(rho: float) -> dict:
    yrs = RECENT_DAYS / 252.0
    sd = math.sqrt(2.0 * (1.0 - rho) / yrs)
    return {"rho": rho, "sd_delta_sr": sd, "min_delta_sr_t2": 2.0 * sd}


def point_block(
    spec: eng.Spec,
    frames: list[pd.DataFrame],
    b0: list[pd.DataFrame],
    i0: list[pd.DataFrame] | None,
) -> dict:
    b0_blend = blend(b0)
    bl = blend(frames)
    out: dict = {
        "vid": spec.vid,
        "slow": spec.slow,
        "mode": spec.mode,
        "param": spec.param,
        "fast": spec.fast,
        "daily": spec.daily,
        "windows": {},
    }
    sk, fk = stress_key(spec), full_key(spec)
    for name in ("recent", sk, fk, "A", "B"):
        w = WINDOWS[name]
        wb = window_block(frames, w)
        ref = [T25.series_metrics(f, w)["net_sharpe"] for f in b0]
        cand = wb["net_sharpe_by_offset"]
        med_c = float(np.median(cand))
        med_b = float(np.median(ref))
        if len(frames) == 1:
            improved = int(sum(cand[0] > r for r in ref))
            diffs = [cand[0] - r for r in ref]
        else:
            diffs = [a - b for a, b in zip(cand, ref, strict=True)]
            improved = int(sum(d > 0 for d in diffs))
        wb["b0_net_sharpe_by_offset"] = ref
        wb["delta_offset_median"] = med_c - med_b
        wb["offsets_improved"] = improved
        wb["net_sharpe_diff_by_offset"] = diffs
        d = vol_matched_diff(bl["net"].loc[w[0] : w[1]], b0_blend["net"].loc[w[0] : w[1]])
        wb["paired_nw_t"] = hac_t(d.to_numpy(), 5)
        cc = pd.concat(
            [bl["net"].loc[w[0] : w[1]], b0_blend["net"].loc[w[0] : w[1]]], axis=1, join="inner"
        ).dropna()
        wb["corr_with_b0"] = float(cc.corr().iloc[0, 1])
        if i0 is not None and spec.mode != "I0":
            ref0 = [T25.series_metrics(f, w)["net_sharpe"] for f in i0]
            wb["delta_vs_slow_only_i0_offset_median"] = med_c - float(np.median(ref0))
        out["windows"][name] = wb
    rec, st = out["windows"]["recent"], out["windows"][sk]
    out["G1"] = bool(rec["delta_offset_median"] >= G1_MIN)
    out["G2"] = bool(rec["offsets_improved"] >= 4)
    out["G4_diag"] = bool(st["delta_offset_median"] >= -G4_MAX_DROP)
    out["power"] = power_block(rec["corr_with_b0"])
    out["recent_net_sharpe_offset_median"] = rec["net_sharpe_offset_median"]
    return out


def e_tests(res: dict, vid: str) -> dict:
    """v1.4 Stage B conditions E1, E2, E4 on the I0 points (stress_ml window), E5 from stage_a.json."""
    p = res["points"][vid]
    rec, st = p["windows"]["recent"], p["windows"]["stress_ml"]
    betas = {k: p["windows"][k] for k in ("recent", "stress_ml")}
    e1 = bool(rec["delta_offset_median"] >= 0.10 and st["delta_offset_median"] >= 0.10)
    e2 = bool(rec["offsets_improved"] >= 4 and st["offsets_improved"] >= 4)
    e4 = bool(all(abs(betas[k][b]) <= 0.15 for k in betas for b in ("beta_ols", "beta_dimson")))
    sa = ROOT / "reports/research/iterations/t20261004_book_v14_ml/stage_a.json"
    e5 = None
    if sa.exists():
        a = json.loads(sa.read_text())
        col = {"S2_I0": "m0m2", "S3_I0": "m0m3"}[vid]
        surv = a.get("stage_a_survivors", [])
        e5 = bool(col in surv) if surv else None
    return {
        "E1": e1,
        "E2": e2,
        "E4": e4,
        "E5": e5,
        "note": "E5 = Stage A survivor flag of v1.4; identity tolerance here 1e-9 on the same platform (v1.4 froze 1e-12)",
    }


def run_grid() -> dict:
    specs = eng.grid(include_f=True)
    by = {s.vid: s for s in specs}
    b0 = load_frames("B0")
    s2_i0 = load_frames("S2_I0")
    res: dict = {"points": {}, "b0": {}}
    res["b0"] = {
        "windows": {k: window_block(b0, w) for k, w in WINDOWS.items() if k != "stress_ml" or True}
    }
    for s in specs:
        if s.vid == "B0":
            continue
        try:
            fr = load_frames(s.vid)
        except FileNotFoundError:
            res["points"][s.vid] = {"vid": s.vid, "status": "not_run"}
            continue
        i0 = s2_i0 if s.slow == "m0m2" else None
        res["points"][s.vid] = point_block(s, fr, b0, i0)
    res["v14_stage_b_points"] = {
        v: e_tests(res, v) for v in ("S2_I0", "S3_I0") if "windows" in res["points"].get(v, {})
    }
    fast_pts = [
        v for v, p in res["points"].items() if "windows" in p and by[v].mode in ("I1", "I2", "I3")
    ]
    rank = sorted(fast_pts, key=lambda v: (-res["points"][v]["recent_net_sharpe_offset_median"], v))
    top3 = rank[:3]
    sel = top3[1] if len(top3) >= 2 else (top3[0] if top3 else None)
    res["selection"] = {
        "candidates_considered": len(fast_pts),
        "ranking": [(v, res["points"][v]["recent_net_sharpe_offset_median"]) for v in rank],
        "top3": top3,
        "selected": sel,
        "rule": "median (second) of the top three recent offset-median net Sharpe among the fast-element points",
    }
    # not-established rule
    s0 = [v for v in fast_pts if by[v].slow == "M0" and by[v].fast == "fc_ew"]
    s2 = [v for v in fast_pts if by[v].slow == "m0m2"]
    s0_nonpos = all(res["points"][v]["windows"]["recent"]["delta_offset_median"] <= 0 for v in s0)
    s2_nonpos = all(
        res["points"][v]["windows"]["recent"].get("delta_vs_slow_only_i0_offset_median", 0.0) <= 0
        for v in s2
    )
    res["not_established_rule"] = {
        "s0_all_delta_vs_b0_le_0": bool(s0_nonpos),
        "s2_all_delta_vs_s2_i0_le_0": bool(s2_nonpos),
        "all_points_present": bool(len(s0) == 9 and len(s2) == 9),
        "n_s0": len(s0),
        "n_s2": len(s2),
    }
    res["g_flags_selected"] = (
        None if sel is None else {k: res["points"][sel][k] for k in ("G1", "G2", "G4_diag")}
    )
    jdump(ITER / "results_grid.json", res)
    ledger = []
    for s in specs:
        if s.vid == "B0":
            continue
        p = res["points"].get(s.vid, {})
        ledger.append(
            {
                "candidate_id": s.vid,
                "status": "run" if "windows" in p else "not_run",
                "recent_net_sharpe_offset_median": p.get("recent_net_sharpe_offset_median"),
                "G1": p.get("G1"),
                "G2": p.get("G2"),
            }
        )
    jdump(
        ITER / "trial-ledger.json",
        {
            "iter_id": ITER.name,
            "trials": ledger,
            "n_registered": len(ledger),
            "n_run": sum(r["status"] == "run" for r in ledger),
        },
    )
    print("selected", sel, "top3", top3)
    return res


def win(x: pd.Series, w: tuple[str, str]) -> pd.Series:
    return x.loc[w[0] : w[1]]


def placebo_series(vid: str, target: str, seeds: range) -> dict[int, pd.DataFrame]:
    out = {}
    for sd in seeds:
        f = DATA / f"P_{vid}__{target}{sd:03d}_o0.parquet"
        if f.exists():
            out[sd] = pd.read_parquet(f)
    return out


def run_score() -> dict:
    from open_composer.research import scorecard_v2 as sc
    from scripts import book_v12_small as small

    grid_res = json.loads((ITER / "results_grid.json").read_text())
    sel = grid_res["selection"]["selected"]
    spec = eng.spec_by_id(sel)
    rw = WINDOWS["recent"]
    res: dict = {
        "selected": sel,
        "spec": {"slow": spec.slow, "mode": spec.mode, "param": spec.param, "fast": spec.fast},
    }
    frames = load_frames(sel)
    bl = blend(frames)
    b0 = load_frames("B0")
    b0bl = blend(b0)
    # ---- placebo: G3 and net percentile
    b0w = blend([pd.read_parquet(DATA / f"P_B0w_o{o}.parquet") for o in OFFSETS])
    sr_b0w = sc.annual_sharpe(win(b0w["net"], rw))
    pl: dict = {"b0_warm_start_recent_net_sharpe": sr_b0w}
    for target in ("fast", "full"):
        ser = placebo_series(sel, target, range(0, 101))
        real = ser.get(0)
        seeds = {k: v for k, v in ser.items() if k > 0}
        if real is None or len(seeds) < 100:
            pl[target] = {"status": "incomplete", "n_seeds": len(seeds)}
            continue
        real_sr = sc.annual_sharpe(win(real["net"], rw))
        net_sr = [sc.annual_sharpe(win(v["net"], rw)) for k, v in sorted(seeds.items())]
        gross_sr = [sc.annual_sharpe(win(v["gross"], rw)) for k, v in sorted(seeds.items())]
        block = {
            "status": "ok",
            "n_seeds": len(seeds),
            "real_warm_start_net_sharpe": real_sr,
            "seed_net_sharpes_mean": float(np.mean(net_sr)),
            "seed_net_sharpes_p90": float(np.quantile(net_sr, 0.90)),
            "seed_net_sharpes_max": float(np.max(net_sr)),
        }
        if target == "fast":
            inc_real = real_sr - sr_b0w
            inc_seeds = [x - sr_b0w for x in net_sr]
            block.update(
                {
                    "increment_real_vs_b0": inc_real,
                    "increment_percentile": sc.placebo_percentile(inc_real, inc_seeds),
                    "increment_seeds_mean": float(np.mean(inc_seeds)),
                    "G3": bool((sc.placebo_percentile(inc_real, inc_seeds) or 0) >= 0.90),
                }
            )
        else:
            block.update(
                {
                    "net_percentile": sc.placebo_percentile(real_sr, net_sr),
                    "gross_percentile": sc.placebo_percentile(
                        sc.annual_sharpe(win(real["gross"], rw)), gross_sr
                    ),
                }
            )
            block["_net"], block["_gross"] = net_sr, gross_sr
        pl[target] = block
    res["placebo"] = {
        k: ({a: b for a, b in v.items() if not a.startswith("_")} if isinstance(v, dict) else v)
        for k, v in pl.items()
    }
    # ---- DSR (own 23 points and family 19 + 23), correlations among all points
    pts = [v for v, p in grid_res["points"].items() if "windows" in p]
    series = {"B0": win(b0bl["net"], rw)}
    for v in pts:
        series[v] = win(blend(load_frames(v))["net"], rw)
    panel = pd.DataFrame(series).dropna()
    corr = panel.corr().to_numpy()
    iu = np.triu_indices(len(series), k=1)
    rho = float(corr[iu].mean())
    sharpes = {v: sc.annual_sharpe(series[v]) for v in pts}
    var_sr = float(np.var(list(sharpes.values()), ddof=1))
    dsr_own = sc.dsr(
        series[sel].to_numpy(), var_sr_annual=var_sr, n_eff=sc.n_eff_from_corr(len(pts), rho)
    )
    dsr_fam = sc.dsr(
        series[sel].to_numpy(), var_sr_annual=var_sr, n_eff=sc.n_eff_from_corr(19 + len(pts), rho)
    )
    res["dsr"] = {
        "n_points": len(pts),
        "mean_pairwise_corr": rho,
        "var_sr_annual": var_sr,
        "own": dsr_own,
        "family_19_plus_own": dsr_fam,
        "n_eff_own": sc.n_eff_from_corr(len(pts), rho),
        "n_eff_family": sc.n_eff_from_corr(19 + len(pts), rho),
    }
    # ---- score card for the vetoes and robustness (daily book replicated over five offsets)
    cfg = sc.load_config()
    rows, rows2 = [], []
    for v in ["B0", sel]:
        fr = load_frames(v)
        for o in OFFSETS:
            d = fr[o] if len(fr) > 1 else fr[0]
            base = pd.DataFrame({"date": d.index, "variant": v, "offset": o})
            rows.append(base.assign(net=d["net"].to_numpy(), gross=d["gross"].to_numpy()))
            rows2.append(
                base.assign(
                    net=(d["gross"] - 2.0 * d["cost"] - 4.0 * d["borrow"]).to_numpy(),
                    gross=float("nan"),
                )
            )
    returns, cost2x = pd.concat(rows), pd.concat(rows2)
    bil = pd.Series(0.0, index=pd.DatetimeIndex(returns["date"].unique()).sort_values())
    eb = T25.EB
    phases = json.loads((eb / "regimes/phases.json").read_text())["phases_recent"]
    state = pd.read_parquet(eb / "regimes/market_state.parquet")["state"]
    ident = json.loads((ITER / "identity.json").read_text())
    acct_ok = None
    afile = DATA / f"A_{sel}_1000000.parquet"
    if afile.exists():
        d = pd.read_parquet(afile).set_index("date")
        acct_ok = bool(small.v2_block(d)["v2_pass"])
    att = {v: {"V1": bool(ident["pass"]), "V2": acct_ok} for v in ("B0", sel)}
    placebo_in = {}
    full = pl.get("full", {})
    if full.get("status") == "ok":
        placebo_in[sel] = {"net": full["_net"], "gross": full["_gross"]}
    card = sc.score_family(
        returns,
        cost2x,
        bil,
        phases,
        state,
        placebo=placebo_in,
        attestations=att,
        n_trials=19 + len(pts),
    )
    c = card["variants"][sel]
    metrics = {
        "dsr": dsr_fam["dsr"],
        "signal_t": None,
        "placebo_net_pct": c["placebo"]["net_pct"],
        "placebo_gross_pct": c["placebo"]["gross_pct"],
        "robustness_score": c["robustness_score"],
    }
    tier, detail = sc._tier(cfg, metrics, c["vetoes_triggered"], c["vetoes_unassessed"])
    res["scorecard"] = {
        "tier": tier,
        "tier_detail": detail,
        "vetoes_triggered": c["vetoes_triggered"],
        "vetoes_unassessed": c["vetoes_unassessed"],
        "vetoes": c["vetoes"],
        "robustness": c["robustness"],
        "robustness_score": c["robustness_score"],
        "placebo": c["placebo"],
        "main_excess": c["inputs"]["main_excess"],
        "note": "daily-book point replicated over five offsets for the offset robustness item; signal-layer t not computed (not needed for P1); gross placebo percentile from the hash-rank placebo",
    }
    # ---- G flags
    p = grid_res["points"][sel]
    res["G"] = {
        "G1": p["G1"],
        "G2": p["G2"],
        "G3": pl.get("fast", {}).get("G3"),
        "G4_stress_delta_ok": p["G4_diag"],
        "V4_collapse_triggered": "V4" in c["vetoes_triggered"],
        "tier": tier,
    }
    res["paired_t"] = {
        k: p["windows"][k]["paired_nw_t"] for k in ("recent", stress_key(spec), full_key(spec))
    }
    res["power"] = p["power"]
    # ---- diagnostics (reported only)
    diag: dict = {}
    base_sr = p["windows"]["recent"]["net_sharpe_offset_median"]
    for tag in ("p1000", "moo", "nofast") + tuple(
        f"drop_{t}" for t in __import__("scripts.run_book_v1_stage2", fromlist=["THEMES"]).THEMES
    ):
        did = f"{sel}__{tag}"
        fl = [
            DATA / f"D_{did}_o{o}.parquet"
            for o in ((0,) if spec.daily and tag not in ("nofast",) else OFFSETS)
        ]
        if not all(f.exists() for f in fl):
            continue
        fr = [pd.read_parquet(f) for f in fl]
        sr = float(np.median(sharpe_by_offset(fr, rw)))
        diag[tag] = {"recent_net_sharpe_offset_median": sr, "delta_vs_selected": sr - base_sr}
    res["diagnostics"] = {"variants": diag}
    m = window_block(frames, rw)
    res["diagnostics"]["two_x_cost_net_sharpe_offset_median"] = m[
        "net_sharpe_2x_cost_offset_median"
    ]
    res["diagnostics"]["turnover_one_sided_ann"] = m["turnover_one_sided_ann"]
    res["diagnostics"]["cost_bp_yr"] = m["cost_bp_yr"]
    res["diagnostics"]["b0_turnover_one_sided_ann"] = window_block(b0, rw)["turnover_one_sided_ann"]
    res["diagnostics"]["b0_cost_bp_yr"] = window_block(b0, rw)["cost_bp_yr"]
    vs = bl["vix_scale"]
    flip = (vs != vs.shift(1)) & vs.shift(1).notna()
    cw = win(bl["cost"], rw)
    res["diagnostics"]["vix_flip_cost_share"] = (
        float(cw[win(flip, rw)].sum() / cw.sum()) if cw.sum() > 0 else None
    )
    a_, b_ = win(bl["net"], rw), win(b0bl["net"], rw)
    cc = pd.concat([a_, b_], axis=1, join="inner").dropna()
    res["diagnostics"]["corr_with_v12_recent"] = float(cc.corr().iloc[0, 1])
    res["diagnostics"]["tracking_error_ann_vol_matched"] = float(
        vol_matched_diff(a_, b_).std(ddof=1) * math.sqrt(252)
    )
    ladder = {}
    for cap in (300000, 1000000):
        f = DATA / f"A_{sel}_{cap}.parquet"
        if f.exists():
            d = pd.read_parquet(f).set_index("date")
            blk = small.v2_block(d)
            rec = d.loc[rw[0] : rw[1]]
            blk["dropped_order_share"] = float(
                rec["n_dropped"].sum() / max(rec["n_wanted"].sum(), 1)
            )
            blk["orders_per_day_mean"] = float(rec["n_orders"].mean())
            ladder[str(cap)] = blk
    res["diagnostics"]["capital_ladder_simplified_whole_share"] = ladder
    # ---- conclusion
    gflags = res["G"]
    ok_all = bool(
        gflags["G1"]
        and gflags["G2"]
        and gflags["G3"]
        and gflags["G4_stress_delta_ok"]
        and not gflags["V4_collapse_triggered"]
        and tier in ("P1", "P2")
    )
    ne = grid_res["not_established_rule"]
    if ok_all:
        concl = "established"
    elif (
        ne["all_points_present"]
        and ne["s0_all_delta_vs_b0_le_0"]
        and ne["s2_all_delta_vs_s2_i0_le_0"]
    ):
        concl = "not_established"
    else:
        concl = "not_deep_enough"
    res["conclusion"] = {"status": concl, "g_flags": gflags, "not_established_rule": ne}
    jdump(ITER / "results_score.json", res)
    print("conclusion", concl, gflags)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["grid", "score"])
    ns = ap.parse_args()
    if ns.stage == "grid":
        run_grid()
    else:
        run_score()


if __name__ == "__main__":
    main()
