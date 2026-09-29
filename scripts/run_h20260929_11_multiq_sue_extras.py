"""T-20260929-11 post-run report: results.json from the screen_lane leaderboard,
SPY/QQQ beta of ENET_TOP50, DSR with n_trials=9, and the information-only
ENET_LS long-short (top 50 long / bottom 50 short by model score, monthly,
10bp per side, 0.5%/yr borrow on the short leg).

    scripts/run_capped.sh --mem 1.3G -- uv run python scripts/run_h20260929_11_multiq_sue_extras.py

Reads only files produced by the preregistered pipeline; no parameter here was
chosen after seeing results (the criteria are copied from candidate-manifest.json).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import build_h20260929_11_multiq_sue_scores as sc  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

ITER = sc.ITER
SCREEN_DIR = ROOT / "reports/research/screens/h20260929_11_multiq_sue"
OUT_DIR = sc.OUT_DIR
K1_ANCHOR, K1_STRESS = 1.1882, 0.6447
S3_ANCHOR, S3_STRESS = 1.4853, 0.8059
WINDOWS = {
    "anchor": ("2024-01-08", "2026-09-17"),
    "stress": ("2019-01-02", "2023-09-15"),
    "select": ("2023-09-18", "2025-12-31"),
}
KEEP_ELIGIBLE = ["ENET_TOP50", "ENET_TOP20", "ENET_MOM_TOP50"]
BORROW_YR = 0.005
COST = 0.0010


def _daily_prices(symbols: list[str]) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='400MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""SELECT symbol, timestamp::DATE AS d, close
            FROM read_parquet('data/sip/daily/*/*.parquet')
            WHERE symbol IN ({in_list}) AND d >= DATE '2015-12-01' AND d <= DATE '{sc.PANEL_END}'"""
    ).df()
    con.close()
    out = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    out.index = pd.to_datetime(out.index)
    return out


def _sharpe(r: pd.Series, rf: pd.Series | None = None) -> float:
    x = r if rf is None else r - rf.reindex(r.index).fillna(0.0)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if x.std(ddof=1) > 0 else float("nan")


def candidate_table(lb: dict) -> dict[str, dict]:
    table: dict[str, dict] = {}
    for c in lb["candidates"]:
        row: dict = {"first_valid_signal_date": c["first_valid_signal_date"]}
        for w in ("anchor", "stress", "select"):
            pw = c["per_window"][w]
            offs = pw["offsets"]
            row[f"{w}_median_sharpe_net10"] = pw["summary_net10"]["sharpe"]["median"]
            row[f"{w}_median_cagr_net10"] = pw["summary_net10"]["cagr"]["median"]
            row[f"{w}_median_cagr_net20"] = float(
                np.median([offs[o]["net20"]["cagr"] for o in offs])
            )
            row[f"{w}_min_cagr_net20"] = float(min(offs[o]["net20"]["cagr"] for o in offs))
            row[f"{w}_median_max_dd_net10"] = pw["summary_net10"]["max_dd"]["median"]
            row[f"{w}_actual_start"] = pw["actual_start"]
        row["k2_edge_anchor"] = c["diversifier"]["anchor"]["judged_edge"]
        row["k2_edge_stress"] = c["diversifier"]["stress"]["judged_edge"]
        row["dsr_anchor_n8"] = c.get("dsr_anchor")
        row["corr_s3_anchor"] = c["correlation_with_s3"]["anchor"]
        row["corr_s3_stress"] = c["correlation_with_s3"]["stress"]
        table[c["id"]] = row
    return table


