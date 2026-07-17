from __future__ import annotations

import hashlib
import json
from typing import Any

ITER_ID = "mom_stock_intraday_codesign_q1"
RUNNABLE_IDS = tuple(
    [f"D{index:02d}" for index in range(1, 13)] + [f"M{index:02d}" for index in range(1, 17)]
)
PRIMITIVE_FIELDS = ("open", "close", "volume")
BENCHMARKS = (
    "same_symbol_buy_and_hold",
    "equal_weight_universe",
    "SPY_market_proxy",
    "XLK_sector_proxy",
    "BIL_cash_proxy",
    "ex_post_best_symbol_report_only",
    "deterministic_12_1",
)

FEATURE_FORMULAS = {
    "mom_63_raw": "close.shift(1).pct_change(63)",
    "mom_126_raw": "close.shift(1).pct_change(126)",
    "stock_return_126": "close.shift(1).pct_change(126)",
    "spy_return_126": "spy_close.shift(1).pct_change(126)",
    "vol_21_raw": "close.shift(1).pct_change().rolling(21,min=15).std()",
    "mom_21_rank": "pct_rank(close.shift(1).pct_change(21))",
    "mom_63_rank": "pct_rank(close.shift(1).pct_change(63))",
    "mom_126_skip21_rank": "pct_rank(close.shift(22)/close.shift(127)-1)",
    "mom_252_skip21_rank": "pct_rank(close.shift(22)/close.shift(253)-1)",
    "vol_21_rank": "pct_rank(close.shift(1).pct_change().rolling(21,min=15).std())",
    "downside_vol_63_rank": (
        "pct_rank(min(close.shift(1).pct_change(),0).rolling(63,min=40).std())"
    ),
    "drawdown_63_rank": "pct_rank(close.shift(1)/rolling_max(close.shift(1),63,min=40)-1)",
    "liquidity_rank": "pct_rank(rolling_median(close.shift(1)*volume.shift(1),60,min=40))",
    "industry_relative_63_rank": "pct_rank(mom_63_raw-industry_mean(mom_63_raw))",
    "industry_relative_126_rank": "pct_rank(mom_126_raw-industry_mean(mom_126_raw))",
    "relative_spy_126_rank": "pct_rank(stock_return_126-spy_return_126)",
    "relative_spy_252_skip21_rank": (
        "pct_rank(stock_close.shift(22)/stock_close.shift(253)-"
        "spy_close.shift(22)/spy_close.shift(253))"
    ),
    "volume_surprise_21_63_rank": (
        "pct_rank(rolling_mean(volume.shift(1),21,min=15)/rolling_mean(volume.shift(1),63,min=40))"
    ),
    "price_volume_corr_21_rank": (
        "pct_rank(rolling_corr(close.shift(1).pct_change(),volume.shift(1).pct_change(),21,min=15))"
    ),
    "trend_consistency_252_rank": (
        "pct_rank(rolling_mean(close.shift(1).pct_change()>0,252,min=180))"
    ),
    "spy_trend_126": "spy_close.shift(1).pct_change(126)",
    "spy_vol_21": "spy_close.shift(1).pct_change().rolling(21,min=15).std()",
    "cross_sectional_dispersion_21": (
        "rolling_mean(cross_section_std(selected62_close.shift(1).pct_change()),21,min=15)"
    ),
    "market_breadth_20": (
        "mean(selected62_close.shift(1)>rolling_mean(selected62_close.shift(1),20,min=15))"
    ),
}

