"""Step 12 Group B recent-regime gate evaluation.

docs/plan-step-12-groupb-recent-regime-high-hit-rate-2026-09-09.zh.md
section 1. Synthetic-data unit tests for
``open_composer.research.regime.gates`` -- ``evaluate_regime_candidate``'s
window slicing and gate arithmetic, ``dsr_trial_count_for_family``'s ledger
scan, and ``append_ledger``'s dedup rule -- plus one integration check that
the real, committed ``recent-regime-high-hit-rate-gates.json`` contract
loads and matches this module's key set (mirrors
``tests/test_kernel_gate_contract.py``'s equivalent check for the kernel
contract). No real market data and no shared ledger mutation: ledger-reading
tests use a ``tmp_path`` ledger file, and the gate-arithmetic tests use a
directly constructed ``PreregisteredGates`` object with a test-only family
name so they never depend on -- or write to -- the real, shared
``reports/research/ledger/experiments.jsonl``.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.gate_contract import PreregisteredGates
from open_composer.research.regime import gates as regime_gates

TEST_FAMILY = "groupb_test_synthetic_only"


def _permissive_gate_values(**overrides: float) -> dict[str, float]:
    values = {
        "hit_rate_weekly_minimum": 0.0,
        "hit_rate_daily_or_intraday_minimum": 0.0,
        "cagr_recent_net_minimum": -1.0,
        "max_drawdown_recent_minimum": -1.0,
        "sharpe_excess_bil_recent_minimum": -10.0,
        "profit_factor_minimum": 0.0,
        "positive_quarter_fraction_minimum": 0.0,
        "dsr_probability_minimum": 0.0,
        "stress_cost_recent_cagr_minimum": -1.0,
        "ml_placebo_rank_ic_abs_maximum": 1.0,
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
    index = pd.bdate_range(start, end, tz="UTC")
    rng = np.random.default_rng(seed)
    values = rng.normal(loc=mean, scale=std, size=len(index))
    return pd.Series(values, index=index, name="return")


def _full_history_fixture() -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns covering 2021-06-01..2025-03-31: enough rows before 2024 for
    the disclosure window and the 2022 replay, and >21 rows on/after
    2024-01-02 for DSR's HAC-lag minimum-length requirement.
    """
    full_returns = _synthetic_returns("2021-06-01", "2025-03-31", mean=0.0012, std=0.008, seed=1)
    full_stress_returns = full_returns - 0.00015
    bil_returns = pd.Series(
        np.random.default_rng(2).normal(loc=0.00012, scale=0.0003, size=len(full_returns)),
        index=full_returns.index,
    )
    return full_returns, full_stress_returns, bil_returns


def _holding_period_returns(win_fraction: float, count: int = 20) -> list[float]:
    wins = round(count * win_fraction)
    return [0.01] * wins + [-0.02] * (count - wins)


def test_evaluate_regime_candidate_passes_every_gate_under_permissive_thresholds() -> None:
    full_returns, full_stress_returns, bil_returns = _full_history_fixture()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_pass",
        config_hash="hash-pass-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="daily_or_intraday",
        holding_period_net_returns_recent=_holding_period_returns(0.6),
        holding_period_net_returns_disclosure=_holding_period_returns(0.55),
        trade_count_recent=40,
        turnover_annualized_recent=12.0,
        family=TEST_FAMILY,
        gates=_permissive_gates(),
    )
    assert verdict.all_gates_pass
    assert verdict.gates_not_applicable == ("ml_placebo_rank_ic",)
    assert verdict.evaluated_gate_count == len(verdict.gate_results) - 1
    assert verdict.promotion_eligible
    assert verdict.dsr_trial_count >= 2
    assert verdict.metrics["holding_period_count_recent"] == 20
    assert verdict.disclosure["cagr_2018_2023"] is not None
    assert verdict.disclosure["replay_2022_full_year_return"] is not None
    assert "2024Q1" in verdict.disclosure["quarterly_returns_2024_2026"]


def test_evaluate_regime_candidate_fails_only_the_overridden_gate() -> None:
    full_returns, full_stress_returns, bil_returns = _full_history_fixture()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_fail_cagr",
        config_hash="hash-fail-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="weekly",
        holding_period_net_returns_recent=_holding_period_returns(0.6),
        family=TEST_FAMILY,
        gates=_permissive_gates(cagr_recent_net_minimum=999.0),
    )
    assert verdict.gate_results["cagr_recent_net"] is False
    assert not verdict.all_gates_pass
    assert not verdict.promotion_eligible
    other_gates = {k: v for k, v in verdict.gate_results.items() if k != "cagr_recent_net"}
    assert all(other_gates.values())


def test_hit_rate_gate_uses_weekly_key_for_weekly_holding_period() -> None:
    full_returns, full_stress_returns, bil_returns = _full_history_fixture()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_weekly_key",
        config_hash="hash-weekly-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="weekly",
        holding_period_net_returns_recent=_holding_period_returns(0.5),
        family=TEST_FAMILY,
        # Only the weekly threshold is demanding; if the daily key were used
        # by mistake this candidate would still pass (0.0 minimum).
        gates=_permissive_gates(hit_rate_weekly_minimum=0.9),
    )
    assert verdict.gate_results["hit_rate_by_holding_period"] is False


