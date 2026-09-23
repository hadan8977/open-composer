#!/usr/bin/env python3
"""H-20260923-12: should the part of S3 that sits in SHY hold a Defense First
rotation instead?

S3 as renewed (menu TQQQ SOXL UPRO USD TECL, 63-session momentum, top 2,
monthly, absolute momentum against SHY, vt40 on 21-session realized volatility,
QQQ dip boost 60/10) is copied unchanged from `run_h20260922_05_salvage.py`.
What changes is only where its remainder goes -- the volatility-target
remainder and any slot the absolute-momentum filter leaves in SHY.

Defense First (Carlson 2025, rules pinned in candidate-manifest.json from the
AllocateSmartly replication): on the last session of each month rank TLT, GLD,
DBC and UUP by the mean of their 1, 3, 6 and 12-calendar-month returns between
month-end closes; weights 40/30/20/10 by rank; an asset whose score is below
the T-bill fund's (BIL) hands its slot to the fallback (SPY in DF01, SHY in
DF02). Decided at the close, held from the next open. The 12-month part first
exists at the 2017-01-31 close; until then the remainder stays in SHY.

Controls: EW holds a static 25/25/25/25 basket of the four from the first
session S3 holds risk; RR-k keeps the weights, hurdle and fallback but ranks
the four at random each month (seeds 1..40). SPY and SHY buy-and-hold are
shown for scale. Design window 2016-01-04..2023-09-15; the frozen anchor is a
do-no-harm check; the 2026 holdout was already seen for S3, so no holdout
claim is made. Like every cell in this engine, the remainder's split is a
target held between decisions, not a drifting position.

    uv run python scripts/run_h20260923_12_s3_defense_first.py [--render-only]
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

ITER_ID = "h20260923_12_s3_defense_first"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
MANIFEST = OUT_DIR / "candidate-manifest.json"
CASH = base.CASH
PANEL_START = "2016-01-04"  # the first local daily bar for every symbol
DESIGN = ("2016-01-04", "2023-09-15")
ANCHOR = (base.ANCHOR_START, base.ANCHOR_END)
BASE_TARGET = 0.40
BOOST_TARGET = 0.60
BOOST_HOLD = 10
DEFENSIVE = ("TLT", "GLD", "DBC", "UUP")
MONTHS = (1, 3, 6, 12)  # calendar months between month-end closes
RANK_WEIGHTS = (0.40, 0.30, 0.20, 0.10)
HURDLE = "BIL"
FALLBACK = {"DF01": "SPY", "DF02": CASH}
BENCHMARKS = ("SPY", CASH)
STRESS_REPLAY = ROOT / "reports" / "paper" / "renewal" / "2026-09-23-s3-stress-2016-2023.json"
CANDIDATES = ("DF01", "DF02")
N_SEEDS = 40
MIN_SHARPE_GAIN = 0.10
MIN_SEED_BEATS = 36
G1_CAGR = 0.50
G1_MAX_DD = -0.35


def symbols() -> list[str]:
    return sorted(set(salvage.symbols()) | set(DEFENSIVE) | {"SPY", HURDLE, CASH})


def month_end_sessions(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    flags = base.rebalance_flags(index, "monthly")
    return list(index[flags.to_numpy()])


def momentum_score(close: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Mean of the 1, 3, 6 and 12-month returns between month-end closes, one
    row per month-end session; NaN until all four exist."""
    ends = close.loc[month_end_sessions(close.index), cols]
    parts = [ends / ends.shift(n) - 1.0 for n in MONTHS]
    return sum(parts) / len(parts)


def defense_weights(
    close: pd.DataFrame, fallback: str, rng: np.random.Generator | None = None
) -> pd.DataFrame:
    """Target weights over DEFENSIVE + fallback + cash, one row per session,
    decided at month-end closes and live from the next session. A placebo
    draws a fresh permutation at every decision date, warmup included."""
    cols = sorted(set(DEFENSIVE) | {fallback, CASH})
    score = momentum_score(close, list(DEFENSIVE) + [HURDLE])
    decided = pd.DataFrame(np.nan, index=close.index, columns=cols)
    for day, row in score.iterrows():
        order = list(DEFENSIVE) if rng is None else list(rng.permutation(DEFENSIVE))
        w = dict.fromkeys(cols, 0.0)
        if row.isna().any():
            w[CASH] = 1.0  # warmup: remainder stays in SHY, as in DF00
        else:
            if rng is None:
                order.sort(key=lambda sym: -row[sym])
            for sym, weight in zip(order, RANK_WEIGHTS, strict=True):
                w[fallback if row[sym] < row[HURDLE] else sym] += weight
        decided.loc[day] = pd.Series(w)
    # live from the session after the decision; before the first one, cash
    live = decided.shift(1).ffill()
    return live.fillna({c: (1.0 if c == CASH else 0.0) for c in cols})


