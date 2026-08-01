from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from open_composer.analytics import build_performance_metrics
from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.iteration_dossier import validate_iteration_dossier
from open_composer.research.knowledge_memory import canonical_source_url, claim_fingerprint
from open_composer.research.multiscale_low_turnover_r6 import (
    ALL_DAILY_SYMBOLS,
    CORE_SYMBOLS,
    SECTOR_SYMBOLS,
    SPY,
    R6ContractViolation,
    R6DailyFeatures,
    R6Panel,
    _daily_field,
    _intraday_anchor_frames,
    _ranked_symbols,
    _select_with_hold_band,
    build_r6_daily_features,
    load_r6_panel,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_core_satellite_r7"
STRATEGY_NAME = "us_core_satellite_momentum_r7"
FORMAL_FORWARD_START = "2026-07-20"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
R6_ITERATION_DIR = Path("reports/research/iterations/mom_multiscale_low_turnover_r6")
SPEC_PATH = Path("strategy_specs/drafts/us_core_satellite_momentum_r7.yaml")
RUNNER_PATH = Path("open_composer/research/core_satellite_r7.py")
R6_DEPENDENCY_PATH = Path("open_composer/research/multiscale_low_turnover_r6.py")
SOURCE_CARDS_PATH = Path("reports/harness/source_cards/us_core_satellite_momentum_r7.jsonl")
PANEL_MANIFEST_PATH = ITERATION_DIR / "panel-manifest.json"
CANDIDATE_MANIFEST_PATH = ITERATION_DIR / "candidate-manifest.json"
DATA_FEASIBILITY_PATH = ITERATION_DIR / "data-feasibility.json"
SEARCH_SPACE_PATH = ITERATION_DIR / "search-space.json"
UNIVERSE_MANIFEST_PATH = ITERATION_DIR / "universe-manifest.json"
Q2_EXECUTION_MAP_PATH = ITERATION_DIR / "q2-execution-map.json"
COST_CONTRACT_PATH = ITERATION_DIR / "cost-contract.json"

COST_SCENARIOS = (5.0, 10.0, 20.0)
OUTER_FOLDS = 4
REBALANCE_SESSIONS = 21
POSITION_CAP = 0.4
CORE_BUDGET = 0.4
SATELLITE_BUDGET_FULL = 0.6
SATELLITE_BUDGET_CONSERVATIVE = 0.4
TARGET_VOLATILITY = 0.12
TOP_N = 3
HOLD_RANK = 5
PERMUTATION_REPLICATES = 100
PERMUTATION_SEED = 707
SHARPE_GATE = 0.75
MAX_DRAWDOWN_GATE_PCT = -20.0
PBO_GATE = 0.25
DSR_PROBABILITY_GATE = 0.95
EXPECTED_CANDIDATE_IDS = (
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "E01",
    "E02",
    "N01",
    "N02",
)


class R7ContractViolation(R6ContractViolation):
    pass


class R7FeatureAvailabilityError(R7ContractViolation):
    pass


@dataclass(frozen=True)
class R7Targets:
    weights: pd.DataFrame
    decision_mask: pd.Series


@dataclass(frozen=True)
class R7Simulation:
    gross_returns: pd.Series
    rebalance_turnover: pd.Series
    weights: pd.DataFrame
    terminal_turnover: float
    terminal_session: date
    rebalance_sessions: tuple[date, ...]


@dataclass(frozen=True)
class R7DiagnosticResult:
    evaluation_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def preregister_r7(root: Path | None = None) -> dict[str, Any]:
    base = root or project_root()
    output = ensure_dir(base / ITERATION_DIR)
    spec = load_strategy_spec(base / SPEC_PATH)
    spec_hash = strategy_content_hash(spec)
    cards = _load_source_cards(base / SOURCE_CARDS_PATH)
    if len(cards) < 8:
        raise R7ContractViolation("R7 requires at least eight verified source cards")

    r6_panel = _load_json(base / R6_ITERATION_DIR / "panel-manifest.json")
    _verify_source_panel_files(base, r6_panel)
    panel = copy.deepcopy(r6_panel)
    panel.update(
        {
            "report_type": "core_satellite_r7_panel_manifest",
            "panel_id": "alpaca_iex_adjusted_all_r7_bound_20260717",
            "iter_id": ITER_ID,
            "generated_at": datetime.now(UTC).isoformat(),
            "formal_forward_start": FORMAL_FORWARD_START,
            "formal_forward_daily_observation_count": 0,
            "formal_forward_intraday_observation_count": 0,
            "generator": {
                "path": str(RUNNER_PATH),
                "sha256": _sha256_file(base / RUNNER_PATH),
                "data_feature_dependency_path": str(R6_DEPENDENCY_PATH),
                "data_feature_dependency_sha256": _sha256_file(base / R6_DEPENDENCY_PATH),
                "source_panel_path": str(R6_ITERATION_DIR / "panel-manifest.json"),
                "source_panel_sha256": _sha256_file(
                    base / R6_ITERATION_DIR / "panel-manifest.json"
                ),
            },
        }
    )
    write_json(base / PANEL_MANIFEST_PATH, panel)

    universe = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "scope": "fixed_current_sector_etf_universe_diagnostic",
        "selection_rule": "fixed_SPY_11_SPDR_sector_ETFs_QQQ_and_BIL_preregistered",
        "all_symbols": list(ALL_DAILY_SYMBOLS),
        "core_symbols": list(CORE_SYMBOLS),
        "benchmark_symbols": ["QQQ", "BIL"],
        "point_in_time_membership_claimed": False,
        "survivorship_labelled": True,
        "delisted_instruments_included": False,
        "promotion_authority": False,
    }
    write_json(base / UNIVERSE_MANIFEST_PATH, universe)

    cost_contract = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "model": "self_financing_drift_aware_turnover_cost_v1",
        "one_way_cost_bps": list(COST_SCENARIOS),
        "turnover_formula": "sum_absolute_target_asset_weight_minus_pretrade_drifted_asset_weight",
        "cost_formula": "equity_times_turnover_times_one_way_cost_bps_div_10000",
        "cost_application": "multiplicative_at_each_rebalance_and_terminal_liquidation",
        "cash_change_not_double_counted": True,
        "entry_exit_costed_separately_over_lifecycle": True,
        "holdings_drift_between_rebalances": True,
        "dividends_and_splits": "Alpaca Adjustment.ALL snapshot",
        "borrow_cost": "not_applicable_long_only",
        "taxes": "excluded",
        "capacity_model": "blocked_pending_consolidated_ADV_and_matched_paper_TCA",
        "promotion_cost_gate_bps": 10.0,
        "severe_stress_cost_gate_bps": 20.0,
        "paper_ready": False,
    }
    write_json(base / COST_CONTRACT_PATH, cost_contract)

    manifest = _candidate_manifest(spec_hash)
    write_json(base / CANDIDATE_MANIFEST_PATH, manifest)
    execution_map = _q2_execution_map(manifest)
    write_json(base / Q2_EXECUTION_MAP_PATH, execution_map)
    feasibility = _data_feasibility(base, manifest, panel)
    write_json(base / DATA_FEASIBILITY_PATH, feasibility)
    search_space = _search_space(base, spec_hash)
    write_json(base / SEARCH_SPACE_PATH, search_space)

    _write_r7_dossier_documents(base, spec_hash, cards)
    _write_r7_knowledge_contracts(base)
    return {
        "iteration_dir": str(output),
        "candidate_manifest_sha256": _sha256_file(base / CANDIDATE_MANIFEST_PATH),
        "data_feasibility_sha256": _sha256_file(base / DATA_FEASIBILITY_PATH),
        "panel_manifest_sha256": _sha256_file(base / PANEL_MANIFEST_PATH),
        "spec_hash": spec_hash,
    }


