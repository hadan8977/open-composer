from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import open_composer.research.pit_semantic_theme_r24 as r24
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE, R11PricePanel
from open_composer.research.pit_semantic_theme_r24 import (
    EFFECTIVE_TRIAL_COUNT,
    MINIMUM_POLICY_OVERRIDE_COUNT,
    MODEL_FEATURES,
    POLICY_VALUE_HORIZON_SESSIONS,
    POLICY_VALUE_LOWER_COVERAGE,
    POLICY_VALUE_MIN_PREDICTION,
    POLICY_VALUE_PURGE_EMBARGO_SESSIONS,
    RECOVERY_BREADTH_MIN_COUNT,
    RECOVERY_TQQQ_MOMENTUM_MIN,
    SPEC_PATHS,
    USD_PRESSURE_DRAWDOWN_MAX,
    USD_PRESSURE_RECOVERY_MOMENTUM_MIN,
    _advance_usd_pressure,
    _evaluate_folds,
    _fit_route_models,
    _policy_value_label_for_review,
    _r24_frame_hash,
    _stress_recovery_contract,
    _usd_pressure_contract,
    build_r24_d01_targets,
    build_r24_feature_dataset,
    build_segment_targets,
    development_folds,
    load_and_validate_r24_specs,
    load_r24_price_panel,
    training_rows_for_r24_prediction,
)
from open_composer.research.pit_semantic_theme_r24_forward import (
    BROKER_WRITES,
    ORDER_AUTHORITY,
    RUNTIME_STATUS,
    SOURCE_PACKET_CONTRACT,
    build_r24_forward_source_packet,
)

ROOT = Path(__file__).resolve().parents[1]


def _unit_panel(sessions: pd.DatetimeIndex) -> R11PricePanel:
    frame = pd.DataFrame(100.0, index=sessions, columns=list(UNIVERSE))
    return R11PricePanel(
        open=frame.copy(),
        low=frame.copy(),
        close=frame.copy(),
        volume=frame.copy(),
        metadata={"scope": "unit"},
    )


def _route_rows(
    sessions: pd.DatetimeIndex,
    *,
    risk_on: list[bool] | None = None,
    recovery_boost: list[bool] | None = None,
    ridge_predictions: list[float] | None = None,
    ridge_lower_bounds: list[float] | None = None,
    lightgbm_predictions: list[float] | None = None,
    lightgbm_lower_bounds: list[float] | None = None,
) -> pd.DataFrame:
    route: str | None = None
    held_sessions = 0
    sessions_since_review = 0
    rows = []
    for offset, session in enumerate(sessions):
        is_risk_on = True if risk_on is None else risk_on[offset]
        is_recovery = False if recovery_boost is None else recovery_boost[offset]
        pre_route = route
        route, held_sessions, sessions_since_review, review_due, switched = r24._advance_d01_route(
            current_route=route,
            held_sessions=held_sessions,
            sessions_since_review=sessions_since_review,
            risk_on=is_risk_on,
            recovery_boost=is_recovery,
        )
        eligible = bool(review_due and is_risk_on and route == "USD100")
        decision_position = 300 + offset
        label_end_position = decision_position + POLICY_VALUE_HORIZON_SESSIONS + 1
        rows.append(
            {
                "decision_position": decision_position,
                "decision_session": (session - pd.offsets.BDay(1)).date().isoformat(),
                "execution_position": decision_position + 1,
                "execution_session": session.date().isoformat(),
                "d01_pre_review_route": pre_route,
                "d01_selected_route": route,
                "d01_review_due": review_due,
                "d01_switched": switched,
                "d01_held_sessions": held_sessions,
                "d01_sessions_since_review": sessions_since_review,
                "policy_value_eligible": eligible,
                "policy_value_label": 0.01 if eligible else np.nan,
                "policy_value_label_end_position": (label_end_position if eligible else np.nan),
                "policy_value_label_end_session": (
                    (session + pd.offsets.BDay(POLICY_VALUE_HORIZON_SESSIONS)).date().isoformat()
                    if eligible
                    else None
                ),
                "risk_on": is_risk_on,
                "base_risk_on": is_risk_on,
                "usd_pressure_active": False,
                "usd_pressure_transition": "clear",
                "fast_price_recovery": is_recovery,
                "ordinary_stress_recovery": is_recovery,
                "usd_pressure_recovery": False,
                "recovery_boost": is_recovery,
                "semiconductor_leadership": False,
                "qqq_trend_gap_50": 0.01 if is_recovery else -0.01,
                "tqqq_momentum_10": 0.09 if is_recovery else 0.07,
                "tech_breadth_count_100": 4 if is_recovery else 3,
                "ridge_prediction": (
                    0.02 if ridge_predictions is None else ridge_predictions[offset]
                ),
                "ridge_lower_bound": (
                    0.01 if ridge_lower_bounds is None else ridge_lower_bounds[offset]
                ),
                "lightgbm_prediction": (
                    0.02 if lightgbm_predictions is None else lightgbm_predictions[offset]
                ),
                "lightgbm_lower_bound": (
                    0.01 if lightgbm_lower_bounds is None else lightgbm_lower_bounds[offset]
                ),
                **{
                    feature: 0.001 * (offset + index + 1)
                    for index, feature in enumerate(MODEL_FEATURES)
                },
            }
        )
    return pd.DataFrame(rows)


