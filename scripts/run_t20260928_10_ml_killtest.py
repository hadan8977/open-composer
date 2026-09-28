"""T-20260928-10 Stage-1 kill test: multi-source cross-sectional LightGBM
ranking, stress window only.

Preregistration: ``reports/research/intel/I-20260928-02-modal-lane-ml-cnn.md``
section A.4 (candidates table, universe, target, walk-forward/embargo, kill
test). Design context: ``reports/research/control/ml-strategy-design-2026-09-28.md``.
Queue block: ``reports/research/control/autonomous-queue.md`` ``### T-20260928-10``.

This is a **kill test only**: no cost model, no position cap, no placebo, no
portfolio construction -- just walk-forward validation-role RankIC for
candidates 5, 6, 11 (LightGBM regression/LambdaRank, all data layers combined,
monthly/biweekly) plus a same-universe price-volume-only baseline B0. If none
of 5/6/11 clears the preregistered bar, the direction is refuted on this data
without spending Stage-2 budget.

Reuse (imported, not copied) from ``scripts/run_h20260917_02_ml_ranking.py``
(``h02`` below): ``build_folds``, ``Fold``, ``rank_ic_per_date``,
``_forward_return_lookup``, ``_quintile``, ``band_of``, ``_benchmark_prices``,
``_read_year_at_dates``, ``_ns``, ``_log``, ``_write_json``, ``_json_default``,
``DAILY_FEATURE_COLUMNS``, ``INSIDER_FEATURE_COLUMNS``,
``SHORT_INTEREST_FEATURE_COLUMNS``, ``BETA_COLUMN``,
``FEATURE_COVERAGE_THRESHOLD``, ``MIN_TRAIN_ROWS``, ``RANKIC_MIN_NAMES``,
``MODEL_REGISTRY`` (this script adds two new entries into that same dict so
``h02.run_training``-style model lookups would also see them, though this
script writes its own fold-training loop -- see "Why not h02.run_training"
below). ``h02.EMBARGO_DAYS`` is monkeypatched to 21 or 10 immediately before
each ``build_folds`` call (that function reads it as a bare module global,
not a parameter) and restored after.

**Why not h02.run_training verbatim**: that function returns only the mean
validation RankIC per fold (for the card's refutation check) and the
**test**-role predictions (for portfolio construction) -- it does not keep
the per-date IC series or split by liquidity tercile, both of which this
kill test's brief requires as by-products. ``build_folds``/``Fold``/
``rank_ic_per_date`` are reused as-is; the fold loop itself
(``run_training_stage1`` below) is new, deliberately smaller than
``h02.run_training`` (no test-role scoring, since there is no portfolio here).

**Universe**: ``data/features/universe_t20260928_10/{year}.parquet``, built
this task via the existing, unmodified ``scripts/build_feature_universe.py``::

    uv run python scripts/build_feature_universe.py --no-top-n-cap \\
        --min-dollar-adv 1000000 --min-close 3.0 --adv-lookback-days 21 \\
        --include-delisted-root data/sip-delisted/by_year \\
        --out-dir data/features/universe_t20260928_10 --memory-limit 1200MB

Close >= $3, 21-day **mean** (not median -- ``build_pit_universe_panel``'s
existing floor-mode implementation, brief's own carve-out) dollar ADV >=
$1M, ETF/fund excluded, delisted names backfilled. 441,765 rows, 9,364
distinct symbols, 2016-2026 (see ``logs/t20260928_10_universe_build.log``).
This is deliberately a *fresh* panel, not the committed ``universe_broad``
(which uses min_close=2.0, adv_lookback=60) -- the brief's own thresholds
(close>=$3, 21-day ADV) are stricter/different and are not free to redefine
here.

**Price/feature source**: ``data/features/daily_broad`` (price-volume base,
identical column set to H-20260917-02's ``DAILY_FEATURE_COLUMNS``) -- this
table already spans the full archive, not filtered to any symbol cap, so no
universe-mismatch join loss.

**Fundamentals**: ``data/features/sec_fundamentals_daily`` (built off
``universe_broad``, effectively full broad-universe coverage). Passthrough:
``gross_profitability``, ``asset_growth``, ``accruals``, ``roe``,
``sue_eps``, ``sue_rev``, ``days_since_report`` (point-in-time, filing-date
based -- these also serve as this task's "earnings-date event features":
**no dedicated earnings-calendar/8-K table covers the 2016-2023 stress
window** -- ``data/features/earnings_events`` only starts 2024, checked, not
invented -- so SUE and days-since-last-filing are the honest substitute, not
a silently narrower proxy).

Four JKP accounting-change factors
(``reports/research/intel/I-20260928-04-recent-high-ic-factors.md``),
**computed, with one documented approximation**: ``sec_fundamentals_daily``'s
``net_income``/``operating_cash_flow``/``stockholders_equity`` are annual-only
(one 10-K update per year -- see ``scripts/build_sec_xbrl_fundamentals.py``
module docstring, "Annual vs. trailing four quarters"), so a true *quarterly*
``niq_at_chg1``/``niq_be_chg1`` is not directly available. This script
proxies quarterly net income as ``eps_diluted * shares_outstanding`` --
``eps_diluted`` *does* carry the full quarterly ladder (built for SUE) --
which is the best available quarterly-resolution numerator. ``ocf_at_chg1``
uses the annual OCF/assets ratio directly (JKP's own definition is a 1-year
change, so the annual cadence is not an approximation for that one factor).
All three ``*_chg1`` factors are the ratio's value today minus its value 252
trading sessions ago (elementwise on a dense daily-forward-filled wide
matrix) -- an approximation of "4 quarters ago" by trading days, consistent
across all three. ``ni_inc8q`` (count of consecutive quarters, capped at 8,
with a higher diluted EPS than the previous *distinct* filed value) is
computed from genuine quarter-to-quarter change points in the ``eps_diluted``
wide matrix (see :func:`consecutive_increase_streak`), not annual data.

**Insider**: ``data/features/insider_broad`` (built off ``universe_broad``,
``feature_universe_top_n: 1000000`` per its own manifest -- i.e. already
full broad-universe coverage, unlike the narrower ``data/features/insider``
which H-20260917-02 used and which is capped at top-1000). Same four columns
as H-20260917-02: ``net_buy_usd_60d``, ``open_market_buy_count_60d``,
``buyers_60d``, ``days_since_last_visible_buy``.

**Short interest / short volume**: ``data/features/short_interest`` (top-1000
liquid names) and ``data/features/short_volume`` (top-500) -- **neither was
rebuilt for the broad universe**; checked their own ``_build_manifest.json``,
not assumed. On a ~9,364-symbol universe this means these columns' coverage
is structurally well under 100%; the existing 50%-coverage-drop rule (reused
from H-20260917-02, ``FEATURE_COVERAGE_THRESHOLD``) may or may not drop them
depending on how much of the stress-window formation panel falls in that
liquid subset -- actual coverage is measured and reported in
``results.json``'s ``feature_coverage`` block and ``report.md``, not assumed
either way before running.

**Target**: 21-day (monthly candidates) or 10-day (biweekly) forward return,
SPY-beta hedged, demeaned within (formation_date, dollar-ADV quintile) --
identical construction to H-20260917-02, parameterized by horizon
(:func:`build_target`).

**Walk-forward**: 3-year rolling training window, quarterly retrain, embargo
= horizon (21 or 10 trading days) -- ``h02.build_folds`` reused verbatim,
with ``h02.EMBARGO_DAYS`` monkeypatched per horizon before each call (see
module docstring above).

**Window**: stress only, 2016-05-02 to 2023-08-31 (frozen per
``docs/runbook-autonomous-round.zh.md`` section 5; price/feature archive
starts 2016-01-04, so the earliest folds' training windows expand back to
that date rather than reaching a full 3 years, exactly as H-20260917-02
documents and records via ``actual_train_years``).

**Models** (fixed hyperparameters, no tuning -- see ``LGBM_REG_PARAMS`` /
``LGBM_RANK_PARAMS`` below): LightGBM regression (``num_threads=16``) and
LightGBM LambdaRank with a 5-grade (0-4) per-formation-date quantile label
(:func:`quantile_grade`) -- validation RankIC is always measured against the
**continuous** target (``target_excess_{h}``), never the discretized grade,
per the brief's own RankIC definition.

Stages (resumable via ``--force`` to rebuild): ``panel`` (universe + features
+ target, two formation cadences), ``train`` (4 candidates: B0, 5, 6, 11),
``report`` (``results.json``, ``feature_ic.csv``, ``report.md``).

Usage (Modal; see ``scripts/modal_run.py`` docstring)::

    python3 scripts/modal_run.py --job t20260928-10-smoke --cpu 2 --memory-gib 8 \\
        --timeout-min 15 \\
        --data data/features/universe_t20260928_10 --data data/features/daily_broad \\
        --data data/features/sec_fundamentals_daily --data data/features/insider_broad \\
        --data data/features/short_interest --data data/features/short_volume \\
        --data data/sip/daily \\
        --out reports/research/iterations/t20260928_10_ml_killtest \\
        --fetch-to reports/research/control/scratch/t20260928_10_smoke \\
        -- uv run python -u scripts/run_t20260928_10_ml_killtest.py --stage all \\
        --smoke --window-start 2022-01-01 --window-end 2022-12-31 --max-symbols 200

    python3 scripts/modal_run.py --job t20260928-10-real --cpu 8 --memory-gib 32 \\
        --timeout-min 90 \\
        --data data/features/universe_t20260928_10 --data data/features/daily_broad \\
        --data data/features/sec_fundamentals_daily --data data/features/insider_broad \\
        --data data/features/short_interest --data data/features/short_volume \\
        --data data/sip/daily \\
        --out reports/research/iterations/t20260928_10_ml_killtest \\
        -- uv run python -u scripts/run_t20260928_10_ml_killtest.py --stage all --force
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from open_composer.research.features import price_hygiene  # noqa: E402
from open_composer.research.features.short_interest import SHORT_INTEREST_ROOT  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from scripts import run_h20260917_02_ml_ranking as h02  # noqa: E402

ITERATION_ID = "t20260928_10_ml_killtest"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
FEATURES_ROOT = ROOT / "data" / "features"

CUSTOM_UNIVERSE_ROOT = FEATURES_ROOT / "universe_t20260928_10"
DAILY_ROOT = FEATURES_ROOT / "daily_broad"
INSIDER_ROOT = FEATURES_ROOT / "insider_broad"
FUNDAMENTALS_ROOT = FEATURES_ROOT / "sec_fundamentals_daily"
SHORT_VOLUME_ROOT = FEATURES_ROOT / "short_volume"

DATA_START = "2016-01-04"
DEFAULT_WINDOW_START = "2016-05-02"
DEFAULT_WINDOW_END = "2023-08-31"
YOY_TRADING_DAYS = 252
BIWEEKLY_STEP_SESSIONS = 10
DEFAULT_TRAIN_YEARS = 3.0
RESULTS_PATH = OUT_DIR / "results.json"
FEATURE_IC_PATH = OUT_DIR / "feature_ic.csv"
REPORT_PATH = OUT_DIR / "report.md"

# --------------------------------------------------------------------------
# feature column registry -- see module docstring for per-layer rationale.
# --------------------------------------------------------------------------

BASE_FEATURE_COLUMNS: tuple[str, ...] = h02.DAILY_FEATURE_COLUMNS
INSIDER_FEATURE_COLUMNS: tuple[str, ...] = h02.INSIDER_FEATURE_COLUMNS
SHORT_INTEREST_FEATURE_COLUMNS: tuple[str, ...] = h02.SHORT_INTEREST_FEATURE_COLUMNS
SHORT_VOLUME_FEATURE_COLUMNS: tuple[str, ...] = (
    "short_volume_ratio",
    "short_volume_ratio_zscore_21",
)
FUNDAMENTALS_PASSTHROUGH_COLUMNS: tuple[str, ...] = (
    "gross_profitability",
    "asset_growth",
    "accruals",
    "roe",
    "sue_eps",
    "sue_rev",
    "days_since_report",
)
FUNDAMENTALS_JKP_COLUMNS: tuple[str, ...] = (
    "ocf_at_chg1",
    "niq_at_chg1",
    "niq_be_chg1",
    "ni_inc8q",
)
FUNDAMENTALS_FEATURE_COLUMNS: tuple[str, ...] = (
    *FUNDAMENTALS_PASSTHROUGH_COLUMNS,
    *FUNDAMENTALS_JKP_COLUMNS,
)
ALL_LAYER_FEATURE_COLUMNS: tuple[str, ...] = (
    *BASE_FEATURE_COLUMNS,
    *FUNDAMENTALS_FEATURE_COLUMNS,
    *INSIDER_FEATURE_COLUMNS,
    *SHORT_INTEREST_FEATURE_COLUMNS,
    *SHORT_VOLUME_FEATURE_COLUMNS,
)

# --------------------------------------------------------------------------
# LightGBM: fixed hyperparameters, written before any run, no tuning here.
# --------------------------------------------------------------------------

LGBM_THREADS = 16
LGBM_COMMON = dict(
    num_leaves=31,
    learning_rate=0.05,
    n_estimators=400,
    colsample_bytree=0.8,
    subsample=0.8,
    subsample_freq=1,
    min_child_samples=200,
    n_jobs=LGBM_THREADS,
    random_state=20260928,
    verbosity=-1,
)
LGBM_REG_PARAMS = dict(LGBM_COMMON)
LGBM_RANK_PARAMS = dict(LGBM_COMMON, objective="lambdarank", label_gain=[0, 1, 2, 3, 4])
RANK_GRADE_BINS = 5


def quantile_grade(y: np.ndarray, groups: np.ndarray, n_bins: int = RANK_GRADE_BINS) -> np.ndarray:
    """Per-group (formation-date) percentile bucket of ``y``, 0..``n_bins``-1.
    Used only as the LambdaRank training label -- validation RankIC always
    scores against the continuous target, never this grade (module
    docstring).
    """
    out = np.zeros(len(y), dtype="float64")
    frame = pd.DataFrame({"y": y, "g": groups})
    for _g, idx in frame.groupby("g", sort=False).groups.items():
        vals = frame.loc[idx, "y"]
        pct = vals.rank(method="first", pct=True).to_numpy()
        bins = np.minimum((pct * n_bins).astype(int), n_bins - 1)
        out[np.asarray(idx)] = bins
    return out


@dataclass
class LightGBMRegressionModel:
    _model: Any = field(default=None, init=False, repr=False)

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        del groups
        self._model = lgb.LGBMRegressor(**LGBM_REG_PARAMS)
        self._model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self._model is not None
        return self._model.predict(X)


@dataclass
class LightGBMLambdaRankModel:
    _model: Any = field(default=None, init=False, repr=False)

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        order = np.argsort(groups, kind="stable")
        X_sorted, y_sorted, g_sorted = X[order], y[order], groups[order]
        grade = quantile_grade(y_sorted, g_sorted)
        _uniques, counts = np.unique(g_sorted, return_counts=True)
        self._model = lgb.LGBMRanker(**LGBM_RANK_PARAMS)
        self._model.fit(X_sorted, grade, group=counts)

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self._model is not None
        return self._model.predict(X)


# Registered into h02's own MODEL_REGISTRY too (same dict object), in case a
# future stage reuses h02.run_training directly against these candidates.
h02.MODEL_REGISTRY["lgbm_reg"] = lambda: LightGBMRegressionModel()
h02.MODEL_REGISTRY["lgbm_lambdarank"] = lambda: LightGBMLambdaRankModel()
MODEL_FACTORIES: dict[str, Any] = {
    "lgbm_reg": lambda: LightGBMRegressionModel(),
    "lgbm_lambdarank": lambda: LightGBMLambdaRankModel(),
}

# --------------------------------------------------------------------------
# candidate registry -- 5, 6, 11 per the preregistration's table, plus B0
# (interactive-session addition: same-universe price-volume-only baseline).
# --------------------------------------------------------------------------

CANDIDATES: dict[str, dict[str, Any]] = {
    "B0": dict(
        label="B0 price-volume-only baseline (LightGBM regression, monthly)",
        feature_set="base",
        model="lgbm_reg",
        cadence="monthly",
        horizon=21,
    ),
    "5": dict(
        label="Candidate 5: LightGBM regression, all layers, monthly, excess_21",
        feature_set="all",
        model="lgbm_reg",
        cadence="monthly",
        horizon=21,
    ),
    "6": dict(
        label="Candidate 6: LightGBM regression, all layers, biweekly, excess_10",
        feature_set="all",
        model="lgbm_reg",
        cadence="biweekly",
        horizon=10,
    ),
    "11": dict(
        label="Candidate 11: LightGBM LambdaRank, all layers, monthly, excess_21 rank",
        feature_set="all",
        model="lgbm_lambdarank",
        cadence="monthly",
        horizon=21,
    ),
}

KILL_RANKIC_FLOOR = 0.02
KILL_MARGIN_OVER_BASELINE = 0.01
RIDGE_BASELINE_RANKIC = (
    0.0071  # H-20260917-02, reports/research/iterations/h20260917_02_ml_ranking/report.md
)

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=h02._json_default) + "\n"
    )


# --------------------------------------------------------------------------
# stage: panel
# --------------------------------------------------------------------------


def _years_for_window(window_start: str, window_end: str, min_year: int | None = None) -> list[int]:
    start_year = min_year if min_year is not None else pd.Timestamp(DATA_START).year
    end_year = pd.Timestamp(window_end).year
    return list(range(start_year, end_year + 1))


def load_price_matrices(years: list[int]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """``(close_wide, open_wide, daily_at_formation_ready)`` -- price matrices
    plus the raw daily feature frame (every symbol/day, not yet filtered to
    formation dates); mirrors ``h02.stage_panel``'s daily-year loop.
    """
    daily_feature_cols = [*BASE_FEATURE_COLUMNS, h02.BETA_COLUMN]
    close_frames, open_frames, raw_frames = [], [], []
    for year in years:
        path = DAILY_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(
            path, columns=["symbol", "trade_date", "open", "close", *daily_feature_cols]
        )
        frame = table.to_pandas()
        del table
        frame["trade_date"] = h02._ns(frame["trade_date"])
        frame["symbol"] = frame["symbol"].astype(str)
        frame = frame.drop_duplicates(["trade_date", "symbol"], keep="last")
        close_frames.append(frame.pivot(index="trade_date", columns="symbol", values="close"))
        open_frames.append(frame.pivot(index="trade_date", columns="symbol", values="open"))
        raw_frames.append(frame)
        _log(
            f"panel: daily_broad {year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols"
        )
    close_wide = pd.concat(close_frames).sort_index().astype("float64")
    open_wide = pd.concat(open_frames).sort_index().astype("float64")
    close_wide.columns = close_wide.columns.astype(str)
    open_wide.columns = open_wide.columns.astype(str)
    close_wide.index = h02._ns(close_wide.index)
    open_wide.index = h02._ns(open_wide.index)
    daily_raw = pd.concat(raw_frames, ignore_index=True)
    return close_wide, open_wide, daily_raw


def build_cohort_frames(
    custom_universe: pd.DataFrame,
    trading_calendar: pd.DatetimeIndex,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    max_symbols: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(monthly_cohort, biweekly_cohort)`` -- (formation_date, symbol,
    adv_rank, dollar_adv, close) rows within the window. Biweekly formation
    dates are every :data:`BIWEEKLY_STEP_SESSIONS`-th trading session in the
    window; each one's universe membership is the most recently known
    (point-in-time) month-end cohort -- membership only ever updates at a
    real month-end, never mid-month, so no biweekly date ever sees a cohort
    decided after itself.
    """
    universe = custom_universe.copy()
    universe["month_end"] = h02._ns(universe["month_end"])
    universe["symbol"] = universe["symbol"].astype(str)
    if max_symbols is not None:
        universe = universe.loc[universe["adv_rank"] <= max_symbols]

    month_ends = sorted(universe["month_end"].unique())
    cohort_sizes = universe.groupby("month_end").size()
    valid_month_ends = [
        d for d in month_ends if cohort_sizes.get(d, 0) >= h02.DEFAULT_MIN_COHORT_SYMBOLS
    ]

    monthly_dates = [d for d in valid_month_ends if window_start <= d <= window_end]
    monthly_cohort = universe.loc[
        universe["month_end"].isin(monthly_dates),
        ["month_end", "symbol", "adv_rank", "dollar_adv", "close"],
    ].rename(columns={"month_end": "formation_date"})

    cal = trading_calendar[(trading_calendar >= window_start) & (trading_calendar <= window_end)]
    biweekly_dates = list(cal[::BIWEEKLY_STEP_SESSIONS])
    month_end_arr = np.array(valid_month_ends)
    rows = []
    for d in biweekly_dates:
        pos = np.searchsorted(month_end_arr, d, side="right") - 1
        if pos < 0:
            continue
        cohort_month_end = month_end_arr[pos]
        sub = universe.loc[
            universe["month_end"] == cohort_month_end,
            ["symbol", "adv_rank", "dollar_adv", "close"],
        ].copy()
        sub["formation_date"] = d
        rows.append(sub)
    biweekly_cohort = (
        pd.concat(rows, ignore_index=True)
        if rows
        else pd.DataFrame(columns=["formation_date", "symbol", "adv_rank", "dollar_adv", "close"])
    )
    return monthly_cohort, biweekly_cohort


