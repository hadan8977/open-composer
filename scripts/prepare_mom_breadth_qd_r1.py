# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from open_composer.market_calendar import us_equity_session_dates
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.factor_library import write_factor_library_artifact
from open_composer.research.iteration_dossier import candidate_authorization_binding_sha256
from open_composer.research.knowledge_memory import canonical_source_url, claim_fingerprint
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

CAMPAIGN_ID = "mom_breadth_qd_r1"
GENERATOR_PATH = Path("scripts/prepare_mom_breadth_qd_r1.py")
DEVELOPMENT_RUNNER_PATH = Path("open_composer/research/mom_breadth_qd_r1.py")
DEVELOPMENT_RUNNER_TEST_PATH = Path("tests/test_mom_breadth_qd_r1.py")
DEVELOPMENT_IMPLEMENTATION_PATHS = {
    "campaign_implementation": Path("open_composer/research/campaign.py"),
    "campaign_statistics_implementation": Path("open_composer/research/campaign_statistics.py"),
    "iteration_dossier_implementation": Path("open_composer/research/iteration_dossier.py"),
    "market_calendar_implementation": Path("open_composer/market_calendar.py"),
    "quality_diversity_implementation": Path("open_composer/research/quality_diversity.py"),
    "storage_implementation": Path("open_composer/storage.py"),
    "strategy_spec_implementation": Path("open_composer/models/strategy_spec.py"),
    "python_project": Path("pyproject.toml"),
    "python_lock": Path("uv.lock"),
}
CAMPAIGN_PATH = Path("reports/research/campaigns") / CAMPAIGN_ID / "research-campaign-contract.json"
SOURCE_CARDS_PATH = Path("reports/harness/source_cards") / f"{CAMPAIGN_ID}.jsonl"
BRANCH_SOURCE_EVIDENCE_PATH = (
    Path("reports/research/campaigns") / CAMPAIGN_ID / "branch-source-evidence.jsonl"
)
INTEGRITY_AMENDMENT_PATH = (
    Path("reports/research/campaigns") / CAMPAIGN_ID / "development-integrity-repair-amendment.json"
)
INTEGRITY_RECEIPT_PATH = (
    Path("reports/research/campaigns") / CAMPAIGN_ID / "development-integrity-repair-receipt.json"
)
FACTOR_LIBRARY_PATH = Path("reports/research/mom_breadth_qd_r1-factor-library.json")
DEVELOPMENT_DATA_ROOT = Path("data/research/mom_breadth_qd_r1_development")
STRUCTURAL_SOURCE_ROOT = Path("data/research/alpaca_etf_structural_r9")
LEVERAGED_SOURCE_ROOT = Path("data/research/alpaca_pit_price_adjustment_repair_20260804")
PRICE_SNAPSHOT_PATH = DEVELOPMENT_DATA_ROOT / "structural/snapshot-manifest.json"
LEVERAGED_SNAPSHOT_PATH = DEVELOPMENT_DATA_ROOT / "leveraged/snapshot-manifest.json"
STATIC_CONTROL_SNAPSHOT_PATH = DEVELOPMENT_DATA_ROOT / "static/snapshot-manifest.json"
EXCHANGE_CALENDAR_PATH = DEVELOPMENT_DATA_ROOT / "us-equity-session-calendar.json"
PROMOTION_BENCHMARK_DATA_ARTIFACTS = [LEVERAGED_SNAPSHOT_PATH]

PREREGISTERED_AT = "2026-08-15T17:10:00Z"
PRIOR_EFFECTIVE_TRIAL_COUNT = 8147
CAMPAIGN_CANDIDATE_COUNT = 19
CAMPAIGN_EFFECTIVE_TRIAL_COUNT = PRIOR_EFFECTIVE_TRIAL_COUNT + CAMPAIGN_CANDIDATE_COUNT
PRIMARY_COST_BPS = 20
STRESS_COST_BPS = [10, 20, 40]
PORTFOLIO_RETURN_IDENTITY = "open_t_to_open_t_plus_1_simple_return_net_of_turnover_cost"
DEVELOPMENT_START = "2017-02-01"
DEVELOPMENT_TRAIN_END = "2020-12-31"
DEVELOPMENT_VALIDATION_START = "2021-01-04"
DEVELOPMENT_VALIDATION_END = "2023-12-29"
STATIC_CONTROL_DEVELOPMENT_START = "2020-07-27"
FROZEN_OOS_START = "2024-01-02"
FROZEN_OOS_END = "2025-12-31"
CHALLENGE_START = "2026-01-02"
CHALLENGE_END = "2026-07-17"

BENCHMARK_FAMILY = [
    "same_symbol_buy_and_hold",
    "equal_weight_full_spec_universe",
    "SPY_buy_and_hold_market_proxy",
    "QQQ_buy_and_hold_growth_proxy",
    "XLK_buy_and_hold_sector_theme_proxy",
    "BIL_buy_and_hold_cash_proxy",
    "TQQQ_buy_and_hold_leveraged_growth_proxy",
    "ex_post_best_symbol_report_only",
]

TRIAL_ACCOUNTING_IDENTITY_KEYS = (
    "prior_effective_trial_count",
    "campaign_candidate_count",
    "minimum_incremental_trial_count",
    "campaign_trial_exposure_budget",
    "minimum_effective_trial_count",
    "maximum_effective_trial_count",
    "effective_trial_count_source",
)


def _trial_accounting_identity(campaign: dict[str, Any]) -> dict[str, Any]:
    budgets = campaign["exposure_budgets"]
    prior = int(budgets["prior_effective_trial_count"])
    candidate_count = int(budgets["candidate_budget"])
    exposure_budget = int(budgets["cumulative_trial_exposure_budget"])
    if prior != PRIOR_EFFECTIVE_TRIAL_COUNT:
        raise ValueError("campaign prior effective trial count drift")
    if candidate_count != CAMPAIGN_CANDIDATE_COUNT:
        raise ValueError("campaign candidate count drift")
    if exposure_budget < candidate_count:
        raise ValueError("campaign trial exposure budget is below candidate count")
    return {
        "prior_effective_trial_count": prior,
        "campaign_candidate_count": candidate_count,
        "minimum_incremental_trial_count": candidate_count,
        "campaign_trial_exposure_budget": exposure_budget,
        "minimum_effective_trial_count": prior + candidate_count,
        "maximum_effective_trial_count": prior + exposure_budget,
        "effective_trial_count_source": "campaign_pre_oos_seal",
    }


COMMON_SOURCE_IDS = [
    "breadth_qd_map_elites",
    "breadth_qd_hyperband_boundary",
    "breadth_qd_pbo",
    "breadth_qd_dsr",
    "breadth_qd_spa",
    "breadth_qd_factor_multiple_testing",
    "breadth_qd_simple_allocation_benchmark",
]

FACTOR_LIBRARY_IDS = [
    "absolute_time_series_momentum_120",
    "cross_sectional_relative_momentum_120",
    "defensive_asset_dual_momentum",
    "drawdown_guard_20_60",
    "overextension_mean_reversion_guard",
    "overnight_intraday_return_split",
    "volatility_managed_leverage_state",
]

STATIC_CONTROL_SYMBOLS = ["AAPL", "AMZN", "AVGO", "GOOGL", "META", "MSFT", "NFLX"]
STATIC_CONTROL_FILES = [
    *(Path(f"data/cache/{symbol.lower()}_daily_iex.csv") for symbol in STATIC_CONTROL_SYMBOLS),
    Path("data/cache/bil_daily_iex.csv"),
]
STRUCTURAL_DEVELOPMENT_SYMBOLS = [
    "SPY",
    "QQQ",
    "IEF",
    "GLD",
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "BIL",
]
LEVERAGED_DEVELOPMENT_SYMBOLS = ["SPY", "QQQ", "QLD", "TQQQ", "GLD", "XLK", "BIL"]

