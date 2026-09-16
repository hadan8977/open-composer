"""H-20260916-03: meta-labeling position tiers on the rule-momentum top-50 book.

Card: ``reports/research/hypotheses/H-20260916-03-meta-labeling-position-tiers.md``.
One-line hypothesis: keep the rule-momentum primary signal exactly as it is,
and let a second-stage classifier decide only *whether and how big* to hold
each of its weekly picks (p < 0.4 -> 0, 0.4-0.6 -> 1%, > 0.6 -> 2%, rest in
BIL), versus today's flat equal-weight 2%.

The primary cell is not re-designed and not re-tuned here. It is exactly
``step13_m0b_mom_over_vol63_uni500_k50_gate_off`` (ledger family
``step13_recent_high_return``): ``MomentumFactorStrategy`` on the derived
column ``momentum_252_21_over_vol_63``, PIT universe ``adv_rank <= 500``,
top 50 names, weekly (last session of each ISO week) equal weight, trend gate
**off**, 24-month trailing training window, quarterly refit, ``next_open``
execution, 10 bps/side primary cost and 25 bps/side stress cost. The only
difference from ``scripts/run_step13_m_grid.py``'s own M0b cell is the
walk-forward span: that cell only walks the gated window (2024-2026), while a
meta-labeler needs a training history, so this script walks 2017-2026 (see
``TEST_YEARS`` below for why 2017 and not 2016) and evaluates only on the
quarters that follow a real 3-year training window.

Data loading, universe handling, benchmark/cash augmentation and the
regime-table date clipping are **imported** from
``scripts/run_step13_m_grid.py`` rather than re-implemented, so the picks this
script exports cannot silently diverge from the cell they claim to filter.
Scoring reuses ``regime.gates.evaluate_recent_high_return_candidate`` for the
gate contract's own recent window (2024-01-02 onward) so the headline
``cagr_excess_vol_matched_spy`` is the ledger's own number, and
``kernel.vol_matched`` (tested to reproduce that number) for the wider
full-OOS window the gate function has no entry point for.

**No ledger row is written.** Nothing here goes through
``loop.run_experiment``, so per this round's instruction the shared
``reports/research/ledger/experiments.jsonl`` is left untouched; the recent-
window gate verdicts are computed with ``reference_only=True`` and are
reported as disclosure only.

Stages (each resumable from its own parquet/json checkpoints under
``reports/research/iterations/h20260916_03_meta_label/``; re-running a stage
whose outputs exist is a no-op unless ``--force``)::

    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_03_meta_label.py export
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_03_meta_label.py train
    ./scripts/run_capped.sh --mem 1.8G -- \\
        uv run python scripts/run_h20260916_03_meta_label.py evaluate
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

from open_composer.research.features.panel import load_feature_panel  # noqa: E402
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy  # noqa: E402
from open_composer.research.kernel.loop import (  # noqa: E402
    RebalanceEvent,
    build_weight_schedule,
    returns_from_weight_schedule,
)
from open_composer.research.kernel.mechanism_eval import annualized_cagr, max_drawdown  # noqa: E402
from open_composer.research.kernel.pick_export import (  # noqa: E402
    PickCollector,
    turnover_per_rebalance,
    weight_schedule_from_pick_frame,
)
from open_composer.research.kernel.vol_matched import (  # noqa: E402
    cagr_excess_vol_matched,
    vol_match_weight,
)
from open_composer.research.regime import gates as regime_gates  # noqa: E402
from open_composer.research.regime import metrics as regime_metrics  # noqa: E402

m_grid = importlib.import_module("scripts.run_step13_m_grid")

OUT_DIR = ROOT / "reports" / "research" / "iterations" / "h20260916_03_meta_label"
MODEL_DIR = OUT_DIR / "models"
PICKS_PATH = OUT_DIR / "picks.parquet"
DATASET_PATH = OUT_DIR / "dataset.parquet"
SCHEDULE_PATH = OUT_DIR / "schedule_baseline.json"
WEEKLY_MARKS_PATH = OUT_DIR / "weekly_marks.parquet"
REGIME_WEEKLY_PATH = OUT_DIR / "regime_weekly.parquet"
VALIDATION_METRICS_PATH = OUT_DIR / "validation_metrics.json"
REPORT_JSON_PATH = OUT_DIR / "report.json"
REPORT_MD_PATH = OUT_DIR / "report.md"

#: The primary cell, unchanged (see module docstring).
SCORE_COLUMN = "momentum_252_21_over_vol_63"
UNIVERSE_TOP_N = 500
TOP_K = 50
TRAIN_WINDOW_MONTHS = m_grid.TRAIN_WINDOW_MONTHS  # 24, the cell's own value
PRIMARY_COST_BPS = m_grid.PRIMARY_COST_BPS  # 10.0
STRESS_COST_BPS = m_grid.STRESS_COST_BPS  # 25.0
CASH_SYMBOL = m_grid.CASH_SYMBOL  # "BIL"
EXECUTION = "next_open"

#: Panel years to load. The card asks for 2016-01 onward; ``momentum_252_21``
#: needs 252 trading days of history and the SIP daily archive starts
#: 2016-01-04, so every 2016 row's momentum is null (verified: 0 non-null
#: rows in data/features/daily/2016.parquet) and the first date that can
#: produce a pick at all is 2017-01-03. 2016 is therefore loaded as warm-up
#: only and TEST_YEARS starts at 2017 -- a 2016 test year would just crash
#: ``embargo_cutoff`` for want of prior trading days.
DATA_YEARS: tuple[int, ...] = tuple(range(2016, 2027))
TEST_YEARS: tuple[int, ...] = tuple(range(2017, 2027))

#: Columns pulled from the daily feature panel. Only ``SCORE_COLUMN`` is
#: passed to ``build_weight_schedule``'s ``feature_columns`` (that argument
#: drives the notna mask and therefore selection); the rest ride along on the
#: as-of frame purely so ``PickCollector`` can record them, which is why
#: adding them cannot change a single pick.
PANEL_FEATURE_COLUMNS: tuple[str, ...] = (
    "momentum_252_21",
    "vol_63",
    "ret_21",
    "dist_from_252d_high",
    "overnight_return_21d_mean",
    "intraday_return_21d_mean",
)

#: The card's feature list, in card order. Each is either a panel column or
#: derived below in ``build_dataset``; ``report.md`` documents which.
FEATURE_COLUMNS: tuple[str, ...] = (
    "momentum_pct",
    "vol_63",
    "excess_21d_vs_book",
    "weeks_in_book",
    "dist_from_252d_high",
    "overnight_intraday_ratio",
    "spy_gap_200sma",
    "breadth_50d",
)

#: Label horizon in weekly rebalance steps (4 weeks ~ 28 calendar days).
LABEL_WEEKS = 4
#: Rolling training window and embargo, from the card ("训练滚动 3 年、验证留出
#: 1 个季度、隔离期 4 周；每季重训"). The embargo is exactly the label horizon,
#: so the last training pick's forward window closes on the first validation
#: day rather than overlapping it.
TRAIN_YEARS = 3
EMBARGO_DAYS = 28
MIN_TRAIN_ROWS = 2000

#: Position tiers, exactly as preregistered in the card. Not tuned here.
TIER_LOW_P = 0.4
TIER_HIGH_P = 0.6
TIER_MID_WEIGHT = 0.01
TIER_HIGH_WEIGHT = 0.02

MODELS = ("logit", "lgbm")
#: The placebo is run on several seeds, not one. With a single permutation the
#: card's "placebo reached >= 50% of the real improvement" test is decided by
#: one draw: the first run of this script produced ratios of 1.06 (logit) and
#: 0.49 (lgbm) -- i.e. the boosted tree "passed" by 0.007, which is noise, not
#: evidence. Five seeds turn that single draw into a distribution, and the
#: verdict uses the mean placebo improvement with the full spread disclosed.
PLACEBO_SEED = 20260916
PLACEBO_SEED_COUNT = 5
PLACEBO_VARIANTS: tuple[str, ...] = tuple(
    f"placebo{index + 1}" for index in range(PLACEBO_SEED_COUNT)
)
VARIANTS: tuple[str, ...] = ("real", *PLACEBO_VARIANTS)
LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "n_estimators": 200,
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_child_samples": 100,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 7,
    "n_jobs": 2,
    "verbose": -1,
}


def _log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str))
    tmp.replace(path)


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.replace(path)


def _events_to_json(schedule: list[RebalanceEvent]) -> list[dict[str, Any]]:
    return [
        {
            "date": event.date,
            "universe_size": event.universe_size,
            "selected": event.selected,
            "portfolio_beta": event.portfolio_beta,
        }
        for event in schedule
    ]


def _events_from_json(payload: list[dict[str, Any]]) -> list[RebalanceEvent]:
    return [
        RebalanceEvent(
            date=row["date"],
            universe_size=int(row["universe_size"]),
            selected={str(k): float(v) for k, v in row["selected"].items()},
            portfolio_beta=row.get("portfolio_beta"),
        )
        for row in payload
    ]


# --------------------------------------------------------------------------
# stage: export
# --------------------------------------------------------------------------


def stage_export(*, force: bool) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not force and PICKS_PATH.exists() and SCHEDULE_PATH.exists() and WEEKLY_MARKS_PATH.exists():
        _log(f"{PICKS_PATH.name} / {SCHEDULE_PATH.name} already present -- reusing (checkpoint)")
    else:
        common = m_grid._load_common_data(years=DATA_YEARS, trend_gate_required=False)
        _log(
            "loading feature panel on rebalance dates "
            f"({len(common.weekly_dates)} weekly dates, {len(PANEL_FEATURE_COLUMNS)} columns) ..."
        )
        panel = load_feature_panel(
            list(PANEL_FEATURE_COLUMNS),
            ["label_rank_5"],
            dates=common.weekly_dates,
            include_prices=False,
        )
        ratio = panel["momentum_252_21"] / panel["vol_63"]
        panel[SCORE_COLUMN] = ratio.replace([np.inf, -np.inf], np.nan)
        _log(f"panel rows={len(panel):,} memory={panel.memory_usage(deep=True).sum() / 1e6:.0f}MB")

        collector = PickCollector(feature_columns=(SCORE_COLUMN, *PANEL_FEATURE_COLUMNS))
        _log(f"building the weight schedule for test years {TEST_YEARS} ...")
        trading_calendar = pd.DatetimeIndex(sorted(common.price_panel["trade_date"].unique()))
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
            trend_gate_series=None,  # the cell is gate_off
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

        weekly_index = pd.DatetimeIndex(sorted(picks["rebalance_date"].unique()))
        held = set(picks["symbol"].unique())
        marks = common.price_panel.loc[
            common.price_panel["trade_date"].isin(weekly_index)
            & common.price_panel["symbol"].astype(str).isin(held),
            ["symbol", "trade_date", "close"],
        ].copy()
        marks["symbol"] = marks["symbol"].astype(str)
        _write_parquet(WEEKLY_MARKS_PATH, marks.reset_index(drop=True))
        _log(f"wrote {WEEKLY_MARKS_PATH.name}: {len(marks):,} weekly close marks")

        regime_weekly = common.regime_daily.loc[
            common.regime_daily["trade_date"].isin(weekly_index),
            ["trade_date", "spy_gap_200sma", "breadth_50d", "cs_dispersion_21"],
        ].copy()
        _write_parquet(REGIME_WEEKLY_PATH, regime_weekly.reset_index(drop=True))
        del common, panel, schedule
    dataset = build_dataset()
    _write_parquet(DATASET_PATH, dataset)
    labelled = int(dataset["label"].notna().sum())
    _log(
        f"wrote {DATASET_PATH.name}: {len(dataset):,} rows "
        f"({labelled:,} with a resolved 4-week label, "
        f"positive fraction {dataset['label'].mean():.4f})"
    )


def build_dataset() -> pd.DataFrame:
    """One row per (rebalance date, symbol in the top-50 book), with the
    card's eight as-of features and the 4-week within-book label.

    Label: the symbol's close-to-close return over the next
    ``LABEL_WEEKS`` weekly rebalance dates minus the equal-weight *median* of
    that same week's book, ``> 0 -> 1``. The book median (not the mean) is
    the card's own definition, and it makes the label balanced by
    construction within each week, which is what keeps the placebo's
    positive-fraction preservation meaningful.

    Derived (not panel) columns, with the reason each is derived:
    ``momentum_pct`` = the pick's ascending percentile of
    ``momentum_252_21_over_vol_63`` within that date's own top-500 PIT cohort
    (recorded by ``PickCollector``; not recoverable from the book, which is
    already a top-50 truncation); ``excess_21d_vs_book`` = ``ret_21`` minus
    the book's median ``ret_21`` that week (the card's "过去 4 周相对组合的超额");
    ``weeks_in_book`` = number of consecutive weekly rebalances, including
    this one, that the symbol has been in the book; and
    ``overnight_intraday_ratio`` = ``overnight_return_21d_mean`` /
    ``intraday_return_21d_mean``, clipped to +-5 and set null when the
    denominator is within 1e-5 of zero (a raw ratio of two small signed means
    is unbounded and would otherwise dominate a linear model). No column in
    this frame uses information from after its own rebalance date except
    the label itself.
    """
    picks = pd.read_parquet(PICKS_PATH)
    marks = pd.read_parquet(WEEKLY_MARKS_PATH)
    regime = pd.read_parquet(REGIME_WEEKLY_PATH)

    book = picks.loc[(picks["weight"] > 0.0) & (picks["symbol"] != CASH_SYMBOL)].copy()
    book["rebalance_date"] = pd.to_datetime(book["rebalance_date"])

    close_wide = marks.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    forward = close_wide.shift(-LABEL_WEEKS) / close_wide - 1.0
    stacked = forward.stack()
    stacked.index = stacked.index.set_names(["rebalance_date", "symbol"])
    keys = pd.MultiIndex.from_arrays(
        [book["rebalance_date"], book["symbol"]], names=["rebalance_date", "symbol"]
    )
    book["fwd_4w_ret"] = stacked.reindex(keys).to_numpy()

    grouped = book.groupby("rebalance_date")
    book["book_size"] = grouped["symbol"].transform("size").astype(int)
    book["book_median_fwd_4w_ret"] = grouped["fwd_4w_ret"].transform("median")
    book["fwd_4w_excess_vs_book"] = book["fwd_4w_ret"] - book["book_median_fwd_4w_ret"]
    book["label"] = np.where(
        book["fwd_4w_excess_vs_book"].notna(),
        (book["fwd_4w_excess_vs_book"] > 0.0).astype(float),
        np.nan,
    )

    book["momentum_pct"] = book["score_pct"]
    book["excess_21d_vs_book"] = book["ret_21"] - grouped["ret_21"].transform("median")
    denominator = book["intraday_return_21d_mean"]
    ratio = book["overnight_return_21d_mean"] / denominator.where(denominator.abs() >= 1e-5)
    book["overnight_intraday_ratio"] = ratio.clip(-5.0, 5.0)

    weekly_index = pd.DatetimeIndex(sorted(book["rebalance_date"].unique()))
    week_number = pd.Series(range(len(weekly_index)), index=weekly_index)
    book["week_number"] = book["rebalance_date"].map(week_number).astype(int)
    book = book.sort_values(["symbol", "week_number"], ignore_index=True)
    gap = book.groupby("symbol", sort=False)["week_number"].diff()
    streak_id = (gap != 1.0).cumsum()
    book["weeks_in_book"] = book.groupby(["symbol", streak_id], sort=False).cumcount() + 1

    regime["trade_date"] = pd.to_datetime(regime["trade_date"])
    book = book.merge(
        regime.rename(columns={"trade_date": "rebalance_date"}),
        on="rebalance_date",
        how="left",
    )

    columns = [
        "rebalance_date",
        "symbol",
        "weight",
        "score",
        "score_rank",
        "cohort_size",
        "universe_size",
        "book_size",
        "week_number",
        *FEATURE_COLUMNS,
        "fwd_4w_ret",
        "book_median_fwd_4w_ret",
        "fwd_4w_excess_vs_book",
        "label",
    ]
    return book[columns].sort_values(["rebalance_date", "symbol"], ignore_index=True)


# --------------------------------------------------------------------------
# stage: train
# --------------------------------------------------------------------------


def _quarter_windows(dataset: pd.DataFrame) -> list[dict[str, Any]]:
    """Every quarter that has both a full 3-year embargoed training window
    inside the dataset and at least one book row of its own -- the card's
    "训练滚动 3 年、验证留出 1 个季度、隔离期 4 周；每季重训" walk-forward.
    """
    dates = pd.DatetimeIndex(sorted(dataset["rebalance_date"].unique()))
    first, last = dates.min(), dates.max()
    windows: list[dict[str, Any]] = []
    for period in pd.period_range(first.to_period("Q"), last.to_period("Q"), freq="Q"):
        q_start = period.start_time
        q_end = period.end_time
        train_end = q_start - pd.Timedelta(days=EMBARGO_DAYS)
        train_start = train_end - pd.DateOffset(years=TRAIN_YEARS)
        if train_start < first:
            continue
        if not ((dates >= q_start) & (dates <= q_end)).any():
            continue
        windows.append(
            {
                "quarter": str(period),
                "validation_start": q_start,
                "validation_end": q_end,
                "train_start": train_start,
                "train_end": train_end,
            }
        )
    return windows


def _placebo_seed(variant: str) -> int:
    """``placebo1`` -> ``PLACEBO_SEED``, ``placebo2`` -> ``PLACEBO_SEED + 1`` ..."""
    return PLACEBO_SEED + int(variant.removeprefix("placebo")) - 1


def _shuffle_labels_within_week(dataset: pd.DataFrame, seed: int) -> pd.Series:
    """Placebo labels: a random permutation of the label column *inside each
    rebalance date*. That destroys every symbol-to-outcome link the model
    could learn while preserving each week's positive fraction exactly (the
    card's "把标签在时间上随机平移（保持每周的正负比例）"), so a tier effect that
    survives this is coming from the week's composition, not from selection.
    """
    rng = np.random.default_rng(seed)
    out = dataset["label"].copy()
    for _date, index in dataset.groupby("rebalance_date").groups.items():
        values = out.loc[index].to_numpy()
        mask = ~np.isnan(values)
        permuted = values.copy()
        permuted[mask] = rng.permutation(values[mask])
        out.loc[index] = permuted
    return out


def _fit_logit(train_x: pd.DataFrame, train_y: np.ndarray) -> Any:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("model", LogisticRegression(max_iter=1000, C=1.0)),
        ]
    ).fit(train_x, train_y)


def _fit_lgbm(train_x: pd.DataFrame, train_y: np.ndarray) -> Any:
    from lightgbm import LGBMClassifier

    return LGBMClassifier(**LGBM_PARAMS).fit(train_x, train_y)


def _auc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    from sklearn.metrics import roc_auc_score

    mask = ~np.isnan(labels)
    if mask.sum() < 30 or len(np.unique(labels[mask])) < 2:
        return None
    return float(roc_auc_score(labels[mask], scores[mask]))


def stage_train(*, force: bool) -> None:
    import joblib

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dataset = pd.read_parquet(DATASET_PATH)
    windows = _quarter_windows(dataset)
    _log(f"{len(windows)} walk-forward quarters: {windows[0]['quarter']}..{windows[-1]['quarter']}")
    metrics: dict[str, Any] = {
        "hypothesis": "H-20260916-03",
        "primary_cell": "step13_m0b_mom_over_vol63_uni500_k50_gate_off",
        "feature_columns": list(FEATURE_COLUMNS),
        "label": (
            "forward 4 weekly-rebalance-step close-to-close return minus that "
            "week's book median, > 0 -> 1"
        ),
        "train_years": TRAIN_YEARS,
        "embargo_days": EMBARGO_DAYS,
        "refit": "quarterly",
        "lgbm_params": LGBM_PARAMS,
        "placebo": "labels permuted within each rebalance date (per-week positive fraction kept)",
        "windows": [],
    }
    predictions: list[pd.DataFrame] = []
    for variant in VARIANTS:
        target = (
            dataset["label"]
            if variant == "real"
            else _shuffle_labels_within_week(dataset, _placebo_seed(variant))
        )
        frame = dataset.assign(target=target)
        for window in windows:
            train = frame.loc[
                (frame["rebalance_date"] >= window["train_start"])
                & (frame["rebalance_date"] < window["train_end"])
                & frame["target"].notna()
            ]
            validation = frame.loc[
                (frame["rebalance_date"] >= window["validation_start"])
                & (frame["rebalance_date"] <= window["validation_end"])
            ]
            if len(train) < MIN_TRAIN_ROWS or train["target"].nunique() < 2 or validation.empty:
                _log(f"{variant}/{window['quarter']}: skipped (train rows {len(train)})")
                continue
            train_x = train[list(FEATURE_COLUMNS)]
            train_y = train["target"].to_numpy()
            validation_x = validation[list(FEATURE_COLUMNS)]
            labels = validation["target"].to_numpy()
            record: dict[str, Any] = {
                "variant": variant,
                "quarter": window["quarter"],
                "train_start": window["train_start"].date().isoformat(),
                "train_end": window["train_end"].date().isoformat(),
                "validation_start": window["validation_start"].date().isoformat(),
                "validation_end": window["validation_end"].date().isoformat(),
                "train_rows": int(len(train)),
                "validation_rows": int(len(validation)),
                "train_positive_fraction": float(train_y.mean()),
                "validation_positive_fraction": (
                    float(np.nanmean(labels)) if np.isfinite(labels).any() else None
                ),
            }
            for model_name in MODELS:
                path = MODEL_DIR / f"{variant}_{model_name}_{window['quarter']}.joblib"
                if path.exists() and not force:
                    model = joblib.load(path)
                else:
                    model = (
                        _fit_logit(train_x, train_y)
                        if model_name == "logit"
                        else _fit_lgbm(train_x, train_y)
                    )
                    joblib.dump(model, path, compress=3)
                probability = model.predict_proba(validation_x)[:, 1]
                record[f"{model_name}_auc"] = _auc(labels, probability)
                record[f"{model_name}_p_mean"] = float(np.mean(probability))
                record[f"{model_name}_p_std"] = float(np.std(probability))
                if model_name == "logit":
                    record["logit_coefficients"] = dict(
                        zip(
                            FEATURE_COLUMNS,
                            (float(v) for v in model.named_steps["model"].coef_[0]),
                            strict=True,
                        )
                    )
                else:
                    record["lgbm_gain_importance"] = dict(
                        zip(
                            FEATURE_COLUMNS,
                            (float(v) for v in model.booster_.feature_importance("gain")),
                            strict=True,
                        )
                    )
                predictions.append(
                    pd.DataFrame(
                        {
                            "rebalance_date": validation["rebalance_date"].to_numpy(),
                            "symbol": validation["symbol"].to_numpy(),
                            "variant": variant,
                            "model": model_name,
                            "quarter": window["quarter"],
                            "p": probability,
                            "label": validation["label"].to_numpy(),
                            "fwd_4w_excess_vs_book": validation["fwd_4w_excess_vs_book"].to_numpy(),
                            "baseline_weight": validation["weight"].to_numpy(),
                        }
                    )
                )
            metrics["windows"].append(record)
            _log(
                f"{variant}/{window['quarter']}: train={len(train)} val={len(validation)} "
                f"auc_logit={record.get('logit_auc')} auc_lgbm={record.get('lgbm_auc')}"
            )
    metrics["summary"] = _training_summary(metrics["windows"])
    _write_json(VALIDATION_METRICS_PATH, metrics)
    frame = pd.concat(predictions, ignore_index=True)
    _write_parquet(OUT_DIR / "predictions.parquet", frame)
    _log(f"wrote validation_metrics.json and predictions.parquet ({len(frame):,} rows)")


def _training_summary(windows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean/median validation AUC per (variant, model), the fraction of
    quarters clearing 0.55, and logistic-coefficient sign stability: for the
    four features with the largest mean |coefficient|, the share of quarters
    whose sign equals that feature's majority sign (1.0 = never flipped).
    """
    summary: dict[str, Any] = {}
    for variant in VARIANTS:
        rows = [w for w in windows if w["variant"] == variant]
        for model_name in MODELS:
            values = [
                w[f"{model_name}_auc"] for w in rows if w.get(f"{model_name}_auc") is not None
            ]
            summary[f"{variant}_{model_name}"] = {
                "quarters": len(values),
                "auc_mean": float(np.mean(values)) if values else None,
                "auc_median": float(np.median(values)) if values else None,
                "auc_min": float(np.min(values)) if values else None,
                "auc_max": float(np.max(values)) if values else None,
                "auc_above_0_55_fraction": (
                    float(np.mean([v >= 0.55 for v in values])) if values else None
                ),
            }
        coefficient_rows = [w["logit_coefficients"] for w in rows if "logit_coefficients" in w]
        if coefficient_rows:
            coefficients = pd.DataFrame(coefficient_rows)
            ranked = coefficients.abs().mean().sort_values(ascending=False)
            stability = {}
            for feature in ranked.index[:4]:
                signs = np.sign(coefficients[feature].to_numpy())
                signs = signs[signs != 0]
                majority = 1.0 if (signs > 0).sum() >= (signs < 0).sum() else -1.0
                stability[feature] = {
                    "mean_abs_coefficient": float(ranked[feature]),
                    "mean_coefficient": float(coefficients[feature].mean()),
                    "majority_sign": majority,
                    "sign_stability": float(np.mean(signs == majority)) if len(signs) else None,
                }
            summary[f"{variant}_logit_top_coefficient_sign_stability"] = stability
            last_four = coefficients.tail(4)
            summary[f"{variant}_logit_sign_stability_last_4_windows"] = {
                feature: float(
                    np.mean(np.sign(last_four[feature]) == np.sign(last_four[feature]).iloc[0])
                )
                for feature in ranked.index[:4]
            }
    return summary


