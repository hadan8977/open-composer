"""B-4 / H-20260922-05: does the volatility-target mechanism transfer, and does a
dip boost lift the frozen S3-vt40 book to the return bar?

Two preregistered paths, one engine, nothing about the underlying sleeves
re-searched. Everything -- panel, four windows, 10/20 bp costs, next-open fills,
metric definitions, placebo design -- is inherited from
`scripts/run_h20260918_05_recent_menu.py`; the overlay machinery (down-only
volatility target read on the signal close and live at the next open, leverage
capped at 1.0 so weight can only move to SHY) is inherited from
`scripts/run_h20260922_02_s3_voltarget.py`, where it passed G1-G5 on S3.

Path A, mechanism transfer. The same overlay on the two unlevered live sleeves,
S1 (A2_sector, 252d, top 2, weekly) and S2 (A3_growth, blend, top 2, monthly).
A volatility target only binds when realized volatility exceeds it, so a target
is meaningless unless it is set relative to the book it runs on. Targets are
therefore frozen at 0.6x and 0.8x of each book's own median 21-session realized
volatility measured on the SELECTION window only (`--freeze-targets`, written
into candidate-manifest.json before any metric is computed). No return series
enters that choice.

Path B, dip boost. The frozen S3-vt40 cell, plus: while QQQ closes above its
200d SMA and Wilder RSI(10) on QQQ is below 30, the target is raised for a fixed
holding of sessions, then reverts. This is the one placebo-clean signal the
2026-09-22 giants sweep found (`f1_tqqq_rsi_no_hedge_ablation`, anchor 15.9% /
-5.2% / 1.37, calendar-shift placebo 0%), which failed only the return bar
because it sits in cash most of the time. Here it does not pick assets; it only
decides when the frozen sleeve may carry more of its own risk.

Placebos: random-pick (60 seeds) for path A, dip-signal calendar shift over all
20 offsets for path B. Gates G1-G5 as frozen in the strategy factory plan, plus
the path-specific transfer/boost criteria from the brief.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402

ITER_ID = "h20260922_05_salvage"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
MANIFEST = OUT_DIR / "candidate-manifest.json"
CASH = base.CASH
RF = base.RF
BENCHMARKS = ["SPY", "MTUM", "SPMO", "QQQ", "TQQQ"]

SLEEVES = {
    "s1": {"menu": "A2_sector", "lookback": "252", "rebal": "weekly", "top_n": 2},
    "s2": {"menu": "A3_growth", "lookback": "blend", "rebal": "monthly", "top_n": 2},
    "s3": {"menu": "A4_levered", "lookback": "63", "rebal": "monthly", "top_n": 2},
}
S3_FROZEN_TARGET = 0.40  # H-20260922-02 winner, not re-searched
TRANSFER_FRACTIONS = [0.6, 0.8]  # of each book's own select-window median vol
BOOST_TARGETS = [0.55, 0.60]
BOOST_HOLDS = [5, 10]
DIP_ASSET = "QQQ"
DIP_SMA = 200
DIP_RSI_WINDOW = 10
DIP_RSI_LEVEL = 30.0
VOL_WINDOW = 21

GATE_G1_CAGR, GATE_G1_MAXDD = 0.50, -0.35
GATE_G1ALT_SHARPE, GATE_G1ALT_CAGR = 2.0, 0.30
GATE_G2_SHARPE, GATE_G3_PLACEBO = 1.0, 0.10
TRANSFER_MIN_CAGR = 0.358  # SPMO anchor, H-20260918-05 section 3
BOOST_MIN_CAGR, BOOST_MAX_DD, BOOST_MIN_HOLDOUT_SHARPE = 1.10, -0.35, 2.0


def symbols() -> list[str]:
    out = {CASH, RF, DIP_ASSET, *BENCHMARKS}
    for cfg in SLEEVES.values():
        out.update(base.MENUS[cfg["menu"]])
    return sorted(out)


def wilder_rsi(series: pd.Series, window: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(avg_loss > 0, 100.0)


def dip_signal(close: pd.DataFrame) -> np.ndarray:
    px = close[DIP_ASSET]
    above = px > px.rolling(DIP_SMA).mean()
    oversold = wilder_rsi(px, DIP_RSI_WINDOW) < DIP_RSI_LEVEL
    return (above & oversold).fillna(False).to_numpy()


def boost_window(sig: np.ndarray, hold: int) -> np.ndarray:
    """Boost is live from the session after a firing close, for `hold` sessions."""
    n = len(sig)
    on = np.zeros(n, dtype=bool)
    for i in np.flatnonzero(sig):
        on[i + 1 : min(n, i + 1 + hold)] = True
    return on


def sleeve_weights(
    close: pd.DataFrame,
    key: str,
    *,
    rng: np.random.Generator | None = None,
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    cfg = SLEEVES[key]
    menu = [s for s in base.MENUS[cfg["menu"]] if s in close.columns]
    cols = sorted(set(menu + [CASH]))
    score = base.momentum_score(close, cfg["lookback"])
    cash_score = score[CASH]
    flags = base.rebalance_flags(close.index, cfg["rebal"])
    signal_dates = list(close.index[flags])
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in signal_dates:
        row = score.loc[d, menu].dropna()
        if row.empty:
            continue
        if rng is not None:
            chosen = list(
                rng.choice(list(row.index), size=min(cfg["top_n"], len(row)), replace=False)
            )
        else:
            chosen = list(row.sort_values(ascending=False).index[: cfg["top_n"]])
        cs = cash_score.loc[d]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        picks[d] = chosen
    return base.weights_from_selection(close.index, signal_dates, picks, cols), signal_dates


def legs(close: pd.DataFrame, open_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prev_c = close.shift(1)
    return (open_ / prev_c - 1.0).fillna(0.0), (close / open_ - 1.0).fillna(0.0)


def simulate(
    weights: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    scale: np.ndarray,
    cost_bps: float,
) -> tuple[pd.Series, pd.Series]:
    cols = list(weights.columns)
    cash_i = cols.index(CASH)
    wb = weights.to_numpy(dtype=float)
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    n = len(wb)
    rets = np.zeros(n)
    turns = np.zeros(n)
    w_prev = np.zeros(wb.shape[1])
    for i in range(n):
        m = scale[i]
        row = wb[i]
        risk = row.copy()
        risk[cash_i] = 0.0
        w = risk * m
        w[cash_i] = row[cash_i] + (1.0 - m) * risk.sum()
        gross = float(w_prev @ lo[i] + w @ lc[i])
        turnover = float(np.abs(w - w_prev).sum())
        rets[i] = gross - turnover * cost_bps / 10_000.0
        turns[i] = turnover
        w_prev = w
    return pd.Series(rets, index=weights.index), pd.Series(turns, index=weights.index)


def vol_scale(
    index: pd.DatetimeIndex,
    signal_dates: list[pd.Timestamp],
    book_returns: pd.Series,
    base_target: float | None,
    boost: np.ndarray | None = None,
    boost_target: float | None = None,
) -> np.ndarray:
    """Down-only exposure multiplier. Recomputed at the open after a rebalance
    close, and -- when a boost is supplied -- also at the open after the boost
    turns on or off. With boost=None this is exactly the H-20260922-02 schedule."""
    n = len(index)
    if base_target is None and boost is None:
        return np.ones(n)
    realized = (book_returns.rolling(VOL_WINDOW).std(ddof=1) * np.sqrt(252.0)).to_numpy()
    target = np.full(n, np.nan if base_target is None else base_target)
    if boost is not None and boost_target is not None:
        target = np.where(boost, boost_target, target)
    pos = {d: i for i, d in enumerate(index)}
    updates = {pos[d] + 1 for d in signal_dates if pos[d] + 1 < n}
    if boost is not None:
        changed = np.flatnonzero(np.diff(boost.astype(int)) != 0) + 1
        updates.update(int(i) for i in changed if i < n)
    sched = np.ones(n)
    current = 1.0
    for i in range(n):
        if i in updates:
            t = target[i]
            v = realized[i - 1] if i > 0 else np.nan
            if np.isnan(t):
                current = 1.0
            elif not np.isfinite(v) or v <= 0:
                current = 1.0
            else:
                current = min(1.0, float(t) / float(v))
        sched[i] = current
    return sched


def run_cell(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    key: str,
    target: float | None,
    cost_bps: float,
    *,
    rng: np.random.Generator | None = None,
    boost: np.ndarray | None = None,
    boost_target: float | None = None,
) -> tuple[pd.Series, pd.Series]:
    weights, signal_dates = sleeve_weights(close, key, rng=rng)
    gross, _ = simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    scale = vol_scale(close.index, signal_dates, gross, target, boost, boost_target)
    return simulate(weights, leg_open, leg_close, scale, cost_bps)


def book_vol_select(
    close: pd.DataFrame, leg_open: pd.DataFrame, leg_close: pd.DataFrame, key: str
) -> float:
    weights, _ = sleeve_weights(close, key)
    gross, _ = simulate(weights, leg_open, leg_close, np.ones(len(close.index)), 0.0)
    rv = gross.rolling(VOL_WINDOW).std(ddof=1) * np.sqrt(252.0)
    a, b = base.WINDOWS["select"]
    return float(rv.loc[(rv.index >= a) & (rv.index <= b)].median())


def flat(prefix: str, m: base.Metrics) -> dict:
    return {f"{prefix}_{k}": v for k, v in m.__dict__.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-targets", action="store_true")
    ap.add_argument("--pick-seeds", type=int, default=60)
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    close, open_ = base.load_panel(symbols())
    leg_open, leg_close = legs(close, open_)
    rf = (close[RF] / close[RF].shift(1) - 1.0).fillna(0.0)

    if args.freeze_targets:
        frozen = {
            "schema": 1,
            "iter_id": ITER_ID,
            "frozen_at": pd.Timestamp.utcnow().isoformat(),
            "rule": "targets = fraction x median 21-session realized vol of the unscaled book, "
            "selection window only; no return series enters this choice",
            "fractions": TRANSFER_FRACTIONS,
            "sleeves": {},
        }
        for key in ("s1", "s2", "s3"):
            v = book_vol_select(close, leg_open, leg_close, key)
            frozen["sleeves"][key] = {
                "select_median_realized_vol": round(v, 4),
                "targets": [round(f * v, 3) for f in TRANSFER_FRACTIONS]
                if key != "s3"
                else [S3_FROZEN_TARGET],
                **SLEEVES[key],
            }
        frozen["path_b"] = {
            "base_target": S3_FROZEN_TARGET,
            "boost_targets": BOOST_TARGETS,
            "holds": BOOST_HOLDS,
            "signal": (
                f"{DIP_ASSET} > SMA{DIP_SMA} and Wilder RSI({DIP_RSI_WINDOW}) < {DIP_RSI_LEVEL}"
            ),
        }
        MANIFEST.write_text(json.dumps(frozen, indent=2) + "\n")
        print(json.dumps(frozen["sleeves"], indent=2))
        return 0

    frozen = json.loads(MANIFEST.read_text())
    sig = dip_signal(close)
    print(f"dip signal fires on {int(sig.sum())} sessions", flush=True)

    rows: list[dict] = []

    def record(
        cell_id: str,
        path: str,
        params: dict,
        ret: pd.Series,
        turn: pd.Series,
        ret20: pd.Series,
        turn20: pd.Series,
    ) -> dict:
        wm = base.window_metrics(ret, rf, turn)
        wm20 = base.window_metrics(ret20, rf, turn20)
        row = {"cell_id": cell_id, "path": path, **params}
        for w in ("select", "holdout", "anchor"):
            row.update(flat(w, wm[w]))
            row[f"stress20_{w}_cagr"] = wm20[w].cagr
            row[f"stress20_{w}_sharpe"] = wm20[w].sharpe
            row[f"stress20_{w}_max_dd"] = wm20[w].max_dd
        rows.append(row)
        return row

    # --- baselines: the unscaled live books and the frozen S3-vt40 reference ---
    for key in ("s1", "s2", "s3"):
        r, t = run_cell(close, leg_open, leg_close, key, None, base.COST_BPS_PRIMARY)
        r20, t20 = run_cell(close, leg_open, leg_close, key, None, base.COST_BPS_STRESS)
        record(f"{key}_novt_baseline", "baseline", {"sleeve": key, "target": None}, r, t, r20, t20)
    r, t = run_cell(close, leg_open, leg_close, "s3", S3_FROZEN_TARGET, base.COST_BPS_PRIMARY)
    r20, t20 = run_cell(close, leg_open, leg_close, "s3", S3_FROZEN_TARGET, base.COST_BPS_STRESS)
    s3_vt40 = record(
        "s3_vt40_frozen", "baseline", {"sleeve": "s3", "target": S3_FROZEN_TARGET}, r, t, r20, t20
    )

    # --- path A: mechanism transfer to S1 and S2 ---
    for key in ("s1", "s2"):
        for target in frozen["sleeves"][key]["targets"]:
            r, t = run_cell(close, leg_open, leg_close, key, target, base.COST_BPS_PRIMARY)
            r20, t20 = run_cell(close, leg_open, leg_close, key, target, base.COST_BPS_STRESS)
            cid = f"{key}_vt{int(round(target * 100))}"
            row = record(cid, "A_transfer", {"sleeve": key, "target": target}, r, t, r20, t20)
            beat_s, beat_h = 0, 0
            for seed in range(args.pick_seeds):
                rng = np.random.default_rng(20260922 + seed)
                pr, pt = run_cell(
                    close, leg_open, leg_close, key, target, base.COST_BPS_PRIMARY, rng=rng
                )
                pm = base.window_metrics(pr, rf, pt)
                beat_s += pm["select"].sharpe > row["select_sharpe"]
                beat_h += pm["holdout"].sharpe > row["holdout_sharpe"]
            row["placebo_pick_beat_select"] = beat_s / args.pick_seeds
            row["placebo_pick_beat_holdout"] = beat_h / args.pick_seeds
            print(f"  {cid} done", flush=True)

    # --- path B: dip boost on the frozen S3-vt40 book ---
    for bt in BOOST_TARGETS:
        for hold in BOOST_HOLDS:
            on = boost_window(sig, hold)
            r, t = run_cell(
                close,
                leg_open,
                leg_close,
                "s3",
                S3_FROZEN_TARGET,
                base.COST_BPS_PRIMARY,
                boost=on,
                boost_target=bt,
            )
            r20, t20 = run_cell(
                close,
                leg_open,
                leg_close,
                "s3",
                S3_FROZEN_TARGET,
                base.COST_BPS_STRESS,
                boost=on,
                boost_target=bt,
            )
            cid = f"s3_vt40_boost{int(round(bt * 100))}_h{hold}"
            row = record(
                cid,
                "B_dip_boost",
                {
                    "sleeve": "s3",
                    "target": S3_FROZEN_TARGET,
                    "boost_target": bt,
                    "hold": hold,
                    "boost_days_anchor": int(on[(close.index >= base.WINDOWS["anchor"][0])].sum()),
                },
                r,
                t,
                r20,
                t20,
            )
            beat_c, beat_h = 0, 0
            for k in range(1, 21):
                shifted = np.zeros_like(sig)
                shifted[k:] = sig[:-k]
                pon = boost_window(shifted, hold)
                pr, pt = run_cell(
                    close,
                    leg_open,
                    leg_close,
                    "s3",
                    S3_FROZEN_TARGET,
                    base.COST_BPS_PRIMARY,
                    boost=pon,
                    boost_target=bt,
                )
                pm = base.window_metrics(pr, rf, pt)
                beat_c += pm["anchor"].cagr > row["anchor_cagr"]
                beat_h += pm["holdout"].sharpe > row["holdout_sharpe"]
            row["placebo_shift_beat_anchor_cagr"] = beat_c / 20.0
            row["placebo_shift_beat_holdout"] = beat_h / 20.0
            print(f"  {cid} done", flush=True)

    # --- benchmarks ---
    bench: list[dict] = []
    for sym in BENCHMARKS:
        br, bt_ = base.buy_hold(close, open_, sym)
        wm = base.window_metrics(br, rf, bt_)
        bench.append(
            {
                "cell_id": f"bench_{sym}",
                **{
                    f"{w}_{k}": v
                    for w in ("select", "holdout", "anchor")
                    for k, v in wm[w].__dict__.items()
                },
            }
        )

    df = pd.DataFrame(rows)
    # gates
    df["G1"] = (df.anchor_cagr >= GATE_G1_CAGR) & (df.anchor_max_dd >= GATE_G1_MAXDD)
    df["G1_alt"] = (df.anchor_sharpe >= GATE_G1ALT_SHARPE) & (df.anchor_cagr >= GATE_G1ALT_CAGR)
    df["G2"] = (df.holdout_sharpe >= GATE_G2_SHARPE) & (df.holdout_cagr > 0)
    worst = df[[c for c in df.columns if c.startswith("placebo_")]].max(axis=1)
    df["G3"] = worst.isna() | (worst <= GATE_G3_PLACEBO)
    df["G4"] = (
        (df.stress20_anchor_cagr >= GATE_G1_CAGR) & (df.stress20_anchor_max_dd >= GATE_G1_MAXDD)
    ) | (
        (df.stress20_anchor_sharpe >= GATE_G1ALT_SHARPE)
        & (df.stress20_anchor_cagr >= GATE_G1ALT_CAGR)
    )
    df["G5"] = True
    df["all_gates"] = df[["G1", "G2", "G3", "G4", "G5"]].all(axis=1) | (
        df[["G1_alt", "G2", "G3", "G4", "G5"]].all(axis=1)
    )
    # path-specific criteria
    basel = {
        r["params_sleeve"] if "params_sleeve" in r else r["sleeve"]: r
        for r in rows
        if r["path"] == "baseline" and r.get("target") is None
    }

    def tcrit(row):
        if row["path"] != "A_transfer":
            return np.nan
        b = basel[row["sleeve"]]
        return bool(
            row["anchor_sharpe"] > b["anchor_sharpe"]
            and row["anchor_max_dd"] > b["anchor_max_dd"]
            and row["anchor_cagr"] >= TRANSFER_MIN_CAGR
            and row["holdout_sharpe"] >= GATE_G2_SHARPE
            and row.get("placebo_pick_beat_holdout", 1.0) <= GATE_G3_PLACEBO
        )

    df["transfer_pass"] = df.apply(tcrit, axis=1)
    df["boost_pass"] = df.apply(
        lambda r: (
            np.nan
            if r["path"] != "B_dip_boost"
            else bool(
                r["anchor_cagr"] >= BOOST_MIN_CAGR
                and r["anchor_max_dd"] >= BOOST_MAX_DD
                and r["holdout_sharpe"] >= BOOST_MIN_HOLDOUT_SHARPE
                and max(
                    r.get("placebo_shift_beat_anchor_cagr", 1.0),
                    r.get("placebo_shift_beat_holdout", 1.0),
                )
                <= GATE_G3_PLACEBO
            )
        ),
        axis=1,
    )

    df.to_parquet(OUT_DIR / "cells.parquet")
    pd.DataFrame(bench).to_parquet(OUT_DIR / "benchmarks.parquet")
    summary = {
        "iter_id": ITER_ID,
        "card_id": "H-20260922-05",
        "cell_count": int(len(df)),
        "dip_signal_sessions": int(sig.sum()),
        "s3_vt40_reference": {
            "anchor_cagr": s3_vt40["anchor_cagr"],
            "anchor_max_dd": s3_vt40["anchor_max_dd"],
            "anchor_sharpe": s3_vt40["anchor_sharpe"],
            "holdout_sharpe": s3_vt40["holdout_sharpe"],
            "published": {"anchor_cagr": 0.983, "anchor_max_dd": -0.302, "anchor_sharpe": 1.66},
        },
        "frozen_targets": frozen["sleeves"],
        "cells": df.to_dict("records"),
        "benchmarks": bench,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    cols = [
        "cell_id",
        "path",
        "anchor_cagr",
        "anchor_max_dd",
        "anchor_sharpe",
        "holdout_sharpe",
        "placebo_pick_beat_holdout",
        "placebo_shift_beat_anchor_cagr",
        "all_gates",
        "transfer_pass",
        "boost_pass",
    ]
    print(df[[c for c in cols if c in df.columns]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
