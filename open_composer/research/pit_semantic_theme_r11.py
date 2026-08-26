from __future__ import annotations

import hashlib
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
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.dynamic_theme_chain_r8 import (
    _daily_returns,
    _simulate_static,
    _simulation_metric_views,
    cscv_probability_backtest_overfitting,
    deflated_sharpe_probability,
)
from open_composer.research.etf_structural_r9 import simulate_target_portfolio
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.router_common import RouterFrameDataset
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_pit_semantic_theme_r11"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SNAPSHOT_DIR = ITERATION_DIR / "historical-price-snapshot"
SNAPSHOT_MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"
LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
OUTPUT_DIR = ITERATION_DIR / "historical-evaluation"
RUNNER_PATH = Path("open_composer/research/pit_semantic_theme_r11.py")
TEST_PATH = Path("tests/test_pit_semantic_theme_r11.py")

UNIVERSE = (
    "QQQ",
    "TQQQ",
    "SQQQ",
    "QLD",
    "PSQ",
    "SMH",
    "SOXL",
    "SOXS",
    "TECL",
    "TECS",
    "ROM",
    "USD",
    "SPY",
    "XLK",
    "SOXX",
    "IGV",
    "GLD",
    "BIL",
)
RANKABLE_SYMBOLS = tuple(symbol for symbol in UNIVERSE if symbol != "BIL")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r11_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R11D01", "d01"),
        ("R11D02", "d02"),
        ("R11M01", "m01"),
        ("R11M02", "m02"),
        ("R11L01", "l01"),
        ("R11C01", "c01"),
        ("R11F01", "f01"),
        ("R11P01", "p01"),
    )
}
M01_FEATURES = (
    "momentum_5",
    "momentum_20",
    "momentum_60",
    "trend_gap_50",
    "trend_gap_200",
    "realized_volatility_20",
    "drawdown_20",
    "drawdown_63",
)
M02_FEATURES = (
    "momentum_5",
    "momentum_20",
    "trend_gap_50",
    "realized_volatility_10",
    "realized_volatility_20",
    "drawdown_10",
    "drawdown_20",
)
MODEL_IDS = ("R11M01_LINEAR", "R11M01", "R11M02_LINEAR", "R11M02")
TARGET_IDS = (*MODEL_IDS, "R11F01")
SELECTION_IDS = ("R11D01", "R11M01", "R11M02")
COST_VIEWS = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
EFFECTIVE_TRIAL_COUNT = 8038
DEVELOPMENT_END = "2025-07-31"
TRANSFER_START = "2025-08-01"
LOCK_STATUS = "r11_price_data_and_model_implementation_locked_before_first_historical_fit"
LINEAR_BASELINE_CONTRACT = {
    "R11M01_LINEAR": {
        "pipeline": "StandardScaler_then_Ridge",
        "alpha": 1.0,
        "fit_intercept": True,
    },
    "R11M02_LINEAR": {
        "pipeline": "StandardScaler_then_LogisticRegression",
        "C": 1.0,
        "penalty": "l2",
        "solver": "lbfgs",
        "max_iter": 1000,
    },
}
ROLE_GATE_CONTRACT = {
    "M01_minimum_fold_wins_vs_linear_and_D01": 3,
    "M01_minimum_exposure_ratio_vs_D01": 0.90,
    "M02_minimum_brier_wins_vs_linear_and_base_rate": 3,
    "M02_minimum_path_loss_improvement_folds": 3,
    "M02_minimum_exposure_ratio_vs_M01": 0.75,
    "M02_minimum_up_capture_retention_vs_M01": 0.90,
}


@dataclass(frozen=True)
class R11PricePanel:
    open: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    metadata: dict[str, Any]


@dataclass(frozen=True)
class R11FreezeResult:
    snapshot_manifest_path: Path
    lock_path: Path


@dataclass(frozen=True)
class R11EvaluationResult:
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
    feature_names: tuple[str, ...]
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


def freeze_pit_semantic_theme_r11(root: Path) -> R11FreezeResult:
    base = root.resolve()
    lock_path = base / LOCK_PATH
    output_path = base / OUTPUT_DIR
    if lock_path.exists():
        raise ValueError("R11 historical evaluation lock already exists")
    if output_path.exists() or any((base / ITERATION_DIR).glob("historical-evaluation.staging-*")):
        raise ValueError("R11 historical evaluation state exists before its lock")

    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R11 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = _load_and_validate_specs(base)
    snapshot_path = base / SNAPSHOT_MANIFEST_PATH
    if snapshot_path.exists():
        _load_snapshot_manifest(base, verify_files=True)
    else:
        _create_price_snapshot(base)

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
    )
    implementation_paths = (
        RUNNER_PATH,
        TEST_PATH,
        Path("open_composer/research/hybrid_router_core.py"),
        Path("open_composer/research/router_common.py"),
        Path("open_composer/research/etf_structural_r9.py"),
        Path("open_composer/research/dynamic_theme_chain_r8.py"),
        Path("open_composer/models/strategy_spec.py"),
        Path("open_composer/strategy_versions.py"),
        Path("pyproject.toml"),
        Path("uv.lock"),
    )
    lock = {
        "schema_version": 1,
        "lock_contract": "pit_semantic_theme_r11_historical_evaluation_v1",
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
        "snapshot_manifest": _binding(snapshot_path, base),
        "snapshot_manifest_contract": "r11_alpaca_iex_daily_snapshot_v1",
        "universe": list(UNIVERSE),
        "rankable_symbols": list(RANKABLE_SYMBOLS),
        "m01_features": list(M01_FEATURES),
        "m02_features": list(M02_FEATURES),
        "linear_baseline_contract": LINEAR_BASELINE_CONTRACT,
        "role_gate_contract": ROLE_GATE_CONTRACT,
        "cost_views_bps": COST_VIEWS,
        "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "development_end": DEVELOPMENT_END,
        "transfer_start": TRANSFER_START,
        "library_versions": {
            name: version(name) for name in ("lightgbm", "numpy", "pandas", "scikit-learn")
        },
        "historical_model_fit_at_lock": False,
        "historical_candidate_outcomes_read_at_lock": False,
        "one_shot": True,
        "order_authority": False,
        "broker_writes": False,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=False)
    write_json(lock_path, lock)
    return R11FreezeResult(snapshot_manifest_path=snapshot_path, lock_path=lock_path)


def validate_r11_specs(specs: dict[str, StrategySpec]) -> None:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R11 requires exactly the eight preregistered specs")
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
        ):
            raise ValueError(f"R11 spec safety or universe mismatch: {candidate_id}")

    d01 = specs["R11D01"]
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
        raise ValueError("R11D01 deterministic route identity mismatch")

    for candidate_id in ("R11M01", "R11M02", "R11F01"):
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
            raise ValueError(f"R11 price-model portfolio contract mismatch: {candidate_id}")

    m01 = specs["R11M01"].model
    m02 = specs["R11M02"].model
    f01 = specs["R11F01"].model
    if m01 is None or m02 is None or f01 is None:
        raise ValueError("R11 model specifications are missing")
    if (
        m01.kind != "lightgbm_regressor"
        or tuple(m01.features) != M01_FEATURES
        or m01.label.type != "forward_return"
        or m01.label.horizon_bars != 5
        or m01.training.window_bars != 756
        or m01.training.retrain_every_bars != 5
        or m01.training.embargo_bars != 10
        or m01.training.seed != 11101
        or m01.selection.method != "top_quantile"
        or m01.selection.quantile != 0.25
        or m01.baseline != "linear_composite"
    ):
        raise ValueError("R11M01 model identity mismatch")
    if (
        m02.kind != "lightgbm_classifier"
        or tuple(m02.features) != M02_FEATURES
        or m02.label.type != "path_survival"
        or m02.label.horizon_bars != 5
        or m02.label.max_drawdown_pct != 8.0
        or m02.label.min_terminal_return_pct != 0.0
        or m02.training.window_bars != 756
        or m02.training.retrain_every_bars != 5
        or m02.training.embargo_bars != 10
        or m02.training.seed != 11102
        or m02.selection.method != "threshold"
        or m02.selection.threshold != 0.55
        or m02.baseline != "linear_composite"
    ):
        raise ValueError("R11M02 model identity mismatch")
    if f01.model_dump(mode="json") != m01.model_dump(mode="json"):
        raise ValueError("R11F01 model contract must exactly match R11M01")


def _load_and_validate_specs(root: Path) -> dict[str, StrategySpec]:
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    validate_r11_specs(specs)
    return specs


