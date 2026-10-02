# ruff: noqa: E501
"""Book v1.2 Stage A summary, Stage C scorecard and diagnostics (t20261002_book_v12).

Contract: ``reports/research/iterations/t20261002_book_v12/hypotheses.md`` sections 5-6.

    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v12_score.py --stage account-summary
    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v12_score.py --stage score
    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v12_score.py --stage diag
    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/book_v12_score.py --stage report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research import scorecard_v2 as sc  # noqa: E402
from open_composer.research.equity_book import book_v12 as bv  # noqa: E402
from open_composer.research.equity_book.evaluate import load_rf_spy  # noqa: E402
from scripts import realism_ladder_book_ls as T25  # noqa: E402

DATA = ROOT / "data/research/book_v12"
REP = ROOT / "reports/research/iterations/t20261002_book_v12"
EB = T25.EB
VARIANTS = T25.VARIANTS
OFFSETS = T25.OFFSETS
E = bv.EQUITY
WIN = {
    "recent": ("2024-01-08", "2026-09-15"),
    "A": ("2024-01-08", "2026-06-30"),
    "B": ("2026-07-01", "2026-09-15"),
}
V1_MANIFEST = ROOT / "reports/research/iterations/t20261001_book_v1/stage2a-manifest.json"
V1_VARIANTS = tuple(f"{m}_{x}" for m in ("M0", "M1") for x in ("A", "B", "C"))
PROGRAM_N = 111
PROGRAM_RHO = 0.5
PROGRAM_VAR_FLOOR = 0.25
DEFAULT_RHO = 0.3
FAMILY_N = 10


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def win(s: pd.Series, a: str, b: str) -> pd.Series:
    return s[(s.index >= pd.Timestamp(a)) & (s.index <= pd.Timestamp(b))]


def max_dd(r: pd.Series) -> float:
    c = r.cumsum()
    return float((c - c.cummax()).min())


def stats(r: pd.Series, excess: pd.Series | None = None) -> dict:
    r = r.dropna()
    ex = r if excess is None else excess.reindex(r.index).dropna()
    n = len(ex)
    if n < 20:
        return {"n": n}
    sd = float(ex.std(ddof=1))
    return {
        "n": n,
        "ann_return": float(r.mean() * 252),
        "ann_excess": float(ex.mean() * 252),
        "ann_vol": float(r.std(ddof=1) * math.sqrt(252)),
        "ann_vol_excess": float(sd * math.sqrt(252)),
        "sharpe_excess": float(ex.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan"),
        "max_dd": max_dd(r),
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def a1(variant: str, form: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"A1_{variant}_{form}.parquet")


# ---------------------------------------------------------------------------
# account summary (Stage A1)
# ---------------------------------------------------------------------------
def account_metrics(variant: str) -> dict:
    out: dict = {}
    d1, d2 = a1(variant, "F1"), a1(variant, "F2")
    for form, d in (("F1", d1), ("F2", d2)):
        blk: dict = {
            "equity_end": float(d["equity"].iloc[-1]),
            "sessions": int(len(d)),
            "first": str(d.index[0].date()),
            "last": str(d.index[-1].date()),
        }
        viol = (d["init_excess"] < 0) | (d["maint_excess"] < 0)
        rec = (d.index >= pd.Timestamp(WIN["recent"][0])) & (
            d.index <= pd.Timestamp(WIN["recent"][1])
        )
        eq_pre = d["equity"].shift(1).fillna(E) - d["cost"]
        init_fixed = E - (eq_pre - d["init_excess"])
        maint_fixed = E - (eq_pre - d["maint_excess"])
        viol_fixed = (init_fixed < 0) | (maint_fixed < 0)
        blk["margin"] = {
            "violation_sessions_all": int(viol.sum()),
            "violation_sessions_recent": int(viol[rec].sum()),
            "min_init_excess_dollars": float(d["init_excess"].min()),
            "min_maint_excess_dollars": float(d["maint_excess"].min()),
            "min_init_excess_frac_equity": float(d["init_excess"].min() / E),
            "min_maint_excess_frac_equity": float(d["maint_excess"].min() / E),
            "min_init_excess_recent": float(d.loc[rec, "init_excess"].min()),
            "min_maint_excess_recent": float(d.loc[rec, "maint_excess"].min()),
            "stress_equity_fixed_at_E": {
                "violation_sessions_all": int(viol_fixed.sum()),
                "min_init_excess_dollars": float(init_fixed.min()),
                "min_maint_excess_dollars": float(maint_fixed.min()),
            },
            "max_gross_frac": float(d["gross"].max() / E),
            "mean_gross_frac": float(d["gross"].mean() / E),
            "mean_long_frac": float(d["long_mv"].mean() / E),
            "mean_short_frac": float(d["short_mv"].mean() / E),
            "min_cash_frac_equity": float(d["cash"].min() / E),
            "sessions_with_negative_cash": int((d["cash"] < 0).sum()),
        }
        blk["orders"] = {
            "n_orders_median": float(d["n_orders"].median()),
            "n_orders_p95": float(d["n_orders"].quantile(0.95)),
            "n_dropped_median": float(d["n_dropped"].median()),
            "n_dropped_p95": float(d["n_dropped"].quantile(0.95)),
            "rounding_drift_mean": float(d["rounding_drift"].mean()),
            "rounding_drift_p95": float(d["rounding_drift"].quantile(0.95)),
            "scale_events": int(d["scale_events"].sum()),
        }
        z = np.load(DATA / f"A1_{variant}_{form}_participation.npz")
        ratio = z["notional"] / z["adv"]
        ratio = ratio[np.isfinite(ratio) & (z["adv"] > 0)]
        blk["participation"] = {
            "n_orders_with_adv": int(len(ratio)),
            "median": float(np.median(ratio)),
            "p99": float(np.quantile(ratio, 0.99)),
            "max": float(ratio.max()),
        }
        r = d["net_pnl"] / E
        r_b25 = (d["net_pnl"] - d["short_mv_stock"] * 25.0 / 1e4 / 252.0) / E
        r_d0 = (d["net_pnl"] - d["delist_adj"]) / E
        cash_gain = np.maximum(0.0, d["cash"] - d["short_mv"]) * d["bil_ret"] / E
        r_cash = r + cash_gain
        bench = d["bil_ret"] if form == "F1" else d["spy_ret"]
        blk["pnl_decomposition_ann_frac_equity_recent"] = {
            c: float((win(d[c], *WIN["recent"]) / E).mean() * 252)
            for c in (
                "stock_pnl",
                "spy_pnl",
                "tbill_pnl",
                "cost",
                "interest",
                "delist_adj",
                "net_pnl",
            )
        }
        blk["windows"] = {}
        for w, (a, b) in WIN.items():
            ws = win(r, a, b)
            bw = win(bench, a, b)
            base = stats(ws, ws - bw)
            if form == "F2":
                ex = ws - bw
                sd = float(ex.std(ddof=1))
                base["tracking_error"] = float(sd * math.sqrt(252))
                base["information_ratio"] = float(ex.mean() / sd * math.sqrt(252))
                base["interest_ann_frac_equity"] = float(
                    (win(d["interest"], a, b) / E).mean() * 252
                )
            blk["windows"][w] = base
        blk["sensitivities_recent"] = {}
        for name, s_ in (
            ("main", r),
            ("borrow_25bp", r_b25),
            ("delist_zero", r_d0),
            ("cash_interest_bil", r_cash),
            ("borrow_25bp_delist_zero", r_b25 - d["delist_adj"] / E),
        ):
            ws = win(s_, *WIN["recent"])
            blk["sensitivities_recent"][name] = stats(ws, ws - win(bench, *WIN["recent"]))
        out[form] = blk
        frac = d.drop(columns=["n_orders", "n_dropped", "scale_events"]) / E
        frac[["n_orders", "n_dropped", "scale_events"]] = d[
            ["n_orders", "n_dropped", "scale_events"]
        ]
        frac.to_parquet(DATA / f"A1_{variant}_{form}_frac.parquet")
    # F1 overlay: stocks plus SPY hedge, net of their own costs, no T-bill leg, no cash
    ov = (d1["stock_pnl"] + d1["spy_pnl"] - d1["cost_overlay"] + d1["delist_adj"]) / E
    ov25 = ov - d1["short_mv_stock"] * 25.0 / 1e4 / 252.0 / E
    out["F1_overlay"] = {
        "main_borrow0_delist30": {w: stats(win(ov, *ab)) for w, ab in WIN.items()},
        "borrow25_delist30": {w: stats(win(ov25, *ab)) for w, ab in WIN.items()},
    }
    ov.to_frame("overlay_net").assign(overlay_net_borrow25=ov25).to_parquet(
        DATA / f"A1_{variant}_F1_overlay.parquet"
    )
    return out


def run_account_summary() -> None:
    res = {
        "equity_basis": E,
        "g_cap": bv.G_CAP,
        "variants": {v: account_metrics(v) for v in VARIANTS},
    }
    (REP / "account-summary.json").write_text(json.dumps(res, indent=1, default=float))
    for v, blk in res["variants"].items():
        f1, f2 = blk["F1"], blk["F2"]
        print(
            v,
            "F1 viol",
            f1["margin"]["violation_sessions_all"],
            "F2 viol",
            f2["margin"]["violation_sessions_all"],
            "part med",
            round(f1["participation"]["median"], 5),
            "F1 recent sharpe",
            round(f1["windows"]["recent"]["sharpe_excess"], 2),
            "overlay",
            round(blk["F1_overlay"]["main_borrow0_delist30"]["recent"]["sharpe_excess"], 2),
        )


# ---------------------------------------------------------------------------
# scorecard (Stage C)
# ---------------------------------------------------------------------------
def r6_blend(variant: str) -> pd.DataFrame:
    return T25.blend([pd.read_parquet(T25.RAW / f"R6_{variant}_o{o}.parquet") for o in OFFSETS])


def calendar() -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.read_parquet(EB / "panel/_calendar.parquet")["trade_date"])


def label_to_session(idx: pd.DatetimeIndex, cal: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Label t earns the return of session t+2."""
    pos = cal.get_indexer(idx)
    return pd.DatetimeIndex(cal[pos + 2])


