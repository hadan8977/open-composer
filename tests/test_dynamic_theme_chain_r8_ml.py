from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.dynamic_theme_chain_r8 import (
    D01_CANDIDATE_SYMBOLS,
    SPEC_PATHS,
    UNIVERSE,
    compute_d01_targets,
)
from open_composer.research.dynamic_theme_chain_r8_ml import (
    FEATURE_NAMES,
    ML_SPEC_PATHS,
    R8MLPanel,
    SegmentResult,
    _apply_survival_gate,
    _fit_model_family,
    _risk_budget_target,
    build_r8_ml_dataset,
    build_segment_targets,
    run_dynamic_theme_chain_r8_stage_e,
    training_rows_for_prediction,
    validate_ml_specs,
)


def test_r8_stage_e_specs_match_locked_model_contract(repo_root: Path) -> None:
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in ML_SPEC_PATHS.items()
    }

    validate_ml_specs(specs)

    assert tuple(specs["R8M01"].model.features) == FEATURE_NAMES
    assert specs["R8M01"].model.training.seed == 8201
    assert specs["R8M02"].model.training.seed == 8202
    assert specs["R8M02"].model.selection.threshold == 0.58


@pytest.mark.slow
def test_r8_stage_e_features_use_decision_time_only() -> None:
    panel = _synthetic_ml_panel(session_count=180)
    dataset = build_r8_ml_dataset(panel)
    pivot = dataset.iloc[len(dataset) // 2]
    decision_position = int(pivot["decision_position"])

    changed = R8MLPanel(
        open=panel.open.copy(),
        low=panel.low.copy(),
        close=panel.close.copy(),
        volume=panel.volume.copy(),
    )
    changed.open.iloc[decision_position + 1 :] *= 1.70
    changed.low.iloc[decision_position + 1 :] *= 1.30
    changed.close.iloc[decision_position + 1 :] *= 1.50
    changed.volume.iloc[decision_position + 1 :] *= 3.0
    changed_dataset = build_r8_ml_dataset(changed)

    before = dataset[dataset["decision_position"] == decision_position].set_index("symbol")
    after = changed_dataset[changed_dataset["decision_position"] == decision_position].set_index(
        "symbol"
    )
    pd.testing.assert_frame_equal(
        before.loc[:, list(FEATURE_NAMES)], after.loc[:, list(FEATURE_NAMES)]
    )


@pytest.mark.slow
def test_r8_stage_e_training_rows_enforce_window_and_embargo(repo_root: Path) -> None:
    panel = _synthetic_ml_panel(session_count=940)
    dataset = build_r8_ml_dataset(panel)
    spec = load_strategy_spec(repo_root / ML_SPEC_PATHS["R8M01"])
    decision_position = int(dataset["decision_position"].max()) - 10
    train_start = str(dataset["decision_session"].min())

    rows = training_rows_for_prediction(
        dataset,
        decision_position=decision_position,
        train_start_session=train_start,
        spec=spec,
        label_name="forward_return_5",
    )

    assert len(rows) > 80
    assert int(rows["decision_position"].min()) >= decision_position - 756
    assert int(rows["label_end_position"].max()) <= decision_position - 10
    assert set(rows["symbol"]) == set(D01_CANDIDATE_SYMBOLS)


def test_r8_stage_e_risk_budget_and_survival_gate_conserve_capital() -> None:
    symbols = sorted(D01_CANDIDATE_SYMBOLS)
    scores = pd.Series(np.linspace(-1.0, 1.0, len(symbols)), index=symbols)
    current = pd.DataFrame(
        {
            "symbol": symbols,
            "raw_realized_volatility_20": np.linspace(0.01, 0.03, len(symbols)),
        }
    )
    target = _risk_budget_target(scores, current, columns=pd.Index(UNIVERSE), max_weight=0.60)
    probabilities = pd.Series(0.90, index=symbols)
    selected = [symbol for symbol in symbols if target[symbol] > 0]
    probabilities[selected[0]] = 0.20

    gated = _apply_survival_gate(target, probabilities, threshold=0.58, reserve_symbol="BIL")

    assert np.isclose(target.sum(), 1.0)
    assert np.isclose(gated.sum(), 1.0)
    assert target.max() <= 0.60 + 1e-12
    assert gated[selected[0]] == 0.0
    assert gated["BIL"] > target["BIL"]


@pytest.mark.slow
def test_r8_stage_e_model_family_is_hash_bound_and_deterministic(repo_root: Path) -> None:
    panel = _synthetic_ml_panel(session_count=940)
    dataset = build_r8_ml_dataset(panel)
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in ML_SPEC_PATHS.items()
    }
    decision_position = int(dataset["decision_position"].max()) - 10
    current = dataset[dataset["decision_position"] == decision_position].sort_values("symbol")
    provenance = _provenance()

    first, first_records = _fit_model_family(
        dataset,
        current,
        decision_position=decision_position,
        train_start_session=str(dataset["decision_session"].min()),
        segment_id="TEST",
        specs=specs,
        provenance=provenance,
    )
    second, second_records = _fit_model_family(
        dataset,
        current,
        decision_position=decision_position,
        train_start_session=str(dataset["decision_session"].min()),
        segment_id="TEST",
        specs=specs,
        provenance=provenance,
    )

    assert set(first) == {"R8M01_LINEAR", "R8M01", "R8M02_LINEAR", "R8M02"}
    assert [row["model_id"] for row in first_records] == [row["model_id"] for row in second_records]
    assert all(len(model.model_id) == 64 for model in first.values())
    assert all(
        row["training_label_terminal_end"] < row["decision_session"] for row in first_records
    )