def _create_price_snapshot(root: Path) -> Path:
    destination = root / SNAPSHOT_DIR
    staging = destination.with_name(
        f"{destination.name}.staging-{os.getpid()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )
    if destination.exists() or staging.exists():
        raise ValueError("R11 historical price snapshot already exists")
    staging_data = staging / "data"
    staging_data.mkdir(parents=True, exist_ok=False)
    items: list[dict[str, Any]] = []
    date_sets: list[set[str]] = []
    try:
        for symbol in UNIVERSE:
            source = _regular_in_root(root, root / "data/cache" / f"{symbol.lower()}_daily_iex.csv")
            output = staging_data / source.name
            shutil.copyfile(source, output)
            source_hash = _sha256(source)
            output_hash = _sha256(output)
            if output_hash != source_hash:
                raise ValueError(f"R11 snapshot copy hash mismatch: {symbol}")
            frame = _read_price_csv(output)
            sessions = frame.index.date.astype(str).tolist()
            date_sets.append(set(sessions))
            items.append(
                {
                    "symbol": symbol,
                    "provider": "alpaca",
                    "feed": "iex",
                    "adjustment": "all",
                    "source_path": _relpath(source, root),
                    "source_sha256": source_hash,
                    "output_path": f"data/{output.name}",
                    "output_sha256": output_hash,
                    "row_count": len(frame),
                    "first_session": sessions[0],
                    "last_session": sessions[-1],
                }
            )
        common = sorted(set.intersection(*date_sets))
        if len(common) != 1321 or common[0] != "2020-08-17" or common[-1] != "2026-08-03":
            raise ValueError("R11 snapshot common-session capacity changed before lock")
        development_count = sum(session <= DEVELOPMENT_END for session in common)
        transfer_count = sum(session >= TRANSFER_START for session in common)
        if development_count != 1091 or transfer_count != 230:
            raise ValueError("R11 snapshot development or transfer capacity changed")
        manifest = {
            "schema_version": 1,
            "snapshot_contract": "r11_alpaca_iex_daily_snapshot_v1",
            "iter_id": ITER_ID,
            "created_at": datetime.now(UTC).isoformat(),
            "provider": "alpaca",
            "feed": "iex",
            "adjustment": "all",
            "session_scope": "regular",
            "symbol_count": len(UNIVERSE),
            "symbols": list(UNIVERSE),
            "items": items,
            "common_session_count": len(common),
            "common_first_session": common[0],
            "common_last_session": common[-1],
            "common_sessions_sha256": _canonical_hash(common),
            "development_session_count": development_count,
            "transfer_session_count": transfer_count,
            "historical_returns_or_targets_computed": False,
            "broker_writes": False,
        }
        write_json(staging / "manifest.json", manifest)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return destination / "manifest.json"


def _load_snapshot_manifest(root: Path, *, verify_files: bool) -> dict[str, Any]:
    path = _regular_in_root(root, root / SNAPSHOT_MANIFEST_PATH)
    payload = _load_json(path)
    if (
        payload.get("snapshot_contract") != "r11_alpaca_iex_daily_snapshot_v1"
        or payload.get("iter_id") != ITER_ID
        or payload.get("symbols") != list(UNIVERSE)
        or payload.get("common_session_count") != 1321
        or payload.get("broker_writes") is not False
    ):
        raise ValueError("R11 snapshot manifest identity mismatch")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != len(UNIVERSE):
        raise ValueError("R11 snapshot item coverage mismatch")
    if verify_files:
        parent = path.parent
        for item in items:
            output = _regular_in_root(root, parent / str(item["output_path"]))
            if _sha256(output) != item.get("output_sha256"):
                raise ValueError(f"R11 snapshot hash mismatch: {item.get('symbol')}")
    return payload


def load_r11_price_panel(root: Path, lock: dict[str, Any]) -> R11PricePanel:
    base = root.resolve()
    manifest_binding = lock.get("snapshot_manifest")
    _verify_binding(base, manifest_binding)
    manifest = _load_snapshot_manifest(base, verify_files=True)
    manifest_path = base / SNAPSHOT_MANIFEST_PATH
    fields: dict[str, dict[str, pd.Series]] = {
        "open": {},
        "low": {},
        "close": {},
        "volume": {},
    }
    indices: list[set[pd.Timestamp]] = []
    by_symbol = {str(item["symbol"]): item for item in manifest["items"]}
    for symbol in UNIVERSE:
        item = by_symbol[symbol]
        path = _regular_in_root(base, manifest_path.parent / str(item["output_path"]))
        frame = _read_price_csv(path)
        indices.append(set(frame.index))
        for field in fields:
            fields[field][symbol] = frame[field]
    common = pd.DatetimeIndex(sorted(set.intersection(*indices)))
    if _canonical_hash(common.date.astype(str).tolist()) != manifest["common_sessions_sha256"]:
        raise ValueError("R11 snapshot common-session hash mismatch")
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
            "feed": "iex",
            "adjustment": "all",
            "symbol_count": len(UNIVERSE),
            "session_count": len(common),
            "first_session": common.min().date().isoformat(),
            "last_session": common.max().date().isoformat(),
            "snapshot_manifest_path": SNAPSHOT_MANIFEST_PATH.as_posix(),
            "snapshot_manifest_sha256": _sha256(manifest_path),
            "fallback_used": False,
        },
    )


def _read_price_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"R11 price file columns are incomplete: {path}")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    sessions = pd.DatetimeIndex(
        timestamps.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    )
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError(f"R11 price sessions are duplicate or unordered: {path}")
    output = frame.loc[:, ["open", "low", "close", "volume"]].apply(pd.to_numeric, errors="raise")
    output.index = sessions
    values = output.to_numpy(dtype=float)
    if (
        not np.isfinite(values).all()
        or (output[["open", "low", "close"]] <= 0).any().any()
        or (output["volume"] < 0).any()
    ):
        raise ValueError(f"R11 price values are invalid: {path}")
    return output.astype(float)


def _validate_panel_values(panels: dict[str, pd.DataFrame]) -> None:
    first = panels["open"]
    if (
        first.empty
        or list(first.columns) != list(UNIVERSE)
        or first.index.has_duplicates
        or not first.index.is_monotonic_increasing
    ):
        raise ValueError("R11 price panel identity is invalid")
    for field, frame in panels.items():
        if not frame.index.equals(first.index) or list(frame.columns) != list(UNIVERSE):
            raise ValueError(f"R11 price panel alignment failed: {field}")
        if not np.isfinite(frame.to_numpy()).all():
            raise ValueError(f"R11 price panel is nonfinite: {field}")
    if any((panels[field] <= 0).any().any() for field in ("open", "low", "close")):
        raise ValueError("R11 price panel contains nonpositive prices")
    if (panels["volume"] < 0).any().any():
        raise ValueError("R11 price panel contains negative volume")


def _preflight(root: Path) -> dict[str, Any]:
    base = root.resolve()
    lock_path = _regular_in_root(base, base / LOCK_PATH)
    lock = _load_json(lock_path)
    if (
        lock.get("iter_id") != ITER_ID
        or lock.get("status") != LOCK_STATUS
        or lock.get("one_shot") is not True
        or lock.get("historical_model_fit_at_lock") is not False
        or lock.get("broker_writes") is not False
        or lock.get("effective_trial_count") != EFFECTIVE_TRIAL_COUNT
        or lock.get("m01_features") != list(M01_FEATURES)
        or lock.get("m02_features") != list(M02_FEATURES)
        or lock.get("linear_baseline_contract") != LINEAR_BASELINE_CONTRACT
        or lock.get("role_gate_contract") != ROLE_GATE_CONTRACT
    ):
        raise ValueError("R11 historical evaluation lock identity mismatch")
    for group in ("contracts", "specs", "implementation"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R11 lock group is missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    _verify_binding(base, lock.get("snapshot_manifest"))
    specs = _load_and_validate_specs(base)
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R11 semantic spec changed after lock: {candidate_id}")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R11 dossier changed after lock: " + ", ".join(validation.blocked))
    return {
        "lock": lock,
        "lock_path": LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "snapshot_manifest_sha256": _sha256(base / SNAPSHOT_MANIFEST_PATH),
        "dossier_checked_at": validation.checked_at.isoformat(),
    }


