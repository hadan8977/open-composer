"""Receive and QA the approved exact file inventory; no forecasts or returns."""

import gc
import hashlib
import json
import os
import resource
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from public_intake_continuation import main as capture

P = Path(__file__).parent
RECOVERY = json.loads((P / "source-intake-recovery-500.json").read_text())
CPU_BASE = RECOVERY["old_actual_job_CPU_coreseconds"]
resource.setrlimit(resource.RLIMIT_CPU, (1000, 1000))
os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
pa.set_cpu_count(1)
pa.set_io_thread_count(1)


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def cpu():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return CPU_BASE + usage.ru_utime + usage.ru_stime


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def qa(path, expected_names, row):
    meta = pq.read_metadata(path)
    assert meta.schema.names == expected_names, "Column identity/order drift"
    frame = pd.read_parquet(path, use_threads=False)
    assert frame.shape[1] == 272
    index = frame.index
    dates = index.normalize()
    numeric = frame.to_numpy()
    finite = np.isfinite(numeric)
    bad_log = np.isfinite(numeric) & (numeric <= -1)
    days = []
    for day in dates.unique():
        ticks = index[dates == day]
        gaps = (ticks[1:] - ticks[:-1]).total_seconds() != 60
        days.append({"date": str(day.date()), "rows": len(ticks),
                     "first": str(ticks[0]), "last": str(ticks[-1]),
                     "non_one_minute_steps": int(gaps.sum()),
                     "duplicate_times": int(ticks.duplicated().sum())})
    result = {
        "month": row["month"], "path": str(path), "sha256": sha(path),
        "bytes": path.stat().st_size, "rows": len(frame), "factor_columns": 272,
        "column_order_matches_first": True,
        "numeric_types": sorted(set(map(str, frame.dtypes))),
        "timezone": str(index.tz), "first": str(index[0]), "last": str(index[-1]),
        "monotonic": index.is_monotonic_increasing,
        "duplicate_timestamps": int(index.duplicated().sum()),
        "nonfinite_values": int((~finite).sum()),
        "NaN_values": int(np.isnan(numeric).sum()),
        "infinite_values": int(np.isinf(numeric).sum()),
        "values_not_in_log1p_domain": int(bad_log.sum()),
        "days": days,
        "economic_admitted": False, "historical_PIT_or_units_complete_proof": False,
        "source_reused": row["reuse_existing"],
    }
    assert result["monotonic"] and result["duplicate_timestamps"] == 0
    assert all(str(day).startswith(row["month"][:4] + "-" + row["month"][4:]) for day in index)
    del numeric, finite, bad_log, frame, index, dates
    gc.collect()
    return result


def main():
    approval_path = P / "independent-complete-input-scope-review.json"
    assert sha(approval_path) == "4b85b329877b51d5b7c36efd50c5863a767b4fca64376cb6fe6008a71abf0747"
    approval = json.loads(approval_path.read_text())
    assert approval["verdict"] == "approve_complete_input_scope"
    manifest_path = P / "complete-input-request-manifest.json"
    assert sha(manifest_path) == approval["bindings"]["request_manifest"]["sha256"]
    manifest = json.loads(manifest_path.read_text())
    expected_names = pq.read_metadata(P / "inputs/199601.parquet").schema.names
    progress_path = P / "complete-input-progress.json"
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {
        "task_id": "DAY3-HF-FACTOR-RETURN", "files": [], "required_files": 300,
        "fits": 0, "economic_runs": 0, "source_QA_only": True,
    }
    completed = {row["month"]: row for row in progress["files"]}
    state_path = P / "current-state.json"
    try:
        for row in manifest["files"]:
            if row["month"] in completed:
                previous = completed[row["month"]]
                assert sha(Path(previous["path"])) == previous["sha256"]
                continue
            state = json.loads(state_path.read_text())
            state.update(status="complete_input_receiving_and_QA", input_process_pid=os.getpid(),
                         input_process_checked_at_utc=datetime.now(UTC).isoformat(),
                         current_input_month=row["month"], complete_months_QA=len(completed),
                         continuation_input_job_CPU_sofar=cpu(), economic_execution_admitted=False,
                         next_action="Complete299approveddownloads+reusefirst withsourceQA only; fullscience/native/economic remainsclosed")
            save(state_path, state)
            output = RECOVERY["output_override"].get(row["month"], row["output"])
            path = P / output
            if row["reuse_existing"]:
                path = Path(row["existing_input"]["path"])
                assert sha(path) == row["existing_input"]["sha256"]
            elif path.exists():
                ledger = json.loads((P / "continuation-source-request-ledger.json").read_text())
                receipts = [r for r in ledger if r.get("path") == str(path)]
                assert receipts and receipts[-1].get("body_complete") and receipts[-1]["status"] == 200
                assert sha(path) == receipts[-1]["sha256"]
            else:
                sys.argv = ["public_intake_continuation", row["url"], output,
                            "--stage", "complete_input", "--max-bytes", str(row["individual_body_hard_cap_bytes"])]
                capture()
                ledger = json.loads((P / "continuation-source-request-ledger.json").read_text())
                receipt = ledger[-1]
                assert receipt["status"] == 200 and receipt.get("body_complete"), "Incomplete or refused source body"
                assert receipt["path"] == str(path)
            if row["size_bytes_verified"] is not None:
                assert path.stat().st_size == row["size_bytes_verified"], "Advertised version/size mismatch"
            result = qa(path, expected_names, row)
            progress["files"].append(result)
            completed[row["month"]] = result
            progress.update(updated_at_utc=datetime.now(UTC).isoformat(), process_pid=os.getpid(),
                            known_input_job_CPU_coreseconds=cpu(), complete_months=len(completed),
                            rows=sum(r["rows"] for r in progress["files"]),
                            raw_file_bytes=sum(r["bytes"] for r in progress["files"]),
                            complete_input_ready_for_independent_QA=False)
            save(progress_path, progress)
            print(json.dumps({"QA_month": row["month"], "completed": len(completed),
                              "rows": result["rows"], "CPU_coreseconds": cpu()}), flush=True)
        progress.update(process_exit_status=0, complete_input_ready_for_independent_QA=True,
                        final_input_job_CPU_coreseconds=cpu(), finished_at_utc=datetime.now(UTC).isoformat())
        save(progress_path, progress)
        state = json.loads(state_path.read_text())
        state.update(status="complete_source_input_actual_QA_pending_independent_acceptance",
                     input_process_pid=None, input_process_exit_status=0,
                     complete_months_QA=300, continuation_input_job_CPU_sofar=cpu(),
                     economic_execution_admitted=False,
                     next_action="Bindcomplete300monthactualinputs/QA/provenance; completeindependentinputacceptance andfullscienceplan, no fits yet")
        save(state_path, state)
    except BaseException as exc:
        progress.update(process_exit_status="error", error=type(exc).__name__ + ": " + str(exc),
                        failure_at_utc=datetime.now(UTC).isoformat(), input_job_CPU_sofar=cpu())
        save(progress_path, progress)
        state = json.loads(state_path.read_text())
        state.update(status="complete_input_same_scope_repair_required", input_process_exit_status="error",
                     input_job_error=progress["error"], continuation_input_job_CPU_sofar=cpu(),
                     economic_execution_admitted=False, next_action="Inspectretained actualfailure andpartialreceipt; same-scopefix/no quota reset")
        save(state_path, state)
        raise


if __name__ == "__main__":
    main()