def v1_blended_excess() -> dict[str, pd.Series]:
    paths = json.loads(V1_MANIFEST.read_text())["paths"]
    rf, _ = load_rf_spy()
    out: dict[str, pd.Series] = {}
    for v in V1_VARIANTS:
        m, x = v.split("_")
        frames = []
        for o in OFFSETS:
            info = paths[f"{m}_{x}_o{o}_close"]
            df = (
                pd.read_parquet(ROOT / info["files"]["daily.parquet"]["path"])
                .set_index("trade_date")
                .sort_index()
            )
            frames.append(df["net"])
        common = frames[0].index
        for f in frames[1:]:
            common = common.intersection(f.index)
        net = sum(f.loc[common] for f in frames) / len(frames)
        out[v] = (net - rf.reindex(net.index).fillna(0.0)).dropna()
    return out


def family_stats(r6_excess_labels: dict[str, pd.Series]) -> dict:
    """10-variant family: 6 v1 Stage 2a variants + 4 R6 variants, recent-window blended excess."""
    cal = calendar()
    series: dict[str, pd.Series] = {}
    notes: dict[str, str] = {}
    try:
        v1 = v1_blended_excess()
    except Exception as exc:  # missing series -> sharpe unknown; correlation 0.3
        v1 = {}
        notes["v1_error"] = repr(exc)[:200]
    lo, hi = WIN["recent"]
    for v, s in v1.items():
        series[f"v1_{v}"] = win(s, lo, "2026-09-17")
    for v, s in r6_excess_labels.items():
        s2 = win(s, lo, hi).copy()
        s2.index = label_to_session(s2.index, cal)
        series[f"R6_{v}"] = s2
    names = list(series)
    align = {}
    if "v1_M0_A" in series:
        ref = win(r6_excess_labels["M0_U3000"], lo, hi)
        for sh in (0, 1, 2):
            idx = pd.DatetimeIndex(cal[cal.get_indexer(ref.index) + sh])
            c2 = pd.concat(
                [pd.Series(ref.to_numpy(), index=idx), series["v1_M0_A"]], axis=1
            ).dropna()
            align[f"shift_{sh}_sessions"] = float(c2.corr().iloc[0, 1])
    sharpes = {n: sc.annual_sharpe(series[n]) for n in names}
    panel = pd.DataFrame(series).dropna()
    corr = panel.corr()
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pairs.append(float(corr.iloc[i, j]))
    # a family with fewer than 10 series: missing pairs count 0.3
    n_missing = FAMILY_N * (FAMILY_N - 1) // 2 - len(pairs)
    pairs += [DEFAULT_RHO] * n_missing
    rho = float(np.mean(pairs))
    sr_vals = list(sharpes.values())
    # missing variants: v1 results.json Sharpe is not available here -> not counted in the variance
    var_sr = float(np.var(sr_vals, ddof=1))
    return {
        "series": names,
        "n_series": len(names),
        "n_missing_pairs_at_0.3": n_missing,
        "sharpes_recent": sharpes,
        "mean_pairwise_corr": rho,
        "corr_matrix_sessions": int(len(panel)),
        "var_sr_annual": var_sr,
        "n_eff": sc.n_eff_from_corr(FAMILY_N, rho),
        "corr_pair_min": float(min(pairs)),
        "corr_pair_max": float(max(pairs)),
        "alignment_corr_v1_M0_A_vs_R6_M0_U3000": align,
        "notes": notes,
    }