def _regular_in_root(root: Path, path: Path) -> Path:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    cursor = candidate
    while cursor != base and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f"R11 bound path cannot use symlinks: {candidate}")
        cursor = cursor.parent
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R11 bound path escapes the project root: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"R11 bound path is not a regular file: {candidate}")
    return resolved


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = _regular_in_root(root, path)
    return {
        "path": _relpath(resolved, root),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _verify_binding(root: Path, binding: Any) -> Path:
    if not isinstance(binding, dict):
        raise ValueError("R11 file binding is malformed")
    path = _regular_in_root(root, root / str(binding.get("path") or ""))
    if _sha256(path) != binding.get("sha256") or path.stat().st_size != binding.get("size_bytes"):
        raise ValueError(f"R11 file binding changed: {binding.get('path')}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R11 JSON artifact must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def slice_price_panel(panel: R11PricePanel, *, end: str) -> R11PricePanel:
    selected = panel.open.index <= pd.Timestamp(end)
    if not selected.any():
        raise ValueError("R11 panel slice is empty")
    frames = {
        name: getattr(panel, name).loc[selected].copy()
        for name in ("open", "low", "close", "volume")
    }
    metadata = {
        **panel.metadata,
        "session_count": len(frames["open"]),
        "first_session": frames["open"].index.min().date().isoformat(),
        "last_session": frames["open"].index.max().date().isoformat(),
    }
    return R11PricePanel(metadata=metadata, **frames)


def build_d01_targets(
    panel: R11PricePanel,
    spec: StrategySpec,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    label = spec.portfolio.selected_route_label
    if not label:
        raise ValueError("R11D01 selected route is missing")
    params = hybrid_params_from_label(label)
    dates = panel.open.index.date.astype(str).tolist()
    frame = pd.DataFrame({"date": dates})
    timestamps = panel.open.index.tz_localize("America/New_York").tz_convert("UTC")
    for symbol in UNIVERSE:
        frame[f"{symbol}_timestamp"] = timestamps
        frame[f"{symbol}_open"] = panel.open[symbol].to_numpy(dtype=float)
        frame[f"{symbol}_close"] = panel.close[symbol].to_numpy(dtype=float)
    frame["timestamp"] = frame["QQQ_timestamp"]
    dataset = RouterFrameDataset(
        symbols=list(UNIVERSE),
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
        dates=dates,
        frame=frame,
        data_profile=panel.metadata,
    )
    start_index = max(_effective_lookback(params), 1)
    rows: list[pd.Series] = []
    sessions: list[pd.Timestamp] = []
    records: list[dict[str, Any]] = []
    for index in range(start_index, len(dates)):
        snapshot = hybrid_target_weight_snapshot(spec, dataset, params, index)
        weights = pd.Series(0.0, index=panel.open.columns, dtype=float)
        for symbol, weight in snapshot.weights.items():
            weights[symbol] = float(weight)
        gross = float(weights.sum())
        if (
            not np.isfinite(weights.to_numpy()).all()
            or (weights < -1e-12).any()
            or gross > 0.8 + 1e-10
        ):
            raise ValueError("R11D01 target violates the frozen risk budget")
        execution_session = panel.open.index[index]
        decision_session = panel.open.index[index - 1]
        rows.append(weights)
        sessions.append(execution_session)
        payload_weights = {symbol: float(weights[symbol]) for symbol in UNIVERSE}
        records.append(
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "candidate_id": "R11D01",
                "decision_session": decision_session.date().isoformat(),
                "execution_session": execution_session.date().isoformat(),
                "selected_symbols": [
                    symbol for symbol in UNIVERSE if payload_weights[symbol] > 1e-12
                ],
                "state": snapshot.state,
                "weights": payload_weights,
                "target_sha256": _canonical_hash(payload_weights),
                "broker_writes": False,
            }
        )
    targets = pd.DataFrame(rows, index=pd.DatetimeIndex(sessions), columns=panel.open.columns)
    if targets.empty:
        raise ValueError("R11D01 produced no targets")
    return targets.astype(float), records


def build_price_feature_dataset(panel: R11PricePanel) -> pd.DataFrame:
    closes = panel.close
    returns = closes.pct_change(fill_method=None)
    raw = {
        "momentum_5": closes / closes.shift(5) - 1.0,
        "momentum_20": closes / closes.shift(20) - 1.0,
        "momentum_60": closes / closes.shift(60) - 1.0,
        "trend_gap_50": closes / closes.rolling(50, min_periods=50).mean() - 1.0,
        "trend_gap_200": closes / closes.rolling(200, min_periods=200).mean() - 1.0,
        "realized_volatility_10": returns.rolling(10, min_periods=10).std(ddof=0),
        "realized_volatility_20": returns.rolling(20, min_periods=20).std(ddof=0),
        "drawdown_10": closes / closes.rolling(10, min_periods=10).max() - 1.0,
        "drawdown_20": closes / closes.rolling(20, min_periods=20).max() - 1.0,
        "drawdown_63": closes / closes.rolling(63, min_periods=63).max() - 1.0,
    }
    rows: list[dict[str, Any]] = []
    sessions = closes.index
    cost_rate = COST_VIEWS["primary_20bps"] / 10_000.0
    for decision_position, execution_position in scheduled_positions(sessions):
        decision_session = sessions[decision_position]
        values = {
            name: frame.loc[decision_session, list(RANKABLE_SYMBOLS)].astype(float)
            for name, frame in raw.items()
        }
        if any(not np.isfinite(item.to_numpy()).all() for item in values.values()):
            continue
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
                    raw["realized_volatility_20"].at[decision_session, symbol]
                ),
            }
            row.update({name: float(values[name][symbol]) for name in raw})
            if label_available:
                entry = float(
                    panel.open.iat[execution_position, panel.open.columns.get_loc(symbol)]
                )
                terminal = float(
                    panel.open.iat[label_end_position, panel.open.columns.get_loc(symbol)]
                )
                lows = panel.low.iloc[execution_position : label_end_position + 1][symbol]
                path_drawdown = float((lows / entry - 1.0).min())
                net_return = terminal / entry * (1.0 - cost_rate) ** 2 - 1.0
                row.update(
                    {
                        "net_forward_return_5": net_return,
                        "max_open_path_drawdown_5": path_drawdown,
                        "path_survival_label": int(net_return >= 0.0 and path_drawdown >= -0.08),
                    }
                )
            else:
                row.update(
                    {
                        "net_forward_return_5": None,
                        "max_open_path_drawdown_5": None,
                        "path_survival_label": None,
                    }
                )
            rows.append(row)
    dataset = pd.DataFrame(rows).sort_values(["decision_position", "symbol"]).reset_index(drop=True)
    if dataset.empty:
        raise ValueError("R11 price feature dataset is empty")
    feature_names = sorted(set(M01_FEATURES) | set(M02_FEATURES))
    feature_values = dataset.loc[:, feature_names].to_numpy(dtype=float)
    if not np.isfinite(feature_values).all():
        raise ValueError("R11 price feature dataset contains nonfinite values")
    return dataset


def scheduled_positions(index: pd.DatetimeIndex) -> list[tuple[int, int]]:
    return [
        (position, position + 1)
        for position in range(len(index) - 1)
        if index[position + 1].weekday() in {0, 2, 4}
    ]


