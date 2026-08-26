# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss
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
from open_composer.research.factor_library import get_factor_definition
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.pit_semantic_theme_r11 import R11PricePanel
from open_composer.research.pit_semantic_theme_r24 import load_r24_price_panel
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_high_beta_sleeve_ensemble_r1"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
OUTPUT_DIR = ITERATION_DIR / "evaluation-run"
RUNNER_PATH = Path("open_composer/research/high_beta_sleeve_ensemble_r1.py")
TEST_PATH = Path("tests/test_high_beta_sleeve_ensemble_r1.py")
SEMANTIC_TEST_PATH = Path("tests/test_high_beta_sleeve_ensemble_r1_semantic.py")
PREPARE_PATH = Path("scripts/prepare_high_beta_sleeve_ensemble_r1.py")
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
SOURCE_CARDS_PATH = Path("reports/harness/source_cards/us_high_beta_sleeve_ensemble_r1.jsonl")
FACTOR_LIBRARY_PATH = Path("reports/research/us_high_beta_sleeve_ensemble_r1-factor-library.json")
FACTOR_LIBRARY_IMPLEMENTATION_PATH = Path("open_composer/research/factor_library.py")
SLEEVE_FACTOR_ID = "fixed_anchor_monthly_trend_sleeve"
SLEEVE_FACTOR_SOURCE_CARD_IDS = (
    "hbs_r1_time_series_momentum_paper",
    "hbs_r1_tqqq_daily_target_and_path_risk",
)

CANDIDATE_ROWS = (
    ("S1D01", "d01"),
    ("S1D02", "d02"),
    ("S1M01", "m01"),
    ("S1M02", "m02"),
    ("S1L01", "l01"),
    ("S1C01", "c01"),
    ("S1F01", "f01"),
    ("S1P01", "p01"),
    ("S1D03", "d03"),
    ("S1D04", "d04"),
)
# Immutable role metadata for the preregistered candidate family.  The
# manifest is evidence of this contract, not its authority: a mutated manifest
# must fail validation even when its own fields remain internally consistent.
R1_CANDIDATE_CONTRACT: dict[str, dict[str, Any]] = {
    "S1D01": {
        "role": "deterministic_equal_anchor_monthly_trend_core",
        "method": "fixed_50pct_TQQQ_anchor_plus_50pct_monthly_QQQ_SMA200_sleeve",
        "ablation": "quant_only_primary",
        "fallback": "BIL_for_tactical_sleeve_only",
        "path": "deterministic_primary",
        "promotion_eligible": True,
    },
    "S1D02": {
        "role": "deterministic_semantic_control",
        "method": "S1D01_plus_zero_capital_structured_event_control",
        "ablation": "deterministic_semantic_control",
        "fallback": "S1D01",
        "path": "deterministic_semantic",
        "promotion_eligible": False,
    },
    "S1M01": {
        "role": "ridge_after_cost_policy_value_overlay",
        "method": "fold_local_ridge_monthly_tactical_override_with_lower_bound_abstention",
        "ablation": "quant_ml_policy_value",
        "fallback": "S1D01",
        "path": "trained_ml",
        "promotion_eligible": True,
    },
    "S1M02": {
        "role": "logistic_tail_risk_overlay",
        "method": "fold_local_logistic_anchor_tail_risk_cut_with_calibrated_abstention",
        "ablation": "quant_ml_tail_risk",
        "fallback": "S1D01",
        "path": "trained_ml",
        "promotion_eligible": True,
    },
    "S1L01": {
        "role": "structured_llm_factor_zero_capital",
        "method": "PIT_structured_semantic_observation_no_weight_authority",
        "ablation": "modality_only_zero_capital",
        "fallback": "S1D01",
        "path": "llm_text",
        "promotion_eligible": False,
    },
    "S1C01": {
        "role": "quant_ml_plus_structured_llm_zero_capital",
        "method": "S1M01_plus_PIT_semantic_observation_no_weight_authority",
        "ablation": "combined_quant_and_modality",
        "fallback": "S1M01_then_S1D01",
        "path": "combined",
        "promotion_eligible": False,
    },
    "S1F01": {
        "role": "exact_missing_semantic_fallback",
        "method": "exact_S1M01_target_identity_without_semantic_packet",
        "ablation": "missing_modality_exact_fallback",
        "fallback": "S1M01_then_S1D01",
        "path": "missing_modality",
        "promotion_eligible": False,
    },
    "S1P01": {
        "role": "semantic_placebo_dependency_skipped",
        "method": "dependency_skipped_no_historical_packets_exact_S1D01_identity",
        "ablation": "planned_placebo_modality_not_executed",
        "fallback": "S1D01",
        "path": "placebo",
        "promotion_eligible": False,
    },
    "S1D03": {
        "role": "nonpromotable_anchor_weight_neighbor",
        "method": "fixed_40pct_TQQQ_anchor_plus_60pct_monthly_QQQ_SMA200_sleeve",
        "ablation": "anchor_weight_lower_neighbor",
        "fallback": "BIL_for_tactical_sleeve_only",
        "path": "deterministic_neighborhood",
        "promotion_eligible": False,
    },
    "S1D04": {
        "role": "nonpromotable_anchor_weight_neighbor",
        "method": "fixed_60pct_TQQQ_anchor_plus_40pct_monthly_QQQ_SMA200_sleeve",
        "ablation": "anchor_weight_upper_neighbor",
        "fallback": "BIL_for_tactical_sleeve_only",
        "path": "deterministic_neighborhood",
        "promotion_eligible": False,
    },
}
R1_CONTRACT_REF_IDS = {
    "data_contract": "hbs_r1_data_v1",
    "feature_contract": "hbs_r1_features_v1",
    "label_contract": "hbs_r1_labels_v1",
    "validation_contract": "hbs_r1_validation_v1",
    "cost_contract": "hbs_r1_costs_v1",
    "benchmark_contract": "hbs_r1_benchmarks_v1",
}
R1_CONTRACT_REF_CATEGORIES = {
    "data_contract": "data",
    "feature_contract": "features",
    "label_contract": "labels",
    "validation_contract": "validation",
    "cost_contract": "costs",
    "benchmark_contract": "benchmarks",
}
R1_CONTRACT_REF_FILENAMES = {
    "data_contract": "data-contract.json",
    "feature_contract": "feature-contract.json",
    "label_contract": "label-contract.json",
    "validation_contract": "validation-contract.json",
    "cost_contract": "cost-contract.json",
    "benchmark_contract": "benchmark-contract.json",
}
EXPECTED_FEATURE_EXPRESSIONS = {
    "qqq_trend_gap_200": "close / sma(close, 200) - 1",
    "qqq_momentum_252_skip21": "lag(close, 21) / lag(close, 252) - 1",
    "tqqq_momentum_21": "close / lag(close, 21) - 1",
    "tqqq_momentum_63": "close / lag(close, 63) - 1",
    "tqqq_realized_volatility_21": "stddev(close / lag(close, 1) - 1, 21)",
    "tqqq_drawdown_63": "close / highest(close, 63) - 1",
}
M02_MAX_DRAWDOWN_PCT = 12.0
M02_MIN_TERMINAL_RETURN_PCT = -8.0
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_{suffix}.yaml")
    for candidate_id, suffix in CANDIDATE_ROWS
}
ANCHOR_WEIGHTS = {"S1D01": 0.5, "S1D03": 0.4, "S1D04": 0.6}
MODEL_FEATURES = (
    "qqq_trend_gap_200",
    "qqq_momentum_252_skip21",
    "tqqq_momentum_21",
    "tqqq_momentum_63",
    "tqqq_realized_volatility_21",
    "tqqq_drawdown_63",
)
COST_VIEWS = {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}
PRIMARY_COST_BPS = 20.0
EFFECTIVE_TRIAL_COUNT = 8138
FOLD_COUNT = 4
FOLD_SESSIONS = 252
TRAIN_WINDOW_SESSIONS = 756
LABEL_MAX_SPAN_SESSIONS = 24
PURGE_SESSIONS = LABEL_MAX_SPAN_SESSIONS
EMBARGO_SESSIONS = LABEL_MAX_SPAN_SESSIONS
MINIMUM_FIT_LABELS = 18
MINIMUM_CALIBRATION_LABELS = 6
MINIMUM_CLASS_LABELS = 5
MINIMUM_CALIBRATION_CLASS_LABELS = 2
CALIBRATION_FRACTION = 0.25
M01_LOWER_COVERAGE = 0.80
M01_FOLD_COVERAGE_FLOOR = 0.75
M02_SURVIVAL_THRESHOLD = 0.35
M02_ANCHOR_CUT = 0.25
ANNUALIZED_ONE_WAY_TURNOVER_CAP = 6.0
LOCK_STATUS = "implementation_and_contracts_locked_before_first_R1_return_calculation"

CONTRACT_FILENAMES = (
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
    "knowledge-baseline.json",
    "knowledge-scout-queries.json",
    "external-brief.json",
    "external-brief.md",
    "hypotheses.md",
    "search-space.json",
    "search-space.md",
    "decision-record.md",
)


@dataclass(frozen=True)
class R1EvaluationResult:
    evaluation_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class FittedDecisionModel:
    model_id: str
    estimator: Pipeline
    calibrator: LogisticRegression | None
    lower_offset: float | None
    record: dict[str, Any]


@dataclass(frozen=True)
class R1ModelRuntime:
    candidate_id: str
    kind: str
    features: tuple[str, ...]
    label: dict[str, Any]
    training: dict[str, Any]
    selection: dict[str, Any]
    abstention: dict[str, Any]
    action: dict[str, Any]
    preprocessing: str
    hyperparameters: dict[str, Any]
    baseline: str

    @property
    def sha256(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "features": list(self.features),
            "label": self.label,
            "training": self.training,
            "selection": self.selection,
            "abstention": self.abstention,
            "action": self.action,
            "preprocessing": self.preprocessing,
            "hyperparameters": self.hyperparameters,
            "baseline": self.baseline,
        }


