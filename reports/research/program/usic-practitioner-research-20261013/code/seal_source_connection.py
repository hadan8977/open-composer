"""Seal bounded source metadata and a material scope choice; no market rows."""

from __future__ import annotations

import hashlib
import json
import math
import resource
from datetime import UTC, date, datetime
from pathlib import Path

from open_composer.market_sessions import us_equity_session_dates

ROOT = Path.cwd()
BASE = ROOT / "reports/research/program/usic-practitioner-research-20261013"
OUT = BASE / "continuity-source-locator"
NOW = datetime.now(UTC).isoformat()
resource.setrlimit(resource.RLIMIT_CPU, (20, 21))


def bind(path: Path) -> dict:
    content = path.read_bytes()
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def read(path: Path):
    return json.loads(path.read_text())


def write(name: str, obj):
    path = OUT / name
    assert not path.exists(), f"Preserve existing artifact: {path}"
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    return bind(path)


def main():
    assert not (OUT / "package-manifest.json").exists()
    first = read(OUT / "locator-result.json")
    recovery = read(OUT / "recovery/source-link-recovery.json")
    metadata = read(OUT / "metadata-summaries.json")
    anchor = read(OUT / "historical-anchor/anchor-source-assessment.json")
    before = read(BASE / "acquisition/cumulative-accounting-v2.json")
    accepted = {
        "actual_components": bind(BASE / "acquisition/independent-input-acceptance.json"),
        "issuer_diff": bind(
            BASE / "acquisition/supplements/gme-issuer/independent-source-diff-acceptance.json"
        ),
        "followon_not_allocated": bind(
            BASE / "acquisition/independent-followon-allocation-decision.json"
        ),
        "v2_scientific_review": bind(BASE / "revisions/v2/independent-plan-review.json"),
    }
    assert accepted["actual_components"]["sha256"] == (
        "3d2c134f51c06e7ac5b9b54b282d8e6275f204d50d27a41d54cf50efb3372aa9"
    )
    assert accepted["followon_not_allocated"]["sha256"] == (
        "e4e1c2aae355434a79e111be3769dd9911680e310358c8e2f1d4bb5a18555c15"
    )
    snapshots = OUT / "producer-snapshots"
    snapshots.mkdir(exist_ok=True)
    producers = []
    for name in ("scripts/fetch_sip_universe.py", "scripts/t21_intraday_ml/build_5m.py"):
        path = ROOT / name
        target = snapshots / path.name
        if target.exists():
            assert target.read_bytes() == path.read_bytes()
        else:
            target.write_bytes(path.read_bytes())
        producers.append({"original": bind(path), "snapshot": bind(target)})
    counts = {
        2024: sum(recovery["2024_month_file_counts"].values()),
        2025: sum(first["minute_archive_file_counts_2024_2025"].values()),
    }
    assert counts == {2024: 13416, 2025: 13416}
    selected_metadata = [
        item
        for item in metadata
        if any(
            word in item.get("binding", {}).get("path", "")
            for word in (
                "_COMPLETE_2023_2026",
                "_LAYOUT",
                "chinco-modern-adaptation",
                "parent-universe",
                "equity_book/panel/_manifest",
            )
        )
    ]
    bridges = write(
        "source-connection-evidence.json",
        {
            "as_of_utc": NOW,
            "scope": "Bounded metadata, filename and footer inspection; no column/row scan",
            "accepted_existing_components": accepted,
            "positive_archive_evidence": {
                "minute_shard_files": counts,
                "total2024_2025_files": sum(counts.values()),
                "monthly_shards_each": 1118,
                "2024_registered_alias": recovery["known_registered_alias"],
                "first2024_locator_status": "N/A_not_followed; repaired, never datazero",
                "schema": "symbol,timestamp[ns,UTC],OHLC,volume,trade_count,vwap",
                "completion_marker_declares": {"symbols": 13405, "rows2023_2026": 1279495748},
                "marker_rows_recounted": False,
                "eight_footer_reads_including_repeated_borrow_copy": True,
                "footer_ranges_are_not_per_symbol_continuity": True,
                "whole_price_file_hashes_claimed": False,
            },
            "source_basis_and_population": {
                "producer_bindings": producers,
                "acquisition_population": (
                    "GetAssetsRequest ACTIVE US_EQUITY, tradable at collection"
                ),
                "minute_adjustment": "all",
                "historical_dated_stock_membership_not_certified": True,
                "current_assets14402": "Snapshot2026-10-01, no2024-25 episode validity",
                "derived_universe27600": (
                    "Prior-monthclose>=5 Top600; dates2022-12..2026-09; no issue/type identity"
                ),
                "five_minute_grid": (
                    "Producer forwardfills empty OHLC from close, volume0, filled iff n_min==0"
                ),
                "partial_parent": (
                    "n_min1..4 not markedfilled; use actual minutes for v2 complete-parent rule"
                ),
                "READY_marker_not_ordered_execution_proof": True,
            },
            "specific_other_routes": [
                {
                    "route": "Known generic raw-data snapshot manifests",
                    "actual_example": recovery["source_item_metadata"][0],
                    "finding": (
                        "8daily instruments, adjustmentall,864sessions2020-07-27..202"
                        "3-12-29; no2024-25 raw1min"
                    ),
                },
                {
                    "route": "Chinco namedcohort50 cachedquote index",
                    "finding": (
                        "50symbols,2026-06-01..05,4187261quotes,422pages,October2026n"
                        "amedpopulation; mixedtypes"
                    ),
                    "use": (
                        "Real quote-source input, wrong period/type/population for v2"
                        "; no quote rows reread"
                    ),
                },
                {
                    "route": "Intraday codesign parent-universe",
                    "finding": (
                        "894current symbols; current_snapshot_forward_parent_only; hi"
                        "storical_membership_pit=false"
                    ),
                },
                {
                    "route": "Previously accepted JD wide daily archive",
                    "binding": bind(
                        ROOT
                        / (
                            "reports/research/program/day-goal-20261013/joint-daily-metho"
                            "d/local-input/archive-inventory.json"
                        )
                    ),
                    "finding": (
                        "Actual wide daily source exists; prior mixed-version/action/"
                        "episode issues retained; no rescan"
                    ),
                },
            ],
            "selected_metadata_bindings_and_fields": selected_metadata,
            "boundedness": {
                "filename_paths": first["filename_locator"]["files_listed"],
                "report_candidate_paths": first["report_metadata_locator"]["candidate_paths"],
                "initial_metadata_objects": first["metadata_objects_inspected"],
                "initial_metadata_bytes": first["metadata_content_bytes"],
                "uninspected_candidates": first["metadata_candidates_not_inspected"],
                "targeted_alias_recovery_no_whole_mount_scan": True,
                "mounted_filesystem_wire_bytes": None,
                "no_market_client_requests": True,
                "absence_of_complete_bound_route_not_global_absence": True,
            },
            "historical_identity_alternative": anchor,
        },
    )
    dates = us_equity_session_dates(date(2024, 1, 1), date(2025, 12, 31))
    years = {str(y): sum(d.year == y for d in dates) for y in (2024, 2025)}
    pilot = dates[:40]
    morning_slots = len(dates) * 50 * 90
    workload = write(
        "calendar-and-residual-workload.json",
        {
            "scope": "Calendar and input-size arithmetic only, no economic calculation",
            "calendar_source": bind(ROOT / "open_composer/market_sessions.py"),
            "calendar_sessions": years,
            "sessions_total": len(dates),
            "dense_Top50_first90minute_example": {
                "input_slots": morning_slots,
                "ideal_10000_limit_pages_if_all_present": math.ceil(morning_slots / 10000),
                "not_actual_row_count_or_opportunities": True,
                "not_lower_or_global_upper_bound": True,
                "held_assets_outside_dailyTop50_need_continued_prices": True,
                "verified_cache_may_reduce_HTTP": True,
            },
            "original_v2_workload_identity": {
                "definitions": 8,
                "cells": 120,
                "predeclared_duplicates": 6,
                "structural_ceiling": 114,
                "exact_pairs": 102,
                "actual_data_linked_continuous_streams": 0,
                "whole_run_CPU_RSS_estimate": None,
                "economic_implementation_native_input_resource_gate_complete": False,
            },
            "exact_missing_connections": [
                (
                    "Dated meaningful stock coverage roster -> issue/type/episode"
                    " -> date-valid source symbol"
                ),
                (
                    "Continuous raw price/volume and action-compatible basis for "
                    "entries, exits and held periods"
                ),
                (
                    "Held rights only where needed: entitlement, mark and actual "
                    "spendable receipt remain distinct"
                ),
                (
                    "Full chronological data-linked8/120/102 implementation plus "
                    "applicable native/input/resource gates"
                ),
            ],
            "not_blanket_blockers": [
                "Rf",
                "ETB for longcash",
                "historicalfirstseen",
                "PERMNO alone",
                "AVWAP when frozenEMA alternative applies",
            ],
            "component_validation_tranche_proposed_not_run": {
                "first_session": pilot[0].isoformat(),
                "last_session": pilot[-1].isoformat(),
                "sessions": len(pilot),
                "diagnostic_symbols_max": 25,
                "RTH_minute_slots_if_complete": 25 * len(pilot) * 390,
                "minute_requests_max": 40,
                "minute_entity_cap_each_bytes": 1310720,
                "daily_actions_rights_benchmark_requests_max": 8,
                "other_entity_cap_each_bytes": 1572864,
                "request_cap": 48,
                "entity_cap_bytes": 65011712,
                "diagnostic_subset_not_investment_cohort": True,
                "full_historical_population_remains_required_for_v2_ranking": True,
                "held_position_economic_run_from_this_tranche": False,
            },
        },
    )
    decision = write(
        "material-scope-decision.json",
        {
            "status": "Root_choice_required_not_adopted",
            "why_material": (
                "Historical population adaptation and new securities exceed f"
                "irst13scope; fullroute conditionalee grant unmet"
            ),
            "recommended": {
                "id": "HISTORICAL_STOCK_COHORT_RAW_BRIDGE",
                "population": (
                    "Entire eligible stock-issue roster in actual primary2023-09-"
                    "30 QQQ holdings record, frozenbefore marketvalues"
                ),
                "source": anchor["primary_url"],
                "not_ready": [
                    "fullroster",
                    "sourcepublication admissibility",
                    "datedsymbol/class/episode join",
                ],
                "identity_policy": (
                    "Preserve separateCUSIP/ISIN issues, unknown types/mapping an"
                    "d later terminal rights; no current-list or future-completen"
                    "ess filter"
                ),
                "study_claim": (
                    "Finitehistoricalgrowth-stock population public-rule adaptati"
                    "on; not all-market Top50/privateUSICaccount replication"
                ),
                "preserved_science": (
                    "Retain8methods/R1-R4/orders/costs/controller/120cells/102pai"
                    "rs and2024-2025 intended economic interval"
                ),
                "diagnostic_subset": (
                    "Once roster frozen, earliest25 by SHA256(USIC-RAW-BRIDGE-202"
                    "61013|CUSIP|ISIN); no return/data-completeness selection"
                ),
                "diagnostic_period": (
                    "Earliest40contiguous2024sessions; source/action/rawconnectio"
                    "n only, not controllerprofitability test or replacementinves"
                    "tmentcohort"
                ),
                "requested_conditional_raw_tranche": workload,
                "max_requests_bytes": [48, 65011712],
                "CPU_from_existing_Martin_preparation_max": 120,
                "economic_CPU_requested_now": 0,
                "after_tranche": (
                    "If actual raw/cache basis bridges and fullpopulation inputs/"
                    "workload/native gates pass, ee can evaluate remaining origin"
                    "al allocation; otherwise retain exact shortfall and stop"
                ),
                "stop": (
                    "Publication/episode ambiguity after boundedsource work, resp"
                    "onse/entity/page cap, unjoinable basis, missing fullcohort o"
                    "rdereddata; no retrybudget reset"
                ),
            },
            "alternative_weaker_claim": {
                "id": "RETROSPECTIVE_VENDOR_COVERED_DIAGNOSTIC",
                "basis": (
                    "Use actual currentACTIVE/all-adjusted cached population as e"
                    "xplicitretrospective provider-covered price diagnostics"
                ),
                "lost_claims": [
                    "historicalmembership",
                    "rawcashNAV without bridge",
                    "wholeUSICreplication",
                    "all-marketselection",
                ],
                "needs": (
                    "Root scope decision and independent affectedscientificdelta "
                    "before adopting; not recommended for fullcashbook claim"
                ),
            },
            "no_auto_adoption_allocation_or_run": True,
            "no_new_budget_spending_provider": True,
            "source35of40_remaining5_not_reset": True,
            "original_initial_unused19_not_repurposed": True,
        },
    )
    accounting = write(
        "cumulative-accounting.json",
        {
            "as_of_utc": NOW,
            "predecessor": bind(BASE / "acquisition/cumulative-accounting-v2.json"),
            "Martin_prior_CPU": before["Martin_global_CPU_used"],
            "new_locator_measured_CPU": 5.88,
            "new_alias_recovery_measured_CPU": 1.78,
            "metadata_setup_reads_lint_and_sealing_unknown_charge": 20,
            "historical_anchor_small_source_unknown_charge": 5,
            "sealing_measured_inside_unknown20_no_doublecharge": True,
            "Martin_CPU_used": 136.46,
            "Martin_CPU_cap": 2000,
            "Martin_CPU_remaining": 1863.54,
            "first_input_tranche_CPU_used_cap_unchanged": [39.82, 120],
            "Martin_public_units_used_cap": [35, 40],
            "public_delta": 6,
            "Martin_direct_HTTP_bytes": 2405943,
            "public_tool_wire_bytes": None,
            "Martin_public_tool24units_reserved_bytes": 25165824,
            "Martin_public_direct_plus_reserved_bytes": 27571767,
            "Martin_public_byte_cap": 67108864,
            "comparison_CPU_used_remaining": [194.01, 805.99],
            "comparison_latest_review_delta": 27.77,
            "comparison_failed8_82_success8_95_setup10_once": True,
            "comparison_source_units_used_cap_unchanged": [24, 64],
            "actual_market_requests_bytes": [13, 2347300],
            "initial_allocated_requests_bytes": [32, 67108864],
            "unused_initial19_not_repurposed": True,
            "unallocated_remaining_requests_bytes": [64, 67108864],
            "new_locator_market_requests": 0,
            "mounted_filesystem_transport_bytes": None,
            "economic_CPU_used_allocated": [0, 0],
            "fits_orders_paid": [0, 0, 0],
            "all_old_failure_and_unknown_costs_preserved": True,
            "source_index_and_submission_open_failures_counted": True,
            "initial_symlink_nonfollow_and_targetedrepair_retained": True,
        },
    )
    result = write(
        "result.json",
        {
            "task_id": "USIC-PRACTITIONER-RESEARCH",
            "owner": "f9add224-744b-471c-b812-c43cc179fa38",
            "as_of_utc": NOW,
            "verdict": (
                "REAL_CONTINUOUS_ARCHIVE_FOUND_COMPLETE_V2_SOURCE_CONNECTION_NOT_DEMONSTRATED"
            ),
            "positive_input_acceptance": accepted,
            "source_bridge": bridges,
            "calendar_workload": workload,
            "material_scope_decision": decision,
            "cumulative_accounting": accounting,
            "real_minute_archive_year_files": counts,
            "raw_or_historical_class_from_alladjusted_currentACTIVE_not_certified": True,
            "historical_primary_issue_identifier_anchor_found_not_fullcohort_ready": True,
            "no_global_absence_or_mechanism_refutation": True,
            "economic_performance": None,
            "strict_full_input_ready": False,
            "economic_execution_admitted": False,
            "next_action": (
                "Independent scopedmetadata acceptance, then one Rootmaterial"
                "scope choice; no repeatedwarehouse/firstseen/unused19 loop"
            ),
        },
    )
    files = sorted(p for p in OUT.rglob("*") if p.is_file())
    manifest = write(
        "package-manifest.json",
        {
            "kind": "bounded_source_connection_and_material_scope_choice",
            "as_of_utc": NOW,
            "result": result,
            "immutable_bindings": [bind(p) for p in files] + [bind(Path(__file__))],
            "input42file_manifest_unchanged": bind(BASE / "acquisition/package-manifest.json"),
            "no_author_self_acceptance": True,
            "hashes_marketdata": "Only captured footer hashes; no wholelargepricefile SHAclaim",
            "independent_receipt_written_separately_after_seal": True,
        },
    )
    state = {
        "task_id": "USIC-PRACTITIONER-RESEARCH",
        "owner": "f9add224-744b-471c-b812-c43cc179fa38",
        "as_of_utc": NOW,
        "status": "bounded_source_connection_complete_independent_diff_pending",
        "current_result": result,
        "current_manifest": manifest,
        "scientific_review": accepted["v2_scientific_review"],
        "actual_input_acceptance": accepted["actual_components"],
        "followon_allocation_decision": accepted["followon_not_allocated"],
        "input_ready": False,
        "economic_execution_admitted": False,
        "budget_accounting": accounting,
        "Martin_CPU_used_remaining": [136.46, 1863.54],
        "Martin_public_units_used_cap": [35, 40],
        "comparison_CPU_used_remaining": [194.01, 805.99],
        "market_requests_used_allocated": [13, 32],
        "economic_CPU_used_allocated": [0, 0],
        "active_numeric_job": None,
        "execution_active": True,
        "next_action": (
            "ee sourceconnection diff; if no actualsamev2 route, Rootchoo"
            "se concrete finitehistoricalcohort/rawbridge scope"
        ),
        "preserved": (
            "v1,v2,accepted42input,GMEissuer,oldaccountings,failure/unknownrecords unchanged"
        ),
    }
    (BASE / "current-state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(
        json.dumps(
            {
                "manifest": manifest,
                "result": result,
                "counts": counts,
                "calendar": years,
                "pilot_last": pilot[-1].isoformat(),
            }
        )
    )


if __name__ == "__main__":
    main()
