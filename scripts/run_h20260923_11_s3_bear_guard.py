#!/usr/bin/env python3
"""H-20260923-11: does a bear-regime gate cut S3's pre-window drawdown by more
than an exposure-matched lower volatility target would?

S3 as renewed (menu TQQQ SOXL UPRO USD TECL, 63-session momentum, top 2,
monthly, absolute momentum against SHY, vt40 on 21-session realized volatility,
QQQ dip boost 60/10) is copied unchanged from `run_h20260922_05_salvage.py`.
Each gate moves the book's risk weight to SHY while it is on; the gate is read
on a completed close and applies from the next open, like the volatility target.

Every earlier bear-guard test ran on 2023-09..2026-09, which holds no bear
market. Here the design window is 2016-01-04..2023-09-15, the years before any
window used to select S3 (the frozen S3 there: 30.7% / Sharpe 0.83 / -48.0%,
`scripts/stress_s3_pre_window.py`). The frozen anchor window is a do-no-harm
check only; the 2026 holdout was already seen for S3, so no holdout claim is
made for any gate.

Controls per gate (preregistered in candidate-manifest.json):
- EM: base and boost targets scaled by one factor c, found by bisection so the
  mean daily gross risk exposure over the design window equals the gate's;
- CS: 20 circular shifts of the gate's on/off series inside the design window
  by round(N * j / 21) sessions, keeping its durations but not its timing.

    uv run python scripts/run_h20260923_11_s3_bear_guard.py [--render-only]
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
import run_h20260922_05_salvage as salvage  # noqa: E402

ITER_ID = "h20260923_11_s3_bear_guard"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
MANIFEST = OUT_DIR / "candidate-manifest.json"
CASH = base.CASH
PANEL_START = "2015-01-02"  # bars begin 2016-01-04: S3 holds risk from 2016-05-02 and the
# 200-session SMAs are valid from 2016-10-17; a gate reads as off during warmup
DESIGN = ("2016-01-04", "2023-09-15")
ANCHOR = (base.ANCHOR_START, base.ANCHOR_END)
BASE_TARGET = 0.40
BOOST_TARGET = 0.60
BOOST_HOLD = 10
GATES = ("BG01", "BG02", "BG03", "BG04")
GATE_RULES = {
    "BG01": "QQQ close < SMA200(QQQ)",
    "BG02": "SMH close < SMA200(SMH)",
    "BG03": "HYG/IEF < SMA100(HYG/IEF)",
    "BG04": "unscaled S3 book equity < its SMA200",
}
N_SHIFTS = 20
MIN_DD_GAIN = 0.10
MIN_SHARPE_GAIN = 0.10
MIN_SHIFT_BEATS = 18
G1_CAGR = 0.50
G1_MAX_DD = -0.35


def symbols() -> list[str]:
    return sorted(set(salvage.symbols()) | {"SMH", "HYG", "IEF"})


def gate_signals(close: pd.DataFrame, book_gross: pd.Series) -> dict[str, np.ndarray]:
    """True on a close where the gate says risk off; warmup reads as off."""
    qqq, smh = close["QQQ"], close["SMH"]
    ratio = close["HYG"] / close["IEF"]
    book = (1.0 + book_gross).cumprod()
    raw = {
        "BG01": qqq < qqq.rolling(200).mean(),
        "BG02": smh < smh.rolling(200).mean(),
        "BG03": ratio < ratio.rolling(100).mean(),
        "BG04": book < book.rolling(200).mean(),
    }
    return {k: v.fillna(False).to_numpy(dtype=bool) for k, v in raw.items()}


def gate_multiplier(gate: np.ndarray) -> np.ndarray:
    """A gate read on close i-1 holds the book in SHY from the open of i."""
    m = np.ones(len(gate))
    m[1:] = np.where(gate[:-1], 0.0, 1.0)
    return m


def risk_exposure(weights: pd.DataFrame, scale: np.ndarray) -> np.ndarray:
    risk = weights.drop(columns=[CASH]).sum(axis=1).to_numpy(dtype=float)
    return risk * scale


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    return (index >= window[0]) & (index <= window[1])


def circular_shift(gate: np.ndarray, mask: np.ndarray, offset: int) -> np.ndarray:
    out = gate.copy()
    idx = np.flatnonzero(mask)
    out[idx] = np.roll(gate[idx], offset)
    return out


def scores(ret: pd.Series, turn: pd.Series, rf: pd.Series, window: tuple[str, str]) -> dict:
    mask = window_mask(ret.index, window)
    return base.metrics(ret.loc[mask], rf, turn.loc[mask]).__dict__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true")
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = {c["candidate_id"] for c in manifest["candidates"]}
    missing = set(GATES) - ids
    if missing:
        raise SystemExit(f"candidate-manifest.json lacks {sorted(missing)}")
    if args.render_only:
        render(pd.read_parquet(OUT_DIR / "cells.parquet"), load_summary())
        return 0

    base.WARMUP_START = PANEL_START
    close, open_ = base.load_panel(symbols())
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    weights, signal_dates = salvage.sleeve_weights(close, "s3")
    ones = np.ones(len(close.index))
    book_gross, _ = salvage.simulate(weights, leg_open, leg_close, ones, 0.0)
    boost = salvage.boost_window(salvage.dip_signal(close), BOOST_HOLD)

    def schedule(c: float) -> np.ndarray:
        return salvage.vol_scale(
            close.index, signal_dates, book_gross, BASE_TARGET * c, boost, BOOST_TARGET * c
        )

    def run(scale: np.ndarray) -> dict:
        out = {}
        for bps in (10.0, 20.0):
            ret, turn = salvage.simulate(weights, leg_open, leg_close, scale, bps)
            out[bps] = (ret, turn)
        return out

    design = window_mask(close.index, DESIGN)
    sched = schedule(1.0)
    gates = gate_signals(close, book_gross)
    rows, placebo_rows = [], []

    def record(cell_id: str, role: str, scale: np.ndarray, extra: dict) -> dict:
        res = run(scale)
        row = {"cell_id": cell_id, "role": role, **extra}
        row["design_exposure"] = float(risk_exposure(weights, scale)[design].mean())
        for bps, tag in ((10.0, ""), (20.0, "stress20_")):
            ret, turn = res[bps]
            for name, window in (("design", DESIGN), ("anchor", ANCHOR)):
                for k, v in scores(ret, turn, rf, window).items():
                    row[f"{tag}{name}_{k}"] = v
        ret10 = res[10.0][0]
        row["yearly"] = json.dumps(
            {str(y): float((1.0 + r).prod() - 1.0) for y, r in ret10.groupby(ret10.index.year)}
        )
        rows.append(row)
        print(
            f"{cell_id:10s} design {row['design_cagr']:.1%} / {row['design_sharpe']:.2f} / "
            f"{row['design_max_dd']:.1%}  anchor {row['anchor_cagr']:.1%} / "
            f"{row['anchor_max_dd']:.1%}  exposure {row['design_exposure']:.3f}",
            flush=True,
        )
        return row

    record("BG00", "reference", sched, {"rule": "S3 as renewed, no gate", "c": 1.0})
    for gid in GATES:
        gate = gates[gid]
        scale = sched * gate_multiplier(gate)
        g_row = record(
            gid,
            "candidate",
            scale,
            {
                "rule": GATE_RULES[gid],
                "c": 1.0,
                "design_time_gated": float(gate[design].mean()),
                "design_gate_switches": int(np.abs(np.diff(gate[design].astype(int))).sum()),
            },
        )
        target = g_row["design_exposure"]
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2.0
            if risk_exposure(weights, schedule(mid))[design].mean() < target:
                lo = mid
            else:
                hi = mid
        c = (lo + hi) / 2.0
        record(f"EM-{gid}", "exposure_matched_control", schedule(c), {"rule": "vt scaled", "c": c})
        n = int(design.sum())
        for j in range(1, N_SHIFTS + 1):
            offset = round(n * j / (N_SHIFTS + 1))
            shifted = circular_shift(gate, design, offset)
            ret, turn = salvage.simulate(
                weights, leg_open, leg_close, sched * gate_multiplier(shifted), 10.0
            )
            m = scores(ret, turn, rf, DESIGN)
            placebo_rows.append(
                {"gate": gid, "j": j, "offset": offset, **{f"design_{k}": v for k, v in m.items()}}
            )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = pd.DataFrame(rows)
    placebo = pd.DataFrame(placebo_rows)
    cells.to_parquet(OUT_DIR / "cells.parquet")
    placebo.to_parquet(OUT_DIR / "placebo.parquet")
    summary = decide(cells, placebo)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    render(cells, summary)
    return 0


def load_summary() -> dict:
    return json.loads((OUT_DIR / "summary.json").read_text(encoding="utf-8"))


def decide(cells: pd.DataFrame, placebo: pd.DataFrame) -> dict:
    by_id = cells.set_index("cell_id")
    ref = by_id.loc["BG00"]
    decisions, passed = {}, []
    for gid in GATES:
        g, em = by_id.loc[gid], by_id.loc[f"EM-{gid}"]
        shifts = placebo.loc[placebo["gate"] == gid, "design_sharpe"]
        beats = int((g["design_sharpe"] > shifts).sum())
        checks = {
            "a_dd_gain": bool(g["design_max_dd"] - ref["design_max_dd"] >= MIN_DD_GAIN),
            "b_sharpe_gain": bool(g["design_sharpe"] >= ref["design_sharpe"] + MIN_SHARPE_GAIN),
            "c_beats_exposure_match": bool(g["design_sharpe"] > em["design_sharpe"]),
            "d_beats_shifts": bool(beats >= MIN_SHIFT_BEATS),
            "e_anchor_g1_10bp": bool(
                g["anchor_cagr"] >= G1_CAGR and g["anchor_max_dd"] >= G1_MAX_DD
            ),
            "e_anchor_g1_20bp": bool(
                g["stress20_anchor_cagr"] >= G1_CAGR and g["stress20_anchor_max_dd"] >= G1_MAX_DD
            ),
        }
        ok = all(checks.values())
        decisions[gid] = {
            "rule": GATE_RULES[gid],
            "checks": checks,
            "shift_beats": beats,
            "em_c": float(em["c"]),
            "pass": ok,
        }
        if ok:
            passed.append(gid)
    verdict = "guard recommended" if passed else "no guard; keep the 25% exit"
    return {"iter_id": ITER_ID, "verdict": verdict, "passed": passed, "decisions": decisions}


def render(cells: pd.DataFrame, summary: dict) -> None:
    """Trial ledger and report from the saved outputs, registered in
    search-space.json for the final-stage iteration gate."""
    ledger = OUT_DIR / "trial-ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as handle:
        for row in cells.to_dict(orient="records"):
            record = {
                k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()
            }
            gid = row["cell_id"]
            record["gates"] = summary["decisions"].get(gid)
            handle.write(json.dumps(record, default=str) + "\n")

    def pct(v: float) -> str:
        return "n/a" if v is None or pd.isna(v) else f"{v:.1%}"

    def num(v: float) -> str:
        return "n/a" if v is None or pd.isna(v) else f"{v:.2f}"

    by_id = cells.set_index("cell_id")
    lines = [
        f"# {ITER_ID}: bear-regime gate on S3 (H-20260923-11)",
        "",
        f"Verdict: **{summary['verdict']}** -- passed: {', '.join(summary['passed']) or 'none'}.",
        "",
        "S3 as renewed, unchanged; a gate moves its risk weight to SHY from the open after "
        f"a risk-off close. Design window {DESIGN[0]}..{DESIGN[1]} (before any window used "
        f"to select S3); anchor {ANCHOR[0]}..{ANCHOR[1]} is a do-no-harm check. The 2026 "
        "holdout was already seen for S3: no holdout claim is made. 10 bp per side, 20 bp "
        "stress.",
        "",
        "| cell | rule | design CAGR | design Sharpe | design maxDD | exposure | time gated | "
        "anchor CAGR | anchor maxDD | 20 bp anchor CAGR |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, r in by_id.iterrows():
        lines.append(
            f"| {cid} | {r['rule']} | {pct(r['design_cagr'])} | {num(r['design_sharpe'])} | "
            f"{pct(r['design_max_dd'])} | {num(r['design_exposure'])} | "
            f"{pct(r.get('design_time_gated'))} | {pct(r['anchor_cagr'])} | "
            f"{pct(r['anchor_max_dd'])} | {pct(r['stress20_anchor_cagr'])} |"
        )
    lines += [
        "",
        "| gate | (a) DD +10pt | (b) Sharpe +0.10 | (c) > exposure match | (d) shifts beaten | "
        "(e) anchor G1 10/20 bp | pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for gid, d in summary["decisions"].items():
        ch = d["checks"]
        lines.append(
            f"| {gid} | {ch['a_dd_gain']} | {ch['b_sharpe_gain']} | {ch['c_beats_exposure_match']} "
            f"(c={d['em_c']:.2f}) | {d['shift_beats']}/20 | "
            f"{ch['e_anchor_g1_10bp']}/{ch['e_anchor_g1_20bp']} | {d['pass']} |"
        )
    years = sorted(json.loads(by_id.iloc[0]["yearly"]))
    shown = ["BG00", *GATES]
    lines += ["", "Calendar-year returns, 10 bp:", "", "| year | " + " | ".join(shown) + " |"]
    lines.append("|---" * (len(shown) + 1) + "|")
    yearly = {cid: json.loads(by_id.loc[cid, "yearly"]) for cid in shown}
    for y in years:
        lines.append(f"| {y} | " + " | ".join(pct(yearly[c].get(y)) for c in shown) + " |")
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    space_path = OUT_DIR / "search-space.json"
    space = json.loads(space_path.read_text(encoding="utf-8"))
    space["trial_ledger_paths"] = [str(ledger.relative_to(ROOT))]
    space["evaluation_report_paths"] = [str((OUT_DIR / "report.md").relative_to(ROOT))]
    space_path.write_text(json.dumps(space, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
