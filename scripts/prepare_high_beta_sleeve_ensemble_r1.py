# ruff: noqa: E501

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.factor_library import write_factor_library_artifact
from open_composer.research.knowledge_memory import claim_fingerprint
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_high_beta_sleeve_ensemble_r1"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SOURCE_CARDS_PATH = Path("reports/harness/source_cards/us_high_beta_sleeve_ensemble_r1.jsonl")
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
PRIMARY_SPEC_PATH = Path("strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_d01.yaml")
FACTOR_LIBRARY_STEM = "us_high_beta_sleeve_ensemble_r1-factor-library"
FACTOR_LIBRARY_PATH = Path("reports/research") / f"{FACTOR_LIBRARY_STEM}.json"
SEMANTIC_PACKET_SCHEMA_PATH = Path(
    "schemas/high_beta_sleeve_ensemble_r1_feature_packet.schema.json"
)
SEMANTIC_PROMPT_PATH = Path("prompts/pit_semantic_theme_r24_factor_v1.txt")
SEMANTIC_PACKET_ROOT = Path("data/forward/high_beta_sleeve_ensemble_r1")
SEMANTIC_CANDIDATE_IDS = frozenset({"S1L01", "S1C01", "S1P01"})
PRIOR_EFFECTIVE_TRIAL_COUNT = 8128
ROUND_CANDIDATE_COUNT = 10
EFFECTIVE_TRIAL_COUNT = PRIOR_EFFECTIVE_TRIAL_COUNT + ROUND_CANDIDATE_COUNT
SOURCE_CARD_CLAIM_IDS = (
    "hbs_r1_alpaca_opg_semantics",
    "hbs_r1_alpaca_paper_limitations",
    "hbs_r1_alpaca_sip_vs_iex",
    "hbs_r1_nasdaq_opening_cross",
    "hbs_r1_tqqq_daily_target_and_path_risk",
    "hbs_r1_time_series_momentum_paper",
    "hbs_r1_leveraged_etf_regime_compounding",
    "hbs_r1_deep_momentum_cost_regularization",
    "hbs_r1_end_to_end_policy_nonuniform_lift",
    "hbs_r1_friction_aware_inaction_band",
    "hbs_r1_model_comparison_with_costs",
    "hbs_r1_deflated_sharpe_method",
    "hbs_r1_probability_backtest_overfitting_method",
)

FACTOR_LIBRARY_IDS = [
    "fixed_anchor_monthly_trend_sleeve",
]
MODEL_FEATURES = [
    "qqq_trend_gap_200",
    "qqq_momentum_252_skip21",
    "tqqq_momentum_21",
    "tqqq_momentum_63",
    "tqqq_realized_volatility_21",
    "tqqq_drawdown_63",
]
BENCHMARK_FAMILY = [
    "TQQQ_buy_hold_same_symbol",
    "QQQ_buy_hold",
    "SPY_buy_hold_market_proxy",
    "SMH_buy_hold_sector_theme_proxy",
    "BIL_buy_hold_cash_proxy",
    "equal_weight_full_spec_universe",
    "ex_post_best_symbol_report_only",
]
COST_VIEW_ROWS = [
    {"name": "low_10bps", "bps": 10.0},
    {"name": "primary_20bps", "bps": 20.0},
    {"name": "severe_40bps", "bps": 40.0},
]
PRIMARY_COST_BPS = 20.0
STRESS_COST_BPS = [row["bps"] for row in COST_VIEW_ROWS]
BENCHMARK_SINGLE_SYMBOLS = {
    "TQQQ_buy_hold_same_symbol": {"TQQQ": 1.0},
    "QQQ_buy_hold": {"QQQ": 1.0},
    "SPY_buy_hold_market_proxy": {"SPY": 1.0},
    "SMH_buy_hold_sector_theme_proxy": {"SMH": 1.0},
    "BIL_buy_hold_cash_proxy": {"BIL": 1.0},
}
BENCHMARK_CASH_PROXY_SYMBOL = "BIL"
FEATURE_EXPRESSIONS = {
    "qqq_trend_gap_200": "close / sma(close, 200) - 1",
    "qqq_momentum_252_skip21": "lag(close, 21) / lag(close, 252) - 1",
    "tqqq_momentum_21": "close / lag(close, 21) - 1",
    "tqqq_momentum_63": "close / lag(close, 63) - 1",
    "tqqq_realized_volatility_21": "stddev(close / lag(close, 1) - 1, 21)",
    "tqqq_drawdown_63": "close / highest(close, 63) - 1",
}
LABEL_MAX_SPAN_SESSIONS = 24
PURGE_SESSIONS = LABEL_MAX_SPAN_SESSIONS
EMBARGO_SESSIONS = LABEL_MAX_SPAN_SESSIONS
MINIMUM_FIT_LABELS = 18
MINIMUM_CALIBRATION_LABELS = 6
MINIMUM_CLASS_LABELS = 5
MINIMUM_CALIBRATION_CLASS_LABELS = 2
M01_TARGET_COVERAGE = 0.80
M01_FOLD_COVERAGE_FLOOR = 0.75
ANNUALIZED_ONE_WAY_TURNOVER_CAP = 6.0

