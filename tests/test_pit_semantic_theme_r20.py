from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import open_composer.research.pit_semantic_theme_r20 as r20
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE, R11PricePanel
from open_composer.research.pit_semantic_theme_r20 import (
    ITER_ID,
    MODEL_FEATURES,
    SPEC_PATHS,
    USD_PRESSURE_DRAWDOWN_MAX,
    USD_PRESSURE_RECOVERY_MOMENTUM_MIN,
    _advance_usd_pressure,
    _evaluate_folds,
    _fit_route_models,
    _r20_frame_hash,
    _stress_recovery_contract,
    _usd_pressure_contract,
    build_r20_d01_targets,
    build_segment_targets,
    development_folds,
    load_and_validate_r20_specs,
    load_r20_price_panel,
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
    recovery_boost: list[bool] | None = None,
    base_risk_on: list[bool] | None = None,
    usd_pressure_active: list[bool] | None = None,
    m01_probabilities: list[float] | None = None,
    m02_probabilities: list[float] | None = None,
) -> pd.DataFrame:
    rows = []
    for offset, (session, is_leader) in enumerate(zip(sessions, leadership, strict=True)):
        is_recovery = False if recovery_boost is None else recovery_boost[offset]
        is_risk_on = True if risk_on is None else risk_on[offset]
        is_base_risk_on = is_risk_on if base_risk_on is None else base_risk_on[offset]
        is_pressure = False if usd_pressure_active is None else usd_pressure_active[offset]
        rows.append(
            {
                "decision_position": 300 + offset,
                "decision_session": (session - pd.offsets.BDay(1)).date().isoformat(),
                "execution_position": 301 + offset,
                "execution_session": session.date().isoformat(),
                "risk_on": is_risk_on,
                "base_risk_on": is_base_risk_on,
                "usd_pressure_active": is_pressure,
                "usd_pressure_transition": "held" if is_pressure else "clear",
                "recovery_boost": is_recovery,
                "qqq_trend_gap_50": 0.01 if is_recovery else -0.01,
                "tqqq_momentum_10": 0.09 if is_recovery else 0.07,
                "tech_breadth_count_100": 4 if is_recovery else 3,
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


def test_r20_specs_bind_fixed_states_classifiers_and_exact_fallback() -> None:
    specs = load_and_validate_r20_specs(ROOT)

    assert set(specs) == set(SPEC_PATHS)
    assert (
        specs["R20D01"].portfolio.selected_route_label
        == "pit_semantic_theme_r20:D01:usd_pressure_latch_v1"
    )
    route_contract = specs["R20D01"].notes.model_dump(mode="json")["route_contract"]
    assert route_contract["stress_target"] == {"QQQ": 1.0}
    assert route_contract["normal_risk_on_target"] == {"USD": 1.0}
    assert route_contract["stress_recovery"] == _stress_recovery_contract()
    assert route_contract["usd_pressure_override"] == _usd_pressure_contract()
    assert specs["R20M01"].model is not None
    assert specs["R20M01"].model.kind == "logistic_regression_classifier"
    assert specs["R20M01"].model.label.horizon_bars == 20
    assert specs["R20M01"].model.training.embargo_bars == 21
    assert specs["R20M01"].model.training.retrain_every_bars == 20
    assert specs["R20M01"].model.training.seed == 15101
    assert specs["R20M02"].model is not None
    assert specs["R20M02"].model.kind == "lightgbm_classifier"
    assert specs["R20M02"].model.label.horizon_bars == 10
    assert specs["R20M02"].model.selection.threshold == 0.20
    assert specs["R20M02"].model.training.seed == 15102
    assert specs["R20F01"].model is not None
    assert specs["R20F01"].model.model_dump(mode="json") == specs["R20M01"].model.model_dump(
        mode="json"
    )
    assert tuple(specs["R20M01"].model.features) == MODEL_FEATURES
    assert tuple(specs["R20M02"].model.features) == MODEL_FEATURES
    assert "qqq_trend_gap_50" not in MODEL_FEATURES
    assert "tqqq_momentum_10" not in MODEL_FEATURES


def test_r20_search_space_matches_specs_and_cumulative_trial_contract() -> None:
    iteration = ROOT / "reports/research/iterations/mom_pit_semantic_theme_r20"
    search = json.loads((iteration / "search-space.json").read_text(encoding="utf-8"))
    cumulative = json.loads(
        (iteration / "cumulative-trial-contract.json").read_text(encoding="utf-8")
    )
    deterministic = next(row for row in search["paths"] if row["name"] == "deterministic_price")
    trained = next(row for row in search["paths"] if row["name"] == "trained_ml")
    placebo = next(row for row in search["paths"] if row["name"] == "placebo")

    assert deterministic["parameters"]["stress_target"] == "QQQ100"
    assert deterministic["parameters"]["stress_recovery"] == _stress_recovery_contract()
    assert trained["parameters"]["label_horizon_sessions"] == {
        "R20M01": 20,
        "R20M02": 10,
    }
    assert trained["parameters"]["purge_sessions"] == 21
    assert trained["parameters"]["embargo_sessions"] == 21
    assert placebo["parameters"]["permutation_seed"] == 15108
    assert deterministic["parameters"]["usd_pressure_override"] == _usd_pressure_contract()
    assert search["cumulative_trial_count"] == 8110
    assert cumulative["prior_effective_trial_count"] == 8102
    assert cumulative["effective_trial_count"] == 8110


def test_r20_clean_sip_panel_removes_r11_split_discontinuity() -> None:
    panel = load_r20_price_panel(ROOT)

    assert panel.metadata["feed"] == "sip"
    assert panel.metadata["session_count"] == 2388
    assert panel.open.at[pd.Timestamp("2024-11-01"), "TECS"] > 50.0
    ratio = (
        panel.open.at[pd.Timestamp("2024-11-04"), "TECS"]
        / panel.close.at[pd.Timestamp("2024-11-01"), "TECS"]
    )
    assert 0.8 < ratio < 1.2


def test_r20_folds_are_four_nonoverlapping_embargoed_full_year_windows() -> None:
    panel = load_r20_price_panel(ROOT)
    folds = development_folds(panel.open.index)

    assert len(folds) == 4
    assert all(row["test_session_count"] == 252 for row in folds)
    assert all(row["purge_sessions"] == 21 for row in folds)
    assert all(row["embargo_sessions"] == 21 for row in folds)
    assert folds[0]["test_start"] > folds[0]["train_end"]
    assert all(folds[index]["test_end"] < folds[index + 1]["test_start"] for index in range(3))
    assert folds[-1]["test_end"] == "2025-07-31"


def test_r20_models_fit_classification_labels_without_future_data() -> None:
    specs = load_and_validate_r20_specs(ROOT)
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
                "m01_tqqq100_label": float(position % 3 == 0),
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

    assert set(fitted) == {"R20M01", "R20M02"}
    assert {row["model_kind"] for row in records} == {
        "logistic_regression_classifier",
        "lightgbm_classifier",
    }
    assert {row["label_name"] for row in records} == {
        "m01_tqqq100_label",
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


def test_r20_frame_hash_binds_session_identity_and_both_label_horizons() -> None:
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
    original = _r20_frame_hash(frame, list(MODEL_FEATURES))
    changed = frame.copy()
    changed.loc[0, "m02_label_end_position"] = 22

    assert _r20_frame_hash(frame, list(MODEL_FEATURES)) == original
    assert _r20_frame_hash(changed, list(MODEL_FEATURES)) != original


def test_r20_usd_pressure_latches_at_frozen_tail_boundary_until_trend_recovery() -> None:
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


def test_r20_d01_uses_scheduled_usd100_and_immediate_stress_recovery() -> None:
    sessions = pd.bdate_range("2025-01-02", periods=20)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r20_specs(ROOT)
    dataset = _route_rows(
        sessions,
        [False, *([True] * 13), *([False] * 6)],
        risk_on=[*([True] * 14), False, False, False, False, True, True],
        recovery_boost=[*([False] * 14), False, True, True, False, False, False],
    )

    targets, records = build_r20_d01_targets(panel, specs["R20D01"], dataset)

    assert [row["selected_target"] for row in records[:14]] == ["USD100"] * 14
    assert [row["selected_target"] for row in records[14:18]] == [
        "QQQ",
        "TQQQ",
        "TQQQ",
        "QQQ",
    ]
    assert [row["selected_target"] for row in records[18:]] == ["USD100", "USD100"]
    assert targets.iloc[9]["USD"] == 1.0
    assert targets.iloc[10]["USD"] == 1.0
    assert targets["SOXL"].eq(0.0).all()
    assert targets.iloc[10]["TQQQ"] == 0.0
    assert targets.iloc[14]["QQQ"] == 1.0
    assert targets.iloc[15]["TQQQ"] == 1.0
    assert targets.iloc[17]["QQQ"] == 1.0
    assert targets.iloc[18]["USD"] == 1.0
    assert records[15]["switched"] is True
    assert records[16]["switched"] is False
    assert records[17]["switched"] is True
    assert targets.loc[:, ["BIL", "GLD"]].eq(0.0).all().all()
    assert targets.sum(axis=1).eq(1.0).all()


def test_r20_m01_authorizes_only_tqqq_override_and_m02_exits_to_qqq(monkeypatch) -> None:
    sessions = pd.bdate_range("2025-02-03", periods=16)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r20_specs(ROOT)
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
                for candidate_id in ("R20M01", "R20M02")
            },
            [],
        )

    def fake_probability(model, current):
        column = "m01_probability" if model.candidate_id == "R20M01" else "m02_probability"
        return float(current.iloc[0][column])

    monkeypatch.setattr(r20, "_fit_route_models", fake_fit)
    monkeypatch.setattr(r20, "_predict_probability", fake_probability)

    result = build_segment_targets(
        dataset,
        panel,
        segment_id="F1",
        start_session=sessions[0].date().isoformat(),
        end_session=sessions[-1].date().isoformat(),
        specs=specs,
        provenance={"test_binding": "unit"},
    )

    m01 = result.targets["R20M01"]
    m02 = result.targets["R20M02"]
    assert m01.iloc[:10]["USD"].eq(1.0).all()
    assert m01.iloc[10:]["TQQQ"].eq(1.0).all()
    assert m01["SOXL"].eq(0.0).all()
    assert m01.iloc[10:]["USD"].eq(0.0).all()
    assert m02.iloc[:11].equals(m01.iloc[:11])
    assert m02.iloc[11:]["QQQ"].eq(1.0).all()
    assert result.targets["R20F01"].equals(m01)
    assert all(
        frame.loc[:, ["BIL", "GLD"]].eq(0.0).all().all() for frame in result.targets.values()
    )
    assert all(frame.sum(axis=1).eq(1.0).all() for frame in result.targets.values())

    m01_predictions = [
        row["probability"] for row in result.prediction_records if row["candidate_id"] == "R20M01"
    ]
    f01_predictions = [
        row["probability"] for row in result.prediction_records if row["candidate_id"] == "R20F01"
    ]
    assert f01_predictions == m01_predictions


def test_r20_ml_routes_inherit_immediate_stress_recovery(monkeypatch) -> None:
    sessions = pd.bdate_range("2025-03-03", periods=4)
    panel = _unit_panel(sessions)
    specs = load_and_validate_r20_specs(ROOT)
    dataset = _route_rows(
        sessions,
        [False] * len(sessions),
        risk_on=[False] * len(sessions),
        recovery_boost=[False, True, True, False],
    )

    def fake_fit(*args, **kwargs):
        del args, kwargs
        return (
            {
                candidate_id: SimpleNamespace(candidate_id=candidate_id, model_id=candidate_id)
                for candidate_id in ("R20M01", "R20M02")
            },
            [],
        )

    monkeypatch.setattr(r20, "_fit_route_models", fake_fit)
    monkeypatch.setattr(r20, "_predict_probability", lambda model, current: 0.90)

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
        assert frame["QQQ"].tolist() == [1.0, 0.0, 0.0, 1.0]
        assert frame["TQQQ"].tolist() == [0.0, 1.0, 1.0, 0.0]


def test_r20_fold_evaluation_uses_shared_terminal_metric_views() -> None:
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

    result = _evaluate_folds(opens, folds, {"R20TEST": targets})["R20TEST"][0]

    assert set(result["metrics"]) == {"with_terminal", "without_terminal"}
    assert set(result["qqq_benchmark_metrics"]) == {"with_terminal", "without_terminal"}
    assert result["metrics"]["with_terminal"]["market_interval_count"] == 7
