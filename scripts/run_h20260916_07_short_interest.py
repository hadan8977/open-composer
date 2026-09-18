"""H-20260916-07: FINRA short-interest avoid list -- pre-check, then twin cells.

Card: ``reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md``

Order of operations, and why it is this order
---------------------------------------------
The pre-check runs **first and can stop the round**. That rule is
``L-20260916-01``'s main operational lesson: H-01 spent a day pricing 29 books
to discover that the new data layer covered 1.9% of the momentum book, a fact a
30-row cross-table would have produced in half an hour. ``docs/current-view.zh.md``
now carries it as a process rule, so this round's stage order enforces it:
``precheck`` refuses to hand over to ``gate-states`` unless the avoid condition
hits at least :data:`MIN_BOOK_HIT_SHARE` of the book's stock-weeks.

The pre-check deliberately asks two different questions, because the second one
is the one the user's 2026-09-17 ruling added and it is not a subset of the
first:

1. **As a layer on the momentum book** (the card's own framing): does the avoid
   condition touch enough of the top-50 book to matter, and do high
   days-to-cover names overlap high-momentum names -- the card's stated main
   confound (short squeezes *are* momentum)?
2. **As an independent input on the broad liquid universe** (price >= $2,
   dollar ADV >= $1M -- not the top 500): is there a monotone forward-excess
   pattern across days-to-cover quintiles at all? A layer on a 50-name book can
   fail for pure sample-size reasons while the same signal is perfectly usable
   as a standalone cross-sectional input, and "new signals are not assumed to
   be layers on momentum" is now a standing rule. Both tables are printed side
   by side so the round cannot conclude "short interest is useless" when what
   it measured was "short interest does not help *this* 50-name book".

Stages (each resumable; rerunning skips finished work)
------------------------------------------------------
``export``
    The unchanged M0B momentum top-50 book (score = ``momentum_252_21 /
    vol_63``, point-in-time top-500 pool, ``k=50``, equal weight, gate off,
    next-open execution) into ``picks.parquet`` + ``schedule_baseline.json``.
    Rebuilt here rather than copied from H-01's directory so it uses the
    **fixed** universe cohorts (the 2026-09-16 cohort repair) instead of the
    ones H-01 ran on.
``precheck``
    The mandatory cross-table -> ``precheck.md`` / ``precheck.json``.
``gate-states``
    Join ``data/features/short_interest/`` (and each placebo root) onto the
    book, assign avoid states -> ``gate_states/{source}.parquet``.
``evaluate``
    Price the baseline, both avoid variants (normalized and, for disclosure,
    the raw de-leveraged versions), plus two families of controls with >= 5
    seeds each -> ``results-raw.json``.
``report``
    Render ``report.md`` / ``report.json`` from the checkpoint.

Controls (both required, and neither is optional after L-20260916-01)
--------------------------------------------------------------------
* **Same-size random drop**: the avoid states are permuted *within each
  rebalance week*, so the same number of names is dropped or halved every week
  and only the identity changes. An improvement this reproduces is a
  concentration effect.
* **Publication-shift placebo**: the whole feature table is rebuilt with each
  settlement date's visibility shifted by a random +/-1..N sessions. An
  improvement this reproduces is not short-interest information.

Both are reported as distributions over >= 5 seeds, never as a single number
(``L-20260916-03``: one seed decided a borderline call by 0.007).

Usage::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_07_short_interest.py --stage export

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_07_short_interest.py --stage precheck
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as scipy_stats  # noqa: E402

from open_composer.research.features.panel import load_feature_panel  # noqa: E402
from open_composer.research.features.short_interest import (  # noqa: E402
    AVOID_PERCENTILE_THRESHOLD,
    CROSS_SECTIONAL_POOL_TOP_N,
    SHORT_INTEREST_ROOT,
)
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.insider_gate import (  # noqa: E402
    STATE_WEIGHT_MULTIPLIER,
    gate_state_changes_per_year,
    normalize_weights_to_full_exposure,
    rebalances_with_gate_change_per_year,
    state_shares,
)
from open_composer.research.kernel.loop import (  # noqa: E402
    RebalanceEvent,
    build_weight_schedule,
    returns_from_weight_schedule,
    universe_as_of_calendar_month,
    weekly_rebalance_dates,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.pick_export import (  # noqa: E402
    PickCollector,
    turnover_per_rebalance,
    weight_schedule_from_pick_frame,
)
from open_composer.research.kernel.short_interest_gate import (  # noqa: E402
    AVOID_SPECS,
    avoid_states,
    shuffle_states_within_date,
)
from open_composer.research.kernel.vol_matched import (  # noqa: E402
    cagr_excess_vol_matched,
    vol_match_weight,
)
from open_composer.research.regime import gates as regime_gates  # noqa: E402
from open_composer.research.regime import metrics as regime_metrics  # noqa: E402
from scripts.build_short_interest_features import load_records  # noqa: E402

m_grid = importlib.import_module("scripts.run_step13_m_grid")

OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_07_short_interest"
PICKS_PATH = OUT_DIR / "picks.parquet"
SCHEDULE_PATH = OUT_DIR / "schedule_baseline.json"
PRECHECK_MD = OUT_DIR / "precheck.md"
PRECHECK_JSON = OUT_DIR / "precheck.json"
POOL_PANEL_PATH = OUT_DIR / "precheck_pool.parquet"
BROAD_PANEL_PATH = OUT_DIR / "precheck_broad.parquet"
GATE_STATES_DIR = OUT_DIR / "gate_states"
RESULTS_PATH = OUT_DIR / "results-raw.json"
REPORT_JSON_PATH = OUT_DIR / "report.json"
REPORT_MD_PATH = OUT_DIR / "report.md"

DAILY_ROOT = ROOT / "data" / "features" / "daily"
LABELS_ROOT = ROOT / "data" / "features" / "labels"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"

#: The primary cell, unchanged from Step 13-M0b / H-01 / H-03.
SCORE_COLUMN = "momentum_252_21_over_vol_63"
PRIMARY_CELL = "step13_m0b_mom_over_vol63_uni500_k50_gate_off"
UNIVERSE_TOP_N = CROSS_SECTIONAL_POOL_TOP_N
TOP_K = 50
TRAIN_WINDOW_MONTHS = m_grid.TRAIN_WINDOW_MONTHS
PRIMARY_COST_BPS = m_grid.PRIMARY_COST_BPS
STRESS_COST_BPS = m_grid.STRESS_COST_BPS
CASH_SYMBOL = m_grid.CASH_SYMBOL
EXECUTION = "next_open"

#: The FINRA archive starts 2017-12-29 (first visible 2018-01-10), so this
#: round's book starts in 2018 -- one year later than H-01's. 2017 is warm-up
#: for the momentum score only.
DATA_YEARS: tuple[int, ...] = tuple(range(2016, 2027))
TEST_YEARS: tuple[int, ...] = tuple(range(2018, 2027))
SCREEN_YEARS: tuple[int, ...] = tuple(range(2018, 2027))

#: Thresholds the pre-check reports the avoid condition at. 0.80 is the card's
#: own ("highest 20%"); 0.70 and 0.90 are printed next to it so the report can
#: say whether the hit rate is a knife edge or a plateau, without either of them
#: becoming a tuning knob (the twin cells only ever use 0.80).
PRECHECK_THRESHOLDS: tuple[float, ...] = (0.70, 0.80, 0.90)

#: The pre-check's stop rule, from the brief: below this share of book
#: stock-weeks the layer cannot move the book enough to be measurable and the
#: round stops at the pre-check instead of pricing anything.
MIN_BOOK_HIT_SHARE = 0.10

#: Broad liquid universe for the independent-signal question.
BROAD_MIN_CLOSE = 2.0
BROAD_MIN_DOLLAR_ADV = 1_000_000.0
BROAD_QUINTILES = 5

PLACEBO_SHIFT_DAYS = 10
PLACEBO_SEEDS: tuple[int, ...] = (20260916, 20260917, 20260918, 20260919, 20260920)
SHUFFLE_SEEDS: tuple[int, ...] = (20260916, 20260917, 20260918, 20260919, 20260920)
CONTROL_SHIFT = "shift"
CONTROL_SHUFFLE = "shuffle"

H03_COMPARABLE_START = pd.Timestamp("2020-04-01")

LABEL_COLUMNS: tuple[str, ...] = ("label_excess_5", "label_excess_21")

#: Stop conditions, verbatim from the card and the brief.
STOP_EXCESS_IMPROVEMENT_PP = 0.02
STOP_CONTROL_SHARE = 0.5


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")
    temporary.replace(path)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".parquet.part")
    frame.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(path)


def _events_to_json(schedule: list[RebalanceEvent]) -> list[dict[str, Any]]:
    """Same shape H-20260916-01/03 wrote: ``RebalanceEvent.date`` is already a
    string in this kernel, so it is passed through rather than reformatted."""
    return [
        {
            "date": event.date,
            "universe_size": int(event.universe_size),
            "selected": {str(symbol): float(weight) for symbol, weight in event.selected.items()},
            "portfolio_beta": event.portfolio_beta,
        }
        for event in schedule
    ]


# --------------------------------------------------------------------------
# stage: export
# --------------------------------------------------------------------------


def stage_export(*, force: bool) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not force and PICKS_PATH.exists() and SCHEDULE_PATH.exists():
        _log(f"{PICKS_PATH.name} / {SCHEDULE_PATH.name} already present -- reusing (checkpoint)")
        return 0
    common = m_grid._load_common_data(years=DATA_YEARS, trend_gate_required=False)
    _log(f"loading feature panel on {len(common.weekly_dates)} weekly rebalance dates ...")
    panel = load_feature_panel(
        ["momentum_252_21", "vol_63"],
        ["label_rank_5"],
        dates=common.weekly_dates,
        include_prices=False,
    )
    ratio = panel["momentum_252_21"] / panel["vol_63"]
    panel[SCORE_COLUMN] = ratio.replace([np.inf, -np.inf], np.nan)
    collector = PickCollector(feature_columns=(SCORE_COLUMN,))
    trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
    _log(f"building the weight schedule for test years {TEST_YEARS} ...")
    schedule = build_weight_schedule(
        panel=panel,
        universe_panel=common.universe_panel,
        strategy_factory=lambda: MomentumFactorStrategy(factor_column=SCORE_COLUMN),
        feature_columns=[SCORE_COLUMN],
        label_column="label_rank_5",
        label_horizon_days=5,
        test_years=TEST_YEARS,
        top_k=TOP_K,
        hedge="none",
        trading_calendar=trading_calendar,
        train_window_months=TRAIN_WINDOW_MONTHS,
        refit_frequency="quarterly",
        universe_top_n=UNIVERSE_TOP_N,
        trend_gate_series=None,
        trend_gate_cash_symbol=CASH_SYMBOL,
        pick_observer=collector,
    )
    picks = collector.to_frame()
    _write_parquet(PICKS_PATH, picks)
    _write_json(SCHEDULE_PATH, _events_to_json(schedule))
    _log(
        f"wrote {PICKS_PATH.name}: {len(picks):,} rows, "
        f"{picks['rebalance_date'].nunique()} rebalance dates, "
        f"{picks['rebalance_date'].min().date()}..{picks['rebalance_date'].max().date()}"
    )
    empty = [event.date for event in schedule if not event.selected]
    _log(f"{len(empty)} rebalance weeks produced no book at all: {empty}")
    return 0


# --------------------------------------------------------------------------
# pre-check helpers
# --------------------------------------------------------------------------


def _weekly_dates(years: tuple[int, ...]) -> list[pd.Timestamp]:
    dates: list[pd.Timestamp] = []
    for year in years:
        path = LABELS_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        trade_dates = pd.read_parquet(path, columns=["trade_date"])["trade_date"]
        dates.extend(weekly_rebalance_dates(sorted(pd.to_datetime(trade_dates.unique()))))
    return sorted(set(dates))


def build_pool_panel(*, force: bool) -> pd.DataFrame:
    """One row per (weekly date, top-500 pool symbol) with the momentum score,
    the point-in-time short-interest columns and the forward-excess labels.

    This is the pre-check's reference table: the book is a subset of it, so
    "book share vs pool share" is measured on one join rather than two.
    """
    if POOL_PANEL_PATH.exists() and not force:
        _log(f"{POOL_PANEL_PATH.name}: reusing (checkpoint)")
        return pd.read_parquet(POOL_PANEL_PATH)
    dates = _weekly_dates(SCREEN_YEARS)
    _log(f"pool panel: {len(dates)} weekly dates {dates[0].date()}..{dates[-1].date()}")
    universe_panel = m_grid.universe_mod.load_universe_panel(UNIVERSE_ROOT)
    membership = pd.DataFrame(
        [
            (date, symbol)
            for date in dates
            for symbol in universe_as_of_calendar_month(
                universe_panel, date, top_n=CROSS_SECTIONAL_POOL_TOP_N
            )
        ],
        columns=["trade_date", "symbol"],
    )
    panel = load_feature_panel(
        ["momentum_252_21", "vol_63"],
        list(LABEL_COLUMNS),
        dates=pd.DatetimeIndex(dates),
        include_prices=False,
    )
    ratio = panel["momentum_252_21"] / panel["vol_63"]
    panel[SCORE_COLUMN] = ratio.replace([np.inf, -np.inf], np.nan)
    panel = panel[["symbol", "trade_date", SCORE_COLUMN, *LABEL_COLUMNS]]
    panel["symbol"] = panel["symbol"].astype(str)
    merged = membership.merge(panel, on=["trade_date", "symbol"], how="inner")
    frames = []
    for year in SCREEN_YEARS:
        path = SHORT_INTEREST_ROOT / f"{year}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(
            path,
            columns=[
                "symbol",
                "trade_date",
                "days_to_cover",
                "dtc_cross_sectional_pct",
                "staleness_days",
                "si_record_present",
            ],
        )
        frames.append(frame.loc[frame["trade_date"].isin(set(dates))])
    if not frames:
        raise SystemExit(f"no short-interest features under {SHORT_INTEREST_ROOT}")
    short_interest = pd.concat(frames, ignore_index=True)
    short_interest["symbol"] = short_interest["symbol"].astype(str)
    merged = merged.merge(short_interest, on=["symbol", "trade_date"], how="left")
    merged["si_record_present"] = merged["si_record_present"].fillna(0.0)
    _write_parquet(POOL_PANEL_PATH, merged)
    _log(f"wrote {POOL_PANEL_PATH.name}: {len(merged):,} pool stock-weeks")
    return merged


def build_broad_panel(*, force: bool) -> pd.DataFrame:
    """One row per (weekly date, broad-universe symbol) with the point-in-time
    short-interest record, its within-day percentile **inside the broad
    universe**, and the forward-excess labels.

    The broad universe is every symbol in ``data/features/daily`` whose own
    ``close >= $2`` and ``dollar_adv_63 >= $1M`` on that date -- deliberately
    not the top-500 ADV pool, because the question this table answers is
    whether short interest is an independent cross-sectional input rather than
    a filter on one 50-name momentum book. Building it from the raw parsed
    archive (not from ``data/features/short_interest/``, which is top-1000 by
    construction) is what makes that possible.
    """
    if BROAD_PANEL_PATH.exists() and not force:
        _log(f"{BROAD_PANEL_PATH.name}: reusing (checkpoint)")
        return pd.read_parquet(BROAD_PANEL_PATH)
    dates = _weekly_dates(SCREEN_YEARS)
    date_set = set(dates)
    sessions = pd.DatetimeIndex(
        sorted(
            pd.concat(
                [
                    pd.read_parquet(LABELS_ROOT / f"{year}.parquet", columns=["trade_date"])[
                        "trade_date"
                    ]
                    for year in SCREEN_YEARS
                    if (LABELS_ROOT / f"{year}.parquet").exists()
                ]
            ).unique()
        )
    )
    records = load_records(symbols=None, sessions=sessions, shift_days=0, seed=0)
    _log(f"broad panel: {len(records):,} visible snapshots over the whole archive")
    session_position = {timestamp: index for index, timestamp in enumerate(sessions)}

    frames: list[pd.DataFrame] = []
    for year in SCREEN_YEARS:
        daily_path = DAILY_ROOT / f"{year}.parquet"
        label_path = LABELS_ROOT / f"{year}.parquet"
        if not daily_path.exists() or not label_path.exists():
            continue
        daily = pd.read_parquet(
            daily_path, columns=["symbol", "trade_date", "close", "dollar_adv_63"]
        )
        daily = daily.loc[daily["trade_date"].isin(date_set)]
        daily = daily.loc[
            (daily["close"] >= BROAD_MIN_CLOSE) & (daily["dollar_adv_63"] >= BROAD_MIN_DOLLAR_ADV)
        ]
        if daily.empty:
            continue
        labels = pd.read_parquet(label_path, columns=["symbol", "trade_date", *LABEL_COLUMNS])
        grid = daily.merge(labels, on=["symbol", "trade_date"], how="left")
        grid["symbol"] = grid["symbol"].astype(str)
        grid["session_idx"] = grid["trade_date"].map(session_position).astype("Int64")
        grid = grid.loc[grid["session_idx"].notna()].copy()
        grid["session_idx"] = grid["session_idx"].astype(np.int64)
        merged = pd.merge_asof(
            grid.sort_values("session_idx", ignore_index=True),
            records[
                ["symbol", "visible_idx", "days_to_cover", "short_interest_shares"]
            ].sort_values("visible_idx", ignore_index=True),
            left_on="session_idx",
            right_on="visible_idx",
            by="symbol",
            direction="backward",
        )
        merged["si_record_present"] = merged["visible_idx"].notna().astype("float64")
        merged["staleness_days"] = (merged["session_idx"] - merged["visible_idx"]).astype("float64")
        merged["dtc_broad_pct"] = merged.groupby("trade_date")["days_to_cover"].rank(pct=True)
        adv_shares = merged["dollar_adv_63"] / merged["close"].where(merged["close"] > 0)
        merged["short_interest_ratio"] = merged["short_interest_shares"] / adv_shares.where(
            adv_shares > 0
        )
        frames.append(
            merged[
                [
                    "symbol",
                    "trade_date",
                    "close",
                    "dollar_adv_63",
                    "days_to_cover",
                    "dtc_broad_pct",
                    "short_interest_ratio",
                    "staleness_days",
                    "si_record_present",
                    *LABEL_COLUMNS,
                ]
            ]
        )
        _log(f"{year}: {len(merged):,} broad-universe stock-weeks")
    broad = pd.concat(frames, ignore_index=True)
    _write_parquet(BROAD_PANEL_PATH, broad)
    _log(f"wrote {BROAD_PANEL_PATH.name}: {len(broad):,} broad stock-weeks")
    return broad


def _hit_share(frame: pd.DataFrame, column: str, threshold: float) -> float:
    values = pd.to_numeric(frame[column], errors="coerce")
    return float((values >= threshold).fillna(False).mean())


def _per_date_spearman(frame: pd.DataFrame, left: str, right: str) -> dict[str, float]:
    """Mean per-date Spearman correlation plus its t-statistic."""
    values: list[float] = []
    for _, group in frame.groupby("trade_date", sort=True):
        valid = group[left].notna() & group[right].notna()
        if int(valid.sum()) < 50:
            continue
        correlation = group.loc[valid, left].corr(group.loc[valid, right], method="spearman")
        if pd.notna(correlation):
            values.append(float(correlation))
    if len(values) < 2:
        return {"mean": float("nan"), "t": float("nan"), "dates": len(values)}
    series = pd.Series(values)
    mean = float(series.mean())
    std = float(series.std(ddof=1))
    t = mean / std * np.sqrt(len(series)) if std > 0 else float("nan")
    return {"mean": mean, "t": float(t), "dates": len(values)}


def _quintile_table(frame: pd.DataFrame, rank_column: str) -> list[dict[str, Any]]:
    """Forward excess by within-date days-to-cover quintile."""
    usable = frame.loc[frame[rank_column].notna()].copy()
    if usable.empty:
        return []
    usable["bucket"] = np.clip(
        np.ceil(usable[rank_column] * BROAD_QUINTILES).astype(int), 1, BROAD_QUINTILES
    )
    rows: list[dict[str, Any]] = []
    for bucket, group in usable.groupby("bucket", sort=True):
        row: dict[str, Any] = {"quintile": int(bucket), "rows": int(len(group))}
        for label in LABEL_COLUMNS:
            values = group[label].dropna()
            row[f"{label}_mean"] = float(values.mean()) if len(values) else float("nan")
            row[f"{label}_n"] = int(len(values))
        row["days_to_cover_mean"] = float(group["days_to_cover"].mean())
        rows.append(row)
    return rows


def _top_minus_bottom(frame: pd.DataFrame, rank_column: str, label: str) -> dict[str, float]:
    """Per-date (top quintile mean - bottom quintile mean) with a t-statistic.

    Computed per date and then aggregated, not pooled: pooling across dates
    would let a handful of extreme weeks (2020-03, 2021-01) dominate, and the
    2021-01 meme squeeze is exactly the episode this card must not be decided
    by.
    """
    spreads: list[float] = []
    for _, group in frame.groupby("trade_date", sort=True):
        usable = group.loc[group[rank_column].notna() & group[label].notna()]
        if len(usable) < 100:
            continue
        top = usable.loc[usable[rank_column] > 1.0 - 1.0 / BROAD_QUINTILES, label]
        bottom = usable.loc[usable[rank_column] <= 1.0 / BROAD_QUINTILES, label]
        if len(top) < 10 or len(bottom) < 10:
            continue
        spreads.append(float(top.mean() - bottom.mean()))
    if len(spreads) < 2:
        return {"mean": float("nan"), "t": float("nan"), "dates": len(spreads)}
    series = pd.Series(spreads)
    mean = float(series.mean())
    std = float(series.std(ddof=1))
    t = mean / std * np.sqrt(len(series)) if std > 0 else float("nan")
    p = (
        float(2.0 * scipy_stats.t.sf(abs(t), df=len(series) - 1))
        if np.isfinite(t)
        else float("nan")
    )
    return {
        "mean": mean,
        "t": float(t),
        "p_value": p,
        "dates": len(spreads),
        "share_positive": float((series > 0).mean()),
    }


def _ratio_decomposition_controls(broad: pd.DataFrame) -> dict[str, Any]:
    """Is the short-interest **ratio** spread short interest, or is it 1/ADV?

    ``short_interest_ratio = short_interest_shares / (dollar_adv_63 / close)``,
    so a spread on it has two candidate sources and they must be separated
    before anything is built on it:

    ``inverse_liquidity``
        Rank ``-adv_shares_63`` (i.e. pure illiquidity) and run the identical
        top-minus-bottom test. If this alone reproduces the spread, the
        "signal" is a liquidity premium and the numerator is decoration.
    ``symbol_shuffle``
        Permute ``short_interest_shares`` **across symbols within each
        rebalance date**, keeping every symbol's own ADV denominator, then
        rebuild the ratio and rank it. This is the analogue of the control
        that decided H-20260916-01: it preserves the calendar, the
        cross-sectional distribution and the denominator, and destroys only
        *which company* each short position belongs to. Reported over
        :data:`SHUFFLE_SEEDS` as a distribution, never a single draw.

    The publication-shift placebo cannot answer this question and the report
    says so: the underlying series changes twice a month with a weekly rank
    autocorrelation of 0.97, so moving visibility by a few sessions swaps in a
    nearly identical snapshot.
    """
    frame = broad.copy()
    adv_shares = frame["dollar_adv_63"] / frame["close"].where(frame["close"] > 0)
    frame["adv_shares_63"] = adv_shares
    frame["short_interest_shares"] = frame["short_interest_ratio"] * adv_shares
    frame["inverse_liquidity_pct"] = frame.groupby("trade_date")["adv_shares_63"].rank(
        pct=True, ascending=False
    )
    out: dict[str, Any] = {
        "inverse_liquidity": {
            label: _top_minus_bottom(frame, "inverse_liquidity_pct", label)
            for label in LABEL_COLUMNS
        },
        "symbol_shuffle": {},
    }
    groups = frame.groupby("trade_date").indices
    shares = frame["short_interest_shares"].to_numpy(copy=True)
    per_seed: dict[str, list[dict[str, float]]] = {label: [] for label in LABEL_COLUMNS}
    for seed in SHUFFLE_SEEDS:
        rng = np.random.default_rng(seed)
        shuffled = shares.copy()
        for index in groups.values():
            shuffled[index] = rng.permutation(shuffled[index])
        trial = frame.assign(shuffled_ratio=shuffled / frame["adv_shares_63"])
        trial["shuffled_pct"] = trial.groupby("trade_date")["shuffled_ratio"].rank(pct=True)
        for label in LABEL_COLUMNS:
            per_seed[label].append(_top_minus_bottom(trial, "shuffled_pct", label))
    for label, results in per_seed.items():
        means = [row["mean"] for row in results if np.isfinite(row["mean"])]
        ts = [row["t"] for row in results if np.isfinite(row.get("t", float("nan")))]
        out["symbol_shuffle"][label] = {
            "seeds": len(results),
            "mean_of_means": float(np.mean(means)) if means else float("nan"),
            "min_mean": float(np.min(means)) if means else float("nan"),
            "max_mean": float(np.max(means)) if means else float("nan"),
            "mean_t": float(np.mean(ts)) if ts else float("nan"),
            "per_seed": results,
        }
    return out


def _by_liquidity_tercile(broad: pd.DataFrame) -> list[dict[str, Any]]:
    """Top-minus-bottom short-interest-ratio spread **inside each within-date
    dollar-ADV tercile**.

    The obvious alternative explanation for a broad-universe short-interest
    spread is that it is a size/liquidity premium wearing a short-interest
    costume: small illiquid names carry more short interest per unit of volume
    *and* have different forward returns for reasons of their own. Re-ranking
    inside each liquidity tercile removes the cross-tercile part of the sort,
    so a spread that survives in all three terciles is not a size effect --
    and one that only survives in the smallest tercile is worth knowing about
    before anyone builds on it.
    """
    frame = broad.copy()
    frame["adv_tercile"] = frame.groupby("trade_date")["dollar_adv_63"].transform(
        lambda values: np.clip(np.ceil(values.rank(pct=True) * 3).astype(int), 1, 3)
    )
    frame["ratio_pct_within"] = frame.groupby(["trade_date", "adv_tercile"])[
        "short_interest_ratio"
    ].rank(pct=True)
    rows: list[dict[str, Any]] = []
    for tercile, group in frame.groupby("adv_tercile", sort=True):
        row: dict[str, Any] = {
            "adv_tercile": int(tercile),
            "label": "1 = 最不流动"
            if tercile == 1
            else ("2 = 中" if tercile == 2 else "3 = 最流动"),
            "stock_weeks": int(len(group)),
            "median_dollar_adv": float(group["dollar_adv_63"].median()),
        }
        for label in LABEL_COLUMNS:
            row[label] = _top_minus_bottom(group, "ratio_pct_within", label)
        rows.append(row)
    return rows


def _by_year_spread(broad: pd.DataFrame, rank_column: str) -> list[dict[str, Any]]:
    """The same top-minus-bottom spread year by year, so the report can say
    whether one episode (2021-01's meme squeeze) carries it."""
    rows: list[dict[str, Any]] = []
    for year, group in broad.groupby(broad["trade_date"].dt.year, sort=True):
        row: dict[str, Any] = {"year": int(year), "stock_weeks": int(len(group))}
        for label in LABEL_COLUMNS:
            row[label] = _top_minus_bottom(group, rank_column, label)
        rows.append(row)
    return rows


def stage_precheck(*, force: bool) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    picks = pd.read_parquet(PICKS_PATH)
    picks["rebalance_date"] = pd.to_datetime(picks["rebalance_date"])
    book = picks.loc[(picks["weight"] > 0.0) & (picks["symbol"] != CASH_SYMBOL)].copy()
    book["symbol"] = book["symbol"].astype(str)
    book = book.rename(columns={"rebalance_date": "trade_date"})

    pool = build_pool_panel(force=force)
    pool["trade_date"] = pd.to_datetime(pool["trade_date"])
    pool["symbol"] = pool["symbol"].astype(str)
    book_joined = book.merge(
        pool[
            [
                "symbol",
                "trade_date",
                "days_to_cover",
                "dtc_cross_sectional_pct",
                "staleness_days",
                "si_record_present",
            ]
        ],
        on=["symbol", "trade_date"],
        how="left",
    )
    book_joined["si_record_present"] = book_joined["si_record_present"].fillna(0.0)
    pool_in_book_window = pool.loc[
        (pool["trade_date"] >= book["trade_date"].min())
        & (pool["trade_date"] <= book["trade_date"].max())
    ]

    coverage = {
        "book_stock_weeks": int(len(book_joined)),
        "book_with_visible_record": float(book_joined["si_record_present"].mean()),
        "pool_stock_weeks": int(len(pool_in_book_window)),
        "pool_with_visible_record": float(pool_in_book_window["si_record_present"].mean()),
        "book_median_staleness_sessions": float(book_joined["staleness_days"].median()),
        "book_dates": int(book_joined["trade_date"].nunique()),
        "window": [
            book_joined["trade_date"].min().date().isoformat(),
            book_joined["trade_date"].max().date().isoformat(),
        ],
    }

    thresholds: dict[str, Any] = {}
    for threshold in PRECHECK_THRESHOLDS:
        book_share = _hit_share(book_joined, "dtc_cross_sectional_pct", threshold)
        pool_share = _hit_share(pool_in_book_window, "dtc_cross_sectional_pct", threshold)
        thresholds[f"{threshold:.2f}"] = {
            "threshold": threshold,
            "book_hit_share": book_share,
            "pool_hit_share": pool_share,
            "book_over_pool_ratio": book_share / pool_share if pool_share else None,
            "book_names_per_week_mean": float(
                book_joined.assign(
                    hit=(book_joined["dtc_cross_sectional_pct"] >= threshold).fillna(False)
                )
                .groupby("trade_date")["hit"]
                .sum()
                .mean()
            ),
            "meets_minimum": bool(book_share >= MIN_BOOK_HIT_SHARE),
        }

    per_year: list[dict[str, Any]] = []
    for year, group in book_joined.groupby(book_joined["trade_date"].dt.year):
        pool_year = pool_in_book_window.loc[pool_in_book_window["trade_date"].dt.year == year]
        row: dict[str, Any] = {
            "year": int(year),
            "book_stock_weeks": int(len(group)),
            "book_coverage": float(group["si_record_present"].mean()),
            "pool_coverage": float(pool_year["si_record_present"].mean()),
        }
        for threshold in PRECHECK_THRESHOLDS:
            key = f"hit_{int(threshold * 100)}"
            row[f"book_{key}"] = _hit_share(group, "dtc_cross_sectional_pct", threshold)
            row[f"pool_{key}"] = _hit_share(pool_year, "dtc_cross_sectional_pct", threshold)
        row["book_over_pool_ratio_80"] = (
            row["book_hit_80"] / row["pool_hit_80"] if row["pool_hit_80"] else None
        )
        per_year.append(row)

    confound = {
        "dtc_pct_vs_momentum_score_in_pool": _per_date_spearman(
            pool_in_book_window, "dtc_cross_sectional_pct", SCORE_COLUMN
        ),
        "days_to_cover_vs_momentum_score_in_pool": _per_date_spearman(
            pool_in_book_window, "days_to_cover", SCORE_COLUMN
        ),
    }

    broad = build_broad_panel(force=force)
    broad["trade_date"] = pd.to_datetime(broad["trade_date"])
    broad_window = broad.loc[
        (broad["trade_date"] >= book["trade_date"].min())
        & (broad["trade_date"] <= book["trade_date"].max())
    ]
    # The ADV-normalized ratio is a second, differently-normalized sort of the
    # same numerator; ranking it once here keeps the quintile table and its
    # top-minus-bottom test on exactly the same ranks.
    broad_with_ratio_rank = broad_window.assign(
        ratio_pct=broad_window.groupby("trade_date")["short_interest_ratio"].rank(pct=True)
    )
    broad_block = {
        "definition": (
            f"close >= ${BROAD_MIN_CLOSE:.0f} and dollar_adv_63 >= "
            f"${BROAD_MIN_DOLLAR_ADV / 1e6:.0f}M on the rebalance date"
        ),
        "stock_weeks": int(len(broad_window)),
        "symbols": int(broad_window["symbol"].nunique()),
        "names_per_week_mean": float(broad_window.groupby("trade_date").size().mean()),
        "coverage_with_visible_record": float(broad_window["si_record_present"].mean()),
        "median_staleness_sessions": float(broad_window["staleness_days"].median()),
        "quintiles": _quintile_table(broad_window, "dtc_broad_pct"),
        "top_minus_bottom": {
            label: _top_minus_bottom(broad_window, "dtc_broad_pct", label)
            for label in LABEL_COLUMNS
        },
        "quintiles_by_ratio": _quintile_table(broad_with_ratio_rank, "ratio_pct"),
        "top_minus_bottom_by_ratio": {
            label: _top_minus_bottom(broad_with_ratio_rank, "ratio_pct", label)
            for label in LABEL_COLUMNS
        },
        "hit_shares": {
            f"{threshold:.2f}": _hit_share(broad_window, "dtc_broad_pct", threshold)
            for threshold in PRECHECK_THRESHOLDS
        },
        "per_year_coverage": {
            str(int(year)): float(group["si_record_present"].mean())
            for year, group in broad_window.groupby(broad_window["trade_date"].dt.year)
        },
        "by_liquidity_tercile": _by_liquidity_tercile(broad_window),
        "by_year_ratio_spread": _by_year_spread(broad_with_ratio_rank, "ratio_pct"),
        "ratio_decomposition": _ratio_decomposition_controls(broad_window),
    }

    # The avoid condition's own forward excess inside the book: if dropping
    # these names is supposed to help, the names being dropped should have
    # worse forward excess than the ones kept. Compared against >= 5 same-size
    # random draws so "the dropped names were bad" is not just "50 names are
    # noisy".
    book_labels = book.merge(
        pool[["symbol", "trade_date", *LABEL_COLUMNS]], on=["symbol", "trade_date"], how="left"
    ).merge(
        book_joined[["symbol", "trade_date", "dtc_cross_sectional_pct"]],
        on=["symbol", "trade_date"],
        how="left",
    )
    dropped_vs_random = _dropped_vs_random(book_labels, AVOID_PERCENTILE_THRESHOLD)

    verdict = {
        "threshold": AVOID_PERCENTILE_THRESHOLD,
        "book_hit_share": thresholds[f"{AVOID_PERCENTILE_THRESHOLD:.2f}"]["book_hit_share"],
        "minimum_required": MIN_BOOK_HIT_SHARE,
        "proceed_to_twin_cells": bool(
            thresholds[f"{AVOID_PERCENTILE_THRESHOLD:.2f}"]["book_hit_share"] >= MIN_BOOK_HIT_SHARE
        ),
    }

    payload = {
        "hypothesis": "H-20260916-07",
        "step": "precheck",
        "card": ("reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md"),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "primary_cell": PRIMARY_CELL,
        "book": {"top_k": TOP_K, "pool_top_n": UNIVERSE_TOP_N, "weighting": "equal"},
        "coverage": coverage,
        "thresholds": thresholds,
        "per_year": per_year,
        "confound": confound,
        "broad_universe": broad_block,
        "dropped_vs_random": dropped_vs_random,
        "verdict": verdict,
    }
    _write_json(PRECHECK_JSON, payload)
    PRECHECK_MD.write_text(_render_precheck(payload), encoding="utf-8")
    _log(f"wrote {PRECHECK_JSON.name} and {PRECHECK_MD.name}")
    _log(
        f"VERDICT: book hit share at {AVOID_PERCENTILE_THRESHOLD:.0%} = "
        f"{verdict['book_hit_share']:.2%} "
        f"({'>=' if verdict['proceed_to_twin_cells'] else '<'} "
        f"{MIN_BOOK_HIT_SHARE:.0%}) -> "
        + ("proceed to twin cells" if verdict["proceed_to_twin_cells"] else "STOP at the pre-check")
    )
    return 0


def _dropped_vs_random(book_labels: pd.DataFrame, threshold: float) -> dict[str, Any]:
    """Forward excess of the avoid-list names vs same-size random draws."""
    frame = book_labels.copy()
    frame["hit"] = (frame["dtc_cross_sectional_pct"] >= threshold).fillna(False)
    out: dict[str, Any] = {"threshold": threshold, "labels": {}}
    for label in LABEL_COLUMNS:
        usable = frame.loc[frame[label].notna()]
        dropped = usable.loc[usable["hit"], label]
        kept = usable.loc[~usable["hit"], label]
        real_gap = (
            float(dropped.mean() - kept.mean()) if len(dropped) and len(kept) else float("nan")
        )
        random_gaps: list[float] = []
        for seed in SHUFFLE_SEEDS:
            rng = np.random.default_rng(seed)
            flags = np.zeros(len(usable), dtype=bool)
            for _, index in usable.groupby("trade_date").indices.items():
                count = int(usable["hit"].to_numpy()[index].sum())
                if count == 0:
                    continue
                flags[rng.choice(index, size=count, replace=False)] = True
            values = usable[label].to_numpy()
            if flags.any() and (~flags).any():
                random_gaps.append(float(values[flags].mean() - values[~flags].mean()))
        out["labels"][label] = {
            "dropped_rows": int(len(dropped)),
            "kept_rows": int(len(kept)),
            "dropped_mean": float(dropped.mean()) if len(dropped) else float("nan"),
            "kept_mean": float(kept.mean()) if len(kept) else float("nan"),
            "real_gap": real_gap,
            "random_gap_mean": float(np.mean(random_gaps)) if random_gaps else float("nan"),
            "random_gap_min": float(np.min(random_gaps)) if random_gaps else float("nan"),
            "random_gap_max": float(np.max(random_gaps)) if random_gaps else float("nan"),
            "random_seeds": len(random_gaps),
        }
    return out


def _pct(value: float | None, digits: int = 1) -> str:
    if value is None or not np.isfinite(value):
        return "N/A"
    return f"{value * 100:.{digits}f}%"


def _num(value: float | None, spec: str = "+.4f") -> str:
    if value is None or not np.isfinite(value):
        return "N/A"
    return format(value, spec)


def _render_precheck(payload: dict[str, Any]) -> str:
    coverage = payload["coverage"]
    lines: list[str] = []
    lines.append("# H-20260916-07 前置检查：FINRA 空头兴趣回避清单")
    lines.append("")
    lines.append(
        f"生成时间 {payload['generated_at']}｜书 = `{payload['primary_cell']}`"
        f"（点时 top-{payload['book']['pool_top_n']} 池，等权 top-{payload['book']['top_k']}）｜"
        f"窗口 {coverage['window'][0]} → {coverage['window'][1]}"
        f"（{coverage['book_dates']} 个调仓周）"
    )
    lines.append("")
    lines.append("## 0. 结论先行")
    verdict = payload["verdict"]
    lines.append("")
    lines.append(
        f"- avoid 条件（days-to-cover 处于 top-500 池最高 "
        f"{(1 - verdict['threshold']) * 100:.0f}%）命中 "
        f"**{_pct(verdict['book_hit_share'])}** 的组合持仓周，门槛是 "
        f"{_pct(verdict['minimum_required'], 0)} → "
        f"**{'继续做孪生单元' if verdict['proceed_to_twin_cells'] else '在前置检查处停止'}**。"
    )
    lines.append(
        f"- 覆盖率：组合持仓周 **{_pct(coverage['book_with_visible_record'])}** "
        "有可见的空头余额记录，"
        f"池子 {_pct(coverage['pool_with_visible_record'])}，"
        f"中位陈旧度 {coverage['book_median_staleness_sessions']:.0f} 个交易日。"
        "（对照 Form 4 的 1.9%：这一层**看得见**这本书。）"
    )
    confound = payload["confound"]["dtc_pct_vs_momentum_score_in_pool"]
    lines.append(
        f"- 卡上的主要混淆（高空头 ≈ 高动量）：池内 days-to-cover 百分位与动量分数的"
        f"逐周 Spearman 均值 **{_num(confound['mean'], '+.4f')}**"
        f"（t = {_num(confound['t'], '+.2f')}，{confound['dates']} 周）。"
    )
    lines.append("")
    lines.append("## 1. 命中率交叉表（组合 vs 池子，按阈值）")
    lines.append("")
    lines.append(
        "| 阈值（DTC 百分位 ≥） | 组合命中率 | 池子命中率 | 组合/池子 | "
        "组合每周平均剔除只数 | ≥ 10% |"
    )
    lines.append("|---|---:|---:|---:|---:|:-:|")
    for key in sorted(payload["thresholds"], reverse=True):
        row = payload["thresholds"][key]
        lines.append(
            f"| {row['threshold']:.2f}（最高 {(1 - row['threshold']) * 100:.0f}%） | "
            f"{_pct(row['book_hit_share'])} | {_pct(row['pool_hit_share'])} | "
            f"{_num(row['book_over_pool_ratio'], '.2f')} | "
            f"{row['book_names_per_week_mean']:.1f} | "
            f"{'是' if row['meets_minimum'] else '否'} |"
        )
    lines.append("")
    lines.append(
        "池子命中率按定义接近阈值的补数（百分位是在池内算的）；"
        "**组合/池子比值**才是信息量所在：> 1 表示动量赢家系统性地更拥挤（空头更多），"
        "< 1 表示动量赢家反而是空头少的名字。"
    )
    lines.append("")
    lines.append("## 2. 逐年（覆盖率与 0.80 阈值命中率）")
    lines.append("")
    lines.append(
        "| 年 | 组合持仓周 | 组合覆盖率 | 池子覆盖率 | 组合命中 ≥0.80 | "
        "池子命中 ≥0.80 | 组合/池子 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in payload["per_year"]:
        lines.append(
            f"| {row['year']} | {row['book_stock_weeks']:,} | "
            f"{_pct(row['book_coverage'])} | {_pct(row['pool_coverage'])} | "
            f"{_pct(row['book_hit_80'])} | {_pct(row['pool_hit_80'])} | "
            f"{_num(row['book_over_pool_ratio_80'], '.2f')} |"
        )
    lines.append("")
    lines.append("## 3. 被剔除的名字真的更差吗（对同尺寸随机剔除）")
    lines.append("")
    dropped = payload["dropped_vs_random"]
    lines.append(
        "| 标签 | 被剔除均值 | 保留均值 | 真实差 | 随机同尺寸差（均值） | 随机最小 | 随机最大 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, row in dropped["labels"].items():
        lines.append(
            f"| `{label}` | {_num(row['dropped_mean'])} | {_num(row['kept_mean'])} | "
            f"**{_num(row['real_gap'])}** | {_num(row['random_gap_mean'])} | "
            f"{_num(row['random_gap_min'])} | {_num(row['random_gap_max'])} |"
        )
    lines.append("")
    lines.append(
        "读法：真实差为**负**才支持「剔除高空头能改善」。随机同尺寸差应该在 0 附近；"
        "如果真实差和随机差分不开，说明差异来自「组合里 50 只票本来就散」，不是空头信息。"
    )
    lines.append("")
    broad = payload["broad_universe"]
    lines.append("## 4. 宽口径流动性股票池：空头兴趣能不能当独立输入")
    lines.append("")
    lines.append(
        f"定义：{broad['definition']}。"
        f"{broad['stock_weeks']:,} 个股票周，{broad['symbols']:,} 只票，"
        f"每周平均 {broad['names_per_week_mean']:.0f} 只；"
        f"有可见记录 {_pct(broad['coverage_with_visible_record'])}，"
        f"中位陈旧度 {broad['median_staleness_sessions']:.0f} 个交易日。"
    )
    lines.append("")
    lines.append(
        "| DTC 五分位（1 = 最低） | 股票周 | 平均 days-to-cover | 5 日超额均值 | 21 日超额均值 |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    for row in broad["quintiles"]:
        lines.append(
            f"| {row['quintile']} | {row['rows']:,} | {row['days_to_cover_mean']:.2f} | "
            f"{_num(row['label_excess_5_mean'])} | {_num(row['label_excess_21_mean'])} |"
        )
    lines.append("")
    lines.append("最高五分位减最低五分位（逐周算差再汇总，不是池化）：")
    lines.append("")
    lines.append("| 标签 | 平均差 | t | p | 周数 | 差为正的周占比 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for label, row in broad["top_minus_bottom"].items():
        lines.append(
            f"| `{label}` | {_num(row['mean'])} | {_num(row.get('t'), '+.2f')} | "
            f"{_num(row.get('p_value'), '.4f')} | {row['dates']} | "
            f"{_pct(row.get('share_positive'))} |"
        )
    lines.append("")
    lines.append(
        "文献里稳定的是空方腿（高空头兴趣 → 未来收益更低），所以**平均差为负**才支持"
        "「拥挤空头反转 / 逼空」这一族的前提。为正则说明在这个池子和这个持有期上，"
        "高空头兴趣的名字**跑得更好**，那么「回避清单」的方向本身就是错的。"
    )
    lines.append("")
    lines.append("按 `short_interest_ratio`（空头股数 / 自有 63 日日均股数）分位的同一张表：")
    lines.append("")
    lines.append("| 五分位 | 股票周 | 5 日超额均值 | 21 日超额均值 |")
    lines.append("|---|---:|---:|---:|")
    for row in broad["quintiles_by_ratio"]:
        lines.append(
            f"| {row['quintile']} | {row['rows']:,} | "
            f"{_num(row['label_excess_5_mean'])} | {_num(row['label_excess_21_mean'])} |"
        )
    lines.append("")
    lines.append("同样口径的最高减最低：")
    lines.append("")
    lines.append("| 标签 | 平均差 | t | p | 周数 | 差为正的周占比 |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for label, row in broad.get("top_minus_bottom_by_ratio", {}).items():
        lines.append(
            f"| `{label}` | {_num(row['mean'])} | {_num(row.get('t'), '+.2f')} | "
            f"{_num(row.get('p_value'), '.4f')} | {row['dates']} | "
            f"{_pct(row.get('share_positive'))} |"
        )
    lines.append("")
    decomposition = broad.get("ratio_decomposition")
    if decomposition:
        lines.append("### 4.0 这个比值到底是「空头」还是「1 ÷ 成交量」（两个拆解对照）")
        lines.append("")
        lines.append("| 对照 | 5 日差 (t) | 21 日差 (t) | 说明 |")
        lines.append("|---|---:|---:|---|")
        inverse = decomposition["inverse_liquidity"]
        lines.append(
            f"| 只用 −成交股数排名（纯不流动） | "
            f"{_num(inverse['label_excess_5']['mean'])} "
            f"({_num(inverse['label_excess_5'].get('t'), '+.2f')}) | "
            f"{_num(inverse['label_excess_21']['mean'])} "
            f"({_num(inverse['label_excess_21'].get('t'), '+.2f')}) | "
            "若这一行就复现了真实差，比值里值钱的是分母不是分子 |"
        )
        shuffle = decomposition["symbol_shuffle"]
        lines.append(
            f"| 同日跨股票打乱空头股数（{shuffle['label_excess_5']['seeds']} 个种子均值） | "
            f"{_num(shuffle['label_excess_5']['mean_of_means'])} "
            f"({_num(shuffle['label_excess_5'].get('mean_t'), '+.2f')}) | "
            f"{_num(shuffle['label_excess_21']['mean_of_means'])} "
            f"({_num(shuffle['label_excess_21'].get('mean_t'), '+.2f')}) | "
            "保留日历、分布和每只票自己的分母，只打乱「这笔空头属于谁」 |"
        )
        lines.append("")
        lines.append(
            "打乱种子的区间："
            f"5 日 [{_num(shuffle['label_excess_5']['min_mean'])}, "
            f"{_num(shuffle['label_excess_5']['max_mean'])}]；"
            f"21 日 [{_num(shuffle['label_excess_21']['min_mean'])}, "
            f"{_num(shuffle['label_excess_21']['max_mean'])}]。"
        )
        lines.append("")
        lines.append(
            "**为什么必须加这两行**：发布日平移占位在这个数据层上几乎没有破坏力——"
            "底层一个月只更新两次、周度秩自相关 0.97，把可见性挪几天基本还是同一份快照，"
            "所以占位筛选器复现了真实筛选器约 100%（见第 3.1 节）。"
            "能回答「是不是空头信息」的是上面这两个对照，不是那个占位。"
        )
        lines.append("")
    lines.append("### 4.1 是不是只是「小票流动性溢价」（在每日成交额三分位**内部**重新排名）")
    lines.append("")
    lines.append("| 成交额三分位 | 股票周 | 中位日均成交额 | 5 日差 (t) | 21 日差 (t) |")
    lines.append("|---|---:|---:|---:|---:|")
    for row in broad.get("by_liquidity_tercile", []):
        five = row["label_excess_5"]
        twentyone = row["label_excess_21"]
        lines.append(
            f"| {row['label']} | {row['stock_weeks']:,} | "
            f"${row['median_dollar_adv'] / 1e6:.1f}M | "
            f"{_num(five['mean'])} ({_num(five.get('t'), '+.2f')}) | "
            f"{_num(twentyone['mean'])} ({_num(twentyone.get('t'), '+.2f')}) |"
        )
    lines.append("")
    lines.append(
        "三档都为负才说明它不是规模/流动性效应换了件衣服；只有最不流动那一档为负，"
        "就要按小票溢价来读。"
    )
    lines.append("")
    lines.append("### 4.2 逐年（看是不是某一段行情扛起来的）")
    lines.append("")
    lines.append("| 年 | 股票周 | 5 日差 (t) | 21 日差 (t) |")
    lines.append("|---|---:|---:|---:|")
    for row in broad.get("by_year_ratio_spread", []):
        five = row["label_excess_5"]
        twentyone = row["label_excess_21"]
        lines.append(
            f"| {row['year']} | {row['stock_weeks']:,} | "
            f"{_num(five['mean'])} ({_num(five.get('t'), '+.2f')}) | "
            f"{_num(twentyone['mean'])} ({_num(twentyone.get('t'), '+.2f')}) |"
        )
    lines.append("")
    lines.append(
        "重叠窗口提醒：21 日标签在周频上重叠约 4 倍，所以上面所有 21 日的 t 要按约 "
        "1/√4 ≈ 0.5 打折才是独立观测下的读数；文中引用时已经说明。"
    )
    lines.append("")
    lines.append(
        "幸存者偏差提醒：这个宽口径池子来自 `data/features/daily`，里面**没有已退市/被收购的代码**"
        "（见 `D-20260917-01`）。破产退市的名字通常正是空头最拥挤的那一类，"
        "所以这里的「高空头 → 未来更差」很可能被**低估**而不是高估。"
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# stage: gate-states
# --------------------------------------------------------------------------


def _feature_root_for(source: str) -> Path:
    if source == "real":
        return SHORT_INTEREST_ROOT
    seed = int(source.removeprefix("placebo"))
    return SHORT_INTEREST_ROOT.with_name(
        f"short_interest_placebo_shift{PLACEBO_SHIFT_DAYS}_seed{seed}"
    )


def _gate_state_path(source: str) -> Path:
    return GATE_STATES_DIR / f"{source}.parquet"


def build_gate_state_frame(picks: pd.DataFrame, feature_root: Path) -> pd.DataFrame:
    """One row per (rebalance date, held symbol) with the short-interest columns
    the avoid layers read, as of that rebalance date, plus each layer's state.
    """
    book = picks.loc[(picks["weight"] > 0.0) & (picks["symbol"] != CASH_SYMBOL)].copy()
    book["rebalance_date"] = pd.to_datetime(book["rebalance_date"])
    book["symbol"] = book["symbol"].astype(str)
    wanted = ["dtc_cross_sectional_pct", "days_to_cover", "staleness_days", "si_record_present"]
    frames = []
    for year in sorted({int(date.year) for date in book["rebalance_date"]}):
        path = feature_root / f"{year}.parquet"
        if not path.exists():
            continue
        dates = set(book.loc[book["rebalance_date"].dt.year == year, "rebalance_date"])
        frame = pd.read_parquet(path, columns=["symbol", "trade_date", *wanted])
        frame["symbol"] = frame["symbol"].astype(str)
        frames.append(frame.loc[frame["trade_date"].isin(dates)])
    if not frames:
        raise SystemExit(f"no short-interest feature years found under {feature_root}")
    features = pd.concat(frames, ignore_index=True)
    merged = book.merge(
        features.rename(columns={"trade_date": "rebalance_date"}),
        on=["symbol", "rebalance_date"],
        how="left",
    )
    merged["si_record_present"] = merged["si_record_present"].fillna(0.0)
    for name in AVOID_SPECS:
        merged[f"state_{name}"] = avoid_states(merged, name)
    columns = [
        "rebalance_date",
        "symbol",
        "weight",
        "score",
        "score_pct",
        "cohort_size",
        "universe_size",
        *wanted,
        *[f"state_{name}" for name in AVOID_SPECS],
    ]
    return merged[[c for c in columns if c in merged.columns]].sort_values(
        ["rebalance_date", "symbol"], ignore_index=True
    )


def stage_gate_states(*, force: bool, sources: list[str]) -> int:
    picks = pd.read_parquet(PICKS_PATH)
    GATE_STATES_DIR.mkdir(parents=True, exist_ok=True)
    for source in sources:
        path = _gate_state_path(source)
        if path.exists() and not force:
            _log(f"{path.name}: already present -- reusing (checkpoint)")
            continue
        root = _feature_root_for(source)
        if not (root / "_build_manifest.json").exists():
            _log(f"{source}: {root} not built yet -- skipping")
            continue
        frame = build_gate_state_frame(picks, root)
        _write_parquet(path, frame)
        shares = {name: state_shares(frame[f"state_{name}"]) for name in AVOID_SPECS}
        _log(
            f"{source}: {len(frame):,} book rows, coverage "
            f"{float(frame['si_record_present'].mean()):.2%}; "
            + "; ".join(
                f"{name} full={share.get('full', 0.0):.3f}" for name, share in shares.items()
            )
        )
    return 0


# --------------------------------------------------------------------------
# stage: evaluate
# --------------------------------------------------------------------------


def variant_books(states: pd.DataFrame) -> dict[str, pd.DataFrame]:
    books: dict[str, pd.DataFrame] = {"gate_off": states[["rebalance_date", "symbol", "weight"]]}
    for name in AVOID_SPECS:
        multiplier = states[f"state_{name}"].map(STATE_WEIGHT_MULTIPLIER)
        raw = states.assign(weight=states["weight"] * multiplier)
        books[f"{name}_raw"] = raw[["rebalance_date", "symbol", "weight"]]
        books[f"{name}_norm"] = normalize_weights_to_full_exposure(raw)[
            ["rebalance_date", "symbol", "weight"]
        ]
    return books


def _slice_window(series: pd.Series, start: pd.Timestamp) -> pd.Series:
    return series.loc[series.index >= start]


def _window_block(
    returns: pd.Series,
    stress_returns: pd.Series,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    schedule: list[RebalanceEvent],
    start: pd.Timestamp,
) -> dict[str, Any]:
    sliced = _slice_window(returns, start)
    weekly = m_grid._weekly_returns_excluding_cash(schedule, returns, recent_start=start)
    return {
        "cagr_net": annualized_cagr(sliced),
        "max_drawdown": max_drawdown(sliced),
        "cagr_excess_vol_matched_spy": cagr_excess_vol_matched(sliced, spy_returns, bil_returns),
        "vol_match_weight_vs_spy": vol_match_weight(sliced, spy_returns),
        "hit_rate_weekly": regime_metrics.hit_rate(weekly),
        "stress_cost_cagr_net": annualized_cagr(_slice_window(stress_returns, start)),
        "window": [
            sliced.index.min().date().isoformat(),
            sliced.index.max().date().isoformat(),
        ],
        "weeks": len(weekly),
    }


def _variant_metrics(
    *,
    label: str,
    book: pd.DataFrame,
    states: pd.DataFrame,
    gate_name: str | None,
    returns: pd.Series,
    stress_returns: pd.Series,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    schedule: list[RebalanceEvent],
    oos_start: pd.Timestamp,
) -> dict[str, Any]:
    weekly_recent = m_grid._weekly_returns_excluding_cash(
        schedule, returns, recent_start=pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    )
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=f"h20260916_07_{label}",
        config_hash=f"h20260916_07_{label}",
        full_returns=returns,
        full_stress_returns=stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=weekly_recent,
        rebalances_with_change_per_year=m_grid._rebalances_with_change_per_year(schedule),
        family=m_grid.FAMILY,
        is_ml=False,
        reference_only=True,
    )
    turnover = turnover_per_rebalance(schedule)
    exposure = [
        sum(weight for symbol, weight in event.selected.items() if symbol != CASH_SYMBOL)
        for event in schedule
        if event.selected
    ]
    metrics: dict[str, Any] = {
        "label": label,
        "recent_2024": {
            "cagr_net": verdict.metrics["cagr_recent_net"],
            "max_drawdown": verdict.metrics["max_drawdown_recent"],
            "cagr_excess_vol_matched_spy": verdict.metrics["cagr_excess_vol_matched_spy"],
            "vol_match_weight_vs_spy": verdict.metrics["vol_match_weight_vs_spy"],
            "hit_rate_weekly": verdict.metrics["hit_rate_weekly"],
            "sharpe_excess_bil": verdict.metrics["sharpe_excess_bil_recent"],
            "stress_cost_cagr_net": verdict.metrics["stress_cost_recent_cagr_net"],
            "window": [
                verdict.metrics["recent_window_start"],
                verdict.metrics["recent_window_end"],
            ],
            "all_gates_pass": verdict.all_gates_pass,
        },
        "full_oos": _window_block(
            returns, stress_returns, spy_returns, bil_returns, schedule, oos_start
        ),
        "h03_comparable": _window_block(
            returns, stress_returns, spy_returns, bil_returns, schedule, H03_COMPARABLE_START
        ),
        "turnover_per_rebalance_mean": float(np.mean(turnover[1:])) if len(turnover) > 1 else None,
        "turnover_annualized": float(np.mean(turnover[1:]) * 52.0) if len(turnover) > 1 else None,
        "mean_invested_exposure": float(np.mean(exposure)) if exposure else None,
        "min_invested_exposure": float(np.min(exposure)) if exposure else None,
        "rebalance_count": len([event for event in schedule if event.selected]),
        "positions_per_week_mean": float(
            book.loc[book["weight"] > 0].groupby("rebalance_date").size().mean()
        ),
    }
    if gate_name is not None:
        column = f"state_{gate_name}"
        recent = pd.Timestamp(regime_gates.RECENT_WINDOW_START)
        dates = pd.to_datetime(states["rebalance_date"])
        metrics["state_shares"] = state_shares(states[column])
        metrics["state_shares_recent_2024"] = state_shares(states.loc[dates >= recent, column])
        metrics["state_shares_per_year"] = {
            str(year): state_shares(group[column]) for year, group in states.groupby(dates.dt.year)
        }
        metrics["gate_state_changes_per_year"] = gate_state_changes_per_year(states, gate_name)
        metrics["rebalances_with_gate_change_per_year"] = rebalances_with_gate_change_per_year(
            states, gate_name
        )
    return metrics


def _price_streams(
    schedule: list[RebalanceEvent],
    price_wide: pd.DataFrame,
    open_wide: pd.DataFrame,
    spy_returns: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    primary = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=PRIMARY_COST_BPS,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=open_wide,
    )
    stress = returns_from_weight_schedule(
        schedule,
        price_wide,
        spy_returns,
        cost_bps_per_side=STRESS_COST_BPS,
        include_hedge=False,
        execution=EXECUTION,
        open_wide=open_wide,
    )
    return primary, stress


def stage_evaluate(*, force: bool) -> int:
    del force
    precheck = json.loads(PRECHECK_JSON.read_text()) if PRECHECK_JSON.exists() else None
    if precheck is not None and not precheck["verdict"]["proceed_to_twin_cells"]:
        _log(
            "pre-check verdict says STOP "
            f"(book hit share {precheck['verdict']['book_hit_share']:.2%} < "
            f"{MIN_BOOK_HIT_SHARE:.0%}); not pricing anything"
        )
        return 0
    states_real = pd.read_parquet(_gate_state_path("real"))
    states_real["rebalance_date"] = pd.to_datetime(states_real["rebalance_date"])
    oos_dates = pd.DatetimeIndex(sorted(states_real["rebalance_date"].unique()))
    oos_start = oos_dates.min()
    _log(f"book span: {oos_start.date()}..{oos_dates.max().date()} ({len(oos_dates)} rebalances)")

    years = tuple(range(oos_start.year, 2027))
    common = m_grid._load_common_data(years=years, trend_gate_required=False)
    held = set(states_real["symbol"].astype(str)) | {CASH_SYMBOL}
    for seed in PLACEBO_SEEDS:
        path = _gate_state_path(f"placebo{seed}")
        if path.exists():
            held |= set(pd.read_parquet(path, columns=["symbol"])["symbol"].astype(str))
    price_panel = common.price_panel
    price_panel = price_panel.loc[price_panel["symbol"].astype(str).isin(held)]
    _log(f"price panel narrowed to {price_panel['symbol'].nunique()} held symbols")
    price_wide = price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = price_panel.pivot(index="trade_date", columns="symbol", values="open")
    spy_returns = common.spy_returns
    bil_returns = common.bil_returns
    del common, price_panel

    results: dict[str, Any] = {"variants": {}, "control_variants": {}}
    for label, book in variant_books(states_real).items():
        gate_name = None if label == "gate_off" else label.rsplit("_", 1)[0]
        cash = None if label.endswith("_norm") or label == "gate_off" else CASH_SYMBOL
        schedule = weight_schedule_from_pick_frame(
            book, cash_symbol=cash, universe_size_column=None
        )
        primary, stress = _price_streams(schedule, price_wide, open_wide, spy_returns)
        results["variants"][label] = _variant_metrics(
            label=label,
            book=book,
            states=states_real,
            gate_name=gate_name,
            returns=primary,
            stress_returns=stress,
            spy_returns=spy_returns,
            bil_returns=bil_returns,
            schedule=schedule,
            oos_start=oos_start,
        )
        recent = results["variants"][label]["recent_2024"]
        _log(
            f"{label}: 2024→ CAGR {recent['cagr_net']:.4f} MDD {recent['max_drawdown']:.4f} "
            f"vol-matched excess {recent['cagr_excess_vol_matched_spy']:.4f} "
            f"exposure {results['variants'][label]['mean_invested_exposure']:.3f}"
        )

    def price_control(control: str, seed: int, states: pd.DataFrame) -> int:
        books = variant_books(states)
        count = 0
        for gate_name in AVOID_SPECS:
            label = f"{gate_name}_norm"
            schedule = weight_schedule_from_pick_frame(
                books[label], cash_symbol=None, universe_size_column=None
            )
            primary, stress = _price_streams(schedule, price_wide, open_wide, spy_returns)
            results["control_variants"][f"{label}__{control}{seed}"] = _variant_metrics(
                label=f"{label}__{control}{seed}",
                book=books[label],
                states=states,
                gate_name=gate_name,
                returns=primary,
                stress_returns=stress,
                spy_returns=spy_returns,
                bil_returns=bil_returns,
                schedule=schedule,
                oos_start=oos_start,
            )
            count += 1
        return count

    for seed in PLACEBO_SEEDS:
        path = _gate_state_path(f"placebo{seed}")
        if not path.exists():
            _log(f"shift{seed}: no gate-state checkpoint -- skipping")
            continue
        shifted = pd.read_parquet(path)
        shifted["rebalance_date"] = pd.to_datetime(shifted["rebalance_date"])
        _log(f"shift{seed}: priced {price_control(CONTROL_SHIFT, seed, shifted)} books")

    for seed in SHUFFLE_SEEDS:
        shuffled = shuffle_states_within_date(states_real, list(AVOID_SPECS), seed)
        _log(f"shuffle{seed}: priced {price_control(CONTROL_SHUFFLE, seed, shuffled)} books")

    _write_json(RESULTS_PATH, results)
    _log(f"wrote {RESULTS_PATH.name} ({len(results['variants'])} real books)")
    return stage_report()


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def _reference_disclosures() -> dict[str, Any]:
    payload = json.loads(
        (ROOT / "config" / "promotion" / "recent-regime-high-return-gates-v2.json").read_text()
    )
    return payload["reference_disclosures"]


def _control_aggregate(
    results: dict[str, Any], baseline_excess: float, control: str
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for gate_name in AVOID_SPECS:
        label = f"{gate_name}_norm"
        rows = [
            metrics
            for key, metrics in results["control_variants"].items()
            if key.startswith(f"{label}__{control}")
        ]
        if not rows:
            continue
        improvements = [
            row["recent_2024"]["cagr_excess_vol_matched_spy"] - baseline_excess for row in rows
        ]
        out[label] = {
            "seeds": len(rows),
            "improvements": improvements,
            "improvement_mean": float(np.mean(improvements)),
            "improvement_min": float(np.min(improvements)),
            "improvement_max": float(np.max(improvements)),
            "cagr_recent_mean": float(np.mean([r["recent_2024"]["cagr_net"] for r in rows])),
            "max_drawdown_recent_mean": float(
                np.mean([r["recent_2024"]["max_drawdown"] for r in rows])
            ),
            "turnover_per_rebalance_mean": float(
                np.mean([r["turnover_per_rebalance_mean"] for r in rows])
            ),
            "positions_per_week_mean": float(np.mean([r["positions_per_week_mean"] for r in rows])),
        }
    return out


def _stop_conditions(
    results: dict[str, Any], controls: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    baseline = results["variants"]["gate_off"]
    baseline_excess = baseline["recent_2024"]["cagr_excess_vol_matched_spy"]
    baseline_turnover = baseline["turnover_per_rebalance_mean"]
    out: dict[str, Any] = {}
    for gate_name in AVOID_SPECS:
        label = f"{gate_name}_norm"
        if label not in results["variants"]:
            continue
        real = results["variants"][label]
        improvement = real["recent_2024"]["cagr_excess_vol_matched_spy"] - baseline_excess
        ratios: dict[str, float | None] = {}
        for control, aggregate in controls.items():
            row = aggregate.get(label)
            if row is None:
                ratios[control] = None
                continue
            ratios[control] = row["improvement_mean"] / improvement if improvement > 0.0 else None
        turnover_up = (
            real["turnover_per_rebalance_mean"] > baseline_turnover
            if baseline_turnover is not None
            else None
        )
        out[gate_name] = {
            "improvement_pp": improvement,
            "improvement_meets_threshold": bool(improvement >= STOP_EXCESS_IMPROVEMENT_PP),
            "control_share": ratios,
            "control_reproduces_half": {
                control: (ratio is not None and ratio >= STOP_CONTROL_SHARE)
                for control, ratio in ratios.items()
            },
            "turnover_up_without_excess_up": bool(turnover_up and improvement <= 0.0),
            "verdict": (
                "PASS"
                if improvement >= STOP_EXCESS_IMPROVEMENT_PP
                and not any(
                    ratio is not None and ratio >= STOP_CONTROL_SHARE for ratio in ratios.values()
                )
                and not (turnover_up and improvement <= 0.0)
                else "STOP"
            ),
        }
    return out


def stage_report() -> int:
    results = json.loads(RESULTS_PATH.read_text())
    baseline_excess = results["variants"]["gate_off"]["recent_2024"]["cagr_excess_vol_matched_spy"]
    controls = {
        CONTROL_SHUFFLE: _control_aggregate(results, baseline_excess, CONTROL_SHUFFLE),
        CONTROL_SHIFT: _control_aggregate(results, baseline_excess, CONTROL_SHIFT),
    }
    precheck = json.loads(PRECHECK_JSON.read_text()) if PRECHECK_JSON.exists() else None
    screen = None
    screen_path = OUT_DIR / "screen.json"
    if screen_path.exists():
        screen = json.loads(screen_path.read_text())
    report = {
        "hypothesis": "H-20260916-07",
        "card": ("reports/research/hypotheses/H-20260916-07-finra-short-interest-avoid-list.md"),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "primary_cell": PRIMARY_CELL,
        "avoid_specs": {
            name: {"description": spec.description, "columns": list(spec.columns)}
            for name, spec in AVOID_SPECS.items()
        },
        "threshold": AVOID_PERCENTILE_THRESHOLD,
        "placebo_shift_days": PLACEBO_SHIFT_DAYS,
        "placebo_seeds": list(PLACEBO_SEEDS),
        "shuffle_seeds": list(SHUFFLE_SEEDS),
        "reference_disclosures": _reference_disclosures(),
        "contract_judgement": "reference_only",
        "variants": results["variants"],
        "controls": controls,
        "stop_conditions": _stop_conditions(results, controls),
        "precheck": precheck,
        "screen_meta": screen["meta"] if screen else None,
    }
    _write_json(REPORT_JSON_PATH, report)
    REPORT_MD_PATH.write_text(_render_report(report), encoding="utf-8")
    _log(f"wrote {REPORT_JSON_PATH.name} and {REPORT_MD_PATH.name}")
    return 0


def _render_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# H-20260916-07 孪生单元：FINRA 空头兴趣回避清单")
    lines.append("")
    lines.append(
        f"生成时间 {report['generated_at']}｜基础单元 `{report['primary_cell']}`｜"
        f"阈值 = DTC 在池内百分位 ≥ {report['threshold']:.2f}｜"
        f"合同判定 = `{report['contract_judgement']}`（披露，不进账本）"
    )
    lines.append("")
    if report.get("precheck"):
        verdict = report["precheck"]["verdict"]
        lines.append(
            f"前置检查：avoid 条件命中组合 {_pct(verdict['book_hit_share'])} 的持仓周"
            f"（门槛 {_pct(verdict['minimum_required'], 0)}）→ "
            f"{'继续' if verdict['proceed_to_twin_cells'] else '停止'}。"
            "完整交叉表见 `precheck.md`。"
        )
        lines.append("")
    lines.append("## 主表（2024-01-02 起近窗，归一化到 100% 暴露是决策口径）")
    lines.append("")
    lines.append(
        "| 变体 | CAGR | 最大回撤 | 同波动 SPY 超额 | 平均暴露 | 每周双边换手 | 平均持仓只数 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for label, metrics in report["variants"].items():
        recent = metrics["recent_2024"]
        lines.append(
            f"| `{label}` | {_pct(recent['cagr_net'])} | {_pct(recent['max_drawdown'])} | "
            f"{_pct(recent['cagr_excess_vol_matched_spy'])} | "
            f"{_num(metrics['mean_invested_exposure'], '.3f')} | "
            f"{_num(metrics['turnover_per_rebalance_mean'], '.3f')} | "
            f"{_num(metrics['positions_per_week_mean'], '.1f')} |"
        )
    lines.append("")
    reference = report["reference_disclosures"]
    lines.append(
        f"对照数（`reference_disclosures`，{reference['window']}）："
        f"SPY {reference['SPY']['cagr'] * 100:.1f}% / "
        f"{reference['SPY']['max_drawdown'] * 100:.1f}%，"
        f"MTUM {reference['MTUM']['cagr'] * 100:.1f}% / "
        f"{reference['MTUM']['max_drawdown'] * 100:.1f}%，"
        f"SPMO {reference['SPMO']['cagr'] * 100:.1f}% / "
        f"{reference['SPMO']['max_drawdown'] * 100:.1f}%。"
    )
    lines.append("")
    lines.append("## 两套对照（都按分布报，不报单值）")
    lines.append("")
    lines.append("| 对照 | 变体 | 种子数 | 改善均值 | 最小 | 最大 | 占真实改善的比例 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    stop = report["stop_conditions"]
    for control, aggregate in report["controls"].items():
        for label, row in aggregate.items():
            gate_name = label.rsplit("_", 1)[0]
            ratio = stop.get(gate_name, {}).get("control_share", {}).get(control)
            lines.append(
                f"| {control} | `{label}` | {row['seeds']} | "
                f"{_pct(row['improvement_mean'], 2)} | {_pct(row['improvement_min'], 2)} | "
                f"{_pct(row['improvement_max'], 2)} | "
                f"{_num(ratio, '.2f') if ratio is not None else 'n/a'} |"
            )
    lines.append("")
    lines.append("## 停止判据（任一命中即停）")
    lines.append("")
    lines.append(
        "| 变体 | 归一化同波动超额改善 | ≥ 2pp | 对照复现 ≥ 50% | 换手升而超额不升 | 判定 |"
    )
    lines.append("|---|---:|:-:|:-:|:-:|:-:|")
    for gate_name, row in stop.items():
        reproduced = ", ".join(
            f"{control}={'是' if value else '否'}"
            for control, value in row["control_reproduces_half"].items()
        )
        lines.append(
            f"| `{gate_name}` | {_pct(row['improvement_pp'], 2)} | "
            f"{'是' if row['improvement_meets_threshold'] else '否'} | {reproduced} | "
            f"{'是' if row['turnover_up_without_excess_up'] else '否'} | **{row['verdict']}** |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--stage",
        required=True,
        choices=["export", "precheck", "gate-states", "evaluate", "report"],
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--sources",
        nargs="*",
        default=None,
        help="gate-states sources: real, placebo{seed}. Default: real plus every placebo seed.",
    )
    args = parser.parse_args(argv)

    if args.stage == "export":
        return stage_export(force=args.force)
    if args.stage == "precheck":
        return stage_precheck(force=args.force)
    if args.stage == "gate-states":
        sources = args.sources or ["real", *[f"placebo{seed}" for seed in PLACEBO_SEEDS]]
        return stage_gate_states(force=args.force, sources=sources)
    if args.stage == "evaluate":
        return stage_evaluate(force=args.force)
    return stage_report()


if __name__ == "__main__":
    raise SystemExit(main())
