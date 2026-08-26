from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.knowledge_memory import claim_fingerprint
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

SOURCE_ITER = "mom_pit_semantic_theme_r12"
ITER_ID = "mom_pit_semantic_theme_r13"
SOURCE_DIR = Path("reports/research/iterations") / SOURCE_ITER
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
SOURCE_CARD_PATH = Path("reports/harness/source_cards/us_pit_semantic_theme_r13.jsonl")
SOURCE_SOURCE_CARD_PATH = Path("reports/harness/source_cards/us_pit_semantic_theme_r12.jsonl")
PROMPT_PATH = Path("prompts/pit_semantic_theme_r13_factor_v1.txt")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r13_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R13D01", "d01"),
        ("R13D02", "d02"),
        ("R13M01", "m01"),
        ("R13M02", "m02"),
        ("R13L01", "l01"),
        ("R13C01", "c01"),
        ("R13F01", "f01"),
        ("R13P01", "p01"),
    )
}
CONTRACT_FILES = (
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
    "knowledge-scout-queries.json",
)


def prepare(root: Path) -> None:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    snapshot = _load_json(base / SNAPSHOT_PATH)
    quality = _load_json(base / QUALITY_PATH)
    if quality.get("status") != "ok" or quality.get("research_eligible") is not True:
        raise ValueError("R13 preparation requires a passing price-adjustment quality report")
    if snapshot.get("request_count") != 72:
        raise ValueError("R13 snapshot must bind 18 symbols x four adjustment modes")

    generated_at = datetime.now(UTC).isoformat()
    _write_source_cards(base)
    specs = _write_specs(base)
    _write_prompt(base)
    for name in CONTRACT_FILES:
        payload = _replace_r12(_load_json(base / SOURCE_DIR / name))
        _customize_contract(name, payload, base, generated_at)
        write_json(iteration / name, payload)
    _write_external_brief(base, specs, generated_at)
    _write_markdown(base)
    manifest = _candidate_manifest(base, specs)
    write_json(iteration / "candidate-manifest.json", manifest)
    _write_feasibility_and_search(base, include_knowledge_assessment=False)


def finalize(root: Path) -> None:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    for name in (
        "external-brief.json",
        "knowledge-scout.json",
        "knowledge-assessment.json",
        "model-reuse-decision.json",
        "modality-role-matrix.json",
        "candidate-manifest.json",
    ):
        if not (iteration / name).is_file():
            raise ValueError(f"R13 finalization prerequisite is missing: {name}")
    assessment = _load_json(iteration / "knowledge-assessment.json")
    if assessment.get("status") != "ok":
        raise ValueError("R13 knowledge assessment must pass before finalization")
    _write_feasibility_and_search(base, include_knowledge_assessment=True)


def _model_factors() -> dict[str, dict[str, Any]]:
    return {
        "qqq_momentum_20": _panel_factor(
            "close / lag(close, 20) - 1", "QQQ", "QQQ twenty-session momentum."
        ),
        "qqq_momentum_120": _panel_factor(
            "close / lag(close, 120) - 1", "QQQ", "QQQ long-cycle momentum state."
        ),
        "qqq_trend_gap_200": _panel_factor(
            "close / sma(close, 200) - 1", "QQQ", "QQQ long-trend distance."
        ),
        "tqqq_momentum_5": _panel_factor(
            "close / lag(close, 5) - 1", "TQQQ", "TQQQ weekly momentum."
        ),
        "tqqq_momentum_20": _panel_factor(
            "close / lag(close, 20) - 1", "TQQQ", "TQQQ monthly momentum."
        ),
        "tqqq_realized_volatility_20": _panel_factor(
            "stddev(close / lag(close, 1) - 1, 20)",
            "TQQQ",
            "TQQQ recent path volatility.",
        ),
        "tqqq_drawdown_20": _panel_factor(
            "close / highest(close, 20) - 1", "TQQQ", "TQQQ fast drawdown state."
        ),
        "tqqq_drawdown_63": _panel_factor(
            "close / highest(close, 63) - 1", "TQQQ", "TQQQ quarterly drawdown state."
        ),
        "override_momentum_10": _panel_factor(
            "close / lag(close, 10) - 1",
            "deterministic_override_candidate",
            "Current fixed-rule override candidate ten-session momentum.",
        ),
        "override_momentum_20": _panel_factor(
            "close / lag(close, 20) - 1",
            "deterministic_override_candidate",
            "Current fixed-rule override candidate twenty-session momentum.",
        ),
        "override_advantage_20": _panel_factor(
            "close / lag(close, 20) - 1",
            "deterministic_override_candidate",
            "Override candidate twenty-session momentum minus TQQQ twenty-session momentum.",
            panel_operation="candidate_minus_tqqq",
        ),
        "override_trend_gap_100": _panel_factor(
            "close / sma(close, 100) - 1",
            "deterministic_override_candidate",
            "Current fixed-rule override candidate medium-trend distance.",
        ),
        "risk_on_breadth": _panel_factor(
            "close > sma(close, 100)",
            "override_universe",
            "Fraction of preregistered override ETFs above their 100-session trend.",
            panel_operation="finite_cross_section_mean",
        ),
    }


def _panel_factor(
    expression: str,
    panel_symbol: str,
    description: str,
    *,
    panel_operation: str = "identity",
) -> dict[str, Any]:
    return {
        "source": "expression",
        "expression": expression,
        "default": 0.0,
        "description": description,
        "params": {
            "panel_symbol": panel_symbol,
            "panel_operation": panel_operation,
            "resolver": "pit_semantic_theme_r13_panel_feature_v1",
        },
    }


