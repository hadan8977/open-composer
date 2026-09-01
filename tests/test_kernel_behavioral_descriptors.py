"""P2a: behavioural MAP-Elites descriptors (plan section 6.1).

The pre-existing QD archive keys cells on ``mechanism_family`` alone, a
single categorical dimension that degenerates MAP-Elites into "best per
mechanism". These tests check the three new behavioural dimensions
(correlation-to-benchmark, activity/turnover proxy, volatility) plus
drawdown, and that their bucket edges are fixed constants rather than
anything fit to the data passed in.
"""

from __future__ import annotations

import numpy as np
import pytest

from open_composer.research.kernel.behavioral_descriptors import (
    ACTIVITY_BUCKET_LABELS,
    CORRELATION_BUCKET_LABELS,
    DRAWDOWN_BUCKET_LABELS,
    VOLATILITY_BUCKET_LABELS,
    behavioral_descriptors,
)


def _series(seed: int, *, n: int = 500, drift: float = 0.0004, vol: float = 0.01) -> list[float]:
    return np.random.default_rng(seed).normal(drift, vol, n).tolist()


def test_descriptor_keys_and_types() -> None:
    descriptors = behavioral_descriptors(_series(1), benchmark_returns=_series(2))
    assert set(descriptors) == {
        "benchmark_correlation_bucket",
        "activity_bucket",
        "volatility_bucket",
        "drawdown_bucket",
    }
    for value in descriptors.values():
        assert isinstance(value, str)
    assert descriptors["benchmark_correlation_bucket"] in CORRELATION_BUCKET_LABELS
    assert descriptors["activity_bucket"] in ACTIVITY_BUCKET_LABELS
    assert descriptors["volatility_bucket"] in VOLATILITY_BUCKET_LABELS
    assert descriptors["drawdown_bucket"] in DRAWDOWN_BUCKET_LABELS


def test_identical_series_is_strong_positive_correlation() -> None:
    returns = _series(3)
    descriptors = behavioral_descriptors(returns, benchmark_returns=returns)
    assert descriptors["benchmark_correlation_bucket"] == "strong_positive"


def test_negated_series_is_strong_negative_correlation() -> None:
    returns = _series(4)
    descriptors = behavioral_descriptors(returns, benchmark_returns=[-value for value in returns])
    assert descriptors["benchmark_correlation_bucket"] == "strong_negative"


def test_low_volatility_series_buckets_low() -> None:
    quiet = np.random.default_rng(5).normal(0.0002, 0.001, 500).tolist()
    descriptors = behavioral_descriptors(quiet, benchmark_returns=_series(6))
    assert descriptors["volatility_bucket"] == "low"


def test_high_volatility_series_buckets_very_high() -> None:
    wild = np.random.default_rng(7).normal(0.0, 0.05, 500).tolist()
    descriptors = behavioral_descriptors(wild, benchmark_returns=_series(8))
    assert descriptors["volatility_bucket"] == "very_high"


def test_alternating_sign_series_has_very_high_activity() -> None:
    alternating = [0.01 if i % 2 == 0 else -0.01 for i in range(200)]
    descriptors = behavioral_descriptors(alternating, benchmark_returns=_series(9, n=200))
    assert descriptors["activity_bucket"] == "very_high"


def test_all_positive_series_has_low_activity() -> None:
    low_activity = [0.001 + 0.00001 * (i % 5) for i in range(300)]
    descriptors = behavioral_descriptors(low_activity, benchmark_returns=_series(10, n=300))
    assert descriptors["activity_bucket"] == "low"


def test_deep_crash_series_buckets_severe_drawdown() -> None:
    crash = [-0.05] * 20 + [0.0005] * 200
    descriptors = behavioral_descriptors(crash, benchmark_returns=_series(20, n=220))
    assert descriptors["drawdown_bucket"] == "severe"


def test_low_volatility_series_has_shallow_drawdown() -> None:
    quiet = np.random.default_rng(21).normal(0.0003, 0.001, 500).tolist()
    descriptors = behavioral_descriptors(quiet, benchmark_returns=_series(22))
    assert descriptors["drawdown_bucket"] == "shallow"


def test_mismatched_lengths_are_rejected() -> None:
    with pytest.raises(ValueError):
        behavioral_descriptors(_series(11, n=100), benchmark_returns=_series(12, n=50))


def test_non_finite_values_are_rejected() -> None:
    returns = _series(13)
    returns[0] = float("nan")
    with pytest.raises(ValueError):
        behavioral_descriptors(returns, benchmark_returns=_series(14))


def test_too_short_series_is_rejected() -> None:
    with pytest.raises(ValueError):
        behavioral_descriptors([0.01], benchmark_returns=[0.01])


def test_zero_variance_series_correlation_is_undefined() -> None:
    with pytest.raises(ValueError):
        behavioral_descriptors([0.001] * 200, benchmark_returns=_series(15, n=200))


def test_descriptors_are_a_pure_function_of_their_inputs() -> None:
    """Same inputs, computed twice, must be byte-identical -- bucket edges are
    fixed constants declared in this module, never fit to a particular call's
    data."""
    returns = _series(16)
    benchmark = _series(17)
    first = behavioral_descriptors(returns, benchmark_returns=benchmark)
    second = behavioral_descriptors(returns, benchmark_returns=benchmark)
    assert first == second
