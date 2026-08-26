from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import open_composer.research.pit_semantic_theme_r13 as r13
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE, R11PricePanel
from open_composer.research.pit_semantic_theme_r13 import (
    INCREMENTAL_OVERRIDE_COST,
    ITER_ID,
    MODEL_FEATURES,
    SPEC_PATHS,
    _evaluate_folds,
    _fit_route_models,
    build_r13_d01_targets,
    build_r13_feature_dataset,
    build_segment_targets,
    development_folds,
    load_and_validate_r13_specs,
    load_r13_price_panel,
    training_rows_for_r13_prediction,
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
    overrides: list[str | None],
    *,
    risk_on: list[bool] | None = None,
    m01_probabilities: list[float] | None = None,
    m02_probabilities: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for offset, (session, override) in enumerate(zip(sessions, overrides, strict=True)):
        item = {
            "decision_position": 300 + offset,
            "decision_session": (session - pd.offsets.BDay(1)).date().isoformat(),
            "execution_position": 301 + offset,
            "execution_session": session.date().isoformat(),
            "risk_on": True if risk_on is None else risk_on[offset],
            "gld_defensive_ok": False,
            "eligible_override_symbol": override,
            "eligible_override_score": 0.10 if override else None,
            "tqqq_score": 0.01,
            "m01_probability": (0.90 if m01_probabilities is None else m01_probabilities[offset]),
            "m02_probability": (0.90 if m02_probabilities is None else m02_probabilities[offset]),
            **{
                feature: 0.001 * (offset + index + 1)
                for index, feature in enumerate(MODEL_FEATURES)
            },
        }
        for symbol in ("TQQQ", *r13.OVERRIDE_SYMBOLS):
            item[f"score_{symbol}"] = 0.10 if symbol == override else 0.01
            item[f"eligible_{symbol}"] = symbol == "TQQQ" or symbol == override
        rows.append(item)
    return pd.DataFrame(rows)


def test_r13_specs_bind_classifiers_and_exact_fallback() -> None:
    specs = load_and_validate_r13_specs(ROOT)

    assert set(specs) == set(SPEC_PATHS)
    assert specs["R13M01"].model is not None
    assert specs["R13M01"].model.kind == "logistic_regression_classifier"
    assert specs["R13M02"].model is not None
    assert specs["R13M02"].model.kind == "lightgbm_classifier"
    assert specs["R13F01"].model is not None
    assert specs["R13F01"].model.model_dump(mode="json") == specs["R13M01"].model.model_dump(
        mode="json"
    )
    assert tuple(specs["R13M01"].model.features) == MODEL_FEATURES
    assert tuple(specs["R13M02"].model.features) == MODEL_FEATURES


def test_r13_clean_sip_panel_removes_r11_split_discontinuity() -> None:
    panel = load_r13_price_panel(ROOT)

    assert panel.metadata["feed"] == "sip"
    assert panel.metadata["session_count"] == 2388
    assert panel.open.at[pd.Timestamp("2024-11-01"), "TECS"] > 50.0
    ratio = (
        panel.open.at[pd.Timestamp("2024-11-04"), "TECS"]
        / panel.close.at[pd.Timestamp("2024-11-01"), "TECS"]
    )
    assert 0.8 < ratio < 1.2


def test_r13_folds_are_four_nonoverlapping_full_year_windows() -> None:
    panel = load_r13_price_panel(ROOT)
    folds = development_folds(panel.open.index)

    assert len(folds) == 4
    assert all(row["test_session_count"] == 252 for row in folds)
    assert folds[0]["test_start"] > folds[0]["train_end"]
    assert all(folds[index]["test_end"] < folds[index + 1]["test_start"] for index in range(3))
    assert folds[-1]["test_end"] == "2025-07-31"


def test_r13_features_labels_and_embargo_use_the_registered_timing() -> None:
    panel = load_r13_price_panel(ROOT)
    specs = load_and_validate_r13_specs(ROOT)
    dataset = build_r13_feature_dataset(panel)
    folds = development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])

    assert int(point["execution_position"]) == position + 1
    assert int(point["label_end_position"]) == position + 6
    assert point["qqq_momentum_20"] == (
        panel.close.iloc[position]["QQQ"] / panel.close.iloc[position - 20]["QQQ"] - 1.0
    )

    labelled = dataset[dataset["m01_override_label"].notna()].iloc[0]
    override = str(labelled["eligible_override_symbol"])
    execution_position = int(labelled["execution_position"])
    label_end_position = int(labelled["label_end_position"])
    override_return = (
        panel.open.iloc[label_end_position][override]
        / panel.open.iloc[execution_position][override]
        - 1.0
    )
    tqqq_return = (
        panel.open.iloc[label_end_position]["TQQQ"] / panel.open.iloc[execution_position]["TQQQ"]
        - 1.0
    )
    assert labelled["m01_override_label"] == float(
        override_return - tqqq_return - INCREMENTAL_OVERRIDE_COST > 0.0
    )

    for candidate_id, label_name in (
        ("R13M01", "m01_override_label"),
        ("R13M02", "m02_survival_label"),
    ):
        train = training_rows_for_r13_prediction(
            dataset,
            decision_position=position,
            spec=specs[candidate_id],
            label_name=label_name,
        )
        assert not train.empty
        assert int(train["label_end_position"].max()) <= position - 10
        assert train[label_name].isin([0.0, 1.0]).all()