def _candidate_manifest(spec_hash: str) -> dict[str, Any]:
    contracts = {
        "data": {
            "daily_adjusted_iex_r7_v1": {
                "provider": "alpaca",
                "feed": "iex",
                "adjustment": "all",
                "primitive_fields": ["open", "close", "volume"],
                "strict_common_sessions": True,
                "forward_fill": False,
                "zero_return_substitution": False,
            },
            "intraday_adjusted_iex_r7_v1": {
                "timeframe_minutes": 30,
                "complete_session_intersection": True,
                "primitive_fields": ["open", "close", "volume"],
                "forward_fill": False,
            },
            "event_packets_forward_only_r7_v1": {
                "historical_packets_available": False,
                "fixture_substitution": False,
                "retrospective_generation": False,
            },
        },
        "features": {
            "spy_trend_core_r7_v1": {
                "fields": ["spy_close_above_ma126", "spy_momentum_126"],
                "lag": "complete_close_before_next_open",
            },
            "residual_persistency_satellite_r7_v1": {
                "fields": [
                    "rolling_spy_beta_126",
                    "residual_momentum_63",
                    "residual_momentum_126_skip21",
                    "six_block_trend_consistency",
                    "realized_volatility_21",
                    "sector_breadth_126",
                ],
                "rank_tie_break": "symbol_ascending",
            },
            "matched_first_hour_r7_v1": {
                "fields": [
                    "first_hour_SPY_return",
                    "first_hour_sector_relative_return",
                    "first_hour_positive_sector_breadth",
                ],
                "decision_time_et": "10:30",
                "parent_execution_mask_required": True,
            },
            "event_packet_r7_v1": {
                "required_fields": [
                    "published_at",
                    "fetched_at",
                    "visible_at",
                    "decision_at",
                    "source",
                    "symbol",
                    "input_hash",
                    "prompt_hash",
                    "dedupe_key",
                    "evidence_spans",
                ],
                "availability": "visible_at_strictly_before_decision_at",
            },
            "permutation_control_r7_v1": {
                "replicates": PERMUTATION_REPLICATES,
                "seed": PERMUTATION_SEED,
                "scope": "within_each_decision_cross_section",
            },
            "future_availability_control_r7_v1": {
                "test_path": "same_event_packet_validator_used_by_event_candidates",
                "mandatory_outcome": "rejected_control",
            },
        },
        "labels": {
            "next_open_persistent_holdings_r7_v1": {
                "signal": "complete_close_t",
                "entry": "open_t_plus_1",
                "holdings": "self_financing_and_drift_between_scheduled_rebalances",
                "terminal_liquidation": "final_strict_common_open",
            },
            "matched_1030_to_next_open_r7_v1": {
                "parent_entry": "09:30_ET_open_on_exact_parent_mask",
                "overlay_entry": "10:30_ET_open_on_exact_same_parent_mask",
                "comparison": "identical_sessions_and_target_source",
            },
            "none_control_r7_v1": {"horizon_sessions": 0},
        },
        "validation": {
            "chronological_outer4_r7_v1": {
                "outer_folds": OUTER_FOLDS,
                "chronological": True,
                "shared_windows": True,
                "rebalance_schedule_anchor": "first_strict_common_all_feature_finite_session",
                "minimum_positive_net_folds": 3,
                "fold_metric_cost_bps": 10.0,
                "candidate_sharpe_minimum": SHARPE_GATE,
                "maximum_drawdown_floor_pct": MAX_DRAWDOWN_GATE_PCT,
                "benchmark_sharpe_tolerance": 0.0,
                "pbo_proxy_maximum": PBO_GATE,
                "dsr_probability_minimum": DSR_PROBABILITY_GATE,
                "all_thresholds_preregistered": True,
                "selection_policy": "highest_10bps_sharpe_then_candidate_id_ascending",
            },
            "intraday_matched_shadow_r7_v1": {
                "outer_folds": OUTER_FOLDS,
                "promotion_authority": False,
                "exact_parent_schedule_required": True,
                "same_window_parent_benchmark_required": True,
            },
            "dependency_skip_r7_v1": {"required_outcome_when_packet_missing": "skipped_dependency"},
            "negative_control_r7_v1": {
                "permutation_parent_must_exceed_percentile": 0.95,
                "future_packet_mandatory_outcome": "rejected_control",
            },
        },
        "costs": {
            "self_financing_cost_r7_v1": {
                "one_way_bps": list(COST_SCENARIOS),
                "drift_aware_pretrade_weights": True,
                "terminal_liquidation": True,
            }
        },
        "benchmarks": {
            "full_family_r7_v1": [
                "SPY_buy_and_hold",
                "QQQ_buy_and_hold",
                "equal_weight_sector_buy_and_hold",
                "BIL_cash_proxy",
                "uninvested_cash",
                "ex_post_best_symbol_report_only",
                "D04_same_intraday_window",
            ]
        },
    }

    common = {
        "spec_path": str(SPEC_PATH),
        "data_contract": "daily_adjusted_iex_r7_v1",
        "label_contract": "next_open_persistent_holdings_r7_v1",
        "validation_contract": "chronological_outer4_r7_v1",
        "cost_contract": "self_financing_cost_r7_v1",
        "benchmark_contract": "full_family_r7_v1",
        "rebalance_sessions": REBALANCE_SESSIONS,
        "max_symbol_weight": POSITION_CAP,
        "position_cap_semantics": "rebalance_target_only_natural_drift_allowed",
        "continuous_cap_enforcement": False,
        "max_gross_exposure": 1.0,
        "cash_remainder": True,
    }
    candidates = [
        {
            **common,
            "candidate_id": "D01",
            "path": "daily_core",
            "role": "regime_meta_gating",
            "method": "capped_SPY_dual_trend_core",
            "ablation": "market_trend_core_only",
            "feature_contract": "spy_trend_core_r7_v1",
            "fallback": "cash",
            "formula": "SPY_weight_0.4_if_close_above_MA126_and_momentum126_positive_else_cash",
        },
        {
            **common,
            "candidate_id": "D02",
            "path": "daily_core",
            "role": "return_ranking",
            "method": "capped_residual_sector_satellite",
            "ablation": "satellite_only",
            "feature_contract": "residual_persistency_satellite_r7_v1",
            "fallback": "cash",
            "top_n": TOP_N,
            "hold_rank": HOLD_RANK,
            "satellite_budget": SATELLITE_BUDGET_FULL,
            "satellite_symbol_cap": 0.2,
            "formula": (
                "top3_residual_persistency_equal_0.2_each_with_rank5_hold_band_and_cash_remainder"
            ),
        },
        {
            **common,
            "candidate_id": "D03",
            "path": "daily_core",
            "role": "sizing",
            "method": "fixed_40_60_core_satellite",
            "ablation": "fixed_core_satellite_combination",
            "feature_contract": "residual_persistency_satellite_r7_v1",
            "fallback": "D01",
            "parents": ["D01", "D02"],
            "core_budget": CORE_BUDGET,
            "satellite_budget": SATELLITE_BUDGET_FULL,
            "satellite_symbol_cap": 0.2,
            "formula": "D01_plus_D02_with_identical_decision_mask_and_no_weight_redistribution",
        },
        {
            **common,
            "candidate_id": "D04",
            "path": "daily_core",
            "role": "risk_prediction",
            "method": "volatility_scaled_40_60_core_satellite",
            "ablation": "satellite_volatility_scaling",
            "feature_contract": "residual_persistency_satellite_r7_v1",
            "fallback": "D03",
            "parents": ["D01", "D02"],
            "core_budget": CORE_BUDGET,
            "satellite_budget": SATELLITE_BUDGET_FULL,
            "satellite_symbol_cap": 0.3,
            "target_volatility": TARGET_VOLATILITY,
            "formula": (
                "D01_plus_inverse_vol_D02_scaled_to_min_0.6_and_0.12_target_"
                "with_0.3_sector_cap_no_redistribution"
            ),
        },
        {
            **common,
            "candidate_id": "D05",
            "path": "daily_core",
            "role": "regime_meta_gating",
            "method": "regime_capped_40_40_core_satellite",
            "ablation": "conservative_satellite_regime_cap",
            "feature_contract": "residual_persistency_satellite_r7_v1",
            "fallback": "D01",
            "parents": ["D01", "D04"],
            "core_budget": CORE_BUDGET,
            "satellite_budget": SATELLITE_BUDGET_CONSERVATIVE,
            "satellite_symbol_cap": 0.2,
            "formula": (
                "D01_plus_inverse_vol_satellite_capped_at_0.4_only_when_SPY_"
                "above_MA126_and_breadth_at_least_0.45"
            ),
        },
        {
            **common,
            "candidate_id": "D06",
            "path": "intraday_overlay",
            "role": "sizing",
            "method": "D04_matched_first_hour_execution_shadow",
            "ablation": "execution_time_only",
            "data_contract": "intraday_adjusted_iex_r7_v1",
            "feature_contract": "matched_first_hour_r7_v1",
            "label_contract": "matched_1030_to_next_open_r7_v1",
            "validation_contract": "intraday_matched_shadow_r7_v1",
            "fallback": "D04",
            "parents": ["D04"],
            "selection_prohibited": True,
            "formula": (
                "apply_D04_sells_and_filtered_new_buys_at_10:30_on_exact_D04_execution_dates_only"
            ),
        },
        {
            **common,
            "candidate_id": "E01",
            "path": "event_llm",
            "role": "factor_generation",
            "method": "SEC_filing_delta_overlay_forward_only",
            "ablation": "filing_only",
            "data_contract": "event_packets_forward_only_r7_v1",
            "feature_contract": "event_packet_r7_v1",
            "validation_contract": "dependency_skip_r7_v1",
            "fallback": "D05",
            "parents": ["D05"],
            "selection_prohibited": True,
        },
        {
            **common,
            "candidate_id": "E02",
            "path": "event_llm",
            "role": "factor_generation",
            "method": "news_earnings_call_overlay_forward_only",
            "ablation": "news_earnings_call_only",
            "data_contract": "event_packets_forward_only_r7_v1",
            "feature_contract": "event_packet_r7_v1",
            "validation_contract": "dependency_skip_r7_v1",
            "fallback": "D05",
            "parents": ["D05"],
            "selection_prohibited": True,
        },
        {
            **common,
            "candidate_id": "N01",
            "path": "negative_controls",
            "role": "uncertainty",
            "method": "within_date_permutation_distribution",
            "ablation": "quant_score_placebo_distribution",
            "feature_contract": "permutation_control_r7_v1",
            "label_contract": "none_control_r7_v1",
            "validation_contract": "negative_control_r7_v1",
            "fallback": "reject_control_if_parent_not_above_p95",
            "parents": ["D02"],
            "permutation_selection_metric": "10bps_annualized_sharpe",
            "selection_prohibited": True,
        },
        {
            **common,
            "candidate_id": "N02",
            "path": "negative_controls",
            "role": "uncertainty",
            "method": "end_to_end_future_packet_rejection",
            "ablation": "future_information_availability",
            "feature_contract": "future_availability_control_r7_v1",
            "label_contract": "none_control_r7_v1",
            "validation_contract": "negative_control_r7_v1",
            "fallback": "reject_control",
            "selection_prohibited": True,
        },
    ]
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "generated_before_backtest": True,
        "candidate_count": len(candidates),
        "spec_hashes": {str(SPEC_PATH): spec_hash},
        "panel_manifest_path": str(PANEL_MANIFEST_PATH),
        "data_feasibility_path": str(DATA_FEASIBILITY_PATH),
        "cost_contract_path": str(COST_CONTRACT_PATH),
        "contracts": contracts,
        "candidates": candidates,
    }


def _q2_execution_map(manifest: dict[str, Any]) -> dict[str, Any]:
    required_benchmarks = [
        "SPY_buy_and_hold",
        "QQQ_buy_and_hold",
        "equal_weight_sector_buy_and_hold",
        "BIL_cash_proxy",
        "uninvested_cash",
        "ex_post_best_symbol_report_only",
    ]
    rows = []
    for candidate in manifest["candidates"]:
        if candidate["path"] == "event_llm":
            continue
        benchmarks = list(required_benchmarks)
        if candidate["candidate_id"] == "D06":
            benchmarks.append("D04_same_intraday_window")
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_binding_sha256": _canonical_sha(candidate),
                "path": candidate["path"],
                "method": candidate["method"],
                "primitive_fields": ["open", "close", "volume"],
                "required_benchmarks": benchmarks,
                "research_pass": False,
                "promotion_eligible": False,
                "paper_ready_pass": False,
            }
        )
    return {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "scope": "historical_current_universe_diagnostic",
        "survivorship_labelled": True,
        "primitive_field_allowlist": ["open", "close", "volume"],
        "high_low_dependent_candidates_allowed": False,
        "forward_fill_allowed": False,
        "zero_return_substitution_allowed": False,
        "runnable_candidate_count": len(rows),
        "rows": rows,
    }


def _data_feasibility(
    root: Path,
    manifest: dict[str, Any],
    panel: dict[str, Any],
) -> dict[str, Any]:
    panel_hash = _sha256_file(root / PANEL_MANIFEST_PATH)
    universe_hash = _sha256_file(root / UNIVERSE_MANIFEST_PATH)
    cost_hash = _sha256_file(root / COST_CONTRACT_PATH)
    execution_hash = _sha256_file(root / Q2_EXECUTION_MAP_PATH)
    manifest_hash = _sha256_file(root / CANDIDATE_MANIFEST_PATH)
    path_gates = {
        "daily_core": {
            "candidate_ids": ["D01", "D02", "D03", "D04", "D05"],
            "historical_diagnostic_go": True,
            "historical_research_qualified": False,
            "q2_action": "run_diagnostic",
            "reason_code": "strict_live_adjusted_daily_panel_complete",
        },
        "intraday_overlay": {
            "candidate_ids": ["D06"],
            "historical_diagnostic_go": True,
            "historical_research_qualified": False,
            "q2_action": "run_diagnostic",
            "reason_code": "strict_complete_intraday_panel_shadow_only",
        },
        "event_llm": {
            "candidate_ids": ["E01", "E02"],
            "historical_diagnostic_go": False,
            "historical_research_qualified": False,
            "q2_action": "dependency_skipped",
            "reason_code": "real_historical_PIT_event_packets_missing",
        },
        "negative_controls": {
            "candidate_ids": ["N01", "N02"],
            "historical_diagnostic_go": True,
            "historical_research_qualified": False,
            "q2_action": "run_diagnostic",
            "reason_code": "mandatory_negative_control_path",
        },
    }
    authorization_rows = []
    for candidate in manifest["candidates"]:
        gate = path_gates[candidate["path"]]
        authorization_rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_binding_sha256": _canonical_sha(candidate),
                "path": candidate["path"],
                "action": gate["q2_action"],
                "reason_code": gate["reason_code"],
                "evidence_path": str(PANEL_MANIFEST_PATH),
                "evidence_sha256": panel_hash,
            }
        )
    runnable_count = sum(row["action"] == "run_diagnostic" for row in authorization_rows)
    skipped_count = len(authorization_rows) - runnable_count
    return {
        "schema_version": 1,
        "report_type": "core_satellite_r7_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "fixed_sector_etf_IEX_adjusted_diagnostic",
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "q2_diagnostic_execution_authorized": True,
        "formal_forward_start": FORMAL_FORWARD_START,
        "formal_forward_daily_observation_count": 0,
        "formal_forward_intraday_observation_count": 0,
        "candidate_accounting": {
            "frozen_candidate_count": len(authorization_rows),
            "diagnostic_runnable_count": runnable_count,
            "dependency_skipped_count": skipped_count,
            "unresolved_count": 0,
            "balanced": runnable_count + skipped_count == len(authorization_rows),
        },
        "candidate_manifest": {
            "path": str(CANDIDATE_MANIFEST_PATH),
            "sha256": manifest_hash,
        },
        "parent_universe": {
            "path": str(UNIVERSE_MANIFEST_PATH),
            "sha256": universe_hash,
        },
        "daily_panel": {"path": str(PANEL_MANIFEST_PATH), "sha256": panel_hash},
        "intraday_panel": {"path": str(PANEL_MANIFEST_PATH), "sha256": panel_hash},
        "panel_manifest": {"path": str(PANEL_MANIFEST_PATH), "sha256": panel_hash},
        "cost_contract": {"path": str(COST_CONTRACT_PATH), "sha256": cost_hash},
        "q2_execution_map": {
            "path": str(Q2_EXECUTION_MAP_PATH),
            "sha256": execution_hash,
        },
        "path_gates": path_gates,
        "q2_authorization": {
            "candidate_count": len(authorization_rows),
            "rows": authorization_rows,
        },
        "data_quality": {
            "adjustment": panel["adjustment"],
            "fallback_used": panel["fallback_used"],
            "forward_fill_allowed": panel["forward_fill_allowed"],
            "zero_return_substitution_allowed": panel["zero_return_substitution_allowed"],
            "daily_strict_common_session_count": panel["daily"]["strict_common_session_count"],
            "daily_last_session": panel["daily"]["strict_common_last_session"],
            "intraday_strict_common_session_count": panel["intraday"][
                "strict_common_complete_session_count"
            ],
            "intraday_last_session": panel["intraday"]["strict_common_last_session"],
        },
        "paper_data_qualified": False,
        "paper_data_blockers": [
            "alpaca_basic_IEX_is_not_consolidated_SIP",
            "official_open_close_and_matched_execution_parity_missing",
            "formal_forward_observations_missing",
        ],
    }