MODEL_SELECTION_CONTRACT = {
    "outer_split": (
        "sort_unique_candidate_decision_dates;initial_train=floor(0.40*n)_minimum_8;"
        "split_remaining_dates_into_4_contiguous_array_split_blocks;each_fold_trains_on_all_"
        "earlier_dates_subject_to_purge"
    ),
    "inner_split": (
        "sort_unique_outer_train_dates;inner_test=last_20pct_ceiling_minimum_4;"
        "inner_train=all_earlier_dates_subject_to_purge"
    ),
    "outer_purge": "label_end_position<=outer_test_start_position-embargo_bars",
    "inner_purge": "label_end_position<=inner_test_start_position-embargo_bars",
    "parameter_tie_break": "canonical_json_ascending",
    "ranking_metric": "mean_rank_ic_then_net_return_at_10bps",
    "quantile_metric": "pinball_loss_alpha_0_1_then_net_utility_at_10bps",
    "classification_metric": "brier_score_then_net_utility_at_10bps",
    "inner_stage_fit": (
        "fit_imputer_scaler_ordinal_or_relevance_bins_downside_label_thresholds_prediction_"
        "thresholds_and_regime_state_on_purged_inner_train_only;transform_inner_test_without_"
        "refit"
    ),
    "outer_stage_refit": (
        "after_parameter_selection_refit_all_declared_preprocessing_label_bins_thresholds_and_"
        "regime_state_on_purged_full_outer_train_only;transform_outer_test_without_refit"
    ),
    "imputation": "active_stage_train_median_only",
    "scaling": "active_stage_train_standard_scaler_only_when_declared",
    "label_derived_artifacts": "active_stage_train_labels_only",
    "feature_selection": "fixed_preregistered_feature_contract_only",
    "outer_test_labels_never_used_for_parameter_or_threshold_selection": True,
}


def _elastic_grid() -> list[dict[str, Any]]:
    return [
        {"alpha": 0.001, "l1_ratio": 0.2, "max_iter": 10_000},
        {"alpha": 0.01, "l1_ratio": 0.2, "max_iter": 10_000},
    ]


def _linear_classifier_grid() -> list[dict[str, Any]]:
    return [
        {"C": 0.1, "class_weight": "balanced", "max_iter": 2_000},
        {"C": 1.0, "class_weight": "balanced", "max_iter": 2_000},
    ]


def _lgbm_grid(*, objective: str) -> list[dict[str, Any]]:
    return [
        {
            "objective": objective,
            "n_estimators": 120,
            "learning_rate": 0.03,
            "num_leaves": leaves,
            "max_depth": depth,
            "min_child_samples": 30,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_lambda": 1.0,
        }
        for leaves, depth in ((7, 3), (15, 5))
    ]


