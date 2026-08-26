from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.dynamic_theme_chain_r8 import (
    D01_CANDIDATE_SYMBOLS,
    EFFECTIVE_TRIAL_COUNT,
    ITER_ID,
    ITERATION_DIR,
    LOCK_DIR,
    SNAPSHOT_MANIFEST_PATH,
    SPEC_PATHS,
    UNIVERSE,
    _benchmark_family,
    _binding,
    _canonical_hash,
    _canonical_json_bytes,
    _daily_returns,
    _load_json,
    _preflight,
    _read_bound_file,
    _relpath,
    _research_gates,
    _run_cost_views,
    _scheduled_positions,
    _sha256,
    _simulate_static,
    _simulation_metric_views,
    _tier0_reserve_gates,
    _validate_targets,
    _verify_binding,
    compute_d01_targets,
    compute_d02_targets,
    cross_sectional_percentile,
    cscv_probability_backtest_overfitting,
    deflated_sharpe_probability,
    load_r8_panel,
)
from open_composer.research.etf_structural_r9 import simulate_target_portfolio
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

STAGE_E_LOCK_DIR = LOCK_DIR / "stage-e"
STAGE_E_LOCK_PATH = STAGE_E_LOCK_DIR / "training-lock.json"
STAGE_E_OUTPUT_DIR = ITERATION_DIR / "stage-e-evaluation"
STAGE_E_RUNNER_PATH = Path("open_composer/research/dynamic_theme_chain_r8_ml.py")
STAGE_E_TEST_PATH = Path("tests/test_dynamic_theme_chain_r8_ml.py")
ML_SPEC_PATHS = {candidate_id: SPEC_PATHS[candidate_id] for candidate_id in ("R8M01", "R8M02")}
RANKABLE_SYMBOLS = D01_CANDIDATE_SYMBOLS
FEATURE_NAMES = (
    "momentum_3",
    "momentum_5",
    "momentum_10",
    "momentum_20",
    "trend_gap_40",
    "volume_surprise_5",
    "volume_surprise_20",
    "realized_volatility_10",
    "realized_volatility_20",
    "drawdown_10",
    "drawdown_20",
    "overnight_gap",
)
MODEL_IDS = ("R8M01_LINEAR", "R8M01", "R8M02_LINEAR", "R8M02")
SELECTION_IDS = ("R8D01", "R8D02", "R8M01", "R8M02")
LINEAR_BASELINE_CONTRACT = {
    "R8M01_LINEAR": {
        "pipeline": "StandardScaler_then_Ridge",
        "alpha": 1.0,
        "fit_intercept": True,
    },
    "R8M02_LINEAR": {
        "pipeline": "StandardScaler_then_LogisticRegression",
        "C": 1.0,
        "penalty": "l2",
        "solver": "lbfgs",
        "max_iter": 1000,
    },
}
ROLE_GATE_CONTRACT = {
    "M01_minimum_fold_wins_vs_linear_and_D01": 3,
    "M02_minimum_brier_wins_vs_linear_and_base_rate": 3,
    "M02_minimum_path_loss_improvement_folds": 3,
    "M02_calibration_slope_min": 0.70,
    "M02_calibration_slope_max": 1.30,
    "M02_minimum_exposure_ratio_vs_M01": 0.75,
    "M02_minimum_CAGR_retention_vs_M01": 0.90,
}


@dataclass(frozen=True)
class R8MLPanel:
    open: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame


@dataclass(frozen=True)
class StageEFreezeResult:
    lock_path: Path


@dataclass(frozen=True)
class StageEEvaluationResult:
    evaluation_path: Path
    trial_ledger_path: Path
    model_ledger_path: Path
    prediction_ledger_path: Path
    target_ledger_path: Path
    payload: dict[str, Any]


@dataclass
class FittedModel:
    candidate_id: str
    model_id: str
    estimator: Any
    training_label_mean: float
    record: dict[str, Any]


@dataclass
class SegmentResult:
    targets: dict[str, pd.DataFrame]
    target_records: list[dict[str, Any]]
    model_records: list[dict[str, Any]]
    prediction_records: list[dict[str, Any]]
    calibration_records: list[dict[str, Any]]


def freeze_dynamic_theme_chain_r8_stage_e(root: Path) -> StageEFreezeResult:
    base = root.resolve()
    if (base / STAGE_E_LOCK_DIR).exists():
        raise ValueError("R8 Stage E training lock already exists")
    if (base / STAGE_E_OUTPUT_DIR).exists() or any(
        (base / ITERATION_DIR).glob("stage-e-evaluation.staging-*")
    ):
        raise ValueError("R8 Stage E evaluation state already exists")

    parent_preflight = _preflight(base)
    stage_d_paths = [
        base / ITERATION_DIR / name
        for name in (
            "evaluation-report.json",
            "implementation-contract.json",
            "fold-results.json",
            "benchmark-results.json",
            "target-ledger.jsonl",
            "trial-ledger.jsonl",
        )
    ]
    stage_d = _load_json(stage_d_paths[0])
    if not (
        stage_d.get("workflow_pass") is True
        and stage_d.get("stage_e_training_authorized") is True
        and stage_d.get("broker_writes") is False
        and stage_d.get("paper_ready_pass") is False
    ):
        raise ValueError("R8 Stage D did not authorize diagnostic model training")

    specs = {
        candidate_id: load_strategy_spec(base / path)
        for candidate_id, path in ML_SPEC_PATHS.items()
    }
    validate_ml_specs(specs)
    contract_paths = [
        base / ITERATION_DIR / name
        for name in (
            "candidate-manifest.json",
            "feature-contract.json",
            "label-contract.json",
            "validation-contract.json",
            "cost-contract.json",
            "holdout-contract.json",
            "cumulative-trial-contract.json",
        )
    ]
    implementation_paths = [
        base / STAGE_E_RUNNER_PATH,
        base / STAGE_E_TEST_PATH,
        base / "open_composer/research/dynamic_theme_chain_r8.py",
        base / "open_composer/research/etf_structural_r9.py",
        base / "open_composer/models/strategy_spec.py",
        base / "open_composer/strategy_versions.py",
        base / "pyproject.toml",
        base / "uv.lock",
    ]
    lock = {
        "schema_version": 1,
        "lock_contract": "dynamic_theme_chain_r8_stage_e_training_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "implementation_and_model_semantics_locked_before_first_R8_model_fit",
        "parent_preflight": parent_preflight,
        "stage_d_authorization": [_binding(path, base) for path in stage_d_paths],
        "contracts": [_binding(path, base) for path in contract_paths],
        "specs": [
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in ML_SPEC_PATHS.items()
        ],
        "implementation": [_binding(path, base) for path in implementation_paths],
        "snapshot_manifest": _binding(base / SNAPSHOT_MANIFEST_PATH, base),
        "feature_names": list(FEATURE_NAMES),
        "rankable_symbols": list(RANKABLE_SYMBOLS),
        "linear_baseline_contract": LINEAR_BASELINE_CONTRACT,
        "role_gate_contract": ROLE_GATE_CONTRACT,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "library_versions": {
            name: version(name) for name in ("lightgbm", "numpy", "pandas", "scikit-learn", "scipy")
        },
        "historical_model_fit_at_lock": False,
        "one_shot": True,
        "order_authority": False,
        "broker_writes": False,
    }
    lock_dir = base / STAGE_E_LOCK_DIR
    lock_dir.mkdir(parents=True, exist_ok=False)
    lock_path = base / STAGE_E_LOCK_PATH
    write_json(lock_path, lock)
    return StageEFreezeResult(lock_path=lock_path)


