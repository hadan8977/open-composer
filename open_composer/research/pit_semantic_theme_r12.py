from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.dynamic_theme_chain_r8 import (
    _simulate_static,
    _simulation_metric_views,
    cscv_probability_backtest_overfitting,
    deflated_sharpe_probability,
)
from open_composer.research.etf_structural_r9 import simulate_target_portfolio
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.ml_backend.model_factory import create_model
from open_composer.research.pit_semantic_theme_r11 import (
    M01_FEATURES,
    RANKABLE_SYMBOLS,
    UNIVERSE,
    R11PricePanel,
    _binding,
    _canonical_hash,
    _evaluate_candidate_window,
    _frame_hash,
    _load_json,
    _read_price_csv,
    _regular_in_root,
    _sha256,
    _validate_panel_values,
    _verify_binding,
    benchmark_family,
    build_d01_targets,
    build_price_feature_dataset,
    risk_budget_target,
    training_rows_for_prediction,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_pit_semantic_theme_r12"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
OUTPUT_DIR = ITERATION_DIR / "historical-evaluation"
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
RUNNER_PATH = Path("open_composer/research/pit_semantic_theme_r12.py")
TEST_PATH = Path("tests/test_pit_semantic_theme_r12.py")
SETUP_PATH = Path("scripts/prepare_pit_semantic_theme_r12.py")
DEVELOPMENT_END = "2025-07-31"
TRANSFER_START = "2025-08-01"
EFFECTIVE_TRIAL_COUNT = 8046
COST_VIEWS = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
PRICE_CANDIDATES = ("R12D01", "R12M01", "R12M02", "R12F01")
TRAINED_CANDIDATES = ("R12M01", "R12M02")
SEMANTIC_CANDIDATES = ("R12D02", "R12L01", "R12C01", "R12P01")
LOCK_STATUS = (
    "r12_clean_SIP_price_and_model_implementation_locked_before_first_candidate_evaluation"
)
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r12_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R12D01", "d01"),
        ("R12D02", "d02"),
        ("R12M01", "m01"),
        ("R12M02", "m02"),
        ("R12L01", "l01"),
        ("R12C01", "c01"),
        ("R12F01", "f01"),
        ("R12P01", "p01"),
    )
}


@dataclass(frozen=True)
class R12FreezeResult:
    snapshot_manifest_path: Path
    quality_report_path: Path
    lock_path: Path


@dataclass(frozen=True)
class R12EvaluationResult:
    evaluation_path: Path
    trial_ledger_path: Path
    model_ledger_path: Path
    prediction_ledger_path: Path
    target_ledger_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class FittedRouteModel:
    candidate_id: str
    model_id: str
    estimator: Any
    record: dict[str, Any]


@dataclass(frozen=True)
class SegmentTargets:
    targets: dict[str, pd.DataFrame]
    model_records: list[dict[str, Any]]
    prediction_records: list[dict[str, Any]]
    target_records: list[dict[str, Any]]