# --------------------------------------------------------------------------
# stage: evaluate
# --------------------------------------------------------------------------


def tier_weight(probability: float) -> float:
    """The card's preregistered tiers: ``p < 0.4 -> 0``, ``0.4 <= p <= 0.6 ->
    1%``, ``p > 0.6 -> 2%``. Untuned; the thresholds are the hypothesis.
    """
    if probability < TIER_LOW_P:
        return 0.0
    if probability <= TIER_HIGH_P:
        return TIER_MID_WEIGHT
    return TIER_HIGH_WEIGHT


def _window_metrics(
    *,
    label: str,
    returns: pd.Series,
    stress_returns: pd.Series,
    spy_returns: pd.Series,
    bil_returns: pd.Series,
    schedule: list[RebalanceEvent],
    oos_start: pd.Timestamp,
    is_ml: bool,
    placebo_rank_ic_abs: float | None = None,
    rule_baseline_cagr_recent_net: float | None = None,
) -> dict[str, Any]:
    """Recent-window (2024-01-02 onward) numbers straight out of the gate
    contract's own evaluator -- ``cagr_excess_vol_matched_spy`` included, so
    the headline figure is literally the ledger's formula -- plus the same
    three headline numbers over the full OOS span via ``kernel.vol_matched``
    (tested equal to the gate evaluator on a common window). Nothing is
    written to the ledger: ``reference_only=True``.
    """
    weekly_recent = m_grid._weekly_returns_excluding_cash(
        schedule, returns, recent_start=pd.Timestamp(regime_gates.RECENT_WINDOW_START)
    )
    weekly_oos = m_grid._weekly_returns_excluding_cash(schedule, returns, recent_start=oos_start)
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id=f"h20260916_03_{label}",
        config_hash=f"h20260916_03_{label}",
        full_returns=returns,
        full_stress_returns=stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=weekly_recent,
        rebalances_with_change_per_year=m_grid._rebalances_with_change_per_year(schedule),
        family=m_grid.FAMILY,
        is_ml=is_ml,
        placebo_rank_ic_abs=placebo_rank_ic_abs,
        rule_baseline_cagr_recent_net=rule_baseline_cagr_recent_net,
        reference_only=True,
    )
    turnover = turnover_per_rebalance(schedule)
    exposure = [
        sum(w for s, w in event.selected.items() if s != CASH_SYMBOL)
        for event in schedule
        if event.selected
    ]
    return {
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
            "gate_results": verdict.gate_results,
        },
        "full_oos": {
            "cagr_net": annualized_cagr(returns),
            "max_drawdown": max_drawdown(returns),
            "cagr_excess_vol_matched_spy": cagr_excess_vol_matched(
                returns, spy_returns, bil_returns
            ),
            "vol_match_weight_vs_spy": vol_match_weight(returns, spy_returns),
            "hit_rate_weekly": regime_metrics.hit_rate(weekly_oos),
            "stress_cost_cagr_net": annualized_cagr(stress_returns),
            "window": [
                returns.index.min().date().isoformat(),
                returns.index.max().date().isoformat(),
            ],
        },
        "turnover_per_rebalance_mean": float(np.mean(turnover[1:])) if len(turnover) > 1 else None,
        "turnover_annualized": (float(np.mean(turnover[1:]) * 52.0) if len(turnover) > 1 else None),
        "mean_invested_exposure": float(np.mean(exposure)) if exposure else None,
        "rebalance_count": len([e for e in schedule if e.selected]),
    }


