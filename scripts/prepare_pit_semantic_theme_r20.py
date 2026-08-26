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

SOURCE_ITER = "mom_pit_semantic_theme_r19"
ITER_ID = "mom_pit_semantic_theme_r20"
SOURCE_DIR = Path("reports/research/iterations") / SOURCE_ITER
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
SOURCE_CARD_PATH = Path("reports/harness/source_cards/us_pit_semantic_theme_r20.jsonl")
SOURCE_SOURCE_CARD_PATH = Path("reports/harness/source_cards/us_pit_semantic_theme_r19.jsonl")
PROMPT_PATH = Path("prompts/pit_semantic_theme_r20_factor_v1.txt")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r20_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R20D01", "d01"),
        ("R20D02", "d02"),
        ("R20M01", "m01"),
        ("R20M02", "m02"),
        ("R20L01", "l01"),
        ("R20C01", "c01"),
        ("R20F01", "f01"),
        ("R20P01", "p01"),
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
TECH_BREADTH_SYMBOLS = ("QQQ", "XLK", "IGV", "SOXX", "SMH")
RECOVERY_QQQ_TREND_SESSIONS = 50
RECOVERY_TQQQ_MOMENTUM_SESSIONS = 10
RECOVERY_TQQQ_MOMENTUM_MIN = 0.08
RECOVERY_BREADTH_TREND_SESSIONS = 100
RECOVERY_BREADTH_MIN_COUNT = 4
USD_PRESSURE_DRAWDOWN_SESSIONS = 20
USD_PRESSURE_DRAWDOWN_MAX = -0.20
USD_PRESSURE_RECOVERY_TREND_SESSIONS = 100
USD_PRESSURE_RECOVERY_MOMENTUM_SESSIONS = 20
USD_PRESSURE_RECOVERY_MOMENTUM_MIN = 0.0
R20_NEW_SOURCE_CLAIM = (
    "The SEC-filed USD summary prospectus states that Index volatility has a negative impact "
    "on the Fund's holding-period returns and may affect them as much as or more than the Index "
    "return; its hypothetical table gives a -50.2% Fund return when the one-year Index return "
    "is -20% and annualized Index volatility is 50%."
)
R20_NEW_SOURCE_URL = (
    "https://www.sec.gov/Archives/edgar/data/1174610/000119312525220600/f42921d1.htm"
)
R20_NEW_SOURCE_DOCUMENT_SHA256 = "9298e5780220cfe5b1d72f618ddc27859397e6dd06f0e419d67da080ddf7bab3"
R20_CRASH_BRAKE_SOURCE_CLAIM = (
    "A 2026 working paper reports that a fast crash-brake overlay using drawdown and other "
    "real-time states reduced walk-forward maximum drawdown for a fixed ETF risk sleeve, but "
    "also lowered CAGR during a strong post-2022 rebound; the authors frame the overlays as "
    "drawdown-control tools rather than standalone return-enhancement claims."
)
R20_CRASH_BRAKE_SOURCE_URL = "https://arxiv.org/abs/2606.09025"
R20_CRASH_BRAKE_DOCUMENT_SHA256 = "e489ea3cb18c3cb7bd5d47a7651cc44711b7c2623ca6657bc25c6ec56346a706"


def _stress_recovery_contract() -> dict[str, Any]:
    return {
        "stress_target": "QQQ",
        "recovery_target": "TQQQ",
        "qqq_trend_sessions": RECOVERY_QQQ_TREND_SESSIONS,
        "tqqq_momentum_sessions": RECOVERY_TQQQ_MOMENTUM_SESSIONS,
        "tqqq_momentum_min": RECOVERY_TQQQ_MOMENTUM_MIN,
        "breadth_symbols": list(TECH_BREADTH_SYMBOLS),
        "breadth_trend_sessions": RECOVERY_BREADTH_TREND_SESSIONS,
        "breadth_min_count": RECOVERY_BREADTH_MIN_COUNT,
        "failed_condition_returns_to_stress_immediately": True,
    }


def _usd_pressure_contract() -> dict[str, Any]:
    return {
        "trigger_drawdown_sessions": USD_PRESSURE_DRAWDOWN_SESSIONS,
        "trigger_drawdown_max": USD_PRESSURE_DRAWDOWN_MAX,
        "recovery_trend_sessions": USD_PRESSURE_RECOVERY_TREND_SESSIONS,
        "recovery_momentum_sessions": USD_PRESSURE_RECOVERY_MOMENTUM_SESSIONS,
        "recovery_momentum_min": USD_PRESSURE_RECOVERY_MOMENTUM_MIN,
        "latch_until_recovery": True,
        "pressure_target": "QQQ",
        "suppresses_tqqq_recovery": True,
    }


def prepare(root: Path) -> None:
    base = root.resolve()
    iteration = base / ITERATION_DIR
    snapshot = _load_json(base / SNAPSHOT_PATH)
    quality = _load_json(base / QUALITY_PATH)
    if quality.get("status") != "ok" or quality.get("research_eligible") is not True:
        raise ValueError("R20 preparation requires a passing price-adjustment quality report")
    if snapshot.get("request_count") != 72:
        raise ValueError("R20 snapshot must bind 18 symbols x four adjustment modes")

    generated_at = datetime.now(UTC).isoformat()
    _write_source_cards(base)
    specs = _write_specs(base)
    _write_prompt(base)
    for name in CONTRACT_FILES:
        payload = _replace_r19(_load_json(base / SOURCE_DIR / name))
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
            raise ValueError(f"R20 finalization prerequisite is missing: {name}")
    assessment = _load_json(iteration / "knowledge-assessment.json")
    if assessment.get("status") != "ok":
        raise ValueError("R20 knowledge assessment must pass before finalization")
    model_reuse_path = iteration / "model-reuse-decision.json"
    model_reuse = _load_json(model_reuse_path)
    model_reuse["round_decision"] = _model_reuse_round_decision(base)
    write_json(model_reuse_path, model_reuse)
    _write_capability_reviews(base)
    _write_feasibility_and_search(base, include_knowledge_assessment=True)


