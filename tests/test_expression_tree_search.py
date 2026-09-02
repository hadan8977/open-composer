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
    FoldGpResult,
    GpSearchResult,
    crossover_trees,
    derive_fold_seed,
    mutate_tree,
    random_expression_tree,
    run_expression_gp_search,
    run_nested_expression_gp_search,
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


def _make_raw_signal_fn_with_sleeves(
    frame: pd.DataFrame,
    cash_close: pd.Series,
    cash_open: pd.Series,
    *,
    cost_bps: float = 20.0,
):
    """A "long RISK vs CASH" execution function generalizing
    ``scripts/search_daily_momentum_p2a.py::simulate_momentum`` to an
    arbitrary expression-tree score, for testing the GP driver end to end.

    Sleeves are taken as explicit arguments (rather than built internally,
    as ``_make_raw_signal_fn`` below does for the common case) so a caller
    can build a "clean" and a "poisoned" raw-signal function that agree on
    everything except a specific window of rows -- see the per-fold
    poisoning test.
    """
    risk_close = frame["close"]
    risk_open = frame["open"]
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

    return raw_signal_fn


def _make_raw_signal_fn(
    frame: pd.DataFrame, *, cost_bps: float = 20.0
) -> tuple[callable, pd.Series]:
    cash_close, cash_open = _cash_sleeve(frame.index)
    raw_signal_fn = _make_raw_signal_fn_with_sleeves(
        frame, cash_close, cash_open, cost_bps=cost_bps
    )
    benchmark_returns = frame["close"].pct_change().dropna()
    return raw_signal_fn, benchmark_returns