@pytest.mark.slow
def test_r8_stage_e_segment_builds_mwf_targets_without_broker_writes(
    repo_root: Path,
) -> None:
    panel = _synthetic_ml_panel(session_count=940)
    dataset = build_r8_ml_dataset(panel)
    specs = {
        candidate_id: load_strategy_spec(repo_root / path)
        for candidate_id, path in ML_SPEC_PATHS.items()
    }
    d01 = load_strategy_spec(repo_root / SPEC_PATHS["R8D01"])
    d01_targets, _ = compute_d01_targets(panel.close, panel.volume, d01)
    execution_sessions = sorted(set(dataset["execution_session"]))
    start = execution_sessions[-35]
    end = execution_sessions[-2]

    result = build_segment_targets(
        dataset,
        panel,
        segment_id="TEST",
        train_start_session=str(dataset["decision_session"].min()),
        start_session=start,
        end_session=end,
        specs=specs,
        d01_targets=d01_targets,
        provenance=_provenance(),
    )

    assert set(result.targets) == {"R8M01_LINEAR", "R8M01", "R8M02_LINEAR", "R8M02"}
    assert len(result.model_records) >= 4
    assert len(result.prediction_records) == len(result.targets["R8M01"]) * 4
    for frame in result.targets.values():
        assert np.allclose(frame.sum(axis=1), 1.0)
        assert all(session.weekday() in {0, 2, 4} for session in frame.index)
    assert (
        result.targets["R8M02"].drop(columns="BIL").sum(axis=1)
        <= result.targets["R8M01"].drop(columns="BIL").sum(axis=1) + 1e-12
    ).all()
    assert all(row["fallback_applied"] is False for row in result.target_records)