def _write_specs(root: Path) -> dict[str, Any]:
    source_specs = {
        candidate_id.replace("R13", "R12", 1): yaml.safe_load(
            (
                root / str(path).replace("us_pit_semantic_theme_r13", "us_pit_semantic_theme_r12")
            ).read_text(encoding="utf-8")
        )
        for candidate_id, path in SPEC_PATHS.items()
    }
    generated: dict[str, dict[str, Any]] = {}
    for candidate_id in SPEC_PATHS:
        source_id = candidate_id.replace("R13", "R12", 1)
        raw = _replace_r12(source_specs[source_id])
        generated[candidate_id] = raw

    d01 = generated["R13D01"]
    d01["description"] = (
        "Persistent high-beta core: hold TQQQ in confirmed Nasdaq risk-on states, allow only "
        "short-cycle stronger ETF overrides, and use GLD/BIL only when the QQQ trend is off."
    )
    d01["risk"]["max_position_weight"] = 1.0
    d01["portfolio"].update(
        {
            "max_symbols_per_day": 2,
            "gross_exposure_limit": 1.0,
            "max_symbol_weight": 1.0,
            "selected_route_label": "pit_semantic_theme_r13:D01:persistent_beta_override_v1",
        }
    )
    d01["factors"] = {
        "qqq_momentum_120": {
            "source": "expression",
            "expression": "close / lag(close, 120) - 1",
            "default": 0.0,
            "description": "QQQ 120-session absolute momentum risk-on gate.",
        },
        "qqq_trend_gap_200": {
            "source": "expression",
            "expression": "close / sma(close, 200) - 1",
            "default": 0.0,
            "description": "QQQ distance above its 200-session trend gate.",
        },
        "override_momentum_10": {
            "source": "expression",
            "expression": "close / lag(close, 10) - 1",
            "default": 0.0,
            "description": "Short-cycle offensive ETF momentum used by the fixed override rank.",
        },
        "override_momentum_20": {
            "source": "expression",
            "expression": "close / lag(close, 20) - 1",
            "default": 0.0,
            "description": "Twenty-session offensive ETF momentum and TQQQ-relative edge input.",
        },
        "override_trend_gap_100": {
            "source": "expression",
            "expression": "close / sma(close, 100) - 1",
            "default": 0.0,
            "description": "Offensive ETF medium-trend eligibility gate.",
        },
        "gld_momentum_60": {
            "source": "expression",
            "expression": "close / lag(close, 60) - 1",
            "default": 0.0,
            "description": "GLD defensive substitution momentum.",
        },
        "gld_trend_gap_50": {
            "source": "expression",
            "expression": "close / sma(close, 50) - 1",
            "default": 0.0,
            "description": "GLD defensive substitution trend gate.",
        },
    }
    d01["research_design"]["selection_objective"] = (
        "Approach or exceed TQQQ-like upside with a 45% net CAGR target at 20 bps while "
        "accepting drawdown down to -65% and avoiding permanent low-beta exposure."
    )
    d01["notes"].update(
        {
            "candidate_role": "deterministic_persistent_high_beta_core",
            "method": "persistent_tqqq_short_cycle_override_v1",
            "fallback_candidate_id": "GLD80_BIL20_then_BIL100",
            "factor_library_ids": [
                "underlying_moving_average_leverage_gate",
                "core_beta_sleeve",
                "leadership_satellite_rank",
                "stress_only_defensive_sleeve",
            ],
            "route_contract": {
                "risk_on": "QQQ_above_SMA200_or_momentum120_positive",
                "default_symbol": "TQQQ",
                "override_symbols": [
                    "QLD",
                    "SOXL",
                    "TECL",
                    "ROM",
                    "USD",
                    "SMH",
                    "SOXX",
                    "XLK",
                    "IGV",
                ],
                "override_eligibility": (
                    "momentum10_positive_and_momentum20_positive_and_above_SMA100_and_"
                    "momentum20_exceeds_TQQQ_by_2pp"
                ),
                "override_score": "0.6_momentum10_plus_0.4_momentum20",
                "minimum_hold_sessions": 3,
                "switch_score_advantage_pp": 3.0,
                "risk_off": "GLD80_BIL20_if_GLD_momentum60_positive_and_above_SMA50_else_BIL100",
                "strategy_equity_throttle": False,
                "volatility_position_scaling": False,
            },
        }
    )

    m01 = generated["R13M01"]
    m01["description"] = (
        "Fold-local logistic override classifier; the default remains the deterministic "
        "high-beta route unless a preregistered offensive ETF is likely to beat TQQQ net of cost."
    )
    m01["risk"]["max_position_weight"] = 1.0
    m01["portfolio"].update(
        {
            "cross_sectional_execution_profile": "generic",
            "max_symbols_per_day": 2,
            "gross_exposure_limit": 1.0,
            "max_symbol_weight": 1.0,
            "selected_route_label": "pit_semantic_theme_r13:M01:relative_override_logit_v1",
            "rebalance_schedule": "every_bar",
            "weighting": "equal_weight",
        }
    )
    m01["factors"] = _model_factors()
    m01["model"] = {
        "kind": "logistic_regression_classifier",
        "label": {"type": "forward_direction", "horizon_bars": 5, "threshold_pct": 0.0},
        "features": list(_model_factors()),
        "training": {
            "window_bars": 756,
            "retrain_every_bars": 5,
            "test_window_bars": 63,
            "embargo_bars": 10,
            "seed": 13101,
        },
        "selection": {"method": "threshold", "threshold": 0.60},
        "hyperparameters": {
            "C": 0.25,
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 1000,
            "class_weight": "balanced",
        },
        "baseline": "none",
    }
    m01["notes"].update(
        {
            "candidate_role": "fold_local_relative_override_classifier",
            "method": "logistic_tqqq_relative_override_v1",
            "fallback_candidate_id": "R13D01",
            "low_confidence_action": "D01_risk_off_branch_or_TQQQ_core",
            "factor_library_ids": [
                "core_beta_sleeve",
                "leadership_satellite_rank",
                "tech_canary_breadth",
            ],
        }
    )

    m02 = json.loads(json.dumps(m01))
    m02["name"] = "us_pit_semantic_theme_r13_m02"
    m02["description"] = (
        "Fold-local LightGBM tail-survival diagnostic layered on M01; it may exit only on "
        "high-confidence five-session path risk and otherwise preserves the high-beta target."
    )
    m02["portfolio"]["selected_route_label"] = "pit_semantic_theme_r13:M02:tail_exit_lgbm_v1"
    m02["model"]["kind"] = "lightgbm_classifier"
    m02["model"]["label"] = {
        "type": "path_survival",
        "horizon_bars": 5,
        "max_drawdown_pct": 12.0,
        "min_terminal_return_pct": -5.0,
    }
    m02["model"]["selection"] = {"method": "threshold", "threshold": 0.35}
    m02["model"]["training"]["seed"] = 13102
    m02["model"]["hyperparameters"] = {
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
    }
    m02["notes"].update(
        {
            "candidate_id": "R13M02",
            "candidate_role": "fold_local_tail_survival_exit_diagnostic",
            "method": "lightgbm_high_confidence_tail_exit_v1",
            "fallback_candidate_id": "R13M01_then_R13D01",
            "low_confidence_action": "preserve_R13M01_target",
            "factor_library_ids": [
                "drawdown_guard_20_60",
                "momentum_crash_rebound_guard",
                "volatility_managed_leverage_state",
            ],
        }
    )
    m02["research_design"]["parameter_space"]["candidate_id"] = ["R13M02"]
    generated["R13M02"] = m02

    f01 = json.loads(json.dumps(m01))
    f01["name"] = "us_pit_semantic_theme_r13_f01"
    f01["description"] = "Exact no-semantic-input identity control for R13M01."
    f01["portfolio"]["selected_route_label"] = "pit_semantic_theme_r13:F01:exact_m01_fallback"
    f01["notes"].update(
        {
            "candidate_id": "R13F01",
            "candidate_role": "missing_modality_exact_m01_fallback",
            "method": "exact_r13m01_without_semantic_inputs_v1",
            "fallback_candidate_id": "R13M01_then_R13D01",
        }
    )
    f01["research_design"]["parameter_space"]["candidate_id"] = ["R13F01"]
    generated["R13F01"] = f01

    for candidate_id in ("R13C01", "R13P01"):
        generated[candidate_id]["model"] = json.loads(json.dumps(m01["model"]))
        generated[candidate_id]["factors"].update(json.loads(json.dumps(_model_factors())))
    generated["R13P01"]["notes"]["placebo_seed"] = 13108

    for candidate_id, raw in generated.items():
        raw["risk"]["max_position_weight"] = 1.0
        raw["portfolio"]["gross_exposure_limit"] = 1.0
        raw["portfolio"]["max_symbol_weight"] = 1.0
        raw["data"].update(
            {
                "source": "alpaca",
                "path": SNAPSHOT_PATH.as_posix(),
                "feed": "sip",
            }
        )
        raw["data_assumptions"].update(
            {
                "source": "alpaca",
                "adjusted": True,
                "acquisition_tier": "research_strict",
                "immutable_snapshot_required": True,
                "snapshot_manifest_path": SNAPSHOT_PATH.as_posix(),
                "price_adjustment_quality_path": QUALITY_PATH.as_posix(),
            }
        )
        raw["research_design"]["source_cards_path"] = SOURCE_CARD_PATH.as_posix()
        if raw.get("execution_policy"):
            raw["execution_policy"]["policy_id"] = "r13_protected_opg_v1"
        path = root / SPEC_PATHS[candidate_id]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(raw, sort_keys=False, width=110), encoding="utf-8")

    return {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }


