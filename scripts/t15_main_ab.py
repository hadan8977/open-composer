"""T-20261006-15 groups A and B on the amended main grid (amendment-2026-10-06-main-grid.md).

Reads data/features/t15_work/ab_<SYM>.npz written by run_t20261006_15_intraday_rules.py build-ab.
Writes reports/research/iterations/t20261006_15_intraday_rules/results_ab_main.json.
"""

from __future__ import annotations

import json
import math
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_t20261006_15_intraday_rules as R  # noqa: E402
import t15_engine as E  # noqa: E402
import t15_grid as G  # noqa: E402
import t15_stats as T  # noqa: E402

OUT = ROOT / "reports/research/iterations/t20261006_15_intraday_rules/results_ab_main.json"
BASKETS = {
    "B1_spy": ["SPY"],
    "B3_spy_qqq_iwm": ["SPY", "QQQ", "IWM"],
    "B15": G.ETFS_INDEX + G.ETFS_SECTOR,
}
EXPLORATORY = {
    "QQQ_only": ["QQQ"],
    "SPY_QQQ": ["SPY", "QQQ"],
}  # added after seeing the full-grid medians; counted
A_MAIN = [(k, m, vt) for k in R.MAIN_K for m in R.MAIN_M for vt in (0, 1)]
B_MAIN = [(p, th) for p in ("r1_overnight", "r1_plus_r12") for th in (0.0, 0.5)]
A_ANCHOR = (30, 1.0, 1)
B_ANCHOR = ("r1_overnight", 0.0)
SEEDS = 100
rng_seed = 20261006