def _search_space(root: Path, spec_hash: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "source_spec_path": str(SPEC_PATH),
        "spec_hash": spec_hash,
        "total_candidate_budget": len(EXPECTED_CANDIDATE_IDS),
        "paths": [
            {
                "name": "daily_core",
                "candidate_count": 5,
                "hypothesis_refs": ["H1", "H2", "H3", "H4"],
                "parameters": {
                    "candidate_ids": ["D01", "D02", "D03", "D04", "D05"],
                    "rebalance_sessions": [REBALANCE_SESSIONS],
                    "top_n": [TOP_N],
                    "hold_rank": [HOLD_RANK],
                    "core_budget": [CORE_BUDGET],
                    "satellite_budget": [
                        SATELLITE_BUDGET_CONSERVATIVE,
                        SATELLITE_BUDGET_FULL,
                    ],
                    "target_volatility": [TARGET_VOLATILITY],
                    "one_way_cost_bps": list(COST_SCENARIOS),
                    "outer_folds": [OUTER_FOLDS],
                    "DSR_probability_gate": [DSR_PROBABILITY_GATE],
                    "PBO_proxy_gate": [PBO_GATE],
                },
                "benchmark_family": [
                    "SPY_buy_and_hold",
                    "QQQ_buy_and_hold",
                    "equal_weight_sector_buy_and_hold",
                    "BIL_cash_proxy",
                    "uninvested_cash",
                    "ex_post_best_symbol_report_only",
                ],
            },
            {
                "name": "intraday_overlay",
                "candidate_count": 1,
                "hypothesis_refs": ["H5"],
                "parameters": {
                    "candidate_ids": ["D06"],
                    "timeframe_minutes": [30],
                    "decision_time_et": ["10:30"],
                    "parent_candidate": ["D04"],
                    "exact_parent_mask_required": [True],
                    "promotion_authority": [False],
                },
                "benchmark_family": [
                    "D04_same_intraday_window",
                    "SPY_buy_and_hold",
                    "uninvested_cash",
                ],
            },
            {
                "name": "event_llm",
                "candidate_count": 2,
                "hypothesis_refs": ["H6"],
                "parameters": {
                    "candidate_ids": ["E01", "E02"],
                    "required_packet_visibility": ["visible_at_strictly_before_decision_at"],
                    "missing_packet_action": ["dependency_skipped"],
                    "historical_fixture_substitution": [False],
                    "retrospective_llm_generation": [False],
                },
                "benchmark_family": [
                    "D05_quant_only",
                    "missing_modality_exact_quant_fallback",
                    "uninvested_cash",
                ],
            },
            {
                "name": "negative_controls",
                "candidate_count": 2,
                "hypothesis_refs": ["H7"],
                "parameters": {
                    "candidate_ids": ["N01", "N02"],
                    "permutation_replicates": [PERMUTATION_REPLICATES],
                    "permutation_seed": [PERMUTATION_SEED],
                    "parent_must_exceed_percentile": [0.95],
                    "future_packet_required_outcome": ["rejected_control"],
                    "selection_prohibited": [True],
                },
                "benchmark_family": ["D02_deterministic_parent", "uninvested_cash"],
            },
        ],
        "trial_ledger_paths": [str(ITERATION_DIR / "trial-ledger.jsonl")],
        "evaluation_report_paths": [str(ITERATION_DIR / "evaluation-report.json")],
        "cost_table_path": str(COST_CONTRACT_PATH),
        "data_feasibility_path": str(DATA_FEASIBILITY_PATH),
        "data_feasibility_sha256": _sha256_file(root / DATA_FEASIBILITY_PATH),
        "candidate_manifest_path": str(CANDIDATE_MANIFEST_PATH),
        "candidate_manifest_sha256": _sha256_file(root / CANDIDATE_MANIFEST_PATH),
        "knowledge_contract": {
            "assessment_path": str(ITERATION_DIR / "knowledge-assessment.json"),
            "scout_path": str(ITERATION_DIR / "knowledge-scout.json"),
            "model_reuse_decision_path": str(ITERATION_DIR / "model-reuse-decision.json"),
            "modality_role_matrix_path": str(ITERATION_DIR / "modality-role-matrix.json"),
            "required_visibility_partitions": [
                "public_literature",
                "train_only_empirical",
                "challenge_result",
                "forward_observation",
            ],
        },
        "preregistration": {
            "generated_before_backtest": True,
            "manifest_is_required_by_runner": True,
            "no_post_result_candidate_edits": True,
            "result_based_parameter_changes_forbidden": True,
            "R6_metrics_not_used_as_R7_performance": True,
        },
    }


def _write_r7_dossier_documents(
    root: Path,
    spec_hash: str,
    cards: list[dict[str, Any]],
) -> None:
    sources = []
    bindings = []
    seen_urls: set[str] = set()
    for card in cards:
        source_url = str(card["source_url"])
        source_type = str(card["source_type"])
        canonical = canonical_source_url(source_url)
        if canonical in seen_urls:
            continue
        seen_urls.add(canonical)
        sources.append(
            {
                "url": source_url,
                "published_or_updated_at": str(card.get("accessed_at") or "2026-07-19"),
                "source_type": source_type,
                "credibility": _source_credibility(source_type),
                "core_claim": str(card["claim"]),
                "project_applicability": str(card["impact_on_spec"]),
                "reflection": str(card["limitations"]),
            }
        )
        bindings.append(
            {
                "canonical_url": canonical,
                "source_card_claim_id": str(card["claim_id"]),
                "claim_fingerprint": claim_fingerprint(str(card["claim"])),
                "brief_claim_fingerprint": claim_fingerprint(str(card["claim"])),
            }
        )
    brief = {
        "schema_version": 2,
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "source_spec_path": str(SPEC_PATH),
        "spec_hash": spec_hash,
        "objective": (
            "Correct R6 portfolio and schedule accounting, then test a bounded capped "
            "SPY trend core and residual persistent sector satellite family."
        ),
        "current_source_card_paths": [str(SOURCE_CARDS_PATH)],
        "source_evidence_bindings": bindings,
        "topic_coverage": [
            "industry and sector momentum",
            "residual momentum",
            "trend persistency",
            "time-series momentum",
            "momentum crash and volatility management",
            "turnover hold bands",
            "PBO and DSR",
            "IEX versus SIP data",
            "opening-auction and paper execution",
            "SEC point-in-time collection",
            "news and conference-call provenance",
            "transaction-cost analysis",
        ],
        "candidate_matrix_revisions": [
            (
                "Replace R6 constant-target returns with self-financing drift-aware "
                "holdings and terminal liquidation."
            ),
            (
                "Enforce the 0.40 symbol cap during target construction and leave every "
                "residual allocation in cash."
            ),
            "Use one common 21-session decision mask for all selectable candidates.",
            (
                "Require D06 to reuse D04's exact execution mask and include a matched "
                "D04 same-window benchmark."
            ),
            "Freeze 0.95 DSR and 0.25 PBO-proxy thresholds before diagnostics.",
            (
                "Use 100 within-date score permutations and an end-to-end event packet "
                "availability rejection."
            ),
            (
                "Dependency-skip filing, news, earnings, and call candidates until real "
                "PIT packets exist."
            ),
            "Do not train or reuse a return model in R7 after prior lockbox and placebo failures.",
        ],
        "sources": sources,
    }
    write_json(root / ITERATION_DIR / "external-brief.json", brief)
    (root / ITERATION_DIR / "external-brief.md").write_text(
        "# R7 External Research Brief\n\n"
        "R7 uses fresh primary-source cards for residual and sector momentum, risk "
        "management, turnover control, PBO/DSR, Alpaca IEX and paper limitations, "
        "opening-auction constraints, and PIT event provenance. Literature motivates "
        "bounded hypotheses only; it does not establish local alpha or paper readiness.\n\n"
        "The implementation response to R6 is fixed before diagnostics: self-financing "
        "holdings, hard position caps, cash residuals, one common schedule, an exact "
        "intraday parent mask, a matched parent benchmark, and preregistered statistical "
        "thresholds. Event and LLM candidates remain dependency-skipped without real "
        "point-in-time packets.\n",
        encoding="utf-8",
    )
    (root / ITERATION_DIR / "hypotheses.md").write_text(
        "# R7 Hypotheses\n\n"
        "## Hypothesis H1\n"
        "A 40 percent SPY dual-trend core may retain benchmark-comparable Sharpe while "
        "reducing drawdown. Failure mode: capped exposure produces no positive net edge. "
        "Measurement: 10 and 20 bps returns, Sharpe, drawdown, and four folds. "
        "Stop/Pivot criterion: stop if the fixed historical gate fails.\n\n"
        "## Hypothesis H2\n"
        "A residual and persistent sector satellite may add independent risk-adjusted "
        "return. Failure mode: sector rotation is weak, concentrated, or cost-sensitive. "
        "Measurement: D02 versus D01 and passive sector benchmarks. Stop/Pivot criterion: "
        "stop the satellite if it fails costs, folds, or permutation rejection.\n\n"
        "## Hypothesis H3\n"
        "A fixed 40/60 core-satellite combination may diversify the two sleeves. Failure "
        "mode: correlated momentum exposure merely increases drawdown. Measurement: D03 "
        "versus both parents. Stop/Pivot criterion: stop if no risk-adjusted incremental lift.\n\n"
        "## Hypothesis H4\n"
        "Fixed volatility and breadth controls may reduce crash exposure without erasing "
        "net return. Failure mode: de-risking arrives late or over-trades. Measurement: D04 "
        "and D05 versus D03. Stop/Pivot criterion: stop if Sharpe or folds deteriorate.\n\n"
        "## Hypothesis H5\n"
        "A 10:30 buy filter may improve execution only on the exact D04 schedule. Failure "
        "mode: first-hour delay loses returns or schedule parity fails. Measurement: D06 "
        "versus D04_same_intraday_window. Stop/Pivot criterion: reject automatically on "
        "any schedule or session mismatch.\n\n"
        "## Hypothesis H6\n"
        "Future real PIT filing, news, earnings, and call packets may add bounded risk or "
        "catalyst information. Failure mode: missing provenance, coverage, rights, or lift. "
        "Measurement: matched modality ablations after packet availability. Stop/Pivot "
        "criterion: dependency-skip while historical packets are absent.\n\n"
        "## Hypothesis H7\n"
        "The deterministic satellite should exceed a within-date permutation distribution, "
        "and future-dated packets must be rejected by the production validator. Failure mode: "
        "placebo lift or availability acceptance. Measurement: 100 permutations and one "
        "malicious future packet. Stop/Pivot criterion: block the family on either failure.\n",
        encoding="utf-8",
    )
    (root / ITERATION_DIR / "search-space.md").write_text(
        "# R7 Search Space\n\n"
        "The iteration contains exactly ten preregistered candidates: five selectable "
        "monthly daily candidates, one selection-prohibited matched intraday shadow, two "
        "dependency-skipped event candidates, and two mandatory controls. All formulas, "
        "budgets, caps, costs, schedules, benchmarks, permutation count, and statistical "
        "thresholds are fixed in candidate-manifest.json before diagnostics. No R6 return "
        "is treated as R7 evidence and no post-result parameter edit is permitted.\n",
        encoding="utf-8",
    )
    (root / ITERATION_DIR / "decision-record.md").write_text(
        "# R7 Preregistered Decision Record\n\n"
        "## Daily Core Path\n"
        "- Path: Five capped self-financing core and satellite candidates.\n"
        "- Decision: continue to preregistered diagnostics only after the pre-backtest gate.\n"
        "- Reason: R6 accounting failed and R7 has no performance result yet.\n"
        "- Next iteration suggestion: use a new iteration for any formula or threshold change.\n\n"
        "## Intraday Overlay Path\n"
        "- Path: One exact-parent-mask 10:30 execution shadow.\n"
        "- Decision: continue as selection-prohibited matched evidence only.\n"
        "- Reason: IEX lacks consolidated execution parity and no matched result exists yet.\n"
        "- Next iteration suggestion: stop automatically on schedule or session mismatch.\n\n"
        "## Event And AI Path\n"
        "- Path: SEC, news, earnings, and call packet overlays.\n"
        "- Decision: stop historical execution while real PIT packets are missing.\n"
        "- Reason: fixtures and retrospective LLM output are prohibited substitutes.\n"
        "- Next iteration suggestion: continue prospective packet collection with full "
        "provenance.\n\n"
        "## Paper Simulation Path\n"
        "- Path: Formal-forward observation followed by possible paper review.\n"
        "- Decision: stop activation pending all research, forward, TCA, and safety gates.\n"
        "- Reason: this draft has no promotion or paper authority.\n"
        "- Next iteration suggestion: do not weaken gates to accelerate activation.\n",
        encoding="utf-8",
    )


