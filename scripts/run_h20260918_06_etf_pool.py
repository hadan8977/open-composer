"""H-20260918-06: pooled cross-sectional ETF relative strength, no hand-picked menu.

Card H-20260918-05 shipped three sleeves. Its weakest point, stated in the card,
is that I chose each menu knowing which assets led 2023-2026; for the growth
sleeve a random 2-of-6 pick from the same menu reached its holdout Sharpe in 20%
of seeds. Its strongest point is the sector sleeve, where relative strength inside
a coherent group beat the random-pick placebo in 98% of seeds.

This card removes the menu. At every formation date the candidate set is defined
by a mechanical point-in-time liquidity rule over every fund-classified symbol in
the archive, so there is no group for hindsight to enter through. The question is
whether relative strength among ETFs survives without me choosing the group.

Windows, costs, fills and the placebo protocol are inherited unchanged from
scripts/run_h20260918_05_recent_menu.py so the two cards are directly comparable:
selection 2023-09-18..2025-12-31, untouched holdout 2026-01-02..2026-09-17, anchor
2024-01-08..2026-09-16, net 10 bp per side, signal on close and fill at the next
open, fully adjusted prices.

Point-in-time universe, recomputed at every formation date from data available
strictly up to that date:
  * symbol is classified as a fund/ETF by open_composer.research.features.asset_metadata
  * at least MIN_HISTORY_SESSIONS sessions of history
  * trailing 60-session dollar ADV at or above MIN_DOLLAR_ADV

Three problems a pooled ETF universe has that a hand-picked menu does not, each
handled explicitly rather than ignored:
  1. Levered and inverse funds amplify any return, so a raw-return ranking just
     buys 3x funds. Hence the levered/inverse split as a preregistered axis, and a
     risk-adjusted score variant that neutralises leverage by construction.
  2. Near-duplicates (SPY, IVV, VOO, VTI) can fill the whole book with one
     exposure. Hence the correlation cap, which drops a candidate whose trailing
     return correlation with an already-selected pick exceeds MAX_PAIR_CORR.
  3. Survivorship: closed funds are absent from today's metadata, and closed funds
     were usually bad.

SURVIVORSHIP, MEASURED AND UNRESOLVED (2026-09-18)
The first version of the section-0 probe reported 0 of 384 liquid funds gone, which
is impossible -- US fund closures run in the hundreds per year. The probe was
tautological: the symbol list comes from the cached Alpaca asset metadata, which
holds 5,910 fund rows of which exactly 0 have a last trading day before 2026-09.
Alpaca's assets API does not return delisted symbols (already recorded in this
repo's delisted-backfill work), so a probe built on that list can never detect
attrition. The probe now says so instead of printing a reassuring zero.

The delisted archive at data/sip-delisted/by_year does hold 4,833 dead symbols, 183
of them above 20M dollar ADV in H1 2023, but they are stocks (FRC, ATVI, PXD,
SIVB, SGEN) because its candidate union came from Form 4 issuers, SEC company
tickers and 13D filers. It gives no delisted-fund coverage.

So the bias is real and unquantified. What bounds it: this is a long-only top-K
pick with a liquidity floor, so a missing fund only matters if the strategy would
have HELD it, and a fund heading for closure is shrinking and performing badly, at
the bottom of the very ranking this strategy takes the top of. The exception, and
it is the one that matters, is the levered arm: a levered or thematic fund can be a
top-K momentum pick and then close after a crash. Read the levered arm as carrying
unmeasured survivorship risk and prefer the exclude-levered arm unless the levered
arm's advantage is large.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_h20260918_05_recent_menu as BASE  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260918_06_etf_pool"
#: Shared across cells in one process: the correlation matrix for a given
#: (date, candidate shortlist) is identical for every cell that asks for it.
CORR_CACHE: dict = {}
META_PATH = ROOT / "data" / "features" / "universe_backup_2026-09-16" / "_asset_metadata.parquet"

WARMUP_START = "2021-06-01"
CASH = "SHY"
RF = "BIL"

MIN_HISTORY_SESSIONS = 250
MIN_DOLLAR_ADV = 20_000_000.0
ADV_WINDOW = 60
MAX_PAIR_CORR = 0.95
CORR_WINDOW = 250
#: Only the top-ranked candidates are considered for the correlation cap. The
#: cap can reject at most CORR_PREFILTER - top_n candidates before it runs out,
#: and with top_n at most 10 that leaves 30 rejections of headroom, which never
#: binds in this data. Without the prefilter the cap was pairwise over the whole
#: eligible set and the grid would not finish in a day.
CORR_PREFILTER = 40

GRID_SCORES = ["blend", "risk_adj", "r63", "r252"]
GRID_LEVERAGE = ["all", "exclude_levered"]
GRID_TOPN = [3, 5, 10]
GRID_REBAL = ["monthly", "weekly"]
GRID_WEIGHTING = ["equal", "inverse_vol"]

COST_BPS_PRIMARY = 10.0
COST_BPS_STRESS = 20.0
PLACEBO_SEEDS = 40

#: Name patterns for a levered or inverse fund. Deliberately broad: a false
#: positive only removes a candidate, a false negative smuggles leverage into the
#: "exclude_levered" arm and would silently invalidate that whole arm.
LEVERED_PATTERNS = (
    "2X",
    "3X",
    "1.5X",
    "-1X",
    "ULTRA",
    "ULTRASHORT",
    "ULTRAPRO",
    "LEVERAGED",
    "INVERSE",
    "BEAR",
    "BULL",
    "SHORT ",
    "DAILY 2",
    "DAILY 3",
    "DOUBLE",
    "TRIPLE",
    "GEARED",
    "PROSHARES ULTRA",
    "DIREXION DAILY",
)


def load_fund_names() -> pd.DataFrame:
    meta = pd.read_parquet(META_PATH)
    meta["symbol"] = meta["symbol"].str.upper()
    meta["name_upper"] = meta["name"].fillna("").str.upper()
    funds = meta.loc[meta["is_probable_fund_or_etf"].fillna(False)].copy()
    funds["is_levered"] = funds["name_upper"].apply(
        lambda name: any(pattern in name for pattern in LEVERED_PATTERNS)
    )
    return funds[["symbol", "name", "is_levered"]].drop_duplicates("symbol")


def load_panel(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='700MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT upper(symbol) AS symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('data/sip/daily/*/*.parquet')
        WHERE upper(symbol) IN ({in_list})
              AND timestamp::DATE >= DATE '{WARMUP_START}'
              AND timestamp::DATE <= DATE '{BASE.HOLD_END}'
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    close = frame.pivot_table(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot_table(index="d", columns="symbol", values="open").sort_index()
    dollar = (
        frame.assign(dv=frame["close"] * frame["volume"])
        .pivot_table(index="d", columns="symbol", values="dv")
        .sort_index()
    )
    for f in (close, open_, dollar):
        f.index = pd.to_datetime(f.index)
    return close, open_, dollar


def score_frame(close: pd.DataFrame, kind: str) -> pd.DataFrame:
    if kind == "blend":
        parts = [close.pct_change(n, fill_method=None) for n in (21, 63, 126, 252)]
        return sum(parts) / len(parts)
    if kind == "risk_adj":
        parts = [close.pct_change(n, fill_method=None) for n in (21, 63, 126, 252)]
        blend = sum(parts) / len(parts)
        vol = close.pct_change(fill_method=None).rolling(63, min_periods=40).std()
        return blend / vol.replace(0.0, np.nan)
    if kind == "r63":
        return close.pct_change(63, fill_method=None)
    if kind == "r252":
        return close.pct_change(252, fill_method=None)
    raise ValueError(kind)


ELIGIBLE_CACHE: dict = {}


def eligible_at(
    day: pd.Timestamp,
    close: pd.DataFrame,
    dollar: pd.DataFrame,
    levered: set[str],
    leverage_arm: str,
) -> list[str]:
    """Point-in-time candidate set: history and liquidity as of ``day`` only.

    Cached per (day, leverage arm) because it does not depend on the score, the
    holding count, the weighting or the rebalance schedule."""
    cache_key = (day, leverage_arm)
    hit = ELIGIBLE_CACHE.get(cache_key)
    if hit is not None:
        return hit
    upto = close.loc[:day]
    if len(upto) < MIN_HISTORY_SESSIONS:
        ELIGIBLE_CACHE[cache_key] = []
        return []
    history = upto.notna().sum(axis=0)
    adv = dollar.loc[:day].tail(ADV_WINDOW).mean(axis=0)
    ok = (history >= MIN_HISTORY_SESSIONS) & (adv >= MIN_DOLLAR_ADV)
    names = [s for s in close.columns[ok.reindex(close.columns).fillna(False)] if s != CASH]
    if leverage_arm == "exclude_levered":
        names = [s for s in names if s not in levered]
    ELIGIBLE_CACHE[cache_key] = names
    return names


def pick_with_corr_cap(
    ranked: list[str],
    returns: pd.DataFrame,
    day: pd.Timestamp,
    top_n: int,
    *,
    corr_cache: dict | None = None,
) -> list[str]:
    """Greedy top-``top_n`` pick that skips a candidate too correlated with one
    already held. One correlation matrix over the top ``CORR_PREFILTER``
    candidates, cached per (day, candidate set), instead of pairwise
    recomputation per cell."""
    shortlist = ranked[:CORR_PREFILTER]
    if len(shortlist) <= 1:
        return shortlist[:top_n]
    key = (day, tuple(shortlist))
    corr = None if corr_cache is None else corr_cache.get(key)
    if corr is None:
        window = returns.loc[:day].tail(CORR_WINDOW)
        corr = window[shortlist].corr(min_periods=60)
        if corr_cache is not None:
            if len(corr_cache) > 512:
                corr_cache.clear()
            corr_cache[key] = corr
    chosen: list[str] = []
    for symbol in shortlist:
        if len(chosen) >= top_n:
            break
        if chosen:
            pair_corrs = corr.loc[symbol, chosen]
            if bool((pair_corrs > MAX_PAIR_CORR).any()):
                continue
        chosen.append(symbol)
    return chosen


def run_cell(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    dollar: pd.DataFrame,
    returns: pd.DataFrame,
    scores: pd.DataFrame,
    levered: set[str],
    *,
    leverage_arm: str,
    top_n: int,
    rebal: str,
    weighting: str,
    cost_bps: float,
    rng: np.random.Generator | None = None,
) -> tuple[pd.Series, pd.Series, dict]:
    flags = BASE.rebalance_flags(close.index, rebal)
    signal_dates = list(close.index[flags])
    cash_score = scores[CASH]
    vol = returns.rolling(63, min_periods=40).std()
    books: dict[pd.Timestamp, dict[str, float]] = {}
    sizes: list[int] = []
    corr_cache = CORR_CACHE
    for day in signal_dates:
        names = eligible_at(day, close, dollar, levered, leverage_arm)
        sizes.append(len(names))
        row = scores.loc[day, names].dropna() if names else pd.Series(dtype=float)
        if row.empty:
            books[day] = {CASH: 1.0}
            continue
        if rng is not None:
            order = list(rng.permutation(list(row.index)))
        else:
            order = list(row.sort_values(ascending=False).index)
        chosen = pick_with_corr_cap(order, returns, day, top_n, corr_cache=corr_cache)
        cs = cash_score.loc[day]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        if not chosen:
            books[day] = {CASH: 1.0}
            continue
        if weighting == "inverse_vol":
            inv = {}
            for s in chosen:
                v = vol.loc[day, s]
                inv[s] = 1.0 / v if v and v == v and v > 0 else np.nan
            if all(x != x for x in inv.values()):
                weights = {s: 1.0 / len(chosen) for s in chosen}
            else:
                total = sum(x for x in inv.values() if x == x)
                weights = {s: (inv[s] / total if inv[s] == inv[s] else 0.0) for s in chosen}
                residual = 1.0 - sum(weights.values())
                if residual > 1e-9:
                    weights[CASH] = residual
        else:
            weights = {s: 1.0 / len(chosen) for s in chosen}
        books[day] = weights
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
    info = {
        "rebalances": len(signal_dates),
        "universe_min": int(min(sizes)) if sizes else 0,
        "universe_median": int(np.median(sizes)) if sizes else 0,
        "universe_max": int(max(sizes)) if sizes else 0,
    }
    return ret, turnover, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=PLACEBO_SEEDS)
    ap.add_argument("--placebo-top", type=int, default=8)
    ap.add_argument(
        "--placebo-only",
        action="store_true",
        help=(
            "skip the grid and load the cells.parquet an earlier run wrote, then run "
            "only the placebo pass. The grid takes about an hour and the placebo pass "
            "several, so the two have to be separable around the nightly paper window."
        ),
    )
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    funds = load_fund_names()
    levered = set(funds.loc[funds["is_levered"], "symbol"])
    symbols = sorted(set(funds["symbol"]) | {CASH, RF, "SPY", "SPMO", "QQQ"})
    print(f"fund-classified symbols in metadata: {len(funds)} (levered/inverse {len(levered)})")

    grid: list[dict] = []
    for score in GRID_SCORES:
        for arm in GRID_LEVERAGE:
            for top_n in GRID_TOPN:
                for rebal in GRID_REBAL:
                    for weighting in GRID_WEIGHTING:
                        grid.append(
                            {
                                "cell_id": f"pool_{score}_{arm}_top{top_n}_{rebal}_{weighting}",
                                "family": f"{score}|{arm}",
                                "score": score,
                                "leverage_arm": arm,
                                "top_n": top_n,
                                "rebalance": rebal,
                                "weighting": weighting,
                            }
                        )
    manifest = {
        "card_id": "H-20260918-06",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "windows": BASE.WINDOWS,
        "pit_universe_rule": {
            "classifier": "asset_metadata.is_probable_fund_or_etf",
            "min_history_sessions": MIN_HISTORY_SESSIONS,
            "min_dollar_adv": MIN_DOLLAR_ADV,
            "adv_window": ADV_WINDOW,
        },
        "max_pair_corr": MAX_PAIR_CORR,
        "corr_window": CORR_WINDOW,
        "cost_bps_primary": COST_BPS_PRIMARY,
        "cost_bps_stress": COST_BPS_STRESS,
        "cells": grid,
        "cell_count": len(grid),
        "family_count": len({c["family"] for c in grid}),
        "selection_rule": (
            "highest selection-window Sharpe within each (score, leverage) family; "
            "the holdout window is never used to rank and is reported as the "
            "out-of-sample estimate for whatever the selection window picked"
        ),
        "placebo_seeds": args.seeds,
    }
    (OUT_DIR / "candidate-manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(f"preregistered {len(grid)} cells in {manifest['family_count']} families")

    reuse_cells = bool(args.placebo_only) and (OUT_DIR / "cells.parquet").is_file()
    if args.placebo_only and not reuse_cells:
        raise SystemExit("--placebo-only needs a cells.parquet from an earlier grid run")

    close, open_, dollar = load_panel(symbols)
    print(
        f"panel {close.shape[0]} sessions x {close.shape[1]} symbols "
        f"{close.index[0].date()}..{close.index[-1].date()}"
    )
    returns = close.pct_change(fill_method=None)
    rf = close[RF].pct_change(fill_method=None).fillna(0.0)

    # section 0: survivorship -- report what this probe CAN and CANNOT see.
    liq_2023 = dollar.loc["2023-01-01":"2023-06-30"].mean(axis=0)
    was_liquid = set(liq_2023.loc[liq_2023 >= MIN_DOLLAR_ADV].index)
    last_seen = close.apply(lambda col: col.last_valid_index())
    gone = sorted(
        s
        for s in close.columns
        if last_seen.get(s) is not None and pd.Timestamp(last_seen[s]) < pd.Timestamp("2026-09-01")
    )
    detectable = len(gone) > 0
    survivorship = {
        "liquid_in_h1_2023": len(was_liquid),
        "panel_symbols": int(close.shape[1]),
        "panel_symbols_gone_before_2026_09": len(gone),
        "attrition_detectable": detectable,
        "caveat": (
            "The symbol list comes from cached Alpaca asset metadata, which contains "
            "only currently-active assets: Alpaca's assets API does not return "
            "delisted symbols. When panel_symbols_gone_before_2026_09 is 0 the probe "
            "has detected nothing because it CANNOT detect anything, not because no "
            "fund closed. Hundreds of US funds close every year. The bias is real and "
            "unquantified here. data/sip-delisted/by_year holds 4,833 dead symbols but "
            "they are stocks, so it gives no delisted-fund coverage. What bounds the "
            "bias: a long-only top-K pick with a liquidity floor only suffers if it "
            "would have HELD the missing fund, and a fund heading for closure sits at "
            "the bottom of this ranking. The exception is the levered arm, where a "
            "fund can be a top-K momentum pick and then close after a crash."
        ),
        "examples": gone[:25],
    }
    if detectable:
        print(
            f"survivorship probe: {len(gone)} of {close.shape[1]} panel symbols stopped "
            "trading before 2026-09"
        )
    else:
        print(
            "survivorship probe: CANNOT DETECT ATTRITION -- 0 of "
            f"{close.shape[1]} panel symbols have a last trading day before 2026-09, "
            "which means the metadata holds only active assets. Treat the levered arm "
            "as carrying unmeasured survivorship risk."
        )

    score_cache = {kind: score_frame(close, kind) for kind in GRID_SCORES}
    rows: list[dict] = []
    series: dict[str, pd.Series] = {}
    infos: dict[str, dict] = {}
    grid_iter: list[dict] = [] if reuse_cells else grid
    if reuse_cells:
        print("reusing cells.parquet from the earlier grid run; placebo pass only")
    for n, spec in enumerate(grid_iter, 1):
        for tag, cost in (("net10", COST_BPS_PRIMARY), ("net20", COST_BPS_STRESS)):
            ret, tv, info = run_cell(
                close,
                open_,
                dollar,
                returns,
                score_cache[spec["score"]],
                levered,
                leverage_arm=spec["leverage_arm"],
                top_n=spec["top_n"],
                rebal=spec["rebalance"],
                weighting=spec["weighting"],
                cost_bps=cost,
            )
            wm = BASE.window_metrics(ret, rf, tv)
            row = {"cell_id": spec["cell_id"], "family": spec["family"], "cost": tag}
            for wname, m in wm.items():
                for k, v in asdict(m).items():
                    row[f"{wname}_{k}"] = v
            rows.append(row)
            if tag == "net10":
                series[spec["cell_id"]] = ret
                infos[spec["cell_id"]] = info
        if n % 12 == 0:
            print(f"  {n}/{len(grid)} cells done")

    for bench in ("SPY", "SPMO", "QQQ"):
        ret, tv = BASE.buy_hold(close, open_, bench)
        wm = BASE.window_metrics(ret, rf, tv)
        row = {"cell_id": f"bench_{bench}", "family": "benchmark", "cost": "net0"}
        for wname, m in wm.items():
            for k, v in asdict(m).items():
                row[f"{wname}_{k}"] = v
        rows.append(row)
    if reuse_cells:
        table = pd.read_parquet(OUT_DIR / "cells.parquet")
    else:
        table = pd.DataFrame(rows)
        table.to_parquet(OUT_DIR / "cells.parquet", index=False)

    primary = table.loc[table["cost"] == "net10"]
    ranked = primary.loc[primary["family"] != "benchmark"].sort_values(
        "select_sharpe", ascending=False
    )
    family_picks = ranked.sort_values("select_sharpe", ascending=False).groupby("family").head(1)

    placebo_path = OUT_DIR / "placebo.parquet"
    placebo_rows: list[dict] = []
    done_cells: set[str] = set()
    if placebo_path.is_file():
        prior = pd.read_parquet(placebo_path)
        placebo_rows = prior.to_dict("records")
        counts = prior.groupby("cell_id")["seed"].nunique()
        done_cells = set(counts.loc[counts >= args.seeds].index)
        if done_cells:
            print(f"resuming placebos; {len(done_cells)} cell(s) already at {args.seeds} seeds")
    targets = list(
        dict.fromkeys(
            list(family_picks["cell_id"]) + list(ranked["cell_id"].head(args.placebo_top))
        )
    )
    for cell_id in targets:
        if cell_id in done_cells:
            print(f"  placebo cached: {cell_id}")
            continue
        spec = next(g for g in grid if g["cell_id"] == cell_id)
        for seed in range(args.seeds):
            rng = np.random.default_rng(seed)
            pret, ptv, _ = run_cell(
                close,
                open_,
                dollar,
                returns,
                score_cache[spec["score"]],
                levered,
                leverage_arm=spec["leverage_arm"],
                top_n=spec["top_n"],
                rebal=spec["rebalance"],
                weighting=spec["weighting"],
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
        # write after every cell: this pass takes hours and is stopped before the
        # nightly paper window, so progress has to survive a kill
        pd.DataFrame(placebo_rows).to_parquet(placebo_path, index=False)
        print(f"  placebo done: {cell_id}")
    placebo = pd.DataFrame(placebo_rows)
    if not placebo.empty:
        placebo.to_parquet(placebo_path, index=False)

    summary: dict = {
        "card_id": "H-20260918-06",
        "cell_count": len(grid),
        "windows": BASE.WINDOWS,
        "survivorship_probe": survivorship,
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
    for _, r in family_picks.iterrows():
        cid = r["cell_id"]
        stress = table.loc[(table["cell_id"] == cid) & (table["cost"] == "net20")].iloc[0]
        pb = placebo.loc[placebo["cell_id"] == cid]
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
            "stress20_holdout_sharpe": stress["holdout_sharpe"],
            "universe": infos.get(cid, {}),
        }
        if not pb.empty:
            entry["placebo_holdout_median"] = float(pb["holdout_sharpe"].median())
            entry["placebo_holdout_p90"] = float(pb["holdout_sharpe"].quantile(0.90))
            entry["placebo_holdout_beat_frac"] = float(
                (pb["holdout_sharpe"] >= r["holdout_sharpe"]).mean()
            )
            entry["placebo_select_beat_frac"] = float(
                (pb["select_sharpe"] >= r["select_sharpe"]).mean()
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
