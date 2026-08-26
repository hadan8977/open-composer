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

SOURCE_ITER = "mom_pit_semantic_theme_r11"
ITER_ID = "mom_pit_semantic_theme_r12"
SOURCE_DIR = Path("reports/research/iterations") / SOURCE_ITER
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SNAPSHOT_PATH = Path(
    "data/research/alpaca_pit_price_adjustment_repair_20260804/snapshot-manifest.json"
)
QUALITY_PATH = Path("reports/research/data-quality/r11-price-repair-20260804-quality.json")
SOURCE_CARD_PATH = Path("reports/harness/source_cards/us_pit_semantic_theme_r12.jsonl")
SOURCE_SOURCE_CARD_PATH = Path("reports/harness/source_cards/us_pit_semantic_theme_r11.jsonl")
PROMPT_PATH = Path("prompts/pit_semantic_theme_r12_factor_v1.txt")
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r12_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R12D01", "d01"),
        ("R12D02", "d02"),
        ("R12M01", "m01"),
        ("R12M02", "m02"),
        ("R12L01", "l01"),
        ("R12C01", "c01"),
        ("R12F01", "f01"),
        ("R12P01", "p01"),
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
        raise ValueError("R12 preparation requires a passing price-adjustment quality report")
    if snapshot.get("request_count") != 72:
        raise ValueError("R12 snapshot must bind 18 symbols x four adjustment modes")

    generated_at = datetime.now(UTC).isoformat()
    _write_source_cards(base)
    specs = _write_specs(base)
    _write_prompt(base)
    for name in CONTRACT_FILES:
        payload = _replace_r11(_load_json(base / SOURCE_DIR / name))
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
            raise ValueError(f"R12 finalization prerequisite is missing: {name}")
    assessment = _load_json(iteration / "knowledge-assessment.json")
    if assessment.get("status") != "ok":
        raise ValueError("R12 knowledge assessment must pass before finalization")
    _write_feasibility_and_search(base, include_knowledge_assessment=True)


def _write_specs(root: Path) -> dict[str, Any]:
    source_specs = {
        candidate_id.replace("R12", "R11", 1): yaml.safe_load(
            (
                root / str(path).replace("us_pit_semantic_theme_r12", "us_pit_semantic_theme_r11")
            ).read_text(encoding="utf-8")
        )
        for candidate_id, path in SPEC_PATHS.items()
    }
    generated: dict[str, dict[str, Any]] = {}
    for candidate_id in SPEC_PATHS:
        source_id = candidate_id.replace("R12", "R11", 1)
        raw = _replace_r11(source_specs[source_id])
        generated[candidate_id] = raw

    m01 = generated["R12M01"]
    m01["description"] = (
        "Fold-local standardized Ridge ETF route ranker on the clean immutable SIP bundle."
    )
    m01["model"]["kind"] = "ridge_regressor"
    m01["model"]["training"]["seed"] = 12101
    m01["model"]["hyperparameters"] = {"alpha": 1.0, "fit_intercept": True}
    m01["model"]["baseline"] = "none"
    m01["notes"].update(
        {
            "candidate_role": "fold_local_ridge_etf_route_ranker",
            "method": "standardized_ridge_route_ranker_v1",
        }
    )

    m02 = json.loads(json.dumps(m01))
    m02["name"] = "us_pit_semantic_theme_r12_m02"
    m02["description"] = (
        "Matched fold-local LightGBM ETF route ranker; complexity is admitted only "
        "with stable lift over Ridge."
    )
    m02["portfolio"]["selected_route_label"] = "pit_semantic_theme_r12:M02:lightgbm_route_v1"
    m02["model"]["kind"] = "lightgbm_regressor"
    m02["model"]["training"]["seed"] = 12102
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
            "candidate_id": "R12M02",
            "candidate_role": "fold_local_lightgbm_complexity_challenger",
            "method": "matched_lightgbm_route_ranker_v1",
            "fallback_candidate_id": "R12M01_then_R12D01",
        }
    )
    m02["research_design"]["parameter_space"]["candidate_id"] = ["R12M02"]
    generated["R12M02"] = m02

    f01 = json.loads(json.dumps(m01))
    f01["name"] = "us_pit_semantic_theme_r12_f01"
    f01["description"] = "Exact missing-semantic fallback identity control for R12M01."
    f01["portfolio"]["selected_route_label"] = "pit_semantic_theme_r12:F01:exact_m01_fallback"
    f01["notes"].update(
        {
            "candidate_id": "R12F01",
            "candidate_role": "missing_modality_exact_m01_fallback",
            "method": "exact_r12m01_without_semantic_inputs_v1",
            "fallback_candidate_id": "R12M01_then_R12D01",
        }
    )
    f01["research_design"]["parameter_space"]["candidate_id"] = ["R12F01"]
    generated["R12F01"] = f01

    for candidate_id in ("R12C01", "R12P01"):
        generated[candidate_id]["model"] = json.loads(json.dumps(m01["model"]))

    for candidate_id, raw in generated.items():
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
            raw["execution_policy"]["policy_id"] = "r12_protected_opg_v1"
        path = root / SPEC_PATHS[candidate_id]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(raw, sort_keys=False, width=110), encoding="utf-8")

    return {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }


