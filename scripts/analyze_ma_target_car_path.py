"""T-20260929-03 diagnostic: cumulative excess return path around merger-target 8-Ks.

Companion to the ``signal_card`` event cards. It answers what the card does not
show: how much of the target premium was earned BEFORE the 8-K (leakage, days
-5..-1), on the reaction day (day 0), in the after-hours gap missed by a
next-open entry, and day by day after the entry. Same universe, membership,
price hygiene (via ``signal_card.load_market``) and excess definition (return
minus the equal-weight universe mean on the same rows) as the card.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/analyze_ma_target_car_path.py \\
        --out reports/research/iterations/h20260929_03_ma_target_drift
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.research.signal_card import TIER_EDGES, load_market  # noqa: E402

EVENTS = ROOT / "data" / "features" / "sec_8k_ma_announcements"
POST_HORIZONS = (1, 2, 5, 10, 20, 60)


def mean_t(values: np.ndarray) -> dict:
    v = values[np.isfinite(values)]
    if len(v) < 3:
        return {"n": int(len(v))}
    sd = float(v.std(ddof=1))
    return {
        "n": int(len(v)),
        "mean": float(v.mean()),
        "median": float(np.median(v)),
        "t": float(v.mean() / (sd / math.sqrt(len(v)))) if sd > 0 else None,
        "hit": float((v > 0).mean()),
    }


def excess_matrix(ret: np.ndarray, member: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        return ret - np.nanmean(np.where(member, ret, np.nan), axis=1, keepdims=True)


def path_stats(
    rows: np.ndarray,
    cols: np.ndarray,
    close_ex: np.ndarray,
    fwd_ex: dict[int, np.ndarray],
    gap_ex: np.ndarray,
) -> dict:
    """Mean excess returns by window for events at (rows, cols)."""
    out: dict = {}
    for name, lo, hi in (("pre_m20_m6", -20, -6), ("pre_m5_m1", -5, -1)):
        acc = np.zeros(len(rows))
        for k in range(lo, hi + 1):
            idx = np.clip(rows + k, 0, len(close_ex) - 1)
            acc += close_ex[idx, cols]
        out[name] = mean_t(acc)
    out["day0_close_to_close"] = mean_t(close_ex[rows, cols])
    out["gap_close0_to_open1"] = mean_t(gap_ex[rows, cols])
    for h, ex in fwd_ex.items():
        out[f"post_h{h}"] = mean_t(ex[rows, cols])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top-n", type=int, default=3000)
    args = ap.parse_args()
    ev = pd.concat(pd.read_parquet(p) for p in sorted(EVENTS.glob("*.parquet")))
    ev = ev[ev["is_target_rule"] & ev["is_first_for_cik_365d"]].copy()
    market = load_market(args.top_n)
    member = market.member()
    date_idx = market.dates.get_indexer(pd.to_datetime(ev["trade_date"]))
    sym_idx = market.symbols.get_indexer(ev["symbol"])
    ev["row"], ev["col"] = date_idx, sym_idx
    ev["year"] = pd.to_datetime(ev["trade_date"]).dt.year
    in_member = np.zeros(len(ev), dtype=bool)
    ok = (date_idx >= 0) & (sym_idx >= 0)
    in_member[ok] = member[date_idx[ok], sym_idx[ok]]
    coverage = pd.DataFrame(
        {
            "target_events": ev.groupby("year").size(),
            "symbol_in_panel": ev[sym_idx >= 0].groupby("year").size(),
            "in_tradable_universe": ev[in_member].groupby("year").size(),
        }
    ).fillna(0)
    coverage["mapped_share"] = coverage["in_tradable_universe"] / coverage["target_events"]
    ev = ev[(ev["row"] >= 25) & (ev["col"] >= 0) & (ev["row"] < len(market.dates) - 62)]
    ev = ev[member[ev["row"].to_numpy(), ev["col"].to_numpy()]]
    close_ret = np.full_like(market.close, np.nan)
    close_ret[1:] = market.close[1:] / market.close[:-1] - 1.0
    gap = np.full_like(market.close, np.nan)
    gap[:-1] = market.open_[1:] / market.close[:-1] - 1.0
    close_ex = excess_matrix(close_ret, member)
    gap_ex = excess_matrix(gap, member)
    fwd_ex = {h: excess_matrix(market.forward_returns(h), member) for h in POST_HORIZONS}
    tiers = {"all": member, **{f"t{i + 1}": market.member(t) for i, t in enumerate(TIER_EDGES)}}
    result: dict = {
        "events_by_year": {str(y): int(n) for y, n in ev.groupby("year").size().items()},
        "events_total_in_universe": int(len(ev)),
        "coverage_by_year": coverage.round(3).to_dict(orient="index"),
        "by_tier": {},
        "by_year_post_h20": {},
    }
    rows_all, cols_all = ev["row"].to_numpy(), ev["col"].to_numpy()
    for name, tm in tiers.items():
        sel = tm[rows_all, cols_all]
        result["by_tier"][name] = path_stats(rows_all[sel], cols_all[sel], close_ex, fwd_ex, gap_ex)
    for y, g in ev.groupby("year"):
        r, c = g["row"].to_numpy(), g["col"].to_numpy()
        result["by_year_post_h20"][str(y)] = mean_t(fwd_ex[20][r, c])
    recent = ev["year"] >= 2024
    r, c = rows_all[recent.to_numpy()], cols_all[recent.to_numpy()]
    result["recent_2024_on"] = path_stats(r, c, close_ex, fwd_ex, gap_ex)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "car_path_diagnostic.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({k: result[k] for k in ("events_by_year", "events_total_in_universe")}))
    for name in ("all", "t3"):
        print(name, json.dumps(result["by_tier"][name]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
