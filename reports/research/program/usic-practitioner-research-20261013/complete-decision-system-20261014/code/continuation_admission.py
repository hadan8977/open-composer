"""Root's continuation amendment over the existing unique job ledger.

Historical receipts and consumer grants stay sealed. This helper adds the
prospective allocation to that ledger; it grants no HTTP or account replay.
"""

import json
import math
import os
import re
import resource
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from consumer_admission import (
    AUTHOR,
    REVIEWER,
    ROOT,
    TASK,
    P,
    bind,
    locked_ledger,
    receipt,
    save,
    usage,
    verify_bindings,
)

ROOT_GRANT = P / "economic-results/root-complete-resource-allocation-20261014.json"
ROOT_SHA = "04ea1aa4ec09e72f6b3f0e4145dac75594e3c3c65ab46c97c5d2d31cdb0898b5"
OLD_USED = Decimal("4229.65333")
CAP = Decimal("40229.65333")
STAGES = {"source_input": 1400, "first8": 10600, "remaining24": 22000, "interpretation": 2000}
LAUNCHER = 5


def decimal(value):
    return Decimal(str(value))


def current_grant():
    hold_path = ROOT / "reports/research/control/owner-compute-hold.json"
    day_path = ROOT / "reports/research/control/day-goal.json"
    hold = json.loads(hold_path.read_text())
    assert hold["research_paused"] is False
    tasks = [t for t in json.loads(day_path.read_text())["tasks"] if t.get("id") == TASK]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["owner"] == AUTHOR and task.get("active_owner", AUTHOR) == AUTHOR
    assert task["status"] in {
        "running_complete_task",
        "resources_granted_source_consumer_admission_in_progress",
    }
    assert task.get("root_resource_allocation") == str(ROOT_GRANT.relative_to(ROOT))
    assert os.sched_getaffinity(0) == {0}
    assert all(os.environ.get(k) == "1" for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS"))
    auth = dict(hold=bind(hold_path), task=task)
    assert bind(ROOT_GRANT)["sha256"] == ROOT_SHA
    grant = json.loads(ROOT_GRANT.read_text())
    assert grant["decision"] == "approve_complete_conditional_resource_allocation"
    assert grant["execution_owner"] == AUTHOR and grant["independent_reviewer"] == REVIEWER
    assert grant["task_id"] == TASK
    assert decimal(grant["CPU_allocation"]["new_continuation_cumulative_cap"]) == CAP
    assert decimal(grant["CPU_allocation"]["old_continuation_spent"]) == OLD_USED
    verify_bindings(grant["independent_review"])
    return grant, auth


def totals(folder):
    rows = [json.loads(p.read_text()) for p in folder.glob("*.json")]
    actual = sum((decimal(r["charged_CPU"]) for r in rows if r["status"] == "settled"), Decimal(0))
    inflight = sum(
        (decimal(r["combined_CPU_upper"]) for r in rows if r["status"] != "settled"), Decimal(0)
    )
    stages = {
        stage: sum(
            (
                decimal(r["charged_CPU"] if r["status"] == "settled" else r["combined_CPU_upper"])
                for r in rows
                if r.get("continuation_stage") == stage
            ),
            Decimal(0),
        )
        for stage in STAGES
    }
    assert actual >= OLD_USED, "historical ledger incomplete"
    return actual, inflight, stages


def reserve(job, upper, *, stage="source_input", entry="offline_input", bindings=None):
    grant, auth = current_grant()
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job)
    assert stage in STAGES and decimal(upper) > LAUNCHER
    # Root admitted preparation directly. Actual source/native economic work
    # requires its separately bound affected acceptance, checked at each entry.
    assert entry in {
        "offline_input",
        "independent_review",
        "source_witness",
        "consumer_probe",
        "matched_block",
    }
    if entry not in {"offline_input", "independent_review"}:
        assert bindings and "affected_review" in bindings
        verify_bindings(bindings["affected_review"])
    with locked_ledger() as folder:
        actual, inflight, stages = totals(folder)
        assert actual + inflight + decimal(upper) <= CAP
        assert stages[stage] + decimal(upper) <= STAGES[stage]
        row = dict(
            job_id=job,
            task=TASK,
            owner=AUTHOR,
            pid=None,
            reservation_writer_pid=os.getpid(),
            status="reserved",
            at_utc=datetime.now(UTC).isoformat(),
            cells=[],
            planned_entry=entry,
            continuation_stage=stage,
            root_allocation=bind(ROOT_GRANT),
            review=grant["independent_review"],
            authority=auth,
            combined_CPU_upper=float(upper),
            runtime_CPU_upper=0,
            empirical_CPU_upper=float(upper),
            runtime_actual_CPU=0,
            launcher_unknown_CPU=LAUNCHER,
            current_phase="admission",
            binding=bindings or {},
            historical_used_CPU=float(OLD_USED),
            pool_cumulative_cap_CPU=float(CAP),
            no_budget_reset=True,
            HTTP_admitted=entry == "source_witness",
            economic_admitted=entry == "matched_block",
        )
        with (folder / (job + ".json")).open("x") as f:
            f.write(json.dumps(row, indent=2) + "\n")
    return row