def _write_prompt(root: Path) -> None:
    source = root / "prompts/pit_semantic_theme_r11_factor_v1.txt"
    target = root / PROMPT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_replace_text(source.read_text(encoding="utf-8")), encoding="utf-8")


def _write_source_cards(root: Path) -> None:
    source = root / SOURCE_SOURCE_CARD_PATH
    target = root / SOURCE_CARD_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    retained = _replace_text(source.read_text(encoding="utf-8")).rstrip("\n")
    ridge_card = {
        "iteration_id": ITER_ID,
        "verification_status": "source_verified",
        "verified_at": "2026-08-04T20:47:41Z",
        "verification_method": "arxiv_official_api_metadata_and_abstract",
        "claim_id": "r12_ridge_finite_sample_bias_variance",
        "claim": (
            "A recent finite-sample analysis describes ridge regression as trading bias for "
            "variance to reduce estimation and prediction error and studies risk-based "
            "regularization under heteroskedasticity and autocorrelation in a low-dimensional "
            "setting."
        ),
        "source_url": "https://arxiv.org/abs/2608.02539",
        "source_type": "paper",
        "accessed_at": "2026-08-04",
        "applies_to": ["ridge_regression", "small_sample_model_risk", "R12M01"],
        "impact_on_spec": (
            "Preregister standardized Ridge as the simple trained candidate and require "
            "matched LightGBM to justify its added complexity out of sample."
        ),
        "limitations": (
            "This is a new arXiv working paper, not asset-return evidence; it does not choose "
            "alpha, validate R12, or justify changing alpha after outcomes are observed."
        ),
    }
    target.write_text(
        retained + "\n" + json.dumps(ridge_card, separators=(",", ":")) + "\n",
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
                "allowed_candidate_ids": ["R12D01", "R12M01", "R12M02", "R12F01"],
                "limitations": [
                    "historical_prices_are_globally_exposed_development_data",
                    "provider_all_is_not_local_corporate_action_lineage",
                    "no_historical_stock_membership_claim",
                ],
            }
        )
    elif name == "feature-contract.json":
        payload["single_hypothesis"] = (
            "on a clean fixed price bundle, a standardized linear ranker is more stable than "
            "a tree ensemble; semantic themes remain forward-only"
        )
        payload["semantic_features"]["prompt_path"] = PROMPT_PATH.as_posix()
        payload["capital"]["fallbacks"]["R12M02"] = "R12M01_then_R12D01"
    elif name == "label-contract.json":
        payload["labels"]["R12M02"] = {
            "type": "net_forward_route_return",
            "horizon_sessions": 5,
            "cost_bps": 20.0,
            "fit_scope": "fold_train_only",
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
        payload["pbo"]["selection_candidate_ids"] = ["R12D01", "R12M01", "R12M02"]
        payload["model_gates"] = {
            "R12M01": (
                "Ridge must improve tail efficiency or CAGR over D01 in at least three OOS folds"
            ),
            "R12M02": (
                "LightGBM complexity is admitted only with positive net lift over Ridge in at "
                "least three folds and no worse drawdown"
            ),
            "R12F01": "target and prediction identity with M01 for every matched session",
        }
        payload["semantic_gates"]["stock_budget_during_R12"] = 0.0
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
                "prior_effective_trial_count": 8038,
                "effective_trial_count": 8046,
                "prior_trial_evidence": {
                    "path": (
                        "reports/research/iterations/mom_pit_semantic_theme_r11/"
                        "data-quality-invalidation.json"
                    ),
                    "status": "invalidated_price_adjustment_contamination",
                },
            }
        )
    elif name == "universe-contract.json":
        payload["contract_id"] = "r12_dynamic_universe_v1"
        payload["execution_universe_role"] = (
            "fixed_ETF_risk_and_execution_core_only_not_dynamic_theme_membership"
        )
    elif name == "modality-role-matrix.json":
        for row in payload["roles"]:
            if row["role"] == "risk_prediction":
                row.update(
                    {
                        "modalities": ["deterministic_route_state"],
                        "candidates": ["R12D01"],
                        "method": "no_trained_risk_model_in_this_single_hypothesis_round",
                        "fallback": "R12D01",
                    }
                )
        for row in payload["required_ablations"]:
            if row["candidate"] == "R12M01":
                row["ablation"] = "quant_only_ridge"
            elif row["candidate"] == "R12M02":
                row["ablation"] = "quant_only_lightgbm_complexity_challenger"
    elif name == "model-reuse-decision.json":
        payload["round_decision"] = {
            "action": "fit_from_scratch",
            "reason": (
                "R11 estimator outcomes are invalidated by price-adjustment contamination; "
                "R12 binds a new SIP snapshot and performs no warm start"
            ),
            "source_iteration": SOURCE_ITER,
            "source_status": "invalidated_data_quality",
            "snapshot_sha256": _sha256(root / SNAPSHOT_PATH),
            "feature_contract_status": "new_epoch",
            "validation_contract_status": "new_epoch",
        }
    elif name == "knowledge-scout-queries.json":
        payload["scout_network_status"] = {
            "status": "reuse_current_verified_evidence",
            "observed_at": "2026-08-04",
            "action": (
                "reuse verified dynamic-theme claims; R12 changes only price provenance and "
                "the Ridge-versus-LightGBM model role"
            ),
        }
        payload["curated_candidates"].append(
            {
                "discovery_id": "r12_ridge_finite_sample_bias_variance",
                "url": "https://arxiv.org/abs/2608.02539",
                "title": (
                    "A Simple Approximation to the Distribution of the Ridge Regression Estimator"
                ),
                "summary": (
                    "Finite-sample Ridge trades bias and variance; the paper develops "
                    "risk-based regularization under heteroskedasticity and autocorrelation."
                ),
                "published_at": "2026-08-03T17:28:17Z",
                "authors": [
                    "Jose Luis Montiel Olea",
                    "Ryan Strong",
                    "Amilcar Velez",
                    "Zhuoheng Xu",
                    "Haomin Yu",
                ],
                "source_type": "paper",
                "topics": ["ridge regression", "finite-sample risk", "bias variance"],
            }
        )


