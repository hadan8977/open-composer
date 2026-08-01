from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.multiasset_forward_multimodal_r5 import (
    CORE_FEATURES,
    FORMULA_FEATURES,
    RANKABLE_SYMBOLS,
    RESERVE_SYMBOL,
    TOP_N,
    ExactSimulationResult,
    PanelData,
    _benchmark_family_exact,
    _canonical_json_bytes,
    _expected_llm_contribution_bootstrap_contract,
    _formula_placebo_evidence,
    _frame_sha256,
    _json_ready,
    _make_estimator,
    _target_difference_count,
    _target_from_symbols,
    _top_symbols,
    _top_symbols_from_series,
    build_cscv_partitions,
    build_monthly_feature_dataset,
    build_point_in_time_features,
    canonical_target_bytes,
    canonical_target_hash,
    paired_transfer_sharpe_bootstrap,
    simulate_exact_target_portfolio,
    training_rows_for_prediction,
)
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_multiasset_forward_multimodal_r6"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
DATA_DIR = Path("data/research/alpaca_multiasset_forward_mm_r6")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_multiasset_forward_mm_r6_{suffix}.yaml")
    for candidate_id, suffix in {
        "R6D01": "d01",
        "R6D02": "d02",
        "R6M01": "m01",
        "R6M02": "m02",
        "R6L01": "l01",
        "R6C01": "c01",
        "R6F01": "f01",
        "R6P01": "p01",
    }.items()
}
PROMOTION_ELIGIBLE = frozenset({"R6D01", "R6D02", "R6M01", "R6M02", "R6L01", "R6C01"})
SELECTION_PROHIBITED = frozenset({"R6F01", "R6P01"})
CORE_PREDICTORS = tuple(CORE_FEATURES)
FORMULA_PREDICTORS = tuple(FORMULA_FEATURES)
PREDICTOR_CONTRACT = {
    "R6M01": CORE_PREDICTORS,
    "R6M02": CORE_PREDICTORS,
    "R6C01": (*CORE_PREDICTORS, *FORMULA_PREDICTORS),
    "R6P01": (*CORE_PREDICTORS, *(f"placebo_{name}" for name in FORMULA_PREDICTORS)),
}
DECLARED_FEATURE_CONTRACT = {
    **PREDICTOR_CONTRACT,
    "R6P01": (*CORE_PREDICTORS, *FORMULA_PREDICTORS),
}
LABEL_CONTRACT = {
    "R6M01": "forward_return_21",
    "R6M02": "path_survival_label",
    "R6C01": "forward_return_21",
    "R6P01": "forward_return_21",
}
FORBIDDEN_PREDICTORS = frozenset(
    {
        "decision_position",
        "decision_session",
        "execution_position",
        "execution_session",
        "label_end_position",
        "label_end_session",
        "symbol",
        "forward_return_21",
        "path_survival_label",
        "max_open_path_drawdown",
    }
)
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 20.0
SEVERE_COST_BPS = 35.0


@dataclass(frozen=True)
class R6FreezeResult:
    preregistration_lock_path: Path
    lock_anchor_path: Path
    lock_anchor_sha256: str


@dataclass(frozen=True)
class R6EvaluationResult:
    evaluation_path: Path
    trial_ledger_path: Path
    target_ledger_path: Path
    receipt_path: Path
    payload: dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    relative = resolved.relative_to(root.resolve()).as_posix()
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"locked input must be a regular file: {relative}")
    return {"path": relative, "sha256": _sha256(path), "size_bytes": path.stat().st_size}


