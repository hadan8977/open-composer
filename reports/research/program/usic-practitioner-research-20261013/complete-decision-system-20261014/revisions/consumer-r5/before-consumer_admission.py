"""Shared fail-closed admission and accounting for the existing two phases.

This is a local job receipt, not an execution service. Unknown interrupted
reservations stay committed until actual inclusive usage is reconciled.
"""

import fcntl
import hashlib
import json
import math
import os
import re
import resource
import signal
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[4]
AUTHOR = "7c7b1f3d-b962-4bbe-a2eb-87578888a8d5"
REVIEWER = "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3"
TASK = "MARTIN-COMPLETE-DECISION-SYSTEM-20261014"
ITER = "martin_complete_system_20261014_dev"
POOL = 7176.73
LAUNCHER_UNKNOWN_CPU = 5.0  # Reserved inside the empirical600, never outside1800.
CPU_STOP_REQUESTED = False


def empirical_allocation(alloc):
    # A later affected resource acceptance can allocate continuation within
    # the original pool. Its receipt must bind the settled prior usage; an
    # updated hash never automatically replenishes first600/1800.
    return alloc.get("empirical_continuation_CPU", alloc.get("first_empirical_CPU", 0))


def bind(path):
    path = Path(path)
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=str(path.relative_to(ROOT)), sha256=sha, bytes=path.stat().st_size)