BRANCHES: dict[str, dict[str, Any]] = {
    "mom_breadth_pit_xsmom_r1": {
        "strategy_stem": "us_breadth_pit_xsmom_r1",
        "hypothesis_id": "H1_PIT_XSMOM",
        "path": "pit_cross_sectional_momentum",
        "universe_selection": "point_in_time",
        "contract_status": "dependency_skipped",
        "symbols": ["BIL"],
        "primary_symbol": "BIL",
        "data_path": PRICE_SNAPSHOT_PATH,
        "data_artifacts": [PRICE_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_cross_sectional_momentum",
            "breadth_qd_pit_equity_requirement",
            "breadth_qd_delisting_return_bias",
        ],
        "factor_library_ids": ["cross_sectional_relative_momentum_120"],
        "feature_expressions": {
            "momentum_252_skip21": "lag(close, 21) / lag(close, 252) - 1",
            "momentum_126_skip21": "lag(close, 21) / lag(close, 126) - 1",
            "realized_volatility_63": "stddev(close / lag(close, 1) - 1, 63)",
        },
        "blockers": [
            "point_in_time_US_equity_membership_with_inactive_and_delisted_securities_is_not_configured",
            "permanent_security_identity_corporate_actions_and_delisting_returns_are_unavailable",
            "current_stock_lists_and_static_2026_membership_are_forbidden_substitutes",
        ],
        "objective": "Test long-only cross-sectional continuation only after a valid-time US equity membership panel with inactive names and delisting returns exists.",
    },
    "mom_breadth_crossasset_trend_r1": {
        "strategy_stem": "us_breadth_crossasset_trend_r1",
        "hypothesis_id": "H2_CROSSASSET_TREND",
        "path": "cross_asset_time_series_trend",
        "universe_selection": "cross_asset",
        "contract_status": "ready",
        "symbols": ["SPY", "QQQ", "IEF", "GLD", "BIL"],
        "primary_symbol": "SPY",
        "data_path": PRICE_SNAPSHOT_PATH,
        "data_artifacts": [PRICE_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_time_series_momentum",
            "breadth_qd_century_trend_evidence",
        ],
        "factor_library_ids": [
            "absolute_time_series_momentum_120",
            "defensive_asset_dual_momentum",
        ],
        "feature_expressions": {
            "trend_63": "close / lag(close, 63) - 1",
            "trend_126": "close / lag(close, 126) - 1",
            "trend_252": "close / lag(close, 252) - 1",
            "realized_volatility_20": "stddev(close / lag(close, 1) - 1, 20)",
            "breakout_55": "close / highest(close, 55) - 1",
            "exit_channel_20": "close / lowest(close, 20) - 1",
        },
        "objective": "Compare absolute trend, multihorizon voting, and breakout rules across equity, Treasury, gold, and cash-like ETFs.",
    },
    "mom_breadth_short_reversal_r1": {
        "strategy_stem": "us_breadth_short_reversal_r1",
        "hypothesis_id": "H3_SHORT_REVERSAL",
        "path": "short_horizon_reversal",
        "universe_selection": "fixed_long_lived",
        "contract_status": "ready",
        "symbols": [
            "SPY",
            "QQQ",
            "XLB",
            "XLE",
            "XLF",
            "XLI",
            "XLK",
            "XLP",
            "XLU",
            "XLV",
            "XLY",
            "BIL",
        ],
        "primary_symbol": "SPY",
        "data_path": PRICE_SNAPSHOT_PATH,
        "data_artifacts": [PRICE_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_short_horizon_reversal",
            "breadth_qd_reversal_liquidity_state",
        ],
        "factor_library_ids": ["overextension_mean_reversion_guard"],
        "feature_expressions": {
            "return_5": "close / lag(close, 5) - 1",
            "trend_gap_200": "close / sma(close, 200) - 1",
            "rsi_7": "rsi(close, 7)",
            "volume_shock_20": "volume / sma(volume, 20) - 1",
        },
        "objective": "Test short-horizon long-only reversal only inside a positive long trend and after explicit turnover costs.",
    },
    "mom_breadth_cross_session_r1": {
        "strategy_stem": "us_breadth_cross_session_r1",
        "hypothesis_id": "H4_CROSS_SESSION",
        "path": "overnight_intraday_decomposition",
        "universe_selection": "fixed_long_lived",
        "contract_status": "ready",
        "symbols": ["SPY", "QQQ", "XLE", "XLF", "XLK", "XLV", "BIL"],
        "primary_symbol": "QQQ",
        "data_path": PRICE_SNAPSHOT_PATH,
        "data_artifacts": [PRICE_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_cross_session_returns",
            "breadth_qd_open_attention_reversal_cost",
        ],
        "factor_library_ids": ["overnight_intraday_return_split"],
        "feature_expressions": {
            "overnight_return": "open / lag(close, 1) - 1",
            "intraday_return": "close / open - 1",
            "trend_20": "close / lag(close, 20) - 1",
            "realized_volatility_20": "stddev(close / lag(close, 1) - 1, 20)",
            "volume_ratio_20": "volume / sma(volume, 20)",
        },
        "objective": "Keep overnight and regular-session returns separate and test only decision-time-safe next-session rules.",
    },
    "mom_breadth_volatility_beta_r1": {
        "strategy_stem": "us_breadth_volatility_beta_r1",
        "hypothesis_id": "H5_VOLATILITY_BETA",
        "path": "volatility_managed_beta",
        "universe_selection": "cross_asset",
        "contract_status": "ready",
        "symbols": ["SPY", "QQQ", "QLD", "TQQQ", "GLD", "BIL"],
        "primary_symbol": "QQQ",
        "data_path": LEVERAGED_SNAPSHOT_PATH,
        "data_artifacts": [LEVERAGED_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_volatility_management",
            "breadth_qd_leveraged_etf_path_dependence",
        ],
        "factor_library_ids": ["volatility_managed_leverage_state", "drawdown_guard_20_60"],
        "feature_expressions": {
            "realized_volatility_20": "stddev(close / lag(close, 1) - 1, 20)",
            "realized_volatility_63": "stddev(close / lag(close, 1) - 1, 63)",
            "drawdown_63": "close / highest(close, 63) - 1",
            "trend_gap_200": "close / sma(close, 200) - 1",
        },
        "objective": "Test volatility-scaled allocation and a discrete QQQ/QLD/TQQQ beta ladder without introducing trained models.",
    },
    "mom_breadth_calendar_flow_r1": {
        "strategy_stem": "us_breadth_calendar_flow_r1",
        "hypothesis_id": "H6_CALENDAR_FLOW",
        "path": "calendar_boundary_flow",
        "universe_selection": "fixed_long_lived",
        "contract_status": "ready",
        "symbols": ["SPY", "QQQ", "BIL"],
        "primary_symbol": "QQQ",
        "data_path": PRICE_SNAPSHOT_PATH,
        "data_artifacts": [PRICE_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_calendar_seasonality",
            "breadth_qd_turn_of_month_replication",
            "breadth_qd_nyse_session_calendar",
        ],
        "factor_library_ids": [],
        "feature_expressions": {
            "return_1": "close / lag(close, 1) - 1",
            "trend_63": "close / lag(close, 63) - 1",
        },
        "objective": "Test exactly three exchange-session calendar windows against always-defined neutral and buy-and-hold baselines.",
    },
    "mom_breadth_static_hotspot_control_r1": {
        "strategy_stem": "us_breadth_static_hotspot_control_r1",
        "hypothesis_id": "H7_STATIC_HOTSPOT_CONTROL",
        "path": "static_hotspot_survivorship_control",
        "universe_selection": "static_hotspot_control",
        "contract_status": "ready",
        "symbols": [*STATIC_CONTROL_SYMBOLS, "BIL"],
        "primary_symbol": "AAPL",
        "data_path": STATIC_CONTROL_SNAPSHOT_PATH,
        "data_artifacts": [STATIC_CONTROL_SNAPSHOT_PATH],
        "source_ids": [
            *COMMON_SOURCE_IDS,
            "breadth_qd_survivorship_false_predictability",
            "breadth_qd_survivor_conditioning_performance",
        ],
        "factor_library_ids": ["cross_sectional_relative_momentum_120"],
        "feature_expressions": {
            "momentum_252_skip21": "lag(close, 21) / lag(close, 252) - 1",
        },
        "objective": "Measure, but never promote, the apparent benefit of projecting a current successful-stock basket backward through history.",
    },
}

COMMON_POLICY = {
    "schema_version": 1,
    "decision_timestamp": "completed_regular_session_close",
    "execution_timestamp": "next_regular_session_open",
    "feature_lag_sessions": 1,
    "fallback_symbol": "BIL",
    "gross_exposure_limit": 1.0,
    "long_only": True,
    "terminal_liquidation_in_metrics": False,
}

