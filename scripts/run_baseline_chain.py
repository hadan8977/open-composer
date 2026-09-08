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
"""

from __future__ import annotations

import json
import multiprocessing
import sys
import time
from pathlib import Path
from queue import Empty as QueueEmpty

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

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


#: Only pull the columns the B0/B1/B2 baselines (and run_experiment's own
#: price pivot / beta-hedge weighting) actually touch -- data/features/daily
#: carries ~27-47 columns per year once intraday joins land, but this round
#: is daily_only and needs at most identifiers + B2_FEATURE_COLUMNS. Reading
#: a column subset keeps the concatenated 11-year panel far smaller than the
#: full archive (see scripts/build_daily_features.py's module docstring for
#: the real OOM-adjacent incident this mirrors the fix for).
_DAILY_READ_COLUMNS = sorted({"symbol", "trade_date", "close", *B2_FEATURE_COLUMNS})
_LABEL_READ_COLUMNS = ["symbol", "trade_date", LABEL_COLUMN]


def _load_panel(feature_set: str = "daily_only") -> pd.DataFrame:
    if feature_set != "daily_only":
        raise NotImplementedError("daily_plus_intraday joins land once the backfill is complete")

    # Merge per year, then concat the (much smaller) merged results -- one
    # 11-year-vs-11-year merge peaks far higher than 11 single-year merges,
    # because pandas' hash join briefly holds both full inputs *and* the
    # output alive at once. Real incident: this used to concat all 11 years
    # of daily + all 11 years of labels first and merge once, which grew RSS
    # past 2.6GB and was still climbing after a full minute (see
    # scripts/build_daily_features.py's module docstring for the sibling
    # incident this mirrors the fix for).
    years = sorted(int(p.stem) for p in DAILY_FEATURES_ROOT.glob("*.parquet") if p.stem.isdigit())
    merged_frames = []
    for year in years:
        daily_year = pd.read_parquet(
            DAILY_FEATURES_ROOT / f"{year}.parquet", columns=_DAILY_READ_COLUMNS
        )
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
        merged_frames.append(daily_year.merge(label_year, on=["symbol", "trade_date"], how="inner"))
        del daily_year, label_year

    panel = pd.concat(merged_frames, ignore_index=True)
    del merged_frames
    return panel


def main() -> int:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] loading daily+label panel ...", flush=True)
    panel = _load_panel()
    print(f"panel: {len(panel)} rows, {panel['symbol'].nunique()} symbols", flush=True)

    universe_panel = load_universe_panel(UNIVERSE_ROOT)

    print("loading SPY/QQQ/TQQQ/BIL benchmark returns ...", flush=True)
    benchmarks = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }

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
    ]

    summary_rows = []
    for config, factory in configs:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] running {config.experiment_id} "
            f"(in its own subprocess) ...",
            flush=True,
        )
        started = time.monotonic()
        rows = _run_experiment_in_subprocess(config, factory, panel, universe_panel, benchmarks)
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
            "before producing a result (likely killed -- e.g. exit code -9 is SIGKILL/OOM)"
        )
    if status == "error":
        raise RuntimeError(f"{config.experiment_id} subprocess raised: {payload}")
    if process.exitcode != 0:
        raise RuntimeError(f"{config.experiment_id} subprocess exited with code {process.exitcode}")
    return payload  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())
