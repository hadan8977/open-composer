"""Refresh native bindings for the existing approved full mother scope."""

import hashlib
import json
from datetime import UTC, datetime

from consumer_admission import ROOT, P, bind

ITER = "martin_complete_system_20261014_dev"
D = ROOT / "reports/research/iterations" / ITER
ROLE = "market_component_method"
CAND = ["B_BREAK", "P_EMA", "P_SHAPE", "P_ANCHOR", "P_REENTRY", "P_HOLD", "P_FEEDBACK", "P_SYSTEM"]


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + "\n")


def main():
    D.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    campaign = bind(
        ROOT
        / (
            "reports/research/campaigns/martin_complete_system_20261014/r"
            "esearch-campaign-contract.json"
        )
    )
    cards_path = ROOT / "reports/harness/source_cards/martin_complete_system_20261014.jsonl"
    cards = [json.loads(line) for line in cards_path.read_text().splitlines()]
    # Same-day verified original first-person claims, retaining real source cards.
    selected = [c for c in cards if c["claim_id"] in {"ML_watchlist", "ML_ADR"}]
    sources = []
    eb = []
    for c in selected:
        sources.append(
            dict(
                claim_id=c["claim_id"],
                claim=c["claim"],
                core_claim=c["claim"],
                url=c["source_url"],
                source_type=c["source_type"],
                source_kind="authored_public_method",
                published_or_updated_at="2025-02-01",
                market_and_period="US six seen source names 2024-25",
                applicability="source-led full decision-system controls",
                limitations=c["limitations"],
                independent_replication=(
                    "Own matched controls pending; private account not reproduced"
                ),
                fetched_at="2026-10-13T16:45:18.374906+00:00",
                snapshot_path=c["snapshot_path"],
                sha256=c["snapshot_sha256"],
                source_card_path=str(cards_path.relative_to(ROOT)),
                credibility="Authored original source, not performance-isolating evidence",
                project_applicability=c["impact_on_spec"],
                reflection="Source mechanism and numeric adaptation remain separate",
            )
        )
        eb.append(
            dict(
                claim_id=c["claim_id"],
                source_card_path=str(cards_path.relative_to(ROOT)),
                snapshot_path=c["snapshot_path"],
                snapshot_sha256=c["snapshot_sha256"],
                source_url=c["source_url"],
            )
        )
    query = [
        dict(
            query=(
                "Reuse verified guest original; source-led long mechanism and"
                " negative/source-counterexamples from existing same-day inta"
                "ke"
            ),
            searched_at="2026-10-14T02:05:00+00:00",
            opened_urls=list({s["url"] for s in sources}),
        )
    ]
    save(
        D / "source-query-manifest.json",
        dict(
            iter_id=ITER,
            queries=query,
            actual_fresh_source_ledgers=[
                bind(P / "sources/discovery-01.json"),
                bind(P / "sources/primary-passages-01.json"),
            ],
            no_new_sourcecalls_from_dossier=True,
        ),
    )
    save(
        D / "knowledge-baseline.json",
        dict(
            as_of="2026-10-14T02:00:10.930746+00:00",
            source_reuse=[
                bind(P / "root-correction-and-continuation.json"),
                bind(P / "sources/preparation-receipt.json"),
            ],
            old_v3_and_four_case_grid_closed_unchanged=True,
            all_source_controls_seen_not_OOS=True,
            no_new_modality_or_ML=True,
            global_effective_trial_count=None,
        ),
    )
    direction = dict(
        schema_version=3,
        iter_id=ITER,
        reviewed_at=now,
        decision="proceed",
        objective=(
            "Executable full public decision system and costed continuous component contribution"
        ),
        target_regime_and_horizon=(
            "Exactly six seen source names, continuous2024-25 long holding with intraday entries"
        ),
        existing_solution_comparison=(
            "Preserve prior sealed cases; full context, geometry, anchors"
            ", reentry, holding, own-feedback in a common native cash boo"
            "k"
        ),
        remaining_evidence_gap=(
            "Conditional raw minute precision, active gaps, GME warrant v"
            "aluation, PIT cohort and actual NBBO/auction remain unresolv"
            "ed"
        ),
        negative_experiments_checked=(
            "Old diagnostic stop is not mother stop; explicit source losi"
            "ng examples and prototype counterexamples retained"
        ),
        cost_and_execution_assumptions=(
            "0/20/40bps each filled side, shared risk/cash; exact O-H-L-C"
            " and O-L-H-C synthetic L2 proxies, never global NAV bounds"
        ),
        stop_condition=(
            "Unknown active path remains sticky NA; no Alpha or whole-mec"
            "hanism refutation from shallow null. Original cumulative cap"
            "s unchanged"
        ),
        queries=query,
        sources=sources,
        source_evidence_bindings=eb,
        query_manifest=bind(D / "source-query-manifest.json"),
        pre_iteration_knowledge_baseline=bind(D / "knowledge-baseline.json"),
        cheapest_decisive_test=dict(
            action=(
                "After input/consumer/native/resource acceptance, matched ful"
                "l-system controls at20bps first; disclose both routes/paths"
            ),
            pass_condition=(
                "Valid source-conditioned whole cashbook trajectories disting"
                "uish component effects after costs"
            ),
            falsification_condition=(
                "Component incremental contribution absent on matched valid p"
                "aths; preserve untested parent claims"
            ),
            max_compute_minutes=10,
        ),
    )
    save(D / "direction-review.json", direction)
    external = dict(
        schema_version=3,
        iter_id=ITER,
        research_role=ROLE,
        strategy_name="Martin complete source-method system",
        source_spec_path=None,
        spec_hash=None,
        objective=direction["objective"],
        mechanism_family="full_source_method_component_system",
        mechanism_description=(
            "Frozen context and full stateful policy consumed by native execution"
        ),
        difference_from_existing=[direction["existing_solution_comparison"]],
        current_source_card_paths=[str(cards_path.relative_to(ROOT))],
        source_evidence_bindings=eb,
        sources=sources,
        topic_coverage=[
            "context",
            "base",
            "typed confluence",
            "clock",
            "shared cash",
            "actions",
            "reentry",
            "holding",
            "feedback",
            "counterevidence",
        ],
        candidate_matrix_revisions=[
            "8x2x3x2=96 distinct continuous simulations; annual views additional"
        ],
        hypothesis_links=["H_ROOT", "H_CONTEXT", "H_PATH", "H_POLICY"],
        campaign_id=campaign["path"].split("/")[-2],
        campaign_contract_path=campaign["path"],
        campaign_contract_sha256=campaign["sha256"],
    )
    save(D / "external-brief.json", external)
    (D / "external-brief.md").write_text(
        "Source-led complete Martin long decision system: causal watc"
        "hlist, base, confluence, entry, reentry, holding and own-fee"
        "dback in one cash account. Six predetermined 2024-25 names a"
        "re seen controls. Source examples and local numeric adaptati"
        "ons remain separate. Economic execution requires actual inde"
        "pendent input, implementation, native and resource acceptanc"
        "e. Mother research continues.\n"
    )
    (D / "hypotheses.md").write_text(
        "Hypothesis: causal context, full holding and risk feedback m"
        "ay add matched net contribution. Failure mode: retrospective"
        " cohort, insufficient causal geometry, friction or unknown a"
        "ctive input may prevent identifying that contribution. Measu"
        "rement: frozen eight policy components crossed with both rou"
        "tes, three costs and both OHLC scenarios in one continuous a"
        "ccount. Stop/Pivot criterion: preserve typed unknown paths, "
        "pursue informative original depth and do not refute the full"
        " public mechanism from a shallow null.\n"
    )
    (D / "search-space.md").write_text(
        "Eight frozen policies are crossed with two independent execu"
        "tion routes, three fixed cost assumptions and two explicitly"
        " named OHLC paths. Exactly ninety-six distinct continuous si"
        "mulations are declared. The two annual slices are additional"
        " reporting views. No profitable path selection, numeric para"
        "meter expansion, annual account restart or old four-case gri"
        "d reopening is permitted.\n"
    )
    (D / "decision-record.md").write_text(
        "Path: full source-method component system. Decision: continu"
        "e the complete mother question under its approved R1 science"
        ". Reason: diagnostic completion did not complete strategy co"
        "nversion, and implementation evidence now supports independe"
        "nt acceptance work. Next iteration suggestion: after actual "
        "input, consumer, native and resource acceptance run the matc"
        "hed costed continuous controls; retain unresolved claims and"
        " cumulative spending.\n"
    )
    contracts = {}
    for name, target in {
        "data": P / "complete-input-v2-result.json",
        "features": P / "code/frame_producer.py",
        "labels": P / "revisions/r1/event-book-contract.json",
        "validation": P / "revisions/r1/scientific-plan-v2.json",
        "costs": P / "consumer-cases.json",
        "benchmarks": P / "revisions/r1/scientific-plan-v2.json",
    }.items():
        q = D / (name + "-contract.json")
        save(
            q,
            dict(
                binding=bind(target),
                definition=(
                    "Approved frozen contracts apply; descriptive nonpromotable component controls"
                ),
                promotion_eligible=False,
            ),
        )
        contracts[name] = {name: bind(q)}
    # Receipt may not exist yet. Its real SHA must be refreshed after independent acceptance.
    review = P / "consumer-independent-review.json"
    rb = bind(review) if review.exists() else dict(path=str(review.relative_to(ROOT)), sha256=None)
    method = dict(
        schema_version=1,
        research_role=ROLE,
        iter_id=ITER,
        candidate_manifest_path=str((D / "candidate-manifest.json").relative_to(ROOT)),
        data_feasibility_path=str((D / "data-feasibility.json").relative_to(ROOT)),
        time_axis_kind="market_timestamp",
        claim_scope="conditional_cohort",
        real_market_claim=True,
        candidate_ids=CAND,
        promotion_eligible=False,
        paper_trading_allowed=False,
        broker_activity_allowed=False,
        pit_universe_certified=False,
        deployment_readiness_claim=False,
        scientific_plan=bind(P / "revisions/r1/scientific-plan-v2.json"),
        independent_plan_review=bind(P / "revisions/r1/independent-review.json"),
        implementation_manifest=bind(P / "consumer-implementation-manifest.json"),
        independent_implementation_review=rb,
        resource_permission=(
            "Explicit independent original-pool admission; native/source "
            "generation is part of admitted economic consumer only if rec"
            "eipt explicitly allocates it"
        ),
    )
    save(D / "method-definition.json", method)
    candidates = []
    blueprints = json.loads((ROOT / campaign["path"]).read_text())["candidate_blueprints"]
    for c in CAND:
        b = next(x for x in blueprints if x["candidate_id"] == c)
        candidates.append(
            dict(
                candidate_id=c,
                path="complete_system",
                role="matched_component",
                method=c,
                ablation=b["method_variant"],
                fallback="sticky_unknown_NA_or_no_signal_when_flat",
                research_role=ROLE,
                promotion_eligible=False,
                method_definition_path=str((D / "method-definition.json").relative_to(ROOT)),
                method_definition_sha256=bind(D / "method-definition.json")["sha256"],
                mechanism_family="full_source_method_component_system",
                data_contract="data",
                feature_contract="features",
                label_contract="labels",
                validation_contract="validation",
                cost_contract="costs",
                benchmark_contract="benchmarks",
                campaign_id=external["campaign_id"],
                hypothesis_id=b["hypothesis_id"],
                branch_id=b["branch_id"],
                child_iteration_id=ITER,
                quality_metric="development_diagnostic_net_contribution_not_selectable",
                universe_contract_path=str(
                    (D / ("universe-" + b["branch_id"] + ".json")).relative_to(ROOT)
                ),
                universe_contract_sha256=None,
                development_partition_contract_path=str(
                    (D / "data-contract.json").relative_to(ROOT)
                ),
                development_partition_contract_sha256=bind(D / "data-contract.json")["sha256"],
                pit_universe_sha256=None,
                development_partition_sha256=bind(P / "complete-input-v2-result.json")["sha256"],
            )
        )
    manifest = dict(
        schema_version=3,
        research_role=ROLE,
        manifest_type="generic_candidate_family_v1",
        iter_id=ITER,
        generated_before_backtest=True,
        generated_at=now,
        candidate_count=8,
        contracts=contracts,
        candidates=candidates,
        actual_new_executed_cells=0,
        planned_distinct_continuous_cells=96,
        selection_optimization=False,
    )
    save(D / "candidate-manifest.json", manifest)
    accepted = (
        review.exists()
        and json.loads(review.read_text()).get("verdict") == "approve_implementation"
    )
    feas = dict(
        schema_version=1,
        report_type="conditional_complete_source_system_input_feasibility",
        iter_id=ITER,
        workflow_pass=accepted,
        research_pass=False,
        llm_contribution_pass=False,
        paper_ready_pass=False,
        historical_evaluation_authorized=accepted,
        economic_execution_admitted=False,
        path_gates={
            "complete_system": dict(
                action="evaluate" if accepted else "dependency_skipped",
                historical_evaluation_go=accepted,
                candidate_ids=CAND,
                claim_scope="conditional_cohort",
            )
        },
        candidate_accounting=dict(
            frozen_candidate_count=8,
            evaluation_authorized_count=8 if accepted else 0,
            dependency_skipped_count=0 if accepted else 8,
            unresolved_count=0,
            balanced=True,
        ),
        candidate_authorization=dict(
            candidate_count=8,
            rows=[
                dict(
                    candidate_id=c,
                    action="evaluate" if accepted else "dependency_skipped",
                    path="complete_system",
                    reason_code="accepted_conditional_full_input_and_consumer"
                    if accepted
                    else "await_independent_consumer",
                    candidate_binding_sha256=hashlib.sha256(
                        json.dumps(
                            {
                                k: v
                                for k, v in row.items()
                                if k
                                not in {
                                    "universe_contract_sha256",
                                    "development_partition_contract_sha256",
                                }
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest(),
                )
                for c, row in zip(CAND, candidates, strict=True)
            ],
        ),
        campaign_universe=dict(
            status="ready" if accepted else "dependency_skipped",
            capability_ids=["market.alpaca_bars"],
        ),
        required_reference_names=["science", "input"] + (["implementation"] if accepted else []),
        required_references={
            "science": method["independent_plan_review"],
            "input": bind(P / "complete-input-v2-result.json"),
            **({"implementation": rb} if accepted else {}),
        },
    )
    save(D / "data-feasibility.json", feas)
    data_contract = json.loads((D / "data-contract.json").read_text())
    data_contract.update(partition_id="seen_2024_2025", kind="development")
    save(D / "data-contract.json", data_contract)
    contracts["data"]["data"] = bind(D / "data-contract.json")
    for branch in ("H_CONTEXT", "H_PATH", "H_POLICY"):
        u = dict(
            schema_version=1,
            campaign_id=external["campaign_id"],
            child_iteration_id=ITER,
            hypothesis_id=branch,
            universe_selection="static_hotspot_control",
            promotion_eligible=False,
            contract_status="ready" if accepted else "dependency_skipped",
            capability_ids=["market.alpaca_bars"],
            data_feasibility_binding=bind(D / "data-feasibility.json"),
            blockers=[] if accepted else ["actual_independent_consumer_acceptance_pending"],
            universe_definition=dict(
                membership_mode="static_hotspot_control",
                symbols=["COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"],
                selection_rule=(
                    "Exactly six source examples frozen before candidate generati"
                    "on; no population selection claim"
                ),
                selection_frozen_at="2026-10-14T02:06:11.937089+00:00",
            ),
        )
        save(D / ("universe-" + branch + ".json"), u)
    for row in candidates:
        row["universe_contract_sha256"] = bind(ROOT / row["universe_contract_path"])["sha256"]
        row["development_partition_contract_sha256"] = bind(D / "data-contract.json")["sha256"]
    save(D / "candidate-manifest.json", manifest)
    search = dict(
        schema_version=3,
        iter_id=ITER,
        research_role=ROLE,
        strategy_name=external["strategy_name"],
        source_spec_path=None,
        spec_hash=None,
        created_at=now,
        paths=[
            dict(
                name="complete_system",
                candidate_count=8,
                hypothesis_refs=["H_CONTEXT", "H_PATH", "H_POLICY"],
                parameters=dict(
                    policies=CAND,
                    routes=["market", "capped"],
                    cost_bps_per_side=[0, 20, 40],
                    scenarios=["O-H-L-C", "O-L-H-C"],
                    profit_optimization=False,
                ),
                benchmark_family=[
                    "same_symbol_buy_and_hold",
                    "equal_weight_universe",
                    "QQQ",
                    "IWM",
                    "cash",
                    "sector_dependency_unresolved",
                    "ex_post_best_symbol_descriptive",
                ],
            )
        ],
        total_candidate_budget=8,
        candidate_manifest_path=method["candidate_manifest_path"],
        candidate_manifest_contract="generic_candidate_family_v1",
        candidate_manifest_sha256=bind(D / "candidate-manifest.json")["sha256"],
        cost_table_path=str((D / "costs-contract.json").relative_to(ROOT)),
        data_feasibility_path=method["data_feasibility_path"],
        data_feasibility_sha256=bind(D / "data-feasibility.json")["sha256"],
        trial_ledger_paths=[str((P / "economic-results/trial-ledger.jsonl").relative_to(ROOT))],
        evaluation_report_paths=[],
        candidate_selection_eligible=False,
        economic_execution_admitted=False,
        campaign_id=external["campaign_id"],
        campaign_contract_path=campaign["path"],
        campaign_contract_sha256=campaign["sha256"],
    )
    save(D / "search-space.json", search)
    print(json.dumps(dict(iteration=ITER, independent_implementation_accepted=accepted)))


if __name__ == "__main__":
    main()