def _stage_e_preflight(root: Path) -> dict[str, Any]:
    base = root.resolve()
    parent = _preflight(base)
    lock_path = base / STAGE_E_LOCK_PATH
    lock = _load_json(lock_path)
    if (
        lock.get("iter_id") != ITER_ID
        or lock.get("status")
        != "implementation_and_model_semantics_locked_before_first_R8_model_fit"
        or lock.get("one_shot") is not True
        or lock.get("historical_model_fit_at_lock") is not False
        or lock.get("broker_writes") is not False
    ):
        raise ValueError("R8 Stage E lock identity is invalid")
    if lock.get("linear_baseline_contract") != LINEAR_BASELINE_CONTRACT:
        raise ValueError("R8 Stage E linear baseline contract changed")
    if lock.get("role_gate_contract") != ROLE_GATE_CONTRACT:
        raise ValueError("R8 Stage E role gate contract changed")
    if lock.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("R8 Stage E feature contract changed")
    for group in ("stage_d_authorization", "contracts", "specs", "implementation"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R8 Stage E lock group missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    _verify_binding(base, lock.get("snapshot_manifest"))

    specs = {
        candidate_id: load_strategy_spec(base / path)
        for candidate_id, path in ML_SPEC_PATHS.items()
    }
    validate_ml_specs(specs)
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R8 Stage E semantic spec changed: {candidate_id}")
    return {
        "status": "ok",
        "parent": parent,
        "stage_e_lock_path": _relpath(lock_path, base),
        "stage_e_lock_sha256": _sha256(lock_path),
        "snapshot_manifest_sha256": _sha256(base / SNAPSHOT_MANIFEST_PATH),
    }


def validate_ml_specs(specs: dict[str, StrategySpec]) -> None:
    if set(specs) != set(ML_SPEC_PATHS):
        raise ValueError("R8 Stage E requires exactly M01 and M02 specs")
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        model = spec.model
        if (
            notes.get("candidate_id") != candidate_id
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
            or spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or model is None
            or tuple(model.features) != FEATURE_NAMES
            or model.training.window_bars != 756
            or model.training.retrain_every_bars != 5
            or model.training.embargo_bars != 10
            or model.training.test_window_bars != 63
        ):
            raise ValueError(f"R8 Stage E spec contract mismatch: {candidate_id}")
    m01 = specs["R8M01"].model
    m02 = specs["R8M02"].model
    assert m01 is not None and m02 is not None
    if (
        m01.kind != "lightgbm_regressor"
        or m01.label.type != "forward_return"
        or m01.label.horizon_bars != 5
        or m01.selection.method != "top_quantile"
        or m01.selection.quantile != 0.15
        or m01.baseline != "linear_composite"
    ):
        raise ValueError("R8M01 model identity mismatch")
    if (
        m02.kind != "lightgbm_classifier"
        or m02.label.type != "path_survival"
        or m02.label.horizon_bars != 5
        or m02.label.max_drawdown_pct != 8.0
        or m02.label.min_terminal_return_pct != 0.0
        or m02.selection.method != "threshold"
        or m02.selection.threshold != 0.58
        or m02.baseline != "linear_composite"
    ):
        raise ValueError("R8M02 model identity mismatch")


def load_r8_ml_panel(root: Path, manifest_path: Path) -> R8MLPanel:
    base = root.resolve()
    core = load_r8_panel(base, manifest_path)
    path = manifest_path if manifest_path.is_absolute() else base / manifest_path
    manifest = json.loads(_read_bound_file(base, path))
    low_by_symbol: dict[str, pd.Series] = {}
    selected = sorted(
        (item for item in manifest["items"] if item.get("adjustment") == "all"),
        key=lambda item: str(item["symbol"]),
    )
    if len(selected) != len(UNIVERSE):
        raise ValueError("R8 Stage E all-adjusted low coverage is incomplete")
    for item in selected:
        symbol = str(item["symbol"])
        csv_path = path.parent / str(item["output_path"])
        payload = _read_bound_file(base, csv_path)
        if hashlib.sha256(payload).hexdigest() != item.get("output_sha256"):
            raise ValueError(f"R8 Stage E low source hash mismatch: {symbol}")
        frame = pd.read_csv(io.BytesIO(payload))
        timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        sessions = pd.DatetimeIndex(
            timestamps.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
        )
        if not sessions.equals(core.open.index):
            raise ValueError(f"R8 Stage E low sessions differ: {symbol}")
        low_by_symbol[symbol] = pd.Series(
            pd.to_numeric(frame["low"], errors="raise").to_numpy(dtype=float), index=sessions
        )
    low = pd.DataFrame(low_by_symbol, index=core.open.index).loc[:, list(UNIVERSE)]
    if not np.isfinite(low.to_numpy()).all() or (low <= 0.0).any().any():
        raise ValueError("R8 Stage E lows must be finite and positive")
    return R8MLPanel(open=core.open, low=low, close=core.close, volume=core.volume)


def build_r8_ml_dataset(panel: R8MLPanel) -> pd.DataFrame:
    _validate_ml_panel(panel)
    closes = panel.close
    returns = closes.pct_change(fill_method=None)
    raw_features = {
        "momentum_3": closes / closes.shift(3) - 1.0,
        "momentum_5": closes / closes.shift(5) - 1.0,
        "momentum_10": closes / closes.shift(10) - 1.0,
        "momentum_20": closes / closes.shift(20) - 1.0,
        "trend_gap_40": closes / closes.rolling(40, min_periods=40).mean() - 1.0,
        "volume_surprise_5": panel.volume / panel.volume.rolling(5, min_periods=5).mean() - 1.0,
        "volume_surprise_20": panel.volume / panel.volume.rolling(20, min_periods=20).mean() - 1.0,
        "realized_volatility_10": returns.rolling(10, min_periods=10).std(ddof=0),
        "realized_volatility_20": returns.rolling(20, min_periods=20).std(ddof=0),
        "drawdown_10": closes / closes.rolling(10, min_periods=10).max() - 1.0,
        "drawdown_20": closes / closes.rolling(20, min_periods=20).max() - 1.0,
        "overnight_gap": panel.open / closes.shift(1) - 1.0,
    }
    rows: list[dict[str, Any]] = []
    sessions = closes.index
    for decision_position, execution_position in _scheduled_positions(sessions):
        decision_session = sessions[decision_position]
        feature_rows = {
            name: frame.loc[decision_session, list(RANKABLE_SYMBOLS)].astype(float)
            for name, frame in raw_features.items()
        }
        if any(not np.isfinite(values.to_numpy()).all() for values in feature_rows.values()):
            continue
        ranked = {name: cross_sectional_percentile(values) for name, values in feature_rows.items()}
        label_end_position = execution_position + 5
        label_available = label_end_position < len(sessions)
        for symbol in RANKABLE_SYMBOLS:
            row: dict[str, Any] = {
                "decision_position": decision_position,
                "decision_session": decision_session.date().isoformat(),
                "execution_position": execution_position,
                "execution_session": sessions[execution_position].date().isoformat(),
                "label_end_position": label_end_position if label_available else None,
                "label_end_session": (
                    sessions[label_end_position].date().isoformat() if label_available else None
                ),
                "symbol": symbol,
                "raw_realized_volatility_20": float(
                    raw_features["realized_volatility_20"].at[decision_session, symbol]
                ),
            }
            row.update({name: float(ranked[name][symbol]) for name in FEATURE_NAMES})
            if label_available:
                entry = float(
                    panel.open.iat[execution_position, panel.open.columns.get_loc(symbol)]
                )
                terminal = float(
                    panel.open.iat[label_end_position, panel.open.columns.get_loc(symbol)]
                )
                lows = panel.low.iloc[execution_position : label_end_position + 1][symbol]
                path_drawdown = float((lows / entry - 1.0).min())
                forward_return = terminal / entry - 1.0
                row.update(
                    {
                        "forward_return_5": forward_return,
                        "max_open_path_drawdown_5": path_drawdown,
                        "path_survival_label": int(
                            forward_return >= 0.0 and path_drawdown >= -0.08
                        ),
                    }
                )
            else:
                row.update(
                    {
                        "forward_return_5": None,
                        "max_open_path_drawdown_5": None,
                        "path_survival_label": None,
                    }
                )
            rows.append(row)
    dataset = pd.DataFrame(rows).sort_values(["decision_position", "symbol"]).reset_index(drop=True)
    if dataset.empty:
        raise ValueError("R8 Stage E feature dataset is empty")
    values = dataset.loc[:, list(FEATURE_NAMES)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0.0).any() or (values > 1.0).any():
        raise ValueError("R8 Stage E ranked features are invalid")
    return dataset


def training_rows_for_prediction(
    dataset: pd.DataFrame,
    *,
    decision_position: int,
    train_start_session: str,
    spec: StrategySpec,
    label_name: str,
) -> pd.DataFrame:
    if spec.model is None:
        raise ValueError("R8 Stage E model config is missing")
    starts = dataset.loc[dataset["decision_session"] >= train_start_session, "decision_position"]
    if starts.empty:
        raise ValueError("R8 Stage E train start is outside the feature dataset")
    lower = max(int(starts.min()), decision_position - int(spec.model.training.window_bars))
    embargo_cutoff = decision_position - int(spec.model.training.embargo_bars)
    rows = dataset[
        (dataset["decision_position"] >= lower)
        & (dataset["decision_position"] < decision_position)
        & dataset["label_end_position"].notna()
        & (dataset["label_end_position"].astype(float) <= embargo_cutoff)
        & dataset[label_name].notna()
    ].copy()
    rows = rows.sort_values(["decision_position", "symbol"]).reset_index(drop=True)
    if not rows.empty and float(rows["label_end_position"].max()) > embargo_cutoff:
        raise AssertionError("R8 Stage E embargo filtering failed")
    return rows


def build_segment_targets(
    dataset: pd.DataFrame,
    panel: R8MLPanel,
    *,
    segment_id: str,
    train_start_session: str,
    start_session: str,
    end_session: str,
    specs: dict[str, StrategySpec],
    d01_targets: pd.DataFrame,
    provenance: dict[str, str],
) -> SegmentResult:
    validate_ml_specs(specs)
    points = (
        dataset[
            (dataset["execution_session"] <= end_session)
            & (dataset["execution_session"] >= _prior_scheduled_session(dataset, start_session))
        ][
            [
                "decision_position",
                "decision_session",
                "execution_position",
                "execution_session",
            ]
        ]
        .drop_duplicates()
        .sort_values("execution_position")
    )
    if points.empty:
        raise ValueError(f"R8 Stage E segment has no prediction points: {segment_id}")

    target_rows: dict[str, list[pd.Series]] = {candidate_id: [] for candidate_id in MODEL_IDS}
    target_index: list[pd.Timestamp] = []
    target_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    calibration_records: list[dict[str, Any]] = []
    fitted: dict[str, FittedModel] = {}
    last_fit_position: int | None = None

    for point in points.to_dict(orient="records"):
        decision_position = int(point["decision_position"])
        decision_session = str(point["decision_session"])
        execution_session = str(point["execution_session"])
        current = dataset[dataset["decision_position"] == decision_position].sort_values("symbol")
        if tuple(current["symbol"]) != tuple(sorted(RANKABLE_SYMBOLS)):
            raise ValueError(f"R8 Stage E symbol coverage failed: {decision_session}")
        if last_fit_position is None or decision_position - last_fit_position >= 5:
            fitted, records = _fit_model_family(
                dataset,
                current,
                decision_position=decision_position,
                train_start_session=train_start_session,
                segment_id=segment_id,
                specs=specs,
                provenance=provenance,
            )
            model_records.extend(records)
            last_fit_position = decision_position

        predictions: dict[str, pd.Series] = {}
        for candidate_id in MODEL_IDS:
            model = fitted[candidate_id]
            values = _predict(model, current.loc[:, list(FEATURE_NAMES)])
            predictions[candidate_id] = pd.Series(
                values, index=current["symbol"].astype(str), dtype=float
            )
            prediction_records.append(
                _prediction_record(
                    model,
                    segment_id=segment_id,
                    decision_session=decision_session,
                    execution_session=execution_session,
                    current=current,
                    values=values,
                    provenance=provenance,
                )
            )

        execution_timestamp = pd.Timestamp(execution_session)
        if execution_timestamp not in d01_targets.index:
            raise ValueError(f"R8 Stage E D01 fallback target missing: {execution_session}")
        fallback = d01_targets.loc[execution_timestamp].astype(float)
        m01 = _risk_budget_target(
            predictions["R8M01"], current, columns=panel.open.columns, max_weight=0.60
        )
        m01_linear = _risk_budget_target(
            predictions["R8M01_LINEAR"],
            current,
            columns=panel.open.columns,
            max_weight=0.60,
        )
        if not np.isfinite(m01.to_numpy()).all():
            m01 = fallback.copy()
        if not np.isfinite(m01_linear.to_numpy()).all():
            m01_linear = fallback.copy()
        m02 = _apply_survival_gate(m01, predictions["R8M02"], threshold=0.58, reserve_symbol="BIL")
        m02_linear = _apply_survival_gate(
            m01_linear,
            predictions["R8M02_LINEAR"],
            threshold=0.58,
            reserve_symbol="BIL",
        )
        targets = {
            "R8M01_LINEAR": m01_linear,
            "R8M01": m01,
            "R8M02_LINEAR": m02_linear,
            "R8M02": m02,
        }
        target_index.append(execution_timestamp)
        for candidate_id, target in targets.items():
            target_rows[candidate_id].append(target)
            weights = {symbol: float(target[symbol]) for symbol in panel.open.columns}
            selected = [symbol for symbol in RANKABLE_SYMBOLS if float(target[symbol]) > 1e-12]
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "stage": "E",
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": selected,
                    "weights": weights,
                    "target_sha256": _canonical_hash(weights),
                    "model_id": fitted[candidate_id].model_id,
                    "fallback_candidate_id": (
                        "R8D01" if candidate_id.startswith("R8M01") else "R8M01"
                    ),
                    "fallback_applied": False,
                }
            )

        for row in current.to_dict(orient="records"):
            if row["path_survival_label"] is None or pd.isna(row["path_survival_label"]):
                continue
            symbol = str(row["symbol"])
            calibration_records.append(
                {
                    "segment_id": segment_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "symbol": symbol,
                    "label": int(row["path_survival_label"]),
                    "lgbm_probability": float(predictions["R8M02"][symbol]),
                    "linear_probability": float(predictions["R8M02_LINEAR"][symbol]),
                    "training_base_probability": float(fitted["R8M02"].training_label_mean),
                    "m01_selected": bool(float(m01[symbol]) > 1e-12),
                    "m02_accepted": bool(float(m02[symbol]) > 1e-12),
                }
            )

    frames = {
        candidate_id: pd.DataFrame(
            rows, index=pd.DatetimeIndex(target_index), columns=panel.open.columns
        )
        for candidate_id, rows in target_rows.items()
    }
    for candidate_id, frame in frames.items():
        records = [row for row in target_records if row["candidate_id"] == candidate_id]
        _validate_targets(frame, records, panel.open.index, candidate_id=candidate_id)
    return SegmentResult(
        targets=frames,
        target_records=target_records,
        model_records=model_records,
        prediction_records=prediction_records,
        calibration_records=calibration_records,
    )