EXECUTION_OVERRIDES: dict[str, dict[str, Any]] = {
    "D01": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "mom_252_skip21_rank",
        "top_n": 5,
    },
    "D02": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "mom_252_skip21_rank",
        "top_n": 10,
    },
    "D03": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "industry_relative_63_rank",
        "top_n": 5,
    },
    "D04": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "industry_relative_126_rank",
        "top_n": 10,
    },
    "D05": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "relative_spy_126_rank",
        "top_n": 5,
    },
    "D06": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "relative_spy_252_skip21_rank",
        "top_n": 5,
    },
    "D07": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "mom_126_skip21_rank_plus_volume_surprise_21_63_rank",
        "score_formula": "0.7*mom_126_skip21_rank+0.3*volume_surprise_21_63_rank",
        "top_n": 5,
    },
    "D08": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "mom_126_skip21_rank_minus_volume_surprise_21_63_rank",
        "score_formula": "0.7*mom_126_skip21_rank-0.3*volume_surprise_21_63_rank",
        "top_n": 5,
    },
    "D09": {
        "task": "deterministic_buffered_rank",
        "estimator": "formula",
        "score": "mom_252_skip21_rank",
        "top_n": 5,
        "rank_buffer": 2,
        "portfolio_mapping": "retain_previous_within_top_n_plus_buffer_then_equal_weight",
    },
    "D10": {
        "task": "deterministic_buffered_rank",
        "estimator": "formula",
        "score": "mom_252_skip21_rank",
        "top_n": 5,
        "rank_buffer": 4,
        "portfolio_mapping": "retain_previous_within_top_n_plus_buffer_then_equal_weight",
    },
    "D11": {
        "task": "deterministic_risk_sizing",
        "estimator": "formula",
        "score": "mom_252_skip21_rank_div_vol_21_rank",
        "score_formula": "mom_252_skip21_rank/max(vol_21_rank,0.000001)",
        "top_n": 5,
        "portfolio_mapping": (
            "select_top5_by_score;raw_weight=1/max(vol_21_raw,0.000001);"
            "normalize_positive_weights;100pct_BIL_if_empty"
        ),
        "regime_state_policy": "excluded_formula_candidate",
        "label_horizon_bars": 21,
        "embargo_bars": 21,
        "decision_stride_bars": 21,
    },
    "D12": {
        "task": "deterministic_rank",
        "estimator": "formula",
        "score": "core_industry_volume_rank_ensemble",
        "score_components": {
            "mom_252_skip21_rank": 0.4,
            "industry_relative_126_rank": 0.3,
            "volume_surprise_21_63_rank": 0.2,
            "trend_consistency_252_rank": 0.1,
        },
        "top_n": 5,
    },
    "M01": {
        "task": "return_ranking",
        "estimator": "elastic_net",
        "target": "forward_open_to_open_excess_5d",
        "parameter_grid": _elastic_grid(),
        "preprocessing": ["train_median_imputer", "train_standard_scaler"],
        "top_n": 5,
    },
    "M02": {
        "task": "return_ranking",
        "estimator": "ordinal_logistic",
        "target": "active_stage_train_quantile_class_of_forward_open_to_open_excess_5d",
        "ordinal_classes": 5,
        "prediction_score": "class_probability_expected_value",
        "parameter_grid": _linear_classifier_grid(),
        "preprocessing": ["train_median_imputer", "train_standard_scaler"],
        "top_n": 5,
        "train_only_artifacts": ["ordinal_bin_edges", "imputer", "scaler"],
    },
    "M03": {
        "task": "return_ranking",
        "estimator": "lightgbm_regression_shallow",
        "target": "forward_open_to_open_excess_5d",
        "parameter_grid": _lgbm_grid(objective="regression_l2"),
        "preprocessing": ["train_median_imputer"],
        "top_n": 5,
    },
    "M04": {
        "task": "return_ranking",
        "estimator": "lightgbm_lambdarank_shallow",
        "target": "per_decision_date_forward_excess_relevance_0_to_4",
        "parameter_grid": _lgbm_grid(objective="lambdarank"),
        "preprocessing": ["train_median_imputer"],
        "query_group_order": "decision_date_ascending_symbol_ascending",
        "top_n": 5,
        "train_only_artifacts": ["relevance_bins", "query_groups", "imputer"],
    },
    "M05": {
        "task": "downside_quantile",
        "estimator": "hist_gradient_quantile_q10",
        "target": "forward_min_drawdown_21",
        "quantile_alpha": 0.1,
        "parameter_grid": [
            {
                "loss": "quantile",
                "quantile": 0.1,
                "max_iter": 120,
                "learning_rate": 0.04,
                "max_leaf_nodes": leaves,
                "min_samples_leaf": 25,
                "l2_regularization": 1.0,
            }
            for leaves in (7, 15)
        ],
        "preprocessing": ["train_median_imputer"],
        "risk_acceptance": (
            "predicted_q10_above_global_q20_of_fitted_active_stage_train_row_predictions"
        ),
        "regime_state_policy": "default_train_only_risk_context_regime",
        "portfolio_mapping": "D01_slot_weight_retained_when_accepted_remainder_to_BIL",
        "parent_candidate_ids": ["D01"],
        "top_n": 5,
        "risk_fallback": "BIL_cash_proxy",
    },
    "M06": {
        "task": "downside_quantile",
        "estimator": "lightgbm_quantile_q10",
        "target": "forward_min_drawdown_21",
        "quantile_alpha": 0.1,
        "parameter_grid": _lgbm_grid(objective="quantile_alpha_0_1"),
        "preprocessing": ["train_median_imputer"],
        "risk_acceptance": (
            "predicted_q10_above_global_q20_of_fitted_active_stage_train_row_predictions"
        ),
        "regime_state_policy": "default_train_only_risk_context_regime",
        "portfolio_mapping": "D01_slot_weight_retained_when_accepted_remainder_to_BIL",
        "parent_candidate_ids": ["D01"],
        "top_n": 5,
        "risk_fallback": "BIL_cash_proxy",
    },
    "M07": {
        "task": "downside_classification",
        "estimator": "logistic_downside",
        "target": "forward_min_drawdown_21_le_active_stage_train_q10",
        "parameter_grid": _linear_classifier_grid(),
        "probability_threshold_grid": [0.3, 0.5, 0.7],
        "preprocessing": ["train_median_imputer", "train_standard_scaler"],
        "regime_state_policy": "default_train_only_risk_context_regime",
        "portfolio_mapping": "D01_slot_weight_retained_below_threshold_remainder_to_BIL",
        "parent_candidate_ids": ["D01"],
        "top_n": 5,
        "risk_fallback": "BIL_cash_proxy",
        "train_only_artifacts": ["downside_threshold", "imputer", "scaler"],
    },
    "M08": {
        "task": "downside_classification",
        "estimator": "lightgbm_downside_shallow",
        "target": "forward_min_drawdown_21_le_active_stage_train_q10",
        "parameter_grid": _lgbm_grid(objective="binary_logloss"),
        "probability_threshold_grid": [0.3, 0.5, 0.7],
        "preprocessing": ["train_median_imputer"],
        "regime_state_policy": "default_train_only_risk_context_regime",
        "portfolio_mapping": "D01_slot_weight_retained_below_threshold_remainder_to_BIL",
        "parent_candidate_ids": ["D01"],
        "top_n": 5,
        "risk_fallback": "BIL_cash_proxy",
        "train_only_artifacts": ["downside_threshold", "imputer"],
    },
    "M09": {
        "task": "rank_risk_cost_sizing",
        "estimator": "fixed_blend",
        "parent_candidate_ids": ["M01", "M07"],
        "blend_formula": "0.65*pct_rank(M01)+0.35*(1-pct_rank(M07_risk_probability))",
        "portfolio_mapping": (
            "select_top5_blend;raw_weight=max(blend,0)*clip(1-risk_probability,0,1);"
            "normalize_positive_weights_remainder_to_BIL"
        ),
        "rank_buffer": 2,
        "turnover_control": "retain_previous_within_top_n_plus_buffer",
        "regime_state_policy": "inherited_from_M07_outer_train_fit",
        "top_n": 5,
        "upstream_max_label_horizon_bars": 21,
        "embargo_bars": 21,
        "composite_parent_training": {
            "outer_fold_schedule": "composite_decision_dates_every_5_bars",
            "rank_parent_train_stride_bars": 5,
            "risk_parent_train_stride_bars": 21,
            "risk_parent_train_anchor": "decision_origin_position_modulo_21_zero",
            "parent_refit": "refit_both_parents_inside_each_composite_outer_fold",
            "test_prediction_schedule": "predict_both_parents_on_every_5_bar_composite_test_date",
            "state_reuse": "none_no_asof_carry_no_native_schedule_intersection",
        },
    },
    "M10": {
        "task": "rank_risk_cost_sizing",
        "estimator": "fixed_blend",
        "parent_candidate_ids": ["M04", "M06"],
        "blend_formula": "0.65*pct_rank(M04)+0.35*pct_rank(M06_predicted_q10)",
        "portfolio_mapping": (
            "select_top5_blend;raw_weight=max(blend,0)*pct_rank(predicted_q10);"
            "normalize_positive_weights_remainder_to_BIL"
        ),
        "rank_buffer": 2,
        "turnover_control": "retain_previous_within_top_n_plus_buffer",
        "regime_state_policy": "inherited_from_M06_outer_train_fit",
        "top_n": 5,
        "upstream_max_label_horizon_bars": 21,
        "embargo_bars": 21,
        "composite_parent_training": {
            "outer_fold_schedule": "composite_decision_dates_every_5_bars",
            "rank_parent_train_stride_bars": 5,
            "risk_parent_train_stride_bars": 21,
            "risk_parent_train_anchor": "decision_origin_position_modulo_21_zero",
            "parent_refit": "refit_both_parents_inside_each_composite_outer_fold",
            "test_prediction_schedule": "predict_both_parents_on_every_5_bar_composite_test_date",
            "state_reuse": "none_no_asof_carry_no_native_schedule_intersection",
        },
    },
    "M11": {
        "task": "hybrid_shrinkage",
        "estimator": "fixed_blend",
        "parent_candidate_ids": ["D01", "M01"],
        "blend_formula": "0.75*pct_rank(D01)+0.25*pct_rank(M01)",
        "model_weight": 0.25,
        "top_n": 5,
    },
    "M12": {
        "task": "hybrid_shrinkage",
        "estimator": "fixed_blend",
        "parent_candidate_ids": ["D01", "M04"],
        "blend_formula": "0.50*pct_rank(D01)+0.50*pct_rank(M04)",
        "model_weight": 0.5,
        "top_n": 5,
    },
    "M13": {
        "task": "regime_context_ranking",
        "estimator": "elastic_net",
        "target": "forward_open_to_open_excess_5d",
        "parameter_grid": _elastic_grid(),
        "preprocessing": ["train_median_imputer", "train_standard_scaler"],
        "parent_candidate_ids": ["M01"],
        "regime_method": "fixed_spy_trend_vol",
        "regime_formula": "2*(spy_trend_126>0)+1*(spy_vol_21>0.02)",
        "regime_interactions": "multiply_each_daily_core_feature_by_regime_state",
        "top_n": 5,
    },
    "M14": {
        "task": "regime_context_ranking",
        "estimator": "lightgbm_lambdarank_shallow",
        "target": "per_decision_date_forward_excess_relevance_0_to_4",
        "parameter_grid": _lgbm_grid(objective="lambdarank"),
        "preprocessing": ["train_median_imputer"],
        "parent_candidate_ids": ["M04"],
        "regime_method": "train_only_change_point",
        "change_point_algorithm": (
            "active_stage_train_unique_dates_middle_20_to_80pct_split_minimizing_standardized_"
            "spy_trend_126_and_spy_vol_21_within_segment_sse"
        ),
        "regime_assignment": "nearest_active_stage_train_segment_centroid",
        "regime_interactions": "multiply_each_daily_core_feature_by_regime_state",
        "top_n": 5,
        "train_only_artifacts": ["change_point", "regime_state", "imputer"],
    },
    "M15": {
        "task": "negative_control",
        "estimator": "elastic_net_shuffled_training_labels",
        "target": "outer_train_only_permuted_forward_open_to_open_excess_5d",
        "fixed_parameters": {"alpha": 0.001, "l1_ratio": 0.2, "max_iter": 10_000},
        "preprocessing": ["train_median_imputer", "train_standard_scaler"],
        "parent_candidate_ids": ["M01"],
        "top_n": 5,
        "expected_control": "no_positive_oos_lift",
        "selection_prohibited": True,
        "shuffle_scope": "outer_train_rows_only_before_fit",
        "random_seed": 77,
        "fold_seed_formula": "77+outer_fold_number",
    },
    "M16": {
        "task": "negative_control",
        "estimator": "future_label_shift_rejection_control",
        "parent_candidate_ids": ["M01"],
        "prohibited_feature": "forward_open_to_open_excess_5d_shifted_to_decision_row",
        "future_shift_bars": 5,
        "availability_audit": "reject_when_feature_timestamp_greater_than_decision_timestamp",
        "fit_allowed": False,
        "top_n": 5,
        "expected_control": "non_null_lift_requires_pipeline_rejection",
        "selection_prohibited": True,
        "mandatory_outcome": "rejected_control",
    },
}


