from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.pdr_ml_gate import (
    PDRMLGateConfig,
    build_pdr_ml_gate_label,
    pdr_ml_gate_from_token,
    pdr_ml_gate_search_space,
    register_pdr_ml_gate_predictions,
    train_pdr_ml_gate_trials,
    validate_pdr_ml_gate_training_config,
)
from open_composer.research.post_drawdown_reentry_router import (
    post_drawdown_reentry_params_from_label,
)
from open_composer.research.router_common import load_daily_dataset
from tests.test_pdr_router_parity import (
    BASE_LABEL,
    OVERLAY_LABEL,
    ROOT,
    SYMBOLS,
    _daily_rows,
    _fixture_dataset,
    _spec,
)

GATED_LABEL = OVERLAY_LABEL.replace("_delay30_base[", "_delay30_mlgate_h10_t2_p70_base[")


def test_pdr_ml_gate_label_roundtrip_and_search_space() -> None:
    params = hybrid_params_from_label(GATED_LABEL)

    assert params.ml_gate == PDRMLGateConfig(
        horizon_bars=10,
        threshold_return_pct=2.0,
        probability_threshold=0.7,
    )
    assert params.label == GATED_LABEL
    assert pdr_ml_gate_from_token("mlgate_h20_t0_p80") == PDRMLGateConfig(20, 0.0, 0.8)
    assert len(pdr_ml_gate_search_space()) == 12
    assert {item.horizon_bars for item in pdr_ml_gate_search_space()} == {10, 20}
    assert {item.threshold_return_pct for item in pdr_ml_gate_search_space()} == {0.0, 2.0}
    assert {item.probability_threshold for item in pdr_ml_gate_search_space()} == {
        0.6,
        0.7,
        0.8,
    }


def test_pdr_ml_gate_path_survival_roundtrip_and_search_space() -> None:
    config = pdr_ml_gate_from_token("mlgate2_h20_dd12_p70")

    assert config == PDRMLGateConfig(
        horizon_bars=20,
        threshold_return_pct=0.0,
        probability_threshold=0.7,
        label_kind="path_survival",
        max_drawdown_pct=12.0,
        min_terminal_return_pct=0.0,
    )
    assert config.token == "mlgate2_h20_dd12_p70"
    assert len(pdr_ml_gate_search_space(label_kind="path_survival")) == 8
    assert {item.max_drawdown_pct for item in pdr_ml_gate_search_space("path_survival")} == {
        8.0,
        12.0,
    }
    assert {item.probability_threshold for item in pdr_ml_gate_search_space("path_survival")} == {
        0.6,
        0.7,
    }


def test_pdr_ml_gate_path_survival_label_uses_terminal_and_path_drawdown() -> None:
    dataset = _fixture_dataset()
    base = dataset.frame["TQQQ_open"].iloc[261]
    dataset.frame.loc[261:266, "TQQQ_open"] = [
        base,
        base * 1.00,
        base * 0.93,
        base * 0.96,
        base * 1.01,
        base * 1.02,
    ]
    dataset.frame.loc[267:272, "TQQQ_open"] = [
        base * 1.02,
        base * 1.03,
        base * 0.90,
        base * 0.95,
        base * 1.02,
        base * 1.03,
    ]
    config = PDRMLGateConfig(
        horizon_bars=5,
        threshold_return_pct=0.0,
        probability_threshold=0.6,
        label_kind="path_survival",
        max_drawdown_pct=8.0,
        min_terminal_return_pct=0.0,
    )

    label = build_pdr_ml_gate_label(dataset, config)

    assert label.iloc[260] == 1.0
    assert label.iloc[266] == 0.0
    assert label.iloc[-1] != label.iloc[-1]


def test_pdr_ml_gate_rejects_embargo_shorter_than_horizon() -> None:
    with pytest.raises(ValueError, match="embargo_bars >= horizon_bars"):
        validate_pdr_ml_gate_training_config(horizon_bars=10, embargo_bars=9)


