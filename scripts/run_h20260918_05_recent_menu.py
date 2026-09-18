"""H-20260918-05: recent-window ETF menu -- rotation and leveraged-trend cells.

User acceptance bar (2026-09-18, verbatim intent): the strategy only has to work
on the *recent* market, a bad 2016-2020 is acceptable because regimes change;
what matters is high return AND high Sharpe, and at least two or three cells go
on the Alpaca paper account today.

So this runner deliberately drops the multi-year robustness requirement and
replaces it with a single honest guard: a selection window and a completely
untouched recent holdout.

    warmup      2022-06-01 .. 2023-09-15   (lookbacks only, never scored)
    selection   2023-09-18 .. 2025-12-31   (cells are ranked here)
    holdout     2026-01-02 .. 2026-09-17   (out-of-sample, never used to rank)
    anchor      2024-01-08 .. 2026-09-16   (the window the SPMO benchmark quotes)

Preregistration: the whole grid is enumerated in GRID_* below and written to
candidate-manifest.json before any metric is computed; ranking uses the
selection window only, and the holdout number is reported as the out-of-sample
estimate for whatever the selection window picked. Placebos are run for the
per-family winners:

  * rotation cells  -- random-pick placebo: same menu, same rebalance calendar,
    same number of holdings, random assets (N seeds). A real ranking edge has to
    beat the 95th percentile of that.
  * trend cells     -- random-calendar-shift placebo: the SMA gate is shifted by
    a random 1..20 session offset (N seeds). This is the control that killed the
    momentum trend gate in L-20260918-01.

Costs: sum(|delta w|) * slippage_bps, charged on the execution session, at 10 bp
primary and 20 bp stress. Fills are next-session open (matching the live paper
path's fill_assumption). Prices are the SIP archive's fully adjusted closes
(verified: SPY 2016-01-04 = 171.10 vs ~201 unadjusted, so dividends are in).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260918_05_recent_menu"
DAILY_GLOB = "data/sip/daily/*/*.parquet"

WARMUP_START = "2022-06-01"
SELECT_START = "2023-09-18"
SELECT_END = "2025-12-31"
HOLD_START = "2026-01-02"
HOLD_END = "2026-09-17"
ANCHOR_START = "2024-01-08"
ANCHOR_END = "2026-09-16"

CASH = "SHY"
RF = "BIL"

MENUS: dict[str, list[str]] = {
    "A1_global": ["SPY", "QQQ", "EFA", "EEM", "TLT", "GLD", "IEF"],
    "A2_sector": ["XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"],
    "A3_growth": ["SPMO", "QQQ", "SMH", "XLK", "GLD", "TLT"],
    "A4_levered": ["TQQQ", "SOXL", "UPRO", "USD", "TECL"],
}
GRID_LOOKBACKS: list[str] = ["63", "126", "252", "blend"]
GRID_TOPN: list[int] = [1, 2]
GRID_REBAL: list[str] = ["monthly", "weekly"]

TREND_ASSETS: dict[str, str] = {
    "TQQQ": "QQQ",
    "SOXL": "SMH",
    "UPRO": "SPY",
    "USD": "SMH",
    "TECL": "XLK",
}
GRID_SMA: list[int] = [20, 50, 100, 200]
GRID_GATE_ON: list[str] = ["underlying", "self"]

BENCHMARKS = ["SPY", "SPMO", "QQQ", "TQQQ"]
PLACEBO_SEEDS = 40
COST_BPS_PRIMARY = 10.0
COST_BPS_STRESS = 20.0


def all_symbols() -> list[str]:
    out = {CASH, RF}
    for menu in MENUS.values():
        out.update(menu)
    out.update(TREND_ASSETS)
    out.update(TREND_ASSETS.values())
    out.update(BENCHMARKS)
    return sorted(out)


def load_panel(symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='700MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('{DAILY_GLOB}')
        WHERE symbol IN ({in_list}) AND timestamp::DATE >= DATE '{WARMUP_START}'
              AND timestamp::DATE <= DATE '{HOLD_END}'
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    # price hygiene: drop vendor ghost bars (zero volume and zero trades)
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    return close, open_


def rebalance_flags(index: pd.DatetimeIndex, rebal: str) -> pd.Series:
    if rebal == "monthly":
        key = index.to_period("M")
    elif rebal == "weekly":
        key = index.to_period("W")
    else:  # pragma: no cover - guarded by the grid
        raise ValueError(rebal)
    frame = pd.Series(index, index=index)
    last = frame.groupby(key).transform("max")
    return frame == last


def momentum_score(close: pd.DataFrame, lookback: str) -> pd.DataFrame:
    if lookback == "blend":
        parts = [close.pct_change(n, fill_method=None) for n in (21, 63, 126, 252)]
        return sum(parts) / len(parts)
    return close.pct_change(int(lookback), fill_method=None)


def weights_from_selection(
    index: pd.DatetimeIndex,
    signal_dates: list[pd.Timestamp],
    picks: dict[pd.Timestamp, list[str]],
    columns: list[str],
) -> pd.DataFrame:
    """Weights effective at the OPEN of the session after each signal date."""
    w = pd.DataFrame(0.0, index=index, columns=columns)
    pos = {d: i for i, d in enumerate(index)}
    current: dict[str, float] = {CASH: 1.0}
    rows: list[dict[str, float]] = []
    next_change: dict[int, dict[str, float]] = {}
    for d in signal_dates:
        i = pos[d]
        if i + 1 >= len(index):
            continue
        chosen = picks.get(d, [])
        if not chosen:
            book = {CASH: 1.0}
        else:
            book = {s: 1.0 / len(chosen) for s in chosen}
        next_change[i + 1] = book
    for i in range(len(index)):
        if i in next_change:
            current = next_change[i]
        rows.append(dict(current))
    w = pd.DataFrame(rows, index=index).reindex(columns=columns).fillna(0.0)
    return w


def portfolio_returns(
    weights: pd.DataFrame, close: pd.DataFrame, open_: pd.DataFrame, cost_bps: float
) -> pd.Series:
    cols = weights.columns
    c = close[cols]
    o = open_[cols]
    prev_c = c.shift(1)
    leg_open = (o / prev_c - 1.0).fillna(0.0)
    leg_close = (c / o - 1.0).fillna(0.0)
    w_prev = weights.shift(1).fillna(0.0)
    gross = (w_prev * leg_open).sum(axis=1) + (weights * leg_close).sum(axis=1)
    turnover = (weights - w_prev).abs().sum(axis=1)
    return gross - turnover * cost_bps / 10_000.0


@dataclass
class Metrics:
    days: int
    cagr: float
    vol: float
    sharpe: float
    max_dd: float
    turnover_yr: float
    hit_month: float


def metrics(ret: pd.Series, rf: pd.Series, turnover: pd.Series) -> Metrics:
    ret = ret.dropna()
    if ret.empty:
        return Metrics(0, float("nan"), float("nan"), float("nan"), float("nan"), 0.0, float("nan"))
    n = len(ret)
    equity = (1.0 + ret).cumprod()
    years = n / 252.0
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else float("nan")
    vol = float(ret.std(ddof=1) * np.sqrt(252.0))
    excess = ret - rf.reindex(ret.index).fillna(0.0)
    sd = float(excess.std(ddof=1))
    sharpe = float(excess.mean() / sd * np.sqrt(252.0)) if sd > 0 else float("nan")
    dd = float((equity / equity.cummax() - 1.0).min())
    tv = float(turnover.reindex(ret.index).fillna(0.0).sum() / years) if years > 0 else 0.0
    monthly = (1.0 + ret).groupby(ret.index.to_period("M")).prod() - 1.0
    hit = float((monthly > 0).mean()) if len(monthly) else float("nan")
    return Metrics(n, cagr, vol, sharpe, dd, tv, hit)


WINDOWS = {
    "select": (SELECT_START, SELECT_END),
    "holdout": (HOLD_START, HOLD_END),
    "anchor": (ANCHOR_START, ANCHOR_END),
}


def window_metrics(ret: pd.Series, rf: pd.Series, turnover: pd.Series) -> dict[str, Metrics]:
    out = {}
    for name, (a, b) in WINDOWS.items():
        mask = (ret.index >= a) & (ret.index <= b)
        out[name] = metrics(ret.loc[mask], rf, turnover.loc[mask])
    return out


def rotation_cell(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    menu_key: str,
    lookback: str,
    top_n: int,
    rebal: str,
    cost_bps: float,
    *,
    rng: np.random.Generator | None = None,
) -> tuple[pd.Series, pd.Series]:
    menu = [s for s in MENUS[menu_key] if s in close.columns]
    cols = sorted(set(menu + [CASH]))
    score = momentum_score(close, lookback)
    cash_score = score[CASH]
    flags = rebalance_flags(close.index, rebal)
    signal_dates = list(close.index[flags])
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in signal_dates:
        row = score.loc[d, menu].dropna()
        if row.empty:
            continue
        if rng is not None:
            avail = list(row.index)
            k = min(top_n, len(avail))
            chosen = list(rng.choice(avail, size=k, replace=False))
        else:
            chosen = list(row.sort_values(ascending=False).index[:top_n])
        # absolute-momentum filter: an asset must beat cash over the same lookback
        cs = cash_score.loc[d]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        picks[d] = chosen
    w = weights_from_selection(close.index, signal_dates, picks, cols)
    ret = portfolio_returns(w, close, open_, cost_bps)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    return ret, turnover


def trend_cell(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    asset: str,
    sma: int,
    gate_on: str,
    cost_bps: float,
    *,
    shift: int = 0,
) -> tuple[pd.Series, pd.Series]:
    gate_sym = asset if gate_on == "self" else TREND_ASSETS[asset]
    px = close[gate_sym]
    ma = px.rolling(sma, min_periods=sma).mean()
    on = (px > ma).astype(float)
    if shift:
        on = on.shift(shift)
    on = on.fillna(0.0)
    cols = sorted({asset, CASH})
    w = pd.DataFrame(0.0, index=close.index, columns=cols)
    # signal on close of t, effective at the open of t+1
    eff = on.shift(1).fillna(0.0)
    w[asset] = eff
    w[CASH] = 1.0 - eff
    ret = portfolio_returns(w, close, open_, cost_bps)
    turnover = (w - w.shift(1).fillna(0.0)).abs().sum(axis=1)
    return ret, turnover


def buy_hold(close: pd.DataFrame, open_: pd.DataFrame, symbol: str) -> tuple[pd.Series, pd.Series]:
    cols = [symbol]
    w = pd.DataFrame(1.0, index=close.index, columns=cols)
    ret = portfolio_returns(w, close, open_, 0.0)
    return ret, pd.Series(0.0, index=close.index)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=PLACEBO_SEEDS)
    ap.add_argument("--placebo-top", type=int, default=6)
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    syms = all_symbols()
    grid: list[dict] = []
    for menu_key in MENUS:
        for lb in GRID_LOOKBACKS:
            for tn in GRID_TOPN:
                for rb in GRID_REBAL:
                    grid.append(
                        {
                            "family": "rotation",
                            "cell_id": f"rot_{menu_key}_lb{lb}_top{tn}_{rb}",
                            "menu": menu_key,
                            "lookback": lb,
                            "top_n": tn,
                            "rebalance": rb,
                        }
                    )
    for asset, under in TREND_ASSETS.items():
        for sma in GRID_SMA:
            for gate in GRID_GATE_ON:
                grid.append(
                    {
                        "family": "trend",
                        "cell_id": f"trd_{asset}_sma{sma}_{gate}",
                        "asset": asset,
                        "underlying": under,
                        "sma": sma,
                        "gate_on": gate,
                    }
                )
    manifest = {
        "card_id": "H-20260918-05",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "windows": WINDOWS,
        "cost_bps_primary": COST_BPS_PRIMARY,
        "cost_bps_stress": COST_BPS_STRESS,
        "cells": grid,
        "cell_count": len(grid),
        "symbols": syms,
        "placebo_seeds": args.seeds,
    }
    (OUT_DIR / "candidate-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"preregistered {len(grid)} cells over {len(syms)} symbols")

    close, open_ = load_panel(syms)
    print(
        f"panel {close.shape[0]} sessions x {close.shape[1]} symbols "
        f"{close.index[0].date()}..{close.index[-1].date()}"
    )
    rf = close[RF].pct_change(fill_method=None).fillna(0.0)

    rows: list[dict] = []
    series: dict[str, pd.Series] = {}
    for spec in grid:
        for cost_tag, cost in (("net10", COST_BPS_PRIMARY), ("net20", COST_BPS_STRESS)):
            if spec["family"] == "rotation":
                ret, tv = rotation_cell(
                    close,
                    open_,
                    spec["menu"],
                    spec["lookback"],
                    spec["top_n"],
                    spec["rebalance"],
                    cost,
                )
            else:
                ret, tv = trend_cell(
                    close, open_, spec["asset"], spec["sma"], spec["gate_on"], cost
                )
            wm = window_metrics(ret, rf, tv)
            row = {"cell_id": spec["cell_id"], "family": spec["family"], "cost": cost_tag}
            for wname, m in wm.items():
                for k, v in asdict(m).items():
                    row[f"{wname}_{k}"] = v
            rows.append(row)
            if cost_tag == "net10":
                series[spec["cell_id"]] = ret
    for bench in BENCHMARKS:
        ret, tv = buy_hold(close, open_, bench)
        wm = window_metrics(ret, rf, tv)
        row = {"cell_id": f"bench_{bench}", "family": "benchmark", "cost": "net0"}
        for wname, m in wm.items():
            for k, v in asdict(m).items():
                row[f"{wname}_{k}"] = v
        rows.append(row)
        series[f"bench_{bench}"] = ret
    table = pd.DataFrame(rows)
    table.to_parquet(OUT_DIR / "cells.parquet", index=False)

    primary = table.loc[table["cost"] == "net10"].copy()
    ranked = primary.loc[primary["family"] != "benchmark"].sort_values(
        "select_sharpe", ascending=False
    )
    # placebos for the top cells of each family, ranked on the SELECTION window only
    placebo_rows: list[dict] = []
    for family in ("rotation", "trend"):
        fam = ranked.loc[ranked["family"] == family].head(args.placebo_top)
        for cell_id in fam["cell_id"]:
            spec = next(g for g in grid if g["cell_id"] == cell_id)
            for seed in range(args.seeds):
                rng = np.random.default_rng(seed)
                if family == "rotation":
                    pret, ptv = rotation_cell(
                        close,
                        open_,
                        spec["menu"],
                        spec["lookback"],
                        spec["top_n"],
                        spec["rebalance"],
                        COST_BPS_PRIMARY,
                        rng=rng,
                    )
                else:
                    shift = int(rng.integers(1, 21))
                    pret, ptv = trend_cell(
                        close,
                        open_,
                        spec["asset"],
                        spec["sma"],
                        spec["gate_on"],
                        COST_BPS_PRIMARY,
                        shift=shift,
                    )
                wm = window_metrics(pret, rf, ptv)
                placebo_rows.append(
                    {
                        "cell_id": cell_id,
                        "family": family,
                        "seed": seed,
                        "select_sharpe": wm["select"].sharpe,
                        "select_cagr": wm["select"].cagr,
                        "holdout_sharpe": wm["holdout"].sharpe,
                        "holdout_cagr": wm["holdout"].cagr,
                        "anchor_sharpe": wm["anchor"].sharpe,
                        "anchor_cagr": wm["anchor"].cagr,
                    }
                )
        print(f"placebo done for {family}: {len(fam)} cells x {args.seeds} seeds")
    placebo = pd.DataFrame(placebo_rows)
    placebo.to_parquet(OUT_DIR / "placebo.parquet", index=False)

    summary: dict = {"card_id": "H-20260918-05", "cell_count": len(grid), "windows": WINDOWS}
    top_rows = []
    for cell_id in ranked["cell_id"].head(20):
        r = primary.loc[primary["cell_id"] == cell_id].iloc[0]
        stress = table.loc[(table["cell_id"] == cell_id) & (table["cost"] == "net20")].iloc[0]
        pb = placebo.loc[placebo["cell_id"] == cell_id] if not placebo.empty else pd.DataFrame()
        entry = {
            "cell_id": cell_id,
            "family": r["family"],
            "select_sharpe": r["select_sharpe"],
            "select_cagr": r["select_cagr"],
            "select_max_dd": r["select_max_dd"],
            "holdout_sharpe": r["holdout_sharpe"],
            "holdout_cagr": r["holdout_cagr"],
            "holdout_max_dd": r["holdout_max_dd"],
            "anchor_sharpe": r["anchor_sharpe"],
            "anchor_cagr": r["anchor_cagr"],
            "anchor_max_dd": r["anchor_max_dd"],
            "turnover_yr": r["select_turnover_yr"],
            "stress20_holdout_sharpe": stress["holdout_sharpe"],
            "stress20_anchor_cagr": stress["anchor_cagr"],
        }
        if not pb.empty:
            entry["placebo_select_sharpe_p95"] = float(pb["select_sharpe"].quantile(0.95))
            entry["placebo_select_sharpe_median"] = float(pb["select_sharpe"].median())
            entry["placebo_beat_frac"] = float((pb["select_sharpe"] >= r["select_sharpe"]).mean())
            entry["placebo_holdout_sharpe_p95"] = float(pb["holdout_sharpe"].quantile(0.95))
            entry["placebo_holdout_beat_frac"] = float(
                (pb["holdout_sharpe"] >= r["holdout_sharpe"]).mean()
            )
        top_rows.append(entry)
    summary["top_by_select_sharpe"] = top_rows
    bench_rows = []
    for bench in BENCHMARKS:
        r = table.loc[table["cell_id"] == f"bench_{bench}"].iloc[0]
        bench_rows.append(
            {
                "cell_id": f"bench_{bench}",
                "select_sharpe": r["select_sharpe"],
                "select_cagr": r["select_cagr"],
                "holdout_sharpe": r["holdout_sharpe"],
                "holdout_cagr": r["holdout_cagr"],
                "anchor_sharpe": r["anchor_sharpe"],
                "anchor_cagr": r["anchor_cagr"],
                "anchor_max_dd": r["anchor_max_dd"],
            }
        )
    summary["benchmarks"] = bench_rows
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float))

    equity = pd.DataFrame({k: (1.0 + v).cumprod() for k, v in series.items()})
    equity.to_parquet(OUT_DIR / "equity.parquet")
    print(json.dumps(summary["benchmarks"], indent=2, default=float))
    print(json.dumps(top_rows[:8], indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
