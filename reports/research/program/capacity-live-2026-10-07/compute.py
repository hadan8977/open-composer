"""T-20261004-71 / R1005-T71: whole-share realizability by capital tier. Read-only; no broker calls."""
import json, math
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path("/root/codex-test/open-composer")
OUT = ROOT / "reports/research/program/capacity-live-2026-10-07"
CAPS = [10_000, 25_000, 50_000, 100_000, 250_000]
ETFS = {
    "S1": "us_etf_sector_rotation_252_top2_weekly",
    "S2": "us_etf_growth_rotation_blend_top2_monthly",
    "S3": "us_etf_levered_rotation_63_top2_monthly",
    "C2": "us_etf_eom_sector_blend_monthly",
}
ALLOC = {"S3": 0.60, "C2": 0.335, "F2": 0.12, "F1": 0.025}  # 10-02 allocation-dd30 decision
# V2 operational thresholds, fixed before looking at results (standard v2.1 gives no numbers)
V2_SHORT_RATIO_MIN = 0.90   # realized short gross / target
V2_REL_L1_MAX = 0.30        # sum|w_real-w_tgt| / sum|w_tgt| over the stock leg
V2_NET_LIMIT = 0.05         # engine RiskLimits.max_abs_net (open_composer/book_paper/plan.py:43)


def rha(x):
    return np.where(x == 0, 0.0, np.sign(x) * np.floor(np.abs(x) + 0.5))


def stock_leg(path):
    d = json.load(open(path))
    w = {s: v for s, v in d["weights"].items() if s not in (d["hedge_symbol"], d["core_symbol"])}
    px, ex = d["reference_prices"], d["exposures"]
    syms = [s for s in w if s in px and px[s] and px[s] > 0]
    return d, syms, np.array([w[s] for s in syms]), np.array([px[s] for s in syms]), \
        np.array([ex[s]["beta"] if s in ex and ex[s].get("beta") is not None else 1.0 for s in syms], dtype=float), \
        np.array([ex[s]["dollar_adv_21"] if s in ex and ex[s].get("dollar_adv_21") is not None else np.nan for s in syms], dtype=float)


def realize(w, p, C, mode):
    """mode: 'mixed' = fractional longs (>= $1), whole-share shorts; 'engine' = whole shares both sides, $100 min;
    'whole' = whole shares both sides, no minimum."""
    tgt = w * C / p
    q = tgt.copy()
    if mode == "mixed":
        short = w < 0
        q[short] = rha(tgt[short])
        q[(~short) & (np.abs(tgt) * p < 1.0)] = 0.0
    else:
        q = rha(tgt)
        if mode == "engine":
            q[np.abs(q) * p < 100.0] = 0.0
    return q


def metrics(w, p, beta, adv, C, mode):
    q = realize(w, p, C, mode)
    wr = q * p / C
    L, S = w > 0, w < 0
    tg_s, tg_l = -w[S].sum(), w[L].sum()
    rs, rl = -wr[S].sum(), wr[L].sum()
    rel_l1 = np.abs(wr - w).sum() / np.abs(w).sum()
    effn = lambda x: (np.abs(x).sum() ** 2 / (x ** 2).sum()) if (x ** 2).sum() > 0 else 0.0
    pos = np.abs(q) * p
    return {
        "n_long_target": int(L.sum()), "n_short_target": int(S.sum()),
        "short_zero_frac": float((q[S] == 0).mean()), "long_zero_frac": float((q[L] == 0).mean()),
        "short_gross_ratio": float(rs / tg_s), "long_gross_ratio": float(rl / tg_l),
        "net_dollar_err_pct_equity": float(wr.sum() - w.sum()),
        "net_beta_err_pct_equity": float((wr * beta).sum() - (w * beta).sum()),
        "rel_l1_error": float(rel_l1),
        "eff_n_short_real": float(effn(wr[S])), "eff_n_short_target": float(effn(w[S])),
        "max_pos_over_adv": float(np.nanmax(pos / adv)), "median_pos_over_adv": float(np.nanmedian(pos[pos > 0] / adv[pos > 0])),
    }


def v2(m):
    ok_short = m["short_gross_ratio"] >= V2_SHORT_RATIO_MIN
    ok_l1 = m["rel_l1_error"] <= V2_REL_L1_MAX
    ok_net = abs(m["net_dollar_err_pct_equity"]) <= V2_NET_LIMIT
    ok_adv = m["max_pos_over_adv"] <= 0.01
    return {"pass": bool(ok_short and ok_l1 and ok_net and ok_adv), "short_ratio_ok": bool(ok_short),
            "rel_l1_ok": bool(ok_l1), "net_dollar_ok": bool(ok_net), "adv_1pct_ok": bool(ok_adv)}


