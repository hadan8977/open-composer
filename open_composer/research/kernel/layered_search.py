"""The three-layer search loop that makes wide search legitimate (plan section 6.4).

::

    Layer 1  discovery : hundreds of candidates, scored on TRAIN/DEV ONLY
                         v filter by quality + diversity
    Layer 2  QD archive: few elites per descriptor cell
                         v cluster OOS return streams -> effective N (P1a)
    Layer 3  gate      : effective_n <= 32 required, then the full gate battery

The one rule that makes this legitimate is that Layer 1 and Layer 2 never see
out-of-sample data. If discovery or the QD archive could see
``Candidate.oos_return_stream``, they would (even unintentionally) select for
candidates that happen to look good on the exact data the promotion gate
later scores them on, which silently turns "effective N" back into a fiction
-- the entire point of P1a's clustering is that the OOS stream is spent
*once*, at Layer 3, on a small, already-diversified set of candidates.

This module enforces that boundary structurally, not by convention:
:class:`DevelopmentView` -- the only type Layer 1 and Layer 2 code in this
module ever operates on -- has no ``oos_return_stream`` field at all. There
is nothing to read by mistake. ``Candidate.oos_return_stream`` is read in
exactly one place in this module: :func:`run_layered_search`'s Layer 3 step,
where it is handed to ``evaluate_family`` (``kernel.mechanism_eval``).

Everything else is reused, not reimplemented, per plan section 6.4/6.3:

* the QD archive itself is ``open_composer.research.quality_diversity``'s
  ``build_quality_diversity_archive`` / ``QualityDiversityPolicy``;
* the effective-N clustering and paper-tier gates are
  ``kernel.mechanism_eval.evaluate_family`` / ``evaluate_candidate``, which in
  turn call ``kernel.effective_trials.effective_independent_trials``;
* the anchored walk-forward purge+embargo split is
  ``kernel.rolling_origin.rolling_origin_folds`` (already applied by
  ``expand_mechanism`` before a :class:`Candidate` ever reaches this module).

This module additionally implements the plan section 6.3 anti-lookahead
check for the feature/signal layer itself: :func:`assert_causal_transform`
proves a feature transform's value at date ``t`` cannot change when data
strictly after ``t`` is removed -- the general definition of "uses only
``t-1`` and earlier". Purge+embargo (above) prevents *fold-boundary*
contamination; this check catches *within-signal* lookahead (a centred
rolling window, a full-sample z-score) that fold splitting cannot see because
it operates on the whole array before any split happens.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from open_composer.research.campaign import MAX_FAMILY_EFFECTIVE_TRIAL_COUNT
from open_composer.research.campaign_statistics import annualized_sharpe
from open_composer.research.kernel.behavioral_descriptors import behavioral_descriptors
from open_composer.research.kernel.datamodel import ResearchDataModel
from open_composer.research.kernel.effective_trials import (
    DEFAULT_CORRELATION_THRESHOLD,
    effective_independent_trials,
)
from open_composer.research.kernel.mechanism_eval import Candidate, FamilyVerdict, evaluate_family
from open_composer.research.quality_diversity import (
    QualityDiversityArchive,
    QualityDiversityCandidate,
    QualityDiversityPolicy,
    build_quality_diversity_archive,
)

#: Minimum DSR trial count the harness (``campaign_statistics.
#: deflated_sharpe_probability``) accepts. When clustering collapses a
#: family to a single effective trial, this is the smallest -- and therefore
#: the most conservative direction to round -- value that keeps the DSR call
#: well-defined (see effective_trials.py: "prefer to overestimate N").
_MIN_DSR_TRIAL_COUNT = 2

DEVELOPMENT_QUALITY_METRIC = "development_sharpe"
DEVELOPMENT_PARTITION_ID = "development"


# ---------------------------------------------------------------------------
# Layer 1 / Layer 2: the OOS-blind view
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DevelopmentView(ResearchDataModel):
    """Everything Layer 1 discovery and Layer 2 QD selection are structurally
    permitted to see for one candidate.

    Deliberately has no ``oos_return_stream`` or ``stress_return_stream``
    field. A function that only accepts a :class:`DevelopmentView` cannot
    read out-of-sample data even by mistake -- there is nothing on this type
    to read.
    """

    candidate_id: str
    mechanism_family: str
    param_vector: dict[str, Any]
    generation: int
    parent_id: str | None
    development_returns: list[float]
    development_benchmark_returns: list[float]

    @property
    def flattened_returns(self) -> list[float]:
        return list(self.development_returns)

    @property
    def flattened_benchmark_returns(self) -> list[float]:
        return list(self.development_benchmark_returns)


def development_view(candidate: Candidate, benchmark_returns: pd.Series) -> DevelopmentView:
    """Build the Layer 1/2-safe view of ``candidate``.

    Everything here is aligned on ``candidate.development_dates`` -- the
    region strictly before the first fold's test window, which
    ``expand_mechanism`` asserts is disjoint from the out-of-sample stream.
    ``oos_return_stream``, ``oos_fold_returns``, ``stress_return_stream``
    and ``oos_dates`` are never read.
    """
    if len(candidate.development_dates) != len(candidate.development_returns):
        raise ValueError(f"{candidate.candidate_id}: development dates/returns disagree")
    aligned = benchmark_returns.reindex(pd.DatetimeIndex(candidate.development_dates))
    if aligned.isna().any():
        raise ValueError(
            f"{candidate.candidate_id}: benchmark is missing a development-window date"
        )
    development_benchmark = aligned.tolist()

    return DevelopmentView(
        candidate_id=candidate.candidate_id,
        mechanism_family=candidate.mechanism_family,
        param_vector=dict(candidate.param_vector),
        generation=candidate.generation,
        parent_id=candidate.parent_id,
        development_returns=list(candidate.development_returns),
        development_benchmark_returns=development_benchmark,
    )


#: Below this annualized volatility a candidate is not a strategy, it is cash.
#:
#: Raw Sharpe rewards low variance, so a candidate that barely moves scores
#: spectacularly: hold T-bills and you get a small positive drift divided by a
#: near-zero denominator. The expression-tree search hit this for real -- GP
#: readily evolves formulas that reduce to a constant signal, which means always
#: holding the same sleeve, and those individuals dominated Layer 1 on Sharpe
#: alone. Rejecting them at one search's own admission gate fixed that search and
#: left every other caller exposed, so the floor belongs here, in the shared
#: quality function.
#:
#: 1% annualized is deliberately far below anything tradeable and far above cash:
#: BIL runs about 0.2-0.5%, while a portfolio only 20% exposed to QQQ still clears
#: 4%. It excludes cash impersonators without touching genuinely defensive
#: candidates, which is the distinction that matters -- a strategy that rotates
#: into T-bills during drawdowns is exactly what this project is looking for.
#: Sessions per year used to annualize the volatility floor above.
TRADING_DAYS_PER_YEAR = 252
MIN_DEVELOPMENT_ANNUALIZED_VOLATILITY = 0.01


def development_quality(view: DevelopmentView) -> float:
    """Layer 1's quality score: annualized Sharpe over the development returns only.

    Returns ``-inf`` (never raises) for a candidate that cannot be scored on its
    merits -- too few rows, non-finite values, zero variance, or volatility below
    :data:`MIN_DEVELOPMENT_ANNUALIZED_VOLATILITY` -- so it sorts to the bottom and
    :func:`select_layer1_survivors` drops it, instead of aborting the whole run.
    """
    flattened = np.asarray(view.flattened_returns, dtype=float)
    if flattened.size < 2 or not np.all(np.isfinite(flattened)):
        return float("-inf")
    annualized_volatility = float(np.std(flattened, ddof=1)) * math.sqrt(TRADING_DAYS_PER_YEAR)
    if annualized_volatility < MIN_DEVELOPMENT_ANNUALIZED_VOLATILITY:
        return float("-inf")
    try:
        return float(annualized_sharpe(flattened))
    except ValueError:
        return float("-inf")


def select_layer1_survivors(
    views: Sequence[DevelopmentView],
    *,
    quality_fn: Callable[[DevelopmentView], float] = development_quality,
) -> tuple[dict[str, float], list[DevelopmentView]]:
    """Score every Layer 1 candidate and keep the ones with a finite quality score.

    This is the "filter by quality" half of plan section 6.4's Layer 1 step;
    the "diversity" half is Layer 2's QD archive, which keeps only the best
    survivor per descriptor cell -- the two steps are deliberately not
    duplicated here.
    """
    qualities = {view.candidate_id: quality_fn(view) for view in views}
    survivors = sorted(
        (view for view in views if math.isfinite(qualities[view.candidate_id])),
        key=lambda view: view.candidate_id,
    )
    return qualities, survivors


# ---------------------------------------------------------------------------
# Layer 2: the QD archive (reuses quality_diversity.py wholesale)
# ---------------------------------------------------------------------------

#: The archive's cell key: mechanism identity plus every behavioural
#: dimension from ``behavioral_descriptors``. Five dimensions, not the one
#: (``mechanism_family``-only) dimension the plan flags as degenerate.
LAYER2_DESCRIPTOR_NAMES: tuple[str, ...] = (
    "mechanism_family",
    "benchmark_correlation_bucket",
    "activity_bucket",
    "volatility_bucket",
    "drawdown_bucket",
)


def _sha256_of(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def build_layer2_qd_candidates(
    survivors: Sequence[DevelopmentView],
    qualities: Mapping[str, float],
) -> list[QualityDiversityCandidate]:
    """Turn Layer 1 survivors into ``quality_diversity.py``'s candidate shape.

    Descriptors are computed exclusively from ``development_returns``
    (via ``DevelopmentView.flattened_returns``/``flattened_benchmark_returns``)
    -- Layer 2 never sees ``oos_return_stream``, structurally, for the same
    reason Layer 1 does not (see module docstring).
    """
    qd_candidates: list[QualityDiversityCandidate] = []
    for view in survivors:
        descriptors: dict[str, Any] = {
            "mechanism_family": view.mechanism_family,
            **behavioral_descriptors(
                view.flattened_returns,
                benchmark_returns=view.flattened_benchmark_returns,
            ),
        }
        metrics_payload = {
            "candidate_id": view.candidate_id,
            "development_returns": view.development_returns,
            "quality": qualities[view.candidate_id],
            "descriptors": descriptors,
        }
        qd_candidates.append(
            QualityDiversityCandidate(
                candidate_id=view.candidate_id,
                hypothesis_id=view.mechanism_family,
                branch=view.mechanism_family,
                archive_descriptors=descriptors,
                quality=qualities[view.candidate_id],
                quality_metric=DEVELOPMENT_QUALITY_METRIC,
                visibility_partition=DEVELOPMENT_PARTITION_ID,
                metrics_snapshot_path=f"layer1/{view.candidate_id}/development-metrics.json",
                metrics_snapshot_sha256=_sha256_of(metrics_payload),
                partition_contract_path=f"layer1/{DEVELOPMENT_PARTITION_ID}/partition-contract.json",
                partition_contract_sha256=_sha256_of(
                    {
                        "partition_id": DEVELOPMENT_PARTITION_ID,
                        "descriptor_names": LAYER2_DESCRIPTOR_NAMES,
                    }
                ),
                promotion_eligible=True,
                resource_rung=0,
            )
        )
    return qd_candidates


def build_layer2_policy(
    qd_candidates: Sequence[QualityDiversityCandidate],
    *,
    campaign_id: str,
) -> QualityDiversityPolicy:
    """Build the ``QualityDiversityPolicy`` binding for one discovery run.

    ``campaign_contract_sha256`` here is not a preregistered campaign
    contract hash (P2a discovery runs are not sealed campaigns) -- it is a
    deterministic hash of this run's own candidate inventory, which is all
    ``QualityDiversityPolicy`` needs structurally (a stable, well-formed
    SHA-256 identity) to run its validation.
    """
    registered_ids = tuple(sorted(candidate.candidate_id for candidate in qd_candidates))
    if not registered_ids:
        raise ValueError("build_layer2_policy requires at least one QD candidate")
    by_id = {candidate.candidate_id: candidate for candidate in qd_candidates}
    return QualityDiversityPolicy(
        campaign_id=campaign_id,
        campaign_contract_sha256=_sha256_of(
            {"campaign_id": campaign_id, "candidates": registered_ids}
        ),
        descriptor_names=LAYER2_DESCRIPTOR_NAMES,
        quality_direction="maximize",
        quality_metric=DEVELOPMENT_QUALITY_METRIC,
        quality_partition_id=DEVELOPMENT_PARTITION_ID,
        candidate_budget=len(registered_ids),
        registered_candidate_ids=registered_ids,
        candidate_hypothesis_ids={cid: by_id[cid].hypothesis_id for cid in registered_ids},
        candidate_branch_ids={cid: by_id[cid].branch for cid in registered_ids},
        candidate_promotion_eligibility={
            cid: by_id[cid].promotion_eligible for cid in registered_ids
        },
        candidate_archive_descriptors={
            cid: dict(by_id[cid].archive_descriptors) for cid in registered_ids
        },
    )


def build_layer2_archive(
    survivors: Sequence[DevelopmentView],
    qualities: Mapping[str, float],
    *,
    campaign_id: str,
) -> QualityDiversityArchive:
    """Layer 2: one elite per descriptor cell, via ``quality_diversity.py`` verbatim."""
    qd_candidates = build_layer2_qd_candidates(survivors, qualities)
    policy = build_layer2_policy(qd_candidates, campaign_id=campaign_id)
    return build_quality_diversity_archive(qd_candidates, policy)


# ---------------------------------------------------------------------------
# Layer 3: cluster to effective N, then the full gate battery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayeredSearchVerdict(ResearchDataModel):
    """The end-to-end outcome of one discovery -> QD archive -> gate run."""

    raw_candidate_count: int
    layer1_survivor_count: int
    layer2_elite_count: int
    max_effective_n: int
    effective_n_gate_passed: bool
    #: Effective independent trials across EVERY evaluated candidate, not
    #: just the gated elites. This is what the DSR is charged for.
    search_effective_n: int
    dsr_trial_count: int
    qd_archive: QualityDiversityArchive
    family_verdict: FamilyVerdict | None = None


def run_layered_search(
    candidates: Sequence[Candidate],
    *,
    benchmark_returns: pd.Series,
    campaign_id: str,
    correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
    max_effective_n: int = MAX_FAMILY_EFFECTIVE_TRIAL_COUNT,
    quality_fn: Callable[[DevelopmentView], float] = development_quality,
    **evaluate_family_kwargs: Any,
) -> LayeredSearchVerdict:
    """Run the full Layer 1 -> Layer 2 -> Layer 3 loop over ``candidates``.

    ``evaluate_family_kwargs`` is forwarded to ``kernel.mechanism_eval.
    evaluate_family`` for the Layer 3 gate battery (``qqq_returns``,
    ``tqqq_returns``, ``bil_returns``, ``gates``, ...); ``dsr_trial_count`` is
    set internally from the clustered effective N (P1a) and must not be
    passed here.

    Only this function -- and only in the two ``evaluate_family`` calls at
    the bottom -- reads ``Candidate.oos_return_stream``. Everything above
    that point operates on :class:`DevelopmentView`.
    """
    if "dsr_trial_count" in evaluate_family_kwargs:
        raise ValueError(
            "run_layered_search sets dsr_trial_count internally from the clustered "
            "effective N; callers must not override it"
        )
    if not candidates:
        raise ValueError("run_layered_search requires at least one candidate")
    candidate_ids = [candidate.candidate_id for candidate in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_id values must be unique")

    # --- Layer 1: discovery, development-only -----------------------------
    views = [development_view(candidate, benchmark_returns) for candidate in candidates]
    qualities, survivors = select_layer1_survivors(views, quality_fn=quality_fn)
    if not survivors:
        return LayeredSearchVerdict(
            raw_candidate_count=len(candidates),
            layer1_survivor_count=0,
            layer2_elite_count=0,
            max_effective_n=max_effective_n,
            effective_n_gate_passed=False,
            search_effective_n=0,
            dsr_trial_count=0,
            qd_archive=_empty_archive_placeholder(campaign_id),
            family_verdict=None,
        )

    # --- Layer 2: QD archive, still development-only -----------------------
    archive = build_layer2_archive(survivors, qualities, campaign_id=campaign_id)
    elite_ids = {elite.candidate.candidate_id for elite in archive.elites}
    candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    elite_candidates = [candidates_by_id[cid] for cid in sorted(elite_ids)]

    # --- Layer 3: cluster to effective N, then gate. This is the only place
    # oos_return_stream is read. -------------------------------------------
    probe = evaluate_family(
        elite_candidates,
        correlation_threshold=correlation_threshold,
        **evaluate_family_kwargs,
    )
    if probe.effective_n > max_effective_n:
        return LayeredSearchVerdict(
            raw_candidate_count=len(candidates),
            layer1_survivor_count=len(survivors),
            layer2_elite_count=len(elite_candidates),
            max_effective_n=max_effective_n,
            effective_n_gate_passed=False,
            search_effective_n=0,
            dsr_trial_count=0,
            qd_archive=archive,
            family_verdict=probe,
        )

    # The DSR trial count must reflect the whole search, not the survivors.
    # Clustering only the elites is exactly the "hand-picked subset" that
    # campaign.py's _effective_trial_clustering_blockers exists to reject: 60
    # candidates screened down to 5 and then clustered to 3 would charge the
    # DSR for 3 trials while the selection bias came from 60. Cluster every
    # candidate that was actually evaluated, and take the larger of that and
    # the elite-level count so this can only ever tighten the gate.
    search_trials = effective_independent_trials(
        {candidate.candidate_id: candidate.oos_return_stream for candidate in candidates},
        correlation_threshold=correlation_threshold,
    )
    calibrated_trial_count = max(search_trials.effective_n, probe.effective_n, _MIN_DSR_TRIAL_COUNT)
    final = evaluate_family(
        elite_candidates,
        correlation_threshold=correlation_threshold,
        dsr_trial_count=calibrated_trial_count,
        **evaluate_family_kwargs,
    )
    return LayeredSearchVerdict(
        raw_candidate_count=len(candidates),
        layer1_survivor_count=len(survivors),
        layer2_elite_count=len(elite_candidates),
        max_effective_n=max_effective_n,
        effective_n_gate_passed=True,
        search_effective_n=search_trials.effective_n,
        dsr_trial_count=calibrated_trial_count,
        qd_archive=archive,
        family_verdict=final,
    )


def _empty_archive_placeholder(campaign_id: str) -> QualityDiversityArchive:
    """A zero-candidate archive for the (degenerate) all-candidates-rejected case.

    ``QualityDiversityPolicy`` requires ``candidate_budget >= 1``, so an empty
    Layer 1 survivor set cannot build a policy with zero registered
    candidates; instead, one placeholder id is registered and immediately
    excluded, giving a policy-valid, genuinely empty archive (zero eligible
    candidates, zero elites) via the same ``build_quality_diversity_archive``
    every non-degenerate run uses -- no bespoke archive shape.
    """
    placeholder_id = "layer1-no-survivors-placeholder"
    descriptors: dict[str, Any] = dict.fromkeys(LAYER2_DESCRIPTOR_NAMES, "none")
    qd_candidate = QualityDiversityCandidate(
        candidate_id=placeholder_id,
        hypothesis_id="none",
        branch="none",
        archive_descriptors=descriptors,
        quality=float("-inf"),
        quality_metric=DEVELOPMENT_QUALITY_METRIC,
        visibility_partition=DEVELOPMENT_PARTITION_ID,
        metrics_snapshot_path=f"layer1/{placeholder_id}/development-metrics.json",
        metrics_snapshot_sha256=_sha256_of({"placeholder": True}),
        partition_contract_path=f"layer1/{DEVELOPMENT_PARTITION_ID}/partition-contract.json",
        partition_contract_sha256=_sha256_of({"placeholder": True}),
        promotion_eligible=False,
        resource_rung=0,
    )
    policy = build_layer2_policy([qd_candidate], campaign_id=campaign_id)
    return build_quality_diversity_archive([], policy, excluded_candidate_ids=[placeholder_id])


# ---------------------------------------------------------------------------
# Anti-lookahead (plan section 6.3): causal-invariance check
# ---------------------------------------------------------------------------


class LookaheadError(ValueError):
    """Raised when a feature/signal transform is not causal.

    "Not causal" means: its value at some date ``t`` changed when data
    strictly after ``t`` was removed from the input, i.e. the transform used
    information from ``t`` or later to compute the value it reports *at*
    ``t``. Confirmed non-anticipating transforms (a rolling mean lagged by
    one bar, a trailing z-score) are invariant to that truncation by
    construction; a centred rolling window or a full-sample statistic is
    not.
    """


def assert_causal_transform(
    transform: Callable[[pd.Series], pd.Series],
    raw_series: pd.Series,
    *,
    probe_count: int = 5,
) -> None:
    """Assert ``transform`` never uses data at or after the date it labels.

    For each of ``probe_count`` deterministic, evenly spaced probe dates in
    the middle of ``raw_series``, this recomputes ``transform`` twice: once
    on the full series, once on the series truncated to end exactly at the
    probe date. A causal transform must report the identical value at the
    probe date either way, because none of the removed (future) rows should
    have been able to influence it. Raises :class:`LookaheadError` the first
    time a probe disagrees.

    This is the generic form of the plan section 6.3 requirement ("features
    may only use data at t-1 and earlier"): it catches a centred rolling mean
    or a full-sample z-score without needing a mechanism-specific check,
    because both of those recompute differently once you delete the future
    rows they depend on.
    """
    if not isinstance(raw_series.index, pd.DatetimeIndex):
        raise ValueError("raw_series must be indexed by a DatetimeIndex")
    if raw_series.index.has_duplicates or not raw_series.index.is_monotonic_increasing:
        raise ValueError("raw_series index must be sorted and duplicate-free")
    if probe_count < 1:
        raise ValueError("probe_count must be a positive integer")

    full_output = transform(raw_series)
    if not isinstance(full_output, pd.Series) or not isinstance(
        full_output.index, pd.DatetimeIndex
    ):
        raise ValueError("transform must return a Series indexed by a DatetimeIndex")

    length = len(raw_series)
    # Probe the whole usable span, not a fixed middle window. A fixed [40%, 90%]
    # window leaves two blind spots, and raising ``probe_count`` does not close
    # them because the extra probes land inside the same window: a leak anchored
    # to absolute dates in the last 10% of the series survives 40 probes. The
    # tail is exactly where an accidental leak is most likely, since that is the
    # most recent data. So the lower bound is where the transform's own warmup
    # ends (its first finite output), and the upper bound is the last position
    # that still has a future to remove -- at ``length - 1`` truncation is a
    # no-op and the check would be vacuous.
    finite_positions = [
        i
        for i, value in enumerate(full_output.to_numpy())
        if isinstance(value, float | int) and math.isfinite(float(value))
    ]
    lower = min(finite_positions) if finite_positions else 0
    upper = length - 2
    if upper <= lower:
        raise ValueError("raw_series is too short to probe for lookahead")
    span = max(probe_count - 1, 1)
    positions = sorted({lower + round(i * (upper - lower) / span) for i in range(probe_count)})

    checked = 0
    for position in positions:
        probe_date = raw_series.index[position]
        truncated_output = transform(raw_series.iloc[: position + 1])
        if probe_date not in full_output.index or probe_date not in truncated_output.index:
            continue
        full_value = float(full_output.loc[probe_date])
        truncated_value = float(truncated_output.loc[probe_date])
        full_defined = math.isfinite(full_value)
        truncated_defined = math.isfinite(truncated_value)
        if full_defined != truncated_defined:
            raise LookaheadError(
                f"{probe_date.date()}: value became "
                f"{'defined' if truncated_defined else 'undefined'} when data strictly after "
                "this date was removed -- transform is not causal"
            )
        if full_defined and not math.isclose(
            full_value, truncated_value, rel_tol=1e-9, abs_tol=1e-12
        ):
            raise LookaheadError(
                f"{probe_date.date()}: value changed from {full_value} to {truncated_value} when "
                "data strictly after this date was removed -- transform reads future information"
            )
        checked += 1
    if checked == 0:
        raise ValueError(
            "no probe date had a defined value in both the full and truncated output; "
            "cannot assess causality (probe window may be inside the transform's warm-up)"
        )