def _write_r7_knowledge_contracts(root: Path) -> None:
    query_manifest = {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "max_results_per_query": 3,
        "queries": [
            {
                "query_id": "core_satellite_momentum",
                "query": "cat:q-fin.PM AND (all:momentum OR all:trend) AND all:portfolio",
                "topics": ["core satellite", "time series momentum", "sector momentum"],
            },
            {
                "query_id": "backtest_selection_bias",
                "query": "cat:q-fin.ST AND (all:backtest AND all:overfitting)",
                "topics": ["PBO", "DSR", "selection bias"],
            },
            {
                "query_id": "event_point_in_time",
                "query": "cat:q-fin.ST AND (all:filing OR all:news) AND all:timestamp",
                "topics": ["SEC", "news", "point in time", "conference calls"],
            },
        ],
        "curated_candidates": [
            {
                "discovery_id": "residual_momentum",
                "url": "https://doi.org/10.1016/j.jempfin.2011.01.003",
                "title": "Residual momentum",
                "summary": "Residual-return ranking reduces common-factor contamination.",
                "published_at": "2011",
                "authors": ["David Blitz", "Joop Huij", "Martin Martens"],
                "source_type": "paper",
                "topics": ["residual momentum"],
            },
            {
                "discovery_id": "momentum_crashes",
                "url": "https://doi.org/10.1016/j.jfineco.2014.11.010",
                "title": "Momentum Crashes",
                "summary": "Momentum crash risk is time varying.",
                "published_at": "2016",
                "authors": ["Kent Daniel", "Tobias Moskowitz"],
                "source_type": "paper",
                "topics": ["momentum crash", "risk management"],
            },
            {
                "discovery_id": "pbo",
                "url": "https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf",
                "title": "The Probability of Backtest Overfitting",
                "summary": "Partition-based diagnostic for strategy-selection overfitting.",
                "published_at": "2016",
                "authors": [
                    "David Bailey",
                    "Jonathan Borwein",
                    "Marcos Lopez de Prado",
                    "Qiji Zhu",
                ],
                "source_type": "paper",
                "topics": ["PBO", "multiple testing"],
            },
            {
                "discovery_id": "dsr",
                "url": "https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf",
                "title": "The Deflated Sharpe Ratio",
                "summary": "Sharpe inference adjusted for selection and non-normality.",
                "published_at": "2014",
                "authors": ["David Bailey", "Marcos Lopez de Prado"],
                "source_type": "paper",
                "topics": ["DSR", "multiple testing"],
            },
        ],
    }
    write_json(root / ITERATION_DIR / "knowledge-scout-queries.json", query_manifest)
    prior_models = _load_json(root / R6_ITERATION_DIR / "model-reuse-decision.json")
    prior_models.update(
        {
            "iter_id": ITER_ID,
            "generated_at": datetime.now(UTC).isoformat(),
            "default_policy": "retain_all_prior_models_as_negative_memory_no_R7_training",
        }
    )
    write_json(root / ITERATION_DIR / "model-reuse-decision.json", prior_models)
    write_json(
        root / ITERATION_DIR / "modality-role-matrix.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "order_authority": False,
            "trainable_model_authorized": False,
            "roles": [
                {
                    "role": "factor_generation",
                    "modalities": [
                        "adjusted daily OHLCV",
                        "30m OHLCV",
                        "future SEC packets",
                        "future news earnings call packets",
                    ],
                    "methods": ["fixed transforms", "future grounded extraction"],
                    "fallback": "quant factors unchanged",
                },
                {
                    "role": "return_ranking",
                    "modalities": ["residual return", "trend consistency"],
                    "methods": ["fixed cross-sectional ranks"],
                    "fallback": "SPY trend core or cash",
                    "direct_ml_ranker_applicable": False,
                    "reason": (
                        "Prior direct ML paths failed and R7 is an accounting correction round."
                    ),
                },
                {
                    "role": "risk_prediction",
                    "modalities": ["21-day realized volatility", "sector breadth"],
                    "methods": ["fixed inverse-volatility sizing", "fixed regime cap"],
                    "fallback": "cash remainder",
                    "trainable_model_applicable": False,
                },
                {
                    "role": "regime_meta_gating",
                    "modalities": ["SPY 126-day trend", "sector breadth", "first hour"],
                    "methods": ["fixed thresholds"],
                    "fallback": "no new allocation",
                },
                {
                    "role": "sizing",
                    "modalities": ["fixed sleeve budgets", "rank hold band", "inverse volatility"],
                    "methods": ["equal budget", "inverse volatility", "cash remainder"],
                    "fallback": "cash",
                },
                {
                    "role": "uncertainty",
                    "modalities": ["missing packet", "permuted score", "future packet"],
                    "methods": [
                        "dependency skip",
                        "permutation distribution",
                        "availability rejection",
                    ],
                    "fallback": "quant-only behavior",
                },
                {
                    "role": "LLM_or_text_signal",
                    "modalities": ["SEC", "news", "earnings", "licensed call Q&A"],
                    "methods": ["future grounded extraction with evidence spans"],
                    "fallback": "quant-only D05",
                    "historical_training_authorized": False,
                    "llm_contribution_pass": False,
                },
            ],
            "required_ablations": list(EXPECTED_CANDIDATE_IDS),
            "llm_contribution_pass": False,
        },
    )


def load_r7_panel(root: Path | None = None) -> R6Panel:
    base = root or project_root()
    _verify_r7_panel_manifest(base)
    return load_r6_panel(base)


def build_r7_targets(
    candidate_id: str,
    panel: R6Panel,
    features: R6DailyFeatures,
    *,
    score_override: pd.DataFrame | None = None,
) -> R7Targets:
    if candidate_id not in {"D01", "D02", "D03", "D04", "D05"}:
        raise R7ContractViolation(f"unsupported R7 daily candidate: {candidate_id}")
    dates = list(panel.daily_sessions)
    weights = pd.DataFrame(0.0, index=dates, columns=ALL_DAILY_SYMBOLS)
    decision_mask = pd.Series(False, index=dates, dtype=bool)
    start_index = dates.index(features.evaluation_start)
    score = score_override if score_override is not None else features.residual_score
    previous: list[str] = []
    current = pd.Series(0.0, index=ALL_DAILY_SYMBOLS, dtype=float)
    spy_close = panel.daily[SPY].loc[dates, "close"].astype(float)
    spy_ma_126 = spy_close.rolling(126, min_periods=126).mean()
    spy_momentum_126 = spy_close / spy_close.shift(126) - 1.0

    for offset, session in enumerate(dates[start_index:]):
        if offset % REBALANCE_SESSIONS == 0:
            decision_mask.loc[session] = True
            ranked = _ranked_symbols(
                score.loc[session],
                features.residual_eligible.loc[session],
            )
            selected = _select_with_hold_band(
                ranked,
                previous,
                top_n=TOP_N,
                hold_rank=HOLD_RANK,
            )
            previous = list(selected)
            core_on = bool(
                spy_close.loc[session] > spy_ma_126.loc[session]
                and spy_momentum_126.loc[session] > 0.0
            )
            core = pd.Series(0.0, index=ALL_DAILY_SYMBOLS, dtype=float)
            if core_on:
                core.loc[SPY] = CORE_BUDGET
            equal_satellite = _equal_budget_sleeve(
                selected,
                budget=SATELLITE_BUDGET_FULL,
                symbol_cap=0.2,
            ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)
            inverse_satellite = _inverse_volatility_sleeve(
                selected,
                features.realized_vol_21.loc[session],
                budget=SATELLITE_BUDGET_FULL,
                symbol_cap=0.3,
                target_volatility=TARGET_VOLATILITY,
            ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)
            conservative_satellite = _inverse_volatility_sleeve(
                selected,
                features.realized_vol_21.loc[session],
                budget=SATELLITE_BUDGET_CONSERVATIVE,
                symbol_cap=0.2,
                target_volatility=TARGET_VOLATILITY,
            ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)

            if candidate_id == "D01":
                current = core
            elif candidate_id == "D02":
                current = equal_satellite
            elif candidate_id == "D03":
                current = core + equal_satellite
            elif candidate_id == "D04":
                current = core + inverse_satellite
            else:
                current = core.copy()
                if bool(features.regime_on.loc[session]):
                    current = current + conservative_satellite
            _validate_target_row(current, candidate_id=candidate_id, session=session)
        weights.loc[session] = current
    return R7Targets(weights=weights, decision_mask=decision_mask)


