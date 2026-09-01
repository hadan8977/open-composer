"""Reusable mechanism -> candidate -> gate evaluation harness.

Extracted from ``scripts/evaluate_vol02_recalibrated.py`` (Work Item P1b, see
``docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md`` section 5). That
342-line script proved a fast path from real data to a credible promotion
verdict; roughly 170 of those lines were mechanism-agnostic plumbing (load
real data, split into rolling-origin folds, recompute the gate metrics,
render a verdict). This module is that plumbing, so a new mechanism only has
to supply a signal function and a parameter space.

Core vocabulary:

    Mechanism  = a signal-function template that declares its own parameter
                 space.
    Candidate  = that template bound to one concrete parameter vector.

A hand-written strategy is a :class:`Mechanism` whose ``param_space`` has
exactly one point. A grid or genetic search is a :class:`Mechanism` whose
``param_space`` has many points. A tree-structured exploration is several
mechanisms evaluated side by side through :func:`evaluate_family`. Every
candidate -- whether it came from a param space of one or of a thousand --
is expanded by :func:`expand_mechanism` and scored by :func:`evaluate_candidate`,
so a hand-written candidate can never receive looser statistical treatment
than a searched one: both emit a return stream, both are folded by
``rolling_origin_folds``, both are scored by the same
``recompute_candidate_promotion_metrics`` + DSR gates, both are clustered by
the same ``effective_independent_trials``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from open_composer.research.campaign import (
    QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD,
    recompute_candidate_promotion_metrics,
)
from open_composer.research.campaign_statistics import (
    annualized_sharpe,
    deflated_sharpe_probability,
)
from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.effective_trials import (
    DEFAULT_CORRELATION_THRESHOLD,
    EffectiveTrialsReport,
    effective_independent_trials,
)
from open_composer.research.kernel.rolling_origin import (
    DEFAULT_EMBARGO_BARS,
    DEFAULT_FOLD_COUNT,
    rolling_origin_folds,
)

#: A signal function turns one concrete parameter vector into a chronologically
#: sorted, gap-free daily return series (see ``rolling_origin.returns_from_ohlcv``
#: for the OHLCV -> returns step). It must apply its own PIT safety buffer --
#: the harness does not lag anything on the mechanism's behalf.
SignalFn = Callable[[Mapping[str, Any]], pd.Series]

#: Paper-tier promotion gates (see plan section 4). Mechanism-agnostic: every
#: candidate from every mechanism is judged against the same thresholds.
DEFAULT_PROMOTION_GATES: dict[str, float] = {
    "cagr_excess_qqq_minimum": 0.05,
    "sharpe_excess_bil_minimum": 1.00,
    "dsr_minimum": 0.50,
    "max_drawdown_minimum": -0.65,
    "mar_minimum": 0.60,
    "minimum_positive_fold_fraction": 3 / 5,
    "qqq_capture_ratio_minimum": 1.0,
    "qqq_downside_capture_maximum": 1.0,
}
DEFAULT_DSR_TRIAL_COUNT = 32
DEFAULT_DSR_HAC_LAG = 21
DEFAULT_MIN_DSR_STREAM_ROWS = 1000


@dataclass(frozen=True)
class Mechanism:
    """A signal-function template plus the parameter space it can be run at."""

    family: str
    signal_fn: SignalFn
    param_space: Sequence[Mapping[str, Any]]
    #: Optional second signal function evaluated at the same parameter vector
    #: to produce the elevated-cost stream ``recompute_candidate_promotion_
    #: metrics`` needs for its stress-total-return gate. Defaults to reusing
    #: ``signal_fn`` (i.e. the mechanism is treated as cost-insensitive) when a
    #: mechanism does not model transaction-cost stress explicitly.
    stress_signal_fn: SignalFn | None = None

    def __post_init__(self) -> None:
        if not self.family.strip():
            raise ValueError("mechanism family must be a non-empty string")
        if not self.param_space:
            raise ValueError(
                f"mechanism {self.family!r} param_space must declare at least one point "
                "(a hand-written mechanism is the one-point degenerate case)"
            )


@dataclass(frozen=True)
class Candidate(ResearchDataModel):
    """One mechanism bound to one concrete parameter vector."""

    candidate_id: str
    mechanism_family: str
    param_vector: dict[str, Any]
    #: The stitched, rolling-origin out-of-sample return stream -- the input
    #: to effective-trials clustering and to DSR/PBO/SPA.
    oos_return_stream: list[float]
    generation: int = 0
    parent_id: str | None = None
    oos_dates: list[str] = field(default_factory=list)
    development_fold_returns: list[list[float]] = field(default_factory=list)
    stress_return_stream: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateVerdict(ResearchDataModel):
    """A candidate's promotion metrics and paper-tier gate results."""

    candidate: Candidate
    metrics: dict[str, float | int]
    sharpe_excess_bil: float
    dsr_probability: float
    positive_fold_fraction: float
    orthogonal_to_qqq: bool
    gate_results: dict[str, bool]
    all_gates_pass: bool


