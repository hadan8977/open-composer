#!/usr/bin/env python3
"""H-20260928-31: does a TRAINED ensemble-disagreement (DEUP-style epistemic
uncertainty) gate raise the T1 12-1 momentum book's Sharpe (not just cut its
drawdown), on the frozen select/holdout/anchor windows, versus a
same-realized-vol-matched unguarded control?

Card: ``reports/research/hypotheses/H-20260928-31-uncertainty-gate.md``.
Dossier: ``reports/research/iterations/h20260928_14b_uncertainty_gate/``.
Source: arXiv 2603.13252 "When Alpha Breaks" (two-level DEUP-style
uncertainty: a strategy-level regime-trust gate and a position-level
epistemic tail-risk cap). Queue task T-20260928-14.

The T1 book (top 30 of the largest 500 names by 12-1 momentum, overlapping
20-session cohorts) is reproduced unchanged via
``scripts.run_h20260924_02_momentum_crash_guard.load_book`` (itself built on
``open_composer.research.signal_card``); this script only adds a TRAINED
ensemble-disagreement signal on top of it. Window/cost/Sharpe conventions
(select/holdout/anchor, 10bp/20bp, RF=BIL excess Sharpe) are reused unchanged
from ``scripts.run_h20260918_05_recent_menu`` (imported as ``base``).

Three preregistered candidates (candidate-manifest.json), one path
(``uncertainty_gate_t1_book``):

U1   Book-level moderate gate: exposure 0.5 (remainder SHY) when the
     trailing-252-session uncertainty quantile z(s-1) > 0.80, else 1.0.
U2   Book-level severe gate: exposure 0.0 when z(s-1) > 0.90, else 1.0.
U3   Individual-name DEUP-style cap: at each daily cohort formation, exclude
     the top 20% most-uncertain eligible names that day, backfill the
     30-name cohort by momentum rank among the rest.

Model: k=15 bootstrap LightGBM regressors (row-level bootstrap, seeds 0-14),
target = 20-session-forward cross-sectional percentile rank of return,
features = ``kt.BASE_FEATURE_COLUMNS`` (``scripts.run_t20260928_10_ml_killtest``)
rank-normalized daily via ``open_composer.research.signal_card.percentile_ranks``
(the same operation as ``scripts.run_t20260928_30_smallcap_ml_book.rank_normalize_daily``,
re-expressed here on the Market-matrix representation this script otherwise
uses, rather than importing that script -- only ``signal_card`` and
``run_h20260924_02_momentum_crash_guard`` are imported by this task's brief).
Universe: top-500 by dollar ADV (same PIT universe as the T1 book). Walk
forward: expanding window, annual retrain each January, training labels
purged to end >=21 sessions before the retrain date. LightGBM hyperparameters
fixed to ``scripts.run_t20260928_10_ml_killtest.LGBM_COMMON`` (num_leaves=31,
learning_rate=0.05, n_estimators=400, colsample_bytree=0.8, subsample=0.8,
subsample_freq=1, min_child_samples=200); ``num_threads`` = ``--cores``.

**Disclosed compute cap** (a pre-backtest engineering choice, not a change to
any preregistered threshold): each bootstrap fit's training pool is capped
at ``ROW_CAP`` rows (sampled with replacement, i.e. the row-level bootstrap
itself is drawn up to this size rather than the full pool size) so that
later retrain years -- whose expanding training pool is otherwise O(500
symbols x 2000+ days) -- remain tractable on the requested Modal cores within
this task's time/cost budget. This affects fit variance/speed only, not the
gate's definition, thresholds, or evaluation.

Timing discipline: label formation at date t uses only information known
through the close of t; the label itself (20-session forward return) is
purged from training until its outcome is realized. The uncertainty signal
u_i(t)/U(t)/z(t) is therefore already point-in-time by construction (a model
trained only on purged, realized history). The gate multiplier for session s
is decided from z(s-1) -- ordinary 1-session settlement lag (not the T1
book's own 2-session lag for signals derived from its OWN return series,
since z(t) here is derived from the model panel, not the book's realized
open-to-open returns -- see decision-record.md).

Usage::

    scripts/run_capped.sh --mem 1.8G -- uv run python \\
        scripts/run_h20260928_14b_uncertainty_gate.py --stage eval

    # heavy stage, run on Modal (see scripts/modal_run.py):
    uv run python scripts/run_h20260928_14b_uncertainty_gate.py --stage train \\
        --cores 4 --k-models 15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402
import run_h20260924_02_momentum_crash_guard as guard  # noqa: E402
import run_t20260928_10_ml_killtest as kt  # noqa: E402

from open_composer.research.signal_card import (  # noqa: E402
    book_returns,
    hold,
    load_market,
    load_signal,
    percentile_ranks,
    topk_cohorts,
)

ITER_ID = "h20260928_14b_uncertainty_gate"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
CACHE_DIR = OUT_DIR / "cache"

TOP_N = 500
TOP_K = 30
HOLD_SESSIONS = 20
PRIMARY_BPS = 10.0
STRESS_BPS = 20.0

K_MODELS = 15
HORIZON = 20
PURGE_SESSIONS = 21
U_WINDOW = 252
Z_THRESH_U1 = 0.80
Z_THRESH_U2 = 0.90
U1_EXPOSURE = 0.5
U2_EXPOSURE = 0.0
U3_EXCLUDE_FRAC = 0.20
N_PLACEBO_SEEDS = 200
AUROC_MIN = 0.60
DD_IMPROVEMENT_MARGIN_PP = 0.05
PLACEBO_SHARPE_PCTL = 0.90
OWNER_SHARPE_GAP = 0.10
ROW_CAP = 100_000  # disclosed compute cap, see module docstring

STRESS_START = "2016-05-01"
STRESS_END = "2023-08-31"

LGBM_COMMON_BASE = dict(kt.LGBM_COMMON)


# --------------------------------------------------------------------- train


def build_rank_feature_matrices(market, member: np.ndarray) -> dict[str, np.ndarray]:
    """Each of ``kt.BASE_FEATURE_COLUMNS``, daily-cross-sectional percentile
    ranked over ``member`` -- the same operation
    ``scripts.run_t20260928_30_smallcap_ml_book.rank_normalize_daily`` performs,
    re-expressed on the Market-matrix representation."""
    out = {}
    for col in kt.BASE_FEATURE_COLUMNS:
        raw = load_signal(market, source="data/features/daily_broad", column=col)
        out[col] = percentile_ranks(raw, member)
    return out


def build_label(market, member: np.ndarray) -> np.ndarray:
    fwd = market.forward_returns(HORIZON)
    return percentile_ranks(fwd, member)


def _year_start_index(dates: pd.DatetimeIndex, year: int) -> int:
    jan1 = pd.Timestamp(f"{year}-01-01")
    idx = dates.searchsorted(jan1, side="left")
    return int(idx)


def train_predict(
    market,
    member: np.ndarray,
    rank_features: dict[str, np.ndarray],
    label: np.ndarray,
    *,
    cores: int,
    k_models: int,
    years: list[int] | None = None,
    row_cap: int = ROW_CAP,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Walk-forward annual retrain. Returns (pred_mean, pred_std, meta) where
    pred_mean/pred_std are T x N arrays (NaN where no out-of-sample
    prediction exists), and meta records the actual first out-of-sample
    year and per-year training-pool sizes."""
    import lightgbm as lgb

    dates = market.dates
    T, N = member.shape
    pred_mean = np.full((T, N), np.nan, dtype=np.float32)
    pred_std = np.full((T, N), np.nan, dtype=np.float32)
    cols = list(kt.BASE_FEATURE_COLUMNS)
    feature_stack = np.stack([rank_features[c] for c in cols], axis=-1)  # T x N x F

    all_years = years if years is not None else sorted(set(dates.year))
    first_oos_year = None
    per_year_pool = {}

    lgbm_params = dict(LGBM_COMMON_BASE)
    lgbm_params["n_jobs"] = int(cores)
    lgbm_params.pop("random_state", None)

    for year in all_years:
        j0 = _year_start_index(dates, year)
        if j0 <= 0 or j0 >= T:
            continue
        cutoff = j0 - PURGE_SESSIONS
        if cutoff <= 0:
            continue
        train_mask = np.zeros((T, N), dtype=bool)
        train_mask[:cutoff] = member[:cutoff] & np.isfinite(label[:cutoff])
        pool_t, pool_n = np.nonzero(train_mask)
        pool_size = len(pool_t)
        per_year_pool[int(year)] = pool_size
        if pool_size < 2000:
            continue  # not enough history for a meaningful fit this year
        if first_oos_year is None:
            first_oos_year = year

        j1 = _year_start_index(dates, year + 1)
        j1 = j1 if j1 > j0 else T
        pred_t, pred_n = np.nonzero(member[j0:j1])
        pred_t = pred_t + j0
        if len(pred_t) == 0:
            continue
        X_pred = feature_stack[pred_t, pred_n, :]
        pred_ok = np.isfinite(X_pred).all(axis=1)

        X_train_full = feature_stack[pool_t, pool_n, :]
        y_train_full = label[pool_t, pool_n]
        row_ok = np.isfinite(X_train_full).all(axis=1) & np.isfinite(y_train_full)
        X_train_full = X_train_full[row_ok]
        y_train_full = y_train_full[row_ok]
        if len(X_train_full) < 2000:
            continue

        sum_pred = np.zeros(len(pred_t), dtype=np.float64)
        sumsq_pred = np.zeros(len(pred_t), dtype=np.float64)
        sample_size = min(len(X_train_full), row_cap)
        for seed in range(k_models):
            rng = np.random.default_rng(1000 * year + seed)
            boot_idx = rng.integers(0, len(X_train_full), size=sample_size)
            model = lgb.LGBMRegressor(**lgbm_params, random_state=seed)
            model.fit(X_train_full[boot_idx], y_train_full[boot_idx])
            p = np.full(len(pred_t), np.nan, dtype=np.float64)
            if pred_ok.any():
                p[pred_ok] = model.predict(X_pred[pred_ok])
            sum_pred += np.where(np.isfinite(p), p, 0.0)
            sumsq_pred += np.where(np.isfinite(p), p * p, 0.0)
        mean_p = sum_pred / k_models
        var_p = np.maximum(sumsq_pred / k_models - mean_p**2, 0.0)
        std_p = np.sqrt(var_p)
        mean_p = np.where(pred_ok, mean_p, np.nan)
        std_p = np.where(pred_ok, std_p, np.nan)
        pred_mean[pred_t, pred_n] = mean_p.astype(np.float32)
        pred_std[pred_t, pred_n] = std_p.astype(np.float32)

    meta = {
        "first_oos_year": int(first_oos_year) if first_oos_year is not None else None,
        "per_year_training_pool_size": per_year_pool,
        "k_models": k_models,
        "row_cap": row_cap,
        "cores": cores,
    }
    return pred_mean, pred_std, meta


