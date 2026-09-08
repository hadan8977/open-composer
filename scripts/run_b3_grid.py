"""Step 11 Wave B: B3, LightGBM bounded grid + validation-year selection.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 4. The plan's grid
is label horizon {5, 10, 21} x tree depth {3, 6} x feature set {daily-only,
daily+intraday} = <=12 configurations explored, selection rule fixed
("按训练窗口最后一年（验证年）的 rank IC 选，不看测试年"). This script runs
*two* top-level experiments (one per feature set), each wrapping a
``b3_grid_strategy.GridSelectedLightGBMStrategy`` that internally explores
its 6 (horizon, depth) cells every walk-forward test year and keeps whichever
cell had the best validation-year rank IC -- not 12 separate, statically
chosen candidates spliced together after the fact (that would need the same
per-year selection logic anyway, just reimplemented outside the strategy
interface, and a naive "run all 12, pick the best by test-year Sharpe after
the fact" design would be the exact test-year peeking the plan's selection
rule is written to prevent).

``GridSelectedLightGBMStrategy.fit`` needs all three label horizons
(``label_rank_5/10/21``) present in the same ``train_frame`` at once (one
grid cell per horizon) -- ``build_weight_schedule``'s narrow-copy fix
(2026-09-08, commit 00911bc) only ever kept a single ``label_column``, so
``loop.py`` gained a new, additive-only ``extra_train_columns`` parameter
this same day (see its docstring) to carry the other two horizons along
without requiring them to be simultaneously non-null (each grid cell already
does its own per-column ``dropna`` inside ``fit()``).

**``train_row_dates="rebalance_dates"`` (loop.py, commit 2e6e3ce) is not
optional for this script**, unlike B0-B2's default ``"all"``: every walk-
forward test year here fits *six* separate LightGBM models (one per grid
cell), each of which materializes its own full training matrix. On the
``"all"``-rows daily+intraday panel (~6.1M rows x 44 feature columns) that
is infeasible on this box -- confirmed directly, not assumed: B2's single-
ridge-model daily+intraday variant (one fit per year, not six, and ridge's
constant-memory chunked solve at that) still needed a 2.6-3.6GB+ cgroup cap
and died more than once even there (see the Step 11 ledger's 2026-09-08
entries). ``"rebalance_dates"`` cuts training rows to the weekly cross-
sections the model is actually served on (~1/5 of "all", ~1.2M rows for the
full universe), which is the only regime in which all 12 (2 feature sets x 6
cells) LightGBM fits per test year are tractable here. This also happens to
be methodologically preferable, not just cheaper (see loop.py's docstring:
daily rows carry h-day overlapping forward labels that overstate the
independent sample, and the model is only ever invoked at rebalance time
anyway) -- but tractability, not preference, is why it is not a CLI flag on
this script.

Usage::

    uv run python scripts/run_b3_grid.py
    uv run python scripts/run_b3_grid.py --only step11_b3_lightgbm_grid_daily_only
    # Cheap correctness smoke test before paying for the full 9-year walk
    # forward (--only + --test-years so it costs seconds, not minutes):
    uv run python scripts/run_b3_grid.py --only step11_b3_lightgbm_grid_daily_only \\
        --test-years 2025 2026
    # Label-shuffle placebo only (pipeline-leakage check, plan section 4):
    uv run python scripts/run_b3_grid.py --placebo-only
"""

from __future__ import annotations

import argparse
import gc
import json
import multiprocessing
import sys
import time
from pathlib import Path
from queue import Empty as QueueEmpty

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features.intraday_daily import INTRADAY_DAILY_COLUMNS  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.b3_grid_strategy import (  # noqa: E402
    DEFAULT_GRID,
    GridSelectedLightGBMStrategy,
)
from open_composer.research.kernel.benchmark_returns import (  # noqa: E402
    daily_returns_on_naive_dates,
)
from open_composer.research.kernel.loop import (  # noqa: E402
    DEFAULT_TEST_YEARS,
    ExperimentConfig,
    build_weight_schedule,
    run_experiment,
)

DAILY_FEATURES_ROOT = ROOT / "data" / "features" / "daily"
LABELS_ROOT = ROOT / "data" / "features" / "labels"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
DATA_START = "2016-01-04"

