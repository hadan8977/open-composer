from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.high_beta_sleeve_ensemble_r1 import (
    EMBARGO_SESSIONS,
    LABEL_MAX_SPAN_SESSIONS,
    MINIMUM_CALIBRATION_LABELS,
    MINIMUM_FIT_LABELS,
    MODEL_FEATURES,
    _calibration_gate_pass,
    _fit_logistic,
    _fit_ridge,
    _month_end_positions,
    _paired_target_stream_log_wealth_value,
    _policy_diagnostics,
    _policy_value,
    build_candidate_targets,
    build_deterministic_targets,
    build_monthly_dataset,
    load_and_validate_specs,
    runtime_contract_from_specs,
    training_rows_for_decision,
)
from open_composer.research.pit_semantic_theme_r11 import R11PricePanel

ROOT = Path(__file__).resolve().parents[1]
SYMBOLS = ["QQQ", "TQQQ", "BIL", "SPY", "SMH"]


def _synthetic_panel(session_count: int = 440) -> R11PricePanel:
    sessions = pd.bdate_range("2020-01-02", periods=session_count)
    step = np.arange(session_count, dtype=float)
    data = {
        "QQQ": 100.0 * np.exp(0.0005 * step + 0.015 * np.sin(step / 23.0)),
        "TQQQ": 50.0 * np.exp(0.0012 * step + 0.04 * np.sin(step / 17.0)),
        "BIL": 90.0 * np.exp(0.00008 * step),
        "SPY": 110.0 * np.exp(0.00035 * step),
        "SMH": 80.0 * np.exp(0.0007 * step + 0.02 * np.sin(step / 19.0)),
    }
    opens = pd.DataFrame(data, index=sessions)
    closes = opens.mul(1.0 + 0.001 * np.sin(step / 7.0), axis=0)
    lows = np.minimum(opens, closes) * 0.995
    volume = pd.DataFrame(1_000_000.0, index=sessions, columns=SYMBOLS)
    return R11PricePanel(
        open=opens.loc[:, SYMBOLS],
        low=lows.loc[:, SYMBOLS],
        close=closes.loc[:, SYMBOLS],
        volume=volume,
        metadata={"scope": "synthetic_only"},
    )


def _training_frame(count: int, *, binary: bool = False) -> pd.DataFrame:
    rows = []
    for index in range(count):
        label = float(index % 2) if binary else 0.002 * math.sin(index / 3.0)
        rows.append(
            {
                "decision_position": 30 * index,
                "decision_session": (pd.Timestamp("2018-01-02") + pd.offsets.BDay(30 * index))
                .date()
                .isoformat(),
                "label_end_position": 30 * index + 21,
                "label_end_session": (pd.Timestamp("2018-01-02") + pd.offsets.BDay(30 * index + 21))
                .date()
                .isoformat(),
                "m01_policy_value": label,
                "m02_path_survival": label,
                **{
                    feature: 0.01 * math.sin(index + feature_index)
                    for feature_index, feature in enumerate(MODEL_FEATURES)
                },
            }
        )
    return pd.DataFrame(rows)


def _runtime_contract():
    return runtime_contract_from_specs(load_and_validate_specs(ROOT))


def _copy_r1_contract_dependencies(tmp_path: Path) -> None:
    """Copy non-iteration bindings required by the fail-closed runtime contract."""
    for relative in (
        "schemas/high_beta_sleeve_ensemble_r1_feature_packet.schema.json",
        "reports/research/us_high_beta_sleeve_ensemble_r1-factor-library.json",
        "reports/harness/source_cards/us_high_beta_sleeve_ensemble_r1.jsonl",
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _copy_r1_runtime_tree(tmp_path: Path) -> Path:
    iteration = tmp_path / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    shutil.copytree(
        ROOT / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1",
        iteration,
    )
    for spec_path in (ROOT / "strategy_specs/drafts").glob(
        "us_high_beta_sleeve_ensemble_r1_*.yaml"
    ):
        target = tmp_path / spec_path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec_path, target)
    _copy_r1_contract_dependencies(tmp_path)
    return iteration