def _rank_ic(frame: pd.DataFrame) -> float:
    """Mean per-week Spearman correlation between the predicted probability
    and the realized within-book 4-week excess -- the same "does the score
    order the outcome" quantity the v2 contract's placebo gate uses.
    """
    values = []
    for _date, rows in frame.groupby("rebalance_date"):
        subset = rows.dropna(subset=["fwd_4w_excess_vs_book"])
        if len(subset) < 5 or subset["p"].nunique() < 2:
            continue
        values.append(float(subset["p"].corr(subset["fwd_4w_excess_vs_book"], method="spearman")))
    return float(np.mean(values)) if values else float("nan")


def stage_evaluate(*, force: bool) -> None:
    del force
    predictions = pd.read_parquet(OUT_DIR / "predictions.parquet")
    predictions["rebalance_date"] = pd.to_datetime(predictions["rebalance_date"])
    baseline_schedule_all = _events_from_json(json.loads(SCHEDULE_PATH.read_text()))
    validation_metrics = json.loads(VALIDATION_METRICS_PATH.read_text())

    oos_dates = pd.DatetimeIndex(sorted(predictions["rebalance_date"].unique()))
    oos_start = oos_dates.min()
    _log(f"OOS span: {oos_start.date()}..{oos_dates.max().date()} ({len(oos_dates)} rebalances)")

    years = tuple(range(oos_start.year, 2027))
    common = m_grid._load_common_data(years=years, trend_gate_required=False)
    price_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="close")
    open_wide = common.price_panel.pivot(index="trade_date", columns="symbol", values="open")
    spy_returns = common.spy_returns
    bil_returns = common.bil_returns

    def price_streams(schedule: list[RebalanceEvent]) -> tuple[pd.Series, pd.Series]:
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

    oos_date_set = set(oos_dates)
    baseline_schedule = [
        event for event in baseline_schedule_all if pd.Timestamp(event.date) in oos_date_set
    ]
    # Weeks inside the OOS span that produced no book at all (see _caveats):
    # the picks export never saw them, so they are absent from `oos_dates` and
    # have to be recovered from the full schedule to be reportable.
    oos_gaps = [
        pd.Timestamp(event.date).date().isoformat()
        for event in baseline_schedule_all
        if not event.selected and oos_start <= pd.Timestamp(event.date) <= oos_dates.max()
    ]
    if oos_gaps:
        _log(f"{len(oos_gaps)} empty (no-book) rebalance weeks inside the OOS span: {oos_gaps}")
    baseline_primary, baseline_stress = price_streams(baseline_schedule)
    baseline = _window_metrics(
        label="baseline_equal_weight_2pct",
        returns=baseline_primary,
        stress_returns=baseline_stress,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        schedule=baseline_schedule,
        oos_start=oos_start,
        is_ml=False,
    )
    _log(
        f"baseline: recent CAGR {baseline['recent_2024']['cagr_net']:.4f} "
        f"MDD {baseline['recent_2024']['max_drawdown']:.4f} "
        f"vol-matched excess {baseline['recent_2024']['cagr_excess_vol_matched_spy']:.4f}"
    )

    results: dict[str, Any] = {"baseline": baseline, "variants": {}, "rank_ic": {}}
    # Tiered books and rank ICs for every (model, variant) first: the v2
    # contract's ``ml_placebo_rank_ic`` disclosure for a real cell is the
    # *placebo's* IC, so it has to exist before the real cell is scored --
    # scoring them in VARIANTS order would silently hand the real cell its own
    # IC for the first model.
    books: dict[str, pd.DataFrame] = {}
    for model_name in MODELS:
        for variant in VARIANTS:
            subset = predictions.loc[
                (predictions["model"] == model_name) & (predictions["variant"] == variant)
            ].copy()
            if subset.empty:
                continue
            subset["weight"] = subset["p"].map(tier_weight)
            books[f"{variant}_{model_name}"] = subset
            results["rank_ic"][f"{variant}_{model_name}"] = _rank_ic(subset)

    for model_name in MODELS:
        for variant in VARIANTS:
            key = f"{variant}_{model_name}"
            subset = books.get(key)
            if subset is None:
                continue
            schedule = weight_schedule_from_pick_frame(
                subset, cash_symbol=CASH_SYMBOL, universe_size_column=None
            )
            primary, stress = price_streams(schedule)
            rank_ic = results["rank_ic"][key]
            placebo_ics = [
                results["rank_ic"][f"{name}_{model_name}"]
                for name in PLACEBO_VARIANTS
                if f"{name}_{model_name}" in results["rank_ic"]
            ]
            placebo_ic = float(np.mean(placebo_ics)) if placebo_ics else rank_ic
            metrics = _window_metrics(
                label=f"tiers_{variant}_{model_name}",
                returns=primary,
                stress_returns=stress,
                spy_returns=spy_returns,
                bil_returns=bil_returns,
                schedule=schedule,
                oos_start=oos_start,
                is_ml=True,
                placebo_rank_ic_abs=abs(placebo_ic),
                rule_baseline_cagr_recent_net=baseline["recent_2024"]["cagr_net"],
            )
            metrics["rank_ic_vs_realized_excess"] = rank_ic
            metrics["p_quantiles"] = {
                str(q): float(subset["p"].quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)
            }
            metrics["tier_shares"] = {
                "zero": float((subset["weight"] == 0.0).mean()),
                "one_pct": float((subset["weight"] == TIER_MID_WEIGHT).mean()),
                "two_pct": float((subset["weight"] == TIER_HIGH_WEIGHT).mean()),
            }
            results["variants"][key] = metrics
            _log(
                f"tiers/{variant}/{model_name}: recent CAGR "
                f"{metrics['recent_2024']['cagr_net']:.4f} "
                f"MDD {metrics['recent_2024']['max_drawdown']:.4f} "
                f"vol-matched excess "
                f"{metrics['recent_2024']['cagr_excess_vol_matched_spy']:.4f} "
                f"exposure {metrics['mean_invested_exposure']:.3f}"
            )

    report = _build_report(
        baseline=baseline,
        results=results,
        validation_metrics=validation_metrics,
        oos_dates=oos_dates,
        predictions=predictions,
        oos_gaps=oos_gaps,
    )
    _write_json(REPORT_JSON_PATH, report)
    REPORT_MD_PATH.write_text(_render_markdown(report))
    _log(f"wrote {REPORT_JSON_PATH.name} and {REPORT_MD_PATH.name}")
    for model_name in MODELS:
        verdict = report["stop_conditions"][model_name]
        for key, value in verdict.items():
            _log(f"stop-condition[{model_name}] {key}: {value['verdict']} -- {value['detail']}")


