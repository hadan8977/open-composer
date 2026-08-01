from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from open_composer.expressions import ExpressionError, prepare_factor_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research import multiasset_forward_multimodal_r5 as r5_module
from open_composer.research.multiasset_forward_multimodal_r5 import (
    FORMULA_FEATURES,
    R5_LOCK_ITERATION_FILENAMES,
    R5_RUNTIME_CONTRACT_FILENAMES,
    RANKABLE_SYMBOLS,
    SPEC_PATHS,
    TOP_N,
    ExactSimulationResult,
    _benchmark_family_exact,
    _cost_reconciliation,
    _derive_evaluation_statuses,
    _evaluate_benchmark_gates,
    _evaluate_role_gates,
    _evaluation_anchor_payload,
    _formula_placebo_evidence,
    _llm_bootstrap_role_gate_evidence,
    _load_json,
    _load_strategy_spec_stable,
    _model_provenance_payload,
    _non_circular_moving_block_indices,
    _pbo_returns_from_daily_ledger,
    _publish_directory_exclusive,
    _r5_runner_relative_paths,
    _read_regular_file_bytes,
    _rebuild_staged_model_and_target_ledgers,
    _reconcile_candidate_manifest_and_specs,
    _reconcile_feature_and_model_refits,
    _reconcile_model_prediction_evidence,
    _reconcile_model_target_coverage,
    _reconcile_staged_benchmark_gates,
    _reconcile_staged_model_provenance,
    _reconcile_staged_role_gate_evidence,
    _reconcile_staged_trial_ledger,
    _reconcile_target_ledger_evidence,
    _render_markdown,
    _replay_staged_feature_ledger,
    _replay_staged_performance_ledgers,
    _reserve_evaluation_attempt,
    _seal_evidence_directory,
    _simulation_accounting_checks,
    _staged_calibration_from_ledgers,
    _staged_target_frames,
    _validate_r5_runtime_contracts,
    _validate_r5_spec_execution_contract,
    _write_json_exclusive_readonly,
    build_candidate_targets_for_segment,
    build_cscv_partitions,
    build_point_in_time_features,
    calibration_metrics,
    canonical_target_bytes,
    canonical_target_hash,
    cross_sectional_percentile_rank,
    defined_annualized_sharpe,
    deflated_sharpe_ratio,
    formula_features_from_spec,
    joint_formula_placebo,
    month_end_decision_points,
    paired_transfer_sharpe_bootstrap,
    probability_backtest_overfitting,
    simulate_exact_target_portfolio,
    solve_post_trade_equity_ratio,
    training_rows_for_prediction,
)

VALIDATION_CONTRACT_PATH = (
    Path("reports/research/iterations/mom_multiasset_forward_multimodal_r5")
    / "validation-contract.json"
)
R5_ITERATION_PATH = VALIDATION_CONTRACT_PATH.parent
R5_RUNTIME_CONTRACT_FILES = (
    "benchmark-contract.json",
    "candidate-manifest.json",
    "cost-contract.json",
    "cumulative-trial-contract.json",
    "feature-contract.json",
    "holdout-contract.json",
    "label-contract.json",
    "validation-contract.json",
)


def _llm_bootstrap_contract(repo_root: Path) -> dict[str, object]:
    return json.loads((repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8"))[
        "llm_contribution_bootstrap"
    ]


def _copy_r5_harness_workspace(repo_root: Path, destination: Path) -> dict[str, StrategySpec]:
    source_specs = {
        candidate_id: _load_strategy_spec_stable(repo_root / relative)
        for candidate_id, relative in SPEC_PATHS.items()
    }
    relatives = [
        *(relative.as_posix() for relative in SPEC_PATHS.values()),
        *r5_module._r5_harness_relative_paths(source_specs),
    ]
    for relative in relatives:
        source = repo_root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return {
        candidate_id: _load_strategy_spec_stable(destination / relative)
        for candidate_id, relative in SPEC_PATHS.items()
    }


def _synthetic_llm_bootstrap_ledgers() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    sessions = pd.bdate_range("2025-01-02", periods=385)
    positions = np.arange(384, dtype=float)
    common = 0.0002 + 0.003 * np.sin(positions / 9.0) + 0.001 * np.cos(positions / 17.0)
    candidate_returns = {
        "R5C01": common + 0.0010,
        "R5M01": common,
        "R5P01": common - 0.0002,
    }
    entry_ratio = 1.0 / 1.001
    terminal_ratio = 0.9992
    daily_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    for candidate_id, returns in candidate_returns.items():
        factors = 1.0 + returns
        factors[0] *= entry_ratio
        factors[-1] *= terminal_ratio
        equity = 1.0
        for index, factor in enumerate(factors):
            cost_factor = 1.0
            if index == 0:
                cost_factor *= entry_ratio
            if index == len(factors) - 1:
                cost_factor *= terminal_ratio
            equity *= float(factor)
            daily_rows.append(
                {
                    "schema_version": 1,
                    "iter_id": "mom_multiasset_forward_multimodal_r5",
                    "candidate_id": candidate_id,
                    "scope_id": "TRANSFER",
                    "cost_view": "primary_10bps",
                    "interval_start": sessions[index].date().isoformat(),
                    "interval_end": sessions[index + 1].date().isoformat(),
                    "gross_factor_after_rebalance": float(factor / cost_factor),
                    "net_factor": float(factor),
                    "net_return": float(factor - 1.0),
                    "cost_factor": cost_factor,
                    "equity": equity,
                }
            )
        for terminal, session, reason, ratio in (
            (False, sessions[0], "independent_boundary_entry", entry_ratio),
            (True, sessions[-1], "terminal_liquidation", terminal_ratio),
        ):
            cost_fraction = 1.0 - ratio
            pretrade_weights = (
                {"BIL": 0.0, "SPY": 0.0} if not terminal else {"BIL": 0.3, "SPY": 0.5}
            )
            target_weights = {"BIL": 0.4, "SPY": 0.6} if not terminal else {"BIL": 0.0, "SPY": 0.0}
            event_rows.append(
                {
                    "schema_version": 1,
                    "iter_id": "mom_multiasset_forward_multimodal_r5",
                    "candidate_id": candidate_id,
                    "scope_id": "TRANSFER",
                    "cost_view": "primary_10bps",
                    "session": session.date().isoformat(),
                    "reason": reason,
                    "terminal": terminal,
                    "pretrade_equity": 1.0 if not terminal else equity / terminal_ratio,
                    "pretrade_asset_weights": pretrade_weights,
                    "pretrade_cash_weight": 1.0 if not terminal else 0.2,
                    "target_asset_weights": target_weights,
                    "posttrade_cash_weight": 0.0 if not terminal else 1.0,
                    "posttrade_equity_ratio": ratio,
                    "cost_bps": 10.0,
                    "full_L1_executed_notional_fraction": cost_fraction / 0.001,
                    "cost_fraction_of_pretrade_equity": cost_fraction,
                    "cost_reconciliation_error": 0.0,
                }
            )
    return daily_rows, event_rows


def test_point_in_time_features_ignore_future_mutations(repo_root: Path) -> None:
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
    formula_spec = load_strategy_spec(repo_root / SPEC_PATHS["R5C01"])
    original = build_point_in_time_features(
        close,
        volume,
        rankable_symbols=symbols,
        formula_spec=formula_spec,
    )

    changed_close = close.copy()
    changed_volume = volume.copy()
    changed_close.loc[changed_close.index > cutoff] *= 7.0
    changed_volume.loc[changed_volume.index > cutoff] *= 11.0
    changed = build_point_in_time_features(
        changed_close,
        changed_volume,
        rankable_symbols=symbols,
        formula_spec=formula_spec,
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


def test_formula_values_require_the_exact_bound_strategy_spec(repo_root: Path) -> None:
    spec = load_strategy_spec(repo_root / SPEC_PATHS["R5C01"])
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
    assert set(original) == set(FORMULA_FEATURES)
    changed = spec.model_copy(deep=True)
    changed.factors["llm_momentum_quality"].params["coefficients"][0] = 2.0
    with pytest.raises(ValueError, match="source mapping contract mismatch"):
        formula_features_from_spec(ranked, formula_spec=changed)
    with pytest.raises(ValueError, match="explicitly bound StrategySpec"):
        formula_features_from_spec(ranked, formula_spec=None)


def test_generic_expression_engine_fails_closed_for_panel_formula_spec(repo_root: Path) -> None:
    spec = load_strategy_spec(repo_root / SPEC_PATHS["R5C01"])
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


def test_r5_execution_schedule_is_bound_to_all_strategy_specs(repo_root: Path) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }

    contract = _validate_r5_spec_execution_contract(specs)

    assert contract["rebalance_schedule"] == "calendar_month_end"
    assert contract["paired_return_ranker_seed"] == 4101
    assert specs["R5M01"].model.training.seed == 4101
    assert specs["R5C01"].model.training.seed == 4101
    assert specs["R5P01"].model.training.seed == 4101
    assert all(
        spec.portfolio.cross_sectional_execution_profile == "monthly_equal_weight_bil_reserve"
        for spec in specs.values()
    )

    coordinated_formula_drift = {
        candidate_id: spec.model_copy(deep=True) for candidate_id, spec in specs.items()
    }
    for candidate_id in ("R5L01", "R5C01", "R5P01"):
        coordinated_formula_drift[candidate_id].factors["llm_momentum_quality"].params[
            "coefficients"
        ][0] = 99.0
    with pytest.raises(ValueError, match="differs from locked R2 source mapping"):
        _validate_r5_spec_execution_contract(coordinated_formula_drift)

    expression_drift = dict(specs)
    expression_drift["R5C01"] = specs["R5C01"].model_copy(deep=True)
    expression_drift["R5C01"].factors["llm_momentum_quality"].expression = "close + 1"
    with pytest.raises(ValueError, match="formula expression contract mismatch"):
        _validate_r5_spec_execution_contract(expression_drift)

    core_expression_drift = dict(specs)
    core_expression_drift["R5M01"] = specs["R5M01"].model_copy(deep=True)
    core_expression_drift["R5M01"].factors["mom_21"].expression = "close + 1"
    with pytest.raises(ValueError, match="factor expression contract mismatch for R5M01:mom_21"):
        _validate_r5_spec_execution_contract(core_expression_drift)

    mutations = {
        "position_weight_enforcement": "continuous",
        "rebalance_schedule": "every_bar",
        "weighting": "engine_default",
        "reserve_symbol": "QQQ",
        "reserve_exempt_from_max_symbol_weight": False,
    }
    raw = specs["R5D01"].model_dump(mode="python")
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
    seed_drift["R5C01"] = specs["R5C01"].model_copy(deep=True)
    seed_drift["R5C01"].model.training.seed = 4103
    with pytest.raises(ValueError, match="paired return-ranker seed mismatch"):
        _validate_r5_spec_execution_contract(seed_drift)

    cross_label_drift = dict(specs)
    cross_label_drift["R5M01"] = specs["R5M01"].model_copy(deep=True)
    cross_label_drift["R5F01"] = specs["R5F01"].model_copy(deep=True)
    cross_label_drift["R5M01"].model.features = ["path_survival_label"]
    cross_label_drift["R5F01"].model.features = ["path_survival_label"]
    with pytest.raises(ValueError, match="immutable model contract mismatch for R5M01"):
        _validate_r5_spec_execution_contract(cross_label_drift)

    future_return_drift = dict(specs)
    future_return_drift["R5M02"] = specs["R5M02"].model_copy(deep=True)
    future_return_drift["R5M02"].model.features = ["forward_return_21"]
    with pytest.raises(ValueError, match="immutable model contract mismatch for R5M02"):
        _validate_r5_spec_execution_contract(future_return_drift)

    fallback_drift = dict(specs)
    fallback_drift["R5F01"] = specs["R5F01"].model_copy(deep=True)
    fallback_drift["R5F01"].model.hyperparameters["num_leaves"] += 1
    with pytest.raises(ValueError, match="exact R5M01 model contract"):
        _validate_r5_spec_execution_contract(fallback_drift)

    cost_drift = dict(specs)
    cost_drift["R5D01"] = specs["R5D01"].model_copy(deep=True)
    cost_drift["R5D01"].costs.commission_pct = 0.01
    with pytest.raises(ValueError, match="commission"):
        _validate_r5_spec_execution_contract(cost_drift)


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


def test_exact_simulator_rejects_missing_terminal_and_inexact_boundary_sessions() -> None:
    sessions = pd.DatetimeIndex(["2026-01-02", "2026-01-05", "2026-01-06"])
    marks = pd.DataFrame(
        {"BIL": [100.0, 100.0, 100.0], "SPY": [100.0, 101.0, 102.0]},
        index=sessions,
    )
    missing_session_target = pd.DataFrame(
        [{"BIL": 0.0, "SPY": 1.0}],
        index=pd.DatetimeIndex(["2026-01-04"]),
    )
    terminal_target = pd.DataFrame(
        [{"BIL": 0.0, "SPY": 1.0}],
        index=pd.DatetimeIndex([sessions[-1]]),
    )

    with pytest.raises(ValueError, match="executable nonterminal mark session"):
        simulate_exact_target_portfolio(marks, missing_session_target, cost_bps=10.0)
    with pytest.raises(ValueError, match="executable nonterminal mark session"):
        simulate_exact_target_portfolio(marks, terminal_target, cost_bps=10.0)
    with pytest.raises(ValueError, match="exact mark sessions"):
        simulate_exact_target_portfolio(
            marks,
            pd.DataFrame(
                [{"BIL": 1.0, "SPY": 0.0}],
                index=pd.DatetimeIndex([sessions[0]]),
            ),
            cost_bps=10.0,
            start="2026-01-03",
            end=sessions[-1],
        )


def test_exact_simulator_records_start_and_end_risk_exposure() -> None:
    sessions = pd.DatetimeIndex(["2026-01-02", "2026-01-05"])
    marks = pd.DataFrame(
        {"BIL": [100.0, 100.0], "SPY": [100.0, 200.0]},
        index=sessions,
    )
    targets = pd.DataFrame(
        [{"BIL": 0.5, "SPY": 0.5}],
        index=pd.DatetimeIndex([sessions[0]]),
    )

    result = simulate_exact_target_portfolio(marks, targets, cost_bps=0.0)

    row = result.daily.iloc[0]
    assert row["start_risk_asset_exposure"] == pytest.approx(0.5)
    assert row["end_risk_asset_exposure"] == pytest.approx(2.0 / 3.0)
    assert result.metrics["average_start_risk_asset_exposure"] == pytest.approx(0.5)
    assert result.metrics["average_end_risk_asset_exposure"] == pytest.approx(2.0 / 3.0)


def test_complete_session_contract_binds_csv_manifest_and_exchange_calendar() -> None:
    complete = pd.DatetimeIndex(["2026-01-02", "2026-01-05", "2026-01-06"])
    declared = [session.date().isoformat() for session in complete]
    assert (
        r5_module._validate_complete_session_contract(
            complete,
            declared,
            symbol="SPY",
        )
        == declared
    )

    with pytest.raises(r5_module.AlpacaDataError, match="differs from parsed CSV"):
        r5_module._validate_complete_session_contract(
            complete,
            declared[:-1],
            symbol="SPY",
        )
    omitted = pd.DatetimeIndex(["2026-01-02", "2026-01-06"])
    with pytest.raises(r5_module.AlpacaDataError, match="omits an exchange session"):
        r5_module._validate_complete_session_contract(
            omitted,
            [session.date().isoformat() for session in omitted],
            symbol="SPY",
        )


def test_zero_cost_events_reconcile_without_weakening_notional_checks() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=5)
    marks = pd.DataFrame({"BIL": [100.0] * len(sessions)}, index=sessions)
    targets = pd.DataFrame({"BIL": [1.0]}, index=pd.DatetimeIndex([sessions[0]]))
    gross = simulate_exact_target_portfolio(marks, targets, cost_bps=0.0)
    primary = simulate_exact_target_portfolio(marks, targets, cost_bps=10.0)

    checks = _simulation_accounting_checks(
        gross,
        expected_start=sessions[0].date().isoformat(),
        tolerance=1e-12,
        expected_event_reason_codes={
            "scheduled_rebalance",
            "independent_boundary_entry",
            "terminal_liquidation",
        },
        expected_cost_bps=0.0,
    )

    assert checks["failures"] == []
    assert all(event["posttrade_equity_ratio"] == 1.0 for event in gross.events)
    assert all(event["cost_fraction_of_pretrade_equity"] == 0.0 for event in gross.events)
    aggregate = {
        candidate_id: {"gross_0bps": gross, "primary_10bps": primary} for candidate_id in SPEC_PATHS
    }
    segments = {candidate_id: {"S1": {"primary_10bps": primary}} for candidate_id in SPEC_PATHS}
    reconciliation = _cost_reconciliation(
        aggregate,
        segments,
        [{"segment_id": "S1", "start": sessions[0].date().isoformat()}],
        expected_cost_bps_by_view={"gross_0bps": 0.0, "primary_10bps": 10.0},
    )
    assert reconciliation["pass"] is True