def _rewrite_manifest_contract_hash(iteration: Path, category: str, contract_id: str) -> None:
    manifest_path = iteration / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract_path = iteration / manifest["contracts"][category][contract_id]["path"].split("/")[-1]
    manifest["contracts"][category][contract_id]["sha256"] = hashlib.sha256(
        contract_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_runtime_contract_sha_changes_when_bound_contract_changes(tmp_path: Path) -> None:
    iteration = tmp_path / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    source = ROOT / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    shutil.copytree(source, iteration)
    for spec_path in (ROOT / "strategy_specs/drafts").glob(
        "us_high_beta_sleeve_ensemble_r1_*.yaml"
    ):
        target = tmp_path / spec_path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec_path, target)
    _copy_r1_contract_dependencies(tmp_path)
    contract = runtime_contract_from_specs(load_and_validate_specs(tmp_path), root=tmp_path)
    payload = json.loads((iteration / "cost-contract.json").read_text())
    payload["impact_model"] = "mutated_for_test"
    (iteration / "cost-contract.json").write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = iteration / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["contracts"]["costs"]["hbs_r1_costs_v1"]["sha256"] = hashlib.sha256(
        (iteration / "cost-contract.json").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    changed = runtime_contract_from_specs(load_and_validate_specs(tmp_path), root=tmp_path)
    assert changed.sha256 != contract.sha256
    assert changed.cost_contract["impact_model"] == "mutated_for_test"


def test_runtime_contract_rejects_factor_expression_mutation(tmp_path: Path) -> None:
    iteration = tmp_path / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    source = ROOT / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    shutil.copytree(source, iteration)
    for spec_path in (ROOT / "strategy_specs/drafts").glob(
        "us_high_beta_sleeve_ensemble_r1_*.yaml"
    ):
        target = tmp_path / spec_path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec_path, target)
    _copy_r1_contract_dependencies(tmp_path)
    payload = json.loads((iteration / "feature-contract.json").read_text())
    payload["quant_features"]["expressions"]["qqq_trend_gap_200"] = "close / sma(close, 199) - 1"
    (iteration / "feature-contract.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        ValueError, match="feature expression contract|factor|manifest contract hash"
    ):
        runtime_contract_from_specs(load_and_validate_specs(tmp_path), root=tmp_path)