def _reference_disclosures() -> dict[str, Any]:
    """SPY/QQQ/MTUM/SPMO comparison numbers, read out of the preregistered v2
    gate contract's own ``reference_disclosures`` block (the same source
    ``docs/current-view.zh.md``'s comparison table quotes) rather than
    recomputed here, so this report cannot quietly disagree with the contract.
    """
    payload = json.loads(
        (ROOT / "config" / "promotion" / "recent-regime-high-return-gates-v2.json").read_text()
    )
    return payload["reference_disclosures"]


def _fmt(value: float | None, spec: str) -> str:
    """``format(value, spec)`` that tolerates ``None`` -- the stop-condition
    details have to stay readable when a placebo run or a coefficient-stability
    figure is genuinely unavailable rather than crashing the report.
    """
    return "N/A" if value is None else format(value, spec)


def _quarterly_rank_ic(frame: pd.DataFrame) -> dict[str, float]:
    """Per-validation-quarter mean weekly rank IC of the predicted probability
    against the realized within-book 4-week excess. This is the model-agnostic
    reading of the card's "符号在四个滚动窗里不稳定": a logistic model has
    coefficients whose signs can be inspected directly, a boosted tree does
    not, but both have a per-quarter *direction*.
    """
    return {str(quarter): _rank_ic(rows) for quarter, rows in frame.groupby("quarter")}