#: Mirrors run_baseline_chain.py's B2_FEATURE_COLUMNS exactly (same feature
#: block B2 uses -- B3's grid is "same features, model swapped for LightGBM
#: with a horizon/depth search", not a separate feature-engineering effort).
B2_FEATURE_COLUMNS = (
    "ret_1",
    "ret_5",
    "ret_21",
    "ret_63",
    "ret_126",
    "ret_252",
    "momentum_252_21",
    "vol_21",
    "vol_63",
    "beta_252_spy",
    "idio_vol_63",
    "max_ret_1_21",
    "dollar_adv_21",
    "dollar_adv_63",
    "dollar_adv_21_over_63",
    "amihud_21",
    "dist_from_252d_high",
    "ret_1_rel",
    "ret_5_rel",
    "ret_21_rel",
    "ret_63_rel",
    "ret_126_rel",
    "ret_252_rel",
    "momentum_252_21_rel",
)
INTRADAY_ROLLING_WINDOWS = (5, 21)
INTRADAY_ROLLING_FEATURE_COLUMNS = tuple(
    f"{column}_{window}d_mean"
    for column in INTRADAY_DAILY_COLUMNS
    if column not in ("symbol", "trade_date")
    for window in INTRADAY_ROLLING_WINDOWS
)
B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY = B2_FEATURE_COLUMNS + INTRADAY_ROLLING_FEATURE_COLUMNS

#: The grid's three label horizons. label_rank_21 is the "official" outer
#: label_column (also sets the embargo -- the longest horizon's cutoff is
#: safe for the shorter ones too); the other two ride in via
#: extra_train_columns (see loop.py's docstring for why they must NOT be
#: required non-null by the outer row mask).
PRIMARY_LABEL_COLUMN = "label_rank_21"
EXTRA_LABEL_COLUMNS = ("label_rank_5", "label_rank_10")
ALL_LABEL_COLUMNS = (*EXTRA_LABEL_COLUMNS, PRIMARY_LABEL_COLUMN)
#: label_horizon_days feeds only the embargo cutoff (see loop.py); 21 is the
#: max of the grid's horizons, so the cutoff is safe for every cell.
LABEL_HORIZON_DAYS = 21

_DAILY_ONLY_READ_COLUMNS = sorted({"symbol", "trade_date", "close", *B2_FEATURE_COLUMNS})
_DAILY_PLUS_INTRADAY_READ_COLUMNS = sorted(
    {"symbol", "trade_date", "close", *B2_FEATURE_COLUMNS, *INTRADAY_ROLLING_FEATURE_COLUMNS}
)
_LABEL_READ_COLUMNS = ["symbol", "trade_date", *ALL_LABEL_COLUMNS]
_READ_COLUMNS_BY_FEATURE_SET = {
    "daily_only": _DAILY_ONLY_READ_COLUMNS,
    "daily_plus_intraday": _DAILY_PLUS_INTRADAY_READ_COLUMNS,
}


def _load_panel(feature_set: str = "daily_only") -> pd.DataFrame:
    """Same shared-CategoricalDtype-before-merge / float32 / per-year-merge
    approach as run_baseline_chain.py::_load_panel (see that module's
    comments for the full rationale) -- duplicated rather than imported
    because the label column set differs (all 3 horizons here, one there)
    and this script must not risk perturbing the already-committed,
    already-recorded B0-B2 baseline chain by refactoring its loader.
    """
    if feature_set not in _READ_COLUMNS_BY_FEATURE_SET:
        known = sorted(_READ_COLUMNS_BY_FEATURE_SET)
        raise ValueError(f"unknown feature_set {feature_set!r}, expected one of {known}")
    read_columns = _READ_COLUMNS_BY_FEATURE_SET[feature_set]

    years = sorted(int(p.stem) for p in DAILY_FEATURES_ROOT.glob("*.parquet") if p.stem.isdigit())

    all_symbols: set[str] = set()
    for year in years:
        year_symbols = pd.read_parquet(DAILY_FEATURES_ROOT / f"{year}.parquet", columns=["symbol"])
        all_symbols.update(year_symbols["symbol"].unique())
        del year_symbols
    symbol_dtype = pd.CategoricalDtype(categories=sorted(all_symbols))

    merged_frames = []
    for year in years:
        daily_year = pd.read_parquet(DAILY_FEATURES_ROOT / f"{year}.parquet", columns=read_columns)
        label_path = LABELS_ROOT / f"{year}.parquet"
        if not label_path.exists():
            continue
        label_year = pd.read_parquet(label_path, columns=_LABEL_READ_COLUMNS)
        for frame in (daily_year, label_year):
            float_columns = frame.select_dtypes(include=["float64"]).columns
            frame[float_columns] = frame[float_columns].astype("float32")
        daily_year["symbol"] = daily_year["symbol"].astype(symbol_dtype)
        label_year["symbol"] = label_year["symbol"].astype(symbol_dtype)
        merged_frames.append(daily_year.merge(label_year, on=["symbol", "trade_date"], how="inner"))
        del daily_year, label_year

    panel = pd.concat(merged_frames, ignore_index=True)
    del merged_frames
    gc.collect()
    return panel


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="experiment_id to run (repeatable); default runs both feature sets",
    )
    parser.add_argument(
        "--test-years",
        type=int,
        nargs="*",
        default=None,
        help="restrict the walk-forward to these years (default: DEFAULT_TEST_YEARS, 2018-2026)",
    )
    parser.add_argument(
        "--placebo-only",
        action="store_true",
        help="run only the label-shuffle placebo check (no ledger/tearsheet experiments)",
    )
    return parser.parse_args()


