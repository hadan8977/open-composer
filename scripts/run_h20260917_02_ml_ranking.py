"""H-20260917-02: broad-universe cross-sectional ML ranking, monthly, target
first.

Card: ``reports/research/hypotheses/H-20260917-02-broad-universe-ml-ranking.md``
Data card: ``reports/research/hypotheses/D-20260917-01-broad-universe-and-delisted-backfill.md``
Feature pipelines this reuses: H-01 (insider), H-05 (13D), H-07 (short
interest); news-attention columns per H-20260916-02 (stage 1 of that card was
refuted -- included here anyway because this is a different target/model/
universe, per the card's own reasoning for why ML is worth retrying now).

**This is part 1 of 2.** It builds the whole pipeline -- panel, target,
rolling quarterly splits, portfolio construction, controls, placebo, report
-- with a ridge-regression baseline as the only registered model. A later
change adds LightGBM LambdaRank and a GBDT classifier; the only change that
requires is a new entry in :data:`MODEL_REGISTRY` (a callable returning
something with ``.fit(X, y, groups)`` / ``.predict(X)``), never a rewrite of
the fold/portfolio/report machinery below.

Design decisions this script had to make that the card leaves implicit are
recorded here rather than silently baked in:

**Target** (card section "目标"): 21-trading-day forward return, hedged
against the symbol's own trailing-252-day SPY beta (``beta_252_spy``, already
computed point-in-time in ``data/features/daily{suffix}``) applied
*prospectively* to SPY's own realized forward 21-day return over the same
window, then demeaned against the mean of the same quantity within the
symbol's own dollar-ADV quintile at that formation date (quintiles of the
universe panel's ``dollar_adv``, computed within the formation date's cohort).
``data/features/labels{suffix}`` was inspected (schema: ``label_excess_{h}``,
``label_rank_{h}`` for h in 5/10/21) and carries only cross-sectional-median-
excess and rank columns, never a raw forward return -- so per the task's own
fallback instruction, the raw 21-day forward return is computed here directly
from price-hygiene-sanitized closes (``features.price_hygiene``), matching
``labels.py``'s own LEAD(close, 21) convention but without inheriting its
different (full-union-median, not beta+size-hedged) excess definition.

**Splits** (card section "模型"): rolling, retrained every quarter, train
window = the trailing ``--train-years`` (default 3.0) calendar years of
formation dates ending ``EMBARGO_DAYS`` (21) trading days before the
validation quarter's first formation date (``kernel.loop.embargo_cutoff``),
validation = that quarter, test = the quarter after. Only the **test**-role
score is ever used to build the traded portfolio -- each formation date
enters the traded return series through exactly one fold's test role, never
two. The **same** calendar quarter is, in a *different* fold one quarter
later, scored again as that later fold's *validation* set by a *different*
model (trained through a later, still-embargoed cutoff) -- this is an
intentional consequence of retraining every quarter with a validation step
placed immediately before test, not a leak: both scoring passes are causal
(neither model ever sees its own scored quarter during training), and the
validation-role pass is a diagnostic only, never part of the portfolio. When
fewer than ``--train-years`` years of formation-date history exist before a
fold's embargoed cutoff (guaranteed on the smoke test's 3-year window), the
train window silently expands back to the first available formation date
instead of skipping the fold -- ``actual_train_years`` is recorded per fold
so this is never mistaken for a full rolling window.

**Portfolio / controls**: every cell (ML top/bottom decile, band equal
weight, same-size random x5 seeds, momentum twin, insider twin, placebo) is
priced over the *same* date axis -- the union of every fold's test dates --
so no cell gets a survivorship-friendlier or longer window than another.
Momentum twin ranks by ``momentum_252_21 / vol_63`` (the M0B score used by
``scripts/run_h20260916_07_short_interest.py`` and
``scripts/run_step13_m_grid.py``'s ``M0B_SCORE_COLUMNS``); insider twin ranks
by ``net_buy_usd_60d``. Both are raw (not rank-normalized) at selection time,
exactly like the model's own top-decile selection uses raw prediction values.

**Features** (card section "特征"): from ``data/features/daily{suffix}`` --
momentum (``ret_21/63/126/252``, ``momentum_252_21``), reversal
(``ret_1``, ``ret_5``, ``max_ret_1_21``, ``dist_from_252d_high``), volatility
(``vol_21``, ``vol_63``, ``idio_vol_63``), turnover
(``dollar_adv_21_over_63``, ``amihud_21``), and the 21-day-mean overnight/
intraday columns only (the 5-day-mean duplicates are dropped to control
width; ``feature_sets.py``'s ``DAILY27_COLUMNS`` dropped this whole family as
"proven negative" in the *B0-B3 weekly momentum* context of Step 11 Wave B --
a different target, model and universe, so it is included here on the card's
explicit instruction, with that prior null result disclosed for context, not
silently repeated or silently overridden). ``beta_252_spy`` is read but is
**not** a model feature -- it only feeds the target's hedge term, kept out of
the feature matrix to avoid the appearance of using the same quantity on both
sides. Insider: ``net_buy_usd_60d``, ``open_market_buy_count_60d``,
``buyers_60d``, ``days_since_last_visible_buy`` (the card's role-split
``*_od_60d``/``*_tenpct_60d`` columns do not exist in
``data/features/insider{suffix}`` as of this run -- checked, not invented).
13D: one derived flag, ``new_13d_60d`` (an ``is_new_13d`` filing with
``visible_session`` in the trailing 60 sessions, matched by
``issuer_symbol``), built via ``merge_asof`` since ``sec_13d/filings.parquet``
is an event table, not a dense daily one. Short interest and news attention
(``data/features/short_interest``, ``data/features/news_attention``, neither
suffix-namespaced) *are* dense one-row-per-(symbol, trading day) tables whose
own ``trade_date`` already encodes the latest point-in-time-visible record
(confirmed from their own module docstrings and by row count), so they are
joined the same plain equi-join on ``(symbol, formation_date)`` as the daily
and insider tables -- no separate ``merge_asof`` needed for those two.
News-attention keyword columns (``kw_*``) and ``distinct_sources_5d`` (a
constant per that table's own module docstring) are excluded to control
width; the rest of ``news_attention.NEWS_ATTENTION_COLUMNS`` is used. Every
feature is cross-sectionally rank-normalized (0-1 percentile) within its
formation date; a column whose overall non-null coverage is below 50% is
dropped and recorded in the feature manifest rather than trained on with a
fabricated fill.

Stages (each resumable from ``reports/research/iterations/<id>/cache/``)
-------------------------------------------------------------------------
``panel``      universe cohorts -> formation frame; raw (pre-rank-normalize)
               feature columns joined from every source; raw daily
               open/close price matrices and benchmark returns cached.
``target``     price-hygiene-sanitized forward 21-day returns, the SPY-beta
               + size-quintile hedge, the top-20% binary alternative target,
               cross-sectional rank-normalization, coverage-based feature
               dropping.
``train``      rolling quarterly folds; one fit per (model, target, fold) on
               ``--models`` x ``--target``; validation RankIC per fold; test
               -role predictions cached; the shuffled-label placebo (skipped
               by ``--skip-placebo``).
``portfolio``  real book, controls and placebo priced through
               ``kernel.loop.returns_from_weight_schedule`` (price hygiene
               on, ``next_open`` execution, 10bp/side).
``report``     metrics, the card's refutation criteria, ``summary.json`` and
               a Chinese ``report.md``.

Nothing here writes a ledger row; nothing goes through ``loop.run_experiment``
(that function's weekly/yearly cadence does not match this card's monthly/
quarterly design -- see the "Splits" note above for why a bespoke fold loop
was written instead of reusing ``build_weight_schedule``).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402
from open_composer.research.features import price_hygiene  # noqa: E402
from open_composer.research.features.news_attention import (  # noqa: E402
    NEWS_ATTENTION_ROOT,
)
from open_composer.research.features.short_interest import SHORT_INTEREST_ROOT  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel import loop as kernel_loop  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    DEFAULT_MIN_COHORT_SYMBOLS,
    RebalanceEvent,
    embargo_cutoff,
    returns_from_weight_schedule,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.pick_export import turnover_per_rebalance  # noqa: E402
from open_composer.research.kernel.vol_matched import (  # noqa: E402
    cagr_excess_vol_matched,
    vol_match_weight,
)

try:
    from sklearn.linear_model import Ridge as _SkRidge

    _SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover -- exercised only if sklearn is absent
    _SkRidge = None
    _SKLEARN_AVAILABLE = False

ITERATION_ID = "h20260917_02_ml_ranking"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
FEATURES_ROOT = ROOT / "data" / "features"
SEC13D_PATH = FEATURES_ROOT / "sec_13d" / "filings.parquet"

#: Cache and artifact paths are per feature family. Without this a ``_broad``
#: run silently reuses the narrow run's cached panel/train/returns: on
#: 2026-09-18 the first broad run finished in 8 seconds and reported the
#: narrow 2023-2025 window's numbers ("train: ridge_excess21 cached --
#: reusing"). ``bind_paths`` is called once from ``main`` before any stage.
CACHE_DIR = OUT_DIR / "cache" / "broad"
TRAIN_DIR = CACHE_DIR / "train"
RETURNS_DIR = CACHE_DIR / "returns"
BOOKS_DIR = CACHE_DIR / "books"
SUMMARY_PATH = OUT_DIR / "summary.json"
REPORT_PATH = OUT_DIR / "report.md"


def bind_paths(features_suffix: str) -> str:
    """Point cache and artifact paths at this feature family; return its tag."""
    global CACHE_DIR, TRAIN_DIR, RETURNS_DIR, BOOKS_DIR, SUMMARY_PATH, REPORT_PATH
    tag = features_suffix.strip("_") or "narrow"
    CACHE_DIR = OUT_DIR / "cache" / tag
    TRAIN_DIR = CACHE_DIR / "train"
    RETURNS_DIR = CACHE_DIR / "returns"
    BOOKS_DIR = CACHE_DIR / "books"
    stem = "" if tag == "broad" else f"_{tag}"
    SUMMARY_PATH = OUT_DIR / f"summary{stem}.json"
    REPORT_PATH = OUT_DIR / f"report{stem}.md"
    return tag


DATA_START = "2016-01-04"
PRIMARY_COST_BPS = 10.0
EXECUTION = "next_open"
CASH_SYMBOL = "BIL"
BENCHMARK_SYMBOLS: tuple[str, ...] = ("SPY", "IWM", "MTUM", "SPMO")
MAX_NAMES = 100
TOP_DECILE_FRACTION = 0.10
BOTTOM_DECILE_FRACTION = 0.10
EMBARGO_DAYS = 21
FORWARD_HORIZON_DAYS = 21
DEFAULT_TRAIN_YEARS = 3.0
RANDOM_SEEDS: tuple[int, ...] = (1, 2, 3, 4, 5)
PLACEBO_SEEDS: tuple[int, ...] = (101, 102, 103, 104, 105)
MIN_TRAIN_ROWS = 200
RANKIC_MIN_NAMES = 5
RIDGE_ALPHA = 1.0
#: Card refutation thresholds, literal.
REFUTE_RANKIC_THRESHOLD = 0.02
REFUTE_PLACEBO_SHARE_THRESHOLD = 0.5

BANDS: dict[str, tuple[int, int | None]] = {
    "all": (1, None),
    "b1_500": (1, 500),
    "b501_1500": (501, 1500),
    "b1501_plus": (1501, None),
}
BAND_LABELS = {"all": "全部", "b1_500": "1–500", "b501_1500": "501–1500", "b1501_plus": "1501+"}

# --------------------------------------------------------------------------
# feature registry -- see module docstring's "Features" section for the
# per-column rationale.
# --------------------------------------------------------------------------

DAILY_MOMENTUM_COLUMNS: tuple[str, ...] = (
    "ret_21",
    "ret_63",
    "ret_126",
    "ret_252",
    "momentum_252_21",
)
DAILY_REVERSAL_COLUMNS: tuple[str, ...] = ("ret_1", "ret_5", "max_ret_1_21", "dist_from_252d_high")
DAILY_VOLATILITY_COLUMNS: tuple[str, ...] = ("vol_21", "vol_63", "idio_vol_63")
DAILY_TURNOVER_COLUMNS: tuple[str, ...] = ("dollar_adv_21_over_63", "amihud_21")
#: 21-day-mean overnight/intraday family only -- the 5-day-mean duplicates
#: are dropped to control feature-set width (see module docstring).
DAILY_OVERNIGHT_INTRADAY_COLUMNS: tuple[str, ...] = (
    "overnight_return_21d_mean",
    "intraday_return_21d_mean",
    "intraday_realized_vol_21d_mean",
    "intraday_amplitude_21d_mean",
    "open_30min_volume_share_21d_mean",
    "close_30min_volume_share_21d_mean",
    "vwap_deviation_21d_mean",
    "intraday_skew_21d_mean",
    "trade_count_21d_mean",
    "amihud_intraday_21d_mean",
)
DAILY_FEATURE_COLUMNS: tuple[str, ...] = (
    *DAILY_MOMENTUM_COLUMNS,
    *DAILY_REVERSAL_COLUMNS,
    *DAILY_VOLATILITY_COLUMNS,
    *DAILY_TURNOVER_COLUMNS,
    *DAILY_OVERNIGHT_INTRADAY_COLUMNS,
)
#: Read alongside the feature columns but never trained on -- see module
#: docstring: it only feeds the target's SPY-beta hedge term.
BETA_COLUMN = "beta_252_spy"

INSIDER_FEATURE_COLUMNS: tuple[str, ...] = (
    "net_buy_usd_60d",
    "open_market_buy_count_60d",
    "buyers_60d",
    "days_since_last_visible_buy",
)
#: The card's role-split columns (*_od_60d / *_tenpct_60d): not present in
#: data/features/insider{suffix} as of 2026-09-18 -- checked, not invented.
INSIDER_ROLE_SPLIT_COLUMNS_NOT_YET_BUILT: tuple[str, ...] = ()

#: short_interest.SHORT_INTEREST_COLUMNS minus staleness_days -- that
#: module's own docstring calls staleness_days "a negative control", not a
#: factor.
SHORT_INTEREST_FEATURE_COLUMNS: tuple[str, ...] = (
    "days_to_cover",
    "short_interest_ratio",
    "dtc_change_vs_prior",
    "dtc_cross_sectional_pct",
)
#: news_attention.NEWS_ATTENTION_COLUMNS minus distinct_sources_5d (that
#: module's own SCREEN_EXCLUDED_COLUMNS: constant, no cross-sectional
#: information) and minus the nine kw_* keyword flags (width control; H-
#: 20260916-02 stage 1 already found this family FDR-indistinguishable from
#: noise for a different target -- disclosed, not silently reused as if new).
NEWS_ATTENTION_FEATURE_COLUMNS: tuple[str, ...] = (
    "news_count_1d",
    "news_count_5d",
    "news_count_20d",
    "attention_surge_5d",
    "distinct_authors_5d",
    "novelty_5d",
    "days_since_last_news",
)
SEC13D_FEATURE_COLUMNS: tuple[str, ...] = ("new_13d_60d",)

ALL_FEATURE_COLUMNS: tuple[str, ...] = (
    *DAILY_FEATURE_COLUMNS,
    *INSIDER_FEATURE_COLUMNS,
    *SHORT_INTEREST_FEATURE_COLUMNS,
    *NEWS_ATTENTION_FEATURE_COLUMNS,
    *SEC13D_FEATURE_COLUMNS,
)
FEATURE_COVERAGE_THRESHOLD = 0.50

MOMENTUM_TWIN_NUMERATOR = "momentum_252_21"
MOMENTUM_TWIN_DENOMINATOR = "vol_63"
INSIDER_TWIN_COLUMN = "net_buy_usd_60d"

#: The card's own declared trial family (header: "预算 6，每个可被选中的模型×
#: 目标组合计 1 次"): 3 models (ridge is the only one *registered* this round;
#: lambdarank/gbdt are named by the card but not yet implemented) x 2 targets.
CARD_MODELS: tuple[str, ...] = ("ridge", "lambdarank", "gbdt")
CARD_TARGETS: tuple[str, ...] = ("excess21", "top20")
TARGET_COLUMNS = {"excess21": "target_excess_21", "top20": "target_top20"}

_T0 = time.time()


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n")


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"not JSON serializable: {type(value)}")


def _ns(values: pd.Series | pd.Index) -> pd.Series | pd.Index:
    """Datetime column normalized to ``datetime64[ns]`` so month_end (us),
    daily (us/ns) and event-table (ns/date32) keys compare and join exactly.
    """
    return pd.to_datetime(values).astype("datetime64[ns]")


def feature_roots(suffix: str) -> dict[str, Path]:
    return {
        "universe": FEATURES_ROOT / f"universe{suffix}",
        "daily": FEATURES_ROOT / f"daily{suffix}",
        "labels": FEATURES_ROOT / f"labels{suffix}",
        "insider": FEATURES_ROOT / f"insider{suffix}",
    }


def band_of(adv_rank: pd.Series) -> pd.Series:
    rank = adv_rank.to_numpy()
    out = np.where(rank <= 500, "b1_500", np.where(rank <= 1500, "b501_1500", "b1501_plus"))
    return pd.Series(out, index=adv_rank.index, dtype="object")


def band_frame(frame: pd.DataFrame, band: str) -> pd.DataFrame:
    low, high = BANDS[band]
    mask = frame["adv_rank"] >= low
    if high is not None:
        mask &= frame["adv_rank"] <= high
    return frame.loc[mask]


# --------------------------------------------------------------------------
# model registry -- fit(X, y, groups) -> None, predict(X) -> np.ndarray.
# --------------------------------------------------------------------------


class RankingModel(Protocol):
    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None: ...

    def predict(self, X: np.ndarray) -> np.ndarray: ...


@dataclass
class RidgeRankingModel:
    """Ridge regression on cross-sectionally rank-normalized features.

    ``groups`` (the formation-date label of each training row) is accepted
    for interface parity with the group-aware models this registry will grow
    (LambdaRank needs per-date group sizes; a GBDT classifier does not) but is
    unused here -- ridge treats every row independently.

    Uses scikit-learn's ``Ridge`` when available (confirmed present in this
    venv, version 1.9.0, 2026-09-18); falls back to a closed-form numpy
    solve (unpenalized intercept) if scikit-learn is ever absent, so this
    baseline never hard-fails on a leaner environment.
    """

    alpha: float = RIDGE_ALPHA
    _model: Any = field(default=None, init=False, repr=False)
    _intercept: float | None = field(default=None, init=False, repr=False)
    _coef: np.ndarray | None = field(default=None, init=False, repr=False)

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        del groups
        if _SKLEARN_AVAILABLE:
            self._model = _SkRidge(alpha=self.alpha)
            self._model.fit(X, y)
            return
        design = np.column_stack([np.ones(len(X)), X])
        penalty = self.alpha * np.eye(design.shape[1])
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ y)
        self._intercept = float(beta[0])
        self._coef = beta[1:]

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._model is not None:
            return self._model.predict(X)
        if self._coef is None or self._intercept is None:
            raise RuntimeError("RidgeRankingModel.predict called before fit")
        return self._intercept + X @ self._coef


MODEL_REGISTRY: dict[str, Callable[[], RankingModel]] = {
    "ridge": lambda: RidgeRankingModel(alpha=RIDGE_ALPHA),
}


# --------------------------------------------------------------------------
# stage: panel
# --------------------------------------------------------------------------


def _benchmark_prices(symbols: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(close, open)`` daily frames indexed by naive trade_date."""
    raw = load_sip_bars(list(symbols), frequency="daily", start=DATA_START)
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    raw["trade_date"] = _ns(pd.to_datetime(raw["timestamp"].dt.date))
    raw = raw.sort_values(["symbol", "timestamp"]).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    close = raw.pivot(index="trade_date", columns="symbol", values="close").astype("float64")
    open_ = raw.pivot(index="trade_date", columns="symbol", values="open").astype("float64")
    return close.sort_index(), open_.sort_index()


