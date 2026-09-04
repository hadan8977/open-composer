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
    MIN_DSR_STREAM_ROWS,
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
from open_composer.research.kernel.gate_contract import PreregisteredGates
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
#:
#: **These are development defaults, not a promotion authority.** On the campaign
#: path the same thresholds are fields of a hash-sealed, preregistered contract
#: (``CampaignCandidatePromotionPolicy`` in ``campaign.py``), committed before any
#: result is visible. A plain module-level dict has no such protection -- anyone
#: can edit it after seeing a verdict. So every :class:`CandidateVerdict` records
#: ``gates_provenance``, and any real promotion decision must pass its
#: preregistered thresholds in explicitly rather than inherit these.
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
#: Imported rather than redeclared: two copies of a gate constant drift.
DEFAULT_MIN_DSR_STREAM_ROWS = MIN_DSR_STREAM_ROWS


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
    #: Per-fold slices of ``oos_return_stream`` -- i.e. each fold's TEST window.
    #: Flattened, this is exactly ``oos_return_stream``. It is the right input
    #: for the ``positive_fold_fraction`` gate ("how many out-of-sample folds
    #: were positive") and it must never be used to select between candidates.
    #: It was previously named ``development_fold_returns``, which read like
    #: in-sample data and invited exactly that misuse.
    oos_fold_returns: list[list[float]] = field(default_factory=list)
    #: The contamination-free development partition: returns strictly before
    #: the FIRST fold's test window, with the embargo already applied. This is
    #: the only stream a selection layer may look at.
    #:
    #: Per-fold training windows would be the obvious choice and are the wrong
    #: one. They are anchored and expanding, so fold 5's training window
    #: contains folds 1-4's *test* windows. That is correct for walk-forward
    #: fitting -- by the time fold 5 trains, those years really are history --
    #: but it is contamination for *selection*: ranking candidates on data that
    #: overlaps the out-of-sample stream makes the ranking mechanically
    #: correlated with the score the gate is about to compute. Only the region
    #: that is never a test window is safe, and that is this one.
    development_returns: list[float] = field(default_factory=list)
    #: Calendar index for :attr:`development_returns`. Disjoint from
    #: ``oos_dates`` by construction.
    development_dates: list[str] = field(default_factory=list)
    stress_return_stream: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateVerdict(ResearchDataModel):
    """A candidate's promotion metrics and paper-tier gate results."""

    candidate: Candidate
    metrics: dict[str, float | int | str]
    sharpe_excess_bil: float
    dsr_probability: float
    positive_fold_fraction: float
    orthogonal_to_qqq: bool
    gate_results: dict[str, bool]
    all_gates_pass: bool
    #: ``"preregistered"`` when the thresholds came from a git-committed
    #: :class:`~open_composer.research.kernel.gate_contract.PreregisteredGates`,
    #: ``"explicit"`` for a bare mapping passed in by a caller, and
    #: ``"kernel_defaults"`` when it inherited :data:`DEFAULT_PROMOTION_GATES`.
    gates_provenance: str = "kernel_defaults"
    #: Where the preregistered thresholds came from, when they were.
    gate_contract: dict[str, str] = field(default_factory=dict)
    #: Gates that were not evaluated on their merits because they are
    #: meaningless for this candidate. Today that is the pair of QQQ-capture
    #: gates for a candidate uncorrelated with QQQ: a capture ratio against an
    #: index you do not track is noise, so ``campaign.py`` passes them by
    #: construction. Passing by construction is not evidence, and a report that
    #: says "8 of 8" without saying which two were never really tested reads
    #: stronger than the evidence is. Listing them keeps the count honest.
    gates_not_applicable: tuple[str, ...] = ()

    @property
    def evaluated_gate_count(self) -> int:
        """Gates actually tested on their merits, i.e. excluding the N/A ones."""
        return len(self.gate_results) - len(self.gates_not_applicable)

    @property
    def promotion_eligible(self) -> bool:
        """Passing every gate is necessary for promotion, and not sufficient.

        A verdict whose thresholds were not preregistered proves only that the
        candidate cleared a bar; it cannot show the bar predated the result. That
        is a research signal, never a promotion authority, so this stays False
        for it however good the numbers look.
        """
        return self.all_gates_pass and self.gates_provenance == "preregistered"


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
        oos_fold_returns = [
            stitched.loc[
                pd.Timestamp(fold.train.test_start) : pd.Timestamp(fold.train.test_end)
            ].tolist()
            for fold in folds
        ]
        # Sliced from the RAW series, not from ``stitched``: the training window
        # is by construction disjoint from every test window, so it cannot be
        # recovered from the stitched out-of-sample stream at all.
        # The first fold's training window is exactly the region that is never
        # any fold's test window, because the folds' test windows run forward
        # in time from it. Its end already has the embargo applied.
        development_slice = raw_returns.loc[
            pd.Timestamp(folds[0].train.train_start) : pd.Timestamp(folds[0].train.train_end)
        ]
        development_returns = development_slice.tolist()
        development_dates = [timestamp.isoformat() for timestamp in development_slice.index]
        overlap = set(development_dates) & {timestamp.isoformat() for timestamp in stitched.index}
        if overlap:
            raise ValueError(
                f"{mechanism.family}[{index}]: development partition overlaps the "
                f"out-of-sample stream on {len(overlap)} date(s)"
            )

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
                oos_fold_returns=oos_fold_returns,
                development_returns=development_returns,
                development_dates=development_dates,
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
    gates: Mapping[str, float] | PreregisteredGates | None = None,
    dsr_trial_count: int = DEFAULT_DSR_TRIAL_COUNT,
    dsr_hac_lag: int = DEFAULT_DSR_HAC_LAG,
    min_dsr_stream_rows: int = DEFAULT_MIN_DSR_STREAM_ROWS,
    benchmark_returns: pd.Series | None = None,
    benchmark_name: str = "QQQ",
) -> CandidateVerdict:
    """Score one candidate against the paper-tier promotion gates.

    ``qqq_returns``, ``tqqq_returns`` and ``bil_returns`` are full-history
    benchmark series; they are reindexed onto ``candidate.oos_dates`` here so
    every candidate -- even ones from mechanisms with different warm-up
    lengths -- is judged against the exact same benchmark dates it traded.

    ``benchmark_returns`` is ``None`` by default, which keeps this function's
    behavior identical to before Step 10 (see
    docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 3.2):
    the candidate is judged against absolute QQQ CAGR and QQQ capture, the
    ``config/promotion/kernel-paper-tier-gates.json`` key names, exactly as
    today. That contract was calibrated for 3x-leveraged Nasdaq router
    candidates and auto-fails any un-levered strategy family regardless of
    merit (QQQ's own trailing CAGR is ~20%/yr). When ``benchmark_returns`` is
    given -- the candidate's own natural benchmark family, e.g. QQQ or SPY for
    a beta-exposure router, SPY for a cross-asset trend book -- it is instead
    volatility-matched to the candidate before comparing CAGR:
    ``benchmark_vm = w*benchmark + (1-w)*BIL``, where
    ``w = realized_vol(candidate)/realized_vol(benchmark)`` on the stitched
    OOS window (``w>1`` means the blend borrows at the BIL rate to match a
    candidate riskier than the raw benchmark). Gates are then evaluated under
    the ``config/promotion/unlevered-family-paper-tier-gates.json`` key names
    (``cagr_excess_vol_matched_benchmark_minimum`` etc. -- see
    ``gate_contract.UNLEVERED_FAMILY_GATE_KEYS``); the caller must pass a
    ``gates`` contract using those same key names in that case. ``metrics``
    always additionally records the vol-matched figures plus ``benchmark_name``
    and ``vol_match_weight`` when this path is taken, so a report can show
    both benchmark framings.
    """
    if isinstance(gates, PreregisteredGates):
        thresholds = dict(gates.values)
        gates_provenance = "preregistered"
        gate_contract = gates.as_provenance()
    elif gates is not None:
        thresholds = dict(gates)
        gates_provenance = "explicit"
        gate_contract = {}
    else:
        thresholds = DEFAULT_PROMOTION_GATES
        gates_provenance = "kernel_defaults"
        gate_contract = {}
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
        development_fold_returns=candidate.oos_fold_returns,
        annualization_sessions=annualization_sessions,
    )
    excess_bil = (stitched - aligned_bil).to_numpy()
    sharpe_excess_bil = annualized_sharpe(excess_bil)
    dsr_probability = deflated_sharpe_probability(
        excess_bil, trial_count=dsr_trial_count, hac_lag=dsr_hac_lag
    )
    positive_fold_fraction = metrics["positive_fold_count"] / len(candidate.oos_fold_returns)

    orthogonal = abs(metrics["qqq_correlation"]) <= QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD

    vol_match_weight: float | None = None
    vm_metrics: dict[str, float] | None = None
    if benchmark_returns is not None:
        aligned_benchmark = benchmark_returns.reindex(index)
        if aligned_benchmark.isna().any():
            raise ValueError(
                f"benchmark_returns alignment produced missing rows for {candidate.candidate_id}"
            )
        candidate_vol = float(stitched.std())
        benchmark_vol = float(aligned_benchmark.std())
        if not math.isfinite(benchmark_vol) or benchmark_vol <= 0.0:
            raise ValueError(
                f"benchmark_returns has non-positive realized volatility for "
                f"{candidate.candidate_id}"
            )
        vol_match_weight = candidate_vol / benchmark_vol
        vol_matched_benchmark = (
            vol_match_weight * aligned_benchmark + (1.0 - vol_match_weight) * aligned_bil
        )
        # Reuses the exact same, already-tested CAGR/capture-ratio math as the
        # QQQ path above by substituting the vol-matched series in its place;
        # ``tqqq_returns`` here is unused (its outputs are diagnostic-only and
        # discarded below), passed only to satisfy the shared row-count check.
        raw_vm_metrics = recompute_candidate_promotion_metrics(
            candidate_returns=candidate.oos_return_stream,
            qqq_returns=vol_matched_benchmark.tolist(),
            tqqq_returns=aligned_tqqq.tolist(),
            stress_returns=candidate.stress_return_stream,
            development_fold_returns=candidate.oos_fold_returns,
            annualization_sessions=annualization_sessions,
        )
        vm_metrics = {
            "cagr_excess_vol_matched_benchmark": float(raw_vm_metrics["cagr_excess_qqq"]),
            "benchmark_vm_capture_ratio": float(raw_vm_metrics["qqq_capture_ratio"]),
            "benchmark_vm_downside_capture": float(raw_vm_metrics["qqq_downside_capture"]),
            "benchmark_vm_correlation": float(raw_vm_metrics["qqq_correlation"]),
        }

    if vm_metrics is not None:
        # The un-levered families this path serves are chosen to be exposed to
        # their benchmark (a beta-exposure router IS long QQQ/SPY when
        # risk-on), so unlike the QQQ path above there is no orthogonality
        # carve-out here: both capture gates are always evaluated on their
        # merits.
        gates_not_applicable: tuple[str, ...] = ()
        gate_results = {
            "cagr_excess_vol_matched_benchmark": (
                vm_metrics["cagr_excess_vol_matched_benchmark"]
                >= thresholds["cagr_excess_vol_matched_benchmark_minimum"]
            ),
            "sharpe_excess_bil": sharpe_excess_bil > thresholds["sharpe_excess_bil_minimum"],
            "dsr_probability": (
                dsr_probability >= thresholds["dsr_minimum"]
                and len(stitched) >= min_dsr_stream_rows
            ),
            "max_drawdown": metrics["max_drawdown"] >= thresholds["max_drawdown_minimum"],
            "mar": metrics["mar"] >= thresholds["mar_minimum"],
            "positive_fold_fraction": (
                positive_fold_fraction >= thresholds["minimum_positive_fold_fraction"]
            ),
            "benchmark_vm_capture_ratio": (
                vm_metrics["benchmark_vm_capture_ratio"]
                >= thresholds["benchmark_vm_capture_ratio_minimum"]
            ),
            "benchmark_vm_downside_capture": (
                vm_metrics["benchmark_vm_downside_capture"]
                <= thresholds["benchmark_vm_downside_capture_maximum"]
            ),
        }
    else:
        # _qqq_capture_gate_passes returns (True, True) for an orthogonal candidate
        # rather than evaluating the ratios. Record which gates that covers so the
        # pass count cannot quietly overstate how much was actually tested.
        gates_not_applicable = ("qqq_capture_ratio", "qqq_downside_capture") if orthogonal else ()
        gate_results = {
            "cagr_excess_qqq": metrics["cagr_excess_qqq"] >= thresholds["cagr_excess_qqq_minimum"],
            "sharpe_excess_bil": sharpe_excess_bil > thresholds["sharpe_excess_bil_minimum"],
            "dsr_probability": (
                dsr_probability >= thresholds["dsr_minimum"]
                and len(stitched) >= min_dsr_stream_rows
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
    full_metrics: dict[str, float | int | str] = {
        key: (float(value) if isinstance(value, float) else value) for key, value in metrics.items()
    }
    if vm_metrics is not None:
        full_metrics.update(vm_metrics)
        full_metrics["benchmark_name"] = benchmark_name
        assert vol_match_weight is not None
        full_metrics["vol_match_weight"] = float(vol_match_weight)
    return CandidateVerdict(
        candidate=candidate,
        metrics=full_metrics,
        sharpe_excess_bil=float(sharpe_excess_bil),
        dsr_probability=float(dsr_probability),
        positive_fold_fraction=float(positive_fold_fraction),
        orthogonal_to_qqq=bool(orthogonal),
        gate_results=gate_results,
        all_gates_pass=bool(all(gate_results.values())),
        gates_provenance=gates_provenance,
        gate_contract=gate_contract,
        gates_not_applicable=gates_not_applicable,
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