def attach_daily_features(cohort: pd.DataFrame, daily_raw: pd.DataFrame) -> pd.DataFrame:
    daily_feature_cols = [*BASE_FEATURE_COLUMNS, h02.BETA_COLUMN]
    merged = cohort.merge(
        daily_raw[["symbol", "trade_date", *daily_feature_cols]].rename(
            columns={"trade_date": "formation_date"}
        ),
        on=["formation_date", "symbol"],
        how="left",
    )
    return merged


def attach_pointwise_layers(
    formation: pd.DataFrame, formation_dates_set: set[pd.Timestamp], years: list[int]
) -> pd.DataFrame:
    """Insider, short-interest, short-volume and fundamentals-passthrough
    columns -- all dense point lookups at the formation date, reusing
    ``h02._read_year_at_dates`` (year-file read + formation-date filter).
    """
    layer_specs = [
        (INSIDER_ROOT, INSIDER_FEATURE_COLUMNS),
        (SHORT_INTEREST_ROOT, SHORT_INTEREST_FEATURE_COLUMNS),
        (SHORT_VOLUME_ROOT, SHORT_VOLUME_FEATURE_COLUMNS),
        (FUNDAMENTALS_ROOT, FUNDAMENTALS_PASSTHROUGH_COLUMNS),
    ]
    for root, columns in layer_specs:
        layer_years = [y for y in years if (root / f"{y}.parquet").exists()]
        frames = [
            h02._read_year_at_dates(root, year, list(columns), formation_dates_set)
            for year in layer_years
        ]
        layer = (
            pd.concat(frames, ignore_index=True)
            if frames
            else pd.DataFrame(columns=["symbol", "trade_date", *columns])
        )
        formation = formation.merge(
            layer.rename(columns={"trade_date": "formation_date"}),
            on=["formation_date", "symbol"],
            how="left",
        )
    return formation