res = {"generated_at_utc": pd.Timestamp.utcnow().strftime("%Y-%m-%dT%H:%MZ"),
       "v2_thresholds": {"short_gross_ratio_min": V2_SHORT_RATIO_MIN, "rel_l1_max": V2_REL_L1_MAX,
                         "net_dollar_abs_max": V2_NET_LIMIT, "adv_frac_max": 0.01,
                         "note": "researcher operationalization of standard v2.1 V2; the standard text gives no numbers; fixed before computing"},
       "program_allocation_10_02": ALLOC, "capitals": CAPS, "stock_books": {}, "etf_sleeves": {},
       "small_n_feasibility": {}, "margin": {}}

# ---- stock books F1/F2 (and P1 proxy = F1 stock leg)
for form, q in (("F1", "quant1"), ("F2", "quant2")):
    path = ROOT / f"reports/paper/book/{q}/targets/2026-10-02.json"
    d, syms, w, p, beta, adv = stock_leg(path)
    res["stock_books"][form] = {"file": str(path.relative_to(ROOT)), "equity_basis": d["equity_basis"],
                                "core": [d["core_symbol"], d["core_weight"]], "hedge": [d["hedge_symbol"], d["hedge_weight"]],
                                "n_names": len(syms), "by_capital": {}}
    for C in CAPS:
        cell = {}
        for mode in ("mixed", "engine", "whole"):
            m = metrics(w, p, beta, adv, C, mode)
            m["v2"] = v2(m)
            cell[mode] = m
        res["stock_books"][form]["by_capital"][str(C)] = cell
        # margin: Reg T 50% of long+short MV, core/hedge sized exactly (liquid ETFs, fractional)
        wr = realize(w, p, C, "mixed") * p / C
        longs = wr[wr > 0].sum() + d["hedge_weight"] + d["core_weight"]
        shorts = -wr[wr < 0].sum()
        res["margin"].setdefault(form, {})[str(C)] = {"long_mv_over_equity": float(longs), "short_mv_over_equity": float(shorts),
                                                      "reg_t_initial_over_equity": float(0.5 * (longs + shorts))}
    # concentration feasibility (rounding only; performance cost not measured here)
    if form == "F1":
        order_s = np.argsort(w)           # most negative first
        order_l = np.argsort(-w)
        for N in (50, 100, 200, 300, 500):
            keep = np.zeros(len(w), bool)
            sidx = [i for i in order_s if w[i] < 0][:N]; lidx = [i for i in order_l if w[i] > 0][:N]
            keep[sidx] = True; keep[lidx] = True
            w2 = np.where(keep, w, 0.0)
            w2[w2 < 0] *= (-w[w < 0].sum()) / (-w2[w2 < 0].sum())
            w2[w2 > 0] *= (w[w > 0].sum()) / (w2[w2 > 0].sum())
            sel = w2 != 0
            row = {}
            for C in CAPS:
                m = metrics(w2[sel], p[sel], beta[sel], adv[sel], C, "mixed"); m["v2"] = v2(m)
                row[str(C)] = {k: m[k] for k in ("short_zero_frac", "short_gross_ratio", "rel_l1_error", "net_dollar_err_pct_equity")}
                row[str(C)]["v2_pass"] = m["v2"]["pass"]
            res["small_n_feasibility"][f"top{N}_per_side"] = row

# ---- ETF sleeves
for k, name in ETFS.items():
    d = json.load(open(ROOT / f"reports/execution/{name}-target-weights.json"))
    rows = [r for r in d["target_weights"] if r["target_weight"] > 0]
    w = np.array([r["target_weight"] for r in rows]); p = np.array([r["reference_price"] for r in rows])
    res["etf_sleeves"][k] = {"file": f"reports/execution/{name}-target-weights.json", "generated_at": d["generated_at"],
                             "signal_session": d["summary"]["signal_session"],
                             "targets": {r["symbol"]: [r["target_weight"], r["reference_price"]] for r in rows}, "by_capital": {}}
    for C in CAPS:
        out = {}
        q = np.floor(w * C / p)  # long-only whole shares: floor so as never to exceed cash; Alpaca fractional also allowed
        wr = q * p / C
        out["whole_share_floor"] = {"exposure_ratio": float(wr.sum() / w.sum()), "zero_names": int((q == 0).sum()),
                                    "n_names": len(w), "rel_l1_error": float(np.abs(wr - w).sum() / w.sum())}
        q2 = rha(w * C / p); wr2 = q2 * p / C
        out["whole_share_round"] = {"exposure_ratio": float(wr2.sum() / w.sum()), "zero_names": int((q2 == 0).sum()),
                                    "rel_l1_error": float(np.abs(wr2 - w).sum() / w.sum())}
        okf = out["whole_share_floor"]["exposure_ratio"] >= V2_SHORT_RATIO_MIN and out["whole_share_floor"]["rel_l1_error"] <= V2_REL_L1_MAX and out["whole_share_floor"]["zero_names"] == 0
        out["v2_whole_share_pass"] = bool(okf)
        out["fractional_pass"] = bool(float(np.min(w * C)) >= 1.0)
        res["etf_sleeves"][k]["by_capital"][str(C)] = out