def verify_bindings(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            actual = bind(ROOT / value["path"])
            assert actual["sha256"] == value["sha256"], value["path"]
            assert "bytes" not in value or actual["bytes"] == value["bytes"], value["path"]
        else:
            for v in value.values():
                verify_bindings(v)
    elif isinstance(value, list):
        for v in value:
            verify_bindings(v)


def authority():
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    assert hold["research_paused"] is False
    day = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    tasks = [t for t in day["tasks"] if t.get("id") == TASK]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["owner"] == AUTHOR and task["status"] == "running_complete_task"
    assert task.get("active_owner", AUTHOR) == AUTHOR  # Real conflicting field fails.
    assert os.sched_getaffinity(0) == {0}
    assert all(os.environ.get(k) == "1" for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS"))
    return dict(hold=bind(ROOT / "reports/research/control/owner-compute-hold.json"), task=task)


def accepted_package(cells):
    auth = authority()
    review = json.loads((P / "consumer-independent-review.json").read_text())
    assert review["verdict"] == "approve_implementation"
    assert review["author"] == AUTHOR and review["reviewer"] == REVIEWER and AUTHOR != REVIEWER
    assert review["economic_execution_admitted"] is True
    alloc = review["allocation"]
    assert alloc["CPU"] == 1 and 0 < alloc["memory_MiB"] <= 900
    assert 0 < alloc["economic_coreseconds"] <= POOL
    verify_bindings(review["bindings"])
    impl = json.loads((P / "consumer-implementation-manifest.json").read_text())
    # The grant must bind this actual package, including every executable file.
    assert any(
        isinstance(b, dict)
        and b.get("path") == str((P / "consumer-implementation-manifest.json").relative_to(ROOT))
        and b.get("sha256") == bind(P / "consumer-implementation-manifest.json")["sha256"]
        for b in review["bindings"].values()
    )
    verify_bindings(
        {
            k: impl[k]
            for k in (
                "files",
                "approved_plan",
                "science_review",
                "scientific_contracts",
                "cases",
                "input",
                "prepared_feature_prefix",
            )
        }
    )
    manifest = json.loads((P / "consumer-cases.json").read_text())
    ids = {c["cell_id"] for c in manifest["cells"]}
    assert len(ids) == 96 and len(cells) == len(set(cells)) and set(cells) <= ids
    return review, manifest, auth


def usage():
    own = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    return own.ru_utime + own.ru_stime, child.ru_utime + child.ru_stime


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(tmp, path)


@contextmanager
def locked_ledger():
    folder = P / "economic-results/reservations"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield folder


def committed(folder):
    rows = [json.loads(p.read_text()) for p in folder.glob("*.json")]
    settled = sum(r["charged_CPU"] for r in rows if r["status"] == "settled")
    inflight = sum(r["combined_CPU_upper"] for r in rows if r["status"] != "settled")
    account = json.loads((P / "cumulative-accounting.json").read_text())
    # Persisted accounting is a view of these same receipts, not an extra charge.
    used = max(settled, account.get("new_measured_economic_CPU", 0))
    return used, inflight


def reserve(job_id, cells, runtime_cpu, empirical_cpu, *, entry="consumer"):
    review, manifest, auth = accepted_package(cells)
    alloc = review["allocation"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id)
    assert entry in ("consumer", "frames")
    assert 0 <= runtime_cpu <= min(1200, alloc["runtime_feature_generation_CPU"])
    assert LAUNCHER_UNKNOWN_CPU < empirical_cpu <= empirical_allocation(alloc)
    total = runtime_cpu + empirical_cpu
    if "empirical_continuation_CPU" not in alloc:
        assert total <= 1800 and empirical_cpu <= 600
    assert total <= alloc["economic_coreseconds"]
    with locked_ledger() as folder:
        if (folder / (job_id + ".json")).exists():
            raise FileExistsError(folder / (job_id + ".json"))
        used, inflight = committed(folder)
        assert used + inflight + total <= POOL, (used, inflight, total)
        grant = bind(P / "consumer-independent-review.json")
        same_grant = [
            json.loads(p.read_text())
            for p in folder.glob("*.json")
            if json.loads(p.read_text())["review"] == grant
        ]
        runtime_committed = sum(
            r["runtime_actual_CPU"] if r["status"] == "settled" else r["runtime_CPU_upper"]
            for r in same_grant
        )
        empirical_committed = sum(
            r["empirical_actual_CPU"] if r["status"] == "settled" else r["empirical_CPU_upper"]
            for r in same_grant
        )
        assert runtime_committed + runtime_cpu <= alloc["runtime_feature_generation_CPU"]
        assert empirical_committed + empirical_cpu <= empirical_allocation(alloc)
        if "empirical_continuation_CPU" in alloc:
            # The continuation grant explicitly starts after these immutable
            # old receipts, rather than using a fresh review SHA as a reset.
            lineage = review["grant_lineage"]
            assert lineage["no_budget_reset"] is True
            assert lineage["consumed_CPU"] <= used
            assert alloc["economic_coreseconds"] <= POOL - lineage["consumed_CPU"]
        assert runtime_committed + empirical_committed + total <= alloc["economic_coreseconds"]
        row = dict(
            job_id=job_id,
            task=TASK,
            owner=AUTHOR,
            pid=None,
            planned_entry=entry,
            reservation_writer_pid=os.getpid(),
            status="reserved",
            at_utc=datetime.now(UTC).isoformat(),
            cells=cells,
            runtime_CPU_upper=runtime_cpu,
            empirical_CPU_upper=empirical_cpu,
            combined_CPU_upper=total,
            old_used_CPU=23.27,
            pool_original_cap_CPU=7200,
            review=grant,
            authority=auth,
            launcher_unknown_CPU=LAUNCHER_UNKNOWN_CPU,
            runtime_actual_CPU=0,
            native=None,
            current_phase="admission",
        )
        with (folder / (job_id + ".json")).open("x") as f:
            f.write(json.dumps(row, indent=2) + "\n")
    return row, manifest


def receipt(job_id):
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id)
    return json.loads((P / "economic-results/reservations" / (job_id + ".json")).read_text())


def update(job_id, **changes):
    with locked_ledger() as folder:
        row = receipt(job_id)
        assert row["status"] != "settled"
        row.update(changes)
        save(folder / (job_id + ".json"), row)
    return row


def claim_launch(job_id, entry):
    row = receipt(job_id)
    accepted_package(row["cells"])
    assert row["review"] == bind(P / "consumer-independent-review.json")
    with locked_ledger() as folder:
        row = receipt(job_id)
        assert row["status"] == "reserved" and row["pid"] is None
        assert row["planned_entry"] == entry
        row["pid"] = os.getpid()
        save(folder / (job_id + ".json"), row)
    return row


def native_admission(job_id):
    row = receipt(job_id)
    accepted_package(row["cells"])
    assert row["pid"] == os.getpid() and row["status"] == "reserved"
    empirical_limit(job_id)

    def limited_child(command):
        own, children = usage()
        remaining = math.floor(
            row["empirical_CPU_upper"] - row["launcher_unknown_CPU"] - own - children - 2
        )
        assert remaining > 1
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CPU, (remaining, remaining + 1)),
        )

    memory = limited_child(
        [
            "python3",
            str(ROOT / "scripts/memory_budget.py"),
            "admit",
            "--kind",
            "job",
            "--mem",
            "900",
        ],
    )
    assert memory.returncode == 0, memory.stdout + memory.stderr
    result = limited_child(
        [str(ROOT / ".venv/bin/oc"), "research", "iteration", "validate", ITER, "--json"],
    )
    native = json.loads(result.stdout)
    assert result.returncode == 0 and native["status"] == "ok", native
    # Native validates actual dossier/code/input bindings now, rather than an old claim.
    dossier = ROOT / "reports/research/iterations" / ITER
    current = {p.name: bind(p) for p in dossier.iterdir() if p.is_file()}
    return update(job_id, native=native, native_dossier=current, status="admitted")


def phase_admission(job_id, phase, *, child=False, claim_runtime=False):
    row = receipt(job_id)
    accepted_package(row["cells"])
    assert row["status"] == "admitted" and row["review"] == bind(
        P / "consumer-independent-review.json"
    )
    assert row["native"]["status"] == "ok"
    verify_bindings(row["native_dossier"])
    assert row["pid"] == (os.getppid() if child else os.getpid())
    with locked_ledger() as folder:
        used, inflight = committed(folder)
        assert used + inflight <= POOL
        if phase == "runtime" and (child or claim_runtime):
            current = receipt(job_id)
            assert "runtime_claimed_pid" not in current, "runtime phase already claimed"
            current["runtime_claimed_pid"] = os.getpid()
            save(folder / (job_id + ".json"), current)
    assert phase in ("runtime", "empirical") and row[phase + "_CPU_upper"] > 0
    if child:
        assert row["current_phase"] == "runtime"
    else:
        update(job_id, current_phase=phase)
    return row