def _fake_fit(*args, **kwargs):
    del args, kwargs
    return (
        {
            candidate_id: SimpleNamespace(candidate_id=candidate_id, model_id=candidate_id)
            for candidate_id in ("R24M01", "R24M02")
        },
        [],
    )


def _fake_policy_value(model, current):
    prefix = "ridge" if model.candidate_id == "R24M01" else "lightgbm"
    prediction = float(current.iloc[0][f"{prefix}_prediction"])
    lower_bound = float(current.iloc[0][f"{prefix}_lower_bound"])
    return {
        "prediction": prediction,
        "lower_bound": lower_bound,
        "minimum_prediction_pass": prediction >= POLICY_VALUE_MIN_PREDICTION,
        "lower_bound_pass": lower_bound > 0.0,
    }


def test_r24_specs_bind_policy_value_regressors_and_exact_m02_fallback() -> None:
    specs = load_and_validate_r24_specs(ROOT)

    assert set(specs) == set(SPEC_PATHS)
    assert (
        specs["R24D01"].portfolio.selected_route_label
        == "pit_semantic_theme_r24:D01:usd_pressure_dual_fast_recovery_v1"
    )
    route_contract = specs["R24D01"].notes.model_dump(mode="json")["route_contract"]
    assert route_contract["stress_target"] == {"QQQ": 1.0}
    assert route_contract["normal_risk_on_target"] == {"USD": 1.0}
    assert route_contract["stress_recovery"] == _stress_recovery_contract()
    assert route_contract["usd_pressure_override"] == _usd_pressure_contract()

    m01 = specs["R24M01"].model
    m02 = specs["R24M02"].model
    f01 = specs["R24F01"].model
    assert m01 is not None and m02 is not None and f01 is not None
    assert m01.kind == "ridge_regressor"
    assert m02.kind == "lightgbm_regressor"
    assert m01.label.type == m02.label.type == "forward_return"
    assert m01.label.horizon_bars == m02.label.horizon_bars == 10
    assert m01.training.embargo_bars == m02.training.embargo_bars == 11
    assert m01.training.retrain_every_bars == m02.training.retrain_every_bars == 20
    assert m01.training.seed == 15241
    assert m02.training.seed == 15242
    assert m01.selection.threshold == m02.selection.threshold == 0.005
    assert f01.model_dump(mode="json") == m02.model_dump(mode="json")
    assert tuple(m01.features) == tuple(m02.features) == MODEL_FEATURES
    assert len(MODEL_FEATURES) == 8
    assert MINIMUM_POLICY_OVERRIDE_COUNT == 8
    assert (
        "semiconductor_leadership_confirmation"
        in specs["R24D01"].notes.model_dump(mode="json")["factor_library_ids"]
    )