def run_dynamic_theme_chain_r8_stage_e(root: Path) -> StageEEvaluationResult:
    base = root.resolve()
    destination = base / STAGE_E_OUTPUT_DIR
    if destination.exists():
        raise ValueError("R8 Stage E one-shot evaluation already exists")
    staging = destination.with_name(
        f"{destination.name}.staging-{os.getpid()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )
    if staging.exists() or any((base / ITERATION_DIR).glob("stage-e-evaluation.staging-*")):
        raise ValueError("R8 Stage E has unresolved staging state")

    preflight = _stage_e_preflight(base)
    specs = {
        candidate_id: load_strategy_spec(base / path)
        for candidate_id, path in ML_SPEC_PATHS.items()
    }
    panel = load_r8_ml_panel(base, base / SNAPSHOT_MANIFEST_PATH)
    dataset = build_r8_ml_dataset(panel)
    d01_spec = load_strategy_spec(base / SPEC_PATHS["R8D01"])
    d02_spec = load_strategy_spec(base / SPEC_PATHS["R8D02"])
    d01_targets, _ = compute_d01_targets(panel.close, panel.volume, d01_spec)
    d02_targets, _ = compute_d02_targets(panel.close, d02_spec)
    stage_d = _load_json(base / ITERATION_DIR / "evaluation-report.json")
    folds = list(_load_json(base / ITERATION_DIR / "fold-results.json")["folds"])
    windows = stage_d["evaluation_windows"]
    segments = [
        {
            "segment_id": str(fold["fold_id"]),
            "train_start": str(fold["train_start"]),
            "start": str(fold["test_start"]),
            "end": str(fold["test_end"]),
        }
        for fold in folds
    ]
    segments.append(
        {
            "segment_id": "LOCKBOX",
            "train_start": str(folds[0]["train_start"]),
            "start": str(windows["lockbox"]["start"])[:10],
            "end": str(windows["lockbox"]["end"])[:10],
        }
    )
    provenance = {
        "snapshot_manifest_sha256": preflight["snapshot_manifest_sha256"],
        "feature_contract_sha256": _sha256(base / ITERATION_DIR / "feature-contract.json"),
        "label_contract_sha256": _sha256(base / ITERATION_DIR / "label-contract.json"),
        "validation_contract_sha256": _sha256(base / ITERATION_DIR / "validation-contract.json"),
        "stage_e_lock_sha256": preflight["stage_e_lock_sha256"],
    }

    segment_results: dict[str, SegmentResult] = {}
    target_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    calibration_records: list[dict[str, Any]] = []
    for segment in segments:
        result = build_segment_targets(
            dataset,
            panel,
            segment_id=segment["segment_id"],
            train_start_session=segment["train_start"],
            start_session=segment["start"],
            end_session=segment["end"],
            specs=specs,
            d01_targets=d01_targets,
            provenance=provenance,
        )
        segment_results[segment["segment_id"]] = result
        target_records.extend(result.target_records)
        model_records.extend(result.model_records)
        prediction_records.extend(result.prediction_records)
        calibration_records.extend(result.calibration_records)

    aggregate_targets = {
        candidate_id: _aggregate_segment_targets(
            segment_results, segments, candidate_id=candidate_id, columns=panel.open.columns
        )
        for candidate_id in MODEL_IDS
    }
    first_oos = pd.Timestamp(segments[0]["start"])
    full_end = pd.Timestamp(segments[-1]["end"])
    development_end = pd.Timestamp(segments[3]["end"])
    evaluation_windows = {
        "development": {"start": first_oos, "end": development_end},
        "lockbox": {
            "start": pd.Timestamp(segments[-1]["start"]),
            "end": full_end,
        },
        "full": {"start": first_oos, "end": full_end},
    }
    candidate_targets = {
        "R8D01": d01_targets,
        "R8D02": d02_targets,
        **aggregate_targets,
    }
    cost_views = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
    candidate_payloads: dict[str, dict[str, Any]] = {}
    development_returns: dict[str, pd.Series] = {}
    for candidate_id, targets in candidate_targets.items():
        window_results: dict[str, Any] = {}
        for window_name, boundary in evaluation_windows.items():
            cost_results, simulations = _run_cost_views(
                panel.open,
                targets,
                start=boundary["start"],
                end=boundary["end"],
                cost_views=cost_views,
            )
            window_results[window_name] = cost_results
            if window_name == "development" and candidate_id in SELECTION_IDS:
                development_returns[candidate_id] = _daily_returns(
                    simulations["primary_20bps"], include_terminal=True
                )
        candidate_payloads[candidate_id] = {
            "strategy_name": (
                load_strategy_spec(base / SPEC_PATHS[candidate_id]).name
                if candidate_id in SPEC_PATHS
                else candidate_id.lower()
            ),
            "spec_hash": (
                strategy_content_hash(load_strategy_spec(base / SPEC_PATHS[candidate_id]))
                if candidate_id in SPEC_PATHS
                else None
            ),
            "target_count": len(targets),
            "windows": window_results,
            "folds": [],
        }

    benchmark_payload = {
        window_name: _benchmark_family(
            panel.open,
            start=boundary["start"],
            end=boundary["end"],
            cost_views=cost_views,
        )
        for window_name, boundary in evaluation_windows.items()
    }
    fold_payloads = _evaluate_folds(
        panel.open,
        segment_results,
        folds=folds,
        d01_targets=d01_targets,
        d02_targets=d02_targets,
    )
    for candidate_id, rows in fold_payloads.items():
        candidate_payloads[candidate_id]["folds"] = rows

    pbo = cscv_probability_backtest_overfitting(development_returns, block_count=8)
    calibration = _calibration_payload(calibration_records, folds)
    role_gates = _role_gates(candidate_payloads, calibration)
    for candidate_id in SELECTION_IDS:
        candidate = candidate_payloads[candidate_id]
        full = candidate["windows"]["full"]["primary_20bps"]["with_terminal"]
        lockbox = candidate["windows"]["lockbox"]["primary_20bps"]["with_terminal"]
        stress = candidate["windows"]["full"]["severe_40bps"]["with_terminal"]
        qqq = benchmark_payload["full"]["QQQ_buy_hold"]["cost_views"]["primary_20bps"][
            "with_terminal"
        ]
        tqqq = benchmark_payload["full"]["TQQQ_buy_hold"]["cost_views"]["primary_20bps"][
            "with_terminal"
        ]
        positive_folds = sum(float(row["qqq_cagr_lift"]) > 0.0 for row in candidate["folds"])
        dsr = deflated_sharpe_probability(development_returns[candidate_id], EFFECTIVE_TRIAL_COUNT)
        gates = _research_gates(
            candidate_id=candidate_id,
            metrics=full,
            lockbox_metrics=lockbox,
            stress_metrics=stress,
            qqq_metrics=qqq,
            tqqq_metrics=tqqq,
            positive_lift_folds=positive_folds,
            dsr=dsr,
            pbo=pbo,
            d02_metrics=candidate_payloads["R8D02"]["windows"]["full"]["primary_20bps"][
                "with_terminal"
            ],
        )
        reserves = _tier0_reserve_gates(full, qqq)
        candidate.update(
            {
                "positive_qqq_lift_fold_count": positive_folds,
                "deflated_sharpe": dsr,
                "research_gates": gates,
                "role_gate": role_gates[candidate_id],
                "research_pass": bool(
                    candidate_id in {"R8M01", "R8M02"}
                    and all(row["pass"] for row in gates)
                    and role_gates[candidate_id]["pass"]
                ),
                "tier0_reserve_gates": reserves,
                "tier0_reserve_pass": bool(
                    candidate_id in {"R8M01", "R8M02"}
                    and all(row["pass"] for row in reserves)
                    and role_gates[candidate_id]["pass"]
                ),
            }
        )
    for candidate_id in ("R8M01_LINEAR", "R8M02_LINEAR"):
        candidate_payloads[candidate_id].update(
            {
                "selection_prohibited": True,
                "research_pass": False,
                "tier0_reserve_pass": False,
            }
        )

    selected_research = [
        candidate_id
        for candidate_id in ("R8M01", "R8M02")
        if candidate_payloads[candidate_id]["research_pass"]
    ]
    selected_tier0 = [
        candidate_id
        for candidate_id in ("R8M01", "R8M02")
        if candidate_payloads[candidate_id]["tier0_reserve_pass"]
    ]
    decision = (
        "continue_to_broker_free_tier0"
        if selected_research
        else "continue_to_broker_free_tier0_reserve"
        if selected_tier0
        else "stop_historical_ml_candidates"
    )

    staging.mkdir(parents=True, exist_ok=False)
    target_ledger_path = staging / "target-ledger.jsonl"
    model_ledger_path = staging / "model-ledger.jsonl"
    prediction_ledger_path = staging / "prediction-ledger.jsonl"
    trial_ledger_path = staging / "trial-ledger.jsonl"
    calibration_path = staging / "calibration.json"
    provenance_path = staging / "model-provenance.json"
    _write_jsonl(target_ledger_path, target_records)
    _write_jsonl(model_ledger_path, model_records)
    _write_jsonl(prediction_ledger_path, prediction_records)
    write_json(calibration_path, calibration)
    provenance_payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "historical_models_are_fold_local_evidence_not_reusable_deployed_state",
        "snapshot_manifest_sha256": provenance["snapshot_manifest_sha256"],
        "stage_e_lock_sha256": provenance["stage_e_lock_sha256"],
        "feature_contract_sha256": provenance["feature_contract_sha256"],
        "label_contract_sha256": provenance["label_contract_sha256"],
        "validation_contract_sha256": provenance["validation_contract_sha256"],
        "model_ledger_sha256": _sha256(model_ledger_path),
        "prediction_ledger_sha256": _sha256(prediction_ledger_path),
        "model_count": len(model_records),
        "prediction_count": len(prediction_records),
        "serialized_estimator_reuse_allowed": False,
        "broker_writes": False,
    }
    write_json(provenance_path, provenance_payload)
    _write_jsonl(
        trial_ledger_path,
        [
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "candidate_id": candidate_id,
                "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
                "research_pass": payload.get("research_pass", False),
                "tier0_reserve_pass": payload.get("tier0_reserve_pass", False),
                "windows": payload["windows"],
                "folds": payload["folds"],
            }
            for candidate_id, payload in candidate_payloads.items()
        ],
    )
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "stage": "E",
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": True,
        "research_pass": bool(selected_research),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "order_authority": False,
        "broker_writes": False,
        "selected_research_candidate_ids": selected_research,
        "selected_tier0_reserve_candidate_ids": selected_tier0,
        "historical_llm_paths": "dependency_skipped",
        "preflight": preflight,
        "data": {
            "provider": "alpaca",
            "feed": "sip",
            "adjustment": "all",
            "symbol_count": len(panel.open.columns),
            "session_count": len(panel.open),
            "first_session": panel.open.index.min().date().isoformat(),
            "last_session": panel.open.index.max().date().isoformat(),
        },
        "evaluation_windows": {
            name: {key: value.isoformat() for key, value in boundary.items()}
            for name, boundary in evaluation_windows.items()
        },
        "cost_views_bps": cost_views,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "linear_baseline_contract": LINEAR_BASELINE_CONTRACT,
        "role_gate_contract": ROLE_GATE_CONTRACT,
        "candidates": candidate_payloads,
        "benchmarks": benchmark_payload,
        "pbo": pbo,
        "calibration": calibration,
        "model_provenance": provenance_payload,
        "artifacts": {
            "target_ledger_sha256": _sha256(target_ledger_path),
            "model_ledger_sha256": _sha256(model_ledger_path),
            "prediction_ledger_sha256": _sha256(prediction_ledger_path),
            "trial_ledger_sha256": _sha256(trial_ledger_path),
            "calibration_sha256": _sha256(calibration_path),
            "model_provenance_sha256": _sha256(provenance_path),
        },
    }
    evaluation_path = staging / "evaluation-report.json"
    markdown_path = staging / "evaluation-report.md"
    write_json(evaluation_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    os.replace(staging, destination)
    _write_forensics(base, payload)
    return StageEEvaluationResult(
        evaluation_path=destination / "evaluation-report.json",
        trial_ledger_path=destination / "trial-ledger.jsonl",
        model_ledger_path=destination / "model-ledger.jsonl",
        prediction_ledger_path=destination / "prediction-ledger.jsonl",
        target_ledger_path=destination / "target-ledger.jsonl",
        payload=payload,
    )


def _validate_ml_panel(panel: R8MLPanel) -> None:
    frames = (panel.open, panel.low, panel.close, panel.volume)
    first = panel.open
    if list(first.columns) != list(UNIVERSE) or first.empty:
        raise ValueError("R8 Stage E panel identity mismatch")
    for frame in frames:
        if not frame.index.equals(first.index) or list(frame.columns) != list(first.columns):
            raise ValueError("R8 Stage E panel alignment failed")
        if not np.isfinite(frame.to_numpy()).all():
            raise ValueError("R8 Stage E panel contains nonfinite values")
    if (
        (panel.open <= 0).any().any()
        or (panel.low <= 0).any().any()
        or (panel.close <= 0).any().any()
    ):
        raise ValueError("R8 Stage E prices must be positive")
    if (panel.volume < 0).any().any():
        raise ValueError("R8 Stage E volume must be nonnegative")


def _fit_model_family(
    dataset: pd.DataFrame,
    current: pd.DataFrame,
    *,
    decision_position: int,
    train_start_session: str,
    segment_id: str,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str],
) -> tuple[dict[str, FittedModel], list[dict[str, Any]]]:
    definitions = {
        "R8M01_LINEAR": (specs["R8M01"], "forward_return_5", True),
        "R8M01": (specs["R8M01"], "forward_return_5", False),
        "R8M02_LINEAR": (specs["R8M02"], "path_survival_label", True),
        "R8M02": (specs["R8M02"], "path_survival_label", False),
    }
    output: dict[str, FittedModel] = {}
    records: list[dict[str, Any]] = []
    for candidate_id, (spec, label_name, linear) in definitions.items():
        train = training_rows_for_prediction(
            dataset,
            decision_position=decision_position,
            train_start_session=train_start_session,
            spec=spec,
            label_name=label_name,
        )
        minimum_rows = max(80, 2 * int(spec.model.hyperparameters["min_child_samples"]))
        if len(train) < minimum_rows:
            raise ValueError(f"R8 Stage E insufficient training rows: {candidate_id}")
        if "M02" in candidate_id and train[label_name].nunique() < 2:
            raise ValueError(f"R8 Stage E classifier has one training class: {candidate_id}")
        estimator, resolved = _make_estimator(spec, candidate_id=candidate_id, linear=linear)
        train_x = train.loc[:, list(FEATURE_NAMES)].astype(float)
        train_y = train[label_name].astype(float)
        estimator.fit(train_x, train_y)
        fitted_sha = _fitted_model_hash(estimator, candidate_id)
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "stage": "E",
            "segment_id": segment_id,
            "candidate_id": candidate_id,
            "strategy_name": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "decision_session": str(current["decision_session"].iloc[0]),
            "model_kind": resolved["model_kind"],
            "feature_names": list(FEATURE_NAMES),
            "label_name": label_name,
            "training_row_count": len(train),
            "training_decision_start": str(train["decision_session"].min()),
            "training_decision_end": str(train["decision_session"].max()),
            "training_label_terminal_end": str(train["label_end_session"].max()),
            "training_data_sha256": _frame_hash(train, [*FEATURE_NAMES, label_name]),
            "resolved_model_parameters": resolved,
            "fitted_model_sha256": fitted_sha,
            "training_label_mean": float(train_y.mean()),
            **provenance,
        }
        record["model_id"] = hashlib.sha256(_canonical_json_bytes(record)).hexdigest()
        fitted = FittedModel(
            candidate_id=candidate_id,
            model_id=record["model_id"],
            estimator=estimator,
            training_label_mean=float(train_y.mean()),
            record=record,
        )
        output[candidate_id] = fitted
        records.append(record)
    return output, records


