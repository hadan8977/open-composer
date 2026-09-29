"""H-20260928-22: build B/L/P/R books and score the LLM-news-momentum-filter replication.

Card: reports/research/hypotheses/H-20260928-22-llm-news-momentum-filter.md;
reports/research/iterations/h20260928_22_llm_news_momentum_filter/{direction-review,
candidate-manifest}.json.

Replicates Anic, Barbon, Seiz and Zarattini (2025, arXiv:2510.26228) on Open Composer's
own PIT largest-500 universe, using ``open_composer.research.signal_card`` for the market
data engine (unchanged) and the DeepSeek scores produced by
``scripts/score_h20260928_22_news_momentum.py``.

Four candidates, one monthly (non-overlapping) rebalance schedule:

* ``B``: top decile (~50 names) of the PIT top-500 universe by momentum_252_21, equal
  weight -- no DeepSeek scores.
* ``L``: top-2-decile pool (~100 names), re-ranked by the DeepSeek ``L`` score, top m=50
  selected, weighted ``Wi = E * eta**score_i`` (E=1/50, eta=5), capped at 15% per stock and
  renormalized to sum 1.
* ``P``: identical mechanism to L, but each ticker's score is L's own score for a
  different, seeded-randomly-chosen ticker from the same month's pool (never its own).
  Needs no separate DeepSeek calls: 2026-09-28 pre-scoring amendment (candidate-manifest.json
  "amendments") -- this prompt carries no stock-specific numeric content, so scoring ticker
  A with ticker B's headlines is a byte-identical prompt to L's own call for ticker B in the
  same month, and P is exactly a within-month permutation of L's already-scored values via
  ``scorer.derangement_map``. Only defined for the CLEAN window (formations >= 2026-05-29).
* ``R``: 5 seeded uniform-random 50-name selections from the same top-2-decile pool,
  equal weight; no DeepSeek calls. Reported as the per-seed median of each performance
  metric ("R-median").

Weights are held flat from the session after each month-end formation through the session
of the NEXT formation (inclusive) -- i.e. decided at formation close, effective at the
next session's open, per this repo's frozen next-open-fill convention
(``open_composer.research.signal_card.book_returns``).

    ./scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260928_22_news_momentum.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import score_h20260928_22_news_momentum as scorer  # noqa: E402

from open_composer.research.signal_card import (  # noqa: E402
    book_returns,
    load_market,
    load_signal,
    perf,
)

ITER_ID = "h20260928_22_llm_news_momentum_filter"
OUT_DIR = ROOT / "reports/research/iterations" / ITER_ID
SCORES_PATH = ROOT / "data/features/h20260928_22_news_momentum_scores/items.parquet"

TOP_N_UNIVERSE = 500
M_SELECTED = 50
ETA = 5.0
WEIGHT_CAP = 0.15
COSTS_BPS = (10.0, 20.0)
CLEAN_WINDOW_START = scorer.CLEAN_WINDOW_START  # 2026-05-01, tz-naive
R_SEEDS = (1, 2, 3, 4, 5)

# S3 / K1 informational reference numbers, supplied directly by the task brief (not
# recomputed here -- they come from this repo's existing frozen S3 leveraged-momentum
# pipeline and its K1 comparison bar).
S3_DATE_NEUTRAL_SHARPE_2024_01_2026_09 = 1.49
K1_BAR_SHARPE = 1.19


def decile_pool(market, momentum: np.ndarray, idx: int, decile_hi: int) -> list[str]:
    member = market.member()[idx]
    sig = np.where(member & np.isfinite(momentum[idx]), momentum[idx], np.nan)
    n = int(np.isfinite(sig).sum())
    if n < scorer.MIN_MEMBERS_FOR_DECILE:
        return []
    order = np.argsort(-np.where(np.isfinite(sig), sig, -np.inf))
    k = max(1, round(n * (decile_hi / 10.0)))
    return [str(market.symbols[i]) for i in order[:k]]


def cap_and_renormalize(weights: dict[str, float], cap: float = WEIGHT_CAP) -> dict[str, float]:
    tickers = list(weights.keys())
    w = np.array([weights[t] for t in tickers], dtype=float)
    total = w.sum()
    if total <= 0:
        return {t: 1.0 / len(tickers) for t in tickers} if tickers else {}
    w = w / total
    for _ in range(100):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over
        under_sum = w[under].sum()
        if under_sum <= 0:
            break
        w[under] += excess * (w[under] / under_sum)
    w = w / w.sum()
    return dict(zip(tickers, w, strict=True))


def llm_weights(pool_scores: dict[str, float], m: int, eta: float) -> dict[str, float]:
    """score_norm in [-1, 1]; ties (equal score) keep the pool's given order (already
    momentum-ranked) -- matches the paper's own tie-break rule."""
    ranked = sorted(pool_scores.items(), key=lambda kv: -kv[1])
    top = ranked[:m]
    if not top:
        return {}
    e = 1.0 / len(top)
    raw = {t: e * (eta**s) for t, s in top}
    return cap_and_renormalize(raw)