def _turnover_and_capacity(schedule, panel: pd.DataFrame) -> dict[str, float]:
    """Turnover (mean two-sided Sum|delta w| per rebalance, matching
    loop.py::returns_from_weight_schedule's own formula -- see its comment
    for why this is *not* doubled again for cost purposes here, this is a
    report-only figure) and a capacity proxy: for every selected holding,
    what fraction of that name's 21-day average dollar volume a purely
    illustrative $10mm book's position would represent, at an equal-weight
    top-K book (position size $10mm / K). The plan doesn't pin an exact AUM,
    so $10mm is disclosed here as an assumption a reader can rescale
    linearly (capacity_pct_of_adv scales 1:1 with assumed AUM).
    """
    ASSUMED_AUM_USD = 10_000_000.0
    active = [event for event in schedule if event.selected]
    if not active:
        return {"mean_turnover": float("nan"), "median_capacity_pct_of_adv": float("nan")}

    turnovers = []
    previous_weights: dict[str, float] = {}
    for event in active:
        weights = {k: v for k, v in event.selected.items() if k != "__SPY_HEDGE__"}
        symbols_touched = set(weights) | set(previous_weights)
        turnover = sum(
            abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in symbols_touched
        )
        turnovers.append(turnover)
        previous_weights = weights

    adv_by_date_symbol = panel.set_index(["trade_date", "symbol"])["dollar_adv_21"]
    capacity_pcts = []
    for event in active:
        weights = {k: v for k, v in event.selected.items() if k != "__SPY_HEDGE__"}
        event_date = pd.Timestamp(event.date)
        for symbol, weight in weights.items():
            try:
                adv = adv_by_date_symbol.loc[(event_date, symbol)]
            except KeyError:
                continue
            if pd.isna(adv) or adv <= 0:
                continue
            position_usd = weight * ASSUMED_AUM_USD
            capacity_pcts.append(100.0 * position_usd / float(adv))

    return {
        "mean_turnover": float(np.mean(turnovers)),
        "median_capacity_pct_of_adv": float(np.median(capacity_pcts))
        if capacity_pcts
        else float("nan"),
        "assumed_aum_usd": ASSUMED_AUM_USD,
    }


def _annual_compounded_returns(candidate) -> dict[str, float]:
    """Plan section 4's "逐年组合收益" (per-year portfolio returns).
    ``Candidate.oos_return_stream``/``oos_dates`` (mechanism_eval.py) are the
    exact daily, cost-adjusted return stream ``evaluate_candidate`` scored --
    already accessible off ``CandidateVerdict.candidate`` without needing any
    further loop.py change. Grouped by calendar year and compounded
    ((1+r).prod() - 1), one entry per test year actually present in the
    stream (a year with zero active weeks -- e.g. an empty universe fallback
    -- legitimately contributes 0.0, not a missing key).
    """
    if not candidate.oos_return_stream:
        return {}
    dates = pd.to_datetime(candidate.oos_dates)
    returns = pd.Series(candidate.oos_return_stream, index=dates)
    annual = returns.groupby(returns.index.year).apply(lambda r: float((1.0 + r).prod() - 1.0))
    return {str(year): value for year, value in annual.items()}