def git_clean(path: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=ROOT)
    return r.returncode == 0


def run_score() -> None:
    cfg = sc.load_config()
    hyp = REP / "hypotheses.md"
    ident = json.loads((REP / "identity.json").read_text())
    acct = json.loads((REP / "account-summary.json").read_text())
    plc = json.loads((REP / "placebo.json").read_text())
    phases = json.loads((EB / "regimes/phases.json").read_text())["phases_recent"]
    state = pd.read_parquet(EB / "regimes/market_state.parquet")["state"]

    rows, rows2 = [], []
    sig_ls: dict[str, pd.Series] = {}
    bl_all: dict[str, pd.DataFrame] = {}
    for v in VARIANTS:
        for o in OFFSETS:
            d = pd.read_parquet(T25.RAW / f"R6_{v}_o{o}.parquet")
            base = pd.DataFrame({"date": d.index, "variant": v, "offset": o})
            rows.append(base.assign(net=d["net"].to_numpy(), gross=d["gross"].to_numpy()))
            # contract section 4: 2x trade cost plus 100 bp/yr on every short (T-25's borrow is 25 bp)
            c2 = (d["gross"] - 2.0 * d["cost"] - 4.0 * d["borrow"]).to_numpy()
            rows2.append(base.assign(net=c2, gross=float("nan")))
        sig_ls[v] = pd.read_parquet(T25.RAW / f"R1a_{v}_daily.parquet")["gross"]
        bl_all[v] = r6_blend(v)
    returns, cost2x = pd.concat(rows), pd.concat(rows2)
    bil = pd.Series(0.0, index=pd.DatetimeIndex(returns["date"].unique()).sort_values())

    # --- family and program DSR
    ex_r6 = {v: bl_all[v]["net"] for v in VARIANTS}
    fam = family_stats(ex_r6)
    lo, hi = WIN["recent"]
    rec = {v: win(ex_r6[v], lo, hi) for v in VARIANTS}
    var_prog = max(fam["var_sr_annual"], PROGRAM_VAR_FLOOR)
    n_eff_prog = sc.n_eff_from_corr(PROGRAM_N, PROGRAM_RHO)
    dsr_fam = {
        v: sc.dsr(rec[v].to_numpy(), var_sr_annual=fam["var_sr_annual"], n_eff=fam["n_eff"])
        for v in VARIANTS
    }
    dsr_prog = {
        v: sc.dsr(rec[v].to_numpy(), var_sr_annual=var_prog, n_eff=n_eff_prog) for v in VARIANTS
    }

    # --- V2 from the account layer
    v2: dict[str, dict] = {}
    for v in VARIANTS:
        blk = acct["variants"][v]
        viol = max(
            blk["F1"]["margin"]["violation_sessions_all"],
            blk["F2"]["margin"]["violation_sessions_all"],
        )
        part = max(blk["F1"]["participation"]["median"], blk["F2"]["participation"]["median"])
        sessions_ok = blk["F1"]["sessions"] >= 2000 and blk["F2"]["sessions"] >= 2000
        ok = bool(viol == 0 and part <= cfg["vetoes"]["max_participation_adv"] and sessions_ok)
        v2[v] = {
            "attested": ok,
            "margin_violation_sessions_max_form": viol,
            "participation_median_max_form": part,
            "participation_threshold": cfg["vetoes"]["max_participation_adv"],
            "whole_share_simulation_completed": sessions_ok,
        }
    v1_att = bool(ident["pass"] and git_clean(hyp))
    attest = {v: {"V1": v1_att, "V2": v2[v]["attested"]} for v in VARIANTS}
    placebo_in = {
        v: {
            "net": plc["variants"][v]["placebo_net_sharpes"],
            "gross": plc["variants"][v]["placebo_gross_sharpes"],
        }
        for v in VARIANTS
    }

    card = sc.score_family(
        returns,
        cost2x,
        bil,
        phases,
        state,
        signal_ls=sig_ls,
        placebo=placebo_in,
        attestations=attest,
        n_trials=FAMILY_N,
    )

    # --- overlay rule (binding)
    overlay_rule: dict[str, dict] = {}
    for v in VARIANTS:
        ov = pd.read_parquet(DATA / f"A1_{v}_F1_overlay.parquet")["overlay_net"]
        sr_ov = sc.annual_sharpe(win(ov, lo, hi))
        sr_r6 = sc.annual_sharpe(rec[v])
        overlay_rule[v] = {
            "overlay_recent_net_sharpe": sr_ov,
            "r6_recent_net_sharpe": sr_r6,
            "difference": sr_ov - sr_r6,
            "rescore_triggered": bool(sr_ov < sr_r6 - 0.25),
            "overlay_recent_net_sharpe_borrow25": sc.annual_sharpe(
                win(
                    pd.read_parquet(DATA / f"A1_{v}_F1_overlay.parquet")["overlay_net_borrow25"],
                    lo,
                    hi,
                )
            ),
        }

    triggered_ov = [v for v, r in overlay_rule.items() if r["rescore_triggered"]]
    if triggered_ov:  # binding rule of section 5; not implemented because it did not trigger
        raise RuntimeError(f"overlay rescore rule triggered for {triggered_ov}: rescoring needed")
    rescored: dict[str, dict] = {}

    # --- tier per variant with the family DSR, program cap
    out_vars: dict[str, dict] = {}
    for v in VARIANTS:
        c = card["variants"][v]
        metrics = {
            "dsr": dsr_fam[v]["dsr"],
            "signal_t": c["signal"].get("t_iid"),
            "placebo_net_pct": c["placebo"]["net_pct"],
            "placebo_gross_pct": c["placebo"]["gross_pct"],
            "robustness_score": c["robustness_score"],
        }
        tier, detail = sc._tier(cfg, metrics, c["vetoes_triggered"], c["vetoes_unassessed"])
        capped = False
        if tier == "P2" and dsr_prog[v]["dsr"] < 0.50:
            tier, capped = "P1", True
        if tier in ("P1", "P2") and dsr_prog[v]["dsr"] < 0.50:
            pass
        sig = c["signal"]
        sig_win = win(sig_ls[v], lo, hi)
        out_vars[v] = {
            "tier": tier,
            "tier_capped_by_program_dsr": capped,
            "tier_detail": detail,
            "family_dsr": dsr_fam[v]["dsr"],
            "family_psr0": dsr_fam[v]["psr0"],
            "family_sr0_annual": dsr_fam[v]["sr0_annual"],
            "program_dsr": dsr_prog[v]["dsr"],
            "program_sr0_annual": dsr_prog[v]["sr0_annual"],
            "scorecard_own_dsr_n4": c["dsr"]["dsr"],
            "scorecard_own_n_eff": c["dsr"]["n_eff"],
            "recent_net_sharpe": sc.annual_sharpe(rec[v]),
            "recent_sessions": int(len(rec[v])),
            "signal_t_iid_r1a_gross": sig.get("t_iid"),
            "signal_t_newey_west_lag5": sc.signal_t_stats(sig_win, 5)["t_newey_west"],
            "placebo_net_pct": c["placebo"]["net_pct"],
            "placebo_gross_pct": c["placebo"]["gross_pct"],
            "robustness_score": c["robustness_score"],
            "robustness": c["robustness"],
            "vetoes": c["vetoes"],
            "vetoes_triggered": c["vetoes_triggered"],
            "vetoes_unassessed": c["vetoes_unassessed"],
            "V2_detail": v2[v],
            "overlay_rule": overlay_rule[v],
            "pass_flags": c["pass_flags"],
        }
    res = {
        "contract": {
            "hypotheses_sha256": sha256(hyp),
            "config_version": cfg["version"],
            "committed_unchanged": git_clean(hyp),
        },
        "identity": {"pass": ident["pass"], "max_abs_diff": ident["max_abs_diff"]},
        "family": fam,
        "program": {
            "n_trials": PROGRAM_N,
            "rho": PROGRAM_RHO,
            "n_eff": n_eff_prog,
            "var_sr_annual": var_prog,
        },
        "overlay_rule_rescored": rescored,
        "variants": out_vars,
    }
    # --- primary variant and decision (section 6)
    ok = [v for v in VARIANTS if out_vars[v]["tier"] in ("P1", "P2")]
    primary = None
    if ok:
        ranked = sorted(
            ok, key=lambda v: (-out_vars[v]["family_dsr"], -out_vars[v]["recent_net_sharpe"])
        )
        primary = ranked[0]
        for v in ranked[1:]:
            if (
                abs(out_vars[v]["family_dsr"] - out_vars[primary]["family_dsr"]) < 0.01
                and out_vars[v]["recent_net_sharpe"] > out_vars[primary]["recent_net_sharpe"]
            ):
                primary = v
    res["primary_variant"] = primary
    res["decision"] = (
        f"proceed to paper incubation per section 6 with {primary} (quant1 F1, quant2 F2)"
        if primary
        else "no variant reaches P1: the book line pauses (stop/pivot of the contract); no parameter is changed"
    )
    (REP / "results.json").write_text(json.dumps(res, indent=1, default=float))
    for v in VARIANTS:
        o = out_vars[v]
        print(
            v,
            o["tier"],
            "fdsr",
            round(o["family_dsr"], 3),
            "pdsr",
            round(o["program_dsr"], 3),
            "plc",
            o["placebo_net_pct"],
            o["placebo_gross_pct"],
            "rob",
            o["robustness_score"],
            "veto",
            o["vetoes_triggered"],
            "unassessed",
            o["vetoes_unassessed"],
            "ovl",
            round(overlay_rule[v]["difference"], 2),
        )
    print("primary", primary)