# ---- program view: sleeve capital = weight x C (10-02 allocation), ETF + stock books
prog = {}
for C in CAPS:
    row = {}
    for k, wt in ALLOC.items():
        sc = wt * C
        if k in ETFS:
            t = res["etf_sleeves"][k]["targets"]
            w = np.array([v[0] for v in t.values()]); p = np.array([v[1] for v in t.values()])
            q = np.floor(w * sc / p); wr = q * p / sc
            row[k] = {"sleeve_capital": sc, "etf_whole_share_pass": bool(wr.sum() / w.sum() >= .9 and (q > 0).all()),
                      "exposure_ratio": float(wr.sum() / w.sum())}
        else:
            path = ROOT / f"reports/paper/book/{'quant1' if k=='F1' else 'quant2'}/targets/2026-10-02.json"
            d, syms, w, p, beta, adv = stock_leg(path)
            m = metrics(w, p, beta, adv, sc, "mixed"); v = v2(m)
            row[k] = {"sleeve_capital": sc, "short_zero_frac": m["short_zero_frac"], "short_gross_ratio": m["short_gross_ratio"],
                      "rel_l1_error": m["rel_l1_error"], "v2_pass": v["pass"]}
    prog[str(C)] = row
res["program_view"] = prog

# ---- raw backtest numbers + DSR inputs
rt = pd.read_parquet(ROOT / "data/research/account_review_2026_10/returns.parquet")
bil = None
alloc = json.load(open(ROOT / "reports/research/program/allocation-dd30-2026-10-02/results.json"))["engine_stats"]
raw = {}
for k in ("S1", "S2"):
    r = rt[f"{k}__net10"].dropna()
    for wn, (a, b) in {"full": ("2017-02-01", "2026-10-02"), "anchor": ("2024-01-08", "2026-09-17")}.items():
        x = r[a:b]
        raw.setdefault(k, {})[wn] = {"cagr": float((1 + x).prod() ** (252 / len(x)) - 1), "vol": float(x.std() * 252 ** .5),
                                     "sharpe_no_rf": float(x.mean() / x.std() * 252 ** .5), "sessions": int(len(x)),
                                     "note": "from returns.parquet net10, rf not subtracted, own computation"}
for k in ("S3", "C2", "F1", "F2"):
    raw[k] = {w: {m: alloc[k][w][m] for m in ("cagr", "vol", "sharpe_excess", "max_dd")} for w in ("full", "stress", "anchor")}
    raw[k]["source"] = "reports/research/program/allocation-dd30-2026-10-02/results.json engine_stats"
iter12 = json.load(open(ROOT / "reports/research/iterations/t20261002_book_v12/results.json"))["variants"]["M0_U3000"]
dsr = {"family_dsr": iter12["family_dsr"], "family_sr0_annual": iter12["family_sr0_annual"],
       "program_dsr": iter12["program_dsr"], "program_sr0_annual": iter12["program_sr0_annual"],
       "recent_net_sharpe": iter12["recent_net_sharpe"], "recent_sessions": iter12["recent_sessions"],
       "source": "reports/research/iterations/t20261002_book_v12/results.json variants.M0_U3000"}
h_hi = max(0.0, dsr["recent_net_sharpe"] - dsr["family_sr0_annual"]) / dsr["recent_net_sharpe"]
h_lo = max(0.0, dsr["recent_net_sharpe"] - dsr["program_sr0_annual"]) / dsr["recent_net_sharpe"]
dsr["haircut_factor_family"] = h_hi; dsr["haircut_factor_program"] = h_lo
rng = {}
for k in ("F1", "F2"):
    a = raw[k]["anchor"]
    exc = a["sharpe_excess"] * a["vol"]
    rng[k] = {"raw_anchor_excess_return": exc, "raw_anchor_cagr": a["cagr"], "raw_full_cagr": raw[k]["full"]["cagr"],
              "deflated_excess_return_low": h_lo * exc, "deflated_excess_return_high": h_hi * exc,
              "method": "excess-over-cash return = haircut x anchor Sharpe x anchor vol; haircut = (SR - SR0)/SR using v1.2 M0_U3000 SR0 (program SR0 = low, family SR0 = high)"}
rng["P1_proxy"] = dict(rng["F1"]); rng["P1_proxy"]["note"] = "F1 stock legs as proxy; P1 itself has no scorecard (待定)"
res["raw_backtest"] = raw; res["dsr_inputs"] = dsr; res["deflated_return_range"] = rng
json.dump(res, open(OUT / "results.json", "w"), indent=1, ensure_ascii=False)
print("ok")