def simulate_self_financing(
    panel: R6Panel,
    targets: R7Targets,
    *,
    enforce_target_cap: bool = True,
) -> R7Simulation:
    dates = list(panel.daily_sessions)
    opens = _daily_field(panel, "open").loc[:, list(ALL_DAILY_SYMBOLS)]
    interval_dates = dates[1:-1]
    gross_returns = pd.Series(0.0, index=interval_dates, dtype=float)
    turnover = pd.Series(0.0, index=interval_dates, dtype=float)
    weights = pd.DataFrame(0.0, index=interval_dates, columns=ALL_DAILY_SYMBOLS)
    current = pd.Series(0.0, index=ALL_DAILY_SYMBOLS, dtype=float)
    rebalance_sessions: list[date] = []

    for position, session in enumerate(interval_dates, start=1):
        signal_session = dates[position - 1]
        next_session = dates[position + 1]
        if bool(targets.decision_mask.loc[signal_session]):
            target = targets.weights.loc[signal_session].astype(float)
            if enforce_target_cap:
                _validate_target_row(target, candidate_id="simulation", session=signal_session)
            else:
                _validate_long_only_target(target, candidate_id="benchmark", session=signal_session)
            turnover.loc[session] = float((target - current).abs().sum())
            current = target.copy()
            rebalance_sessions.append(session)
        weights.loc[session] = current
        asset_returns = opens.loc[next_session] / opens.loc[session] - 1.0
        portfolio_return = float((current * asset_returns).sum())
        gross_returns.loc[session] = portfolio_return
        denominator = 1.0 + portfolio_return
        if denominator <= 0.0 or not math.isfinite(denominator):
            raise R7ContractViolation(f"invalid self-financing equity at {session}")
        current = current.mul(1.0 + asset_returns).div(denominator)
        if (current < -1e-12).any() or float(current.sum()) > 1.0 + 1e-9:
            raise R7ContractViolation(f"invalid drifted holdings at {next_session}")

    return R7Simulation(
        gross_returns=gross_returns,
        rebalance_turnover=turnover,
        weights=weights,
        terminal_turnover=float(current.abs().sum()),
        terminal_session=dates[-1],
        rebalance_sessions=tuple(rebalance_sessions),
    )


def _evaluate_simulation(
    simulation: R7Simulation,
    *,
    cost_bps: float,
    start_after: date,
) -> dict[str, Any]:
    mask = pd.Index(simulation.gross_returns.index).map(lambda value: value > start_after)
    gross = simulation.gross_returns.loc[mask].astype(float)
    turnover = simulation.rebalance_turnover.reindex(gross.index).fillna(0.0).astype(float)
    weights = simulation.weights.reindex(gross.index).fillna(0.0)
    if gross.empty:
        raise R7ContractViolation("R7 evaluation window is empty")
    rate = cost_bps / 10_000.0
    net = (1.0 - turnover * rate) * (1.0 + gross) - 1.0
    net.iloc[-1] = (1.0 + net.iloc[-1]) * (1.0 - simulation.terminal_turnover * rate) - 1.0
    aggregate = _performance_payload(
        net,
        gross,
        turnover,
        weights,
        terminal_turnover=simulation.terminal_turnover,
        terminal_session=simulation.terminal_session,
    )
    folds = []
    for fold_number, positions in enumerate(np.array_split(np.arange(len(net)), OUTER_FOLDS), 1):
        if len(positions) == 0:
            continue
        index = net.index[positions]
        fold_terminal = simulation.terminal_turnover if positions[-1] == len(net) - 1 else 0.0
        fold_terminal_session = simulation.terminal_session if fold_terminal else index[-1]
        fold_payload = _performance_payload(
            net.loc[index],
            gross.loc[index],
            turnover.loc[index],
            weights.loc[index],
            terminal_turnover=fold_terminal,
            terminal_session=fold_terminal_session,
        )
        fold_payload.update(
            {
                "fold": fold_number,
                "start": index[0].isoformat(),
                "return_period_end": index[-1].isoformat(),
            }
        )
        folds.append(fold_payload)
    return {
        "one_way_cost_bps": cost_bps,
        "aggregate": aggregate,
        "folds": folds,
        "positive_fold_count": sum(
            float(fold.get("total_return_pct") or 0.0) > 0.0 for fold in folds
        ),
        "net_returns": net,
    }


def _performance_payload(
    net: pd.Series,
    gross: pd.Series,
    turnover: pd.Series,
    weights: pd.DataFrame,
    *,
    terminal_turnover: float,
    terminal_session: date,
) -> dict[str, Any]:
    equity = [1.0, *(1.0 + net).cumprod().tolist()]
    exposure = weights.abs().sum(axis=1)
    trade_mask = turnover > 1e-12
    if terminal_turnover > 1e-12 and len(trade_mask):
        trade_mask.iloc[-1] = True
    metrics = build_performance_metrics(
        equity,
        "daily",
        trade_pnls=net.loc[trade_mask].tolist(),
        trade_return_pcts=(net.loc[trade_mask] * 100.0).tolist(),
        exposure_pct=float(exposure.mean() * 100.0) if len(exposure) else 0.0,
        turnover_ratio=float(turnover.sum() + terminal_turnover),
    )
    rebalance_rows = turnover > 1e-12
    maximum_target_weight = (
        float(weights.loc[rebalance_rows].max().max()) if rebalance_rows.any() else 0.0
    )
    return {
        "session_count": len(net),
        "start": net.index[0].isoformat(),
        "return_period_end": net.index[-1].isoformat(),
        "terminal_execution_session": terminal_session.isoformat(),
        "total_return_pct": _round((equity[-1] - 1.0) * 100.0),
        "gross_total_return_pct": _round(((1.0 + gross).prod() - 1.0) * 100.0),
        "annualized_return_pct": _round(metrics.annualized_return_pct),
        "annualized_volatility_pct": _round(metrics.annualized_volatility_pct),
        "sharpe": _round(metrics.sharpe_ratio),
        "sortino": _round(metrics.sortino_ratio),
        "calmar": _round(metrics.calmar_ratio),
        "max_drawdown_pct": _round(metrics.max_drawdown_pct),
        "win_rate_pct": _round(metrics.win_rate_pct),
        "exposure_pct": _round(metrics.exposure_pct),
        "turnover_units": _round(float(turnover.sum() + terminal_turnover)),
        "rebalance_day_count": int(rebalance_rows.sum()),
        "average_daily_turnover": _round(
            float((turnover.sum() + terminal_turnover) / len(turnover))
        ),
        "maximum_rebalance_target_weight": _round(maximum_target_weight),
        "maximum_drifted_weight": _round(float(weights.max().max())),
        "terminal_turnover": _round(terminal_turnover),
        "cost_drag_pct_points": _round((((1.0 + gross).prod() - 1.0) - (equity[-1] - 1.0)) * 100.0),
    }


def _equal_budget_sleeve(
    selected: list[str],
    *,
    budget: float,
    symbol_cap: float,
) -> pd.Series:
    if not selected:
        return pd.Series(dtype=float)
    each = min(symbol_cap, budget / len(selected))
    return pd.Series({symbol: each for symbol in selected}, dtype=float)


def _inverse_volatility_sleeve(
    selected: list[str],
    volatility: pd.Series,
    *,
    budget: float,
    symbol_cap: float,
    target_volatility: float,
) -> pd.Series:
    if not selected:
        return pd.Series(dtype=float)
    vol = volatility.loc[selected].astype(float).clip(lower=1e-6)
    raw = (1.0 / vol) / (1.0 / vol).sum()
    ex_ante = math.sqrt(float(((raw * vol) ** 2).sum()))
    gross = min(budget, target_volatility / ex_ante) if ex_ante > 0.0 else 0.0
    return (raw * gross).clip(upper=symbol_cap)


def _validate_target_row(
    weights: pd.Series,
    *,
    candidate_id: str,
    session: date,
) -> None:
    _validate_long_only_target(weights, candidate_id=candidate_id, session=session)
    values = weights.astype(float)
    if float(values.max()) > POSITION_CAP + 1e-12:
        raise R7ContractViolation(f"position cap violation for {candidate_id} at {session}")


def _validate_long_only_target(
    weights: pd.Series,
    *,
    candidate_id: str,
    session: date,
) -> None:
    values = weights.astype(float)
    if not np.isfinite(values.to_numpy()).all():
        raise R7ContractViolation(f"non-finite target for {candidate_id} at {session}")
    if (values < -1e-12).any():
        raise R7ContractViolation(f"negative target for {candidate_id} at {session}")
    if float(values.sum()) > 1.0 + 1e-12:
        raise R7ContractViolation(f"gross exposure violation for {candidate_id} at {session}")


def simulate_matched_intraday_pair(
    panel: R6Panel,
    features: R6DailyFeatures,
    parent_targets: R7Targets,
) -> tuple[R7Simulation, R7Simulation, dict[str, Any]]:
    sessions = [
        session
        for session in panel.intraday_sessions
        if session > features.evaluation_start and session in set(panel.daily_sessions)
    ]
    if len(sessions) < 252:
        raise R7ContractViolation("R7 intraday comparison has fewer than 252 sessions")
    daily_dates = list(panel.daily_sessions)
    execution_targets: dict[date, pd.Series] = {}
    for decision_session in daily_dates:
        if not bool(parent_targets.decision_mask.loc[decision_session]):
            continue
        position = daily_dates.index(decision_session)
        if position + 1 >= len(daily_dates):
            continue
        execution_session = daily_dates[position + 1]
        if execution_session in set(sessions[:-1]):
            execution_targets[execution_session] = parent_targets.weights.loc[
                decision_session
            ].astype(float)
    expected_schedule = tuple(sorted(execution_targets))
    open_0930, close_1000, open_1030 = _intraday_anchor_frames(panel, sessions)
    interval_dates = sessions[:-1]

    parent = _simulate_intraday_path(
        interval_dates=interval_dates,
        terminal_session=sessions[-1],
        execution_targets=execution_targets,
        open_0930=open_0930,
        close_1000=close_1000,
        open_1030=open_1030,
        delayed=False,
    )
    overlay = _simulate_intraday_path(
        interval_dates=interval_dates,
        terminal_session=sessions[-1],
        execution_targets=execution_targets,
        open_0930=open_0930,
        close_1000=close_1000,
        open_1030=open_1030,
        delayed=True,
    )
    if parent.rebalance_sessions != expected_schedule:
        raise R7ContractViolation("D04 same-window benchmark schedule mismatch")
    if overlay.rebalance_sessions != expected_schedule:
        raise R7ContractViolation("D06 did not reuse the exact D04 execution mask")
    if parent.gross_returns.index.tolist() != overlay.gross_returns.index.tolist():
        raise R7ContractViolation("D06 and D04 same-window sessions differ")
    evidence = {
        "status": "pass",
        "parent_candidate_id": "D04",
        "overlay_candidate_id": "D06",
        "shared_return_session_count": len(interval_dates),
        "shared_rebalance_count": len(expected_schedule),
        "exact_schedule_match": True,
        "first_rebalance": expected_schedule[0].isoformat() if expected_schedule else None,
        "last_rebalance": expected_schedule[-1].isoformat() if expected_schedule else None,
        "rebalance_dates_sha256": _canonical_sha(
            [session.isoformat() for session in expected_schedule]
        ),
        "shared_sessions_sha256": _canonical_sha(
            [session.isoformat() for session in interval_dates]
        ),
    }
    return parent, overlay, evidence