def test_ml_placebo_gate_is_evaluated_only_when_is_ml() -> None:
    full_returns, full_stress_returns, bil_returns = _full_history_fixture()
    non_ml = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_non_ml",
        config_hash="hash-nonml-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="daily_or_intraday",
        holding_period_net_returns_recent=_holding_period_returns(0.6),
        family=TEST_FAMILY,
        gates=_permissive_gates(),
    )
    assert non_ml.gates_not_applicable == ("ml_placebo_rank_ic",)
    assert non_ml.gate_results["ml_placebo_rank_ic"] is True

    ml_fail = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_ml_fail",
        config_hash="hash-ml-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="weekly",
        holding_period_net_returns_recent=_holding_period_returns(0.6),
        family=TEST_FAMILY,
        is_ml=True,
        placebo_rank_ic_abs=0.05,
        gates=_permissive_gates(ml_placebo_rank_ic_abs_maximum=0.02),
    )
    assert ml_fail.gates_not_applicable == ()
    assert ml_fail.gate_results["ml_placebo_rank_ic"] is False
    assert not ml_fail.all_gates_pass

    with pytest.raises(ValueError):
        regime_gates.evaluate_regime_candidate(
            experiment_id="groupb_test_ml_missing_ic",
            config_hash="hash-ml-0002",
            full_returns=full_returns,
            full_stress_returns=full_stress_returns,
            bil_returns=bil_returns,
            holding_period="weekly",
            holding_period_net_returns_recent=_holding_period_returns(0.6),
            family=TEST_FAMILY,
            is_ml=True,
            gates=_permissive_gates(),
        )


def test_reference_only_forces_promotion_ineligible_even_if_all_gates_pass() -> None:
    full_returns, full_stress_returns, bil_returns = _full_history_fixture()
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_reference",
        config_hash="hash-ref-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="weekly",
        holding_period_net_returns_recent=_holding_period_returns(0.6),
        family=TEST_FAMILY,
        reference_only=True,
        gates=_permissive_gates(),
    )
    assert verdict.all_gates_pass
    assert verdict.promotion_eligible is False


def test_disclosure_reports_none_with_reason_when_no_pre_2024_data() -> None:
    full_returns = _synthetic_returns("2024-01-02", "2025-03-31", mean=0.001, std=0.008, seed=3)
    full_stress_returns = full_returns - 0.0001
    bil_returns = pd.Series(
        np.random.default_rng(4).normal(loc=0.0001, scale=0.0003, size=len(full_returns)),
        index=full_returns.index,
    )
    verdict = regime_gates.evaluate_regime_candidate(
        experiment_id="groupb_test_no_disclosure",
        config_hash="hash-nodisc-0001",
        full_returns=full_returns,
        full_stress_returns=full_stress_returns,
        bil_returns=bil_returns,
        holding_period="daily_or_intraday",
        holding_period_net_returns_recent=_holding_period_returns(0.6),
        family=TEST_FAMILY,
        gates=_permissive_gates(),
    )
    assert verdict.disclosure["cagr_2018_2023"] is None
    assert "disclosure_2018_2023_unavailable_reason" in verdict.disclosure


def test_dsr_trial_count_for_family_counts_distinct_hashes_including_current(
    tmp_path,
) -> None:
    ledger_path = tmp_path / "experiments.jsonl"
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps({"family": "fam_a", "config_hash": "h1"}),
                json.dumps({"family": "fam_a", "config_hash": "h2"}),
                json.dumps({"family": "fam_b", "config_hash": "h3"}),
                "",
            ]
        )
    )
    # Same family, new hash -> 2 existing + 1 new = 3.
    assert regime_gates.dsr_trial_count_for_family("fam_a", "h_new", ledger_path=ledger_path) == 3
    # Same family, hash already present -> still 2 (no double count).
    assert regime_gates.dsr_trial_count_for_family("fam_a", "h1", ledger_path=ledger_path) == 2
    # Different family entirely, brand new hash -> minimum clamp of 2.
    assert regime_gates.dsr_trial_count_for_family("fam_c", "h_new", ledger_path=ledger_path) == 2


def test_dsr_trial_count_for_family_with_no_ledger_file(tmp_path) -> None:
    missing_path = tmp_path / "does-not-exist.jsonl"
    assert regime_gates.dsr_trial_count_for_family("fam_a", "h1", ledger_path=missing_path) == 2


def test_append_ledger_deduplicates_on_config_hash_and_family(tmp_path) -> None:
    ledger_path = tmp_path / "experiments.jsonl"
    record = {"family": "fam_a", "config_hash": "h1", "note": "first"}
    assert regime_gates.append_ledger(record, ledger_path=ledger_path) is True
    duplicate = {"family": "fam_a", "config_hash": "h1", "note": "second"}
    assert regime_gates.append_ledger(duplicate, ledger_path=ledger_path) is False
    different_family = {"family": "fam_b", "config_hash": "h1", "note": "third"}
    assert regime_gates.append_ledger(different_family, ledger_path=ledger_path) is True
    lines = [line for line in ledger_path.read_text().splitlines() if line.strip()]
    assert len(lines) == 2


def test_the_repo_contract_loads_and_matches_this_modules_key_set() -> None:
    gates = regime_gates.load_recent_regime_gates()
    assert set(gates.values) == set(regime_gates.RECENT_REGIME_GATE_KEYS)
    assert gates.rationale
    assert len(gates.git_blob_sha1) == 40
    assert len(gates.content_sha256) == 64
    assert gates.as_provenance()["gates_provenance"] == "preregistered"
