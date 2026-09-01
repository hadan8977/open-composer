"""GP driver tests (Work Item P2b): generation/mutation/crossover limits,
determinism, and the "track everything evaluated, not just the survivors"
property the DSR trial accounting depends on.

All fixtures here are small and synthetic on purpose -- this file's job is
to exercise the search *mechanics* fast; the real run against SIP daily bars
lives in ``scripts/search_expression_trees_p2b.py``, not in the test suite.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.effective_trials import (
    DEFAULT_CORRELATION_THRESHOLD,
    effective_independent_trials,
)
from open_composer.research.kernel.expression_tree_search import (
    GpSearchResult,
    crossover_trees,
    mutate_tree,
    random_expression_tree,
    run_expression_gp_search,
)
from open_composer.research.kernel.expression_trees import (
    MAX_NODE_COUNT,
    MAX_TREE_DEPTH,
    evaluate,
)
from open_composer.research.kernel.nested_walk_forward import run_nested_walk_forward
from open_composer.research.kernel.rolling_origin import rolling_origin_folds

# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

_N_ROWS = 500
_SIGNAL_SYMBOLS = ("RISK", "CASH")


def _synthetic_frame(*, n: int = _N_ROWS, seed: int = 0) -> pd.DataFrame:
    index = pd.bdate_range("2019-01-02", periods=n, tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.011, n))
    open_ = close * (1.0 + rng.normal(0.0, 0.001, n))
    high = np.maximum(close, open_) * (1.0 + np.abs(rng.normal(0.0, 0.004, n)))
    low = np.minimum(close, open_) * (1.0 - np.abs(rng.normal(0.0, 0.004, n)))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def _cash_sleeve(index: pd.DatetimeIndex, *, seed: int = 1) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.00005, 0.0002, len(index)))
    open_ = close * (1.0 + rng.normal(0.0, 0.00005, len(index)))
    return pd.Series(close, index=index), pd.Series(open_, index=index)


def _make_raw_signal_fn(
    frame: pd.DataFrame, *, cost_bps: float = 20.0
) -> tuple[callable, pd.Series]:
    """A "long RISK vs CASH" execution function generalizing
    ``scripts/search_daily_momentum_p2a.py::simulate_momentum`` to an
    arbitrary expression-tree score, for testing the GP driver end to end.
    """
    risk_close = frame["close"]
    risk_open = frame["open"]
    cash_close, cash_open = _cash_sleeve(frame.index)
    closes = {"RISK": risk_close, "CASH": cash_close}
    opens = {"RISK": risk_open, "CASH": cash_open}

    def raw_signal_fn(tree) -> pd.Series:
        score = evaluate(tree, frame)
        first_valid = score.first_valid_index()
        if first_valid is None:
            # Degenerate expression (e.g. a rolling z-score over a
            # zero-variance branch): no valid observation, ever. An empty
            # Series -- not a raised error -- is the documented contract
            # ``run_expression_gp_search`` relies on to filter these out via
            # the ordinary Layer 1 "no development observation" path.
            return pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
        bullish = (score > 0.0).reindex(frame.index).fillna(False)
        dates = list(frame.index)
        start = dates.index(first_valid) + 1
        current = "CASH"
        returns: list[float] = []
        return_dates: list[pd.Timestamp] = []
        for i in range(start, len(dates) - 1):
            decision, execution = dates[i], dates[i + 1]
            target = "RISK" if bool(bullish.loc[decision]) else "CASH"
            if target != current:
                day_return = float(
                    closes[target].loc[execution] / opens[target].loc[execution] - 1.0
                )
                day_return -= (cost_bps / 10_000.0) * 2.0
                current = target
            else:
                day_return = float(
                    closes[current].loc[execution] / closes[current].loc[decision] - 1.0
                )
            returns.append(day_return)
            return_dates.append(execution)
        return pd.Series(returns, index=pd.DatetimeIndex(return_dates))

    benchmark_returns = risk_close.pct_change().dropna()
    return raw_signal_fn, benchmark_returns


def _run_small_search(*, seed: int, population_size: int = 10, generation_count: int = 3):
    frame = _synthetic_frame()
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)
    development_start = frame.index[20].isoformat()
    development_end = frame.index[300].isoformat()
    return run_expression_gp_search(
        frame,
        raw_signal_fn=raw_signal_fn,
        benchmark_returns=benchmark_returns,
        development_start=development_start,
        development_end=development_end,
        seed=seed,
        population_size=population_size,
        generation_count=generation_count,
        elite_carry=4,
    )


# ---------------------------------------------------------------------------
# random_expression_tree / mutate_tree / crossover_trees: limits + determinism
# ---------------------------------------------------------------------------


def test_random_expression_tree_always_respects_limits() -> None:
    rng = np.random.default_rng(2024)
    for _ in range(300):
        tree = random_expression_tree(rng)
        assert tree.depth <= MAX_TREE_DEPTH
        assert tree.size <= MAX_NODE_COUNT


def test_random_expression_tree_is_deterministic_given_seed() -> None:
    from open_composer.research.kernel.expression_trees import formula_string

    first = random_expression_tree(np.random.default_rng(555))
    second = random_expression_tree(np.random.default_rng(555))
    assert formula_string(first) == formula_string(second)


def test_mutate_and_crossover_always_respect_limits() -> None:
    rng = np.random.default_rng(11)
    population = [random_expression_tree(rng) for _ in range(15)]
    for i in range(150):
        parent_a = population[i % len(population)]
        parent_b = population[(i + 5) % len(population)]
        mutant = mutate_tree(parent_a, rng)
        assert mutant.depth <= MAX_TREE_DEPTH
        assert mutant.size <= MAX_NODE_COUNT
        child = crossover_trees(parent_a, parent_b, rng)
        assert child.depth <= MAX_TREE_DEPTH
        assert child.size <= MAX_NODE_COUNT


def test_mutate_and_crossover_are_deterministic_given_seed() -> None:
    from open_composer.research.kernel.expression_trees import formula_string

    rng_seed_population = np.random.default_rng(3)
    population = [random_expression_tree(rng_seed_population) for _ in range(10)]

    rng_a = np.random.default_rng(77)
    rng_b = np.random.default_rng(77)
    mutant_a = mutate_tree(population[0], rng_a)
    mutant_b = mutate_tree(population[0], rng_b)
    assert formula_string(mutant_a) == formula_string(mutant_b)

    child_a = crossover_trees(population[1], population[2], np.random.default_rng(9))
    child_b = crossover_trees(population[1], population[2], np.random.default_rng(9))
    assert formula_string(child_a) == formula_string(child_b)


# ---------------------------------------------------------------------------
# run_expression_gp_search: the evolutionary loop
# ---------------------------------------------------------------------------


def test_run_expression_gp_search_is_deterministic_given_seed() -> None:
    report_a, individuals_a, elites_a = _run_small_search(seed=42)
    report_b, individuals_b, elites_b = _run_small_search(seed=42)

    assert report_a.model_dump() == report_b.model_dump()
    assert elites_a == elites_b
    assert set(individuals_a) == set(individuals_b)


def test_run_expression_gp_search_different_seeds_can_diverge() -> None:
    report_a, _, _ = _run_small_search(seed=1)
    report_b, _, _ = _run_small_search(seed=2)
    # Not a hard requirement that they *must* differ, but with independent
    # seeds over a real random population they should not coincidentally
    # produce byte-identical reports -- this guards against a bug that
    # ignores ``seed`` entirely.
    assert report_a.model_dump() != report_b.model_dump()


def test_run_expression_gp_search_tracks_every_individual_not_just_survivors() -> None:
    """Plan section 6.2: the DSR trial count is charged for the whole
    search, not the survivors. That is only possible if the driver actually
    keeps a record of every individual it ever evaluated, not just the
    final elites -- this is the property the calling script's trial
    accounting depends on.
    """
    report, all_individuals, final_elite_ids = _run_small_search(
        seed=7, population_size=12, generation_count=4
    )
    assert isinstance(report, GpSearchResult)
    assert report.total_individuals_evaluated == len(all_individuals)
    assert len(all_individuals) > len(final_elite_ids)
    # Every generation's summary is itself present in the report, so the
    # per-generation counts (population/survivor/elite) are auditable.
    assert len(report.generations) == 4
    assert all(g.layer1_survivor_count >= g.layer2_elite_count for g in report.generations)


def test_run_expression_gp_search_every_individual_is_within_structural_limits() -> None:
    _, all_individuals, _ = _run_small_search(seed=13)
    for tree in all_individuals.values():
        assert tree.depth <= MAX_TREE_DEPTH
        assert tree.size <= MAX_NODE_COUNT


def test_run_expression_gp_search_never_admits_a_degenerate_expression() -> None:
    """Regression for a real failure: a constant-only tree (e.g.
    ``mul(roll_mean_5(roll_mean_20(0.2)), neg(max2(-0.02, 0.05)))``) has a
    structural advantage under raw-Sharpe Layer 1 quality (it trivially
    mimics "always hold the low-volatility cash sleeve") and, worse, breaks
    the downstream gate (zero-variance excess-of-BIL return is an undefined
    Sharpe). Every individual the search actually admits must have real
    variance in its own score.
    """
    from open_composer.research.kernel.expression_trees import evaluate

    frame = _synthetic_frame()
    report, all_individuals, _ = _run_small_search(seed=41, population_size=16, generation_count=4)
    assert report.rejected_degenerate_count >= 0  # always present, may be zero on a given seed
    for expression_id, tree in all_individuals.items():
        output = evaluate(tree, frame).dropna().to_numpy()
        assert output.size > 0, expression_id
        assert output.std() > 1e-9, f"{expression_id} is degenerate (near-zero variance)"


def test_run_expression_gp_search_rejects_degenerate_configuration() -> None:
    frame = _synthetic_frame()
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)
    with pytest.raises(ValueError, match="population_size"):
        run_expression_gp_search(
            frame,
            raw_signal_fn=raw_signal_fn,
            benchmark_returns=benchmark_returns,
            development_start=frame.index[20].isoformat(),
            development_end=frame.index[300].isoformat(),
            seed=1,
            population_size=1,
        )


# ---------------------------------------------------------------------------
# Integration: the GP search's elites actually flow through
# ``run_nested_walk_forward`` (the correct entry point per the task spec --
# NOT ``layered_search.run_layered_search``'s deprecated global split).
# ---------------------------------------------------------------------------


def test_gp_elites_run_through_nested_walk_forward_end_to_end() -> None:
    frame = _synthetic_frame(n=1900, seed=21)  # ~7.5 years of business days
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)

    folds, _stitched = rolling_origin_folds(benchmark_returns, fold_count=3, embargo_bars=5)
    development_start = folds[0].train.train_start
    development_end = folds[0].train.train_end

    report, all_individuals, final_elite_ids = run_expression_gp_search(
        frame,
        raw_signal_fn=raw_signal_fn,
        benchmark_returns=benchmark_returns,
        development_start=development_start,
        development_end=development_end,
        seed=99,
        population_size=8,
        generation_count=2,
        elite_carry=3,
    )
    assert len(final_elite_ids) >= 1

    # DSR trial accounting must reflect the whole search (plan section 6.2),
    # not just the final elites -- computed here the same way
    # ``scripts/search_expression_trees_p2b.py`` does: cluster every
    # individual's return stream on a calendar every individual actually
    # covers.
    raw_by_id = {
        expression_id: raw_signal_fn(tree) for expression_id, tree in all_individuals.items()
    }
    oos_start, oos_end = _stitched.index.min(), _stitched.index.max()
    common_index = None
    for series in raw_by_id.values():
        windowed = series.index[(series.index >= oos_start) & (series.index <= oos_end)]
        common_index = windowed if common_index is None else common_index.intersection(windowed)
    assert common_index is not None and len(common_index) >= 2
    aligned_returns = {
        expression_id: series.reindex(common_index).tolist()
        for expression_id, series in raw_by_id.items()
    }
    search_trials = effective_independent_trials(
        aligned_returns, correlation_threshold=DEFAULT_CORRELATION_THRESHOLD
    )
    assert search_trials.raw_candidate_count == len(all_individuals)
    dsr_trial_count = max(search_trials.effective_n, 2)

    rng = np.random.default_rng(31)
    qqq = pd.Series(rng.normal(0.0004, 0.01, len(frame.index)), index=frame.index)
    tqqq = pd.Series(rng.normal(0.0009, 0.03, len(frame.index)), index=frame.index)
    bil = pd.Series(rng.normal(0.00005, 0.0002, len(frame.index)), index=frame.index)

    param_space = [{"expression_id": expression_id} for expression_id in final_elite_ids]
    nested_result = run_nested_walk_forward(
        param_space,
        mechanism_family="EXPR_GP_TEST",
        signal_fn=lambda params: raw_by_id[params["expression_id"]],
        benchmark_returns=benchmark_returns,
        qqq_returns=qqq,
        tqqq_returns=tqqq,
        bil_returns=bil,
        campaign_id="expr-gp-test",
        fold_count=3,
        embargo_bars=5,
        dsr_trial_count=dsr_trial_count,
    )

    assert nested_result.fold_count == 3
    # "Expression stability across folds" falls out of the existing
    # parameter-stability machinery for free: the tracked "parameter" here
    # *is* the expression identity, so its churn rate is exactly the
    # fold-to-fold formula-change rate.
    stability = nested_result.parameter_stability
    assert stability.fold_count == 3
    churn_names = {churn.parameter_name for churn in stability.per_parameter_churn}
    assert churn_names == {"expression_id"}
    for fold_result in nested_result.folds:
        # ``selected_candidate_id`` is ``run_nested_walk_forward``'s own
        # positional id (``"{mechanism_family}-{index:03d}"``); the actual
        # expression identity is inside ``selected_param_vector`` -- this is
        # exactly how the real script must translate a fold's winner back to
        # a formula for the report.
        assert fold_result.selected_param_vector["expression_id"] in all_individuals
    assert isinstance(nested_result.procedure_verdict.all_gates_pass, bool)