def _read_year_at_dates(
    root: Path, year: int, columns: Sequence[str], dates: set[pd.Timestamp]
) -> pd.DataFrame:
    path = root / f"{year}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "trade_date", *columns])
    table = pq.read_table(path, columns=["symbol", "trade_date", *columns])
    frame = table.to_pandas()
    del table
    frame["trade_date"] = _ns(frame["trade_date"])
    frame = frame.loc[frame["trade_date"].isin(dates)]
    frame["symbol"] = frame["symbol"].astype(str)
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
    return frame


def _new_13d_flag(formation: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.Series:
    """1.0 if the symbol had an ``is_new_13d`` filing whose ``visible_session``
    falls in the trailing 60 trading sessions ending at (and including) the
    formation date, else 0.0. ``sec_13d/filings.parquet`` is an event table
    (one row per filing), not a dense daily one, so this is a
    ``merge_asof``-nearest-backward match rather than a plain equi-join: the
    nearest prior new-13D filing per symbol is found, then kept only if it is
    within the 60-session window (position difference on the shared trading
    calendar, not calendar days).
    """
    if not SEC13D_PATH.exists():
        _log("panel: sec_13d/filings.parquet missing -- new_13d_60d left all-zero")
        return pd.Series(0.0, index=formation.index)
    filings = pd.read_parquet(
        SEC13D_PATH, columns=["issuer_symbol", "visible_session", "is_new_13d"]
    )
    filings = filings.loc[filings["is_new_13d"]].dropna(subset=["issuer_symbol", "visible_session"])
    filings = filings.rename(columns={"issuer_symbol": "symbol"})
    filings["symbol"] = filings["symbol"].astype(str)
    filings["visible_session"] = _ns(filings["visible_session"])
    filings = filings.sort_values("visible_session")[["symbol", "visible_session"]]

    left = formation[["formation_date", "symbol"]].reset_index().sort_values("formation_date")
    merged = pd.merge_asof(
        left,
        filings,
        left_on="formation_date",
        right_on="visible_session",
        by="symbol",
        direction="backward",
    )
    calendar = pd.DatetimeIndex(calendar)
    formation_pos = calendar.searchsorted(merged["formation_date"].to_numpy())
    filing_pos = calendar.searchsorted(
        merged["visible_session"].fillna(pd.Timestamp.min).to_numpy()
    )
    within_window = (
        merged["visible_session"].notna()
        & ((formation_pos - filing_pos) >= 0)
        & ((formation_pos - filing_pos) <= 60)
    )
    flag = pd.Series(within_window.astype("float64").to_numpy(), index=merged["index"].to_numpy())
    return flag.reindex(formation.index).fillna(0.0)


def stage_panel(args: argparse.Namespace) -> None:
    manifest_path = CACHE_DIR / "panel_manifest.json"
    if manifest_path.exists() and not args.force:
        _log(f"panel: {manifest_path} present -- reusing (pass --force to rebuild)")
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    roots = feature_roots(args.features_suffix)
    for name in ("universe", "daily", "insider"):
        if not any(roots[name].glob("20*.parquet")):
            raise SystemExit(f"panel: {name} root {roots[name]} has no year files yet")
    if not any(roots["labels"].glob("20*.parquet")):
        _log(
            f"panel: labels root {roots['labels']} has no year files -- fwd return will be "
            "computed from closes regardless (see module docstring)"
        )

    daily_years = sorted(
        int(p.stem) for p in roots["daily"].glob("20*.parquet") if p.stem.isdigit()
    )
    years = [y for y in (args.years or daily_years) if y in daily_years]
    _log(f"panel: features_suffix={args.features_suffix!r} years={years}")

    universe = load_universe_panel(roots["universe"], years=years)
    universe["month_end"] = _ns(universe["month_end"])
    universe["symbol"] = universe["symbol"].astype(str)
    cohort_sizes = universe.groupby("month_end").size()
    formation_dates = sorted(
        pd.Timestamp(d) for d, n in cohort_sizes.items() if n >= DEFAULT_MIN_COHORT_SYMBOLS
    )
    _log(
        f"panel: universe {len(universe):,} rows, {universe['symbol'].nunique():,} symbols, "
        f"{len(formation_dates)} cohort dates "
        f"{formation_dates[0].date()}..{formation_dates[-1].date()}"
    )
    formation_dates_set = set(formation_dates)

    rows = universe.loc[
        universe["month_end"].isin(formation_dates),
        ["month_end", "symbol", "adv_rank", "dollar_adv", "close"],
    ].rename(columns={"month_end": "formation_date"})
    rows["adv_rank"] = rows["adv_rank"].astype("int64")
    rows["band"] = band_of(rows["adv_rank"])

    daily_feature_cols = [*DAILY_FEATURE_COLUMNS, BETA_COLUMN]
    close_frames: list[pd.DataFrame] = []
    open_frames: list[pd.DataFrame] = []
    daily_at_formation: list[pd.DataFrame] = []
    for year in years:
        path = roots["daily"] / f"{year}.parquet"
        table = pq.read_table(
            path, columns=["symbol", "trade_date", "open", "close", *daily_feature_cols]
        )
        frame = table.to_pandas()
        del table
        frame["trade_date"] = _ns(frame["trade_date"])
        frame["symbol"] = frame["symbol"].astype(str)
        frame = frame.drop_duplicates(["trade_date", "symbol"], keep="last")
        close_frames.append(frame.pivot(index="trade_date", columns="symbol", values="close"))
        open_frames.append(frame.pivot(index="trade_date", columns="symbol", values="open"))
        at = frame.loc[frame["trade_date"].isin(formation_dates_set)]
        daily_at_formation.append(at[["symbol", "trade_date", *daily_feature_cols]].copy())
        _log(f"panel: daily {year}: {len(frame):,} rows, {frame['symbol'].nunique():,} symbols")
        del frame
    close_wide = pd.concat(close_frames).sort_index().astype("float64")
    open_wide = pd.concat(open_frames).sort_index().astype("float64")
    del close_frames, open_frames
    close_wide = close_wide.reindex(columns=sorted(close_wide.columns))
    open_wide = open_wide.reindex(columns=close_wide.columns)
    close_wide.columns = close_wide.columns.astype(str)
    open_wide.columns = open_wide.columns.astype(str)
    close_wide.index = _ns(close_wide.index)
    open_wide.index = _ns(open_wide.index)

    bench_close, bench_open = _benchmark_prices((*BENCHMARK_SYMBOLS, CASH_SYMBOL))
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
    _log(
        f"panel: price matrix {close_wide.shape[0]} sessions x {close_wide.shape[1]} symbols, "
        f"{close_wide.index[0].date()}..{close_wide.index[-1].date()}"
    )
    close_wide.to_parquet(CACHE_DIR / "close_wide.parquet")
    open_wide.to_parquet(CACHE_DIR / "open_wide.parquet")
    bench_returns.to_parquet(CACHE_DIR / "benchmark_returns.parquet")
    trading_calendar = close_wide.index
    last_price_date = pd.Timestamp(trading_calendar[-1])

    daily_frame = pd.concat(daily_at_formation, ignore_index=True)
    del daily_at_formation
    rows = rows.merge(
        daily_frame.rename(columns={"trade_date": "formation_date"}),
        on=["formation_date", "symbol"],
        how="left",
    )

    insider_years = years
    insider_frames = [
        _read_year_at_dates(roots["insider"], year, INSIDER_FEATURE_COLUMNS, formation_dates_set)
        for year in insider_years
    ]
    insider_frame = (
        pd.concat(insider_frames, ignore_index=True)
        if insider_frames
        else pd.DataFrame(columns=["symbol", "trade_date", *INSIDER_FEATURE_COLUMNS])
    )
    rows = rows.merge(
        insider_frame.rename(columns={"trade_date": "formation_date"}),
        on=["formation_date", "symbol"],
        how="left",
    )

    si_years = [y for y in years if (SHORT_INTEREST_ROOT / f"{y}.parquet").exists()]
    si_frames = [
        _read_year_at_dates(
            SHORT_INTEREST_ROOT, year, SHORT_INTEREST_FEATURE_COLUMNS, formation_dates_set
        )
        for year in si_years
    ]
    si_frame = (
        pd.concat(si_frames, ignore_index=True)
        if si_frames
        else pd.DataFrame(columns=["symbol", "trade_date", *SHORT_INTEREST_FEATURE_COLUMNS])
    )
    rows = rows.merge(
        si_frame.rename(columns={"trade_date": "formation_date"}),
        on=["formation_date", "symbol"],
        how="left",
    )

    news_years = [y for y in years if (NEWS_ATTENTION_ROOT / f"{y}.parquet").exists()]
    news_frames = [
        _read_year_at_dates(
            NEWS_ATTENTION_ROOT, year, NEWS_ATTENTION_FEATURE_COLUMNS, formation_dates_set
        )
        for year in news_years
    ]
    news_frame = (
        pd.concat(news_frames, ignore_index=True)
        if news_frames
        else pd.DataFrame(columns=["symbol", "trade_date", *NEWS_ATTENTION_FEATURE_COLUMNS])
    )
    rows = rows.merge(
        news_frame.rename(columns={"trade_date": "formation_date"}),
        on=["formation_date", "symbol"],
        how="left",
    )

    rows["new_13d_60d"] = _new_13d_flag(rows, trading_calendar)

    rows = rows.reset_index(drop=True)
    rows.to_parquet(CACHE_DIR / "formation_features.parquet", index=False)

    coverage = {
        column: float(rows[column].notna().mean())
        for column in ALL_FEATURE_COLUMNS
        if column in rows.columns
    }
    manifest = {
        "features_suffix": args.features_suffix,
        "roots": {k: str(v.relative_to(ROOT)) for k, v in roots.items()},
        "short_interest_root": str(SHORT_INTEREST_ROOT.relative_to(ROOT)),
        "news_attention_root": str(NEWS_ATTENTION_ROOT.relative_to(ROOT)),
        "sec_13d_path": str(SEC13D_PATH.relative_to(ROOT)),
        "years": years,
        "insider_years_loaded": insider_years,
        "short_interest_years_loaded": si_years,
        "news_attention_years_loaded": news_years,
        "formation_dates": [d.date().isoformat() for d in formation_dates],
        "last_price_date": last_price_date.date().isoformat(),
        "price_sessions": int(len(trading_calendar)),
        "symbols_in_formation_frame": int(rows["symbol"].nunique()),
        "rows": int(len(rows)),
        "raw_feature_coverage": coverage,
        "insider_role_split_columns_not_yet_built": list(INSIDER_ROLE_SPLIT_COLUMNS_NOT_YET_BUILT),
    }
    _write_json(manifest_path, manifest)
    _log(f"panel: wrote {len(rows):,} formation rows, manifest at {manifest_path}")


# --------------------------------------------------------------------------
# stage: target
# --------------------------------------------------------------------------


def _load_panel_manifest() -> dict[str, Any]:
    return json.loads((CACHE_DIR / "panel_manifest.json").read_text())


def _forward_return_lookup(
    close_sanitized: pd.DataFrame, formation: pd.DataFrame, horizon: int
) -> pd.Series:
    """``close[t+horizon]/close[t] - 1`` for every (formation_date, symbol)
    row, read off the full (all trading days) hygiene-sanitized close matrix
    via a whole-matrix ``shift(-horizon)`` and one ``.loc`` lookup per
    formation date (a few dozen, not per row).
    """
    fwd = close_sanitized.shift(-horizon) / close_sanitized - 1.0
    out = pd.Series(np.nan, index=formation.index, dtype="float64")
    for date, idx in formation.groupby("formation_date").indices.items():
        if date not in fwd.index:
            continue
        row = fwd.loc[date]
        symbols = formation.loc[idx, "symbol"]
        out.loc[idx] = row.reindex(symbols).to_numpy()
    return out


def _quintile(values: pd.Series) -> pd.Series:
    try:
        return pd.qcut(values, 5, labels=False, duplicates="drop")
    except ValueError:
        return pd.Series(np.nan, index=values.index)


def stage_target(args: argparse.Namespace) -> None:
    target_path = CACHE_DIR / "panel_target.parquet"
    if target_path.exists() and not args.force:
        _log(f"target: {target_path} present -- reusing (pass --force to rebuild)")
        return
    formation = pd.read_parquet(CACHE_DIR / "formation_features.parquet")
    formation["formation_date"] = _ns(formation["formation_date"])
    close_wide = pd.read_parquet(CACHE_DIR / "close_wide.parquet")
    close_wide.index = _ns(close_wide.index)
    _log(f"target: {len(formation):,} formation rows, sanitizing price matrix")
    close_sanitized, _open_unused, hygiene_report = price_hygiene.sanitize_price_matrices(
        close_wide, None
    )
    _log(
        f"target: price hygiene masked {hygiene_report.symbols_masked} symbols "
        f"({hygiene_report.price_cells_masked} cells)"
    )

    formation["fwd_return_21"] = _forward_return_lookup(
        close_sanitized, formation, FORWARD_HORIZON_DAYS
    )
    spy_fwd = close_sanitized["SPY"].shift(-FORWARD_HORIZON_DAYS) / close_sanitized["SPY"] - 1.0
    formation["_spy_fwd_return_21"] = formation["formation_date"].map(spy_fwd)

    beta = formation[BETA_COLUMN] if BETA_COLUMN in formation.columns else np.nan
    formation["_beta_implied_return"] = beta * formation["_spy_fwd_return_21"]
    formation["_residual_21"] = formation["fwd_return_21"] - formation["_beta_implied_return"]

    formation["size_quintile"] = formation.groupby("formation_date")["dollar_adv"].transform(
        _quintile
    )
    formation["_quintile_mean_residual"] = formation.groupby(["formation_date", "size_quintile"])[
        "_residual_21"
    ].transform("mean")
    formation["target_excess_21"] = formation["_residual_21"] - formation["_quintile_mean_residual"]

    rank_pct = formation.groupby("formation_date")["target_excess_21"].rank(pct=True)
    formation["target_top20"] = (rank_pct >= 0.80).astype("float64")
    formation.loc[formation["target_excess_21"].isna(), "target_top20"] = np.nan

    # Raw copies of the columns the twin controls rank on, preserved before
    # rank-normalization overwrites the feature columns of the same name.
    formation["_raw_momentum_252_21"] = formation.get(MOMENTUM_TWIN_NUMERATOR, np.nan)
    formation["_raw_vol_63"] = formation.get(MOMENTUM_TWIN_DENOMINATOR, np.nan)
    formation["_raw_net_buy_usd_60d"] = formation.get(INSIDER_TWIN_COLUMN, np.nan)

    present_features = [c for c in ALL_FEATURE_COLUMNS if c in formation.columns]
    coverage = {c: float(formation[c].notna().mean()) for c in present_features}
    kept_features = [c for c in present_features if coverage[c] >= FEATURE_COVERAGE_THRESHOLD]
    dropped_features = {
        c: coverage[c] for c in present_features if coverage[c] < FEATURE_COVERAGE_THRESHOLD
    }
    missing_features = [c for c in ALL_FEATURE_COLUMNS if c not in formation.columns]

    for column in kept_features:
        formation[column] = formation.groupby("formation_date")[column].rank(pct=True)

    keep_columns = [
        "formation_date",
        "symbol",
        "adv_rank",
        "dollar_adv",
        "band",
        "size_quintile",
        "fwd_return_21",
        "target_excess_21",
        "target_top20",
        "_raw_momentum_252_21",
        "_raw_vol_63",
        "_raw_net_buy_usd_60d",
        *kept_features,
    ]
    out = formation[keep_columns].copy()
    out.to_parquet(target_path, index=False)

    feature_manifest = {
        "features_considered": list(ALL_FEATURE_COLUMNS),
        "features_kept": kept_features,
        "features_dropped_low_coverage": dropped_features,
        "features_missing_from_source": missing_features,
        "coverage_threshold": FEATURE_COVERAGE_THRESHOLD,
        "target_definition": (
            "fwd_return_21 - beta_252_spy * spy_fwd_return_21, demeaned within "
            "(formation_date, dollar_adv quintile)"
        ),
        "target_top20_definition": (
            "target_excess_21 in the top 20% of its own formation date's cross-section"
        ),
        "price_hygiene": {
            k: v for k, v in hygiene_report.manifest().items() if not isinstance(v, (list, dict))
        },
        "rows_with_target": int(out["target_excess_21"].notna().sum()),
        "rows_total": int(len(out)),
    }
    _write_json(CACHE_DIR / "feature_manifest.json", feature_manifest)
    _log(
        f"target: wrote {len(out):,} rows, {len(kept_features)} features kept, "
        f"{len(dropped_features)} dropped for coverage < {FEATURE_COVERAGE_THRESHOLD:.0%}"
    )


# --------------------------------------------------------------------------
# stage: train
# --------------------------------------------------------------------------


@dataclass
class Fold:
    fold_id: int
    train_dates: list[pd.Timestamp]
    validation_dates: list[pd.Timestamp]
    test_dates: list[pd.Timestamp]
    train_start: pd.Timestamp
    train_cutoff: pd.Timestamp
    actual_train_years: float


def build_folds(
    formation_dates: list[pd.Timestamp], trading_calendar: pd.DatetimeIndex, train_years: float
) -> list[Fold]:
    """Rolling, quarterly-retrained folds. See module docstring's "Splits"
    section for the train/validation/test role design and the documented,
    deliberate overlap of validation/test roles *across* folds (never
    within one fold, and the traded portfolio only ever reads the test
    role).
    """
    frame = pd.DataFrame({"date": formation_dates})
    frame["quarter"] = frame["date"].dt.to_period("Q")
    quarters = sorted(frame["quarter"].unique())
    by_quarter = {q: sorted(frame.loc[frame["quarter"] == q, "date"]) for q in quarters}
    first_date = formation_dates[0]
    folds: list[Fold] = []
    for idx in range(1, len(quarters) - 1):
        validation_dates = by_quarter[quarters[idx]]
        test_dates = by_quarter[quarters[idx + 1]]
        if not validation_dates or not test_dates:
            continue
        validation_start = validation_dates[0]
        try:
            train_cutoff = embargo_cutoff(trading_calendar, validation_start, EMBARGO_DAYS)
        except ValueError:
            continue
        train_start = max(first_date, train_cutoff - pd.DateOffset(years=train_years))
        train_dates = [d for d in formation_dates if train_start <= d <= train_cutoff]
        if not train_dates:
            continue
        actual_years = (train_cutoff - train_start).days / 365.25
        folds.append(
            Fold(
                idx,
                train_dates,
                validation_dates,
                test_dates,
                train_start,
                train_cutoff,
                actual_years,
            )
        )
    return folds


def rank_ic_per_date(
    frame: pd.DataFrame, pred_col: str, target_col: str, min_names: int = RANKIC_MIN_NAMES
) -> list[tuple[pd.Timestamp, float]]:
    out: list[tuple[pd.Timestamp, float]] = []
    for date, group in frame.groupby("formation_date"):
        sub = group[[pred_col, target_col]].dropna()
        if len(sub) < min_names:
            continue
        if sub[pred_col].nunique() < 2 or sub[target_col].nunique() < 2:
            continue
        rho, _p = spearmanr(sub[pred_col].to_numpy(), sub[target_col].to_numpy())
        if np.isfinite(rho):
            out.append((pd.Timestamp(date), float(rho)))
    return out


def shuffle_target_within_date(panel: pd.DataFrame, target_col: str, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = panel[target_col].to_numpy(dtype="float64").copy()
    for _date, idx in panel.groupby("formation_date").indices.items():
        idx = np.asarray(idx)
        valid = idx[~np.isnan(values[idx])]
        if len(valid) > 1:
            values[valid] = rng.permutation(values[valid])
    return values


def run_training(
    panel: pd.DataFrame,
    folds: list[Fold],
    model_name: str,
    target_col: str,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    predictions: list[pd.DataFrame] = []
    fold_records: list[dict[str, Any]] = []
    for fold in folds:
        train_frame = panel.loc[panel["formation_date"].isin(fold.train_dates)]
        train_frame = train_frame.dropna(subset=[*feature_columns, target_col])
        record: dict[str, Any] = {
            "fold_id": fold.fold_id,
            "train_start": fold.train_start.date().isoformat(),
            "train_cutoff": fold.train_cutoff.date().isoformat(),
            "actual_train_years": round(fold.actual_train_years, 2),
            "train_rows": int(len(train_frame)),
            "train_dates": len(fold.train_dates),
            "validation_dates": len(fold.validation_dates),
            "test_dates": len(fold.test_dates),
        }
        if len(train_frame) < MIN_TRAIN_ROWS:
            record["skipped"] = f"train_rows {len(train_frame)} < {MIN_TRAIN_ROWS}"
            fold_records.append(record)
            continue

        model = MODEL_REGISTRY[model_name]()
        X_train = train_frame[feature_columns].to_numpy(dtype="float64")
        y_train = train_frame[target_col].to_numpy(dtype="float64")
        groups_train = train_frame["formation_date"].to_numpy()
        model.fit(X_train, y_train, groups_train)

        validation_frame = panel.loc[panel["formation_date"].isin(fold.validation_dates)].dropna(
            subset=feature_columns
        )
        val_ic: list[tuple[pd.Timestamp, float]] = []
        if not validation_frame.empty:
            preds_val = model.predict(validation_frame[feature_columns].to_numpy(dtype="float64"))
            val_scored = validation_frame[["formation_date", "symbol", target_col]].copy()
            val_scored["prediction"] = preds_val
            val_ic = rank_ic_per_date(val_scored, "prediction", target_col)
        record["validation_rankic_mean"] = (
            float(np.mean([v for _, v in val_ic])) if val_ic else None
        )
        record["validation_rankic_n_dates"] = len(val_ic)

        test_frame = panel.loc[panel["formation_date"].isin(fold.test_dates)].dropna(
            subset=feature_columns
        )
        if not test_frame.empty:
            preds_test = model.predict(test_frame[feature_columns].to_numpy(dtype="float64"))
            out = test_frame[["formation_date", "symbol", "band", "adv_rank"]].copy()
            out["prediction"] = preds_test
            out["fold_id"] = fold.fold_id
            predictions.append(out)
        fold_records.append(record)

    pred_columns = ["formation_date", "symbol", "band", "adv_rank", "prediction", "fold_id"]
    pred_frame = (
        pd.concat(predictions, ignore_index=True)
        if predictions
        else pd.DataFrame(columns=pred_columns)
    )
    return pred_frame, fold_records


def stage_train(args: argparse.Namespace) -> None:
    TRAIN_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(CACHE_DIR / "panel_target.parquet")
    panel["formation_date"] = _ns(panel["formation_date"])
    feature_manifest = json.loads((CACHE_DIR / "feature_manifest.json").read_text())
    feature_columns = feature_manifest["features_kept"]
    close_wide = pd.read_parquet(CACHE_DIR / "close_wide.parquet", columns=[])
    trading_calendar = pd.DatetimeIndex(_ns(close_wide.index))
    formation_dates = sorted(panel["formation_date"].unique())
    train_years = args.train_years or DEFAULT_TRAIN_YEARS
    folds = build_folds(formation_dates, trading_calendar, train_years)
    _write_json(
        TRAIN_DIR / "folds.json",
        [
            {
                "fold_id": f.fold_id,
                "train_start": f.train_start,
                "train_cutoff": f.train_cutoff,
                "actual_train_years": round(f.actual_train_years, 2),
                "validation_dates": [d for d in f.validation_dates],
                "test_dates": [d for d in f.test_dates],
            }
            for f in folds
        ],
    )
    _log(f"train: {len(folds)} rolling quarterly folds, {len(feature_columns)} features")

    seeds = PLACEBO_SEEDS[: args.seeds] if args.seeds else PLACEBO_SEEDS
    for model_name in args.models:
        target_col = TARGET_COLUMNS[args.target]
        key = f"{model_name}_{args.target}"
        pred_path = TRAIN_DIR / f"{key}_predictions.parquet"
        record_path = TRAIN_DIR / f"{key}.json"
        if pred_path.exists() and record_path.exists() and not args.force:
            _log(f"train: {key} cached -- reusing")
        else:
            pred_frame, fold_records = run_training(
                panel, folds, model_name, target_col, feature_columns
            )
            pred_frame.to_parquet(pred_path, index=False)
            overall_ic = [
                r["validation_rankic_mean"]
                for r in fold_records
                if r.get("validation_rankic_mean") is not None
            ]
            _write_json(
                record_path,
                {
                    "model": model_name,
                    "target": args.target,
                    "target_column": target_col,
                    "feature_columns": feature_columns,
                    "folds": fold_records,
                    "overall_validation_rankic_mean": float(np.mean(overall_ic))
                    if overall_ic
                    else None,
                    "overall_validation_rankic_n_folds": len(overall_ic),
                },
            )
            _log(
                f"train: {key} done ({len(fold_records)} folds, "
                f"{len(pred_frame):,} test-role predictions)"
            )

        if args.skip_placebo:
            continue
        for seed in seeds:
            placebo_pred_path = TRAIN_DIR / f"{key}_placebo{seed}_predictions.parquet"
            placebo_record_path = TRAIN_DIR / f"{key}_placebo{seed}.json"
            if placebo_pred_path.exists() and placebo_record_path.exists() and not args.force:
                continue
            shuffled_panel = panel.copy()
            shuffled_panel[target_col] = shuffle_target_within_date(panel, target_col, seed)
            pred_frame, fold_records = run_training(
                shuffled_panel, folds, model_name, target_col, feature_columns
            )
            pred_frame.to_parquet(placebo_pred_path, index=False)
            overall_ic = [
                r["validation_rankic_mean"]
                for r in fold_records
                if r.get("validation_rankic_mean") is not None
            ]
            _write_json(
                placebo_record_path,
                {
                    "model": model_name,
                    "target": args.target,
                    "seed": seed,
                    "folds": fold_records,
                    "overall_validation_rankic_mean": float(np.mean(overall_ic))
                    if overall_ic
                    else None,
                },
            )
            _log(f"train: {key} placebo seed {seed} done")


# --------------------------------------------------------------------------
# stage: portfolio
# --------------------------------------------------------------------------


@dataclass
class Context:
    panel: pd.DataFrame
    close_wide: pd.DataFrame
    open_wide: pd.DataFrame
    bench_returns: pd.DataFrame


def load_context() -> Context:
    panel = pd.read_parquet(CACHE_DIR / "panel_target.parquet")
    panel["formation_date"] = _ns(panel["formation_date"])
    close_wide = pd.read_parquet(CACHE_DIR / "close_wide.parquet")
    open_wide = pd.read_parquet(CACHE_DIR / "open_wide.parquet")
    close_wide.index = _ns(close_wide.index)
    open_wide.index = _ns(open_wide.index)
    bench = pd.read_parquet(CACHE_DIR / "benchmark_returns.parquet")
    bench.index = _ns(bench.index)
    return Context(panel, close_wide, open_wide, bench)


def rank_tranches(
    frame: pd.DataFrame,
    score_col: str,
    dates: list[pd.Timestamp],
    *,
    fraction: float,
    cap: int,
    ascending: bool,
) -> dict[pd.Timestamp, dict[str, float]]:
    out: dict[pd.Timestamp, dict[str, float]] = {}
    for date in dates:
        day = frame.loc[frame["formation_date"] == date, ["symbol", score_col]].dropna()
        if day.empty:
            out[date] = {}
            continue
        day = day.sort_values(score_col, ascending=ascending)
        n = max(1, int(np.ceil(len(day) * fraction)))
        n = min(n, cap, len(day))
        picked = day.head(n)["symbol"].tolist()
        weight = 1.0 / len(picked)
        out[date] = {s: weight for s in picked}
    return out


def equal_weight_tranches(
    frame: pd.DataFrame, dates: list[pd.Timestamp]
) -> dict[pd.Timestamp, dict[str, float]]:
    out: dict[pd.Timestamp, dict[str, float]] = {}
    for date in dates:
        symbols = sorted(frame.loc[frame["formation_date"] == date, "symbol"].astype(str))
        out[date] = {s: 1.0 / len(symbols) for s in symbols} if symbols else {}
    return out


def random_tranches(
    frame: pd.DataFrame, dates: list[pd.Timestamp], sizes: dict[pd.Timestamp, int], seed: int
) -> dict[pd.Timestamp, dict[str, float]]:
    rng = np.random.default_rng(seed)
    out: dict[pd.Timestamp, dict[str, float]] = {}
    for date in dates:
        candidates = sorted(frame.loc[frame["formation_date"] == date, "symbol"].astype(str))
        n = min(sizes.get(date, 0), len(candidates))
        if n <= 0 or not candidates:
            out[date] = {}
            continue
        picked = rng.choice(np.asarray(candidates, dtype=object), size=n, replace=False)
        out[date] = {str(s): 1.0 / n for s in picked}
    return out


def tranches_to_events(
    tranches: dict[pd.Timestamp, dict[str, float]], dates: list[pd.Timestamp]
) -> list[RebalanceEvent]:
    events: list[RebalanceEvent] = []
    for date in dates:
        weights = tranches.get(date) or {CASH_SYMBOL: 1.0}
        events.append(
            RebalanceEvent(
                date=pd.Timestamp(date).isoformat(),
                universe_size=len(weights),
                selected=weights,
                portfolio_beta=None,
            )
        )
    return events


def _returns_path(key: str) -> Path:
    return RETURNS_DIR / f"{key}.parquet"


def _cell_done(key: str) -> bool:
    return _returns_path(key).exists() and (BOOKS_DIR / f"{key}.json").exists()


def price_events(
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


def book_stats(
    tranches: dict[pd.Timestamp, dict[str, float]], events: list[RebalanceEvent]
) -> dict[str, Any]:
    sizes = [len([s for s in e.selected if s != CASH_SYMBOL]) for e in events]
    turnover = turnover_per_rebalance(events)
    cash_months = sum(1 for e in events if CASH_SYMBOL in e.selected and len(e.selected) == 1)
    return {
        "months": len(events),
        "tranche_size_mean": float(np.mean(sizes)) if sizes else 0.0,
        "tranche_size_min": int(np.min(sizes)) if sizes else 0,
        "tranche_size_max": int(np.max(sizes)) if sizes else 0,
        "tranche_size_latest": int(sizes[-1]) if sizes else 0,
        "cash_months": int(cash_months),
        "turnover_per_month_mean": float(np.mean(turnover[1:])) if len(turnover) > 1 else None,
        "turnover_annualized": float(np.mean(turnover[1:]) * 12.0) if len(turnover) > 1 else None,
    }


def _save_cell(key: str, returns: pd.Series, stats: dict[str, Any]) -> None:
    RETURNS_DIR.mkdir(parents=True, exist_ok=True)
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"trade_date": returns.index, "ret": returns.to_numpy(dtype="float64")})
    frame.to_parquet(_returns_path(key), index=False)
    _write_json(BOOKS_DIR / f"{key}.json", stats)


def _price_and_save(
    ctx: Context,
    key: str,
    tranches: dict[pd.Timestamp, dict[str, float]],
    dates: list[pd.Timestamp],
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    events = tranches_to_events(tranches, dates)
    returns, missing = price_events(ctx, events)
    stats = book_stats(tranches, events)
    stats["symbols_missing_from_price_matrix"] = missing
    stats["price_hygiene"] = {
        k: v
        for k, v in kernel_loop.LAST_PRICE_HYGIENE_MANIFEST.items()
        if not isinstance(v, (list, dict))
    }
    if extra:
        stats.update(extra)
    _save_cell(key, returns, stats)


def all_test_dates() -> list[pd.Timestamp]:
    """Every formation date that is the *test* role of some fold -- the one
    shared axis every portfolio/control/placebo cell in this stage is priced
    over (see module docstring's "Portfolio / controls" section).
    """
    folds = json.loads((TRAIN_DIR / "folds.json").read_text())
    dates: set[pd.Timestamp] = set()
    for fold in folds:
        dates.update(pd.Timestamp(d) for d in fold["test_dates"])
    return sorted(dates)


def cell_key(kind: str, model: str, target: str, band: str, seed: str | int | None = None) -> str:
    key = f"{kind}__{model}__{target}__{band}"
    return key if seed is None else f"{key}__s{seed}"


def stage_portfolio(args: argparse.Namespace) -> None:
    ctx = load_context()
    bands = list(args.bands) if args.bands else list(BANDS)
    seeds = RANDOM_SEEDS[: args.seeds] if args.seeds else RANDOM_SEEDS
    placebo_seeds = PLACEBO_SEEDS[: args.seeds] if args.seeds else PLACEBO_SEEDS
    test_dates = all_test_dates() if args.models else []
    if not test_dates:
        raise SystemExit("portfolio: no test dates found -- run --stage train first")
    _log(
        f"portfolio: {len(test_dates)} test-role formation dates "
        f"{test_dates[0].date()}..{test_dates[-1].date()}"
    )

    for model_name in args.models:
        key = f"{model_name}_{args.target}"
        pred_path = TRAIN_DIR / f"{key}_predictions.parquet"
        if not pred_path.exists():
            _log(f"portfolio: {pred_path} missing -- skip {model_name}")
            continue
        predictions = pd.read_parquet(pred_path)
        predictions["formation_date"] = _ns(predictions["formation_date"])
        panel_scored = ctx.panel.merge(
            predictions[["formation_date", "symbol", "prediction"]],
            on=["formation_date", "symbol"],
            how="inner",
        )
        for band in bands:
            pool = band_frame(panel_scored, band)
            if pool.empty:
                _log(f"portfolio: {model_name}/{args.target}/{band}: empty pool -- skipped")
                continue
            top = rank_tranches(
                pool,
                "prediction",
                test_dates,
                fraction=TOP_DECILE_FRACTION,
                cap=MAX_NAMES,
                ascending=False,
            )
            bottom = rank_tranches(
                pool,
                "prediction",
                test_dates,
                fraction=BOTTOM_DECILE_FRACTION,
                cap=MAX_NAMES,
                ascending=True,
            )
            ew = equal_weight_tranches(pool, test_dates)
            top_sizes = {d: len(t) for d, t in top.items()}

            for name, tranches in (("top_decile", top), ("bottom_decile", bottom), ("band_ew", ew)):
                cell = cell_key(name, model_name, args.target, band)
                if _cell_done(cell) and not args.force:
                    continue
                _price_and_save(ctx, cell, tranches, test_dates)
                _log(f"portfolio: {cell} done")

            for seed in seeds:
                cell = cell_key("random", model_name, args.target, band, seed)
                if _cell_done(cell) and not args.force:
                    continue
                control = random_tranches(pool, test_dates, top_sizes, int(seed))
                _price_and_save(ctx, cell, control, test_dates, extra={"seed": int(seed)})
            _log(f"portfolio: {model_name}/{args.target}/{band}: random controls done")

            mom_cell = cell_key("momentum_twin", model_name, args.target, band)
            if not (_cell_done(mom_cell) and not args.force):
                mom_pool = pool.copy()
                mom_pool["_mom_score"] = mom_pool["_raw_momentum_252_21"] / mom_pool["_raw_vol_63"]
                mom_pool = mom_pool.replace([np.inf, -np.inf], np.nan)
                mom_tranches = rank_tranches(
                    mom_pool,
                    "_mom_score",
                    test_dates,
                    fraction=TOP_DECILE_FRACTION,
                    cap=MAX_NAMES,
                    ascending=False,
                )
                _price_and_save(ctx, mom_cell, mom_tranches, test_dates)

            ins_cell = cell_key("insider_twin", model_name, args.target, band)
            if not (_cell_done(ins_cell) and not args.force):
                ins_tranches = rank_tranches(
                    pool,
                    "_raw_net_buy_usd_60d",
                    test_dates,
                    fraction=TOP_DECILE_FRACTION,
                    cap=MAX_NAMES,
                    ascending=False,
                )
                _price_and_save(ctx, ins_cell, ins_tranches, test_dates)
            _log(f"portfolio: {model_name}/{args.target}/{band}: twins done")

        if args.skip_placebo:
            continue
        for seed in placebo_seeds:
            placebo_pred_path = TRAIN_DIR / f"{key}_placebo{seed}_predictions.parquet"
            if not placebo_pred_path.exists():
                continue
            placebo_predictions = pd.read_parquet(placebo_pred_path)
            placebo_predictions["formation_date"] = _ns(placebo_predictions["formation_date"])
            placebo_scored = ctx.panel.merge(
                placebo_predictions[["formation_date", "symbol", "prediction"]],
                on=["formation_date", "symbol"],
                how="inner",
            )
            for band in bands:
                pool = band_frame(placebo_scored, band)
                if pool.empty:
                    continue
                cell = cell_key("placebo", model_name, args.target, band, seed)
                if _cell_done(cell) and not args.force:
                    continue
                tranches = rank_tranches(
                    pool,
                    "prediction",
                    test_dates,
                    fraction=TOP_DECILE_FRACTION,
                    cap=MAX_NAMES,
                    ascending=False,
                )
                _price_and_save(ctx, cell, tranches, test_dates, extra={"placebo_seed": seed})
            _log(f"portfolio: {model_name}/{args.target}: placebo seed {seed} done")


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def nw_tstat(values: np.ndarray, lag: int = 0) -> float:
    clean = np.asarray(values, dtype="float64")
    clean = clean[np.isfinite(clean)]
    n = len(clean)
    if n < 6:
        return float("nan")
    mean = clean.mean()
    resid = clean - mean
    variance = float(resid @ resid) / n
    for lag_ in range(1, min(lag, n - 1) + 1):
        weight = 1.0 - lag_ / (lag + 1.0)
        variance += 2.0 * weight * float(resid[lag_:] @ resid[:-lag_]) / n
    if variance <= 0:
        return float("nan")
    return float(mean / math.sqrt(variance / n))


def monthly_returns(series: pd.Series) -> pd.Series:
    return (1.0 + series).groupby(series.index.to_period("M")).prod() - 1.0


def excess_block(strategy: pd.Series, benchmark: pd.Series) -> dict[str, Any]:
    aligned = benchmark.reindex(strategy.index).fillna(0.0)
    ex = monthly_returns(strategy) - monthly_returns(aligned)
    values = ex.to_numpy(dtype="float64")
    return {
        "mean_monthly_excess": float(np.nanmean(values)) if len(values) else None,
        "t_nw": nw_tstat(values, 0),
        "months": int(len(values)),
    }


def load_returns(key: str) -> pd.Series | None:
    path = _returns_path(key)
    if not path.exists():
        return None
    frame = pd.read_parquet(path)
    series = pd.Series(frame["ret"].to_numpy(dtype="float64"), index=_ns(frame["trade_date"]))
    return series.sort_index()


def load_book(key: str) -> dict[str, Any] | None:
    path = BOOKS_DIR / f"{key}.json"
    return json.loads(path.read_text()) if path.exists() else None


def cell_metrics(series: pd.Series, bench: pd.DataFrame) -> dict[str, Any] | None:
    if len(series) < 20:
        return None
    stats: dict[str, Any] = {
        "cagr": annualized_cagr(series),
        "vol": float(series.std() * math.sqrt(252.0)),
        "max_drawdown": max_drawdown(series),
        "sessions": int(len(series)),
        "window": [series.index[0].date().isoformat(), series.index[-1].date().isoformat()],
    }
    try:
        stats["cagr_excess_vol_matched_spy"] = cagr_excess_vol_matched(
            series, bench["SPY"].fillna(0.0), bench[CASH_SYMBOL].fillna(0.0)
        )
        stats["vol_match_weight_vs_spy"] = vol_match_weight(series, bench["SPY"].fillna(0.0))
    except ValueError:
        stats["cagr_excess_vol_matched_spy"] = None
        stats["vol_match_weight_vs_spy"] = None
    stats["excess"] = {
        sym: excess_block(series, bench[sym].fillna(0.0)) for sym in BENCHMARK_SYMBOLS
    }
    return stats


def benchmark_metrics(bench: pd.DataFrame) -> dict[str, Any]:
    """Mandatory buy-and-hold disclosure for every benchmark this study
    compares against (SPY/IWM/MTUM/SPMO), independent of any cell -- the
    project's own "复盘必须报 SPY / MTUM / SPMO" rule
    (``reports/research/hypotheses/README.md``).
    """
    out: dict[str, Any] = {}
    for sym in BENCHMARK_SYMBOLS:
        series = bench[sym].dropna()
        if len(series) < 20:
            out[sym] = None
            continue
        out[sym] = {
            "cagr": annualized_cagr(series),
            "max_drawdown": max_drawdown(series),
            "vol": float(series.std() * math.sqrt(252.0)),
            "window": [series.index[0].date().isoformat(), series.index[-1].date().isoformat()],
        }
    return out


def _percentiles(values: list[float]) -> dict[str, float | None]:
    clean = [v for v in values if v is not None and np.isfinite(v)]
    if not clean:
        return {"mean": None, "p5": None, "p95": None, "n": 0}
    arr = np.asarray(clean, dtype="float64")
    return {
        "mean": float(arr.mean()),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
        "n": int(len(arr)),
    }


def stage_report(args: argparse.Namespace) -> dict[str, Any]:
    ctx = load_context()
    bench = ctx.bench_returns
    bands = list(args.bands) if args.bands else list(BANDS)
    seeds = RANDOM_SEEDS[: args.seeds] if args.seeds else RANDOM_SEEDS
    placebo_seeds = PLACEBO_SEEDS[: args.seeds] if args.seeds else PLACEBO_SEEDS
    panel_manifest = _load_panel_manifest()
    feature_manifest = json.loads((CACHE_DIR / "feature_manifest.json").read_text())

    cells: dict[str, Any] = {}
    train_summaries: dict[str, Any] = {}
    for model_name in args.models:
        key = f"{model_name}_{args.target}"
        record_path = TRAIN_DIR / f"{key}.json"
        if not record_path.exists():
            continue
        train_record = json.loads(record_path.read_text())
        train_summaries[key] = train_record
        placebo_ic: list[float] = []
        placebo_cagr_by_band: dict[str, list[float]] = {b: [] for b in bands}
        for seed in placebo_seeds:
            precord_path = TRAIN_DIR / f"{key}_placebo{seed}.json"
            if precord_path.exists():
                precord = json.loads(precord_path.read_text())
                if precord.get("overall_validation_rankic_mean") is not None:
                    placebo_ic.append(precord["overall_validation_rankic_mean"])
            for band in bands:
                series = load_returns(cell_key("placebo", model_name, args.target, band, seed))
                if series is not None:
                    metrics = cell_metrics(series, bench)
                    if metrics:
                        placebo_cagr_by_band[band].append(metrics["cagr"])
        placebo_agg = {
            "validation_rankic": _percentiles(placebo_ic),
            "top_decile_cagr_by_band": {
                b: _percentiles(v) for b, v in placebo_cagr_by_band.items()
            },
        }

        for band in bands:
            band_cells: dict[str, Any] = {}
            for kind in ("top_decile", "bottom_decile", "band_ew", "momentum_twin", "insider_twin"):
                series = load_returns(cell_key(kind, model_name, args.target, band))
                band_cells[kind] = {
                    "metrics": cell_metrics(series, bench) if series is not None else None,
                    "book": load_book(cell_key(kind, model_name, args.target, band)),
                }
            random_metrics = []
            for seed in seeds:
                series = load_returns(cell_key("random", model_name, args.target, band, seed))
                if series is not None:
                    m = cell_metrics(series, bench)
                    if m:
                        random_metrics.append(m)
            random_agg = (
                {
                    "cagr": _percentiles([m["cagr"] for m in random_metrics]),
                    "mean_monthly_excess_spy": _percentiles(
                        [m["excess"]["SPY"]["mean_monthly_excess"] for m in random_metrics]
                    ),
                }
                if random_metrics
                else None
            )

            top_series = load_returns(cell_key("top_decile", model_name, args.target, band))
            bottom_series = load_returns(cell_key("bottom_decile", model_name, args.target, band))
            long_short = None
            if top_series is not None and bottom_series is not None:
                spread = top_series.reindex(top_series.index).fillna(0.0) - bottom_series.reindex(
                    top_series.index
                ).fillna(0.0)
                long_short = cell_metrics(spread, bench)

            top_metrics = band_cells["top_decile"]["metrics"]
            mom_metrics = band_cells["momentum_twin"]["metrics"]
            ins_metrics = band_cells["insider_twin"]["metrics"]
            best_twin_excess = None
            for twin in (mom_metrics, ins_metrics):
                if twin and twin.get("cagr_excess_vol_matched_spy") is not None:
                    value = twin["cagr_excess_vol_matched_spy"]
                    best_twin_excess = (
                        value if best_twin_excess is None else max(best_twin_excess, value)
                    )
            overall_val_ic = train_record.get("overall_validation_rankic_mean")
            placebo_ic_mean = placebo_agg["validation_rankic"]["mean"]
            placebo_share = (
                placebo_ic_mean / overall_val_ic
                if overall_val_ic and overall_val_ic > 0 and placebo_ic_mean is not None
                else None
            )
            top_excess = top_metrics.get("cagr_excess_vol_matched_spy") if top_metrics else None
            reasons: list[str] = []
            if overall_val_ic is None or overall_val_ic < REFUTE_RANKIC_THRESHOLD:
                verdict = "refuted"
                reasons.append(
                    f"验证集 RankIC {_num(overall_val_ic, 4)} < {REFUTE_RANKIC_THRESHOLD}"
                )
            elif placebo_share is not None and placebo_share >= REFUTE_PLACEBO_SHARE_THRESHOLD:
                verdict = "refuted"
                reasons.append(f"占位达到真实 RankIC 的 {placebo_share:.0%}（≥ 50%）")
            elif (
                top_excess is not None
                and best_twin_excess is not None
                and top_excess <= best_twin_excess
            ):
                verdict = "refuted"
                reasons.append("前 10% 组同波动超额未优于最好的规则孪生")
            elif args.skip_placebo:
                verdict = "inconclusive"
                reasons.append("本次运行跳过占位（--skip-placebo），占位条件未评估")
            elif top_excess is None or best_twin_excess is None:
                verdict = "inconclusive"
                reasons.append("同波动超额或规则孪生数据不足，无法判定第三条否定条件")
            else:
                verdict = "supported"
                reasons.append(
                    "验证集 RankIC 达标，占位份额 < 50%，前 10% 组同波动超额优于规则孪生"
                )

            cells[f"{key}__{band}"] = {
                "model": model_name,
                "target": args.target,
                "band": band,
                **band_cells,
                "long_short": long_short,
                "random": random_agg,
                "placebo": placebo_agg,
                "verdict": {
                    "verdict": verdict,
                    "reasons": reasons,
                    "overall_validation_rankic_mean": overall_val_ic,
                    "placebo_validation_rankic_mean": placebo_ic_mean,
                    "placebo_share_of_real": placebo_share,
                    "top_decile_vol_matched_excess": top_excess,
                    "best_twin_vol_matched_excess": best_twin_excess,
                },
            }

    verdicts = [c["verdict"]["verdict"] for c in cells.values()]
    if any(v == "supported" for v in verdicts):
        card_verdict = "supported"
    elif verdicts and all(v == "refuted" for v in verdicts):
        card_verdict = "refuted"
    else:
        card_verdict = "inconclusive"

    selected_combos = [{"model": m, "target": args.target} for m in args.models]
    summary = {
        "iteration_id": ITERATION_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "panel_manifest": panel_manifest,
        "feature_manifest": feature_manifest,
        "benchmarks": benchmark_metrics(bench),
        "design": {
            "execution": EXECUTION,
            "cost_bps_per_side": PRIMARY_COST_BPS,
            "max_names": MAX_NAMES,
            "top_decile_fraction": TOP_DECILE_FRACTION,
            "bottom_decile_fraction": BOTTOM_DECILE_FRACTION,
            "embargo_days": EMBARGO_DAYS,
            "train_years": args.train_years or DEFAULT_TRAIN_YEARS,
            "forward_horizon_days": FORWARD_HORIZON_DAYS,
            "random_seeds": list(seeds),
            "placebo_seeds": list(placebo_seeds),
            "skip_placebo": bool(args.skip_placebo),
            "returns_contract": kernel_loop.PORTFOLIO_RETURNS_CONTRACT,
        },
        "train_summaries": train_summaries,
        "cells": cells,
        "card_verdict": {"verdict": card_verdict, "cells_evaluated": len(cells)},
        "trial_family": {
            "family": "ml_ranking_broad",
            "card_models": list(CARD_MODELS),
            "card_targets": list(CARD_TARGETS),
            "selectable_combinations_this_card": len(CARD_MODELS) * len(CARD_TARGETS),
            "selected_this_round": selected_combos,
        },
    }
    _write_json(SUMMARY_PATH, summary)
    _log(f"report: wrote {SUMMARY_PATH} ({len(cells)} cells) -- card verdict {card_verdict}")
    return summary


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def _num(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value:.{digits}f}"


def _bp(value: float | None) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    return f"{value * 1e4:+.0f}bp"


def render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    man = summary["panel_manifest"]
    fm = summary["feature_manifest"]
    design = summary["design"]
    lines.append("# H-20260917-02 全池截面 ML 排序（岭回归基线，part 1/2）— 报告")
    lines.append("")
    lines.append(
        f"- 生成时间：{summary['generated_at'][:16]} UTC · "
        f"features_suffix=`{man['features_suffix']}` · 年份 {man['years']}"
    )
    lines.append(
        f"- 形成日：{len(man['formation_dates'])} 个月末 cohort 日，"
        f"{man['formation_dates'][0]} .. {man['formation_dates'][-1]}；"
        f"价格到 {man['last_price_date']}"
    )
    lines.append(
        f"- 特征：考虑 {len(fm['features_considered'])} 列，保留 {len(fm['features_kept'])} "
        f"列（覆盖率 ≥ {fm['coverage_threshold']:.0%}），因覆盖率不足丢弃 "
        f"{len(fm['features_dropped_low_coverage'])} 列，来源缺失 "
        f"{len(fm['features_missing_from_source'])} 列"
    )
    lines.append(f"- 保留特征：`{'`, `'.join(fm['features_kept'])}`")
    if fm["features_dropped_low_coverage"]:
        dropped = ", ".join(f"{k}({v:.0%})" for k, v in fm["features_dropped_low_coverage"].items())
        lines.append(f"- 丢弃（覆盖率不足）：{dropped}")
    if fm["features_missing_from_source"]:
        lines.append(f"- 数据源里不存在：`{'`, `'.join(fm['features_missing_from_source'])}`")
    lines.append(
        f"- 目标：{fm['target_definition']}；备选（未使用除非 --target top20）："
        f"{fm['target_top20_definition']}"
    )
    lines.append(
        f"- 执行与成本：{design['execution']}，{design['cost_bps_per_side']:.0f} bp/边；"
        f"训练窗口 {design['train_years']} 年、隔离 {design['embargo_days']} 个交易日、"
        f"按季重训；前/后 {design['top_decile_fraction']:.0%} 组，上限 {design['max_names']} 只"
    )
    if design["skip_placebo"]:
        placebo_note = "本次跳过（--skip-placebo）"
    else:
        placebo_note = f"打乱标签 {len(design['placebo_seeds'])} 个种子"
    lines.append(f"- 占位：{placebo_note}")
    lines.append("")

    tf = summary["trial_family"]
    lines.append(f"## 0. 结论：**{summary['card_verdict']['verdict']}**")
    lines.append("")
    lines.append(
        f"- 本轮评估 {summary['card_verdict']['cells_evaluated']} 个（模型×目标×分段）单元。"
    )
    lines.append(
        f"- 假设族 `{tf['family']}` 卡上声明的可选组合 {tf['selectable_combinations_this_card']} "
        f"个（模型 {tf['card_models']} × 目标 {tf['card_targets']}）；本轮实际运行 "
        f"{tf['selected_this_round']}。"
    )
    lines.append("")

    lines.append("## 1. 必报对照（买入持有，收盘到收盘，无成本）")
    lines.append("")
    lines.append("| 基准 | CAGR | 最大回撤 | 年化波动 | 窗口 |")
    lines.append("|---|---:|---:|---:|---|")
    for sym in BENCHMARK_SYMBOLS:
        b = summary["benchmarks"].get(sym)
        if not b:
            lines.append(f"| {sym} | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| {sym} | {_pct(b['cagr'])} | {_pct(b['max_drawdown'])} | {_pct(b['vol'])} | "
            f"{b['window'][0]} .. {b['window'][1]} |"
        )
    lines.append("")

    for key, train_record in summary["train_summaries"].items():
        lines.append(f"## 2. 滚动折叠与验证 RankIC — `{key}`")
        lines.append("")
        lines.append(
            f"- 总体验证 RankIC 均值：{_num(train_record.get('overall_validation_rankic_mean'), 4)}"
            f"（{train_record.get('overall_validation_rankic_n_folds', 0)} 个折）"
        )
        lines.append("")
        lines.append(
            "| 折 | 训练起 | 训练止（隔离后） | 实际训练年数 | 训练行数 | "
            "验证日数 | 验证 RankIC | 测试日数 |"
        )
        lines.append("|---:|---|---|---:|---:|---:|---:|---:|")
        for fold in train_record["folds"]:
            if fold.get("skipped"):
                lines.append(
                    f"| {fold['fold_id']} | {fold['train_start']} | {fold['train_cutoff']} | "
                    f"{fold['actual_train_years']} | {fold['train_rows']} | - | 跳过："
                    f"{fold['skipped']} | - |"
                )
                continue
            lines.append(
                f"| {fold['fold_id']} | {fold['train_start']} | {fold['train_cutoff']} | "
                f"{fold['actual_train_years']} | {fold['train_rows']} | "
                f"{fold['validation_dates']} | {_num(fold.get('validation_rankic_mean'), 4)} | "
                f"{fold['test_dates']} |"
            )
        lines.append("")

    lines.append("## 3. 组合表现（按模型×目标×分段）")
    lines.append("")
    header = (
        "| 单元 | 分段 | CAGR | 最大回撤 | 年化波动 | 同波动 SPY 超额 | 月超额 vs SPY(t) | "
        "vs IWM(t) | 月双边换手 |"
    )
    sep = "|---|---|---:|---:|---:|---:|---:|---:|---:|"
    for cell_id, cell in summary["cells"].items():
        lines.append(f"### `{cell_id}` — 判定：**{cell['verdict']['verdict']}**")
        lines.append("")
        for reason in cell["verdict"]["reasons"]:
            lines.append(f"- {reason}")
        lines.append("")
        lines.append(header)
        lines.append(sep)
        for kind in ("top_decile", "bottom_decile", "band_ew", "momentum_twin", "insider_twin"):
            m = cell[kind]["metrics"]
            book = cell[kind]["book"] or {}
            if not m:
                lines.append(
                    f"| {kind} | {cell['band']} | n/a | n/a | n/a | n/a | n/a | n/a | n/a |"
                )
                continue
            spy = m["excess"]["SPY"]
            iwm = m["excess"]["IWM"]
            lines.append(
                f"| {kind} | {cell['band']} | {_pct(m['cagr'])} | {_pct(m['max_drawdown'])} | "
                f"{_pct(m['vol'])} | {_pct(m['cagr_excess_vol_matched_spy'])} | "
                f"{_bp(spy['mean_monthly_excess'])} ({_num(spy['t_nw'], 1)}) | "
                f"{_bp(iwm['mean_monthly_excess'])} ({_num(iwm['t_nw'], 1)}) | "
                f"{_num(book.get('turnover_per_month_mean'), 2)} |"
            )
        if cell["long_short"]:
            ls = cell["long_short"]
            lines.append(
                f"| top−bottom 价差 | {cell['band']} | {_pct(ls['cagr'])} | "
                f"{_pct(ls['max_drawdown'])} | {_pct(ls['vol'])} | "
                f"{_pct(ls['cagr_excess_vol_matched_spy'])} | "
                f"{_bp(ls['excess']['SPY']['mean_monthly_excess'])} "
                f"({_num(ls['excess']['SPY']['t_nw'], 1)}) | "
                f"{_bp(ls['excess']['IWM']['mean_monthly_excess'])} "
                f"({_num(ls['excess']['IWM']['t_nw'], 1)}) | n/a |"
            )
        if cell["random"]:
            r = cell["random"]
            lines.append(
                f"| 同尺寸随机均值 | {cell['band']} | "
                f"{_pct(r['cagr']['mean'])} [{_pct(r['cagr']['p5'])}, {_pct(r['cagr']['p95'])}] | "
                f"n/a | n/a | n/a | "
                f"{_bp(r['mean_monthly_excess_spy']['mean'])} | n/a | n/a |"
            )
        lines.append("")
        placebo = cell["placebo"]
        lines.append(
            f"占位（打乱标签）：验证 RankIC 均值 {_num(placebo['validation_rankic']['mean'], 4)} "
            f"[{_num(placebo['validation_rankic']['p5'], 4)}, "
            f"{_num(placebo['validation_rankic']['p95'], 4)}]，"
            f"前 10% 组 CAGR "
            f"{_pct(placebo['top_decile_cagr_by_band'].get(cell['band'], {}).get('mean'))}"
        )
        lines.append("")

    lines.append("## 4. 文件")
    lines.append("")
    lines.append(
        f"- 汇总：`{SUMMARY_PATH.relative_to(ROOT)}`；本报告：`{REPORT_PATH.relative_to(ROOT)}`"
    )
    lines.append(
        f"- 缓存（gitignore）：`{CACHE_DIR.relative_to(ROOT)}/`（形成帧、宽价格矩阵、按折的"
        "训练记录与预测、每个单元的日收益与簿统计）"
    )
    lines.append(
        "- 脚本：`scripts/run_h20260917_02_ml_ranking.py`（阶段 panel / target / train / "
        "portfolio / report，全部可断点续跑；模型注册表当前只有 `ridge`，"
        "`lambdarank`/`gbdt` 是后续任务的注册表条目，不是重写）"
    )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stage",
        choices=["all", "panel", "target", "train", "portfolio", "report"],
        default="all",
    )
    parser.add_argument(
        "--features-suffix", default="_broad", help="'' for the narrow smoke-test tables"
    )
    parser.add_argument("--years", type=int, nargs="*", default=None)
    parser.add_argument("--bands", nargs="*", default=None, choices=list(BANDS))
    parser.add_argument("--models", nargs="*", default=["ridge"], choices=sorted(MODEL_REGISTRY))
    parser.add_argument("--target", choices=list(CARD_TARGETS), default="excess21")
    parser.add_argument(
        "--seeds", type=int, default=None, help="number of random/placebo seeds (default 5)"
    )
    parser.add_argument("--train-years", type=float, default=None)
    parser.add_argument("--skip-placebo", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tag = bind_paths(args.features_suffix)
    _log(f"paths: feature family {tag!r} -> cache {CACHE_DIR}, report {REPORT_PATH.name}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
        REPORT_PATH.write_text(render_markdown(summary), encoding="utf-8")
        _log(f"report: wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