def development_folds(index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    selected = index[index <= pd.Timestamp(DEVELOPMENT_END)]
    if len(selected) != 1091:
        raise ValueError("R11 development sessions no longer match the preregistered capacity")
    minimum_train = 756
    purge = 10
    fold_intervals = 81
    cursor = minimum_train + purge
    if len(selected) - 1 - cursor != 4 * fold_intervals:
        raise ValueError("R11 development fold arithmetic changed")
    folds = []
    for fold_number in range(1, 5):
        end_position = cursor + fold_intervals
        train_end_position = cursor - purge - 1
        folds.append(
            {
                "fold_id": f"F{fold_number}",
                "train_start": selected[0].date().isoformat(),
                "train_end": selected[train_end_position].date().isoformat(),
                "purge_sessions": purge,
                "embargo_sessions": 10,
                "test_start": selected[cursor].date().isoformat(),
                "test_end": selected[end_position].date().isoformat(),
                "test_interval_count": fold_intervals,
                "fit_from_scratch": True,
            }
        )
        cursor = end_position
    return folds


def training_rows_for_prediction(
    dataset: pd.DataFrame,
    *,
    decision_position: int,
    spec: StrategySpec,
    label_name: str,
) -> pd.DataFrame:
    if spec.model is None:
        raise ValueError("R11 model config is missing")
    lower = decision_position - int(spec.model.training.window_bars)
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
        raise AssertionError("R11 embargo filtering failed")
    return rows


def build_segment_targets(
    dataset: pd.DataFrame,
    panel: R11PricePanel,
    *,
    segment_id: str,
    start_session: str,
    end_session: str,
    specs: dict[str, StrategySpec],
    d01_targets: pd.DataFrame,
    provenance: dict[str, str],
) -> SegmentResult:
    points = dataset[
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
    points = points.drop_duplicates().sort_values("execution_position")
    if points.empty:
        raise ValueError(f"R11 segment has no prediction points: {segment_id}")

    target_rows: dict[str, list[pd.Series]] = {candidate_id: [] for candidate_id in TARGET_IDS}
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
            raise ValueError(f"R11 model symbol coverage failed: {decision_session}")
        if last_fit_position is None or decision_position - last_fit_position >= 5:
            fitted, records = _fit_model_family(
                dataset,
                current,
                decision_position=decision_position,
                segment_id=segment_id,
                specs=specs,
                provenance=provenance,
            )
            model_records.extend(records)
            last_fit_position = decision_position

        predictions: dict[str, pd.Series] = {}
        for candidate_id in MODEL_IDS:
            model = fitted[candidate_id]
            current_x = current.loc[:, list(model.feature_names)].astype(float)
            values = _predict(model, current_x)
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
            raise ValueError(f"R11D01 fallback target is missing: {execution_session}")
        fallback = d01_targets.loc[execution_timestamp].astype(float)
        m01 = risk_budget_target(
            predictions["R11M01"],
            current,
            columns=panel.open.columns,
            gross_budget=0.8,
            max_symbols=3,
        )
        m01_linear = risk_budget_target(
            predictions["R11M01_LINEAR"],
            current,
            columns=panel.open.columns,
            gross_budget=0.8,
            max_symbols=3,
        )
        if not np.isfinite(m01.to_numpy()).all():
            m01 = fallback.copy()
        if not np.isfinite(m01_linear.to_numpy()).all():
            m01_linear = fallback.copy()
        m02 = apply_survival_gate(
            m01,
            predictions["R11M02"],
            threshold=0.55,
            reserve_symbol="BIL",
        )
        m02_linear = apply_survival_gate(
            m01,
            predictions["R11M02_LINEAR"],
            threshold=0.55,
            reserve_symbol="BIL",
        )
        targets = {
            "R11M01_LINEAR": m01_linear,
            "R11M01": m01,
            "R11M02_LINEAR": m02_linear,
            "R11M02": m02,
            "R11F01": m01.copy(),
        }
        target_index.append(execution_timestamp)
        for candidate_id, target in targets.items():
            target_rows[candidate_id].append(target)
            weights = {symbol: float(target[symbol]) for symbol in UNIVERSE}
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": [
                        symbol for symbol in RANKABLE_SYMBOLS if float(target[symbol]) > 1e-12
                    ],
                    "weights": weights,
                    "target_sha256": _canonical_hash(weights),
                    "model_id": (
                        fitted["R11M01"].model_id
                        if candidate_id == "R11F01"
                        else fitted[candidate_id].model_id
                    ),
                    "fallback_candidate_id": (
                        "R11M01"
                        if candidate_id in {"R11M02", "R11M02_LINEAR", "R11F01"}
                        else "R11D01"
                    ),
                    "fallback_applied": bool(target.equals(fallback)),
                    **provenance,
                }
            )
        m01_prediction = next(
            row
            for row in reversed(prediction_records)
            if row["candidate_id"] == "R11M01" and row["execution_session"] == execution_session
        )
        prediction_records.append(
            {
                **m01_prediction,
                "candidate_id": "R11F01",
                "fallback_source_candidate_id": "R11M01",
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
                    "lgbm_probability": float(predictions["R11M02"][symbol]),
                    "linear_probability": float(predictions["R11M02_LINEAR"][symbol]),
                    "training_base_probability": float(fitted["R11M02"].training_label_mean),
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
        _validate_model_targets(frame, candidate_id=candidate_id)
    if not frames["R11F01"].equals(frames["R11M01"]):
        raise ValueError("R11F01 targets differ from R11M01")
    return SegmentResult(
        targets=frames,
        target_records=target_records,
        model_records=model_records,
        prediction_records=prediction_records,
        calibration_records=calibration_records,
    )


def risk_budget_target(
    scores: pd.Series,
    current: pd.DataFrame,
    *,
    columns: pd.Index,
    gross_budget: float,
    max_symbols: int,
) -> pd.Series:
    if set(scores.index) != set(RANKABLE_SYMBOLS) or not np.isfinite(scores.to_numpy()).all():
        raise ValueError("R11 ranking scores are incomplete")
    selected = sorted(scores.index, key=lambda symbol: (-float(scores[symbol]), str(symbol)))[
        :max_symbols
    ]
    ranks = scores.rank(method="average", pct=True)
    volatility = current.set_index("symbol")["raw_realized_volatility_20"].astype(float)
    raw = {
        symbol: max(float(ranks[symbol]), 1.0 / len(RANKABLE_SYMBOLS))
        / max(float(volatility[symbol]), 1e-6)
        for symbol in selected
    }
    if not all(math.isfinite(value) and value > 0 for value in raw.values()):
        raise ValueError("R11 risk budget is invalid")
    total = math.fsum(raw.values())
    target = pd.Series(0.0, index=columns, dtype=float)
    for symbol, value in raw.items():
        target[symbol] = gross_budget * value / total
    target["BIL"] = 1.0 - float(target.sum())
    _validate_model_targets(pd.DataFrame([target]), candidate_id="R11_risk_budget")
    return target


def apply_survival_gate(
    base_target: pd.Series,
    probabilities: pd.Series,
    *,
    threshold: float,
    reserve_symbol: str,
) -> pd.Series:
    if set(probabilities.index) != set(RANKABLE_SYMBOLS):
        raise ValueError("R11 survival probabilities are incomplete")
    target = base_target.astype(float).copy()
    for symbol in RANKABLE_SYMBOLS:
        if target[symbol] > 0 and float(probabilities[symbol]) < threshold:
            target[reserve_symbol] += target[symbol]
            target[symbol] = 0.0
    if not np.isclose(float(target.sum()), 1.0, atol=1e-12):
        raise ValueError("R11 survival gate violates capital conservation")
    return target


def _fit_model_family(
    dataset: pd.DataFrame,
    current: pd.DataFrame,
    *,
    decision_position: int,
    segment_id: str,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str],
) -> tuple[dict[str, FittedModel], list[dict[str, Any]]]:
    definitions = {
        "R11M01_LINEAR": (
            specs["R11M01"],
            "net_forward_return_5",
            M01_FEATURES,
            True,
        ),
        "R11M01": (specs["R11M01"], "net_forward_return_5", M01_FEATURES, False),
        "R11M02_LINEAR": (
            specs["R11M02"],
            "path_survival_label",
            M02_FEATURES,
            True,
        ),
        "R11M02": (specs["R11M02"], "path_survival_label", M02_FEATURES, False),
    }
    output: dict[str, FittedModel] = {}
    records: list[dict[str, Any]] = []
    for candidate_id, (spec, label_name, features, linear) in definitions.items():
        train = training_rows_for_prediction(
            dataset,
            decision_position=decision_position,
            spec=spec,
            label_name=label_name,
        )
        minimum_rows = max(80, 2 * int(spec.model.hyperparameters["min_child_samples"]))
        if len(train) < minimum_rows:
            raise ValueError(f"R11 has insufficient training rows: {candidate_id}")
        if "M02" in candidate_id and train[label_name].nunique() < 2:
            raise ValueError(f"R11 classifier has one training class: {candidate_id}")
        estimator, resolved = _make_estimator(spec, candidate_id=candidate_id, linear=linear)
        train_x = train.loc[:, list(features)].astype(float)
        train_y = train[label_name].astype(float)
        estimator.fit(train_x, train_y)
        fitted_sha = _fitted_model_hash(estimator, candidate_id)
        record = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "segment_id": segment_id,
            "candidate_id": candidate_id,
            "strategy_name": spec.name,
            "spec_hash": strategy_content_hash(spec),
            "decision_session": str(current["decision_session"].iloc[0]),
            "model_kind": resolved["model_kind"],
            "feature_names": list(features),
            "label_name": label_name,
            "training_row_count": len(train),
            "training_decision_start": str(train["decision_session"].min()),
            "training_decision_end": str(train["decision_session"].max()),
            "training_label_terminal_end": str(train["label_end_session"].max()),
            "training_data_sha256": _frame_hash(train, [*features, label_name]),
            "resolved_model_parameters": resolved,
            "fitted_model_sha256": fitted_sha,
            "training_label_mean": float(train_y.mean()),
            **provenance,
        }
        record["model_id"] = _canonical_hash(record)
        output[candidate_id] = FittedModel(
            candidate_id=candidate_id,
            model_id=record["model_id"],
            feature_names=features,
            estimator=estimator,
            training_label_mean=float(train_y.mean()),
            record=record,
        )
        records.append(record)
    return output, records


