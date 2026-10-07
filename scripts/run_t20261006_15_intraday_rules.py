"""T-20261006-15 runner: groups A and B (ETF minute panels). C and D have their own scripts.

  build-ab SYM...   compute every registered A and B version for the symbols, save daily series
  stats-ab          depth curves, selection rule, placebos, DSR -> results_ab.json

Work files: data/features/t15_work/ (not committed). Results: reports/research/iterations/<iter>/.
"""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t15_engine as E  # noqa: E402
import t15_grid as G  # noqa: E402

WORK = ROOT / "data/features/t15_work"
ITER_DIR = ROOT / "reports/research/iterations/t20261006_15_intraday_rules"


def a_specs():
    return list(product(G.A_LOOKBACK, G.A_INTERVAL, G.A_MULT, G.A_STOP))


def build_ab(symbol: str) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    p = E.Panel(symbol)
    nd = len(p.dates)
    specs = a_specs()
    Gm = np.zeros((len(specs), nd), np.float32)
    Cm = np.zeros((len(specs), nd), np.float32)
    Nm = np.zeros((len(specs), nd), np.float32)
    k_index = {s: i for i, s in enumerate(specs)}
    for lb in G.A_LOOKBACK:
        sig = E.noise_sigma(p, lb)
        for k in G.A_INTERVAL:
            paths = E.a_position_paths(p, sig, k, G.A_MULT, G.A_STOP)
            for (m, st), P in paths.items():
                g, c, n, _ = E.a_daily(p, k, P)
                i = k_index[(lb, k, m, st)]
                Gm[i], Cm[i], Nm[i] = g, c, n
    # main grid (amendment 1): L=14, stop both, k in {15,30}, M in {1,1.5}; check phases 0,+1,+2
    # and per-trade segments for the random-direction-per-entry placebo
    extra = {}
    sig14m = E.noise_sigma(p, 14)
    for k in MAIN_K:
        for ph in (0, 1, 2):
            paths = E.a_position_paths(p, sig14m, k, MAIN_M, ["both"], phase=ph)
            for m in MAIN_M:
                P = paths[(m, "both")]
                if ph == 0:
                    g, c, n, segg, tid = E.a_daily(p, k, P, phase=0, detail=True)
                    extra[f"seg_k{k}_m{m}"] = segg.astype(np.float32)
                    extra[f"tid_k{k}_m{m}"] = tid.astype(np.int8)
                else:
                    g, c, n, _ = E.a_daily(p, k, P, phase=ph)
                extra[f"G_k{k}_m{m}_ph{ph}"] = g.astype(np.float32)
                extra[f"C_k{k}_m{m}_ph{ph}"] = c.astype(np.float32)
                extra[f"N_k{k}_m{m}_ph{ph}"] = n.astype(np.float32)
    # paper base (opposite band) for reproduction, not a counted trial
    sig14 = E.noise_sigma(p, 14)
    base = E.a_position_paths(p, sig14, 30, [1.0], ["opp"])[(1.0, "opp")]
    gb, cb, nb, _ = E.a_daily(p, 30, base)
    # band-shift placebo for anchors (paper spec only), 30 minutes later profile
    sh = E.a_position_paths(p, sig14, 30, [1.0], ["both"], shift=30)[(1.0, "both")]
    gs, cs, ns, _ = E.a_daily(p, 30, sh)
    # B
    feats = E.b_features(p)
    bspecs = list(product(G.B_PRED, G.B_THRESH))
    Gb = np.zeros((len(bspecs), nd), np.float32)
    Cb = np.zeros_like(Gb)
    Nb = np.zeros_like(Gb)
    Pb = np.zeros_like(Gb)
    for i, (pr, th) in enumerate(bspecs):
        g, c, n, pos = E.b_daily(p, feats, pr, th)
        Gb[i], Cb[i], Nb[i], Pb[i] = g, c, n, pos
    np.savez_compressed(
        WORK / f"ab_{symbol}.npz",
        dates=p.dates.values.astype("datetime64[D]"),
        lev=E.vol_target_lev(p).astype(np.float32),
        Ga=Gm, Ca=Cm, Na=Nm,
        Gbase=gb.astype(np.float32), Cbase=cb.astype(np.float32), Nbase=nb.astype(np.float32),
        Gshift=gs.astype(np.float32), Cshift=cs.astype(np.float32), Nshift=ns.astype(np.float32),
        Gb=Gb, Cb=Cb, Nb=Nb, Pb=Pb, factor=p.factor, **extra,
        r1_intraday=feats["r1_intraday"], r1_overnight=feats["r1_overnight"], r12=feats["r12"],
        r13=feats["r13"], daily_ret=p.daily_ret, close=p.day_close, full_day=p.full_day,
    )  # fmt: skip
    print(symbol, "built", nd, flush=True)


