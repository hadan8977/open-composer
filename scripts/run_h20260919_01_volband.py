"""H-20260919-01: relative strength inside a mechanical volatility band.

This follows directly from H-20260918-06's mechanism, not from a new idea. That
card showed a pooled ETF ranking fails in two opposite ways, and the holdings
diagnostic said why: over a pool spanning T-bill funds to 3x funds, dividing the
score by volatility degenerates into buying T-bills (holdout Sharpe 2.91 at 6.7%
annualized, 0.29% median holding volatility) and not dividing degenerates into
buying the most levered product available (100% median holding volatility, -58 to
-75% drawdown). The conclusion was that cross-sectional momentum needs a
RISK-HOMOGENEOUS candidate set, which is what the hand-picked sector menu supplied
by accident: eleven comparable 1x equity funds, so the ranking compares signal
rather than leverage.

Hypothesis: replace my choice of members with a mechanical volatility band, keep
the homogeneity, and the sector sleeve's result should reproduce or improve.

Design choices that matter, both taken from what went wrong before:
  * ABSOLUTE volatility bands, not quantile buckets. A quantile bucket's risk
    character drifts with the market; homogeneity is the whole point, so the band
    has to be pinned to a volatility level.
  * The bands exclude below 5% and at or above 60% annualized volatility, which
    removes the cash-like and the levered corners BY CONSTRUCTION rather than by
    a name-pattern guess. H-20260918-06's name-based levered filter still let BITO
    through at 34% volatility, so names are not a reliable proxy for risk.
  * The risk_adj score is dropped entirely. It is proven degenerate: dividing by
    volatility inside an already volatility-homogeneous band would also be close
    to meaningless.
  * The holdings diagnostic runs INSIDE this card rather than as an afterthought.
    H-20260918-06 only caught its own degeneration because I went looking; the
    check that decides the verdict should not be optional.

Second arm, added before the full grid ran and disclosed as such
-----------------------------------------------------------------
A single smoke cell (midvol 15-30%, blend score, top 3, monthly) was run while
this file was being written. It confirmed the mechanism -- 24.6% median holding
volatility, nothing under 5%, nothing over 60%, so neither degeneration can
recur -- and it also showed WHAT the band actually holds: SVXY (inverse VIX),
TBF (inverse 20-year Treasuries), ITB (homebuilders), EWW (Mexico equity), GSG
(broad commodities). Equal volatility, completely unrelated risk drivers. Its
numbers were selection Sharpe 0.48, holdout -0.04, and the random-pick placebo
inside the same band beat it on the holdout in 20 of 20 seeds.

That says volatility homogeneity is not the property the sector menu has. The
eleven SPDR sectors are an exhaustive partition of ONE market: they share a
common factor, so ranking them isolates the rotation component rather than
guessing which asset class just ran. So a second dimension is preregistered
here, ``beta_filter``: require a trailing 250-session return correlation to SPY
of at least 0.70, i.e. "same market, different slice, comparable risk". The
vol-only arm is kept so the two are measured against each other rather than one
replacing the other on a hunch. The smoke cell's numbers above are part of this
card's record and are not re-derived as a fresh discovery below.

Windows, costs, fills and the placebo protocol are inherited from
scripts/run_h20260918_05_recent_menu.py unchanged, so all three cards compare
directly. The bar is not SPMO: it is the sector sleeve already trading on paper,
anchor Sharpe 1.36 at 27.8% annualized with a -16.9% drawdown, holdout Sharpe 2.22.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

BASE = importlib.import_module("run_h20260918_05" + "_recent_menu")
POOL = importlib.import_module("run_h20260918_06" + "_etf_pool")

OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260919_01_volband"

CASH = "SHY"
RF = "BIL"
VOL_WINDOW = 63
#: (name, low, high) in annualized volatility. Half-open [low, high).
VOL_BANDS: list[tuple[str, float, float]] = [
    ("lowvol_05_15", 0.05, 0.15),
    ("midvol_15_30", 0.15, 0.30),
    ("highvol_30_60", 0.30, 0.60),
    ("midhigh_15_60", 0.15, 0.60),
]
GRID_SCORES = ["blend", "r252"]
GRID_BETA = ["none", "corr_spy_ge_70"]
BETA_BENCH = "SPY"
BETA_WINDOW = 250
BETA_MIN_CORR = 0.70
GRID_TOPN = [2, 3, 5]
GRID_REBAL = ["monthly", "weekly"]

COST_BPS_PRIMARY = 10.0
COST_BPS_STRESS = 20.0
PLACEBO_SEEDS = 20
MIN_BAND_SIZE = 6

INCUMBENT = {
    "name": "sector sleeve on paper (rot_A2_sector_lb252_top2_weekly)",
    "select_sharpe": 1.135,
    "holdout_sharpe": 2.216,
    "anchor_sharpe": 1.361,
    "anchor_cagr": 0.278,
    "anchor_max_dd": -0.169,
}


def band_members(
    day: pd.Timestamp,
    eligible: list[str],
    vol: pd.DataFrame,
    low: float,
    high: float,
) -> list[str]:
    if not eligible:
        return []
    row = vol.loc[day, [s for s in eligible if s in vol.columns]].dropna()
    inside = row.loc[(row >= low) & (row < high)]
    return sorted(inside.index)


BETA_CACHE: dict = {}


def beta_members(
    day: pd.Timestamp,
    members: list[str],
    returns: pd.DataFrame,
    arm: str,
) -> list[str]:
    """Keep only candidates that move with the benchmark.

    ``corr_spy_ge_70`` is the mechanical statement of what the hand-picked sector
    menu is: eleven slices of one market. A fund whose trailing correlation to
    SPY is below the floor may have the same volatility as a sector ETF and still
    be an unrelated bet (inverse VIX, inverse Treasuries, a single foreign
    market), which is what the vol-only arm was found to be holding."""
    if arm == "none":
        return members
    if arm != "corr_spy_ge_70":
        raise ValueError(f"unknown beta arm: {arm!r}")
    key = (day, tuple(members))
    hit = BETA_CACHE.get(key)
    if hit is not None:
        return hit
    window = returns.loc[:day].tail(BETA_WINDOW)
    if BETA_BENCH not in window.columns or len(window) < 120:
        BETA_CACHE[key] = []
        return []
    bench = window[BETA_BENCH]
    cols = [c for c in members if c in window.columns]
    corr = window[cols].corrwith(bench)
    kept = sorted(corr.loc[corr >= BETA_MIN_CORR].index)
    if len(BETA_CACHE) > 4096:
        BETA_CACHE.clear()
    BETA_CACHE[key] = kept
    return kept


def run_cell(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    dollar: pd.DataFrame,
    returns: pd.DataFrame,
    vol: pd.DataFrame,
    scores: pd.DataFrame,
    levered: set[str],
    *,
    low: float,
    high: float,
    beta_arm: str,
    top_n: int,
    rebal: str,
    cost_bps: float,
    rng: np.random.Generator | None = None,
    collect_holdings: bool = False,
) -> tuple[pd.Series, pd.Series, dict]:
    flags = BASE.rebalance_flags(close.index, rebal)
    signal_dates = list(close.index[flags])
    cash_score = scores[CASH]
    books: dict[pd.Timestamp, dict[str, float]] = {}
    band_sizes: list[tuple[pd.Timestamp, int]] = []
    held: Counter = Counter()
    held_vols: list[float] = []
    skipped_small_band = 0
    for day in signal_dates:
        eligible = POOL.eligible_at(day, close, dollar, levered, "all")
        members = band_members(day, eligible, vol, low, high)
        members = beta_members(day, members, returns, beta_arm)
        band_sizes.append((day, len(members)))
        if len(members) < MIN_BAND_SIZE:
            skipped_small_band += 1
            books[day] = {CASH: 1.0}
            continue
        row = scores.loc[day, members].dropna()
        if row.empty:
            books[day] = {CASH: 1.0}
            continue
        if rng is not None:
            order = list(rng.permutation(list(row.index)))
        else:
            order = list(row.sort_values(ascending=False).index)
        chosen = POOL.pick_with_corr_cap(order, returns, day, top_n, corr_cache=POOL.CORR_CACHE)
        cs = cash_score.loc[day]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        if not chosen:
            books[day] = {CASH: 1.0}
            continue
        books[day] = {s: 1.0 / len(chosen) for s in chosen}
        if collect_holdings:
            for s in chosen:
                held[s] += 1
                v = vol.loc[day, s]
                if v == v:
                    held_vols.append(float(v))
    cols = sorted(set(close.columns))
    pos = {d: i for i, d in enumerate(close.index)}
    next_change: dict[int, dict[str, float]] = {}
    for day, book in books.items():
        i = pos[day]
        if i + 1 < len(close.index):
            next_change[i + 1] = book
    rows: list[dict[str, float]] = []
    current: dict[str, float] = {CASH: 1.0}
    for i in range(len(close.index)):
        if i in next_change:
            current = next_change[i]
        rows.append(dict(current))
    w = pd.DataFrame(rows, index=close.index).reindex(columns=cols).fillna(0.0)
    ret = BASE.portfolio_returns(w, close, open_, cost_bps)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    # Band sizes are reported over the evaluated window only. Warmup-era signal
    # dates have no eligible names at all (the PIT history rule has not been met
    # yet), so including them would make the minimum meaninglessly zero.
    live_start = pd.Timestamp(BASE.SELECT_START)
    live = [n for d, n in band_sizes if d >= live_start]
    info: dict = {
        "rebalances": len(signal_dates),
        "rebalances_evaluated": len(live),
        "band_size_min": int(min(live)) if live else 0,
        "band_size_median": int(np.median(live)) if live else 0,
        "band_size_max": int(max(live)) if live else 0,
        "rebalances_skipped_small_band": skipped_small_band,
        "rebalances_skipped_small_band_in_window": sum(
            1 for d, n in band_sizes if d >= live_start and n < MIN_BAND_SIZE
        ),
    }
    if collect_holdings:
        total = max(sum(held.values()), 1)
        vseries = pd.Series(held_vols, dtype=float)
        info["holdings"] = {
            "distinct_symbols": len(held),
            "median_holding_vol": round(float(vseries.median()), 4) if len(vseries) else None,
            "share_vol_under_5pct": round(float((vseries < 0.05).mean()), 4)
            if len(vseries)
            else None,
            "share_vol_over_60pct": round(float((vseries > 0.60).mean()), 4)
            if len(vseries)
            else None,
            "top": [{"symbol": s, "share": round(n / total, 3)} for s, n in held.most_common(10)],
        }
    return ret, turnover, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=PLACEBO_SEEDS)
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    funds = POOL.load_fund_names()
    levered = set(funds.loc[funds["is_levered"], "symbol"])
    symbols = sorted(set(funds["symbol"]) | {CASH, RF, "SPY", "SPMO", "QQQ"})

    grid: list[dict] = []
    for band, low, high in VOL_BANDS:
        for score in GRID_SCORES:
            for beta_arm in GRID_BETA:
                for top_n in GRID_TOPN:
                    for rebal in GRID_REBAL:
                        grid.append(
                            {
                                "cell_id": (f"vb_{band}_{score}_{beta_arm}_top{top_n}_{rebal}"),
                                "family": f"{band}|{score}|{beta_arm}",
                                "band": band,
                                "low": low,
                                "high": high,
                                "beta_arm": beta_arm,
                                "score": score,
                                "top_n": top_n,
                                "rebalance": rebal,
                            }
                        )
    manifest = {
        "card_id": "H-20260919-01",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "windows": BASE.WINDOWS,
        "vol_bands": [{"name": n, "low": lo, "high": hi} for n, lo, hi in VOL_BANDS],
        "vol_window": VOL_WINDOW,
        "min_band_size": MIN_BAND_SIZE,
        "pit_universe_rule": {
            "classifier": "asset_metadata.is_probable_fund_or_etf",
            "min_history_sessions": POOL.MIN_HISTORY_SESSIONS,
            "min_dollar_adv": POOL.MIN_DOLLAR_ADV,
            "adv_window": POOL.ADV_WINDOW,
        },
        "beta_filter": {
            "arms": GRID_BETA,
            "benchmark": BETA_BENCH,
            "window": BETA_WINDOW,
            "min_corr": BETA_MIN_CORR,
            "added_after_smoke_cell": (
                "disclosed in the module docstring: one smoke cell showed the "
                "vol-only band holds SVXY, TBF, EWW and GSG together, so "
                "volatility homogeneity is not the sector menu's property"
            ),
        },
        "max_pair_corr": POOL.MAX_PAIR_CORR,
        "cells": grid,
        "cell_count": len(grid),
        "family_count": len({c["family"] for c in grid}),
        "incumbent_to_beat": INCUMBENT,
        "selection_rule": (
            "highest selection-window Sharpe within each (band, score, beta arm) family; the "
            "holdout is never used to rank. A family pick is only interesting if it "
            "beats the incumbent sector sleeve on the anchor window AND its holdings "
            "diagnostic shows a median volatility inside its own band"
        ),
        "placebo_seeds": args.seeds,
        "dropped_by_design": (
            "risk_adj score dropped: H-20260918-06 proved it degenerates into T-bill "
            "funds. Volatility bands replace the name-based levered filter, which let "
            "BITO through at 34% volatility."
        ),
    }
    (OUT_DIR / "candidate-manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"preregistered {len(grid)} cells in {manifest['family_count']} families")

    t0 = time.time()
    close, open_, dollar = POOL.load_panel(symbols)
    print(f"panel {close.shape[0]} sessions x {close.shape[1]} symbols")
    returns = close.pct_change(fill_method=None)
    vol = returns.rolling(VOL_WINDOW, min_periods=40).std() * np.sqrt(252.0)
    rf = close[RF].pct_change(fill_method=None).fillna(0.0)
    score_cache = {kind: POOL.score_frame(close, kind) for kind in GRID_SCORES}

    rows: list[dict] = []
    infos: dict[str, dict] = {}
    series: dict[str, pd.Series] = {}
    for n, spec in enumerate(grid, 1):
        for tag, cost in (("net10", COST_BPS_PRIMARY), ("net20", COST_BPS_STRESS)):
            ret, tv, info = run_cell(
                close,
                open_,
                dollar,
                returns,
                vol,
                score_cache[spec["score"]],
                levered,
                low=spec["low"],
                high=spec["high"],
                beta_arm=spec["beta_arm"],
                top_n=spec["top_n"],
                rebal=spec["rebalance"],
                cost_bps=cost,
                collect_holdings=(tag == "net10"),
            )
            wm = BASE.window_metrics(ret, rf, tv)
            row = {"cell_id": spec["cell_id"], "family": spec["family"], "cost": tag}
            for wname, m in wm.items():
                for k, v in asdict(m).items():
                    row[f"{wname}_{k}"] = v
            rows.append(row)
            if tag == "net10":
                infos[spec["cell_id"]] = info
                series[spec["cell_id"]] = ret
        # Written after every cell: 96 cells x 2 cost arms is long enough that a
        # kill at the 21:45 UTC heavy-job stop must not lose the completed ones.
        pd.DataFrame(rows).to_parquet(OUT_DIR / "cells.parquet", index=False)
        (OUT_DIR / "holdings_diagnostic.json").write_text(
            json.dumps(infos, indent=2, default=float)
        )
        print(f"  {n}/{len(grid)} {spec['cell_id']} {time.time() - t0:.0f}s elapsed", flush=True)
    for bench in ("SPY", "SPMO", "QQQ"):
        ret, tv = BASE.buy_hold(close, open_, bench)
        wm = BASE.window_metrics(ret, rf, tv)
        row = {"cell_id": f"bench_{bench}", "family": "benchmark", "cost": "net0"}
        for wname, m in wm.items():
            for k, v in asdict(m).items():
                row[f"{wname}_{k}"] = v
        rows.append(row)
    table = pd.DataFrame(rows)
    table.to_parquet(OUT_DIR / "cells.parquet", index=False)
    (OUT_DIR / "holdings_diagnostic.json").write_text(json.dumps(infos, indent=2, default=float))

    primary = table.loc[table["cost"] == "net10"]
    cells = primary.loc[primary["family"] != "benchmark"]
    picks = cells.sort_values("select_sharpe", ascending=False).groupby("family").head(1)

    placebo_path = OUT_DIR / "placebo.parquet"
    placebo_rows: list[dict] = []
    for cell_id in picks["cell_id"]:
        spec = next(g for g in grid if g["cell_id"] == cell_id)
        for seed in range(args.seeds):
            rng = np.random.default_rng(seed)
            pret, ptv, _ = run_cell(
                close,
                open_,
                dollar,
                returns,
                vol,
                score_cache[spec["score"]],
                levered,
                low=spec["low"],
                high=spec["high"],
                beta_arm=spec["beta_arm"],
                top_n=spec["top_n"],
                rebal=spec["rebalance"],
                cost_bps=COST_BPS_PRIMARY,
                rng=rng,
            )
            pwm = BASE.window_metrics(pret, rf, ptv)
            placebo_rows.append(
                {
                    "cell_id": cell_id,
                    "seed": seed,
                    "select_sharpe": pwm["select"].sharpe,
                    "holdout_sharpe": pwm["holdout"].sharpe,
                    "anchor_sharpe": pwm["anchor"].sharpe,
                    "anchor_cagr": pwm["anchor"].cagr,
                }
            )
        pd.DataFrame(placebo_rows).to_parquet(placebo_path, index=False)
        print(f"  placebo done: {cell_id} {time.time() - t0:.0f}s elapsed", flush=True)
    placebo = pd.DataFrame(placebo_rows)

    summary: dict = {
        "card_id": "H-20260919-01",
        "cell_count": len(grid),
        "windows": BASE.WINDOWS,
        "incumbent_to_beat": INCUMBENT,
        "benchmarks": [],
        "family_picks": [],
    }
    for bench in ("SPY", "SPMO", "QQQ"):
        r = table.loc[table["cell_id"] == f"bench_{bench}"].iloc[0]
        summary["benchmarks"].append(
            {
                "cell_id": f"bench_{bench}",
                "select_sharpe": r["select_sharpe"],
                "holdout_sharpe": r["holdout_sharpe"],
                "anchor_sharpe": r["anchor_sharpe"],
                "anchor_cagr": r["anchor_cagr"],
                "anchor_max_dd": r["anchor_max_dd"],
            }
        )
    for _, r in picks.iterrows():
        cid = r["cell_id"]
        stress = table.loc[(table["cell_id"] == cid) & (table["cost"] == "net20")].iloc[0]
        pb = placebo.loc[placebo["cell_id"] == cid] if not placebo.empty else pd.DataFrame()
        entry = {
            "family": r["family"],
            "cell_id": cid,
            "select_sharpe": r["select_sharpe"],
            "select_cagr": r["select_cagr"],
            "holdout_sharpe": r["holdout_sharpe"],
            "holdout_cagr": r["holdout_cagr"],
            "holdout_max_dd": r["holdout_max_dd"],
            "anchor_sharpe": r["anchor_sharpe"],
            "anchor_cagr": r["anchor_cagr"],
            "anchor_max_dd": r["anchor_max_dd"],
            "turnover_yr": r["select_turnover_yr"],
            "stress20_anchor_sharpe": stress["anchor_sharpe"],
            "beats_incumbent_anchor_sharpe": bool(r["anchor_sharpe"] > INCUMBENT["anchor_sharpe"]),
            "beats_incumbent_anchor_cagr": bool(r["anchor_cagr"] > INCUMBENT["anchor_cagr"]),
            "diagnostic": infos.get(cid, {}),
        }
        if not pb.empty:
            entry["placebo_holdout_median"] = float(pb["holdout_sharpe"].median())
            entry["placebo_holdout_p90"] = float(pb["holdout_sharpe"].quantile(0.90))
            entry["placebo_holdout_beat_frac"] = float(
                (pb["holdout_sharpe"] >= r["holdout_sharpe"]).mean()
            )
            entry["placebo_anchor_beat_frac"] = float(
                (pb["anchor_sharpe"] >= r["anchor_sharpe"]).mean()
            )
        summary["family_picks"].append(entry)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    equity = pd.DataFrame({k: (1.0 + v).cumprod() for k, v in series.items()})
    equity.to_parquet(OUT_DIR / "equity.parquet")
    print(json.dumps(summary["benchmarks"], indent=2, default=float))
    print(json.dumps(summary["family_picks"], indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