def verdicts(table: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cid in KEEP_ELIGIBLE:
        t = table[cid]
        k1_sharpe = (
            t["anchor_median_sharpe_net10"] >= K1_ANCHOR
            and t["stress_median_sharpe_net10"] >= K1_STRESS
        )
        k1_cagr = t["anchor_median_cagr_net20"] > 0 and t["stress_median_cagr_net20"] > 0
        k1 = bool(k1_sharpe and k1_cagr)
        k2 = bool(t["k2_edge_anchor"] >= 0.05 and t["k2_edge_stress"] >= 0.05)
        watch = bool(t["anchor_median_sharpe_net10"] >= K1_ANCHOR and not k1)
        strong = bool(
            (t["k2_edge_anchor"] >= 0.10 and t["k2_edge_stress"] >= 0.10)
            or (
                t["anchor_median_sharpe_net10"] >= S3_ANCHOR
                and t["stress_median_sharpe_net10"] >= S3_STRESS
            )
        )
        inc = {
            name: {
                "candidate_anchor": t["anchor_median_sharpe_net10"],
                "other_anchor": table[name]["anchor_median_sharpe_net10"],
                "candidate_greater": bool(
                    t["anchor_median_sharpe_net10"] > table[name]["anchor_median_sharpe_net10"]
                ),
            }
            for name in ("SUE1_TOP50", "MOM12_1_TOP50", "ENET_SHUF_TOP50", "RAND_TOP50")
        }
        increment = all(v["candidate_greater"] for v in inc.values())
        out[cid] = {
            "K1": k1,
            "K1_sharpe_both_windows": bool(k1_sharpe),
            "K1_net20_cagr_positive_both": bool(k1_cagr),
            "K2": k2,
            "watch_recent": watch,
            "strong_keep": strong,
            "increment_comparisons": inc,
            "increment_criterion": bool(increment),
            "tier_and_increment": bool((k1 or k2 or watch) and increment),
        }
    return out


def beta_report(returns: pd.DataFrame, lb: dict) -> dict:
    px = _daily_prices(["SPY", "QQQ", "BIL"])
    ret = px.pct_change(fill_method=None)
    rf = ret["BIL"].fillna(0.0)
    out: dict = {}
    for cid in ("ENET_TOP50", "ENET_MOM_TOP50", "MOM12_1_TOP50", "SUE1_TOP50", "EW_POOL"):
        cols = [c for c in returns.columns if c.startswith(f"{cid}__o") and c.endswith("net10")]
        book = returns[cols].mean(axis=1)  # date-neutral: average of all 21 offsets
        a0, a1 = map(pd.Timestamp, WINDOWS["anchor"])
        book = book.loc[a0:a1]
        row: dict = {"window": list(WINDOWS["anchor"]), "n_days": int(len(book))}
        for bench in ("SPY", "QQQ"):
            m = ret[bench].reindex(book.index)
            ok = m.notna() & book.notna()
            x = m[ok] - rf.reindex(book.index)[ok]
            y = book[ok] - rf.reindex(book.index)[ok]
            beta = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))
            alpha_d = float(y.mean() - beta * x.mean())
            resid = y - beta * x
            row[bench] = {
                "beta": beta,
                "alpha_annualized_excess_of_rf": alpha_d * 252,
                "alpha_tstat": float(alpha_d / (resid.std(ddof=1) / np.sqrt(len(resid)))),
                "corr": float(np.corrcoef(y, x)[0, 1]),
                "bench_annualized_return_excess": float(x.mean() * 252),
            }
        out[cid] = row
    # DSR with n_trials = 9 for the judged anchor offset of ENET_TOP50
    cand = next(c for c in lb["candidates"] if c["id"] == "ENET_TOP50")
    off = cand["judged"]["anchor"]["offset"]
    r = returns[f"ENET_TOP50__o{off:02d}__net10"]
    start = pd.Timestamp(cand["per_window"]["anchor"]["actual_start"])
    r = r.loc[start : pd.Timestamp(WINDOWS["anchor"][1])]
    excess = (r - rf.reindex(r.index).fillna(0.0)).to_numpy()
    out["dsr_enet_top50_n9"] = float(deflated_sharpe_probability(excess, trial_count=9, hac_lag=21))
    return out


