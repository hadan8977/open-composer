# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.adapters.data.cboe_volatility import (
    CboeVolatilityPacket,
    load_cboe_volatility_snapshot,
)
from open_composer.market_calendar import NEW_YORK, next_us_equity_session, us_equity_session_close
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.dynamic_theme_chain_r8 import (
    _daily_returns,
    _simulate_static,
    _simulation_metric_views,
)
from open_composer.research.etf_structural_r9 import simulate_target_portfolio
from open_composer.research.high_beta_sleeve_ensemble_r1 import (
    OUTPUT_DIR as PRIOR_OUTPUT_DIR,
)
from open_composer.research.high_beta_sleeve_ensemble_r1 import (
    build_deterministic_targets as build_prior_r1_targets,
)
from open_composer.research.high_beta_sleeve_ensemble_r1 import (
    build_monthly_dataset as build_prior_r1_dataset,
)
from open_composer.research.high_beta_sleeve_ensemble_r1 import (
    load_and_validate_specs as load_prior_r1_specs,
)
from open_composer.research.high_beta_sleeve_ensemble_r1 import (
    runtime_contract_from_specs as prior_r1_runtime_contract,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.multiasset_forward_multimodal_r6 import (
    deflated_sharpe_ratio_r6,
    probability_backtest_overfitting_r6,
)
from open_composer.research.pit_semantic_theme_r11 import R11PricePanel
from open_composer.research.pit_semantic_theme_r24 import load_r24_price_panel
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

BASE_ITER_ID = "mom_vix_term_structure_overlay_r1"
REPAIR_ITER_ID = "mom_vix_term_structure_overlay_r1_implfix1"
BASE_STRATEGY_STEM = "us_vix_term_structure_overlay_r1"
REPAIR_STRATEGY_STEM = "us_vix_term_structure_overlay_r1_implfix1"
ALLOWED_ITERATION_STEMS = {
    BASE_ITER_ID: BASE_STRATEGY_STEM,
    REPAIR_ITER_ID: REPAIR_STRATEGY_STEM,
}
ITER_ID = BASE_ITER_ID
STRATEGY_STEM = BASE_STRATEGY_STEM
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
OUTPUT_DIR = ITERATION_DIR / "evaluation-run"
EVALUATION_ATTEMPT_PATH = ITERATION_DIR / "evaluation-attempt.json"
RUNNER_PATH = Path("open_composer/research/vix_term_structure_overlay_r1.py")
PREPARE_PATH = Path("scripts/prepare_vix_term_structure_overlay_r1.py")
TEST_PATH = Path("tests/test_vix_term_structure_overlay_r1.py")
PRICE_SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
PRICE_QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
CBOE_SNAPSHOT_PATH = Path(
    "data/research/cboe_vix_term_structure_20260814_pairing_v1/snapshot-manifest.json"
)
CBOE_PACKET_PATH = CBOE_SNAPSHOT_PATH.parent / "cboe-volatility-packets.jsonl"
SOURCE_CARDS_PATH = Path("reports/harness/source_cards") / f"{STRATEGY_STEM}.jsonl"
FACTOR_LIBRARY_PATH = Path("reports/research") / f"{STRATEGY_STEM}-factor-library.json"
SOURCE_ITERATION_LOCK_PATH = Path(
    "reports/research/iterations/mom_vix_term_structure_overlay_r1/lock-set/"
    "historical-evaluation-lock.json"
)
SOURCE_ITERATION_LOCK_SHA256 = "97e8c8c61159a356e54abb64f7a10fb08ba442727ba4d9fc2d122e04fe0ed946"
PRIOR_LOCK_PATH = Path(
    "reports/research/iterations/mom_high_beta_sleeve_ensemble_r1/lock-set/historical-evaluation-lock.json"
)
PRIOR_REPORT_PATH = PRIOR_OUTPUT_DIR / "evaluation-report.json"
PRIOR_RECEIPT_PATH = PRIOR_OUTPUT_DIR / "evaluation-receipt.json"
PRIOR_TARGET_LEDGER_PATH = PRIOR_OUTPUT_DIR / "target-ledger.jsonl"
PRIOR_DAILY_RETURN_LEDGER_PATH = PRIOR_OUTPUT_DIR / "daily-return-ledger.jsonl"

CANDIDATE_ROWS = (
    ("V1R01", "r01"),
    ("V1Q01", "q01"),
    ("V1V01", "v01"),
    ("V1D02", "d02"),
    ("V1M01", "m01"),
    ("V1M02", "m02"),
    ("V1C01", "c01"),
    ("V1F01", "f01"),
    ("V1P01", "p01"),
)
CANDIDATE_IDS = tuple(candidate_id for candidate_id, _ in CANDIDATE_ROWS)
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/{STRATEGY_STEM}_{suffix}.yaml")
    for candidate_id, suffix in CANDIDATE_ROWS
}
PRICE_SYMBOLS = ("TQQQ", "QQQ", "BIL", "SPY", "XLK")
TRAINED_IDS = ("V1M01", "V1M02", "V1C01", "V1P01")
SELECTABLE_IDS = ("V1Q01", "V1V01", "V1D02", "V1M01", "V1M02", "V1C01")
PRICE_FEATURES = (
    "qqq_momentum_21",
    "qqq_momentum_63",
    "qqq_realized_volatility_21",
    "qqq_drawdown_63",
)
VIX_FEATURES = (
    "vix_to_vix3m_ratio",
    "normalized_term_slope",
    "vix_close",
    "vix3m_close",
    "vix_high",
    "vix_low",
    "vix3m_high",
    "vix3m_low",
)
ALL_FEATURES = (*PRICE_FEATURES, *VIX_FEATURES)
BASE_LOCK_STATUS = "vix_r1_implementation_contracts_and_data_locked_before_first_historical_return"
REPAIR_LOCK_STATUS = "vix_r1_implfix1_locked_after_parent_failure_audit_before_repair_evaluation"
LOCK_STATUS = BASE_LOCK_STATUS
LOCK_CONTRACT_ID = "vix_term_structure_overlay_r1_historical_evaluation_v1"

BASE_ITERATION_FILES = (
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
    "modality-role-matrix.json",
    "model-reuse-decision.json",
    "knowledge-assessment.json",
    "knowledge-scout.json",
    "knowledge-baseline.json",
    "knowledge-context.json",
    "knowledge-scout-queries.json",
    "external-brief.json",
    "external-brief.md",
    "hypotheses.md",
    "search-space.json",
    "search-space.md",
    "decision-record.md",
)
REPAIR_ITERATION_FILES = (
    *BASE_ITERATION_FILES,
    "parent-failure-audit.json",
    "implementation-repair-contract.json",
)
ITERATION_FILES = BASE_ITERATION_FILES


def _external_input_paths(*, implementation_repair: bool) -> dict[str, Path]:
    paths = {
        "historical_price_snapshot": PRICE_SNAPSHOT_PATH,
        "price_adjustment_quality": PRICE_QUALITY_PATH,
        "cboe_snapshot": CBOE_SNAPSHOT_PATH,
        "cboe_packets": CBOE_PACKET_PATH,
        "source_cards": SOURCE_CARDS_PATH,
        "factor_library": FACTOR_LIBRARY_PATH,
        "capability_registry": Path("capabilities/registry.yaml"),
        "sealed_r1_lock": PRIOR_LOCK_PATH,
        "sealed_r1_receipt": PRIOR_RECEIPT_PATH,
        "sealed_r1_report": PRIOR_REPORT_PATH,
        "sealed_r1_target_ledger": PRIOR_TARGET_LEDGER_PATH,
        "sealed_r1_daily_return_ledger": PRIOR_DAILY_RETURN_LEDGER_PATH,
    }
    if implementation_repair:
        paths["failed_parent_iteration_lock"] = SOURCE_ITERATION_LOCK_PATH
    return paths


EXTERNAL_INPUT_PATHS = _external_input_paths(implementation_repair=False)
IMPLEMENTATION_PATHS = (
    RUNNER_PATH,
    TEST_PATH,
    PREPARE_PATH,
    Path("open_composer/adapters/data/cboe_volatility.py"),
    Path("open_composer/research/high_beta_sleeve_ensemble_r1.py"),
    Path("open_composer/research/pit_semantic_theme_r24.py"),
    Path("open_composer/research/dynamic_theme_chain_r8.py"),
    Path("open_composer/research/etf_structural_r9.py"),
    Path("open_composer/research/multiasset_forward_multimodal_r6.py"),
    Path("open_composer/research/iteration_dossier.py"),
    Path("open_composer/models/strategy_spec.py"),
    Path("open_composer/strategy_versions.py"),
    Path("pyproject.toml"),
    Path("uv.lock"),
)


def configure_iteration(iter_id: str) -> None:
    if iter_id not in ALLOWED_ITERATION_STEMS:
        raise ValueError(f"unsupported VIX iteration identity: {iter_id}")
    global ITER_ID
    global STRATEGY_STEM
    global ITERATION_DIR
    global LOCK_PATH
    global OUTPUT_DIR
    global EVALUATION_ATTEMPT_PATH
    global SOURCE_CARDS_PATH
    global FACTOR_LIBRARY_PATH
    global SPEC_PATHS
    global ITERATION_FILES
    global EXTERNAL_INPUT_PATHS
    global LOCK_STATUS
    global LOCK_CONTRACT_ID
    ITER_ID = iter_id
    STRATEGY_STEM = ALLOWED_ITERATION_STEMS[iter_id]
    ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
    LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
    OUTPUT_DIR = ITERATION_DIR / "evaluation-run"
    EVALUATION_ATTEMPT_PATH = ITERATION_DIR / "evaluation-attempt.json"
    SOURCE_CARDS_PATH = Path("reports/harness/source_cards") / f"{STRATEGY_STEM}.jsonl"
    FACTOR_LIBRARY_PATH = Path("reports/research") / f"{STRATEGY_STEM}-factor-library.json"
    SPEC_PATHS = {
        candidate_id: Path(f"strategy_specs/drafts/{STRATEGY_STEM}_{suffix}.yaml")
        for candidate_id, suffix in CANDIDATE_ROWS
    }
    is_repair = iter_id == REPAIR_ITER_ID
    ITERATION_FILES = REPAIR_ITERATION_FILES if is_repair else BASE_ITERATION_FILES
    EXTERNAL_INPUT_PATHS = _external_input_paths(implementation_repair=is_repair)
    LOCK_STATUS = REPAIR_LOCK_STATUS if is_repair else BASE_LOCK_STATUS
    LOCK_CONTRACT_ID = (
        "vix_term_structure_overlay_r1_implfix1_historical_evaluation_v1"
        if is_repair
        else "vix_term_structure_overlay_r1_historical_evaluation_v1"
    )


@dataclass(frozen=True)
class VixEvaluationResult:
    evaluation_path: Path
    trial_ledger_path: Path
    model_ledger_path: Path
    prediction_ledger_path: Path
    target_ledger_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class VixRuntimeContract:
    manifest: dict[str, Any]
    contracts: dict[str, dict[str, Any]]
    candidate_specs: dict[str, dict[str, Any]]
    file_bindings: dict[str, dict[str, Any]]

    @property
    def validation(self) -> dict[str, Any]:
        return self.contracts["validation-contract.json"]

    @property
    def feature(self) -> dict[str, Any]:
        return self.contracts["feature-contract.json"]

    @property
    def label(self) -> dict[str, Any]:
        return self.contracts["label-contract.json"]

    @property
    def cost_views(self) -> dict[str, float]:
        rows = self.contracts["cost-contract.json"].get("views", [])
        output = {str(row["name"]): float(row["one_way_bps"]) for row in rows}
        if output != {"low_10bps": 10.0, "primary_20bps": 20.0, "severe_40bps": 40.0}:
            raise ValueError("VIX R1 cost views differ from the preregistered contract")
        return output

    @property
    def primary_cost_bps(self) -> float:
        return float(self.validation["family_gates"]["primary_cost_bps"])

    @property
    def effective_trial_count(self) -> int:
        return int(self.contracts["cumulative-trial-contract.json"]["effective_trial_count"])

    @property
    def sha256(self) -> str:
        return _canonical_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "contracts": self.contracts,
            "candidate_specs": self.candidate_specs,
            "file_bindings": self.file_bindings,
        }


@dataclass(frozen=True)
class FittedSurvivalModel:
    candidate_id: str
    model_id: str
    estimator: Pipeline
    calibrator: LogisticRegression
    record: dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "ascii"
        )
        + b"\n"
    )


def _report_type() -> str:
    if ITER_ID == REPAIR_ITER_ID:
        return "vix_term_structure_overlay_r1_implfix1_historical_evaluation"
    return "vix_term_structure_overlay_r1_historical_evaluation"


def _report_title() -> str:
    if ITER_ID == REPAIR_ITER_ID:
        return "VIX Term-Structure Overlay R1 Implementation Repair 1 Historical Evaluation"
    return "VIX Term-Structure Overlay R1 Historical Evaluation"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _binding(path: Path, root: Path) -> dict[str, Any]:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    cursor = candidate
    while cursor != base and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f"VIX R1 bound path cannot use symlinks: {candidate}")
        cursor = cursor.parent
    resolved = candidate.resolve(strict=True)
    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"VIX R1 bound path leaves repository root: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"VIX R1 bound path is not a regular file: {candidate}")
    return {
        "path": relative.as_posix(),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _verify_binding(root: Path, binding: Any) -> Path:
    if not isinstance(binding, dict):
        raise ValueError("VIX R1 lock binding is malformed")
    base = root.resolve()
    candidate = base / str(binding.get("path") or "")
    cursor = candidate
    while cursor != base and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f"VIX R1 lock binding cannot use symlinks: {candidate}")
        cursor = cursor.parent
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("VIX R1 lock binding leaves repository root") from exc
    if not path.is_file():
        raise ValueError(f"VIX R1 lock binding is not a regular file: {path}")
    if _sha256(path) != binding.get("sha256") or path.stat().st_size != binding.get("size_bytes"):
        raise ValueError(f"VIX R1 lock binding changed: {path}")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def load_and_validate_specs(root: Path) -> dict[str, StrategySpec]:
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    manifest = _load_json(root / ITERATION_DIR / "candidate-manifest.json")
    rows = manifest.get("candidates")
    if not isinstance(rows, list) or [row.get("candidate_id") for row in rows] != list(
        CANDIDATE_IDS
    ):
        raise ValueError("VIX R1 manifest candidate order or coverage changed")
    by_id = {str(row["candidate_id"]): row for row in rows}
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        row = by_id[candidate_id]
        path = SPEC_PATHS[candidate_id].as_posix()
        if (
            tuple(spec.universe)
            != (("QQQ", "TQQQ", "BIL", "SPY", "SMH") if candidate_id == "V1R01" else PRICE_SYMBOLS)
            or notes.get("candidate_id") != candidate_id
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
            or spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or row.get("spec_path") != path
            or manifest.get("spec_hashes", {}).get(path) != strategy_content_hash(spec)
        ):
            raise ValueError(f"VIX R1 spec safety or manifest binding mismatch: {candidate_id}")
    if specs["V1F01"].model is not None:
        raise ValueError("V1F01 must be a target-stream identity control without an estimator")
    for candidate_id in TRAINED_IDS:
        model = specs[candidate_id].model
        if model is None or model.kind != "logistic_regression_classifier":
            raise ValueError(f"VIX R1 trained model is missing or changed: {candidate_id}")
    expected_features = {
        "V1M01": PRICE_FEATURES,
        "V1M02": VIX_FEATURES,
        "V1C01": ALL_FEATURES,
        "V1P01": ALL_FEATURES,
    }
    for candidate_id, features in expected_features.items():
        if tuple(specs[candidate_id].model.features) != tuple(features):  # type: ignore[union-attr]
            raise ValueError(f"VIX R1 feature set changed: {candidate_id}")
    return specs


def runtime_contract_from_specs(specs: dict[str, StrategySpec], root: Path) -> VixRuntimeContract:
    if set(specs) != set(CANDIDATE_IDS):
        raise ValueError("VIX R1 runtime requires exactly nine specs")
    bindings: dict[str, dict[str, Any]] = {}
    contracts: dict[str, dict[str, Any]] = {}
    for filename in ITERATION_FILES:
        path = root / ITERATION_DIR / filename
        bindings[filename] = _binding(path, root)
        if path.suffix == ".json":
            contracts[filename] = _load_json(path)
    manifest = contracts["candidate-manifest.json"]
    snapshots = {
        candidate_id: {
            "path": SPEC_PATHS[candidate_id].as_posix(),
            "semantic_sha256": strategy_content_hash(spec),
            "spec": spec.model_dump(mode="json"),
        }
        for candidate_id, spec in specs.items()
    }
    contract = VixRuntimeContract(
        manifest=manifest,
        contracts=contracts,
        candidate_specs=snapshots,
        file_bindings=bindings,
    )
    _validate_runtime_contract(contract, root=root)
    return contract


