from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from open_composer.expressions import ExpressionError, prepare_factor_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.multiasset_forward_multimodal_r4 import (
    FORMULA_FEATURES,
    RANKABLE_SYMBOLS,
    SPEC_PATHS,
    ExactSimulationResult,
    _benchmark_family_exact,
    _cost_reconciliation,
    _evaluate_benchmark_gates,
    _evaluate_role_gates,
    _formula_placebo_evidence,
    _pbo_returns_from_daily_ledger,
    _publish_directory_exclusive,
    _reconcile_feature_and_model_refits,
    _reconcile_model_prediction_evidence,
    _reconcile_target_ledger_evidence,
    _reserve_evaluation_attempt,
    _validate_r4_runtime_contracts,
    _validate_r4_spec_execution_contract,
    build_candidate_targets_for_segment,
    build_cscv_partitions,
    build_point_in_time_features,
    calibration_metrics,
    canonical_target_bytes,
    canonical_target_hash,
    cross_sectional_percentile_rank,
    deflated_sharpe_ratio,
    formula_features_from_spec,
    joint_formula_placebo,
    month_end_decision_points,
    probability_backtest_overfitting,
    simulate_exact_target_portfolio,
    solve_post_trade_equity_ratio,
    training_rows_for_prediction,
)

VALIDATION_CONTRACT_PATH = (
    Path("reports/research/iterations/mom_multiasset_forward_multimodal_r4")
    / "validation-contract.json"
)
R4_ITERATION_PATH = VALIDATION_CONTRACT_PATH.parent
R4_RUNTIME_CONTRACT_FILES = (
    "benchmark-contract.json",
    "candidate-manifest.json",
    "cost-contract.json",
    "cumulative-trial-contract.json",
    "feature-contract.json",
    "holdout-contract.json",
    "label-contract.json",
    "validation-contract.json",
)