def test_r24_search_space_matches_policy_value_and_trial_contract() -> None:
    iteration = ROOT / "reports/research/iterations/mom_pit_semantic_theme_r24"
    search = json.loads((iteration / "search-space.json").read_text(encoding="utf-8"))
    cumulative = json.loads(
        (iteration / "cumulative-trial-contract.json").read_text(encoding="utf-8")
    )
    deterministic = next(row for row in search["paths"] if row["name"] == "deterministic_price")
    trained = next(row for row in search["paths"] if row["name"] == "trained_ml")

    assert deterministic["parameters"]["stress_target"] == "QQQ100"
    assert deterministic["parameters"]["stress_recovery"] == _stress_recovery_contract()
    assert deterministic["parameters"]["usd_pressure_override"] == _usd_pressure_contract()
    assert trained["parameters"]["label_horizon_sessions"] == {
        "R24M01": 10,
        "R24M02": 10,
    }
    assert trained["parameters"]["calibration_fraction"] == 0.20
    assert trained["parameters"]["lower_bound_coverage"] == 0.80
    assert trained["parameters"]["purge_sessions"] == 11
    assert trained["parameters"]["embargo_sessions"] == 11
    assert search["cumulative_trial_count"] == EFFECTIVE_TRIAL_COUNT == 8128
    assert cumulative["prior_effective_trial_count"] == 8126
    assert cumulative["effective_trial_count"] == 8128


def test_r24_clean_sip_panel_removes_split_discontinuity() -> None:
    panel = load_r24_price_panel(ROOT)

    assert panel.metadata["feed"] == "sip"
    assert panel.metadata["session_count"] == 2388
    assert panel.open.at[pd.Timestamp("2024-11-01"), "TECS"] > 50.0
    ratio = (
        panel.open.at[pd.Timestamp("2024-11-04"), "TECS"]
        / panel.close.at[pd.Timestamp("2024-11-01"), "TECS"]
    )
    assert 0.8 < ratio < 1.2


def test_r24_folds_are_four_nonoverlapping_embargoed_full_year_windows() -> None:
    folds = development_folds(load_r24_price_panel(ROOT).open.index)

    assert len(folds) == 4
    assert all(row["test_session_count"] == 252 for row in folds)
    assert all(row["purge_sessions"] == POLICY_VALUE_PURGE_EMBARGO_SESSIONS for row in folds)
    assert all(row["embargo_sessions"] == POLICY_VALUE_PURGE_EMBARGO_SESSIONS for row in folds)
    assert folds[0]["test_start"] > folds[0]["train_end"]
    assert all(folds[index]["test_end"] < folds[index + 1]["test_start"] for index in range(3))
    assert folds[-1]["test_end"] == "2025-07-31"


@pytest.mark.slow
def test_r24_features_policy_value_labels_and_embargo_use_registered_timing() -> None:
    panel = load_r24_price_panel(ROOT)
    specs = load_and_validate_r24_specs(ROOT)
    dataset = build_r24_feature_dataset(panel)
    _, d01_records = build_r24_d01_targets(panel, specs["R24D01"], dataset)
    folds = development_folds(panel.open.index)
    labelled = dataset[dataset["policy_value_label"].notna()].iloc[0]
    position = int(labelled["decision_position"])

    assert int(labelled["execution_position"]) == position + 1
    assert int(labelled["policy_value_label_end_position"]) == position + 11
    assert bool(labelled["policy_value_eligible"])
    assert bool(labelled["d01_review_due"])
    assert labelled["d01_selected_route"] == "USD100"
    assert labelled["policy_value_label"] == np.log(
        labelled["policy_value_alternative_wealth"] / labelled["policy_value_baseline_wealth"]
    )
    assert dataset.loc[~dataset["policy_value_eligible"], "policy_value_label"].isna().all()
    assert [row["selected_target"] for row in d01_records] == dataset["d01_selected_route"].tolist()

    assert labelled["tqqq_usd_relative_momentum_5"] == (
        panel.close.iloc[position]["TQQQ"] / panel.close.iloc[position - 5]["TQQQ"]
        - panel.close.iloc[position]["USD"] / panel.close.iloc[position - 5]["USD"]
    )
    assert labelled["smh_qqq_relative_momentum_20"] == (
        panel.close.iloc[position]["SMH"] / panel.close.iloc[position - 20]["SMH"]
        - panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"]
    )

    prediction_point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    train = training_rows_for_r24_prediction(
        dataset,
        decision_position=int(prediction_point["decision_position"]),
        spec=specs["R24M01"],
        label_name="policy_value_label",
    )
    assert not train.empty
    assert train["policy_value_eligible"].all()
    assert int(train["policy_value_label_end_position"].max()) <= (
        int(prediction_point["decision_position"]) - POLICY_VALUE_PURGE_EMBARGO_SESSIONS
    )


