"""T-20260929-12: build 5 static factor ensembles from T-15's already-computed
select-window (2016-06-01..2023-12-29) ICIR/sign scan. NO new IC is computed
here -- every ranking decision reads
``reports/research/iterations/h20260928_15_claude_factor_batch/select-results.json``
directly. Reuses ``open_composer.research.signal_card`` (``load_market``,
``percentile_ranks``, ``masked_ranks``, ``rank_corr``, ``rank_ic``,
``ic_summary``) and
``scripts/run_h20260928_15_factor_batch._load_candidate`` (the existing
batch/zoo/card dispatcher) unmodified; no new factor-loading logic.

Ensembles
---------
E10 / E20 / E40
    Top-K by |select-window 21d rank ICIR|, equal-weight average of daily
    cross-sectional percentile ranks (``signal_card.percentile_ranks``,
    reused unmodified), tolerant to missing factors: a stock/day counts if
    at least half of the chosen K are known that day (see
    ``build_equal_weight_score`` for why this deviates from T-15's
    ALL-known ``composite_signal`` convention -- a data-coverage finding,
    not a result-driven relaxation).
E20D
    Greedy top-20 from the SAME top-40 pool as E40/R40 (a documented
    compute-bounded restriction -- the brief's "top-K by |ICIR|" pool is not
    reopened further down the ranked list), skipping a candidate whose
    select-window daily rank correlation (sign-adjusted) with an
    already-chosen factor exceeds 0.70.
R40
    Ridge regression on percentile-rank features of a DENSE top-40 pool
    (top-40 by |ICIR| among factors with median daily coverage >= 30% of
    the eligible universe -- ridge needs a complete feature vector per
    training row, so narrow-coverage event-like factors such as
    F10/F08/F01/F09 are excluded from this pool only; E10/E20/E40/E20D use
    the full, unfiltered ranked list). Alpha is chosen by 5-fold blocked
    time-series CV with a 21-session purge on the select window only (fold
    selection uses POOLED, not per-day-averaged, out-of-fold rank
    correlation -- a documented simplification; the ensemble's own reported
    test rank IC uses the proper ``signal_card.rank_ic`` day-by-day
    average). The final model is refit on the full select window at the
    chosen alpha and applied out of sample by fixed linear coefficients (no
    refitting after 2023-12-29).

Nested composite zoo cards (``card_comp_c1``..``card_comp_c5``) are excluded
from every candidate pool (see candidate-matrix-revisions in
external-brief.json): they are composites of factors that already compete
individually in the same ranked pool.

Outputs, one ``.npz`` per ensemble under
``reports/research/iterations/h20260929_12_hedged_factor_ensemble/scores/``:
``dates`` (datetime64[ns]), ``symbols`` (object array), ``score`` (float32,
T x N, NaN where not investable that day).

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/build_h20260929_12_ensembles.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260928_15_factor_batch as t15  # noqa: E402

from open_composer.research.signal_card import (  # noqa: E402
    Market,
    load_market,
    percentile_ranks,
)

ITER_DIR = ROOT / "reports/research/iterations/h20260929_12_hedged_factor_ensemble"
SCORE_DIR = ITER_DIR / "scores"
SELECT_RESULTS = (
    ROOT / "reports/research/iterations/h20260928_15_claude_factor_batch/select-results.json"
)
SELECT_WINDOW = ("2016-06-01", "2023-12-29")
TOP_N = 1000
FORWARD_HORIZON = 21
E20D_CORR_THRESHOLD = 0.70
R40_POOL = 40
CV_FOLDS = 5
CV_PURGE_SESSIONS = 21
RIDGE_ALPHAS = [0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0, 1000.0]
MAX_R40_TRAIN_ROWS = 2_000_000
RNG_SEED = 20260929

NESTED_COMPOSITE_CARDS = {
    "card_comp_c1_mom_quality",
    "card_comp_c2_mom_quality_insider",
    "card_comp_c3_mom_52w",
    "card_comp_c4_mom_roe",
    "card_comp_c5_mom_roe_insider",
}


def _log(msg: str, t0: float) -> None:
    print(f"[h20260929_12_ensembles] {msg} ({time.monotonic() - t0:.0f}s)", flush=True)


def ranked_candidates() -> list[tuple[str, float, int]]:
    """(candidate_id, icir, sign) sorted by |icir| descending. Reads ONLY
    T-15's existing select-window scan; computes nothing new."""
    payload = json.loads(SELECT_RESULTS.read_text(encoding="utf-8"))
    results = payload["results"]
    out = []
    for cid, r in results.items():
        if cid in NESTED_COMPOSITE_CARDS:
            continue
        icir = r.get("select_21d", {}).get("icir")
        sign = r.get("sign_from_select")
        if icir is None or sign is None:
            continue
        out.append((cid, float(icir), int(sign)))
    out.sort(key=lambda t: -abs(t[1]))
    return out