def test_r13_models_fit_classification_labels_without_future_data() -> None:
    specs = load_and_validate_r13_specs(ROOT)
    sessions = pd.bdate_range("2020-01-02", periods=150)
    rows = []
    for position, session in enumerate(sessions[:140]):
        label_end_position = position + 6
        rows.append(
            {
                "decision_position": position,
                "decision_session": session.date().isoformat(),
                "label_end_position": label_end_position,
                "label_end_session": sessions[label_end_position].date().isoformat(),
                "execution_session": sessions[position + 1].date().isoformat(),
                "eligible_override_symbol": "SOXL",
                **{
                    feature: 0.001 * (position + 1) + 0.0001 * feature_index
                    for feature_index, feature in enumerate(MODEL_FEATURES)
                },
                "m01_override_label": float(position % 3 == 0),
                "m02_survival_label": float(position % 4 != 0),
            }
        )
    dataset = pd.DataFrame(rows)
    position = 130
    current = dataset[dataset["decision_position"] == position].copy()

    fitted, records = _fit_route_models(
        dataset,
        current,
        decision_position=position,
        segment_id="F1",
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    assert set(fitted) == {"R13M01", "R13M02"}
    assert {row["model_kind"] for row in records} == {
        "logistic_regression_classifier",
        "lightgbm_classifier",
    }
    assert {row["label_name"] for row in records} == {
        "m01_override_label",
        "m02_survival_label",
    }
    assert all(
        row["training_label_terminal_end"] <= sessions[120].date().isoformat() for row in records
    )
    assert all(row["iter_id"] == ITER_ID for row in records)
    assert all(
        fitted[candidate_id].estimator.predict_proba(current[list(MODEL_FEATURES)]).shape == (1, 2)
        for candidate_id in fitted
    )


def test_r13_d01_defaults_to_tqqq_and_applies_three_session_switch_hysteresis() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=9)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r13_specs(ROOT)
    dataset = _route_rows(
        sessions,
        [None, "SOXL", "SOXL", "SOXL", "TECL", "TECL", "TECL", None, None],
        risk_on=[True, True, True, True, True, True, True, False, False],
    )
    dataset.loc[7, "gld_defensive_ok"] = True

    targets, records = build_r13_d01_targets(panel, specs["R13D01"], dataset)

    assert [row["selected_target"] for row in records[:7]] == [
        "TQQQ",
        "TQQQ",
        "TQQQ",
        "SOXL",
        "SOXL",
        "SOXL",
        "TECL",
    ]
    assert targets.iloc[0]["TQQQ"] == 1.0
    assert targets.iloc[7]["GLD"] == 0.8
    assert targets.iloc[7]["BIL"] == 0.2
    assert targets.iloc[8]["BIL"] == 1.0
    assert targets.sum(axis=1).eq(1.0).all()


def test_r13_m01_low_confidence_and_m02_tail_exit_preserve_fallbacks(monkeypatch) -> None:
    sessions = pd.bdate_range("2025-02-03", periods=8)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r13_specs(ROOT)
    dataset = _route_rows(
        sessions,
        ["SOXL"] * len(sessions),
        m01_probabilities=[0.20, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.90],
        m02_probabilities=[0.90, 0.90, 0.90, 0.90, 0.20, 0.90, 0.90, 0.90],
    )

    def fake_fit(*args, **kwargs):
        del args, kwargs
        return (
            {
                candidate_id: SimpleNamespace(candidate_id=candidate_id, model_id=candidate_id)
                for candidate_id in ("R13M01", "R13M02")
            },
            [],
        )

    def fake_probability(model, current):
        column = "m01_probability" if model.candidate_id == "R13M01" else "m02_probability"
        return float(current.iloc[0][column])

    monkeypatch.setattr(r13, "_fit_route_models", fake_fit)
    monkeypatch.setattr(r13, "_predict_probability", fake_probability)

    result = build_segment_targets(
        dataset,
        panel,
        segment_id="F1",
        start_session=sessions[0].date().isoformat(),
        end_session=sessions[-1].date().isoformat(),
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    m01 = result.targets["R13M01"]
    m02 = result.targets["R13M02"]
    assert m01.iloc[0]["TQQQ"] == 1.0
    assert m01.iloc[3]["SOXL"] == 1.0
    assert m02.iloc[:4].equals(m01.iloc[:4])
    assert m02.iloc[4:7]["BIL"].eq(1.0).all()
    assert m02.iloc[7].equals(m01.iloc[7])
    assert result.targets["R13F01"].equals(m01)
    assert all(frame.sum(axis=1).eq(1.0).all() for frame in result.targets.values())

    m01_predictions = [
        row["probability"] for row in result.prediction_records if row["candidate_id"] == "R13M01"
    ]
    f01_predictions = [
        row["probability"] for row in result.prediction_records if row["candidate_id"] == "R13F01"
    ]
    assert f01_predictions == m01_predictions


def test_r13_fold_evaluation_uses_shared_terminal_metric_views() -> None:
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

    result = _evaluate_folds(opens, folds, {"R13TEST": targets})["R13TEST"][0]

    assert set(result["metrics"]) == {"with_terminal", "without_terminal"}
    assert set(result["qqq_benchmark_metrics"]) == {
        "with_terminal",
        "without_terminal",
    }
    assert result["metrics"]["with_terminal"]["market_interval_count"] == 7
