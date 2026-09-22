"""H-20260922-04 / brief B-1: replicate the Composer RSI-extreme branch family.

Rule tree, exactly as the source strategy publishes it (see the snapshot in
reports/research/iterations/h20260922_04_rsi_branch/sources/):

    RSI(10) on the reference index > 80   -> hold the overheat asset (UVXY|BIL)
    RSI(10) < 30                          -> hold TQQQ (rebound bet)
    otherwise                             -> hold the single strongest 21-day
                                             performer of the menu

Windows, cost model, fill assumption and placebo machinery are imported
unchanged from scripts/run_h20260918_05_recent_menu.py, so this candidate is
measured on exactly the same ruler as the live S1/S2/S3 sleeves.

The 16-cell grid was frozen in candidate-manifest.json before this script read
a single price; `oc research direction-check` and
`oc research iteration validate` both passed first.
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

from run_h20260918_05_recent_menu import (  # noqa: E402
    COST_BPS_PRIMARY,
    COST_BPS_STRESS,
    RF,
    WINDOWS,
    load_panel,
    portfolio_returns,
    rebalance_flags,
    rotation_cell,
    weights_from_selection,
    window_metrics,
)

ROOT = Path(__file__).resolve().parents[1]
ITER_ID = "h20260922_04_rsi_branch"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
MANIFEST = OUT_DIR / "candidate-manifest.json"

MENUS = {
    "sector1x": ["XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"],
    "levered3x": ["TECL", "FAS", "ERX", "CURE", "DUSL"],
}
BENCH_BUY_HOLD = ["SPY", "MTUM", "SPMO", "QQQ", "TQQQ"]
S1_MENU = ["XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
CASH = "SHY"

SHIFT_SEEDS = 20
PICK_SEEDS = 60


def wilder_rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    # a window with no down days is maximally overbought
    return rsi.where(avg_loss.notna() & (avg_loss > 0), 100.0).where(avg_gain.notna())


def signal_dates(index: pd.DatetimeIndex, rebalance: str) -> list[pd.Timestamp]:
    if rebalance == "daily":
        return list(index)
    if rebalance == "friday":
        return list(index[rebalance_flags(index, "weekly")])
    raise ValueError(rebalance)


def branch_cell(
    close: pd.DataFrame,
    open_: pd.DataFrame,
    *,
    rsi_ref: str,
    rsi_window: int,
    overheat_threshold: float,
    overheat_asset: str,
    oversold_threshold: float,
    oversold_asset: str,
    menu: str,
    normal_lookback_days: int,
    rebalance: str,
    cost_bps: float,
    rsi_shift: int = 0,
    pick_rng: np.random.Generator | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (net returns, turnover, branch label per session)."""
    assets = [s for s in MENUS[menu] if s in close.columns]
    cols = sorted({*assets, overheat_asset, oversold_asset, CASH})
    rsi = wilder_rsi(close[rsi_ref], rsi_window)
    if rsi_shift:
        rsi = rsi.shift(rsi_shift)
    score = close[assets].pct_change(normal_lookback_days, fill_method=None)
    dates = signal_dates(close.index, rebalance)

    picks: dict[pd.Timestamp, list[str]] = {}
    branch_at: dict[pd.Timestamp, str] = {}
    for d in dates:
        value = rsi.loc[d]
        if pd.isna(value):
            picks[d] = [CASH]
            branch_at[d] = "warmup"
            continue
        if value > overheat_threshold:
            picks[d] = [overheat_asset]
            branch_at[d] = "overheat"
        elif value < oversold_threshold:
            picks[d] = [oversold_asset]
            branch_at[d] = "oversold"
        else:
            row = score.loc[d].dropna()
            if row.empty:
                picks[d] = [CASH]
                branch_at[d] = "warmup"
                continue
            if pick_rng is not None:
                picks[d] = [str(pick_rng.choice(list(row.index)))]
            else:
                picks[d] = [str(row.sort_values(ascending=False).index[0])]
            branch_at[d] = "normal"

    weights = weights_from_selection(close.index, dates, picks, cols)
    ret = portfolio_returns(weights, close, open_, cost_bps)
    turnover = (weights - weights.shift(1).fillna(0.0)).abs().sum(axis=1)

    # the branch decided on signal date d is the one the book is actually in
    # from the next session's open until the next signal date
    label = pd.Series("cash", index=close.index, dtype=object)
    pos = {d: i for i, d in enumerate(close.index)}
    current = "cash"
    changes: dict[int, str] = {}
    for d in dates:
        i = pos[d]
        if i + 1 < len(close.index):
            changes[i + 1] = branch_at[d]
    for i in range(len(close.index)):
        current = changes.get(i, current)
        label.iloc[i] = current
    return ret, turnover, label


