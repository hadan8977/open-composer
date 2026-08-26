from __future__ import annotations

import copy
import json
import math
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import open_composer.research.vix_term_structure_overlay_r1 as vix_r1
from open_composer.market_calendar import us_equity_session_close
from open_composer.research.pit_semantic_theme_r11 import R11PricePanel


@pytest.fixture(autouse=True)
def _restore_vix_iteration_identity() -> None:
    vix_r1.configure_iteration(vix_r1.BASE_ITER_ID)
    yield
    vix_r1.configure_iteration(vix_r1.BASE_ITER_ID)


def _panel(session_count: int = 12) -> R11PricePanel:
    candidates = pd.date_range("2024-01-02", periods=session_count * 2, freq="D")
    sessions = pd.DatetimeIndex(
        [session for session in candidates if us_equity_session_close(session.date())][
            :session_count
        ]
    )
    step = np.arange(session_count, dtype=float)
    opens = pd.DataFrame(
        {
            "TQQQ": 100.0 + step,
            "QQQ": 200.0 + step,
            "BIL": 90.0 + 0.01 * step,
            "SPY": 300.0 + step,
            "XLK": 150.0 + step,
        },
        index=sessions,
    )
    close = opens * 1.001
    return R11PricePanel(
        open=opens,
        low=opens * 0.995,
        close=close,
        volume=pd.DataFrame(1_000_000.0, index=sessions, columns=opens.columns),
        metadata={"scope": "synthetic_only"},
    )


def _packet_frame(session: pd.Timestamp, visible_at: pd.Timestamp) -> pd.DataFrame:
    ratio = 18.0 / 20.0
    row = {
        "observation_date": session - pd.offsets.BDay(1),
        "visible_at": visible_at,
        "input_hash": "1" * 64,
        "vix_to_vix3m_ratio": ratio,
        "normalized_term_slope": 20.0 / 18.0 - 1.0,
        "vix_close": 18.0,
        "vix3m_close": 20.0,
        "vix_high": 19.0,
        "vix_low": 17.0,
        "vix3m_high": 21.0,
        "vix3m_low": 19.0,
    }
    return pd.DataFrame([row], index=pd.DatetimeIndex([session]))


def _state_contract() -> SimpleNamespace:
    return SimpleNamespace(
        feature={
            "state_machine": {
                "thresholds": {
                    "risk_on_ratio_max": 0.95,
                    "stress_ratio_min": 1.0,
                    "crisis_ratio_min": 1.08,
                    "crisis_vix_min": 40.0,
                },
                "confirmation": {"required_consecutive_sessions": 2},
                "initial_route_state": "transition",
            }
        }
    )


def _ml_contract() -> SimpleNamespace:
    return SimpleNamespace(
        validation={
            "ml_training": {
                "calibration_fraction": 0.2,
                "minimum_calibration_rows": 120,
                "retrain_every_sessions": 21,
                "selection_threshold": 0.65,
                "window_cap_sessions": 10_000,
            },
            "ml_override": {"duration_sessions": 5},
        },
        label={"timing": {"embargo_sessions": 5}},
    )


def test_evaluate_rejects_missing_lock_before_data_or_model_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched = False

    def forbidden_loader(_root: Path) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("price loading happened before preflight")

    monkeypatch.setattr(vix_r1, "load_r24_price_panel", forbidden_loader)

    with pytest.raises(ValueError, match="lock is missing"):
        vix_r1.evaluate(tmp_path)

    assert touched is False


def _create_evaluation_state(root: Path, state: str) -> None:
    if state == "output":
        (root / vix_r1.OUTPUT_DIR).mkdir(parents=True)
    elif state == "staging":
        (root / vix_r1.ITERATION_DIR / "evaluation-run.staging-existing").mkdir(parents=True)
    elif state == "attempt":
        path = root / vix_r1.EVALUATION_ATTEMPT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="ascii")
    else:  # pragma: no cover - pytest owns the parameter inventory.
        raise AssertionError(f"unknown evaluation state: {state}")


