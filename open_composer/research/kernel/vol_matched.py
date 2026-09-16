"""Volatility-matched benchmark blend and its excess CAGR.

``regime.gates.evaluate_recent_high_return_candidate`` computes the ledger's
``cagr_excess_vol_matched_spy`` metric inline, but only ever for the gate
contract's own recent window (``RECENT_WINDOW_START``.. latest): it slices
that window out of the streams it is handed, by design, so that every gated
candidate is sliced identically. A report that also has to quote the same
metric over a *different* window (H-20260916-03 needs it over its full
out-of-sample span, 2020Q2 onward, next to the 2024-onward gate number) had
no entry point.

This module is that entry point, and it is deliberately not a second
formula: ``tests/test_kernel_vol_matched.py`` asserts
``cagr_excess_vol_matched`` reproduces
``evaluate_recent_high_return_candidate``'s own
``cagr_excess_vol_matched_spy`` bit-for-bit on the same window, so the two
can never drift apart silently. Gate thresholds and gate definitions are not
touched here -- this computes one disclosure metric, it decides nothing.
"""

from __future__ import annotations

import math

import pandas as pd

from open_composer.research.kernel.mechanism_eval import annualized_cagr


def vol_matched_benchmark_returns(
    candidate: pd.Series, benchmark: pd.Series, cash: pd.Series
) -> pd.Series:
    """The ``w * benchmark + (1 - w) * cash`` blend whose realized daily
    volatility over ``candidate.index`` matches the candidate's own, with
    ``w = std(candidate) / std(benchmark)`` (leverage above 1.0 is allowed --
    the point of the metric is to ask what the passive comparator would have
    returned if it had been run at the candidate's risk level, which for a
    low-vol benchmark means scaling it up).

    ``benchmark``/``cash`` are reindexed onto the candidate's dates and must
    cover all of them: a missing benchmark day would otherwise be silently
    treated as a zero-return day and flatter the candidate.
    """
    aligned_benchmark = benchmark.reindex(candidate.index)
    if aligned_benchmark.isna().any():
        raise ValueError("benchmark alignment produced missing rows")
    aligned_cash = cash.reindex(candidate.index)
    if aligned_cash.isna().any():
        raise ValueError("cash alignment produced missing rows")
    benchmark_vol = float(aligned_benchmark.std())
    if not math.isfinite(benchmark_vol) or benchmark_vol <= 0.0:
        raise ValueError("benchmark has non-positive realized volatility in this window")
    weight = float(candidate.std()) / benchmark_vol
    return weight * aligned_benchmark + (1.0 - weight) * aligned_cash


def vol_match_weight(candidate: pd.Series, benchmark: pd.Series) -> float:
    """``std(candidate) / std(benchmark)`` over the candidate's own dates."""
    aligned_benchmark = benchmark.reindex(candidate.index)
    if aligned_benchmark.isna().any():
        raise ValueError("benchmark alignment produced missing rows")
    benchmark_vol = float(aligned_benchmark.std())
    if not math.isfinite(benchmark_vol) or benchmark_vol <= 0.0:
        raise ValueError("benchmark has non-positive realized volatility in this window")
    return float(candidate.std()) / benchmark_vol


def cagr_excess_vol_matched(candidate: pd.Series, benchmark: pd.Series, cash: pd.Series) -> float:
    """``annualized_cagr(candidate) - annualized_cagr(vol_matched_blend)`` --
    the ledger's ``cagr_excess_vol_matched_spy`` identity, over whatever
    window ``candidate`` spans.
    """
    blend = vol_matched_benchmark_returns(candidate, benchmark, cash)
    return annualized_cagr(candidate) - annualized_cagr(blend)