def load_fundamentals_wide(years: list[int]) -> dict[str, pd.DataFrame]:
    cols = [
        "operating_cash_flow",
        "total_assets",
        "stockholders_equity",
        "eps_diluted",
        "shares_outstanding",
    ]
    frames = []
    for year in years:
        path = FUNDAMENTALS_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(path, columns=["symbol", "trade_date", *cols])
        frame = table.to_pandas()
        del table
        frame["trade_date"] = h02._ns(frame["trade_date"])
        frame["symbol"] = frame["symbol"].astype(str)
        frames.append(frame)
    long = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["symbol", "trade_date", *cols])
    )
    wide = {}
    for c in cols:
        wide[c] = long.pivot_table(index="trade_date", columns="symbol", values=c, aggfunc="last")
    return wide


def consecutive_increase_streak(eps_wide: pd.DataFrame, cap: int = 8) -> pd.DataFrame:
    """Per symbol: count of consecutive *distinct* filed diluted-EPS values
    that increased over the previous distinct value, capped at ``cap``,
    forward-filled to daily granularity from each change point's own usable
    session (module docstring, "ni_inc8q").
    """
    out = pd.DataFrame(index=eps_wide.index, columns=eps_wide.columns, dtype="float64")
    for col in eps_wide.columns:
        s = eps_wide[col]
        changed = s.ne(s.shift(1)) & s.notna()
        distinct_idx = s.index[changed.to_numpy()]
        if len(distinct_idx) == 0:
            continue
        distinct_vals = s.loc[distinct_idx].to_numpy()
        streak = np.zeros(len(distinct_vals), dtype="float64")
        run = 0
        for i in range(len(distinct_vals)):
            if i == 0:
                run = 0
            elif distinct_vals[i] > distinct_vals[i - 1]:
                run = min(run + 1, cap)
            else:
                run = 0
            streak[i] = run
        out[col] = pd.Series(streak, index=distinct_idx).reindex(s.index).ffill()
    return out


