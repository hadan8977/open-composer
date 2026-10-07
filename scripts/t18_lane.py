# ruff: noqa: E501
"""T-20261006-18 lane runner: the eight ETF / calendar first-batch ids under the screen-lane contract.

    flock /tmp/oc-heavy.lock ./scripts/run_capped.sh --mem 1.2G -- uv run python scripts/t18_lane.py

Candidates = existing opex-week batch (20, unchanged) + existing pre-holiday batch (18, unchanged) + the new
rules of ``scripts/screen_batches/t20261006_18_library_lane.py`` (25).  ``n_trials`` for every DSR is the number
of candidates run here.  Placebo: 200 circular shifts (>= 126 sessions) of the candidate's whole weight path
against the returns, same simulator and costs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_batch as sb  # noqa: E402
import screen_lane as lane  # noqa: E402

ITER = "t20261006_18_library_batch1_lane"
OUT = ROOT / "reports/research/iterations/t20261006_18_library_batch1"
SEED = 20261006
N_PLACEBO = 200


def all_candidates():
    opex = sb.load_batch_module("h20260928_42_opex_week")
    prehol = sb.load_batch_module("h20260929_02_pre_holiday_etf")
    new = sb.load_batch_module("t20261006_18_library_lane")
    cands = list(opex.CANDIDATES) + list(prehol.CANDIDATES) + list(new.CANDIDATES)
    return cands, new.GROUPS


def anchor_sharpe(ret: pd.Series, rf: pd.Series, start: pd.Timestamp) -> float:
    a, b = start, pd.Timestamp(lane.WINDOWS["anchor"][1])
    sub = ret[(ret.index >= a) & (ret.index <= b)]
    ex = sub - rf.reindex(sub.index).fillna(0.0)
    sd = float(ex.std(ddof=1))
    return float(ex.mean() / sd * np.sqrt(252)) if sd > 0 else float("nan")


def v4_crash(ret: pd.Series, rf: pd.Series) -> dict:
    """Standard v2.1 V4 on the stress window: worst 21-session loss versus 5x (4x warning) the monthly realised vol."""
    a, b = (pd.Timestamp(x) for x in lane.WINDOWS["stress"])
    ex = (ret - rf.reindex(ret.index).fillna(0.0))[(ret.index >= a) & (ret.index <= b)]
    if len(ex) < 63:
        return {"n": int(len(ex))}
    roll = ex.rolling(21).sum()
    monthly_vol = float(ex.std(ddof=1) * np.sqrt(21))
    worst = float(roll.min())
    return {
        "worst_21d": worst,
        "monthly_vol": monthly_vol,
        "ratio": (-worst / monthly_vol) if monthly_vol > 0 else None,
        "veto": bool(monthly_vol > 0 and -worst > 5 * monthly_vol),
    }


def placebo(c, close, leg_open, leg_close, rf, real_sharpe: float, first_valid, rng) -> dict:
    w, _ = lane.weights_frame(close, c, 0)
    cols = list(w.columns)
    n = len(w)
    start = lane.window_actual_start(lane.WINDOWS["anchor"][0], first_valid)
    vals = []
    arr = w.to_numpy()
    for k in rng.integers(126, n - 126, size=N_PLACEBO):
        ws = pd.DataFrame(np.roll(arr, int(k), axis=0), index=w.index, columns=cols)
        ret, _t = salvage.simulate(ws, leg_open, leg_close, np.ones(n), lane.COST_BPS_PRIMARY)
        vals.append(anchor_sharpe(ret, rf, start))
    v = np.array(vals)
    v = v[np.isfinite(v)]
    return {
        "n": int(len(v)),
        "pct_below_real": float((v < real_sharpe).mean()) if len(v) else None,
        "placebo_mean": float(v.mean()) if len(v) else None,
        "placebo_p95": float(np.quantile(v, 0.95)) if len(v) else None,
    }


def main() -> None:
    cands, groups = all_candidates()
    ids = [c.id for c in cands]
    manifest = json.loads((OUT.parent / ITER / "candidate-manifest.json").read_text())
    mids = [x["candidate_id"] for x in manifest["candidates"]]
    if sorted(mids) != sorted(groups):
        raise SystemExit(f"manifest guard: manifest ids {mids} != groups {sorted(groups)}")
    for cid in ids:
        owners = [g for g, v in groups.items() if cid.startswith(tuple(v["prefix"]))]
        if len(owners) != 1:
            raise SystemExit(f"candidate {cid} belongs to {owners}, expected exactly one group")
    close, _o, leg_open, leg_close, rf = lane.load_batch_panel(cands)
    problems = sb.calendar_anchor_problems(close, cands)
    if problems:
        raise SystemExit("\n".join(problems))
    shy_ret = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    s3_ret10, _ = lane.s3_incumbent(close, leg_open, leg_close, lane.COST_BPS_PRIMARY)
    rng = np.random.default_rng(SEED)
    results = []
    shard, nshards = 0, 1
    if "--shard" in sys.argv:
        shard = int(sys.argv[sys.argv.index("--shard") + 1])
        nshards = int(sys.argv[sys.argv.index("--nshards") + 1])
    for c in cands[shard::nshards]:
        r = lane.evaluate_candidate(
            c,
            close=close,
            leg_open=leg_open,
            leg_close=leg_close,
            rf=rf,
            shy_ret=shy_ret,
            s3_ret10=s3_ret10,
            n_trials=len(cands),
        )
        if not r["skipped"]:
            rets10 = r.pop("_returns_net10_by_offset")
            r.pop("_returns_net20_by_offset")
            jo = r["judged"]["anchor"]["offset"]
            first_valid = pd.Timestamp(r["first_valid_signal_date"])
            real = anchor_sharpe(
                rets10[jo], rf, lane.window_actual_start(lane.WINDOWS["anchor"][0], first_valid)
            )
            r["circular_shift_placebo"] = placebo(
                c, close, leg_open, leg_close, rf, real, first_valid, rng
            )
            r["anchor_sharpe_recomputed"] = real
            r["v4_stress"] = v4_crash(rets10[jo], rf)
        results.append(r)
        print(
            c.id,
            "skipped" if r["skipped"] else f"anchor {r['judged']['anchor']['sharpe']:.2f}",
            flush=True,
        )
    out = {
        "iteration": ITER,
        "n_trials": len(cands),
        "groups": groups,
        "cost_bps": [lane.COST_BPS_PRIMARY, lane.COST_BPS_STRESS],
        "windows": {k: list(v) for k, v in lane.WINDOWS.items()},
        "candidates": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ("lane-results.json" if nshards == 1 else f"lane-results-shard{shard}.json")).write_text(
        json.dumps(out, indent=1, default=float)
    )
    print("wrote lane results shard", shard)


if __name__ == "__main__":
    main()