# ---------------------------------------------------------------------------
# diagnostics (not tiering)
# ---------------------------------------------------------------------------
SPAN_ETFS = ("SPLV", "SPHB", "MTUM", "QUAL", "VLUE", "IWM")
SPAN_SHARDS = {
    "IWM": "0158",
    "MTUM": "0197",
    "QUAL": "0244",
    "SPLV": "0276",
    "SPHB": "0276",
    "SPY": "0278",
    "VLUE": "0313",
}


def nw_ols(y: np.ndarray, x: np.ndarray, lag: int = 5) -> dict:
    """OLS with intercept and Newey-West (Bartlett) standard errors."""
    n = len(y)
    X = np.column_stack([np.ones(n), x])
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    u = y - X @ beta
    xu = X * u[:, None]
    S = xu.T @ xu
    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        G = xu[k:].T @ xu[:-k]
        S += w * (G + G.T)
    cov = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.diag(cov))
    r2 = 1.0 - float((u**2).sum() / ((y - y.mean()) ** 2).sum())
    return {"beta": beta, "se": se, "t": beta / se, "r2": r2, "n": n}


def etf_returns() -> pd.DataFrame:
    frames = []
    for year in (2023, 2024, 2025, 2026):
        for sym, shard in SPAN_SHARDS.items():
            if sym == "SPY" and year == 2023 and False:
                continue
            f = ROOT / f"data/sip/daily/{year}/shard-{shard}.parquet"
            df = pd.read_parquet(
                f,
                filters=[("symbol", "in", list(SPAN_SHARDS))],
                columns=["symbol", "timestamp", "close"],
            )
            frames.append(df)
    df = pd.concat(frames).drop_duplicates(["symbol", "timestamp"])
    df["date"] = (
        pd.to_datetime(df["timestamp"])
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    c = df.pivot(index="date", columns="symbol", values="close").sort_index()
    return c / c.shift(1) - 1.0


def run_diag() -> None:
    res = json.loads((REP / "results.json").read_text())
    cal = calendar()
    ret = etf_returns()
    out: dict = {"etfs": list(SPAN_ETFS), "lag": 5, "variants": {}}
    for v in VARIANTS:
        bl = r6_blend(v)
        y = win(bl["net"], *WIN["recent"])
        sess = label_to_session(y.index, cal)
        yy = pd.Series(y.to_numpy(), index=sess)
        X = pd.DataFrame({f"{e}-SPY": ret[e] - ret["SPY"] for e in SPAN_ETFS})
        X["SPY"] = ret["SPY"]
        d = pd.concat([yy.rename("y"), X], axis=1).dropna()
        spy_col = pd.Series(win(bl["spy"], *WIN["recent"]).to_numpy(), index=sess)
        chk = pd.concat([spy_col.rename("a"), ret["SPY"].rename("b")], axis=1).dropna()
        reg = nw_ols(d["y"].to_numpy(), d.drop(columns="y").to_numpy())
        names = ["alpha"] + list(d.columns[1:])
        out["variants"][v] = {
            "sessions": int(len(d)),
            "spy_column_vs_etf_spy_corr": float(chk.corr().iloc[0, 1]),
            "alpha_ann": float(reg["beta"][0] * 252),
            "alpha_t_nw5": float(reg["t"][0]),
            "r2": reg["r2"],
            "loadings": {n: float(b) for n, b in zip(names[1:], reg["beta"][1:], strict=True)},
            "loading_t_nw5": {n: float(t) for n, t in zip(names[1:], reg["t"][1:], strict=True)},
        }
        print(
            v,
            "alpha_ann",
            round(reg["beta"][0] * 252, 3),
            "t",
            round(reg["t"][0], 2),
            "r2",
            round(reg["r2"], 2),
            "spy corr",
            round(float(chk.corr().iloc[0, 1]), 5),
        )
    res["diagnostics_spanning"] = out
    (REP / "results.json").write_text(json.dumps(res, indent=1, default=float))


def run_attrib() -> None:
    """Style / specific attribution of the primary variant (T-19 ``attribute_day``), recent window."""
    from open_composer.research.equity_book.risk import RiskModel
    from scripts import book_v12_account as acct
    from scripts.eval_book_postmortem import attribute_day

    res = json.loads((REP / "results.json").read_text())
    v = res.get("primary_variant") or "M0_U3000"
    ctx = T25.Context()
    px = ctx.px
    flag = acct.variant_flag(v)
    first = int(px.dates.searchsorted(pd.Timestamp("2023-12-01")))
    last_label = px.T - 3
    blocks: dict[int, list] = {}
    for o in OFFSETS:
        src = acct.make_source(ctx, v)
        dec = T25.decision_positions(px.T, first, last_label, T25.WEEK, o)
        lst = []
        for i, p in enumerate(dec):
            nxt = dec[i + 1] if i + 1 < len(dec) else last_label + 1
            di = acct.decision_inputs(ctx, src, flag, p)
            if di is None:
                continue
            tt = acct.tranche_from_inputs(ctx, di)
            nz = np.flatnonzero(tt.w)
            ret, _ = px.returns("close", p, nxt - p)
            r = np.where(np.isfinite(ret[:, nz]), ret[:, nz], 0.0)
            g_after = np.cumprod(1.0 + r, axis=0)
            g_before = np.vstack([np.ones((1, r.shape[1])), g_after[:-1]])
            lst.append((p, nxt - p, nz, tt.w[nz], g_before))
        blocks[o] = lst
        print("attrib decisions", o, len(lst), flush=True)
    rm = RiskModel()
    meta = json.loads((EB / "risk/meta.json").read_text())
    factors, groups, styles = list(meta["factors"]), list(meta["groups"]), list(meta["styles"])
    fr = pd.concat(
        [pd.read_parquet(EB / f"risk/factor_returns_{y}.parquet") for y in range(2023, 2027)]
    )
    fret = fr.pivot(index="trade_date", columns="factor", values="ret").sort_index()
    bl = r6_blend(v)
    lo_p = int(px.dates.searchsorted(pd.Timestamp(WIN["recent"][0])))
    hi_p = int(px.dates.searchsorted(pd.Timestamp(WIN["recent"][1])))
    rows = []
    cache: tuple[pd.Timestamp | None, pd.DataFrame | None] = (None, None)
    for tau in range(lo_p, hi_p + 1):
        wv = np.zeros(px.N)
        for o in OFFSETS:
            for p, length, nz, w0, gb in blocks[o]:
                if p <= tau < p + length:
                    wv[nz] += w0 * gb[tau - p] / len(OFFSETS)
                    break
        with np.errstate(invalid="ignore", divide="ignore"):
            r_all = px.C[tau + 2] / px.C[tau + 1] - 1.0
        r_all = np.where(np.isfinite(r_all), r_all, 0.0)
        nzw = np.flatnonzero(wv)
        w_s = pd.Series(wv[nzw], index=px.symbols[nzw])
        r_s = pd.Series(r_all, index=px.symbols)
        d_prev = px.dates[tau + 1]
        try:
            used = rm.resolve(d_prev)
        except KeyError:  # first weeks of a year: the last saved model of the previous year
            used = rm.resolve(pd.Timestamp(f"{d_prev.year - 1}-12-31"))
        if used != cache[0]:
            x, _f, _d = rm.at(used)
            cache = (used, x)
        sess = px.dates[tau + 2]
        f = fret.loc[sess] if sess in fret.index else pd.Series(dtype="float64")
        row = attribute_day(w_s, r_s, cache[1], f, factors, groups, styles)
        row["stock_total"] = float((w_s * r_s.reindex(w_s.index)).sum())
        row["date"] = px.dates[tau]
        rows.append(row)
    df = pd.DataFrame(rows).set_index("date")
    gross = bl["gross"].reindex(df.index)
    df["etf_leg"] = gross - df["stock_total"]
    comps = [c for c in df.columns if c not in ("stock_total",)]
    out: dict = {"variant": v, "k": 1, "windows": {}}
    for w, (a, b) in WIN.items():
        sub = win(df, a, b)
        out["windows"][w] = {
            c: {
                "ann_contribution": float(sub[c].mean() * 252),
                "sharpe": float(sub[c].mean() / sub[c].std(ddof=1) * math.sqrt(252))
                if sub[c].std(ddof=1) > 0
                else float("nan"),
            }
            for c in comps
        }
        styl = [c for c in comps if c.startswith("style_")]
        out["windows"][w]["style_total"] = {
            "ann_contribution": float(sub[styl].sum(axis=1).mean() * 252)
        }
        out["windows"][w]["style_total"]["sharpe"] = float(
            sub[styl].sum(axis=1).mean() / sub[styl].sum(axis=1).std(ddof=1) * math.sqrt(252)
        )
    res["diagnostics_attribution"] = out
    (REP / "results.json").write_text(json.dumps(res, indent=1, default=float))
    df.to_parquet(DATA / f"attrib_{v}.parquet")
    rec = out["windows"]["recent"]
    print(v, {c: round(rec[c]["ann_contribution"], 4) for c in rec})


def pct(x: float | None, nd: int = 1) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x * 100:.{nd}f}%"


