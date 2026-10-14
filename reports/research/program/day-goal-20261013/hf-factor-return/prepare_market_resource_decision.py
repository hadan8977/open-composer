# ruff: noqa: E501
"""Bind the real exhausted request gate and a concrete same-study continuation."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).parent
ROOT = Path.cwd()


def b(path):
    path = Path(path)
    return {
        "path": str(path.resolve().relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def cpu_receipt(name):
    path = P / name
    text = path.read_text()
    u = float(re.search(r"User time \(seconds\): ([0-9.]+)", text).group(1))
    s = float(re.search(r"System time \(seconds\): ([0-9.]+)", text).group(1))
    return {"receipt": b(path), "actual_user_plus_system_CPU": u + s}


def main():
    qa = json.loads((P / "market-input-coverage-and-resource-QA.json").read_text())
    ledger = json.loads((P / "market-input/market-request-ledger.json").read_text())
    plan = json.loads((P / "scientific-plan.json").read_text())
    review = json.loads((P / "independent-plan-review.json").read_text())
    acceptance = json.loads((P / "independent-complete-source-input-acceptance.json").read_text())
    assert review["verdict"] == "approve_deep_plan"
    assert acceptance["verdict"] == "accept_complete_conditional_source_input"
    assert len(ledger) == qa["market_HTTP_requests"] == 15
    assert all(r["status"] == 200 and r["body_complete"] for r in ledger)
    assert json.loads(Path(ledger[-1]["path"]).read_bytes())["next_page_token"]
    receipts = [
        cpu_receipt(n)
        for n in (
            "SPY-input-capture-resource.txt",
            "market-coverage-resource-QA-resource.txt",
            "market-coverage-resource-QA-final-format-resource.txt",
        )
    ]
    baseline = json.loads((P / "preparation-resource-continuation-01.json").read_text())
    resources = {
        "schema_version": 1,
        "as_of_utc": datetime.now(UTC).isoformat(),
        "pool": "HFcontinuation2000 source/inputQA only",
        "prior_resource_continuation": b(P / "preparation-resource-continuation-01.json"),
        "immutable_base_source_ledger": b(P / "continuation-preparation-resource-ledger.json"),
        "prior_measured_plus_allowance": baseline["cumulative_conservative_coreseconds"],
        "new_receipts": receipts,
        "new_resource_decision_write_and_review_setup_allowance": 10,
        "cumulative_conservative_CPU": baseline["cumulative_conservative_coreseconds"]
        + sum(r["actual_user_plus_system_CPU"] for r in receipts)
        + 10,
        "old500preparation_reservation_preserved": True,
        "old163_31actual_plus30review_reservation_preserved": True,
        "oldknown186_164505_and_unknown_preserved": True,
        "HF_economic_used": 0,
        "unique_economic_remaining": 7006.69,
        "newpaid_cloud_Hadan_orders": 0,
        "public_source_accounting": {
            "immutable_actual321_directledger": b(P / "continuation-source-request-ledger.json"),
            "extra_docs_receipt": b(P / "continuation-extra-resolution-source-ledger.json"),
            "extra_search_queries": 2,
            "extra_coauthor_page": 1,
            "continuation_public_request_units_known": 327,
            "initial_resolution21_plus6_new_units": 27,
            "resolution_unit_cap": 32,
            "inclusive_unit_cap": 400,
            "continuation_known_direct_bytes": 6_494_626_426,
            "extra_web_original_entity_bytes": None,
            "web_unknown_transfer_retained_not_zero_or_toolbytes": True,
        },
    }
    resources["remaining_of2000_before_new_independent_decision_review"] = (
        2000 - resources["cumulative_conservative_CPU"]
    )
    save(P / "preparation-resource-continuation-02.json", resources)
    last = json.loads(Path(ledger[-1]["path"]).read_bytes())
    request = {
        "schema_version": 1,
        "task_id": "DAY3-HF-FACTOR-RETURN",
        "author": "7b109880-ac40-447e-b2a6-f0ed1266ebac",
        "status": "proposed_not_authorized_no_new_market_call",
        "existing_complete_scientific_plan": b(P / "scientific-plan.json"),
        "complete_plan_review": b(P / "independent-plan-review.json"),
        "actual_market_ledger": b(P / "market-input/market-request-ledger.json"),
        "last_raw_page": b(Path(ledger[-1]["path"])),
        "cursor": {
            "source_field": "next_page_token",
            "value": last["next_page_token"],
            "semantics": "Opaque documentedcontinuation; notdecoded/guessed. Previously15pagesmusthash-reuse, no refetch.",
        },
        "endpoint": "https://data.alpaca.markets/v2/stocks/bars",
        "params_except_cursor": {k: v for k, v in ledger[0]["params"].items() if k != "page_token"},
        "proposed_new_additional_request_units": 120,
        "request_inventory": "Sequential documentednext_page_token responses for exactlysameSPY/raw/SIP15Min2016..2020 scope. Stop onendtoken, hardcount/byte/error, countallnewHTTPcalls/failures/redirects; no newassets/windows/endpoints orautomaticretry.",
        "prior_global_market_requests": 24,
        "prior_HF_market_requests": 15,
        "prior_HF_market_bytes": 1_314_927,
        "prior_global_market_bytes": 5_434_959,
        "same_global_byte_cap": 16_777_216,
        "same_remaining_byte_cap": 11_342_257,
        "new_direct_byte_allowance": 0,
        "new_USD_allowance": 0,
        "existing_route": "Normalappmarketdata credentials/client read-only, streaming body cap, no credentialoutput. No accountwrites/providerupgrade/cloud/Hadan.",
        "financial_or_scientific_changes": "None to20candidates, sourceviews/target,2016..2020fundedscope,c/h,clock,cashproxy,coststress,seenstatus or7006.69economiccap. Resourcecountamendment only needsRootactualgrant beforeuse; marketinput/feature/implementation/native/freshresource gates stillrequired.",
        "projection": qa["projection_not_actual"],
        "scope_activation": "This proposal/reviewerreceipt doesnotraise cap. Rootexternalresource decision mustbind thissame-study manifest; no currentcall after15bound.",
    }
    save(P / "remaining-market-request-proposal.json", request)
    bindings = {
        k: b(P / name)
        for k, name in {
            "plan": "scientific-plan.json",
            "contract": "execution-contract.json",
            "scientific_review": "independent-plan-review.json",
            "source_acceptance": "independent-complete-source-input-acceptance.json",
            "source_manifest": "complete-source-input-manifest.json",
            "market_coverage_QA": "market-input-coverage-and-resource-QA.json",
            "market_ledger": "market-input/market-request-ledger.json",
            "market_capture_loaded_code": "fetch_spy_intraday-v1-loaded.py",
            "market_capture_named_code": "fetch_spy_intraday.py",
            "market_QA_code": "market_coverage_resource_QA.py",
            "provider_official_docs": "resolution-sources/market-bars-official-docs-web.json",
            "provider_sourcecards": "market-sourcecards.jsonl",
            "extra_resolution_accounting": "continuation-extra-resolution-source-ledger.json",
            "primary_alternative_search": "resolution-sources/SPY-alternative-primary-search.json",
            "coauthor_research_page": "resolution-sources/SPY-coauthor-research-page.json",
            "request_proposal": "remaining-market-request-proposal.json",
            "resources": "preparation-resource-continuation-02.json",
        }.items()
    }
    body = {
        "schema_version": 1,
        "task_id": "DAY3-HF-FACTOR-RETURN",
        "author": plan["author"],
        "reviewer": plan["reviewer"],
        "as_of_utc": datetime.now(UTC).isoformat(),
        "decision": "preserve_complete_study_request_count_resource_reallocation_required",
        "scope": "Actual marketinput/resource decision after fullsource and scientificacceptance; not a completedcostedstudy or economicplanrejection.",
        "bindings": bindings,
        "actual_new_evidence": {
            "source_months": 300,
            "source_rows": 2_454_420,
            "source_raw_file_bytes": 6_515_013_371,
            "source_and_science_independent_acceptance": True,
            "SPY_market_successes": 15,
            "SPY_market_bytes": 1_314_927,
            "SPY_rows": 12_187,
            "regular_rows": 5096,
            "regular_days": 196,
            "complete_observed_regular_day_grids": True,
            "last_actual_local_date": "2016-10-11",
            "next_page_token_present": True,
            "frozen_expected_funded_days": 1259,
            "frozen_future_expected_days_missing": 1063,
            "observed_rows_per_request": [719, 925],
            "requested_limit": 10000,
            "real_failure": "Local15requesthardbound, providerallHTTP200. Notauth/ratequota/paywall orfullproviderdataunavailableclaim.",
        },
        "recommended_choice": "Authorize max120 additional sameSPY documentedpagination requests using existing11,342,257byte remainingbudget/$0newpaid, beforecontinuingtheunchangedcomplete2016..2020study. 82additional/~7.19MB is measured2016density extrapolation, notexactfullcount. 120hardcount addsdensity/error headroom, actualbodyboundstilldominates. No usebeforeRootresourcegrant.",
        "alternatives_considered": [
            {
                "choice": "Complete samefrozenstudy withrequestcount amendment",
                "judgment": "Preferred: full272 input/source/science已实际解锁，缺的是明确剩余SPYpagination，不是未知URL或作者代码。旧bytes足够的实测外推可信但非保证，additionneedonlycountnotnewpaid/bytes/economic.",
            },
            {
                "choice": "Shrinkapplicationtoavailable2016Jan-Oct",
                "judgment": "Rejected: only196of1259days andmissingfixed2019..2020comparison, changesregime/depth bydataconvenience; notcompleteprimary-returntest.",
            },
            {
                "choice": "FitfullFFindex andcallitSPYprofits",
                "judgment": "Rejected: sourceindexunits/formation/syntheticmeasurement != ETFcash/fills/actions. Statisticalmethod-only studywouldrequireexplicitpriority/claimchange andwouldnotsettlecurrent20kquestion.",
            },
            {
                "choice": "UseidentifiedauthoractualETFcode/pricepacket",
                "judgment": "NoactualfullSPYpacketidentified. ActualauthorDrive data hasetcFF6andproc1minfactorfiles; currentauthor/correspondingprimarypage/sourcequery onlypaper/OA/source272. Publisherknown403notretried, no13actualarchiveURLsclaimed. Notglobalabsenceproof, remaining5parserunitsneednotbefutilelyspent.",
            },
            {
                "choice": "Ifcountamendmentnotgranteddeferapplication",
                "judgment": "Preservemechanism/fullinput/acceptedplan, economicN/A, no Alpha/globalrefutation. Returnowner onrealresourcedecision soRootcancontinueactualfullwork/resourcetriage.",
            },
        ],
        "compute_suitability": {
            "source_geometry_upper_2019_train_rows": 96488,
            "float64_816training_matrix_bytes": 629873664,
            "uint8_816bin_matrix_bytes": 78734208,
            "memory_CPU_not_measured_by_fitting": True,
            "actual450CPU900MiB_maxHGB_calibration_only_after_fullgates": True,
            "economic_remaining_unchanged": 7006.69,
        },
        "resources": resources,
        "study_result": {
            "CAGR": None,
            "Sharpe": None,
            "terminal_NAV": None,
            "model_fits": 0,
            "source_method_statistical_evaluations": 0,
            "economic_runs": 0,
            "qualified_Alpha_lines": 0,
        },
        "workflow_pass": False,
        "research_pass": False,
        "ml_contribution_pass": False,
        "paper_ready_pass": False,
        "simulation_or_orders_started": False,
        "input_market_ready": False,
        "implementation_ready": False,
        "native_ready": False,
        "economic_execution_admitted": False,
        "not_global_mechanism_refutation": True,
        "review_requested": "独立审真实resourcechoice及actual15responses/params/coverage/projections，绑定整包并写independent-market-resource-decision-review.json；旧科学approval不重审/旧300源acceptance复用。仅重大requestcount决定，无新11表/Root中间通知/新request/fit/economic；当前owner完成具体handoff后nativefinishonce。",
    }
    save(P / "market-input-resource-decision.json", body)
    manifest = {
        "schema_version": 1,
        "task_id": plan["task_id"],
        "author": plan["author"],
        "scope": "Complete evidence-backed marketrequestgate decision, notfullcostedresult",
        "decision": b(P / "market-input-resource-decision.json"),
        "bindings": bindings,
        "actual_market_pages": qa["pages"],
        "reuse_independent300source_acceptance_no_repeatbulkhash": b(
            P / "independent-complete-source-input-acceptance.json"
        ),
        "economic_or_paid_ready": False,
    }
    save(P / "market-resource-decision-manifest.json", manifest)
    print(
        json.dumps(
            {
                "decision": b(P / "market-input-resource-decision.json"),
                "manifest": b(P / "market-resource-decision-manifest.json"),
                "request_proposal": b(P / "remaining-market-request-proposal.json"),
                "cumulative_preparation": resources["cumulative_conservative_CPU"],
            }
        )
    )


if __name__ == "__main__":
    main()
