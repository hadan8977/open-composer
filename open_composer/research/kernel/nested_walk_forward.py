"""Nested (anchored) walk-forward search: re-select parameters inside every fold.

Two prior designs each got half of this right.

``open_composer.research.router_common.walk_forward_router`` (the reference
implementation this project shipped with) re-selects the best parameter
vector *inside every fold*, using only data strictly before that fold's test
window. That is the right object to validate: nobody deploys "the one
parameter vector chosen once on 2016-2021 data", they deploy a *procedure*
that re-optimises periodically, and it is the procedure -- not any single
frozen parameter vector -- whose out-of-sample record must be judged. But
``walk_forward_router`` has no purge/embargo: its training window ends
exactly where the test window begins (``end_index=test_start``), so a
feature with a multi-day lookback can leak information from right across the
fold boundary.

The kernel search built in Work Items P1b/P2a
(``mechanism_eval.py``/``layered_search.py``) has the opposite defect. It
selects **one fixed parameter vector globally**: every candidate is ranked
once on a single development partition (2016-2021 in the P2a run) and the
winner is then scored on a single stitched out-of-sample stream
(2022-2026). The selection step never sees recent data, and -- because nobody
re-optimises a real strategy once and then runs it unchanged for five years
-- it validates an object nobody would actually deploy. Its one genuine
improvement over the old code is ``rolling_origin_folds``'s purge + embargo.

This module combines them instead of picking a side: for every fold produced
by :func:`open_composer.research.kernel.rolling_origin.rolling_origin_folds`
(purged, embargoed, anchored/expanding-origin), it re-runs the full Layer 1
(development-only quality) -> Layer 2 (QD archive) selection loop from
``layered_search.py`` using *only* that fold's training window, picks that
fold's winner, and evaluates the winner *only* on that fold's test window --
a window the selection step never touched. The stitched, chronological
concatenation of every fold's winner's test-window returns is "the
procedure"'s out-of-sample record, and that is what is handed off to
``kernel.mechanism_eval.evaluate_candidate`` for the DSR + promotion gate
battery.

Structural non-negotiable: a fold's test window must be unreadable during
that fold's own selection. This is enforced by construction, not by
convention -- :func:`_window_slice` returns a **new** ``pandas.Series``
containing only the rows inside ``[start, end]``; the rows outside that range
are not merely masked or ignored, they are absent from the object handed to
Layer 1/2 code. ``test_kernel_nested_walk_forward.py`` proves this
executably, one fold at a time: it poisons exactly one fold's own test-window
rows with a synthetic pattern unrelated to the organic data, leaving every
other row (including every training-window row, and every other fold's test
window) byte-identical, and asserts that every *selection* output for that
fold (the winner picked, its training score, how many candidates were
scored) is unchanged -- only that fold's own test-window returns (which are
supposed to reflect whatever is really there) and the final gate verdict are
allowed to differ. (Poisoning is done one fold at a time, not all folds at
once, because ``rolling_origin_folds``'s anchored/expanding design means a
*later* fold's training window legitimately -- and correctly -- includes an
*earlier* fold's test window once it is history; poisoning every fold
simultaneously would conflate that intended behaviour with an actual leak.)

Reused, not reimplemented, per the same discipline as ``layered_search.py``:

* the purge+embargo anchored fold split is ``rolling_origin.rolling_origin_folds``;
* Layer 1 quality scoring is ``layered_search.development_quality``
  (development-return-only annualized Sharpe) via
  ``layered_search.select_layer1_survivors``;
* Layer 2 diversity selection is ``layered_search.build_layer2_archive``,
  which itself reuses ``behavioral_descriptors`` and
  ``quality_diversity.build_quality_diversity_archive`` verbatim;
* the final gate battery is ``mechanism_eval.evaluate_candidate``.

This module owns none of those algorithms; it only owns the fold loop that
calls them with a training-only view, and the bookkeeping (parameter
stability, stitching) around it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.gate_contract import PreregisteredGates
from open_composer.research.kernel.layered_search import (
    DevelopmentView,
    build_layer2_archive,
    development_quality,
    select_layer1_survivors,
)
from open_composer.research.kernel.mechanism_eval import (
    DEFAULT_DSR_HAC_LAG,
    DEFAULT_DSR_TRIAL_COUNT,
    DEFAULT_MIN_DSR_STREAM_ROWS,
    Candidate,
    CandidateVerdict,
    SignalFn,
    evaluate_candidate,
)
from open_composer.research.kernel.rolling_origin import (
    DEFAULT_EMBARGO_BARS,
    DEFAULT_FOLD_COUNT,
    rolling_origin_folds,
)
from open_composer.research.quality_diversity import QualityDiversityElite


@dataclass(frozen=True)
class ParameterChurn(ResearchDataModel):
    """How often one parameter's selected value changed from fold to fold.

    ``change_count`` counts fold-to-fold transitions where the value differs
    from the previous fold's selection; ``total_transitions`` is
    ``fold_count - 1``. High churn on a parameter is a direct overfitting
    signal -- a procedure that picks a wildly different value every year is
    fitting noise, not a stable edge -- so it is reported here, never gated
    on or tuned to (per the task's explicit instruction).
    """

    parameter_name: str
    change_count: int
    total_transitions: int
    churn_rate: float
    values_by_fold: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ParameterStability(ResearchDataModel):
    """Aggregate parameter-stability report across every fold's selection."""

    fold_count: int
    distinct_selected_vector_count: int
    selected_vectors_by_fold: list[dict[str, Any]]
    per_parameter_churn: list[ParameterChurn]


@dataclass(frozen=True)
class NestedFoldResult(ResearchDataModel):
    """One fold's selection (training-only) and evaluation (test-only) outcome."""

    fold: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    candidates_scored: int
    selected_candidate_id: str
    selected_param_vector: dict[str, Any]
    selected_training_score: float
    test_returns: list[float]
    test_dates: list[str]


@dataclass(frozen=True)
class NestedWalkForwardResult(ResearchDataModel):
    """The full nested walk-forward outcome: every fold, stability, and the
    stitched procedure-level verdict."""

    mechanism_family: str
    fold_count: int
    embargo_bars: int
    folds: list[NestedFoldResult]
    parameter_stability: ParameterStability
    procedure_candidate: Candidate
    procedure_verdict: CandidateVerdict


def _require_return_series(series: pd.Series, *, label: str) -> None:
    if not isinstance(series, pd.Series):
        raise TypeError(f"{label} must be a pandas Series")
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(f"{label} must be indexed by a DatetimeIndex")
    if series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError(f"{label} index must be sorted and duplicate-free")


def _window_slice(series: pd.Series, *, start: str, end: str) -> pd.Series:
    """Return a **new** Series containing only the rows inside ``[start, end]``.

    This is the structural enforcement point: rows outside the window are not
    present in the object this returns, so nothing downstream can read them
    even by accident. ``.loc`` label-slicing on a sorted ``DatetimeIndex`` is
    inclusive of both endpoints when they are present and simply omits rows
    that fall outside the range otherwise.
    """
    return series.loc[pd.Timestamp(start) : pd.Timestamp(end)]


def _aligned_benchmark(
    benchmark_returns: pd.Series, index: pd.DatetimeIndex, *, label: str
) -> list[float]:
    aligned = benchmark_returns.reindex(index)
    if aligned.isna().any():
        raise ValueError(f"{label}: benchmark return series is missing rows for this window")
    return aligned.tolist()


def _select_winner(elites: Sequence[QualityDiversityElite]) -> QualityDiversityElite:
    """Pick the single best-quality elite out of the Layer 2 archive.

    Tie-break matches ``quality_diversity._candidate_precedes``'s own
    "maximize" convention: highest quality first, then lowest candidate_id --
    so this is deterministic even when two elites tie exactly.
    """
    if not elites:
        raise ValueError("cannot select a winner from an empty Layer 2 archive")
    return sorted(
        elites, key=lambda elite: (-elite.candidate.quality, elite.candidate.candidate_id)
    )[0]


def _canonical_vector(vector: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted(vector.items()))


def _parameter_stability(selected_vectors: Sequence[dict[str, Any]]) -> ParameterStability:
    fold_count = len(selected_vectors)
    distinct_count = len({_canonical_vector(vector) for vector in selected_vectors})
    parameter_names = sorted({name for vector in selected_vectors for name in vector})
    total_transitions = max(fold_count - 1, 0)
    churn: list[ParameterChurn] = []
    for name in parameter_names:
        values = [vector.get(name) for vector in selected_vectors]
        # Deliberately *not* strict=True: this zips a sequence against its own
        # tail offset by one to iterate consecutive pairs, so the two inputs
        # are one element different in length by construction.
        change_count = sum(
            1 for prev, curr in zip(values, values[1:], strict=False) if prev != curr
        )
        churn_rate = (change_count / total_transitions) if total_transitions else 0.0
        churn.append(
            ParameterChurn(
                parameter_name=name,
                change_count=change_count,
                total_transitions=total_transitions,
                churn_rate=churn_rate,
                values_by_fold=values,
            )
        )
    return ParameterStability(
        fold_count=fold_count,
        distinct_selected_vector_count=distinct_count,
        selected_vectors_by_fold=[dict(vector) for vector in selected_vectors],
        per_parameter_churn=churn,
    )


def run_nested_walk_forward(
    param_space: Sequence[Mapping[str, Any]],
    *,
    mechanism_family: str,
    signal_fn: SignalFn,
    benchmark_returns: pd.Series,
    qqq_returns: pd.Series,
    tqqq_returns: pd.Series,
    bil_returns: pd.Series,
    campaign_id: str,
    stress_signal_fn: SignalFn | None = None,
    fold_count: int = DEFAULT_FOLD_COUNT,
    embargo_bars: int = DEFAULT_EMBARGO_BARS,
    quality_fn: Callable[[DevelopmentView], float] = development_quality,
    annualization_sessions: int = 252,
    gates: Mapping[str, float] | PreregisteredGates | None = None,
    dsr_trial_count: int = DEFAULT_DSR_TRIAL_COUNT,
    dsr_hac_lag: int = DEFAULT_DSR_HAC_LAG,
    min_dsr_stream_rows: int = DEFAULT_MIN_DSR_STREAM_ROWS,
) -> NestedWalkForwardResult:
    """Run the nested (anchored) walk-forward procedure over ``param_space``.

    For every ``rolling_origin_folds`` fold: score every point in
    ``param_space`` (via ``signal_fn``) using only that fold's training
    window, run the Layer 1 -> Layer 2 selection loop on that training-only
    view, pick the winner, then evaluate the winner's own signal on that
    fold's test window -- a window the selection step never read. The
    stitched, chronological concatenation of every fold's winner's
    test-window returns is scored once, as a single :class:`Candidate`
    ("the procedure"), against the full paper-tier gate battery.

    ``benchmark_returns`` supplies both the calendar ``rolling_origin_folds``
    splits into folds (it should be the longest, most complete return series
    available, e.g. the underlying benchmark/market series) and the paired
    series ``behavioral_descriptors`` needs for each candidate's Layer 2 cell.
    Every candidate in ``param_space`` is folded against these *same* fold
    boundaries, which is what makes "the fold's winner" comparable across the
    whole grid even though different parameter vectors (e.g. different
    lookbacks) can have different warm-up lengths and therefore different
    native start dates.

    Raises ``ValueError`` if any fold has zero Layer 1 survivors (every
    candidate degenerate on that fold's training window) or if the winner's
    signal has no observations in the fold's test window.
    """
    if not param_space:
        raise ValueError("param_space must declare at least one point")
    if not mechanism_family.strip():
        raise ValueError("mechanism_family must be a non-empty string")
    _require_return_series(benchmark_returns, label="benchmark_returns")

    candidate_ids = [f"{mechanism_family}-{index:03d}" for index in range(len(param_space))]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("param_space produced duplicate candidate ids")
    params_by_id = dict(zip(candidate_ids, param_space, strict=True))

    # Computed once: signal_fn is a pure function of the parameter vector, not
    # of the fold, so the full-history raw series is reused (sliced per fold)
    # rather than recomputed fold by fold.
    raw_returns_by_id: dict[str, pd.Series] = {}
    for candidate_id, params in params_by_id.items():
        raw = signal_fn(params)
        _require_return_series(raw, label=f"{candidate_id} signal")
        raw_returns_by_id[candidate_id] = raw

    folds, _stitched_calendar = rolling_origin_folds(
        benchmark_returns, fold_count=fold_count, embargo_bars=embargo_bars
    )

    fold_results: list[NestedFoldResult] = []
    stress_fn = stress_signal_fn or signal_fn

    for fold in folds:
        train_start, train_end = fold.train.train_start, fold.train.train_end
        test_start, test_end = fold.train.test_start, fold.train.test_end

        views: list[DevelopmentView] = []
        for candidate_id, params in params_by_id.items():
            train_window = _window_slice(
                raw_returns_by_id[candidate_id], start=train_start, end=train_end
            )
            if train_window.empty:
                continue
            benchmark_window = _aligned_benchmark(
                benchmark_returns, train_window.index, label=f"fold {fold.fold} / {candidate_id}"
            )
            views.append(
                DevelopmentView(
                    candidate_id=candidate_id,
                    mechanism_family=mechanism_family,
                    param_vector=dict(params),
                    generation=0,
                    parent_id=None,
                    development_returns=train_window.tolist(),
                    development_benchmark_returns=benchmark_window,
                )
            )
        if not views:
            raise ValueError(
                f"fold {fold.fold}: no candidate has any observation in the training "
                f"window [{train_start}, {train_end}]"
            )

        qualities, survivors = select_layer1_survivors(views, quality_fn=quality_fn)
        if not survivors:
            raise ValueError(
                f"fold {fold.fold}: every candidate was degenerate on the training "
                f"window [{train_start}, {train_end}] (zero Layer 1 survivors)"
            )

        archive = build_layer2_archive(
            survivors, qualities, campaign_id=f"{campaign_id}-fold-{fold.fold:02d}"
        )
        winner = _select_winner(archive.elites)
        winner_id = winner.candidate.candidate_id
        winner_params = params_by_id[winner_id]

        # First read of this fold's test window, for this fold's winner only --
        # nothing above this line has touched any row in [test_start, test_end].
        test_window = _window_slice(raw_returns_by_id[winner_id], start=test_start, end=test_end)
        if test_window.empty:
            raise ValueError(
                f"fold {fold.fold}: winner {winner_id} has no observation in the test "
                f"window [{test_start}, {test_end}]"
            )

        fold_results.append(
            NestedFoldResult(
                fold=fold.fold,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                candidates_scored=len(param_space),
                selected_candidate_id=winner_id,
                selected_param_vector=dict(winner_params),
                selected_training_score=float(qualities[winner_id]),
                test_returns=[float(value) for value in test_window.tolist()],
                test_dates=[timestamp.isoformat() for timestamp in test_window.index],
            )
        )

    stability = _parameter_stability([result.selected_param_vector for result in fold_results])

    # Stitch: fold_results is already in rolling_origin_folds's chronological
    # order, and its test windows are disjoint by construction, so simple
    # concatenation in fold order is the chronological stitched OOS stream.
    stitched_returns: list[float] = []
    stitched_dates: list[str] = []
    stitched_stress: list[float] = []
    oos_fold_returns: list[list[float]] = []
    for result in fold_results:
        stitched_returns.extend(result.test_returns)
        stitched_dates.extend(result.test_dates)
        oos_fold_returns.append(list(result.test_returns))

        winner_params = result.selected_param_vector
        stress_raw = stress_fn(winner_params)
        _require_return_series(stress_raw, label=f"fold {result.fold} stress signal")
        stress_window = _window_slice(stress_raw, start=result.test_start, end=result.test_end)
        stress_aligned = stress_window.reindex(pd.DatetimeIndex(result.test_dates))
        if stress_aligned.isna().any():
            raise ValueError(
                f"fold {result.fold}: stress signal is missing rows the primary signal has"
            )
        stitched_stress.extend(float(value) for value in stress_aligned.tolist())

    procedure_candidate = Candidate(
        candidate_id=f"{campaign_id}-nested-procedure",
        mechanism_family=mechanism_family,
        param_vector={
            "nested_walk_forward_per_fold": {
                str(result.fold): dict(result.selected_param_vector) for result in fold_results
            }
        },
        oos_return_stream=stitched_returns,
        oos_dates=stitched_dates,
        oos_fold_returns=oos_fold_returns,
        stress_return_stream=stitched_stress,
    )
    procedure_verdict = evaluate_candidate(
        procedure_candidate,
        qqq_returns=qqq_returns,
        tqqq_returns=tqqq_returns,
        bil_returns=bil_returns,
        annualization_sessions=annualization_sessions,
        gates=gates,
        dsr_trial_count=dsr_trial_count,
        dsr_hac_lag=dsr_hac_lag,
        min_dsr_stream_rows=min_dsr_stream_rows,
    )

    return NestedWalkForwardResult(
        mechanism_family=mechanism_family,
        fold_count=len(fold_results),
        embargo_bars=embargo_bars,
        folds=fold_results,
        parameter_stability=stability,
        procedure_candidate=procedure_candidate,
        procedure_verdict=procedure_verdict,
    )