def test_runtime_contract_rejects_sleeve_semantic_mutation(tmp_path: Path) -> None:
    iteration = tmp_path / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    source = ROOT / "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1"
    shutil.copytree(source, iteration)
    for spec_path in (ROOT / "strategy_specs/drafts").glob(
        "us_high_beta_sleeve_ensemble_r1_*.yaml"
    ):
        target = tmp_path / spec_path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec_path, target)
    _copy_r1_contract_dependencies(tmp_path)
    d01 = tmp_path / "strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_d01.yaml"
    text = d01.read_text(encoding="utf-8").replace("capital_weight: 0.5", "capital_weight: 0.55", 1)
    d01.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="hash|sleeve"):
        load_and_validate_specs(tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("role", "mutated-role", "role"),
        ("method", "mutated-method", "method"),
        ("fallback", "S1M02", "fallback"),
        ("path", "mutated-path", "path"),
        ("promotion_eligible", False, "promotion_eligible"),
    ],
)
def test_runtime_contract_rejects_candidate_manifest_semantic_mutation(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    iteration = _copy_r1_runtime_tree(tmp_path)
    manifest_path = iteration / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["candidates"][0][field] = value
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        runtime_contract_from_specs(load_and_validate_specs(tmp_path), root=tmp_path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("path", "path binding"),
        ("sha256", "hash binding"),
        ("factor_count", "factor_count"),
    ],
)
def test_runtime_contract_rejects_factor_artifact_binding_mutation(
    tmp_path: Path, mutation: str, message: str
) -> None:
    iteration = _copy_r1_runtime_tree(tmp_path)
    feature_path = iteration / "feature-contract.json"
    feature = json.loads(feature_path.read_text(encoding="utf-8"))
    if mutation == "path":
        feature["factor_library"]["path"] = "reports/research/other-factor-library.json"
    elif mutation == "sha256":
        feature["factor_library"]["sha256"] = "0" * 64
    else:
        artifact_path = (
            tmp_path / "reports/research/us_high_beta_sleeve_ensemble_r1-factor-library.json"
        )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        artifact["factor_count"] = 2
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        feature["factor_library"]["sha256"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    feature_path.write_text(json.dumps(feature), encoding="utf-8")
    _rewrite_manifest_contract_hash(iteration, "features", "hbs_r1_features_v1")

    with pytest.raises(ValueError, match=message):
        runtime_contract_from_specs(load_and_validate_specs(tmp_path), root=tmp_path)


def test_runtime_contract_rejects_unresolvable_factor_source_claim(tmp_path: Path) -> None:
    _copy_r1_runtime_tree(tmp_path)
    source_path = tmp_path / "reports/harness/source_cards/us_high_beta_sleeve_ensemble_r1.jsonl"
    rows = [
        row
        for row in source_path.read_text(encoding="utf-8").splitlines()
        if "hbs_r1_time_series_momentum_paper" not in row
    ]
    source_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not verified"):
        runtime_contract_from_specs(load_and_validate_specs(tmp_path), root=tmp_path)


def test_calibration_gate_requires_observations_and_beats_raw() -> None:
    contract = _runtime_contract()
    assert not _calibration_gate_pass(
        observation_count=2,
        calibrated_brier=0.01,
        raw_brier=0.02,
        contract=contract,
    )
    assert not _calibration_gate_pass(
        observation_count=3,
        calibrated_brier=0.02,
        raw_brier=0.02,
        contract=contract,
    )
    assert _calibration_gate_pass(
        observation_count=3,
        calibrated_brier=0.01,
        raw_brier=0.02,
        contract=contract,
    )


def test_month_end_positions_use_last_completed_session() -> None:
    sessions = pd.DatetimeIndex(
        pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"])
    )

    assert _month_end_positions(sessions) == [1, 3]


def test_dataset_uses_close_then_next_open_and_next_review_label_endpoint() -> None:
    panel = _synthetic_panel()
    contract = _runtime_contract()
    dataset = build_monthly_dataset(panel, contract)
    eligible = dataset.dropna(subset=["qqq_momentum_252_skip21", "label_end_position"])
    row = eligible.iloc[0]
    next_row = dataset.iloc[int(row.name) + 1]

    assert int(row["execution_position"]) == int(row["decision_position"]) + 1
    assert (
        row["execution_session"]
        == panel.open.index[int(row["execution_position"])].date().isoformat()
    )
    assert int(row["label_end_position"]) == int(next_row["execution_position"])
    assert row["label_end_session"] == next_row["execution_session"]
    assert 1 <= int(row["label_span_sessions"]) <= LABEL_MAX_SPAN_SESSIONS

    targets = build_deterministic_targets(panel, dataset, anchor_weight=0.5)
    execution = pd.Timestamp(row["execution_session"])
    decision = pd.Timestamp(row["decision_session"])
    assert execution in targets.index
    assert decision not in targets.index
    assert math.isclose(float(targets.loc[execution].sum()), 1.0, abs_tol=1e-12)


def test_policy_value_separately_charges_override_and_rejoin() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=2)
    opens = pd.DataFrame(
        {"TQQQ": [100.0, 100.0], "BIL": [100.0, 100.0]},
        index=sessions,
    )

    value = _policy_value(
        opens,
        start_position=0,
        end_position=1,
        pretrade_weights={"TQQQ": 0.5, "BIL": 0.5},
        baseline_target={"TQQQ": 0.5, "BIL": 0.5},
        alternative_target={"TQQQ": 1.0, "BIL": 0.0},
        rejoin_target={"TQQQ": 0.5, "BIL": 0.5},
        cost_bps=20.0,
    )

    assert math.isclose(value, math.log(0.998**2), rel_tol=0, abs_tol=1e-12)


