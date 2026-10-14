"""Freeze actual evidence and an enumerated conditional research package."""

import hashlib
import itertools
import json
import re
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
MARTIN = BASE.parent / "martin-luk-usic-20261013"
ITER_ID = "usic_pullback_feedback_20261013"
ITER = ROOT / "reports/research/iterations" / ITER_ID
CAMP = ROOT / "reports/research/campaigns" / ITER_ID
NOW = datetime.now(UTC).isoformat()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def plaintext(path):
    obj = json.loads(path.read_text())
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


plan = json.loads((BASE / "scientific-plan.json").read_text())
inventory = plan["candidate_inventory"]
# Campaign is written before the candidate manifest/feature evaluation.
template = json.loads(
    (
        ROOT / "reports/research/campaigns/eq_role_source_20261013/research-campaign-contract.json"
    ).read_text()
)
template.update(
    campaign_id=ITER_ID,
    created_at=NOW,
    title="Public practitioner pullback and feedback diagnostics",
    objective=(
        "Eight fixed nonpromotable, input/resource-conditional method"
        " contrasts; selectedpubliccases are fidelityevidence, not in"
        "vestablewinnercohort. No privateaccountreturn replication or"
        " unseenOOSclaim."
    ),
    parent_iteration_ids=["h20260923_13_orb_stocks_in_play"],
    child_iteration_ids=[ITER_ID],
    root_hypothesis_id="H_ROOT",
)
template["hypotheses"] = []
for identifier, parent, mechanism in [
    ("H_ROOT", None, "Public momentum/pullback andriskfeedback attribution"),
    ("H_ENTRY", "H_ROOT", "Sameleaderinformation; timing compared withmomentum/breakout"),
    ("H_GEOMETRY", "H_ROOT", "Tightstop,reentry andpartial/righttail tradeoff"),
    ("H_FEEDBACK", "H_ROOT", "Closedfeedback andcausalmonthlyrisk budget"),
]:
    template["hypotheses"].append(
        dict(
            hypothesis_id=identifier,
            parent_hypothesis_id=parent,
            economic_mechanism=mechanism,
            universe_or_asset_class=(
                "Evidence-supporteddateseurityepisodes; broadcoveragecurrentlyunproven"
            ),
            horizon="Intradayentry andmulti-dayswing; markettimestamps",
            data_modality="Actualraw/actionconsistentbars andorderedexecutioninputsrequired",
            portfolio_construction="Continuous20ksettledcash, integerstockshares, gross<=1",
            execution_style="Knowncompletedbarstop/stoplimit orders; gap/ambiguitybounds",
            universe_selection="point_in_time",
            role="research",
            promotion_eligible=False,
        )
    )
groups = {
    "H_ENTRY": ["C_MOM", "C_BREAK", "M_REF"],
    "H_GEOMETRY": ["M_WIDE", "M_REENTRY", "M_PARTIAL"],
    "H_FEEDBACK": ["M_FEEDBACK", "F_MONTHLY"],
}
template["branch_quotas"] = [
    dict(branch_id=hyp, hypothesis_id=hyp, min_candidates=len(ids), max_candidates=len(ids))
    for hyp, ids in groups.items()
]
template["candidate_blueprints"] = []
for cand in inventory:
    group = next(g for g, ids in groups.items() if cand["id"] in ids)
    template["candidate_blueprints"].append(
        dict(
            candidate_id=cand["id"],
            hypothesis_id=group,
            branch_id=group,
            child_iteration_id=ITER_ID,
            method_variant=json.dumps(cand),
            factor_variant="Sameacceptedcausalprice/leader/supportinputs",
            archive_descriptors={"mechanism_family": group},
            model_training=False,
            promotion_eligible=False,
        )
    )