def _poison_ohlcv_window(
    frame: pd.DataFrame,
    cash_close: pd.Series,
    cash_open: pd.Series,
    *,
    start: str,
    end: str,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Replace every row in ``[start, end]`` with a clearly synthetic,
    deterministic price pattern unrelated to the organic random walk that
    built ``frame``/the cash sleeve.

    This is the OHLCV analogue of
    ``test_kernel_nested_walk_forward.py::_poison_window``: that helper
    poisons a pre-built return series, which works when ``signal_fn`` maps a
    parameter straight onto a prebuilt series. Here, every candidate's
    return stream is *derived* from the shared OHLCV frame via
    ``evaluate(tree, frame)``, so poisoning has to happen one level down, on
    the raw prices themselves, for the resulting return streams (whichever
    tree produces them) to actually change.
    """
    mask = (frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))
    count = int(mask.sum())
    assert count > 0, "poison window must overlap the frame"
    pattern = 200.0 + np.array([15.0 if i % 2 == 0 else -15.0 for i in range(count)])

    poisoned_frame = frame.copy()
    poisoned_frame.loc[mask, "close"] = pattern
    poisoned_frame.loc[mask, "open"] = pattern * 0.998
    poisoned_frame.loc[mask, "high"] = pattern * 1.02
    poisoned_frame.loc[mask, "low"] = pattern * 0.98
    poisoned_frame.loc[mask, "volume"] = 9_000_000.0

    cash_mask = (cash_close.index >= pd.Timestamp(start)) & (cash_close.index <= pd.Timestamp(end))
    cash_count = int(cash_mask.sum())
    cash_pattern = 50.0 + np.array([-3.0 if i % 2 == 0 else 3.0 for i in range(cash_count)])
    poisoned_cash_close = cash_close.copy()
    poisoned_cash_open = cash_open.copy()
    poisoned_cash_close.loc[cash_mask] = cash_pattern
    poisoned_cash_open.loc[cash_mask] = cash_pattern * 0.999
    return poisoned_frame, poisoned_cash_close, poisoned_cash_open


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


# ---------------------------------------------------------------------------
# derive_fold_seed: deterministic per-fold seed derivation.
# ---------------------------------------------------------------------------


def test_derive_fold_seed_is_deterministic() -> None:
    assert derive_fold_seed(20260901, 3) == derive_fold_seed(20260901, 3)


def test_derive_fold_seed_differs_across_folds() -> None:
    seeds = {derive_fold_seed(20260901, fold) for fold in range(1, 6)}
    assert len(seeds) == 5


def test_derive_fold_seed_differs_across_base_seeds() -> None:
    assert derive_fold_seed(1, 1) != derive_fold_seed(2, 1)


# ---------------------------------------------------------------------------
# run_nested_expression_gp_search: a fresh evolution per fold (review item
# 3.3 -- the expression *structure*, not just which pre-evolved expression
# wins, must be re-discovered on each fold's own training window).
# ---------------------------------------------------------------------------


def _run_small_nested_search(
    *,
    frame: pd.DataFrame,
    raw_signal_fn,
    benchmark_returns: pd.Series,
    fold_count: int = 3,
    embargo_bars: int = 5,
    base_seed: int = 2026,
    population_size: int = 10,
    generation_count: int = 3,
    elite_carry: int = 4,
):
    folds, stitched = rolling_origin_folds(
        benchmark_returns, fold_count=fold_count, embargo_bars=embargo_bars
    )
    fold_results, all_individuals = run_nested_expression_gp_search(
        frame,
        raw_signal_fn=raw_signal_fn,
        benchmark_returns=benchmark_returns,
        folds=folds,
        base_seed=base_seed,
        population_size=population_size,
        generation_count=generation_count,
        elite_carry=elite_carry,
    )
    return folds, stitched, fold_results, all_individuals


def test_run_nested_expression_gp_search_rejects_empty_folds() -> None:
    frame = _synthetic_frame(n=1900, seed=21)
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)
    with pytest.raises(ValueError, match="folds"):
        run_nested_expression_gp_search(
            frame,
            raw_signal_fn=raw_signal_fn,
            benchmark_returns=benchmark_returns,
            folds=[],
            base_seed=1,
        )


def test_run_nested_expression_gp_search_evolves_one_population_per_fold() -> None:
    frame = _synthetic_frame(n=1900, seed=21)
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)
    folds, _stitched, fold_results, all_individuals = _run_small_nested_search(
        frame=frame, raw_signal_fn=raw_signal_fn, benchmark_returns=benchmark_returns
    )

    assert len(fold_results) == len(folds) == 3
    for fold_result, fold in zip(fold_results, folds, strict=True):
        assert isinstance(fold_result, FoldGpResult)
        assert fold_result.fold == fold.fold
        assert fold_result.train_start == fold.train.train_start
        assert fold_result.train_end == fold.train.train_end
        assert fold_result.seed == derive_fold_seed(2026, fold.fold)
        # Each fold's own GP evolution used only that fold's own training
        # bounds -- not the global development partition.
        assert fold_result.report.development_start == fold.train.train_start
        assert fold_result.report.development_end == fold.train.train_end
        assert len(fold_result.elite_expression_ids) >= 1
        assert fold_result.report.total_individuals_evaluated >= len(
            fold_result.elite_expression_ids
        )

    # Merged, deduplicated across every fold's own evolution: the union can
    # never exceed the sum of each fold's own count, and every fold's own
    # elites must actually be present in the merged pool.
    assert len(all_individuals) <= sum(
        fold_result.report.total_individuals_evaluated for fold_result in fold_results
    )
    for fold_result in fold_results:
        for expression_id in fold_result.elite_expression_ids:
            assert expression_id in all_individuals


def test_run_nested_expression_gp_search_is_deterministic_given_base_seed() -> None:
    frame = _synthetic_frame(n=1900, seed=21)
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)

    _, _, first_results, first_individuals = _run_small_nested_search(
        frame=frame, raw_signal_fn=raw_signal_fn, benchmark_returns=benchmark_returns
    )
    _, _, second_results, second_individuals = _run_small_nested_search(
        frame=frame, raw_signal_fn=raw_signal_fn, benchmark_returns=benchmark_returns
    )

    assert [r.model_dump() for r in first_results] == [r.model_dump() for r in second_results]
    assert set(first_individuals) == set(second_individuals)


def test_run_nested_expression_gp_search_every_individual_is_within_structural_limits() -> None:
    frame = _synthetic_frame(n=1900, seed=21)
    raw_signal_fn, benchmark_returns = _make_raw_signal_fn(frame)
    _, _, _, all_individuals = _run_small_nested_search(
        frame=frame, raw_signal_fn=raw_signal_fn, benchmark_returns=benchmark_returns
    )
    for tree in all_individuals.values():
        assert tree.depth <= MAX_TREE_DEPTH
        assert tree.size <= MAX_NODE_COUNT


# ---------------------------------------------------------------------------
# The correctness rule (review item 3.3): a fold's own test window must be
# unreadable during that fold's own GP evolution AND selection. Poisoning
# is done for exactly one fold's test window at a time -- rolling_origin_folds
# is anchored, so a *later* fold's training window legitimately includes an
# *earlier* fold's now-historical test window, and poisoning every fold at
# once would conflate that intended behaviour with an actual leak.
# ---------------------------------------------------------------------------


def test_poisoning_a_folds_own_test_window_does_not_change_that_folds_gp_evolution() -> None:
    frame = _synthetic_frame(n=1900, seed=21)
    cash_close, cash_open = _cash_sleeve(frame.index)
    benchmark_returns = frame["close"].pct_change().dropna()
    folds, _stitched = rolling_origin_folds(benchmark_returns, fold_count=3, embargo_bars=5)
    target = folds[1]  # not fold 1, so an earlier fold is exercised too

    poisoned_frame, poisoned_cash_close, poisoned_cash_open = _poison_ohlcv_window(
        frame, cash_close, cash_open, start=target.train.test_start, end=target.train.test_end
    )

    clean_raw_signal_fn = _make_raw_signal_fn_with_sleeves(frame, cash_close, cash_open)
    poisoned_raw_signal_fn = _make_raw_signal_fn_with_sleeves(
        poisoned_frame, poisoned_cash_close, poisoned_cash_open
    )

    clean_results, _ = run_nested_expression_gp_search(
        frame,
        raw_signal_fn=clean_raw_signal_fn,
        benchmark_returns=benchmark_returns,
        folds=folds,
        base_seed=2026,
        population_size=10,
        generation_count=3,
        elite_carry=4,
    )
    poisoned_results, _ = run_nested_expression_gp_search(
        poisoned_frame,
        raw_signal_fn=poisoned_raw_signal_fn,
        benchmark_returns=benchmark_returns,
        folds=folds,
        base_seed=2026,
        population_size=10,
        generation_count=3,
        elite_carry=4,
    )

    for clean_fold, poisoned_fold in zip(clean_results, poisoned_results, strict=True):
        if clean_fold.fold <= target.fold:
            # Every fold up to and including the target trains on data that
            # ends strictly before the target's own test window starts, so
            # poisoning that window must leave the *entire* evolved
            # population, not just the elites, byte-identical.
            assert clean_fold.seed == poisoned_fold.seed
            assert clean_fold.report.model_dump() == poisoned_fold.report.model_dump()
            assert clean_fold.elite_expression_ids == poisoned_fold.elite_expression_ids
        # Later folds are deliberately not checked here: rolling_origin_folds
        # is anchored, so a later fold's training window legitimately (and
        # correctly) includes the target's now-historical test window --
        # asserting equality there would conflate that with an actual leak.


def test_poisoning_a_folds_own_test_window_changes_only_that_folds_test_returns() -> None:
    """The full pipeline: per-fold GP evolution feeding
    ``run_nested_walk_forward`` via ``param_space_for_fold``. Poisoning
    exactly one fold's test window must leave every *selection* output for
    that fold (and every earlier fold, entirely) unchanged, while the
    poisoned fold's own test-window returns -- read only after selection is
    complete -- must actually differ. This is the same property
    ``test_kernel_nested_walk_forward.py``'s own poisoning tests prove for
    a fixed pool, extended one level up to a pool that is itself
    re-evolved per fold.
    """
    frame = _synthetic_frame(n=1900, seed=21)
    cash_close, cash_open = _cash_sleeve(frame.index)
    benchmark_returns = frame["close"].pct_change().dropna()
    folds, _stitched = rolling_origin_folds(benchmark_returns, fold_count=3, embargo_bars=5)
    target = folds[1]

    poisoned_frame, poisoned_cash_close, poisoned_cash_open = _poison_ohlcv_window(
        frame, cash_close, cash_open, start=target.train.test_start, end=target.train.test_end
    )

    clean_raw_signal_fn = _make_raw_signal_fn_with_sleeves(frame, cash_close, cash_open)
    poisoned_raw_signal_fn = _make_raw_signal_fn_with_sleeves(
        poisoned_frame, poisoned_cash_close, poisoned_cash_open
    )

    def _run_end_to_end(frame_, raw_signal_fn):
        fold_results, all_individuals = run_nested_expression_gp_search(
            frame_,
            raw_signal_fn=raw_signal_fn,
            benchmark_returns=benchmark_returns,
            folds=folds,
            base_seed=2026,
            population_size=10,
            generation_count=3,
            elite_carry=4,
        )
        elite_ids_by_fold = {result.fold: result.elite_expression_ids for result in fold_results}
        raw_by_id = {
            expression_id: raw_signal_fn(tree) for expression_id, tree in all_individuals.items()
        }

        def param_space_for_fold(fold):
            return [{"expression_id": eid} for eid in elite_ids_by_fold[fold.fold]]

        rng = np.random.default_rng(31)
        qqq = pd.Series(rng.normal(0.0004, 0.01, len(frame_.index)), index=frame_.index)
        tqqq = pd.Series(rng.normal(0.0009, 0.03, len(frame_.index)), index=frame_.index)
        bil = pd.Series(rng.normal(0.00005, 0.0002, len(frame_.index)), index=frame_.index)

        return run_nested_walk_forward(
            param_space_for_fold=param_space_for_fold,
            mechanism_family="EXPR_GP_POISON_TEST",
            signal_fn=lambda params: raw_by_id[params["expression_id"]],
            benchmark_returns=benchmark_returns,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id="expr-gp-poison-test",
            fold_count=3,
            embargo_bars=5,
        )

    clean_nested = _run_end_to_end(frame, clean_raw_signal_fn)
    poisoned_nested = _run_end_to_end(poisoned_frame, poisoned_raw_signal_fn)

    for clean_fold, poisoned_fold in zip(clean_nested.folds, poisoned_nested.folds, strict=True):
        # Calendar boundaries come from ``benchmark_returns`` alone, which is
        # shared, un-poisoned, and identical between the two runs -- so fold
        # boundaries match regardless of fold index.
        assert clean_fold.train_start == poisoned_fold.train_start
        assert clean_fold.train_end == poisoned_fold.train_end
        assert clean_fold.test_start == poisoned_fold.test_start
        assert clean_fold.test_end == poisoned_fold.test_end
        if clean_fold.fold <= target.fold:
            # Selection-related outputs must be byte-identical up to and
            # including the target fold: the target's own test window has
            # not been read by anything that produced these numbers.
            assert clean_fold.candidates_scored == poisoned_fold.candidates_scored
            assert clean_fold.selected_candidate_id == poisoned_fold.selected_candidate_id
            assert clean_fold.selected_param_vector == poisoned_fold.selected_param_vector
            assert clean_fold.selected_training_score == poisoned_fold.selected_training_score
        if clean_fold.fold < target.fold:
            assert clean_fold.test_returns == poisoned_fold.test_returns
        # A later fold (fold.fold > target.fold) is deliberately not checked
        # for equality: rolling_origin_folds is anchored, so that fold's own
        # training window legitimately (and correctly) includes the target
        # fold's now-historical test window -- its own evolved pool, winner,
        # and score are expected to differ, and asserting equality there
        # would conflate that with an actual leak.

    poisoned_target_fold = next(f for f in poisoned_nested.folds if f.fold == target.fold)
    clean_target_fold = next(f for f in clean_nested.folds if f.fold == target.fold)
    # Sanity check that the poisoning was not a no-op: the winner's own
    # test-window returns (which are read only *after* selection is
    # complete, using the full, un-windowed signal) must actually change.
    assert clean_target_fold.test_returns != poisoned_target_fold.test_returns
