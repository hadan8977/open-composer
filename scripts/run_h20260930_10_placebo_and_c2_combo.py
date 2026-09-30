"""H-20260930-10 (plan A1): random-shift placebo and C2 combination increment
for the six industry-seasonality cells, writing
reports/research/iterations/h20260930_10_industry_seasonality/results.json.

Frozen design: reports/research/iterations/h20260930_10_industry_seasonality/
hypotheses.md. Nothing here changes a gate, the universe, the grid or the
placebo shift set {2..9}.

  scripts/run_capped.sh --mem 1.5G -- uv run python \\
      scripts/run_h20260930_10_placebo_and_c2_combo.py

Engine = scripts/screen_lane.py unchanged (weights_frame + salvage.simulate,
10/20 bp per side, next-open fill). The panel is loaded to 2026-09-29 (the data
end named in hypotheses.md) instead of the lane's 2026-09-17; every return on a
date <= 2026-09-17 is unchanged, which is checked against the batch's
returns.parquet.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as b2  # noqa: E402
import h20260928_20_recent_opt as opt  # noqa: E402
import h20260930_10_industry_seasonality as ind  # noqa: E402
import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260922_05_salvage as salvage  # noqa: E402
import screen_lane as lane  # noqa: E402

from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402

IT = "h20260930_10_industry_seasonality"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / IT
SCREEN_DIR = ROOT / "reports" / "research" / "screens" / IT
S0_C2_RETURNS = (
    ROOT / "reports" / "research" / "screens" / "h20260928_20_recent_opt" / "returns.parquet"
)
DATA_END = "2026-09-29"
SEEDS = list(range(1, 21))
STAGE1_SHARPE = 1.19
STAGE1_BEAT_MAX = 0.10
STAGE2_EDGE_MIN = 0.05
K1_ANCHOR, K1_STRESS = 1.19, 0.65
PLACEBO_CACHE = SCREEN_DIR / "placebo_raw.json"


def cand(cid: str, name: str, fn, universe) -> lane.ScreenCandidate:
    return lane.ScreenCandidate(
        id=cid,
        name=name,
        source_card="h20260930_10",
        universe=tuple(universe),
        freq="D",
        weights_fn=fn,
        signal_dates_fn=b2.month_end_signal_dates,
    )


def sim(close, leg_open, leg_close, c: lane.ScreenCandidate, cost: float):
    weights, _ = lane.weights_frame(close, c, 0)
    return salvage.simulate(weights, leg_open, leg_close, np.ones(len(close.index)), cost)


def wm(ret, turn, rf, window):
    mask = (ret.index >= window[0]) & (ret.index <= window[1])
    m = base.metrics(ret.loc[mask], rf, turn.loc[mask])
    return {"days": m.days, "sharpe": m.sharpe, "cagr": m.cagr, "max_dd": m.max_dd}


def corr_in(a_ser: pd.Series, b_ser: pd.Series, window) -> float:
    idx = a_ser.index[(a_ser.index >= window[0]) & (a_ser.index <= window[1])]
    return float(a_ser.loc[idx].corr(b_ser.loc[idx]))


def main() -> None:
    real = [
        cand(
            cid,
            f"real {cid}",
            opt.make_sector_seasonality_fn(universe=ind.INDUSTRY_ETFS, top_n=k, avg_years=y),
            ind.INDUSTRY_ETFS,
        )
        for cid, k, y in ind.GRID
    ]
    c2c = cand("C2", "C2", opt.make_c2_eom_sector_blend_fn(), ("SPY", *b2.SECTOR_ETFS))
    s0c = cand("S0", "S0", opt.make_sector_seasonality_fn(), b2.SECTOR_ETFS)
    base.HOLD_END = DATA_END
    close, _open, leg_open, leg_close, rf = lane.load_batch_panel([*real, c2c, s0c])
    print("panel", close.index.min().date(), close.index.max().date(), len(close), flush=True)
    shy_ret = (close[lane.CASH] / close[lane.CASH].shift(1) - 1.0).fillna(0.0)
    data_end = close.index[-1]
    win = {
        "anchor_lane": lane.WINDOWS["anchor"],
        "anchor_data_end": ("2024-01-08", str(data_end.date())),
        "select": lane.WINDOWS["select"],
        "holdout_2026": lane.WINDOWS["holdout"],
        "stress": lane.WINDOWS["stress"],
    }

    # ---- series: real cells, C2, S0 (10 and 20 bp) ----
    ser: dict[str, dict[str, tuple[pd.Series, pd.Series]]] = {}
    for c in [*real, c2c, s0c]:
        ser[c.id] = {
            "10": sim(close, leg_open, leg_close, c, lane.COST_BPS_PRIMARY),
            "20": sim(close, leg_open, leg_close, c, lane.COST_BPS_STRESS),
        }
        print("series", c.id, flush=True)

    # ---- consistency checks against the stored batch outputs ----
    prev = pd.read_parquet(S0_C2_RETURNS)
    new = pd.read_parquet(SCREEN_DIR / "returns.parquet")

    def maxdiff(a: pd.Series, b: pd.Series) -> float:
        idx = a.index.intersection(b.index)
        return float((a.loc[idx] - b.loc[idx]).abs().max())

    consistency = {
        "c2_net10_vs_h20260928_20": maxdiff(ser["C2"]["10"][0], prev["C2__o00__net10"]),
        "c2_net20_vs_h20260928_20": maxdiff(ser["C2"]["20"][0], prev["C2__o00__net20"]),
        "s0_net10_vs_h20260928_20": maxdiff(ser["S0"]["10"][0], prev["S0__o00__net10"]),
        "overlap_days_c2": int(len(ser["C2"]["10"][0].index.intersection(prev.index))),
        "overlap_end": str(prev.index.max().date()),
        "threshold": 1e-9,
    }
    for c in real:
        consistency[f"{c.id}_net10_vs_batch"] = maxdiff(
            ser[c.id]["10"][0], new[f"{c.id}__o00__net10"]
        )
        consistency[f"{c.id}_net20_vs_batch"] = maxdiff(
            ser[c.id]["20"][0], new[f"{c.id}__o00__net20"]
        )
    consistency["all_pass"] = bool(
        all(
            v < 1e-9
            for k, v in consistency.items()
            if k.endswith(("_vs_h20260928_20", "_vs_batch"))
        )
    )
    print("consistency", consistency, flush=True)

    board = {
        r["id"]: r for r in json.loads((SCREEN_DIR / "leaderboard.json").read_text())["candidates"]
    }

    # ---- placebo (cached per cell) ----
    cache = json.loads(PLACEBO_CACHE.read_text()) if PLACEBO_CACHE.exists() else {}
    for cid, k, y in ind.GRID:
        if cid in cache:
            continue
        rows = []
        for seed in SEEDS:
            pc = cand(
                f"{cid}_P{seed}",
                "placebo",
                ind.make_shift_placebo_fn(top_n=k, avg_years=y, seed=seed),
                ind.INDUSTRY_ETFS,
            )
            r10, t10 = sim(close, leg_open, leg_close, pc, lane.COST_BPS_PRIMARY)
            rows.append(
                {
                    "seed": seed,
                    "anchor_data_end_sharpe": wm(r10, t10, rf, win["anchor_data_end"])["sharpe"],
                    "anchor_lane_sharpe": wm(r10, t10, rf, win["anchor_lane"])["sharpe"],
                }
            )
        cache[cid] = rows
        PLACEBO_CACHE.write_text(json.dumps(cache, indent=2))
        print("placebo", cid, "done", flush=True)

    # ---- assemble ----
    cells = {}
    s0_10 = ser["S0"]["10"][0]
    c2_10 = ser["C2"]["10"][0]
    for cid, k, y in ind.GRID:
        r10, t10 = ser[cid]["10"]
        r20, t20 = ser[cid]["20"]
        m10 = {w: wm(r10, t10, rf, win[w]) for w in win}
        m20 = {w: wm(r20, t20, rf, win[w]) for w in win}
        lb = board[cid]
        seeds10 = [row["anchor_data_end_sharpe"] for row in cache[cid]]
        seedsL = [row["anchor_lane_sharpe"] for row in cache[cid]]
        real_de = m10["anchor_data_end"]["sharpe"]
        real_ln = m10["anchor_lane"]["sharpe"]
        beat_de = float(np.mean([s >= real_de for s in seeds10]))
        beat_ln = float(np.mean([s >= real_ln for s in seedsL]))
        # C2 combination: lane.diversifier_edge_for_offset with C2 in the S3 slot
        edge = {
            w: lane.diversifier_edge_for_offset(c2_10, r10, shy_ret, rf, win[w])
            for w in ("anchor_data_end", "anchor_lane", "stress")
        }

        # correlation with S0
        stage1 = {
            "sharpe_ge_1.19": bool(real_de >= STAGE1_SHARPE),
            "cagr20_gt_0": bool(m20["anchor_data_end"]["cagr"] > 0),
            "placebo_beat_le_10pct": bool(beat_de <= STAGE1_BEAT_MAX),
        }
        stage1_lane = {
            "sharpe_ge_1.19": bool(real_ln >= STAGE1_SHARPE),
            "cagr20_gt_0": bool(m20["anchor_lane"]["cagr"] > 0),
            "placebo_beat_le_10pct": bool(beat_ln <= STAGE1_BEAT_MAX),
        }
        s1 = all(stage1.values())
        s1_lane = all(stage1_lane.values())
        s2_flags = {
            "anchor_ge_0.05": bool(edge["anchor_data_end"] >= STAGE2_EDGE_MIN),
            "stress_ge_0.05": bool(edge["stress"] >= STAGE2_EDGE_MIN),
        }
        ex = (r10 - rf.reindex(r10.index).fillna(0.0)).loc[
            (r10.index >= lane.WINDOWS["anchor"][0]) & (r10.index <= lane.WINDOWS["anchor"][1])
        ]
        ex = ex.loc[ex.index >= pd.Timestamp(lb["first_valid_signal_date"])].to_numpy()
        dsr6 = float(deflated_sharpe_probability(ex, trial_count=6, hac_lag=lane.DSR_HAC_LAG))
        dsr16 = float(deflated_sharpe_probability(ex, trial_count=16, hac_lag=lane.DSR_HAC_LAG))
        k1 = {
            "anchor_sharpe_ge_1.19": bool(real_ln >= K1_ANCHOR),
            "stress_sharpe_ge_0.65": bool(m10["stress"]["sharpe"] >= K1_STRESS),
            "cagr20_anchor_gt_0": bool(m20["anchor_lane"]["cagr"] > 0),
            "cagr20_stress_gt_0": bool(m20["stress"]["cagr"] > 0),
        }
        k2 = {
            "edge_anchor_vs_s3": lb["diversifier"]["anchor"]["judged_edge"],
            "edge_stress_vs_s3": lb["diversifier"]["stress"]["judged_edge"],
        }
        cells[cid] = {
            "top_n": k,
            "avg_years": y,
            "anchor_sharpe_10bp": real_de,
            "anchor_sharpe_10bp_lane_window_to_2026_09_17": real_ln,
            "anchor_cagr_10bp": m10["anchor_data_end"]["cagr"],
            "anchor_cagr_20bp": m20["anchor_data_end"]["cagr"],
            "anchor_cagr_20bp_lane_window": m20["anchor_lane"]["cagr"],
            "anchor_max_dd_10bp": m10["anchor_data_end"]["max_dd"],
            "stress_sharpe_10bp": m10["stress"]["sharpe"],
            "stress_cagr_20bp": m20["stress"]["cagr"],
            "select_sharpe_10bp": m10["select"]["sharpe"],
            "holdout_2026_sharpe": m10["holdout_2026"]["sharpe"],
            "placebo_seed_sharpes": seeds10,
            "placebo_seed_sharpes_lane_window": seedsL,
            "placebo_mean": float(np.mean(seeds10)),
            "placebo_max": float(np.max(seeds10)),
            "placebo_beat_fraction": beat_de,
            "placebo_beat_fraction_lane_window": beat_ln,
            "stage1_conditions": stage1,
            "stage1_conditions_lane_window": stage1_lane,
            "stage1_pass": s1,
            "stage1_pass_lane_window": s1_lane,
            "c2_combo_edge_anchor": edge["anchor_data_end"],
            "c2_combo_edge_anchor_lane_window": edge["anchor_lane"],
            "c2_combo_edge_stress": edge["stress"],
            "stage2_conditions": s2_flags,
            "stage2_pass": bool(s1 and all(s2_flags.values())),
            "corr_with_S0_anchor": corr_in(r10, s0_10, win["anchor_data_end"]),
            "corr_with_S0_stress": corr_in(r10, s0_10, win["stress"]),
            "K1": k1,
            "K1_pass": bool(all(k1.values())),
            "K2_vs_S3": k2,
            "K2_vs_S3_pass": bool(all(v >= 0.05 for v in k2.values())),
            "dsr_n6": dsr6,
            "dsr_n6_leaderboard": lb["dsr_anchor"],
            "dsr_n16": dsr16,
        }
    passing = [cid for cid, v in cells.items() if v["stage2_pass"]]
    stage1_cells = [cid for cid, v in cells.items() if v["stage1_pass"]]
    rep = max(passing, key=lambda i: cells[i]["select_sharpe_10bp"]) if passing else None
    out = {
        "iter_id": IT,
        "windows": win,
        "data_end": str(data_end.date()),
        "note_windows": (
            "hypotheses.md names the anchor as 2024-01-08 -> 2026-09-29; screen_lane's frozen"
            " anchor ends 2026-09-17. Stage 1 fields without a suffix use the data-end window;"
            " *_lane_window fields use the lane window (= leaderboard.json)."
        ),
        "c2_series_consistency_check": consistency,
        "stage1_cells": stage1_cells,
        "stage2_pass_cells": passing,
        "representative_cell": rep,
        "cells": cells,
    }
    (ITER_DIR / "results.json").write_text(json.dumps(out, indent=2, default=float))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