def _write_prompt(root: Path) -> None:
    source = root / "prompts/pit_semantic_theme_r12_factor_v1.txt"
    target = root / PROMPT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_replace_text(source.read_text(encoding="utf-8")), encoding="utf-8")


def _write_source_cards(root: Path) -> None:
    source = root / SOURCE_SOURCE_CARD_PATH
    target = root / SOURCE_CARD_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    retained: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("claim_id") == "r12_ridge_finite_sample_bias_variance":
            continue
        retained.append(_replace_r12(row))
    new_cards = [
        {
            "iteration_id": ITER_ID,
            "verification_status": "source_verified",
            "verified_at": "2026-08-05T15:36:41Z",
            "verification_method": "arxiv_official_api_metadata_and_abstract",
            "claim_id": "r13_structured_news_dimensions",
            "claim": (
                "A 2026 FNSPID classification study reports that event type, impact subject, "
                "time horizon, and confidence add information beyond FinBERT sentiment in its "
                "news-stock classification task."
            ),
            "source_url": "https://arxiv.org/abs/2607.28496",
            "source_type": "paper",
            "accessed_at": "2026-08-05",
            "applies_to": ["llm_or_news_signal", "structured_theme_factor", "R13L01"],
            "impact_on_spec": (
                "Keep event type, affected entity, direction, confidence, and horizon as "
                "separate PIT fields instead of collapsing every article to sentiment."
            ),
            "limitations": (
                "This is a recent arXiv classification experiment, not a tradable-return or "
                "transaction-cost study; it supplies no R13 alpha or promotion evidence."
            ),
        },
        {
            "iteration_id": ITER_ID,
            "verification_status": "source_verified",
            "verified_at": "2026-08-05T15:36:41Z",
            "verification_method": "arxiv_official_api_metadata_and_abstract",
            "claim_id": "r13_dynamic_financial_knowledge_graph_simulation",
            "claim": (
                "A 2026 working paper proposes time-varying supplier, customer, competitor, and "
                "technology-ecosystem links for cross-entity event propagation and reports only "
                "controlled simulation and Russell-1000-calibrated simulation results."
            ),
            "source_url": "https://arxiv.org/abs/2607.10932",
            "source_type": "paper",
            "accessed_at": "2026-08-05",
            "applies_to": ["dynamic_theme_membership", "economic_relationships", "R13D02"],
            "impact_on_spec": (
                "Use source-bound, expiring economic links to form changing themes such as AI "
                "infrastructure or robotics without freezing a modern stock basket through history."
            ),
            "limitations": (
                "The reported predictive results are simulations, not real-market OOS returns; "
                "implicit links may not be treated as facts without source packets."
            ),
        },
    ]
    target.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n"
            for row in [*retained, *new_cards]
        ),
        encoding="utf-8",
    )


