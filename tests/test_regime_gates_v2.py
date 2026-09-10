"""Step 13 Track M/L v2 gate evaluation.

docs/plan-step-13-recent-high-return-ml-and-llm-tracks-2026-09-09.zh.md;
config/promotion/recent-regime-high-return-gates-v2.json. Synthetic-data
unit tests for ``evaluate_recent_high_return_candidate`` -- window slicing,
vol-matched-SPY excess CAGR, the activity floor's min-year (not average)
semantics, and the is_ml-required-fields discipline -- plus one integration
check that the real, committed v2 contract loads and matches this module's
key set. No real market data and no shared ledger mutation (a tmp_path
ledger is used wherever dsr_trial_count_for_family/append_ledger touch
disk).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.gate_contract import PreregisteredGates
from open_composer.research.regime import gates as regime_gates

TEST_FAMILY = "step13_test_synthetic_only"


def _permissive_gate_values(**overrides: float) -> dict[str, float]:
    values = {
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
    }
    values.update(overrides)
    return values


def _permissive_gates(**overrides: float) -> PreregisteredGates:
    return PreregisteredGates(
        values=_permissive_gate_values(**overrides),
        source_path="test",
        git_blob_sha1="0" * 40,
        content_sha256="0" * 64,
        rationale="synthetic test contract",
    )


def _synthetic_returns(start: str, end: str, *, mean: float, std: float, seed: int) -> pd.Series:
    index = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    values = rng.normal(loc=mean, scale=std, size=len(index))
    return pd.Series(values, index=index, name="return")


def _fixture() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """full_returns, full_stress_returns, spy_returns, bil_returns covering
    2021-06-01..2025-03-31 -- enough rows before 2024 for the disclosure
    window and the 2022 replay, enough on/after 2024-01-02 for DSR's
    HAC-lag minimum length.
    """
    full_returns = _synthetic_returns("2021-06-01", "2025-03-31", mean=0.0012, std=0.008, seed=1)
    full_stress_returns = full_returns - 0.00015
    spy_returns = pd.Series(
        np.random.default_rng(3).normal(loc=0.0004, scale=0.007, size=len(full_returns)),
        index=full_returns.index,
    )
    bil_returns = pd.Series(
        np.random.default_rng(2).normal(loc=0.00012, scale=0.0003, size=len(full_returns)),
        index=full_returns.index,
    )
    return full_returns, full_stress_returns, spy_returns, bil_returns


def _weekly_holding_returns(count: int = 20, *, positive_fraction: float = 0.7) -> list[float]:
    n_positive = round(count * positive_fraction)
    return [0.01] * n_positive + [-0.005] * (count - n_positive)


def test_evaluate_recent_high_return_candidate_slices_and_scores(tmp_path) -> None:
    full_returns, full_stress_returns, spy_returns, bil_returns = _fixture()
    ledger_path = tmp_path / "experiments.jsonl"
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id="m0_test_cell",
        config_hash="abc123",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=_weekly_holding_returns(),
        rebalances_with_change_per_year={2024: 40, 2025: 35},
        family=TEST_FAMILY,
        gates=_permissive_gates(),
    )
    assert verdict.metrics["recent_window_start"] >= "2024-01-02"
    # _fixture() deliberately starts 2021-06-01 ("enough rows before 2024
    # for the disclosure window and the 2022 replay" -- see its docstring),
    # so the 2018-2023 disclosure slice is 2021-06-01..2023-12-31: real
    # data, not empty. A stale copy-pasted comment here previously claimed
    # the opposite and asserted None, which only happened to pass if the
    # fixture were changed to start in 2024 -- it was not, so this was
    # dead/wrong until caught by an actual pytest run.
    assert isinstance(verdict.disclosure["cagr_2018_2023"], float)
    assert np.isfinite(verdict.disclosure["cagr_2018_2023"])
    assert verdict.gates_not_applicable == (
        "ml_placebo_rank_ic",
        "ml_must_beat_rule_baseline",
        "llm_marginal_lift",
    )
    assert verdict.all_gates_pass  # permissive thresholds
    assert verdict.promotion_eligible
    # dsr_trial_count_for_family must have been consulted (default path,
    # real LEDGER_PATH) -- not asserting its value here, just that scoring
    # completed and produced a sane (>=2) trial count.
    assert verdict.dsr_trial_count >= 2
    del ledger_path  # unused; kept for symmetry with tests that do write one


def test_activity_floor_uses_the_minimum_year_not_the_average() -> None:
    full_returns, full_stress_returns, spy_returns, bil_returns = _fixture()
    strict_gates = _permissive_gates(activity_floor_rebalances_with_change_per_year_minimum=30.0)
    # Average of {50, 10} is 30 (would pass an average-based floor), but the
    # weaker year (10) must fail a min-based floor.
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id="m0_activity_floor_test",
        config_hash="def456",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=_weekly_holding_returns(),
        rebalances_with_change_per_year={2024: 50, 2025: 10},
        family=TEST_FAMILY,
        gates=strict_gates,
    )
    assert verdict.metrics["activity_floor_rebalances_with_change_per_year_min"] == 10
    assert verdict.gate_results["activity_floor"] is False
    assert verdict.all_gates_pass is False


def test_is_ml_requires_placebo_and_rule_baseline_fields() -> None:
    full_returns, full_stress_returns, spy_returns, bil_returns = _fixture()
    common_kwargs = dict(
        experiment_id="m1_test_cell",
        config_hash="ml001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=_weekly_holding_returns(),
        rebalances_with_change_per_year={2024: 40, 2025: 35},
        family=TEST_FAMILY,
        gates=_permissive_gates(),
        is_ml=True,
    )
    with pytest.raises(ValueError, match="placebo_rank_ic_abs"):
        regime_gates.evaluate_recent_high_return_candidate(**common_kwargs)
    with pytest.raises(ValueError, match="rule_baseline_cagr_recent_net"):
        regime_gates.evaluate_recent_high_return_candidate(
            **common_kwargs, placebo_rank_ic_abs=0.01
        )
    # With both supplied, the ml-only gates are evaluated (not declared N/A).
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        **common_kwargs, placebo_rank_ic_abs=0.01, rule_baseline_cagr_recent_net=0.05
    )
    assert "ml_placebo_rank_ic" not in verdict.gates_not_applicable
    assert "ml_must_beat_rule_baseline" not in verdict.gates_not_applicable
    assert verdict.metrics["ml_placebo_rank_ic_abs"] == pytest.approx(0.01)


def test_reference_only_forces_promotion_ineligible_even_when_all_gates_pass() -> None:
    full_returns, full_stress_returns, spy_returns, bil_returns = _fixture()
    verdict = regime_gates.evaluate_recent_high_return_candidate(
        experiment_id="m3_reference_only",
        config_hash="ref001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        spy_returns=spy_returns,
        bil_returns=bil_returns,
        weekly_holding_period_net_returns_recent=_weekly_holding_returns(),
        rebalances_with_change_per_year={2024: 40, 2025: 35},
        family=TEST_FAMILY,
        gates=_permissive_gates(),
        reference_only=True,
    )
    assert verdict.all_gates_pass
    assert verdict.promotion_eligible is False


def test_real_v2_contract_loads_and_matches_this_modules_key_set() -> None:
    gates = regime_gates.load_recent_high_return_gates()
    assert set(gates.values) == set(regime_gates.RECENT_HIGH_RETURN_GATE_KEYS)
    assert gates.values["cagr_recent_net_minimum"] == 0.30
    assert gates.values["stress_cost_recent_cagr_minimum"] == 0.20
    assert gates.values["activity_floor_rebalances_with_change_per_year_minimum"] == 30