def _r(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def weights(arr, symbols, dates_len):
    sig = []
    for s in symbols:
        r = pd.Series(arr[s]["daily_ret"])
        sig.append(r.rolling(60, min_periods=40).std().shift(1).to_numpy())
    w = 1.0 / np.stack(sig)
    w = np.where(np.isfinite(w), w, 0.0)
    tot = w.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(tot > 0, w / tot, np.nan)
    return w  # (n, D)


def basket(series: list[np.ndarray], w: np.ndarray) -> np.ndarray:
    """Risk-weighted average over symbols; NaN symbols drop out, weights renormalise."""
    X = np.stack(series)
    ok = np.isfinite(X) & np.isfinite(w) & (w > 0)
    ww = np.where(ok, w, 0.0)
    tot = ww.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(tot > 0, (np.where(ok, X, 0.0) * ww).sum(axis=0) / tot, np.nan)
    return out


def lev_of(z, vt):
    if not vt:
        return np.ones_like(z["lev"])
    return np.where(np.isfinite(z["lev"]), z["lev"], 1.0)


def a_symbol_series(z, k, m, vt, mult, ph=0):
    L = lev_of(z, vt)
    return L * (z[f"G_k{k}_m{m}_ph{ph}"] - mult * z[f"C_k{k}_m{m}_ph{ph}"])


def metrics(
    net_by_mult: dict, gross: np.ndarray, entries: np.ndarray, gross_unlev_sum_entry, masks, dates
):
    rec = masks["recent"]
    n1 = net_by_mult[1.0]
    d = {
        "gross_bp_day": _r(np.nanmean(gross[rec]) * 1e4),
        "cost_bp_day": _r((np.nanmean(gross[rec]) - np.nanmean(n1[rec])) * 1e4),
        "net_bp_day": _r(np.nanmean(n1[rec]) * 1e4),
        "sr_net_recent": {
            f"x{m}": _r(T.sr_rows(net_by_mult[m][None, :], rec)[0]) for m in E.COST_MULTS
        },
        "sr_gross_recent": _r(T.sr_rows(gross[None, :], rec)[0]),
        "sr_net_diag_2016_2023": _r(T.sr_rows(n1[None, :], masks["diag_2016_2023"])[0]),
        "phase_sr_net": {
            f"P{i:02d}": _r(T.sr_rows(n1[None, :], masks[f"P{i:02d}"])[0]) for i in range(1, 12)
        },
        "entries_per_day": _r(np.nanmean(entries[rec])),
    }
    g, e = gross_unlev_sum_entry
    d["gross_bp_per_entry"] = _r(g / e * 1e4) if e > 0 else None
    cb, gb = d["cost_bp_day"], d["gross_bp_day"]
    d["cost_share_of_gross"] = _r(cb / gb) if gb and gb > 0 else None
    t = T.nw(n1[rec])
    d["t_newey_west"] = _r(t["t_newey_west"])
    d["t_iid"] = _r(t["t_iid"])
    d["ann_net_ret"] = _r(np.nanmean(n1[rec]) * 252)
    return d


def v4_check(net: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    m = (dates >= pd.Timestamp("2017-10-02")) & (dates <= pd.Timestamp("2023-08-31"))
    x = np.nan_to_num(net[m], nan=0.0)
    out = {"sessions": int(m.sum())}
    sd = x.std(ddof=1)
    for w, name, veto, warn in ((21, "21d", 5.0, 4.0), (63, "63d", 4.0, 3.0)):
        c = np.convolve(x, np.ones(w), mode="valid")
        worst = float(c.min())
        vol = sd * math.sqrt(w)
        ratio = -worst / vol if vol > 0 else float("nan")
        out[name] = {
            "worst_sum": _r(worst),
            "vol_over_window": _r(vol),
            "loss_over_vol": _r(ratio),
            "veto": bool(ratio > veto),
            "warn": bool(ratio > warn),
        }
    return out


def eval_candidate(label, net1, net2, gross, masks, dates, net_pl, gross_pl, dsr_args):
    rec = masks["recent"]
    sr_net = T.sr_rows(net1[None, :], rec)[0]
    sr_gross = T.sr_rows(gross[None, :], rec)[0]
    net_pct = T.placebo_pct(sr_net, T.sr_rows(net_pl, rec)) if net_pl is not None else None
    gr_pct = T.placebo_pct(sr_gross, T.sr_rows(gross_pl, rec)) if gross_pl is not None else None
    rob = T.robustness(net1, net2, dates, masks, gr_pct)
    d = T.dsr_of(net1[rec], *dsr_args)
    out = {
        "sr_net_recent": _r(sr_net),
        "net_placebo_pct": _r(net_pct),
        "gross_placebo_pct": _r(gr_pct),
        "dsr": _r(d["dsr"]),
        "psr0": _r(d["psr0"]),
        "sr0_annual_null": _r(d["sr0_annual"]),
        "robustness": rob,
        "V3_cost2x_recent_ann_net_gt0": bool(np.nanmean(net2[rec]) * 252 > 0),
        "V4": v4_check(net1, dates),
    }
    out["tier"] = T.tier_p1(d["dsr"], net_pct, rob["score"])
    return out


def run(symbols: list[str]) -> dict:
    master, arr = R.load_ab(symbols)
    masks = E.window_masks(master)
    rec = masks["recent"]
    D = len(master)
    rng = np.random.default_rng(rng_seed)
    res = {
        "generated_for": "amendment-2026-10-06-main-grid",
        "symbols_loaded": symbols,
        "baskets": {},
    }

    # ---------------------------------------------------------------- A
    point_series = {}  # (basket, variant) -> net x1 (for var_sr / n_eff)
    a_tab = {}
    for bname, bsyms in {**BASKETS, **EXPLORATORY}.items():
        syms = [s for s in bsyms if s in arr]
        if len(syms) < len(bsyms) and bname != "B1_spy":
            if not syms:
                continue
        if not syms:
            continue
        w = weights(arr, syms, D)
        rows = {}
        for k, m, vt in A_MAIN:
            nets = {
                mu: basket([a_symbol_series(arr[s], k, m, vt, mu) for s in syms], w)
                for mu in E.COST_MULTS
            }
            gross = basket([lev_of(arr[s], vt) * arr[s][f"G_k{k}_m{m}_ph0"] for s in syms], w)
            ent = basket([arr[s][f"N_k{k}_m{m}_ph0"] for s in syms], w)
            gsum = float(np.nansum(basket([arr[s][f"G_k{k}_m{m}_ph0"] for s in syms], w)[rec]))
            esum = float(np.nansum(ent[rec]))
            rows[(k, m, vt)] = {
                "nets": nets,
                "gross": gross,
                "ent": ent,
                "m": metrics(nets, gross, ent, (gsum, esum), masks, master),
            }
            point_series[("A", bname, (k, m, vt))] = nets[1.0]
        a_tab[bname] = (syms, w, rows)

    # B
    b_tab = {}
    for bname, bsyms in {
        **BASKETS,
        "SPY_only": ["SPY"],
        "QQQ_only": ["QQQ"],
        "SPY_QQQ": ["SPY", "QQQ"],
    }.items():
        syms = [s for s in bsyms if s in arr]
        if not syms or len(syms) < len(bsyms):
            continue
        w = weights(arr, syms, D)
        rows = {}
        bspecs = list(product(G.B_PRED, G.B_THRESH))
        for pr, th in B_MAIN:
            i = bspecs.index((pr, th))
            nets = {
                mu: basket([arr[s]["Gb"][i] - mu * arr[s]["Cb"][i] for s in syms], w)
                for mu in E.COST_MULTS
            }
            gross = basket([arr[s]["Gb"][i] for s in syms], w)
            ent = basket([arr[s]["Nb"][i] for s in syms], w)
            gsum = float(np.nansum(gross[rec]))
            esum = float(np.nansum(ent[rec]))
            rows[(pr, th)] = {
                "nets": nets,
                "gross": gross,
                "ent": ent,
                "m": metrics(nets, gross, ent, (gsum, esum), masks, master),
                "i": i,
            }
            point_series[("B", bname, (pr, th))] = nets[1.0]
        b_tab[bname] = (syms, w, rows)

    # DSR inputs per group (points = variants x baskets)
    def group_args(g, n_total_points):
        keys = [k for k in point_series if k[0] == g]
        X = np.stack([point_series[k] for k in keys])
        srs = T.sr_rows(X, rec)
        var_sr = float(np.nanvar(srs, ddof=1)) if len(srs) > 1 else 0.0
        c = np.nan_to_num(X[:, rec], nan=0.0)
        c = c[np.std(c, axis=1) > 0]
        rho = float(np.mean(np.corrcoef(c)[np.triu_indices(len(c), 1)])) if len(c) > 1 else 1.0
        return {
            "points": len(keys),
            "var_sr": var_sr,
            "mean_corr": rho,
            "n_eff": 1 + (n_total_points - 1) * (1 - rho),
        }

    na = sum(1 for k in point_series if k[0] == "A")
    nb = sum(1 for k in point_series if k[0] == "B")
    ga, gb = group_args("A", na), group_args("B", nb)
    n_eff_total = (
        ga["n_eff"] + gb["n_eff"] + 18 + 16
    )  # C, D not yet run: counted as independent points
    dsr_args = {"A": (ga["var_sr"], n_eff_total), "B": (gb["var_sr"], n_eff_total)}
    res["dsr_inputs"] = {
        "A": ga,
        "B": gb,
        "n_eff_total_incl_C_D_as_independent": n_eff_total,
        "total_counted_points_main": na + nb + 18 + 16,
        "A_points": na,
        "B_points": nb,
    }

    # A candidates
    for bname, (syms, w, rows) in a_tab.items():
        srs = {key: rows[key]["m"]["sr_net_recent"]["x1.0"] for key in rows}
        order = sorted(rows, key=lambda q: -(srs[q] if srs[q] is not None else -9))
        sel = order[1]
        entry = {
            "symbols": syms,
            "variants": {},
            "selected": list(sel),
            "top3": [list(q) for q in order[:3]],
        }
        for key, v in rows.items():
            entry["variants"][f"k{key[0]}_M{key[1]}_vt{key[2]}"] = v["m"]
        for tag, key in (("anchor_paper", A_ANCHOR), ("selected", sel)):
            v = rows[key]
            k, m, vt = key
            net_pl, gross_pl = a_placebos(arr, syms, w, k, m, vt, rec, rng)
            ph_sr = {}
            for ph in (0, 1, 2):
                s_ph = basket([a_symbol_series(arr[s], k, m, vt, 1.0, ph) for s in syms], w)
                ph_sr[f"phase_{ph}"] = _r(T.sr_rows(s_ph[None, :], rec)[0])
            ev = eval_candidate(
                tag,
                v["nets"][1.0],
                v["nets"][2.0],
                v["gross"],
                masks,
                master,
                net_pl,
                gross_pl,
                dsr_args["A"],
            )
            ev["d_check_phases_recent_sr"] = ph_sr
            ev["d_check_ok_ge2_positive"] = sum(1 for x in ph_sr.values() if x and x > 0) >= 2
            # replace score's d with the real check
            rb = ev["robustness"]
            rb["d_offsets"] = ev["d_check_ok_ge2_positive"]
            rb["score"] = (
                int(rb["a_cost2x_ratio"])
                + int(rb["b_up_state_sharpe_gt0"])
                + int(rb["c_ok"])
                + int(ev["d_check_ok_ge2_positive"])
                + int(rb["e_ok"])
                + int(rb["f_ok"])
            )
            ev["tier"] = T.tier_p1(ev["dsr"], ev["net_placebo_pct"], rb["score"])
            entry[tag] = {"spec": {"interval": k, "mult": m, "vol_target": vt}, **ev}
        res["baskets"].setdefault("A", {})[bname] = entry

    # B candidates
    for bname, (syms, w, rows) in b_tab.items():
        srs = {key: rows[key]["m"]["sr_net_recent"]["x1.0"] for key in rows}
        order = sorted(rows, key=lambda q: -(srs[q] if srs[q] is not None else -9))
        sel = order[1]
        entry = {
            "symbols": syms,
            "variants": {f"{k[0]}_th{k[1]}": rows[k]["m"] for k in rows},
            "selected": list(sel),
            "top3": [list(q) for q in order[:3]],
        }
        for tag, key in (("anchor_paper", B_ANCHOR), ("selected", sel)):
            v = rows[key]
            net_pl, gross_pl = b_placebos(arr, syms, w, v["i"], rec, rng)
            ev = eval_candidate(
                tag,
                v["nets"][1.0],
                v["nets"][2.0],
                v["gross"],
                masks,
                master,
                net_pl,
                gross_pl,
                dsr_args["B"],
            )
            ev["d_offsets_note"] = (
                "B trades once at a fixed time; phase offsets not applicable, d scored as n/a"
            )
            entry[tag] = {"spec": {"predictor": key[0], "threshold": key[1]}, **ev}
        res["baskets"].setdefault("B", {})[bname] = entry

    # B regression reproduction (per symbol, three windows)
    reg = {}
    for s in symbols:
        z = arr[s]
        reg[s] = {}
        for wname, msk in (
            ("2016_2022", (master <= pd.Timestamp("2022-12-30"))),
            ("2023_2026", (master >= pd.Timestamp("2023-01-03"))),
            ("recent_2024", rec),
        ):
            reg[s][wname] = ols_b(z, msk)
    res["B_regression"] = reg
    return res


def ols_b(z, msk) -> dict:
    y = z["r13"][msk]
    out = {}
    for name, cols in (
        ("r1_overnight", ["r1_overnight"]),
        ("r1_overnight+r12", ["r1_overnight", "r12"]),
    ):
        X = np.column_stack([np.ones(msk.sum())] + [z[c][msk] for c in cols])
        ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
        Xo, yo = X[ok], y[ok]
        if len(yo) < 100:
            out[name] = None
            continue
        beta, *_ = np.linalg.lstsq(Xo, yo, rcond=None)
        e = yo - Xo @ beta
        r2 = 1 - e.var() / yo.var()
        # Newey-West (5 lags) t of the slopes
        XtXi = np.linalg.inv(Xo.T @ Xo)
        Xe = Xo * e[:, None]
        Smat = Xe.T @ Xe
        for lag in range(1, 6):
            wgt = 1 - lag / 6.0
            G_ = Xe[lag:].T @ Xe[:-lag]
            Smat += wgt * (G_ + G_.T)
        cov = XtXi @ Smat @ XtXi
        t = beta / np.sqrt(np.diag(cov))
        out[name] = {
            "n": int(len(yo)),
            "beta": [_r(b, 5) for b in beta[1:]],
            "t_nw": [_r(x) for x in t[1:]],
            "r2": _r(r2, 5),
        }
    return out


def a_placebos(arr, syms, w, k, m, vt, rec, rng):
    """Random direction per entry (trade) with identical timing, size and cost, SEEDS draws."""
    nets, grs = [], []
    idx = np.flatnonzero(rec)
    for s in syms:
        z = arr[s]
        seg = np.nan_to_num(z[f"seg_k{k}_m{m}"][idx])  # (Dr, J)
        tid = z[f"tid_k{k}_m{m}"][idx].astype(int)
        T_ = max(1, tid.max() + 1)
        sign = rng.choice([-1.0, 1.0], size=(SEEDS, len(idx), T_))
        j = np.where(tid >= 0, tid, 0)
        gat = np.take_along_axis(sign, np.broadcast_to(j, (SEEDS,) + j.shape), axis=2)
        gat = np.where(tid[None] >= 0, gat, 0.0)
        gpl = (seg[None] * gat).sum(axis=2)  # (S, Dr)
        L = lev_of(z, vt)[idx][None, :]
        cost = np.nan_to_num(z[f"C_k{k}_m{m}_ph0"][idx])[None, :]
        grs.append(L * gpl)
        nets.append(L * (gpl - cost))
    ww = w[:, idx]

    def comb(lst):
        out = np.zeros((SEEDS, len(idx)))
        for sd in range(SEEDS):
            out[sd] = basket([x[sd] for x in lst], ww)
        return out

    full_net = np.full((SEEDS, rec.size), np.nan)
    full_gr = np.full((SEEDS, rec.size), np.nan)
    full_net[:, idx] = comb(nets)
    full_gr[:, idx] = comb(grs)
    return full_net, full_gr


def b_placebos(arr, syms, w, i, rec, rng):
    idx = np.flatnonzero(rec)
    nets, grs = [], []
    for s in syms:
        z = arr[s]
        g = np.nan_to_num(z["Gb"][i][idx])
        c = np.nan_to_num(z["Cb"][i][idx])
        act = np.abs(z["Pb"][i][idx]) > 0
        # real direction is sign(P) * (exit/entry-1); random direction: +-1 on active days
        sign = rng.choice([-1.0, 1.0], size=(SEEDS, len(idx)))
        gpl = np.where(act[None], g[None] * sign, 0.0)
        grs.append(gpl)
        nets.append(gpl - c[None])
    ww = w[:, idx]
    full_net = np.full((SEEDS, rec.size), np.nan)
    full_gr = np.full((SEEDS, rec.size), np.nan)
    for sd in range(SEEDS):
        full_net[sd, idx] = basket([x[sd] for x in nets], ww)
        full_gr[sd, idx] = basket([x[sd] for x in grs], ww)
    return full_net, full_gr


if __name__ == "__main__":
    syms = sys.argv[1:]
    out = run(syms)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("wrote", OUT)
