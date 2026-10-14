"""Close the accepted task once; all earlier submitted evidence stays immutable."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from hf_completion_resources import snapshot

P = Path(__file__).resolve().parent


def bind(path):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                bytes=path.stat().st_size)


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def contains_sha(value, digest):
    if isinstance(value, dict):
        return value.get("sha256") == digest or any(contains_sha(v, digest) for v in value.values())
    if isinstance(value, list):
        return any(contains_sha(v, digest) for v in value)
    return False


def main():
    review_path = P / "independent-result-review.json"
    review = json.loads(review_path.read_text())
    assert review["verdict"] == "accept_complete_conditional_result", review["verdict"]
    assert review["author"] != review["reviewer"]
    manifest = bind(P / "complete-costed-final-manifest.json")
    assert contains_sha(review, manifest["sha256"])
    resource = snapshot()
    assert not resource["commitments"]
    assert resource["conservative_used_CPU"] <= resource["cap_CPU"]
    result = json.loads((P / "complete-costed-result.json").read_text())
    state_path = P / "current-state.json"
    before = P / "current-state-before-complete-result-closeout.json"
    assert not before.exists(), "one final closeout only"
    before.write_bytes(state_path.read_bytes())
    state = json.loads(state_path.read_text())
    superseded = {}
    for key in [
        "new_model_fits", "new_economic_runs", "new_economic_CPU_coreseconds",
        "actual_registered_logical_trials_started", "actual_registered_logical_trials_completed",
        "registered_logical_configs_started", "registered_unique_logical_configs_started",
        "completed_model_prefixes", "economic_original7006_69_remaining",
        "new_strategy_account_runs", "new_economic_runs_identity", "new_model_fits_identity",
        "completed_economic_job_inclusive_CPU", "hgb_next_refit", "hgb_latest_attempt_metadata",
        "hgb_started_rows", "hgb_completed_rows", "hgb_unique_logical_trials",
        "hgb_persisted_checkpoints", "hgb_runtime_observation", "calibration_resource_progress",
        "result", "final_manifest", "completion_receipt_path", "actual_native_gate",
        "implementation_manifest", "independent_implementation_accepted",
        "completion_native_prebacktest_status", "completion_independent_implementation",
    ]:
        if key in state:
            superseded[key] = state.pop(key)
    state["superseded_historical_fields_at_final_closeout"] = dict(
        reason="Historical observations retained, not current counts or remaining budget",
        before_state=bind(before), fields=superseded,
    )
    final_ledger = P / "completion-resource-ledger-final.json"
    assert not final_ledger.exists()
    final_ledger.write_bytes((P / "completion-resource-ledger.json").read_bytes())
    receipt = dict(
        task_id="DAY3-HF-FACTOR-RETURN", owner="7b109880-ac40-447e-b2a6-f0ed1266ebac",
        status="complete_independently_accepted_conditional_result",
        decision=result["economic_judgment"]["decision"], at_utc=datetime.now(UTC).isoformat(),
        result=bind(P / "complete-costed-result.json"),
        report=bind(P / "complete-costed-result.md"), final_manifest=manifest,
        independent_result_review=bind(review_path), resource_ledger=bind(final_ledger),
        historical_review_ledger_binding_resolution=bind(
            P / "completion-resource-ledger-at-independent-result-acceptance.json"
        ),
        native_review_event_wait=bind(P / "independent-result-event-wait-time.txt"),
        resources=resource, actual_inventory=result["inventory"],
        workflow_pass=True, research_pass=False, ml_contribution_pass=False,
        paper_ready_pass=False, orders=0, new_paid_USD=0,
        immutable_submission_pending_field=(
            "Result/report pending wording records their pre-review seal time. "
            "This receipt and independent review are the authoritative acceptance status."
        ),
        resource_history=dict(
            old_completion_base_CPU=460.49, old_preparation_cap_CPU=2300,
            old_preparation_used_CPU=2281.64992391, old500_reservation_released=False,
            old_source_market_failures_unknowns_refunded=False,
            initial_calibration_exit137_kernel_cause_not_certified=True,
            initial_calibration_peak_RSS_KiB=925484,
            old900MiB_compliance_claim=False,
            all_new_work_charged_only_to_existing36000=True,
        ),
        model_retrain_on_stream_disconnect=False,
        standalone_account_rerun_on_stream_disconnect=False,
        scope_limits=result["scope"],
        native_return="One native final; no explicit duplicate Root notification",
    )
    receipt_path = P / "complete-costed-completion-receipt.json"
    save(receipt_path, receipt)
    state.update(
        status="complete_independently_accepted_costed_conditional_result",
        owner_released=True, complete_costed_HF_result=True, independent_result_accepted=True,
        workflow_pass=True, research_pass=False, ml_contribution_pass=False, paper_ready_pass=False,
        result=receipt["result"], final_manifest=manifest,
        independent_result_review=receipt["independent_result_review"],
        completion_receipt_path=str(receipt_path), completion_receipt=bind(receipt_path),
        implementation_manifest=bind(P / "implementation-manifest.json"),
        independent_implementation_accepted=bind(P / "independent-implementation-review.json"),
        actual_current_trial_accounting=result["inventory"],
        completion_current_conservative_CPU=round(resource["conservative_used_CPU"], 2),
        completion_reserved_CPU=0,
        completion_current_remaining_CPU=round(resource["remaining_uncommitted_CPU"], 2),
        completion_current_remaining_uncommitted_CPU=round(resource["remaining_uncommitted_CPU"], 2),
        current_process_pid=None, current_process_exit_status=0, actual_process_exit_status=0,
        current_economic_job_processes=0, current_training_processes=0,
        current_training_phase="Complete; no native scientific job active",
        no_further_execution_scheduled=True,
        native_gate_ready=True, knowledge_gate_ready=True, implementation_ready=True,
        actual_native_M3_evidence=bind(P / "economic/host-completion-resource.json"),
        test_statistical_metric_report_available=True,
        costed_account_result_available=True,
        economic_judgment=result["economic_judgment"],
        next_action="Stop current application allocation; defer deployment. Root receives one complete result; no local new experiment or order authorization.",
        updated_at_utc=datetime.now(UTC).isoformat(),
    )
    save(state_path, state)
    print(json.dumps(dict(receipt=bind(receipt_path), resources=resource)))


if __name__ == "__main__":
    main()
