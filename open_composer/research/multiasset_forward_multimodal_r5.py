from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import os
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from importlib.util import resolve_name
from itertools import combinations
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from open_composer.adapters.data.alpaca import AlpacaDataError
from open_composer.adapters.data.alpaca_snapshot import verify_alpaca_contract_snapshot
from open_composer.config import ensure_dir
from open_composer.harness.policy import (
    artifact_path,
    blocking_rules_for_domains,
    check_artifact,
    detect_risk_domains,
    required_artifacts_for_domains,
    required_skills_for_domains,
)
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.models.strategy_spec import MLModelConfig, StrategySpec
from open_composer.research.evidence_custody import (
    ExternalCustodyRecord,
    verify_external_custody_record,
    write_external_custody_bundle,
)
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.strategy_versions import strategy_content_hash
from open_composer.yaml_utils import safe_load_yaml

ITER_ID = "mom_multiasset_forward_multimodal_r5"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
DATA_DIR = Path("data/research/alpaca_etf_structural_r9")
EVALUATION_ANCHOR_CONTRACT = "multiasset_forward_multimodal_r5_evaluation_anchor_v1"
R5_HARNESS_RECONCILIATION_CONTRACT = "multiasset_forward_multimodal_r5_harness_reconciliation_v1"
R5_CUSTODY_NAMESPACE = "mom_multiasset_forward_multimodal_r5"
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_multiasset_forward_mm_r5_{suffix}.yaml")
    for candidate_id, suffix in {
        "R5D01": "d01",
        "R5D02": "d02",
        "R5M01": "m01",
        "R5M02": "m02",
        "R5L01": "l01",
        "R5C01": "c01",
        "R5F01": "f01",
        "R5P01": "p01",
    }.items()
}
R5_CANDIDATE_ROLE_CONTRACT = {
    "R5D01": {
        "candidate_id": "R5D01",
        "path": "deterministic",
        "role": "deterministic_core_baseline",
        "method": "12_1_top3_equal_weight",
        "ablation": "quant_only_deterministic",
        "spec_path": SPEC_PATHS["R5D01"].as_posix(),
        "fallback": "BIL",
        "data_contract": "daily_sip_v1",
        "feature_contract": "deterministic_12_1_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "matched_family_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": True,
    },
    "R5D02": {
        "candidate_id": "R5D02",
        "path": "deterministic",
        "role": "deterministic_diversification_control",
        "method": "6_1_trend_top3_equal_weight",
        "ablation": "quant_only_alternative",
        "spec_path": SPEC_PATHS["R5D02"].as_posix(),
        "fallback": "R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "deterministic_6_1_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "matched_family_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": True,
    },
    "R5M01": {
        "candidate_id": "R5M01",
        "path": "trained_ml",
        "role": "trained_return_ranker",
        "method": "fold_local_lightgbm_core_features",
        "ablation": "quant_only_trained",
        "spec_path": SPEC_PATHS["R5M01"].as_posix(),
        "fallback": "R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "core_quant_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "matched_family_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": True,
    },
    "R5M02": {
        "candidate_id": "R5M02",
        "path": "trained_ml",
        "role": "trained_risk_rejection_gate",
        "method": "fold_local_lightgbm_path_survival",
        "ablation": "risk_gate",
        "spec_path": SPEC_PATHS["R5M02"].as_posix(),
        "fallback": "R5M01_then_R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "core_quant_v1",
        "label_contract": "path_survival_v1",
        "validation_contract": "matched_family_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": True,
    },
    "R5L01": {
        "candidate_id": "R5L01",
        "path": "llm_formula",
        "role": "llm_derived_formula_only",
        "method": "deterministic_equal_formula_composite",
        "ablation": "formula_only",
        "spec_path": SPEC_PATHS["R5L01"].as_posix(),
        "fallback": "R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "llm_formula_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "matched_family_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": True,
    },
    "R5C01": {
        "candidate_id": "R5C01",
        "path": "combined",
        "role": "combined_ml_and_llm_formula",
        "method": "fold_local_lightgbm_core_plus_llm_formulas",
        "ablation": "quant_plus_formula",
        "spec_path": SPEC_PATHS["R5C01"].as_posix(),
        "fallback": "R5M01_then_R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "core_plus_llm_formula_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "matched_family_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": True,
    },
    "R5F01": {
        "candidate_id": "R5F01",
        "path": "missing_modality",
        "role": "missing_formula_ablation_selection_prohibited",
        "method": "exact_M01_without_formula_inputs",
        "ablation": "missing_formula",
        "spec_path": SPEC_PATHS["R5F01"].as_posix(),
        "fallback": "R5M01_then_R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "core_quant_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "exact_fallback_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": False,
    },
    "R5P01": {
        "candidate_id": "R5P01",
        "path": "placebo",
        "role": "shuffled_formula_placebo_selection_prohibited",
        "method": "C01_with_symbol_formula_permutation_seed_4199",
        "ablation": "shuffled_formula_placebo",
        "spec_path": SPEC_PATHS["R5P01"].as_posix(),
        "fallback": "R5M01_then_R5D01",
        "data_contract": "daily_sip_v1",
        "feature_contract": "llm_formula_placebo_v1",
        "label_contract": "monthly_open_return_v1",
        "validation_contract": "placebo_v1",
        "cost_contract": "opg_10_20_35_v1",
        "benchmark_contract": "complete_etf_family_v1",
        "promotion_eligible": False,
    },
}
RANKABLE_SYMBOLS = (
    "GLD",
    "IEF",
    "QQQ",
    "SPY",
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
)
RESERVE_SYMBOL = "BIL"
CORE_FEATURES = (
    "mom_21",
    "mom_63",
    "mom_126_skip21",
    "mom_252_skip21",
    "trend_gap_126",
    "vol_21",
    "drawdown_63",
)
FORMULA_FEATURES = (
    "llm_momentum_quality",
    "llm_volume_confirmed_trend",
    "llm_rebound_trap",
    "llm_crowding_risk",
)
R5_DECLARED_FEATURE_CONTRACT = {
    "R5D01": ("mom_252_skip21",),
    "R5D02": ("mom_126_skip21", "trend_gap_252"),
    "R5M01": CORE_FEATURES,
    "R5M02": CORE_FEATURES,
    "R5L01": FORMULA_FEATURES,
    "R5C01": (*CORE_FEATURES, *FORMULA_FEATURES),
    "R5F01": CORE_FEATURES,
    "R5P01": (*CORE_FEATURES, *FORMULA_FEATURES),
}
R5_RUNTIME_PREDICTOR_CONTRACT = {
    "R5M01": CORE_FEATURES,
    "R5M02": CORE_FEATURES,
    "R5C01": (*CORE_FEATURES, *FORMULA_FEATURES),
    "R5P01": (*CORE_FEATURES, *(f"placebo_{name}" for name in FORMULA_FEATURES)),
}
R5_MODEL_LABEL_CONTRACT = {
    "R5M01": "forward_return_21",
    "R5M02": "path_survival_label",
    "R5C01": "forward_return_21",
    "R5P01": "forward_return_21",
}
R5_PROMOTION_ELIGIBLE_CANDIDATE_IDS = frozenset(
    candidate_id
    for candidate_id, contract in R5_CANDIDATE_ROLE_CONTRACT.items()
    if contract["promotion_eligible"] is True
)
R5_SELECTION_PROHIBITED_CANDIDATE_IDS = frozenset(
    set(SPEC_PATHS) - R5_PROMOTION_ELIGIBLE_CANDIDATE_IDS
)
R5_FORBIDDEN_PREDICTOR_COLUMNS = frozenset(
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
R5_FORMULA_SOURCE_CONTRACT = {
    "llm_momentum_quality": {
        "source_factor_name": "ai_momentum_quality",
        "source_formula": "mom_126_skip21_rank + high_252_rank - vol_63_rank",
        "spec_expression": "mom_126_skip21 + high_gap_252 - vol_63",
        "components": ["mom_126_skip21", "high_gap_252", "vol_63"],
        "coefficients": [1.0, 1.0, -1.0],
    },
    "llm_volume_confirmed_trend": {
        "source_factor_name": "ai_volume_confirmed_trend",
        "source_formula": "mom_63_rank + volume_surprise_21_rank + ma_gap_50_rank",
        "spec_expression": "mom_63 + volume_surprise_21 + ma_gap_50",
        "components": ["mom_63", "volume_surprise_21", "ma_gap_50"],
        "coefficients": [1.0, 1.0, 1.0],
    },
    "llm_rebound_trap": {
        "source_factor_name": "ai_rebound_trap",
        "source_formula": "mom_21_rank - mom_126_skip21_rank - drawdown_63_rank",
        "spec_expression": "mom_21 - mom_126_skip21 - drawdown_63",
        "components": ["mom_21", "mom_126_skip21", "drawdown_63"],
        "coefficients": [1.0, -1.0, -1.0],
    },
    "llm_crowding_risk": {
        "source_factor_name": "ai_crowding_risk",
        "source_formula": (
            "mom_21_rank + volume_surprise_5_rank + high_63_rank - mom_252_skip21_rank"
        ),
        "spec_expression": ("mom_21 + volume_surprise_5 + high_gap_63 - mom_252_skip21"),
        "components": ["mom_21", "volume_surprise_5", "high_gap_63", "mom_252_skip21"],
        "coefficients": [1.0, 1.0, 1.0, -1.0],
    },
}
R5_RAW_FACTOR_EXPRESSION_CONTRACT = {
    "mom_21": "close / lag(close, 21) - 1",
    "mom_63": "close / lag(close, 63) - 1",
    "mom_126_skip21": "lag(close, 21) / lag(close, 126) - 1",
    "mom_252_skip21": "lag(close, 21) / lag(close, 252) - 1",
    "trend_gap_126": "close / sma(close, 126) - 1",
    "trend_gap_252": "close / sma(close, 252) - 1",
    "vol_21": "stddev(close / lag(close, 1) - 1, 21)",
    "vol_63": "stddev(close / lag(close, 1) - 1, 63)",
    "drawdown_63": "close / highest(close, 63) - 1",
    "high_gap_63": "close / highest(close, 63) - 1",
    "high_gap_252": "close / highest(close, 252) - 1",
    "volume_surprise_5": "volume / sma(volume, 5) - 1",
    "volume_surprise_21": "volume / sma(volume, 21) - 1",
    "ma_gap_50": "close / sma(close, 50) - 1",
}
R5_FORMULA_RAW_FACTOR_NAMES = tuple(
    name for name in R5_RAW_FACTOR_EXPRESSION_CONTRACT if name != "trend_gap_252"
)
R5_SPEC_FACTOR_EXPRESSION_CONTRACT = {
    "R5D01": {"momentum_12_1": R5_RAW_FACTOR_EXPRESSION_CONTRACT["mom_252_skip21"]},
    "R5D02": {
        "momentum_6_1": R5_RAW_FACTOR_EXPRESSION_CONTRACT["mom_126_skip21"],
        "trend_252": R5_RAW_FACTOR_EXPRESSION_CONTRACT["trend_gap_252"],
    },
    "R5M01": {name: R5_RAW_FACTOR_EXPRESSION_CONTRACT[name] for name in CORE_FEATURES},
    "R5M02": {name: R5_RAW_FACTOR_EXPRESSION_CONTRACT[name] for name in CORE_FEATURES},
    "R5L01": {
        name: R5_RAW_FACTOR_EXPRESSION_CONTRACT[name] for name in R5_FORMULA_RAW_FACTOR_NAMES
    },
    "R5C01": {
        name: R5_RAW_FACTOR_EXPRESSION_CONTRACT[name] for name in R5_FORMULA_RAW_FACTOR_NAMES
    },
    "R5F01": {name: R5_RAW_FACTOR_EXPRESSION_CONTRACT[name] for name in CORE_FEATURES},
    "R5P01": {
        name: R5_RAW_FACTOR_EXPRESSION_CONTRACT[name] for name in R5_FORMULA_RAW_FACTOR_NAMES
    },
}
R5_CORE_FEATURE_DESCRIPTION_CONTRACT = {
    "mom_21": "close_t / close_t-21 - 1",
    "mom_63": "close_t / close_t-63 - 1",
    "mom_126_skip21": "close_t-21 / close_t-126 - 1",
    "mom_252_skip21": "close_t-21 / close_t-252 - 1",
    "trend_gap_126": "close_t / sma_126_t - 1",
    "vol_21": "population_std(daily_return,21)",
    "drawdown_63": "close_t / rolling_high_63_t - 1",
}
R5_LLM_FEATURE_DESCRIPTION_CONTRACT = {
    "llm_momentum_quality": ("rank(mom_126_skip21) + rank(high_gap_252) - rank(vol_63)"),
    "llm_volume_confirmed_trend": ("rank(mom_63) + rank(volume_surprise_21) + rank(ma_gap_50)"),
    "llm_rebound_trap": ("rank(mom_21) - rank(mom_126_skip21) - rank(drawdown_63)"),
    "llm_crowding_risk": (
        "rank(mom_21) + rank(volume_surprise_5) + rank(high_gap_63) - rank(mom_252_skip21)"
    ),
}
TOP_N = 3
HORIZON_SESSIONS = 21
EMBARGO_SESSIONS = 21
TRAINING_WINDOW_SESSIONS = 756
PRIMARY_COST_BPS = 10.0
STRESS_COST_BPS = 20.0
SEVERE_COST_BPS = 35.0
PLACEBO_SEED = 4199
PAIRED_RETURN_RANKER_SEED = 4101
R5_MODEL_SPEC_CONTRACT = {
    "R5M01": {
        "kind": "lightgbm_regressor",
        "label": {
            "type": "forward_return",
            "horizon_bars": HORIZON_SESSIONS,
            "threshold_pct": None,
            "max_drawdown_pct": None,
            "min_terminal_return_pct": None,
        },
        "features": list(R5_DECLARED_FEATURE_CONTRACT["R5M01"]),
        "training": {
            "window_bars": TRAINING_WINDOW_SESSIONS,
            "retrain_every_bars": 21,
            "test_window_bars": 63,
            "embargo_bars": EMBARGO_SESSIONS,
            "seed": PAIRED_RETURN_RANKER_SEED,
        },
        "selection": {"method": "top_quantile", "quantile": 0.22, "threshold": None},
        "hyperparameters": {
            "n_estimators": 120,
            "num_leaves": 7,
            "learning_rate": 0.03,
            "min_child_samples": 40,
            "subsample": 0.8,
            "subsample_freq": 1,
            "colsample_bytree": 0.8,
            "reg_lambda": 2.0,
            "verbosity": -1,
            "n_jobs": 1,
        },
        "baseline": "linear_composite",
    },
    "R5M02": {
        "kind": "lightgbm_classifier",
        "label": {
            "type": "path_survival",
            "horizon_bars": HORIZON_SESSIONS,
            "threshold_pct": None,
            "max_drawdown_pct": 8.0,
            "min_terminal_return_pct": 0.0,
        },
        "features": list(R5_DECLARED_FEATURE_CONTRACT["R5M02"]),
        "training": {
            "window_bars": TRAINING_WINDOW_SESSIONS,
            "retrain_every_bars": 21,
            "test_window_bars": 63,
            "embargo_bars": EMBARGO_SESSIONS,
            "seed": 4102,
        },
        "selection": {"method": "threshold", "quantile": None, "threshold": 0.55},
        "hyperparameters": {
            "n_estimators": 120,
            "num_leaves": 7,
            "learning_rate": 0.03,
            "min_child_samples": 40,
            "subsample": 0.8,
            "subsample_freq": 1,
            "colsample_bytree": 0.8,
            "reg_lambda": 2.0,
            "verbosity": -1,
            "n_jobs": 1,
        },
        "baseline": "linear_composite",
    },
}
R5_MODEL_SPEC_CONTRACT["R5C01"] = {
    **R5_MODEL_SPEC_CONTRACT["R5M01"],
    "features": list(R5_DECLARED_FEATURE_CONTRACT["R5C01"]),
}
R5_MODEL_SPEC_CONTRACT["R5F01"] = {
    **R5_MODEL_SPEC_CONTRACT["R5M01"],
    "features": list(R5_DECLARED_FEATURE_CONTRACT["R5F01"]),
}
R5_MODEL_SPEC_CONTRACT["R5P01"] = {
    **R5_MODEL_SPEC_CONTRACT["R5M01"],
    "features": list(R5_DECLARED_FEATURE_CONTRACT["R5P01"]),
}
R5_MODEL_SPEC_CONTRACT = {
    candidate_id: MLModelConfig.model_validate(payload).model_dump(mode="json")
    for candidate_id, payload in R5_MODEL_SPEC_CONTRACT.items()
}
R5_RUNTIME_CONTRACT_FILENAMES = {
    "benchmark": "benchmark-contract.json",
    "candidate_manifest": "candidate-manifest.json",
    "cost": "cost-contract.json",
    "cumulative_trial": "cumulative-trial-contract.json",
    "feature": "feature-contract.json",
    "holdout": "holdout-contract.json",
    "label": "label-contract.json",
    "validation": "validation-contract.json",
}
R5_LOCK_ITERATION_FILENAMES = (
    "benchmark-contract.json",
    "candidate-manifest.json",
    "cost-contract.json",
    "cumulative-trial-contract.json",
    "data-contract.json",
    "data-feasibility.json",
    "decision-record.md",
    "evaluation-gates.json",
    "external-brief.json",
    "external-brief.md",
    "feature-contract.json",
    "holdout-contract.json",
    "hypotheses.md",
    "knowledge-assessment.json",
    "knowledge-baseline.json",
    "knowledge-context.json",
    "knowledge-scout-queries.json",
    "knowledge-scout.json",
    "label-contract.json",
    "modality-role-matrix.json",
    "model-reuse-decision.json",
    "search-space.json",
    "search-space.md",
    "validation-contract.json",
)
R5_EVALUATION_FILENAMES = {
    "feature_ledger": "feature-ledger.jsonl",
    "prediction_ledger": "prediction-ledger.jsonl",
    "daily_return_ledger": "daily-return-ledger.jsonl",
    "target_ledger": "target-ledger.jsonl",
    "event_ledger": "cost-event-ledger.jsonl",
    "benchmark_ledger": "benchmark-ledger.jsonl",
    "model_ledger": "model-ledger.jsonl",
    "trial_ledger": "trial-ledger.jsonl",
    "cost_reconciliation": "cost-reconciliation.json",
    "model_provenance": "model-provenance.json",
    "evaluation": "evaluation-report.json",
    "evaluation_markdown": "evaluation-report.md",
    "decision_record": "decision-record.md",
    "receipt": "evaluation-receipt.json",
    "evaluation_anchor": "evaluation-anchor.json",
}
R5_HARNESS_CONFIG_PATHS = {
    "risk_domains": Path("harness/risk_domains.yaml"),
    "artifact_contracts": Path("harness/artifact_contracts.yaml"),
    "skill_manifest": Path("harness/skill_manifest.yaml"),
}
FORMULA_PARAM_KEYS = (
    "transform",
    "rank_method",
    "full_sample_fit",
    "components",
    "coefficients",
    "population",
    "rank_ascending",
    "tie_break",
    "apply_at",
)


@dataclass(frozen=True)
class PanelData:
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    manifest: dict[str, Any]


@dataclass(frozen=True)
class FeatureBundle:
    raw: dict[str, pd.DataFrame]
    ranked: dict[str, pd.DataFrame]
    formulas: dict[str, pd.DataFrame]


@dataclass(frozen=True)
class ExactSimulationResult:
    daily: pd.DataFrame
    events: list[dict[str, Any]]
    metrics: dict[str, Any]


@dataclass(frozen=True)
class R5EvaluationResult:
    evaluation_path: Path
    evaluation_markdown_path: Path
    receipt_path: Path
    evaluation_anchor_path: Path
    evaluation_anchor_sha256: str
    operator_evaluation_anchor_sha256: str
    custody_receipt_path: Path
    custody_receipt_sha256: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class R5FreezeResult:
    preregistration_lock_path: Path
    runner_lock_path: Path
    lock_anchor_path: Path
    lock_anchor_sha256: str
    custody_receipt_path: Path
    custody_receipt_sha256: str
    payload: dict[str, Any]


def _validate_r5_spec_execution_contract(
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R5 spec set must contain exactly the eight frozen candidates")

    expected_universe = {RESERVE_SYMBOL, *RANKABLE_SYMBOLS}
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="json")
        portfolio = spec.portfolio
        checks = {
            "candidate_id": notes.get("candidate_id") == candidate_id,
            "daily": spec.timeframe == "daily",
            "long_only": spec.position_direction == "long_only",
            "universe": set(spec.universe) == expected_universe,
            "portfolio_mode": portfolio.mode == "cross_sectional_momentum",
            "execution_profile": (
                portfolio.cross_sectional_execution_profile == "monthly_equal_weight_bil_reserve"
            ),
            "rebalance_schedule": portfolio.rebalance_schedule == "calendar_month_end",
            "weighting": portfolio.weighting == "equal_weight",
            "reserve_symbol": portfolio.reserve_symbol == RESERVE_SYMBOL,
            "reserve_cap_exemption": portfolio.reserve_exempt_from_max_symbol_weight is True,
            "position_weight_enforcement": portfolio.position_weight_enforcement == "entry_only",
            "top_n": portfolio.max_symbols_per_day == TOP_N,
            "gross_exposure": portfolio.gross_exposure_limit == 1.0,
            "portfolio_weight_cap": portfolio.max_symbol_weight == 0.34,
            "risk_weight_cap": spec.risk.max_position_weight == 0.34,
            "manual_only": spec.execution.mode == "manual_signal",
            "broker_none": spec.execution.broker == "none",
            "decision_close": spec.execution.signal_on == "bar_close",
            "next_open": spec.execution.fill_assumption == "next_bar_open",
            "commission": spec.costs.commission_pct == 0.0,
            "primary_cost": spec.costs.slippage_bps == PRIMARY_COST_BPS,
            "impact_model": spec.costs.impact_model == "linear",
            "impact_eta": spec.costs.impact_eta == 0.0,
            "impact_gamma": spec.costs.impact_gamma == 0.0,
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise ValueError(
                f"R5 StrategySpec execution contract mismatch for {candidate_id}: {failed}"
            )
        expected_factor_expressions = R5_SPEC_FACTOR_EXPRESSION_CONTRACT[candidate_id]
        for factor_name, expected_expression in expected_factor_expressions.items():
            factor = spec.factors.get(factor_name)
            if (
                factor is None
                or factor.source != "expression"
                or factor.expression != expected_expression
            ):
                raise ValueError(
                    f"R5 factor expression contract mismatch for {candidate_id}:{factor_name}"
                )
    formula_specs = {candidate_id: specs[candidate_id] for candidate_id in ("R5L01", "R5C01")}
    for name in FORMULA_FEATURES:
        reference = {
            key: formula_specs["R5C01"].factors[name].params.get(key) for key in FORMULA_PARAM_KEYS
        }
        source_contract = R5_FORMULA_SOURCE_CONTRACT[name]
        if (
            reference["components"] != source_contract["components"]
            or reference["coefficients"] != source_contract["coefficients"]
        ):
            raise ValueError(f"R5 formula differs from locked R2 source mapping: {name}")
        for candidate_id, spec in formula_specs.items():
            if spec.factors[name].expression != source_contract["spec_expression"]:
                raise ValueError(
                    f"R5 formula expression contract mismatch for {candidate_id}:{name}"
                )
            actual = {key: spec.factors[name].params.get(key) for key in FORMULA_PARAM_KEYS}
            if actual != reference:
                raise ValueError(f"R5 formula contract mismatch for {candidate_id}:{name}")
        placebo = specs["R5P01"].factors[name].params
        if specs["R5P01"].factors[name].expression != source_contract["spec_expression"]:
            raise ValueError(f"R5 formula expression contract mismatch for R5P01:{name}")
        actual_placebo = {key: placebo.get(key) for key in FORMULA_PARAM_KEYS}
        if actual_placebo != reference:
            raise ValueError(f"R5 placebo formula contract mismatch for {name}")
        if (
            placebo.get("placebo_operation") != "per_decision_session_symbol_permutation"
            or placebo.get("placebo_mapping") != "same_permutation_for_all_formula_columns"
            or placebo.get("placebo_seed") != PLACEBO_SEED
        ):
            raise ValueError(f"R5 placebo metadata mismatch for {name}")

    paired_models = {
        candidate_id: specs[candidate_id].model for candidate_id in ("R5M01", "R5C01", "R5P01")
    }
    if any(model is None for model in paired_models.values()):
        raise ValueError("R5 paired return-ranker model contract is missing")
    normalized_models = {}
    for candidate_id, model in paired_models.items():
        payload = model.model_dump(mode="json")
        payload.pop("features", None)
        normalized_models[candidate_id] = payload
        if model.training.seed != PAIRED_RETURN_RANKER_SEED:
            raise ValueError(
                f"R5 paired return-ranker seed mismatch for {candidate_id}: "
                f"expected {PAIRED_RETURN_RANKER_SEED}"
            )
    if len({_canonical_json_bytes(payload) for payload in normalized_models.values()}) != 1:
        raise ValueError(
            "R5M01, R5C01 and R5P01 must use identical model contracts except features"
        )
    m01_model = specs["R5M01"].model
    f01_model = specs["R5F01"].model
    if (
        m01_model is None
        or f01_model is None
        or m01_model.model_dump(mode="json") != f01_model.model_dump(mode="json")
    ):
        raise ValueError("R5F01 must declare the exact R5M01 model contract")
    m02_model = specs["R5M02"].model
    if (
        m02_model is None
        or m02_model.selection.method != "threshold"
        or m02_model.selection.threshold != 0.55
    ):
        raise ValueError("R5M02 must use the frozen 0.55 survival threshold")
    for candidate_id, spec in specs.items():
        expected_model = R5_MODEL_SPEC_CONTRACT.get(candidate_id)
        actual_model = spec.model.model_dump(mode="json") if spec.model is not None else None
        if actual_model != expected_model:
            raise ValueError(f"R5 immutable model contract mismatch for {candidate_id}")
        expected_features = R5_DECLARED_FEATURE_CONTRACT[candidate_id]
        if spec.model is not None and tuple(spec.model.features) != expected_features:
            raise ValueError(f"R5 immutable feature contract mismatch for {candidate_id}")
    return {
        "rebalance_schedule": "calendar_month_end",
        "weighting": "equal_weight",
        "reserve_symbol": RESERVE_SYMBOL,
        "top_n": TOP_N,
        "paired_return_ranker_seed": PAIRED_RETURN_RANKER_SEED,
        "formula_spec_candidate_id": "R5C01",
        "placebo_spec_candidate_id": "R5P01",
    }


def build_point_in_time_features(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    *,
    rankable_symbols: tuple[str, ...] = RANKABLE_SYMBOLS,
    formula_spec: StrategySpec | None = None,
) -> FeatureBundle:
    prices = _strict_numeric_panel(close, "close", positive=True)
    volumes = _strict_numeric_panel(volume, "volume", positive=False).reindex_like(prices)
    if volumes.isna().any().any() or (volumes < 0).any().any():
        raise ValueError("volume must align with closes and remain nonnegative")
    missing = sorted(set(rankable_symbols) - set(prices.columns))
    if missing:
        raise ValueError("rankable symbols missing from feature panel: " + ", ".join(missing))

    daily = prices.pct_change(fill_method=None)
    raw = {
        "mom_21": prices.div(prices.shift(21)).sub(1.0),
        "mom_63": prices.div(prices.shift(63)).sub(1.0),
        "mom_126_skip21": prices.shift(21).div(prices.shift(126)).sub(1.0),
        "mom_252_skip21": prices.shift(21).div(prices.shift(252)).sub(1.0),
        "trend_gap_126": prices.div(prices.rolling(126, min_periods=126).mean()).sub(1.0),
        "trend_gap_252": prices.div(prices.rolling(252, min_periods=252).mean()).sub(1.0),
        "vol_21": daily.rolling(21, min_periods=21).std(ddof=0),
        "vol_63": daily.rolling(63, min_periods=63).std(ddof=0),
        "drawdown_63": prices.div(prices.rolling(63, min_periods=63).max()).sub(1.0),
        "high_gap_63": prices.div(prices.rolling(63, min_periods=63).max()).sub(1.0),
        "high_gap_252": prices.div(prices.rolling(252, min_periods=252).max()).sub(1.0),
        "volume_surprise_5": volumes.div(
            volumes.rolling(5, min_periods=5).mean().replace(0.0, np.nan)
        ).sub(1.0),
        "volume_surprise_21": volumes.div(
            volumes.rolling(21, min_periods=21).mean().replace(0.0, np.nan)
        ).sub(1.0),
        "ma_gap_50": prices.div(prices.rolling(50, min_periods=50).mean()).sub(1.0),
    }
    ranked = {
        name: cross_sectional_percentile_rank(frame, rankable_symbols=rankable_symbols)
        for name, frame in raw.items()
    }
    formulas = formula_features_from_spec(ranked, formula_spec=formula_spec)
    return FeatureBundle(raw=raw, ranked=ranked, formulas=formulas)


def cross_sectional_percentile_rank(
    frame: pd.DataFrame,
    *,
    rankable_symbols: tuple[str, ...] = RANKABLE_SYMBOLS,
) -> pd.DataFrame:
    symbols = sorted(rankable_symbols)
    values = frame.reindex(columns=symbols).astype(float)
    return values.rank(axis=1, method="first", ascending=True, pct=True)


def formula_features_from_spec(
    ranked: dict[str, pd.DataFrame],
    *,
    formula_spec: StrategySpec | None,
) -> dict[str, pd.DataFrame]:
    if formula_spec is None:
        raise ValueError("R5 formula features require an explicitly bound StrategySpec")
    formulas: dict[str, pd.DataFrame] = {}
    for name in FORMULA_FEATURES:
        factor = formula_spec.factors.get(name)
        if factor is None:
            raise ValueError(f"formula factor missing from StrategySpec: {name}")
        source_contract = R5_FORMULA_SOURCE_CONTRACT[name]
        params = factor.params
        if factor.expression != source_contract["spec_expression"]:
            raise ValueError(f"formula expression contract mismatch: {name}")
        if (
            params.get("transform") != "weighted_sum_of_component_cross_sectional_percentile_ranks"
            or params.get("rank_method") != "percentile_rank_by_decision_session"
            or params.get("full_sample_fit") is not False
            or params.get("population") != "rankable_symbols_with_finite_history"
            or params.get("rank_ascending") is not True
            or params.get("tie_break") != "symbol_ascending"
            or params.get("apply_at") != "decision_close"
        ):
            raise ValueError(f"formula rank transform contract mismatch: {name}")
        components = list(map(str, params.get("components") or []))
        coefficients = list(map(float, params.get("coefficients") or []))
        if (
            components != source_contract["components"]
            or coefficients != source_contract["coefficients"]
        ):
            raise ValueError(f"formula source mapping contract mismatch: {name}")
        if not components or len(components) != len(coefficients):
            raise ValueError(f"formula component contract mismatch: {name}")
        missing = sorted(set(components) - set(ranked))
        if missing:
            raise ValueError(f"formula components missing for {name}: {', '.join(missing)}")
        value = ranked[components[0]] * coefficients[0]
        for component, coefficient in zip(components[1:], coefficients[1:], strict=True):
            value = value + ranked[component] * coefficient
        formulas[name] = value
    return formulas


def joint_formula_placebo(
    formulas: dict[str, pd.DataFrame],
    *,
    seed: int = PLACEBO_SEED,
    placebo_spec: StrategySpec | None = None,
) -> dict[str, pd.DataFrame]:
    if set(formulas) != set(FORMULA_FEATURES):
        raise ValueError("placebo requires the exact four frozen formula features")
    if placebo_spec is not None:
        factor_params = [placebo_spec.factors[name].params for name in FORMULA_FEATURES]
        seeds = {int(params.get("placebo_seed", -1)) for params in factor_params}
        if seeds != {PLACEBO_SEED} or any(
            params.get("placebo_operation") != "per_decision_session_symbol_permutation"
            or params.get("placebo_mapping") != "same_permutation_for_all_formula_columns"
            for params in factor_params
        ):
            raise ValueError("P01 placebo StrategySpec metadata mismatch")
        seed = seeds.pop()
    template = formulas[FORMULA_FEATURES[0]]
    symbols = sorted(template.columns)
    result = {name: frame.copy() for name, frame in formulas.items()}
    for name, frame in formulas.items():
        if not frame.index.equals(template.index) or list(frame.columns) != list(template.columns):
            raise ValueError(f"formula panel identity mismatch: {name}")
    for session in template.index:
        date = pd.Timestamp(session).date().isoformat()
        destinations = sorted(
            symbols,
            key=lambda symbol: hashlib.sha256(
                f"{seed}|{date}|{symbol}".encode("ascii")
            ).hexdigest(),
        )
        for name, frame in formulas.items():
            source_values = frame.loc[session, symbols].to_numpy(dtype=float)
            result[name].loc[session, destinations] = source_values
    return result


def month_end_decision_points(
    index: pd.DatetimeIndex,
    *,
    rebalance_schedule: str = "calendar_month_end",
) -> list[dict[str, Any]]:
    if rebalance_schedule != "calendar_month_end":
        raise ValueError("R5 requires rebalance_schedule=calendar_month_end")
    sessions = pd.DatetimeIndex(index)
    if sessions.has_duplicates or not sessions.is_monotonic_increasing:
        raise ValueError("decision sessions must be unique and increasing")
    periods = sessions.to_period("M")
    points: list[dict[str, Any]] = []
    for position in range(len(sessions) - 1):
        if periods[position] == periods[position + 1]:
            continue
        points.append(
            {
                "decision_position": position,
                "decision_session": sessions[position],
                "execution_position": position + 1,
                "execution_session": sessions[position + 1],
                "label_end_position": position + 1 + HORIZON_SESSIONS,
            }
        )
    return points


def build_monthly_feature_dataset(
    panel: PanelData,
    features: FeatureBundle,
    *,
    rankable_symbols: tuple[str, ...] = RANKABLE_SYMBOLS,
    placebo_spec: StrategySpec | None = None,
    rebalance_schedule: str = "calendar_month_end",
) -> pd.DataFrame:
    sessions = panel.close.index
    placebo_formulas = joint_formula_placebo(
        features.formulas,
        placebo_spec=placebo_spec,
    )
    rows: list[dict[str, Any]] = []
    for point in month_end_decision_points(
        sessions,
        rebalance_schedule=rebalance_schedule,
    ):
        decision = point["decision_session"]
        entry_position = int(point["execution_position"])
        label_end_position = int(point["label_end_position"])
        for symbol in sorted(rankable_symbols):
            row: dict[str, Any] = {
                **point,
                "decision_session": decision.date().isoformat(),
                "execution_session": point["execution_session"].date().isoformat(),
                "symbol": symbol,
            }
            for name in CORE_FEATURES:
                row[name] = features.ranked[name].at[decision, symbol]
            for name in FORMULA_FEATURES:
                row[name] = features.formulas[name].at[decision, symbol]
                row[f"placebo_{name}"] = placebo_formulas[name].at[decision, symbol]
            for name in ("mom_126_skip21", "mom_252_skip21", "trend_gap_252"):
                row[f"raw_{name}"] = features.raw[name].at[decision, symbol]
            if label_end_position < len(sessions):
                entry = float(panel.open.iloc[entry_position][symbol])
                terminal = float(panel.open.iloc[label_end_position][symbol])
                path = panel.open[symbol].iloc[entry_position : label_end_position + 1]
                path_drawdown = path.div(path.cummax()).sub(1.0)
                forward_return = terminal / entry - 1.0
                row.update(
                    {
                        "label_end_session": sessions[label_end_position].date().isoformat(),
                        "forward_return_21": forward_return,
                        "path_survival_label": int(
                            forward_return >= 0.0 and float(path_drawdown.min()) >= -0.08
                        ),
                        "max_open_path_drawdown": float(path_drawdown.min()),
                    }
                )
            else:
                row.update(
                    {
                        "label_end_session": None,
                        "forward_return_21": np.nan,
                        "path_survival_label": np.nan,
                        "max_open_path_drawdown": np.nan,
                    }
                )
            rows.append(row)
    dataset = pd.DataFrame(rows)
    if dataset.empty:
        raise ValueError("monthly feature dataset is empty")
    return dataset.sort_values(["execution_position", "symbol"]).reset_index(drop=True)


def _formula_placebo_evidence(
    dataset: pd.DataFrame,
    *,
    decision_sessions: set[str],
    seed: int = PLACEBO_SEED,
) -> dict[str, Any]:
    if not decision_sessions:
        raise ValueError("placebo evidence requires evaluated decision sessions")
    required = {
        "decision_session",
        "symbol",
        *FORMULA_FEATURES,
        *(f"placebo_{name}" for name in FORMULA_FEATURES),
    }
    missing = sorted(required - set(dataset.columns))
    if missing:
        raise ValueError("placebo evidence columns missing: " + ", ".join(missing))
    work = dataset[dataset["decision_session"].isin(decision_sessions)].copy()
    actual_sessions = set(map(str, work["decision_session"].unique()))
    if actual_sessions != decision_sessions:
        missing_sessions = sorted(decision_sessions - actual_sessions)
        raise ValueError(
            "placebo evidence decision sessions missing: " + ", ".join(missing_sessions)
        )

    valid_sessions = 0
    divergent_sessions = 0
    divergent_cells = 0
    formula_composite_nonconstant_sessions = 0
    original_records: list[dict[str, Any]] = []
    placebo_records: list[dict[str, Any]] = []
    failures: list[str] = []
    for decision_session, group in work.groupby("decision_session", sort=True):
        current = group.sort_values("symbol")
        symbols = list(map(str, current["symbol"]))
        if symbols != sorted(RANKABLE_SYMBOLS):
            failures.append(f"{decision_session}:symbol_coverage")
            continue
        original = current[list(FORMULA_FEATURES)].to_numpy(dtype=float)
        placebo = current[[f"placebo_{name}" for name in FORMULA_FEATURES]].to_numpy(dtype=float)
        if not np.isfinite(original).all() or not np.isfinite(placebo).all():
            failures.append(f"{decision_session}:nonfinite_formula_values")
            continue
        destinations = sorted(
            symbols,
            key=lambda symbol: hashlib.sha256(
                f"{seed}|{decision_session}|{symbol}".encode("ascii")
            ).hexdigest(),
        )
        destination_positions = {symbol: index for index, symbol in enumerate(symbols)}
        expected = np.empty_like(original)
        for source_position, destination in enumerate(destinations):
            expected[destination_positions[destination], :] = original[source_position, :]
        if not np.array_equal(placebo, expected):
            failures.append(f"{decision_session}:joint_permutation_mismatch")
            continue
        differences = placebo != original
        session_divergent_cells = int(differences.sum())
        divergent_cells += session_divergent_cells
        divergent_sessions += session_divergent_cells > 0
        formula_composite_nonconstant_sessions += int(
            pd.Series(original.mean(axis=1)).nunique(dropna=False) > 1
        )
        valid_sessions += 1
        for row_index, symbol in enumerate(symbols):
            original_records.append(
                {
                    "decision_session": str(decision_session),
                    "symbol": symbol,
                    "values": original[row_index].tolist(),
                }
            )
            placebo_records.append(
                {
                    "decision_session": str(decision_session),
                    "symbol": symbol,
                    "values": placebo[row_index].tolist(),
                }
            )

    expected_count = len(decision_sessions)
    joint_permutation_pass = valid_sessions == expected_count and not failures
    divergence_pass = divergent_sessions == expected_count and divergent_cells > 0
    formula_composite_pass = formula_composite_nonconstant_sessions == expected_count
    return {
        "seed": seed,
        "expected_decision_count": expected_count,
        "valid_joint_permutation_decision_count": valid_sessions,
        "divergent_decision_count": divergent_sessions,
        "divergent_cell_count": divergent_cells,
        "nonconstant_formula_composite_decision_count": formula_composite_nonconstant_sessions,
        "joint_permutation_pass": joint_permutation_pass,
        "formula_feature_divergence_pass": divergence_pass,
        "formula_composite_nonconstant_pass": formula_composite_pass,
        "original_formula_sha256": hashlib.sha256(
            _canonical_json_bytes(original_records)
        ).hexdigest(),
        "placebo_formula_sha256": hashlib.sha256(
            _canonical_json_bytes(placebo_records)
        ).hexdigest(),
        "failures": failures,
        "pass": joint_permutation_pass and divergence_pass and formula_composite_pass,
    }


def _target_difference_count(left: pd.DataFrame, right: pd.DataFrame) -> int:
    columns = sorted(set(left.columns) | set(right.columns))
    if not left.index.equals(right.index) or set(left.columns) != set(right.columns):
        raise ValueError("target difference comparison requires aligned sessions and symbols")
    left_values = left.reindex(columns=columns).to_numpy(dtype=float)
    right_values = right.reindex(columns=columns).to_numpy(dtype=float)
    return int(np.any(left_values != right_values, axis=1).sum())


def _validated_predictor_frame(
    frame: pd.DataFrame,
    *,
    candidate_id: str,
    feature_names: tuple[str, ...],
    label_name: str,
) -> pd.DataFrame:
    expected_features = R5_RUNTIME_PREDICTOR_CONTRACT.get(candidate_id)
    expected_label = R5_MODEL_LABEL_CONTRACT.get(candidate_id)
    if expected_features is None or expected_label is None:
        raise ValueError(f"R5 candidate is not an independently fitted model: {candidate_id}")
    if feature_names != expected_features:
        raise ValueError(f"R5 immutable runtime predictor contract mismatch: {candidate_id}")
    if label_name != expected_label:
        raise ValueError(f"R5 immutable runtime label contract mismatch: {candidate_id}")
    if (
        len(feature_names) != len(set(feature_names))
        or set(feature_names) & R5_FORBIDDEN_PREDICTOR_COLUMNS
        or label_name in feature_names
    ):
        raise ValueError(f"R5 forbidden outcome, identity, or timing predictor: {candidate_id}")
    missing = sorted(set(feature_names) - set(frame.columns))
    if missing:
        raise ValueError(
            f"R5 predictor frame is missing columns for {candidate_id}: {', '.join(missing)}"
        )
    predictors = frame.loc[:, list(feature_names)].copy()
    if tuple(map(str, predictors.columns)) != feature_names:
        raise ValueError(f"R5 predictor frame order changed for {candidate_id}")
    return predictors


def training_rows_for_prediction(
    dataset: pd.DataFrame,
    *,
    decision_position: int,
    train_start_session: str,
    feature_names: tuple[str, ...],
    label_name: str,
    maximum_window_sessions: int = TRAINING_WINDOW_SESSIONS,
    embargo_sessions: int = EMBARGO_SESSIONS,
) -> pd.DataFrame:
    cutoff = decision_position - embargo_sessions
    lower = decision_position - maximum_window_sessions
    work = dataset[
        (dataset["decision_position"] >= lower)
        & (dataset["decision_position"] < decision_position)
        & (dataset["decision_session"] >= train_start_session)
        & (dataset["label_end_position"] <= cutoff)
    ].copy()
    required = [*feature_names, label_name]
    work = work.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
    return work.sort_values(["decision_position", "symbol"]).reset_index(drop=True)


def solve_post_trade_equity_ratio(
    pretrade_weights: np.ndarray,
    target_weights: np.ndarray,
    *,
    cost_bps: float,
    tolerance: float = 1e-14,
) -> tuple[float, float, float]:
    pretrade = np.asarray(pretrade_weights, dtype=float)
    target = np.asarray(target_weights, dtype=float)
    if pretrade.shape != target.shape or pretrade.ndim != 1:
        raise ValueError("pretrade and target weights must be aligned vectors")
    if (
        not np.isfinite(pretrade).all()
        or not np.isfinite(target).all()
        or (pretrade < -tolerance).any()
        or (target < -tolerance).any()
        or pretrade.sum() > 1.0 + tolerance
        or target.sum() > 1.0 + tolerance
    ):
        raise ValueError("self-financing weights must be finite, nonnegative, and sum to <=1")
    if not math.isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("cost_bps must be finite and nonnegative")
    rate = cost_bps / 10_000.0
    if rate == 0.0:
        notional = float(np.abs(target - pretrade).sum())
        return 1.0, notional, 0.0

    def equation(ratio: float) -> float:
        return ratio + rate * float(np.abs(ratio * target - pretrade).sum()) - 1.0

    low = 0.0
    high = 1.0
    if equation(low) > tolerance or equation(high) < -tolerance:
        raise ValueError("self-financing cost equation has no bounded root")
    for _ in range(160):
        midpoint = (low + high) / 2.0
        if equation(midpoint) > 0.0:
            high = midpoint
        else:
            low = midpoint
    ratio = (low + high) / 2.0
    notional = float(np.abs(ratio * target - pretrade).sum())
    cost_fraction = rate * notional
    error = abs((1.0 - ratio) - cost_fraction)
    if error > tolerance:
        raise ValueError("self-financing cost reconciliation failed")
    return ratio, notional, error


def simulate_exact_target_portfolio(
    marks: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    cost_bps: float,
    start: pd.Timestamp | str | None = None,
    end: pd.Timestamp | str | None = None,
    reserve_symbol: str = RESERVE_SYMBOL,
) -> ExactSimulationResult:
    prices = _strict_numeric_panel(marks, "simulation marks", positive=True)
    if list(targets.columns) != list(prices.columns):
        raise ValueError("simulation target symbols must exactly match mark symbols")
    target_values = targets.astype(float)
    if target_values.index.has_duplicates or not target_values.index.is_monotonic_increasing:
        raise ValueError("simulation targets must be unique and increasing")
    if (
        not np.isfinite(target_values.to_numpy()).all()
        or (target_values < -1e-12).any().any()
        or (target_values.sum(axis=1) > 1.0 + 1e-12).any()
    ):
        raise ValueError("simulation targets are invalid")

    selected_start = pd.Timestamp(start) if start is not None else prices.index.min()
    selected_end = pd.Timestamp(end) if end is not None else prices.index.max()
    if selected_start not in prices.index or selected_end not in prices.index:
        raise ValueError("simulation start and end must be exact mark sessions")
    window = prices.loc[(prices.index >= selected_start) & (prices.index <= selected_end)]
    if len(window) < 2:
        raise ValueError("simulation window requires at least two mark sessions")
    in_window_targets = target_values.index[
        (target_values.index >= window.index[0]) & (target_values.index <= window.index[-1])
    ]
    invalid_target_sessions = in_window_targets.difference(window.index[:-1])
    if not invalid_target_sessions.empty:
        raise ValueError(
            "simulation target lacks an executable nonterminal mark session: "
            + ", ".join(str(value) for value in invalid_target_sessions)
        )

    current = np.zeros(len(window.columns), dtype=float)
    cash_weight = 1.0
    equity = 1.0
    events: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    maximum_weight = 0.0
    first_session = window.index[0]
    prior = target_values.loc[target_values.index <= first_session]
    initial_target = prior.iloc[-1] if not prior.empty else None

    for position in range(len(window.index) - 1):
        session = window.index[position]
        next_session = window.index[position + 1]
        selected_target: pd.Series | None = None
        reason = ""
        if session in target_values.index:
            selected_target = target_values.loc[session]
            if isinstance(selected_target, pd.DataFrame):
                raise ValueError("duplicate target session")
            reason = "scheduled_rebalance"
        elif position == 0 and initial_target is not None:
            selected_target = initial_target
            reason = "independent_boundary_entry"

        pretrade_equity = equity
        cost_factor = 1.0
        if selected_target is not None:
            desired = selected_target.to_numpy(dtype=float)
            pretrade = current.copy()
            cost_factor, notional, error = solve_post_trade_equity_ratio(
                pretrade,
                desired,
                cost_bps=cost_bps,
            )
            equity *= cost_factor
            current = desired.copy()
            cash_weight = 1.0 - float(current.sum())
            maximum_weight = max(maximum_weight, float(current.max(initial=0.0)))
            if notional > 1e-15:
                events.append(
                    {
                        "session": session.date().isoformat(),
                        "reason": reason,
                        "terminal": False,
                        "pretrade_equity": pretrade_equity,
                        "pretrade_asset_weights": _weight_mapping(window.columns, pretrade),
                        "pretrade_cash_weight": 1.0 - float(pretrade.sum()),
                        "target_asset_weights": _weight_mapping(window.columns, desired),
                        "posttrade_cash_weight": cash_weight,
                        "posttrade_equity_ratio": cost_factor,
                        "cost_bps": cost_bps,
                        "full_L1_executed_notional_fraction": notional,
                        "cost_fraction_of_pretrade_equity": 1.0 - cost_factor,
                        "cost_reconciliation_error": error,
                    }
                )
        interval_maximum_weight = float(current.max(initial=0.0))
        start_risk_asset_exposure = float(
            sum(
                weight
                for symbol, weight in zip(window.columns, current, strict=True)
                if symbol != reserve_symbol
            )
        )

        asset_returns = (
            window.iloc[position + 1].to_numpy(dtype=float)
            / window.iloc[position].to_numpy(dtype=float)
            - 1.0
        )
        if not np.isfinite(asset_returns).all() or (asset_returns <= -1.0).any():
            raise ValueError("simulation produced invalid asset returns")
        gross_factor = cash_weight + float(np.dot(current, 1.0 + asset_returns))
        if not math.isfinite(gross_factor) or gross_factor <= 0.0:
            raise ValueError("simulation gross factor is invalid")
        net_factor = cost_factor * gross_factor
        equity = pretrade_equity * net_factor
        current = current * (1.0 + asset_returns) / gross_factor
        cash_weight = cash_weight / gross_factor
        if (
            not np.isfinite(current).all()
            or (current < -1e-12).any()
            or abs(float(current.sum()) + cash_weight - 1.0) > 1e-12
        ):
            raise ValueError("simulation drifted weights are invalid")
        maximum_weight = max(maximum_weight, float(current.max(initial=0.0)))
        interval_maximum_weight = max(
            interval_maximum_weight,
            float(current.max(initial=0.0)),
        )
        end_risk_asset_exposure = float(
            sum(
                weight
                for symbol, weight in zip(window.columns, current, strict=True)
                if symbol != reserve_symbol
            )
        )
        daily_rows.append(
            {
                "interval_start": session.date().isoformat(),
                "interval_end": next_session.date().isoformat(),
                "gross_factor_after_rebalance": gross_factor,
                "cost_factor": cost_factor,
                "net_factor": net_factor,
                "net_return": net_factor - 1.0,
                "equity": equity,
                "start_risk_asset_exposure": start_risk_asset_exposure,
                "end_risk_asset_exposure": end_risk_asset_exposure,
                "risk_asset_exposure": end_risk_asset_exposure,
                "maximum_asset_weight_observed": interval_maximum_weight,
            }
        )

    terminal_pretrade = current.copy()
    terminal_ratio, terminal_notional, terminal_error = solve_post_trade_equity_ratio(
        terminal_pretrade,
        np.zeros_like(terminal_pretrade),
        cost_bps=cost_bps,
    )
    if terminal_notional > 1e-15:
        pretrade_equity = equity
        equity *= terminal_ratio
        daily_rows[-1]["cost_factor"] *= terminal_ratio
        daily_rows[-1]["net_factor"] *= terminal_ratio
        daily_rows[-1]["net_return"] = daily_rows[-1]["net_factor"] - 1.0
        daily_rows[-1]["equity"] = equity
        events.append(
            {
                "session": window.index[-1].date().isoformat(),
                "reason": "terminal_liquidation",
                "terminal": True,
                "pretrade_equity": pretrade_equity,
                "pretrade_asset_weights": _weight_mapping(window.columns, terminal_pretrade),
                "pretrade_cash_weight": 1.0 - float(terminal_pretrade.sum()),
                "target_asset_weights": _weight_mapping(
                    window.columns, np.zeros_like(terminal_pretrade)
                ),
                "posttrade_cash_weight": 1.0,
                "posttrade_equity_ratio": terminal_ratio,
                "cost_bps": cost_bps,
                "full_L1_executed_notional_fraction": terminal_notional,
                "cost_fraction_of_pretrade_equity": 1.0 - terminal_ratio,
                "cost_reconciliation_error": terminal_error,
            }
        )

    daily = pd.DataFrame(daily_rows)
    metrics = performance_metrics(daily, events, maximum_weight=maximum_weight)
    return ExactSimulationResult(daily=daily, events=events, metrics=metrics)


def performance_metrics(
    daily: pd.DataFrame,
    events: list[dict[str, Any]],
    *,
    maximum_weight: float,
) -> dict[str, Any]:
    returns = pd.to_numeric(daily["net_return"], errors="raise").astype(float)
    equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
    if (
        returns.empty
        or not np.isfinite(returns.to_numpy()).all()
        or not np.isfinite(equity.to_numpy()).all()
        or (equity <= 0.0).any()
    ):
        raise ValueError("performance path must be finite, positive, and nonempty")
    observed_maximum_weight = float(
        pd.to_numeric(daily["maximum_asset_weight_observed"], errors="raise").max()
    )
    if abs(observed_maximum_weight - maximum_weight) > 1e-12:
        raise ValueError("performance maximum weight differs from daily ledger")
    std = float(returns.std(ddof=1)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / std * math.sqrt(252.0)) if std > 0.0 else 0.0
    full_equity = pd.concat([pd.Series([1.0]), equity], ignore_index=True)
    drawdown = full_equity.div(full_equity.cummax()).sub(1.0)
    years = len(returns) / 252.0
    final_equity = float(equity.iloc[-1])
    full_l1 = float(sum(event["full_L1_executed_notional_fraction"] for event in events))
    return {
        "market_interval_count": len(returns),
        "total_return_pct": (final_equity - 1.0) * 100.0,
        "annualized_return_pct": (final_equity ** (1.0 / years) - 1.0) * 100.0,
        "annualized_volatility_pct": std * math.sqrt(252.0) * 100.0,
        "annualized_sharpe": sharpe,
        "max_drawdown_pct": float(drawdown.min() * 100.0),
        "positive_interval_pct": float((returns > 0.0).mean() * 100.0),
        "total_full_L1_executed_notional": full_l1,
        "annualized_full_L1_executed_notional_ratio": full_l1 / years,
        "legacy_half_turnover_report_only": 0.5 * full_l1,
        "maximum_drifted_weight": maximum_weight,
        "average_start_risk_asset_exposure": float(daily["start_risk_asset_exposure"].mean()),
        "average_end_risk_asset_exposure": float(daily["end_risk_asset_exposure"].mean()),
        "average_risk_asset_exposure": float(daily["risk_asset_exposure"].mean()),
        "nonzero_rebalance_count": sum(not event["terminal"] for event in events),
        "terminal_liquidation_count": sum(bool(event["terminal"]) for event in events),
        "maximum_cost_reconciliation_error": max(
            (float(event["cost_reconciliation_error"]) for event in events), default=0.0
        ),
    }


def build_cscv_partitions(
    sessions: pd.Index,
    *,
    block_count: int = 8,
    in_sample_block_count: int = 4,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    ordered = pd.Index(sessions)
    if len(ordered) < block_count or ordered.has_duplicates:
        raise ValueError("CSCV sessions must be unique and cover every block")
    blocks = [
        np.asarray(values, dtype=int)
        for values in np.array_split(np.arange(len(ordered)), block_count)
    ]
    if any(len(block) == 0 for block in blocks):
        raise ValueError("CSCV block cannot be empty")
    if max(map(len, blocks)) - min(map(len, blocks)) > 1:
        raise ValueError("CSCV block sizes differ by more than one")
    metadata = [
        {
            "block_id": f"B{index + 1:02d}",
            "position_start": int(block[0]),
            "position_end": int(block[-1]),
            "observation_count": len(block),
            "session_start": str(ordered[block[0]]),
            "session_end": str(ordered[block[-1]]),
        }
        for index, block in enumerate(blocks)
    ]
    partitions = [
        np.asarray(indices, dtype=int)
        for indices in combinations(range(block_count), in_sample_block_count)
    ]
    expected = math.comb(block_count, in_sample_block_count)
    if len(partitions) != expected:
        raise AssertionError("CSCV directional partition count mismatch")
    return metadata, partitions


def probability_backtest_overfitting(
    returns: pd.DataFrame,
    *,
    candidate_ids: tuple[str, ...] | list[str],
    block_count: int = 8,
    in_sample_block_count: int = 4,
) -> dict[str, Any]:
    candidates = list(candidate_ids)
    if len(candidates) < 2 or len(set(candidates)) != len(candidates):
        raise ValueError("PBO candidate IDs must be unique and contain at least two candidates")
    missing = sorted(set(candidates) - set(returns.columns))
    if missing:
        raise ValueError("PBO candidate returns missing: " + ", ".join(missing))
    values = returns[candidates].astype(float)
    if values.empty or values.index.has_duplicates or not np.isfinite(values.to_numpy()).all():
        raise ValueError("PBO returns must be finite, nonempty, and uniquely indexed")
    blocks, partitions = build_cscv_partitions(
        values.index,
        block_count=block_count,
        in_sample_block_count=in_sample_block_count,
    )
    all_blocks = set(range(len(blocks)))
    rows: list[dict[str, Any]] = []
    overfit_count = 0
    for partition_number, in_blocks_array in enumerate(partitions, start=1):
        in_blocks = tuple(map(int, in_blocks_array))
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
        if set(in_positions) & set(out_positions) or len(in_positions) + len(out_positions) != len(
            values
        ):
            raise ValueError("PBO partition does not cover sessions exactly once")
        in_sharpes = {
            candidate: defined_annualized_sharpe(values.iloc[in_positions][candidate])
            for candidate in candidates
        }
        selected = sorted(candidates, key=lambda item: (-in_sharpes[item], item))[0]
        out_sharpes = {
            candidate: defined_annualized_sharpe(values.iloc[out_positions][candidate])
            for candidate in candidates
        }
        ordered = sorted(candidates, key=lambda item: (out_sharpes[item], item))
        rank = ordered.index(selected) + 1
        omega = (rank - 0.5) / len(candidates)
        logit = math.log(omega / (1.0 - omega))
        overfit = logit <= 0.0
        overfit_count += int(overfit)
        rows.append(
            {
                "partition": partition_number,
                "in_sample_blocks": [blocks[index]["block_id"] for index in in_blocks],
                "out_of_sample_blocks": [blocks[index]["block_id"] for index in out_blocks],
                "selected_candidate_id": selected,
                "in_sample_sharpes": in_sharpes,
                "out_of_sample_sharpes": out_sharpes,
                "selected_out_of_sample_rank": rank,
                "normalized_rank": omega,
                "rank_logit": logit,
                "overfit_event": overfit,
            }
        )
    expected_partition_count = math.comb(block_count, in_sample_block_count)
    if len(rows) != expected_partition_count:
        raise ValueError("R5 PBO directional partition count is incomplete")
    return {
        "method": "combinatorially_symmetric_cross_validation",
        "candidate_ids": candidates,
        "block_count": block_count,
        "in_sample_block_count": in_sample_block_count,
        "blocks": blocks,
        "partition_count": len(rows),
        "valid_partition_count": len(rows),
        "overfit_partition_count": overfit_count,
        "probability": overfit_count / len(rows),
        "partitions": rows,
    }


def defined_annualized_sharpe(values: pd.Series) -> float:
    returns = pd.to_numeric(values, errors="raise").astype(float)
    if len(returns) < 2 or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Sharpe requires at least two finite returns")
    if returns.nunique(dropna=False) < 2:
        raise ValueError("Sharpe is undefined for zero-variance returns")
    standard_deviation = float(returns.std(ddof=1))
    if standard_deviation <= 0.0:
        raise ValueError("Sharpe is undefined for zero-variance returns")
    return float(returns.mean() / standard_deviation * math.sqrt(252.0))


def _expected_llm_contribution_bootstrap_contract() -> dict[str, Any]:
    return {
        "method_id": "paired_non_circular_moving_block_bootstrap_sharpe_delta_v1",
        "scope_id": "TRANSFER",
        "cost_view": "primary_10bps",
        "cost_bps": 10.0,
        "candidate_id": "R5C01",
        "comparator_ids": ["R5M01", "R5P01"],
        "expected_return_observation_count": 384,
        "minimum_return_observation_count": 252,
        "statistic": "annualized_sharpe_candidate_minus_comparator",
        "sample_std_ddof": 1,
        "annualization_sessions": 252,
        "block_sampling": "shared_non_circular_moving_blocks_with_replacement",
        "block_length": 21,
        "blocks_per_resample": "ceiling_observation_count_divided_by_block_length",
        "path_length": "truncate_concatenated_blocks_to_observation_count",
        "rng_bit_generator": "PCG64",
        "rng_seed": 4201,
        "resample_count": 2000,
        "required_valid_resample_count": 2000,
        "point_estimate_minimum_delta": 0.05,
        "familywise_one_sided_alpha": 0.05,
        "multiple_comparison_correction": "bonferroni_two_comparisons",
        "per_comparison_one_sided_alpha": 0.025,
        "lower_percentile_sorted_zero_based_index": 49,
        "lower_confidence_bound_requirement": "strictly_positive",
        "boundary_cost_policy": (
            "strip_each_candidate_entry_and_terminal_posttrade_equity_ratio_then_restore_"
            "each_once_at_bootstrap_path_boundaries"
        ),
        "index_matrix_hash_format": "little_endian_int64_c_order",
        "delta_array_hash_format": "little_endian_float64_c_order",
        "invalid_evidence_action": "fail_closed",
        "interpretation": (
            "historical_incremental_contribution_from_frozen_formula_mappings_not_"
            "independent_llm_alpha"
        ),
    }


def _non_circular_moving_block_indices(
    observation_count: int,
    *,
    block_length: int,
    resample_count: int,
    seed: int,
) -> np.ndarray:
    if (
        type(observation_count) is not int
        or type(block_length) is not int
        or type(resample_count) is not int
        or type(seed) is not int
        or observation_count < 2
        or not 1 <= block_length <= observation_count
        or resample_count < 1
        or seed < 0
    ):
        raise ValueError("moving-block bootstrap dimensions are invalid")
    blocks_per_resample = math.ceil(observation_count / block_length)
    generator = np.random.Generator(np.random.PCG64(seed))
    starts = generator.integers(
        0,
        observation_count - block_length + 1,
        size=(resample_count, blocks_per_resample),
        dtype=np.int64,
    )
    offsets = np.arange(block_length, dtype=np.int64)
    indexes = (starts[:, :, None] + offsets[None, None, :]).reshape(resample_count, -1)
    indexes = np.ascontiguousarray(indexes[:, :observation_count], dtype="<i8")
    if indexes.shape != (resample_count, observation_count):
        raise ValueError("moving-block bootstrap index matrix has the wrong shape")
    if int(indexes.min()) < 0 or int(indexes.max()) >= observation_count:
        raise ValueError("moving-block bootstrap index matrix is out of bounds")
    return indexes


def _little_endian_array_sha256(values: np.ndarray, dtype: str) -> str:
    normalized = np.ascontiguousarray(values, dtype=dtype)
    return hashlib.sha256(normalized.tobytes(order="C")).hexdigest()


def _canonical_session_timestamp(value: Any) -> pd.Timestamp:
    if not isinstance(value, str) or not value:
        raise ValueError("session must be a nonempty canonical date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("session must be a canonical ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError("session must use canonical YYYY-MM-DD form")
    return pd.Timestamp(parsed)


def paired_transfer_sharpe_bootstrap(
    daily_return_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
) -> dict[str, Any]:
    expected_contract = _expected_llm_contribution_bootstrap_contract()
    if _canonical_json_bytes(contract) != _canonical_json_bytes(expected_contract):
        raise ValueError("R5 LLM contribution bootstrap contract is invalid")

    candidate_id = str(contract["candidate_id"])
    comparator_ids = list(map(str, contract["comparator_ids"]))
    candidate_ids = [candidate_id, *comparator_ids]
    scope_id = str(contract["scope_id"])
    cost_view = str(contract["cost_view"])
    expected_count = int(contract["expected_return_observation_count"])
    minimum_count = int(contract["minimum_return_observation_count"])
    tolerance = 1e-12

    common_identities: list[tuple[str, str]] | None = None
    return_sources: dict[str, dict[str, Any]] = {}
    boundary_costs: dict[str, dict[str, Any]] = {}
    stripped_factors: dict[str, np.ndarray] = {}
    observed_sharpes: dict[str, float] = {}

    for selected_candidate_id in candidate_ids:
        selected_rows = [
            row
            for row in daily_return_rows
            if row.get("candidate_id") == selected_candidate_id
            and row.get("scope_id") == scope_id
            and row.get("cost_view") == cost_view
        ]
        selected_rows.sort(
            key=lambda row: (
                str(row.get("interval_start") or ""),
                str(row.get("interval_end") or ""),
            )
        )
        identities = [
            (str(row.get("interval_start") or ""), str(row.get("interval_end") or ""))
            for row in selected_rows
        ]
        if len(selected_rows) != expected_count or len(selected_rows) < minimum_count:
            raise ValueError(
                f"R5 LLM contribution bootstrap return count is invalid for {selected_candidate_id}"
            )
        if any(not start or not end for start, end in identities) or len(identities) != len(
            set(identities)
        ):
            raise ValueError(
                f"R5 LLM contribution bootstrap intervals are missing or duplicated for "
                f"{selected_candidate_id}"
            )
        if len({start for start, _ in identities}) != len(identities):
            raise ValueError(
                f"R5 LLM contribution bootstrap interval starts are duplicated for "
                f"{selected_candidate_id}"
            )
        try:
            parsed_identities = [
                (_canonical_session_timestamp(start), _canonical_session_timestamp(end))
                for start, end in identities
            ]
        except ValueError as exc:
            raise ValueError(
                f"R5 LLM contribution bootstrap intervals are invalid for {selected_candidate_id}"
            ) from exc
        if any(start >= end for start, end in parsed_identities) or any(
            parsed_identities[index][0] >= parsed_identities[index + 1][0]
            for index in range(len(parsed_identities) - 1)
        ):
            raise ValueError(
                f"R5 LLM contribution bootstrap intervals are not chronological for "
                f"{selected_candidate_id}"
            )
        if any(
            identities[index][1] != identities[index + 1][0] for index in range(len(identities) - 1)
        ):
            raise ValueError(
                f"R5 LLM contribution bootstrap intervals are not contiguous for "
                f"{selected_candidate_id}"
            )
        if common_identities is None:
            common_identities = identities
        elif identities != common_identities:
            raise ValueError("R5 LLM contribution bootstrap candidate intervals are misaligned")

        source_rows: list[dict[str, Any]] = []
        factors: list[float] = []
        returns: list[float] = []
        for row in selected_rows:
            try:
                net_factor = float(row["net_factor"])
                net_return = float(row["net_return"])
                cost_factor = float(row["cost_factor"])
                gross_factor = float(row["gross_factor_after_rebalance"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"R5 LLM contribution bootstrap return fields are invalid for "
                    f"{selected_candidate_id}"
                ) from exc
            if (
                not all(
                    math.isfinite(value)
                    for value in (net_factor, net_return, cost_factor, gross_factor)
                )
                or net_factor <= 0.0
                or not 0.0 < cost_factor <= 1.0
                or gross_factor <= 0.0
                or abs(net_factor - (1.0 + net_return)) > tolerance
            ):
                raise ValueError(
                    f"R5 LLM contribution bootstrap returns are nonfinite or inconsistent for "
                    f"{selected_candidate_id}"
                )
            factors.append(net_factor)
            returns.append(net_return)
            source_rows.append(
                {
                    "interval_start": str(row["interval_start"]),
                    "interval_end": str(row["interval_end"]),
                    "net_factor": net_factor,
                    "net_return": net_return,
                    "cost_factor": cost_factor,
                    "gross_factor_after_rebalance": gross_factor,
                }
            )

        factor_array = np.asarray(factors, dtype=float)
        return_array = np.asarray(returns, dtype=float)
        observed_sharpes[selected_candidate_id] = defined_annualized_sharpe(pd.Series(return_array))
        return_sources[selected_candidate_id] = {
            "row_count": len(source_rows),
            "first_interval_start": identities[0][0],
            "last_interval_end": identities[-1][1],
            "sha256": hashlib.sha256(_canonical_json_bytes(source_rows)).hexdigest(),
        }

        selected_events = [
            row
            for row in event_rows
            if row.get("candidate_id") == selected_candidate_id
            and row.get("scope_id") == scope_id
            and row.get("cost_view") == cost_view
        ]
        daily_event_binding = _daily_event_cost_binding_checks(
            pd.DataFrame(selected_rows),
            selected_events,
            tolerance=tolerance,
            expected_cost_bps=float(contract["cost_bps"]),
        )
        if daily_event_binding["failures"]:
            raise ValueError(
                f"R5 LLM contribution bootstrap daily/event cost binding is invalid for "
                f"{selected_candidate_id}:" + ",".join(daily_event_binding["failures"])
            )
        entry_events = [
            row
            for row in selected_events
            if row.get("terminal") is False and str(row.get("session") or "") == identities[0][0]
        ]
        terminal_events = [row for row in selected_events if row.get("terminal") is True]
        nonterminal_sessions = [
            str(row.get("session") or "") for row in selected_events if row.get("terminal") is False
        ]
        if (
            len(entry_events) != 1
            or len(terminal_events) != 1
            or not nonterminal_sessions
            or min(nonterminal_sessions) != identities[0][0]
            or str(terminal_events[0].get("session") or "") != identities[-1][1]
            or entry_events[0].get("reason")
            not in {"scheduled_rebalance", "independent_boundary_entry"}
            or terminal_events[0].get("reason") != "terminal_liquidation"
        ):
            raise ValueError(
                f"R5 LLM contribution bootstrap boundary events are invalid for "
                f"{selected_candidate_id}"
            )

        ratios: dict[str, float] = {}
        boundary_sources: dict[str, dict[str, Any]] = {}
        for boundary_name, event in (
            ("entry", entry_events[0]),
            ("terminal", terminal_events[0]),
        ):
            try:
                ratio = float(event["posttrade_equity_ratio"])
                event_cost_bps = float(event["cost_bps"])
                notional = float(event["full_L1_executed_notional_fraction"])
                cost_fraction = float(event["cost_fraction_of_pretrade_equity"])
                pretrade_cash = float(event["pretrade_cash_weight"])
                posttrade_cash = float(event["posttrade_cash_weight"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"R5 LLM contribution bootstrap boundary fields are invalid for "
                    f"{selected_candidate_id}:{boundary_name}"
                ) from exc
            expected_cost_fraction = float(contract["cost_bps"]) / 10_000.0 * notional
            pretrade_weights = event.get("pretrade_asset_weights")
            target_weights = event.get("target_asset_weights")
            weight_mappings_valid = bool(
                isinstance(pretrade_weights, dict)
                and isinstance(target_weights, dict)
                and set(pretrade_weights) == set(target_weights)
                and RESERVE_SYMBOL in pretrade_weights
                and all(
                    math.isfinite(float(value))
                    for value in [*pretrade_weights.values(), *target_weights.values()]
                )
            )
            boundary_position_valid = False
            if weight_mappings_valid and boundary_name == "entry":
                boundary_position_valid = bool(
                    all(abs(float(value)) <= tolerance for value in pretrade_weights.values())
                    and abs(pretrade_cash - 1.0) <= tolerance
                    and sum(float(value) for value in target_weights.values()) > 0.0
                )
            elif weight_mappings_valid:
                boundary_position_valid = bool(
                    all(abs(float(value)) <= tolerance for value in target_weights.values())
                    and abs(posttrade_cash - 1.0) <= tolerance
                )
            reconstructed_notional = (
                sum(
                    abs(ratio * float(target_weights[symbol]) - float(pretrade_weights[symbol]))
                    for symbol in target_weights
                )
                if weight_mappings_valid
                else math.nan
            )
            weight_totals_valid = bool(
                weight_mappings_valid
                and abs(
                    sum(float(value) for value in pretrade_weights.values()) + pretrade_cash - 1.0
                )
                <= tolerance
                and abs(
                    sum(float(value) for value in target_weights.values()) + posttrade_cash - 1.0
                )
                <= tolerance
            )
            if (
                not all(
                    math.isfinite(value)
                    for value in (
                        ratio,
                        event_cost_bps,
                        notional,
                        cost_fraction,
                        pretrade_cash,
                        posttrade_cash,
                    )
                )
                or not 0.0 < ratio < 1.0
                or notional <= 0.0
                or cost_fraction <= 0.0
                or event_cost_bps != float(contract["cost_bps"])
                or abs(cost_fraction - (1.0 - ratio)) > tolerance
                or abs(cost_fraction - expected_cost_fraction) > tolerance
                or not boundary_position_valid
                or not weight_totals_valid
                or abs(reconstructed_notional - notional) > tolerance
            ):
                raise ValueError(
                    f"R5 LLM contribution bootstrap boundary accounting is invalid for "
                    f"{selected_candidate_id}:{boundary_name}"
                )
            ratios[boundary_name] = ratio
            boundary_sources[boundary_name] = {
                "session": str(event["session"]),
                "reason": str(event["reason"]),
                "posttrade_equity_ratio": ratio,
                "event_sha256": hashlib.sha256(_canonical_json_bytes(event)).hexdigest(),
            }

        stripped = factor_array.copy()
        stripped[0] /= ratios["entry"]
        stripped[-1] /= ratios["terminal"]
        if not np.isfinite(stripped).all() or (stripped <= 0.0).any():
            raise ValueError(
                f"R5 LLM contribution bootstrap boundary stripping failed for "
                f"{selected_candidate_id}"
            )
        reconstructed = stripped.copy()
        reconstructed[0] *= ratios["entry"]
        reconstructed[-1] *= ratios["terminal"]
        if not np.allclose(reconstructed, factor_array, atol=tolerance, rtol=0.0):
            raise ValueError(
                f"R5 LLM contribution bootstrap boundary restoration failed for "
                f"{selected_candidate_id}"
            )
        stripped_factors[selected_candidate_id] = stripped
        boundary_costs[selected_candidate_id] = {
            **boundary_sources,
            "entry_restorations_per_resample": 1,
            "terminal_restorations_per_resample": 1,
            "boundary_stripped_factor_sha256": _little_endian_array_sha256(stripped, "<f8"),
        }

    if common_identities is None:
        raise ValueError("R5 LLM contribution bootstrap has no common intervals")
    indexes = _non_circular_moving_block_indices(
        expected_count,
        block_length=int(contract["block_length"]),
        resample_count=int(contract["resample_count"]),
        seed=int(contract["rng_seed"]),
    )
    block_starts = np.ascontiguousarray(
        indexes[:, :: int(contract["block_length"])],
        dtype="<i8",
    )
    deltas = {comparator_id: [] for comparator_id in comparator_ids}
    valid_resample_count = 0
    for bootstrap_indexes in indexes:
        path_sharpes: dict[str, float] = {}
        try:
            for selected_candidate_id in candidate_ids:
                path_factors = stripped_factors[selected_candidate_id][bootstrap_indexes].copy()
                path_factors[0] *= boundary_costs[selected_candidate_id]["entry"][
                    "posttrade_equity_ratio"
                ]
                path_factors[-1] *= boundary_costs[selected_candidate_id]["terminal"][
                    "posttrade_equity_ratio"
                ]
                path_sharpes[selected_candidate_id] = defined_annualized_sharpe(
                    pd.Series(path_factors - 1.0)
                )
        except ValueError:
            continue
        valid_resample_count += 1
        for comparator_id in comparator_ids:
            deltas[comparator_id].append(path_sharpes[candidate_id] - path_sharpes[comparator_id])

    required_valid_count = int(contract["required_valid_resample_count"])
    if valid_resample_count != required_valid_count:
        raise ValueError("R5 LLM contribution bootstrap has too few valid resamples")
    lower_index = int(contract["lower_percentile_sorted_zero_based_index"])
    minimum_delta = float(contract["point_estimate_minimum_delta"])
    comparisons: dict[str, dict[str, Any]] = {}
    for comparator_id in comparator_ids:
        delta_array = np.asarray(deltas[comparator_id], dtype=float)
        if len(delta_array) != required_valid_count or not np.isfinite(delta_array).all():
            raise ValueError(
                f"R5 LLM contribution bootstrap delta array is invalid for {comparator_id}"
            )
        sorted_deltas = np.sort(delta_array)
        if not 0 <= lower_index < len(sorted_deltas):
            raise ValueError("R5 LLM contribution bootstrap percentile index is invalid")
        observed_delta = observed_sharpes[candidate_id] - observed_sharpes[comparator_id]
        lower_bound = float(sorted_deltas[lower_index])
        point_estimate_pass = observed_delta >= minimum_delta
        lower_bound_pass = lower_bound > 0.0
        comparison_id = f"{candidate_id}_minus_{comparator_id}"
        comparisons[comparison_id] = {
            "candidate_id": candidate_id,
            "comparator_id": comparator_id,
            "candidate_observed_annualized_sharpe": observed_sharpes[candidate_id],
            "comparator_observed_annualized_sharpe": observed_sharpes[comparator_id],
            "observed_annualized_sharpe_delta": observed_delta,
            "minimum_observed_delta": minimum_delta,
            "point_estimate_pass": point_estimate_pass,
            "valid_resample_count": len(delta_array),
            "delta_array_sha256": _little_endian_array_sha256(delta_array, "<f8"),
            "lower_percentile_sorted_zero_based_index": lower_index,
            "one_sided_alpha": float(contract["per_comparison_one_sided_alpha"]),
            "lower_confidence_bound": lower_bound,
            "lower_confidence_bound_strictly_positive": lower_bound_pass,
            "pass": bool(point_estimate_pass and lower_bound_pass),
        }

    return {
        "schema_version": 1,
        "method_id": str(contract["method_id"]),
        "interpretation": str(contract["interpretation"]),
        "config": contract,
        "config_sha256": hashlib.sha256(_canonical_json_bytes(contract)).hexdigest(),
        "source_ledgers": {
            "daily_return_ledger_sha256": _jsonl_sha256(daily_return_rows),
            "event_ledger_sha256": _jsonl_sha256(event_rows),
        },
        "return_sources": return_sources,
        "boundary_costs": boundary_costs,
        "common_interval_count": len(common_identities),
        "common_interval_identity_sha256": hashlib.sha256(
            _canonical_json_bytes(common_identities)
        ).hexdigest(),
        "bootstrap_index_matrix_shape": list(indexes.shape),
        "bootstrap_index_matrix_sha256": _little_endian_array_sha256(indexes, "<i8"),
        "bootstrap_block_start_matrix_shape": list(block_starts.shape),
        "bootstrap_block_start_matrix_sha256": _little_endian_array_sha256(block_starts, "<i8"),
        "valid_resample_count": valid_resample_count,
        "comparisons": comparisons,
        "pass": all(row["pass"] for row in comparisons.values()),
    }


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    trial_count: int,
    scope_ids: list[str] | tuple[str, ...] | pd.Series | None = None,
    hac_lag: int = 21,
) -> dict[str, Any]:
    values = pd.to_numeric(returns, errors="raise").astype(float)
    if type(trial_count) is not int or trial_count < 2:
        raise ValueError("DSR trial_count must be an integer at least two")
    if type(hac_lag) is not int or hac_lag < 1:
        raise ValueError("DSR HAC lag must be a positive integer")
    if len(values) <= hac_lag or not np.isfinite(values.to_numpy()).all():
        raise ValueError("DSR requires finite returns and more sessions than the HAC lag")
    scopes = list(scope_ids) if scope_ids is not None else ["ALL"] * len(values)
    if len(scopes) != len(values) or any(not isinstance(item, str) or not item for item in scopes):
        raise ValueError("DSR scope IDs must be aligned nonempty strings")
    standard_deviation = float(values.std(ddof=1))
    if values.nunique(dropna=False) < 2 or standard_deviation <= 0.0:
        raise ValueError("DSR is undefined for zero-variance returns")
    array = values.to_numpy(dtype=float)
    session_count = len(array)
    mean = math.fsum(map(float, array)) / session_count
    centered = [float(value) - mean for value in array]
    second_central_moment = math.fsum(value * value for value in centered) / session_count
    if not math.isfinite(second_central_moment) or second_central_moment <= 0.0:
        raise ValueError("DSR second central moment is nonpositive")
    third_central_moment = math.fsum(value * value * value for value in centered) / session_count
    fourth_central_moment = (
        math.fsum(value * value * value * value for value in centered) / session_count
    )
    raw_skew = third_central_moment / second_central_moment**1.5
    skew = math.sqrt(session_count * (session_count - 1.0)) / (session_count - 2.0) * raw_skew
    raw_excess_kurtosis = fourth_central_moment / second_central_moment**2 - 3.0
    excess_kurtosis = (
        (session_count - 1.0)
        / ((session_count - 2.0) * (session_count - 3.0))
        * ((session_count + 1.0) * raw_excess_kurtosis + 6.0)
    )
    pearson_kurtosis = excess_kurtosis + 3.0

    autocorrelations: list[dict[str, Any]] = []
    weighted_autocorrelation_sum = 0.0
    for lag in range(1, hac_lag + 1):
        products = [
            centered[index] * centered[index - lag]
            for index in range(lag, session_count)
            if scopes[index] == scopes[index - lag]
        ]
        pair_count = len(products)
        autocovariance = math.fsum(products) / session_count
        autocorrelation = autocovariance / second_central_moment
        weight = 1.0 - lag / (hac_lag + 1.0)
        weighted_autocorrelation_sum += weight * autocorrelation
        autocorrelations.append(
            {
                "lag": lag,
                "bartlett_weight": weight,
                "within_scope_pair_count": pair_count,
                "autocovariance_divisor": session_count,
                "autocorrelation": autocorrelation,
            }
        )
    raw_inflation = 1.0 + 2.0 * weighted_autocorrelation_sum
    inflation = max(1.0, raw_inflation)
    effective_session_count = min(float(session_count), session_count / inflation)
    if not math.isfinite(effective_session_count) or effective_session_count <= 1.0:
        raise ValueError("DSR HAC effective session count is invalid")

    observed_daily = mean / standard_deviation
    normal = NormalDist()
    gamma = 0.5772156649015329
    expected_max_standard = (1.0 - gamma) * normal.inv_cdf(1.0 - 1.0 / trial_count) + (
        gamma * normal.inv_cdf(1.0 - 1.0 / (trial_count * math.e))
    )
    denominator = 1.0 - skew * observed_daily + ((pearson_kurtosis - 1.0) / 4.0) * observed_daily**2
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("DSR denominator is nonfinite or nonpositive")

    def probability_for_session_count(count: float) -> tuple[float, float, float]:
        expected_daily = expected_max_standard / math.sqrt(count - 1.0)
        statistic = (observed_daily * math.sqrt(count - 1.0) - expected_max_standard) / math.sqrt(
            denominator
        )
        probability = normal.cdf(statistic)
        return probability, expected_daily, statistic

    iid_probability, iid_expected_daily, iid_statistic = probability_for_session_count(
        float(session_count)
    )
    hac_probability, hac_expected_daily, hac_statistic = probability_for_session_count(
        effective_session_count
    )
    promotion_probability = min(iid_probability, hac_probability)
    return {
        "estimator_id": (
            "bailey_lopez_de_prado_expected_max_normal_with_bartlett_effective_sessions_v2"
        ),
        "trial_count": trial_count,
        "session_count": session_count,
        "scope_count": len(set(scopes)),
        "probability": promotion_probability,
        "iid_probability": iid_probability,
        "hac_probability": hac_probability,
        "promotion_probability": promotion_probability,
        "promotion_probability_rule": "minimum_of_iid_and_hac_effective_session_probabilities",
        "observed_annualized_sharpe": observed_daily * math.sqrt(252.0),
        "expected_max_annualized_sharpe_under_null": hac_expected_daily * math.sqrt(252.0),
        "iid_expected_max_annualized_sharpe_under_null": iid_expected_daily * math.sqrt(252.0),
        "hac_expected_max_annualized_sharpe_under_null": hac_expected_daily * math.sqrt(252.0),
        "iid_statistic": iid_statistic,
        "hac_statistic": hac_statistic,
        "return_skew": skew,
        "return_pearson_kurtosis": pearson_kurtosis,
        "hac_overlay_id": "bartlett_newey_west_effective_session_haircut_v1",
        "hac_lag": hac_lag,
        "hac_autocovariance_mean": "global_return_mean",
        "hac_autocovariance_divisor": "full_session_count_n",
        "hac_fold_boundary_policy": "exclude_cross_scope_lag_pairs",
        "hac_autocorrelations": autocorrelations,
        "hac_raw_inflation_factor": raw_inflation,
        "hac_inflation_factor": inflation,
        "effective_session_count": effective_session_count,
    }


def calibration_metrics(
    labels: pd.Series | np.ndarray,
    probabilities: pd.Series | np.ndarray,
    training_base_probabilities: pd.Series | np.ndarray,
    *,
    clip: float = 1e-6,
    slope_min: float = 0.7,
    slope_max: float = 1.3,
    minimum_observation_count: int = 3,
    minimum_class_count: int = 1,
) -> dict[str, Any]:
    y = np.asarray(labels, dtype=float)
    probability = np.asarray(probabilities, dtype=float)
    base = np.asarray(training_base_probabilities, dtype=float)
    if not (y.shape == probability.shape == base.shape) or y.ndim != 1 or len(y) < 3:
        raise ValueError("calibration inputs must be aligned one-dimensional vectors")
    if (
        not np.isfinite(y).all()
        or not np.isfinite(probability).all()
        or not np.isfinite(base).all()
        or not np.isin(y, [0.0, 1.0]).all()
        or (probability < 0.0).any()
        or (probability > 1.0).any()
        or (base < 0.0).any()
        or (base > 1.0).any()
    ):
        raise ValueError("calibration inputs are invalid")
    if not (0.0 < clip < 0.5):
        raise ValueError("calibration probability clip must be between zero and one half")
    if not (math.isfinite(slope_min) and math.isfinite(slope_max) and 0.0 < slope_min <= slope_max):
        raise ValueError("calibration slope bounds are invalid")
    if minimum_observation_count < 3 or minimum_class_count < 1:
        raise ValueError("calibration sample thresholds are invalid")
    model_brier = float(np.mean((probability - y) ** 2))
    base_brier = float(np.mean((base - y) ** 2))
    positive_count = int(np.sum(y == 1.0))
    negative_count = int(np.sum(y == 0.0))
    slope: float | None = None
    reason: str | None = None
    if len(y) < minimum_observation_count:
        reason = "insufficient_observations"
    elif min(positive_count, negative_count) < minimum_class_count:
        reason = "insufficient_class_count"
    elif len(np.unique(y)) < 2:
        reason = "single_class_labels"
    else:
        clipped = np.clip(probability, clip, 1.0 - clip)
        logits = np.log(clipped / (1.0 - clipped))
        if float(np.std(logits)) <= 1e-12:
            reason = "constant_probabilities"
        else:
            design = np.column_stack([np.ones(len(logits)), logits])

            def objective(coefficients: np.ndarray) -> float:
                linear = np.clip(design @ coefficients, -40.0, 40.0)
                return float(np.sum(np.logaddexp(0.0, linear) - y * linear))

            fitted = minimize(objective, np.asarray([0.0, 1.0]), method="BFGS")
            if not fitted.success or not np.isfinite(fitted.x).all():
                reason = "calibration_fit_failed"
            else:
                slope = float(fitted.x[1])
    passed = bool(
        slope is not None and model_brier < base_brier and slope_min <= slope <= slope_max
    )
    return {
        "observation_count": len(y),
        "positive_label_count": positive_count,
        "negative_label_count": negative_count,
        "minimum_observation_count": minimum_observation_count,
        "minimum_class_count": minimum_class_count,
        "model_brier_score": model_brier,
        "training_base_probability_brier_score": base_brier,
        "calibration_slope": slope,
        "calibration_failure_reason": reason,
        "joint_gate_pass": passed,
    }


def canonical_target_bytes(targets: pd.DataFrame) -> bytes:
    values = targets.sort_index().sort_index(axis=1).astype(float)
    rows = [
        {
            "execution_session": pd.Timestamp(session).date().isoformat(),
            "weights": {symbol: float(row[symbol]) for symbol in values.columns},
        }
        for session, row in values.iterrows()
    ]
    return _canonical_json_bytes(rows)


def canonical_target_hash(targets: pd.DataFrame) -> str:
    return hashlib.sha256(canonical_target_bytes(targets)).hexdigest()


def _strict_numeric_panel(frame: pd.DataFrame, label: str, *, positive: bool) -> pd.DataFrame:
    values = frame.astype(float).copy()
    if values.empty or values.index.has_duplicates or not values.index.is_monotonic_increasing:
        raise ValueError(f"{label} must be nonempty with unique increasing sessions")
    if not np.isfinite(values.to_numpy()).all():
        raise ValueError(f"{label} must be finite")
    if positive and (values <= 0.0).any().any():
        raise ValueError(f"{label} must be positive")
    return values


def _weight_mapping(columns: pd.Index, values: np.ndarray) -> dict[str, float]:
    return {str(symbol): float(value) for symbol, value in zip(columns, values, strict=True)}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_ready(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON evidence cannot contain nonfinite numbers")
        return number
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def build_candidate_targets_for_segment(
    dataset: pd.DataFrame,
    *,
    segment_id: str,
    execution_start: str,
    execution_end: str,
    train_start_session: str,
    columns: pd.Index,
    specs: dict[str, StrategySpec],
    provenance: dict[str, str] | None = None,
) -> tuple[
    dict[str, pd.DataFrame],
    list[dict[str, Any]],
    list[dict[str, Any]],
    pd.DataFrame,
]:
    provenance = provenance or {}
    _validate_r5_spec_execution_contract(specs)
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
        raise ValueError(f"segment {segment_id} has no monthly prediction points")
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
            raise ValueError(f"rankable symbol coverage failed at {decision_session}")

        d01_symbols = _top_symbols(current, "raw_mom_252_skip21", TOP_N)
        d01 = _target_from_symbols(d01_symbols, columns)
        eligible_d02 = current[
            np.isfinite(current["raw_mom_126_skip21"])
            & np.isfinite(current["raw_trend_gap_252"])
            & (current["raw_trend_gap_252"] > 0.0)
        ]
        d02_symbols = _top_symbols(eligible_d02, "raw_mom_126_skip21", TOP_N)
        d02 = _target_from_symbols(d02_symbols, columns) if len(d02_symbols) == TOP_N else d01

        formula_values = current[list(FORMULA_FEATURES)].astype(float)
        formula_score = formula_values.mean(axis=1)
        if np.isfinite(formula_values.to_numpy()).all() and formula_score.nunique() > 1:
            l01_symbols = _top_symbols(
                current.assign(_formula_score=formula_score), "_formula_score"
            )
            l01 = _target_from_symbols(l01_symbols, columns)
            l01_fallback = None
        else:
            l01 = d01
            l01_fallback = "nonfinite_or_constant_formula_composite"

        m01_prediction, m01_record = _fit_predict_for_point(
            specs["R5M01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=R5_RUNTIME_PREDICTOR_CONTRACT["R5M01"],
            label_name=R5_MODEL_LABEL_CONTRACT["R5M01"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(m01_record)
        if m01_prediction is None:
            m01 = d01
            m01_symbols = d01_symbols
            m01_fallback = str(m01_record["failure_reason"])
            m01_scores = pd.Series(
                current["raw_mom_252_skip21"].to_numpy(dtype=float),
                index=current["symbol"],
            )
        else:
            m01_scores = pd.Series(m01_prediction, index=current["symbol"], dtype=float)
            m01_symbols = _top_symbols_from_series(m01_scores)
            m01 = _target_from_symbols(m01_symbols, columns)
            m01_fallback = None

        c01_prediction, c01_record = _fit_predict_for_point(
            specs["R5C01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=R5_RUNTIME_PREDICTOR_CONTRACT["R5C01"],
            label_name=R5_MODEL_LABEL_CONTRACT["R5C01"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(c01_record)
        if c01_prediction is None:
            c01 = m01
            c01_symbols = m01_symbols
            c01_fallback = str(c01_record["failure_reason"])
        else:
            c01_symbols = _top_symbols_from_series(
                pd.Series(c01_prediction, index=current["symbol"], dtype=float)
            )
            c01 = _target_from_symbols(c01_symbols, columns)
            c01_fallback = None

        p01_prediction, p01_record = _fit_predict_for_point(
            specs["R5P01"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=R5_RUNTIME_PREDICTOR_CONTRACT["R5P01"],
            label_name=R5_MODEL_LABEL_CONTRACT["R5P01"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(p01_record)
        if p01_prediction is None:
            p01 = m01
            p01_symbols = m01_symbols
            p01_fallback = str(p01_record["failure_reason"])
        else:
            p01_symbols = _top_symbols_from_series(
                pd.Series(p01_prediction, index=current["symbol"], dtype=float)
            )
            p01 = _target_from_symbols(p01_symbols, columns)
            p01_fallback = None

        m02_prediction, m02_record = _fit_predict_for_point(
            specs["R5M02"],
            dataset,
            current,
            decision_position=decision_position,
            train_start_session=train_start_session,
            feature_names=R5_RUNTIME_PREDICTOR_CONTRACT["R5M02"],
            label_name=R5_MODEL_LABEL_CONTRACT["R5M02"],
            segment_id=segment_id,
            provenance=provenance,
        )
        model_records.append(m02_record)
        if m02_prediction is None:
            m02 = m01
            m02_symbols = m01_symbols
            m02_fallback = str(m02_record["failure_reason"])
        else:
            survival = pd.Series(m02_prediction, index=current["symbol"], dtype=float)
            ranked = sorted(
                current["symbol"],
                key=lambda symbol: (-float(m01_scores[symbol]), str(symbol)),
            )
            threshold = specs["R5M02"].model.selection.threshold
            if threshold is None:
                raise ValueError("R5M02 survival threshold is missing")
            accepted = [symbol for symbol in ranked if float(survival[symbol]) >= float(threshold)][
                :TOP_N
            ]
            if len(accepted) < TOP_N:
                m02 = m01
                m02_symbols = m01_symbols
                m02_fallback = "fewer_than_three_survival_eligible_symbols"
            else:
                m02_symbols = accepted
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
                            "symbol": row["symbol"],
                            "label": int(row["path_survival_label"]),
                            "probability": float(probability),
                            "training_base_probability": base_probability,
                        }
                    )

        if m01_prediction is None:
            m02 = m01.copy()
            m02_symbols = list(m01_symbols)
            m02_fallback = "upstream_R5M01_fallback"

        candidate_rows = {
            "R5D01": (d01, d01_symbols, None),
            "R5D02": (d02, d02_symbols if len(d02_symbols) == TOP_N else d01_symbols, None),
            "R5M01": (m01, m01_symbols, m01_fallback),
            "R5M02": (m02, m02_symbols, m02_fallback),
            "R5L01": (l01, l01_symbols if l01_fallback is None else d01_symbols, l01_fallback),
            "R5C01": (c01, c01_symbols, c01_fallback),
            "R5F01": (m01.copy(), m01_symbols, "intentional_missing_modality_identity"),
            "R5P01": (p01, p01_symbols, p01_fallback),
        }
        target_index.append(pd.Timestamp(execution_session))
        for candidate_id, (target, selected_symbols, fallback_reason) in candidate_rows.items():
            targets[candidate_id].append(target)
            target_records.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "segment_id": segment_id,
                    "candidate_id": candidate_id,
                    "decision_session": decision_session,
                    "execution_session": execution_session,
                    "selected_symbols": list(map(str, selected_symbols)),
                    "weights": {symbol: float(target[symbol]) for symbol in columns},
                    "target_sha256": hashlib.sha256(
                        _canonical_json_bytes(
                            {symbol: float(target[symbol]) for symbol in sorted(columns)}
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
    if canonical_target_bytes(frames["R5F01"]) != canonical_target_bytes(frames["R5M01"]):
        raise ValueError("R5F01 target identity with R5M01 failed")
    return frames, target_records, model_records, pd.DataFrame(calibration_rows)


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
        raise ValueError(f"model config missing for {spec.name}")
    candidate_id = str(spec.notes.model_dump(mode="json").get("candidate_id") or "")
    expected_model = R5_MODEL_SPEC_CONTRACT.get(candidate_id)
    if expected_model is None or spec.model.model_dump(mode="json") != expected_model:
        raise ValueError(f"R5 immutable model contract mismatch for {candidate_id or spec.name}")
    train = training_rows_for_prediction(
        dataset,
        decision_position=decision_position,
        train_start_session=train_start_session,
        feature_names=feature_names,
        label_name=label_name,
    )
    train_predictors = _validated_predictor_frame(
        train,
        candidate_id=candidate_id,
        feature_names=feature_names,
        label_name=label_name,
    )
    current_predictors = _validated_predictor_frame(
        current,
        candidate_id=candidate_id,
        feature_names=feature_names,
        label_name=label_name,
    )
    decision_session = str(current["decision_session"].iloc[0])
    base_record: dict[str, Any] = {
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
        "training_decision_start": (
            str(train["decision_session"].min()) if not train.empty else None
        ),
        "training_decision_end": str(train["decision_session"].max()) if not train.empty else None,
        "training_label_terminal_end": (
            str(train["label_end_session"].max()) if not train.empty else None
        ),
        "training_data_sha256": _frame_sha256(train, [*feature_names, label_name]),
        "prediction_feature_sha256": _frame_sha256(current_predictors, list(feature_names)),
        "model_config": spec.model.model_dump(mode="json"),
        "data_manifest_sha256": provenance.get("data_manifest_sha256"),
        "feature_contract_sha256": provenance.get("feature_contract_sha256"),
        "label_contract_sha256": provenance.get("label_contract_sha256"),
        "prompt_hash": provenance.get("prompt_hash"),
        "training_label_mean": (
            float(pd.to_numeric(train[label_name], errors="raise").mean())
            if not train.empty
            else None
        ),
    }
    minimum_rows = max(80, 2 * int(spec.model.hyperparameters.get("min_child_samples", 1)))
    failure_reason: str | None = None
    if len(train) < minimum_rows:
        failure_reason = "insufficient_training_rows"
    elif spec.model.kind == "lightgbm_classifier" and train[label_name].nunique() < 2:
        failure_reason = "single_class_training_labels"
    current_values = current_predictors.replace([np.inf, -np.inf], np.nan)
    if current_values.isna().any().any():
        failure_reason = "nonfinite_prediction_features"

    model = _make_estimator(spec)
    resolved_model_params = _json_ready(model.get_params(deep=True))
    prediction: np.ndarray | None = None
    fitted_model_sha256: str | None = None
    if failure_reason is None:
        try:
            model.fit(train_predictors, train[label_name])
            if spec.model.kind == "lightgbm_classifier":
                prediction = np.asarray(model.predict_proba(current_values)[:, 1], dtype=float)
            else:
                prediction = np.asarray(model.predict(current_values), dtype=float)
            if prediction.shape != (len(current),) or not np.isfinite(prediction).all():
                raise ValueError("model prediction is nonfinite or misaligned")
            booster = getattr(model, "booster_", None)
            if booster is None:
                raise ValueError("fitted LightGBM model is missing booster state")
            fitted_model_sha256 = hashlib.sha256(
                booster.model_to_string().encode("utf-8")
            ).hexdigest()
        except Exception as exc:  # Model failure is evidence and invokes the frozen fallback.
            failure_reason = f"model_fit_or_prediction_failed:{type(exc).__name__}:{exc}"
            prediction = None

    model_identity = {
        "spec_hash": base_record["spec_hash"],
        "decision_session": decision_session,
        "training_data_sha256": base_record["training_data_sha256"],
        "prediction_feature_sha256": base_record["prediction_feature_sha256"],
        "model_config": base_record["model_config"],
        "resolved_model_params": resolved_model_params,
    }
    record = {
        **base_record,
        "model_id": hashlib.sha256(_canonical_json_bytes(model_identity)).hexdigest(),
        "status": "fit_complete" if prediction is not None else "fallback_applied",
        "failure_reason": failure_reason,
        "resolved_model_class": type(model).__name__,
        "resolved_model_params": resolved_model_params,
        "fitted_model_sha256": fitted_model_sha256,
        "predictions": (
            [
                {"symbol": str(symbol), "value": float(value)}
                for symbol, value in zip(current["symbol"], prediction, strict=True)
            ]
            if prediction is not None
            else []
        ),
        "prediction_sha256": (
            hashlib.sha256(np.asarray(prediction, dtype="<f8").tobytes()).hexdigest()
            if prediction is not None
            else None
        ),
    }
    return prediction, record


def _make_estimator(spec: StrategySpec) -> Any:
    if spec.model is None:
        raise ValueError("model config is required")
    params = dict(spec.model.hyperparameters)
    params["random_state"] = int(spec.model.training.seed)
    params["deterministic"] = True
    params["force_col_wise"] = True
    if spec.model.kind == "lightgbm_regressor":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(**params)
    if spec.model.kind == "lightgbm_classifier":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(**params)
    raise ValueError(f"unsupported model kind: {spec.model.kind}")


def _top_symbols(frame: pd.DataFrame, score_column: str, count: int = TOP_N) -> list[str]:
    values = frame[["symbol", score_column]].replace([np.inf, -np.inf], np.nan).dropna()
    return [
        str(symbol)
        for symbol in sorted(
            values["symbol"],
            key=lambda item: (
                -float(values.loc[values["symbol"] == item, score_column].iloc[0]),
                str(item),
            ),
        )[:count]
    ]


def _top_symbols_from_series(scores: pd.Series, count: int = TOP_N) -> list[str]:
    if not np.isfinite(scores.to_numpy(dtype=float)).all():
        raise ValueError("ranking scores must be finite")
    return [
        str(symbol)
        for symbol in sorted(scores.index, key=lambda item: (-float(scores[item]), str(item)))[
            :count
        ]
    ]


def _target_from_symbols(symbols: list[str], columns: pd.Index) -> pd.Series:
    selected = list(dict.fromkeys(map(str, symbols)))[:TOP_N]
    target = pd.Series(0.0, index=columns, dtype=float)
    for symbol in selected:
        if symbol not in target.index or symbol == RESERVE_SYMBOL:
            raise ValueError(f"invalid selected risk symbol: {symbol}")
        target[symbol] = 1.0 / TOP_N
    target[RESERVE_SYMBOL] = 1.0 - float(target.sum())
    if abs(float(target.sum()) - 1.0) > 1e-12:
        raise ValueError("target weights do not sum to one")
    return target


def _frame_sha256(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return hashlib.sha256(b"").hexdigest()
    identity = [
        column
        for column in ["decision_position", "decision_session", "symbol", *columns]
        if column in frame.columns
    ]
    ordered = frame[identity].sort_values(
        [column for column in ["decision_position", "symbol"] if column in identity]
    )
    raw = ordered.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.17g",
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_r5_panel(
    root: Path,
    manifest_path: Path,
    *,
    expected_manifest_sha256: str | None = None,
) -> PanelData:
    locked_manifest = _load_json(
        manifest_path,
        expected_sha256=expected_manifest_sha256,
    )
    verified_manifest = verify_alpaca_contract_snapshot(root, manifest_path)
    if _canonical_json_bytes(verified_manifest) != _canonical_json_bytes(locked_manifest):
        raise AlpacaDataError("R5 manifest changed during snapshot verification")
    manifest = locked_manifest
    items = manifest.get("items")
    if not isinstance(items, list) or len(items) != 14:
        raise AlpacaDataError("R5 daily manifest must contain exactly 14 items")
    fields: dict[str, dict[str, pd.Series]] = {
        name: {} for name in ["open", "high", "low", "close", "volume"]
    }
    expected_sessions: list[str] | None = None
    for item in items:
        if (
            not isinstance(item, dict)
            or item.get("timeframe") != "daily"
            or item.get("feed") != "sip"
            or item.get("adjustment") != "all"
            or item.get("session_scope") != "regular"
        ):
            raise AlpacaDataError("R5 daily manifest item identity mismatch")
        symbol = str(item.get("symbol") or "")
        if symbol not in {*RANKABLE_SYMBOLS, RESERVE_SYMBOL}:
            raise AlpacaDataError(f"unexpected R5 daily symbol: {symbol}")
        path = manifest_path.parent / str(item.get("output_path") or "")
        raw = _read_regular_file_bytes(path)
        expected_sha256 = str(item.get("output_sha256") or "")
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise AlpacaDataError(f"R5 parsed CSV bytes differ from manifest for {symbol}")
        frame = pd.read_csv(io.BytesIO(raw))
        parsed = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        sessions = pd.DatetimeIndex(
            parsed.dt.tz_convert(NEW_YORK).dt.tz_localize(None).dt.normalize()
        )
        if sessions.has_duplicates or not sessions.is_monotonic_increasing:
            raise AlpacaDataError(f"R5 daily sessions invalid for {symbol}")
        quality_sessions = item.get("quality", {}).get("complete_sessions")
        if not isinstance(quality_sessions, list):
            raise AlpacaDataError(f"R5 complete-session evidence missing for {symbol}")
        actual_sessions = _validate_complete_session_contract(
            sessions,
            quality_sessions,
            symbol=symbol,
        )
        if expected_sessions is None:
            expected_sessions = actual_sessions
        elif actual_sessions != expected_sessions:
            raise AlpacaDataError("R5 daily complete-session lists differ")
        for field in fields:
            values = pd.to_numeric(frame[field], errors="raise").to_numpy(dtype=float)
            fields[field][symbol] = pd.Series(values, index=sessions)

    panels = {field: pd.DataFrame(series).sort_index(axis=1) for field, series in fields.items()}
    expected_columns = sorted([*RANKABLE_SYMBOLS, RESERVE_SYMBOL])
    for field, panel in panels.items():
        if list(panel.columns) != expected_columns or panel.isna().any().any():
            raise AlpacaDataError(f"R5 {field} panel is incomplete")
        if not np.isfinite(panel.to_numpy()).all():
            raise AlpacaDataError(f"R5 {field} panel contains nonfinite values")
    for field in ["open", "high", "low", "close"]:
        if (panels[field] <= 0.0).any().any():
            raise AlpacaDataError(f"R5 {field} panel contains nonpositive values")
    if (panels["volume"] < 0.0).any().any():
        raise AlpacaDataError("R5 volume panel contains negative values")
    return PanelData(
        open=panels["open"],
        high=panels["high"],
        low=panels["low"],
        close=panels["close"],
        volume=panels["volume"],
        manifest=manifest,
    )


def _validate_complete_session_contract(
    sessions: pd.DatetimeIndex,
    quality_sessions: list[Any],
    *,
    symbol: str,
) -> list[str]:
    if sessions.empty:
        raise AlpacaDataError(f"R5 parsed CSV has no complete sessions for {symbol}")
    actual = [session.date().isoformat() for session in sessions]
    declared = [str(value) for value in quality_sessions]
    if declared != actual:
        raise AlpacaDataError(f"R5 complete-session evidence differs from parsed CSV for {symbol}")
    expected: list[str] = []
    current = sessions[0].date()
    end = sessions[-1].date()
    while current <= end:
        if us_equity_session_close(current) is not None:
            expected.append(current.isoformat())
        current += timedelta(days=1)
    if actual != expected:
        raise AlpacaDataError(f"R5 parsed CSV omits an exchange session for {symbol}")
    return actual


def _r5_harness_candidate_paths(spec: StrategySpec) -> dict[str, Path]:
    strategy_name = spec.name
    return {
        "plan_json": Path(f"reports/harness/plans/{strategy_name}.json"),
        "plan_markdown": Path(f"reports/harness/plans/{strategy_name}.md"),
        "execution_policy": Path(
            f"reports/harness/execution/{strategy_name}-execution-policy.json"
        ),
        "execution_reality": Path(
            f"reports/harness/execution/{strategy_name}-execution-reality.json"
        ),
        "execution_reality_markdown": Path(
            f"reports/harness/execution/{strategy_name}-execution-reality.md"
        ),
        "source_cards": Path(f"reports/harness/source_cards/{strategy_name}.jsonl"),
        "verify_receipt": Path(f"reports/harness/verify/{strategy_name}.json"),
    }


def _r5_harness_relative_paths(specs: dict[str, StrategySpec]) -> list[str]:
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R5 harness spec set is incomplete")
    relatives = [path.as_posix() for path in R5_HARNESS_CONFIG_PATHS.values()]
    for candidate_id, spec_path in SPEC_PATHS.items():
        spec = specs[candidate_id]
        if spec.name != spec_path.stem:
            raise ValueError(f"R5 harness strategy identity mismatch: {candidate_id}")
        relatives.extend(path.as_posix() for path in _r5_harness_candidate_paths(spec).values())
    if len(relatives) != len(set(relatives)):
        raise ValueError("R5 harness evidence path inventory contains duplicates")
    return relatives


def _validate_r5_harness_evidence(
    root: Path,
    specs: dict[str, StrategySpec],
    *,
    locked_artifact_sha256_by_path: dict[str, str] | None = None,
) -> dict[str, Any]:
    base = root.resolve()
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R5 harness spec set must contain exactly eight candidates")

    def bound_bytes(relative: Path) -> tuple[bytes, dict[str, Any]]:
        relative_text = relative.as_posix()
        expected_sha256 = None
        if locked_artifact_sha256_by_path is not None:
            expected_sha256 = locked_artifact_sha256_by_path.get(relative_text)
            if expected_sha256 is None:
                raise ValueError(f"R5 harness artifact is absent from lock: {relative_text}")
        path = _repo_file_path(base, relative_text)
        try:
            content = _read_regular_file_bytes(path, expected_sha256=expected_sha256)
        except OSError as exc:
            raise ValueError(
                f"R5 harness artifact is missing or unreadable: {relative_text}"
            ) from exc
        return content, {
            "path": relative_text,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    def json_object(relative: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        content, binding = bound_bytes(relative)
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"R5 harness JSON is invalid: {relative.as_posix()}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"R5 harness JSON must be an object: {relative.as_posix()}")
        return payload, binding

    contract_bindings: dict[str, dict[str, Any]] = {}
    for name, relative in R5_HARNESS_CONFIG_PATHS.items():
        _, contract_bindings[name] = bound_bytes(relative)

    candidate_results: dict[str, dict[str, Any]] = {}
    for candidate_id, spec_path in SPEC_PATHS.items():
        spec = specs[candidate_id]
        if spec.name != spec_path.stem:
            raise ValueError(f"R5 harness strategy name differs from spec path: {candidate_id}")
        spec_file_sha256 = _sha256_file(base / spec_path)
        spec_semantic_sha256 = strategy_content_hash(spec)
        active_domains = detect_risk_domains(spec, base)
        required_artifacts = sorted(required_artifacts_for_domains(active_domains))
        required_skills = sorted(required_skills_for_domains(active_domains))
        blocking_rules = blocking_rules_for_domains(active_domains)
        if active_domains != ["daily_open_execution"]:
            raise ValueError(f"R5 harness risk-domain drift: {candidate_id}:{active_domains}")
        if required_artifacts != [
            "execution_policy",
            "execution_reality_report",
            "source_cards",
        ]:
            raise ValueError(f"R5 harness required-artifact drift: {candidate_id}")
        if required_skills != ["execution-reality-reviewer", "source-researcher"]:
            raise ValueError(f"R5 harness required-skill drift: {candidate_id}")

        paths = _r5_harness_candidate_paths(spec)
        plan, plan_binding = json_object(paths["plan_json"])
        expected_plan = {
            "schema_version": 2,
            "plan_contract": "harness_plan_v2",
            "strategy_name": spec.name,
            "spec_path": spec_path.as_posix(),
            "spec_file_sha256": spec_file_sha256,
            "spec_semantic_sha256": spec_semantic_sha256,
            "risk_domains": active_domains,
            "required_skills": required_skills,
            "required_artifacts": required_artifacts,
            "blocking_rules": [
                {
                    "domain": rule.domain_id,
                    "rule_id": rule.rule_id,
                    "blocks": rule.blocks,
                    "description": rule.description,
                }
                for rule in blocking_rules
            ],
        }
        if plan != expected_plan:
            raise ValueError(f"R5 harness plan is stale or noncanonical: {candidate_id}")
        plan_markdown_bytes, plan_markdown_binding = bound_bytes(paths["plan_markdown"])
        try:
            plan_markdown = plan_markdown_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"R5 harness plan Markdown is invalid: {candidate_id}") from exc
        required_plan_markers = [
            spec.name,
            *active_domains,
            *required_skills,
            *required_artifacts,
            *(rule.rule_id for rule in blocking_rules),
        ]
        if any(marker not in plan_markdown for marker in required_plan_markers):
            raise ValueError(f"R5 harness plan Markdown is incomplete: {candidate_id}")

        policy_payload, policy_binding = json_object(paths["execution_policy"])
        policy = spec.execution_policy
        reality_model = spec.reality_model
        if policy is None or reality_model is None:
            raise ValueError(f"R5 harness inline execution contracts are missing: {candidate_id}")
        policy_model = policy.model_dump(mode="json")
        for field in ("historical_execution_contract", "future_order_contract"):
            if field not in policy.model_fields_set:
                policy_model.pop(field, None)
        inline_policy_sha256 = hashlib.sha256(
            json.dumps(policy_model, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        protection = policy.price_protection.model_dump(mode="json")
        fallback = policy.fallback_behavior.model_dump(mode="json")
        tca = policy.tca.model_dump(mode="json")
        expected_policy_fields = {
            "strategy_name": spec.name,
            "policy_id": policy.policy_id,
            "generated_from_inline_strategy_spec": True,
            "inline_policy_sha256": inline_policy_sha256,
            "order_style": policy.order_style,
            "time_in_force": policy.time_in_force,
            "price_protection": {
                "type": "none" if all(value is None for value in protection.values()) else "limit",
                **protection,
            },
            "gap_filter": {
                "enabled": protection["max_open_gap_pct"] is not None,
                "max_open_gap_pct": protection["max_open_gap_pct"],
                "action_on_exceed": fallback["if_gap_exceeds_limit"],
            },
            "spread_filter": {
                "enabled": protection["max_spread_bps"] is not None,
                "max_spread_bps": protection["max_spread_bps"],
                "action_on_exceed": fallback["if_spread_exceeds_limit"],
            },
            "participation_cap": policy.participation_cap.model_dump(mode="json"),
            "fallback_behavior": fallback,
            "tca_plan": {
                "enabled": tca["enabled"],
                "reference_prices": tca["compare_to"],
                "record_submitted_at": tca["record_submitted_at"],
                "record_fill_price": tca["record_fill_price"],
                "record_slippage_vs_reference": bool(
                    tca["record_fill_price"] and tca["compare_to"]
                ),
                "review_frequency": tca["review_frequency"],
            },
            "source_card_ids": list(policy.source_card_ids),
            "alternatives_compared": list(policy.alternatives_compared),
            "naked_market_justification": policy.naked_market_justification,
        }
        if any(policy_payload.get(key) != value for key, value in expected_policy_fields.items()):
            raise ValueError(f"R5 harness execution policy differs from spec: {candidate_id}")
        alternatives = list(policy_payload.get("alternatives_compared") or [])
        if (
            len(alternatives) < 2
            or len(alternatives) != len(set(alternatives))
            or policy.order_style not in alternatives
        ):
            raise ValueError(f"R5 harness execution alternatives are insufficient: {candidate_id}")
        generated_at_raw = policy_payload.get("generated_at")
        try:
            generated_at = date.fromisoformat(str(generated_at_raw))
        except ValueError as exc:
            raise ValueError(f"R5 harness policy date is invalid: {candidate_id}") from exc
        if generated_at > datetime.now(UTC).date():
            raise ValueError(f"R5 harness policy is future-dated: {candidate_id}")

        reality_payload, reality_binding = json_object(paths["execution_reality"])
        scenarios = [item.model_dump(mode="json") for item in reality_model.stress_scenarios]
        scenario_costs = {
            str(row.get("name")): float(row.get("slippage_bps", math.nan)) for row in scenarios
        }
        if scenario_costs != {
            "primary": PRIMARY_COST_BPS,
            "stress": STRESS_COST_BPS,
            "severe_report_only": SEVERE_COST_BPS,
        }:
            raise ValueError(f"R5 harness stress costs differ from frozen costs: {candidate_id}")
        expected_reality_fields = {
            "strategy_name": spec.name,
            "policy_id": policy.policy_id,
            "generated_at": generated_at_raw,
            "generated_from_inline_strategy_spec": True,
            "slippage_scenarios": scenarios,
            "gap_stress": {
                "max_adverse_gap_pct": policy.price_protection.max_open_gap_pct,
                "fill_model_gap_handling": reality_model.fill_model,
                "recommended_gap_filter": (
                    f"{policy.fallback_behavior.if_gap_exceeds_limit} when abs(gap_pct) > "
                    f"{policy.price_protection.max_open_gap_pct}"
                ),
                "scenarios": scenarios,
            },
            "tca_reference_prices": list(policy.tca.compare_to),
            "fill_model": reality_model.fill_model,
        }
        if any(reality_payload.get(key) != value for key, value in expected_reality_fields.items()):
            raise ValueError(f"R5 harness execution reality differs from spec: {candidate_id}")
        capacity = reality_payload.get("capacity_assessment")
        if (
            not isinstance(capacity, dict)
            or capacity.get("max_position_weight") != spec.risk.max_position_weight
            or capacity.get("max_trades_per_day") != spec.risk.max_trades_per_day
            or "ADV" not in str(capacity.get("notes") or "")
            or "paper_auto" not in str(capacity.get("notes") or "")
        ):
            raise ValueError(f"R5 harness capacity caveat is incomplete: {candidate_id}")
        reality_markdown_bytes, reality_markdown_binding = bound_bytes(
            paths["execution_reality_markdown"]
        )
        try:
            reality_markdown = reality_markdown_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"R5 harness execution Markdown is invalid: {candidate_id}") from exc
        required_reality_markers = [
            spec.name,
            policy.order_style,
            *policy.alternatives_compared,
            "deterministic defaults",
            "placeholder",
            "before paper_auto activation",
        ]
        if any(marker not in reality_markdown for marker in required_reality_markers):
            raise ValueError(f"R5 harness execution caveats are incomplete: {candidate_id}")

        source_bytes, source_binding = bound_bytes(paths["source_cards"])
        try:
            source_rows = [
                json.loads(line)
                for line in source_bytes.decode("utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"R5 harness source cards are invalid: {candidate_id}") from exc
        if not source_rows or any(not isinstance(row, dict) for row in source_rows):
            raise ValueError(f"R5 harness source cards are empty: {candidate_id}")
        source_by_id = {str(row.get("claim_id") or ""): row for row in source_rows}
        if len(source_by_id) != len(source_rows) or "" in source_by_id:
            raise ValueError(f"R5 harness source claim IDs are invalid: {candidate_id}")
        required_source_fields = {
            "claim_id",
            "claim",
            "source_url",
            "source_type",
            "accessed_at",
            "applies_to",
            "impact_on_spec",
            "limitations",
        }
        for claim_id, row in source_by_id.items():
            if any(row.get(field_name) in (None, "") for field_name in required_source_fields):
                raise ValueError(f"R5 harness source card is incomplete: {candidate_id}:{claim_id}")
            if row.get("iteration_id") != ITER_ID or row.get("verification_status") != (
                "source_verified"
            ):
                raise ValueError(
                    f"R5 harness source verification is invalid: {candidate_id}:{claim_id}"
                )
            if not str(row.get("source_url") or "").startswith("https://"):
                raise ValueError(f"R5 harness source URL is invalid: {candidate_id}:{claim_id}")
            try:
                accessed_at = date.fromisoformat(str(row["accessed_at"]))
            except ValueError as exc:
                raise ValueError(
                    f"R5 harness source access date is invalid: {candidate_id}:{claim_id}"
                ) from exc
            if accessed_at > generated_at or accessed_at > datetime.now(UTC).date():
                raise ValueError(
                    f"R5 harness source is future/stale-bound: {candidate_id}:{claim_id}"
                )
        candidate_claim_id = f"{spec.name}:source-research"
        if candidate_claim_id not in source_by_id:
            raise ValueError(f"R5 harness candidate source summary is missing: {candidate_id}")
        for source_card_id in policy.source_card_ids:
            row = source_by_id.get(source_card_id)
            if not isinstance(row, dict) or not set(row.get("applies_to") or []).intersection(
                {"daily_open_execution", "opg_orders", "paper_execution"}
            ):
                raise ValueError(
                    "R5 harness execution source is not applicable: "
                    f"{candidate_id}:{source_card_id}"
                )

        independent_statuses = {
            artifact_name: check_artifact(artifact_name, spec.name, base)
            for artifact_name in required_artifacts
        }
        failed_artifacts = [
            name
            for name, status in independent_statuses.items()
            if not status.present or not status.schema_ok
        ]
        if failed_artifacts:
            raise ValueError(
                f"R5 harness artifact contract failed: {candidate_id}:{failed_artifacts}"
            )
        artifact_bindings = {
            "execution_policy": policy_binding,
            "execution_reality_report": reality_binding,
            "source_cards": source_binding,
        }

        verify_payload, verify_binding = json_object(paths["verify_receipt"])
        expected_verify_artifacts = [
            {
                "name": artifact_name,
                "present": True,
                "schema_ok": True,
                "missing_fields": [],
                "path": artifact_path(artifact_name, spec.name).as_posix(),
                "binding": artifact_bindings[artifact_name],
            }
            for artifact_name in required_artifacts
        ]
        expected_verify_fields = {
            "schema_version": 2,
            "verification_contract": "harness_verify_v2",
            "strategy_name": spec.name,
            "spec_path": spec_path.as_posix(),
            "spec_file_sha256": spec_file_sha256,
            "spec_semantic_sha256": spec_semantic_sha256,
            "stage": "research",
            "risk_domains": active_domains,
            "required_artifacts": required_artifacts,
            "plan_binding": plan_binding,
            "config_bindings": {
                "risk_domains": contract_bindings["risk_domains"],
                "artifact_contracts": contract_bindings["artifact_contracts"],
            },
            "artifacts": expected_verify_artifacts,
            "overall": "ok",
        }
        if verify_payload != expected_verify_fields:
            raise ValueError(f"R5 harness verify receipt is stale or self-asserted: {candidate_id}")

        candidate_results[candidate_id] = {
            "candidate_id": candidate_id,
            "strategy_name": spec.name,
            "spec_path": spec_path.as_posix(),
            "spec_file_sha256": spec_file_sha256,
            "spec_semantic_sha256": spec_semantic_sha256,
            "risk_domains": active_domains,
            "required_skills": required_skills,
            "required_artifacts": required_artifacts,
            "blocking_rule_ids": [rule.rule_id for rule in blocking_rules],
            "structural_research_harness_pass": True,
            "empirical_execution_evidence_pass": False,
            "paper_readiness_evidence_pass": False,
            "bindings": {
                "plan_json": plan_binding,
                "plan_markdown": plan_markdown_binding,
                "execution_policy": policy_binding,
                "execution_reality": reality_binding,
                "execution_reality_markdown": reality_markdown_binding,
                "source_cards": source_binding,
                "verify_receipt": verify_binding,
            },
        }

    return {
        "schema_version": 1,
        "reconciliation_contract": R5_HARNESS_RECONCILIATION_CONTRACT,
        "iter_id": ITER_ID,
        "stage": "research",
        "evidence_scope": (
            "spec_bound_execution_policy_source_research_and_deterministic_stress_contract_only"
        ),
        "candidate_count": len(candidate_results),
        "contract_bindings": contract_bindings,
        "candidates": candidate_results,
        "research_gate_pass": all(
            row["structural_research_harness_pass"] for row in candidate_results.values()
        ),
        "empirical_execution_evidence_pass": False,
        "paper_readiness_evidence_pass": False,
        "limitations": [
            "generated execution-reality artifacts contain deterministic scenarios "
            "and placeholders",
            "historical stress assumptions do not attest OPG fills, queue priority, "
            "spread, or capacity",
            "matched Alpaca Paper TCA remains mandatory before any Paper-readiness claim",
        ],
    }


def _validate_r5_runtime_contracts(
    output: Path,
    *,
    root: Path | None = None,
    locked_artifact_sha256_by_path: dict[str, str] | None = None,
) -> dict[str, Any]:
    base = root.resolve() if root is not None else None
    contracts: dict[str, dict[str, Any]] = {}
    for name, filename in R5_RUNTIME_CONTRACT_FILENAMES.items():
        path = output / filename
        expected_sha256 = None
        if locked_artifact_sha256_by_path is not None:
            if base is None:
                raise ValueError("R5 locked runtime contracts require a repository root")
            relative = _relpath(path, base)
            expected_sha256 = locked_artifact_sha256_by_path.get(relative)
            if expected_sha256 is None:
                raise ValueError(f"R5 runtime contract is absent from lock: {relative}")
        contracts[name] = _load_json(path, expected_sha256=expected_sha256)
    failures: list[str] = []

    def require_equal(name: str, actual: Any, expected: Any) -> None:
        if isinstance(expected, bool):
            matched = actual is expected
        else:
            matched = actual == expected and not (
                isinstance(expected, int) and isinstance(actual, bool)
            )
        if not matched:
            failures.append(name)

    for name, contract in contracts.items():
        if contract.get("iter_id") != ITER_ID:
            failures.append(f"{name}.iter_id")

    manifest = contracts["candidate_manifest"]
    manifest_rows = manifest.get("candidates")
    manifest_ids = (
        [str(row.get("candidate_id") or "") for row in manifest_rows]
        if isinstance(manifest_rows, list) and all(isinstance(row, dict) for row in manifest_rows)
        else []
    )
    if int(manifest.get("candidate_count") or -1) != len(SPEC_PATHS):
        failures.append("candidate_manifest.candidate_count")
    if manifest_ids != list(SPEC_PATHS):
        failures.append("candidate_manifest.candidate_ids")
    if manifest_ids == list(SPEC_PATHS):
        for row in manifest_rows:
            candidate_id = str(row["candidate_id"])
            if row != R5_CANDIDATE_ROLE_CONTRACT[candidate_id]:
                failures.append(f"candidate_manifest.immutable_role_contract.{candidate_id}")

    trial = contracts["cumulative_trial"]
    trial_count = int(trial.get("dsr_trial_count") or -1)
    trial_lower_bound = int(trial.get("cumulative_trial_count_lower_bound") or -1)
    sensitivity_trial_counts = list(map(int, trial.get("dsr_sensitivity_trial_counts") or []))
    require_equal(
        "cumulative_trial.count_status",
        trial.get("count_status"),
        "known_lower_bound_with_preregistered_governance_stress",
    )
    require_equal("cumulative_trial.prior_lower_bound", trial.get("prior_lower_bound"), 8007)
    require_equal(
        "cumulative_trial.current_frozen_candidates",
        trial.get("current_frozen_candidates"),
        len(SPEC_PATHS),
    )
    require_equal("cumulative_trial.lower_bound", trial_lower_bound, 8015)
    require_equal("cumulative_trial.dsr_trial_count", trial_count, 100000)
    require_equal(
        "cumulative_trial.uncertainty_multiplier",
        trial.get("unrecorded_trial_uncertainty_multiplier"),
        12.5,
    )
    require_equal(
        "cumulative_trial.uncertainty_allowance",
        trial.get("unrecorded_trial_governance_allowance"),
        trial_count - trial_lower_bound,
    )
    require_equal(
        "cumulative_trial.sensitivity_trial_counts",
        sensitivity_trial_counts,
        [8015, 10000, 50000, 100000],
    )
    source_bindings = trial.get("source_bindings")
    if not isinstance(source_bindings, list) or len(source_bindings) != 3:
        failures.append("cumulative_trial.source_bindings")
    elif root is not None:
        base = root.resolve()
        for index, binding in enumerate(source_bindings):
            if not isinstance(binding, dict):
                failures.append(f"cumulative_trial.source_bindings.{index}")
                continue
            relative = Path(str(binding.get("path") or ""))
            candidate = base / relative
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(base)
            except (FileNotFoundError, ValueError, OSError):
                failures.append(f"cumulative_trial.source_bindings.{index}.path")
                continue
            if candidate.is_symlink() or not resolved.is_file():
                failures.append(f"cumulative_trial.source_bindings.{index}.regular_file")
                continue
            if _sha256_file(resolved) != binding.get("sha256"):
                failures.append(f"cumulative_trial.source_bindings.{index}.sha256")

    validation = contracts["validation"]
    expected_folds = [
        {
            "fold_id": "F1",
            "train_start": "2018-02-01",
            "train_end": "2020-12-31",
            "test_start": "2021-01-04",
            "test_end": "2021-12-31",
        },
        {
            "fold_id": "F2",
            "train_start": "2018-02-01",
            "train_end": "2021-12-31",
            "test_start": "2022-01-03",
            "test_end": "2022-12-30",
        },
        {
            "fold_id": "F3",
            "train_start": "2018-02-01",
            "train_end": "2022-12-30",
            "test_start": "2023-01-03",
            "test_end": "2023-12-29",
        },
        {
            "fold_id": "F4",
            "train_start": "2018-02-01",
            "train_end": "2023-12-29",
            "test_start": "2024-01-02",
            "test_end": "2024-12-31",
        },
    ]
    require_equal("validation.folds", validation.get("folds"), expected_folds)
    pbo = validation.get("pbo")
    if not isinstance(pbo, dict):
        failures.append("validation.pbo")
        pbo = {}
    block_count = int(pbo.get("block_count") or -1)
    in_sample_block_count = int(pbo.get("in_sample_block_count") or -1)
    expected_partition_count = int(pbo.get("expected_partition_count") or -1)
    if not (1 <= in_sample_block_count < block_count):
        failures.append("validation.pbo.block_counts")
    elif math.comb(block_count, in_sample_block_count) != expected_partition_count:
        failures.append("validation.pbo.expected_partition_count")
    if int(pbo.get("minimum_valid_partition_count") or -1) != expected_partition_count:
        failures.append("validation.pbo.minimum_valid_partition_count")
    if list(pbo.get("block_ids") or []) != [f"B{index + 1:02d}" for index in range(block_count)]:
        failures.append("validation.pbo.block_ids")
    selection_ids = list(map(str, pbo.get("selection_candidate_ids") or []))
    diagnostic_ids = list(map(str, pbo.get("diagnostic_control_ids") or []))
    if selection_ids != list(map(str, trial.get("pbo_family_candidates") or [])):
        failures.append("pbo.selection_candidate_ids")
    if diagnostic_ids != list(map(str, trial.get("pbo_diagnostic_controls") or [])):
        failures.append("pbo.diagnostic_control_ids")
    if selection_ids + diagnostic_ids != list(SPEC_PATHS):
        failures.append("pbo.all_candidate_ids")
    pbo_expected = {
        "method": "combinatorially_symmetric_cross_validation",
        "return_source": "common_fold_test_daily_net_returns_primary_10bps",
        "source_start": "2021-01-04",
        "source_end": "2024-12-31",
        "return_interval_convention": (
            "open_to_open_net_return_indexed_by_interval_start_session_with_"
            "terminal_liquidation_cost_in_final_interval"
        ),
        "fold_boundary_accounting": (
            "each_outer_fold_starts_in_cash_at_test_start_open_and_liquidates_at_test_end_open"
        ),
        "expected_return_observation_count": 1001,
        "expected_block_observation_counts": [126, 125, 125, 125, 125, 125, 125, 125],
        "partition_enumeration": "all_directional_combinations",
        "evaluate_complementary_orientations": True,
        "selection_metric": "annualized_sharpe_zero_risk_free_sample_std",
        "selection_tie_break": "candidate_id_ascending",
        "shuffle": False,
        "scope_statement": (
            "candidate_selection_PBO_over_fully_specified_prequential_strategy_return_streams"
        ),
        "model_training_inside_PBO": False,
        "independent_ML_generalization_validation": False,
        "independent_formula_generation_validation": False,
        "selection_prohibited_controls_in_PBO": False,
    }
    for field_name, expected in pbo_expected.items():
        require_equal(f"validation.pbo.{field_name}", pbo.get(field_name), expected)

    dsr_contract = validation.get("dsr")
    if not isinstance(dsr_contract, dict):
        failures.append("validation.dsr")
        dsr_contract = {}
    dsr_expected = {
        "estimator_id": (
            "bailey_lopez_de_prado_expected_max_normal_with_bartlett_effective_sessions_v2"
        ),
        "hac_overlay_id": "bartlett_newey_west_effective_session_haircut_v1",
        "hac_lag": 21,
        "hac_kernel": "bartlett_weight_1_minus_k_div_lag_plus_1",
        "hac_autocovariance_mean": "global_return_mean",
        "hac_autocovariance_divisor": "full_session_count_n",
        "hac_fold_boundary_policy": "exclude_cross_scope_lag_pairs",
        "hac_inflation_formula": ("max_1_and_1_plus_2_times_sum_bartlett_weight_times_rho_k"),
        "effective_session_formula": "min_n_and_n_div_hac_inflation",
        "promotion_probability_rule": ("minimum_of_iid_and_hac_effective_session_probabilities"),
        "legacy_probability_field": "exact_alias_of_promotion_probability",
        "skew_estimator": "bias_corrected_fisher_pearson_sample_skew",
        "kurtosis_estimator": "bias_corrected_fisher_excess_plus_3_pearson",
        "candidate_return_source": (
            "stitched_2021_2024_outer_fold_daily_net_returns_primary_10bps"
        ),
        "risk_free_return": 0.0,
        "sample_std_ddof": 1,
        "annualization_sessions": 252,
        "known_trial_count_lower_bound": trial_lower_bound,
        "promotion_governance_trial_count": trial_count,
        "sensitivity_trial_counts": sensitivity_trial_counts,
        "promotion_uses_largest_preregistered_trial_count": True,
        "expected_return_observation_count": 1001,
        "return_interval_convention": "same_unrounded_stitched_open_to_open_rows_as_PBO",
        "use_unrounded_returns": True,
        "nonfinite_or_nonpositive_denominator_action": "fail_closed",
    }
    for field_name, expected in dsr_expected.items():
        require_equal(f"validation.dsr.{field_name}", dsr_contract.get(field_name), expected)
    if dsr_contract.get("expected_return_observation_count") != pbo.get(
        "expected_return_observation_count"
    ):
        failures.append("validation.dsr_pbo_observation_count")

    llm_bootstrap_contract = validation.get("llm_contribution_bootstrap")
    expected_llm_bootstrap_contract = _expected_llm_contribution_bootstrap_contract()
    if not isinstance(llm_bootstrap_contract, dict):
        failures.append("validation.llm_contribution_bootstrap")
        llm_bootstrap_contract = {}
    for field_name, expected in expected_llm_bootstrap_contract.items():
        require_equal(
            f"validation.llm_contribution_bootstrap.{field_name}",
            llm_bootstrap_contract.get(field_name),
            expected,
        )

    model_rules = validation.get("model_rules")
    expected_model_rules = {
        "fit_within_each_fold_only": True,
        "outer_fold_walk_forward_retraining": (
            "at_each_month_end_decision_using_only_labels_available_before_that_decision"
        ),
        "maximum_training_window_sessions": TRAINING_WINDOW_SESSIONS,
        "training_label_cutoff": (
            "label_terminal_session_at_least_21_sessions_before_prediction_decision"
        ),
        "pbo_model_refit_allowed": False,
        "feature_selection_after_fold_results": False,
        "warm_start_from_prior_failed_models": False,
        "fixed_hyperparameters": True,
        "fixed_seeds": True,
        "paired_return_ranker_seed": 4101,
        "path_survival_seed": 4102,
        "R5M01_R5C01_R5P01_model_contract_identical_except_features": True,
    }
    if not isinstance(model_rules, dict):
        failures.append("validation.model_rules")
        model_rules = {}
    for field_name, expected in expected_model_rules.items():
        require_equal(f"validation.model_rules.{field_name}", model_rules.get(field_name), expected)

    role_gates = validation.get("role_gates")
    if not isinstance(role_gates, dict):
        failures.append("validation.role_gates")
        role_gates = {}
    for candidate_id in ("R5M01", "R5L01", "R5C01"):
        gate = role_gates.get(candidate_id)
        if not isinstance(gate, dict) or int(gate.get("minimum_winning_folds") or -1) < 1:
            failures.append(f"validation.role_gates.{candidate_id}.minimum_winning_folds")
    c01_gate = role_gates.get("R5C01")
    if (
        not isinstance(c01_gate, dict)
        or c01_gate.get("paired_transfer_bootstrap_required") is not True
    ):
        failures.append("validation.role_gates.R5C01.paired_transfer_bootstrap_required")
    m02_gate = role_gates.get("R5M02")
    if (
        not isinstance(m02_gate, dict)
        or int(m02_gate.get("joint_brier_and_slope_passing_folds_min") or -1) < 1
    ):
        failures.append("validation.role_gates.R5M02.calibration_fold_min")
        m02_gate = {}
    expected_m02_gate = {
        "calibration_population": (
            "all_outer_fold_test_symbol_decisions_with_finite_labels_and_probabilities"
        ),
        "base_probability_source": (
            "corresponding_walk_forward_training_label_mean_for_each_prediction"
        ),
        "brier_comparison": "model_strictly_below_constant_training_base_probability",
        "calibration_slope_method": (
            "unpenalized_logistic_regression_of_label_on_clipped_prediction_logit_with_intercept"
        ),
        "probability_clip": 1e-6,
        "calibration_slope_min": 0.7,
        "calibration_slope_max": 1.3,
        "expected_observation_count_by_fold": {
            "F1": 143,
            "F2": 143,
            "F3": 143,
            "F4": 143,
        },
        "minimum_class_count_per_fold": 20,
        "joint_brier_and_slope_passing_folds_min": 3,
        "minimum_applied_gate_decisions": 6,
        "minimum_folds_with_target_difference_from_R5M01": 3,
        "aggregate_target_hash_must_differ_from_R5M01": True,
        "single_class_constant_probability_or_failed_fit_action": "fold_fail",
    }
    for field_name, expected in expected_m02_gate.items():
        require_equal(
            f"validation.role_gates.R5M02.{field_name}",
            m02_gate.get(field_name),
            expected,
        )

    expected_family_gates = {
        "positive_net_return_folds_min": 3,
        "stress_20bps_positive_folds_min": 3,
        "transfer_holdout_sharpe_min": 0.7,
        "transfer_holdout_max_drawdown_abs_pct_max": 20.0,
        "annualized_full_L1_executed_notional_ratio_max": 6.0,
        "annualized_BIL_excess_sharpe_min": 0.0,
        "cumulative_dsr_probability_min": 0.95,
        "pbo_max": 0.2,
        "pbo_min_partitions": 20,
    }
    family_gates = validation.get("family_gates")
    if not isinstance(family_gates, dict):
        failures.append("validation.family_gates")
        family_gates = {}
    for field_name, expected in expected_family_gates.items():
        require_equal(
            f"validation.family_gates.{field_name}", family_gates.get(field_name), expected
        )

    feature = contracts["feature"]
    candidate_feature_sets = feature.get("candidate_feature_sets")
    expected_candidate_feature_sets = {
        candidate_id: list(feature_names)
        for candidate_id, feature_names in R5_DECLARED_FEATURE_CONTRACT.items()
    }
    require_equal(
        "feature.candidate_feature_sets",
        candidate_feature_sets,
        expected_candidate_feature_sets,
    )
    require_equal(
        "feature.core_features",
        feature.get("core_features"),
        R5_CORE_FEATURE_DESCRIPTION_CONTRACT,
    )
    require_equal(
        "feature.llm_formula_features",
        feature.get("llm_formula_features"),
        R5_LLM_FEATURE_DESCRIPTION_CONTRACT,
    )
    formula_provenance = feature.get("llm_formula_provenance")
    expected_formula_mapping = {
        formula_name: str(contract["source_factor_name"])
        for formula_name, contract in R5_FORMULA_SOURCE_CONTRACT.items()
    }
    if not isinstance(formula_provenance, dict):
        failures.append("feature.llm_formula_provenance")
        formula_provenance = {}
    formula_provenance_expected = {
        "source_iteration": "mom_multiasset_ai_r2",
        "source_path": "reports/research/iterations/mom_multiasset_ai_r2/factor-proposals.json",
        "generated_by": "codex_offline_research_compiler",
        "input_hash": "7696685d49d88679a2c922e10824ec205ee21b71b00caab7a0976f5e75088e25",
        "prompt_hash": "048d43642e4ec0ba9b17514f4da24140836655996c788ec67db0ae1b2804c99f",
        "live_llm_inference": False,
        "formula_search_in_r5": False,
        "selected_source_factor_names": expected_formula_mapping,
    }
    for field_name, expected in formula_provenance_expected.items():
        require_equal(
            f"feature.llm_formula_provenance.{field_name}",
            formula_provenance.get(field_name),
            expected,
        )
    if base is not None:
        source_relative = str(formula_provenance.get("source_path") or "")
        source_sha256 = str(formula_provenance.get("source_sha256") or "")
        if locked_artifact_sha256_by_path is not None and (
            locked_artifact_sha256_by_path.get(source_relative) != source_sha256
        ):
            failures.append("feature.llm_formula_provenance.lock_binding")
        try:
            source_path = _repo_file_path(base, source_relative)
            source_payload = _load_json(source_path, expected_sha256=source_sha256)
        except ValueError:
            failures.append("feature.llm_formula_provenance.source_binding")
        else:
            for field_name in ("generated_by", "input_hash", "prompt_hash"):
                if source_payload.get(field_name) != formula_provenance.get(field_name):
                    failures.append(f"feature.llm_formula_provenance.source_{field_name}")
            if source_payload.get("live_decision_use") is not False:
                failures.append("feature.llm_formula_provenance.source_live_decision_use")
            proposals = source_payload.get("proposals")
            proposals_by_name = {
                str(row.get("factor_name") or ""): row
                for row in proposals or []
                if isinstance(row, dict)
            }
            expected_source_formulas = {
                str(contract["source_factor_name"]): str(contract["source_formula"])
                for contract in R5_FORMULA_SOURCE_CONTRACT.values()
            }
            for source_factor_name in expected_formula_mapping.values():
                proposal = proposals_by_name.get(source_factor_name)
                if (
                    not isinstance(proposal, dict)
                    or proposal.get("formula") != expected_source_formulas[source_factor_name]
                    or proposal.get("input_visibility") != "index-1_or_earlier"
                ):
                    failures.append(
                        f"feature.llm_formula_provenance.source_proposal.{source_factor_name}"
                    )
    target_contract = feature.get("target_construction")
    model_contract = feature.get("model_fitting")
    formula_contract = feature.get("formula_composition")
    if not isinstance(target_contract, dict) or int(target_contract.get("top_n") or -1) != TOP_N:
        failures.append("feature.target_construction.top_n")
    if not isinstance(model_contract, dict):
        failures.append("feature.model_fitting")
        model_contract = {}
    if int(model_contract.get("maximum_trailing_window_sessions") or -1) != (
        TRAINING_WINDOW_SESSIONS
    ):
        failures.append("feature.model_fitting.maximum_trailing_window_sessions")
    if int(model_contract.get("label_terminal_embargo_sessions") or -1) != EMBARGO_SESSIONS:
        failures.append("feature.model_fitting.label_terminal_embargo_sessions")
    if not isinstance(formula_contract, dict) or int(
        formula_contract.get("placebo_seed") or -1
    ) != (PLACEBO_SEED):
        failures.append("feature.formula_composition.placebo_seed")

    label = contracts["label"]
    for label_name in ("return_label", "path_survival_label"):
        row = label.get(label_name)
        if not isinstance(row, dict):
            failures.append(f"label.{label_name}")
            continue
        if int(row.get("horizon_sessions") or -1) != HORIZON_SESSIONS:
            failures.append(f"label.{label_name}.horizon_sessions")
        if int(row.get("embargo_sessions") or -1) != EMBARGO_SESSIONS:
            failures.append(f"label.{label_name}.embargo_sessions")

    cost = contracts["cost"]
    cost_views = {
        "gross_0bps": 0.0,
        "primary_10bps": float(cost.get("primary_cost_bps_per_executed_notional", math.nan)),
        "stress_20bps": float(cost.get("stress_cost_bps_per_executed_notional", math.nan)),
        "severe_report_only_35bps": float(
            cost.get("severe_report_only_cost_bps_per_executed_notional", math.nan)
        ),
    }
    expected_costs = {
        "primary_10bps": PRIMARY_COST_BPS,
        "stress_20bps": STRESS_COST_BPS,
        "severe_report_only_35bps": SEVERE_COST_BPS,
    }
    if any(
        not math.isfinite(cost_views[name]) or cost_views[name] != expected
        for name, expected in expected_costs.items()
    ):
        failures.append("cost.cost_views")
    accounting = cost.get("accounting")
    if (
        not isinstance(accounting, dict)
        or accounting.get("exact_self_financing_transaction_solver_required") is not True
    ):
        failures.append("cost.accounting.exact_solver")
    if cost.get("notional_basis") != "full_L1_executed_notional_including_cash_boundaries":
        failures.append("cost.notional_basis")
    require_equal(
        "cost.charged_events",
        cost.get("charged_events"),
        ["initial_entry", "every_rebalance_delta", "terminal_liquidation"],
    )
    expected_event_reason_codes = [
        "scheduled_rebalance",
        "independent_boundary_entry",
        "terminal_liquidation",
    ]
    require_equal(
        "cost.event_reason_codes",
        cost.get("event_reason_codes"),
        expected_event_reason_codes,
    )
    expected_spec_costs = {
        "commission_pct": 0.0,
        "slippage_bps": PRIMARY_COST_BPS,
        "impact_model": "linear",
        "impact_eta": 0.0,
        "impact_gamma": 0.0,
    }
    require_equal(
        "cost.strategy_spec_costs",
        cost.get("strategy_spec_costs"),
        expected_spec_costs,
    )
    if isinstance(accounting, dict):
        require_equal(
            "cost.accounting.tolerance",
            accounting.get("cost_reconciliation_tolerance"),
            1e-12,
        )
        require_equal(
            "cost.accounting.aggregate_fold_explanation",
            accounting.get("aggregate_and_fold_ledgers_must_explain_reset_differences"),
            True,
        )
        require_equal(
            "cost.accounting.reserve_costing", accounting.get("reserve_trades_are_costed"), True
        )
        require_equal(
            "cost.accounting.missing_open_price_action",
            accounting.get("missing_open_price_action"),
            "fail_closed",
        )
        require_equal(
            "cost.accounting.event_cost_bps_field_required",
            accounting.get("event_cost_bps_field_required"),
            True,
        )
        require_equal(
            "cost.accounting.event_cost_formula",
            accounting.get("event_cost_formula"),
            "cost_fraction_of_pretrade_equity_equals_cost_bps_div_10000_times_full_L1_executed_notional_fraction",
        )

    holdout = contracts["holdout"]
    holdout_tca = holdout.get("matched_tca")
    cost_tca = cost.get("paper_tca")
    if not isinstance(holdout_tca, dict) or not isinstance(cost_tca, dict):
        failures.append("holdout.matched_tca")
        holdout_tca = {}
        cost_tca = {}
    if int(holdout_tca.get("minimum_unique_fills") or -1) != int(
        cost_tca.get("minimum_matched_fills") or -2
    ):
        failures.append("holdout.matched_tca.minimum_unique_fills")
    if int(holdout_tca.get("minimum_distinct_sessions") or -1) != int(
        cost_tca.get("minimum_distinct_sessions") or -2
    ):
        failures.append("holdout.matched_tca.minimum_distinct_sessions")
    if int(holdout.get("minimum_contiguous_bound_sessions") or -1) < 1:
        failures.append("holdout.minimum_contiguous_bound_sessions")
    if int(holdout.get("forward_count_start", -1)) != 0:
        failures.append("holdout.forward_count_start")
    if holdout.get("backfill_allowed") is not False:
        failures.append("holdout.backfill_allowed")

    benchmark = contracts["benchmark"]
    benchmark_rows = benchmark.get("benchmarks")
    benchmark_definitions = {
        str(row.get("benchmark_id") or ""): str(row.get("definition") or "")
        for row in benchmark_rows or []
        if isinstance(row, dict)
    }
    expected_benchmarks = {
        "same_symbol_buy_hold_SPY": "100_percent_SPY",
        "equal_weight_universe": "equal_weight_13_rankable_ETFs_monthly",
        "market_proxy": "100_percent_SPY",
        "sector_theme_proxy": "equal_weight_XLB_XLE_XLF_XLI_XLK_XLP_XLU_XLV_XLY_monthly",
        "balanced_proxy": "60_percent_SPY_40_percent_IEF_monthly",
        "cash_proxy": "100_percent_BIL",
        "ex_post_best_symbol_report_only": "best_single_symbol_after_results",
    }
    if benchmark_definitions != expected_benchmarks:
        failures.append("benchmark.definitions")
    if benchmark.get("same_cost_engine_required") is not True:
        failures.append("benchmark.same_cost_engine_required")
    benchmark_gates = benchmark.get("promotion_gates")
    expected_benchmark_gates = {
        "scope": "aggregate_common_window",
        "cost_view": "primary_10bps",
        "metric": "annualized_sharpe",
        "comparison": "candidate_greater_than_or_equal_to_each_required_benchmark",
        "required_benchmark_ids": [
            "market_proxy",
            "equal_weight_universe",
            "sector_theme_proxy",
            "balanced_proxy",
        ],
        "minimum_delta": 0.0,
        "same_symbol_buy_hold_SPY_is_identity_duplicate_of_market_proxy": True,
        "cash_proxy_raw_sharpe_is_report_only": True,
        "ex_post_best_symbol_is_report_only": True,
    }
    require_equal("benchmark.promotion_gates", benchmark_gates, expected_benchmark_gates)

    if failures:
        raise ValueError("R5 runtime contract mismatch: " + ", ".join(sorted(failures)))
    return {
        **contracts,
        "trial_count": trial_count,
        "trial_count_lower_bound": trial_lower_bound,
        "dsr_sensitivity_trial_counts": sensitivity_trial_counts,
        "cost_views": cost_views,
        "cost_reconciliation_tolerance": float(accounting["cost_reconciliation_tolerance"]),
        "cost_event_reason_codes": expected_event_reason_codes,
        "benchmark_gate_config": expected_benchmark_gates,
        "calibration_config": {
            "probability_clip": float(m02_gate["probability_clip"]),
            "slope_min": float(m02_gate["calibration_slope_min"]),
            "slope_max": float(m02_gate["calibration_slope_max"]),
            "expected_observation_count_by_fold": {
                str(key): int(value)
                for key, value in m02_gate["expected_observation_count_by_fold"].items()
            },
            "minimum_class_count_per_fold": int(m02_gate["minimum_class_count_per_fold"]),
        },
        "pbo_config": {
            "block_count": block_count,
            "in_sample_block_count": in_sample_block_count,
            "expected_partition_count": expected_partition_count,
            "minimum_valid_partition_count": int(pbo["minimum_valid_partition_count"]),
        },
        "dsr_config": {
            "hac_lag": int(dsr_contract["hac_lag"]),
            "promotion_probability_rule": str(dsr_contract["promotion_probability_rule"]),
        },
        "llm_contribution_bootstrap_config": llm_bootstrap_contract,
        "forward_requirements": {
            "forward_epoch_utc": str(holdout["forward_epoch_utc"]),
            "minimum_contiguous_bound_sessions": int(holdout["minimum_contiguous_bound_sessions"]),
            "minimum_unique_matched_paper_fills": int(holdout_tca["minimum_unique_fills"]),
            "minimum_distinct_paper_sessions": int(holdout_tca["minimum_distinct_sessions"]),
            "backfill_allowed": bool(holdout["backfill_allowed"]),
            "paper_orders_authorized": False,
            "explicit_user_confirmation_required": True,
        },
    }


def freeze_multiasset_forward_multimodal_r5(
    root: Path,
    *,
    custody_dir: Path,
) -> R5FreezeResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    validation = validate_iteration_dossier(ITER_ID, base, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R5 cannot freeze a blocked dossier: " + ", ".join(validation.blocked))
    runtime_contracts = _validate_r5_runtime_contracts(output, root=base)
    lock_dir = output / "lock-set"
    lock_stage = output / ".r5-lock-stage"
    lock_marker = output / ".lock-set-publish.lock"
    preregistration_path = lock_dir / "preregistration-lock.json"
    runner_path = lock_dir / "runner-lock.json"
    lock_anchor_path = lock_dir / "lock-anchor.json"
    if lock_dir.exists() or lock_stage.exists() or lock_marker.exists():
        raise ValueError("R5 lock already exists; lock overwrite is prohibited")
    result_dir = output / "evaluation-run"
    attempt_path = output / "evaluation-attempt.json"
    publish_marker = output / ".evaluation-run-publish.lock"
    staged_attempts = sorted(path.name for path in output.glob(".r5-evaluation-stage-*"))
    if result_dir.exists() or attempt_path.exists() or publish_marker.exists() or staged_attempts:
        raise ValueError("R5 result or staged-attempt artifacts exist before lock")

    loaded_specs = {
        candidate_id: _load_strategy_spec_stable(base / relative)
        for candidate_id, relative in SPEC_PATHS.items()
    }
    execution_contract = _validate_r5_spec_execution_contract(loaded_specs)
    harness_reconciliation = _validate_r5_harness_evidence(base, loaded_specs)

    data_contract = _load_json(output / "data-contract.json")
    manifest_path = base / str(data_contract.get("snapshot_manifest_path") or "")
    parent_binding_path = base / str(data_contract.get("bound_parent_snapshot_path") or "")
    if _sha256_file(manifest_path) != data_contract.get("snapshot_manifest_sha256"):
        raise ValueError("R5 data manifest hash differs before lock")
    if _sha256_file(parent_binding_path) != data_contract.get("bound_parent_snapshot_sha256"):
        raise ValueError("R5 parent snapshot binding hash differs before lock")
    verify_alpaca_contract_snapshot(base, manifest_path)

    artifact_relatives = [
        *(f"{ITERATION_DIR.as_posix()}/{filename}" for filename in R5_LOCK_ITERATION_FILENAMES),
        "reports/research/iterations/mom_multiasset_ai_r2/factor-proposals.json",
        "reports/harness/source_cards/us_multiasset_forward_multimodal_r5.jsonl",
        *_r5_harness_relative_paths(loaded_specs),
        _relpath(parent_binding_path, base),
        _relpath(manifest_path, base),
    ]
    if len(artifact_relatives) != len(set(artifact_relatives)):
        raise ValueError("R5 preregistration artifact inventory contains duplicate paths")
    artifacts = [_file_binding(base / relative, base) for relative in artifact_relatives]
    specs = []
    for candidate_id, relative in SPEC_PATHS.items():
        path = base / relative
        spec = loaded_specs[candidate_id]
        specs.append(
            {
                "candidate_id": candidate_id,
                "path": relative.as_posix(),
                "file_sha256": _sha256_file(path),
                "semantic_sha256": strategy_content_hash(spec),
            }
        )
    locked_at = datetime.now(UTC).isoformat()
    preregistration = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "behavior_contracts_locked_before_first_r5_price_calculation",
        "locked_at": locked_at,
        "candidate_count": 8,
        "cumulative_trial_count_lower_bound": runtime_contracts["trial_count_lower_bound"],
        "dsr_governance_trial_count": runtime_contracts["trial_count"],
        "first_evaluation_artifacts_absent": True,
        "historical_scope": "matched_transfer_evidence_not_pristine_promotion_holdout",
        "forward_count_at_lock": 0,
        "backfill_allowed": False,
        "artifacts": artifacts,
        "specs": specs,
        "spec_execution_contract": execution_contract,
        "harness_reconciliation": harness_reconciliation,
        "prohibitions": [
            "no_candidate_or_parameter_changes_after_lock",
            "no_result_overwrite_or_rerun",
            "no_broker_client_or_order_authorization",
            "no_forward_backfill",
        ],
    }
    runner_relatives = _r5_runner_relative_paths(base)
    runner = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "implementation_locked_before_first_r5_price_calculation",
        "locked_at": locked_at,
        "files": [_file_binding(base / relative, base) for relative in runner_relatives],
        "dependency_closure": {
            "algorithm": "recursive_static_local_import_closure_v1",
            "evaluation_entry": "open_composer/research/multiasset_forward_multimodal_r5.py",
            "forward_adapter_entry": (
                "open_composer/adapters/execution/"
                "multiasset_forward_multimodal_r5_target_weights.py"
            ),
            "file_count": len(runner_relatives),
            "unrelated_package_files_excluded": True,
        },
        "runtime": _current_runtime(),
        "test_command": (
            "uv run pytest -q tests/test_multiasset_forward_multimodal_r5.py "
            "tests/test_iteration_dossier.py tests/test_spec_validation.py"
        ),
        "first_real_price_evaluation_completed": False,
    }
    lock_stage.mkdir(mode=0o700)
    _write_json_atomic(lock_stage / "preregistration-lock.json", preregistration)
    _write_json_atomic(lock_stage / "runner-lock.json", runner)
    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": _sha256_file(lock_stage / "preregistration-lock.json"),
        "runner_lock_sha256": _sha256_file(lock_stage / "runner-lock.json"),
    }
    lock_anchor_sha256 = hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest()
    lock_anchor = {
        "schema_version": 1,
        **anchor_subject,
        "operator_lock_anchor_sha256": lock_anchor_sha256,
        "external_custody_required": True,
        "operator_instruction": (
            "Retain the external content-addressed custody receipt and pass this SHA-256 "
            "explicitly to the one-shot evaluation command."
        ),
    }
    _write_json_atomic(lock_stage / "lock-anchor.json", lock_anchor)
    custody = _write_r5_lock_custody(
        root=base,
        custody_dir=custody_dir,
        lock_stage=lock_stage,
        preregistration=preregistration,
        runner=runner,
        lock_anchor=lock_anchor,
        manifest_path=manifest_path,
    )
    _publish_directory_exclusive(lock_stage, lock_dir)
    return R5FreezeResult(
        preregistration_lock_path=preregistration_path,
        runner_lock_path=runner_path,
        lock_anchor_path=lock_anchor_path,
        lock_anchor_sha256=lock_anchor_sha256,
        custody_receipt_path=custody.receipt_path,
        custody_receipt_sha256=custody.receipt_sha256,
        payload={
            "preregistration": preregistration,
            "runner": runner,
            "lock_anchor": lock_anchor,
            "external_custody": _custody_summary(custody),
        },
    )


def _write_r5_lock_custody(
    *,
    root: Path,
    custody_dir: Path,
    lock_stage: Path,
    preregistration: dict[str, Any],
    runner: dict[str, Any],
    lock_anchor: dict[str, Any],
    manifest_path: Path,
) -> ExternalCustodyRecord:
    entries: dict[str, bytes] = {}

    def add_project_file(path: Path) -> None:
        relative = _relpath(path, root)
        contents = _read_regular_file_bytes(path)
        prior = entries.get(relative)
        if prior is not None and prior != contents:
            raise ValueError(f"R5 custody source path has conflicting bytes: {relative}")
        entries[relative] = contents

    for binding in preregistration.get("artifacts", []):
        add_project_file(_verify_file_binding(root, binding))
    for binding in preregistration.get("specs", []):
        add_project_file(
            _verify_file_binding(
                root,
                {"path": binding.get("path"), "sha256": binding.get("file_sha256")},
            )
        )
    for binding in runner.get("files", []):
        add_project_file(_verify_file_binding(root, binding))
    for path in sorted(manifest_path.parent.rglob("*")):
        if path.is_file():
            add_project_file(path)
        elif path.is_symlink():
            raise ValueError("R5 custody snapshot inventory cannot contain symlinks")
    for filename in ("preregistration-lock.json", "runner-lock.json", "lock-anchor.json"):
        entries[(ITERATION_DIR / "lock-set" / filename).as_posix()] = _read_regular_file_bytes(
            lock_stage / filename
        )
    operator_hash = str(lock_anchor.get("operator_lock_anchor_sha256") or "")
    return write_external_custody_bundle(
        project_root=root,
        custody_root=custody_dir,
        namespace=R5_CUSTODY_NAMESPACE,
        record_kind="lock",
        subject_sha256=operator_hash,
        entries=entries,
        subject={
            "iter_id": ITER_ID,
            "operator_lock_anchor_sha256": operator_hash,
            "lock_anchor_file_sha256": hashlib.sha256(
                entries[(ITERATION_DIR / "lock-set/lock-anchor.json").as_posix()]
            ).hexdigest(),
            "source_bundle_complete": True,
        },
    )


def _verify_r5_lock_custody(
    *,
    root: Path,
    custody_dir: Path,
    lock_anchor_sha256: str,
) -> ExternalCustodyRecord:
    receipt_path = custody_dir / R5_CUSTODY_NAMESPACE / "lock" / lock_anchor_sha256 / "receipt.json"
    record = verify_external_custody_record(
        project_root=root,
        custody_root=custody_dir,
        receipt_path=receipt_path,
        expected_namespace=R5_CUSTODY_NAMESPACE,
        expected_record_kind="lock",
        expected_subject_sha256=lock_anchor_sha256,
    )
    subject = record.payload.get("subject")
    if (
        not isinstance(subject, dict)
        or subject.get("iter_id") != ITER_ID
        or subject.get("operator_lock_anchor_sha256") != lock_anchor_sha256
        or subject.get("source_bundle_complete") is not True
    ):
        raise ValueError("R5 external lock custody subject is invalid")
    return record


def _write_r5_evaluation_custody(
    *,
    root: Path,
    custody_dir: Path,
    stage_dir: Path,
    evaluation_anchor: dict[str, Any],
    preflight: dict[str, Any],
) -> ExternalCustodyRecord:
    entries = {
        (ITERATION_DIR / "evaluation-run" / path.name).as_posix(): _read_regular_file_bytes(path)
        for path in sorted(stage_dir.iterdir())
    }
    for path in sorted((root / ITERATION_DIR / "lock-set").iterdir()):
        entries[(ITERATION_DIR / "lock-set" / path.name).as_posix()] = _read_regular_file_bytes(
            path
        )
    attempt_path = root / ITERATION_DIR / "evaluation-attempt.json"
    entries[(ITERATION_DIR / "evaluation-attempt.json").as_posix()] = _read_regular_file_bytes(
        attempt_path
    )
    lock_custody = _verify_r5_lock_custody(
        root=root,
        custody_dir=custody_dir,
        lock_anchor_sha256=str(preflight["operator_lock_anchor_sha256"]),
    )
    entries["external-custody/lock-receipt.json"] = _read_regular_file_bytes(
        lock_custody.receipt_path
    )
    operator_hash = str(evaluation_anchor.get("operator_evaluation_anchor_sha256") or "")
    return write_external_custody_bundle(
        project_root=root,
        custody_root=custody_dir,
        namespace=R5_CUSTODY_NAMESPACE,
        record_kind="evaluation",
        subject_sha256=operator_hash,
        entries=entries,
        subject={
            "iter_id": ITER_ID,
            "operator_lock_anchor_sha256": preflight["operator_lock_anchor_sha256"],
            "operator_evaluation_anchor_sha256": operator_hash,
            "evaluation_anchor_file_sha256": hashlib.sha256(
                entries[(ITERATION_DIR / "evaluation-run/evaluation-anchor.json").as_posix()]
            ).hexdigest(),
            "lock_custody_receipt_sha256": lock_custody.receipt_sha256,
            "publication_only_recovery_allowed": True,
            "price_recomputation_allowed": False,
        },
    )


def _custody_summary(record: ExternalCustodyRecord) -> dict[str, Any]:
    return {
        "receipt_path": str(record.receipt_path),
        "receipt_sha256": record.receipt_sha256,
        "bundle_path": str(record.bundle_path),
        "bundle_sha256": record.bundle_sha256,
        "entry_count": record.payload["entry_count"],
    }


def _evaluation_paths(directory: Path) -> dict[str, Path]:
    return {name: directory / filename for name, filename in R5_EVALUATION_FILENAMES.items()}


def _r5_runner_relative_paths(root: Path) -> list[str]:
    base = root.resolve()
    forward_adapter = (
        "open_composer/adapters/execution/multiasset_forward_multimodal_r5_target_weights.py"
    )
    entry_paths = [
        "open_composer/research/multiasset_forward_multimodal_r5.py",
        forward_adapter,
    ]
    package_paths = _local_python_dependency_closure(base, entry_paths)
    extras = [
        "tests/test_multiasset_forward_multimodal_r5.py",
        "tests/test_multiasset_forward_multimodal_r5_target_weights.py",
        "tests/test_iteration_dossier.py",
        "tests/test_spec_validation.py",
        "schemas/alpaca_snapshot_contract.schema.json",
        "schemas/alpaca_snapshot_manifest.schema.json",
        "schemas/strategy_spec.schema.json",
        "pyproject.toml",
        "uv.lock",
    ]
    relatives = [*package_paths, *extras]
    if len(relatives) != len(set(relatives)):
        raise ValueError("R5 runner lock inventory contains duplicate paths")
    for relative in relatives:
        _read_regular_file_bytes(base / relative)
    return relatives


def _local_python_dependency_closure(root: Path, entry_paths: list[str]) -> list[str]:
    base = root.resolve()
    module_to_path: dict[str, str] = {}
    path_to_module: dict[str, str] = {}
    for path in sorted((base / "open_composer").rglob("*.py")):
        relative = path.relative_to(base).as_posix()
        parts = list(path.relative_to(base).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        module = ".".join(parts)
        module_to_path[module] = relative
        path_to_module[relative] = module
    missing_entries = sorted(set(entry_paths) - set(path_to_module))
    if missing_entries:
        raise ValueError("R5 dependency entry point is missing: " + ", ".join(missing_entries))

    pending = [path_to_module[path] for path in entry_paths]
    selected_modules: set[str] = set()

    def enqueue(module: str) -> None:
        current = module
        while current.startswith("open_composer"):
            if current in module_to_path and current not in selected_modules:
                pending.append(current)
            if "." not in current:
                break
            current = current.rpartition(".")[0]

    while pending:
        module = pending.pop()
        if module in selected_modules:
            continue
        selected_modules.add(module)
        relative = module_to_path[module]
        try:
            tree = ast.parse(_read_regular_file_bytes(base / relative), filename=relative)
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise ValueError(f"R5 dependency source cannot be parsed: {relative}") from exc
        package = module if relative.endswith("/__init__.py") else module.rpartition(".")[0]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    enqueue(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    try:
                        imported = resolve_name(
                            "." * node.level + (node.module or ""),
                            package,
                        )
                    except (ImportError, ValueError) as exc:
                        raise ValueError(
                            f"R5 relative import cannot be resolved: {relative}:{node.lineno}"
                        ) from exc
                else:
                    imported = node.module or ""
                enqueue(imported)
                for alias in node.names:
                    if alias.name != "*":
                        enqueue(f"{imported}.{alias.name}")
    return sorted(module_to_path[module] for module in selected_modules)


def run_multiasset_forward_multimodal_r5(
    root: Path,
    *,
    expected_lock_anchor_sha256: str,
    custody_dir: Path,
) -> R5EvaluationResult:
    base = root.resolve()
    output = base / ITERATION_DIR
    preflight = _preflight(
        base,
        expected_lock_anchor_sha256=expected_lock_anchor_sha256,
        custody_dir=custody_dir,
    )
    preregistration = _load_json(
        output / "lock-set/preregistration-lock.json",
        expected_sha256=preflight["preregistration_lock_sha256"],
    )
    locked_artifact_hashes = _binding_sha256_by_path(
        preregistration.get("artifacts"),
        label="R5 preregistration artifacts",
    )
    harness_reconciliation = preregistration.get("harness_reconciliation")
    if (
        not isinstance(harness_reconciliation, dict)
        or harness_reconciliation.get("reconciliation_contract")
        != R5_HARNESS_RECONCILIATION_CONTRACT
        or harness_reconciliation.get("iter_id") != ITER_ID
        or harness_reconciliation.get("research_gate_pass") is not True
        or harness_reconciliation.get("empirical_execution_evidence_pass") is not False
        or harness_reconciliation.get("paper_readiness_evidence_pass") is not False
    ):
        raise ValueError("R5 preregistration harness reconciliation is invalid")
    harness_reconciliation_sha256 = hashlib.sha256(
        _canonical_json_bytes(harness_reconciliation)
    ).hexdigest()
    locked_spec_hashes = _spec_file_sha256_by_path(preregistration.get("specs"))
    runtime_contracts = _validate_r5_runtime_contracts(
        output,
        root=base,
        locked_artifact_sha256_by_path=locked_artifact_hashes,
    )
    validation_contract = runtime_contracts["validation"]
    feature_contract = runtime_contracts["feature"]
    specs = {
        candidate_id: _load_strategy_spec_stable(
            base / path,
            expected_sha256=locked_spec_hashes[path.as_posix()],
        )
        for candidate_id, path in SPEC_PATHS.items()
    }
    spec_execution_contract = _validate_r5_spec_execution_contract(specs)
    harness_reconciliation = _validate_r5_harness_evidence(
        base,
        specs,
        locked_artifact_sha256_by_path=locked_artifact_hashes,
    )
    if _canonical_json_bytes(harness_reconciliation) != _canonical_json_bytes(
        preregistration.get("harness_reconciliation")
    ):
        raise ValueError("R5 harness reconciliation differs from preregistration")
    if harness_reconciliation_sha256 != preflight.get("harness_reconciliation_sha256"):
        raise ValueError("R5 harness reconciliation hash differs from preflight")
    attempt_binding = _reserve_evaluation_attempt(base, preflight)
    preflight["evaluation_attempt"] = attempt_binding
    panel = load_r5_panel(
        base,
        base / preflight["data_manifest_path"],
        expected_manifest_sha256=preflight["data_manifest_sha256"],
    )
    features = build_point_in_time_features(
        panel.close,
        panel.volume,
        formula_spec=specs[spec_execution_contract["formula_spec_candidate_id"]],
    )
    dataset = build_monthly_feature_dataset(
        panel,
        features,
        placebo_spec=specs[spec_execution_contract["placebo_spec_candidate_id"]],
        rebalance_schedule=spec_execution_contract["rebalance_schedule"],
    )
    if dataset["decision_session"].min() > "2018-02-01":
        raise ValueError("R5 feature history does not cover the frozen training start")

    provenance = {
        "data_manifest_sha256": preflight["data_manifest_sha256"],
        "feature_contract_sha256": _sha256_file(output / "feature-contract.json"),
        "label_contract_sha256": _sha256_file(output / "label-contract.json"),
        "prompt_hash": str(feature_contract["llm_formula_provenance"]["prompt_hash"]),
    }
    folds = validation_contract.get("folds")
    if not isinstance(folds, list) or len(folds) != 4:
        raise ValueError("R5 requires exactly four frozen outer folds")
    segments = [
        {
            "segment_id": str(fold["fold_id"]),
            "kind": "outer_fold",
            "train_start": str(fold["train_start"]),
            "start": str(fold["test_start"]),
            "end": str(fold["test_end"]),
        }
        for fold in folds
    ]
    transfer = validation_contract.get("transfer_holdout")
    if not isinstance(transfer, dict):
        raise ValueError("R5 transfer holdout contract is missing")
    segments.append(
        {
            "segment_id": "TRANSFER",
            "kind": "transfer_holdout",
            "train_start": str(folds[0]["train_start"]),
            "start": str(transfer["start"]),
            "end": str(transfer["end"]),
        }
    )

    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    target_records: list[dict[str, Any]] = []
    model_records: list[dict[str, Any]] = []
    calibration_by_segment: dict[str, pd.DataFrame] = {}
    for segment in segments:
        frames, records, models, calibration = build_candidate_targets_for_segment(
            dataset,
            segment_id=segment["segment_id"],
            execution_start=segment["start"],
            execution_end=segment["end"],
            train_start_session=segment["train_start"],
            columns=panel.open.columns,
            specs=specs,
            provenance=provenance,
        )
        segment_targets[segment["segment_id"]] = frames
        target_records.extend(records)
        model_records.extend(models)
        calibration_by_segment[segment["segment_id"]] = calibration

    aggregate_targets = {
        candidate_id: pd.concat(
            [segment_targets[segment["segment_id"]][candidate_id] for segment in segments]
        ).sort_index()
        for candidate_id in SPEC_PATHS
    }
    if any(frame.index.has_duplicates for frame in aggregate_targets.values()):
        raise ValueError("R5 aggregate targets contain duplicate execution sessions")
    fallback_identity = canonical_target_bytes(aggregate_targets["R5F01"]) == (
        canonical_target_bytes(aggregate_targets["R5M01"])
    )
    if not fallback_identity:
        raise ValueError("R5 missing-modality target identity failed")
    evaluated_decision_sessions = {
        str(row["decision_session"]) for row in target_records if row["candidate_id"] == "R5P01"
    }
    formula_placebo_evidence = _formula_placebo_evidence(
        dataset,
        decision_sessions=evaluated_decision_sessions,
    )

    cost_views = runtime_contracts["cost_views"]
    aggregate_simulations: dict[str, dict[str, ExactSimulationResult]] = {}
    segment_simulations: dict[str, dict[str, dict[str, ExactSimulationResult]]] = {}
    event_records: list[dict[str, Any]] = []
    daily_return_records: list[dict[str, Any]] = []
    aggregate_start = str(segments[0]["start"])
    aggregate_end = str(segments[-1]["end"])
    for candidate_id in SPEC_PATHS:
        aggregate_simulations[candidate_id] = {}
        for view_name, cost_bps in cost_views.items():
            simulation = simulate_exact_target_portfolio(
                panel.open,
                aggregate_targets[candidate_id],
                cost_bps=cost_bps,
                start=aggregate_start,
                end=aggregate_end,
            )
            aggregate_simulations[candidate_id][view_name] = simulation
            event_records.extend(
                _scoped_events(
                    simulation.events,
                    candidate_id=candidate_id,
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
            daily_return_records.extend(
                _scoped_daily_returns(
                    simulation.daily,
                    candidate_id=candidate_id,
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
        segment_simulations[candidate_id] = {}
        for segment in segments:
            scope = segment["segment_id"]
            segment_simulations[candidate_id][scope] = {}
            for view_name, cost_bps in {
                name: cost_views[name] for name in ("primary_10bps", "stress_20bps")
            }.items():
                simulation = simulate_exact_target_portfolio(
                    panel.open,
                    segment_targets[scope][candidate_id],
                    cost_bps=cost_bps,
                    start=segment["start"],
                    end=segment["end"],
                )
                segment_simulations[candidate_id][scope][view_name] = simulation
                event_records.extend(
                    _scoped_events(
                        simulation.events,
                        candidate_id=candidate_id,
                        scope_id=scope,
                        cost_view=view_name,
                    )
                )
                daily_return_records.extend(
                    _scoped_daily_returns(
                        simulation.daily,
                        candidate_id=candidate_id,
                        scope_id=scope,
                        cost_view=view_name,
                    )
                )

    simulated_pbo_returns = _stitched_fold_returns(segment_simulations, folds)
    pbo_contract = validation_contract["pbo"]
    pbo_returns, pbo_ledger_source_rows = _pbo_returns_from_daily_ledger(
        daily_return_records,
        folds=folds,
        candidate_ids=list(SPEC_PATHS),
    )
    if (
        list(pbo_returns.index) != list(simulated_pbo_returns.index)
        or list(pbo_returns.columns) != list(simulated_pbo_returns.columns)
        or not np.array_equal(
            pbo_returns.to_numpy(dtype=float),
            simulated_pbo_returns.to_numpy(dtype=float),
        )
    ):
        raise ValueError("R5 daily-return ledger differs from simulated PBO returns")
    pbo_candidate_ids = list(map(str, pbo_contract["selection_candidate_ids"]))
    pbo_source_rows = [
        {
            "scope_id": row["scope_id"],
            "interval_start": row["interval_start"],
            "interval_end": row["interval_end"],
            **{candidate_id: float(row[candidate_id]) for candidate_id in pbo_candidate_ids},
        }
        for row in pbo_ledger_source_rows
    ]
    if len(pbo_source_rows) != int(pbo_contract["expected_return_observation_count"]):
        raise ValueError("R5 PBO return observation count differs from frozen contract")
    pbo_config = runtime_contracts["pbo_config"]
    pbo_blocks, _ = build_cscv_partitions(
        pbo_returns.index,
        block_count=pbo_config["block_count"],
        in_sample_block_count=pbo_config["in_sample_block_count"],
    )
    if [int(block["observation_count"]) for block in pbo_blocks] != list(
        map(int, pbo_contract["expected_block_observation_counts"])
    ):
        raise ValueError("R5 PBO block sizes differ from frozen contract")
    pbo = probability_backtest_overfitting(
        pbo_returns,
        candidate_ids=pbo_candidate_ids,
        block_count=pbo_config["block_count"],
        in_sample_block_count=pbo_config["in_sample_block_count"],
    )
    if pbo["partition_count"] != int(pbo_contract["expected_partition_count"]):
        raise ValueError("R5 PBO partition count differs from frozen contract")
    pbo["return_observation_count"] = len(pbo_source_rows)
    pbo["return_source_sha256"] = hashlib.sha256(_canonical_json_bytes(pbo_source_rows)).hexdigest()
    dsr: dict[str, Any] = {}
    dsr_scope_ids = [str(row["scope_id"]) for row in pbo_ledger_source_rows]
    for candidate_id in SPEC_PATHS:
        return_rows = [
            {
                "scope_id": row["scope_id"],
                "interval_start": row["interval_start"],
                "interval_end": row["interval_end"],
                "net_return": float(row[candidate_id]),
            }
            for row in pbo_ledger_source_rows
        ]
        sensitivity = {
            str(trial_count): deflated_sharpe_ratio(
                pbo_returns[candidate_id],
                trial_count=trial_count,
                scope_ids=dsr_scope_ids,
                hac_lag=int(runtime_contracts["dsr_config"]["hac_lag"]),
            )
            for trial_count in runtime_contracts["dsr_sensitivity_trial_counts"]
        }
        result = dict(sensitivity[str(runtime_contracts["trial_count"])])
        result["known_trial_count_lower_bound"] = runtime_contracts["trial_count_lower_bound"]
        result["promotion_governance_trial_count"] = runtime_contracts["trial_count"]
        result["sensitivity"] = sensitivity
        result["return_source_sha256"] = hashlib.sha256(
            _canonical_json_bytes(return_rows)
        ).hexdigest()
        dsr[candidate_id] = result

    m02_role_contract = validation_contract["role_gates"]["R5M02"]
    calibration = _calibration_payload(
        calibration_by_segment,
        folds,
        required_joint_passing_fold_count=int(
            m02_role_contract["joint_brier_and_slope_passing_folds_min"]
        ),
        probability_clip=float(m02_role_contract["probability_clip"]),
        slope_min=float(m02_role_contract["calibration_slope_min"]),
        slope_max=float(m02_role_contract["calibration_slope_max"]),
        expected_observation_count_by_fold={
            str(key): int(value)
            for key, value in m02_role_contract["expected_observation_count_by_fold"].items()
        },
        minimum_class_count=int(m02_role_contract["minimum_class_count_per_fold"]),
    )
    benchmark_payload, benchmark_simulations, benchmark_targets = _benchmark_family_exact(
        panel.open,
        monthly_sessions=aggregate_targets["R5D01"].index,
        start=aggregate_start,
        end=aggregate_end,
        primary_cost_bps=cost_views["primary_10bps"],
        stress_cost_bps=cost_views["stress_20bps"],
    )
    for benchmark_id, views in benchmark_simulations.items():
        for view_name, simulation in views.items():
            event_records.extend(
                _scoped_events(
                    simulation.events,
                    candidate_id=f"BENCHMARK:{benchmark_id}",
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
            daily_return_records.extend(
                _scoped_daily_returns(
                    simulation.daily,
                    candidate_id=f"BENCHMARK:{benchmark_id}",
                    scope_id="AGGREGATE",
                    cost_view=view_name,
                )
            )
    daily_return_ledger_sha256 = _jsonl_sha256(daily_return_records)
    llm_contribution_bootstrap = paired_transfer_sharpe_bootstrap(
        daily_return_records,
        event_records,
        contract=runtime_contracts["llm_contribution_bootstrap_config"],
    )
    pbo["return_source"] = {
        "artifact_name": "daily_return_ledger",
        "ledger_sha256": daily_return_ledger_sha256,
        "scope_ids": [str(fold["fold_id"]) for fold in folds],
        "cost_view": "primary_10bps",
        "candidate_ids": pbo_candidate_ids,
        "canonical_form": "interval_start_then_candidate_id_sorted_canonical_json",
        "row_count": len(pbo_source_rows),
        "sha256": pbo["return_source_sha256"],
    }
    for candidate_id, result in dsr.items():
        result["return_source"] = {
            "artifact_name": "daily_return_ledger",
            "ledger_sha256": daily_return_ledger_sha256,
            "scope_ids": [str(fold["fold_id"]) for fold in folds],
            "cost_view": "primary_10bps",
            "candidate_id": candidate_id,
            "canonical_form": "interval_start_and_net_return_canonical_json",
            "row_count": int(result["session_count"]),
            "sha256": result["return_source_sha256"],
        }
    benchmark_rows = _benchmark_ledger_rows(
        benchmark_payload,
        benchmark_simulations,
        benchmark_targets,
        promotion_gate_ids=set(
            runtime_contracts["benchmark_gate_config"]["required_benchmark_ids"]
        ),
    )
    bil_primary = benchmark_simulations["cash_proxy"]["primary_10bps"]
    candidates: dict[str, Any] = {}
    for candidate_id, spec in specs.items():
        aggregate_cost_metrics = {
            view: dict(simulation.metrics)
            for view, simulation in aggregate_simulations[candidate_id].items()
        }
        candidate_returns = aggregate_simulations[candidate_id]["primary_10bps"].daily["net_return"]
        bil_returns = bil_primary.daily["net_return"]
        try:
            bil_excess_sharpe = defined_annualized_sharpe(candidate_returns - bil_returns)
        except ValueError:
            bil_excess_sharpe = 0.0
        aggregate_cost_metrics["primary_10bps"]["annualized_BIL_excess_sharpe"] = bil_excess_sharpe
        candidate_folds = {
            str(fold["fold_id"]): {
                view: simulation.metrics
                for view, simulation in segment_simulations[candidate_id][
                    str(fold["fold_id"])
                ].items()
            }
            for fold in folds
        }
        transfer_metrics = {
            view: simulation.metrics
            for view, simulation in segment_simulations[candidate_id]["TRANSFER"].items()
        }
        candidates[candidate_id] = {
            "strategy_name": spec.name,
            "spec_path": SPEC_PATHS[candidate_id].as_posix(),
            "spec_hash": strategy_content_hash(spec),
            "promotion_eligible": R5_CANDIDATE_ROLE_CONTRACT[candidate_id]["promotion_eligible"],
            "aggregate_cost_views": aggregate_cost_metrics,
            "folds": candidate_folds,
            "transfer_holdout": transfer_metrics,
            "dsr": dsr[candidate_id],
            "target_count": len(aggregate_targets[candidate_id]),
            "target_sha256": canonical_target_hash(aggregate_targets[candidate_id]),
            "unexpected_model_fallback_count": sum(
                bool(row["unexpected_model_fallback"])
                for row in target_records
                if row["candidate_id"] == candidate_id
            ),
        }

    role_gates = _evaluate_role_gates(
        candidates,
        calibration=calibration,
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_placebo_evidence,
        llm_contribution_bootstrap=llm_contribution_bootstrap,
        validation_contract=validation_contract,
    )
    benchmark_gates = _evaluate_benchmark_gates(
        candidates,
        benchmark_payload=benchmark_payload,
        benchmark_contract=runtime_contracts["benchmark"],
    )
    candidate_gates = _evaluate_candidate_gates(
        candidates,
        validation_contract,
        benchmark_gates=benchmark_gates,
    )
    for candidate_id in candidates:
        candidates[candidate_id]["role_gate"] = role_gates[candidate_id]
        candidates[candidate_id]["benchmark_gate"] = benchmark_gates[candidate_id]
        candidates[candidate_id]["family_gates"] = candidate_gates[candidate_id]
        candidates[candidate_id]["historical_research_gate_pass"] = bool(
            candidate_gates[candidate_id]["pass"] and role_gates[candidate_id]["pass"]
        )

    cost_reconciliation = _cost_reconciliation(
        aggregate_simulations,
        segment_simulations,
        segments,
        benchmarks=benchmark_simulations,
        tolerance=runtime_contracts["cost_reconciliation_tolerance"],
        expected_event_reason_codes=set(runtime_contracts["cost_event_reason_codes"]),
        expected_cost_bps_by_view=cost_views,
    )
    workflow_pass = bool(
        harness_reconciliation["research_gate_pass"] is True
        and fallback_identity
        and cost_reconciliation["pass"]
        and benchmark_payload["complete"]
        and benchmark_payload["same_cost_engine"]
        and all(
            not frame.isna().any().any()
            and np.isfinite(frame.to_numpy()).all()
            and np.allclose(frame.sum(axis=1).to_numpy(), 1.0, atol=1e-12, rtol=0.0)
            for frame in aggregate_targets.values()
        )
        and all(
            (
                frame.drop(columns=[RESERVE_SYMBOL])
                <= float(specs[candidate_id].portfolio.max_symbol_weight) + 1e-12
            )
            .all()
            .all()
            for candidate_id, frame in aggregate_targets.items()
        )
    )
    pbo_pass = _pbo_gate_pass(
        pbo,
        pbo_config=pbo_config,
        validation_contract=validation_contract,
    )
    statuses = _derive_evaluation_statuses(
        candidates,
        workflow_pass=workflow_pass,
        pbo_pass=pbo_pass,
    )
    selected = statuses["selected_candidate_ids"]
    research_pass = statuses["research_pass"]
    llm_contribution_pass = statuses["llm_contribution_pass"]
    paper_ready_pass = statuses["paper_ready_pass"]
    decision = statuses["decision"]

    trial_rows = _trial_ledger_rows(candidates)
    feature_rows = _dataframe_records(dataset)
    prediction_rows = [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "segment_id": record["segment_id"],
            "candidate_id": record["candidate_id"],
            "model_id": record["model_id"],
            "decision_session": record["decision_session"],
            "symbol": prediction["symbol"],
            "value": prediction["value"],
            "prediction_sha256": record["prediction_sha256"],
        }
        for record in model_records
        for prediction in record["predictions"]
    ]
    prediction_reconciliation = _reconcile_model_prediction_evidence(
        model_records,
        prediction_rows,
    )
    ledger_inventory = {
        name: {"row_count": len(rows), "sha256": _jsonl_sha256(rows)}
        for name, rows in {
            "feature_ledger": feature_rows,
            "prediction_ledger": prediction_rows,
            "daily_return_ledger": daily_return_records,
            "target_ledger": target_records,
            "event_ledger": event_records,
            "benchmark_ledger": benchmark_rows,
            "model_ledger": model_records,
            "trial_ledger": trial_rows,
        }.items()
    }
    if ledger_inventory["daily_return_ledger"]["sha256"] != daily_return_ledger_sha256:
        raise ValueError("R5 daily-return ledger changed after statistical reconciliation")
    model_provenance = _model_provenance_payload(
        model_records,
        prediction_reconciliation=prediction_reconciliation,
        ledger_inventory=ledger_inventory,
        expected_provenance=provenance,
    )
    result_dir = output / "evaluation-run"
    stage_dir = output / f".r5-evaluation-stage-{attempt_binding['sha256'][:16]}"
    if result_dir.exists() or stage_dir.exists():
        raise ValueError("R5 result or staged attempt already exists; overwrite is prohibited")
    stage_dir.mkdir(mode=0o700)
    paths = _evaluation_paths(stage_dir)
    published_paths = _evaluation_paths(result_dir)
    _write_jsonl_atomic(paths["feature_ledger"], feature_rows)
    _write_jsonl_atomic(paths["prediction_ledger"], prediction_rows)
    _write_jsonl_atomic(paths["daily_return_ledger"], daily_return_records)
    _write_jsonl_atomic(paths["target_ledger"], target_records)
    _write_jsonl_atomic(paths["event_ledger"], event_records)
    _write_jsonl_atomic(paths["benchmark_ledger"], benchmark_rows)
    _write_jsonl_atomic(paths["model_ledger"], model_records)
    _write_jsonl_atomic(paths["trial_ledger"], trial_rows)
    _write_json_atomic(paths["cost_reconciliation"], cost_reconciliation)
    _write_json_atomic(paths["model_provenance"], model_provenance)
    child_bindings = {
        name: _binding_for_destination(path, published_paths[name], base)
        for name, path in paths.items()
        if name
        in {
            "feature_ledger",
            "prediction_ledger",
            "daily_return_ledger",
            "target_ledger",
            "event_ledger",
            "benchmark_ledger",
            "model_ledger",
            "trial_ledger",
            "cost_reconciliation",
            "model_provenance",
        }
    }
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "report_type": "multiasset_forward_multimodal_r5_matched_transfer_evaluation",
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": paper_ready_pass,
        "selected_candidate_ids": selected,
        "candidate_count": len(candidates),
        "cumulative_trial_count_lower_bound": runtime_contracts["trial_count_lower_bound"],
        "dsr_governance_trial_count": runtime_contracts["trial_count"],
        "common_window": {"start": aggregate_start, "end": aggregate_end},
        "historical_scope": "globally_exposed_transfer_evidence_not_pristine_promotion_holdout",
        "preflight": preflight,
        "child_artifacts": child_bindings,
        "candidates": candidates,
        "calibration": calibration,
        "family_pbo": pbo,
        "family_pbo_pass": pbo_pass,
        "spec_execution_contract": spec_execution_contract,
        "harness_reconciliation": harness_reconciliation,
        "formula_placebo_evidence": formula_placebo_evidence,
        "llm_contribution_bootstrap": llm_contribution_bootstrap,
        "benchmarks": benchmark_payload,
        "fallback_identity": {
            "R5F01_equals_R5M01": fallback_identity,
            "R5M01_target_sha256": canonical_target_hash(aggregate_targets["R5M01"]),
            "R5F01_target_sha256": canonical_target_hash(aggregate_targets["R5F01"]),
        },
        "cost_reconciliation": cost_reconciliation,
        "evidence_reconciliation": {
            "ledger_inventory": ledger_inventory,
            "prediction_reconciliation": prediction_reconciliation,
            "pbo_reproduced_from_daily_return_ledger": True,
            "dsr_reproduced_from_daily_return_ledger": True,
        },
        "forward_requirements": runtime_contracts["forward_requirements"],
    }
    staged_ledger_verification = _verify_staged_ledger_bundle(
        paths,
        payload,
        runtime_contracts,
        specs,
        panel,
        root=base,
        locked_artifact_sha256_by_path=locked_artifact_hashes,
        expected_model_provenance=provenance,
    )
    payload["evidence_reconciliation"]["staged_ledger_verification"] = staged_ledger_verification
    _write_json_atomic(paths["evaluation"], payload)
    _write_text_atomic(paths["evaluation_markdown"], _render_markdown(payload))
    _write_text_atomic(paths["decision_record"], _render_decision_record(payload))
    receipt_children = {
        name: _binding_for_destination(path, published_paths[name], base)
        for name, path in paths.items()
        if name not in {"receipt", "evaluation_anchor"} and path.is_file()
    }
    receipt = {
        "schema_version": 3,
        "receipt_contract": "multiasset_forward_multimodal_r5_v3",
        "iter_id": ITER_ID,
        "evidence_publication_status": "complete",
        "decision": decision,
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": paper_ready_pass,
        "preregistration_lock": _file_binding(output / "lock-set/preregistration-lock.json", base),
        "runner_lock": _file_binding(output / "lock-set/runner-lock.json", base),
        "lock_anchor": _file_binding(output / "lock-set/lock-anchor.json", base),
        "evaluation_attempt": attempt_binding,
        "children": receipt_children,
        "prepublication_checks": {
            "prebacktest_dossier_status": "ok",
            "workflow_pass": workflow_pass,
            "fallback_identity": fallback_identity,
            "cost_reconciliation_pass": cost_reconciliation["pass"],
            "benchmark_family_complete": benchmark_payload["complete"],
            "harness_reconciliation_pass": harness_reconciliation["research_gate_pass"],
            "staged_ledger_verification_pass": staged_ledger_verification["pass"],
        },
    }
    _write_json_atomic(paths["receipt"], receipt)
    evaluation_anchor = _evaluation_anchor_payload(
        root=base,
        receipt_source=paths["receipt"],
        receipt_destination=published_paths["receipt"],
        anchor_destination=published_paths["evaluation_anchor"],
        preregistration_lock_path=output / "lock-set/preregistration-lock.json",
        runner_lock_path=output / "lock-set/runner-lock.json",
        lock_anchor_path=output / "lock-set/lock-anchor.json",
        evaluation_attempt_path=output / "evaluation-attempt.json",
    )
    _write_json_exclusive_readonly(paths["evaluation_anchor"], evaluation_anchor)
    _seal_evidence_directory(stage_dir)
    _verify_staged_publication(
        paths,
        published_paths,
        payload,
        receipt,
        evaluation_anchor,
        base,
    )
    staged_final_validation = validate_iteration_dossier(
        ITER_ID,
        base,
        stage="final",
        staged_evaluation_dir=stage_dir,
    )
    if not staged_final_validation.ok:
        raise ValueError(
            "R5 staged final dossier blocked: " + ", ".join(staged_final_validation.blocked)
        )
    _reverify_locked_inputs(base, preflight)
    custody = _write_r5_evaluation_custody(
        root=base,
        custody_dir=custody_dir,
        stage_dir=stage_dir,
        evaluation_anchor=evaluation_anchor,
        preflight=preflight,
    )
    _publish_directory_exclusive(stage_dir, result_dir)
    final_validation = validate_iteration_dossier(ITER_ID, base, stage="final")
    if not final_validation.ok:
        raise ValueError("R5 final dossier blocked: " + ", ".join(final_validation.blocked))
    return R5EvaluationResult(
        evaluation_path=published_paths["evaluation"],
        evaluation_markdown_path=published_paths["evaluation_markdown"],
        receipt_path=published_paths["receipt"],
        evaluation_anchor_path=published_paths["evaluation_anchor"],
        evaluation_anchor_sha256=_sha256_file(published_paths["evaluation_anchor"]),
        operator_evaluation_anchor_sha256=evaluation_anchor["operator_evaluation_anchor_sha256"],
        custody_receipt_path=custody.receipt_path,
        custody_receipt_sha256=custody.receipt_sha256,
        payload=payload,
    )


def finalize_multiasset_forward_multimodal_r5(
    root: Path,
    *,
    expected_lock_anchor_sha256: str,
    custody_dir: Path,
) -> R5EvaluationResult:
    """Publish an already-computed sealed R5 bundle without rerunning price computation."""
    base = root.resolve()
    output = base / ITERATION_DIR
    result_dir = output / "evaluation-run"
    if result_dir.exists():
        return _finalize_r5_published_result(
            base,
            result_dir=result_dir,
            expected_lock_anchor_sha256=expected_lock_anchor_sha256,
            custody_dir=custody_dir,
        )

    stages = sorted(output.glob(".r5-evaluation-stage-*"))
    if len(stages) != 1:
        raise ValueError(
            "R5 publication recovery requires exactly one sealed staged evaluation; "
            "price recomputation remains prohibited"
        )
    stage_dir = stages[0]
    paths = _evaluation_paths(stage_dir)
    published_paths = _evaluation_paths(result_dir)
    payload = _load_json(paths["evaluation"])
    receipt = _load_json(paths["receipt"])
    evaluation_anchor = _load_json(paths["evaluation_anchor"])
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        raise ValueError("R5 staged recovery preflight is missing")
    _verify_recovery_lock_identity(
        base,
        preflight=preflight,
        expected_lock_anchor_sha256=expected_lock_anchor_sha256,
        custody_dir=custody_dir,
    )
    attempt_binding = preflight.get("evaluation_attempt")
    if not isinstance(attempt_binding, dict) or stage_dir.name != (
        f".r5-evaluation-stage-{str(attempt_binding.get('sha256') or '')[:16]}"
    ):
        raise ValueError("R5 staged recovery directory is not bound to the reserved attempt")
    _verify_staged_publication(
        paths,
        published_paths,
        payload,
        receipt,
        evaluation_anchor,
        base,
    )
    staged_validation = validate_iteration_dossier(
        ITER_ID,
        base,
        stage="final",
        staged_evaluation_dir=stage_dir,
    )
    if not staged_validation.ok:
        raise ValueError(
            "R5 staged recovery dossier blocked: " + ", ".join(staged_validation.blocked)
        )
    _reverify_locked_inputs(base, preflight)
    custody = _write_r5_evaluation_custody(
        root=base,
        custody_dir=custody_dir,
        stage_dir=stage_dir,
        evaluation_anchor=evaluation_anchor,
        preflight=preflight,
    )
    _clear_stale_r5_publish_marker(output / ".evaluation-run-publish.lock")
    _publish_directory_exclusive(stage_dir, result_dir)
    final_validation = validate_iteration_dossier(ITER_ID, base, stage="final")
    if not final_validation.ok:
        raise ValueError(
            "R5 recovered final dossier blocked: " + ", ".join(final_validation.blocked)
        )
    return _r5_evaluation_result(
        result_dir=result_dir,
        custody=custody,
    )


def classify_multiasset_forward_multimodal_r5_state(root: Path) -> dict[str, Any]:
    output = root.resolve() / ITERATION_DIR
    result_dir = output / "evaluation-run"
    attempt_path = output / "evaluation-attempt.json"
    marker = output / ".evaluation-run-publish.lock"
    stages = sorted(output.glob(".r5-evaluation-stage-*"))
    if result_dir.is_dir() and not result_dir.is_symlink():
        state = "published_requires_validation"
    elif len(stages) == 1 and _is_sealed_evaluation_directory(stages[0]):
        state = "sealed_stage_publication_recovery_only"
    elif stages:
        state = "incomplete_stage_terminal_abort"
    elif attempt_path.exists():
        state = "reserved_attempt_terminal_abort"
    else:
        state = "not_started"
    return {
        "iter_id": ITER_ID,
        "state": state,
        "attempt_exists": attempt_path.exists(),
        "result_exists": result_dir.exists(),
        "publish_marker_exists": marker.exists(),
        "staged_directories": [path.name for path in stages],
        "price_recomputation_allowed": state == "not_started",
        "publication_only_recovery_allowed": state
        in {"sealed_stage_publication_recovery_only", "published_requires_validation"},
    }


def _finalize_r5_published_result(
    root: Path,
    *,
    result_dir: Path,
    expected_lock_anchor_sha256: str,
    custody_dir: Path,
) -> R5EvaluationResult:
    paths = _evaluation_paths(result_dir)
    payload = _load_json(paths["evaluation"])
    evaluation_anchor = _load_json(paths["evaluation_anchor"])
    preflight = payload.get("preflight")
    if not isinstance(preflight, dict):
        raise ValueError("R5 published recovery preflight is missing")
    _verify_recovery_lock_identity(
        root,
        preflight=preflight,
        expected_lock_anchor_sha256=expected_lock_anchor_sha256,
        custody_dir=custody_dir,
    )
    _reverify_locked_inputs(root, preflight)
    final_validation = validate_iteration_dossier(ITER_ID, root, stage="final")
    if not final_validation.ok:
        raise ValueError(
            "R5 published final dossier blocked: " + ", ".join(final_validation.blocked)
        )
    custody = _write_r5_evaluation_custody(
        root=root,
        custody_dir=custody_dir,
        stage_dir=result_dir,
        evaluation_anchor=evaluation_anchor,
        preflight=preflight,
    )
    return _r5_evaluation_result(result_dir=result_dir, custody=custody)


def _verify_recovery_lock_identity(
    root: Path,
    *,
    preflight: dict[str, Any],
    expected_lock_anchor_sha256: str,
    custody_dir: Path,
) -> None:
    if (
        not _is_sha256(expected_lock_anchor_sha256)
        or preflight.get("operator_lock_anchor_sha256") != expected_lock_anchor_sha256
    ):
        raise ValueError("R5 recovery lock anchor does not match the staged evaluation")
    custody = _verify_r5_lock_custody(
        root=root,
        custody_dir=custody_dir,
        lock_anchor_sha256=expected_lock_anchor_sha256,
    )
    if (
        preflight.get("lock_custody_receipt_sha256") != custody.receipt_sha256
        or preflight.get("lock_custody_bundle_sha256") != custody.bundle_sha256
    ):
        raise ValueError("R5 recovery lock custody differs from the evaluation preflight")


def _r5_evaluation_result(
    *,
    result_dir: Path,
    custody: ExternalCustodyRecord,
) -> R5EvaluationResult:
    paths = _evaluation_paths(result_dir)
    payload = _load_json(paths["evaluation"])
    anchor = _load_json(paths["evaluation_anchor"])
    return R5EvaluationResult(
        evaluation_path=paths["evaluation"],
        evaluation_markdown_path=paths["evaluation_markdown"],
        receipt_path=paths["receipt"],
        evaluation_anchor_path=paths["evaluation_anchor"],
        evaluation_anchor_sha256=_sha256_file(paths["evaluation_anchor"]),
        operator_evaluation_anchor_sha256=str(
            anchor.get("operator_evaluation_anchor_sha256") or ""
        ),
        custody_receipt_path=custody.receipt_path,
        custody_receipt_sha256=custody.receipt_sha256,
        payload=payload,
    )


def _is_sealed_evaluation_directory(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o222:
        return False
    entries = list(path.iterdir())
    return {entry.name for entry in entries} == set(R5_EVALUATION_FILENAMES.values()) and all(
        not entry.is_symlink() and entry.is_file() and not entry.stat().st_mode & 0o222
        for entry in entries
    )


def _clear_stale_r5_publish_marker(path: Path) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.is_file():
        raise ValueError("R5 publication marker is not a regular file")
    try:
        text = path.read_text(encoding="ascii").strip()
        pid = int(text.removeprefix("pid="))
    except (OSError, ValueError) as exc:
        raise ValueError("R5 publication marker is malformed") from exc
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        path.unlink()
        _fsync_directory(path.parent)
        return
    except PermissionError:
        pass
    raise ValueError("R5 publication marker belongs to a live process; recovery refused")


def _reserve_evaluation_attempt(root: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    path = root / ITERATION_DIR / "evaluation-attempt.json"
    payload = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "reserved_before_first_price_parse",
        "reserved_at": datetime.now(UTC).isoformat(),
        "operator_lock_anchor_sha256": preflight["operator_lock_anchor_sha256"],
        "preregistration_lock_sha256": preflight["preregistration_lock_sha256"],
        "runner_lock_sha256": preflight["runner_lock_sha256"],
        "data_manifest_sha256": preflight["data_manifest_sha256"],
        "lock_custody_receipt_sha256": preflight["lock_custody_receipt_sha256"],
        "lock_custody_bundle_sha256": preflight["lock_custody_bundle_sha256"],
        "rerun_policy": "any_existing_attempt_blocks_all_future_evaluation_attempts",
    }
    content = _canonical_json_bytes(payload) + b"\n"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError as exc:
        raise ValueError("R5 evaluation attempt already exists; rerun refused") from exc
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write R5 evaluation attempt receipt")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)
    return _file_binding(path, root)


def _evaluation_anchor_payload(
    *,
    root: Path,
    receipt_source: Path,
    receipt_destination: Path,
    anchor_destination: Path,
    preregistration_lock_path: Path,
    runner_lock_path: Path,
    lock_anchor_path: Path,
    evaluation_attempt_path: Path,
) -> dict[str, Any]:
    lock_anchor = _load_json(lock_anchor_path)
    operator_lock_anchor_sha256 = lock_anchor.get("operator_lock_anchor_sha256")
    if not _is_sha256(operator_lock_anchor_sha256):
        raise ValueError("R5 operator lock anchor identity is invalid")
    subject = {
        "schema_version": 1,
        "anchor_contract": EVALUATION_ANCHOR_CONTRACT,
        "iter_id": ITER_ID,
        "status": "complete_for_external_hash_custody",
        "anchor_path": _relpath(anchor_destination, root),
        "receipt": _binding_for_destination(receipt_source, receipt_destination, root),
        "preregistration_lock": _file_binding(preregistration_lock_path, root),
        "runner_lock": _file_binding(runner_lock_path, root),
        "lock_anchor": _file_binding(lock_anchor_path, root),
        "evaluation_attempt": _file_binding(evaluation_attempt_path, root),
        "operator_lock_anchor_sha256": operator_lock_anchor_sha256,
        "custody_requirement": (
            "record_evaluation_anchor_file_sha256_and_operator_subject_sha256_"
            "outside_the_mutable_worktree"
        ),
        "local_read_only_mode_is_not_independent_custody": True,
    }
    return {
        **subject,
        "operator_evaluation_anchor_sha256": hashlib.sha256(
            _canonical_json_bytes(subject)
        ).hexdigest(),
    }


def _write_json_exclusive_readonly(path: Path, payload: Any) -> None:
    content = _canonical_json_bytes(payload) + b"\n"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o400)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write R5 exclusive read-only JSON")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _seal_evidence_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("R5 staged evidence directory is invalid")
    entries = list(path.iterdir())
    if not entries or any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("R5 staged evidence contains a non-regular file")
    for entry in entries:
        entry.chmod(0o400)
    path.chmod(0o500)
    _fsync_directory(path)
    _fsync_directory(path.parent)


def _preflight(
    root: Path,
    *,
    expected_lock_anchor_sha256: str,
    custody_dir: Path,
) -> dict[str, Any]:
    validation = validate_iteration_dossier(ITER_ID, root, stage="pre-backtest")
    if not validation.ok:
        raise ValueError("R5 pre-backtest dossier blocked: " + ", ".join(validation.blocked))
    output = root / ITERATION_DIR
    result_dir = output / "evaluation-run"
    attempt_path = output / "evaluation-attempt.json"
    publish_marker = output / ".evaluation-run-publish.lock"
    staged_attempts = sorted(output.glob(".r5-evaluation-stage-*"))
    if result_dir.exists() or attempt_path.exists() or publish_marker.exists() or staged_attempts:
        raise ValueError("R5 result or staged attempt already exists; reruns are prohibited")

    lock_anchor_path = output / "lock-set/lock-anchor.json"
    lock_anchor, lock_anchor_file_sha256 = _load_json_with_sha256(lock_anchor_path)
    if not _is_sha256(expected_lock_anchor_sha256):
        raise ValueError("R5 expected lock anchor must be a lowercase SHA-256")

    preregistration_path = output / "lock-set/preregistration-lock.json"
    preregistration, preregistration_sha256 = _load_json_with_sha256(
        preregistration_path,
        expected_sha256=str(lock_anchor.get("preregistration_lock_sha256") or ""),
    )
    if preregistration.get("iter_id") != ITER_ID or preregistration.get("status") != (
        "behavior_contracts_locked_before_first_r5_price_calculation"
    ):
        raise ValueError("R5 preregistration lock identity is invalid")
    for binding in preregistration.get("artifacts", []):
        _verify_file_binding(root, binding)
    for binding in preregistration.get("specs", []):
        path = _verify_file_binding(
            root,
            {"path": binding.get("path"), "sha256": binding.get("file_sha256")},
        )
        spec = _load_strategy_spec_stable(
            path,
            expected_sha256=str(binding.get("file_sha256") or ""),
        )
        if strategy_content_hash(spec) != binding.get("semantic_sha256"):
            raise ValueError(f"R5 semantic spec hash mismatch: {binding.get('path')}")

    runner_path = output / "lock-set/runner-lock.json"
    runner, runner_sha256 = _load_json_with_sha256(
        runner_path,
        expected_sha256=str(lock_anchor.get("runner_lock_sha256") or ""),
    )
    if runner.get("iter_id") != ITER_ID or runner.get("status") != (
        "implementation_locked_before_first_r5_price_calculation"
    ):
        raise ValueError("R5 runner lock identity is invalid")
    for binding in runner.get("files", []):
        _verify_file_binding(root, binding)
    if runner.get("runtime") != _current_runtime():
        raise ValueError("R5 locked runtime package versions changed")

    anchor_subject = {
        "iter_id": ITER_ID,
        "preregistration_lock_sha256": preregistration_sha256,
        "runner_lock_sha256": runner_sha256,
    }
    computed_anchor = hashlib.sha256(_canonical_json_bytes(anchor_subject)).hexdigest()
    if lock_anchor.get("schema_version") != 1 or any(
        lock_anchor.get(key) != value for key, value in anchor_subject.items()
    ):
        raise ValueError("R5 lock anchor bindings are invalid")
    if lock_anchor.get("operator_lock_anchor_sha256") != computed_anchor:
        raise ValueError("R5 lock anchor payload is invalid")
    if expected_lock_anchor_sha256 != computed_anchor:
        raise ValueError("R5 operator-provided lock anchor does not match frozen bytes")

    locked_artifact_hashes = _binding_sha256_by_path(
        preregistration.get("artifacts"),
        label="R5 preregistration artifacts",
    )
    harness_reconciliation = preregistration.get("harness_reconciliation")
    if (
        not isinstance(harness_reconciliation, dict)
        or harness_reconciliation.get("reconciliation_contract")
        != R5_HARNESS_RECONCILIATION_CONTRACT
        or harness_reconciliation.get("iter_id") != ITER_ID
        or harness_reconciliation.get("research_gate_pass") is not True
        or harness_reconciliation.get("empirical_execution_evidence_pass") is not False
        or harness_reconciliation.get("paper_readiness_evidence_pass") is not False
    ):
        raise ValueError("R5 preregistration harness reconciliation is invalid")
    harness_reconciliation_sha256 = hashlib.sha256(
        _canonical_json_bytes(harness_reconciliation)
    ).hexdigest()
    data_contract_path = output / "data-contract.json"
    data_contract_relative = _relpath(data_contract_path, root)
    data_contract, data_contract_sha256 = _load_json_with_sha256(
        data_contract_path,
        expected_sha256=locked_artifact_hashes.get(data_contract_relative),
    )
    manifest_relative = str(data_contract.get("snapshot_manifest_path") or "")
    parent_binding_relative = str(data_contract.get("bound_parent_snapshot_path") or "")
    manifest_path = _repo_file_path(root, manifest_relative)
    parent_binding_path = _repo_file_path(root, parent_binding_relative)
    manifest_sha256 = _sha256_file(manifest_path)
    parent_binding_sha256 = _sha256_file(parent_binding_path)
    if manifest_sha256 != data_contract.get("snapshot_manifest_sha256"):
        raise ValueError("R5 data manifest hash differs from data contract")
    if locked_artifact_hashes.get(manifest_relative) != manifest_sha256:
        raise ValueError("R5 data manifest differs from preregistration lock")
    if parent_binding_sha256 != data_contract.get("bound_parent_snapshot_sha256"):
        raise ValueError("R5 parent snapshot binding hash differs from data contract")
    if locked_artifact_hashes.get(parent_binding_relative) != parent_binding_sha256:
        raise ValueError("R5 parent snapshot binding differs from preregistration lock")
    lock_custody = _verify_r5_lock_custody(
        root=root,
        custody_dir=custody_dir,
        lock_anchor_sha256=computed_anchor,
    )
    return {
        "status": "ok",
        "dossier_checked_at": validation.checked_at.isoformat(),
        "preregistration_lock_path": _relpath(preregistration_path, root),
        "preregistration_lock_sha256": preregistration_sha256,
        "runner_lock_path": _relpath(runner_path, root),
        "runner_lock_sha256": runner_sha256,
        "lock_anchor_path": _relpath(lock_anchor_path, root),
        "lock_anchor_file_sha256": lock_anchor_file_sha256,
        "operator_lock_anchor_sha256": computed_anchor,
        "harness_reconciliation_sha256": harness_reconciliation_sha256,
        "candidate_manifest_path": _relpath(output / "candidate-manifest.json", root),
        "candidate_manifest_sha256": locked_artifact_hashes[
            _relpath(output / "candidate-manifest.json", root)
        ],
        "data_contract_path": _relpath(data_contract_path, root),
        "data_contract_sha256": data_contract_sha256,
        "data_manifest_path": _relpath(manifest_path, root),
        "data_manifest_sha256": manifest_sha256,
        "parent_snapshot_binding_path": _relpath(parent_binding_path, root),
        "parent_snapshot_binding_sha256": parent_binding_sha256,
        "lock_custody_receipt_sha256": lock_custody.receipt_sha256,
        "lock_custody_bundle_sha256": lock_custody.bundle_sha256,
    }


def _stitched_fold_returns(
    simulations: dict[str, dict[str, dict[str, ExactSimulationResult]]],
    folds: list[dict[str, Any]],
) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {}
    for candidate_id in SPEC_PATHS:
        rows = []
        for fold in folds:
            fold_id = str(fold["fold_id"])
            daily = simulations[candidate_id][fold_id]["primary_10bps"].daily
            rows.append(
                pd.Series(
                    daily["net_return"].to_numpy(dtype=float),
                    index=pd.Index(daily["interval_start"].astype(str), name="interval_start"),
                )
            )
        stitched = pd.concat(rows)
        if stitched.index.has_duplicates:
            raise ValueError(f"duplicate stitched fold return session for {candidate_id}")
        columns[candidate_id] = stitched
    frame = pd.DataFrame(columns)
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy()).all():
        raise ValueError("stitched R5 fold return matrix is incomplete")
    return frame


def _calibration_payload(
    calibration_by_segment: dict[str, pd.DataFrame],
    folds: list[dict[str, Any]],
    *,
    required_joint_passing_fold_count: int,
    probability_clip: float,
    slope_min: float,
    slope_max: float,
    expected_observation_count_by_fold: dict[str, int],
    minimum_class_count: int,
) -> dict[str, Any]:
    if required_joint_passing_fold_count < 1 or required_joint_passing_fold_count > len(folds):
        raise ValueError("R5 calibration fold threshold is outside the frozen fold count")
    fold_ids = [str(fold["fold_id"]) for fold in folds]
    if set(expected_observation_count_by_fold) != set(fold_ids) or any(
        count < 3 for count in expected_observation_count_by_fold.values()
    ):
        raise ValueError("R5 calibration observation contract is invalid")
    if minimum_class_count < 1:
        raise ValueError("R5 calibration class-count contract is invalid")
    rows: dict[str, Any] = {}
    for fold in folds:
        fold_id = str(fold["fold_id"])
        frame = calibration_by_segment.get(fold_id, pd.DataFrame())
        if frame.empty:
            rows[fold_id] = {
                "observation_count": 0,
                "expected_observation_count": expected_observation_count_by_fold[fold_id],
                "observation_count_match": False,
                "positive_label_count": 0,
                "negative_label_count": 0,
                "minimum_observation_count": expected_observation_count_by_fold[fold_id],
                "minimum_class_count": minimum_class_count,
                "model_brier_score": None,
                "training_base_probability_brier_score": None,
                "calibration_slope": None,
                "calibration_failure_reason": "no_valid_fold_predictions",
                "joint_gate_pass": False,
            }
            continue
        rows[fold_id] = calibration_metrics(
            frame["label"],
            frame["probability"],
            frame["training_base_probability"],
            clip=probability_clip,
            slope_min=slope_min,
            slope_max=slope_max,
            minimum_observation_count=expected_observation_count_by_fold[fold_id],
            minimum_class_count=minimum_class_count,
        )
        rows[fold_id]["expected_observation_count"] = expected_observation_count_by_fold[fold_id]
        rows[fold_id]["observation_count_match"] = (
            rows[fold_id]["observation_count"] == expected_observation_count_by_fold[fold_id]
        )
        if not rows[fold_id]["observation_count_match"]:
            rows[fold_id]["joint_gate_pass"] = False
            rows[fold_id]["calibration_failure_reason"] = "observation_count_mismatch"
    passing = sum(bool(row["joint_gate_pass"]) for row in rows.values())
    all_observation_counts_match = all(
        bool(row["observation_count_match"]) for row in rows.values()
    )
    return {
        "candidate_id": "R5M02",
        "folds": rows,
        "joint_passing_fold_count": passing,
        "required_joint_passing_fold_count": required_joint_passing_fold_count,
        "probability_clip": probability_clip,
        "calibration_slope_min": slope_min,
        "calibration_slope_max": slope_max,
        "expected_observation_count_by_fold": expected_observation_count_by_fold,
        "minimum_class_count_per_fold": minimum_class_count,
        "all_observation_counts_match": all_observation_counts_match,
        "pass": bool(all_observation_counts_match and passing >= required_joint_passing_fold_count),
    }


def _benchmark_family_exact(
    opens: pd.DataFrame,
    *,
    monthly_sessions: pd.DatetimeIndex,
    start: str,
    end: str,
    primary_cost_bps: float,
    stress_cost_bps: float,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, ExactSimulationResult]],
    dict[str, pd.DataFrame],
]:
    columns = opens.columns
    sectors = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]

    def targets(weights: dict[str, float], *, monthly: bool) -> pd.DataFrame:
        row = {symbol: float(weights.get(symbol, 0.0)) for symbol in columns}
        index = monthly_sessions if monthly else pd.DatetimeIndex([pd.Timestamp(start)])
        return pd.DataFrame([row] * len(index), index=index, columns=columns)

    definitions = {
        "same_symbol_buy_hold_SPY": targets({"SPY": 1.0}, monthly=False),
        "equal_weight_universe": targets(
            {symbol: 1.0 / len(RANKABLE_SYMBOLS) for symbol in RANKABLE_SYMBOLS},
            monthly=True,
        ),
        "market_proxy": targets({"SPY": 1.0}, monthly=False),
        "sector_theme_proxy": targets(
            {symbol: 1.0 / len(sectors) for symbol in sectors}, monthly=True
        ),
        "balanced_proxy": targets({"SPY": 0.6, "IEF": 0.4}, monthly=True),
        "cash_proxy": targets({RESERVE_SYMBOL: 1.0}, monthly=False),
    }
    spy_identity = canonical_target_bytes(definitions["same_symbol_buy_hold_SPY"]) == (
        canonical_target_bytes(definitions["market_proxy"])
    )
    if not spy_identity:
        raise ValueError("R5 SPY buy-and-hold and market proxy targets differ")
    simulations: dict[str, dict[str, ExactSimulationResult]] = {}
    payload: dict[str, Any] = {}
    for benchmark_id, target_frame in definitions.items():
        simulations[benchmark_id] = {}
        payload[benchmark_id] = {
            "promotion_gate": False,
            "required_evidence": True,
            "cost_views": {},
        }
        for view_name, bps in {
            "primary_10bps": primary_cost_bps,
            "stress_20bps": stress_cost_bps,
        }.items():
            simulation = simulate_exact_target_portfolio(
                opens, target_frame, cost_bps=bps, start=start, end=end
            )
            simulations[benchmark_id][view_name] = simulation
            payload[benchmark_id]["cost_views"][view_name] = simulation.metrics

    single_symbol: dict[str, ExactSimulationResult] = {}
    for symbol in columns:
        simulation = simulate_exact_target_portfolio(
            opens,
            targets({str(symbol): 1.0}, monthly=False),
            cost_bps=primary_cost_bps,
            start=start,
            end=end,
        )
        single_symbol[str(symbol)] = simulation
    best_symbol = sorted(
        single_symbol,
        key=lambda symbol: (
            -float(single_symbol[symbol].metrics["total_return_pct"]),
            symbol,
        ),
    )[0]
    best_target = targets({best_symbol: 1.0}, monthly=False)
    definitions["ex_post_best_symbol_report_only"] = best_target
    simulations["ex_post_best_symbol_report_only"] = {"primary_10bps": single_symbol[best_symbol]}
    payload["ex_post_best_symbol_report_only"] = {
        "promotion_gate": False,
        "selected_symbol": best_symbol,
        "cost_views": {"primary_10bps": single_symbol[best_symbol].metrics},
    }
    return (
        {
            "complete": spy_identity
            and set(payload)
            == {
                "same_symbol_buy_hold_SPY",
                "equal_weight_universe",
                "market_proxy",
                "sector_theme_proxy",
                "balanced_proxy",
                "cash_proxy",
                "ex_post_best_symbol_report_only",
            },
            "same_cost_engine": True,
            "identity_checks": {
                "same_symbol_buy_hold_SPY_equals_market_proxy": spy_identity,
                "same_symbol_buy_hold_SPY_target_sha256": canonical_target_hash(
                    definitions["same_symbol_buy_hold_SPY"]
                ),
                "market_proxy_target_sha256": canonical_target_hash(definitions["market_proxy"]),
            },
            "risk_free_treatment": "raw_and_BIL_excess_Sharpe_reported_separately",
            "results": payload,
        },
        simulations,
        definitions,
    )


def _llm_bootstrap_role_gate_evidence(
    evidence: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = str(contract.get("candidate_id") or "")
    comparator_ids = list(map(str, contract.get("comparator_ids") or []))
    expected_comparison_ids = [
        f"{candidate_id}_minus_{comparator_id}" for comparator_id in comparator_ids
    ]
    comparisons = evidence.get("comparisons")
    config_match = bool(
        isinstance(evidence.get("config"), dict)
        and _canonical_json_bytes(evidence["config"]) == _canonical_json_bytes(contract)
        and evidence.get("config_sha256")
        == hashlib.sha256(_canonical_json_bytes(contract)).hexdigest()
    )
    comparison_ids_match = bool(
        isinstance(comparisons, dict) and list(comparisons) == expected_comparison_ids
    )
    actual_valid_count = evidence.get("valid_resample_count")
    required_valid_count = contract.get("required_valid_resample_count")
    valid_resample_count_match = bool(
        type(actual_valid_count) is int
        and type(required_valid_count) is int
        and actual_valid_count == required_valid_count
    )
    comparison_passes: dict[str, bool] = {}
    comparison_reported_pass_matches: dict[str, bool] = {}
    comparison_field_contract_matches: dict[str, bool] = {}
    for comparison_id, comparator_id in zip(
        expected_comparison_ids,
        comparator_ids,
        strict=True,
    ):
        row = comparisons.get(comparison_id) if isinstance(comparisons, dict) else None
        derived_pass = False
        reported_pass_matches = False
        field_contract_match = False
        if isinstance(row, dict):
            try:
                candidate_sharpe = float(row["candidate_observed_annualized_sharpe"])
                comparator_sharpe = float(row["comparator_observed_annualized_sharpe"])
                observed_delta = float(row["observed_annualized_sharpe_delta"])
                minimum_delta = float(row["minimum_observed_delta"])
                lower_bound = float(row["lower_confidence_bound"])
                one_sided_alpha = float(row["one_sided_alpha"])
                row_valid_count = row["valid_resample_count"]
                lower_index = row["lower_percentile_sorted_zero_based_index"]
            except (KeyError, TypeError, ValueError):
                pass
            else:
                numeric_values = (
                    candidate_sharpe,
                    comparator_sharpe,
                    observed_delta,
                    minimum_delta,
                    lower_bound,
                    one_sided_alpha,
                )
                point_estimate_pass = observed_delta >= float(
                    contract["point_estimate_minimum_delta"]
                )
                lower_bound_pass = lower_bound > 0.0
                field_contract_match = bool(
                    all(math.isfinite(value) for value in numeric_values)
                    and row.get("candidate_id") == candidate_id
                    and row.get("comparator_id") == comparator_id
                    and math.isclose(
                        observed_delta,
                        candidate_sharpe - comparator_sharpe,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    and minimum_delta == float(contract["point_estimate_minimum_delta"])
                    and type(row_valid_count) is int
                    and row_valid_count == required_valid_count
                    and type(lower_index) is int
                    and lower_index == int(contract["lower_percentile_sorted_zero_based_index"])
                    and one_sided_alpha == float(contract["per_comparison_one_sided_alpha"])
                    and row.get("point_estimate_pass") is point_estimate_pass
                    and row.get("lower_confidence_bound_strictly_positive") is lower_bound_pass
                )
                derived_pass = bool(
                    field_contract_match and point_estimate_pass and lower_bound_pass
                )
                reported_pass_matches = row.get("pass") is derived_pass
        comparison_passes[comparison_id] = derived_pass
        comparison_reported_pass_matches[comparison_id] = reported_pass_matches
        comparison_field_contract_matches[comparison_id] = field_contract_match
    derived_top_level_pass = bool(expected_comparison_ids and all(comparison_passes.values()))
    reported_top_level_pass_matches = evidence.get("pass") is derived_top_level_pass
    return {
        "config_match": config_match,
        "comparison_ids_match": comparison_ids_match,
        "comparison_field_contract_matches": comparison_field_contract_matches,
        "comparison_passes": comparison_passes,
        "comparison_reported_pass_matches": comparison_reported_pass_matches,
        "valid_resample_count_match": valid_resample_count_match,
        "reported_top_level_pass_matches": reported_top_level_pass_matches,
        "pass": bool(
            config_match
            and comparison_ids_match
            and valid_resample_count_match
            and all(comparison_field_contract_matches.values())
            and all(comparison_passes.values())
            and all(comparison_reported_pass_matches.values())
            and reported_top_level_pass_matches
        ),
    }


def _evaluate_role_gates(
    candidates: dict[str, Any],
    *,
    calibration: dict[str, Any],
    aggregate_targets: dict[str, pd.DataFrame],
    segment_targets: dict[str, dict[str, pd.DataFrame]],
    formula_placebo_evidence: dict[str, Any],
    llm_contribution_bootstrap: dict[str, Any],
    validation_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fold_ids = sorted(candidates["R5D01"]["folds"])
    role_contracts = validation_contract["role_gates"]

    def fold_sharpe(candidate_id: str, fold_id: str) -> float:
        return float(
            candidates[candidate_id]["folds"][fold_id]["primary_10bps"]["annualized_sharpe"]
        )

    def transfer_sharpe(candidate_id: str) -> float:
        return float(
            candidates[candidate_id]["transfer_holdout"]["primary_10bps"]["annualized_sharpe"]
        )

    m01_wins = [fold_sharpe("R5M01", fold) > fold_sharpe("R5D01", fold) for fold in fold_ids]
    l01_wins = [fold_sharpe("R5L01", fold) > fold_sharpe("R5D01", fold) for fold in fold_ids]
    c01_wins = [
        fold_sharpe("R5C01", fold) > max(fold_sharpe("R5M01", fold), fold_sharpe("R5P01", fold))
        for fold in fold_ids
    ]
    formula_ordering = bool(
        formula_placebo_evidence["formula_composite_nonconstant_pass"]
        and canonical_target_hash(aggregate_targets["R5L01"])
        != canonical_target_hash(aggregate_targets["R5D01"])
    )
    identity = canonical_target_bytes(aggregate_targets["R5F01"]) == canonical_target_bytes(
        aggregate_targets["R5M01"]
    )
    m02_difference_count = _target_difference_count(
        aggregate_targets["R5M02"], aggregate_targets["R5M01"]
    )
    m02_different_folds = [
        fold_id
        for fold_id in fold_ids
        if _target_difference_count(
            segment_targets[fold_id]["R5M02"],
            segment_targets[fold_id]["R5M01"],
        )
        > 0
    ]
    m02_hash_difference = canonical_target_hash(aggregate_targets["R5M02"]) != (
        canonical_target_hash(aggregate_targets["R5M01"])
    )
    m02_contract = role_contracts["R5M02"]
    m02_calibration_contract_match = bool(
        int(calibration.get("required_joint_passing_fold_count", -1))
        == int(m02_contract["joint_brier_and_slope_passing_folds_min"])
        and float(calibration.get("probability_clip", math.nan))
        == float(m02_contract["probability_clip"])
        and float(calibration.get("calibration_slope_min", math.nan))
        == float(m02_contract["calibration_slope_min"])
        and float(calibration.get("calibration_slope_max", math.nan))
        == float(m02_contract["calibration_slope_max"])
        and calibration.get("expected_observation_count_by_fold")
        == m02_contract["expected_observation_count_by_fold"]
        and int(calibration.get("minimum_class_count_per_fold", -1))
        == int(m02_contract["minimum_class_count_per_fold"])
        and calibration.get("all_observation_counts_match") is True
    )
    m02_behavior_pass = bool(
        m02_difference_count >= int(m02_contract["minimum_applied_gate_decisions"])
        and len(m02_different_folds)
        >= int(m02_contract["minimum_folds_with_target_difference_from_R5M01"])
        and (
            m02_hash_difference
            if bool(m02_contract["aggregate_target_hash_must_differ_from_R5M01"])
            else True
        )
    )
    p01_contract = role_contracts["R5P01"]
    p01_zero_fallbacks = int(candidates["R5P01"]["unexpected_model_fallback_count"]) == 0
    p01_valid = bool(
        (p01_zero_fallbacks if p01_contract["zero_unexpected_model_fallbacks_required"] else True)
        and (
            formula_placebo_evidence["joint_permutation_pass"]
            if p01_contract["joint_permutation_evidence_required"]
            else True
        )
        and (
            formula_placebo_evidence["formula_feature_divergence_pass"]
            if p01_contract["formula_feature_divergence_required"]
            else True
        )
    )
    m01_contract = role_contracts["R5M01"]
    l01_contract = role_contracts["R5L01"]
    c01_contract = role_contracts["R5C01"]
    m01_transfer_win = transfer_sharpe("R5M01") > transfer_sharpe("R5D01")
    l01_transfer_win = transfer_sharpe("R5L01") > transfer_sharpe("R5D01")
    c01_transfer_win = transfer_sharpe("R5C01") > max(
        transfer_sharpe("R5M01"), transfer_sharpe("R5P01")
    )
    c01_performance_pass = bool(
        sum(c01_wins) >= int(c01_contract["minimum_winning_folds"])
        and (
            c01_transfer_win
            if bool(c01_contract["transfer_holdout_win_against_both_required"])
            else True
        )
    )
    c01_bootstrap_gate = _llm_bootstrap_role_gate_evidence(
        llm_contribution_bootstrap,
        validation_contract["llm_contribution_bootstrap"],
    )
    return {
        "R5D01": {"pass": True, "reason": "deterministic_baseline"},
        "R5D02": {"pass": True, "reason": "deterministic_control"},
        "R5M01": {
            "fold_wins": sum(m01_wins),
            "required_fold_wins": int(m01_contract["minimum_winning_folds"]),
            "transfer_win": m01_transfer_win,
            "pass": sum(m01_wins) >= int(m01_contract["minimum_winning_folds"])
            and (m01_transfer_win if m01_contract["transfer_holdout_win_required"] else True),
        },
        "R5M02": {
            "joint_calibration_passing_folds": calibration["joint_passing_fold_count"],
            "calibration_contract_match": m02_calibration_contract_match,
            "applied_gate_decision_count": m02_difference_count,
            "folds_with_target_difference_from_R5M01": m02_different_folds,
            "aggregate_target_hash_differs_from_R5M01": m02_hash_difference,
            "behavior_gate_pass": m02_behavior_pass,
            "pass": bool(
                m02_calibration_contract_match and calibration["pass"] and m02_behavior_pass
            ),
        },
        "R5L01": {
            "fold_wins": sum(l01_wins),
            "required_fold_wins": int(l01_contract["minimum_winning_folds"]),
            "transfer_win": l01_transfer_win,
            "formula_ordering_audit_pass": formula_ordering,
            "pass": sum(l01_wins) >= int(l01_contract["minimum_winning_folds"])
            and (l01_transfer_win if l01_contract["transfer_holdout_win_required"] else True)
            and formula_ordering,
        },
        "R5C01": {
            "same_fold_wins_against_M01_and_P01": sum(c01_wins),
            "required_same_fold_wins": int(c01_contract["minimum_winning_folds"]),
            "transfer_win_against_both": c01_transfer_win,
            "valid_R5P01_placebo": p01_valid,
            "performance_gate_pass": c01_performance_pass,
            "paired_transfer_bootstrap": c01_bootstrap_gate,
            "pass": c01_performance_pass and p01_valid and c01_bootstrap_gate["pass"],
        },
        "R5F01": {"exact_target_identity": identity, "pass": identity},
        "R5P01": {
            "selection_prohibited": True,
            "zero_unexpected_model_fallbacks": p01_zero_fallbacks,
            "joint_permutation_evidence_pass": formula_placebo_evidence["joint_permutation_pass"],
            "formula_feature_divergence_pass": formula_placebo_evidence[
                "formula_feature_divergence_pass"
            ],
            "pass": p01_valid,
        },
    }


def _pbo_gate_pass(
    pbo: dict[str, Any],
    *,
    pbo_config: dict[str, Any],
    validation_contract: dict[str, Any],
) -> bool:
    return bool(
        int(pbo.get("partition_count", -1)) == int(pbo_config["expected_partition_count"])
        and int(pbo.get("valid_partition_count", -1))
        >= int(pbo_config["minimum_valid_partition_count"])
        and int(pbo.get("valid_partition_count", -1))
        >= int(validation_contract["family_gates"]["pbo_min_partitions"])
        and float(pbo.get("probability", math.inf))
        <= float(validation_contract["family_gates"]["pbo_max"])
    )


def _derive_evaluation_statuses(
    candidates: dict[str, Any],
    *,
    workflow_pass: bool,
    pbo_pass: bool,
) -> dict[str, Any]:
    if type(workflow_pass) is not bool or type(pbo_pass) is not bool:
        raise ValueError("R5 evaluation status inputs must be booleans")
    if set(candidates) != set(SPEC_PATHS):
        raise ValueError("R5 evaluation status candidate set is incomplete")
    for candidate_id, candidate in candidates.items():
        expected_promotion_eligible = R5_CANDIDATE_ROLE_CONTRACT[candidate_id]["promotion_eligible"]
        if candidate.get("promotion_eligible") is not expected_promotion_eligible:
            raise ValueError(
                f"R5 promotion eligibility differs from immutable role contract: {candidate_id}"
            )
        family_pass = candidate.get("family_gates", {}).get("pass")
        role_pass = candidate.get("role_gate", {}).get("pass")
        expected_historical_pass = bool(family_pass is True and role_pass is True)
        if candidate.get("historical_research_gate_pass") is not expected_historical_pass:
            raise ValueError(
                f"R5 historical research status is not derived from gates: {candidate_id}"
            )
    selected = [
        candidate_id
        for candidate_id in SPEC_PATHS
        if workflow_pass
        and candidate_id in R5_PROMOTION_ELIGIBLE_CANDIDATE_IDS
        and candidates[candidate_id]["historical_research_gate_pass"] is True
        and pbo_pass
    ]
    if set(selected) & R5_SELECTION_PROHIBITED_CANDIDATE_IDS:
        raise ValueError("R5 selection-prohibited control reached selected candidates")
    research_pass = bool(workflow_pass and selected)
    c01 = candidates["R5C01"]
    llm_contribution_pass = bool(
        workflow_pass
        and c01["role_gate"]["pass"] is True
        and c01["family_gates"]["pass"] is True
        and pbo_pass
    )
    return {
        "workflow_pass": workflow_pass,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_pass,
        "paper_ready_pass": False,
        "selected_candidate_ids": selected,
        "decision": "continue_to_locked_forward_observation" if research_pass else "stop_r5",
    }


def _trial_ledger_rows(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    if set(candidates) != set(SPEC_PATHS):
        raise ValueError("R5 trial ledger candidate set is incomplete")
    return [
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "spec_hash": candidates[candidate_id]["spec_hash"],
            "promotion_eligible": candidates[candidate_id]["promotion_eligible"],
            "aggregate_cost_views": candidates[candidate_id]["aggregate_cost_views"],
            "folds": candidates[candidate_id]["folds"],
            "transfer_holdout": candidates[candidate_id]["transfer_holdout"],
            "dsr": candidates[candidate_id]["dsr"],
            "role_gate": candidates[candidate_id]["role_gate"],
            "family_gates": candidates[candidate_id]["family_gates"],
            "historical_research_gate_pass": candidates[candidate_id][
                "historical_research_gate_pass"
            ],
        }
        for candidate_id in SPEC_PATHS
    ]


def _reconcile_staged_trial_ledger(
    candidates: dict[str, Any],
    trial_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    expected = _trial_ledger_rows(candidates)
    if _canonical_json_bytes(trial_rows) != _canonical_json_bytes(expected):
        raise ValueError("R5 staged trial ledger differs from canonical regenerated rows")
    return {"pass": True, "row_count": len(expected)}


def _evaluate_benchmark_gates(
    candidates: dict[str, Any],
    *,
    benchmark_payload: dict[str, Any],
    benchmark_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    config = benchmark_contract["promotion_gates"]
    cost_view = str(config["cost_view"])
    metric = str(config["metric"])
    required_ids = list(map(str, config["required_benchmark_ids"]))
    minimum_delta = float(config["minimum_delta"])
    benchmark_metrics = {
        benchmark_id: float(
            benchmark_payload["results"][benchmark_id]["cost_views"][cost_view][metric]
        )
        for benchmark_id in required_ids
    }
    results: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        candidate_value = float(candidate["aggregate_cost_views"][cost_view][metric])
        deltas = {
            benchmark_id: candidate_value - benchmark_value
            for benchmark_id, benchmark_value in benchmark_metrics.items()
        }
        checks = {benchmark_id: delta >= minimum_delta for benchmark_id, delta in deltas.items()}
        results[candidate_id] = {
            "scope": str(config["scope"]),
            "cost_view": cost_view,
            "metric": metric,
            "candidate_value": candidate_value,
            "required_benchmark_values": benchmark_metrics,
            "deltas": deltas,
            "minimum_delta": minimum_delta,
            "checks": checks,
            "pass": all(checks.values()),
        }
    return results


def _reconcile_staged_benchmark_gates(
    candidates: dict[str, Any],
    *,
    benchmark_payload: dict[str, Any],
    benchmark_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    recomputed = _evaluate_benchmark_gates(
        candidates,
        benchmark_payload=benchmark_payload,
        benchmark_contract=benchmark_contract,
    )
    for candidate_id, gates in recomputed.items():
        if _canonical_json_bytes(gates) != _canonical_json_bytes(
            candidates[candidate_id].get("benchmark_gate")
        ):
            raise ValueError(f"R5 staged benchmark gate is not derived: {candidate_id}")
    return recomputed


def _benchmark_ledger_rows(
    payload: dict[str, Any],
    simulations: dict[str, dict[str, ExactSimulationResult]],
    targets: dict[str, pd.DataFrame],
    *,
    promotion_gate_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for benchmark_id, views in simulations.items():
        for view_name, simulation in views.items():
            daily = _dataframe_records(simulation.daily)
            events = [_json_ready(event) for event in simulation.events]
            rows.append(
                {
                    "schema_version": 1,
                    "iter_id": ITER_ID,
                    "benchmark_id": benchmark_id,
                    "cost_view": view_name,
                    "promotion_gate": benchmark_id in promotion_gate_ids,
                    "required_evidence": True,
                    "target_sha256": canonical_target_hash(targets[benchmark_id]),
                    "daily_return_sha256": hashlib.sha256(_canonical_json_bytes(daily)).hexdigest(),
                    "cost_event_sha256": hashlib.sha256(_canonical_json_bytes(events)).hexdigest(),
                    "metrics": payload["results"][benchmark_id]["cost_views"][view_name],
                    "daily": daily,
                    "events": events,
                }
            )
    return rows


def _evaluate_candidate_gates(
    candidates: dict[str, Any],
    validation_contract: dict[str, Any],
    *,
    benchmark_gates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    gates = validation_contract["family_gates"]
    result: dict[str, dict[str, Any]] = {}
    for candidate_id, candidate in candidates.items():
        folds = candidate["folds"]
        positive_primary = sum(
            float(row["primary_10bps"]["total_return_pct"]) > 0.0 for row in folds.values()
        )
        positive_stress = sum(
            float(row["stress_20bps"]["total_return_pct"]) > 0.0 for row in folds.values()
        )
        transfer = candidate["transfer_holdout"]["primary_10bps"]
        aggregate = candidate["aggregate_cost_views"]["primary_10bps"]
        checks = {
            "positive_net_return_folds": positive_primary
            >= int(gates["positive_net_return_folds_min"]),
            "positive_stress_20bps_folds": positive_stress
            >= int(gates["stress_20bps_positive_folds_min"]),
            "transfer_holdout_sharpe": float(transfer["annualized_sharpe"])
            >= float(gates["transfer_holdout_sharpe_min"]),
            "transfer_holdout_max_drawdown": abs(float(transfer["max_drawdown_pct"]))
            <= float(gates["transfer_holdout_max_drawdown_abs_pct_max"]),
            "annualized_full_L1_executed_notional": float(
                aggregate["annualized_full_L1_executed_notional_ratio"]
            )
            <= float(gates["annualized_full_L1_executed_notional_ratio_max"]),
            "annualized_BIL_excess_sharpe": float(aggregate["annualized_BIL_excess_sharpe"])
            >= float(gates["annualized_BIL_excess_sharpe_min"]),
            "cumulative_DSR": float(candidate["dsr"]["promotion_probability"])
            >= float(gates["cumulative_dsr_probability_min"]),
            "benchmark_relative_sharpe": bool(benchmark_gates[candidate_id]["pass"]),
            "no_unexpected_model_fallback": int(candidate["unexpected_model_fallback_count"]) == 0,
        }
        result[candidate_id] = {
            "positive_primary_fold_count": positive_primary,
            "positive_stress_fold_count": positive_stress,
            "checks": checks,
            "pass": all(checks.values()),
        }
    return result


def _cost_reconciliation(
    aggregate: dict[str, dict[str, ExactSimulationResult]],
    segments: dict[str, dict[str, dict[str, ExactSimulationResult]]],
    segment_definitions: list[dict[str, Any]],
    *,
    benchmarks: dict[str, dict[str, ExactSimulationResult]] | None = None,
    tolerance: float = 1e-12,
    expected_event_reason_codes: set[str] | None = None,
    expected_cost_bps_by_view: dict[str, float],
) -> dict[str, Any]:
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("cost reconciliation tolerance must be finite and positive")
    expected_event_reason_codes = expected_event_reason_codes or {
        "scheduled_rebalance",
        "independent_boundary_entry",
        "terminal_liquidation",
    }
    rows = []
    maximum_error = 0.0
    maximum_equity_error = 0.0
    failures: list[str] = []
    aggregate_start = str(segment_definitions[0]["start"])
    for candidate_id in SPEC_PATHS:
        aggregate_value = float(
            aggregate[candidate_id]["primary_10bps"].metrics["total_full_L1_executed_notional"]
        )
        segment_values = {
            segment["segment_id"]: float(
                segments[candidate_id][segment["segment_id"]]["primary_10bps"].metrics[
                    "total_full_L1_executed_notional"
                ]
            )
            for segment in segment_definitions
        }
        for view_name, simulation in aggregate[candidate_id].items():
            expected_cost_bps = _required_cost_view_bps(expected_cost_bps_by_view, view_name)
            maximum_error = max(
                maximum_error,
                float(simulation.metrics["maximum_cost_reconciliation_error"]),
            )
            checks = _simulation_accounting_checks(
                simulation,
                expected_start=aggregate_start,
                tolerance=tolerance,
                expected_event_reason_codes=expected_event_reason_codes,
                expected_cost_bps=expected_cost_bps,
            )
            maximum_equity_error = max(maximum_equity_error, checks["equity_chain_error"])
            failures.extend(
                f"{candidate_id}:AGGREGATE:{view_name}:{failure}" for failure in checks["failures"]
            )
        for scope_id, scope in segments[candidate_id].items():
            expected_start = str(
                next(
                    segment["start"]
                    for segment in segment_definitions
                    if segment["segment_id"] == scope_id
                )
            )
            for view_name, simulation in scope.items():
                expected_cost_bps = _required_cost_view_bps(
                    expected_cost_bps_by_view,
                    view_name,
                )
                maximum_error = max(
                    maximum_error,
                    float(simulation.metrics["maximum_cost_reconciliation_error"]),
                )
                checks = _simulation_accounting_checks(
                    simulation,
                    expected_start=expected_start,
                    tolerance=tolerance,
                    expected_event_reason_codes=expected_event_reason_codes,
                    expected_cost_bps=expected_cost_bps,
                )
                maximum_equity_error = max(maximum_equity_error, checks["equity_chain_error"])
                failures.extend(
                    f"{candidate_id}:{scope_id}:{view_name}:{failure}"
                    for failure in checks["failures"]
                )
        segment_sum = sum(segment_values.values())
        aggregate_events = aggregate[candidate_id]["primary_10bps"].events
        segment_event_groups = [
            segments[candidate_id][segment["segment_id"]]["primary_10bps"].events
            for segment in segment_definitions
        ]
        segment_events = [event for group in segment_event_groups for event in group]
        aggregate_boundaries = _boundary_notionals(aggregate_events)
        segment_boundaries = [_boundary_notionals(group) for group in segment_event_groups]
        rows.append(
            {
                "candidate_id": candidate_id,
                "aggregate_primary_full_L1": aggregate_value,
                "independent_segment_primary_full_L1": segment_values,
                "independent_segment_sum": segment_sum,
                "reset_difference_segment_sum_minus_aggregate": segment_sum - aggregate_value,
                "aggregate_boundary_full_L1": aggregate_boundaries,
                "independent_segment_boundary_full_L1": {
                    "entry_sum": float(
                        sum(boundary["entry"] or 0.0 for boundary in segment_boundaries)
                    ),
                    "terminal_sum": float(
                        sum(boundary["terminal"] or 0.0 for boundary in segment_boundaries)
                    ),
                    "event_count": len(segment_events),
                },
                "difference_explanation": (
                    "Each fold and transfer segment starts in cash and liquidates independently; "
                    "the aggregate path enters once, crosses boundaries without reset, and "
                    "liquidates once."
                ),
            }
        )
    benchmark_rows = []
    for benchmark_id, views in (benchmarks or {}).items():
        for view_name, simulation in views.items():
            expected_cost_bps = _required_cost_view_bps(expected_cost_bps_by_view, view_name)
            maximum_error = max(
                maximum_error,
                float(simulation.metrics["maximum_cost_reconciliation_error"]),
            )
            checks = _simulation_accounting_checks(
                simulation,
                expected_start=aggregate_start,
                tolerance=tolerance,
                expected_event_reason_codes=expected_event_reason_codes,
                expected_cost_bps=expected_cost_bps,
            )
            maximum_equity_error = max(maximum_equity_error, checks["equity_chain_error"])
            failures.extend(
                f"BENCHMARK:{benchmark_id}:AGGREGATE:{view_name}:{failure}"
                for failure in checks["failures"]
            )
            benchmark_rows.append(
                {
                    "benchmark_id": benchmark_id,
                    "cost_view": view_name,
                    "cost_bps": expected_cost_bps,
                    "full_L1_executed_notional": float(
                        simulation.metrics["total_full_L1_executed_notional"]
                    ),
                    "accounting_pass": not checks["failures"],
                }
            )
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "accounting": "exact_self_financing_full_L1",
        "event_cost_formula": (
            "cost_fraction_of_pretrade_equity_equals_cost_bps_div_10000_times_"
            "full_L1_executed_notional_fraction"
        ),
        "cost_bps_by_view": expected_cost_bps_by_view,
        "tolerance": tolerance,
        "maximum_event_reconciliation_error": maximum_error,
        "maximum_equity_chain_error": maximum_equity_error,
        "failures": failures,
        "pass": maximum_error <= tolerance and maximum_equity_error <= tolerance and not failures,
        "rows": rows,
        "benchmark_rows": benchmark_rows,
    }


def _require_independent_cost_reconciliation(
    published: dict[str, Any],
    evaluation_payload: dict[str, Any],
    independently_recomputed: dict[str, Any],
) -> dict[str, Any]:
    if _canonical_json_bytes(published) != _canonical_json_bytes(
        evaluation_payload
    ) or _canonical_json_bytes(published) != _canonical_json_bytes(independently_recomputed):
        raise ValueError(
            "R5 staged cost reconciliation differs from independent locked-mark replay"
        )
    return independently_recomputed


def _daily_event_cost_binding_checks(
    daily: pd.DataFrame,
    events: list[dict[str, Any]],
    *,
    tolerance: float,
    expected_cost_bps: float,
) -> dict[str, Any]:
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("daily/event binding tolerance must be finite and positive")
    if not math.isfinite(expected_cost_bps) or expected_cost_bps < 0.0:
        raise ValueError("daily/event expected cost bps must be finite and nonnegative")
    failures: list[str] = []
    required_columns = {
        "interval_start",
        "interval_end",
        "gross_factor_after_rebalance",
        "cost_factor",
        "net_factor",
        "net_return",
    }
    if daily.empty or not required_columns.issubset(daily.columns):
        return {
            "mapped_event_count": 0,
            "nonterminal_event_count": 0,
            "terminal_event_count": 0,
            "maximum_cost_factor_error": math.inf,
            "maximum_net_factor_error": math.inf,
            "maximum_net_return_error": math.inf,
            "failures": ["daily_event_binding_fields_missing"],
        }

    interval_starts = [value if isinstance(value, str) else "" for value in daily["interval_start"]]
    interval_ends = [value if isinstance(value, str) else "" for value in daily["interval_end"]]
    if any(not start or not end for start, end in zip(interval_starts, interval_ends, strict=True)):
        failures.append("daily_interval_identity_missing")
    if len(interval_starts) != len(set(interval_starts)):
        failures.append("daily_interval_start_duplicate")
    try:
        parsed_intervals = [
            (_canonical_session_timestamp(start), _canonical_session_timestamp(end))
            for start, end in zip(interval_starts, interval_ends, strict=True)
        ]
    except ValueError:
        parsed_intervals = []
        failures.append("daily_interval_identity_invalid")
    if parsed_intervals:
        if any(start >= end for start, end in parsed_intervals) or any(
            parsed_intervals[index][0] >= parsed_intervals[index + 1][0]
            for index in range(len(parsed_intervals) - 1)
        ):
            failures.append("daily_intervals_not_chronological")
        if any(
            interval_ends[index] != interval_starts[index + 1]
            for index in range(len(interval_starts) - 1)
        ):
            failures.append("daily_intervals_not_contiguous")

    start_to_row = {session: index for index, session in enumerate(interval_starts)}
    mapped_cost_factors = np.ones(len(daily), dtype=float)
    mapped_event_count = 0
    nonterminal_count = 0
    terminal_count = 0
    seen_nonterminal_sessions: set[str] = set()
    mapped_order_keys: list[int] = []
    for event in events:
        terminal = event.get("terminal")
        if type(terminal) is not bool:
            failures.append("event_terminal_flag_invalid")
            continue
        if terminal:
            terminal_count += 1
        else:
            nonterminal_count += 1
        session = event.get("session")
        try:
            ratio = float(event["posttrade_equity_ratio"])
        except (KeyError, TypeError, ValueError):
            failures.append("event_posttrade_equity_ratio_invalid")
            continue
        try:
            _canonical_session_timestamp(session)
        except ValueError:
            failures.append("event_session_invalid")
            continue
        zero_cost_view = expected_cost_bps == 0.0
        ratio_is_valid = (
            math.isfinite(ratio)
            and 0.0 < ratio <= 1.0
            and (abs(ratio - 1.0) <= tolerance if zero_cost_view else ratio < 1.0)
        )
        if not ratio_is_valid:
            failures.append("event_posttrade_equity_ratio_invalid")
            continue

        pretrade = event.get("pretrade_asset_weights")
        target = event.get("target_asset_weights")
        if (
            not isinstance(pretrade, dict)
            or not isinstance(target, dict)
            or set(pretrade) != set(target)
            or RESERVE_SYMBOL not in pretrade
        ):
            failures.append("event_weight_mapping_mismatch")
            continue
        try:
            pretrade_values = {str(symbol): float(value) for symbol, value in pretrade.items()}
            target_values = {str(symbol): float(value) for symbol, value in target.items()}
            pretrade_cash = float(event["pretrade_cash_weight"])
            posttrade_cash = float(event["posttrade_cash_weight"])
            event_cost_bps = float(event["cost_bps"])
            event_notional = float(event["full_L1_executed_notional_fraction"])
            event_cost_fraction = float(event["cost_fraction_of_pretrade_equity"])
            event_reconciliation_error = float(event["cost_reconciliation_error"])
            event_pretrade_equity = float(event["pretrade_equity"])
        except (KeyError, TypeError, ValueError):
            failures.append("event_accounting_fields_invalid")
            continue
        if any(
            isinstance(value, bool)
            for value in [
                *pretrade.values(),
                *target.values(),
                event.get("pretrade_cash_weight"),
                event.get("posttrade_cash_weight"),
            ]
        ):
            failures.append("event_weight_fields_boolean")
            continue
        all_weight_values = [
            *pretrade_values.values(),
            *target_values.values(),
            pretrade_cash,
            posttrade_cash,
        ]
        if (
            not all(math.isfinite(value) for value in all_weight_values)
            or any(value < -tolerance for value in all_weight_values)
            or abs(sum(pretrade_values.values()) + pretrade_cash - 1.0) > tolerance
            or abs(sum(target_values.values()) + posttrade_cash - 1.0) > tolerance
        ):
            failures.append("event_weight_cash_accounting_invalid")
            continue
        accounting_values = (
            event_cost_bps,
            event_notional,
            event_cost_fraction,
            event_reconciliation_error,
            event_pretrade_equity,
        )
        if not all(math.isfinite(value) for value in accounting_values):
            failures.append("event_cost_fields_nonfinite")
            continue
        if event_cost_bps != expected_cost_bps:
            failures.append("event_cost_bps_mismatch")
        if event_notional <= 1e-15:
            failures.append("event_notional_not_strictly_positive")
        if (zero_cost_view and abs(event_cost_fraction) > tolerance) or (
            not zero_cost_view and event_cost_fraction <= 0.0
        ):
            failures.append("event_cost_fraction_not_strictly_positive")
        if event_pretrade_equity <= 0.0:
            failures.append("event_pretrade_equity_invalid")
        if event_reconciliation_error < 0.0 or event_reconciliation_error > tolerance:
            failures.append("event_reported_cost_reconciliation_error_exceeds_tolerance")
        expected_cost_fraction = expected_cost_bps / 10_000.0 * event_notional
        reconstructed_notional = float(
            sum(
                abs(ratio * target_values[symbol] - pretrade_values[symbol])
                for symbol in target_values
            )
        )
        if not math.isfinite(reconstructed_notional):
            failures.append("event_reconstructed_notional_nonfinite")
        elif abs(reconstructed_notional - event_notional) > tolerance:
            failures.append("event_full_L1_notional_mismatch")
        if abs(event_cost_fraction - expected_cost_fraction) > tolerance:
            failures.append("event_cost_fraction_bps_notional_mismatch")
        if abs(event_cost_fraction - (1.0 - ratio)) > tolerance:
            failures.append("event_cost_fraction_equity_ratio_mismatch")

        if terminal:
            if session != interval_ends[-1]:
                failures.append("terminal_event_not_mapped_to_final_interval_end")
                continue
            row_index = len(daily) - 1
            order_key = row_index * 2 + 1
        else:
            if session in seen_nonterminal_sessions:
                failures.append("nonterminal_event_session_duplicate")
                continue
            seen_nonterminal_sessions.add(session)
            row_index = start_to_row.get(session, -1)
            if row_index < 0:
                failures.append("nonterminal_event_not_mapped_to_interval_start")
                continue
            order_key = row_index * 2
        if terminal:
            expected_pretrade_equity = float(daily.iloc[-1]["equity"]) / ratio
        else:
            expected_pretrade_equity = (
                1.0 if row_index == 0 else float(daily.iloc[row_index - 1]["equity"])
            )
        if (
            not math.isfinite(expected_pretrade_equity)
            or abs(event_pretrade_equity - expected_pretrade_equity) > tolerance
        ):
            failures.append("event_pretrade_equity_chain_mismatch")
        mapped_cost_factors[row_index] *= ratio
        mapped_order_keys.append(order_key)
        mapped_event_count += 1
    if terminal_count != 1:
        failures.append("terminal_event_count_not_one")
    if any(
        mapped_order_keys[index] >= mapped_order_keys[index + 1]
        for index in range(len(mapped_order_keys) - 1)
    ):
        failures.append("cost_events_not_strictly_chronological")

    maximum_cost_error = 0.0
    maximum_net_factor_error = 0.0
    maximum_net_return_error = 0.0
    for row_index, row in daily.reset_index(drop=True).iterrows():
        try:
            gross_factor = float(row["gross_factor_after_rebalance"])
            cost_factor = float(row["cost_factor"])
            net_factor = float(row["net_factor"])
            net_return = float(row["net_return"])
        except (KeyError, TypeError, ValueError):
            failures.append("daily_factor_fields_invalid")
            continue
        if (
            not all(
                math.isfinite(value)
                for value in (gross_factor, cost_factor, net_factor, net_return)
            )
            or gross_factor <= 0.0
            or not 0.0 < cost_factor <= 1.0
            or net_factor <= 0.0
        ):
            failures.append("daily_factor_fields_nonfinite_or_out_of_bounds")
            continue
        cost_error = abs(cost_factor - float(mapped_cost_factors[row_index]))
        net_factor_error = abs(net_factor - cost_factor * gross_factor)
        net_return_error = abs(net_return - (net_factor - 1.0))
        maximum_cost_error = max(maximum_cost_error, cost_error)
        maximum_net_factor_error = max(maximum_net_factor_error, net_factor_error)
        maximum_net_return_error = max(maximum_net_return_error, net_return_error)
        if cost_error > tolerance:
            failures.append("daily_cost_factor_event_product_mismatch")
        if net_factor_error > tolerance:
            failures.append("daily_net_factor_cost_gross_mismatch")
        if net_return_error > tolerance:
            failures.append("daily_net_return_factor_mismatch")

    return {
        "mapped_event_count": mapped_event_count,
        "nonterminal_event_count": nonterminal_count,
        "terminal_event_count": terminal_count,
        "maximum_cost_factor_error": maximum_cost_error,
        "maximum_net_factor_error": maximum_net_factor_error,
        "maximum_net_return_error": maximum_net_return_error,
        "failures": sorted(set(failures)),
    }


def _simulation_accounting_checks(
    simulation: ExactSimulationResult,
    *,
    expected_start: str,
    tolerance: float,
    expected_event_reason_codes: set[str],
    expected_cost_bps: float,
) -> dict[str, Any]:
    failures: list[str] = []
    events = simulation.events
    daily = simulation.daily
    if not events:
        return {
            "equity_chain_error": math.inf,
            "failures": ["event_ledger_empty"],
        }
    daily_event_binding = _daily_event_cost_binding_checks(
        daily,
        events,
        tolerance=tolerance,
        expected_cost_bps=expected_cost_bps,
    )
    failures.extend(daily_event_binding["failures"])
    nonterminal = [event for event in events if event.get("terminal") is False]
    terminal = [event for event in events if event.get("terminal") is True]
    if not nonterminal or str(nonterminal[0]["session"]) != expected_start:
        failures.append("missing_first_session_entry")
    if len(terminal) != 1:
        failures.append("terminal_liquidation_count_not_one")
    if events[-1].get("terminal") is not True:
        failures.append("terminal_liquidation_not_last_event")
    if any(str(event.get("reason")) not in expected_event_reason_codes for event in events):
        failures.append("unexpected_event_reason")
    if any(
        event.get("terminal") is not (event.get("reason") == "terminal_liquidation")
        for event in events
    ):
        failures.append("terminal_reason_mismatch")
    try:
        event_notional = float(
            sum(float(event["full_L1_executed_notional_fraction"]) for event in events)
        )
    except (KeyError, TypeError, ValueError):
        event_notional = math.nan
    if (
        not math.isfinite(event_notional)
        or abs(event_notional - simulation.metrics["total_full_L1_executed_notional"]) > tolerance
    ):
        failures.append("event_notional_metric_mismatch")
    try:
        factors = pd.to_numeric(daily["net_factor"], errors="raise").astype(float)
        equity = pd.to_numeric(daily["equity"], errors="raise").astype(float)
        expected_equity = factors.cumprod()
        equity_error = float(np.max(np.abs(expected_equity.to_numpy() - equity.to_numpy())))
    except (KeyError, TypeError, ValueError):
        equity_error = math.inf
    if not math.isfinite(equity_error) or equity_error > tolerance:
        failures.append("daily_factor_equity_chain_mismatch")
    if int(simulation.metrics["terminal_liquidation_count"]) != len(terminal):
        failures.append("terminal_metric_event_mismatch")
    if int(simulation.metrics["nonzero_rebalance_count"]) != len(nonterminal):
        failures.append("rebalance_metric_event_mismatch")
    return {
        "equity_chain_error": equity_error,
        "daily_event_binding": daily_event_binding,
        "failures": sorted(set(failures)),
    }


def _required_cost_view_bps(
    expected_cost_bps_by_view: dict[str, float],
    view_name: str,
) -> float:
    if view_name not in expected_cost_bps_by_view:
        raise ValueError(f"R5 cost view is not frozen: {view_name}")
    value = float(expected_cost_bps_by_view[view_name])
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"R5 cost view bps is invalid: {view_name}")
    return value


def _boundary_notionals(events: list[dict[str, Any]]) -> dict[str, float | None]:
    entry = next((event for event in events if not event.get("terminal")), None)
    terminal = next((event for event in reversed(events) if event.get("terminal")), None)
    return {
        "entry": (
            float(entry["full_L1_executed_notional_fraction"]) if entry is not None else None
        ),
        "terminal": (
            float(terminal["full_L1_executed_notional_fraction"]) if terminal is not None else None
        ),
    }


def _scoped_events(
    events: list[dict[str, Any]],
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
            **event,
        }
        for event in events
    ]


def _scoped_daily_returns(
    daily: pd.DataFrame,
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
            **row,
        }
        for row in _dataframe_records(daily)
    ]


def _pbo_returns_from_daily_ledger(
    rows: list[dict[str, Any]],
    *,
    folds: list[dict[str, Any]],
    candidate_ids: list[str],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    fold_ids = [str(fold["fold_id"]) for fold in folds]
    fold_order = {fold_id: index for index, fold_id in enumerate(fold_ids)}
    candidate_series: dict[str, pd.Series] = {}
    common_identities: list[tuple[str, str, str]] | None = None
    for candidate_id in candidate_ids:
        selected = [
            row
            for row in rows
            if row.get("candidate_id") == candidate_id
            and row.get("scope_id") in fold_order
            and row.get("cost_view") == "primary_10bps"
        ]
        selected.sort(
            key=lambda row: (
                fold_order[str(row["scope_id"])],
                str(row["interval_start"]),
            )
        )
        identities = [
            (
                str(row["scope_id"]),
                str(row["interval_start"]),
                str(row.get("interval_end") or ""),
            )
            for row in selected
        ]
        intervals = [identity[1] for identity in identities]
        if not intervals or len(intervals) != len(set(intervals)):
            raise ValueError(f"R5 daily-return ledger is incomplete for {candidate_id}")
        if any(not interval_end for _, _, interval_end in identities):
            raise ValueError(f"R5 daily-return ledger interval end is missing for {candidate_id}")
        if common_identities is None:
            common_identities = identities
        elif identities != common_identities:
            raise ValueError("R5 daily-return ledger scope or interval identities differ")
        values = np.asarray([float(row["net_return"]) for row in selected], dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"R5 daily-return ledger is nonfinite for {candidate_id}")
        candidate_series[candidate_id] = pd.Series(values, index=pd.Index(intervals))
    frame = pd.DataFrame(candidate_series)
    if (
        frame.empty
        or frame.isna().any().any()
        or list(frame.columns) != candidate_ids
        or frame.index.has_duplicates
    ):
        raise ValueError("R5 daily-return ledger cannot reproduce the common PBO matrix")
    if common_identities is None:
        raise ValueError("R5 daily-return ledger identity set is empty")
    source_rows = [
        {
            "scope_id": common_identities[index][0],
            "interval_start": str(interval_start),
            "interval_end": common_identities[index][2],
            **{candidate_id: float(value) for candidate_id, value in row.items()},
        }
        for index, (interval_start, row) in enumerate(frame.iterrows())
    ]
    return frame, source_rows


def _reconcile_model_prediction_evidence(
    model_records: list[dict[str, Any]],
    prediction_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_prediction_fields = {
        "schema_version",
        "iter_id",
        "segment_id",
        "candidate_id",
        "model_id",
        "decision_session",
        "symbol",
        "value",
        "prediction_sha256",
    }
    by_model: dict[str, list[dict[str, Any]]] = {}
    seen_prediction_keys: set[tuple[str, str]] = set()
    for row in prediction_rows:
        if (
            set(row) != expected_prediction_fields
            or row.get("schema_version") != 1
            or row.get("iter_id") != ITER_ID
            or isinstance(row.get("value"), bool)
        ):
            raise ValueError("R5 prediction ledger row contract is invalid")
        try:
            value = float(row["value"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("R5 prediction ledger value is invalid") from exc
        if not math.isfinite(value):
            raise ValueError("R5 prediction ledger value is nonfinite")
        model_id = str(row.get("model_id") or "")
        symbol = str(row.get("symbol") or "")
        key = (model_id, symbol)
        if not model_id or not symbol or key in seen_prediction_keys:
            raise ValueError(
                "R5 prediction ledger contains a missing or duplicate model-symbol key"
            )
        seen_prediction_keys.add(key)
        by_model.setdefault(model_id, []).append(row)

    seen_models: set[str] = set()
    successful_models = 0
    fallback_models = 0
    for record in model_records:
        model_id = str(record.get("model_id") or "")
        if not model_id or model_id in seen_models:
            raise ValueError("R5 model ledger contains a missing or duplicate model_id")
        seen_models.add(model_id)
        expected_predictions = record.get("predictions")
        if not isinstance(expected_predictions, list):
            raise ValueError(f"R5 model predictions are malformed for {model_id}")
        actual_rows = by_model.pop(model_id, [])
        expected_rows = [
            {
                "symbol": str(row["symbol"]),
                "value": float(row["value"]),
            }
            for row in expected_predictions
        ]
        actual_values = [
            {"symbol": str(row["symbol"]), "value": float(row["value"])} for row in actual_rows
        ]
        if actual_values != expected_rows:
            raise ValueError(f"R5 prediction ledger differs from model evidence for {model_id}")
        for row in actual_rows:
            for field in ("segment_id", "candidate_id", "decision_session", "prediction_sha256"):
                if row.get(field) != record.get(field):
                    raise ValueError(f"R5 prediction ledger {field} mismatch for {model_id}")
        if record.get("status") == "fit_complete":
            successful_models += 1
            values = np.asarray([row["value"] for row in expected_rows], dtype="<f8")
            expected_hash = hashlib.sha256(values.tobytes()).hexdigest()
            if record.get("prediction_sha256") != expected_hash:
                raise ValueError(f"R5 model prediction hash mismatch for {model_id}")
            if not str(record.get("fitted_model_sha256") or ""):
                raise ValueError(f"R5 fitted model hash is missing for {model_id}")
        else:
            fallback_models += 1
            if expected_rows or record.get("prediction_sha256") is not None:
                raise ValueError(
                    f"R5 fallback model unexpectedly contains predictions for {model_id}"
                )
    if by_model:
        raise ValueError("R5 prediction ledger contains rows without a model-ledger record")
    return {
        "pass": True,
        "model_record_count": len(model_records),
        "prediction_row_count": len(prediction_rows),
        "successful_model_count": successful_models,
        "fallback_model_count": fallback_models,
    }


def _reconcile_target_ledger_evidence(
    target_rows: list[dict[str, Any]],
    candidates: dict[str, Any],
) -> dict[str, Any]:
    expected_symbols = sorted([RESERVE_SYMBOL, *RANKABLE_SYMBOLS])
    grouped: dict[str, list[dict[str, Any]]] = {candidate_id: [] for candidate_id in SPEC_PATHS}
    seen: set[tuple[str, str]] = set()
    for row in target_rows:
        candidate_id = str(row.get("candidate_id") or "")
        execution_session = str(row.get("execution_session") or "")
        key = (candidate_id, execution_session)
        if candidate_id not in grouped or not execution_session or key in seen:
            raise ValueError("R5 target ledger contains an invalid or duplicate identity")
        seen.add(key)
        weights = row.get("weights")
        if not isinstance(weights, dict) or sorted(weights) != expected_symbols:
            raise ValueError(f"R5 target ledger symbol set mismatch for {candidate_id}")
        numeric = {symbol: float(weights[symbol]) for symbol in expected_symbols}
        values = np.asarray(list(numeric.values()), dtype=float)
        if (
            not np.isfinite(values).all()
            or (values < -1e-12).any()
            or abs(float(values.sum()) - 1.0) > 1e-12
        ):
            raise ValueError(f"R5 target ledger weights are invalid for {candidate_id}")
        row_hash = hashlib.sha256(_canonical_json_bytes(numeric)).hexdigest()
        if row.get("target_sha256") != row_hash:
            raise ValueError(f"R5 target row hash mismatch for {candidate_id}")
        grouped[candidate_id].append(row)

    hashes: dict[str, str] = {}
    for candidate_id, rows in grouped.items():
        rows.sort(key=lambda row: str(row["execution_session"]))
        if not rows:
            raise ValueError(f"R5 target ledger is empty for {candidate_id}")
        frame = pd.DataFrame(
            [row["weights"] for row in rows],
            index=pd.DatetimeIndex([row["execution_session"] for row in rows]),
            columns=expected_symbols,
            dtype=float,
        )
        target_hash = canonical_target_hash(frame)
        expected = candidates[candidate_id]
        if len(frame) != int(expected["target_count"]):
            raise ValueError(f"R5 target count mismatch for {candidate_id}")
        if target_hash != expected["target_sha256"]:
            raise ValueError(f"R5 aggregate target hash mismatch for {candidate_id}")
        hashes[candidate_id] = target_hash
    if hashes["R5F01"] != hashes["R5M01"]:
        raise ValueError("R5 staged fallback target identity failed")
    return {
        "pass": True,
        "row_count": len(target_rows),
        "candidate_target_sha256": hashes,
    }


def _staged_target_frames(
    target_rows: list[dict[str, Any]],
    validation_contract: dict[str, Any],
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, dict[str, pd.DataFrame]],
    dict[str, int],
]:
    expected_symbols = sorted([RESERVE_SYMBOL, *RANKABLE_SYMBOLS])
    expected_segment_ids = {
        *(str(fold["fold_id"]) for fold in validation_contract["folds"]),
        "TRANSFER",
    }
    segment_window_by_id = {
        str(fold["fold_id"]): (str(fold["test_start"]), str(fold["test_end"]))
        for fold in validation_contract["folds"]
    }
    transfer = validation_contract["transfer_holdout"]
    segment_window_by_id["TRANSFER"] = (str(transfer["start"]), str(transfer["end"]))
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        segment_id: {candidate_id: [] for candidate_id in SPEC_PATHS}
        for segment_id in expected_segment_ids
    }
    fallback_counts = {candidate_id: 0 for candidate_id in SPEC_PATHS}
    seen: set[tuple[str, str]] = set()
    allowed_expected_fallbacks = {
        "intentional_missing_modality_identity",
        "fewer_than_three_survival_eligible_symbols",
    }
    for row in target_rows:
        candidate_id = str(row.get("candidate_id") or "")
        segment_id = str(row.get("segment_id") or "")
        decision_session = str(row.get("decision_session") or "")
        execution_session = str(row.get("execution_session") or "")
        key = (candidate_id, execution_session)
        if (
            row.get("schema_version") != 1
            or row.get("iter_id") != ITER_ID
            or candidate_id not in SPEC_PATHS
            or segment_id not in expected_segment_ids
            or not decision_session
            or not execution_session
            or key in seen
        ):
            raise ValueError("R5 staged target ledger identity is invalid or duplicated")
        seen.add(key)
        try:
            decision_timestamp = _canonical_session_timestamp(decision_session)
            execution_timestamp = _canonical_session_timestamp(execution_session)
        except ValueError as exc:
            raise ValueError("R5 staged target ledger session is invalid") from exc
        if decision_timestamp >= execution_timestamp:
            raise ValueError("R5 staged target decision/execution chronology is invalid")
        segment_start, segment_end = segment_window_by_id[segment_id]
        if not segment_start <= execution_session <= segment_end:
            raise ValueError("R5 staged target execution is outside its segment")

        weights = row.get("weights")
        if not isinstance(weights, dict) or sorted(weights) != expected_symbols:
            raise ValueError(f"R5 staged target symbol set mismatch for {candidate_id}")
        numeric = {symbol: float(weights[symbol]) for symbol in expected_symbols}
        values = np.asarray(list(numeric.values()), dtype=float)
        if (
            not np.isfinite(values).all()
            or (values < -1e-12).any()
            or abs(float(values.sum()) - 1.0) > 1e-12
        ):
            raise ValueError(f"R5 staged target weights are invalid for {candidate_id}")
        expected_row_hash = hashlib.sha256(_canonical_json_bytes(numeric)).hexdigest()
        if row.get("target_sha256") != expected_row_hash:
            raise ValueError(f"R5 staged target row hash mismatch for {candidate_id}")
        selected_symbols = row.get("selected_symbols")
        if (
            not isinstance(selected_symbols, list)
            or len(selected_symbols) != TOP_N
            or len(selected_symbols) != len(set(selected_symbols))
            or not set(selected_symbols).issubset(RANKABLE_SYMBOLS)
        ):
            raise ValueError(f"R5 staged selected-symbol evidence is invalid for {candidate_id}")
        weighted_risk_symbols = {
            symbol for symbol in RANKABLE_SYMBOLS if float(numeric[symbol]) > 1e-12
        }
        if set(selected_symbols) != weighted_risk_symbols:
            raise ValueError(f"R5 staged selected symbols differ from weights for {candidate_id}")
        if any(
            abs(float(numeric[symbol]) - 1.0 / TOP_N) > 1e-12 for symbol in selected_symbols
        ) or any(float(numeric[symbol]) > 0.34 + 1e-12 for symbol in RANKABLE_SYMBOLS):
            raise ValueError(f"R5 staged target weighting contract failed for {candidate_id}")
        fallback_reason = row.get("fallback_reason")
        if fallback_reason is not None and (
            not isinstance(fallback_reason, str) or not fallback_reason
        ):
            raise ValueError(f"R5 staged fallback reason is invalid for {candidate_id}")
        if (
            (candidate_id == "R5F01")
            != (fallback_reason == "intentional_missing_modality_identity")
        ) or (
            fallback_reason == "fewer_than_three_survival_eligible_symbols"
            and candidate_id != "R5M02"
        ):
            raise ValueError(f"R5 staged fallback reason is not role-bound for {candidate_id}")
        expected_unexpected = bool(
            fallback_reason and fallback_reason not in allowed_expected_fallbacks
        )
        if row.get("unexpected_model_fallback") is not expected_unexpected:
            raise ValueError(f"R5 staged fallback flag is not derived for {candidate_id}")
        fallback_counts[candidate_id] += int(expected_unexpected)
        grouped[segment_id][candidate_id].append(row)

    segment_targets: dict[str, dict[str, pd.DataFrame]] = {}
    for segment_id in sorted(expected_segment_ids):
        segment_targets[segment_id] = {}
        reference_index: pd.DatetimeIndex | None = None
        for candidate_id in SPEC_PATHS:
            rows = sorted(
                grouped[segment_id][candidate_id],
                key=lambda row: str(row["execution_session"]),
            )
            if not rows:
                raise ValueError(f"R5 staged target segment is empty: {segment_id}:{candidate_id}")
            frame = pd.DataFrame(
                [row["weights"] for row in rows],
                index=pd.DatetimeIndex([row["execution_session"] for row in rows]),
                columns=expected_symbols,
                dtype=float,
            )
            if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
                raise ValueError(
                    f"R5 staged target sessions are invalid: {segment_id}:{candidate_id}"
                )
            if reference_index is None:
                reference_index = frame.index
            elif not frame.index.equals(reference_index):
                raise ValueError(f"R5 staged target segment is misaligned: {segment_id}")
            segment_targets[segment_id][candidate_id] = frame

    aggregate_targets = {
        candidate_id: pd.concat(
            [segment_targets[segment_id][candidate_id] for segment_id in sorted(segment_targets)]
        ).sort_index()
        for candidate_id in SPEC_PATHS
    }
    reference_aggregate_index = aggregate_targets["R5D01"].index
    if any(
        frame.index.has_duplicates or not frame.index.equals(reference_aggregate_index)
        for frame in aggregate_targets.values()
    ):
        raise ValueError("R5 staged aggregate target sessions are invalid or misaligned")
    return aggregate_targets, segment_targets, fallback_counts


def _staged_calibration_from_ledgers(
    feature_rows: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    validation_contract: dict[str, Any],
) -> dict[str, Any]:
    dataset = pd.DataFrame(feature_rows)
    folds = list(validation_contract["folds"])
    fold_contract_by_id = {str(fold["fold_id"]): fold for fold in folds}
    expected_target_by_model_key = {
        (str(row["segment_id"]), str(row["decision_session"])): str(row["execution_session"])
        for row in target_rows
        if row.get("candidate_id") == "R5M02"
        and str(row.get("segment_id") or "") in fold_contract_by_id
    }
    model_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in model_records:
        if record.get("candidate_id") != "R5M02":
            continue
        segment_id = str(record.get("segment_id") or "")
        if segment_id not in fold_contract_by_id:
            continue
        key = (segment_id, str(record.get("decision_session") or ""))
        if not key[1] or key in model_by_key:
            raise ValueError("R5 staged M02 calibration model identity is invalid")
        model_by_key[key] = record
    if set(model_by_key) != set(expected_target_by_model_key):
        raise ValueError("R5 staged M02 calibration model coverage is incomplete")

    calibration_rows: dict[str, list[dict[str, Any]]] = {
        fold_id: [] for fold_id in fold_contract_by_id
    }
    for (segment_id, decision_session), record in sorted(model_by_key.items()):
        if record.get("status") != "fit_complete":
            continue
        predictions = record.get("predictions")
        if not isinstance(predictions, list):
            raise ValueError("R5 staged M02 calibration predictions are invalid")
        prediction_by_symbol = {
            str(row.get("symbol") or ""): float(row["value"]) for row in predictions
        }
        if set(prediction_by_symbol) != set(RANKABLE_SYMBOLS):
            raise ValueError("R5 staged M02 calibration prediction coverage is incomplete")
        current = dataset[dataset["decision_session"] == decision_session].sort_values("symbol")
        if set(map(str, current["symbol"])) != set(RANKABLE_SYMBOLS):
            raise ValueError("R5 staged M02 calibration feature coverage is incomplete")
        expected_execution_session = expected_target_by_model_key[(segment_id, decision_session)]
        fold_contract = fold_contract_by_id[segment_id]
        if (
            set(map(str, current["execution_session"])) != {expected_execution_session}
            or not str(fold_contract["test_start"])
            <= expected_execution_session
            <= str(fold_contract["test_end"])
            or _canonical_session_timestamp(decision_session)
            >= _canonical_session_timestamp(expected_execution_session)
        ):
            raise ValueError("R5 staged M02 calibration observation is outside its fold")
        try:
            training_base_probability = float(record["training_label_mean"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("R5 staged M02 training base probability is invalid") from exc
        if not math.isfinite(training_base_probability):
            raise ValueError("R5 staged M02 training base probability is nonfinite")
        for row in current.to_dict(orient="records"):
            label_end_session = row.get("label_end_session")
            if label_end_session is None or str(label_end_session) > str(fold_contract["test_end"]):
                continue
            try:
                label = int(row["path_survival_label"])
                probability = float(prediction_by_symbol[str(row["symbol"])])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("R5 staged M02 calibration row is invalid") from exc
            if label not in {0, 1} or not math.isfinite(probability):
                raise ValueError("R5 staged M02 calibration values are invalid")
            calibration_rows[segment_id].append(
                {
                    "label": label,
                    "probability": probability,
                    "training_base_probability": training_base_probability,
                }
            )

    m02_contract = validation_contract["role_gates"]["R5M02"]
    return _calibration_payload(
        {fold_id: pd.DataFrame(rows) for fold_id, rows in calibration_rows.items()},
        folds,
        required_joint_passing_fold_count=int(
            m02_contract["joint_brier_and_slope_passing_folds_min"]
        ),
        probability_clip=float(m02_contract["probability_clip"]),
        slope_min=float(m02_contract["calibration_slope_min"]),
        slope_max=float(m02_contract["calibration_slope_max"]),
        expected_observation_count_by_fold={
            str(key): int(value)
            for key, value in m02_contract["expected_observation_count_by_fold"].items()
        },
        minimum_class_count=int(m02_contract["minimum_class_count_per_fold"]),
    )


def _reconcile_staged_role_gate_evidence(
    *,
    feature_rows: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    candidates: dict[str, Any],
    reported_calibration: dict[str, Any],
    reported_formula_placebo_evidence: dict[str, Any],
    llm_contribution_bootstrap: dict[str, Any],
    validation_contract: dict[str, Any],
) -> dict[str, Any]:
    aggregate_targets, segment_targets, fallback_counts = _staged_target_frames(
        target_rows,
        validation_contract,
    )
    for candidate_id, count in fallback_counts.items():
        if candidates[candidate_id].get("unexpected_model_fallback_count") != count:
            raise ValueError(f"R5 staged unexpected fallback count mismatch: {candidate_id}")

    evaluated_decision_sessions = {
        str(row["decision_session"]) for row in target_rows if row.get("candidate_id") == "R5P01"
    }
    formula_placebo_evidence = _formula_placebo_evidence(
        pd.DataFrame(feature_rows),
        decision_sessions=evaluated_decision_sessions,
    )
    if _canonical_json_bytes(formula_placebo_evidence) != _canonical_json_bytes(
        reported_formula_placebo_evidence
    ):
        raise ValueError("R5 staged formula placebo evidence differs from feature ledger")

    calibration = _staged_calibration_from_ledgers(
        feature_rows,
        model_records,
        target_rows,
        validation_contract,
    )
    if _canonical_json_bytes(calibration) != _canonical_json_bytes(reported_calibration):
        raise ValueError("R5 staged M02 calibration differs from feature/model ledgers")

    gate_candidates = {
        candidate_id: {
            **candidate,
            "unexpected_model_fallback_count": fallback_counts[candidate_id],
        }
        for candidate_id, candidate in candidates.items()
    }
    recomputed_role_gates = _evaluate_role_gates(
        gate_candidates,
        calibration=calibration,
        aggregate_targets=aggregate_targets,
        segment_targets=segment_targets,
        formula_placebo_evidence=formula_placebo_evidence,
        llm_contribution_bootstrap=llm_contribution_bootstrap,
        validation_contract=validation_contract,
    )
    for candidate_id, recomputed in recomputed_role_gates.items():
        if _canonical_json_bytes(recomputed) != _canonical_json_bytes(
            candidates[candidate_id].get("role_gate")
        ):
            raise ValueError(f"R5 staged role gate is not derived: {candidate_id}")
    return {
        "pass": True,
        "candidate_count": len(recomputed_role_gates),
        "formula_placebo_evidence_recomputed": True,
        "m02_calibration_recomputed": True,
        "target_frames_reconstructed": True,
        "unexpected_fallback_counts": fallback_counts,
    }


def _reconcile_feature_and_model_refits(
    feature_rows: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    dataset = pd.DataFrame(feature_rows)
    required_identity = {
        "decision_position",
        "decision_session",
        "execution_position",
        "execution_session",
        "label_end_position",
        "label_end_session",
        "symbol",
    }
    if dataset.empty or not required_identity.issubset(dataset.columns):
        raise ValueError("R5 staged feature ledger identity fields are incomplete")
    if dataset.duplicated(["decision_position", "symbol"]).any():
        raise ValueError("R5 staged feature ledger contains duplicate decision-symbol rows")
    for _, group in dataset.groupby("decision_position", sort=True):
        if set(map(str, group["symbol"])) != set(RANKABLE_SYMBOLS):
            raise ValueError("R5 staged feature ledger symbol coverage mismatch")
        if any(group[field].nunique(dropna=False) != 1 for field in required_identity - {"symbol"}):
            raise ValueError("R5 staged feature ledger decision identity is inconsistent")
        row = group.iloc[0]
        if int(row["execution_position"]) != int(row["decision_position"]) + 1:
            raise ValueError("R5 staged execution position is not next-session aligned")
        decision = pd.Timestamp(str(row["decision_session"]))
        execution = pd.Timestamp(str(row["execution_session"]))
        label_position = row["label_end_position"]
        label_session = row["label_end_session"]
        if label_position is None or label_session is None:
            if not (label_position is None and label_session is None):
                raise ValueError("R5 staged unavailable label identity is inconsistent")
            if not decision < execution:
                raise ValueError("R5 staged decision/execution chronology is invalid")
            continue
        if int(label_position) != int(row["execution_position"]) + HORIZON_SESSIONS:
            raise ValueError("R5 staged label horizon position mismatch")
        label_end = pd.Timestamp(str(label_session))
        if not decision < execution < label_end:
            raise ValueError("R5 staged decision/execution/label chronology is invalid")

    successful_refits = 0
    deterministic_fallbacks = 0
    for record in model_records:
        candidate_id = str(record.get("candidate_id") or "")
        spec = specs.get(candidate_id)
        if spec is None or spec.model is None:
            raise ValueError(f"R5 staged model record has no bound spec: {candidate_id}")
        feature_names = tuple(map(str, record.get("feature_names") or []))
        label_name = str(record.get("label_name") or "")
        expected_feature_names = R5_RUNTIME_PREDICTOR_CONTRACT.get(candidate_id)
        expected_label_name = R5_MODEL_LABEL_CONTRACT.get(candidate_id)
        if feature_names != expected_feature_names:
            raise ValueError(f"R5 staged model feature identity mismatch: {candidate_id}")
        if label_name != expected_label_name or label_name in feature_names:
            raise ValueError(f"R5 staged model label identity mismatch: {candidate_id}")
        if spec.model.model_dump(mode="json") != R5_MODEL_SPEC_CONTRACT.get(candidate_id):
            raise ValueError(f"R5 staged immutable model contract mismatch: {candidate_id}")
        decision_session = str(record.get("decision_session") or "")
        current = dataset[dataset["decision_session"] == decision_session].sort_values("symbol")
        if len(current) != len(RANKABLE_SYMBOLS) or not feature_names or not label_name:
            raise ValueError(f"R5 staged model identity is incomplete: {record.get('model_id')}")
        decision_positions = current["decision_position"].unique()
        if len(decision_positions) != 1:
            raise ValueError(f"R5 staged model decision position is ambiguous: {decision_session}")
        train = training_rows_for_prediction(
            dataset,
            decision_position=int(decision_positions[0]),
            train_start_session="2018-02-01",
            feature_names=feature_names,
            label_name=label_name,
        )
        train_predictors = _validated_predictor_frame(
            train,
            candidate_id=candidate_id,
            feature_names=feature_names,
            label_name=label_name,
        )
        current_predictors = _validated_predictor_frame(
            current,
            candidate_id=candidate_id,
            feature_names=feature_names,
            label_name=label_name,
        )
        checks = {
            "training_row_count": len(train),
            "training_decision_start": (
                str(train["decision_session"].min()) if not train.empty else None
            ),
            "training_decision_end": (
                str(train["decision_session"].max()) if not train.empty else None
            ),
            "training_label_terminal_end": (
                str(train["label_end_session"].max()) if not train.empty else None
            ),
            "training_data_sha256": _frame_sha256(train, [*feature_names, label_name]),
            "prediction_feature_sha256": _frame_sha256(current_predictors, list(feature_names)),
            "training_label_mean": (
                float(pd.to_numeric(train[label_name], errors="raise").mean())
                if not train.empty
                else None
            ),
        }
        for field_name, expected in checks.items():
            actual = record.get(field_name)
            if isinstance(expected, float):
                matched = math.isclose(float(actual), expected, rel_tol=1e-12, abs_tol=1e-12)
            else:
                matched = actual == expected
            if not matched:
                raise ValueError(
                    f"R5 staged model training evidence mismatch: {record.get('model_id')}:"
                    f"{field_name}"
                )
        if record.get("model_config") != spec.model.model_dump(mode="json"):
            raise ValueError(f"R5 staged model config mismatch: {record.get('model_id')}")

        minimum_rows = max(80, 2 * int(spec.model.hyperparameters.get("min_child_samples", 1)))
        deterministic_failure: str | None = None
        if len(train) < minimum_rows:
            deterministic_failure = "insufficient_training_rows"
        elif spec.model.kind == "lightgbm_classifier" and train[label_name].nunique() < 2:
            deterministic_failure = "single_class_training_labels"
        current_values = current_predictors.replace([np.inf, -np.inf], np.nan)
        if current_values.isna().any().any():
            deterministic_failure = "nonfinite_prediction_features"
        if deterministic_failure is not None:
            if (
                record.get("status") != "fallback_applied"
                or record.get("failure_reason") != deterministic_failure
                or record.get("predictions")
            ):
                raise ValueError(
                    f"R5 staged deterministic fallback mismatch: {record.get('model_id')}"
                )
            deterministic_fallbacks += 1
            continue
        if record.get("status") != "fit_complete":
            raise ValueError(
                f"R5 non-deterministic model failure cannot be independently attested: "
                f"{record.get('model_id')}"
            )
        model = _make_estimator(spec)
        if _json_ready(model.get_params(deep=True)) != record.get("resolved_model_params"):
            raise ValueError(f"R5 staged resolved model params mismatch: {record.get('model_id')}")
        model.fit(train_predictors, train[label_name])
        if spec.model.kind == "lightgbm_classifier":
            prediction = np.asarray(model.predict_proba(current_values)[:, 1], dtype=float)
        else:
            prediction = np.asarray(model.predict(current_values), dtype=float)
        expected_predictions = [
            {"symbol": str(symbol), "value": float(value)}
            for symbol, value in zip(current["symbol"], prediction, strict=True)
        ]
        if expected_predictions != record.get("predictions"):
            raise ValueError(f"R5 staged independent model refit differs: {record.get('model_id')}")
        booster = getattr(model, "booster_", None)
        fitted_sha256 = hashlib.sha256(booster.model_to_string().encode("utf-8")).hexdigest()
        if fitted_sha256 != record.get("fitted_model_sha256"):
            raise ValueError(f"R5 staged fitted model hash mismatch: {record.get('model_id')}")
        successful_refits += 1
    return {
        "pass": True,
        "feature_row_count": len(dataset),
        "decision_count": int(dataset["decision_position"].nunique()),
        "successful_model_refit_count": successful_refits,
        "deterministic_fallback_count": deterministic_fallbacks,
    }


def _reconcile_model_target_coverage(
    model_records: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    model_candidate_ids = {"R5M01", "R5M02", "R5C01", "R5P01"}
    expected_keys = [
        (
            str(row.get("segment_id") or ""),
            str(row.get("candidate_id") or ""),
            str(row.get("decision_session") or ""),
        )
        for row in target_rows
        if row.get("candidate_id") in model_candidate_ids
    ]
    actual_keys = [
        (
            str(record.get("segment_id") or ""),
            str(record.get("candidate_id") or ""),
            str(record.get("decision_session") or ""),
        )
        for record in model_records
    ]
    if (
        any(not all(key) for key in expected_keys)
        or any(not all(key) for key in actual_keys)
        or len(expected_keys) != len(set(expected_keys))
        or len(actual_keys) != len(set(actual_keys))
        or set(actual_keys) != set(expected_keys)
    ):
        raise ValueError("R5 staged model-to-target coverage is incomplete or duplicated")
    return {
        "pass": True,
        "model_candidate_ids": sorted(model_candidate_ids),
        "expected_model_record_count": len(expected_keys),
    }


def _model_provenance_payload(
    model_records: list[dict[str, Any]],
    *,
    prediction_reconciliation: dict[str, Any],
    ledger_inventory: dict[str, dict[str, Any]],
    expected_provenance: dict[str, str],
) -> dict[str, Any]:
    provenance_fields = {
        "data_manifest_sha256",
        "feature_contract_sha256",
        "label_contract_sha256",
        "prompt_hash",
    }
    if set(expected_provenance) != provenance_fields or any(
        not _is_sha256(value) for value in expected_provenance.values()
    ):
        raise ValueError("R5 locked expected model provenance hashes are invalid")
    for ledger_name in ("model_ledger", "prediction_ledger"):
        binding = ledger_inventory.get(ledger_name)
        if (
            not isinstance(binding, dict)
            or type(binding.get("row_count")) is not int
            or not _is_sha256(binding.get("sha256"))
        ):
            raise ValueError(f"R5 model provenance ledger inventory is invalid: {ledger_name}")
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "status": "historical_models_are_fold_local_evidence_not_reusable_deployed_state",
        "model_fit_count": len(model_records),
        "successful_fit_count": sum(row.get("status") == "fit_complete" for row in model_records),
        "fallback_fit_count": sum(row.get("status") != "fit_complete" for row in model_records),
        **expected_provenance,
        "warm_start_used": False,
        "serialized_estimator_promoted": False,
        "ledger_path": f"{ITERATION_DIR.as_posix()}/evaluation-run/model-ledger.jsonl",
        "ledger_sha256": ledger_inventory["model_ledger"]["sha256"],
        "prediction_ledger_path": (
            f"{ITERATION_DIR.as_posix()}/evaluation-run/prediction-ledger.jsonl"
        ),
        "prediction_ledger_sha256": ledger_inventory["prediction_ledger"]["sha256"],
        "prediction_reconciliation": prediction_reconciliation,
    }


def _reconcile_staged_model_provenance(
    reported: dict[str, Any],
    model_records: list[dict[str, Any]],
    *,
    prediction_reconciliation: dict[str, Any],
    ledger_inventory: dict[str, dict[str, Any]],
    expected_provenance: dict[str, str],
) -> dict[str, Any]:
    expected = _model_provenance_payload(
        model_records,
        prediction_reconciliation=prediction_reconciliation,
        ledger_inventory=ledger_inventory,
        expected_provenance=expected_provenance,
    )
    if _canonical_json_bytes(reported) != _canonical_json_bytes(expected):
        raise ValueError("R5 staged model provenance payload is not independently derived")
    return {"pass": True, "model_fit_count": len(model_records)}


def _rebuild_staged_model_and_target_ledgers(
    feature_rows: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    specs: dict[str, StrategySpec],
    validation_contract: dict[str, Any],
    columns: pd.Index,
    *,
    expected_provenance: dict[str, str],
) -> dict[str, Any]:
    coverage_reconciliation = _reconcile_model_target_coverage(
        model_records,
        target_rows,
    )
    if not model_records:
        raise ValueError("R5 staged model ledger is empty")
    provenance_fields = {
        "data_manifest_sha256",
        "feature_contract_sha256",
        "label_contract_sha256",
        "prompt_hash",
    }
    if set(expected_provenance) != provenance_fields or any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in expected_provenance.values()
    ):
        raise ValueError("R5 locked expected model provenance hashes are invalid")
    if any(
        record.get(field_name) != value
        for record in model_records
        for field_name, value in expected_provenance.items()
    ):
        raise ValueError("R5 staged model provenance differs from locked evidence")
    refit_reconciliation = _reconcile_feature_and_model_refits(
        feature_rows,
        model_records,
        specs,
    )
    folds = list(validation_contract["folds"])
    transfer = validation_contract["transfer_holdout"]
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
    dataset = pd.DataFrame(feature_rows)
    rebuilt_target_rows: list[dict[str, Any]] = []
    rebuilt_model_records: list[dict[str, Any]] = []
    for segment in segments:
        _, generated_targets, generated_models, _ = build_candidate_targets_for_segment(
            dataset,
            segment_id=str(segment["segment_id"]),
            execution_start=str(segment["start"]),
            execution_end=str(segment["end"]),
            train_start_session=str(segment["train_start"]),
            columns=columns,
            specs=specs,
            provenance=expected_provenance,
        )
        rebuilt_target_rows.extend(generated_targets)
        rebuilt_model_records.extend(generated_models)
    if _canonical_json_bytes(rebuilt_model_records) != _canonical_json_bytes(model_records):
        raise ValueError("R5 staged model ledger differs from independent full rebuild")
    if _canonical_json_bytes(rebuilt_target_rows) != _canonical_json_bytes(target_rows):
        raise ValueError("R5 staged target ledger differs from independent model/feature rebuild")
    return {
        **refit_reconciliation,
        "model_target_coverage": coverage_reconciliation,
        "full_model_ledger_rebuilt": True,
        "full_target_ledger_rebuilt": True,
        "rebuilt_model_record_count": len(rebuilt_model_records),
        "rebuilt_target_row_count": len(rebuilt_target_rows),
    }


def _replay_staged_feature_ledger(
    panel: PanelData,
    feature_rows: list[dict[str, Any]],
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    execution_contract = _validate_r5_spec_execution_contract(specs)
    features = build_point_in_time_features(
        panel.close,
        panel.volume,
        formula_spec=specs[execution_contract["formula_spec_candidate_id"]],
    )
    dataset = build_monthly_feature_dataset(
        panel,
        features,
        placebo_spec=specs[execution_contract["placebo_spec_candidate_id"]],
        rebalance_schedule=execution_contract["rebalance_schedule"],
    )
    expected_rows = _dataframe_records(dataset)
    if _canonical_json_bytes(expected_rows) != _canonical_json_bytes(feature_rows):
        raise ValueError("R5 staged feature ledger differs from locked OHLCV/spec replay")
    return {
        "pass": True,
        "feature_row_count": len(expected_rows),
        "decision_count": int(dataset["decision_position"].nunique()),
        "feature_ledger_sha256": _jsonl_sha256(expected_rows),
        "locked_ohlcv_replayed": True,
        "formula_spec_candidate_id": execution_contract["formula_spec_candidate_id"],
        "placebo_spec_candidate_id": execution_contract["placebo_spec_candidate_id"],
    }


def _assert_metric_mapping_matches(
    label: str,
    actual: dict[str, Any],
    expected: dict[str, Any],
    *,
    ignored_fields: set[str] | None = None,
) -> None:
    ignored_fields = ignored_fields or set()
    actual_keys = set(actual) - ignored_fields
    expected_keys = set(expected) - ignored_fields
    if actual_keys != expected_keys:
        raise ValueError(f"R5 metric field set mismatch for {label}")
    for field_name in sorted(actual_keys):
        actual_value = actual[field_name]
        expected_value = expected[field_name]
        if isinstance(expected_value, bool) or isinstance(expected_value, str):
            matched = type(actual_value) is type(expected_value) and actual_value == expected_value
        elif isinstance(expected_value, int):
            matched = type(actual_value) is int and actual_value == expected_value
        elif isinstance(expected_value, float):
            matched = math.isclose(
                float(actual_value),
                expected_value,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        else:
            matched = actual_value == expected_value
        if not matched:
            raise ValueError(f"R5 metric mismatch for {label}:{field_name}")


def _strip_scope_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key
        not in {
            "schema_version",
            "iter_id",
            "candidate_id",
            "scope_id",
            "cost_view",
        }
    }


def _replay_staged_performance_ledgers(
    marks: pd.DataFrame,
    target_rows: list[dict[str, Any]],
    daily_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    payload: dict[str, Any],
    runtime_contracts: dict[str, Any],
) -> dict[str, Any]:
    validation_contract = runtime_contracts["validation"]
    aggregate_targets, segment_targets, _ = _staged_target_frames(
        target_rows,
        validation_contract,
    )
    folds = list(validation_contract["folds"])
    transfer = validation_contract["transfer_holdout"]
    segments = [
        {
            "segment_id": str(fold["fold_id"]),
            "start": str(fold["test_start"]),
            "end": str(fold["test_end"]),
        }
        for fold in folds
    ]
    segments.append(
        {
            "segment_id": "TRANSFER",
            "start": str(transfer["start"]),
            "end": str(transfer["end"]),
        }
    )
    aggregate_start = str(segments[0]["start"])
    aggregate_end = str(segments[-1]["end"])
    cost_views = runtime_contracts["cost_views"]
    expected_daily_rows: list[dict[str, Any]] = []
    expected_event_rows: list[dict[str, Any]] = []

    def append_simulation(
        simulation: ExactSimulationResult,
        *,
        candidate_id: str,
        scope_id: str,
        cost_view: str,
    ) -> None:
        expected_daily_rows.extend(
            _scoped_daily_returns(
                simulation.daily,
                candidate_id=candidate_id,
                scope_id=scope_id,
                cost_view=cost_view,
            )
        )
        expected_event_rows.extend(
            _scoped_events(
                simulation.events,
                candidate_id=candidate_id,
                scope_id=scope_id,
                cost_view=cost_view,
            )
        )

    candidate_simulation_count = 0
    replayed_aggregate: dict[str, dict[str, ExactSimulationResult]] = {}
    replayed_segments: dict[str, dict[str, dict[str, ExactSimulationResult]]] = {}
    for candidate_id in SPEC_PATHS:
        replayed_aggregate[candidate_id] = {}
        replayed_segments[candidate_id] = {}
        for cost_view, cost_bps in cost_views.items():
            simulation = simulate_exact_target_portfolio(
                marks,
                aggregate_targets[candidate_id],
                cost_bps=float(cost_bps),
                start=aggregate_start,
                end=aggregate_end,
            )
            replayed_aggregate[candidate_id][cost_view] = simulation
            append_simulation(
                simulation,
                candidate_id=candidate_id,
                scope_id="AGGREGATE",
                cost_view=cost_view,
            )
            candidate_simulation_count += 1
        for segment in segments:
            scope_id = str(segment["segment_id"])
            replayed_segments[candidate_id][scope_id] = {}
            for cost_view in ("primary_10bps", "stress_20bps"):
                simulation = simulate_exact_target_portfolio(
                    marks,
                    segment_targets[scope_id][candidate_id],
                    cost_bps=float(cost_views[cost_view]),
                    start=str(segment["start"]),
                    end=str(segment["end"]),
                )
                replayed_segments[candidate_id][scope_id][cost_view] = simulation
                append_simulation(
                    simulation,
                    candidate_id=candidate_id,
                    scope_id=scope_id,
                    cost_view=cost_view,
                )
                candidate_simulation_count += 1

    benchmark_payload, benchmark_simulations, benchmark_targets = _benchmark_family_exact(
        marks,
        monthly_sessions=aggregate_targets["R5D01"].index,
        start=aggregate_start,
        end=aggregate_end,
        primary_cost_bps=float(cost_views["primary_10bps"]),
        stress_cost_bps=float(cost_views["stress_20bps"]),
    )
    if _canonical_json_bytes(benchmark_payload) != _canonical_json_bytes(payload.get("benchmarks")):
        raise ValueError("R5 staged benchmark payload differs from locked-mark replay")
    expected_benchmark_rows = _benchmark_ledger_rows(
        benchmark_payload,
        benchmark_simulations,
        benchmark_targets,
        promotion_gate_ids=set(
            runtime_contracts["benchmark_gate_config"]["required_benchmark_ids"]
        ),
    )
    if _canonical_json_bytes(expected_benchmark_rows) != _canonical_json_bytes(benchmark_rows):
        raise ValueError("R5 staged benchmark ledger differs from locked-mark replay")
    benchmark_simulation_count = 0
    for benchmark_id, views in benchmark_simulations.items():
        for cost_view, simulation in views.items():
            append_simulation(
                simulation,
                candidate_id=f"BENCHMARK:{benchmark_id}",
                scope_id="AGGREGATE",
                cost_view=cost_view,
            )
            benchmark_simulation_count += 1

    if _canonical_json_bytes(expected_daily_rows) != _canonical_json_bytes(daily_rows):
        raise ValueError("R5 staged daily-return ledger differs from locked-mark replay")
    if _canonical_json_bytes(expected_event_rows) != _canonical_json_bytes(event_rows):
        raise ValueError("R5 staged cost-event ledger differs from locked-mark replay")
    independently_recomputed_cost_reconciliation = _cost_reconciliation(
        replayed_aggregate,
        replayed_segments,
        segments,
        benchmarks=benchmark_simulations,
        tolerance=float(runtime_contracts["cost_reconciliation_tolerance"]),
        expected_event_reason_codes=set(runtime_contracts["cost_event_reason_codes"]),
        expected_cost_bps_by_view={str(name): float(value) for name, value in cost_views.items()},
    )
    return {
        "pass": True,
        "candidate_simulation_count": candidate_simulation_count,
        "benchmark_simulation_count": benchmark_simulation_count,
        "daily_return_row_count": len(expected_daily_rows),
        "cost_event_row_count": len(expected_event_rows),
        "daily_return_ledger_sha256": _jsonl_sha256(expected_daily_rows),
        "cost_event_ledger_sha256": _jsonl_sha256(expected_event_rows),
        "independently_recomputed_cost_reconciliation": (
            independently_recomputed_cost_reconciliation
        ),
    }


def _reconcile_performance_ledgers(
    daily_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    benchmark_rows: list[dict[str, Any]],
    payload: dict[str, Any],
    runtime_contracts: dict[str, Any],
) -> dict[str, Any]:
    tolerance = float(runtime_contracts["cost_reconciliation_tolerance"])
    reason_codes = set(runtime_contracts["cost_event_reason_codes"])
    cost_bps_by_view = runtime_contracts["cost_views"]

    def select_rows(
        rows: list[dict[str, Any]],
        candidate_id: str,
        scope_id: str,
        cost_view: str,
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if row.get("candidate_id") == candidate_id
            and row.get("scope_id") == scope_id
            and row.get("cost_view") == cost_view
        ]

    def reconcile_group(
        candidate_id: str,
        scope_id: str,
        cost_view: str,
        expected_metrics: dict[str, Any],
    ) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
        selected_daily = select_rows(daily_rows, candidate_id, scope_id, cost_view)
        selected_events = select_rows(event_rows, candidate_id, scope_id, cost_view)
        if not selected_daily or not selected_events:
            raise ValueError(
                f"R5 staged performance ledger group missing: {candidate_id}:{scope_id}:{cost_view}"
            )
        intervals = [str(row.get("interval_start") or "") for row in selected_daily]
        if len(intervals) != len(set(intervals)) or intervals != sorted(intervals):
            raise ValueError(
                f"R5 staged daily intervals invalid: {candidate_id}:{scope_id}:{cost_view}"
            )
        daily = pd.DataFrame([_strip_scope_fields(row) for row in selected_daily])
        events = [_strip_scope_fields(row) for row in selected_events]
        maximum_weight = float(daily["maximum_asset_weight_observed"].max())
        recomputed = performance_metrics(daily, events, maximum_weight=maximum_weight)
        _assert_metric_mapping_matches(
            f"{candidate_id}:{scope_id}:{cost_view}",
            recomputed,
            expected_metrics,
            ignored_fields={"annualized_BIL_excess_sharpe"},
        )
        simulation = ExactSimulationResult(daily=daily, events=events, metrics=recomputed)
        expected_cost_bps = _required_cost_view_bps(cost_bps_by_view, cost_view)
        checks = _simulation_accounting_checks(
            simulation,
            expected_start=str(daily.iloc[0]["interval_start"]),
            tolerance=tolerance,
            expected_event_reason_codes=reason_codes,
            expected_cost_bps=expected_cost_bps,
        )
        if checks["failures"]:
            raise ValueError(
                f"R5 staged accounting mismatch: {candidate_id}:{scope_id}:{cost_view}:"
                + ",".join(checks["failures"])
            )
        return daily, events, recomputed

    group_count = 0
    candidate_primary_daily: dict[str, pd.Series] = {}
    for candidate_id, candidate in payload["candidates"].items():
        for cost_view, metrics in candidate["aggregate_cost_views"].items():
            daily, _, _ = reconcile_group(candidate_id, "AGGREGATE", cost_view, metrics)
            group_count += 1
            if cost_view == "primary_10bps":
                candidate_primary_daily[candidate_id] = daily["net_return"].astype(float)
        for scope_id, views in {
            **candidate["folds"],
            "TRANSFER": candidate["transfer_holdout"],
        }.items():
            for cost_view, metrics in views.items():
                reconcile_group(candidate_id, scope_id, cost_view, metrics)
                group_count += 1

    benchmark_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in benchmark_rows:
        key = (str(row.get("benchmark_id") or ""), str(row.get("cost_view") or ""))
        if not all(key) or key in benchmark_by_key:
            raise ValueError("R5 benchmark ledger contains an invalid or duplicate identity")
        benchmark_by_key[key] = row
    required_gate_ids = set(runtime_contracts["benchmark_gate_config"]["required_benchmark_ids"])
    cash_primary: pd.Series | None = None
    for benchmark_id, benchmark in payload["benchmarks"]["results"].items():
        staged_id = f"BENCHMARK:{benchmark_id}"
        for cost_view, metrics in benchmark["cost_views"].items():
            daily, events, recomputed = reconcile_group(
                staged_id,
                "AGGREGATE",
                cost_view,
                metrics,
            )
            group_count += 1
            row = benchmark_by_key.pop((benchmark_id, cost_view), None)
            if row is None:
                raise ValueError(f"R5 benchmark ledger row missing: {benchmark_id}:{cost_view}")
            if bool(row.get("promotion_gate")) != (benchmark_id in required_gate_ids):
                raise ValueError(f"R5 benchmark promotion flag mismatch: {benchmark_id}")
            if row.get("daily") != _dataframe_records(daily):
                raise ValueError(f"R5 benchmark embedded daily rows mismatch: {benchmark_id}")
            if row.get("events") != [_json_ready(event) for event in events]:
                raise ValueError(f"R5 benchmark embedded event rows mismatch: {benchmark_id}")
            _assert_metric_mapping_matches(
                f"benchmark:{benchmark_id}:{cost_view}",
                recomputed,
                row.get("metrics") or {},
            )
            if benchmark_id == "cash_proxy" and cost_view == "primary_10bps":
                cash_primary = daily["net_return"].astype(float)
    if benchmark_by_key:
        raise ValueError("R5 benchmark ledger contains unexpected rows")
    if cash_primary is None:
        raise ValueError("R5 staged cash benchmark is missing")
    for candidate_id, returns in candidate_primary_daily.items():
        expected = float(
            payload["candidates"][candidate_id]["aggregate_cost_views"]["primary_10bps"][
                "annualized_BIL_excess_sharpe"
            ]
        )
        actual = defined_annualized_sharpe(returns - cash_primary)
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"R5 staged BIL-excess Sharpe mismatch for {candidate_id}")
    return {"pass": True, "simulation_group_count": group_count}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ValueError(f"blank JSONL row at {path}:{line_number}")
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
                rows.append(row)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSONL artifact: {path}") from exc
    return rows


def _reconcile_candidate_manifest_and_specs(
    payload: dict[str, Any],
    candidate_manifest: dict[str, Any],
    specs: dict[str, StrategySpec],
) -> dict[str, Any]:
    rows = candidate_manifest.get("candidates")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("R5 staged candidate manifest rows are invalid")
    by_id = {str(row.get("candidate_id") or ""): row for row in rows}
    if (
        list(by_id) != list(SPEC_PATHS)
        or len(by_id) != len(rows)
        or candidate_manifest.get("candidate_count") != len(SPEC_PATHS)
        or payload.get("candidate_count") != len(SPEC_PATHS)
        or set(payload.get("candidates") or {}) != set(SPEC_PATHS)
    ):
        raise ValueError("R5 staged candidate manifest identity is invalid")
    for candidate_id in SPEC_PATHS:
        if by_id[candidate_id] != R5_CANDIDATE_ROLE_CONTRACT[candidate_id]:
            raise ValueError(
                f"R5 staged candidate role differs from immutable contract: {candidate_id}"
            )
    manifest_spec_hashes = candidate_manifest.get("spec_hashes")
    if not isinstance(manifest_spec_hashes, dict) or set(manifest_spec_hashes) != {
        path.as_posix() for path in SPEC_PATHS.values()
    }:
        raise ValueError("R5 staged candidate manifest spec-hash inventory is invalid")
    for candidate_id, relative_path in SPEC_PATHS.items():
        spec = specs[candidate_id]
        candidate = payload["candidates"][candidate_id]
        manifest_row = by_id[candidate_id]
        semantic_sha256 = strategy_content_hash(spec)
        expected_promotion_eligible = R5_CANDIDATE_ROLE_CONTRACT[candidate_id]["promotion_eligible"]
        if (
            manifest_row.get("spec_path") != relative_path.as_posix()
            or manifest_spec_hashes.get(relative_path.as_posix()) != semantic_sha256
            or candidate.get("spec_path") != relative_path.as_posix()
            or candidate.get("strategy_name") != spec.name
            or candidate.get("spec_hash") != semantic_sha256
            or candidate.get("promotion_eligible") is not expected_promotion_eligible
        ):
            raise ValueError(f"R5 staged candidate/spec/manifest binding failed: {candidate_id}")
    return {
        "pass": True,
        "candidate_count": len(SPEC_PATHS),
        "promotion_eligible_candidate_ids": [
            candidate_id
            for candidate_id in SPEC_PATHS
            if candidate_id in R5_PROMOTION_ELIGIBLE_CANDIDATE_IDS
        ],
        "selection_prohibited_candidate_ids": [
            candidate_id
            for candidate_id in SPEC_PATHS
            if candidate_id in R5_SELECTION_PROHIBITED_CANDIDATE_IDS
        ],
    }


def _verify_staged_ledger_bundle(
    paths: dict[str, Path],
    payload: dict[str, Any],
    runtime_contracts: dict[str, Any],
    specs: dict[str, StrategySpec],
    panel: PanelData,
    *,
    root: Path,
    locked_artifact_sha256_by_path: dict[str, str],
    expected_model_provenance: dict[str, str],
) -> dict[str, Any]:
    ledger_names = {
        "feature_ledger": "feature_ledger",
        "prediction_ledger": "prediction_ledger",
        "daily_return_ledger": "daily_return_ledger",
        "target_ledger": "target_ledger",
        "event_ledger": "event_ledger",
        "benchmark_ledger": "benchmark_ledger",
        "model_ledger": "model_ledger",
        "trial_ledger": "trial_ledger",
    }
    inventory = payload["evidence_reconciliation"]["ledger_inventory"]
    loaded: dict[str, list[dict[str, Any]]] = {}
    for path_name, inventory_name in ledger_names.items():
        rows = _load_jsonl(paths[path_name])
        expected = inventory[inventory_name]
        if len(rows) != int(expected["row_count"]):
            raise ValueError(f"R5 staged ledger row count mismatch: {inventory_name}")
        if _jsonl_sha256(rows) != expected["sha256"]:
            raise ValueError(f"R5 staged ledger hash mismatch: {inventory_name}")
        if _sha256_file(paths[path_name]) != expected["sha256"]:
            raise ValueError(f"R5 staged ledger file hash mismatch: {inventory_name}")
        loaded[inventory_name] = rows

    manifest_reconciliation = _reconcile_candidate_manifest_and_specs(
        payload,
        runtime_contracts["candidate_manifest"],
        specs,
    )
    feature_replay = _replay_staged_feature_ledger(
        panel,
        loaded["feature_ledger"],
        specs,
    )
    harness_reconciliation = _validate_r5_harness_evidence(
        root,
        specs,
        locked_artifact_sha256_by_path=locked_artifact_sha256_by_path,
    )
    if _canonical_json_bytes(harness_reconciliation) != _canonical_json_bytes(
        payload.get("harness_reconciliation")
    ):
        raise ValueError("R5 staged harness reconciliation differs from locked evidence")
    if hashlib.sha256(_canonical_json_bytes(harness_reconciliation)).hexdigest() != payload.get(
        "preflight", {}
    ).get("harness_reconciliation_sha256"):
        raise ValueError("R5 staged harness reconciliation hash mismatch")

    recomputed_llm_bootstrap = paired_transfer_sharpe_bootstrap(
        loaded["daily_return_ledger"],
        loaded["event_ledger"],
        contract=runtime_contracts["llm_contribution_bootstrap_config"],
    )
    if _canonical_json_bytes(recomputed_llm_bootstrap) != _canonical_json_bytes(
        payload.get("llm_contribution_bootstrap")
    ):
        raise ValueError("R5 staged LLM contribution bootstrap differs from report")

    target_reconciliation = _reconcile_target_ledger_evidence(
        loaded["target_ledger"],
        payload["candidates"],
    )
    prediction_reconciliation = _reconcile_model_prediction_evidence(
        loaded["model_ledger"],
        loaded["prediction_ledger"],
    )
    if prediction_reconciliation != payload["evidence_reconciliation"]["prediction_reconciliation"]:
        raise ValueError("R5 staged prediction reconciliation differs from report")
    model_refit_reconciliation = _rebuild_staged_model_and_target_ledgers(
        loaded["feature_ledger"],
        loaded["model_ledger"],
        loaded["target_ledger"],
        specs,
        runtime_contracts["validation"],
        panel.open.columns,
        expected_provenance=expected_model_provenance,
    )

    trial_reconciliation = _reconcile_staged_trial_ledger(
        payload["candidates"],
        loaded["trial_ledger"],
    )

    folds = runtime_contracts["validation"]["folds"]
    pbo_contract = runtime_contracts["validation"]["pbo"]
    pbo_frame, pbo_ledger_source_rows = _pbo_returns_from_daily_ledger(
        loaded["daily_return_ledger"],
        folds=folds,
        candidate_ids=list(SPEC_PATHS),
    )
    if len(pbo_frame) != int(pbo_contract["expected_return_observation_count"]):
        raise ValueError("R5 staged PBO observation count mismatch")
    selection_ids = list(map(str, pbo_contract["selection_candidate_ids"]))
    recomputed_pbo = probability_backtest_overfitting(
        pbo_frame,
        candidate_ids=selection_ids,
        block_count=int(pbo_contract["block_count"]),
        in_sample_block_count=int(pbo_contract["in_sample_block_count"]),
    )
    reported_pbo = payload["family_pbo"]
    for field_name, value in recomputed_pbo.items():
        if _canonical_json_bytes(reported_pbo.get(field_name)) != _canonical_json_bytes(value):
            raise ValueError(f"R5 staged PBO mismatch: {field_name}")
    pbo_source_rows = [
        {
            "scope_id": row["scope_id"],
            "interval_start": row["interval_start"],
            "interval_end": row["interval_end"],
            **{candidate_id: float(row[candidate_id]) for candidate_id in selection_ids},
        }
        for row in pbo_ledger_source_rows
    ]
    if hashlib.sha256(_canonical_json_bytes(pbo_source_rows)).hexdigest() != reported_pbo.get(
        "return_source_sha256"
    ):
        raise ValueError("R5 staged PBO source hash mismatch")

    dsr_scope_ids = [str(row["scope_id"]) for row in pbo_ledger_source_rows]
    for candidate_id in SPEC_PATHS:
        reported_dsr = payload["candidates"][candidate_id]["dsr"]
        recomputed_by_trial_count: dict[str, dict[str, Any]] = {}
        for trial_count in runtime_contracts["dsr_sensitivity_trial_counts"]:
            recomputed = deflated_sharpe_ratio(
                pbo_frame[candidate_id],
                trial_count=trial_count,
                scope_ids=dsr_scope_ids,
                hac_lag=int(runtime_contracts["dsr_config"]["hac_lag"]),
            )
            recomputed_by_trial_count[str(trial_count)] = recomputed
            reported = reported_dsr["sensitivity"][str(trial_count)]
            if _canonical_json_bytes(recomputed) != _canonical_json_bytes(reported):
                raise ValueError(f"R5 staged DSR mismatch: {candidate_id}:{trial_count}")
        governance = recomputed_by_trial_count[str(runtime_contracts["trial_count"])]
        for field_name, value in governance.items():
            if _canonical_json_bytes(reported_dsr.get(field_name)) != _canonical_json_bytes(value):
                raise ValueError(f"R5 staged DSR governance mismatch: {candidate_id}:{field_name}")
        return_rows = [
            {
                "scope_id": row["scope_id"],
                "interval_start": row["interval_start"],
                "interval_end": row["interval_end"],
                "net_return": float(row[candidate_id]),
            }
            for row in pbo_ledger_source_rows
        ]
        expected_source_sha256 = hashlib.sha256(_canonical_json_bytes(return_rows)).hexdigest()
        if reported_dsr.get("return_source_sha256") != expected_source_sha256:
            raise ValueError(f"R5 staged DSR source hash mismatch: {candidate_id}")
        if reported_dsr.get("probability") != reported_dsr.get("promotion_probability"):
            raise ValueError(f"R5 staged DSR probability alias mismatch: {candidate_id}")

    performance_reconciliation = _reconcile_performance_ledgers(
        loaded["daily_return_ledger"],
        loaded["event_ledger"],
        loaded["benchmark_ledger"],
        payload,
        runtime_contracts,
    )
    locked_mark_replay = _replay_staged_performance_ledgers(
        panel.open,
        loaded["target_ledger"],
        loaded["daily_return_ledger"],
        loaded["event_ledger"],
        loaded["benchmark_ledger"],
        payload,
        runtime_contracts,
    )
    role_gate_reconciliation = _reconcile_staged_role_gate_evidence(
        feature_rows=loaded["feature_ledger"],
        model_records=loaded["model_ledger"],
        target_rows=loaded["target_ledger"],
        candidates=payload["candidates"],
        reported_calibration=payload["calibration"],
        reported_formula_placebo_evidence=payload["formula_placebo_evidence"],
        llm_contribution_bootstrap=recomputed_llm_bootstrap,
        validation_contract=runtime_contracts["validation"],
    )
    recomputed_benchmark_gates = _reconcile_staged_benchmark_gates(
        payload["candidates"],
        benchmark_payload=payload["benchmarks"],
        benchmark_contract=runtime_contracts["benchmark"],
    )
    recomputed_candidate_gates = _evaluate_candidate_gates(
        payload["candidates"],
        runtime_contracts["validation"],
        benchmark_gates=recomputed_benchmark_gates,
    )
    for candidate_id, gates in recomputed_candidate_gates.items():
        if _canonical_json_bytes(gates) != _canonical_json_bytes(
            payload["candidates"][candidate_id]["family_gates"]
        ):
            raise ValueError(f"R5 staged candidate gate mismatch: {candidate_id}")
    cost_reconciliation = _load_json(paths["cost_reconciliation"])
    independently_recomputed_cost_reconciliation = locked_mark_replay[
        "independently_recomputed_cost_reconciliation"
    ]
    _require_independent_cost_reconciliation(
        cost_reconciliation,
        payload["cost_reconciliation"],
        independently_recomputed_cost_reconciliation,
    )
    recomputed_pbo_pass = _pbo_gate_pass(
        recomputed_pbo,
        pbo_config=runtime_contracts["pbo_config"],
        validation_contract=runtime_contracts["validation"],
    )
    if payload.get("family_pbo_pass") is not recomputed_pbo_pass:
        raise ValueError("R5 staged family PBO status is not derived from the ledger")
    benchmark_payload = payload.get("benchmarks")
    recomputed_workflow_pass = bool(
        harness_reconciliation["research_gate_pass"] is True
        and manifest_reconciliation["pass"]
        and target_reconciliation["pass"]
        and prediction_reconciliation["pass"]
        and model_refit_reconciliation["pass"]
        and performance_reconciliation["pass"]
        and independently_recomputed_cost_reconciliation.get("pass") is True
        and isinstance(benchmark_payload, dict)
        and benchmark_payload.get("complete") is True
        and benchmark_payload.get("same_cost_engine") is True
    )
    recomputed_statuses = _derive_evaluation_statuses(
        payload["candidates"],
        workflow_pass=recomputed_workflow_pass,
        pbo_pass=recomputed_pbo_pass,
    )
    for field_name, expected in recomputed_statuses.items():
        if _canonical_json_bytes(payload.get(field_name)) != _canonical_json_bytes(expected):
            raise ValueError(f"R5 staged evaluation status is not derived: {field_name}")
    model_provenance = _load_json(paths["model_provenance"])
    model_provenance_reconciliation = _reconcile_staged_model_provenance(
        model_provenance,
        loaded["model_ledger"],
        prediction_reconciliation=prediction_reconciliation,
        ledger_inventory=inventory,
        expected_provenance=expected_model_provenance,
    )
    return {
        "pass": True,
        "ledger_count": len(ledger_names),
        "manifest_reconciliation": manifest_reconciliation,
        "harness_reconciliation": {
            "pass": harness_reconciliation["research_gate_pass"],
            "empirical_execution_evidence_pass": harness_reconciliation[
                "empirical_execution_evidence_pass"
            ],
            "paper_readiness_evidence_pass": harness_reconciliation[
                "paper_readiness_evidence_pass"
            ],
        },
        "target_reconciliation": target_reconciliation,
        "feature_replay": feature_replay,
        "prediction_reconciliation": prediction_reconciliation,
        "model_refit_reconciliation": model_refit_reconciliation,
        "model_provenance_reconciliation": model_provenance_reconciliation,
        "performance_reconciliation": performance_reconciliation,
        "locked_mark_replay": locked_mark_replay,
        "role_gate_reconciliation": role_gate_reconciliation,
        "trial_reconciliation": trial_reconciliation,
        "pbo_recomputed": True,
        "dsr_sensitivity_recomputed": True,
        "llm_contribution_bootstrap_recomputed": True,
        "benchmark_gates_recomputed": True,
        "evaluation_statuses_recomputed": True,
    }


def _verify_staged_publication(
    paths: dict[str, Path],
    published_paths: dict[str, Path],
    payload: dict[str, Any],
    receipt: dict[str, Any],
    evaluation_anchor: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    expected_names = set(paths)
    actual_entries = list(next(iter(paths.values())).parent.iterdir())
    actual_filenames = {path.name for path in actual_entries}
    expected_filenames = {path.name for path in paths.values()}
    if actual_filenames != expected_filenames:
        raise ValueError("R5 staged publication file inventory mismatch")
    if any(path.is_symlink() or not path.is_file() for path in actual_entries):
        raise ValueError("R5 staged publication contains a non-regular file")
    if _canonical_json_bytes(_load_json(paths["evaluation"])) != _canonical_json_bytes(payload):
        raise ValueError("R5 staged evaluation report differs from in-memory payload")
    if _canonical_json_bytes(_load_json(paths["receipt"])) != _canonical_json_bytes(receipt):
        raise ValueError("R5 staged receipt differs from in-memory payload")
    if _canonical_json_bytes(_load_json(paths["evaluation_anchor"])) != _canonical_json_bytes(
        evaluation_anchor
    ):
        raise ValueError("R5 staged evaluation anchor differs from in-memory payload")
    payload_child_names = {
        "feature_ledger",
        "prediction_ledger",
        "daily_return_ledger",
        "target_ledger",
        "event_ledger",
        "benchmark_ledger",
        "model_ledger",
        "trial_ledger",
        "cost_reconciliation",
        "model_provenance",
    }
    expected_payload_children = {
        name: _binding_for_destination(paths[name], published_paths[name], root)
        for name in payload_child_names
    }
    if payload.get("child_artifacts") != expected_payload_children:
        raise ValueError("R5 staged evaluation child bindings are not derived from files")
    if receipt.get("schema_version") != 3 or receipt.get("receipt_contract") != (
        "multiasset_forward_multimodal_r5_v3"
    ):
        raise ValueError("R5 staged receipt contract is invalid")
    expected_children = expected_names - {"receipt", "evaluation_anchor"}
    if set(receipt.get("children") or {}) != expected_children:
        raise ValueError("R5 staged receipt child inventory mismatch")
    for name in expected_children:
        binding = receipt["children"][name]
        expected_binding = _binding_for_destination(paths[name], published_paths[name], root)
        if binding != expected_binding:
            raise ValueError(f"R5 staged receipt child binding mismatch: {name}")
    for field_name in (
        "decision",
        "workflow_pass",
        "research_pass",
        "llm_contribution_pass",
        "paper_ready_pass",
    ):
        if receipt.get(field_name) != payload.get(field_name):
            raise ValueError(f"R5 staged receipt status mismatch: {field_name}")
    if receipt.get("paper_ready_pass") is not False:
        raise ValueError("R5 staged receipt cannot assert Paper readiness")
    for name, expected_path in {
        "preregistration_lock": root / ITERATION_DIR / "lock-set/preregistration-lock.json",
        "runner_lock": root / ITERATION_DIR / "lock-set/runner-lock.json",
        "lock_anchor": root / ITERATION_DIR / "lock-set/lock-anchor.json",
        "evaluation_attempt": root / ITERATION_DIR / "evaluation-attempt.json",
    }.items():
        if receipt.get(name) != _file_binding(expected_path, root):
            raise ValueError(f"R5 staged external binding mismatch: {name}")
    expected_anchor = _evaluation_anchor_payload(
        root=root,
        receipt_source=paths["receipt"],
        receipt_destination=published_paths["receipt"],
        anchor_destination=published_paths["evaluation_anchor"],
        preregistration_lock_path=root / ITERATION_DIR / "lock-set/preregistration-lock.json",
        runner_lock_path=root / ITERATION_DIR / "lock-set/runner-lock.json",
        lock_anchor_path=root / ITERATION_DIR / "lock-set/lock-anchor.json",
        evaluation_attempt_path=root / ITERATION_DIR / "evaluation-attempt.json",
    )
    if evaluation_anchor != expected_anchor:
        raise ValueError("R5 staged evaluation anchor bindings are not derived")
    if paths["evaluation_anchor"].stat().st_mode & 0o222:
        raise ValueError("R5 staged evaluation anchor must be read-only")
    return {
        "pass": True,
        "file_count": len(expected_names),
        "child_count": len(expected_children),
        "operator_evaluation_anchor_sha256": evaluation_anchor["operator_evaluation_anchor_sha256"],
    }


def _dataframe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    values = frame.astype(object).where(pd.notna(frame), None)
    return [_json_ready(row) for row in values.to_dict(orient="records")]


def _load_json(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    payload, _ = _load_json_with_sha256(path, expected_sha256=expected_sha256)
    return payload


def _load_json_with_sha256(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    try:
        content = _read_regular_file_bytes(path, expected_sha256=expected_sha256)
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload, hashlib.sha256(content).hexdigest()


def _verify_file_binding(root: Path, binding: Any) -> Path:
    if not isinstance(binding, dict):
        raise ValueError("R5 file binding must be an object")
    relative = str(binding.get("path") or "")
    try:
        path = _repo_file_path(root, relative)
    except ValueError as exc:
        raise ValueError(f"R5 file binding escapes repository: {relative}") from exc
    expected = str(binding.get("sha256") or "")
    try:
        _read_regular_file_bytes(path, expected_sha256=expected)
    except (OSError, ValueError) as exc:
        raise ValueError(f"R5 file binding SHA-256 mismatch: {relative}") from exc
    return path


def _binding_sha256_by_path(bindings: Any, *, label: str) -> dict[str, str]:
    if not isinstance(bindings, list) or not bindings:
        raise ValueError(f"{label} must be a nonempty list")
    result: dict[str, str] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError(f"{label} contains a non-object binding")
        path = str(binding.get("path") or "")
        sha256 = str(binding.get("sha256") or "")
        if not path or not _is_sha256(sha256) or path in result:
            raise ValueError(f"{label} contains an invalid or duplicate binding")
        result[path] = sha256
    return result


def _spec_file_sha256_by_path(bindings: Any) -> dict[str, str]:
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("R5 preregistration specs must be a nonempty list")
    result: dict[str, str] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("R5 preregistration specs contain a non-object binding")
        path = str(binding.get("path") or "")
        sha256 = str(binding.get("file_sha256") or "")
        semantic_sha256 = str(binding.get("semantic_sha256") or "")
        if (
            path not in {candidate_path.as_posix() for candidate_path in SPEC_PATHS.values()}
            or not _is_sha256(sha256)
            or not _is_sha256(semantic_sha256)
            or path in result
        ):
            raise ValueError("R5 preregistration specs contain an invalid binding")
        result[path] = sha256
    if set(result) != {path.as_posix() for path in SPEC_PATHS.values()}:
        raise ValueError("R5 preregistration spec path set is incomplete")
    return result


def _load_strategy_spec_stable(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> StrategySpec:
    try:
        content = _read_regular_file_bytes(path, expected_sha256=expected_sha256)
        raw = safe_load_yaml(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"invalid locked StrategySpec: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    spec = StrategySpec.model_validate(raw)
    from open_composer.expressions import validate_expression

    expression_root = path.parents[2] if len(path.parents) >= 3 else path.parent
    for expression in spec.all_expressions():
        validate_expression(expression, spec.factors, root=expression_root)
    return spec


def _repo_file_path(root: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute():
        raise ValueError("R5 locked path must be repository-relative")
    root_resolved = root.resolve()
    candidate = root_resolved / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("R5 locked path escapes the repository") from exc
    if resolved != candidate:
        raise ValueError("R5 locked path traverses a symlink or noncanonical component")
    return candidate


def _read_regular_file_bytes(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> bytes:
    if path.is_symlink():
        raise ValueError(f"R5 refuses symlinked input: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"R5 input is not a regular file: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    content = b"".join(chunks)
    if identity_before != identity_after or len(content) != before.st_size:
        raise ValueError(f"R5 input changed while being read: {path}")
    if expected_sha256 is not None:
        if not _is_sha256(expected_sha256):
            raise ValueError(f"R5 expected SHA-256 is invalid: {path}")
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise ValueError(f"R5 locked SHA-256 mismatch: {path}")
    return content


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _write_json_atomic(path: Path, payload: Any) -> None:
    _atomic_write(path, _canonical_json_bytes(payload) + b"\n")


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    _atomic_write(path, _jsonl_bytes(rows))


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical_json_bytes(row) + b"\n" for row in rows)


def _jsonl_sha256(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_jsonl_bytes(rows)).hexdigest()


def _write_text_atomic(path: Path, content: str) -> None:
    _atomic_write(path, content.encode("utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _file_binding(path: Path, root: Path) -> dict[str, Any]:
    content = _read_regular_file_bytes(path)
    return {
        "path": _relpath(path, root),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _binding_for_destination(source: Path, destination: Path, root: Path) -> dict[str, Any]:
    content = _read_regular_file_bytes(source)
    return {
        "path": _relpath(destination, root),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }


def _current_runtime() -> dict[str, str]:
    return {
        "python": sys.version,
        "numpy": version("numpy"),
        "pandas": version("pandas"),
        "scipy": version("scipy"),
        "lightgbm": version("lightgbm"),
        "scikit_learn": version("scikit-learn"),
        "pydantic": version("pydantic"),
        "pyyaml": version("PyYAML"),
        "alpaca_py": version("alpaca-py"),
    }


def _reverify_locked_inputs(root: Path, preflight: dict[str, Any]) -> None:
    output = root / ITERATION_DIR
    preregistration_path = output / "lock-set/preregistration-lock.json"
    runner_path = output / "lock-set/runner-lock.json"
    lock_anchor_path = output / "lock-set/lock-anchor.json"
    attempt_path = output / "evaluation-attempt.json"
    preregistration = _load_json(
        preregistration_path,
        expected_sha256=preflight["preregistration_lock_sha256"],
    )
    runner = _load_json(runner_path, expected_sha256=preflight["runner_lock_sha256"])
    _load_json(lock_anchor_path, expected_sha256=preflight["lock_anchor_file_sha256"])
    attempt_binding = preflight.get("evaluation_attempt")
    if not isinstance(attempt_binding, dict):
        raise ValueError("R5 evaluation attempt binding is missing")
    if _verify_file_binding(root, attempt_binding) != attempt_path.resolve():
        raise ValueError("R5 evaluation attempt path changed during evaluation")
    for binding in preregistration.get("artifacts", []):
        _verify_file_binding(root, binding)
    for binding in preregistration.get("specs", []):
        path = _verify_file_binding(
            root,
            {"path": binding.get("path"), "sha256": binding.get("file_sha256")},
        )
        spec = _load_strategy_spec_stable(
            path,
            expected_sha256=str(binding.get("file_sha256") or ""),
        )
        if strategy_content_hash(spec) != binding.get("semantic_sha256"):
            raise ValueError(f"R5 semantic spec changed during evaluation: {binding.get('path')}")
    for binding in runner.get("files", []):
        _verify_file_binding(root, binding)
    if runner.get("runtime") != _current_runtime():
        raise ValueError("R5 runtime changed during evaluation")
    manifest_path = root / preflight["data_manifest_path"]
    parent_path = root / preflight["parent_snapshot_binding_path"]
    _load_json(manifest_path, expected_sha256=preflight["data_manifest_sha256"])
    _read_regular_file_bytes(
        parent_path,
        expected_sha256=preflight["parent_snapshot_binding_sha256"],
    )
    verify_alpaca_contract_snapshot(root, manifest_path)


def _publish_directory_exclusive(stage: Path, destination: Path) -> None:
    if not stage.is_dir() or stage.is_symlink():
        raise ValueError("R5 staged result directory is invalid")
    marker = destination.parent / f".{destination.name}-publish.lock"
    descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        if destination.exists():
            raise ValueError("R5 destination exists; exclusive publication refused")
        os.rename(stage, destination)
        _fsync_directory(destination.parent)
    finally:
        os.close(descriptor)
        if marker.exists():
            marker.unlink()
            _fsync_directory(destination.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(_read_regular_file_bytes(path)).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _render_markdown(payload: dict[str, Any]) -> str:
    bootstrap = payload["llm_contribution_bootstrap"]
    lines = [
        f"# R5 Evaluation: {payload['iter_id']}",
        "",
        f"- Decision: `{payload['decision']}`",
        f"- workflow_pass: `{str(payload['workflow_pass']).lower()}`",
        f"- research_pass: `{str(payload['research_pass']).lower()}`",
        f"- llm_contribution_pass: `{str(payload['llm_contribution_pass']).lower()}`",
        f"- paper_ready_pass: `{str(payload['paper_ready_pass']).lower()}`",
        f"- PBO: `{payload['family_pbo']['probability']:.6f}` over "
        f"`{payload['family_pbo']['partition_count']}` directional partitions",
        f"- Formula contribution method: `{bootstrap['method_id']}`",
        f"- Formula contribution config SHA-256: `{bootstrap['config_sha256']}`",
        f"- Bootstrap index matrix SHA-256: `{bootstrap['bootstrap_index_matrix_sha256']}`",
        f"- Daily-return ledger SHA-256: "
        f"`{bootstrap['source_ledgers']['daily_return_ledger_sha256']}`",
        f"- Cost-event ledger SHA-256: `{bootstrap['source_ledgers']['event_ledger_sha256']}`",
        "",
        "| Candidate | Return % | Sharpe | Max DD % | IID DSR | HAC DSR | "
        "Promotion DSR | Historical gate |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for candidate_id, candidate in payload["candidates"].items():
        metrics = candidate["aggregate_cost_views"]["primary_10bps"]
        lines.append(
            f"| {candidate_id} | {metrics['total_return_pct']:.4f} | "
            f"{metrics['annualized_sharpe']:.4f} | {metrics['max_drawdown_pct']:.4f} | "
            f"{candidate['dsr']['iid_probability']:.6f} | "
            f"{candidate['dsr']['hac_probability']:.6f} | "
            f"{candidate['dsr']['promotion_probability']:.6f} | "
            f"{str(candidate['historical_research_gate_pass']).lower()} |"
        )
    lines.extend(
        [
            "",
            "| Formula comparison | Observed Sharpe delta | 2.5% one-sided LCB | Pass |",
            "|---|---:|---:|---|",
        ]
    )
    for comparison_id, comparison in payload["llm_contribution_bootstrap"]["comparisons"].items():
        lines.append(
            f"| {comparison_id} | "
            f"{comparison['observed_annualized_sharpe_delta']:.6f} | "
            f"{comparison['lower_confidence_bound']:.6f} | "
            f"{str(comparison['pass']).lower()} |"
        )
    lines.extend(
        [
            "",
            "`llm_contribution_pass` means only historical incremental contribution from the "
            "frozen formula mappings against the matched quant model and shuffled-formula "
            "placebo. It is not evidence of independent LLM Alpha or live LLM inference.",
            "Historical results are globally exposed transfer evidence. They do not satisfy the "
            "20-session forward or matched Alpaca Paper TCA requirements.",
            "R5 PBO diagnoses candidate selection over fully specified prequential strategy "
            "return streams. It performs no model refit and is not independent ML "
            "generalization or formula-generation validation.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_record(payload: dict[str, Any]) -> str:
    if payload["research_pass"]:
        decision = "continue"
        reason = (
            "At least one frozen promotion-eligible candidate passed the matched historical "
            "research gates. This authorizes only a newly locked broker-free forward epoch."
        )
        next_step = (
            "Freeze target routing, start at zero forward sessions, and require 20 contiguous "
            "bound sessions before any separately reviewed Paper canary."
        )
    else:
        decision = "stop"
        reason = (
            "No frozen promotion-eligible candidate passed every statistical, role, cost, and "
            "stability gate under the preregistered evaluation."
        )
        next_step = (
            "Create a new preregistered iteration; do not retune or add R5 candidates after "
            "seeing these results."
        )
    return (
        f"# Decision Record: {ITER_ID}\n\n"
        "- Path: `eight_candidate_matched_etf_multimodal_family`\n"
        f"- Decision: {decision}\n"
        f"- Reason: {reason}\n"
        f"- Next iteration suggestion: {next_step}\n\n"
        f"Final stored status is `workflow_pass={str(payload['workflow_pass']).lower()}`, "
        f"`research_pass={str(payload['research_pass']).lower()}`, "
        f"`llm_contribution_pass={str(payload['llm_contribution_pass']).lower()}`, and "
        "`paper_ready_pass=false`. Broker writes remain unauthorized.\n"
    )