def build_q2_execution_map(candidate_manifest: dict[str, Any]) -> dict[str, Any]:
    candidates = candidate_manifest.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidate manifest requires candidates")
    by_id = {
        str(candidate.get("candidate_id") or ""): candidate
        for candidate in candidates
        if isinstance(candidate, dict)
    }
    if set(EXECUTION_OVERRIDES) != set(RUNNABLE_IDS):
        raise AssertionError("Q2 execution overrides must cover all runnable IDs")
    missing = sorted(set(RUNNABLE_IDS) - set(by_id))
    if missing:
        raise ValueError(f"Q2 candidates missing from manifest: {','.join(missing)}")
    rows = []
    for candidate_id in RUNNABLE_IDS:
        candidate = by_id[candidate_id]
        label_contract = str(candidate["label_contract"])
        label_horizon = 21 if label_contract == "daily_downside_21d" else 5
        override = EXECUTION_OVERRIDES[candidate_id]
        row = {
            "candidate_id": candidate_id,
            "path": str(candidate["path"]),
            "method": str(candidate["method"]),
            "candidate_binding_sha256": hashlib.sha256(
                json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "primitive_fields": list(PRIMITIVE_FIELDS),
            "feature_contract": str(candidate["feature_contract"]),
            "label_contract": label_contract,
            "label_horizon_bars": label_horizon,
            "embargo_bars": label_horizon,
            "decision_stride_bars": 5 if label_horizon == 5 else 21,
            "cost_contract": "daily_cost_v1",
            "cost_stress_one_way_bps": [10.0, 20.0, 40.0],
            "benchmark_contract": str(candidate["benchmark_contract"]),
            "required_benchmarks": list(BENCHMARKS),
            "feature_availability": "all_rolling_features_shifted_one_bar",
            "missing_input_policy": (
                "primitive_missing_skips_entire_decision;deterministic_derived_missing_skips_"
                "entire_decision"
                if candidate_id.startswith("D")
                else "primitive_missing_skips_entire_decision;ml_derived_missing_uses_active_"
                "stage_train_median_imputation"
            ),
            "primitive_missing_policy": (
                "skip_entire_decision_if_any_selected62_open_close_volume_row_missing_no_fill"
            ),
            "derived_feature_missing_policy": (
                "skip_entire_decision"
                if candidate_id.startswith("D")
                else "active_stage_train_median_imputation"
            ),
            "model_failure_fallback": str(candidate["fallback"]),
            "portfolio_fallback": "BIL_cash_proxy",
            "portfolio_mapping": "equal_weight_top_n",
            "research_pass": False,
            "paper_ready_pass": False,
            "promotion_eligible": False,
            **override,
        }
        rows.append(row)
    return {
        "schema_version": 2,
        "iter_id": ITER_ID,
        "scope": "historical_current_universe_diagnostic",
        "runtime_entrypoint": (
            "open_composer.research.stock_momentum_codesign_q2:run_stock_momentum_codesign_q2"
        ),
        "survivorship_labelled": True,
        "runnable_candidate_count": len(rows),
        "primitive_field_allowlist": list(PRIMITIVE_FIELDS),
        "panel_contract": {
            "selected_symbol_source": "daily-panel-manifest.selected_symbols",
            "cross_sectional_rank_universe": "exact_62_selected_symbols",
            "breadth_and_dispersion_universe": "exact_62_selected_symbols",
            "share_class_policy": "treat_symbols_as_distinct_listings_no_issuer_aggregation",
            "alignment": "exact_intersection_of_selected62_SPY_XLK_BIL_sessions",
            "decision_origin_position": 252,
            "minimum_common_sessions": 900,
            "timestamp_order": "ascending_utc",
            "duplicate_timestamp_policy": "reject",
            "benchmark_symbols": ["SPY", "XLK", "BIL"],
            "benchmark_binding_source": "daily-panel-manifest.benchmark_inputs",
            "forward_epoch_use": "none_historical_diagnostic_only",
        },
        "ranking_contract": {
            "method": "average_percentile",
            "selection_order": ["score_desc", "symbol_asc"],
            "minimum_symbols_per_decision": 62,
            "incomplete_cross_section_action": "skip_entire_decision_and_record_reason",
        },
        "missing_input_contract": {
            "validation_order": [
                "validate_exact_common_session_membership",
                "validate_selected62_primitive_open_close_volume_rows",
                "compute_one_bar_lagged_derived_features",
                "apply_candidate_path_derived_feature_policy",
                "validate_complete_selected62_future_open_label_window",
                "materialize_labels_after_feature_eligibility",
            ],
            "primitive_rows": (
                "missing_nonfinite_open_close_or_volume_for_any_selected62_symbol_skips_the_"
                "entire_decision_before_feature_computation"
            ),
            "deterministic_derived_features": (
                "missing_nonfinite_required_feature_for_any_selected62_symbol_skips_the_entire_"
                "decision"
            ),
            "ml_derived_features": (
                "missing_nonfinite_required_feature_is_imputed_from_the_active_stage_train_"
                "median_fit;inner_train_for_inner_selection_then_purged_full_outer_train_after_"
                "selection"
            ),
            "label_open_window": (
                "require_finite_open_for_all_selected62_symbols_at_offsets_0_and_5_for_five_day_"
                "labels_or_every_offset_0_through_21_for_downside_labels;otherwise_exclude_the_"
                "entire_decision_from_labelled_training_and_evaluation_before_cross_sectional_"
                "label_formation;label_completeness_must_never_change_features_scores_or_weights"
            ),
            "forward_fill_allowed": False,
            "zero_return_substitution_allowed": False,
        },
        "label_contract": {
            "entry": "decision_session_open",
            "exit": "horizon_session_open",
            "five_day_excess": "symbol_open_to_open_return_minus_selected62_mean",
            "downside_21": "minimum_open_to_open_return_over_offsets_1_through_21",
        },
        "cost_application": "half_l1_one_way_turnover_including_BIL_cash_weight",
        "reproducibility_contract": {
            "base_random_seed": 77,
            "model_threads": 1,
            "fold_initial_state": "100pct_BIL",
            "state_carry": "chronological_within_fold_only_reset_at_each_outer_fold",
            "numeric_sort_tie_break": "canonical_json_ascending",
        },
        "risk_context_regime_contract": {
            "default_train_only_risk_context_regime": (
                "fit_global_medians_of_spy_trend_126_and_spy_vol_21_on_unique_active_stage_"
                "train_dates;state=2*(trend>train_median_trend)+1*(vol>train_median_vol);"
                "inner_train_fit_applies_unchanged_to_inner_test;purged_full_outer_train_refit_"
                "applies_unchanged_to_outer_test;no_regime_interactions"
            ),
            "D11_usage": "exclude_train_only_regime_state_formula_candidate",
            "M05_M08_usage": "include_default_train_only_state_as_one_model_feature",
            "M09_M10_usage": "inherit_state_inside_declared_risk_parent_only",
            "M13_usage": "override_with_fixed_spy_trend_vol_contract",
            "M14_usage": "override_with_train_only_change_point_contract",
        },
        "benchmark_evaluation_contract": {
            "window": "same_outer_test_decision_dates_and_candidate_label_horizon",
            "cost_scenarios_bps": [10.0, 20.0, 40.0],
            "fold_start_position": "100pct_BIL_then_charge_initial_one_way_turnover",
            "terminal_turnover": "not_charged_positions_remain_held_at_fold_end",
            "same_symbol_buy_and_hold": (
                "report_each_selected62_symbol_open_to_open_path_and_cross_symbol_median;"
                "buy_at_first_fold_decision_hold_without_intermediate_rebalance;selection_"
                "ineligible"
            ),
            "equal_weight_universe": (
                "rebalance_equal_weight_selected62_each_decision_charge_realized_half_l1"
            ),
            "SPY_market_proxy": "buy_at_first_fold_decision_hold_SPY_no_intermediate_rebalance",
            "XLK_sector_proxy": "buy_at_first_fold_decision_hold_XLK_no_intermediate_rebalance",
            "BIL_cash_proxy": "hold_100pct_BIL_no_turnover",
            "ex_post_best_symbol_report_only": (
                "choose_one_selected62_symbol_maximizing_open_at_last_outer_test_decision_plus_"
                "candidate_horizon_div_open_at_first_outer_test_decision_minus_1;symbol_ascending_"
                "tie_break;buy_at_first_fold_decision_and_hold_that_same_symbol_through_the_last_"
                "outer_test_horizon_open;selection_ineligible"
            ),
            "deterministic_12_1": (
                "D01_scores_rebalance_equal_weight_top5_each_decision_on_identical_fold"
            ),
        },
        "fallback_contract": {
            "candidate_status": (
                "a_failed_candidate_remains_failed_and_fallback_returns_are_comparison_only"
            ),
            "named_candidate": (
                "use_the_already_completed_named_candidate_on_the_identical_outer_fold_and_cost_"
                "scenario;recursively_resolve_its_manifest_fallback_if_it_failed"
            ),
            "equal_weight_cash": "100pct_BIL_cash_proxy",
            "fixed_position_caps": (
                "D01_top_five_on_the_identical_outer_fold_at_exactly_20pct_each;100pct_BIL_if_"
                "D01_is_unavailable"
            ),
            "reject_if_not_null": (
                "record_rejected_control_without_fit_and_use_100pct_BIL_for_comparison_only"
            ),
            "cycle_or_resolution_failure": "100pct_BIL_cash_proxy",
            "empty_selection": "100pct_BIL_cash_proxy",
            "recursion_guard": "candidate_id_visited_set",
        },
        "fallback_precedence": [
            "record_candidate_failure_without_overwriting_candidate_metrics",
            "resolve_manifest_fallback_for_comparison_only_with_candidate_id_visited_set",
            "use_100pct_BIL_on_cycle_resolution_failure_or_empty_selection",
        ],
        "model_selection_contract": MODEL_SELECTION_CONTRACT,
        "feature_formulas": FEATURE_FORMULAS,
        "high_low_dependent_candidates_allowed": False,
        "forward_fill_allowed": False,
        "zero_return_substitution_allowed": False,
        "rows": rows,
    }