def buy_hold(
    close: pd.DataFrame, open_: pd.DataFrame, symbols: list[str]
) -> tuple[pd.Series, pd.Series]:
    cols = [s for s in symbols if s in close.columns]
    weights = pd.DataFrame(1.0 / len(cols), index=close.index, columns=cols)
    ret = portfolio_returns(weights, close, open_, 0.0)
    return ret, pd.Series(0.0, index=close.index)


def equal_weight_menu(
    close: pd.DataFrame, open_: pd.DataFrame, menu: str, cost_bps: float
) -> tuple[pd.Series, pd.Series]:
    assets = [s for s in MENUS[menu] if s in close.columns]
    dates = signal_dates(close.index, "friday")
    picks = {d: assets for d in dates}
    weights = weights_from_selection(close.index, dates, picks, sorted({*assets, CASH}))
    ret = portfolio_returns(weights, close, open_, cost_bps)
    turnover = (weights - weights.shift(1).fillna(0.0)).abs().sum(axis=1)
    return ret, turnover


def window_slice(series: pd.Series, name: str) -> pd.Series:
    a, b = WINDOWS[name]
    return series.loc[(series.index >= a) & (series.index <= b)]


def vol_matched_excess(ret: pd.Series, bench: pd.Series, rf: pd.Series, name: str) -> float:
    """Annualized return of the strategy rescaled to the benchmark's vol, minus the benchmark."""
    r = window_slice(ret, name)
    b = window_slice(bench, name)
    rv, bv = r.std(ddof=1), b.std(ddof=1)
    if not rv or np.isnan(rv) or not bv:
        return float("nan")
    scaled = r * (bv / rv)
    years = len(r) / 252.0
    scaled_cagr = float((1.0 + scaled).prod() ** (1.0 / years) - 1.0)
    bench_cagr = float((1.0 + b).prod() ** (1.0 / years) - 1.0)
    return scaled_cagr - bench_cagr