#: Step 11 Wave C (open_composer/models/strategy_spec.py, PortfolioConfig)
#: added these 9 always-default-None fields for portfolio.mode=
#: model_ranking_portfolio. No VIX R1 spec uses that mode, but frozen
#: historical lock snapshots captured before that change simply lack the
#: keys, while a freshly re-dumped current spec now carries them (as
#: null) -- an exact-dict-equality projection like this one must drop them
#: when unset on a given side, the same way strategy_content_hash's own
#: _remove_unset_schema_extensions already does, or every repair-identity
#: check here spuriously fails independent of any real economic change.
#: Confirmed via a real full-suite pytest run plus a direct before/after
#: payload diff (git commit c394d82), not a hypothetical.
_MODEL_RANKING_PORTFOLIO_SCHEMA_EXTENSION_FIELDS = (
    "candidate_artifact_dir",
    "universe_rule",
    "universe_top_n",
    "feature_set_id",
    "label_horizon_days",
    "top_k",
    "rebalance",
    "hedge",
    "account_equity_for_sizing",
)


def _economic_spec_projection(payload: dict[str, Any]) -> dict[str, Any]:
    projection = {
        key: value for key, value in payload.items() if key not in {"name", "research_design"}
    }
    portfolio = projection.get("portfolio")
    if isinstance(portfolio, dict):
        portfolio = dict(portfolio)
        for field in _MODEL_RANKING_PORTFOLIO_SCHEMA_EXTENSION_FIELDS:
            # Only drop when unset on this side, so a real future
            # divergence (e.g. a repair iteration that actually adopts
            # model_ranking_portfolio mode) still surfaces instead of
            # being silently hidden.
            if portfolio.get(field) is None:
                portfolio.pop(field, None)
        projection["portfolio"] = portfolio
    return projection


def _validate_repair_identity(
    contract: VixRuntimeContract,
    *,
    root: Path,
) -> None:
    if ITER_ID != REPAIR_ITER_ID:
        return

    base = root.resolve()
    parent_binding = _binding(SOURCE_ITERATION_LOCK_PATH, base)
    if parent_binding["sha256"] != SOURCE_ITERATION_LOCK_SHA256:
        raise ValueError("VIX repair parent lock SHA drifted")
    parent_lock = _load_json(base / SOURCE_ITERATION_LOCK_PATH)
    parent_runtime = parent_lock.get("runtime_contract", {})
    parent_snapshots = parent_runtime.get("candidate_specs", {})
    parent_manifest_rows = parent_runtime.get("manifest", {}).get("candidates", [])
    if (
        parent_lock.get("iter_id") != BASE_ITER_ID
        or parent_lock.get("lock_contract")
        != "vix_term_structure_overlay_r1_historical_evaluation_v1"
        or set(parent_snapshots) != set(CANDIDATE_IDS)
        or [row.get("candidate_id") for row in parent_manifest_rows] != list(CANDIDATE_IDS)
    ):
        raise ValueError("VIX repair parent lock identity changed")

    repair = contract.contracts["implementation-repair-contract.json"]
    parent_audit = contract.contracts["parent-failure-audit.json"]
    expected_governance_bindings = {
        "vix_r1_parent_failure_audit_v1": contract.file_bindings["parent-failure-audit.json"],
        "vix_r1_pure_implementation_repair_v1": contract.file_bindings[
            "implementation-repair-contract.json"
        ],
    }
    if contract.manifest.get("contracts", {}).get("governance") != expected_governance_bindings:
        raise ValueError("VIX repair candidate manifest governance bindings changed")
    expected_forbidden_changes = [
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
    ]
    if (
        repair.get("contract_id") != "vix_r1_pure_implementation_repair_v1"
        or repair.get("repair_scope")
        != "candidate_target_inventory_order_and_one_shot_evaluation_custody"
        or parent_audit.get("source_lock") != parent_binding
        or repair.get("source_lock") != parent_binding
        or repair.get("parent_failure_audit") != contract.file_bindings["parent-failure-audit.json"]
        or repair.get("source_iteration_id") != BASE_ITER_ID
        or repair.get("new_economic_candidate_count") != 0
        or repair.get("manifest_candidate_count") != len(CANDIDATE_IDS)
        or repair.get("effective_trial_count") != 8147
        or repair.get("forbidden_changes") != expected_forbidden_changes
    ):
        raise ValueError("VIX repair parent or trial identity changed")

    failure = parent_audit.get("failure", {})
    exposure = parent_audit.get("exposure", {})
    if (
        parent_audit.get("source_iteration_id") != BASE_ITER_ID
        or parent_audit.get("parameter_changes_from_outcomes") is not False
        or parent_audit.get("paper_or_broker_activity") is not False
        or failure.get("selectable_candidate_returns_computed") is not False
        or failure.get("selectable_candidate_metrics_computed") is not False
        or failure.get("selection_performed") is not False
        or exposure.get("historical_targets_computed") is not True
        or exposure.get("historical_predictions_computed") != "true_or_unknown"
        or exposure.get("historical_predictions_inspected") != "false_or_unknown"
        or exposure.get("unpersisted_refit_attempts_lower_bound") != 0
        or exposure.get("unpersisted_refit_attempts_upper_bound") != 312
        or exposure.get("prediction_rows_upper_bound") != 6528
        or exposure.get("persisted_model_ids") != 0
        or exposure.get("persisted_prediction_rows") != 0
    ):
        raise ValueError("VIX repair failed-run exposure disclosure changed")

    if (
        contract.manifest.get("source_iteration_id") != BASE_ITER_ID
        or contract.manifest.get("implementation_repair_only") is not True
        or contract.manifest.get("incremental_economic_trial_count") != 0
    ):
        raise ValueError("VIX repair manifest accounting changed")
    manifest_rows = contract.manifest["candidates"]
    for row in manifest_rows:
        candidate_id = str(row["candidate_id"])
        if (
            row.get("source_trial_id") != f"{BASE_ITER_ID}:{candidate_id}"
            or row.get("effective_trial_increment") != 0
            or row.get("implementation_repair_only") is not True
        ):
            raise ValueError(f"VIX repair trial identity changed: {candidate_id}")

    equivalence_rows = repair.get("economic_spec_equivalence")
    if not isinstance(equivalence_rows, list) or [
        row.get("candidate_id") for row in equivalence_rows if isinstance(row, dict)
    ] != list(CANDIDATE_IDS):
        raise ValueError("VIX repair economic-equivalence inventory changed")
    for row in equivalence_rows:
        candidate_id = str(row["candidate_id"])
        source_snapshot = parent_snapshots[candidate_id]
        repair_snapshot = contract.candidate_specs[candidate_id]
        source_projection = _economic_spec_projection(source_snapshot["spec"])
        repair_projection = _economic_spec_projection(repair_snapshot["spec"])
        if source_projection != repair_projection:
            raise ValueError(f"VIX repair economic StrategySpec changed: {candidate_id}")
        expected_row = {
            "candidate_id": candidate_id,
            "source_spec_path": source_snapshot["path"],
            "source_spec_semantic_sha256": source_snapshot["semantic_sha256"],
            "repair_spec_path": repair_snapshot["path"],
            "repair_spec_semantic_sha256": repair_snapshot["semantic_sha256"],
            "economic_projection_sha256": _canonical_hash(source_projection),
            "economic_projection_equal": True,
            "allowed_spec_differences": ["name", "research_design"],
        }
        if row != expected_row:
            raise ValueError(f"VIX repair economic evidence changed: {candidate_id}")

    expected_policy_delta = {
        "reason": "post_2026_08_15_new_iteration_governance",
        "metric": "primary_20bps_continuous_terminal_free_OOS_annualized_sharpe_excess_BIL",
        "operator": "strictly_greater_than",
        "threshold": 1.0,
        "applies_to": list(SELECTABLE_IDS),
    }
    if repair.get("validation_policy_delta") != expected_policy_delta:
        raise ValueError("VIX repair validation-policy delta changed")


def _validate_runtime_contract(contract: VixRuntimeContract, *, root: Path) -> None:
    manifest_rows = contract.manifest.get("candidates", [])
    if [row.get("candidate_id") for row in manifest_rows] != list(CANDIDATE_IDS):
        raise ValueError("VIX R1 runtime manifest coverage changed")
    for candidate_id, snapshot in contract.candidate_specs.items():
        if (
            contract.manifest.get("spec_hashes", {}).get(snapshot["path"])
            != snapshot["semantic_sha256"]
        ):
            raise ValueError(f"VIX R1 runtime spec hash mismatch: {candidate_id}")
    validation = contract.validation
    feature = contract.feature
    label = contract.label
    state = feature.get("state_machine", {})
    thresholds = state.get("thresholds", {})
    if thresholds != {
        "risk_on_ratio_max": 0.95,
        "stress_ratio_min": 1.0,
        "crisis_ratio_min": 1.08,
        "crisis_vix_min": 40.0,
    }:
        raise ValueError("VIX R1 state thresholds differ from the lock contract")
    if state.get("confirmation", {}).get("required_consecutive_sessions") != 2:
        raise ValueError("VIX R1 risk-on confirmation contract changed")
    if (
        state.get("confirmation", {}).get("risk_on_hysteresis_hold")
        != "while ratio < stress_ratio_min and vix_close < crisis_vix_min"
    ):
        raise ValueError("VIX R1 risk-on hysteresis contract changed")
    trigger_eligibility = (
        "probability_lte_threshold_and_step_down_target_differs_from_same_session_fallback_target"
    )
    if feature.get("ml_overlay", {}).get("trigger_eligibility") != trigger_eligibility:
        raise ValueError("VIX R1 ML overlay trigger contract changed")
    timing = label.get("timing", {})
    if (
        timing.get("label_start") != "regular_open_t_plus_1"
        or timing.get("label_end") != "regular_open_t_plus_6"
        or timing.get("return_intervals") != 5
        or timing.get("decision_session_open_excluded") is not True
    ):
        raise ValueError("VIX R1 future label timing is not uniquely frozen")
    ml = validation.get("ml_training", {})
    if (
        ml.get("candidate_ids") != list(TRAINED_IDS)
        or ml.get("retrain_every_sessions") != 21
        or ml.get("selection_threshold") != 0.65
        or ml.get("placebo_contract", {}).get("fit_rows_only") is not True
        or ml.get("override_contract", {}).get("trigger_eligibility") != trigger_eligibility
        or validation.get("ml_override", {}).get("trigger_eligibility") != trigger_eligibility
    ):
        raise ValueError("VIX R1 ML training contract changed")
    folds = validation.get("chronological_folds", {})
    if (
        folds.get("count") != 4
        or folds.get("oos_sessions") != 408
        or folds.get("first_oos_index") != 756
    ):
        raise ValueError("VIX R1 fold or common-return contract changed")
    pbo = validation.get("pbo", {})
    pbo_matrix = pbo.get("common_return_matrix", {})
    if (
        pbo.get("selection_candidate_ids") != list(SELECTABLE_IDS)
        or pbo.get("block_count") != 8
        or pbo.get("in_sample_block_count") != 4
        or pbo.get("expected_partition_count") != 70
        or pbo.get("minimum_valid_partition_count") != 70
        or pbo_matrix.get("cost_view") != "primary_20bps"
        or pbo_matrix.get("terminal_liquidation_included") is not False
        or pbo_matrix.get("expected_observation_count") != 1631
        or pbo_matrix.get("expected_block_observation_counts")
        != [204, 204, 204, 204, 204, 204, 204, 203]
        or pbo_matrix.get("source_rows_sha256_required") is not True
    ):
        raise ValueError("VIX R1 PBO candidate or partition contract changed")
    dsr = validation.get("dsr", {})
    if (
        dsr.get("hac_scope") != "single_continuous_terminal_free_OOS_return_stream"
        or dsr.get("hac_lag_sessions") != 21
        or dsr.get("trial_count") != 8147
    ):
        raise ValueError("VIX R1 DSR stream identity contract changed")
    if contract.effective_trial_count != 8147:
        raise ValueError("VIX R1 cumulative trial count changed")
    family_gates = validation.get("family_gates", {})
    if ITER_ID == REPAIR_ITER_ID:
        expected_sharpe_identity = {
            "cost_view": "primary_20bps",
            "return_stream": "continuous_terminal_free_OOS_daily_open_to_open_net_returns",
            "benchmark": "BIL",
            "annualization_sessions": 252,
            "field": "annualized_sharpe_excess_BIL",
        }
        cumulative = contract.contracts["cumulative-trial-contract.json"]
        repair = contract.contracts["implementation-repair-contract.json"]
        parent_audit = contract.contracts["parent-failure-audit.json"]
        if (
            family_gates.get("Sharpe_floor") != 1.0
            or family_gates.get("Sharpe_operator") != "strictly_greater_than"
            or family_gates.get("Sharpe_metric_identity") != expected_sharpe_identity
            or cumulative.get("prior_effective_trial_count") != 8147
            or cumulative.get("round_manifest_candidate_count") != 9
            or cumulative.get("inherited_already_counted_candidate_count") != 9
            or cumulative.get("incremental_economic_trial_count") != 0
            or cumulative.get("effective_trial_count") != 8147
            or repair.get("contract_id") != "vix_r1_pure_implementation_repair_v1"
            or repair.get("new_economic_candidate_count") != 0
            or repair.get("effective_trial_count") != 8147
            or parent_audit.get("parameter_changes_from_outcomes") is not False
            or parent_audit.get("failure", {}).get("selectable_candidate_returns_computed")
            is not False
            or parent_audit.get("exposure", {}).get("unpersisted_refit_attempts_upper_bound") != 312
        ):
            raise ValueError("VIX R1 implementation-repair or Sharpe contract changed")
    cost = contract.contracts["cost-contract.json"]
    if (
        cost.get("terminal_liquidation_cost") is not False
        or cost.get("initial_entry_cost") is not True
    ):
        raise ValueError("VIX R1 cost boundary contract changed")
    _ = contract.cost_views
    _validate_repair_identity(contract, root=root)


def _subset_panel(panel: R11PricePanel) -> R11PricePanel:
    frames = {
        name: getattr(panel, name).loc[:, list(PRICE_SYMBOLS)].copy()
        for name in ("open", "low", "close", "volume")
    }
    first = frames["open"]
    if (
        list(first.columns) != list(PRICE_SYMBOLS)
        or len(first) != 2388
        or first.index[0] != pd.Timestamp("2017-02-01")
        or first.index[-1] != pd.Timestamp("2026-08-03")
    ):
        raise ValueError("VIX R1 price-panel identity changed")
    for name, frame in frames.items():
        if (
            not frame.index.equals(first.index)
            or not np.isfinite(frame.to_numpy(dtype=float)).all()
        ):
            raise ValueError(f"VIX R1 price panel is incomplete: {name}")
    return R11PricePanel(metadata=dict(panel.metadata), **frames)