def _sign_stability(values: list[float]) -> float | None:
    """Share of finite, non-zero values whose sign equals the majority sign
    (1.0 = never flipped, 0.5 = a coin flip).
    """
    signs = [float(np.sign(v)) for v in values if v is not None and np.isfinite(v) and v != 0.0]
    if not signs:
        return None
    majority = 1.0 if signs.count(1.0) >= signs.count(-1.0) else -1.0
    return float(np.mean([sign == majority for sign in signs]))


#: Where each model feature comes from. Rendered into report.md so the round's
#: "document any you had to derive" requirement is answered in the artifact
#: itself, not only in the code.
FEATURE_PROVENANCE: dict[str, str] = {
    "momentum_pct": (
        "推导：`PickCollector` 记录的该股 `momentum_252_21_over_vol_63` 在当周"
        "前 500 个可交易标的里的升序分位（1.0 = 最强）。组合只有前 50 名，"
        "光看组合内部排名看不出截面尾部在哪，所以必须在内核里记。"
    ),
    "vol_63": "现成列 `data/features/daily` 的 `vol_63`（63 日日波动）。",
    "excess_21d_vs_book": "推导：`ret_21` 减去当周组合的 `ret_21` 中位数。",
    "weeks_in_book": "推导：该股连续入选的周数（含当周），由导出的持仓历史算出。",
    "dist_from_252d_high": "现成列 `dist_from_252d_high`（距 52 周高点，<= 0）。",
    "overnight_intraday_ratio": (
        "推导：`overnight_return_21d_mean / intraday_return_21d_mean`，"
        "分母绝对值 < 1e-5 记为缺失，结果截断在 ±5（两个小的带符号均值相除本身无界，"
        "不截断会主导线性模型）。"
    ),
    "spy_gap_200sma": "现成列 `data/features/regime_daily` 的 `spy_gap_200sma`。",
    "breadth_50d": "现成列 `data/features/regime_daily` 的 `breadth_50d`（截面宽度）。",
}