def _write_capability_reviews(root: Path) -> None:
    packet_schema = Path("schemas/pit_semantic_theme_forward_packet.schema.json")
    semantic_runtime = Path("open_composer/research/pit_semantic_theme_forward.py")
    for candidate_id in ("R20D02", "R20L01", "R20C01", "R20P01"):
        spec = load_strategy_spec(root / SPEC_PATHS[candidate_id])
        payload = {
            "strategy_name": spec.name,
            "reviewed_at": "2026-08-05",
            "capabilities": [
                {
                    "capability_id": "market.alpaca_bars",
                    "kind": "market",
                    "status": "ok",
                    "strict_behavior": "fail_fast_for_unsupported_timeframes",
                    "paper_ready": True,
                    "notes": (
                        "Daily bars are supported; R20 historical research binds an immutable "
                        "SIP snapshot and does not use fixture fallback."
                    ),
                },
                {
                    "capability_id": "events.sec_filings",
                    "kind": "event",
                    "status": "partial",
                    "strict_behavior": "forward_visibility_from_acceptance_or_fetch_time",
                    "paper_ready": False,
                    "notes": (
                        "Official SEC packets are forward-only. Live collection requires a valid "
                        "contact-form SEC_USER_AGENT and measured coverage."
                    ),
                },
                {
                    "capability_id": "news.alpaca",
                    "kind": "news",
                    "status": "partial",
                    "strict_behavior": "forward_only_fail_closed",
                    "paper_ready": False,
                    "notes": (
                        "The registry capability is trial. Fixture records validate shape only; "
                        "historical downloads do not establish local first-seen time."
                    ),
                },
            ],
            "feature_packet_pit_check": "pass",
            "feature_packet_evidence": {
                "source_packet_schema_path": packet_schema.as_posix(),
                "source_packet_schema_sha256": _sha256(root / packet_schema),
                "semantic_runtime_path": semantic_runtime.as_posix(),
                "semantic_runtime_sha256": _sha256(root / semantic_runtime),
                "source_fields": [
                    "published_at",
                    "fetched_at",
                    "first_seen_at",
                    "visible_at",
                    "source",
                    "input_hash",
                ],
                "semantic_materialization_fields": [
                    "prompt_hash",
                    "model",
                    "model_parameters_hash",
                    "structured_output_hash",
                ],
            },
            "sample_data_caveats": [
                "news.alpaca and SEC fixtures are contract tests, not research or paper evidence"
            ],
            "historical_semantic_alpha_authorized": False,
            "semantic_stock_budget": 0.0,
            "blockers": [
                "new R20 forward epoch has no counted live semantic sessions",
                "news.alpaca live coverage and revision handling are not yet paper-qualified",
                "SEC live collection requires a valid contact-form SEC_USER_AGENT",
            ],
            "conclusion": "warning",
        }
        write_json(
            root / "reports/harness/data" / f"{spec.name}-capability-review.json",
            payload,
        )


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
        "tqqq_momentum_20": _panel_factor(
            "close / lag(close, 20) - 1", "TQQQ", "TQQQ monthly momentum."
        ),
        "tqqq_momentum_60": _panel_factor(
            "close / lag(close, 60) - 1", "TQQQ", "TQQQ quarterly momentum."
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
        "smh_momentum_20": _panel_factor(
            "close / lag(close, 20) - 1", "SMH", "SMH monthly momentum."
        ),
        "smh_momentum_60": _panel_factor(
            "close / lag(close, 60) - 1", "SMH", "SMH quarterly momentum."
        ),
        "smh_momentum_120": _panel_factor(
            "close / lag(close, 120) - 1", "SMH", "SMH six-month momentum."
        ),
        "smh_relative_momentum_120": _panel_factor(
            "close / lag(close, 120) - 1",
            "SMH",
            "SMH six-month momentum minus QQQ six-month momentum.",
            panel_operation="smh_minus_qqq",
        ),
        "smh_trend_gap_150": _panel_factor(
            "close / sma(close, 150) - 1", "SMH", "SMH distance above its 150-day trend."
        ),
        "usd_momentum_20": _panel_factor(
            "close / lag(close, 20) - 1", "USD", "USD monthly momentum."
        ),
        "usd_momentum_60": _panel_factor(
            "close / lag(close, 60) - 1", "USD", "USD quarterly momentum."
        ),
        "usd_trend_gap_100": _panel_factor(
            "close / sma(close, 100) - 1", "USD", "USD distance above its 100-day trend."
        ),
        "usd_drawdown_20": _panel_factor(
            "close / highest(close, 20) - 1", "USD", "USD fast drawdown state."
        ),
        "tech_breadth_100": _panel_factor(
            "close > sma(close, 100)",
            "QQQ_XLK_IGV_SOXX_SMH",
            "Fraction of technology canaries above their 100-session trend.",
            panel_operation="finite_cross_section_mean",
        ),
    }


def _recovery_factors() -> dict[str, dict[str, Any]]:
    return {
        "qqq_trend_gap_50": _panel_factor(
            "close / sma(close, 50) - 1",
            "QQQ",
            "QQQ distance above its 50-session trend for stress recovery.",
        ),
        "tqqq_momentum_10": _panel_factor(
            "close / lag(close, 10) - 1",
            "TQQQ",
            "TQQQ ten-session momentum for stress recovery.",
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
            "resolver": "pit_semantic_theme_r20_panel_feature_v1",
        },
    }