def flatten(prefix: str, m) -> dict:
    return {f"{prefix}_{k}": v for k, v in asdict(m).items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shift-seeds", type=int, default=SHIFT_SEEDS)
    ap.add_argument("--pick-seeds", type=int, default=PICK_SEEDS)
    args = ap.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text())
    cells = manifest["candidates"]
    assert manifest["generated_before_backtest"] is True
    assert len(cells) == manifest["candidate_count"] == 16

    symbols = sorted(
        {CASH, RF, "UVXY", "TQQQ", "SPY", "QQQ", *BENCH_BUY_HOLD, *S1_MENU}
        | set(MENUS["sector1x"])
        | set(MENUS["levered3x"])
    )
    close, open_ = load_panel(symbols)
    print(
        f"panel {close.shape[0]} sessions x {close.shape[1]} symbols "
        f"{close.index[0].date()}..{close.index[-1].date()}"
    )
    rf = close[RF].pct_change(fill_method=None).fillna(0.0)
    spy_ret, _ = buy_hold(close, open_, ["SPY"])

    rows: list[dict] = []
    series: dict[str, pd.Series] = {}
    branch_diag: dict[str, dict] = {}

    for cell in cells:
        params = cell["parameters"]
        cid = cell["cell_id"]
        for tag, cost in (("net10", COST_BPS_PRIMARY), ("net20", COST_BPS_STRESS)):
            ret, turnover, label = branch_cell(
                close,
                open_,
                rsi_ref=params["rsi_ref"],
                rsi_window=params["rsi_window"],
                overheat_threshold=params["overheat_threshold"],
                overheat_asset=params["overheat_asset"],
                oversold_threshold=params["oversold_threshold"],
                oversold_asset=params["oversold_asset"],
                menu=params["menu"],
                normal_lookback_days=params["normal_lookback_days"],
                rebalance=params["rebalance"],
                cost_bps=cost,
            )
            wm = window_metrics(ret, rf, turnover)
            row = {
                "candidate_id": cell["candidate_id"],
                "cell_id": cid,
                "cost": tag,
                **{k: params[k] for k in ("rsi_ref", "overheat_asset", "menu", "rebalance")},
            }
            for wname, m in wm.items():
                row.update(flatten(wname, m))
            row["anchor_vol_matched_excess_vs_spy"] = vol_matched_excess(ret, spy_ret, rf, "anchor")
            rows.append(row)
            if tag == "net10":
                series[cid] = ret
                anchor = window_slice(ret, "anchor")
                lab = label.reindex(anchor.index)
                diag = {}
                for branch in ("overheat", "oversold", "normal", "cash", "warmup"):
                    mask = lab == branch
                    days = int(mask.sum())
                    contrib = float(anchor.loc[mask].sum()) if days else 0.0
                    diag[branch] = {
                        "anchor_days": days,
                        "anchor_sum_return": contrib,
                        "anchor_mean_daily": float(anchor.loc[mask].mean()) if days else 0.0,
                    }
                diag["anchor_total_sum_return"] = float(anchor.sum())
                branch_diag[cid] = diag

    # benchmarks on the same ruler
    for bench in BENCH_BUY_HOLD:
        ret, turnover = buy_hold(close, open_, [bench])
        wm = window_metrics(ret, rf, turnover)
        row = {"candidate_id": None, "cell_id": f"bench_{bench}", "cost": "net0"}
        for wname, m in wm.items():
            row.update(flatten(wname, m))
        row["anchor_vol_matched_excess_vs_spy"] = vol_matched_excess(ret, spy_ret, rf, "anchor")
        rows.append(row)
        series[f"bench_{bench}"] = ret
    for menu in MENUS:
        ret, turnover = equal_weight_menu(close, open_, menu, COST_BPS_PRIMARY)
        wm = window_metrics(ret, rf, turnover)
        row = {"candidate_id": None, "cell_id": f"bench_eqw_{menu}", "cost": "net10"}
        for wname, m in wm.items():
            row.update(flatten(wname, m))
        row["anchor_vol_matched_excess_vs_spy"] = vol_matched_excess(ret, spy_ret, rf, "anchor")
        rows.append(row)
        series[f"bench_eqw_{menu}"] = ret
    s1_ret, s1_tv = rotation_cell(close, open_, "A2_sector", "252", 2, "weekly", COST_BPS_PRIMARY)
    wm = window_metrics(s1_ret, rf, s1_tv)
    row = {"candidate_id": None, "cell_id": "bench_live_sleeve_S1", "cost": "net10"}
    for wname, m in wm.items():
        row.update(flatten(wname, m))
    row["anchor_vol_matched_excess_vs_spy"] = vol_matched_excess(s1_ret, spy_ret, rf, "anchor")
    rows.append(row)
    series["bench_live_sleeve_S1"] = s1_ret

    table = pd.DataFrame(rows)
    table.to_parquet(OUT_DIR / "cells.parquet", index=False)

    primary = table.loc[table["cost"] == "net10"].copy()
    real = primary.loc[primary["candidate_id"].notna()].copy()

    # placebos for the selection-window winner of each menu
    placebo_rows: list[dict] = []
    placebo_targets: list[str] = []
    for menu in MENUS:
        sub = real.loc[real["menu"] == menu].sort_values("select_sharpe", ascending=False)
        if not sub.empty:
            placebo_targets.append(str(sub.iloc[0]["cell_id"]))
    for cid in placebo_targets:
        cell = next(c for c in cells if c["cell_id"] == cid)
        params = cell["parameters"]
        base = dict(
            rsi_ref=params["rsi_ref"],
            rsi_window=params["rsi_window"],
            overheat_threshold=params["overheat_threshold"],
            overheat_asset=params["overheat_asset"],
            oversold_threshold=params["oversold_threshold"],
            oversold_asset=params["oversold_asset"],
            menu=params["menu"],
            normal_lookback_days=params["normal_lookback_days"],
            rebalance=params["rebalance"],
            cost_bps=COST_BPS_PRIMARY,
        )
        for seed in range(args.shift_seeds):
            rng = np.random.default_rng(10_000 + seed)
            shift = int(rng.integers(1, 21))
            pret, ptv, _ = branch_cell(close, open_, **base, rsi_shift=shift)
            wm = window_metrics(pret, rf, ptv)
            placebo_rows.append(
                {
                    "cell_id": cid,
                    "placebo": "rsi_calendar_shift",
                    "seed": seed,
                    "shift": shift,
                    **{f"{w}_sharpe": m.sharpe for w, m in wm.items()},
                    **{f"{w}_cagr": m.cagr for w, m in wm.items()},
                }
            )
        for seed in range(args.pick_seeds):
            rng = np.random.default_rng(20_000 + seed)
            pret, ptv, _ = branch_cell(close, open_, **base, pick_rng=rng)
            wm = window_metrics(pret, rf, ptv)
            placebo_rows.append(
                {
                    "cell_id": cid,
                    "placebo": "random_menu_pick",
                    "seed": seed,
                    "shift": 0,
                    **{f"{w}_sharpe": m.sharpe for w, m in wm.items()},
                    **{f"{w}_cagr": m.cagr for w, m in wm.items()},
                }
            )
        print(f"placebos done for {cid}")
    placebo = pd.DataFrame(placebo_rows)
    placebo.to_parquet(OUT_DIR / "placebo.parquet", index=False)

    def gate_block(cid: str) -> dict:
        r = primary.loc[primary["cell_id"] == cid].iloc[0]
        s = table.loc[(table["cell_id"] == cid) & (table["cost"] == "net20")]
        s = s.iloc[0] if len(s) else None
        g1 = bool(r["anchor_cagr"] >= 0.50 and r["anchor_max_dd"] >= -0.35)
        g1p = bool(r["anchor_sharpe"] >= 2.0 and r["anchor_cagr"] >= 0.30)
        g2 = bool(r["holdout_sharpe"] >= 1.0 and r["holdout_cagr"] > 0)
        entry = {
            "cell_id": cid,
            "select_sharpe": r["select_sharpe"],
            "select_cagr": r["select_cagr"],
            "holdout_sharpe": r["holdout_sharpe"],
            "holdout_cagr": r["holdout_cagr"],
            "anchor_sharpe": r["anchor_sharpe"],
            "anchor_cagr": r["anchor_cagr"],
            "anchor_max_dd": r["anchor_max_dd"],
            "anchor_vol": r["anchor_vol"],
            "anchor_turnover_yr": r["anchor_turnover_yr"],
            "anchor_vol_matched_excess_vs_spy": r["anchor_vol_matched_excess_vs_spy"],
            "G1_anchor_cagr_50_dd_35": g1,
            "G1p_sharpe_2_cagr_30": g1p,
            "G2_holdout": g2,
        }
        if s is not None:
            entry["stress20_anchor_cagr"] = s["anchor_cagr"]
            entry["stress20_anchor_sharpe"] = s["anchor_sharpe"]
            entry["stress20_anchor_max_dd"] = s["anchor_max_dd"]
            entry["stress20_holdout_sharpe"] = s["holdout_sharpe"]
            entry["G4_stress20"] = bool(
                (s["anchor_cagr"] >= 0.50 and s["anchor_max_dd"] >= -0.35)
                or (s["anchor_sharpe"] >= 2.0 and s["anchor_cagr"] >= 0.30)
            )
        pb = placebo.loc[placebo["cell_id"] == cid] if not placebo.empty else pd.DataFrame()
        if not pb.empty:
            for kind in ("rsi_calendar_shift", "random_menu_pick"):
                k = pb.loc[pb["placebo"] == kind]
                if k.empty:
                    continue
                for window in ("select", "holdout", "anchor"):
                    col = f"{window}_sharpe"
                    entry[f"placebo_{kind}_{window}_median"] = float(k[col].median())
                    entry[f"placebo_{kind}_{window}_p95"] = float(k[col].quantile(0.95))
                    entry[f"placebo_{kind}_{window}_beat_frac"] = float((k[col] >= r[col]).mean())
            beats = [
                entry.get(f"placebo_{kind}_holdout_beat_frac")
                for kind in ("rsi_calendar_shift", "random_menu_pick")
            ]
            beats = [b for b in beats if b is not None]
            if beats:
                entry["G3_placebo_holdout"] = bool(max(beats) <= 0.10)
                entry["placebo_worst_holdout_beat_frac"] = max(beats)
        entry["G5_executable"] = True
        entry["branch_diagnostics"] = branch_diag.get(cid)
        return entry

    ranked = real.sort_values("select_sharpe", ascending=False)
    summary = {
        "card_id": "H-20260922-04",
        "iter_id": ITER_ID,
        "brief": "reports/research/briefs/B-1-rsi-branch-rotation-2026-09-22.md",
        "cell_count": len(cells),
        "windows": WINDOWS,
        "cost_bps_primary": COST_BPS_PRIMARY,
        "cost_bps_stress": COST_BPS_STRESS,
        "candidate_manifest_sha256": manifest.get("candidate_manifest_sha256"),
        "placebo_targets": placebo_targets,
        "cells_by_select_sharpe": [gate_block(cid) for cid in ranked["cell_id"]],
        "benchmarks": [
            {
                "cell_id": r["cell_id"],
                "select_sharpe": r["select_sharpe"],
                "select_cagr": r["select_cagr"],
                "holdout_sharpe": r["holdout_sharpe"],
                "holdout_cagr": r["holdout_cagr"],
                "anchor_sharpe": r["anchor_sharpe"],
                "anchor_cagr": r["anchor_cagr"],
                "anchor_max_dd": r["anchor_max_dd"],
                "anchor_vol_matched_excess_vs_spy": r["anchor_vol_matched_excess_vs_spy"],
            }
            for _, r in table.loc[table["candidate_id"].isna()].iterrows()
        ],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    equity = pd.DataFrame({k: (1.0 + v).cumprod() for k, v in series.items()})
    equity.to_parquet(OUT_DIR / "equity.parquet")

    print(json.dumps(summary["benchmarks"], indent=2, default=float))
    print(json.dumps(summary["cells_by_select_sharpe"][:4], indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