def test_r24_placebo_seed_has_one_strategy_spec_value() -> None:
    specs = load_and_validate_r24_specs(ROOT)
    placebo = specs["R24P01"]

    assert placebo.research_design is not None
    assert placebo.research_design.parameter_space["placebo_seed"] == [15108]
    assert placebo.notes.model_dump(mode="json")["placebo_seed"] == 15108


def test_r24_forward_packet_contract_is_hashed_and_fail_closed() -> None:
    published_at = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    fetched_at = published_at + timedelta(minutes=1)
    packet = build_r24_forward_source_packet(
        {
            "epoch_id": "r24fwd_unit",
            "source": "news.alpaca",
            "source_version_key": "article-1:v1",
            "provider_article_id": "article-1",
            "version_id": "v1",
            "symbols": ["nvda", "AMD", "NVDA"],
            "title": "Bound multi-company event",
            "summary": "AMD and NVDA are explicitly affected.",
            "source_url": "https://example.invalid/article-1",
            "published_at": published_at,
            "fetched_at": fetched_at,
            "first_seen_at": fetched_at,
            "visible_at": fetched_at,
            "rights_scope": "unit_test_only",
            "revision_id": "v1",
            "acquisition_mode": "live_api_forward_only",
            "dedupe_key": "article-1:v1",
        }
    )
    schema = json.loads(
        (ROOT / "schemas/pit_semantic_theme_r24_forward_packet.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert packet.packet_contract == SOURCE_PACKET_CONTRACT
    assert packet.packet_id == f"r24pkt_{packet.input_hash[:24]}"
    assert packet.symbols == ["AMD", "NVDA"]
    assert schema["properties"]["packet_contract"]["const"] == SOURCE_PACKET_CONTRACT
    assert RUNTIME_STATUS == "pit_contract_validation_only_no_observation_or_orders"
    assert BROKER_WRITES is ORDER_AUTHORITY is False


def test_r24_policy_value_label_charges_terminal_rejoin_and_stops_on_stress() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=14)
    panel = _unit_panel(sessions)
    dataset = _route_rows(sessions)
    label = _policy_value_label_for_review(dataset, panel.open, 0)

    assert label is not None
    assert label["hard_stress_offset"] is None
    assert label["value"] == np.log(1.0 - 2.0 * 20.0 / 10_000.0)

    stressed = _route_rows(
        sessions,
        risk_on=[True, True, True, *([False] * 11)],
    )
    stopped = _policy_value_label_for_review(stressed, panel.open, 0)
    assert stopped is not None
    assert stopped["hard_stress_offset"] == 3
    assert stopped["value"] == 0.0


def test_r24_models_fit_regression_value_with_chronological_calibration() -> None:
    specs = load_and_validate_r24_specs(ROOT)
    rows = []
    sessions = pd.bdate_range("2018-01-02", periods=180)
    for index, session in enumerate(sessions):
        decision_position = 200 + index * 5
        value = 0.015 * np.sin(index / 7.0) + 0.00002 * index
        rows.append(
            {
                "decision_position": decision_position,
                "decision_session": session.date().isoformat(),
                "execution_session": (session + pd.offsets.BDay(1)).date().isoformat(),
                "policy_value_eligible": True,
                "policy_value_label_end_position": decision_position + 11,
                "policy_value_label_end_session": (session + pd.offsets.BDay(11))
                .date()
                .isoformat(),
                "policy_value_label": value,
                **{
                    feature: 0.001 * index + 0.0001 * feature_index
                    for feature_index, feature in enumerate(MODEL_FEATURES)
                },
            }
        )
    dataset = pd.DataFrame(rows)
    decision_position = 1100
    current = pd.DataFrame(
        [
            {
                "decision_position": decision_position,
                "decision_session": "2025-01-02",
                "execution_session": "2025-01-03",
                **{feature: 0.2 + index * 0.001 for index, feature in enumerate(MODEL_FEATURES)},
            }
        ]
    )

    fitted, records = _fit_route_models(
        dataset,
        current,
        decision_position=decision_position,
        segment_id="F1",
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    assert set(fitted) == {"R24M01", "R24M02"}
    assert {row["model_kind"] for row in records} == {
        "ridge_regressor",
        "lightgbm_regressor",
    }
    assert {row["label_name"] for row in records} == {"policy_value_label"}
    assert all(row["fit_decision_end"] < row["calibration_decision_start"] for row in records)
    assert all(row["training_label_terminal_end"] <= "2024-12-20" for row in records)
    assert all(row["calibration_row_count"] >= 8 for row in records)
    assert all(row["calibration_lower_coverage"] == POLICY_VALUE_LOWER_COVERAGE for row in records)
    assert all(np.isfinite(model.calibration_overprediction_quantile) for model in fitted.values())
    assert all(
        fitted[candidate_id].estimator.predict(current[list(MODEL_FEATURES)]).shape == (1,)
        for candidate_id in fitted
    )


def test_r24_frame_hash_binds_session_identity_and_policy_label_horizon() -> None:
    frame = pd.DataFrame(
        [
            {
                "decision_position": 10,
                "decision_session": "2025-01-02",
                "execution_session": "2025-01-03",
                "policy_value_label_end_position": 21,
                "policy_value_label_end_session": "2025-01-17",
                **{feature: float(index) for index, feature in enumerate(MODEL_FEATURES)},
            }
        ]
    )
    original = _r24_frame_hash(frame, list(MODEL_FEATURES))
    changed = frame.copy()
    changed.loc[0, "policy_value_label_end_position"] = 22

    assert _r24_frame_hash(frame, list(MODEL_FEATURES)) == original
    assert _r24_frame_hash(changed, list(MODEL_FEATURES)) != original


def test_r24_usd_pressure_latches_until_fast_price_recovery() -> None:
    active, transition = _advance_usd_pressure(
        active=False,
        drawdown_20=USD_PRESSURE_DRAWDOWN_MAX + 0.001,
        trend_gap_100=-0.10,
        momentum_20=-0.20,
    )
    assert (active, transition) == (False, "clear")
    active, transition = _advance_usd_pressure(
        active=active,
        drawdown_20=USD_PRESSURE_DRAWDOWN_MAX,
        trend_gap_100=-0.10,
        momentum_20=-0.20,
    )
    assert (active, transition) == (True, "triggered")
    active, transition = _advance_usd_pressure(
        active=active,
        drawdown_20=-0.05,
        trend_gap_100=0.01,
        momentum_20=USD_PRESSURE_RECOVERY_MOMENTUM_MIN,
    )
    assert (active, transition) == (True, "held")
    active, transition = _advance_usd_pressure(
        active=active,
        drawdown_20=-0.05,
        trend_gap_100=0.01,
        momentum_20=USD_PRESSURE_RECOVERY_MOMENTUM_MIN + 0.001,
    )
    assert (active, transition) == (False, "released")


@pytest.mark.slow
def test_r24_pressure_recovery_uses_fast_prices_without_slow_breadth() -> None:
    dataset = build_r24_feature_dataset(load_r24_price_panel(ROOT))
    fast_price = (dataset["qqq_trend_gap_50"] > 0.0) & (
        dataset["tqqq_momentum_10"] >= RECOVERY_TQQQ_MOMENTUM_MIN
    )
    pressure = dataset["usd_pressure_active"]
    ordinary_stress = ~pressure & ~dataset["risk_on"]
    breadth = dataset["tech_breadth_count_100"] >= RECOVERY_BREADTH_MIN_COUNT
    expected = ~dataset["risk_on"] & fast_price & (pressure | breadth)

    assert dataset["recovery_boost"].equals(expected)
    assert dataset["usd_pressure_recovery"].equals(pressure & fast_price)
    assert dataset["ordinary_stress_recovery"].equals(ordinary_stress & fast_price & breadth)


def test_r24_d01_uses_scheduled_usd_and_immediate_stress_recovery() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=20)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r24_specs(ROOT)
    dataset = _route_rows(
        sessions,
        risk_on=[*([True] * 14), False, False, False, False, True, True],
        recovery_boost=[*([False] * 14), False, True, True, False, False, False],
    )

    targets, records = build_r24_d01_targets(panel, specs["R24D01"], dataset)

    assert [row["selected_target"] for row in records[:14]] == ["USD100"] * 14
    assert [row["selected_target"] for row in records[14:18]] == [
        "QQQ",
        "TQQQ",
        "TQQQ",
        "QQQ",
    ]
    assert targets.iloc[14]["QQQ"] == 1.0
    assert targets.iloc[15]["TQQQ"] == 1.0
    assert targets.iloc[18]["USD"] == 1.0
    assert targets.sum(axis=1).eq(1.0).all()


def test_r24_policy_value_overrides_persist_rejoin_and_require_m02_consensus(
    monkeypatch,
) -> None:
    sessions = pd.bdate_range("2025-02-03", periods=16)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r24_specs(ROOT)
    lightgbm_lower = [-0.01] * 5 + [0.01] * 11
    dataset = _route_rows(sessions, lightgbm_lower_bounds=lightgbm_lower)
    monkeypatch.setattr(r24, "_fit_route_models", _fake_fit)
    monkeypatch.setattr(r24, "_predict_policy_value", _fake_policy_value)

    result = build_segment_targets(
        dataset,
        panel,
        segment_id="F1",
        start_session=sessions[0].date().isoformat(),
        end_session=sessions[-1].date().isoformat(),
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    m01 = result.targets["R24M01"]
    m02 = result.targets["R24M02"]
    assert m01.iloc[:10]["TQQQ"].eq(1.0).all()
    assert m01.iloc[10:15]["USD"].eq(1.0).all()
    assert m01.iloc[15]["TQQQ"] == 1.0
    assert m02.iloc[:5]["USD"].eq(1.0).all()
    assert m02.iloc[5:15]["TQQQ"].eq(1.0).all()
    assert m02.iloc[15]["USD"] == 1.0
    assert result.targets["R24F01"].equals(m02)
    assert all(frame.sum(axis=1).eq(1.0).all() for frame in result.targets.values())

    m01_starts = [
        row
        for row in result.prediction_records
        if row["candidate_id"] == "R24M01" and row["override_started"]
    ]
    m02_starts = [
        row
        for row in result.prediction_records
        if row["candidate_id"] == "R24M02" and row["override_started"]
    ]
    assert [row["execution_session"] for row in m01_starts] == [
        sessions[0].date().isoformat(),
        sessions[15].date().isoformat(),
    ]
    assert [row["execution_session"] for row in m02_starts] == [sessions[5].date().isoformat()]


def test_r24_hard_stress_terminates_policy_override_immediately(monkeypatch) -> None:
    sessions = pd.bdate_range("2025-03-03", periods=5)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r24_specs(ROOT)
    dataset = _route_rows(
        sessions,
        risk_on=[True, True, False, False, False],
    )
    monkeypatch.setattr(r24, "_fit_route_models", _fake_fit)
    monkeypatch.setattr(r24, "_predict_policy_value", _fake_policy_value)

    result = build_segment_targets(
        dataset,
        panel,
        segment_id="F1",
        start_session=sessions[0].date().isoformat(),
        end_session=sessions[-1].date().isoformat(),
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    for frame in result.targets.values():
        assert frame["TQQQ"].tolist()[:2] == [1.0, 1.0]
        assert frame["QQQ"].tolist()[2:] == [1.0, 1.0, 1.0]
    terminated = [
        row
        for row in result.target_records
        if row["candidate_id"] == "R24M01" and row["hard_stress_terminated"]
    ]
    assert [row["execution_session"] for row in terminated] == [sessions[2].date().isoformat()]


def test_r24_fold_evaluation_uses_shared_terminal_metric_views() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=8)
    opens = pd.DataFrame(
        {
            "QQQ": [100.0, 101.0, 102.0, 101.0, 103.0, 104.0, 105.0, 106.0],
            "TQQQ": [50.0, 51.5, 53.0, 51.0, 54.0, 55.0, 56.5, 58.0],
            "BIL": [91.0, 91.01, 91.02, 91.03, 91.04, 91.05, 91.06, 91.07],
        },
        index=sessions,
    )
    targets = pd.DataFrame(
        [{"QQQ": 0.0, "TQQQ": 1.0, "BIL": 0.0}],
        index=pd.DatetimeIndex([sessions[0]]),
        columns=opens.columns,
    )
    folds = [
        {
            "fold_id": "F1",
            "test_start": sessions[0].date().isoformat(),
            "test_end": sessions[-1].date().isoformat(),
        }
    ]

    result = _evaluate_folds(opens, folds, {"R24TEST": targets})["R24TEST"][0]

    assert set(result["metrics"]) == {"with_terminal", "without_terminal"}
    assert set(result["qqq_benchmark_metrics"]) == {"with_terminal", "without_terminal"}
    assert result["metrics"]["with_terminal"]["market_interval_count"] == 7
