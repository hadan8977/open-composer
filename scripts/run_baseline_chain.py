"""Step 11 Wave A 3.5: baseline chain B0 (equal-weight universe) -> B1
(12-1 momentum) -> B2 (ridge), daily-only features.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.5. Framework is
fixed this round (not searched): weekly rebalance, K=50 equal-weight, 10bps/
side base cost (25bps stress), long-only and SPY-beta-hedged market-neutral
variants both reported. Each level must beat the previous level out of
sample, net of costs, to be "adopted" -- this script does not enforce that
automatically; it runs all three, records everything (including negative
results) to the ledger, and prints a comparison table for the ledger writeup.

Usage::

    uv run python scripts/run_baseline_chain.py
    # Re-run (or resume after a kill) just one experiment -- the ledger
    # already dedups completed configs by config_hash (see loop.py's
    # _append_ledger), so re-running an *already-recorded* id is a harmless
    # no-op write but still repeats the full walk-forward computation
    # (~25 minutes for B1). --only skips that waste when only one candidate
    # in the chain actually needs (re)running, e.g. after B2 alone died to
    # earlyoom/SIGTERM while B0/B1 were already safely recorded.
    uv run python scripts/run_baseline_chain.py --only step11_b2_ridge_top50
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

import pandas as pd  # noqa: E402

from open_composer.research.features.intraday_daily import INTRADAY_DAILY_COLUMNS  # noqa: E402
from open_composer.research.features.universe import load_universe_panel  # noqa: E402
from open_composer.research.kernel.baseline_strategies import (  # noqa: E402
    EqualWeightUniverseStrategy,
    MomentumFactorStrategy,
    RidgeRankStrategy,
)
from open_composer.research.kernel.benchmark_returns import (  # noqa: E402
    daily_returns_on_naive_dates,
)
from open_composer.research.kernel.loop import (  # noqa: E402
    DEFAULT_TEST_YEARS,
    ExperimentConfig,
    run_experiment,
)

DAILY_FEATURES_ROOT = ROOT / "data" / "features" / "daily"
LABELS_ROOT = ROOT / "data" / "features" / "labels"
UNIVERSE_ROOT = ROOT / "data" / "features" / "universe"
DATA_START = "2016-01-04"

#: Every daily_features.py column except identifiers/close and the momentum
#: factor alone (B1 uses only momentum_252_21; B2 gets the fuller block).
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
LABEL_COLUMN = "label_rank_5"
LABEL_HORIZON_DAYS = 5

#: The 5d/21d trailing means daily_features.py::join_intraday_rolling_features
#: adds on top of every intraday_daily.py value column (symbol/trade_date
#: excluded -- those are identifiers, not values to be rolled). Column-name
#: derivation mirrors that function's own `add_suffix(f"_{window}d_mean")`
#: exactly; kept here rather than imported so this script fails loudly (a
#: KeyError from pd.read_parquet's columns= filter) if the two ever drift
#: apart, instead of silently reading an empty/wrong set.
INTRADAY_ROLLING_WINDOWS = (5, 21)
INTRADAY_ROLLING_FEATURE_COLUMNS = tuple(
    f"{column}_{window}d_mean"
    for column in INTRADAY_DAILY_COLUMNS
    if column not in ("symbol", "trade_date")
    for window in INTRADAY_ROLLING_WINDOWS
)
B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY = B2_FEATURE_COLUMNS + INTRADAY_ROLLING_FEATURE_COLUMNS


#: Only pull the columns the B0/B1/B2 baselines (and run_experiment's own
#: price pivot / beta-hedge weighting) actually touch -- data/features/daily
#: carries ~27-47 columns per year once intraday joins land, but the
#: daily_only feature set needs at most identifiers + B2_FEATURE_COLUMNS.
#: Reading a column subset keeps the concatenated 11-year panel far smaller
#: than the full archive (see scripts/build_daily_features.py's module
#: docstring for the real OOM-adjacent incident this mirrors the fix for).
# "open" (Wave B item 4, 2026-09-08): needed so run_experiment can pivot
# open_wide for the next_open execution path; harmless/unused for the
# default close_marked execution every other config here still uses.
_DAILY_ONLY_READ_COLUMNS = sorted({"symbol", "trade_date", "open", "close", *B2_FEATURE_COLUMNS})
#: daily_plus_intraday additionally needs the 20 rolled intraday columns --
#: this set only exists in data/features/daily/{year}.parquet *after*
#: scripts/build_daily_features.py has been (re)run with the intraday
#: backfill in place (join_intraday_rolling_features left-joins them on);
#: reading this column set against a not-yet-rejoined file raises a clear
#: pyarrow error rather than silently proceeding without the columns.
_DAILY_PLUS_INTRADAY_READ_COLUMNS = sorted(
    {
        "symbol",
        "trade_date",
        "open",
        "close",
        *B2_FEATURE_COLUMNS,
        *INTRADAY_ROLLING_FEATURE_COLUMNS,
    }
)
_LABEL_READ_COLUMNS = ["symbol", "trade_date", LABEL_COLUMN]
_READ_COLUMNS_BY_FEATURE_SET = {
    "daily_only": _DAILY_ONLY_READ_COLUMNS,
    "daily_plus_intraday": _DAILY_PLUS_INTRADAY_READ_COLUMNS,
}


def _load_panel(feature_set: str = "daily_only") -> pd.DataFrame:
    if feature_set not in _READ_COLUMNS_BY_FEATURE_SET:
        known = sorted(_READ_COLUMNS_BY_FEATURE_SET)
        raise ValueError(f"unknown feature_set {feature_set!r}, expected one of {known}")
    read_columns = _READ_COLUMNS_BY_FEATURE_SET[feature_set]

    # Merge per year, then concat the (much smaller) merged results -- one
    # 11-year-vs-11-year merge peaks far higher than 11 single-year merges,
    # because pandas' hash join briefly holds both full inputs *and* the
    # output alive at once. Real incident: this used to concat all 11 years
    # of daily + all 11 years of labels first and merge once, which grew RSS
    # past 2.6GB and was still climbing after a full minute (see
    # scripts/build_daily_features.py's module docstring for the sibling
    # incident this mirrors the fix for).
    years = sorted(int(p.stem) for p in DAILY_FEATURES_ROOT.glob("*.parquet") if p.stem.isdigit())

    # One narrow pass (symbol only -- parquet stores columns separately, so
    # this never touches the wide feature data) to fix a single, shared
    # pd.CategoricalDtype up front. This is required, not just an ordering
    # choice: verified interactively that pd.concat does NOT union per-frame
    # categories on its own -- concatenating two category columns whose
    # `.cat.categories` differ even slightly silently upcasts the result
    # back to `object`, undoing category-encoding entirely with no error or
    # warning. Sharing one CategoricalDtype (built from every year's actual
    # symbols) across all 11 per-year frames is what lets the dtype survive
    # the final concat below.
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
        # float64 -> float32 halves the numeric payload (ridge/percentile-rank
        # values have nowhere near 15-digit precision needs to begin with);
        # identifiers (symbol, trade_date) are left alone. Shrinks both this
        # year's frame and every later concat/merge it participates in.
        for frame in (daily_year, label_year):
            float_columns = frame.select_dtypes(include=["float64"]).columns
            frame[float_columns] = frame[float_columns].astype("float32")
        # Category-encode *before* merging, using the shared dtype: a year's
        # ~500-650k Python strings is exactly the kind of object-dtype
        # column that breaks copy-on-write sharing across the fork in this
        # script's later multiprocessing.Process (every element is its own
        # refcounted Python object; merely touching them dirties their
        # pages). Collapsing to a small integer code array (against the one
        # shared ~2,721-symbol dict) before the merge, not after, keeps
        # every frame this function ever holds narrow, not just the one it
        # returns -- both sides of the join need it for an efficient
        # categorical merge, so both get it.
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
        help="experiment_id to run (repeatable); default runs all three",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    # NOTE on why there is exactly one ExperimentConfig per model, not one per
    # (model, hedge) pair: run_experiment() *always* computes both the
    # long-only and the SPY-beta-hedged market-neutral verdict from a single
    # walk-forward weight schedule (loop.py builds long_base/long_stress with
    # include_hedge=False and neutral_base/neutral_stress with
    # include_hedge=True unconditionally -- see its module code) and writes
    # *one* ledger record containing both. config.hedge only controls whether
    # build_weight_schedule inserts a __SPY_HEDGE__ leg into the schedule at
    # all. So setting hedge="spy_beta_hedge" here gives both a correct
    # long-only reading (the hedge leg stripped back out) and a correct
    # market-neutral reading (the hedge leg included) from *one*
    # run_experiment call; a first version of this script instead built a
    # second config with hedge="none" per model and called run_experiment
    # again, which silently computed a meaningless "market_neutral" verdict
    # for that config (identical to its own long-only, since no hedge leg
    # existed to include) while doubling total runtime and ledger entries for
    # no benefit. Fixed before the first real run completed a single
    # experiment (see the Wave A 3.5 ledger section).
    configs = [
        (
            ExperimentConfig(
                experiment_id="step11_b0_equal_weight_universe",
                family="step11_baseline_chain",
                model_kind="b0_equal_weight",
                feature_set="daily_only",
                label_horizon_days=LABEL_HORIZON_DAYS,
                # EqualWeightUniverseStrategy.score never reads this column, but
                # build_weight_schedule also uses config.feature_columns as the
                # per-week `.dropna(subset=feature_columns)` eligibility filter
                # (see loop.py::build_weight_schedule). Setting it to
                # momentum_252_21 -- the same column B1/B2 require -- means B0's
                # weekly universe is intersected with "has 273 trading days of
                # history", i.e. exactly the same eligible names B1 and B2 see,
                # not the raw, unfiltered PIT universe. This is intentional: it
                # isolates the ranking method as the only difference between B0
                # and B1/B2 rather than confounding it with a different
                # tradable universe. Recorded in the Wave A 3.5 ledger section.
                feature_columns=("momentum_252_21",),
                top_k=None,
                hedge="spy_beta_hedge",
                test_years=DEFAULT_TEST_YEARS,
            ),
            lambda: EqualWeightUniverseStrategy(),
        ),
        (
            ExperimentConfig(
                experiment_id="step11_b1_momentum_top50",
                family="step11_baseline_chain",
                model_kind="b1_momentum",
                feature_set="daily_only",
                label_horizon_days=LABEL_HORIZON_DAYS,
                feature_columns=("momentum_252_21",),
                top_k=50,
                hedge="spy_beta_hedge",
                test_years=DEFAULT_TEST_YEARS,
            ),
            lambda: MomentumFactorStrategy(),
        ),
        (
            ExperimentConfig(
                experiment_id="step11_b2_ridge_top50",
                family="step11_baseline_chain",
                model_kind="ridge_regressor",
                feature_set="daily_only",
                label_horizon_days=LABEL_HORIZON_DAYS,
                feature_columns=B2_FEATURE_COLUMNS,
                top_k=50,
                hedge="spy_beta_hedge",
                test_years=DEFAULT_TEST_YEARS,
                hyperparameters={"alpha": 1.0},
            ),
            lambda: RidgeRankStrategy(B2_FEATURE_COLUMNS, LABEL_COLUMN, alpha=1.0),
        ),
        (
            # Wave A 3.5 step 2 (coordinator, 2026-09-08): same B2 ridge model
            # and hyperparameters, but with the 20 intraday-derived 5d/21d
            # rolling columns added to feature_columns, to A/B test
            # daily-only vs daily+intraday now that the minute-bar backfill
            # (3.3.1) is complete. Requires data/features/daily/{year}.parquet
            # to already carry those columns -- run
            # scripts/build_daily_features.py (no --skip-intraday-join) first.
            ExperimentConfig(
                experiment_id="step11_b2_ridge_top50_daily_plus_intraday",
                family="step11_baseline_chain",
                model_kind="ridge_regressor",
                feature_set="daily_plus_intraday",
                label_horizon_days=LABEL_HORIZON_DAYS,
                feature_columns=B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY,
                top_k=50,
                hedge="spy_beta_hedge",
                test_years=DEFAULT_TEST_YEARS,
                hyperparameters={"alpha": 1.0},
            ),
            lambda: RidgeRankStrategy(
                B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY, LABEL_COLUMN, alpha=1.0
            ),
        ),
        (
            # Coordinator, 2026-09-08 (commit 2e6e3ce): the daily+intraday
            # variant above (train_row_dates="all", the default) does not fit
            # in memory on this box -- confirmed directly, not assumed: it
            # died twice under generous caps (2.6-3.6GB+), once via a silent
            # whole-scope memcg OOM and once via system-wide earlyoom (see
            # the Step 11 ledger's 2026-09-08 entries for both). Rather than
            # just retrying "all" at an ever-higher cap, train_row_dates=
            # "rebalance_dates" removes the actual root cause (~6.1M training
            # rows down to the ~1.2M weekly cross-sections the model is ever
            # served on) instead of papering over it with more RAM. This
            # config is also backfilled for daily-only (not just
            # daily+intraday) so the feature-set comparison (daily-only vs
            # daily+intraday) is never confounded with a training-row-
            # methodology difference: all four {daily-only, daily+intraday} x
            # {all, rebalance_dates} cells get run and reported (the already-
            # recorded daily-only+all result is not rerun).
            ExperimentConfig(
                experiment_id="step11_b2_ridge_top50_rebalance_dates",
                family="step11_baseline_chain",
                model_kind="ridge_regressor",
                feature_set="daily_only",
                label_horizon_days=LABEL_HORIZON_DAYS,
                feature_columns=B2_FEATURE_COLUMNS,
                top_k=50,
                hedge="spy_beta_hedge",
                test_years=DEFAULT_TEST_YEARS,
                train_row_dates="rebalance_dates",
                hyperparameters={"alpha": 1.0},
            ),
            lambda: RidgeRankStrategy(B2_FEATURE_COLUMNS, LABEL_COLUMN, alpha=1.0),
        ),
        (
            ExperimentConfig(
                experiment_id="step11_b2_ridge_top50_daily_plus_intraday_rebalance_dates",
                family="step11_baseline_chain",
                model_kind="ridge_regressor",
                feature_set="daily_plus_intraday",
                label_horizon_days=LABEL_HORIZON_DAYS,
                feature_columns=B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY,
                top_k=50,
                hedge="spy_beta_hedge",
                test_years=DEFAULT_TEST_YEARS,
                train_row_dates="rebalance_dates",
                hyperparameters={"alpha": 1.0},
            ),
            lambda: RidgeRankStrategy(
                B2_FEATURE_COLUMNS_DAILY_PLUS_INTRADAY, LABEL_COLUMN, alpha=1.0
            ),
        ),
    ]

    if args.only:
        wanted = set(args.only)
        configs = [
            (config, factory) for config, factory in configs if config.experiment_id in wanted
        ]
        missing = wanted - {config.experiment_id for config, _ in configs}
        if missing:
            raise SystemExit(f"--only requested unknown experiment_id(s): {sorted(missing)}")

    # Load only the panel(s) the selected configs actually need -- running
    # --only against a single daily_only experiment must not also pay for a
    # daily_plus_intraday load (and vice versa). Panels are cached in this
    # dict for the (currently impossible-to-hit-twice-cheaply, but harmless)
    # case where --only spans both feature sets in one invocation.
    needed_feature_sets = sorted({config.feature_set for config, _ in configs})
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

    print("loading SPY/QQQ/TQQQ/BIL benchmark returns ...", flush=True)
    benchmarks = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }

    summary_rows = []
    for config, factory in configs:
        # Collect before every fork, not just once after loading: pandas'
        # per-year merge/concat/category-cast loop in _load_panel leaves
        # behind reference cycles (DataFrames hold cyclic refs to their own
        # internal BlockManager) that plain refcounting won't free -- those
        # garbage-but-uncollected pages would otherwise sit resident in the
        # parent and get inherited (and charged again on first touch) by
        # every child this loop forks.
        gc.collect()
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] running {config.experiment_id} "
            f"(in its own subprocess) ...",
            flush=True,
        )
        started = time.monotonic()
        rows = _run_experiment_in_subprocess(
            config, factory, panels[config.feature_set], universe_panel, benchmarks
        )
        elapsed = time.monotonic() - started
        for row in rows:
            row["elapsed_seconds"] = round(elapsed, 1)
            summary_rows.append(row)
            print(json.dumps(row, indent=2, default=str), flush=True)

    print("\n=== SUMMARY ===", flush=True)
    summary_frame = pd.DataFrame(summary_rows)
    print(summary_frame.to_string(index=False), flush=True)
    return 0


def _run_experiment_and_queue_rows(
    config: ExperimentConfig,
    factory,
    panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    benchmarks: dict[str, pd.Series],
    result_queue: multiprocessing.Queue,
) -> None:
    """Child-process entry point: run one experiment, put its two summary
    rows (long-only, market-neutral) on ``result_queue``, then exit -- every
    allocation ``run_experiment`` makes (the weight schedule, both return
    streams, the fitted model, QuantStats' matplotlib figures, ...) is
    reclaimed by the OS the moment this process exits, instead of relying on
    Python's own GC inside a long-lived loop. ``panel``/``universe_panel``/
    ``benchmarks`` are inherited via ``fork()`` copy-on-write (the default
    ``multiprocessing`` start method on Linux), not re-pickled or reloaded,
    so the ~5-minute panel load in the parent still only happens once.
    """
    try:
        verdict = run_experiment(
            config,
            panel=panel,
            universe_panel=universe_panel,
            label_column=LABEL_COLUMN,
            strategy_factory=factory,
            spy_returns=benchmarks["SPY"],
            qqq_returns=benchmarks["QQQ"],
            tqqq_returns=benchmarks["TQQQ"],
            bil_returns=benchmarks["BIL"],
        )
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
                    # sharpe_excess_bil is a top-level CandidateVerdict field,
                    # not a key inside .metrics (mechanism_eval.
                    # evaluate_candidate's full_metrics dict never includes
                    # it -- confirmed by reading its construction after the
                    # first real run crashed on this exact KeyError).
                    "sharpe_excess_bil": candidate_verdict.sharpe_excess_bil,
                    "max_drawdown": metrics["max_drawdown"],
                    "mar": metrics["mar"],
                    "benchmark_vm_capture_ratio": metrics["benchmark_vm_capture_ratio"],
                    "gates_passed": sum(gate_results.values()),
                    "gates_total": len(gate_results),
                    "all_gates_pass": candidate_verdict.all_gates_pass,
                    "dsr_trial_count": verdict.dsr_trial_count,
                }
            )
        result_queue.put(("ok", rows))
    except Exception as exc:  # noqa: BLE001 -- must always report back, never hang the parent
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def _run_experiment_in_subprocess(
    config: ExperimentConfig,
    factory,
    panel: pd.DataFrame,
    universe_panel: pd.DataFrame,
    benchmarks: dict[str, pd.Series],
) -> list[dict[str, object]]:
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_run_experiment_and_queue_rows,
        args=(config, factory, panel, universe_panel, benchmarks, result_queue),
    )
    process.start()
    status: str | None = None
    payload: object = None
    # Poll rather than a single blocking get(): a caught exception always
    # puts ("error", ...), but a signal (OOM-kill, SIGSEGV, ...) takes the
    # child out with nothing on the queue at all -- an unconditional
    # result_queue.get() would then hang the parent forever. is_alive()
    # going False with the queue still empty means exactly that happened.
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
            "before producing a result (likely killed by a signal -- exit code -9 is "
            "SIGKILL, typically a cgroup MemoryMax/MemorySwapMax enforcement (run under "
            "scripts/run_capped.sh: contained, the job alone dies and can be resumed); "
            "exit code -15 is SIGTERM, typically earlyoom reacting to *system-wide* free "
            "memory/swap dropping below its threshold -- this can fire even inside a "
            "capped cgroup scope, since MemoryMax only bounds this job's own usage, not "
            "how close the whole box's shared swap device is to exhaustion. See the Step "
            "11 ledger's 2026-09-08 entries for real examples of both.)"
        )
    if status == "error":
        raise RuntimeError(f"{config.experiment_id} subprocess raised: {payload}")
    if process.exitcode != 0:
        raise RuntimeError(f"{config.experiment_id} subprocess exited with code {process.exitcode}")
    return payload  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())