def _write_specs(root: Path) -> dict[str, Any]:
    source_specs = {
        candidate_id.replace("R20", "R19", 1): yaml.safe_load(
            (
                root / str(path).replace("us_pit_semantic_theme_r20", "us_pit_semantic_theme_r19")
            ).read_text(encoding="utf-8")
        )
        for candidate_id, path in SPEC_PATHS.items()
    }
    generated: dict[str, dict[str, Any]] = {}
    for candidate_id in SPEC_PATHS:
        source_id = candidate_id.replace("R20", "R19", 1)
        raw = _replace_r19(source_specs[source_id])
        generated[candidate_id] = raw

    d01 = generated["R20D01"]
    d01["description"] = (
        "Full-gross high-beta state: hold QQQ in confirmed Nasdaq stress, recover temporarily "
        "to TQQQ only on the frozen fast rebound signal, and otherwise hold USD at full weight. "
        "A USD 20-session drawdown latch forces QQQ until USD trend and momentum recover."
    )
    d01["risk"]["max_position_weight"] = 1.0
    d01["portfolio"].update(
        {
            "max_symbols_per_day": 1,
            "gross_exposure_limit": 1.0,
            "max_symbol_weight": 1.0,
            "selected_route_label": "pit_semantic_theme_r20:D01:usd_pressure_latch_v1",
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
        "qqq_trend_gap_50": _recovery_factors()["qqq_trend_gap_50"],
        "tqqq_momentum_10": _recovery_factors()["tqqq_momentum_10"],
        "tech_breadth_100": _model_factors()["tech_breadth_100"],
        "usd_momentum_20": _model_factors()["usd_momentum_20"],
        "usd_trend_gap_100": _model_factors()["usd_trend_gap_100"],
        "usd_drawdown_20": _model_factors()["usd_drawdown_20"],
    }
    d01["research_design"]["selection_objective"] = (
        "Approach or exceed TQQQ-like upside with a 45% net CAGR target at 20 bps while "
        "accepting drawdown down to -65% and avoiding permanent low-beta exposure."
    )
    d01["notes"].update(
        {
            "candidate_role": "deterministic_usd100_core_with_pressure_latch",
            "method": "usd100_core_qqq_stress_recovery_pressure_latch_v1",
            "fallback_candidate_id": "R19D01_without_USD_pressure_latch",
            "factor_library_ids": [
                "underlying_moving_average_leverage_gate",
                "core_beta_sleeve",
                "semiconductor_beta_core",
                "tech_canary_breadth",
                "risk_on_recovery_boost",
                "drawdown_guard_20_60",
            ],
            "route_contract": {
                "stress_state": "QQQ_below_SMA200_and_momentum120_nonpositive",
                "stress_target": {"QQQ": 1.0},
                "stress_recovery": _stress_recovery_contract(),
                "normal_risk_on_target": {"USD": 1.0},
                "usd_pressure_override": _usd_pressure_contract(),
                "review_every_sessions": 5,
                "minimum_hold_sessions": 10,
                "stress_override_immediate": True,
                "strategy_equity_throttle": False,
                "volatility_position_scaling": False,
            },
        }
    )

    m01 = generated["R20M01"]
    m01["description"] = (
        "Fold-local Logistic classifier that may replace the deterministic USD100 normal core "
        "with TQQQ only at high confidence; low confidence and all USD pressure sessions "
        "preserve exact D01."
    )
    m01["risk"]["max_position_weight"] = 1.0
    m01["portfolio"].update(
        {
            "cross_sectional_execution_profile": "generic",
            "max_symbols_per_day": 1,
            "gross_exposure_limit": 1.0,
            "max_symbol_weight": 1.0,
            "selected_route_label": "pit_semantic_theme_r20:M01:tqqq_override_logit_v1",
            "rebalance_schedule": "every_bar",
            "weighting": "equal_weight",
        }
    )
    m01["factors"] = {**_model_factors(), **_recovery_factors()}
    m01["model"] = {
        "kind": "logistic_regression_classifier",
        "label": {"type": "forward_direction", "horizon_bars": 20, "threshold_pct": 0.0},
        "features": list(_model_factors()),
        "training": {
            "window_bars": 756,
            "retrain_every_bars": 20,
            "test_window_bars": 63,
            "embargo_bars": 21,
            "seed": 15101,
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
            "candidate_role": "fold_local_tqqq_over_usd_override_classifier",
            "method": "logistic_tqqq100_vs_usd100_v1",
            "fallback_candidate_id": "R20D01",
            "low_confidence_action": ("exact_D01_QQQ_stress_or_pressure_TQQQ_recovery_or_USD_core"),
            "factor_library_ids": [
                "core_beta_sleeve",
                "leadership_satellite_rank",
                "tech_canary_breadth",
                "risk_on_recovery_boost",
            ],
        }
    )

    m02 = json.loads(json.dumps(m01))
    m02["name"] = "us_pit_semantic_theme_r20_m02"
    m02["description"] = (
        "Fold-local LightGBM tail-survival diagnostic layered on M01; it may exit only on "
        "high-confidence ten-session path risk and otherwise preserves the high-beta target."
    )
    m02["portfolio"]["selected_route_label"] = "pit_semantic_theme_r20:M02:tail_exit_lgbm_v1"
    m02["model"]["kind"] = "lightgbm_classifier"
    m02["model"]["label"] = {
        "type": "path_survival",
        "horizon_bars": 10,
        "max_drawdown_pct": 20.0,
        "min_terminal_return_pct": -8.0,
    }
    m02["model"]["selection"] = {"method": "threshold", "threshold": 0.20}
    m02["model"]["training"]["seed"] = 15102
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
            "candidate_id": "R20M02",
            "candidate_role": "fold_local_tail_survival_exit_diagnostic",
            "method": "lightgbm_high_confidence_tail_exit_v1",
            "fallback_candidate_id": "R20M01_then_R20D01",
            "low_confidence_action": "preserve_R20M01_target",
            "factor_library_ids": [
                "drawdown_guard_20_60",
                "momentum_crash_rebound_guard",
                "volatility_managed_leverage_state",
            ],
        }
    )
    m02["research_design"]["parameter_space"]["candidate_id"] = ["R20M02"]
    generated["R20M02"] = m02

    f01 = json.loads(json.dumps(m01))
    f01["name"] = "us_pit_semantic_theme_r20_f01"
    f01["description"] = "Exact no-semantic-input identity control for R20M01."
    f01["portfolio"]["selected_route_label"] = "pit_semantic_theme_r20:F01:exact_m01_fallback"
    f01["notes"].update(
        {
            "candidate_id": "R20F01",
            "candidate_role": "missing_modality_exact_m01_fallback",
            "method": "exact_r20m01_without_semantic_inputs_v1",
            "fallback_candidate_id": "R20M01_then_R20D01",
        }
    )
    f01["research_design"]["parameter_space"]["candidate_id"] = ["R20F01"]
    generated["R20F01"] = f01

    semantic_factor_names = {
        "R20C01": ("theme_confidence", "theme_direction"),
        "R20P01": ("shuffled_theme_direction",),
    }
    for candidate_id in ("R20C01", "R20P01"):
        generated[candidate_id]["model"] = json.loads(json.dumps(m01["model"]))
        inherited_factors = generated[candidate_id]["factors"]
        generated[candidate_id]["factors"] = {
            name: inherited_factors[name] for name in semantic_factor_names[candidate_id]
        }
        generated[candidate_id]["factors"].update(json.loads(json.dumps(_model_factors())))
        generated[candidate_id]["factors"].update(json.loads(json.dumps(_recovery_factors())))
    generated["R20P01"]["notes"]["placebo_seed"] = 15108

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
            raw["execution_policy"]["policy_id"] = "r20_protected_opg_v1"
        path = root / SPEC_PATHS[candidate_id]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(raw, sort_keys=False, width=110), encoding="utf-8")

    return {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }


