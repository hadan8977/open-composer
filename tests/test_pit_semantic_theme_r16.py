from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import open_composer.research.pit_semantic_theme_r16 as r16
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE, R11PricePanel
from open_composer.research.pit_semantic_theme_r16 import (
    ITER_ID,
    MODEL_FEATURES,
    SPEC_PATHS,
    _evaluate_folds,
    _fit_route_models,
    _r16_frame_hash,
    build_r16_d01_targets,
    build_segment_targets,
    development_folds,
    load_and_validate_r16_specs,
    load_r16_price_panel,
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
    leadership: list[bool],
    *,
    risk_on: list[bool] | None = None,
    m01_probabilities: list[float] | None = None,
    m02_probabilities: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for offset, (session, is_leader) in enumerate(zip(sessions, leadership, strict=True)):
        rows.append(
            {
                "decision_position": 300 + offset,
                "decision_session": (session - pd.offsets.BDay(1)).date().isoformat(),
                "execution_position": 301 + offset,
                "execution_session": session.date().isoformat(),
                "risk_on": True if risk_on is None else risk_on[offset],
                "semiconductor_leadership": is_leader,
                "m01_probability": (
                    0.90 if m01_probabilities is None else m01_probabilities[offset]
                ),
                "m02_probability": (
                    0.90 if m02_probabilities is None else m02_probabilities[offset]
                ),
                **{
                    feature: 0.001 * (offset + index + 1)
                    for index, feature in enumerate(MODEL_FEATURES)
                },
            }
        )
    return pd.DataFrame(rows)


def test_r16_specs_bind_fixed_states_classifiers_and_exact_fallback() -> None:
    specs = load_and_validate_r16_specs(ROOT)

    assert set(specs) == set(SPEC_PATHS)
    assert (
        specs["R16D01"].portfolio.selected_route_label
        == "pit_semantic_theme_r16:D01:inverse_stress_state_v1"
    )
    assert specs["R16M01"].model is not None
    assert specs["R16M01"].model.kind == "logistic_regression_classifier"
    assert specs["R16M01"].model.label.horizon_bars == 20
    assert specs["R16M01"].model.training.embargo_bars == 21
    assert specs["R16M01"].model.training.retrain_every_bars == 20
    assert specs["R16M01"].model.training.seed == 15101
    assert specs["R16M02"].model is not None
    assert specs["R16M02"].model.kind == "lightgbm_classifier"
    assert specs["R16M02"].model.label.horizon_bars == 10
    assert specs["R16M02"].model.selection.threshold == 0.20
    assert specs["R16M02"].model.training.seed == 15102
    assert specs["R16F01"].model is not None
    assert specs["R16F01"].model.model_dump(mode="json") == specs["R16M01"].model.model_dump(
        mode="json"
    )
    assert tuple(specs["R16M01"].model.features) == MODEL_FEATURES
    assert tuple(specs["R16M02"].model.features) == MODEL_FEATURES


def test_r16_clean_sip_panel_removes_r11_split_discontinuity() -> None:
    panel = load_r16_price_panel(ROOT)

    assert panel.metadata["feed"] == "sip"
    assert panel.metadata["session_count"] == 2388
    assert panel.open.at[pd.Timestamp("2024-11-01"), "TECS"] > 50.0
    ratio = (
        panel.open.at[pd.Timestamp("2024-11-04"), "TECS"]
        / panel.close.at[pd.Timestamp("2024-11-01"), "TECS"]
    )
    assert 0.8 < ratio < 1.2


def test_r16_folds_are_four_nonoverlapping_embargoed_full_year_windows() -> None:
    panel = load_r16_price_panel(ROOT)
    folds = development_folds(panel.open.index)

    assert len(folds) == 4
    assert all(row["test_session_count"] == 252 for row in folds)
    assert all(row["purge_sessions"] == 21 for row in folds)
    assert all(row["embargo_sessions"] == 21 for row in folds)
    assert folds[0]["test_start"] > folds[0]["train_end"]
    assert all(folds[index]["test_end"] < folds[index + 1]["test_start"] for index in range(3))
    assert folds[-1]["test_end"] == "2025-07-31"


def test_r16_models_fit_classification_labels_without_future_data() -> None:
    specs = load_and_validate_r16_specs(ROOT)
    sessions = pd.bdate_range("2019-01-02", periods=260)
    rows = []
    for position, session in enumerate(sessions[:230]):
        rows.append(
            {
                "decision_position": position,
                "decision_session": session.date().isoformat(),
                "execution_session": sessions[position + 1].date().isoformat(),
                "m01_label_end_position": position + 21,
                "m01_label_end_session": sessions[position + 21].date().isoformat(),
                "m02_label_end_position": position + 11,
                "m02_label_end_session": sessions[position + 11].date().isoformat(),
                **{
                    feature: 0.001 * (position + 1) + 0.0001 * feature_index
                    for feature_index, feature in enumerate(MODEL_FEATURES)
                },
                "m01_soxl100_label": float(position % 3 == 0),
                "m02_survival_label": float(position % 4 != 0),
            }
        )
    dataset = pd.DataFrame(rows)
    position = 220
    current = dataset[dataset["decision_position"] == position].copy()

    fitted, records = _fit_route_models(
        dataset,
        current,
        decision_position=position,
        segment_id="F1",
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    assert set(fitted) == {"R16M01", "R16M02"}
    assert {row["model_kind"] for row in records} == {
        "logistic_regression_classifier",
        "lightgbm_classifier",
    }
    assert {row["label_name"] for row in records} == {
        "m01_soxl100_label",
        "m02_survival_label",
    }
    assert all(
        row["training_label_terminal_end"] <= sessions[199].date().isoformat() for row in records
    )
    assert all(row["iter_id"] == ITER_ID for row in records)
    assert all(
        fitted[candidate_id].estimator.predict_proba(current[list(MODEL_FEATURES)]).shape == (1, 2)
        for candidate_id in fitted
    )


def test_r16_frame_hash_binds_session_identity_and_both_label_horizons() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=2)
    frame = pd.DataFrame(
        [
            {
                "decision_position": 10,
                "decision_session": sessions[0].date().isoformat(),
                "execution_session": sessions[1].date().isoformat(),
                "m01_label_end_position": 31,
                "m01_label_end_session": "2025-02-14",
                "m02_label_end_position": 21,
                "m02_label_end_session": "2025-01-31",
                **{feature: float(index) for index, feature in enumerate(MODEL_FEATURES)},
            }
        ]
    )
    original = _r16_frame_hash(frame, list(MODEL_FEATURES))
    changed = frame.copy()
    changed.loc[0, "m02_label_end_position"] = 22

    assert _r16_frame_hash(frame, list(MODEL_FEATURES)) == original
    assert _r16_frame_hash(changed, list(MODEL_FEATURES)) != original


def test_r16_d01_uses_scheduled_soxl100_and_immediate_sqqq_entry_exit() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=18)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r16_specs(ROOT)
    dataset = _route_rows(
        sessions,
        [False, *([True] * 13), False, False, False, False],
        risk_on=[*([True] * 14), False, False, True, True],
    )

    targets, records = build_r16_d01_targets(panel, specs["R16D01"], dataset)

    assert [row["selected_target"] for row in records[:10]] == ["TQQQ"] * 10
    assert [row["selected_target"] for row in records[10:14]] == ["SOXL100"] * 4
    assert [row["selected_target"] for row in records[14:16]] == ["SQQQ", "SQQQ"]
    assert [row["selected_target"] for row in records[16:]] == ["TQQQ", "TQQQ"]
    assert targets.iloc[9]["TQQQ"] == 1.0
    assert targets.iloc[10]["SOXL"] == 1.0
    assert targets.iloc[10]["TQQQ"] == 0.0
    assert targets.iloc[14]["SQQQ"] == 1.0
    assert targets.iloc[16]["TQQQ"] == 1.0
    assert targets.loc[:, ["BIL", "GLD"]].eq(0.0).all().all()
    assert targets.sum(axis=1).eq(1.0).all()


