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
SOURCE_CARDS_PATH = Path("reports/harness/source_cards") / f"{STRATEGY_STEM}.jsonl"
PRICE_SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
PRICE_QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
CBOE_SNAPSHOT_DIR = Path("data/research/cboe_vix_term_structure_20260814_pairing_v1")
CBOE_SNAPSHOT_PATH = CBOE_SNAPSHOT_DIR / "snapshot-manifest.json"
CBOE_PACKET_PATH = CBOE_SNAPSHOT_DIR / "cboe-volatility-packets.jsonl"
BASE_SPEC_PATH = Path("strategy_specs/drafts/us_high_beta_sleeve_ensemble_r1_d01.yaml")
PRIMARY_CANDIDATE_ID = "V1D02"
PRIMARY_SPEC_PATH = Path("strategy_specs/drafts/us_vix_term_structure_overlay_r1_d02.yaml")
FACTOR_LIBRARY_PATH = Path("reports/research/us_vix_term_structure_overlay_r1-factor-library.json")
SOURCE_ITERATION_LOCK_PATH = Path(
    "reports/research/iterations/mom_vix_term_structure_overlay_r1/lock-set/"
    "historical-evaluation-lock.json"
)
SOURCE_ITERATION_LOCK_SHA256 = "97e8c8c61159a356e54abb64f7a10fb08ba442727ba4d9fc2d122e04fe0ed946"
FACTOR_ID = "vix_vix3m_term_structure_state"

PRIOR_EFFECTIVE_TRIAL_COUNT = 8138
ROUND_CANDIDATE_COUNT = 9
COUNTED_TRIAL_DELTA = ROUND_CANDIDATE_COUNT
EFFECTIVE_TRIAL_COUNT = PRIOR_EFFECTIVE_TRIAL_COUNT + COUNTED_TRIAL_DELTA
IS_IMPLEMENTATION_REPAIR = False
SHARPE_FLOOR = 0.8
SHARPE_OPERATOR = "greater_than_or_equal"
PRIMARY_COST_BPS = 20.0
PLACEBO_SEED = 15108
MODEL_SEED = 16101
# F01 is a missing-modality identity control.  It must not fit a second
# estimator: its target stream is required to be byte-identical to M01.
ML_CANDIDATE_IDS = {"V1M01", "V1M02", "V1C01", "V1P01"}
PRICE_ONLY_CANDIDATE_IDS = {"V1Q01", "V1M01", "V1F01"}
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

# These semantics are copied into the generated contracts and specs. The
# evaluation runner must consume the frozen values rather than selecting state
# or overlap behavior after seeing returns.
VIX_STATE_MACHINE = {
    "thresholds": {
        "risk_on_ratio_max": 0.95,
        "stress_ratio_min": 1.00,
        "crisis_ratio_min": 1.08,
        "crisis_vix_min": 40.0,
    },
    "raw_states": {
        "risk_on_candidate": "ratio <= risk_on_ratio_max and vix_close < crisis_vix_min",
        "transition": "risk_on_ratio_max < ratio < stress_ratio_min and vix_close < crisis_vix_min",
        "stress": "stress_ratio_min <= ratio < crisis_ratio_min and vix_close < crisis_vix_min",
        "crisis": "ratio >= crisis_ratio_min or vix_close >= crisis_vix_min",
    },
    "route_states": {
        "risk_on": {"TQQQ": 1.0},
        "transition": {"QQQ": 1.0},
        "crisis": {"BIL": 1.0},
    },
    "confirmation": {
        "required_consecutive_sessions": 2,
        "counts_current_observation": True,
        "crisis_is_immediate": True,
        "reset_on_missing_or_non_risk_on": True,
        "first_confirmation_route": "transition",
        "candidate_confirmation_state": "consecutive_risk_on_candidate_observations",
        "subsequent_candidate_sessions_remain_risk_on": True,
        "risk_on_hysteresis_hold": "while ratio < stress_ratio_min and vix_close < crisis_vix_min",
        "risk_on_exit_ratio_min": 1.00,
        "risk_on_exit_action": "transition",
        "missing_observation_action": "explicit_candidate_fallback",
    },
    "stress_route": "transition",
    "initial_route_state": "transition",
    "state_update_order": [
        "missing",
        "crisis",
        "risk_on_candidate_confirmation",
        "risk_on_exit",
        "raw_route",
    ],
}
ML_OVERLAY_CONTRACT = {
    "duration_sessions": 5,
    "step_down_map": {"TQQQ": "QQQ", "QQQ": "BIL", "BIL": "BIL"},
    "overlap_policy": "reset_to_five_sessions_from_latest_effective_trigger",
    "effective_override_definition": "execution_sessions_where_overlay_target_differs_from_exact_fallback_target",
    "insufficient_model_action": "exact_fallback_target_identity",
    "missing_modality_action": "candidate_specific_exact_fallback",
    "decision_stream": "one_target_decision_per_regular_session_at_next_open",
    "trigger_eligibility": "probability_lte_threshold_and_step_down_target_differs_from_same_session_fallback_target",
    "override_retrigger": "only_a_new_low_survival_prediction_restarts_the_five_session_clock",
}

BASE_CONTRACT_IDS = {
    "data_contract": "vix_r1_data_v2",
    "feature_contract": "vix_r1_features_v3",
    "label_contract": "vix_r1_labels_v3",
    "validation_contract": "vix_r1_validation_v3",
    "cost_contract": "vix_r1_costs_v3",
    "benchmark_contract": "vix_r1_benchmarks_v2",
}
REPAIR_CONTRACT_IDS = {key: f"{value}_implfix1" for key, value in BASE_CONTRACT_IDS.items()}
CONTRACT_IDS = dict(BASE_CONTRACT_IDS)
CONTRACT_FILENAMES = {
    "data_contract": "data-contract.json",
    "feature_contract": "feature-contract.json",
    "label_contract": "label-contract.json",
    "validation_contract": "validation-contract.json",
    "cost_contract": "cost-contract.json",
    "benchmark_contract": "benchmark-contract.json",
}
CONTRACT_GROUPS = {
    "data_contract": "data",
    "feature_contract": "features",
    "label_contract": "labels",
    "validation_contract": "validation",
    "cost_contract": "costs",
    "benchmark_contract": "benchmarks",
}


def configure_iteration(iter_id: str) -> None:
    if iter_id not in ALLOWED_ITERATION_STEMS:
        raise ValueError(f"unsupported VIX iteration identity: {iter_id}")
    global ITER_ID
    global STRATEGY_STEM
    global ITERATION_DIR
    global SOURCE_CARDS_PATH
    global PRIMARY_SPEC_PATH
    global FACTOR_LIBRARY_PATH
    global PRIOR_EFFECTIVE_TRIAL_COUNT
    global COUNTED_TRIAL_DELTA
    global EFFECTIVE_TRIAL_COUNT
    global IS_IMPLEMENTATION_REPAIR
    global SHARPE_FLOOR
    global SHARPE_OPERATOR
    global CONTRACT_IDS
    ITER_ID = iter_id
    STRATEGY_STEM = ALLOWED_ITERATION_STEMS[iter_id]
    ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
    SOURCE_CARDS_PATH = Path("reports/harness/source_cards") / f"{STRATEGY_STEM}.jsonl"
    PRIMARY_SPEC_PATH = Path(f"strategy_specs/drafts/{STRATEGY_STEM}_d02.yaml")
    FACTOR_LIBRARY_PATH = Path("reports/research") / f"{STRATEGY_STEM}-factor-library.json"
    IS_IMPLEMENTATION_REPAIR = iter_id == REPAIR_ITER_ID
    PRIOR_EFFECTIVE_TRIAL_COUNT = 8147 if IS_IMPLEMENTATION_REPAIR else 8138
    COUNTED_TRIAL_DELTA = 0 if IS_IMPLEMENTATION_REPAIR else ROUND_CANDIDATE_COUNT
    EFFECTIVE_TRIAL_COUNT = PRIOR_EFFECTIVE_TRIAL_COUNT + COUNTED_TRIAL_DELTA
    SHARPE_FLOOR = 1.0 if IS_IMPLEMENTATION_REPAIR else 0.8
    SHARPE_OPERATOR = (
        "strictly_greater_than" if IS_IMPLEMENTATION_REPAIR else "greater_than_or_equal"
    )
    CONTRACT_IDS = dict(REPAIR_CONTRACT_IDS if IS_IMPLEMENTATION_REPAIR else BASE_CONTRACT_IDS)


ROLE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "V1R01",
        "suffix": "r01",
        "path": "locked_replication_diagnostic",
        "role": "sealed_S1D01_runner_data_cost_replication",
        "method": "fixed_50pct_TQQQ_anchor_plus_monthly_QQQ_SMA200_sleeve",
        "ablation": "locked_prior_runner_replication_control",
        "fallback": "BIL_for_tactical_sleeve_only",
        "promotion_eligible": False,
    },
    {
        "candidate_id": "V1Q01",
        "suffix": "q01",
        "path": "deterministic_price_only",
        "role": "price_only_momentum_control",
        "method": "QQQ_63_session_momentum_sign_to_TQQQ_or_BIL",
        "ablation": "quant_only_deterministic_control",
        "fallback": "BIL",
        "promotion_eligible": True,
    },
    {
        "candidate_id": "V1V01",
        "suffix": "v01",
        "path": "deterministic_vix_only",
        "role": "vix_vix3m_term_structure_exposure_ladder",
        "method": "paired_term_structure_hysteresis_to_TQQQ_QQQ_BIL",
        "ablation": "new_modality_only_deterministic",
        "fallback": "V1Q01_then_BIL_on_price_failure",
        "promotion_eligible": True,
    },
    {
        "candidate_id": "V1D02",
        "suffix": "d02",
        "path": "deterministic_combined",
        "role": "price_plus_vix_consensus_exposure_ladder",
        "method": "QQQ_momentum_and_VIX_term_structure_consensus_to_TQQQ_QQQ_BIL",
        "ablation": "combined_deterministic",
        "fallback": "V1Q01",
        "promotion_eligible": True,
    },
    {
        "candidate_id": "V1M01",
        "suffix": "m01",
        "path": "trained_ml_price_only",
        "role": "price_feature_logistic_tail_risk_overlay",
        "method": "matched_prequential_logistic_with_price_features_only",
        "ablation": "matched_ML_price_only",
        "fallback": "V1Q01",
        "promotion_eligible": True,
    },
    {
        "candidate_id": "V1M02",
        "suffix": "m02",
        "path": "trained_ml_vix_only",
        "role": "vix_feature_logistic_tail_risk_overlay",
        "method": "matched_prequential_logistic_with_VIX_features_only",
        "ablation": "matched_ML_modality_only",
        "fallback": "V1Q01",
        "promotion_eligible": True,
    },
    {
        "candidate_id": "V1C01",
        "suffix": "c01",
        "path": "trained_ml_combined",
        "role": "combined_price_and_vix_logistic_tail_risk_overlay",
        "method": "matched_prequential_logistic_with_price_plus_VIX_features",
        "ablation": "matched_ML_combined",
        "fallback": "V1M01_on_missing_VIX_then_V1Q01",
        "promotion_eligible": True,
    },
    {
        "candidate_id": "V1F01",
        "suffix": "f01",
        "path": "missing_modality",
        "role": "exact_missing_vix_combined_model_fallback",
        "method": "injected_missing_Cboe_packet_exact_V1M01_target_identity",
        "ablation": "missing_modality_exact_fallback",
        "fallback": "V1M01_then_V1Q01",
        "promotion_eligible": False,
    },
    {
        "candidate_id": "V1P01",
        "suffix": "p01",
        "path": "placebo",
        "role": "combined_logistic_train_only_vix_placebo",
        "method": "seed_15108_fold_local_train_only_permutation_of_VIX_feature_rows",
        "ablation": "matched_ML_new_modality_placebo",
        "fallback": "V1Q01",
        "promotion_eligible": False,
    },
)