def _simulate_intraday_path(
    *,
    interval_dates: list[date],
    terminal_session: date,
    execution_targets: dict[date, pd.Series],
    open_0930: pd.DataFrame,
    close_1000: pd.DataFrame,
    open_1030: pd.DataFrame,
    delayed: bool,
) -> R7Simulation:
    gross_returns = pd.Series(0.0, index=interval_dates, dtype=float)
    turnover = pd.Series(0.0, index=interval_dates, dtype=float)
    weights = pd.DataFrame(0.0, index=interval_dates, columns=ALL_DAILY_SYMBOLS)
    current = pd.Series(0.0, index=ALL_DAILY_SYMBOLS, dtype=float)
    rebalance_sessions: list[date] = []
    core_columns = list(CORE_SYMBOLS)

    for offset, session in enumerate(interval_dates):
        next_session = (
            interval_dates[offset + 1] if offset + 1 < len(interval_dates) else terminal_session
        )
        if delayed:
            first_returns = (
                open_1030.loc[session, core_columns] / open_0930.loc[session, core_columns] - 1.0
            ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)
            first_portfolio = float((current * first_returns).sum())
            current = _drift_weights(current, first_returns, session=session)
            if session in execution_targets:
                target = execution_targets[session].copy()
                first_hour = (
                    close_1000.loc[session, core_columns] / open_0930.loc[session, core_columns]
                    - 1.0
                )
                spy_first_hour = float(first_hour[SPY])
                breadth = float((first_hour.loc[list(SECTOR_SYMBOLS)] > 0.0).mean())
                for symbol in SECTOR_SYMBOLS:
                    increasing = target[symbol] > current[symbol] + 1e-12
                    relative = float(first_hour[symbol] - spy_first_hour)
                    buy_allowed = spy_first_hour > -0.005 and relative > 0.0 and breadth >= 0.45
                    if increasing and not buy_allowed:
                        target[symbol] = min(target[symbol], current[symbol])
                _validate_target_row(target, candidate_id="D06", session=session)
                turnover.loc[session] = float((target - current).abs().sum())
                current = target
                rebalance_sessions.append(session)
            post_returns = (
                open_0930.loc[next_session, core_columns] / open_1030.loc[session, core_columns]
                - 1.0
            ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)
            post_portfolio = float((current * post_returns).sum())
            gross_returns.loc[session] = (1.0 + first_portfolio) * (1.0 + post_portfolio) - 1.0
            weights.loc[session] = current
            current = _drift_weights(current, post_returns, session=session)
        else:
            if session in execution_targets:
                target = execution_targets[session].copy()
                _validate_target_row(target, candidate_id="D04_same_window", session=session)
                turnover.loc[session] = float((target - current).abs().sum())
                current = target
                rebalance_sessions.append(session)
            weights.loc[session] = current
            full_returns = (
                open_0930.loc[next_session, core_columns] / open_0930.loc[session, core_columns]
                - 1.0
            ).reindex(ALL_DAILY_SYMBOLS, fill_value=0.0)
            gross_returns.loc[session] = float((current * full_returns).sum())
            current = _drift_weights(current, full_returns, session=session)
    return R7Simulation(
        gross_returns=gross_returns,
        rebalance_turnover=turnover,
        weights=weights,
        terminal_turnover=float(current.abs().sum()),
        terminal_session=terminal_session,
        rebalance_sessions=tuple(rebalance_sessions),
    )


def _drift_weights(
    current: pd.Series,
    returns: pd.Series,
    *,
    session: date,
) -> pd.Series:
    portfolio_return = float((current * returns).sum())
    denominator = 1.0 + portfolio_return
    if denominator <= 0.0 or not math.isfinite(denominator):
        raise R7ContractViolation(f"invalid self-financing equity at {session}")
    drifted = current.mul(1.0 + returns).div(denominator)
    if (drifted < -1e-12).any() or float(drifted.sum()) > 1.0 + 1e-9:
        raise R7ContractViolation(f"invalid drifted weights at {session}")
    return drifted


def validate_event_packet_availability(packet: dict[str, Any]) -> dict[str, Any]:
    required = {
        "published_at",
        "fetched_at",
        "visible_at",
        "decision_at",
        "source",
        "symbol",
        "input_hash",
        "prompt_hash",
        "dedupe_key",
        "evidence_spans",
    }
    missing = sorted(field for field in required if packet.get(field) in (None, "", []))
    if missing:
        raise R7FeatureAvailabilityError("missing packet fields: " + ",".join(missing))
    published = _parse_timestamp(str(packet["published_at"]))
    fetched = _parse_timestamp(str(packet["fetched_at"]))
    visible = _parse_timestamp(str(packet["visible_at"]))
    decision = _parse_timestamp(str(packet["decision_at"]))
    if visible < published or visible < fetched:
        raise R7FeatureAvailabilityError("visible_at predates publication or collection")
    if visible >= decision:
        raise R7FeatureAvailabilityError("packet is not visible before the decision")
    return {
        "symbol": str(packet["symbol"]),
        "visible_at": visible.isoformat(),
        "decision_at": decision.isoformat(),
        "availability": "valid",
    }


def run_future_packet_control() -> dict[str, Any]:
    packet = {
        "published_at": "2026-07-21T13:00:00+00:00",
        "fetched_at": "2026-07-21T13:00:02+00:00",
        "visible_at": "2026-07-21T13:00:02+00:00",
        "decision_at": "2026-07-21T12:59:59+00:00",
        "source": "malicious_control_fixture",
        "symbol": "SPY",
        "input_hash": "0" * 64,
        "prompt_hash": "1" * 64,
        "dedupe_key": "N02-future-packet",
        "evidence_spans": [{"start": 0, "end": 1}],
    }
    try:
        validate_event_packet_availability(packet)
    except R7FeatureAvailabilityError as exc:
        return {
            "candidate_id": "N02",
            "status": "rejected_control",
            "reason_code": "future_packet_rejected_by_event_candidate_validator",
            "detail": str(exc),
            "selection_prohibited": True,
            "pass": True,
        }
    raise R7ContractViolation("future packet control was accepted")


def _run_permutation_control(
    panel: R6Panel,
    features: R6DailyFeatures,
    parent_evaluation: dict[str, Any],
) -> dict[str, Any]:
    rng = np.random.default_rng(PERMUTATION_SEED)
    decision_dates = list(
        build_r7_targets("D02", panel, features).decision_mask.loc[lambda values: values].index
    )
    sharpe_values = []
    return_values = []
    for _ in range(PERMUTATION_REPLICATES):
        shuffled = features.residual_score.copy()
        for session in decision_dates:
            values = shuffled.loc[session, list(SECTOR_SYMBOLS)].to_numpy(copy=True)
            shuffled.loc[session, list(SECTOR_SYMBOLS)] = values[rng.permutation(len(values))]
        targets = build_r7_targets("D02", panel, features, score_override=shuffled)
        simulation = simulate_self_financing(panel, targets)
        evaluation = _evaluate_simulation(
            simulation,
            cost_bps=10.0,
            start_after=features.evaluation_start,
        )
        aggregate = evaluation["aggregate"]
        sharpe_values.append(_metric_value(aggregate, "sharpe", -math.inf))
        return_values.append(_metric_value(aggregate, "total_return_pct", -math.inf))
    parent_sharpe = _metric_value(parent_evaluation["aggregate"], "sharpe", -math.inf)
    percentile_95 = float(np.quantile(sharpe_values, 0.95))
    exceedance_p = float((1 + sum(value >= parent_sharpe for value in sharpe_values)) / 101)
    passed = parent_sharpe > percentile_95
    return {
        "candidate_id": "N01",
        "status": "completed_control",
        "selection_prohibited": True,
        "replicate_count": PERMUTATION_REPLICATES,
        "seed": PERMUTATION_SEED,
        "shuffle_scope": "within_each_decision_cross_section",
        "metric": "10bps_annualized_sharpe",
        "parent_candidate_id": "D02",
        "parent_sharpe": _round(parent_sharpe),
        "placebo_sharpe_mean": _round(float(np.mean(sharpe_values))),
        "placebo_sharpe_95th_percentile": _round(percentile_95),
        "placebo_total_return_mean_pct": _round(float(np.mean(return_values))),
        "empirical_exceedance_p": _round(exceedance_p),
        "pass": passed,
    }


def run_r7_diagnostics(root: Path | None = None) -> R7DiagnosticResult:
    base = root or project_root()
    _verify_r7_preregistration(base)
    panel = load_r7_panel(base)
    features = build_r6_daily_features(panel)
    targets = {
        candidate_id: build_r7_targets(candidate_id, panel, features)
        for candidate_id in ("D01", "D02", "D03", "D04", "D05")
    }
    contract_checks = _daily_contract_checks(targets, panel, features)
    simulations = {
        candidate_id: simulate_self_financing(panel, candidate_targets)
        for candidate_id, candidate_targets in targets.items()
    }
    parent_intraday, overlay_intraday, intraday_contract = simulate_matched_intraday_pair(
        panel,
        features,
        targets["D04"],
    )
    simulations["D06"] = overlay_intraday

    internal_evaluations: dict[str, dict[str, dict[str, Any]]] = {}
    results: dict[str, dict[str, Any]] = {}
    for candidate_id, simulation in simulations.items():
        cost_evaluations = {
            _cost_key(cost): _evaluate_simulation(
                simulation,
                cost_bps=cost,
                start_after=features.evaluation_start,
            )
            for cost in COST_SCENARIOS
        }
        internal_evaluations[candidate_id] = cost_evaluations
        results[candidate_id] = {
            "candidate_id": candidate_id,
            "status": "completed",
            "selection_prohibited": candidate_id == "D06",
            "cost_scenarios": {
                key: _public_evaluation(value) for key, value in cost_evaluations.items()
            },
        }
    results["E01"] = _skipped_result("E01", "real_historical_SEC_PIT_packets_missing")
    results["E02"] = _skipped_result(
        "E02", "real_historical_news_earnings_call_PIT_packets_missing"
    )
    permutation = _run_permutation_control(
        panel,
        features,
        internal_evaluations["D02"]["10bps"],
    )
    future_control = run_future_packet_control()
    results["N01"] = permutation
    results["N02"] = future_control

    benchmarks = _build_r7_benchmarks(
        panel,
        features,
        parent_intraday=parent_intraday,
    )
    benchmark_sharpe = max(
        _metric_value(
            benchmarks[name]["cost_scenarios"]["10bps"]["aggregate"],
            "sharpe",
            -math.inf,
        )
        for name in ("SPY_buy_and_hold", "equal_weight_sector_buy_and_hold")
    )
    candidate_gates = {
        candidate_id: _candidate_gate(
            results[candidate_id],
            benchmark_sharpe=benchmark_sharpe,
            contract_valid=contract_checks["pass"],
        )
        for candidate_id in ("D01", "D02", "D03", "D04", "D05")
    }
    overfit = _overfit_diagnostics(internal_evaluations)
    eligible = []
    for candidate_id, gate in candidate_gates.items():
        satellite_control_pass = permutation["pass"] if candidate_id != "D01" else True
        if gate["pass"] and satellite_control_pass and future_control["pass"] and overfit["pass"]:
            eligible.append(candidate_id)
    ranking = sorted(
        eligible,
        key=lambda candidate_id: (
            -_metric_value(
                results[candidate_id]["cost_scenarios"]["10bps"]["aggregate"],
                "sharpe",
                -math.inf,
            ),
            candidate_id,
        ),
    )
    selected_id = ranking[0] if ranking else None
    formal_forward_count = int(
        _load_json(base / PANEL_MANIFEST_PATH).get("formal_forward_daily_observation_count", 0)
    )

    manifest = _load_json(base / CANDIDATE_MANIFEST_PATH)
    ledger_rows = []
    for candidate in manifest["candidates"]:
        candidate_id = str(candidate["candidate_id"])
        row = {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "candidate_id": candidate_id,
            "path": candidate["path"],
            "role": candidate["role"],
            "method": candidate["method"],
            "ablation": candidate["ablation"],
            "status": results[candidate_id]["status"],
            "selection_prohibited": bool(candidate.get("selection_prohibited", False)),
            "candidate_binding_sha256": _canonical_sha(candidate),
            "result": results[candidate_id],
        }
        if candidate_id in candidate_gates:
            row["promotion_gate"] = candidate_gates[candidate_id]
        ledger_rows.append(row)

    historical_candidate_gate_pass = selected_id is not None
    payload = {
        "schema_version": 1,
        "report_type": "core_satellite_r7_evaluation",
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_NAME,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": contract_checks["pass"] and intraday_contract["status"] == "pass",
        "historical_candidate_gate_pass": historical_candidate_gate_pass,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "research_pass_blockers": [
            *([] if historical_candidate_gate_pass else ["no_candidate_cleared_historical_gate"]),
            "backtest_forensics_pending",
            "independent_SIP_or_official_open_parity_missing",
        ],
        "paper_ready_blockers": [
            "formal_forward_observations_missing"
            if formal_forward_count == 0
            else "formal_forward_gate_not_assessed",
            "matched_paper_TCA_missing",
            "promotion_not_passed",
            "paper_safety_review_missing",
        ],
        "data_scope": {
            "scope": "fixed_sector_etf_IEX_adjusted_diagnostic",
            "daily_session_count": len(panel.daily_sessions),
            "daily_first_session": panel.daily_sessions[0].isoformat(),
            "daily_last_session": panel.daily_sessions[-1].isoformat(),
            "daily_evaluation_start": features.evaluation_start.isoformat(),
            "intraday_complete_session_count": len(panel.intraday_sessions),
            "intraday_first_session": panel.intraday_sessions[0].isoformat(),
            "intraday_last_session": panel.intraday_sessions[-1].isoformat(),
            "formal_forward_start": FORMAL_FORWARD_START,
            "formal_forward_observation_count": formal_forward_count,
            "provider": "alpaca",
            "feed": "iex",
            "adjustment": "all",
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(EXPECTED_CANDIDATE_IDS),
            "completed_count": sum(row["status"] == "completed" for row in results.values()),
            "completed_control_count": sum(
                row["status"] in {"completed_control", "rejected_control"}
                for row in results.values()
            ),
            "dependency_skipped_count": sum(
                row["status"] == "skipped_dependency" for row in results.values()
            ),
            "unresolved_count": 0,
        },
        "candidate_results": [results[candidate_id] for candidate_id in EXPECTED_CANDIDATE_IDS],
        "candidate_gates": candidate_gates,
        "negative_controls": {
            "permutation_distribution": permutation,
            "future_packet": future_control,
        },
        "overfit_diagnostics": overfit,
        "contract_checks": contract_checks,
        "intraday_contract": intraday_contract,
        "benchmarks": benchmarks,
        "diagnostic_leader": {
            "candidate_id": selected_id,
            "historical_gate_pass": historical_candidate_gate_pass,
            "selection_authority": False,
            "metrics_10bps": results[selected_id]["cost_scenarios"]["10bps"]["aggregate"]
            if selected_id
            else None,
        },
        "selected_candidate_ids": [selected_id] if selected_id else [],
        "selection_note": (
            "One preregistered historical candidate clears all frozen diagnostic gates, but "
            "it has no forward, promotion, or paper authority."
            if selected_id
            else "No candidate clears the frozen R7 historical and statistical gates."
        ),
        "input_bindings": {
            "spec_path": str(SPEC_PATH),
            "spec_hash": strategy_content_hash(load_strategy_spec(base / SPEC_PATH)),
            "candidate_manifest_sha256": _sha256_file(base / CANDIDATE_MANIFEST_PATH),
            "data_feasibility_sha256": _sha256_file(base / DATA_FEASIBILITY_PATH),
            "panel_manifest_sha256": _sha256_file(base / PANEL_MANIFEST_PATH),
            "cost_contract_sha256": _sha256_file(base / COST_CONTRACT_PATH),
            "runner_path": str(RUNNER_PATH),
            "runner_sha256": _sha256_file(base / RUNNER_PATH),
            "data_feature_dependency_path": str(R6_DEPENDENCY_PATH),
            "data_feature_dependency_sha256": _sha256_file(base / R6_DEPENDENCY_PATH),
        },
    }
    output = ensure_dir(base / ITERATION_DIR)
    evaluation_path = output / "evaluation-report.json"
    markdown_path = output / "evaluation-report.md"
    ledger_path = output / "trial-ledger.jsonl"
    write_json(evaluation_path, payload)
    _write_jsonl(ledger_path, ledger_rows)
    markdown_path.write_text(_render_r7_evaluation(payload), encoding="utf-8")
    write_json(
        output / "forward-observation-status.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "formal_forward_start": FORMAL_FORWARD_START,
            "observation_count": formal_forward_count,
            "status": "blocked_no_observations" if formal_forward_count == 0 else "pending_review",
            "broker_orders_authorized": False,
        },
    )
    write_json(
        output / "feature-diagnostics.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "evaluation_start": features.evaluation_start.isoformat(),
            "daily_session_count": len(panel.daily_sessions),
            "intraday_complete_session_count": len(panel.intraday_sessions),
            "future_feature_used": False,
            "forward_fill_used": False,
            "zero_return_substitution_used": False,
            "position_cap_semantics": "rebalance_target_only_natural_drift_allowed",
        },
    )
    return R7DiagnosticResult(
        evaluation_path=evaluation_path,
        markdown_path=markdown_path,
        trial_ledger_path=ledger_path,
        payload=payload,
    )