@dataclass(frozen=True)
class FamilyVerdict(ResearchDataModel):
    """Every candidate in a family, plus its honest effective-N accounting."""

    candidates: list[CandidateVerdict]
    effective_trials: EffectiveTrialsReport
    raw_candidate_count: int
    effective_n: int
    breadth_ratio: float


def _require_finite_return_series(series: pd.Series, *, label: str) -> None:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError(f"{label} return series must be indexed by a DatetimeIndex")
    if series.isna().any() or not series.map(math.isfinite).all():
        raise ValueError(f"{label} return series contains non-finite values")


def expand_mechanism(
    mechanism: Mechanism,
    *,
    fold_count: int = DEFAULT_FOLD_COUNT,
    embargo_bars: int = DEFAULT_EMBARGO_BARS,
    generation: int = 0,
    parent_id: str | None = None,
) -> list[Candidate]:
    """Bind ``mechanism`` to every point in its parameter space.

    Each resulting :class:`Candidate` carries a rolling-origin stitched
    out-of-sample stream (purge + embargo via ``rolling_origin_folds``) and,
    when the mechanism supplies one, a cost-stressed stream reindexed onto
    that same stitched window. This is the one and only code path from
    "parameter vector" to "candidate" -- a one-point param space and an
    N-point param space run through it identically.
    """
    candidates: list[Candidate] = []
    for index, params in enumerate(mechanism.param_space):
        raw_returns = mechanism.signal_fn(params)
        _require_finite_return_series(raw_returns, label=f"{mechanism.family}[{index}]")
        folds, stitched = rolling_origin_folds(
            raw_returns, fold_count=fold_count, embargo_bars=embargo_bars
        )
        fold_returns = [
            stitched.loc[
                pd.Timestamp(fold.train.test_start) : pd.Timestamp(fold.train.test_end)
            ].tolist()
            for fold in folds
        ]

        stress_fn = mechanism.stress_signal_fn or mechanism.signal_fn
        stress_raw = stress_fn(params)
        _require_finite_return_series(stress_raw, label=f"{mechanism.family}[{index}] stress")
        stress_stream = stress_raw.reindex(stitched.index)
        if stress_stream.isna().any():
            raise ValueError(
                f"{mechanism.family}[{index}] stress stream is missing rows the primary stream has"
            )

        candidates.append(
            Candidate(
                candidate_id=f"{mechanism.family}-{index:03d}",
                mechanism_family=mechanism.family,
                param_vector=dict(params),
                oos_return_stream=[float(value) for value in stitched.tolist()],
                generation=generation,
                parent_id=parent_id,
                oos_dates=[timestamp.isoformat() for timestamp in stitched.index],
                development_fold_returns=fold_returns,
                stress_return_stream=[float(value) for value in stress_stream.tolist()],
            )
        )
    return candidates