SOURCE_CARDS: tuple[dict[str, Any], ...] = (
    {
        "claim_id": "vix_r1_cboe_vix3m_term_structure",
        "claim": "Cboe defines VIX3M as a constant measure of three-month SPX option implied volatility, distinguishes it from the one-month VIX index, and states that using VIX3M with VIX provides insight into the SPX implied-volatility term structure.",
        "source_url": "https://www.cboe.com/us/indices/dashboard/vix3m/",
        "source_type": "exchange_official_docs",
        "published_or_updated_at": "2026-08-14",
        "retrieved_document_sha256": "18347e3d8c2eb02d17e6f5ca41925c65cd475e3542b9ac1bc4eb787ac0b42c38",
        "applies_to": ["volatility_term_structure", "factor_generation", "V1V01", "V1D02"],
        "impact_on_spec": "Use the same-date VIX/VIX3M close ratio as a research-only regime input and never describe it as a tradable spread.",
        "limitations": "The product page explains the indices but does not establish Alpha, a threshold, exact publication latency, or execution quality.",
        "verification_method": "fresh_official_exchange_page_retrieval",
    },
    {
        "claim_id": "vix_r1_cboe_paired_history",
        "claim": "Cboe publishes separate official daily-history CSV files for VIX and VIX3M; the frozen pairing-v1 research snapshot retains their raw hashes, intersects same-date observations without forward fill, and records zero unmatched US-equity sessions over the paired range.",
        "source_url": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv",
        "source_type": "exchange_official_docs",
        "published_or_updated_at": "2026-08-13",
        "retrieved_document_sha256": "6b0a7d586fa19918d194fed1103e9075607e037f6515f66281f864dedb4e4449",
        "applies_to": ["market_data", "point_in_time_replay", "pairing_integrity"],
        "impact_on_spec": "Bind the successor only to the immutable pairing-v1 snapshot and fail closed on a missing leg, duplicate date, nonfinite value, or stale packet.",
        "limitations": "A historical download captured in 2026 is not historical first-seen evidence and remains research-only until forward collection latency is verified.",
        "verification_method": "fresh_official_csv_retrieval_and_local_hash_pairing_audit",
    },
    {
        "claim_id": "vix_r1_cboe_vix_methodology",
        "claim": "Cboe's official volatility-index methodology defines the VIX family from SPX option prices and target expected-volatility horizons; the index values are derived reference measures rather than executable ETF prices.",
        "source_url": "https://cdn.cboe.com/resources/indices/Volatility_Index_Methodology_Cboe_Volatility_Index.pdf",
        "source_type": "exchange_official_docs",
        "published_or_updated_at": "2024-01-01",
        "retrieved_document_sha256": "5e0e8dd278a5e4c2e0315ff573b60a314d31946841e6fc67eac784dfba729622",
        "applies_to": ["index_methodology", "nontradable_input", "execution_separation"],
        "impact_on_spec": "Trade only separately validated long-only ETFs; VIX and VIX3M remain information inputs with no direct order mapping.",
        "limitations": "Methodology does not prove that daily historical files were first visible at a particular intraday timestamp.",
        "verification_method": "fresh_official_methodology_pdf_retrieval",
    },
    {
        "claim_id": "vix_r1_vixy_is_futures_not_spot",
        "claim": "ProShares states that VIXY seeks exposure to an index of short-term VIX futures contracts rather than the spot VIX index, so a VIX futures ETP cannot be substituted for the VIX/VIX3M index inputs without changing the hypothesis.",
        "source_url": "https://www.proshares.com/our-etfs/strategic/vixy",
        "source_type": "provider_official_docs",
        "published_or_updated_at": "2026-08-14",
        "retrieved_document_sha256": "55ec2f6c06eb083db34d6ef8d77a1ded9a0d4c66d81d50e5326a21924a836eca",
        "applies_to": ["instrument_identity", "vix_futures", "factor_integrity"],
        "impact_on_spec": "Do not backfill missing VIX or VIX3M observations with VIXY and do not trade VIXY in this long-beta exposure ladder.",
        "limitations": "The issuer page is a product contract, not evidence that the proposed term-structure signal is profitable.",
        "verification_method": "fresh_official_fund_page_retrieval",
    },
    {
        "claim_id": "vix_r1_alpaca_market_data_scope",
        "claim": "Alpaca documents US-stock historical data availability since 2016 and distinguishes limited IEX coverage from all-US-exchange coverage, supporting an explicit SIP feed binding for the frozen ETF price panel.",
        "source_url": "https://docs.alpaca.markets/docs/about-market-data-api",
        "source_type": "provider_official_docs",
        "published_or_updated_at": "2025-09-24",
        "retrieved_document_sha256": "5fadeae03c9e86439af84657b51ac7adaf9e86caf251cdb775cd5057ca745fdf",
        "applies_to": ["market_data", "SIP", "provider_coverage"],
        "impact_on_spec": "Use the immutable SIP daily bundle and reject IEX, cache, or fixture fallback for counted historical evidence.",
        "limitations": "Feed identity does not establish bar correctness, corporate-action lineage, survivorship freedom, or future subscription access.",
        "verification_method": "fresh_official_provider_page_retrieval",
    },
    {
        "claim_id": "vix_r1_tqqq_daily_target_path_risk",
        "claim": "ProShares states that TQQQ targets three times the daily Nasdaq-100 return before fees and expenses and warns that returns over longer holding periods can differ significantly because volatility and path matter.",
        "source_url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
        "source_type": "provider_official_docs",
        "published_or_updated_at": "2026-08-14",
        "retrieved_document_sha256": "75014773c0625a6c2a9c1634c54e5824c63419d0af4572ba384a8ea5e2561ad9",
        "applies_to": ["leveraged_etf", "path_dependency", "benchmark_definition"],
        "impact_on_spec": "Measure realized TQQQ upside/downside capture and drawdown instead of assuming a constant three-times annual return.",
        "limitations": "The issuer objective does not validate the VIX thresholds, costs, or next-open fills.",
        "verification_method": "fresh_official_fund_page_retrieval",
    },
    {
        "claim_id": "vix_r1_vix_basis_paper",
        "claim": "Crossref records Simon and Campasano's peer-reviewed paper The VIX Futures Basis: Evidence and Trading Strategies, which studies information in the relationship between VIX and VIX futures and establishes a relevant but not directly transferable volatility-curve signal family.",
        "source_url": "https://doi.org/10.3905/jod.2014.21.3.054",
        "source_type": "paper",
        "published_or_updated_at": "2014-02-28",
        "retrieved_document_sha256": "d22e2c1e15a77c85fbd3390651ae226b3274e53fda33907831abac56bdba2c34",
        "applies_to": ["volatility_curve", "signal_research", "basis"],
        "impact_on_spec": "Treat curve shape as a candidate risk-state input while requiring local long-ETF OOS and cost evidence.",
        "limitations": "A VIX-futures basis strategy is not the same instrument, target, or execution contract as VIX/VIX3M timing of TQQQ.",
        "verification_method": "fresh_crossref_official_metadata",
    },
    {
        "claim_id": "vix_r1_vix_term_structure_paper",
        "claim": "Crossref records Luo and Zhang's paper The Term Structure of VIX, providing a primary research identity for studying the relation among VIX horizons rather than relying on a single volatility level.",
        "source_url": "https://doi.org/10.1002/fut.21572",
        "source_type": "paper",
        "published_or_updated_at": "2012-08-16",
        "retrieved_document_sha256": "4c6095460c0a20f629c2bc3c98aa411504a9fc446b88451d3ff385c48d138c4d",
        "applies_to": ["volatility_term_structure", "factor_generation", "horizon_comparison"],
        "impact_on_spec": "Preregister both the VIX/VIX3M ratio and normalized slope and compare them against a VIX-level-only interpretation.",
        "limitations": "Paper metadata and term-structure theory do not choose profitable local thresholds or establish ETF execution parity.",
        "verification_method": "fresh_crossref_official_metadata",
    },
    {
        "claim_id": "vix_r1_vix_futures_signals_paper",
        "claim": "Crossref records Avellaneda, Li, Papanicolaou, and Wang's paper Trading Signals in VIX Futures, supporting the existence of systematic volatility-curve signal research while requiring instrument-specific validation.",
        "source_url": "https://doi.org/10.1080/1350486X.2021.2010584",
        "source_type": "paper",
        "published_or_updated_at": "2021-05-04",
        "retrieved_document_sha256": "3846ac8c7c827d995cc5d416840eb76c2d29261e7f8188826ae85c8f229a0e49",
        "applies_to": ["volatility_signals", "systematic_strategy", "instrument_transfer"],
        "impact_on_spec": "Use a bounded deterministic curve-state core before granting ML complexity credit and retain a separate long-ETF benchmark family.",
        "limitations": "VIX-futures trading results do not transfer automatically to long-only QQQ/TQQQ/BIL allocation.",
        "verification_method": "fresh_crossref_official_metadata",
    },
    {
        "claim_id": "vix_r1_volatility_managed_portfolios",
        "claim": "Crossref records Moreira and Muir's peer-reviewed Volatility-Managed Portfolios, a relevant methodology reference for reducing risky exposure when volatility is high rather than treating volatility only as a return forecast.",
        "source_url": "https://doi.org/10.1111/jofi.12513",
        "source_type": "paper",
        "published_or_updated_at": "2017-05-15",
        "retrieved_document_sha256": "8740815e094f17a0339128ce9951ebd1c9491e39f292dfc948e789bd97da7446",
        "applies_to": ["volatility_management", "risk_sizing", "deterministic_baseline"],
        "impact_on_spec": "Interpret the Cboe curve primarily as an exposure and tail-risk state and compare full-return and drawdown effects.",
        "limitations": "The paper does not validate daily-reset leverage, VIX/VIX3M cutoffs, or this sample.",
        "verification_method": "fresh_crossref_official_metadata",
    },
    {
        "claim_id": "vix_r1_model_comparison_with_costs",
        "claim": "The Journal of Finance paper Model Comparison with Transaction Costs reports that omitting implementation costs can bias model comparisons toward high-turnover signals and change attainable frontier conclusions.",
        "source_url": "https://doi.org/10.1111/jofi.13225",
        "source_type": "paper",
        "published_or_updated_at": "2023-04-12",
        "retrieved_document_sha256": "b4890911430b9885d730923ba0db87551d5285e397ae2bc247452dbc3a53906f",
        "applies_to": ["transaction_costs", "model_comparison", "ML_policy_value"],
        "impact_on_spec": "Bind 10/20/40 bps costs before fitting and credit ML only for positive realized after-cost override value.",
        "limitations": "The paper studies general model comparison, not the local Cboe signal or broker fills.",
        "verification_method": "reused_fresh_crossref_metadata_from_R1",
    },
    {
        "claim_id": "vix_r1_probability_calibration_methods",
        "claim": "Crossref records Niculescu-Mizil and Caruana's Predicting Good Probabilities with Supervised Learning, which compares probability calibration methods and reports that calibration behavior and data requirements differ across learning algorithms.",
        "source_url": "https://doi.org/10.1145/1102351.1102430",
        "source_type": "paper",
        "published_or_updated_at": "2005-01-01",
        "retrieved_document_sha256": "4a96bffa61744078aedd96a10e13d2d745c5d0f9ce19748f0841aeeb18a3369c",
        "applies_to": ["probability_calibration", "Platt_scaling", "ML_validation"],
        "impact_on_spec": "Fit chronological Platt calibration only after minimum class and row checks, record calibrated Brier scores, and deny ML credit when calibration evidence is missing or invalid.",
        "limitations": "The paper does not study financial time series, prequential validation, transaction costs, or this strategy's probability threshold.",
        "verification_method": "fresh_crossref_official_metadata",
    },
    {
        "claim_id": "vix_r1_calibration_sample_size_risk",
        "claim": "Crossref metadata and the publisher abstract for Calibration: the Achilles Heel of Predictive Analytics state that calibration must be evaluated during validation and emphasize balancing model complexity with available sample size.",
        "source_url": "https://doi.org/10.1186/s12916-019-1466-7",
        "source_type": "paper",
        "published_or_updated_at": "2019-12-01",
        "retrieved_document_sha256": "de50791b7dcb4e804908b2a799144da44d9940c8bc9dcb04778dcdacfc625284",
        "applies_to": ["probability_calibration", "sample_size", "ML_validation"],
        "impact_on_spec": "Require explicit calibration row and class minima at every refit and treat absent, undersized, or invalid calibration as a failed ML contribution gate rather than a silent fallback success.",
        "limitations": "The article is written for clinical prediction; its general calibration warning does not establish financial Alpha or select local sample minima.",
        "verification_method": "fresh_crossref_official_metadata_and_publisher_abstract",
    },
    {
        "claim_id": "vix_r1_selective_classification_reject_option",
        "claim": "Crossref records Herbei and Wegkamp's Classification with Reject Option, whose abstract studies binary classifiers that abstain when conditional class probabilities are too close for a reliable decision.",
        "source_url": "https://doi.org/10.1002/cjs.5550340410",
        "source_type": "paper",
        "published_or_updated_at": "2006-12-01",
        "retrieved_document_sha256": "a9ddae66f9b0cd235c0cb416e863964126b0a53d398c307f62fc2e216a7ab591",
        "applies_to": ["selective_prediction", "abstention", "deterministic_fallback"],
        "impact_on_spec": "Treat abstention as an explicit deterministic fallback policy and measure coverage and after-cost override value; abstention alone is not independent ML Alpha.",
        "limitations": "Reject-option classification theory does not define a trading action, transaction-cost objective, or profitable coverage threshold for this strategy.",
        "verification_method": "fresh_crossref_official_metadata_and_publisher_abstract",
    },
    {
        "claim_id": "vix_r1_deflated_sharpe_method",
        "claim": "Crossref records The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality, identifying the method used to penalize the full strategy-search history.",
        "source_url": "https://doi.org/10.3905/jpm.2014.40.5.094",
        "source_type": "paper",
        "published_or_updated_at": "2014-09-30",
        "retrieved_document_sha256": "d50cf71520060892516920dbb2ddce68bb3f21cdb77ad62530d066fbdd52f521",
        "applies_to": ["multiple_testing", "DSR", "backtest_forensics"],
        "impact_on_spec": "Carry forward all 8,138 prior effective trials and add every counted VIX candidate before computing DSR.",
        "limitations": "Passing DSR would not remove data provenance, capacity, or execution risks.",
        "verification_method": "reused_fresh_crossref_metadata_from_R1",
    },
    {
        "claim_id": "vix_r1_probability_backtest_overfitting_method",
        "claim": "Crossref records Bailey, Borwein, Lopez de Prado, and Zhu's Probability of Back-Test Overfitting paper, providing the primary methodology identity for CSCV/PBO diagnostics.",
        "source_url": "https://doi.org/10.2139/ssrn.2326253",
        "source_type": "paper",
        "published_or_updated_at": "2013-01-01",
        "retrieved_document_sha256": "c7235399778e4fe7fd8d5746b172170441e749a37ec8f3af60dcda3e386e5f7f",
        "applies_to": ["multiple_testing", "PBO", "backtest_forensics"],
        "impact_on_spec": "Use eight ordered blocks, all 70 directional four-versus-four partitions, and invariant tie handling.",
        "limitations": "PBO is a selection-risk diagnostic and cannot establish causal Alpha or future performance.",
        "verification_method": "reused_fresh_crossref_metadata_from_R1",
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(path: Path, root: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": _sha256(root / path)}


def _binding_with_size(path: Path, root: Path) -> dict[str, Any]:
    binding: dict[str, Any] = _binding(path, root)
    binding["size_bytes"] = (root / path).stat().st_size
    return binding


def _canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _spec_path(row: dict[str, Any]) -> Path:
    return Path(f"strategy_specs/drafts/{STRATEGY_STEM}_{row['suffix']}.yaml")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, width=100), encoding="utf-8")


def _economic_spec_projection(payload: dict[str, Any]) -> dict[str, Any]:
    projection = copy.deepcopy(payload)
    projection.pop("name", None)
    projection.pop("research_design", None)
    return projection


def _load_source_iteration_lock(root: Path) -> dict[str, Any]:
    path = root / SOURCE_ITERATION_LOCK_PATH
    if _sha256(path) != SOURCE_ITERATION_LOCK_SHA256:
        raise ValueError("VIX repair parent lock SHA drifted")
    payload = json.loads(path.read_text(encoding="utf-8"))
    runtime = payload.get("runtime_contract", {})
    snapshots = runtime.get("candidate_specs", {})
    manifest_rows = runtime.get("manifest", {}).get("candidates", [])
    if (
        payload.get("iter_id") != BASE_ITER_ID
        or payload.get("lock_contract") != "vix_term_structure_overlay_r1_historical_evaluation_v1"
        or set(snapshots) != {row["candidate_id"] for row in ROLE_ROWS}
        or [row.get("candidate_id") for row in manifest_rows]
        != [row["candidate_id"] for row in ROLE_ROWS]
    ):
        raise ValueError("VIX repair parent lock candidate inventory drifted")
    return payload


def _repair_research_design(source: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    design = copy.deepcopy(source)
    design.update(
        {
            "iter_id": ITER_ID,
            "candidate_manifest_path": (ITERATION_DIR / "candidate-manifest.json").as_posix(),
            "data_feasibility_path": (ITERATION_DIR / "data-feasibility.json").as_posix(),
            "data_contract_path": (ITERATION_DIR / "data-contract.json").as_posix(),
            "holdout_contract_path": (ITERATION_DIR / "holdout-contract.json").as_posix(),
            "cost_contract_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
            "cumulative_trial_contract_path": (
                ITERATION_DIR / "cumulative-trial-contract.json"
            ).as_posix(),
            "source_cards_path": SOURCE_CARDS_PATH.as_posix(),
            "candidate_budget": ROUND_CANDIDATE_COUNT,
            "selection_objective": (
                "Pure implementation repair of the parent-locked candidate; no economic "
                "change or outcome-driven tuning. Promotion additionally requires the "
                "post-2026-08-15 strict primary-cost terminal-free OOS Sharpe > 1.0 gate."
            ),
            "anti_overfit_notes": [
                "All nine economic candidates were preregistered and counted in the parent iteration.",
                "This repair adds zero economic candidates and keeps effective DSR trials at 8,147.",
                "The failed parent run may have created up to 312 unpersisted refits; no model is reused.",
                "Only iteration identity, research bindings, and the stricter governance gate may differ.",
            ],
            "implementation_repair": {
                "contract": "vix_r1_pure_implementation_repair_v1",
                "source_iter_id": BASE_ITER_ID,
                "source_candidate_id": candidate_id,
                "effective_trial_increment": 0,
            },
        }
    )
    return design


def _build_repair_specs(root: Path) -> dict[str, Any]:
    source_lock = _load_source_iteration_lock(root)
    snapshots = source_lock["runtime_contract"]["candidate_specs"]
    for row in ROLE_ROWS:
        candidate_id = row["candidate_id"]
        source_spec = copy.deepcopy(snapshots[candidate_id]["spec"])
        repair_spec = copy.deepcopy(source_spec)
        repair_spec["name"] = f"{STRATEGY_STEM}_{row['suffix']}"
        repair_spec["research_design"] = _repair_research_design(
            source_spec["research_design"], candidate_id
        )
        if _economic_spec_projection(repair_spec) != _economic_spec_projection(source_spec):
            raise ValueError(f"VIX repair economic StrategySpec drifted: {candidate_id}")
        _write_yaml(root / _spec_path(row), repair_spec)
    return {row["candidate_id"]: load_strategy_spec(root / _spec_path(row)) for row in ROLE_ROWS}


def _packet_factor(field: str, description: str, default: float) -> dict[str, Any]:
    return {
        "source": "feature_packet",
        "path": CBOE_PACKET_PATH.as_posix(),
        "field": field,
        "default": default,
        "description": description,
        "params": {
            "resolver": "cboe_volatility_research_snapshot_v1",
            "availability_field": "visible_at",
            "same_date_pair_required": True,
            "forward_fill_allowed": False,
            "max_age_sessions": 1,
            "historical_first_seen_claim": False,
        },
    }


def _model_config(candidate_id: str) -> dict[str, Any]:
    feature_sets = {
        "V1M01": PRICE_FEATURES,
        "V1M02": VIX_FEATURES,
        "V1C01": (*PRICE_FEATURES, *VIX_FEATURES),
        "V1P01": (*PRICE_FEATURES, *VIX_FEATURES),
    }
    fallback_ids = {
        "V1M01": "V1Q01",
        "V1M02": "V1Q01",
        "V1C01": "V1M01",
        "V1P01": "V1Q01",
    }
    return {
        "features": list(feature_sets[candidate_id]),
        "kind": "logistic_regression_classifier",
        "label": {
            "type": "path_survival",
            "horizon_bars": 5,
            "max_drawdown_pct": 10.0,
            "min_terminal_return_pct": -6.0,
            "path_drawdown_reference": "running_open_peak",
        },
        "training": {
            "window_bars": 10000,
            "retrain_every_bars": 21,
            "retrain_schedule": "fixed_bars",
            "test_window_bars": 252,
            "purge_bars": 5,
            "embargo_bars": 5,
            "seed": MODEL_SEED,
        },
        "selection": {
            "method": "threshold",
            "threshold": 0.65,
            "operator": "less_than_or_equal",
        },
        "abstention": {
            "calibration_method": "chronological_platt_scaling",
            "calibration_fraction": 0.20,
            "minimum_fit_rows": 480,
            "minimum_calibration_rows": 120,
            "minimum_positive_class_rows": 24,
            "minimum_negative_class_rows": 24,
            "minimum_calibration_positive_class_rows": 6,
            "minimum_calibration_negative_class_rows": 6,
            "calibrator": {
                "kind": "logistic_regression",
                "C": 1.0,
                "penalty": "l2",
                "solver": "lbfgs",
                "max_iter": 1000,
                "use_training_seed": True,
            },
            "fallback_candidate_id": fallback_ids[candidate_id],
            "insufficient_data_action": "exact_target_identity_fallback",
        },
        "preprocessing": "standard_scaler",
        "hyperparameters": {
            "C": 1.0,
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 1000,
        },
        "baseline": "none",
    }


def _expression_factor(
    expression: str,
    description: str,
    *,
    default: float = 0.0,
    lookback: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "panel_symbol": "QQQ",
        "panel_operation": "identity",
        "resolver": "vix_term_structure_r1_panel_feature_v2",
    }
    if lookback is not None:
        params["lookback_sessions"] = lookback
    return {
        "source": "expression",
        "expression": expression,
        "default": default,
        "description": description,
        "params": params,
    }


def _price_factors() -> dict[str, Any]:
    return {
        "qqq_momentum_21": _expression_factor(
            "close / lag(close, 21) - 1",
            "Completed-close QQQ 21-session momentum.",
            lookback=21,
        ),
        "qqq_momentum_63": _expression_factor(
            "close / lag(close, 63) - 1",
            "Completed-close QQQ 63-session momentum.",
            lookback=63,
        ),
        "qqq_realized_volatility_21": _expression_factor(
            "stddev(close / lag(close, 1) - 1, 21)",
            "Trailing QQQ close-to-close volatility, known before the next open.",
            lookback=21,
        ),
        "qqq_drawdown_63": _expression_factor(
            "close / highest(close, 63) - 1",
            "QQQ drawdown from the trailing 63-session completed-close high.",
            lookback=63,
        ),
    }


def _vix_factors() -> dict[str, Any]:
    return {
        "vix_to_vix3m_ratio": _packet_factor(
            "vix_to_vix3m_ratio",
            "Paired Cboe VIX close divided by VIX3M close, available only at visible_at.",
            1.0,
        ),
        "normalized_term_slope": _packet_factor(
            "normalized_term_slope",
            "Paired normalized VIX3M-minus-VIX term slope.",
            0.0,
        ),
        "vix_close": _packet_factor("vix_close", "Cboe VIX close.", 40.0),
        "vix3m_close": _packet_factor("vix3m_close", "Cboe VIX3M close.", 40.0),
        "vix_high": _packet_factor("vix_high", "Cboe VIX daily high.", 40.0),
        "vix_low": _packet_factor("vix_low", "Cboe VIX daily low.", 40.0),
        "vix3m_high": _packet_factor("vix3m_high", "Cboe VIX3M daily high.", 40.0),
        "vix3m_low": _packet_factor("vix3m_low", "Cboe VIX3M daily low.", 40.0),
    }


def build_specs(root: Path) -> dict[str, Any]:
    if IS_IMPLEMENTATION_REPAIR:
        return _build_repair_specs(root)
    base = yaml.safe_load((root / BASE_SPEC_PATH).read_text(encoding="utf-8"))
    for row in ROLE_ROWS:
        candidate_id = row["candidate_id"]
        # Keep a byte-for-behavior replication of the sealed prior primary as a
        # diagnostic.  It is never eligible for selection or promotion.
        if candidate_id == "V1R01":
            spec = copy.deepcopy(base)
            spec["name"] = f"{STRATEGY_STEM}_{row['suffix']}"
            spec["description"] = (
                "Locked diagnostic replication of S1D01's fixed anchor/monthly trend route; "
                "it is not a new VIX hypothesis and has no promotion authority."
            )
            spec["lifecycle"] = "draft"
            spec["execution"]["backend"] = "nautilus_trader"
            spec["execution"]["mode"] = "manual_signal"
            spec["execution"]["broker"] = "none"
            spec["costs"]["slippage_bps"] = PRIMARY_COST_BPS
            notes = copy.deepcopy(spec.get("notes", {}))
            notes.update(
                {
                    "candidate_id": candidate_id,
                    "candidate_role": row["role"],
                    "method": row["method"],
                    "ablation": row["ablation"],
                    "replication_source_spec": BASE_SPEC_PATH.as_posix(),
                    "replication_source_candidate_id": "S1D01",
                    "factor_library_ids": ["fixed_anchor_monthly_trend_sleeve"],
                    "order_authority": False,
                    "broker_writes": False,
                }
            )
            spec["notes"] = notes
            spec["research_design"] = {
                "iter_id": ITER_ID,
                "candidate_manifest_path": (ITERATION_DIR / "candidate-manifest.json").as_posix(),
                "data_feasibility_path": (ITERATION_DIR / "data-feasibility.json").as_posix(),
                "data_contract_path": (ITERATION_DIR / "data-contract.json").as_posix(),
                "holdout_contract_path": (ITERATION_DIR / "holdout-contract.json").as_posix(),
                "cost_contract_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
                "cumulative_trial_contract_path": (
                    ITERATION_DIR / "cumulative-trial-contract.json"
                ).as_posix(),
                "source_cards_path": SOURCE_CARDS_PATH.as_posix(),
                "parameter_space": {"candidate_id": [candidate_id], "parameter_search": [False]},
                "candidate_budget": ROUND_CANDIDATE_COUNT,
                "selection_objective": "diagnostic replication only; never selected for promotion",
                "anti_overfit_notes": [
                    "Sealed S1D01 behavior is reused only to detect runner/data/cost drift.",
                    f"Effective trial count starts at {PRIOR_EFFECTIVE_TRIAL_COUNT} and includes all {ROUND_CANDIDATE_COUNT} new rows.",
                ],
                "validation_plan": ["locked_prior_runner_replication", "no_selection_credit"],
                "source_card_claim_ids": [card["claim_id"] for card in SOURCE_CARDS],
            }
            _write_yaml(root / _spec_path(row), spec)
            continue

        spec = copy.deepcopy(base)
        uses_vix = candidate_id in {"V1V01", "V1D02", "V1M02", "V1C01", "V1P01"}
        # VIX-primary rows declare only QQQ momentum for their explicit
        # fallback.  The matched price feature bundle is absent unless the
        # candidate actually consumes it.
        needs_price_control = True
        spec["name"] = f"{STRATEGY_STEM}_{row['suffix']}"
        spec["description"] = (
            f"Preregistered {candidate_id} role for the VIX/VIX3M term-structure successor: "
            f"{row['role']}. Research-only; no broker writes are authorized."
        )
        spec["universe"] = ["TQQQ", "QQQ", "BIL", "SPY", "XLK"]
        spec["lifecycle"] = "draft"
        spec["portfolio"] = {
            "mode": "hybrid_adaptive_router",
            "max_symbols_per_day": 1,
            "gross_exposure_limit": 1.0,
            "max_symbol_weight": 1.0,
            "same_day_flatten": False,
            "duplicate_signal_policy": "stable_signal_id",
            "selected_route_label": f"vix_term_structure_r1:{candidate_id}:{row['method']}",
        }
        spec["costs"] = {
            "commission_pct": 0.0,
            "slippage_bps": PRIMARY_COST_BPS,
            "impact_model": "linear",
            "impact_eta": 0.0,
            "impact_gamma": 0.0,
        }
        spec["execution"]["backend"] = "nautilus_trader"
        spec["execution"]["mode"] = "manual_signal"
        spec["execution"]["broker"] = "none"
        spec["execution"]["fill_assumption"] = "next_bar_open"
        spec["execution_policy"]["policy_id"] = "vix_term_structure_r1_protected_open_v1"
        spec["execution_policy"]["source_card_ids"] = [
            "vix_r1_tqqq_daily_target_path_risk",
            "vix_r1_alpaca_market_data_scope",
        ]
        spec["data"] = {
            "source": "alpaca",
            "symbol": "QQQ",
            "path": PRICE_SNAPSHOT_PATH.as_posix(),
            "feed": "sip",
        }
        spec["data_assumptions"] = {
            "source": "alpaca+cboe_global_indices" if uses_vix else "alpaca",
            "adjusted": True,
            "timezone": "America/New_York",
            "acquisition_tier": "research_strict",
            "immutable_snapshot_required": True,
            "snapshot_manifest_path": PRICE_SNAPSHOT_PATH.as_posix(),
            "session_scope": "regular",
            "forward_fill_allowed": False,
            "zero_return_substitution_allowed": False,
            "nonfinite_action": "fail_closed",
            "historical_first_seen_claim": False,
            "historical_quality_paper_eligible": False,
            "historical_quality_is_paper_authorization": False,
        }
        if uses_vix:
            spec["data_assumptions"]["external_factor_snapshot_manifest_path"] = (
                CBOE_SNAPSHOT_PATH.as_posix()
            )
        factors: dict[str, Any] = {}
        if candidate_id in {"V1Q01", "V1M01", "V1C01", "V1F01", "V1P01"}:
            factors.update(_price_factors())
        elif needs_price_control:
            factors["qqq_momentum_63"] = _price_factors()["qqq_momentum_63"]
        if uses_vix:
            factors.update(_vix_factors())
        spec["factors"] = factors
        if candidate_id in ML_CANDIDATE_IDS:
            spec["model"] = _model_config(candidate_id)
        else:
            spec.pop("model", None)
        spec["required_capabilities"] = ["market.alpaca_bars"]
        if uses_vix:
            spec["required_capabilities"].append("market.cboe_volatility_indices")

        parameter_space: dict[str, list[Any]] = {
            "candidate_id": [candidate_id],
            "parameter_search": [False],
        }
        if candidate_id in {"V1V01", "V1D02"}:
            parameter_space.update(
                {
                    "risk_on_ratio_max": [0.95],
                    "stress_ratio_min": [1.0],
                    "crisis_ratio_min": [1.08],
                    "crisis_vix_min": [40.0],
                    "exit_confirmation_sessions": [2],
                }
            )
        if needs_price_control:
            parameter_space["price_control_lookback_sessions"] = [63]
        if candidate_id in ML_CANDIDATE_IDS:
            parameter_space.update(
                {
                    "model_kind": ["logistic_regression_classifier"],
                    "label_horizon_sessions": [5],
                    "decision_cadence": ["every_regular_session"],
                    "retrain_every_sessions": [21],
                    "calibration_fraction": [0.20],
                    "selection_threshold": [0.65],
                    "override_duration_sessions": [5],
                }
            )
        parameter_space["placebo_seed"] = [PLACEBO_SEED if candidate_id == "V1P01" else None]
        spec["research_design"] = {
            "iter_id": ITER_ID,
            "candidate_manifest_path": (ITERATION_DIR / "candidate-manifest.json").as_posix(),
            "data_feasibility_path": (ITERATION_DIR / "data-feasibility.json").as_posix(),
            "data_contract_path": (ITERATION_DIR / "data-contract.json").as_posix(),
            "holdout_contract_path": (ITERATION_DIR / "holdout-contract.json").as_posix(),
            "cost_contract_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
            "cumulative_trial_contract_path": (
                ITERATION_DIR / "cumulative-trial-contract.json"
            ).as_posix(),
            "source_cards_path": SOURCE_CARDS_PATH.as_posix(),
            "parameter_space": parameter_space,
            "candidate_budget": ROUND_CANDIDATE_COUNT,
            "selection_objective": (
                "Meet the frozen strategy-group CAGR, TQQQ capture, drawdown, Sharpe, MAR, "
                "fold, DSR, PBO, cost, and ML incremental-value gates without changing "
                "thresholds after any candidate return is calculated."
            ),
            "anti_overfit_notes": [
                f"All {ROUND_CANDIDATE_COUNT} role configurations and seed 15108 are fixed before the first return calculation.",
                f"Effective trial count starts at {PRIOR_EFFECTIVE_TRIAL_COUNT} and includes every candidate in this round.",
                "Historical prices are globally exposed; no segment is described as an untouched holdout.",
                "The ML trio shares one label, cadence, split indices, estimator, and calibration contract; only declared feature sets differ.",
                "ML uses expanding prequential refits from a fixed common start, five-session purge/embargo, and exact deterministic fallbacks.",
            ],
            "validation_plan": [
                "four_chronological_oos_folds",
                "fixed_common_start_expanding_prequential_daily_decisions",
                "five_session_purge_and_embargo",
                "eight_block_all_70_directional_CSCV_PBO_partitions",
                "cumulative_trial_DSR",
                "full_benchmark_family",
                "ten_twenty_forty_bps",
                "matched_price_only_vix_only_combined_missing_and_placebo_ablations",
            ],
            "source_card_claim_ids": [card["claim_id"] for card in SOURCE_CARDS],
        }
        route_contract: dict[str, Any]
        if candidate_id == "V1Q01":
            route_contract = {
                "risk_on": "qqq_momentum_63 > 0",
                "targets": {"risk_on": {"TQQQ": 1.0}, "risk_off": {"BIL": 1.0}},
                "missing_or_stale": "BIL",
            }
        elif candidate_id == "V1V01":
            route_contract = {
                "state_machine": copy.deepcopy(VIX_STATE_MACHINE),
                "risk_on": "two consecutive risk_on_candidate observations; first remains transition, second enters risk_on",
                "transition": "raw transition/stress, first confirmation, or risk_on exit at ratio >= 1.00",
                "crisis": "raw crisis is immediate",
                "targets": copy.deepcopy(VIX_STATE_MACHINE["route_states"]),
                "missing_or_stale": "explicit_V1Q01_target_for_this_session",
            }
        elif candidate_id == "V1D02":
            route_contract = {
                "state_machine": copy.deepcopy(VIX_STATE_MACHINE),
                "price_risk_on": "qqq_momentum_63 > 0",
                "risk_on": "price_risk_on and vix_route_state == risk_on",
                "transition": "exactly_one_of_price_risk_on_or_vix_route_state == risk_on",
                "crisis": "price_risk_off and vix_route_state != risk_on",
                "targets": {
                    "risk_on": {"TQQQ": 1.0},
                    "transition": {"QQQ": 1.0},
                    "crisis": {"BIL": 1.0},
                },
                "missing_or_stale": "exact_V1Q01",
            }
        elif candidate_id in ML_CANDIDATE_IDS:
            route_contract = {
                "base_candidate": "V1Q01",
                "low_survival_action": "one_exposure_step_down_for_five_execution_sessions",
                "overlay_contract": copy.deepcopy(ML_OVERLAY_CONTRACT),
                "decision_cadence": "every_regular_session",
                "missing_or_stale": row["fallback"],
                "matched_model_contract": "same_label_indices_estimator_calibration_across_M01_M02_C01; F01_is_identity_only",
                "placebo_training_only": candidate_id == "V1P01",
            }
        else:
            route_contract = {"exact_target_identity": "V1M01", "injected_missing_modality": True}
        notes: dict[str, Any] = {
            "intent": (
                "Test whether a separately sourced implied-volatility term structure can "
                "improve long Nasdaq exposure timing where price-only ML failed to add value."
            ),
            "candidate_id": candidate_id,
            "candidate_role": row["role"],
            "method": row["method"],
            "ablation": row["ablation"],
            "fallback_candidate_id": row["fallback"],
            "factor_library_ids": [FACTOR_ID] if uses_vix else [],
            "route_contract": route_contract,
            "feature_set": list(spec.get("model", {}).get("features", []))
            if spec.get("model")
            else [],
            "semantic_stock_budget": 0.0,
            "placebo_seed": PLACEBO_SEED if candidate_id == "V1P01" else None,
            "order_authority": False,
            "broker_writes": False,
            "open_questions": [
                "Forward Cboe collection latency and Python/Nautilus availability parity must pass before paper readiness.",
                "The trial capability and historical snapshot cannot by themselves establish paper-ready market evidence.",
            ],
        }
        if uses_vix:
            notes["external_factor_binding"] = {
                "capability_id": "market.cboe_volatility_indices",
                "snapshot_manifest_path": CBOE_SNAPSHOT_PATH.as_posix(),
                "packet_path": CBOE_PACKET_PATH.as_posix(),
                "availability_field": "visible_at",
                "generic_feature_packet_contract": "research_snapshot_with_actual_fetch_time",
                "historical_first_seen_claim": False,
                "paper_ready": False,
            }
        if candidate_id == "V1F01":
            notes["missing_modality_contract"] = {
                "packet_injection": "explicit_missing_or_stale_Cboe_packet",
                "target_identity": "byte_identical_to_V1M01",
                "silent_default_forbidden": True,
            }
        spec["notes"] = notes
        _write_yaml(root / _spec_path(row), spec)
    return {row["candidate_id"]: load_strategy_spec(root / _spec_path(row)) for row in ROLE_ROWS}


def write_source_cards(root: Path) -> None:
    verified_at = "2026-08-14T17:00:00Z"
    rows = []
    for source in SOURCE_CARDS:
        row = {
            "iteration_id": ITER_ID,
            "verification_status": "source_verified",
            "verified_at": verified_at,
            "verification_method": source["verification_method"],
            "claim_id": source["claim_id"],
            "claim": source["claim"],
            "source_url": source["source_url"],
            "source_type": source["source_type"],
            "accessed_at": "2026-08-14",
            "document_updated_at": source["published_or_updated_at"],
            "retrieved_document_sha256": source["retrieved_document_sha256"],
            "applies_to": source["applies_to"],
            "impact_on_spec": source["impact_on_spec"],
            "limitations": source["limitations"],
        }
        rows.append(json.dumps(row, sort_keys=True, separators=(",", ":")))
    path = root / SOURCE_CARDS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_external_brief(root: Path, spec_hash: str) -> None:
    sources = []
    bindings = []
    for source in SOURCE_CARDS:
        core_claim = source["claim"]
        sources.append(
            {
                "title": source["claim_id"].replace("_", " ").title(),
                "url": source["source_url"],
                "published_or_updated_at": source["published_or_updated_at"],
                "source_type": source["source_type"],
                "credibility": "official primary source"
                if source["source_type"] != "paper"
                else "paper metadata verified through Crossref",
                "core_claim": core_claim,
                "project_applicability": source["impact_on_spec"],
                "reflection": source["limitations"],
                "topics": source["applies_to"],
            }
        )
        fingerprint = claim_fingerprint(core_claim)
        bindings.append(
            {
                "canonical_url": source["source_url"],
                "source_card_claim_id": source["claim_id"],
                "claim_fingerprint": fingerprint,
                "brief_claim_fingerprint": fingerprint,
            }
        )
    objective = (
        "Re-evaluate the exact parent-locked VIX/VIX3M family after an implementation-only "
        "candidate-order failure, adding zero economic candidates and disclosing all prior "
        "unpersisted model exposure."
        if IS_IMPLEMENTATION_REPAIR
        else "Test a paired VIX/VIX3M research modality as an independent next-open "
        "long-Nasdaq exposure state and require deterministic, ML, missing, and placebo evidence."
    )
    payload = {
        "schema_version": 2,
        "iter_id": ITER_ID,
        "strategy_name": STRATEGY_STEM,
        "objective": objective,
        "source_spec_path": PRIMARY_SPEC_PATH.as_posix(),
        "spec_hash": spec_hash,
        "generated_at": datetime.now(UTC).isoformat(),
        "current_source_card_paths": [SOURCE_CARDS_PATH.as_posix()],
        "source_evidence_bindings": bindings,
        "sources": sources,
        "topic_coverage": [
            "VIX_VIX3M_term_structure",
            "point_in_time_market_data",
            "nontradable_index_identity",
            "leveraged_ETF_path_dependency",
            "after_cost_ML_policy_value",
            "probability_calibration_and_selective_prediction",
            "matched_modality_ablation",
            "DSR_PBO_multiple_testing",
            "next_open_execution",
        ],
        "hypothesis_links": ["VIX-H0", "VIX-H1", "VIX-H2", "VIX-H3", "VIX-H4"],
        "candidate_matrix_revisions": (
            [
                "No economic candidate, data, feature, label, model, seed, fallback, fold, cost, or benchmark revision is permitted.",
                "Rebind only iteration governance paths and require economic-projection equality to the parent lock.",
                "Apply the post-2026-08-15 strict primary-cost terminal-free OOS Sharpe greater-than-1.0 gate.",
            ]
            if IS_IMPLEMENTATION_REPAIR
            else [
                "Keep a sealed S1D01 replication diagnostic so runner/data/cost drift cannot masquerade as Alpha.",
                "Separate price-only, VIX-only, and combined deterministic routes and matched logistic feature ablations.",
                "Use one daily five-session path-survival label and one expanding prequential training index across the ML trio.",
                "Make missing-modality fallback explicit and keep the train-only placebo outside selectable PBO candidates.",
                "Bind all thresholds, feature sets, cadence, calibration minima, and placebo seed before any successor return calculation.",
            ]
        ),
    }
    write_json(root / ITERATION_DIR / "external-brief.json", payload)
    brief_intro = (
        "This pure implementation repair reuses the exact parent-locked VIX/VIX3M family. "
        "It introduces no new economic hypothesis and cannot erase the disclosed failed-run "
        "exposure; all evidence is rebound to the new iteration before a single repair evaluation."
        if IS_IMPLEMENTATION_REPAIR
        else "This round tests a genuinely separate implied-volatility term-structure input. "
        "Selectable candidates do not reuse the frozen R1 anchor or SMA200 route; V1R01 exists "
        "only as a non-selectable replication diagnostic. VIX, VIX3M, and VIXY are never treated "
        "as interchangeable instruments."
    )
    lines = [
        f"# External Brief: {ITER_ID}",
        "",
        brief_intro,
        "",
        "## Sourced Findings",
        "",
    ]
    for index, source in enumerate(sources, 1):
        lines.extend(
            [
                f"### {index}. {source['title']}",
                "",
                f"- URL: {source['url']}",
                f"- Date: {source['published_or_updated_at']}",
                f"- Type: {source['source_type']}",
                f"- Claim: {source['core_claim']}",
                f"- Application: {source['project_applicability']}",
                f"- Limitation: {source['reflection']}",
                "",
            ]
        )
    (root / ITERATION_DIR / "external-brief.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )


def write_hypotheses_and_markdown(root: Path) -> None:
    repair_note = (
        "\nThis iteration is a pure implementation repair of the parent-locked hypotheses. "
        "It adds zero economic candidates and permits no outcome-driven parameter change.\n"
        if IS_IMPLEMENTATION_REPAIR
        else ""
    )
    hypotheses = f"""# Hypotheses: {ITER_ID}
{repair_note}

## VIX-H0

- Hypothesis: The new runner, price panel, costs, and target semantics reproduce the sealed S1D01 route on the common evaluation sessions.
- Failure mode: A loader, session, fill, or cost change creates a false improvement or false degradation.
- Measurement: Byte-level target hashes and paired daily return streams against the locked S1D01 diagnostic.
- Stop/Pivot criterion: Stop the round if replication is not exact before interpreting any VIX result.

## VIX-H1

- Hypothesis: A same-date VIX/VIX3M ratio and slope, applied only when `visible_at <= decision_at`, can preserve at least 85% of matched TQQQ CAGR while lowering TQQQ downside capture below 0.90 at 20 bps.
- Failure mode: Backwardation arrives after the opening gap, exits too late, or whipsaws during fast recoveries.
- Measurement: Full-window and four chronological folds against TQQQ, QQQ, equal-weight universe, SPY, XLK, BIL, and ex-post-best-symbol report-only benchmarks.
- Stop/Pivot criterion: Stop this deterministic family if the primary misses any frozen CAGR, capture, drawdown, Sharpe, MAR, DSR, PBO, or fold gate.

## VIX-H2

- Hypothesis: V1V01 beats the price-only V1Q01 control after identical costs, showing incremental information rather than relabelled QQQ momentum; V1D02 is a preregistered consensus check.
- Failure mode: The Cboe state is merely contemporaneous with price stress and adds no out-of-sample policy value.
- Measurement: Matched targets, fold return differences, state confusion, override count, and after-cost realized override value.
- Stop/Pivot criterion: Stop the modality claim if V1V01 does not beat V1Q01 in at least three of four folds and in aggregate after 20 bps.

## VIX-H3

- Hypothesis: Matched prequential logistic overlays can add value to the same V1Q01 base when price-only, VIX-only, and combined feature sets are compared with identical labels, indices, estimator, cadence, and calibration.
- Failure mode: Threshold regimes already capture the useful information, calibration sample sizes are inadequate, or ML pays costs for noisy overrides.
- Measurement: At least eight effective overrides, at least three winning folds, positive aggregate after-cost override value over V1Q01, calibration diagnostics, exact fallback, and retained upside capture.
- Stop/Pivot criterion: Deny ML complexity credit unless every ML gate passes; keep negative results in model memory.

## VIX-H4

- Hypothesis: Fold-local seed-15108 train-only permutation destroys useful VIX ordering, while an explicitly injected missing packet reproduces V1M01 exactly.
- Failure mode: Placebo matches the real modality, fallback diverges, or results depend on silent defaults.
- Measurement: Exact target hashes for fallback, byte-level model feature bindings, and fold-local real-versus-placebo performance under identical costs.
- Stop/Pivot criterion: Block research if fallback identity fails; reject the modality claim if placebo is not materially weaker.
"""
    (root / ITERATION_DIR / "hypotheses.md").write_text(hypotheses, encoding="utf-8")
    search_md = f"""# Search Space: {ITER_ID}

{"This repair reuses the exact nine parent-counted economic rows; incremental economic trial count is zero and effective DSR trial count remains 8,147." if IS_IMPLEMENTATION_REPAIR else ""}

The round contains exactly nine preregistered rows: a locked S1D01 replication diagnostic, price-only deterministic control (V1Q01), VIX-only deterministic route (V1V01), combined deterministic route (V1D02), matched price-only/VIX-only/combined logistic overlays (V1M01/V1M02/V1C01), an explicit missing-modality fallback (V1F01), and a non-selectable placebo (V1P01). The factor catalog retains broader ranges for later independent rounds, but this historical evaluation locks risk-on ratio 0.95, stress ratio 1.00, crisis ratio 1.08, crisis VIX 40, two-session confirmation, QQQ momentum lookback 63, logistic threshold 0.65, five-session execution-open-to-open label, 21-session refit cadence, five-session override duration, and placebo seed 15108. No outcome-driven neighbor selection is allowed.

The three ML rows share one label definition, expanding common-start decision indices, five-session purge/embargo, estimator, calibration split, five-session step-down overlay, and cost contract; only their declared price/VIX feature sets differ. Every path uses the same immutable price panel, next-regular-open timing, 10/20/40 bps cost views, full benchmark family, four chronological folds, cumulative trial DSR, and eight-block 70-partition PBO. The placebo and replication are diagnostics and cannot be selected as a promoted strategy.
"""
    (root / ITERATION_DIR / "search-space.md").write_text(search_md, encoding="utf-8")
    decision_reason = (
        "the parent failure audit, economic-equivalence proof, prior exposure disclosure, contracts, and source bindings must be frozen before any repair candidate return is calculated"
        if IS_IMPLEMENTATION_REPAIR
        else "contracts, source bindings, immutable snapshots, and model/fallback roles must be frozen before any candidate return is calculated"
    )
    decision = f"""# Decision Record: {ITER_ID}

## Pre-Evaluation State

- Path: all nine preregistered VIX successor roles
- Decision: pending; evaluation is forbidden until the knowledge and pre-backtest gates pass
- Reason: {decision_reason}
- Next iteration suggestion: after a single locked evaluation, continue only a candidate that passes every frozen family gate; otherwise record stop or pivot without tuning this lock

Status separation before evaluation: `workflow_pass=true`, `research_pass=false`, `llm_contribution_pass=false`, and `paper_ready_pass=false`. No paper orders, broker writes, or simulation waiting are authorized.
"""
    (root / ITERATION_DIR / "decision-record.md").write_text(decision, encoding="utf-8")


def write_contracts(root: Path) -> None:
    price_binding = _binding(PRICE_SNAPSHOT_PATH, root)
    quality_binding = _binding(PRICE_QUALITY_PATH, root)
    cboe_binding = _binding(CBOE_SNAPSHOT_PATH, root)
    packet_binding = _binding(CBOE_PACKET_PATH, root)
    factor_binding = _binding(FACTOR_LIBRARY_PATH, root)
    uses_vix_ids = ["V1V01", "V1D02", "V1M02", "V1C01", "V1P01"]
    contracts: dict[str, dict[str, Any]] = {
        "data-contract.json": {
            "schema_version": 2,
            "contract_id": CONTRACT_IDS["data_contract"],
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "market_prices": {
                "provider": "alpaca",
                "feed": "sip",
                "adjustment": "all",
                "session_scope": "regular",
                "snapshot_manifest": price_binding,
                "quality_report": quality_binding,
                "symbols": ["TQQQ", "QQQ", "BIL", "SPY", "XLK"],
            },
            "candidate_modality_bindings": {
                candidate_id: {
                    "required_capabilities": [
                        "market.alpaca_bars",
                        *(
                            ["market.cboe_volatility_indices"]
                            if candidate_id in uses_vix_ids
                            else []
                        ),
                    ],
                    "external_modality_consumed_by_primary_logic": candidate_id in uses_vix_ids,
                    "missing_packet_behavior": "explicit_fallback_only"
                    if candidate_id == "V1F01"
                    else None,
                }
                for candidate_id in [row["candidate_id"] for row in ROLE_ROWS]
            },
            "external_modality": {
                "provider": "cboe_global_indices",
                "capability_id": "market.cboe_volatility_indices",
                "status": "trial",
                "strict_behavior": "research_only",
                "snapshot_manifest": cboe_binding,
                "packet_path": packet_binding,
                "pairing": "same_observation_date_intersection_without_forward_fill",
                "availability_join": "visible_at_lte_decision_at",
                "historical_first_seen_claim": False,
                "paper_ready": False,
            },
            "timing": {
                "feature_cutoff": "decision_session_completed_regular_close",
                "decision": "completed_close_t_after_all_asof_features_are_available",
                "decision_at": "decision_session_regular_close",
                "execution": "first_following_regular_session_open_t_plus_1",
                "packet_join": "latest_packet_with_visible_at_lte_decision_at; no_same_open_packet",
                "price_return": "regular_open_to_next_regular_open",
            },
            "integrity": {
                "immutable_snapshots_required": True,
                "forward_fill_allowed": False,
                "silent_feed_fallback_allowed": False,
                "zero_return_substitution_allowed": False,
                "nonfinite_action": "fail_closed",
                "missing_leg_action": "fail_closed",
                "stale_packet_action": "explicit_candidate_fallback_only",
            },
        },
        "feature-contract.json": {
            "schema_version": 3,
            "contract_id": CONTRACT_IDS["feature_contract"],
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "factor_library": factor_binding,
            "price_features": list(PRICE_FEATURES),
            "vix_features": list(VIX_FEATURES),
            "external_factor": {
                "factor_id": FACTOR_ID,
                "expression": None,
                "packet_fields": [
                    "vix_close",
                    "vix3m_close",
                    "vix_to_vix3m_ratio",
                    "normalized_term_slope",
                    "vix_high",
                    "vix_low",
                    "vix3m_high",
                    "vix3m_low",
                    "visible_at",
                    "source",
                    "input_hash",
                ],
                "full_sample_fit": False,
                "availability_field": "visible_at",
            },
            "state_machine": copy.deepcopy(VIX_STATE_MACHINE),
            "ml_overlay": copy.deepcopy(ML_OVERLAY_CONTRACT),
            "quant_control": {
                "name": "qqq_momentum_63",
                "formula": "QQQ_close_t/QQQ_close_t_minus_63-1",
                "availability": "completed_close_before_next_open",
            },
            "deterministic_routes": {
                "V1R01": "exact sealed S1D01 fixed anchor/monthly trend replication",
                "V1Q01": "QQQ 63-session momentum sign to TQQQ or BIL",
                "V1V01": "VIX/VIX3M ratio and VIX exposure ladder",
                "V1D02": "V1Q01 and V1V01 consensus ladder",
                "V1F01": "explicit missing-modality identity to V1M01",
                "V1P01": "fold-local train-only VIX feature permutation",
            },
            "matched_ml": {
                "candidate_ids": ["V1M01", "V1M02", "V1C01"],
                "model_kind": "logistic_regression_classifier",
                "same_label": True,
                "same_decision_indices": True,
                "same_calibration_indices": True,
                "only_feature_sets_differ": True,
                "feature_sets": {
                    "V1M01": list(PRICE_FEATURES),
                    "V1M02": list(VIX_FEATURES),
                    "V1C01": [*PRICE_FEATURES, *VIX_FEATURES],
                },
            },
            "prohibited": [
                "same_session_close_execution",
                "historical_fetched_at_rewrite",
                "VIXY_substitution",
                "full_sample_scaling",
                "missing_packet_default_as_observed_data",
                "random_split",
            ],
        },
        "label-contract.json": {
            "schema_version": 3,
            "contract_id": CONTRACT_IDS["label_contract"],
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "shared_by_candidates": ["V1M01", "V1M02", "V1C01", "V1P01"],
            "timing": {
                "feature_cutoff": "completed_close_t_and_packet_visible_at_lte_decision_close_t",
                "decision_session": "t",
                "execution_session": "first_following_regular_session_t_plus_1",
                "decision_at": "regular_close_t",
                "label_start": "regular_open_t_plus_1",
                "label_end": "regular_open_t_plus_6",
                "horizon_sessions": 5,
                "return_intervals": 5,
                "path_observation_points": 6,
                "label_end_position_formula": "decision_position + 1 + horizon_sessions",
                "decision_session_open_excluded": True,
                "purge_sessions": 5,
                "embargo_sessions": 5,
            },
            "labels": {
                "path_survival": {
                    "type": "TQQQ_path_survival_binary",
                    "positive": "running_open_peak_drawdown_greater_than_or_equal_to_minus_10pct_and_terminal_return_strictly_greater_than_minus_6pct",
                    "path_reference": "TQQQ_open[t_plus_1:t_plus_6] with five open_to_open intervals",
                    "action_on_low_probability": "one_exposure_step_down_for_five_execution_sessions",
                }
            },
            "maturity": {
                "training_row_required": "label_end_position <= current_execution_position - embargo_sessions",
                "unmatured_action": "exclude_row",
            },
            "prohibited": [
                "random_split",
                "same_session_return_label",
                "decision_session_open_in_label",
                "unmatured_label_training",
                "zero_fill_for_missing_return",
            ],
        },
        "validation-contract.json": {
            "schema_version": 3,
            "contract_id": CONTRACT_IDS["validation_contract"],
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "common_start": {
                "price_range_start": "2017-02-01",
                "warmup_sessions": 756,
                "first_oos_session": "2020-02-04",
                "decision_cadence": "every_regular_session",
                "training_mode": "expanding_from_fixed_common_start",
            },
            "chronological_folds": {
                "count": 4,
                "construction": "four_contiguous_equal_length_OOS_folds_after_fixed_common_start_and_756_session_warmup",
                "minimum_train_sessions": 756,
                "purge_sessions": 5,
                "embargo_sessions": 5,
                "random_split": False,
                "fold_indices_shared_by_M01_M02_C01_P01": True,
                "oos_sessions": 408,
                "first_oos_index": 756,
            },
            "ml_training": {
                "candidate_ids": ["V1M01", "V1M02", "V1C01", "V1P01"],
                "identity_control_ids": ["V1F01"],
                "model_kind": "logistic_regression_classifier",
                "label_horizon_sessions": 5,
                "retrain_every_sessions": 21,
                "expanding_fit": True,
                "window_cap_sessions": 10000,
                "calibration_fraction": 0.20,
                "minimum_fit_rows": 480,
                "minimum_calibration_rows": 120,
                "minimum_fit_positive_rows": 24,
                "minimum_fit_negative_rows": 24,
                "minimum_calibration_positive_rows": 6,
                "minimum_calibration_negative_rows": 6,
                "selection_threshold": 0.65,
                "common_seed": MODEL_SEED,
                "training_indices_hash_required": True,
                "common_index_contract": {
                    "index_name": "shared_eligible_decision_rows_v1",
                    "row_identity": "decision_session|execution_session|label_end_position|label",
                    "hash": "sha256_canonical_sorted_json_rows",
                    "same_for": ["V1M01", "V1M02", "V1C01", "V1P01"],
                    "fitted_feature_columns_do_not_change_row_identity": True,
                },
                "fit_estimator": {
                    "kind": "StandardScaler_then_LogisticRegression",
                    "C": 1.0,
                    "penalty": "l2",
                    "solver": "lbfgs",
                    "max_iter": 1000,
                    "random_state": MODEL_SEED,
                },
                "calibration_estimator": {
                    "kind": "chronological_Platt_scaling",
                    "C": 1.0,
                    "penalty": "l2",
                    "solver": "lbfgs",
                    "max_iter": 1000,
                    "random_state": MODEL_SEED,
                },
                "refit_schedule": "fit_at_first_eligible_decision_then_every_21_execution_sessions; reuse_model_for_intervening_sessions",
                "override_contract": copy.deepcopy(ML_OVERLAY_CONTRACT),
                "placebo_contract": {
                    "seed": PLACEBO_SEED,
                    "scope": "joint_permutation_of_VIX_feature_columns_in_fit_rows_only",
                    "seed_derivation": "sha256(seed|fold_id|refit_ordinal|split_id) first 8 bytes little endian",
                    "permutation_unit": "one_shared_row_permutation_for_all_eight_VIX_columns",
                    "fit_rows_only": True,
                    "price_features_unchanged": True,
                    "labels_unchanged": True,
                    "calibration_rows_unchanged": True,
                    "evaluation_order_unchanged": True,
                },
            },
            "family_gates": {
                "primary_candidate_id": PRIMARY_CANDIDATE_ID,
                "net_CAGR_floor_pct": 45.0,
                "maximum_drawdown_floor_pct": -65.0,
                "Sharpe_floor": SHARPE_FLOOR,
                "Sharpe_operator": SHARPE_OPERATOR,
                "Sharpe_metric_identity": {
                    "cost_view": "primary_20bps",
                    "return_stream": "continuous_terminal_free_OOS_daily_open_to_open_net_returns",
                    "benchmark": "BIL",
                    "annualization_sessions": 252,
                    "field": "annualized_sharpe_excess_BIL",
                },
                "MAR_floor": 0.4,
                "matched_QQQ_CAGR_lift_floor_pct_points": 8.0,
                "matched_TQQQ_CAGR_fraction_floor": 0.85,
                "TQQQ_up_capture_floor": 0.8,
                "TQQQ_down_capture_ceiling": 0.9,
                "positive_QQQ_lift_folds_min": 3,
                "DSR_probability_floor": 0.75,
                "PBO_ceiling": 0.4,
                "pbo_min_partitions": 70,
                "primary_cost_bps": PRIMARY_COST_BPS,
                "stress_cost_bps": [10.0, 20.0, 40.0],
            },
            "ML_gates": {
                "minimum_effective_overrides": 8,
                "minimum_folds_beating_fallback": 3,
                "aggregate_realized_override_value_strictly_positive": True,
                "combined_ML_beats_price_ML_folds_min": 3,
                "combined_ML_beats_price_ML_aggregate_strictly_positive": True,
                "minimum_primary_upside_capture_retained": 0.95,
                "calibration_required": True,
                "exact_fallback_required": True,
            },
            "modality_gates": {
                "V1V01_folds_beating_V1Q01_min": 3,
                "V1V01_aggregate_after_cost_lift_over_V1Q01_strictly_positive": True,
                "V1D02_folds_beating_V1Q01_min": 3,
                "V1F01_exact_V1M01_target_identity": True,
                "V1P01_must_not_match_or_beat_V1C01": True,
                "V1R01_exact_S1D01_replication": True,
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
                "selection_candidate_ids": ["V1Q01", "V1V01", "V1D02", "V1M01", "V1M02", "V1C01"],
                "diagnostic_control_ids": ["V1R01", "V1F01", "V1P01"],
                "valid_partition_requirements": [
                    "all_candidate_Sharpe_values_are_defined",
                    "all_selection_candidates_have_nonempty_finite_returns_on_both_sides",
                    "exactly_four_in_sample_and_four_out_of_sample_blocks",
                    "no_session_substitution_or_overlap",
                    "candidate_id_invariant_equal_weight_in_sample_ties",
                    "candidate_id_invariant_average_oos_midranks",
                    "identical_candidate_streams_contribute_exactly_0.5",
                ],
                "common_return_matrix": {
                    "cost_view": "primary_20bps",
                    "terminal_liquidation_included": False,
                    "expected_observation_count": 1631,
                    "expected_block_observation_counts": [204, 204, 204, 204, 204, 204, 204, 203],
                    "row_identity": "fold_id|interval_start|interval_end",
                    "source_rows_sha256_required": True,
                },
            },
            "dsr": {
                "trial_count": EFFECTIVE_TRIAL_COUNT,
                "primary_return_stream": "daily_open_to_open_net_return_without_terminal_liquidation",
                "iid_method": "deflated_sharpe_probability_dynamic_theme_r8_v1",
                "hac_method": "influence_series_newey_west_deflated_sharpe",
                "hac_lag_sessions": 21,
                "hac_scope": "single_continuous_terminal_free_OOS_return_stream",
                "gate_probability": "minimum_of_iid_and_hac",
                "minimum_probability": 0.75,
            },
            "ml_override": copy.deepcopy(ML_OVERLAY_CONTRACT),
            "low_trade_count_rule": "fewer_than_30_completed_target_changes_sets_low_trade_count_and_short_sample_caveat",
        },
        "cost-contract.json": {
            "schema_version": 3,
            "contract_id": CONTRACT_IDS["cost_contract"],
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "views": [
                {"name": "low_10bps", "one_way_bps": 10.0},
                {"name": "primary_20bps", "one_way_bps": 20.0},
                {"name": "severe_40bps", "one_way_bps": 40.0},
            ],
            "application": "full_L1_target_change_notional_times_bps_at_each_next_regular_open_target_change",
            "reported_one_way_turnover": "0.5_times_full_L1_target_change_for_two_sided_rebalance_reporting",
            "initial_entry_cost": True,
            "terminal_liquidation_cost": False,
            "daily_stream": "terminal_free_is_authoritative_for_gates_and_DSR_PBO",
            "ML_label_costs_match_primary": False,
            "ML_label_costs": "not applicable; shared path-survival labels are market outcomes, while target streams are evaluated at all three frozen costs",
            "future_protected_order_policy_equivalent": False,
        },
        "benchmark-contract.json": {
            "schema_version": 2,
            "contract_id": CONTRACT_IDS["benchmark_contract"],
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "family": [
                {"id": "TQQQ_buy_hold_same_symbol", "weights": {"TQQQ": 1.0}},
                {"id": "equal_weight_universe", "symbols": ["TQQQ", "QQQ", "BIL", "SPY", "XLK"]},
                {"id": "SPY_market_proxy", "weights": {"SPY": 1.0}},
                {"id": "XLK_sector_theme_proxy", "weights": {"XLK": 1.0}},
                {"id": "BIL_cash_proxy", "weights": {"BIL": 1.0}},
                {"id": "QQQ_buy_hold", "weights": {"QQQ": 1.0}},
                {
                    "id": "ex_post_best_symbol_report_only",
                    "selection": "highest_full_window_net_CAGR",
                    "promotion_eligible": False,
                },
            ],
            "matched_window": True,
            "matched_open_to_open_returns": True,
            "same_cost_views": True,
        },
    }
    for filename, payload in contracts.items():
        write_json(root / ITERATION_DIR / filename, payload)
    write_json(
        root / ITERATION_DIR / "holdout-contract.json",
        {
            "schema_version": 2,
            "contract_id": (
                "vix_r1_holdout_implfix1_v1" if IS_IMPLEMENTATION_REPAIR else "vix_r1_holdout_v2"
            ),
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "historical_prices_globally_exposed": True,
            "untouched_holdout_claim": False,
            "selection_mode": "preregistered_fixed_family_no_post_outcome_neighbor_selection",
            "four_fold_evidence": "chronological_OOS_not_untouched",
            "promotion_limit": "historical success can authorize readiness engineering but not paper-ready data evidence",
        },
    )
    write_json(
        root / ITERATION_DIR / "cumulative-trial-contract.json",
        {
            "schema_version": 2,
            "contract_id": (
                "vix_r1_cumulative_trials_implfix1_v1"
                if IS_IMPLEMENTATION_REPAIR
                else "vix_r1_cumulative_trials_v2"
            ),
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "prior_effective_trial_count": PRIOR_EFFECTIVE_TRIAL_COUNT,
            "round_manifest_candidate_count": ROUND_CANDIDATE_COUNT,
            "inherited_already_counted_candidate_count": (
                ROUND_CANDIDATE_COUNT if IS_IMPLEMENTATION_REPAIR else 0
            ),
            "incremental_economic_trial_count": COUNTED_TRIAL_DELTA,
            "round_candidate_count": COUNTED_TRIAL_DELTA,
            "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
            "reset_allowed": False,
            "DSR_uses_effective_trial_count": True,
            "source_iteration_id": BASE_ITER_ID if IS_IMPLEMENTATION_REPAIR else None,
            "implementation_repair_only": IS_IMPLEMENTATION_REPAIR,
            "DSR_contract": {
                "trial_count": EFFECTIVE_TRIAL_COUNT,
                "primary_stream": "terminal_free_daily_open_to_open",
                "hac_lag_sessions": 21,
                "gate": "minimum_iid_and_hac_probability",
            },
        },
    )
    write_json(
        root / ITERATION_DIR / "modality-role-matrix.json",
        {
            "schema_version": 2,
            "contract_id": "vix_r1_modality_roles_v2",
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "roles": [
                {
                    "role": "factor_generation",
                    "candidates": ["V1V01", "V1D02", "V1M02", "V1C01", "V1P01"],
                    "method": "paired_VIX_VIX3M_packet",
                    "fallback": "V1Q01",
                },
                {
                    "role": "return_ranking",
                    "candidates": [],
                    "method": "not_applicable_tail_risk_classifiers_do_not_rank_expected_returns",
                    "fallback": "none",
                },
                {
                    "role": "risk_prediction",
                    "candidates": ["V1M01", "V1M02", "V1C01", "V1P01"],
                    "method": "five_session_TQQQ_path_survival",
                    "fallback": "V1Q01",
                },
                {
                    "role": "regime_meta_gating",
                    "candidates": ["V1V01", "V1D02"],
                    "method": "term_structure_and_price_control_consensus",
                    "fallback": "V1Q01",
                },
                {
                    "role": "sizing",
                    "candidates": [row["candidate_id"] for row in ROLE_ROWS],
                    "method": "one_of_TQQQ_QQQ_BIL_full_capital",
                    "fallback": "BIL",
                },
                {
                    "role": "uncertainty",
                    "candidates": ["V1M01", "V1M02", "V1C01"],
                    "method": "chronological_platt_scaling_and_abstention",
                    "fallback": "V1Q01",
                },
                {
                    "role": "deterministic_fallback",
                    "candidates": ["V1F01"],
                    "method": "exact_V1M01_target_identity_on_missing_packet",
                    "fallback": "V1Q01",
                },
                {
                    "role": "llm_news_event_macro",
                    "candidates": [],
                    "method": "not_applicable_this_round",
                    "fallback": "none",
                },
            ],
            "matched_ablations": [
                "price_only_V1M01",
                "vix_only_V1M02",
                "combined_V1C01",
                "missing_modality_V1F01",
                "placebo_V1P01_seed_15108",
            ],
            "independent_llm_alpha_claim": False,
        },
    )
    write_json(
        root / ITERATION_DIR / "knowledge-scout-queries.json",
        {
            "schema_version": 1,
            "iter_id": ITER_ID,
            "max_results_per_query": 5,
            "queries": [
                {
                    "query_id": "vix_term_structure_equity_risk",
                    "query": 'all:"VIX term structure" AND (all:"equity risk" OR all:"equity returns")',
                    "topics": ["volatility_term_structure", "equity_risk", "instrument_transfer"],
                },
                {
                    "query_id": "probability_calibration_time_series",
                    "query": 'all:"probability calibration" AND (all:"time series" OR all:"machine learning")',
                    "topics": ["probability_calibration", "sample_size", "prequential_validation"],
                },
                {
                    "query_id": "selective_prediction_reject_option",
                    "query": 'all:"selective classification" OR all:"reject option"',
                    "topics": ["selective_prediction", "abstention", "coverage_risk"],
                },
                {
                    "query_id": "backtest_overfitting_sharpe",
                    "query": 'all:"backtest overfitting" AND all:"Sharpe ratio"',
                    "topics": ["multiple_testing", "DSR", "PBO"],
                },
            ],
            "curated_candidates": [
                {
                    "discovery_id": source["claim_id"],
                    "url": source["source_url"],
                    "title": source["claim_id"].replace("_", " ").title(),
                    "summary": source["claim"],
                    "published_at": source["published_or_updated_at"],
                    "authors": [],
                    "source_type": source["source_type"],
                    "topics": source["applies_to"],
                }
                for source in SOURCE_CARDS
            ],
        },
    )


def write_candidate_manifest(root: Path, specs: dict[str, Any]) -> None:
    contract_bindings: dict[str, dict[str, dict[str, Any]]] = {
        group: {} for group in CONTRACT_GROUPS.values()
    }
    for field, contract_id in CONTRACT_IDS.items():
        group = CONTRACT_GROUPS[field]
        path = ITERATION_DIR / CONTRACT_FILENAMES[field]
        contract_bindings[group][contract_id] = _binding(path, root)
    if IS_IMPLEMENTATION_REPAIR:
        contract_bindings["governance"] = {
            "vix_r1_parent_failure_audit_v1": _binding_with_size(
                ITERATION_DIR / "parent-failure-audit.json", root
            ),
            "vix_r1_pure_implementation_repair_v1": _binding_with_size(
                ITERATION_DIR / "implementation-repair-contract.json", root
            ),
        }
    candidates = []
    for row in ROLE_ROWS:
        candidate_id = row["candidate_id"]
        uses_vix = candidate_id in {"V1V01", "V1D02", "V1M02", "V1C01", "V1P01"}
        parameters: dict[str, Any] = {
            "parameter_search": False,
            "placebo_seed": PLACEBO_SEED if candidate_id == "V1P01" else None,
        }
        if candidate_id in {"V1V01", "V1D02"}:
            parameters.update(
                {
                    "risk_on_ratio_max": 0.95,
                    "stress_ratio_min": 1.0,
                    "crisis_ratio_min": 1.08,
                    "crisis_vix_min": 40.0,
                    "exit_confirmation_sessions": 2,
                }
            )
        if candidate_id != "V1R01":
            parameters["price_control_lookback_sessions"] = 63
        if candidate_id in ML_CANDIDATE_IDS:
            parameters.update(
                {
                    "model_kind": "logistic_regression_classifier",
                    "label_horizon_sessions": 5,
                    "decision_cadence": "every_regular_session",
                    "retrain_every_sessions": 21,
                    "selection_threshold": 0.65,
                    "override_duration_sessions": 5,
                    "model_seed": MODEL_SEED,
                }
            )
        candidate = {
            "candidate_id": candidate_id,
            "path": row["path"],
            "role": row["role"],
            "method": row["method"],
            "ablation": row["ablation"],
            "spec_path": _spec_path(row).as_posix(),
            "fallback": row["fallback"],
            "promotion_eligible": row["promotion_eligible"],
            "selection_eligible": candidate_id not in {"V1R01", "V1F01", "V1P01"},
            "diagnostic_only": candidate_id in {"V1R01", "V1F01", "V1P01"},
            "required_capabilities": [
                "market.alpaca_bars",
                *(["market.cboe_volatility_indices"] if uses_vix else []),
            ],
            "features": (
                list(specs[candidate_id].model.features)
                if specs[candidate_id].model is not None
                else []
            ),
            "label": (
                specs[candidate_id].model.label.model_dump(mode="json")
                if specs[candidate_id].model is not None
                else None
            ),
            "validation_role": (
                "matched_ml"
                if candidate_id in {"V1M01", "V1M02", "V1C01"}
                else "diagnostic"
                if candidate_id in {"V1R01", "V1F01", "V1P01"}
                else "deterministic"
            ),
            "parameters": parameters,
            "source_trial_id": (
                f"{BASE_ITER_ID}:{candidate_id}" if IS_IMPLEMENTATION_REPAIR else None
            ),
            "effective_trial_increment": 0 if IS_IMPLEMENTATION_REPAIR else 1,
            "implementation_repair_only": IS_IMPLEMENTATION_REPAIR,
        }
        candidate.update(CONTRACT_IDS)
        candidates.append(candidate)
    write_json(
        root / ITERATION_DIR / "candidate-manifest.json",
        {
            "schema_version": 2,
            "manifest_type": "generic_candidate_family_v1",
            "iter_id": ITER_ID,
            "generated_before_backtest": True,
            "generated_before_model_training": True,
            "single_new_hypothesis": (
                "none_pure_implementation_repair_of_parent_preregistered_hypothesis"
                if IS_IMPLEMENTATION_REPAIR
                else "paired_VIX_VIX3M_term_structure_changes_next_open_long_beta_exposure"
            ),
            "historical_first_seen_claim": False,
            "source_iteration_id": BASE_ITER_ID if IS_IMPLEMENTATION_REPAIR else None,
            "implementation_repair_only": IS_IMPLEMENTATION_REPAIR,
            "incremental_economic_trial_count": COUNTED_TRIAL_DELTA,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "contracts": contract_bindings,
            "spec_hashes": {
                _spec_path(row).as_posix(): strategy_content_hash(specs[row["candidate_id"]])
                for row in ROLE_ROWS
            },
        },
    )


def write_implementation_repair_artifacts(root: Path, specs: dict[str, Any]) -> None:
    if not IS_IMPLEMENTATION_REPAIR:
        return
    source_lock = _load_source_iteration_lock(root)
    parent_audit_path = ITERATION_DIR / "parent-failure-audit.json"
    parent_audit = {
        "schema_version": 1,
        "contract_id": "vix_r1_parent_failure_audit_v1",
        "iter_id": ITER_ID,
        "source_iteration_id": BASE_ITER_ID,
        "source_lock": {
            "path": SOURCE_ITERATION_LOCK_PATH.as_posix(),
            "sha256": SOURCE_ITERATION_LOCK_SHA256,
            "size_bytes": (root / SOURCE_ITERATION_LOCK_PATH).stat().st_size,
        },
        "evidence_class": "posthoc_code_path_without_model_or_prediction_ledger",
        "failure": {
            "exception": "AssertionError: VIX R1 candidate target order changed",
            "expected_candidate_order": [row["candidate_id"] for row in ROLE_ROWS],
            "constructed_candidate_order": [
                "V1R01",
                "V1Q01",
                "V1V01",
                "V1D02",
                "V1M01",
                "V1M02",
                "V1C01",
                "V1P01",
                "V1F01",
            ],
            "selectable_candidate_returns_computed": False,
            "selectable_candidate_metrics_computed": False,
            "selection_performed": False,
        },
        "exposure": {
            "sealed_R01_replication_returns_may_have_been_recomputed": True,
            "historical_targets_computed": True,
            "historical_predictions_computed": "true_or_unknown",
            "historical_predictions_inspected": "false_or_unknown",
            "unpersisted_refit_attempts_lower_bound": 0,
            "unpersisted_refit_attempts_upper_bound": 312,
            "prediction_rows_upper_bound": 6528,
            "persisted_model_ids": 0,
            "persisted_prediction_rows": 0,
        },
        "parameter_changes_from_outcomes": False,
        "paper_or_broker_activity": False,
    }
    write_json(root / parent_audit_path, parent_audit)

    snapshots = source_lock["runtime_contract"]["candidate_specs"]
    equivalence_rows = []
    for row in ROLE_ROWS:
        candidate_id = row["candidate_id"]
        source_spec = snapshots[candidate_id]["spec"]
        repair_spec = specs[candidate_id].model_dump(mode="json")
        source_projection = _economic_spec_projection(source_spec)
        repair_projection = _economic_spec_projection(repair_spec)
        if source_projection != repair_projection:
            raise ValueError(f"VIX repair economic projection mismatch: {candidate_id}")
        equivalence_rows.append(
            {
                "candidate_id": candidate_id,
                "source_spec_path": snapshots[candidate_id]["path"],
                "source_spec_semantic_sha256": snapshots[candidate_id]["semantic_sha256"],
                "repair_spec_path": _spec_path(row).as_posix(),
                "repair_spec_semantic_sha256": strategy_content_hash(specs[candidate_id]),
                "economic_projection_sha256": _canonical_hash(source_projection),
                "economic_projection_equal": True,
                "allowed_spec_differences": ["name", "research_design"],
            }
        )
    write_json(
        root / ITERATION_DIR / "implementation-repair-contract.json",
        {
            "schema_version": 1,
            "contract_id": "vix_r1_pure_implementation_repair_v1",
            "iter_id": ITER_ID,
            "source_iteration_id": BASE_ITER_ID,
            "generated_before_repair_evaluation": True,
            "repair_scope": "candidate_target_inventory_order_and_one_shot_evaluation_custody",
            "new_economic_candidate_count": 0,
            "manifest_candidate_count": ROUND_CANDIDATE_COUNT,
            "effective_trial_count": EFFECTIVE_TRIAL_COUNT,
            "parent_failure_audit": _binding_with_size(parent_audit_path, root),
            "source_lock": parent_audit["source_lock"],
            "economic_spec_equivalence": equivalence_rows,
            "forbidden_changes": [
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
            ],
            "validation_policy_delta": {
                "reason": "post_2026_08_15_new_iteration_governance",
                "metric": "primary_20bps_continuous_terminal_free_OOS_annualized_sharpe_excess_BIL",
                "operator": "strictly_greater_than",
                "threshold": 1.0,
                "applies_to": [
                    row["candidate_id"]
                    for row in ROLE_ROWS
                    if row["promotion_eligible"] and row["candidate_id"] != "V1P01"
                ],
            },
            "required_regressions": [
                "complete_candidate_target_assembly_uses_frozen_inventory_order",
                "candidate_target_inventory_rejects_missing_extra_and_duplicate_ids",
                "strict_Sharpe_equality_fails",
                "parent_lock_SHA_must_match",
                "repair_trial_increment_must_be_zero",
                "failed_run_exposure_disclosure_is_mandatory",
                "economic_StrategySpec_projection_must_match_parent",
                "base_repair_base_identity_isolation",
                "evaluation_attempt_reserved_before_price_or_model_work",
                "report_receipt_ML_status_identity",
            ],
            "order_authority": False,
            "broker_writes": False,
        },
    )


def finalize_after_knowledge(root: Path, specs: dict[str, Any]) -> None:
    assessment_path = ITERATION_DIR / "knowledge-assessment.json"
    scout_path = ITERATION_DIR / "knowledge-scout.json"
    model_reuse_path = ITERATION_DIR / "model-reuse-decision.json"
    for path in (assessment_path, scout_path, model_reuse_path):
        if not (root / path).is_file():
            raise FileNotFoundError(f"knowledge phase is incomplete: {path}")
    assessment = json.loads((root / assessment_path).read_text(encoding="utf-8"))
    if assessment.get("status") != "ok":
        raise ValueError(f"knowledge assessment is blocked: {assessment.get('blocked')}")
    current_brief_sha = _sha256(root / ITERATION_DIR / "external-brief.json")
    if assessment.get("external_brief_sha256") != current_brief_sha:
        raise ValueError("knowledge assessment is stale for the current external brief")
    model_reuse = json.loads((root / model_reuse_path).read_text(encoding="utf-8"))
    if IS_IMPLEMENTATION_REPAIR:
        model_reuse["round_decision"] = {
            "action": "refit_parent_locked_models_from_scratch_no_warm_start",
            "retrain": True,
            "warm_start": False,
            "reason": (
                "Pure implementation repair after the parent run failed before selectable "
                "candidate returns. No estimator was persisted; up to 312 unpersisted refits "
                "are disclosed and no economic model, data, feature, label, or cadence changes."
            ),
            "data_reason": "exact_parent_locked_price_and_Cboe_snapshot_bindings_unchanged",
            "feature_reason": "exact_parent_locked_feature_sets_unchanged",
            "validation_reason": (
                "exact_parent_locked_training_and_OOS_contract_unchanged; only the new-iteration "
                "strict primary-cost terminal-free Sharpe greater-than-1.0 governance gate applies"
            ),
            "status_provenance_required": True,
            "source_iteration_id": BASE_ITER_ID,
            "persisted_model_ids_from_failed_parent": 0,
            "unpersisted_refit_attempts_upper_bound": 312,
            "negative_memory_retained": ["S1M01", "S1M02"],
        }
    else:
        model_reuse["round_decision"] = {
            "action": "fit_new_models_from_scratch_no_warm_start",
            "retrain": True,
            "warm_start": False,
            "reason": "R1 price-only ML had too few harmful overrides and negative realized policy value; this round changes the information modality, feature contract, label horizon, and decision frequency.",
            "data_reason": "new immutable paired Cboe VIX/VIX3M research snapshot",
            "feature_reason": "independently sourced term-structure state rather than same-source ETF prices",
            "validation_reason": "daily fixed-common-start expanding refits, shared indices, four folds, five-session purge/embargo, and matched price/VIX/combined ablations",
            "status_provenance_required": True,
            "negative_memory_retained": ["S1M01", "S1M02"],
        }
    write_json(root / model_reuse_path, model_reuse)

    manifest_path = ITERATION_DIR / "candidate-manifest.json"
    manifest = json.loads((root / manifest_path).read_text(encoding="utf-8"))
    manifest_by_id = {candidate["candidate_id"]: candidate for candidate in manifest["candidates"]}
    ids_by_path: dict[str, list[str]] = {}
    for candidate in manifest["candidates"]:
        ids_by_path.setdefault(candidate["path"], []).append(candidate["candidate_id"])
    required_references = {
        "candidate_manifest": _binding(manifest_path, root),
        "historical_price_snapshot": _binding(PRICE_SNAPSHOT_PATH, root),
        "price_adjustment_quality": _binding(PRICE_QUALITY_PATH, root),
        "cboe_snapshot": _binding(CBOE_SNAPSHOT_PATH, root),
        "cboe_packets": _binding(CBOE_PACKET_PATH, root),
        "factor_library": _binding(FACTOR_LIBRARY_PATH, root),
        "source_cards": _binding(SOURCE_CARDS_PATH, root),
        "capability_registry": _binding(Path("capabilities/registry.yaml"), root),
        "modality_role_matrix": _binding(ITERATION_DIR / "modality-role-matrix.json", root),
        "model_reuse_decision": _binding(model_reuse_path, root),
        "knowledge_assessment": _binding(assessment_path, root),
        "knowledge_scout": _binding(scout_path, root),
    }
    if IS_IMPLEMENTATION_REPAIR:
        required_references.update(
            {
                "source_iteration_lock": _binding(SOURCE_ITERATION_LOCK_PATH, root),
                "parent_failure_audit": _binding(ITERATION_DIR / "parent-failure-audit.json", root),
                "implementation_repair_contract": _binding(
                    ITERATION_DIR / "implementation-repair-contract.json", root
                ),
            }
        )
    for filename in [
        *CONTRACT_FILENAMES.values(),
        "holdout-contract.json",
        "cumulative-trial-contract.json",
    ]:
        required_references[filename.removesuffix(".json").replace("-", "_")] = _binding(
            ITERATION_DIR / filename, root
        )
    authorization_rows = []
    for candidate in manifest["candidates"]:
        authorization_rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "path": candidate["path"],
                "action": "evaluate",
                "reason_code": "preregistered_matched_historical_evaluation_or_exact_fallback",
                "candidate_binding_sha256": _canonical_hash(candidate),
            }
        )
    data_feasibility = {
        "schema_version": 2,
        "report_type": "vix_term_structure_overlay_r1_data_feasibility",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_before_backtest": True,
        "generated_before_model_training": True,
        "implementation_repair_only": IS_IMPLEMENTATION_REPAIR,
        "source_iteration_id": BASE_ITER_ID if IS_IMPLEMENTATION_REPAIR else None,
        "incremental_economic_trial_count": COUNTED_TRIAL_DELTA,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "historical_positive_alpha_claim_authorized": False,
        "broker_writes": False,
        "data_scope": {
            "market": "immutable Alpaca SIP daily bundle",
            "new_modality": "immutable paired Cboe VIX/VIX3M research snapshot",
            "pair_count": 4251,
            "pair_range": ["2009-09-18", "2026-08-13"],
            "common_price_evaluation_range": ["2017-02-01", "2026-08-03"],
            "availability": "visible_at_lte_decision_at",
            "historical_first_seen_claim": False,
            "paper_ready": False,
        },
        "path_gates": {
            path: {
                "action": "evaluate",
                "historical_evaluation_go": True,
                "candidate_ids": candidate_ids,
                "scope": "matched_historical_research_or_exact_fallback_identity",
            }
            for path, candidate_ids in ids_by_path.items()
        },
        "candidate_accounting": {
            "frozen_candidate_count": len(manifest["candidates"]),
            "evaluation_authorized_count": len(manifest["candidates"]),
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": len(manifest["candidates"]),
            "rows": authorization_rows,
        },
        "required_reference_names": sorted(required_references),
        "required_references": required_references,
        "blockers": [
            "trial research-only Cboe capability is not paper-ready market evidence",
            "historical fetched_at is actual 2026 snapshot time, not historical first-seen",
            "paper orders and paper fills are outside this stage",
        ],
        "conclusion": "historical_research_evaluation_authorized_with_explicit_PIT_and_fallback_limits",
    }
    feasibility_path = ITERATION_DIR / "data-feasibility.json"
    write_json(root / feasibility_path, data_feasibility)

    primary_hash = strategy_content_hash(specs[PRIMARY_CANDIDATE_ID])
    paths = []
    for path_name, candidate_ids in ids_by_path.items():
        hypothesis_refs = (
            ["VIX-H0"]
            if path_name == "locked_replication_diagnostic"
            else ["VIX-H1", "VIX-H2", "VIX-H3", "VIX-H4"]
        )
        paths.append(
            {
                "name": path_name,
                "candidate_count": len(candidate_ids),
                "candidate_ids": candidate_ids,
                "hypothesis_refs": hypothesis_refs,
                "parameters": {
                    candidate_id: {
                        key: [value]
                        for key, value in manifest_by_id[candidate_id]["parameters"].items()
                    }
                    for candidate_id in candidate_ids
                },
                "benchmark_family": [
                    "TQQQ_buy_hold_same_symbol",
                    "equal_weight_universe",
                    "SPY_market_proxy",
                    "XLK_sector_theme_proxy",
                    "BIL_cash_proxy",
                    "QQQ_buy_hold",
                    "ex_post_best_symbol_report_only",
                ],
            }
        )
    write_json(
        root / ITERATION_DIR / "search-space.json",
        {
            "schema_version": 2,
            "iter_id": ITER_ID,
            "strategy_name": STRATEGY_STEM,
            "objective": (
                "pure implementation repair of the parent-preregistered paired VIX/VIX3M family"
                if IS_IMPLEMENTATION_REPAIR
                else "preregistered paired VIX/VIX3M successor family"
            ),
            "source_spec_path": PRIMARY_SPEC_PATH.as_posix(),
            "spec_hash": primary_hash,
            "candidate_manifest_contract": "generic_candidate_family_v1",
            "candidate_manifest_path": manifest_path.as_posix(),
            "candidate_manifest_sha256": _sha256(root / manifest_path),
            "data_feasibility_path": feasibility_path.as_posix(),
            "data_feasibility_sha256": _sha256(root / feasibility_path),
            "cost_table_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
            "paths": paths,
            "total_candidate_budget": ROUND_CANDIDATE_COUNT,
            "cumulative_trial_count": EFFECTIVE_TRIAL_COUNT,
            "incremental_economic_trial_count": COUNTED_TRIAL_DELTA,
            "source_iteration_id": BASE_ITER_ID if IS_IMPLEMENTATION_REPAIR else None,
            "trial_ledger_paths": [
                (ITERATION_DIR / "evaluation-run/trial-ledger.jsonl").as_posix()
            ],
            "evaluation_report_paths": [
                (ITERATION_DIR / "evaluation-run/evaluation-report.json").as_posix()
            ],
            "knowledge_contract": {
                "assessment_path": assessment_path.as_posix(),
                "scout_path": scout_path.as_posix(),
                "model_reuse_decision_path": model_reuse_path.as_posix(),
                "modality_role_matrix_path": (
                    ITERATION_DIR / "modality-role-matrix.json"
                ).as_posix(),
                "required_visibility_partitions": [
                    "public_literature",
                    "train_only_empirical",
                    "challenge_result",
                    "forward_observation",
                ],
            },
        },
    )


def prepare(root: Path) -> None:
    for required in [
        BASE_SPEC_PATH,
        PRICE_SNAPSHOT_PATH,
        PRICE_QUALITY_PATH,
        CBOE_SNAPSHOT_PATH,
        CBOE_PACKET_PATH,
    ]:
        if not (root / required).is_file():
            raise FileNotFoundError(required)
    (root / ITERATION_DIR).mkdir(parents=True, exist_ok=True)
    specs = build_specs(root)
    write_source_cards(root)
    write_factor_library_artifact(
        strategy_name=STRATEGY_STEM,
        factor_ids=[FACTOR_ID, "fixed_anchor_monthly_trend_sleeve"],
        root=root,
    )
    primary_hash = strategy_content_hash(specs[PRIMARY_CANDIDATE_ID])
    write_external_brief(root, primary_hash)
    write_hypotheses_and_markdown(root)
    write_contracts(root)
    write_implementation_repair_artifacts(root, specs)
    write_candidate_manifest(root, specs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--iter-id", choices=tuple(ALLOWED_ITERATION_STEMS), default=BASE_ITER_ID)
    parser.add_argument("--finalize-after-knowledge", action="store_true")
    args = parser.parse_args()
    configure_iteration(args.iter_id)
    root = args.root.resolve()
    if args.finalize_after_knowledge:
        specs = {
            row["candidate_id"]: load_strategy_spec(root / _spec_path(row)) for row in ROLE_ROWS
        }
        finalize_after_knowledge(root, specs)
    else:
        prepare(root)


if __name__ == "__main__":
    main()