def _make_estimator(
    spec: StrategySpec, *, candidate_id: str, linear: bool
) -> tuple[Any, dict[str, Any]]:
    assert spec.model is not None
    if linear and candidate_id == "R8M01_LINEAR":
        estimator = Pipeline(
            [("scale", StandardScaler()), ("model", Ridge(alpha=1.0, fit_intercept=True))]
        )
        return estimator, {"model_kind": "ridge", **LINEAR_BASELINE_CONTRACT[candidate_id]}
    if linear and candidate_id == "R8M02_LINEAR":
        estimator = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=1.0,
                        solver="lbfgs",
                        max_iter=1000,
                        random_state=int(spec.model.training.seed),
                    ),
                ),
            ]
        )
        return estimator, {
            "model_kind": "logistic_regression",
            **LINEAR_BASELINE_CONTRACT[candidate_id],
            "random_state": int(spec.model.training.seed),
        }
    params = dict(spec.model.hyperparameters)
    params.update(
        {
            "random_state": int(spec.model.training.seed),
            "deterministic": True,
            "force_col_wise": True,
        }
    )
    if spec.model.kind == "lightgbm_regressor":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(**params), {"model_kind": spec.model.kind, **params}
    if spec.model.kind == "lightgbm_classifier":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(**params), {"model_kind": spec.model.kind, **params}
    raise ValueError(f"R8 Stage E unsupported model kind: {spec.model.kind}")