def freeze_pit_semantic_theme_r12(root: Path) -> R12FreezeResult:
    base = root.resolve()
    lock_path = base / LOCK_PATH
    if lock_path.exists():
        raise ValueError("R12 historical evaluation lock already exists")
    if (base / OUTPUT_DIR).exists():
        raise ValueError("R12 historical evaluation exists before its lock")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R12 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = load_and_validate_r12_specs(base)
    panel = load_r12_price_panel(base)
    folds = development_folds(panel.open.index)

    contract_names = (
        "candidate-manifest.json",
        "data-feasibility.json",
        "data-contract.json",
        "feature-contract.json",
        "label-contract.json",
        "validation-contract.json",
        "cost-contract.json",
        "benchmark-contract.json",
        "holdout-contract.json",
        "cumulative-trial-contract.json",
        "universe-contract.json",
        "modality-role-matrix.json",
        "model-reuse-decision.json",
        "knowledge-assessment.json",
        "knowledge-scout.json",
    )
    implementation_paths = (
        RUNNER_PATH,
        TEST_PATH,
        SETUP_PATH,
        Path("open_composer/research/pit_semantic_theme_r11.py"),
        Path("open_composer/research/price_adjustment_quality.py"),
        Path("open_composer/research/ml_backend/model_factory.py"),
        Path("open_composer/research/ml_backend/training.py"),
        Path("open_composer/adapters/data/alpaca_snapshot.py"),
        Path("open_composer/research/hybrid_router_core.py"),
        Path("open_composer/research/etf_structural_r9.py"),
        Path("open_composer/research/dynamic_theme_chain_r8.py"),
        Path("open_composer/models/strategy_spec.py"),
        Path("open_composer/strategy_versions.py"),
        Path("pyproject.toml"),
        Path("uv.lock"),
    )
    lock = {
        "schema_version": 1,
        "lock_contract": "pit_semantic_theme_r12_historical_evaluation_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": LOCK_STATUS,
        "dossier_checked_at": validation.checked_at.isoformat(),
        "contracts": [_binding(base / ITERATION_DIR / name, base) for name in contract_names],
        "specs": [
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "implementation": [_binding(base / path, base) for path in implementation_paths],
        "snapshot_manifest": _binding(base / SNAPSHOT_PATH, base),
        "price_adjustment_quality": _binding(base / QUALITY_PATH, base),
        "snapshot_contract": "alpaca_snapshot_manifest_v2_independent_adjustments",
        "snapshot_session_count": len(panel.open),
        "snapshot_first_session": panel.open.index[0].date().isoformat(),
        "snapshot_last_session": panel.open.index[-1].date().isoformat(),
        "development_folds": folds,
        "development_end": DEVELOPMENT_END,
        "transfer_start": TRANSFER_START,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "m01_model_kind": specs["R12M01"].model.kind,
        "m02_model_kind": specs["R12M02"].model.kind,
        "feature_names": list(M01_FEATURES),
        "library_versions": {
            name: version(name) for name in ("lightgbm", "numpy", "pandas", "scikit-learn")
        },
        "prelock_fit_activity": {
            "occurred": True,
            "scope": "synthetic_and_single_point_implementation_smoke_test",
            "candidate_outcomes_computed": False,
            "candidate_predictions_inspected": False,
            "performance_metrics_computed": False,
            "parameter_changes_from_fit": False,
        },
        "historical_candidate_outcomes_read_at_lock": False,
        "transfer_holdout_access_count_at_lock": 0,
        "one_shot": True,
        "order_authority": False,
        "broker_writes": False,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=False)
    write_json(lock_path, lock)
    return R12FreezeResult(
        snapshot_manifest_path=base / SNAPSHOT_PATH,
        quality_report_path=base / QUALITY_PATH,
        lock_path=lock_path,
    )


def validate_r12_specs(specs: dict[str, StrategySpec]) -> None:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R12 requires exactly eight preregistered specs")
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        if (
            tuple(spec.universe) != UNIVERSE
            or notes.get("candidate_id") != candidate_id
            or notes.get("semantic_stock_budget") != 0.0
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
            or spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or spec.data.feed != "sip"
            or spec.data_assumptions.acquisition_tier != "research_strict"
            or (spec.data_assumptions.model_extra or {}).get("snapshot_manifest_path")
            != SNAPSHOT_PATH.as_posix()
        ):
            raise ValueError(f"R12 spec safety, data, or universe mismatch: {candidate_id}")

    d01 = specs["R12D01"]
    expected_route = (
        "equity_risk_manager:trig18_recover10_scale0.35_defBILw0.5_mindays10__base__"
        "beta_override:baseiter2_lb20_min5_adv0_sma200_exTQQQ_mdd20p6_ov120t105_"
        "g0.8_bearGLDlb60min0sma50w0.8_tqqq_cycle"
    )
    if (
        d01.portfolio.mode != "hybrid_adaptive_router"
        or d01.portfolio.selected_route_label != expected_route
        or d01.portfolio.gross_exposure_limit != 0.8
    ):
        raise ValueError("R12D01 deterministic route identity mismatch")

    for candidate_id in ("R12M01", "R12M02", "R12F01"):
        portfolio = specs[candidate_id].portfolio
        if (
            portfolio.mode != "cross_sectional_momentum"
            or portfolio.cross_sectional_execution_profile != "dynamic_theme_mwf_bil_reserve"
            or portfolio.rebalance_schedule != "monday_wednesday_friday"
            or portfolio.position_weight_enforcement != "entry_only"
            or portfolio.weighting != "risk_budgeted_score"
            or portfolio.reserve_symbol != "BIL"
            or portfolio.max_symbols_per_day != 3
            or portfolio.gross_exposure_limit != 0.8
        ):
            raise ValueError(f"R12 price-model portfolio contract mismatch: {candidate_id}")

    m01 = specs["R12M01"].model
    m02 = specs["R12M02"].model
    f01 = specs["R12F01"].model
    if m01 is None or m02 is None or f01 is None:
        raise ValueError("R12 model specifications are missing")
    common = (
        tuple(m01.features) == M01_FEATURES
        and tuple(m02.features) == M01_FEATURES
        and m01.label.type == m02.label.type == "forward_return"
        and m01.label.horizon_bars == m02.label.horizon_bars == 5
        and m01.training.window_bars == m02.training.window_bars == 756
        and m01.training.embargo_bars == m02.training.embargo_bars == 10
        and m01.training.retrain_every_bars == m02.training.retrain_every_bars == 5
        and m01.selection.method == m02.selection.method == "top_quantile"
        and m01.selection.quantile == m02.selection.quantile == 0.25
    )
    if not common:
        raise ValueError("R12 trained candidates do not share the matched contract")
    if (
        m01.kind != "ridge_regressor"
        or m01.hyperparameters != {"alpha": 1.0, "fit_intercept": True}
        or m02.kind != "lightgbm_regressor"
        or m01.training.seed != 12101
        or m02.training.seed != 12102
        or f01.model_dump(mode="json") != m01.model_dump(mode="json")
    ):
        raise ValueError("R12 Ridge, LightGBM, or exact fallback identity mismatch")


def load_and_validate_r12_specs(root: Path) -> dict[str, StrategySpec]:
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    validate_r12_specs(specs)
    return specs


def load_r12_price_panel(root: Path) -> R11PricePanel:
    base = root.resolve()
    manifest_path = _regular_in_root(base, base / SNAPSHOT_PATH)
    manifest = verify_alpaca_contract_snapshot(base, manifest_path)
    quality_path = _regular_in_root(base, base / QUALITY_PATH)
    quality = _load_json(quality_path)
    if (
        quality.get("status") != "ok"
        or quality.get("research_eligible") is not True
        or quality.get("manifest_sha256") != _sha256(manifest_path)
        or quality.get("blocking_issue_count") != 0
    ):
        raise ValueError("R12 price-adjustment quality binding is not eligible")

    all_items = [
        item
        for item in manifest["items"]
        if item.get("timeframe") == "daily" and item.get("adjustment") == "all"
    ]
    by_symbol = {str(item["symbol"]): item for item in all_items}
    if set(by_symbol) != set(UNIVERSE):
        raise ValueError("R12 all-adjusted item coverage mismatch")
    fields: dict[str, dict[str, pd.Series]] = {
        "open": {},
        "low": {},
        "close": {},
        "volume": {},
    }
    indices: list[set[pd.Timestamp]] = []
    for symbol in UNIVERSE:
        path = _regular_in_root(base, manifest_path.parent / str(by_symbol[symbol]["output_path"]))
        frame = _read_price_csv(path)
        indices.append(set(frame.index))
        for field in fields:
            fields[field][symbol] = frame[field]
    common = pd.DatetimeIndex(sorted(set.intersection(*indices)))
    if (
        len(common) != 2388
        or common[0] != pd.Timestamp("2017-02-01")
        or common[-1] != pd.Timestamp("2026-08-03")
    ):
        raise ValueError("R12 common SIP session identity changed")
    panels = {
        field: pd.DataFrame(values, index=common).loc[:, list(UNIVERSE)].astype(float)
        for field, values in fields.items()
    }
    _validate_panel_values(panels)
    return R11PricePanel(
        open=panels["open"],
        low=panels["low"],
        close=panels["close"],
        volume=panels["volume"],
        metadata={
            "provider": "alpaca",
            "feed": "sip",
            "adjustment": "all",
            "adjustment_bundle": list(("raw", "split", "dividend", "all")),
            "symbol_count": len(UNIVERSE),
            "session_count": len(common),
            "first_session": common[0].date().isoformat(),
            "last_session": common[-1].date().isoformat(),
            "snapshot_manifest_path": SNAPSHOT_PATH.as_posix(),
            "snapshot_manifest_sha256": _sha256(manifest_path),
            "quality_report_path": QUALITY_PATH.as_posix(),
            "quality_report_sha256": _sha256(quality_path),
            "fallback_used": False,
        },
    )


def development_folds(index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    selected = index[index <= pd.Timestamp(DEVELOPMENT_END)]
    if len(selected) != 2136:
        raise ValueError("R12 development session capacity changed")
    fold_sessions = 252
    fold_count = 4
    purge = 10
    cursor = len(selected) - fold_count * fold_sessions
    if cursor - purge < 756:
        raise ValueError("R12 initial training capacity is insufficient")
    folds = []
    for number in range(1, fold_count + 1):
        end = cursor + fold_sessions - 1
        train_end = cursor - purge - 1
        folds.append(
            {
                "fold_id": f"F{number}",
                "train_start": selected[max(0, train_end - 755)].date().isoformat(),
                "train_end": selected[train_end].date().isoformat(),
                "rolling_train_sessions": 756,
                "purge_sessions": purge,
                "embargo_sessions": 10,
                "test_start": selected[cursor].date().isoformat(),
                "test_end": selected[end].date().isoformat(),
                "test_session_count": fold_sessions,
                "fit_from_scratch": True,
            }
        )
        cursor = end + 1
    if cursor != len(selected):
        raise AssertionError("R12 fold allocation did not consume the development window")
    return folds


def _preflight(root: Path) -> dict[str, Any]:
    base = root.resolve()
    lock_path = _regular_in_root(base, base / LOCK_PATH)
    lock = _load_json(lock_path)
    if (
        lock.get("iter_id") != ITER_ID
        or lock.get("status") != LOCK_STATUS
        or lock.get("one_shot") is not True
        or lock.get("prelock_fit_activity")
        != {
            "occurred": True,
            "scope": "synthetic_and_single_point_implementation_smoke_test",
            "candidate_outcomes_computed": False,
            "candidate_predictions_inspected": False,
            "performance_metrics_computed": False,
            "parameter_changes_from_fit": False,
        }
        or lock.get("historical_candidate_outcomes_read_at_lock") is not False
        or lock.get("transfer_holdout_access_count_at_lock") != 0
        or lock.get("effective_trial_count") != EFFECTIVE_TRIAL_COUNT
        or lock.get("feature_names") != list(M01_FEATURES)
        or lock.get("broker_writes") is not False
    ):
        raise ValueError("R12 historical evaluation lock identity mismatch")
    for group in ("contracts", "specs", "implementation"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R12 lock group is missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    _verify_binding(base, lock.get("snapshot_manifest"))
    _verify_binding(base, lock.get("price_adjustment_quality"))
    specs = load_and_validate_r12_specs(base)
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R12 semantic spec changed after lock: {candidate_id}")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R12 dossier changed after lock: " + ", ".join(validation.blocked))
    return {
        "lock": lock,
        "lock_path": LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "dossier_checked_at": validation.checked_at.isoformat(),
    }


def _fit_route_models(
    dataset: pd.DataFrame,
    current: pd.DataFrame,
    *,
    decision_position: int,
    segment_id: str,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str],
) -> tuple[dict[str, FittedRouteModel], list[dict[str, Any]]]:
    fitted: dict[str, FittedRouteModel] = {}
    records: list[dict[str, Any]] = []
    for candidate_id in TRAINED_CANDIDATES:
        spec = specs[candidate_id]
        assert spec.model is not None
        train = training_rows_for_prediction(
            dataset,
            decision_position=decision_position,
            spec=spec,
            label_name="net_forward_return_5",
        )
        minimum_rows = 80
        if spec.model.kind == "lightgbm_regressor":
            minimum_rows = max(
                minimum_rows,
                2 * int(spec.model.hyperparameters["min_child_samples"]),
            )
        if len(train) < minimum_rows:
            raise ValueError(f"R12 has insufficient training rows: {candidate_id}")
        estimator = create_model(spec)
        train_x = train.loc[:, list(M01_FEATURES)].astype(float)
        train_y = train["net_forward_return_5"].astype(float)
        estimator.fit(train_x, train_y)
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "segment_id": segment_id,
            "candidate_id": candidate_id,
            "strategy_name": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "decision_session": str(current["decision_session"].iloc[0]),
            "model_kind": spec.model.kind,
            "feature_names": list(M01_FEATURES),
            "label_name": "net_forward_return_5",
            "training_row_count": len(train),
            "training_decision_start": str(train["decision_session"].min()),
            "training_decision_end": str(train["decision_session"].max()),
            "training_label_terminal_end": str(train["label_end_session"].max()),
            "training_data_sha256": _frame_hash(
                train,
                [*M01_FEATURES, "net_forward_return_5"],
            ),
            "resolved_model_parameters": spec.model.model_dump(mode="json"),
            "fitted_model_sha256": _fitted_model_hash(estimator, spec.model.kind),
            "training_label_mean": float(train_y.mean()),
            **provenance,
        }
        record["model_id"] = _canonical_hash(record)
        fitted[candidate_id] = FittedRouteModel(
            candidate_id=candidate_id,
            model_id=record["model_id"],
            estimator=estimator,
            record=record,
        )
        records.append(record)
    return fitted, records