def test_accounting_rejects_zero_notional_nonfinite_and_reordered_internal_events() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=6)
    marks = pd.DataFrame(
        {
            "BIL": np.linspace(100.0, 100.1, len(sessions)),
            "SPY": np.linspace(100.0, 103.0, len(sessions)),
        },
        index=sessions,
    )
    targets = pd.DataFrame(
        [
            {"BIL": 0.0, "SPY": 1.0},
            {"BIL": 1.0, "SPY": 0.0},
        ],
        index=pd.DatetimeIndex([sessions[0], sessions[2]]),
    )
    simulation = simulate_exact_target_portfolio(marks, targets, cost_bps=10.0)
    checks = _simulation_accounting_checks(
        simulation,
        expected_start=sessions[0].date().isoformat(),
        tolerance=1e-12,
        expected_event_reason_codes={
            "scheduled_rebalance",
            "independent_boundary_entry",
            "terminal_liquidation",
        },
        expected_cost_bps=10.0,
    )
    assert checks["failures"] == []
    assert len(simulation.events) == 3

    reordered_events = json.loads(json.dumps(simulation.events))
    reordered_events[0], reordered_events[1] = reordered_events[1], reordered_events[0]
    reordered = ExactSimulationResult(
        daily=simulation.daily.copy(),
        events=reordered_events,
        metrics=dict(simulation.metrics),
    )
    reordered_checks = _simulation_accounting_checks(
        reordered,
        expected_start=sessions[0].date().isoformat(),
        tolerance=1e-12,
        expected_event_reason_codes={
            "scheduled_rebalance",
            "independent_boundary_entry",
            "terminal_liquidation",
        },
        expected_cost_bps=10.0,
    )
    assert "cost_events_not_strictly_chronological" in reordered_checks["failures"]

    nonfinite_events = json.loads(json.dumps(simulation.events))
    nonfinite_events[1]["pretrade_asset_weights"]["BIL"] = "NaN"
    nonfinite = ExactSimulationResult(
        daily=simulation.daily.copy(),
        events=nonfinite_events,
        metrics=dict(simulation.metrics),
    )
    nonfinite_checks = _simulation_accounting_checks(
        nonfinite,
        expected_start=sessions[0].date().isoformat(),
        tolerance=1e-12,
        expected_event_reason_codes={
            "scheduled_rebalance",
            "independent_boundary_entry",
            "terminal_liquidation",
        },
        expected_cost_bps=10.0,
    )
    assert "event_weight_cash_accounting_invalid" in nonfinite_checks["failures"]

    wrong_equity_events = json.loads(json.dumps(simulation.events))
    wrong_equity_events[0]["pretrade_equity"] = 999_999.0
    wrong_equity = ExactSimulationResult(
        daily=simulation.daily.copy(),
        events=wrong_equity_events,
        metrics=dict(simulation.metrics),
    )
    wrong_equity_checks = _simulation_accounting_checks(
        wrong_equity,
        expected_start=sessions[0].date().isoformat(),
        tolerance=1e-12,
        expected_event_reason_codes={
            "scheduled_rebalance",
            "independent_boundary_entry",
            "terminal_liquidation",
        },
        expected_cost_bps=10.0,
    )
    assert "event_pretrade_equity_chain_mismatch" in wrong_equity_checks["failures"]

    zero_events = json.loads(json.dumps(simulation.events))
    zero_event = json.loads(json.dumps(zero_events[1]))
    zero_event.update(
        {
            "session": sessions[1].date().isoformat(),
            "pretrade_asset_weights": {"BIL": 0.0, "SPY": 1.0},
            "pretrade_cash_weight": 0.0,
            "target_asset_weights": {"BIL": 0.0, "SPY": 1.0},
            "posttrade_cash_weight": 0.0,
            "posttrade_equity_ratio": 1.0,
            "full_L1_executed_notional_fraction": 0.0,
            "cost_fraction_of_pretrade_equity": 0.0,
            "cost_reconciliation_error": 0.0,
        }
    )
    zero_events.insert(1, zero_event)
    zero_metrics = dict(simulation.metrics)
    zero_metrics["nonzero_rebalance_count"] += 1
    zero = ExactSimulationResult(
        daily=simulation.daily.copy(),
        events=zero_events,
        metrics=zero_metrics,
    )
    zero_checks = _simulation_accounting_checks(
        zero,
        expected_start=sessions[0].date().isoformat(),
        tolerance=1e-12,
        expected_event_reason_codes={
            "scheduled_rebalance",
            "independent_boundary_entry",
            "terminal_liquidation",
        },
        expected_cost_bps=10.0,
    )
    assert "event_posttrade_equity_ratio_invalid" in zero_checks["failures"]


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
    assert result["estimator_id"] == (
        "bailey_lopez_de_prado_expected_max_normal_with_bartlett_effective_sessions_v2"
    )
    assert result["hac_lag"] == 21
    assert len(result["hac_autocorrelations"]) == 21
    assert result["promotion_probability"] == min(
        result["iid_probability"], result["hac_probability"]
    )
    assert result["probability"] == result["promotion_probability"]
    assert 0.0 < result["probability"] < 1.0


def test_hac_dsr_penalizes_positive_serial_correlation_relative_to_shuffle() -> None:
    rng = np.random.default_rng(811)
    innovations = rng.normal(0.0002, 0.004, 1001)
    autocorrelated = np.empty_like(innovations)
    autocorrelated[0] = innovations[0]
    for index in range(1, len(autocorrelated)):
        autocorrelated[index] = 0.85 * autocorrelated[index - 1] + innovations[index]
    shuffled = np.random.default_rng(812).permutation(autocorrelated)

    ordered_result = deflated_sharpe_ratio(
        pd.Series(autocorrelated),
        trial_count=100000,
    )
    shuffled_result = deflated_sharpe_ratio(
        pd.Series(shuffled),
        trial_count=100000,
    )

    assert ordered_result["observed_annualized_sharpe"] == pytest.approx(
        shuffled_result["observed_annualized_sharpe"]
    )
    assert ordered_result["hac_inflation_factor"] > shuffled_result["hac_inflation_factor"]
    assert ordered_result["effective_session_count"] < shuffled_result["effective_session_count"]
    assert ordered_result["promotion_probability"] < shuffled_result["promotion_probability"]


def test_hac_dsr_floors_negative_serial_correlation_inflation_at_one() -> None:
    values = pd.Series([0.01 if index % 2 == 0 else -0.009 for index in range(1001)])

    result = deflated_sharpe_ratio(values, trial_count=100000)

    assert result["hac_raw_inflation_factor"] < 1.0
    assert result["hac_inflation_factor"] == 1.0
    assert result["effective_session_count"] == 1001.0
    assert result["hac_probability"] == result["iid_probability"]


def test_hac_dsr_excludes_cross_fold_lag_pairs() -> None:
    values = pd.Series(np.linspace(-0.01, 0.02, 60) + 0.001 * np.sin(np.arange(60)))
    scopes = ["F1"] * 30 + ["F2"] * 30

    bounded = deflated_sharpe_ratio(values, trial_count=100000, scope_ids=scopes)
    unbounded = deflated_sharpe_ratio(values, trial_count=100000)

    assert bounded["scope_count"] == 2
    assert bounded["hac_autocorrelations"][0]["within_scope_pair_count"] == 58
    assert unbounded["hac_autocorrelations"][0]["within_scope_pair_count"] == 59