def derive_jkp_factors(
    wide: dict[str, pd.DataFrame], trading_calendar: pd.DatetimeIndex
) -> dict[str, pd.DataFrame]:
    def _align(df: pd.DataFrame) -> pd.DataFrame:
        return df.reindex(index=trading_calendar).sort_index()

    ocf = _align(wide["operating_cash_flow"])
    assets = _align(wide["total_assets"])
    equity = _align(wide["stockholders_equity"])
    eps = _align(wide["eps_diluted"])
    shares = _align(wide["shares_outstanding"])

    with np.errstate(divide="ignore", invalid="ignore"):
        ocf_at = ocf / assets
        niq_proxy = eps * shares
        niq_at = niq_proxy / assets
        niq_be = niq_proxy / equity

    return {
        "ocf_at_chg1": ocf_at - ocf_at.shift(YOY_TRADING_DAYS),
        "niq_at_chg1": niq_at - niq_at.shift(YOY_TRADING_DAYS),
        "niq_be_chg1": niq_be - niq_be.shift(YOY_TRADING_DAYS),
        "ni_inc8q": consecutive_increase_streak(eps, cap=8),
    }


def lookup_wide_at_formation(
    wide_df: pd.DataFrame, formation: pd.DataFrame, column: str
) -> pd.Series:
    dates = sorted(formation["formation_date"].unique())
    sub = wide_df.reindex(index=dates)
    long = sub.stack(future_stack=True)
    long.index.names = ["formation_date", "symbol"]
    long = long.rename(column).reset_index()
    merged = formation[["formation_date", "symbol"]].merge(
        long, on=["formation_date", "symbol"], how="left"
    )
    return merged[column]