def test_training_rows_require_mature_label_plus_embargo() -> None:
    frame = _training_frame(8)
    contract = _runtime_contract()
    frame.loc[0, ["decision_position", "label_end_position"]] = [100, 176]
    frame.loc[1, ["decision_position", "label_end_position"]] = [110, 177]

    selected = training_rows_for_decision(
        frame,
        decision_position=200,
        label_name="m01_policy_value",
        model_contract=contract.m01,
    )

    assert EMBARGO_SESSIONS == 24
    assert 176 in selected["label_end_position"].tolist()
    assert 177 not in selected["label_end_position"].tolist()


def test_ridge_and_logistic_fail_closed_until_calibration_is_eligible() -> None:
    contract = _runtime_contract()
    minimum = MINIMUM_FIT_LABELS + MINIMUM_CALIBRATION_LABELS
    too_short = _training_frame(minimum - 1)
    assert (
        _fit_ridge(
            too_short,
            decision_session="2024-01-31",
            provenance={},
            model_contract=contract.m01,
        )
        is None
    )

    ridge = _fit_ridge(
        _training_frame(minimum),
        decision_session="2024-01-31",
        provenance={},
        model_contract=contract.m01,
    )
    assert ridge is not None
    assert ridge.record["fit_row_count"] == MINIMUM_FIT_LABELS
    assert ridge.record["calibration_row_count"] == MINIMUM_CALIBRATION_LABELS
    assert ridge.record["quantile_method"] == "higher"

    one_class = _training_frame(36, binary=True)
    one_class["m02_path_survival"] = 1.0
    assert (
        _fit_logistic(
            one_class,
            decision_session="2024-01-31",
            provenance={},
            model_contract=contract.m02,
        )
        is None
    )

    logistic = _fit_logistic(
        _training_frame(36, binary=True),
        decision_session="2024-01-31",
        provenance={},
        model_contract=contract.m02,
    )
    assert logistic is not None
    assert logistic.calibrator is not None
    assert logistic.record["calibration_method"] == "chronological_platt_scaling"
    assert logistic.record["fit_positive_count"] >= 5
    assert logistic.record["calibration_negative_count"] >= 2


def test_unavailable_models_preserve_exact_d01_targets_and_weight_conservation() -> None:
    panel = _synthetic_panel()
    contract = _runtime_contract()
    dataset = build_monthly_dataset(panel, contract)
    folds = [
        {
            "fold_id": "F1",
            "test_start": panel.open.index[-100].date().isoformat(),
            "test_end": panel.open.index[-1].date().isoformat(),
        }
    ]

    candidates, _, _, predictions = build_candidate_targets(panel, dataset, folds, {}, contract)

    assert candidates["S1M01"].equals(candidates["S1D01"])
    assert candidates["S1M02"].equals(candidates["S1D01"])
    for targets in candidates.values():
        assert np.allclose(targets.sum(axis=1).to_numpy(dtype=float), 1.0, atol=1e-12)
        assert (targets.to_numpy(dtype=float) >= 0).all()
    fallback_rows = [row for row in predictions if row["fallback_used"]]
    assert fallback_rows
    assert all(row["fallback_target_identity"] for row in fallback_rows)
    assert all(row["model_unavailable"] for row in fallback_rows)
    assert not any(row["normal_noop"] for row in fallback_rows)