def load_and_validate_packets(root: Path) -> pd.DataFrame:
    manifest_frame = load_cboe_volatility_snapshot(root / CBOE_SNAPSHOT_PATH)
    rows: list[dict[str, Any]] = []
    with (root / CBOE_PACKET_PATH).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"VIX R1 packet line is blank: {line_number}")
            packet = CboeVolatilityPacket.model_validate(json.loads(line))
            source_input = {
                "observation_date": packet.observation_date.isoformat(),
                "source_urls": packet.source_urls,
                "vix": {
                    "open": packet.vix_open,
                    "high": packet.vix_high,
                    "low": packet.vix_low,
                    "close": packet.vix_close,
                },
                "vix3m": {
                    "open": packet.vix3m_open,
                    "high": packet.vix3m_high,
                    "low": packet.vix3m_low,
                    "close": packet.vix3m_close,
                },
            }
            expected_hash = hashlib.sha256(
                json.dumps(source_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            expected_visible = pd.Timestamp(
                datetime.combine(
                    next_us_equity_session(packet.observation_date),
                    datetime.min.time().replace(hour=9, minute=30),
                    tzinfo=NEW_YORK,
                )
            ).tz_convert("UTC")
            if (
                packet.input_hash != expected_hash
                or not math.isclose(
                    packet.vix_to_vix3m_ratio,
                    packet.vix_close / packet.vix3m_close,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                or not math.isclose(
                    packet.normalized_term_slope,
                    packet.vix3m_close / packet.vix_close - 1.0,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                or pd.Timestamp(packet.visible_at) != expected_visible
            ):
                raise ValueError(
                    f"VIX R1 packet provenance or derived values changed: {line_number}"
                )
            rows.append(packet.model_dump(mode="json"))
    frame = pd.DataFrame(rows)
    if len(frame) != len(manifest_frame) or len(frame) != 4251:
        raise ValueError("VIX R1 packet row count changed")
    frame["observation_date"] = pd.to_datetime(frame["observation_date"], errors="raise")
    for column in ("published_at", "visible_at", "fetched_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    visible_sessions = (
        frame["visible_at"].dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
    )
    if visible_sessions.duplicated().any() or not visible_sessions.is_monotonic_increasing:
        raise ValueError("VIX R1 packets have duplicate or unordered visible sessions")
    frame.index = pd.DatetimeIndex(visible_sessions)
    return frame


def _decision_close(session: pd.Timestamp) -> pd.Timestamp:
    close = us_equity_session_close(session.date())
    if close is None:
        raise ValueError(f"VIX R1 decision date is not an equity session: {session.date()}")
    return pd.Timestamp(datetime.combine(session.date(), close, tzinfo=NEW_YORK)).tz_convert("UTC")


def path_survival_label(open_path: pd.Series | list[float] | np.ndarray) -> int:
    values = np.asarray(open_path, dtype=float)
    if len(values) != 6 or not np.isfinite(values).all() or (values <= 0.0).any():
        raise ValueError("VIX R1 path-survival label requires six finite positive opens")
    running_drawdown = values / np.maximum.accumulate(values) - 1.0
    terminal = values[-1] / values[0] - 1.0
    return int(float(running_drawdown.min()) >= -0.10 and float(terminal) > -0.06)


def build_feature_label_dataset(panel: R11PricePanel, packets: pd.DataFrame) -> pd.DataFrame:
    close = panel.close
    opens = panel.open
    qqq = close["QQQ"].astype(float)
    qqq_return = qqq.pct_change(fill_method=None)
    features = pd.DataFrame(index=close.index)
    features["qqq_momentum_21"] = qqq / qqq.shift(21) - 1.0
    features["qqq_momentum_63"] = qqq / qqq.shift(63) - 1.0
    features["qqq_realized_volatility_21"] = qqq_return.rolling(21, min_periods=21).std(ddof=1)
    features["qqq_drawdown_63"] = qqq / qqq.rolling(63, min_periods=63).max() - 1.0

    rows: list[dict[str, Any]] = []
    for execution_position in range(1, len(close.index)):
        decision_position = execution_position - 1
        decision_session = close.index[decision_position]
        execution_session = close.index[execution_position]
        decision_at = _decision_close(decision_session)
        packet_row: pd.Series | None = None
        packet_reason = "missing_expected_packet"
        if decision_session in packets.index:
            selected = packets.loc[decision_session]
            if isinstance(selected, pd.DataFrame):
                raise ValueError("VIX R1 packet join produced duplicate rows")
            if pd.Timestamp(selected["visible_at"]) <= decision_at:
                packet_row = selected
                packet_reason = "visible_at_lte_decision_at"
            else:
                packet_reason = "visible_after_decision_exact_fallback"
        row: dict[str, Any] = {
            "decision_position": decision_position,
            "decision_session": decision_session.date().isoformat(),
            "decision_at": decision_at.isoformat(),
            "execution_position": execution_position,
            "execution_session": execution_session.date().isoformat(),
            "packet_available": packet_row is not None,
            "packet_reason": packet_reason,
            "packet_observation_date": None,
            "packet_visible_at": None,
            "packet_input_hash": None,
            **{name: float(features.at[decision_session, name]) for name in PRICE_FEATURES},
        }
        for name in VIX_FEATURES:
            row[name] = float(packet_row[name]) if packet_row is not None else float("nan")
        if packet_row is not None:
            row.update(
                {
                    "packet_observation_date": pd.Timestamp(packet_row["observation_date"])
                    .date()
                    .isoformat(),
                    "packet_visible_at": pd.Timestamp(packet_row["visible_at"]).isoformat(),
                    "packet_input_hash": str(packet_row["input_hash"]),
                }
            )
        label_end_position = execution_position + 5
        row["label_end_position"] = label_end_position if label_end_position < len(opens) else None
        row["label_end_session"] = (
            opens.index[label_end_position].date().isoformat()
            if label_end_position < len(opens)
            else None
        )
        if label_end_position < len(opens):
            path = opens["TQQQ"].iloc[execution_position : label_end_position + 1].astype(float)
            row["path_survival"] = float(path_survival_label(path))
        else:
            row["path_survival"] = float("nan")
        row["feature_complete"] = bool(
            all(math.isfinite(float(row[name])) for name in ALL_FEATURES)
        )
        rows.append(row)
    dataset = pd.DataFrame(rows, index=pd.DatetimeIndex(close.index[1:]))
    if dataset.index.has_duplicates or not dataset.index.is_monotonic_increasing:
        raise ValueError("VIX R1 feature-label dataset index is invalid")
    return dataset


def chronological_folds(
    index: pd.DatetimeIndex, contract: VixRuntimeContract
) -> list[dict[str, Any]]:
    cfg = contract.validation["chronological_folds"]
    first = int(cfg["first_oos_index"])
    count = int(cfg["count"])
    size = int(cfg["oos_sessions"])
    # A panel index includes absolute price position zero; the daily dataset
    # starts at execution position one. Accept either representation while
    # preserving the contract's absolute execution positions.
    position_offset = 0 if len(index) == first + count * size else 1
    if (
        len(index) + position_offset != first + count * size
        or index[first - position_offset].date().isoformat()
        != contract.validation["common_start"]["first_oos_session"]
    ):
        raise ValueError("VIX R1 OOS fold capacity changed")
    folds = []
    for number in range(count):
        start = first + number * size
        end = start + size - 1
        folds.append(
            {
                "fold_id": f"F{number + 1}",
                "execution_position_start": start,
                "execution_position_end": end,
                "test_start": index[start - position_offset].date().isoformat(),
                "test_end": index[end - position_offset].date().isoformat(),
                "test_session_count": size,
                "purge_sessions": int(cfg["purge_sessions"]),
                "embargo_sessions": int(cfg["embargo_sessions"]),
            }
        )
    return folds


def _empty_target(columns: pd.Index) -> dict[str, float]:
    return {str(symbol): 0.0 for symbol in columns}


def _one_hot(columns: pd.Index, symbol: str) -> dict[str, float]:
    target = _empty_target(columns)
    if symbol not in target:
        raise ValueError(f"VIX R1 target symbol is missing: {symbol}")
    target[symbol] = 1.0
    return target


def _target_symbol(target: pd.Series | dict[str, float]) -> str:
    items = [
        (str(symbol), float(weight)) for symbol, weight in target.items() if float(weight) > 1e-12
    ]
    if len(items) != 1 or not math.isclose(items[0][1], 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("VIX R1 daily ladder target must contain exactly one full-capital symbol")
    return items[0][0]


def _targets_equal(left: pd.Series | dict[str, float], right: pd.Series | dict[str, float]) -> bool:
    return _canonical_hash(
        {key: float(value) for key, value in left.items() if float(value) > 1e-12}
    ) == _canonical_hash(
        {key: float(value) for key, value in right.items() if float(value) > 1e-12}
    )


def build_vix_route_states(
    dataset: pd.DataFrame,
    contract: VixRuntimeContract,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    state_contract = contract.feature["state_machine"]
    thresholds = state_contract["thresholds"]
    risk_on_max = float(thresholds["risk_on_ratio_max"])
    stress_min = float(thresholds["stress_ratio_min"])
    crisis_ratio = float(thresholds["crisis_ratio_min"])
    crisis_vix = float(thresholds["crisis_vix_min"])
    required = int(state_contract["confirmation"]["required_consecutive_sessions"])
    route_state = str(state_contract["initial_route_state"])
    confirmations = 0
    states: list[str | None] = []
    records: list[dict[str, Any]] = []
    for execution_session, row in dataset.iterrows():
        raw_state: str | None = None
        missing = not bool(row["packet_available"])
        ratio = float(row["vix_to_vix3m_ratio"])
        vix = float(row["vix_close"])
        if missing or not math.isfinite(ratio) or not math.isfinite(vix):
            confirmations = 0
            route_state = str(state_contract["initial_route_state"])
            selected_state: str | None = None
        else:
            if ratio >= crisis_ratio or vix >= crisis_vix:
                raw_state = "crisis"
                confirmations = 0
                route_state = "crisis"
            elif ratio <= risk_on_max:
                raw_state = "risk_on_candidate"
                if route_state == "risk_on":
                    confirmations = required
                else:
                    confirmations += 1
                    route_state = "risk_on" if confirmations >= required else "transition"
            elif ratio < stress_min:
                raw_state = "transition"
                confirmations = 0
                if route_state != "risk_on":
                    route_state = "transition"
            else:
                raw_state = "stress"
                confirmations = 0
                route_state = "transition"
            selected_state = route_state
        states.append(selected_state)
        records.append(
            {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "decision_session": str(row["decision_session"]),
                "execution_session": execution_session.date().isoformat(),
                "raw_state": raw_state,
                "route_state": selected_state,
                "risk_on_confirmation_count": confirmations,
                "packet_available": not missing,
                "packet_input_hash": row.get("packet_input_hash"),
            }
        )
    return pd.Series(states, index=dataset.index, dtype="object"), records


def build_deterministic_targets(
    panel: R11PricePanel,
    dataset: pd.DataFrame,
    contract: VixRuntimeContract,
    *,
    oos_index: pd.DatetimeIndex,
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    states, state_records = build_vix_route_states(dataset, contract)
    q01_rows: list[dict[str, float]] = []
    v01_rows: list[dict[str, float]] = []
    d02_rows: list[dict[str, float]] = []
    for session, row in dataset.iterrows():
        price_risk_on = (
            math.isfinite(float(row["qqq_momentum_63"])) and float(row["qqq_momentum_63"]) > 0.0
        )
        q01 = _one_hot(panel.open.columns, "TQQQ" if price_risk_on else "BIL")
        vix_state = states.at[session]
        if vix_state is None:
            v01 = dict(q01)
            d02 = dict(q01)
        else:
            v01_symbol = {"risk_on": "TQQQ", "transition": "QQQ", "crisis": "BIL"}[str(vix_state)]
            v01 = _one_hot(panel.open.columns, v01_symbol)
            vix_risk_on = vix_state == "risk_on"
            d02_symbol = (
                "TQQQ"
                if price_risk_on and vix_risk_on
                else "QQQ"
                if price_risk_on != vix_risk_on
                else "BIL"
            )
            d02 = _one_hot(panel.open.columns, d02_symbol)
        q01_rows.append(q01)
        v01_rows.append(v01)
        d02_rows.append(d02)
    all_targets = {
        "V1Q01": pd.DataFrame(q01_rows, index=dataset.index, columns=panel.open.columns),
        "V1V01": pd.DataFrame(v01_rows, index=dataset.index, columns=panel.open.columns),
        "V1D02": pd.DataFrame(d02_rows, index=dataset.index, columns=panel.open.columns),
    }
    output = {
        candidate_id: frame.loc[oos_index].astype(float)
        for candidate_id, frame in all_targets.items()
    }
    _validate_target_frames(output, panel.open.columns, oos_index)
    return output, state_records


def _validate_target_frames(
    targets: dict[str, pd.DataFrame],
    columns: pd.Index,
    expected_index: pd.DatetimeIndex,
) -> None:
    for candidate_id, frame in targets.items():
        if (
            list(frame.columns) != list(columns)
            or not frame.index.equals(expected_index)
            or frame.index.has_duplicates
            or not np.isfinite(frame.to_numpy(dtype=float)).all()
            or (frame.to_numpy(dtype=float) < -1e-12).any()
            or not np.allclose(frame.sum(axis=1).to_numpy(dtype=float), 1.0, atol=1e-12, rtol=0.0)
        ):
            raise ValueError(f"VIX R1 target frame is invalid: {candidate_id}")


def _shared_training_rows(
    dataset: pd.DataFrame,
    *,
    current_execution_position: int,
    contract: VixRuntimeContract,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    ml = contract.validation["ml_training"]
    embargo = int(contract.label["timing"]["embargo_sessions"])
    mature = dataset[
        dataset["feature_complete"]
        & dataset["path_survival"].notna()
        & dataset["label_end_position"].notna()
        & (dataset["label_end_position"] <= current_execution_position - embargo)
        & (dataset["execution_position"] < current_execution_position)
    ].copy()
    cap = int(ml["window_cap_sessions"])
    if len(mature) > cap:
        mature = mature.iloc[-cap:].copy()
    calibration_rows = max(
        int(ml["minimum_calibration_rows"]),
        int(math.ceil(float(ml["calibration_fraction"]) * len(mature))),
    )
    if calibration_rows >= len(mature):
        fit = mature.iloc[0:0].copy()
        calibration = mature.copy()
    else:
        fit = mature.iloc[:-calibration_rows].copy()
        calibration = mature.iloc[-calibration_rows:].copy()
    identity_rows = [
        {
            "decision_session": str(row["decision_session"]),
            "execution_session": session.date().isoformat(),
            "label_end_position": int(row["label_end_position"]),
            "label": int(row["path_survival"]),
        }
        for session, row in mature.iterrows()
    ]
    return fit, calibration, _canonical_hash(identity_rows)


def _class_count(values: pd.Series, label: int) -> int:
    return int((values.astype(int) == label).sum())


def _placebo_seed(base_seed: int, fold_id: str, refit_ordinal: int, split_id: str) -> int:
    digest = hashlib.sha256(
        f"{base_seed}|{fold_id}|{refit_ordinal}|{split_id}".encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "little")


def _joint_permute_vix_fit_rows(
    fit: pd.DataFrame,
    *,
    base_seed: int,
    fold_id: str,
    refit_ordinal: int,
    split_id: str,
) -> tuple[pd.DataFrame, np.ndarray]:
    if not set(VIX_FEATURES).issubset(fit.columns):
        raise ValueError("VIX R1 placebo fit frame is missing VIX columns")
    output = fit.copy(deep=True)
    permutation = np.random.default_rng(
        _placebo_seed(base_seed, fold_id, refit_ordinal, split_id)
    ).permutation(len(output))
    output.loc[:, list(VIX_FEATURES)] = fit.loc[:, list(VIX_FEATURES)].to_numpy()[permutation]
    untouched = [column for column in fit.columns if column not in VIX_FEATURES]
    if not output.loc[:, untouched].equals(fit.loc[:, untouched]):
        raise AssertionError("VIX R1 placebo changed price, label, or identity columns")
    return output, permutation


def _model_payload(estimator: Pipeline, calibrator: LogisticRegression) -> dict[str, Any]:
    scaler = estimator.named_steps["scaler"]
    model = estimator.named_steps["model"]
    return {
        "scaler_mean": np.asarray(scaler.mean_, dtype=float).tolist(),
        "scaler_scale": np.asarray(scaler.scale_, dtype=float).tolist(),
        "model_coef": np.asarray(model.coef_, dtype=float).tolist(),
        "model_intercept": np.asarray(model.intercept_, dtype=float).tolist(),
        "calibrator_coef": np.asarray(calibrator.coef_, dtype=float).tolist(),
        "calibrator_intercept": np.asarray(calibrator.intercept_, dtype=float).tolist(),
    }


def _training_values_hash(frame: pd.DataFrame, features: tuple[str, ...]) -> str:
    rows = [
        {
            "execution_session": session.date().isoformat(),
            "decision_session": str(row["decision_session"]),
            "label_end_position": int(row["label_end_position"]),
            "path_survival": int(row["path_survival"]),
            "packet_input_hash": row.get("packet_input_hash"),
            "feature_values": {name: float(row[name]) for name in features},
        }
        for session, row in frame.iterrows()
    ]
    return _canonical_hash(rows)


def _fit_survival_model(
    candidate_id: str,
    fit: pd.DataFrame,
    calibration: pd.DataFrame,
    *,
    fold_id: str,
    refit_ordinal: int,
    common_index_sha256: str,
    contract: VixRuntimeContract,
) -> tuple[FittedSurvivalModel | None, dict[str, Any]]:
    ml = contract.validation["ml_training"]
    feature_sets = {
        "V1M01": PRICE_FEATURES,
        "V1M02": VIX_FEATURES,
        "V1C01": ALL_FEATURES,
        "V1P01": ALL_FEATURES,
    }
    features = tuple(feature_sets[candidate_id])
    fit_y = fit["path_survival"].astype(int)
    calibration_y = calibration["path_survival"].astype(int)
    frozen_provenance = {
        "spec_semantic_sha256": contract.candidate_specs[candidate_id]["semantic_sha256"],
        "data_contract_sha256": contract.file_bindings["data-contract.json"]["sha256"],
        "feature_contract_sha256": contract.file_bindings["feature-contract.json"]["sha256"],
        "label_contract_sha256": contract.file_bindings["label-contract.json"]["sha256"],
        "validation_contract_sha256": contract.file_bindings["validation-contract.json"]["sha256"],
        "model_reuse_decision_sha256": contract.file_bindings["model-reuse-decision.json"][
            "sha256"
        ],
        "runtime_contract_sha256": contract.sha256,
        "prompt": {
            "applicable": False,
            "prompt_hash": None,
            "reason": "quant_only_model_no_prompt",
        },
        "status_provenance": "historical_fold_local_diagnostic_not_runtime_model",
    }
    checks = {
        "fit_rows": len(fit) >= int(ml["minimum_fit_rows"]),
        "calibration_rows": len(calibration) >= int(ml["minimum_calibration_rows"]),
        "fit_positive": _class_count(fit_y, 1) >= int(ml["minimum_fit_positive_rows"]),
        "fit_negative": _class_count(fit_y, 0) >= int(ml["minimum_fit_negative_rows"]),
        "calibration_positive": _class_count(calibration_y, 1)
        >= int(ml["minimum_calibration_positive_rows"]),
        "calibration_negative": _class_count(calibration_y, 0)
        >= int(ml["minimum_calibration_negative_rows"]),
    }
    base_record: dict[str, Any] = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "candidate_id": candidate_id,
        "fold_id": fold_id,
        "refit_ordinal": refit_ordinal,
        "features": list(features),
        "fit_row_count": len(fit),
        "calibration_row_count": len(calibration),
        "fit_index_sha256": _canonical_hash([session.date().isoformat() for session in fit.index]),
        "calibration_index_sha256": _canonical_hash(
            [session.date().isoformat() for session in calibration.index]
        ),
        "common_training_index_sha256": common_index_sha256,
        "fit_feature_values_sha256": _training_values_hash(fit, features),
        "calibration_feature_values_sha256": _training_values_hash(calibration, features),
        "class_checks": checks,
        "fit_from_scratch": True,
        "frozen_provenance": frozen_provenance,
    }
    if not all(checks.values()):
        return None, {
            **base_record,
            "status": "insufficient_class_or_row_minima_exact_fallback",
            "model_id": None,
        }
    fit_X = fit.loc[:, list(features)].astype(float).copy()
    permutation_sha256: str | None = None
    derived_seed: int | None = None
    if candidate_id == "V1P01":
        placebo = ml["placebo_contract"]
        fit_with_placebo, permutation = _joint_permute_vix_fit_rows(
            fit,
            base_seed=int(placebo["seed"]),
            fold_id=fold_id,
            refit_ordinal=refit_ordinal,
            split_id="fit_rows",
        )
        derived_seed = _placebo_seed(int(placebo["seed"]), fold_id, refit_ordinal, "fit_rows")
        fit_X = fit_with_placebo.loc[:, list(features)].astype(float)
        permutation_sha256 = hashlib.sha256(
            np.asarray(permutation, dtype="<i8").tobytes()
        ).hexdigest()
    estimator = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    penalty="l2",
                    solver="lbfgs",
                    max_iter=1000,
                    random_state=int(ml["common_seed"]),
                ),
            ),
        ]
    )
    estimator.fit(fit_X, fit_y)
    calibration_X = calibration.loc[:, list(features)].astype(float)
    raw_scores = np.asarray(estimator.decision_function(calibration_X), dtype=float).reshape(-1, 1)
    raw_probabilities = np.asarray(estimator.predict_proba(calibration_X)[:, 1], dtype=float)
    calibrator = LogisticRegression(
        C=1.0,
        penalty="l2",
        solver="lbfgs",
        max_iter=1000,
        random_state=int(ml["common_seed"]),
    )
    calibrator.fit(raw_scores, calibration_y)
    calibrated = np.asarray(calibrator.predict_proba(raw_scores)[:, 1], dtype=float)
    parameters = _model_payload(estimator, calibrator)
    fitted_status = "fitted_and_chronologically_calibrated"
    fitted_matrix_sha256 = _canonical_hash(
        {
            "feature_order": list(features),
            "fit_values": fit_X.to_numpy(dtype=float).tolist(),
            "fit_labels": fit_y.to_list(),
            "calibration_values": calibration_X.to_numpy(dtype=float).tolist(),
            "calibration_labels": calibration_y.to_list(),
        }
    )
    model_id = _canonical_hash(
        {
            "candidate_id": candidate_id,
            "fold_id": fold_id,
            "refit_ordinal": refit_ordinal,
            "common_index_sha256": common_index_sha256,
            "parameters": parameters,
            "placebo_permutation_sha256": permutation_sha256,
            "fitted_matrix_sha256": fitted_matrix_sha256,
            "frozen_provenance": frozen_provenance,
            "status": fitted_status,
        }
    )
    record = {
        **base_record,
        "status": fitted_status,
        "model_id": model_id,
        "fitted_matrix_sha256": fitted_matrix_sha256,
        "parameters": parameters,
        "parameters_sha256": _canonical_hash(parameters),
        "raw_brier": float(brier_score_loss(calibration_y, raw_probabilities)),
        "calibrated_brier": float(brier_score_loss(calibration_y, calibrated)),
        "placebo_seed": derived_seed,
        "placebo_permutation_sha256": permutation_sha256,
        "calibration_rows_permuted": False,
    }
    return (
        FittedSurvivalModel(
            candidate_id=candidate_id,
            model_id=model_id,
            estimator=estimator,
            calibrator=calibrator,
            record=record,
        ),
        record,
    )


def _prediction_probability(model: FittedSurvivalModel, row: pd.Series) -> tuple[float, float]:
    features = list(model.record["features"])
    values = pd.DataFrame([[float(row[name]) for name in features]], columns=features)
    raw_score = float(model.estimator.decision_function(values)[0])
    probability = float(model.calibrator.predict_proba(np.asarray([[raw_score]]))[:, 1][0])
    if not (math.isfinite(raw_score) and math.isfinite(probability) and 0.0 <= probability <= 1.0):
        raise ValueError("VIX R1 model produced an invalid probability")
    return raw_score, probability


def build_ml_targets(
    panel: R11PricePanel,
    dataset: pd.DataFrame,
    deterministic: dict[str, pd.DataFrame],
    folds: list[dict[str, Any]],
    contract: VixRuntimeContract,
) -> tuple[
    dict[str, pd.DataFrame],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    oos_index = deterministic["V1Q01"].index
    fold_by_position: dict[int, str] = {}
    for fold in folds:
        for position in range(
            int(fold["execution_position_start"]), int(fold["execution_position_end"]) + 1
        ):
            fold_by_position[position] = str(fold["fold_id"])
    retrain_every = int(contract.validation["ml_training"]["retrain_every_sessions"])
    threshold = float(contract.validation["ml_training"]["selection_threshold"])
    duration = int(contract.validation["ml_override"]["duration_sessions"])
    fitted: dict[str, FittedSurvivalModel | None] = {
        candidate_id: None for candidate_id in TRAINED_IDS
    }
    overlay_remaining = {candidate_id: 0 for candidate_id in TRAINED_IDS}
    target_rows = {candidate_id: [] for candidate_id in TRAINED_IDS}
    model_records: list[dict[str, Any]] = []
    prediction_records: list[dict[str, Any]] = []
    common_index_records: list[dict[str, Any]] = []
    m01_targets_by_session: dict[pd.Timestamp, dict[str, float]] = {}

    for oos_ordinal, execution_session in enumerate(oos_index):
        row = dataset.loc[execution_session]
        execution_position = int(row["execution_position"])
        fold_id = fold_by_position[execution_position]
        if oos_ordinal % retrain_every == 0:
            refit_ordinal = oos_ordinal // retrain_every
            fit, calibration, common_hash = _shared_training_rows(
                dataset,
                current_execution_position=execution_position,
                contract=contract,
            )
            common_record = {
                "schema_version": 1,
                "iter_id": ITER_ID,
                "fold_id": fold_id,
                "refit_ordinal": refit_ordinal,
                "execution_session": execution_session.date().isoformat(),
                "fit_index_sha256": _canonical_hash(
                    [session.date().isoformat() for session in fit.index]
                ),
                "calibration_index_sha256": _canonical_hash(
                    [session.date().isoformat() for session in calibration.index]
                ),
                "common_training_index_sha256": common_hash,
                "fit_row_count": len(fit),
                "calibration_row_count": len(calibration),
            }
            common_index_records.append(common_record)
            for candidate_id in TRAINED_IDS:
                fitted_model, record = _fit_survival_model(
                    candidate_id,
                    fit,
                    calibration,
                    fold_id=fold_id,
                    refit_ordinal=refit_ordinal,
                    common_index_sha256=common_hash,
                    contract=contract,
                )
                fitted[candidate_id] = fitted_model
                model_records.append(
                    {**record, "refit_execution_session": execution_session.date().isoformat()}
                )

        q01_target = deterministic["V1Q01"].loc[execution_session].to_dict()
        for candidate_id in TRAINED_IDS:
            missing_fallback_id = "V1M01" if candidate_id == "V1C01" else "V1Q01"
            missing_fallback_target = (
                m01_targets_by_session[execution_session]
                if missing_fallback_id == "V1M01"
                else dict(q01_target)
            )
            requires_vix = candidate_id in {"V1M02", "V1C01", "V1P01"}
            missing_modality = requires_vix and not bool(row["packet_available"])
            model = fitted[candidate_id]
            raw_score: float | None = None
            probability: float | None = None
            reason: str | None = None
            trigger = False
            remaining_before = overlay_remaining[candidate_id]
            if missing_modality:
                overlay_remaining[candidate_id] = 0
                selected = dict(missing_fallback_target)
                reason = "missing_vix_exact_candidate_fallback"
            elif model is None:
                overlay_remaining[candidate_id] = 0
                selected = dict(q01_target)
                reason = "insufficient_model_exact_candidate_fallback"
            else:
                raw_score, probability = _prediction_probability(model, row)
                base_symbol = _target_symbol(q01_target)
                stepped_symbol = {"TQQQ": "QQQ", "QQQ": "BIL", "BIL": "BIL"}[base_symbol]
                trigger = probability <= threshold and stepped_symbol != base_symbol
                if trigger:
                    overlay_remaining[candidate_id] = duration
                if overlay_remaining[candidate_id] > 0:
                    selected = _one_hot(panel.open.columns, stepped_symbol)
                    overlay_remaining[candidate_id] -= 1
                else:
                    selected = dict(q01_target)
            comparison_fallback = missing_fallback_target if missing_modality else q01_target
            effective_override = not _targets_equal(selected, comparison_fallback)
            target_rows[candidate_id].append(selected)
            if candidate_id == "V1M01":
                m01_targets_by_session[execution_session] = dict(selected)
            prediction_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "candidate_id": candidate_id,
                    "fold_id": fold_id,
                    "decision_session": str(row["decision_session"]),
                    "execution_session": execution_session.date().isoformat(),
                    "model_id": model.model_id if model is not None else None,
                    "raw_score": raw_score,
                    "calibrated_probability": probability,
                    "selection_threshold": threshold,
                    "trigger": trigger,
                    "overlay_remaining_before": remaining_before,
                    "overlay_remaining_after": overlay_remaining[candidate_id],
                    "fallback_candidate_id": missing_fallback_id if missing_modality else "V1Q01",
                    "fallback_reason": reason,
                    "fallback_target_sha256": _canonical_hash(
                        {key: value for key, value in comparison_fallback.items() if value > 1e-12}
                    ),
                    "selected_target_sha256": _canonical_hash(
                        {key: value for key, value in selected.items() if value > 1e-12}
                    ),
                    "effective_override": effective_override,
                    "packet_input_hash": row.get("packet_input_hash"),
                }
            )
    frames = {
        candidate_id: pd.DataFrame(rows, index=oos_index, columns=panel.open.columns).astype(float)
        for candidate_id, rows in target_rows.items()
    }
    frames["V1F01"] = frames["V1M01"].copy(deep=True)
    if canonical_target_bytes(frames["V1F01"]) != canonical_target_bytes(frames["V1M01"]):
        raise ValueError("V1F01 target identity with V1M01 failed")
    _validate_target_frames(frames, panel.open.columns, oos_index)
    return frames, model_records, prediction_records, common_index_records


def canonical_target_bytes(frame: pd.DataFrame) -> bytes:
    rows = [
        {
            "execution_session": session.date().isoformat(),
            "weights": {
                str(symbol): float(weight)
                for symbol, weight in frame.loc[session].items()
                if float(weight) > 1e-12
            },
        }
        for session in frame.index
    ]
    return json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, default=str) + "\n").encode("utf-8") for row in rows
    )