def _customize_contract(
    name: str,
    payload: dict[str, Any],
    root: Path,
    generated_at: str,
) -> None:
    payload["iter_id"] = ITER_ID
    if "generated_at" in payload:
        payload["generated_at"] = generated_at
    if name == "data-contract.json":
        scope = payload["historical_price_scope"]
        scope.update(
            {
                "provider": "alpaca",
                "feed": "sip",
                "adjustment": "independent_raw_split_dividend_all",
                "snapshot_manifest_path": SNAPSHOT_PATH.as_posix(),
                "snapshot_manifest_sha256": _sha256(root / SNAPSHOT_PATH),
                "quality_report_path": QUALITY_PATH.as_posix(),
                "quality_report_sha256": _sha256(root / QUALITY_PATH),
                "allowed_candidate_ids": ["R13D01", "R13M01", "R13M02", "R13F01"],
                "limitations": [
                    "historical_prices_are_globally_exposed_development_data",
                    "provider_all_is_not_local_corporate_action_lineage",
                    "no_historical_stock_membership_claim",
                ],
            }
        )
    elif name == "feature-contract.json":
        payload["single_hypothesis"] = (
            "persistent high beta should be the default; ML may only authorize a short-cycle "
            "TQQQ-relative override or a high-confidence tail exit, while semantic themes "
            "remain forward-only and zero-capital"
        )
        payload["semantic_features"]["prompt_path"] = PROMPT_PATH.as_posix()
        payload["capital"]["fallbacks"]["R13M02"] = "R13M01_then_R13D01"
        payload["deterministic_route"] = {
            "candidate_id": "R13D01",
            "route_label": "pit_semantic_theme_r13:D01:persistent_beta_override_v1",
            "parameters_frozen": True,
            "risk_on_gate": "QQQ_above_SMA200_or_momentum120_positive",
            "default_risk_on_target": {"TQQQ": 1.0},
            "override_symbols": [
                "QLD",
                "SOXL",
                "TECL",
                "ROM",
                "USD",
                "SMH",
                "SOXX",
                "XLK",
                "IGV",
            ],
            "override_eligibility": {
                "momentum_10_min": 0.0,
                "momentum_20_min": 0.0,
                "trend_sma_sessions": 100,
                "momentum_20_advantage_over_TQQQ_pp": 2.0,
            },
            "override_score": {"momentum_10": 0.6, "momentum_20": 0.4},
            "minimum_hold_sessions": 3,
            "switch_score_advantage_pp": 3.0,
            "risk_off_target": {
                "if_GLD_momentum60_positive_and_above_SMA50": {"GLD": 0.8, "BIL": 0.2},
                "otherwise": {"BIL": 1.0},
            },
            "strategy_equity_throttle": False,
            "volatility_position_scaling": False,
        }
        payload["quant_features"].update(
            {
                "candidate_ids": ["R13M01", "R13M02", "R13C01", "R13F01", "R13P01"],
                "families": [
                    "QQQ_trend_and_momentum",
                    "TQQQ_short_path_momentum_volatility_drawdown",
                    "deterministic_override_candidate_momentum_and_trend",
                    "TQQQ_relative_override_advantage",
                    "override_universe_breadth",
                ],
                "resolver": "pit_semantic_theme_r13_panel_feature_v1",
                "feature_names": list(_model_factors()),
            }
        )
        payload["model_roles"] = {
            "R13M01": {
                "kind": "logistic_regression_classifier",
                "decision": "authorize_fixed_override_candidate_instead_of_D01_target",
                "probability_threshold": 0.60,
                "low_confidence_action": "D01_risk_off_branch_or_TQQQ_core",
            },
            "R13M02": {
                "kind": "lightgbm_classifier",
                "decision": "exit_M01_target_only_when_path_survival_probability_below_0.35",
                "low_confidence_action": "preserve_R13M01_target",
            },
        }
        payload["placebo"]["seed"] = 13108
    elif name == "label-contract.json":
        payload["labels"]["R13M01"] = {
            "type": "fixed_override_beats_TQQQ_net_binary",
            "horizon_sessions": 5,
            "cost_bps": 20.0,
            "fit_scope": "fold_train_only",
            "positive_when": (
                "eligible_override_open_to_open_return_minus_TQQQ_open_to_open_return_minus_"
                "incremental_switch_cost_is_positive"
            ),
        }
        payload["labels"]["R13M02"] = {
            "type": "TQQQ_path_survival_binary",
            "horizon_sessions": 5,
            "maximum_path_drawdown_pct": 12.0,
            "minimum_terminal_return_pct": -5.0,
            "fit_scope": "fold_train_only",
            "positive_when": "both_path_drawdown_and_terminal_return_limits_hold",
        }
    elif name == "validation-contract.json":
        folds = payload["chronological_folds"]
        folds.update(
            {
                "minimum_train_sessions": 756,
                "oos_sessions": 252,
                "capacity_basis": (
                    "18_symbol_common_SIP_sessions_through_2025-07-31_checked_before_model_fit"
                ),
            }
        )
        payload["pbo"]["selection_candidate_ids"] = ["R13D01", "R13M01", "R13M02"]
        payload["model_gates"] = {
            "R13M01": (
                "Logistic override must improve net CAGR or MAR over D01 in at least three OOS "
                "folds, preserve at least 95% of D01 upside capture, and keep annualized "
                "one-way turnover at or below 12"
            ),
            "R13M02": (
                "Tail exit must improve maximum drawdown by at least five percentage points "
                "versus M01, retain at least 95% of M01 CAGR, and improve tail outcomes in at "
                "least three OOS folds"
            ),
            "R13F01": "target and prediction identity with M01 for every matched session",
        }
        payload["route_integrity_gates"] = {
            "D01_default_risk_on_target_is_TQQQ100": True,
            "D01_average_risk_asset_exposure_floor": 0.80,
            "M01_low_confidence_uses_TQQQ_core_or_D01_risk_off_branch": True,
            "M02_non_tail_exact_M01": True,
            "minimum_hold_sessions": 3,
            "maximum_annualized_one_way_turnover": 12.0,
        }
        payload["semantic_gates"]["stock_budget_during_R13"] = 0.0
    elif name == "holdout-contract.json":
        payload.update(
            {
                "available_diagnostic_transfer_holdout_sessions_at_lock": 252,
                "holdout_capacity_basis": (
                    "18_symbol_common_SIP_sessions_through_2026-08-03_checked_before_model_fit"
                ),
                "access_count": 0,
                "model_outcomes_not_read_before_lock": True,
            }
        )
    elif name == "cumulative-trial-contract.json":
        payload.update(
            {
                "prior_effective_trial_count": 8046,
                "effective_trial_count": 8054,
                "prior_trial_evidence": {
                    "path": (
                        "reports/research/iterations/mom_pit_semantic_theme_r12/"
                        "historical-evaluation/evaluation-report.json"
                    ),
                    "status": "valid_clean_data_stop_price_paths",
                },
            }
        )
    elif name == "universe-contract.json":
        payload["contract_id"] = "r13_dynamic_universe_v1"
        payload["execution_universe_role"] = (
            "fixed_ETF_risk_and_execution_core_only_not_dynamic_theme_membership"
        )
        payload["fixed_short_cycle_override_symbols"] = [
            "QLD",
            "SOXL",
            "TECL",
            "ROM",
            "USD",
            "SMH",
            "SOXX",
            "XLK",
            "IGV",
        ]
        payload["dynamic_theme_membership_rule"] = (
            "members_must_enter_from_post_epoch_source_packets_and_expire_after_3_to_20_sessions"
        )
    elif name == "modality-role-matrix.json":
        for row in payload["roles"]:
            if row["role"] == "return_ranking":
                row.update(
                    {
                        "modalities": ["price", "trend", "TQQQ_relative_override_state"],
                        "candidates": ["R13D01", "R13M01", "R13C01", "R13F01", "R13P01"],
                        "method": "deterministic_short_cycle_override_then_logistic_authorization",
                        "fallback": "R13D01",
                    }
                )
            if row["role"] == "risk_prediction":
                row.update(
                    {
                        "modalities": ["price", "path_drawdown", "volatility"],
                        "candidates": ["R13D01", "R13M02"],
                        "method": "deterministic_trend_off_plus_fold_local_tail_survival",
                        "fallback": "R13M01_then_R13D01",
                    }
                )
            if row["role"] == "regime_meta_gate":
                row.update(
                    {
                        "candidates": ["R13D01", "R13M01", "R13M02"],
                        "method": "persistent_TQQQ_core_with_sparse_override_and_tail_exit",
                        "fallback": "R13D01",
                    }
                )
        for row in payload["required_ablations"]:
            if row["candidate"] == "R13M01":
                row["ablation"] = "quant_only_logistic_relative_override"
            elif row["candidate"] == "R13M02":
                row["ablation"] = "quant_only_lightgbm_tail_exit"
    elif name == "model-reuse-decision.json":
        payload["round_decision"] = {
            "action": "fit_from_scratch",
            "reason": (
                "R12 clean-data Ridge and LightGBM route rankers lost persistent beta and "
                "generated 41-56x annual turnover; R13 changes the labels and decision roles "
                "to sparse relative override and tail exit, so no estimator can be reused"
            ),
            "source_iteration": SOURCE_ITER,
            "source_status": "stop_price_paths",
            "snapshot_sha256": _sha256(root / SNAPSHOT_PATH),
            "feature_contract_status": "new_epoch",
            "validation_contract_status": "new_epoch",
            "warm_start": False,
        }
    elif name == "knowledge-scout-queries.json":
        payload["scout_network_status"] = {
            "status": "fresh_network_evidence_added",
            "observed_at": "2026-08-05",
            "action": (
                "reuse verified momentum and execution claims; add structured-news and dynamic-"
                "relationship evidence while retaining their non-alpha limitations"
            ),
        }
        payload["curated_candidates"] = [
            row
            for row in payload["curated_candidates"]
            if row.get("discovery_id") != "r13_ridge_finite_sample_bias_variance"
        ]
        payload["curated_candidates"].extend(
            [
                {
                    "discovery_id": "r13_structured_news_dimensions",
                    "url": "https://arxiv.org/abs/2607.28496",
                    "title": (
                        "Beyond Sentiment: Structured Information Extraction from Financial News"
                    ),
                    "summary": (
                        "FNSPID classification experiments report incremental information in "
                        "event type, scope, horizon, and confidence beyond sentiment."
                    ),
                    "published_at": "2026-07-30T16:41:55Z",
                    "authors": ["Daohan Zhu", "Sitong Ge", "Ruofei Wang", "et al."],
                    "source_type": "paper",
                    "topics": ["structured financial news", "event dimensions", "ablation"],
                },
                {
                    "discovery_id": "r13_dynamic_financial_knowledge_graph_simulation",
                    "url": "https://arxiv.org/abs/2607.10932",
                    "title": (
                        "LLM-Enhanced Dynamic Financial Knowledge Graphs for Cross-Entity "
                        "Signal Propagation and alpha discovery"
                    ),
                    "summary": (
                        "Dynamic economic relationships and signal propagation are evaluated in "
                        "controlled simulations only."
                    ),
                    "published_at": "2026-07-12T21:44:05Z",
                    "authors": ["Lin Zhang"],
                    "source_type": "paper",
                    "topics": ["dynamic knowledge graph", "cross-entity propagation", "simulation"],
                },
            ]
        )


