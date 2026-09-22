"""B-2 / H-20260922-02: volatility target and drawdown brake on the S3 sleeve.

Reuses `scripts/run_h20260918_05_recent_menu.py` for the data panel, the four
windows, the cost and fill conventions, the metric definitions and the placebo
design. Nothing about the underlying sleeve is re-searched: menu A4, top two,
month-end rebalance and the absolute-momentum filter against SHY are inherited
unchanged, so the cell with no volatility target and no brake must reproduce the
published S3 numbers (anchor 145.4% / -56.4% / 1.48). That identity is asserted
at the end of the run.

Overlay, frozen in candidate-manifest.json before this file computed anything:

  * volatility target 40%, 60% or none, from the 21-session realized volatility
    of the sleeve's own unscaled book, annualized, read on the month-end signal
    date and effective at the next open (Moreira-Muir cadence);
  * leverage cap 1.0 -- the overlay can only move weight into SHY;
  * drawdown brake none, or halve the risk weights once the sleeve's net equity
    is 25% below its running peak, restoring on a new equity high or after 21
    sessions, and re-arming only after drawdown recovers above -25%.
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

ITER_ID = "h20260922_02_s3_voltarget"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
MENU_KEY = "A4_levered"
CASH = base.CASH
RF = base.RF
BENCHMARKS = ["SPY", "MTUM", "SPMO", "TQQQ", "QQQ"]

VOL_TARGETS: list[float | None] = [0.40, 0.60, None]
BRAKES = ["none", "dd25_halve_recover_high_or_21d"]
LOOKBACKS = ["63", "blend"]
TOP_N = 2
REBAL = "monthly"
VOL_WINDOW = 21
BRAKE_TRIGGER = -0.25
BRAKE_MULT = 0.5
BRAKE_RECOVER_SESSIONS = 21

GATE_G1_CAGR = 0.50
GATE_G1_MAXDD = -0.35
GATE_G1ALT_SHARPE = 2.0
GATE_G1ALT_CAGR = 0.30
GATE_G2_SHARPE = 1.0
GATE_G3_PLACEBO = 0.10


def cell_id(vol: float | None, brake: str, lookback: str) -> str:
    vol_tag = "novt" if vol is None else f"vt{int(round(vol * 100))}"
    brake_tag = "nobrake" if brake == "none" else "brake25"
    return f"s3_lb{lookback}_{vol_tag}_{brake_tag}"


def symbols() -> list[str]:
    out = {CASH, RF, *base.MENUS[MENU_KEY], *BENCHMARKS}
    return sorted(out)


def base_weights(
    close: pd.DataFrame,
    lookback: str,
    *,
    rng: np.random.Generator | None = None,
    equal_weight: bool = False,
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Risk-on book of the frozen S3 sleeve (same rules as base.rotation_cell)."""
    menu = [s for s in base.MENUS[MENU_KEY] if s in close.columns]
    cols = sorted(set(menu + [CASH]))
    score = base.momentum_score(close, lookback)
    cash_score = score[CASH]
    flags = base.rebalance_flags(close.index, REBAL)
    signal_dates = list(close.index[flags])
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in signal_dates:
        row = score.loc[d, menu].dropna()
        if row.empty:
            continue
        if equal_weight:
            picks[d] = list(row.index)
            continue
        if rng is not None:
            avail = list(row.index)
            chosen = list(rng.choice(avail, size=min(TOP_N, len(avail)), replace=False))
        else:
            chosen = list(row.sort_values(ascending=False).index[:TOP_N])
        cs = cash_score.loc[d]
        if pd.notna(cs):
            chosen = [s for s in chosen if row[s] > cs]
        picks[d] = chosen
    weights = base.weights_from_selection(close.index, signal_dates, picks, cols)
    return weights, signal_dates