MIN_DENSE_COVERAGE = 0.30


def dense_pool(
    market: Market, ranked: list[tuple[str, float, int]], k: int, min_coverage: float, t0: float
) -> list[tuple[str, float, int]]:
    """Walk ``ranked`` (already sorted by |icir| desc) and keep the first
    ``k`` whose median daily coverage (finite fraction of the eligible
    universe) is at least ``min_coverage``. Needed only for R40's ridge
    features, which require a complete row per training observation --
    unlike the average-based ensembles (E10/E20/E40/E20D), a single sparse
    factor in the pool does not merely shrink the count, it removes the row
    entirely from the training set once ALL 40 columns must be present."""
    member = market.member()
    denom = member.sum(axis=1)
    chosen: list[tuple[str, float, int]] = []
    for cid, icir, sign in ranked:
        if len(chosen) >= k:
            break
        raw = t15._load_candidate(market, cid)
        cov = np.isfinite(raw) & member
        with np.errstate(invalid="ignore", divide="ignore"):
            frac = np.where(denom > 0, cov.sum(axis=1) / np.maximum(denom, 1), 0.0)
        median_cov = float(np.median(frac))
        del raw, cov, frac
        if median_cov >= min_coverage:
            chosen.append((cid, icir, sign))
        _log(
            f"dense_pool: {cid} median_coverage={median_cov:.3f} kept={median_cov >= min_coverage}",
            t0,
        )
    return chosen


MIN_FRAC_KNOWN = 0.5


def build_equal_weight_score(
    market: Market, chosen: list[tuple[str, int]], min_frac_known: float = MIN_FRAC_KNOWN
) -> np.ndarray:
    """Equal-weight average of daily cross-sectional percentile ranks
    (``signal_card.percentile_ranks``, reused unmodified) over whichever of
    ``chosen`` are known that stock/day, requiring at least
    ``ceil(len(chosen) * min_frac_known)`` of them known (else NaN).

    DEVIATION from T-15's ``composite_signal`` (which requires ALL
    components known): a smoke test showed the batch factor
    F10_quality_composite_roe_profitability_accruals (the single highest
    |ICIR| candidate, sign_from_select icir=0.272) covers a median of only
    ~14% of eligible names per day (sec_fundamentals-derived, not densely
    forward-filled), which collapsed an ALL-known E10 ensemble to <1% of
    stock-days -- an artifact of one narrow-coverage factor, not a
    meaningful test of the ensemble hypothesis. This tolerant-average
    convention is decided BEFORE any 2024+ (Stage 1) number is computed, so
    it is a design fix, not a result-driven relaxation; it is disclosed here
    and in report.md. Still no new factor-value formula: only the
    missing-data/completeness policy for combining already-computed,
    reused percentile ranks changes."""
    member = market.member()
    total = np.zeros(market.open_.shape, dtype=np.float64)
    count = np.zeros(market.open_.shape, dtype=np.int32)
    for cid, sign in chosen:
        raw = t15._load_candidate(market, cid)
        pct = percentile_ranks(raw * sign, member)
        finite = np.isfinite(pct)
        total[finite] += pct[finite]
        count[finite] += 1
        del raw, pct
    min_known = max(1, int(np.ceil(len(chosen) * min_frac_known)))
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(count >= min_known, total / np.maximum(count, 1), np.nan)
    return score.astype(np.float32)