MAIN_K = (15, 30)
MAIN_M = (1.0, 1.5)
PAPER_SPEC_A = (14, 30, 1.0, "both")  # (lookback, interval, mult, stop), vt=1


def load_ab(symbols: list[str]):
    """Return master dates and per-symbol arrays reindexed to the master calendar."""
    master = None
    out = {}
    for s in symbols:
        z = np.load(WORK / f"ab_{s}.npz")
        dates = pd.DatetimeIndex(z["dates"])
        if master is None:
            master = dates
        ix = master.get_indexer(dates)
        keep = ix >= 0
        d = {}
        for k in z.files:
            if k == "dates":
                continue
            a = z[k]
            if a.ndim == 2 and a.shape[0] == len(dates) and a.shape[1] != len(dates):
                full = np.full(
                    (len(master), a.shape[1]),
                    np.nan if a.dtype.kind == "f" else -1,
                    dtype=np.float64,
                )
                full[ix[keep]] = a[keep]
                d[k] = full
                continue
            if a.shape[-1] != len(dates):
                continue
            shape = a.shape[:-1] + (len(master),)
            full = np.full(shape, np.nan, dtype=np.float64 if a.dtype != bool else float)
            full[..., ix[keep]] = a[..., keep]
            d[k] = full
        out[s] = d
    return master, out


def a_rows_for(sym_arrays, symbol):
    """Version rows (vt x spec) for one symbol as net/gross/cost series and ids."""
    specs = a_specs()
    rows = []
    for vt in G.A_VT:
        L = sym_arrays["lev"] if vt else np.ones_like(sym_arrays["lev"])
        for i, (lb, k, m, st) in enumerate(specs):
            vid = f"A|{symbol}|m{m}|L{lb}|k{k}|{st}|vt{vt}"
            rows.append((vid, vt, i, L))
    return rows