def first_live(weights: pd.DataFrame) -> str | None:
    """First session the remainder holds anything but SHY."""
    risky = weights.drop(columns=[CASH]).sum(axis=1) > 0
    return str(risky.idxmax().date()) if risky.any() else None


def static_weights(close: pd.DataFrame, start: pd.Timestamp) -> pd.DataFrame:
    """25% in each of the four from ``start`` (S3's first risk session); SHY before."""
    cols = sorted(set(DEFENSIVE) | {CASH})
    w = pd.DataFrame(0.0, index=close.index, columns=cols)
    on = close.index >= start
    for sym in DEFENSIVE:
        w.loc[on, sym] = 0.25
    w.loc[~on, CASH] = 1.0
    return w


def expanded(
    book: pd.DataFrame, scale: np.ndarray, remainder_weights: pd.DataFrame | None
) -> pd.DataFrame:
    """S3's risk legs after the vol-target multiplier, plus its remainder held in
    ``remainder_weights`` (SHY when None), as one daily target-weight matrix."""
    risk = book.drop(columns=[CASH]).mul(scale, axis=0)
    rem = 1.0 - risk.sum(axis=1)
    hold = (
        pd.DataFrame({CASH: 1.0}, index=book.index)
        if remainder_weights is None
        else remainder_weights
    )
    parts = risk.copy()
    for col in hold.columns:
        add = hold[col] * rem
        parts[col] = parts[col] + add if col in parts else add
    return parts.fillna(0.0)


def simulate(
    weights: pd.DataFrame, leg_open: pd.DataFrame, leg_close: pd.DataFrame, cost_bps: float
) -> tuple[pd.Series, pd.Series]:
    """Same accounting as the salvage engine: yesterday's weights earn the
    overnight leg, today's the open-to-close leg, sum|dw| pays the cost."""
    cols = list(weights.columns)
    wb = weights.to_numpy(dtype=float)
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    prev = np.vstack([np.zeros((1, wb.shape[1])), wb[:-1]])
    gross = (prev * lo).sum(axis=1) + (wb * lc).sum(axis=1)
    turnover = np.abs(wb - prev).sum(axis=1)
    rets = gross - turnover * cost_bps / 10_000.0
    return pd.Series(rets, index=weights.index), pd.Series(turnover, index=weights.index)


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    return (index >= window[0]) & (index <= window[1])


