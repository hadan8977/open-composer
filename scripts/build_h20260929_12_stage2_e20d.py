"""T-20260929-12 Stage 2: walk-forward stress check for E20D (the only Stage 1
candidate that passed: hedged forms b/bp both cleared edge>=+0.05,
standalone Sharpe>0, correlation with S3<0.3 in 2024-01-02..2026-09-08).

Per the brief: "Redo the selection with yearly expanding windows: select at
each year-end from 2017-12 using all IC data since 2016-06. This makes
2018-01->2023-09 pseudo-out-of-sample." Re-derives BOTH the factor selection
(top-40-by-|ICIR| -> greedy corr-dedup top-20, reusing
``build_h20260929_12_ensembles.greedy_dedup`` unmodified) AND each factor's
sign at every year-end cutoff, using only IC data up to that cutoff -- no
2024+ data, and for a given holding year no data from later years either.

DISCLOSED SIMPLIFICATION: the walk-forward candidate UNIVERSE is bounded to
the same top-40 pool already computed for Stage 1 (``e40_ids`` in
ensemble-build.json), not the full 263-candidate zoo. That pool was itself
chosen using the full 2016-2023 select window (which overlaps the 2018-2023
Stage 2 window), so Stage 2 is the "pseudo-out-of-sample" re-selection check
the brief itself names it -- a re-weighting/re-dedup stress test bounded to
an already-identified pool, not a fully independent from-scratch walk-forward
factor discovery. This bound keeps the 40 factors' raw signals cached in
memory (reused across all 6 cutoffs) instead of reloading 263 candidates x 6
cutoffs from disk.

Reuses ``open_composer.research.signal_card`` (``load_market``, ``rank_ic``,
``percentile_ranks``) and ``run_h20260928_15_factor_batch._load_candidate``
unmodified, ``build_h20260929_12_ensembles.greedy_dedup`` unmodified, and
``run_h20260929_12_hedged_books`` (``load_etf_panel``, ``build_top50_weights``,
``hedge_weight_series``, ``simulate_book``, ``build_hedged_book``,
``stock_legs``, ``window_metrics``, ``HEDGE_PAIRS``, ``OFFSETS``) unmodified
-- the same close-to-close leg-mixing engine ``run_h20260929_12_hedged_books``
uses (2026-09-29 fix, superseding an earlier open-to-open convention;
see that module's docstring).

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260929_12_stage2_e20d.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_h20260929_12_ensembles as build_mod  # noqa: E402
import run_h20260929_12_hedged_books as books_mod  # noqa: E402
import screen_lane  # noqa: E402

from open_composer.research.signal_card import (  # noqa: E402
    load_market,
    percentile_ranks,
    rank_ic,
)

ITER_DIR = ROOT / "reports/research/iterations/h20260929_12_hedged_factor_ensemble"
EXPANDING_START = "2016-06-01"
CUTOFF_YEARS = [2017, 2018, 2019, 2020, 2021, 2022]  # holding years 2018..2023(partial)
STAGE2_WINDOW = ("2018-01-02", "2023-09-15")
STAGE2_PASS_EDGE_MIN = 0.05


def _log(msg: str, t0: float) -> None:
    print(f"[h20260929_12_stage2] {msg} ({time.monotonic() - t0:.0f}s)", flush=True)


def year_end_cutoff(dates: pd.DatetimeIndex, year: int) -> pd.Timestamp:
    in_year_dec = dates[(dates.year == year) & (dates.month == 12)]
    return in_year_dec.max()


def expanding_icir_sign(ic_series: np.ndarray, dates: pd.DatetimeIndex, cutoff: pd.Timestamp):
    mask = (dates >= pd.Timestamp(EXPANDING_START)) & (dates <= cutoff)
    sub = ic_series[mask]
    sub = sub[np.isfinite(sub)]
    if len(sub) < 30:
        return None, None
    mean = float(sub.mean())
    sd = float(sub.std(ddof=1))
    icir = mean / sd if sd > 0 else None
    sign = 1 if mean >= 0 else -1
    return icir, sign


def score_from_cache(
    chosen: list[tuple[str, int]], raw_cache: dict[str, np.ndarray], member: np.ndarray
) -> np.ndarray:
    """Same tolerant-average convention as
    ``build_h20260929_12_ensembles.build_equal_weight_score``, but reads
    already-loaded raw arrays instead of re-hitting disk (reused across all
    6 cutoffs)."""
    shape = member.shape
    total = np.zeros(shape, dtype=np.float64)
    count = np.zeros(shape, dtype=np.int32)
    for cid, sign in chosen:
        pct = percentile_ranks(raw_cache[cid] * sign, member)
        finite = np.isfinite(pct)
        total[finite] += pct[finite]
        count[finite] += 1
    min_known = max(1, int(np.ceil(len(chosen) * build_mod.MIN_FRAC_KNOWN)))
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(count >= min_known, total / np.maximum(count, 1), np.nan)
    return score.astype(np.float32)


def main() -> int:
    t0 = time.monotonic()
    market = load_market(top_n=1000, memory_limit="1200MB")
    _log(f"market loaded: {len(market.dates)} x {len(market.symbols)}", t0)
    member = market.member()
    fwd21 = market.forward_returns(21)

    build_info = json.loads((ITER_DIR / "ensemble-build.json").read_text(encoding="utf-8"))
    pool40_ids = build_info["e40_ids"]
    _log(f"pool40 ids loaded from Stage 1: {len(pool40_ids)}", t0)

    raw_cache: dict[str, np.ndarray] = {}
    ic_cache: dict[str, np.ndarray] = {}
    for cid in pool40_ids:
        raw = build_mod.t15._load_candidate(market, cid)
        raw_cache[cid] = raw
        ic_cache[cid] = rank_ic(raw, fwd21, member)
        _log(f"cached raw+ic for {cid}", t0)

    year_scores: dict[int, np.ndarray] = {}
    selection_log: dict[str, dict] = {}
    for year in CUTOFF_YEARS:
        cutoff = year_end_cutoff(market.dates, year)
        ranked_at_cutoff = []
        for cid in pool40_ids:
            icir, sign = expanding_icir_sign(ic_cache[cid], market.dates, cutoff)
            if icir is None:
                continue
            ranked_at_cutoff.append((cid, icir, sign))
        ranked_at_cutoff.sort(key=lambda t: -abs(t[1]))

        expanding_mask = (market.dates >= pd.Timestamp(EXPANDING_START)) & (market.dates <= cutoff)
        top40_at_cutoff = ranked_at_cutoff[: build_mod.R40_POOL]
        pct_cache_cutoff = {
            cid: percentile_ranks(raw_cache[cid] * sign, member)[expanding_mask]
            for cid, _icir, sign in top40_at_cutoff
        }
        chosen = build_mod.greedy_dedup(top40_at_cutoff, pct_cache_cutoff, k=20)
        selection_log[str(year)] = {
            "cutoff": str(cutoff.date()),
            "chosen_ids": [c for c, _s in chosen],
            "chosen_count": len(chosen),
        }
        _log(f"year {year} cutoff={cutoff.date()} chosen={len(chosen)} factors", t0)

        score_full = score_from_cache(chosen, raw_cache, member)
        holding_year = year + 1
        year_scores[holding_year] = score_full

    T, N = member.shape
    wf_score = np.full((T, N), np.nan, dtype=np.float32)
    for holding_year, score_full in year_scores.items():
        year_mask = market.dates.year == holding_year
        wf_score[year_mask] = score_full[year_mask]
    _log("walk-forward score assembled", t0)

    SCORE_DIR = ITER_DIR / "scores"
    np.savez_compressed(
        SCORE_DIR / "E20D_WF.npz",
        dates=market.dates.to_numpy(),
        symbols=market.symbols.to_numpy(dtype=object),
        score=wf_score,
    )
    _log("wrote E20D_WF.npz", t0)

    # ---- Stage 2 hedged-book evaluation, forms b/bp only ----
    panel = books_mod.load_etf_panel()
    close, leg_open, leg_close = panel["close"], panel["leg_open"], panel["leg_close"]
    rf, shy_ret = panel["rf"], panel["shy_ret"]
    s3_ret10, _t = screen_lane.s3_incumbent(close, leg_open, leg_close, books_mod.COST_BPS_PRIMARY)
    unified_index = market.dates.intersection(close.index)
    stock_pos = market.dates.get_indexer(unified_index)
    score_u = wf_score[stock_pos]

    # CLOSE-TO-CLOSE LEG-MIXING ENGINE (2026-09-29, mirrors
    # run_h20260929_12_hedged_books.py's second, deeper convention fix): S3
    # (screen_lane.s3_incumbent -> salvage.simulate) splits every rebalance
    # day at the open (old weights earn the overnight gap, new weights earn
    # the intraday move), so its own row t is a CLOSE-TO-CLOSE realized
    # return, not open-to-open. This script now builds the stock/hedge legs
    # with books_mod.stock_legs/simulate_book/build_hedged_book -- the exact
    # same engine run_h20260929_12_hedged_books.py uses -- so both scripts
    # land on the identical convention as S3 with no relabeling step.
    mkt_open_u = market.open_[stock_pos].astype(np.float64)
    mkt_close_u = market.close[stock_pos].astype(np.float64)
    stock_leg_open_u, stock_leg_close_u = books_mod.stock_legs(mkt_open_u, mkt_close_u)
    underlying_ret_cc = {
        sym: (close[sym] / close[sym].shift(1) - 1.0).reindex(unified_index)
        for sym in ("SPY", "QQQ")
    }
    hedge_leg_open_map = {
        sym: leg_open[sym].reindex(unified_index).to_numpy() for sym in ("SH", "PSQ")
    }
    hedge_leg_close_map = {
        sym: leg_close[sym].reindex(unified_index).to_numpy() for sym in ("SH", "PSQ")
    }

    results = {}
    for form, (hsym, usym) in books_mod.HEDGE_PAIRS.items():
        u_ret = underlying_ret_cc[usym].to_numpy()
        h_leg_open = hedge_leg_open_map[hsym]
        h_leg_close = hedge_leg_close_map[hsym]
        edge_by_offset, sharpe_by_offset, corr_by_offset = {}, {}, {}
        for off in books_mod.OFFSETS:
            raw_w, _skipped = books_mod.build_top50_weights(
                score_u, unified_index, off, books_mod.TOP_K, books_mod.MIN_ELIGIBLE
            )
            raw_w64 = raw_w.astype(np.float64)
            a_net10, _turn = books_mod.simulate_book(
                raw_w64, stock_leg_open_u, stock_leg_close_u, books_mod.COST_BPS_PRIMARY
            )
            sig_dates = books_mod.tranche.shifted_signal_dates(unified_index, off)
            hedge_w, stock_scale = books_mod.hedge_weight_series(
                a_net10,
                u_ret,
                unified_index,
                sig_dates,
                books_mod.HEDGE_LOOKBACK,
                books_mod.HEDGE_BETA_CAP,
            )
            net10, _turn2 = books_mod.build_hedged_book(
                raw_w64,
                stock_leg_open_u,
                stock_leg_close_u,
                h_leg_open,
                h_leg_close,
                hedge_w,
                stock_scale,
                books_mod.COST_BPS_PRIMARY,
            )
            s = pd.Series(net10, index=unified_index)
            m = books_mod.window_metrics(s, rf, pd.Series(0.0, index=unified_index), STAGE2_WINDOW)
            sharpe_by_offset[off] = m.sharpe
            edge_by_offset[off] = screen_lane.diversifier_edge_for_offset(
                s3_ret10, s, shy_ret, rf, STAGE2_WINDOW
            )
            corr_by_offset[off] = screen_lane.correlation_with_s3(s, s3_ret10, STAGE2_WINDOW)
        results[form] = {
            "sharpe_by_offset": sharpe_by_offset,
            "sharpe_median": float(np.median(list(sharpe_by_offset.values()))),
            "edge_by_offset": edge_by_offset,
            "edge_median": float(np.median(list(edge_by_offset.values()))),
            "correlation_with_s3_by_offset": corr_by_offset,
            "correlation_with_s3_median": float(np.nanmedian(list(corr_by_offset.values()))),
        }
        _log(f"stage2 form {form} done: edge_median={results[form]['edge_median']:.4f}", t0)

    stage2_pass = all(results[form]["edge_median"] >= STAGE2_PASS_EDGE_MIN for form in ("b", "bp"))
    payload = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "stage2_window": list(STAGE2_WINDOW),
        "candidate_universe_note": "bounded to Stage 1's top-40 pool (e40_ids); "
        "see module docstring",
        "selection_by_year": selection_log,
        "results": results,
        "stage2_pass": stage2_pass,
    }
    out_path = ITER_DIR / "stage2-results.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    _log(f"wrote {out_path}, stage2_pass={stage2_pass}", t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