def build_held_matrix(
    dates: pd.DatetimeIndex,
    symbols: pd.Index,
    formations: list[tuple[int, dict[str, float]]],
) -> np.ndarray:
    T, N = len(dates), len(symbols)
    held = np.zeros((T, N), dtype=np.float64)
    sym_pos = {s: i for i, s in enumerate(symbols)}
    for j, (idx, weights) in enumerate(formations):
        start = idx + 1
        stop = formations[j + 1][0] + 1 if j + 1 < len(formations) else T
        if start >= T:
            continue
        stop = min(stop, T)
        cols = [sym_pos[t] for t in weights if t in sym_pos]
        vals = np.array([weights[symbols[c]] for c in cols], dtype=np.float64)
        held[start:stop, cols] = vals
    return held.astype(np.float32)


def window_slice(
    net: pd.Series, active: pd.Series, start: pd.Timestamp | None, end: pd.Timestamp | None
):
    idx = net.index
    mask = pd.Series(True, index=idx)
    if start is not None:
        mask &= idx >= start
    if end is not None:
        mask &= idx <= end
    return net[mask], active[mask]


def perf_block(net: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    s = pd.Series(net, index=dates)
    return perf(s)


def monthly_returns(net: np.ndarray, dates: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(1.0 + net, index=dates)
    return s.groupby(s.index.to_period("M")).prod() - 1.0


def main() -> int:
    print("[run] loading market...", flush=True)
    market = load_market(top_n=TOP_N_UNIVERSE, memory_limit="1200MB")
    momentum = load_signal(
        market, source="data/features/daily_broad", column="momentum_252_21", lag=0
    )
    ret = market.next_open_returns()
    dates = market.dates
    symbols = market.symbols

    months = scorer.build_candidate_months(
        market, start=scorer.FULL_PERIOD_START, momentum=momentum
    )
    print(f"[run] formations: {len(months)}", flush=True)

    # AMEND-4 refutation-only window: the REFUTATION_CONTAMINATED_MONTHS most
    # recent look-ahead-contaminated formations (newest-first), used only for
    # an asymmetric refutation check (look-ahead can only flatter L, so a
    # non-positive L-B gain there is decisive; a positive one is not
    # confirmatory on its own). See candidate-manifest.json AMEND-4.
    clean_start_utc = scorer.CLEAN_WINDOW_START.tz_localize("UTC")
    _months_desc = sorted(months, key=lambda m: m[1], reverse=True)
    _contaminated_desc = [m for m in _months_desc if m[1] < clean_start_utc]
    _refutation_set = _contaminated_desc[: scorer.REFUTATION_CONTAMINATED_MONTHS]
    refutation_asof = [m[1] for m in _refutation_set]
    refutation_start = pd.Timestamp(min(refutation_asof).date()) if refutation_asof else None
    refutation_end = pd.Timestamp(max(refutation_asof).date()) if refutation_asof else None

    scores = pd.read_parquet(SCORES_PATH) if SCORES_PATH.exists() else pd.DataFrame()
    if not scores.empty:
        scores["asof"] = pd.to_datetime(scores["asof"], utc=True)

    def scores_for(variant: str, month_asof: pd.Timestamp) -> dict[str, float]:
        if scores.empty:
            return {}
        sub = scores[(scores["variant"] == variant) & (scores["asof"] == month_asof)]
        return dict(zip(sub["ticker"], sub["score_norm"].astype(float), strict=True))

    b_formations: list[tuple[int, dict[str, float]]] = []
    l_formations: list[tuple[int, dict[str, float]]] = []
    p_formations: list[tuple[int, dict[str, float]]] = []
    r_formations: dict[int, list[tuple[int, dict[str, float]]]] = {seed: [] for seed in R_SEEDS}

    clean_formations_asof: list[pd.Timestamp] = []

    for idx, asof, _horizon, pool in months:
        b_pool = decile_pool(market, momentum, idx, decile_hi=1)
        if b_pool:
            b_formations.append((idx, {t: 1.0 / len(b_pool) for t in b_pool}))

        l_scores = scores_for("L", asof)
        pool_scores = {t: l_scores.get(t, 0.0) for t in pool}
        if pool:
            l_formations.append((idx, llm_weights(pool_scores, M_SELECTED, ETA)))

        is_clean = (
            asof.tz_localize(None) >= CLEAN_WINDOW_START
            if asof.tzinfo
            else asof >= CLEAN_WINDOW_START
        )
        if is_clean:
            clean_formations_asof.append(asof)
            # P (headline-shuffle placebo) needs no separate DeepSeek calls: this
            # round's prompt carries no stock-specific numeric content (only
            # anonymized headlines plus a per-month asof/horizon shared by every
            # candidate that month), so scoring ticker A with ticker B's headlines
            # is a byte-identical prompt to L's own call for ticker B in the same
            # month. P is therefore exactly L's score under a seeded within-month
            # derangement (2026-09-28 pre-scoring amendment; see
            # candidate-manifest.json "amendments").
            mapping = scorer.derangement_map(pool, seed=scorer.PLACEBO_SEED_BASE + idx)
            p_pool_scores = {t: l_scores.get(mapping.get(t, t), 0.0) for t in pool}
            if pool:
                p_formations.append((idx, llm_weights(p_pool_scores, M_SELECTED, ETA)))

        for seed in R_SEEDS:
            import random

            rng = random.Random(scorer.PLACEBO_SEED_BASE + seed * 100000 + idx)
            chosen = pool[:]
            rng.shuffle(chosen)
            chosen = chosen[:M_SELECTED]
            if chosen:
                r_formations[seed].append((idx, {t: 1.0 / len(chosen) for t in chosen}))

    print(f"[run] clean-window formations: {len(clean_formations_asof)}", flush=True)

    held_b = build_held_matrix(dates, symbols, b_formations)
    held_l = build_held_matrix(dates, symbols, l_formations)
    held_p = (
        build_held_matrix(dates, symbols, p_formations) if p_formations else np.zeros_like(held_b)
    )
    held_r = {seed: build_held_matrix(dates, symbols, r_formations[seed]) for seed in R_SEEDS}

    clean_start = pd.Timestamp(min(clean_formations_asof).date()) if clean_formations_asof else None
    panel_end = dates[-1]

    results: dict = {
        "iter_id": ITER_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "full_period": {"start": str(dates[0].date()), "end": str(panel_end.date())},
        "clean_window": {
            "start": str(clean_start.date()) if clean_start is not None else None,
            "end": str(panel_end.date()),
            "n_formations": len(clean_formations_asof),
        },
        "candidates": {},
    }

    def add_candidate(name: str, held: np.ndarray, windows: dict[str, tuple]):
        results["candidates"].setdefault(name, {})
        for bps in COSTS_BPS:
            net, turnover = book_returns(held, ret, bps)
            tag = f"{int(bps)}bp"
            for wname, (start, end) in windows.items():
                s = pd.Series(net, index=dates)
                mask = pd.Series(True, index=dates)
                if start is not None:
                    mask &= dates >= start
                if end is not None:
                    mask &= dates <= end
                sub = s[mask]
                results["candidates"][name].setdefault(wname, {})[tag] = perf(sub)

    windows = {
        "full_period": (None, None),
        "clean_window": (clean_start, None),
        "contaminated_window": (
            None,
            (clean_start - pd.Timedelta(days=1)) if clean_start is not None else None,
        ),
        "contaminated_refutation14": (refutation_start, refutation_end),
    }

    add_candidate("B", held_b, windows)
    add_candidate("L", held_l, windows)
    add_candidate("P", held_p, {"clean_window": windows["clean_window"]})
    for seed in R_SEEDS:
        add_candidate(f"R_seed{seed}", held_r[seed], windows)

    # R-median across seeds, per window/cost/metric
    r_median: dict = {}
    for wname in windows:
        r_median[wname] = {}
        for bps in COSTS_BPS:
            tag = f"{int(bps)}bp"
            r_median[wname][tag] = {}
            for metric in ("sharpe", "cagr", "max_dd"):
                vals = [
                    results["candidates"][f"R_seed{seed}"].get(wname, {}).get(tag, {}).get(metric)
                    for seed in R_SEEDS
                ]
                vals = [v for v in vals if v is not None]
                r_median[wname][tag][metric] = float(np.median(vals)) if vals else None
    results["candidates"]["R_median"] = r_median

    # t-stat of L-B monthly return difference (full period, informational)
    net_b_10, _ = book_returns(held_b, ret, 10.0)
    net_l_10, _ = book_returns(held_l, ret, 10.0)
    mb = monthly_returns(net_b_10, dates)
    ml = monthly_returns(net_l_10, dates)
    common = mb.index.intersection(ml.index)
    diff = (ml.loc[common] - mb.loc[common]).dropna()
    if len(diff) > 2:
        t_stat = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))))
    else:
        t_stat = None
    results["l_minus_b_monthly_return_diff_full_period"] = {
        "n_months": int(len(diff)),
        "mean": float(diff.mean()) if len(diff) else None,
        "t_stat": t_stat,
    }

    # Informational: L vs S3 / K1 (clean window and full period, both reported)
    results["informational_reference"] = {
        "s3_date_neutral_sharpe_2024_01_2026_09": S3_DATE_NEUTRAL_SHARPE_2024_01_2026_09,
        "k1_bar_sharpe": K1_BAR_SHARPE,
        "note": "S3/K1 numbers supplied by the task brief, not recomputed in this script.",
    }

    # AMEND-4 verdict rule (2026-09-28, candidate-manifest.json "amendments"):
    # replaces the original single Sharpe(L)>=Sharpe(B)+0.10 magnitude threshold
    # (underpowered at the clean window's n=5 monthly observations) with a
    # sign-based, asymmetric-bound test using the refutation-only contaminated
    # window, while KEEPING the original P/R controls as required conditions
    # for a "promising" classification (the coordinator's amendment message did
    # not mention R; dropping a preregistered negative control without a
    # stated reason was judged an unintentional omission, not a deliberate
    # relaxation, so the executor preserved it rather than silently dropping
    # it -- see AMEND-4's verdict_rule note).
    cw = "clean_window"
    rw = "contaminated_refutation14"
    tag10 = "10bp"

    def get(name, wname, tag, metric):
        return results["candidates"].get(name, {}).get(wname, {}).get(tag, {}).get(metric)

    sharpe_b_clean = get("B", cw, tag10, "sharpe")
    sharpe_l_clean = get("L", cw, tag10, "sharpe")
    sharpe_p_clean = get("P", cw, tag10, "sharpe")
    sharpe_r_median_clean = r_median[cw][tag10]["sharpe"]

    cagr_b_ref = get("B", rw, tag10, "cagr")
    cagr_l_ref = get("L", rw, tag10, "cagr")
    sharpe_b_ref = get("B", rw, tag10, "sharpe")
    sharpe_l_ref = get("L", rw, tag10, "sharpe")

    l_improve_clean = (
        (sharpe_l_clean - sharpe_b_clean)
        if (sharpe_l_clean is not None and sharpe_b_clean is not None)
        else None
    )
    p_improve_clean = (
        (sharpe_p_clean - sharpe_b_clean)
        if (sharpe_p_clean is not None and sharpe_b_clean is not None)
        else None
    )
    l_improve_ref_cagr = (
        (cagr_l_ref - cagr_b_ref) if (cagr_l_ref is not None and cagr_b_ref is not None) else None
    )
    l_improve_ref_sharpe = (
        (sharpe_l_ref - sharpe_b_ref)
        if (sharpe_l_ref is not None and sharpe_b_ref is not None)
        else None
    )

    clean_le_b = l_improve_clean is not None and l_improve_clean <= 0
    contaminated_le_b = l_improve_ref_cagr is not None and l_improve_ref_cagr <= 0
    is_refuted = clean_le_b or contaminated_le_b

    both_positive = (
        l_improve_clean is not None
        and l_improve_clean > 0
        and l_improve_ref_cagr is not None
        and l_improve_ref_cagr > 0
    )
    placebo_fails_to_reproduce = (
        p_improve_clean is not None
        and l_improve_clean is not None
        and l_improve_clean > 0
        and p_improve_clean < 0.5 * l_improve_clean
    )
    beats_random = (
        sharpe_l_clean is not None
        and sharpe_r_median_clean is not None
        and sharpe_l_clean > sharpe_r_median_clean
    )

    if is_refuted:
        verdict = "refuted"
    elif both_positive and placebo_fails_to_reproduce and beats_random:
        verdict = "promising_forward_shadow"
    else:
        verdict = "inconclusive_forward_shadow"

    results["stop_continue_rule"] = {
        "clean_window_5_formations_10bp": {
            "sharpe_B": sharpe_b_clean,
            "sharpe_L": sharpe_l_clean,
            "sharpe_P": sharpe_p_clean,
            "sharpe_R_median": sharpe_r_median_clean,
            "l_minus_b_sharpe": l_improve_clean,
            "p_minus_b_sharpe": p_improve_clean,
        },
        "contaminated_refutation14_10bp": {
            "window": [
                str(refutation_start.date()) if refutation_start is not None else None,
                str(refutation_end.date()) if refutation_end is not None else None,
            ],
            "cagr_B": cagr_b_ref,
            "cagr_L": cagr_l_ref,
            "sharpe_B": sharpe_b_ref,
            "sharpe_L": sharpe_l_ref,
            "l_minus_b_cagr": l_improve_ref_cagr,
            "l_minus_b_sharpe": l_improve_ref_sharpe,
        },
        "condition_refuted_clean_le_b": clean_le_b,
        "condition_refuted_contaminated_le_b": contaminated_le_b,
        "condition_both_windows_positive": both_positive,
        "condition_placebo_fails_to_reproduce_lt_half": placebo_fails_to_reproduce,
        "condition_beats_random_median": beats_random,
        "verdict": verdict,
        "amendment_ref": "candidate-manifest.json amendments[1] AMEND-4",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    print(f"[run] wrote {OUT_DIR / 'results.json'}", flush=True)
    print(json.dumps(results["stop_continue_rule"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
