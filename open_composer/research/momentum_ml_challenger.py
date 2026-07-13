from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

FEATURES = (
    "qqq_roc_12_index_minus_1",
    "qqq_roc_36_index_minus_1",
    "qqq_roc_72_index_minus_1",
    "qqq_atr_ratio_72_index_minus_1",
    "qqq_realized_vol_26_index_minus_1",
    "tqqq_gap_1_index_minus_1",
)
LABEL = "tqqq_forward_13_bar_return_positive"
HORIZON_BARS = 13
PURGE_BARS = 72
EMBARGO_BARS = 72
SEARCH_CAP = 12
RANDOM_SEED = 77


@dataclass(frozen=True)
class MomentumMLEligibilityResult:
    status: str
    path: Path
    payload: dict[str, Any]


def write_momentum_product_status(
    readiness_path: Path,
    eligibility_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    readiness = _read_json(readiness_path)
    eligibility = _read_json(eligibility_path)
    inputs_valid = (
        readiness.get("report_type") == "momentum_shadow_readiness"
        and eligibility.get("report_type") == "momentum_ml_challenger_eligibility"
    )
    payload = {
        "report_type": "momentum_product_final_status",
        "product_capability_complete": inputs_valid,
        "shadow_status": readiness.get("status", "blocked"),
        "shadow_operational_interim": readiness.get("operational_interim", {}).get("passed", False),
        "shadow_observation_complete": readiness.get("status") == "shadow_observation_complete",
        "ml_eligible": eligibility.get("eligible", False),
        "ml_training_invoked": False,
        "research_pass": False,
        "paper_ready_pass": False,
        "paper_authorized": False,
        "broker_writes": False,
        "external_evidence_collection": "automatic_when_shadow_cycle_runs",
        "remaining_external_gates": [
            "fresh forward market sessions and intents",
            "current cross-source evidence",
            "observed Alpaca Paper fill TCA after explicit user authorization",
            "ML effective sample and regime coverage",
        ],
    }
    write_json(output_path, payload)
    return payload


def evaluate_momentum_ml_eligibility(
    forward_ledger_path: Path,
    output_path: Path,
    *,
    spec_path: Path | None = None,
    search_combinations: int = SEARCH_CAP,
    purge_bars: int = PURGE_BARS,
    embargo_bars: int = EMBARGO_BARS,
) -> MomentumMLEligibilityResult:
    if search_combinations < 1 or search_combinations > SEARCH_CAP:
        raise ValueError(f"ML challenger search combinations must be within 1..{SEARCH_CAP}")
    if (
        purge_bars < PURGE_BARS
        or embargo_bars < EMBARGO_BARS
        or purge_bars < HORIZON_BARS
        or embargo_bars < HORIZON_BARS
    ):
        raise ValueError("ML challenger requires purge_bars>=72 and embargo_bars>=72")
    rows = _read_jsonl(forward_ledger_path)
    provenance = _validate_ledger(rows, spec_path, forward_ledger_path)
    sessions = {
        pd.Timestamp(row["signal_timestamp"]).tz_convert("America/New_York").date().isoformat()
        for row in rows
    }
    intents = [row for row in rows if row.get("order_required_intent")]
    entries = [row for row in intents if float(row.get("target_weight", 0.0)) > 0]
    exits = [row for row in intents if float(row.get("target_weight", 0.0)) == 0]
    regimes = {str(row["regime"]) for row in rows if row.get("regime")}
    effective_sample_size = _effective_sample_size(rows)
    gates = {
        "forward_decisions": {"actual": len(rows), "threshold": 800, "passed": len(rows) >= 800},
        "forward_sessions": {
            "actual": len(sessions),
            "threshold": 120,
            "passed": len(sessions) >= 120,
        },
        "intent_events": {
            "actual": len(intents),
            "threshold": 100,
            "passed": len(intents) >= 100,
        },
        "entry_events": {
            "actual": len(entries),
            "threshold": 40,
            "passed": len(entries) >= 40,
        },
        "exit_events": {
            "actual": len(exits),
            "threshold": 40,
            "passed": len(exits) >= 40,
        },
        "regime_coverage": {
            "actual": len(regimes),
            "threshold": 3,
            "passed": len(regimes) >= 3,
        },
        "effective_sample_size": {
            "actual": round(effective_sample_size, 4),
            "threshold": 200,
            "passed": effective_sample_size >= 200,
        },
    }
    eligible = all(gate["passed"] for gate in gates.values())
    contract = _contract(
        search_combinations=search_combinations,
        purge_bars=purge_bars,
        embargo_bars=embargo_bars,
    )
    payload = {
        "report_type": "momentum_ml_challenger_eligibility",
        "status": "eligible" if eligible else "blocked",
        "eligible": eligible,
        "training_invoked": False,
        "model_factory_invoked": False,
        "role": "advisory_only",
        "execution_target_control": False,
        "contract": contract,
        "ledger_provenance": provenance,
        "gates": gates,
        "failed_gates": [name for name, gate in gates.items() if not gate["passed"]],
        "paper_order_authorization": False,
        "paper_ready_pass": False,
    }
    write_json(output_path, payload)
    return MomentumMLEligibilityResult(status=payload["status"], path=output_path, payload=payload)


def advisory_prediction(
    *,
    baseline_target: float,
    features: dict[str, float],
    predictor: Callable[[dict[str, float]], float] | None,
    threshold: float = 0.6,
) -> dict[str, Any]:
    execution_target = float(baseline_target)
    try:
        if predictor is None:
            raise RuntimeError("model unavailable")
        missing = [name for name in FEATURES if name not in features]
        if missing:
            raise ValueError(f"missing features: {','.join(missing)}")
        values = [float(features[name]) for name in FEATURES]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("non-finite feature")
        probability = float(predictor(features))
        if not math.isfinite(probability):
            raise ValueError("non-finite prediction")
        advisory_target = baseline_target if probability >= threshold else 0.0
        return {
            "status": "advisory_available",
            "probability": probability,
            "advisory_target": advisory_target,
            "execution_target": execution_target,
            "baseline_identical_execution": True,
        }
    except Exception as exc:
        return {
            "status": "baseline_fallback",
            "reason": str(exc),
            "probability": None,
            "advisory_target": execution_target,
            "execution_target": execution_target,
            "baseline_identical_execution": True,
        }


def _contract(*, search_combinations: int, purge_bars: int, embargo_bars: int) -> dict[str, Any]:
    base = {
        "feature_alignment": "index_minus_1",
        "features": list(FEATURES),
        "label": LABEL,
        "horizon_bars": HORIZON_BARS,
        "purge_bars": purge_bars,
        "embargo_bars": embargo_bars,
        "models": ["frozen_rule", "regularized_linear", "lightgbm_challenger"],
        "search_combinations": search_combinations,
        "search_cap": SEARCH_CAP,
        "random_seed": RANDOM_SEED,
        "evaluation": {
            "prediction_scope": "stitched_oos_only",
            "required_fold_wins": "at_least_3_of_4_vs_rule_and_linear",
            "metrics": ["net_return_after_cost", "sharpe", "information_ratio", "max_drawdown"],
        },
    }
    encoded = json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**base, "schema_sha256": hashlib.sha256(encoded).hexdigest()}