def scores(ret: pd.Series, turn: pd.Series, rf: pd.Series, window: tuple[str, str]) -> dict:
    mask = window_mask(ret.index, window)
    return base.metrics(ret.loc[mask], rf, turn.loc[mask]).__dict__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render-only", action="store_true")
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = {c["candidate_id"] for c in manifest["candidates"]}
    missing = set(CANDIDATES) - ids
    if missing:
        raise SystemExit(f"candidate-manifest.json lacks {sorted(missing)}")
    if args.render_only:
        render(pd.read_parquet(OUT_DIR / "cells.parquet"), load_summary())
        return 0

    base.WARMUP_START = PANEL_START
    close, open_ = base.load_panel(symbols())
    leg_open, leg_close = salvage.legs(close, open_)
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    book, signal_dates = salvage.sleeve_weights(close, "s3")
    ones = np.ones(len(close.index))
    book_gross, _ = salvage.simulate(book, leg_open, leg_close, ones, 0.0)
    boost = salvage.boost_window(salvage.dip_signal(close), BOOST_HOLD)
    sched = salvage.vol_scale(
        close.index, signal_dates, book_gross, BASE_TARGET, boost, BOOST_TARGET
    )
    risk_total = book.drop(columns=[CASH]).mul(sched, axis=0).sum(axis=1)
    first_risk = risk_total[risk_total > 0].index[0]
    print(f"S3 first holds risk {first_risk.date()}", flush=True)
    rows, placebo_rows, starts = [], [], {}

    def record(
        cell_id: str, role: str, remainder: pd.DataFrame | None, rule: str, whole: bool = False
    ) -> dict:
        w = remainder if whole else expanded(book, sched, remainder)
        row = {"cell_id": cell_id, "role": role, "rule": rule}
        for bps, tag in ((10.0, ""), (20.0, "stress20_")):
            ret, turn = simulate(w, leg_open, leg_close, bps)
            for name, window in (("design", DESIGN), ("anchor", ANCHOR)):
                for k, v in scores(ret, turn, rf, window).items():
                    row[f"{tag}{name}_{k}"] = v
            if bps == 10.0:
                row["yearly"] = json.dumps(
                    {str(y): float((1.0 + r).prod() - 1.0) for y, r in ret.groupby(ret.index.year)}
                )
        rows.append(row)
        print(
            f"{cell_id:8s} design {row['design_cagr']:.1%} / {row['design_sharpe']:.2f} / "
            f"{row['design_max_dd']:.1%}  anchor {row['anchor_cagr']:.1%} / "
            f"{row['anchor_max_dd']:.1%}",
            flush=True,
        )
        return row

    # the reference must reproduce the frozen S3 numbers exactly: the salvage
    # engine, and the design-window numbers the stress replay published
    ref = record("DF00", "reference", None, "S3 as renewed, remainder in SHY")
    check, _ = salvage.run_cell(
        close, leg_open, leg_close, "s3", BASE_TARGET, 10.0, boost=boost, boost_target=BOOST_TARGET
    )
    mask = window_mask(close.index, DESIGN)
    parity = base.metrics(check.loc[mask], rf, pd.Series(0.0, index=check.index)).sharpe
    if abs(parity - ref["design_sharpe"]) > 1e-9:
        raise SystemExit(
            f"DF00 does not reproduce the salvage engine: {parity} vs {ref['design_sharpe']}"
        )
    replay = json.loads(STRESS_REPLAY.read_text(encoding="utf-8"))["cells"]["s3_vt40_boost"]
    for key in ("cagr", "sharpe", "max_dd"):
        if abs(replay["metrics"][key] - ref[f"design_{key}"]) > 1e-9:
            raise SystemExit(f"DF00 design {key} differs from the stress replay")
    ew = static_weights(close, first_risk)
    starts["EW"] = first_live(ew)
    record("EW", "control_static_basket", ew, "25/25/25/25 TLT GLD DBC UUP")
    for sym in BENCHMARKS:
        hold = pd.DataFrame({sym: 1.0}, index=close.index)
        record(sym, "benchmark", hold, f"{sym} buy and hold", whole=True)
    for cid in CANDIDATES:
        fb = FALLBACK[cid]
        rem = defense_weights(close, fb)
        starts[cid] = first_live(rem)
        record(cid, "candidate", rem, f"Defense First, failing slots to {fb}")
        for seed in range(1, N_SEEDS + 1):
            rng = np.random.default_rng(seed)
            w = expanded(book, sched, defense_weights(close, fb, rng))
            ret, turn = simulate(w, leg_open, leg_close, 10.0)
            m = scores(ret, turn, rf, DESIGN)
            placebo_rows.append(
                {"candidate": cid, "seed": seed, **{f"design_{k}": v for k, v in m.items()}}
            )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = pd.DataFrame(rows)
    placebo = pd.DataFrame(placebo_rows)
    cells.to_parquet(OUT_DIR / "cells.parquet")
    placebo.to_parquet(OUT_DIR / "placebo.parquet")
    summary = decide(cells, placebo)
    summary["first_risk_session"] = str(first_risk.date())
    summary["remainder_first_live"] = starts
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    render(cells, summary)
    return 0


def load_summary() -> dict:
    return json.loads((OUT_DIR / "summary.json").read_text(encoding="utf-8"))