def _build_r7_benchmarks(
    panel: R6Panel,
    features: R6DailyFeatures,
    *,
    parent_intraday: R7Simulation,
) -> dict[str, Any]:
    columns = list(ALL_DAILY_SYMBOLS)
    templates: dict[str, pd.Series] = {}
    for name, symbol in (
        ("SPY_buy_and_hold", "SPY"),
        ("QQQ_buy_and_hold", "QQQ"),
        ("BIL_cash_proxy", "BIL"),
    ):
        target = pd.Series(0.0, index=columns, dtype=float)
        target.loc[symbol] = 1.0
        templates[name] = target
    equal_weight = pd.Series(0.0, index=columns, dtype=float)
    equal_weight.loc[list(SECTOR_SYMBOLS)] = 1.0 / len(SECTOR_SYMBOLS)
    templates["equal_weight_sector_buy_and_hold"] = equal_weight
    templates["uninvested_cash"] = pd.Series(0.0, index=columns, dtype=float)

    opens = _daily_field(panel, "open")
    evaluation_dates = [
        session for session in panel.daily_sessions if session > features.evaluation_start
    ]
    gross_by_sector = {}
    for symbol in SECTOR_SYMBOLS:
        series = opens.loc[evaluation_dates, symbol]
        gross_by_sector[symbol] = float(series.iloc[-1] / series.iloc[0] - 1.0)
    best_symbol = max(gross_by_sector, key=lambda symbol: (gross_by_sector[symbol], symbol))
    best_target = pd.Series(0.0, index=columns, dtype=float)
    best_target.loc[best_symbol] = 1.0
    templates["ex_post_best_symbol_report_only"] = best_target

    output = {}
    for name, target in templates.items():
        benchmark_targets = _static_targets(
            panel,
            start=features.evaluation_start,
            target=target,
        )
        simulation = simulate_self_financing(
            panel,
            benchmark_targets,
            enforce_target_cap=False,
        )
        output[name] = {
            "status": "completed",
            "report_only": name == "ex_post_best_symbol_report_only",
            "fixed_symbol": best_symbol if name == "ex_post_best_symbol_report_only" else None,
            "cost_scenarios": {
                _cost_key(cost): _public_evaluation(
                    _evaluate_simulation(
                        simulation,
                        cost_bps=cost,
                        start_after=features.evaluation_start,
                    )
                )
                for cost in COST_SCENARIOS
            },
        }
    output["D04_same_intraday_window"] = {
        "status": "completed",
        "report_only": False,
        "fixed_symbol": None,
        "cost_scenarios": {
            _cost_key(cost): _public_evaluation(
                _evaluate_simulation(
                    parent_intraday,
                    cost_bps=cost,
                    start_after=features.evaluation_start,
                )
            )
            for cost in COST_SCENARIOS
        },
    }
    return output


def _static_targets(
    panel: R6Panel,
    *,
    start: date,
    target: pd.Series,
) -> R7Targets:
    dates = list(panel.daily_sessions)
    weights = pd.DataFrame(0.0, index=dates, columns=ALL_DAILY_SYMBOLS)
    decision_mask = pd.Series(False, index=dates, dtype=bool)
    weights.loc[start:, :] = np.broadcast_to(
        target.reindex(ALL_DAILY_SYMBOLS, fill_value=0.0).to_numpy(dtype=float),
        (len(weights.loc[start:]), len(ALL_DAILY_SYMBOLS)),
    )
    decision_mask.loc[start] = True
    return R7Targets(weights=weights, decision_mask=decision_mask)


def _candidate_gate(
    result: dict[str, Any],
    *,
    benchmark_sharpe: float,
    contract_valid: bool,
) -> dict[str, Any]:
    ten = result["cost_scenarios"]["10bps"]
    twenty = result["cost_scenarios"]["20bps"]
    aggregate = ten["aggregate"]
    checks = {
        "implementation_contract_valid": contract_valid,
        "positive_10bps_total_return": _metric_value(aggregate, "total_return_pct", -math.inf)
        > 0.0,
        "sharpe_at_least_0_75_at_10bps": _metric_value(aggregate, "sharpe", -math.inf)
        >= SHARPE_GATE,
        "benchmark_sharpe_parity": _metric_value(aggregate, "sharpe", -math.inf)
        >= benchmark_sharpe,
        "max_drawdown_no_worse_than_20pct": _metric_value(aggregate, "max_drawdown_pct", -math.inf)
        >= MAX_DRAWDOWN_GATE_PCT,
        "at_least_3_positive_10bps_folds": int(ten["positive_fold_count"]) >= 3,
        "positive_20bps_total_return": _metric_value(
            twenty["aggregate"], "total_return_pct", -math.inf
        )
        > 0.0,
        "rebalance_target_cap_at_most_40pct": _metric_value(
            aggregate, "maximum_rebalance_target_weight", math.inf
        )
        <= POSITION_CAP + 1e-9,
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "benchmark_sharpe_threshold": _round(benchmark_sharpe),
    }