def _write_external_brief(root: Path, specs: dict[str, Any], generated_at: str) -> None:
    payload = _replace_r11(_load_json(root / SOURCE_DIR / "external-brief.json"))
    payload.update(
        {
            "iter_id": ITER_ID,
            "strategy_name": specs["R12D01"].name,
            "objective": (
                "On a freshly retrieved and independently reconciled Alpaca SIP price bundle, "
                "test whether a simple fold-local Ridge ranker is more stable than LightGBM "
                "while retaining a high-beta deterministic core; collect changing semantic "
                "themes only forward from source-bound news and SEC packets."
            ),
            "source_spec_path": SPEC_PATHS["R12D01"].as_posix(),
            "spec_hash": strategy_content_hash(specs["R12D01"]),
            "current_source_card_paths": [SOURCE_CARD_PATH.as_posix()],
            "hypothesis_links": ["R12-H1"],
            "generated_at": generated_at,
        }
    )
    revisions = {row["candidate_id"]: row for row in payload["candidate_matrix_revisions"]}
    revisions["R12M01"]["revision"] = (
        "first-class standardized Ridge ranker on a clean immutable SIP snapshot"
    )
    revisions["R12M02"]["revision"] = (
        "matched LightGBM ranker admitted only if complexity adds stable OOS lift"
    )
    claim = (
        "A recent finite-sample analysis describes ridge regression as trading bias for "
        "variance to reduce estimation and prediction error and studies risk-based "
        "regularization under heteroskedasticity and autocorrelation in a low-dimensional "
        "setting."
    )
    fingerprint = claim_fingerprint(claim)
    payload["sources"].append(
        {
            "url": "https://arxiv.org/abs/2608.02539",
            "published_or_updated_at": "2026-08-03",
            "source_type": "paper",
            "credibility": "recent arXiv econometrics working paper metadata and abstract",
            "core_claim": claim,
            "project_applicability": (
                "Use standardized Ridge as the simple preregistered model and require a "
                "matched nonlinear challenger to demonstrate stable OOS lift."
            ),
            "reflection": (
                "The paper is not about asset returns and supplies no R12 performance evidence."
            ),
        }
    )
    payload["source_evidence_bindings"].append(
        {
            "canonical_url": "https://arxiv.org/abs/2608.02539",
            "source_card_claim_id": "r12_ridge_finite_sample_bias_variance",
            "claim_fingerprint": fingerprint,
            "brief_claim_fingerprint": fingerprint,
        }
    )
    payload["topic_coverage"].append("ridge_finite_sample_bias_variance")
    write_json(root / ITERATION_DIR / "external-brief.json", payload)