def decide(cells: pd.DataFrame, placebo: pd.DataFrame) -> dict:
    by_id = cells.set_index("cell_id")
    ref, ew = by_id.loc["DF00"], by_id.loc["EW"]
    decisions, passed = {}, []
    for cid in CANDIDATES:
        c = by_id.loc[cid]
        seeds = placebo.loc[placebo["candidate"] == cid, "design_sharpe"]
        beats = int((c["design_sharpe"] > seeds).sum())
        checks = {
            "a_sharpe_gain": bool(c["design_sharpe"] >= ref["design_sharpe"] + MIN_SHARPE_GAIN),
            "b_dd_not_worse": bool(c["design_max_dd"] >= ref["design_max_dd"]),
            "c_beats_random_ranks": bool(beats >= MIN_SEED_BEATS),
            "d_beats_static_basket": bool(c["design_sharpe"] > ew["design_sharpe"]),
            "e_anchor_g1_10bp": bool(
                c["anchor_cagr"] >= G1_CAGR and c["anchor_max_dd"] >= G1_MAX_DD
            ),
            "e_anchor_g1_20bp": bool(
                c["stress20_anchor_cagr"] >= G1_CAGR and c["stress20_anchor_max_dd"] >= G1_MAX_DD
            ),
        }
        ok = all(checks.values())
        decisions[cid] = {
            "rule": c["rule"],
            "checks": checks,
            "seed_beats": beats,
            "seed_sharpe_median": float(seeds.median()),
            "pass": ok,
        }
        if ok:
            passed.append(cid)
    verdict = "hold the remainder in Defense First" if passed else "keep SHY"
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
            record["gates"] = summary["decisions"].get(row["cell_id"])
            handle.write(json.dumps(record, default=str) + "\n")

    def pct(v: float) -> str:
        return "n/a" if v is None or pd.isna(v) else f"{v:.1%}"

    def num(v: float) -> str:
        return "n/a" if v is None or pd.isna(v) else f"{v:.2f}"

    by_id = cells.set_index("cell_id")
    lines = [
        f"# {ITER_ID}: S3's remainder in Defense First instead of SHY (H-20260923-12)",
        "",
        f"Verdict: **{summary['verdict']}** -- passed: {', '.join(summary['passed']) or 'none'}.",
        "",
        "S3 as renewed, unchanged; only the remainder it keeps in SHY moves. Design window "
        f"{DESIGN[0]}..{DESIGN[1]}; anchor {ANCHOR[0]}..{ANCHOR[1]} is a do-no-harm check; "
        "no holdout claim. 10 bp per side on the whole weight vector, 20 bp stress.",
        "",
        f"S3 first holds risk {summary.get('first_risk_session')}. The remainder first leaves "
        "SHY on: "
        + ", ".join(f"{k} {v}" for k, v in (summary.get("remainder_first_live") or {}).items())
        + ". DF00 reproduces the salvage engine and the published 2016-2023 stress replay "
        "(CAGR, Sharpe and max DD within 1e-9). No cell applies the 25% drawdown exit; it is "
        "an account-level rule outside this comparison.",
        "",
        "| cell | rule | design CAGR | design Sharpe | design maxDD | anchor CAGR | "
        "anchor maxDD | 20 bp anchor CAGR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cid, r in by_id.iterrows():
        lines.append(
            f"| {cid} | {r['rule']} | {pct(r['design_cagr'])} | {num(r['design_sharpe'])} | "
            f"{pct(r['design_max_dd'])} | {pct(r['anchor_cagr'])} | {pct(r['anchor_max_dd'])} | "
            f"{pct(r['stress20_anchor_cagr'])} |"
        )
    lines += [
        "",
        "| candidate | (a) Sharpe +0.10 | (b) DD not worse | (c) random ranks beaten | "
        "(d) > static basket | (e) anchor G1 10/20 bp | pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for cid, d in summary["decisions"].items():
        ch = d["checks"]
        lines.append(
            f"| {cid} | {ch['a_sharpe_gain']} | {ch['b_dd_not_worse']} | {d['seed_beats']}/40 "
            f"(median {d['seed_sharpe_median']:.2f}) | {ch['d_beats_static_basket']} | "
            f"{ch['e_anchor_g1_10bp']}/{ch['e_anchor_g1_20bp']} | {d['pass']} |"
        )
    shown = list(by_id.index)
    years = sorted(json.loads(by_id.iloc[0]["yearly"]))
    yearly = {cid: json.loads(by_id.loc[cid, "yearly"]) for cid in shown}
    lines += ["", "Calendar-year returns, 10 bp:", "", "| year | " + " | ".join(shown) + " |"]
    lines.append("|---" * (len(shown) + 1) + "|")
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