def evaluate_candidate(
    candidate: Candidate,
    *,
    qqq_returns: pd.Series,
    tqqq_returns: pd.Series,
    bil_returns: pd.Series,
    annualization_sessions: int = 252,
    gates: Mapping[str, float] | None = None,
    dsr_trial_count: int = DEFAULT_DSR_TRIAL_COUNT,
    dsr_hac_lag: int = DEFAULT_DSR_HAC_LAG,
    min_dsr_stream_rows: int = DEFAULT_MIN_DSR_STREAM_ROWS,
) -> CandidateVerdict:
    """Score one candidate against the paper-tier promotion gates.

    ``qqq_returns``, ``tqqq_returns`` and ``bil_returns`` are full-history
    benchmark series; they are reindexed onto ``candidate.oos_dates`` here so
    every candidate -- even ones from mechanisms with different warm-up
    lengths -- is judged against the exact same benchmark dates it traded.
    """
    thresholds = dict(gates) if gates is not None else DEFAULT_PROMOTION_GATES
    index = pd.DatetimeIndex(candidate.oos_dates)
    stitched = pd.Series(candidate.oos_return_stream, index=index)
    aligned_qqq = qqq_returns.reindex(index)
    aligned_tqqq = tqqq_returns.reindex(index)
    aligned_bil = bil_returns.reindex(index)
    if aligned_qqq.isna().any() or aligned_tqqq.isna().any() or aligned_bil.isna().any():
        raise ValueError(f"benchmark alignment produced missing rows for {candidate.candidate_id}")
    if not candidate.stress_return_stream:
        raise ValueError(f"{candidate.candidate_id} has no stress return stream")

    metrics = recompute_candidate_promotion_metrics(
        candidate_returns=candidate.oos_return_stream,
        qqq_returns=aligned_qqq.tolist(),
        tqqq_returns=aligned_tqqq.tolist(),
        stress_returns=candidate.stress_return_stream,
        development_fold_returns=candidate.development_fold_returns,
        annualization_sessions=annualization_sessions,
    )
    excess_bil = (stitched - aligned_bil).to_numpy()
    sharpe_excess_bil = annualized_sharpe(excess_bil)
    dsr_probability = deflated_sharpe_probability(
        excess_bil, trial_count=dsr_trial_count, hac_lag=dsr_hac_lag
    )
    positive_fold_fraction = metrics["positive_fold_count"] / len(
        candidate.development_fold_returns
    )

    orthogonal = abs(metrics["qqq_correlation"]) <= QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD
    gate_results = {
        "cagr_excess_qqq": metrics["cagr_excess_qqq"] >= thresholds["cagr_excess_qqq_minimum"],
        "sharpe_excess_bil": sharpe_excess_bil > thresholds["sharpe_excess_bil_minimum"],
        "dsr_probability": (
            dsr_probability >= thresholds["dsr_minimum"] and len(stitched) >= min_dsr_stream_rows
        ),
        "max_drawdown": metrics["max_drawdown"] >= thresholds["max_drawdown_minimum"],
        "mar": metrics["mar"] >= thresholds["mar_minimum"],
        "positive_fold_fraction": (
            positive_fold_fraction >= thresholds["minimum_positive_fold_fraction"]
        ),
        "qqq_capture_ratio": (
            True
            if orthogonal
            else metrics["qqq_capture_ratio"] >= thresholds["qqq_capture_ratio_minimum"]
        ),
        "qqq_downside_capture": (
            True
            if orthogonal
            else metrics["qqq_downside_capture"] <= thresholds["qqq_downside_capture_maximum"]
        ),
    }
    return CandidateVerdict(
        candidate=candidate,
        metrics={
            key: (float(value) if isinstance(value, float) else value)
            for key, value in metrics.items()
        },
        sharpe_excess_bil=float(sharpe_excess_bil),
        dsr_probability=float(dsr_probability),
        positive_fold_fraction=float(positive_fold_fraction),
        orthogonal_to_qqq=bool(orthogonal),
        gate_results=gate_results,
        all_gates_pass=bool(all(gate_results.values())),
    )