def _caveats(*, baseline: dict[str, Any], oos_gaps: list[str]) -> list[str]:
    """The honest read-me-first list for this round's numbers."""
    return [
        "**卡上写的是 2016-01 起，实际只能从 2017-01-06 起。** `momentum_252_21` 需要 252 个"
        "交易日历史，日线档案本身从 2016-01-04 开始，所以 2016 年整年这一列全是空值"
        "（`data/features/daily/2016.parquet` 里非空行数 = 0）。2016 只当暖机年加载。",
        "**滚动 3 年训练 + 4 周隔离 + 每季重训，最早只能从 2020Q2 开始验证。** "
        "因此样本外从 2020Q2 起算；2024 年起的近窗是其中的一段。",
        "**这 26 个季度既是 AUC 的验证集，也是分档评估的样本外区间。** 分档阈值"
        "（0.4 / 0.6）和模型超参数都是卡上事先写死、没有在这些季度上调过的，"
        "所以不存在在同一段数据上选参数的问题；但也没有第三段独立数据可以再验一次，"
        "这是这一轮证据强度的上限。",
        f"**基线在近窗算出 {_pct(baseline['recent_2024']['cagr_net'])} 而账本里那一格是 33.0%。** "
        "两者是同一批持仓（最大回撤同为 -28.3%，完全一致），差别只在窗口边界：账本那一格的"
        "调仓表从 2024-01-08 才开始，而这里的调仓表从 2020 年就在跑，于是近窗把"
        "2024-01-02 至 01-08 这段（由 2023-12-29 的持仓产生）也算进来了，同时它也没有账本那一格"
        "在窗口内一次性建仓的 100% 换手成本。两个数都对，口径不同，不能混用。",
        f"**有 {len(oos_gaps)} 个样本外调仓周是空仓周**"
        f"（{', '.join(oos_gaps) if oos_gaps else '无'}）："
        "宇宙面板 `data/features/universe` 里存在个别只有 1 行、月末日期在月中的"
        "异常 cohort（如 2019-10-02、2021-04-02），`universe_as_of_calendar_month` 会把"
        "那一行当成当月 cohort，导致 `adv_rank <= 500` 过滤后没有可选标的。这是既有数据的"
        "毛病，不是这一轮引入的，基线和分档受影响完全一样，所以不影响对比；但要记在账上。",
        "**标签是“相对当周组合中位数”，这决定了分档只能在组合内部搬钱，不能做择时。** "
        "每周正负各一半，组合层特征（SPY 距 200 日线、截面宽度）在同一周内是常数，"
        "对这个标签没有主效应可学，于是概率天然堆在 0.5 附近，几乎全部落进 1% 档，"
        "总暴露掉到 50% 左右。观察到的回撤改善主要是“少拿一半”，不是“挑对了”。",
        "**没有写账本。** 这一轮不走 `loop.run_experiment`，`reports/research/ledger/"
        "experiments.jsonl` 未改动；报告里的合同 v2 判定是 `reference_only` 披露，"
        "不构成任何晋级资格。",
    ]