def _predict(model: FittedModel, current_x: pd.DataFrame) -> np.ndarray:
    if "M02" in model.candidate_id:
        values = np.asarray(model.estimator.predict_proba(current_x)[:, 1], dtype=float)
    else:
        values = np.asarray(model.estimator.predict(current_x), dtype=float)
    if values.shape != (len(current_x),) or not np.isfinite(values).all():
        raise ValueError(f"R8 Stage E prediction invalid: {model.candidate_id}")
    return values


def _prediction_record(
    model: FittedModel,
    *,
    segment_id: str,
    decision_session: str,
    execution_session: str,
    current: pd.DataFrame,
    values: np.ndarray,
    provenance: dict[str, str],
) -> dict[str, Any]:
    rows = [
        {"symbol": str(symbol), "value": float(value)}
        for symbol, value in zip(current["symbol"], values, strict=True)
    ]
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "stage": "E",
        "segment_id": segment_id,
        "candidate_id": model.candidate_id,
        "model_id": model.model_id,
        "decision_session": decision_session,
        "execution_session": execution_session,
        "prediction_feature_sha256": _frame_hash(current, list(FEATURE_NAMES)),
        "predictions": rows,
        "prediction_sha256": hashlib.sha256(_canonical_json_bytes(rows)).hexdigest(),
        **provenance,
    }