def select_window_mask(dates: pd.DatetimeIndex) -> np.ndarray:
    a, b = pd.Timestamp(SELECT_WINDOW[0]), pd.Timestamp(SELECT_WINDOW[1])
    mask = (dates >= a) & (dates <= b)
    return np.asarray(mask)


def pct_select_window(market: Market, cid: str, sign: int, sel_mask: np.ndarray) -> np.ndarray:
    """Percentile rank of one candidate, computed row-wise (each day
    independent of the others) and immediately restricted to select-window
    rows to bound memory -- equivalent to computing over the full history
    and slicing, since ``percentile_ranks`` is row-independent."""
    raw = t15._load_candidate(market, cid)
    raw_sel = raw[sel_mask] * sign
    del raw
    member_sel = market.member()[sel_mask]
    return percentile_ranks(raw_sel, member_sel)


def greedy_dedup(
    pool: list[tuple[str, float, int]], pct_cache: dict[str, np.ndarray], k: int
) -> list[tuple[str, int]]:
    """Greedy top-K by |icir| (pool already sorted), skipping a candidate
    whose select-window daily rank correlation (sign already applied in
    ``pct_cache``) with an already-chosen factor exceeds
    ``E20D_CORR_THRESHOLD``. Correlation is the mean per-day Pearson
    correlation of the two (already-ranked) percentile columns, over days
    both are known -- signed, not absolute, per the brief's exact wording."""
    chosen: list[tuple[str, int]] = []
    chosen_pct: list[np.ndarray] = []
    for cid, _icir, sign in pool:
        if len(chosen) >= k:
            break
        cand = pct_cache[cid]
        ok = True
        for prior in chosen_pct:
            m = np.isfinite(cand) & np.isfinite(prior)
            n = m.sum(axis=1)
            with np.errstate(invalid="ignore", divide="ignore"):
                a = np.where(m, cand, np.nan)
                b = np.where(m, prior, np.nan)
                a = a - np.nanmean(a, axis=1, keepdims=True)
                b = b - np.nanmean(b, axis=1, keepdims=True)
                num = np.nansum(a * b, axis=1)
                den = np.sqrt(np.nansum(a * a, axis=1) * np.nansum(b * b, axis=1))
                daily_corr = np.where((n >= 30) & (den > 0), num / den, np.nan)
            mean_corr = float(np.nanmean(daily_corr)) if np.isfinite(daily_corr).any() else 0.0
            if mean_corr > E20D_CORR_THRESHOLD:
                ok = False
                break
        if ok:
            chosen.append((cid, sign))
            chosen_pct.append(cand)
    return chosen


