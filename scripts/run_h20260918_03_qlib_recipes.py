"""H-20260918-03: reuse Qlib's *published* LightGBM-Alpha158 and
DoubleEnsemble-Alpha158 recipes -- hyperparameters verbatim, no tuning -- on
this repo's broad US-equity universe.

Card: ``reports/research/hypotheses/H-20260918-03-qlib-recipes-on-broad-universe.md``
Sibling runner this reuses (imported as a module, see "Reuse" below):
``scripts/run_h20260917_02_ml_ranking.py`` (H-20260917-02). Report/verdict
style reference: ``scripts/run_h20260917_01_insider_independent.py``.

**The point of this card is fidelity, not improvement**: every hyperparameter
below is transcribed from Qlib's public ``examples/benchmarks``
``workflow_config_lightgbm_Alpha158.yaml`` /
``workflow_config_doubleensemble_Alpha158.yaml`` and the card's own
transcription of them. Anything that differs from the published recipe is
listed in the "Deviations" section below and echoed into the report --
never silently changed.

Deviations from the published recipe (all disclosed here and in the report)
-----------------------------------------------------------------------------
1. **``num_threads=2``, not 20.** The card's own instruction: this box has 2
   usable cores (3.9GB RAM, other jobs always running); 20 threads would not
   make the box faster and would raise contention/OOM risk for no benefit.
2. **LightGBM ``num_boost_round=1000`` / ``early_stopping_rounds=50``** are
   not among the card's 8 listed hyperparameters (``loss, learning_rate,
   colsample_bytree, subsample, lambda_l1, lambda_l2, max_depth,
   num_leaves``) -- they are ``qlib.contrib.model.gbdt.LGBModel.fit``'s own
   defaults, needed to run gradient boosting at all, not a tuning choice
   made here. Early stopping needs a validation slice; this repo's
   ``fit(X, y, groups)`` model-registry interface (from H-20260917-02) is
   not given one, so :class:`QlibLightGBMModel` carves an internal,
   temporally-last slice of its own *training* rows (by ``groups``, i.e.
   formation date; never the fold's own validation/test rows) for early
   stopping only -- see that class's docstring.
3. **DoubleEnsemble's SR (sample reweighting) and FS (feature selection)
   are reimplemented directly over ``lightgbm``**, not the ``qlib`` package
   (not installed) or torch (not installed, and not needed here either --
   Qlib's own ``qlib/contrib/model/double_ensemble.py`` is pure
   ``lightgbm``, torch is only used by Qlib's *other* model classes). This
   is a documented, reasoned reconstruction of the paper's structure
   (rank-based per-sample "hardness" from loss level (``alpha1``) and
   loss-curve instability (``alpha2``), ``bins_sr``-bin bucketing,
   ``decay``-blended weight updates; ``bins_fs``-bin bucketing of
   LightGBM's own gain-based feature importance with a ``sample_ratios``
   per-bin keep-fraction feature mask feeding the next sub-model) -- not a
   byte-for-byte port of Qlib's resampling-based FS importance estimator
   (which perturbs and rescores each feature; gain importance is used here
   as a far cheaper proxy given the 2-core/3.9GB box). See
   :class:`DoubleEnsembleModel`.
4. **``config/feature_sets/screened_top40_recent_broad.json`` does not
   exist yet** (checked 2026-09-18). The "layered" feature family falls
   back to the narrow-suffixed ``screened_top40_recent.json`` factor list,
   and per-factor to the narrow (unsuffixed) source-root table when a
   ``_broad`` source root does not exist for that factor's
   ``source_root`` -- disclosed per factor in the feature manifest and the
   report; low resulting coverage on the broad universe is expected to
   (correctly) trip the existing 50%-coverage drop rule, not silently
   patched over.
5. **``data/features/alpha158_broad`` did not exist when this runner was
   written** (checked 2026-09-18, see the card's own instruction to smoke
   test narrow first). Unlike (4), there is **no fallback** here: the
   primary ``alpha158{suffix}`` root is required to exist for the exact
   requested ``--features-suffix`` or this refuses to run (``stage_panel``
   raises) -- this is the one root this script will never silently
   substitute a narrower table for (see the module docstring's "Cache
   keyed by feature family" note below for why: an
   H-20260917-01 run on 2026-09-18 lost an entire 991-cell run this exact
   way).

Reuse from ``scripts/run_h20260917_02_ml_ranking.py`` (imported as
``ml02 = importlib.import_module("scripts.run_h20260917_02_ml_ranking")``;
confirmed importing cleanly as a module -- no argparse/IO side effects at
import time)
-----------------------------------------------------------------------------
``ml02.RidgeRankingModel`` (the card's third model, "ridge" -- registered
unchanged), ``ml02.build_folds``/``Fold``/``EMBARGO_DAYS``/
``DEFAULT_TRAIN_YEARS`` (identical rolling quarterly-retrain design, so
folds line up 1:1 with H-20260917-02's), ``ml02.rank_ic_per_date``,
``ml02._read_year_at_dates`` (generic pyarrow-then-filter reader -- reused
only for *narrow* per-formation-date column reads: insider/short-interest/
13D/extra top-40 source roots, never for the 154-column alpha158 table,
see "Cache keyed by feature family" below), ``ml02._new_13d_flag``,
``ml02._benchmark_prices``, ``ml02.rank_tranches``/``equal_weight_tranches``/
``random_tranches``/``tranches_to_events``/``book_stats``/``cell_metrics``/
``benchmark_metrics``/``nw_tstat``/``monthly_returns``/``excess_block``/
``_percentiles``/``_pct``/``_num``/``_bp``/``_write_json``/``_json_default``/
``_ns``, and the column-name constants ``INSIDER_FEATURE_COLUMNS``/
``SHORT_INTEREST_FEATURE_COLUMNS``/``SHORT_INTEREST_ROOT``/``SEC13D_PATH``/
``FEATURE_COVERAGE_THRESHOLD``/``BENCHMARK_SYMBOLS``/``CASH_SYMBOL``/
``DATA_START``/``PRIMARY_COST_BPS``/``EXECUTION``/``MAX_NAMES``/
``TOP_DECILE_FRACTION``/``RANDOM_SEEDS``/``PLACEBO_SEEDS``/
``MIN_TRAIN_ROWS``/``RANKIC_MIN_NAMES``. ``ml02.MODEL_REGISTRY`` is
extended (not edited on disk) with this script's two new entries -- exactly
the extension point that module's own docstring names
("the only change that requires is a new entry in MODEL_REGISTRY").

Cache keyed by feature family (2026-09-18 lesson this must not repeat)
-----------------------------------------------------------------------------
``scripts/run_h20260917_01_insider_independent.py`` lost an entire 991-cell
run on 2026-09-18 because its cache key ignored ``--features-suffix`` and
silently reused narrow-universe artifacts under a path that looked
suffix-qualified but was not. Every cache path here is
``cache/<suffix-or-narrow>/<feature-family>/...`` (:func:`cache_dir_for`),
every report/summary file is ``report_<tag>.md`` /
``summary_<tag>.json`` with the same ``<suffix>_<family>`` tag
(:func:`report_path_for`/:func:`summary_path_for`), and the primary
``alpha158{suffix}`` root is a hard-fail (never a fallback) if missing for
the requested suffix -- see Deviation 5 above.

Memory discipline (3.9GB box, 2 usable cores, other jobs always running)
-----------------------------------------------------------------------------
The 154-column alpha158 table is never read a full year at a time and then
filtered in pandas (``pyarrow.read_table`` followed by ``.loc[...isin...]``
still materializes every trading day of that year before the filter runs --
for the broad universe, one year of alpha158 at full column width is
plausibly multiple GB). Instead :func:`_read_wide_features_at_dates` uses a
memory-capped DuckDB connection (``--duckdb-memory-limit``, 2 threads) to
push the formation-date filter down into the scan, so only the needed rows
are ever materialized into pandas. The per-formation-date-only "raw"
frame produced by :func:`stage_panel` is small regardless of table width
(one row per (formation date, symbol), not one row per trading day), so
:func:`stage_target`'s coverage pass and rank-normalization pass, and
:func:`stage_train`'s fold loop, only ever need to hold **the formation
rows for the years one fold spans** (``panel_target/{year}.parquet``,
read via :func:`_load_panel_target_years`) -- never the whole multi-year,
all-symbols, 154-column panel at once. One fold's data is loaded once and
reused for every ``--models`` entry and every placebo seed on that fold
before being dropped (``del`` + ``gc.collect()``), rather than re-reading
per model/seed.

Stages (resumable; the cache directory is the one thing making a stage a
no-op on rerun -- pass ``--force`` to rebuild)
-----------------------------------------------------------------------------
``panel``      universe cohorts -> formation frame; wide open/close price
               matrices + benchmark ETF returns (cached once, not
               per-fold: these are one column *per symbol*, not per
               symbol-feature, so they are cheap even at 9,191 symbols);
               raw (pre-rank-normalize) feature columns for the requested
               ``--feature-family``, written **year-partitioned**
               (``formation_raw/{year}.parquet``).
``target``     two-pass, year-by-year: pass 1 computes coverage across all
               years without holding more than one year in memory at a
               time; pass 2 rank-normalizes kept columns (a per-formation-
               date operation, so it is correct to do year-by-year -- a
               given formation date's rows never span two year files),
               computes both labels (``target_open1``, ``target_open21``),
               and writes ``panel_target/{year}.parquet``.
``train``      per (label, fold): load only that fold's years once; per
               ``--models`` entry, fit/predict/record validation+test Rank
               IC and ICIR, plus (unless ``--skip-placebo``) 5
               shuffled-label placebo refits scored on the validation role
               only (matching H-20260917-02's own placebo usage: only the
               *validation*-role placebo IC feeds the refutation check,
               never a placebo portfolio -- built here only as an IC
               distribution, not priced, to control compute).
``portfolio``  TopkDropoutStrategy(50, 5) (primary) and top-decile equal
               weight capped at 100 (secondary, for H-20260917-02
               comparability), same-size random x5 seeds, momentum twin,
               insider twin -- every cell priced over the union of every
               fold's test dates, price hygiene on, ``next_open``
               execution, 10bp/side.
``report``     Rank IC/ICIR vs Qlib's published CSI300 numbers, SPMO/SPY/
               IWM comparison, the card's literal refutation criteria,
               deviations, ``summary_<tag>.json`` and ``report_<tag>.md``.
"""

from __future__ import annotations

