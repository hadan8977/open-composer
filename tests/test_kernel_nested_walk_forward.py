"""Nested (anchored) walk-forward search: per-fold re-selection (see module
docstring in ``open_composer/research/kernel/nested_walk_forward.py``).

The central correctness rule under test: a fold's test window must be
unreadable during that fold's own selection. ``rolling_origin_folds``'s
anchored/expanding design means a *later* fold's training window legitimately
includes an *earlier* fold's test window (by the time fold 2 trains, fold 1's
test year really is history) -- so the only clean way to prove "fold k cannot
read fold k's own test window" is to poison exactly one fold's test window in
isolation and confirm that exact fold's own selection is unchanged. Poisoning
every fold simultaneously would conflate that with the (correct, expected)
behaviour of later folds legitimately training on earlier folds' now-historical
test data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.mechanism_eval import CandidateVerdict
from open_composer.research.kernel.nested_walk_forward import (
    NestedWalkForwardResult,
    ParameterChurn,
    _parameter_stability,
    _select_winner,
    _window_slice,
    run_nested_walk_forward,
)
from open_composer.research.kernel.rolling_origin import rolling_origin_folds
from open_composer.research.quality_diversity import (
    QualityDiversityCandidate,
    QualityDiversityElite,
)

# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

FOLD_COUNT = 3
EMBARGO_BARS = 5
PARAM_SPACE = [{"variant": index} for index in range(4)]


def _benchmark_series(*, start: str = "2019-01-02", end: str = "2024-12-31") -> pd.Series:
    index = pd.bdate_range(start, end, tz="UTC")
    values = np.random.default_rng(0).normal(0.0003, 0.008, len(index))
    return pd.Series(values, index=index, name="benchmark")


def _variant_series(index: pd.DatetimeIndex) -> dict[int, pd.Series]:
    """Four deterministic, differently-behaved variants sharing one calendar."""
    specs = [
        (0.0012, 0.010, 10),  # best risk-adjusted
        (0.0003, 0.020, 11),
        (-0.0004, 0.015, 12),
        (0.0000, 0.030, 13),
    ]
    series: dict[int, pd.Series] = {}
    for variant_id, (mean, std, seed) in enumerate(specs):
        values = np.random.default_rng(seed).normal(mean, std, len(index))
        series[variant_id] = pd.Series(values, index=index, name=f"variant-{variant_id}")
    return series


def _make_signal_fn(series_by_variant: dict[int, pd.Series]):
    def signal_fn(params: dict[str, object]) -> pd.Series:
        return series_by_variant[params["variant"]]

    return signal_fn


def _poison_window(series: pd.Series, *, start: str, end: str) -> pd.Series:
    """Replace every row in ``[start, end]`` with a clearly synthetic alternating
    pattern (bounded, so compounding stays finite) unrelated to the organic
    noise in ``series``."""
    poisoned = series.copy()
    mask = (poisoned.index >= pd.Timestamp(start)) & (poisoned.index <= pd.Timestamp(end))
    count = int(mask.sum())
    pattern = np.array([0.2 if i % 2 == 0 else -0.2 for i in range(count)])
    poisoned.loc[mask] = pattern
    return poisoned


def _benchmark_family(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, pd.Series]:
    rng = np.random.default_rng(999)
    qqq = pd.Series(rng.normal(0.0004, 0.01, len(index)), index=index)
    tqqq = pd.Series(rng.normal(0.0009, 0.03, len(index)), index=index)
    bil = pd.Series(rng.normal(0.00005, 0.0002, len(index)), index=index)
    return qqq, tqqq, bil


def _run(series_by_variant: dict[int, pd.Series], benchmark: pd.Series, *, campaign_id: str):
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    return run_nested_walk_forward(
        PARAM_SPACE,
        mechanism_family="TEST_MECH",
        signal_fn=_make_signal_fn(series_by_variant),
        benchmark_returns=benchmark,
        qqq_returns=qqq,
        tqqq_returns=tqqq,
        bil_returns=bil,
        campaign_id=campaign_id,
        fold_count=FOLD_COUNT,
        embargo_bars=EMBARGO_BARS,
    )


# ---------------------------------------------------------------------------
# _window_slice: structural window enforcement
# ---------------------------------------------------------------------------


def test_window_slice_excludes_rows_outside_the_range() -> None:
    index = pd.bdate_range("2020-01-01", "2020-03-31", tz="UTC")
    series = pd.Series(np.arange(len(index), dtype=float), index=index)
    start = pd.Timestamp("2020-02-01", tz="UTC").isoformat()
    end = pd.Timestamp("2020-02-29", tz="UTC").isoformat()
    windowed = _window_slice(series, start=start, end=end)
    assert windowed.index.min() >= pd.Timestamp("2020-02-01", tz="UTC")
    assert windowed.index.max() <= pd.Timestamp("2020-02-29", tz="UTC")
    assert len(windowed) < len(series)


# ---------------------------------------------------------------------------
# _select_winner: deterministic tie-break
# ---------------------------------------------------------------------------


def _fake_elite(candidate_id: str, quality: float) -> QualityDiversityElite:
    candidate = QualityDiversityCandidate(
        candidate_id=candidate_id,
        hypothesis_id="fam",
        branch="fam",
        archive_descriptors={},
        quality=quality,
        quality_metric="development_sharpe",
        visibility_partition="development",
        metrics_snapshot_path="x",
        metrics_snapshot_sha256="0" * 64,
        partition_contract_path="x",
        partition_contract_sha256="0" * 64,
        promotion_eligible=True,
        resource_rung=0,
    )
    return QualityDiversityElite(cell_id="cell", cell_descriptors={}, candidate=candidate)


def test_select_winner_picks_highest_quality() -> None:
    elites = [_fake_elite("a", 0.5), _fake_elite("b", 1.5), _fake_elite("c", 1.0)]
    assert _select_winner(elites).candidate.candidate_id == "b"


def test_select_winner_breaks_quality_ties_by_lowest_candidate_id() -> None:
    elites = [_fake_elite("zzz", 1.0), _fake_elite("aaa", 1.0)]
    assert _select_winner(elites).candidate.candidate_id == "aaa"


def test_select_winner_rejects_empty_archive() -> None:
    with pytest.raises(ValueError, match="empty"):
        _select_winner([])


# ---------------------------------------------------------------------------
# _parameter_stability: churn accounting
# ---------------------------------------------------------------------------


def test_parameter_stability_counts_distinct_vectors_and_churn() -> None:
    vectors = [
        {"a": 1, "b": 2},
        {"a": 1, "b": 2},
        {"a": 2, "b": 2},
        {"a": 2, "b": 3},
    ]
    report = _parameter_stability(vectors)
    assert report.fold_count == 4
    assert report.distinct_selected_vector_count == 3
    churn_by_name = {churn.parameter_name: churn for churn in report.per_parameter_churn}
    assert churn_by_name["a"].change_count == 1
    assert churn_by_name["a"].total_transitions == 3
    assert churn_by_name["a"].churn_rate == pytest.approx(1 / 3)
    assert churn_by_name["b"].change_count == 1
    assert churn_by_name["b"].churn_rate == pytest.approx(1 / 3)


def test_parameter_stability_zero_churn_when_selection_never_changes() -> None:
    vectors = [{"a": 5}, {"a": 5}, {"a": 5}]
    report = _parameter_stability(vectors)
    assert report.distinct_selected_vector_count == 1
    (churn,) = report.per_parameter_churn
    assert isinstance(churn, ParameterChurn)
    assert churn.change_count == 0
    assert churn.churn_rate == 0.0


def test_parameter_stability_single_fold_has_no_transitions() -> None:
    report = _parameter_stability([{"a": 1}])
    assert report.fold_count == 1
    (churn,) = report.per_parameter_churn
    assert churn.total_transitions == 0
    assert churn.churn_rate == 0.0


# ---------------------------------------------------------------------------
# End-to-end: run_nested_walk_forward
# ---------------------------------------------------------------------------


def test_run_nested_walk_forward_end_to_end() -> None:
    benchmark = _benchmark_series()
    variants = _variant_series(benchmark.index)
    result = _run(variants, benchmark, campaign_id="e2e")

    assert isinstance(result, NestedWalkForwardResult)
    assert result.fold_count == FOLD_COUNT
    assert len(result.folds) == FOLD_COUNT

    for fold in result.folds:
        assert pd.Timestamp(fold.train_end) < pd.Timestamp(fold.test_start)
        assert fold.candidates_scored == len(PARAM_SPACE)
        assert fold.selected_param_vector["variant"] in {v["variant"] for v in PARAM_SPACE}
        assert len(fold.test_returns) == len(fold.test_dates)
        assert len(fold.test_returns) > 0

    # Folds are chronological and their test windows are disjoint, so the
    # stitched stream must be monotonically increasing with no repeats.
    stitched_dates = pd.DatetimeIndex(result.procedure_candidate.oos_dates)
    assert stitched_dates.is_monotonic_increasing
    assert not stitched_dates.has_duplicates

    total_test_rows = sum(len(fold.test_returns) for fold in result.folds)
    assert len(result.procedure_candidate.oos_return_stream) == total_test_rows
    assert len(result.procedure_candidate.stress_return_stream) == total_test_rows
    assert len(result.procedure_candidate.oos_fold_returns) == FOLD_COUNT

    assert result.parameter_stability.fold_count == FOLD_COUNT
    assert result.parameter_stability.selected_vectors_by_fold == [
        fold.selected_param_vector for fold in result.folds
    ]

    assert isinstance(result.procedure_verdict, CandidateVerdict)
    assert set(result.procedure_verdict.gate_results) == {
        "cagr_excess_qqq",
        "sharpe_excess_bil",
        "dsr_probability",
        "max_drawdown",
        "mar",
        "positive_fold_fraction",
        "qqq_capture_ratio",
        "qqq_downside_capture",
    }


def test_run_nested_walk_forward_is_deterministic() -> None:
    benchmark = _benchmark_series()
    variants = _variant_series(benchmark.index)
    first = _run(variants, benchmark, campaign_id="determinism")
    second = _run(variants, benchmark, campaign_id="determinism")
    assert first.model_dump() == second.model_dump()


def test_run_nested_walk_forward_rejects_empty_param_space() -> None:
    benchmark = _benchmark_series()
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    with pytest.raises(ValueError, match="param_space"):
        run_nested_walk_forward(
            [],
            mechanism_family="TEST",
            signal_fn=lambda params: benchmark,
            benchmark_returns=benchmark,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id="empty",
        )


def test_run_nested_walk_forward_raises_when_every_candidate_is_degenerate() -> None:
    benchmark = _benchmark_series()
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    zero_series = pd.Series(0.0, index=benchmark.index)
    with pytest.raises(ValueError, match="Layer 1 survivors"):
        run_nested_walk_forward(
            PARAM_SPACE,
            mechanism_family="DEGENERATE",
            signal_fn=lambda params: zero_series,
            benchmark_returns=benchmark,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id="degenerate",
            fold_count=FOLD_COUNT,
            embargo_bars=EMBARGO_BARS,
        )


# ---------------------------------------------------------------------------
# param_space_for_fold: per-fold candidate pools (review item 3.3).
#
# The backward-compatible extension this module's docstring describes:
# exactly one of param_space / param_space_for_fold must be given, and when
# the pool itself is a function of the fold (e.g. a from-scratch GP
# evolution per fold -- see expression_tree_search.run_nested_expression_gp_search
# and its own tests), the callable shape is what lets the caller express
# that without forking this driver.
# ---------------------------------------------------------------------------


def test_run_nested_walk_forward_rejects_both_param_space_and_callback() -> None:
    benchmark = _benchmark_series()
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    with pytest.raises(ValueError, match="exactly one"):
        run_nested_walk_forward(
            PARAM_SPACE,
            mechanism_family="TEST",
            signal_fn=lambda params: benchmark,
            benchmark_returns=benchmark,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id="both",
            param_space_for_fold=lambda fold: PARAM_SPACE,
        )


def test_run_nested_walk_forward_rejects_neither_param_space_nor_callback() -> None:
    benchmark = _benchmark_series()
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    with pytest.raises(ValueError, match="exactly one"):
        run_nested_walk_forward(
            mechanism_family="TEST",
            signal_fn=lambda params: benchmark,
            benchmark_returns=benchmark,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id="neither",
        )


def test_run_nested_walk_forward_rejects_an_empty_per_fold_pool() -> None:
    benchmark = _benchmark_series()
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    with pytest.raises(ValueError, match="empty pool"):
        run_nested_walk_forward(
            mechanism_family="TEST",
            signal_fn=lambda params: benchmark,
            benchmark_returns=benchmark,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id="empty-per-fold",
            fold_count=FOLD_COUNT,
            embargo_bars=EMBARGO_BARS,
            param_space_for_fold=lambda fold: [],
        )


def test_run_nested_walk_forward_allows_the_same_per_fold_pool_every_fold() -> None:
    """The per-fold callback is allowed to return an identical pool every
    fold (candidate ids are namespaced by fold number internally, so this
    cannot collide) -- the degenerate case of ``param_space_for_fold``,
    included for completeness alongside the "different pool every fold"
    case below.
    """
    benchmark = _benchmark_series()
    variants = _variant_series(benchmark.index)
    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    result = run_nested_walk_forward(
        mechanism_family="TEST_SAME_POOL",
        signal_fn=_make_signal_fn(variants),
        benchmark_returns=benchmark,
        qqq_returns=qqq,
        tqqq_returns=tqqq,
        bil_returns=bil,
        campaign_id="same-pool-every-fold",
        fold_count=FOLD_COUNT,
        embargo_bars=EMBARGO_BARS,
        param_space_for_fold=lambda fold: PARAM_SPACE,
    )
    assert result.fold_count == FOLD_COUNT
    for fold_result in result.folds:
        assert fold_result.candidates_scored == len(PARAM_SPACE)


def test_run_nested_walk_forward_with_per_fold_param_space_uses_a_different_pool_each_fold() -> (
    None
):
    """The core capability review item 3.3 asks for: the candidate *pool*,
    not just which candidate wins, can be a function of the fold -- the
    shape a per-fold GP elite archive has in practice.
    """
    benchmark = _benchmark_series()
    variants = _variant_series(benchmark.index)
    folds, _stitched = rolling_origin_folds(
        benchmark, fold_count=FOLD_COUNT, embargo_bars=EMBARGO_BARS
    )

    def fold_pool(fold) -> list[dict[str, object]]:
        base = (fold.fold - 1) % len(variants)
        other = (base + 1) % len(variants)
        return [{"variant": base}, {"variant": other}]

    qqq, tqqq, bil = _benchmark_family(benchmark.index)
    result = run_nested_walk_forward(
        mechanism_family="TEST_PER_FOLD",
        signal_fn=_make_signal_fn(variants),
        benchmark_returns=benchmark,
        qqq_returns=qqq,
        tqqq_returns=tqqq,
        bil_returns=bil,
        campaign_id="per-fold-pool",
        fold_count=FOLD_COUNT,
        embargo_bars=EMBARGO_BARS,
        param_space_for_fold=fold_pool,
    )

    assert result.fold_count == FOLD_COUNT
    for fold_result, fold in zip(result.folds, folds, strict=True):
        assert fold_result.candidates_scored == 2
        base = (fold.fold - 1) % len(variants)
        other = (base + 1) % len(variants)
        assert fold_result.selected_param_vector["variant"] in {base, other}


def test_run_nested_walk_forward_with_per_fold_param_space_is_deterministic() -> None:
    benchmark = _benchmark_series()
    variants = _variant_series(benchmark.index)
    qqq, tqqq, bil = _benchmark_family(benchmark.index)

    def fold_pool(fold) -> list[dict[str, object]]:
        base = (fold.fold - 1) % len(variants)
        return [{"variant": base}, {"variant": (base + 1) % len(variants)}]

    def _run_per_fold(campaign_id: str) -> NestedWalkForwardResult:
        return run_nested_walk_forward(
            mechanism_family="TEST_PER_FOLD_DET",
            signal_fn=_make_signal_fn(variants),
            benchmark_returns=benchmark,
            qqq_returns=qqq,
            tqqq_returns=tqqq,
            bil_returns=bil,
            campaign_id=campaign_id,
            fold_count=FOLD_COUNT,
            embargo_bars=EMBARGO_BARS,
            param_space_for_fold=fold_pool,
        )

    first = _run_per_fold("det-per-fold")
    second = _run_per_fold("det-per-fold")
    assert first.model_dump() == second.model_dump()


# ---------------------------------------------------------------------------
# The correctness rule: a fold's own test window is unreadable during its
# own selection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fold_index", [0, 1, 2])
def test_poisoning_a_folds_own_test_window_does_not_change_that_folds_selection(
    fold_index: int,
) -> None:
    benchmark = _benchmark_series()
    variants = _variant_series(benchmark.index)

    folds, _stitched = rolling_origin_folds(
        benchmark, fold_count=FOLD_COUNT, embargo_bars=EMBARGO_BARS
    )
    target = folds[fold_index]

    poisoned_variants = {
        variant_id: _poison_window(series, start=target.train.test_start, end=target.train.test_end)
        for variant_id, series in variants.items()
    }

    clean = _run(variants, benchmark, campaign_id=f"poison-{fold_index}")
    poisoned = _run(poisoned_variants, benchmark, campaign_id=f"poison-{fold_index}")

    # Every fold strictly before the poisoned one is untouched by
    # construction: its training window only ever looks backward, and the
    # poisoned dates are the most recent dates seen so far at that point.
    for earlier in range(fold_index):
        assert (
            clean.folds[earlier].selected_param_vector
            == poisoned.folds[earlier].selected_param_vector
        )
        assert clean.folds[earlier].test_returns == poisoned.folds[earlier].test_returns

    clean_fold = clean.folds[fold_index]
    poisoned_fold = poisoned.folds[fold_index]

    # The selection outputs -- everything decided using only the training
    # window -- must be byte-identical, because the training window itself
    # was never touched by this poisoning.
    assert clean_fold.train_start == poisoned_fold.train_start
    assert clean_fold.train_end == poisoned_fold.train_end
    assert clean_fold.test_start == poisoned_fold.test_start
    assert clean_fold.test_end == poisoned_fold.test_end
    assert clean_fold.candidates_scored == poisoned_fold.candidates_scored
    assert clean_fold.selected_candidate_id == poisoned_fold.selected_candidate_id
    assert clean_fold.selected_param_vector == poisoned_fold.selected_param_vector
    assert clean_fold.selected_training_score == poisoned_fold.selected_training_score
    assert (
        clean.parameter_stability.selected_vectors_by_fold[: fold_index + 1]
        == poisoned.parameter_stability.selected_vectors_by_fold[: fold_index + 1]
    )

    # Sanity check that the poisoning was not a no-op: the winner's own
    # test-window returns (which are supposed to reflect whatever is really
    # in the test window) must actually have changed.
    assert clean_fold.test_returns != poisoned_fold.test_returns