def stats_ab(symbols: list[str]) -> dict:
    import t15_stats as S_  # noqa: F401

    globals()["S"] = S_
    master, arr = load_ab(symbols)
    masks = E.window_masks(master)
    rec = masks["recent"]
    specs = a_specs()
    nspec = len(specs)
    # ---------------- A: version table
    ver_ids, ver_meta = [], []
    NET = {m: [] for m in E.COST_MULTS}
    GROSS_L, COST_L, ENT, GROSS_U = [], [], [], []
    for s in symbols:
        z = arr[s]
        for vt in G.A_VT:
            L = z["lev"] if vt else np.ones_like(z["lev"])
            Lc = np.where(np.isfinite(L), L, 1.0)[None, :]
            for m in E.COST_MULTS:
                NET[m].append(Lc * (z["Ga"] - m * z["Ca"]))
            GROSS_L.append(Lc * z["Ga"])
            COST_L.append(Lc * z["Ca"])
            ENT.append(z["Na"])
            GROSS_U.append(z["Ga"])
            for i, (lb, k, mm, st) in enumerate(specs):
                ver_ids.append(f"A|{s}|m{mm}|L{lb}|k{k}|{st}|vt{vt}")
                ver_meta.append((s, vt, i, lb, k, mm, st))
    NETm = {m: np.concatenate(v, axis=0) for m, v in NET.items()}
    GRL = np.concatenate(GROSS_L, axis=0)
    CSL = np.concatenate(COST_L, axis=0)
    ENTM = np.concatenate(ENT, axis=0)
    GRU = np.concatenate(GROSS_U, axis=0)
    srs = {m: S_.sr_rows(NETm[m], rec) for m in E.COST_MULTS}
    sr_diag = S_.sr_rows(NETm[1.0], masks["diag_2016_2023"])
    sr_gross = S_.sr_rows(GRL, rec)
    phase_sr = np.stack([S_.sr_rows(NETm[1.0], masks[f"P{i:02d}"]) for i in range(1, 12)], axis=1)
    g_bp = np.nanmean(GRL[:, rec], axis=1) * 1e4
    c_bp = np.nanmean(CSL[:, rec], axis=1) * 1e4
    tr_day = np.nanmean(ENTM[:, rec], axis=1)
    sum_g_unlev = np.nansum(np.where(np.isfinite(GRU), GRU, 0.0)[:, rec], axis=1)
    sum_e = np.nansum(ENTM[:, rec], axis=1)
    rows = []
    for j, vid in enumerate(ver_ids):
        rows.append(
            {
                "id": vid,
                "gross_bp_day": round(float(g_bp[j]), 4),
                "cost_bp_day": round(float(c_bp[j]), 4),
                "net_bp_day": round(float(g_bp[j] - c_bp[j]), 4),
                "sr_net_recent_x1": _r(srs[1.0][j]),
                "sr_net_recent_x0.5": _r(srs[0.5][j]),
                "sr_net_recent_x2": _r(srs[2.0][j]),
                "sr_net_recent_x4": _r(srs[4.0][j]),
                "sr_gross_recent": _r(sr_gross[j]),
                "sr_net_diag_2016_2023": _r(sr_diag[j]),
                "phase_sr_net": [_r(x) for x in phase_sr[j]],
                "entries_per_day": _r(tr_day[j]),
                "gross_bp_per_entry": _r(
                    sum_g_unlev[j] / sum_e[j] * 1e4 if sum_e[j] > 0 else np.nan
                ),
                "cost_share_of_gross": _r(c_bp[j] / g_bp[j] if g_bp[j] > 0 else np.nan),
            }
        )
    var_sr_a = float(np.nanvar(srs[1.0], ddof=1))
    neff_a = S_.n_eff_estimate(NETm[1.0], rec, len(ver_ids) if len(symbols) == 17 else 3672)
    # ---------------- A: portfolios per depth set
    sets = {k: [s for s in v if s in symbols] for k, v in G.DEPTH_SETS.items()}
    sets = {k: v for k, v in sets.items() if v}
    port = {}
    for name, syms in sets.items():
        for vt in G.A_VT:
            for m in E.COST_MULTS:
                acc = []
                for s in syms:
                    z = arr[s]
                    L = z["lev"] if vt else np.ones_like(z["lev"])
                    L = np.where(np.isfinite(L), L, 1.0)[None, :]
                    acc.append(L * (z["Ga"] - m * z["Ca"]))
                port[(name, vt, m)] = np.nanmean(np.stack(acc), axis=0)  # (nspec, D)
            gacc = []
            for s in syms:
                z = arr[s]
                L = z["lev"] if vt else np.ones_like(z["lev"])
                L = np.where(np.isfinite(L), L, 1.0)[None, :]
                gacc.append(L * z["Ga"])
            port[(name, vt, "gross")] = np.nanmean(np.stack(gacc), axis=0)
    curves = {}
    cands = {}
    paper_i = specs.index(PAPER_SPEC_A)
    for name, syms in sets.items():
        both = np.concatenate([port[(name, 0, 1.0)], port[(name, 1, 1.0)]], axis=0)
        sr = S_.sr_rows(both, rec)
        order = np.argsort(-np.nan_to_num(sr, nan=-9))
        top3 = order[:3]
        sel = int(top3[1])  # median Sharpe of the top three

        def label(ix):
            vt, i = divmod(ix, nspec)
            lb, k, mm, st = specs[i]
            return {"vt": vt, "lookback": lb, "interval": k, "mult": mm, "stop": st, "index": ix}

        anchor_ix = nspec * 1 + paper_i
        curves[name] = {
            "symbols": syms,
            "n_symbols": len(syms),
            "anchor_sr_net_recent": _r(sr[anchor_ix]),
            "selected": label(sel),
            "selected_sr_net_recent": _r(sr[sel]),
            "best": label(int(order[0])),
            "best_sr_net_recent": _r(sr[order[0]]),
            "median_sr_over_216_specs": _r(np.nanmedian(sr)),
            "share_specs_sr_gt0": _r(np.mean(sr[np.isfinite(sr)] > 0)),
            "top3": [label(int(x)) | {"sr": _r(sr[x])} for x in top3],
        }
        cands[name] = {"anchor": anchor_ix, "selected": sel}
    return {
        "master": master,
        "masks": masks,
        "rows": rows,
        "var_sr_a": var_sr_a,
        "neff_a": neff_a,
        "NETm1": NETm[1.0],
        "port": port,
        "curves": curves,
        "cands": cands,
        "sets": sets,
        "arr": arr,
        "specs": specs,
    }


