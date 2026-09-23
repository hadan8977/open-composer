"""H-20260923-10: a second levered sector lane beside semiconductors.

The one mechanism that has cleared the shipping gates is a trending sector held
with leverage under a volatility target (S3-vt40 + dip boost), and it is mostly a
semiconductor position (card H-20260923-09). This round asks whether another
sector does the same job with low correlation to it. Five single-ETF lanes are
preregistered in candidate-manifest.json -- NUGT, JNUG (gold miners), FAS, DPST
(banks), DFEN (aerospace and defense) -- and each runs through the frozen S3
machine unchanged:

- hold the lane ETF when its 63-session return beats SHY's at a month-end
  close, else SHY; fill at the next open;
- scale by min(1, 0.40 / 21-session realized volatility of the unscaled book),
  raised to 0.60 for 10 sessions after QQQ closes above its 200-session average
  with Wilder RSI(10) below 30; the removed weight sits in SHY.

Every building block is imported from the engines that froze those rules
(`scripts/run_h20260922_05_salvage.py`, `scripts/run_h20260918_05_recent_menu.py`),
so windows, costs, fills and metrics are identical to cards H-20260918-05,
H-20260922-02 and H-20260922-05. Placebos: the same machine on every other ETF in
the 24-name liquid levered pool (does this lane beat generic leverage?) and the
dip-signal calendar shift over 20 offsets. Gates G1-G5 plus a correlation cap
against the live S3 book; no lane is selected over another.

Usage::

    uv run python scripts/run_h20260923_10_levered_lanes.py
    uv run python scripts/run_h20260923_10_levered_lanes.py --render-only  # report from saved cells
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260922_05_salvage as research  # noqa: E402

base = research.base
ITER_ID = "h20260923_10_levered_lanes"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
MANIFEST = OUT_DIR / "candidate-manifest.json"
CASH = base.CASH
RF = base.RF
LANES = {"LN01": "NUGT", "LN02": "JNUG", "LN03": "FAS", "LN04": "DPST", "LN05": "DFEN"}
POOL = [
    "TQQQ", "SOXL", "SPXL", "TNA", "UPRO", "SSO", "QLD", "NUGT", "UDOW", "LABU", "FAS", "TECL",
    "JNUG", "ERX", "BOIL", "YINN", "GUSH", "TMF", "URTY", "BULZ", "AGQ", "DPST", "UWM", "NAIL",
]  # fmt: skip
BENCHMARKS = ["SPY", "SPMO", "QQQ", "TQQQ", "MTUM"]
BASE_TARGET = 0.40
BOOST_TARGET = 0.60
BOOST_HOLD = 10
LOOKBACK = "63"
SHIFTS = range(1, 21)
PLACEBO_MAX = 0.10
FAMILY_STRICT = PLACEBO_MAX / len(LANES)
CORR_MAX = 0.5


def symbols() -> list[str]:
    return sorted(
        {*POOL, *LANES.values(), CASH, RF, research.DIP_ASSET, *BENCHMARKS}
        | set(base.MENUS["A4_levered"])
    )


def lane_weights(close: pd.DataFrame, symbol: str) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """The S3 selection rule with a one-name menu: the lane at 100% when its
    63-session return beats SHY's on a month-end close, else SHY."""
    score = base.momentum_score(close[[symbol, CASH]], LOOKBACK)
    signal_dates = list(close.index[base.rebalance_flags(close.index, "monthly")])
    picks: dict[pd.Timestamp, list[str]] = {}
    for d in signal_dates:
        s, cs = score.at[d, symbol], score.at[d, CASH]
        if pd.isna(s):
            continue
        picks[d] = [symbol] if pd.isna(cs) or s > cs else []
    cols = sorted({symbol, CASH})
    return base.weights_from_selection(close.index, signal_dates, picks, cols), signal_dates


def run_lane(
    close: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    symbol: str,
    cost_bps: float,
    *,
    target: float | None = BASE_TARGET,
    boost: np.ndarray | None = None,
    boost_target: float | None = BOOST_TARGET,
) -> tuple[pd.Series, pd.Series]:
    weights, signal_dates = lane_weights(close, symbol)
    ones = np.ones(len(close.index))
    gross, _ = research.simulate(weights, leg_open, leg_close, ones, 0.0)
    if target is None and boost is None:
        scale = ones
    else:
        scale = research.vol_scale(
            close.index,
            signal_dates,
            gross,
            target,
            boost,
            boost_target if boost is not None else None,
        )
    return research.simulate(weights, leg_open, leg_close, scale, cost_bps)