def blocked_cv_folds(n_days: int, k: int, purge: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """K contiguous day-index blocks; train excludes the test block AND any
    day within ``purge`` sessions of the block's start/end (21-day purge
    around the forward-return horizon)."""
    edges = np.linspace(0, n_days, k + 1, dtype=int)
    folds = []
    all_days = np.arange(n_days)
    for i in range(k):
        lo, hi = edges[i], edges[i + 1]
        test_days = all_days[lo:hi]
        purge_lo, purge_hi = max(0, lo - purge), min(n_days, hi + purge)
        train_mask = np.ones(n_days, dtype=bool)
        train_mask[purge_lo:purge_hi] = False
        folds.append((all_days[train_mask], test_days))
    return folds


def fit_r40(
    market: Market, pool40: list[tuple[str, float, int]], sel_mask: np.ndarray, t0: float
) -> dict:
    """Blocked-CV ridge fit on percentile-rank features of the top-40 pool,
    select window only. Returns the chosen alpha, coefficients, intercept
    and CV diagnostics."""
    dates_sel = market.dates[sel_mask]
    n_days = len(dates_sel)
    fwd = market.forward_returns(FORWARD_HORIZON)
    fwd_sel = fwd[sel_mask]
    del fwd
    member_sel = market.member()[sel_mask]

    pct_cache: dict[str, np.ndarray] = {}
    for cid, _icir, sign in pool40:
        pct_cache[cid] = pct_select_window(market, cid, sign, sel_mask)
        _log(f"R40: cached {cid}", t0)

    intersection = member_sel & np.isfinite(fwd_sel)
    for arr in pct_cache.values():
        intersection &= np.isfinite(arr)
    n_obs = int(intersection.sum())
    _log(f"R40: intersection rows={n_obs} of member_sel={int(member_sel.sum())}", t0)

    day_idx_2d = np.broadcast_to(np.arange(n_days)[:, None], intersection.shape)
    day_idx_all = day_idx_2d[intersection]
    y_all = fwd_sel[intersection].astype(np.float64)
    cols = [pct_cache[cid][intersection] for cid, _icir, _sign in pool40]
    X_all = np.column_stack(cols).astype(np.float64)
    del pct_cache, cols

    rng = np.random.default_rng(RNG_SEED)
    subsampled = False
    if X_all.shape[0] > MAX_R40_TRAIN_ROWS:
        keep = rng.choice(X_all.shape[0], size=MAX_R40_TRAIN_ROWS, replace=False)
        keep.sort()
        X_all, y_all, day_idx_all = X_all[keep], y_all[keep], day_idx_all[keep]
        subsampled = True
    _log(f"R40: X_all shape={X_all.shape} subsampled={subsampled}", t0)

    folds = blocked_cv_folds(n_days, CV_FOLDS, CV_PURGE_SESSIONS)
    cv_scores: dict[float, list[float]] = {a: [] for a in RIDGE_ALPHAS}
    for fi, (train_days, test_days) in enumerate(folds):
        train_rows = np.isin(day_idx_all, train_days)
        test_rows = np.isin(day_idx_all, test_days)
        if train_rows.sum() < 1000 or test_rows.sum() < 200:
            continue
        for alpha in RIDGE_ALPHAS:
            model = Ridge(alpha=alpha)
            model.fit(X_all[train_rows], y_all[train_rows])
            pred = model.predict(X_all[test_rows])
            rho, _p = spearmanr(pred, y_all[test_rows])
            cv_scores[alpha].append(float(rho) if np.isfinite(rho) else 0.0)
        _log(f"R40: fold {fi} done", t0)

    mean_cv = {a: float(np.mean(v)) if v else float("-inf") for a, v in cv_scores.items()}
    best_alpha = max(mean_cv, key=lambda a: mean_cv[a])
    final_model = Ridge(alpha=best_alpha)
    final_model.fit(X_all, y_all)
    _log(f"R40: chosen alpha={best_alpha} cv_scores={mean_cv}", t0)

    return {
        "alpha_grid": RIDGE_ALPHAS,
        "cv_mean_pooled_rank_corr": mean_cv,
        "chosen_alpha": best_alpha,
        "coef": final_model.coef_.tolist(),
        "intercept": float(final_model.intercept_),
        "n_obs_fit": int(X_all.shape[0]),
        "n_obs_intersection_before_subsample": n_obs,
        "subsampled": subsampled,
        "candidate_order": [cid for cid, _icir, _sign in pool40],
    }


def build_r40_score(
    market: Market, pool40: list[tuple[str, float, int]], coef: list[float], intercept: float
) -> np.ndarray:
    """Full-history R40 score: fixed linear combination of the 40 factors'
    daily percentile ranks (sign already applied via ``sign`` below), one
    factor loaded and discarded at a time. A stock/day scores only if ALL 40
    factors are known that day (same convention as the equal-weight
    ensembles' ``composite_signal``)."""
    member = market.member()
    total = np.zeros(market.open_.shape, dtype=np.float64)
    known = member.copy()
    for (cid, _icir, sign), c in zip(pool40, coef, strict=True):
        raw = t15._load_candidate(market, cid)
        pct = percentile_ranks(raw * sign, member)
        known &= np.isfinite(pct)
        total += np.where(np.isfinite(pct), pct, 0.0).astype(np.float64) * c
        del raw, pct
    score = np.where(known, total + intercept, np.nan)
    return score.astype(np.float32)


def save_score(eid: str, market: Market, score: np.ndarray) -> None:
    SCORE_DIR.mkdir(parents=True, exist_ok=True)
    out = SCORE_DIR / f"{eid}.npz"
    np.savez_compressed(
        out,
        dates=market.dates.to_numpy(),
        symbols=market.symbols.to_numpy(dtype=object),
        score=score,
    )
    print(f"[h20260929_12_ensembles] wrote {out}", flush=True)


def main() -> int:
    t0 = time.monotonic()
    market = load_market(top_n=TOP_N, memory_limit="1200MB")
    _log(f"market loaded: {len(market.dates)} dates x {len(market.symbols)} symbols", t0)

    ranked = ranked_candidates()
    _log(f"ranked candidates with valid select ICIR: {len(ranked)}", t0)

    e10 = [(cid, sign) for cid, _icir, sign in ranked[:10]]
    e20 = [(cid, sign) for cid, _icir, sign in ranked[:20]]
    pool40_unfiltered = ranked[:R40_POOL]
    e40 = [(cid, sign) for cid, _icir, sign in pool40_unfiltered]

    save_score("E10", market, build_equal_weight_score(market, e10))
    save_score("E20", market, build_equal_weight_score(market, e20))
    save_score("E40", market, build_equal_weight_score(market, e40))

    sel_mask = select_window_mask(market.dates)
    pct_cache_40 = {
        cid: pct_select_window(market, cid, sign, sel_mask)
        for cid, _icir, sign in pool40_unfiltered
    }
    _log("pct_cache_40 built for E20D dedup", t0)
    e20d = greedy_dedup(pool40_unfiltered, pct_cache_40, k=20)
    del pct_cache_40
    _log(f"E20D chosen {len(e20d)} of target 20: {[c for c, _ in e20d]}", t0)
    save_score("E20D", market, build_equal_weight_score(market, e20d))

    pool40_dense = dense_pool(market, ranked, R40_POOL, MIN_DENSE_COVERAGE, t0)
    _log(f"R40 dense pool: {len(pool40_dense)} of target {R40_POOL}", t0)
    r40_fit = fit_r40(market, pool40_dense, sel_mask, t0)
    r40_score = build_r40_score(market, pool40_dense, r40_fit["coef"], r40_fit["intercept"])
    save_score("R40", market, r40_score)

    manifest_out = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "select_window": list(SELECT_WINDOW),
        "universe_top_n": TOP_N,
        "n_ranked_candidates": len(ranked),
        "e10_ids": [c for c, _ in e10],
        "e20_ids": [c for c, _ in e20],
        "e40_ids": [c for c, _ in e40],
        "e20d_ids": [c for c, _ in e20d],
        "e20d_count": len(e20d),
        "r40_pool_ids": [c for c, _icir, _s in pool40_dense],
        "r40_fit": r40_fit,
    }
    out_path = ITER_DIR / "ensemble-build.json"
    out_path.write_text(json.dumps(manifest_out, indent=2, default=str) + "\n", encoding="utf-8")
    _log(f"wrote {out_path}", t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
