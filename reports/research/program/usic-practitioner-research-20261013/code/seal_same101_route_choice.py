"""Summarize actual key coverage and stop the funded route; no economic calculation."""

from __future__ import annotations

import hashlib
import json
import os
import resource
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
V3 = BASE / "revisions/v3-finite-qqq"
ROUTE = V3 / "full-cohort-route"
OUT = ROUTE / "decisive-local-route-audit"


def bind(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, obj):
    assert not path.exists(), "retain_original_and_failed_evidence"
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (120, 121))
    data = json.loads((OUT / "actual-coverage.json").read_text())
    assert data["counts"]["unique_file_refs"] == 2232
    assert data["counts"]["original_file_refs"] == 2328
    assert data["counts"]["files_read"] == 2232
    assert data["counts"]["without_locator_retained"] == 4
    by_symbol = defaultdict(list)
    selected_files = []
    whole_hashes = 0
    out_of_month = []
    for checkpoint in data["file_checkpoints"]:
        path = ROOT / checkpoint["path"]
        assert bind(path)["sha256"] == checkpoint["sha256"]
        item = json.loads(path.read_text())
        whole_hashes += int(item.get("sha256") is not None)
        selected_files.append(
            {
                "path": item["path"],
                "bytes": item["bytes"],
                "mtime_ns": item["mtime_ns"],
                "whole_file_sha256": item.get("sha256"),
                "footer_sha256": item["footer_sha256"],
                "checkpoint": checkpoint,
            }
        )
        parts = Path(item["path"]).parts
        month = f"{parts[-3]}-{parts[-2]}"
        for rec in item["records"]:
            if rec["nonnull_unique_timestamp_keys"]:
                by_symbol[rec["symbol_candidate"]].append({**rec, "path": item["path"]})
                if rec["first_UTC"][:7] != month or rec["last_UTC"][:7] != month:
                    out_of_month.append(
                        {
                            "path": item["path"],
                            "symbol": rec["symbol_candidate"],
                            "first_UTC": rec["first_UTC"],
                            "last_UTC": rec["last_UTC"],
                        }
                    )
    shared_endpoints = []
    unique_counts = {}
    for symbol, files in sorted(by_symbol.items()):
        files.sort(key=lambda f: f["first_UTC"])
        subtotal = sum(f["nonnull_unique_timestamp_keys"] for f in files)
        for previous, current in zip(files[:-1], files[1:], strict=True):
            assert previous["last_UTC"] <= current["first_UTC"], (
                "nonpoint_range_overlap_requires_exact_selected_keys_not_approximate_count",
                symbol,
                previous["path"],
                current["path"],
            )
            if previous["last_UTC"] == current["first_UTC"]:
                key = current["first_UTC"]
                assert key[11:] == "00:00:00.000000000Z", "RTH_boundary_needs_clock_recheck"
                subtotal -= 1
                shared_endpoints.append(
                    {
                        "symbol": symbol,
                        "timestamp_UTC": key,
                        "previous_path": previous["path"],
                        "next_path": current["path"],
                        "proof": "Sorted unique extrema intersect at exactly one actual endpoint",
                    }
                )
        unique_counts[symbol] = subtotal
    actual_unique = sum(unique_counts.values())
    assert actual_unique == data["counts"]["unique_keys"] - len(shared_endpoints)
    global_key_proof = {
        "within_file_unique_keys_sum": data["counts"]["unique_keys"],
        "actual_global_unique_symbol_timestamp_keys": actual_unique,
        "cross_file_duplicate_occurrences": len(shared_endpoints),
        "duplicate_endpoint_evidence": shared_endpoints,
        "per_symbol_actual_unique_keys": unique_counts,
        "all_file_domains_disjoint_or_single_shared_midnight_endpoint": True,
        "RTH_global_unique_keys": data["counts"]["unique_RTH_minute_keys"],
        "midnight_cross_file_duplicates_not_RTH": True,
        "out_of_filename_month_extrema": out_of_month,
        "whole_file_SHA_count": whole_hashes,
        "footer_plus_selected_key_SHA_count": len(selected_files) - whole_hashes,
        "hash_scope_not_all_whole_file_SHA": True,
    }
    save(OUT / "global-key-verification.json", global_key_proof)
    counts = data["counts"]
    rows = data["records"]
    missing = [r for r in rows if not r["shards"]]
    diagnosed = [r for r in rows if r["shards"]]
    assert {r["symbol_candidate"] for r in missing} == {"SGEN", "ANSS", "EA", "WBA"}
    complete = sum(r["complete_RTH_key_sessions"] for r in diagnosed)
    key_days = sum(r["sessions_with_RTH_keys"] for r in diagnosed)
    queried = sum(r["queried_calendar_sessions"] for r in diagnosed)
    missing_grid = sum(r["missing_grid_keys_not_filled"] for r in diagnosed)
    caps = {
        "original_market_requests_bytes": [96, 134217728],
        "actual_market_used_requests_bytes": [63, 44065545],
        "remaining_unallocated_requests_bytes": [33, 90152183],
        "potential_new_bar_records_if_all33_are_limit10000_bar_pages": 330000,
        "hypothetical_unconditional_cache_key_replacement_pages_limit10000": (actual_unique + 9999)
        // 10000,
        "replacement_is_a_conditional_workload_not_minimum_required_study_input": True,
        "no_linear_extrapolation_from_25x40": True,
        "sparse_causal_acquisition_may_need_fewer_records_but_no_exact_original_route_proven": True,
        "public_source_used_cap": [37, 40],
        "economic_CPU_used_allocated": [0, 0],
        "wire_bytes_unknown_preserved": True,
        "no_new_HTTP_or_economic_trials": True,
    }
    save(OUT / "budget-reconciliation.json", caps)
    findings = [
        {
            "finding": "Real broad continuous cache exists; its actual selected keys are audited",
            "evidence": bind(OUT / "actual-coverage.json"),
            "consequence": "File presence is now replaced by actual selected-symbol/date coverage; "
            "it does not certify raw cash prices, valid historical shareclass or fills.",
        },
        {
            "finding": "The known minute producer requests ALL; raw-equivalence is not general",
            "evidence": bind(ROUTE / "source-link-probes/actual-result.json"),
            "consequence": "PCAR/GEHC cached and current ALL match on Jan2; ROST also changes "
            "vintage. Three nonneutral issues have six currentALL-high collisions versus "
            "different retained raw highs/cent-grid order references. TSLA matches on this "
            "packet only. A value-only daily-factor inverse is not an accepted raw bridge. "
            "This does not prove every possible time/action-aware inverse impossible.",
        },
        {
            "finding": "The frozen original EMA seed is first real issue-episode close",
            "evidence": bind(ROUTE / "source-link-probes/independent-actual-input-acceptance.json"),
            "consequence": "TSLA pre2016 is empty in one exact provider packet; no birth/history "
            "certificate follows. GEHC regular prefix grows126 to249 sessions without "
            "joining GEHCV; EMA50 changes-0.0129640858 and two gates remaintrue. No "
            "economic harmlessness is proven. Finite source window/burnin would require "
            "an explicit scientific delta and paired initialization sensitivity.",
        },
        {
            "finding": "Four unlocated names remain in the frozen101 roster",
            "evidence": bind(OUT / "same-issue-backfill-source-metadata.json"),
            "consequence": "Named backfill metadata contains EA and SGEN daily/ALL, no raw minute "
            "route. ANSS/WBA are absent from this namedmanifest only. SGEN Dec2023 terminal "
            "precedes Jan2024 cashseed, so its229 right is retained but not inherited by "
            "a nonexistent initial holding. EA/ANSS/WBA are not silently removed.",
        },
        {
            "finding": "Known retained raw entities cover bounded25x40, not a completed101 route",
            "evidence": bind(OUT / "retained-raw-route-metadata.json"),
            "consequence": "The13 selectedpubliccase objects have zero roster overlap. The47 "
            "bridge entities and3 probes are preserved with actual params; no authenticated "
            "full101 original-seed/raw-action/necessaryordered/held-rights route is available.",
        },
    ]
    result = {
        "as_of_UTC": datetime.now(UTC).isoformat(),
        "task": "USIC-PRACTITIONER-RESEARCH / v3 finite historical QQQ adaptation",
        "author": "f9add224-744b-471c-b812-c43cc179fa38",
        "decision": "stop_current_funded_v3_adaptation_before_economic_execution",
        "decision_status": "author_route_and_investment_recommendation_for_independent_acceptance",
        "why_this_complete_choice": "The decisive local audit confirms a real wide archive, "
        "but it supplies ALL keys rather than a certified original raw cash execution route. "
        "The fixed source-episode initialization and full population/action/ordered links "
        "remain unresolved. Further field-only requests would not jointly resolve those "
        "requirements. In this limited large-growth adaptation, use the preserved components "
        "and stop further input/economic allocation rather than consume the remaining33 "
        "requests on another nonunlocking probe. This is an opportunity-cost decision, "
        "not a market-wide impossibility proof or a rejection of Martin's mechanisms.",
        "actual_coverage": {
            "original_file_refs": 2328,
            "unique_files": 2232,
            "unique_file_bytes_not_HTTP_transfer": counts["unique_file_bytes"],
            "frozen_issues": 101,
            "located_issues": 97,
            "unlocated_issues_retained_NA": [r["symbol_candidate"] for r in missing],
            "target_rows": counts["target_rows"],
            "actual_global_unique_symbol_timestamp_keys": actual_unique,
            "within_file_duplicate_keys": counts["duplicate_keys"],
            "cross_file_duplicate_occurrences": len(shared_endpoints),
            "unique_RTH_minute_keys": counts["unique_RTH_minute_keys"],
            "queried_symbol_session_cells": queried,
            "cells_with_actual_RTH_keys": key_days,
            "complete_RTH_key_cells_not_valid_price_or_fills": complete,
            "missing_real_grid_keys_no_padding": missing_grid,
            "null_timestamp_rows": counts["null_timestamp_rows"],
            "RTH_nonminute_aligned_keys": counts["RTH_nonminute_aligned_keys"],
            "not_global_equity_absence_or_full_study_page_minimum": True,
        },
        "findings": findings,
        "route_choices": {
            "original_frozen_definition": "Not admitted: no complete original raw route proven; "
            "no network/economics request proposed from the audit.",
            "material_scientific_delta": "Possible separate finite-window EMA initialization "
            "with paired sensitivity, or another explicit input/execution objective. This "
            "alone does not fix raw cash basis, cent-grid/whole-share sizing, dividend/child "
            "rights, fullrank or ordered paths. No delta adopted or implemented here.",
            "chosen": "Stop the current fundedQQQ adaptation; retain the original8/120/102 "
            "definitions, 2024-25 seen status, actual publiccase/Flanders risk components "
            "and data/seed counterevidence. Main Martin highADR/smallcap opportunity set "
            "remains scientifically unresolved, not refuted.",
        },
        "valuable_alternative": {
            "existing_deliverable": "Actual public winners/losers/reentry/no-trade casebook and "
            "Flanders risk contrast with13 real components, plus bounded25x40 causal-price "
            "and ordered-parent geometry diagnostics; they test source/execution semantics "
            "without claiming a tradable winner-selected universe.",
            "next_economic_route_requires": "A genuinely raw, appropriately dated meaningful "
            "stock cohort with supported issue/action/necessaryordered links and an "
            "explicit approved initialization rule. Preserve the core matched entry/risk/exit "
            "and feedback question; do not silently substitute a9EMA shallow scan or ALL "
            "units as raw cash. Any new cohort/objective is a material scope decision.",
        },
        "retained_boundaries": {
            "definitions_cells_pairs": [8, 120, 102],
            "enumerated_duplicates": 6,
            "windows": [2024, 2025],
            "thresholds_seed_cohort_changed": False,
            "ADR5percent_added_as_filter": False,
            "old960_below_source_usual_ADR_preference_not_population_failure": True,
            "no_missing_rights_zeroed_no_future_completeness_filter": True,
            "historical_first_visible_unknown_not_blanket_price_blocker": True,
            "Rf_ETB_AVWAP_not_the_route_stop_reason": True,
            "old_LAYOUT_mismatch_not_rewritten": True,
            "no_private969_8percent_replication_claim": True,
        },
        "budget_reconciliation": bind(OUT / "budget-reconciliation.json"),
        "workflow_pass": "bounded_actual_source_and_input_components_only",
        "research_pass": False,
        "llm_contribution_pass": False,
        "ml_contribution_pass": False,
        "paper_ready_pass": False,
        "net_return": None,
        "backtests_started": False,
        "fits": 0,
        "paper_or_broker_activity_started": False,
        "new_paid_USD": 0,
        "independent_acceptance": None,
    }
    save(OUT / "result.json", result)
    source_paths = [
        OUT / "result.json",
        OUT / "global-key-verification.json",
        OUT / "actual-coverage.json",
        OUT / "calendar.json",
        OUT / "budget-reconciliation.json",
        OUT / "retained-raw-route-metadata.json",
        OUT / "same-issue-backfill-source-metadata.json",
        ROUTE / "identity-candidates.json",
        ROUTE / "cache-route-inventory.json",
        ROUTE / "source-link-probes/independent-current-layout-snapshot.json",
        ROUTE / "source-link-probes/independent-actual-input-acceptance.json",
        ROUTE / "source-link-probes/actual-manifest.json",
        V3 / "root-task-pool-continuation.json",
        V3 / "scientific-plan.json",
        V3 / "state-and-ledger-contract.json",
        V3 / "diagnostic-completion/independent-input-acceptance.json",
        BASE / "continuity-source-locator/producer-snapshots/fetch_sip_universe.py",
        BASE / "code/audit_same101_local_route.py",
        BASE / "code/audit_same101_local_route-attempt1.py",
        BASE / "code/audit_same101_local_route-attempt2.py",
        Path(__file__).resolve(),
    ]
    source_paths.extend(sorted(ROUTE.glob("audit-*-resource.txt")))
    source_paths.extend(sorted(ROUTE.glob("audit-*-fresh-memory.txt")))
    source_paths.extend([ROUTE / "audit-resource.txt", ROUTE / "audit-fresh-memory.txt"])
    save(
        OUT / "manifest.json",
        {
            "author": result["author"],
            "scope": "Complete decisive same101 local route choice",
            "bindings": [bind(p) for p in source_paths],
            "file_checkpoint_bindings": data["file_checkpoints"],
            "source_file_witnesses": selected_files,
            "source_file_hash_scopes_are_explicit": True,
            "full_price_rows_or_strategy_returns_replayed": False,
            "economic_execution_admitted": False,
        },
    )
    print(json.dumps(result["actual_coverage"]))


if __name__ == "__main__":
    main()