def _effective_sample_size(rows: list[dict[str, Any]]) -> float:
    if len(rows) < 3:
        return float(len(rows))
    values = np.asarray([float(row.get("target_weight", 0.0)) for row in rows], dtype=float)
    variance = float(values.var())
    if variance <= 1e-12:
        return 1.0
    centered = values - values.mean()
    autocorrelations = []
    max_lag = min(72, len(values) - 1)
    for lag in range(1, max_lag + 1):
        correlation = float(
            np.dot(centered[:-lag], centered[lag:]) / ((len(values) - lag) * variance)
        )
        if correlation <= 0:
            break
        autocorrelations.append(correlation)
    denominator = 1.0 + 2.0 * sum(autocorrelations)
    return max(1.0, min(float(len(values)), float(len(values)) / denominator))


def _validate_ledger(
    rows: list[dict[str, Any]], spec_path: Path | None, ledger_path: Path
) -> dict[str, Any]:
    if spec_path is None:
        if rows:
            raise ValueError("non-empty ML eligibility ledger requires a frozen StrategySpec")
        return {"valid": True, "ledger_sha256": _sha256_path(ledger_path), "row_count": 0}
    spec = load_strategy_spec(spec_path)
    expected_hash = strategy_content_hash(spec)
    design = spec.notes.research_design
    epoch = pd.Timestamp(design["forward_epoch_utc"])
    keys: set[tuple[str, str, str]] = set()
    previous_signal: pd.Timestamp | None = None
    for row in rows:
        required = {
            "evidence_class",
            "spec_hash",
            "observed_at",
            "signal_timestamp",
            "effective_timestamp",
            "target_weight",
            "order_required_intent",
            "regime",
            "paper_order_authorization",
            "broker_writes",
        }
        if not required.issubset(row):
            raise ValueError("forward ledger row is missing provenance fields")
        signal_at = pd.Timestamp(row["signal_timestamp"])
        effective_at = pd.Timestamp(row["effective_timestamp"])
        observed_at = pd.Timestamp(row["observed_at"])
        key = (row["spec_hash"], signal_at.isoformat(), effective_at.isoformat())
        if row["evidence_class"] != "forward_observation" or row["spec_hash"] != expected_hash:
            raise ValueError("forward ledger source identity mismatch")
        if signal_at <= epoch or not signal_at < effective_at <= observed_at:
            raise ValueError("forward ledger timestamp contract violation")
        if row["paper_order_authorization"] is not False or row["broker_writes"] is not False:
            raise ValueError("forward ledger contains broker-authorized evidence")
        if key in keys or (previous_signal is not None and signal_at < previous_signal):
            raise ValueError("forward ledger is duplicate or non-monotonic")
        keys.add(key)
        previous_signal = signal_at
    return {
        "valid": True,
        "spec_hash": expected_hash,
        "forward_epoch_utc": epoch.isoformat(),
        "ledger_sha256": _sha256_path(ledger_path),
        "row_count": len(rows),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_path(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