@pytest.mark.slow
def test_r8_stage_e_evaluation_publishes_complete_broker_free_report(
    tmp_path: Path, repo_root: Path, monkeypatch
) -> None:
    panel = _synthetic_ml_panel(session_count=1750)
    sessions = panel.open.index
    fold_positions = [(800, 1000), (1000, 1200), (1200, 1400), (1400, 1600)]
    folds = [
        {
            "fold_id": f"F{index}",
            "train_start": sessions[40].date().isoformat(),
            "train_end": sessions[start - 11].date().isoformat(),
            "purge_sessions": 10,
            "embargo_sessions": 10,
            "test_start": sessions[start].date().isoformat(),
            "test_end": sessions[end].date().isoformat(),
            "test_interval_count": end - start,
        }
        for index, (start, end) in enumerate(fold_positions, start=1)
    ]
    lockbox_start = sessions[1600].date().isoformat()
    lockbox_end = sessions[1749].date().isoformat()
    iteration = tmp_path / "reports/research/iterations/mom_dynamic_theme_chain_r8"
    iteration.mkdir(parents=True)
    (iteration / "evaluation-report.json").write_text(
        json.dumps(
            {"evaluation_windows": {"lockbox": {"start": lockbox_start, "end": lockbox_end}}}
        ),
        encoding="utf-8",
    )
    (iteration / "fold-results.json").write_text(json.dumps({"folds": folds}), encoding="utf-8")
    for contract_name in (
        "feature-contract.json",
        "label-contract.json",
        "validation-contract.json",
    ):
        (iteration / contract_name).write_text("{}\n", encoding="utf-8")
    specs_by_name = {
        path.name: load_strategy_spec(repo_root / path) for path in SPEC_PATHS.values()
    }
    controls = {
        "R8D01": _scheduled_static_targets(panel.open, {"QQQ": 1.0}),
        "R8D02": _scheduled_static_targets(panel.open, {"TQQQ": 1.0}),
    }

    def fake_segment(*_args, segment_id: str, start_session: str, end_session: str, **_kwargs):
        start = pd.Timestamp(start_session)
        end = pd.Timestamp(end_session)
        frames = {
            "R8M01_LINEAR": _scheduled_static_targets(
                panel.open, {"QQQ": 0.7, "BIL": 0.3}, start=start, end=end
            ),
            "R8M01": _scheduled_static_targets(
                panel.open, {"TQQQ": 0.7, "QQQ": 0.3}, start=start, end=end
            ),
            "R8M02_LINEAR": _scheduled_static_targets(
                panel.open, {"QQQ": 0.6, "BIL": 0.4}, start=start, end=end
            ),
            "R8M02": _scheduled_static_targets(
                panel.open, {"TQQQ": 0.55, "QQQ": 0.25, "BIL": 0.2}, start=start, end=end
            ),
        }
        calibration = [
            {
                "segment_id": segment_id,
                "decision_session": start_session,
                "execution_session": start_session,
                "symbol": D01_CANDIDATE_SYMBOLS[index % len(D01_CANDIDATE_SYMBOLS)],
                "label": index % 2,
                "lgbm_probability": 0.75 if index % 2 else 0.25,
                "linear_probability": 0.55 if index % 2 else 0.45,
                "training_base_probability": 0.5,
                "m01_selected": True,
                "m02_accepted": bool(index % 2),
            }
            for index in range(80)
        ]
        return SegmentResult(
            targets=frames,
            target_records=[],
            model_records=[{"segment_id": segment_id, "model_id": "a" * 64}],
            prediction_records=[{"segment_id": segment_id, "model_id": "a" * 64}],
            calibration_records=calibration,
        )

    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml._stage_e_preflight",
        lambda _root: {
            "status": "ok",
            "snapshot_manifest_sha256": "a" * 64,
            "stage_e_lock_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml.load_r8_ml_panel",
        lambda _root, _manifest: panel,
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml.build_r8_ml_dataset",
        lambda _panel: pd.DataFrame({"execution_session": [sessions[0].date().isoformat()]}),
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml.load_strategy_spec",
        lambda path: specs_by_name[Path(path).name],
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml.compute_d01_targets",
        lambda *_args: (controls["R8D01"], []),
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml.compute_d02_targets",
        lambda *_args: (controls["R8D02"], []),
    )
    monkeypatch.setattr(
        "open_composer.research.dynamic_theme_chain_r8_ml.build_segment_targets",
        fake_segment,
    )

    result = run_dynamic_theme_chain_r8_stage_e(tmp_path)

    assert result.evaluation_path.exists()
    assert result.model_ledger_path.exists()
    assert result.prediction_ledger_path.exists()
    assert result.payload["workflow_pass"] is True
    assert result.payload["paper_ready_pass"] is False
    assert result.payload["broker_writes"] is False
    assert result.payload["pbo"]["partition_count"] == 70
    assert set(result.payload["candidates"]) == {
        "R8D01",
        "R8D02",
        "R8M01_LINEAR",
        "R8M01",
        "R8M02_LINEAR",
        "R8M02",
    }
    assert not list(iteration.glob("stage-e-evaluation.staging-*"))