ops = [
    "candidate_generation",
    "factor_evaluation",
    "deterministic_backtest",
    "resource_allocation",
    "archive_update",
    "reporting",
]
template["visibility_partitions"] = [
    dict(partition_id="seen_2024_2025", kind="development", allowed_operations=ops),
    dict(partition_id="seen_2026_report", kind="forward", allowed_operations=["reporting"]),
    dict(partition_id="future_unavailable", kind="frozen_oos", allowed_operations=["reporting"]),
]
template["exposure_budgets"] = dict(
    candidate_budget=8,
    cumulative_trial_exposure_budget=120,
    prior_effective_trial_count=8147,
    effective_trial_counting="candidate_count",
)
template["qd_archive"].update(
    quality_metric="development_paired_net_contribution_diagnostic_only",
    quality_partition_id="seen_2024_2025",
)
template["candidate_promotion_policy"].update(
    development_partition_id="seen_2024_2025", development_fold_ids=["seen_2024", "seen_2025"]
)
template["expensive_resource_rungs"] = []
template["promotion_evidence"] = None
dump(CAMP / "research-campaign-contract.json", template)
dump(
    BASE / "trial-exposure-policy.json",
    dict(
        prior_exact_effective_exposure=None,
        legacy_contract_declared_unverified_count=8147,
        legacy_source=(
            "eq_role_source_20261013 campaign; copiedconservative bookkee"
            "pingvalue notverifiedglobalcount"
        ),
        new_economic_exposure=0,
        candidate_definitions=8,
        max_enumerated_streams=120,
        all_nonselectable=True,
        seen_windows_not_reset=True,
        DSR_PBO_SPA_claims=False,
    ),
)

