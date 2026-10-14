"""Freeze the four scientific corrections without changing the old receipt paths."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from open_composer.research.campaign import validate_campaign_contract

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
REV = BASE / "revisions/v2"
OLD_ID = "usic_pullback_feedback_20261013"
NEW_ID = OLD_ID + "_v2"
OLD_ITER = ROOT / "reports/research/iterations" / OLD_ID
NEW_ITER = ROOT / "reports/research/iterations" / NEW_ID
OLD_CAMP = ROOT / "reports/research/campaigns" / OLD_ID
NEW_CAMP = ROOT / "reports/research/campaigns" / NEW_ID
NOW = datetime.now(UTC).isoformat()


def load(path):
    return json.loads(path.read_text())


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


old_review = BASE / "independent-plan-review.json"
old_plan = BASE / "scientific-plan.json"
contract = REV / "state-and-ledger-contract.json"
definitions = load(contract)["candidate_state_table"]
old_bindings = load(BASE / "review-bindings.json")
# v1 remains at every original path, including original canonical iteration.
preserved = {key: value for key, value in old_bindings.items() if isinstance(value, dict)}
for value in preserved.values():
    assert binding(ROOT / value["path"])["sha256"] == value["sha256"]
dump(
    REV / "v1-preservation.json",
    {
        "all_original_bound_paths_unchanged": True,
        "old_review": binding(old_review),
        "old_bindings": preserved,
    },
)

plan = copy.deepcopy(load(old_plan))
plan.update(
    study_id=NEW_ID,
    version="v2_R1_R4_complete_contract_for_independent_acceptance",
    supersedes_unexecuted_definition=binding(old_plan),
    revision_trigger=binding(old_review),
    authoritative_state_and_ledger_contract=binding(contract),
)
plan["selection_and_information"] = {
    "definition": binding(contract),
    "sections": ["features_and_pool", "opportunity_tape_and_epochs"],
    "first_phase_public_cases": (
        "Unchanged24 selected public decisions; not investablecohort or generalization sample."
    ),
    "missing_breadth": (
        "Leader rank/NAV remainsN/A if actual dated episode pool or market"
        "/cash chain isunidentified; legalpricecomponents remainpossible."
    ),
    "firstvisible": (
        "Historicalfirstseen unknown remainsnull; current-vintage hypothesis is explicitly limited."
    ),
    "source_limits": (
        "Thematic discretion, shorts/parabolicstyles and privatefullledger"
        " are not reproduced; no DLSA/Attention data/budget reuse."
    ),
}
roles = {item["id"]: item["role"] for item in load(old_plan)["candidate_inventory"]}
plan["candidate_inventory"] = [
    dict(item, role=roles[item["id"]], promotion_eligible=False) for item in definitions
]
plan["portfolio_and_execution"] = {
    "definition": binding(contract),
    "sections": [
        "orders_and_R1_quantity",
        "cash_rights_and_R3_feedback",
        "R4_path_scenarios_and_pairing",
    ],
    "starting_capital_USD": 20000,
    "gross_exposure_cap": 1.0,
    "entry_notional_cap": 0.35,
    "costs": (
        "10/20/40bps per actual/scenariofilledside;20primary. Everypartial"
        "/reentry charged; reservation doesnotreplaceactualcost."
    ),
    "quantity_frozen_before_fill": True,
    "afterfill_risk_target_reduction_in_this_scope": False,
    "settlement_claim": (
        "Explicit conservativeT+2houseproxy, not exacthistorical/currentSchwab permission."
    ),
    "intrabar_claim": "Two declaredpath scenarios, not globalNAVbounds.",
    "Schwab": load(old_plan)["portfolio_and_execution"]["Schwab"],
}
depth = plan["validation_and_depth"]
depth["matched_comparisons"] = {
    "definition": binding(contract),
    "section": "R4_path_scenarios_and_pairing.pairs",
    "common_opportunities_not_common_fills": True,
}
depth["controller_decision"] = (
    "PairedF_MONTHLY-M_FEEDBACK at matchedcost/path/order/extra0or1; reportreturn, "
    "underwater/loss-tail andmissedopportunities. Two pathscenarios are sensitivity, "
    "not bounds. Feedback-alone orcombinedcontrollers relativeM_REENTRY onlyextra0."
)
depth["uncertainty"] = load(contract)["R4_path_scenarios_and_pairing"]["statistics"]
plan["resource_and_stopping"]["economic_allocation_proposal"] = {
    "initial_input_decision_only": (
        "Original13objects up to32actualpages/64MiB; allocationnotgranted."
    ),
    "full7200_now_recommended": False,
    "full_pool_next_condition": (
        "Actual usefuldatedcohort/minutebreadth/actionterminal/orderedexec"
        "ution and8-definitionworkload estimate before additionalallocatio"
        "n."
    ),
    "same_shared_condition_upper_coreseconds": 7200,
    "economic_allocated": 0,
    "market_allocated": 0,
}
plan["resource_and_stopping"]["method_stop"] = (
    "Interpret pairedmethod failures onlyonidentifiedinput/adequatecoverage; "
    "no globalMartin/Flandersrefutation or privateaccountreplication. "
    "Cashunknown=>NAV/SharpeN/A; source/pricecomponents continue."
)
plan["validation_and_depth"]["metrics"] = [
    "cancel/submission-cap-breach/unfinanceable/missedtradecounts"
    if value == "cancel/sizeclipping/missedtradecounts"
    else value
    for value in plan["validation_and_depth"]["metrics"]
]
dump(REV / "scientific-plan.json", plan)

campaign = copy.deepcopy(load(OLD_CAMP / "research-campaign-contract.json"))
campaign.update(
    campaign_id=NEW_ID,
    created_at=NOW,
    child_iteration_ids=[NEW_ID],
    parent_iteration_ids=[OLD_ID],
    objective=(
        "R1-R4 amendment of the same eight unexecuted conditional methods;"
        " same120rowenvelope andoriginalsharedbudgets, notnewbudget/triala"
        "llocation."
    ),
)
for item in campaign["candidate_blueprints"]:
    item["child_iteration_id"] = NEW_ID
    item["method_variant"] = json.dumps(
        next(d for d in definitions if d["id"] == item["candidate_id"])
    )
dump(NEW_CAMP / "research-campaign-contract.json", campaign)
result = validate_campaign_contract(
    NEW_CAMP / "research-campaign-contract.json", ROOT, stage="pre-discovery"
)
dump(REV / "campaign-pre-discovery.json", result.model_dump(mode="json"))
assert result.status == "ok", result

manifest = copy.deepcopy(load(OLD_ITER / "candidate-manifest.json"))
manifest.update(
    iter_id=NEW_ID,
    campaign_id=NEW_ID,
    generated_at=NOW,
    supersedes_unexecuted_manifest=binding(OLD_ITER / "candidate-manifest.json"),
)
for item in manifest["candidates"]:
    item.update(
        campaign_id=NEW_ID,
        child_iteration_id=NEW_ID,
        definition=next(d for d in definitions if d["id"] == item["candidate_id"]),
        scientific_plan=binding(REV / "scientific-plan.json"),
        state_and_ledger_contract=binding(contract),
    )
dump(NEW_ITER / "candidate-manifest.json", manifest)

old_cells = load(OLD_ITER / "evaluation-cell-manifest.json")
cells = copy.deepcopy(old_cells["cells"])
for cell in cells:
    if cell["extra_latency_bars"] == 1 and cell["candidate_id"] == "M_REENTRY":
        cell["candidate_id"] = "M_FEEDBACK"
    tag = cell["order_style"]
    cell["legacy_enumeration_tag"] = tag
    if cell["candidate_id"] == "C_MOM":
        cell["order_style"] = "monthly_nextopen_market"
        cell["order_style_comparison_applicable"] = False
        cell["duplicate_order_tag"] = tag != "stop_market"
    else:
        cell["order_style_comparison_applicable"] = True
        cell["duplicate_order_tag"] = False
    cell["cell_id"] = ":".join(
        str(cell[k])
        for k in (
            "candidate_id",
            "cost_bps",
            "sequencing",
            "legacy_enumeration_tag",
            "extra_latency_bars",
        )
    )
    cell["path_scenario_not_global_bound"] = True
assert len(cells) == 120
assert sum(c["duplicate_order_tag"] for c in cells) == 6
assert {c["candidate_id"] for c in cells if c["extra_latency_bars"]} == {"M_FEEDBACK", "F_MONTHLY"}
dump(
    NEW_ITER / "evaluation-cell-manifest.json",
    {
        "generated_before_execution": True,
        "selection_allowed": False,
        "cells": cells,
        "supersedes_unexecuted_cells": binding(OLD_ITER / "evaluation-cell-manifest.json"),
        "enumerated_row_cap": 120,
        "structural_distinct_policy_ceiling": 114,
        "conservative_trial_charge_cap": 120,
        "actual_return_streams": 0,
    },
)

# Exact cell IDs make each attribution's matching conditions dereferenceable.
pairs = []
for question in load(contract)["R4_path_scenarios_and_pairing"]["pairs"]:
    allowed_delays = {0, 1} if question["question"] == "monthlybudget" else {0}
    for left in cells:
        if (
            left["candidate_id"] != question["A"]
            or left["extra_latency_bars"] not in allowed_delays
        ):
            continue
        for right in cells:
            if right["candidate_id"] != question["B"]:
                continue
            common_keys = ("cost_bps", "sequencing", "extra_latency_bars")
            if any(left[key] != right[key] for key in common_keys):
                continue
            if question["B"] == "C_MOM":
                # Its duplicated order tags are not two independent controls.
                if right["duplicate_order_tag"] or left["legacy_enumeration_tag"] != "stop_market":
                    continue
            elif left["legacy_enumeration_tag"] != right["legacy_enumeration_tag"]:
                continue
            pairs.append(
                {
                    "question": question["question"],
                    "A": left["cell_id"],
                    "B": right["cell_id"],
                    "common": question["common"],
                    "different": question["different"],
                    "actual_comparison_observed": False,
                }
            )
assert len(pairs) == 102
dump(
    NEW_ITER / "paired-comparison-manifest.json",
    {
        "cells": binding(NEW_ITER / "evaluation-cell-manifest.json"),
        "state_contract": binding(contract),
        "pairs": pairs,
        "pair_count": len(pairs),
        "extra_delay_attributions": ["monthlybudget"],
        "common_fills_required": False,
        "economic_results_seen": 0,
    },
)

# Reuse byte-identical verifiedsourcecards; no newfetch or timestamp.
old_cards = ROOT / f"reports/harness/source_cards/{OLD_ID}.jsonl"
new_cards = ROOT / f"reports/harness/source_cards/{NEW_ID}.jsonl"
new_cards.parent.mkdir(parents=True, exist_ok=True)
new_cards.write_bytes(old_cards.read_bytes())
old_query = load(OLD_ITER / "source-query-manifest.json")
direction = copy.deepcopy(load(OLD_ITER / "direction-review.json"))
direction.update(iter_id=NEW_ID, reviewed_at=NOW)
for source in direction["sources"]:
    source["source_card_path"] = str(new_cards.relative_to(ROOT))
# These are exact sourceopens/GETs ofknown URLs, not a fabricated submittedsearchphrase.
queries = [
    dict(
        query=source["url"],
        tool_action="exact_url_open_or_direct_GET",
        searched_at=source["fetched_at"],
        timestamp_kind="actualsavedcaptureupperbound",
        opened_urls=[source["url"]],
    )
    for source in direction["sources"]
]
dump(
    NEW_ITER / "source-query-manifest.json",
    {
        "queries": queries,
        "reused_receipts": old_query["receipts"],
        "correction": (
            "v1querywasintakedescription; v2explicitexactURLsourceopens, notnewwebsearch or request"
        ),
        "old_manifest": binding(OLD_ITER / "source-query-manifest.json"),
        "new_requests": 0,
    },
)
(NEW_ITER / "knowledge-baseline.json").write_bytes(
    (OLD_ITER / "knowledge-baseline.json").read_bytes()
)
direction.update(
    queries=queries,
    query_manifest=binding(NEW_ITER / "source-query-manifest.json"),
    pre_iteration_knowledge_baseline=binding(NEW_ITER / "knowledge-baseline.json"),
    source_evidence_bindings=[
        dict(
            claim_id=s["claim_id"],
            source_card_path=s["source_card_path"],
            snapshot_path=s["snapshot_path"],
            snapshot_sha256=s["sha256"],
            source_url=s["url"],
        )
        for s in direction["sources"]
    ],
)
direction["existing_solution_comparison"] += (
    " R1-R4 nowdefinedinoneboundstate/cashcontract; noactualfillquanti"
    "tyrollback or globalpathbounds."
)
dump(NEW_ITER / "direction-review.json", direction)

delta = {
    "old_review": binding(old_review),
    "old_plan": binding(old_plan),
    "new_plan": binding(REV / "scientific-plan.json"),
    "state_contract": binding(contract),
    "R1": (
        "Pre-submissionquantity,R0,reservations/limitfrozen; fillgaprisk r"
        "etained; noafterfillclip orinventedreject."
    ),
    "R2": (
        "8state definitions/pool/features/grids/activation/expiry/epochs/p"
        "riorityfrozen; C_MOMtagsdeclared6duplicates."
    ),
    "R3": (
        "Ownclosed-lotfeedback, fixedR0/allcosts/partialclosure, marks/mon"
        "thboundary/risk/cashreserves andconservativeT+2proxyfrozen; commo"
        "nopportunities notfills."
    ),
    "R4": (
        "TwoOHLCpaths are scenarios, notglobalbounds; unchanged120rows rea"
        "llocate24delaycells toM_FEEDBACK/F_MONTHLY forpairedmonthlytest."
    ),
    "old_paths_preserved": True,
    "old_case_source_and_input_hashes_unchanged": True,
    "request_scope_changed": False,
    "public_or_market_requests_new": 0,
    "new_economic_exposure": 0,
    "same_original_caps_consumption_carried": True,
}
dump(REV / "revision-delta.json", delta)
new_bindings = copy.deepcopy(old_bindings)
new_bindings.update(
    plan=binding(REV / "scientific-plan.json"),
    state_contract=binding(contract),
    revision_delta=binding(REV / "revision-delta.json"),
    prior_review=binding(old_review),
    source_cards=binding(new_cards),
    campaign=binding(NEW_CAMP / "research-campaign-contract.json"),
    candidate_manifest=binding(NEW_ITER / "candidate-manifest.json"),
    evaluation_cells=binding(NEW_ITER / "evaluation-cell-manifest.json"),
    paired_comparisons=binding(NEW_ITER / "paired-comparison-manifest.json"),
    direction=binding(NEW_ITER / "direction-review.json"),
)
dump(REV / "review-bindings.json", new_bindings)
print(
    json.dumps(
        {
            "review_bindings": binding(REV / "review-bindings.json"),
            "plan": binding(REV / "scientific-plan.json"),
            "contract": binding(contract),
            "v1_preserved": True,
            "new_requests": 0,
            "economic_exposure": 0,
        }
    )
)
