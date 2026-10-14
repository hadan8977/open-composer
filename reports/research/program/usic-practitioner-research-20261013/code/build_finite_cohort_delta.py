"""Freeze affected population delta and bounded source/input implementation."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq"
resource.setrlimit(resource.RLIMIT_CPU, (20, 21))


def bind(p):
    return {"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def read(p):
    return json.loads(p.read_text())


def save(name, obj):
    p = OUT / name
    assert not p.exists(), "preserve_existing_version"
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    return bind(p)


def main():
    assert os.sched_getaffinity(0) == {0}
    OUT.mkdir(exist_ok=True)
    oldplan = BASE / "revisions/v2/scientific-plan.json"
    oldcontract = BASE / "revisions/v2/state-and-ledger-contract.json"
    rootdecision = BASE / "continuity-source-locator/root-scope-and-resource-decision.json"
    web = BASE / "continuity-source-locator/root-web-evidence.json"
    decision = read(rootdecision)
    assert decision["allocation"]["requests_max"] == 48
    population = {
        "source": "SEC NPORT-P QQQ holdings2023-09-30; entire actual reported issue roster",
        "role": "Finite large-cap growth-stock public-rule adaptation and raw bridge",
        "eligibility_scope": (
            "Reported EC issue candidates intersect the unchanged v2 date"
            "d US common-stock eligibility evidence; unknown class/mappin"
            "g retained"
        ),
        "not_QQQ_ETF_trading": True,
        "not_Martin_main_high_ADR_smallcap_theme_opportunity_set": True,
        "historical_publication_claim": False,
        "historical_first_visible": None,
        "unknown_firstvisible_does_not_block_current_vintage_components": True,
        "freeze": (
            "Save full parsed issue roster and identity SHA before readin"
            "g any new prices; hash-order EC issue keys before symbol res"
            "olution"
        ),
        "diagnostic": (
            "First25 unique EC issues by SHA256(USIC-RAW-BRIDGE-20261013|"
            "CUSIP|ISIN), no resample for unknown mapping/data/eligibilit"
            "y"
        ),
        "date_scope": (
            "Earliest40 sessions2024-01-02..2024-02-28 source only; selec"
            "ted25 daily raw/all to2025-12-31 for coverage/causal-source-"
            "fit only"
        ),
        "identity": (
            "NPORT actual ticker if provided; otherwise source-dated Dece"
            "mber2023 SEC FTD sameCUSIP symbol candidate, not a validity "
            "interval"
        ),
        "no_current_membership_or_future_completeness_filter": True,
        "no_price_returns_weights_PnL_for_cohort_or_diagnostic_selection": True,
        "unknown_and_terminal_issues": (
            "Keep roster, absentmapping and action/held rights; never zero/remove affectedassets"
        ),
        "signal_information": (
            "UnchangedADR/momentum/EMA/ADV thresholds; actual missing see"
            "d/episode/rawbasis prevents stronger qualification, legal co"
            "nditionalcomponents retained"
        ),
        "EMA_diagnostic": (
            "Source-window recursion explicitly labelled; full v2 first-e"
            "pisode seed not certified by a limited source-start date"
        ),
        "full_study": (
            "2024-2025 all accepted historical cohort, 8 definitions/120c"
            "ells/102pairs; diagnostic25x40 not economic population"
        ),
        "economic_information_decision": (
            "Reviewer judges full route/opportunity information by covera"
            "ge, causal qualification and source fit; never diagnostic Pn"
            "L or lowered thresholds"
        ),
        "generalization": (
            "Neither positive nor negative results establish/refute Marti"
            "n's all-market/highADR/smallcap discretion or privatecontest"
            " return"
        ),
        "public_cases_Flanders": "Keep independent forensic evidence; selectedwinners not universe",
    }
    contract = read(oldcontract)
    contract["version"] = "v3_finite_QQQ_population_delta_only"
    contract["features_and_pool"]["population_scope_delta"] = population
    cb = save("state-and-ledger-contract.json", contract)
    plan = read(oldplan)
    plan["version"] = "v3_finite_large_growth_population_adaptation"
    plan["object"] = population["role"]
    for k in ("selection_and_information", "portfolio_and_execution"):
        plan[k]["definition"] = cb
    plan["selection_and_information"]["population_scope_delta"] = population
    plan["validation_and_depth"]["matched_comparisons"]["definition"] = cb
    plan["authoritative_state_and_ledger_contract"] = cb
    plan["supersedes_unexecuted_definition"] = bind(oldplan)
    plan["revision_trigger"] = bind(rootdecision)
    plan["resource_and_stopping"]["economic_allocation_proposal"] = {
        "finite_source_bridge_reserved": [48, 65011712, 120],
        "economic_allocated": 0,
        "full_pool_next_condition": decision["delegation"]["followon"],
        "full_pool_information_not_PnL_screen": True,
    }
    pb = save("scientific-plan.json", plan)
    inventory = plan["candidate_inventory"]
    assert inventory == read(oldplan)["candidate_inventory"]
    for key in (
        "opportunity_tape_and_epochs",
        "candidate_state_table",
        "orders_and_R1_quantity",
        "cash_rights_and_R3_feedback",
        "R4_path_scenarios_and_pairing",
    ):
        assert contract[key] == read(oldcontract)[key]
    source_prefix = "https://www.sec.gov/Archives/edgar/data/1067839/000175272423269960/"
    common = {
        "symbols": "FROZEN_DIAGNOSTIC_SYMBOLS",
        "timeframe": "1Day",
        "start": "2023-07-01T00:00:00Z",
        "end": "2026-01-01T00:00:00Z",
        "feed": "sip",
        "asof": "-",
        "sort": "asc",
        "currency": "USD",
        "limit": 10000,
    }
    objects = []
    for adjustment in ("raw", "all"):
        objects.append(
            {
                "id": "diagnostic_daily_" + adjustment,
                "path": "/stocks/bars",
                "params": {**common, "adjustment": adjustment},
                "max_pages": 2,
                "per_page_byte_cap": 1572864,
            }
        )
    objects.append(
        {
            "id": "diagnostic_alltype_actions",
            "path": "https://data.alpaca.markets/v1/corporate-actions",
            "params": {
                "symbols": "FROZEN_DIAGNOSTIC_SYMBOLS",
                "start": "2023-01-01",
                "end": "2026-10-13",
                "data_quality": "all",
                "region": "us",
                "sort": "asc",
                "limit": 1000,
            },
            "max_pages": 2,
            "per_page_byte_cap": 1572864,
        }
    )
    for adjustment in ("raw", "all"):
        objects.append(
            {
                "id": "SPY_BIL_daily_" + adjustment,
                "path": "/stocks/bars",
                "params": {**common, "symbols": "SPY,BIL", "adjustment": adjustment},
                "max_pages": 1,
                "per_page_byte_cap": 1572864,
            }
        )
    sb = save(
        "input-scope.json",
        {
            "root_decision": bind(rootdecision),
            "scientific_plan": pb,
            "contract": cb,
            "source_form_requests": [
                {"url": source_prefix + "primary_doc.xml", "entity_cap": 2097152},
                {
                    "url": source_prefix + "xslFormNPORT-P_X01/primary_doc.xml",
                    "entity_cap": 2097152,
                    "only_if": "firstrepresentation200unparsed_or404; no403/429retry",
                },
            ],
            "source_pool": (
                "OriginalMartin35/40; atmost2 extra actualHTTPcalls, sourceby"
                "tes outside market reservation"
            ),
            "local_identity_files": [
                "data/sec_ftd/cnsfails202312a.parquet",
                "data/sec_ftd/cnsfails202312b.parquet",
            ],
            "local_identity_columns": ["settlement_date", "cusip", "symbol", "description"],
            "FTD_point_is_not_episode_interval": True,
            "market_prefix_objects": objects,
            "minute_objects": (
                "40calendar-derived RTH days, raw,sip,asof-,asc,limit10000; f"
                "ixed hash-first issues' candidate symbols, no resampling"
            ),
            "minute_day_max_pages": 1,
            "minute_entity_cap": 1310720,
            "total_request_cap": 48,
            "total_entity_byte_cap": 65011712,
            "pages_not_guaranteed_sufficient": True,
            "initial_unused19_scope_unchanged": True,
            "CPU_total_reserved": 120,
            "oneCPU_affinity0": True,
            "memory_cap_MiB": 512,
            "whole_source_or_entity_failure": (
                "Retain allpartial/failedrequests; never extend quota or trade on an unparsedroster"
            ),
            "economic_trials_fits_orders": 0,
        },
    )
    delta = save(
        "affected-scientific-delta.json",
        {
            "as_of_utc": datetime.now(UTC).isoformat(),
            "root_decision": bind(rootdecision),
            "root_web_evidence": bind(web),
            "baseline_plan": bind(oldplan),
            "baseline_contract": bind(oldcontract),
            "plan": pb,
            "contract": cb,
            "input_scope": sb,
            "population": population,
            "unchanged_sections_verified": True,
            "eight_definitions": 8,
            "cells": 120,
            "pairs": 102,
            "old_seen_dev_report_exposure_preserved": True,
            "new_economic_trials": 0,
            "economic_admission": False,
            "delta_only_review_not_nine_eleven_template": True,
        },
    )
    entry_paths = [
        rootdecision,
        OUT / "scientific-plan.json",
        OUT / "state-and-ledger-contract.json",
        OUT / "input-scope.json",
        OUT / "affected-scientific-delta.json",
        BASE / "code/acquire_finite_cohort_bridge.py",
        BASE / "code/acquire_components.py",
        ROOT / "open_composer/adapters/data/alpaca_snapshot.py",
        ROOT / "open_composer/market_sessions.py",
    ]
    entry = save(
        "implementation-entry-manifest.json",
        {
            "entry_bindings": [bind(p) for p in entry_paths],
            "factory": (
                "existing _stock_data_client/_load_env; credentials only afte"
                "r source freeze and actual review"
            ),
            "bounded_transport": (
                "Reuse accepted bounded_get and collect; no new controller/retry/test framework"
            ),
            "source_entry": (
                "taskset-c0 + freshmemory + run_capped512M + acquire_finite_cohort_bridge.py source"
            ),
            "market_entry": "sameadmission + acquire_finite_cohort_bridge.py market",
            "offline_entry": "acquire_finite_cohort_bridge.py offline; no network or credentials",
            "review_required": (
                "independent-delta-review.json: accepted affecteddelta, exact"
                "entry_bindings; reviewer != author"
            ),
            "resource": (
                "Beforeeachjob manualcumulative120 charge includingsetup/fail"
                "ures andfreshmemory, capjob45 orsmallerremaining. Noeconomic"
                "run."
            ),
        },
    )
    save(
        "affected-review-packet.json",
        {
            "delta": delta,
            "entry": entry,
            "author_self_approval": False,
            "economic_execution_admitted": False,
        },
    )
    state = read(BASE / "current-state.json")
    state.update(
        as_of_utc=datetime.now(UTC).isoformat(),
        status="finite_QQQ_delta_and_exact_source_entry_independent_review_pending",
        root_scope_resource_decision=bind(rootdecision),
        new_revision_review_packet=bind(OUT / "affected-review-packet.json"),
        reserved_followon=[48, 65011712, 120],
        allocated_economic_CPU=0,
        execution_active=True,
        next_action=(
            "ee affecteddelta/implementation acceptance, actualsourcefree"
            "ze/rawdiagnostic/inputacceptance; no intermediateRootreturn"
        ),
    )
    (BASE / "current-state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"packet": bind(OUT / "affected-review-packet.json"), "entry": entry}))


if __name__ == "__main__":
    main()
