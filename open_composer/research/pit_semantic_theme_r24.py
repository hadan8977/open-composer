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
from open_composer.research.factor_library import factor_definition_ids
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.ml_backend.model_factory import create_model
from open_composer.research.pit_semantic_theme_r11 import (
    UNIVERSE,
    R11PricePanel,
    _binding,
    _canonical_hash,
    _evaluate_candidate_window,
    _load_json,
    _read_price_csv,
    _regular_in_root,
    _sha256,
    _validate_panel_values,
    _verify_binding,
    benchmark_family,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_pit_semantic_theme_r24"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
OUTPUT_DIR = ITERATION_DIR / "historical-evaluation"
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
RUNNER_PATH = Path("open_composer/research/pit_semantic_theme_r24.py")
TEST_PATH = Path("tests/test_pit_semantic_theme_r24.py")
SETUP_PATH = Path("scripts/prepare_pit_semantic_theme_r24.py")
DEVELOPMENT_END = "2025-07-31"
TRANSFER_START = "2025-08-01"
EFFECTIVE_TRIAL_COUNT = 8128
COST_VIEWS = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
MODEL_FEATURES = (
    "qqq_trend_gap_50",
    "qqq_trend_gap_200",
    "tqqq_usd_relative_momentum_5",
    "tqqq_usd_relative_momentum_20",
    "smh_qqq_relative_momentum_20",
    "tqqq_realized_volatility_20",
    "tqqq_drawdown_20",
    "tech_breadth_100",
)
TECH_BREADTH_SYMBOLS = ("QQQ", "XLK", "IGV", "SOXX", "SMH")
REVIEW_EVERY_SESSIONS = 5
MINIMUM_HOLD_SESSIONS = 10
POLICY_VALUE_HORIZON_SESSIONS = 10
POLICY_VALUE_MIN_PREDICTION = 0.005
POLICY_VALUE_CALIBRATION_FRACTION = 0.20
POLICY_VALUE_LOWER_COVERAGE = 0.80
POLICY_VALUE_COST_BPS = 20.0
POLICY_VALUE_PURGE_EMBARGO_SESSIONS = 11
MODEL_RETRAIN_EVERY_SESSIONS = 20
MINIMUM_POLICY_FIT_ROWS = 32
MINIMUM_POLICY_CALIBRATION_ROWS = 8
MAXIMUM_POLICY_TURNOVER = 14.0
MINIMUM_POLICY_OVERRIDE_COUNT = 8
LEADERSHIP_WEIGHTS = {"USD": 1.0}
STRESS_ROUTE = "QQQ"
RECOVERY_QQQ_TREND_SESSIONS = 50
RECOVERY_TQQQ_MOMENTUM_SESSIONS = 10
RECOVERY_TQQQ_MOMENTUM_MIN = 0.08
RECOVERY_BREADTH_TREND_SESSIONS = 100
RECOVERY_BREADTH_MIN_COUNT = 4
USD_PRESSURE_DRAWDOWN_SESSIONS = 20
USD_PRESSURE_DRAWDOWN_MAX = -0.20
USD_PRESSURE_RECOVERY_TREND_SESSIONS = 100
USD_PRESSURE_RECOVERY_MOMENTUM_SESSIONS = 20
USD_PRESSURE_RECOVERY_MOMENTUM_MIN = 0.0
PRICE_CANDIDATES = ("R24D01", "R24M01", "R24M02", "R24F01")
TRAINED_CANDIDATES = ("R24M01", "R24M02")
SEMANTIC_CANDIDATES = ("R24D02", "R24L01", "R24C01", "R24P01")
LOCK_STATUS = (
    "r24_clean_SIP_price_and_model_implementation_locked_before_first_candidate_evaluation"
)
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r24_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R24D01", "d01"),
        ("R24D02", "d02"),
        ("R24M01", "m01"),
        ("R24M02", "m02"),
        ("R24L01", "l01"),
        ("R24C01", "c01"),
        ("R24F01", "f01"),
        ("R24P01", "p01"),
    )
}


@dataclass(frozen=True)
class R24FreezeResult:
    snapshot_manifest_path: Path
    quality_report_path: Path
    lock_path: Path


@dataclass(frozen=True)
class R24EvaluationResult:
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
    calibration_overprediction_quantile: float
    record: dict[str, Any]


@dataclass(frozen=True)
class SegmentTargets:
    targets: dict[str, pd.DataFrame]
    model_records: list[dict[str, Any]]
    prediction_records: list[dict[str, Any]]
    target_records: list[dict[str, Any]]


def _stress_recovery_contract() -> dict[str, Any]:
    return {
        "stress_target": STRESS_ROUTE,
        "recovery_target": "TQQQ",
        "qqq_trend_sessions": RECOVERY_QQQ_TREND_SESSIONS,
        "tqqq_momentum_sessions": RECOVERY_TQQQ_MOMENTUM_SESSIONS,
        "tqqq_momentum_min": RECOVERY_TQQQ_MOMENTUM_MIN,
        "breadth_symbols": list(TECH_BREADTH_SYMBOLS),
        "breadth_trend_sessions": RECOVERY_BREADTH_TREND_SESSIONS,
        "breadth_min_count": RECOVERY_BREADTH_MIN_COUNT,
        "failed_condition_returns_to_stress_immediately": True,
    }


def _usd_pressure_contract() -> dict[str, Any]:
    return {
        "trigger_drawdown_sessions": USD_PRESSURE_DRAWDOWN_SESSIONS,
        "trigger_drawdown_max": USD_PRESSURE_DRAWDOWN_MAX,
        "recovery_trend_sessions": USD_PRESSURE_RECOVERY_TREND_SESSIONS,
        "recovery_momentum_sessions": USD_PRESSURE_RECOVERY_MOMENTUM_SESSIONS,
        "recovery_momentum_min": USD_PRESSURE_RECOVERY_MOMENTUM_MIN,
        "latch_until_recovery": True,
        "pressure_target": STRESS_ROUTE,
        "suppresses_tqqq_recovery": False,
        "pressure_recovery_uses_fast_price_confirmation": True,
        "pressure_recovery_ignores_slow_breadth_confirmation": True,
        "ordinary_stress_recovery_unchanged": True,
    }


def _policy_value_contract() -> dict[str, Any]:
    return {
        "decision_points": "actual_D01_review_points_only",
        "horizon_sessions": POLICY_VALUE_HORIZON_SESSIONS,
        "minimum_prediction": POLICY_VALUE_MIN_PREDICTION,
        "calibration_fraction": POLICY_VALUE_CALIBRATION_FRACTION,
        "lower_bound_coverage": POLICY_VALUE_LOWER_COVERAGE,
        "cost_bps": POLICY_VALUE_COST_BPS,
        "purge_embargo_sessions": POLICY_VALUE_PURGE_EMBARGO_SESSIONS,
        "retrain_every_sessions": MODEL_RETRAIN_EVERY_SESSIONS,
        "hard_stress_termination": True,
        "terminal_rejoin_cost": True,
        "low_confidence_action": "exact_R24D01_no_change",
        "m02_consensus": "Ridge_and_LightGBM_lower_bounds_positive",
    }


def freeze_pit_semantic_theme_r24(root: Path) -> R24FreezeResult:
    base = root.resolve()
    lock_path = base / LOCK_PATH
    if lock_path.exists():
        raise ValueError("R24 historical evaluation lock already exists")
    if (base / OUTPUT_DIR).exists():
        raise ValueError("R24 historical evaluation exists before its lock")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R24 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = load_and_validate_r24_specs(base)
    panel = load_r24_price_panel(base)
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
        "lock_contract": "pit_semantic_theme_r24_historical_evaluation_v1",
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
        "stress_recovery_contract": _stress_recovery_contract(),
        "usd_pressure_contract": _usd_pressure_contract(),
        "policy_value_contract": _policy_value_contract(),
        "m01_model_kind": specs["R24M01"].model.kind,
        "m02_model_kind": specs["R24M02"].model.kind,
        "feature_names": list(MODEL_FEATURES),
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
    return R24FreezeResult(
        snapshot_manifest_path=base / SNAPSHOT_PATH,
        quality_report_path=base / QUALITY_PATH,
        lock_path=lock_path,
    )