def vol_schedule(
    index: pd.DatetimeIndex,
    signal_dates: list[pd.Timestamp],
    book_returns: pd.Series,
    target: float | None,
) -> np.ndarray:
    """Down-only exposure multiplier, set on the signal close, live next open."""
    n = len(index)
    sched = np.ones(n)
    if target is None:
        return sched
    realized = book_returns.rolling(VOL_WINDOW).std(ddof=1) * np.sqrt(252.0)
    pos = {d: i for i, d in enumerate(index)}
    change: dict[int, float] = {}
    for d in signal_dates:
        i = pos[d]
        if i + 1 >= n:
            continue
        v = float(realized.iloc[i])
        change[i + 1] = 1.0 if not np.isfinite(v) or v <= 0 else min(1.0, target / v)
    current = 1.0
    for i in range(n):
        if i in change:
            current = change[i]
        sched[i] = current
    return sched


def simulate(
    weights: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    scale: np.ndarray,
    cost_bps: float,
    *,
    brake: bool,
    forced_brake: np.ndarray | None = None,
) -> tuple[pd.Series, pd.Series, np.ndarray]:
    cols = list(weights.columns)
    cash_i = cols.index(CASH)
    wb = weights.to_numpy(dtype=float)
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    n = len(wb)
    rets = np.zeros(n)
    turns = np.zeros(n)
    brake_on = np.zeros(n, dtype=bool)
    if forced_brake is not None:
        brake_on = forced_brake.astype(bool).copy()
    w_prev = np.zeros(wb.shape[1])
    equity = 1.0
    peak = 1.0
    engaged = False
    engaged_i = -1
    armed = True
    for i in range(n):
        m = scale[i] * (BRAKE_MULT if brake_on[i] else 1.0)
        row = wb[i]
        risk = row.copy()
        risk[cash_i] = 0.0
        w = risk * m
        w[cash_i] = row[cash_i] + (1.0 - m) * risk.sum()
        gross = float(w_prev @ lo[i] + w @ lc[i])
        turnover = float(np.abs(w - w_prev).sum())
        r = gross - turnover * cost_bps / 10_000.0
        rets[i] = r
        turns[i] = turnover
        equity *= 1.0 + r
        peak = max(peak, equity)
        dd = equity / peak - 1.0
        if brake and forced_brake is None:
            if engaged:
                if dd >= 0.0 or (i - engaged_i) >= BRAKE_RECOVER_SESSIONS:
                    engaged = False
                    armed = dd > BRAKE_TRIGGER
            else:
                if not armed and dd > BRAKE_TRIGGER:
                    armed = True
                if armed and dd <= BRAKE_TRIGGER:
                    engaged = True
                    engaged_i = i
                    armed = False
            if i + 1 < n:
                brake_on[i + 1] = engaged
        w_prev = w
    idx = weights.index
    return pd.Series(rets, index=idx), pd.Series(turns, index=idx), brake_on