def enet_long_short() -> dict:
    close, open_, _ = sc.load_pool_prices()
    scores = pd.read_parquet(OUT_DIR / "scores.parquet")
    scores["date"] = pd.to_datetime(scores["date"])
    by_date = {d: g for d, g in scores.groupby("date")}
    idx = close.index
    op = open_.to_numpy()
    op_ff = open_.ffill().to_numpy()
    col = {s: i for i, s in enumerate(close.columns)}
    me = sc.month_end_positions(idx)
    rows = []
    prev_long: set[str] = set()
    prev_short: set[str] = set()
    for p in me:
        d = idx[p]
        if d < pd.Timestamp("2019-01-02") or p + sc.LABEL_END >= len(idx) or d not in by_date:
            continue
        g = by_date[d]
        syms = g["symbol"].to_numpy()
        key = np.random.default_rng([sc.SEED, d.year * 100 + d.month]).random(len(g))
        order = np.lexsort((key, -g["score"].to_numpy()))
        longs = list(syms[order[:50]])
        shorts = list(syms[order[-50:]])

        def hold_ret(names: list[str], p: int = p) -> float:
            vals = []
            for s in names:
                start = op[p + sc.LABEL_START, col[s]]
                end = op_ff[p + sc.LABEL_END, col[s]]
                if np.isfinite(start) and np.isfinite(end):
                    vals.append(end / start - 1.0)
            return float(np.mean(vals)) if vals else 0.0

        rl, rs = hold_ret(longs), hold_ret(shorts)
        turn_l = 1.0 - len(prev_long & set(longs)) / 50.0 if prev_long else 1.0
        turn_s = 1.0 - len(prev_short & set(shorts)) / 50.0 if prev_short else 1.0
        # each side trades turn * weight both in and out -> 2 * turn * side weight
        cost = COST * (2.0 * turn_l + 2.0 * turn_s) + BORROW_YR / 12.0
        rows.append({"date": idx[p + sc.LABEL_START], "gross": rl - rs, "net": rl - rs - cost})
        prev_long, prev_short = set(longs), set(shorts)
    df = pd.DataFrame(rows).set_index("date")
    out: dict = {"n_months": int(len(df)), "note": "offset 0 (month-end) only, information only"}
    for w, (a, b) in WINDOWS.items():
        sub = df.loc[a:b]
        if len(sub) < 6:
            continue
        m = sub["net"]
        out[w] = {
            "n_months": int(len(sub)),
            "mean_monthly_net": float(m.mean()),
            "annualized_return_net": float(m.mean() * 12),
            "sharpe_net": float(m.mean() / m.std(ddof=1) * np.sqrt(12)),
            "sharpe_gross": float(sub["gross"].mean() / sub["gross"].std(ddof=1) * np.sqrt(12)),
            "cost_note": "10bp/side on traded weight + 0.5%/yr borrow on short notional",
        }
    return out


def main() -> int:
    lb = json.loads((SCREEN_DIR / "leaderboard.json").read_text(encoding="utf-8"))
    returns = pd.read_parquet(SCREEN_DIR / "returns.parquet")
    table = candidate_table(lb)
    ver = verdicts(table)
    fits = json.loads((OUT_DIR / "model-fits.json").read_text(encoding="utf-8"))
    beta = beta_report(returns, lb)
    ls = enet_long_short()
    result = {
        "iter_id": ITER,
        "source_files": {
            "leaderboard": "reports/research/screens/h20260929_11_multiq_sue/leaderboard.json",
            "returns": "reports/research/screens/h20260929_11_multiq_sue/returns.parquet",
            "model_fits": f"reports/research/iterations/{ITER}/model-fits.json",
            "price_hygiene": f"reports/research/iterations/{ITER}/price-hygiene.json",
        },
        "windows": WINDOWS,
        "thresholds": {
            "K1_anchor": K1_ANCHOR,
            "K1_stress": K1_STRESS,
            "S3_anchor": S3_ANCHOR,
            "S3_stress": S3_STRESS,
        },
        "stress_note": "stress sample short: candidates hold positions only from 2019-01-02",
        "n_trials_lane": lb["n_trials"],
        "candidates": table,
        "verdicts": ver,
        "monthly_rankic": fits["monthly_rankic"],
        "constant_score_years": [
            y for y, f in fits["fits"].items() if all(v == 0 for v in f["coef"].values())
        ],
        "beta_report": beta,
        "enet_long_short_information_only": ls,
        "workflow_pass": True,
        "research_pass": any(v["tier_and_increment"] for v in ver.values()),
        "llm_contribution_pass": False,
        "ml_contribution_pass": any(v["tier_and_increment"] for v in ver.values()),
        "paper_ready_pass": False,
    }
    (OUT_DIR / "results.json").write_text(
        json.dumps(result, indent=2, default=float), encoding="utf-8"
    )
    print(json.dumps({"verdicts": ver, "beta": beta, "ls": ls}, indent=1, default=float)[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