def test_policy_diagnostics_do_not_count_normal_noop_as_fallback() -> None:
    contract = _runtime_contract()
    records = []
    for fold_number in range(1, contract.fold_count + 1):
        records.append(
            {
                "candidate_id": "S1M02",
                "fold_id": f"F{fold_number}",
                "override": False,
                "prediction": 0.8,
                "uncalibrated_prediction": 0.7,
                "realized_path_survival": 1.0,
                "training_base_rate": 0.5,
                "lower_bound": None,
                "local_counterfactual_policy_value": None,
                "model_id": f"model-{fold_number}",
                "model_unavailable": False,
                "abstention_used": False,
                "fallback_used": False,
                "normal_noop": True,
                "fallback_target_identity": True,
                "fit_row_count": 18,
                "calibration_row_count": 6,
                "fit_positive_count": 5,
                "fit_negative_count": 5,
                "calibration_positive_count": 2,
                "calibration_negative_count": 2,
                "calibration_method": "chronological_platt_scaling",
            }
        )
    folds = [
        {
            "fold_id": f"F{fold_number}",
            "paired_S1D01_realized_log_wealth_value": 0.0,
        }
        for fold_number in range(1, contract.fold_count + 1)
    ]

    diagnostics = _policy_diagnostics(records, "S1M02", folds, 0.0, contract)

    assert diagnostics["normal_noop_count"] == contract.fold_count
    assert diagnostics["fallback_count"] == 0
    assert diagnostics["model_unavailable_count"] == 0
    assert diagnostics["abstention_count"] == 0
    assert diagnostics["uncertainty_fallback_count"] == 0


def test_stateful_paired_value_does_not_recharge_continuous_override() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=5)
    opens = pd.DataFrame(
        {"TQQQ": [100.0] * 5, "BIL": [100.0] * 5},
        index=sessions,
    )
    baseline = pd.DataFrame(
        [{"TQQQ": 0.5, "BIL": 0.5}] * 3,
        index=sessions[:3],
    )
    continuous = pd.DataFrame(
        [
            {"TQQQ": 1.0, "BIL": 0.0},
            {"TQQQ": 1.0, "BIL": 0.0},
            {"TQQQ": 0.5, "BIL": 0.5},
        ],
        index=sessions[:3],
    )
    value = _paired_target_stream_log_wealth_value(
        opens,
        baseline,
        continuous,
        start=sessions[0],
        end=sessions[-1],
        cost_bps=20.0,
    )
    assert math.isclose(value, math.log(0.998), rel_tol=0, abs_tol=1e-12)


def test_stateful_paired_value_charges_each_real_state_switch_once() -> None:
    sessions = pd.bdate_range("2024-01-02", periods=5)
    opens = pd.DataFrame(
        {"TQQQ": [100.0] * 5, "BIL": [100.0] * 5},
        index=sessions,
    )
    baseline = pd.DataFrame(
        [{"TQQQ": 0.5, "BIL": 0.5}] * 3,
        index=sessions[:3],
    )
    switching = pd.DataFrame(
        [
            {"TQQQ": 1.0, "BIL": 0.0},
            {"TQQQ": 0.5, "BIL": 0.5},
            {"TQQQ": 1.0, "BIL": 0.0},
        ],
        index=sessions[:3],
    )
    value = _paired_target_stream_log_wealth_value(
        opens,
        baseline,
        switching,
        start=sessions[0],
        end=sessions[-1],
        cost_bps=20.0,
    )
    assert math.isclose(value, math.log(0.998**2), rel_tol=0, abs_tol=1e-12)


def test_generated_specs_bind_fixed_primary_and_scheduled_ml_contracts() -> None:
    specs = load_and_validate_specs(ROOT)

    assert set(specs) == {
        "S1D01",
        "S1D02",
        "S1M01",
        "S1M02",
        "S1L01",
        "S1C01",
        "S1F01",
        "S1P01",
        "S1D03",
        "S1D04",
    }
    assert specs["S1D01"].research_design is not None
    assert specs["S1D01"].research_design.parameter_space["parameter_search"] == [False]
    assert specs["S1M01"].model is not None
    assert specs["S1M01"].model.label.type == "net_incremental_policy_value"
    assert specs["S1M01"].model.label.horizon_bars is None
    assert specs["S1M02"].model is not None
    assert specs["S1M02"].model.action is not None
    assert specs["S1M02"].model.action.portfolio_weight_delta == 0.25