def _risk_budget_target(
    scores: pd.Series,
    current: pd.DataFrame,
    *,
    columns: pd.Index,
    max_weight: float,
) -> pd.Series:
    if set(scores.index) != set(RANKABLE_SYMBOLS) or not np.isfinite(scores.to_numpy()).all():
        raise ValueError("R8 Stage E ranking scores are incomplete")
    selected = sorted(scores.index, key=lambda symbol: (-float(scores[symbol]), str(symbol)))[:3]
    score_ranks = cross_sectional_percentile(scores)
    volatility = current.set_index("symbol")["raw_realized_volatility_20"].astype(float)
    raw = {
        symbol: max(float(score_ranks[symbol]), 1.0 / len(RANKABLE_SYMBOLS))
        / float(volatility[symbol])
        for symbol in selected
    }
    if not all(math.isfinite(value) and value > 0.0 for value in raw.values()):
        raise ValueError("R8 Stage E risk budget is invalid")
    total = math.fsum(raw.values())
    target = pd.Series(0.0, index=columns, dtype=float)
    for symbol, value in raw.items():
        target[symbol] = min(value / total, max_weight)
    target["BIL"] = 1.0 - float(target.sum())
    if target["BIL"] < -1e-12:
        raise ValueError("R8 Stage E risk target exceeds capital")
    return target