def test_r16_m01_authorizes_only_soxl100_and_m02_exits_to_qqq(monkeypatch) -> None:
    sessions = pd.bdate_range("2025-02-03", periods=16)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r16_specs(ROOT)
    dataset = _route_rows(
        sessions,
        [True] * len(sessions),
        m01_probabilities=[*([0.20] * 5), *([0.90] * 11)],
        m02_probabilities=[*([0.90] * 11), 0.10, *([0.90] * 4)],
    )

    def fake_fit(*args, **kwargs):
        del args, kwargs
        return (
            {
                candidate_id: SimpleNamespace(candidate_id=candidate_id, model_id=candidate_id)
                for candidate_id in ("R16M01", "R16M02")
            },
            [],
        )

    def fake_probability(model, current):
        column = "m01_probability" if model.candidate_id == "R16M01" else "m02_probability"
        return float(current.iloc[0][column])

    monkeypatch.setattr(r16, "_fit_route_models", fake_fit)
    monkeypatch.setattr(r16, "_predict_probability", fake_probability)

    result = build_segment_targets(
        dataset,
        panel,
        segment_id="F1",
        start_session=sessions[0].date().isoformat(),
        end_session=sessions[-1].date().isoformat(),
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    m01 = result.targets["R16M01"]
    m02 = result.targets["R16M02"]
    assert m01.iloc[:10]["TQQQ"].eq(1.0).all()
    assert m01.iloc[10:]["SOXL"].eq(1.0).all()
    assert m01.iloc[10:]["TQQQ"].eq(0.0).all()
    assert m02.iloc[:11].equals(m01.iloc[:11])
    assert m02.iloc[11:]["QQQ"].eq(1.0).all()
    assert result.targets["R16F01"].equals(m01)
    assert all(
        frame.loc[:, ["BIL", "GLD"]].eq(0.0).all().all() for frame in result.targets.values()
    )
    assert all(frame.sum(axis=1).eq(1.0).all() for frame in result.targets.values())

    m01_predictions = [
        row["probability"] for row in result.prediction_records if row["candidate_id"] == "R16M01"
    ]
    f01_predictions = [
        row["probability"] for row in result.prediction_records if row["candidate_id"] == "R16F01"
    ]
    assert f01_predictions == m01_predictions


def test_r16_fold_evaluation_uses_shared_terminal_metric_views() -> None:
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

    result = _evaluate_folds(opens, folds, {"R16TEST": targets})["R16TEST"][0]

    assert set(result["metrics"]) == {"with_terminal", "without_terminal"}
    assert set(result["qqq_benchmark_metrics"]) == {"with_terminal", "without_terminal"}
    assert result["metrics"]["with_terminal"]["market_interval_count"] == 7