def _write_prompt(root: Path) -> None:
    source = root / "prompts/pit_semantic_theme_r19_factor_v1.txt"
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
        retained.append(_replace_r19(row))
    retained.append(
        {
            "iteration_id": ITER_ID,
            "verification_status": "source_verified",
            "verified_at": "2026-08-05T22:17:00Z",
            "verification_method": "fresh_SEC_EDGAR_official_summary_prospectus_retrieval",
            "claim_id": "r20_usd_volatility_path_risk",
            "claim": R20_NEW_SOURCE_CLAIM,
            "source_url": R20_NEW_SOURCE_URL,
            "source_type": "regulatory_docs",
            "accessed_at": "2026-08-05",
            "document_updated_at": "2025-09-26",
            "retrieved_document_sha256": R20_NEW_SOURCE_DOCUMENT_SHA256,
            "applies_to": ["leveraged_etf", "path_risk", "R20D01", "R20M02"],
            "impact_on_spec": (
                "Preregister a path-pressure state for the leveraged semiconductor core while "
                "retaining matched costs, fold tests, and an untouched transfer holdout."
            ),
            "limitations": (
                "The prospectus example is hypothetical and does not validate R20 Alpha, the "
                "selected drawdown boundary, recovery conditions, or Paper execution."
            ),
        }
    )
    retained.append(
        {
            "iteration_id": ITER_ID,
            "verification_status": "source_verified",
            "verified_at": "2026-08-05T22:24:03Z",
            "verification_method": "arxiv_official_api_metadata_and_abstract",
            "claim_id": "r20_crash_brake_drawdown_cagr_tradeoff",
            "claim": R20_CRASH_BRAKE_SOURCE_CLAIM,
            "source_url": R20_CRASH_BRAKE_SOURCE_URL,
            "source_type": "paper",
            "accessed_at": "2026-08-05",
            "document_updated_at": "2026-06-14",
            "retrieved_document_sha256": R20_CRASH_BRAKE_DOCUMENT_SHA256,
            "applies_to": ["path_risk", "drawdown_control", "R20D01"],
            "impact_on_spec": (
                "Treat the USD pressure latch as a risk-control hypothesis that must preserve "
                "the preregistered CAGR and fold gates, not as presumed return enhancement."
            ),
            "limitations": (
                "The working paper studies a different multi-asset sleeve and a richer cash "
                "overlay, leaves multiple-testing adjustment for future work, and does not "
                "validate R20 assets, thresholds, costs, or Paper execution."
            ),
        }
    )
    target.write_text(
        "".join(
            json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n" for row in retained
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
                "allowed_candidate_ids": ["R20D01", "R20M01", "R20M02", "R20F01"],
                "limitations": [
                    "historical_prices_are_globally_exposed_development_data",
                    "provider_all_is_not_local_corporate_action_lineage",
                    "no_historical_stock_membership_claim",
                ],
            }
        )
    elif name == "feature-contract.json":
        payload["single_hypothesis"] = (
            "preserve every R19 route and model contract, but latch an immediate QQQ pressure "
            "override when USD's 20-session drawdown reaches the already frozen -20% tail "
            "boundary; release only after USD is above SMA100 with positive 20-session "
            "momentum; all other thresholds, schedules, folds, costs, and semantic roles remain "
            "frozen"
        )
        payload["semantic_features"]["prompt_path"] = PROMPT_PATH.as_posix()
        payload["capital"]["fallbacks"]["R20M02"] = "R20M01_then_R20D01"
        payload["deterministic_route"] = {
            "candidate_id": "R20D01",
            "route_label": "pit_semantic_theme_r20:D01:usd_pressure_latch_v1",
            "parameters_frozen": True,
            "stress_gate": "QQQ_below_SMA200_and_momentum120_nonpositive",
            "stress_target": {"QQQ": 1.0},
            "stress_recovery": _stress_recovery_contract(),
            "normal_risk_on_target": {"USD": 1.0},
            "usd_pressure_override": _usd_pressure_contract(),
            "review_every_sessions": 5,
            "minimum_hold_sessions": 10,
            "stress_override_immediate": True,
            "strategy_equity_throttle": False,
            "volatility_position_scaling": False,
        }
        payload["quant_features"].update(
            {
                "candidate_ids": ["R20M01", "R20M02", "R20C01", "R20F01", "R20P01"],
                "families": [
                    "QQQ_trend_and_momentum",
                    "TQQQ_path_momentum_volatility_drawdown",
                    "SMH_leadership_and_QQQ_relative_momentum",
                    "USD_momentum_trend_and_drawdown",
                    "technology_canary_breadth",
                    "stress_recovery_route_fields_not_model_features",
                ],
                "resolver": "pit_semantic_theme_r20_panel_feature_v1",
                "feature_names": list(_model_factors()),
            }
        )
        payload["model_roles"] = {
            "R20M01": {
                "kind": "logistic_regression_classifier",
                "decision": "authorize_fixed_TQQQ100_instead_of_USD100",
                "probability_threshold": 0.60,
                "low_confidence_action": (
                    "exact_D01_QQQ_stress_or_pressure_TQQQ_recovery_or_USD_core"
                ),
            },
            "R20M02": {
                "kind": "lightgbm_classifier",
                "decision": "exit_M01_target_to_QQQ_only_when_survival_probability_below_0.20",
                "low_confidence_action": "preserve_R20M01_target",
            },
        }
        payload["placebo"]["seed"] = 15108
    elif name == "label-contract.json":
        payload["timing"].update({"purge_sessions": 21, "embargo_sessions": 21})
        payload["labels"]["R20M01"] = {
            "type": "fixed_TQQQ100_beats_USD100_net_binary",
            "horizon_sessions": 20,
            "cost_bps": 20.0,
            "fit_scope": "fold_train_only",
            "positive_when": (
                "TQQQ100_open_to_open_return_minus_USD100_open_to_open_return_minus_"
                "incremental_switch_cost_is_positive; authorization_is_used_only_in_normal_"
                "risk_on_state"
            ),
        }
        payload["labels"]["R20M02"] = {
            "type": "actual_D01_route_path_survival_binary",
            "horizon_sessions": 10,
            "maximum_path_drawdown_pct": 20.0,
            "minimum_terminal_return_pct": -8.0,
            "fit_scope": "fold_train_only",
            "route_basis": (
                "the exact scheduled D01 target at the decision, including USD pressure and "
                "recovery hold state"
            ),
            "positive_when": "both_path_drawdown_and_terminal_return_limits_hold",
        }
    elif name == "validation-contract.json":
        folds = payload["chronological_folds"]
        folds.update(
            {
                "minimum_train_sessions": 756,
                "oos_sessions": 252,
                "purge_sessions": 21,
                "embargo_sessions": 21,
                "capacity_basis": (
                    "18_symbol_common_SIP_sessions_through_2025-07-31_checked_before_model_fit"
                ),
            }
        )
        payload["pbo"]["selection_candidate_ids"] = ["R20D01", "R20M01", "R20M02"]
        payload["model_gates"] = {
            "R20M01": (
                "Logistic TQQQ100 override must improve net CAGR or MAR over D01 in at "
                "least three OOS folds, preserve at least 95% of D01 upside capture, and keep "
                "annualized one-way turnover at or below 12"
            ),
            "R20M02": (
                "Tail exit must improve maximum drawdown by at least five percentage points "
                "versus M01, retain at least 95% of M01 CAGR, and improve tail outcomes in at "
                "least three OOS folds"
            ),
            "R20F01": "target and prediction identity with M01 for every matched session",
        }
        payload["route_integrity_gates"] = {
            "D01_default_risk_on_target_is_USD100": True,
            "D01_stress_target_is_QQQ100": True,
            "D01_stress_recovery_contract": _stress_recovery_contract(),
            "D01_USD_pressure_contract": _usd_pressure_contract(),
            "D01_pressure_suppresses_TQQQ_recovery": True,
            "D01_failed_recovery_condition_returns_immediately_to_QQQ100": True,
            "D01_average_risk_asset_exposure_floor": 0.99,
            "M01_low_confidence_uses_exact_D01_stress_recovery_route": True,
            "M02_non_tail_exact_M01": True,
            "review_every_sessions": 5,
            "minimum_hold_sessions": 10,
            "maximum_annualized_one_way_turnover": 12.0,
        }
        payload["semantic_gates"]["stock_budget_during_R20"] = 0.0
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
                "prior_effective_trial_count": 8102,
                "effective_trial_count": 8110,
                "prior_trial_evidence": {
                    "path": (
                        "reports/research/iterations/mom_pit_semantic_theme_r19/"
                        "historical-evaluation/evaluation-report.json"
                    ),
                    "status": "valid_clean_data_stop_price_paths_R19",
                },
                "adaptive_selection_disclosure": (
                    "USD was the exposed development window's ex-post best benchmark symbol; "
                    "R20 development evidence is adaptive and cannot establish Alpha without "
                    "a separately locked one-time transfer-holdout pass"
                ),
            }
        )
    elif name == "universe-contract.json":
        payload["contract_id"] = "r20_dynamic_universe_v1"
        payload["execution_universe_role"] = (
            "fixed_ETF_risk_and_execution_core_only_not_dynamic_theme_membership"
        )
        payload.pop("fixed_short_cycle_override_symbols", None)
        payload["fixed_execution_state_symbols"] = ["QQQ", "TQQQ", "USD"]
        payload["dynamic_theme_membership_rule"] = (
            "members_must_enter_from_post_epoch_source_packets_and_expire_after_3_to_20_sessions"
        )
    elif name == "modality-role-matrix.json":
        for row in payload["roles"]:
            if row["role"] == "return_ranking":
                row.update(
                    {
                        "modalities": ["price", "trend", "leveraged_semiconductor_beta"],
                        "candidates": ["R20D01", "R20M01", "R20C01", "R20F01", "R20P01"],
                        "method": "USD100_normal_core_then_logistic_TQQQ100_override",
                        "fallback": "R20D01",
                    }
                )
            if row["role"] == "risk_prediction":
                row.update(
                    {
                        "modalities": ["price", "path_drawdown", "volatility"],
                        "candidates": ["R20D01", "R20M02"],
                        "method": (
                            "deterministic_USD_drawdown_pressure_latch_plus_fold_local_tail_"
                            "survival"
                        ),
                        "fallback": "R20M01_then_R20D01",
                    }
                )
            if row["role"] == "regime_meta_gate":
                row.update(
                    {
                        "candidates": ["R20D01", "R20M01", "R20M02"],
                        "method": (
                            "full_gross_USD_core_QQQ_stress_and_pressure_TQQQ_recovery_with_"
                            "rare_QQQ_tail_exit"
                        ),
                        "fallback": "R20D01",
                    }
                )
        for row in payload["required_ablations"]:
            if row["candidate"] == "R20M01":
                row["ablation"] = "quant_only_logistic_TQQQ100_override"
            elif row["candidate"] == "R20M02":
                row["ablation"] = "quant_only_lightgbm_tail_exit"
    elif name == "model-reuse-decision.json":
        payload["round_decision"] = _model_reuse_round_decision(root)
    elif name == "knowledge-scout-queries.json":
        payload["scout_network_status"] = {
            "status": "fresh_verified_sources_reused",
            "observed_at": "2026-08-05",
            "action": (
                "reuse the verified time-series-momentum own-trend claim, current ProShares and "
                "SEC product contracts, and the finalized R19 route-level negative evidence"
            ),
        }