def test_pdr_ml_gate_missing_predictions_equals_baseline_fixture() -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    baseline = hybrid_params_from_label(OVERLAY_LABEL)
    gated = hybrid_params_from_label(GATED_LABEL)

    baseline_rows = _daily_rows(
        spec, dataset, baseline, _effective_lookback(baseline), len(dataset.dates) - 1
    )
    gated_rows = _daily_rows(
        spec, dataset, gated, _effective_lookback(gated), len(dataset.dates) - 1
    )

    assert gated_rows == baseline_rows


def test_pdr_ml_gate_ignores_non_hard_stress_high_prediction_fixture() -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    baseline = hybrid_params_from_label(OVERLAY_LABEL)
    gated = hybrid_params_from_label(GATED_LABEL)
    index = _effective_lookback(gated)
    register_pdr_ml_gate_predictions(dataset, gated.ml_gate, {dataset.dates[index]: 0.99})

    base_snapshot = hybrid_target_weight_snapshot(spec, dataset, baseline, index)
    gated_snapshot = hybrid_target_weight_snapshot(spec, dataset, gated, index)

    assert base_snapshot.state != "hard_stress_defensive"
    assert gated_snapshot == base_snapshot


def test_pdr_ml_gate_releases_only_hard_stress_when_oos_prediction_exists() -> None:
    data_path = ROOT / "data/research/longbridge_adjusted_daily/qqq_daily_longbridge_adjusted.csv"
    if not data_path.exists():
        pytest.skip("local Longbridge materialized data is absent")

    spec = _spec()
    dataset = load_daily_dataset(
        spec=spec,
        root=ROOT,
        symbols=SYMBOLS,
        data_source="longbridge",
        feed=None,
        start="2012-01-03",
        end="2026-05-22",
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    baseline = hybrid_params_from_label(OVERLAY_LABEL)
    gated = hybrid_params_from_label(GATED_LABEL)
    hard_index = next(
        index
        for index in range(_effective_lookback(baseline), len(dataset.dates) - 1)
        if hybrid_target_weight_snapshot(spec, dataset, baseline, index).state
        == "hard_stress_defensive"
    )
    register_pdr_ml_gate_predictions(dataset, gated.ml_gate, {dataset.dates[hard_index]: 0.99})

    base_snapshot = hybrid_target_weight_snapshot(spec, dataset, baseline, hard_index)
    gated_snapshot = hybrid_target_weight_snapshot(spec, dataset, gated, hard_index)

    assert base_snapshot.state == "hard_stress_defensive"
    assert base_snapshot.weights == {"GLD": 1.0}
    assert "ml_release" in gated_snapshot.state
    assert gated_snapshot.weights != base_snapshot.weights


def test_pdr_ml_gate_training_writes_exactly_twelve_trial_ledger_rows(
    sample_workspace: Path,
) -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    summary = train_pdr_ml_gate_trials(
        spec,
        dataset,
        post_drawdown_reentry_params_from_label(BASE_LABEL),
        root=sample_workspace,
        window_bars=260,
        test_window_bars=30,
        retrain_every_bars=30,
        seed=7,
        hyperparameters={"n_estimators": 5, "min_child_samples": 5},
    )
    ledger_path = Path(summary["trial_ledger_path"])
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 12
    assert {row["family"] for row in rows} == {"pdr_defensive_exit_ml_gate"}
    assert {row["config"]["token"] for row in rows} == {
        config.token for config in pdr_ml_gate_search_space()
    }
    for row in rows:
        assert row["purged_embargo"]["embargo_bars"] == row["purged_embargo"]["horizon_bars"]


def test_pdr_ml_gate_path_survival_training_writes_exactly_eight_trial_ledger_rows(
    sample_workspace: Path,
) -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    summary = train_pdr_ml_gate_trials(
        spec,
        dataset,
        post_drawdown_reentry_params_from_label(BASE_LABEL),
        root=sample_workspace,
        window_bars=260,
        test_window_bars=30,
        retrain_every_bars=30,
        seed=7,
        hyperparameters={"n_estimators": 5, "min_child_samples": 5},
        label_kind="path_survival",
    )
    ledger_path = Path(summary["trial_ledger_path"])
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 8
    assert {row["config"]["label_kind"] for row in rows} == {"path_survival"}
    assert {row["config"]["token"] for row in rows} == {
        config.token for config in pdr_ml_gate_search_space("path_survival")
    }
    assert {row["positive_label_rate"] is None for row in rows} <= {False, True}