def _run_b3_and_queue_result(
    config: ExperimentConfig,
    panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    benchmarks: dict[str, pd.Series],
    result_queue: multiprocessing.Queue,
) -> None:
    try:
        created_strategies: list[GridSelectedLightGBMStrategy] = []

        def factory() -> GridSelectedLightGBMStrategy:
            strategy = GridSelectedLightGBMStrategy(config.feature_columns, grid=DEFAULT_GRID)
            created_strategies.append(strategy)
            return strategy

        verdict = run_experiment(
            config,
            panel=panel,
            universe_panel=universe_panel,
            label_column=PRIMARY_LABEL_COLUMN,
            strategy_factory=factory,
            spy_returns=benchmarks["SPY"],
            qqq_returns=benchmarks["QQQ"],
            tqqq_returns=benchmarks["TQQQ"],
            bil_returns=benchmarks["BIL"],
            extra_train_columns=EXTRA_LABEL_COLUMNS,
        )

        per_year_selection = []
        for strategy in created_strategies:
            if strategy.selected_cell is None:
                continue
            per_year_selection.append(
                {
                    "validation_year": strategy.validation_year,
                    "selected_cell": strategy.selected_cell.config_id,
                    "validation_ic_by_cell": strategy.validation_ic_by_cell,
                }
            )
        top_features = (
            created_strategies[-1].top_feature_importances(20).to_dict()
            if created_strategies
            else {}
        )
        turnover_capacity = _turnover_and_capacity(verdict.schedule, panel)

        rows = []
        for hedge_label, candidate_verdict in (
            ("long_only", verdict.long_only),
            ("market_neutral", verdict.market_neutral),
        ):
            metrics = candidate_verdict.metrics
            gate_results = candidate_verdict.gate_results
            rows.append(
                {
                    "experiment_id": f"{config.experiment_id}_{hedge_label}",
                    "cagr_excess_vol_matched_benchmark": metrics[
                        "cagr_excess_vol_matched_benchmark"
                    ],
                    "sharpe_excess_bil": candidate_verdict.sharpe_excess_bil,
                    "max_drawdown": metrics["max_drawdown"],
                    "mar": metrics["mar"],
                    "benchmark_vm_capture_ratio": metrics["benchmark_vm_capture_ratio"],
                    "gates_passed": sum(gate_results.values()),
                    "gates_total": len(gate_results),
                    "all_gates_pass": candidate_verdict.all_gates_pass,
                    "dsr_trial_count": verdict.dsr_trial_count,
                    "annual_returns": _annual_compounded_returns(candidate_verdict.candidate),
                }
            )
        result_queue.put(
            (
                "ok",
                {
                    "rows": rows,
                    "per_year_selection": per_year_selection,
                    "top_feature_importances": top_features,
                    "turnover_capacity": turnover_capacity,
                },
            )
        )
    except Exception as exc:  # noqa: BLE001 -- must always report back, never hang the parent
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _run_b3_in_subprocess(
    config: ExperimentConfig,
    panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    benchmarks: dict[str, pd.Series],
) -> dict[str, object]:
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_run_b3_and_queue_result,
        args=(config, panel, universe_panel, benchmarks, result_queue),
    )
    process.start()
    status: str | None = None
    payload: object = None
    while process.is_alive():
        try:
            status, payload = result_queue.get(timeout=5.0)
            break
        except QueueEmpty:
            continue
    if status is None:
        try:
            status, payload = result_queue.get(timeout=5.0)
        except QueueEmpty:
            pass
    process.join()
    if status is None:
        raise RuntimeError(
            f"{config.experiment_id} subprocess died with exit code {process.exitcode} "
            "before producing a result (exit -9 = cgroup MemoryMax/MemorySwapMax, "
            "contained/resumable; exit -15 = earlyoom reacting to system-wide free "
            "mem/swap, can fire even inside a capped scope. See the Step 11 ledger's "
            "2026-09-08 entries.)"
        )
    if status == "error":
        raise RuntimeError(f"{config.experiment_id} subprocess raised: {payload}")
    if process.exitcode != 0:
        raise RuntimeError(f"{config.experiment_id} subprocess exited with code {process.exitcode}")
    return payload  # type: ignore[return-value]


def _run_label_shuffle_placebo(
    panel: pd.DataFrame, universe_panel: pd.DataFrame
) -> dict[str, object]:
    """Plan section 4's "一次标签打乱的安慰剂": shuffle label_rank_21 *within*
    each trade_date's cross-section (so the marginal distribution the model
    sees is unchanged, but any true feature-label relationship is
    destroyed), fit the same GridSelectedLightGBMStrategy machinery on one
    anchored training window, score the following validation year, and
    report the mean rank IC -- must be approximately 0. A single (year,
    feature-set) pair is enough to catch a leakage bug (the plan says "一
    次", one placebo), so this intentionally does not repeat the full
    9-year walk-forward: it borrows build_weight_schedule's exact
    train/embargo logic for one test year via a throwaway one-year config,
    which is representative of every other year's mechanics.
    """
    rng = np.random.default_rng(7)
    shuffled = panel.copy()
    shuffled[PRIMARY_LABEL_COLUMN] = shuffled.groupby("trade_date")[PRIMARY_LABEL_COLUMN].transform(
        lambda s: rng.permutation(s.to_numpy()) if s.notna().any() else s
    )

    strategy = GridSelectedLightGBMStrategy(B2_FEATURE_COLUMNS, grid=DEFAULT_GRID)
    schedule = build_weight_schedule(
        panel=shuffled,
        universe_panel=universe_panel,
        strategy_factory=lambda: strategy,
        feature_columns=list(B2_FEATURE_COLUMNS),
        label_column=PRIMARY_LABEL_COLUMN,
        label_horizon_days=LABEL_HORIZON_DAYS,
        test_years=(2026,),
        top_k=50,
        hedge="none",
        train_row_dates="rebalance_dates",
    )
    del schedule  # only strategy.fit()'s internal validation IC is needed

    if strategy.selected_cell is None:
        return {
            "placebo_mean_rank_ic": float("nan"),
            "note": "no grid cell fit (empty training window)",
        }
    selected_ic = strategy.validation_ic_by_cell[strategy.selected_cell.config_id]
    return {
        "validation_year": strategy.validation_year,
        "selected_cell": strategy.selected_cell.config_id,
        "validation_ic_by_cell": strategy.validation_ic_by_cell,
        "placebo_selected_cell_mean_rank_ic": selected_ic,
    }