def _write_markdown(root: Path) -> None:
    iteration = root / ITERATION_DIR
    (iteration / "hypotheses.md").write_text(
        "\n".join(
            [
                "# Hypotheses: mom_pit_semantic_theme_r12",
                "",
                "## R12-H1",
                "",
                (
                    "- Hypothesis: after eliminating mixed-vintage adjustment contamination, "
                    "a standardized fold-local Ridge ranker can retain more stable high-beta "
                    "route performance than matched LightGBM; decision-time semantic events "
                    "may define changing themes only in forward observation."
                ),
                (
                    "- Failure mode: both trained rankers underperform the deterministic D01 "
                    "route or LightGBM lift is fold-unstable; semantic packets are absent, "
                    "stale, or cannot prove changing membership."
                ),
                (
                    "- Measurement: four 252-session chronological OOS folds, 10-session "
                    "purge and embargo, 10/20/40 bps costs, matched D01/TQQQ/QQQ/SPY/BIL "
                    "benchmarks, DSR, CSCV PBO, exact F01 fallback, and forward-only semantic "
                    "ablations."
                ),
                (
                    "- Stop/Pivot criterion: stop the trained path if neither model clears "
                    "preregistered family gates; retain D01 only if it independently clears. "
                    "Do not open the transfer holdout or allocate semantic stock capital after "
                    "a development failure."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    (iteration / "search-space.md").write_text(
        "\n".join(
            [
                "# Search Space: mom_pit_semantic_theme_r12",
                "",
                (
                    "Exactly eight preregistered roles are counted: deterministic high-beta "
                    "D01, deterministic semantic D02, Ridge M01, matched LightGBM M02, "
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
                "# Decision Record: mom_pit_semantic_theme_r12",
                "",
                "## Preregistration",
                "",
                "- Path: clean SIP price core with forward-only dynamic semantic themes.",
                (
                    "- Decision: authorize only the clean-price D01/M01/M02/F01 historical "
                    "evaluation after the pre-backtest dossier passes."
                ),
                (
                    "- Reason: R11 price outcomes were invalidated by mixed-vintage adjustment "
                    "contamination; R12 binds a fresh independently retrieved bundle."
                ),
                (
                    "- Data: bind the immutable 72-request Alpaca SIP "
                    "raw/split/dividend/all snapshot and its passing adjustment-quality report."
                ),
                (
                    "- Model change: make Ridge the simple primary trained ranker and LightGBM "
                    "the matched complexity challenger; fit both from scratch in every fold."
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
                "# External Brief: mom_pit_semantic_theme_r12",
                "",
                (
                    "R12 reuses the verified evidence assembled for R11 on time-varying product "
                    "networks, customer momentum, attention decay, narrative factors, "
                    "point-in-time SEC/news handling, leveraged-ETF path risk, and opening "
                    "execution. The new empirical question is deliberately narrow: after "
                    "replacing a contaminated mixed-vintage cache with a fresh independently "
                    "retrieved SIP adjustment bundle, does standardized Ridge generalize more "
                    "reliably than matched LightGBM? No new historical semantic dataset is "
                    "claimed, and no current AI or robotics membership is replayed backward."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _candidate_manifest(root: Path, specs: dict[str, Any]) -> dict[str, Any]:
    source = _replace_r11(_load_json(root / SOURCE_DIR / "candidate-manifest.json"))
    source["iter_id"] = ITER_ID
    source["spec_hashes"] = {
        path.as_posix(): strategy_content_hash(specs[candidate_id])
        for candidate_id, path in SPEC_PATHS.items()
    }
    contract_names = {
        "data": ("r12_pit_semantic_theme_data_v1", "data-contract.json"),
        "features": ("r12_pit_semantic_theme_features_v1", "feature-contract.json"),
        "labels": ("r12_labels_v1", "label-contract.json"),
        "validation": ("r12_validation_v1", "validation-contract.json"),
        "costs": ("r12_costs_v1", "cost-contract.json"),
        "benchmarks": ("r12_benchmark_family_v1", "benchmark-contract.json"),
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
    by_id["R12M01"].update(
        {
            "role": "fold_local_ridge_etf_route_ranker",
            "method": "standardized_ridge_route_ranker_v1",
            "ablation": "quant_only_ridge",
        }
    )
    by_id["R12M02"].update(
        {
            "role": "fold_local_lightgbm_complexity_challenger",
            "method": "matched_lightgbm_route_ranker_v1",
            "ablation": "quant_only_lightgbm_complexity_challenger",
            "fallback": "R12M01_then_R12D01",
        }
    )
    by_id["R12F01"].update(
        {
            "role": "missing_modality_exact_m01_fallback",
            "method": "exact_r12m01_without_semantic_inputs_v1",
        }
    )
    return source


def _write_feasibility_and_search(root: Path, *, include_knowledge_assessment: bool) -> None:
    iteration = root / ITERATION_DIR
    manifest = _load_json(iteration / "candidate-manifest.json")
    payload = _replace_r11(_load_json(root / SOURCE_DIR / "data-feasibility.json"))
    payload.update(
        {
            "report_type": "pit_semantic_theme_r12_data_feasibility",
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
        "forward_news_capability": "registered_collector_not_yet_implemented",
        "forward_sec_capability": "registered_collector_requires_SEC_USER_AGENT",
        "semantic_stock_budget": 0.0,
    }
    payload["path_gates"]["trained_ml"].update(
        {
            "scope": "matched_fold_local_Ridge_and_LightGBM_on_clean_SIP_bundle",
            "candidate_ids": ["R12M01", "R12M02"],
        }
    )
    by_candidate = {row["candidate_id"]: row for row in manifest["candidates"]}
    for row in payload["candidate_authorization"]["rows"]:
        candidate = by_candidate[row["candidate_id"]]
        row["candidate_binding_sha256"] = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if row["candidate_id"] == "R12M01":
            row["reason_code"] = "clean_SIP_price_features_available_for_fold_local_Ridge"
        elif row["candidate_id"] == "R12M02":
            row["reason_code"] = (
                "clean_SIP_price_features_available_for_matched_LightGBM_challenger"
            )
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
        "news_collector_not_yet_implemented",
        "paper_order_authority_false",
    ]
    write_json(iteration / "data-feasibility.json", payload)

    search = _replace_r11(_load_json(root / SOURCE_DIR / "search-space.json"))
    search.update(
        {
            "iter_id": ITER_ID,
            "candidate_manifest_path": (ITERATION_DIR / "candidate-manifest.json").as_posix(),
            "candidate_manifest_sha256": _sha256(iteration / "candidate-manifest.json"),
            "data_feasibility_path": (ITERATION_DIR / "data-feasibility.json").as_posix(),
            "data_feasibility_sha256": _sha256(iteration / "data-feasibility.json"),
            "cost_table_path": (ITERATION_DIR / "cost-contract.json").as_posix(),
        }
    )
    d01_spec = load_strategy_spec(root / SPEC_PATHS["R12D01"])
    search["source_spec_path"] = SPEC_PATHS["R12D01"].as_posix()
    search["spec_hash"] = strategy_content_hash(d01_spec)
    trained = next(row for row in search["paths"] if row["name"] == "trained_ml")
    trained["parameters"].update(
        {
            "candidate_ids": ["R12M01", "R12M02"],
            "model_family": "standardized_Ridge_vs_matched_LightGBM",
            "fold_count": 4,
            "fold_oos_sessions": 252,
            "hyperparameter_search": False,
        }
    )
    write_json(iteration / "search-space.json", search)


def _replace_r11(value: Any) -> Any:
    if isinstance(value, dict):
        return {_replace_text(str(key)): _replace_r11(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_r11(item) for item in value]
    if isinstance(value, str):
        return _replace_text(value)
    return value


def _replace_text(value: str) -> str:
    return value.replace("R11", "R12").replace("r11", "r12")


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