def test_hac_dsr_rejects_too_few_sessions_for_frozen_lag() -> None:
    with pytest.raises(ValueError, match="more sessions than the HAC lag"):
        deflated_sharpe_ratio(pd.Series(np.linspace(-0.01, 0.01, 21)), trial_count=100000)


def test_non_circular_moving_blocks_are_shared_bounded_and_deterministic() -> None:
    indexes = _non_circular_moving_block_indices(
        384,
        block_length=21,
        resample_count=2000,
        seed=4201,
    )
    repeated = _non_circular_moving_block_indices(
        384,
        block_length=21,
        resample_count=2000,
        seed=4201,
    )

    assert indexes.shape == (2000, 384)
    assert indexes.dtype == np.dtype("<i8")
    assert np.array_equal(indexes, repeated)
    assert indexes.min() >= 0
    assert indexes.max() < 384
    starts = np.ascontiguousarray(indexes[:, ::21], dtype="<i8")
    assert starts[0].tolist() == [
        24,
        32,
        318,
        333,
        192,
        351,
        214,
        67,
        209,
        107,
        170,
        142,
        237,
        4,
        286,
        251,
        158,
        44,
        4,
    ]
    assert hashlib.sha256(starts.tobytes(order="C")).hexdigest() == (
        "578d0fc5c9432cd1e74fae42cf59b2d1ce632deed7bd0091baf5b5c1f790249d"
    )
    for start in range(0, 384, 21):
        block = indexes[:, start : min(start + 21, 384)]
        if block.shape[1] > 1:
            assert np.all(np.diff(block, axis=1) == 1)


def test_paired_transfer_bootstrap_is_deterministic_and_uses_sharpe_differences(
    repo_root: Path,
) -> None:
    daily_rows, event_rows = _synthetic_llm_bootstrap_ledgers()
    contract = _llm_bootstrap_contract(repo_root)

    result = paired_transfer_sharpe_bootstrap(
        daily_rows,
        event_rows,
        contract=contract,
    )
    repeated = paired_transfer_sharpe_bootstrap(
        daily_rows,
        event_rows,
        contract=contract,
    )

    assert result == repeated
    assert result["common_interval_count"] == 384
    assert result["bootstrap_index_matrix_shape"] == [2000, 384]
    assert len(result["bootstrap_index_matrix_sha256"]) == 64
    assert result["valid_resample_count"] == 2000
    assert result["pass"] is True
    for candidate_id in ("R5C01", "R5M01", "R5P01"):
        boundary = result["boundary_costs"][candidate_id]
        assert boundary["entry_restorations_per_resample"] == 1
        assert boundary["terminal_restorations_per_resample"] == 1
    by_candidate = {
        candidate_id: pd.Series(
            [float(row["net_return"]) for row in daily_rows if row["candidate_id"] == candidate_id]
        )
        for candidate_id in ("R5C01", "R5M01", "R5P01")
    }
    for comparator_id in ("R5M01", "R5P01"):
        comparison = result["comparisons"][f"R5C01_minus_{comparator_id}"]
        expected_delta = defined_annualized_sharpe(by_candidate["R5C01"]) - (
            defined_annualized_sharpe(by_candidate[comparator_id])
        )
        spread_sharpe = defined_annualized_sharpe(
            by_candidate["R5C01"] - by_candidate[comparator_id]
        )
        assert comparison["observed_annualized_sharpe_delta"] == pytest.approx(expected_delta)
        assert comparison["observed_annualized_sharpe_delta"] != pytest.approx(spread_sharpe)
        assert comparison["lower_percentile_sorted_zero_based_index"] == 49
        assert comparison["lower_confidence_bound"] > 0.0
        assert comparison["pass"] is True


def test_paired_transfer_bootstrap_rejects_no_incremental_formula_lift(
    repo_root: Path,
) -> None:
    daily_rows, event_rows = _synthetic_llm_bootstrap_ledgers()
    m01_by_interval = {
        (row["interval_start"], row["interval_end"]): row
        for row in daily_rows
        if row["candidate_id"] == "R5M01"
    }
    for row in daily_rows:
        if row["candidate_id"] == "R5C01":
            source = m01_by_interval[(row["interval_start"], row["interval_end"])]
            for field_name in (
                "gross_factor_after_rebalance",
                "net_factor",
                "net_return",
                "cost_factor",
            ):
                row[field_name] = source[field_name]

    result = paired_transfer_sharpe_bootstrap(
        daily_rows,
        event_rows,
        contract=_llm_bootstrap_contract(repo_root),
    )

    comparison = result["comparisons"]["R5C01_minus_R5M01"]
    assert comparison["observed_annualized_sharpe_delta"] == 0.0
    assert comparison["lower_confidence_bound"] == 0.0
    assert comparison["point_estimate_pass"] is False
    assert comparison["lower_confidence_bound_strictly_positive"] is False
    assert comparison["pass"] is False
    assert result["pass"] is False


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("missing_row", "return count"),
        ("duplicate_interval", "duplicated"),
        ("misaligned_interval", "misaligned"),
        ("interval_gap", "intervals are invalid"),
        ("interval_overlap", "not contiguous"),
        ("nat_interval", "intervals are invalid"),
        ("nonfinite_return", "nonfinite or inconsistent"),
        ("missing_terminal", "daily/event cost binding"),
        ("altered_daily_cost_factor", "daily/event cost binding"),
        ("net_factor_cost_gross_mismatch", "daily/event cost binding"),
        ("unmapped_event", "daily/event cost binding"),
        ("duplicate_event", "daily/event cost binding"),
        ("invalid_boundary_cost", "daily/event cost binding"),
        ("noncash_entry", "daily/event cost binding"),
        ("wrong_pretrade_equity", "daily/event cost binding"),
        ("zero_notional_event", "daily/event cost binding"),
        ("nonfinite_event_weight", "daily/event cost binding"),
        ("event_order", "daily/event cost binding"),
        ("zero_variance", "zero-variance"),
    ],
)
def test_paired_transfer_bootstrap_fails_closed_on_invalid_evidence(
    repo_root: Path,
    mutation: str,
    match: str,
) -> None:
    daily_rows, event_rows = _synthetic_llm_bootstrap_ledgers()
    if mutation == "missing_row":
        daily_rows.pop(0)
    elif mutation == "duplicate_interval":
        c01_rows = [row for row in daily_rows if row["candidate_id"] == "R5C01"]
        c01_rows[1]["interval_start"] = c01_rows[0]["interval_start"]
        c01_rows[1]["interval_end"] = c01_rows[0]["interval_end"]
    elif mutation == "misaligned_interval":
        m01_row = next(row for row in daily_rows if row["candidate_id"] == "R5M01")
        m01_row["interval_start"] = "2025-01-01"
    elif mutation == "interval_gap":
        c01_rows = [row for row in daily_rows if row["candidate_id"] == "R5C01"]
        c01_rows[0]["interval_end"] = "2025-01-02T12:00:00"
    elif mutation == "interval_overlap":
        c01_rows = [row for row in daily_rows if row["candidate_id"] == "R5C01"]
        c01_rows[0]["interval_end"] = "2025-01-04"
    elif mutation == "nat_interval":
        c01_rows = [row for row in daily_rows if row["candidate_id"] == "R5C01"]
        c01_rows[-2]["interval_end"] = "NaT"
        c01_rows[-1]["interval_start"] = "NaT"
    elif mutation == "nonfinite_return":
        c01_row = next(row for row in daily_rows if row["candidate_id"] == "R5C01")
        c01_row["net_return"] = math.nan
    elif mutation == "missing_terminal":
        event_rows[:] = [
            row
            for row in event_rows
            if not (row["candidate_id"] == "R5C01" and row["terminal"] is True)
        ]
    elif mutation == "altered_daily_cost_factor":
        c01_row = [row for row in daily_rows if row["candidate_id"] == "R5C01"][10]
        c01_row["cost_factor"] = 0.999
        c01_row["net_factor"] = 0.999 * float(c01_row["gross_factor_after_rebalance"])
        c01_row["net_return"] = float(c01_row["net_factor"]) - 1.0
    elif mutation == "net_factor_cost_gross_mismatch":
        c01_row = [row for row in daily_rows if row["candidate_id"] == "R5C01"][10]
        c01_row["net_factor"] = float(c01_row["net_factor"]) * 0.999
        c01_row["net_return"] = float(c01_row["net_factor"]) - 1.0
    elif mutation == "unmapped_event":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and not row["terminal"]
        )
        c01_entry["session"] = "2025-01-01"
    elif mutation == "duplicate_event":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and not row["terminal"]
        )
        event_rows.append(json.loads(json.dumps(c01_entry)))
    elif mutation == "invalid_boundary_cost":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and row["terminal"] is False
        )
        c01_entry["cost_bps"] = 1.0
    elif mutation == "noncash_entry":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and row["terminal"] is False
        )
        c01_entry["pretrade_asset_weights"]["SPY"] = 0.1
        c01_entry["pretrade_cash_weight"] = 0.9
    elif mutation == "wrong_pretrade_equity":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and row["terminal"] is False
        )
        c01_entry["pretrade_equity"] = 2.0
    elif mutation == "zero_notional_event":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and not row["terminal"]
        )
        zero_event = json.loads(json.dumps(c01_entry))
        zero_event.update(
            {
                "session": [row for row in daily_rows if row["candidate_id"] == "R5C01"][10][
                    "interval_start"
                ],
                "pretrade_asset_weights": {"BIL": 0.4, "SPY": 0.6},
                "pretrade_cash_weight": 0.0,
                "target_asset_weights": {"BIL": 0.4, "SPY": 0.6},
                "posttrade_cash_weight": 0.0,
                "posttrade_equity_ratio": 1.0,
                "full_L1_executed_notional_fraction": 0.0,
                "cost_fraction_of_pretrade_equity": 0.0,
            }
        )
        event_rows.insert(1, zero_event)
    elif mutation == "nonfinite_event_weight":
        c01_entry = next(
            row for row in event_rows if row["candidate_id"] == "R5C01" and not row["terminal"]
        )
        c01_entry["pretrade_asset_weights"]["BIL"] = "NaN"
    elif mutation == "event_order":
        c01_indexes = [
            index for index, row in enumerate(event_rows) if row["candidate_id"] == "R5C01"
        ]
        event_rows[c01_indexes[0]], event_rows[c01_indexes[1]] = (
            event_rows[c01_indexes[1]],
            event_rows[c01_indexes[0]],
        )
    elif mutation == "zero_variance":
        for row in daily_rows:
            if row["candidate_id"] == "R5C01":
                row["net_factor"] = 1.001
                row["net_return"] = 0.001
                row["gross_factor_after_rebalance"] = 1.001 / float(row["cost_factor"])
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValueError, match=match):
        paired_transfer_sharpe_bootstrap(
            daily_rows,
            event_rows,
            contract=_llm_bootstrap_contract(repo_root),
        )


def test_llm_bootstrap_role_gate_derives_comparison_passes(repo_root: Path) -> None:
    daily_rows, event_rows = _synthetic_llm_bootstrap_ledgers()
    contract = _llm_bootstrap_contract(repo_root)
    evidence = paired_transfer_sharpe_bootstrap(
        daily_rows,
        event_rows,
        contract=contract,
    )

    valid = _llm_bootstrap_role_gate_evidence(evidence, contract)
    forged = json.loads(json.dumps(evidence))
    comparison = forged["comparisons"]["R5C01_minus_R5M01"]
    comparison["candidate_observed_annualized_sharpe"] = (
        comparison["comparator_observed_annualized_sharpe"] + 0.01
    )
    comparison["observed_annualized_sharpe_delta"] = 0.01
    comparison["point_estimate_pass"] = True
    comparison["pass"] = True
    forged["pass"] = True
    rejected = _llm_bootstrap_role_gate_evidence(forged, contract)

    assert valid["pass"] is True
    assert rejected["comparison_passes"]["R5C01_minus_R5M01"] is False
    assert rejected["pass"] is False