def run_train_stage(args: argparse.Namespace) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print("[train 1/3] loading market + features ...", flush=True)
    market = load_market(top_n=TOP_N)
    member = market.member()
    rank_features = build_rank_feature_matrices(market, member)
    label = build_label(market, member)
    print(f"  market: {len(market.dates)} sessions, {len(market.symbols)} symbols", flush=True)

    years = None
    if args.smoke:
        years = [market.dates.year.max() - 1]
        k_models = min(2, args.k_models)
        print(f"[train 2/3] SMOKE MODE: year={years}, k_models={k_models}", flush=True)
    else:
        k_models = args.k_models

    print("[train 2/3] walk-forward bootstrap training ...", flush=True)
    pred_mean, pred_std, meta = train_predict(
        market,
        member,
        rank_features,
        label,
        cores=args.cores,
        k_models=k_models,
        years=years,
        row_cap=args.row_cap,
    )
    print(f"  meta: {meta}", flush=True)

    print("[train 3/3] writing cache ...", flush=True)
    np.savez_compressed(
        CACHE_DIR
        / ("ensemble_predictions_smoke.npz" if args.smoke else "ensemble_predictions.npz"),
        pred_mean=pred_mean,
        pred_std=pred_std,
        dates=market.dates.values.astype("datetime64[ns]"),
        symbols=np.asarray(market.symbols),
    )
    (CACHE_DIR / ("train_meta_smoke.json" if args.smoke else "train_meta.json")).write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8"
    )
    out_name = "ensemble_predictions_smoke.npz" if args.smoke else "ensemble_predictions.npz"
    print("wrote", CACHE_DIR / out_name, flush=True)
    return 0