def _make_estimator(
    spec: StrategySpec,
    *,
    candidate_id: str,
    linear: bool,
) -> tuple[Any, dict[str, Any]]:
    assert spec.model is not None
    if linear and candidate_id == "R11M01_LINEAR":
        estimator = Pipeline(
            [("scale", StandardScaler()), ("model", Ridge(alpha=1.0, fit_intercept=True))]
        )
        return estimator, {"model_kind": "ridge", **LINEAR_BASELINE_CONTRACT[candidate_id]}
    if linear and candidate_id == "R11M02_LINEAR":
        estimator = Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        C=1.0,
                        penalty="l2",
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
    raise ValueError(f"R11 unsupported model kind: {spec.model.kind}")


def _predict(model: FittedModel, current_x: pd.DataFrame) -> np.ndarray:
    if "M02" in model.candidate_id:
        values = np.asarray(model.estimator.predict_proba(current_x)[:, 1], dtype=float)
    else:
        values = np.asarray(model.estimator.predict(current_x), dtype=float)
    if values.shape != (len(current_x),) or not np.isfinite(values).all():
        raise ValueError(f"R11 model prediction is invalid: {model.candidate_id}")
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
        "segment_id": segment_id,
        "candidate_id": model.candidate_id,
        "model_id": model.model_id,
        "decision_session": decision_session,
        "execution_session": execution_session,
        "prediction_feature_sha256": _frame_hash(current, list(model.feature_names)),
        "predictions": rows,
        "prediction_sha256": _canonical_hash(rows),
        **provenance,
    }


def _fitted_model_hash(estimator: Any, candidate_id: str) -> str:
    if candidate_id in {"R11M01", "R11M02"}:
        return hashlib.sha256(estimator.booster_.model_to_string().encode("utf-8")).hexdigest()
    scale = estimator.named_steps["scale"]
    model = estimator.named_steps["model"]
    payload = {
        "scale_mean": scale.mean_.tolist(),
        "scale_scale": scale.scale_.tolist(),
        "coef": np.asarray(model.coef_, dtype=float).tolist(),
        "intercept": np.asarray(model.intercept_, dtype=float).reshape(-1).tolist(),
    }
    return _canonical_hash(payload)


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


def _prior_scheduled_session(dataset: pd.DataFrame, start_session: str) -> str:
    sessions = sorted(set(map(str, dataset["execution_session"])))
    prior = [session for session in sessions if session <= start_session]
    if not prior:
        raise ValueError("R11 has no scheduled target before the segment start")
    return prior[-1]


def _validate_model_targets(targets: pd.DataFrame, *, candidate_id: str) -> None:
    if (
        targets.empty
        or list(targets.columns) != list(UNIVERSE)
        or targets.index.has_duplicates
        or not targets.index.is_monotonic_increasing
        or not np.isfinite(targets.to_numpy()).all()
        or (targets.to_numpy() < -1e-12).any()
        or not np.allclose(targets.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0)
    ):
        raise ValueError(f"R11 model target contract failed: {candidate_id}")