def build_target(
    formation: pd.DataFrame, close_sanitized: pd.DataFrame, horizon: int
) -> pd.DataFrame:
    """Identical construction to ``h02.stage_target``'s target, parameterized
    by horizon (see module docstring)."""
    formation = formation.copy()
    fwd_col = f"fwd_return_{horizon}"
    target_col = f"target_excess_{horizon}"
    formation[fwd_col] = h02._forward_return_lookup(close_sanitized, formation, horizon)
    spy_fwd = close_sanitized["SPY"].shift(-horizon) / close_sanitized["SPY"] - 1.0
    formation["_spy_fwd"] = formation["formation_date"].map(spy_fwd)
    beta = formation[h02.BETA_COLUMN] if h02.BETA_COLUMN in formation.columns else np.nan
    formation["_beta_implied"] = beta * formation["_spy_fwd"]
    formation["_residual"] = formation[fwd_col] - formation["_beta_implied"]
    formation["size_quintile"] = formation.groupby("formation_date")["dollar_adv"].transform(
        h02._quintile
    )
    formation["_quintile_mean_residual"] = formation.groupby(["formation_date", "size_quintile"])[
        "_residual"
    ].transform("mean")
    formation[target_col] = formation["_residual"] - formation["_quintile_mean_residual"]
    formation = formation.drop(
        columns=["_spy_fwd", "_beta_implied", "_residual", "_quintile_mean_residual"]
    )
    return formation


def rank_normalize_and_filter(
    formation: pd.DataFrame,
    feature_columns: tuple[str, ...],
    threshold: float = h02.FEATURE_COVERAGE_THRESHOLD,
) -> tuple[pd.DataFrame, list[str], dict[str, float]]:
    present = [c for c in feature_columns if c in formation.columns]
    coverage = {c: float(formation[c].notna().mean()) for c in present}
    kept = [c for c in present if coverage[c] >= threshold]
    for c in kept:
        formation[c] = formation.groupby("formation_date")[c].rank(pct=True)
    return formation, kept, coverage


def add_adv_tercile(formation: pd.DataFrame) -> pd.DataFrame:
    def _tercile(s: pd.Series) -> pd.Series:
        try:
            return pd.qcut(s, 3, labels=["T1_liquid", "T2_mid", "T3_illiquid"], duplicates="drop")
        except ValueError:
            return pd.Series(["T1_liquid"] * len(s), index=s.index)

    formation = formation.copy()
    formation["adv_tercile"] = (
        formation.groupby("formation_date")["adv_rank"].transform(_tercile).astype(str)
    )
    return formation


