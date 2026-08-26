from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from statistics import NormalDist

import numpy as np


@dataclass(frozen=True)
class CampaignRecomputedStatistics:
    candidate_sharpe_excess_bil: dict[str, float]
    candidate_dsr_probabilities: dict[str, float]
    dsr_probability: float
    pbo_probability: float
    spa_p_value: float


def recompute_campaign_statistics(
    *,
    candidate_ids: list[str] | tuple[str, ...],
    candidate_returns: dict[str, list[float]],
    benchmark_returns: list[float],
    effective_trial_count: int,
    dsr_hac_lag: int,
    pbo_block_count: int,
    pbo_in_sample_block_count: int,
    spa_block_length: int,
    spa_resample_count: int,
    spa_seed: int,
) -> CampaignRecomputedStatistics:
    """Recompute campaign family statistics from one common return matrix."""
    candidates = list(candidate_ids)
    if len(candidates) < 2 or len(candidates) != len(set(candidates)):
        raise ValueError("campaign statistics require at least two unique candidates")
    if set(candidate_returns) != set(candidates):
        raise ValueError("campaign statistics candidate return inventory mismatch")
    benchmark = np.asarray(benchmark_returns, dtype=float)
    if benchmark.ndim != 1 or not np.isfinite(benchmark).all():
        raise ValueError("campaign benchmark returns must be a finite vector")
    if len(benchmark) <= max(dsr_hac_lag, pbo_block_count, spa_block_length):
        raise ValueError("campaign return matrix has too few rows for frozen statistics")

    columns: list[np.ndarray] = []
    for candidate_id in candidates:
        values = np.asarray(candidate_returns[candidate_id], dtype=float)
        if values.shape != benchmark.shape or not np.isfinite(values).all():
            raise ValueError(f"campaign candidate returns are incomplete: {candidate_id}")
        columns.append(values - benchmark)
    excess = np.column_stack(columns)

    sharpes = {
        candidate_id: annualized_sharpe(excess[:, index])
        for index, candidate_id in enumerate(candidates)
    }
    dsr = {
        candidate_id: deflated_sharpe_probability(
            excess[:, index],
            trial_count=effective_trial_count,
            hac_lag=dsr_hac_lag,
        )
        for index, candidate_id in enumerate(candidates)
    }
    return CampaignRecomputedStatistics(
        candidate_sharpe_excess_bil=sharpes,
        candidate_dsr_probabilities=dsr,
        dsr_probability=min(dsr.values()),
        pbo_probability=cscv_probability_backtest_overfitting(
            excess,
            block_count=pbo_block_count,
            in_sample_block_count=pbo_in_sample_block_count,
        ),
        spa_p_value=studentized_spa_p_value(
            excess,
            block_length=spa_block_length,
            resample_count=spa_resample_count,
            seed=spa_seed,
        ),
    )


def annualized_sharpe(values: np.ndarray) -> float:
    returns = np.asarray(values, dtype=float)
    if returns.ndim != 1 or len(returns) < 2 or not np.isfinite(returns).all():
        raise ValueError("Sharpe requires at least two finite returns")
    standard_deviation = float(np.std(returns, ddof=1))
    if standard_deviation <= 0.0:
        raise ValueError("Sharpe is undefined for zero-variance returns")
    return float(np.mean(returns) / standard_deviation * math.sqrt(252.0))


def deflated_sharpe_probability(
    values: np.ndarray,
    *,
    trial_count: int,
    hac_lag: int,
) -> float:
    returns = np.asarray(values, dtype=float)
    if trial_count < 2 or hac_lag < 1 or len(returns) <= max(hac_lag, 3):
        raise ValueError("DSR dimensions are invalid")
    if returns.ndim != 1 or not np.isfinite(returns).all():
        raise ValueError("DSR returns must be a finite vector")
    standard_deviation = float(np.std(returns, ddof=1))
    if standard_deviation <= 0.0:
        raise ValueError("DSR is undefined for zero-variance returns")

    session_count = len(returns)
    mean = float(np.mean(returns))
    centered = returns - mean
    moment2 = float(np.mean(centered**2))
    if moment2 <= 0.0:
        raise ValueError("DSR second central moment is nonpositive")
    raw_skew = float(np.mean(centered**3) / moment2**1.5)
    skew = math.sqrt(session_count * (session_count - 1.0)) / (session_count - 2.0) * raw_skew
    raw_excess = float(np.mean(centered**4) / moment2**2 - 3.0)
    excess = (
        (session_count - 1.0)
        / ((session_count - 2.0) * (session_count - 3.0))
        * ((session_count + 1.0) * raw_excess + 6.0)
    )
    pearson_kurtosis = excess + 3.0

    weighted_autocorrelation_sum = 0.0
    for lag in range(1, hac_lag + 1):
        autocovariance = float(np.dot(centered[lag:], centered[:-lag]) / session_count)
        autocorrelation = autocovariance / moment2
        weighted_autocorrelation_sum += (1.0 - lag / (hac_lag + 1.0)) * autocorrelation
    inflation = max(1.0, 1.0 + 2.0 * weighted_autocorrelation_sum)
    effective_session_count = min(float(session_count), session_count / inflation)
    if not math.isfinite(effective_session_count) or effective_session_count <= 1.0:
        raise ValueError("DSR HAC effective session count is invalid")

    observed_daily = mean / standard_deviation
    denominator = 1.0 - skew * observed_daily + (pearson_kurtosis - 1.0) / 4.0 * observed_daily**2
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("DSR denominator is nonfinite or nonpositive")
    normal = NormalDist()
    gamma = 0.5772156649015329
    expected_max_standard = (1.0 - gamma) * normal.inv_cdf(
        1.0 - 1.0 / trial_count
    ) + gamma * normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))

    def probability(count: float) -> float:
        statistic = (observed_daily * math.sqrt(count - 1.0) - expected_max_standard) / math.sqrt(
            denominator
        )
        return normal.cdf(statistic)

    return min(probability(float(session_count)), probability(effective_session_count))