CANDIDATE_POLICIES: dict[str, dict[str, Any]] = {
    "PIT01": {
        **COMMON_POLICY,
        "policy_type": "pit_cross_sectional_rank",
        "rebalance_frequency": "month_end",
        "required_features": ["momentum_252_skip21"],
        "signal_parameters": {"ranking": "descending", "top_fraction": 0.10},
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.10},
        "required_data": [
            "point_in_time_membership",
            "permanent_security_identity",
            "delisting_returns",
            "corporate_actions",
            "then_visible_liquidity",
        ],
    },
    "PIT02": {
        **COMMON_POLICY,
        "policy_type": "pit_cross_sectional_rank",
        "rebalance_frequency": "month_end",
        "required_features": [
            "momentum_126_skip21",
            "momentum_252_skip21",
            "realized_volatility_63",
        ],
        "signal_parameters": {
            "score": "mean_momentum_126_252_divided_by_volatility_63",
            "ranking": "descending",
            "top_fraction": 0.20,
        },
        "allocation_parameters": {
            "method": "inverse_volatility_63",
            "max_weight": 0.10,
        },
        "required_data": [
            "point_in_time_membership",
            "permanent_security_identity",
            "delisting_returns",
            "corporate_actions",
            "then_visible_liquidity",
        ],
    },
    "PIT03": {
        **COMMON_POLICY,
        "policy_type": "pit_residual_momentum_rank",
        "rebalance_frequency": "month_end",
        "required_features": ["momentum_252_skip21", "rolling_spy_beta_126"],
        "signal_parameters": {
            "score": "beta_residualized_momentum_252_skip21",
            "ranking": "descending",
            "top_fraction": 0.20,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.10},
        "required_data": [
            "point_in_time_membership",
            "permanent_security_identity",
            "delisting_returns",
            "corporate_actions",
            "then_visible_liquidity",
        ],
    },
    "TSM01": {
        **COMMON_POLICY,
        "policy_type": "absolute_trend_allocation",
        "rebalance_frequency": "month_end",
        "required_features": ["trend_252", "realized_volatility_20"],
        "signal_parameters": {"eligible_when": "trend_252_gt_0"},
        "allocation_parameters": {
            "method": "inverse_volatility_20",
            "risk_assets": ["SPY", "QQQ", "IEF", "GLD"],
            "max_weight": 0.40,
        },
    },
    "TSM02": {
        **COMMON_POLICY,
        "policy_type": "multihorizon_trend_vote",
        "rebalance_frequency": "weekly_last_session",
        "required_features": [
            "trend_63",
            "trend_126",
            "trend_252",
            "realized_volatility_20",
        ],
        "signal_parameters": {"positive_votes_required": 2, "total_votes": 3},
        "allocation_parameters": {
            "method": "inverse_volatility_20",
            "risk_assets": ["SPY", "QQQ", "IEF", "GLD"],
            "max_weight": 0.40,
        },
    },
    "TSM03": {
        **COMMON_POLICY,
        "policy_type": "stateful_breakout_channel",
        "rebalance_frequency": "weekly_last_session",
        "required_features": ["breakout_55", "exit_channel_20"],
        "signal_parameters": {
            "entry": "close_at_55_session_high",
            "exit": "close_at_20_session_low",
            "stateful": True,
        },
        "allocation_parameters": {
            "method": "equal_weight_active_signals",
            "risk_assets": ["SPY", "QQQ", "IEF", "GLD"],
            "max_weight": 0.40,
        },
    },
    "REV01": {
        **COMMON_POLICY,
        "policy_type": "cross_sectional_loser_recovery",
        "rebalance_frequency": "daily",
        "required_features": ["return_5", "trend_gap_200"],
        "signal_parameters": {
            "return_5_max": -0.03,
            "trend_gap_200_min": 0.0,
            "select_worst_count": 3,
            "max_holding_sessions": 5,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.34},
    },
    "REV02": {
        **COMMON_POLICY,
        "policy_type": "rsi_recovery_confirmation",
        "rebalance_frequency": "daily",
        "required_features": ["rsi_7", "trend_gap_200"],
        "signal_parameters": {
            "prior_rsi_max": 30.0,
            "current_rsi_min": 30.0,
            "trend_gap_200_min": 0.0,
            "exit_rsi_min": 55.0,
            "max_holding_sessions": 5,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.34},
    },
    "REV03": {
        **COMMON_POLICY,
        "policy_type": "volume_shock_reversal",
        "rebalance_frequency": "daily",
        "required_features": ["return_5", "trend_gap_200", "volume_shock_20"],
        "signal_parameters": {
            "return_5_max": -0.04,
            "volume_shock_min": 0.50,
            "trend_gap_200_min": 0.0,
            "max_holding_sessions": 3,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.34},
    },
    "SES01": {
        **COMMON_POLICY,
        "policy_type": "lagged_overnight_gap_fade",
        "rebalance_frequency": "daily",
        "required_features": ["overnight_return", "volume_ratio_20"],
        "signal_parameters": {
            "completed_session_gap_max": -0.01,
            "volume_ratio_min": 1.0,
            "holding_sessions": 1,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.34},
    },
    "SES02": {
        **COMMON_POLICY,
        "policy_type": "lagged_gap_trend_continuation",
        "rebalance_frequency": "daily",
        "required_features": ["overnight_return", "trend_20"],
        "signal_parameters": {
            "completed_session_gap_min": 0.005,
            "trend_20_min": 0.0,
            "holding_sessions": 1,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.34},
    },
    "SES03": {
        **COMMON_POLICY,
        "policy_type": "intraday_loss_next_session_recovery",
        "rebalance_frequency": "daily",
        "required_features": ["intraday_return", "trend_20"],
        "signal_parameters": {
            "completed_session_intraday_return_max": -0.01,
            "trend_20_min": 0.0,
            "holding_sessions": 1,
        },
        "allocation_parameters": {"method": "equal_weight", "max_weight": 0.34},
    },
    "VOL01": {
        **COMMON_POLICY,
        "policy_type": "cross_asset_inverse_volatility",
        "rebalance_frequency": "weekly_last_session",
        "required_features": ["realized_volatility_20", "trend_gap_200"],
        "signal_parameters": {"trend_gap_200_min": 0.0},
        "allocation_parameters": {
            "method": "inverse_volatility_20",
            "risk_assets": ["SPY", "QQQ", "GLD"],
            "max_weight": 0.50,
        },
    },
    "VOL02": {
        **COMMON_POLICY,
        "policy_type": "discrete_beta_ladder",
        "rebalance_frequency": "weekly_last_session",
        "required_features": ["realized_volatility_20", "trend_gap_200"],
        "signal_parameters": {
            "annualization_sessions": 252,
            "risk_off_when_trend_gap_200_lte": 0.0,
            "tqqq_when_annualized_vol_lte": 0.12,
            "qld_when_annualized_vol_lte": 0.20,
            "otherwise": "QQQ",
        },
        "allocation_parameters": {
            "method": "single_sleeve",
            "sleeves": ["BIL", "QQQ", "QLD", "TQQQ"],
        },
    },
    "VOL03": {
        **COMMON_POLICY,
        "policy_type": "volatility_drawdown_state_switch",
        "rebalance_frequency": "weekly_last_session",
        "required_features": [
            "realized_volatility_20",
            "realized_volatility_63",
            "drawdown_63",
            "trend_gap_200",
        ],
        "signal_parameters": {
            "stress_vol_ratio_min": 1.25,
            "stress_drawdown_max": -0.12,
            "risk_on_drawdown_min": -0.08,
            "risk_on_trend_gap_min": 0.0,
        },
        "allocation_parameters": {
            "method": "single_sleeve_state_machine",
            "risk_on": "TQQQ",
            "transition": "QQQ",
            "stress": "BIL",
        },
    },
    "CAL01": {
        **COMMON_POLICY,
        "policy_type": "exchange_session_calendar_window",
        "rebalance_frequency": "daily",
        "required_features": ["exchange_session_calendar"],
        "signal_parameters": {"relative_month_session_offsets": [-1, 0, 1, 2]},
        "allocation_parameters": {"method": "single_sleeve", "risk_asset": "QQQ"},
    },
    "CAL02": {
        **COMMON_POLICY,
        "policy_type": "exchange_session_calendar_window",
        "rebalance_frequency": "daily",
        "required_features": ["exchange_session_calendar"],
        "signal_parameters": {"last_sessions_of_month": 5},
        "allocation_parameters": {"method": "single_sleeve", "risk_asset": "QQQ"},
    },
    "CAL03": {
        **COMMON_POLICY,
        "policy_type": "exchange_session_calendar_window",
        "rebalance_frequency": "daily",
        "required_features": ["exchange_session_calendar"],
        "signal_parameters": {
            "last_sessions_of_quarter": 3,
            "first_sessions_of_quarter": 2,
        },
        "allocation_parameters": {"method": "single_sleeve", "risk_asset": "QQQ"},
    },
    "CTL01": {
        **COMMON_POLICY,
        "policy_type": "static_hotspot_cross_sectional_rank_control",
        "rebalance_frequency": "month_end",
        "required_features": ["momentum_252_skip21"],
        "signal_parameters": {"ranking": "descending", "select_count": 3},
        "allocation_parameters": {"method": "equal_weight", "max_weight": 1 / 3},
        "promotion_eligible": False,
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _binding(path: Path, root: Path) -> dict[str, str]:
    absolute = root / path
    if not absolute.is_file():
        raise FileNotFoundError(path)
    return {"path": path.as_posix(), "sha256": _sha256(absolute)}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"expected object rows: {path}")
    return rows


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def _bounded_development_csv(
    source: Path,
    *,
    start_session: str = DEVELOPMENT_START,
) -> tuple[bytes, dict[str, Any]]:
    lines: list[bytes] = []
    first_session: str | None = None
    last_session: str | None = None
    row_count = 0
    end_found = False
    with source.open("rb") as handle:
        header = handle.readline()
        if not header.startswith(b"timestamp,"):
            raise ValueError(f"development slice source schema mismatch: {source}")
        lines.append(header)
        for raw_line in handle:
            timestamp = raw_line.split(b",", maxsplit=1)[0].decode("ascii")
            session = date.fromisoformat(timestamp[:10]).isoformat()
            if session < start_session:
                continue
            if session > DEVELOPMENT_VALIDATION_END:
                raise ValueError(f"development slice source misses declared end: {source}")
            lines.append(raw_line)
            first_session = first_session or session
            last_session = session
            row_count += 1
            if session == DEVELOPMENT_VALIDATION_END:
                end_found = True
                break
    if not end_found or first_session != start_session:
        raise ValueError(f"development slice has incomplete declared bounds: {source}")
    payload = b"".join(lines)
    return payload, {
        "row_count": row_count,
        "first_session": first_session,
        "last_session": last_session,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_development_snapshot(
    root: Path,
    *,
    dataset_id: str,
    destination: Path,
    sources: dict[str, Path],
    feed: str,
    first_session: str,
    feed_by_symbol: dict[str, str] | None = None,
) -> None:
    output_root = root / destination.parent
    output_root.mkdir(parents=True, exist_ok=True)
    items = []
    for symbol, source_path in sorted(sources.items()):
        item_feed = (feed_by_symbol or {}).get(symbol, feed)
        payload, metadata = _bounded_development_csv(
            root / source_path,
            start_session=first_session,
        )
        filename = f"{symbol.lower()}_1d_{item_feed}_all_development.csv"
        output = output_root / filename
        if output.exists() and output.read_bytes() != payload:
            raise ValueError(f"refusing to overwrite development slice drift: {output}")
        if not output.exists():
            output.write_bytes(payload)
        items.append(
            {
                "symbol": symbol,
                "adjustment": "all",
                "feed": item_feed,
                "timeframe": "daily",
                "session_scope": "regular",
                "output_path": filename,
                "output_sha256": metadata["sha256"],
                "row_count": metadata["row_count"],
                "first_timestamp": f"{metadata['first_session']}T00:00:00Z",
                "last_timestamp": f"{metadata['last_session']}T00:00:00Z",
                "source_file_path": source_path.as_posix(),
                "source_bytes_read_through_session": DEVELOPMENT_VALIDATION_END,
            }
        )
    write_json(
        root / destination,
        {
            "schema_version": 1,
            "manifest_type": "development_partition_snapshot_v1",
            "campaign_id": CAMPAIGN_ID,
            "dataset_id": dataset_id,
            "partition_id": "development_train_and_development_validation",
            "first_session": first_session,
            "last_session": DEVELOPMENT_VALIDATION_END,
            "protected_partitions_included": False,
            "future_source_metadata_included": False,
            "derivation": "byte_bounded_source_copy_stop_exactly_at_development_end",
            "items": items,
        },
    )


def _write_development_data_slices(root: Path) -> None:
    sessions = [
        value.isoformat()
        for value in us_equity_session_dates(
            date.fromisoformat(DEVELOPMENT_START),
            date.fromisoformat(DEVELOPMENT_VALIDATION_END),
        )
    ]
    if (
        not sessions
        or sessions[0] != DEVELOPMENT_START
        or sessions[-1] != DEVELOPMENT_VALIDATION_END
    ):
        raise ValueError("US-equity calendar does not match declared development bounds")
    calendar_payload = {
        "schema_version": 1,
        "artifact_type": "us_equity_daily_session_calendar_v1",
        "campaign_id": CAMPAIGN_ID,
        "calendar_id": "XNYS",
        "timezone": "America/New_York",
        "session_label": "exchange_local_date",
        "session_scope": "regular",
        "ruleset_id": "open_composer_us_equity_calendar_v1",
        "ruleset_implementation_path": "open_composer/market_calendar.py",
        "ruleset_implementation_sha256": _sha256(root / "open_composer/market_calendar.py"),
        "requested_start": DEVELOPMENT_START,
        "requested_end": DEVELOPMENT_VALIDATION_END,
        "first_session": sessions[0],
        "last_session": sessions[-1],
        "session_count": len(sessions),
        "sessions": sessions,
        "sessions_sha256": _payload_sha256(sessions),
        "derived_from_price_data": False,
        "protected_partitions_included": False,
        "source_card_claim_id": "breadth_qd_nyse_session_calendar",
    }
    calendar_path = root / EXCHANGE_CALENDAR_PATH
    if calendar_path.exists():
        if _read_json(calendar_path) != calendar_payload:
            raise ValueError(f"refusing to overwrite exchange calendar drift: {calendar_path}")
    else:
        write_json(calendar_path, calendar_payload)
    _write_development_snapshot(
        root,
        dataset_id="alpaca_etf_structural_r9_development_only",
        destination=PRICE_SNAPSHOT_PATH,
        sources={
            symbol: STRUCTURAL_SOURCE_ROOT / f"{symbol.lower()}_1d_alpaca_sip_all.csv"
            for symbol in STRUCTURAL_DEVELOPMENT_SYMBOLS
        },
        feed="sip",
        first_session=DEVELOPMENT_START,
    )
    _write_development_snapshot(
        root,
        dataset_id="alpaca_pit_price_adjustment_repair_development_only",
        destination=LEVERAGED_SNAPSHOT_PATH,
        sources={
            symbol: LEVERAGED_SOURCE_ROOT / f"{symbol.lower()}_1d_alpaca_sip_all.csv"
            for symbol in LEVERAGED_DEVELOPMENT_SYMBOLS
        },
        feed="sip",
        first_session=DEVELOPMENT_START,
    )
    _write_development_snapshot(
        root,
        dataset_id="static_hotspot_iex_control_with_sip_cash_proxy_development_only",
        destination=STATIC_CONTROL_SNAPSHOT_PATH,
        sources={
            **{
                symbol: Path(f"data/cache/{symbol.lower()}_daily_iex.csv")
                for symbol in STATIC_CONTROL_SYMBOLS
            },
            "BIL": STRUCTURAL_SOURCE_ROOT / "bil_1d_alpaca_sip_all.csv",
        },
        feed="iex",
        first_session=STATIC_CONTROL_DEVELOPMENT_START,
        feed_by_symbol={"BIL": "sip"},
    )


def _iteration_dir(iter_id: str) -> Path:
    return Path("reports/research/iterations") / iter_id


def _iteration_source_cards_path(iter_id: str) -> Path:
    return Path("reports/harness/source_cards") / f"{iter_id}.jsonl"


def _spec_path(branch: dict[str, Any], candidate_id: str) -> Path:
    return Path("strategy_specs/drafts") / f"{branch['strategy_stem']}_{candidate_id.lower()}.yaml"


def _contract_id(iter_id: str, kind: str) -> str:
    return f"{iter_id}_{kind}_v1"


def _campaign(root: Path) -> dict[str, Any]:
    campaign = _read_json(root / CAMPAIGN_PATH)
    if campaign.get("campaign_id") != CAMPAIGN_ID:
        raise ValueError("campaign identity mismatch")
    child_ids = list(campaign.get("child_iteration_ids") or [])
    if child_ids != list(BRANCHES):
        raise ValueError("generator branch order does not match campaign child inventory")
    candidates = campaign.get("candidate_blueprints")
    if not isinstance(candidates, list) or len(candidates) != CAMPAIGN_CANDIDATE_COUNT:
        raise ValueError("campaign candidate inventory mismatch")
    candidate_ids = [str(row.get("candidate_id") or "") for row in candidates]
    if len(candidate_ids) != len(set(candidate_ids)) or set(candidate_ids) != set(
        CANDIDATE_POLICIES
    ):
        raise ValueError("candidate policy inventory does not match campaign candidates")
    return campaign


def _branch_candidates(campaign: dict[str, Any], iter_id: str) -> list[dict[str, Any]]:
    rows = [
        row for row in campaign["candidate_blueprints"] if row.get("child_iteration_id") == iter_id
    ]
    if not rows:
        raise ValueError(f"no campaign candidates assigned to {iter_id}")
    return rows


def _source_cards(root: Path) -> dict[str, dict[str, Any]]:
    campaign_rows = _read_jsonl(root / SOURCE_CARDS_PATH)
    branch_rows = _read_jsonl(root / BRANCH_SOURCE_EVIDENCE_PATH)
    rows = [*campaign_rows, *branch_rows]
    by_id = {str(row.get("claim_id") or ""): row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("source-card claim IDs must be nonempty and unique")
    required = {source_id for branch in BRANCHES.values() for source_id in branch["source_ids"]}
    missing = sorted(required - set(by_id))
    if missing:
        raise ValueError("missing campaign source cards: " + ", ".join(missing))
    for row in branch_rows:
        iter_id = str(row.get("iteration_id") or "")
        claim_id = str(row.get("claim_id") or "")
        if (
            iter_id not in BRANCHES
            or row.get("campaign_id") != CAMPAIGN_ID
            or claim_id not in BRANCHES[iter_id]["source_ids"]
        ):
            raise ValueError(f"branch source-card identity mismatch: {claim_id}")
    return by_id


def _write_iteration_source_cards(
    root: Path,
    *,
    cards: dict[str, dict[str, Any]],
) -> None:
    for iter_id, branch in BRANCHES.items():
        rows = []
        for source_id in branch["source_ids"]:
            row = dict(cards[source_id])
            row["iteration_id"] = iter_id
            rows.append(row)
        path = root / _iteration_source_cards_path(iter_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                for row in rows
            )
            + "\n",
            encoding="utf-8",
        )


def _build_spec(
    *,
    iter_id: str,
    branch: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = str(candidate["candidate_id"])
    policy = CANDIDATE_POLICIES[candidate_id]
    manifest_path = _iteration_dir(iter_id) / "candidate-manifest.json"
    feasibility_path = _iteration_dir(iter_id) / "data-feasibility.json"
    universe_path = _iteration_dir(iter_id) / "universe-contract.json"
    policy_path = _iteration_dir(iter_id) / "candidate-policy-contract.json"
    phase_one_lock_path = _iteration_dir(iter_id) / "phase-one-preregistration-lock.json"
    description = (
        f"Preregistered {candidate_id} candidate for {candidate['method_variant']}. "
        "Research-only, deterministic, next-session execution; no broker writes or frozen-OOS access are authorized."
    )
    if branch["contract_status"] == "dependency_skipped":
        description += (
            " Execution is blocked until the point-in-time stock-universe dependency is supplied."
        )
    factors = {
        name: {
            "source": "expression",
            "expression": expression,
            "default": 0.0,
            "description": f"Lagged research feature for {candidate_id}; the branch contract defines panel and timestamp semantics.",
            "params": {
                "resolver": "mom_breadth_qd_r1_panel_feature_v1",
                "panel_operation": "identity",
                "decision_lag_sessions": 1,
            },
        }
        for name, expression in branch["feature_expressions"].items()
    }
    return {
        "name": f"{branch['strategy_stem']}_{candidate_id.lower()}",
        "description": description,
        "timeframe": "daily",
        "universe": branch["symbols"],
        "lifecycle": "draft",
        "position_direction": "long_only",
        "entry": {"all": ["close > 0"], "any": []},
        "exit": {"all": [], "any": ["close <= 0"]},
        "risk": {
            "max_trades_per_day": max(4, len(branch["symbols"])),
            "max_position_weight": 1.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
        },
        "portfolio": {
            "mode": "hybrid_adaptive_router",
            "max_symbols_per_day": max(1, min(10, len(branch["symbols"]))),
            "gross_exposure_limit": 1.0,
            "max_symbol_weight": 1.0,
            "same_day_flatten": False,
            "duplicate_signal_policy": "stable_signal_id",
            "selected_route_label": f"{CAMPAIGN_ID}:{candidate_id}:{candidate['method_variant']}",
        },
        "costs": {
            "commission_pct": 0.0,
            "slippage_bps": float(PRIMARY_COST_BPS),
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        },
        "execution": {
            "backend": "nautilus_trader",
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {
            "source": "alpaca",
            "symbol": branch["primary_symbol"],
            "path": branch["data_path"].as_posix(),
            "feed": "sip" if iter_id != "mom_breadth_static_hotspot_control_r1" else "iex",
        },
        "data_assumptions": {
            "source": "alpaca",
            "adjusted": True,
            "timezone": "America/New_York",
            "acquisition_tier": "research_strict",
            "derived_development_slice": True,
            "immutable_snapshot_required": True,
            "snapshot_manifest_path": branch["data_path"].as_posix(),
            "session_scope": "regular",
            "forward_fill_allowed": False,
            "zero_return_substitution_allowed": False,
            "nonfinite_action": "fail_closed",
            "historical_quality_paper_eligible": False,
            "historical_quality_is_paper_authorization": False,
        },
        "factors": factors,
        "llm_review": {"enabled": False, "model": None},
        "required_capabilities": ["market.alpaca_bars"],
        "research_design": {
            "iter_id": iter_id,
            "campaign_id": CAMPAIGN_ID,
            "campaign_contract_path": CAMPAIGN_PATH.as_posix(),
            "candidate_manifest_path": manifest_path.as_posix(),
            "data_feasibility_path": feasibility_path.as_posix(),
            "universe_contract_path": universe_path.as_posix(),
            "candidate_policy_contract_path": policy_path.as_posix(),
            "data_contract_path": (_iteration_dir(iter_id) / "data-contract.json").as_posix(),
            "holdout_contract_path": (_iteration_dir(iter_id) / "holdout-contract.json").as_posix(),
            "cost_contract_path": (_iteration_dir(iter_id) / "cost-contract.json").as_posix(),
            "cumulative_trial_contract_path": (
                _iteration_dir(iter_id) / "cumulative-trial-contract.json"
            ).as_posix(),
            "source_cards_path": _iteration_source_cards_path(iter_id).as_posix(),
            "source_card_claim_ids": branch["source_ids"],
            "preregistration_lock_path": phase_one_lock_path.as_posix(),
            "parameter_space": {
                "candidate_id": [candidate_id],
                "method_variant": [candidate["method_variant"]],
                "factor_variant": [candidate["factor_variant"]],
                "parameter_search": [False],
            },
            "candidate_budget": len(branch.get("candidate_ids", [])) or 3,
            "selection_objective": "Maximize development worst-fold Sharpe excess BIL at 20 bps without reading frozen OOS, while retaining one elite per economic mechanism.",
            "anti_overfit_notes": [
                "Candidate semantics and count are fixed by the campaign before any new return is calculated.",
                f"All inference uses the conservative cumulative effective trial count {CAMPAIGN_EFFECTIVE_TRIAL_COUNT}.",
                "Only development_train and development_validation may affect selection; frozen_oos, challenge, and forward partitions are excluded.",
                "Current-stock membership may never substitute for a historical point-in-time stock universe.",
            ],
            "validation_plan": [
                "four_contiguous_development_folds",
                "next_session_execution_with_ten_twenty_forty_bps_cost_views",
                "development_worst_fold_quality_archive",
                "full_benchmark_family",
                "campaign_level_DSR_PBO_SPA_after_pre_OOS_seal",
                "continuous_terminal_free_return_stream",
            ],
        },
        "notes": {
            "intent": branch["objective"],
            "campaign_id": CAMPAIGN_ID,
            "candidate_id": candidate_id,
            "hypothesis_id": candidate["hypothesis_id"],
            "branch_id": candidate["branch_id"],
            "method": candidate["method_variant"],
            "factor_variant": candidate["factor_variant"],
            "archive_descriptors": candidate["archive_descriptors"],
            "factor_library_ids": branch["factor_library_ids"],
            "candidate_policy": policy,
            "candidate_policy_sha256": _payload_sha256(policy),
            "fallback_candidate_id": "BIL",
            "promotion_eligible": candidate["promotion_eligible"],
            "contract_status": branch["contract_status"],
            "terminal_liquidation_in_metrics": False,
            "broker_writes": False,
            "frozen_oos_read_authorized": False,
        },
    }


def _write_specs(root: Path, campaign: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _spec_records(root, campaign, write_specs=True)


def _load_specs(root: Path, campaign: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _spec_records(root, campaign, write_specs=False)


def _spec_records(
    root: Path,
    campaign: dict[str, Any],
    *,
    write_specs: bool,
) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for iter_id, branch in BRANCHES.items():
        candidates = _branch_candidates(campaign, iter_id)
        branch["candidate_ids"] = [str(row["candidate_id"]) for row in candidates]
        for candidate in candidates:
            candidate_id = str(candidate["candidate_id"])
            path = _spec_path(branch, candidate_id)
            if write_specs:
                _write_yaml(
                    root / path,
                    _build_spec(iter_id=iter_id, branch=branch, candidate=candidate),
                )
            elif not (root / path).is_file():
                raise FileNotFoundError(path)
            spec = load_strategy_spec(root / path)
            specs[candidate_id] = {
                "path": path,
                "hash": strategy_content_hash(spec),
                "iter_id": iter_id,
            }
    return specs


def _development_partition(iter_id: str) -> dict[str, Any]:
    start = (
        STATIC_CONTROL_DEVELOPMENT_START
        if iter_id == "mom_breadth_static_hotspot_control_r1"
        else DEVELOPMENT_VALIDATION_START
    )
    return {
        "schema_version": 1,
        "contract_id": _contract_id(iter_id, "development_partition"),
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "partition_id": "development_validation",
        "kind": "development",
        "selection_visible": True,
        "start_session": start,
        "end_session": DEVELOPMENT_VALIDATION_END,
        "quality_metric": "development_worst_fold_sharpe_excess_bil_20bps",
        "folds": [
            {"fold_id": "D1", "start_session": "2021-01-04", "end_session": "2021-09-30"},
            {"fold_id": "D2", "start_session": "2021-10-01", "end_session": "2022-06-30"},
            {"fold_id": "D3", "start_session": "2022-07-01", "end_session": "2023-03-31"},
            {
                "fold_id": "D4",
                "start_session": "2023-04-03",
                "end_session": DEVELOPMENT_VALIDATION_END,
            },
        ],
        "fold_session_intersection_required": True,
        "frozen_oos_access": False,
        "challenge_access": False,
    }


def _validation_contract(
    campaign: dict[str, Any], iter_id: str, candidate_ids: list[str]
) -> dict[str, Any]:
    trial_accounting = _trial_accounting_identity(campaign)
    promotion = campaign["candidate_promotion_policy"]
    family = campaign["statistical_family_policy"]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": _contract_id(iter_id, "validation"),
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "generated_before_backtest": True,
        "selection_partition": "development_validation",
        "quality_metric": "development_worst_fold_sharpe_excess_bil_20bps",
        "return_stream_identity": {
            "frequency": "daily",
            "benchmark": "BIL",
            "primary_cost_bps": PRIMARY_COST_BPS,
            "continuous_across_folds": True,
            "terminal_liquidation_included": False,
        },
        "promotion_gates": {
            "sharpe_excess_bil": {
                "operator": family["primary_sharpe_operator"],
                "threshold": family["primary_sharpe_minimum"],
            },
            "cagr": {"operator": ">=", "threshold": promotion["cagr_minimum"]},
            "tqqq_cagr_capture": {
                "operator": ">=",
                "threshold": promotion["tqqq_cagr_capture_minimum"],
            },
            "tqqq_upside_capture": {
                "operator": ">=",
                "threshold": promotion["tqqq_upside_capture_minimum"],
            },
            "tqqq_downside_capture": {
                "operator": "<=",
                "threshold": promotion["tqqq_downside_capture_maximum"],
            },
            "cagr_excess_qqq": {
                "operator": ">=",
                "threshold": promotion["cagr_excess_qqq_minimum"],
            },
            "max_drawdown": {
                "operator": ">=",
                "threshold": promotion["max_drawdown_minimum"],
            },
            "mar": {"operator": ">=", "threshold": promotion["mar_minimum"]},
            "positive_fold_count": {
                "operator": ">=",
                "threshold": promotion["minimum_positive_folds"],
            },
            "stress_total_return": {
                "operator": promotion["stress_total_return_operator"],
                "threshold": promotion["stress_total_return_minimum"],
                "cost_bps": promotion["stress_cost_bps"],
            },
            "dsr_probability": {"operator": ">=", "threshold": family["dsr_minimum"]},
            "pbo": {"operator": "<=", "threshold": family["pbo_maximum"]},
            "spa_p_value": {
                "operator": "<=",
                "threshold": family["spa_p_value_maximum"],
            },
        },
        "dsr": {
            **trial_accounting,
            "hac_lag_sessions": 21,
            "hac_scope": "single_continuous_terminal_free_OOS_return_stream",
            "minimum_iid_and_hac_probability": family["dsr_minimum"],
        },
        "cost_stress_bps": STRESS_COST_BPS,
        "benchmark_family": BENCHMARK_FAMILY,
        "selection_uses_frozen_oos": False,
    }
    if len(candidate_ids) >= 2:
        payload["family_gates"] = {
            "pbo_min_partitions": 70,
            "dsr_minimum": family["dsr_minimum"],
            "pbo_maximum": family["pbo_maximum"],
            "spa_p_value_maximum": family["spa_p_value_maximum"],
        }
        payload["pbo"] = {
            "block_count": 8,
            "block_ids": [f"B{index}" for index in range(1, 9)],
            "block_construction": {
                "algorithm": "split_ordered_common_sessions_into_contiguous_blocks",
                "remainder_allocation": "one_extra_session_to_earliest_block_ids_in_order",
                "maximum_size_difference": 1,
                "no_shuffle": True,
            },
            "in_sample_block_count": 4,
            "partition_enumeration": "all_directional_combinations",
            "evaluate_complementary_orientations": True,
            "expected_partition_count": 70,
            "minimum_valid_partition_count": 70,
            "selection_candidate_ids": candidate_ids,
            "diagnostic_control_ids": [],
            "valid_partition_requirements": [
                "all_candidate_Sharpe_values_are_defined",
                "all_selection_candidates_have_nonempty_finite_returns_on_both_sides",
                "exactly_four_in_sample_and_four_out_of_sample_blocks",
                "no_session_substitution_or_overlap",
                "candidate_id_invariant_equal_weight_in_sample_ties",
                "candidate_id_invariant_average_oos_midranks",
                "identical_candidate_streams_contribute_exactly_0.5",
            ],
        }
    return payload


def _cumulative_trial_contract(
    campaign: dict[str, Any], iter_id: str, candidate_ids: list[str]
) -> dict[str, Any]:
    trial_accounting = _trial_accounting_identity(campaign)
    return {
        "schema_version": 2,
        "contract_id": _contract_id(iter_id, "cumulative_trials"),
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "generated_before_backtest": True,
        **trial_accounting,
        "branch_candidate_count": len(candidate_ids),
        # Compatibility alias for older readers; this is the incremental cap.
        "cumulative_trial_exposure_budget": trial_accounting["campaign_trial_exposure_budget"],
        "DSR_uses_effective_trial_count": True,
        "all_candidates_controls_and_failed_paths_counted": True,
        "reset_allowed": False,
    }


def _write_static_contracts(root: Path, campaign: dict[str, Any]) -> None:
    exchange_calendar_artifact = _binding(EXCHANGE_CALENDAR_PATH, root)
    for iter_id, branch in BRANCHES.items():
        iteration = root / _iteration_dir(iter_id)
        iteration.mkdir(parents=True, exist_ok=True)
        candidate_ids = [row["candidate_id"] for row in _branch_candidates(campaign, iter_id)]
        data_artifacts = [_binding(path, root) for path in branch["data_artifacts"]]
        promotion_benchmark_artifacts = [
            _binding(path, root) for path in PROMOTION_BENCHMARK_DATA_ARTIFACTS
        ]
        development_first_session = (
            STATIC_CONTROL_DEVELOPMENT_START
            if iter_id == "mom_breadth_static_hotspot_control_r1"
            else DEVELOPMENT_START
        )
        contracts: dict[str, dict[str, Any]] = {
            "data-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "data"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "capability_ids": ["market.alpaca_bars"],
                "artifacts": data_artifacts,
                "promotion_benchmark_artifacts": promotion_benchmark_artifacts,
                "exchange_calendar_artifact": exchange_calendar_artifact,
                "calendar_id": "XNYS",
                "calendar_coverage_policy": "exact_each_symbol",
                "missing_calendar_session_action": "fail_closed",
                "extra_non_session_action": "fail_closed",
                "price_intersection_as_calendar_allowed": False,
                "adjustment": "all",
                "feed": "iex_cache_control"
                if iter_id == "mom_breadth_static_hotspot_control_r1"
                else "sip",
                "auxiliary_cash_proxy_feed": "sip"
                if iter_id == "mom_breadth_static_hotspot_control_r1"
                else "same_as_primary",
                "session_scope": "regular",
                "forward_fill_allowed": False,
                "zero_return_substitution_allowed": False,
                "decision_features_lagged_sessions": 1,
                "paper_ready_evidence": False,
                "dependency_status": branch["contract_status"],
                "visibility_partition": "development_train_and_development_validation",
                "development_only_snapshot": True,
                "first_session": development_first_session,
                "last_session": DEVELOPMENT_VALIDATION_END,
            },
            "feature-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "features"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "features": [
                    {
                        "feature_id": name,
                        "expression": expression,
                        "lag_sessions": 1,
                        "nonfinite_action": "candidate_fallback",
                    }
                    for name, expression in branch["feature_expressions"].items()
                ],
                "factor_library_ids": branch["factor_library_ids"],
                "calendar_features_use_exchange_session_index": iter_id
                == "mom_breadth_calendar_flow_r1",
                "calendar_index_source": "data_contract.exchange_calendar_artifact"
                if iter_id == "mom_breadth_calendar_flow_r1"
                else "not_applicable",
                "calendar_window_position_identity": "XNYS_exchange_session_ordinal"
                if iter_id == "mom_breadth_calendar_flow_r1"
                else "not_applicable",
                "price_intersection_as_calendar_allowed": False,
                "cross_session_open_and_close_are_never_collapsed": iter_id
                == "mom_breadth_cross_session_r1",
                "point_in_time_membership_required": iter_id == "mom_breadth_pit_xsmom_r1",
            },
            "label-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "labels"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "model_training": False,
                "label": "not_applicable_deterministic_policy",
                "portfolio_return": PORTFOLIO_RETURN_IDENTITY,
                "signal_timestamp": "completed_regular_session_close",
                "execution_timestamp": "next_regular_session_open",
                "terminal_liquidation_included": False,
            },
            "validation-contract.json": _validation_contract(campaign, iter_id, candidate_ids),
            "cost-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "costs"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "cost_views": [
                    {"name": "low", "one_way_bps": 10},
                    {"name": "primary", "one_way_bps": 20},
                    {"name": "severe", "one_way_bps": 40},
                ],
                "primary_one_way_bps": PRIMARY_COST_BPS,
                "cost_applied_to": "one_way_notional_turnover_at_next_regular_open",
                "terminal_rejoin_cost_included": False,
            },
            "benchmark-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "benchmarks"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "required": BENCHMARK_FAMILY,
                "cash_proxy_symbol": "BIL",
                "market_proxy_symbol": "SPY",
                "growth_proxy_symbol": "QQQ",
                "leveraged_growth_proxy_symbol": "TQQQ",
                "promotion_benchmark_artifacts": promotion_benchmark_artifacts,
                "sector_theme_proxy_symbol": "XLK",
                "same_sessions": True,
                "same_cost_views": True,
                "cost_views_bps": STRESS_COST_BPS,
                "primary_one_way_bps": PRIMARY_COST_BPS,
                "cost_applied_to": "initial_notional_at_first_available_development_open",
                "initialization_precedes_validation": True,
                "allocation": "fixed_initial_notional_buy_and_hold_no_rebalance",
                "terminal_liquidation_included": False,
                "validation_return_cost_note": "initialization_cost_precedes_validation_so_validation_daily_returns_are_cost_invariant",
                "ex_post_best_symbol_selectable": False,
                "equal_weight_symbols": branch["symbols"],
                "ex_post_best_symbols": branch["symbols"],
            },
            "holdout-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "holdout"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "partitions": [
                    {
                        "partition_id": "development_train",
                        "kind": "development",
                        "start_session": development_first_session,
                        "end_session": DEVELOPMENT_TRAIN_END,
                        "selection_visible": True,
                    },
                    {
                        "partition_id": "development_validation",
                        "kind": "development",
                        "start_session": DEVELOPMENT_VALIDATION_START,
                        "end_session": DEVELOPMENT_VALIDATION_END,
                        "selection_visible": True,
                    },
                    {
                        "partition_id": "frozen_oos",
                        "kind": "frozen_oos",
                        "start_session": FROZEN_OOS_START,
                        "end_session": FROZEN_OOS_END,
                        "selection_visible": False,
                    },
                    {
                        "partition_id": "challenge_set",
                        "kind": "challenge",
                        "start_session": CHALLENGE_START,
                        "end_session": CHALLENGE_END,
                        "selection_visible": False,
                    },
                    {
                        "partition_id": "forward_observation",
                        "kind": "forward",
                        "start_session": "after_challenge_end",
                        "end_session": None,
                        "selection_visible": False,
                    },
                ],
                "pre_oos_seal_required": True,
                "globally_exposed_historical_data_disclosure": True,
                "campaign_specific_holdout_only": True,
            },
            "cumulative-trial-contract.json": _cumulative_trial_contract(
                campaign, iter_id, candidate_ids
            ),
            "development-partition-contract.json": _development_partition(iter_id),
            "candidate-policy-contract.json": {
                "schema_version": 1,
                "contract_id": _contract_id(iter_id, "candidate_policies"),
                "campaign_id": CAMPAIGN_ID,
                "iter_id": iter_id,
                "generated_before_backtest": True,
                "policy_count": len(candidate_ids),
                "policies": [
                    {
                        "candidate_id": row["candidate_id"],
                        "method_variant": row["method_variant"],
                        "factor_variant": row["factor_variant"],
                        "policy": CANDIDATE_POLICIES[str(row["candidate_id"])],
                        "policy_sha256": _payload_sha256(
                            CANDIDATE_POLICIES[str(row["candidate_id"])]
                        ),
                    }
                    for row in _branch_candidates(campaign, iter_id)
                ],
            },
        }
        for filename, payload in contracts.items():
            write_json(iteration / filename, payload)