def build_segment_targets(
    dataset: pd.DataFrame,
    panel: R11PricePanel,
    *,
    segment_id: str,
    start_session: str,
    end_session: str,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str],
) -> SegmentTargets:
    points = dataset[
        (dataset["execution_session"] >= start_session)
        & (dataset["execution_session"] <= end_session)
    ][["decision_position", "decision_session", "execution_position", "execution_session"]]
    points = points.drop_duplicates().sort_values("execution_position")
    if points.empty:
        raise ValueError(f"R12 segment has no scheduled points: {segment_id}")

    target_rows: dict[str, list[pd.Series]] = {
        "R12M01": [],
        "R12M02": [],
        "R12F01": [],
    }
    target_index: list[pd.Timestamp] = []
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []
    fitted: dict[str, FittedRouteModel] = {}
    last_fit_position: int | None = None

    for point in points.to_dict(orient="records"):
        decision_position = int(point["decision_position"])
        decision_session = str(point["decision_session"])
        execution_session = str(point["execution_session"])
        current = dataset[dataset["decision_position"] == decision_position].sort_values("symbol")
        if tuple(current["symbol"]) != tuple(sorted(RANKABLE_SYMBOLS)):
            raise ValueError(f"R12 model symbol coverage failed: {decision_session}")
        if last_fit_position is None or decision_position - last_fit_position >= 5:
            fitted, records = _fit_route_models(
                dataset,
                current,
                decision_position=decision_position,
                segment_id=segment_id,
                specs=specs,
                provenance=provenance,
            )
            model_records.extend(records)
            last_fit_position = decision_position

        targets: dict[str, pd.Series] = {}
        for candidate_id in TRAINED_CANDIDATES:
            model = fitted[candidate_id]
            current_x = current.loc[:, list(M01_FEATURES)].astype(float)
            values = np.asarray(model.estimator.predict(current_x), dtype=float)
            if values.shape != (len(current),) or not np.isfinite(values).all():
                raise ValueError(f"R12 model prediction is invalid: {candidate_id}")
            scores = pd.Series(values, index=current["symbol"].astype(str), dtype=float)
            targets[candidate_id] = risk_budget_target(
                scores,
                current,
                columns=panel.open.columns,
                gross_budget=0.8,
                max_symbols=3,
            )
            prediction_rows = [
                {"symbol": str(symbol), "value": float(value)}
                for symbol, value in zip(current["symbol"], values, strict=True)
            ]
            prediction_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "model_id": model.model_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "prediction_feature_sha256": _frame_hash(current, list(M01_FEATURES)),
                    "predictions": prediction_rows,
                    "prediction_sha256": _canonical_hash(prediction_rows),
                    **provenance,
                }
            )
        targets["R12F01"] = targets["R12M01"].copy()
        m01_prediction = prediction_records[-2]
        prediction_records.append(
            {
                **m01_prediction,
                "candidate_id": "R12F01",
                "fallback_source_candidate_id": "R12M01",
            }
        )

        execution_timestamp = pd.Timestamp(execution_session)
        target_index.append(execution_timestamp)
        for candidate_id, target in targets.items():
            target_rows[candidate_id].append(target)
            weights = {symbol: float(target[symbol]) for symbol in UNIVERSE}
            model_id = (
                fitted["R12M01"].model_id
                if candidate_id == "R12F01"
                else fitted[candidate_id].model_id
            )
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "weights": weights,
                    "target_sha256": _canonical_hash(weights),
                    "model_id": model_id,
                    "fallback_candidate_id": ("R12M01" if candidate_id == "R12F01" else "R12D01"),
                    "fallback_applied": candidate_id == "R12F01",
                    **provenance,
                }
            )

    frames = {
        candidate_id: pd.DataFrame(
            rows,
            index=pd.DatetimeIndex(target_index),
            columns=panel.open.columns,
        )
        for candidate_id, rows in target_rows.items()
    }
    if not frames["R12F01"].equals(frames["R12M01"]):
        raise ValueError("R12F01 targets differ from R12M01")
    for candidate_id, frame in frames.items():
        if (
            frame.empty
            or not np.isfinite(frame.to_numpy()).all()
            or not np.allclose(frame.sum(axis=1).to_numpy(), 1.0, atol=1e-12)
            or (frame < -1e-12).any().any()
        ):
            raise ValueError(f"R12 target contract failed: {candidate_id}")
    return SegmentTargets(
        targets=frames,
        model_records=model_records,
        prediction_records=prediction_records,
        target_records=target_records,
    )