def _write_external_brief(root: Path, specs: dict[str, Any], generated_at: str) -> None:
    payload = _replace_r12(_load_json(root / SOURCE_DIR / "external-brief.json"))
    payload.update(
        {
            "iter_id": ITER_ID,
            "strategy_name": specs["R13D01"].name,
            "objective": (
                "Test whether a persistent TQQQ core with sparse, short-cycle offensive ETF "
                "overrides can reach the preregistered high-return gates; let fold-local ML "
                "authorize only TQQQ-relative overrides or tail exits, while changing semantic "
                "themes remain forward-only and zero-capital."
            ),
            "source_spec_path": SPEC_PATHS["R13D01"].as_posix(),
            "spec_hash": strategy_content_hash(specs["R13D01"]),
            "current_source_card_paths": [SOURCE_CARD_PATH.as_posix()],
            "hypothesis_links": ["R13-H1"],
            "generated_at": generated_at,
        }
    )
    revisions = {row["candidate_id"]: row for row in payload["candidate_matrix_revisions"]}
    revisions["R13D01"]["revision"] = (
        "replace the low-exposure equity-curve throttle with a persistent TQQQ risk-on core "
        "and fixed short-cycle relative-strength overrides"
    )
    revisions["R13M01"]["revision"] = (
        "fold-local logistic classifier authorizes only an eligible override versus TQQQ; "
        "low confidence is exact D01"
    )
    revisions["R13M02"]["revision"] = (
        "fold-local LightGBM path-survival diagnostic can only make high-confidence tail exits"
    )
    payload["sources"] = [
        row for row in payload["sources"] if row.get("url") != "https://arxiv.org/abs/2608.02539"
    ]
    payload["source_evidence_bindings"] = [
        row
        for row in payload["source_evidence_bindings"]
        if row.get("source_card_claim_id") != "r13_ridge_finite_sample_bias_variance"
    ]
    payload["topic_coverage"] = [
        topic for topic in payload["topic_coverage"] if topic != "ridge_finite_sample_bias_variance"
    ]
    additions = [
        {
            "url": "https://arxiv.org/abs/2607.28496",
            "claim_id": "r13_structured_news_dimensions",
            "published_or_updated_at": "2026-07-30",
            "core_claim": (
                "A 2026 FNSPID classification study reports that event type, impact subject, "
                "time horizon, and confidence add information beyond FinBERT sentiment in its "
                "news-stock classification task."
            ),
            "project_applicability": (
                "Keep separate structured event fields and require matched missing-modality and "
                "placebo controls."
            ),
            "reflection": "Classification lift is not return alpha or execution evidence.",
            "topic": "structured_news_dimensions",
        },
        {
            "url": "https://arxiv.org/abs/2607.10932",
            "claim_id": "r13_dynamic_financial_knowledge_graph_simulation",
            "published_or_updated_at": "2026-07-12",
            "core_claim": (
                "A 2026 working paper proposes time-varying supplier, customer, competitor, and "
                "technology-ecosystem links for cross-entity event propagation and reports only "
                "controlled simulation and Russell-1000-calibrated simulation results."
            ),
            "project_applicability": (
                "Use expiring, source-bound economic links to define changing themes rather than "
                "a fixed historical stock basket."
            ),
            "reflection": "Simulation evidence cannot establish live economic links or R13 alpha.",
            "topic": "dynamic_relationship_graphs",
        },
    ]
    for addition in additions:
        claim = addition["core_claim"]
        fingerprint = claim_fingerprint(claim)
        payload["sources"].append(
            {
                "url": addition["url"],
                "published_or_updated_at": addition["published_or_updated_at"],
                "source_type": "paper",
                "credibility": "recent arXiv working paper metadata and abstract",
                "core_claim": claim,
                "project_applicability": addition["project_applicability"],
                "reflection": addition["reflection"],
            }
        )
        payload["source_evidence_bindings"].append(
            {
                "canonical_url": addition["url"],
                "source_card_claim_id": addition["claim_id"],
                "claim_fingerprint": fingerprint,
                "brief_claim_fingerprint": fingerprint,
            }
        )
        payload["topic_coverage"].append(addition["topic"])
    write_json(root / ITERATION_DIR / "external-brief.json", payload)