def run_pit_semantic_theme_r11(root: Path) -> R11EvaluationResult:
    base = root.resolve()
    destination = base / OUTPUT_DIR
    if destination.exists():
        raise ValueError("R11 historical evaluation is one-shot and already exists")
    staging = destination.with_name(
        f"{destination.name}.staging-{os.getpid()}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    )
    if staging.exists() or any((base / ITERATION_DIR).glob("historical-evaluation.staging-*")):
        raise ValueError("R11 has unresolved historical-evaluation staging state")

    preflight = _preflight(base)
    specs = _load_and_validate_specs(base)
    full_panel = load_r11_price_panel(base, preflight["lock"])
    development_panel = slice_price_panel(full_panel, end=DEVELOPMENT_END)
    folds = development_folds(development_panel.open.index)
    dataset = build_price_feature_dataset(development_panel)
    d01_targets, d01_records = build_d01_targets(development_panel, specs["R11D01"])
    provenance = {
        "snapshot_manifest_sha256": preflight["snapshot_manifest_sha256"],
        "historical_evaluation_lock_sha256": preflight["lock_sha256"],
        "feature_contract_sha256": _sha256(base / ITERATION_DIR / "feature-contract.json"),
        "label_contract_sha256": _sha256(base / ITERATION_DIR / "label-contract.json"),
        "validation_contract_sha256": _sha256(base / ITERATION_DIR / "validation-contract.json"),
    }

    segments = [
        {
            "segment_id": str(fold["fold_id"]),
            "start": str(fold["test_start"]),
            "end": str(fold["test_end"]),
        }
        for fold in folds
    ]
    segment_results: dict[str, SegmentResult] = {}
    target_records: list[dict[str, Any]] = list(d01_records)
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    calibration_records: list[dict[str, Any]] = []
    for segment in segments:
        result = build_segment_targets(
            dataset,
            development_panel,
            segment_id=segment["segment_id"],
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
            segment_results,
            segments,
            candidate_id=candidate_id,
            columns=development_panel.open.columns,
        )
        for candidate_id in TARGET_IDS
    }
    if not aggregate_targets["R11F01"].equals(aggregate_targets["R11M01"]):
        raise ValueError("R11F01 aggregate targets differ from R11M01")
    _validate_prediction_identity(prediction_records)

    development_start = pd.Timestamp(folds[0]["test_start"])
    development_end = pd.Timestamp(folds[-1]["test_end"])
    candidate_targets = {"R11D01": d01_targets, **aggregate_targets}
    candidate_payloads, development_returns = _evaluate_candidate_window(
        development_panel.open,
        candidate_targets,
        specs=specs,
        start=development_start,
        end=development_end,
        window_name="development_oos",
    )
    fold_payloads = _evaluate_folds(
        development_panel.open,
        segment_results,
        folds=folds,
        d01_targets=d01_targets,
    )
    for candidate_id, rows in fold_payloads.items():
        candidate_payloads[candidate_id]["folds"] = rows
    benchmarks = {
        "development_oos": benchmark_family(
            development_panel.open,
            start=development_start,
            end=development_end,
        )
    }
    pbo = cscv_probability_backtest_overfitting(
        {candidate_id: development_returns[candidate_id] for candidate_id in SELECTION_IDS},
        block_count=8,
    )
    calibration = calibration_payload(calibration_records, folds)
    role_gates = role_gate_payload(candidate_payloads, calibration)
    qqq_metrics = benchmarks["development_oos"]["QQQ_buy_hold"]["cost_views"]["primary_20bps"][
        "with_terminal"
    ]
    tqqq_metrics = benchmarks["development_oos"]["TQQQ_buy_hold"]["cost_views"]["primary_20bps"][
        "with_terminal"
    ]
    for candidate_id in SELECTION_IDS:
        candidate = candidate_payloads[candidate_id]
        metrics = candidate["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
        stress = candidate["windows"]["development_oos"]["severe_40bps"]["with_terminal"]
        positive_folds = sum(float(row["qqq_cagr_lift"]) > 0 for row in candidate["folds"])
        dsr = deflated_sharpe_probability(development_returns[candidate_id], EFFECTIVE_TRIAL_COUNT)
        gates = family_gates(
            metrics=metrics,
            stress_metrics=stress,
            qqq_metrics=qqq_metrics,
            tqqq_metrics=tqqq_metrics,
            positive_lift_folds=positive_folds,
            dsr=dsr,
            pbo=pbo,
        )
        reserves = tier0_reserve_gates(metrics, qqq_metrics)
        candidate.update(
            {
                "positive_qqq_lift_fold_count": positive_folds,
                "deflated_sharpe": dsr,
                "family_gates": gates,
                "role_gate": role_gates[candidate_id],
                "research_pass": bool(
                    all(row["pass"] for row in gates) and role_gates[candidate_id]["pass"]
                ),
                "tier0_reserve_gates": reserves,
                "tier0_reserve_pass": bool(
                    all(row["pass"] for row in reserves) and role_gates[candidate_id]["pass"]
                ),
            }
        )
    for candidate_id in ("R11M01_LINEAR", "R11M02_LINEAR", "R11F01"):
        candidate_payloads[candidate_id].update(
            {
                "selection_prohibited": True,
                "research_pass": False,
                "tier0_reserve_pass": False,
                "role_gate": role_gates.get(candidate_id),
            }
        )

    selected_research = [
        candidate_id
        for candidate_id in SELECTION_IDS
        if candidate_payloads[candidate_id]["research_pass"]
    ]
    selected_tier0 = [
        candidate_id
        for candidate_id in SELECTION_IDS
        if candidate_payloads[candidate_id]["tier0_reserve_pass"]
    ]
    transfer_payload: dict[str, Any] = {
        "status": "not_accessed_development_gate_not_met",
        "access_count": 0,
        "minimum_required_sessions": 126,
        "available_sessions": 230,
    }
    if selected_research:
        transfer_result = _evaluate_transfer(
            full_panel,
            specs=specs,
            provenance=provenance,
        )
        transfer_payload = transfer_result["summary"]
        benchmarks["diagnostic_transfer"] = transfer_result["benchmarks"]
        for candidate_id, windows in transfer_result["candidate_windows"].items():
            candidate_payloads[candidate_id]["windows"].update(windows)
        target_records.extend(transfer_result["target_records"])
        model_records.extend(transfer_result["model_records"])
        prediction_records.extend(transfer_result["prediction_records"])
        calibration_records.extend(transfer_result["calibration_records"])

    workflow_checks = {
        "prebacktest_dossier_pass": True,
        "snapshot_bound": preflight["snapshot_manifest_sha256"]
        == full_panel.metadata["snapshot_manifest_sha256"],
        "development_sessions_exact": len(development_panel.open) == 1091,
        "four_folds_of_81_intervals": [row["test_interval_count"] for row in folds]
        == [81, 81, 81, 81],
        "fold_local_models_fit_from_scratch": all(row["fit_from_scratch"] for row in folds),
        "f01_target_identity": aggregate_targets["R11F01"].equals(aggregate_targets["R11M01"]),
        "f01_prediction_identity": _prediction_identity_pass(prediction_records),
        "capital_conservation": all(
            np.allclose(frame.sum(axis=1).to_numpy(), 1.0, atol=1e-10, rtol=0)
            for frame in aggregate_targets.values()
        ),
        "semantic_historical_paths_skipped": True,
        "order_authority_false": True,
        "broker_writes_false": True,
    }
    workflow_pass = all(workflow_checks.values())
    if not workflow_pass:
        selected_research = []
        selected_tier0 = []
    decision = (
        "continue_to_broker_free_tier0"
        if selected_research
        else "continue_to_broker_free_tier0_reserve"
        if selected_tier0
        else "stop_historical_price_candidates"
    )

    staging.mkdir(parents=True, exist_ok=False)
    try:
        target_ledger_path = staging / "target-ledger.jsonl"
        model_ledger_path = staging / "model-ledger.jsonl"
        prediction_ledger_path = staging / "prediction-ledger.jsonl"
        trial_ledger_path = staging / "trial-ledger.jsonl"
        fold_path = staging / "fold-results.json"
        benchmark_path = staging / "benchmark-results.json"
        calibration_path = staging / "calibration.json"
        provenance_path = staging / "model-provenance.json"
        _write_jsonl(target_ledger_path, target_records)
        _write_jsonl(model_ledger_path, model_records)
        _write_jsonl(prediction_ledger_path, prediction_records)
        _write_jsonl(
            trial_ledger_path,
            [
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "candidate_id": candidate_id,
                    "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
                    "research_pass": candidate.get("research_pass", False),
                    "tier0_reserve_pass": candidate.get("tier0_reserve_pass", False),
                    "windows": candidate["windows"],
                    "folds": candidate.get("folds", []),
                }
                for candidate_id, candidate in candidate_payloads.items()
            ],
        )
        write_json(
            fold_path,
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "folds": folds,
                "candidate_results": fold_payloads,
                "pbo": pbo,
            },
        )
        write_json(
            benchmark_path,
            {"schema_version": 1, "iter_id": ITER_ID, "benchmarks": benchmarks},
        )
        write_json(calibration_path, calibration)
        model_provenance = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "status": "fold_local_historical_models_not_reusable_deployed_state",
            **provenance,
            "model_ledger_sha256": _sha256(model_ledger_path),
            "prediction_ledger_sha256": _sha256(prediction_ledger_path),
            "model_count": len(model_records),
            "prediction_count": len(prediction_records),
            "serialized_estimator_reuse_allowed": False,
            "broker_writes": False,
        }
        write_json(provenance_path, model_provenance)
        payload = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "report_type": "pit_semantic_theme_r11_historical_price_evaluation",
            "generated_at": datetime.now(UTC).isoformat(),
            "decision": decision,
            "workflow_pass": workflow_pass,
            "research_pass": bool(selected_research),
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "order_authority": False,
            "broker_writes": False,
            "selected_research_candidate_ids": selected_research,
            "selected_tier0_reserve_candidate_ids": selected_tier0,
            "historical_semantic_paths": {
                "candidate_ids": ["R11D02", "R11L01", "R11C01", "R11P01"],
                "status": "dependency_skipped_forward_only",
                "historical_alpha_credit": False,
            },
            "preflight": preflight,
            "data": full_panel.metadata,
            "development_window": {
                "start": development_start.date().isoformat(),
                "end": development_end.date().isoformat(),
                "market_interval_count": int(
                    (development_panel.open.index >= development_start).sum() - 1
                ),
                "scope": "four_fold_matched_out_of_sample_only",
            },
            "transfer_holdout": transfer_payload,
            "cost_views_bps": COST_VIEWS,
            "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
            "linear_baseline_contract": LINEAR_BASELINE_CONTRACT,
            "role_gate_contract": ROLE_GATE_CONTRACT,
            "workflow_checks": workflow_checks,
            "candidates": candidate_payloads,
            "benchmarks": benchmarks,
            "pbo": pbo,
            "calibration": calibration,
            "model_provenance": model_provenance,
            "artifacts": {
                "target_ledger_sha256": _sha256(target_ledger_path),
                "model_ledger_sha256": _sha256(model_ledger_path),
                "prediction_ledger_sha256": _sha256(prediction_ledger_path),
                "trial_ledger_sha256": _sha256(trial_ledger_path),
                "fold_results_sha256": _sha256(fold_path),
                "benchmark_results_sha256": _sha256(benchmark_path),
                "calibration_sha256": _sha256(calibration_path),
                "model_provenance_sha256": _sha256(provenance_path),
            },
            "next_stage": {
                "broker_free_tier0_allowed_candidate_ids": selected_tier0,
                "forward_semantic_collection_allowed": workflow_pass,
                "historical_semantic_replay_allowed": False,
                "paper_orders_allowed": False,
            },
        }
        evaluation_path = staging / "evaluation-report.json"
        markdown_path = staging / "evaluation-report.md"
        write_json(evaluation_path, payload)
        markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    _write_forensics(base, payload)
    return R11EvaluationResult(
        evaluation_path=destination / "evaluation-report.json",
        trial_ledger_path=destination / "trial-ledger.jsonl",
        model_ledger_path=destination / "model-ledger.jsonl",
        prediction_ledger_path=destination / "prediction-ledger.jsonl",
        target_ledger_path=destination / "target-ledger.jsonl",
        payload=payload,
    )


def _evaluate_transfer(
    panel: R11PricePanel,
    *,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str],
) -> dict[str, Any]:
    dataset = build_price_feature_dataset(panel)
    d01_targets, d01_records = build_d01_targets(panel, specs["R11D01"])
    result = build_segment_targets(
        dataset,
        panel,
        segment_id="TRANSFER",
        start_session=TRANSFER_START,
        end_session=panel.open.index.max().date().isoformat(),
        specs=specs,
        d01_targets=d01_targets,
        provenance=provenance,
    )
    start = pd.Timestamp(TRANSFER_START)
    end = panel.open.index.max()
    targets = {"R11D01": d01_targets, **result.targets}
    candidate_payloads, _ = _evaluate_candidate_window(
        panel.open,
        targets,
        specs=specs,
        start=start,
        end=end,
        window_name="diagnostic_transfer",
    )
    candidate_windows = {
        candidate_id: payload["windows"] for candidate_id, payload in candidate_payloads.items()
    }
    return {
        "summary": {
            "status": "accessed_after_development_gate_pass",
            "access_count": 1,
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "market_interval_count": len(panel.open.loc[start:end]) - 1,
            "minimum_required_sessions": 126,
            "historical_holdout_is_forward_evidence": False,
        },
        "candidate_windows": candidate_windows,
        "benchmarks": benchmark_family(panel.open, start=start, end=end),
        "target_records": [row for row in d01_records if row["execution_session"] >= TRANSFER_START]
        + result.target_records,
        "model_records": result.model_records,
        "prediction_records": result.prediction_records,
        "calibration_records": result.calibration_records,
    }