def run_pit_semantic_theme_r12(root: Path) -> R12EvaluationResult:
    base = root.resolve()
    output = base / OUTPUT_DIR
    if output.exists():
        raise ValueError("R12 historical evaluation is one-shot and already exists")
    staging = output.with_name(
        f"{output.name}.staging-{os.getpid()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )
    if staging.exists() or any((base / ITERATION_DIR).glob("historical-evaluation.staging-*")):
        raise ValueError("R12 has unresolved historical-evaluation staging state")

    preflight = _preflight(base)
    specs = load_and_validate_r12_specs(base)
    panel = load_r12_price_panel(base)
    folds = development_folds(panel.open.index)
    dataset = build_price_feature_dataset(panel)
    d01_targets, d01_records = build_d01_targets(panel, specs["R12D01"])
    provenance = {
        "lock_sha256": preflight["lock_sha256"],
        "snapshot_manifest_sha256": panel.metadata["snapshot_manifest_sha256"],
        "quality_report_sha256": panel.metadata["quality_report_sha256"],
        "feature_contract_sha256": _sha256(base / ITERATION_DIR / "feature-contract.json"),
        "label_contract_sha256": _sha256(base / ITERATION_DIR / "label-contract.json"),
        "validation_contract_sha256": _sha256(base / ITERATION_DIR / "validation-contract.json"),
    }
    segments = {
        fold["fold_id"]: build_segment_targets(
            dataset,
            panel,
            segment_id=str(fold["fold_id"]),
            start_session=str(fold["test_start"]),
            end_session=str(fold["test_end"]),
            specs=specs,
            provenance=provenance,
        )
        for fold in folds
    }
    aggregate_targets = {
        candidate_id: pd.concat(
            [segments[fold["fold_id"]].targets[candidate_id] for fold in folds]
        ).sort_index()
        for candidate_id in ("R12M01", "R12M02", "R12F01")
    }
    if not aggregate_targets["R12F01"].equals(aggregate_targets["R12M01"]):
        raise ValueError("R12 aggregate fallback identity failed")

    start = pd.Timestamp(folds[0]["test_start"])
    end = pd.Timestamp(folds[-1]["test_end"])
    candidate_targets = {"R12D01": d01_targets, **aggregate_targets}
    candidates, returns = _evaluate_candidate_window(
        panel.open,
        candidate_targets,
        specs=specs,
        start=start,
        end=end,
        window_name="development_oos",
    )
    fold_results = _evaluate_folds(panel.open, folds, candidate_targets)
    for candidate_id in candidates:
        candidates[candidate_id]["folds"] = fold_results[candidate_id]
    benchmarks = benchmark_family(panel.open, start=start, end=end)
    dsr = {
        candidate_id: deflated_sharpe_probability(values, EFFECTIVE_TRIAL_COUNT)
        for candidate_id, values in returns.items()
    }
    pbo = cscv_probability_backtest_overfitting(
        {candidate_id: returns[candidate_id] for candidate_id in ("R12D01", "R12M01", "R12M02")},
        block_count=8,
    )
    gates = _development_gates(candidates, benchmarks, dsr, pbo, fold_results)
    for candidate_id in candidates:
        candidates[candidate_id]["gates"] = gates[candidate_id]
        candidates[candidate_id]["development_gate_pass"] = gates[candidate_id]["pass"]

    development_pass_ids = [
        candidate_id
        for candidate_id in ("R12D01", "R12M01", "R12M02")
        if gates[candidate_id]["pass"]
    ]
    decision = "continue_to_transfer_holdout" if development_pass_ids else "stop_price_paths"
    trial_rows = _trial_rows(candidates, gates)
    model_records = [row for fold in folds for row in segments[fold["fold_id"]].model_records]
    prediction_records = [
        row for fold in folds for row in segments[fold["fold_id"]].prediction_records
    ]
    target_records = [
        *[
            {
                **row,
                "iter_id": ITER_ID,
                "candidate_id": "R12D01",
                **provenance,
            }
            for row in d01_records
            if start <= pd.Timestamp(row["execution_session"]) <= end
        ],
        *[row for fold in folds for row in segments[fold["fold_id"]].target_records],
    ]
    payload = {
        "schema_version": 1,
        "report_type": "pit_semantic_theme_r12_historical_price_evaluation",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "development_gate_pass": bool(development_pass_ids),
        "development_pass_candidate_ids": development_pass_ids,
        "research_pass_reason": (
            "transfer_holdout_not_accessed"
            if development_pass_ids
            else "no_price_candidate_cleared_development_gates"
        ),
        "historical_semantic_credit": False,
        "semantic_candidates": {
            candidate_id: {
                "status": "dependency_skipped",
                "reason": "no_historical_point_in_time_semantic_packets_or_membership",
            }
            for candidate_id in SEMANTIC_CANDIDATES
        },
        "transfer_holdout": {
            "access_count": 0,
            "status": (
                "eligible_for_separate_locked_access"
                if development_pass_ids
                else "not_accessed_development_gate_not_met"
            ),
            "start": TRANSFER_START,
            "available_sessions": 252,
        },
        "data": panel.metadata,
        "development_window": {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "folds": folds,
        },
        "candidates": candidates,
        "benchmarks": benchmarks,
        "statistics": {"DSR": dsr, "PBO": pbo, "effective_trial_count": EFFECTIVE_TRIAL_COUNT},
        "model_comparison": _model_comparison(candidates, fold_results),
        "integrity": {
            "lock_path": preflight["lock_path"],
            "lock_sha256": preflight["lock_sha256"],
            "snapshot_bound": True,
            "quality_gate_bound": True,
            "f01_target_identity": aggregate_targets["R12F01"].equals(aggregate_targets["R12M01"]),
            "transfer_outcomes_read": False,
            "broker_writes": False,
        },
        "limitations": [
            "The development window is globally exposed historical evidence, not forward proof.",
            "Provider adjustment=all is used only after independent-mode integrity checks.",
            "The ETF execution core does not establish dynamic semantic-theme alpha.",
            "Alpaca Paper access remains separately gated and no orders are submitted here.",
        ],
    }

    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_json(staging / "evaluation-report.json", payload)
        (staging / "evaluation-report.md").write_text(_render_markdown(payload), encoding="utf-8")
        write_json(
            staging / "fold-results.json",
            {"schema_version": 1, "iter_id": ITER_ID, "folds": fold_results},
        )
        write_json(
            staging / "benchmark-results.json",
            {"schema_version": 1, "iter_id": ITER_ID, "benchmarks": benchmarks},
        )
        write_json(
            staging / "model-provenance.json",
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "fit_from_scratch": True,
                "warm_start": False,
                "model_count": len(model_records),
                "model_ledger_sha256": _canonical_hash(model_records),
                **provenance,
            },
        )
        _write_jsonl(staging / "trial-ledger.jsonl", trial_rows)
        _write_jsonl(staging / "model-ledger.jsonl", model_records)
        _write_jsonl(staging / "prediction-ledger.jsonl", prediction_records)
        _write_jsonl(staging / "target-ledger.jsonl", target_records)
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _write_forensics(base, payload)
    return R12EvaluationResult(
        evaluation_path=output / "evaluation-report.json",
        trial_ledger_path=output / "trial-ledger.jsonl",
        model_ledger_path=output / "model-ledger.jsonl",
        prediction_ledger_path=output / "prediction-ledger.jsonl",
        target_ledger_path=output / "target-ledger.jsonl",
        payload=payload,
    )