def test_runtime_contracts_bind_dsr_pbo_costs_and_forward_requirements(
    repo_root: Path,
) -> None:
    contracts = _validate_r5_runtime_contracts(
        repo_root / R5_ITERATION_PATH,
        root=repo_root,
    )

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
    assert contracts["llm_contribution_bootstrap_config"]["rng_seed"] == 4201
    assert contracts["llm_contribution_bootstrap_config"]["resample_count"] == 2000
    assert (
        contracts["llm_contribution_bootstrap_config"]["lower_percentile_sorted_zero_based_index"]
        == 49
    )
    assert contracts["forward_requirements"]["minimum_contiguous_bound_sessions"] == 20
    assert contracts["forward_requirements"]["minimum_unique_matched_paper_fills"] == 30


def test_every_runtime_contract_is_in_the_preregistration_lock_inventory() -> None:
    assert set(R5_RUNTIME_CONTRACT_FILENAMES.values()).issubset(R5_LOCK_ITERATION_FILENAMES)


def test_runner_lock_inventory_is_a_verified_local_dependency_closure(repo_root: Path) -> None:
    inventory = _r5_runner_relative_paths(repo_root)
    inventory_set = set(inventory)
    local_python = {
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "open_composer").rglob("*.py")
    }
    required_runtime_modules = {
        "open_composer/research/multiasset_forward_multimodal_r5.py",
        "open_composer/research/evidence_custody.py",
        "open_composer/research/iteration_dossier.py",
        "open_composer/adapters/data/alpaca_snapshot.py",
        "open_composer/harness/policy.py",
        "open_composer/models/strategy_spec.py",
    }

    assert len(inventory) == len(inventory_set)
    assert required_runtime_modules.issubset(inventory_set)
    assert inventory_set.intersection(local_python) < local_python
    assert "open_composer/dashboard/server.py" not in inventory_set
    assert set(
        r5_module._local_python_dependency_closure(
            repo_root,
            ["open_composer/research/multiasset_forward_multimodal_r5.py"],
        )
    ).issubset(inventory_set)
    assert all(
        (repo_root / relative).is_file() and not (repo_root / relative).is_symlink()
        for relative in inventory
    )


def test_r5_harness_evidence_is_spec_bound_and_never_claims_paper_readiness(
    repo_root: Path,
) -> None:
    specs = {
        candidate_id: _load_strategy_spec_stable(repo_root / relative)
        for candidate_id, relative in SPEC_PATHS.items()
    }

    result = r5_module._validate_r5_harness_evidence(repo_root, specs)

    assert result["candidate_count"] == 8
    assert result["research_gate_pass"] is True
    assert result["empirical_execution_evidence_pass"] is False
    assert result["paper_readiness_evidence_pass"] is False
    assert sum(len(row["bindings"]) for row in result["candidates"].values()) == 56
    assert len(result["contract_bindings"]) == 3
    assert all(
        row["structural_research_harness_pass"] is True
        and row["empirical_execution_evidence_pass"] is False
        and row["paper_readiness_evidence_pass"] is False
        for row in result["candidates"].values()
    )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("missing", "missing or unreadable"),
        ("stale_receipt", "stale or self-asserted"),
        ("tampered_policy", "differs from spec"),
        ("wrong_strategy", "differs from spec"),
        ("self_asserted_ok", "differs from spec"),
    ],
)
def test_r5_harness_evidence_fails_closed_on_invalid_or_self_asserted_artifacts(
    repo_root: Path,
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    specs = _copy_r5_harness_workspace(repo_root, tmp_path)
    strategy_name = specs["R5C01"].name
    policy_path = tmp_path / "reports/harness/execution" / f"{strategy_name}-execution-policy.json"
    reality_path = (
        tmp_path / "reports/harness/execution" / f"{strategy_name}-execution-reality.json"
    )
    verify_path = tmp_path / "reports/harness/verify" / f"{strategy_name}.json"

    if mutation == "missing":
        reality_path.unlink()
    elif mutation == "stale_receipt":
        verify = json.loads(verify_path.read_text(encoding="utf-8"))
        verify["spec_semantic_sha256"] = "0" * 64
        verify_path.write_text(json.dumps(verify), encoding="utf-8")
    elif mutation == "tampered_policy":
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["gap_filter"]["max_open_gap_pct"] = 99.0
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
    else:
        reality = json.loads(reality_path.read_text(encoding="utf-8"))
        reality["strategy_name"] = "wrong_strategy"
        reality_path.write_text(json.dumps(reality), encoding="utf-8")
        if mutation == "self_asserted_ok":
            verify = json.loads(verify_path.read_text(encoding="utf-8"))
            content = reality_path.read_bytes()
            row = next(
                item for item in verify["artifacts"] if item["name"] == "execution_reality_report"
            )
            row["present"] = True
            row["schema_ok"] = True
            row["missing_fields"] = []
            row["binding"]["sha256"] = hashlib.sha256(content).hexdigest()
            row["binding"]["size_bytes"] = len(content)
            verify["overall"] = "ok"
            verify_path.write_text(json.dumps(verify), encoding="utf-8")

    with pytest.raises((ValueError, FileNotFoundError), match=match):
        r5_module._validate_r5_harness_evidence(tmp_path, specs)


def test_candidate_manifest_reconciliation_binds_specs_and_selection_roles(
    repo_root: Path,
) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }
    manifest = json.loads(
        (repo_root / R5_ITERATION_PATH / "candidate-manifest.json").read_text(encoding="utf-8")
    )
    payload = {
        "candidate_count": len(SPEC_PATHS),
        "candidates": {
            candidate_id: {
                "strategy_name": specs[candidate_id].name,
                "spec_path": path.as_posix(),
                "spec_hash": r5_module.strategy_content_hash(specs[candidate_id]),
                "promotion_eligible": next(
                    row["promotion_eligible"]
                    for row in manifest["candidates"]
                    if row["candidate_id"] == candidate_id
                ),
            }
            for candidate_id, path in SPEC_PATHS.items()
        },
    }

    reconciled = _reconcile_candidate_manifest_and_specs(payload, manifest, specs)

    assert reconciled["pass"] is True
    assert set(reconciled["selection_prohibited_candidate_ids"]) == {"R5F01", "R5P01"}

    forged_role = json.loads(json.dumps(payload))
    forged_role["candidates"]["R5P01"]["promotion_eligible"] = True
    with pytest.raises(ValueError, match="candidate/spec/manifest binding failed: R5P01"):
        _reconcile_candidate_manifest_and_specs(forged_role, manifest, specs)

    coordinated_role_forgery = json.loads(json.dumps(payload))
    coordinated_manifest_forgery = json.loads(json.dumps(manifest))
    coordinated_role_forgery["candidates"]["R5P01"]["promotion_eligible"] = True
    next(
        row for row in coordinated_manifest_forgery["candidates"] if row["candidate_id"] == "R5P01"
    )["promotion_eligible"] = True
    with pytest.raises(ValueError, match="differs from immutable contract: R5P01"):
        _reconcile_candidate_manifest_and_specs(
            coordinated_role_forgery,
            coordinated_manifest_forgery,
            specs,
        )

    forged_manifest = json.loads(json.dumps(manifest))
    forged_manifest["spec_hashes"][SPEC_PATHS["R5C01"].as_posix()] = "0" * 64
    with pytest.raises(ValueError, match="candidate/spec/manifest binding failed: R5C01"):
        _reconcile_candidate_manifest_and_specs(payload, forged_manifest, specs)