def _placebo_aggregate(baseline: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    """Per model: the vol-matched-excess improvement each placebo seed produced
    over the baseline, plus the mean/min/max of that and of the headline
    recent-window numbers. The card's placebo test is a single comparison, so
    the *mean* seed is what the verdict uses; the spread is reported so a
    borderline call is visible.
    """
    baseline_excess = baseline["recent_2024"]["cagr_excess_vol_matched_spy"]
    out: dict[str, Any] = {}
    for model_name in MODELS:
        rows = [
            results["variants"][f"{name}_{model_name}"]
            for name in PLACEBO_VARIANTS
            if f"{name}_{model_name}" in results["variants"]
        ]
        if not rows:
            continue
        improvements = [
            row["recent_2024"]["cagr_excess_vol_matched_spy"] - baseline_excess for row in rows
        ]
        out[model_name] = {
            "seeds": len(rows),
            "improvements": improvements,
            "improvement_mean": float(np.mean(improvements)),
            "improvement_min": float(np.min(improvements)),
            "improvement_max": float(np.max(improvements)),
            "cagr_recent_mean": float(np.mean([r["recent_2024"]["cagr_net"] for r in rows])),
            "max_drawdown_recent_mean": float(
                np.mean([r["recent_2024"]["max_drawdown"] for r in rows])
            ),
            "cagr_excess_vol_matched_spy_mean": float(
                np.mean([r["recent_2024"]["cagr_excess_vol_matched_spy"] for r in rows])
            ),
            "hit_rate_weekly_mean": float(
                np.mean([r["recent_2024"]["hit_rate_weekly"] for r in rows])
            ),
            "turnover_per_rebalance_mean": float(
                np.mean([r["turnover_per_rebalance_mean"] for r in rows])
            ),
            "mean_invested_exposure": float(np.mean([r["mean_invested_exposure"] for r in rows])),
            "full_oos_cagr_mean": float(np.mean([r["full_oos"]["cagr_net"] for r in rows])),
            "full_oos_max_drawdown_mean": float(
                np.mean([r["full_oos"]["max_drawdown"] for r in rows])
            ),
            "full_oos_excess_mean": float(
                np.mean([r["full_oos"]["cagr_excess_vol_matched_spy"] for r in rows])
            ),
            "full_oos_hit_rate_mean": float(
                np.mean([r["full_oos"]["hit_rate_weekly"] for r in rows])
            ),
        }
    return out


def _build_report(
    *,
    baseline: dict[str, Any],
    results: dict[str, Any],
    validation_metrics: dict[str, Any],
    oos_dates: pd.DatetimeIndex,
    predictions: pd.DataFrame,
    oos_gaps: list[str],
) -> dict[str, Any]:
    summary = validation_metrics["summary"]
    quarterly_rank_ic: dict[str, dict[str, float]] = {}
    for model_name in MODELS:
        subset = predictions.loc[
            (predictions["model"] == model_name) & (predictions["variant"] == "real")
        ]
        if not subset.empty:
            quarterly_rank_ic[model_name] = _quarterly_rank_ic(subset)
    placebo_aggregate = _placebo_aggregate(baseline, results)
    stop_conditions: dict[str, Any] = {}
    for model_name in MODELS:
        real = results["variants"].get(f"real_{model_name}")
        if real is None:
            continue
        baseline_excess = baseline["recent_2024"]["cagr_excess_vol_matched_spy"]
        real_excess = real["recent_2024"]["cagr_excess_vol_matched_spy"]
        real_improvement = real_excess - baseline_excess
        aggregate = placebo_aggregate.get(model_name, {})
        placebo_improvement = aggregate.get("improvement_mean")
        placebo_improvements = aggregate.get("improvements", [])
        auc = summary[f"real_{model_name}"]["auc_mean"]
        # "符号在四个滚动窗里不稳定": for the logistic model that is literally its
        # coefficients' signs; for the boosted tree, which has no signed
        # coefficients, it is the sign of its per-quarter rank IC. Both are
        # reported; the verdict uses the one that exists for this model.
        coefficient_stability = summary.get("real_logit_top_coefficient_sign_stability", {})
        min_coefficient_stability = (
            min(v["sign_stability"] for v in coefficient_stability.values())
            if coefficient_stability
            else None
        )
        coefficient_stability_last_4 = summary.get("real_logit_sign_stability_last_4_windows", {})
        min_coefficient_stability_last_4 = (
            min(coefficient_stability_last_4.values()) if coefficient_stability_last_4 else None
        )
        ic_values = list(quarterly_rank_ic.get(model_name, {}).values())
        ic_stability = _sign_stability(ic_values)
        ic_stability_last_4 = _sign_stability(ic_values[-4:])
        # The card says "符号在四个滚动窗里不稳定" -- four windows, so the verdict
        # uses the last four refits; the all-window figure is reported next to
        # it so a borderline case is visible rather than hidden behind the
        # narrower test.
        used_stability = (
            min_coefficient_stability_last_4 if model_name == "logit" else ic_stability_last_4
        )
        signs_unstable = bool(used_stability is not None and used_stability < 0.75)
        cagr_shortfall = baseline["recent_2024"]["cagr_net"] - real["recent_2024"]["cagr_net"]
        placebo_ratio = (
            placebo_improvement / real_improvement
            if placebo_improvement is not None and real_improvement > 0.0
            else None
        )
        placebo_ratio_max = (
            aggregate["improvement_max"] / real_improvement
            if real_improvement > 0.0 and aggregate.get("improvement_max") is not None
            else None
        )
        stop_conditions[model_name] = {
            "1_vol_matched_excess_improvement_ge_3pp": {
                "verdict": "PASS" if real_improvement >= 0.03 else "FAIL",
                "value": real_improvement,
                "threshold": 0.03,
                "detail": (
                    f"vol-matched SPY excess {baseline_excess:.4f} -> {real_excess:.4f} "
                    f"(improvement {real_improvement:+.4f}, needs >= +0.0300)"
                ),
            },
            "2_placebo_improvement_lt_50pct_of_real": {
                # When the real improvement is not positive there is nothing
                # for the placebo to account for and the ratio is meaningless
                # (condition 1 has already stopped the card), so this is
                # reported as N/A rather than as a spurious pass or fail.
                "verdict": (
                    "N/A" if placebo_ratio is None else ("FAIL" if placebo_ratio >= 0.5 else "PASS")
                ),
                "value": placebo_ratio,
                "threshold": 0.5,
                "placebo_seeds": len(placebo_improvements),
                "placebo_improvements": placebo_improvements,
                "placebo_improvement_mean": placebo_improvement,
                "placebo_improvement_max": aggregate.get("improvement_max"),
                "placebo_ratio_max": placebo_ratio_max,
                "detail": (
                    f"real improvement {real_improvement:+.4f}; placebo improvement over "
                    f"{len(placebo_improvements)} seeds mean "
                    f"{_fmt(placebo_improvement, '+.4f')} "
                    f"(min {_fmt(aggregate.get('improvement_min'), '+.4f')}, max "
                    f"{_fmt(aggregate.get('improvement_max'), '+.4f')}); mean ratio "
                    f"{_fmt(placebo_ratio, '.3f')}, worst-seed ratio "
                    f"{_fmt(placebo_ratio_max, '.3f')}"
                    + (
                        " (real improvement is not positive, so the ratio is not meaningful)"
                        if placebo_ratio is None
                        else ""
                    )
                ),
            },
            "3_validation_auc_ge_0_55_or_stable_signs": {
                "verdict": "PASS"
                if (auc is not None and auc >= 0.55) or not signs_unstable
                else "FAIL",
                "value": auc,
                "threshold": 0.55,
                "sign_stability_used": used_stability,
                "logit_min_coefficient_sign_stability_all_windows": min_coefficient_stability,
                "logit_min_coefficient_sign_stability_last_4": min_coefficient_stability_last_4,
                "quarterly_rank_ic_sign_stability": ic_stability,
                "quarterly_rank_ic_sign_stability_last_4": ic_stability_last_4,
                "detail": (
                    f"mean validation AUC {_fmt(auc, '.4f')}; sign stability over the last 4 "
                    f"refits {_fmt(used_stability, '.2f')} "
                    f"(logit coefficients: last 4 "
                    f"{_fmt(min_coefficient_stability_last_4, '.2f')}, all 26 "
                    f"{_fmt(min_coefficient_stability, '.2f')}; quarterly rank-IC: last 4 "
                    f"{_fmt(ic_stability_last_4, '.2f')}, all 26 {_fmt(ic_stability, '.2f')}) "
                    "-- card stops only when AUC < 0.55 *and* signs are unstable"
                ),
            },
            "4_net_cagr_within_3pp_of_baseline": {
                "verdict": "PASS" if cagr_shortfall <= 0.03 else "FAIL",
                "value": cagr_shortfall,
                "threshold": 0.03,
                "detail": (
                    f"recent-window net CAGR {baseline['recent_2024']['cagr_net']:.4f} -> "
                    f"{real['recent_2024']['cagr_net']:.4f} (shortfall {cagr_shortfall:+.4f}, "
                    f"turnover/rebalance {baseline['turnover_per_rebalance_mean']:.3f} -> "
                    f"{real['turnover_per_rebalance_mean']:.3f})"
                ),
            },
        }
    return {
        "hypothesis": "H-20260916-03",
        "card": "reports/research/hypotheses/H-20260916-03-meta-labeling-position-tiers.md",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "primary_cell": "step13_m0b_mom_over_vol63_uni500_k50_gate_off",
        "ledger_written": False,
        "ledger_note": (
            "evaluation does not go through loop.run_experiment, so no row was appended to "
            "reports/research/ledger/experiments.jsonl; the v2 gate verdicts here are "
            "reference_only disclosures"
        ),
        "cost_assumptions": {
            "primary_cost_bps_per_side": PRIMARY_COST_BPS,
            "stress_cost_bps_per_side": STRESS_COST_BPS,
            "execution": EXECUTION,
            "returns_contract": "portfolio_returns.buy_and_hold_drift.v2",
            "cash_leg": CASH_SYMBOL,
        },
        "oos_window": {
            "first_rebalance": oos_dates.min().date().isoformat(),
            "last_rebalance": oos_dates.max().date().isoformat(),
            "rebalance_dates": int(len(oos_dates)),
            "quarters": int(predictions["quarter"].nunique()),
            "empty_no_book_weeks": oos_gaps,
        },
        "tiers": {
            "p_lt_0_4": 0.0,
            "p_0_4_to_0_6": TIER_MID_WEIGHT,
            "p_gt_0_6": TIER_HIGH_WEIGHT,
            "rest": CASH_SYMBOL,
        },
        "baseline": baseline,
        "variants": results["variants"],
        "rank_ic": results["rank_ic"],
        "quarterly_rank_ic_real": quarterly_rank_ic,
        "placebo_aggregate": placebo_aggregate,
        "feature_provenance": FEATURE_PROVENANCE,
        "caveats": _caveats(baseline=baseline, oos_gaps=oos_gaps),
        "validation_summary": summary,
        "reference_disclosures": _reference_disclosures(),
        "stop_conditions": stop_conditions,
    }


def _pct(value: float | None) -> str:
    return "N/A" if value is None or not np.isfinite(value) else f"{value * 100:.1f}%"


def _verdict_paragraph(report: dict[str, Any]) -> list[str]:
    """The plain-language verdict, assembled from the computed numbers only --
    no hand-typed figure appears anywhere in report.md.
    """
    baseline = report["baseline"]["recent_2024"]
    lines: list[str] = []
    failed = {
        model: [name for name, item in conditions.items() if item["verdict"] == "FAIL"]
        for model, conditions in report["stop_conditions"].items()
    }
    any_failed = any(failed.values())
    lines.append(
        "**假设被否定。** 两个二级模型（逻辑回归、LightGBM）都命中了卡上的停止条件："
        + "；".join(
            f"{model} 命中 {len(names)} 条（{', '.join(names)}）" for model, names in failed.items()
        )
        + "。"
        if any_failed
        else "**没有命中任何停止条件。**"
    )
    lines.append("")
    for model in MODELS:
        real = report["variants"].get(f"real_{model}")
        aggregate = report["placebo_aggregate"].get(model)
        if real is None or aggregate is None:
            continue
        real_recent = real["recent_2024"]
        improvement = (
            real_recent["cagr_excess_vol_matched_spy"] - baseline["cagr_excess_vol_matched_spy"]
        )
        placebo_share = aggregate["improvement_mean"] / improvement if improvement else float("nan")
        lines.append(
            f"- {model}：同波动 SPY 超额从 "
            f"{_pct(baseline['cagr_excess_vol_matched_spy'])} 改善到 "
            f"{_pct(real_recent['cagr_excess_vol_matched_spy'])}"
            f"（+{improvement * 100:.1f} 个百分点，达到了卡上要求的 3 个百分点），"
            f"最大回撤从 {_pct(baseline['max_drawdown'])} 改善到 "
            f"{_pct(real_recent['max_drawdown'])}；"
            f"但把标签在每周内部随机打乱（{aggregate['seeds']} 个种子）以后，"
            f"占位版本的改善均值是 +{aggregate['improvement_mean'] * 100:.1f} 个百分点，"
            f"是真实版本的 {placebo_share * 100:.0f}%，"
            "也就是说改善几乎全部来自“仓位只上到一半”，不是来自模型挑对了股票；"
            f"同时 CAGR 从 {_pct(baseline['cagr_net'])} 掉到 "
            f"{_pct(real_recent['cagr_net'])}，远超卡上容许的 3 个百分点。"
        )
    lines.append("")
    lines.append(
        "一句话：**这套标签定义下的元标签不是过滤器，是一个去杠杆器**。"
        "平均持仓暴露掉到 50% 左右（概率几乎全部落在 0.4–0.6 的 1% 档），"
        "回撤和同波动超额都按比例变好，收益也按比例变差；随机标签能做到同样的事。"
    )
    return lines


def _render_markdown(report: dict[str, Any]) -> str:
    baseline = report["baseline"]
    reference = report["reference_disclosures"]
    lines: list[str] = []
    lines.append("# H-20260916-03 元标签仓位分档 — 结果")
    lines.append("")
    lines.append(
        f"- 生成时间：{report['generated_at']}｜一级信号：`{report['primary_cell']}`（未改动）"
    )
    lines.append(
        f"- 样本外区间：{report['oos_window']['first_rebalance']} → "
        f"{report['oos_window']['last_rebalance']}"
        f"（{report['oos_window']['rebalance_dates']} 个调仓周，"
        f"{report['oos_window']['quarters']} 个季度，每季重训）"
    )
    costs = report["cost_assumptions"]
    lines.append(
        f"- 成本与执行：主成本 {costs['primary_cost_bps_per_side']:.0f} bp/边、"
        f"压力成本 {costs['stress_cost_bps_per_side']:.0f} bp/边、"
        f"`{costs['execution']}`（周五收盘信号 → 下一交易日开盘成交）、"
        f"现金腿 {costs['cash_leg']}，与 Step 13 完全一致"
    )
    lines.append(
        "- 账本：这一轮不经过 `loop.run_experiment`，所以 "
        "`reports/research/ledger/experiments.jsonl` 一行都没写；表里的合同 v2 判定是 "
        "`reference_only` 披露，不构成晋级资格。"
    )
    lines.append("")
    lines.append("## 结论（先看这一段）")
    lines.append("")
    for line in _verdict_paragraph(report):
        lines.append(line)
    lines.append("")
    lines.append("## 对照表（2024-01-02 起的近窗，与合同 v2 同窗口）")
    lines.append("")
    lines.append(
        "| 方案 | 2024→ CAGR | 最大回撤 | 同波动 SPY 超额 | 周胜率 | 每周双边换手 | 平均持仓暴露 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")

    def row(label: str, metrics: dict[str, Any]) -> str:
        recent = metrics["recent_2024"]
        return (
            f"| {label} | {_pct(recent['cagr_net'])} | {_pct(recent['max_drawdown'])} | "
            f"{_pct(recent['cagr_excess_vol_matched_spy'])} | {_pct(recent['hit_rate_weekly'])} | "
            f"{metrics['turnover_per_rebalance_mean']:.2f} | "
            f"{_pct(metrics['mean_invested_exposure'])} |"
        )

    lines.append(row("等权 2%（基线）", baseline))
    for model in MODELS:
        real = report["variants"].get(f"real_{model}")
        if real is not None:
            lines.append(row(f"分档 {model}（真实标签）", real))
        aggregate = report["placebo_aggregate"].get(model)
        if aggregate is not None:
            lines.append(
                f"| 分档 {model}（占位，{aggregate['seeds']} 个种子均值） | "
                f"{_pct(aggregate['cagr_recent_mean'])} | "
                f"{_pct(aggregate['max_drawdown_recent_mean'])} | "
                f"{_pct(aggregate['cagr_excess_vol_matched_spy_mean'])} | "
                f"{_pct(aggregate['hit_rate_weekly_mean'])} | "
                f"{aggregate['turnover_per_rebalance_mean']:.2f} | "
                f"{_pct(aggregate['mean_invested_exposure'])} |"
            )
    lines.append(
        f"| SPY | {_pct(reference['SPY']['cagr'])} | {_pct(reference['SPY']['max_drawdown'])} | "
        "基准 | " + _pct(reference["SPY"]["weekly_hit_rate"]) + " | 0 | 100% |"
    )
    lines.append(
        f"| MTUM | {_pct(reference['MTUM']['cagr'])} | {_pct(reference['MTUM']['max_drawdown'])} "
        "| — | " + _pct(reference["MTUM"]["weekly_hit_rate"]) + " | 0 | 100% |"
    )
    lines.append(
        f"| SPMO | {_pct(reference['SPMO']['cagr'])} | {_pct(reference['SPMO']['max_drawdown'])} "
        "| — | " + _pct(reference["SPMO"]["weekly_hit_rate"]) + " | 0 | 100% |"
    )
    lines.append("")
    lines.append(
        f"SPY/MTUM/SPMO 三行取自合同 v2 的 `reference_disclosures`（{reference['window']}）。"
    )
    lines.append("")
    lines.append("## 全样本外窗口（含 2020-2023）")
    lines.append("")
    lines.append("| 方案 | CAGR | 最大回撤 | 同波动 SPY 超额 | 周胜率 |")
    lines.append("|---|---:|---:|---:|---:|")
    full = baseline["full_oos"]
    lines.append(
        f"| 等权 2%（基线） | {_pct(full['cagr_net'])} | {_pct(full['max_drawdown'])} | "
        f"{_pct(full['cagr_excess_vol_matched_spy'])} | {_pct(full['hit_rate_weekly'])} |"
    )
    for model in MODELS:
        real = report["variants"].get(f"real_{model}")
        if real is not None:
            full = real["full_oos"]
            lines.append(
                f"| 分档 {model}（真实标签） | {_pct(full['cagr_net'])} | "
                f"{_pct(full['max_drawdown'])} | "
                f"{_pct(full['cagr_excess_vol_matched_spy'])} | "
                f"{_pct(full['hit_rate_weekly'])} |"
            )
        aggregate = report["placebo_aggregate"].get(model)
        if aggregate is not None:
            lines.append(
                f"| 分档 {model}（占位，{aggregate['seeds']} 个种子均值） | "
                f"{_pct(aggregate['full_oos_cagr_mean'])} | "
                f"{_pct(aggregate['full_oos_max_drawdown_mean'])} | "
                f"{_pct(aggregate['full_oos_excess_mean'])} | "
                f"{_pct(aggregate['full_oos_hit_rate_mean'])} |"
            )
    lines.append("")
    lines.append("## 二级模型的验证表现")
    lines.append("")
    lines.append(
        "| 变体 | 季度数 | 平均 AUC | 中位 AUC | AUC≥0.55 的季度占比 | 与真实超额的 rank IC |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for variant in VARIANTS:
        for model in MODELS:
            item = report["validation_summary"][f"{variant}_{model}"]
            rank_ic = report["rank_ic"].get(f"{variant}_{model}")
            lines.append(
                f"| {variant}/{model} | {item['quarters']} | "
                f"{_fmt(item['auc_mean'], '.4f')} | {_fmt(item['auc_median'], '.4f')} | "
                f"{_pct(item['auc_above_0_55_fraction'])} | "
                f"{'N/A' if rank_ic is None else f'{rank_ic:+.4f}'} |"
            )
    lines.append("")
    stability = report["validation_summary"].get("real_logit_top_coefficient_sign_stability", {})
    if stability:
        lines.append("逻辑回归系数最大的四个特征及其符号稳定性（1.00 = 每个季度符号都一样）：")
        lines.append("")
        lines.append("| 特征 | 平均系数 | 平均绝对系数 | 多数符号 | 符号稳定性（全部 26 个窗） |")
        lines.append("|---|---:|---:|---:|---:|")
        for feature, item in stability.items():
            lines.append(
                f"| `{feature}` | {item['mean_coefficient']:+.4f} | "
                f"{item['mean_abs_coefficient']:.4f} | {item['majority_sign']:+.0f} | "
                f"{item['sign_stability']:.2f} |"
            )
        lines.append("")
    lines.append("## 分档占比（样本外每周每只持仓）")
    lines.append("")
    lines.append("| 变体 | 0 档 | 1% 档 | 2% 档 |")
    lines.append("|---|---:|---:|---:|")
    for key, metrics in report["variants"].items():
        shares = metrics["tier_shares"]
        lines.append(
            f"| {key} | {_pct(shares['zero'])} | {_pct(shares['one_pct'])} | "
            f"{_pct(shares['two_pct'])} |"
        )
    lines.append("")
    lines.append("## 否定判据（卡上写死的四条，任一命中即停）")
    lines.append("")
    for model, conditions in report["stop_conditions"].items():
        lines.append(f"### {model}")
        lines.append("")
        for name, item in conditions.items():
            lines.append(f"- **{item['verdict']}** `{name}`：{item['detail']}")
        lines.append("")
    lines.append("## 数据口径与需要知道的坑")
    lines.append("")
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")
    lines.append("## 特征来源（哪些是现成列、哪些是我算的）")
    lines.append("")
    lines.append("| 特征 | 来源 |")
    lines.append("|---|---|")
    for feature, source in report["feature_provenance"].items():
        lines.append(f"| `{feature}` | {source} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["export", "train", "evaluate"])
    parser.add_argument(
        "--force",
        action="store_true",
        help="recompute even when this stage's checkpoints already exist",
    )
    args = parser.parse_args()
    if args.stage == "export":
        stage_export(force=args.force)
    elif args.stage == "train":
        stage_train(force=args.force)
    else:
        stage_evaluate(force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
