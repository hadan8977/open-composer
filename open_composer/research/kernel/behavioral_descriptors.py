"""Behavioural MAP-Elites descriptors for the QD archive (plan section 6.1).

``open_composer.research.quality_diversity`` implements a fully general
MAP-Elites archive, but every campaign that has used it so far keyed its
cells on ``mechanism_family`` alone -- a single categorical dimension, which
degenerates MAP-Elites into "keep the best candidate per mechanism", not
"keep the best candidate per *behaviour*". This module adds genuinely
behavioural dimensions computed from a candidate's own return stream:

* ``benchmark_correlation_bucket`` -- how correlated the candidate is with a
  benchmark (e.g. QQQ): orthogonal strategies and directional bets are
  different behaviours even if they share a mechanism family.
* ``activity_bucket`` -- a turnover/switching-frequency proxy (the fraction
  of bars whose return sign differs from the previous bar's).
* ``volatility_bucket`` -- annualized realized volatility.
* ``drawdown_bucket`` -- maximum peak-to-trough drawdown magnitude.

Every bucket boundary below is a **declared constant**, fixed before any
candidate is scored. Fitting bucket edges to the distribution of candidates a
search run happens to produce would be a selection leak (the cells would
silently adapt to make *this run's* candidates look diverse); these edges
are therefore plain domain-knowledge cutoffs (e.g. "15% annualized vol is
low for a leveraged-ETF rotation, 40% is high") chosen without looking at any
particular run's output.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from open_composer.research.quality_diversity import DescriptorValue

ANNUALIZATION_PERIODS = 252

#: Pearson |correlation| is not signed here -- ``correlation_bucket`` below
#: reports direction and magnitude jointly via signed cutoffs.
CORRELATION_BUCKET_EDGES: tuple[float, ...] = (-0.5, -0.15, 0.15, 0.5)
CORRELATION_BUCKET_LABELS: tuple[str, ...] = (
    "strong_negative",
    "weak_negative",
    "orthogonal",
    "weak_positive",
    "strong_positive",
)

#: Fraction of bars whose return sign flips relative to the prior bar -- a
#: mechanism-agnostic proxy for how often a strategy is switching exposure.
ACTIVITY_BUCKET_EDGES: tuple[float, ...] = (0.30, 0.45, 0.60)
ACTIVITY_BUCKET_LABELS: tuple[str, ...] = ("low", "medium", "high", "very_high")

#: Annualized realized volatility (std * sqrt(252)).
VOLATILITY_BUCKET_EDGES: tuple[float, ...] = (0.10, 0.20, 0.35)
VOLATILITY_BUCKET_LABELS: tuple[str, ...] = ("low", "medium", "high", "very_high")

#: Maximum peak-to-trough drawdown magnitude (positive number, e.g. 0.20 = 20%).
DRAWDOWN_BUCKET_EDGES: tuple[float, ...] = (0.15, 0.30, 0.50)
DRAWDOWN_BUCKET_LABELS: tuple[str, ...] = ("shallow", "moderate", "deep", "severe")


def _require_return_series(values: Sequence[float], *, label: str) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1 or array.shape[0] < 2:
        raise ValueError(f"{label} requires at least two observations")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains non-finite values")
    return array


def _bucket(value: float, *, edges: Sequence[float], labels: Sequence[str]) -> str:
    if len(labels) != len(edges) + 1:
        raise ValueError("bucket labels must have exactly one more entry than edges")
    for edge, label in zip(edges, labels[:-1], strict=True):
        if value < edge:
            return label
    return labels[-1]


def _pearson_correlation(left: np.ndarray, right: np.ndarray) -> float:
    """Pearson correlation, matching the convention used across the kernel:
    mean-centred, clipped into ``[-1, 1]``, undefined for a zero-variance series.
    """
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    left_norm = math.sqrt(float(np.dot(left_centered, left_centered)))
    right_norm = math.sqrt(float(np.dot(right_centered, right_centered)))
    if left_norm <= 1e-15 or right_norm <= 1e-15:
        raise ValueError("correlation is undefined for a zero-variance return series")
    correlation = float(np.dot(left_centered, right_centered)) / (left_norm * right_norm)
    return max(-1.0, min(1.0, correlation))


def _activity_rate(returns: np.ndarray) -> float:
    signs = np.sign(returns)
    flips = signs[1:] != signs[:-1]
    return float(np.mean(flips)) if flips.size else 0.0


def _annualized_volatility(returns: np.ndarray, *, annualization_periods: int) -> float:
    return float(np.std(returns, ddof=1) * math.sqrt(annualization_periods))


def _max_drawdown_magnitude(returns: np.ndarray) -> float:
    wealth = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(wealth)
    drawdown = wealth / peak - 1.0
    return float(abs(drawdown.min()))


def behavioral_descriptors(
    returns: Sequence[float],
    *,
    benchmark_returns: Sequence[float],
    annualization_periods: int = ANNUALIZATION_PERIODS,
) -> dict[str, DescriptorValue]:
    """Compute bucketed behavioural MAP-Elites descriptors for one return stream.

    ``returns`` and ``benchmark_returns`` must be the same length and paired
    bar-for-bar (index alignment is the caller's responsibility -- this
    function only ever sees plain sequences of floats, deliberately, so it
    cannot itself read anything beyond what its caller decided to hand it).

    Every value returned is a discrete string label so the archive gets real
    MAP-Elites cells (finitely many, declared in advance) rather than
    continuous coordinates that would give every candidate its own cell.
    """
    returns_array = _require_return_series(returns, label="returns")
    benchmark_array = _require_return_series(benchmark_returns, label="benchmark_returns")
    if returns_array.shape[0] != benchmark_array.shape[0]:
        raise ValueError("returns and benchmark_returns must have the same length")
    if annualization_periods < 1:
        raise ValueError("annualization_periods must be a positive integer")

    correlation = _pearson_correlation(returns_array, benchmark_array)
    activity_rate = _activity_rate(returns_array)
    volatility = _annualized_volatility(returns_array, annualization_periods=annualization_periods)
    drawdown = _max_drawdown_magnitude(returns_array)

    return {
        "benchmark_correlation_bucket": _bucket(
            correlation, edges=CORRELATION_BUCKET_EDGES, labels=CORRELATION_BUCKET_LABELS
        ),
        "activity_bucket": _bucket(
            activity_rate, edges=ACTIVITY_BUCKET_EDGES, labels=ACTIVITY_BUCKET_LABELS
        ),
        "volatility_bucket": _bucket(
            volatility, edges=VOLATILITY_BUCKET_EDGES, labels=VOLATILITY_BUCKET_LABELS
        ),
        "drawdown_bucket": _bucket(
            drawdown, edges=DRAWDOWN_BUCKET_EDGES, labels=DRAWDOWN_BUCKET_LABELS
        ),
    }