def _r(x, nd=4):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if np.isfinite(x) else None


def main(argv: list[str]) -> int:
    cmd = argv[0]
    if cmd == "build-ab":
        for s in argv[1:]:
            if (WORK / f"ab_{s}.npz").exists():
                print(s, "exists", flush=True)
                continue
            build_ab(s)
        return 0
    if cmd == "stats-ab-dev":
        import t15_stats as S_

        globals()["S"] = S_
        syms = argv[1:]
        r = stats_ab(syms)
        print(
            json.dumps(
                {"curves": r["curves"], "neff_a": r["neff_a"], "var_sr_a": r["var_sr_a"]}, indent=1
            )[:4000]
        )
        return 0
    if cmd == "versions-ab":
        import t15_stats as S_

        syms = argv[1:]
        r = stats_ab(syms)
        arr = r["arr"]
        masks = r["masks"]
        rec = masks["recent"]
        brows = []
        bspecs = list(product(G.B_PRED, G.B_THRESH))
        for s in syms:
            z = arr[s]
            for i, (pr, th) in enumerate(bspecs):
                g, c, n = z["Gb"][i], z["Cb"][i], z["Nb"][i]
                net = {m: g - m * c for m in E.COST_MULTS}
                ent = np.nansum(n[rec])
                brows.append(
                    {
                        "id": f"B|{s}|{pr}|th{th}",
                        "gross_bp_day": _r(np.nanmean(g[rec]) * 1e4),
                        "cost_bp_day": _r(np.nanmean(c[rec]) * 1e4),
                        "net_bp_day": _r(np.nanmean(net[1.0][rec]) * 1e4),
                        "sr_net_recent_x1": _r(S_.sr_rows(net[1.0][None], rec)[0]),
                        "sr_net_recent_x0.5": _r(S_.sr_rows(net[0.5][None], rec)[0]),
                        "sr_net_recent_x2": _r(S_.sr_rows(net[2.0][None], rec)[0]),
                        "sr_net_recent_x4": _r(S_.sr_rows(net[4.0][None], rec)[0]),
                        "sr_gross_recent": _r(S_.sr_rows(g[None], rec)[0]),
                        "sr_net_diag_2016_2023": _r(
                            S_.sr_rows(net[1.0][None], masks["diag_2016_2023"])[0]
                        ),
                        "phase_sr_net": [
                            _r(S_.sr_rows(net[1.0][None], masks[f"P{i:02d}"])[0])
                            for i in range(1, 12)
                        ],
                        "entries_per_day": _r(np.nanmean(n[rec])),
                        "gross_bp_per_entry": _r(
                            np.nansum(g[rec]) / ent * 1e4 if ent > 0 else np.nan
                        ),
                    }
                )
        out = {
            "A_versions": r["rows"],
            "B_versions": brows,
            "A_depth_curves_full_grid_216_specs": r["curves"],
            "var_sr_A_full_grid": r["var_sr_a"],
            "neff_A_full_grid": r["neff_a"],
            "note": "Full registered A/B grid (robustness set under amendment 1); "
            "not used to select the main-grid candidate.",
        }
        ITER_DIR.mkdir(parents=True, exist_ok=True)
        (ITER_DIR / "versions_ab.json").write_text(json.dumps(out) + "\n")
        print("wrote versions_ab.json", len(r["rows"]), len(brows), flush=True)
        return 0
    raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