@pytest.mark.parametrize("state", ["output", "staging", "attempt"])
def test_freeze_rejects_existing_evaluation_state_before_dossier_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    _create_evaluation_state(tmp_path, state)

    def forbidden_validation(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("dossier validation happened after existing state was found")

    monkeypatch.setattr(vix_r1, "validate_iteration_dossier", forbidden_validation)

    with pytest.raises(ValueError, match="state exists before lock"):
        vix_r1.freeze(tmp_path)


@pytest.mark.parametrize("state", ["output", "staging", "attempt"])
def test_evaluate_rejects_existing_evaluation_state_before_price_or_model_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    _create_evaluation_state(tmp_path, state)
    price_or_model_touched = False

    def forbidden_loader(_root: Path) -> object:
        nonlocal price_or_model_touched
        price_or_model_touched = True
        raise AssertionError("price loading happened after existing state was found")

    monkeypatch.setattr(vix_r1, "load_r24_price_panel", forbidden_loader)

    with pytest.raises(ValueError, match="already exists|stale staging"):
        vix_r1.evaluate(tmp_path)

    assert price_or_model_touched is False


def test_evaluation_attempt_reservation_is_exclusive_and_binds_preflight(tmp_path: Path) -> None:
    (tmp_path / vix_r1.ITERATION_DIR).mkdir(parents=True)
    preflight = {
        "lock_path": vix_r1.LOCK_PATH.as_posix(),
        "lock_sha256": "a" * 64,
        "runtime_contract_sha256": "b" * 64,
        "dossier_checked_at": "2026-08-15T00:00:00+00:00",
    }

    binding = vix_r1._reserve_evaluation_attempt(tmp_path, preflight)

    attempt_path = tmp_path / vix_r1.EVALUATION_ATTEMPT_PATH
    payload = json.loads(attempt_path.read_text(encoding="ascii"))
    assert binding["path"] == vix_r1.EVALUATION_ATTEMPT_PATH.as_posix()
    assert payload["iter_id"] == vix_r1.ITER_ID
    assert payload["lock_contract"] == vix_r1.LOCK_CONTRACT_ID
    assert payload["lock_sha256"] == preflight["lock_sha256"]
    assert payload["runtime_contract_sha256"] == preflight["runtime_contract_sha256"]
    assert payload["status"] == "reserved_after_preflight_before_first_price_or_model_operation"
    assert payload["rerun_policy"] == (
        "any_existing_attempt_permanently_blocks_future_evaluation_attempts"
    )

    with pytest.raises(ValueError, match="attempt already exists"):
        vix_r1._reserve_evaluation_attempt(tmp_path, preflight)


def test_evaluate_reserves_attempt_after_preflight_before_price_or_model_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    preflight = {
        "lock_path": vix_r1.LOCK_PATH.as_posix(),
        "lock_sha256": "a" * 64,
        "runtime_contract_sha256": "b" * 64,
        "dossier_checked_at": "2026-08-15T00:00:00+00:00",
    }

    class ExpectedStop(Exception):
        pass

    def fake_preflight(_root: Path) -> dict[str, object]:
        events.append("preflight")
        return preflight

    def fake_reservation(_root: Path, observed: dict[str, object]) -> dict[str, object]:
        assert observed is preflight
        events.append("reservation")
        return {"path": vix_r1.EVALUATION_ATTEMPT_PATH.as_posix()}

    def stop_at_price_load(_root: Path) -> object:
        events.append("price")
        raise ExpectedStop

    monkeypatch.setattr(vix_r1, "_preflight", fake_preflight)
    monkeypatch.setattr(vix_r1, "_reserve_evaluation_attempt", fake_reservation)
    monkeypatch.setattr(vix_r1, "load_and_validate_specs", lambda _root: {})
    monkeypatch.setattr(
        vix_r1, "runtime_contract_from_specs", lambda _specs, root: SimpleNamespace()
    )
    monkeypatch.setattr(vix_r1, "load_r24_price_panel", stop_at_price_load)

    with pytest.raises(ExpectedStop):
        vix_r1.evaluate(tmp_path)

    assert events == ["preflight", "reservation", "price"]


def test_packet_visible_at_equality_is_eligible_and_late_packet_falls_back() -> None:
    panel = _panel()
    decision_session = panel.close.index[1]
    decision_at = vix_r1._decision_close(decision_session)

    equal = vix_r1.build_feature_label_dataset(panel, _packet_frame(decision_session, decision_at))
    equal_row = equal.loc[panel.open.index[2]]
    assert bool(equal_row["packet_available"])
    assert equal_row["packet_reason"] == "visible_at_lte_decision_at"
    assert equal_row["packet_observation_date"] == panel.open.index[0].date().isoformat()

    late = vix_r1.build_feature_label_dataset(
        panel, _packet_frame(decision_session, decision_at + pd.Timedelta(nanoseconds=1))
    )
    late_row = late.loc[panel.open.index[2]]
    assert not bool(late_row["packet_available"])
    assert late_row["packet_reason"] == "visible_after_decision_exact_fallback"
    assert all(math.isnan(float(late_row[name])) for name in vix_r1.VIX_FEATURES)


def test_path_survival_uses_t_plus_1_through_t_plus_6_boundaries() -> None:
    assert vix_r1.path_survival_label([100.0, 90.0, 100.0, 101.0, 102.0, 103.0]) == 1
    assert vix_r1.path_survival_label([100.0, 100.0, 100.0, 100.0, 100.0, 94.0]) == 0
    with pytest.raises(ValueError, match="six"):
        vix_r1.path_survival_label([100.0] * 5)

    panel = _panel(10)
    dataset = vix_r1.build_feature_label_dataset(panel, pd.DataFrame())
    first = dataset.iloc[0]
    assert first["execution_position"] == 1
    assert first["label_end_position"] == 6
    assert first["label_end_session"] == panel.open.index[6].date().isoformat()


def test_vix_state_machine_confirms_risk_on_and_enters_crisis_immediately() -> None:
    sessions = pd.bdate_range("2024-02-01", periods=7)
    dataset = pd.DataFrame(
        {
            "decision_session": [session.date().isoformat() for session in sessions],
            "packet_available": [True, True, True, True, True, True, False],
            "vix_to_vix3m_ratio": [0.94, 0.94, 0.97, 1.00, 0.94, 1.08, np.nan],
            "vix_close": [20.0] * 6 + [np.nan],
            "packet_input_hash": ["a"] * 6 + [None],
        },
        index=sessions,
    )

    states, records = vix_r1.build_vix_route_states(dataset, _state_contract())

    assert states.tolist() == [
        "transition",
        "risk_on",
        "risk_on",
        "transition",
        "transition",
        "crisis",
        None,
    ]
    assert records[0]["risk_on_confirmation_count"] == 1
    assert records[1]["risk_on_confirmation_count"] == 2
    assert records[5]["raw_state"] == "crisis"


def test_chronological_folds_preserve_absolute_execution_positions() -> None:
    full = pd.bdate_range("2017-02-01", periods=2388)
    contract = SimpleNamespace(
        validation={
            "chronological_folds": {
                "first_oos_index": 756,
                "count": 4,
                "oos_sessions": 408,
                "purge_sessions": 5,
                "embargo_sessions": 5,
            },
            "common_start": {"first_oos_session": full[756].date().isoformat()},
        }
    )

    panel_folds = vix_r1.chronological_folds(full, contract)
    dataset_folds = vix_r1.chronological_folds(full[1:], contract)

    assert panel_folds == dataset_folds
    assert panel_folds[0]["execution_position_start"] == 756
    assert panel_folds[-1]["execution_position_end"] == 2387


def test_refit_schedule_reuses_models_for_twenty_intervening_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = pd.bdate_range("2024-03-01", periods=45)
    panel = _panel(45)
    panel = R11PricePanel(
        open=panel.open.set_axis(sessions),
        low=panel.low.set_axis(sessions),
        close=panel.close.set_axis(sessions),
        volume=panel.volume.set_axis(sessions),
        metadata=panel.metadata,
    )
    dataset = pd.DataFrame(index=sessions)
    dataset["decision_session"] = [session.date().isoformat() for session in sessions]
    dataset["execution_position"] = np.arange(100, 145)
    dataset["label_end_position"] = np.arange(90, 135)
    dataset["path_survival"] = np.arange(45) % 2
    dataset["feature_complete"] = True
    dataset["packet_available"] = True
    dataset["packet_input_hash"] = "b" * 64
    for feature_number, feature in enumerate(vix_r1.ALL_FEATURES):
        dataset[feature] = np.sin(np.arange(45) + feature_number)
    q01 = pd.DataFrame(
        [{symbol: float(symbol == "TQQQ") for symbol in panel.open.columns}] * len(sessions),
        index=sessions,
    )
    deterministic = {"V1Q01": q01}
    folds = [
        {
            "fold_id": "F1",
            "execution_position_start": 100,
            "execution_position_end": 144,
        }
    ]
    calls: list[tuple[str, int]] = []

    def fake_fit(
        candidate_id: str,
        _fit: pd.DataFrame,
        _calibration: pd.DataFrame,
        **kwargs: object,
    ) -> tuple[SimpleNamespace, dict[str, object]]:
        ordinal = int(kwargs["refit_ordinal"])
        calls.append((candidate_id, ordinal))
        model_id = f"{candidate_id}:{ordinal}"
        return SimpleNamespace(model_id=model_id), {
            "candidate_id": candidate_id,
            "model_id": model_id,
        }

    monkeypatch.setattr(vix_r1, "_fit_survival_model", fake_fit)
    monkeypatch.setattr(vix_r1, "_prediction_probability", lambda _model, _row: (1.0, 0.90))

    targets, _models, predictions, _indices = vix_r1.build_ml_targets(
        panel,
        dataset,
        deterministic,
        folds,
        _ml_contract(),
    )

    assert Counter(ordinal for _candidate, ordinal in calls) == {0: 4, 1: 4, 2: 4}
    m01 = [row for row in predictions if row["candidate_id"] == "V1M01"]
    assert m01[0]["model_id"] == m01[20]["model_id"] == "V1M01:0"
    assert m01[21]["model_id"] == m01[41]["model_id"] == "V1M01:1"
    assert m01[42]["model_id"] == "V1M01:2"
    assert vix_r1.canonical_target_bytes(targets["V1F01"]) == vix_r1.canonical_target_bytes(
        targets["V1M01"]
    )


def _candidate_target_inputs() -> tuple[
    pd.DataFrame,
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    sessions = pd.bdate_range("2024-01-02", periods=2)
    columns = ["TQQQ", "QQQ", "BIL", "SPY", "XLK"]

    def frame(candidate_id: str) -> pd.DataFrame:
        value = float(vix_r1.CANDIDATE_IDS.index(candidate_id) + 1)
        return pd.DataFrame(value, index=sessions, columns=columns)

    r01 = frame("V1R01")
    deterministic = {
        candidate_id: frame(candidate_id) for candidate_id in ("V1Q01", "V1V01", "V1D02")
    }
    ml_targets = {
        candidate_id: frame(candidate_id)
        for candidate_id in ("V1M01", "V1M02", "V1C01", "V1P01", "V1F01")
    }
    return r01, deterministic, ml_targets


def test_complete_candidate_target_assembly_uses_frozen_inventory_order() -> None:
    r01, deterministic, ml_targets = _candidate_target_inputs()

    targets = vix_r1._assemble_candidate_targets(r01, deterministic, ml_targets)

    assert tuple(targets) == vix_r1.CANDIDATE_IDS
    assert targets["V1R01"] is r01
    for candidate_id in (*deterministic, *ml_targets):
        source = deterministic.get(candidate_id, ml_targets.get(candidate_id))
        assert targets[candidate_id] is source


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate"])
def test_invalid_candidate_target_inventory_stops_before_return_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    r01, deterministic, ml_targets = _candidate_target_inputs()
    if mutation == "missing":
        ml_targets.pop("V1M02")
    elif mutation == "extra":
        ml_targets["V1X01"] = r01.copy()
    elif mutation == "duplicate":
        ml_targets["V1Q01"] = r01.copy()
    else:  # pragma: no cover - pytest owns the parameter inventory.
        raise AssertionError(f"unknown inventory mutation: {mutation}")

    return_evaluation_touched = False

    def forbidden_return_evaluation(*_args: object, **_kwargs: object) -> object:
        nonlocal return_evaluation_touched
        return_evaluation_touched = True
        raise AssertionError("candidate returns were evaluated for an invalid inventory")

    sessions = pd.bdate_range("2024-01-02", periods=4 * 408)
    panel = SimpleNamespace(open=pd.DataFrame(index=sessions))
    contract = SimpleNamespace(validation={"chronological_folds": {"first_oos_index": 0}})
    monkeypatch.setattr(
        vix_r1,
        "_preflight",
        lambda _root: {
            "lock_path": vix_r1.LOCK_PATH.as_posix(),
            "lock_sha256": "a" * 64,
            "runtime_contract_sha256": "b" * 64,
            "dossier_checked_at": "2026-08-15T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        vix_r1,
        "_reserve_evaluation_attempt",
        lambda _root, _preflight: {"path": vix_r1.EVALUATION_ATTEMPT_PATH.as_posix()},
    )
    monkeypatch.setattr(vix_r1, "load_and_validate_specs", lambda _root: {})
    monkeypatch.setattr(vix_r1, "runtime_contract_from_specs", lambda _specs, root: contract)
    monkeypatch.setattr(vix_r1, "load_r24_price_panel", lambda _root: panel)
    monkeypatch.setattr(vix_r1, "build_and_verify_r01", lambda _root, _panel: (r01, {}))
    monkeypatch.setattr(vix_r1, "_subset_panel", lambda _panel: panel)
    monkeypatch.setattr(vix_r1, "load_and_validate_packets", lambda _root: pd.DataFrame())
    monkeypatch.setattr(
        vix_r1, "build_feature_label_dataset", lambda _panel, _packets: pd.DataFrame(index=sessions)
    )
    monkeypatch.setattr(vix_r1, "chronological_folds", lambda _index, _contract: [])
    monkeypatch.setattr(
        vix_r1,
        "build_deterministic_targets",
        lambda *_args, **_kwargs: (deterministic, []),
    )
    monkeypatch.setattr(
        vix_r1,
        "build_ml_targets",
        lambda *_args, **_kwargs: (ml_targets, [], [], []),
    )
    monkeypatch.setattr(vix_r1, "_evaluate_candidates", forbidden_return_evaluation)

    expected_message = "duplicates" if mutation == "duplicate" else "inventory changed"
    with pytest.raises(ValueError, match=expected_message):
        vix_r1.evaluate(tmp_path)

    assert return_evaluation_touched is False


def test_placebo_uses_one_joint_fit_only_vix_row_permutation() -> None:
    rows = 20
    frame = pd.DataFrame(
        {
            "decision_session": [f"d{index}" for index in range(rows)],
            "path_survival": np.arange(rows) % 2,
            **{
                feature: np.arange(rows, dtype=float) + feature_number / 100.0
                for feature_number, feature in enumerate(vix_r1.PRICE_FEATURES)
            },
            **{
                feature: np.arange(rows, dtype=float) * 100.0 + feature_number
                for feature_number, feature in enumerate(vix_r1.VIX_FEATURES)
            },
        }
    )
    calibration = frame.copy(deep=True)

    permuted, permutation = vix_r1._joint_permute_vix_fit_rows(
        frame,
        base_seed=15108,
        fold_id="F2",
        refit_ordinal=3,
        split_id="fit_rows",
    )

    assert not np.array_equal(permutation, np.arange(rows))
    pd.testing.assert_frame_equal(
        permuted.loc[:, list(vix_r1.PRICE_FEATURES)], frame.loc[:, list(vix_r1.PRICE_FEATURES)]
    )
    pd.testing.assert_series_equal(permuted["path_survival"], frame["path_survival"])
    np.testing.assert_array_equal(
        permuted.loc[:, list(vix_r1.VIX_FEATURES)].to_numpy(),
        frame.loc[:, list(vix_r1.VIX_FEATURES)].to_numpy()[permutation],
    )
    pd.testing.assert_frame_equal(calibration, frame)


def test_strict_pbo_evaluates_all_70_partitions_and_ties_contribute_half() -> None:
    sessions = pd.bdate_range("2023-01-03", periods=160)
    stream = 0.0002 + np.sin(np.arange(len(sessions), dtype=float) / 7.0) * 0.01
    returns = pd.DataFrame(
        {candidate_id: stream for candidate_id in vix_r1.SELECTABLE_IDS},
        index=sessions,
    )

    interval_starts = pd.bdate_range("2023-01-02", periods=160)
    row_identities = [
        {
            "fold_id": f"F{position // 40 + 1}",
            "interval_start": interval_starts[position],
            "interval_end": session,
        }
        for position, session in enumerate(sessions)
    ]
    result = vix_r1.probability_backtest_overfitting_vix_r1(
        returns,
        return_row_identities=row_identities,
    )

    assert result["partition_count"] == result["valid_partition_count"] == 70
    assert result["probability"] == pytest.approx(0.5)
    assert result["candidate_ids"] == list(vix_r1.SELECTABLE_IDS)
    assert result["expected_block_observation_counts"] == [20] * 8
    assert result["return_source_row_identity_schema"] == [
        "row_position",
        "fold_id",
        "interval_start",
        "interval_end",
    ]
    assert result["return_source_fold_counts"] == {
        "F1": 40,
        "F2": 40,
        "F3": 40,
        "F4": 40,
    }
    assert result["return_source_first_identity"]["interval_end"] == sessions[0].isoformat()
    assert len(result["return_source_row_identity_sha256"]) == 64
    assert len(result["return_source_rows_sha256"]) == 64
    assert all(
        row["fractional_overfit_contribution"] == pytest.approx(0.5) for row in result["partitions"]
    )
    with pytest.raises(ValueError, match="exact six selection candidates"):
        vix_r1.probability_backtest_overfitting_vix_r1(
            returns.loc[:, list(reversed(vix_r1.SELECTABLE_IDS))],
            return_row_identities=row_identities,
            candidate_ids=list(reversed(vix_r1.SELECTABLE_IDS)),
        )


def test_strict_pbo_rejects_constant_candidate_stream() -> None:
    sessions = pd.bdate_range("2023-01-03", periods=80)
    values = np.sin(np.arange(len(sessions), dtype=float) / 9.0) * 0.01
    returns = pd.DataFrame(
        {
            candidate_id: np.zeros(len(sessions)) if candidate_id == "V1M02" else values
            for candidate_id in vix_r1.SELECTABLE_IDS
        },
        index=sessions,
    )

    with pytest.raises(ValueError, match="zero variance"):
        vix_r1.probability_backtest_overfitting_vix_r1(
            returns,
            return_row_identities=[
                {
                    "fold_id": f"F{position // 20 + 1}",
                    "interval_start": session - pd.offsets.BDay(1),
                    "interval_end": session,
                }
                for position, session in enumerate(sessions)
            ],
        )


def test_terminal_free_prior_daily_rows_reverse_only_sealed_terminal_cost() -> None:
    terminal_factor = 0.998
    sealed_rows = [
        {
            "schema_version": 1,
            "iter_id": "mom_high_beta_sleeve_ensemble_r1",
            "candidate_id": "S1D01",
            "session": "2026-07-31",
            "net_return": 0.02,
            "cost_bps": 20.0,
        },
        {
            "schema_version": 1,
            "iter_id": "mom_high_beta_sleeve_ensemble_r1",
            "candidate_id": "S1D01",
            "session": "2026-08-03",
            "net_return": (1.0 - 0.015) * terminal_factor - 1.0,
            "cost_bps": 20.0,
        },
    ]
    report = {
        "candidates": {
            "S1D01": {
                "cost_views": {
                    "primary_20bps": {
                        "with_terminal": {
                            "cumulative_cost_factor": 0.9 * terminal_factor,
                            "terminal_liquidation_count": 1,
                        },
                        "without_terminal": {
                            "cumulative_cost_factor": 0.9,
                            "terminal_liquidation_count": 0,
                        },
                    }
                }
            }
        }
    }

    transformed, observed_factor = vix_r1._terminal_free_prior_daily_rows(
        report,
        sealed_rows,
        view_name="primary_20bps",
    )

    assert observed_factor == pytest.approx(terminal_factor)
    assert transformed[0] == sealed_rows[0]
    assert transformed[-1]["net_return"] == pytest.approx(-0.015)
    assert sealed_rows[-1]["net_return"] != transformed[-1]["net_return"]


def test_prior_target_window_keeps_last_state_before_oos_start() -> None:
    sessions = pd.DatetimeIndex(
        pd.to_datetime(["2022-06-01", "2022-07-01", "2022-08-01", "2022-09-01"])
    )
    target = pd.DataFrame(
        {"TQQQ": [0.0, 0.5, 0.5, 1.0], "BIL": [1.0, 0.5, 0.5, 0.0]},
        index=sessions,
    )

    window = vix_r1._target_window_with_prestart_state(
        target,
        start=pd.Timestamp("2022-07-27"),
        end=pd.Timestamp("2022-09-01"),
    )

    assert list(window.index) == list(sessions[1:])
    assert window.index[0] < pd.Timestamp("2022-07-27")


def test_sealed_prior_result_survives_current_registry_evolution(repo_root: Path) -> None:
    prior_lock = vix_r1._load_json(repo_root / vix_r1.PRIOR_LOCK_PATH)
    registry_binding = next(
        row for row in prior_lock["external_inputs"] if row["path"] == "capabilities/registry.yaml"
    )
    assert vix_r1._sha256(repo_root / "capabilities/registry.yaml") != registry_binding["sha256"]

    result = vix_r1._verify_sealed_prior_r1_artifacts(repo_root)

    assert result["lock_sha256"] == vix_r1._sha256(repo_root / vix_r1.PRIOR_LOCK_PATH)
    assert result["receipt_sha256"] == vix_r1._sha256(repo_root / vix_r1.PRIOR_RECEIPT_PATH)


@pytest.mark.parametrize(
    ("research_pass", "ml_contribution_pass", "ml_strategy_pass"),
    [
        (True, True, True),
        (True, True, False),
        (True, False, True),
        (True, False, False),
        (False, True, True),
        (False, True, False),
        (False, False, True),
        (False, False, False),
    ],
)
def test_strategy_group_requires_research_ml_incremental_value_and_ml_family_pass(
    research_pass: bool,
    ml_contribution_pass: bool,
    ml_strategy_pass: bool,
) -> None:
    strategy_group_pass, decision, _interpretation = vix_r1._strategy_group_outcome(
        research_pass=research_pass,
        ml_contribution_pass=ml_contribution_pass,
        ml_strategy_pass=ml_strategy_pass,
    )

    expected_pass = research_pass and ml_contribution_pass and ml_strategy_pass
    assert strategy_group_pass is expected_pass
    assert decision == ("continue" if expected_pass else "stop")


def test_repair_sharpe_gate_is_strict_while_base_contract_remains_inclusive() -> None:
    base_gate = {"Sharpe_floor": 0.8, "Sharpe_operator": "greater_than_or_equal"}
    repair_gate = {"Sharpe_floor": 1.0, "Sharpe_operator": "strictly_greater_than"}

    assert vix_r1._passes_sharpe_gate(0.8, base_gate) is True
    assert vix_r1._passes_sharpe_gate(math.nextafter(0.8, 0.0), base_gate) is False
    assert vix_r1._passes_sharpe_gate(1.0, repair_gate) is False
    assert vix_r1._passes_sharpe_gate(math.nextafter(1.0, math.inf), repair_gate) is True


def _iteration_identity_snapshot() -> dict[str, object]:
    return {
        "iter_id": vix_r1.ITER_ID,
        "strategy_stem": vix_r1.STRATEGY_STEM,
        "iteration_dir": vix_r1.ITERATION_DIR,
        "lock_path": vix_r1.LOCK_PATH,
        "output_dir": vix_r1.OUTPUT_DIR,
        "attempt_path": vix_r1.EVALUATION_ATTEMPT_PATH,
        "source_cards_path": vix_r1.SOURCE_CARDS_PATH,
        "factor_library_path": vix_r1.FACTOR_LIBRARY_PATH,
        "spec_paths": tuple(vix_r1.SPEC_PATHS.items()),
        "iteration_files": vix_r1.ITERATION_FILES,
        "external_inputs": tuple(vix_r1.EXTERNAL_INPUT_PATHS.items()),
        "lock_status": vix_r1.LOCK_STATUS,
        "lock_contract": vix_r1.LOCK_CONTRACT_ID,
    }


def test_configure_iteration_isolates_base_repair_and_base_identity() -> None:
    vix_r1.configure_iteration(vix_r1.BASE_ITER_ID)
    base_before = _iteration_identity_snapshot()

    vix_r1.configure_iteration(vix_r1.REPAIR_ITER_ID)
    repair = _iteration_identity_snapshot()

    assert repair["iter_id"] == "mom_vix_term_structure_overlay_r1_implfix1"
    assert repair["strategy_stem"] == "us_vix_term_structure_overlay_r1_implfix1"
    assert repair["iteration_dir"] == Path(
        "reports/research/iterations/mom_vix_term_structure_overlay_r1_implfix1"
    )
    assert repair["lock_path"] == repair["iteration_dir"] / (
        "lock-set/historical-evaluation-lock.json"
    )
    assert repair["output_dir"] == repair["iteration_dir"] / "evaluation-run"
    assert repair["attempt_path"] == repair["iteration_dir"] / "evaluation-attempt.json"
    assert repair["lock_contract"] == (
        "vix_term_structure_overlay_r1_implfix1_historical_evaluation_v1"
    )
    assert len(repair["iteration_files"]) == len(vix_r1.BASE_ITERATION_FILES) + 2
    assert len(repair["external_inputs"]) == 13
    assert all(
        "us_vix_term_structure_overlay_r1_implfix1" in path.as_posix()
        for _candidate_id, path in repair["spec_paths"]
    )

    vix_r1.configure_iteration(vix_r1.BASE_ITER_ID)
    assert _iteration_identity_snapshot() == base_before
    assert len(base_before["external_inputs"]) == 12


def _passing_gate_inputs(repo_root: Path) -> dict[str, object]:
    specs = vix_r1.load_and_validate_specs(repo_root)
    contract = vix_r1.runtime_contract_from_specs(specs, repo_root)
    sessions = pd.bdate_range("2024-01-03", periods=12)
    fold_starts = [sessions[0] - pd.offsets.BDay(1), sessions[3], sessions[6], sessions[9]]
    folds = [
        {
            "fold_id": f"F{position + 1}",
            "test_start": start.date().isoformat(),
            "test_end": sessions[min((position + 1) * 3, len(sessions) - 1)].date().isoformat(),
            "qqq_cagr_lift_pct_points": 1.0,
        }
        for position, start in enumerate(fold_starts)
    ]
    passing_metrics = {
        "cagr": 0.50,
        "cagr_pct": 50.0,
        "max_drawdown_pct": -50.0,
        "annualized_sharpe_excess_BIL": 1.0,
        "mar": 1.0,
        "tqqq_up_capture": 0.90,
        "tqqq_down_capture": 0.80,
    }
    target_hashes = {candidate_id: candidate_id for candidate_id in vix_r1.CANDIDATE_IDS}
    target_hashes["V1F01"] = target_hashes["V1M01"] = "matched-m01-f01"
    candidates = {
        candidate_id: {
            "cost_views": {"primary_20bps": {"terminal_free": dict(passing_metrics)}},
            "folds": [dict(row) for row in folds],
            "target_stream_sha256": target_hashes[candidate_id],
        }
        for candidate_id in vix_r1.CANDIDATE_IDS
    }
    benchmarks = {
        "QQQ_buy_hold": {
            "cost_views": {"primary_20bps": {"terminal_free": {"cagr": 0.30, "cagr_pct": 30.0}}}
        },
        "TQQQ_buy_hold_same_symbol": {
            "cost_views": {"primary_20bps": {"terminal_free": {"cagr": 0.55}}}
        },
    }
    dsr = {candidate_id: {"promotion_probability": 0.80} for candidate_id in vix_r1.SELECTABLE_IDS}
    pbo = {"probability": 0.30, "valid_partition_count": 70}
    levels = {
        "V1R01": 0.001,
        "V1Q01": 0.001,
        "V1V01": 0.002,
        "V1D02": 0.003,
        "V1M01": 0.004,
        "V1M02": 0.005,
        "V1C01": 0.006,
        "V1F01": 0.004,
        "V1P01": 0.0,
    }
    return_streams = {
        candidate_id: pd.Series(level, index=sessions, dtype=float)
        for candidate_id, level in levels.items()
    }

    predictions: list[dict[str, object]] = []
    for candidate_id in ("V1M01", "V1M02", "V1C01"):
        for position, session in enumerate(sessions):
            effective_override = position < 8
            fallback_hash = "q01-target"
            selected_hash = (
                f"{candidate_id}-override-{position}" if effective_override else fallback_hash
            )
            fallback_candidate_id = "V1Q01"
            fallback_reason = None
            if candidate_id == "V1M01" and position == 8:
                effective_override = True
                selected_hash = "m01-active-override"
            if candidate_id == "V1C01" and position == 8:
                effective_override = False
                fallback_hash = selected_hash = "m01-active-override"
                fallback_candidate_id = "V1M01"
                fallback_reason = "missing_vix_exact_candidate_fallback"
            predictions.append(
                {
                    "candidate_id": candidate_id,
                    "execution_session": session.date().isoformat(),
                    "effective_override": effective_override,
                    "fallback_candidate_id": fallback_candidate_id,
                    "fallback_reason": fallback_reason,
                    "fallback_target_sha256": fallback_hash,
                    "selected_target_sha256": selected_hash,
                }
            )
    model_records = [
        {
            "candidate_id": candidate_id,
            "status": "fitted_and_chronologically_calibrated",
            "calibration_row_count": 120,
            "class_checks": {
                "calibration_rows": True,
                "calibration_positive": True,
                "calibration_negative": True,
            },
            "calibrated_brier": 0.20,
        }
        for candidate_id in ("V1M01", "V1M02", "V1C01")
    ]
    replication = {
        "status": "pass",
        "target_identity": True,
        "terminal_free_daily_return_identity": True,
        "terminal_free_metric_identity": True,
    }

    return {
        "candidates": candidates,
        "benchmarks": benchmarks,
        "dsr": dsr,
        "pbo": pbo,
        "predictions": predictions,
        "model_records": model_records,
        "return_streams": return_streams,
        "replication": replication,
        "contract": contract,
    }


def test_complete_gate_semantics_keep_c01_main_and_incremental_fallbacks_separate(
    repo_root: Path,
) -> None:
    inputs = _passing_gate_inputs(repo_root)

    candidate_gates, gate_payload = vix_r1._candidate_and_family_gates(**inputs)

    assert gate_payload["research_pass"] is True
    assert gate_payload["ml_contribution_pass"] is True
    assert gate_payload["ml"]["V1C01"]["fallback_candidate_id"] == "V1Q01"
    assert gate_payload["combined_vs_price_ML"]["fallback_candidate_id"] == "V1M01"
    assert gate_payload["ml"]["V1C01"]["c01_missing_VIX_exact_M01_and_F01_identity"] is True
    assert gate_payload["modality"]["checks"]["V1V01_folds_beating_V1Q01"] is True
    assert gate_payload["modality"]["checks"]["V1D02_folds_beating_V1Q01"] is True
    assert candidate_gates["V1D02"]["pass"] is True

    corrupted = [dict(row) for row in inputs["predictions"]]
    missing_row = next(
        row
        for row in corrupted
        if row["candidate_id"] == "V1C01"
        and row["fallback_reason"] == "missing_vix_exact_candidate_fallback"
    )
    missing_row["fallback_target_sha256"] = missing_row["selected_target_sha256"] = "wrong-m01"
    _candidate_gates, corrupted_payload = vix_r1._candidate_and_family_gates(
        **{**inputs, "predictions": corrupted}
    )

    assert corrupted_payload["research_pass"] is True
    assert corrupted_payload["ml_contribution_pass"] is False
    assert corrupted_payload["ml"]["V1C01"]["checks"]["exact_fallback_required"] is False

    all_override = [dict(row) for row in inputs["predictions"]]
    for row in all_override:
        if row["candidate_id"] == "V1M02":
            row["effective_override"] = True
            row["selected_target_sha256"] = "always-override"
    _candidate_gates, all_override_payload = vix_r1._candidate_and_family_gates(
        **{**inputs, "predictions": all_override}
    )

    assert all_override_payload["ml"]["V1M02"]["checks"]["exact_fallback_required"] is False


@pytest.mark.parametrize(
    ("mutation", "check_group", "check_name", "expected_research", "expected_ml"),
    [
        (
            "upside_retention",
            "ml",
            "minimum_primary_upside_capture_retained",
            True,
            False,
        ),
        ("missing_calibration", "ml", "calibration_required", True, False),
        ("invalid_calibration", "ml", "calibration_required", True, False),
        (
            "v01_modality",
            "modality",
            "V1V01_aggregate_after_cost_lift_over_V1Q01_strictly_positive",
            False,
            True,
        ),
        (
            "d02_fold_gate",
            "modality",
            "V1D02_folds_beating_V1Q01",
            False,
            True,
        ),
    ],
)
def test_gate_counterexamples_fail_their_named_status_only(
    repo_root: Path,
    mutation: str,
    check_group: str,
    check_name: str,
    expected_research: bool,
    expected_ml: bool,
) -> None:
    inputs = copy.deepcopy(_passing_gate_inputs(repo_root))

    if mutation == "upside_retention":
        inputs["candidates"]["V1M02"]["cost_views"]["primary_20bps"]["terminal_free"][
            "tqqq_up_capture"
        ] = 0.85
    elif mutation == "missing_calibration":
        inputs["model_records"] = [
            row for row in inputs["model_records"] if row["candidate_id"] != "V1M02"
        ]
    elif mutation == "invalid_calibration":
        record = next(row for row in inputs["model_records"] if row["candidate_id"] == "V1M02")
        record["calibrated_brier"] = math.nan
    elif mutation == "v01_modality":
        inputs["return_streams"]["V1V01"] = inputs["return_streams"]["V1Q01"].copy()
    elif mutation == "d02_fold_gate":
        q01 = inputs["return_streams"]["V1Q01"]
        folds = inputs["candidates"]["V1D02"]["folds"]
        scopes = vix_r1._return_scope_ids(pd.DatetimeIndex(q01.index), folds)
        inputs["return_streams"]["V1D02"] = pd.Series(
            [0.002 if scope in {"F1", "F2"} else 0.0 for scope in scopes],
            index=q01.index,
            dtype=float,
        )
    else:  # pragma: no cover - pytest owns the parameter inventory.
        raise AssertionError(f"unknown mutation: {mutation}")

    _candidate_gates, gate_payload = vix_r1._candidate_and_family_gates(**inputs)

    if check_group == "ml":
        checks = gate_payload["ml"]["V1M02"]["checks"]
    else:
        checks = gate_payload["modality"]["checks"]
    assert checks[check_name] is False
    assert gate_payload["research_pass"] is expected_research
    assert gate_payload["ml_contribution_pass"] is expected_ml


def test_dsr_uses_frozen_trial_count_and_minimum_of_iid_and_hac() -> None:
    rng = np.random.default_rng(16101)
    innovations = rng.normal(0.0, 0.008, 504)
    values = np.empty_like(innovations)
    values[0] = innovations[0]
    for index in range(1, len(values)):
        values[index] = 0.35 * values[index - 1] + innovations[index] + 0.0004
    result = vix_r1.deflated_sharpe_ratio_vix_r1(pd.Series(values))

    assert result["trial_count"] == 8147
    assert result["hac_lag"] == 21
    assert result["scope_count"] == 1
    assert result["hac_scope"] == "single_continuous_terminal_free_OOS_return_stream"
    assert result["promotion_probability"] == min(
        result["iid_probability"], result["hac_probability"]
    )
    with pytest.raises(ValueError, match="trial count"):
        vix_r1.deflated_sharpe_ratio_vix_r1(pd.Series(values), trial_count=8146)


def test_dsr_evidence_hac_scope_must_match_frozen_contract(repo_root: Path) -> None:
    specs = vix_r1.load_and_validate_specs(repo_root)
    contract = vix_r1.runtime_contract_from_specs(specs, repo_root)
    expected_scope = contract.validation["dsr"]["hac_scope"]
    dsr = {candidate_id: {"hac_scope": expected_scope} for candidate_id in vix_r1.CANDIDATE_IDS}

    vix_r1._validate_dsr_evidence_identity(dsr, contract)

    drifted = copy.deepcopy(dsr)
    drifted["V1C01"]["hac_scope"] = "four_fold_reset"
    with pytest.raises(ValueError, match="HAC scope"):
        vix_r1._validate_dsr_evidence_identity(drifted, contract)


def test_continuous_return_fold_assignment_has_no_missing_boundary_interval() -> None:
    sessions = pd.bdate_range("2020-01-02", periods=1632)
    folds = [
        {
            "fold_id": f"F{number + 1}",
            "test_start": sessions[number * 408].date().isoformat(),
            "test_end": sessions[(number + 1) * 408 - 1].date().isoformat(),
        }
        for number in range(4)
    ]

    scopes = vix_r1._return_scope_ids(sessions[1:], folds)

    assert Counter(scopes) == {"F1": 408, "F2": 408, "F3": 408, "F4": 407}
    assert scopes[407] == "F1"
    assert scopes[408] == "F2"


def test_fitted_model_identity_binds_feature_values_and_frozen_provenance(
    repo_root: Path,
) -> None:
    specs = vix_r1.load_and_validate_specs(repo_root)
    contract = vix_r1.runtime_contract_from_specs(specs, repo_root)
    sessions = pd.bdate_range("2018-01-02", periods=620)
    rows = np.arange(len(sessions), dtype=float)
    frame = pd.DataFrame(index=sessions)
    frame["decision_session"] = [session.date().isoformat() for session in sessions]
    frame["label_end_position"] = np.arange(5, 625)
    frame["path_survival"] = np.arange(len(sessions)) % 2
    frame["packet_input_hash"] = "c" * 64
    for number, feature in enumerate(vix_r1.PRICE_FEATURES, start=1):
        frame[feature] = np.sin(rows / number) + np.cos(rows / (number + 1))
    fit = frame.iloc[:500].copy()
    calibration = frame.iloc[500:].copy()

    first, first_record = vix_r1._fit_survival_model(
        "V1M01",
        fit,
        calibration,
        fold_id="F1",
        refit_ordinal=0,
        common_index_sha256="d" * 64,
        contract=contract,
    )
    changed = fit.copy(deep=True)
    changed.iloc[0, changed.columns.get_loc(vix_r1.PRICE_FEATURES[0])] += 0.001
    second, second_record = vix_r1._fit_survival_model(
        "V1M01",
        changed,
        calibration,
        fold_id="F1",
        refit_ordinal=0,
        common_index_sha256="d" * 64,
        contract=contract,
    )

    assert first is not None and second is not None
    assert first.model_id != second.model_id
    assert first_record["fit_feature_values_sha256"] != second_record["fit_feature_values_sha256"]
    provenance = first_record["frozen_provenance"]
    assert provenance["runtime_contract_sha256"] == contract.sha256
    assert provenance["prompt"] == {
        "applicable": False,
        "prompt_hash": None,
        "reason": "quant_only_model_no_prompt",
    }


def test_runtime_contract_binds_all_23_files_and_f01_has_no_model(repo_root: Path) -> None:
    specs = vix_r1.load_and_validate_specs(repo_root)
    contract = vix_r1.runtime_contract_from_specs(specs, repo_root)

    assert len(contract.file_bindings) == 23
    assert contract.effective_trial_count == 8147
    assert contract.cost_views == {
        "low_10bps": 10.0,
        "primary_20bps": 20.0,
        "severe_40bps": 40.0,
    }
    assert specs["V1F01"].model is None


def test_generated_repair_runtime_contract_accepts_exact_governance_bindings(
    repo_root: Path,
) -> None:
    vix_r1.configure_iteration(vix_r1.REPAIR_ITER_ID)

    specs = vix_r1.load_and_validate_specs(repo_root)
    contract = vix_r1.runtime_contract_from_specs(specs, repo_root)

    assert len(specs) == len(vix_r1.CANDIDATE_IDS) == 9
    assert len(contract.file_bindings) == 25
    assert contract.effective_trial_count == 8147
    assert contract.manifest["contracts"]["governance"] == {
        "vix_r1_parent_failure_audit_v1": contract.file_bindings["parent-failure-audit.json"],
        "vix_r1_pure_implementation_repair_v1": contract.file_bindings[
            "implementation-repair-contract.json"
        ],
    }


def _repair_identity_contract(repo_root: Path) -> vix_r1.VixRuntimeContract:
    vix_r1.configure_iteration(vix_r1.REPAIR_ITER_ID)
    parent_binding = vix_r1._binding(vix_r1.SOURCE_ITERATION_LOCK_PATH, repo_root)
    parent_lock = vix_r1._load_json(repo_root / vix_r1.SOURCE_ITERATION_LOCK_PATH)
    parent_snapshots = parent_lock["runtime_contract"]["candidate_specs"]
    audit_binding = {
        "path": (vix_r1.ITERATION_DIR / "parent-failure-audit.json").as_posix(),
        "sha256": "c" * 64,
        "size_bytes": 1,
    }
    repair_binding = {
        "path": (vix_r1.ITERATION_DIR / "implementation-repair-contract.json").as_posix(),
        "sha256": "d" * 64,
        "size_bytes": 2,
    }
    candidate_specs: dict[str, dict[str, object]] = {}
    manifest_rows: list[dict[str, object]] = []
    equivalence_rows: list[dict[str, object]] = []
    for position, candidate_id in enumerate(vix_r1.CANDIDATE_IDS, start=1):
        source_snapshot = parent_snapshots[candidate_id]
        repair_spec = copy.deepcopy(source_snapshot["spec"])
        repair_spec["name"] = f"{vix_r1.STRATEGY_STEM}_{candidate_id.lower()}"
        repair_spec["research_design"] = {
            "iter_id": vix_r1.REPAIR_ITER_ID,
            "implementation_repair": True,
        }
        repair_snapshot = {
            "path": vix_r1.SPEC_PATHS[candidate_id].as_posix(),
            "semantic_sha256": f"{position:064x}",
            "spec": repair_spec,
        }
        candidate_specs[candidate_id] = repair_snapshot
        manifest_rows.append(
            {
                "candidate_id": candidate_id,
                "source_trial_id": f"{vix_r1.BASE_ITER_ID}:{candidate_id}",
                "effective_trial_increment": 0,
                "implementation_repair_only": True,
            }
        )
        source_projection = vix_r1._economic_spec_projection(source_snapshot["spec"])
        equivalence_rows.append(
            {
                "candidate_id": candidate_id,
                "source_spec_path": source_snapshot["path"],
                "source_spec_semantic_sha256": source_snapshot["semantic_sha256"],
                "repair_spec_path": repair_snapshot["path"],
                "repair_spec_semantic_sha256": repair_snapshot["semantic_sha256"],
                "economic_projection_sha256": vix_r1._canonical_hash(source_projection),
                "economic_projection_equal": True,
                "allowed_spec_differences": ["name", "research_design"],
            }
        )

    parent_audit = {
        "source_iteration_id": vix_r1.BASE_ITER_ID,
        "source_lock": parent_binding,
        "parameter_changes_from_outcomes": False,
        "paper_or_broker_activity": False,
        "failure": {
            "selectable_candidate_returns_computed": False,
            "selectable_candidate_metrics_computed": False,
            "selection_performed": False,
        },
        "exposure": {
            "historical_targets_computed": True,
            "historical_predictions_computed": "true_or_unknown",
            "historical_predictions_inspected": "false_or_unknown",
            "unpersisted_refit_attempts_lower_bound": 0,
            "unpersisted_refit_attempts_upper_bound": 312,
            "prediction_rows_upper_bound": 6528,
            "persisted_model_ids": 0,
            "persisted_prediction_rows": 0,
        },
    }
    repair = {
        "contract_id": "vix_r1_pure_implementation_repair_v1",
        "repair_scope": "candidate_target_inventory_order_and_one_shot_evaluation_custody",
        "parent_failure_audit": audit_binding,
        "source_lock": parent_binding,
        "source_iteration_id": vix_r1.BASE_ITER_ID,
        "new_economic_candidate_count": 0,
        "manifest_candidate_count": len(vix_r1.CANDIDATE_IDS),
        "effective_trial_count": 8147,
        "forbidden_changes": [
            "universe",
            "data",
            "features",
            "labels",
            "models",
            "seeds",
            "fallbacks",
            "folds",
            "costs",
            "benchmarks",
            "economic_parameters",
        ],
        "economic_spec_equivalence": equivalence_rows,
        "validation_policy_delta": {
            "reason": "post_2026_08_15_new_iteration_governance",
            "metric": ("primary_20bps_continuous_terminal_free_OOS_annualized_sharpe_excess_BIL"),
            "operator": "strictly_greater_than",
            "threshold": 1.0,
            "applies_to": list(vix_r1.SELECTABLE_IDS),
        },
    }
    return vix_r1.VixRuntimeContract(
        manifest={
            "source_iteration_id": vix_r1.BASE_ITER_ID,
            "implementation_repair_only": True,
            "incremental_economic_trial_count": 0,
            "candidates": manifest_rows,
            "contracts": {
                "governance": {
                    "vix_r1_parent_failure_audit_v1": audit_binding,
                    "vix_r1_pure_implementation_repair_v1": repair_binding,
                }
            },
        },
        contracts={
            "implementation-repair-contract.json": repair,
            "parent-failure-audit.json": parent_audit,
        },
        candidate_specs=candidate_specs,
        file_bindings={
            "parent-failure-audit.json": audit_binding,
            "implementation-repair-contract.json": repair_binding,
        },
    )


def test_repair_identity_rejects_parent_lock_sha_drift(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _repair_identity_contract(repo_root)
    vix_r1._validate_repair_identity(contract, root=repo_root)

    monkeypatch.setattr(vix_r1, "SOURCE_ITERATION_LOCK_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="parent lock SHA drifted"):
        vix_r1._validate_repair_identity(contract, root=repo_root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("manifest_trial_count", "manifest accounting"),
        ("manifest_governance_binding", "governance bindings"),
        ("candidate_trial_increment", "trial identity"),
        ("repair_candidate_count", "parent or trial identity"),
        ("exposure_disclosure", "exposure disclosure"),
        ("economic_projection", "economic StrategySpec"),
        ("economic_evidence", "economic evidence"),
    ],
)
def test_repair_identity_rejects_trial_exposure_and_economic_tampering(
    repo_root: Path,
    mutation: str,
    message: str,
) -> None:
    contract = _repair_identity_contract(repo_root)
    vix_r1._validate_repair_identity(contract, root=repo_root)

    if mutation == "manifest_trial_count":
        contract.manifest["incremental_economic_trial_count"] = 1
    elif mutation == "manifest_governance_binding":
        contract.manifest["contracts"]["governance"]["vix_r1_parent_failure_audit_v1"] = {
            **contract.file_bindings["parent-failure-audit.json"],
            "sha256": "0" * 64,
        }
    elif mutation == "candidate_trial_increment":
        contract.manifest["candidates"][0]["effective_trial_increment"] = 1
    elif mutation == "repair_candidate_count":
        contract.contracts["implementation-repair-contract.json"][
            "new_economic_candidate_count"
        ] = 1
    elif mutation == "exposure_disclosure":
        contract.contracts["parent-failure-audit.json"]["exposure"][
            "unpersisted_refit_attempts_upper_bound"
        ] = 311
    elif mutation == "economic_projection":
        contract.candidate_specs["V1D02"]["spec"]["universe"] = ["SPY"]
    elif mutation == "economic_evidence":
        contract.contracts["implementation-repair-contract.json"]["economic_spec_equivalence"][3][
            "economic_projection_sha256"
        ] = "0" * 64
    else:  # pragma: no cover - pytest owns the parameter inventory.
        raise AssertionError(f"unknown repair mutation: {mutation}")

    with pytest.raises(ValueError, match=message):
        vix_r1._validate_repair_identity(contract, root=repo_root)


def test_publication_binding_uses_final_path_and_child_hash(tmp_path: Path) -> None:
    staging = tmp_path / "reports/evaluation-run.staging-1"
    destination = tmp_path / "reports/evaluation-run"
    staging.mkdir(parents=True)
    child = staging / "evaluation-report.json"
    child.write_bytes(b"{}\n")

    binding = vix_r1._publication_binding(
        child,
        root=tmp_path,
        staging_dir=staging,
        destination_dir=destination,
    )

    assert binding["path"] == "reports/evaluation-run/evaluation-report.json"
    assert binding["size_bytes"] == 3
    assert len(binding["sha256"]) == 64