def _write_markdown(root: Path) -> None:
    iteration = root / ITERATION_DIR
    (iteration / "hypotheses.md").write_text(
        "\n".join(
            [
                "# Hypotheses: mom_pit_semantic_theme_r13",
                "",
                "## R13-H1",
                "",
                (
                    "- Hypothesis: R12 underperformed because it structurally removed beta. A "
                    "persistent TQQQ risk-on core with sparse 10/20-session relative-strength "
                    "overrides can recover upside; Logistic ML may authorize only overrides and "
                    "LightGBM may make only high-confidence tail exits."
                ),
                (
                    "- Failure mode: D01 still misses the 45% net CAGR or 80% TQQQ upside-capture "
                    "gate, M01 adds turnover without stable lift, M02 exits too often and loses "
                    "upside, or semantic packets cannot prove changing membership."
                ),
                (
                    "- Measurement: four 252-session chronological OOS folds, 10-session "
                    "purge and embargo, 10/20/40 bps costs, matched D01/TQQQ/QQQ/SPY/BIL "
                    "benchmarks, DSR, CSCV PBO, exact F01 fallback, and forward-only semantic "
                    "ablations."
                ),
                (
                    "- Stop/Pivot criterion: do not tune any R13 threshold after results. Open the "
                    "transfer holdout only for a development-pass price candidate; otherwise "
                    "start a new iteration with one new hypothesis. Semantic stock capital "
                    "remains zero regardless of historical price results."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (iteration / "search-space.md").write_text(
        "\n".join(
            [
                "# Search Space: mom_pit_semantic_theme_r13",
                "",
                (
                    "Exactly eight preregistered roles are counted: deterministic high-beta "
                    "D01, deterministic semantic D02, Logistic override M01, LightGBM "
                    "tail-exit M02, "
                    "structured semantic L01, combined C01, exact missing-modality F01, and "
                    "shuffled placebo P01. There is no parameter sweep. All price candidates "
                    "share one immutable SIP snapshot, features, labels, folds, costs, and "
                    "benchmark family. Semantic roles are dependency-skipped historically and "
                    "begin only with forward point-in-time packets."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (iteration / "decision-record.md").write_text(
        "\n".join(
            [
                "# Decision Record: mom_pit_semantic_theme_r13",
                "",
                "## Preregistration",
                "",
                "- Path: clean SIP price core with forward-only dynamic semantic themes.",
                (
                    "- Decision: authorize only the clean-price D01/M01/M02/F01 historical "
                    "evaluation after the pre-backtest dossier passes."
                ),
                (
                    "- Reason: valid R12 diagnostics showed that the deterministic route averaged "
                    "only 37.8% risk exposure and 19.9% TQQQ upside capture, while independent ETF "
                    "rankers incurred roughly 41-56x annual one-way turnover."
                ),
                (
                    "- Data: bind the immutable 72-request Alpaca SIP "
                    "raw/split/dividend/all snapshot and its passing adjustment-quality report."
                ),
                (
                    "- Model change: M01 is a regularized Logistic classifier for whether the "
                    "already eligible override beats TQQQ over five opens; M02 is a LightGBM "
                    "five-session path-survival diagnostic. Both fit from scratch in every fold."
                ),
                (
                    "- Dynamic themes: current examples such as AI infrastructure or robotics "
                    "are not permanent membership. D02/L01/C01/P01 remain historical "
                    "dependency-skipped and require future source-bound news or SEC packets."
                ),
                (
                    "- Safety: workflow, research, LLM contribution, Paper readiness, order "
                    "authority, and broker writes remain separate false states."
                ),
                "- Next iteration suggestion: stop if no price candidate clears the frozen gates; "
                "open a new epoch for any threshold, universe, or semantic-budget change.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (iteration / "external-brief.md").write_text(
        "\n".join(
            [
                "# External Brief: mom_pit_semantic_theme_r13",
                "",
                (
                    "R13 reuses the verified evidence assembled through R12 on time-varying "
                    "product "
                    "networks, customer momentum, attention decay, narrative factors, "
                    "point-in-time SEC/news handling, leveraged-ETF path risk, and opening "
                    "execution. The new empirical question is narrow: does preserving TQQQ as "
                    "the default risk-on target, while permitting only sparse short-cycle "
                    "overrides and tail exits, repair the beta and turnover failures observed in "
                    "R12? AI infrastructure and robotics remain examples of current event-defined "
                    "themes, not a stock basket replayed backward."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _candidate_manifest(root: Path, specs: dict[str, Any]) -> dict[str, Any]:
    source = _replace_r12(_load_json(root / SOURCE_DIR / "candidate-manifest.json"))
    source["iter_id"] = ITER_ID
    source["spec_hashes"] = {
        path.as_posix(): strategy_content_hash(specs[candidate_id])
        for candidate_id, path in SPEC_PATHS.items()
    }
    contract_names = {
        "data": ("r13_pit_semantic_theme_data_v1", "data-contract.json"),
        "features": ("r13_pit_semantic_theme_features_v1", "feature-contract.json"),
        "labels": ("r13_labels_v1", "label-contract.json"),
        "validation": ("r13_validation_v1", "validation-contract.json"),
        "costs": ("r13_costs_v1", "cost-contract.json"),
        "benchmarks": ("r13_benchmark_family_v1", "benchmark-contract.json"),
    }
    source["contracts"] = {
        group: {
            contract_id: {
                "path": (ITERATION_DIR / name).as_posix(),
                "sha256": _sha256(root / ITERATION_DIR / name),
            }
        }
        for group, (contract_id, name) in contract_names.items()
    }
    by_id = {row["candidate_id"]: row for row in source["candidates"]}
    by_id["R13D01"].update(
        {
            "role": "deterministic_persistent_high_beta_core",
            "method": "persistent_tqqq_short_cycle_override_v1",
            "ablation": "deterministic_high_beta",
            "fallback": "GLD80_BIL20_then_BIL100",
        }
    )
    by_id["R13M01"].update(
        {
            "role": "fold_local_relative_override_classifier",
            "method": "logistic_tqqq_relative_override_v1",
            "ablation": "quant_only_logistic_relative_override",
            "fallback": "R13D01",
        }
    )
    by_id["R13M02"].update(
        {
            "role": "fold_local_tail_survival_exit_diagnostic",
            "method": "lightgbm_high_confidence_tail_exit_v1",
            "ablation": "quant_only_lightgbm_tail_exit",
            "fallback": "R13M01_then_R13D01",
        }
    )
    by_id["R13F01"].update(
        {
            "role": "missing_modality_exact_m01_fallback",
            "method": "exact_r13m01_without_semantic_inputs_v1",
        }
    )
    by_id["R13P01"]["placebo_seed"] = 13108
    return source


def _write_feasibility_and_search(root: Path, *, include_knowledge_assessment: bool) -> None:
    iteration = root / ITERATION_DIR
    manifest = _load_json(iteration / "candidate-manifest.json")
    payload = _replace_r12(_load_json(root / SOURCE_DIR / "data-feasibility.json"))
    payload.update(
        {
            "report_type": "pit_semantic_theme_r13_data_feasibility",
            "iter_id": ITER_ID,
            "generated_at": datetime.now(UTC).isoformat(),
            "conclusion": "clean_SIP_price_paths_authorized_semantic_paths_forward_only",
        }
    )
    payload["data_scope"] = {
        "historical_price_panel": (
            "Alpaca SIP immutable daily raw/split/dividend/all bundle for 18 ETFs, with 2,388 "
            "complete sessions from 2017-02-01 through 2026-08-03"
        ),
        "historical_price_quality": "passed_with_zero_blockers_and_four_cross_mode_warnings",
        "development_fold_capacity": "4 x 252 OOS sessions through 2025-07-31",
        "transfer_holdout_capacity": "252 sessions from 2025-08-01 through 2026-08-03",
        "historical_semantic_packets": False,
        "historical_semantic_membership": False,
        "forward_news_capability": (
            "registered_live_collector_implemented; R12 observed 49 source packets but none "
            "count toward the new R13 epoch"
        ),
        "forward_sec_capability": "collector_implemented_requires_valid_SEC_USER_AGENT",
        "forward_llm_capability": "collector_implemented_requires_valid_OPENAI_API_KEY",
        "semantic_stock_budget": 0.0,
    }
    payload["path_gates"]["trained_ml"].update(
        {
            "scope": "fold_local_Logistic_override_and_LightGBM_tail_exit_on_clean_SIP_bundle",
            "candidate_ids": ["R13M01", "R13M02"],
        }
    )
    by_candidate = {row["candidate_id"]: row for row in manifest["candidates"]}
    for row in payload["candidate_authorization"]["rows"]:
        candidate = by_candidate[row["candidate_id"]]
        row["candidate_binding_sha256"] = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if row["candidate_id"] == "R13M01":
            row["reason_code"] = (
                "clean_SIP_price_features_available_for_fold_local_relative_override_Logistic"
            )
        elif row["candidate_id"] == "R13M02":
            row["reason_code"] = "clean_SIP_paths_available_for_fold_local_LightGBM_tail_exit"
    references = {
        "universe_contract": ITERATION_DIR / "universe-contract.json",
        "historical_price_snapshot": SNAPSHOT_PATH,
        "price_adjustment_quality": QUALITY_PATH,
        "data_contract": ITERATION_DIR / "data-contract.json",
        "validation_contract": ITERATION_DIR / "validation-contract.json",
        "holdout_contract": ITERATION_DIR / "holdout-contract.json",
        "capability_registry": Path("capabilities/registry.yaml"),
        "source_cards": SOURCE_CARD_PATH,
        "modality_role_matrix": ITERATION_DIR / "modality-role-matrix.json",
        "model_reuse_decision": ITERATION_DIR / "model-reuse-decision.json",
        "llm_prompt": PROMPT_PATH,
    }
    if include_knowledge_assessment:
        references["knowledge_assessment"] = ITERATION_DIR / "knowledge-assessment.json"
    payload["required_reference_names"] = list(references)
    payload["required_references"] = {
        name: {"path": path.as_posix(), "sha256": _sha256(root / path)}
        for name, path in references.items()
    }
    payload["blockers"] = [
        "historical_semantic_PIT_packets_missing",
        "historical_dynamic_stock_membership_missing",
        "R13_forward_epoch_not_started",
        "valid_OPENAI_API_KEY_required_for_independent_LLM_factors",
        "valid_SEC_USER_AGENT_required_for_SEC_packets",
        "paper_order_authority_false",
    ]
    write_json(iteration / "data-feasibility.json", payload)

    search = _replace_r12(_load_json(root / SOURCE_DIR / "search-space.json"))
    search.update(
        {
            "iter_id": ITER_ID,
            "objective": (
                "Test a persistent TQQQ core, sparse short-cycle overrides, fold-local relative "
                "override and tail-exit models, and forward-only changing semantic themes."
            ),
            "candidate_manifest_path": (ITERATION_DIR / "candidate-manifest.json").as_posix(),
            "candidate_manifest_sha256": _sha256(iteration / "candidate-manifest.json"),
            "data_feasibility_path": (ITERATION_DIR / "data-feasibility.json").as_posix(),
            "data_feasibility_sha256": _sha256(iteration / "data-feasibility.json"),
            "cost_table_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
        }
    )
    d01_spec = load_strategy_spec(root / SPEC_PATHS["R13D01"])
    search["source_spec_path"] = SPEC_PATHS["R13D01"].as_posix()
    search["spec_hash"] = strategy_content_hash(d01_spec)
    trained = next(row for row in search["paths"] if row["name"] == "trained_ml")
    deterministic = next(row for row in search["paths"] if row["name"] == "deterministic_price")
    deterministic["parameters"].update(
        {
            "candidate_ids": ["R13D01"],
            "route_label": "pit_semantic_theme_r13:D01:persistent_beta_override_v1",
            "default_risk_on_target": "TQQQ100",
            "minimum_hold_sessions": 3,
            "parameter_search": False,
        }
    )
    trained["parameters"].update(
        {
            "candidate_ids": ["R13M01", "R13M02"],
            "model_family": "Logistic_relative_override_plus_LightGBM_tail_exit",
            "fold_count": 4,
            "fold_oos_sessions": 252,
            "hyperparameter_search": False,
            "m01_probability_threshold": 0.60,
            "m02_tail_exit_survival_threshold": 0.35,
        }
    )
    write_json(iteration / "search-space.json", search)


def _replace_r12(value: Any) -> Any:
    if isinstance(value, dict):
        return {_replace_text(str(key)): _replace_r12(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_r12(item) for item in value]
    if isinstance(value, str):
        return _replace_text(value)
    return value


def _replace_text(value: str) -> str:
    return value.replace("R12", "R13").replace("r12", "r13")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
