"""Metadata-only sealing of actual bounded inputs and preserved failed jobs."""

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "revisions/v3-finite-qqq"


def read(name):
    return json.loads((OUT / name).read_text())


def binding(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(name, obj):
    p = OUT / name
    assert not p.exists(), "preserve_seal"
    p.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def main():
    now = datetime.now(UTC).isoformat()
    ledger = read("market/request-ledger.json")
    daily = read("bounded-components/daily-coverage-and-basis.json")
    actions = read("bounded-components/all-actions-and-held-rights.json")["records"]
    cases = read("bounded-components/fixed-first-three-price-features.json")["records"]
    assert ledger["requests_used"] == 47 and all(a["entity_complete"] for a in ledger["attempts"])
    failures = [
        {
            "job": "full_diagnostic_attempt1",
            "CPU": 45.18,
            "RSS_KiB": 170840,
            "actual_exit": 152,
            "signal": 24,
            "serialized_features": None,
            "retained_partial_pointer_rows": 291108,
            "time_Exit_status_zero_is_not_success": True,
        },
        {
            "job": "full_diagnostic_attempt2",
            "CPU": 16.08,
            "RSS_KiB": 169704,
            "actual_exit": 152,
            "signal": 24,
            "serialized_features": None,
        },
        {
            "job": "bounded_component_seal",
            "CPU": 2.10,
            "RSS_KiB": 156984,
            "actual_exit": 137,
            "signal": 9,
            "completed_files": [
                "fixed-first-three-price-features.json",
                "all-actions-and-held-rights.json",
                "daily-coverage-and-basis.json",
            ],
            "incomplete_file_not_created": "source-timestamp-coverage.json",
        },
        {"job": "metadata_lint_failure", "CPU": 0.10, "actual_exit": 1},
    ]
    account = {
        "as_of": now,
        "predecessor": binding(OUT / "r1-accounting.json"),
        "bridge_CPU_sequence": {
            "prior_R1": 21.78,
            "source403": 1.51,
            "transport_setup_unknown_retained": 10,
            "transport_preparation": 0.28,
            "source_repair": 4.52,
            "market": 12.88,
            "diagnostic_code_reads_seal_handoff_unknown_reserved": 5,
            "diagnostic_lint_failure": 0.05,
            "full_build_failure": 45.18,
            "recovery_failure": 16.08,
            "bounded_components_failure": 2.10,
            "metadata_lint_failure": 0.10,
        },
        "bridge_CPU_used_cap_remaining_before_metadata_seal": [119.48, 120, 0.52],
        "metadata_seal_actual_CPU": "profile bound; record final charge in current-state",
        "Martin_CPU_used_cap_remaining_before_metadata_seal": [260.94, 2000, 1739.06],
        "comparison_CPU_used_cap_remaining_at_received_reviews": [216.79, 1000, 783.21],
        "affected_review40_used_remaining": [16.27, 23.73],
        "public_source_units_used_cap": [37, 40],
        "new_source_actual_calls": 2,
        "new_source_complete_entity_bytes": 113966,
        "known_direct_source_entity_bytes_cumulative": 2519909,
        "historical_tool_source_HTTP_and_wire_totals": None,
        "Root_web_separate_open_find": [2, 3],
        "old_market_calls_bytes": [13, 2347300],
        "new_bridge_market_calls_bytes": [47, 41548041],
        "new_bridge_requests_bytes_reserved": [48, 65011712],
        "new_bridge_unused_requests_bytes": [1, 23463671],
        "unreserved_followon_requests_bytes": [16, 2097152],
        "old_unused_initial19_not_repurposed": True,
        "economic_CPU_used_allocated": [0, 0],
        "all_old_failures_unknowns_affinity_limits_preserved": True,
        "actual_job_affinity": [0],
        "actual_job_memcap_MiB": 900,
        "local_original_JD_APP_H5_budgets_not_inherited": True,
    }
    assert abs(sum(account["bridge_CPU_sequence"].values()) - 119.48) < 1e-8
    save("actual-acquisition-accounting.json", account)
    save(
        "actual-bridge-result.json",
        {
            "task_id": "USIC-PRACTITIONER-RESEARCH",
            "owner": "f9add224-744b-471c-b812-c43cc179fa38",
            "as_of": now,
            "verdict": "actual_raw_components_with_partial_causal_features_full_diagnostic_capped",
            "source": {
                "same_primary_SEC_XML_complete_200": True,
                "bytes": 109147,
                "prior403_retained": True,
                "roster_issue_rows": 101,
                "frozen_before_price": True,
                "hash_first_diagnostic_slots": 25,
                "dated_FTD_identity_candidates": 25,
                "FTD_is_not_episode_interval": True,
                "historical_first_visible": None,
            },
            "actual_market": {
                "requests": 47,
                "complete_entity_bytes": 41548041,
                "all200_complete": True,
                "incomplete_reserved_bytes": 0,
                "raw_daily_rows": sum(x["raw_rows"] for x in daily),
                "all_daily_rows": sum(x["all_rows"] for x in daily),
                "symbols": len(daily),
                "daily_scope": "2023-07-01..2025-12-31; raw and all separately",
                "minute_entities": sum(x["id"].startswith("raw_RTH_") for x in ledger["attempts"]),
                "minute_scope": "first40 2024 sessions; 25 pre-price fixed slots; raw RTH",
                "minute_total_rows_and_valid_parent_geometry": None,
                "missing_terminal_slot_not_resampled": [x for x in daily if x["symbol"] == "SGEN"],
            },
            "actual_features": {
                "cases": [
                    {
                        k: f[k]
                        for k in (
                            "symbol",
                            "decision_day",
                            "prior_completed_day",
                            "ADR20",
                            "ADV20",
                            "momentum21",
                            "numeric_price_gate",
                        )
                    }
                    for f in cases
                ],
                "case_selection": "first3 frozen hashes, first fixed session, no outcome selection",
                "Decimal_precision": 60,
                "source_window_EMA_seed_not_episode_seed": True,
                "full1000_features_and_full101_rank": None,
                "full_eligibility": None,
                "geometry_trade_count": None,
                "N_A_means_unfinished_not_zero_or_no_opportunity": True,
            },
            "actual_actions": {
                "rows": len(actions),
                "types": dict(Counter(a["type"] for a in actions)),
                "identity_mismatches": [a for a in actions if a["quarantined_identity_mismatch"]],
                "critical_case_rules": [
                    "SGEN old equity cash merger229 on2023-12-14; "
                    "postmerger FTD point not life interval; receipt unknown",
                    "ILMN GRAL child right retained at source rate0.166666667; "
                    "no invented fractional cash/mark/receipt",
                    "ASML 2024-12-02 dividend CUSIP G3730V147 differs from frozen N07059210; "
                    "quarantine action, do not apply by ticker",
                    "PANW/PCAR source splits retained with exdate/sharebasis; "
                    "raw/all prices never interchangeable",
                    "SNPS/PANW acquirer or recipient roles do not cancel their continuing shares",
                    "Process_date/source publication/current_fetched_at/ex/payable/spendable "
                    "clocks distinct",
                ],
            },
            "resource_failures": failures,
            "precise_remaining_links": [
                "101-issue dated roster exists, but all101 ticker/type/episode-to-raw bridge "
                "not certified",
                "25 raw daily candidates exist; 40 raw minute entities exist; "
                "continuous2024-25 ordered execution for full101 not acquired",
                "Held-child/right cash or market values, actualreceipt/fraction rules "
                "still unknown where relevant; no deletion",
                "997 diagnostic feature cases and all1000 minute-parent/geometry cells "
                "unfinished due preparation CPU cap",
                "Full8/120/102 data-linked execution implementation, workload, "
                "native/input/resource admissions not complete",
            ],
            "scientific_limits": [
                "Finite historicalQQQ largecap-growth adaptation; "
                "cannot generalize to Martin highADR/smallcap/theme universe",
                "8definitions/120cells/102pairs/2024-25 unchanged; "
                "no ADR/momentum relaxation or profit selection",
                "Current-vintage components legal with firstvisible=null; "
                "not historical public-firstseen certification",
                "No Rf/ETB/AVWAP single-gap global impossibility claim; "
                "legal price components retained",
                "Public Martin/Flanders actual-case evidence remains separate "
                "from investable universe",
            ],
            "economic_execution_admitted": False,
            "strict_input_ready": False,
            "economic_trials_fits_orders_PnL": 0,
            "independent_acceptance": "pending reviewer; author does not self-approve",
            "next_value_decision": (
                "ee actual component acceptance and bounded route/resource judgement; "
                "no automatic7200 allocation"
            ),
        },
    )
    paths = [
        p
        for p in OUT.rglob("*")
        if p.is_file()
        and p.name
        not in {
            "actual-diagnostic-package-manifest.json",
            "actual-input-handoff.txt",
            "seal-result-resource.txt",
        }
        and not p.name.startswith("independent")
        and "__pycache__" not in p.parts
        and "entry-r1-before" not in p.parts
    ]
    paths += [
        BASE / "code" / name
        for name in (
            "acquire_finite_cohort_bridge.py",
            "repair_declared_sec_source.py",
            "build_finite_raw_diagnostic.py",
            "seal_bounded_raw_components.py",
            "seal_actual_bridge_result.py",
        )
    ]
    save(
        "actual-diagnostic-package-manifest.json",
        {
            "schema_version": 3,
            "as_of": now,
            "role": "actual_component_package_not_economic_input",
            "result": binding(OUT / "actual-bridge-result.json"),
            "files": [binding(p) for p in sorted(set(paths))],
            "accepted_authority": [
                binding(OUT / name)
                for name in (
                    "independent-delta-review.json",
                    "independent-entry-diff-review.json",
                    "independent-source-access-and-method-review.json",
                    "independent-transport-entry-diff-review.json",
                )
            ],
            "FTD_existing_source_bindings": read("identity-candidates.json")["FTD_sources"],
            "partial_row_pointer_index_is_not_complete": True,
            "complete_source_entity_SHA_binding_is_authoritative": True,
            "all_parent_sealed_packages_untouched": True,
        },
    )
    print(json.dumps(binding(OUT / "actual-diagnostic-package-manifest.json")))


if __name__ == "__main__":
    main()
