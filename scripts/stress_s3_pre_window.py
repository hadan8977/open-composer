#!/usr/bin/env python3
"""S3 as renewed (vt40 + dip boost 60/10), replayed on 2016-01 .. 2023-09-15.

A risk disclosure for the live-pilot decision, not a research iteration: no
rule, parameter or asset is chosen here. The frozen research windows start at
2023-09-18, so the renewed S3 has never been run through a semiconductor bear
market; this replays the identical engine (`run_h20260922_05_salvage.py`, which
the paper adapter matches to 1e-12) on the years before the select window and
reports what the 25% drawdown exit would have done.

    uv run python scripts/stress_s3_pre_window.py

Writes ``reports/paper/renewal/2026-09-23-s3-stress-2016-2023.{json,md}``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402

PANEL_START = "2015-01-02"  # bars begin 2016-01-04: S3 holds risk from 2016-05-02,
# the QQQ SMA200 (dip boost) is valid from 2016-10-17
REPORT_START = "2016-01-04"
REPORT_END = "2023-09-15"  # the last session before the frozen select window
EXIT_DRAWDOWN = 0.25
COST_BPS = 10.0
OUT = ROOT / "reports" / "paper" / "renewal"


def equity(ret: pd.Series) -> pd.Series:
    return (1.0 + ret).cumprod()


def drawdown_exit(ret: pd.Series, limit: float) -> dict:
    """First session whose close sits ``limit`` below the running peak; the
    sleeve is flat from the next open, as in the paper runtime."""
    eq = equity(ret)
    dd = eq / eq.cummax() - 1.0
    hit = dd[dd <= -limit]
    if hit.empty:
        return {"triggered": False}
    day = hit.index[0]
    after = eq.loc[day:]
    return {
        "triggered": True,
        "exit_session": str(day.date()),
        "equity_at_exit": float(eq.loc[day]),
        "drawdown_at_exit": float(dd.loc[day]),
        "held_on_equity_end": float(eq.iloc[-1]),
        "held_on_worst_after_exit": float((after / eq.loc[day]).min() - 1.0),
        "held_on_back_to_exit_level": next(
            (str(d.date()) for d, v in after.iloc[1:].items() if v >= eq.loc[day]), None
        ),
    }


def episodes(ret: pd.Series, top: int = 5) -> list[dict]:
    """The deepest peak-to-trough drawdowns, each with its recovery date."""
    eq = equity(ret)
    peak = eq.cummax()
    dd = eq / peak - 1.0
    out, used = [], pd.Series(False, index=eq.index)
    for _ in range(top):
        free = dd[~used]
        if free.empty or free.min() >= 0:
            break
        trough = free.idxmin()
        start = eq.loc[:trough].idxmax()
        recovered = eq.loc[trough:][eq.loc[trough:] >= eq.loc[start]]
        end = recovered.index[0] if not recovered.empty else eq.index[-1]
        used.loc[start:end] = True
        out.append(
            {
                "peak": str(start.date()),
                "trough": str(trough.date()),
                "recovered": str(end.date()) if not recovered.empty else None,
                "depth": float(dd.loc[trough]),
            }
        )
    return out


def yearly(ret: pd.Series) -> dict[str, float]:
    return {str(y): float((1.0 + r).prod() - 1.0) for y, r in ret.groupby(ret.index.year)}


def main() -> int:
    base.WARMUP_START, base.HOLD_END = PANEL_START, REPORT_END
    close, open_ = base.load_panel(salvage.symbols())
    leg_open, leg_close = salvage.legs(close, open_)
    boost = salvage.boost_window(salvage.dip_signal(close), 10)
    cells = {
        "s3_vt40_boost": salvage.run_cell(
            close, leg_open, leg_close, "s3", 0.40, COST_BPS, boost=boost, boost_target=0.60
        ),
        "s3_no_overlay": salvage.run_cell(close, leg_open, leg_close, "s3", None, COST_BPS),
    }
    rf = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    mask = (close.index >= REPORT_START) & (close.index <= REPORT_END)
    result: dict = {
        "window": [REPORT_START, REPORT_END],
        "cost_bps": COST_BPS,
        "note": "risk disclosure only; frozen rules, no selection; pre-dates the select window",
        "cells": {},
        "benchmarks": {},
    }
    for name, (ret, turn) in cells.items():
        r = ret.loc[mask]
        m = base.metrics(r, rf, turn.loc[mask])
        result["cells"][name] = {
            "metrics": m.__dict__,
            "yearly": yearly(r),
            "episodes": episodes(r),
            "drawdown_exit_25": drawdown_exit(r, EXIT_DRAWDOWN),
        }
    for sym in ("QQQ", "TQQQ", "SOXL", "SPY"):
        r = close[sym].pct_change().loc[mask].fillna(0.0)
        m = base.metrics(r, rf, pd.Series(0.0, index=r.index))
        result["benchmarks"][sym] = {"metrics": m.__dict__, "yearly": yearly(r)}
    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / "2026-09-23-s3-stress-2016-2023"
    stem.with_suffix(".json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    stem.with_suffix(".md").write_text(render(result), encoding="utf-8")
    print(render(result))
    return 0


def pct(x: float | None) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.1f}%"


def render(result: dict) -> str:
    lines = [
        f"# S3 stress replay {result['window'][0]} .. {result['window'][1]}"
        f" ({result['cost_bps']:.0f} bp)",
        "",
        result["note"],
        "",
        "| series | CAGR | vol | Sharpe | max DD |",
        "|---|---|---|---|---|",
    ]
    rows = {**result["cells"], **result["benchmarks"]}
    for name, body in rows.items():
        m = body["metrics"]
        lines.append(
            f"| {name} | {pct(m['cagr'])} | {pct(m['vol'])} | {m['sharpe']:.2f}"
            f" | {pct(m['max_dd'])} |"
        )
    years = sorted(next(iter(rows.values()))["yearly"])
    lines += ["", "| year | " + " | ".join(rows) + " |", "|---" * (len(rows) + 1) + "|"]
    for y in years:
        lines.append(
            f"| {y} | " + " | ".join(pct(b["yearly"].get(y)) for b in rows.values()) + " |"
        )
    for name, body in result["cells"].items():
        lines += ["", f"## {name}", "", "Deepest drawdowns:", ""]
        for e in body["episodes"]:
            lines.append(
                f"- {e['peak']} -> {e['trough']}: {pct(e['depth'])}, "
                f"recovered {e['recovered'] or 'not by window end'}"
            )
        x = body["drawdown_exit_25"]
        if x["triggered"]:
            lines += [
                "",
                f"25% exit: fires on {x['exit_session']} (drawdown {pct(x['drawdown_at_exit'])}); "
                f"equity multiple at exit {x['equity_at_exit']:.2f}; holding on instead would have "
                f"fallen a further {pct(x['held_on_worst_after_exit'])} and regained the exit "
                f"level on {x['held_on_back_to_exit_level'] or 'no date in window'}.",
            ]
        else:
            lines += ["", "25% exit: never fires in this window."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