def test_locked_json_and_spec_readers_reject_hash_drift_and_symlinks(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    json_path = tmp_path / "payload.json"
    json_path.write_text('{"status":"ok"}\n', encoding="utf-8")
    expected_json_sha256 = hashlib.sha256(json_path.read_bytes()).hexdigest()

    assert _load_json(json_path, expected_sha256=expected_json_sha256) == {"status": "ok"}
    with pytest.raises(ValueError, match="locked SHA-256 mismatch"):
        _load_json(json_path, expected_sha256="0" * 64)

    json_link = tmp_path / "payload-link.json"
    json_link.symlink_to(json_path)
    with pytest.raises(ValueError, match="symlinked input"):
        _read_regular_file_bytes(json_link)

    spec_path = repo_root / SPEC_PATHS["R5D01"]
    expected_spec_sha256 = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    assert (
        _load_strategy_spec_stable(
            spec_path,
            expected_sha256=expected_spec_sha256,
        ).notes.candidate_id
        == "R5D01"
    )
    spec_link = tmp_path / "spec-link.yaml"
    spec_link.symlink_to(spec_path)
    with pytest.raises(ValueError, match="invalid locked StrategySpec"):
        _load_strategy_spec_stable(spec_link, expected_sha256=expected_spec_sha256)


def test_runtime_contracts_reject_tampered_formula_provenance_source(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / R5_ITERATION_PATH
    output.mkdir(parents=True)
    source = repo_root / R5_ITERATION_PATH
    for contract_filename in R5_RUNTIME_CONTRACT_FILES:
        (output / contract_filename).write_bytes((source / contract_filename).read_bytes())
    proposal_path = (
        tmp_path / "reports/research/iterations/mom_multiasset_ai_r2/factor-proposals.json"
    )
    proposal_path.parent.mkdir(parents=True)
    proposal_path.write_text('{"tampered":true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="feature.llm_formula_provenance.source_binding"):
        _validate_r5_runtime_contracts(output, root=tmp_path)


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
            lambda payload: payload["dsr"].update({"hac_lag": 20}),
            "validation.dsr.hac_lag",
        ),
        (
            "validation-contract.json",
            lambda payload: payload["llm_contribution_bootstrap"].update({"rng_seed": 4200}),
            "validation.llm_contribution_bootstrap.rng_seed",
        ),
        (
            "validation-contract.json",
            lambda payload: payload["role_gates"]["R5M02"].update({"probability_clip": 0.01}),
            "validation.role_gates.R5M02.probability_clip",
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
        (
            "feature-contract.json",
            lambda payload: payload["candidate_feature_sets"].update(
                {"R5M01": ["path_survival_label"]}
            ),
            "feature.candidate_feature_sets",
        ),
        (
            "feature-contract.json",
            lambda payload: payload["core_features"].update({"mom_21": "close_t + 1"}),
            "feature.core_features",
        ),
        (
            "feature-contract.json",
            lambda payload: payload["llm_formula_features"].update(
                {"llm_momentum_quality": "rank(mom_21)"}
            ),
            "feature.llm_formula_features",
        ),
        (
            "candidate-manifest.json",
            lambda payload: next(
                row for row in payload["candidates"] if row["candidate_id"] == "R5P01"
            ).update({"promotion_eligible": True}),
            "candidate_manifest.immutable_role_contract.R5P01",
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
    source = repo_root / R5_ITERATION_PATH
    for contract_filename in R5_RUNTIME_CONTRACT_FILES:
        (tmp_path / contract_filename).write_bytes((source / contract_filename).read_bytes())
    path = tmp_path / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        _validate_r5_runtime_contracts(tmp_path)


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


def test_model_predictor_frame_excludes_all_outcomes_identity_and_timing() -> None:
    expected = r5_module.R5_RUNTIME_PREDICTOR_CONTRACT["R5M01"]
    frame = pd.DataFrame(
        {
            **{name: [float(index)] for index, name in enumerate(expected)},
            "decision_position": [100],
            "decision_session": ["2026-01-30"],
            "execution_session": ["2026-02-02"],
            "label_end_position": [122],
            "forward_return_21": [99.0],
            "path_survival_label": [1],
            "max_open_path_drawdown": [-0.01],
            "symbol": ["SPY"],
        }
    )

    predictors = r5_module._validated_predictor_frame(
        frame,
        candidate_id="R5M01",
        feature_names=expected,
        label_name="forward_return_21",
    )

    assert tuple(predictors.columns) == expected
    assert not (set(predictors.columns) & r5_module.R5_FORBIDDEN_PREDICTOR_COLUMNS)
    with pytest.raises(ValueError, match="immutable runtime predictor contract mismatch"):
        r5_module._validated_predictor_frame(
            frame,
            candidate_id="R5M01",
            feature_names=("path_survival_label",),
            label_name="forward_return_21",
        )


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
        "R5D01": candidate(0.5),
        "R5D02": candidate(0.6),
        "R5M01": candidate(1.0),
        "R5M02": candidate(1.1),
        "R5L01": candidate(1.2),
        "R5C01": candidate(2.0),
        "R5F01": candidate(1.0),
        "R5P01": candidate(0.4),
    }
    candidates["R5P01"]["unexpected_model_fallback_count"] = 1
    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    aggregate_parts: list[pd.DataFrame] = []
    for index, fold_id in enumerate(fold_ids):
        sessions = pd.bdate_range(f"202{index + 1}-01-04", periods=2)
        m01 = pd.DataFrame({"AAA": [1.0, 1.0], "BIL": [0.0, 0.0]}, index=sessions)
        segment_targets[fold_id] = {"R5M01": m01, "R5M02": m01.copy()}
        aggregate_parts.append(m01)
    m01_aggregate = pd.concat(aggregate_parts)
    bil = pd.DataFrame(
        {"AAA": np.zeros(len(m01_aggregate)), "BIL": np.ones(len(m01_aggregate))},
        index=m01_aggregate.index,
    )
    aggregate_targets = {
        "R5D01": bil,
        "R5D02": bil.copy(),
        "R5M01": m01_aggregate,
        "R5M02": m01_aggregate.copy(),
        "R5L01": m01_aggregate.copy(),
        "R5C01": m01_aggregate.copy(),
        "R5F01": m01_aggregate.copy(),
        "R5P01": bil.copy(),
    }
    formula_evidence = {
        "joint_permutation_pass": True,
        "formula_feature_divergence_pass": True,
        "formula_composite_nonconstant_pass": True,
    }
    validation_contract = json.loads(
        (repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    daily_rows, event_rows = _synthetic_llm_bootstrap_ledgers()
    bootstrap_evidence = paired_transfer_sharpe_bootstrap(
        daily_rows,
        event_rows,
        contract=validation_contract["llm_contribution_bootstrap"],
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
        llm_contribution_bootstrap=bootstrap_evidence,
        validation_contract=validation_contract,
    )

    assert gates["R5M02"]["behavior_gate_pass"] is False
    assert gates["R5M02"]["pass"] is False
    assert gates["R5P01"]["zero_unexpected_model_fallbacks"] is False
    assert gates["R5P01"]["pass"] is False
    assert gates["R5C01"]["performance_gate_pass"] is True
    assert gates["R5C01"]["pass"] is False

    for candidate_id in ("R5M01", "R5L01", "R5C01"):
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
        llm_contribution_bootstrap=bootstrap_evidence,
        validation_contract=validation_contract,
    )
    assert stricter["R5M01"]["pass"] is False
    assert stricter["R5L01"]["pass"] is False
    assert stricter["R5C01"]["performance_gate_pass"] is False

    candidates["R5P01"]["unexpected_model_fallback_count"] = 0
    validation_contract["role_gates"]["R5C01"]["minimum_winning_folds"] = 3
    failed_bootstrap = json.loads(json.dumps(bootstrap_evidence))
    failed_bootstrap["pass"] = False
    bootstrap_blocked = _evaluate_role_gates(
        candidates,
        calibration={
            "joint_passing_fold_count": 4,
            "required_joint_passing_fold_count": 3,
            "pass": True,
        },
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_evidence,
        llm_contribution_bootstrap=failed_bootstrap,
        validation_contract=validation_contract,
    )
    assert bootstrap_blocked["R5C01"]["performance_gate_pass"] is True
    assert bootstrap_blocked["R5C01"]["valid_R5P01_placebo"] is True
    assert bootstrap_blocked["R5C01"]["paired_transfer_bootstrap"]["pass"] is False
    assert bootstrap_blocked["R5C01"]["pass"] is False


def test_staged_role_gates_reject_forged_performance_placebo_and_status(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        "R5D01": candidate(0.5),
        "R5D02": candidate(0.6),
        "R5M01": candidate(1.0),
        "R5M02": candidate(1.1),
        "R5L01": candidate(1.2),
        "R5C01": candidate(2.0),
        "R5F01": candidate(1.0),
        "R5P01": candidate(0.4),
    }
    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    aggregate_parts: list[pd.DataFrame] = []
    for index, fold_id in enumerate(fold_ids):
        sessions = pd.bdate_range(f"202{index + 1}-01-04", periods=2)
        m01 = pd.DataFrame({"AAA": [1.0, 1.0], "BIL": [0.0, 0.0]}, index=sessions)
        segment_targets[fold_id] = {"R5M01": m01, "R5M02": m01.copy()}
        aggregate_parts.append(m01)
    m01_aggregate = pd.concat(aggregate_parts)
    bil = pd.DataFrame(
        {"AAA": np.zeros(len(m01_aggregate)), "BIL": np.ones(len(m01_aggregate))},
        index=m01_aggregate.index,
    )
    aggregate_targets = {
        "R5D01": bil,
        "R5D02": bil.copy(),
        "R5M01": m01_aggregate,
        "R5M02": m01_aggregate.copy(),
        "R5L01": m01_aggregate.copy(),
        "R5C01": m01_aggregate.copy(),
        "R5F01": m01_aggregate.copy(),
        "R5P01": bil.copy(),
    }
    formula_evidence = {
        "joint_permutation_pass": True,
        "formula_feature_divergence_pass": True,
        "formula_composite_nonconstant_pass": True,
    }
    validation_contract = json.loads(
        (repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    m02_contract = validation_contract["role_gates"]["R5M02"]
    calibration = {
        "joint_passing_fold_count": 4,
        "required_joint_passing_fold_count": int(
            m02_contract["joint_brier_and_slope_passing_folds_min"]
        ),
        "probability_clip": float(m02_contract["probability_clip"]),
        "calibration_slope_min": float(m02_contract["calibration_slope_min"]),
        "calibration_slope_max": float(m02_contract["calibration_slope_max"]),
        "expected_observation_count_by_fold": m02_contract["expected_observation_count_by_fold"],
        "minimum_class_count_per_fold": int(m02_contract["minimum_class_count_per_fold"]),
        "all_observation_counts_match": True,
        "pass": True,
    }
    daily_rows, event_rows = _synthetic_llm_bootstrap_ledgers()
    bootstrap = paired_transfer_sharpe_bootstrap(
        daily_rows,
        event_rows,
        contract=validation_contract["llm_contribution_bootstrap"],
    )
    role_gates = _evaluate_role_gates(
        candidates,
        calibration=calibration,
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_evidence,
        llm_contribution_bootstrap=bootstrap,
        validation_contract=validation_contract,
    )
    for candidate_id, role_gate in role_gates.items():
        candidates[candidate_id]["role_gate"] = role_gate

    fallback_counts = {candidate_id: 0 for candidate_id in SPEC_PATHS}
    monkeypatch.setattr(
        r5_module,
        "_staged_target_frames",
        lambda _rows, _contract: (aggregate_targets, segment_targets, fallback_counts),
    )
    monkeypatch.setattr(
        r5_module,
        "_formula_placebo_evidence",
        lambda _dataset, *, decision_sessions: formula_evidence,
    )
    monkeypatch.setattr(
        r5_module,
        "_staged_calibration_from_ledgers",
        lambda _features, _models, _targets, _contract: calibration,
    )

    valid = _reconcile_staged_role_gate_evidence(
        feature_rows=[],
        model_records=[],
        target_rows=[],
        candidates=candidates,
        reported_calibration=calibration,
        reported_formula_placebo_evidence=formula_evidence,
        llm_contribution_bootstrap=bootstrap,
        validation_contract=validation_contract,
    )
    assert valid["pass"] is True

    forged_performance = json.loads(json.dumps(candidates))
    for fold in fold_ids:
        forged_performance["R5C01"]["folds"][fold]["primary_10bps"]["annualized_sharpe"] = -1.0
    forged_performance["R5C01"]["transfer_holdout"]["primary_10bps"]["annualized_sharpe"] = -1.0
    with pytest.raises(ValueError, match="role gate is not derived: R5C01"):
        _reconcile_staged_role_gate_evidence(
            feature_rows=[],
            model_records=[],
            target_rows=[],
            candidates=forged_performance,
            reported_calibration=calibration,
            reported_formula_placebo_evidence=formula_evidence,
            llm_contribution_bootstrap=bootstrap,
            validation_contract=validation_contract,
        )

    forged_placebo = {**formula_evidence, "joint_permutation_pass": False}
    with pytest.raises(ValueError, match="placebo evidence differs"):
        _reconcile_staged_role_gate_evidence(
            feature_rows=[],
            model_records=[],
            target_rows=[],
            candidates=candidates,
            reported_calibration=calibration,
            reported_formula_placebo_evidence=forged_placebo,
            llm_contribution_bootstrap=bootstrap,
            validation_contract=validation_contract,
        )

    forged_status = json.loads(json.dumps(candidates))
    forged_status["R5C01"]["role_gate"]["pass"] = not role_gates["R5C01"]["pass"]
    with pytest.raises(ValueError, match="role gate is not derived: R5C01"):
        _reconcile_staged_role_gate_evidence(
            feature_rows=[],
            model_records=[],
            target_rows=[],
            candidates=forged_status,
            reported_calibration=calibration,
            reported_formula_placebo_evidence=formula_evidence,
            llm_contribution_bootstrap=bootstrap,
            validation_contract=validation_contract,
        )


def test_evaluation_statuses_are_derived_and_never_make_paper_ready() -> None:
    candidates = {
        candidate_id: {
            "promotion_eligible": candidate_id not in {"R5F01", "R5P01"},
            "role_gate": {"pass": True},
            "family_gates": {"pass": True},
            "historical_research_gate_pass": True,
        }
        for candidate_id in SPEC_PATHS
    }

    statuses = _derive_evaluation_statuses(
        candidates,
        workflow_pass=True,
        pbo_pass=True,
    )

    assert statuses["research_pass"] is True
    assert statuses["llm_contribution_pass"] is True
    assert statuses["paper_ready_pass"] is False
    assert "R5C01" in statuses["selected_candidate_ids"]

    forged_control = json.loads(json.dumps(candidates))
    forged_control["R5P01"]["promotion_eligible"] = True
    with pytest.raises(ValueError, match="immutable role contract: R5P01"):
        _derive_evaluation_statuses(
            forged_control,
            workflow_pass=True,
            pbo_pass=True,
        )

    candidates["R5C01"]["role_gate"]["pass"] = False
    candidates["R5C01"]["historical_research_gate_pass"] = False
    bootstrap_failed = _derive_evaluation_statuses(
        candidates,
        workflow_pass=True,
        pbo_pass=True,
    )
    assert bootstrap_failed["llm_contribution_pass"] is False
    assert "R5C01" not in bootstrap_failed["selected_candidate_ids"]
    assert bootstrap_failed["paper_ready_pass"] is False

    workflow_failed = _derive_evaluation_statuses(
        candidates,
        workflow_pass=False,
        pbo_pass=True,
    )
    assert workflow_failed["selected_candidate_ids"] == []
    assert workflow_failed["research_pass"] is False
    assert workflow_failed["llm_contribution_pass"] is False
    assert workflow_failed["paper_ready_pass"] is False

    candidates["R5C01"]["historical_research_gate_pass"] = True
    with pytest.raises(ValueError, match="not derived from gates"):
        _derive_evaluation_statuses(
            candidates,
            workflow_pass=True,
            pbo_pass=True,
        )


def test_trial_ledger_rows_are_exactly_regenerated() -> None:
    candidates = {
        candidate_id: {
            "spec_hash": hashlib.sha256(candidate_id.encode("ascii")).hexdigest(),
            "promotion_eligible": candidate_id not in {"R5F01", "R5P01"},
            "aggregate_cost_views": {"primary_10bps": {"annualized_sharpe": 1.0}},
            "folds": {"F1": {"primary_10bps": {"total_return_pct": 1.0}}},
            "transfer_holdout": {"primary_10bps": {"annualized_sharpe": 1.0}},
            "dsr": {"promotion_probability": 0.96},
            "role_gate": {"pass": True},
            "family_gates": {"pass": True},
            "historical_research_gate_pass": True,
        }
        for candidate_id in SPEC_PATHS
    }
    rows = r5_module._trial_ledger_rows(candidates)

    assert _reconcile_staged_trial_ledger(candidates, rows)["pass"] is True

    forged = json.loads(json.dumps(rows))
    forged[0]["schema_version"] = 999
    forged[0]["forged_claim"] = True
    with pytest.raises(ValueError, match="canonical regenerated rows"):
        _reconcile_staged_trial_ledger(candidates, forged)


def test_evaluation_markdown_attests_bootstrap_method_hashes_and_interpretation() -> None:
    candidate_payload = {
        "aggregate_cost_views": {
            "primary_10bps": {
                "total_return_pct": 1.0,
                "annualized_sharpe": 1.0,
                "max_drawdown_pct": -1.0,
            }
        },
        "dsr": {
            "iid_probability": 0.96,
            "hac_probability": 0.95,
            "promotion_probability": 0.95,
        },
        "historical_research_gate_pass": True,
    }
    payload = {
        "iter_id": "mom_multiasset_forward_multimodal_r5",
        "decision": "stop_r5",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "family_pbo": {"probability": 0.1, "partition_count": 70},
        "candidates": {candidate_id: candidate_payload for candidate_id in SPEC_PATHS},
        "llm_contribution_bootstrap": {
            "method_id": "paired_non_circular_moving_block_bootstrap_sharpe_delta_v1",
            "config_sha256": "a" * 64,
            "bootstrap_index_matrix_sha256": "b" * 64,
            "source_ledgers": {
                "daily_return_ledger_sha256": "c" * 64,
                "event_ledger_sha256": "d" * 64,
            },
            "comparisons": {
                "R5C01_minus_R5M01": {
                    "observed_annualized_sharpe_delta": 0.1,
                    "lower_confidence_bound": 0.01,
                    "pass": True,
                },
                "R5C01_minus_R5P01": {
                    "observed_annualized_sharpe_delta": 0.2,
                    "lower_confidence_bound": -0.01,
                    "pass": False,
                },
            },
        },
    }

    markdown = _render_markdown(payload)

    assert "paired_non_circular_moving_block_bootstrap_sharpe_delta_v1" in markdown
    for digest in ("a" * 64, "b" * 64, "c" * 64, "d" * 64):
        assert digest in markdown
    assert "R5C01_minus_R5M01" in markdown
    assert "R5C01_minus_R5P01" in markdown
    assert "not evidence of independent LLM Alpha" in markdown


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
                        "interval_end": f"202{fold_index}-01-0{day + 2}",
                        "net_return": candidate_index * 0.001 + day * 0.0001,
                    }
                )
    rows.append(
        {
            "candidate_id": "BENCHMARK:SPY",
            "scope_id": "AGGREGATE",
            "cost_view": "primary_10bps",
            "interval_start": "2021-01-01",
            "interval_end": "2021-01-02",
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
    assert [row["scope_id"] for row in source_rows] == ["F1", "F1", "F2", "F2"]

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
        "candidate_id": "R5M01",
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
            "schema_version": 1,
            "iter_id": "mom_multiasset_forward_multimodal_r5",
            "model_id": "model-1",
            "segment_id": "F1",
            "candidate_id": "R5M01",
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

    forged_contract = json.loads(json.dumps(rows))
    forged_contract[0]["schema_version"] = 999
    forged_contract[0]["forged_claim"] = True
    with pytest.raises(ValueError, match="row contract is invalid"):
        _reconcile_model_prediction_evidence([record], forged_contract)


def test_model_provenance_is_exactly_bound_to_locked_expected_hashes() -> None:
    model_records = [{"status": "fit_complete"}, {"status": "fallback_applied"}]
    prediction_reconciliation = {"pass": True, "prediction_row_count": 3}
    inventory = {
        "model_ledger": {"row_count": 2, "sha256": "a" * 64},
        "prediction_ledger": {"row_count": 3, "sha256": "b" * 64},
    }
    expected_provenance = {
        "data_manifest_sha256": "c" * 64,
        "feature_contract_sha256": "d" * 64,
        "label_contract_sha256": "e" * 64,
        "prompt_hash": "f" * 64,
    }
    payload = _model_provenance_payload(
        model_records,
        prediction_reconciliation=prediction_reconciliation,
        ledger_inventory=inventory,
        expected_provenance=expected_provenance,
    )

    assert (
        _reconcile_staged_model_provenance(
            payload,
            model_records,
            prediction_reconciliation=prediction_reconciliation,
            ledger_inventory=inventory,
            expected_provenance=expected_provenance,
        )["pass"]
        is True
    )

    forged = json.loads(json.dumps(payload))
    forged["prompt_hash"] = "0" * 64
    forged["forged_claim"] = True
    with pytest.raises(ValueError, match="not independently derived"):
        _reconcile_staged_model_provenance(
            forged,
            model_records,
            prediction_reconciliation=prediction_reconciliation,
            ledger_inventory=inventory,
            expected_provenance=expected_provenance,
        )


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


def test_staged_target_frames_reconstruct_segments_and_fallback_counts(
    repo_root: Path,
) -> None:
    validation_contract = json.loads(
        (repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    symbols = sorted(["BIL", *RANKABLE_SYMBOLS])
    selected_symbols = list(RANKABLE_SYMBOLS[:3])
    weights = {symbol: 0.0 for symbol in symbols}
    for symbol in selected_symbols:
        weights[symbol] = 1.0 / 3.0
    row_hash = hashlib.sha256(
        json.dumps(weights, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    segment_executions = {
        str(fold["fold_id"]): str(fold["test_start"]) for fold in validation_contract["folds"]
    }
    segment_executions["TRANSFER"] = str(validation_contract["transfer_holdout"]["start"])
    rows = []
    for segment_id, execution_session in segment_executions.items():
        decision_session = (
            (pd.Timestamp(execution_session) - pd.Timedelta(days=1)).date().isoformat()
        )
        for candidate_id in SPEC_PATHS:
            fallback_reason = (
                "intentional_missing_modality_identity" if candidate_id == "R5F01" else None
            )
            rows.append(
                {
                    "schema_version": 1,
                    "iter_id": "mom_multiasset_forward_multimodal_r5",
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": selected_symbols,
                    "weights": dict(weights),
                    "target_sha256": row_hash,
                    "fallback_reason": fallback_reason,
                    "unexpected_model_fallback": False,
                }
            )

    aggregate, segments, fallback_counts = _staged_target_frames(rows, validation_contract)

    assert set(segments) == {"F1", "F2", "F3", "F4", "TRANSFER"}
    assert all(len(frame) == 5 for frame in aggregate.values())
    assert fallback_counts == {candidate_id: 0 for candidate_id in SPEC_PATHS}

    forged = json.loads(json.dumps(rows))
    forged[0]["unexpected_model_fallback"] = True
    with pytest.raises(ValueError, match="fallback flag is not derived"):
        _staged_target_frames(forged, validation_contract)

    forged_reason = json.loads(json.dumps(rows))
    forged_reason[0]["fallback_reason"] = "fewer_than_three_survival_eligible_symbols"
    with pytest.raises(ValueError, match="fallback reason is not role-bound"):
        _staged_target_frames(forged_reason, validation_contract)

    out_of_window = json.loads(json.dumps(rows))
    out_of_window[0]["decision_session"] = "2020-12-30"
    out_of_window[0]["execution_session"] = "2020-12-31"
    with pytest.raises(ValueError, match="execution is outside its segment"):
        _staged_target_frames(out_of_window, validation_contract)


def test_m02_copies_m01_when_upstream_ranker_falls_back(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }
    symbols = sorted(RANKABLE_SYMBOLS)
    rows = []
    for symbol_index, symbol in enumerate(symbols):
        rows.append(
            {
                "decision_position": 300,
                "decision_session": "2024-01-31",
                "execution_position": 301,
                "execution_session": "2024-02-01",
                "label_end_position": 322,
                "label_end_session": "2024-03-01",
                "symbol": symbol,
                "raw_mom_252_skip21": float(symbol_index),
                "raw_mom_126_skip21": float(symbol_index),
                "raw_trend_gap_252": 1.0,
                "path_survival_label": symbol_index % 2,
                **{name: float(symbol_index) for name in FORMULA_FEATURES},
            }
        )
    dataset = pd.DataFrame(rows)

    def fake_fit_predict(spec, _dataset, current, **_kwargs):
        candidate_id = str(spec.notes.model_dump(mode="json")["candidate_id"])
        if candidate_id == "R5M01":
            return None, {
                "candidate_id": candidate_id,
                "status": "fallback_applied",
                "failure_reason": "insufficient_training_rows",
                "predictions": [],
            }
        if candidate_id == "R5M02":
            prediction = np.asarray(
                [0.9 if index < len(current) - TOP_N else 0.1 for index in range(len(current))],
                dtype=float,
            )
        else:
            prediction = np.arange(len(current), dtype=float)
        return prediction, {
            "candidate_id": candidate_id,
            "status": "fit_complete",
            "failure_reason": None,
            "training_label_mean": 0.5,
            "predictions": [
                {"symbol": str(symbol), "value": float(value)}
                for symbol, value in zip(current["symbol"], prediction, strict=True)
            ],
        }

    monkeypatch.setattr(r5_module, "_fit_predict_for_point", fake_fit_predict)
    frames, target_rows, _, _ = build_candidate_targets_for_segment(
        dataset,
        segment_id="F1",
        execution_start="2024-02-01",
        execution_end="2024-02-01",
        train_start_session="2018-02-01",
        columns=pd.Index(sorted(["BIL", *RANKABLE_SYMBOLS])),
        specs=specs,
    )

    pd.testing.assert_frame_equal(frames["R5M02"], frames["R5M01"])
    m02_row = next(row for row in target_rows if row["candidate_id"] == "R5M02")
    assert m02_row["fallback_reason"] == "upstream_R5M01_fallback"
    assert m02_row["unexpected_model_fallback"] is True


def test_locked_mark_replay_rejects_coordinated_cost_event_deletion(
    repo_root: Path,
) -> None:
    runtime_contracts = _validate_r5_runtime_contracts(
        repo_root / R5_ITERATION_PATH,
        root=repo_root,
    )
    validation_contract = runtime_contracts["validation"]
    fold_segments = [
        {
            "segment_id": str(fold["fold_id"]),
            "start": str(fold["test_start"]),
            "end": str(fold["test_end"]),
        }
        for fold in validation_contract["folds"]
    ]
    transfer = validation_contract["transfer_holdout"]
    segments = [
        *fold_segments,
        {"segment_id": "TRANSFER", "start": transfer["start"], "end": transfer["end"]},
    ]
    sessions = pd.bdate_range(segments[0]["start"], segments[-1]["end"])
    position = np.arange(len(sessions), dtype=float)
    symbols = sorted(["BIL", *RANKABLE_SYMBOLS])
    marks = pd.DataFrame(
        {
            symbol: 100.0
            * np.exp(
                np.cumsum(
                    0.00005
                    + symbol_index * 0.000002
                    + 0.0004 * np.sin(position / (17.0 + symbol_index))
                )
            )
            for symbol_index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    target_rows = []
    for segment_index, segment in enumerate(segments):
        selected = [
            RANKABLE_SYMBOLS[(segment_index + offset) % len(RANKABLE_SYMBOLS)]
            for offset in range(3)
        ]
        weights = {symbol: 0.0 for symbol in symbols}
        for symbol in selected:
            weights[symbol] = 1.0 / 3.0
        weights["BIL"] = 1.0 - sum(weights.values())
        row_hash = hashlib.sha256(
            json.dumps(weights, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for candidate_id in SPEC_PATHS:
            fallback_reason = (
                "intentional_missing_modality_identity" if candidate_id == "R5F01" else None
            )
            target_rows.append(
                {
                    "schema_version": 1,
                    "iter_id": "mom_multiasset_forward_multimodal_r5",
                    "segment_id": segment["segment_id"],
                    "candidate_id": candidate_id,
                    "decision_session": (pd.Timestamp(segment["start"]) - pd.Timedelta(days=1))
                    .date()
                    .isoformat(),
                    "execution_session": segment["start"],
                    "selected_symbols": selected,
                    "weights": dict(weights),
                    "target_sha256": row_hash,
                    "fallback_reason": fallback_reason,
                    "unexpected_model_fallback": False,
                }
            )
    aggregate_targets, segment_targets, _ = _staged_target_frames(
        target_rows,
        validation_contract,
    )
    cost_views = runtime_contracts["cost_views"]
    daily_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []

    def append_simulation(
        simulation: ExactSimulationResult,
        *,
        candidate_id: str,
        scope_id: str,
        cost_view: str,
    ) -> None:
        daily_rows.extend(
            r5_module._scoped_daily_returns(
                simulation.daily,
                candidate_id=candidate_id,
                scope_id=scope_id,
                cost_view=cost_view,
            )
        )
        event_rows.extend(
            r5_module._scoped_events(
                simulation.events,
                candidate_id=candidate_id,
                scope_id=scope_id,
                cost_view=cost_view,
            )
        )

    for candidate_id in SPEC_PATHS:
        for cost_view, cost_bps in cost_views.items():
            append_simulation(
                simulate_exact_target_portfolio(
                    marks,
                    aggregate_targets[candidate_id],
                    cost_bps=float(cost_bps),
                    start=segments[0]["start"],
                    end=segments[-1]["end"],
                ),
                candidate_id=candidate_id,
                scope_id="AGGREGATE",
                cost_view=cost_view,
            )
        for segment in segments:
            for cost_view in ("primary_10bps", "stress_20bps"):
                append_simulation(
                    simulate_exact_target_portfolio(
                        marks,
                        segment_targets[segment["segment_id"]][candidate_id],
                        cost_bps=float(cost_views[cost_view]),
                        start=segment["start"],
                        end=segment["end"],
                    ),
                    candidate_id=candidate_id,
                    scope_id=segment["segment_id"],
                    cost_view=cost_view,
                )

    benchmark_payload, benchmark_simulations, benchmark_targets = _benchmark_family_exact(
        marks,
        monthly_sessions=aggregate_targets["R5D01"].index,
        start=segments[0]["start"],
        end=segments[-1]["end"],
        primary_cost_bps=float(cost_views["primary_10bps"]),
        stress_cost_bps=float(cost_views["stress_20bps"]),
    )
    for benchmark_id, views in benchmark_simulations.items():
        for cost_view, simulation in views.items():
            append_simulation(
                simulation,
                candidate_id=f"BENCHMARK:{benchmark_id}",
                scope_id="AGGREGATE",
                cost_view=cost_view,
            )
    benchmark_rows = r5_module._benchmark_ledger_rows(
        benchmark_payload,
        benchmark_simulations,
        benchmark_targets,
        promotion_gate_ids=set(
            runtime_contracts["benchmark_gate_config"]["required_benchmark_ids"]
        ),
    )
    payload = {"benchmarks": benchmark_payload}

    replay = _replay_staged_performance_ledgers(
        marks,
        target_rows,
        daily_rows,
        event_rows,
        benchmark_rows,
        payload,
        runtime_contracts,
    )
    assert replay["pass"] is True

    forged_benchmarks = json.loads(json.dumps(benchmark_rows))
    forged_benchmarks[0]["schema_version"] = 999
    forged_benchmarks[0]["forged_claim"] = True
    with pytest.raises(ValueError, match="benchmark ledger differs from locked-mark replay"):
        _replay_staged_performance_ledgers(
            marks,
            target_rows,
            daily_rows,
            event_rows,
            forged_benchmarks,
            payload,
            runtime_contracts,
        )

    forged_daily = json.loads(json.dumps(daily_rows))
    forged_events = json.loads(json.dumps(event_rows))
    removed_event = next(
        row
        for row in forged_events
        if row["candidate_id"] == "R5C01"
        and row["scope_id"] == "AGGREGATE"
        and row["cost_view"] == "primary_10bps"
        and row["reason"] == "scheduled_rebalance"
        and row["session"] != segments[0]["start"]
    )
    forged_events.remove(removed_event)
    affected_daily = next(
        row
        for row in forged_daily
        if row["candidate_id"] == "R5C01"
        and row["scope_id"] == "AGGREGATE"
        and row["cost_view"] == "primary_10bps"
        and row["interval_start"] == removed_event["session"]
    )
    affected_daily["cost_factor"] = float(affected_daily["cost_factor"]) / float(
        removed_event["posttrade_equity_ratio"]
    )
    affected_daily["net_factor"] = float(affected_daily["cost_factor"]) * float(
        affected_daily["gross_factor_after_rebalance"]
    )
    affected_daily["net_return"] = float(affected_daily["net_factor"]) - 1.0

    with pytest.raises(ValueError, match="locked-mark replay"):
        _replay_staged_performance_ledgers(
            marks,
            target_rows,
            forged_daily,
            forged_events,
            benchmark_rows,
            payload,
            runtime_contracts,
        )


def test_staged_calibration_is_reconstructed_from_feature_and_model_ledgers(
    repo_root: Path,
) -> None:
    validation_contract = json.loads(
        (repo_root / VALIDATION_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    m02_contract = validation_contract["role_gates"]["R5M02"]
    m02_contract["expected_observation_count_by_fold"] = {
        str(fold["fold_id"]): len(RANKABLE_SYMBOLS) for fold in validation_contract["folds"]
    }
    m02_contract["minimum_class_count_per_fold"] = 2
    feature_rows = []
    model_records = []
    target_rows = []
    for fold_index, fold in enumerate(validation_contract["folds"]):
        fold_id = str(fold["fold_id"])
        decision_session = f"{2021 + fold_index}-01-04"
        execution_session = (pd.Timestamp(decision_session) + pd.offsets.BDay(1)).date().isoformat()
        predictions = []
        for symbol_index, symbol in enumerate(sorted(RANKABLE_SYMBOLS)):
            label = symbol_index % 2
            probability = 0.8 if label else 0.2
            feature_rows.append(
                {
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "symbol": symbol,
                    "label_end_session": f"{2021 + fold_index}-02-04",
                    "path_survival_label": label,
                }
            )
            predictions.append({"symbol": symbol, "value": probability})
        model_records.append(
            {
                "candidate_id": "R5M02",
                "segment_id": fold_id,
                "decision_session": decision_session,
                "status": "fit_complete",
                "training_label_mean": 0.5,
                "predictions": predictions,
            }
        )
        target_rows.append(
            {
                "candidate_id": "R5M02",
                "segment_id": fold_id,
                "decision_session": decision_session,
                "execution_session": execution_session,
            }
        )

    calibration = _staged_calibration_from_ledgers(
        feature_rows,
        model_records,
        target_rows,
        validation_contract,
    )

    assert calibration["all_observation_counts_match"] is True
    assert all(
        row["observation_count"] == len(RANKABLE_SYMBOLS) for row in calibration["folds"].values()
    )
    with pytest.raises(ValueError, match="model coverage is incomplete"):
        _staged_calibration_from_ledgers(
            feature_rows,
            model_records[:-1],
            target_rows,
            validation_contract,
        )

    pre_fold_features = json.loads(json.dumps(feature_rows))
    pre_fold_models = json.loads(json.dumps(model_records))
    pre_fold_targets = json.loads(json.dumps(target_rows))
    first_fold_id = str(validation_contract["folds"][0]["fold_id"])
    for row in pre_fold_features:
        if row["decision_session"] == model_records[0]["decision_session"]:
            row["decision_session"] = "2020-12-01"
            row["execution_session"] = "2020-12-02"
    pre_fold_models[0]["decision_session"] = "2020-12-01"
    pre_fold_targets[0]["decision_session"] = "2020-12-01"
    pre_fold_targets[0]["execution_session"] = "2020-12-02"
    assert pre_fold_models[0]["segment_id"] == first_fold_id
    with pytest.raises(ValueError, match="observation is outside its fold"):
        _staged_calibration_from_ledgers(
            pre_fold_features,
            pre_fold_models,
            pre_fold_targets,
            validation_contract,
        )


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
        (repo_root / R5_ITERATION_PATH / "benchmark-contract.json").read_text(encoding="utf-8")
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

    for candidate_id, gates in result.items():
        candidates[candidate_id]["benchmark_gate"] = gates
    assert (
        _reconcile_staged_benchmark_gates(
            candidates,
            benchmark_payload=benchmark_payload,
            benchmark_contract=contract,
        )
        == result
    )

    forged = json.loads(json.dumps(candidates))
    forged["FAIL"]["benchmark_gate"]["pass"] = True
    with pytest.raises(ValueError, match="benchmark gate is not derived: FAIL"):
        _reconcile_staged_benchmark_gates(
            forged,
            benchmark_payload=benchmark_payload,
            benchmark_contract=contract,
        )


def test_canonical_target_identity_excludes_candidate_metadata() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=2)
    targets = pd.DataFrame(
        [{"AAA": 1.0 / 3.0, "BIL": 2.0 / 3.0}, {"AAA": 0.0, "BIL": 1.0}],
        index=sessions,
    )

    copied = targets[["BIL", "AAA"]].copy()

    assert canonical_target_bytes(targets) == canonical_target_bytes(copied)
    assert canonical_target_hash(targets) == canonical_target_hash(copied)


def test_feature_ledger_is_replayed_from_locked_ohlcv_and_specs(repo_root: Path) -> None:
    sessions = pd.bdate_range("2020-01-02", periods=340)
    position = np.arange(len(sessions), dtype=float)
    symbols = sorted(["BIL", *RANKABLE_SYMBOLS])
    close = pd.DataFrame(
        {
            symbol: 100.0
            * np.exp(
                np.cumsum(
                    0.0001
                    + symbol_index * 0.000003
                    + 0.0005 * np.sin(position / (13.0 + symbol_index))
                )
            )
            for symbol_index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    volume = pd.DataFrame(
        {
            symbol: 1_000_000.0
            + 1_000.0 * symbol_index
            + 10_000.0 * np.cos(position / (7.0 + symbol_index))
            for symbol_index, symbol in enumerate(symbols)
        },
        index=sessions,
    )
    panel = r5_module.PanelData(
        open=close * 1.0001,
        high=close * 1.001,
        low=close * 0.999,
        close=close,
        volume=volume,
        manifest={},
    )
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in SPEC_PATHS.items()
    }
    execution_contract = _validate_r5_spec_execution_contract(specs)
    features = build_point_in_time_features(
        close,
        volume,
        formula_spec=specs[execution_contract["formula_spec_candidate_id"]],
    )
    dataset = r5_module.build_monthly_feature_dataset(
        panel,
        features,
        placebo_spec=specs[execution_contract["placebo_spec_candidate_id"]],
        rebalance_schedule=execution_contract["rebalance_schedule"],
    )
    rows = r5_module._dataframe_records(dataset)

    replay = _replay_staged_feature_ledger(panel, rows, specs)

    assert replay["locked_ohlcv_replayed"] is True
    mutated = json.loads(json.dumps(rows))
    changed = next(row for row in mutated if row["mom_21"] is not None)
    changed["mom_21"] = float(changed["mom_21"]) + 0.01
    with pytest.raises(ValueError, match="feature ledger differs from locked OHLCV"):
        _replay_staged_feature_ledger(panel, mutated, specs)


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
    assert canonical_target_bytes(targets["R5F01"]) == canonical_target_bytes(targets["R5M01"])
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

    label_as_feature = json.loads(json.dumps(models))
    label_as_feature[0]["feature_names"][0] = label_as_feature[0]["label_name"]
    with pytest.raises(ValueError, match="model feature identity mismatch"):
        _reconcile_feature_and_model_refits(
            r5_module._dataframe_records(dataset),
            label_as_feature,
            specs,
        )

    execution_dates = [
        (decision + pd.offsets.BDay(1)).date().isoformat() for decision in selected_dates
    ]
    validation_contract = {
        "folds": [
            {
                "fold_id": "F1",
                "train_start": "2018-02-01",
                "test_start": execution_dates[0],
                "test_end": execution_dates[1],
            }
        ],
        "transfer_holdout": {
            "start": execution_dates[2],
            "end": execution_dates[3],
        },
    }
    provenance = {
        "data_manifest_sha256": "a" * 64,
        "feature_contract_sha256": "b" * 64,
        "label_contract_sha256": "c" * 64,
        "prompt_hash": "d" * 64,
    }
    staged_targets: list[dict[str, object]] = []
    staged_models: list[dict[str, object]] = []
    for segment_id, segment_start, segment_end in (
        ("F1", execution_dates[0], execution_dates[1]),
        ("TRANSFER", execution_dates[2], execution_dates[3]),
    ):
        _, generated_targets, generated_models, _ = build_candidate_targets_for_segment(
            dataset,
            segment_id=segment_id,
            execution_start=segment_start,
            execution_end=segment_end,
            train_start_session="2018-02-01",
            columns=columns,
            specs=specs,
            provenance=provenance,
        )
        staged_targets.extend(generated_targets)
        staged_models.extend(generated_models)
    coverage = _reconcile_model_target_coverage(staged_models, staged_targets)
    assert coverage["expected_model_record_count"] == len(staged_models)
    with pytest.raises(ValueError, match="model-to-target coverage is incomplete"):
        _reconcile_model_target_coverage(staged_models[:-1], staged_targets)
    forged_provenance = json.loads(json.dumps(staged_models))
    forged_provenance[0]["prompt_hash"] = "e" * 64
    with pytest.raises(ValueError, match="provenance differs from locked evidence"):
        _rebuild_staged_model_and_target_ledgers(
            r5_module._dataframe_records(dataset),
            forged_provenance,
            staged_targets,
            specs,
            validation_contract,
            columns,
            expected_provenance=provenance,
        )
    rebuilt = _rebuild_staged_model_and_target_ledgers(
        r5_module._dataframe_records(dataset),
        staged_models,
        staged_targets,
        specs,
        validation_contract,
        columns,
        expected_provenance=provenance,
    )
    assert rebuilt["full_model_ledger_rebuilt"] is True
    assert rebuilt["full_target_ledger_rebuilt"] is True
    assert rebuilt["rebuilt_target_row_count"] == len(staged_targets)


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
        expected_cost_bps_by_view={"primary_10bps": 10.0},
    )

    assert result["pass"] is False
    assert any("event_ledger_empty" in failure for failure in result["failures"])


def test_cost_reconciliation_rejects_one_bps_ledger_labeled_primary_10bps() -> None:
    sessions = pd.DatetimeIndex(["2026-01-02", "2026-01-05", "2026-01-06"])
    marks = pd.DataFrame(
        {"BIL": [100.0, 100.01, 100.02], "SPY": [100.0, 101.0, 102.0]},
        index=sessions,
    )
    targets = pd.DataFrame(
        [{"BIL": 0.0, "SPY": 1.0}],
        index=pd.DatetimeIndex(["2026-01-02"]),
    )
    simulation = simulate_exact_target_portfolio(
        marks,
        targets,
        cost_bps=1.0,
        start="2026-01-02",
        end="2026-01-06",
    )
    aggregate = {candidate_id: {"primary_10bps": simulation} for candidate_id in SPEC_PATHS}
    segments = {candidate_id: {"S1": {"primary_10bps": simulation}} for candidate_id in SPEC_PATHS}

    result = _cost_reconciliation(
        aggregate,
        segments,
        [{"segment_id": "S1", "start": "2026-01-02"}],
        expected_cost_bps_by_view={"primary_10bps": 10.0},
    )

    assert result["pass"] is False
    assert any("event_cost_bps_mismatch" in failure for failure in result["failures"])
    assert any(
        "event_cost_fraction_bps_notional_mismatch" in failure for failure in result["failures"]
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("maximum_event_reconciliation_error", 0.5),
        ("maximum_equity_chain_error", 0.5),
        ("pass", False),
        ("aggregate_primary_full_L1", 99.0),
        ("reset_difference_segment_sum_minus_aggregate", 99.0),
        ("aggregate_boundary_full_L1", {"entry": 99.0, "terminal": 99.0}),
    ],
)
def test_independent_cost_reconciliation_rejects_coordinated_publication_mutation(
    field: str,
    replacement: object,
) -> None:
    recomputed = {
        "schema_version": 1,
        "maximum_event_reconciliation_error": 0.0,
        "maximum_equity_chain_error": 0.0,
        "pass": True,
        "rows": [
            {
                "candidate_id": "R5D01",
                "aggregate_primary_full_L1": 2.0,
                "reset_difference_segment_sum_minus_aggregate": 0.0,
                "aggregate_boundary_full_L1": {"entry": 1.0, "terminal": 1.0},
            }
        ],
    }
    coordinated = json.loads(json.dumps(recomputed))
    if field in coordinated:
        coordinated[field] = replacement
    else:
        coordinated["rows"][0][field] = replacement

    with pytest.raises(ValueError, match="independent locked-mark replay"):
        r5_module._require_independent_cost_reconciliation(
            coordinated,
            json.loads(json.dumps(coordinated)),
            recomputed,
        )


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


def test_r5_state_classifier_never_treats_partial_computation_as_recoverable(
    tmp_path: Path,
) -> None:
    output = tmp_path / R5_ITERATION_PATH
    output.mkdir(parents=True)
    assert r5_module.classify_multiasset_forward_multimodal_r5_state(tmp_path)["state"] == (
        "not_started"
    )

    (output / "evaluation-attempt.json").write_text('{"attempt":1}\n', encoding="utf-8")
    assert r5_module.classify_multiasset_forward_multimodal_r5_state(tmp_path)["state"] == (
        "reserved_attempt_terminal_abort"
    )

    stage = output / ".r5-evaluation-stage-deadbeefdeadbeef"
    stage.mkdir()
    (stage / "partial.json").write_text("{}\n", encoding="utf-8")
    assert r5_module.classify_multiasset_forward_multimodal_r5_state(tmp_path)["state"] == (
        "incomplete_stage_terminal_abort"
    )

    (stage / "partial.json").unlink()
    for filename in r5_module.R5_EVALUATION_FILENAMES.values():
        path = stage / filename
        path.write_text("{}\n", encoding="utf-8")
        path.chmod(0o400)
    stage.chmod(0o500)
    state = r5_module.classify_multiasset_forward_multimodal_r5_state(tmp_path)
    assert state["state"] == "sealed_stage_publication_recovery_only"
    assert state["publication_only_recovery_allowed"] is True
    assert state["price_recomputation_allowed"] is False
    stage.chmod(0o700)


def test_r5_recovery_only_clears_stale_publish_marker(tmp_path: Path) -> None:
    stale = tmp_path / ".evaluation-run-publish.lock"
    stale.write_text("pid=99999999\n", encoding="ascii")
    r5_module._clear_stale_r5_publish_marker(stale)
    assert not stale.exists()

    live = tmp_path / ".evaluation-run-publish.lock"
    live.write_text(f"pid={os.getpid()}\n", encoding="ascii")
    with pytest.raises(ValueError, match="live process"):
        r5_module._clear_stale_r5_publish_marker(live)
    assert live.exists()


def test_r5_lock_custody_binds_source_snapshot_and_locked_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    custody = tmp_path / "custody"
    output = project / R5_ITERATION_PATH
    lock_stage = output / ".r5-lock-stage"
    snapshot = project / "data/research/snapshot"
    lock_stage.mkdir(parents=True)
    snapshot.mkdir(parents=True)

    artifact = output / "contract.json"
    spec = project / "strategy_specs/drafts/r5.yaml"
    runner = project / "open_composer/research/r5.py"
    for path, content in (
        (artifact, "contract\n"),
        (spec, "name: r5\n"),
        (runner, "RUNNER = True\n"),
        (snapshot / "snapshot-manifest.json", "{}\n"),
        (snapshot / "SPY.csv", "timestamp,open\n2026-01-02,1\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for filename, content in (
        ("preregistration-lock.json", '{"lock":1}\n'),
        ("runner-lock.json", '{"runner":1}\n'),
        ("lock-anchor.json", '{"anchor":1}\n'),
    ):
        (lock_stage / filename).write_text(content, encoding="utf-8")

    def binding(path: Path) -> dict[str, object]:
        contents = path.read_bytes()
        return {
            "path": path.relative_to(project).as_posix(),
            "sha256": hashlib.sha256(contents).hexdigest(),
            "size_bytes": len(contents),
        }

    operator_hash = "d" * 64
    record = r5_module._write_r5_lock_custody(
        root=project,
        custody_dir=custody.resolve(),
        lock_stage=lock_stage,
        preregistration={
            "artifacts": [binding(artifact), binding(snapshot / "snapshot-manifest.json")],
            "specs": [
                {
                    "path": spec.relative_to(project).as_posix(),
                    "file_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
                }
            ],
        },
        runner={"files": [binding(runner)]},
        lock_anchor={"operator_lock_anchor_sha256": operator_hash},
        manifest_path=snapshot / "snapshot-manifest.json",
    )
    verified = r5_module._verify_r5_lock_custody(
        root=project,
        custody_dir=custody.resolve(),
        lock_anchor_sha256=operator_hash,
    )

    assert record.receipt_sha256 == verified.receipt_sha256
    paths = {row["path"] for row in record.payload["entries"]}
    assert "data/research/snapshot/SPY.csv" in paths
    assert (R5_ITERATION_PATH / "lock-set/lock-anchor.json").as_posix() in paths


def test_evaluation_anchor_is_one_way_exclusive_and_sealed(tmp_path: Path) -> None:
    output = tmp_path / R5_ITERATION_PATH
    lock_dir = output / "lock-set"
    stage = output / ".stage"
    lock_dir.mkdir(parents=True)
    stage.mkdir()
    preregistration = lock_dir / "preregistration-lock.json"
    runner = lock_dir / "runner-lock.json"
    lock_anchor = lock_dir / "lock-anchor.json"
    attempt = output / "evaluation-attempt.json"
    receipt = stage / "evaluation-receipt.json"
    preregistration.write_text('{"lock":"preregistration"}\n', encoding="utf-8")
    runner.write_text('{"lock":"runner"}\n', encoding="utf-8")
    lock_anchor.write_text(
        json.dumps({"operator_lock_anchor_sha256": "a" * 64}) + "\n",
        encoding="utf-8",
    )
    attempt.write_text('{"attempt":1}\n', encoding="utf-8")
    receipt.write_text('{"receipt":1}\n', encoding="utf-8")
    receipt_destination = output / "evaluation-run/evaluation-receipt.json"
    anchor_destination = output / "evaluation-run/evaluation-anchor.json"

    anchor = _evaluation_anchor_payload(
        root=tmp_path,
        receipt_source=receipt,
        receipt_destination=receipt_destination,
        anchor_destination=anchor_destination,
        preregistration_lock_path=preregistration,
        runner_lock_path=runner,
        lock_anchor_path=lock_anchor,
        evaluation_attempt_path=attempt,
    )
    anchor_path = stage / "evaluation-anchor.json"
    _write_json_exclusive_readonly(anchor_path, anchor)

    assert anchor["receipt"]["path"] == receipt_destination.relative_to(tmp_path).as_posix()
    assert anchor_path.stat().st_mode & 0o222 == 0
    with pytest.raises(FileExistsError):
        _write_json_exclusive_readonly(anchor_path, anchor)

    original_operator_sha256 = anchor["operator_evaluation_anchor_sha256"]
    receipt.write_text('{"receipt":2}\n', encoding="utf-8")
    changed = _evaluation_anchor_payload(
        root=tmp_path,
        receipt_source=receipt,
        receipt_destination=receipt_destination,
        anchor_destination=anchor_destination,
        preregistration_lock_path=preregistration,
        runner_lock_path=runner,
        lock_anchor_path=lock_anchor,
        evaluation_attempt_path=attempt,
    )
    assert changed["receipt"]["sha256"] != anchor["receipt"]["sha256"]
    assert changed["operator_evaluation_anchor_sha256"] != original_operator_sha256

    _seal_evidence_directory(stage)
    assert stage.stat().st_mode & 0o222 == 0
    assert all(path.stat().st_mode & 0o222 == 0 for path in stage.iterdir())


def test_evaluation_attempt_is_exclusive_and_permanent(tmp_path: Path) -> None:
    output = tmp_path / R5_ITERATION_PATH
    output.mkdir(parents=True)
    preflight = {
        "operator_lock_anchor_sha256": "a" * 64,
        "preregistration_lock_sha256": "b" * 64,
        "runner_lock_sha256": "c" * 64,
        "data_manifest_sha256": "d" * 64,
        "lock_custody_receipt_sha256": "e" * 64,
        "lock_custody_bundle_sha256": "f" * 64,
    }

    binding = _reserve_evaluation_attempt(tmp_path, preflight)

    assert binding["path"].endswith("evaluation-attempt.json")
    assert len(binding["sha256"]) == 64
    with pytest.raises(ValueError, match="already exists"):
        _reserve_evaluation_attempt(tmp_path, preflight)
