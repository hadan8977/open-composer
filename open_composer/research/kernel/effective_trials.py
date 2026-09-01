"""Effective independent trial counting for multiple-testing corrections.

The Deflated Sharpe Ratio's ``N`` is the number of *independent* trials, not the
literal number of backtests that were run.  Two candidates that differ only by
``MA50`` vs ``MA51`` produce nearly the same return stream and therefore do not
constitute two independent looks at the data; counting them as two inflates the
multiple-testing penalty until the gate becomes mathematically unpassable (this
project previously carried a lifetime count of 8195, at which a Sharpe 1.0
strategy scores DSR 0.026 against a 0.75 threshold).

López de Prado (2018) resolves this by clustering the *candidate return
streams* and using the cluster count as the effective ``N``.  That also gives a
measurable definition of "fake exploration breadth": 500 candidates that
collapse into 3 clusters mean three ideas were tested with 167 parameter
variations each, while 500 candidates that form 80 clusters mean 80 genuinely
different behaviours were explored.  ``breadth_ratio`` is that diagnostic.

References:
    https://www.ml4trading.io/docs/diagnostic/methods/deflated-sharpe-ratio/
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

Implementation notes:

* Correlation is Pearson on the raw return streams, matching the convention of
  ``open_composer.research.campaign._pearson_correlation`` (mean-centred, clipped
  into ``[-1, 1]``, and undefined -- an error -- for a zero-variance stream).
* The linkage is ``complete``.  Complete linkage merges two groups only when
  *every* cross pair is within the cut distance, so every cluster satisfies the
  exact invariant "all members are mutually correlated at ``|rho| >=
  correlation_threshold``".  It is also the conservative choice: it never
  produces fewer clusters than average or single linkage, and over-estimating
  ``N`` tightens the gate while under-estimating it loosens the gate.
* ``numpy`` and ``scipy`` only -- no new dependency.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from open_composer.research.kernel.datamodel import ResearchDataModel

EffectiveTrialsMethod = Literal["hierarchical"]

#: Two return streams correlated at or above this level are treated as the same
#: trial.  Raising it yields more clusters (a stricter gate); lowering it yields
#: fewer clusters (a weaker gate), which is why callers that feed a promotion
#: gate must floor the threshold at this value rather than accept an arbitrary
#: caller-supplied one.
DEFAULT_CORRELATION_THRESHOLD = 0.7

#: Pearson correlation needs at least two observations to be defined at all.
MIN_OBSERVATIONS = 2

_LINKAGE_METHOD = "complete"
_ZERO_TOLERANCE = 1e-15


@dataclass(frozen=True)
class TrialCluster(ResearchDataModel):
    """One group of candidates that count as a single independent trial."""

    cluster_id: str
    members: list[str] = field(default_factory=list)
    #: Smallest ``|rho|`` between any two members; guaranteed ``>=``
    #: ``correlation_threshold`` by the complete-linkage cut.  ``1.0`` for a
    #: singleton cluster (a stream is perfectly correlated with itself).
    min_absolute_intra_correlation: float = 1.0
    mean_absolute_intra_correlation: float = 1.0


@dataclass(frozen=True)
class EffectiveTrialsReport(ResearchDataModel):
    """Effective independent trial count for one multiple-testing family."""

    method: EffectiveTrialsMethod
    linkage_method: str
    correlation_threshold: float
    #: The number the DSR/PBO/SPA family gate must use as its trial count.
    effective_n: int
    #: How many backtests were actually run; the audit denominator.
    raw_candidate_count: int
    #: ``effective_n / raw_candidate_count``: 1.0 means every candidate was a
    #: genuinely distinct trial, values near zero mean manufactured breadth.
    breadth_ratio: float
    observation_count: int
    candidate_ids: list[str] = field(default_factory=list)
    clusters: list[TrialCluster] = field(default_factory=list)
    #: Largest ``|rho|`` between candidates placed in different clusters; a
    #: value close to ``correlation_threshold`` means the partition is a near
    #: tie and the count is sensitive to the threshold.
    max_absolute_inter_cluster_correlation: float = 0.0

    @property
    def cluster_members(self) -> dict[str, list[str]]:
        return {cluster.cluster_id: list(cluster.members) for cluster in self.clusters}


def _validate_threshold(correlation_threshold: float) -> float:
    threshold = float(correlation_threshold)
    if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError(
            "correlation_threshold must be a finite value in the open interval "
            f"(0, 1); got {correlation_threshold!r}"
        )
    return threshold


def _return_matrix(
    candidate_returns: Mapping[str, Sequence[float]],
) -> tuple[list[str], np.ndarray]:
    if not isinstance(candidate_returns, Mapping):
        raise TypeError("candidate_returns must be a mapping of candidate id to return stream")
    if not candidate_returns:
        raise ValueError("effective trial counting requires at least one candidate")
    candidate_ids = sorted(str(candidate_id) for candidate_id in candidate_returns)
    if any(not candidate_id.strip() for candidate_id in candidate_ids):
        raise ValueError("candidate ids must be non-empty strings")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate ids must be unique")

    rows: list[np.ndarray] = []
    lengths: set[int] = set()
    for candidate_id in candidate_ids:
        values = np.asarray(list(candidate_returns[candidate_id]), dtype=float)
        if values.ndim != 1:
            raise ValueError(f"candidate return stream must be one-dimensional: {candidate_id}")
        if not np.isfinite(values).all():
            raise ValueError(f"candidate return stream has non-finite values: {candidate_id}")
        lengths.add(values.shape[0])
        rows.append(values)
    if len(lengths) != 1:
        raise ValueError(
            f"all candidates must share one time axis; got return stream lengths {sorted(lengths)}"
        )
    observation_count = lengths.pop()
    if observation_count < MIN_OBSERVATIONS:
        raise ValueError(
            "effective trial counting requires at least "
            f"{MIN_OBSERVATIONS} observations per candidate; got {observation_count}"
        )
    return candidate_ids, np.vstack(rows)


def _absolute_correlation_matrix(matrix: np.ndarray, candidate_ids: list[str]) -> np.ndarray:
    """Pearson ``|rho|`` matrix, matching ``campaign._pearson_correlation``."""
    centered = matrix - matrix.mean(axis=1, keepdims=True)
    norms = np.sqrt(np.square(centered).sum(axis=1))
    degenerate = [
        candidate_id
        for candidate_id, norm in zip(candidate_ids, norms.tolist(), strict=True)
        if norm <= _ZERO_TOLERANCE
    ]
    if degenerate:
        raise ValueError(
            "correlation is undefined for a zero-variance return series: " + ",".join(degenerate)
        )
    correlation = (centered @ centered.T) / np.outer(norms, norms)
    correlation = np.clip(correlation, -1.0, 1.0)
    absolute = np.abs(correlation)
    absolute = 0.5 * (absolute + absolute.T)
    np.fill_diagonal(absolute, 1.0)
    return absolute


def _labels(absolute_correlation: np.ndarray, correlation_threshold: float) -> np.ndarray:
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform

    distance = np.clip(1.0 - absolute_correlation, 0.0, 1.0)
    np.fill_diagonal(distance, 0.0)
    condensed = squareform(distance, checks=False)
    tree = linkage(condensed, method=_LINKAGE_METHOD)
    cut = 1.0 - correlation_threshold
    return np.asarray(fcluster(tree, t=cut, criterion="distance"), dtype=int)


def _build_clusters(
    candidate_ids: list[str],
    labels: np.ndarray,
    absolute_correlation: np.ndarray,
) -> list[TrialCluster]:
    grouped: dict[int, list[int]] = {}
    for index, label in enumerate(labels.tolist()):
        grouped.setdefault(int(label), []).append(index)
    # Deterministic ordering: clusters follow the input position of their first
    # member, which itself follows the sorted candidate ids.
    ordered = sorted(grouped.values(), key=lambda members: members[0])
    clusters: list[TrialCluster] = []
    for position, members in enumerate(ordered, start=1):
        if len(members) == 1:
            minimum = 1.0
            mean = 1.0
        else:
            block = absolute_correlation[np.ix_(members, members)]
            upper = block[np.triu_indices(len(members), k=1)]
            minimum = float(upper.min())
            mean = float(upper.mean())
        clusters.append(
            TrialCluster(
                cluster_id=f"cluster_{position:03d}",
                members=[candidate_ids[index] for index in members],
                min_absolute_intra_correlation=minimum,
                mean_absolute_intra_correlation=mean,
            )
        )
    return clusters


def _max_inter_cluster_correlation(
    absolute_correlation: np.ndarray,
    labels: np.ndarray,
) -> float:
    different = labels[:, None] != labels[None, :]
    if not different.any():
        return 0.0
    return float(absolute_correlation[different].max())


def effective_independent_trials(
    candidate_returns: Mapping[str, Sequence[float]],
    *,
    method: EffectiveTrialsMethod = "hierarchical",
    correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
) -> EffectiveTrialsReport:
    """Return the effective independent trial count for a candidate family.

    Args:
        candidate_returns: candidate id -> return stream.  Every candidate must
            live on one common time axis (the same matrix the PBO/CSCV and SPA
            recomputation already consume), otherwise the pairwise correlations
            are not comparable.
        method: clustering family.  Only ``"hierarchical"`` is supported.
        correlation_threshold: candidates whose pairwise ``|rho|`` is at or
            above this level are the same trial.

    Returns:
        An :class:`EffectiveTrialsReport` carrying ``effective_n`` (the DSR
        trial count), ``raw_candidate_count``, the members of every cluster and
        ``breadth_ratio``.

    Raises:
        ValueError: for an unsupported method, an out-of-range threshold, an
            empty family, ragged/non-finite return streams, or a zero-variance
            stream (for which Pearson correlation is undefined).
    """
    if method != "hierarchical":
        raise ValueError(f"unsupported effective trial clustering method: {method!r}")
    threshold = _validate_threshold(correlation_threshold)
    candidate_ids, matrix = _return_matrix(candidate_returns)
    observation_count = int(matrix.shape[1])
    raw_candidate_count = len(candidate_ids)

    if raw_candidate_count == 1:
        absolute_correlation = np.ones((1, 1), dtype=float)
        labels = np.ones(1, dtype=int)
    else:
        absolute_correlation = _absolute_correlation_matrix(matrix, candidate_ids)
        labels = _labels(absolute_correlation, threshold)

    clusters = _build_clusters(candidate_ids, labels, absolute_correlation)
    effective_n = len(clusters)
    return EffectiveTrialsReport(
        method="hierarchical",
        linkage_method=_LINKAGE_METHOD,
        correlation_threshold=threshold,
        effective_n=effective_n,
        raw_candidate_count=raw_candidate_count,
        breadth_ratio=effective_n / raw_candidate_count,
        observation_count=observation_count,
        candidate_ids=list(candidate_ids),
        clusters=clusters,
        max_absolute_inter_cluster_correlation=_max_inter_cluster_correlation(
            absolute_correlation, labels
        ),
    )
