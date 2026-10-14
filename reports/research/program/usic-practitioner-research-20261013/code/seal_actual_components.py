"""Seal actual input components and cumulative spending; keep the old decision immutable."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "acquisition"


def bound(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(path, payload):
    path.write_text(json.dumps(payload, indent=2) + "\n")


def main():
    assert not (OUT / "package-manifest.json").exists(), "No silent reseal/overwrite"
    now = datetime.now(UTC).isoformat()
    ledger = json.loads((OUT / "request-ledger.json").read_text())
    result = json.loads((OUT / "actual-component-result.json").read_text())
    old_accounting = (
        ROOT / "reports/research/program/martin-luk-usic-20261013/cumulative-accounting.json"
    )
    prior = json.loads(old_accounting.read_text())
    measured = []
    for name in ("acquire-process-resource.txt", "build-process-resource.txt"):
        path = OUT / name
        text = path.read_text()
        cpu = sum(
            float(re.search(rf"{key} time \(seconds\): ([0-9.]+)", text).group(1))
            for key in ("User", "System")
        )
        measured.append(
            {
                "profile": bound(path),
                "coreseconds": cpu,
                "max_RSS_KiB": int(
                    re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
                ),
                "exit": int(re.search(r"Exit status: (\d+)", text).group(1)),
            }
        )
    new_charge = sum(x["coreseconds"] for x in measured) + 20
    old_charge = (
        prior["preparation_measured_CPU_seconds"]
        + prior["setup_and_small_reads_unknown_CPU_charge"]
    )
    accounting = {
        "as_of_utc": now,
        "prior_Martin_accounting": bound(old_accounting),
        "prior_Martin_CPU_used": old_charge,
        "new_measured_jobs": measured,
        "unknown_setup_read_code_and_sealing_conservative_charge": 20,
        "sealing_metadata_job_included_in_conservative_charge": True,
        "first_tranche_CPU_reserved_upper": 120,
        "first_tranche_conservative_CPU_used": round(new_charge, 4),
        "first_tranche_CPU_remaining": round(120 - new_charge, 4),
        "Martin_global_CPU_used": round(old_charge + new_charge, 4),
        "Martin_global_CPU_cap": 2000,
        "Martin_global_CPU_remaining": round(2000 - old_charge - new_charge, 4),
        "actual_market_requests": ledger["requests_used"],
        "actual_complete_entity_bytes": ledger["complete_entity_bytes"],
        "unknown_response_byte_reservations": ledger["incomplete_response_reserved_bytes"],
        "allocated_initial_requests": 32,
        "allocated_initial_bytes": 67108864,
        "unused_initial_request_allocation": 32 - ledger["requests_used"],
        "unused_initial_byte_allocation": 67108864 - ledger["complete_entity_bytes"],
        "shared_market_request_cap": 96,
        "shared_market_byte_cap": 134217728,
        "unallocated_remainder_requests": 64,
        "unallocated_remainder_bytes": 67108864,
        "unallocated_remainder_requires_conditional_ee_decision": True,
        "comparison_prior_accounting": bound(BASE / "cumulative-accounting.json"),
        "comparison_CPU_used": 166.24,
        "comparison_CPU_remaining": 833.76,
        "source_original_Martin_request_units_used_cap": [26, 40],
        "source_comparison_request_units_used_cap": [24, 64],
        "public_requests_added": 0,
        "economic_CPU_allocated": 0,
        "economic_CPU_used": 0,
        "fits": 0,
        "orders": 0,
        "new_paid_USD": 0,
        "old_failure_and_unknown_accounts_unchanged": True,
        "Root_relativepath_check_not_author_implementation_failure": bound(
            OUT / "root-admission-check.json"
        ),
    }
    assert accounting["first_tranche_CPU_remaining"] > 0
    save(OUT / "cumulative-accounting.json", accounting)

    followon = {
        "scope": (
            "One actual decision about feasibility of approved8 defi"
            "nitions; no second controller/engine or new budget"
        ),
        "v2_scientific_review": bound(BASE / "revisions/v2/independent-plan-review.json"),
        "Root_conditional_delegation": bound(OUT / "root-resource-decision.json"),
        "actual_component_coverage": {
            "raw_daily_rows": 8282,
            "source_records": 22410,
            "selected_symbols": 7,
            "single_minute_days": 8,
            "continuous_strategy_execution_years": 0,
        },
        "admitted_vs_missing": {
            "per_name_raw_price_volume": (
                "Actual7 histories and8days, legal bounded current-vintage candidates"
            ),
            "source_current_vintage_fields": (
                "fetched_at exists; firstvisible null, no infinite method hunt"
            ),
            "broad_episode_cohort": (
                "Not provided by this manifest. Public winner/loser case"
                "s are a forensic sampling frame, not declared historica"
                "l leader universe"
            ),
            "ordered_execution": (
                "Only8discontinuous case days; no asserted2yearcontinuou"
                "s tape/AVWAP or controller cash feedback"
            ),
            "price_cash_rights": (
                "GME2025GME.WS is actual separate source action. Receipt"
                "/value absent, no deletion/zero; 7cachedday adjustments"
                " reconcile, not proof of broad all->rawcash"
            ),
            "native_direction_campaign": (
                "Actualv2 preparation gatespass; full iteration/input/im"
                "plementation/resource gates for economics still pending"
            ),
            "eight_method_workload": (
                "120enumerated rows/102paired comparisons are frozen, no"
                " returns seen or run; full data-linked execution estima"
                "te cannot be certified from8days"
            ),
        },
        "requested_independent_action": (
            "Independently accept/correct actual components; decide "
            "whether an existing evidence-backed completecohort/orde"
            "redexecution route withinv2 is available. If it is, bin"
            "d the specific source/episode/clock/workload/native/inp"
            "ut/implementation/resource evidence and allocate only e"
            "ligible remainingpool. If not, explicitly retain the un"
            "resolved economics and identify the missing packet/most"
            " valuable alternate scope; do not autoallocate on these"
            "7selectednames."
        ),
        "no_global_market_refutation": True,
        "minimum_same_v2_full_route": [
            (
                "Dated source-backed common-stock/unleveragedETF episode"
                "s from a declared usable coverage pool; no current cons"
                "tituent/futurecompleteness selection"
            ),
            (
                "Raw/action-compatible past features and actual or decla"
                "red bar-scenario full holding chronology with missing/t"
                "erminal assets retained"
            ),
            "Pre-anchor RTH VWAP/volume or declared frozenEMA fallback, noHLC substitute",
            (
                "All8 ledger/state definitions and matchedclock/cost sce"
                "narios executed independently within one shared7200CPU "
                "if actually admitted"
            ),
        ],
        "budget": accounting,
        "economic_execution_admitted": False,
    }
    save(OUT / "followon-input-and-workload-decision.json", followon)

    result.update(
        as_of_utc=now,
        author="f9add224-744b-471c-b812-c43cc179fa38",
        scope="Actual first bounded acquisition; not full economic research completion",
        request_ledger=bound(OUT / "request-ledger.json"),
        cumulative_accounting=bound(OUT / "cumulative-accounting.json"),
        source_firstvisible_unknown_not_price_component_blocker=True,
        original_v1_v2_initial_decision_artifacts_unchanged=True,
        independent_input_acceptance=None,
        next_action=(
            "Directee actualcomponent acceptance and conditionalfoll"
            "owon decision; sameowner ordinaryrepairs/continuation, "
            "no stage-readyRootfinish."
        ),
    )
    save(OUT / "actual-component-result.json", result)
    files = sorted((OUT / "entities").glob("*.bin")) + sorted((OUT / "derived").glob("*"))
    files += [
        OUT / x
        for x in (
            "request-ledger.json",
            "root-resource-decision.json",
            "root-admission-check.json",
            "implementation-manifest.json",
            "fresh-memory.json",
            "admission.txt",
            "collection-resource.json",
            "acquire-process-resource.txt",
            "build-fresh-memory.json",
            "build-admission.txt",
            "build-process-resource.txt",
            "cumulative-accounting.json",
            "actual-component-result.json",
            "followon-input-and-workload-decision.json",
        )
    ]
    files += [
        BASE / "code/build_actual_components.py",
        BASE / "code/seal_actual_components.py",
        ROOT / "open_composer/research/features/price_hygiene.py",
        ROOT / "open_composer/market_calendar.py",
        ROOT / "open_composer/market_sessions.py",
    ]
    manifest = {
        "schema_version": 1,
        "created_at": now,
        "owner": "f9add224-744b-471c-b812-c43cc179fa38",
        "role": (
            "Actual raw/action/clock and bounded price-feature input candidates; no economic result"
        ),
        "files": [bound(path) for path in files],
        "historical_first_visible": None,
        "original_entities_never_rewritten": True,
        "current_vintage": True,
        "full_method_input_ready": False,
        "economic_execution_admitted": False,
        "conditional_allocation_not_claimed": True,
    }
    save(OUT / "package-manifest.json", manifest)
    state = json.loads((BASE / "current-state.json").read_text())
    state.update(
        as_of_utc=now,
        status="actual13requests_complete_component_packet_to_independent_receiver",
        result=bound(OUT / "actual-component-result.json"),
        actual_input_manifest=bound(OUT / "package-manifest.json"),
        budget_accounting=bound(OUT / "cumulative-accounting.json"),
        execution_active=True,
        active_numeric_job=None,
        market_requests_used_allocated=[13, 32],
        market_entity_bytes_used_allocated=[2347300, 67108864],
        original_Martin_CPU_used_remaining=[
            round(old_charge + new_charge, 4),
            round(2000 - old_charge - new_charge, 4),
        ],
        actual_component_counts={
            "source_records": 22410,
            "daily_raw": 8282,
            "single_minute_days": 8,
            "features": 7,
            "complete_grid_events": 175,
            "missing_grid_events_retained": 33,
        },
        actual_new_right="GME.WS1per10shares ex2025-10-03, value/receiptunknown retained",
        next_action=result["next_action"],
    )
    save(BASE / "current-state.json", state)
    print(
        json.dumps(
            {
                "manifest": bound(OUT / "package-manifest.json"),
                "files": len(files),
                "first_tranche_CPU_used": accounting["first_tranche_conservative_CPU_used"],
                "Martin_global_CPU_remaining": accounting["Martin_global_CPU_remaining"],
                "actual_HTTP": 13,
                "source_rows": 22410,
                "economic_runs": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