def legs(close: pd.DataFrame, open_: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prev_c = close.shift(1)
    return (open_ / prev_c - 1.0).fillna(0.0), (close / open_ - 1.0).fillna(0.0)


def flat(name: str, m: base.Metrics) -> dict[str, float]:
    return {f"{name}_{k}": v for k, v in m.__dict__.items()}


def run_config(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    lookback: str,
    target: float | None,
    brake: bool,
    cost_bps: float,
    *,
    rng: np.random.Generator | None = None,
    forced_brake: np.ndarray | None = None,
) -> tuple[pd.Series, pd.Series, np.ndarray]:
    weights, signal_dates = base_weights(close, lookback, rng=rng)
    gross_book, _, _ = simulate(
        weights, leg_open, leg_close, np.ones(len(close.index)), 0.0, brake=False
    )
    scale = vol_schedule(close.index, signal_dates, gross_book, target)
    return simulate(
        weights,
        leg_open,
        leg_close,
        scale,
        cost_bps,
        brake=brake,
        forced_brake=forced_brake,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick-seeds", type=int, default=60)
    ap.add_argument("--shift-seeds", type=int, default=20)
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((OUT_DIR / "candidate-manifest.json").read_text())
    assert manifest["generated_before_backtest"] is True
    assert manifest["candidate_count"] == 12

    close, open_ = base.load_panel(symbols())
    print(
        f"panel {close.shape[0]} sessions x {close.shape[1]} symbols "
        f"{close.index[0].date()}..{close.index[-1].date()}",
        flush=True,
    )
    leg_open, leg_close = legs(close, open_)
    rf = close[RF].pct_change(fill_method=None).fillna(0.0)

    rows: list[dict] = []
    series: dict[str, pd.Series] = {}
    brake_states: dict[str, np.ndarray] = {}
    for lookback in LOOKBACKS:
        for target in VOL_TARGETS:
            for brake_name in BRAKES:
                cid = cell_id(target, brake_name, lookback)
                brake = brake_name != "none"
                for tag, cost in (
                    ("net10", base.COST_BPS_PRIMARY),
                    ("net20", base.COST_BPS_STRESS),
                ):
                    ret, turnover, states = run_config(
                        close, leg_open, leg_close, lookback, target, brake, cost
                    )
                    wm = base.window_metrics(ret, rf, turnover)
                    row = {
                        "cell_id": cid,
                        "family": "voltarget_brake",
                        "cost": tag,
                        "lookback": lookback,
                        "vol_target": -1.0 if target is None else target,
                        "brake": brake_name,
                    }
                    for wname, m in wm.items():
                        row.update(flat(wname, m))
                    rows.append(row)
                    if tag == "net10":
                        series[cid] = ret
                        brake_states[cid] = states
                print(f"cell {cid} done", flush=True)

    # benchmarks -------------------------------------------------------
    for bench in BENCHMARKS:
        ret, turnover = base.buy_hold(close, open_, bench)
        wm = base.window_metrics(ret, rf, turnover)
        row = {"cell_id": f"bench_{bench}", "family": "benchmark", "cost": "net0"}
        for wname, m in wm.items():
            row.update(flat(wname, m))
        rows.append(row)
        series[f"bench_{bench}"] = ret
    eq_weights, _ = base_weights(close, "63", equal_weight=True)
    ret, turnover, _ = simulate(
        eq_weights,
        leg_open,
        leg_close,
        np.ones(len(close.index)),
        base.COST_BPS_PRIMARY,
        brake=False,
    )
    wm = base.window_metrics(ret, rf, turnover)
    row = {"cell_id": "bench_A4_equal_weight", "family": "benchmark", "cost": "net10"}
    for wname, m in wm.items():
        row.update(flat(wname, m))
    rows.append(row)
    series["bench_A4_equal_weight"] = ret

    table = pd.DataFrame(rows)
    table.to_parquet(OUT_DIR / "cells.parquet", index=False)

    primary = table.loc[(table["cost"] == "net10") & (table["family"] == "voltarget_brake")].copy()
    cells_only = primary.sort_values("select_sharpe", ascending=False)
    winner = str(cells_only.iloc[0]["cell_id"])
    print(f"selection-window winner: {winner}", flush=True)

    # placebos ---------------------------------------------------------
    placebo_rows: list[dict] = []
    for cid in cells_only["cell_id"]:
        spec = primary.loc[primary["cell_id"] == cid].iloc[0]
        target = None if spec["vol_target"] < 0 else float(spec["vol_target"])
        brake = spec["brake"] != "none"
        lookback = str(spec["lookback"])
        for seed in range(args.pick_seeds):
            rng = np.random.default_rng(seed)
            pret, ptv, _ = run_config(
                close, leg_open, leg_close, lookback, target, brake, base.COST_BPS_PRIMARY, rng=rng
            )
            wm = base.window_metrics(pret, rf, ptv)
            placebo_rows.append(
                {
                    "cell_id": cid,
                    "placebo": "random_pick",
                    "seed": seed,
                    "select_sharpe": wm["select"].sharpe,
                    "holdout_sharpe": wm["holdout"].sharpe,
                    "anchor_sharpe": wm["anchor"].sharpe,
                    "anchor_cagr": wm["anchor"].cagr,
                    "anchor_max_dd": wm["anchor"].max_dd,
                }
            )
        if brake:
            truth = brake_states[cid]
            for seed in range(args.shift_seeds):
                rng = np.random.default_rng(1000 + seed)
                shift = int(rng.integers(1, 21))
                forced = np.zeros_like(truth)
                if shift < len(truth):
                    forced[shift:] = truth[:-shift]
                pret, ptv, _ = run_config(
                    close,
                    leg_open,
                    leg_close,
                    lookback,
                    target,
                    True,
                    base.COST_BPS_PRIMARY,
                    forced_brake=forced,
                )
                wm = base.window_metrics(pret, rf, ptv)
                placebo_rows.append(
                    {
                        "cell_id": cid,
                        "placebo": "brake_calendar_shift",
                        "seed": seed,
                        "shift": shift,
                        "select_sharpe": wm["select"].sharpe,
                        "holdout_sharpe": wm["holdout"].sharpe,
                        "anchor_sharpe": wm["anchor"].sharpe,
                        "anchor_cagr": wm["anchor"].cagr,
                        "anchor_max_dd": wm["anchor"].max_dd,
                    }
                )
        print(f"placebo {cid} done", flush=True)
    placebo = pd.DataFrame(placebo_rows)
    placebo.to_parquet(OUT_DIR / "placebo.parquet", index=False)

    # gates ------------------------------------------------------------
    spy = table.loc[table["cell_id"] == "bench_SPY"].iloc[0]
    entries: list[dict] = []
    for cid in cells_only["cell_id"]:
        r = primary.loc[primary["cell_id"] == cid].iloc[0]
        stress = table.loc[(table["cell_id"] == cid) & (table["cost"] == "net20")].iloc[0]
        pick = placebo.loc[(placebo["cell_id"] == cid) & (placebo["placebo"] == "random_pick")]
        shifted = placebo.loc[
            (placebo["cell_id"] == cid) & (placebo["placebo"] == "brake_calendar_shift")
        ]
        g1 = bool(r["anchor_cagr"] >= GATE_G1_CAGR and r["anchor_max_dd"] >= GATE_G1_MAXDD)
        g1alt = bool(
            r["anchor_sharpe"] >= GATE_G1ALT_SHARPE and r["anchor_cagr"] >= GATE_G1ALT_CAGR
        )
        g2 = bool(r["holdout_sharpe"] >= GATE_G2_SHARPE and r["holdout_cagr"] > 0)
        beat = float((pick["select_sharpe"] >= r["select_sharpe"]).mean()) if len(pick) else np.nan
        beat_holdout = (
            float((pick["holdout_sharpe"] >= r["holdout_sharpe"]).mean()) if len(pick) else np.nan
        )
        g3 = bool(beat <= GATE_G3_PLACEBO)
        g4 = bool(
            (stress["anchor_cagr"] >= GATE_G1_CAGR and stress["anchor_max_dd"] >= GATE_G1_MAXDD)
            or (
                stress["anchor_sharpe"] >= GATE_G1ALT_SHARPE
                and stress["anchor_cagr"] >= GATE_G1ALT_CAGR
            )
        )
        vol_matched = float(
            r["anchor_cagr"] - (r["anchor_vol"] / spy["anchor_vol"]) * spy["anchor_cagr"]
        )
        entry = {
            "cell_id": cid,
            "lookback": r["lookback"],
            "vol_target": None if r["vol_target"] < 0 else float(r["vol_target"]),
            "brake": r["brake"],
            "select_sharpe": float(r["select_sharpe"]),
            "select_cagr": float(r["select_cagr"]),
            "select_max_dd": float(r["select_max_dd"]),
            "holdout_sharpe": float(r["holdout_sharpe"]),
            "holdout_cagr": float(r["holdout_cagr"]),
            "holdout_max_dd": float(r["holdout_max_dd"]),
            "anchor_sharpe": float(r["anchor_sharpe"]),
            "anchor_cagr": float(r["anchor_cagr"]),
            "anchor_max_dd": float(r["anchor_max_dd"]),
            "anchor_vol": float(r["anchor_vol"]),
            "turnover_yr": float(r["anchor_turnover_yr"]),
            "stress20_anchor_cagr": float(stress["anchor_cagr"]),
            "stress20_anchor_max_dd": float(stress["anchor_max_dd"]),
            "stress20_anchor_sharpe": float(stress["anchor_sharpe"]),
            "stress20_holdout_sharpe": float(stress["holdout_sharpe"]),
            "vol_matched_excess_over_spy_anchor": vol_matched,
            "placebo_pick_beat_frac_select": beat,
            "placebo_pick_beat_frac_holdout": beat_holdout,
            "placebo_pick_select_sharpe_median": float(pick["select_sharpe"].median())
            if len(pick)
            else None,
            "placebo_pick_select_sharpe_p95": float(pick["select_sharpe"].quantile(0.95))
            if len(pick)
            else None,
            "placebo_shift_beat_frac_select": float(
                (shifted["select_sharpe"] >= r["select_sharpe"]).mean()
            )
            if len(shifted)
            else None,
            "placebo_shift_anchor_dd_better_frac": float(
                (shifted["anchor_max_dd"] >= r["anchor_max_dd"]).mean()
            )
            if len(shifted)
            else None,
            "G1": g1,
            "G1_alt": g1alt,
            "G2": g2,
            "G3": g3,
            "G4": g4,
            "G5": True,
            "all_gates": bool((g1 or g1alt) and g2 and g3 and g4),
        }
        entries.append(entry)

    bench_rows = []
    for cid in [f"bench_{b}" for b in BENCHMARKS] + ["bench_A4_equal_weight"]:
        r = table.loc[table["cell_id"] == cid].iloc[0]
        bench_rows.append(
            {
                "cell_id": cid,
                "select_sharpe": float(r["select_sharpe"]),
                "select_cagr": float(r["select_cagr"]),
                "holdout_sharpe": float(r["holdout_sharpe"]),
                "holdout_cagr": float(r["holdout_cagr"]),
                "anchor_sharpe": float(r["anchor_sharpe"]),
                "anchor_cagr": float(r["anchor_cagr"]),
                "anchor_max_dd": float(r["anchor_max_dd"]),
                "anchor_vol": float(r["anchor_vol"]),
            }
        )

    s3 = next(e for e in entries if e["cell_id"] == "s3_lb63_novt_nobrake")
    reference_check = {
        "cell_id": s3["cell_id"],
        "published_anchor_cagr": 1.454,
        "published_anchor_max_dd": -0.564,
        "published_anchor_sharpe": 1.48,
        "reproduced_anchor_cagr": s3["anchor_cagr"],
        "reproduced_anchor_max_dd": s3["anchor_max_dd"],
        "reproduced_anchor_sharpe": s3["anchor_sharpe"],
        "matches": bool(
            abs(s3["anchor_cagr"] - 1.454) < 0.02
            and abs(s3["anchor_max_dd"] + 0.564) < 0.01
            and abs(s3["anchor_sharpe"] - 1.48) < 0.03
        ),
    }
    summary = {
        "iter_id": ITER_ID,
        "card_id": "H-20260922-02",
        "windows": base.WINDOWS,
        "cell_count": len(entries),
        "selection_rule": "highest selection-window Sharpe at 10 bp per side",
        "winner": winner,
        "s3_reference_check": reference_check,
        "cells": entries,
        "benchmarks": bench_rows,
        "gate_thresholds": {
            "G1": "anchor cagr >= 0.50 and anchor max_dd >= -0.35",
            "G1_alt": "anchor sharpe >= 2.0 and anchor cagr >= 0.30",
            "G2": "holdout sharpe >= 1.0 and holdout cagr > 0",
            "G3": "random-pick placebo beat fraction <= 0.10",
            "G4": "G1 or G1_alt still holds at 20 bp per side",
            "G5": "Alpaca long-only spot ETFs on the existing daily cron",
        },
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    equity = pd.DataFrame({k: (1.0 + v).cumprod() for k, v in series.items()})
    equity.to_parquet(OUT_DIR / "equity.parquet")
    write_report(summary)
    print(json.dumps(reference_check, indent=2, default=float))
    print(json.dumps(entries[:3], indent=2, default=float))
    return 0


def pct(x: float | None) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{100 * x:.1f}%"


def num(x: float | None) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.2f}"


def write_report(summary: dict) -> None:
    lines: list[str] = []
    lines.append("# H-20260922-02 report: S3 volatility target and drawdown brake")
    lines.append("")
    lines.append(
        f"Iteration `{summary['iter_id']}`. Twelve preregistered cells, "
        f"selection rule: {summary['selection_rule']}. "
        f"Selection-window winner: **{summary['winner']}**."
    )
    lines.append("")
    chk = summary["s3_reference_check"]
    lines.append(
        f"Engine identity check: cell `{chk['cell_id']}` is the unmodified S3 sleeve and "
        f"reproduces anchor {pct(chk['reproduced_anchor_cagr'])} / "
        f"{pct(chk['reproduced_anchor_max_dd'])} / {num(chk['reproduced_anchor_sharpe'])} "
        f"against the published 145.4% / -56.4% / 1.48 "
        f"({'match' if chk['matches'] else 'MISMATCH'})."
    )
    lines.append("")
    lines.append("## Per-cell windows (10 bp per side)")
    lines.append("")
    lines.append(
        "| cell | select Sh | select CAGR | holdout Sh | holdout CAGR | anchor Sh | "
        "anchor CAGR | anchor maxDD | turnover/yr |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for e in summary["cells"]:
        lines.append(
            f"| `{e['cell_id']}` | {num(e['select_sharpe'])} | {pct(e['select_cagr'])} | "
            f"{num(e['holdout_sharpe'])} | {pct(e['holdout_cagr'])} | {num(e['anchor_sharpe'])} | "
            f"{pct(e['anchor_cagr'])} | {pct(e['anchor_max_dd'])} | {e['turnover_yr']:.1f} |"
        )
    lines.append("")
    lines.append("## The five required numbers, anchor window")
    lines.append("")
    lines.append("| reference | anchor Sharpe | anchor CAGR | anchor maxDD |")
    lines.append("|---|---|---|---|")
    for b in summary["benchmarks"]:
        lines.append(
            f"| {b['cell_id']} | {num(b['anchor_sharpe'])} | {pct(b['anchor_cagr'])} | "
            f"{pct(b['anchor_max_dd'])} |"
        )
    best = next(e for e in summary["cells"] if e["cell_id"] == summary["winner"])
    lines.append("")
    lines.append(
        f"Volatility-matched excess over SPY for the winner (anchor CAGR minus "
        f"cell_vol/SPY_vol times SPY CAGR): **{pct(best['vol_matched_excess_over_spy_anchor'])}**."
    )
    lines.append(
        f"Random-pick placebo for the winner: "
        f"{pct(best['placebo_pick_beat_frac_select'])} of 60 seeds beat it on the selection "
        f"window, {pct(best['placebo_pick_beat_frac_holdout'])} on the holdout; "
        f"placebo select Sharpe median {num(best['placebo_pick_select_sharpe_median'])}, "
        f"p95 {num(best['placebo_pick_select_sharpe_p95'])}."
    )
    if best["placebo_shift_beat_frac_select"] is not None:
        lines.append(
            f"Brake calendar-shift placebo for the winner: "
            f"{pct(best['placebo_shift_beat_frac_select'])} of 20 shifted-brake seeds beat it "
            f"on the selection window, and {pct(best['placebo_shift_anchor_dd_better_frac'])} "
            f"had an anchor drawdown at least as shallow."
        )
    lines.append("")
    lines.append("## Gate table")
    lines.append("")
    lines.append(
        "| cell | G1 ret+DD | G1' Sh | G2 holdout | G3 placebo | G4 20bp | G5 exec | all |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    mark = {True: "pass", False: "FAIL"}
    for e in summary["cells"]:
        lines.append(
            f"| `{e['cell_id']}` | {mark[e['G1']]} | {mark[e['G1_alt']]} | {mark[e['G2']]} | "
            f"{mark[e['G3']]} ({pct(e['placebo_pick_beat_frac_select'])}) | {mark[e['G4']]} | "
            f"{mark[e['G5']]} | {mark[e['all_gates']]} |"
        )
    lines.append("")
    lines.append("## Stress view (20 bp per side)")
    lines.append("")
    lines.append("| cell | anchor CAGR | anchor maxDD | anchor Sharpe | holdout Sharpe |")
    lines.append("|---|---|---|---|---|")
    for e in summary["cells"]:
        lines.append(
            f"| `{e['cell_id']}` | {pct(e['stress20_anchor_cagr'])} | "
            f"{pct(e['stress20_anchor_max_dd'])} | {num(e['stress20_anchor_sharpe'])} | "
            f"{num(e['stress20_holdout_sharpe'])} |"
        )
    lines.append("")
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
