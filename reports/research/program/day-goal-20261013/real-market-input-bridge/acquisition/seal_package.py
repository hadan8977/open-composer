"""Seal new evidence without modifying either previously accepted package."""

from __future__ import annotations

import json
from pathlib import Path

from acquire import save, sha, utc

ROOT = Path("/root/codex-test/open-composer")
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent


def binding(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path), "bytes": path.stat().st_size}


def main():
    ledger = json.loads((OUT / "data-request-ledger.json").read_text())
    result = json.loads((OUT / "result.json").read_text())
    request = json.loads((OUT / "request-manifest.json").read_text())
    verification = json.loads((OUT / "verification.json").read_text())
    assert verification["verdict"] == "author_integrity_and_input_arithmetic_checks_pass"
    cpu_receipts = {}
    for filename in (
        "acquisition-resource-receipt.json",
        "schema-inspection-receipt.json",
        "component-build-resource-receipt.json",
    ):
        cpu_receipts[filename] = json.loads((OUT / filename).read_text())["cpu_seconds"]
    cpu_receipts["verification.json"] = verification["resource"]["cpu_seconds"]
    prior = request["prior_consumption_preserved"]
    old_measured = prior["old_local_CPU_measured_seconds"]
    h5_measured = prior["H5_reception_CPU_seconds"]
    measured = old_measured + h5_measured + sum(cpu_receipts.values())
    charges = {
        "old_failures_and_setup_preserved": prior["old_unmeasured_CPU_charge_seconds"],
        "H5_reception_setup_unknown": prior["H5_reception_setup_unknown_CPU_charge_seconds"],
        "pre_acquisition_setup_unknown": prior["pre_acquisition_setup_CPU_unknown_charge_seconds"],
        "postapproval_setup_imports_lint_metadata_and_finalization_unknown": 30,
    }
    accounting = {
        "as_of_utc": utc(),
        "original_CPU_cap_seconds": 7200,
        "prior_acquisition_remaining_accepted_seconds": 6875.075568,
        "old_measured_CPU_seconds": old_measured,
        "H5_reception_CPU_seconds": h5_measured,
        "new_acquisition_measured_CPU_by_receipt": cpu_receipts,
        "cumulative_measured_CPU_seconds": measured,
        "unknown_CPU_charges_seconds": charges,
        "charges_are_conservative_allowances_not_measurements": True,
        "remaining_original_CPU_seconds_conservative": 7200 - measured - sum(charges.values()),
        "old_source_units": 22,
        "old_source_unit_limit": 24,
        "model_source_units": 40,
        "old_source_bytes_and_all_failures_preserved": {
            "direct_bytes": 394831,
            "total_conservative_byte_allowance": 11929167,
            "memory_failure_receipt": str(
                (PARENT / "intake-before-low-memory-repair-receipt.json").relative_to(ROOT)
            ),
        },
        "old_numeric_source_record_reads_known": 963,
        "old_local_row_scope_limit": 2000,
        "old_distinct_value_files": 16,
        "old_local_file_scope_limit": 24,
        "old_source_pool_rescanned": False,
        "new_explicit_HTTP_envelope_not_old_local_pool_reset": True,
        "new_actual_HTTP_entity_files": 13,
        "new_unique_numeric_source_records": 392,
        "new_source_entity_record_parse_occurrences_known": {
            "collector_payloads": 392,
            "bounded_schema_inspection": 392,
            "component_build": 392,
            "verification_original_entities": 392,
        },
        "new_normalized_copy_records_verified": 392,
        "new_data_requests_used": ledger["data_requests_used"],
        "new_data_request_limit": 32,
        "new_data_actual_response_bytes": ledger["actual_entity_bytes"],
        "new_data_response_bytes_limit": 67108864,
        "new_data_unknown_bytes_allowance": ledger["unknown_entity_byte_allowance"],
        "new_public_method_units_used": 5,
        "new_public_method_unit_limit": 16,
        "new_public_direct_HTTP_bytes": 0,
        "new_public_direct_byte_limit": 33554432,
        "new_public_web_bytes_unexposed": True,
        "new_public_web_byte_allowance": 8388608,
        "new_fits": 0,
        "optimizer_updates": 0,
        "economic_computations": 0,
        "orders": 0,
        "new_paid_USD": 0,
        "remote_allocations": 0,
        "H5_global_counts_kept": {
            "authoritative_fits": 10,
            "authoritative_updates": 8000,
            "new_independently_received_fits": 2,
            "new_independently_received_updates": 1600,
            "Root_acceptance_of_counts_pending": True,
        },
        "no_quota_reset": True,
    }
    save(OUT / "continuation-accounting.json", accounting)
    source_cards = []
    for attempt in ledger["attempts"]:
        kind = (
            "raw daily prices"
            if attempt["input_id"].endswith("bars_raw")
            else "all-adjusted diagnostic bars"
            if attempt["input_id"].endswith("bars_all")
            else "current alltype action records"
            if "actions" in attempt["input_id"]
            else "fixed SIP quote endpoint or actual bounded empty response"
        )
        source_cards.append(
            {
                "id": attempt["input_id"],
                "url": attempt["endpoint"],
                "source_type": "actual configured read-only provider response",
                "accessed_at": attempt["actual_fetched_at"],
                "snapshot_path": attempt["entity_path"],
                "snapshot_sha256": attempt["entity_sha256"],
                "claim": kind,
                "parameters": attempt["params"],
                "historical_first_visible_at": None,
                "role": "real-market input component; original500stock factor source unreproduced",
                "limits": "Current vintage; absence conditional; strictPIT/receipt uncertified",
            }
        )
    for url, claim in (
        (
            "https://docs.alpaca.markets/reference/corporateactions-1",
            "Inclusive process-date/alltype/data_qualityall; CA creation time unguaranteed",
        ),
        (
            "https://docs.alpaca.markets/reference/stockbars",
            "Raw/all meanings and pagination; asof is symbolmapping, not vintage",
        ),
        (
            "https://docs.alpaca.markets/reference/stockquotes-1",
            "Inclusive quote window, ascending pagination, SIP; asof symbolmapping",
        ),
    ):
        source_cards.append(
            {
                "url": url,
                "source_type": "retained primary official method page",
                "claim": claim,
                "snapshot": binding(OUT / "provider-method-opened.json"),
                "scope_binding": binding(OUT / "request-scope-acceptance.json"),
                "new_source_request": False,
            }
        )
    with (OUT / "source-evidence.jsonl").open("w") as handle:
        for row in source_cards:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    old_manifest = json.loads((PARENT / "package-manifest.json").read_text())
    reused_paths = {
        "lifecycle-contract.json",
        "sources/apple_split_dividend.html",
        "sources/ATVI_terminal.html",
        "terminal-web-snapshots.json",
    }
    prior_bindings = [
        dict(
            path=str((PARENT / item["path"]).relative_to(ROOT)),
            sha256=item["sha256"],
            bytes=item["bytes"],
            status="reuse existing independently received evidence; not redownloaded",
        )
        for item in old_manifest["files"]
        if item["path"] in reused_paths
    ]
    excluded = {
        "package-manifest.json",
        "independent-input-acceptance.json",
        "scope-review-handoff.txt",
        "model-owner-handoff.txt",
        "handoff-native-receipt.json",
        "final-input-receipt.json",
    }
    files = [
        p
        for p in sorted(OUT.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name not in excluded
    ]
    sealed = {
        "schema_version": 1,
        "task_id": "DAY3-REAL-MARKET-INPUT-BRIDGE",
        "revision": "actual_acquisition_AAPL_ATVI_components_v1",
        "sealed_at_utc": utc(),
        "author": "f9add224-744b-471c-b812-c43cc179fa38",
        "independent_reviewer": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
        "independent_result_acceptance": "pending external receipt, excluded from author seal",
        "request_manifest": binding(OUT / "request-manifest.json"),
        "scope_acceptance": binding(OUT / "request-scope-acceptance.json"),
        "model_interface": binding(OUT / "model-input-interface.json"),
        "authority": binding(PARENT / "acquisition-continuation.md"),
        "parent_accepted_v2": binding(PARENT / "package-manifest.json"),
        "parent_accepted_partial": binding(PARENT / "partial-input/package-manifest.json"),
        "reused_prior_evidence": prior_bindings,
        "independent_H5_receipt": binding(
            PARENT.parent / "dlsa/deepening/independent-H5-result-acceptance.json"
        ),
        "classes": {
            "A_sourcefacts": True,
            "B_current_vintage_candidates": True,
            "C_strict_APP": False,
        },
        "coverage": {
            k: result[k]
            for k in (
                "raw_numeric_source_records",
                "calendar_session_rows",
                "price3_numerical_rows",
                "price3_usable_non_split_trigger_rows",
                "actual_0945_endpoint_quotes",
                "current_vintage_gross_quote_label_candidates",
                "retained_blocked_label_cases",
            )
        },
        "strict_APP_input_ready": False,
        "full7": False,
        "model_or_economic_admitted": False,
        "cohort_scientific_plan_modified": False,
        "source_role": "Actual source arithmetic; full500/8year/original39factor unreproduced",
        "files": [
            {"path": str(p.relative_to(OUT)), "sha256": sha(p), "bytes": p.stat().st_size}
            for p in files
        ],
        "mutable_not_sealed": sorted(excluded - {"package-manifest.json"}),
    }
    save(OUT / "package-manifest.json", sealed)
    manifest_binding = binding(OUT / "package-manifest.json")
    state = json.loads((PARENT / "current-state.json").read_text())
    state.update(
        as_of_utc=utc(),
        status="actual_components_sealed_pending_independent_model_owner_acceptance",
        acquisition_package_manifest=manifest_binding,
        acquisition_result=binding(OUT / "result.json"),
        acquisition_coverage=sealed["coverage"],
        cumulative_acquisition=accounting,
        next_action=(
            "Modelowner independent component reception/scientific choice; "
            "fixedscope source fetching complete"
        ),
    )
    state["sourcehash"].update(
        acquisition_manifest=manifest_binding["sha256"],
        acquisition_request_manifest=sha(OUT / "request-manifest.json"),
    )
    state["real_gaps"] = {
        "strict_APP": (
            "First-visible/revisions, marketwide identity/eligibility/top500/8year uncertified; "
            "twoepisode package cannot refute wholemarket feasibility"
        ),
        "price3": "66 numerical rows/65 nonsplit-trigger conditional inputs; RF/ETB doesnot block",
        "label": "3 quote-label candidates; Oct13empty retained N/A/95cashright/delivery unknown",
        "Rf_ETB_full7": "Uncertified in current scope; no two-stock rank/median substitutions",
    }
    save(PARENT / "current-state.json", state)
    handoff = (
        f"实际取数包已封：{manifest_binding['path']} "
        f"SHA{manifest_binding['sha256']}。"
        "请直接独立接收并写 acquisition/independent-input-acceptance.json，绑定本SHA。"
        "13实际请求/44098bytes/全200，无追加/重试；392来源记录；"
        "82日历行，66当前vintage price3/65非split-trigger条件行，"
        "6首0945报价/3两端gross quote labels，ATVI terminal出口真实empty所以N/A且95right保留。"
        "AAPL行动真exAug7/$0.82旧股、splitexAug31/4:1；record/pay/process及actualspendable未知分开。"
        "检查入口 result/normalized/return-inputs/price3/quote-label/"
        "held-obligations/verification/sourceentities。"
        "作者50digitDecimal重算66price3和3labels通过，不自批。"
        "AAPLquotecondition?、ATVI R保留，sizeunits/fill未认证；firstvisible全null；"
        "event/hypotheticalmaturity/currentreceipt三钟分开；原v2/partial/canonical未改，非完整7/500/8y/PIT。"
        "旧CPU/失败/22和40账均保留，新public5/16无更多firstseen；剩余原CPU详accounting。"
        "H5非作者接收已写，原10/8000计数不改。"
        "请同接收给出你与7b的后续科学选择边界；不需重拉/训练/回测或Root逐项通知。\n"
    )
    (OUT / "model-owner-handoff.txt").write_text(handoff)
    print(
        json.dumps(
            {
                "manifest": manifest_binding,
                "files": len(files),
                "remaining_CPU": accounting["remaining_original_CPU_seconds_conservative"],
            }
        )
    )


if __name__ == "__main__":
    main()
