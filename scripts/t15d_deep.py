# ruff: noqa: E501, E741
"""T-20261006-15-D assembly: metrics for the 16 main-grid points, selection (2nd of top 3 per basket),
placebos, phase/latency, robustness grid, V4, DSR, P1 tier, signal-level information table.

    scripts/heavy_run.sh --mem 0.8G -- uv run python scripts/t15d_deep.py [--skip-stock-robustness]

Writes reports/research/iterations/t20261006_15_intraday_rules/results_d.json and trial-ledger-d.jsonl
(only those two files). Robustness series are cached under data/features/t15_work/d_acc/rob_*.npz.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15_engine as E  # noqa: E402
import t15_main_ab as M  # noqa: E402
import t15_stats as T  # noqa: E402
import t15d_engine as X  # noqa: E402
import t15d_run as R  # noqa: E402

ITER = ROOT / "reports/research/iterations/t20261006_15_intraday_rules"
OUT = ITER / "results_d.json"
LEDGER = ITER / "trial-ledger-d.jsonl"
MASTER = R.MASTER
MASKS = E.window_masks(MASTER)
REC = MASKS["recent"]
ROB_DIR = R.ACC_DIR


def _r(x, nd=4):
    return M._r(x, nd)


def sr1(x: np.ndarray, mask: np.ndarray) -> float:
    return float(T.sr_rows(np.asarray(x)[None, :], mask)[0])


def net_of(a: dict, mult: float = 1.0) -> np.ndarray:
    return a["g"] - (mult * a["cv"] + a["cf"]) / 1e4 / float(a["N"])


def cluster_t(day: np.ndarray, x: np.ndarray) -> float | None:
    """t of the mean of x with standard error clustered by entry day."""
    n = len(x)
    if n < 10:
        return None
    m = x.mean()
    df = pd.DataFrame({"d": day, "e": x - m}).groupby("d")["e"].sum().to_numpy()
    se = math.sqrt(float((df**2).sum())) / n
    return float(m / se) if se > 0 else None


def mde_sharpe(n_sessions: int, power_z: float = 2.486) -> float:
    """Smallest annual Sharpe detected with 80% power at one-sided 5%: (1.645 + 0.842) x SE of the
    annual Sharpe under the null (Lo 2002 iid SE at SR = 0, i.e. sqrt(1 / years)); the SR^2/2 term of the
    exact SE is ignored, so the true detectable Sharpe is a little higher."""
    return power_z * math.sqrt(252.0 / n_sessions)


def point_metrics(a: dict) -> dict:
    N = float(a["N"])
    nets = {mu: net_of(a, mu) for mu in E.COST_MULTS}
    n1 = nets[1.0]
    g = a["g"]
    rec_tr = a["tr_day"] >= R.RECENT_IDX0
    gbp = a["tr_g"][rec_tr]
    cbp = a["tr_c"][rec_tr]
    gm = float(np.nanmean(g[REC]))
    cm = float(gm - np.nanmean(n1[REC]))
    cost1 = (a["cv"] + a["cf"]) / 1e4 / N
    pl_net = a["pl_g"] - cost1[None, :]
    rd_net = a["rd_g"] - a["rd_c"]
    sr_net = sr1(n1, REC)
    sr_gross = sr1(g, REC)
    rd_mean = np.where(a["rd_n"] > 0, a["rd_sum"] / np.maximum(a["rd_n"], 1), np.nan)
    tn = T.nw(n1[REC])
    out = {
        "trades_recent": int(rec_tr.sum()),
        "trades_per_day": _r(np.nanmean(a["ent"][REC])),
        "gross_bp_per_trade": _r(gbp.mean()) if len(gbp) else None,
        "gross_bp_per_trade_t_day_cluster": _r(cluster_t(a["tr_day"][rec_tr], gbp))
        if len(gbp)
        else None,
        "cost_bp_per_trade_roundtrip_x1": _r(cbp.mean()) if len(cbp) else None,
        "cost_share_of_gross": _r(cm / gm) if gm > 0 else None,
        "long_share_of_trades": _r(float((a["tr_side"][rec_tr] > 0).mean())) if len(gbp) else None,
        "sr_net_recent": {f"x{mu}": _r(sr1(nets[mu], REC)) for mu in E.COST_MULTS},
        "sr_gross_recent": _r(sr_gross),
        "sr_net_diag_2016_2023": _r(sr1(n1, MASKS["diag_2016_2023"])),
        "phase_sr_net": {f"P{i:02d}": _r(sr1(n1, MASKS[f"P{i:02d}"])) for i in range(1, 12)},
        "ann_net_ret": _r(np.nanmean(n1[REC]) * 252),
        "net_bp_day": _r(np.nanmean(n1[REC]) * 1e4),
        "gross_bp_day": _r(gm * 1e4),
        "t_newey_west": _r(tn["t_newey_west"]),
        "placebo_random_direction": {
            "net_pct": _r(T.placebo_pct(sr_net, T.sr_rows(pl_net, REC))),
            "gross_pct": _r(T.placebo_pct(sr_gross, T.sr_rows(a["pl_g"], REC))),
        },
        "placebo_same_slot_random_day": {
            "net_pct": _r(T.placebo_pct(sr_net, T.sr_rows(rd_net, REC))),
            "gross_pct": _r(T.placebo_pct(sr_gross, T.sr_rows(a["rd_g"], REC))),
            "trade_gross_bp_pct": _r(
                T.placebo_pct(float(gbp.mean()), rd_mean[np.isfinite(rd_mean)])
                if len(gbp)
                else None
            ),
            "control_gross_bp_per_trade_mean": _r(np.nanmean(rd_mean)),
        },
    }
    return out, n1, g, cost1, pl_net, rd_net


def info_row(a: dict) -> dict:
    rec_tr = a["tr_day"] >= R.RECENT_IDX0
    gbp = a["tr_g"][rec_tr]
    rd_mean = np.where(a["rd_n"] > 0, a["rd_sum"] / np.maximum(a["rd_n"], 1), np.nan)
    rd_mean = rd_mean[np.isfinite(rd_mean)]
    n1 = net_of(a, 1.0)
    return {
        "trades_recent": int(rec_tr.sum()),
        "gross_bp_per_trade": _r(gbp.mean()) if len(gbp) else None,
        "t_day_cluster": _r(cluster_t(a["tr_day"][rec_tr], gbp)) if len(gbp) else None,
        "control_same_slot_random_day_bp_per_trade": _r(rd_mean.mean()) if len(rd_mean) else None,
        "excess_over_control_bp": _r(gbp.mean() - rd_mean.mean())
        if len(gbp) and len(rd_mean)
        else None,
        "excess_pct_vs_control_distribution": _r(
            T.placebo_pct(float(gbp.mean()), rd_mean) if len(gbp) and len(rd_mean) else None
        ),
        "sr_net_recent": _r(sr1(n1, REC)),
        "sr_gross_recent": _r(sr1(a["g"], REC)),
        "cost_bp_per_trade_roundtrip_x1": _r(a["tr_c"][rec_tr].mean()) if len(gbp) else None,
    }


def qqq_noiseband_daily() -> np.ndarray | None:
    p = X.WORK / "ab_QQQ.npz"
    if not p.exists():
        return None
    z = np.load(p)
    dates = pd.DatetimeIndex(z["dates"])
    if not dates.equals(MASTER):
        return None
    needed = ("G_k30_m1.0_ph0", "C_k30_m1.0_ph0", "lev")
    if any(k not in z.files for k in needed):
        return None
    lev = np.where(np.isfinite(z["lev"]), np.minimum(z["lev"], 1.0), 1.0)
    return lev * (z["G_k30_m1.0_ph0"].astype(float) - z["C_k30_m1.0_ph0"].astype(float))


def corr_with(x: np.ndarray, y: np.ndarray | None) -> float | None:
    if y is None:
        return None
    m = REC & np.isfinite(x) & np.isfinite(y)
    if m.sum() < 50 or np.std(x[m]) == 0 or np.std(y[m]) == 0:
        return None
    return _r(float(np.corrcoef(x[m], y[m])[0, 1]))


def rob_series(bname, period, dirn, sig, key: str, **kw) -> dict:
    p = ROB_DIR / f"rob_{bname}_{period}_{dirn}_{sig}_{key}.npz"
    if p.exists():
        return R.Acc.load(p)
    a = R.series_sum(bname, period, dirn, sig, **kw)
    ROB_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(p, **a)
    return a


def robustness_grid(period: str) -> list[tuple[str, dict]]:
    H0 = R.PERIODS[period]["H"]
    Hs = (6, 13, 26) if period == "1h" else (30, 90, 180)
    exits = ("time_stop", "time_stop_or_reverse", "atr_trailing_2x")
    out = []
    for H in Hs:
        for ex in exits:
            if H == H0 and ex == "time_stop":
                continue
            out.append((f"H{H}_{ex}", dict(H=H, exit_rule=ex)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-stock-robustness", action="store_true")
    ap.add_argument("--stock-v4", default=None, help="path to stock V4 daily net npz (optional)")
    args = ap.parse_args()
    bks = {k: v for k, v in R.baskets().items() if k in ("QQQ_SPY", "TOP50")}
    qb = qqq_noiseband_daily()

    # ---------------- 16 main-grid points
    points: dict[str, dict] = {}
    nets_main: dict[str, np.ndarray] = {}
    accs: dict[str, dict] = {}
    for bname in bks:
        for period in R.PERIODS:
            for dirn in R.DIRS:
                for sig in R.SIGS:
                    name = f"main|{dirn}|{sig}"
                    a = R.Acc.load(R.acc_path(bname, period, name))
                    m, n1, g, cost1, pl_net, rd_net = point_metrics(a)
                    key = f"{bname}|{period}|{dirn}|{sig}"
                    points[key] = {
                        "basket": bname,
                        "period": period,
                        "direction": dirn,
                        "signal": sig,
                        "hold_bars": R.PERIODS[period]["H"],
                        "exit": "time_stop",
                        **m,
                        "corr_with_qqq_noiseband_recent": corr_with(n1, qb),
                    }
                    nets_main[key] = n1
                    accs[key] = a
    keys = list(points)
    srs = np.array([points[k]["sr_net_recent"]["x1.0"] for k in keys], float)
    X16 = np.stack([nets_main[k] for k in keys])
    var_sr = float(np.nanvar(srs, ddof=1))
    c = np.nan_to_num(X16[:, REC], nan=0.0)
    c = c[np.std(c, axis=1) > 0]
    rho = float(np.mean(np.corrcoef(c)[np.triu_indices(len(c), 1)]))
    n_eff_D_own = 1 + (len(keys) - 1) * (1 - rho)
    ab = json.loads((ITER / "results_ab_main.json").read_text())["dsr_inputs"]
    n_eff_A, n_eff_B = ab["A"]["n_eff"], ab["B"]["n_eff"]

    # ---------------- selection per basket (2nd of top-3 by recent net Sharpe x1)
    selected: dict[str, dict] = {}
    for bname in bks:
        ks = [k for k in keys if points[k]["basket"] == bname]
        order = sorted(ks, key=lambda k: -(points[k]["sr_net_recent"]["x1.0"] or -9))
        selected[bname] = {"top3": order[:3], "selected": order[1], "order": order}

    # ---------------- deep checks for the selected specs
    rob_all: dict[str, dict] = {}
    n_rob = 0
    for bname, sel in selected.items():
        key = sel["selected"]
        p = points[key]
        period, dirn, sig = p["period"], p["direction"], p["signal"]
        d: dict = {"spec": {"basket": bname, "period": period, "direction": dirn, "signal": sig}}
        # phase / latency (d item)
        ph = {"phase_0": p["sr_net_recent"]["x1.0"]}
        if period == "1h":
            for phase in (1, 2):
                a = rob_series(bname, period, dirn, sig, f"phase{phase}", H=13, phase=phase)
                ph[f"phase_{phase}"] = _r(sr1(net_of(a), REC))
            d["phase_definition"] = "1h bars anchored 09:30 + 0/1/2 minutes (indicator recomputed)"
        else:
            for dl in (1, 2):
                a = rob_series(bname, period, dirn, sig, f"delay{dl}", H=90, delay=dl)
                ph[f"phase_{dl}"] = _r(sr1(net_of(a), REC))
            d["phase_definition"] = (
                "1m: fill delayed by 0/1/2 bars (a 1-minute chart has no anchor to shift)"
            )
        d["phase_recent_sr_net"] = ph
        d["d_ok_ge2_positive"] = sum(1 for v in ph.values() if v is not None and v > 0) >= 2
        n_rob += 2
        # hold / exit robustness
        rob = {}
        for rkey, kw in robustness_grid(period):
            if bname == "TOP50" and args.skip_stock_robustness:
                continue
            a = rob_series(bname, period, dirn, sig, rkey, **kw)
            rob[rkey] = {
                "sr_net_recent_x1": _r(sr1(net_of(a), REC)),
                "sr_net_recent_x2": _r(sr1(net_of(a, 2.0), REC)),
                "sr_gross_recent": _r(sr1(a["g"], REC)),
                "trades_per_day": _r(np.nanmean(a["ent"][REC])),
            }
            n_rob += 1
        if bname == "TOP50" and not args.skip_stock_robustness:
            a = rob_series(
                bname,
                period,
                dirn,
                sig,
                "all_open_snapshot",
                H=R.PERIODS[period]["H"],
                alt_open=True,
            )
            rob["all_fills_use_open_spread"] = {
                "sr_net_recent_x1": _r(sr1(net_of(a), REC)),
                "sr_gross_recent": _r(sr1(a["g"], REC)),
            }
            n_rob += 1
        d["robustness_hold_exit"] = rob
        d["robustness_positive_share"] = _r(
            float(
                np.mean(
                    [
                        v["sr_net_recent_x1"] > 0
                        for v in rob.values()
                        if v["sr_net_recent_x1"] is not None
                    ]
                )
            )
            if rob
            else None
        )
        rob_all[bname] = d

    n_eff_total = n_eff_A + n_eff_B + 18 + 16 + n_rob
    n_eff_total_own = n_eff_A + n_eff_B + 18 + n_eff_D_own + n_rob

    # ---------------- evaluate the selected specs
    candidates: dict[str, dict] = {}
    for bname, sel in selected.items():
        key = sel["selected"]
        p = points[key]
        a = accs[key]
        n1 = nets_main[key]
        n2 = net_of(a, 2.0)
        g = a["g"]
        cost1 = (a["cv"] + a["cf"]) / 1e4 / float(a["N"])
        pl_net = a["pl_g"] - cost1[None, :]
        sr_n = sr1(n1, REC)
        net_pct = T.placebo_pct(sr_n, T.sr_rows(pl_net, REC))
        gross_pct = T.placebo_pct(sr1(g, REC), T.sr_rows(a["pl_g"], REC))
        rd_pct = p["placebo_same_slot_random_day"]["net_pct"]
        rob = T.robustness(n1, n2, MASTER, MASKS, gross_pct)
        d_ok = rob_all[bname]["d_ok_ge2_positive"]
        rob["d_offsets"] = d_ok
        rob["score"] = (
            int(rob["a_cost2x_ratio"])
            + int(rob["b_up_state_sharpe_gt0"])
            + int(rob["c_ok"])
            + int(d_ok)
            + int(rob["e_ok"])
            + int(rob["f_ok"])
        )
        dsr = T.dsr_of(n1[REC], var_sr, n_eff_total)
        dsr_own = T.dsr_of(n1[REC], var_sr, n_eff_total_own)
        # V4
        if bname == "QQQ_SPY":
            v4 = M.v4_check(n1, MASTER)
            v4_veto = v4["21d"]["veto"] or v4["63d"]["veto"]
            v4_warn = v4["21d"]["warn"] or v4["63d"]["warn"]
            v4_state = "computed"
        elif args.stock_v4 and Path(args.stock_v4).exists():
            z = np.load(args.stock_v4)
            v4 = M.v4_check(z["net"], MASTER)
            v4_veto = v4["21d"]["veto"] or v4["63d"]["veto"]
            v4_warn = v4["21d"]["warn"] or v4["63d"]["warn"]
            v4_state = "computed"
        else:
            v4 = None
            v4_veto = None
            v4_warn = None
            v4_state = "not_run"
        v3_veto = not bool(np.nanmean(n2[REC]) * 252 > 0)
        tier = T.tier_p1(dsr["dsr"], net_pct, rob["score"])
        other_ok = tier["P1_paper_incubation"]
        vetoed = bool(v3_veto or v4_veto)
        p1 = bool(other_ok and not vetoed and v4_state == "computed")
        candidates[bname] = {
            "key": key,
            "spec": p["period"] + " " + p["direction"] + " " + p["signal"],
            "sr_net_recent": _r(sr_n),
            "sr_gross_recent": p["sr_gross_recent"],
            "gross_bp_per_trade": p["gross_bp_per_trade"],
            "cost_share_of_gross": p["cost_share_of_gross"],
            "trades_per_day": p["trades_per_day"],
            "net_placebo_pct_random_direction": _r(net_pct),
            "gross_placebo_pct_random_direction": _r(gross_pct),
            "net_placebo_pct_same_slot_random_day": rd_pct,
            "dsr": _r(dsr["dsr"]),
            "dsr_with_D_own_correlation": _r(dsr_own["dsr"]),
            "sr0_annual_null": _r(dsr["sr0_annual"]),
            "psr0": _r(dsr["psr0"]),
            "robustness": rob,
            "V3_cost2x_veto": v3_veto,
            "V4": v4,
            "V4_state": v4_state,
            "V4_veto": v4_veto,
            "V4_warn": v4_warn,
            "tier_P1_inputs": tier,
            "P1_other_criteria_met": other_ok,
            "P1_paper_incubation": p1,
            "power": {
                "sessions_recent": int(REC.sum()),
                "min_detectable_annual_sharpe_80pct": _r(mde_sharpe(int(REC.sum()))),
            },
        }

    # ---------------- information table (single-signal, aligned direction)
    info: dict = {}
    for bname in bks:
        for period in R.PERIODS:
            for sg in R.INFO_SIGNALS:
                a = R.Acc.load(R.acc_path(bname, period, f"info|{sg}"))
                info[f"{bname}|{period}|{sg}"] = info_row(a)

    # ---------------- scale-curve supplement: top-10 / top-25 stock baskets (not part of the frozen 16)
    scale: dict = {}
    for bname in ("TOP10", "TOP25"):
        for period in R.PERIODS:
            for dirn in R.DIRS:
                for sig in R.SIGS:
                    p_ = R.acc_path(bname, period, f"main|{dirn}|{sig}")
                    if not p_.exists():
                        continue
                    a = R.Acc.load(p_)
                    m, *_ = point_metrics(a)
                    scale[f"{bname}|{period}|{dirn}|{sig}"] = {
                        k: m[k]
                        for k in (
                            "trades_recent",
                            "trades_per_day",
                            "gross_bp_per_trade",
                            "cost_share_of_gross",
                            "sr_net_recent",
                            "sr_gross_recent",
                            "placebo_random_direction",
                            "placebo_same_slot_random_day",
                        )
                    }
    n_rob += len(scale)

    # ---------------- ledger
    ts = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%MZ")
    rows = []
    for k, p in points.items():
        rows.append(
            {
                "ts": ts,
                "group": "D",
                "kind": "main_grid_point",
                "id": k,
                "sr_net_recent_x1": p["sr_net_recent"]["x1.0"],
                "sr_gross_recent": p["sr_gross_recent"],
                "gross_bp_per_trade": p["gross_bp_per_trade"],
                "trades_recent": p["trades_recent"],
            }
        )
    rows.append(
        {
            "ts": ts,
            "group": "D",
            "kind": "robustness",
            "points": n_rob,
            "detail": "phase/latency, hold x exit, cost snapshot on the two selected specs",
        }
    )
    rows.append(
        {
            "ts": ts,
            "group": "D",
            "kind": "info_diagnostics_not_counted",
            "points": len(info),
            "detail": "single-signal runs, aligned direction",
        }
    )
    LEDGER.write_text("".join(json.dumps(r) + "\n" for r in rows))

    res = {
        "task": "T-20261006-15-D",
        "generated": ts,
        "frozen": "amendment-2026-10-06-main-grid.md",
        "recent_window": "2024-01-08..2026-10-06",
        "sessions_recent": int(REC.sum()),
        "main_grid_points": points,
        "selection": {b: {k: v for k, v in s.items() if k != "order"} for b, s in selected.items()},
        "selected_candidates": candidates,
        "deep_checks": rob_all,
        "information_table": info,
        "scale_curve_supplement": scale,
        "dsr_inputs": {
            "var_sr_main_grid_D": _r(var_sr),
            "mean_pairwise_corr_D": _r(rho),
            "n_eff_D_own": _r(n_eff_D_own),
            "n_eff_A": _r(n_eff_A),
            "n_eff_B": _r(n_eff_B),
            "C_counted_independent": 18,
            "D_counted_independent": 16,
            "robustness_points_D": n_rob,
            "n_eff_total": _r(n_eff_total),
            "n_eff_total_with_D_own_corr": _r(n_eff_total_own),
        },
        "power": {
            "sessions_recent": int(REC.sum()),
            "min_detectable_annual_sharpe_80pct": _r(mde_sharpe(int(REC.sum()))),
        },
    }
    OUT.write_text(json.dumps(res, indent=1, default=str) + "\n")
    print("wrote", OUT, LEDGER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