def _model_reuse_round_decision(root: Path) -> dict[str, Any]:
    return {
        "action": "refit_from_same_frozen_contract_without_warm_start",
        "reason": (
            "R19D01 reached 48.37% net CAGR and -64.76% maximum drawdown but beat QQQ in only "
            "two of four folds. Exposed route decomposition attributes F1 and F4 relative loss "
            "to USD100 sessions, while F2 and F3 require retaining USD upside. R20 therefore "
            "adds only the preregistered USD pressure latch and preserves all model families, "
            "schedules, costs, folds, and thresholds. Both models refit fold-locally without "
            "prior estimators"
        ),
        "source_iteration": SOURCE_ITER,
        "source_status": "stop_price_paths",
        "negative_evidence_iteration": "mom_pit_semantic_theme_r19",
        "negative_evidence_status": "stop_price_paths",
        "snapshot_sha256": _sha256(root / SNAPSHOT_PATH),
        "feature_contract_status": "new_epoch",
        "validation_contract_status": "new_epoch",
        "warm_start": False,
    }


def _write_external_brief(root: Path, specs: dict[str, Any], generated_at: str) -> None:
    payload = _replace_r19(_load_json(root / SOURCE_DIR / "external-brief.json"))
    payload.update(
        {
            "iter_id": ITER_ID,
            "strategy_name": specs["R20D01"].name,
            "objective": (
                "Preserve the complete R19 price and model route, but add one deterministic USD "
                "pressure latch: trigger QQQ at the frozen -20% 20-session drawdown boundary "
                "and release only above USD SMA100 with positive 20-session momentum. All model "
                "families, thresholds, folds, costs, and zero-capital semantic roles remain "
                "unchanged."
            ),
            "source_spec_path": SPEC_PATHS["R20D01"].as_posix(),
            "spec_hash": strategy_content_hash(specs["R20D01"]),
            "current_source_card_paths": [SOURCE_CARD_PATH.as_posix()],
            "hypothesis_links": ["R20-H1"],
            "generated_at": generated_at,
        }
    )
    revisions = {row["candidate_id"]: row for row in payload["candidate_matrix_revisions"]}
    revisions["R20D01"]["revision"] = (
        "preserve R19 exactly and add the fixed USD drawdown pressure latch"
    )
    revisions["R20M01"]["revision"] = (
        "preserve R19 Logistic TQQQ override and inherit the deterministic pressure latch"
    )
    revisions["R20M02"]["revision"] = (
        "preserve R19 LightGBM path-survival diagnostic on the newly scheduled D01 route"
    )
    payload["sources"].append(
        {
            "core_claim": R20_NEW_SOURCE_CLAIM,
            "credibility": "freshly retrieved official SEC EDGAR summary prospectus",
            "project_applicability": (
                "Motivates testing a fixed own-path pressure state for USD without claiming "
                "that the regulatory disclosure selects a profitable threshold."
            ),
            "published_or_updated_at": "2025-09-26",
            "reflection": (
                "The disclosure establishes volatility and compounding risk, not R20 Alpha or "
                "Paper readiness."
            ),
            "source_type": "regulatory_docs",
            "url": R20_NEW_SOURCE_URL,
        }
    )
    payload["source_evidence_bindings"].append(
        {
            "brief_claim_fingerprint": claim_fingerprint(R20_NEW_SOURCE_CLAIM),
            "canonical_url": R20_NEW_SOURCE_URL,
            "claim_fingerprint": claim_fingerprint(R20_NEW_SOURCE_CLAIM),
            "source_card_claim_id": "r20_usd_volatility_path_risk",
        }
    )
    payload["topic_coverage"].append("USD_volatility_path_risk")
    payload["sources"].append(
        {
            "core_claim": R20_CRASH_BRAKE_SOURCE_CLAIM,
            "credibility": "freshly retrieved arXiv official API metadata and abstract",
            "project_applicability": (
                "Treat the pressure latch as a drawdown-control hypothesis and require it to "
                "retain the fixed CAGR and chronological-fold gates."
            ),
            "published_or_updated_at": "2026-06-14",
            "reflection": (
                "The source highlights the exact risk of sacrificing rebound CAGR and does not "
                "select R20 parameters or establish Alpha."
            ),
            "source_type": "paper",
            "url": R20_CRASH_BRAKE_SOURCE_URL,
        }
    )
    payload["source_evidence_bindings"].append(
        {
            "brief_claim_fingerprint": claim_fingerprint(R20_CRASH_BRAKE_SOURCE_CLAIM),
            "canonical_url": R20_CRASH_BRAKE_SOURCE_URL,
            "claim_fingerprint": claim_fingerprint(R20_CRASH_BRAKE_SOURCE_CLAIM),
            "source_card_claim_id": "r20_crash_brake_drawdown_cagr_tradeoff",
        }
    )
    payload["topic_coverage"].append("crash_brake_drawdown_CAGR_tradeoff")
    write_json(root / ITERATION_DIR / "external-brief.json", payload)