def _evaluate_candidate_window(
    opens: pd.DataFrame,
    targets_by_id: dict[str, pd.DataFrame],
    *,
    specs: dict[str, StrategySpec],
    start: pd.Timestamp,
    end: pd.Timestamp,
    window_name: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, pd.Series]]:
    payloads: dict[str, dict[str, Any]] = {}
    returns: dict[str, pd.Series] = {}
    for candidate_id, targets in targets_by_id.items():
        cost_results, simulations = run_cost_views(opens, targets, start=start, end=end)
        returns[candidate_id] = _daily_returns(simulations["primary_20bps"], include_terminal=True)
        spec_candidate = candidate_id if candidate_id in specs else None
        payloads[candidate_id] = {
            "strategy_name": specs[spec_candidate].name if spec_candidate else candidate_id.lower(),
            "spec_hash": (strategy_content_hash(specs[spec_candidate]) if spec_candidate else None),
            "target_count": len(targets),
            "windows": {window_name: cost_results},
            "folds": [],
        }
    return payloads, returns


def run_cost_views(
    opens: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[dict[str, Any], dict[str, Any]]:
    results: dict[str, Any] = {}
    simulations: dict[str, Any] = {}
    for view_name, cost_bps in COST_VIEWS.items():
        simulation = simulate_target_portfolio(
            opens,
            targets,
            cost_bps=cost_bps,
            start=start,
            end=end,
            reserve_symbol="BIL",
        )
        simulations[view_name] = simulation
        results[view_name] = _simulation_metric_views(simulation, opens)
    return results, simulations


def benchmark_family(
    opens: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    definitions = {
        "TQQQ_buy_hold": {"TQQQ": 1.0},
        "QQQ_buy_hold": {"QQQ": 1.0},
        "SPY_buy_hold": {"SPY": 1.0},
        "BIL_buy_hold": {"BIL": 1.0},
        "equal_weight_execution_universe": {symbol: 1.0 / len(UNIVERSE) for symbol in UNIVERSE},
        "SMH_or_matched_theme_proxy": {"SMH": 1.0},
    }
    output: dict[str, Any] = {}
    for benchmark_id, weights in definitions.items():
        output[benchmark_id] = {
            "weights": weights,
            "cost_views": {
                view_name: _simulation_metric_views(
                    _simulate_static(
                        opens,
                        weights,
                        start=start,
                        end=end,
                        cost_bps=cost_bps,
                    ),
                    opens,
                )
                for view_name, cost_bps in COST_VIEWS.items()
            },
        }
    symbol_results = {
        symbol: {
            view_name: _simulation_metric_views(
                _simulate_static(
                    opens,
                    {symbol: 1.0},
                    start=start,
                    end=end,
                    cost_bps=cost_bps,
                ),
                opens,
            )
            for view_name, cost_bps in COST_VIEWS.items()
        }
        for symbol in UNIVERSE
    }
    best_symbol = max(
        UNIVERSE,
        key=lambda symbol: (
            symbol_results[symbol]["primary_20bps"]["with_terminal"]["cagr"],
            symbol,
        ),
    )
    output["ex_post_best_symbol"] = {
        "symbol": best_symbol,
        "selection_use": "report_only",
        "cost_views": symbol_results[best_symbol],
    }
    output["equal_weight_active_theme_when_available"] = {
        "status": "dependency_skipped_no_historical_PIT_semantic_theme",
        "selection_use": "not_available",
    }
    return output


def _evaluate_folds(
    opens: pd.DataFrame,
    segment_results: dict[str, SegmentResult],
    *,
    folds: list[dict[str, Any]],
    d01_targets: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    output = {candidate_id: [] for candidate_id in ("R11D01", *TARGET_IDS)}
    for fold in folds:
        fold_id = str(fold["fold_id"])
        start = pd.Timestamp(fold["test_start"])
        end = pd.Timestamp(fold["test_end"])
        targets = {"R11D01": d01_targets, **segment_results[fold_id].targets}
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


def calibration_payload(
    records: list[dict[str, Any]], folds: list[dict[str, Any]]
) -> dict[str, Any]:
    frame = pd.DataFrame(records)
    rows = {
        str(fold["fold_id"]): _calibration_metrics(
            frame[frame["segment_id"] == str(fold["fold_id"])]
        )
        for fold in folds
    }
    aggregate = _calibration_metrics(frame[frame["segment_id"].isin(rows)])
    return {
        "folds": rows,
        "aggregate": aggregate,
        "brier_winning_fold_count": sum(
            row["lgbm_brier"] < row["linear_brier"] and row["lgbm_brier"] < row["base_rate_brier"]
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
        "m01_selected_path_loss": (
            float(1.0 - selected["label"].mean()) if not selected.empty else 1.0
        ),
        "m02_accepted_path_loss": (
            float(1.0 - accepted["label"].mean()) if not accepted.empty else 1.0
        ),
        "m01_selected_count": len(selected),
        "m02_accepted_count": len(accepted),
    }


def role_gate_payload(
    candidates: dict[str, dict[str, Any]], calibration: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    m01_wins = 0
    path_wins = 0
    for index in range(4):
        m01 = candidates["R11M01"]["folds"][index]["metrics"]["with_terminal"]["cagr"]
        linear = candidates["R11M01_LINEAR"]["folds"][index]["metrics"]["with_terminal"]["cagr"]
        d01 = candidates["R11D01"]["folds"][index]["metrics"]["with_terminal"]["cagr"]
        m01_wins += int(m01 > max(linear, d01))
        row = calibration["folds"][f"F{index + 1}"]
        path_wins += int(row["m02_accepted_path_loss"] < row["m01_selected_path_loss"])
    m01_metrics = candidates["R11M01"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    d01_metrics = candidates["R11D01"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    m02_metrics = candidates["R11M02"]["windows"]["development_oos"]["primary_20bps"][
        "with_terminal"
    ]
    m01_exposure_ratio = m01_metrics["average_risk_asset_exposure"] / max(
        d01_metrics["average_risk_asset_exposure"], 1e-12
    )
    m02_exposure_ratio = m02_metrics["average_risk_asset_exposure"] / max(
        m01_metrics["average_risk_asset_exposure"], 1e-12
    )
    up_capture_retention = m02_metrics["tqqq_up_capture"] / max(
        m01_metrics["tqqq_up_capture"], 1e-12
    )
    m01_checks = {
        "fold_wins_vs_linear_and_D01": m01_wins
        >= ROLE_GATE_CONTRACT["M01_minimum_fold_wins_vs_linear_and_D01"],
        "exposure_ratio_vs_D01": m01_exposure_ratio
        >= ROLE_GATE_CONTRACT["M01_minimum_exposure_ratio_vs_D01"],
    }
    m02_checks = {
        "brier_winning_folds": calibration["brier_winning_fold_count"]
        >= ROLE_GATE_CONTRACT["M02_minimum_brier_wins_vs_linear_and_base_rate"],
        "path_loss_improvement_folds": path_wins
        >= ROLE_GATE_CONTRACT["M02_minimum_path_loss_improvement_folds"],
        "exposure_ratio_vs_M01": m02_exposure_ratio
        >= ROLE_GATE_CONTRACT["M02_minimum_exposure_ratio_vs_M01"],
        "up_capture_retention_vs_M01": up_capture_retention
        >= ROLE_GATE_CONTRACT["M02_minimum_up_capture_retention_vs_M01"],
        "drawdown_improvement": m02_metrics["max_drawdown"] > m01_metrics["max_drawdown"],
    }
    return {
        "R11D01": {"pass": True, "reason": "locked_deterministic_execution_baseline"},
        "R11M01": {
            "checks": m01_checks,
            "fold_wins_vs_linear_and_D01": m01_wins,
            "exposure_ratio_vs_D01": m01_exposure_ratio,
            "pass": all(m01_checks.values()),
        },
        "R11M02": {
            "checks": m02_checks,
            "brier_winning_fold_count": calibration["brier_winning_fold_count"],
            "path_loss_improvement_fold_count": path_wins,
            "exposure_ratio_vs_M01": m02_exposure_ratio,
            "up_capture_retention_vs_M01": up_capture_retention,
            "pass": all(m02_checks.values()),
        },
        "R11F01": {"pass": True, "reason": "exact_M01_identity_control"},
    }


def family_gates(
    *,
    metrics: dict[str, Any],
    stress_metrics: dict[str, Any],
    qqq_metrics: dict[str, Any],
    tqqq_metrics: dict[str, Any],
    positive_lift_folds: int,
    dsr: dict[str, Any],
    pbo: dict[str, Any],
) -> list[dict[str, Any]]:
    required_cagr = max(0.45, 0.85 * float(tqqq_metrics["cagr"]))
    return [
        _gate("net_CAGR", metrics["cagr"] >= required_cagr, required_cagr, metrics["cagr"]),
        _gate(
            "QQQ_CAGR_lift",
            metrics["cagr"] - qqq_metrics["cagr"] >= 0.08,
            0.08,
            metrics["cagr"] - qqq_metrics["cagr"],
        ),
        _gate(
            "maximum_drawdown",
            metrics["max_drawdown"] >= -0.65,
            -0.65,
            metrics["max_drawdown"],
        ),
        _gate(
            "annualized_sharpe_excess_BIL",
            metrics["annualized_sharpe_excess_BIL"] >= 0.80,
            0.80,
            metrics["annualized_sharpe_excess_BIL"],
        ),
        _gate("MAR", metrics["mar"] is not None and metrics["mar"] >= 0.40, 0.40, metrics["mar"]),
        _gate(
            "TQQQ_up_capture",
            metrics["tqqq_up_capture"] >= 0.80,
            0.80,
            metrics["tqqq_up_capture"],
        ),
        _gate(
            "TQQQ_down_capture",
            metrics["tqqq_down_capture"] <= 0.90,
            "<=0.90",
            metrics["tqqq_down_capture"],
        ),
        _gate("positive_QQQ_lift_folds", positive_lift_folds >= 3, 3, positive_lift_folds),
        _gate("DSR_probability", dsr["probability"] >= 0.75, 0.75, dsr["probability"]),
        _gate("PBO_probability", pbo["probability"] <= 0.40, "<=0.40", pbo["probability"]),
        _gate(
            "40bps_total_return",
            stress_metrics["total_return"] > 0,
            ">0",
            stress_metrics["total_return"],
        ),
    ]


def tier0_reserve_gates(
    metrics: dict[str, Any], qqq_metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        _gate("net_CAGR", metrics["cagr"] >= 0.30, 0.30, metrics["cagr"]),
        _gate(
            "QQQ_CAGR_lift",
            metrics["cagr"] - qqq_metrics["cagr"] >= 0.04,
            0.04,
            metrics["cagr"] - qqq_metrics["cagr"],
        ),
        _gate("20bps_total_return", metrics["total_return"] > 0, ">0", metrics["total_return"]),
        _gate(
            "maximum_drawdown",
            metrics["max_drawdown"] >= -0.65,
            -0.65,
            metrics["max_drawdown"],
        ),
    ]


def _gate(name: str, passed: bool, threshold: Any, value: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "threshold": threshold, "value": value}


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
            raise ValueError(f"R11 segment lacks a boundary target: {segment['segment_id']}")
        rows.append(prior.iloc[-1])
        sessions.append(start)
        for session, row in frame.loc[(frame.index > start) & (frame.index <= end)].iterrows():
            rows.append(row)
            sessions.append(pd.Timestamp(session))
    values = pd.DataFrame(rows, index=pd.DatetimeIndex(sessions), columns=columns)
    values = values[~values.index.duplicated(keep="last")].sort_index()
    _validate_model_targets(values, candidate_id=candidate_id)
    return values


def _validate_prediction_identity(records: list[dict[str, Any]]) -> None:
    if not _prediction_identity_pass(records):
        raise ValueError("R11F01 prediction hashes differ from R11M01")


def _prediction_identity_pass(records: list[dict[str, Any]]) -> bool:
    by_key = {
        (str(row["segment_id"]), str(row["execution_session"]), str(row["candidate_id"])): str(
            row["prediction_sha256"]
        )
        for row in records
        if row.get("candidate_id") in {"R11M01", "R11F01"}
    }
    sessions = {
        (segment, session) for segment, session, candidate_id in by_key if candidate_id == "R11M01"
    }
    return bool(sessions) and all(
        by_key.get((segment, session, "R11M01")) == by_key.get((segment, session, "R11F01"))
        for segment, session in sessions
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    )
    path.write_text(payload, encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PIT Semantic Theme R11 Historical Price Evaluation",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{str(payload['workflow_pass']).lower()}`",
        f"- Research pass: `{str(payload['research_pass']).lower()}`",
        "- LLM contribution pass: `false` (historical semantic paths were skipped)",
        "- Paper-ready pass: `false`",
        "- Broker writes: `false`",
        "",
        "| Candidate | CAGR | Sharpe excess BIL | Max drawdown | MAR | Up capture | "
        "Down capture | Research | Tier 0 |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|:---:|",
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["windows"]["development_oos"]["primary_20bps"]["with_terminal"]
        lines.append(
            f"| {candidate_id} | {metrics['cagr_pct']:.2f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['max_drawdown_pct']:.2f}% | "
            f"{metrics['mar'] if metrics['mar'] is not None else 0.0:.3f} | "
            f"{metrics['tqqq_up_capture']:.3f} | {metrics['tqqq_down_capture']:.3f} | "
            f"{str(candidate.get('research_pass', False)).lower()} | "
            f"{str(candidate.get('tier0_reserve_pass', False)).lower()} |"
        )
    tqqq = payload["benchmarks"]["development_oos"]["TQQQ_buy_hold"]["cost_views"]["primary_20bps"][
        "with_terminal"
    ]
    qqq = payload["benchmarks"]["development_oos"]["QQQ_buy_hold"]["cost_views"]["primary_20bps"][
        "with_terminal"
    ]
    lines.extend(
        [
            "",
            f"Matched TQQQ CAGR: `{tqqq['cagr_pct']:.2f}%`; matched QQQ CAGR: "
            f"`{qqq['cagr_pct']:.2f}%`.",
            "",
            "CAGR is geometric. The scored development window is the four preregistered 81-session "
            "OOS folds. Signals use completed closes and execute at the next regular-session open. "
            "Costs are charged on one-way target-weight turnover. Historical SEC/news/LLM paths "
            "were not replayed because immutable decision-time semantic packets do not exist.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_forensics(root: Path, payload: dict[str, Any]) -> None:
    output = root / "reports/harness/forensics"
    output.mkdir(parents=True, exist_ok=True)
    for candidate_id in SELECTION_IDS:
        strategy_name = payload["candidates"][candidate_id]["strategy_name"]
        metrics = payload["candidates"][candidate_id]["windows"]["development_oos"][
            "primary_20bps"
        ]["with_terminal"]
        evidence = {
            "strategy_name": strategy_name,
            "candidate_id": candidate_id,
            "lookahead_check": "pass",
            "future_leak_check": "pass",
            "overfit_risk": "high",
            "multiple_testing_count": EFFECTIVE_TRIAL_COUNT,
            "pbo_proxy": payload["pbo"]["probability"],
            "dsr_proxy": payload["candidates"][candidate_id]["deflated_sharpe"]["probability"],
            "sample_data_caveats": [
                "Alpaca IEX is not consolidated SIP",
                "historical prices are globally exposed development evidence",
                "no historical semantic PIT packets were admitted",
            ],
            "trade_count": metrics["nonzero_rebalance_count"],
            "trading_days": metrics["market_interval_count"],
            "capacity_assessment": (
                "ETF capacity is not established by this backtest; the planned Paper canary "
                "remains "
                "bounded to 1000 USD and 1% ADV safeguards."
            ),
            "short_sample": metrics["market_interval_count"] < 252,
            "conclusion": (
                "warning" if payload["candidates"][candidate_id].get("research_pass") else "blocked"
            ),
            "notes": (
                "The deterministic route inherits 660 prior candidates and the cumulative family "
                "trial count is 8038. Fold-local models use no warm start."
            ),
        }
        json_path = output / f"{strategy_name}-backtest-forensics.json"
        md_path = output / f"{strategy_name}-backtest-forensics.md"
        write_json(json_path, evidence)
        md_path.write_text(
            "\n".join(
                [
                    f"# Backtest Forensics: {strategy_name}",
                    "",
                    f"- Conclusion: `{evidence['conclusion']}`",
                    "- Lookahead: `pass`; future leak: `pass`.",
                    f"- Effective trial count: `{EFFECTIVE_TRIAL_COUNT}`; overfit risk: `high`.",
                    f"- DSR probability: `{evidence['dsr_proxy']:.6f}`; "
                    f"PBO: `{evidence['pbo_proxy']:.6f}`.",
                    "- Historical semantic data was not backfilled or credited.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
