"""``kernel.vol_matched`` must reproduce the ledger's own vol-matched excess.

``regime.gates.evaluate_recent_high_return_candidate`` computes
``cagr_excess_vol_matched_spy`` inline for the gate contract's recent window
only. ``kernel.vol_matched`` exists so a report can quote the same metric over
a different window -- which is only legitimate if it is the *same* formula,
which is what the first test pins down (same streams, same window, exact
equality).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel import vol_matched
from open_composer.research.kernel.gate_contract import PreregisteredGates
from open_composer.research.regime import gates as regime_gates


def _permissive_gates() -> PreregisteredGates:
    return PreregisteredGates(
        values={
            "cagr_recent_net_minimum": -1.0,
            "cagr_excess_vol_matched_spy_minimum": -1.0,
            "hit_rate_weekly_minimum": 0.0,
            "max_drawdown_recent_minimum": -1.0,
            "sharpe_excess_bil_recent_minimum": -10.0,
            "positive_quarter_fraction_minimum": 0.0,
            "dsr_probability_minimum": 0.0,
            "stress_cost_recent_cagr_minimum": -1.0,
            "activity_floor_rebalances_with_change_per_year_minimum": 0.0,
            "ml_placebo_rank_ic_abs_maximum": 1.0,
            "ml_must_beat_rule_baseline_cagr_margin_minimum": -1.0,
            "llm_marginal_lift_cagr_minimum": -1.0,
            "llm_marginal_lift_rank_ic_minimum": -1.0,
        },
        source_path="test",
        git_blob_sha1="0" * 40,
        content_sha256="0" * 64,
        rationale="synthetic test contract",
    )


def _streams() -> tuple[pd.Series, pd.Series, pd.Series]:
    index = pd.bdate_range("2021-06-01", "2025-03-31")
    candidate = pd.Series(
        np.random.default_rng(1).normal(0.0012, 0.008, len(index)), index=index, name="return"
    )
    spy = pd.Series(np.random.default_rng(3).normal(0.0004, 0.007, len(index)), index=index)
    bil = pd.Series(np.random.default_rng(2).normal(0.00012, 0.0003, len(index)), index=index)
    return candidate, spy, bil


def test_matches_the_gate_evaluators_cagr_excess_vol_matched_spy() -> None:
    candidate, spy, bil = _streams()
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id="vol_matched_parity",
        config_hash="vol_matched_parity",
        full_returns=candidate,
        full_stress_returns=candidate - 0.00015,
        spy_returns=spy,
        bil_returns=bil,
        weekly_holding_period_net_returns_recent=[0.01, -0.005, 0.02],
        rebalances_with_change_per_year={2024: 40, 2025: 10},
        family="step13_test_synthetic_only",
        gates=_permissive_gates(),
    )
    recent = candidate.loc[candidate.index >= pd.Timestamp(regime_gates.RECENT_WINDOW_START)]
    assert vol_matched.cagr_excess_vol_matched(recent, spy, bil) == pytest.approx(
        verdict.metrics["cagr_excess_vol_matched_spy"], rel=0, abs=1e-12
    )
    assert vol_matched.vol_match_weight(recent, spy) == pytest.approx(
        verdict.metrics["vol_match_weight_vs_spy"], rel=0, abs=1e-12
    )


def test_blend_has_the_candidates_realized_volatility() -> None:
    candidate, spy, bil = _streams()
    blend = vol_matched.vol_matched_benchmark_returns(candidate, spy, bil)
    # bil's own volatility is not zero, so the blend's vol is only
    # approximately the candidate's -- the metric's definition is the weight,
    # not an exact vol equality, and the two agree to within bil's noise.
    assert blend.std() == pytest.approx(candidate.std(), rel=0.02)


def test_missing_benchmark_rows_raise_rather_than_being_treated_as_zero() -> None:
    candidate, spy, bil = _streams()
    with pytest.raises(ValueError, match="benchmark alignment"):
        vol_matched.cagr_excess_vol_matched(candidate, spy.iloc[5:], bil)
    with pytest.raises(ValueError, match="cash alignment"):
        vol_matched.cagr_excess_vol_matched(candidate, spy, bil.iloc[5:])


def test_non_positive_benchmark_volatility_raises() -> None:
    candidate, _spy, bil = _streams()
    flat = pd.Series(0.0, index=candidate.index)
    with pytest.raises(ValueError, match="non-positive realized volatility"):
        vol_matched.cagr_excess_vol_matched(candidate, flat, bil)
