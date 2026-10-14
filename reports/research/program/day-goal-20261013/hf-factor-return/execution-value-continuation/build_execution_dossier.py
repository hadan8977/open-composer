"""Canonical native wiring for the approved package; pending review stays pending."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from open_composer.research.iteration_dossier import candidate_authorization_binding_sha256
from open_composer.research.knowledge_memory import canonical_source_url, claim_fingerprint

ROOT = Path.cwd()
P = Path(__file__).resolve().parent
OLD = P.parent
ITER_ID = "t20261014_hf_execution_value"
D = ROOT / "reports/research/iterations" / ITER_ID
OWNER = "66ebc2b7-c533-4992-82fe-cece4f3e2b12"


def bind(path):
    body = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


at = datetime.now(UTC).isoformat()
if (D / "external-brief.json").is_file():
    at = json.loads((D / "external-brief.json").read_text())["registered_at"]
review = json.loads((P / "independent-plan-review-root-v1.json").read_text())
assert review["verdict"] == "approve_deep_plan"
assert review["author_agent_id"] == OWNER != review["reviewer_agent_id"]
for row in review["bindings_verified"]:
    if row["path"].endswith(("/scientific-plan.json", "/scientific-plan-v1.md")):
        assert bind(ROOT / row["path"]) == row
D.mkdir(exist_ok=True)
save(
    P / "native-plan-review-binding.json",
    {
        "verdict": review["verdict"],
        "author": OWNER,
        "reviewer": review["reviewer_agent_id"],
        "bindings": [
            r
            for r in review["bindings_verified"]
            if r["path"].endswith(("/scientific-plan.json", "/scientific-plan-v1.md"))
        ],
        "actual_original_review": bind(P / "independent-plan-review-root-v1.json"),
        "scope": "Field-name adapter only; not a new review, signature or economic admission",
    },
)
input_manifest = json.loads((P / "execution-input-manifest.json").read_text())
plan = json.loads((P / "scientific-plan.json").read_text())
proposal = json.loads((P / "candidate-manifest-proposed.json").read_text())
search_definition = {
    "total_candidate_budget": len(proposal["candidates"]),
    "paths": [
        {
            "name": policy,
            "candidate_count": 20,
            "hypothesis_refs": ["H1", "H2", "H3"],
            "parameters": {
                "fixed_ids": [
                    r["candidate_id"]
                    for r in proposal["candidates"]
                    if r["policy"]["policy_id"] == policy
                ]
            },
            "benchmark_family": ["ZERO", "MKT", "SPY", "CASH", "BIL", "causal_risk_control"],
        }
        for policy in ["CONT_H1_SLOW", "DP_H16_FAST", "DP_H16_SLOW"]
    ],
}
scope_path = P / "fixed-component-comparison.json"
prior_scope = json.loads(scope_path.read_text()) if scope_path.is_file() else {}
save(
    P / "fixed-component-comparison.json",
    {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "parent_task": plan["parent_task"],
        "scientific_plan": bind(P / "scientific-plan.json"),
        "approved_inventory": plan["candidate_manifest"],
        "validation": plan["validation"],
        "candidate_ids": [r["candidate_id"] for r in proposal["candidates"]],
        "operations": ["compare_all_fixed_candidates"],
        "search_definition": search_definition,
        **(
            {"canonical_wiring": prior_scope["canonical_wiring"]}
            if "canonical_wiring" in prior_scope
            else {}
        ),
        "actual_input_manifest": bind(P / "execution-input-manifest.json"),
        "actual_input_inventory": input_manifest["actual_financial_read_inputs"],
        "inherited_source_inputs": input_manifest["original_source_inputs"],
        "inherited_source_acceptance": input_manifest["inherited_source_acceptance"],
        "inherited_full_result_acceptance": input_manifest["inherited_full_result_acceptance"],
        **{
            key: False
            for key in [
                "new_family_discovery",
                "adaptive_selection",
                "candidate_pruning",
                "parameter_optimization",
                "new_model_fits",
                "new_model_selection",
                "promotion_eligible",
            ]
        },
    },
)
files = [
    bind(P / name)
    for name in [
        "hf_execution_policy.py",
        "run_execution_accounts.py",
        "prepare_execution_inputs.py",
        "test_hf_execution_policy.py",
        "test_implementation_revisions.py",
        "check_revised_input_clocks.py",
        "build_execution_dossier.py",
        "run_native_preparation.py",
        "implementation-contract-v1.md",
        "execution-input-manifest.json",
        "execution-input-QA.json",
        "revision-input-clock-QA.json",
        "fixed-component-comparison.json",
    ]
]
files.extend([bind(OLD / "hf_accounts.py"), bind(OLD / "hf_native_policy_batch.py")])
files.extend(input_manifest["actual_financial_read_inputs"])
unique = {row["path"]: row for row in files}
save(
    P / "implementation-manifest.json",
    {
        "schema_version": 3,
        "task_id": "HF-EXECUTION-VALUE-CONTINUATION-20261014",
        "iter_id": ITER_ID,
        "author": OWNER,
        "files": list(unique.values()),
        "scientific_plan": bind(P / "scientific-plan.json"),
        "implementation_definition": bind(P / "implementation-contract-v1.md"),
        "actual_input_manifest": bind(P / "execution-input-manifest.json"),
        "fixed_component_comparison": bind(P / "fixed-component-comparison.json"),
        "real_market_runs": 0,
        "real_model_fits_or_inference": 0,
        "test_receipt": bind(P / "revision-tests-01.xml"),
        "prior_test_receipt": bind(P / "implementation-tests-03.xml"),
        "implementation_independent_acceptance": "pending",
        "financial_launch_admitted": False,
        "I1_I4_resolved_by_concrete_code_and_synthetic_evidence": True,
    },
)
cards_path = ROOT / "reports/harness/source_cards/hf_execution_value_20261014.jsonl"
cards = [json.loads(line) for line in (P / "policy-source-cards.jsonl").read_text().splitlines()]
for card in cards:
    card.update(
        iteration_id=ITER_ID,
        verified_at=at,
        verification_method="Inherited fetched snapshot, author read and Root plan review",
    )
cards_path.write_text("".join(json.dumps(card, ensure_ascii=False) + "\n" for card in cards))
direction = json.loads((P / "direction-review.json").read_text())
sources, bindings = [], []
for source in direction["sources"]:
    row = dict(source)
    row["source_card_path"] = str(cards_path.relative_to(ROOT))
    row["core_claim"] = row["claim"]
    row["credibility"] = "Fetched original source retained; Root independently reviewed the limits"
    row["reflection"] = (
        "L1 current-vintage component research; no unseen or execution certification"
    )
    row["project_applicability"] = "Fixed approved policies without refits or lower costs"
    sources.append(row)
    bindings.append(
        {
            "claim_id": row["claim_id"],
            "source_card_claim_id": row["claim_id"],
            "source_card_path": row["source_card_path"],
            "snapshot_path": row["snapshot_path"],
            "snapshot_sha256": row["sha256"],
            "source_url": row["url"],
            "canonical_url": canonical_source_url(row["url"]),
            "claim_fingerprint": claim_fingerprint(row["claim"]),
            "brief_claim_fingerprint": claim_fingerprint(row["core_claim"]),
        }
    )
direction["sources"], direction["source_evidence_bindings"] = sources, bindings
direction["native_wiring_from_approved_source_definition"] = bind(P / "direction-review.json")
save(D / "direction-review.json", direction)
identity = {
    "schema_version": 3,
    "iter_id": ITER_ID,
    "research_role": "market_component_method",
    "strategy_name": "conditional_hf_execution_value",
    "source_spec_path": None,
    "spec_hash": None,
}
external = {
    **identity,
    "registered_at": at,
    "objective": direction["objective"],
    "mechanism_family": "broad_factor_intraday_forecasting",
    "mechanism_description": "Approved complete existing-HF linear-cost L1 execution continuation",
    "current_source_card_paths": [str(cards_path.relative_to(ROOT))],
    "source_evidence_bindings": bindings,
    "sources": sources,
    "candidate_matrix_revisions": [
        "Approved48 fixed information/anchor configurations and12 controls"
    ],
    "topic_coverage": [
        "source_fidelity",
        "clock",
        "execution",
        "cost",
        "funding",
        "risk",
        "lifetime",
        "matched_information",
        "power",
    ],
    "difference_from_existing": [
        "Continuous actual shares, no mandatory open liquidation or nightly risk increase",
        "Full original fees and cash; explicit decay APP rather than source5minute new training",
    ],
    "family_quota_exception": {
        "signed_by": "Root/Astra lead: actual independent-plan-review-root-v1",
        "signed_at": review["reviewed_at_utc"][:10],
        "reason": "Root independently approved exactly60 fixed identities in the same parent "
        "continuation, preserving prior family exposure and the same cumulative pool.",
        "actual_authority": bind(P / "independent-plan-review-root-v1.json"),
        "derived_consumer_scope_record_not_new_author_signature": True,
    },
}
save(D / "external-brief.json", external)
save(
    D / "knowledge-scout-queries.json",
    {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "queries": [],
        "curated_candidates": [
            {
                "title": row["claim_id"],
                "url": row["url"],
                "summary": row["claim"],
                "source_type": "paper",
                "topics": ["linear_cost", "clock", "decay", "negative_evidence"],
            }
            for row in sources
        ],
        "max_results_per_query": 3,
        "reuse_reason": "Actual fresh originals and negative evidence; zero new source requests",
    },
)
plan = json.loads((P / "scientific-plan.json").read_text())
save(
    D / "modality-role-matrix.json",
    {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "roles": [{"role": key, "definition": value} for key, value in plan["role_matrix"].items()],
    },
)
proposal = json.loads((P / "candidate-manifest-proposed.json").read_text())
ids = [row["candidate_id"] for row in proposal["candidates"]]
implementation_review_path = P / "independent-implementation-review.json"
implementation_review = (
    bind(implementation_review_path)
    if implementation_review_path.is_file()
    else {"path": str(implementation_review_path.relative_to(ROOT)), "sha256": ""}
)
definition = {
    "schema_version": 1,
    "research_role": "market_component_method",
    "iter_id": ITER_ID,
    "candidate_manifest_path": str((D / "candidate-manifest.json").relative_to(ROOT)),
    "data_feasibility_path": str((D / "data-feasibility.json").relative_to(ROOT)),
    "time_axis_kind": "market_timestamp",
    "claim_scope": "conditional_cohort",
    "real_market_claim": True,
    "candidate_ids": ids,
    "scientific_plan": bind(P / "scientific-plan.json"),
    "independent_plan_review": bind(P / "native-plan-review-binding.json"),
    "implementation_manifest": bind(P / "implementation-manifest.json"),
    "independent_implementation_review": implementation_review,
    **{
        field: False
        for field in [
            "promotion_eligible",
            "paper_trading_allowed",
            "broker_activity_allowed",
            "pit_universe_certified",
            "deployment_readiness_claim",
        ]
    },
}
save(D / "method-definition.json", definition)
contract_values = {
    "data": {
        "actual_inputs": bind(P / "execution-input-manifest.json"),
        "source_and_fills_conditional": True,
    },
    "features": {
        "existing_predictions_only": proposal["input_bindings"],
        "streams": plan["information_streams"],
        "new_inference": 0,
    },
    "labels": {
        "old_original_label_only": "FF log15minute Cts/All unchanged",
        "execution": "L1 label ends at execution; same-session post-delay intervals only",
        "outcome_mask_does_not_control_current_signal": True,
    },
    "validation": plan["validation"],
    "costs": {
        "primary_each_side": 0.002,
        "stress_each_side": 0.004,
        "actual_share_cash_formulas": bind(P / "implementation-contract-v1.md"),
        "no_unsettled_funding_or_planning_cash": True,
    },
    "benchmarks": {
        "same_policy": ["PLS_IDX_MKT", "ZERO", "STALE", "INV", "NEG_PLS", "AR26"],
        "physical": ["SPY_buyhold", "CASH", "BIL_known_CIL_limits"],
        "causal_exposure_control": True,
    },
}
contracts = {}
for group, value in contract_values.items():
    path = D / f"{group}-contract.json"
    save(path, {"schema_version": 1, "iter_id": ITER_ID, "definition": value})
    contracts[group] = {"conditional_hf_execution_value": bind(path)}
candidates = []
for row in proposal["candidates"]:
    candidates.append(
        {
            **row,
            "path": row["policy"]["policy_id"],
            "role": "nonpromotable_L1_cash_application",
            "method": json.dumps(row["policy"], sort_keys=True),
            "ablation": row["stream"],
            "fallback": "I3 hold or absolute-share reduction only",
            "mechanism_family": external["mechanism_family"],
            "mechanism": "Existing HF return information under fixed full-cost continuation",
            "scale_curve_point": False,
            "method_definition_path": str((D / "method-definition.json").relative_to(ROOT)),
            "method_definition_sha256": bind(D / "method-definition.json")["sha256"],
            **{
                key: "conditional_hf_execution_value"
                for key in [
                    "data_contract",
                    "feature_contract",
                    "label_contract",
                    "validation_contract",
                    "cost_contract",
                    "benchmark_contract",
                ]
            },
        }
    )
save(
    D / "candidate-manifest.json",
    {
        **identity,
        "candidate_count": 60,
        "candidates": candidates,
        "manifest_type": "generic_candidate_family_v1",
        "generated_before_backtest": True,
        "generated_at": at,
        "spec_hashes": {},
        "contracts": contracts,
        "approved_candidate_proposal": bind(P / "candidate-manifest-proposed.json"),
        "new_financial_trials": 0,
    },
)
references = {
    "current_input_QA": bind(P / "execution-input-QA.json"),
    "approved_plan": bind(P / "independent-plan-review-root-v1.json"),
    "original_source_acceptance": input_manifest["inherited_source_acceptance"],
    "original_price_acceptance": input_manifest["inherited_price_bridge_acceptance"],
    "implementation_definition": bind(P / "implementation-contract-v1.md"),
}
save(
    D / "data-feasibility.json",
    {
        "schema_version": 1,
        "report_type": "conditional_small_input_preparation",
        "iter_id": ITER_ID,
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "historical_evaluation_authorized": True,
        "financial_launch_admitted": False,
        "authorization_scope": (
            "Approved scientific input use; implementation/runtime still pending"
        ),
        "path_gates": {
            policy: {
                "action": "evaluate",
                "historical_evaluation_go": True,
                "candidate_ids": [r["candidate_id"] for r in candidates if r["path"] == policy],
            }
            for policy in ["CONT_H1_SLOW", "DP_H16_FAST", "DP_H16_SLOW"]
        },
        "candidate_accounting": {
            "frozen_candidate_count": 60,
            "evaluation_authorized_count": 60,
            "dependency_skipped_count": 0,
            "unresolved_count": 0,
            "balanced": True,
        },
        "candidate_authorization": {
            "candidate_count": 60,
            "rows": [
                {
                    "candidate_id": row["candidate_id"],
                    "path": row["path"],
                    "action": "evaluate",
                    "reason_code": "Root_reviewed_scientific_scope_runtime_still_required",
                    "candidate_binding_sha256": candidate_authorization_binding_sha256(row),
                }
                for row in candidates
            ],
        },
        "required_reference_names": list(references),
        "required_references": references,
    },
)
save(
    D / "search-space.json",
    {
        **identity,
        "created_at": at,
        **search_definition,
        "single_mechanism_no_campaign_attestation": True,
        "candidate_manifest_path": str((D / "candidate-manifest.json").relative_to(ROOT)),
        "candidate_manifest_sha256": bind(D / "candidate-manifest.json")["sha256"],
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "data_feasibility_path": str((D / "data-feasibility.json").relative_to(ROOT)),
        "data_feasibility_sha256": bind(D / "data-feasibility.json")["sha256"],
        "cost_table_path": str((D / "costs-contract.json").relative_to(ROOT)),
        "contracts": contracts,
        "trial_ledger_paths": [str((D / "trial-ledger.jsonl").relative_to(ROOT))],
        "evaluation_report_paths": [str((D / "evaluation-report.json").relative_to(ROOT))],
        "knowledge_contract": {
            "assessment_path": str((D / "knowledge-assessment.json").relative_to(ROOT)),
            "scout_path": str((D / "knowledge-scout.json").relative_to(ROOT)),
            "model_reuse_decision_path": str((D / "model-reuse-decision.json").relative_to(ROOT)),
            "modality_role_matrix_path": str((D / "modality-role-matrix.json").relative_to(ROOT)),
            "required_visibility_partitions": [
                "public_literature",
                "train_only_empirical",
                "challenge_result",
                "forward_observation",
            ],
        },
    },
)
for name, body in {
    "external-brief.md": (
        "Source-led continuation of the full HF question with already fitted forecasts. "
        "The original20bp failure stays accepted. Root approved a bounded complete "
        "linear-cost, continuous-position application. This is conditional research "
        "under the original L1 delay; it neither tests a faster production clock nor "
        "certifies original factor construction, real settlement, current2026 profitability "
        "or paper readiness. All scientific sources, information controls, cash and "
        "risk assumptions remain bound to the approved scientific plan."
    ),
    "hypotheses.md": (
        "Hypothesis H1: continuous existing positions may preserve forecast value. "
        "Hypothesis H2: signal lifespan after the original delayed execution determines "
        "whether cumulative payoff can pay full fees. Hypothesis H3: matched market, "
        "zero and causal risk controls identify information rather than passive exposure. "
        "Failure mode: source reconstruction, expired labels, unsettled cash, small "
        "forecast magnitudes and overnight exposure. Measurement: fixed paired net "
        "dollars, continuous NAV, joint family uncertainty and actual risk. "
        "Stop/Pivot criterion: stop this APP when attributable net value fails, "
        "retaining the broader source mechanism and faster-clock question."
    ),
    "search-space.md": (
        "The approved inventory has three fixed policies, eight information streams "
        "and two capital anchors, together48 main identities and12 causal exposure "
        "controls. Exactly120 prospective twenty-thousand books cover primary20bp "
        "and stress40bp; thirty-six independently funded four-thousand sleeves are "
        "conditional on the main incremental-value criterion. No source, models, "
        "nearby parameters, costs, roles or windows can be added after results. "
        "All candidates are nonpromotable and all historical windows are seen."
    ),
    "decision-record.md": (
        "Path: full HF execution-value continuation. Decision: continue approved "
        "implementation and input/native preparation, with financial launch still "
        "blocked. Reason: an independent Root scientific review approved the complete "
        "question, while I1-I4 require actual code and arithmetic acceptance. "
        "Next iteration suggestion: return this concrete implementation to the same "
        "owner after independent acceptance, then run the real gates and first-book "
        "runtime calibration within the existing original pool. No economic result "
        "or broad mechanism refutation has been produced."
    ),
}.items():
    (D / name).write_text(body + "\n")
save(
    P / "first-book-launch-manifest.json",
    {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "candidate_id": "DP_H16_SLOW__PLS_IDX_CTS__B0",
        "capital_USD": 20000,
        "cost_bps_each_side": 20,
        "L_windows": 1,
        "CPU_upper": 200,
        "memory_MiB": 900,
        "disk_refresh_reserve_bytes": 9_533_075_101,
        "book_checkpoint_atomic_output_bytes": 64 * 1024**2,
        "core_count": 1,
        "financial_launch_admitted": False,
        "inputs": bind(P / "execution-input-manifest.json"),
        "implementation": bind(P / "implementation-manifest.json"),
        "full_approved_inventory": bind(P / "candidate-manifest-proposed.json"),
        "same_definition_native_checkpoint": True,
    },
)
save(
    P / "full-run-launch-manifest.json",
    {
        "schema_version": 1,
        "iter_id": ITER_ID,
        "financial_launch_admitted": False,
        "same_original_pool_and_parent": True,
        "fixed20k_views": [
            {
                "view_id": f"{r['candidate_id']}__{bps}__20k",
                "candidate_id": r["candidate_id"],
                "cost_bps_each_side": bps,
                "capital_USD": 20000,
                "kind": r["kind"],
            }
            for r in proposal["candidates"]
            for bps in [20, 40]
        ],
        "conditional4k_views": [
            {
                "view_id": f"{r['candidate_id']}__{bps}__4k",
                "candidate_id": r["candidate_id"],
                "cost_bps_each_side": bps,
                "capital_USD": 4000,
            }
            for r in proposal["candidates"]
            if r["optional_independent_4k_views"]
            for bps in [20, 40]
        ],
        "whole_batch_requires_measured_first_book_projection": True,
        "actual_cpu_memory_and_output_bytes_not_yet_measured_for_first_book": True,
        "actual_ledger_and_controls_first_then_secondary_statistics": True,
        "no_accepted_review_or_gate_fabricated": True,
    },
)
print(
    json.dumps(
        {
            "canonical_dossier_prepared": True,
            "candidates": 60,
            "implementation_review_pending": True,
            "financial_runs": 0,
        }
    )
)