def _source_object(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": card["source_url"],
        "published_or_updated_at": card.get("published_or_updated_at") or card["accessed_at"],
        "source_type": card["source_type"],
        "credibility": "identified primary research, official provider documentation, or registered scholarly metadata",
        "core_claim": card["claim"],
        "project_applicability": card["impact_on_spec"],
        "reflection": card["limitations"],
        "topics": card["applies_to"],
    }


def _write_external_brief(
    root: Path,
    *,
    iter_id: str,
    branch: dict[str, Any],
    candidates: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
) -> None:
    iteration = _iteration_dir(iter_id)
    primary_id = str(candidates[0]["candidate_id"])
    selected_cards = [cards[source_id] for source_id in branch["source_ids"]]
    sources = [_source_object(card) for card in selected_cards]
    bindings = [
        {
            "source_card_claim_id": card["claim_id"],
            "canonical_url": canonical_source_url(card["source_url"]),
            "claim_fingerprint": claim_fingerprint(card["claim"]),
            "brief_claim_fingerprint": claim_fingerprint(card["claim"]),
        }
        for card in selected_cards
    ]
    payload = {
        "schema_version": 2,
        "iter_id": iter_id,
        "strategy_name": f"{branch['strategy_stem']}_{primary_id.lower()}",
        "source_spec_path": specs[primary_id]["path"].as_posix(),
        "spec_hash": specs[primary_id]["hash"],
        "objective": branch["objective"],
        "current_source_card_paths": [_iteration_source_cards_path(iter_id).as_posix()],
        "source_evidence_bindings": bindings,
        "sources": sources,
        "topic_coverage": [
            "economic_mechanism",
            "universe_and_survivorship",
            "quality_diversity",
            "transaction_costs_and_simple_benchmarks",
            "multiple_testing_DSR_PBO_SPA",
            "development_holdout_and_failure_memory",
            "execution_timestamp_safety",
        ],
        "candidate_matrix_revisions": [
            "Keep exactly the campaign-assigned deterministic candidates and add no outcome-driven mutation.",
            "Preserve one development elite per economic mechanism rather than one global winner.",
            "Block any point-in-time stock candidate whose historical membership and delisting dependencies are absent.",
            "Reserve ML and expensive resource rungs until a deterministic mechanism shows net development evidence.",
        ],
        "hypothesis_links": [branch["hypothesis_id"]],
    }
    write_json(root / iteration / "external-brief.json", payload)
    (root / iteration / "external-brief.md").write_text(
        f"""# External Brief: {iter_id}

This branch tests `{branch["hypothesis_id"]}` inside the sealed `{CAMPAIGN_ID}` quality-diversity campaign. The evidence set contains {len(sources)} verified sources and separates economic motivation from proof of Alpha. The candidate inventory is fixed before any new return is calculated.

The design uses development data only for candidate comparison, applies 10, 20, and 40 bps one-way cost views, retains BIL and simple buy-and-hold benchmarks, and carries all prior candidate exposure into DSR. Frozen OOS, challenge, and forward outcomes are unavailable to candidate generation.

The branch status is `{branch["contract_status"]}`. A dependency-skipped branch is evidence of a missing capability, not permission to substitute current constituents, cached lists, or fabricated point-in-time membership.
""",
        encoding="utf-8",
    )