def claim(job, entry):
    current_grant()
    with locked_ledger() as folder:
        row = receipt(job)
        assert row["root_allocation"] == bind(ROOT_GRANT)
        assert row["status"] == "reserved" and row["pid"] is None
        assert row["planned_entry"] == entry
        verify_bindings(row["binding"])
        actual, inflight, _ = totals(folder)
        assert actual + inflight <= CAP
        row.update(pid=os.getpid(), status="running", current_phase=entry)
        save(folder / (job + ".json"), row)
    rearm(job)
    return row


def rearm(job):
    row = receipt(job)
    assert row["pid"] == os.getpid() and row["status"] == "running"
    own, child = usage()
    upper = row["combined_CPU_upper"] - LAUNCHER - child
    assert own + 12 < upper
    resource.setrlimit(resource.RLIMIT_CPU, (math.floor(upper - 10), math.floor(upper - 2)))


def remaining(job):
    row = receipt(job)
    own, child = usage()
    return row["combined_CPU_upper"] - LAUNCHER - own - child


def settle_outer(job, profile, outcome):
    # Closing an incurred charge remains necessary even if the owner pauses.
    assert bind(ROOT_GRANT)["sha256"] == ROOT_SHA
    text = Path(profile).read_text()
    user = re.search(r"User time \(seconds\): ([0-9.]+)", text)
    system = re.search(r"System time \(seconds\): ([0-9.]+)", text)
    assert user and system
    measured = decimal(user[1]) + decimal(system[1])
    with locked_ledger() as folder:
        row = receipt(job)
        assert row["status"] != "settled", "no repeated settlement"
        if row["pid"]:
            assert not Path(f"/proc/{row['pid']}").exists(), "postexit only"
        charged = measured + decimal(row["launcher_unknown_CPU"])
        row.update(
            status="settled",
            charged_CPU=float(charged),
            empirical_actual_CPU=float(charged),
            runtime_actual_CPU=0,
            outer_profile=bind(Path(profile).resolve()),
            outcome=outcome,
            postexit_reconciled=True,
            measured_inclusive_CPU=float(measured),
            settled_at_utc=datetime.now(UTC).isoformat(),
            empirical_cap_overrun_CPU=float(
                max(Decimal(0), charged - decimal(row["combined_CPU_upper"]))
            ),
        )
        save(folder / (job + ".json"), row)
        actual, inflight, stages = totals(folder)
        account = json.loads((P / "cumulative-accounting.json").read_text())
        account.update(
            new_measured_economic_CPU=float(actual),
            economic_remaining_CPU=float(CAP - actual),
            economic_active_commitment_CPU=float(inflight),
            continuation_cumulative_cap_CPU=float(CAP),
            prospective_used_CPU=float(actual - OLD_USED),
            prospective_remaining_CPU=float(CAP - actual),
            prospective_stage_committed_CPU={k: float(v) for k, v in stages.items()},
            root_resource_allocation=bind(ROOT_GRANT),
        )
        save(P / "cumulative-accounting.json", account)
    return row


def native_admission(job, review_path, permission):
    """Current native CLI, fresh memory and inclusive post-child CPU rearm."""
    import subprocess

    current_grant()
    row = receipt(job)
    proof = json.loads(Path(review_path).read_text())
    assert proof["verdict"] in {"approve_implementation", "approve_deep_plan"}
    assert proof["author"] == AUTHOR and proof["reviewer"] == REVIEWER and AUTHOR != REVIEWER
    assert proof[permission] is True
    assert row["pid"] == os.getpid() and row["status"] == "running"
    assert row["binding"]["affected_review"] == bind(Path(review_path))
    verify_bindings(proof["bindings"])
    rearm(job)

    def child(command):
        left = math.floor(remaining(job) - 12)
        assert left > 1
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CPU, (left, left + 1)),
        )

    memory = child(
        [
            "python3",
            str(ROOT / "scripts/memory_budget.py"),
            "admit",
            "--kind",
            "job",
            "--mem",
            "900",
        ]
    )
    assert memory.returncode == 0, memory.stdout + memory.stderr
    validation = child(
        [
            str(ROOT / ".venv/bin/oc"),
            "research",
            "iteration",
            "validate",
            "martin_complete_system_20261014_dev",
            "--json",
        ]
    )
    result = json.loads(validation.stdout)
    assert validation.returncode == 0 and result["status"] == "ok", result
    dossier = ROOT / "reports/research/iterations/martin_complete_system_20261014_dev"
    with locked_ledger() as folder:
        row = receipt(job)
        row.update(
            current_native=result,
            current_native_dossier={p.name: bind(p) for p in dossier.iterdir() if p.is_file()},
            fresh_memory_stdout=memory.stdout,
            native_child_CPU=usage()[1],
        )
        save(folder / (job + ".json"), row)
    rearm(job)
    return result