# ------------------------------------------------------------------- gate


def load_predictions(
    smoke: bool = False,
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex, pd.Index]:
    name = "ensemble_predictions_smoke.npz" if smoke else "ensemble_predictions.npz"
    data = np.load(CACHE_DIR / name, allow_pickle=True)
    dates = pd.DatetimeIndex(data["dates"])
    symbols = pd.Index(data["symbols"])
    return data["pred_mean"], data["pred_std"], dates, symbols


def align_predictions(
    pred_std: np.ndarray,
    pred_dates: pd.DatetimeIndex,
    pred_symbols: pd.Index,
    market_dates: pd.DatetimeIndex,
    market_symbols: pd.Index,
) -> np.ndarray:
    """Reindex the (possibly differently-shaped) prediction panel onto the
    T1 book's own market dates/symbols; missing entries are NaN."""
    df = pd.DataFrame(pred_std, index=pred_dates, columns=pred_symbols)
    df = df.reindex(index=market_dates, columns=market_symbols)
    return df.to_numpy(dtype=np.float32)


def book_level_uncertainty(held: np.ndarray, u_i: np.ndarray) -> np.ndarray:
    """Held-weight-weighted mean of u_i over currently-held names; NaN if no
    held name has a finite u_i that day."""
    w = held.astype(np.float64)
    have = np.isfinite(u_i)
    w_eff = np.where(have, w, 0.0)
    denom = w_eff.sum(axis=1)
    num = np.where(have, w_eff * np.where(have, u_i, 0.0), 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(denom > 0, num / np.where(denom > 0, denom, 1.0), np.nan)
    return out


def trailing_quantile(
    u_series: np.ndarray, window: int = U_WINDOW, min_valid_frac: float = 0.90
) -> np.ndarray:
    """z(t): U(t)'s quantile within U[t-window+1 .. t] (inclusive), using only
    U(t) and its own past -- never a future observation.

    Requires at least ``min_valid_frac`` of the ``window`` trailing POSITIONS
    to have a finite U value (not that literally all ``window`` positions be
    finite) -- U has sparse single-day NaN gaps (e.g. a held name's u_i
    momentarily missing around a universe entry/exit), and requiring a
    perfectly gap-free window made z(t) finite on only 1 of 2692 sessions in
    practice, an implementation defect fixed before any candidate was scored
    against it, not a change to the window length or either quantile
    threshold (both unchanged)."""
    T = len(u_series)
    z = np.full(T, np.nan, dtype=np.float64)
    arr = np.asarray(u_series, dtype=np.float64)
    min_valid = int(np.ceil(window * min_valid_frac))
    for t in range(T):
        if not np.isfinite(arr[t]):
            continue
        lo = max(0, t - window + 1)
        win = arr[lo : t + 1]
        win = win[np.isfinite(win)]
        if len(win) < min_valid:
            continue
        z[t] = float((win <= arr[t]).mean())
    return z


def settle_1session(z: np.ndarray) -> np.ndarray:
    """z(s-1) available for the decision applied at session s -- ordinary
    1-session lag (z is model-panel-derived, not the book's own realized
    return series; see module docstring)."""
    out = np.full_like(z, np.nan)
    out[1:] = z[:-1]
    return out


def multiplier_from_z(z_lagged: np.ndarray, threshold: float, exposure: float) -> np.ndarray:
    """Fallback: missing/NaN z means no gate information -> multiplier 1.0
    (unguarded), matching run_h20260924_02's own fallback convention."""
    return np.where(np.isfinite(z_lagged) & (z_lagged > threshold), exposure, 1.0)


def circular_shift(x: np.ndarray, k: int) -> np.ndarray:
    """Rotate by k (preserves the exact run-length/segment-duration
    distribution of the real series, per the preregistered placebo design)."""
    k = k % len(x)
    if k == 0:
        return x.copy()
    return np.concatenate([x[-k:], x[:-k]])


def solve_vol_matched_k(base_ret: np.ndarray, shy_ret: np.ndarray, target_vol: float) -> float:
    """k such that std(k*base + (1-k)*shy) == target_vol (both series over
    the SAME window as target_vol was measured). Closed-form quadratic in k;
    clipped to [0, 2] and preferring the smaller non-negative root."""
    b = np.asarray(base_ret, dtype=np.float64)
    s = np.asarray(shy_ret, dtype=np.float64)
    ok = np.isfinite(b) & np.isfinite(s)
    b, s = b[ok], s[ok]
    if len(b) < 5 or not np.isfinite(target_vol):
        return float("nan")
    var_b = float(np.var(b, ddof=1))
    var_s = float(np.var(s, ddof=1))
    cov_bs = float(np.cov(b, s, ddof=1)[0, 1])
    target_var = target_vol**2 / 252.0  # target_vol is annualized; work in daily variance
    a = var_b + var_s - 2 * cov_bs
    bb = 2 * cov_bs - 2 * var_s
    cc = var_s - target_var
    if abs(a) < 1e-18:
        if abs(bb) < 1e-18:
            return float("nan")
        k = -cc / bb
        return float(np.clip(k, 0.0, 2.0))
    disc = bb**2 - 4 * a * cc
    if disc < 0:
        return float(np.clip(-bb / (2 * a), 0.0, 2.0))
    sq = np.sqrt(disc)
    k1 = (-bb + sq) / (2 * a)
    k2 = (-bb - sq) / (2 * a)
    candidates = [k for k in (k1, k2) if np.isfinite(k)]
    nonneg = [k for k in candidates if k >= 0]
    pick = min(nonneg, key=lambda k: abs(k - 1.0)) if nonneg else min(candidates, key=abs)
    return float(np.clip(pick, 0.0, 2.0))


def auroc(score: np.ndarray, label: np.ndarray) -> float:
    """Mann-Whitney rank-sum AUROC; NaN if either class is empty."""
    mask = np.isfinite(score) & np.isfinite(label.astype(float))
    s = score[mask]
    y = label[mask].astype(bool)
    n1 = int(y.sum())
    n0 = int((~y).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    ranks = pd.Series(s).rank(method="average").to_numpy()
    sum_ranks_pos = ranks[y].sum()
    return float((sum_ranks_pos - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def forward_drawdown_label(
    net_ret: np.ndarray, dates: pd.DatetimeIndex, window: int = HORIZON
) -> tuple[np.ndarray, np.ndarray]:
    """y(t)=1 iff the base book's max drawdown over [t+2, t+21] (20 sessions,
    starting 2 sessions ahead per the book's own settlement lag) is deeper
    than the median of that same quantity across the scored window."""
    T = len(net_ret)
    r = np.where(np.isfinite(net_ret), net_ret, 0.0)
    fwd_dd = np.full(T, np.nan, dtype=np.float64)
    for t in range(T - window - 2):
        seg = r[t + 2 : t + 2 + window]
        if len(seg) < window:
            continue
        equity = np.cumprod(1.0 + seg)
        dd = float(np.min(equity / np.maximum.accumulate(equity) - 1.0))
        fwd_dd[t] = dd
    return fwd_dd, np.full(T, np.nan)  # median computed by caller over the scored mask


def window_mask(index: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    return (index >= start) & (index <= end)


def metrics_dict(m: base.Metrics) -> dict:
    return {
        "days": m.days,
        "cagr": m.cagr,
        "vol": m.vol,
        "sharpe": m.sharpe,
        "max_dd": m.max_dd,
        "turnover_yr": m.turnover_yr,
    }


def evaluate_series(
    net: np.ndarray, turnover: np.ndarray, index: pd.DatetimeIndex, rf: pd.Series
) -> dict:
    s_net = pd.Series(net, index=index)
    s_turn = pd.Series(turnover, index=index)
    out = {name: metrics_dict(m) for name, m in base.window_metrics(s_net, rf, s_turn).items()}
    dmask = window_mask(index, STRESS_START, STRESS_END)
    out["stress"] = metrics_dict(base.metrics(s_net.loc[dmask], rf.loc[dmask], s_turn.loc[dmask]))
    return out


def run_gate_stage(args: argparse.Namespace) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print("[gate 1/6] loading T1 book ...", flush=True)
    market, held, ret, signal = guard.load_book()
    dates = market.dates

    print("[gate 2/6] loading ensemble predictions ...", flush=True)
    _, pred_std, pred_dates, pred_symbols = load_predictions(smoke=args.smoke)
    u_i = align_predictions(pred_std, pred_dates, pred_symbols, dates, market.symbols)

    print("[gate 3/6] side panel + base book ...", flush=True)
    close, open_ = guard.load_side_panel(["SPY", "SHY", "BIL"], "2013-06-03", base.HOLD_END)
    shy_open = open_["SHY"].reindex(dates)
    bil_close = close["BIL"].reindex(dates)
    shy_next_open = np.full(len(dates), np.nan)
    shy_open_vals = shy_open.to_numpy(dtype=float)
    shy_next_open[:-1] = shy_open_vals[1:] / shy_open_vals[:-1] - 1.0
    rf = bil_close.pct_change().fillna(0.0)

    base_net_10bp, base_turn_10bp = book_returns(held, ret, PRIMARY_BPS)
    base_net_20bp, base_turn_20bp = book_returns(held, ret, STRESS_BPS)

    print("[gate 4/6] U(t), z(t) ...", flush=True)
    U = book_level_uncertainty(held, u_i)
    z = trailing_quantile(U, U_WINDOW)
    z_lagged = settle_1session(z)

    m_u1 = multiplier_from_z(z_lagged, Z_THRESH_U1, U1_EXPOSURE)
    m_u2 = multiplier_from_z(z_lagged, Z_THRESH_U2, U2_EXPOSURE)

    print("[gate 5/6] U3 cohort reselection ...", flush=True)
    member = market.member((1, TOP_N))
    u_i_pct = percentile_ranks(u_i, member)  # (0,1], higher = more uncertain that day
    eligible_u3 = member & ~(np.isfinite(u_i_pct) & (u_i_pct > (1.0 - U3_EXCLUDE_FRAC)))
    n_excluded_per_day = (member & np.isfinite(u_i_pct) & (u_i_pct > (1.0 - U3_EXCLUDE_FRAC))).sum(
        axis=1
    )
    cohorts_u3 = topk_cohorts(signal, eligible_u3, TOP_K)
    held_u3 = hold(cohorts_u3, HOLD_SESSIONS)

    print("[gate 6/6] evaluating candidates ...", flush=True)
    results: dict = {
        "iter_id": ITER_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "market": {
            "sessions": int(len(dates)),
            "symbols": int(len(market.symbols)),
            "date_range": [str(dates[0].date()), str(dates[-1].date())],
        },
        "prediction_coverage": {
            "u_i_finite_days": int(np.isfinite(u_i).any(axis=1).sum()),
            "u_i_first_date": str(dates[np.isfinite(u_i).any(axis=1)][0].date())
            if np.isfinite(u_i).any()
            else None,
        },
        "candidates": {},
        "trial_ledger_rows": [],
    }

    def _run_multiplier_candidate(cand_id: str, m: np.ndarray) -> dict:
        net10, turn10 = guard.guarded_net_returns(held, ret, m, shy_next_open, PRIMARY_BPS)
        net20, turn20 = guard.guarded_net_returns(held, ret, m, shy_next_open, STRESS_BPS)
        return {"net10": net10, "turn10": turn10, "net20": net20, "turn20": turn20}

    def _owner_rule(
        net10: np.ndarray, index: pd.DatetimeIndex, start: str, end: str, base_series: pd.Series
    ) -> dict:
        mask = window_mask(index, start, end)
        cand_ret = pd.Series(net10, index=index).loc[mask]
        cand_vol = (
            float(cand_ret.std(ddof=1) * np.sqrt(252.0))
            if cand_ret.std(ddof=1) > 0
            else float("nan")
        )
        cand_sharpe_metrics = base.metrics(
            cand_ret, rf.loc[mask], pd.Series(0.0, index=index).loc[mask]
        )
        base_win = base_series.loc[mask]
        shy_win = pd.Series(shy_next_open, index=index).loc[mask]
        k = solve_vol_matched_k(base_win.to_numpy(), shy_win.to_numpy(), cand_vol)
        if np.isfinite(k):
            mix = k * base_win.fillna(0.0) + (1.0 - k) * shy_win.fillna(0.0)
            mix_metrics = base.metrics(mix, rf.loc[mask], pd.Series(0.0, index=index).loc[mask])
        else:
            mix_metrics = None
        gap = (
            (cand_sharpe_metrics.sharpe - mix_metrics.sharpe)
            if mix_metrics is not None
            and mix_metrics.sharpe is not None
            and cand_sharpe_metrics.sharpe is not None
            else float("nan")
        )
        return {
            "k": k,
            "candidate_sharpe": cand_sharpe_metrics.sharpe,
            "control_sharpe": mix_metrics.sharpe if mix_metrics else None,
            "sharpe_gap": gap,
            "owner_rule_pass": bool(np.isfinite(gap) and gap >= OWNER_SHARPE_GAP),
        }

    base_net10_series = pd.Series(base_net_10bp, index=dates)

    fwd_dd_base, _ = forward_drawdown_label(base_net_10bp, dates, HORIZON)
    anchor_scored_mask = window_mask(dates, base.ANCHOR_START, base.ANCHOR_END) & np.isfinite(
        fwd_dd_base
    )
    median_fwd_dd = (
        float(np.nanmedian(fwd_dd_base[anchor_scored_mask]))
        if anchor_scored_mask.any()
        else float("nan")
    )
    y_label = np.where(anchor_scored_mask, fwd_dd_base < median_fwd_dd, False)

    for cand_id, m in (("u1", m_u1), ("u2", m_u2)):
        series = _run_multiplier_candidate(cand_id, m)
        metrics10 = evaluate_series(series["net10"], series["turn10"], dates, rf)
        metrics20 = evaluate_series(series["net20"], series["turn20"], dates, rf)

        score = np.where(anchor_scored_mask, z_lagged, np.nan)
        cand_auroc = auroc(score, y_label.astype(float))

        real_dd = metrics10["anchor"]["max_dd"]
        base_dd_anchor = base.metrics(
            base_net10_series.loc[window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)],
            rf.loc[window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)],
            pd.Series(base_turn_10bp, index=dates).loc[
                window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)
            ],
        ).max_dd
        real_dd_improve = (
            (base_dd_anchor - real_dd)
            if (base_dd_anchor is not None and real_dd is not None)
            else float("nan")
        )

        placebo_dd_improve = []
        placebo_sharpe = []
        rng = np.random.default_rng(hash(cand_id) % (2**31))
        threshold = Z_THRESH_U1 if cand_id == "u1" else Z_THRESH_U2
        exposure = U1_EXPOSURE if cand_id == "u1" else U2_EXPOSURE
        m_raw = multiplier_from_z(z_lagged, threshold, exposure)
        for _seed in range(N_PLACEBO_SEEDS):
            k_shift = int(rng.integers(1, len(m_raw) - 1))
            m_shift = circular_shift(m_raw, k_shift)
            snet10, _ = guard.guarded_net_returns(held, ret, m_shift, shy_next_open, PRIMARY_BPS)
            amask = window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)
            s_ret = pd.Series(snet10, index=dates).loc[amask]
            s_turn = pd.Series(np.zeros(len(dates)), index=dates).loc[amask]
            mtx = base.metrics(s_ret, rf.loc[amask], s_turn)
            placebo_dd_improve.append(
                (base_dd_anchor - mtx.max_dd)
                if (mtx.max_dd is not None and base_dd_anchor is not None)
                else np.nan
            )
            placebo_sharpe.append(mtx.sharpe if mtx.sharpe is not None else np.nan)
        placebo_dd_improve = np.array(placebo_dd_improve, dtype=float)
        placebo_sharpe = np.array(placebo_sharpe, dtype=float)
        placebo_dd_median = float(np.nanmedian(placebo_dd_improve))
        placebo_sharpe_p90 = float(
            np.nanpercentile(placebo_sharpe[np.isfinite(placebo_sharpe)], 90)
        )
        real_anchor_sharpe = metrics10["anchor"]["sharpe"]

        cond_a = bool(np.isfinite(cand_auroc) and cand_auroc < AUROC_MIN)
        cond_b1 = bool(
            np.isfinite(real_dd_improve)
            and np.isfinite(placebo_dd_median)
            and (real_dd_improve - placebo_dd_median) < DD_IMPROVEMENT_MARGIN_PP
        )
        cond_b2 = bool(
            real_anchor_sharpe is not None
            and np.isfinite(real_anchor_sharpe)
            and np.isfinite(placebo_sharpe_p90)
            and real_anchor_sharpe < placebo_sharpe_p90
        )
        owner = _owner_rule(
            series["net10"], dates, base.ANCHOR_START, base.ANCHOR_END, base_net10_series
        )
        cond_c = not owner["owner_rule_pass"]

        stage1_stop = cond_a or cond_b1 or cond_b2 or cond_c
        entry = {
            "metrics_10bp": metrics10,
            "metrics_20bp": metrics20,
            "auroc": cand_auroc,
            "auroc_min": AUROC_MIN,
            "real_dd_improvement_anchor": real_dd_improve,
            "placebo_dd_improvement_median": placebo_dd_median,
            "placebo_sharpe_p90": placebo_sharpe_p90,
            "owner_rule": owner,
            "stop_conditions": {
                "a_auroc_below_min": cond_a,
                "b1_dd_improvement_below_placebo_plus_5pp": cond_b1,
                "b2_sharpe_below_placebo_p90": cond_b2,
                "c_owner_rule_fail": cond_c,
                "stage1_stop": stage1_stop,
            },
            "stage1_passed": not stage1_stop,
            "stage2_run": False,
        }
        results["candidates"][cand_id] = entry
        results["trial_ledger_rows"].append({"candidate_id": cand_id, **entry["stop_conditions"]})
        print(
            f"  {cand_id}: AUROC {cand_auroc:.3f} sharpe_gap {owner['sharpe_gap']} "
            f"stage1_stop={stage1_stop}",
            flush=True,
        )

    # -- U3 --
    net10_u3, turn10_u3 = book_returns(held_u3, ret, PRIMARY_BPS)
    net20_u3, turn20_u3 = book_returns(held_u3, ret, STRESS_BPS)
    metrics10_u3 = evaluate_series(net10_u3, turn10_u3, dates, rf)
    metrics20_u3 = evaluate_series(net20_u3, turn20_u3, dates, rf)

    placebo_sharpe_u3 = []
    rng3 = np.random.default_rng(20260928)
    for _seed in range(N_PLACEBO_SEEDS):
        eligible_p = member.copy()
        for t in range(len(dates)):
            n_ex = int(n_excluded_per_day[t])
            if n_ex <= 0:
                continue
            idxs = np.nonzero(member[t])[0]
            if len(idxs) <= n_ex:
                continue
            drop = rng3.choice(idxs, size=n_ex, replace=False)
            eligible_p[t, drop] = False
        cohorts_p = topk_cohorts(signal, eligible_p, TOP_K)
        held_p = hold(cohorts_p, HOLD_SESSIONS)
        net_p, turn_p = book_returns(held_p, ret, PRIMARY_BPS)
        amask = window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)
        s_ret = pd.Series(net_p, index=dates).loc[amask]
        s_turn = pd.Series(turn_p, index=dates).loc[amask]
        mtx = base.metrics(s_ret, rf.loc[amask], s_turn)
        placebo_sharpe_u3.append(mtx.sharpe if mtx.sharpe is not None else np.nan)
    placebo_sharpe_u3 = np.array(placebo_sharpe_u3, dtype=float)
    placebo_sharpe_u3_p90 = float(
        np.nanpercentile(placebo_sharpe_u3[np.isfinite(placebo_sharpe_u3)], 90)
    )
    real_anchor_sharpe_u3 = metrics10_u3["anchor"]["sharpe"]
    cond_b2_u3 = bool(
        real_anchor_sharpe_u3 is not None
        and np.isfinite(real_anchor_sharpe_u3)
        and np.isfinite(placebo_sharpe_u3_p90)
        and real_anchor_sharpe_u3 < placebo_sharpe_u3_p90
    )
    owner_u3 = _owner_rule(net10_u3, dates, base.ANCHOR_START, base.ANCHOR_END, base_net10_series)
    cond_c_u3 = not owner_u3["owner_rule_pass"]
    stage1_stop_u3 = cond_b2_u3 or cond_c_u3
    entry_u3 = {
        "metrics_10bp": metrics10_u3,
        "metrics_20bp": metrics20_u3,
        "auroc": None,
        "auroc_not_applicable": True,
        "placebo_sharpe_p90": placebo_sharpe_u3_p90,
        "owner_rule": owner_u3,
        "stop_conditions": {
            "a_auroc_below_min": False,
            "a_not_applicable": True,
            "b2_sharpe_below_placebo_p90": cond_b2_u3,
            "c_owner_rule_fail": cond_c_u3,
            "stage1_stop": stage1_stop_u3,
        },
        "stage1_passed": not stage1_stop_u3,
        "stage2_run": False,
    }
    results["candidates"]["u3"] = entry_u3
    results["trial_ledger_rows"].append({"candidate_id": "u3", **entry_u3["stop_conditions"]})
    print(f"  u3: sharpe_gap {owner_u3['sharpe_gap']} stage1_stop={stage1_stop_u3}", flush=True)

    results["base_book"] = {
        "anchor_10bp": metrics_dict(
            base.metrics(
                base_net10_series.loc[window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)],
                rf.loc[window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)],
                pd.Series(base_turn_10bp, index=dates).loc[
                    window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)
                ],
            )
        ),
    }
    results["any_stage1_pass"] = any(c["stage1_passed"] for c in results["candidates"].values())

    (OUT_DIR / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    print("wrote", OUT_DIR / "results.json", flush=True)
    return 0


# ------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("train", "eval"), required=True)
    ap.add_argument("--cores", type=int, default=4)
    ap.add_argument("--k-models", type=int, default=K_MODELS)
    ap.add_argument("--row-cap", type=int, default=ROW_CAP)
    ap.add_argument(
        "--smoke", action="store_true", help="1 year, <=2 models, for pipeline smoke tests"
    )
    args = ap.parse_args(argv)

    if args.stage == "train":
        return run_train_stage(args)
    return run_gate_stage(args)


if __name__ == "__main__":
    raise SystemExit(main())