def _publication_binding(
    path: Path,
    *,
    root: Path,
    staging_dir: Path,
    destination_dir: Path,
) -> dict[str, Any]:
    binding = _binding(path, root)
    relative = path.resolve().relative_to(staging_dir.resolve())
    binding["path"] = (destination_dir / relative).relative_to(root.resolve()).as_posix()
    return binding


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_ready(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(_json_ready(row), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    )
    path.write_text(content, encoding="utf-8")


def _validate_specs(specs: dict[str, StrategySpec]) -> None:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R6 requires exactly the eight preregistered StrategySpecs")
    expected_universe = {RESERVE_SYMBOL, *RANKABLE_SYMBOLS}
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        portfolio = spec.portfolio
        checks = {
            "candidate_id": notes.get("candidate_id") == candidate_id,
            "timeframe": spec.timeframe == "daily",
            "long_only": spec.position_direction == "long_only",
            "universe": set(spec.universe) == expected_universe,
            "portfolio_mode": portfolio.mode == "cross_sectional_momentum",
            "execution_profile": (
                portfolio.cross_sectional_execution_profile == "monthly_equal_weight_bil_reserve"
            ),
            "entry_only": portfolio.position_weight_enforcement == "entry_only",
            "month_end": portfolio.rebalance_schedule == "calendar_month_end",
            "equal_weight": portfolio.weighting == "equal_weight",
            "reserve": portfolio.reserve_symbol == RESERVE_SYMBOL,
            "top_n": portfolio.max_symbols_per_day == TOP_N,
            "manual_signal": spec.execution.mode == "manual_signal",
            "broker_none": spec.execution.broker == "none",
            "decision_close": spec.execution.signal_on == "bar_close",
            "next_open": spec.execution.fill_assumption == "next_bar_open",
            "primary_cost": spec.costs.slippage_bps == PRIMARY_COST_BPS,
            "snapshot": (
                spec.data_assumptions is not None
                and spec.data_assumptions.snapshot_manifest_path
                == (DATA_DIR / "snapshot-manifest.json").as_posix()
            ),
            "feature_basis": notes.get("feature_price_basis")
            == "immutable_alpaca_all_adjusted_ohlcv",
            "execution_basis": notes.get("execution_price_basis") == "raw_unadjusted_ohlcv",
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(f"R6 StrategySpec contract mismatch for {candidate_id}: {failed}")

    paired = [specs[candidate_id].model for candidate_id in ("R6M01", "R6C01", "R6P01")]
    if any(model is None for model in paired):
        raise ValueError("R6 paired return-ranker model contract is missing")
    normalized = []
    for model in paired:
        assert model is not None
        payload = model.model_dump(mode="json")
        payload.pop("features", None)
        normalized.append(_canonical_json_bytes(payload))
        if model.training.seed != 4101:
            raise ValueError("R6 paired return-ranker seed must remain 4101")
    if len(set(normalized)) != 1:
        raise ValueError("R6M01, R6C01 and R6P01 models must differ only by features")
    if (
        specs["R6M01"].model is None
        or specs["R6F01"].model is None
        or specs["R6M01"].model.model_dump(mode="json")
        != specs["R6F01"].model.model_dump(mode="json")
    ):
        raise ValueError("R6F01 must exactly declare the R6M01 model")
    m02 = specs["R6M02"].model
    if m02 is None or m02.selection.method != "threshold" or m02.selection.threshold != 0.55:
        raise ValueError("R6M02 must retain the frozen 0.55 threshold")
    for candidate_id, expected in DECLARED_FEATURE_CONTRACT.items():
        model = specs[candidate_id].model
        if model is None or tuple(model.features) != expected:
            raise ValueError(f"R6 model feature contract mismatch: {candidate_id}")


def freeze_multiasset_forward_multimodal_r6(root: Path) -> R6FreezeResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    if (output / "evaluation-run").exists() or any(output.glob("evaluation-run.staging-*")):
        raise ValueError("R6 evaluation state already exists")
    lock_dir = output / "lock-set"
    if lock_dir.exists():
        raise ValueError("R6 preregistration was already frozen")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if validation.status != "ok":
        raise ValueError("R6 pre-backtest dossier is blocked: " + ", ".join(validation.blocked))
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    _validate_specs(specs)

    iteration_inputs = sorted(
        path
        for path in output.iterdir()
        if path.is_file() and path.name not in {"evaluation-report.json", "evaluation-report.md"}
    )
    implementation_paths = [
        Path("open_composer/research/multiasset_forward_multimodal_r6.py"),
        Path("open_composer/research/multiasset_forward_multimodal_r5.py"),
        Path("open_composer/adapters/data/alpaca_snapshot.py"),
        Path("open_composer/models/strategy_spec.py"),
        Path("open_composer/strategy_versions.py"),
    ]
    manifest_path = base / DATA_DIR / "snapshot-manifest.json"
    data_contract = _load_json(output / "data-contract.json")
    if _sha256(manifest_path) != data_contract.get("snapshot_manifest_sha256"):
        raise ValueError("R6 snapshot manifest differs from the data contract")
    verify_alpaca_contract_snapshot(base, manifest_path)

    lock = {
        "schema_version": 1,
        "lock_contract": "multiasset_forward_multimodal_r6_preregistration_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "behavior_and_inputs_locked_before_first_r6_price_calculation",
        "iteration_artifacts": [_binding(path, base) for path in iteration_inputs],
        "specs": [
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "implementation": [_binding(base / path, base) for path in implementation_paths],
        "snapshot_manifest": _binding(manifest_path, base),
        "one_shot": True,
        "forward_count_at_lock": 0,
        "broker_writes": False,
    }
    lock_dir.mkdir(parents=True, exist_ok=False)
    lock_path = lock_dir / "preregistration-lock.json"
    _write_json(lock_path, lock)
    lock_sha = _sha256(lock_path)
    anchor_path = lock_dir / "lock-anchor.json"
    _write_json(
        anchor_path,
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "preregistration_lock_path": lock_path.relative_to(base).as_posix(),
            "preregistration_lock_sha256": lock_sha,
        },
    )
    return R6FreezeResult(lock_path, anchor_path, _sha256(anchor_path))


def _verify_lock(root: Path, expected_lock_anchor_sha256: str) -> dict[str, Any]:
    output = root / ITERATION_DIR
    anchor_path = output / "lock-set/lock-anchor.json"
    if _sha256(anchor_path) != expected_lock_anchor_sha256:
        raise ValueError("R6 operator lock anchor SHA-256 mismatch")
    anchor = _load_json(anchor_path)
    lock_path = root / str(anchor.get("preregistration_lock_path") or "")
    if _sha256(lock_path) != anchor.get("preregistration_lock_sha256"):
        raise ValueError("R6 preregistration lock SHA-256 mismatch")
    lock = _load_json(lock_path)
    if lock.get("iter_id") != ITER_ID or lock.get("one_shot") is not True:
        raise ValueError("R6 preregistration lock identity is invalid")
    for group in ("iteration_artifacts", "specs", "implementation"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R6 lock group is missing: {group}")
        for row in rows:
            path = root / str(row.get("path") or "")
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"R6 locked file is missing: {path}")
            if _sha256(path) != row.get("sha256") or path.stat().st_size != row.get("size_bytes"):
                raise ValueError(f"R6 locked file changed: {path}")
    snapshot = lock.get("snapshot_manifest")
    if not isinstance(snapshot, dict):
        raise ValueError("R6 snapshot lock binding is missing")
    manifest_path = root / str(snapshot.get("path") or "")
    if _sha256(manifest_path) != snapshot.get("sha256"):
        raise ValueError("R6 locked snapshot manifest changed")
    return lock


def load_r6_panels(
    root: Path,
    manifest_path: Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, PanelData]:
    raw_manifest = manifest_path.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != expected_manifest_sha256:
        raise AlpacaDataError("R6 snapshot manifest hash mismatch")
    manifest = json.loads(raw_manifest)
    verified = verify_alpaca_contract_snapshot(root, manifest_path)
    if _canonical_json_bytes(verified) != _canonical_json_bytes(manifest):
        raise AlpacaDataError("R6 snapshot manifest changed during verification")
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 56:
        raise AlpacaDataError("R6 snapshot must contain 14 symbols by four adjustments")

    expected_symbols = sorted([*RANKABLE_SYMBOLS, RESERVE_SYMBOL])
    panels: dict[str, PanelData] = {}
    shared_sessions: pd.DatetimeIndex | None = None
    for adjustment in ("all", "raw"):
        selected = [item for item in items if item.get("adjustment") == adjustment]
        if len(selected) != 14 or sorted(str(item.get("symbol")) for item in selected) != (
            expected_symbols
        ):
            raise AlpacaDataError(f"R6 {adjustment} item set is incomplete")
        fields: dict[str, dict[str, pd.Series]] = {
            name: {} for name in ("open", "high", "low", "close", "volume")
        }
        adjustment_sessions: pd.DatetimeIndex | None = None
        for item in selected:
            if (
                item.get("timeframe") != "daily"
                or item.get("feed") != "sip"
                or item.get("session_scope") != "regular"
            ):
                raise AlpacaDataError(f"R6 {adjustment} item identity mismatch")
            symbol = str(item["symbol"])
            path = manifest_path.parent / str(item.get("output_path") or "")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != item.get("output_sha256"):
                raise AlpacaDataError(f"R6 CSV hash mismatch: {adjustment}:{symbol}")
            frame = pd.read_csv(io.BytesIO(payload))
            timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
            sessions = pd.DatetimeIndex(
                timestamps.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
            )
            if sessions.has_duplicates or not sessions.is_monotonic_increasing:
                raise AlpacaDataError(f"R6 sessions invalid: {adjustment}:{symbol}")
            complete = item.get("quality", {}).get("complete_sessions")
            if not isinstance(complete, list) or [
                session.date().isoformat() for session in sessions
            ] != (list(map(str, complete))):
                raise AlpacaDataError(
                    f"R6 complete-session evidence mismatch: {adjustment}:{symbol}"
                )
            if adjustment_sessions is None:
                adjustment_sessions = sessions
            elif not adjustment_sessions.equals(sessions):
                raise AlpacaDataError(f"R6 {adjustment} symbol sessions differ")
            for field in fields:
                fields[field][symbol] = pd.Series(
                    pd.to_numeric(frame[field], errors="raise").to_numpy(dtype=float),
                    index=sessions,
                )
        assert adjustment_sessions is not None
        if shared_sessions is None:
            shared_sessions = adjustment_sessions
        elif not shared_sessions.equals(adjustment_sessions):
            raise AlpacaDataError("R6 raw and all-adjusted sessions differ")
        frames = {name: pd.DataFrame(values).sort_index(axis=1) for name, values in fields.items()}
        for field, frame in frames.items():
            values = frame.to_numpy(dtype=float)
            if list(frame.columns) != expected_symbols or not np.isfinite(values).all():
                raise AlpacaDataError(f"R6 {adjustment} {field} panel is incomplete")
            if field != "volume" and (values <= 0.0).any():
                raise AlpacaDataError(f"R6 {adjustment} {field} panel is nonpositive")
            if field == "volume" and (values < 0.0).any():
                raise AlpacaDataError(f"R6 {adjustment} volume panel is negative")
        panels[adjustment] = PanelData(
            open=frames["open"],
            high=frames["high"],
            low=frames["low"],
            close=frames["close"],
            volume=frames["volume"],
            manifest=manifest,
        )
    return panels


def _predictor_frame(
    frame: pd.DataFrame,
    *,
    candidate_id: str,
    feature_names: tuple[str, ...],
    label_name: str,
) -> pd.DataFrame:
    if PREDICTOR_CONTRACT.get(candidate_id) != feature_names:
        raise ValueError(f"R6 predictor contract mismatch: {candidate_id}")
    if LABEL_CONTRACT.get(candidate_id) != label_name:
        raise ValueError(f"R6 label contract mismatch: {candidate_id}")
    if len(feature_names) != len(set(feature_names)) or set(feature_names) & FORBIDDEN_PREDICTORS:
        raise ValueError(f"R6 forbidden predictor: {candidate_id}")
    missing = sorted(set(feature_names) - set(frame.columns))
    if missing:
        raise ValueError(f"R6 predictor columns missing for {candidate_id}: {missing}")
    return frame.loc[:, list(feature_names)].copy()


def _fit_predict_for_point(
    spec: StrategySpec,
    dataset: pd.DataFrame,
    current: pd.DataFrame,
    *,
    decision_position: int,
    train_start_session: str,
    feature_names: tuple[str, ...],
    label_name: str,
    segment_id: str,
    provenance: dict[str, str],
) -> tuple[np.ndarray | None, dict[str, Any]]:
    if spec.model is None:
        raise ValueError(f"R6 model config missing: {spec.name}")
    candidate_id = str(spec.notes.model_dump(mode="json").get("candidate_id") or "")
    train = training_rows_for_prediction(
        dataset,
        decision_position=decision_position,
        train_start_session=train_start_session,
        feature_names=feature_names,
        label_name=label_name,
    )
    train_x = _predictor_frame(
        train,
        candidate_id=candidate_id,
        feature_names=feature_names,
        label_name=label_name,
    )
    current_x = _predictor_frame(
        current,
        candidate_id=candidate_id,
        feature_names=feature_names,
        label_name=label_name,
    )
    decision_session = str(current["decision_session"].iloc[0])
    minimum_rows = max(80, 2 * int(spec.model.hyperparameters.get("min_child_samples", 1)))
    failure: str | None = None
    if len(train) < minimum_rows:
        failure = "insufficient_training_rows"
    elif spec.model.kind == "lightgbm_classifier" and train[label_name].nunique() < 2:
        failure = "single_class_training_labels"
    if current_x.replace([np.inf, -np.inf], np.nan).isna().any().any():
        failure = "nonfinite_prediction_features"

    model = _make_estimator(spec)
    prediction: np.ndarray | None = None
    fitted_sha: str | None = None
    if failure is None:
        try:
            model.fit(train_x, train[label_name])
            prediction = (
                np.asarray(model.predict_proba(current_x)[:, 1], dtype=float)
                if spec.model.kind == "lightgbm_classifier"
                else np.asarray(model.predict(current_x), dtype=float)
            )
            if prediction.shape != (len(current),) or not np.isfinite(prediction).all():
                raise ValueError("prediction is nonfinite or misaligned")
            fitted_sha = hashlib.sha256(
                model.booster_.model_to_string().encode("utf-8")
            ).hexdigest()
        except Exception as exc:
            failure = f"model_fit_or_prediction_failed:{type(exc).__name__}:{exc}"
            prediction = None
    record = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "segment_id": segment_id,
        "candidate_id": candidate_id,
        "strategy_name": spec.name,
        "spec_hash": strategy_content_hash(spec),
        "decision_session": decision_session,
        "model_kind": spec.model.kind,
        "feature_names": list(feature_names),
        "label_name": label_name,
        "training_row_count": len(train),
        "training_decision_start": str(train["decision_session"].min())
        if not train.empty
        else None,
        "training_decision_end": str(train["decision_session"].max()) if not train.empty else None,
        "training_label_terminal_end": (
            str(train["label_end_session"].max()) if not train.empty else None
        ),
        "training_data_sha256": _frame_sha256(train, [*feature_names, label_name]),
        "prediction_feature_sha256": _frame_sha256(current_x, list(feature_names)),
        "data_manifest_sha256": provenance["data_manifest_sha256"],
        "feature_contract_sha256": provenance["feature_contract_sha256"],
        "label_contract_sha256": provenance["label_contract_sha256"],
        "prompt_hash": provenance["prompt_hash"],
        "training_label_mean": float(train[label_name].mean()) if not train.empty else None,
        "status": "fit_complete" if prediction is not None else "fallback_applied",
        "failure_reason": failure,
        "fitted_model_sha256": fitted_sha,
        "predictions": (
            [
                {"symbol": str(symbol), "value": float(value)}
                for symbol, value in zip(current["symbol"], prediction, strict=True)
            ]
            if prediction is not None
            else []
        ),
    }
    record["model_id"] = hashlib.sha256(_canonical_json_bytes(record)).hexdigest()
    return prediction, record


def build_candidate_targets_for_segment(
    dataset: pd.DataFrame,
    *,
    segment_id: str,
    execution_start: str,
    execution_end: str,
    train_start_session: str,
    columns: pd.Index,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str],
) -> tuple[
    dict[str, pd.DataFrame],
    list[dict[str, Any]],
    list[dict[str, Any]],
    pd.DataFrame,
]:
    _validate_specs(specs)
    points = (
        dataset[
            (dataset["execution_session"] >= execution_start)
            & (dataset["execution_session"] <= execution_end)
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
        raise ValueError(f"R6 segment has no prediction points: {segment_id}")
    targets: dict[str, list[pd.Series]] = {candidate_id: [] for candidate_id in SPEC_PATHS}
    target_index: list[pd.Timestamp] = []
    target_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []

    for point in points.to_dict(orient="records"):
        decision_position = int(point["decision_position"])
        decision_session = str(point["decision_session"])
        execution_session = str(point["execution_session"])
        current = dataset[dataset["decision_position"] == decision_position].sort_values("symbol")
        if set(current["symbol"]) != set(RANKABLE_SYMBOLS):
            raise ValueError(f"R6 rankable symbol coverage failed: {decision_session}")

        d01_symbols = _top_symbols(current, "raw_mom_252_skip21", TOP_N)
        d01 = _target_from_symbols(d01_symbols, columns)
        eligible_d02 = current[
            np.isfinite(current["raw_mom_126_skip21"])
            & np.isfinite(current["raw_trend_gap_252"])
            & (current["raw_trend_gap_252"] > 0.0)
        ]
        d02_symbols = _top_symbols(eligible_d02, "raw_mom_126_skip21", TOP_N)
        if len(d02_symbols) == TOP_N:
            d02 = _target_from_symbols(d02_symbols, columns)
            selected_d02 = d02_symbols
        else:
            d02 = d01.copy()
            selected_d02 = d01_symbols

        formula_values = current[list(FORMULA_FEATURES)].astype(float)
        formula_score = formula_values.mean(axis=1)
        if np.isfinite(formula_values.to_numpy()).all() and formula_score.nunique() > 1:
            l01_symbols = _top_symbols(
                current.assign(_formula_score=formula_score), "_formula_score"
            )
            l01 = _target_from_symbols(l01_symbols, columns)
            l01_fallback = None
        else:
            l01_symbols = d01_symbols
            l01 = d01.copy()
            l01_fallback = "nonfinite_or_constant_formula_composite"

        m01_prediction, m01_record = _fit_predict_for_point(
            specs["R6M01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=PREDICTOR_CONTRACT["R6M01"],
            label_name=LABEL_CONTRACT["R6M01"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(m01_record)
        if m01_prediction is None:
            m01_scores = pd.Series(
                current["raw_mom_252_skip21"].to_numpy(dtype=float),
                index=current["symbol"],
            )
            m01_symbols = d01_symbols
            m01 = d01.copy()
            m01_fallback = str(m01_record["failure_reason"])
        else:
            m01_scores = pd.Series(m01_prediction, index=current["symbol"], dtype=float)
            m01_symbols = _top_symbols_from_series(m01_scores)
            m01 = _target_from_symbols(m01_symbols, columns)
            m01_fallback = None

        c01_prediction, c01_record = _fit_predict_for_point(
            specs["R6C01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=PREDICTOR_CONTRACT["R6C01"],
            label_name=LABEL_CONTRACT["R6C01"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(c01_record)
        if c01_prediction is None:
            c01_symbols = m01_symbols
            c01 = m01.copy()
            c01_fallback = str(c01_record["failure_reason"])
        else:
            c01_symbols = _top_symbols_from_series(
                pd.Series(c01_prediction, index=current["symbol"], dtype=float)
            )
            c01 = _target_from_symbols(c01_symbols, columns)
            c01_fallback = None

        p01_prediction, p01_record = _fit_predict_for_point(
            specs["R6P01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=PREDICTOR_CONTRACT["R6P01"],
            label_name=LABEL_CONTRACT["R6P01"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(p01_record)
        if p01_prediction is None:
            p01_symbols = m01_symbols
            p01 = m01.copy()
            p01_fallback = str(p01_record["failure_reason"])
        else:
            p01_symbols = _top_symbols_from_series(
                pd.Series(p01_prediction, index=current["symbol"], dtype=float)
            )
            p01 = _target_from_symbols(p01_symbols, columns)
            p01_fallback = None

        m02_prediction, m02_record = _fit_predict_for_point(
            specs["R6M02"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=PREDICTOR_CONTRACT["R6M02"],
            label_name=LABEL_CONTRACT["R6M02"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(m02_record)
        if m02_prediction is None or m01_prediction is None:
            m02_symbols = m01_symbols
            m02 = m01.copy()
            m02_fallback = (
                "upstream_R6M01_fallback"
                if m01_prediction is None
                else str(m02_record["failure_reason"])
            )
        else:
            survival = pd.Series(m02_prediction, index=current["symbol"], dtype=float)
            ranked = sorted(
                current["symbol"], key=lambda symbol: (-float(m01_scores[symbol]), str(symbol))
            )
            threshold = specs["R6M02"].model.selection.threshold
            assert threshold is not None
            accepted = [symbol for symbol in ranked if float(survival[symbol]) >= threshold][:TOP_N]
            if len(accepted) < TOP_N:
                m02_symbols = m01_symbols
                m02 = m01.copy()
                m02_fallback = "fewer_than_three_survival_eligible_symbols"
            else:
                m02_symbols = list(map(str, accepted))
                m02 = _target_from_symbols(m02_symbols, columns)
                m02_fallback = None
            base_probability = float(m02_record["training_label_mean"])
            for row, probability in zip(
                current.to_dict(orient="records"), m02_prediction, strict=True
            ):
                if row["label_end_session"] is not None and row["label_end_session"] <= (
                    execution_end
                ):
                    calibration_rows.append(
                        {
                            "segment_id": segment_id,
                            "decision_session": decision_session,
                            "execution_session": execution_session,
                            "symbol": str(row["symbol"]),
                            "label": int(row["path_survival_label"]),
                            "probability": float(probability),
                            "training_base_probability": base_probability,
                            "threshold_accepted": bool(float(probability) >= threshold),
                        }
                    )

        candidate_rows = {
            "R6D01": (d01, d01_symbols, None),
            "R6D02": (d02, selected_d02, None),
            "R6M01": (m01, m01_symbols, m01_fallback),
            "R6M02": (m02, m02_symbols, m02_fallback),
            "R6L01": (l01, l01_symbols, l01_fallback),
            "R6C01": (c01, c01_symbols, c01_fallback),
            "R6F01": (m01.copy(), m01_symbols, "intentional_missing_modality_identity"),
            "R6P01": (p01, p01_symbols, p01_fallback),
        }
        target_index.append(pd.Timestamp(execution_session))
        for candidate_id, (target, selected_symbols, fallback_reason) in candidate_rows.items():
            targets[candidate_id].append(target)
            weights = {symbol: float(target[symbol]) for symbol in columns}
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": list(map(str, selected_symbols)),
                    "weights": weights,
                    "target_sha256": hashlib.sha256(
                        _canonical_json_bytes(
                            {symbol: weights[symbol] for symbol in sorted(weights)}
                        )
                    ).hexdigest(),
                    "fallback_reason": fallback_reason,
                    "unexpected_model_fallback": bool(
                        fallback_reason
                        and fallback_reason
                        not in {
                            "intentional_missing_modality_identity",
                            "fewer_than_three_survival_eligible_symbols",
                        }
                    ),
                }
            )

    frames = {
        candidate_id: pd.DataFrame(rows, index=pd.DatetimeIndex(target_index), columns=columns)
        for candidate_id, rows in targets.items()
    }
    if canonical_target_bytes(frames["R6F01"]) != canonical_target_bytes(frames["R6M01"]):
        raise ValueError("R6F01 target identity with R6M01 failed")
    return frames, target_records, model_records, pd.DataFrame(calibration_rows)


def probability_backtest_overfitting_r6(
    returns: pd.DataFrame,
    *,
    candidate_ids: list[str] | tuple[str, ...],
    block_count: int = 8,
    in_sample_block_count: int = 4,
) -> dict[str, Any]:
    candidates = list(candidate_ids)
    if len(candidates) < 2 or len(set(candidates)) != len(candidates):
        raise ValueError("R6 PBO requires at least two unique candidates")
    values = returns.loc[:, candidates].astype(float)
    if values.empty or values.index.has_duplicates or not np.isfinite(values.to_numpy()).all():
        raise ValueError("R6 PBO returns are incomplete")
    blocks, partitions = build_cscv_partitions(
        values.index,
        block_count=block_count,
        in_sample_block_count=in_sample_block_count,
    )
    all_blocks = set(range(block_count))
    rows: list[dict[str, Any]] = []
    contribution_sum = 0.0
    for partition_number, in_blocks_raw in enumerate(partitions, start=1):
        in_blocks = tuple(map(int, in_blocks_raw))
        out_blocks = tuple(sorted(all_blocks - set(in_blocks)))
        in_positions = np.sort(
            np.concatenate(
                [
                    np.arange(blocks[index]["position_start"], blocks[index]["position_end"] + 1)
                    for index in in_blocks
                ]
            )
        )
        out_positions = np.sort(
            np.concatenate(
                [
                    np.arange(blocks[index]["position_start"], blocks[index]["position_end"] + 1)
                    for index in out_blocks
                ]
            )
        )
        in_sharpes = {
            candidate: _annualized_sharpe(values.iloc[in_positions][candidate])
            for candidate in candidates
        }
        out_sharpes = {
            candidate: _annualized_sharpe(values.iloc[out_positions][candidate])
            for candidate in candidates
        }
        maximum = max(in_sharpes.values())
        winners = [candidate for candidate in candidates if in_sharpes[candidate] == maximum]
        out_values = pd.Series(out_sharpes, dtype=float)
        average_ranks = out_values.rank(method="average", ascending=True)
        winner_rows: list[dict[str, Any]] = []
        partition_contributions: list[float] = []
        for winner in winners:
            rank = float(average_ranks[winner])
            omega = (rank - 0.5) / len(candidates)
            contribution = 1.0 if omega < 0.5 else 0.0 if omega > 0.5 else 0.5
            partition_contributions.append(contribution)
            winner_rows.append(
                {
                    "candidate_id": winner,
                    "out_of_sample_average_rank": rank,
                    "normalized_rank": omega,
                    "logit": math.log(omega / (1.0 - omega)),
                    "overfit_contribution": contribution,
                }
            )
        partition_contribution = math.fsum(partition_contributions) / len(winners)
        contribution_sum += partition_contribution
        rows.append(
            {
                "partition": partition_number,
                "in_sample_blocks": [blocks[index]["block_id"] for index in in_blocks],
                "out_of_sample_blocks": [blocks[index]["block_id"] for index in out_blocks],
                "in_sample_sharpes": in_sharpes,
                "out_of_sample_sharpes": out_sharpes,
                "in_sample_winners": winners,
                "winner_evidence": winner_rows,
                "fractional_overfit_contribution": partition_contribution,
            }
        )
    expected = math.comb(block_count, in_sample_block_count)
    if len(rows) != expected:
        raise ValueError("R6 PBO partition set is incomplete")
    return {
        "method": "candidate_id_invariant_fractional_CSCV_PBO",
        "partition_count": len(rows),
        "valid_partition_count": len(rows),
        "probability": contribution_sum / len(rows),
        "fractional_overfit_contribution_sum": contribution_sum,
        "blocks": blocks,
        "partitions": rows,
    }


def _annualized_sharpe(values: pd.Series | np.ndarray) -> float:
    series = pd.Series(values, dtype=float)
    if len(series) < 2 or not np.isfinite(series.to_numpy()).all():
        raise ValueError("R6 Sharpe requires at least two finite returns")
    std = float(series.std(ddof=1))
    if std <= 0.0:
        raise ValueError("R6 Sharpe is undefined for zero variance")
    return float(series.mean() / std * math.sqrt(252.0))


def deflated_sharpe_ratio_r6(
    returns: pd.Series,
    *,
    trial_count: int,
    scope_ids: list[str],
    hac_lag: int = 21,
) -> dict[str, Any]:
    values = pd.Series(returns, dtype=float)
    if trial_count < 2 or len(values) <= hac_lag or len(scope_ids) != len(values):
        raise ValueError("R6 DSR dimensions are invalid")
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all() or values.nunique() < 2:
        raise ValueError("R6 DSR returns must be finite and nonconstant")
    n = len(array)
    mean = float(array.mean())
    sample_std = float(values.std(ddof=1))
    observed_daily = mean / sample_std
    centered = array - mean
    moment2 = float(np.mean(centered**2))
    raw_skew = float(np.mean(centered**3) / moment2**1.5)
    skew = math.sqrt(n * (n - 1.0)) / (n - 2.0) * raw_skew
    raw_excess = float(np.mean(centered**4) / moment2**2 - 3.0)
    excess = (n - 1.0) / ((n - 2.0) * (n - 3.0)) * ((n + 1.0) * raw_excess + 6.0)
    kurtosis = excess + 3.0
    denominator = 1.0 - skew * observed_daily + (kurtosis - 1.0) / 4.0 * observed_daily**2
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("R6 DSR denominator is invalid")

    normal = NormalDist()
    gamma = 0.5772156649015329
    expected_max_standard = (1.0 - gamma) * normal.inv_cdf(1.0 - 1.0 / trial_count) + (
        gamma * normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))
    )
    iid_statistic = (observed_daily * math.sqrt(n - 1.0) - expected_max_standard) / math.sqrt(
        denominator
    )
    iid_probability = normal.cdf(iid_statistic)

    z = centered / sample_std
    influence = z - 0.5 * observed_daily * (z**2 - 1.0)
    influence_centered = influence - float(influence.mean())
    gamma0 = float(np.dot(influence_centered, influence_centered) / n)
    lag_rows: list[dict[str, Any]] = []
    long_run_variance = gamma0
    for lag in range(1, hac_lag + 1):
        products = [
            float(influence_centered[index] * influence_centered[index - lag])
            for index in range(lag, n)
            if scope_ids[index] == scope_ids[index - lag]
        ]
        autocovariance = math.fsum(products) / n
        weight = 1.0 - lag / (hac_lag + 1.0)
        long_run_variance += 2.0 * weight * autocovariance
        lag_rows.append(
            {
                "lag": lag,
                "bartlett_weight": weight,
                "within_scope_pair_count": len(products),
                "autocovariance": autocovariance,
            }
        )
    long_run_variance = max(0.0, long_run_variance)
    hac_standard_error_annualized = math.sqrt(long_run_variance / n) * math.sqrt(252.0)
    observed_annualized = observed_daily * math.sqrt(252.0)
    expected_annualized = expected_max_standard / math.sqrt(n - 1.0) * math.sqrt(252.0)
    if hac_standard_error_annualized <= 0.0:
        raise ValueError("R6 influence-HAC standard error is nonpositive")
    hac_statistic = (observed_annualized - expected_annualized) / hac_standard_error_annualized
    hac_probability = normal.cdf(hac_statistic)
    promotion_probability = min(iid_probability, hac_probability)
    return {
        "estimator_id": "bailey_lopez_de_prado_expected_max_normal_with_sharpe_influence_hac_v3",
        "trial_count": trial_count,
        "session_count": n,
        "scope_count": len(set(scope_ids)),
        "probability": promotion_probability,
        "iid_probability": iid_probability,
        "hac_probability": hac_probability,
        "promotion_probability": promotion_probability,
        "promotion_probability_rule": "minimum_of_iid_DSR_and_influence_HAC_DSR_probabilities",
        "observed_annualized_sharpe": observed_annualized,
        "expected_max_annualized_sharpe_under_null": expected_annualized,
        "iid_statistic": iid_statistic,
        "hac_statistic": hac_statistic,
        "return_skew": skew,
        "return_pearson_kurtosis": kurtosis,
        "hac_overlay_id": "bartlett_newey_west_sharpe_influence_long_run_variance_v1",
        "hac_lag": hac_lag,
        "influence_series_sha256": hashlib.sha256(
            np.asarray(influence, dtype="<f8").tobytes()
        ).hexdigest(),
        "hac_gamma0": gamma0,
        "hac_long_run_variance": long_run_variance,
        "hac_standard_error_annualized": hac_standard_error_annualized,
        "hac_lags": lag_rows,
    }


def _bind_raw_execution_marks(
    simulation: ExactSimulationResult,
    raw_opens: pd.DataFrame,
) -> None:
    for event in simulation.events:
        session = pd.Timestamp(str(event["session"]))
        if session not in raw_opens.index:
            raise ValueError(f"R6 raw execution mark is missing: {session.date()}")
        prices = raw_opens.loc[session].astype(float)
        pretrade_equity = float(event["pretrade_equity"])
        posttrade_equity = pretrade_equity * float(event["posttrade_equity_ratio"])
        pretrade_weights = event["pretrade_asset_weights"]
        target_weights = event["target_asset_weights"]
        raw_notional = 0.0
        raw_rows: list[dict[str, Any]] = []
        for symbol in raw_opens.columns:
            price = float(prices[symbol])
            pretrade_shares = pretrade_equity * float(pretrade_weights[symbol]) / price
            target_shares = posttrade_equity * float(target_weights[symbol]) / price
            delta = target_shares - pretrade_shares
            raw_notional += abs(delta) * price / pretrade_equity
            raw_rows.append(
                {
                    "symbol": str(symbol),
                    "raw_open": price,
                    "pretrade_shares_per_initial_equity": pretrade_shares,
                    "target_shares_per_initial_equity": target_shares,
                    "delta_shares_per_initial_equity": delta,
                }
            )
        if abs(raw_notional - float(event["full_L1_executed_notional_fraction"])) > 1e-12:
            raise ValueError("R6 raw-open share notional differs from weight accounting")
        event["execution_price_adjustment"] = "raw"
        event["raw_share_notional_fraction"] = raw_notional
        event["raw_execution_rows_sha256"] = hashlib.sha256(
            _canonical_json_bytes(raw_rows)
        ).hexdigest()


def _daily_rows(
    simulation: ExactSimulationResult,
    *,
    candidate_id: str,
    scope_id: str,
    cost_view: str,
) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "scope_id": scope_id,
            "cost_view": cost_view,
            **_json_ready(row),
        }
        for row in simulation.daily.to_dict(orient="records")
    ]


def _event_rows(
    simulation: ExactSimulationResult,
    *,
    candidate_id: str,
    scope_id: str,
    cost_view: str,
) -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "scope_id": scope_id,
            "cost_view": cost_view,
            **_json_ready(row),
        }
        for row in simulation.events
    ]


def _stitched_fold_returns(
    simulations: dict[str, dict[str, dict[str, ExactSimulationResult]]],
    folds: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[str]]:
    columns: dict[str, pd.Series] = {}
    scopes: list[str] | None = None
    for candidate_id in SPEC_PATHS:
        pieces: list[pd.Series] = []
        candidate_scopes: list[str] = []
        for fold in folds:
            fold_id = str(fold["fold_id"])
            daily = simulations[candidate_id][fold_id]["primary_10bps"].daily
            pieces.append(
                pd.Series(
                    daily["net_return"].to_numpy(dtype=float),
                    index=pd.Index(daily["interval_start"].astype(str), name="interval_start"),
                )
            )
            candidate_scopes.extend([fold_id] * len(daily))
        stitched = pd.concat(pieces)
        if stitched.index.has_duplicates:
            raise ValueError(f"R6 stitched fold returns overlap: {candidate_id}")
        columns[candidate_id] = stitched
        if scopes is None:
            scopes = candidate_scopes
        elif scopes != candidate_scopes:
            raise ValueError("R6 stitched fold scopes differ by candidate")
    result = pd.DataFrame(columns)
    if result.isna().any().any() or not np.isfinite(result.to_numpy()).all():
        raise ValueError("R6 stitched fold return matrix is incomplete")
    return result, scopes or []


def _calibration_fit(frame: pd.DataFrame, *, clip: float, threshold: float) -> dict[str, Any]:
    labels = frame["label"].to_numpy(dtype=float)
    probabilities = frame["probability"].to_numpy(dtype=float)
    base = frame["training_base_probability"].to_numpy(dtype=float)
    if (
        len(labels) < 3
        or not np.isfinite(labels).all()
        or not np.isfinite(probabilities).all()
        or not np.isfinite(base).all()
        or not np.isin(labels, [0.0, 1.0]).all()
    ):
        raise ValueError("R6 calibration inputs are invalid")
    clipped = np.clip(probabilities, clip, 1.0 - clip)
    logits = np.log(clipped / (1.0 - clipped))
    design = np.column_stack([np.ones(len(logits)), logits])

    def objective(coefficients: np.ndarray) -> float:
        linear = np.clip(design @ coefficients, -40.0, 40.0)
        return float(np.sum(np.logaddexp(0.0, linear) - labels * linear))

    fitted = minimize(objective, np.asarray([0.0, 1.0]), method="BFGS")
    intercept = float(fitted.x[0]) if fitted.success and np.isfinite(fitted.x).all() else None
    slope = float(fitted.x[1]) if fitted.success and np.isfinite(fitted.x).all() else None
    model_brier = float(np.mean((probabilities - labels) ** 2))
    base_brier = float(np.mean((base - labels) ** 2))
    brier_skill = 1.0 - model_brier / base_brier if base_brier > 0.0 else -math.inf
    accepted = labels[probabilities >= threshold]
    rejected = labels[probabilities < threshold]
    survival_lift = (
        float(accepted.mean() - rejected.mean())
        if len(accepted) > 0 and len(rejected) > 0
        else -math.inf
    )
    return {
        "observation_count": len(labels),
        "positive_label_count": int(np.sum(labels == 1.0)),
        "negative_label_count": int(np.sum(labels == 0.0)),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "model_brier_score": model_brier,
        "training_base_probability_brier_score": base_brier,
        "brier_skill_vs_training_base_rate": brier_skill,
        "threshold": threshold,
        "threshold_accepted_count": len(accepted),
        "threshold_rejected_count": len(rejected),
        "threshold_group_realized_survival_lift": survival_lift,
        "fit_success": intercept is not None and slope is not None,
    }


def _calibration_payload(
    calibration_by_segment: dict[str, pd.DataFrame],
    folds: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    clip = float(contract["probability_clip"])
    threshold = 0.55
    expected = {
        str(key): int(value)
        for key, value in contract["expected_observation_count_by_fold"].items()
    }
    fold_rows: dict[str, Any] = {}
    combined: list[pd.DataFrame] = []
    for fold in folds:
        fold_id = str(fold["fold_id"])
        frame = calibration_by_segment.get(fold_id, pd.DataFrame())
        if frame.empty:
            fold_rows[fold_id] = {
                "observation_count": 0,
                "expected_observation_count": expected[fold_id],
                "pass": False,
            }
            continue
        row = _calibration_fit(frame, clip=clip, threshold=threshold)
        row["expected_observation_count"] = expected[fold_id]
        row["observation_count_match"] = row["observation_count"] == expected[fold_id]
        row["minimum_class_count_pass"] = min(
            row["positive_label_count"], row["negative_label_count"]
        ) >= int(contract["minimum_class_count_per_fold"])
        row["joint_brier_and_slope_pass"] = bool(
            row["observation_count_match"]
            and row["minimum_class_count_pass"]
            and row["brier_skill_vs_training_base_rate"]
            > float(contract["brier_skill_vs_fold_train_base_rate_min_exclusive"])
            and row["calibration_slope"] is not None
            and float(contract["calibration_slope_min"])
            <= row["calibration_slope"]
            <= float(contract["calibration_slope_max"])
        )
        row["pass"] = row["joint_brier_and_slope_pass"]
        fold_rows[fold_id] = row
        combined.append(frame)
    aggregate = _calibration_fit(pd.concat(combined), clip=clip, threshold=threshold)
    passing = sum(bool(row.get("joint_brier_and_slope_pass")) for row in fold_rows.values())
    return {
        "candidate_id": "R6M02",
        "folds": fold_rows,
        "aggregate": aggregate,
        "joint_brier_and_slope_passing_fold_count": passing,
        "required_joint_brier_and_slope_passing_fold_count": int(
            contract["joint_brier_and_slope_passing_folds_min"]
        ),
        "all_observation_counts_match": all(
            bool(row.get("observation_count_match")) for row in fold_rows.values()
        ),
    }


def _rejected_opportunity_cost_bps(
    m01: pd.DataFrame,
    m02: pd.DataFrame,
    adjusted_opens: pd.DataFrame,
) -> tuple[float, int]:
    if not m01.index.equals(m02.index):
        raise ValueError("R6 M02 opportunity targets are misaligned")
    costs: list[float] = []
    sessions = list(m01.index)
    for index, session in enumerate(sessions[:-1]):
        if np.array_equal(
            m01.loc[session].to_numpy(dtype=float), m02.loc[session].to_numpy(dtype=float)
        ):
            continue
        terminal = sessions[index + 1]
        relative = adjusted_opens.loc[terminal].div(adjusted_opens.loc[session]).sub(1.0)
        m01_return = float(np.dot(m01.loc[session].to_numpy(dtype=float), relative.to_numpy()))
        m02_return = float(np.dot(m02.loc[session].to_numpy(dtype=float), relative.to_numpy()))
        costs.append(max(0.0, m01_return - m02_return) * 10_000.0)
    return (float(np.mean(costs)) if costs else 0.0, len(costs))


def _remap_ids(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {_remap_ids(key, mapping): _remap_ids(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_remap_ids(item, mapping) for item in value]
    if isinstance(value, str):
        result = value
        for source, destination in mapping.items():
            result = result.replace(source, destination)
        return result
    return value


def _jsonl_sha256(rows: list[dict[str, Any]]) -> str:
    payload = "".join(
        json.dumps(_json_ready(row), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _llm_bootstrap_r6(
    daily_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any]:
    to_r5 = {"R6C01": "R5C01", "R6M01": "R5M01", "R6P01": "R5P01"}
    to_r6 = {value: key for key, value in to_r5.items()}
    selected = {"R6C01", "R6M01", "R6P01"}
    mapped_daily = _remap_ids(
        [row for row in daily_rows if row.get("candidate_id") in selected], to_r5
    )
    mapped_events = _remap_ids(
        [row for row in event_rows if row.get("candidate_id") in selected], to_r5
    )
    result = paired_transfer_sharpe_bootstrap(
        mapped_daily,
        mapped_events,
        contract=_expected_llm_contribution_bootstrap_contract(),
    )
    result = _remap_ids(result, to_r6)
    result["config"] = contract
    result["config_sha256"] = hashlib.sha256(_canonical_json_bytes(contract)).hexdigest()
    result["source_ledgers"] = {
        "daily_return_ledger_sha256": _jsonl_sha256(daily_rows),
        "event_ledger_sha256": _jsonl_sha256(event_rows),
    }
    return result


def _benchmark_gates(
    candidates: dict[str, Any],
    benchmark_payload: dict[str, Any],
    benchmark_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    config = benchmark_contract["promotion_gates"]
    cost_view = str(config["cost_view"])
    metric = str(config["metric"])
    benchmark_values = {
        benchmark_id: float(
            benchmark_payload["results"][benchmark_id]["cost_views"][cost_view][metric]
        )
        for benchmark_id in config["required_benchmark_ids"]
    }
    output: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        value = float(candidate["aggregate_cost_views"][cost_view][metric])
        deltas = {key: value - benchmark for key, benchmark in benchmark_values.items()}
        output[candidate_id] = {
            "candidate_value": value,
            "required_benchmark_values": benchmark_values,
            "deltas": deltas,
            "minimum_delta": float(config["minimum_delta"]),
            "pass": all(delta >= float(config["minimum_delta"]) for delta in deltas.values()),
        }
    return output


def _role_gates(
    candidates: dict[str, Any],
    *,
    calibration: dict[str, Any],
    aggregate_targets: dict[str, pd.DataFrame],
    segment_targets: dict[str, dict[str, pd.DataFrame]],
    formula_evidence: dict[str, Any],
    llm_bootstrap: dict[str, Any],
    validation: dict[str, Any],
    adjusted_opens: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    fold_ids = sorted(candidates["R6D01"]["folds"])

    def fold_sharpe(candidate_id: str, fold_id: str) -> float:
        return float(
            candidates[candidate_id]["folds"][fold_id]["primary_10bps"]["annualized_sharpe"]
        )

    def transfer_sharpe(candidate_id: str) -> float:
        return float(
            candidates[candidate_id]["transfer_holdout"]["primary_10bps"]["annualized_sharpe"]
        )

    contracts = validation["role_gates"]
    m01_wins = sum(fold_sharpe("R6M01", fold) > fold_sharpe("R6D01", fold) for fold in fold_ids)
    l01_wins = sum(fold_sharpe("R6L01", fold) > fold_sharpe("R6D01", fold) for fold in fold_ids)
    c01_wins = sum(
        fold_sharpe("R6C01", fold) > max(fold_sharpe("R6M01", fold), fold_sharpe("R6P01", fold))
        for fold in fold_ids
    )
    p01_valid = bool(
        candidates["R6P01"]["unexpected_model_fallback_count"] == 0
        and formula_evidence["joint_permutation_pass"]
        and formula_evidence["formula_feature_divergence_pass"]
    )
    m02_contract = contracts["R6M02"]
    aggregate_calibration = calibration["aggregate"]
    m01_metrics = candidates["R6M01"]["aggregate_cost_views"]["primary_10bps"]
    m02_metrics = candidates["R6M02"]["aggregate_cost_views"]["primary_10bps"]
    drawdown_improvement = abs(float(m01_metrics["max_drawdown_pct"])) - abs(
        float(m02_metrics["max_drawdown_pct"])
    )
    return_shortfall_bps = (
        max(
            0.0,
            float(m01_metrics["annualized_return_pct"])
            - float(m02_metrics["annualized_return_pct"]),
        )
        * 100.0
    )
    opportunity_cost_bps, opportunity_count = _rejected_opportunity_cost_bps(
        aggregate_targets["R6M01"], aggregate_targets["R6M02"], adjusted_opens
    )
    six_checks = {
        "calibration_intercept": bool(
            aggregate_calibration["calibration_intercept"] is not None
            and aggregate_calibration["calibration_intercept"]
            <= float(m02_contract["calibration_intercept_max"])
        ),
        "brier_skill": aggregate_calibration["brier_skill_vs_training_base_rate"]
        > float(m02_contract["brier_skill_vs_fold_train_base_rate_min_exclusive"]),
        "threshold_group_survival_lift": aggregate_calibration[
            "threshold_group_realized_survival_lift"
        ]
        > float(m02_contract["threshold_group_realized_survival_lift_min_exclusive"]),
        "max_drawdown_improvement": drawdown_improvement
        >= float(m02_contract["max_drawdown_improvement_vs_R6M01_pct_points_min"]),
        "exposure_matched_return_shortfall": return_shortfall_bps
        <= float(m02_contract["exposure_matched_return_shortfall_bps_max"]),
        "rejected_opportunity_cost": opportunity_cost_bps
        <= float(m02_contract["rejected_opportunity_cost_bps_max"]),
    }
    m02_difference_count = _target_difference_count(
        aggregate_targets["R6M02"], aggregate_targets["R6M01"]
    )
    different_folds = [
        fold
        for fold in fold_ids
        if _target_difference_count(segment_targets[fold]["R6M02"], segment_targets[fold]["R6M01"])
        > 0
    ]
    m02_behavior = bool(
        m02_difference_count >= int(m02_contract["minimum_applied_gate_decisions"])
        and len(different_folds)
        >= int(m02_contract["minimum_folds_with_target_difference_from_R6M01"])
        and canonical_target_hash(aggregate_targets["R6M02"])
        != canonical_target_hash(aggregate_targets["R6M01"])
    )
    return {
        "R6D01": {"pass": True, "reason": "deterministic_baseline"},
        "R6D02": {"pass": True, "reason": "deterministic_control"},
        "R6M01": {
            "fold_wins": m01_wins,
            "transfer_win": transfer_sharpe("R6M01") > transfer_sharpe("R6D01"),
            "pass": bool(
                m01_wins >= int(contracts["R6M01"]["minimum_winning_folds"])
                and transfer_sharpe("R6M01") > transfer_sharpe("R6D01")
            ),
        },
        "R6M02": {
            "six_gate_values": {
                "calibration_intercept": aggregate_calibration["calibration_intercept"],
                "brier_skill_vs_training_base_rate": aggregate_calibration[
                    "brier_skill_vs_training_base_rate"
                ],
                "threshold_group_realized_survival_lift": aggregate_calibration[
                    "threshold_group_realized_survival_lift"
                ],
                "max_drawdown_improvement_pct_points": drawdown_improvement,
                "exposure_matched_return_shortfall_bps": return_shortfall_bps,
                "rejected_opportunity_cost_bps": opportunity_cost_bps,
                "rejected_opportunity_period_count": opportunity_count,
            },
            "six_gate_checks": six_checks,
            "joint_brier_and_slope_passing_folds": calibration[
                "joint_brier_and_slope_passing_fold_count"
            ],
            "target_difference_count": m02_difference_count,
            "folds_with_target_difference": different_folds,
            "behavior_gate_pass": m02_behavior,
            "pass": bool(
                all(six_checks.values())
                and calibration["all_observation_counts_match"]
                and calibration["joint_brier_and_slope_passing_fold_count"]
                >= int(m02_contract["joint_brier_and_slope_passing_folds_min"])
                and m02_behavior
            ),
        },
        "R6L01": {
            "fold_wins": l01_wins,
            "transfer_win": transfer_sharpe("R6L01") > transfer_sharpe("R6D01"),
            "formula_ordering_audit_pass": bool(
                formula_evidence["formula_composite_nonconstant_pass"]
                and canonical_target_hash(aggregate_targets["R6L01"])
                != canonical_target_hash(aggregate_targets["R6D01"])
            ),
            "pass": bool(
                l01_wins >= int(contracts["R6L01"]["minimum_winning_folds"])
                and transfer_sharpe("R6L01") > transfer_sharpe("R6D01")
                and formula_evidence["formula_composite_nonconstant_pass"]
            ),
        },
        "R6C01": {
            "same_fold_wins_against_M01_and_P01": c01_wins,
            "transfer_win_against_both": transfer_sharpe("R6C01")
            > max(transfer_sharpe("R6M01"), transfer_sharpe("R6P01")),
            "valid_R6P01_placebo": p01_valid,
            "paired_transfer_bootstrap": llm_bootstrap,
            "pass": bool(
                c01_wins >= int(contracts["R6C01"]["minimum_winning_folds"])
                and transfer_sharpe("R6C01")
                > max(transfer_sharpe("R6M01"), transfer_sharpe("R6P01"))
                and p01_valid
                and llm_bootstrap["pass"]
            ),
        },
        "R6F01": {
            "exact_target_identity": canonical_target_bytes(aggregate_targets["R6F01"])
            == canonical_target_bytes(aggregate_targets["R6M01"]),
            "pass": canonical_target_bytes(aggregate_targets["R6F01"])
            == canonical_target_bytes(aggregate_targets["R6M01"]),
        },
        "R6P01": {
            "selection_prohibited": True,
            "zero_unexpected_model_fallbacks": candidates["R6P01"][
                "unexpected_model_fallback_count"
            ]
            == 0,
            "joint_permutation_evidence_pass": formula_evidence["joint_permutation_pass"],
            "formula_feature_divergence_pass": formula_evidence["formula_feature_divergence_pass"],
            "pass": p01_valid,
        },
    }


def _family_gates(
    candidates: dict[str, Any],
    validation: dict[str, Any],
    benchmark_gates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    contract = validation["family_gates"]
    output: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        positive_primary = sum(
            float(row["primary_10bps"]["total_return_pct"]) > 0.0
            for row in candidate["folds"].values()
        )
        positive_stress = sum(
            float(row["stress_20bps"]["total_return_pct"]) > 0.0
            for row in candidate["folds"].values()
        )
        transfer = candidate["transfer_holdout"]["primary_10bps"]
        aggregate = candidate["aggregate_cost_views"]["primary_10bps"]
        checks = {
            "positive_net_return_folds": positive_primary
            >= int(contract["positive_net_return_folds_min"]),
            "positive_stress_folds": positive_stress
            >= int(contract["stress_20bps_positive_folds_min"]),
            "transfer_sharpe": float(transfer["annualized_sharpe"])
            >= float(contract["transfer_holdout_sharpe_min"]),
            "transfer_drawdown": abs(float(transfer["max_drawdown_pct"]))
            <= float(contract["transfer_holdout_max_drawdown_abs_pct_max"]),
            "turnover": float(aggregate["annualized_full_L1_executed_notional_ratio"])
            <= float(contract["annualized_full_L1_executed_notional_ratio_max"]),
            "BIL_excess_sharpe": float(aggregate["annualized_BIL_excess_sharpe"])
            >= float(contract["annualized_BIL_excess_sharpe_min"]),
            "DSR": float(candidate["dsr"]["promotion_probability"])
            >= float(contract["cumulative_dsr_probability_min"]),
            "benchmarks": benchmark_gates[candidate_id]["pass"],
            "no_unexpected_model_fallback": candidate["unexpected_model_fallback_count"] == 0,
        }
        output[candidate_id] = {
            "positive_primary_fold_count": positive_primary,
            "positive_stress_fold_count": positive_stress,
            "checks": checks,
            "pass": all(checks.values()),
        }
    return output


def _bil_excess_sharpe(candidate: ExactSimulationResult, bil: ExactSimulationResult) -> float:
    left = candidate.daily.set_index("interval_start")["net_return"].astype(float)
    right = bil.daily.set_index("interval_start")["net_return"].astype(float)
    if not left.index.equals(right.index):
        raise ValueError("R6 candidate and BIL return intervals differ")
    return _annualized_sharpe(left - right)


def _render_markdown(payload: dict[str, Any]) -> str:
    pbo = payload["family_pbo"]
    lines = [
        "# R6 Multiasset Forward Multimodal Evaluation",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{str(payload['workflow_pass']).lower()}`",
        f"- Research pass: `{str(payload['research_pass']).lower()}`",
        f"- LLM contribution pass: `{str(payload['llm_contribution_pass']).lower()}`",
        f"- Paper ready pass: `{str(payload['paper_ready_pass']).lower()}`",
        f"- Selected candidates: `{', '.join(payload['selected_candidate_ids']) or 'none'}`",
        f"- Family PBO: `{pbo['probability']:.6f}` over `{pbo['partition_count']}` partitions",
        "",
        "| Candidate | Role | Total return | Annualized | Sharpe | "
        "Max drawdown | DSR | Family | Role |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for candidate_id in SPEC_PATHS:
        row = payload["candidates"][candidate_id]
        metrics = row["aggregate_cost_views"]["primary_10bps"]
        lines.append(
            f"| {candidate_id} | {row['role']} | {metrics['total_return_pct']:.3f}% | "
            f"{metrics['annualized_return_pct']:.3f}% | {metrics['annualized_sharpe']:.3f} | "
            f"{metrics['max_drawdown_pct']:.3f}% | {row['dsr']['promotion_probability']:.4f} | "
            f"{row['family_gates']['pass']} | {row['role_gate']['pass']} |"
        )
    lines.extend(
        [
            "",
            "Historical results use immutable Alpaca all-adjusted bars for features and "
            "total returns, with raw opens bound to every transaction-notional event. "
            "They are transfer evidence, not Paper performance.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_record(payload: dict[str, Any]) -> str:
    selected = ", ".join(payload["selected_candidate_ids"]) or "none"
    if payload["research_pass"]:
        reason = (
            f"Frozen historical gates selected {selected}; only broker-free forward "
            "observation may begin."
        )
        suggestion = (
            "Retain the frozen candidates and start the zero-count 2026-08-03 forward "
            "epoch; do not retune from historical results."
        )
    else:
        reason = (
            "No promotion-eligible candidate cleared every frozen family, role, PBO and DSR gate."
        )
        suggestion = (
            "Start a new iteration only after identifying one failed economic assumption; "
            "preserve all R6 results as negative evidence."
        )
    return (
        f"# Decision Record: {ITER_ID}\n\n"
        "- Path: `eight_candidate_matched_etf_multimodal_family`\n"
        f"- Decision: `{payload['decision']}`\n"
        f"- Reason: {reason}\n"
        f"- Next iteration suggestion: {suggestion}\n"
        "- Paper authority: false; 20 real forward sessions, promotion review, safety "
        "review, explicit confirmation and matched Paper TCA remain required.\n"
    )


def run_multiasset_forward_multimodal_r6(
    root: Path,
    *,
    expected_lock_anchor_sha256: str,
) -> R6EvaluationResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    destination = output / "evaluation-run"
    if destination.exists():
        raise ValueError("R6 evaluation was already published")
    if any(output.glob("evaluation-run.staging-*")):
        raise ValueError("R6 evaluation has unresolved staging state")
    lock = _verify_lock(base, expected_lock_anchor_sha256)
    dossier = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if dossier.status != "ok":
        raise ValueError("R6 dossier changed after lock: " + ", ".join(dossier.blocked))

    contracts = {
        name: _load_json(output / filename)
        for name, filename in {
            "data": "data-contract.json",
            "feature": "feature-contract.json",
            "validation": "validation-contract.json",
            "cost": "cost-contract.json",
            "benchmark": "benchmark-contract.json",
            "trials": "cumulative-trial-contract.json",
        }.items()
    }
    specs = {
        candidate_id: load_strategy_spec(base / path) for candidate_id, path in SPEC_PATHS.items()
    }
    _validate_specs(specs)
    locked_specs = {row["candidate_id"]: row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id]["semantic_sha256"]:
            raise ValueError(f"R6 semantic spec changed after lock: {candidate_id}")

    data_contract = contracts["data"]
    manifest_path = base / str(data_contract["snapshot_manifest_path"])
    panels = load_r6_panels(
        base,
        manifest_path,
        expected_manifest_sha256=str(data_contract["snapshot_manifest_sha256"]),
    )
    adjusted = panels["all"]
    raw = panels["raw"]
    common_window = data_contract["common_window"]
    start_session = pd.Timestamp(common_window["start_session"])
    end_session = pd.Timestamp(common_window["end_session"])
    if start_session not in adjusted.open.index or end_session not in adjusted.open.index:
        raise ValueError("R6 historical common-window boundaries are absent")

    features = build_point_in_time_features(
        adjusted.close,
        adjusted.volume,
        formula_spec=specs["R6C01"],
    )
    dataset = build_monthly_feature_dataset(
        adjusted,
        features,
        placebo_spec=specs["R6P01"],
        rebalance_schedule="calendar_month_end",
    )
    feature_contract = contracts["feature"]
    provenance = {
        "data_manifest_sha256": str(data_contract["snapshot_manifest_sha256"]),
        "feature_contract_sha256": _sha256(output / "feature-contract.json"),
        "label_contract_sha256": _sha256(output / "label-contract.json"),
        "prompt_hash": str(feature_contract["llm_formula_provenance"]["prompt_hash"]),
    }

    validation = contracts["validation"]
    folds = validation["folds"]
    transfer = validation["transfer_holdout"]
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
            "segment_id": "TRANSFER",
            "train_start": str(folds[0]["train_start"]),
            "start": str(transfer["start"]),
            "end": str(transfer["end"]),
        }
    )
    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    target_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    calibration_by_segment: dict[str, pd.DataFrame] = {}
    for segment in segments:
        frames, targets, models, calibration = build_candidate_targets_for_segment(
            dataset,
            segment_id=segment["segment_id"],
            execution_start=segment["start"],
            execution_end=segment["end"],
            train_start_session=segment["train_start"],
            columns=adjusted.open.columns,
            specs=specs,
            provenance=provenance,
        )
        segment_targets[segment["segment_id"]] = frames
        target_rows.extend(targets)
        model_rows.extend(models)
        calibration_by_segment[segment["segment_id"]] = calibration
    aggregate_targets = {
        candidate_id: pd.concat(
            [segment_targets[segment["segment_id"]][candidate_id] for segment in segments]
        ).sort_index()
        for candidate_id in SPEC_PATHS
    }
    if any(frame.index.has_duplicates for frame in aggregate_targets.values()):
        raise ValueError("R6 aggregate targets contain duplicate sessions")
    if canonical_target_bytes(aggregate_targets["R6F01"]) != canonical_target_bytes(
        aggregate_targets["R6M01"]
    ):
        raise ValueError("R6 missing-modality target identity failed")

    cost_views = {
        "primary_10bps": float(contracts["cost"]["primary_cost_bps_per_executed_notional"]),
        "stress_20bps": float(contracts["cost"]["stress_cost_bps_per_executed_notional"]),
        "severe_35bps_report_only": float(
            contracts["cost"]["severe_report_only_cost_bps_per_executed_notional"]
        ),
    }
    aggregate_start = str(folds[0]["test_start"])
    aggregate_end = str(transfer["end"])
    aggregate_simulations: dict[str, dict[str, ExactSimulationResult]] = {}
    segment_simulations: dict[str, dict[str, dict[str, ExactSimulationResult]]] = {}
    daily_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for candidate_id in SPEC_PATHS:
        aggregate_simulations[candidate_id] = {}
        for view_name, cost_bps in cost_views.items():
            simulation = simulate_exact_target_portfolio(
                adjusted.open,
                aggregate_targets[candidate_id],
                cost_bps=cost_bps,
                start=aggregate_start,
                end=aggregate_end,
            )
            _bind_raw_execution_marks(simulation, raw.open)
            aggregate_simulations[candidate_id][view_name] = simulation
            daily_rows.extend(
                _daily_rows(
                    simulation,
                    candidate_id=candidate_id,
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
            event_rows.extend(
                _event_rows(
                    simulation,
                    candidate_id=candidate_id,
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
        segment_simulations[candidate_id] = {}
        for segment in segments:
            scope = segment["segment_id"]
            segment_simulations[candidate_id][scope] = {}
            for view_name in ("primary_10bps", "stress_20bps"):
                simulation = simulate_exact_target_portfolio(
                    adjusted.open,
                    segment_targets[scope][candidate_id],
                    cost_bps=cost_views[view_name],
                    start=segment["start"],
                    end=segment["end"],
                )
                _bind_raw_execution_marks(simulation, raw.open)
                segment_simulations[candidate_id][scope][view_name] = simulation
                daily_rows.extend(
                    _daily_rows(
                        simulation,
                        candidate_id=candidate_id,
                        scope_id=scope,
                        cost_view=view_name,
                    )
                )
                event_rows.extend(
                    _event_rows(
                        simulation,
                        candidate_id=candidate_id,
                        scope_id=scope,
                        cost_view=view_name,
                    )
                )

    pbo_returns, pbo_scopes = _stitched_fold_returns(segment_simulations, folds)
    pbo_contract = validation["pbo"]
    if len(pbo_returns) != int(pbo_contract["expected_return_observation_count"]):
        raise ValueError("R6 PBO return count differs from the preregistration")
    pbo = probability_backtest_overfitting_r6(
        pbo_returns,
        candidate_ids=list(map(str, pbo_contract["selection_candidate_ids"])),
        block_count=int(pbo_contract["block_count"]),
        in_sample_block_count=int(pbo_contract["in_sample_block_count"]),
    )
    if [row["observation_count"] for row in pbo["blocks"]] != list(
        map(int, pbo_contract["expected_block_observation_counts"])
    ):
        raise ValueError("R6 PBO block sizes differ from the preregistration")
    pbo["return_observation_count"] = len(pbo_returns)
    pbo["return_source_sha256"] = hashlib.sha256(
        pbo_returns.to_csv(float_format="%.17g", lineterminator="\n").encode("utf-8")
    ).hexdigest()

    trial_contract = contracts["trials"]
    dsr: dict[str, Any] = {}
    for candidate_id in SPEC_PATHS:
        sensitivity = {
            str(trial_count): deflated_sharpe_ratio_r6(
                pbo_returns[candidate_id],
                trial_count=int(trial_count),
                scope_ids=pbo_scopes,
                hac_lag=int(validation["dsr"]["hac_lag"]),
            )
            for trial_count in trial_contract["dsr_sensitivity_trial_counts"]
        }
        selected = dict(sensitivity[str(trial_contract["dsr_trial_count"])])
        selected["known_trial_count_lower_bound"] = int(
            trial_contract["cumulative_trial_count_lower_bound"]
        )
        selected["promotion_governance_trial_count"] = int(trial_contract["dsr_trial_count"])
        selected["sensitivity"] = sensitivity
        dsr[candidate_id] = selected

    monthly_sessions = aggregate_targets["R6D01"].index
    benchmark_payload, benchmark_simulations, benchmark_targets = _benchmark_family_exact(
        adjusted.open,
        monthly_sessions=monthly_sessions,
        start=aggregate_start,
        end=aggregate_end,
        primary_cost_bps=PRIMARY_COST_BPS,
        stress_cost_bps=STRESS_COST_BPS,
    )
    promotion_benchmarks = set(
        map(str, contracts["benchmark"]["promotion_gates"]["required_benchmark_ids"])
    )
    for benchmark_id, views in benchmark_simulations.items():
        benchmark_payload["results"][benchmark_id]["promotion_gate"] = (
            benchmark_id in promotion_benchmarks
        )
        for simulation in views.values():
            _bind_raw_execution_marks(simulation, raw.open)

    candidates: dict[str, Any] = {}
    bil_primary = benchmark_simulations["cash_proxy"]["primary_10bps"]
    bil_stress = benchmark_simulations["cash_proxy"]["stress_20bps"]
    for candidate_id in SPEC_PATHS:
        aggregate_metrics = {
            view_name: dict(simulation.metrics)
            for view_name, simulation in aggregate_simulations[candidate_id].items()
        }
        aggregate_metrics["primary_10bps"]["annualized_BIL_excess_sharpe"] = _bil_excess_sharpe(
            aggregate_simulations[candidate_id]["primary_10bps"], bil_primary
        )
        aggregate_metrics["stress_20bps"]["annualized_BIL_excess_sharpe"] = _bil_excess_sharpe(
            aggregate_simulations[candidate_id]["stress_20bps"], bil_stress
        )
        candidates[candidate_id] = {
            "candidate_id": candidate_id,
            "role": str(
                next(
                    row["role"]
                    for row in _load_json(output / "candidate-manifest.json")["candidates"]
                    if row["candidate_id"] == candidate_id
                )
            ),
            "spec_path": SPEC_PATHS[candidate_id].as_posix(),
            "spec_hash": strategy_content_hash(specs[candidate_id]),
            "promotion_eligible": candidate_id in PROMOTION_ELIGIBLE,
            "aggregate_target_sha256": canonical_target_hash(aggregate_targets[candidate_id]),
            "aggregate_cost_views": aggregate_metrics,
            "folds": {
                str(fold["fold_id"]): {
                    view_name: dict(
                        segment_simulations[candidate_id][str(fold["fold_id"])][view_name].metrics
                    )
                    for view_name in ("primary_10bps", "stress_20bps")
                }
                for fold in folds
            },
            "transfer_holdout": {
                view_name: dict(segment_simulations[candidate_id]["TRANSFER"][view_name].metrics)
                for view_name in ("primary_10bps", "stress_20bps")
            },
            "dsr": dsr[candidate_id],
            "unexpected_model_fallback_count": sum(
                bool(row["unexpected_model_fallback"])
                for row in target_rows
                if row["candidate_id"] == candidate_id
            ),
        }

    calibration = _calibration_payload(
        calibration_by_segment,
        folds,
        validation["role_gates"]["R6M02"],
    )
    evaluated_p01_sessions = {
        str(row["decision_session"]) for row in target_rows if row["candidate_id"] == "R6P01"
    }
    formula_evidence = _formula_placebo_evidence(dataset, decision_sessions=evaluated_p01_sessions)
    llm_bootstrap = _llm_bootstrap_r6(
        daily_rows, event_rows, validation["llm_contribution_bootstrap"]
    )
    benchmark_gates = _benchmark_gates(candidates, benchmark_payload, contracts["benchmark"])
    role_gates = _role_gates(
        candidates,
        calibration=calibration,
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_evidence=formula_evidence,
        llm_bootstrap=llm_bootstrap,
        validation=validation,
        adjusted_opens=adjusted.open,
    )
    family_gates = _family_gates(candidates, validation, benchmark_gates)
    for candidate_id in SPEC_PATHS:
        candidates[candidate_id]["benchmark_gate"] = benchmark_gates[candidate_id]
        candidates[candidate_id]["role_gate"] = role_gates[candidate_id]
        candidates[candidate_id]["family_gates"] = family_gates[candidate_id]
        candidates[candidate_id]["historical_research_gate_pass"] = bool(
            family_gates[candidate_id]["pass"] and role_gates[candidate_id]["pass"]
        )

    pbo_pass = bool(
        pbo["partition_count"] == int(pbo_contract["expected_partition_count"])
        and pbo["valid_partition_count"] == int(pbo_contract["minimum_valid_partition_count"])
        and float(pbo["probability"]) <= float(validation["family_gates"]["pbo_max"])
    )
    selected = [
        candidate_id
        for candidate_id in SPEC_PATHS
        if candidate_id in PROMOTION_ELIGIBLE
        and candidates[candidate_id]["historical_research_gate_pass"]
        and pbo_pass
    ]
    if set(selected) & SELECTION_PROHIBITED:
        raise ValueError("R6 selection-prohibited control was selected")
    workflow_pass = True
    research_pass = bool(selected)
    llm_contribution_pass = bool("R6C01" in selected and candidates["R6C01"]["role_gate"]["pass"])
    decision = "continue_to_locked_forward_observation" if research_pass else "stop_r6"
    payload = {
        "schema_version": 1,
        "report_contract": "multiasset_forward_multimodal_r6_v1",
        "report_type": "multiasset_forward_multimodal_r6_matched_transfer_evaluation",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": False,
        "selected_candidate_ids": selected,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "family_pbo": pbo,
        "family_pbo_pass": pbo_pass,
        "calibration": calibration,
        "formula_placebo_evidence": formula_evidence,
        "llm_contribution_bootstrap": llm_bootstrap,
        "benchmark_family": benchmark_payload,
        "data_evidence": {
            "snapshot_manifest_path": data_contract["snapshot_manifest_path"],
            "snapshot_manifest_sha256": data_contract["snapshot_manifest_sha256"],
            "all_adjusted_panel_role": "features_labels_and_total_returns",
            "raw_panel_role": "execution_share_and_full_L1_notional_binding",
            "session_count": len(adjusted.open),
            "snapshot_start": adjusted.open.index.min().date().isoformat(),
            "snapshot_end": adjusted.open.index.max().date().isoformat(),
            "evaluation_end": end_session.date().isoformat(),
            "raw_and_all_session_alignment": adjusted.open.index.equals(raw.open.index),
            "raw_execution_event_binding_pass": all(
                row.get("execution_price_adjustment") == "raw" for row in event_rows
            ),
        },
        "lock_binding": {
            "lock_anchor_sha256": expected_lock_anchor_sha256,
            "preregistration_lock_sha256": _sha256(output / "lock-set/preregistration-lock.json"),
        },
        "forward_requirements": {
            "epoch_start": "2026-08-03",
            "current_valid_sessions": 0,
            "minimum_bound_sessions": 20,
            "minimum_matched_tca_fills": 30,
            "minimum_matched_tca_sessions": 10,
            "paper_orders_authorized": False,
        },
        "limitations": [
            "The historical transfer window was exposed to prior strategy-family work.",
            "LLM factors are frozen static formulas; no live LLM inference or independent "
            "LLM Alpha is claimed.",
            "paper_ready_pass remains false until real forward observation, review, "
            "confirmation and matched Alpaca Paper TCA complete.",
        ],
    }

    stage = output / f"evaluation-run.staging-{os.getpid()}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        _write_json(stage / "evaluation-report.json", payload)
        (stage / "evaluation-report.md").write_text(_render_markdown(payload), encoding="utf-8")
        (stage / "decision-record.md").write_text(
            _render_decision_record(payload), encoding="utf-8"
        )
        trial_rows = [
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                **candidates[candidate_id],
            }
            for candidate_id in SPEC_PATHS
        ]
        _write_jsonl(stage / "trial-ledger.jsonl", trial_rows)
        _write_jsonl(stage / "target-ledger.jsonl", target_rows)
        _write_jsonl(stage / "model-ledger.jsonl", model_rows)
        _write_jsonl(stage / "daily-return-ledger.jsonl", daily_rows)
        _write_jsonl(stage / "cost-event-ledger.jsonl", event_rows)
        _write_jsonl(stage / "pbo-ledger.jsonl", pbo["partitions"])
        calibration_rows = [
            _json_ready(row)
            for frame in calibration_by_segment.values()
            for row in frame.to_dict(orient="records")
        ]
        _write_jsonl(stage / "calibration-ledger.jsonl", calibration_rows)
        _write_json(stage / "benchmark-report.json", benchmark_payload)
        _write_json(stage / "execution-basis.json", payload["data_evidence"])
        receipt_artifacts = [
            _publication_binding(
                path,
                root=base,
                staging_dir=stage,
                destination_dir=destination,
            )
            for path in sorted(stage.iterdir())
            if path.is_file()
        ]
        receipt = {
            "schema_version": 1,
            "receipt_contract": "multiasset_forward_multimodal_r6_evaluation_receipt_v1",
            "iter_id": ITER_ID,
            "decision": decision,
            "statuses": {
                "workflow_pass": workflow_pass,
                "research_pass": research_pass,
                "llm_contribution_pass": llm_contribution_pass,
                "paper_ready_pass": False,
            },
            "artifacts": receipt_artifacts,
        }
        _write_json(stage / "evaluation-receipt.json", receipt)
        if destination.exists():
            raise ValueError("R6 evaluation destination appeared during publication")
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    return R6EvaluationResult(
        evaluation_path=destination / "evaluation-report.json",
        trial_ledger_path=destination / "trial-ledger.jsonl",
        target_ledger_path=destination / "target-ledger.jsonl",
        receipt_path=destination / "evaluation-receipt.json",
        payload=payload,
    )