import argparse
import gc
import importlib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from open_composer.research.features import price_hygiene  # noqa: E402
from open_composer.research.features.alpha158 import alpha158_columns  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel import loop as kernel_loop  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    DEFAULT_MIN_COHORT_SYMBOLS,
    RebalanceEvent,
    returns_from_weight_schedule,
)
from open_composer.research.kernel.vol_matched import cagr_excess_vol_matched  # noqa: E402

ml02 = importlib.import_module("scripts.run_h20260917_02_ml_ranking")

ITERATION_ID = "h20260918_03_qlib_recipes"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_ROOT = OUT_DIR / "cache"
FEATURES_ROOT = ROOT / "data" / "features"
CONFIG_ROOT = ROOT / "config" / "feature_sets"

ALPHA158_COLUMNS: tuple[str, ...] = tuple(alpha158_columns())
ALPHA158_COLUMN_SET = frozenset(ALPHA158_COLUMNS)

LABELS: tuple[str, ...] = ("open1", "open21")
LABEL_HORIZON_DAYS: dict[str, int] = {"open1": 1, "open21": 21}
TARGET_COLUMNS: dict[str, str] = {"open1": "target_open1", "open21": "target_open21"}
LABEL_LEAD_DAYS = 1  # next-open executable, matches Qlib's Ref($close,-2)/Ref($close,-1)-1
MODEL_NAMES: tuple[str, ...] = ("ridge", "qlib_lgbm", "double_ensemble")
FEATURE_FAMILIES: tuple[str, ...] = ("alpha158", "layered")

TOPK = 50
N_DROP = 5
TOP_DECILE_FRACTION = ml02.TOP_DECILE_FRACTION
MAX_NAMES = ml02.MAX_NAMES
BENCHMARK_SYMBOLS = ml02.BENCHMARK_SYMBOLS
CASH_SYMBOL = ml02.CASH_SYMBOL
DATA_START = ml02.DATA_START
PRIMARY_COST_BPS = ml02.PRIMARY_COST_BPS
EXECUTION = ml02.EXECUTION
EMBARGO_DAYS = ml02.EMBARGO_DAYS
DEFAULT_TRAIN_YEARS = ml02.DEFAULT_TRAIN_YEARS
RANDOM_SEEDS = ml02.RANDOM_SEEDS
PLACEBO_SEEDS = ml02.PLACEBO_SEEDS
MIN_TRAIN_ROWS = ml02.MIN_TRAIN_ROWS
RANKIC_MIN_NAMES = ml02.RANKIC_MIN_NAMES
FEATURE_COVERAGE_THRESHOLD = ml02.FEATURE_COVERAGE_THRESHOLD
INSIDER_FEATURE_COLUMNS = ml02.INSIDER_FEATURE_COLUMNS
SHORT_INTEREST_FEATURE_COLUMNS = ml02.SHORT_INTEREST_FEATURE_COLUMNS
SEC13D_FEATURE_COLUMNS: tuple[str, ...] = ("new_13d_60d",)
MOMENTUM_TWIN_NUMERATOR = ml02.MOMENTUM_TWIN_NUMERATOR
MOMENTUM_TWIN_DENOMINATOR = ml02.MOMENTUM_TWIN_DENOMINATOR
INSIDER_TWIN_COLUMN = ml02.INSIDER_TWIN_COLUMN

#: Card refutation thresholds, literal (see module docstring's card excerpt).
REFUTE_RANKIC_THRESHOLD = 0.02
REFUTE_PLACEBO_SHARE_THRESHOLD = 0.5
REFUTE_WINDOW_START = pd.Timestamp("2024-01-01")

#: Qlib's own published CSI300 + Alpha158 numbers (20-seed mean), from the
#: card verbatim -- the comparison table's right-hand column.
QLIB_PUBLISHED: dict[str, dict[str, float]] = {
    "qlib_lgbm": {"ic": 0.0448, "icir": 0.366, "rank_ic": 0.0469, "rank_icir": 0.388},
    "double_ensemble": {"ic": 0.0521, "icir": 0.422, "rank_ic": 0.0502, "rank_icir": 0.412},
}

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def suffix_tag(suffix: str) -> str:
    return suffix.lstrip("_") if suffix else "narrow"


def family_tag(feature_family: str) -> str:
    return feature_family


def cache_dir_for(suffix: str, feature_family: str) -> Path:
    """``cache/<suffix-or-narrow>/<feature-family>/`` -- see module
    docstring's "Cache keyed by feature family" section.
    """
    return CACHE_ROOT / suffix_tag(suffix) / family_tag(feature_family)


def run_tag(suffix: str, feature_family: str) -> str:
    return f"{suffix_tag(suffix)}_{family_tag(feature_family)}"


def report_path_for(suffix: str, feature_family: str) -> Path:
    return OUT_DIR / f"report_{run_tag(suffix, feature_family)}.md"


def summary_path_for(suffix: str, feature_family: str) -> Path:
    return OUT_DIR / f"summary_{run_tag(suffix, feature_family)}.json"


# --------------------------------------------------------------------------
# DuckDB-backed wide-feature reader (see module docstring's "Memory
# discipline" section for why this is not plain pyarrow-then-filter).
# --------------------------------------------------------------------------

_DUCKDB_CONN: duckdb.DuckDBPyConnection | None = None
_DUCKDB_MEMORY_LIMIT = "900MB"


def configure_duckdb(memory_limit: str) -> None:
    global _DUCKDB_CONN, _DUCKDB_MEMORY_LIMIT
    _DUCKDB_MEMORY_LIMIT = memory_limit
    _DUCKDB_CONN = duckdb.connect(config={"memory_limit": memory_limit, "threads": "2"})


def _duckdb() -> duckdb.DuckDBPyConnection:
    global _DUCKDB_CONN
    if _DUCKDB_CONN is None:
        _DUCKDB_CONN = duckdb.connect(config={"memory_limit": _DUCKDB_MEMORY_LIMIT, "threads": "2"})
    return _DUCKDB_CONN


def _read_wide_features_at_dates(
    root: Path, year: int, columns: list[str], dates: set[pd.Timestamp]
) -> pd.DataFrame:
    """Same contract as ``ml02._read_year_at_dates`` (returns ``symbol``,
    ``trade_date``, ``*columns``) but the formation-date filter is pushed
    into a memory-capped DuckDB scan instead of a pandas ``.loc`` filter
    applied *after* pyarrow has already materialized the whole year -- see
    module docstring. Only used for the wide (154+ column) alpha158/layered
    feature reads; narrow (few-column) reads still use
    ``ml02._read_year_at_dates`` (cheap either way).
    """
    path = root / f"{year}.parquet"
    if not path.exists() or not dates:
        return pd.DataFrame(columns=["symbol", "trade_date", *columns])
    date_list = sorted(dates)
    placeholders = ",".join("?" for _ in date_list)
    col_list = ", ".join(f'"{c}"' for c in ["symbol", "trade_date", *columns])
    query = f"SELECT {col_list} FROM read_parquet(?) WHERE trade_date IN ({placeholders})"
    params: list[Any] = [str(path), *[d.to_pydatetime() for d in date_list]]
    frame = _duckdb().execute(query, params).df()
    frame["trade_date"] = ml02._ns(frame["trade_date"])
    frame["symbol"] = frame["symbol"].astype(str)
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    return frame


# --------------------------------------------------------------------------
# model registry additions -- see ml02.RankingModel Protocol:
# fit(X, y, groups) -> None, predict(X) -> np.ndarray.
# --------------------------------------------------------------------------

#: Qlib's published LightGBM-Alpha158 hyperparameters
#: (``workflow_config_lightgbm_Alpha158.yaml``), verbatim except
#: ``num_threads`` -- see module docstring Deviation 1.
QLIB_LGBM_PARAMS: dict[str, Any] = {
    "objective": "regression",  # the yaml's "loss: mse"
    "learning_rate": 0.2,
    "colsample_bytree": 0.8879,
    "subsample": 0.8789,
    "lambda_l1": 205.6999,
    "lambda_l2": 580.9768,
    "max_depth": 8,
    "num_leaves": 210,
    "num_threads": 2,
    "verbosity": -1,
    "seed": 0,
}
QLIB_LGBM_NUM_BOOST_ROUND = 1000
QLIB_LGBM_EARLY_STOPPING_ROUNDS = 50
#: Internal early-stopping holdout -- see module docstring Deviation 2 and
#: this class's own docstring.
QLIB_LGBM_VALID_TAIL_FRACTION = 0.1


@dataclass
class QlibLightGBMModel:
    """Qlib's published LightGBM-Alpha158 recipe. ``num_boost_round=1000``/
    ``early_stopping_rounds=50`` are ``qlib.contrib.model.gbdt.LGBModel``'s
    own defaults (not among the card's 8 listed hyperparameters). Early
    stopping needs a validation slice that this registry's
    ``fit(X, y, groups)`` interface does not provide, so the temporally
    last ``QLIB_LGBM_VALID_TAIL_FRACTION`` of the training rows (ordered by
    ``groups``, i.e. formation date) is held out for early stopping only --
    it is still training data (from the same fold's train window), never
    the fold's own validation/test rows. Falls back to fitting on the full
    set with a self-referential "validation" set when the split would
    leave either side smaller than 5 rows (tiny synthetic panels in tests):
    early stopping degenerates to "however many of the 1000 rounds help
    training loss", which is fine for a shape/contract test and never hit
    on real fold sizes (``MIN_TRAIN_ROWS`` = 200).
    """

    params: dict[str, Any] = field(default_factory=lambda: dict(QLIB_LGBM_PARAMS))
    _booster: Any = field(default=None, init=False, repr=False)

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        order = np.argsort(groups, kind="stable")
        n = len(order)
        cut = max(1, int(round(n * (1.0 - QLIB_LGBM_VALID_TAIL_FRACTION))))
        train_idx, valid_idx = order[:cut], order[cut:]
        if len(train_idx) < 5 or len(valid_idx) < 5:
            train_idx = valid_idx = order
        train_set = lgb.Dataset(X[train_idx], label=y[train_idx])
        valid_set = lgb.Dataset(X[valid_idx], label=y[valid_idx], reference=train_set)
        self._booster = lgb.train(
            self.params,
            train_set,
            num_boost_round=QLIB_LGBM_NUM_BOOST_ROUND,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(QLIB_LGBM_EARLY_STOPPING_ROUNDS, verbose=False)],
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._booster is None:
            raise RuntimeError("QlibLightGBMModel.predict called before fit")
        best = self._booster.best_iteration or self._booster.current_iteration()
        return self._booster.predict(X, num_iteration=best)