def test_point_in_time_features_ignore_future_mutations() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=340)
    symbols = ("AAA", "BBB", "CCC", "DDD")
    position = np.arange(len(sessions), dtype=float)
    close = pd.DataFrame(
        {
            symbol: 100.0 * np.exp((0.0002 + index * 0.0001) * position)
            for index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    volume = pd.DataFrame(
        {
            symbol: 1_000_000.0 + (index + 1) * 100.0 * position
            for index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    cutoff = sessions[300]
    original = build_point_in_time_features(close, volume, rankable_symbols=symbols)

    changed_close = close.copy()
    changed_volume = volume.copy()
    changed_close.loc[changed_close.index > cutoff] *= 7.0
    changed_volume.loc[changed_volume.index > cutoff] *= 11.0
    changed = build_point_in_time_features(
        changed_close,
        changed_volume,
        rankable_symbols=symbols,
    )

    for name in original.raw:
        pd.testing.assert_series_equal(
            original.raw[name].loc[cutoff], changed.raw[name].loc[cutoff]
        )
        pd.testing.assert_series_equal(
            original.ranked[name].loc[cutoff], changed.ranked[name].loc[cutoff]
        )
    for name in FORMULA_FEATURES:
        pd.testing.assert_series_equal(
            original.formulas[name].loc[cutoff], changed.formulas[name].loc[cutoff]
        )


def test_cross_sectional_rank_breaks_ties_by_symbol() -> None:
    frame = pd.DataFrame({"BBB": [1.0], "AAA": [1.0]}, index=[pd.Timestamp("2026-01-02")])

    ranked = cross_sectional_percentile_rank(frame, rankable_symbols=("BBB", "AAA"))

    assert list(ranked.columns) == ["AAA", "BBB"]
    assert ranked.iloc[0].to_dict() == {"AAA": 0.5, "BBB": 1.0}


def test_joint_formula_placebo_is_deterministic_and_joint() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=3)
    symbols = ["AAA", "BBB", "CCC", "DDD"]
    formulas = {
        name: pd.DataFrame(
            np.arange(12, dtype=float).reshape(3, 4) + index * 100.0,
            index=sessions,
            columns=symbols,
        )
        for index, name in enumerate(FORMULA_FEATURES)
    }

    first = joint_formula_placebo(formulas)
    second = joint_formula_placebo(formulas)

    for name in FORMULA_FEATURES:
        pd.testing.assert_frame_equal(first[name], second[name])
    for session in sessions:
        original_vectors = {
            tuple(formulas[name].at[session, symbol] for name in FORMULA_FEATURES)
            for symbol in symbols
        }
        placebo_vectors = {
            tuple(first[name].at[session, symbol] for name in FORMULA_FEATURES)
            for symbol in symbols
        }
        assert placebo_vectors == original_vectors


def test_formula_values_are_derived_from_strategy_spec_params(repo_root: Path) -> None:
    spec = load_strategy_spec(repo_root / SPEC_PATHS["R4C01"])
    components = {
        component
        for name in FORMULA_FEATURES
        for component in spec.factors[name].params["components"]
    }
    sessions = pd.DatetimeIndex([pd.Timestamp("2026-01-30")])
    ranked = {
        component: pd.DataFrame([[0.25, 0.75]], index=sessions, columns=["AAA", "BBB"])
        for component in components
    }

    original = formula_features_from_spec(ranked, formula_spec=spec)
    changed = spec.model_copy(deep=True)
    changed.factors["llm_momentum_quality"].params["coefficients"][0] = 2.0
    modified = formula_features_from_spec(ranked, formula_spec=changed)

    expected_delta = ranked["mom_126_skip21"]
    pd.testing.assert_frame_equal(
        modified["llm_momentum_quality"] - original["llm_momentum_quality"],
        expected_delta,
    )


def test_generic_expression_engine_fails_closed_for_panel_formula_spec(repo_root: Path) -> None:
    spec = load_strategy_spec(repo_root / SPEC_PATHS["R4C01"])
    sessions = pd.bdate_range("2024-01-02", periods=300)
    frame = pd.DataFrame(
        {
            "timestamp": sessions,
            "open": np.arange(1.0, 301.0),
            "high": np.arange(2.0, 302.0),
            "low": np.arange(0.5, 300.5),
            "close": np.arange(1.0, 301.0),
            "volume": np.arange(1_000.0, 1_300.0),
        }
    )

    with pytest.raises(ExpressionError, match="panel-aware cross-sectional transform"):
        prepare_factor_frame(frame, spec.factors)

    typo_factor = SimpleNamespace(
        source="expression",
        expression="close + 1",
        params={"transform": "weighted_sum_typo"},
    )
    with pytest.raises(ExpressionError, match="unsupported transform"):
        prepare_factor_frame(frame, {"typo_factor": typo_factor})


def test_r4_execution_schedule_is_bound_to_all_strategy_specs(repo_root: Path) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }

    contract = _validate_r4_spec_execution_contract(specs)

    assert contract["rebalance_schedule"] == "calendar_month_end"
    assert specs["R4M01"].model.training.seed == 4101
    assert specs["R4C01"].model.training.seed == 4101
    assert specs["R4P01"].model.training.seed == 4101
    assert all(
        spec.portfolio.cross_sectional_execution_profile == "monthly_equal_weight_bil_reserve"
        for spec in specs.values()
    )

    mutations = {
        "position_weight_enforcement": "continuous",
        "rebalance_schedule": "every_bar",
        "weighting": "engine_default",
        "reserve_symbol": "QQQ",
        "reserve_exempt_from_max_symbol_weight": False,
    }
    raw = specs["R4D01"].model_dump(mode="python")
    for field, value in mutations.items():
        changed = json.loads(json.dumps(raw, default=str))
        changed["portfolio"][field] = value
        with pytest.raises(ValueError, match=field):
            StrategySpec.model_validate(changed)

        omitted = json.loads(json.dumps(raw, default=str))
        omitted["portfolio"].pop(field)
        with pytest.raises(ValueError, match=field):
            StrategySpec.model_validate(omitted)

    seed_drift = dict(specs)
    seed_drift["R4C01"] = specs["R4C01"].model_copy(deep=True)
    seed_drift["R4P01"] = specs["R4P01"].model_copy(deep=True)
    seed_drift["R4C01"].model.training.seed = 4103
    seed_drift["R4P01"].model.training.seed = 4103
    with pytest.raises(ValueError, match="may differ only by feature columns"):
        _validate_r4_spec_execution_contract(seed_drift)

    cost_drift = dict(specs)
    cost_drift["R4D01"] = specs["R4D01"].model_copy(deep=True)
    cost_drift["R4D01"].costs.commission_pct = 0.01
    with pytest.raises(ValueError, match="commission"):
        _validate_r4_spec_execution_contract(cost_drift)


def test_formula_placebo_evidence_rejects_nonjoint_mutation() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=2)
    symbols = sorted(RANKABLE_SYMBOLS)
    formulas = {
        name: pd.DataFrame(
            np.arange(len(sessions) * len(symbols), dtype=float).reshape(
                len(sessions), len(symbols)
            )
            + formula_index * 100.0,
            index=sessions,
            columns=symbols,
        )
        for formula_index, name in enumerate(FORMULA_FEATURES)
    }
    placebo = joint_formula_placebo(formulas)
    rows = []
    for session in sessions:
        for symbol in symbols:
            rows.append(
                {
                    "decision_session": session.date().isoformat(),
                    "symbol": symbol,
                    **{name: formulas[name].at[session, symbol] for name in FORMULA_FEATURES},
                    **{
                        f"placebo_{name}": placebo[name].at[session, symbol]
                        for name in FORMULA_FEATURES
                    },
                }
            )
    dataset = pd.DataFrame(rows)
    decision_sessions = {session.date().isoformat() for session in sessions}

    valid = _formula_placebo_evidence(dataset, decision_sessions=decision_sessions)
    corrupted = dataset.copy()
    corrupted.loc[0, f"placebo_{FORMULA_FEATURES[0]}"] += 1.0
    invalid = _formula_placebo_evidence(corrupted, decision_sessions=decision_sessions)

    assert valid["pass"] is True
    assert valid["divergent_decision_count"] == len(sessions)
    assert invalid["joint_permutation_pass"] is False
    assert invalid["pass"] is False


def test_month_end_decisions_execute_on_immediate_next_session() -> None:
    sessions = pd.bdate_range("2026-01-20", "2026-03-05")

    points = month_end_decision_points(sessions)

    positions = {session: index for index, session in enumerate(sessions)}
    assert len(points) == 2
    assert all(
        positions[point["execution_session"]] == positions[point["decision_session"]] + 1
        for point in points
    )


def test_exact_self_financing_solver_handles_buy_and_sell_asymmetry() -> None:
    entry_ratio, entry_notional, entry_error = solve_post_trade_equity_ratio(
        np.asarray([0.0]),
        np.asarray([1.0]),
        cost_bps=10.0,
    )
    exit_ratio, exit_notional, exit_error = solve_post_trade_equity_ratio(
        np.asarray([1.0]),
        np.asarray([0.0]),
        cost_bps=10.0,
    )

    assert entry_ratio == pytest.approx(1.0 / 1.001)
    assert entry_notional == pytest.approx(entry_ratio)
    assert exit_ratio == pytest.approx(0.999)
    assert exit_notional == pytest.approx(1.0)
    assert entry_error <= 1e-14
    assert exit_error <= 1e-14


def test_exact_simulator_reconciles_full_l1_entry_and_liquidation() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=5)
    marks = pd.DataFrame({"BIL": [100.0] * len(sessions)}, index=sessions)
    targets = pd.DataFrame({"BIL": [1.0]}, index=pd.DatetimeIndex([sessions[0]]))

    result = simulate_exact_target_portfolio(marks, targets, cost_bps=10.0)

    expected_equity = (1.0 / 1.001) * 0.999
    assert result.metrics["total_return_pct"] == pytest.approx((expected_equity - 1.0) * 100.0)
    assert result.metrics["total_full_L1_executed_notional"] == pytest.approx(1.0 / 1.001 + 1.0)
    assert result.metrics["terminal_liquidation_count"] == 1
    assert result.metrics["maximum_cost_reconciliation_error"] <= 1e-14
    assert all(event["cost_reconciliation_error"] <= 1e-14 for event in result.events)