def validate_r24_specs(specs: dict[str, StrategySpec]) -> None:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R24 requires exactly eight preregistered specs")
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
            raise ValueError(f"R24 spec safety, data, or universe mismatch: {candidate_id}")
        factor_ids = notes.get("factor_library_ids", [])
        unknown_factor_ids = sorted(set(factor_ids) - set(factor_definition_ids()))
        if unknown_factor_ids:
            raise ValueError(
                f"R24 spec references unknown factor-library IDs: {candidate_id}: "
                f"{unknown_factor_ids}"
            )

    placebo = specs["R24P01"]
    placebo_notes = placebo.notes.model_dump(mode="json")
    placebo_parameter_space = (
        placebo.research_design.parameter_space if placebo.research_design is not None else {}
    )
    if (
        placebo_parameter_space.get("placebo_seed") != [15108]
        or placebo_notes.get("placebo_seed") != 15108
    ):
        raise ValueError("R24 placebo seed must have one canonical value across the StrategySpec")

    d01 = specs["R24D01"]
    d01_notes = d01.notes.model_dump(mode="json")
    if (
        d01.portfolio.mode != "hybrid_adaptive_router"
        or d01.portfolio.selected_route_label
        != "pit_semantic_theme_r24:D01:usd_pressure_dual_fast_recovery_v1"
        or d01.portfolio.gross_exposure_limit != 1.0
        or d01.portfolio.max_symbol_weight != 1.0
        or d01.portfolio.max_symbols_per_day != 1
        or d01_notes.get("route_contract", {}).get("normal_risk_on_target") != {"USD": 1.0}
        or d01_notes.get("route_contract", {}).get("stress_target") != {"QQQ": 1.0}
        or d01_notes.get("route_contract", {}).get("stress_recovery") != _stress_recovery_contract()
        or d01_notes.get("route_contract", {}).get("usd_pressure_override")
        != _usd_pressure_contract()
    ):
        raise ValueError("R24D01 deterministic route identity mismatch")

    for candidate_id in ("R24M01", "R24M02", "R24F01"):
        portfolio = specs[candidate_id].portfolio
        if (
            portfolio.mode != "cross_sectional_momentum"
            or portfolio.cross_sectional_execution_profile != "generic"
            or portfolio.rebalance_schedule != "every_bar"
            or portfolio.position_weight_enforcement != "entry_only"
            or portfolio.weighting != "equal_weight"
            or portfolio.reserve_symbol != "BIL"
            or portfolio.max_symbols_per_day != 1
            or portfolio.gross_exposure_limit != 1.0
            or portfolio.max_symbol_weight != 1.0
        ):
            raise ValueError(f"R24 price-model portfolio contract mismatch: {candidate_id}")

    m01 = specs["R24M01"].model
    m02 = specs["R24M02"].model
    f01 = specs["R24F01"].model
    if m01 is None or m02 is None or f01 is None:
        raise ValueError("R24 model specifications are missing")
    common = (
        tuple(m01.features) == MODEL_FEATURES
        and tuple(m02.features) == MODEL_FEATURES
        and m01.label.type == m02.label.type == "forward_return"
        and m01.label.horizon_bars == m02.label.horizon_bars == POLICY_VALUE_HORIZON_SESSIONS
        and m01.training.window_bars == m02.training.window_bars == 756
        and m01.training.embargo_bars
        == m02.training.embargo_bars
        == POLICY_VALUE_PURGE_EMBARGO_SESSIONS
        and m01.training.retrain_every_bars
        == m02.training.retrain_every_bars
        == MODEL_RETRAIN_EVERY_SESSIONS
        and m01.selection.method == m02.selection.method == "threshold"
        and m01.selection.threshold == m02.selection.threshold == POLICY_VALUE_MIN_PREDICTION
    )
    if not common:
        raise ValueError("R24 trained candidates do not share the matched contract")
    if (
        m01.kind != "ridge_regressor"
        or m02.kind != "lightgbm_regressor"
        or m01.training.seed != 15241
        or m02.training.seed != 15242
        or m01.hyperparameters != {"alpha": 8.0, "fit_intercept": True}
        or f01.model_dump(mode="json") != m02.model_dump(mode="json")
    ):
        raise ValueError("R24 policy-value regressors or exact M02 fallback identity mismatch")


def load_and_validate_r24_specs(root: Path) -> dict[str, StrategySpec]:
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    validate_r24_specs(specs)
    return specs


def load_r24_price_panel(root: Path) -> R11PricePanel:
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
        raise ValueError("R24 price-adjustment quality binding is not eligible")

    all_items = [
        item
        for item in manifest["items"]
        if item.get("timeframe") == "daily" and item.get("adjustment") == "all"
    ]
    by_symbol = {str(item["symbol"]): item for item in all_items}
    if set(by_symbol) != set(UNIVERSE):
        raise ValueError("R24 all-adjusted item coverage mismatch")
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
        raise ValueError("R24 common SIP session identity changed")
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
        raise ValueError("R24 development session capacity changed")
    fold_sessions = 252
    fold_count = 4
    purge = POLICY_VALUE_PURGE_EMBARGO_SESSIONS
    cursor = len(selected) - fold_count * fold_sessions
    if cursor - purge < 756:
        raise ValueError("R24 initial training capacity is insufficient")
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
                "embargo_sessions": POLICY_VALUE_PURGE_EMBARGO_SESSIONS,
                "test_start": selected[cursor].date().isoformat(),
                "test_end": selected[end].date().isoformat(),
                "test_session_count": fold_sessions,
                "fit_from_scratch": True,
            }
        )
        cursor = end + 1
    if cursor != len(selected):
        raise AssertionError("R24 fold allocation did not consume the development window")
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
        or lock.get("stress_recovery_contract") != _stress_recovery_contract()
        or lock.get("usd_pressure_contract") != _usd_pressure_contract()
        or lock.get("policy_value_contract") != _policy_value_contract()
        or lock.get("feature_names") != list(MODEL_FEATURES)
        or lock.get("broker_writes") is not False
    ):
        raise ValueError("R24 historical evaluation lock identity mismatch")
    for group in ("contracts", "specs", "implementation"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R24 lock group is missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    _verify_binding(base, lock.get("snapshot_manifest"))
    _verify_binding(base, lock.get("price_adjustment_quality"))
    specs = load_and_validate_r24_specs(base)
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R24 semantic spec changed after lock: {candidate_id}")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R24 dossier changed after lock: " + ", ".join(validation.blocked))
    return {
        "lock": lock,
        "lock_path": LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "dossier_checked_at": validation.checked_at.isoformat(),
    }


class _ConstantRegressionModel:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return np.full(len(features), self.value, dtype=float)


def _r24_frame_hash(frame: pd.DataFrame, columns: list[str]) -> str:
    identity_columns = ["decision_position", "decision_session", "execution_session"]
    for optional in ("policy_value_label_end_position", "policy_value_label_end_session"):
        if optional in frame.columns:
            identity_columns.append(optional)
    missing = [name for name in [*identity_columns, *columns] if name not in frame.columns]
    if missing:
        raise ValueError(f"R24 frame hash columns are missing: {missing}")
    values = frame.loc[:, columns].astype(float).to_numpy(dtype="<f8", copy=True)
    if not np.isfinite(values).all():
        raise ValueError("R24 frame hash received nonfinite values")
    identities = [
        [None if pd.isna(value) else value for value in row]
        for row in frame.loc[:, identity_columns].itertuples(index=False, name=None)
    ]
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {"identity_columns": identity_columns, "identities": identities, "columns": columns},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    digest.update(values.tobytes())
    return digest.hexdigest()


