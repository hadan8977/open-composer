"""Diagnostic for the live C2 sleeve: random-shift placebo on S0 (9 sector
SPDRs, top-2, 1-year score) and on C2 (E0 leg fixed, S leg replaced by the
same-seed S0 placebo). Preregistered in
reports/research/iterations/h20260930_10_industry_seasonality/s0-placebo-preregistration.md.

    scripts/run_capped.sh --mem 1.5G -- uv run python scripts/run_h20260930_10_s0_c2_placebo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as b2  # noqa: E402
import h20260928_20_recent_opt as opt  # noqa: E402
import h20260930_10_industry_seasonality as ind  # noqa: E402
import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260930_10_placebo_and_c2_combo as runner  # noqa: E402
import screen_lane as lane  # noqa: E402

OUT = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "h20260930_10_industry_seasonality"
    / "s0-c2-placebo.json"
)
SEEDS = list(range(1, 101))


def c2_placebo_fn(seed: int):
    eom_fn = opt.make_eom_reversal_fn()
    s_fn = ind.make_shift_placebo_fn(universe=b2.SECTOR_ETFS, top_n=2, avg_years=1, seed=seed)

    def fn(close, asof):
        if not b2._is_month_end(close.index, asof):
            return {}
        out: dict[str, float] = {}
        for w_map in (eom_fn(close, asof) or {}, s_fn(close, asof) or {}):
            for sym, w in w_map.items():
                out[sym] = out.get(sym, 0.0) + 0.5 * w
        return out

    return fn


def main() -> None:
    c2_universe = ("SPY", *b2.SECTOR_ETFS)
    s0 = runner.cand("S0", "S0", opt.make_sector_seasonality_fn(), b2.SECTOR_ETFS)
    c2 = runner.cand("C2", "C2", opt.make_c2_eom_sector_blend_fn(), c2_universe)
    base.HOLD_END = runner.DATA_END
    close, _open, leg_open, leg_close, rf = lane.load_batch_panel([s0, c2])
    windows = {
        "anchor": ("2024-01-08", str(close.index[-1].date())),
        "select": lane.WINDOWS["select"],
        "holdout_2026": lane.WINDOWS["holdout"],
        "stress": lane.WINDOWS["stress"],
    }

    def sharpes(c):
        ret, turn = runner.sim(close, leg_open, leg_close, c, lane.COST_BPS_PRIMARY)
        return {k: runner.wm(ret, turn, rf, w)["sharpe"] for k, w in windows.items()}

    real = {"S0": sharpes(s0), "C2": sharpes(c2)}
    seeds: dict[str, list[dict[str, float]]] = {"S0": [], "C2": []}
    for seed in SEEDS:
        ps = runner.cand(
            f"S0_P{seed}",
            "placebo",
            ind.make_shift_placebo_fn(universe=b2.SECTOR_ETFS, top_n=2, avg_years=1, seed=seed),
            b2.SECTOR_ETFS,
        )
        pc = runner.cand(f"C2_P{seed}", "placebo", c2_placebo_fn(seed), c2_universe)
        seeds["S0"].append(sharpes(ps))
        seeds["C2"].append(sharpes(pc))
        if seed % 10 == 0:
            print("seed", seed, flush=True)

    summary = {}
    for name in ("S0", "C2"):
        summary[name] = {}
        for k in windows:
            vals = np.array([s[k] for s in seeds[name]], dtype=float)
            summary[name][k] = {
                "real_sharpe": real[name][k],
                "placebo_median": float(np.median(vals)),
                "placebo_p90": float(np.quantile(vals, 0.9)),
                "beat_fraction": float(np.mean(vals >= real[name][k])),
            }
    OUT.write_text(
        json.dumps(
            {
                "preregistration": "s0-placebo-preregistration.md",
                "windows": windows,
                "seeds": SEEDS,
                "placebo_shifts": list(ind.PLACEBO_SHIFTS),
                "summary": summary,
                "seed_sharpes": seeds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
