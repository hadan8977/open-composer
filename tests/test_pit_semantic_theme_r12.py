from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.research.pit_semantic_theme_r11 import (
    M01_FEATURES,
    build_price_feature_dataset,
    training_rows_for_prediction,
)
from open_composer.research.pit_semantic_theme_r12 import (
    ITER_ID,
    SPEC_PATHS,
    _evaluate_folds,
    _fit_route_models,
    development_folds,
    load_and_validate_r12_specs,
    load_r12_price_panel,
)

ROOT = Path(__file__).resolve().parents[1]


def test_r12_specs_bind_ridge_lightgbm_and_exact_fallback() -> None:
    specs = load_and_validate_r12_specs(ROOT)

    assert set(specs) == set(SPEC_PATHS)
    assert specs["R12M01"].model is not None
    assert specs["R12M01"].model.kind == "ridge_regressor"
    assert specs["R12M02"].model is not None
    assert specs["R12M02"].model.kind == "lightgbm_regressor"
    assert specs["R12F01"].model is not None
    assert specs["R12F01"].model.model_dump(mode="json") == specs["R12M01"].model.model_dump(
        mode="json"
    )


def test_r12_clean_sip_panel_removes_r11_split_discontinuity() -> None:
    panel = load_r12_price_panel(ROOT)

    assert panel.metadata["feed"] == "sip"
    assert panel.metadata["session_count"] == 2388
    assert panel.open.at[pd.Timestamp("2024-11-01"), "TECS"] > 50.0
    ratio = (
        panel.open.at[pd.Timestamp("2024-11-04"), "TECS"]
        / panel.close.at[pd.Timestamp("2024-11-01"), "TECS"]
    )
    assert 0.8 < ratio < 1.2


def test_r12_folds_are_four_nonoverlapping_full_year_windows() -> None:
    panel = load_r12_price_panel(ROOT)
    folds = development_folds(panel.open.index)

    assert len(folds) == 4
    assert all(row["test_session_count"] == 252 for row in folds)
    assert folds[0]["test_start"] > folds[0]["train_end"]
    assert all(folds[index]["test_end"] < folds[index + 1]["test_start"] for index in range(3))
    assert folds[-1]["test_end"] == "2025-07-31"


def test_r12_fold_local_fit_uses_only_embargo_safe_labels() -> None:
    panel = load_r12_price_panel(ROOT)
    specs = load_and_validate_r12_specs(ROOT)
    dataset = build_price_feature_dataset(panel)
    folds = development_folds(panel.open.index)
    point = dataset[dataset["execution_session"] >= folds[0]["test_start"]].iloc[0]
    position = int(point["decision_position"])
    train = training_rows_for_prediction(
        dataset,
        decision_position=position,
        spec=specs["R12M01"],
        label_name="net_forward_return_5",
    )

    assert not train.empty
    assert int(train["label_end_position"].max()) <= position - 10
    assert tuple(specs["R12M01"].model.features) == M01_FEATURES


def test_r12_matched_models_fit_from_same_synthetic_rows_without_future_data() -> None:
    specs = load_and_validate_r12_specs(ROOT)
    sessions = pd.bdate_range("2020-01-02", periods=130)
    rows = []
    for position, session in enumerate(sessions[:120]):
        label_end_position = position + 5
        rows.append(
            {
                "decision_position": position,
                "decision_session": session.date().isoformat(),
                "label_end_position": label_end_position,
                "label_end_session": sessions[label_end_position].date().isoformat(),
                "execution_session": sessions[position + 1].date().isoformat(),
                "symbol": "SYN",
                **{
                    feature: 0.001 * (position + 1) + 0.0001 * feature_index
                    for feature_index, feature in enumerate(M01_FEATURES)
                },
                "net_forward_return_5": 0.001 * ((position % 7) - 3),
            }
        )
    dataset = pd.DataFrame(rows)
    position = 110
    current = dataset[dataset["decision_position"] == position].copy()

    fitted, records = _fit_route_models(
        dataset,
        current,
        decision_position=position,
        segment_id="F1",
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    assert set(fitted) == {"R12M01", "R12M02"}
    assert {row["model_kind"] for row in records} == {
        "ridge_regressor",
        "lightgbm_regressor",
    }
    assert len({row["training_data_sha256"] for row in records}) == 1
    assert all(row["iter_id"] == ITER_ID for row in records)


def test_r12_fold_evaluation_uses_shared_terminal_metric_views() -> None:
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
        [{"QQQ": 0.8, "TQQQ": 0.0, "BIL": 0.2}],
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

    result = _evaluate_folds(opens, folds, {"R12TEST": targets})["R12TEST"][0]

    assert set(result["metrics"]) == {"with_terminal", "without_terminal"}
    assert set(result["qqq_benchmark_metrics"]) == {
        "with_terminal",
        "without_terminal",
    }
    assert result["metrics"]["with_terminal"]["market_interval_count"] == 7