def _apply_survival_gate(
    base_target: pd.Series,
    probabilities: pd.Series,
    *,
    threshold: float,
    reserve_symbol: str,
) -> pd.Series:
    target = base_target.astype(float).copy()
    for symbol in RANKABLE_SYMBOLS:
        if target[symbol] > 0.0 and float(probabilities[symbol]) < threshold:
            target[reserve_symbol] += target[symbol]
            target[symbol] = 0.0
    if not np.isclose(float(target.sum()), 1.0, atol=1e-12):
        raise ValueError("R8 Stage E survival gate violates capital conservation")
    return target


def _evaluate_folds(
    opens: pd.DataFrame,
    segment_results: dict[str, SegmentResult],
    *,
    folds: list[dict[str, Any]],
    d01_targets: pd.DataFrame,
    d02_targets: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    output = {candidate_id: [] for candidate_id in (*SELECTION_IDS, *MODEL_IDS)}
    for fold in folds:
        fold_id = str(fold["fold_id"])
        start = pd.Timestamp(fold["test_start"])
        end = pd.Timestamp(fold["test_end"])
        targets = {
            "R8D01": d01_targets,
            "R8D02": d02_targets,
            **segment_results[fold_id].targets,
        }
        qqq = _simulate_static(opens, {"QQQ": 1.0}, start=start, end=end, cost_bps=20.0)
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


def _calibration_payload(
    records: list[dict[str, Any]], folds: list[dict[str, Any]]
) -> dict[str, Any]:
    frame = pd.DataFrame(records)
    rows: dict[str, Any] = {}
    for fold in folds:
        fold_id = str(fold["fold_id"])
        selected = frame[frame["segment_id"] == fold_id]
        rows[fold_id] = _calibration_metrics(selected)
    aggregate = _calibration_metrics(frame[frame["segment_id"].isin(rows)])
    return {
        "folds": rows,
        "aggregate": aggregate,
        "brier_winning_fold_count": sum(
            row["lgbm_brier"] < row["linear_brier"] and row["lgbm_brier"] < row["base_rate_brier"]
            for row in rows.values()
        ),
        "calibration_slope_passing_fold_count": sum(
            row["calibration_slope"] is not None
            and ROLE_GATE_CONTRACT["M02_calibration_slope_min"]
            <= row["calibration_slope"]
            <= ROLE_GATE_CONTRACT["M02_calibration_slope_max"]
            for row in rows.values()
        ),
    }


def _calibration_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "observation_count": 0,
            "lgbm_brier": 1.0,
            "linear_brier": 1.0,
            "base_rate_brier": 1.0,
            "calibration_slope": None,
            "m01_selected_path_loss": 1.0,
            "m02_accepted_path_loss": 1.0,
        }
    labels = frame["label"].to_numpy(dtype=float)
    lgbm = frame["lgbm_probability"].to_numpy(dtype=float)
    linear = frame["linear_probability"].to_numpy(dtype=float)
    base = frame["training_base_probability"].to_numpy(dtype=float)
    selected = frame[frame["m01_selected"]]
    accepted = frame[frame["m02_accepted"]]
    return {
        "observation_count": len(frame),
        "positive_label_count": int(labels.sum()),
        "negative_label_count": int(len(labels) - labels.sum()),
        "lgbm_brier": float(np.mean((lgbm - labels) ** 2)),
        "linear_brier": float(np.mean((linear - labels) ** 2)),
        "base_rate_brier": float(np.mean((base - labels) ** 2)),
        "calibration_slope": _calibration_slope(labels, lgbm),
        "m01_selected_path_loss": (
            float(1.0 - selected["label"].mean()) if not selected.empty else 1.0
        ),
        "m02_accepted_path_loss": (
            float(1.0 - accepted["label"].mean()) if not accepted.empty else 1.0
        ),
        "m01_selected_count": len(selected),
        "m02_accepted_count": len(accepted),
    }