def _terminal_free_prior_daily_rows(
    report: dict[str, Any],
    sealed_rows: list[dict[str, Any]],
    *,
    view_name: str,
) -> tuple[list[dict[str, Any]], float]:
    if not sealed_rows:
        raise ValueError("sealed S1D01 daily-return ledger is empty")
    sessions = pd.DatetimeIndex(pd.to_datetime([row["session"] for row in sealed_rows]))
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("sealed S1D01 daily-return sessions are invalid")
    if any(row.get("candidate_id") != "S1D01" for row in sealed_rows):
        raise ValueError("sealed daily-return rows contain a non-S1D01 candidate")
    values = np.asarray([float(row["net_return"]) for row in sealed_rows], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("sealed S1D01 daily returns are nonfinite")

    metrics = report["candidates"]["S1D01"]["cost_views"][view_name]
    with_terminal = metrics["with_terminal"]
    without_terminal = metrics["without_terminal"]
    with_factor = float(with_terminal["cumulative_cost_factor"])
    without_factor = float(without_terminal["cumulative_cost_factor"])
    if (
        int(with_terminal["terminal_liquidation_count"]) != 1
        or int(without_terminal["terminal_liquidation_count"]) != 0
        or without_factor <= 0.0
    ):
        raise ValueError("sealed S1D01 terminal-liquidation evidence is invalid")
    terminal_factor = with_factor / without_factor
    expected_factor = 1.0 - float(sealed_rows[-1]["cost_bps"]) / 10_000.0
    if (
        not math.isfinite(terminal_factor)
        or not 0.0 < terminal_factor <= 1.0
        or abs(terminal_factor - expected_factor) > 1e-12
    ):
        raise ValueError("sealed S1D01 terminal cost factor differs from the cost contract")

    terminal_free_rows = [dict(row) for row in sealed_rows]
    sealed_last_factor = 1.0 + float(terminal_free_rows[-1]["net_return"])
    terminal_free_rows[-1]["net_return"] = sealed_last_factor / terminal_factor - 1.0
    return terminal_free_rows, terminal_factor


def _verify_sealed_prior_r1_artifacts(root: Path) -> dict[str, Any]:
    lock_path = root / PRIOR_LOCK_PATH
    lock = _load_json(lock_path)
    if (
        lock.get("iter_id") != "mom_high_beta_sleeve_ensemble_r1"
        or lock.get("status")
        != "implementation_and_contracts_locked_before_first_R1_return_calculation"
        or lock.get("one_shot") is not True
        or lock.get("historical_candidate_outcomes_read_at_lock") is not False
        or lock.get("broker_writes") is not False
    ):
        raise ValueError("sealed prior R1 lock contract is invalid")
    lock_sha256 = _sha256(lock_path)

    receipt = _load_json(root / PRIOR_RECEIPT_PATH)
    if (
        receipt.get("iter_id") != "mom_high_beta_sleeve_ensemble_r1"
        or receipt.get("evidence_publication_status") != "complete"
        or receipt.get("workflow_pass") is not True
        or receipt.get("paper_ready_pass") is not False
    ):
        raise ValueError("sealed prior R1 evaluation receipt is invalid")
    children = receipt.get("children")
    if not isinstance(children, dict):
        raise ValueError("sealed prior R1 receipt has no child bindings")
    expected = {
        "evaluation": PRIOR_REPORT_PATH,
        "target_ledger": PRIOR_TARGET_LEDGER_PATH,
        "daily_return_ledger": PRIOR_DAILY_RETURN_LEDGER_PATH,
    }
    for child_name, expected_path in expected.items():
        binding = children.get(child_name)
        verified = _verify_binding(root, binding)
        if verified != (root / expected_path).resolve():
            raise ValueError(f"sealed prior R1 receipt child path changed: {child_name}")

    report = _load_json(root / PRIOR_REPORT_PATH)
    if (
        report.get("iter_id") != "mom_high_beta_sleeve_ensemble_r1"
        or report.get("integrity", {}).get("lock_sha256") != lock_sha256
        or report.get("integrity", {}).get("broker_writes") is not False
    ):
        raise ValueError("sealed prior R1 report does not bind its historical lock")
    return {
        "lock_sha256": lock_sha256,
        "receipt_sha256": _sha256(root / PRIOR_RECEIPT_PATH),
    }


def _target_window_with_prestart_state(
    target: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    eligible = target.index[target.index <= start]
    if eligible.empty:
        raise ValueError("R1 target stream has no state at or before the OOS start")
    initial_state_session = eligible[-1]
    window = target.loc[initial_state_session:end]
    if window.empty or window.index[0] != initial_state_session:
        raise ValueError("R1 target replication window is empty")
    return window


def build_and_verify_r01(
    root: Path,
    full_panel: R11PricePanel,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    prior_preflight = _verify_sealed_prior_r1_artifacts(root)
    prior_specs = load_prior_r1_specs(root)
    prior_contract = prior_r1_runtime_contract(prior_specs, root=root)
    prior_dataset = build_prior_r1_dataset(full_panel, prior_contract)
    prior_sleeve = prior_contract.candidate_specs["S1D01"]["spec"]["notes"]["sleeve_contract"]
    target = build_prior_r1_targets(
        full_panel,
        prior_dataset,
        anchor_weight=float(prior_contract.anchors["S1D01"]),
        sleeve_contract=prior_sleeve,
    )
    report = _load_json(root / PRIOR_REPORT_PATH)
    common_start = pd.Timestamp(report["oos_window"]["start"])
    common_end = pd.Timestamp(report["oos_window"]["end"])
    simulation = simulate_target_portfolio(
        full_panel.open,
        target,
        cost_bps=prior_contract.primary_cost_bps,
        start=common_start,
        end=common_end,
        reserve_symbol=prior_contract.reserve_symbol,
    )
    actual_metrics = _simulation_metric_views(simulation, full_panel.open)["without_terminal"]
    actual_daily_returns = _daily_returns(simulation, include_terminal=False)
    sealed_metrics = report["candidates"]["S1D01"]["cost_views"][prior_contract.primary_view_name][
        "without_terminal"
    ]
    metric_differences = {
        key: abs(float(actual_metrics[key]) - float(sealed_metrics[key]))
        for key in (
            "total_return",
            "cagr",
            "max_drawdown",
            "annualized_sharpe_excess_BIL",
            "total_reported_one_way_turnover",
        )
    }
    metric_identity = all(value <= 1e-12 for value in metric_differences.values())
    sealed_target_rows = []
    with (root / PRIOR_TARGET_LEDGER_PATH).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("candidate_id") == "S1D01":
                sealed_target_rows.append(row)
    replication_target = _target_window_with_prestart_state(
        target,
        start=common_start,
        end=common_end,
    )
    generated = {
        session.date().isoformat(): _canonical_hash(
            {
                str(symbol): float(weight)
                for symbol, weight in target.loc[session].items()
                if float(weight) > 1e-12
            }
        )
        for session in replication_target.index
    }
    ledger_identity = (
        bool(sealed_target_rows)
        and len(sealed_target_rows) == len(generated)
        and {str(row["execution_session"]) for row in sealed_target_rows} == set(generated)
        and all(
            generated.get(str(row["execution_session"])) == str(row["target_sha256"])
            for row in sealed_target_rows
        )
    )

    sealed_daily_rows: list[dict[str, Any]] = []
    sealed_daily_bytes = bytearray()
    with (root / PRIOR_DAILY_RETURN_LEDGER_PATH).open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("candidate_id") == "S1D01":
                sealed_daily_rows.append(row)
                sealed_daily_bytes.extend(line.encode("utf-8"))
    generated_daily_rows = [
        {
            "schema_version": 1,
            "iter_id": "mom_high_beta_sleeve_ensemble_r1",
            "candidate_id": "S1D01",
            "session": session.date().isoformat(),
            "net_return": float(value),
            "cost_bps": float(prior_contract.primary_cost_bps),
        }
        for session, value in actual_daily_returns.items()
    ]
    terminal_free_sealed_rows, terminal_factor = _terminal_free_prior_daily_rows(
        report,
        sealed_daily_rows,
        view_name=prior_contract.primary_view_name,
    )
    terminal_free_sealed_bytes = _canonical_jsonl_bytes(terminal_free_sealed_rows)
    generated_daily_bytes = _canonical_jsonl_bytes(generated_daily_rows)
    daily_return_identity = (
        len(terminal_free_sealed_rows) == len(generated_daily_rows)
        and terminal_free_sealed_bytes == generated_daily_bytes
    )
    if not metric_identity or not ledger_identity or not daily_return_identity:
        raise ValueError(
            "V1R01 failed sealed S1D01 target, daily-return, or terminal-free metric replication"
        )
    return target.loc[:, list(PRICE_SYMBOLS)].astype(float), {
        "status": "pass",
        "prior_lock_sha256": prior_preflight["lock_sha256"],
        "prior_receipt_sha256": prior_preflight["receipt_sha256"],
        "prior_report_sha256": _sha256(root / PRIOR_REPORT_PATH),
        "prior_target_ledger_sha256": _sha256(root / PRIOR_TARGET_LEDGER_PATH),
        "prior_daily_return_ledger_sha256": _sha256(root / PRIOR_DAILY_RETURN_LEDGER_PATH),
        "common_start": common_start.date().isoformat(),
        "common_end": common_end.date().isoformat(),
        "sealed_target_row_count": len(sealed_target_rows),
        "target_identity": ledger_identity,
        "daily_return_row_count": len(sealed_daily_rows),
        "daily_return_identity": daily_return_identity,
        "terminal_free_daily_return_identity": daily_return_identity,
        "sealed_terminal_including_daily_return_rows_sha256": hashlib.sha256(
            bytes(sealed_daily_bytes)
        ).hexdigest(),
        "terminal_liquidation_cost_factor": terminal_factor,
        "derived_terminal_free_daily_return_rows_sha256": hashlib.sha256(
            terminal_free_sealed_bytes
        ).hexdigest(),
        "generated_terminal_free_daily_return_rows_sha256": hashlib.sha256(
            generated_daily_bytes
        ).hexdigest(),
        "terminal_free_metric_identity": metric_identity,
        "metric_absolute_differences": metric_differences,
    }


R1EvaluationResult = VixEvaluationResult


def probability_backtest_overfitting_vix_r1(
    returns: pd.DataFrame,
    *,
    return_row_identities: list[dict[str, Any]],
    candidate_ids: tuple[str, ...] | list[str] = SELECTABLE_IDS,
    block_count: int = 8,
    in_sample_block_count: int = 4,
) -> dict[str, Any]:
    ids = list(candidate_ids)
    if ids != list(SELECTABLE_IDS):
        raise ValueError("VIX R1 PBO requires the exact six selection candidates in order")
    if list(returns.columns) != ids:
        raise ValueError("VIX R1 PBO return columns must exactly match candidate order")
    if (
        returns.empty
        or returns.index.has_duplicates
        or not returns.index.is_monotonic_increasing
        or not np.isfinite(returns.to_numpy(dtype=float)).all()
    ):
        raise ValueError("VIX R1 PBO common return matrix is incomplete")
    result = probability_backtest_overfitting_r6(
        returns,
        candidate_ids=ids,
        block_count=block_count,
        in_sample_block_count=in_sample_block_count,
    )
    expected = math.comb(block_count, in_sample_block_count)
    quotient, remainder = divmod(len(returns), block_count)
    expected_block_counts = [
        quotient + (1 if index < remainder else 0) for index in range(block_count)
    ]
    observed_block_counts = [int(row["observation_count"]) for row in result["blocks"]]
    if (
        block_count != 8
        or in_sample_block_count != 4
        or result.get("partition_count") != expected
        or result.get("valid_partition_count") != expected
        or expected != 70
        or observed_block_counts != expected_block_counts
    ):
        raise ValueError("VIX R1 PBO did not evaluate all 70 directional partitions")
    if len(returns) == 1631 and observed_block_counts != [204] * 7 + [203]:
        raise ValueError("VIX R1 PBO frozen block sizes changed")
    if len(return_row_identities) != len(returns):
        raise ValueError("VIX R1 PBO return-row identity count differs from returns")
    source_row_identities: list[dict[str, Any]] = []
    for position, (session, identity) in enumerate(
        zip(returns.index, return_row_identities, strict=True)
    ):
        fold_id = str(identity.get("fold_id", ""))
        interval_start = pd.Timestamp(identity.get("interval_start"))
        interval_end = pd.Timestamp(identity.get("interval_end"))
        if (
            fold_id not in {"F1", "F2", "F3", "F4"}
            or pd.isna(interval_start)
            or pd.isna(interval_end)
            or interval_start >= interval_end
            or interval_end != pd.Timestamp(session)
        ):
            raise ValueError("VIX R1 PBO return-row identity is invalid")
        source_row_identities.append(
            {
                "row_position": position,
                "fold_id": fold_id,
                "interval_start": interval_start.isoformat(),
                "interval_end": interval_end.isoformat(),
            }
        )
    source_rows = [
        {
            **identity,
            **{
                candidate_id: float(returns.iloc[position][candidate_id])
                for candidate_id in SELECTABLE_IDS
            },
        }
        for position, identity in enumerate(source_row_identities)
    ]
    fold_counts = {
        fold_id: sum(row["fold_id"] == fold_id for row in source_row_identities)
        for fold_id in ("F1", "F2", "F3", "F4")
    }
    if len(returns) == 1631 and list(fold_counts.values()) != [408, 408, 408, 407]:
        raise ValueError("VIX R1 PBO frozen fold identity counts changed")
    return {
        **result,
        "contract_id": "vix_r1_strict_8_block_4_vs_4_pbo_v1",
        "candidate_ids": list(SELECTABLE_IDS),
        "return_observation_count": len(returns),
        "expected_block_observation_counts": expected_block_counts,
        "return_source_row_identity_schema": [
            "row_position",
            "fold_id",
            "interval_start",
            "interval_end",
        ],
        "return_source_row_identity_count": len(source_row_identities),
        "return_source_fold_counts": fold_counts,
        "return_source_first_identity": source_row_identities[0],
        "return_source_last_identity": source_row_identities[-1],
        "return_source_row_identity_sha256": _canonical_hash(source_row_identities),
        "return_source_rows_sha256": _canonical_hash(source_rows),
        "return_source_csv_sha256": hashlib.sha256(
            returns.to_csv(float_format="%.17g", lineterminator="\n").encode("utf-8")
        ).hexdigest(),
    }


probability_backtest_overfitting_r1 = probability_backtest_overfitting_vix_r1


def deflated_sharpe_ratio_vix_r1(
    returns: pd.Series,
    *,
    trial_count: int = 8147,
    hac_lag: int = 21,
) -> dict[str, Any]:
    if trial_count != 8147 or hac_lag != 21:
        raise ValueError("VIX R1 DSR trial count or HAC lag differs from the frozen contract")
    result = deflated_sharpe_ratio_r6(
        pd.Series(returns, index=returns.index, dtype=float),
        trial_count=trial_count,
        scope_ids=["FULL_OOS_CONTINUOUS"] * len(returns),
        hac_lag=hac_lag,
    )
    if result.get("promotion_probability") != min(
        result.get("iid_probability"), result.get("hac_probability")
    ):
        raise AssertionError("VIX R1 DSR promotion probability is not the strict minimum")
    return {
        **result,
        "contract_id": "vix_r1_iid_plus_influence_hac_dsr_v1",
        "hac_scope": "single_continuous_terminal_free_OOS_return_stream",
    }


deflated_sharpe_ratio_r1 = deflated_sharpe_ratio_vix_r1


def _validate_dsr_evidence_identity(
    dsr: dict[str, dict[str, Any]],
    contract: VixRuntimeContract,
) -> None:
    if tuple(dsr) != CANDIDATE_IDS:
        raise ValueError("VIX R1 DSR evidence candidate inventory drifted from the frozen contract")
    expected_scope = str(contract.validation["dsr"]["hac_scope"])
    mismatched = [
        candidate_id
        for candidate_id, result in dsr.items()
        if result.get("hac_scope") != expected_scope
    ]
    if mismatched:
        raise ValueError(
            "VIX R1 DSR HAC scope drifted from the frozen contract for " + ", ".join(mismatched)
        )


def common_oos_return_matrix(
    returns: dict[str, pd.Series],
    *,
    candidate_ids: tuple[str, ...] | list[str],
) -> pd.DataFrame:
    ids = list(candidate_ids)
    if set(returns) < set(ids):
        raise ValueError("VIX R1 common return matrix is missing a candidate")
    reference: pd.DatetimeIndex | None = None
    columns: dict[str, np.ndarray] = {}
    for candidate_id in ids:
        series = returns[candidate_id]
        index = pd.DatetimeIndex(series.index)
        if index.has_duplicates or not index.is_monotonic_increasing:
            raise ValueError(f"VIX R1 return index is invalid: {candidate_id}")
        if reference is None:
            reference = index
        elif not index.equals(reference):
            raise ValueError("VIX R1 candidate return indices differ; substitution is forbidden")
        values = series.to_numpy(dtype=float)
        if len(values) < 2 or not np.isfinite(values).all():
            raise ValueError(f"VIX R1 candidate returns are incomplete: {candidate_id}")
        columns[candidate_id] = values
    assert reference is not None
    return pd.DataFrame(columns, index=reference, columns=ids)


def _return_scope_ids(
    return_index: pd.DatetimeIndex,
    folds: list[dict[str, Any]],
) -> list[str]:
    starts = [pd.Timestamp(fold["test_start"]) for fold in folds]
    output: list[str] = []
    for session in return_index:
        # Return indices are interval ends. A return ending exactly at the next
        # fold start was initiated by the prior fold's last target.
        interval_start_position = max(
            index for index, start in enumerate(starts) if start < pd.Timestamp(session)
        )
        output.append(str(folds[interval_start_position]["fold_id"]))
    return output


def _fold_return_metrics(
    returns: pd.Series,
    panel: R11PricePanel,
) -> dict[str, Any]:
    values = pd.Series(returns, index=returns.index, dtype=float)
    if len(values) < 2 or not np.isfinite(values.to_numpy()).all():
        raise ValueError("VIX R1 fold return slice must contain finite observations")
    positions = panel.open.index.get_indexer(values.index)
    if (positions <= 0).any():
        raise ValueError("VIX R1 fold return dates do not map to open intervals")
    prior = positions - 1
    tqqq = (
        panel.open["TQQQ"].iloc[positions].to_numpy(dtype=float)
        / panel.open["TQQQ"].iloc[prior].to_numpy(dtype=float)
        - 1.0
    )
    bil = (
        panel.open["BIL"].iloc[positions].to_numpy(dtype=float)
        / panel.open["BIL"].iloc[prior].to_numpy(dtype=float)
        - 1.0
    )
    equity = (1.0 + values).cumprod()
    curve = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)], ignore_index=True)
    drawdown = curve / curve.cummax() - 1.0
    maximum_drawdown = float(drawdown.min())
    years = len(values) / 252.0
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0)
    excess = values.to_numpy(dtype=float) - bil
    excess_std = float(np.std(excess, ddof=1))
    sharpe = float(np.mean(excess) / excess_std * math.sqrt(252.0)) if excess_std > 0 else 0.0
    up = tqqq > 0
    down = tqqq < 0
    return {
        "market_interval_count": len(values),
        "total_return": float(equity.iloc[-1] - 1.0),
        "total_return_pct": float((equity.iloc[-1] - 1.0) * 100.0),
        "cagr": cagr,
        "cagr_pct": cagr * 100.0,
        "annualized_sharpe_excess_BIL": sharpe,
        "max_drawdown": maximum_drawdown,
        "max_drawdown_pct": maximum_drawdown * 100.0,
        "mar": cagr / abs(maximum_drawdown) if maximum_drawdown < 0 else None,
        "tqqq_up_capture": float(np.mean(values.to_numpy()[up]) / np.mean(tqqq[up]))
        if up.any() and float(np.mean(tqqq[up])) != 0.0
        else 0.0,
        "tqqq_down_capture": float(np.mean(values.to_numpy()[down]) / np.mean(tqqq[down]))
        if down.any() and float(np.mean(tqqq[down])) != 0.0
        else 0.0,
        "terminal_liquidation_included": False,
    }