def empirical_limit(job_id):
    row = receipt(job_id)
    own, children = usage()
    limit = (
        row["empirical_CPU_upper"]
        - row["launcher_unknown_CPU"]
        - (children - row["runtime_actual_CPU"])
    )
    assert own + 12 < limit
    # The first envelope exceeded empirical600 by1.856538 at OS SIG granularity.
    # Keep a genuine unwind/settlement margin and stop at small source intervals.
    soft = math.floor(limit - 10)
    hard = math.floor(limit - 2)
    resource.setrlimit(resource.RLIMIT_CPU, (soft, hard))

    def request_stop(signum, frame):
        global CPU_STOP_REQUESTED
        CPU_STOP_REQUESTED = True

    signal.signal(signal.SIGXCPU, request_stop)


def empirical_remaining(job_id):
    row = receipt(job_id)
    own, children = usage()
    remaining = (
        row["empirical_CPU_upper"]
        - row["launcher_unknown_CPU"]
        - own
        - (children - row["runtime_actual_CPU"])
    )
    return 0 if CPU_STOP_REQUESTED else remaining


def settle(job_id, outcome):
    # Called even on failed admission/native/runtime/empirical execution. A kill
    # that prevents this leaves the entire upper reservation in flight.
    with locked_ledger() as folder:
        row = receipt(job_id)
        assert row["status"] != "settled"
        account = json.loads((P / "cumulative-accounting.json").read_text())
        previous_settled = sum(
            json.loads(p.read_text())["charged_CPU"]
            for p in folder.glob("*.json")
            if json.loads(p.read_text())["status"] == "settled"
        )
        baseline = max(0, account.get("new_measured_economic_CPU", 0) - previous_settled)
        own, child = usage()
        runtime = row["runtime_actual_CPU"]
        empirical = own + child - runtime + row["launcher_unknown_CPU"]
        charged = runtime + empirical
        row.update(
            status="settled",
            outcome=outcome,
            runtime_actual_CPU=runtime,
            empirical_actual_CPU=empirical,
            charged_CPU=charged,
            runtime_cap_overrun_CPU=max(0, runtime - row["runtime_CPU_upper"]),
            empirical_cap_overrun_CPU=max(0, empirical - row["empirical_CPU_upper"]),
            settled_at_utc=datetime.now(UTC).isoformat(),
        )
        save(folder / (job_id + ".json"), row)
        account["new_measured_economic_CPU"] = baseline + sum(
            json.loads(p.read_text())["charged_CPU"]
            for p in folder.glob("*.json")
            if json.loads(p.read_text())["status"] == "settled"
        )
        account["economic_remaining_CPU"] = POOL - account["new_measured_economic_CPU"]
        save(P / "cumulative-accounting.json", account)


def verified_frames():
    result = json.loads((P / "frame-preparation-result.json").read_text())
    verify_bindings(result["manifest"])
    job = json.loads((ROOT / result["manifest"]["path"]).read_text())
    implementation = json.loads((P / "consumer-implementation-manifest.json").read_text())
    substitutions = implementation.get("prepared_frame_provenance_substitutions", [])
    for source in job["files"]:
        if bind(ROOT / source["path"]) == source:
            continue
        matches = [s for s in substitutions if s["source"] == source]
        assert len(matches) == 1 and matches[0]["role"] == "admission_only_no_feature_change"
        archived = matches[0]["archived"]
        verify_bindings(archived)
        assert archived["sha256"] == source["sha256"] and archived["bytes"] == source["bytes"]
        assert source["path"] == str((P / "code/consumer_admission.py").relative_to(ROOT))
    assert job["input_result"] == bind(P / "complete-input-v2-result.json")
    verify_bindings(
        {
            k: job[k]
            for k in (
                "input_result",
                "spec",
                "science_review",
                "completed_prefixes",
                "prefix_semantic_verification",
            )
        }
    )
    source_job = receipt(job["reservation_id"])
    assert source_job["frame_result"] == bind(P / "frame-preparation-result.json")
    verify_bindings(result["outputs"])
    expected = {f"{year}-{month:02}" for year in (2024, 2025) for month in range(1, 13)} | {
        "2023-12"
    }
    assert {Path(b["path"]).name[:7] for b in result["outputs"]} == expected
    assert len(result["outputs"]) == 25
    assert "trigger_masks" in result
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Prelaunch one original-pool reservation, no job execution"
    )
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--cells", nargs="*", default=[])
    parser.add_argument("--runtime-CPU", type=float, required=True)
    parser.add_argument("--empirical-CPU", type=float, required=True)
    parser.add_argument("--entry", choices=("consumer", "frames"), required=True)
    args = parser.parse_args()
    row, _ = reserve(
        args.job_id, args.cells, args.runtime_CPU, args.empirical_CPU, entry=args.entry
    )
    print(json.dumps(row))
