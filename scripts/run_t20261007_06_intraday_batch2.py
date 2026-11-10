# ruff: noqa: E501
"""T-20261007-06 runner. Subcommands: g3, g2, g1, corr, merge.

Run through scripts/heavy_run.sh --mem 0.8G. Writes one JSON per group under the iteration dir
(results_g1.json, ...), candidate daily nets to candidate_series.npz, then `merge` builds results.json.
Nothing after 2026-09-15 is read. Results are written once per group; re-running overwrites the group file.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import t0706_costs as C  # noqa: E402
import t0706_engines as EN  # noqa: E402
import t0706_eval as V  # noqa: E402
import t0706_grid as G  # noqa: E402
import t15_engine as E  # noqa: E402

ITER = "t20261007_06_intraday_batch2"
D = ROOT / "reports/research/iterations" / ITER
SERIES = D / "candidate_series.npz"
CM = C.CostModel()
MULTS = (0.5, 1.0, 2.0, 4.0)
SEED = 20261007


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def save_series(name: str, master: pd.DatetimeIndex, net: np.ndarray) -> None:
    store = dict(np.load(SERIES, allow_pickle=False)) if SERIES.exists() else {}
    store["dates"] = master.values.astype("datetime64[D]").astype(np.int64)
    store[name] = np.asarray(net, float)
    tmp = SERIES.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, **store)
    tmp.replace(SERIES)


def dump(name: str, obj: dict) -> None:
    (D / f"results_{name}.json").write_text(json.dumps(obj, indent=1, default=float) + "\n")


def nets_from(piece: dict) -> dict[float, np.ndarray]:
    return {m: piece["gross"] - (m * piece["sp"] + piece["fx"]) for m in MULTS}


# ======================================================================================= G3
def run_g3() -> None:
    master = EN.master_index()
    masks = E.window_masks(master)
    rec = masks["recent"]
    panels = {s: EN.load_etf(s, ("o",)) for s in G.ETF15}
    log("g3 panels", len(panels))
    res = {"group": "G3", "variants": {}, "recent_sessions": int(rec.sum())}
    ser = {}
    rows = {}
    for p, e, x in [(p, e, x) for p in G.G3_PCT for e in G.G3_ENTRY for x in G.G3_EXIT]:
        key = f"G3|{G.G3_BASKET_MAIN}|p{int(p * 100)}|e{e}|x{x}"
        pc = EN.g3_series(panels, master, CM, G.INDEX4, p, e, x)
        nets = nets_from(pc)
        ser[key] = nets[1.0]
        rows[key] = (pc, nets, (p, e, x))
        res["variants"][key] = {
            "sr_net_recent": V.r4(V.sr(nets[1.0], rec)),
            "sr_gross_recent": V.r4(V.sr(pc["gross"], rec)),
            "trade_days": int((pc["trades"][rec] > 0).sum()),
        }
    srs = {
        k: v["sr_net_recent"] if v["sr_net_recent"] is not None else float("nan")
        for k, v in res["variants"].items()
    }
    sel = V.median_of_top3(srs)
    res["selected"] = sel
    res["top3"] = sorted(srs.items(), key=lambda kv: -(kv[1] if kv[1] == kv[1] else -9))[:3]
    p, e, x = rows[sel][2]
    n_trials = len(G.grid_g3()) + 2
    dsr_args = V.group_dsr_args([s[rec] for s in ser.values()], n_trials)
    res["dsr_inputs"] = dsr_args
    rng = np.random.default_rng(SEED)
    cands = {}
    for bname, basket in (("INDEX4", G.INDEX4), ("SPY", ["SPY"]), ("ETF15", G.ETF15)):
        pc = EN.g3_series(panels, master, CM, basket, p, e, x, placebo_rng=rng)
        nets = nets_from(pc)
        gp = pc["gross_placebo"]
        netp = gp - (pc["sp"] + pc["fx"])[None, :]
        phn = [nets[1.0]] + [
            net_of(EN.g3_series(panels, master, CM, basket, p, e, x, phase=ph)) for ph in (1, 2)
        ]
        ev = V.eval_candidate(
            f"G3_{bname}", nets, pc["gross"], masks, master, netp, gp, dsr_args, phn
        )
        m = V.metrics(nets, pc["gross"], pc["trades"], _gross_per_trade(pc, rec), masks)
        cands[bname] = {"spec": {"pct": p, "entry": e, "exit": x}, "metrics": m, "eval": ev}
        save_series(f"G3_{bname}", master, nets[1.0])
        log("g3", bname, ev["sr_net_recent"], ev["tier"]["P1_paper_incubation"])
    res["candidates"] = cands
    # depth: also report the three-point curve over baskets of the other main-grid specs
    dump("g3", res)


def net_of(pc):
    return pc["gross"] - (pc["sp"] + pc["fx"])


def _gross_per_trade(pc, rec) -> float | None:
    tr = np.nansum(pc["trades"][rec])
    return float(np.nansum(pc["gross"][rec] * pc["n"]) / tr * 1e4) if tr > 0 else None


# ======================================================================================= G2
def g2_stock_matrices(master_stock: pd.DatetimeIndex):
    """Pivot the small 5-minute extract (built once) into symbol-by-day matrices."""
    path = ROOT / "data/features/t0706_g2/panel.parquet"
    if not path.exists():
        build_g2_panel(path)
    d = pd.read_parquet(path)
    d = d[d["d"] <= G.DATA_END]
    syms = sorted(d["symbol"].unique())
    si = {s: i for i, s in enumerate(syms)}
    di = master_stock.get_indexer(pd.DatetimeIndex(d["d"]))
    ok = di >= 0
    d = d[ok]
    di = di[ok]
    sj = d["symbol"].map(si).to_numpy()
    shape = (len(master_stock), len(syms))

    def mat(col):
        m = np.full(shape, np.nan)
        m[di, sj] = d[col].to_numpy()
        return m

    return syms, {
        c: mat(c)
        for c in (
            "o0",
            "c65",
            "c71",
            "o72",
            "o73",
            "o74",
            "c76",
            "c77",
            "f0",
            "f71",
            "f72",
            "f76",
            "f73",
            "f74",
        )
    }


def build_g2_panel(path: Path) -> None:
    import duckdb

    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET memory_limit='400MB'")
    con.execute("SET threads=2")
    files = sorted((ROOT / "data/features/intraday5m").glob("20*/*.READY"))
    parts = []
    for f in files:
        pq = f.with_suffix(".parquet")
        y, m = int(pq.parent.name), int(pq.stem)
        if pd.Timestamp(y, m, 1) > G.DATA_END:
            continue
        q = f"""
        SELECT symbol, d,
          max(CASE WHEN bar=0 THEN open END) o0, max(CASE WHEN bar=65 THEN close END) c65,
          max(CASE WHEN bar=71 THEN close END) c71, max(CASE WHEN bar=72 THEN open END) o72,
          max(CASE WHEN bar=73 THEN open END) o73, max(CASE WHEN bar=74 THEN open END) o74,
          max(CASE WHEN bar=76 THEN close END) c76, max(CASE WHEN bar=77 THEN close END) c77,
          max(CASE WHEN bar=0 THEN filled END) f0, max(CASE WHEN bar=71 THEN filled END) f71,
          max(CASE WHEN bar=72 THEN filled END) f72, max(CASE WHEN bar=73 THEN filled END) f73,
          max(CASE WHEN bar=74 THEN filled END) f74, max(CASE WHEN bar=76 THEN filled END) f76
        FROM read_parquet('{pq}') WHERE d <= TIMESTAMP '{G.DATA_END.date()}'
          AND bar IN (0,65,71,72,73,74,76,77) GROUP BY symbol, d"""
        parts.append(con.execute(q).fetchdf())
        log("g2 panel month", y, m, len(parts[-1]))
    df = pd.concat(parts, ignore_index=True)
    df.to_parquet(path)


def g2_universe_rank(master_stock, syms) -> np.ndarray:
    u = pd.read_parquet(ROOT / "data/features/intraday5m/universe.parquet")
    u = u[u["month"] <= str(G.DATA_END)[:7]]
    si = {s: i for i, s in enumerate(syms)}
    rank = np.full((len(master_stock), len(syms)), np.nan)
    months = master_stock.to_period("M").astype(str)
    for mo, g in u.groupby("month"):
        rows = np.flatnonzero(months == mo)
        if not len(rows):
            continue
        cols = g["symbol"].map(si)
        ok = cols.notna()
        rank[np.ix_(rows, cols[ok].astype(int).to_numpy())] = g.loc[ok, "rank_in_pool"].to_numpy()[
            None, :
        ]
    return rank


def hs_matrix(syms, rank, snap: str) -> np.ndarray:
    b20 = CM.hs("", snap, "top20")
    b100 = CM.hs("", snap, "r21_100")
    b250 = CM.hs("", snap, "r101_250")
    b500 = CM.hs("", snap, "r251_500")
    hs = np.where(rank <= 20, b20, np.where(rank <= 100, b100, np.where(rank <= 250, b250, b500)))
    for j, s in enumerate(syms):
        r = CM.per_symbol.get(s, {}).get(snap)
        if r and r["n"] >= C.MIN_DAYS:
            hs[:, j] = r["med"]
    return hs


def g2_run_universe(sig_mats, r, hs_sum, valid, grouping, signal, placebo_seeds=0, rng_seed=SEED):
    """Daily series over the stock master index for one (grouping, signal); optional placebo."""
    sig = sig_mats[signal]
    nd = sig.shape[0]
    gross = np.zeros(nd)
    sp = np.zeros(nd)
    fx = np.zeros(nd)
    trades = np.zeros(nd)
    for i in range(nd):
        if valid[i].sum() < 6:
            continue
        g, s_, f_, n_ = EN.g2_day(sig[i], r[i], hs_sum[i], valid[i], grouping)
        gross[i], sp[i], fx[i], trades[i] = g, s_, f_, n_
    out = {"gross": gross, "sp": sp, "fx": fx, "trades": trades, "n": 1}
    if placebo_seeds:
        gp = np.zeros((placebo_seeds, nd))
        npl = np.zeros((placebo_seeds, nd))
        for i in range(nd):
            if valid[i].sum() < 6:
                continue
            for sd in range(placebo_seeds):
                rr = np.random.default_rng([rng_seed, sd, i])
                key = rr.random(sig.shape[1])
                g, s_, f_, _ = EN.g2_day(sig[i], r[i], hs_sum[i], valid[i], grouping, perm_key=key)
                gp[sd, i] = g
                npl[sd, i] = g - (s_ + f_)
        out["gross_placebo"] = gp
        out["net_placebo"] = npl
    return out


def run_g2() -> None:
    master = EN.master_index()
    masks = E.window_masks(master)
    rec = masks["recent"]
    res = {"group": "G2", "variants": {}, "recent_sessions": int(rec.sum()), "universes": {}}
    ser: dict[str, np.ndarray] = {}
    pieces: dict[str, dict] = {}

    # ---------------- ETF14 on the 1-minute panels (all phases at once, panels freed one by one)
    arrs = {ph: {} for ph in (0, 1, 2)}
    for s in G.ETF14:
        p = EN.load_etf(s, ("o", "c"))
        for ph in (0, 1, 2):
            arrs[ph][s] = {
                k: EN.put(master, p.dates, v[:, None])[:, 0]
                for k, v in EN.etf_g2_arrays(p, ph).items()
            }
        del p
    log("g2 etf arrays")

    def etf_mats(ph):
        mats = {
            k: np.stack([arrs[ph][s][k] for s in G.ETF14], axis=1)
            for k in ("pc_to_1500", "pc_to_1530", "open_to_1530", "r")
        }
        valid = np.stack([arrs[ph][s]["ok"] for s in G.ETF14], axis=1).astype(bool) & np.isfinite(
            mats["r"]
        )
        hs_sum = np.array([CM.hs(s, "1530", "etf") + CM.hs(s, "1555", "etf") for s in G.ETF14])[
            None, :
        ].repeat(len(master), 0)
        return mats, valid, hs_sum

    mats0, valid0, hs0 = etf_mats(0)
    for grouping in G.G2_GROUP:
        for signal in G.G2_SIGNAL:
            key = f"G2|ETF14|{grouping}|{signal}"
            pc = g2_run_universe_etf(mats0, valid0, hs0, grouping, signal)
            pieces[key] = pc
            ser[key] = pc["gross"] - (pc["sp"] + pc["fx"])
    # ---------------- TOP100 / TOP500 on the 5-minute extract (2023..2026-09-15)
    stock_master = master[master >= pd.Timestamp("2023-01-03")]
    syms, M = g2_stock_matrices(stock_master)
    rank = g2_universe_rank(stock_master, syms)
    log("g2 stock matrices", len(syms), len(stock_master))
    prev_c = np.vstack([np.full((1, len(syms)), np.nan), M["c77"][:-1]])
    # adjacent-session requirement: prev close must come from the previous master session (it does by construction)
    sigs = {
        "pc_to_1500": M["c65"] / prev_c - 1.0,
        "pc_to_1530": M["c71"] / prev_c - 1.0,
        "open_to_1530": M["c71"] / M["o0"] - 1.0,
    }
    r_ = M["c76"] / M["o72"] - 1.0
    hs_in = hs_matrix(syms, rank, "1530")
    hs_out = hs_matrix(syms, rank, "1555")
    hs_sum = hs_in + hs_out
    base_valid = (
        (M["f71"] == 0)
        & (M["f72"] == 0)
        & (M["f76"] == 0)
        & (M["f0"] == 0)
        & np.isfinite(r_)
        & np.isfinite(prev_c)
        & (prev_c >= 5.0)
    )
    for name in ("pc_to_1500", "pc_to_1530", "open_to_1530"):
        base_valid &= np.isfinite(sigs[name]) & (np.abs(sigs[name]) <= 0.35)
    unis = {"TOP100": base_valid & (rank <= 100), "TOP500": base_valid & (rank <= 500)}
    for u, valid in unis.items():
        for grouping in G.G2_GROUP:
            for signal in G.G2_SIGNAL:
                key = f"G2|{u}|{grouping}|{signal}"
                pc = g2_run_universe(sigs, r_, hs_sum, valid, grouping, signal)
                full = dict(pc)
                # outside 2023 the stock universes are not evaluated: NaN gross keeps V4 'not done'
                full["gross"] = EN.put(master, stock_master, pc["gross"][:, None], np.nan)[:, 0]
                full["sp"] = EN.put(master, stock_master, pc["sp"][:, None], np.nan)[:, 0]
                full["fx"] = EN.put(master, stock_master, pc["fx"][:, None], np.nan)[:, 0]
                full["trades"] = EN.put(master, stock_master, pc["trades"][:, None], 0.0)[:, 0]
                pieces[key] = full
                ser[key] = full["gross"] - (full["sp"] + full["fx"])
        log("g2 variants done", u)
    for key, pc in pieces.items():
        res["variants"][key] = {
            "sr_net_recent": V.r4(V.sr(ser[key], rec)),
            "sr_gross_recent": V.r4(V.sr(pc["gross"], rec)),
            "trades_per_day": V.r4(np.nanmean(pc["trades"][rec])),
        }
    n_trials = len(G.grid_g2())
    dsr_args = V.group_dsr_args([ser[k][rec] for k in ser], n_trials)
    res["dsr_inputs"] = dsr_args
    cands = {}
    for u in G.G2_UNIVERSE:
        srs = {
            k: res["variants"][k]["sr_net_recent"]
            if res["variants"][k]["sr_net_recent"] is not None
            else float("nan")
            for k in res["variants"]
            if k.startswith(f"G2|{u}|")
        }
        sel = V.median_of_top3(srs)
        _, _, grouping, signal = sel.split("|")
        pc = pieces[sel]
        nets = {m: pc["gross"] - (m * pc["sp"] + pc["fx"]) for m in MULTS}
        if u == "ETF14":
            rr = np.random.default_rng(SEED)
            gp = np.zeros((EN.SEEDS, len(master)))
            npl = np.zeros_like(gp)
            for i in range(len(master)):
                if valid0[i].sum() < 6:
                    continue
                for sd in range(EN.SEEDS):
                    key = rr.random(len(G.ETF14))
                    g, s_, f_, _ = EN.g2_day(
                        mats0[signal][i],
                        mats0["r"][i],
                        hs0[i],
                        valid0[i],
                        grouping,
                        perm_key=key,
                        slip_bp=C.ETF_SLIP_BP,
                    )
                    gp[sd, i] = g
                    npl[sd, i] = g - (s_ + f_)
            phn = [nets[1.0]]
            for ph in (1, 2):
                m_, v_, h_ = etf_mats(ph)
                q = g2_run_universe_etf(m_, v_, h_, grouping, signal)
                phn.append(q["gross"] - (q["sp"] + q["fx"]))
        else:
            valid = unis[u]
            q = g2_run_universe(sigs, r_, hs_sum, valid, grouping, signal, placebo_seeds=EN.SEEDS)
            gp = np.full((EN.SEEDS, len(master)), np.nan)
            npl = np.full((EN.SEEDS, len(master)), np.nan)
            ix = master.get_indexer(stock_master)
            gp[:, ix] = q["gross_placebo"]
            npl[:, ix] = q["net_placebo"]
            phn = [nets[1.0]] + _g2_stock_phases(
                sigs,
                M,
                rank,
                base_valid,
                valid,
                hs_in,
                hs_out,
                grouping,
                signal,
                master,
                stock_master,
            )
        ev = V.eval_candidate(f"G2_{u}", nets, pc["gross"], masks, master, npl, gp, dsr_args, phn)
        if u != "ETF14":
            ev["robustness"]["d_note"] = (
                "stock universes: entry shifted +5/+10 minutes (5-minute bars), deviation from 0/+1/+2 minutes"
            )
        m = V.metrics(nets, pc["gross"], pc["trades"], _g2_gross_per_trade(pc, rec), masks)
        cands[u] = {"selected": sel, "metrics": m, "eval": ev}
        save_series(f"G2_{u}", master, nets[1.0])
        log("g2", u, sel, ev["sr_net_recent"], ev["tier"]["P1_paper_incubation"])
    res["candidates"] = cands
    dump("g2", res)


def g2_run_universe_etf(mats, valid, hs_sum, grouping, signal, perm_keys=None):
    nd = len(valid)
    gross = np.zeros(nd)
    sp = np.zeros(nd)
    fx = np.zeros(nd)
    trades = np.zeros(nd)
    for i in range(nd):
        if valid[i].sum() < 6:
            continue
        gross[i], sp[i], fx[i], trades[i] = EN.g2_day(
            mats[signal][i], mats["r"][i], hs_sum[i], valid[i], grouping, slip_bp=C.ETF_SLIP_BP
        )
    return {"gross": gross, "sp": sp, "fx": fx, "trades": trades, "n": 1}


def _g2_stock_phases(
    sigs, M, rank, base_valid, valid, hs_in, hs_out, grouping, signal, master, stock_master
):
    outs = []
    ix = master.get_indexer(stock_master)
    for entry_col, f_col in (("o73", "f73"), ("o74", "f74")):
        r2 = M["c76"] / M[entry_col] - 1.0
        v2 = valid & (M[f_col] == 0) & np.isfinite(r2)
        pc = g2_run_universe(sigs, r2, hs_in + hs_out, v2, grouping, signal)
        net = np.full(len(master), np.nan)
        net[ix] = pc["gross"] - (pc["sp"] + pc["fx"])
        outs.append(net)
    return outs


def _g2_gross_per_trade(pc, rec) -> float | None:
    tr = np.nansum(pc["trades"][rec])
    return float(np.nansum(pc["gross"][rec]) / tr * 1e4) if tr > 0 else None


# ======================================================================================= G1
def run_g1() -> None:
    master = EN.master_index()
    masks = E.window_masks(master)
    rec = masks["recent"]
    months = master.to_period("M")
    pools = {}
    for name in G.G1_POOLS:
        syms = G.pool_symbols(name)
        mem = {s: np.zeros(len(master)) for s in syms}
        per_month = {}
        for mo in months.unique():
            per_month[mo] = set(G.pool_for_month(mo.year, mo.month, name))
        for s in syms:
            mem[s] = np.array([1.0 if s in per_month[mo] else 0.0 for mo in months])
        pools[name] = (syms, mem)
    union = sorted({s for syms, _ in pools.values() for s in syms})
    log("g1 union symbols", len(union))
    KM = [(k, m) for k in G.G1_INTERVAL for m in G.G1_MULT]
    store: dict[tuple, dict] = {}
    have = []
    for i, s in enumerate(union):
        path = ROOT / "data/features/t0706_minute" / f"{s}.parquet"
        if not path.exists():
            continue
        p = EN.load_stock_panel(s)
        have.append(s)
        for k, m in KM:
            z = EN.g1_symbol_pieces(p, CM, k, m)
            store[(s, k, m)] = {
                kk: EN.put(master, p.dates, vv[:, None], np.nan)[:, 0] for kk, vv in z.items()
            }
        del p
        if i % 10 == 0:
            log("g1 symbol", i, s)
    missing = [s for s in union if s not in have]
    log("g1 missing symbols", len(missing))
    npool = {"TOP5": 5, "TOP10": 10, "TOP20": 20, "LETF6": 6}

    def pool_series(name, k, m, phase_store=None):
        syms, mem = pools[name]
        st = phase_store or store
        gross = np.zeros(len(master))
        sp = np.zeros(len(master))
        fx = np.zeros(len(master))
        ent = np.zeros(len(master))
        for s in syms:
            z = st.get((s, k, m))
            if z is None:
                continue
            w = mem[s] / npool[name]
            lv = z["lev"]
            gross += np.nan_to_num(w * lv * z["gross"])
            sp += np.nan_to_num(w * lv * z["sp"])
            fx += np.nan_to_num(w * lv * z["fx"])
            ent += np.nan_to_num(w * z["entries"])
        return {"gross": gross, "sp": sp, "fx": fx, "trades": ent, "n": npool[name]}

    res = {
        "group": "G1",
        "variants": {},
        "recent_sessions": int(rec.sum()),
        "missing_symbols": missing,
    }
    ser = {}
    pcs = {}
    for name in G.G1_POOLS:
        for k, m in KM:
            key = f"G1|{name}|k{k}|M{m}"
            pc = pool_series(name, k, m)
            pcs[key] = pc
            ser[key] = pc["gross"] - (pc["sp"] + pc["fx"])
            res["variants"][key] = {
                "sr_net_recent": V.r4(V.sr(ser[key], rec)),
                "sr_gross_recent": V.r4(V.sr(pc["gross"], rec)),
                "entries_per_day": V.r4(np.nanmean(pc["trades"][rec])),
            }
    dsr_args = V.group_dsr_args([ser[k][rec] for k in ser], len(G.grid_g1()))
    res["dsr_inputs"] = dsr_args
    cands = {}
    rng = np.random.default_rng(SEED)
    for name in G.G1_POOLS:
        srs = {
            k: res["variants"][k]["sr_net_recent"]
            if res["variants"][k]["sr_net_recent"] is not None
            else float("nan")
            for k in res["variants"]
            if k.startswith(f"G1|{name}|")
        }
        sel = V.median_of_top3(srs)
        k = int(sel.split("|")[2][1:])
        m = float(sel.split("|")[3][1:])
        pc = pcs[sel]
        nets = {c: pc["gross"] - (c * pc["sp"] + pc["fx"]) for c in MULTS}
        # placebo: random direction per trade, detail pass for the pool's symbols
        syms, mem = pools[name]
        gp = np.zeros((EN.SEEDS, len(master)))
        for s in syms:
            path = ROOT / "data/features/t0706_minute" / f"{s}.parquet"
            if not path.exists():
                continue
            p = EN.load_stock_panel(s)
            z = EN.g1_symbol_pieces(p, CM, k, m, detail=True)
            absseg = np.nan_to_num(EN.put(master, p.dates, z["absseg"], 0.0))
            tid = EN.put(master, p.dates, z["tid"].astype(float), -1.0).astype(int)
            lev = EN.put(master, p.dates, z["lev"][:, None], 1.0)[:, 0]
            w = mem[s] / npool[name] * lev
            T_ = max(1, tid.max() + 1)
            sign = rng.choice([-1.0, 1.0], size=(EN.SEEDS, len(master), T_))
            j = np.where(tid >= 0, tid, 0)
            gat = np.take_along_axis(sign, np.broadcast_to(j, (EN.SEEDS,) + j.shape), axis=2)
            gat = np.where(tid[None] >= 0, gat, 0.0)
            gp += w[None, :] * (absseg[None] * gat).sum(axis=2)
            del p, sign, gat
        netp = gp - (pc["sp"] + pc["fx"])[None, :]
        # phases +1, +2 minutes for the pool at the selected (k, m)
        phn = [nets[1.0]]
        for ph in (1, 2):
            pst = {}
            for s in syms:
                path = ROOT / "data/features/t0706_minute" / f"{s}.parquet"
                if not path.exists():
                    continue
                p = EN.load_stock_panel(s)
                zz = EN.g1_symbol_pieces(p, CM, k, m, phase=ph)
                pst[(s, k, m)] = {
                    kk: EN.put(master, p.dates, vv[:, None], np.nan)[:, 0] for kk, vv in zz.items()
                }
                del p
            q = pool_series(name, k, m, pst)
            phn.append(q["gross"] - (q["sp"] + q["fx"]))
        ev = V.eval_candidate(
            f"G1_{name}", nets, pc["gross"], masks, master, netp, gp, dsr_args, phn
        )
        mt = V.metrics(nets, pc["gross"], pc["trades"], _g1_gross_per_trade(pc, rec), masks)
        cands[name] = {"selected": sel, "metrics": mt, "eval": ev}
        save_series(f"G1_{name}", master, nets[1.0])
        log("g1", name, sel, ev["sr_net_recent"], ev["tier"]["P1_paper_incubation"])
    res["candidates"] = cands
    dump("g1", res)


def _g1_gross_per_trade(pc, rec) -> float | None:
    tr = np.nansum(pc["trades"][rec])
    return float(np.nansum(pc["gross"][rec]) / tr * 1e4) if tr > 0 else None


# ======================================================================================= corr
def run_corr() -> None:
    """Correlation of every candidate's recent daily net with the QQQ noise band (T-15 A_paper, cap 1) and
    the combined G3 + noise band Sharpe (equal and inverse-vol)."""
    master = EN.master_index()
    masks = E.window_masks(master)
    rec = masks["recent"]
    p = E.Panel("QQQ", end=EN.DATA_END)
    sigma = E.noise_sigma(p, 14)
    paths = E.a_position_paths(p, sigma, 30, [1.0], ["both"])
    gross, cost, entries, _ = E.a_daily(p, 30, paths[(1.0, "both")])
    lev = np.where(np.isfinite(p.sigma_ret14), np.minimum(1.0, 0.02 / p.sigma_ret14), 1.0)
    qqq = EN.put(master, p.dates, (lev * (gross - cost))[:, None], np.nan)[:, 0]
    save_series("QQQ_noiseband_cap1", master, qqq)
    st = dict(np.load(SERIES))
    out = {"qqq_noiseband_sr_recent": V.r4(V.sr(qqq, rec)), "pairs": {}}
    for name, x in st.items():
        if name in ("dates", "QQQ_noiseband_cap1"):
            continue
        a, b = qqq[rec], x[rec]
        ok = np.isfinite(a) & np.isfinite(b)
        rho = float(np.corrcoef(a[ok], b[ok])[0, 1]) if ok.sum() > 20 else None
        row = {"corr_recent": V.r4(rho), "sr_candidate": V.r4(V.sr(x, rec)), "n": int(ok.sum())}
        if rho is not None:
            xa, qa = np.nan_to_num(x[rec]), np.nan_to_num(a)
            row["sr_combined_equal"] = V.r4(
                V.sr(0.5 * np.nan_to_num(x) + 0.5 * np.nan_to_num(qqq), rec)
            )
            wq, wx = 1 / np.std(qa), 1 / np.std(xa) if np.std(xa) > 0 else 0.0
            tot = wq + wx
            row["sr_combined_invvol"] = V.r4(
                V.sr((wx * np.nan_to_num(x) + wq * np.nan_to_num(qqq)) / tot, rec)
            )
        out["pairs"][name] = row
    # pairwise correlation among candidates
    names = [n for n in st if n not in ("dates", "QQQ_noiseband_cap1")]
    out["candidate_corr"] = {}
    for i, a_ in enumerate(names):
        for b_ in names[i + 1 :]:
            xa, xb = st[a_][rec], st[b_][rec]
            ok = np.isfinite(xa) & np.isfinite(xb)
            if ok.sum() > 20:
                out["candidate_corr"][f"{a_}|{b_}"] = V.r4(np.corrcoef(xa[ok], xb[ok])[0, 1])
    dump("corr", out)
    log("corr done", len(out["pairs"]))


def run_merge() -> None:
    res = {"iter_id": ITER, "data_end": str(G.DATA_END.date())}
    for g in ("g1", "g2", "g3", "corr"):
        p = D / f"results_{g}.json"
        if p.exists():
            res[g] = json.loads(p.read_text())
    (D / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    log("merged", [k for k in res if k.startswith("g") or k == "corr"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"g1": run_g1, "g2": run_g2, "g3": run_g3, "corr": run_corr, "merge": run_merge}[cmd]()