def _write_queries(
    root: Path,
    *,
    iter_id: str,
    branch: dict[str, Any],
    cards: dict[str, dict[str, Any]],
) -> None:
    curated = []
    for source_id in branch["source_ids"]:
        card = cards[source_id]
        curated.append(
            {
                "discovery_id": source_id,
                "title": source_id.replace("_", " ").title(),
                "authors": [],
                "published_at": card.get("published_or_updated_at") or card["accessed_at"],
                "source_type": card["source_type"],
                "summary": card["claim"],
                "topics": card["applies_to"],
                "url": card["source_url"],
            }
        )
    write_json(
        root / _iteration_dir(iter_id) / "knowledge-scout-queries.json",
        {
            "schema_version": 1,
            "iter_id": iter_id,
            "queries": [],
            "curated_candidates": curated,
            "max_results_per_query": 5,
        },
    )


def _write_markdown(
    root: Path,
    *,
    iter_id: str,
    branch: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> None:
    iteration = root / _iteration_dir(iter_id)
    candidate_lines = "\n".join(
        f"- `{row['candidate_id']}`: `{row['method_variant']}` using `{row['factor_variant']}`; promotion eligible = `{row['promotion_eligible']}`."
        for row in candidates
    )
    (iteration / "hypotheses.md").write_text(
        f"""# Hypotheses: {iter_id}

## Hypothesis

{branch["objective"]}

## Failure mode

The mechanism may be sample-specific, too costly, redundant with buy-and-hold beta, unstable across development folds, or unavailable under the declared data capability. A missing point-in-time dependency is a hard skip rather than a proxy substitution.

## Measurement

Rank only on development worst-fold Sharpe excess BIL at 20 bps. Also report CAGR, QQQ excess, TQQQ upside capture, drawdown, MAR, turnover, all benchmark-family rows, and 10/20/40 bps stress. Campaign inference later uses DSR, PBO, and SPA on one common continuous terminal-free return matrix.

## Stop/Pivot criterion

Stop the branch when no candidate has finite common-session returns or all candidates fail their simple matched baseline after primary costs. Pivot only in a new registered campaign; do not mutate this frozen inventory.

{candidate_lines}
""",
        encoding="utf-8",
    )
    (iteration / "search-space.md").write_text(
        f"""# Search Space: {iter_id}

The Path is `{branch["path"]}` and contains exactly {len(candidates)} deterministic candidates assigned by `{CAMPAIGN_ID}`. Candidate IDs, method variants, factors, universe semantics, development partitions, costs, and fallback behavior are enumerated before any new training or backtest. There is no mutation, ML training, LLM inference, or early-stopping rung in this round.

Every candidate uses the full benchmark family and the same primary 20 bps cost view. Frozen OOS is not a search resource. The campaign archive keeps at most one elite for the branch's economic mechanism, with candidate ID as the deterministic tie-break.
""",
        encoding="utf-8",
    )
    (iteration / "decision-record.md").write_text(
        f"""# Decision Record: {iter_id}

- Path: `{branch["path"]}`
- Decision: pending until preregistration, knowledge assessment, data feasibility, and development evaluation complete.
- Reason: no candidate return from this campaign has been inspected, so continue, pivot, or stop would be premature.
- Next iteration suggestion: only a newly registered campaign may refine a surviving mechanism; ML remains deferred until deterministic incremental value exists.

Broker writes, paper automation, frozen OOS access, and real-money execution are outside this decision record.
""",
        encoding="utf-8",
    )


def _write_modality_and_reuse(root: Path, iter_id: str, candidate_ids: list[str]) -> None:
    iteration = root / _iteration_dir(iter_id)
    write_json(
        iteration / "modality-role-matrix.json",
        {
            "schema_version": 1,
            "contract_id": _contract_id(iter_id, "modality_roles"),
            "campaign_id": CAMPAIGN_ID,
            "iter_id": iter_id,
            "generated_before_backtest": True,
            "ai_ml_round": False,
            "candidate_ids": candidate_ids,
            "roles": [
                {
                    "role": "factor_generation",
                    "status": "deterministic_only",
                    "candidates": candidate_ids,
                    "fallback": "BIL",
                },
                {
                    "role": "return_ranking",
                    "status": "not_applicable_no_model_training",
                    "candidates": [],
                    "fallback": "deterministic_candidate",
                },
                {
                    "role": "risk_prediction",
                    "status": "not_applicable_no_model_training",
                    "candidates": [],
                    "fallback": "deterministic_candidate",
                },
                {
                    "role": "regime_meta_gate",
                    "status": "deterministic_if_declared",
                    "candidates": candidate_ids,
                    "fallback": "BIL",
                },
                {
                    "role": "sizing",
                    "status": "deterministic_only",
                    "candidates": candidate_ids,
                    "fallback": "BIL",
                },
                {
                    "role": "uncertainty",
                    "status": "not_applicable_no_estimator",
                    "candidates": [],
                    "fallback": "BIL",
                },
                {
                    "role": "deterministic_fallback",
                    "status": "required",
                    "candidates": candidate_ids,
                    "fallback": "BIL",
                },
            ],
            "matched_modality_ablations": "not_applicable_no_new_information_modality",
            "model_training_authorized": False,
        },
    )
    write_json(
        iteration / "model-reuse-decision.json",
        {
            "schema_version": 1,
            "iter_id": iter_id,
            "generated_at": PREREGISTERED_AT,
            "default_policy": "no_warm_start_without_explicit_drift_or_data_reason",
            "decisions": [],
            "round_decision": {
                "action": "no_model_training_deterministic_discovery_round",
                "retrain": False,
                "warm_start": False,
                "reason": "The campaign deliberately tests deterministic economic mechanisms before spending trial budget on ML.",
                "negative_ml_memory_retained": True,
            },
        },
    )


def _search_space(
    *,
    campaign: dict[str, Any],
    iter_id: str,
    branch: dict[str, Any],
    candidates: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
    root: Path,
    finalized: bool,
) -> dict[str, Any]:
    iteration = _iteration_dir(iter_id)
    primary_id = str(candidates[0]["candidate_id"])
    manifest_path = iteration / "candidate-manifest.json"
    feasibility_path = iteration / "data-feasibility.json"
    payload: dict[str, Any] = {
        "schema_version": 3,
        "created_at": PREREGISTERED_AT,
        "iter_id": iter_id,
        "strategy_name": f"{branch['strategy_stem']}_{primary_id.lower()}",
        "source_spec_path": specs[primary_id]["path"].as_posix(),
        "spec_hash": specs[primary_id]["hash"],
        "objective": branch["objective"],
        "campaign_id": CAMPAIGN_ID,
        "campaign_contract_path": CAMPAIGN_PATH.as_posix(),
        "campaign_contract_sha256": _sha256(root / CAMPAIGN_PATH),
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "candidate_manifest_path": manifest_path.as_posix(),
        "data_feasibility_path": feasibility_path.as_posix(),
        "cost_table_path": (iteration / "cost-contract.json").as_posix(),
        "total_candidate_budget": len(candidates),
        "cumulative_trial_count": CAMPAIGN_EFFECTIVE_TRIAL_COUNT,
        "cumulative_trial_count_semantics": "preregistered_minimum_before_allocation_ledger_seal",
        "trial_accounting": _trial_accounting_identity(campaign),
        "paths": [
            {
                "name": branch["path"],
                "candidate_count": len(candidates),
                "hypothesis_refs": [branch["hypothesis_id"]],
                "parameters": {
                    "candidate_ids": [row["candidate_id"] for row in candidates],
                    "method_variants": [row["method_variant"] for row in candidates],
                    "factor_variants": [row["factor_variant"] for row in candidates],
                    "mutation": "none",
                    "model_training": False,
                },
                "benchmark_family": BENCHMARK_FAMILY,
            }
        ],
        "trial_ledger_paths": [(iteration / "evaluation-run/trial-ledger.jsonl").as_posix()],
        "evaluation_report_paths": [
            (iteration / "evaluation-run/evaluation-report.json").as_posix()
        ],
        "contracts": {
            "data": (iteration / "data-contract.json").as_posix(),
            "feature": (iteration / "feature-contract.json").as_posix(),
            "label": (iteration / "label-contract.json").as_posix(),
            "validation": (iteration / "validation-contract.json").as_posix(),
            "cost": (iteration / "cost-contract.json").as_posix(),
            "benchmark": (iteration / "benchmark-contract.json").as_posix(),
            "holdout": (iteration / "holdout-contract.json").as_posix(),
            "cumulative_trial": (iteration / "cumulative-trial-contract.json").as_posix(),
            "universe": (iteration / "universe-contract.json").as_posix(),
            "development_partition": (iteration / "development-partition-contract.json").as_posix(),
            "candidate_policy": (iteration / "candidate-policy-contract.json").as_posix(),
        },
        "knowledge_contract": {
            "assessment_path": (iteration / "knowledge-assessment.json").as_posix(),
            "scout_path": (iteration / "knowledge-scout.json").as_posix(),
            "model_reuse_decision_path": (iteration / "model-reuse-decision.json").as_posix(),
            "modality_role_matrix_path": (iteration / "modality-role-matrix.json").as_posix(),
            "required_visibility_partitions": [
                "public_literature",
                "train_only_empirical",
                "challenge_result",
                "forward_observation",
            ],
        },
        "adaptive_selection_disclosure": "All earlier momentum research and historical prices are exposed; this campaign's frozen OOS remains unread until the development archive and allocation ledger are sealed.",
    }
    if finalized:
        payload["candidate_manifest_sha256"] = _sha256(root / manifest_path)
        payload["data_feasibility_sha256"] = _sha256(root / feasibility_path)
    return payload


def _phase_one_lock_path(iter_id: str) -> Path:
    return _iteration_dir(iter_id) / "phase-one-preregistration-lock.json"


def _phase_one_lock_payload(
    root: Path,
    *,
    campaign: dict[str, Any],
    iter_id: str,
    branch: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    iteration = _iteration_dir(iter_id)
    candidates = _branch_candidates(campaign, iter_id)
    paths: dict[str, Path] = {
        "generator": GENERATOR_PATH,
        "development_runner": DEVELOPMENT_RUNNER_PATH,
        "development_runner_tests": DEVELOPMENT_RUNNER_TEST_PATH,
        **DEVELOPMENT_IMPLEMENTATION_PATHS,
        "campaign_contract": CAMPAIGN_PATH,
        "development_integrity_amendment": INTEGRITY_AMENDMENT_PATH,
        "campaign_source_cards": SOURCE_CARDS_PATH,
        "branch_source_evidence": BRANCH_SOURCE_EVIDENCE_PATH,
        "iteration_source_cards": _iteration_source_cards_path(iter_id),
        "factor_library_json": FACTOR_LIBRARY_PATH,
        "factor_library_markdown": FACTOR_LIBRARY_PATH.with_suffix(".md"),
        "capability_registry": Path("capabilities/registry.yaml"),
        "exchange_calendar_artifact": EXCHANGE_CALENDAR_PATH,
        "data_contract": iteration / "data-contract.json",
        "feature_contract": iteration / "feature-contract.json",
        "label_contract": iteration / "label-contract.json",
        "validation_contract": iteration / "validation-contract.json",
        "cost_contract": iteration / "cost-contract.json",
        "benchmark_contract": iteration / "benchmark-contract.json",
        "holdout_contract": iteration / "holdout-contract.json",
        "cumulative_trial_contract": iteration / "cumulative-trial-contract.json",
        "development_partition_contract": iteration / "development-partition-contract.json",
        "candidate_policy_contract": iteration / "candidate-policy-contract.json",
        "external_brief_json": iteration / "external-brief.json",
        "external_brief_markdown": iteration / "external-brief.md",
        "knowledge_scout_queries": iteration / "knowledge-scout-queries.json",
        "hypotheses": iteration / "hypotheses.md",
        "search_space_markdown": iteration / "search-space.md",
        "decision_record": iteration / "decision-record.md",
        "modality_role_matrix": iteration / "modality-role-matrix.json",
    }
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        paths[f"spec_{candidate_id}"] = specs[candidate_id]["path"]
    for index, artifact in enumerate(branch["data_artifacts"], start=1):
        paths[f"market_data_artifact_{index}"] = artifact
    for index, artifact in enumerate(PROMOTION_BENCHMARK_DATA_ARTIFACTS, start=1):
        paths[f"promotion_benchmark_data_artifact_{index}"] = artifact
    return {
        "schema_version": 1,
        "lock_type": "breadth_campaign_phase_one_preregistration_v1",
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "created_at": PREREGISTERED_AT,
        "generated_before_backtest": True,
        "generated_before_model_training": True,
        "candidate_ids": [str(row["candidate_id"]) for row in candidates],
        "candidate_policy_sha256": {
            str(row["candidate_id"]): _payload_sha256(CANDIDATE_POLICIES[str(row["candidate_id"])])
            for row in candidates
        },
        "immutable_inventory": {name: _binding(path, root) for name, path in paths.items()},
        "mutable_after_lock": [
            "knowledge-baseline.json",
            "knowledge-scout.json",
            "knowledge-assessment.json",
            "knowledge-context.json",
            "model-reuse-decision.json",
            "search-space.json",
            "data-feasibility.json",
            "universe-contract.json",
            "candidate-manifest.json",
        ],
        "frozen_oos_read_authorized": False,
        "broker_writes": False,
    }


def _verify_phase_one_locks(
    root: Path,
    *,
    campaign: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> None:
    lock_paths = [root / _phase_one_lock_path(iter_id) for iter_id in BRANCHES]
    if not all(path.is_file() for path in lock_paths):
        raise FileNotFoundError("complete phase-one preregistration lock inventory is required")
    for iter_id, branch in BRANCHES.items():
        path = root / _phase_one_lock_path(iter_id)
        actual = _read_json(path)
        expected = _phase_one_lock_payload(
            root,
            campaign=campaign,
            iter_id=iter_id,
            branch=branch,
            specs=specs,
        )
        if actual != expected:
            raise ValueError(f"phase-one preregistration lock drift: {iter_id}")


def _write_phase_one_locks(
    root: Path,
    *,
    campaign: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> None:
    for iter_id, branch in BRANCHES.items():
        path = root / _phase_one_lock_path(iter_id)
        payload = _phase_one_lock_payload(
            root,
            campaign=campaign,
            iter_id=iter_id,
            branch=branch,
            specs=specs,
        )
        if path.exists():
            if _read_json(path) != payload:
                raise ValueError(f"refusing to overwrite phase-one lock drift: {iter_id}")
            continue
        write_json(path, payload)


def _write_integrity_repair_receipt(root: Path) -> None:
    lock_bindings = {iter_id: _binding(_phase_one_lock_path(iter_id), root) for iter_id in BRANCHES}
    payload = {
        "schema_version": 1,
        "receipt_id": "mom_breadth_qd_r1_development_integrity_repair_receipt_20260818",
        "campaign_id": CAMPAIGN_ID,
        "generated_at": "2026-08-18T14:43:02Z",
        "status": "replacement_phase_one_locks_created_before_development_evaluation",
        "amendment": _binding(INTEGRITY_AMENDMENT_PATH, root),
        "campaign_contract": _binding(CAMPAIGN_PATH, root),
        "generator": _binding(GENERATOR_PATH, root),
        "development_runner": _binding(DEVELOPMENT_RUNNER_PATH, root),
        "development_runner_tests": _binding(DEVELOPMENT_RUNNER_TEST_PATH, root),
        "market_calendar_implementation": _binding(Path("open_composer/market_calendar.py"), root),
        "exchange_calendar_artifact": _binding(EXCHANGE_CALENDAR_PATH, root),
        "phase_one_lock_count": len(lock_bindings),
        "phase_one_locks": lock_bindings,
        "candidate_count": CAMPAIGN_CANDIDATE_COUNT,
        "expected_evaluated_candidate_count": 16,
        "expected_dependency_skipped_candidate_count": 3,
        "expected_cost_view_count": 48,
        "expected_effective_trial_count": 8195,
        "candidate_inventory_changed": False,
        "candidate_policy_changed": False,
        "partition_boundaries_changed": False,
        "frozen_oos_rows_read": 0,
        "model_training_count": 0,
        "broker_writes": False,
    }
    path = root / INTEGRITY_RECEIPT_PATH
    if path.exists():
        if _read_json(path) != payload:
            raise ValueError(f"development integrity receipt drift: {path}")
        return
    write_json(path, payload)


def prepare(root: Path) -> None:
    base = root.resolve()
    campaign = _campaign(base)
    existing_locks = [(base / _phase_one_lock_path(iter_id)).is_file() for iter_id in BRANCHES]
    if any(existing_locks):
        if not all(existing_locks):
            raise ValueError("partial phase-one preregistration lock inventory")
        specs = _load_specs(base, campaign)
        _verify_phase_one_locks(base, campaign=campaign, specs=specs)
        _write_integrity_repair_receipt(base)
        return
    _write_development_data_slices(base)
    cards = _source_cards(base)
    _write_iteration_source_cards(base, cards=cards)
    write_factor_library_artifact(
        strategy_name=CAMPAIGN_ID,
        factor_ids=FACTOR_LIBRARY_IDS,
        root=base,
        stem="mom_breadth_qd_r1-factor-library",
    )
    specs = _write_specs(base, campaign)
    _write_static_contracts(base, campaign)
    for iter_id, branch in BRANCHES.items():
        candidates = _branch_candidates(campaign, iter_id)
        candidate_ids = [str(row["candidate_id"]) for row in candidates]
        _write_external_brief(
            base,
            iter_id=iter_id,
            branch=branch,
            candidates=candidates,
            specs=specs,
            cards=cards,
        )
        _write_queries(base, iter_id=iter_id, branch=branch, cards=cards)
        _write_markdown(base, iter_id=iter_id, branch=branch, candidates=candidates)
        _write_modality_and_reuse(base, iter_id, candidate_ids)
        write_json(
            base / _iteration_dir(iter_id) / "search-space.json",
            _search_space(
                campaign=campaign,
                iter_id=iter_id,
                branch=branch,
                candidates=candidates,
                specs=specs,
                root=base,
                finalized=False,
            ),
        )
    _write_phase_one_locks(base, campaign=campaign, specs=specs)
    _write_integrity_repair_receipt(base)


def _manifest_contracts(root: Path, iter_id: str) -> dict[str, dict[str, dict[str, str]]]:
    iteration = _iteration_dir(iter_id)
    groups = {
        "data": "data",
        "features": "features",
        "labels": "labels",
        "validation": "validation",
        "costs": "costs",
        "benchmarks": "benchmarks",
        "candidate_policies": "candidate_policies",
    }
    result: dict[str, dict[str, dict[str, str]]] = {}
    for group, kind in groups.items():
        path = (
            iteration
            / f"{kind.rstrip('s') if kind in {'features', 'labels', 'costs', 'benchmarks'} else kind}-contract.json"
        )
        filename_by_group = {
            "features": "feature-contract.json",
            "labels": "label-contract.json",
            "costs": "cost-contract.json",
            "benchmarks": "benchmark-contract.json",
            "candidate_policies": "candidate-policy-contract.json",
        }
        if group in filename_by_group:
            path = iteration / filename_by_group[group]
        contract_id = _contract_id(iter_id, kind)
        result[group] = {contract_id: _binding(path, root)}
    return result


def _candidate_rows(
    root: Path,
    *,
    campaign: dict[str, Any],
    iter_id: str,
    branch: dict[str, Any],
    specs: dict[str, dict[str, Any]],
    with_evidence_hashes: bool,
) -> list[dict[str, Any]]:
    iteration = _iteration_dir(iter_id)
    universe_path = iteration / "universe-contract.json"
    partition_path = iteration / "development-partition-contract.json"
    rows = []
    for candidate in _branch_candidates(campaign, iter_id):
        candidate_id = str(candidate["candidate_id"])
        row = {
            "candidate_id": candidate_id,
            "path": branch["path"],
            "role": "deterministic_mechanism_candidate",
            "method": candidate["method_variant"],
            "ablation": candidate["factor_variant"],
            "spec_path": specs[candidate_id]["path"].as_posix(),
            "fallback": "BIL",
            "data_contract": _contract_id(iter_id, "data"),
            "feature_contract": _contract_id(iter_id, "features"),
            "label_contract": _contract_id(iter_id, "labels"),
            "validation_contract": _contract_id(iter_id, "validation"),
            "cost_contract": _contract_id(iter_id, "costs"),
            "benchmark_contract": _contract_id(iter_id, "benchmarks"),
            "candidate_policy_contract": _contract_id(iter_id, "candidate_policies"),
            "candidate_policy_sha256": _payload_sha256(CANDIDATE_POLICIES[candidate_id]),
            "campaign_id": CAMPAIGN_ID,
            "hypothesis_id": candidate["hypothesis_id"],
            "branch_id": candidate["branch_id"],
            "child_iteration_id": iter_id,
            "promotion_eligible": candidate["promotion_eligible"],
            "quality_metric": campaign["qd_archive"]["quality_metric"],
            "archive_descriptors": candidate["archive_descriptors"],
            "universe_contract_path": universe_path.as_posix(),
            "development_partition_contract_path": partition_path.as_posix(),
        }
        if with_evidence_hashes:
            row["universe_contract_sha256"] = _sha256(root / universe_path)
            row["development_partition_contract_sha256"] = _sha256(root / partition_path)
        else:
            row["universe_contract_sha256"] = "0" * 64
            row["development_partition_contract_sha256"] = "0" * 64
        rows.append(row)
    return rows


def _required_references(
    root: Path,
    *,
    iter_id: str,
    branch: dict[str, Any],
) -> dict[str, dict[str, str]]:
    iteration = _iteration_dir(iter_id)
    paths = {
        "campaign_contract": CAMPAIGN_PATH,
        "campaign_source_cards": SOURCE_CARDS_PATH,
        "branch_source_evidence": BRANCH_SOURCE_EVIDENCE_PATH,
        "source_cards": _iteration_source_cards_path(iter_id),
        "factor_library": FACTOR_LIBRARY_PATH,
        "capability_registry": Path("capabilities/registry.yaml"),
        "exchange_calendar_artifact": EXCHANGE_CALENDAR_PATH,
        "data_contract": iteration / "data-contract.json",
        "feature_contract": iteration / "feature-contract.json",
        "label_contract": iteration / "label-contract.json",
        "validation_contract": iteration / "validation-contract.json",
        "cost_contract": iteration / "cost-contract.json",
        "benchmark_contract": iteration / "benchmark-contract.json",
        "holdout_contract": iteration / "holdout-contract.json",
        "cumulative_trial_contract": iteration / "cumulative-trial-contract.json",
        "development_partition_contract": iteration / "development-partition-contract.json",
        "candidate_policy_contract": iteration / "candidate-policy-contract.json",
        "phase_one_preregistration_lock": iteration / "phase-one-preregistration-lock.json",
        "knowledge_assessment": iteration / "knowledge-assessment.json",
        "knowledge_scout": iteration / "knowledge-scout.json",
        "knowledge_context": iteration / "knowledge-context.json",
        "model_reuse_decision": iteration / "model-reuse-decision.json",
        "modality_role_matrix": iteration / "modality-role-matrix.json",
    }
    for index, artifact in enumerate(branch["data_artifacts"], start=1):
        paths[f"market_data_artifact_{index}"] = artifact
    for index, artifact in enumerate(PROMOTION_BENCHMARK_DATA_ARTIFACTS, start=1):
        paths[f"promotion_benchmark_data_artifact_{index}"] = artifact
    return {name: _binding(path, root) for name, path in paths.items()}


def _write_data_feasibility(
    root: Path,
    *,
    campaign: dict[str, Any],
    iter_id: str,
    branch: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> Path:
    iteration = _iteration_dir(iter_id)
    candidates = _candidate_rows(
        root,
        campaign=campaign,
        iter_id=iter_id,
        branch=branch,
        specs=specs,
        with_evidence_hashes=False,
    )
    ready = branch["contract_status"] == "ready"
    action = "evaluate" if ready else "dependency_skipped"
    candidate_ids = [row["candidate_id"] for row in candidates]
    references = _required_references(root, iter_id=iter_id, branch=branch)
    payload = {
        "schema_version": 1,
        "report_type": "mom_breadth_qd_r1_candidate_data_feasibility",
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "generated_at": PREREGISTERED_AT,
        "generated_before_backtest": True,
        "generated_before_model_training": True,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": ready,
        "historical_positive_alpha_claim_authorized": False,
        "broker_writes": False,
        "campaign_universe": {
            "status": branch["contract_status"],
            "capability_ids": ["market.alpaca_bars"],
            "universe_selection": branch["universe_selection"],
        },
        "path_gates": {
            branch["path"]: {
                "action": action,
                "historical_evaluation_go": ready,
                "candidate_ids": candidate_ids,
                "scope": "development_train_and_development_validation_only"
                if ready
                else "no_evaluation_until_dependency_is_resolved",
            }
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(candidates),
            "evaluation_authorized_count": len(candidates) if ready else 0,
            "dependency_skipped_count": 0 if ready else len(candidates),
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": len(candidates),
            "rows": [
                {
                    "candidate_id": row["candidate_id"],
                    "path": row["path"],
                    "action": action,
                    "reason_code": "complete_bound_development_panel"
                    if ready
                    else "point_in_time_universe_dependency_missing_fail_closed",
                    "candidate_binding_sha256": candidate_authorization_binding_sha256(row),
                }
                for row in candidates
            ],
        },
        "required_reference_names": sorted(references),
        "required_references": references,
        "blockers": branch.get("blockers", [])
        + [
            "paper_orders_and_paper_fills_are_outside_this_stage",
            "frozen_OOS_is_unread_until_campaign_archive_and_allocation_ledger_are_sealed",
        ],
        "conclusion": "development_evaluation_authorized"
        if ready
        else "dependency_skipped_fail_closed",
    }
    path = iteration / "data-feasibility.json"
    write_json(root / path, payload)
    return path


def _write_universe_contract(
    root: Path,
    *,
    campaign: dict[str, Any],
    iter_id: str,
    branch: dict[str, Any],
    feasibility_path: Path,
) -> Path:
    hypothesis = next(
        row for row in campaign["hypotheses"] if row["hypothesis_id"] == branch["hypothesis_id"]
    )
    candidates = _branch_candidates(campaign, iter_id)
    promotion_values = {bool(row["promotion_eligible"]) for row in candidates}
    if len(promotion_values) != 1:
        raise ValueError(f"shared universe contract needs one promotion eligibility: {iter_id}")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": _contract_id(iter_id, "universe"),
        "campaign_id": CAMPAIGN_ID,
        "child_iteration_id": iter_id,
        "hypothesis_id": branch["hypothesis_id"],
        "universe_selection": hypothesis["universe_selection"],
        "promotion_eligible": promotion_values.pop(),
        "contract_status": branch["contract_status"],
        "capability_ids": ["market.alpaca_bars"],
        "data_feasibility_binding": _binding(feasibility_path, root),
    }
    if branch["contract_status"] == "dependency_skipped":
        payload["blockers"] = branch["blockers"]
    else:
        membership_mode = {
            "fixed_long_lived": "fixed_long_lived_symbols",
            "cross_asset": "fixed_cross_asset_symbols",
            "static_hotspot_control": "static_hotspot_control",
        }[branch["universe_selection"]]
        payload["universe_definition"] = {
            "membership_mode": membership_mode,
            "symbols": branch["symbols"],
            "selection_rule": "campaign_preregistered_fixed_symbol_inventory_no_post_result_substitution",
            "selection_frozen_at": PREREGISTERED_AT,
            "survivorship_bias_control_only": iter_id == "mom_breadth_static_hotspot_control_r1",
        }
    path = _iteration_dir(iter_id) / "universe-contract.json"
    write_json(root / path, payload)
    return path


def _write_candidate_manifest(
    root: Path,
    *,
    campaign: dict[str, Any],
    iter_id: str,
    branch: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> Path:
    candidates = _candidate_rows(
        root,
        campaign=campaign,
        iter_id=iter_id,
        branch=branch,
        specs=specs,
        with_evidence_hashes=True,
    )
    path = _iteration_dir(iter_id) / "candidate-manifest.json"
    payload = _candidate_manifest_payload(
        campaign=campaign,
        iter_id=iter_id,
        candidates=candidates,
        specs=specs,
        contracts=_manifest_contracts(root, iter_id),
    )
    write_json(root / path, payload)
    return path


def _candidate_manifest_payload(
    *,
    campaign: dict[str, Any],
    iter_id: str,
    candidates: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
    contracts: dict[str, dict[str, dict[str, str]]],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "manifest_type": "generic_candidate_family_v1",
        "campaign_id": CAMPAIGN_ID,
        "iter_id": iter_id,
        "generated_at": PREREGISTERED_AT,
        "generated_before_backtest": True,
        "model_training_authorized": False,
        "candidate_count": len(candidates),
        "trial_accounting": _trial_accounting_identity(campaign),
        "spec_hashes": {row["spec_path"]: specs[row["candidate_id"]]["hash"] for row in candidates},
        "contracts": contracts,
        "candidates": candidates,
    }


def finalize_after_knowledge(root: Path) -> None:
    base = root.resolve()
    campaign = _campaign(base)
    specs = _load_specs(base, campaign)
    _verify_phase_one_locks(base, campaign=campaign, specs=specs)
    for iter_id, branch in BRANCHES.items():
        iteration = base / _iteration_dir(iter_id)
        assessment_path = iteration / "knowledge-assessment.json"
        scout_path = iteration / "knowledge-scout.json"
        context_path = iteration / "knowledge-context.json"
        for path in [assessment_path, scout_path, context_path]:
            if not path.is_file():
                raise FileNotFoundError(f"knowledge phase incomplete: {path}")
        assessment = _read_json(assessment_path)
        if assessment.get("status") != "ok":
            raise ValueError(
                f"knowledge assessment blocked for {iter_id}: {assessment.get('blocked')}"
            )
        if assessment.get("external_brief_sha256") != _sha256(iteration / "external-brief.json"):
            raise ValueError(f"knowledge assessment stale for {iter_id}")

        model_reuse_path = iteration / "model-reuse-decision.json"
        model_reuse = _read_json(model_reuse_path)
        model_reuse["round_decision"] = {
            "action": "no_model_training_deterministic_discovery_round",
            "retrain": False,
            "warm_start": False,
            "reason": "The campaign tests orthogonal deterministic mechanisms first; prior failed models remain negative memory and receive no trial budget.",
            "status_provenance_required_for_any_future_model": True,
        }
        write_json(model_reuse_path, model_reuse)

        feasibility_path = _write_data_feasibility(
            base,
            campaign=campaign,
            iter_id=iter_id,
            branch=branch,
            specs=specs,
        )
        _write_universe_contract(
            base,
            campaign=campaign,
            iter_id=iter_id,
            branch=branch,
            feasibility_path=feasibility_path,
        )
        _write_candidate_manifest(
            base,
            campaign=campaign,
            iter_id=iter_id,
            branch=branch,
            specs=specs,
        )
        candidates = _branch_candidates(campaign, iter_id)
        write_json(
            iteration / "search-space.json",
            _search_space(
                campaign=campaign,
                iter_id=iter_id,
                branch=branch,
                candidates=candidates,
                specs=specs,
                root=base,
                finalized=True,
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--finalize-after-knowledge", action="store_true")
    args = parser.parse_args()
    if args.finalize_after_knowledge:
        finalize_after_knowledge(args.root)
    else:
        prepare(args.root)


if __name__ == "__main__":
    main()