#: Qlib's published DoubleEnsemble-Alpha158 recipe
#: (``workflow_config_doubleensemble_Alpha158.yaml``), verbatim. Sub-model
#: hyperparameters are the card's own "子模型超参同上" instruction: identical
#: to :data:`QLIB_LGBM_PARAMS`.
DOUBLE_ENSEMBLE_NUM_MODELS = 3
DOUBLE_ENSEMBLE_ALPHA1 = 1.0
DOUBLE_ENSEMBLE_ALPHA2 = 1.0
DOUBLE_ENSEMBLE_BINS_SR = 10
DOUBLE_ENSEMBLE_BINS_FS = 5
DOUBLE_ENSEMBLE_DECAY = 0.5
DOUBLE_ENSEMBLE_SAMPLE_RATIOS: tuple[float, ...] = (0.8, 0.7, 0.6, 0.5, 0.4)
DOUBLE_ENSEMBLE_SUB_WEIGHTS: tuple[float, ...] = (1.0, 1.0, 1.0)
DOUBLE_ENSEMBLE_EPOCHS = 28
#: Weight floor so SR never zeroes a sample out entirely (a reasoned,
#: disclosed choice -- see module docstring Deviation 3).
DOUBLE_ENSEMBLE_WEIGHT_FLOOR = 0.2


def _rank01(values: np.ndarray) -> np.ndarray:
    """Each value's percentile rank in ``[0, 1]`` (0 = smallest)."""
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype="float64")
    ranks[order] = np.arange(len(values), dtype="float64")
    denom = max(1, len(values) - 1)
    return ranks / denom


def _quantile_bin(values: np.ndarray, n_bins: int) -> np.ndarray:
    """Bin index in ``[0, n_bins)`` by rank, 0 = lowest value."""
    pct = _rank01(values)
    return np.minimum((pct * n_bins).astype("int64"), n_bins - 1)


