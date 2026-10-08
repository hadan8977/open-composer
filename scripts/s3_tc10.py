"""S3 with the 10% semiconductor theme cap (S3-TC10): targets, parity with T-32, `today`.

Brief T-20261007-21. Imports the T-20261005-32 machinery (scripts/p2_theme_budget.py) and
does not copy its math: the cap itself is `cap_row`, the window/theme view is `ThemeView`.
This module only (1) lists the capped S3 risky weights per rebalance the way
`cap_variant` builds them, (2) proves they are bit-identical to `cap_variant`, and (3)
prints the capped target for the latest completed session of the daily archive.

    uv run python scripts/s3_tc10.py --stage parity
    uv run python scripts/s3_tc10.py --stage today

No orders, no broker, no paper-sleeve change.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import p2_theme_budget as p2  # noqa: E402
import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402

OUT = ROOT / "reports/research/program/s3-tc10-2026-10-08"
LEVEL = 0.10
T32_LAST_SESSION = "2026-10-05"
TOL = 1e-12
DAILY_SOURCE = "data/sip/daily/*/*.parquet (ghost bars dropped; the S3 paper job's archive)"


def code_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def capped_targets(
    ctx: Any, inst: Any = None, level: float = LEVEL, offset: int = 0
) -> dict[str, Any]:
    """Per rebalance start of S3 at `offset`: uncapped risky weights, TRS before, substitution
    fraction s, TRS after, capped weights. Same loop as `p2.cap_variant`.

    Returns {"rows": [...], "w": capped weight matrix (n x len(cols2))}."""
    inst = inst if inst is not None else ctx.insts[f"S3_{offset}"]
    view = ctx.views[p2.THEME]
    w = inst.w2.copy()
    n = len(w)
    risky_pos = [p for p, col in enumerate(inst.cols2) if col not in (p2.CASH, p2.RF)]
    starts = inst.starts
    rows = []
    for j, st in enumerate(starts):
        en = starts[j + 1] if j + 1 < len(starts) else n
        wk = np.zeros(ctx.K)
        wk[inst.kidx] = w[st]
        wk = p2.risky_k(ctx, wk)
        new, s, info = p2.cap_row(view, st - 1, wk, level, ctx.sub_k, ctx.cash_k)
        row = w[st].copy()
        if s > 0.0 or info["bound"]:
            row[risky_pos] = new[inst.kidx[risky_pos]]
            w[st:en] = row
        trs_before = float(info["trs"])
        rows.append(
            {
                "date": str(ctx.index[st - 1].date()),
                "start": int(st),
                "valid": bool(info["valid"]),
                "trs_before": trs_before,
                "bound": bool(info["bound"]),
                "s": float(s),
                "flag": bool(info["flag"]),
                "trs_after": float(info.get("trs_after", trs_before)),
                "weights_uncapped": {
                    inst.cols2[p]: float(inst.w2[st][p]) for p in range(len(inst.cols2))
                },
                "weights_capped": {inst.cols2[p]: float(row[p]) for p in range(len(inst.cols2))},
                "row": row,
            }
        )
    return {"rows": rows, "w": w}


def select_s3(ctx: Any, t: int) -> list[str]:
    """The S3 top-2 pick at signal row t, from the same config as `tranche.s3_weights`."""
    cfg = salvage.SLEEVES["s3"]
    menu = [s for s in base.MENUS[cfg["menu"]] if s in ctx.close.columns]
    score = base.momentum_score(ctx.close, cfg["lookback"])
    row = score.iloc[t][menu].dropna()
    if row.empty:
        return []
    chosen = list(row.sort_values(ascending=False).index[: cfg["top_n"]])
    cs = score.iloc[t][base.CASH]
    if np.isfinite(cs):
        chosen = [s for s in chosen if row[s] > cs]
    return chosen


def weights_for_picks(inst: Any, picks: list[str]) -> np.ndarray:
    """Weight row over inst.cols2: equal weight on the survivors, SHY when none."""
    row = np.zeros(len(inst.cols2))
    if not picks:
        row[inst.cols2.index(p2.CASH)] = 1.0
    else:
        for s in picks:
            row[inst.cols2.index(s)] = 1.0 / len(picks)
    return row


def target_at(ctx: Any, inst: Any, t: int, level: float = LEVEL) -> dict[str, Any]:
    """Capped S3 target as if row t were a signal session."""
    picks = select_s3(ctx, t)
    w_row = weights_for_picks(inst, picks)
    wk = np.zeros(ctx.K)
    wk[inst.kidx] = w_row
    wk = p2.risky_k(ctx, wk)
    new, s, info = p2.cap_row(ctx.views[p2.THEME], t, wk, level, ctx.sub_k, ctx.cash_k)
    out = w_row.copy()
    if s > 0.0 or info["bound"]:
        risky_pos = [p for p, col in enumerate(inst.cols2) if col not in (p2.CASH, p2.RF)]
        out[risky_pos] = new[inst.kidx[risky_pos]]
    trs_before = float(info["trs"])
    return {
        "picks": picks,
        "w_uncapped": w_row,
        "w_capped": out,
        "trs_before": trs_before,
        "s": float(s),
        "trs_after": float(info.get("trs_after", trs_before)),
        "valid": bool(info["valid"]),
        "bound": bool(info["bound"]),
        "flag": bool(info["flag"]),
    }


def stage_parity() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ctx = p2.load_context(T32_LAST_SESSION)
    inst = ctx.insts["S3_0"]
    view = ctx.views[p2.THEME]

    captured: dict[str, np.ndarray] = {}
    real_eff_of = p2.eff_of

    def spy(c: Any, i: Any, w2: np.ndarray) -> np.ndarray:
        captured["w"] = w2.copy()
        return real_eff_of(c, i, w2)

    p2.eff_of = spy
    try:
        ref = p2.cap_variant(ctx, inst, view, LEVEL)
    finally:
        p2.eff_of = real_eff_of
    ref_w = captured["w"]

    mine = capped_targets(ctx, inst, LEVEL, 0)
    rows = mine["rows"]
    diffs = [float(np.abs(r["row"] - ref_w[r["start"]]).max()) for r in rows]
    w_diff = float(np.abs(mine["w"] - ref_w).max())
    eff_mine = p2.eff_of(ctx, inst, mine["w"])
    eff_diff = float(np.abs(eff_mine - ref["eff2"]).max())

    keys = ("date", "valid", "trs", "bound", "val", "flag")
    mine_events = [
        {
            "date": r["date"],
            "valid": r["valid"],
            "trs": r["trs_before"],
            "bound": r["bound"],
            "val": r["s"],
            "flag": r["flag"],
        }
        for r in rows
    ]

    def same(a: dict[str, Any], b: dict[str, Any]) -> bool:
        for k in keys:
            x, y = a[k], b[k]
            if isinstance(x, float) and isinstance(y, float):
                if not ((np.isnan(x) and np.isnan(y)) or x == y):
                    return False
            elif x != y:
                return False
        return True

    events_equal = len(mine_events) == len(ref["events"]) and all(
        same(a, b) for a, b in zip(mine_events, ref["events"], strict=True)
    )

    # selection check: the standalone pick used by `today` reproduces the S3 weights
    sel_bad = 0
    for r in rows:
        t = r["start"] - 1
        pick_row = weights_for_picks(inst, select_s3(ctx, t))
        if np.abs(pick_row - inst.w2[r["start"]]).max() > TOL:
            sel_bad += 1

    max_abs = max([*diffs, w_diff, eff_diff])
    n_bound = sum(1 for r in rows if r["bound"])
    res = {
        "stage": "parity",
        "run_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_commit": code_commit(),
        "t32_last_session": T32_LAST_SESSION,
        "level": LEVEL,
        "offset": 0,
        "rebalance_rows": len(rows),
        "bound_rows": n_bound,
        "max_abs_diff_rows": max(diffs) if diffs else None,
        "max_abs_diff_matrix": w_diff,
        "max_abs_diff_effective": eff_diff,
        "max_abs_diff": max_abs,
        "events_identical": bool(events_equal),
        "select_mismatch_rows": sel_bad,
        "tolerance": TOL,
        "pass": bool(max_abs <= TOL and events_equal and len(rows) > 100 and sel_bad == 0),
    }
    (OUT / "parity.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0 if res["pass"] else 1


def latest_session() -> str:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    d = con.execute(
        "SELECT max(timestamp::DATE) FROM read_parquet(?) WHERE symbol = 'SPY' AND volume > 0",
        [str(ROOT / base.DAILY_GLOB)],
    ).fetchone()[0]
    con.close()
    return str(d)


def stage_today(prices: str | None) -> int:
    if prices:
        raise SystemExit(
            "--prices is accepted for the brief's interface, but the S3 paper job's own "
            "archive (data/sip/daily) feeds ThemeView, so only the default source is wired"
        )
    OUT.mkdir(parents=True, exist_ok=True)
    last = latest_session()
    ctx = p2.load_context(last)
    inst = ctx.insts["S3_0"]
    t = len(ctx.index) - 1
    data_last = str(ctx.index[t].date())
    tg = target_at(ctx, inst, t, LEVEL)
    cols = inst.cols2

    def as_dict(w: np.ndarray) -> dict[str, float]:
        return {cols[p]: float(w[p]) for p in range(len(cols)) if w[p] != 0.0}

    last_ts = ctx.index[t]
    nxt = last_ts + pd.offsets.BDay(1)
    rec = {
        "run_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_last_session": data_last,
        "data_source": DAILY_SOURCE,
        "s3_top2": tg["picks"],
        "weights_uncapped": as_dict(tg["w_uncapped"]),
        "trs_before": tg["trs_before"],
        "s": tg["s"],
        "trs_after": tg["trs_after"],
        "weights_capped": as_dict(tg["w_capped"]),
        "code_commit": code_commit(),
        "is_month_end_session": bool(nxt.month != last_ts.month),
        "note": "target if this session were the month-end signal session; vol target and "
        "dip boost are applied downstream",
    }
    with (OUT / "shadow-log.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=["parity", "today"], required=True)
    ap.add_argument("--prices", default=None)
    a = ap.parse_args(argv)
    if a.stage == "parity":
        return stage_parity()
    return stage_today(a.prices)


if __name__ == "__main__":
    raise SystemExit(main())