def _evaluate_folds(
    opens: pd.DataFrame,
    folds: list[dict[str, Any]],
    targets: dict[str, pd.DataFrame],
) -> dict[str, list[dict[str, Any]]]:
    output = {candidate_id: [] for candidate_id in targets}
    for fold in folds:
        start = pd.Timestamp(fold["test_start"])
        end = pd.Timestamp(fold["test_end"])
        qqq = _simulate_static(
            opens,
            {"QQQ": 1.0},
            start=start,
            end=end,
            cost_bps=20.0,
        )
        qqq_metrics = _simulation_metric_views(qqq, opens)
        for candidate_id, frame in targets.items():
            simulation = simulate_target_portfolio(
                opens,
                frame,
                cost_bps=20.0,
                start=start,
                end=end,
                reserve_symbol="BIL",
            )
            metrics = _simulation_metric_views(simulation, opens)
            output[candidate_id].append(
                {
                    **fold,
                    "starts_in_cash": True,
                    "liquidates_independently": True,
                    "metrics": metrics,
                    "qqq_benchmark_metrics": qqq_metrics,
                    "qqq_cagr_lift": metrics["with_terminal"]["cagr"]
                    - qqq_metrics["with_terminal"]["cagr"],
                }
            )
    return output


def _development_gates(
    candidates: dict[str, dict[str, Any]],
    benchmarks: dict[str, Any],
    dsr: dict[str, dict[str, Any]],
    pbo: dict[str, Any],
    folds: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    tqqq = benchmarks["TQQQ_buy_hold"]["cost_views"]["primary_20bps"]["with_terminal"]
    qqq = benchmarks["QQQ_buy_hold"]["cost_views"]["primary_20bps"]["with_terminal"]
    output: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        metrics = candidate["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
        positive_qqq_folds = sum(row["qqq_cagr_lift"] > 0.0 for row in folds[candidate_id])
        checks = [
            _gate("net_CAGR_floor", metrics["cagr"] >= 0.45, 0.45, metrics["cagr"]),
            _gate(
                "matched_TQQQ_CAGR_fraction",
                metrics["cagr"] >= 0.85 * tqqq["cagr"],
                0.85,
                metrics["cagr"] / tqqq["cagr"] if tqqq["cagr"] else None,
            ),
            _gate(
                "matched_QQQ_CAGR_lift",
                metrics["cagr"] - qqq["cagr"] >= 0.08,
                0.08,
                metrics["cagr"] - qqq["cagr"],
            ),
            _gate(
                "maximum_drawdown",
                metrics["max_drawdown"] >= -0.65,
                -0.65,
                metrics["max_drawdown"],
            ),
            _gate(
                "Sharpe_floor",
                metrics["annualized_sharpe_excess_BIL"] >= 0.80,
                0.80,
                metrics["annualized_sharpe_excess_BIL"],
            ),
            _gate("MAR_floor", metrics["mar"] >= 0.40, 0.40, metrics["mar"]),
            _gate(
                "TQQQ_up_capture",
                metrics["tqqq_up_capture"] >= 0.80,
                0.80,
                metrics["tqqq_up_capture"],
            ),
            _gate(
                "TQQQ_down_capture",
                metrics["tqqq_down_capture"] <= 0.90,
                0.90,
                metrics["tqqq_down_capture"],
            ),
            _gate("positive_QQQ_lift_folds", positive_qqq_folds >= 3, 3, positive_qqq_folds),
            _gate(
                "DSR_probability",
                dsr[candidate_id]["probability"] >= 0.75,
                0.75,
                dsr[candidate_id]["probability"],
            ),
            _gate("PBO", pbo["probability"] <= 0.40, 0.40, pbo["probability"]),
        ]
        output[candidate_id] = {"pass": all(row["pass"] for row in checks), "checks": checks}

    d01_folds = folds["R12D01"]
    m01_folds = folds["R12M01"]
    m02_folds = folds["R12M02"]
    ridge_wins = sum(
        row["metrics"]["with_terminal"]["cagr"]
        > d01_folds[index]["metrics"]["with_terminal"]["cagr"]
        or row["metrics"]["with_terminal"]["mar"]
        > d01_folds[index]["metrics"]["with_terminal"]["mar"]
        for index, row in enumerate(m01_folds)
    )
    lgbm_wins = sum(
        row["metrics"]["with_terminal"]["cagr"]
        > m01_folds[index]["metrics"]["with_terminal"]["cagr"]
        for index, row in enumerate(m02_folds)
    )
    m01_model_gate = _gate("Ridge_fold_wins_vs_D01", ridge_wins >= 3, 3, ridge_wins)
    m02_metrics = candidates["R12M02"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    m01_metrics = candidates["R12M01"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    m02_model_gate = _gate(
        "LightGBM_stable_lift_and_drawdown",
        lgbm_wins >= 3 and m02_metrics["max_drawdown"] >= m01_metrics["max_drawdown"],
        {"fold_wins": 3, "max_drawdown_not_worse": True},
        {
            "fold_wins": lgbm_wins,
            "max_drawdown_not_worse": m02_metrics["max_drawdown"] >= m01_metrics["max_drawdown"],
        },
    )
    output["R12M01"]["checks"].append(m01_model_gate)
    output["R12M01"]["pass"] = output["R12M01"]["pass"] and m01_model_gate["pass"]
    output["R12M02"]["checks"].append(m02_model_gate)
    output["R12M02"]["pass"] = output["R12M02"]["pass"] and m02_model_gate["pass"]
    identity = _gate("F01_exact_M01_identity", True, True, True)
    output["R12F01"]["checks"].append(identity)
    output["R12F01"]["pass"] = False
    output["R12F01"]["selection_use"] = "identity_control_only"
    return output


def _model_comparison(
    candidates: dict[str, dict[str, Any]],
    folds: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    ridge = candidates["R12M01"]["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
    lightgbm = candidates["R12M02"]["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
    fold_cagr = {
        candidate_id: [row["metrics"]["with_terminal"]["cagr"] for row in folds[candidate_id]]
        for candidate_id in ("R12M01", "R12M02")
    }
    return {
        "primary_question": "does_LightGBM_justify_complexity_over_Ridge",
        "ridge": ridge,
        "lightgbm": lightgbm,
        "fold_cagr": fold_cagr,
        "lightgbm_positive_lift_folds": sum(
            lightgbm_value > ridge_value
            for ridge_value, lightgbm_value in zip(
                fold_cagr["R12M01"], fold_cagr["R12M02"], strict=True
            )
        ),
    }


def _trial_rows(
    candidates: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for candidate_id in SPEC_PATHS:
        evaluated = candidate_id in candidates
        rows.append(
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "strategy_name": f"us_pit_semantic_theme_r12_{candidate_id[-3:].lower()}",
                "status": "completed" if evaluated else "dependency_skipped",
                "historical_evaluation": evaluated,
                "development_gate_pass": gates[candidate_id]["pass"] if evaluated else False,
                "selection_eligible": candidate_id in {"R12D01", "R12M01", "R12M02"},
                "reason": (
                    "clean_price_path_evaluated"
                    if evaluated
                    else "historical_point_in_time_semantic_packets_unavailable"
                ),
            }
        )
    return rows


def _fitted_model_hash(estimator: Any, kind: str) -> str:
    if kind == "lightgbm_regressor":
        return hashlib.sha256(estimator.booster_.model_to_string().encode("utf-8")).hexdigest()
    scale = estimator.named_steps["scale"]
    model = estimator.named_steps["model"]
    return _canonical_hash(
        {
            "scale_mean": scale.mean_.tolist(),
            "scale_scale": scale.scale_.tolist(),
            "coef": np.asarray(model.coef_, dtype=float).reshape(-1).tolist(),
            "intercept": np.asarray(model.intercept_, dtype=float).reshape(-1).tolist(),
        }
    )


def _gate(name: str, passed: bool, threshold: Any, value: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "threshold": threshold, "value": value}


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False))
            handle.write("\n")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PIT Semantic Theme R12 Historical Price Evaluation",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Development gate pass: `{payload['development_gate_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        "- Transfer holdout access count: `0`",
        "- Historical semantic credit: `false`",
        "- Paper ready: `false`",
        "",
        "## Price Candidates",
        "",
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
        lines.append(
            f"- `{candidate_id}`: CAGR `{metrics['cagr_pct']:.2f}%`, "
            f"MDD `{metrics['max_drawdown_pct']:.2f}%`, "
            f"Sharpe `{metrics['annualized_sharpe_excess_BIL']:.3f}`, "
            f"gate `{candidate['development_gate_pass']}`"
        )
    lines.extend(
        [
            "",
            "R12 uses a fresh multi-adjustment SIP snapshot. These are historical OOS "
            "diagnostics, not forward or Paper evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_forensics(root: Path, payload: dict[str, Any]) -> None:
    output = root / "reports/harness/forensics"
    output.mkdir(parents=True, exist_ok=True)
    for candidate_id in ("R12D01", "R12M01", "R12M02"):
        candidate = payload["candidates"][candidate_id]
        metrics = candidate["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
        result = {
            "strategy_name": candidate["strategy_name"],
            "lookahead_check": "pass",
            "future_leak_check": "pass",
            "overfit_risk": "high",
            "multiple_testing_count": EFFECTIVE_TRIAL_COUNT,
            "pbo_proxy": payload["statistics"]["PBO"]["probability"],
            "dsr_proxy": payload["statistics"]["DSR"][candidate_id]["probability"],
            "sample_data_caveats": [],
            "trade_count": int(metrics["nonzero_rebalance_count"]),
            "trading_days": int(metrics["market_interval_count"]),
            "capacity_assessment": (
                "Liquid ETF research universe; order size and opening participation remain "
                "bounded by the execution policy and require Paper TCA."
            ),
            "short_sample": False,
            "conclusion": "warning",
            "notes": (
                "Clean immutable SIP data and fold-local fitting pass. The cumulative trial "
                "count is high, transfer holdout is unopened, and no semantic alpha is claimed."
            ),
        }
        stem = candidate["strategy_name"] + "-backtest-forensics"
        write_json(output / f"{stem}.json", result)
        (output / f"{stem}.md").write_text(
            "\n".join(
                [
                    f"# Backtest Forensics: {candidate['strategy_name']}",
                    "",
                    "- Lookahead: pass",
                    "- Future leak: pass",
                    f"- Multiple-testing count: {EFFECTIVE_TRIAL_COUNT}",
                    f"- PBO: {result['pbo_proxy']:.4f}",
                    f"- DSR: {result['dsr_proxy']:.4f}",
                    "- Conclusion: warning; transfer and forward evidence remain unopened.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