def main() -> int:
    args = _parse_args()
    test_years = tuple(args.test_years) if args.test_years else DEFAULT_TEST_YEARS

    configs = [
        ExperimentConfig(
            experiment_id="step11_b3_lightgbm_grid_daily_only",
            family="step11_baseline_chain",
            model_kind="lightgbm_grid_selected",
            feature_set="daily_only",
            label_horizon_days=LABEL_HORIZON_DAYS,
            feature_columns=B2_FEATURE_COLUMNS,
            top_k=50,
            hedge="spy_beta_hedge",
            test_years=test_years,
            train_row_dates="rebalance_dates",
            hyperparameters={"grid": [cell.config_id for cell in DEFAULT_GRID]},
        ),
        ExperimentConfig(
            experiment_id="step11_b3_lightgbm_grid_daily_plus_intraday",
            family="step11_baseline_chain",
            model_kind="lightgbm_grid_selected",
            feature_set="daily_plus_intraday",
            label_horizon_days=LABEL_HORIZON_DAYS,
            feature_columns=B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY,
            top_k=50,
            hedge="spy_beta_hedge",
            test_years=test_years,
            train_row_dates="rebalance_dates",
            hyperparameters={"grid": [cell.config_id for cell in DEFAULT_GRID]},
        ),
    ]
    if args.only:
        wanted = set(args.only)
        configs = [config for config in configs if config.experiment_id in wanted]
        missing = wanted - {config.experiment_id for config in configs}
        if missing:
            raise SystemExit(f"--only requested unknown experiment_id(s): {sorted(missing)}")

    needed_feature_sets = (
        sorted({config.feature_set for config in configs})
        if not args.placebo_only
        else ["daily_only"]
    )
    panels: dict[str, pd.DataFrame] = {}
    for feature_set in needed_feature_sets:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading {feature_set} daily+label panel ...",
            flush=True,
        )
        panel = _load_panel(feature_set)
        print(
            f"panel[{feature_set}]: {len(panel)} rows, {panel['symbol'].nunique()} symbols",
            flush=True,
        )
        panels[feature_set] = panel

    universe_panel = load_universe_panel(UNIVERSE_ROOT)

    if args.placebo_only:
        gc.collect()
        print("running label-shuffle placebo ...", flush=True)
        result = _run_label_shuffle_placebo(panels["daily_only"], universe_panel)
        print(json.dumps(result, indent=2, default=str), flush=True)
        return 0

    print("loading SPY/QQQ/TQQQ/BIL benchmark returns ...", flush=True)
    benchmarks = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }

    all_results = {}
    for config in configs:
        gc.collect()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] running {config.experiment_id} "
            "(in its own subprocess) ...",
            flush=True,
        )
        started = time.monotonic()
        result = _run_b3_in_subprocess(
            config, panels[config.feature_set], universe_panel, benchmarks
        )
        elapsed = time.monotonic() - started
        result["elapsed_seconds"] = round(elapsed, 1)
        all_results[config.experiment_id] = result
        print(json.dumps(result, indent=2, default=str), flush=True)

    print("\n=== label-shuffle placebo (daily_only, 2026 window) ===", flush=True)
    gc.collect()
    placebo = _run_label_shuffle_placebo(panels["daily_only"], universe_panel)
    all_results["label_shuffle_placebo"] = placebo
    print(json.dumps(placebo, indent=2, default=str), flush=True)

    print("\n=== SUMMARY ===", flush=True)
    summary_rows = [
        row for result in all_results.values() if "rows" in result for row in result["rows"]
    ]
    print(pd.DataFrame(summary_rows).to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