def _run_cost_views(
    opens: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_views: dict[str, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    metrics: dict[str, Any] = {}
    simulations: dict[str, Any] = {}
    for view_name, cost_bps in cost_views.items():
        simulation = simulate_target_portfolio(
            opens,
            targets,
            cost_bps=cost_bps,
            start=start,
            end=end,
            reserve_symbol="BIL",
        )
        simulations[view_name] = simulation
        metrics[view_name] = {
            "terminal_free": _simulation_metric_views(simulation, opens)["without_terminal"]
        }
    return metrics, simulations


def _evaluate_candidates(
    panel: R11PricePanel,
    targets: dict[str, pd.DataFrame],
    contract: VixRuntimeContract,
    folds: list[dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, pd.Series],
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
]:
    start = pd.Timestamp(folds[0]["test_start"])
    end = panel.open.index[-1]
    candidate_payloads: dict[str, Any] = {}
    returns: dict[str, pd.Series] = {}
    daily_rows: list[dict[str, Any]] = []
    fold_results: dict[str, list[dict[str, Any]]] = {}
    qqq_continuous = _daily_returns(
        _simulate_static(
            panel.open,
            {"QQQ": 1.0},
            start=start,
            end=end,
            cost_bps=contract.primary_cost_bps,
        ),
        include_terminal=False,
    )
    for candidate_id in CANDIDATE_IDS:
        cost_metrics, simulations = _run_cost_views(
            panel.open,
            targets[candidate_id],
            start=start,
            end=end,
            cost_views=contract.cost_views,
        )
        primary = simulations["primary_20bps"]
        terminal_free = _daily_returns(primary, include_terminal=False)
        if len(terminal_free) != 1631:
            raise ValueError(f"VIX R1 primary return count changed: {candidate_id}")
        returns[candidate_id] = terminal_free
        return_scopes = pd.Series(
            _return_scope_ids(pd.DatetimeIndex(terminal_free.index), folds),
            index=terminal_free.index,
            dtype="object",
        )
        fold_rows: list[dict[str, Any]] = []
        for fold in folds:
            mask = return_scopes == str(fold["fold_id"])
            candidate_slice = terminal_free.loc[mask]
            qqq_slice = qqq_continuous.loc[mask]
            if not candidate_slice.index.equals(qqq_slice.index):
                raise ValueError("VIX R1 fold candidate and QQQ indices differ")
            candidate_metrics = _fold_return_metrics(candidate_slice, panel)
            qqq_metrics = _fold_return_metrics(qqq_slice, panel)
            fold_rows.append(
                {
                    **fold,
                    "return_interval_count": len(candidate_slice),
                    "continuous_ledger_slice": True,
                    "independent_fold_entry_cost": False,
                    "terminal_free_metrics": candidate_metrics,
                    "qqq_terminal_free_metrics": qqq_metrics,
                    "qqq_cagr_lift_pct_points": float(
                        candidate_metrics["cagr_pct"] - qqq_metrics["cagr_pct"]
                    ),
                }
            )
        fold_results[candidate_id] = fold_rows
        candidate_payloads[candidate_id] = {
            "candidate_id": candidate_id,
            "spec_path": SPEC_PATHS[candidate_id].as_posix(),
            "spec_semantic_sha256": contract.candidate_specs[candidate_id]["semantic_sha256"],
            "target_row_count": len(targets[candidate_id]),
            "target_stream_sha256": hashlib.sha256(
                canonical_target_bytes(targets[candidate_id])
            ).hexdigest(),
            "cost_views": cost_metrics,
            "folds": fold_rows,
        }
        primary_daily = primary.daily.copy()
        if len(primary_daily) != len(terminal_free):
            raise ValueError("VIX R1 primary daily ledger contains a terminal row")
        primary_values = terminal_free.to_numpy(dtype=float)
        for row_number, row in primary_daily.iterrows():
            interval_end = pd.Timestamp(row["interval_end"])
            scope_id = return_scopes.at[interval_end]
            daily_rows.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "candidate_id": candidate_id,
                    "scope_id": str(scope_id),
                    "cost_view": "primary_20bps",
                    "terminal_free": True,
                    "interval_start": str(row["interval_start"]),
                    "interval_end": str(row["interval_end"]),
                    "net_return": float(primary_values[row_number]),
                }
            )
    return candidate_payloads, returns, daily_rows, fold_results