def _provenance() -> dict[str, str]:
    return {
        "snapshot_manifest_sha256": "a" * 64,
        "feature_contract_sha256": "b" * 64,
        "label_contract_sha256": "c" * 64,
        "validation_contract_sha256": "d" * 64,
        "stage_e_lock_sha256": "e" * 64,
    }


def _scheduled_static_targets(
    opens: pd.DataFrame,
    weights: dict[str, float],
    *,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    sessions = opens.index[[session.weekday() in {0, 2, 4} for session in opens.index]]
    if start is not None:
        prior = sessions[sessions <= start]
        lower = prior[-1] if len(prior) else start
        sessions = sessions[sessions >= lower]
    if end is not None:
        sessions = sessions[sessions <= end]
    target = {symbol: 0.0 for symbol in UNIVERSE}
    target.update(weights)
    return pd.DataFrame([target] * len(sessions), index=sessions, columns=UNIVERSE)


def _synthetic_ml_panel(session_count: int) -> R8MLPanel:
    rng = np.random.default_rng(8208)
    sessions = pd.bdate_range("2019-01-02", periods=session_count)
    market = rng.normal(0.00045, 0.007, session_count)
    technology = rng.normal(0.00065, 0.009, session_count)
    returns: dict[str, np.ndarray] = {}
    for index, symbol in enumerate(UNIVERSE):
        idiosyncratic = rng.normal(0.00005 * (index % 5), 0.005 + 0.0002 * index, session_count)
        values = 0.30 * market + 0.45 * technology + idiosyncratic
        if symbol == "BIL":
            values = np.full(session_count, 0.00012) + idiosyncratic * 0.01
        elif symbol == "SPY":
            values = market
        elif symbol == "QQQ":
            values = 0.25 * market + technology
        elif symbol == "TQQQ":
            values *= 2.4
        elif symbol in {"QLD", "SOXL"}:
            values *= 1.7
        returns[symbol] = np.clip(values, -0.18, 0.18)
    close = pd.DataFrame(
        {symbol: 100.0 * np.cumprod(1.0 + returns[symbol]) for symbol in UNIVERSE},
        index=sessions,
    )
    overnight = pd.DataFrame(
        rng.normal(0.0, 0.002, size=(session_count, len(UNIVERSE))),
        index=sessions,
        columns=UNIVERSE,
    )
    open_price = close.shift(1).fillna(close.iloc[0]) * (1.0 + overnight)
    low = np.minimum(open_price, close) * (
        1.0
        - pd.DataFrame(
            rng.uniform(0.0, 0.015, size=(session_count, len(UNIVERSE))),
            index=sessions,
            columns=UNIVERSE,
        )
    )
    volume = pd.DataFrame(
        {
            symbol: 1_000_000.0
            * (1.0 + index * 0.03)
            * np.exp(rng.normal(0.0, 0.18, session_count))
            for index, symbol in enumerate(UNIVERSE)
        },
        index=sessions,
    )
    return R8MLPanel(open=open_price, low=low, close=close, volume=volume)
