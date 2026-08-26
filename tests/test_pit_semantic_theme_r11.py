from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.pit_semantic_theme_r11 import (
    M01_FEATURES,
    RANKABLE_SYMBOLS,
    SPEC_PATHS,
    UNIVERSE,
    R11PricePanel,
    _prediction_identity_pass,
    apply_survival_gate,
    build_price_feature_dataset,
    development_folds,
    family_gates,
    risk_budget_target,
    scheduled_positions,
    training_rows_for_prediction,
    validate_r11_specs,
)

ROOT = Path(__file__).resolve().parents[1]


def _specs():
    return {
        candidate_id: load_strategy_spec(ROOT / path) for candidate_id, path in SPEC_PATHS.items()
    }


def _panel(periods: int = 280) -> R11PricePanel:
    index = pd.bdate_range("2023-01-02", periods=periods)
    steps = np.arange(periods, dtype=float)
    opens = {}
    closes = {}
    lows = {}
    volumes = {}
    for offset, symbol in enumerate(UNIVERSE, start=1):
        trend = 100.0 + offset + steps * (0.03 + offset * 0.0005)
        cycle = np.sin(steps / (5.0 + offset / 10.0)) * 0.5
        opens[symbol] = trend + cycle
        closes[symbol] = trend + cycle + np.cos(steps / 7.0) * 0.2
        lows[symbol] = np.minimum(opens[symbol], closes[symbol]) * 0.995
        volumes[symbol] = np.full(periods, 1_000_000.0 + offset * 10_000.0)
    return R11PricePanel(
        open=pd.DataFrame(opens, index=index),
        low=pd.DataFrame(lows, index=index),
        close=pd.DataFrame(closes, index=index),
        volume=pd.DataFrame(volumes, index=index),
        metadata={"provider": "synthetic_test_only"},
    )


def test_r11_all_specs_match_the_preregistered_safety_and_model_contracts() -> None:
    specs = _specs()

    validate_r11_specs(specs)

    assert tuple(specs["R11M01"].model.features) == M01_FEATURES
    assert specs["R11F01"].model.model_dump(mode="json") == specs["R11M01"].model.model_dump(
        mode="json"
    )


def test_r11_schedule_uses_only_next_monday_wednesday_friday_open() -> None:
    index = pd.bdate_range("2026-01-02", periods=20)

    points = scheduled_positions(index)

    assert points
    assert all(execution == decision + 1 for decision, execution in points)
    assert all(index[execution].weekday() in {0, 2, 4} for _, execution in points)


def test_r11_feature_dataset_uses_decision_close_and_future_open_labels() -> None:
    panel = _panel()

    dataset = build_price_feature_dataset(panel)

    assert set(dataset["symbol"]) == set(RANKABLE_SYMBOLS)
    assert (dataset["execution_position"] == dataset["decision_position"] + 1).all()
    labelled = dataset.dropna(subset=["net_forward_return_5"])
    assert (labelled["label_end_position"] == labelled["execution_position"] + 5).all()
    assert np.isfinite(dataset.loc[:, list(M01_FEATURES)].to_numpy(dtype=float)).all()


def test_r11_training_rows_enforce_ten_session_embargo_after_label_end() -> None:
    specs = _specs()
    dataset = build_price_feature_dataset(_panel(900))
    decision_position = int(dataset["decision_position"].max())

    rows = training_rows_for_prediction(
        dataset,
        decision_position=decision_position,
        spec=specs["R11M01"],
        label_name="net_forward_return_5",
    )

    assert not rows.empty
    assert int(rows["label_end_position"].max()) <= decision_position - 10
    assert int(rows["decision_position"].min()) >= decision_position - 756


def test_r11_development_contract_is_four_contiguous_81_interval_folds() -> None:
    index = pd.bdate_range(end="2025-07-31", periods=1091)

    folds = development_folds(index)

    assert [row["test_interval_count"] for row in folds] == [81, 81, 81, 81]
    assert all(row["fit_from_scratch"] is True for row in folds)
    assert all(folds[index]["test_end"] == folds[index + 1]["test_start"] for index in range(3))


def test_r11_risk_budget_keeps_eighty_percent_risk_and_bil_reserve() -> None:
    scores = pd.Series(
        {symbol: float(index) for index, symbol in enumerate(RANKABLE_SYMBOLS, start=1)}
    )
    current = pd.DataFrame(
        {
            "symbol": sorted(RANKABLE_SYMBOLS),
            "raw_realized_volatility_20": np.linspace(0.01, 0.03, len(RANKABLE_SYMBOLS)),
        }
    )

    target = risk_budget_target(
        scores,
        current,
        columns=pd.Index(UNIVERSE),
        gross_budget=0.8,
        max_symbols=3,
    )

    assert np.isclose(target[list(RANKABLE_SYMBOLS)].sum(), 0.8)
    assert np.isclose(target["BIL"], 0.2)
    assert (target[list(RANKABLE_SYMBOLS)] > 0).sum() == 3
    assert np.isclose(target.sum(), 1.0)


def test_r11_survival_gate_moves_rejected_risk_to_bil() -> None:
    base = pd.Series(0.0, index=pd.Index(UNIVERSE), dtype=float)
    base["TQQQ"] = 0.5
    base["SMH"] = 0.3
    base["BIL"] = 0.2
    probabilities = pd.Series(0.9, index=pd.Index(RANKABLE_SYMBOLS), dtype=float)
    probabilities["TQQQ"] = 0.4

    target = apply_survival_gate(base, probabilities, threshold=0.55, reserve_symbol="BIL")

    assert target["TQQQ"] == 0.0
    assert np.isclose(target["SMH"], 0.3)
    assert np.isclose(target["BIL"], 0.7)
    assert np.isclose(target.sum(), 1.0)


def test_r11_missing_modality_prediction_identity_rejects_any_difference() -> None:
    records = [
        {
            "segment_id": "F1",
            "execution_session": "2026-01-05",
            "candidate_id": "R11M01",
            "prediction_sha256": "same",
        },
        {
            "segment_id": "F1",
            "execution_session": "2026-01-05",
            "candidate_id": "R11F01",
            "prediction_sha256": "same",
        },
    ]

    assert _prediction_identity_pass(records) is True
    records[1]["prediction_sha256"] = "different"
    assert _prediction_identity_pass(records) is False


def test_r11_family_gates_use_geometric_cagr_tqqq_fraction_and_dsr_pbo() -> None:
    metrics = {
        "cagr": 0.60,
        "max_drawdown": -0.50,
        "annualized_sharpe_excess_BIL": 1.1,
        "mar": 1.2,
        "tqqq_up_capture": 0.9,
        "tqqq_down_capture": 0.8,
    }

    gates = family_gates(
        metrics=metrics,
        stress_metrics={"total_return": 0.1},
        qqq_metrics={"cagr": 0.40},
        tqqq_metrics={"cagr": 0.65},
        positive_lift_folds=3,
        dsr={"probability": 0.8},
        pbo={"probability": 0.3},
    )

    assert all(row["pass"] for row in gates)
    by_name = {row["name"]: row for row in gates}
    assert np.isclose(by_name["net_CAGR"]["threshold"], 0.85 * 0.65)