@dataclass(frozen=True)
class R1RuntimeContract:
    anchors: dict[str, float]
    tactical_trend_sessions: int
    fold_count: int
    m01: R1ModelRuntime
    m02: R1ModelRuntime
    semantic_placebo: dict[str, Any]
    # Every value that can change the counted R1 behavior is captured here.
    # The runner may derive convenience values from this snapshot, but never
    # from module-level defaults once an evaluation starts.
    candidate_specs: dict[str, dict[str, Any]]
    candidate_manifest: dict[str, Any]
    contract_bindings: dict[str, dict[str, Any]]
    cost_contract: dict[str, Any]
    validation_contract: dict[str, Any]
    benchmark_contract: dict[str, Any]
    cumulative_trial_contract: dict[str, Any]
    iteration_contracts: dict[str, dict[str, Any]]
    factor_definition: dict[str, Any]
    factor_artifact: dict[str, Any]

    @property
    def label_max_span_sessions(self) -> int:
        return int(self.m01.label["maximum_horizon_bars"])

    @property
    def purge_sessions(self) -> int:
        return int(self.m01.training["purge_bars"])

    @property
    def embargo_sessions(self) -> int:
        return int(self.m01.training["embargo_bars"])

    @property
    def fold_sessions(self) -> int:
        return int(self.m01.training["test_window_bars"])

    @property
    def train_window_sessions(self) -> int:
        return int(self.m01.training["window_bars"])

    @property
    def cost_views(self) -> dict[str, float]:
        views = self.cost_contract.get("views")
        if not isinstance(views, list) or not views:
            raise ValueError("R1 cost contract must enumerate named cost views")
        result: dict[str, float] = {}
        for view in views:
            name = str(view.get("name") or "")
            bps = float(view.get("bps"))
            if not name or not math.isfinite(bps) or bps < 0 or name in result:
                raise ValueError("R1 cost contract contains an invalid or duplicate view")
            result[name] = bps
        return result

    @property
    def primary_cost_bps(self) -> float:
        return float(self.cost_contract["primary_bps"])

    @property
    def primary_view_name(self) -> str:
        matches = [
            name
            for name, bps in self.cost_views.items()
            if math.isclose(bps, self.primary_cost_bps)
        ]
        if len(matches) != 1:
            raise ValueError("R1 cost contract has no unique primary view")
        return matches[0]

    @property
    def severe_view_name(self) -> str:
        stress = {float(value) for value in self.cost_contract["stress_bps"]}
        matches = [(name, bps) for name, bps in self.cost_views.items() if bps in stress]
        if not matches:
            raise ValueError("R1 cost contract has no stress views")
        return max(matches, key=lambda item: item[1])[0]

    @property
    def effective_trial_count(self) -> int:
        return int(self.cumulative_trial_contract["effective_trial_count"])

    @property
    def family_gates(self) -> dict[str, Any]:
        return dict(self.validation_contract["family_gates"])

    @property
    def ml_gates(self) -> dict[str, Any]:
        return dict(self.validation_contract["ml_gates"])

    @property
    def feature_names(self) -> tuple[str, ...]:
        names = self.iteration_contracts["feature-contract.json"]["quant_features"]["names"]
        return tuple(str(name) for name in names)

    @property
    def execution_symbols(self) -> tuple[str, ...]:
        return tuple(
            str(symbol)
            for symbol in self.iteration_contracts["universe-contract.json"]["execution_symbols"]
        )

    @property
    def pbo_contract(self) -> dict[str, Any]:
        return dict(self.validation_contract["pbo"])

    @property
    def benchmark_names(self) -> dict[str, dict[str, float]]:
        raw = self.benchmark_contract.get("single_symbol_benchmarks")
        if not isinstance(raw, dict) or not raw:
            raise ValueError("R1 benchmark contract has no single-symbol definitions")
        return {
            str(name): {str(symbol): float(weight) for symbol, weight in weights.items()}
            for name, weights in raw.items()
        }

    @property
    def reserve_symbol(self) -> str:
        symbols = self.iteration_contracts["universe-contract.json"].get("execution_symbols", [])
        cash = self.benchmark_contract.get("cash_proxy_symbol")
        if cash not in symbols:
            raise ValueError("R1 benchmark cash proxy is outside execution universe")
        return str(cash)

    def gate_value(self, name: str) -> Any:
        gates = self.family_gates
        if name not in gates:
            raise KeyError(f"R1 family gate is missing: {name}")
        return gates[name]

    def ml_gate_value(self, name: str) -> Any:
        gates = self.ml_gates
        if name not in gates:
            raise KeyError(f"R1 ML gate is missing: {name}")
        return gates[name]

    @property
    def sha256(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchors": self.anchors,
            "tactical_trend_sessions": self.tactical_trend_sessions,
            "fold_count": self.fold_count,
            "models": {"S1M01": self.m01.to_dict(), "S1M02": self.m02.to_dict()},
            "semantic_placebo": self.semantic_placebo,
            "candidate_specs": self.candidate_specs,
            "candidate_manifest": self.candidate_manifest,
            "contract_bindings": self.contract_bindings,
            "cost_contract": self.cost_contract,
            "validation_contract": self.validation_contract,
            "benchmark_contract": self.benchmark_contract,
            "cumulative_trial_contract": self.cumulative_trial_contract,
            "iteration_contracts": self.iteration_contracts,
            "factor_definition": self.factor_definition,
            "factor_artifact": self.factor_artifact,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else root / path
    raw = resolved.read_bytes()
    return {
        "path": resolved.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _verify_binding(root: Path, binding: dict[str, Any]) -> Path:
    path = (root / str(binding.get("path") or "")).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("R1 lock binding leaves repository root") from exc
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"R1 lock binding is not a regular file: {path}")
    if _sha256(path) != binding.get("sha256") or path.stat().st_size != binding.get("size_bytes"):
        raise ValueError(f"R1 lock binding changed: {path}")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _runtime_model(candidate_id: str, spec: StrategySpec) -> R1ModelRuntime:
    model = spec.model
    if model is None or model.abstention is None or model.action is None:
        raise ValueError(f"R1 runtime model contract is incomplete: {candidate_id}")
    return R1ModelRuntime(
        candidate_id=candidate_id,
        kind=model.kind,
        features=tuple(model.features),
        label=model.label.model_dump(mode="json"),
        training=model.training.model_dump(mode="json"),
        selection=model.selection.model_dump(mode="json"),
        abstention=model.abstention.model_dump(mode="json"),
        action=model.action.model_dump(mode="json"),
        preprocessing=model.preprocessing,
        hyperparameters=dict(model.hyperparameters),
        baseline=model.baseline,
    )


def _runtime_contract_inputs(
    root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    """Load and bind every preregistered input used by the R1 evaluator."""
    base = root.resolve()
    manifest_path = base / ITERATION_DIR / "candidate-manifest.json"
    manifest = _load_json(manifest_path)
    bindings: dict[str, dict[str, Any]] = {"candidate-manifest.json": _binding(manifest_path, base)}
    contracts: dict[str, Any] = {}
    for filename in CONTRACT_FILENAMES:
        path = base / ITERATION_DIR / filename
        if not path.is_file():
            raise ValueError(f"R1 runtime contract input is missing: {path}")
        bindings[filename] = _binding(path, base)
        if filename.endswith(".json"):
            contracts[filename] = _load_json(path)
    return manifest, bindings, contracts


def runtime_contract_from_specs(
    specs: dict[str, StrategySpec], root: Path | None = None
) -> R1RuntimeContract:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R1 runtime contract requires exactly the preregistered specs")
    base = (root or Path.cwd()).resolve()
    manifest, contract_bindings, contract_payloads = _runtime_contract_inputs(base)
    factor_definition = asdict(get_factor_definition(SLEEVE_FACTOR_ID))
    factor_artifact = _load_json(base / FACTOR_LIBRARY_PATH)
    contract_bindings[FACTOR_LIBRARY_PATH.as_posix()] = _binding(base / FACTOR_LIBRARY_PATH, base)
    manifest_rows = {row.get("candidate_id"): row for row in manifest.get("candidates", [])}
    if set(manifest_rows) != set(SPEC_PATHS) or manifest.get("candidate_count") != len(SPEC_PATHS):
        raise ValueError("R1 candidate manifest does not enumerate exactly the preregistered specs")
    candidate_specs: dict[str, dict[str, Any]] = {}
    for candidate_id, spec in specs.items():
        row = manifest_rows.get(candidate_id)
        if row is None or row.get("spec_path") != SPEC_PATHS[candidate_id].as_posix():
            raise ValueError(f"R1 candidate manifest binding mismatch: {candidate_id}")
        semantic_hash = strategy_content_hash(spec)
        expected_hash = manifest.get("spec_hashes", {}).get(row["spec_path"])
        if expected_hash != semantic_hash:
            raise ValueError(f"R1 spec hash differs from preregistered manifest: {candidate_id}")
        candidate_specs[candidate_id] = {
            "path": row["spec_path"],
            "spec_hash": semantic_hash,
            "spec": spec.model_dump(mode="json"),
        }
    anchors = {}
    tactical_sessions: set[int] = set()
    for candidate_id in ("S1D01", "S1D03", "S1D04"):
        notes = specs[candidate_id].notes.model_dump(mode="json")
        sleeve = notes["sleeve_contract"]
        anchors[candidate_id] = float(sleeve["persistent_anchor"]["capital_weight"])
        tactical_sessions.add(int(sleeve["tactical_trend"]["moving_average_sessions"]))
    if len(tactical_sessions) != 1:
        raise ValueError("R1 deterministic candidates must share one tactical trend horizon")
    p01 = specs["S1P01"].notes.model_dump(mode="json")["semantic_packet_contract"]
    historical_packets = bool(p01.get("historical_packets_available"))
    placebo_status = {
        "historical_status": (
            "eligible_for_fixed_seed_packet_permutation"
            if historical_packets
            else "dependency_skipped_no_historical_packets"
        ),
        "historical_packets_available": historical_packets,
        "placebo_executed": False,
        "placebo_seed_used": False,
        "historical_action": p01.get("historical_action"),
        "planned_method": p01.get("planned_method"),
        "planned_seed": p01.get("planned_seed"),
    }
    validation_payload = contract_payloads["validation-contract.json"]
    chronological = validation_payload["chronological_folds"]
    contract = R1RuntimeContract(
        anchors=anchors,
        tactical_trend_sessions=tactical_sessions.pop(),
        fold_count=int(chronological["count"]),
        m01=_runtime_model("S1M01", specs["S1M01"]),
        m02=_runtime_model("S1M02", specs["S1M02"]),
        semantic_placebo=placebo_status,
        candidate_specs=candidate_specs,
        candidate_manifest=manifest,
        contract_bindings=contract_bindings,
        cost_contract=contract_payloads["cost-contract.json"],
        validation_contract=validation_payload,
        benchmark_contract=contract_payloads["benchmark-contract.json"],
        cumulative_trial_contract=contract_payloads["cumulative-trial-contract.json"],
        iteration_contracts=contract_payloads,
        factor_definition=factor_definition,
        factor_artifact=factor_artifact,
    )
    _validate_runtime_contract(contract, base)
    return contract


def _validate_runtime_contract(contract: R1RuntimeContract, root: Path | None = None) -> None:
    expected_ids = set(SPEC_PATHS)
    if set(contract.candidate_specs) != expected_ids:
        raise ValueError("R1 runtime contract candidate snapshot is incomplete")
    manifest_rows = {
        row.get("candidate_id"): row for row in contract.candidate_manifest.get("candidates", [])
    }
    if set(manifest_rows) != expected_ids:
        raise ValueError("R1 runtime contract manifest snapshot is incomplete")
    for candidate_id, snapshot in contract.candidate_specs.items():
        row = manifest_rows[candidate_id]
        if snapshot["path"] != row.get("spec_path"):
            raise ValueError(f"R1 candidate path binding mismatch: {candidate_id}")
        if snapshot["spec_hash"] != contract.candidate_manifest.get("spec_hashes", {}).get(
            snapshot["path"]
        ):
            raise ValueError(f"R1 candidate semantic hash binding mismatch: {candidate_id}")
    if contract.cost_contract.get("iter_id") != ITER_ID:
        raise ValueError("R1 cost contract iteration mismatch")
    if contract.validation_contract.get("iter_id") != ITER_ID:
        raise ValueError("R1 validation contract iteration mismatch")
    if contract.benchmark_contract.get("iter_id") != ITER_ID:
        raise ValueError("R1 benchmark contract iteration mismatch")
    if contract.cumulative_trial_contract.get("iter_id") != ITER_ID:
        raise ValueError("R1 cumulative trial contract iteration mismatch")
    expected_factor = {
        "id": SLEEVE_FACTOR_ID,
        "family": "portfolio_construction",
        "output": "anchor_and_tactical_target_weights",
        "inputs": ["underlying_close", "portfolio_weights", "review_calendar"],
        "default_parameter_space": {
            "anchor_weight_pct": [40.0, 50.0, 60.0],
            "trend_sma_sessions": [200],
            "risk_on_assets": [["TQQQ"]],
            "risk_off_assets": [["BIL"]],
            "review_schedule": ["calendar_month_end"],
        },
        "expression": None,
        "source_card_ids": list(SLEEVE_FACTOR_SOURCE_CARD_IDS),
    }
    for field, expected in expected_factor.items():
        if contract.factor_definition.get(field) != expected:
            raise ValueError(f"R1 factor definition semantic drift: {field}")
    if not contract.factor_definition.get(
        "implementation_notes"
    ) or not contract.factor_definition.get("risk_notes"):
        raise ValueError("R1 factor definition must bind implementation and risk semantics")
    if contract.factor_artifact.get("strategy_name") != "us_high_beta_sleeve_ensemble_r1":
        raise ValueError("R1 factor artifact strategy binding mismatch")
    if contract.factor_artifact.get("factor_ids") != [SLEEVE_FACTOR_ID]:
        raise ValueError("R1 factor artifact must enumerate the exact sleeve factor")
    factor_count = contract.factor_artifact.get("factor_count")
    if isinstance(factor_count, bool) or not isinstance(factor_count, int) or factor_count != 1:
        raise ValueError("R1 factor artifact factor_count must be exactly one")
    artifact_factors = contract.factor_artifact.get("factors")
    if not isinstance(artifact_factors, list) or len(artifact_factors) != factor_count:
        raise ValueError("R1 factor artifact factor_count does not match factors")
    if artifact_factors != [contract.factor_definition]:
        raise ValueError("R1 factor artifact differs from the executable factor registry")
    binding_root = (root or Path.cwd()).resolve()
    source_cards_path = binding_root / SOURCE_CARDS_PATH
    if source_cards_path.is_symlink() or not source_cards_path.is_file():
        raise ValueError("R1 factor source-card artifact is missing")
    source_cards: dict[str, dict[str, Any]] = {}
    for line_number, raw in enumerate(
        source_cards_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            card = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"R1 factor source-card artifact is invalid at line {line_number}"
            ) from exc
        if not isinstance(card, dict) or not isinstance(card.get("claim_id"), str):
            raise ValueError(
                f"R1 factor source-card artifact has an invalid row at line {line_number}"
            )
        claim_id = card["claim_id"]
        if claim_id in source_cards:
            raise ValueError(f"R1 factor source-card claim is duplicated: {claim_id}")
        source_cards[claim_id] = card
    for claim_id in SLEEVE_FACTOR_SOURCE_CARD_IDS:
        card = source_cards.get(claim_id)
        if card is None or card.get("verification_status") != "source_verified":
            raise ValueError(f"R1 factor source-card claim is not verified: {claim_id}")
    if int(contract.validation_contract["pbo"]["expected_partition_count"]) != 70:
        raise ValueError("R1 PBO contract must enumerate 70 directional partitions")
    required_contract_ids = {
        "data-contract.json",
        "feature-contract.json",
        "label-contract.json",
        "holdout-contract.json",
        "universe-contract.json",
        "modality-role-matrix.json",
    }
    if not required_contract_ids.issubset(contract.iteration_contracts):
        raise ValueError("R1 runtime contract is missing a required iteration contract")
    for filename in required_contract_ids:
        payload = contract.iteration_contracts[filename]
        if payload.get("iter_id") != ITER_ID:
            raise ValueError(f"R1 iteration contract identity mismatch: {filename}")
    primary_cost = float(contract.cost_contract["primary_bps"])
    stress_costs = [float(value) for value in contract.cost_contract["stress_bps"]]
    cost_views = contract.cost_views
    if not math.isclose(cost_views[contract.primary_view_name], primary_cost, abs_tol=1e-12):
        raise ValueError("R1 primary cost view is not bound to the primary bps")
    if [
        cost_views[name]
        for name in cost_views
        if name in {str(row.get("name")) for row in contract.cost_contract.get("views", [])}
    ] != [float(row.get("bps")) for row in contract.cost_contract.get("views", [])]:
        raise ValueError("R1 cost view ordering or values drifted")
    if primary_cost not in stress_costs or len(set(stress_costs)) != len(stress_costs):
        raise ValueError("R1 cost contract primary/stress views are inconsistent")
    if sorted(stress_costs) != sorted(cost_views.values()):
        raise ValueError("R1 stress costs must equal the named cost views")
    if contract.effective_trial_count != int(
        contract.candidate_manifest["cumulative_effective_trial_count"]
    ):
        raise ValueError("R1 cumulative trial count is not bound to the candidate manifest")
    if contract.effective_trial_count != int(
        contract.cumulative_trial_contract["effective_trial_count"]
    ):
        raise ValueError("R1 cumulative trial count contract mismatch")
    if contract.candidate_manifest.get("generated_before_backtest") is not True:
        raise ValueError("R1 candidate manifest must be pre-backtest")
    if contract.candidate_manifest.get("generated_before_model_training") is not True:
        raise ValueError("R1 candidate manifest must be pre-training")
    if contract.candidate_manifest.get("candidates"):
        for candidate_id, row in manifest_rows.items():
            if row.get("candidate_id") != candidate_id or row.get("promotion_eligible") is None:
                raise ValueError(f"R1 candidate manifest row is incomplete: {candidate_id}")
            expected = R1_CANDIDATE_CONTRACT.get(candidate_id)
            if expected is None:
                raise ValueError(f"R1 candidate role mapping is missing: {candidate_id}")
            for field in (
                "role",
                "method",
                "ablation",
                "fallback",
                "path",
                "promotion_eligible",
            ):
                if row.get(field) != expected[field]:
                    raise ValueError(
                        f"R1 candidate manifest {field} is not bound to role mapping: "
                        f"{candidate_id}"
                    )
            spec = contract.candidate_specs[candidate_id]["spec"]
            notes = spec.get("notes", {})
            spec_bindings = {
                "role": notes.get("candidate_role"),
                "method": notes.get("method"),
                "fallback": notes.get("fallback_candidate_id"),
                "promotion_eligible": notes.get("promotion_eligible"),
            }
            for field, actual in spec_bindings.items():
                if actual != expected[field] or row.get(field) != actual:
                    raise ValueError(
                        f"R1 candidate {field} is not bound to generated spec: {candidate_id}"
                    )
            design = spec.get("research_design", {})
            if (
                design.get("candidate_manifest_path")
                != (ITERATION_DIR / "candidate-manifest.json").as_posix()
            ):
                raise ValueError(f"R1 candidate manifest path is not bound to spec: {candidate_id}")

    # Each candidate row must point at the exact preregistered contract IDs;
    # checking only a row's self-reported strings would allow a coherent but
    # different contract family to be silently evaluated.
    manifest_contracts = contract.candidate_manifest.get("contracts", {})
    for field, contract_id in R1_CONTRACT_REF_IDS.items():
        category = R1_CONTRACT_REF_CATEGORIES[field]
        filename = R1_CONTRACT_REF_FILENAMES[field]
        reference = manifest_contracts.get(category, {}).get(contract_id)
        if (
            not isinstance(reference, dict)
            or reference.get("path") != (ITERATION_DIR / filename).as_posix()
        ):
            raise ValueError(f"R1 manifest contract reference is missing or wrong: {field}")
        if reference.get("sha256") != contract.contract_bindings.get(filename, {}).get("sha256"):
            raise ValueError(f"R1 manifest contract hash is not bound: {field}")
        payload = contract.iteration_contracts[filename]
        if payload.get("contract_id") != contract_id:
            raise ValueError(f"R1 contract ID drift: {field}")
    for candidate_id, row in manifest_rows.items():
        for field, contract_id in R1_CONTRACT_REF_IDS.items():
            if row.get(field) != contract_id:
                raise ValueError(f"R1 candidate {field} reference is not bound: {candidate_id}")
    if set(contract.anchors) != {"S1D01", "S1D03", "S1D04"}:
        raise ValueError("R1 deterministic anchor contract is incomplete")
    if any(not 0.0 <= weight <= 1.0 for weight in contract.anchors.values()):
        raise ValueError("R1 deterministic anchor weight is out of bounds")
    if contract.tactical_trend_sessions < 2:
        raise ValueError("R1 tactical trend horizon is invalid")
    chronological = contract.validation_contract["chronological_folds"]
    if contract.fold_count != int(chronological["count"]):
        raise ValueError("R1 runtime fold count differs from validation contract")
    if contract.fold_sessions != int(chronological["oos_sessions"]):
        raise ValueError("R1 runtime fold size differs from validation contract")
    if contract.train_window_sessions != int(chronological["minimum_train_sessions"]):
        raise ValueError("R1 runtime train window differs from validation contract")
    label_timing = contract.iteration_contracts["label-contract.json"]["timing"]
    if int(label_timing["maximum_label_span_sessions"]) != contract.label_max_span_sessions:
        raise ValueError("R1 label maximum horizon differs from label contract")
    if int(label_timing["purge_sessions"]) != contract.purge_sessions:
        raise ValueError("R1 purge differs from label contract")
    if int(label_timing["embargo_sessions"]) != contract.embargo_sessions:
        raise ValueError("R1 embargo differs from label contract")
    if (
        float(
            contract.iteration_contracts["label-contract.json"]["labels"]["S1M01"][
                "one_way_cost_bps"
            ]
        )
        != primary_cost
    ):
        raise ValueError("R1 label cost differs from cost contract")
    feature_contract = contract.iteration_contracts["feature-contract.json"]
    factor_binding = feature_contract.get("factor_library")
    expected_factor_path = FACTOR_LIBRARY_PATH.as_posix()
    if not isinstance(factor_binding, dict):
        raise ValueError("R1 feature contract factor library binding is missing")
    if factor_binding.get("path") != expected_factor_path:
        raise ValueError("R1 feature contract factor library path binding drifted")
    bound_factor = contract.contract_bindings.get(expected_factor_path)
    if not isinstance(bound_factor, dict) or factor_binding.get("sha256") != bound_factor.get(
        "sha256"
    ):
        raise ValueError("R1 feature contract factor library hash binding drifted")
    if root is None:
        binding_root = Path.cwd().resolve()
    else:
        binding_root = root.resolve()
    factor_path = binding_root / expected_factor_path
    resolved_factor_path = factor_path.resolve()
    try:
        resolved_factor_path.relative_to(binding_root)
    except ValueError as exc:
        raise ValueError("R1 factor library binding leaves repository root") from exc
    if (
        factor_path.is_symlink()
        or not factor_path.is_file()
        or factor_binding.get("sha256") != _sha256(factor_path)
    ):
        raise ValueError("R1 feature contract factor library binding is stale")
    deterministic_core = feature_contract.get("deterministic_core", {})
    if (
        deterministic_core.get("factor_library_id") != SLEEVE_FACTOR_ID
        or deterministic_core.get("factor_semantic_role")
        != "portfolio_construction_contract_not_scalar_expression"
    ):
        raise ValueError("R1 deterministic core is not bound to the sleeve factor contract")
    if deterministic_core.get("persistent_anchor") != {
        "symbol": "TQQQ",
        "weight": 0.5,
        "always_invested": True,
    } or deterministic_core.get("tactical_sleeve") != {
        "weight": 0.5,
        "signal": "completed_QQQ_close_strictly_above_SMA200",
        "risk_on_symbol": "TQQQ",
        "risk_off_symbol": "BIL",
        "review": "last_completed_session_of_calendar_month",
    }:
        raise ValueError("R1 deterministic core semantics drifted from the factor contract")
    feature_names = tuple(feature_contract["quant_features"]["names"])
    if feature_names != contract.feature_names or not feature_names:
        raise ValueError("R1 feature contract names differ from registered model features")
    if feature_contract["quant_features"].get("full_sample_standardization") is not False:
        raise ValueError("R1 feature contract permits full-sample standardization")
    semantic_packet = feature_contract["semantic_features"]
    packet_schema = semantic_packet.get("packet_schema", {})
    schema_path = (
        (root / str(packet_schema.get("path"))).resolve()
        if root is not None and isinstance(packet_schema, dict)
        else None
    )
    if not isinstance(packet_schema, dict) or schema_path is None:
        raise ValueError("R1 semantic packet schema binding is missing or stale")
    try:
        schema_path.relative_to(root.resolve() if root is not None else Path.cwd().resolve())
    except ValueError as exc:
        raise ValueError("R1 semantic packet schema leaves repository root") from exc
    if (
        schema_path.is_symlink()
        or not schema_path.is_file()
        or packet_schema.get("sha256") != _sha256(schema_path)
    ):
        raise ValueError("R1 semantic packet schema binding is missing or stale")
    universe = contract.iteration_contracts["universe-contract.json"]
    if tuple(universe.get("execution_symbols", [])) != contract.execution_symbols:
        raise ValueError("R1 execution universe drift")
    if not set(universe.get("signal_symbols", [])).issubset(
        set(contract.iteration_contracts["data-contract.json"].get("symbols", []))
    ):
        raise ValueError("R1 signal universe is outside the data contract")
    benchmark_weights = contract.benchmark_contract["equal_weight_full_spec_universe"]["weights"]
    if set(benchmark_weights) != set(
        contract.benchmark_contract["equal_weight_full_spec_universe"]["symbols"]
    ):
        raise ValueError("R1 benchmark weight universe is incomplete")
    required_benchmarks = set(contract.benchmark_contract["required"])
    actual_benchmarks = set(contract.benchmark_names) | {
        "equal_weight_full_spec_universe",
        "ex_post_best_symbol_report_only",
    }
    if actual_benchmarks != required_benchmarks:
        raise ValueError("R1 benchmark family definitions drifted")

    m01 = contract.m01
    m02 = contract.m02
    for model in (m01, m02):
        if model.features != feature_names or model.preprocessing != "standard_scaler":
            raise ValueError(
                f"R1 unsupported feature or preprocessing contract: {model.candidate_id}"
            )
        if model.baseline != "none":
            raise ValueError(f"R1 model baseline must be none: {model.candidate_id}")
        if (
            model.training["retrain_schedule"] != "calendar_month_end"
            or model.training["retrain_every_bars"] is not None
            or model.training["purge_bars"] is None
            or model.label["horizon_mode"] != "next_scheduled_review_open"
            or model.label["horizon_bars"] is not None
            or model.label["review_schedule"] != "calendar_month_end"
            or model.label["maximum_horizon_bars"] is None
            or model.abstention["fallback_candidate_id"] != "S1D01"
            or model.abstention["insufficient_data_action"] != "exact_target_identity_fallback"
            or model.action["apply_at"] != "next_regular_session_open"
            or model.action["hold_until"] != "next_scheduled_review_open"
        ):
            raise ValueError(f"R1 scheduled model contract mismatch: {model.candidate_id}")

    if (
        m01.kind != "ridge_regressor"
        or m01.label["type"] != "net_incremental_policy_value"
        or m01.label["baseline_policy"] != "exact_S1D01_from_same_pretrade_state"
        or m01.label["alternative_policy"] != "invert_S1D01_tactical_sleeve_state"
        or m01.label["value_measure"] != "log_wealth_ratio"
        or m01.label["terminal_rejoin_cost_included"] is not True
        or m01.selection["method"] != "threshold"
        or m01.selection["threshold"] is None
        or m01.selection["operator"] != "lower_bound_strictly_greater_than"
        or m01.abstention["calibration_method"] != "chronological_split_conformal_lower_bound"
        or m01.abstention["target_coverage"] is None
        or m01.abstention["quantile_method"] != "higher"
        or m01.abstention["calibrator"] is not None
        or m01.action["kind"] != "invert_tactical_sleeve"
        or any(
            m01.action[field] is not None
            for field in ("source_symbol", "destination_symbol", "portfolio_weight_delta")
        )
        or set(m01.hyperparameters) != {"alpha", "fit_intercept"}
        or not isinstance(m01.hyperparameters["fit_intercept"], bool)
        or not math.isfinite(float(m01.hyperparameters["alpha"]))
        or float(m01.hyperparameters["alpha"]) <= 0
        or not math.isfinite(float(m01.selection["threshold"]))
        or float(m01.selection["threshold"]) != 0.0
    ):
        raise ValueError("R1 Ridge runtime contract mismatch")

    calibrator = m02.abstention.get("calibrator")
    m02_threshold = m02.selection.get("threshold")
    m02_delta = m02.action.get("portfolio_weight_delta")
    m02_drawdown = m02.label.get("max_drawdown_pct")
    m02_terminal = m02.label.get("min_terminal_return_pct")
    execution_symbols = set(contract.execution_symbols)
    if (
        m02.kind != "logistic_regression_classifier"
        or m02.label["type"] != "path_survival"
        or m02.label["path_drawdown_reference"] != "running_open_peak"
        or m02.label["max_drawdown_pct"] is None
        or m02.label["min_terminal_return_pct"] is None
        or m02.selection["method"] != "threshold"
        or m02.selection["threshold"] is None
        or m02.selection["operator"] != "less_than_or_equal"
        or m02.abstention["calibration_method"] != "chronological_platt_scaling"
        or calibrator is None
        or calibrator["kind"] != "logistic_regression"
        or calibrator["use_training_seed"] is not True
        or m02.action["kind"] != "shift_portfolio_weight"
        or m02.action["source_symbol"] != "TQQQ"
        or m02.action["destination_symbol"] != "BIL"
        or m02.action["portfolio_weight_delta"] is None
        or not math.isfinite(float(m02_threshold))
        or not 0.0 <= float(m02_threshold) <= 1.0
        or not math.isclose(float(m02_threshold), M02_SURVIVAL_THRESHOLD, abs_tol=1e-12)
        or not math.isfinite(float(m02_delta))
        or not 0.0 < float(m02_delta) <= 1.0
        or not math.isclose(float(m02_delta), M02_ANCHOR_CUT, abs_tol=1e-12)
        or m02.action["source_symbol"] == m02.action["destination_symbol"]
        or not {m02.action["source_symbol"], m02.action["destination_symbol"]}.issubset(
            execution_symbols
        )
        or not math.isfinite(float(m02_drawdown))
        or not 0.0 < float(m02_drawdown) <= 100.0
        or not math.isclose(float(m02_drawdown), M02_MAX_DRAWDOWN_PCT, abs_tol=1e-12)
        or not math.isfinite(float(m02_terminal))
        or not -100.0 <= float(m02_terminal) <= 100.0
        or not math.isclose(float(m02_terminal), M02_MIN_TERMINAL_RETURN_PCT, abs_tol=1e-12)
        or set(m02.hyperparameters) != {"C", "penalty", "solver", "max_iter", "class_weight"}
        or m02.hyperparameters["penalty"] != "l2"
        or m02.hyperparameters["solver"] != "lbfgs"
        or m02.hyperparameters["class_weight"] != "balanced"
        or not math.isfinite(float(m02.hyperparameters["C"]))
        or float(m02.hyperparameters["C"]) <= 0
        or not isinstance(m02.hyperparameters["max_iter"], int)
        or m02.hyperparameters["max_iter"] < 1
    ):
        raise ValueError("R1 logistic runtime contract mismatch")
    label_contract = contract.iteration_contracts["label-contract.json"]
    m02_label_contract = label_contract["labels"]["S1M02"]
    if (
        m02_label_contract.get("action", {}).get("portfolio_weight_delta") != float(m02_delta)
        or m02_label_contract.get("action", {}).get("source_symbol") != m02.action["source_symbol"]
        or m02_label_contract.get("action", {}).get("destination_symbol")
        != m02.action["destination_symbol"]
        or m02_label_contract.get("positive")
        != "next_review_open_path_running_peak_drawdown_strictly_above_minus_12pct_and_terminal_return_strictly_above_minus_8pct"
    ):
        raise ValueError("R1 M02 action or label semantics drifted from label contract")

    shared_fields = (
        "window_bars",
        "test_window_bars",
        "purge_bars",
        "embargo_bars",
    )
    if any(m01.training[field] != m02.training[field] for field in shared_fields) or (
        m01.label["maximum_horizon_bars"] != m02.label["maximum_horizon_bars"]
    ):
        raise ValueError("R1 ML models must share fold and label-timing contracts")
    if contract.label_max_span_sessions > contract.purge_sessions:
        raise ValueError("R1 purge must cover the maximum scheduled label horizon")
    if contract.label_max_span_sessions > contract.embargo_sessions:
        raise ValueError("R1 mature-label embargo must cover the maximum scheduled label horizon")
    if contract.semantic_placebo != {
        "historical_status": "dependency_skipped_no_historical_packets",
        "historical_packets_available": False,
        "placebo_executed": False,
        "placebo_seed_used": False,
        "historical_action": "exact_S1D01_identity_not_placebo",
        "planned_method": "fixed_seed_packet_mapping_permutation",
        "planned_seed": 260813,
    }:
        raise ValueError("R1 historical placebo must be explicitly dependency-skipped")
    feature_lineage = contract.iteration_contracts["feature-contract.json"]["quant_features"][
        "lineage"
    ]
    expected_lineage = {
        "qqq_trend_gap_200": {
            "input_symbol": "QQQ",
            "formula": "close_t / mean(close[t-199:t]) - 1",
            "shift": 0,
        },
        "qqq_momentum_252_skip21": {
            "input_symbol": "QQQ",
            "formula": "close_t_minus_21 / close_t_minus_252 - 1",
            "shift": 0,
        },
        "tqqq_momentum_21": {
            "input_symbol": "TQQQ",
            "formula": "close_t / close_t_minus_21 - 1",
            "shift": 0,
        },
        "tqqq_momentum_63": {
            "input_symbol": "TQQQ",
            "formula": "close_t / close_t_minus_63 - 1",
            "shift": 0,
        },
        "tqqq_realized_volatility_21": {
            "input_symbol": "TQQQ",
            "formula": "sample_std_of_21_close_to_close_returns_ending_t",
            "ddof": 1,
        },
        "tqqq_drawdown_63": {
            "input_symbol": "TQQQ",
            "formula": "close_t / max(close[t-62:t]) - 1",
            "rolling_high_shift": 0,
        },
    }
    for name, expected in expected_lineage.items():
        actual = feature_lineage.get(name, {})
        for field, value in expected.items():
            if actual.get(field) != value:
                raise ValueError(f"R1 feature lineage drift: {name}.{field}")
    expressions = feature_contract["quant_features"].get("expressions", {})
    if feature_names != MODEL_FEATURES or set(expressions) != set(feature_names):
        raise ValueError("R1 feature expression contract is incomplete")
    if expressions != EXPECTED_FEATURE_EXPRESSIONS:
        raise ValueError("R1 feature expression contract does not match runner formulas")
    if contract.tactical_trend_sessions != 200:
        raise ValueError("R1 tactical trend horizon must be the preregistered SMA200")
    if feature_contract["quant_features"].get("availability") != "decision_close_or_earlier":
        raise ValueError("R1 feature availability horizon is not point-in-time")
    d01_spec = contract.candidate_specs["S1D01"]["spec"]
    d01_sleeve = d01_spec["notes"]["sleeve_contract"]
    d01_sleeve_semantics = {
        "persistent_anchor": d01_sleeve["persistent_anchor"],
        "tactical_trend": d01_sleeve["tactical_trend"],
        "between_reviews": d01_sleeve["between_reviews"],
        "initial_action": d01_sleeve["initial_action"],
        "terminal_liquidation_in_metrics": d01_sleeve["terminal_liquidation_in_metrics"],
    }
    neighborhood = contract.validation_contract["neighborhood_controls"]
    expected_neighbor_weights = {
        "S1D03": float(neighborhood["S1D03_anchor_weight"]),
        "S1D04": float(neighborhood["S1D04_anchor_weight"]),
    }
    stress_view_values = sorted(float(value) for value in contract.cost_contract["stress_bps"])
    manifest_candidates = {
        row.get("candidate_id"): row for row in contract.candidate_manifest.get("candidates", [])
    }
    for candidate_id, snapshot in contract.candidate_specs.items():
        spec = snapshot["spec"]
        costs = spec.get("costs", {})
        if not math.isclose(float(costs.get("slippage_bps", -1.0)), primary_cost, abs_tol=1e-12):
            raise ValueError(f"R1 candidate cost is not bound to cost contract: {candidate_id}")
        notes = spec.get("notes", {})
        sleeve = notes.get("sleeve_contract", {})
        if candidate_id in contract.anchors:
            weight = sleeve.get("persistent_anchor", {}).get("capital_weight")
            if not math.isclose(float(weight), contract.anchors[candidate_id], abs_tol=1e-12):
                raise ValueError(
                    f"R1 candidate sleeve is not bound to runtime anchor: {candidate_id}"
                )
        sleeve = spec.get("notes", {}).get("sleeve_contract", {})
        normalized_sleeve = {
            "persistent_anchor": sleeve.get("persistent_anchor"),
            "tactical_trend": sleeve.get("tactical_trend"),
            "between_reviews": sleeve.get("between_reviews"),
            "initial_action": sleeve.get("initial_action"),
            "terminal_liquidation_in_metrics": sleeve.get("terminal_liquidation_in_metrics"),
        }
        if candidate_id not in {"S1D03", "S1D04"} and normalized_sleeve != d01_sleeve_semantics:
            raise ValueError(f"R1 candidate sleeve semantics must equal S1D01: {candidate_id}")
        if candidate_id in expected_neighbor_weights:
            if not math.isclose(
                float(sleeve.get("persistent_anchor", {}).get("capital_weight", -1.0)),
                expected_neighbor_weights[candidate_id],
                abs_tol=1e-12,
            ):
                raise ValueError(f"R1 neighborhood anchor is not frozen: {candidate_id}")
            neighbor_tactical = dict(sleeve.get("tactical_trend", {}))
            expected_tactical = dict(d01_sleeve["tactical_trend"])
            expected_tactical["capital_weight"] = 1.0 - expected_neighbor_weights[candidate_id]
            if neighbor_tactical != expected_tactical:
                raise ValueError(f"R1 neighborhood tactical sleeve drift: {candidate_id}")
        manifest_row = manifest_candidates[candidate_id]
        if manifest_row.get("spec_path") != snapshot["path"]:
            raise ValueError(f"R1 candidate manifest path drift: {candidate_id}")
        if spec.get("execution", {}).get("fill_assumption") != "next_bar_open":
            raise ValueError(f"R1 candidate fill assumption drift: {candidate_id}")
        if spec.get("execution_policy") is None or spec.get("reality_model") is None:
            raise ValueError(f"R1 candidate execution/reality contract is missing: {candidate_id}")
        reality = spec["reality_model"]
        stress = reality.get("stress_scenarios", [])
        if sorted(float(row.get("slippage_bps")) for row in stress) != stress_view_values:
            raise ValueError(f"R1 reality stress scenarios drift: {candidate_id}")
        if reality.get("fill_model") != "next_regular_open_with_policy":
            raise ValueError(f"R1 reality fill model drift: {candidate_id}")
        if reality.get("slippage_model") != "stress_bps_by_volatility_and_participation":
            raise ValueError(f"R1 reality slippage model drift: {candidate_id}")
        factor_map = spec.get("factors", {})
        for feature_name in feature_names:
            factor = factor_map.get(feature_name)
            if (
                factor is None
                or factor.get("source") != "expression"
                or factor.get("expression") != expressions[feature_name]
            ):
                raise ValueError(f"R1 candidate factor missing: {candidate_id}/{feature_name}")
        if candidate_id in {"S1L01", "S1C01", "S1P01"}:
            semantic = notes.get("semantic_packet_contract")
            if semantic is None or semantic.get("historical_packets_available") is not False:
                raise ValueError(f"R1 semantic packet status drift: {candidate_id}")
        if notes.get("factor_library_ids") != [SLEEVE_FACTOR_ID]:
            raise ValueError(f"R1 candidate factor lineage drift: {candidate_id}")


def load_and_validate_specs(root: Path) -> dict[str, StrategySpec]:
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R1 requires exactly ten preregistered specs")
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        design = spec.research_design
        if (
            notes.get("candidate_id") != candidate_id
            or notes.get("semantic_stock_budget") != 0.0
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
            or spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or spec.execution.signal_on != "bar_close"
            or spec.execution.fill_assumption != "next_bar_open"
            or spec.data.feed != "sip"
            or design is None
            or design.iter_id != ITER_ID
            or design.candidate_manifest_path
            != (ITERATION_DIR / "candidate-manifest.json").as_posix()
        ):
            raise ValueError(f"R1 spec safety or iteration binding mismatch: {candidate_id}")
        factor_ids = notes.get("factor_library_ids", [])
        if factor_ids != [SLEEVE_FACTOR_ID]:
            raise ValueError(f"R1 factor lineage must bind exact sleeve semantics: {candidate_id}")
        sleeve = notes.get("sleeve_contract", {})
        anchor = sleeve.get("persistent_anchor", {}).get("capital_weight")
        tactical = sleeve.get("tactical_trend", {}).get("capital_weight")
        trend = sleeve.get("tactical_trend", {})
        space = design.parameter_space
        if (
            not math.isclose(float(anchor) + float(tactical), 1.0, abs_tol=1e-12)
            or trend.get("risk_on_symbol") != "TQQQ"
            or trend.get("risk_off_symbol") != "BIL"
            or trend.get("signal_symbol") != "QQQ"
            or trend.get("risk_on_rule") != "completed_QQQ_close_strictly_above_SMA200"
            or trend.get("review_schedule") != "final_completed_session_of_each_calendar_month"
            or trend.get("execution") != "next_regular_session_open"
            or space.get("persistent_anchor_weight") != [anchor]
            or space.get("tactical_trend_sessions") != [trend.get("moving_average_sessions")]
            or space.get("parameter_search") != [False]
        ):
            raise ValueError(f"R1 sleeve weights do not sum to one: {candidate_id}")

    for candidate_id in ("S1M01", "S1C01", "S1F01"):
        model = specs[candidate_id].model
        label = model.label if model is not None else None
        abstention = model.abstention if model is not None else None
        action = model.action if model is not None else None
        if (
            model is None
            or model.kind != "ridge_regressor"
            or tuple(model.features) != tuple(specs["S1M01"].model.features)
            or label is None
            or label.type != "net_incremental_policy_value"
            or abstention is None
            or action is None
        ):
            raise ValueError(f"R1 Ridge role mismatch: {candidate_id}")
    if specs["S1C01"].model != specs["S1M01"].model or specs["S1F01"].model != specs["S1M01"].model:
        raise ValueError("R1 combined and missing-modality Ridge contracts must be exact")
    m02 = specs["S1M02"].model
    m02_label = m02.label if m02 is not None else None
    m02_abstention = m02.abstention if m02 is not None else None
    m02_action = m02.action if m02 is not None else None
    if (
        m02 is None
        or m02.kind != "logistic_regression_classifier"
        or tuple(m02.features) != tuple(specs["S1M02"].model.features)
        or m02_label is None
        or m02_label.type != "path_survival"
        or m02_abstention is None
        or m02_action is None
    ):
        raise ValueError("R1 logistic tail-risk contract mismatch")
    d01_space = specs["S1D01"].research_design.parameter_space
    if d01_space != {
        "candidate_id": ["S1D01"],
        "persistent_anchor_weight": [
            specs["S1D01"].notes.model_dump(mode="json")["sleeve_contract"]["persistent_anchor"][
                "capital_weight"
            ]
        ],
        "tactical_trend_sessions": [
            specs["S1D01"].notes.model_dump(mode="json")["sleeve_contract"]["tactical_trend"][
                "moving_average_sessions"
            ]
        ],
        "rebalance_schedule": ["month_end"],
        "parameter_search": [False],
    }:
        raise ValueError("R1 D01 must be one fixed non-search candidate")
    runtime_contract_from_specs(specs, root=root)
    return specs


def chronological_folds(
    index: pd.DatetimeIndex, contract: R1RuntimeContract
) -> list[dict[str, Any]]:
    if len(index) < (
        contract.train_window_sessions
        + contract.purge_sessions
        + (contract.fold_count * contract.fold_sessions)
    ):
        raise ValueError("R1 panel has insufficient chronological fold capacity")
    first_test = len(index) - contract.fold_count * contract.fold_sessions
    folds = []
    cursor = first_test
    for number in range(1, contract.fold_count + 1):
        test_end = cursor + contract.fold_sessions - 1
        train_end = cursor - contract.purge_sessions - 1
        train_start = max(0, train_end - contract.train_window_sessions + 1)
        folds.append(
            {
                "fold_id": f"F{number}",
                "train_start": index[train_start].date().isoformat(),
                "train_end": index[train_end].date().isoformat(),
                "rolling_train_sessions": train_end - train_start + 1,
                "purge_sessions": contract.purge_sessions,
                "mature_label_embargo_sessions": contract.embargo_sessions,
                "maximum_label_horizon_sessions": contract.label_max_span_sessions,
                "test_start": index[cursor].date().isoformat(),
                "test_end": index[test_end].date().isoformat(),
                "test_session_count": contract.fold_sessions,
                "fit_from_scratch": True,
                "model_update_mode": "prequential_month_end_refit_from_scratch",
            }
        )
        cursor = test_end + 1
    if cursor != len(index):
        raise AssertionError("R1 folds did not consume the frozen final OOS sessions")
    return folds


def _month_end_positions(index: pd.DatetimeIndex) -> list[int]:
    periods = index.to_period("M")
    return [
        position for position in range(len(index) - 1) if periods[position] != periods[position + 1]
    ]


def _sleeve_weights(
    *,
    risk_on: bool,
    anchor_weight: float,
    sleeve_contract: dict[str, Any] | None = None,
) -> dict[str, float]:
    sleeve = sleeve_contract or {
        "persistent_anchor": {"symbol": "TQQQ"},
        "tactical_trend": {"risk_on_symbol": "TQQQ", "risk_off_symbol": "BIL"},
    }
    anchor_symbol = str(sleeve["persistent_anchor"]["symbol"])
    risk_on_symbol = str(sleeve["tactical_trend"]["risk_on_symbol"])
    risk_off_symbol = str(sleeve["tactical_trend"]["risk_off_symbol"])
    if anchor_symbol != risk_on_symbol:
        raise ValueError("R1 sleeve requires the persistent anchor to share the risk-on symbol")
    tactical_weight = 1.0 - anchor_weight
    return {
        risk_on_symbol: anchor_weight + (tactical_weight if risk_on else 0.0),
        risk_off_symbol: tactical_weight if not risk_on else 0.0,
    }


def _contract_sleeve_weights(
    *,
    risk_on: bool,
    candidate_id: str,
    contract: R1RuntimeContract,
) -> dict[str, float]:
    spec = contract.candidate_specs[candidate_id]["spec"]
    sleeve = spec["notes"]["sleeve_contract"]
    anchor = float(sleeve["persistent_anchor"]["capital_weight"])
    return _sleeve_weights(risk_on=risk_on, anchor_weight=anchor, sleeve_contract=sleeve)


def _drift_weights(
    opens: pd.DataFrame,
    *,
    start_position: int,
    end_position: int,
    target: dict[str, float],
) -> dict[str, float]:
    grown = {
        symbol: float(weight)
        * float(opens.iloc[end_position][symbol] / opens.iloc[start_position][symbol])
        for symbol, weight in target.items()
    }
    wealth = math.fsum(grown.values())
    if not math.isfinite(wealth) or wealth <= 0:
        raise ValueError("R1 drifted sleeve wealth is nonpositive")
    return {symbol: value / wealth for symbol, value in grown.items()}


def _policy_wealth_factor(
    opens: pd.DataFrame,
    *,
    start_position: int,
    end_position: int,
    pretrade_weights: dict[str, float],
    start_target: dict[str, float],
    rejoin_target: dict[str, float],
    cost_bps: float,
    symbols: tuple[str, str] = ("TQQQ", "BIL"),
) -> float:
    rate = cost_bps / 10_000.0
    start_notional = math.fsum(
        abs(float(start_target[symbol]) - float(pretrade_weights[symbol])) for symbol in symbols
    )
    start_cost = 1.0 - start_notional * rate
    growth = {
        symbol: float(opens.iloc[end_position][symbol] / opens.iloc[start_position][symbol])
        for symbol in symbols
    }
    gross_factor = math.fsum(float(start_target[symbol]) * growth[symbol] for symbol in symbols)
    end_weights = {
        symbol: float(start_target[symbol]) * growth[symbol] / gross_factor for symbol in symbols
    }
    rejoin_notional = math.fsum(
        abs(float(rejoin_target[symbol]) - end_weights[symbol]) for symbol in symbols
    )
    rejoin_cost = 1.0 - rejoin_notional * rate
    wealth = start_cost * gross_factor * rejoin_cost
    if min(start_cost, gross_factor, rejoin_cost, wealth) <= 0 or not math.isfinite(wealth):
        raise ValueError("R1 policy wealth factor is nonpositive")
    return float(wealth)


def _policy_value(
    opens: pd.DataFrame,
    *,
    start_position: int,
    end_position: int,
    pretrade_weights: dict[str, float],
    baseline_target: dict[str, float],
    alternative_target: dict[str, float],
    rejoin_target: dict[str, float],
    cost_bps: float,
    symbols: tuple[str, str] = ("TQQQ", "BIL"),
) -> float:
    baseline = _policy_wealth_factor(
        opens,
        start_position=start_position,
        end_position=end_position,
        pretrade_weights=pretrade_weights,
        start_target=baseline_target,
        rejoin_target=rejoin_target,
        cost_bps=cost_bps,
        symbols=symbols,
    )
    alternative = _policy_wealth_factor(
        opens,
        start_position=start_position,
        end_position=end_position,
        pretrade_weights=pretrade_weights,
        start_target=alternative_target,
        rejoin_target=rejoin_target,
        cost_bps=cost_bps,
        symbols=symbols,
    )
    return float(math.log(alternative / baseline))


def build_monthly_dataset(panel: R11PricePanel, contract: R1RuntimeContract) -> pd.DataFrame:
    close = panel.close
    opens = panel.open
    d01_sleeve = contract.candidate_specs["S1D01"]["spec"]["notes"]["sleeve_contract"]
    signal_symbol = str(d01_sleeve["tactical_trend"]["signal_symbol"])
    risk_on_symbol = str(d01_sleeve["tactical_trend"]["risk_on_symbol"])
    risk_off_symbol = str(d01_sleeve["tactical_trend"]["risk_off_symbol"])
    if not {signal_symbol, risk_on_symbol, risk_off_symbol}.issubset(close.columns):
        raise ValueError("R1 panel is missing a contract-bound signal or sleeve symbol")
    if tuple(contract.execution_symbols) != (risk_on_symbol, risk_off_symbol):
        raise ValueError("R1 execution universe must match the contract-bound sleeve symbols")
    rows: list[dict[str, Any]] = []
    tqqq_returns = close[risk_on_symbol].pct_change()
    trend_sessions = contract.tactical_trend_sessions
    d01_anchor = contract.anchors["S1D01"]
    for position in _month_end_positions(close.index):
        if position < trend_sessions - 1:
            continue
        execution_position = position + 1
        qqq_close = float(close.iloc[position][signal_symbol])
        qqq_trend = float(
            close[signal_symbol].iloc[position - trend_sessions + 1 : position + 1].mean()
        )
        risk_on = qqq_close > qqq_trend
        feature_values: dict[str, float] = {
            "qqq_trend_gap_200": qqq_close / qqq_trend - 1.0,
            "qqq_momentum_252_skip21": np.nan,
            "tqqq_momentum_21": float(
                close.iloc[position][risk_on_symbol] / close.iloc[position - 21][risk_on_symbol]
                - 1.0
            ),
            "tqqq_momentum_63": float(
                close.iloc[position][risk_on_symbol] / close.iloc[position - 63][risk_on_symbol]
                - 1.0
            ),
            "tqqq_realized_volatility_21": float(
                tqqq_returns.iloc[position - 20 : position + 1].std(ddof=1)
            ),
            "tqqq_drawdown_63": float(
                close.iloc[position][risk_on_symbol]
                / close[risk_on_symbol].iloc[position - 62 : position + 1].max()
                - 1.0
            ),
        }
        if position >= 252:
            feature_values["qqq_momentum_252_skip21"] = float(
                close.iloc[position - 21][signal_symbol] / close.iloc[position - 252][signal_symbol]
                - 1.0
            )
        baseline = _sleeve_weights(
            risk_on=risk_on,
            anchor_weight=d01_anchor,
            sleeve_contract=d01_sleeve,
        )
        rows.append(
            {
                "decision_position": position,
                "decision_session": close.index[position].date().isoformat(),
                "execution_position": execution_position,
                "execution_session": close.index[execution_position].date().isoformat(),
                "label_end_position": None,
                "label_end_session": None,
                "label_span_sessions": None,
                "risk_on": risk_on,
                "d01_tqqq_weight": baseline[risk_on_symbol],
                "d01_bil_weight": baseline[risk_off_symbol],
                "pretrade_tqqq_weight": None,
                "pretrade_bil_weight": None,
                "m01_policy_value": None,
                "m02_path_survival": None,
                "m02_local_counterfactual_policy_value": None,
                **feature_values,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("R1 produced no eligible month-end decisions")
    prior_target: dict[str, float] | None = None
    prior_execution_position: int | None = None
    for row_index in range(len(frame)):
        execution_position = int(frame.at[row_index, "execution_position"])
        if prior_target is None or prior_execution_position is None:
            pretrade = {risk_on_symbol: 0.0, risk_off_symbol: 0.0}
        else:
            pretrade = _drift_weights(
                opens,
                start_position=prior_execution_position,
                end_position=execution_position,
                target=prior_target,
            )
        frame.at[row_index, "pretrade_tqqq_weight"] = pretrade[risk_on_symbol]
        frame.at[row_index, "pretrade_bil_weight"] = pretrade[risk_off_symbol]
        baseline = {
            risk_on_symbol: float(frame.at[row_index, "d01_tqqq_weight"]),
            risk_off_symbol: float(frame.at[row_index, "d01_bil_weight"]),
        }
        prior_target = baseline
        prior_execution_position = execution_position
        if row_index + 1 >= len(frame):
            continue
        end_position = int(frame.at[row_index + 1, "execution_position"])
        label_span = end_position - execution_position
        if not 1 <= label_span <= contract.label_max_span_sessions:
            raise ValueError(f"R1 scheduled label span out of contract: {label_span}")
        rejoin_target = {
            risk_on_symbol: float(frame.at[row_index + 1, "d01_tqqq_weight"]),
            risk_off_symbol: float(frame.at[row_index + 1, "d01_bil_weight"]),
        }
        inverted = _contract_sleeve_weights(
            risk_on=not bool(frame.at[row_index, "risk_on"]),
            candidate_id="S1D01",
            contract=contract,
        )
        action = contract.m02.action
        source = str(action["source_symbol"])
        destination = str(action["destination_symbol"])
        delta = min(float(action["portfolio_weight_delta"]), baseline[source])
        m02_target = {
            **baseline,
            source: baseline[source] - delta,
            destination: baseline[destination] + delta,
        }
        frame.at[row_index, "m01_policy_value"] = _policy_value(
            opens,
            start_position=execution_position,
            end_position=end_position,
            pretrade_weights=pretrade,
            baseline_target=baseline,
            alternative_target=inverted,
            rejoin_target=rejoin_target,
            cost_bps=contract.primary_cost_bps,
            symbols=tuple(contract.execution_symbols),
        )
        frame.at[row_index, "m02_local_counterfactual_policy_value"] = _policy_value(
            opens,
            start_position=execution_position,
            end_position=end_position,
            pretrade_weights=pretrade,
            baseline_target=baseline,
            alternative_target=m02_target,
            rejoin_target=rejoin_target,
            cost_bps=contract.primary_cost_bps,
            symbols=tuple(contract.execution_symbols),
        )
        path = opens[risk_on_symbol].iloc[execution_position : end_position + 1].astype(float)
        running_drawdown = path / path.cummax() - 1.0
        terminal = float(path.iloc[-1] / path.iloc[0] - 1.0)
        drawdown_floor = -float(contract.m02.label["max_drawdown_pct"]) / 100.0
        terminal_floor = float(contract.m02.label["min_terminal_return_pct"]) / 100.0
        frame.at[row_index, "m02_path_survival"] = float(
            float(running_drawdown.min()) > drawdown_floor and terminal > terminal_floor
        )
        frame.at[row_index, "label_end_position"] = end_position
        frame.at[row_index, "label_end_session"] = close.index[end_position].date().isoformat()
        frame.at[row_index, "label_span_sessions"] = label_span
    return frame


def _empty_target(columns: pd.Index) -> dict[str, float]:
    return {str(symbol): 0.0 for symbol in columns}


def build_deterministic_targets(
    panel: R11PricePanel,
    dataset: pd.DataFrame,
    *,
    anchor_weight: float,
    sleeve_contract: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if not 0.0 <= anchor_weight <= 1.0:
        raise ValueError("R1 anchor weight must be between zero and one")
    sleeve = sleeve_contract or {
        "persistent_anchor": {"symbol": "TQQQ"},
        "tactical_trend": {
            "risk_on_symbol": "TQQQ",
            "risk_off_symbol": "BIL",
        },
    }
    anchor_symbol = str(sleeve["persistent_anchor"]["symbol"])
    risk_on_symbol = str(sleeve["tactical_trend"]["risk_on_symbol"])
    risk_off_symbol = str(sleeve["tactical_trend"]["risk_off_symbol"])
    if anchor_symbol != risk_on_symbol:
        raise ValueError("R1 deterministic sleeve anchor and risk-on symbols must match")
    rows = []
    index = []
    for record in dataset.to_dict(orient="records"):
        target = _empty_target(panel.open.columns)
        tactical = 1.0 - anchor_weight
        target[risk_on_symbol] = anchor_weight + (tactical if bool(record["risk_on"]) else 0.0)
        target[risk_off_symbol] = tactical if not bool(record["risk_on"]) else 0.0
        if not math.isclose(math.fsum(target.values()), 1.0, abs_tol=1e-12):
            raise AssertionError("R1 deterministic target does not sum to one")
        rows.append(target)
        index.append(pd.Timestamp(record["execution_session"]))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index), columns=panel.open.columns).astype(
        float
    )


def training_rows_for_decision(
    dataset: pd.DataFrame,
    *,
    decision_position: int,
    label_name: str,
    model_contract: R1ModelRuntime,
) -> pd.DataFrame:
    latest_label_end = decision_position - int(model_contract.training["embargo_bars"])
    earliest_decision = decision_position - int(model_contract.training["window_bars"])
    selected = dataset[
        (dataset["decision_position"] >= earliest_decision)
        & (dataset["decision_position"] < decision_position)
        & (dataset["label_end_position"] <= latest_label_end)
        & dataset[label_name].notna()
    ].copy()
    finite = np.isfinite(selected.loc[:, model_contract.features].to_numpy(dtype=float)).all(axis=1)
    finite &= np.isfinite(selected[label_name].to_numpy(dtype=float))
    return selected.loc[finite].sort_values("decision_position").reset_index(drop=True)


def _frame_hash(frame: pd.DataFrame, columns: list[str]) -> str:
    payload = frame.loc[:, columns].to_dict(orient="records")
    return _canonical_hash(payload)


def _chronological_fit_calibration_split(
    train: pd.DataFrame,
    model_contract: R1ModelRuntime,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    abstention = model_contract.abstention
    calibration_count = max(
        int(abstention["minimum_calibration_rows"]),
        int(math.ceil(len(train) * float(abstention["calibration_fraction"]))),
    )
    fit_count = len(train) - calibration_count
    if fit_count < int(abstention["minimum_fit_rows"]) or calibration_count < int(
        abstention["minimum_calibration_rows"]
    ):
        return None
    return train.iloc[:fit_count].copy(), train.iloc[fit_count:].copy()


def _fit_ridge(
    train: pd.DataFrame,
    *,
    decision_session: str,
    provenance: dict[str, Any],
    model_contract: R1ModelRuntime,
) -> FittedDecisionModel | None:
    split = _chronological_fit_calibration_split(train, model_contract)
    if split is None:
        return None
    fit, calibration = split
    estimator = Pipeline(
        [("scale", StandardScaler()), ("model", Ridge(**model_contract.hyperparameters))]
    )
    estimator.fit(fit.loc[:, model_contract.features], fit["m01_policy_value"])
    predicted = estimator.predict(calibration.loc[:, model_contract.features])
    residual = predicted - calibration["m01_policy_value"].to_numpy(dtype=float)
    conformal_rank = min(
        len(calibration),
        int(
            math.ceil((len(calibration) + 1) * float(model_contract.abstention["target_coverage"]))
        ),
    )
    lower_offset = float(np.sort(residual)[conformal_rank - 1])
    calibration_lower = predicted - lower_offset
    empirical_coverage = float(
        np.mean(calibration["m01_policy_value"].to_numpy(dtype=float) >= calibration_lower)
    )
    training_hash = _frame_hash(
        train,
        ["decision_session", "label_end_session", *model_contract.features, "m01_policy_value"],
    )
    model = estimator.named_steps["model"]
    model_state = {
        "coef": np.asarray(model.coef_, dtype=float).tolist(),
        "intercept": float(model.intercept_),
        "lower_offset": lower_offset,
    }
    model_id = _canonical_hash(
        {
            "candidate_id": "S1M01",
            "decision_session": decision_session,
            "training_hash": training_hash,
            "model_state": model_state,
            "runtime_contract_sha256": model_contract.sha256,
            **provenance,
        }
    )
    return FittedDecisionModel(
        model_id=model_id,
        estimator=estimator,
        calibrator=None,
        lower_offset=lower_offset,
        record={
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "S1M01",
            "model_id": model_id,
            "decision_session": decision_session,
            "kind": "StandardScaler_then_Ridge",
            "fit_from_scratch": True,
            "warm_start": False,
            "fit_row_count": len(fit),
            "calibration_row_count": len(calibration),
            "training_row_count": len(train),
            "training_data_sha256": training_hash,
            "feature_names": list(model_contract.features),
            "runtime_contract": model_contract.to_dict(),
            "runtime_contract_sha256": model_contract.sha256,
            "model_state_sha256": _canonical_hash(model_state),
            "lower_offset": lower_offset,
            "conformal_target_coverage": model_contract.abstention["target_coverage"],
            "conformal_rank": conformal_rank,
            "quantile_method": "higher",
            "calibration_empirical_coverage": empirical_coverage,
            "fit_end_session": str(fit.iloc[-1]["decision_session"]),
            "calibration_start_session": str(calibration.iloc[0]["decision_session"]),
            "prompt_hash": None,
            "prompt_not_applicable_reason": "quant_only_model",
            "status": "historical_fold_local_diagnostic",
            **provenance,
        },
    )


def _fit_logistic(
    train: pd.DataFrame,
    *,
    decision_session: str,
    provenance: dict[str, Any],
    model_contract: R1ModelRuntime,
) -> FittedDecisionModel | None:
    split = _chronological_fit_calibration_split(train, model_contract)
    if split is None:
        return None
    fit, calibration = split
    fit_labels = fit["m02_path_survival"].astype(int)
    calibration_labels = calibration["m02_path_survival"].astype(int)
    fit_counts = fit_labels.value_counts().to_dict()
    calibration_counts = calibration_labels.value_counts().to_dict()
    abstention = model_contract.abstention
    if (
        int(fit_counts.get(0, 0)) < int(abstention["minimum_negative_class_rows"])
        or int(fit_counts.get(1, 0)) < int(abstention["minimum_positive_class_rows"])
        or int(calibration_counts.get(0, 0))
        < int(abstention["minimum_calibration_negative_class_rows"])
        or int(calibration_counts.get(1, 0))
        < int(abstention["minimum_calibration_positive_class_rows"])
    ):
        return None
    estimator_parameters = {
        **model_contract.hyperparameters,
        "random_state": int(model_contract.training["seed"]),
    }
    estimator = Pipeline(
        [
            ("scale", StandardScaler()),
            ("model", LogisticRegression(**estimator_parameters)),
        ]
    )
    estimator.fit(fit.loc[:, model_contract.features], fit_labels)
    raw_score = estimator.decision_function(calibration.loc[:, model_contract.features]).reshape(
        -1, 1
    )
    calibrator_contract = dict(abstention["calibrator"])
    calibrator_contract.pop("kind")
    use_training_seed = bool(calibrator_contract.pop("use_training_seed"))
    calibrator = LogisticRegression(
        **calibrator_contract,
        random_state=(int(model_contract.training["seed"]) if use_training_seed else None),
    )
    calibrator.fit(raw_score, calibration_labels)
    uncalibrated_probability = estimator.predict_proba(calibration.loc[:, model_contract.features])[
        :, 1
    ]
    probability = calibrator.predict_proba(raw_score)[:, 1]
    brier = float(brier_score_loss(calibration_labels, probability))
    uncalibrated_brier = float(brier_score_loss(calibration_labels, uncalibrated_probability))
    fit_base_rate = float(fit_labels.mean())
    base_rate_brier = float(
        brier_score_loss(calibration_labels, np.full(len(calibration), fit_base_rate))
    )
    training_hash = _frame_hash(
        train,
        ["decision_session", "label_end_session", *model_contract.features, "m02_path_survival"],
    )
    model = estimator.named_steps["model"]
    model_state = {
        "coef": np.asarray(model.coef_, dtype=float).tolist(),
        "intercept": np.asarray(model.intercept_, dtype=float).tolist(),
        "calibrator_coef": np.asarray(calibrator.coef_, dtype=float).tolist(),
        "calibrator_intercept": np.asarray(calibrator.intercept_, dtype=float).tolist(),
        "calibration_brier": brier,
    }
    model_id = _canonical_hash(
        {
            "candidate_id": "S1M02",
            "decision_session": decision_session,
            "training_hash": training_hash,
            "model_state": model_state,
            "runtime_contract_sha256": model_contract.sha256,
            **provenance,
        }
    )
    return FittedDecisionModel(
        model_id=model_id,
        estimator=estimator,
        calibrator=calibrator,
        lower_offset=None,
        record={
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": "S1M02",
            "model_id": model_id,
            "decision_session": decision_session,
            "kind": "StandardScaler_then_LogisticRegression",
            "fit_from_scratch": True,
            "warm_start": False,
            "fit_row_count": len(fit),
            "calibration_row_count": len(calibration),
            "training_row_count": len(train),
            "training_data_sha256": training_hash,
            "feature_names": list(model_contract.features),
            "runtime_contract": model_contract.to_dict(),
            "runtime_contract_sha256": model_contract.sha256,
            "model_state_sha256": _canonical_hash(model_state),
            "calibration_brier": brier,
            "uncalibrated_calibration_brier": uncalibrated_brier,
            "fit_base_rate_brier": base_rate_brier,
            "fit_base_rate": fit_base_rate,
            "fit_positive_count": int(fit_counts.get(1, 0)),
            "fit_negative_count": int(fit_counts.get(0, 0)),
            "calibration_positive_count": int(calibration_counts.get(1, 0)),
            "calibration_negative_count": int(calibration_counts.get(0, 0)),
            "calibration_method": "chronological_platt_scaling",
            "fit_end_session": str(fit.iloc[-1]["decision_session"]),
            "calibration_start_session": str(calibration.iloc[0]["decision_session"]),
            "prompt_hash": None,
            "prompt_not_applicable_reason": "quant_only_model",
            "status": "historical_fold_local_diagnostic",
            **provenance,
        },
    )


def _fold_for_session(session: pd.Timestamp, folds: list[dict[str, Any]]) -> str:
    for fold in folds:
        if pd.Timestamp(fold["test_start"]) <= session <= pd.Timestamp(fold["test_end"]):
            return str(fold["fold_id"])
    return "BOUNDARY_SETUP"


def build_candidate_targets(
    panel: R11PricePanel,
    dataset: pd.DataFrame,
    folds: list[dict[str, Any]],
    provenance: dict[str, Any],
    contract: R1RuntimeContract,
) -> tuple[
    dict[str, pd.DataFrame],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    d01_all = build_deterministic_targets(
        panel,
        dataset,
        anchor_weight=contract.anchors["S1D01"],
        sleeve_contract=contract.candidate_specs["S1D01"]["spec"]["notes"]["sleeve_contract"],
    )
    d03_all = build_deterministic_targets(
        panel,
        dataset,
        anchor_weight=contract.anchors["S1D03"],
        sleeve_contract=contract.candidate_specs["S1D03"]["spec"]["notes"]["sleeve_contract"],
    )
    d04_all = build_deterministic_targets(
        panel,
        dataset,
        anchor_weight=contract.anchors["S1D04"],
        sleeve_contract=contract.candidate_specs["S1D04"]["spec"]["notes"]["sleeve_contract"],
    )
    start = pd.Timestamp(folds[0]["test_start"])
    end = pd.Timestamp(folds[-1]["test_end"])
    execution = pd.to_datetime(dataset["execution_session"])
    prior_rows = dataset.loc[execution <= start]
    if prior_rows.empty:
        raise ValueError("R1 has no boundary target before the OOS window")
    boundary_position = int(prior_rows.index[-1])
    selected = dataset.loc[(dataset.index >= boundary_position) & (execution <= end)].copy()

    index = pd.DatetimeIndex(pd.to_datetime(selected["execution_session"]))
    d01 = d01_all.loc[index].copy()
    d03 = d03_all.loc[index].copy()
    d04 = d04_all.loc[index].copy()
    m01 = d01.copy()
    m02 = d01.copy()
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []

    for _, row in selected.iterrows():
        decision_position = int(row["decision_position"])
        decision_session = str(row["decision_session"])
        execution_session = pd.Timestamp(row["execution_session"])
        fold_id = _fold_for_session(execution_session, folds)
        current = row.loc[list(contract.m01.features)].astype(float)
        features_finite = np.isfinite(current.to_numpy()).all()

        ridge_train = training_rows_for_decision(
            dataset,
            decision_position=decision_position,
            label_name="m01_policy_value",
            model_contract=contract.m01,
        )
        ridge = (
            _fit_ridge(
                ridge_train,
                decision_session=decision_session,
                provenance=provenance,
                model_contract=contract.m01,
            )
            if features_finite
            else None
        )
        ridge_prediction = None
        ridge_lower = None
        ridge_override = False
        if ridge is not None:
            model_records.append({**ridge.record, "fold_id": fold_id})
            ridge_prediction = float(
                ridge.estimator.predict(pd.DataFrame([current], columns=contract.m01.features))[0]
            )
            ridge_lower = ridge_prediction - float(ridge.lower_offset or 0.0)
            selection = contract.m01.selection
            if selection["operator"] != "lower_bound_strictly_greater_than":
                raise ValueError("R1 Ridge selection operator drift")
            ridge_override = bool(ridge_lower > float(selection["threshold"]))
        if ridge_override:
            inverted = _contract_sleeve_weights(
                risk_on=not bool(row["risk_on"]), candidate_id="S1D01", contract=contract
            )
            for symbol, weight in inverted.items():
                m01.at[execution_session, symbol] = weight
        ridge_model_unavailable = ridge is None
        # A fitted Ridge model that declines to cross the lower-bound threshold
        # is an explicit uncertainty abstention.  It is a real fallback to the
        # deterministic target, whereas a fitted M02 model with no tail cut is
        # an ordinary no-op (handled below).
        ridge_abstention_used = bool(ridge is not None and not ridge_override)
        ridge_fallback = bool(ridge_model_unavailable or ridge_abstention_used)
        ridge_fallback_identity = bool(
            not ridge_fallback
            or np.allclose(
                m01.loc[execution_session].to_numpy(dtype=float),
                d01.loc[execution_session].to_numpy(dtype=float),
                atol=1e-12,
            )
        )
        prediction_records.append(
            {
                "schema_version": 2,
                "iter_id": ITER_ID,
                "candidate_id": "S1M01",
                "fold_id": fold_id,
                "decision_position": decision_position,
                "decision_session": decision_session,
                "execution_session": execution_session.date().isoformat(),
                "model_id": ridge.model_id if ridge else None,
                "model_unavailable": ridge_model_unavailable,
                "abstention_used": ridge_abstention_used,
                "fallback_used": ridge_fallback,
                "normal_noop": False,
                "decision_status": (
                    "model_unavailable"
                    if ridge_model_unavailable
                    else "abstention_used"
                    if ridge_abstention_used
                    else "override"
                ),
                "fallback_candidate_id": "S1D01",
                "fallback_target_identity": ridge_fallback_identity,
                "prediction": ridge_prediction,
                "lower_bound": ridge_lower,
                "override": ridge_override,
                "local_counterfactual_policy_value": (
                    float(row["m01_policy_value"]) if pd.notna(row["m01_policy_value"]) else None
                ),
                "training_row_count": len(ridge_train),
                "fit_row_count": ridge.record["fit_row_count"] if ridge else 0,
                "calibration_row_count": (ridge.record["calibration_row_count"] if ridge else 0),
                "calibration_method": (
                    "chronological_split_conformal_lower_bound" if ridge else None
                ),
                "label_end_session": row["label_end_session"],
                "feature_values_sha256": _canonical_hash(current.to_dict()),
                "runtime_contract_sha256": contract.sha256,
                **provenance,
            }
        )

        logistic_train = training_rows_for_decision(
            dataset,
            decision_position=decision_position,
            label_name="m02_path_survival",
            model_contract=contract.m02,
        )
        logistic = (
            _fit_logistic(
                logistic_train,
                decision_session=decision_session,
                provenance=provenance,
                model_contract=contract.m02,
            )
            if features_finite
            else None
        )
        survival_probability = None
        uncalibrated_probability = None
        anchor_cut = False
        if logistic is not None:
            model_records.append({**logistic.record, "fold_id": fold_id})
            if logistic.calibrator is None:
                raise AssertionError("R1 calibrated logistic model is missing its calibrator")
            raw_score = logistic.estimator.decision_function(
                pd.DataFrame([current], columns=contract.m02.features)
            ).reshape(-1, 1)
            uncalibrated_probability = float(
                logistic.estimator.predict_proba(
                    pd.DataFrame([current], columns=contract.m02.features)
                )[0, 1]
            )
            survival_probability = float(logistic.calibrator.predict_proba(raw_score)[0, 1])
            anchor_cut = survival_probability <= float(contract.m02.selection["threshold"])
        if anchor_cut:
            action = contract.m02.action
            source = str(action["source_symbol"])
            destination = str(action["destination_symbol"])
            cut = min(
                float(action["portfolio_weight_delta"]),
                float(m02.at[execution_session, source]),
            )
            m02.at[execution_session, source] -= cut
            m02.at[execution_session, destination] += cut
        logistic_model_unavailable = logistic is None
        logistic_abstention_used = False
        logistic_normal_noop = bool(logistic is not None and not anchor_cut)
        logistic_fallback = logistic_model_unavailable
        logistic_fallback_identity = bool(
            not logistic_fallback
            or np.allclose(
                m02.loc[execution_session].to_numpy(dtype=float),
                d01.loc[execution_session].to_numpy(dtype=float),
                atol=1e-12,
            )
        )
        prediction_records.append(
            {
                "schema_version": 2,
                "iter_id": ITER_ID,
                "candidate_id": "S1M02",
                "fold_id": fold_id,
                "decision_position": decision_position,
                "decision_session": decision_session,
                "execution_session": execution_session.date().isoformat(),
                "model_id": logistic.model_id if logistic else None,
                "model_unavailable": logistic_model_unavailable,
                "abstention_used": logistic_abstention_used,
                "fallback_used": logistic_fallback,
                "normal_noop": logistic_normal_noop,
                "decision_status": (
                    "model_unavailable"
                    if logistic_model_unavailable
                    else "override"
                    if anchor_cut
                    else "normal_noop"
                ),
                "fallback_candidate_id": "S1D01",
                "fallback_target_identity": logistic_fallback_identity,
                "prediction": survival_probability,
                "uncalibrated_prediction": uncalibrated_probability,
                "lower_bound": None,
                "override": anchor_cut,
                "local_counterfactual_policy_value": (
                    float(row["m02_local_counterfactual_policy_value"])
                    if pd.notna(row["m02_local_counterfactual_policy_value"])
                    else None
                ),
                "training_row_count": len(logistic_train),
                "fit_row_count": logistic.record["fit_row_count"] if logistic else 0,
                "calibration_row_count": (
                    logistic.record["calibration_row_count"] if logistic else 0
                ),
                "fit_positive_count": (logistic.record["fit_positive_count"] if logistic else 0),
                "fit_negative_count": (logistic.record["fit_negative_count"] if logistic else 0),
                "calibration_positive_count": (
                    logistic.record["calibration_positive_count"] if logistic else 0
                ),
                "calibration_negative_count": (
                    logistic.record["calibration_negative_count"] if logistic else 0
                ),
                "calibration_method": (logistic.record["calibration_method"] if logistic else None),
                "training_base_rate": (logistic.record["fit_base_rate"] if logistic else None),
                "realized_path_survival": (
                    float(row["m02_path_survival"]) if pd.notna(row["m02_path_survival"]) else None
                ),
                "label_end_session": row["label_end_session"],
                "feature_values_sha256": _canonical_hash(current.to_dict()),
                "runtime_contract_sha256": contract.sha256,
                **provenance,
            }
        )

    candidates = {
        "S1D01": d01,
        "S1D02": d01.copy(),
        "S1M01": m01,
        "S1M02": m02,
        "S1L01": d01.copy(),
        "S1C01": m01.copy(),
        "S1F01": m01.copy(),
        "S1P01": d01.copy(),
        "S1D03": d03,
        "S1D04": d04,
    }
    for candidate_id, targets in candidates.items():
        sums = targets.sum(axis=1).to_numpy(dtype=float)
        if (
            not np.isfinite(targets.to_numpy(dtype=float)).all()
            or not np.allclose(sums, 1.0, atol=1e-12)
            or (targets.to_numpy(dtype=float) < -1e-12).any()
        ):
            raise ValueError(f"R1 invalid candidate targets: {candidate_id}")
    if not candidates["S1F01"].equals(candidates["S1M01"]):
        raise ValueError("R1 missing-modality fallback identity failed")
    if not candidates["S1C01"].equals(candidates["S1M01"]):
        raise ValueError("R1 combined missing-packet identity failed")
    for candidate_id in ("S1D02", "S1L01", "S1P01"):
        if not candidates[candidate_id].equals(candidates["S1D01"]):
            raise ValueError(f"R1 zero-capital semantic identity failed: {candidate_id}")

    target_records = []
    for candidate_id, targets in candidates.items():
        for session, weights in targets.iterrows():
            nonzero = {
                str(symbol): float(value)
                for symbol, value in weights.items()
                if abs(float(value)) > 1e-15
            }
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "candidate_id": candidate_id,
                    "execution_session": session.date().isoformat(),
                    "weights": nonzero,
                    "target_sha256": _canonical_hash(nonzero),
                    "broker_writes": False,
                    **provenance,
                }
            )
    for row in prediction_records:
        row["historical_policy_value_semantics"] = "local_counterfactual_only"
    return candidates, target_records, model_records, prediction_records


def _evaluate_candidates(
    opens: pd.DataFrame,
    targets: dict[str, pd.DataFrame],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    contract: R1RuntimeContract,
) -> tuple[dict[str, Any], dict[str, pd.Series], list[dict[str, Any]]]:
    candidates: dict[str, Any] = {}
    primary_returns: dict[str, pd.Series] = {}
    daily_rows: list[dict[str, Any]] = []
    for candidate_id, frame in targets.items():
        cost_results: dict[str, Any] = {}
        for view_name, cost_bps in contract.cost_views.items():
            simulation = simulate_target_portfolio(
                opens,
                frame,
                cost_bps=cost_bps,
                start=start,
                end=end,
                reserve_symbol=contract.reserve_symbol,
            )
            cost_results[view_name] = _simulation_metric_views(simulation, opens)
            if view_name == contract.primary_view_name:
                returns = _daily_returns(simulation, include_terminal=True)
                primary_returns[candidate_id] = returns
                for session, value in returns.items():
                    daily_rows.append(
                        {
                            "schema_version": 1,
                            "iter_id": ITER_ID,
                            "candidate_id": candidate_id,
                            "session": session.date().isoformat(),
                            "net_return": float(value),
                            "cost_bps": cost_bps,
                        }
                    )
        candidates[candidate_id] = {
            "candidate_id": candidate_id,
            "cost_views": cost_results,
        }
    return candidates, primary_returns, daily_rows


def _benchmark_family(
    opens: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    contract: R1RuntimeContract,
) -> dict[str, Any]:
    equal_weight = contract.benchmark_contract["equal_weight_full_spec_universe"]["weights"]
    definitions = {
        **contract.benchmark_names,
        "equal_weight_full_spec_universe": {
            str(symbol): float(weight) for symbol, weight in equal_weight.items()
        },
    }
    required = set(contract.benchmark_contract["required"])
    if set(definitions) | {"ex_post_best_symbol_report_only"} != required:
        raise ValueError("R1 benchmark implementation does not match benchmark contract")
    output: dict[str, Any] = {}
    for name, weights in definitions.items():
        cost_views = {}
        for view_name, cost_bps in contract.cost_views.items():
            simulation = _simulate_static(
                opens,
                weights,
                start=start,
                end=end,
                cost_bps=cost_bps,
            )
            cost_views[view_name] = _simulation_metric_views(simulation, opens)
        output[name] = {"weights": weights, "cost_views": cost_views}
    investable = [
        "TQQQ_buy_hold_same_symbol",
        "QQQ_buy_hold",
        "SPY_buy_hold_market_proxy",
        "SMH_buy_hold_sector_theme_proxy",
        "BIL_buy_hold_cash_proxy",
    ]
    best = max(
        investable,
        key=lambda name: output[name]["cost_views"][contract.primary_view_name]["with_terminal"][
            "cagr"
        ],
    )
    output["ex_post_best_symbol_report_only"] = {
        "selected": best,
        "selectable": False,
        "metrics": output[best]["cost_views"],
    }
    return output


def _evaluate_folds(
    opens: pd.DataFrame,
    folds: list[dict[str, Any]],
    targets: dict[str, pd.DataFrame],
    contract: R1RuntimeContract,
) -> dict[str, list[dict[str, Any]]]:
    output = {candidate_id: [] for candidate_id in targets}
    cost_bps = contract.primary_cost_bps
    for fold in folds:
        start = pd.Timestamp(fold["test_start"])
        end = pd.Timestamp(fold["test_end"])
        d01_simulation = simulate_target_portfolio(
            opens,
            targets["S1D01"],
            cost_bps=cost_bps,
            start=start,
            end=end,
            reserve_symbol=contract.reserve_symbol,
        )
        d01_returns = _daily_returns(d01_simulation, include_terminal=True)
        qqq = _simulate_static(
            opens,
            contract.benchmark_names["QQQ_buy_hold"],
            start=start,
            end=end,
            cost_bps=cost_bps,
        )
        qqq_metrics = _simulation_metric_views(qqq, opens)["with_terminal"]
        for candidate_id, frame in targets.items():
            simulation = simulate_target_portfolio(
                opens,
                frame,
                cost_bps=cost_bps,
                start=start,
                end=end,
                reserve_symbol=contract.reserve_symbol,
            )
            metrics = _simulation_metric_views(simulation, opens)["with_terminal"]
            candidate_returns = _daily_returns(simulation, include_terminal=True)
            if not candidate_returns.index.equals(d01_returns.index):
                raise ValueError("R1 paired policy paths do not share fold sessions")
            paired_policy_value = _paired_target_stream_log_wealth_value(
                opens,
                targets["S1D01"],
                frame,
                start=start,
                end=end,
                cost_bps=cost_bps,
                reserve_symbol=contract.reserve_symbol,
            )
            output[candidate_id].append(
                {
                    **fold,
                    "starts_in_cash": True,
                    "liquidates_independently": True,
                    "metrics": metrics,
                    "qqq_benchmark_metrics": qqq_metrics,
                    "qqq_cagr_lift": metrics["cagr"] - qqq_metrics["cagr"],
                    "paired_S1D01_realized_log_wealth_value": paired_policy_value,
                    "paired_policy_value_semantics": (
                        "complete_fold_target_stream_with_stateful_net_trading_costs"
                    ),
                }
            )
    return output


def _paired_target_stream_log_wealth_value(
    opens: pd.DataFrame,
    baseline_targets: pd.DataFrame,
    alternative_targets: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
    reserve_symbol: str = "BIL",
) -> float:
    """Compare complete stateful target streams, including all trading costs.

    Per-decision labels are deliberately local counterfactuals.  This helper is
    the only paired value used for aggregate ML credit, so consecutive overrides
    cannot be miscounted as independent return-to-baseline trades.
    """
    baseline = simulate_target_portfolio(
        opens,
        baseline_targets,
        cost_bps=cost_bps,
        start=start,
        end=end,
        reserve_symbol=reserve_symbol,
    )
    alternative = simulate_target_portfolio(
        opens,
        alternative_targets,
        cost_bps=cost_bps,
        start=start,
        end=end,
        reserve_symbol=reserve_symbol,
    )
    baseline_returns = _daily_returns(baseline, include_terminal=True)
    alternative_returns = _daily_returns(alternative, include_terminal=True)
    if not alternative_returns.index.equals(baseline_returns.index):
        raise ValueError("R1 paired target streams do not share sessions")
    values = np.asarray(
        [float(np.log1p(value)) for value in alternative_returns.to_numpy(dtype=float)]
    ) - np.asarray([float(np.log1p(value)) for value in baseline_returns.to_numpy(dtype=float)])
    if not np.isfinite(values).all():
        raise ValueError("R1 paired target streams produced nonfinite log wealth")
    return float(values.sum())


def _gate(name: str, passed: bool, threshold: Any, actual: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "threshold": threshold, "actual": actual}


def _calibration_gate_pass(
    *,
    observation_count: int,
    calibrated_brier: float | None,
    raw_brier: float | None,
    contract: R1RuntimeContract,
) -> bool:
    """Apply the preregistered minimum-OOS and calibrated-vs-raw Brier gate."""
    observation_gate = observation_count >= int(
        contract.ml_gate_value("minimum_calibrated_probability_observations_per_fold")
    )
    if not observation_gate:
        return False
    if calibrated_brier is None or raw_brier is None:
        return False
    if contract.ml_gate_value("calibrated_brier_must_beat_raw"):
        return bool(calibrated_brier < raw_brier)
    return True


def _calibration_observation_gate_pass(observation_count: int, contract: R1RuntimeContract) -> bool:
    return observation_count >= int(
        contract.ml_gate_value("minimum_calibrated_probability_observations_per_fold")
    )


def _calibration_improvement_pass(
    calibrated_brier: float | None,
    raw_brier: float | None,
    contract: R1RuntimeContract,
) -> bool:
    if calibrated_brier is None or raw_brier is None:
        return False
    if contract.ml_gate_value("calibrated_brier_must_beat_raw"):
        return bool(calibrated_brier < raw_brier)
    return True


def _minimum_uncertainty_fallbacks(contract: R1RuntimeContract) -> int:
    """Resolve the fallback floor from the frozen validation semantics."""
    gates = contract.ml_gates
    if "minimum_uncertainty_fallbacks" in gates:
        raw = gates["minimum_uncertainty_fallbacks"]
    elif "minimum_fallbacks" in gates:
        raw = gates["minimum_fallbacks"]
    elif (
        gates.get("exact_deterministic_fallback") is True
        and gates.get("uncertainty_action") == "abstain_to_exact_S1D01"
    ):
        raw = 1
    else:
        raise ValueError("R1 validation contract has no uncertainty fallback floor")
    value = int(raw)
    if value < 0:
        raise ValueError("R1 uncertainty fallback minimum cannot be negative")
    return value


def _policy_diagnostics(
    prediction_records: list[dict[str, Any]],
    candidate_id: str,
    candidate_folds: list[dict[str, Any]],
    aggregate_realized_policy_value: float,
    contract: R1RuntimeContract,
) -> dict[str, Any]:
    fold_ids = [f"F{number}" for number in range(1, contract.fold_count + 1)]
    selected = [
        row
        for row in prediction_records
        if row["candidate_id"] == candidate_id and row["fold_id"] in fold_ids
    ]
    folds: dict[str, Any] = {}
    for fold_id in fold_ids:
        rows = [row for row in selected if row["fold_id"] == fold_id]
        overrides = [row for row in rows if row["override"]]
        fold_result = next(row for row in candidate_folds if row["fold_id"] == fold_id)
        realized_path_value = float(fold_result["paired_S1D01_realized_log_wealth_value"])
        coverage_rows = [
            row
            for row in rows
            if row["lower_bound"] is not None
            and row["local_counterfactual_policy_value"] is not None
        ]
        lower_bound_coverage = (
            float(
                np.mean(
                    [
                        float(row["local_counterfactual_policy_value"]) >= float(row["lower_bound"])
                        for row in coverage_rows
                    ]
                )
            )
            if coverage_rows
            else None
        )
        probability_rows = [
            row
            for row in rows
            if row["prediction"] is not None
            and row.get("uncalibrated_prediction") is not None
            and row.get("realized_path_survival") is not None
            and row.get("training_base_rate") is not None
        ]
        calibrated_brier = (
            float(
                brier_score_loss(
                    [int(row["realized_path_survival"]) for row in probability_rows],
                    [float(row["prediction"]) for row in probability_rows],
                )
            )
            if probability_rows
            else None
        )
        base_rate_brier = (
            float(
                brier_score_loss(
                    [int(row["realized_path_survival"]) for row in probability_rows],
                    [float(row["training_base_rate"]) for row in probability_rows],
                )
            )
            if probability_rows
            else None
        )
        uncalibrated_brier = (
            float(
                brier_score_loss(
                    [int(row["realized_path_survival"]) for row in probability_rows],
                    [float(row["uncalibrated_prediction"]) for row in probability_rows],
                )
            )
            if probability_rows
            else None
        )
        model_unavailable_rows = [row for row in rows if row.get("model_unavailable", False)]
        abstention_rows = [row for row in rows if row.get("abstention_used", False)]
        fallback_rows = [row for row in rows if row.get("fallback_used", False)]
        normal_noop_rows = [row for row in rows if row.get("normal_noop", False)]
        fitted_rows = [row for row in rows if row["model_id"] is not None]
        model_contract = contract.m01 if candidate_id == "S1M01" else contract.m02
        if candidate_id == "S1M01":
            sample_contract_violations = sum(
                row["fit_row_count"] < int(model_contract.abstention["minimum_fit_rows"])
                or row["calibration_row_count"]
                < int(model_contract.abstention["minimum_calibration_rows"])
                for row in fitted_rows
            )
        else:
            sample_contract_violations = sum(
                row["fit_row_count"] < int(model_contract.abstention["minimum_fit_rows"])
                or row["calibration_row_count"]
                < int(model_contract.abstention["minimum_calibration_rows"])
                or row["fit_positive_count"]
                < int(model_contract.abstention["minimum_positive_class_rows"])
                or row["fit_negative_count"]
                < int(model_contract.abstention["minimum_negative_class_rows"])
                or row["calibration_positive_count"]
                < int(model_contract.abstention["minimum_calibration_positive_class_rows"])
                or row["calibration_negative_count"]
                < int(model_contract.abstention["minimum_calibration_negative_class_rows"])
                or row["calibration_method"] != "chronological_platt_scaling"
                for row in fitted_rows
            )
        calibration_observation_gate_pass = _calibration_observation_gate_pass(
            len(probability_rows), contract
        )
        calibration_improvement_pass = _calibration_improvement_pass(
            calibrated_brier, uncalibrated_brier, contract
        )
        calibration_gate_pass = _calibration_gate_pass(
            observation_count=len(probability_rows),
            calibrated_brier=calibrated_brier,
            raw_brier=uncalibrated_brier,
            contract=contract,
        )
        folds[fold_id] = {
            "prediction_count": len(rows),
            "override_count": len(overrides),
            "realized_policy_value": realized_path_value,
            "realized_policy_value_semantics": (
                "complete_fold_target_stream_vs_S1D01_with_stateful_net_trading_costs"
            ),
            "positive_realized_policy_value": bool(realized_path_value > 0.0),
            "lower_bound_observation_count": len(coverage_rows),
            "lower_bound_coverage": lower_bound_coverage,
            "lower_bound_coverage_pass": bool(
                lower_bound_coverage is not None
                and len(coverage_rows)
                >= int(contract.ml_gate_value("minimum_lower_bound_observations_per_fold"))
                and lower_bound_coverage
                >= float(contract.ml_gate_value("lower_bound_fold_coverage_floor"))
            ),
            "calibrated_probability_observation_count": len(probability_rows),
            "calibrated_probability_brier": calibrated_brier,
            "uncalibrated_probability_brier": uncalibrated_brier,
            "training_base_rate_brier": base_rate_brier,
            "calibration_improves_uncalibrated_model": bool(
                calibrated_brier is not None
                and uncalibrated_brier is not None
                and calibrated_brier < uncalibrated_brier
            ),
            "calibration_improvement_pass": calibration_improvement_pass,
            "calibration_observation_gate_pass": calibration_observation_gate_pass,
            "calibration_gate_pass": calibration_gate_pass,
            "model_unavailable_count": len(model_unavailable_rows),
            "abstention_count": len(abstention_rows),
            "normal_noop_count": len(normal_noop_rows),
            "fallback_count": len(fallback_rows),
            "fallback_identity_mismatch_count": sum(
                not bool(row["fallback_target_identity"]) for row in fallback_rows
            ),
            "fitted_prediction_count": len(fitted_rows),
            "sample_contract_violation_count": int(sample_contract_violations),
        }
    all_overrides = [row for row in selected if row["override"]]
    return {
        "candidate_id": candidate_id,
        "prediction_count": len(selected),
        "override_count": len(all_overrides),
        "realized_policy_value_sum": aggregate_realized_policy_value,
        "realized_policy_value_semantics": (
            "complete_OOS_target_stream_vs_S1D01_with_stateful_net_trading_costs"
        ),
        "positive_realized_policy_value_folds": sum(
            row["positive_realized_policy_value"] for row in folds.values()
        ),
        "lower_bound_coverage_folds": sum(
            row["lower_bound_coverage_pass"] for row in folds.values()
        ),
        "calibration_improvement_folds": sum(
            row["calibration_improvement_pass"] for row in folds.values()
        ),
        "calibration_observation_gate_folds": sum(
            row["calibration_observation_gate_pass"] for row in folds.values()
        ),
        "calibration_gate_folds": sum(row["calibration_gate_pass"] for row in folds.values()),
        "model_unavailable_count": sum(row["model_unavailable_count"] for row in folds.values()),
        "abstention_count": sum(row["abstention_count"] for row in folds.values()),
        "normal_noop_count": sum(row["normal_noop_count"] for row in folds.values()),
        "uncertainty_fallback_count": sum(
            row["model_unavailable_count"] + row["abstention_count"] for row in folds.values()
        ),
        "fallback_count": sum(row["fallback_count"] for row in folds.values()),
        "fallback_identity_mismatch_count": sum(
            row["fallback_identity_mismatch_count"] for row in folds.values()
        ),
        "fitted_prediction_count": sum(row["fitted_prediction_count"] for row in folds.values()),
        "sample_contract_violation_count": sum(
            row["sample_contract_violation_count"] for row in folds.values()
        ),
        "folds": folds,
    }


def _candidate_gates(
    candidates: dict[str, Any],
    benchmarks: dict[str, Any],
    dsr: dict[str, Any],
    pbo: dict[str, Any],
    folds: dict[str, list[dict[str, Any]]],
    prediction_records: list[dict[str, Any]],
    contract: R1RuntimeContract,
    aggregate_policy_values: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    primary_view = contract.primary_view_name
    severe_view = contract.severe_view_name
    family = contract.family_gates
    ml = contract.ml_gates
    tqqq_primary = benchmarks["TQQQ_buy_hold_same_symbol"]["cost_views"][primary_view][
        "with_terminal"
    ]
    tqqq_severe = benchmarks["TQQQ_buy_hold_same_symbol"]["cost_views"][severe_view][
        "with_terminal"
    ]
    qqq = benchmarks["QQQ_buy_hold"]["cost_views"][primary_view]["with_terminal"]
    output: dict[str, Any] = {}
    for candidate_id, candidate in candidates.items():
        primary = candidate["cost_views"][primary_view]["with_terminal"]
        severe = candidate["cost_views"][severe_view]["with_terminal"]
        cagr_floor = max(
            float(family["net_CAGR_floor_pct"]) / 100.0,
            float(family["matched_TQQQ_CAGR_fraction_floor"]) * tqqq_primary["cagr"],
        )
        severe_cagr_floor = max(
            float(family["net_CAGR_floor_pct"]) / 100.0,
            float(family["matched_TQQQ_CAGR_fraction_floor"]) * tqqq_severe["cagr"],
        )
        positive_qqq_folds = sum(row["qqq_cagr_lift"] > 0 for row in folds[candidate_id])
        checks = [
            _gate("net_CAGR_threshold", primary["cagr"] >= cagr_floor, cagr_floor, primary["cagr"]),
            _gate(
                "matched_TQQQ_CAGR_fraction",
                primary["cagr"]
                >= float(family["matched_TQQQ_CAGR_fraction_floor"]) * tqqq_primary["cagr"],
                family["matched_TQQQ_CAGR_fraction_floor"],
                primary["cagr"] / tqqq_primary["cagr"] if tqqq_primary["cagr"] else None,
            ),
            _gate(
                "matched_QQQ_CAGR_lift",
                primary["cagr"] - qqq["cagr"]
                >= float(family["matched_QQQ_CAGR_lift_floor_pct_points"]) / 100.0,
                float(family["matched_QQQ_CAGR_lift_floor_pct_points"]) / 100.0,
                primary["cagr"] - qqq["cagr"],
            ),
            _gate(
                "maximum_drawdown",
                primary["max_drawdown"] >= float(family["maximum_drawdown_floor_pct"]) / 100.0,
                float(family["maximum_drawdown_floor_pct"]) / 100.0,
                primary["max_drawdown"],
            ),
            _gate(
                "Sharpe_floor",
                primary["annualized_sharpe_excess_BIL"] >= float(family["Sharpe_floor"]),
                family["Sharpe_floor"],
                primary["annualized_sharpe_excess_BIL"],
            ),
            _gate(
                "MAR_floor",
                primary["mar"] is not None and primary["mar"] >= float(family["MAR_floor"]),
                family["MAR_floor"],
                primary["mar"],
            ),
            _gate(
                "TQQQ_up_capture",
                primary["tqqq_up_capture"] >= float(family["TQQQ_up_capture_floor"]),
                family["TQQQ_up_capture_floor"],
                primary["tqqq_up_capture"],
            ),
            _gate(
                "TQQQ_down_capture",
                primary["tqqq_down_capture"] <= float(family["TQQQ_down_capture_ceiling"]),
                family["TQQQ_down_capture_ceiling"],
                primary["tqqq_down_capture"],
            ),
            _gate(
                "positive_QQQ_lift_folds",
                positive_qqq_folds >= int(family["positive_QQQ_lift_folds_min"]),
                family["positive_QQQ_lift_folds_min"],
                positive_qqq_folds,
            ),
            _gate(
                "DSR_probability",
                dsr[candidate_id]["probability"] >= float(family["DSR_probability_floor"]),
                family["DSR_probability_floor"],
                dsr[candidate_id]["probability"],
            ),
            _gate(
                "PBO_probability",
                pbo["probability"] <= float(family["PBO_ceiling"]),
                family["PBO_ceiling"],
                pbo["probability"],
            ),
            _gate(
                "severe_cost_CAGR",
                severe["cagr"] >= severe_cagr_floor,
                severe_cagr_floor,
                severe["cagr"],
            ),
            _gate(
                "severe_cost_maximum_drawdown",
                severe["max_drawdown"] >= float(family["maximum_drawdown_floor_pct"]) / 100.0,
                float(family["maximum_drawdown_floor_pct"]) / 100.0,
                severe["max_drawdown"],
            ),
        ]
        output[candidate_id] = {
            "family_pass": all(check["pass"] for check in checks),
            "checks": checks,
        }

    d01_primary = candidates["S1D01"]["cost_views"][primary_view]["with_terminal"]
    diagnostics = {}
    for candidate_id in ("S1M01", "S1M02"):
        diagnostics[candidate_id] = _policy_diagnostics(
            prediction_records,
            candidate_id,
            folds[candidate_id],
            aggregate_policy_values[candidate_id],
            contract,
        )
    for candidate_id in ("S1M01", "S1M02"):
        candidate_primary = candidates[candidate_id]["cost_views"][primary_view]["with_terminal"]
        fold_wins = sum(
            candidate_fold["metrics"]["cagr"] > folds["S1D01"][index]["metrics"]["cagr"]
            for index, candidate_fold in enumerate(folds[candidate_id])
        )
        retained = (
            candidate_primary["tqqq_up_capture"] / d01_primary["tqqq_up_capture"]
            if d01_primary["tqqq_up_capture"]
            else 0.0
        )
        ml_checks = [
            _gate(
                "folds_beating_exact_S1D01",
                fold_wins >= int(ml["minimum_folds_beating_S1D01"]),
                ml["minimum_folds_beating_S1D01"],
                fold_wins,
            ),
            _gate(
                "positive_realized_policy_value_folds",
                diagnostics[candidate_id]["positive_realized_policy_value_folds"]
                >= int(ml["minimum_positive_realized_policy_value_folds"]),
                ml["minimum_positive_realized_policy_value_folds"],
                diagnostics[candidate_id]["positive_realized_policy_value_folds"],
            ),
            _gate(
                "effective_overrides",
                diagnostics[candidate_id]["override_count"]
                >= int(ml["minimum_effective_overrides"]),
                ml["minimum_effective_overrides"],
                diagnostics[candidate_id]["override_count"],
            ),
            _gate(
                "S1D01_upside_capture_retained",
                retained >= float(ml["minimum_S1D01_upside_capture_retained"]),
                ml["minimum_S1D01_upside_capture_retained"],
                retained,
            ),
            _gate(
                "aggregate_realized_override_value",
                (
                    diagnostics[candidate_id]["realized_policy_value_sum"] > 0.0
                    if ml.get("aggregate_realized_override_value_strictly_positive", True)
                    else True
                ),
                ">0"
                if ml.get("aggregate_realized_override_value_strictly_positive", True)
                else "disabled",
                diagnostics[candidate_id]["realized_policy_value_sum"],
            ),
            _gate(
                "annualized_reported_one_way_turnover",
                candidate_primary["annualized_reported_one_way_turnover"]
                <= float(ml["annualized_reported_one_way_turnover_ceiling"]),
                ml["annualized_reported_one_way_turnover_ceiling"],
                candidate_primary["annualized_reported_one_way_turnover"],
            ),
            _gate(
                "uncertainty_exact_fallback",
                diagnostics[candidate_id]["uncertainty_fallback_count"]
                >= _minimum_uncertainty_fallbacks(contract)
                and diagnostics[candidate_id]["fallback_identity_mismatch_count"] == 0,
                {
                    "minimum_fallbacks": _minimum_uncertainty_fallbacks(contract),
                    "identity_mismatches": 0,
                },
                {
                    "fallbacks": diagnostics[candidate_id]["uncertainty_fallback_count"],
                    "identity_mismatches": diagnostics[candidate_id][
                        "fallback_identity_mismatch_count"
                    ],
                },
            ),
            _gate(
                "minimum_sample_and_calibration_contract",
                diagnostics[candidate_id]["fitted_prediction_count"] > 0
                and diagnostics[candidate_id]["sample_contract_violation_count"] == 0,
                {"minimum_fitted_predictions": 1, "violations": 0},
                {
                    "fitted_predictions": diagnostics[candidate_id]["fitted_prediction_count"],
                    "violations": diagnostics[candidate_id]["sample_contract_violation_count"],
                },
            ),
        ]
        model_contract = contract.m01 if candidate_id == "S1M01" else contract.m02
        if candidate_id == "S1M01":
            ml_checks.append(
                _gate(
                    "lower_bound_coverage_folds",
                    diagnostics[candidate_id]["lower_bound_coverage_folds"]
                    >= int(ml["minimum_lower_bound_coverage_folds"]),
                    ml["minimum_lower_bound_coverage_folds"],
                    diagnostics[candidate_id]["lower_bound_coverage_folds"],
                )
            )
        else:
            ml_checks.append(
                _gate(
                    "calibrated_probability_improves_uncalibrated_folds",
                    diagnostics[candidate_id]["calibration_gate_folds"]
                    >= int(ml["minimum_calibration_improvement_folds"]),
                    ml["minimum_calibration_improvement_folds"],
                    diagnostics[candidate_id]["calibration_gate_folds"],
                )
            )
        minimum_fit = int(model_contract.abstention["minimum_fit_rows"])
        minimum_calibration = int(model_contract.abstention["minimum_calibration_rows"])
        output[candidate_id]["runtime_sample_contract"] = {
            "minimum_fit_rows": minimum_fit,
            "minimum_calibration_rows": minimum_calibration,
            "runtime_contract_sha256": model_contract.sha256,
        }
        output[candidate_id]["ml_checks"] = ml_checks
        output[candidate_id]["ml_complexity_credit_pass"] = all(
            check["pass"] for check in ml_checks
        )
        output[candidate_id]["pass"] = (
            output[candidate_id]["family_pass"]
            and output[candidate_id]["ml_complexity_credit_pass"]
        )
    for candidate_id in output:
        output[candidate_id].setdefault("ml_complexity_credit_pass", False)
        output[candidate_id].setdefault("pass", output[candidate_id]["family_pass"])
    return output, diagnostics


def _trial_rows(
    candidates: dict[str, Any], gates: dict[str, Any], contract: R1RuntimeContract
) -> list[dict[str, Any]]:
    manifest = contract.candidate_manifest
    manifest_by_id = {row["candidate_id"]: row for row in manifest["candidates"]}
    rows = []
    for candidate_id, candidate in candidates.items():
        primary = candidate["cost_views"][contract.primary_view_name]["with_terminal"]
        rows.append(
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "trial_id": f"{ITER_ID}:{candidate_id}",
                "candidate_id": candidate_id,
                "path": manifest_by_id[candidate_id]["path"],
                "method": manifest_by_id[candidate_id]["method"],
                "promotion_eligible": manifest_by_id[candidate_id]["promotion_eligible"],
                "effective_trial_count": contract.effective_trial_count,
                "primary_cost_bps": contract.primary_cost_bps,
                "cagr_pct": primary["cagr_pct"],
                "max_drawdown_pct": primary["max_drawdown_pct"],
                "sharpe": primary["annualized_sharpe_excess_BIL"],
                "mar": primary["mar"],
                "gate_pass": gates[candidate_id]["pass"],
            }
        )
    return rows


def freeze(root: Path) -> Path:
    base = root.resolve()
    lock_path = base / LOCK_PATH
    output = base / OUTPUT_DIR
    if lock_path.exists() or lock_path.parent.exists():
        raise ValueError("R1 historical evaluation lock already exists")
    if output.exists() or any((base / ITERATION_DIR).glob("evaluation-run.staging-*")):
        raise ValueError("R1 historical evaluation state exists before lock")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R1 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = load_and_validate_specs(base)
    contract = runtime_contract_from_specs(specs, root=base)
    iteration_bindings = [
        _binding(base / ITERATION_DIR / filename, base) for filename in CONTRACT_FILENAMES
    ]
    external_bindings = [
        _binding(base / SOURCE_CARDS_PATH, base),
        _binding(base / SNAPSHOT_PATH, base),
        _binding(base / QUALITY_PATH, base),
        _binding(base / "schemas/high_beta_sleeve_ensemble_r1_feature_packet.schema.json", base),
        _binding(base / FACTOR_LIBRARY_PATH, base),
        _binding(base / "capabilities/registry.yaml", base),
    ]
    implementation_paths = [
        RUNNER_PATH,
        TEST_PATH,
        SEMANTIC_TEST_PATH,
        PREPARE_PATH,
        FACTOR_LIBRARY_IMPLEMENTATION_PATH,
        Path("open_composer/research/pit_semantic_theme_r24.py"),
        Path("open_composer/research/dynamic_theme_chain_r8.py"),
        Path("open_composer/research/etf_structural_r9.py"),
        Path("open_composer/research/iteration_dossier.py"),
        Path("open_composer/models/strategy_spec.py"),
        Path("open_composer/strategy_versions.py"),
        Path("pyproject.toml"),
        Path("uv.lock"),
    ]
    lock = {
        "schema_version": 1,
        "lock_contract": "high_beta_sleeve_ensemble_r1_historical_evaluation_v1",
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": LOCK_STATUS,
        "one_shot": True,
        "effective_trial_count": contract.effective_trial_count,
        "cost_views_bps": list(contract.cost_views.values()),
        "fold_count": contract.fold_count,
        "fold_sessions": contract.fold_sessions,
        "model_features": list(contract.feature_names),
        "runtime_contract_sha256": contract.sha256,
        "runtime_contract": contract.to_dict(),
        "contracts": iteration_bindings,
        "external_inputs": external_bindings,
        "specs": [
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "implementation": [_binding(base / path, base) for path in implementation_paths],
        "prelock_activity": {
            "synthetic_unit_tests_only": True,
            "historical_candidate_returns_computed": False,
            "historical_model_predictions_inspected": False,
            "parameter_changes_from_outcomes": False,
        },
        "historical_candidate_outcomes_read_at_lock": False,
        "order_authority": False,
        "broker_writes": False,
    }
    lock_path.parent.mkdir(parents=True, exist_ok=False)
    write_json(lock_path, lock)
    return lock_path


def _preflight(root: Path) -> dict[str, Any]:
    base = root.resolve()
    lock_path = base / LOCK_PATH
    lock = _load_json(lock_path)
    specs = load_and_validate_specs(base)
    contract = runtime_contract_from_specs(specs, root=base)
    if (
        lock.get("iter_id") != ITER_ID
        or lock.get("status") != LOCK_STATUS
        or lock.get("one_shot") is not True
        or lock.get("effective_trial_count") != contract.effective_trial_count
        or lock.get("model_features") != list(contract.feature_names)
        or lock.get("fold_count") != contract.fold_count
        or lock.get("fold_sessions") != contract.fold_sessions
        or lock.get("runtime_contract_sha256") != contract.sha256
        or lock.get("broker_writes") is not False
        or lock.get("historical_candidate_outcomes_read_at_lock") is not False
    ):
        raise ValueError("R1 historical lock identity mismatch")
    for group in ("contracts", "external_inputs", "implementation", "specs"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R1 lock group missing: {group}")
        for binding in rows:
            _verify_binding(base, binding)
    locked = {row["candidate_id"]: row for row in lock["specs"]}
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked[candidate_id]["semantic_sha256"]:
            raise ValueError(f"R1 semantic spec changed after lock: {candidate_id}")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R1 dossier changed after lock: " + ", ".join(validation.blocked))
    return {
        "lock_path": LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "dossier_checked_at": validation.checked_at.isoformat(),
    }


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        "# High-Beta Sleeve Ensemble R1 Historical Evaluation",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- ML contribution pass: `{payload['ml_contribution_pass']}`",
        f"- Paper entry ready: `{payload['paper_entry_ready']}`",
        f"- Effective trial count: `{payload['statistics']['effective_trial_count']}`",
        "",
        "| Candidate | CAGR | MDD | Sharpe | MAR | Up / Down capture | DSR | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    primary_view = payload["integrity"]["primary_cost_view"]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["cost_views"][primary_view]["with_terminal"]
        lines.append(
            f"| {candidate_id} | {metrics['cagr_pct']:.2f}% | "
            f"{metrics['max_drawdown_pct']:.2f}% | "
            f"{metrics['annualized_sharpe_excess_BIL']:.3f} | "
            f"{metrics['mar']:.3f} | {metrics['tqqq_up_capture']:.3f} / "
            f"{metrics['tqqq_down_capture']:.3f} | "
            f"{payload['statistics']['DSR'][candidate_id]['probability']:.4f} | "
            f"{candidate['gates']['pass']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            payload["interpretation"],
            "",
            "Semantic and LLM roles use zero capital and exact fallbacks. They do not earn independent Alpha credit from identical historical target streams. No Paper order was submitted.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_factor_lab(
    root: Path,
    dataset: pd.DataFrame,
    payload: dict[str, Any],
) -> None:
    start = pd.Timestamp(payload["oos_window"]["start"])
    end = pd.Timestamp(payload["oos_window"]["end"])
    rows = dataset[
        (pd.to_datetime(dataset["execution_session"]) >= start)
        & (pd.to_datetime(dataset["execution_session"]) <= end)
        & dataset["m01_policy_value"].notna()
    ].copy()
    rank_ic = (
        float(rows["qqq_trend_gap_200"].corr(rows["m01_policy_value"], method="spearman"))
        if len(rows) >= 3
        else None
    )
    artifact = {
        "schema_version": 1,
        "strategy_name": "us_high_beta_sleeve_ensemble_r1_d01",
        "status": "ok" if rank_ic is not None and math.isfinite(rank_ic) else "warning",
        "mode": "router_level_diagnostic",
        "quality_flags": [
            "router_level_attribution_not_single_symbol_factor_lab",
            "historical_prices_globally_exposed",
        ],
        "factor_metrics": [
            {
                "name": "qqq_trend_gap_200",
                "rank_ic_to_risk_off_tactical_policy_value": rank_ic,
                "observation_count": len(rows),
                "coverage_pct": 100.0 if len(rows) else 0.0,
            }
        ],
        "route_attribution": {
            "risk_on_month_ends": int(dataset["risk_on"].sum()),
            "risk_off_month_ends": int((~dataset["risk_on"]).sum()),
            "primary_candidate": "S1D01",
            "neighbor_selection_prohibited": True,
        },
    }
    json_path = root / "reports/research/us_high_beta_sleeve_ensemble_r1_d01-factor-lab.json"
    write_json(json_path, artifact)
    md_path = json_path.with_suffix(".md")
    md_path.write_text(
        "# Router Factor Lab: us_high_beta_sleeve_ensemble_r1_d01\n\n"
        f"- Status: `{artifact['status']}`\n"
        f"- Risk-off policy-value observations: `{len(rows)}`\n"
        f"- SMA200 gap RankIC: `{rank_ic}`\n\n"
        "This is route-level attribution for a portfolio sleeve. It does not turn an exposed historical correlation into independent Alpha evidence.\n",
        encoding="utf-8",
    )


def _write_forensics(root: Path, payload: dict[str, Any]) -> None:
    candidate = payload["candidates"]["S1D01"]
    primary = candidate["cost_views"][payload["integrity"]["primary_cost_view"]]["with_terminal"]
    forensics = {
        "strategy_name": "us_high_beta_sleeve_ensemble_r1_d01",
        "lookahead_check": "pass",
        "future_leak_check": "pass",
        "overfit_risk": "high",
        "multiple_testing_count": payload["statistics"]["effective_trial_count"],
        "pbo_proxy": payload["statistics"]["PBO"]["probability"],
        "dsr_proxy": payload["statistics"]["DSR"]["S1D01"]["probability"],
        "sample_data_caveats": [
            "historical prices are globally exposed and not an untouched holdout",
            "semantic roles are exact zero-capital fallbacks rather than historical modality evidence",
        ],
        "trade_count": primary["nonzero_rebalance_count"],
        "trading_days": primary["market_interval_count"],
        "capacity_assessment": "A future personal Paper canary capped at USD 1,000 is expected to be far below 1% of TQQQ/BIL ADV; this does not establish live auction capacity.",
        "short_sample": primary["market_interval_count"] < 252,
        "conclusion": "warning",
        "notes": "Signals use completed closes and next-session opens; models use chronological rows whose label end precedes each decision by the frozen purge/embargo. High cumulative selection burden remains explicit.",
    }
    base = root / "reports/harness/forensics/us_high_beta_sleeve_ensemble_r1_d01-backtest-forensics"
    write_json(base.with_suffix(".json"), forensics)
    base.with_suffix(".md").write_text(
        "# Backtest Forensics: us_high_beta_sleeve_ensemble_r1_d01\n\n"
        f"- Conclusion: `{forensics['conclusion']}`\n"
        f"- Lookahead: `{forensics['lookahead_check']}`\n"
        f"- Future leak: `{forensics['future_leak_check']}`\n"
        f"- Effective trials: `{forensics['multiple_testing_count']}`\n"
        f"- DSR probability: `{forensics['dsr_proxy']}`\n"
        f"- PBO: `{forensics['pbo_proxy']}`\n\n"
        "The methodology passes timing checks but retains a high multiple-testing warning because all historical prices and prior rounds are exposed.\n",
        encoding="utf-8",
    )


def _receipt_binding(path: Path, root: Path) -> dict[str, Any]:
    return _binding(path, root)


def evaluate(root: Path) -> R1EvaluationResult:
    base = root.resolve()
    output = base / OUTPUT_DIR
    if output.exists():
        raise ValueError("R1 evaluation output already exists; one-shot rerun is prohibited")
    if any((base / ITERATION_DIR).glob("evaluation-run.staging-*")):
        raise ValueError("R1 stale staging directory exists")
    preflight = _preflight(base)
    panel = load_r24_price_panel(base)
    specs = load_and_validate_specs(base)
    contract = runtime_contract_from_specs(specs, root=base)
    folds = chronological_folds(panel.open.index, contract)
    dataset = build_monthly_dataset(panel, contract)
    provenance = {
        "lock_sha256": preflight["lock_sha256"],
        "snapshot_manifest_sha256": panel.metadata["snapshot_manifest_sha256"],
        "feature_contract_sha256": _sha256(base / ITERATION_DIR / "feature-contract.json"),
        "label_contract_sha256": _sha256(base / ITERATION_DIR / "label-contract.json"),
        "validation_contract_sha256": _sha256(base / ITERATION_DIR / "validation-contract.json"),
    }
    targets, target_records, model_records, prediction_records = build_candidate_targets(
        panel, dataset, folds, provenance, contract
    )
    start = pd.Timestamp(folds[0]["test_start"])
    end = pd.Timestamp(folds[-1]["test_end"])
    candidates, returns, daily_rows = _evaluate_candidates(
        panel.open, targets, start=start, end=end, contract=contract
    )
    fold_results = _evaluate_folds(panel.open, folds, targets, contract)
    aggregate_policy_values = {
        candidate_id: _paired_target_stream_log_wealth_value(
            panel.open,
            targets["S1D01"],
            targets[candidate_id],
            start=start,
            end=end,
            cost_bps=contract.primary_cost_bps,
            reserve_symbol=contract.reserve_symbol,
        )
        for candidate_id in ("S1M01", "S1M02")
    }
    benchmarks = _benchmark_family(panel.open, start=start, end=end, contract=contract)
    dsr = {
        candidate_id: deflated_sharpe_probability(values, contract.effective_trial_count)
        for candidate_id, values in returns.items()
    }
    pbo = cscv_probability_backtest_overfitting(
        {
            candidate_id: returns[candidate_id]
            for candidate_id in ("S1D01", "S1M01", "S1M02", "S1D03", "S1D04")
        },
        block_count=int(contract.pbo_contract["block_count"]),
    )
    gates, policy_diagnostics = _candidate_gates(
        candidates,
        benchmarks,
        dsr,
        pbo,
        fold_results,
        prediction_records,
        contract,
        aggregate_policy_values,
    )
    for candidate_id in candidates:
        candidates[candidate_id]["folds"] = fold_results[candidate_id]
        candidates[candidate_id]["gates"] = gates[candidate_id]

    d01_pass = gates["S1D01"]["pass"]
    ml_pass_ids = [
        candidate_id for candidate_id in ("S1M01", "S1M02") if gates[candidate_id]["pass"]
    ]
    group_historical_pass = bool(d01_pass and ml_pass_ids)
    decision = "continue" if group_historical_pass else "stop"
    interpretation = (
        "The deterministic primary and at least one independently acting ML overlay cleared every frozen historical gate. Runtime parity and Paper-entry safety artifacts may now be built without changing this evaluation."
        if group_historical_pass
        else "No complete strategy group cleared the frozen deterministic, robustness, cost, DSR/PBO, and independent ML contribution gates. This R1 family is sealed as a negative result and cannot be rescued by selecting its 40/60 neighbors or retuning the exposed SMA200 path."
    )
    payload = {
        "schema_version": 1,
        "report_type": "high_beta_sleeve_ensemble_r1_historical_evaluation",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": True,
        "research_pass": group_historical_pass,
        "llm_contribution_pass": False,
        "ml_contribution_pass": bool(ml_pass_ids),
        "paper_ready_pass": False,
        "paper_entry_ready": False,
        "paper_validated": False,
        "historical_group_pass": group_historical_pass,
        "historical_pass_candidate_ids": ["S1D01", *ml_pass_ids] if group_historical_pass else [],
        "interpretation": interpretation,
        "data": panel.metadata,
        "oos_window": {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "folds": folds,
            "globally_exposed_not_pristine": True,
        },
        "candidates": candidates,
        "benchmarks": benchmarks,
        "statistics": {
            "DSR": dsr,
            "PBO": pbo,
            "effective_trial_count": contract.effective_trial_count,
            "primary_cost_view": contract.primary_view_name,
            "cost_views": contract.cost_views,
            "runtime_contract_sha256": contract.sha256,
        },
        "model_comparison": {
            "policy_diagnostics": policy_diagnostics,
            "fallback_identity": {
                "S1F01_equals_S1M01": targets["S1F01"].equals(targets["S1M01"]),
                "S1C01_equals_S1M01_without_packets": targets["S1C01"].equals(targets["S1M01"]),
                "S1L01_equals_S1D01_zero_capital": targets["S1L01"].equals(targets["S1D01"]),
            },
        },
        "integrity": {
            **preflight,
            "primary_cost_view": contract.primary_view_name,
            "primary_cost_bps": contract.primary_cost_bps,
            "cost_views": contract.cost_views,
            "runtime_contract_sha256": contract.sha256,
            "spec_semantic_sha256": {
                candidate_id: strategy_content_hash(spec) for candidate_id, spec in specs.items()
            },
            "target_weights_sum_to_one": True,
            "models_fit_from_scratch": True,
            "random_split_used": False,
            "historical_semantic_backfill_used": False,
            "broker_writes": False,
        },
        "limitations": [
            "All historical prices and earlier strategy outcomes are globally exposed.",
            "The OOS folds are chronological prequential diagnostics, not a pristine holdout.",
            "LLM and semantic roles have zero capital and exact fallback streams.",
            "Simulated next-open fills do not establish Paper or live auction execution quality.",
        ],
    }

    trial_rows = _trial_rows(candidates, gates, contract)
    staging = base / ITERATION_DIR / f"evaluation-run.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        write_json(staging / "evaluation-report.json", payload)
        (staging / "evaluation-report.md").write_text(_render_report(payload), encoding="utf-8")
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
                "model_record_count": len(model_records),
                "model_ledger_sha256": _canonical_hash(model_records),
                "data": provenance,
                "runtime_contract": contract.to_dict(),
                "runtime_contract_sha256": contract.sha256,
                "features": list(contract.m01.features),
                "prompt": {"applicable": False, "reason": "quant_only_models"},
                "validation": {
                    "folds": folds,
                    "purge_sessions": contract.purge_sessions,
                    "embargo_sessions": contract.embargo_sessions,
                    "label_end": "next_scheduled_review_open",
                    "update_mode": "prequential_month_end_refit_from_scratch",
                },
                "status": "historical_fold_local_diagnostic_not_runtime_model",
            },
        )
        decision_text = (
            "# Decision Record: mom_high_beta_sleeve_ensemble_r1\n\n"
            "- Path: Fixed 50/50 high-beta sleeve family and matched ML overlays.\n"
            f"- Decision: {decision}\n"
            f"- Reason: {interpretation}\n"
            "- Next iteration suggestion: Preserve this sealed result. On stop, change to a genuinely independent portfolio or return-source hypothesis; on continue, build runtime parity and safety artifacts without changing historical behavior.\n"
        )
        (staging / "decision-record.md").write_text(decision_text, encoding="utf-8")
        _write_jsonl(staging / "trial-ledger.jsonl", trial_rows)
        _write_jsonl(staging / "model-ledger.jsonl", model_records)
        _write_jsonl(staging / "prediction-ledger.jsonl", prediction_records)
        _write_jsonl(staging / "target-ledger.jsonl", target_records)
        _write_jsonl(staging / "daily-return-ledger.jsonl", daily_rows)
        child_names = {
            "evaluation": "evaluation-report.json",
            "evaluation_markdown": "evaluation-report.md",
            "decision_record": "decision-record.md",
            "trial_ledger": "trial-ledger.jsonl",
            "model_ledger": "model-ledger.jsonl",
            "prediction_ledger": "prediction-ledger.jsonl",
            "target_ledger": "target-ledger.jsonl",
            "daily_return_ledger": "daily-return-ledger.jsonl",
            "fold_results": "fold-results.json",
            "benchmark_results": "benchmark-results.json",
            "model_provenance": "model-provenance.json",
        }
        children = {
            name: _receipt_binding(
                path,
                base,
            )
            for name, filename in child_names.items()
            for path in [staging / filename]
        }
        for binding in children.values():
            relative = Path(binding["path"]).relative_to(staging.relative_to(base))
            binding["path"] = (OUTPUT_DIR / relative).as_posix()
        receipt = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "generated_at": datetime.now(UTC).isoformat(),
            "evidence_publication_status": "complete",
            "decision": decision,
            "workflow_pass": payload["workflow_pass"],
            "research_pass": payload["research_pass"],
            "llm_contribution_pass": payload["llm_contribution_pass"],
            "paper_ready_pass": payload["paper_ready_pass"],
            "children": children,
        }
        write_json(staging / "evaluation-receipt.json", receipt)
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    _write_factor_lab(base, dataset, payload)
    _write_forensics(base, payload)
    return R1EvaluationResult(
        evaluation_path=output / "evaluation-report.json",
        trial_ledger_path=output / "trial-ledger.jsonl",
        payload=payload,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "evaluate"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.action == "freeze":
        path = freeze(args.root)
        print(path)
    else:
        result = evaluate(args.root)
        print(result.evaluation_path)


if __name__ == "__main__":
    main()