def _common_time_axis_returns(candidates: Sequence[Candidate]) -> dict[str, list[float]]:
    """Intersect every candidate's OOS dates onto one shared axis for clustering.

    Effective-trials clustering (and the PBO/CSCV return matrix it mirrors)
    requires every candidate to live on one common time axis. Candidates from
    different mechanisms can have different warm-up lengths, so this is done
    once, here, purely for the correlation matrix -- it does not touch the
    per-candidate gate metrics, which are each scored on that candidate's own
    native window.
    """
    indices = [pd.DatetimeIndex(candidate.oos_dates) for candidate in candidates]
    common = indices[0]
    for other in indices[1:]:
        common = common.intersection(other)
    common = common.sort_values()
    if len(common) < 2:
        raise ValueError(
            "candidates share fewer than two common out-of-sample dates; cannot cluster"
        )
    aligned: dict[str, list[float]] = {}
    for candidate, index in zip(candidates, indices, strict=True):
        series = pd.Series(candidate.oos_return_stream, index=index).reindex(common)
        if series.isna().any():
            raise ValueError(f"{candidate.candidate_id} is missing data at a common date")
        aligned[candidate.candidate_id] = series.tolist()
    return aligned


def evaluate_family(
    candidates: Sequence[Candidate],
    *,
    correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    **evaluate_kwargs: Any,
) -> FamilyVerdict:
    """Score every candidate and cluster them into an honest effective ``N``.

    This is the single entry point whether ``candidates`` came from a
    one-point param space (a hand-written mechanism), a many-point grid or
    genetic search, or several mechanisms expanded side by side -- every
    candidate goes through the same :func:`evaluate_candidate` gate logic and
    the same ``effective_independent_trials`` clustering.
    """
    if not candidates:
        raise ValueError("evaluate_family requires at least one candidate")
    verdicts = [evaluate_candidate(candidate, **evaluate_kwargs) for candidate in candidates]
    aligned_returns = _common_time_axis_returns(candidates)
    trials_report = effective_independent_trials(
        aligned_returns, correlation_threshold=correlation_threshold
    )
    return FamilyVerdict(
        candidates=verdicts,
        effective_trials=trials_report,
        raw_candidate_count=trials_report.raw_candidate_count,
        effective_n=trials_report.effective_n,
        breadth_ratio=trials_report.breadth_ratio,
    )


def annualized_cagr(returns: pd.Series, *, sessions_per_year: int = 252) -> float:
    """Compound annual growth rate implied by a daily (or other bar) return series."""
    compounded = float(np.prod(1.0 + returns.to_numpy())) - 1.0
    years = len(returns) / sessions_per_year
    return (1.0 + compounded) ** (1.0 / years) - 1.0


def max_drawdown(returns: pd.Series) -> float:
    """Largest peak-to-trough decline of the wealth curve implied by ``returns``."""
    wealth = (1.0 + returns).cumprod()
    peak = wealth.cummax()
    return float((wealth / peak - 1.0).min())


def recent_window_diagnostic(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    start: str,
    minimum_rows: int = 5,
) -> dict[str, float | int | str | None]:
    """A non-gated "does this still work now" diagnostic over a recent window.

    Per the user's decision recorded in ``scripts/evaluate_vol02_recalibrated.py``:
    the promotion gate uses the full rolling-origin window for statistical
    power; a recent-only slice is reported separately as a diagnostic, never
    blended into the gate.
    """
    cutoff = pd.Timestamp(start)
    if returns.index.tz is not None and cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize(returns.index.tz)
    recent = returns.loc[returns.index >= cutoff]
    recent_benchmark = benchmark_returns.reindex(recent.index).dropna()
    has_enough = len(recent) > minimum_rows
    return {
        "row_count": int(len(recent)),
        "start": recent.index.min().date().isoformat() if len(recent) else None,
        "end": recent.index.max().date().isoformat() if len(recent) else None,
        "cagr": annualized_cagr(recent) if has_enough else None,
        "sharpe": float(annualized_sharpe(recent.to_numpy())) if has_enough else None,
        "max_drawdown": max_drawdown(recent) if has_enough else None,
        "benchmark_cagr": (
            annualized_cagr(recent_benchmark) if recent_benchmark.shape[0] > minimum_rows else None
        ),
    }