ROLE_ROWS = (
    {
        "candidate_id": "S1D01",
        "suffix": "d01",
        "path": "deterministic_primary",
        "role": "deterministic_equal_anchor_monthly_trend_core",
        "method": "fixed_50pct_TQQQ_anchor_plus_50pct_monthly_QQQ_SMA200_sleeve",
        "ablation": "quant_only_primary",
        "fallback": "BIL_for_tactical_sleeve_only",
        "anchor_weight": 0.5,
        "promotion_eligible": True,
    },
    {
        "candidate_id": "S1D02",
        "suffix": "d02",
        "path": "deterministic_semantic",
        "role": "deterministic_semantic_control",
        "method": "S1D01_plus_zero_capital_structured_event_control",
        "ablation": "deterministic_semantic_control",
        "fallback": "S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": False,
    },
    {
        "candidate_id": "S1M01",
        "suffix": "m01",
        "path": "trained_ml",
        "role": "ridge_after_cost_policy_value_overlay",
        "method": "fold_local_ridge_monthly_tactical_override_with_lower_bound_abstention",
        "ablation": "quant_ml_policy_value",
        "fallback": "S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": True,
    },
    {
        "candidate_id": "S1M02",
        "suffix": "m02",
        "path": "trained_ml",
        "role": "logistic_tail_risk_overlay",
        "method": "fold_local_logistic_anchor_tail_risk_cut_with_calibrated_abstention",
        "ablation": "quant_ml_tail_risk",
        "fallback": "S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": True,
    },
    {
        "candidate_id": "S1L01",
        "suffix": "l01",
        "path": "llm_text",
        "role": "structured_llm_factor_zero_capital",
        "method": "PIT_structured_semantic_observation_no_weight_authority",
        "ablation": "modality_only_zero_capital",
        "fallback": "S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": False,
    },
    {
        "candidate_id": "S1C01",
        "suffix": "c01",
        "path": "combined",
        "role": "quant_ml_plus_structured_llm_zero_capital",
        "method": "S1M01_plus_PIT_semantic_observation_no_weight_authority",
        "ablation": "combined_quant_and_modality",
        "fallback": "S1M01_then_S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": False,
    },
    {
        "candidate_id": "S1F01",
        "suffix": "f01",
        "path": "missing_modality",
        "role": "exact_missing_semantic_fallback",
        "method": "exact_S1M01_target_identity_without_semantic_packet",
        "ablation": "missing_modality_exact_fallback",
        "fallback": "S1M01_then_S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": False,
    },
    {
        "candidate_id": "S1P01",
        "suffix": "p01",
        "path": "placebo",
        "role": "semantic_placebo_dependency_skipped",
        "method": "dependency_skipped_no_historical_packets_exact_S1D01_identity",
        "ablation": "planned_placebo_modality_not_executed",
        "fallback": "S1D01",
        "anchor_weight": 0.5,
        "promotion_eligible": False,
    },
    {
        "candidate_id": "S1D03",
        "suffix": "d03",
        "path": "deterministic_neighborhood",
        "role": "nonpromotable_anchor_weight_neighbor",
        "method": "fixed_40pct_TQQQ_anchor_plus_60pct_monthly_QQQ_SMA200_sleeve",
        "ablation": "anchor_weight_lower_neighbor",
        "fallback": "BIL_for_tactical_sleeve_only",
        "anchor_weight": 0.4,
        "promotion_eligible": False,
    },
    {
        "candidate_id": "S1D04",
        "suffix": "d04",
        "path": "deterministic_neighborhood",
        "role": "nonpromotable_anchor_weight_neighbor",
        "method": "fixed_60pct_TQQQ_anchor_plus_40pct_monthly_QQQ_SMA200_sleeve",
        "ablation": "anchor_weight_upper_neighbor",
        "fallback": "BIL_for_tactical_sleeve_only",
        "anchor_weight": 0.6,
        "promotion_eligible": False,
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _binding(path: Path, root: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": _sha256(root / path)}


def _snapshot_item(snapshot: dict[str, Any], *, symbol: str, adjustment: str) -> dict[str, Any]:
    matches = [
        row
        for row in snapshot.get("items", [])
        if row.get("symbol") == symbol and row.get("adjustment") == adjustment
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one snapshot row for {symbol}/{adjustment}")
    return matches[0]


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _spec_path(row: dict[str, Any]) -> Path:
    return Path(f"strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_{row['suffix']}.yaml")


def _ridge_model(seed: int) -> dict[str, Any]:
    return {
        "kind": "ridge_regressor",
        "label": {
            "type": "net_incremental_policy_value",
            "horizon_bars": None,
            "horizon_mode": "next_scheduled_review_open",
            "review_schedule": "calendar_month_end",
            "maximum_horizon_bars": LABEL_MAX_SPAN_SESSIONS,
            "baseline_policy": "exact_S1D01_from_same_pretrade_state",
            "alternative_policy": "invert_S1D01_tactical_sleeve_state",
            "value_measure": "log_wealth_ratio",
            "one_way_cost_bps": PRIMARY_COST_BPS,
            "terminal_rejoin_cost_included": True,
        },
        "features": MODEL_FEATURES,
        "training": {
            "window_bars": 756,
            "retrain_every_bars": None,
            "retrain_schedule": "calendar_month_end",
            "test_window_bars": 252,
            "purge_bars": PURGE_SESSIONS,
            "embargo_bars": EMBARGO_SESSIONS,
            "seed": seed,
        },
        "selection": {
            "method": "threshold",
            "threshold": 0.0,
            "operator": "lower_bound_strictly_greater_than",
        },
        "abstention": {
            "calibration_method": "chronological_split_conformal_lower_bound",
            "calibration_fraction": 0.25,
            "minimum_fit_rows": MINIMUM_FIT_LABELS,
            "minimum_calibration_rows": MINIMUM_CALIBRATION_LABELS,
            "target_coverage": M01_TARGET_COVERAGE,
            "quantile_method": "higher",
            "fallback_candidate_id": "S1D01",
            "insufficient_data_action": "exact_target_identity_fallback",
        },
        "action": {
            "kind": "invert_tactical_sleeve",
            "apply_at": "next_regular_session_open",
            "hold_until": "next_scheduled_review_open",
        },
        "preprocessing": "standard_scaler",
        "hyperparameters": {"alpha": 8.0, "fit_intercept": True},
        "baseline": "none",
    }


def _logistic_model() -> dict[str, Any]:
    return {
        "kind": "logistic_regression_classifier",
        "label": {
            "type": "path_survival",
            "horizon_bars": None,
            "horizon_mode": "next_scheduled_review_open",
            "review_schedule": "calendar_month_end",
            "maximum_horizon_bars": LABEL_MAX_SPAN_SESSIONS,
            "max_drawdown_pct": 12.0,
            "min_terminal_return_pct": -8.0,
            "path_drawdown_reference": "running_open_peak",
        },
        "features": MODEL_FEATURES,
        "training": {
            "window_bars": 756,
            "retrain_every_bars": None,
            "retrain_schedule": "calendar_month_end",
            "test_window_bars": 252,
            "purge_bars": PURGE_SESSIONS,
            "embargo_bars": EMBARGO_SESSIONS,
            "seed": 260812,
        },
        "selection": {
            "method": "threshold",
            "threshold": 0.35,
            "operator": "less_than_or_equal",
        },
        "abstention": {
            "calibration_method": "chronological_platt_scaling",
            "calibration_fraction": 0.25,
            "minimum_fit_rows": MINIMUM_FIT_LABELS,
            "minimum_calibration_rows": MINIMUM_CALIBRATION_LABELS,
            "minimum_positive_class_rows": MINIMUM_CLASS_LABELS,
            "minimum_negative_class_rows": MINIMUM_CLASS_LABELS,
            "minimum_calibration_positive_class_rows": MINIMUM_CALIBRATION_CLASS_LABELS,
            "minimum_calibration_negative_class_rows": MINIMUM_CALIBRATION_CLASS_LABELS,
            "calibrator": {
                "kind": "logistic_regression",
                "C": 1_000_000.0,
                "penalty": "l2",
                "solver": "lbfgs",
                "max_iter": 1000,
                "use_training_seed": True,
            },
            "fallback_candidate_id": "S1D01",
            "insufficient_data_action": "exact_target_identity_fallback",
        },
        "action": {
            "kind": "shift_portfolio_weight",
            "source_symbol": "TQQQ",
            "destination_symbol": "BIL",
            "portfolio_weight_delta": 0.25,
            "apply_at": "next_regular_session_open",
            "hold_until": "next_scheduled_review_open",
        },
        "preprocessing": "standard_scaler",
        "hyperparameters": {
            "C": 0.25,
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 1000,
            "class_weight": "balanced",
        },
        "baseline": "none",
    }


def _semantic_factor(candidate_id: str) -> dict[str, Any]:
    if candidate_id not in SEMANTIC_CANDIDATE_IDS:
        raise ValueError(f"candidate does not consume semantic packets: {candidate_id}")
    packet_name = (
        "placebo-semantic-observations.jsonl"
        if candidate_id == "S1P01"
        else "semantic-observations.jsonl"
    )
    return {
        "source": "llm_feature",
        "path": (SEMANTIC_PACKET_ROOT / packet_name).as_posix(),
        "field": "direction",
        "default": 0.0,
        "params": {},
        "description": (
            "Forward-only structured Alpaca-news observation with zero capital and no "
            "order authority; a missing packet preserves the candidate's exact quant fallback."
        ),
        "input_view": "hbs_r1_alpaca_news_minimal_text_v1",
        "input_view_version": 1,
        "prompt_template_path": SEMANTIC_PROMPT_PATH.as_posix(),
        "output_schema": {
            "type": "object",
            "required": [
                "theme_id",
                "event_type",
                "impact_subjects",
                "entities",
                "relationships",
                "direction",
                "confidence",
                "novelty",
                "horizon_sessions",
                "evidence_packet_ids",
                "unknown_fields",
            ],
            "properties": {
                "theme_id": {"type": "string"},
                "event_type": {"type": "string"},
                "impact_subjects": {"type": "array"},
                "entities": {"type": "array"},
                "relationships": {"type": "array"},
                "direction": {"type": "number"},
                "confidence": {"type": "number"},
                "novelty": {"type": "number"},
                "horizon_sessions": {"type": "integer"},
                "evidence_packet_ids": {"type": "array"},
                "unknown_fields": {"type": "array"},
            },
        },
        "cache_policy": {
            "mode": "materialize_then_replay",
            "key_fields": [
                "symbol",
                "visible_at",
                "input_view_version",
                "input_hash",
                "prompt_hash",
                "model",
                "schema_version",
            ],
        },
        "model_ref": "openai_structured_factor_runtime",
    }


def _semantic_packet_contract(candidate_id: str) -> dict[str, Any]:
    factor = _semantic_factor(candidate_id)
    return {
        "schema_path": SEMANTIC_PACKET_SCHEMA_PATH.as_posix(),
        "factor_name": "semantic_direction",
        "packet_path": factor["path"],
        "required_capability": "news.alpaca",
        "mode": "forward_only_materialize_then_replay",
        "historical_packets_available": False,
        "historical_action": (
            "exact_S1D01_identity_not_placebo"
            if candidate_id == "S1P01"
            else "exact_quant_fallback_identity"
        ),
        "missing_packet_action": "exact_quant_fallback_identity",
        "semantic_stock_budget": 0.0,
        "order_authority": False,
        "broker_writes": False,
        "historical_status": (
            "dependency_skipped_no_historical_packets"
            if candidate_id == "S1P01"
            else "dependency_skipped_no_historical_packets"
        ),
        "placebo_executed": False if candidate_id == "S1P01" else None,
        "placebo_seed_used": False if candidate_id == "S1P01" else None,
        "planned_method": (
            "fixed_seed_packet_mapping_permutation" if candidate_id == "S1P01" else None
        ),
        "planned_seed": 260813 if candidate_id == "S1P01" else None,
    }


def _write_specs(root: Path) -> dict[str, Any]:
    primary_raw = yaml.safe_load((root / PRIMARY_SPEC_PATH).read_text(encoding="utf-8"))
    if not isinstance(primary_raw, dict):
        raise ValueError("primary StrategySpec must be an object")
    specs: dict[str, Any] = {}
    for row in ROLE_ROWS:
        path = _spec_path(row)
        payload = copy.deepcopy(primary_raw)
        candidate_id = row["candidate_id"]
        anchor = float(row["anchor_weight"])
        payload["name"] = f"us_high_beta_sleeve_ensemble_r1_{row['suffix']}"
        if candidate_id != "S1D01":
            payload["description"] = (
                f"Preregistered {candidate_id} role for the high-beta sleeve ensemble R1: "
                f"{row['role']}. No broker writes are authorized."
            )
        payload["portfolio"]["selected_route_label"] = (
            f"high_beta_sleeve_r1:{candidate_id}:{row['method']}"
        )
        payload["research_design"]["parameter_space"] = {
            "candidate_id": [candidate_id],
            "persistent_anchor_weight": [anchor],
            "tactical_trend_sessions": [200],
            "rebalance_schedule": ["month_end"],
            "parameter_search": [False],
        }
        payload["research_design"]["source_cards_path"] = SOURCE_CARDS_PATH.as_posix()
        source_cards = root / SOURCE_CARDS_PATH
        payload["research_design"]["source_card_claim_ids"] = (
            [card["claim_id"] for card in _read_jsonl(source_cards)]
            if source_cards.is_file()
            else list(SOURCE_CARD_CLAIM_IDS)
        )
        payload["research_design"]["candidate_budget"] = ROUND_CANDIDATE_COUNT
        payload["research_design"]["anti_overfit_notes"] = [
            "D01 is fixed at equal sleeve weights before any R1 return calculation.",
            "The 0.4 and 0.6 anchor variants are non-promotable neighborhood controls.",
            "Effective trial count starts at 8128 and includes all ten R1 candidates.",
            "Historical prices are globally exposed; no result is described as an untouched holdout.",
            "Every ML decision refits prequentially using only labels matured before the 24-session embargo.",
        ]
        payload["data_assumptions"].update(
            {
                "price_adjustment": "all",
                "historical_quality_paper_eligible": False,
                "historical_quality_is_paper_authorization": False,
            }
        )
        payload["execution_policy"]["historical_execution_contract"] = {
            "mode": "guaranteed_next_regular_open_cost_stress",
            "equivalent_to_future_order_policy": False,
            "paper_readiness_credit": False,
        }
        payload["execution_policy"]["future_order_contract"] = {
            "order_style": "opg_limit",
            "submission_cutoff_et": "09:28:00",
            "limit_reference": "prior_regular_close",
            "buy_limit_offset_bps": 20.0,
            "sell_limit_offset_bps": 20.0,
            "gap_reference": "prior_regular_close",
            "unfilled_target_policy": "retain_actual_holdings_until_next_scheduled_review",
            "partial_fill_policy": "cancel_remainder_and_reconcile_actual_weights",
            "paired_leg_policy": "no_unhedged_second_leg_after_first_leg_rejection",
            "retry_policy": "none",
            "duplicate_order_policy": "stable_signal_id",
        }
        payload["notes"].update(
            {
                "candidate_id": candidate_id,
                "candidate_role": row["role"],
                "method": row["method"],
                "fallback_candidate_id": row["fallback"],
                "promotion_eligible": row["promotion_eligible"],
                "semantic_stock_budget": 0.0,
                "order_authority": False,
                "broker_writes": False,
                "factor_library_ids": FACTOR_LIBRARY_IDS,
            }
        )
        payload["notes"]["sleeve_contract"]["persistent_anchor"]["capital_weight"] = anchor
        payload["notes"]["sleeve_contract"]["tactical_trend"]["capital_weight"] = 1.0 - anchor
        if candidate_id in SEMANTIC_CANDIDATE_IDS:
            payload["factors"]["semantic_direction"] = _semantic_factor(candidate_id)
            payload["required_capabilities"] = ["market.alpaca_bars", "news.alpaca"]
            payload["research_design"]["parameter_space"]["semantic_packet_mode"] = [
                "forward_only_zero_capital"
            ]
            payload["notes"]["semantic_packet_contract"] = _semantic_packet_contract(candidate_id)
        elif candidate_id == "S1F01":
            payload["required_capabilities"] = ["market.alpaca_bars"]
            payload["research_design"]["parameter_space"]["semantic_packet_mode"] = [
                "intentionally_missing"
            ]
            payload["notes"]["semantic_packet_contract"] = {
                "schema_path": SEMANTIC_PACKET_SCHEMA_PATH.as_posix(),
                "factor_name": None,
                "packet_path": None,
                "required_capability": None,
                "mode": "missing_modality_control",
                "historical_packets_available": False,
                "historical_action": "exact_S1M01_target_identity",
                "missing_packet_action": "exact_S1M01_target_identity_then_S1D01_on_model_abstention",
                "semantic_stock_budget": 0.0,
                "order_authority": False,
                "broker_writes": False,
            }
        if candidate_id in {"S1M01", "S1C01", "S1F01"}:
            payload["model"] = _ridge_model(260811)
        elif candidate_id == "S1M02":
            payload["model"] = _logistic_model()
        else:
            payload.pop("model", None)
        if candidate_id == "S1P01":
            payload["notes"]["historical_placebo_status"] = (
                "dependency_skipped_no_historical_packets"
            )
            payload["research_design"]["parameter_space"]["planned_placebo_seed"] = [260813]
        output_path = root / path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        specs[candidate_id] = load_strategy_spec(output_path)
    return specs


def _contracts(root: Path) -> dict[str, dict[str, Any]]:
    snapshot = _load_json(root / SNAPSHOT_PATH)
    quality = _load_json(root / QUALITY_PATH)
    if snapshot.get("request_count") != 72:
        raise ValueError("expected the 18-symbol x four-adjustment immutable SIP bundle")
    if quality.get("research_eligible") is not True:
        raise ValueError("price-adjustment quality report is not research eligible")
    if quality.get("paper_eligible") is not False:
        raise ValueError("R1 historical quality must remain explicitly non-Paper evidence")
    output_root = Path(str(snapshot.get("output_root") or ""))
    bil_all = _snapshot_item(snapshot, symbol="BIL", adjustment="all")
    bil_dividend = _snapshot_item(snapshot, symbol="BIL", adjustment="dividend")
    common = {"schema_version": 1, "iter_id": ITER_ID, "generated_before_backtest": True}
    return {
        "data-contract.json": {
            **common,
            "contract_id": "hbs_r1_data_v1",
            "provider": "alpaca",
            "feed": "sip",
            "snapshot_manifest": _binding(SNAPSHOT_PATH, root),
            "price_adjustment_quality": _binding(QUALITY_PATH, root),
            "evaluation_price_view": {
                "adjustment": "all",
                "all_equivalence_assumed": False,
                "bundle_role": snapshot.get("bundle_role"),
            },
            "symbol_lineage": {
                "BIL": {
                    "selected_adjustment": "all",
                    "selected_output_path": (output_root / bil_all["output_path"]).as_posix(),
                    "selected_output_sha256": bil_all["output_sha256"],
                    "selected_semantics": bil_all["adjustment_semantics"],
                    "dividend_cross_check_path": (
                        output_root / bil_dividend["output_path"]
                    ).as_posix(),
                    "dividend_cross_check_sha256": bil_dividend["output_sha256"],
                    "dividend_semantics": bil_dividend["adjustment_semantics"],
                }
            },
            "paper_evidence": {
                "historical_quality_paper_eligible": False,
                "historical_quality_is_paper_authorization": False,
            },
            "symbols": ["QQQ", "TQQQ", "BIL", "SPY", "SMH"],
            "session_scope": "regular",
            "decision_anchor": "completed_regular_session_close",
            "execution_anchor": "next_regular_session_open",
            "integrity": {
                "immutable_snapshot_required": True,
                "forward_fill_allowed": False,
                "zero_return_substitution_allowed": False,
                "nonfinite_action": "fail_closed",
                "silent_feed_fallback_allowed": False,
                "broker_writes": False,
            },
            "limitations": [
                "all historical prices are globally exposed development evidence",
                "provider adjustment=all is accepted only with the independent-mode quality report",
                "historical semantic packets are unavailable and receive zero capital",
            ],
        },
        "feature-contract.json": {
            **common,
            "contract_id": "hbs_r1_features_v1",
            "factor_library": _binding(FACTOR_LIBRARY_PATH, root),
            "deterministic_core": {
                "persistent_anchor": {
                    "symbol": "TQQQ",
                    "weight": 0.5,
                    "always_invested": True,
                },
                "tactical_sleeve": {
                    "weight": 0.5,
                    "signal": "completed_QQQ_close_strictly_above_SMA200",
                    "risk_on_symbol": "TQQQ",
                    "risk_off_symbol": "BIL",
                    "review": "last_completed_session_of_calendar_month",
                },
                "factor_library_id": "fixed_anchor_monthly_trend_sleeve",
                "factor_semantic_role": ("portfolio_construction_contract_not_scalar_expression"),
                "between_reviews": "hold_units_and_allow_weights_to_drift",
                "initial_action": "first_eligible_month_end_after_200_session_warmup",
            },
            "quant_features": {
                "names": MODEL_FEATURES,
                "availability": "decision_close_or_earlier",
                "fold_local_transform_fit": True,
                "full_sample_standardization": False,
                "lineage": {
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
                        "factor_library_id": None,
                    },
                    "tqqq_drawdown_63": {
                        "input_symbol": "TQQQ",
                        "formula": "close_t / max(close[t-62:t]) - 1",
                        "rolling_high_shift": 0,
                        "factor_library_id": None,
                        "lineage_note": "local state feature; drawdown_guard_20_60 is intentionally not cited because it requires a one-bar-shifted high",
                    },
                },
                "expressions": FEATURE_EXPRESSIONS,
            },
            "model_roles": {
                "S1M01": "Ridge estimate of after-cost tactical TQQQ-vs-BIL policy value",
                "S1M02": "calibrated logistic TQQQ path-survival probability through the next scheduled review open",
            },
            "semantic_features": {
                "historical_backfill": False,
                "required_capability": "news.alpaca",
                "packet_schema": _binding(SEMANTIC_PACKET_SCHEMA_PATH, root),
                "packet_paths": {
                    "observation": (
                        SEMANTIC_PACKET_ROOT / "semantic-observations.jsonl"
                    ).as_posix(),
                    "placebo": (
                        SEMANTIC_PACKET_ROOT / "placebo-semantic-observations.jsonl"
                    ).as_posix(),
                },
                "PIT_packet_required_fields": [
                    "visible_at",
                    "published_at",
                    "fetched_at",
                    "source",
                    "input_hash",
                    "prompt_hash",
                ],
                "stock_budget": 0.0,
                "order_authority": False,
                "missing_action": "exact_fallback",
                "forward_packet_status": "contract_defined_no_counted_packets",
            },
        },
        "label-contract.json": {
            **common,
            "contract_id": "hbs_r1_labels_v1",
            "timing": {
                "feature_cutoff": "month_end_completed_close",
                "label_start": "next_regular_session_open",
                "label_end": "next_scheduled_review_open",
                "review_calendar": "last_completed_session_of_calendar_month",
                "maximum_label_span_sessions": LABEL_MAX_SPAN_SESSIONS,
                "purge_sessions": PURGE_SESSIONS,
                "embargo_sessions": EMBARGO_SESSIONS,
            },
            "labels": {
                "S1M01": {
                    "type": "net_incremental_log_wealth_regression",
                    "baseline_policy": "exact_S1D01_from_same_state",
                    "alternative_policy": "invert_the_S1D01_tactical_TQQQ_or_BIL_state_until_the_next_review_open",
                    "value": "log(alternative_net_wealth/baseline_net_wealth)",
                    "one_way_cost_bps": PRIMARY_COST_BPS,
                    "terminal_rejoin_cost_included": True,
                    "start_pretrade_holdings": "same_exact_S1D01_drifted_weights",
                    "cost_method": "separately_simulate_baseline_and_alternative_start_and_rejoin_trades",
                },
                "S1M02": {
                    "type": "TQQQ_path_survival_binary",
                    "positive": "next_review_open_path_running_peak_drawdown_strictly_above_minus_12pct_and_terminal_return_strictly_above_minus_8pct",
                    "action": {
                        "source_symbol": "TQQQ",
                        "destination_symbol": "BIL",
                        "portfolio_weight_delta": 0.25,
                        "meaning": "twenty_five_percentage_points_of_total_portfolio_capital",
                        "apply_at": "next_regular_session_open",
                        "hold_until": "next_scheduled_review_open",
                    },
                    "no_action": "exact_S1D01",
                },
            },
            "calibration": {
                "split": "chronological_first_75pct_fit_last_25pct_calibration",
                "S1M01": {
                    "method": "one_sided_split_conformal",
                    "target_coverage": M01_TARGET_COVERAGE,
                    "quantile_rank": "ceil((n_calibration + 1) * target_coverage)",
                    "quantile_method": "higher",
                    "minimum_fit_labels": MINIMUM_FIT_LABELS,
                    "minimum_calibration_labels": MINIMUM_CALIBRATION_LABELS,
                },
                "S1M02": {
                    "method": "chronological_Platt_scaling",
                    "minimum_fit_labels": MINIMUM_FIT_LABELS,
                    "minimum_calibration_labels": MINIMUM_CALIBRATION_LABELS,
                    "minimum_fit_positive_and_negative_labels_each": MINIMUM_CLASS_LABELS,
                    "minimum_calibration_positive_and_negative_labels_each": MINIMUM_CALIBRATION_CLASS_LABELS,
                },
                "insufficient_action": "exact_S1D01_target_identity",
            },
            "prohibited": [
                "same_session_close_to_close_label",
                "random_train_test_split",
                "full_sample_normalization",
                "missing_return_zero_fill",
                "historical_semantic_backfill",
            ],
        },
        "validation-contract.json": {
            **common,
            "contract_id": "hbs_r1_validation_v1",
            "chronological_folds": {
                "construction": "last_1008_common_sessions_as_four_contiguous_252_session_OOS_folds",
                "count": 4,
                "oos_sessions": 252,
                "minimum_train_sessions": 756,
                "purge_sessions": PURGE_SESSIONS,
                "embargo_sessions": EMBARGO_SESSIONS,
                "model_update_mode": "prequential_month_end_refit_from_scratch",
                "prior_OOS_labels_may_enter_later_decisions_only_after_maturity_and_embargo": True,
                "random_split": False,
            },
            "family_gates": {
                "primary_cost_bps": PRIMARY_COST_BPS,
                "stress_cost_bps": STRESS_COST_BPS,
                "net_CAGR_floor_pct": 45.0,
                "matched_TQQQ_CAGR_fraction_floor": 0.85,
                "matched_QQQ_CAGR_lift_floor_pct_points": 8.0,
                "maximum_drawdown_floor_pct": -65.0,
                "Sharpe_floor": 0.8,
                "MAR_floor": 0.4,
                "TQQQ_up_capture_floor": 0.8,
                "TQQQ_down_capture_ceiling": 0.9,
                "positive_QQQ_lift_folds_min": 3,
                "DSR_probability_floor": 0.75,
                "PBO_ceiling": 0.4,
                "pbo_min_partitions": 70,
            },
            "ml_gates": {
                "exact_deterministic_fallback": True,
                "minimum_folds_beating_S1D01": 3,
                "minimum_positive_realized_policy_value_folds": 3,
                "minimum_effective_overrides": 8,
                "minimum_S1D01_upside_capture_retained": 0.95,
                "uncertainty_action": "abstain_to_exact_S1D01",
                "minimum_lower_bound_coverage_folds": 3,
                "lower_bound_fold_coverage_floor": M01_FOLD_COVERAGE_FLOOR,
                "minimum_lower_bound_observations_per_fold": 3,
                "minimum_calibrated_probability_observations_per_fold": 3,
                "minimum_calibration_improvement_folds": 3,
                "calibrated_brier_must_beat_raw": True,
                "aggregate_realized_override_value_strictly_positive": True,
                "annualized_reported_one_way_turnover_ceiling": ANNUALIZED_ONE_WAY_TURNOVER_CAP,
                "minimum_fit_labels": MINIMUM_FIT_LABELS,
                "minimum_calibration_labels": MINIMUM_CALIBRATION_LABELS,
                "minimum_logistic_fit_positive_and_negative_labels_each": MINIMUM_CLASS_LABELS,
                "minimum_logistic_calibration_positive_and_negative_labels_each": MINIMUM_CALIBRATION_CLASS_LABELS,
                "insufficient_sample_action": "exact_S1D01_target_identity",
            },
            "pbo": {
                "block_count": 8,
                "in_sample_block_count": 4,
                "block_ids": [f"B{index:02d}" for index in range(1, 9)],
                "block_construction": {
                    "algorithm": "split_ordered_common_sessions_into_contiguous_blocks",
                    "remainder_allocation": "one_extra_session_to_earliest_block_ids_in_order",
                    "maximum_size_difference": 1,
                    "no_shuffle": True,
                },
                "partition_enumeration": "all_directional_combinations",
                "evaluate_complementary_orientations": True,
                "expected_partition_count": 70,
                "minimum_valid_partition_count": 70,
                "selection_candidate_ids": ["S1D01", "S1M01", "S1M02", "S1D03", "S1D04"],
                "diagnostic_control_ids": ["S1D02", "S1L01", "S1C01", "S1F01", "S1P01"],
                "valid_partition_requirements": [
                    "all_candidate_Sharpe_values_are_defined",
                    "all_selection_candidates_have_nonempty_finite_returns_on_both_sides",
                    "exactly_four_in_sample_and_four_out_of_sample_blocks",
                    "no_session_substitution_or_overlap",
                    "candidate_id_invariant_equal_weight_in_sample_ties",
                    "candidate_id_invariant_average_oos_midranks",
                    "identical_candidate_streams_contribute_exactly_0.5",
                ],
            },
            "neighborhood_controls": {
                "S1D03_anchor_weight": 0.4,
                "S1D04_anchor_weight": 0.6,
                "promotion_eligible": False,
                "selection_after_results": False,
            },
        },
        "cost-contract.json": {
            **common,
            "contract_id": "hbs_r1_costs_v1",
            "application": "one_way_target_weight_turnover",
            "primary_bps": PRIMARY_COST_BPS,
            "stress_bps": STRESS_COST_BPS,
            "views": COST_VIEW_ROWS,
            "commission_pct": 0.0,
            "impact_model": "linear_stress_only",
            "simulated_fills_are_broker_evidence": False,
        },
        "benchmark-contract.json": {
            **common,
            "contract_id": "hbs_r1_benchmarks_v1",
            "required": BENCHMARK_FAMILY,
            "same_sessions": True,
            "same_costs": True,
            "annualized_return_definition": "geometric_CAGR",
            "ex_post_best_symbol_selectable": False,
            "single_symbol_benchmarks": BENCHMARK_SINGLE_SYMBOLS,
            "cash_proxy_symbol": BENCHMARK_CASH_PROXY_SYMBOL,
            "equal_weight_full_spec_universe": {
                "symbols": ["QQQ", "TQQQ", "BIL", "SPY", "SMH"],
                "weights": {
                    "QQQ": 0.2,
                    "TQQQ": 0.2,
                    "BIL": 0.2,
                    "SPY": 0.2,
                    "SMH": 0.2,
                },
                "construction": "initial_equal_weight_buy_and_hold",
                "same_sessions": True,
                "same_cost_views_bps": STRESS_COST_BPS,
            },
        },
        "holdout-contract.json": {
            **common,
            "contract_id": "hbs_r1_holdout_v1",
            "globally_exposed_not_pristine": True,
            "untouched_holdout_claim_authorized": False,
            "validation_mode": "locked_four_fold_chronological_OOS_plus_DSR_PBO",
            "selection_after_fold_results": False,
            "future_paper_fills_required_for_historical_research_pass": False,
            "future_paper_fills_required_for_paper_validated": True,
        },
        "cumulative-trial-contract.json": {
            **common,
            "contract_id": "hbs_r1_cumulative_trials_v1",
            "prior_effective_trial_count": PRIOR_EFFECTIVE_TRIAL_COUNT,
            "current_round_candidate_count": ROUND_CANDIDATE_COUNT,
            "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
            "reset_allowed": False,
            "all_neighbors_and_ablation_controls_counted": True,
        },
        "universe-contract.json": {
            **common,
            "contract_id": "hbs_r1_universe_v1",
            "execution_symbols": ["TQQQ", "BIL"],
            "signal_symbols": ["QQQ", "TQQQ"],
            "benchmark_only_symbols": ["SPY", "SMH"],
            "survivorship_scope": "fixed_ETF_universe_with_known_inception_dates",
            "dynamic_membership": False,
        },
        "modality-role-matrix.json": {
            **common,
            "contract_id": "hbs_r1_modality_roles_v1",
            "semantic_stock_budget": 0.0,
            "matched_ablations": [
                "quant_only_S1D01",
                "modality_only_S1L01_exact_zero_capital_fallback",
                "combined_S1C01",
                "missing_modality_S1F01",
                "placebo_S1P01",
            ],
            "roles": [
                {
                    "role": "factor_generation",
                    "candidates": ["S1D01", "S1L01"],
                    "method": "registered_quant_factors_and_PIT_structured_observation",
                    "fallback": "S1D01",
                },
                {
                    "role": "return_ranking",
                    "candidates": ["S1M01"],
                    "method": "Ridge_after_cost_policy_value",
                    "fallback": "S1D01",
                },
                {
                    "role": "risk_prediction",
                    "candidates": ["S1M02"],
                    "method": "logistic_path_survival",
                    "fallback": "S1D01",
                },
                {
                    "role": "regime_meta_gate",
                    "candidates": ["S1D01", "S1M02"],
                    "method": "QQQ_SMA200_and_tail_risk",
                    "fallback": "S1D01",
                },
                {
                    "role": "sizing",
                    "candidates": [row["candidate_id"] for row in ROLE_ROWS],
                    "method": "fixed_sleeves_with_bounded_M02_anchor_cut",
                    "fallback": "S1D01",
                },
                {
                    "role": "uncertainty",
                    "candidates": ["S1M01", "S1M02", "S1C01"],
                    "method": "calibrated_abstention_or_missing_packet",
                    "fallback": "S1D01",
                },
                {
                    "role": "deterministic_fallback",
                    "candidates": ["S1F01"],
                    "method": "exact_S1M01_without_semantic_packet_then_S1D01_on_model_uncertainty",
                    "fallback": "S1D01",
                },
            ],
        },
    }


def _write_external_brief(root: Path, specs: dict[str, Any]) -> None:
    cards = _read_jsonl(root / SOURCE_CARDS_PATH)
    sources = []
    bindings = []
    for card in cards:
        claim = str(card["claim"])
        sources.append(
            {
                "url": card["source_url"],
                "published_or_updated_at": card.get("document_published_at")
                or card.get("document_updated_at")
                or card["accessed_at"],
                "source_type": card["source_type"],
                "credibility": "primary official documentation or identified primary research source",
                "core_claim": claim,
                "project_applicability": card["impact_on_spec"],
                "reflection": card["limitations"],
                "topics": card["applies_to"],
            }
        )
        bindings.append(
            {
                "canonical_url": card["source_url"],
                "source_card_claim_id": card["claim_id"],
                "claim_fingerprint": claim_fingerprint(claim),
                "brief_claim_fingerprint": claim_fingerprint(claim),
            }
        )
    brief = {
        "schema_version": 2,
        "iter_id": ITER_ID,
        "strategy_name": specs["S1D01"].name,
        "source_spec_path": PRIMARY_SPEC_PATH.as_posix(),
        "spec_hash": strategy_content_hash(specs["S1D01"]),
        "objective": "Test an independent fixed-sleeve leveraged ETF family and matched ML overlays without reopening R22-R24 price routes.",
        "current_source_card_paths": [SOURCE_CARDS_PATH.as_posix()],
        "source_evidence_bindings": bindings,
        "sources": sources,
        "topic_coverage": [
            "daily_open_execution",
            "leveraged_ETF_path_dependency",
            "time_series_trend",
            "after_cost_ML_policy_value",
            "calibrated_abstention",
            "benchmark_overfit_DSR_PBO",
            "Paper_simulation_limitations",
        ],
        "candidate_matrix_revisions": [
            "Use a fixed 50/50 capital-sleeve primary instead of another all-or-nothing R22 route tweak.",
            "Count 40/60 anchor weights only as nonpromotable neighborhood controls.",
            "Credit ML only for after-cost fold-level policy value with exact deterministic abstention.",
            "Keep semantic and LLM capital at zero because no historical PIT modality evidence exists.",
        ],
        "hypothesis_links": ["HBS-H1", "HBS-H2", "HBS-H3"],
    }
    write_json(root / ITERATION_DIR / "external-brief.json", brief)


def _write_markdown(root: Path) -> None:
    iteration = root / ITERATION_DIR
    (iteration / "external-brief.md").write_text(
        """# External Brief: mom_high_beta_sleeve_ensemble_r1

Thirteen freshly retrieved source cards bind official Alpaca and Nasdaq execution
semantics, the ProShares daily-reset and path-dependency disclosure, five method and
cost-aware ML papers, and the primary DSR/PBO methodology identities. The sources
support testing a low-frequency fixed-sleeve trend family; none proves the local
weights, return target, execution fills, or independent ML Alpha. Paper simulation
is explicitly treated as lifecycle evidence rather than live execution evidence.

The design response is deliberately bounded: one 50/50 primary, two nonpromotable
anchor-weight neighbors, Ridge policy value, logistic tail risk, and five exact
semantic/ablation controls. All ten candidates add to the cumulative trial count.
""",
        encoding="utf-8",
    )
    (iteration / "hypotheses.md").write_text(
        """# Hypotheses: mom_high_beta_sleeve_ensemble_r1

## HBS-H1

- Hypothesis: A persistent 50% TQQQ anchor plus a monthly QQQ SMA200 tactical sleeve preserves rebound participation while shifting half the capital to BIL in prolonged downtrends.
- Failure mode: The anchor preserves too much crash exposure, or the slow tactical signal misses enough rebound that CAGR and TQQQ upside capture remain below the frozen gates.
- Measurement: Ten, twenty, and forty basis-point costs; four chronological prequential OOS folds; TQQQ/QQQ/SPY/SMH/BIL/full-universe equal-weight benchmarks; DSR and eight-block CSCV PBO.
- Stop/Pivot criterion: Stop this family if S1D01 misses any primary performance or robustness gate; do not select S1D03 or S1D04 after observing outcomes.

## HBS-H2

- Hypothesis: Prequential Ridge policy value can identify a minimum of eight monthly tactical-state inversions whose realized after-cost value is positive in at least three folds without sacrificing more than 5% of S1D01 upside capture.
- Failure mode: Sparse month-end labels, unstable coefficients, switching costs, and nonstationary rebound timing make ML worse than the deterministic rule.
- Measurement: Exact S1D01 fallback parity, override count, realized policy value, fold wins, calibration, turnover, and full family gates.
- Stop/Pivot criterion: Stop ML complexity credit unless all frozen ML gates pass; zero overrides or an identical stream is not independent Alpha.

## HBS-H3

- Hypothesis: A conservative logistic tail-risk overlay can reduce severe drawdown without permanently suppressing the persistent anchor.
- Failure mode: Rare-event labels are imbalanced, predicted tail risk arrives late, or anchor cuts destroy the required CAGR and upside capture.
- Measurement: Fold-local Brier/calibration evidence, effective cuts, drawdown change, retained upside capture, and after-cost fold value against exact S1D01.
- Stop/Pivot criterion: Stop the overlay unless it beats S1D01 in at least three folds, acts at least eight times, and clears every ML and family gate.
""",
        encoding="utf-8",
    )
    (iteration / "search-space.md").write_text(
        """# Search Space: mom_high_beta_sleeve_ensemble_r1

The round contains exactly ten preregistered candidates across eight bounded paths.
S1D01 is the only deterministic primary. S1D03 and S1D04 are 40% and 60% anchor
neighborhood diagnostics and cannot replace S1D01 after results are known. S1M01
and S1M02 use fixed model families, features, next-review-open labels, seeds, costs,
purge, embargo, calibration, and thresholds. Semantic, combined, missing-modality, and placebo roles carry zero
semantic capital and must preserve their exact fallback identities.

The primary selection objective is the complete machine-readable gate set, not the
highest observed CAGR. The effective multiple-testing count is 8,138, carrying
forward 8,128 prior trials and adding every candidate and control in this round.
""",
        encoding="utf-8",
    )
    (iteration / "decision-record.md").write_text(
        """# Decision Record: mom_high_beta_sleeve_ensemble_r1

## P1

- Path: Independent fixed-capital high-beta sleeve family with matched ML and semantic controls.
- Decision: pending until the one-shot locked evaluation is published; no candidate is currently promoted.
- Reason: Preregistration, knowledge assessment, data feasibility, and implementation lock must pass before any R1 return or trained prediction is inspected.
- Next iteration suggestion: If the family stops, retain the negative result and move to a genuinely distinct return source or portfolio construction hypothesis rather than retuning anchor weights or the SMA200 rule.
""",
        encoding="utf-8",
    )


def _write_queries(root: Path) -> None:
    cards = _read_jsonl(root / SOURCE_CARDS_PATH)
    curated = [
        {
            "discovery_id": card["claim_id"],
            "url": card["source_url"],
            "title": card["claim_id"].replace("hbs_r1_", "").replace("_", " ").title(),
            "summary": card["claim"],
            "published_at": card.get("document_published_at")
            or card.get("document_updated_at")
            or card["accessed_at"],
            "authors": [],
            "source_type": card["source_type"],
            "topics": card["applies_to"],
        }
        for card in cards
    ]
    write_json(
        root / ITERATION_DIR / "knowledge-scout-queries.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "max_results_per_query": 5,
            "queries": [],
            "curated_candidates": curated,
        },
    )


def _candidate_manifest(root: Path, specs: dict[str, Any]) -> dict[str, Any]:
    contract_ids = {
        "data": ("hbs_r1_data_v1", "data-contract.json"),
        "features": ("hbs_r1_features_v1", "feature-contract.json"),
        "labels": ("hbs_r1_labels_v1", "label-contract.json"),
        "validation": ("hbs_r1_validation_v1", "validation-contract.json"),
        "costs": ("hbs_r1_costs_v1", "cost-contract.json"),
        "benchmarks": ("hbs_r1_benchmarks_v1", "benchmark-contract.json"),
    }
    contracts = {
        group: {contract_id: _binding(ITERATION_DIR / filename, root)}
        for group, (contract_id, filename) in contract_ids.items()
    }
    candidates = []
    for row in ROLE_ROWS:
        candidates.append(
            {
                "candidate_id": row["candidate_id"],
                "path": row["path"],
                "role": row["role"],
                "method": row["method"],
                "ablation": row["ablation"],
                "spec_path": _spec_path(row).as_posix(),
                "fallback": row["fallback"],
                "promotion_eligible": row["promotion_eligible"],
                "data_contract": contract_ids["data"][0],
                "feature_contract": contract_ids["features"][0],
                "label_contract": contract_ids["labels"][0],
                "validation_contract": contract_ids["validation"][0],
                "cost_contract": contract_ids["costs"][0],
                "benchmark_contract": contract_ids["benchmarks"][0],
            }
        )
    return {
        "schema_version": 1,
        "manifest_type": "generic_candidate_family_v1",
        "iter_id": ITER_ID,
        "generated_before_backtest": True,
        "generated_before_model_training": True,
        "candidate_count": len(candidates),
        "single_new_hypothesis": "fixed_capital_sleeves_instead_of_all_or_nothing_router",
        "cumulative_effective_trial_count": EFFECTIVE_TRIAL_COUNT,
        "contracts": contracts,
        "spec_hashes": {
            _spec_path(row).as_posix(): strategy_content_hash(specs[row["candidate_id"]])
            for row in ROLE_ROWS
        },
        "candidates": candidates,
    }


def prepare(root: Path) -> None:
    base = root.resolve()
    (base / ITERATION_DIR).mkdir(parents=True, exist_ok=True)
    specs = _write_specs(base)
    write_factor_library_artifact(
        strategy_name="us_high_beta_sleeve_ensemble_r1",
        factor_ids=FACTOR_LIBRARY_IDS,
        root=base,
        stem=FACTOR_LIBRARY_STEM,
    )
    for filename, payload in _contracts(base).items():
        write_json(base / ITERATION_DIR / filename, payload)
    _write_external_brief(base, specs)
    _write_markdown(base)
    _write_queries(base)
    write_json(base / ITERATION_DIR / "candidate-manifest.json", _candidate_manifest(base, specs))


def _path_rows() -> list[dict[str, Any]]:
    rows = []
    for path_name in dict.fromkeys(row["path"] for row in ROLE_ROWS):
        selected = [row for row in ROLE_ROWS if row["path"] == path_name]
        rows.append(
            {
                "name": path_name,
                "candidate_count": len(selected),
                "hypothesis_refs": ["HBS-H1", "HBS-H2", "HBS-H3"],
                "parameters": {
                    "candidate_ids": [row["candidate_id"] for row in selected],
                    "anchor_weights": sorted({row["anchor_weight"] for row in selected}),
                    "selection_after_results": False,
                },
                "benchmark_family": BENCHMARK_FAMILY,
            }
        )
    return rows


def _write_capability_reviews(root: Path) -> None:
    packet_schema = _binding(SEMANTIC_PACKET_SCHEMA_PATH, root)
    prompt = _binding(SEMANTIC_PROMPT_PATH, root)
    for candidate_id in (*sorted(SEMANTIC_CANDIDATE_IDS), "S1F01"):
        row = next(item for item in ROLE_ROWS if item["candidate_id"] == candidate_id)
        spec = load_strategy_spec(root / _spec_path(row))
        consumes_semantic_packets = candidate_id in SEMANTIC_CANDIDATE_IDS
        factor = spec.factors.get("semantic_direction")
        if consumes_semantic_packets and factor is None:
            raise ValueError(f"{candidate_id} semantic factor is missing")
        payload = {
            "strategy_name": spec.name,
            "iter_id": ITER_ID,
            "reviewed_at": datetime.now(UTC).date().isoformat(),
            "capabilities": [
                {
                    "capability_id": "market.alpaca_bars",
                    "kind": "market",
                    "status": "ok",
                    "strict_behavior": "fail_fast_for_unsupported_timeframes",
                    "paper_ready": False,
                    "notes": (
                        "The immutable Alpaca SIP daily snapshot is eligible for this "
                        "historical research evaluation, but its historical quality report "
                        "explicitly does not authorize Paper use."
                    ),
                },
                *(
                    [
                        {
                            "capability_id": "news.alpaca",
                            "kind": "news",
                            "status": "partial",
                            "strict_behavior": "forward_only_fail_closed",
                            "paper_ready": False,
                            "notes": (
                                "The registered capability is trial and forward-only. The "
                                "fixture checks packet shape only; no fixture, retrospective "
                                "download, or cache fallback receives historical Alpha or "
                                "Paper-readiness credit."
                            ),
                        }
                    ]
                    if consumes_semantic_packets
                    else []
                ),
            ],
            "feature_packet_pit_check": (
                "schema_pass_no_counted_forward_packets"
                if consumes_semantic_packets
                else "pass_not_applicable_missing_modality_control"
            ),
            "feature_packet_evidence": {
                "schema_path": packet_schema["path"],
                "schema_sha256": packet_schema["sha256"],
                "prompt_path": prompt["path"],
                "prompt_sha256": prompt["sha256"],
                "packet_path": factor.path if factor is not None else None,
                "factor_source": factor.source if factor is not None else None,
                "factor_field": factor.field if factor is not None else None,
                "required_fields": [
                    "visible_at",
                    "published_at",
                    "fetched_at",
                    "source",
                    "input_hash",
                    "prompt_hash",
                ],
                "historical_packet_count": 0,
                "counted_forward_packet_count": 0,
                "live_call_inside_historical_evaluation": False,
            },
            "sample_data_caveats": [
                "news.alpaca fixture data validates shape only and is not research or Paper evidence",
                "retrospective news downloads and cache fallback do not establish local first-seen visibility",
                "the historical SIP snapshot is research evidence only and is not Paper authorization",
            ],
            "fallback_check": {
                "mode": (
                    "exact_zero_capital_quant_fallback_when_packet_missing"
                    if consumes_semantic_packets
                    else "exact_S1M01_target_identity_missing_modality_control"
                ),
                "semantic_stock_budget": 0.0,
                "order_authority": False,
                "broker_writes": False,
            },
            "historical_semantic_alpha_authorized": False,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "blockers": (
                [
                    "no counted forward semantic packets",
                    "news.alpaca live coverage, deduplication, revision handling, and latency are not measured",
                    "marginal lift and missing-modality robustness have no forward observation evidence",
                ]
                if consumes_semantic_packets
                else []
            ),
            "conclusion": "warning" if consumes_semantic_packets else "pass",
        }
        write_json(
            root / "reports/harness/data" / f"{spec.name}-capability-review.json",
            payload,
        )


def finalize(root: Path) -> None:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    assessment = _load_json(iteration / "knowledge-assessment.json")
    if assessment.get("status") != "ok":
        raise ValueError("knowledge assessment must pass before finalization")
    model_reuse_path = iteration / "model-reuse-decision.json"
    model_reuse = _load_json(model_reuse_path)
    model_reuse["round_decision"] = {
        "action": "fit_new_models_from_scratch_no_warm_start",
        "reason": "R24 ML produced negative or zero realized policy value; R1 changes the portfolio family, review schedule, labels, and model roles while retaining failed models only as negative memory.",
        "source_negative_iteration": "mom_pit_semantic_theme_r24",
        "warm_start": False,
        "retrain": True,
        "data_reason": "new fixed-sleeve state and current immutable SIP window",
        "feature_reason": "new monthly sleeve-specific policy value and tail survival roles",
        "validation_reason": "new locked four-fold OOS contract",
        "status_provenance_required": True,
    }
    write_json(model_reuse_path, model_reuse)
    _write_capability_reviews(base)

    manifest_path = ITERATION_DIR / "candidate-manifest.json"
    manifest = _load_json(base / manifest_path)
    reference_paths = {
        "candidate_manifest": manifest_path,
        "historical_price_snapshot": SNAPSHOT_PATH,
        "price_adjustment_quality": QUALITY_PATH,
        "factor_library": FACTOR_LIBRARY_PATH,
        "source_cards": SOURCE_CARDS_PATH,
        "capability_registry": Path("capabilities/registry.yaml"),
        "data_contract": ITERATION_DIR / "data-contract.json",
        "feature_contract": ITERATION_DIR / "feature-contract.json",
        "label_contract": ITERATION_DIR / "label-contract.json",
        "validation_contract": ITERATION_DIR / "validation-contract.json",
        "cost_contract": ITERATION_DIR / "cost-contract.json",
        "benchmark_contract": ITERATION_DIR / "benchmark-contract.json",
        "holdout_contract": ITERATION_DIR / "holdout-contract.json",
        "cumulative_trial_contract": ITERATION_DIR / "cumulative-trial-contract.json",
        "universe_contract": ITERATION_DIR / "universe-contract.json",
        "modality_role_matrix": ITERATION_DIR / "modality-role-matrix.json",
        "model_reuse_decision": ITERATION_DIR / "model-reuse-decision.json",
        "knowledge_assessment": ITERATION_DIR / "knowledge-assessment.json",
    }
    candidates = manifest["candidates"]
    path_gates: dict[str, dict[str, Any]] = {}
    for row in ROLE_ROWS:
        path_gates.setdefault(
            row["path"],
            {
                "action": "evaluate",
                "candidate_ids": [],
                "historical_evaluation_go": True,
                "scope": "matched_historical_target_or_exact_zero_capital_fallback",
            },
        )["candidate_ids"].append(row["candidate_id"])
    feasibility = {
        "schema_version": 1,
        "report_type": "high_beta_sleeve_ensemble_r1_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_before_backtest": True,
        "generated_before_model_training": True,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "historical_positive_alpha_claim_authorized": False,
        "broker_writes": False,
        "path_gates": path_gates,
        "candidate_accounting": {
            "frozen_candidate_count": len(candidates),
            "evaluation_authorized_count": len(candidates),
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": len(candidates),
            "rows": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "path": candidate["path"],
                    "action": "evaluate",
                    "reason_code": "locked_matched_historical_evaluation_or_exact_fallback_identity",
                    "candidate_binding_sha256": _canonical_hash(candidate),
                }
                for candidate in candidates
            ],
        },
        "data_scope": {
            "market": "immutable Alpaca SIP daily bundle with independent adjustment quality evidence",
            "evaluation_price_adjustment": "all",
            "historical_quality_paper_eligible": False,
            "historical_semantic_packets": False,
            "semantic_stock_budget": 0.0,
            "fallback_evaluation": "semantic roles reproduce their preregistered exact quant fallback",
            "chronological_capacity": f"at least 756 train sessions plus {PURGE_SESSIONS} purge/embargo sessions and four 252-session OOS folds",
        },
        "blockers": [
            "historical_semantic_PIT_packets_unavailable_so_llm_contribution_pass_must_remain_false",
            "paper orders and paper fills are outside this stage",
        ],
        "required_reference_names": list(reference_paths),
        "required_references": {
            name: _binding(path, base) for name, path in reference_paths.items()
        },
        "conclusion": "historical_evaluation_authorized_with_semantic_zero_capital_exact_fallbacks",
    }
    feasibility_path = ITERATION_DIR / "data-feasibility.json"
    write_json(base / feasibility_path, feasibility)

    primary = load_strategy_spec(base / PRIMARY_SPEC_PATH)
    search = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "strategy_name": primary.name,
        "source_spec_path": PRIMARY_SPEC_PATH.as_posix(),
        "spec_hash": strategy_content_hash(primary),
        "objective": "Evaluate the fixed 50/50 sleeve primary and matched overlays against every frozen performance, robustness, cost, and ML contribution gate.",
        "adaptive_selection_disclosure": "R22-R24 and all historical prices are exposed. No R1 neighbor or threshold may replace the preregistered primary after outcomes are observed.",
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "candidate_manifest_path": manifest_path.as_posix(),
        "candidate_manifest_sha256": _sha256(base / manifest_path),
        "data_feasibility_path": feasibility_path.as_posix(),
        "data_feasibility_sha256": _sha256(base / feasibility_path),
        "cost_table_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
        "cumulative_trial_count": EFFECTIVE_TRIAL_COUNT,
        "paths": _path_rows(),
        "total_candidate_budget": ROUND_CANDIDATE_COUNT,
        "trial_ledger_paths": [(ITERATION_DIR / "evaluation-run/trial-ledger.jsonl").as_posix()],
        "evaluation_report_paths": [
            (ITERATION_DIR / "evaluation-run/evaluation-report.json").as_posix()
        ],
        "knowledge_contract": {
            "assessment_path": (ITERATION_DIR / "knowledge-assessment.json").as_posix(),
            "scout_path": (ITERATION_DIR / "knowledge-scout.json").as_posix(),
            "model_reuse_decision_path": model_reuse_path.relative_to(base).as_posix(),
            "modality_role_matrix_path": (ITERATION_DIR / "modality-role-matrix.json").as_posix(),
            "required_visibility_partitions": [
                "public_literature",
                "train_only_empirical",
                "challenge_result",
                "forward_observation",
            ],
        },
        "contracts": {
            name.removesuffix("_contract"): path.as_posix()
            for name, path in reference_paths.items()
            if name.endswith("_contract")
        },
    }
    write_json(iteration / "search-space.json", search)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize(args.root)
    else:
        prepare(args.root)


if __name__ == "__main__":
    main()