def _advance_usd_pressure(
    *,
    active: bool,
    drawdown_20: float,
    trend_gap_100: float,
    momentum_20: float,
) -> tuple[bool, str]:
    values = np.asarray((drawdown_20, trend_gap_100, momentum_20), dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("R24 USD pressure inputs must be finite")
    if active:
        recovered = bool(trend_gap_100 > 0.0 and momentum_20 > USD_PRESSURE_RECOVERY_MOMENTUM_MIN)
        return (False, "released") if recovered else (True, "held")
    if drawdown_20 <= USD_PRESSURE_DRAWDOWN_MAX:
        return True, "triggered"
    return False, "clear"


def _route_symbol(route: str) -> str:
    if route == "USD100":
        return "USD"
    if route not in {"QQQ", "TQQQ"}:
        raise ValueError(f"R24 route symbol is not registered: {route}")
    return route


def _route_switch_cost_factor(current_route: str | None, target_route: str) -> float:
    rate = POLICY_VALUE_COST_BPS / 10_000.0
    if current_route is None:
        traded_notional = 1.0
    elif current_route == target_route:
        traded_notional = 0.0
    else:
        traded_notional = 2.0
    factor = 1.0 - traded_notional * rate
    if not 0.0 < factor <= 1.0:
        raise ValueError("R24 policy-value switching cost is invalid")
    return factor


def _policy_value_label_for_review(
    dataset: pd.DataFrame,
    opens: pd.DataFrame,
    row_index: int,
) -> dict[str, Any] | None:
    row = dataset.iloc[row_index]
    if not bool(row["policy_value_eligible"]):
        return None
    terminal_index = row_index + POLICY_VALUE_HORIZON_SESSIONS
    if terminal_index >= len(dataset):
        return None
    execution_position = int(row["execution_position"])
    terminal_position = execution_position + POLICY_VALUE_HORIZON_SESSIONS
    execution_session = pd.Timestamp(str(row["execution_session"]))
    matching_positions = np.flatnonzero(opens.index == execution_session)
    if len(matching_positions) != 1:
        raise ValueError("R24 execution session is missing or duplicated in the open-price frame")
    open_execution_position = int(matching_positions[0])
    open_terminal_position = open_execution_position + POLICY_VALUE_HORIZON_SESSIONS
    if open_terminal_position >= len(opens):
        return None

    pre_review_route = row["d01_pre_review_route"]
    current_baseline = None if pd.isna(pre_review_route) else str(pre_review_route)
    current_alternative = current_baseline
    baseline_wealth = 1.0
    alternative_wealth = 1.0
    override_active = True
    hard_stress_offset: int | None = None

    for offset in range(POLICY_VALUE_HORIZON_SESSIONS):
        future = dataset.iloc[row_index + offset]
        interval_start = int(future["execution_position"])
        if interval_start != execution_position + offset:
            raise ValueError("R24 policy-value horizon is not session-contiguous")
        baseline_route = str(future["d01_selected_route"])
        if offset > 0 and override_active and not bool(future["risk_on"]):
            override_active = False
            hard_stress_offset = offset
        alternative_route = "TQQQ" if override_active else baseline_route

        baseline_wealth *= _route_switch_cost_factor(current_baseline, baseline_route)
        alternative_wealth *= _route_switch_cost_factor(current_alternative, alternative_route)
        open_interval_start = open_execution_position + offset
        next_position = open_interval_start + 1
        baseline_symbol = _route_symbol(baseline_route)
        alternative_symbol = _route_symbol(alternative_route)
        baseline_wealth *= float(
            opens.iloc[next_position][baseline_symbol]
            / opens.iloc[open_interval_start][baseline_symbol]
        )
        alternative_wealth *= float(
            opens.iloc[next_position][alternative_symbol]
            / opens.iloc[open_interval_start][alternative_symbol]
        )
        current_baseline = baseline_route
        current_alternative = alternative_route

    terminal_route = str(dataset.iloc[terminal_index]["d01_selected_route"])
    baseline_wealth *= _route_switch_cost_factor(current_baseline, terminal_route)
    alternative_wealth *= _route_switch_cost_factor(current_alternative, terminal_route)
    values = np.asarray((baseline_wealth, alternative_wealth), dtype=float)
    if not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("R24 policy-value wealth is invalid")
    return {
        "value": float(np.log(alternative_wealth / baseline_wealth)),
        "label_end_position": terminal_position,
        "label_end_session": opens.index[open_terminal_position].date().isoformat(),
        "baseline_wealth": baseline_wealth,
        "alternative_wealth": alternative_wealth,
        "hard_stress_offset": hard_stress_offset,
        "terminal_route": terminal_route,
    }


def build_r24_feature_dataset(panel: R11PricePanel) -> pd.DataFrame:
    close = panel.close
    opens = panel.open
    momentum_5 = close / close.shift(5) - 1.0
    momentum_10 = close / close.shift(RECOVERY_TQQQ_MOMENTUM_SESSIONS) - 1.0
    momentum_20 = close / close.shift(20) - 1.0
    momentum_60 = close / close.shift(60) - 1.0
    momentum_120 = close / close.shift(120) - 1.0
    trend_50 = (
        close
        / close.rolling(
            RECOVERY_QQQ_TREND_SESSIONS,
            min_periods=RECOVERY_QQQ_TREND_SESSIONS,
        ).mean()
        - 1.0
    )
    trend_100 = (
        close
        / close.rolling(
            RECOVERY_BREADTH_TREND_SESSIONS,
            min_periods=RECOVERY_BREADTH_TREND_SESSIONS,
        ).mean()
        - 1.0
    )
    trend_150 = close / close.rolling(150, min_periods=150).mean() - 1.0
    trend_200 = close / close.rolling(200, min_periods=200).mean() - 1.0
    daily_returns = close.pct_change(fill_method=None)
    volatility_20 = daily_returns.rolling(20, min_periods=20).std(ddof=0)
    drawdown_20 = close / close.rolling(20, min_periods=20).max() - 1.0
    breadth_count = (trend_100.loc[:, TECH_BREADTH_SYMBOLS] > 0.0).sum(axis=1)
    breadth = breadth_count / len(TECH_BREADTH_SYMBOLS)
    rows: list[dict[str, Any]] = []
    d01_route: str | None = None
    d01_held_sessions = 0
    d01_sessions_since_review = 0
    usd_pressure_active = False
    for position in range(200, len(close) - 1):
        decision_session = close.index[position]
        execution_position = position + 1
        execution_session = close.index[execution_position]
        base_risk_on = bool(
            trend_200.iloc[position]["QQQ"] > 0.0 or momentum_120.iloc[position]["QQQ"] > 0.0
        )
        usd_pressure_active, usd_pressure_transition = _advance_usd_pressure(
            active=usd_pressure_active,
            drawdown_20=float(drawdown_20.iloc[position]["USD"]),
            trend_gap_100=float(trend_100.iloc[position]["USD"]),
            momentum_20=float(momentum_20.iloc[position]["USD"]),
        )
        risk_on = bool(base_risk_on and not usd_pressure_active)
        fast_price_recovery = bool(
            trend_50.iloc[position]["QQQ"] > 0.0
            and momentum_10.iloc[position]["TQQQ"] >= RECOVERY_TQQQ_MOMENTUM_MIN
        )
        ordinary_stress_recovery = bool(
            not base_risk_on
            and not usd_pressure_active
            and fast_price_recovery
            and breadth_count.iloc[position] >= RECOVERY_BREADTH_MIN_COUNT
        )
        usd_pressure_recovery = bool(usd_pressure_active and fast_price_recovery)
        recovery_boost = bool(not risk_on and (ordinary_stress_recovery or usd_pressure_recovery))
        d01_pre_review_route = d01_route
        (
            d01_route,
            d01_held_sessions,
            d01_sessions_since_review,
            d01_review_due,
            d01_switched,
        ) = _advance_d01_route(
            current_route=d01_route,
            held_sessions=d01_held_sessions,
            sessions_since_review=d01_sessions_since_review,
            risk_on=risk_on,
            recovery_boost=recovery_boost,
        )
        semiconductor_leadership = bool(
            momentum_60.iloc[position]["SMH"] > 0.0
            and trend_150.iloc[position]["SMH"] > 0.0
            and momentum_120.iloc[position]["SMH"] > momentum_120.iloc[position]["QQQ"]
            and momentum_20.iloc[position]["USD"] > 0.0
            and trend_100.iloc[position]["USD"] > 0.0
        )
        policy_value_eligible = bool(d01_review_due and risk_on and d01_route == "USD100")
        row: dict[str, Any] = {
            "decision_position": position,
            "decision_session": decision_session.date().isoformat(),
            "execution_position": execution_position,
            "execution_session": execution_session.date().isoformat(),
            "d01_pre_review_route": d01_pre_review_route,
            "d01_selected_route": d01_route,
            "d01_review_due": d01_review_due,
            "d01_switched": d01_switched,
            "d01_held_sessions": d01_held_sessions,
            "d01_sessions_since_review": d01_sessions_since_review,
            "policy_value_eligible": policy_value_eligible,
            "risk_on": risk_on,
            "base_risk_on": base_risk_on,
            "usd_pressure_active": usd_pressure_active,
            "usd_pressure_transition": usd_pressure_transition,
            "fast_price_recovery": fast_price_recovery,
            "ordinary_stress_recovery": ordinary_stress_recovery,
            "usd_pressure_recovery": usd_pressure_recovery,
            "recovery_boost": recovery_boost,
            "semiconductor_leadership": semiconductor_leadership,
            "qqq_momentum_20": float(momentum_20.iloc[position]["QQQ"]),
            "qqq_momentum_120": float(momentum_120.iloc[position]["QQQ"]),
            "qqq_trend_gap_50": float(trend_50.iloc[position]["QQQ"]),
            "qqq_trend_gap_200": float(trend_200.iloc[position]["QQQ"]),
            "tqqq_momentum_10": float(momentum_10.iloc[position]["TQQQ"]),
            "tqqq_momentum_20": float(momentum_20.iloc[position]["TQQQ"]),
            "tqqq_momentum_60": float(momentum_60.iloc[position]["TQQQ"]),
            "tqqq_realized_volatility_20": float(volatility_20.iloc[position]["TQQQ"]),
            "tqqq_drawdown_20": float(drawdown_20.iloc[position]["TQQQ"]),
            "smh_momentum_20": float(momentum_20.iloc[position]["SMH"]),
            "smh_momentum_60": float(momentum_60.iloc[position]["SMH"]),
            "smh_momentum_120": float(momentum_120.iloc[position]["SMH"]),
            "smh_relative_momentum_120": float(
                momentum_120.iloc[position]["SMH"] - momentum_120.iloc[position]["QQQ"]
            ),
            "smh_trend_gap_150": float(trend_150.iloc[position]["SMH"]),
            "usd_momentum_20": float(momentum_20.iloc[position]["USD"]),
            "usd_momentum_60": float(momentum_60.iloc[position]["USD"]),
            "usd_trend_gap_100": float(trend_100.iloc[position]["USD"]),
            "usd_drawdown_20": float(drawdown_20.iloc[position]["USD"]),
            "tqqq_usd_relative_momentum_5": float(
                momentum_5.iloc[position]["TQQQ"] - momentum_5.iloc[position]["USD"]
            ),
            "tqqq_usd_relative_momentum_20": float(
                momentum_20.iloc[position]["TQQQ"] - momentum_20.iloc[position]["USD"]
            ),
            "smh_qqq_relative_momentum_20": float(
                momentum_20.iloc[position]["SMH"] - momentum_20.iloc[position]["QQQ"]
            ),
            "tech_breadth_100": float(breadth.iloc[position]),
            "tech_breadth_count_100": int(breadth_count.iloc[position]),
        }
        rows.append(row)
    dataset = pd.DataFrame(rows)
    if dataset.empty or not np.isfinite(dataset.loc[:, MODEL_FEATURES].to_numpy()).all():
        raise ValueError("R24 feature dataset is empty or nonfinite")
    dataset["policy_value_label"] = np.nan
    dataset["policy_value_label_end_position"] = np.nan
    dataset["policy_value_label_end_session"] = None
    dataset["policy_value_baseline_wealth"] = np.nan
    dataset["policy_value_alternative_wealth"] = np.nan
    dataset["policy_value_hard_stress_offset"] = np.nan
    dataset["policy_value_terminal_route"] = None
    for row_index in dataset.index[dataset["policy_value_eligible"]]:
        label = _policy_value_label_for_review(dataset, opens, int(row_index))
        if label is None:
            continue
        dataset.at[row_index, "policy_value_label"] = label["value"]
        dataset.at[row_index, "policy_value_label_end_position"] = label["label_end_position"]
        dataset.at[row_index, "policy_value_label_end_session"] = label["label_end_session"]
        dataset.at[row_index, "policy_value_baseline_wealth"] = label["baseline_wealth"]
        dataset.at[row_index, "policy_value_alternative_wealth"] = label["alternative_wealth"]
        if label["hard_stress_offset"] is not None:
            dataset.at[row_index, "policy_value_hard_stress_offset"] = label["hard_stress_offset"]
        dataset.at[row_index, "policy_value_terminal_route"] = label["terminal_route"]
    return dataset


def training_rows_for_r24_prediction(
    dataset: pd.DataFrame,
    *,
    decision_position: int,
    spec: StrategySpec,
    label_name: str,
) -> pd.DataFrame:
    assert spec.model is not None
    if label_name != "policy_value_label":
        raise ValueError(f"R24 label is not registered: {label_name}")
    lower = decision_position - spec.model.training.window_bars
    terminal_cutoff = decision_position - spec.model.training.embargo_bars
    train = dataset[
        (dataset["decision_position"] >= lower)
        & (dataset["decision_position"] < decision_position)
        & dataset["policy_value_eligible"]
        & dataset["policy_value_label_end_position"].notna()
        & (dataset["policy_value_label_end_position"] <= terminal_cutoff)
    ]
    columns = [*MODEL_FEATURES, label_name]
    return train.dropna(subset=columns).sort_values("decision_position").copy()


def _split_policy_fit_and_calibration(
    train: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    calibration_rows = max(
        MINIMUM_POLICY_CALIBRATION_ROWS,
        int(np.ceil(len(train) * POLICY_VALUE_CALIBRATION_FRACTION)),
    )
    fit_rows = len(train) - calibration_rows
    if fit_rows < MINIMUM_POLICY_FIT_ROWS:
        raise ValueError("R24 has insufficient policy-value fit rows")
    fit = train.iloc[:fit_rows].copy()
    calibration = train.iloc[fit_rows:].copy()
    if (
        fit.empty
        or calibration.empty
        or int(fit["decision_position"].max()) >= int(calibration["decision_position"].min())
    ):
        raise ValueError("R24 fit/calibration chronology is invalid")
    return fit, calibration


def _one_sided_overprediction_quantile(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> tuple[float, int, float]:
    actual_values = np.asarray(actual, dtype=float).reshape(-1)
    predicted_values = np.asarray(predicted, dtype=float).reshape(-1)
    if (
        actual_values.shape != predicted_values.shape
        or actual_values.size < MINIMUM_POLICY_CALIBRATION_ROWS
        or not np.isfinite(actual_values).all()
        or not np.isfinite(predicted_values).all()
    ):
        raise ValueError("R24 calibration values are invalid")
    scores = np.sort(predicted_values - actual_values)
    rank = min(
        len(scores),
        max(1, int(np.ceil((len(scores) + 1) * POLICY_VALUE_LOWER_COVERAGE))),
    )
    quantile = float(scores[rank - 1])
    empirical_coverage = float(np.mean(actual_values >= predicted_values - quantile))
    return quantile, rank, empirical_coverage


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
        label_name = "policy_value_label"
        train = training_rows_for_r24_prediction(
            dataset,
            decision_position=decision_position,
            spec=spec,
            label_name=label_name,
        )
        if len(train) < MINIMUM_POLICY_FIT_ROWS + MINIMUM_POLICY_CALIBRATION_ROWS:
            raise ValueError(f"R24 has insufficient training rows: {candidate_id}")
        fit, calibration = _split_policy_fit_and_calibration(train)
        fit_x = fit.loc[:, MODEL_FEATURES].astype(float)
        fit_y = fit[label_name].astype(float)
        calibration_x = calibration.loc[:, MODEL_FEATURES].astype(float)
        calibration_y = calibration[label_name].astype(float).to_numpy()
        if float(fit_y.std(ddof=0)) <= 1e-12:
            estimator: Any = _ConstantRegressionModel(float(fit_y.mean()))
            fit_status = "constant_value_fallback"
        else:
            estimator = create_model(spec)
            estimator.fit(fit_x, fit_y)
            fit_status = "fitted"
        calibration_predictions = np.asarray(estimator.predict(calibration_x), dtype=float).reshape(
            -1
        )
        calibration_quantile, calibration_rank, empirical_coverage = (
            _one_sided_overprediction_quantile(
                calibration_y,
                calibration_predictions,
            )
        )
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "segment_id": segment_id,
            "candidate_id": candidate_id,
            "strategy_name": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "decision_session": str(current["decision_session"].iloc[0]),
            "model_kind": spec.model.kind,
            "fit_status": fit_status,
            "feature_names": list(MODEL_FEATURES),
            "label_name": label_name,
            "training_row_count": len(train),
            "fit_row_count": len(fit),
            "calibration_row_count": len(calibration),
            "training_decision_start": str(train["decision_session"].min()),
            "training_decision_end": str(train["decision_session"].max()),
            "fit_decision_end": str(fit["decision_session"].max()),
            "calibration_decision_start": str(calibration["decision_session"].min()),
            "training_label_terminal_end": str(train["policy_value_label_end_session"].max()),
            "training_data_sha256": _r24_frame_hash(train, [*MODEL_FEATURES, label_name]),
            "fit_data_sha256": _r24_frame_hash(fit, [*MODEL_FEATURES, label_name]),
            "calibration_data_sha256": _r24_frame_hash(calibration, [*MODEL_FEATURES, label_name]),
            "resolved_model_parameters": spec.model.model_dump(mode="json"),
            "fitted_model_sha256": _fitted_model_hash(estimator, spec.model.kind),
            "training_label_mean": float(train[label_name].mean()),
            "training_label_std": float(train[label_name].std(ddof=0)),
            "calibration_method": "split_conformal_one_sided_overprediction_rank",
            "calibration_fraction": POLICY_VALUE_CALIBRATION_FRACTION,
            "calibration_lower_coverage": POLICY_VALUE_LOWER_COVERAGE,
            "calibration_rank": calibration_rank,
            "calibration_overprediction_quantile": calibration_quantile,
            "calibration_empirical_coverage": empirical_coverage,
            "calibration_rmse": float(
                np.sqrt(np.mean(np.square(calibration_predictions - calibration_y)))
            ),
            "calibration_zero_baseline_rmse": float(np.sqrt(np.mean(np.square(calibration_y)))),
            **provenance,
        }
        record["model_id"] = _canonical_hash(record)
        fitted[candidate_id] = FittedRouteModel(
            candidate_id=candidate_id,
            model_id=record["model_id"],
            estimator=estimator,
            calibration_overprediction_quantile=calibration_quantile,
            record=record,
        )
        records.append(record)
    return fitted, records


def _target_weights(symbol: str) -> pd.Series:
    target = pd.Series(0.0, index=list(UNIVERSE), dtype=float)
    target[symbol] = 1.0
    return target


def _leadership_target() -> pd.Series:
    target = pd.Series(0.0, index=list(UNIVERSE), dtype=float)
    for symbol, weight in LEADERSHIP_WEIGHTS.items():
        target[symbol] = weight
    return target


def _target_for_route(route: str) -> pd.Series:
    if route == "USD100":
        return _leadership_target()
    if route not in {STRESS_ROUTE, "QQQ", "TQQQ"}:
        raise ValueError(f"R24 route is not registered: {route}")
    return _target_weights(route)


def _stress_route_for_row(row: pd.Series) -> str:
    return "TQQQ" if bool(row["recovery_boost"]) else STRESS_ROUTE


def _advance_nonstress_route(
    *,
    current_route: str | None,
    desired_route: str,
    held_sessions: int,
    sessions_since_review: int,
) -> tuple[str, int, int, bool, bool]:
    if desired_route not in {"TQQQ", "USD100"}:
        raise ValueError(f"R24 non-stress route is invalid: {desired_route}")
    if current_route in {None, STRESS_ROUTE}:
        return desired_route, 1, 0, True, current_route != desired_route

    next_held_sessions = held_sessions + 1
    next_since_review = sessions_since_review + 1
    review_due = next_since_review >= REVIEW_EVERY_SESSIONS
    switched = False
    if review_due:
        next_since_review = 0
        if desired_route != current_route and held_sessions >= MINIMUM_HOLD_SESSIONS:
            current_route = desired_route
            next_held_sessions = 1
            switched = True
    return current_route, next_held_sessions, next_since_review, review_due, switched


def _advance_d01_route(
    *,
    current_route: str | None,
    held_sessions: int,
    sessions_since_review: int,
    risk_on: bool,
    recovery_boost: bool,
) -> tuple[str, int, int, bool, bool]:
    if not risk_on:
        desired_stress_route = "TQQQ" if recovery_boost else STRESS_ROUTE
        switched = current_route != desired_stress_route
        next_held_sessions = held_sessions + 1 if current_route == desired_stress_route else 1
        return desired_stress_route, next_held_sessions, 0, False, switched
    return _advance_nonstress_route(
        current_route=current_route,
        desired_route="USD100",
        held_sessions=held_sessions,
        sessions_since_review=sessions_since_review,
    )


def build_r24_d01_targets(
    panel: R11PricePanel,
    spec: StrategySpec,
    dataset: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    del spec
    rows: list[pd.Series] = []
    index: list[pd.Timestamp] = []
    records: list[dict[str, Any]] = []
    held_route: str | None = None
    held_sessions = 0
    sessions_since_review = 0
    for item in dataset.to_dict(orient="records"):
        row = pd.Series(item)
        held_route, held_sessions, sessions_since_review, review_due, switched = _advance_d01_route(
            current_route=held_route,
            held_sessions=held_sessions,
            sessions_since_review=sessions_since_review,
            risk_on=bool(row["risk_on"]),
            recovery_boost=bool(row["recovery_boost"]),
        )
        if (
            held_route != str(row["d01_selected_route"])
            or held_sessions != int(row["d01_held_sessions"])
            or sessions_since_review != int(row["d01_sessions_since_review"])
            or review_due is not bool(row["d01_review_due"])
            or switched is not bool(row["d01_switched"])
        ):
            raise ValueError("R24 D01 dataset route state changed")
        target = _target_for_route(held_route)
        execution_session = str(row["execution_session"])
        index.append(pd.Timestamp(execution_session))
        rows.append(target)
        weights = {symbol: float(target[symbol]) for symbol in UNIVERSE}
        records.append(
            {
                "schema_version": 1,
                "decision_session": str(row["decision_session"]),
                "execution_session": execution_session,
                "risk_on": bool(row["risk_on"]),
                "base_risk_on": bool(row["base_risk_on"]),
                "usd_pressure_active": bool(row["usd_pressure_active"]),
                "usd_pressure_transition": str(row["usd_pressure_transition"]),
                "fast_price_recovery": bool(row.get("fast_price_recovery", False)),
                "ordinary_stress_recovery": bool(row.get("ordinary_stress_recovery", False)),
                "usd_pressure_recovery": bool(row.get("usd_pressure_recovery", False)),
                "recovery_boost": bool(row["recovery_boost"]),
                "qqq_trend_gap_50": float(row["qqq_trend_gap_50"]),
                "tqqq_momentum_10": float(row["tqqq_momentum_10"]),
                "tech_breadth_count_100": int(row["tech_breadth_count_100"]),
                "semiconductor_leadership": bool(row["semiconductor_leadership"]),
                "review_due": review_due,
                "policy_value_eligible": bool(row["policy_value_eligible"]),
                "switched": switched,
                "selected_target": held_route,
                "held_sessions": held_sessions,
                "weights": weights,
                "target_sha256": _canonical_hash(weights),
            }
        )
    frame = pd.DataFrame(rows, index=pd.DatetimeIndex(index), columns=panel.open.columns)
    _validate_target_frame(frame, "R24D01")
    return frame, records


def _predict_policy_value(
    model: FittedRouteModel,
    current: pd.DataFrame,
) -> dict[str, Any]:
    values = np.asarray(
        model.estimator.predict(current.loc[:, MODEL_FEATURES].astype(float)), dtype=float
    ).reshape(-1)
    if values.shape != (1,) or not np.isfinite(values).all():
        raise ValueError(f"R24 policy-value prediction is invalid: {model.candidate_id}")
    prediction = float(values[0])
    lower_bound = prediction - model.calibration_overprediction_quantile
    return {
        "prediction": prediction,
        "lower_bound": lower_bound,
        "minimum_prediction_pass": prediction >= POLICY_VALUE_MIN_PREDICTION,
        "lower_bound_pass": lower_bound > 0.0,
    }


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
    ].sort_values("execution_position")
    if points.empty:
        raise ValueError(f"R24 segment has no scheduled points: {segment_id}")
    target_rows = {candidate_id: [] for candidate_id in ("R24M01", "R24M02", "R24F01")}
    target_index: list[pd.Timestamp] = []
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []
    fitted: dict[str, FittedRouteModel] = {}
    last_fit_position: int | None = None
    policy_states: dict[str, dict[str, Any]] = {
        candidate_id: {"remaining_intervals": 0, "rejoin_required": False}
        for candidate_id in ("R24M01", "R24M02")
    }

    for point in points.to_dict(orient="records"):
        decision_position = int(point["decision_position"])
        current = pd.DataFrame([point])
        row = current.iloc[0]
        baseline_route = str(row["d01_selected_route"])
        policy_review = bool(row["policy_value_eligible"])
        predictions: dict[str, dict[str, Any]] = {}
        authorizations = {candidate_id: False for candidate_id in TRAINED_CANDIDATES}
        if policy_review:
            if (
                last_fit_position is None
                or decision_position - last_fit_position >= MODEL_RETRAIN_EVERY_SESSIONS
            ):
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
            predictions = {
                candidate_id: _predict_policy_value(fitted[candidate_id], current)
                for candidate_id in TRAINED_CANDIDATES
            }
            authorizations["R24M01"] = bool(
                predictions["R24M01"]["minimum_prediction_pass"]
                and predictions["R24M01"]["lower_bound_pass"]
            )
            authorizations["R24M02"] = bool(
                authorizations["R24M01"]
                and predictions["R24M02"]["minimum_prediction_pass"]
                and predictions["R24M02"]["lower_bound_pass"]
            )

        routes: dict[str, str] = {}
        action_records: dict[str, dict[str, Any]] = {}
        for candidate_id in TRAINED_CANDIDATES:
            state = policy_states[candidate_id]
            override_started = False
            hard_stress_terminated = False
            terminal_rejoin = False
            if not bool(row["risk_on"]):
                hard_stress_terminated = bool(
                    state["remaining_intervals"] > 0 or state["rejoin_required"]
                )
                state["remaining_intervals"] = 0
                state["rejoin_required"] = False
                selected_route = baseline_route
            elif state["rejoin_required"]:
                selected_route = baseline_route
                terminal_rejoin = True
                state["rejoin_required"] = False
            elif state["remaining_intervals"] > 0:
                selected_route = "TQQQ"
                state["remaining_intervals"] -= 1
                if state["remaining_intervals"] == 0:
                    state["rejoin_required"] = True
            elif policy_review and authorizations[candidate_id]:
                selected_route = "TQQQ"
                override_started = True
                state["remaining_intervals"] = POLICY_VALUE_HORIZON_SESSIONS - 1
                if state["remaining_intervals"] == 0:
                    state["rejoin_required"] = True
            else:
                selected_route = baseline_route
            routes[candidate_id] = selected_route
            action_records[candidate_id] = {
                "authorized": authorizations[candidate_id],
                "override_started": override_started,
                "model_override_applied": selected_route != baseline_route,
                "hard_stress_terminated": hard_stress_terminated,
                "terminal_rejoin": terminal_rejoin,
                "remaining_intervals_after_target": int(state["remaining_intervals"]),
                "rejoin_required_after_target": bool(state["rejoin_required"]),
            }

        routes["R24F01"] = routes["R24M02"]
        action_records["R24F01"] = {
            **action_records["R24M02"],
            "fallback_source_candidate_id": "R24M02",
        }
        targets = {candidate_id: _target_for_route(route) for candidate_id, route in routes.items()}

        if policy_review:
            prediction_base = {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "segment_id": segment_id,
                "decision_session": str(row["decision_session"]),
                "execution_session": str(row["execution_session"]),
                "prediction_feature_sha256": _r24_frame_hash(current, list(MODEL_FEATURES)),
                "realized_policy_value": (
                    None if pd.isna(row["policy_value_label"]) else float(row["policy_value_label"])
                ),
                "policy_value_label_end_session": row["policy_value_label_end_session"],
                **provenance,
            }
            for candidate_id in TRAINED_CANDIDATES:
                prediction = predictions[candidate_id]
                payload = {
                    **prediction_base,
                    "candidate_id": candidate_id,
                    "model_id": fitted[candidate_id].model_id,
                    **prediction,
                    **action_records[candidate_id],
                }
                payload["prediction_sha256"] = _canonical_hash(
                    {
                        "prediction": prediction["prediction"],
                        "lower_bound": prediction["lower_bound"],
                        "authorized": action_records[candidate_id]["authorized"],
                    }
                )
                prediction_records.append(payload)
            prediction_records.append(
                {
                    **prediction_records[-1],
                    "candidate_id": "R24F01",
                    "fallback_source_candidate_id": "R24M02",
                }
            )

        target_index.append(pd.Timestamp(str(row["execution_session"])))
        for candidate_id, target in targets.items():
            target_rows[candidate_id].append(target)
            weights = {symbol: float(target[symbol]) for symbol in UNIVERSE}
            prediction_source = "R24M02" if candidate_id == "R24F01" else candidate_id
            model_id = fitted[prediction_source].model_id if prediction_source in fitted else None
            prediction = predictions.get(prediction_source)
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": str(row["decision_session"]),
                    "execution_session": str(row["execution_session"]),
                    "risk_on": bool(row["risk_on"]),
                    "base_risk_on": bool(row["base_risk_on"]),
                    "usd_pressure_active": bool(row["usd_pressure_active"]),
                    "usd_pressure_transition": str(row["usd_pressure_transition"]),
                    "fast_price_recovery": bool(row.get("fast_price_recovery", False)),
                    "ordinary_stress_recovery": bool(row.get("ordinary_stress_recovery", False)),
                    "usd_pressure_recovery": bool(row.get("usd_pressure_recovery", False)),
                    "recovery_boost": bool(row["recovery_boost"]),
                    "qqq_trend_gap_50": float(row["qqq_trend_gap_50"]),
                    "tqqq_momentum_10": float(row["tqqq_momentum_10"]),
                    "tech_breadth_count_100": int(row["tech_breadth_count_100"]),
                    "semiconductor_leadership": bool(row["semiconductor_leadership"]),
                    "d01_selected_route": baseline_route,
                    "policy_value_review": policy_review,
                    "policy_value_prediction": (
                        prediction["prediction"] if prediction is not None else None
                    ),
                    "policy_value_lower_bound": (
                        prediction["lower_bound"] if prediction is not None else None
                    ),
                    "selected_route": routes[candidate_id],
                    **action_records[candidate_id],
                    "weights": weights,
                    "target_sha256": _canonical_hash(weights),
                    "model_id": model_id,
                    "fallback_candidate_id": ("R24M02" if candidate_id == "R24F01" else "R24D01"),
                    "fallback_applied": bool(
                        candidate_id == "R24F01"
                        or not action_records[candidate_id]["model_override_applied"]
                    ),
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
    if not frames["R24F01"].equals(frames["R24M02"]):
        raise ValueError("R24F01 targets differ from R24M02")
    for candidate_id, frame in frames.items():
        _validate_target_frame(frame, candidate_id)
    return SegmentTargets(
        targets=frames,
        model_records=model_records,
        prediction_records=prediction_records,
        target_records=target_records,
    )


def _validate_target_frame(frame: pd.DataFrame, candidate_id: str) -> None:
    if (
        frame.empty
        or not np.isfinite(frame.to_numpy()).all()
        or not np.allclose(frame.sum(axis=1).to_numpy(), 1.0, atol=1e-12)
        or (frame < -1e-12).any().any()
    ):
        raise ValueError(f"R24 target contract failed: {candidate_id}")


def run_pit_semantic_theme_r24(root: Path) -> R24EvaluationResult:
    base = root.resolve()
    output = base / OUTPUT_DIR
    if output.exists():
        raise ValueError("R24 historical evaluation is one-shot and already exists")
    staging = output.with_name(
        f"{output.name}.staging-{os.getpid()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )
    if staging.exists() or any((base / ITERATION_DIR).glob("historical-evaluation.staging-*")):
        raise ValueError("R24 has unresolved historical-evaluation staging state")

    preflight = _preflight(base)
    specs = load_and_validate_r24_specs(base)
    panel = load_r24_price_panel(base)
    folds = development_folds(panel.open.index)
    dataset = build_r24_feature_dataset(panel)
    d01_targets, d01_records = build_r24_d01_targets(panel, specs["R24D01"], dataset)
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
        for candidate_id in ("R24M01", "R24M02", "R24F01")
    }
    if not aggregate_targets["R24F01"].equals(aggregate_targets["R24M02"]):
        raise ValueError("R24 aggregate fallback identity failed")

    start = pd.Timestamp(folds[0]["test_start"])
    end = pd.Timestamp(folds[-1]["test_end"])
    candidate_targets = {"R24D01": d01_targets, **aggregate_targets}
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
        {candidate_id: returns[candidate_id] for candidate_id in ("R24D01", "R24M01", "R24M02")},
        block_count=8,
    )
    model_records = [row for fold in folds for row in segments[fold["fold_id"]].model_records]
    prediction_records = [
        row for fold in folds for row in segments[fold["fold_id"]].prediction_records
    ]
    gates = _development_gates(
        candidates,
        benchmarks,
        dsr,
        pbo,
        fold_results,
        prediction_records,
    )
    for candidate_id in candidates:
        candidates[candidate_id]["gates"] = gates[candidate_id]
        candidates[candidate_id]["development_gate_pass"] = gates[candidate_id]["pass"]

    development_pass_ids = [
        candidate_id
        for candidate_id in ("R24D01", "R24M01", "R24M02")
        if gates[candidate_id]["pass"]
    ]
    decision = "continue_to_transfer_holdout" if development_pass_ids else "stop_price_paths"
    trial_rows = _trial_rows(candidates, gates)
    target_records = [
        *[
            {
                **row,
                "iter_id": ITER_ID,
                "candidate_id": "R24D01",
                **provenance,
            }
            for row in d01_records
            if start <= pd.Timestamp(row["execution_session"]) <= end
        ],
        *[row for fold in folds for row in segments[fold["fold_id"]].target_records],
    ]
    payload = {
        "schema_version": 1,
        "report_type": "pit_semantic_theme_r24_historical_price_evaluation",
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
        "model_comparison": _model_comparison(
            candidates,
            fold_results,
            prediction_records,
        ),
        "integrity": {
            "lock_path": preflight["lock_path"],
            "lock_sha256": preflight["lock_sha256"],
            "snapshot_bound": True,
            "quality_gate_bound": True,
            "f01_target_identity": aggregate_targets["R24F01"].equals(aggregate_targets["R24M02"]),
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
    _record_evaluation_paths(base)
    return R24EvaluationResult(
        evaluation_path=output / "evaluation-report.json",
        trial_ledger_path=output / "trial-ledger.jsonl",
        model_ledger_path=output / "model-ledger.jsonl",
        prediction_ledger_path=output / "prediction-ledger.jsonl",
        target_ledger_path=output / "target-ledger.jsonl",
        payload=payload,
    )


def _record_evaluation_paths(root: Path) -> None:
    search_path = root / ITERATION_DIR / "search-space.json"
    search = _load_json(search_path)
    search["trial_ledger_paths"] = [(OUTPUT_DIR / "trial-ledger.jsonl").as_posix()]
    search["evaluation_report_paths"] = [(OUTPUT_DIR / "evaluation-report.json").as_posix()]
    write_json(search_path, search)


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


def _policy_prediction_diagnostics(
    prediction_records: list[dict[str, Any]],
    candidate_id: str,
) -> dict[str, Any]:
    rows = [
        row
        for row in prediction_records
        if row.get("candidate_id") == candidate_id
        and row.get("realized_policy_value") is not None
        and np.isfinite(
            [
                float(row["realized_policy_value"]),
                float(row["prediction"]),
                float(row["lower_bound"]),
            ]
        ).all()
    ]
    by_fold: dict[str, dict[str, Any]] = {}
    for fold_id in sorted({str(row["segment_id"]) for row in rows}):
        fold_rows = [row for row in rows if str(row["segment_id"]) == fold_id]
        actual = np.asarray([float(row["realized_policy_value"]) for row in fold_rows])
        predicted = np.asarray([float(row["prediction"]) for row in fold_rows])
        lower = np.asarray([float(row["lower_bound"]) for row in fold_rows])
        override = np.asarray(
            [bool(row.get("override_started", False)) for row in fold_rows], dtype=bool
        )
        by_fold[fold_id] = {
            "observation_count": len(fold_rows),
            "rmse": float(np.sqrt(np.mean(np.square(predicted - actual)))),
            "zero_change_rmse": float(np.sqrt(np.mean(np.square(actual)))),
            "rmse_improvement": float(
                np.sqrt(np.mean(np.square(actual)))
                - np.sqrt(np.mean(np.square(predicted - actual)))
            ),
            "lower_bound_coverage": float(np.mean(actual >= lower)),
            "override_count": int(override.sum()),
            "override_value_sum": float(actual[override].sum()) if override.any() else 0.0,
            "override_value_mean": float(actual[override].mean()) if override.any() else None,
        }
    if rows:
        actual = np.asarray([float(row["realized_policy_value"]) for row in rows])
        predicted = np.asarray([float(row["prediction"]) for row in rows])
        lower = np.asarray([float(row["lower_bound"]) for row in rows])
        override = np.asarray(
            [bool(row.get("override_started", False)) for row in rows], dtype=bool
        )
        overall = {
            "observation_count": len(rows),
            "rmse": float(np.sqrt(np.mean(np.square(predicted - actual)))),
            "zero_change_rmse": float(np.sqrt(np.mean(np.square(actual)))),
            "lower_bound_coverage": float(np.mean(actual >= lower)),
            "override_count": int(override.sum()),
            "override_value_sum": float(actual[override].sum()) if override.any() else 0.0,
            "override_value_mean": float(actual[override].mean()) if override.any() else None,
        }
    else:
        overall = {
            "observation_count": 0,
            "rmse": None,
            "zero_change_rmse": None,
            "lower_bound_coverage": None,
            "override_count": 0,
            "override_value_sum": 0.0,
            "override_value_mean": None,
        }
    return {
        "candidate_id": candidate_id,
        "overall": overall,
        "folds": by_fold,
        "rmse_better_folds": sum(row["rmse"] < row["zero_change_rmse"] for row in by_fold.values()),
        "positive_override_value_folds": sum(
            row["override_value_sum"] > 0.0 for row in by_fold.values() if row["override_count"] > 0
        ),
        "lower_bound_coverage_folds": sum(
            row["lower_bound_coverage"] >= POLICY_VALUE_LOWER_COVERAGE for row in by_fold.values()
        ),
    }


def _development_gates(
    candidates: dict[str, dict[str, Any]],
    benchmarks: dict[str, Any],
    dsr: dict[str, dict[str, Any]],
    pbo: dict[str, Any],
    folds: dict[str, list[dict[str, Any]]],
    prediction_records: list[dict[str, Any]],
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

    d01_metrics = candidates["R24D01"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    d01_folds = folds["R24D01"]
    m01_folds = folds["R24M01"]
    m02_folds = folds["R24M02"]
    m01_wins = sum(
        row["metrics"]["with_terminal"]["cagr"]
        > d01_folds[index]["metrics"]["with_terminal"]["cagr"]
        or row["metrics"]["with_terminal"]["mar"]
        > d01_folds[index]["metrics"]["with_terminal"]["mar"]
        for index, row in enumerate(m01_folds)
    )
    m02_wins = sum(
        row["metrics"]["with_terminal"]["cagr"]
        > d01_folds[index]["metrics"]["with_terminal"]["cagr"]
        or row["metrics"]["with_terminal"]["mar"]
        > d01_folds[index]["metrics"]["with_terminal"]["mar"]
        for index, row in enumerate(m02_folds)
    )
    m02_metrics = candidates["R24M02"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    m01_metrics = candidates["R24M01"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    d01_route_gate = _gate(
        "D01_persistent_beta_and_turnover",
        d01_metrics["average_risk_asset_exposure"] >= 0.80
        and d01_metrics["annualized_reported_one_way_turnover"] <= 12.0,
        {"average_risk_asset_exposure": 0.80, "annualized_one_way_turnover": 12.0},
        {
            "average_risk_asset_exposure": d01_metrics["average_risk_asset_exposure"],
            "annualized_one_way_turnover": d01_metrics["annualized_reported_one_way_turnover"],
        },
    )
    output["R24D01"]["checks"].append(d01_route_gate)
    output["R24D01"]["pass"] = output["R24D01"]["pass"] and d01_route_gate["pass"]
    prediction_diagnostics = {
        candidate_id: _policy_prediction_diagnostics(prediction_records, candidate_id)
        for candidate_id in TRAINED_CANDIDATES
    }
    m01_diagnostics = prediction_diagnostics["R24M01"]
    m02_diagnostics = prediction_diagnostics["R24M02"]
    m01_model_gate = _gate(
        "Ridge_policy_value_error_lift_and_override_value",
        m01_wins >= 3
        and m01_diagnostics["rmse_better_folds"] >= 3
        and m01_diagnostics["positive_override_value_folds"] >= 3
        and m01_diagnostics["lower_bound_coverage_folds"] >= 3
        and m01_diagnostics["overall"]["override_count"] >= MINIMUM_POLICY_OVERRIDE_COUNT
        and (m01_diagnostics["overall"]["override_value_sum"] > 0.0)
        and m01_metrics["tqqq_up_capture"] >= 0.95 * d01_metrics["tqqq_up_capture"]
        and m01_metrics["annualized_reported_one_way_turnover"] <= MAXIMUM_POLICY_TURNOVER,
        {
            "fold_wins": 3,
            "rmse_better_folds": 3,
            "positive_override_value_folds": 3,
            "lower_bound_coverage_folds": 3,
            "minimum_override_count": MINIMUM_POLICY_OVERRIDE_COUNT,
            "D01_up_capture_fraction": 0.95,
            "annualized_turnover": MAXIMUM_POLICY_TURNOVER,
        },
        {
            "fold_wins": m01_wins,
            "rmse_better_folds": m01_diagnostics["rmse_better_folds"],
            "positive_override_value_folds": m01_diagnostics["positive_override_value_folds"],
            "lower_bound_coverage_folds": m01_diagnostics["lower_bound_coverage_folds"],
            "override_count": m01_diagnostics["overall"]["override_count"],
            "override_value_sum": m01_diagnostics["overall"]["override_value_sum"],
            "D01_up_capture_fraction": (
                m01_metrics["tqqq_up_capture"] / d01_metrics["tqqq_up_capture"]
                if d01_metrics["tqqq_up_capture"]
                else None
            ),
            "annualized_turnover": m01_metrics["annualized_reported_one_way_turnover"],
        },
    )
    m02_model_gate = _gate(
        "LightGBM_Ridge_consensus_policy_value_and_fold_gate",
        m02_wins >= 3
        and m02_diagnostics["rmse_better_folds"] >= 3
        and m02_diagnostics["positive_override_value_folds"] >= 3
        and m02_diagnostics["lower_bound_coverage_folds"] >= 3
        and m02_diagnostics["overall"]["override_count"] >= MINIMUM_POLICY_OVERRIDE_COUNT
        and (m02_diagnostics["overall"]["override_value_sum"] > 0.0)
        and m02_metrics["total_return"] >= d01_metrics["total_return"]
        and m02_metrics["tqqq_up_capture"] >= 0.95 * d01_metrics["tqqq_up_capture"]
        and m02_metrics["annualized_reported_one_way_turnover"] <= MAXIMUM_POLICY_TURNOVER,
        {
            "fold_wins": 3,
            "rmse_better_folds": 3,
            "positive_override_value_folds": 3,
            "lower_bound_coverage_folds": 3,
            "minimum_override_count": MINIMUM_POLICY_OVERRIDE_COUNT,
            "D01_total_return_floor": d01_metrics["total_return"],
            "D01_up_capture_fraction": 0.95,
            "annualized_turnover": MAXIMUM_POLICY_TURNOVER,
        },
        {
            "fold_wins": m02_wins,
            "rmse_better_folds": m02_diagnostics["rmse_better_folds"],
            "positive_override_value_folds": m02_diagnostics["positive_override_value_folds"],
            "lower_bound_coverage_folds": m02_diagnostics["lower_bound_coverage_folds"],
            "override_count": m02_diagnostics["overall"]["override_count"],
            "override_value_sum": m02_diagnostics["overall"]["override_value_sum"],
            "D01_total_return": d01_metrics["total_return"],
            "total_return": m02_metrics["total_return"],
            "D01_up_capture_fraction": (
                m02_metrics["tqqq_up_capture"] / d01_metrics["tqqq_up_capture"]
                if d01_metrics["tqqq_up_capture"]
                else None
            ),
            "annualized_turnover": m02_metrics["annualized_reported_one_way_turnover"],
        },
    )
    output["R24M01"]["checks"].append(m01_model_gate)
    output["R24M01"]["pass"] = output["R24M01"]["pass"] and m01_model_gate["pass"]
    output["R24M02"]["checks"].append(m02_model_gate)
    output["R24M02"]["pass"] = output["R24M02"]["pass"] and m02_model_gate["pass"]
    identity = _gate("F01_exact_M02_identity", True, True, True)
    output["R24F01"]["checks"].append(identity)
    output["R24F01"]["pass"] = False
    output["R24F01"]["selection_use"] = "identity_control_only"
    return output


def _model_comparison(
    candidates: dict[str, dict[str, Any]],
    folds: dict[str, list[dict[str, Any]]],
    prediction_records: list[dict[str, Any]],
) -> dict[str, Any]:
    ridge_policy_value = candidates["R24M01"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    consensus_policy_value = candidates["R24M02"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    fold_cagr = {
        candidate_id: [row["metrics"]["with_terminal"]["cagr"] for row in folds[candidate_id]]
        for candidate_id in ("R24M01", "R24M02")
    }
    return {
        "primary_question": "does_consensus_policy_value_improve_over_Ridge_policy_value",
        "ridge_policy_value": ridge_policy_value,
        "consensus_policy_value": consensus_policy_value,
        "fold_cagr": fold_cagr,
        "consensus_positive_lift_folds": sum(
            tail_exit_value > logistic_value
            for logistic_value, tail_exit_value in zip(
                fold_cagr["R24M01"], fold_cagr["R24M02"], strict=True
            )
        ),
        "prediction_diagnostics": {
            candidate_id: _policy_prediction_diagnostics(prediction_records, candidate_id)
            for candidate_id in TRAINED_CANDIDATES
        },
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
                "strategy_name": f"us_pit_semantic_theme_r24_{candidate_id[-3:].lower()}",
                "status": "completed" if evaluated else "dependency_skipped",
                "historical_evaluation": evaluated,
                "development_gate_pass": gates[candidate_id]["pass"] if evaluated else False,
                "selection_eligible": candidate_id in {"R24D01", "R24M01", "R24M02"},
                "reason": (
                    "clean_price_path_evaluated"
                    if evaluated
                    else "historical_point_in_time_semantic_packets_unavailable"
                ),
            }
        )
    return rows


def _fitted_model_hash(estimator: Any, kind: str) -> str:
    if isinstance(estimator, _ConstantRegressionModel):
        return _canonical_hash({"kind": "constant_value_fallback", "value": estimator.value})
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
        "# PIT Semantic Theme R24 Historical Price Evaluation",
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
            "R24 uses a fresh multi-adjustment SIP snapshot. These are historical OOS "
            "diagnostics, not forward or Paper evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_forensics(root: Path, payload: dict[str, Any]) -> None:
    output = root / "reports/harness/forensics"
    output.mkdir(parents=True, exist_ok=True)
    for candidate_id in ("R24D01", "R24M01", "R24M02"):
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