def _overfit_diagnostics(
    evaluations: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    candidate_ids = ("D01", "D02", "D03", "D04", "D05")
    aggregate_sharpes = np.array(
        [
            _metric_value(
                evaluations[candidate_id]["10bps"]["aggregate"],
                "sharpe",
                -math.inf,
            )
            for candidate_id in candidate_ids
        ],
        dtype=float,
    )
    leader_index = int(np.argmax(aggregate_sharpes))
    leader_id = candidate_ids[leader_index]
    selected_returns = evaluations[leader_id]["10bps"]["net_returns"].astype(float)
    daily_sharpes = aggregate_sharpes / math.sqrt(252.0)
    mean = float(daily_sharpes.mean())
    std = float(daily_sharpes.std(ddof=0))
    trials = len(candidate_ids)
    euler_gamma = 0.5772156649015329
    expected_max_daily = mean
    if std > 0.0 and trials > 1:
        expected_max_daily = mean + std * (
            (1.0 - euler_gamma) * NormalDist().inv_cdf(1.0 - 1.0 / trials)
            + euler_gamma * NormalDist().inv_cdf(1.0 - 1.0 / (trials * math.e))
        )
    selected_daily_sharpe = float(daily_sharpes[leader_index])
    skew = float(selected_returns.skew())
    kurtosis = float(selected_returns.kurt()) + 3.0
    observations = len(selected_returns)
    denominator = math.sqrt(
        max(
            1e-12,
            1.0
            - skew * selected_daily_sharpe
            + ((kurtosis - 1.0) / 4.0) * selected_daily_sharpe**2,
        )
    )
    z_score = (
        (selected_daily_sharpe - expected_max_daily)
        * math.sqrt(max(observations - 1, 1))
        / denominator
    )
    dsr_probability = NormalDist().cdf(z_score)

    fold_sharpes = np.array(
        [
            [
                _metric_value(
                    evaluations[candidate_id]["10bps"]["folds"][fold_index],
                    "sharpe",
                    -math.inf,
                )
                for fold_index in range(OUTER_FOLDS)
            ]
            for candidate_id in candidate_ids
        ],
        dtype=float,
    )
    held_out_rows = []
    failures = 0
    for held_out_fold in range(OUTER_FOLDS):
        train_folds = [index for index in range(OUTER_FOLDS) if index != held_out_fold]
        train_scores = fold_sharpes[:, train_folds].mean(axis=1)
        selected_index = sorted(
            range(len(candidate_ids)),
            key=lambda index: (-train_scores[index], candidate_ids[index]),
        )[0]
        held_out = fold_sharpes[:, held_out_fold]
        selected_value = held_out[selected_index]
        percentile = float(np.mean(held_out <= selected_value))
        failed = percentile <= 0.5
        failures += int(failed)
        held_out_rows.append(
            {
                "held_out_fold": held_out_fold + 1,
                "selected_on_other_folds": candidate_ids[selected_index],
                "held_out_sharpe": _round(selected_value),
                "held_out_percentile": _round(percentile),
                "below_or_at_median": failed,
            }
        )
    pbo_proxy = failures / OUTER_FOLDS
    passed = pbo_proxy <= PBO_GATE and dsr_probability >= DSR_PROBABILITY_GATE
    return {
        "candidate_count": trials,
        "selected_by_aggregate_sharpe": leader_id,
        "selected_sharpe": _round(aggregate_sharpes[leader_index]),
        "expected_max_sharpe": _round(expected_max_daily * math.sqrt(252.0)),
        "selected_return_skew": _round(skew),
        "selected_return_kurtosis": _round(kurtosis),
        "observation_count": observations,
        "deflated_sharpe_probability": _round(dsr_probability),
        "deflated_sharpe_probability_gate": DSR_PROBABILITY_GATE,
        "pbo_proxy": _round(pbo_proxy),
        "pbo_proxy_gate": PBO_GATE,
        "pbo_definition": (
            "leave_one_chronological_fold_out_select_on_other_three_then_rank_held_out"
        ),
        "held_out_selection_rows": held_out_rows,
        "pass": passed,
        "limitations": (
            "Five-candidate four-fold chronology-aware proxy; not full CSCV and not a "
            "complete correction for serial dependence."
        ),
    }


def _daily_contract_checks(
    targets: dict[str, R7Targets],
    panel: R6Panel,
    features: R6DailyFeatures,
) -> dict[str, Any]:
    schedule_hashes = {
        candidate_id: _canonical_sha(
            [
                session.isoformat()
                for session, selected in candidate_targets.decision_mask.items()
                if bool(selected)
            ]
        )
        for candidate_id, candidate_targets in targets.items()
    }
    target_maxima = {
        candidate_id: _round(
            float(candidate_targets.weights.loc[candidate_targets.decision_mask].max().max())
        )
        for candidate_id, candidate_targets in targets.items()
    }
    gross_maxima = {
        candidate_id: _round(
            float(candidate_targets.weights.loc[candidate_targets.decision_mask].sum(axis=1).max())
        )
        for candidate_id, candidate_targets in targets.items()
    }
    checks = {
        "all_candidates_share_decision_schedule": len(set(schedule_hashes.values())) == 1,
        "all_rebalance_targets_respect_40pct_cap": all(
            value is not None and value <= POSITION_CAP + 1e-9 for value in target_maxima.values()
        ),
        "all_rebalance_targets_respect_gross_limit": all(
            value is not None and value <= 1.0 + 1e-9 for value in gross_maxima.values()
        ),
        "strict_daily_data_reaches_July_2026": panel.daily_sessions[-1] >= date(2026, 7, 1),
        "terminal_session_is_last_strict_common_open": panel.daily_sessions[-1]
        == date.fromisoformat("2026-07-17"),
        "evaluation_anchor_is_feature_complete": features.evaluation_start
        in set(panel.daily_sessions),
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "schedule_hashes": schedule_hashes,
        "maximum_rebalance_target_weights": target_maxima,
        "maximum_rebalance_gross_exposures": gross_maxima,
        "position_cap_semantics": "rebalance_target_only_natural_drift_allowed",
    }


def _verify_r7_preregistration(root: Path) -> None:
    dossier = validate_iteration_dossier(ITER_ID, root, stage="pre-backtest")
    if not dossier.ok:
        raise R7ContractViolation(
            "R7 pre-backtest dossier gate failed: " + ", ".join(dossier.blocked)
        )
    search = _load_json(root / SEARCH_SPACE_PATH)
    manifest = _load_json(root / CANDIDATE_MANIFEST_PATH)
    if search.get("candidate_manifest_sha256") != _sha256_file(root / CANDIDATE_MANIFEST_PATH):
        raise R7ContractViolation("R7 candidate manifest hash mismatch")
    if search.get("data_feasibility_sha256") != _sha256_file(root / DATA_FEASIBILITY_PATH):
        raise R7ContractViolation("R7 data feasibility hash mismatch")
    spec = load_strategy_spec(root / SPEC_PATH)
    if search.get("spec_hash") != strategy_content_hash(spec):
        raise R7ContractViolation("R7 StrategySpec hash mismatch")
    candidate_ids = tuple(str(row["candidate_id"]) for row in manifest["candidates"])
    if candidate_ids != EXPECTED_CANDIDATE_IDS:
        raise R7ContractViolation("R7 candidate ID accounting or order changed")
    panel = _load_json(root / PANEL_MANIFEST_PATH)
    generator = panel.get("generator", {})
    if generator.get("sha256") != _sha256_file(root / RUNNER_PATH):
        raise R7ContractViolation("R7 runner changed after preregistration")
    if generator.get("data_feature_dependency_sha256") != _sha256_file(root / R6_DEPENDENCY_PATH):
        raise R7ContractViolation("R7 data-feature dependency changed after preregistration")
    _verify_r7_panel_manifest(root)


def _verify_r7_panel_manifest(root: Path) -> None:
    manifest = _load_json(root / PANEL_MANIFEST_PATH)
    if manifest.get("adjustment") != "all" or manifest.get("fallback_used") is not False:
        raise R7ContractViolation("R7 panel adjustment or fallback contract changed")
    if manifest.get("forward_fill_allowed") is not False:
        raise R7ContractViolation("R7 panel allows forward fill")
    if manifest.get("zero_return_substitution_allowed") is not False:
        raise R7ContractViolation("R7 panel allows zero-return substitution")
    _verify_source_panel_files(root, manifest)
    for key, count_key in (
        ("daily", "strict_common_session_count"),
        ("intraday", "strict_common_complete_session_count"),
    ):
        section = manifest.get(key, {})
        sessions = section.get("included_sessions")
        if not isinstance(sessions, list) or len(sessions) != section.get(count_key):
            raise R7ContractViolation(f"R7 {key} session membership mismatch")
        if section.get("included_sessions_sha256") != _canonical_sha(sessions):
            raise R7ContractViolation(f"R7 {key} session hash mismatch")


def _verify_source_panel_files(root: Path, manifest: dict[str, Any]) -> None:
    receipt = manifest.get("refresh_receipt", {})
    receipt_path = root / str(receipt.get("path") or "")
    if not receipt_path.exists() or receipt.get("sha256") != _sha256_file(receipt_path):
        raise R7ContractViolation("R7 source refresh receipt mismatch")
    for row in manifest.get("input_files", []):
        path = root / str(row.get("path") or "")
        if not path.exists() or row.get("sha256") != _sha256_file(path):
            raise R7ContractViolation(f"R7 source input hash mismatch: {path}")


def _public_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "net_returns"}


def _skipped_result(candidate_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "status": "skipped_dependency",
        "reason_code": reason_code,
        "selection_prohibited": True,
        "cost_scenarios": None,
    }


def _render_r7_evaluation(payload: dict[str, Any]) -> str:
    leader = payload["diagnostic_leader"]
    lines = [
        "# R7 Core-Satellite Evaluation",
        "",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Historical candidate gate pass: `{payload['historical_candidate_gate_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- LLM contribution pass: `{payload['llm_contribution_pass']}`",
        f"- Paper-ready pass: `{payload['paper_ready_pass']}`",
        f"- Diagnostic leader: `{leader['candidate_id'] or 'none'}`",
        "- Formal-forward observations: "
        f"`{payload['data_scope']['formal_forward_observation_count']}`",
        "",
        "## Candidate Results At 10 bps One-Way",
        "",
        "| Candidate | Status | Total return | Sharpe | Max drawdown | Positive folds | Turnover |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["candidate_results"]:
        if row["status"] != "completed":
            lines.append(
                f"| {row['candidate_id']} | {row['status']} | n/a | n/a | n/a | n/a | n/a |"
            )
            continue
        ten = row["cost_scenarios"]["10bps"]
        aggregate = ten["aggregate"]
        lines.append(
            (
                "| {candidate} | completed | {total}% | {sharpe} | {drawdown}% "
                "| {folds}/4 | {turnover} |"
            ).format(
                candidate=row["candidate_id"],
                total=aggregate["total_return_pct"],
                sharpe=aggregate["sharpe"],
                drawdown=aggregate["max_drawdown_pct"],
                folds=ten["positive_fold_count"],
                turnover=aggregate["turnover_units"],
            )
        )
    lines.extend(
        [
            "",
            "## Frozen Controls",
            "",
            "- Self-financing and target-cap contract pass: "
            f"`{payload['contract_checks']['pass']}`",
            "- Exact D04/D06 schedule and session match: "
            f"`{payload['intraday_contract']['exact_schedule_match']}`",
            "- Permutation distribution pass: "
            f"`{payload['negative_controls']['permutation_distribution']['pass']}`",
            "- Future packet rejection pass: "
            f"`{payload['negative_controls']['future_packet']['pass']}`",
            f"- PBO proxy: `{payload['overfit_diagnostics']['pbo_proxy']}` "
            f"(gate `{payload['overfit_diagnostics']['pbo_proxy_gate']}`)",
            "- Deflated Sharpe probability: "
            f"`{payload['overfit_diagnostics']['deflated_sharpe_probability']}` "
            f"(gate `{payload['overfit_diagnostics']['deflated_sharpe_probability_gate']}`)",
            "- Event candidates use no fixture or retrospective LLM substitute.",
            (
                "- IEX results remain diagnostic until SIP or official-open parity and "
                "matched TCA exist."
            ),
            "- No candidate has broker order authority.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _source_credibility(source_type: str) -> str:
    return {
        "paper": "primary academic or peer-reviewed methodology source",
        "broker_official_docs": "official broker documentation reviewed on 2026-07-19",
        "provider_official_docs": "official data-provider documentation reviewed on 2026-07-19",
        "regulatory_docs": "official regulatory source reviewed on 2026-07-19",
        "exchange_official_docs": "official exchange documentation reviewed on 2026-07-19",
    }.get(source_type, "verified primary source")


def _load_source_cards(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise R7ContractViolation(f"R7 source cards missing: {path}")
    rows = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise R7ContractViolation(f"invalid source card line {line_number}") from exc
        required = {
            "claim_id",
            "claim",
            "source_url",
            "source_type",
            "accessed_at",
            "applies_to",
            "impact_on_spec",
            "limitations",
        }
        missing = sorted(field for field in required if row.get(field) in (None, "", []))
        if missing:
            raise R7ContractViolation(
                f"source card line {line_number} missing: {','.join(missing)}"
            )
        rows.append(row)
    if f"{STRATEGY_NAME}:source-research" not in {str(row["claim_id"]) for row in rows}:
        raise R7ContractViolation("R7 required source-research claim is missing")
    return rows


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise R7FeatureAvailabilityError("packet timestamp must include timezone")
    return parsed.astimezone(UTC)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise R7ContractViolation(f"required R7 artifact missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise R7ContractViolation(f"R7 artifact is not an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cost_key(value: float) -> str:
    return f"{int(value)}bps" if float(value).is_integer() else f"{value:g}bps"


def _metric_value(
    payload: dict[str, Any],
    key: str,
    default: float,
) -> float:
    value = payload.get(key)
    if value is None:
        return float(default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if math.isfinite(parsed) else float(default)


def _round(value: float | None, digits: int = 6) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return round(parsed, digits) if math.isfinite(parsed) else None


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