def test_cscv_builds_all_70_directional_partitions() -> None:
    sessions = pd.bdate_range("2021-01-04", periods=1005)

    blocks, partitions = build_cscv_partitions(sessions)

    assert len(blocks) == 8
    assert [block["observation_count"] for block in blocks] == [126] * 5 + [125] * 3
    assert len(partitions) == math.comb(8, 4) == 70
    assert any(tuple(partition) == (0, 1, 2, 3) for partition in partitions)
    assert any(tuple(partition) == (4, 5, 6, 7) for partition in partitions)


def test_pbo_partition_count_is_driven_by_requested_contract_shape() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=180)
    phase = np.linspace(0.0, 20.0, len(sessions))
    returns = pd.DataFrame(
        {
            candidate: 0.0001 * index + 0.005 * np.sin(phase + index)
            for index, candidate in enumerate(("A", "B", "C"), start=1)
        },
        index=sessions,
    )

    result = probability_backtest_overfitting(
        returns,
        candidate_ids=["A", "B", "C"],
        block_count=6,
        in_sample_block_count=3,
    )

    assert result["block_count"] == 6
    assert result["in_sample_block_count"] == 3
    assert result["partition_count"] == math.comb(6, 3) == 20


def test_frozen_pbo_uses_1001_open_to_open_rows(repo_root: Path) -> None:
    sessions = pd.Index([f"interval-{index:04d}" for index in range(1001)])
    blocks, partitions = build_cscv_partitions(sessions)
    contract = json.loads((repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8"))["pbo"]

    assert contract["expected_return_observation_count"] == 1001
    assert [block["observation_count"] for block in blocks] == contract[
        "expected_block_observation_counts"
    ]
    assert len(partitions) == contract["expected_partition_count"] == 70


def test_pbo_uses_only_declared_candidates_and_rejects_undefined_sharpe() -> None:
    sessions = pd.bdate_range("2021-01-04", periods=160)
    phase = np.linspace(0.0, 16.0, len(sessions))
    candidates = ["A", "B", "C", "D", "E", "F"]
    returns = pd.DataFrame(
        {
            candidate: 0.0001 * (index + 1)
            + 0.004 * np.sin(phase + index * 0.7)
            + 0.001 * np.cos(phase * (index + 1) / 3.0)
            for index, candidate in enumerate(candidates)
        },
        index=sessions,
    )
    returns["CONTROL"] = 0.1

    result = probability_backtest_overfitting(returns, candidate_ids=candidates)

    assert result["partition_count"] == 70
    assert result["valid_partition_count"] == 70
    assert result["candidate_ids"] == candidates
    assert all(row["selected_candidate_id"] in candidates for row in result["partitions"])

    returns["A"] = 0.001
    with pytest.raises(ValueError, match="zero-variance"):
        probability_backtest_overfitting(returns, candidate_ids=candidates)


def test_dsr_uses_governance_stress_trial_count_and_unrounded_returns() -> None:
    values = pd.Series(
        0.0008 + 0.01 * np.sin(np.linspace(0.0, 50.0, 1005)),
        dtype=float,
    )

    result = deflated_sharpe_ratio(values, trial_count=100000)

    assert result["trial_count"] == 100000
    assert result["session_count"] == 1005
    assert result["estimator_id"] == "bailey_lopez_de_prado_expected_max_normal_v1"
    assert 0.0 < result["probability"] < 1.0


def test_runtime_contracts_bind_dsr_pbo_costs_and_forward_requirements(
    repo_root: Path,
) -> None:
    contracts = _validate_r4_runtime_contracts(repo_root / R4_ITERATION_PATH)

    assert contracts["trial_count_lower_bound"] == 8015
    assert contracts["trial_count"] == 100000
    assert contracts["dsr_sensitivity_trial_counts"] == [8015, 10000, 50000, 100000]
    assert contracts["pbo_config"] == {
        "block_count": 8,
        "in_sample_block_count": 4,
        "expected_partition_count": 70,
        "minimum_valid_partition_count": 70,
    }
    assert contracts["cost_views"]["primary_10bps"] == 10.0
    assert contracts["forward_requirements"]["minimum_contiguous_bound_sessions"] == 20
    assert contracts["forward_requirements"]["minimum_unique_matched_paper_fills"] == 30


@pytest.mark.parametrize(
    ("filename", "mutate", "match"),
    [
        (
            "cumulative-trial-contract.json",
            lambda payload: payload.update({"dsr_trial_count": 99999}),
            "cumulative_trial.dsr_trial_count",
        ),
        (
            "validation-contract.json",
            lambda payload: payload["dsr"].update({"annualization_sessions": 365}),
            "validation.dsr.annualization_sessions",
        ),
        (
            "validation-contract.json",
            lambda payload: payload["role_gates"]["R4M02"].update({"probability_clip": 0.01}),
            "validation.role_gates.R4M02.probability_clip",
        ),
        (
            "cost-contract.json",
            lambda payload: payload["strategy_spec_costs"].update({"commission_pct": 1.0}),
            "cost.strategy_spec_costs",
        ),
        (
            "benchmark-contract.json",
            lambda payload: payload["promotion_gates"].update({"minimum_delta": -1.0}),
            "benchmark.promotion_gates",
        ),
        (
            "validation-contract.json",
            lambda payload: payload["pbo"].update({"expected_partition_count": 69}),
            "validation.pbo.expected_partition_count",
        ),
        (
            "holdout-contract.json",
            lambda payload: payload["matched_tca"].update({"minimum_unique_fills": 29}),
            "holdout.matched_tca.minimum_unique_fills",
        ),
    ],
)
def test_runtime_contracts_reject_cross_contract_drift(
    repo_root: Path,
    tmp_path: Path,
    filename: str,
    mutate,
    match: str,
) -> None:
    source = repo_root / R4_ITERATION_PATH
    for contract_filename in R4_RUNTIME_CONTRACT_FILES:
        (tmp_path / contract_filename).write_bytes((source / contract_filename).read_bytes())
    path = tmp_path / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        _validate_r4_runtime_contracts(tmp_path)


def test_training_rows_enforce_label_terminal_embargo() -> None:
    dataset = pd.DataFrame(
        {
            "decision_position": [100, 150, 200],
            "decision_session": ["2020-01-31", "2020-04-30", "2020-07-31"],
            "label_end_position": [121, 171, 221],
            "symbol": ["AAA", "AAA", "AAA"],
            "feature": [0.1, 0.2, 0.3],
            "label": [0.01, 0.02, 0.03],
        }
    )

    selected = training_rows_for_prediction(
        dataset,
        decision_position=210,
        train_start_session="2018-02-01",
        feature_names=("feature",),
        label_name="label",
    )

    assert selected["decision_position"].tolist() == [100, 150]
    assert (selected["label_end_position"] <= 210 - 21).all()


def test_calibration_uses_training_base_probability_and_fails_constant_predictions() -> None:
    rng = np.random.default_rng(90210)
    logits = np.linspace(-2.5, 2.5, 5000)
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    labels = rng.binomial(1, probabilities).astype(float)
    base = np.full_like(probabilities, labels[:2500].mean())

    calibrated = calibration_metrics(labels, probabilities, base)

    assert calibrated["model_brier_score"] < calibrated["training_base_probability_brier_score"]
    assert calibrated["calibration_slope"] == pytest.approx(1.0, abs=0.1)
    assert calibrated["joint_gate_pass"] is True

    constant = calibration_metrics(labels, np.full_like(probabilities, 0.5), base)
    assert constant["joint_gate_pass"] is False
    assert constant["calibration_failure_reason"] == "constant_probabilities"

    underpowered = calibration_metrics(
        labels[:100],
        probabilities[:100],
        base[:100],
        minimum_observation_count=143,
        minimum_class_count=20,
    )
    assert underpowered["joint_gate_pass"] is False
    assert underpowered["calibration_failure_reason"] == "insufficient_observations"


def test_invalid_m02_and_p01_controls_cannot_pass_role_gates(repo_root: Path) -> None:
    fold_ids = ["F1", "F2", "F3", "F4"]

    def candidate(sharpe: float) -> dict[str, object]:
        return {
            "folds": {
                fold_id: {"primary_10bps": {"annualized_sharpe": sharpe}} for fold_id in fold_ids
            },
            "transfer_holdout": {"primary_10bps": {"annualized_sharpe": sharpe}},
            "unexpected_model_fallback_count": 0,
        }

    candidates = {
        "R4D01": candidate(0.5),
        "R4D02": candidate(0.6),
        "R4M01": candidate(1.0),
        "R4M02": candidate(1.1),
        "R4L01": candidate(1.2),
        "R4C01": candidate(2.0),
        "R4F01": candidate(1.0),
        "R4P01": candidate(0.4),
    }
    candidates["R4P01"]["unexpected_model_fallback_count"] = 1
    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    aggregate_parts: list[pd.DataFrame] = []
    for index, fold_id in enumerate(fold_ids):
        sessions = pd.bdate_range(f"202{index + 1}-01-04", periods=2)
        m01 = pd.DataFrame({"AAA": [1.0, 1.0], "BIL": [0.0, 0.0]}, index=sessions)
        segment_targets[fold_id] = {"R4M01": m01, "R4M02": m01.copy()}
        aggregate_parts.append(m01)
    m01_aggregate = pd.concat(aggregate_parts)
    bil = pd.DataFrame(
        {"AAA": np.zeros(len(m01_aggregate)), "BIL": np.ones(len(m01_aggregate))},
        index=m01_aggregate.index,
    )
    aggregate_targets = {
        "R4D01": bil,
        "R4D02": bil.copy(),
        "R4M01": m01_aggregate,
        "R4M02": m01_aggregate.copy(),
        "R4L01": m01_aggregate.copy(),
        "R4C01": m01_aggregate.copy(),
        "R4F01": m01_aggregate.copy(),
        "R4P01": bil.copy(),
    }
    formula_evidence = {
        "joint_permutation_pass": True,
        "formula_feature_divergence_pass": True,
        "formula_composite_nonconstant_pass": True,
    }
    validation_contract = json.loads(
        (repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8")
    )

    gates = _evaluate_role_gates(
        candidates,
        calibration={
            "joint_passing_fold_count": 4,
            "required_joint_passing_fold_count": 3,
            "pass": True,
        },
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_evidence,
        validation_contract=validation_contract,
    )

    assert gates["R4M02"]["behavior_gate_pass"] is False
    assert gates["R4M02"]["pass"] is False
    assert gates["R4P01"]["zero_unexpected_model_fallbacks"] is False
    assert gates["R4P01"]["pass"] is False
    assert gates["R4C01"]["performance_gate_pass"] is True
    assert gates["R4C01"]["pass"] is False

    for candidate_id in ("R4M01", "R4L01", "R4C01"):
        validation_contract["role_gates"][candidate_id]["minimum_winning_folds"] = 5
    stricter = _evaluate_role_gates(
        candidates,
        calibration={
            "joint_passing_fold_count": 4,
            "required_joint_passing_fold_count": 3,
            "pass": True,
        },
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_evidence,
        validation_contract=validation_contract,
    )
    assert stricter["R4M01"]["pass"] is False
    assert stricter["R4L01"]["pass"] is False
    assert stricter["R4C01"]["performance_gate_pass"] is False


def test_daily_return_ledger_reproduces_common_pbo_matrix_and_rejects_duplicates() -> None:
    folds = [{"fold_id": "F1"}, {"fold_id": "F2"}]
    rows = []
    for candidate_index, candidate_id in enumerate(("A", "B"), start=1):
        for fold_index, fold_id in enumerate(("F1", "F2"), start=1):
            for day in range(2):
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "scope_id": fold_id,
                        "cost_view": "primary_10bps",
                        "interval_start": f"202{fold_index}-01-0{day + 1}",
                        "net_return": candidate_index * 0.001 + day * 0.0001,
                    }
                )
    rows.append(
        {
            "candidate_id": "BENCHMARK:SPY",
            "scope_id": "AGGREGATE",
            "cost_view": "primary_10bps",
            "interval_start": "2021-01-01",
            "net_return": 0.5,
        }
    )

    frame, source_rows = _pbo_returns_from_daily_ledger(
        rows,
        folds=folds,
        candidate_ids=["A", "B"],
    )

    assert list(frame.columns) == ["A", "B"]
    assert list(frame.index) == ["2021-01-01", "2021-01-02", "2022-01-01", "2022-01-02"]
    assert len(source_rows) == 4

    duplicated = [*rows, dict(rows[0])]
    with pytest.raises(ValueError, match="daily-return ledger is incomplete"):
        _pbo_returns_from_daily_ledger(
            duplicated,
            folds=folds,
            candidate_ids=["A", "B"],
        )


def test_model_and_prediction_ledgers_reconcile_exact_values_and_hashes() -> None:
    values = np.asarray([0.25, 0.75], dtype="<f8")
    prediction_sha256 = hashlib.sha256(values.tobytes()).hexdigest()
    record = {
        "model_id": "model-1",
        "segment_id": "F1",
        "candidate_id": "R4M01",
        "decision_session": "2024-01-31",
        "status": "fit_complete",
        "fitted_model_sha256": "a" * 64,
        "prediction_sha256": prediction_sha256,
        "predictions": [
            {"symbol": "AAA", "value": 0.25},
            {"symbol": "BBB", "value": 0.75},
        ],
    }
    rows = [
        {
            "model_id": "model-1",
            "segment_id": "F1",
            "candidate_id": "R4M01",
            "decision_session": "2024-01-31",
            "symbol": symbol,
            "value": value,
            "prediction_sha256": prediction_sha256,
        }
        for symbol, value in (("AAA", 0.25), ("BBB", 0.75))
    ]

    result = _reconcile_model_prediction_evidence([record], rows)

    assert result["pass"] is True
    assert result["model_record_count"] == 1
    assert result["prediction_row_count"] == 2

    tampered = [dict(row) for row in rows]
    tampered[1]["value"] = 0.70
    with pytest.raises(ValueError, match="differs from model evidence"):
        _reconcile_model_prediction_evidence([record], tampered)


def test_target_ledger_reconciliation_rejects_weight_tampering() -> None:
    symbols = sorted(["BIL", *RANKABLE_SYMBOLS])
    weights = {symbol: 0.0 for symbol in symbols}
    weights["BIL"] = 1.0
    session = "2026-01-02"
    frame = pd.DataFrame([weights], index=pd.DatetimeIndex([session]), columns=symbols)
    target_hash = canonical_target_hash(frame)
    row_hash = hashlib.sha256(
        json.dumps(weights, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    rows = [
        {
            "candidate_id": candidate_id,
            "execution_session": session,
            "weights": dict(weights),
            "target_sha256": row_hash,
        }
        for candidate_id in SPEC_PATHS
    ]
    candidates = {
        candidate_id: {"target_count": 1, "target_sha256": target_hash}
        for candidate_id in SPEC_PATHS
    }

    result = _reconcile_target_ledger_evidence(rows, candidates)

    assert result["pass"] is True
    tampered = [dict(row) for row in rows]
    tampered[0] = {**tampered[0], "weights": dict(weights)}
    tampered[0]["weights"]["BIL"] = 0.9
    with pytest.raises(ValueError, match="weights are invalid"):
        _reconcile_target_ledger_evidence(tampered, candidates)


def test_spy_buy_hold_and_market_proxy_are_byte_identical() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=30)
    position = np.arange(len(sessions), dtype=float)
    symbols = sorted(["BIL", *RANKABLE_SYMBOLS])
    opens = pd.DataFrame(
        {
            symbol: 100.0 * np.exp((0.0001 + index * 0.00001) * position)
            for index, symbol in enumerate(symbols)
        },
        index=sessions,
    )

    payload, simulations, targets = _benchmark_family_exact(
        opens,
        monthly_sessions=pd.DatetimeIndex([sessions[0], sessions[20]]),
        start=sessions[0].date().isoformat(),
        end=sessions[-1].date().isoformat(),
        primary_cost_bps=10.0,
        stress_cost_bps=20.0,
    )

    assert payload["identity_checks"]["same_symbol_buy_hold_SPY_equals_market_proxy"] is True
    assert canonical_target_bytes(targets["same_symbol_buy_hold_SPY"]) == canonical_target_bytes(
        targets["market_proxy"]
    )
    for view in ("primary_10bps", "stress_20bps"):
        pd.testing.assert_frame_equal(
            simulations["same_symbol_buy_hold_SPY"][view].daily,
            simulations["market_proxy"][view].daily,
        )


def test_benchmark_relative_gate_requires_every_frozen_comparator(repo_root: Path) -> None:
    contract = json.loads(
        (repo_root / R4_ITERATION_PATH / "benchmark-contract.json").read_text(encoding="utf-8")
    )
    benchmark_payload = {
        "results": {
            benchmark_id: {"cost_views": {"primary_10bps": {"annualized_sharpe": value}}}
            for benchmark_id, value in {
                "market_proxy": 0.9,
                "equal_weight_universe": 0.8,
                "sector_theme_proxy": 0.7,
                "balanced_proxy": 1.0,
            }.items()
        }
    }
    candidates = {
        "PASS": {"aggregate_cost_views": {"primary_10bps": {"annualized_sharpe": 1.0}}},
        "FAIL": {"aggregate_cost_views": {"primary_10bps": {"annualized_sharpe": 0.95}}},
    }

    result = _evaluate_benchmark_gates(
        candidates,
        benchmark_payload=benchmark_payload,
        benchmark_contract=contract,
    )

    assert result["PASS"]["pass"] is True
    assert result["FAIL"]["pass"] is False
    assert result["FAIL"]["deltas"]["balanced_proxy"] == pytest.approx(-0.05)


def test_canonical_target_identity_excludes_candidate_metadata() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=2)
    targets = pd.DataFrame(
        [{"AAA": 1.0 / 3.0, "BIL": 2.0 / 3.0}, {"AAA": 0.0, "BIL": 1.0}],
        index=sessions,
    )

    copied = targets[["BIL", "AAA"]].copy()

    assert canonical_target_bytes(targets) == canonical_target_bytes(copied)
    assert canonical_target_hash(targets) == canonical_target_hash(copied)


def test_synthetic_segment_fits_all_model_roles_without_future_rows(repo_root: Path) -> None:
    decision_dates = pd.date_range("2018-02-28", periods=48, freq="ME")
    rows = []
    for decision_index, decision in enumerate(decision_dates):
        decision_position = 300 + decision_index * 21
        execution = decision + pd.offsets.BDay(1)
        label_end = execution + pd.offsets.BDay(21)
        for symbol_index, symbol in enumerate(RANKABLE_SYMBOLS):
            cross_section = (symbol_index + 1) / len(RANKABLE_SYMBOLS)
            cycle = math.sin(decision_index * 0.31 + symbol_index * 0.47)
            core = {
                "mom_21": cross_section + 0.05 * cycle,
                "mom_63": cross_section + 0.08 * cycle,
                "mom_126_skip21": cross_section + 0.11 * cycle,
                "mom_252_skip21": cross_section + 0.14 * cycle,
                "trend_gap_126": cross_section + 0.03 * cycle,
                "vol_21": 1.0 - cross_section + 0.02 * cycle,
                "drawdown_63": cross_section - 0.04 * cycle,
            }
            formulas = {
                "llm_momentum_quality": core["mom_126_skip21"] - core["vol_21"],
                "llm_volume_confirmed_trend": core["mom_63"] + cross_section,
                "llm_rebound_trap": core["mom_21"] - core["mom_126_skip21"],
                "llm_crowding_risk": core["mom_21"] - core["mom_252_skip21"],
            }
            rows.append(
                {
                    "decision_position": decision_position,
                    "decision_session": decision.date().isoformat(),
                    "execution_position": decision_position + 1,
                    "execution_session": execution.date().isoformat(),
                    "label_end_position": decision_position + 22,
                    "label_end_session": label_end.date().isoformat(),
                    "symbol": symbol,
                    **core,
                    **formulas,
                    **{
                        f"placebo_{name}": value + 0.01 * ((symbol_index + 3) % 5)
                        for name, value in formulas.items()
                    },
                    "raw_mom_126_skip21": core["mom_126_skip21"],
                    "raw_mom_252_skip21": core["mom_252_skip21"],
                    "raw_trend_gap_252": 0.1 + core["trend_gap_126"],
                    "forward_return_21": 0.02 * cycle + 0.003 * cross_section,
                    "path_survival_label": int((decision_index + symbol_index) % 3 != 0),
                    "max_open_path_drawdown": -0.02,
                }
            )
    dataset = pd.DataFrame(rows)
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }
    selected_dates = decision_dates[-4:]
    start = (selected_dates[0] + pd.offsets.BDay(1)).date().isoformat()
    end = (selected_dates[-1] + pd.offsets.BDay(1)).date().isoformat()
    columns = pd.Index(sorted(["BIL", *RANKABLE_SYMBOLS]))

    targets, records, models, _ = build_candidate_targets_for_segment(
        dataset,
        segment_id="SYNTHETIC",
        execution_start=start,
        execution_end=end,
        train_start_session="2018-02-01",
        columns=columns,
        specs=specs,
    )

    assert set(targets) == set(SPEC_PATHS)
    assert all(len(frame) == 4 for frame in targets.values())
    assert all(np.allclose(frame.sum(axis=1), 1.0) for frame in targets.values())
    assert canonical_target_bytes(targets["R4F01"]) == canonical_target_bytes(targets["R4M01"])
    assert len(records) == 8 * 4
    assert len(models) == 4 * 4
    assert all(model["status"] == "fit_complete" for model in models)
    assert all(model["resolved_model_params"]["subsample_freq"] == 1 for model in models)
    assert all(len(model["predictions"]) == len(RANKABLE_SYMBOLS) for model in models)
    assert all(len(model["fitted_model_sha256"]) == 64 for model in models)
    refit = _reconcile_feature_and_model_refits(
        dataset.to_dict(orient="records"),
        models,
        specs,
    )
    assert refit["successful_model_refit_count"] == 16
    assert refit["deterministic_fallback_count"] == 0