@dataclass
class DoubleEnsembleModel:
    """See module docstring Deviation 3 for what this reconstructs and why.
    ``num_models`` GBM sub-models are trained in sequence; between
    sub-models, sample reweighting (SR) down-weights samples whose loss is
    both high (``alpha1``) and unstable across a within-training checkpoint
    comparison (``alpha2``), bucketed into ``bins_sr`` quantile bins with a
    ``decay``-blended update against the previous weights; feature
    selection (FS) buckets LightGBM's own gain importance into ``bins_fs``
    quantile bins and randomly keeps ``sample_ratios[bin]`` of each bin's
    features for the next sub-model (bin 0 = lowest importance ->
    ``sample_ratios[-1]``, the smallest keep fraction; the top bin keeps
    ``sample_ratios[0]``, the largest). Final prediction is the
    ``sub_weights``-weighted average of every sub-model's prediction on its
    own selected feature subset.
    """

    num_models: int = DOUBLE_ENSEMBLE_NUM_MODELS
    alpha1: float = DOUBLE_ENSEMBLE_ALPHA1
    alpha2: float = DOUBLE_ENSEMBLE_ALPHA2
    bins_sr: int = DOUBLE_ENSEMBLE_BINS_SR
    bins_fs: int = DOUBLE_ENSEMBLE_BINS_FS
    decay: float = DOUBLE_ENSEMBLE_DECAY
    sample_ratios: tuple[float, ...] = DOUBLE_ENSEMBLE_SAMPLE_RATIOS
    sub_weights: tuple[float, ...] = DOUBLE_ENSEMBLE_SUB_WEIGHTS
    epochs: int = DOUBLE_ENSEMBLE_EPOCHS
    enable_sr: bool = True
    enable_fs: bool = True
    _submodels: list[tuple[Any, np.ndarray]] = field(default_factory=list, init=False, repr=False)

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        del groups
        n_rows, n_features = X.shape
        weights = np.ones(n_rows, dtype="float64")
        feature_mask = np.ones(n_features, dtype=bool)
        self._submodels = []
        rng = np.random.default_rng(0)
        mid_iter = max(1, self.epochs // 2)
        for k in range(self.num_models):
            cols = np.flatnonzero(feature_mask)
            X_k = X[:, cols]
            params = dict(QLIB_LGBM_PARAMS)
            train_set = lgb.Dataset(X_k, label=y, weight=weights)
            booster = lgb.train(params, train_set, num_boost_round=self.epochs)
            self._submodels.append((booster, cols))
            last = k == self.num_models - 1

            if self.enable_sr and not last:
                mid_pred = booster.predict(X_k, num_iteration=mid_iter)
                final_pred = booster.predict(X_k, num_iteration=self.epochs)
                loss_level = (y - final_pred) ** 2
                loss_instability = np.abs((y - final_pred) ** 2 - (y - mid_pred) ** 2)
                h_value = self.alpha1 * _rank01(loss_level) + self.alpha2 * _rank01(
                    loss_instability
                )
                bins = _quantile_bin(h_value, self.bins_sr)
                target = 1.0 - bins.astype("float64") / max(1, self.bins_sr - 1)
                target = (
                    DOUBLE_ENSEMBLE_WEIGHT_FLOOR + (1.0 - DOUBLE_ENSEMBLE_WEIGHT_FLOOR) * target
                )
                weights = self.decay * weights + (1.0 - self.decay) * target
                weights = weights * len(weights) / weights.sum()

            if self.enable_fs and not last:
                gain = booster.feature_importance(importance_type="gain").astype("float64")
                fs_bins = _quantile_bin(gain, self.bins_fs)
                keep = np.zeros(len(cols), dtype=bool)
                for b in range(self.bins_fs):
                    idx_in_bin = np.flatnonzero(fs_bins == b)
                    if len(idx_in_bin) == 0:
                        continue
                    ratio_idx = min(self.bins_fs - 1 - b, len(self.sample_ratios) - 1)
                    ratio = self.sample_ratios[ratio_idx]
                    n_keep = max(1, int(round(ratio * len(idx_in_bin))))
                    n_keep = min(n_keep, len(idx_in_bin))
                    chosen = rng.choice(idx_in_bin, size=n_keep, replace=False)
                    keep[chosen] = True
                new_cols = cols[keep] if keep.any() else cols
                feature_mask = np.zeros(n_features, dtype=bool)
                feature_mask[new_cols] = True

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._submodels:
            raise RuntimeError("DoubleEnsembleModel.predict called before fit")
        preds = [booster.predict(X[:, cols]) for booster, cols in self._submodels]
        weights = np.asarray(self.sub_weights[: len(preds)], dtype="float64")
        weights = weights / weights.sum()
        return np.average(np.column_stack(preds), axis=1, weights=weights)


MODEL_REGISTRY: dict[str, Callable[[], Any]] = {
    "ridge": lambda: ml02.RidgeRankingModel(alpha=ml02.RIDGE_ALPHA),
    "qlib_lgbm": lambda: QlibLightGBMModel(),
    "double_ensemble": lambda: DoubleEnsembleModel(),
}
#: Extend, never edit, ml02's own registry -- see module docstring's "Reuse"
#: section: this is that module's own documented extension point.
ml02.MODEL_REGISTRY.update(MODEL_REGISTRY)


# --------------------------------------------------------------------------
# TopkDropoutStrategy(topk, n_drop)
# --------------------------------------------------------------------------


def topk_dropout_tranches(
    frame: pd.DataFrame,
    score_col: str,
    dates: list[pd.Timestamp],
    *,
    topk: int = TOPK,
    n_drop: int = N_DROP,
) -> dict[pd.Timestamp, dict[str, float]]:
    """Qlib's ``TopkDropoutStrategy``: hold ``topk`` names; at each
    rebalance, sell at most ``n_drop`` of the *worst-ranked currently held*
    names and buy the best-ranked names not already held to refill up to
    ``topk`` -- turnover-limited, unlike rebuilding the top decile from
    scratch every period. A name that has left the day's pool entirely
    (e.g. delisted) is force-dropped regardless of ``n_drop`` -- disclosed
    here rather than silently either violating the pool or the budget: on
    a clean pool with no disappearances, replacements per period are
    exactly ``min(n_drop, len(held))``.
    """
    held: set[str] = set()
    out: dict[pd.Timestamp, dict[str, float]] = {}
    for date in dates:
        day = frame.loc[frame["formation_date"] == date, ["symbol", score_col]].dropna()
        day = day.drop_duplicates("symbol")
        ranked = day.sort_values(score_col, ascending=False)
        pool = set(ranked["symbol"])
        score_of = dict(zip(ranked["symbol"], ranked[score_col], strict=True))

        alive_held = [s for s in held if s in pool]
        alive_sorted = sorted(alive_held, key=lambda s: score_of[s])  # worst first
        voluntary_drop_n = min(n_drop, len(alive_sorted))
        voluntary_drop = set(alive_sorted[:voluntary_drop_n])
        kept = [s for s in alive_held if s not in voluntary_drop]

        need = max(0, topk - len(kept))
        buy = [s for s in ranked["symbol"] if s not in kept][:need]
        new_held = kept + buy
        held = set(new_held)
        out[date] = {s: 1.0 / len(new_held) for s in new_held} if new_held else {}
    return out


# --------------------------------------------------------------------------
# stage: panel
# --------------------------------------------------------------------------


def _feature_roots(suffix: str) -> dict[str, Path]:
    return {
        "universe": FEATURES_ROOT / f"universe{suffix}",
        "daily": FEATURES_ROOT / f"daily{suffix}",
        "insider": FEATURES_ROOT / f"insider{suffix}",
        "alpha158": FEATURES_ROOT / f"alpha158{suffix}",
    }


def _require_root(name: str, root: Path) -> None:
    if not any(root.glob("20*.parquet")):
        raise SystemExit(
            f"panel: {name} root {root} has no year files yet -- refusing to silently fall "
            "back to a narrower table (see module docstring Deviation 5)"
        )


def _resolve_layered_root(name: str, suffix: str, deviations: list[str]) -> Path | None:
    """``{name}{suffix}`` if it exists, else the narrow ``{name}`` with a
    disclosed fallback, else ``None`` if neither exists. Only used for the
    "layered" family's *extra* source roots (never alpha158/universe/daily/
    insider, see :func:`_require_root`) -- see module docstring Deviation 4.
    """
    suffixed = FEATURES_ROOT / f"{name}{suffix}"
    if any(suffixed.glob("20*.parquet")):
        return suffixed
    narrow = FEATURES_ROOT / name
    if suffix and any(narrow.glob("20*.parquet")):
        deviations.append(
            f"{name}{suffix} 不存在，回退到窄库 {name}（仅用于跨库 top-40 的补充列；"
            "宽池子上这些列的实际覆盖率会在 target 阶段的覆盖率清单里如实反映，"
            "预计会被 50% 覆盖率门槛过滤掉大部分）"
        )
        return narrow
    if not suffix and any(narrow.glob("20*.parquet")):
        return narrow
    return None


def _screened_top40_extra_factors(suffix: str, deviations: list[str]) -> dict[str, list[str]]:
    """``{source_root: [factor, ...]}`` for the screened top-40 factors that
    are *not* already alpha158 columns (21 of the 40 are) -- see module
    docstring Deviation 4 for the ``_broad`` json fallback.
    """
    suffixed = CONFIG_ROOT / f"screened_top40_recent{suffix}.json"
    narrow = CONFIG_ROOT / "screened_top40_recent.json"
    path = suffixed if suffixed.exists() else narrow
    if not path.exists():
        return {}
    if path == narrow and suffix:
        deviations.append(
            f"config/feature_sets/screened_top40_recent{suffix}.json 不存在，"
            "回退到窄库版本 screened_top40_recent.json 的因子名单"
        )
    payload = json.loads(path.read_text())
    by_root: dict[str, list[str]] = {}
    for entry in payload.get("factors", []):
        factor = entry["factor"]
        if factor in ALPHA158_COLUMN_SET:
            continue
        by_root.setdefault(entry["source_root"], []).append(factor)
    return by_root


def _benchmark_and_price_matrices(
    daily_root: Path, years: list[int]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """``(close_wide, open_wide, bench_returns)`` -- mirrors
    ``ml02.stage_panel``'s own price-matrix construction (lines ~550-596),
    written standalone here since that logic is embedded in ml02's
    monolithic ``stage_panel`` rather than factored into a reusable
    function. Cheap regardless of table width: only ``open``/``close`` are
    read (column-pruned pyarrow, no DuckDB needed -- 2 float columns times
    every symbol times every trading day is small next to a 154-column
    read of the same shape).
    """
    close_frames: list[pd.DataFrame] = []
    open_frames: list[pd.DataFrame] = []
    for year in years:
        path = daily_root / f"{year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(path, columns=["symbol", "trade_date", "open", "close"])
        frame = table.to_pandas()
        del table
        frame["trade_date"] = ml02._ns(frame["trade_date"])
        frame["symbol"] = frame["symbol"].astype(str)
        frame = frame.drop_duplicates(["trade_date", "symbol"], keep="last")
        close_frames.append(frame.pivot(index="trade_date", columns="symbol", values="close"))
        open_frames.append(frame.pivot(index="trade_date", columns="symbol", values="open"))
        del frame
    close_wide = pd.concat(close_frames).sort_index().astype("float64")
    open_wide = pd.concat(open_frames).sort_index().astype("float64")
    del close_frames, open_frames
    close_wide = close_wide.reindex(columns=sorted(close_wide.columns))
    open_wide = open_wide.reindex(columns=close_wide.columns)
    close_wide.columns = close_wide.columns.astype(str)
    open_wide.columns = open_wide.columns.astype(str)
    close_wide.index = ml02._ns(close_wide.index)
    open_wide.index = ml02._ns(open_wide.index)

    bench_close, bench_open = ml02._benchmark_prices((*BENCHMARK_SYMBOLS, CASH_SYMBOL))
    bench_close = bench_close.reindex(close_wide.index)
    bench_open = bench_open.reindex(close_wide.index)
    close_wide[CASH_SYMBOL] = bench_close[CASH_SYMBOL]
    open_wide[CASH_SYMBOL] = bench_open[CASH_SYMBOL]
    for sym in BENCHMARK_SYMBOLS:
        if sym not in close_wide.columns:
            close_wide[sym] = bench_close[sym]
            open_wide[sym] = bench_open[sym]
    bench_returns = bench_close.pct_change(fill_method=None)
    bench_returns.index.name = "trade_date"
    return close_wide, open_wide, bench_returns


def stage_panel(args: argparse.Namespace) -> None:
    cache_dir = cache_dir_for(args.features_suffix, args.feature_family)
    manifest_path = cache_dir / "panel_manifest.json"
    if manifest_path.exists() and not args.force:
        _log(f"panel: {manifest_path} present -- reusing (pass --force to rebuild)")
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    deviations: list[str] = []
    suffix = args.features_suffix
    roots = _feature_roots(suffix)
    _require_root("alpha158", roots["alpha158"])
    _require_root("universe", roots["universe"])
    _require_root("daily", roots["daily"])
    _require_root("insider", roots["insider"])

    alpha_years = sorted(
        int(p.stem) for p in roots["alpha158"].glob("20*.parquet") if p.stem.isdigit()
    )
    daily_years = sorted(
        int(p.stem) for p in roots["daily"].glob("20*.parquet") if p.stem.isdigit()
    )
    years = [y for y in (args.years or alpha_years) if y in alpha_years and y in daily_years]
    if not years:
        raise SystemExit("panel: no years overlap between alpha158 and daily roots")
    _log(f"panel: features_suffix={suffix!r} feature_family={args.feature_family!r} years={years}")

    universe = load_universe_panel(roots["universe"], years=years)
    universe["month_end"] = ml02._ns(universe["month_end"])
    universe["symbol"] = universe["symbol"].astype(str)
    cohort_sizes = universe.groupby("month_end").size()
    formation_dates = sorted(
        pd.Timestamp(d) for d, n in cohort_sizes.items() if n >= DEFAULT_MIN_COHORT_SYMBOLS
    )
    if not formation_dates:
        raise SystemExit("panel: no cohort dates clear DEFAULT_MIN_COHORT_SYMBOLS")
    formation_dates_set = set(formation_dates)
    _log(
        f"panel: universe {len(universe):,} rows, {universe['symbol'].nunique():,} symbols, "
        f"{len(formation_dates)} cohort dates "
        f"{formation_dates[0].date()}..{formation_dates[-1].date()}"
    )

    close_wide, open_wide, bench_returns = _benchmark_and_price_matrices(roots["daily"], years)
    close_wide.to_parquet(cache_dir / "close_wide.parquet")
    open_wide.to_parquet(cache_dir / "open_wide.parquet")
    bench_returns.to_parquet(cache_dir / "benchmark_returns.parquet")
    trading_calendar = close_wide.index
    _log(
        f"panel: price matrix {close_wide.shape[0]} sessions x {close_wide.shape[1]} symbols, "
        f"{trading_calendar[0].date()}..{trading_calendar[-1].date()}"
    )

    layered_roots: dict[str, Path | None] = {}
    extra_factors_by_root: dict[str, list[str]] = {}
    if args.feature_family == "layered":
        extra_factors_by_root = _screened_top40_extra_factors(suffix, deviations)
        for source_root in extra_factors_by_root:
            layered_roots[source_root] = _resolve_layered_root(source_root, suffix, deviations)

    formation_raw_dir = cache_dir / "formation_raw"
    formation_raw_dir.mkdir(parents=True, exist_ok=True)
    raw_coverage_numer: dict[str, float] = {}
    raw_coverage_denom = 0
    raw_columns_seen: set[str] = set()

    for year in years:
        rows = universe.loc[
            (universe["month_end"].isin(formation_dates)) & (universe["month_end"].dt.year == year),
            ["month_end", "symbol", "adv_rank", "dollar_adv", "close"],
        ].rename(columns={"month_end": "formation_date"})
        if rows.empty:
            continue
        rows["adv_rank"] = rows["adv_rank"].astype("int64")

        alpha_frame = _read_wide_features_at_dates(
            roots["alpha158"], year, list(ALPHA158_COLUMNS), formation_dates_set
        )
        rows = rows.merge(
            alpha_frame.rename(columns={"trade_date": "formation_date"}),
            on=["formation_date", "symbol"],
            how="left",
        )
        del alpha_frame

        daily_twin = ml02._read_year_at_dates(
            roots["daily"],
            year,
            [MOMENTUM_TWIN_NUMERATOR, MOMENTUM_TWIN_DENOMINATOR],
            formation_dates_set,
        )
        rows = rows.merge(
            daily_twin.rename(
                columns={
                    "trade_date": "formation_date",
                    MOMENTUM_TWIN_NUMERATOR: "_raw_momentum_252_21",
                    MOMENTUM_TWIN_DENOMINATOR: "_raw_vol_63",
                }
            ),
            on=["formation_date", "symbol"],
            how="left",
        )

        insider_frame = ml02._read_year_at_dates(
            roots["insider"], year, list(INSIDER_FEATURE_COLUMNS), formation_dates_set
        )
        insider_frame = insider_frame.rename(columns={"trade_date": "formation_date"})
        rows = rows.merge(insider_frame, on=["formation_date", "symbol"], how="left")
        rows["_raw_net_buy_usd_60d"] = rows.get(INSIDER_TWIN_COLUMN, np.nan)
        if args.feature_family != "layered":
            rows = rows.drop(columns=list(INSIDER_FEATURE_COLUMNS), errors="ignore")

        if args.feature_family == "layered":
            for source_root, factors in extra_factors_by_root.items():
                root = layered_roots.get(source_root)
                if root is None:
                    continue
                extra = ml02._read_year_at_dates(root, year, factors, formation_dates_set)
                rows = rows.merge(
                    extra.rename(columns={"trade_date": "formation_date"}),
                    on=["formation_date", "symbol"],
                    how="left",
                )

            si_frame = ml02._read_year_at_dates(
                ml02.SHORT_INTEREST_ROOT,
                year,
                list(SHORT_INTEREST_FEATURE_COLUMNS),
                formation_dates_set,
            )
            rows = rows.merge(
                si_frame.rename(columns={"trade_date": "formation_date"}),
                on=["formation_date", "symbol"],
                how="left",
            )
            rows["new_13d_60d"] = ml02._new_13d_flag(rows, trading_calendar)

        rows = rows.reset_index(drop=True)
        rows.to_parquet(formation_raw_dir / f"{year}.parquet", index=False)

        candidate_cols = [
            c
            for c in rows.columns
            if c
            not in (
                "formation_date",
                "symbol",
                "adv_rank",
                "dollar_adv",
                "close",
                "_raw_momentum_252_21",
                "_raw_vol_63",
                "_raw_net_buy_usd_60d",
            )
        ]
        raw_columns_seen.update(candidate_cols)
        for column in candidate_cols:
            raw_coverage_numer[column] = raw_coverage_numer.get(column, 0.0) + float(
                rows[column].notna().sum()
            )
        raw_coverage_denom += len(rows)
        out_path = formation_raw_dir / f"{year}.parquet"
        _log(f"panel: {year}: wrote {len(rows):,} formation rows -> {out_path}")
        del rows

    coverage = {
        c: (raw_coverage_numer.get(c, 0.0) / raw_coverage_denom if raw_coverage_denom else 0.0)
        for c in sorted(raw_columns_seen)
    }
    manifest = {
        "features_suffix": suffix,
        "feature_family": args.feature_family,
        "years": years,
        "formation_dates": [d.date().isoformat() for d in formation_dates],
        "last_price_date": trading_calendar[-1].date().isoformat(),
        "price_sessions": int(len(trading_calendar)),
        "raw_columns": sorted(raw_columns_seen),
        "raw_feature_coverage": coverage,
        "extra_factors_by_root": extra_factors_by_root,
        "layered_roots_resolved": {
            k: (str(v.relative_to(ROOT)) if v else None) for k, v in layered_roots.items()
        },
        "deviations": deviations,
        "duckdb_memory_limit": _DUCKDB_MEMORY_LIMIT,
    }
    ml02._write_json(manifest_path, manifest)
    _log(f"panel: wrote manifest {manifest_path} ({len(deviations)} deviations recorded)")


# --------------------------------------------------------------------------
# stage: target
# --------------------------------------------------------------------------


def _load_panel_manifest(cache_dir: Path) -> dict[str, Any]:
    return json.loads((cache_dir / "panel_manifest.json").read_text())


def _forward_open_return(
    open_sanitized: pd.DataFrame, formation: pd.DataFrame, lead: int, horizon: int
) -> pd.Series:
    """``open[t+lead+horizon] / open[t+lead] - 1`` per (formation_date,
    symbol) row -- Qlib's ``Ref($close,-2)/Ref($close,-1)-1`` generalized to
    ``open`` and an arbitrary horizon (``lead=1, horizon=1`` reproduces the
    1-day Qlib label exactly; ``lead=1, horizon=21`` is this card's 21-day
    equivalent). One whole-matrix double-shift, then one ``.loc`` lookup
    per formation date, same pattern as ``ml02._forward_return_lookup``.
    """
    numer = open_sanitized.shift(-(lead + horizon))
    denom = open_sanitized.shift(-lead)
    fwd = numer / denom - 1.0
    out = pd.Series(np.nan, index=formation.index, dtype="float64")
    for date, idx in formation.groupby("formation_date").indices.items():
        if date not in fwd.index:
            continue
        row = fwd.loc[date]
        symbols = formation.loc[idx, "symbol"]
        out.loc[idx] = row.reindex(symbols).to_numpy()
    return out


def stage_target(args: argparse.Namespace) -> None:
    cache_dir = cache_dir_for(args.features_suffix, args.feature_family)
    target_dir = cache_dir / "panel_target"
    feature_manifest_path = cache_dir / "feature_manifest.json"
    if feature_manifest_path.exists() and not args.force:
        _log(f"target: {feature_manifest_path} present -- reusing (pass --force to rebuild)")
        return
    manifest = _load_panel_manifest(cache_dir)
    years: list[int] = manifest["years"]
    formation_raw_dir = cache_dir / "formation_raw"

    _log("target: pass 1/2 -- coverage across years")
    coverage_numer: dict[str, float] = {}
    total_rows = 0
    candidate_columns: list[str] = []
    for year in years:
        path = formation_raw_dir / f"{year}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        if not candidate_columns:
            candidate_columns = [
                c
                for c in frame.columns
                if c
                not in (
                    "formation_date",
                    "symbol",
                    "adv_rank",
                    "dollar_adv",
                    "close",
                    "_raw_momentum_252_21",
                    "_raw_vol_63",
                    "_raw_net_buy_usd_60d",
                )
            ]
        for column in candidate_columns:
            coverage_numer[column] = coverage_numer.get(column, 0.0) + float(
                frame[column].notna().sum()
            )
        total_rows += len(frame)
        del frame
        gc.collect()

    coverage = {
        c: (coverage_numer.get(c, 0.0) / total_rows if total_rows else 0.0)
        for c in candidate_columns
    }
    kept_features = sorted(
        c for c in candidate_columns if coverage[c] >= FEATURE_COVERAGE_THRESHOLD
    )
    dropped_features = {
        c: coverage[c] for c in candidate_columns if coverage[c] < FEATURE_COVERAGE_THRESHOLD
    }
    _log(
        f"target: {len(candidate_columns)} candidate columns, {len(kept_features)} kept "
        f"(coverage >= {FEATURE_COVERAGE_THRESHOLD:.0%}), {len(dropped_features)} dropped"
    )

    _log("target: pass 2/2 -- rank-normalize + labels, year by year")
    close_wide = pd.read_parquet(cache_dir / "close_wide.parquet", columns=[])
    open_wide = pd.read_parquet(cache_dir / "open_wide.parquet")
    open_wide.index = ml02._ns(open_wide.index)
    trading_calendar = ml02._ns(close_wide.index)
    del close_wide
    close_full = pd.read_parquet(cache_dir / "close_wide.parquet")
    close_full.index = ml02._ns(close_full.index)
    _log("target: sanitizing price matrices (price hygiene)")
    close_sanitized, open_sanitized, hygiene_report = price_hygiene.sanitize_price_matrices(
        close_full, open_wide
    )
    del close_full, open_wide
    gc.collect()

    target_dir.mkdir(parents=True, exist_ok=True)
    rows_with_target = 0
    rows_total = 0
    for year in years:
        path = formation_raw_dir / f"{year}.parquet"
        if not path.exists():
            continue
        keep_cols = [
            "formation_date",
            "symbol",
            "adv_rank",
            "dollar_adv",
            "_raw_momentum_252_21",
            "_raw_vol_63",
            "_raw_net_buy_usd_60d",
            *kept_features,
        ]
        frame = pd.read_parquet(path, columns=[c for c in keep_cols if c != "close"])
        frame["formation_date"] = ml02._ns(frame["formation_date"])

        for label in LABELS:
            horizon = LABEL_HORIZON_DAYS[label]
            frame[TARGET_COLUMNS[label]] = _forward_open_return(
                open_sanitized, frame, LABEL_LEAD_DAYS, horizon
            )

        for column in kept_features:
            frame[column] = frame.groupby("formation_date")[column].rank(pct=True)

        rows_with_target += int(frame[TARGET_COLUMNS["open1"]].notna().sum())
        rows_total += len(frame)
        frame.to_parquet(target_dir / f"{year}.parquet", index=False)
        del frame
        gc.collect()

    feature_manifest = {
        "features_suffix": args.features_suffix,
        "feature_family": args.feature_family,
        "candidate_columns": candidate_columns,
        "features_kept": kept_features,
        "features_dropped_low_coverage": dropped_features,
        "coverage_threshold": FEATURE_COVERAGE_THRESHOLD,
        "labels": {label: TARGET_COLUMNS[label] for label in LABELS},
        "label_definition": (
            "open[t+1+h]/open[t+1]-1, h in {1, 21}; Qlib's Ref($close,-2)/Ref($close,-1)-1 "
            "generalized to open and to a 21-day horizon (see _forward_open_return)"
        ),
        "price_hygiene": {
            k: v for k, v in hygiene_report.manifest().items() if not isinstance(v, (list, dict))
        },
        "rows_with_target": rows_with_target,
        "rows_total": rows_total,
        "trading_calendar_sessions": int(len(trading_calendar)),
    }
    ml02._write_json(feature_manifest_path, feature_manifest)
    _log(f"target: wrote {feature_manifest_path}")


# --------------------------------------------------------------------------
# stage: train
# --------------------------------------------------------------------------


def _load_panel_target_years(cache_dir: Path, years: list[int], columns: list[str]) -> pd.DataFrame:
    target_dir = cache_dir / "panel_target"
    frames: list[pd.DataFrame] = []
    for year in years:
        path = target_dir / f"{year}.parquet"
        if not path.exists():
            continue
        table = pq.read_table(path, columns=columns)
        frames.append(table.to_pandas())
        del table
    if not frames:
        return pd.DataFrame(columns=columns)
    frame = pd.concat(frames, ignore_index=True)
    frame["formation_date"] = ml02._ns(frame["formation_date"])
    return frame


def _icir(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    arr = np.asarray(values, dtype="float64")
    std = float(arr.std(ddof=1))
    if not np.isfinite(std) or std <= 0:
        return None
    return float(arr.mean() / std)


def _shuffle_stable(frame: pd.DataFrame, target_col: str, seed: int) -> np.ndarray:
    """Same idea as ``ml02.shuffle_target_within_date`` (permute the target
    within each formation date, leaving NaNs alone) but seeded per
    ``(seed, date)`` rather than iterated once over one in-memory global
    panel -- this script loads and shuffles per fold, so the same formation
    date can be touched by more than one fold's load (H-20260917-02's
    documented validation/test role overlap across folds); seeding by date
    makes the permutation for a given date identical regardless of which
    fold's load produced it.
    """
    values = frame[target_col].to_numpy(dtype="float64").copy()
    dates = frame["formation_date"].to_numpy()
    for date in np.unique(dates):
        idx = np.flatnonzero(dates == date)
        valid = idx[~np.isnan(values[idx])]
        if len(valid) > 1:
            date_key = int(pd.Timestamp(date).value % (2**31 - 1))
            rng = np.random.default_rng([int(seed), date_key])
            values[valid] = rng.permutation(values[valid])
    return values


def stage_train(args: argparse.Namespace) -> None:
    cache_dir = cache_dir_for(args.features_suffix, args.feature_family)
    train_dir = cache_dir / "train"
    train_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_panel_manifest(cache_dir)
    feature_manifest = json.loads((cache_dir / "feature_manifest.json").read_text())
    feature_columns: list[str] = feature_manifest["features_kept"]
    formation_dates = [pd.Timestamp(d) for d in manifest["formation_dates"]]
    trading_calendar = pd.DatetimeIndex(
        ml02._ns(pd.read_parquet(cache_dir / "close_wide.parquet", columns=[]).index)
    )
    train_years = args.train_years or DEFAULT_TRAIN_YEARS
    folds = ml02.build_folds(formation_dates, trading_calendar, train_years)
    ml02._write_json(
        train_dir / "folds.json",
        [
            {
                "fold_id": f.fold_id,
                "train_start": f.train_start,
                "train_cutoff": f.train_cutoff,
                "actual_train_years": round(f.actual_train_years, 2),
                "validation_dates": list(f.validation_dates),
                "test_dates": list(f.test_dates),
            }
            for f in folds
        ],
    )
    _log(f"train: {len(folds)} rolling quarterly folds, {len(feature_columns)} features kept")

    placebo_seeds = PLACEBO_SEEDS[: args.seeds] if args.seeds else PLACEBO_SEEDS
    id_columns = ["formation_date", "symbol"]

    for label in LABELS if not args.labels else args.labels:
        target_col = TARGET_COLUMNS[label]
        load_columns = [*id_columns, *feature_columns, target_col]
        per_model_test_frames: dict[str, list[pd.DataFrame]] = {m: [] for m in args.models}
        per_model_fold_records: dict[str, list[dict[str, Any]]] = {m: [] for m in args.models}
        per_model_placebo: dict[str, dict[int, list[float]]] = {
            m: {s: [] for s in placebo_seeds} for m in args.models
        }

        for fold in folds:
            years_needed = sorted(
                {
                    fold.train_start.year + i
                    for i in range(fold.test_dates[-1].year - fold.train_start.year + 1)
                }
            )
            frame = _load_panel_target_years(cache_dir, years_needed, load_columns)
            if frame.empty:
                for model_name in args.models:
                    per_model_fold_records[model_name].append(
                        {"fold_id": fold.fold_id, "skipped": "no panel_target rows for fold years"}
                    )
                continue
            train_frame = frame.loc[frame["formation_date"].isin(fold.train_dates)].dropna(
                subset=[*feature_columns, target_col]
            )
            validation_frame = frame.loc[
                frame["formation_date"].isin(fold.validation_dates)
            ].dropna(subset=feature_columns)
            test_frame = frame.loc[frame["formation_date"].isin(fold.test_dates)].dropna(
                subset=feature_columns
            )

            for model_name in args.models:
                key = f"{model_name}_{label}"
                fold_pred_path = train_dir / f"{key}_fold{fold.fold_id}_predictions.parquet"
                fold_record_path = train_dir / f"{key}_fold{fold.fold_id}.json"
                base_record = {
                    "fold_id": fold.fold_id,
                    "train_start": fold.train_start.date().isoformat(),
                    "train_cutoff": fold.train_cutoff.date().isoformat(),
                    "actual_train_years": round(fold.actual_train_years, 2),
                    "train_rows": int(len(train_frame)),
                }
                if fold_record_path.exists() and not args.force:
                    record = json.loads(fold_record_path.read_text())
                elif len(train_frame) < MIN_TRAIN_ROWS:
                    record = {
                        **base_record,
                        "skipped": f"train_rows {len(train_frame)} < {MIN_TRAIN_ROWS}",
                    }
                    ml02._write_json(fold_record_path, record)
                else:
                    model = MODEL_REGISTRY[model_name]()
                    X_train = train_frame[feature_columns].to_numpy(dtype="float64")
                    y_train = train_frame[target_col].to_numpy(dtype="float64")
                    groups_train = train_frame["formation_date"].to_numpy()
                    model.fit(X_train, y_train, groups_train)

                    record = dict(base_record)
                    if not validation_frame.empty:
                        val_pred = model.predict(
                            validation_frame[feature_columns].to_numpy(dtype="float64")
                        )
                        val_scored = validation_frame[
                            ["formation_date", "symbol", target_col]
                        ].copy()
                        val_scored["prediction"] = val_pred
                        val_ic = ml02.rank_ic_per_date(val_scored, "prediction", target_col)
                    else:
                        val_ic = []
                    record["validation_rankic_mean"] = (
                        float(np.mean([v for _, v in val_ic])) if val_ic else None
                    )
                    record["validation_rankic_icir"] = _icir([v for _, v in val_ic])
                    record["validation_rankic_n_dates"] = len(val_ic)

                    if not test_frame.empty:
                        test_pred = model.predict(
                            test_frame[feature_columns].to_numpy(dtype="float64")
                        )
                        out = test_frame[["formation_date", "symbol"]].copy()
                        out["prediction"] = test_pred
                        out["fold_id"] = fold.fold_id
                        out.to_parquet(fold_pred_path, index=False)
                        test_scored = test_frame[["formation_date", "symbol", target_col]].copy()
                        test_scored["prediction"] = test_pred
                        test_ic = ml02.rank_ic_per_date(test_scored, "prediction", target_col)
                    else:
                        test_ic = []
                    record["test_rankic_mean"] = (
                        float(np.mean([v for _, v in test_ic])) if test_ic else None
                    )
                    record["test_rankic_icir"] = _icir([v for _, v in test_ic])
                    record["test_rankic_n_dates"] = len(test_ic)
                    ml02._write_json(fold_record_path, record)
                    del model

                per_model_fold_records[model_name].append(record)
                if fold_pred_path.exists():
                    per_model_test_frames[model_name].append(pd.read_parquet(fold_pred_path))

                if not args.skip_placebo:
                    for seed in placebo_seeds:
                        placebo_path = train_dir / f"{key}_placebo{seed}_fold{fold.fold_id}.json"
                        if placebo_path.exists() and not args.force:
                            prec = json.loads(placebo_path.read_text())
                        elif len(train_frame) < MIN_TRAIN_ROWS or validation_frame.empty:
                            prec = {"validation_rankic_mean": None, "validation_rankic_n_dates": 0}
                            ml02._write_json(placebo_path, prec)
                        else:
                            shuffled_train = train_frame.copy()
                            shuffled_train[target_col] = _shuffle_stable(
                                train_frame, target_col, seed
                            )
                            model = MODEL_REGISTRY[model_name]()
                            model.fit(
                                shuffled_train[feature_columns].to_numpy(dtype="float64"),
                                shuffled_train[target_col].to_numpy(dtype="float64"),
                                shuffled_train["formation_date"].to_numpy(),
                            )
                            val_pred = model.predict(
                                validation_frame[feature_columns].to_numpy(dtype="float64")
                            )
                            val_scored = validation_frame[["formation_date", "symbol"]].copy()
                            val_scored[target_col] = _shuffle_stable(
                                validation_frame, target_col, seed
                            )
                            val_scored["prediction"] = val_pred
                            val_ic = ml02.rank_ic_per_date(val_scored, "prediction", target_col)
                            prec = {
                                "validation_rankic_mean": (
                                    float(np.mean([v for _, v in val_ic])) if val_ic else None
                                ),
                                "validation_rankic_n_dates": len(val_ic),
                            }
                            ml02._write_json(placebo_path, prec)
                            del model
                        if prec.get("validation_rankic_mean") is not None:
                            per_model_placebo[model_name][seed].append(
                                prec["validation_rankic_mean"]
                            )

            del frame, train_frame, validation_frame, test_frame
            gc.collect()
            _log(f"train: label={label} fold={fold.fold_id} done ({len(args.models)} models)")

        for model_name in args.models:
            key = f"{model_name}_{label}"
            pred_frames = per_model_test_frames[model_name]
            pred_frame = (
                pd.concat(pred_frames, ignore_index=True)
                if pred_frames
                else pd.DataFrame(columns=["formation_date", "symbol", "prediction", "fold_id"])
            )
            pred_frame.to_parquet(train_dir / f"{key}_predictions.parquet", index=False)
            fold_records = per_model_fold_records[model_name]
            val_ic_all = [
                r["validation_rankic_mean"]
                for r in fold_records
                if r.get("validation_rankic_mean") is not None
            ]
            test_ic_all = [
                r["test_rankic_mean"] for r in fold_records if r.get("test_rankic_mean") is not None
            ]
            placebo_means = [
                v for seed_vals in per_model_placebo[model_name].values() for v in seed_vals
            ]
            ml02._write_json(
                train_dir / f"{key}.json",
                {
                    "model": model_name,
                    "label": label,
                    "target_column": target_col,
                    "feature_columns": feature_columns,
                    "folds": fold_records,
                    "overall_validation_rankic_mean": float(np.mean(val_ic_all))
                    if val_ic_all
                    else None,
                    "overall_validation_rankic_icir": _icir(val_ic_all),
                    "overall_test_rankic_mean": float(np.mean(test_ic_all))
                    if test_ic_all
                    else None,
                    "overall_test_rankic_icir": _icir(test_ic_all),
                    "placebo_validation_rankic_mean": (
                        float(np.mean(placebo_means)) if placebo_means else None
                    ),
                    "placebo_validation_rankic_seeds": {
                        str(s): v for s, v in per_model_placebo[model_name].items()
                    },
                },
            )
            _log(f"train: {key} done -- wrote train/{key}.json")


# --------------------------------------------------------------------------
# stage: portfolio
# --------------------------------------------------------------------------


@dataclass
class Context:
    close_wide: pd.DataFrame
    open_wide: pd.DataFrame
    bench_returns: pd.DataFrame


def _load_context(cache_dir: Path) -> Context:
    close_wide = pd.read_parquet(cache_dir / "close_wide.parquet")
    open_wide = pd.read_parquet(cache_dir / "open_wide.parquet")
    close_wide.index = ml02._ns(close_wide.index)
    open_wide.index = ml02._ns(open_wide.index)
    bench = pd.read_parquet(cache_dir / "benchmark_returns.parquet")
    bench.index = ml02._ns(bench.index)
    return Context(close_wide, open_wide, bench)


def _all_test_dates(train_dir: Path) -> list[pd.Timestamp]:
    folds = json.loads((train_dir / "folds.json").read_text())
    dates: set[pd.Timestamp] = set()
    for fold in folds:
        dates.update(pd.Timestamp(d) for d in fold["test_dates"])
    return sorted(dates)


def _price_events(
    ctx: Context, events: list[RebalanceEvent], cost_bps: float = PRIMARY_COST_BPS
) -> tuple[pd.Series, int]:
    held = sorted({s for e in events for s in e.selected})
    columns = [s for s in held if s in ctx.close_wide.columns]
    missing = len(held) - len(columns)
    if CASH_SYMBOL not in columns:
        columns.append(CASH_SYMBOL)
    returns = returns_from_weight_schedule(
        events,
        ctx.close_wide[columns],
        ctx.bench_returns["SPY"].fillna(0.0),
        cost_bps_per_side=cost_bps,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=ctx.open_wide[columns],
    )
    return returns, missing


def _cell_key(kind: str, model: str, label: str, seed: str | int | None = None) -> str:
    key = f"{kind}__{model}__{label}"
    return key if seed is None else f"{key}__s{seed}"


def _cell_paths(cache_dir: Path, key: str) -> tuple[Path, Path]:
    returns_dir = cache_dir / "returns"
    books_dir = cache_dir / "books"
    return returns_dir / f"{key}.parquet", books_dir / f"{key}.json"


def _cell_done(cache_dir: Path, key: str) -> bool:
    returns_path, book_path = _cell_paths(cache_dir, key)
    return returns_path.exists() and book_path.exists()


def _save_cell(cache_dir: Path, key: str, returns: pd.Series, stats: dict[str, Any]) -> None:
    returns_path, book_path = _cell_paths(cache_dir, key)
    returns_path.parent.mkdir(parents=True, exist_ok=True)
    book_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"trade_date": returns.index, "ret": returns.to_numpy(dtype="float64")})
    frame.to_parquet(returns_path, index=False)
    ml02._write_json(book_path, stats)


def _price_and_save(
    cache_dir: Path,
    ctx: Context,
    key: str,
    tranches: dict[pd.Timestamp, dict[str, float]],
    dates: list[pd.Timestamp],
) -> None:
    events = ml02.tranches_to_events(tranches, dates)
    returns, missing = _price_events(ctx, events)
    stats = ml02.book_stats(tranches, events)
    stats["symbols_missing_from_price_matrix"] = missing
    stats["price_hygiene"] = {
        k: v
        for k, v in kernel_loop.LAST_PRICE_HYGIENE_MANIFEST.items()
        if not isinstance(v, (list, dict))
    }
    _save_cell(cache_dir, key, returns, stats)


def stage_portfolio(args: argparse.Namespace) -> None:
    cache_dir = cache_dir_for(args.features_suffix, args.feature_family)
    train_dir = cache_dir / "train"
    ctx = _load_context(cache_dir)
    test_dates = _all_test_dates(train_dir)
    if not test_dates:
        raise SystemExit("portfolio: no test dates found -- run --stage train first")
    _log(
        f"portfolio: {len(test_dates)} test-role formation dates "
        f"{test_dates[0].date()}..{test_dates[-1].date()}"
    )

    seeds = RANDOM_SEEDS[: args.seeds] if args.seeds else RANDOM_SEEDS
    id_columns = [
        "formation_date",
        "symbol",
        "adv_rank",
        "_raw_momentum_252_21",
        "_raw_vol_63",
        "_raw_net_buy_usd_60d",
    ]
    years_needed = sorted({d.year for d in test_dates})
    twin_frame = _load_panel_target_years(cache_dir, years_needed, id_columns)

    for label in LABELS if not args.labels else args.labels:
        for model_name in args.models:
            key = f"{model_name}_{label}"
            pred_path = train_dir / f"{key}_predictions.parquet"
            if not pred_path.exists():
                _log(f"portfolio: {pred_path} missing -- skip {key}")
                continue
            predictions = pd.read_parquet(pred_path)
            if predictions.empty:
                _log(f"portfolio: {key} has no predictions -- skip")
                continue
            predictions["formation_date"] = ml02._ns(predictions["formation_date"])
            pool = twin_frame.merge(
                predictions[["formation_date", "symbol", "prediction"]],
                on=["formation_date", "symbol"],
                how="inner",
            )
            if pool.empty:
                _log(f"portfolio: {key} pool empty after merge -- skip")
                continue

            topk_cell = _cell_key("topk_dropout", model_name, label)
            if not (_cell_done(cache_dir, topk_cell) and not args.force):
                topk_tranches = topk_dropout_tranches(
                    pool, "prediction", test_dates, topk=TOPK, n_drop=N_DROP
                )
                _price_and_save(cache_dir, ctx, topk_cell, topk_tranches, test_dates)
            else:
                topk_tranches = None

            decile_cell = _cell_key("top_decile", model_name, label)
            if not (_cell_done(cache_dir, decile_cell) and not args.force):
                decile_tranches = ml02.rank_tranches(
                    pool,
                    "prediction",
                    test_dates,
                    fraction=TOP_DECILE_FRACTION,
                    cap=MAX_NAMES,
                    ascending=False,
                )
                _price_and_save(cache_dir, ctx, decile_cell, decile_tranches, test_dates)

            if topk_tranches is None:
                topk_returns_path, topk_book_path = _cell_paths(cache_dir, topk_cell)
                topk_book = json.loads(topk_book_path.read_text())
                topk_sizes = {d: topk_book.get("tranche_size_mean", TOPK) for d in test_dates}
            else:
                topk_sizes = {d: len(t) for d, t in topk_tranches.items()}
            topk_sizes = {d: max(1, int(round(n))) for d, n in topk_sizes.items()}

            for seed in seeds:
                random_cell = _cell_key("random", model_name, label, seed)
                if _cell_done(cache_dir, random_cell) and not args.force:
                    continue
                control = ml02.random_tranches(pool, test_dates, topk_sizes, int(seed))
                _price_and_save(cache_dir, ctx, random_cell, control, test_dates)

            mom_cell = _cell_key("momentum_twin", model_name, label)
            if not (_cell_done(cache_dir, mom_cell) and not args.force):
                mom_pool = pool.copy()
                mom_pool["_mom_score"] = mom_pool["_raw_momentum_252_21"] / mom_pool["_raw_vol_63"]
                mom_pool = mom_pool.replace([np.inf, -np.inf], np.nan)
                mom_tranches = ml02.rank_tranches(
                    mom_pool, "_mom_score", test_dates, fraction=1.0, cap=TOPK, ascending=False
                )
                _price_and_save(cache_dir, ctx, mom_cell, mom_tranches, test_dates)

            ins_cell = _cell_key("insider_twin", model_name, label)
            if not (_cell_done(cache_dir, ins_cell) and not args.force):
                ins_tranches = ml02.rank_tranches(
                    pool,
                    "_raw_net_buy_usd_60d",
                    test_dates,
                    fraction=1.0,
                    cap=TOPK,
                    ascending=False,
                )
                _price_and_save(cache_dir, ctx, ins_cell, ins_tranches, test_dates)

            _log(f"portfolio: {key} done (topk_dropout, top_decile, {len(seeds)} random, twins)")


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def _load_returns(cache_dir: Path, key: str) -> pd.Series | None:
    path, _ = _cell_paths(cache_dir, key)
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    series = pd.Series(frame["ret"].to_numpy(dtype="float64"), index=ml02._ns(frame["trade_date"]))
    return series.sort_index()


def _window_metrics(series: pd.Series, start: pd.Timestamp) -> dict[str, float] | None:
    windowed = series.loc[series.index >= start]
    if len(windowed) < 20:
        return None
    return {
        "cagr": ml02.annualized_cagr(windowed),
        "max_drawdown": ml02.max_drawdown(windowed),
    }


def refute_topk_vs_spmo(
    topk_series: pd.Series | None, spmo_series: pd.Series, cash_series: pd.Series
) -> dict[str, Any]:
    if topk_series is None:
        return {"available": False}
    topk_window = _window_metrics(topk_series, REFUTE_WINDOW_START)
    spmo_window = _window_metrics(spmo_series, REFUTE_WINDOW_START)
    if topk_window is None or spmo_window is None:
        return {"available": False}
    aligned = topk_series.loc[topk_series.index >= REFUTE_WINDOW_START]
    try:
        excess = cagr_excess_vol_matched(
            aligned,
            spmo_series.reindex(aligned.index).fillna(0.0),
            cash_series.reindex(aligned.index).fillna(0.0),
        )
    except ValueError:
        excess = None
    loses_cagr = topk_window["cagr"] < spmo_window["cagr"]
    loses_drawdown = topk_window["max_drawdown"] < spmo_window["max_drawdown"]
    loses_both = loses_cagr and loses_drawdown
    return {
        "available": True,
        "topk_cagr": topk_window["cagr"],
        "topk_max_drawdown": topk_window["max_drawdown"],
        "spmo_cagr": spmo_window["cagr"],
        "spmo_max_drawdown": spmo_window["max_drawdown"],
        "excess_vol_matched_vs_spmo": excess,
        "loses_both_dimensions": loses_both,
        "excess_le_zero": (excess is not None and excess <= 0.0),
    }


def cell_verdict(train_record: dict[str, Any], spmo_check: dict[str, Any]) -> dict[str, Any]:
    test_ic = train_record.get("overall_test_rankic_mean")
    placebo_ic = train_record.get("placebo_validation_rankic_mean")
    val_ic = train_record.get("overall_validation_rankic_mean")
    placebo_share = (
        placebo_ic / val_ic if (val_ic and val_ic > 0 and placebo_ic is not None) else None
    )
    reasons: list[str] = []
    if test_ic is None or test_ic < REFUTE_RANKIC_THRESHOLD:
        verdict = "refuted"
        reasons.append(f"测试集 RankIC {ml02._num(test_ic, 4)} < {REFUTE_RANKIC_THRESHOLD}")
    elif placebo_share is not None and placebo_share >= REFUTE_PLACEBO_SHARE_THRESHOLD:
        verdict = "refuted"
        reasons.append(f"打乱标签占位达到真实验证 RankIC 的 {placebo_share:.0%}（>= 50%）")
    elif (
        spmo_check.get("available")
        and spmo_check["loses_both_dimensions"]
        and spmo_check["excess_le_zero"]
    ):
        verdict = "refuted"
        reasons.append(
            "topk=50 组合 2024 年起跑输 SPMO 的年化和最大回撤两个维度，且同波动超额 <= 0"
        )
    elif not spmo_check.get("available"):
        verdict = "inconclusive"
        reasons.append("topk=50 组合与 SPMO 的 2024 年起窗口数据不足，无法判定第三条否定条件")
    else:
        verdict = "supported"
        reasons.append(
            "测试集 RankIC 达标，占位份额 < 50%，topk=50 组合未同时在两个维度且超额为负地跑输 SPMO"
        )
    return {
        "verdict": verdict,
        "reasons": reasons,
        "test_rankic_mean": test_ic,
        "placebo_share_of_validation": placebo_share,
        "spmo_check": spmo_check,
    }


def stage_report(args: argparse.Namespace) -> dict[str, Any]:
    cache_dir = cache_dir_for(args.features_suffix, args.feature_family)
    train_dir = cache_dir / "train"
    ctx = _load_context(cache_dir)
    manifest = _load_panel_manifest(cache_dir)
    feature_manifest = json.loads((cache_dir / "feature_manifest.json").read_text())

    cells: dict[str, Any] = {}
    for label in LABELS if not args.labels else args.labels:
        for model_name in args.models:
            key = f"{model_name}_{label}"
            record_path = train_dir / f"{key}.json"
            if not record_path.exists():
                continue
            train_record = json.loads(record_path.read_text())

            portfolio_cells: dict[str, Any] = {}
            for kind in ("topk_dropout", "top_decile", "momentum_twin", "insider_twin"):
                series = _load_returns(cache_dir, _cell_key(kind, model_name, label))
                portfolio_cells[kind] = (
                    ml02.cell_metrics(series, ctx.bench_returns) if series is not None else None
                )

            random_metrics = []
            for seed in RANDOM_SEEDS[: args.seeds] if args.seeds else RANDOM_SEEDS:
                series = _load_returns(cache_dir, _cell_key("random", model_name, label, seed))
                if series is not None:
                    m = ml02.cell_metrics(series, ctx.bench_returns)
                    if m:
                        random_metrics.append(m)
            random_agg = (
                {"cagr": ml02._percentiles([m["cagr"] for m in random_metrics])}
                if random_metrics
                else None
            )

            topk_series = _load_returns(cache_dir, _cell_key("topk_dropout", model_name, label))
            spmo_check = refute_topk_vs_spmo(
                topk_series, ctx.bench_returns["SPMO"], ctx.bench_returns[CASH_SYMBOL]
            )
            verdict = cell_verdict(train_record, spmo_check)

            cells[key] = {
                "model": model_name,
                "label": label,
                "train": train_record,
                "portfolio": portfolio_cells,
                "random": random_agg,
                "verdict": verdict,
                "published_comparison": QLIB_PUBLISHED.get(model_name),
            }

    verdicts = [c["verdict"]["verdict"] for c in cells.values()]
    if any(v == "supported" for v in verdicts):
        card_verdict = "supported"
    elif verdicts and all(v == "refuted" for v in verdicts):
        card_verdict = "refuted"
    else:
        card_verdict = "inconclusive"

    summary = {
        "iteration_id": ITERATION_ID,
        "run_tag": run_tag(args.features_suffix, args.feature_family),
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "panel_manifest": manifest,
        "feature_manifest": feature_manifest,
        "benchmarks": ml02.benchmark_metrics(ctx.bench_returns),
        "design": {
            "execution": EXECUTION,
            "cost_bps_per_side": PRIMARY_COST_BPS,
            "topk": TOPK,
            "n_drop": N_DROP,
            "top_decile_fraction": TOP_DECILE_FRACTION,
            "embargo_days": EMBARGO_DAYS,
            "train_years": args.train_years or DEFAULT_TRAIN_YEARS,
            "skip_placebo": bool(args.skip_placebo),
            "duckdb_memory_limit": _DUCKDB_MEMORY_LIMIT,
        },
        "qlib_published": QLIB_PUBLISHED,
        "cells": cells,
        "card_verdict": {"verdict": card_verdict, "cells_evaluated": len(cells)},
        "deviations": manifest.get("deviations", []),
    }
    summary_path = summary_path_for(args.features_suffix, args.feature_family)
    ml02._write_json(summary_path, summary)
    _log(f"report: wrote {summary_path} ({len(cells)} cells) -- card verdict {card_verdict}")
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# H-20260918-03 Qlib 配方（LightGBM / DoubleEnsemble）照搬到美股宽池子 — 报告")
    lines.append("")
    lines.append(
        f"- 生成时间：{summary['generated_at'][:16]} UTC · run_tag=`{summary['run_tag']}` · "
        f"features_suffix=`{summary['panel_manifest']['features_suffix']}` · "
        f"feature_family=`{summary['panel_manifest']['feature_family']}`"
    )
    n_cells = summary["card_verdict"]["cells_evaluated"]
    lines.append(f"- 结论：**{summary['card_verdict']['verdict']}**（{n_cells} 个单元）")
    lines.append("")

    lines.append("## 1. Rank IC / ICIR 对比 Qlib 发表的 CSI300 数字")
    lines.append("")
    lines.append(
        "| 单元 | 测试集 RankIC | 测试集 ICIR | Qlib 发表 RankIC | Qlib 发表 RankIC-ICIR |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    for key, cell in summary["cells"].items():
        train = cell["train"]
        pub = cell["published_comparison"]
        pub_ic = f"{pub['rank_ic']:.4f}" if pub else "n/a（未发表基准）"
        pub_icir = f"{pub['rank_icir']:.4f}" if pub else "n/a"
        lines.append(
            f"| `{key}` | {ml02._num(train.get('overall_test_rankic_mean'), 4)} | "
            f"{ml02._num(train.get('overall_test_rankic_icir'), 4)} | {pub_ic} | {pub_icir} |"
        )
    lines.append("")

    lines.append("## 2. 组合表现对比 SPY / IWM / SPMO 买入持有")
    lines.append("")
    lines.append("| 基准 | CAGR | 最大回撤 | 窗口 |")
    lines.append("|---|---:|---:|---|")
    for sym in BENCHMARK_SYMBOLS:
        b = summary["benchmarks"].get(sym)
        if not b:
            lines.append(f"| {sym} | n/a | n/a | n/a |")
            continue
        window = f"{b['window'][0]} .. {b['window'][1]}"
        lines.append(
            f"| {sym} | {ml02._pct(b['cagr'])} | {ml02._pct(b['max_drawdown'])} | {window} |"
        )
    lines.append("")
    lines.append(
        "| 单元 | topk_dropout(50,5) CAGR | 最大回撤 | top_decile CAGR | 最大回撤 | "
        "动量孪生 CAGR | 内部人孪生 CAGR |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for key, cell in summary["cells"].items():
        p = cell["portfolio"]
        topk_m = p.get("topk_dropout")
        dec_m = p.get("top_decile")
        mom_m = p.get("momentum_twin")
        ins_m = p.get("insider_twin")
        lines.append(
            f"| `{key}` | {ml02._pct(topk_m['cagr']) if topk_m else 'n/a'} | "
            f"{ml02._pct(topk_m['max_drawdown']) if topk_m else 'n/a'} | "
            f"{ml02._pct(dec_m['cagr']) if dec_m else 'n/a'} | "
            f"{ml02._pct(dec_m['max_drawdown']) if dec_m else 'n/a'} | "
            f"{ml02._pct(mom_m['cagr']) if mom_m else 'n/a'} | "
            f"{ml02._pct(ins_m['cagr']) if ins_m else 'n/a'} |"
        )
    lines.append("")

    lines.append("## 3. 否定条件判定（逐单元）")
    lines.append("")
    for key, cell in summary["cells"].items():
        v = cell["verdict"]
        lines.append(f"### `{key}` — **{v['verdict']}**")
        for reason in v["reasons"]:
            lines.append(f"- {reason}")
        lines.append("")

    lines.append("## 4. 特征")
    lines.append("")
    fm = summary["feature_manifest"]
    n_dropped = len(fm["features_dropped_low_coverage"])
    lines.append(
        f"- 候选列 {len(fm['candidate_columns'])} 个，保留 {len(fm['features_kept'])} 个"
        f"（覆盖率 >= {fm['coverage_threshold']:.0%}），丢弃 {n_dropped} 个"
    )
    if fm["features_dropped_low_coverage"]:
        dropped = ", ".join(f"{k}({v:.0%})" for k, v in fm["features_dropped_low_coverage"].items())
        lines.append(f"- 丢弃（覆盖率不足）：{dropped}")
    lines.append("")

    lines.append("## 5. 偏离披露（Deviations）")
    lines.append("")
    lines.append(
        "1. `num_threads=2`，不是 Qlib 原文的 20 —— 本机只有 2 个可用核心（见脚本 docstring）。"
    )
    lines.append(
        "2. LightGBM `num_boost_round=1000` / `early_stopping_rounds=50` "
        "不在卡片列出的 8 个超参里，是 Qlib `LGBModel.fit()` 自身的默认值，"
        "为了能训练而补上，不是调参。"
    )
    lines.append(
        "3. DoubleEnsemble 的 SR/FS 直接在 lightgbm 上重建（本机没装 torch 也没装 qlib 包，"
        "Qlib 自己的 DoubleEnsemble 实现本来就只用 lightgbm），是对论文结构的有理由复原，"
        "不是逐字节照搬 qlib/contrib/model/double_ensemble.py（细节见脚本 docstring）。"
    )
    for extra in summary.get("deviations", []):
        lines.append(f"4. {extra}")
    lines.append("")

    lines.append("## 6. 文件")
    lines.append("")
    lines.append(
        f"- 汇总：`summary_{summary['run_tag']}.json`；本报告：`report_{summary['run_tag']}.md`"
    )
    pm = summary["panel_manifest"]
    cache_dir = cache_dir_for(pm["features_suffix"], pm["feature_family"])
    lines.append(f"- 缓存（gitignore）：`{cache_dir.relative_to(ROOT)}/`")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stage", choices=["all", "panel", "target", "train", "portfolio", "report"], default="all"
    )
    parser.add_argument(
        "--features-suffix",
        default="",
        help="'' for the narrow smoke-test tables, '_broad' for the real run",
    )
    parser.add_argument("--feature-family", choices=list(FEATURE_FAMILIES), default="alpha158")
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--models", nargs="*", default=list(MODEL_NAMES), choices=list(MODEL_NAMES))
    parser.add_argument("--labels", nargs="*", default=None, choices=list(LABELS))
    parser.add_argument(
        "--seeds", type=int, default=None, help="number of random/placebo seeds (default 5)"
    )
    parser.add_argument("--train-years", type=float, default=None)
    parser.add_argument("--skip-placebo", action="store_true")
    parser.add_argument("--duckdb-memory-limit", default="900MB")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.labels is None:
        args.labels = list(LABELS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    configure_duckdb(args.duckdb_memory_limit)
    if args.stage in ("all", "panel"):
        stage_panel(args)
    if args.stage in ("all", "target"):
        stage_target(args)
    if args.stage in ("all", "train"):
        stage_train(args)
    if args.stage in ("all", "portfolio"):
        stage_portfolio(args)
    if args.stage in ("all", "report"):
        summary = stage_report(args)
        report_path = report_path_for(args.features_suffix, args.feature_family)
        report_path.write_text(render_markdown(summary), encoding="utf-8")
        _log(f"report: wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