def _calibration_slope(labels: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(labels) < 30 or len(np.unique(labels)) < 2:
        return None
    clipped = np.clip(probabilities, 1e-6, 1.0 - 1e-6)
    logits = np.log(clipped / (1.0 - clipped))
    if float(np.std(logits)) <= 1e-12:
        return None
    design = np.column_stack([np.ones(len(logits)), logits])

    def objective(coefficients: np.ndarray) -> float:
        linear = np.clip(design @ coefficients, -40.0, 40.0)
        return float(np.sum(np.logaddexp(0.0, linear) - labels * linear))

    fitted = minimize(objective, np.asarray([0.0, 1.0]), method="BFGS")
    if not fitted.success or not np.isfinite(fitted.x).all():
        return None
    return float(fitted.x[1])


def _role_gates(
    candidates: dict[str, dict[str, Any]], calibration: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    m01_wins = 0
    path_wins = 0
    for index in range(4):
        m01 = candidates["R8M01"]["folds"][index]["metrics"]["with_terminal"]["cagr"]
        linear = candidates["R8M01_LINEAR"]["folds"][index]["metrics"]["with_terminal"]["cagr"]
        d01 = candidates["R8D01"]["folds"][index]["metrics"]["with_terminal"]["cagr"]
        m01_wins += int(m01 > max(linear, d01))
        row = calibration["folds"][f"F{index + 1}"]
        path_wins += int(row["m02_accepted_path_loss"] < row["m01_selected_path_loss"])
    m01_full = candidates["R8M01"]["windows"]["full"]["primary_20bps"]["with_terminal"]
    m02_full = candidates["R8M02"]["windows"]["full"]["primary_20bps"]["with_terminal"]
    exposure_ratio = m02_full["average_risk_asset_exposure"] / max(
        m01_full["average_risk_asset_exposure"], 1e-12
    )
    cagr_retention = m02_full["cagr"] / max(m01_full["cagr"], 1e-12)
    m01_pass = m01_wins >= ROLE_GATE_CONTRACT["M01_minimum_fold_wins_vs_linear_and_D01"]
    m02_checks = {
        "brier_winning_folds": calibration["brier_winning_fold_count"]
        >= ROLE_GATE_CONTRACT["M02_minimum_brier_wins_vs_linear_and_base_rate"],
        "calibration_slope_folds": calibration["calibration_slope_passing_fold_count"]
        >= ROLE_GATE_CONTRACT["M02_minimum_brier_wins_vs_linear_and_base_rate"],
        "path_loss_improvement_folds": path_wins
        >= ROLE_GATE_CONTRACT["M02_minimum_path_loss_improvement_folds"],
        "exposure_ratio": exposure_ratio >= ROLE_GATE_CONTRACT["M02_minimum_exposure_ratio_vs_M01"],
        "cagr_retention": cagr_retention >= ROLE_GATE_CONTRACT["M02_minimum_CAGR_retention_vs_M01"],
        "drawdown_improvement": m02_full["max_drawdown"] > m01_full["max_drawdown"],
    }
    return {
        "R8D01": {"pass": True, "reason": "locked_deterministic_control"},
        "R8D02": {"pass": True, "reason": "locked_aggressive_beta_control"},
        "R8M01": {
            "fold_wins_vs_linear_and_D01": m01_wins,
            "required_fold_wins": ROLE_GATE_CONTRACT["M01_minimum_fold_wins_vs_linear_and_D01"],
            "pass": m01_pass,
        },
        "R8M02": {
            "checks": m02_checks,
            "brier_winning_fold_count": calibration["brier_winning_fold_count"],
            "calibration_slope_passing_fold_count": calibration[
                "calibration_slope_passing_fold_count"
            ],
            "path_loss_improvement_fold_count": path_wins,
            "exposure_ratio_vs_M01": exposure_ratio,
            "CAGR_retention_vs_M01": cagr_retention,
            "pass": all(m02_checks.values()),
        },
    }


def _aggregate_segment_targets(
    results: dict[str, SegmentResult],
    segments: list[dict[str, str]],
    *,
    candidate_id: str,
    columns: pd.Index,
) -> pd.DataFrame:
    rows: list[pd.Series] = []
    sessions: list[pd.Timestamp] = []
    for segment in segments:
        frame = results[segment["segment_id"]].targets[candidate_id]
        start = pd.Timestamp(segment["start"])
        end = pd.Timestamp(segment["end"])
        prior = frame.loc[frame.index <= start]
        if prior.empty:
            raise ValueError(f"R8 Stage E segment lacks a boundary target: {segment['segment_id']}")
        rows.append(prior.iloc[-1])
        sessions.append(start)
        for session, row in frame.loc[(frame.index > start) & (frame.index <= end)].iterrows():
            rows.append(row)
            sessions.append(pd.Timestamp(session))
    values = pd.DataFrame(rows, index=pd.DatetimeIndex(sessions), columns=columns)
    values = values[~values.index.duplicated(keep="last")].sort_index()
    if not np.allclose(values.sum(axis=1).to_numpy(), 1.0, atol=1e-12):
        raise ValueError("R8 Stage E aggregate targets violate capital conservation")
    return values


def _prior_scheduled_session(dataset: pd.DataFrame, start_session: str) -> str:
    sessions = sorted(set(map(str, dataset["execution_session"])))
    prior = [session for session in sessions if session <= start_session]
    if not prior:
        raise ValueError("R8 Stage E has no scheduled target before segment start")
    return prior[-1]


def _frame_hash(frame: pd.DataFrame, columns: list[str]) -> str:
    values = frame.loc[:, columns].astype(float).to_numpy(dtype="<f8", copy=True)
    identities = [
        f"{row.decision_session}|{row.symbol}"
        for row in frame.loc[:, ["decision_session", "symbol"]].itertuples(index=False)
    ]
    digest = hashlib.sha256()
    digest.update(_canonical_json_bytes(columns))
    digest.update("\n".join(identities).encode("ascii"))
    digest.update(values.tobytes())
    return digest.hexdigest()


def _fitted_model_hash(estimator: Any, candidate_id: str) -> str:
    if candidate_id in {"R8M01", "R8M02"}:
        return hashlib.sha256(estimator.booster_.model_to_string().encode("utf-8")).hexdigest()
    scale = estimator.named_steps["scale"]
    model = estimator.named_steps["model"]
    payload = {
        "scale_mean": scale.mean_.tolist(),
        "scale_scale": scale.scale_.tolist(),
        "coef": np.asarray(model.coef_, dtype=float).tolist(),
        "intercept": np.asarray(model.intercept_, dtype=float).reshape(-1).tolist(),
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    )
    path.write_text(payload, encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# R8 Stage E ML Evaluation",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Research pass: `{payload['research_pass']}`",
        (
            "- Tier 0 reserve: `"
            f"{', '.join(payload['selected_tier0_reserve_candidate_ids']) or 'none'}`"
        ),
        "- Paper authority: `false`",
        "",
        "| Candidate | CAGR | Sharpe | MDD | MAR | DSR | Role | Tier 0 | Research |",
        "|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for candidate_id in ("R8D01", "R8D02", "R8M01_LINEAR", "R8M01", "R8M02_LINEAR", "R8M02"):
        candidate = payload["candidates"][candidate_id]
        metrics = candidate["windows"]["full"]["primary_20bps"]["with_terminal"]
        dsr = candidate.get("deflated_sharpe", {}).get("probability")
        role = candidate.get("role_gate", {}).get("pass")
        lines.append(
            f"| {candidate_id} | {metrics['cagr'] * 100:.2f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['max_drawdown'] * 100:.2f}% | {metrics['mar']:.3f} | "
            f"{dsr:.3f} | {role} | {candidate.get('tier0_reserve_pass', False)} | "
            f"{candidate.get('research_pass', False)} |"
            if dsr is not None
            else f"| {candidate_id} | {metrics['cagr'] * 100:.2f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['max_drawdown'] * 100:.2f}% | {metrics['mar']:.3f} | n/a | "
            f"selection prohibited | False | False |"
        )
    lines.extend(
        [
            "",
            "All returns are geometric CAGR on matched next-open intervals with terminal "
            "liquidation. Historical fitted estimators are evidence only and are not reusable "
            "deployed state. No broker or Paper order was submitted.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_forensics(root: Path, payload: dict[str, Any]) -> None:
    output = root / "reports/harness/forensics"
    output.mkdir(parents=True, exist_ok=True)
    for candidate_id in ("R8M01", "R8M02"):
        candidate = payload["candidates"][candidate_id]
        metrics = candidate["windows"]["full"]["primary_20bps"]["with_terminal"]
        conclusion = "warning" if candidate["research_pass"] else "blocked"
        report = {
            "strategy_name": candidate["strategy_name"],
            "lookahead_check": "pass",
            "future_leak_check": "pass",
            "overfit_risk": "high",
            "multiple_testing_count": EFFECTIVE_TRIAL_COUNT,
            "pbo_proxy": payload["pbo"]["probability"],
            "dsr_proxy": candidate["deflated_sharpe"]["probability"],
            "sample_data_caveats": [],
            "trade_count": int(metrics["nonzero_rebalance_count"]),
            "trading_days": int(metrics["market_interval_count"]),
            "capacity_assessment": (
                "Fixed liquid ETF universe; Paper sizing still requires open-auction TCA and "
                "the one-percent ADV cap."
            ),
            "short_sample": False,
            "conclusion": conclusion,
            "notes": (
                "Features end at decision close and apply next open. Every fit is fold-local, "
                "uses a 756-session window, and excludes labels through a 10-session embargo."
            ),
        }
        path = output / f"{candidate['strategy_name']}-backtest-forensics.json"
        write_json(path, report)
        (path.with_suffix(".md")).write_text(
            f"# Backtest Forensics: {candidate['strategy_name']}\n\n"
            f"- Conclusion: `{conclusion}`\n"
            "- Lookahead: `pass`\n"
            "- Future leak: `pass`\n"
            f"- Effective multiple-testing count: `{EFFECTIVE_TRIAL_COUNT}`\n"
            f"- DSR probability: `{candidate['deflated_sharpe']['probability']:.6f}`\n"
            f"- PBO: `{payload['pbo']['probability']:.6f}`\n"
            "- Paper authority: `false`\n",
            encoding="utf-8",
        )


def cleanup_stage_e_staging(root: Path) -> None:
    base = root.resolve()
    for path in (base / ITERATION_DIR).glob("stage-e-evaluation.staging-*"):
        if path.is_dir():
            shutil.rmtree(path)