def test_cost_reconciliation_rejects_missing_boundary_events() -> None:
    daily = pd.DataFrame(
        [
            {
                "net_factor": 1.0,
                "net_return": 0.0,
                "equity": 1.0,
                "risk_asset_exposure": 0.0,
            }
        ]
    )
    simulation = ExactSimulationResult(
        daily=daily,
        events=[],
        metrics={
            "total_full_L1_executed_notional": 100.0,
            "maximum_cost_reconciliation_error": 0.0,
            "terminal_liquidation_count": 0,
            "nonzero_rebalance_count": 0,
        },
    )
    aggregate = {candidate_id: {"primary_10bps": simulation} for candidate_id in SPEC_PATHS}
    segments = {candidate_id: {"S1": {"primary_10bps": simulation}} for candidate_id in SPEC_PATHS}

    result = _cost_reconciliation(
        aggregate,
        segments,
        [{"segment_id": "S1", "start": "2026-01-02"}],
    )

    assert result["pass"] is False
    assert any("event_ledger_empty" in failure for failure in result["failures"])


def test_result_directory_publication_is_exclusive(tmp_path: Path) -> None:
    stage = tmp_path / ".stage-one"
    stage.mkdir()
    (stage / "evaluation-receipt.json").write_text("first", encoding="utf-8")
    destination = tmp_path / "evaluation-run"

    _publish_directory_exclusive(stage, destination)

    assert (destination / "evaluation-receipt.json").read_text(encoding="utf-8") == "first"
    second = tmp_path / ".stage-two"
    second.mkdir()
    (second / "evaluation-receipt.json").write_text("second", encoding="utf-8")
    with pytest.raises(ValueError, match="destination exists"):
        _publish_directory_exclusive(second, destination)
    assert (destination / "evaluation-receipt.json").read_text(encoding="utf-8") == "first"
    assert second.exists()


def test_evaluation_attempt_is_exclusive_and_permanent(tmp_path: Path) -> None:
    output = tmp_path / R4_ITERATION_PATH
    output.mkdir(parents=True)
    preflight = {
        "operator_lock_anchor_sha256": "a" * 64,
        "preregistration_lock_sha256": "b" * 64,
        "runner_lock_sha256": "c" * 64,
        "data_manifest_sha256": "d" * 64,
    }

    binding = _reserve_evaluation_attempt(tmp_path, preflight)

    assert binding["path"].endswith("evaluation-attempt.json")
    assert len(binding["sha256"]) == 64
    with pytest.raises(ValueError, match="already exists"):
        _reserve_evaluation_attempt(tmp_path, preflight)