def stage_panel(args: argparse.Namespace) -> None:
    manifest_path = CACHE_DIR / "panel_manifest.json"
    if manifest_path.exists() and not args.force:
        _log(f"panel: {manifest_path} present -- reusing (pass --force to rebuild)")
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    window_start = pd.Timestamp(args.window_start)
    window_end = pd.Timestamp(args.window_end)
    years = _years_for_window(args.window_start, args.window_end, min_year=args.min_year)
    _log(
        f"panel: window {window_start.date()}..{window_end.date()}, years={years}, "
        f"smoke={args.smoke}"
    )

    custom_universe = load_universe_panel(CUSTOM_UNIVERSE_ROOT, years=years)
    _log(
        f"panel: custom universe {len(custom_universe):,} rows, "
        f"{custom_universe['symbol'].nunique():,} symbols"
    )

    close_wide, _open_wide, daily_raw = load_price_matrices(years)
    trading_calendar = close_wide.index
    close_sanitized, _open_unused, hygiene_report = price_hygiene.sanitize_price_matrices(
        close_wide, None
    )
    _log(
        f"panel: price hygiene masked {hygiene_report.symbols_masked} symbols "
        f"({hygiene_report.price_cells_masked} cells)"
    )
    if "SPY" not in close_sanitized.columns:
        bench_close, _bench_open = h02._benchmark_prices(("SPY",))
        close_sanitized["SPY"] = bench_close.reindex(close_sanitized.index)["SPY"]

    monthly_cohort, biweekly_cohort = build_cohort_frames(
        custom_universe, trading_calendar, window_start, window_end, args.max_symbols
    )
    _log(
        f"panel: monthly cohort {len(monthly_cohort):,} rows "
        f"({monthly_cohort['formation_date'].nunique()} dates), "
        f"biweekly cohort {len(biweekly_cohort):,} rows "
        f"({biweekly_cohort['formation_date'].nunique()} dates)"
    )

    fundamentals_wide = load_fundamentals_wide(years)
    jkp_wide = derive_jkp_factors(fundamentals_wide, trading_calendar)

    cadences = {"monthly": (monthly_cohort, 21), "biweekly": (biweekly_cohort, 10)}
    panel_paths: dict[str, Path] = {}
    coverage_report: dict[str, dict[str, float]] = {}
    kept_report: dict[str, list[str]] = {}
    for cadence_name, (cohort, horizon) in cadences.items():
        if cohort.empty:
            _log(f"panel: {cadence_name} cohort empty -- skipping")
            continue
        formation = attach_daily_features(cohort, daily_raw)
        formation_dates_set = set(formation["formation_date"].unique())
        formation = attach_pointwise_layers(formation, formation_dates_set, years)
        for jkp_col, jkp_df in jkp_wide.items():
            formation[jkp_col] = lookup_wide_at_formation(jkp_df, formation, jkp_col)
        formation = build_target(formation, close_sanitized, horizon)
        formation = add_adv_tercile(formation)
        formation, kept, coverage = rank_normalize_and_filter(formation, ALL_LAYER_FEATURE_COLUMNS)
        formation["year"] = formation["formation_date"].dt.year
        out_path = CACHE_DIR / f"panel_{cadence_name}.parquet"
        formation.to_parquet(out_path, index=False)
        panel_paths[cadence_name] = out_path
        coverage_report[cadence_name] = coverage
        kept_report[cadence_name] = kept
        _log(
            f"panel: {cadence_name} -> {out_path.name}, {len(formation):,} rows, "
            f"{len(kept)}/{len(ALL_LAYER_FEATURE_COLUMNS)} features kept "
            f"(coverage>={h02.FEATURE_COVERAGE_THRESHOLD:.0%})"
        )

    close_wide.to_parquet(CACHE_DIR / "close_wide.parquet")
    manifest = {
        "window_start": args.window_start,
        "window_end": args.window_end,
        "years": years,
        "smoke": bool(args.smoke),
        "max_symbols": args.max_symbols,
        "custom_universe_rows": int(len(custom_universe)),
        "custom_universe_symbols": int(custom_universe["symbol"].nunique()),
        "feature_coverage_by_cadence": coverage_report,
        "features_kept_by_cadence": kept_report,
        "all_layer_feature_columns": list(ALL_LAYER_FEATURE_COLUMNS),
        "trading_calendar_sessions": int(len(trading_calendar)),
    }
    _write_json(manifest_path, manifest)
    _log(f"panel: wrote manifest to {manifest_path}")


# --------------------------------------------------------------------------
# stage: train
# --------------------------------------------------------------------------