def flat(prefix: str, m: base.Metrics) -> dict:
    return {f"{prefix}_{k}": v for k, v in m.__dict__.items()}


def g1(cagr: float, dd: float, sharpe: float) -> bool:
    return bool((cagr >= 0.50 and dd >= -0.35) or (sharpe >= 2.0 and cagr >= 0.30))


def render(cells: pd.DataFrame, summary: dict) -> None:
    """Trial ledger + evaluation report from the saved outputs, and their
    registration in search-space.json (the final-stage iteration gate)."""
    ledger = OUT_DIR / "trial-ledger.jsonl"
    with ledger.open("w", encoding="utf-8") as handle:
        for row in cells.to_dict(orient="records"):
            decision = summary["decisions"].get(row["cell_id"])
            record = {
                k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in row.items()
            }
            handle.write(json.dumps({**record, "gates": decision}, default=str) + "\n")

    def pct(v: float) -> str:
        return "n/a" if v is None or pd.isna(v) else f"{v:.1%}"

    def num(v: float) -> str:
        return "n/a" if v is None or pd.isna(v) else f"{v:.2f}"

    by_id = cells.set_index("cell_id")
    lines = [
        f"# {ITER_ID}: second levered sector lane (H-20260923-10)",
        "",
        f"Verdict: **{summary['verdict']}** -- passed: {summary['passed'] or 'none'}.",
        "",
        "Machine (frozen, from H-20260922-05): one-ETF lane, 63-session absolute momentum "
        "against SHY at month-end, vt40 on 21-session realized volatility, dip boost 60/10, "
        "cap 1.0, next-open fills, 10 bp per side (20 bp stress). Windows: selection "
        "2023-09-18..2025-12-31, holdout 2026-01-02..2026-09-17 (scored once), anchor "
        "2024-01-08..2026-09-16.",
        "",
        "| lane | anchor CAGR | anchor Sharpe | anchor maxDD | holdout CAGR | holdout Sharpe | "
        "20 bp anchor CAGR | corr S3 | pool beat | shift beat | G1 | G2 | G3 | G4 | pass |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid, d in summary["decisions"].items():
        r = by_id.loc[cid]
        lines.append(
            f"| {cid} {d['symbol']} | {pct(r['anchor_cagr'])} | {num(r['anchor_sharpe'])} | "
            f"{pct(r['anchor_max_dd'])} | {pct(r['holdout_cagr'])} | {num(r['holdout_sharpe'])} | "
            f"{pct(r['stress20_anchor_cagr'])} | {num(r['corr_s3_anchor'])} | "
            f"{pct(r['pool_beat_holdout'])} | {pct(r['shift_beat_holdout'])} | "
            f"{d['G1']} | {d['G2']} | {d['G3']} | {d['G4']} | **{d['pass']}** |"
        )
    ref = by_id.loc["s3_vt40_boost60_h10"]
    lines += [
        "",
        f"Reference, live S3 book (vt40 + boost): anchor {pct(ref['anchor_cagr'])} / Sharpe "
        f"{num(ref['anchor_sharpe'])} / {pct(ref['anchor_max_dd'])}, holdout Sharpe "
        f"{num(ref['holdout_sharpe'])}.",
        "",
        "Diagnostics (never ranked): each lane raw and with vt40 only; the pool of "
        f"{len(summary['pool_evaluated'])} liquid levered ETFs under the same machine is the "
        "generic-leverage placebo (holdout Sharpe of each is in cells.parquet).",
        "",
        "| diagnostic | anchor CAGR | anchor Sharpe | anchor maxDD | holdout Sharpe |",
        "|---|---|---|---|---|",
    ]
    for cid in [c for c in by_id.index if c.endswith(("_raw", "_vt40"))]:
        r = by_id.loc[cid]
        lines.append(
            f"| {cid} | {pct(r['anchor_cagr'])} | {num(r['anchor_sharpe'])} | "
            f"{pct(r['anchor_max_dd'])} | {num(r['holdout_sharpe'])} |"
        )
    pool = by_id[by_id["role"] == "placebo_pool"].sort_values("holdout_sharpe", ascending=False)
    lines += [
        "",
        "Pool under the same machine, best holdout Sharpe first: "
        + ", ".join(
            f"{s} {num(v)}" for s, v in zip(pool["symbol"], pool["holdout_sharpe"], strict=True)
        ),
        "",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    space_path = OUT_DIR / "search-space.json"
    space = json.loads(space_path.read_text(encoding="utf-8"))
    space["trial_ledger_paths"] = [str(ledger.relative_to(ROOT))]
    space["evaluation_report_paths"] = [str((OUT_DIR / "report.md").relative_to(ROOT))]
    space_path.write_text(json.dumps(space, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    if "--render-only" in sys.argv:
        render(
            pd.read_parquet(OUT_DIR / "cells.parquet"),
            json.loads((OUT_DIR / "summary.json").read_text(encoding="utf-8")),
        )
        return 0
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frozen_ids = sorted(c["candidate_id"] for c in manifest["candidates"])
    if frozen_ids != sorted(LANES):
        raise SystemExit(f"candidate manifest {frozen_ids} does not match {sorted(LANES)}")

    close, open_ = base.load_panel(symbols())
    leg_open, leg_close = research.legs(close, open_)
    rf = (close[RF] / close[RF].shift(1) - 1.0).fillna(0.0)
    sig = research.dip_signal(close)
    boost = research.boost_window(sig, BOOST_HOLD)
    anchor_mask = (close.index >= base.WINDOWS["anchor"][0]) & (
        close.index <= base.WINDOWS["anchor"][1]
    )
    s3_ret, _ = research.run_cell(
        close, leg_open, leg_close, "s3", BASE_TARGET, base.COST_BPS_PRIMARY,
        boost=boost, boost_target=BOOST_TARGET,
    )  # fmt: skip

    rows: list[dict] = []

    def record(cell_id: str, role: str, symbol: str, ret, turn, ret20=None, turn20=None) -> dict:
        row = {"cell_id": cell_id, "role": role, "symbol": symbol}
        wm = base.window_metrics(ret, rf, turn)
        for w in ("select", "holdout", "anchor"):
            row.update(flat(w, wm[w]))
        if ret20 is not None:
            wm20 = base.window_metrics(ret20, rf, turn20)
            for w in ("select", "holdout", "anchor"):
                row[f"stress20_{w}_cagr"] = wm20[w].cagr
                row[f"stress20_{w}_sharpe"] = wm20[w].sharpe
                row[f"stress20_{w}_max_dd"] = wm20[w].max_dd
        row["corr_s3_anchor"] = float(np.corrcoef(ret[anchor_mask], s3_ret[anchor_mask])[0, 1])
        rows.append(row)
        return row

    # Generic-leverage placebo: the identical machine on every pool ETF.
    pool_rows: dict[str, dict] = {}
    for symbol in POOL:
        if symbol not in close.columns or close[symbol].notna().sum() < 300:
            continue
        r, t = run_lane(close, leg_open, leg_close, symbol, base.COST_BPS_PRIMARY, boost=boost)
        pool_rows[symbol] = record(f"pool_{symbol}", "placebo_pool", symbol, r, t)

    placebo_shift: list[dict] = []
    decisions: dict[str, dict] = {}
    for cid, symbol in LANES.items():
        r, t = run_lane(close, leg_open, leg_close, symbol, base.COST_BPS_PRIMARY, boost=boost)
        r20, t20 = run_lane(close, leg_open, leg_close, symbol, base.COST_BPS_STRESS, boost=boost)
        row = record(cid, "candidate", symbol, r, t, r20, t20)
        for label, kwargs in (("raw", {"target": None}), ("vt40", {"boost": None})):
            dr, dt = run_lane(close, leg_open, leg_close, symbol, base.COST_BPS_PRIMARY, **kwargs)
            record(f"{cid}_{label}", "diagnostic", symbol, dr, dt)
        others = [p for s, p in pool_rows.items() if s != symbol]
        row["pool_n"] = len(others)
        row["pool_beat_holdout"] = float(
            np.mean([p["holdout_sharpe"] >= row["holdout_sharpe"] for p in others])
        )
        beat_h = beat_c = 0
        for k in SHIFTS:
            shifted = np.zeros_like(sig)
            shifted[k:] = sig[:-k]
            pr, pt = run_lane(
                close, leg_open, leg_close, symbol, base.COST_BPS_PRIMARY,
                boost=research.boost_window(shifted, BOOST_HOLD),
            )  # fmt: skip
            pm = base.window_metrics(pr, rf, pt)
            beat_h += pm["holdout"].sharpe > row["holdout_sharpe"]
            beat_c += pm["anchor"].cagr > row["anchor_cagr"]
            placebo_shift.append(
                {
                    "cell_id": cid,
                    "shift": k,
                    "holdout_sharpe": pm["holdout"].sharpe,
                    "anchor_cagr": pm["anchor"].cagr,
                }
            )
        row["shift_beat_holdout"] = beat_h / len(SHIFTS)
        row["shift_beat_anchor_cagr"] = beat_c / len(SHIFTS)
        gates = {
            "G1": g1(row["anchor_cagr"], row["anchor_max_dd"], row["anchor_sharpe"]),
            "G2": bool(row["holdout_sharpe"] >= 1.0 and row["holdout_cagr"] > 0),
            "G3": bool(
                row["pool_beat_holdout"] <= PLACEBO_MAX and row["shift_beat_holdout"] <= PLACEBO_MAX
            ),
            "G3_family_strict": bool(
                row["pool_beat_holdout"] <= FAMILY_STRICT
                and row["shift_beat_holdout"] <= FAMILY_STRICT
            ),
            "G4": g1(
                row["stress20_anchor_cagr"],
                row["stress20_anchor_max_dd"],
                row["stress20_anchor_sharpe"],
            ),
            "G5": True,
            "corr_le_0_5": bool(row["corr_s3_anchor"] <= CORR_MAX),
        }
        gates["pass"] = all(v for k, v in gates.items() if k != "G3_family_strict")
        decisions[cid] = {"symbol": symbol, **gates}
        print(f"{cid} {symbol}: {gates}", flush=True)

    for sym in BENCHMARKS:
        br, bt = base.buy_hold(close, open_, sym)
        record(f"bench_{sym}", "benchmark", sym, br, bt)
    s3_r20, s3_t20 = research.run_cell(
        close, leg_open, leg_close, "s3", BASE_TARGET, base.COST_BPS_STRESS,
        boost=boost, boost_target=BOOST_TARGET,
    )  # fmt: skip
    s3_r, s3_t = research.run_cell(
        close, leg_open, leg_close, "s3", BASE_TARGET, base.COST_BPS_PRIMARY,
        boost=boost, boost_target=BOOST_TARGET,
    )  # fmt: skip
    record("s3_vt40_boost60_h10", "reference_live_s3", "A4_levered", s3_r, s3_t, s3_r20, s3_t20)

    cells = pd.DataFrame(rows)
    cells.to_parquet(OUT_DIR / "cells.parquet", index=False)
    pd.DataFrame(placebo_shift).to_parquet(OUT_DIR / "placebo.parquet", index=False)
    passed = [cid for cid, d in decisions.items() if d["pass"]]
    summary = {
        "iter_id": ITER_ID,
        "hypothesis": "H-20260923-10",
        "direction": "dir:levered_industry_trend_second_bet",
        "machine": {
            "lookback": LOOKBACK,
            "rebalance": "monthly_last_session",
            "absolute_momentum_vs": CASH,
            "vol_target": BASE_TARGET,
            "boost_target": BOOST_TARGET,
            "boost_hold": BOOST_HOLD,
            "leverage_cap": 1.0,
        },
        "windows": base.WINDOWS,
        "costs_bps": [base.COST_BPS_PRIMARY, base.COST_BPS_STRESS],
        "pool_evaluated": sorted(pool_rows),
        "decisions": decisions,
        "passed": passed,
        "verdict": "pass" if passed else "refuted",
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    cols = [
        "cell_id", "symbol", "anchor_cagr", "anchor_sharpe", "anchor_max_dd", "holdout_cagr",
        "holdout_sharpe", "holdout_max_dd", "select_sharpe", "stress20_anchor_cagr",
        "corr_s3_anchor", "pool_beat_holdout", "shift_beat_holdout",
    ]  # fmt: skip
    view = cells[[c for c in cols if c in cells.columns]]
    print(view.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    render(cells, summary)
    print(json.dumps({"passed": passed, "verdict": summary["verdict"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
