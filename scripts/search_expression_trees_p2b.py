"""Work Item P2b: genetic-programming expression-tree search on real SIP daily bars.

Mechanism: an expression tree (``open_composer.research.kernel.expression_trees``)
computes a continuous score from QQQ's own OHLCV history; the strategy holds
QQQ when the score is positive at session T's close and BIL (cash-like)
otherwise, executed at T+1's open -- the same execution/cost convention as
``scripts/search_daily_momentum_p2a.py::simulate_momentum``, generalized from
one hand-written momentum feature to an arbitrary GP-evolved formula.

Per plan section 6.2, effective alphas are extremely sparse and finding
nothing is the expected, correct outcome -- this script does not relax any
gate if the run comes back empty, and says so plainly if it does.

Pipeline (plan sections 6.1/6.4/6.5, per-fold evolution per review item 3.3)
-----------------------------------------------------------------------------
1. Load QQQ/BIL/TQQQ real SIP daily bars (cheap: ~500MB for the whole
   market's 11-year history per the plan's own throughput budget, section
   6.5) and build the OHLCV frame the expression grammar reads from.
2. Layer 1 discovery, re-run from scratch per fold:
   :func:`expression_tree_search.run_nested_expression_gp_search` evolves a
   *fresh* population per ``rolling_origin_folds`` fold, each one bounded to
   that fold's own ``[train_start, train_end]`` window -- not the single
   2016-2021 development partition every fold used to share. Review item 3.3
   named that sharing as the residual defect after Work Item P1a's fix: a
   fixed *parameter vector* deployed across every fold was fixed one level
   too high; a fixed *expression-structure pool* evolved once and then only
   re-selected among per fold was the same defect one level higher still.
   Every generated expression is causality-checked
   (``expression_trees.validate_expression_is_causal``) before it can enter
   a population; a failure is rejected, not warned about.
3. HEADLINE: each fold's own elite pool becomes *that fold's* candidate pool
   for ``nested_walk_forward.run_nested_walk_forward``, via the driver's
   ``param_space_for_fold`` extension -- the correct entry point per the
   task spec, NOT ``layered_search.run_layered_search``'s deprecated global
   split. Each fold re-selects its own winner from *its own* pool using only
   that fold's own training window, then is scored only on that fold's own
   (never-before-read-during-selection-or-evolution) test window.
4. The DSR trial count charged to the final gate reflects the WHOLE
   per-fold search -- every expression *any* fold's evolution ever
   evaluated, deduplicated by formula (content-addressed
   ``expression_tree_search.expression_id``), not just the elites that made
   it into a fold's pool and not just one fold's population -- via
   ``effective_trials.effective_independent_trials`` clustered on the same
   out-of-sample calendar the procedure's own stitched stream spans.
5. The report includes, per fold: which expression won, its formula, and
   that fold's own GP evolution summary (population/generation counts,
   rejection counts, how many distinct expressions that fold alone
   evaluated); expression stability across folds (the GP analogue of
   parameter churn: reused verbatim from
   ``nested_walk_forward.ParameterStability``, because the tracked
   "parameter" here *is* the expression identity); the full trial
   accounting; and the gate outcome.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.kernel.effective_trials import (
    DEFAULT_CORRELATION_THRESHOLD,
    effective_independent_trials,
)
from open_composer.research.kernel.expression_tree_search import (
    DEFAULT_ELITE_CARRY,
    DEFAULT_GENERATION_COUNT,
    DEFAULT_POPULATION_SIZE,
    FoldGpResult,
    run_nested_expression_gp_search,
)
from open_composer.research.kernel.expression_trees import ExpressionNode, evaluate, formula_string
from open_composer.research.kernel.gate_contract import load_preregistered_gates
from open_composer.research.kernel.nested_walk_forward import (
    NestedWalkForwardResult,
    run_nested_walk_forward,
)
from open_composer.research.kernel.rolling_origin import returns_from_ohlcv, rolling_origin_folds
from open_composer.research.kernel.windows import WalkForwardSlice
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "research" / "search" / "expression-trees-p2b-search.json"

MECHANISM_FAMILY = "EXPR_GP"
SIGNAL_SYMBOLS = ("QQQ", "BIL")
BENCHMARK_SYMBOLS = ("QQQ", "TQQQ", "BIL")
PRIMARY_COST_BPS = 20.0
STRESS_COST_BPS = 40.0
FOLD_COUNT = 5
EMBARGO_BARS = 5

#: The base seed every fold's own seed is deterministically derived from
#: (``expression_tree_search.derive_fold_seed``) -- not used to seed any RNG
#: directly itself.
GP_BASE_SEED = 20260901
#: Thresholds must predate the result, so they come from a git-committed
#: contract rather than from a dict this script could edit afterwards.
GATE_CONTRACT_PATH = "config/promotion/kernel-paper-tier-gates.json"
CAMPAIGN_ID = "p2b-expression-trees-2026-09-01"

#: Minimum independent-trial floor -- matches
#: ``layered_search._MIN_DSR_TRIAL_COUNT``'s own reasoning: the smallest,
#: and therefore most conservative direction to round when clustering
#: collapses everything to very few effective trials.
_MIN_DSR_TRIAL_COUNT = 2


def _load_price_bundles() -> tuple[
    dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series], pd.DataFrame
]:
    """Load real SIP daily bars and build the shared-calendar OHLCV frame
    expression trees are evaluated against.

    Mirrors ``scripts/search_daily_momentum_p2a.py::_load_price_bundles``,
    extended to also return the full OHLCV frame (open/high/low/close/volume)
    that ``expression_trees.evaluate``/``validate_expression_is_causal``
    require.
    """
    raw = load_sip_bars(BENCHMARK_SYMBOLS, frequency="daily")
    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    highs: dict[str, pd.Series] = {}
    lows: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}
    benchmark_returns: dict[str, pd.Series] = {}
    for symbol in BENCHMARK_SYMBOLS:
        rows = raw.loc[raw["symbol"] == symbol].sort_values("timestamp")
        index = pd.DatetimeIndex(rows["timestamp"])
        closes[symbol] = pd.Series(
            pd.to_numeric(rows["close"], errors="raise").to_numpy(), index=index, name=symbol
        )
        opens[symbol] = pd.Series(
            pd.to_numeric(rows["open"], errors="raise").to_numpy(), index=index, name=symbol
        )
        highs[symbol] = pd.Series(
            pd.to_numeric(rows["high"], errors="raise").to_numpy(), index=index, name=symbol
        )
        lows[symbol] = pd.Series(
            pd.to_numeric(rows["low"], errors="raise").to_numpy(), index=index, name=symbol
        )
        volumes[symbol] = pd.Series(
            pd.to_numeric(rows["volume"], errors="raise").to_numpy(), index=index, name=symbol
        )
        benchmark_returns[symbol] = returns_from_ohlcv(rows)

    shared_index = closes["QQQ"].index.intersection(closes["BIL"].index).sort_values()
    frame = pd.DataFrame(
        {
            "open": opens["QQQ"].reindex(shared_index),
            "high": highs["QQQ"].reindex(shared_index),
            "low": lows["QQQ"].reindex(shared_index),
            "close": closes["QQQ"].reindex(shared_index),
            "volume": volumes["QQQ"].reindex(shared_index),
        }
    )
    return closes, opens, benchmark_returns, frame


def _simulate_expression_signal(
    tree: ExpressionNode,
    frame: pd.DataFrame,
    closes: dict[str, pd.Series],
    opens: dict[str, pd.Series],
    *,
    cost_bps: float,
) -> pd.Series:
    """Long QQQ when the tree's score is positive at close, else BIL.

    Same execution convention as ``search_daily_momentum_p2a.py::
    simulate_momentum``: decision confirmed at session T's close, executed
    at session T+1's open, cost charged only on an actual sleeve switch.

    Returns an **empty** Series (never raises) if the tree's score has no
    valid observation anywhere in history -- a legitimate outcome for a
    degenerate expression (e.g. a rolling z-score over a constant branch),
    which the caller's Layer 1 selection then filters out via the ordinary
    "no development observation" path rather than the whole run crashing on
    one bad formula.
    """
    score = evaluate(tree, frame)
    first_valid = score.first_valid_index()
    if first_valid is None:
        return pd.Series([], index=pd.DatetimeIndex([], tz=frame.index.tz), dtype=float)
    bullish = (score > 0.0).reindex(frame.index).fillna(False)

    index = frame.index
    sleeve_closes = {symbol: closes[symbol].reindex(index) for symbol in SIGNAL_SYMBOLS}
    sleeve_opens = {symbol: opens[symbol].reindex(index) for symbol in SIGNAL_SYMBOLS}

    dates = list(index)
    start = dates.index(first_valid) + 1

    current_sleeve = "BIL"
    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    for i in range(start, len(dates) - 1):
        decision, execution = dates[i], dates[i + 1]
        target_sleeve = "QQQ" if bool(bullish.loc[decision]) else "BIL"
        if target_sleeve != current_sleeve:
            day_return = float(
                sleeve_closes[target_sleeve].loc[execution]
                / sleeve_opens[target_sleeve].loc[execution]
                - 1.0
            )
            day_return -= (cost_bps / 10_000.0) * 2.0
            current_sleeve = target_sleeve
        else:
            day_return = float(
                sleeve_closes[current_sleeve].loc[execution]
                / sleeve_closes[current_sleeve].loc[decision]
                - 1.0
            )
        returns.append(day_return)
        return_dates.append(execution)

    series = pd.Series(returns, index=pd.DatetimeIndex(return_dates), name=MECHANISM_FAMILY)
    if series.isna().any():
        raise ValueError("expression reconstructed return series contains non-finite values")
    return series


def main() -> None:
    closes, opens, benchmark_returns, frame = _load_price_bundles()

    def raw_signal_fn(tree: ExpressionNode) -> pd.Series:
        return _simulate_expression_signal(tree, frame, closes, opens, cost_bps=PRIMARY_COST_BPS)

    def stress_signal_fn(tree: ExpressionNode) -> pd.Series:
        return _simulate_expression_signal(tree, frame, closes, opens, cost_bps=STRESS_COST_BPS)

    folds, stitched_benchmark = rolling_origin_folds(
        benchmark_returns["QQQ"], fold_count=FOLD_COUNT, embargo_bars=EMBARGO_BARS
    )

    # --- Per-fold GP evolution (review item 3.3) ----------------------------
    # A fresh evolution per fold, each one bounded to that fold's own
    # [train_start, train_end] -- not the single global 2016-2021 partition
    # every fold used to share. See run_nested_expression_gp_search's
    # docstring for why bounding the OHLCV frame itself (not just the
    # development_start/development_end bounds) is required to keep the
    # causal/informativeness admission checks -- not just the fitness
    # computation -- structurally blind to each fold's own test window and
    # to every later fold's data.
    fold_gp_results: list[FoldGpResult]
    fold_gp_results, all_individuals = run_nested_expression_gp_search(
        frame,
        raw_signal_fn=raw_signal_fn,
        benchmark_returns=benchmark_returns["QQQ"],
        folds=folds,
        base_seed=GP_BASE_SEED,
        population_size=DEFAULT_POPULATION_SIZE,
        generation_count=DEFAULT_GENERATION_COUNT,
        elite_carry=DEFAULT_ELITE_CARRY,
    )
    elite_ids_by_fold: dict[int, list[str]] = {
        result.fold: result.elite_expression_ids for result in fold_gp_results
    }

    # --- DSR trial accounting: charge the WHOLE per-fold search -------------
    # (plan section 6.2; review item 3.3's trial-accounting rule). Cluster
    # EVERY individual ANY fold's evolution ever constructed and admitted,
    # merged/deduplicated by formula (run_nested_expression_gp_search already
    # merges via expression_id's content hash), aligned onto a calendar
    # every one of them actually covers -- the intersection of each
    # individual's own index restricted to the stitched out-of-sample span,
    # so no candidate is excluded for a structural reason (e.g. the very
    # last bar, which no mechanism here can ever produce a forward return
    # for) rather than a real coverage gap.
    #
    # A small number of individuals are expected to be genuinely degenerate
    # (e.g. ``roll_zscore_20`` over a zero-variance constant branch produces
    # an all-NaN score, hence an empty return stream via
    # ``_simulate_expression_signal``) -- these have literally no
    # observation to correlate with anything, so effective-trials clustering
    # cannot include them, and they are excluded from the search population
    # used for clustering (never silently: ``degenerate_expression_count``
    # is reported alongside every other trial-accounting number below).
    raw_by_id: dict[str, pd.Series] = {
        expression_id: raw_signal_fn(tree) for expression_id, tree in all_individuals.items()
    }
    oos_start, oos_end = stitched_benchmark.index.min(), stitched_benchmark.index.max()
    degenerate_expression_ids = [
        expression_id for expression_id, series in raw_by_id.items() if series.empty
    ]
    coverable_ids = [
        expression_id
        for expression_id in raw_by_id
        if expression_id not in degenerate_expression_ids
    ]
    common_index: pd.DatetimeIndex | None = None
    for expression_id in coverable_ids:
        series = raw_by_id[expression_id]
        windowed = series.index[(series.index >= oos_start) & (series.index <= oos_end)]
        common_index = windowed if common_index is None else common_index.intersection(windowed)
    if common_index is None or len(common_index) < 2:
        raise ValueError("expression GP: no common out-of-sample calendar across the population")
    common_index = common_index.sort_values()

    aligned_returns: dict[str, list[float]] = {}
    for expression_id in coverable_ids:
        aligned = raw_by_id[expression_id].reindex(common_index)
        if aligned.isna().any():
            raise ValueError(f"{expression_id}: missing rows on the common OOS calendar")
        aligned_returns[expression_id] = aligned.tolist()

    search_trials = effective_independent_trials(
        aligned_returns, correlation_threshold=DEFAULT_CORRELATION_THRESHOLD
    )
    # The "elite pool" for trial-accounting purposes is now the union of
    # every fold's own elite pool -- each fold hands its own pool to
    # run_nested_walk_forward, so the union is the full set of expressions
    # that ever actually reached out-of-sample selection anywhere in the
    # procedure.
    elite_union_ids = sorted({eid for ids in elite_ids_by_fold.values() for eid in ids})
    elite_aligned = {
        expression_id: aligned_returns[expression_id]
        for expression_id in elite_union_ids
        if expression_id in aligned_returns
    }
    elite_trials = effective_independent_trials(
        elite_aligned, correlation_threshold=DEFAULT_CORRELATION_THRESHOLD
    )
    # Take the larger of "clustered over everything evaluated" and
    # "clustered over the union of every fold's gated elites" -- same
    # reasoning as ``layered_search.run_layered_search``'s own calibration:
    # this can only ever tighten the multiple-testing correction, never
    # loosen it.
    dsr_trial_count = max(search_trials.effective_n, elite_trials.effective_n, _MIN_DSR_TRIAL_COUNT)

    # --- HEADLINE: nested (anchored) walk-forward, one pool per fold -------
    def param_space_for_fold(fold: WalkForwardSlice) -> list[dict[str, Any]]:
        return [{"expression_id": expression_id} for expression_id in elite_ids_by_fold[fold.fold]]

    nested_result: NestedWalkForwardResult = run_nested_walk_forward(
        param_space_for_fold=param_space_for_fold,
        mechanism_family=MECHANISM_FAMILY,
        signal_fn=lambda params: raw_by_id[params["expression_id"]],
        stress_signal_fn=lambda params: stress_signal_fn(all_individuals[params["expression_id"]]),
        benchmark_returns=benchmark_returns["QQQ"],
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        campaign_id=CAMPAIGN_ID,
        gates=load_preregistered_gates(GATE_CONTRACT_PATH),
        fold_count=FOLD_COUNT,
        embargo_bars=EMBARGO_BARS,
        dsr_trial_count=dsr_trial_count,
        annualization_sessions=252,
    )

    # ``selected_candidate_id`` is run_nested_walk_forward's own positional
    # id ("{mechanism_family}-fold{fold:02d}-{index:03d}"); the actual
    # expression identity is inside ``selected_param_vector``.
    fold_reports = []
    for fold in nested_result.folds:
        winner_expression_id = fold.selected_param_vector["expression_id"]
        fold_reports.append(
            {
                "fold": fold.fold,
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "candidates_scored": fold.candidates_scored,
                "selected_expression_id": winner_expression_id,
                "selected_formula": formula_string(all_individuals[winner_expression_id]),
                "selected_training_score": fold.selected_training_score,
                "test_row_count": len(fold.test_returns),
            }
        )

    stability = nested_result.parameter_stability
    expression_churn = next(
        churn for churn in stability.per_parameter_churn if churn.parameter_name == "expression_id"
    )
    distinct_formulas_selected = sorted(
        {formula_string(all_individuals[eid]) for eid in expression_churn.values_by_fold}
    )

    gp_search_by_fold = [
        {
            "fold": result.fold,
            "seed": result.seed,
            "train_start": result.train_start,
            "train_end": result.train_end,
            "population_size": result.report.population_size,
            "generation_count": result.report.generation_count,
            "elite_carry": result.report.elite_carry,
            "total_individuals_evaluated": result.report.total_individuals_evaluated,
            "rejected_lookahead_count": result.report.rejected_lookahead_count,
            "rejected_degenerate_count": result.report.rejected_degenerate_count,
            "elite_pool_size": len(result.elite_expression_ids),
            "elite_formulas": [
                formula_string(all_individuals[eid]) for eid in result.elite_expression_ids
            ],
        }
        for result in fold_gp_results
    ]

    report: dict[str, Any] = {
        "mechanism_family": MECHANISM_FAMILY,
        "campaign_id": CAMPAIGN_ID,
        "fold_count": FOLD_COUNT,
        "primary_cost_bps": PRIMARY_COST_BPS,
        "stress_cost_bps": STRESS_COST_BPS,
        "gp_base_seed": GP_BASE_SEED,
        "gp_search_by_fold": gp_search_by_fold,
        "total_distinct_expressions_evaluated": len(all_individuals),
        "trial_accounting": {
            "total_individuals_evaluated": len(all_individuals),
            "degenerate_expression_count": len(degenerate_expression_ids),
            "clustered_individual_count": len(coverable_ids),
            "search_effective_n": search_trials.effective_n,
            "search_breadth_ratio": search_trials.breadth_ratio,
            "elite_union_pool_size": len(elite_union_ids),
            "elite_pool_effective_n": elite_trials.effective_n,
            "elite_pool_breadth_ratio": elite_trials.breadth_ratio,
            "dsr_trial_count_used": dsr_trial_count,
        },
        "nested_walk_forward": {
            "embargo_bars": nested_result.embargo_bars,
            "folds": fold_reports,
            # Expression stability across folds -- the GP analogue of
            # parameter churn: if every fold selects a structurally
            # different formula, that is strong evidence the search is
            # fitting noise, not finding a stable edge. This is far more
            # informative now than under the old global-evolution design:
            # a different winning formula per fold could previously only
            # come from *re-selecting* among a frozen pool, whereas now each
            # fold's whole pool is independently re-discovered.
            "expression_stability": {
                "fold_count": stability.fold_count,
                "distinct_expressions_selected": len(distinct_formulas_selected),
                "distinct_formulas_selected": distinct_formulas_selected,
                "churn_rate": expression_churn.churn_rate,
                "change_count": expression_churn.change_count,
                "total_transitions": expression_churn.total_transitions,
            },
            "procedure_oos_row_count": len(nested_result.procedure_candidate.oos_return_stream),
            "procedure_metrics": nested_result.procedure_verdict.metrics,
            "procedure_dsr_probability": nested_result.procedure_verdict.dsr_probability,
            "procedure_sharpe_excess_bil": nested_result.procedure_verdict.sharpe_excess_bil,
            "procedure_positive_fold_fraction": (
                nested_result.procedure_verdict.positive_fold_fraction
            ),
            "procedure_orthogonal_to_qqq": nested_result.procedure_verdict.orthogonal_to_qqq,
            "procedure_gate_results": nested_result.procedure_verdict.gate_results,
            "procedure_all_gates_pass": nested_result.procedure_verdict.all_gates_pass,
            # Passing every gate is necessary and not sufficient: eligibility
            # also requires the bar to have been committed in advance.
            "procedure_promotion_eligible": nested_result.procedure_verdict.promotion_eligible,
            "gates_provenance": nested_result.procedure_verdict.gates_provenance,
            "gate_contract": nested_result.procedure_verdict.gate_contract,
        },
    }
    write_json(OUTPUT_PATH, report)

    print("=== Work Item P2b: expression-tree GP search (per-fold evolution, review item 3.3) ===")
    print(f"base_seed={GP_BASE_SEED}  fold_count={FOLD_COUNT}  embargo_bars={EMBARGO_BARS}")
    for fold_result in fold_gp_results:
        print(
            f"  fold {fold_result.fold}: seed={fold_result.seed} "
            f"train=[{fold_result.train_start}..{fold_result.train_end}] "
            f"individuals_evaluated={fold_result.report.total_individuals_evaluated} "
            f"elites={len(fold_result.elite_expression_ids)}"
        )
    print(f"total_distinct_expressions_evaluated={len(all_individuals)}")

    print("\n=== Trial accounting (plan section 6.2 / review item 3.3: charge every fold) ===")
    print(
        f"total_individuals_evaluated={len(all_individuals)}  "
        f"degenerate_expression_count={len(degenerate_expression_ids)}  "
        f"clustered_individual_count={len(coverable_ids)}"
    )
    print(
        f"search_effective_n={search_trials.effective_n} "
        f"(breadth_ratio={search_trials.breadth_ratio:.4f} over "
        f"{len(coverable_ids)} clustered)"
    )
    print(
        f"elite_pool_effective_n={elite_trials.effective_n} "
        f"(breadth_ratio={elite_trials.breadth_ratio:.4f} over {len(elite_union_ids)} "
        "union-of-fold-elites)"
    )
    print(f"dsr_trial_count_used={dsr_trial_count}")

    print("\n=== HEADLINE: nested (anchored) walk-forward procedure ===")
    for fold_report in fold_reports:
        print(
            f"  fold {fold_report['fold']}: test=[{fold_report['test_start']}.."
            f"{fold_report['test_end']}] selected={fold_report['selected_expression_id']} "
            f"formula={fold_report['selected_formula']} "
            f"training_score={fold_report['selected_training_score']:.4f} "
            f"test_rows={fold_report['test_row_count']}"
        )
    print(
        f"expression_stability: {len(distinct_formulas_selected)} distinct formula(s) selected "
        f"across {stability.fold_count} fold(s) (churn_rate="
        f"{expression_churn.churn_rate:.2f})"
    )
    for formula in distinct_formulas_selected:
        print(f"  selected at some fold: {formula}")
    print(f"procedure_oos_row_count={report['nested_walk_forward']['procedure_oos_row_count']}")
    print(f"procedure_dsr_probability={nested_result.procedure_verdict.dsr_probability:.4f}")
    print(f"procedure_sharpe_excess_bil={nested_result.procedure_verdict.sharpe_excess_bil:.4f}")
    print(
        "procedure_positive_fold_fraction="
        f"{nested_result.procedure_verdict.positive_fold_fraction:.4f}"
    )
    print(f"procedure_gate_results={nested_result.procedure_verdict.gate_results}")
    print(f"procedure_all_gates_pass={nested_result.procedure_verdict.all_gates_pass}")
    if not nested_result.procedure_verdict.all_gates_pass:
        print(
            "\nNo candidate passed the full gate battery. Per plan section 6.2, effective "
            "alphas are extremely sparse and this is the expected, correct outcome of an "
            "honest search -- not a failure of the search pipeline, and gates are not "
            "relaxed to manufacture a pass."
        )
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