def run_training_stage1(
    panel: pd.DataFrame,
    folds: list[h02.Fold],
    feature_columns: list[str],
    target_col: str,
    model_factory,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Walk-forward validation-role RankIC only -- no test-role scoring, no
    portfolio (see module docstring, "Why not h02.run_training"). Returns a
    long frame of (formation_date, rho, tercile) records (``tercile=="all"``
    plus each liquidity tercile) and per-fold metadata.
    """
    ic_records: list[dict[str, Any]] = []
    fold_meta: list[dict[str, Any]] = []
    for fold in folds:
        train_frame = panel.loc[panel["formation_date"].isin(fold.train_dates)]
        # LightGBM handles missing features natively; dropping rows with ANY
        # missing feature silently cut the universe to the names that carry
        # the narrowest layer (short interest, ~17% coverage) -- i.e. the
        # liquid tercile only (first run, 2026-09-28 06:xx). Only rows without
        # a target are dropped.
        train_frame = train_frame.dropna(subset=[target_col])
        meta: dict[str, Any] = {
            "fold_id": fold.fold_id,
            "train_start": fold.train_start.date().isoformat(),
            "train_cutoff": fold.train_cutoff.date().isoformat(),
            "actual_train_years": round(fold.actual_train_years, 2),
            "train_rows": int(len(train_frame)),
            "validation_dates": len(fold.validation_dates),
        }
        if len(train_frame) < h02.MIN_TRAIN_ROWS:
            meta["skipped"] = f"train_rows {len(train_frame)} < {h02.MIN_TRAIN_ROWS}"
            fold_meta.append(meta)
            continue

        model = model_factory()
        X_train = train_frame[feature_columns].to_numpy(dtype="float64")
        y_train = train_frame[target_col].to_numpy(dtype="float64")
        groups_train = train_frame["formation_date"].to_numpy()
        model.fit(X_train, y_train, groups_train)

        val_frame = panel.loc[panel["formation_date"].isin(fold.validation_dates)]
        val_frame = val_frame.dropna(subset=[target_col])
        if val_frame.empty:
            meta["validation_rankic_mean"] = None
            meta["validation_rankic_n_dates"] = 0
            fold_meta.append(meta)
            continue
        preds = model.predict(val_frame[feature_columns].to_numpy(dtype="float64"))
        scored = val_frame[["formation_date", "symbol", "adv_tercile", target_col]].copy()
        scored["prediction"] = preds

        overall = h02.rank_ic_per_date(scored, "prediction", target_col)
        for date, rho in overall:
            ic_records.append({"formation_date": date, "rho": rho, "tercile": "all"})
        for tercile_name, sub in scored.groupby("adv_tercile"):
            tsplit = h02.rank_ic_per_date(sub, "prediction", target_col)
            for date, rho in tsplit:
                ic_records.append({"formation_date": date, "rho": rho, "tercile": tercile_name})

        meta["validation_rankic_mean"] = (
            float(np.mean([r for _, r in overall])) if overall else None
        )
        meta["validation_rankic_n_dates"] = len(overall)
        fold_meta.append(meta)

    ic_frame = (
        pd.DataFrame(ic_records)
        if ic_records
        else pd.DataFrame(columns=["formation_date", "rho", "tercile"])
    )
    return ic_frame, fold_meta


def _summarize_ic(ic_frame: pd.DataFrame, tercile: str = "all") -> dict[str, Any]:
    sub = ic_frame.loc[ic_frame["tercile"] == tercile, "rho"]
    n = int(len(sub))
    if n == 0:
        return {"mean_rankic": None, "t_stat": None, "n_dates": 0}
    mean = float(sub.mean())
    std = float(sub.std(ddof=1)) if n > 1 else 0.0
    t_stat = float(mean / (std / np.sqrt(n))) if std > 0 else None
    return {"mean_rankic": mean, "t_stat": t_stat, "n_dates": n}


def univariate_feature_ic(
    panel: pd.DataFrame, target_col: str, feature_columns: list[str]
) -> pd.DataFrame:
    """Descriptive-only per-feature univariate RankIC, stress window, on the
    monthly panel (see report for cadence note)."""
    rows = []
    for col in feature_columns:
        sub = panel[["formation_date", col, target_col]].dropna()
        ic_list = h02.rank_ic_per_date(
            sub.rename(columns={col: "prediction"}), "prediction", target_col
        )
        n = len(ic_list)
        if n == 0:
            rows.append({"feature": col, "mean_ic": None, "t_stat": None, "n_dates": 0})
            continue
        values = np.array([r for _, r in ic_list])
        mean = float(values.mean())
        std = float(values.std(ddof=1)) if n > 1 else 0.0
        t_stat = float(mean / (std / np.sqrt(n))) if std > 0 else None
        rows.append({"feature": col, "mean_ic": mean, "t_stat": t_stat, "n_dates": n})
    frame = pd.DataFrame(rows).sort_values("mean_ic", ascending=False, key=lambda s: s.abs())
    return frame


def stage_train(args: argparse.Namespace) -> None:
    close_wide = pd.read_parquet(CACHE_DIR / "close_wide.parquet", columns=[])
    trading_calendar = pd.DatetimeIndex(h02._ns(close_wide.index))

    panels: dict[str, pd.DataFrame] = {}
    for cadence in ("monthly", "biweekly"):
        path = CACHE_DIR / f"panel_{cadence}.parquet"
        if path.exists():
            frame = pd.read_parquet(path)
            frame["formation_date"] = h02._ns(frame["formation_date"])
            panels[cadence] = frame

    results: dict[str, Any] = {}
    all_ic_frames: dict[str, pd.DataFrame] = {}
    for cand_id, spec in CANDIDATES.items():
        cand_path = CACHE_DIR / f"candidate_{cand_id}.json"
        ic_path = CACHE_DIR / f"candidate_{cand_id}_ic.parquet"
        if cand_path.exists() and ic_path.exists() and not args.force:
            _log(f"train: candidate {cand_id} cached -- reusing")
            results[cand_id] = json.loads(cand_path.read_text())
            all_ic_frames[cand_id] = pd.read_parquet(ic_path)
            continue

        cadence = spec["cadence"]
        horizon = spec["horizon"]
        panel = panels.get(cadence)
        if panel is None or panel.empty:
            _log(f"train: candidate {cand_id} -- no {cadence} panel, skipping")
            continue
        target_col = f"target_excess_{horizon}"
        feature_columns = list(
            BASE_FEATURE_COLUMNS if spec["feature_set"] == "base" else ALL_LAYER_FEATURE_COLUMNS
        )
        feature_columns = [c for c in feature_columns if c in panel.columns]
        formation_dates = sorted(panel["formation_date"].unique())

        h02.EMBARGO_DAYS = horizon
        folds = h02.build_folds(formation_dates, trading_calendar, DEFAULT_TRAIN_YEARS)
        _log(
            f"train: candidate {cand_id} ({spec['label']}) -- {len(folds)} folds, "
            f"{len(feature_columns)} features, embargo={horizon}"
        )

        model_factory = MODEL_FACTORIES[spec["model"]]
        ic_frame, fold_meta = run_training_stage1(
            panel, folds, feature_columns, target_col, model_factory
        )
        ic_frame.to_parquet(ic_path, index=False)
        all_ic_frames[cand_id] = ic_frame

        by_year = {}
        if not ic_frame.empty:
            all_rows = ic_frame.loc[ic_frame["tercile"] == "all"].copy()
            all_rows["year"] = pd.to_datetime(all_rows["formation_date"]).dt.year
            for year, sub in all_rows.groupby("year"):
                by_year[str(int(year))] = _summarize_ic(sub.assign(tercile="all"), "all")

        by_tercile = {
            t: _summarize_ic(ic_frame, t)
            for t in ("T1_liquid", "T2_mid", "T3_illiquid")
            if t in set(ic_frame.get("tercile", []))
        }

        record = {
            "candidate_id": cand_id,
            "label": spec["label"],
            "model": spec["model"],
            "feature_set": spec["feature_set"],
            "n_features": len(feature_columns),
            "feature_columns": feature_columns,
            "cadence": cadence,
            "horizon": horizon,
            "n_folds": len(folds),
            "fold_meta": fold_meta,
            "overall": _summarize_ic(ic_frame, "all"),
            "by_year": by_year,
            "by_tercile": by_tercile,
        }
        _write_json(cand_path, record)
        results[cand_id] = record
        overall = record["overall"]
        _log(
            f"train: candidate {cand_id} done -- mean RankIC={overall['mean_rankic']}, "
            f"t={overall['t_stat']}, n_dates={overall['n_dates']}"
        )

    # Univariate feature IC (by-product, descriptive) on the monthly panel.
    monthly_panel = panels.get("monthly")
    if monthly_panel is not None and not monthly_panel.empty:
        feature_ic = univariate_feature_ic(
            monthly_panel, "target_excess_21", list(ALL_LAYER_FEATURE_COLUMNS)
        )
        feature_ic.to_csv(FEATURE_IC_PATH, index=False)
        _log(f"train: wrote {FEATURE_IC_PATH}")

    _write_json(CACHE_DIR / "train_results.json", results)


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def stage_report(args: argparse.Namespace) -> None:
    del args
    manifest = json.loads((CACHE_DIR / "panel_manifest.json").read_text())
    results = json.loads((CACHE_DIR / "train_results.json").read_text())

    b0 = results.get("B0", {}).get("overall", {})
    b0_mean = b0.get("mean_rankic")
    baseline = max(RIDGE_BASELINE_RANKIC, b0_mean if b0_mean is not None else -1.0)
    threshold = baseline + KILL_MARGIN_OVER_BASELINE

    candidate_verdicts = {}
    any_pass = False
    for cand_id in ("5", "6", "11"):
        rec = results.get(cand_id)
        if rec is None:
            candidate_verdicts[cand_id] = {
                "pass": False,
                "reason": "candidate not trained (see log)",
            }
            continue
        mean_rankic = rec["overall"]["mean_rankic"]
        passed = (
            mean_rankic is not None
            and mean_rankic >= KILL_RANKIC_FLOOR
            and mean_rankic >= threshold
        )
        any_pass = any_pass or passed
        candidate_verdicts[cand_id] = {
            "pass": passed,
            "mean_rankic": mean_rankic,
            "t_stat": rec["overall"]["t_stat"],
            "n_dates": rec["overall"]["n_dates"],
            "floor": KILL_RANKIC_FLOOR,
            "threshold_vs_baseline": threshold,
        }

    verdict = "PASS" if any_pass else "FAIL"
    top_features = None
    if FEATURE_IC_PATH.exists():
        fic = pd.read_csv(FEATURE_IC_PATH)
        top_features = fic.head(5).to_dict("records")

    summary = {
        "task": "T-20260928-10",
        "stage": "Stage-1 kill test",
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "window": {"start": manifest["window_start"], "end": manifest["window_end"]},
        "ridge_baseline_rankic": RIDGE_BASELINE_RANKIC,
        "b0": b0,
        "baseline_used_for_threshold": baseline,
        "kill_threshold": {"floor": KILL_RANKIC_FLOOR, "margin_over_baseline": threshold},
        "candidates": {cid: results[cid] for cid in results},
        "verdict": verdict,
        "verdict_detail": candidate_verdicts,
        "top_univariate_features": top_features,
        "feature_coverage_by_cadence": manifest["feature_coverage_by_cadence"],
        "features_kept_by_cadence": manifest["features_kept_by_cadence"],
    }
    _write_json(RESULTS_PATH, summary)
    _log(f"report: wrote {RESULTS_PATH}, verdict={verdict}")

    lines = [
        "# T-20260928-10 Stage-1 否定测试：多来源截面排序模型",
        "",
        f"压力期 {manifest['window_start']} -> {manifest['window_end']}，"
        "候选 5/6/11（LightGBM 全层特征）+ B0（价量基线，LightGBM）。",
        "",
        f"**结论：{verdict}**",
        "",
        "## 各候选验证集 RankIC（压力期，样本外折）",
        "",
        "| 候选 | 说明 | mean RankIC | t | 调仓日数 | 过线 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for cid in ("B0", "5", "6", "11"):
        rec = results.get(cid)
        if rec is None:
            lines.append(f"| {cid} | -- | -- | -- | -- | 未训练 |")
            continue
        overall = rec["overall"]
        passed = candidate_verdicts.get(cid, {}).get("pass")
        mark = "PASS" if passed else ("--" if cid == "B0" else "FAIL")
        lines.append(
            f"| {cid} | {rec['label']} | {overall['mean_rankic']:.4f} "
            if overall["mean_rankic"] is not None
            else f"| {cid} | {rec['label']} | NA "
        )
        lines[-1] += f"| {overall['t_stat']:.2f} " if overall["t_stat"] is not None else "| NA "
        lines[-1] += f"| {overall['n_dates']} | {mark} |"

    lines += [
        "",
        f"判定线：mean RankIC >= {KILL_RANKIC_FLOOR} 且 >= max(0.0071, B0) + 0.01 = {threshold:.4f}"
        f"（B0 = {b0.get('mean_rankic')}）。",
        "",
        "## 数据层覆盖",
        "",
    ]
    for cadence, kept in manifest["features_kept_by_cadence"].items():
        cov = manifest["feature_coverage_by_cadence"][cadence]
        n_all = len(ALL_LAYER_FEATURE_COLUMNS)
        lines.append(f"- **{cadence}**：{len(kept)}/{n_all} 个特征覆盖率达标（>=50%）保留。")
        narrow = [
            c for c in (*SHORT_INTEREST_FEATURE_COLUMNS, *SHORT_VOLUME_FEATURE_COLUMNS) if c in cov
        ]
        if narrow:
            lines.append(
                "  空头兴趣/空头成交量列覆盖率："
                + ", ".join(f"{c}={cov[c]:.1%}" for c in narrow)
                + "（`short_interest`/`short_volume` 只覆盖流动性前 1000/500，"
                "未按宽池子重建，如实报告）"
            )

    if top_features:
        lines += [
            "",
            "## 单变量特征 IC 前 5（月度面板，压力期，仅描述）",
            "",
            "| 特征 | mean IC | t | 调仓日数 |",
            "|---|---:|---:|---:|",
        ]
        for row in top_features:
            mi = row["mean_ic"]
            ts = row["t_stat"]
            lines.append(
                f"| {row['feature']} | {mi:.4f} | {ts:.2f} | {row['n_dates']} |"
                if mi is not None and ts is not None
                else f"| {row['feature']} | NA | NA | {row['n_dates']} |"
            )

    lines += [
        "",
        "## Modal 花费",
        "",
        "见 `python3 scripts/modal_budget.py status`"
        "（本任务花费另行写入 report.md 末尾，执行者手填）。",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    _log(f"report: wrote {REPORT_PATH}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["panel", "train", "report", "all"], default="all")
    parser.add_argument("--window-start", default=DEFAULT_WINDOW_START)
    parser.add_argument("--window-end", default=DEFAULT_WINDOW_END)
    parser.add_argument(
        "--smoke", action="store_true", help="small slice for a correctness smoke run"
    )
    parser.add_argument(
        "--max-symbols", type=int, default=None, help="cap universe to top-N by adv_rank (smoke)"
    )
    parser.add_argument(
        "--min-year",
        type=int,
        default=None,
        help="override earliest data year (smoke only; real run must use the full 2016 archive)",
    )
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stages = ["panel", "train", "report"] if args.stage == "all" else [args.stage]
    for stage in stages:
        _log(f"=== stage {stage} ===")
        if stage == "panel":
            stage_panel(args)
        elif stage == "train":
            stage_train(args)
        elif stage == "report":
            stage_report(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
