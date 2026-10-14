"""Freeze the received input/complete plan as a native, isolated component dossier."""

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from open_composer.market_sessions import us_equity_session_dates
from open_composer.research.knowledge_memory import canonical_source_url, claim_fingerprint

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
ITER = "t20261014_dlsa_real_market_method"
REL = "reports/research/iterations/" + ITER
DOSSIER = OUT / REL


def write(name, value):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def bind(p):
    return {
        "path": str(p.relative_to(OUT)),
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }


def main():
    stamp = datetime.now(UTC).isoformat()
    DOSSIER.mkdir(parents=True, exist_ok=True)
    contract = json.loads((OUT / "input-contract.json").read_text())
    calendar = [x.isoformat() for x in us_equity_session_dates(date(2018, 1, 2), date(2026, 9, 30))]
    evaluation = list(range(len(calendar) - 501, len(calendar) - 1))
    assert len(evaluation) == 500
    fits = []
    for block in range(-1, 4):
        begin = evaluation[0] - 126 if block == -1 else evaluation[block * 125]
        segment = list(range(begin, begin + 125))
        validation = segment if block == -1 else []
        # Final training label matures at begin-1, before execution information.
        train_end = begin - 1
        training = list(range(train_end - 1000 + 30, train_end))
        assert len(training) == 970
        for stream in ["S1", "S2"]:
            for seed in [0, 1]:
                fits.append(
                    {
                        "fit_id": f"{stream}-block{block:02}-seed{seed}",
                        "stream": stream,
                        "block": block,
                        "seed": seed,
                        "epochs": 100,
                        "optimizer": "Adam",
                        "lr": 0.001,
                        "optimization_batch": 125,
                        "training_calendar_indices": training,
                        "validation_calendar_indices": validation,
                        "evaluation_calendar_indices": segment,
                        "training_costs": {
                            "transaction": 0.0005 if stream == "S2" else 0,
                            "short_daily": 0.0001 if stream == "S2" else 0,
                        },
                        "training_interval": [calendar[training[0]], calendar[training[-1]]],
                        "validation_execution_interval": (
                            [calendar[validation[0]], calendar[validation[-1]]]
                            if validation
                            else None
                        ),
                        "evaluation_execution_interval": [calendar[begin], calendar[begin + 124]],
                        "last_evaluation_label_date": calendar[begin + 125],
                        "promotion_eligible": False,
                        "budget_status": "proposed_not_allocated",
                    }
                )
    role = "market_component_method"
    common = {
        "schema_version": 3,
        "iter_id": ITER,
        "research_role": role,
        "strategy_name": "DLSA conditional real-security PCA cost-learning method",
        "source_spec_path": None,
        "spec_hash": None,
        "mechanism_family": "learned_residual_statistical_arbitrage",
    }
    names = {
        "S0": "source OUThreshold",
        "S1": "same source CNN gross training",
        "S2": "same source CNN source-cost training",
        "S3": "zero model fallback",
        "S4": "S2 inference path lagged60",
        "S5": "S2 fixed20-session input outage",
        "S6": "fixed path-z mean-reversion control",
    }
    codes = OUT / "implementation"
    codes.mkdir(exist_ok=True)
    original = ROOT / (
        "reports/research/program/day-goal-20261011/source-led-selection/r"
        "oot-dlsa-source/input-package"
    )
    for source, target in [
        ("model-CNNTransformer.py", "source-CNNTransformer.py"),
        ("model-OUThreshold.py", "source-OUThreshold.py"),
    ]:
        shutil.copyfile(original / source, codes / target)
    implementation = {
        "schema_version": 1,
        "task_id": contract["task_id"],
        "author": "8450cad5-caf7-47b8-899b-5b28c8076512",
        "files": [
            bind(OUT / name)
            for name in [
                "method_math.py",
                "pipeline.py",
                "prepare_inputs.py",
                "repair_inputs.py",
                "acquire_scoped_inputs.py",
                "verify_math.py",
                "implementation/source-CNNTransformer.py",
                "implementation/source-OUThreshold.py",
            ]
        ],
        "economic_execution_started": False,
        "new_optimizer_updates": 0,
        "licensing_scope": "existing permitted noncommercial research; source files unchanged",
        "known_unexecuted_boundaries": [
            "actual raw/action normalization",
            "real CNN training",
            "actual benchmark/host income acceptance",
            "independent approval",
        ],
    }
    write("implementation-manifest.json", implementation)
    history = (
        ROOT
        / "reports/research/program/day-goal-20261013/dlsa/deepening/root-H5-result-acceptance.json"
    )
    shutil.copyfile(history, OUT / "historical-root-H5-acceptance.json")
    baseline = {
        "schema_version": 1,
        "iter_id": ITER,
        "generated_at": stamp,
        "actual_history_binding": bind(OUT / "historical-root-H5-acceptance.json"),
        "accepted_fits": 12,
        "accepted_optimizer_updates": 9600,
        "prior_findings": (
            "two paired H1 positive/negative intervals and H5 counterevidence retained"
        ),
        "recent_visibility": "2018-2026 current-vintage; 2023-2026 seen; no new unseen OOS claim",
        "original_global_memory_index_preserved": True,
    }
    write("pre-iteration-knowledge-baseline.json", baseline)
    md_binding = bind(OUT / "scientific-plan.md")
    write(
        "scientific-plan.json",
        {
            "schema_version": 1,
            "task_id": contract["task_id"],
            "author": implementation["author"],
            "complete_plan": md_binding,
            "question": (
                "Does same-input cost-aware residual-pat"
                "h CNN beat matched simple residual and "
                "gross-trained CNN after costs?"
            ),
            "research_object": "nonpromotable model method adaptation",
            "parent_question_open": True,
            "input_contract": bind(OUT / "input-contract.json"),
            "input_coverage": bind(OUT / "inputs/coverage.json"),
            "actual_repairs": bind(OUT / "inputs/detailed-episode-repairs.json"),
            "candidate_ids": list(names),
            "planned_model_fits": 20,
            "planned_updates": 16000,
            "actual_new_fits": 0,
            "actual_new_updates": 0,
            "initial_stage_complete": False,
            "training_allocated": False,
            "economic_execution_admitted": False,
            "new_spending_authorized": False,
            "source_requests_proposed": 96,
            "history": baseline,
            "actual_implementation": bind(OUT / "implementation-manifest.json"),
        },
    )
    for name, verdict in [
        ("independent-plan-review.json", "pending_independent_slot"),
        ("independent-implementation-review.json", "pending_independent_slot"),
    ]:
        if not (OUT / name).exists():
            write(
                name,
                {
                    "schema_version": 1,
                    "author": implementation["author"],
                    "reviewer": None,
                    "verdict": verdict,
                    "status": "not_reviewed; cannot_self_approve",
                    "reason": (
                        "4 actual active owners including Root/HF/Martin/DLSA; no fifth agent"
                    ),
                    "bindings": {},
                },
            )
    write(
        REL + "/method-definition.json",
        {
            "schema_version": 1,
            "research_role": role,
            "iter_id": ITER,
            "candidate_manifest_path": REL + "/candidate-manifest.json",
            "data_feasibility_path": REL + "/data-feasibility.json",
            "time_axis_kind": "market_timestamp",
            "claim_scope": "conditional_cohort",
            "real_market_claim": True,
            "candidate_ids": list(names),
            "promotion_eligible": False,
            "paper_trading_allowed": False,
            "broker_activity_allowed": False,
            "pit_universe_certified": False,
            "deployment_readiness_claim": False,
            "scientific_plan": bind(OUT / "scientific-plan.json"),
            "independent_plan_review": bind(OUT / "independent-plan-review.json"),
            "implementation_manifest": bind(OUT / "implementation-manifest.json"),
            "independent_implementation_review": bind(
                OUT / "independent-implementation-review.json"
            ),
        },
    )
    candidates = []
    for name, method in names.items():
        candidates.append(
            {
                "candidate_id": name,
                "path": "fixed_source_cost_method",
                "research_role": role,
                "promotion_eligible": False,
                "role": "conditional_source_cost_method",
                "method": method,
                "ablation": name,
                "fallback": "zero model; unknown held marks retain N/A",
                "mechanism_family": common["mechanism_family"],
                "method_definition_path": REL + "/method-definition.json",
                "method_definition_sha256": bind(DOSSIER / "method-definition.json")["sha256"],
                **{
                    field: "M0"
                    for field in [
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
    manifest = {
        **common,
        "generated_before_backtest": True,
        "manifest_type": "generic_candidate_family_v1",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "calendar": calendar,
        "evaluation_execution_indices": evaluation,
        "fits": fits,
        "model_fit_count": 20,
        "max_optimizer_updates": 19200,
        "seed_selection": (
            "fixed equal2-target ensemble and all individual seeds; no winner selection"
        ),
        "planned_cost_views_bps": [0, 2, 5, 10, 20, 40],
        "historical_accepted_fits": 12,
        "historical_accepted_updates": 9600,
        "new_trials_and_evaluations_executed": 0,
    }
    write("candidate-manifest.json", manifest)
    write(REL + "/candidate-manifest.json", manifest)
    # Task-local cards use the scoped native root. Original intake cards remain intact.
    cards = [json.loads(s) for s in (OUT / "source-cards.jsonl").read_text().splitlines()]
    sources, bindings = [], []
    for c in cards:
        c = dict(c)
        c["snapshot_path"] = str((ROOT / c["snapshot_path"]).relative_to(OUT))
        c.update(
            iteration_id=ITER,
            accessed_at=c["fetched_at"][:10],
            verified_at=c["fetched_at"],
            verification_method="actual_fetched_snapshot_quote_and_sha",
        )
        s = {
            "claim_id": c["claim_id"],
            "url": c["source_url"],
            "source_type": c["source_type"],
            "published_or_updated_at": "2022-10-07"
            if c["claim_id"] == "dlsa-paper-v2"
            else "unknown",
            "market_and_period": "US daily equities; source1998-2016 and conditional2018-2026",
            "applicability": "real-cohort price-PCA method; no original IPCA replication",
            "limitations": c["scope"],
            "independent_replication": "independent PCA caveat card retained",
            "fetched_at": c["fetched_at"],
            "snapshot_path": c["snapshot_path"],
            "sha256": c["source_sha256"],
            "source_card_path": "native-source-cards.jsonl",
            "claim": c["claim"],
            "core_claim": c["claim"],
            "credibility": "actual primary source snapshot",
            "project_applicability": "source-supported conditional cost-learning contrast",
            "reflection": "method/data/source results separate; actual input readiness unapproved",
        }
        sources.append(s)
        bindings.append(
            {
                "claim_id": c["claim_id"],
                "source_card_claim_id": c["claim_id"],
                "source_card_path": "native-source-cards.jsonl",
                "snapshot_path": c["snapshot_path"],
                "snapshot_sha256": c["source_sha256"],
                "source_url": c["source_url"],
                "canonical_url": canonical_source_url(c["source_url"]),
                "claim_fingerprint": claim_fingerprint(c["claim"]),
                "brief_claim_fingerprint": claim_fingerprint(c["claim"]),
            }
        )
    (OUT / "native-source-cards.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    **c,
                    "snapshot_path": str((ROOT / c["snapshot_path"]).relative_to(OUT)),
                    "iteration_id": ITER,
                    "accessed_at": c["fetched_at"][:10],
                    "verified_at": c["fetched_at"],
                    "verification_method": "actual_snapshot_quote_and_sha",
                },
                ensure_ascii=False,
            )
            + "\n"
            for c in cards
        )
    )
    queries = [
        {
            "query": "Deep learning statistical arbitrage PCA transaction costs",
            "searched_at": "2026-10-14T16:28:00+00:00",
            "opened_urls": [s["url"] for s in sources],
        }
    ]
    write("direction-query-manifest.json", {"queries": queries, "actual_source_fetches": 4})
    direction = {
        "schema_version": 3,
        "iter_id": ITER,
        "reviewed_at": stamp,
        "decision": "proceed",
        "objective": "Resolve parent real-market cost-aware residual path question",
        "target_regime_and_horizon": "current-vintage recent500 continuous daily periods; all seen",
        "existing_solution_comparison": (
            "licensed IPCA/CRSP/JKP export unavailab"
            "le; paper PCA is substantive same-retur"
            "n alternative"
        ),
        "remaining_evidence_gap": (
            "32-shareclass raw/action/terminal accep"
            "ted dataset, independent review and act"
            "ual resource admission"
        ),
        "negative_experiments_checked": (
            "accepted H5 underperformance and independent PCA survivorship/cost problems"
        ),
        "cost_and_execution_assumptions": (
            "source5/short1 primary explanatory model; exact drifted-cost fractional method"
        ),
        "stop_condition": (
            "complete matched net evidence or retain"
            "ed unresolved scope plus opportunity-co"
            "st decision; no nearby tuning until pos"
            "itive"
        ),
        "queries": queries,
        "sources": sources,
        "source_evidence_bindings": bindings,
        "query_manifest": bind(OUT / "direction-query-manifest.json"),
        "pre_iteration_knowledge_baseline": bind(OUT / "pre-iteration-knowledge-baseline.json"),
        "cheapest_decisive_test": {
            "action": "actual cohort connection then full same-input OU/gross/cost CNN contrast",
            "pass_condition": (
                "complete primary paired net increments and absence of placebo explanation"
            ),
            "falsification_condition": (
                "cost/terminal/missing repairs remove gain or matched delta lacks economic value"
            ),
            "max_compute_minutes": 480,
        },
    }
    write("direction-review.json", direction)
    write(REL + "/direction-review.json", direction)
    external = {
        **common,
        "created_at": stamp,
        "sources": sources,
        "current_source_card_paths": ["native-source-cards.jsonl"],
        "source_evidence_bindings": bindings,
        "topic_coverage": [
            "source_fidelity",
            "PCA",
            "raw_actions",
            "terminal",
            "causal_calendar",
            "cost_learning",
            "matched_increment",
            "negative_evidence",
        ],
        "candidate_matrix_revisions": [
            "S0 faithful public OU baseline; S6 path-z control; sameCNN S1/S2"
        ],
        "difference_from_existing": (
            "real current-vintage dated cohort instead of anonymous perturbed source"
        ),
    }
    write(REL + "/external-brief.json", external)
    base_contracts = {
        "data": contract,
        "features": {"PCA_k": 5, "history": 252, "loadings": 60, "path": 30, "past_only": True},
        "labels": {
            "clock": "execution close e uses info through e-1; return endpoint e+1",
            "unit": "decimal economic return",
        },
        "validation": {
            "validation125_after_training1000": True,
            "model_selection": False,
            "all_recent_seen": True,
        },
        "costs": {
            "primary_turnover": 0.0005,
            "primary_short_daily": 0.0001,
            "stress_bps": [20, 40],
            "source_penalty_not_actual_fee_calibration": True,
        },
        "benchmarks": {
            "family": [
                "same_symbol",
                "historical_cohort_equal_weight",
                "SPY",
                "XLF",
                "XLI",
                "BIL",
                "ex_post_best",
            ],
            "no_missing_proxy_substitution": True,
        },
    }
    contracts = {}
    for kind, obj in base_contracts.items():
        name = REL + "/" + kind + "-contract.json"
        write(name, obj)
        contracts[kind] = {"M0": bind(OUT / name)}
    feasibility = {
        "input_status": "actual_candidates_received_and_repaired_not_economic_accepted",
        "cohort_size": 32,
        "observed_rows": 68043,
        "calendar_sessions": 2198,
        "data_contract": bind(OUT / "input-contract.json"),
        "actual_connections": bind(OUT / "inputs/actual-connected-raw-sample.json"),
        "actual_episode_repairs": bind(OUT / "inputs/detailed-episode-repairs.json"),
        "scientific_input_ready": False,
        "promotion_data_ready": False,
        "sample_or_fixture": False,
        "missing_dependencies": [
            "bound real raw-action/terminal panel",
            "independent input acceptance",
            "independent complete plan / code acceptance",
            "Root complete resource pool",
        ],
    }
    write(REL + "/data-feasibility.json", feasibility)
    search = {
        **common,
        "created_at": stamp,
        "single_mechanism_no_campaign_attestation": True,
        "total_candidate_budget": 7,
        "candidate_manifest_path": REL + "/candidate-manifest.json",
        "candidate_manifest_sha256": bind(DOSSIER / "candidate-manifest.json")["sha256"],
        "candidate_manifest_contract": "generic_candidate_family_v1",
        "model_fit_count": 20,
        "paths": [
            {
                "name": "fixed_source_cost_method",
                "candidate_count": 7,
                "hypothesis_refs": ["source_cost_learning_on_actual_returns"],
                "parameters": {"fixed_ids": list(names), "fits": 20, "no_parameter_search": True},
            }
        ],
        "contracts": contracts,
        "data_feasibility_path": REL + "/data-feasibility.json",
        "data_feasibility_sha256": bind(DOSSIER / "data-feasibility.json")["sha256"],
        "cost_table_path": REL + "/costs-contract.json",
        "trial_ledger_paths": [REL + "/trial-ledger.jsonl"],
        "evaluation_report_paths": [REL + "/evaluation-report.json"],
        "knowledge_contract": {
            "assessment_path": REL + "/knowledge-assessment.json",
            "scout_path": REL + "/knowledge-scout.json",
            "model_reuse_decision_path": REL + "/model-reuse-decision.json",
            "modality_role_matrix_path": REL + "/modality-role-matrix.json",
            "required_visibility_partitions": [
                "public_literature",
                "train_only_empirical",
                "challenge_result",
                "forward_observation",
            ],
        },
    }
    write(REL + "/search-space.json", search)
    write(
        REL + "/knowledge-scout-queries.json",
        {
            "schema_version": 2,
            "iter_id": ITER,
            "queries": [],
            "curated_candidates": [
                {
                    "url": s["url"],
                    "title": s["claim_id"],
                    "summary": s["claim"],
                    "source_type": s["source_type"],
                    "topics": ["source_fidelity", "costs", "causal_method"],
                    "published_at": s["published_or_updated_at"],
                }
                for s in sources
            ],
            "max_results_per_query": 3,
            "no_network_for_curated_manifest": True,
        },
    )
    write(
        REL + "/modality-role-matrix.json",
        {
            "schema_version": 1,
            "iter_id": ITER,
            "roles": {
                "factor_generation": "causal price PCA fixed",
                "return_ranking": "CNN residual allocation",
                "risk_prediction": "no separate ML forecast",
                "regime_meta_gating": "not part of claim",
                "sizing": "same mapped L1 plus fixed seed ensemble",
                "uncertainty": "paired block bootstrap",
                "deterministic_fallback": "zero",
            },
            "new_information_modality": False,
            "quant_only": "same input original OUThreshold",
            "combined": "not applicable; price only",
            "missing_modality": "S5 actual zero input policy",
            "placebo": "S4 lag60",
            "LLM_signal_contribution_claim": False,
        },
    )
    for name in ["external-brief.md", "search-space.md", "hypotheses.md"]:
        (DOSSIER / name).write_text(
            "# Complete task-local method package\n\n"
            "See scientific-plan.md and bound scientific-plan.json at the scoped root. "
            "Prepared actual inputs and proposed full experiment; no new economic admission.\n"
        )
    symbols = contract["cohort"]["symbols"] + ["EG", "MTB", "FI", "IR", "SPY", "BIL", "XLF", "XLI"]
    requests = []
    for symbol in symbols:
        requests.append(
            {
                "id": symbol + "_raw",
                "endpoint": "https://data.alpaca.markets/v2/stocks/bars",
                "factory_path": "/stocks/bars",
                "kind": "bars",
                "params": {
                    "symbols": symbol,
                    "timeframe": "1Day",
                    "start": "2017-12-27T00:00:00Z",
                    "end": "2026-10-01T00:00:00Z",
                    "feed": "sip",
                    "adjustment": "raw",
                    "asof": "-",
                    "sort": "asc",
                    "limit": 10000,
                    "currency": "USD",
                },
            }
        )
        requests.append(
            {
                "id": symbol + "_actions",
                "endpoint": "https://data.alpaca.markets/v1/corporate-actions",
                "factory_path": "https://data.alpaca.markets/v1/corporate-actions",
                "kind": "actions",
                "params": {
                    "symbols": symbol,
                    "start": "2017-01-01",
                    "end": "2026-10-14",
                    "limit": 1000,
                    "sort": "asc",
                    "data_quality": "all",
                    "region": "us",
                },
            }
        )
    write(
        "source-request-manifest.json",
        {
            "schema_version": 1,
            "task_id": contract["task_id"],
            "frozen_before_new_raw_action_requests": True,
            "status": "proposal_not_admitted",
            "requests": requests,
            "caps": {
                "requests": 96,
                "bytes": 64 * 1024**2,
                "per_response_bytes_max": 2 * 1024**2,
                "pages_per_input_max": 2,
            },
            "pre_existing_requests_preserved": {"old_acquisition": 13, "actual_bytes": 44098},
            "source_semantics": (
                "raw original ticker; all-type process-d"
                "ate action responses need economic-date"
                " reconciliation"
            ),
            "no_new_subscription_or_spending": True,
            "no_orders_or_ETB_requests": True,
            "successor_inputs_are_not_new_selection_candidates": ["EG", "MTB", "FI", "IR"],
        },
    )
    write(
        "resource-proposal.json",
        {
            "task_id": contract["task_id"],
            "as_of_utc": stamp,
            "scope": (
                "One complete input-to-result pool, cond"
                "itional on actual independent/input/nat"
                "ive gates"
            ),
            "source_request_manifest": bind(OUT / "source-request-manifest.json"),
            "new_requests_proposed": 96,
            "new_requests_executed": 0,
            "new_fits_proposed": 20,
            "new_updates_proposed": 16000,
            "actual_new_fits": 0,
            "actual_new_updates": 0,
            "Hadan": {
                "proposed_memory_GiB": 4,
                "proposed_cpu": 1,
                "full_wall_pool_hours": 8,
                "readiness_not_checked_for_unadmitted_work": True,
                "budget_not_allocated": True,
                "required_root": "C:\\paseo",
                "total_usage_cap_GiB": 50,
                "native_checkpoint": "torch model/Adam/RNG, each complete update and completed fit",
            },
            "Modal": {
                "proposed_cpu": 2,
                "proposed_memory_GiB": 4,
                "proposed_gpu": "T4",
                "timeout_minutes": 120,
                "fresh_shared_budget_check_required": True,
                "not_reserved_or_launched": True,
                "known_20261013_conservative_remaining_USD": 2.131736143684387,
                "historical_reservation_retained_USD": 2.9012,
                "historical_bill_margin_snapshot_is_not_current_balance": True,
            },
            "estimated_dense_daily_projection_bytes": len(calendar) * 32 * 32 * 4,
            "memory_estimate_is_not_actual_training_RSS": True,
            "accepted_historical": {"fits": 12, "updates": 9600},
            "Linux": {
                "preparation_default_memory_MiB": 900,
                "reserve_MiB": 500,
                "measured_prepare_RSS_KiB": 229604,
                "measured_prepare_CPU_seconds": 109.421890609,
            },
            "new_spending_authorized": False,
            "paper_or_broker_started": False,
        },
    )
    print(
        json.dumps(
            {
                "native_scope_root": str(OUT),
                "candidates": 7,
                "proposed_fits": 20,
                "proposed_updates": 16000,
                "first_execution": calendar[evaluation[0]],
                "last_execution": calendar[evaluation[-1]],
                "last_return_endpoint": calendar[evaluation[-1] + 1],
                "source_specs": len(requests),
                "new_market_requests": 0,
                "actual_new_training": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