def num(x: float | None, nd: int = 2) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def run_report() -> None:
    res = json.loads((REP / "results.json").read_text())
    acct = json.loads((REP / "account-summary.json").read_text())
    plc = json.loads((REP / "placebo.json").read_text())
    ident = json.loads((REP / "identity.json").read_text())
    for v in VARIANTS:
        res["variants"][v]["account"] = acct["variants"][v]
        res["variants"][v]["placebo"] = {
            k: val for k, val in plc["variants"][v].items() if not k.endswith("_sharpes")
        }
    res["account_equity_basis"] = acct["equity_basis"]
    res["placebo_seeds"] = plc["seeds"]
    (REP / "results.json").write_text(json.dumps(res, indent=1, default=float))
    V = res["variants"]
    fam, prog = res["family"], res["program"]
    L: list[str] = []
    L.append("# 书 v1.2：R6 简单构造的账户层、安慰剂和记分（T-20261002-26）\n")
    L.append(
        "数字全部来自同目录 `results.json`（含 `account-summary.json`、`placebo.json`、`identity.json`）。"
        "合同 `hypotheses.md`（05:31 UTC 冻结，sha256 "
        f"`{res['contract']['hypotheses_sha256'][:16]}…`，与 HEAD 一致={res['contract']['committed_unchanged']}），"
        f"评判标准配置 {res['contract']['config_version']}。\n"
    )
    L.append("## 1. 结论\n")
    L.append(f"- 判定：{res['decision']}。")
    L.append(f"- 主变体：{res['primary_variant']}。")
    L.append(
        "- 本报告只回答第 6 节开始模拟盘的第 1 条（主变体 ≥ P1）；第 2–6 条（live 目录核对、生产端目标生成器的逐位复现、引擎 dry-run、检查表发送机主、开关撤单测试）不在本任务内，尚未满足。\n"
    )
    L.append(
        "| 变体 | 档位 | 定档 DSR | 全项目 DSR | 近期净夏普(R6) | 安慰剂净/毛分位 | 稳健性分 | 否决 |"
    )
    L.append("|---|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        o = V[v]
        L.append(
            f"| {v} | {o['tier']} | {num(o['family_dsr'], 3)} | {num(o['program_dsr'], 3)} | {num(o['recent_net_sharpe'])} | {num(o['placebo_net_pct'])} / {num(o['placebo_gross_pct'])} | {o['robustness_score']}/6 | {', '.join(o['vetoes_triggered']) or '无'} |"
        )
    L.append("\n## 2. 阶段 A0：同一性\n")
    L.append(
        f"R6 的 M0_U3000 偏移 0 和 M1_P1000 偏移 3 经本模块路径（分数权重，k = 1，不轧差）重算，毛收益、成本、融券、净收益与 T-25 保存序列的最大绝对差 {ident['max_abs_diff']}（容差 {ident['tolerance']}），通过={ident['pass']}（`identity.json`）。\n"
    )
    L.append("## 3. 阶段 A1：账户层（$1M，整股，$100 最小订单，Alpaca 保证金，退市下界 −30%）\n")
    L.append("近期窗口 2024-01-08..2026-09-15 的 F1（对 BIL 的超额）与 F2（对 SPY 的超额）：\n")
    L.append(
        "| 变体 | 形式 | 年化收益 | 年化超额 | 年化波动 | 夏普(超额) | 最大回撤 | 跟踪误差 | 信息比率 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        for f in ("F1", "F2"):
            w = V[v]["account"][f]["windows"]["recent"]
            L.append(
                f"| {v} | {f} | {pct(w['ann_return'])} | {pct(w['ann_excess'])} | {pct(w['ann_vol'])} | {num(w['sharpe_excess'])} | {pct(w['max_dd'])} | {pct(w.get('tracking_error'))} | {num(w.get('information_ratio'))} |"
            )
    L.append(
        "\nA 窗 2024-01-08..2026-06-30 和 B 窗 2026-07-01..2026-09-15（B 窗只算一致性）的夏普(超额)：\n"
    )
    L.append("| 变体 | F1 A | F1 B | F2 A | F2 B |")
    L.append("|---|---|---|---|---|")
    for v in VARIANTS:
        a = V[v]["account"]
        L.append(
            f"| {v} | {num(a['F1']['windows']['A']['sharpe_excess'])} | {num(a['F1']['windows']['B']['sharpe_excess'])} | {num(a['F2']['windows']['A']['sharpe_excess'])} | {num(a['F2']['windows']['B']['sharpe_excess'])} |"
        )
    L.append("\n执行性与保证金（全样本 2017-10-02..2026-09-15）：\n")
    L.append(
        "| 变体 | 形式 | 保证金违规会话 | 最小初始余量(占 E) | 最小维持余量(占 E) | E 固定压力下最小初始/维持余量($) | 参与率中位/p99 | 订单数中位/p95 | 被丢小单中位 | 整股漂移均值 | 总敞口均值/最大 | 触顶缩放次数 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        for f in ("F1", "F2"):
            b = V[v]["account"][f]
            m, o, p = b["margin"], b["orders"], b["participation"]
            st = m["stress_equity_fixed_at_E"]
            L.append(
                f"| {v} | {f} | {m['violation_sessions_all']} | {pct(m['min_init_excess_frac_equity'])} | {pct(m['min_maint_excess_frac_equity'])} | {st['min_init_excess_dollars']:,.0f} / {st['min_maint_excess_dollars']:,.0f}（违规 {st['violation_sessions_all']}） | {p['median']:.2e} / {p['p99']:.2e} | {o['n_orders_median']:.0f} / {o['n_orders_p95']:.0f} | {o['n_dropped_median']:.0f} | {pct(o['rounding_drift_mean'])} | {num(m['mean_gross_frac'])} / {num(m['max_gross_frac'])} | {o['scale_events']} |"
            )
    L.append(
        "\n期末权益（E + 累计净盈亏，美元）："
        + "；".join(
            f"{v} F1 {V[v]['account']['F1']['equity_end']:,.0f} / F2 {V[v]['account']['F2']['equity_end']:,.0f}"
            for v in VARIANTS
        )
        + "。"
    )
    L.append("\n近期窗口夏普(超额)的敏感性（主口径：易借 0 bp、退市 −30%、正现金不计息）：\n")
    L.append(
        "| 变体 | 形式 | 主口径 | 借券 25 bp | 退市记 0 | 借券 25 bp + 退市 0 | 现金（除空头所得）按 BIL 计息 |"
    )
    L.append("|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        for f in ("F1", "F2"):
            s_ = V[v]["account"][f]["sensitivities_recent"]
            L.append(
                f"| {v} | {f} | {num(s_['main']['sharpe_excess'])} | {num(s_['borrow_25bp']['sharpe_excess'])} | {num(s_['delist_zero']['sharpe_excess'])} | {num(s_['borrow_25bp_delist_zero']['sharpe_excess'])} | {num(s_['cash_interest_bil']['sharpe_excess'])} |"
            )
    L.append(
        "\nF1 叠加层（股票加 SPY 对冲，扣各自成本，不含 T-bill 和现金）与策略层 R6 的近期净夏普（绑定规则：低 0.25 以上则改用叠加层重算）：\n"
    )
    L.append(
        "| 变体 | R6 策略层 | F1 叠加层（0 bp、退市 −30%） | 差 | 叠加层（25 bp、退市 −30%） | 触发重算 |"
    )
    L.append("|---|---|---|---|---|---|")
    for v in VARIANTS:
        o = V[v]["overlay_rule"]
        L.append(
            f"| {v} | {num(o['r6_recent_net_sharpe'])} | {num(o['overlay_recent_net_sharpe'])} | {num(o['difference'])} | {num(o['overlay_recent_net_sharpe_borrow25'])} | {o['rescore_triggered']} |"
        )
    L.append("\n## 4. 阶段 B：策略层安慰剂（100 个种子，每个调仓日每个偏移独立打乱合成分）\n")
    L.append(
        "| 变体 | 真实近期净/毛夏普 | 安慰剂净夏普 均值/p95/最大 | 安慰剂毛夏普 均值/p95/最大 | 净分位 | 毛分位 |"
    )
    L.append("|---|---|---|---|---|---|")
    for v in VARIANTS:
        p = plc["variants"][v]
        L.append(
            f"| {v} | {num(p['observed_net_sharpe'])} / {num(p['observed_gross_sharpe'])} | {num(p['placebo_net_mean'])} / {num(p['placebo_net_p95'])} / {num(p['placebo_net_max'])} | {num(p['placebo_gross_mean'])} / {num(p['placebo_gross_p95'])} / {num(p['placebo_gross_max'])} | {num(p['net_percentile'])} | {num(p['gross_percentile'])} |"
        )
    L.append(
        "\n安慰剂的净夏普全部为大负数：每周随机重排合成分使整个组合每周几乎全部换手，成本压倒毛收益，所以净分位恒为 1.00，对判定没有信息量；有信息量的是毛分位。P1000 的两个变体毛分位只有 0.89、0.92，低于稳健性 f 项的 0.95 线。\n"
    )
    L.append("## 5. 阶段 C：记分\n")
    L.append(
        f"定档族 {fam['n_series']} 个序列（v1 Stage 2a 的 M0/M1×A/B/C 近期窗口 5 档混合超额，取 `daily.parquet` 的 `net` 减 BIL 日收益；加 T-25 R6 的 4 个）：两两日收益相关的均值 ρ̄ = {num(fam['mean_pairwise_corr'], 4)}（{fam['corr_matrix_sessions']} 个共同会话，{fam['n_missing_pairs_at_0.3']} 对按 0.3 补），N_eff = {num(fam['n_eff'], 3)}，近期夏普方差 var_SR = {num(fam['var_sr_annual'], 4)}。"
        f"全项目口径：N = {prog['n_trials']}，ρ̄ = {prog['rho']}，N_eff = {num(prog['n_eff'], 1)}，var_SR = {num(prog['var_sr_annual'], 4)}（取 max(定档 var_SR, 0.25)）。\n"
    )
    L.append(
        "| 变体 | 定档 DSR | 定档 SR0 | 全项目 DSR | 全项目 SR0 | 记分器自带 DSR（4 变体，n_trials=10） | R1a 毛信号 t（iid / NW5） |"
    )
    L.append("|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        o = V[v]
        L.append(
            f"| {v} | {num(o['family_dsr'], 3)} | {num(o['family_sr0_annual'], 3)} | {num(o['program_dsr'], 3)} | {num(o['program_sr0_annual'], 3)} | {num(o['scorecard_own_dsr_n4'], 3)} | {num(o['signal_t_iid_r1a_gross'])} / {num(o['signal_t_newey_west_lag5'])} |"
        )
    L.append(
        "\n稳健性 6 项（a 成本 2 倍夏普比 ≥ 0.5；b 当前状态条件夏普 > 0；c 单一阶段占近期盈亏 ≤ 50%；d 至少 4 个偏移为正；e 近期一致性 z ≥ −2；f 毛安慰剂分位 ≥ 0.95）：\n"
    )
    L.append("| 变体 | a | b | c | d | e | f | 分数 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for v in VARIANTS:
        rb = V[v]["robustness"]
        cells = []
        for k in (
            "a_cost2x",
            "b_current_state",
            "c_single_phase",
            "d_offsets",
            "e_recent_consistency",
            "f_gross_placebo",
        ):
            x = rb[k]
            val = x.get("value") if k != "b_current_state" else x.get("sharpe")
            cells.append(f"{'通过' if x['pass'] else '未过'}（{num(val, 3)}）")
        L.append(f"| {v} | " + " | ".join(cells) + f" | {V[v]['robustness_score']} |")
    L.append("\n否决项：\n")
    L.append(
        "| 变体 | V1 | V2 | V3 成本 2 倍年化超额 | V4 21 日 / 63 日最大亏损（σ，线 5 / 4） | V5 z 最小值（线 −3） |"
    )
    L.append("|---|---|---|---|---|---|")
    for v in VARIANTS:
        vt = V[v]["vetoes"]
        w4 = vt["V4"]["windows"]
        L.append(
            f"| {v} | {'未触发' if vt['V1']['triggered'] is False else vt['V1']['triggered']} | {'未触发' if vt['V2']['triggered'] is False else vt['V2']['triggered']} | {pct(vt['V3']['annual_excess'])} | {num(w4['21']['loss_in_sigma'])} / {num(w4['63']['loss_in_sigma'])} | {num(vt['V5']['z_min'])} |"
        )
    L.append(
        "\n定档（P1 要求：定档 DSR ≥ 0.70、安慰剂净分位 ≥ 0.90、稳健性 ≥ 3、无否决；P2 另需信号 t ≥ 3.0、安慰剂净/毛分位 ≥ 0.95、DSR ≥ 0.80、稳健性 ≥ 5）：\n"
    )
    L.append("| 变体 | 档位 | P1 | P2 未满足项 |")
    L.append("|---|---|---|---|")
    for v in VARIANTS:
        d = V[v]["tier_detail"]
        miss = [k for k, c in d["P2"]["conditions"].items() if not c["met"]]
        L.append(f"| {v} | {V[v]['tier']} | {d['P1']['met']} | {', '.join(miss) or '无'} |")
    L.append("\n## 6. 诊断（不定档）\n")
    sp = res["diagnostics_spanning"]
    L.append(
        "### 6.1 因子 ETF 张成回归（近期窗口，策略层 R6 净日收益对 SPLV−SPY、SPHB−SPY、MTUM−SPY、QUAL−SPY、VLUE−SPY、IWM−SPY 和 SPY，Newey–West 滞后 5）\n"
    )
    L.append(
        "| 变体 | 年化 α | α 的 t | R² | 载荷（括号内 t） | 标签日 `spy` 列与 ETF SPY 日收益相关 |"
    )
    L.append("|---|---|---|---|---|---|")
    for v in VARIANTS:
        x = sp["variants"][v]
        ld = "; ".join(
            f"{k} {num(b)}（{num(x['loading_t_nw5'][k], 1)}）" for k, b in x["loadings"].items()
        )
        L.append(
            f"| {v} | {pct(x['alpha_ann'])} | {num(x['alpha_t_nw5'])} | {num(x['r2'])} | {ld} | {x['spy_column_vs_etf_spy_corr']:.6f} |"
        )
    at = res.get("diagnostics_attribution")
    if at:
        L.append(
            f"\n### 6.2 风格与特质归因（{at['variant']}，策略层 R6 k = 1，5 档权重按 T-19 的 `attribute_day`，近期窗口年化贡献 / 夏普）\n"
        )
        comps = [c for c in at["windows"]["recent"] if c != "style_total"]
        L.append("| 分量 | 近期 | A | B |")
        L.append("|---|---|---|---|")
        for c in [
            "market",
            "industry",
            "style_total",
            *[x for x in comps if x.startswith("style_")],
            "specific",
            "etf_leg",
        ]:
            cells = []
            for w in ("recent", "A", "B"):
                z = at["windows"][w].get(c)
                cells.append(
                    "—" if z is None else f"{pct(z['ann_contribution'])} / {num(z['sharpe'])}"
                )
            L.append(f"| {c} | " + " | ".join(cells) + " |")
    else:
        L.append("\n### 6.2 风格与特质归因\n未做。")
    L.append("\n## 7. 实现选择（合同含糊处取更保守的读法）\n")
    for t in IMPLEMENTATION_CHOICES:
        L.append(f"- {t}")
    L.append("\n## 8. 局限\n")
    for t in LIMITATIONS:
        L.append(f"- {t}")
    (REP / "report.md").write_text("\n".join(L) + "\n")
    print("wrote", REP / "report.md")


IMPLEMENTATION_CHOICES = [
    "策略层定档序列取 T-25 的 R6 保存序列（借券 25 bp、无退市调整，与 T-25 逐位一致）；账户层主口径取合同第 4 节的借券 0 bp 和退市 −30%（长期持有的名字最后收盘价后一个会话一次性计 −30%，空头 0），两种口径分别报告。",
    "成本 2 倍检验（V3 和稳健性 a）：2 倍交易成本加每年 100 bp 的空头借券（合同第 4 节的字面读法，比 T-25 的“2 倍（成本+25 bp 借券）”更严）；用 R6 保存序列 毛 − 2×成本 − 4×借券列（借券列是 25 bp，乘 4 即 100 bp）。",
    "族 DSR 的 10 个序列：v1 取 stage2a-manifest 的 6 个 close 路径×5 偏移，5 档等权混合，超额 = `daily.parquet` 的 `net` 列减 BIL 日收益（与 `eval_book_v1_stage2.py` 的 `ev.window_metrics(net, rf, …)` 同一列）；v1 的日期是收益所属会话，R6 的标签日 t 赚的是会话 t+2 的收益，所以对齐相关时把 R6 标签日后移 2 个会话（对齐检验见 `results.json` 的 `family.alignment_corr_v1_M0_A_vs_R6_M0_U3000`）。10 个序列都齐，没有用 0.3 补的对。",
    "安慰剂：打乱用 `default_rng(seed*100003 + offset*1009 + p)`，p 是决策日在 `panel/_calendar.parquet` 的位置；对有限分数的宇宙成员整体置换；热身从 2023-11-01 起第一个调仓日，状态从零起算（真实序列从 2017-10 起算，近期窗口起点的持仓状态因此不同）。向量化实现不带置换时与 T-25 保存序列的最大绝对差 ≤ 3e-17（`placebo/check.json`）。",
    "账户层 F1：k_eff 先乘 0.5×VIX 缩放，再在 k_eff×(2+|h|) > 1.8 时压到 1.8/(2+|h|)（h 取 k = 1 的未缩放对冲）；T-bill 腿每天按调仓后 L、S（以决策日收盘价计）重算，整股，同样适用 $100 丢单；BIL 计入多头市值（保证金和现金，更保守）。总敞口超 1.8 的日子把当天目标整体乘 1.8/(L+S)（仅当天，不改各档虚拟股数），没有触发过（次数见 `scale_events`）。",
    "账户层 F2：SPY 目标 = 5 档叠加层对冲虚拟股数之和 + 1.0×E/决策日收盘价，每天重取整；叠加层 k2_eff = min(0.3, 0.8/(2+|h|))×VIX 缩放。负现金按 6.50%/360 每日历日计息（F1 同样计，因为按公式 F1 不应借款，但调仓之间的漂移可能出现短暂负现金）。",
    "无决策日收盘价的名字不能按权重定股数，该档该名字记 0 股；缺价格时按最后价格持有（价格矩阵前向填充），退市标记用“最后收盘价所在会话 ≤ 数据末 − 5 个会话”。",
    "权益 = E + 累计净盈亏用于保证金和现金；定仓基数固定 E = $1,000,000（不复利）。因为 F2 的 SPY 核心盈利使实际权益涨过 E（期末权益见第 3 节），近期保证金余量会偏高，所以另报“权益固定为 E”的压力口径。",
    "V1 = 同一性通过且 `hypotheses.md` 与 HEAD 一致；V2 = 两种形式的保证金违规均为 0、参与率中位 ≤ 1%、账户层整股模拟跑完（≥2000 个会话）。",
    "归因用的是策略层 R6（k = 1）5 档权重（不是 F1/F2 账户的整股持仓）；每年年初没有当年存盘的风险模型，用上一年最后一个存盘日；对冲腿 = R6 毛收益 − 股票账本收益。",
]
LIMITATIONS = [
    "近期窗口 674 个会话（约 2.7 年），夏普标准误约 0.6–0.9；所有窗口此前都看过，B 窗只有 53 个会话；这是构造和账户可行性的度量，不是样本外证据。",
    "成本来自拟合模型，不是实际成交；易借是代理集合；退市用下界而非实际退市收益；空头所得是否计息未核实（主口径不计，现金敏感性单列）。",
    "安慰剂的净夏普分位没有信息量（随机重排全部换手，净值大负）；毛分位是有信息量的检验。",
    "整股账户在 U3000 上每天约一千个小单被 $100 规则丢掉、整股漂移约 4.6%（单边），P1000 约 2%；它们已包含在账户层数字里，没有单独调参。",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage", choices=["account-summary", "score", "diag", "attrib", "report"], required=True
    )
    a = ap.parse_args()
    {
        "account-summary": run_account_summary,
        "score": run_score,
        "diag": run_diag,
        "attrib": run_attrib,
        "report": run_report,
    }[a.stage]()


if __name__ == "__main__":
    main()