def _write_markdown(root: Path) -> None:
    iteration = root / ITERATION_DIR
    (iteration / "hypotheses.md").write_text(
        "\n".join(
            [
                "# Hypotheses: mom_pit_semantic_theme_r20",
                "",
                "## R20-H1",
                "",
                (
                    "- Hypothesis: R19D01 reached 48.37% CAGR but lost relative to QQQ in F1 and "
                    "F4 specifically during USD100 intervals. Trigger an immediate QQQ pressure "
                    "latch when USD 20-session drawdown reaches the already frozen -20% tail "
                    "boundary, and release only when USD is above SMA100 with positive 20-session "
                    "momentum. Preserve every other route and model rule."
                ),
                (
                    "- Failure mode: D01 or M01 still misses 45% net CAGR, fewer than three folds "
                    "beat QQQ, DSR/PBO remains unacceptable, MDD breaches -65%, turnover exceeds "
                    "12, or the latch removes the F2/F3 USD upside needed for the return target."
                ),
                (
                    "- Measurement: four 252-session chronological OOS folds, 21-session "
                    "purge and embargo, 10/20/40 bps costs, matched D01/TQQQ/QQQ/SPY/BIL "
                    "benchmarks, DSR, CSCV PBO, exact F01 fallback, and forward-only semantic "
                    "ablations."
                ),
                (
                    "- Stop/Pivot criterion: do not tune any R20 threshold after results. Open the "
                    "transfer holdout only for a development-pass price candidate; otherwise "
                    "start a new iteration with one new hypothesis. Semantic stock capital "
                    "remains zero regardless of historical price results."
                ),
                (
                    "- Adaptiveness disclosure: USD and the failing folds are already exposed. "
                    "The -20% boundary is reused from the preregistered R19 path-survival label, "
                    "not searched in R20. A development pass remains adaptive and cannot by "
                    "itself authorize Alpha, Tier 0 capital, or Paper."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (iteration / "search-space.md").write_text(
        "\n".join(
            [
                "# Search Space: mom_pit_semantic_theme_r20",
                "",
                (
                    "Exactly eight preregistered roles are counted: deterministic high-beta "
                    "D01, deterministic semantic D02, Logistic TQQQ-override M01, LightGBM "
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
                "# Decision Record: mom_pit_semantic_theme_r20",
                "",
                "## Preregistration",
                "",
                "- Path: clean SIP price core with forward-only dynamic semantic themes.",
                (
                    "- Decision: authorize only the clean-price D01/M01/M02/F01 historical "
                    "evaluation after the pre-backtest dossier passes."
                ),
                (
                    "- Reason: R19D01 reached 48.37% net CAGR and -64.76% MDD but beat QQQ in "
                    "only 2/4 folds. Exposed route decomposition attributes F1/F4 relative loss "
                    "to USD intervals while F2/F3 require retaining USD. R20 adds only the fixed "
                    "USD pressure latch and preserves recovery, models, scheduling, costs, folds, "
                    "and holdout."
                ),
                (
                    "- Data: bind the immutable 72-request Alpaca SIP "
                    "raw/split/dividend/all snapshot and its passing adjustment-quality report."
                ),
                (
                    "- Model change: M01 is a regularized Logistic classifier for whether the "
                    "fixed TQQQ100 override beats USD100 over 20 opens; M02 is a LightGBM "
                    "10-session path-survival diagnostic. Both use a 21-session embargo and fit "
                    "from scratch in every fold."
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
                "# External Brief: mom_pit_semantic_theme_r20",
                "",
                (
                    "R20 reuses the verified evidence assembled through R19 on time-varying "
                    "product "
                    "networks, customer momentum, attention decay, narrative factors, "
                    "point-in-time SEC/news handling, leveraged-ETF path risk, and opening "
                    "execution. The new empirical question is narrow: can an own-path USD "
                    "drawdown latch improve fold stability without deleting the F2/F3 high-beta "
                    "upside? The trigger reuses R19's frozen -20% tail boundary; no threshold "
                    "sweep is allowed. USD and the weak folds are exposed, so development results "
                    "cannot establish Alpha. AI infrastructure and robotics remain "
                    "examples of current "
                    "event-defined "
                    "themes, not a stock basket replayed backward."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _candidate_manifest(root: Path, specs: dict[str, Any]) -> dict[str, Any]:
    source = _replace_r19(_load_json(root / SOURCE_DIR / "candidate-manifest.json"))
    source["iter_id"] = ITER_ID
    source["spec_hashes"] = {
        path.as_posix(): strategy_content_hash(specs[candidate_id])
        for candidate_id, path in SPEC_PATHS.items()
    }
    contract_names = {
        "data": ("r20_pit_semantic_theme_data_v1", "data-contract.json"),
        "features": ("r20_pit_semantic_theme_features_v1", "feature-contract.json"),
        "labels": ("r20_labels_v1", "label-contract.json"),
        "validation": ("r20_validation_v1", "validation-contract.json"),
        "costs": ("r20_costs_v1", "cost-contract.json"),
        "benchmarks": ("r20_benchmark_family_v1", "benchmark-contract.json"),
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
    by_id["R20D01"].update(
        {
            "role": "deterministic_usd100_core_with_pressure_latch",
            "method": "usd100_core_qqq_stress_recovery_pressure_latch_v1",
            "ablation": "R19D01_without_USD_pressure_latch",
            "fallback": "R19D01",
        }
    )
    by_id["R20M01"].update(
        {
            "role": "fold_local_tqqq_over_usd_override_classifier",
            "method": "logistic_tqqq100_vs_usd100_v1",
            "ablation": "quant_only_logistic_tqqq100_override",
            "fallback": "R20D01",
        }
    )
    by_id["R20M02"].update(
        {
            "role": "fold_local_tail_survival_exit_diagnostic",
            "method": "lightgbm_high_confidence_tail_exit_v1",
            "ablation": "quant_only_lightgbm_tail_exit",
            "fallback": "R20M01_then_R20D01",
        }
    )
    by_id["R20F01"].update(
        {
            "role": "missing_modality_exact_m01_fallback",
            "method": "exact_r20m01_without_semantic_inputs_v1",
        }
    )
    by_id["R20P01"]["placebo_seed"] = 15108
    return source


def _write_feasibility_and_search(root: Path, *, include_knowledge_assessment: bool) -> None:
    iteration = root / ITERATION_DIR
    manifest = _load_json(iteration / "candidate-manifest.json")
    payload = _replace_r19(_load_json(root / SOURCE_DIR / "data-feasibility.json"))
    payload.update(
        {
            "report_type": "pit_semantic_theme_r20_data_feasibility",
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
            "registered_live_collector_implemented; prior-epoch source packets do not count "
            "toward the new R20 epoch"
        ),
        "forward_sec_capability": "collector_implemented_requires_valid_SEC_USER_AGENT",
        "forward_llm_capability": "collector_implemented_requires_valid_OPENAI_API_KEY",
        "semantic_stock_budget": 0.0,
        "adaptive_price_selection": (
            "USD and R19's weak folds were exposed before the pressure latch was specified; "
            "the -20% trigger reuses a prior frozen boundary, development results are not "
            "independent, and transfer holdout access remains locked"
        ),
    }
    payload["path_gates"]["trained_ml"].update(
        {
            "scope": "fold_local_Logistic_override_and_LightGBM_tail_exit_on_clean_SIP_bundle",
            "candidate_ids": ["R20M01", "R20M02"],
        }
    )
    by_candidate = {row["candidate_id"]: row for row in manifest["candidates"]}
    for row in payload["candidate_authorization"]["rows"]:
        candidate = by_candidate[row["candidate_id"]]
        row["candidate_binding_sha256"] = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if row["candidate_id"] == "R20M01":
            row["reason_code"] = (
                "clean_SIP_features_available_for_fold_local_TQQQ100_over_USD100_Logistic"
            )
        elif row["candidate_id"] == "R20M02":
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
        "R20_forward_epoch_not_started",
        "valid_OPENAI_API_KEY_required_for_independent_LLM_factors",
        "valid_SEC_USER_AGENT_required_for_SEC_packets",
        "paper_order_authority_false",
    ]
    write_json(iteration / "data-feasibility.json", payload)

    search = _replace_r19(_load_json(root / SOURCE_DIR / "search-space.json"))
    search.update(
        {
            "iter_id": ITER_ID,
            "objective": (
                "Preserve the complete R19 route and models, add only the fixed USD pressure "
                "latch, and test whether it repairs fold stability without deleting high-beta "
                "upside; semantic themes remain forward-only."
            ),
            "candidate_manifest_path": (ITERATION_DIR / "candidate-manifest.json").as_posix(),
            "candidate_manifest_sha256": _sha256(iteration / "candidate-manifest.json"),
            "data_feasibility_path": (ITERATION_DIR / "data-feasibility.json").as_posix(),
            "data_feasibility_sha256": _sha256(iteration / "data-feasibility.json"),
            "cost_table_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
        }
    )
    d01_spec = load_strategy_spec(root / SPEC_PATHS["R20D01"])
    search["source_spec_path"] = SPEC_PATHS["R20D01"].as_posix()
    search["spec_hash"] = strategy_content_hash(d01_spec)
    trained = next(row for row in search["paths"] if row["name"] == "trained_ml")
    deterministic = next(row for row in search["paths"] if row["name"] == "deterministic_price")
    deterministic["parameters"].update(
        {
            "candidate_ids": ["R20D01"],
            "route_label": "pit_semantic_theme_r20:D01:usd_pressure_latch_v1",
            "default_risk_on_target": "USD100",
            "stress_target": "QQQ100",
            "stress_recovery": _stress_recovery_contract(),
            "usd_pressure_override": _usd_pressure_contract(),
            "review_every_sessions": 5,
            "minimum_hold_sessions": 10,
            "parameter_search": False,
        }
    )
    trained["parameters"].update(
        {
            "candidate_ids": ["R20M01", "R20M02"],
            "model_family": "Logistic_TQQQ100_over_USD100_plus_LightGBM_QQQ_tail_exit",
            "fold_count": 4,
            "fold_oos_sessions": 252,
            "hyperparameter_search": False,
            "m01_probability_threshold": 0.60,
            "m02_tail_exit_survival_threshold": 0.20,
            "retrain_every_sessions": 20,
            "embargo_sessions": 21,
            "purge_sessions": 21,
            "label_horizon_sessions": {"R20M01": 20, "R20M02": 10},
        }
    )
    placebo = next(row for row in search["paths"] if row["name"] == "placebo")
    placebo["parameters"]["permutation_seed"] = 15108
    search["cumulative_trial_count"] = 8110
    search["adaptive_selection_disclosure"] = (
        "USD and the F1/F4 failure attribution are exposed; the pressure threshold is inherited "
        "rather than searched, and only a separately locked one-time transfer-holdout evaluation "
        "may provide independent selection evidence"
    )
    search["trial_ledger_paths"] = []
    search["evaluation_report_paths"] = []
    write_json(iteration / "search-space.json", search)


def _replace_r19(value: Any) -> Any:
    if isinstance(value, dict):
        return {_replace_text(str(key)): _replace_r19(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_r19(item) for item in value]
    if isinstance(value, str):
        return _replace_text(value)
    return value


def _replace_text(value: str) -> str:
    return value.replace("R19", "R20").replace("r19", "r20")


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