sources = [
    (
        "ML_defined_stop",
        (
            "Martin's2024guestessay explicitly definesstops beforeentry; "
            "tight/reentry adaptation must use thenknownpricelevels."
        ),
        "https://tradingresourcehub.substack.com/p/martin-luk-283-usic-2024-key-lessons",
        "practitioner_first_person",
        "2025-02-01",
        MARTIN / "sources/guest2024-original.html",
        "I define my stop before entering a trade",
    ),
    (
        "CF_cut_risk",
        (
            "Flanders2024guestessay says he cutsize aftertradesstoppedwor"
            "king; monthly5%spreadsheet isnot an ex-postNAVfloor forsimul"
            "ation."
        ),
        "https://tradingresourcehub.substack.com/p/christian-flanders-usic-2024-outperformance",
        "practitioner_first_person",
        "2025-01-18",
        BASE / "sources/comparison-firstperson-01.json",
        "started dramatically cutting size when my trades stopped working",
    ),
    (
        "CF_actual_slippage",
        (
            "Flanders2025review disclosesplannedCSIQbuystop25.51/stop25.1"
            "0 butexecuted26.28 plusduplicatedentry; plannedstop-risk isn"
            "otactualrisk."
        ),
        "https://tradingresourcehub.substack.com/p/christian-flanders-2025-review",
        "practitioner_first_person",
        "2026-01-17",
        BASE / "sources/comparison-firstperson-01.json",
        "My order was executed at $26.28",
    ),
    (
        "USIC_CF_2024",
        (
            "Official2024stock20k+standings listChristianFlanders433.5%, "
            "distinctfromround433inJanuaryguestarticle."
        ),
        (
            "https://financial-competitions.com/previousstandings/2025/2/"
            "12/december-final-standings-2024"
        ),
        "competition_official",
        "2025-02-12",
        BASE / "sources/comparison-primary-method-reads.json",
        "Christian Flanders + 433.5%",
    ),
    (
        "SCHW_current_PDT",
        (
            "SchwabJuly2026officialupdate says itstoppedcountingdaytrades"
            "June8; old25kPDTdocs areconflicting/stale andnotcurrentaccou"
            "ntpermission."
        ),
        "https://www.schwab.com/learn/story/schwab-changes-rules-around-day-trading",
        "broker_official_docs",
        "2026-07-06",
        MARTIN / "sources/schwab-current-rules-discovery.json",
        "Schwab no longer counts day trades in margin accounts",
    ),
]
cards = []
direction_sources = []
for cid, claim, url, typ, published, snapshot, quote in sources:
    fetched = datetime.fromtimestamp(snapshot.stat().st_mtime, UTC).isoformat()
    if snapshot.suffix == ".json":
        text = plaintext(snapshot)
        target = BASE / "sources/plain" / (snapshot.stem + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        snapshot = target
    body = snapshot.read_text()
    normal = re.sub(r"<[^>]+>", " ", body)
    assert quote in normal, (cid, "sourcequotationabsent")
    common = dict(
        claim_id=cid,
        claim=claim,
        source_type=typ,
        source_url=url,
        accessed_at="2026-10-13",
        fetched_at=fetched,
        fetch_timestamp_kind=(
            "Savedactualtool/directentity capture upperbound; originalHTTPdate notexposedforwebtool"
        ),
        snapshot_derived_at=NOW,
        verification_status="source_verified",
        source_sha256=binding(snapshot)["sha256"],
        quote=quote,
        applies_to=["public_practitioner_method"],
        impact_on_spec=(
            "Bindsourcefidelity andcontroller/executionboundary; noresourceauthorization"
        ),
        limitations=(
            "Publicfirstpersonrecords areselected andnotfullbrokerledger;"
            " officialcontestreturns do notisolatecausalmethodprofit."
        ),
    )
    cards.append(common)
    direction_sources.append(
        dict(
            claim_id=cid,
            claim=claim,
            url=url,
            source_type=typ,
            published_or_updated_at=published,
            market_and_period="USlistedstocks, public2024/2025cases andcurrent2026brokercontext",
            applicability="Conditionalpairedmethod research only",
            limitations=common["limitations"],
            independent_replication=(
                "No completeindependentprivateaccountreplication found; oldSt"
                "ocksInPlay isdifferentmechanism andretainednegativeevidence"
            ),
            fetched_at=fetched,
            snapshot_path=binding(snapshot)["path"],
            sha256=binding(snapshot)["sha256"],
            source_card_path=f"reports/harness/source_cards/{ITER_ID}.jsonl",
        )
    )
card_path = ROOT / f"reports/harness/source_cards/{ITER_ID}.jsonl"
card_path.parent.mkdir(parents=True, exist_ok=True)
card_path.write_text("".join(json.dumps(card) + "\n" for card in cards))
queries = [
    dict(
        query=(
            "ReusedactualRootMartinrecords plus boundedfirstperson/offici"
            "alUSIC comparison andcurrentSchwab rules"
        ),
        searched_at=NOW,
        opened_urls=[s["url"] for s in direction_sources],
    )
]
dump(
    ITER / "source-query-manifest.json",
    dict(
        queries=queries,
        receipts=[
            binding(BASE / "sources/comparison-firstperson-01.json"),
            binding(BASE / "sources/comparison-primary-method-reads.json"),
            binding(BASE / "sources/comparison-official-reads-and-method-leads.json"),
        ],
        transport=(
            "Existingactualwebreads; localplaintext isrenderedtoolcapture, notrawHTTPorfullvideo"
        ),
    ),
)
dump(
    ITER / "knowledge-baseline.json",
    dict(
        as_of=NOW,
        source_reuse=[
            binding(
                ROOT
                / "reports/research/iterations/h20260923_13_orb_stocks_in_play/decision-record.md"
            ),
            binding(
                ROOT
                / (
                    "reports/research/program/day-goal-20261013/joint-daily-metho"
                    "d/local-input/package-manifest.json"
                )
            ),
        ],
        legacy_window_exposure="2023Sep18..2026Sep17alreadyseen; notreset",
        no_new_modality_features=True,
        ML_training=False,
        unknown_prior_effective_trial_count=True,
    ),
)
review = dict(
    schema_version=3,
    iter_id=ITER_ID,
    reviewed_at=NOW,
    decision="proceed",
    objective=plan["object"],
    target_regime_and_horizon=(
        "Intradaycausalpullbacks andmulti-dayswings, 2024–2025seenhis"
        "tory, cash20k; casefidelitybeforegeneralization"
    ),
    existing_solution_comparison=(
        "Martin support/reentry/righttail differs fromold5minuteStock"
        "sInPlayflatatclose; Flandersfeedback paired onunchangedoppor"
        "tunitytape, notanothernameforindependentalpha"
    ),
    remaining_evidence_gap=(
        "Raw/action/minuteversionanddatedepisode/terminalcashinputnot"
        "yetaccepted; selectedpublicexamplesarenotinvestablecohort; m"
        "issingthemeoriginaldiscretion retained"
    ),
    negative_experiments_checked=(
        "OldSIP01/02refutedremainclosed; originaldecision records gap"
        "-throughstop andentry-barambiguity defects; notrefutation of"
        "Martin"
    ),
    cost_and_execution_assumptions=plan["portfolio_and_execution"]["costs"],
    stop_condition=plan["resource_and_stopping"]["input_stop"],
    queries=queries,
    sources=direction_sources,
    source_evidence_bindings=[
        dict(
            claim_id=s["claim_id"],
            source_card_path=s["source_card_path"],
            snapshot_path=s["snapshot_path"],
            snapshot_sha256=s["sha256"],
            source_url=s["url"],
        )
        for s in direction_sources
    ],
    query_manifest=binding(ITER / "source-query-manifest.json"),
    pre_iteration_knowledge_baseline=binding(ITER / "knowledge-baseline.json"),
    cheapest_decisive_test=dict(
        action=(
            "Onindependentlyacceptedraw/actioninputs, checkpubliccasecloc"
            "kfidelity then pairedwholecashbookcontrasts; nevercomputeuna"
            "uthorizedeconomics"
        ),
        pass_condition=(
            "Legalepisode/orderedexecutionchain supportsqualified paired "
            "methoddiagnostic; economicacceptance requireswholecashandcov"
            "erage"
        ),
        falsification_condition=(
            "Specificcasescannotbejoined acrossbar/actionbasis orstop/fil"
            "lcannotbeidentified; stopsaffectedclaim, notglobalpractition"
            "ermechanism"
        ),
        max_compute_minutes=120,
    ),
)
dump(ITER / "direction-review.json", review)

candidate_manifest = dict(
    schema_version=3,
    iter_id=ITER_ID,
    research_role="market_component_method",
    manifest_type="generic_candidate_family_v1",
    generated_before_backtest=True,
    generated_at=NOW,
    campaign_id=ITER_ID,
    promotion_eligible=False,
    spec_hashes={},
    candidates=[],
)
for cand in inventory:
    group = next(g for g, ids in groups.items() if cand["id"] in ids)
    row = dict(
        candidate_id=cand["id"],
        research_role="market_component_method",
        promotion_eligible=False,
        spec_path=None,
        campaign_id=ITER_ID,
        hypothesis_id=group,
        branch_id=group,
        child_iteration_id=ITER_ID,
        definition=cand,
        input_status="dependency_pending_actual_raw_action_episode_acceptance",
        scientific_plan=binding(BASE / "scientific-plan.json"),
        input_readiness=binding(BASE / "input-readiness.json"),
        data_contract="singlevintage_raw_action_marketclock_v1",
        feature_contract="causal_leader_support_completedbar_v1",
        label_contract="actualcash_share_eventledger_v1",
        validation_contract="seen2024_2025_nonselectable_v1",
        cost_contract="20bpsprimary_10_40diagnostic_everyfill_v1",
        benchmark_contract="sameepisode_EW_SPY_QQQ_sector_cash_BIL_best_v1",
        ablation=cand["role"],
        fallback="Noentryifunknown; retainheldassetrights; unknownNAVnotzero",
    )
    candidate_manifest["candidates"].append(row)
dump(ITER / "candidate-manifest.json", candidate_manifest)
streams = []
for cand, bps, bound, order in itertools.product(
    inventory,
    [10, 20, 40],
    ["adverse_first", "favourable_first"],
    ["stop_market", "stop_limit_0_25R"],
):
    streams.append(
        dict(
            candidate_id=cand["id"],
            cost_bps=bps,
            sequencing=bound,
            order_style=order,
            extra_latency_bars=0,
            promotion_eligible=False,
        )
    )
for cid, bps, bound, order in itertools.product(
    ["M_REENTRY", "F_MONTHLY"],
    [10, 20, 40],
    ["adverse_first", "favourable_first"],
    ["stop_market", "stop_limit_0_25R"],
):
    streams.append(
        dict(
            candidate_id=cid,
            cost_bps=bps,
            sequencing=bound,
            order_style=order,
            extra_latency_bars=1,
            promotion_eligible=False,
        )
    )
assert len(streams) == 120
dump(
    ITER / "evaluation-cell-manifest.json",
    dict(
        generated_before_execution=True,
        selection_allowed=False,
        cells=streams,
        max_new_return_streams=120,
        actual_return_streams=0,
    ),
)
dump(
    BASE / "review-bindings.json",
    dict(
        author="f9add224-744b-471c-b812-c43cc179fa38",
        plan=binding(BASE / "scientific-plan.json"),
        casebook=binding(MARTIN / "casebook.json"),
        rule_versions=binding(MARTIN / "rule-versions.json"),
        input_probe=binding(MARTIN / "local-case-input-probe.json"),
        input_readiness=binding(BASE / "input-readiness.json"),
        request_scope=binding(BASE / "input-and-request-scope.json"),
        comparison=binding(BASE / "method-comparison.json"),
        source_cards=binding(card_path),
        campaign=binding(CAMP / "research-campaign-contract.json"),
        candidate_manifest=binding(ITER / "candidate-manifest.json"),
        evaluation_cells=binding(ITER / "evaluation-cell-manifest.json"),
        direction=binding(ITER / "direction-review.json"),
        source_type_diff=binding(BASE / "source-type-interface-diff.json"),
    ),
)
print(
    json.dumps(
        {
            "study_id": ITER_ID,
            "candidate_count": len(inventory),
            "planned_stream_count": len(streams),
            "new_economic_exposure": 0,
            "review_bindings": binding(BASE / "review-bindings.json"),
        }
    )
)