def cscv_probability_backtest_overfitting(
    excess_returns: np.ndarray,
    *,
    block_count: int,
    in_sample_block_count: int,
) -> float:
    values = np.asarray(excess_returns, dtype=float)
    if values.ndim != 2 or values.shape[1] < 2 or not np.isfinite(values).all():
        raise ValueError("PBO requires a finite matrix with at least two candidates")
    if block_count < 2 or not 1 <= in_sample_block_count < block_count:
        raise ValueError("PBO block dimensions are invalid")
    blocks = [
        np.asarray(block, dtype=int)
        for block in np.array_split(np.arange(len(values)), block_count)
    ]
    if any(len(block) == 0 for block in blocks):
        raise ValueError("PBO blocks must be nonempty")

    all_blocks = set(range(block_count))
    contribution_sum = 0.0
    partition_count = 0
    for in_blocks in combinations(range(block_count), in_sample_block_count):
        out_blocks = tuple(sorted(all_blocks - set(in_blocks)))
        in_positions = np.sort(np.concatenate([blocks[index] for index in in_blocks]))
        out_positions = np.sort(np.concatenate([blocks[index] for index in out_blocks]))
        in_sharpes = np.asarray(
            [annualized_sharpe(values[in_positions, index]) for index in range(values.shape[1])]
        )
        out_sharpes = np.asarray(
            [annualized_sharpe(values[out_positions, index]) for index in range(values.shape[1])]
        )
        winners = np.flatnonzero(np.isclose(in_sharpes, np.max(in_sharpes), rtol=0.0, atol=1e-12))
        ranks = _ascending_midranks(out_sharpes)
        contributions = []
        for winner in winners:
            omega = (ranks[int(winner)] - 0.5) / values.shape[1]
            contributions.append(1.0 if omega < 0.5 else 0.0 if omega > 0.5 else 0.5)
        contribution_sum += math.fsum(contributions) / len(contributions)
        partition_count += 1
    expected = math.comb(block_count, in_sample_block_count)
    if partition_count != expected:
        raise ValueError("PBO partition set is incomplete")
    return contribution_sum / partition_count


def studentized_spa_p_value(
    excess_returns: np.ndarray,
    *,
    block_length: int,
    resample_count: int,
    seed: int,
) -> float:
    """Deterministic studentized moving-block SPA test against zero excess return."""
    values = np.asarray(excess_returns, dtype=float)
    if values.ndim != 2 or values.shape[1] < 1 or not np.isfinite(values).all():
        raise ValueError("SPA requires a finite candidate return matrix")
    observation_count = values.shape[0]
    if not 1 <= block_length <= observation_count or resample_count < 1 or seed < 0:
        raise ValueError("SPA bootstrap dimensions are invalid")
    standard_deviations = np.std(values, axis=0, ddof=1)
    if np.any(standard_deviations <= 0.0):
        raise ValueError("SPA is undefined for zero-variance candidate returns")
    means = np.mean(values, axis=0)
    observed = float(np.max(np.sqrt(observation_count) * means / standard_deviations))

    # Positive sample means are recentered to the boundary of the composite null;
    # negative means retain their drift, matching the conservative SPA null.
    null_values = values - np.maximum(means, 0.0)
    indexes = _moving_block_indexes(
        observation_count,
        block_length=block_length,
        resample_count=resample_count,
        seed=seed,
    )
    exceedances = 0
    for row in indexes:
        bootstrap_means = np.mean(null_values[row], axis=0)
        statistic = float(
            np.max(np.sqrt(observation_count) * bootstrap_means / standard_deviations)
        )
        exceedances += int(statistic >= observed)
    return (exceedances + 1.0) / (resample_count + 1.0)


def _moving_block_indexes(
    observation_count: int,
    *,
    block_length: int,
    resample_count: int,
    seed: int,
) -> np.ndarray:
    blocks_per_resample = math.ceil(observation_count / block_length)
    generator = np.random.Generator(np.random.PCG64(seed))
    starts = generator.integers(
        0,
        observation_count - block_length + 1,
        size=(resample_count, blocks_per_resample),
        dtype=np.int64,
    )
    offsets = np.arange(block_length, dtype=np.int64)
    indexes = (starts[:, :, None] + offsets[None, None, :]).reshape(resample_count, -1)
    return np.ascontiguousarray(indexes[:, :observation_count], dtype=np.int64)


def _ascending_midranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=float)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and math.isclose(
            float(values[order[end]]),
            float(values[order[cursor]]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            end += 1
        ranks[order[cursor:end]] = (cursor + 1 + end) / 2.0
        cursor = end
    return ranks


__all__ = [
    "CampaignRecomputedStatistics",
    "annualized_sharpe",
    "cscv_probability_backtest_overfitting",
    "deflated_sharpe_probability",
    "recompute_campaign_statistics",
    "studentized_spa_p_value",
]