def _benchmark_family(
    panel: R11PricePanel,
    contract: VixRuntimeContract,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    definitions = {
        "TQQQ_buy_hold_same_symbol": {"TQQQ": 1.0},
        "equal_weight_universe": {symbol: 1.0 / len(PRICE_SYMBOLS) for symbol in PRICE_SYMBOLS},
        "SPY_market_proxy": {"SPY": 1.0},
        "XLK_sector_theme_proxy": {"XLK": 1.0},
        "BIL_cash_proxy": {"BIL": 1.0},
        "QQQ_buy_hold": {"QQQ": 1.0},
    }
    output: dict[str, Any] = {}
    for benchmark_id, weights in definitions.items():
        output[benchmark_id] = {
            "weights": weights,
            "cost_views": {
                view_name: {
                    "terminal_free": _simulation_metric_views(
                        _simulate_static(
                            panel.open,
                            weights,
                            start=start,
                            end=end,
                            cost_bps=cost_bps,
                        ),
                        panel.open,
                    )["without_terminal"]
                }
                for view_name, cost_bps in contract.cost_views.items()
            },
        }
    symbol_results = {
        symbol: {
            view_name: _simulation_metric_views(
                _simulate_static(
                    panel.open,
                    {symbol: 1.0},
                    start=start,
                    end=end,
                    cost_bps=cost_bps,
                ),
                panel.open,
            )["without_terminal"]
            for view_name, cost_bps in contract.cost_views.items()
        }
        for symbol in PRICE_SYMBOLS
    }
    best = max(
        PRICE_SYMBOLS,
        key=lambda symbol: (
            symbol_results[symbol]["primary_20bps"]["cagr"],
            symbol,
        ),
    )
    output["ex_post_best_symbol_report_only"] = {
        "symbol": best,
        "promotion_eligible": False,
        "cost_views": {
            name: {"terminal_free": metrics} for name, metrics in symbol_results[best].items()
        },
    }
    return output


def _paired_log_wealth(left: pd.Series, right: pd.Series) -> float:
    if not left.index.equals(right.index):
        raise ValueError("VIX R1 paired return indices differ")
    left_values = left.to_numpy(dtype=float)
    right_values = right.to_numpy(dtype=float)
    if (
        not np.isfinite(left_values).all()
        or not np.isfinite(right_values).all()
        or (left_values <= -1.0).any()
        or (right_values <= -1.0).any()
    ):
        raise ValueError("VIX R1 paired returns are invalid")
    return float(np.log1p(right_values).sum() - np.log1p(left_values).sum())


def _passes_sharpe_gate(actual: float, family_contract: dict[str, Any]) -> bool:
    threshold = float(family_contract["Sharpe_floor"])
    operator = str(family_contract.get("Sharpe_operator", "greater_than_or_equal"))
    if operator == "strictly_greater_than":
        return actual > threshold
    if operator == "greater_than_or_equal":
        return actual >= threshold
    raise ValueError(f"VIX R1 unsupported Sharpe gate operator: {operator}")


def _candidate_and_family_gates(
    candidates: dict[str, Any],
    benchmarks: dict[str, Any],
    dsr: dict[str, Any],
    pbo: dict[str, Any],
    predictions: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    return_streams: dict[str, pd.Series],
    replication: dict[str, Any],
    contract: VixRuntimeContract,
) -> tuple[dict[str, Any], dict[str, Any]]:
    family_contract = contract.validation["family_gates"]
    ml_contract = contract.validation["ML_gates"]
    modality_contract = contract.validation["modality_gates"]
    primary_id = str(family_contract["primary_candidate_id"])
    qqq_metrics = benchmarks["QQQ_buy_hold"]["cost_views"]["primary_20bps"]["terminal_free"]
    tqqq_metrics = benchmarks["TQQQ_buy_hold_same_symbol"]["cost_views"]["primary_20bps"][
        "terminal_free"
    ]

    family_by_candidate: dict[str, dict[str, bool]] = {}
    for candidate_id in SELECTABLE_IDS:
        metrics = candidates[candidate_id]["cost_views"]["primary_20bps"]["terminal_free"]
        positive_lift_folds = sum(
            float(row["qqq_cagr_lift_pct_points"]) > 0.0
            for row in candidates[candidate_id]["folds"]
        )
        family_by_candidate[candidate_id] = {
            "net_CAGR_floor": float(metrics["cagr_pct"])
            >= float(family_contract["net_CAGR_floor_pct"]),
            "maximum_drawdown_floor": float(metrics["max_drawdown_pct"])
            >= float(family_contract["maximum_drawdown_floor_pct"]),
            "Sharpe_floor": _passes_sharpe_gate(
                float(metrics["annualized_sharpe_excess_BIL"]), family_contract
            ),
            "MAR_floor": metrics["mar"] is not None
            and float(metrics["mar"]) >= float(family_contract["MAR_floor"]),
            "matched_QQQ_CAGR_lift": float(metrics["cagr_pct"] - qqq_metrics["cagr_pct"])
            >= float(family_contract["matched_QQQ_CAGR_lift_floor_pct_points"]),
            "matched_TQQQ_CAGR_fraction": float(metrics["cagr"])
            >= float(family_contract["matched_TQQQ_CAGR_fraction_floor"])
            * max(float(tqqq_metrics["cagr"]), 0.0),
            "TQQQ_up_capture": float(metrics["tqqq_up_capture"])
            >= float(family_contract["TQQQ_up_capture_floor"]),
            "TQQQ_down_capture": float(metrics["tqqq_down_capture"])
            <= float(family_contract["TQQQ_down_capture_ceiling"]),
            "positive_QQQ_lift_folds": positive_lift_folds
            >= int(family_contract["positive_QQQ_lift_folds_min"]),
            "DSR_probability": float(dsr[candidate_id]["promotion_probability"])
            >= float(family_contract["DSR_probability_floor"]),
            "PBO_probability": float(pbo["probability"]) <= float(family_contract["PBO_ceiling"]),
            "PBO_partition_count": int(pbo["valid_partition_count"])
            >= int(family_contract["pbo_min_partitions"]),
        }

    scopes = pd.Series(
        _return_scope_ids(
            pd.DatetimeIndex(return_streams["V1Q01"].index),
            candidates["V1Q01"]["folds"],
        ),
        index=return_streams["V1Q01"].index,
        dtype="object",
    )

    def paired_evidence(candidate_id: str, fallback_id: str) -> dict[str, Any]:
        fold_values = [
            _paired_log_wealth(
                return_streams[fallback_id].loc[scopes == str(fold["fold_id"])],
                return_streams[candidate_id].loc[scopes == str(fold["fold_id"])],
            )
            for fold in candidates[candidate_id]["folds"]
        ]
        aggregate = _paired_log_wealth(return_streams[fallback_id], return_streams[candidate_id])
        return {
            "fallback_candidate_id": fallback_id,
            "fold_log_wealth_values": fold_values,
            "folds_beating_fallback": sum(value > 0.0 for value in fold_values),
            "aggregate_log_wealth_value": aggregate,
        }

    fallback_ids = {"V1M01": "V1Q01", "V1M02": "V1Q01", "V1C01": "V1Q01"}
    m01_predictions_by_session = {
        str(row["execution_session"]): row for row in predictions if row["candidate_id"] == "V1M01"
    }
    f01_m01_target_identity = (
        candidates["V1F01"]["target_stream_sha256"] == candidates["V1M01"]["target_stream_sha256"]
    )
    ml_evidence: dict[str, dict[str, Any]] = {}
    for candidate_id, fallback_id in fallback_ids.items():
        paired = paired_evidence(candidate_id, fallback_id)
        candidate_predictions = [row for row in predictions if row["candidate_id"] == candidate_id]
        non_override_predictions = [
            row for row in candidate_predictions if not bool(row["effective_override"])
        ]
        missing_modality_predictions = [
            row
            for row in candidate_predictions
            if row.get("fallback_reason") == "missing_vix_exact_candidate_fallback"
        ]
        fitted_records = [
            row
            for row in model_records
            if row["candidate_id"] == candidate_id
            and row["status"] == "fitted_and_chronologically_calibrated"
        ]
        candidate_metrics = candidates[candidate_id]["cost_views"]["primary_20bps"]["terminal_free"]
        fallback_metrics = candidates[fallback_id]["cost_views"]["primary_20bps"]["terminal_free"]
        override_count = sum(bool(row["effective_override"]) for row in candidate_predictions)
        exact_fallback = bool(non_override_predictions) and all(
            row["selected_target_sha256"] == row["fallback_target_sha256"]
            for row in non_override_predictions
        )
        c01_missing_identity = candidate_id != "V1C01" or (
            f01_m01_target_identity
            and all(
                row.get("fallback_candidate_id") == "V1M01"
                and row["fallback_target_sha256"]
                == m01_predictions_by_session.get(str(row["execution_session"]), {}).get(
                    "selected_target_sha256"
                )
                for row in missing_modality_predictions
            )
        )
        exact_fallback = exact_fallback and c01_missing_identity
        calibration_present = bool(fitted_records) and all(
            int(row["calibration_row_count"]) > 0
            and bool(row["class_checks"]["calibration_rows"])
            and bool(row["class_checks"]["calibration_positive"])
            and bool(row["class_checks"]["calibration_negative"])
            and math.isfinite(float(row["calibrated_brier"]))
            for row in fitted_records
        )
        upside_threshold = float(ml_contract["minimum_primary_upside_capture_retained"])
        checks = {
            "minimum_effective_overrides": override_count
            >= int(ml_contract["minimum_effective_overrides"]),
            "minimum_folds_beating_fallback": int(paired["folds_beating_fallback"])
            >= int(ml_contract["minimum_folds_beating_fallback"]),
            "aggregate_realized_override_value_strictly_positive": float(
                paired["aggregate_log_wealth_value"]
            )
            > 0.0,
            "calibration_required": calibration_present,
            "exact_fallback_required": exact_fallback,
            "minimum_primary_upside_capture_retained": float(candidate_metrics["tqqq_up_capture"])
            >= upside_threshold * float(fallback_metrics["tqqq_up_capture"]),
        }
        ml_evidence[candidate_id] = {
            **paired,
            "effective_override_count": override_count,
            "non_override_identity_count": len(non_override_predictions),
            "missing_modality_event_count": len(missing_modality_predictions),
            "c01_missing_VIX_exact_M01_and_F01_identity": c01_missing_identity,
            "fitted_model_record_count": len(fitted_records),
            "checks": checks,
            "pass": all(checks.values()),
        }

    combined = paired_evidence("V1C01", "V1M01")
    combined_checks = {
        "combined_ML_beats_price_ML_folds": int(combined["folds_beating_fallback"])
        >= int(ml_contract["combined_ML_beats_price_ML_folds_min"]),
        "combined_ML_beats_price_ML_aggregate_strictly_positive": float(
            combined["aggregate_log_wealth_value"]
        )
        > 0.0,
    }
    combined_pass = all(combined_checks.values())
    ml_contribution_pass = bool(all(row["pass"] for row in ml_evidence.values()) and combined_pass)
    ml_family_pass_candidate_ids = [
        candidate_id
        for candidate_id in ("V1M01", "V1M02", "V1C01")
        if all(family_by_candidate[candidate_id].values())
    ]
    ml_strategy_pass = bool(ml_family_pass_candidate_ids)

    v01 = paired_evidence("V1V01", "V1Q01")
    d02 = paired_evidence("V1D02", "V1Q01")
    f01_identity = candidates["V1F01"]["target_stream_sha256"] == candidates["V1M01"][
        "target_stream_sha256"
    ] and return_streams["V1F01"].equals(return_streams["V1M01"])
    p01_value = _paired_log_wealth(return_streams["V1C01"], return_streams["V1P01"])
    modality_checks = {
        "V1R01_exact_S1D01_replication": replication.get("status") == "pass"
        and replication.get("target_identity") is True
        and replication.get("terminal_free_daily_return_identity") is True
        and replication.get("terminal_free_metric_identity") is True,
        "V1F01_exact_V1M01_target_identity": f01_identity,
        "V1V01_folds_beating_V1Q01": int(v01["folds_beating_fallback"])
        >= int(modality_contract["V1V01_folds_beating_V1Q01_min"]),
        "V1V01_aggregate_after_cost_lift_over_V1Q01_strictly_positive": float(
            v01["aggregate_log_wealth_value"]
        )
        > 0.0,
        "V1D02_folds_beating_V1Q01": int(d02["folds_beating_fallback"])
        >= int(modality_contract["V1D02_folds_beating_V1Q01_min"]),
        "V1P01_must_not_match_or_beat_V1C01": candidates["V1P01"]["target_stream_sha256"]
        != candidates["V1C01"]["target_stream_sha256"]
        and p01_value < 0.0,
    }
    modality_pass = all(modality_checks.values())
    family_pass = all(family_by_candidate[primary_id].values())
    research_pass = bool(family_pass and modality_pass)

    candidate_gates: dict[str, dict[str, Any]] = {}
    for candidate_id in CANDIDATE_IDS:
        manifest_row = next(
            row for row in contract.manifest["candidates"] if row["candidate_id"] == candidate_id
        )
        checks: dict[str, bool]
        if candidate_id in SELECTABLE_IDS:
            checks = dict(family_by_candidate[candidate_id])
            if candidate_id == "V1V01":
                checks.update(
                    {
                        key: modality_checks[key]
                        for key in (
                            "V1V01_folds_beating_V1Q01",
                            "V1V01_aggregate_after_cost_lift_over_V1Q01_strictly_positive",
                        )
                    }
                )
            elif candidate_id == "V1D02":
                checks["V1D02_folds_beating_V1Q01"] = modality_checks["V1D02_folds_beating_V1Q01"]
            elif candidate_id in ml_evidence:
                checks.update(ml_evidence[candidate_id]["checks"])
                if candidate_id == "V1C01":
                    checks.update(combined_checks)
        else:
            diagnostic_key = {
                "V1R01": "V1R01_exact_S1D01_replication",
                "V1F01": "V1F01_exact_V1M01_target_identity",
                "V1P01": "V1P01_must_not_match_or_beat_V1C01",
            }[candidate_id]
            checks = {diagnostic_key: modality_checks[diagnostic_key]}
        candidate_gates[candidate_id] = {
            "selection_eligible": bool(manifest_row["selection_eligible"]),
            "promotion_eligible": bool(manifest_row["promotion_eligible"]),
            "diagnostic_only": bool(manifest_row["diagnostic_only"]),
            "checks": checks,
            "pass": all(checks.values()),
        }

    payload = {
        "primary_candidate_id": primary_id,
        "family": family_by_candidate[primary_id],
        "family_by_candidate": family_by_candidate,
        "family_pass": family_pass,
        "modality": {
            "checks": modality_checks,
            "pass": modality_pass,
            "V1V01_vs_V1Q01": v01,
            "V1D02_vs_V1Q01": d02,
            "V1P01_vs_V1C01_aggregate_log_wealth_value": p01_value,
        },
        "modality_pass": modality_pass,
        "research_pass": research_pass,
        "ml": ml_evidence,
        "combined_vs_price_ML": {
            **combined,
            "checks": combined_checks,
            "pass": combined_pass,
        },
        "ml_contribution_pass": ml_contribution_pass,
        "ml_strategy_pass": ml_strategy_pass,
        "ml_family_pass_candidate_ids": ml_family_pass_candidate_ids,
    }
    return candidate_gates, payload


def _render_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# {_report_title()}",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- ML contribution pass: `{payload['ml_contribution_pass']}`",
        f"- ML strategy pass: `{payload['ml_strategy_pass']}`",
        f"- Strategy group pass: `{payload['strategy_group_pass']}`",
        f"- Paper ready pass: `{payload['paper_ready_pass']}`",
        f"- Effective trial count: `{payload['statistics']['effective_trial_count']}`",
        f"- PBO: `{payload['statistics']['PBO']['probability']:.6f}`",
        "",
        "| Candidate | CAGR | MDD | Sharpe | MAR | DSR | Pass |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate_id in CANDIDATE_IDS:
        candidate = payload["candidates"][candidate_id]
        metrics = candidate["cost_views"]["primary_20bps"]["terminal_free"]
        mar = "n/a" if metrics["mar"] is None else f"{float(metrics['mar']):.3f}"
        lines.append(
            f"| {candidate_id} | {float(metrics['cagr_pct']):.2f}% | "
            f"{float(metrics['max_drawdown_pct']):.2f}% | "
            f"{float(metrics['annualized_sharpe_excess_BIL']):.3f} | {mar} | "
            f"{float(payload['statistics']['DSR'][candidate_id]['promotion_probability']):.4f} | "
            f"{candidate['gates']['pass']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            payload["interpretation"],
            "",
            "All authoritative returns are terminal-free next-open research streams. No Paper order was submitted, and the trial Cboe snapshot is not paper-ready evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def _strategy_group_outcome(
    *,
    research_pass: bool,
    ml_contribution_pass: bool,
    ml_strategy_pass: bool,
) -> tuple[bool, str, str]:
    strategy_group_pass = bool(research_pass and ml_contribution_pass and ml_strategy_pass)
    if strategy_group_pass:
        interpretation = (
            "The preregistered V1D02 primary and matched ML family cleared every frozen "
            "terminal-free, robustness, and incremental-value gate. The result may authorize "
            "parity and readiness engineering, but not paper readiness or Paper orders."
        )
    elif research_pass and ml_strategy_pass:
        interpretation = (
            "The deterministic primary cleared its frozen family and modality gates, but the "
            "matched ML family did not clear every incremental-value gate. The requested "
            "strategy group therefore fails and is sealed without parameter rescue."
        )
    elif research_pass:
        interpretation = (
            "The deterministic primary cleared its frozen family and modality gates, but no "
            "ML candidate cleared the same return, risk, DSR, PBO, and Sharpe family gates. "
            "The requested strategy group therefore fails without parameter rescue."
        )
    else:
        interpretation = (
            "The preregistered primary did not clear every frozen return, benchmark, fold, "
            "cost, DSR, PBO, and modality gate. The family is sealed without parameter rescue."
        )
    return strategy_group_pass, "continue" if strategy_group_pass else "stop", interpretation


def _publication_binding(
    path: Path,
    *,
    root: Path,
    staging_dir: Path,
    destination_dir: Path,
) -> dict[str, Any]:
    relative = path.resolve().relative_to(staging_dir.resolve())
    raw = path.read_bytes()
    return {
        "path": (destination_dir / relative).relative_to(root.resolve()).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }


def _prelock_activity(contract: VixRuntimeContract) -> dict[str, Any]:
    if ITER_ID != REPAIR_ITER_ID:
        return {
            "scope": "synthetic_behavior_and_static_repository_contract_binding_tests",
            "synthetic_behavior_tests_run": True,
            "static_repository_contract_binding_tests_run": True,
            "historical_candidate_returns_computed": False,
            "historical_model_predictions_inspected": False,
            "parameter_changes_from_outcomes": False,
        }

    parent_audit = contract.contracts["parent-failure-audit.json"]
    failure = parent_audit["failure"]
    exposure = parent_audit["exposure"]
    return {
        "scope": "pure_implementation_repair_after_parent_historical_failure",
        "source_iteration_id": BASE_ITER_ID,
        "synthetic_behavior_tests_run": True,
        "static_repository_contract_binding_tests_run": True,
        "source_selectable_candidate_returns_computed": failure[
            "selectable_candidate_returns_computed"
        ],
        "source_selectable_candidate_metrics_computed": failure[
            "selectable_candidate_metrics_computed"
        ],
        "source_historical_targets_computed": exposure["historical_targets_computed"],
        "source_historical_predictions_computed": exposure["historical_predictions_computed"],
        "source_historical_predictions_inspected": exposure["historical_predictions_inspected"],
        "source_unpersisted_refit_attempts_upper_bound": exposure[
            "unpersisted_refit_attempts_upper_bound"
        ],
        "source_persisted_model_ids": exposure["persisted_model_ids"],
        "new_economic_candidate_count": 0,
        "parameter_changes_from_outcomes": parent_audit["parameter_changes_from_outcomes"],
    }


def _reserve_evaluation_attempt(root: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    base = root.resolve()
    path = base / EVALUATION_ATTEMPT_PATH
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("VIX R1 evaluation-attempt parent is invalid")
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "lock_contract": LOCK_CONTRACT_ID,
        "status": "reserved_after_preflight_before_first_price_or_model_operation",
        "reserved_at": datetime.now(UTC).isoformat(),
        "lock_path": preflight["lock_path"],
        "lock_sha256": preflight["lock_sha256"],
        "runtime_contract_sha256": preflight["runtime_contract_sha256"],
        "dossier_checked_at": preflight["dossier_checked_at"],
        "rerun_policy": "any_existing_attempt_permanently_blocks_future_evaluation_attempts",
        "order_authority": False,
        "broker_writes": False,
    }
    content = _canonical_json_bytes(payload)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError as exc:
        raise ValueError("VIX R1 evaluation attempt already exists; rerun is prohibited") from exc
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write VIX R1 evaluation-attempt receipt")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_descriptor = os.open(path.parent, directory_flags)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return _binding(EVALUATION_ATTEMPT_PATH, base)


def _validate_publication_status_identity(
    payload: dict[str, Any],
    receipt: dict[str, Any],
    *,
    evaluation_attempt: dict[str, Any],
    root: Path,
) -> None:
    status_fields = (
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "ml_contribution_pass",
        "ml_strategy_pass",
        "strategy_group_pass",
        "paper_ready_pass",
        "paper_entry_ready",
        "paper_validated",
    )
    if (
        payload.get("iter_id") != ITER_ID
        or payload.get("report_type") != _report_type()
        or receipt.get("iter_id") != ITER_ID
        or receipt.get("evaluation_attempt") != evaluation_attempt
        or payload.get("integrity", {}).get("evaluation_attempt") != evaluation_attempt
    ):
        raise ValueError("VIX R1 report, receipt, or attempt identity changed")
    _verify_binding(root, evaluation_attempt)
    for field_name in status_fields:
        if type(payload.get(field_name)) is not bool or type(receipt.get(field_name)) is not bool:
            raise ValueError(f"VIX R1 publication status is not boolean: {field_name}")
        if payload[field_name] != receipt[field_name]:
            raise ValueError(f"VIX R1 report/receipt status mismatch: {field_name}")
    if payload.get("decision") != receipt.get("decision"):
        raise ValueError("VIX R1 report/receipt decision mismatch")
    expected_group_pass = bool(
        payload["research_pass"] and payload["ml_contribution_pass"] and payload["ml_strategy_pass"]
    )
    if (
        payload["strategy_group_pass"] is not expected_group_pass
        or payload["decision"] != ("continue" if expected_group_pass else "stop")
        or payload["paper_ready_pass"] is not False
        or payload["paper_entry_ready"] is not False
        or payload["paper_validated"] is not False
    ):
        raise ValueError("VIX R1 publication decision/status semantics changed")


def freeze(root: Path) -> Path:
    base = root.resolve()
    lock_path = base / LOCK_PATH
    output = base / OUTPUT_DIR
    attempt = base / EVALUATION_ATTEMPT_PATH
    if lock_path.exists() or lock_path.parent.exists():
        raise ValueError("VIX R1 historical evaluation lock already exists")
    if (
        output.exists()
        or attempt.exists()
        or attempt.is_symlink()
        or any((base / ITERATION_DIR).glob("evaluation-run.staging-*"))
    ):
        raise ValueError("VIX R1 historical evaluation state exists before lock")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("VIX R1 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    specs = load_and_validate_specs(base)
    contract = runtime_contract_from_specs(specs, root=base)
    lock = {
        "schema_version": 1,
        "lock_contract": LOCK_CONTRACT_ID,
        "iter_id": ITER_ID,
        "created_at": datetime.now(UTC).isoformat(),
        "status": LOCK_STATUS,
        "one_shot": True,
        "effective_trial_count": contract.effective_trial_count,
        "cost_views_bps": contract.cost_views,
        "fold_count": int(contract.validation["chronological_folds"]["count"]),
        "fold_sessions": int(contract.validation["chronological_folds"]["oos_sessions"]),
        "runtime_contract_sha256": contract.sha256,
        "runtime_contract": contract.to_dict(),
        "contracts": [contract.file_bindings[name] for name in ITERATION_FILES],
        "external_inputs": [
            {"name": name, **_binding(path, base)} for name, path in EXTERNAL_INPUT_PATHS.items()
        ],
        "specs": [
            {
                "candidate_id": candidate_id,
                **_binding(path, base),
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
            for candidate_id, path in SPEC_PATHS.items()
        ],
        "implementation": [_binding(path, base) for path in IMPLEMENTATION_PATHS],
        "prelock_activity": _prelock_activity(contract),
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
    if not lock_path.is_file():
        raise ValueError("VIX R1 historical evaluation lock is missing")
    lock = _load_json(lock_path)
    specs = load_and_validate_specs(base)
    contract = runtime_contract_from_specs(specs, root=base)
    if (
        lock.get("schema_version") != 1
        or lock.get("lock_contract") != LOCK_CONTRACT_ID
        or lock.get("iter_id") != ITER_ID
        or lock.get("status") != LOCK_STATUS
        or lock.get("one_shot") is not True
        or lock.get("effective_trial_count") != contract.effective_trial_count
        or lock.get("cost_views_bps") != contract.cost_views
        or lock.get("fold_count") != int(contract.validation["chronological_folds"]["count"])
        or lock.get("fold_sessions")
        != int(contract.validation["chronological_folds"]["oos_sessions"])
        or lock.get("runtime_contract_sha256") != contract.sha256
        or lock.get("runtime_contract") != contract.to_dict()
        or lock.get("historical_candidate_outcomes_read_at_lock") is not False
        or lock.get("order_authority") is not False
        or lock.get("broker_writes") is not False
        or lock.get("prelock_activity") != _prelock_activity(contract)
    ):
        raise ValueError("VIX R1 historical lock identity mismatch")
    expected_lengths = {
        "contracts": len(ITERATION_FILES),
        "external_inputs": len(EXTERNAL_INPUT_PATHS),
        "specs": len(CANDIDATE_IDS),
        "implementation": len(IMPLEMENTATION_PATHS),
    }
    for group, expected_length in expected_lengths.items():
        rows = lock.get(group)
        if not isinstance(rows, list) or len(rows) != expected_length:
            raise ValueError(f"VIX R1 lock group is missing or incomplete: {group}")
        for binding in rows:
            _verify_binding(base, binding)
    expected_group_paths = {
        "contracts": [(ITERATION_DIR / filename).as_posix() for filename in ITERATION_FILES],
        "external_inputs": [path.as_posix() for path in EXTERNAL_INPUT_PATHS.values()],
        "specs": [path.as_posix() for path in SPEC_PATHS.values()],
        "implementation": [path.as_posix() for path in IMPLEMENTATION_PATHS],
    }
    for group, expected_paths in expected_group_paths.items():
        if [str(row.get("path")) for row in lock[group]] != expected_paths:
            raise ValueError(f"VIX R1 lock path inventory changed: {group}")
    if [str(row.get("name")) for row in lock["external_inputs"]] != list(EXTERNAL_INPUT_PATHS):
        raise ValueError("VIX R1 external-input name inventory changed")
    locked_specs = {str(row["candidate_id"]): row for row in lock["specs"]}
    if [str(row.get("candidate_id")) for row in lock["specs"]] != list(CANDIDATE_IDS) or set(
        locked_specs
    ) != set(CANDIDATE_IDS):
        raise ValueError("VIX R1 locked spec inventory changed")
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"VIX R1 semantic spec changed after lock: {candidate_id}")
    validation = validate_iteration_dossier(ITER_ID, root=base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("VIX R1 dossier changed after lock: " + ", ".join(validation.blocked))
    return {
        "lock_path": LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "runtime_contract_sha256": contract.sha256,
        "dossier_checked_at": validation.checked_at.isoformat(),
    }


def _target_ledger_rows(targets: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate_id in CANDIDATE_IDS:
        frame = targets[candidate_id]
        for session, target in frame.iterrows():
            weights = {
                str(symbol): float(weight)
                for symbol, weight in target.items()
                if float(weight) > 1e-12
            }
            rows.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "candidate_id": candidate_id,
                    "execution_session": session.date().isoformat(),
                    "weights": weights,
                    "target_sha256": _canonical_hash(weights),
                    "order_authority": False,
                    "broker_writes": False,
                }
            )
    return rows


def _assemble_candidate_targets(
    r01_targets: pd.DataFrame,
    deterministic: dict[str, pd.DataFrame],
    ml_targets: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    groups = ({"V1R01": r01_targets}, deterministic, ml_targets)
    observed: dict[str, pd.DataFrame] = {}
    duplicates: list[str] = []
    for group in groups:
        for candidate_id, frame in group.items():
            if candidate_id in observed:
                duplicates.append(candidate_id)
            else:
                observed[candidate_id] = frame
    if duplicates:
        raise ValueError(
            "VIX R1 candidate target inventory contains duplicates: "
            + ", ".join(sorted(set(duplicates)))
        )
    missing = sorted(set(CANDIDATE_IDS) - set(observed))
    extra = sorted(set(observed) - set(CANDIDATE_IDS))
    if missing or extra:
        raise ValueError(
            f"VIX R1 candidate target inventory changed: missing={missing}, extra={extra}"
        )
    return {candidate_id: observed[candidate_id] for candidate_id in CANDIDATE_IDS}


def evaluate(root: Path) -> VixEvaluationResult:
    base = root.resolve()
    output = base / OUTPUT_DIR
    attempt = base / EVALUATION_ATTEMPT_PATH
    if output.exists():
        raise ValueError("VIX R1 evaluation output already exists; one-shot rerun is prohibited")
    if any((base / ITERATION_DIR).glob("evaluation-run.staging-*")):
        raise ValueError("VIX R1 stale staging directory exists")
    if attempt.exists() or attempt.is_symlink():
        raise ValueError("VIX R1 evaluation attempt already exists; rerun is prohibited")

    # No price return, target, or model operation may occur above this line.
    preflight = _preflight(base)
    evaluation_attempt = _reserve_evaluation_attempt(base, preflight)
    specs = load_and_validate_specs(base)
    contract = runtime_contract_from_specs(specs, root=base)
    full_panel = load_r24_price_panel(base)

    # The locked prior result is replicated before any new candidate is built.
    r01_targets, replication = build_and_verify_r01(base, full_panel)
    panel = _subset_panel(full_panel)
    packets = load_and_validate_packets(base)
    dataset = build_feature_label_dataset(panel, packets)
    folds = chronological_folds(panel.open.index, contract)
    first_oos_position = int(contract.validation["chronological_folds"]["first_oos_index"])
    oos_index = panel.open.index[first_oos_position:]
    if len(oos_index) != 4 * 408 or not oos_index.isin(dataset.index).all():
        raise ValueError("VIX R1 shared OOS decision index changed")
    deterministic, state_records = build_deterministic_targets(
        panel,
        dataset,
        contract,
        oos_index=oos_index,
    )
    ml_targets, model_records, prediction_records, common_index_records = build_ml_targets(
        panel,
        dataset,
        deterministic,
        folds,
        contract,
    )
    targets = _assemble_candidate_targets(r01_targets, deterministic, ml_targets)
    if tuple(targets) != CANDIDATE_IDS:
        raise AssertionError("VIX R1 candidate target order changed")
    if canonical_target_bytes(targets["V1F01"]) != canonical_target_bytes(targets["V1M01"]):
        raise ValueError("VIX R1 missing-modality identity failed before returns")

    candidates, return_streams, daily_rows, fold_results = _evaluate_candidates(
        panel, targets, contract, folds
    )
    matrix = common_oos_return_matrix(
        return_streams,
        candidate_ids=list(CANDIDATE_IDS),
    )
    if len(matrix) != 1631:
        raise ValueError("VIX R1 common terminal-free return matrix must contain 1,631 rows")
    scope_ids = _return_scope_ids(matrix.index, folds)
    dsr = {
        candidate_id: deflated_sharpe_ratio_vix_r1(
            matrix[candidate_id],
            trial_count=contract.effective_trial_count,
            hac_lag=int(contract.validation["dsr"]["hac_lag_sessions"]),
        )
        for candidate_id in CANDIDATE_IDS
    }
    _validate_dsr_evidence_identity(dsr, contract)
    pbo_matrix = matrix.loc[:, list(SELECTABLE_IDS)]
    panel_positions = panel.open.index.get_indexer(pbo_matrix.index)
    if (panel_positions <= 0).any():
        raise ValueError("VIX R1 PBO return intervals do not map to the frozen price panel")
    pbo_row_identities = [
        {
            "fold_id": scope_ids[position],
            "interval_start": panel.open.index[panel_position - 1],
            "interval_end": session,
        }
        for position, (session, panel_position) in enumerate(
            zip(pbo_matrix.index, panel_positions, strict=True)
        )
    ]
    pbo = probability_backtest_overfitting_vix_r1(
        pbo_matrix,
        return_row_identities=pbo_row_identities,
        candidate_ids=list(SELECTABLE_IDS),
        block_count=int(contract.validation["pbo"]["block_count"]),
        in_sample_block_count=int(contract.validation["pbo"]["in_sample_block_count"]),
    )
    start = pd.Timestamp(folds[0]["test_start"])
    end = panel.open.index[-1]
    benchmarks = _benchmark_family(panel, contract, start=start, end=end)
    candidate_gates, gate_payload = _candidate_and_family_gates(
        candidates,
        benchmarks,
        dsr,
        pbo,
        prediction_records,
        model_records,
        return_streams,
        replication,
        contract,
    )
    for candidate_id in CANDIDATE_IDS:
        candidates[candidate_id]["gates"] = candidate_gates[candidate_id]
        candidates[candidate_id]["folds"] = fold_results[candidate_id]

    research_pass = bool(gate_payload["research_pass"])
    ml_contribution_pass = bool(gate_payload["ml_contribution_pass"])
    ml_strategy_pass = bool(gate_payload["ml_strategy_pass"])
    strategy_group_pass, decision, interpretation = _strategy_group_outcome(
        research_pass=research_pass,
        ml_contribution_pass=ml_contribution_pass,
        ml_strategy_pass=ml_strategy_pass,
    )
    payload = {
        "schema_version": 1,
        "report_type": _report_type(),
        "iter_id": ITER_ID,
        "implementation_repair_only": ITER_ID == REPAIR_ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "workflow_pass": True,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "ml_contribution_pass": ml_contribution_pass,
        "ml_strategy_pass": ml_strategy_pass,
        "strategy_group_pass": strategy_group_pass,
        "paper_ready_pass": False,
        "paper_entry_ready": False,
        "paper_validated": False,
        "interpretation": interpretation,
        "data": {
            **panel.metadata,
            "cboe_snapshot_path": CBOE_SNAPSHOT_PATH.as_posix(),
            "cboe_snapshot_sha256": _sha256(base / CBOE_SNAPSHOT_PATH),
            "cboe_packet_path": CBOE_PACKET_PATH.as_posix(),
            "cboe_packet_sha256": _sha256(base / CBOE_PACKET_PATH),
            "historical_first_seen_claim": False,
            "paper_ready": False,
        },
        "oos_window": {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "target_session_count": len(oos_index),
            "return_interval_count": len(matrix),
            "folds": folds,
            "globally_exposed_not_pristine": True,
        },
        "replication": replication,
        "candidates": candidates,
        "benchmarks": benchmarks,
        "gates": gate_payload,
        "statistics": {
            "DSR": dsr,
            "PBO": pbo,
            "effective_trial_count": contract.effective_trial_count,
            "primary_cost_view": "primary_20bps",
            "cost_views": contract.cost_views,
            "terminal_free_return_matrix_sha256": hashlib.sha256(
                np.asarray(matrix.to_numpy(dtype=float), dtype="<f8").tobytes()
            ).hexdigest(),
            "terminal_free_return_index_sha256": _canonical_hash(
                [session.date().isoformat() for session in matrix.index]
            ),
            "runtime_contract_sha256": contract.sha256,
        },
        "model_provenance": {
            "trained_candidate_ids": list(TRAINED_IDS),
            "identity_only_candidate_ids": ["V1F01"],
            "shared_index_records": common_index_records,
            "shared_index_record_count": len(common_index_records),
            "model_record_sha256": _canonical_hash(model_records),
            "models_fit_from_scratch": True,
            "random_split_used": False,
            "placebo_fit_rows_only": True,
            "prompt": {
                "applicable": False,
                "prompt_hash": None,
                "reason": "quant_only_models",
            },
            "status": "historical_fold_local_diagnostic_not_runtime_model",
        },
        "integrity": {
            **preflight,
            "evaluation_attempt": evaluation_attempt,
            "contract_file_count": len(contract.file_bindings),
            "candidate_count": len(CANDIDATE_IDS),
            "V1F01_byte_identical_to_V1M01": True,
            "target_weights_sum_to_one": True,
            "terminal_liquidation_cost_applied": False,
            "order_authority": False,
            "broker_writes": False,
        },
        "limitations": [
            "Historical prices and the 2026 Cboe snapshot are globally exposed research data.",
            "The Cboe snapshot records actual 2026 fetched_at rather than historical first-seen timestamps.",
            "Four chronological folds are not an untouched holdout.",
            "This evaluation cannot authorize paper_auto or broker writes.",
        ],
    }
    manifest_by_id = {str(row["candidate_id"]): row for row in contract.manifest["candidates"]}
    trial_rows = [
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
            "terminal_free": True,
            "metrics": candidates[candidate_id]["cost_views"]["primary_20bps"]["terminal_free"],
            "gate_pass": candidate_gates[candidate_id]["pass"],
            "source_trial_id": manifest_by_id[candidate_id].get("source_trial_id"),
            "effective_trial_increment": manifest_by_id[candidate_id].get(
                "effective_trial_increment"
            ),
            "implementation_repair_only": manifest_by_id[candidate_id].get(
                "implementation_repair_only"
            ),
        }
        for candidate_id in CANDIDATE_IDS
    ]
    target_rows = _target_ledger_rows(targets)
    model_provenance = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        **payload["model_provenance"],
        "model_record_count": len(model_records),
        "prediction_record_count": len(prediction_records),
        "runtime_contract": contract.to_dict(),
        "runtime_contract_sha256": contract.sha256,
        "spec_semantic_sha256": {
            candidate_id: contract.candidate_specs[candidate_id]["semantic_sha256"]
            for candidate_id in TRAINED_IDS
        },
        "feature_sets": {
            candidate_id: list(contract.candidate_specs[candidate_id]["spec"]["model"]["features"])
            for candidate_id in TRAINED_IDS
        },
        "data_contract": contract.contracts["data-contract.json"],
        "data_contract_sha256": contract.file_bindings["data-contract.json"]["sha256"],
        "feature_contract_sha256": _sha256(base / ITERATION_DIR / "feature-contract.json"),
        "label_contract_sha256": _sha256(base / ITERATION_DIR / "label-contract.json"),
        "validation_contract_sha256": _sha256(base / ITERATION_DIR / "validation-contract.json"),
    }

    staging = base / ITERATION_DIR / f"evaluation-run.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        write_json(staging / "evaluation-report.json", payload)
        (staging / "evaluation-report.md").write_text(_render_report(payload), encoding="utf-8")
        write_json(staging / "benchmark-results.json", benchmarks)
        write_json(staging / "fold-results.json", fold_results)
        write_json(staging / "model-provenance.json", model_provenance)
        write_json(staging / "replication-diagnostic.json", replication)
        _write_jsonl(staging / "trial-ledger.jsonl", trial_rows)
        _write_jsonl(staging / "model-ledger.jsonl", model_records)
        _write_jsonl(staging / "prediction-ledger.jsonl", prediction_records)
        _write_jsonl(staging / "target-ledger.jsonl", target_rows)
        _write_jsonl(staging / "daily-return-ledger.jsonl", daily_rows)
        _write_jsonl(staging / "state-ledger.jsonl", state_records)
        next_iteration = (
            "Preserve this sealed result and build execution parity and readiness evidence without changing historical behavior."
            if decision == "continue"
            else "Preserve this sealed negative result and pivot only to a genuinely independent hypothesis in a new preregistered round."
        )
        (staging / "decision-record.md").write_text(
            f"# Decision Record: {ITER_ID}\n\n"
            "- Path: Nine-row VIX/VIX3M term-structure family with deterministic, matched ML, missing-modality, placebo, and sealed-replication controls.\n"
            f"- Decision: {decision}\n"
            f"- Reason: {interpretation}\n"
            f"- Next iteration suggestion: {next_iteration}\n"
            "- Status separation: workflow_pass is independent of research_pass, ml_contribution_pass, ml_strategy_pass, strategy_group_pass, and paper_ready_pass; no Paper order or broker write is authorized.\n",
            encoding="utf-8",
        )
        child_names = {
            "evaluation": "evaluation-report.json",
            "evaluation_markdown": "evaluation-report.md",
            "benchmark_results": "benchmark-results.json",
            "fold_results": "fold-results.json",
            "model_provenance": "model-provenance.json",
            "replication_diagnostic": "replication-diagnostic.json",
            "trial_ledger": "trial-ledger.jsonl",
            "model_ledger": "model-ledger.jsonl",
            "prediction_ledger": "prediction-ledger.jsonl",
            "target_ledger": "target-ledger.jsonl",
            "daily_return_ledger": "daily-return-ledger.jsonl",
            "state_ledger": "state-ledger.jsonl",
            "decision_record": "decision-record.md",
        }
        children = {
            name: _publication_binding(
                staging / filename,
                root=base,
                staging_dir=staging,
                destination_dir=output,
            )
            for name, filename in child_names.items()
        }
        receipt = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "generated_at": datetime.now(UTC).isoformat(),
            "evidence_publication_status": "complete",
            "one_shot": True,
            "decision": decision,
            "workflow_pass": payload["workflow_pass"],
            "research_pass": payload["research_pass"],
            "llm_contribution_pass": payload["llm_contribution_pass"],
            "ml_contribution_pass": payload["ml_contribution_pass"],
            "ml_strategy_pass": payload["ml_strategy_pass"],
            "strategy_group_pass": payload["strategy_group_pass"],
            "paper_ready_pass": payload["paper_ready_pass"],
            "paper_entry_ready": payload["paper_entry_ready"],
            "paper_validated": payload["paper_validated"],
            "evaluation_attempt": evaluation_attempt,
            "order_authority": False,
            "broker_writes": False,
            "children": children,
        }
        _validate_publication_status_identity(
            payload,
            receipt,
            evaluation_attempt=evaluation_attempt,
            root=base,
        )
        write_json(staging / "evaluation-receipt.json", receipt)
        final_validation = validate_iteration_dossier(
            ITER_ID,
            root=base,
            stage="final",
            staged_evaluation_dir=staging,
        )
        if not final_validation.ok:
            raise ValueError(
                "VIX R1 staged final dossier validation blocked: "
                + ", ".join(final_validation.blocked)
            )
        if output.exists():
            raise ValueError("VIX R1 evaluation destination appeared during publication")
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return VixEvaluationResult(
        evaluation_path=output / "evaluation-report.json",
        trial_ledger_path=output / "trial-ledger.jsonl",
        model_ledger_path=output / "model-ledger.jsonl",
        prediction_ledger_path=output / "prediction-ledger.jsonl",
        target_ledger_path=output / "target-ledger.jsonl",
        payload=payload,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "evaluate"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--iter-id", choices=tuple(ALLOWED_ITERATION_STEMS), default=BASE_ITER_ID)
    args = parser.parse_args()
    configure_iteration(args.iter_id)
    if args.action == "freeze":
        print(freeze(args.root))
    else:
        print(evaluate(args.root).evaluation_path)


if __name__ == "__main__":
    main()
