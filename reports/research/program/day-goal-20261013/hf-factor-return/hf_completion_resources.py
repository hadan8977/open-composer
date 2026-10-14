"""The single Root-amended completion ledger, including nonzero allowances."""

import argparse
import hashlib
import json
import math
import os
import re
import resource
from datetime import UTC, datetime
from pathlib import Path

P = Path(__file__).parent
LEDGER = P / "completion-resource-ledger.json"
AUTHORITY = P / "root-complete-economic-resource-amendment.json"


def snapshot(path=LEDGER):
    ledger = json.loads(Path(path).read_text())
    assert ledger["cap_CPU"] == 36000 and ledger["base_conservative_CPU"] == 460.49
    ids = [r["job_id"] for r in ledger["entries"]]
    assert len(ids) == len(set(ids)), "a job or nested receipt was charged twice"
    used = ledger["base_conservative_CPU"]
    commitments = {}
    for row in ledger["entries"]:
        assert row["status"] in ["closed", "reserved"]
        if row["status"] == "closed":
            assert row["charge_CPU"] >= 0
            used += row["charge_CPU"]
        else:
            assert row["upper_CPU"] > 0
            commitments[row["job_id"]] = row["upper_CPU"]
    return dict(
        cap_CPU=ledger["cap_CPU"],
        conservative_used_CPU=used,
        commitments=commitments,
        committed_CPU=sum(commitments.values()),
        remaining_uncommitted_CPU=ledger["cap_CPU"] - used - sum(commitments.values()),
    )


def process_limit(inclusive_upper, launcher_margin=5):
    assert inclusive_upper > launcher_margin
    # RLIMIT counts this process from launch, including already performed guards.
    return math.floor(inclusive_upper - launcher_margin)


def apply_job_limit(stage):
    job_id = os.environ["HF_COMPLETION_JOB_ID"]
    state = snapshot()
    assert job_id in state["commitments"], "job needs a cumulative ledger reservation"
    upper = state["commitments"][job_id]
    assert state["remaining_uncommitted_CPU"] >= 0
    authority = json.loads(AUTHORITY.read_text())["resource_amendment"]
    assert authority["new_cumulative_completion_cap_CPU"] == state["cap_CPU"]
    if stage == "resume-calibration":
        assert upper <= authority["calibration_continuation_inclusive_subcap_CPU"] == 1200
    elif stage == "linear":
        assert upper <= 1700
    elif stage == "accounts":
        assert upper <= 700
    elif stage == "hgb":
        projection = json.loads((P / "economic/full-resource-projection.json").read_text())
        assert upper <= math.ceil(projection["HGB_remaining_conservative_CPU"])
    os.sched_setaffinity(0, {0})
    limit = process_limit(upper)
    resource.setrlimit(resource.RLIMIT_CPU, (limit, limit))
    return state


def reserve(job_id, upper, scope):
    ledger = json.loads(LEDGER.read_text())
    assert not any(r["job_id"] == job_id for r in ledger["entries"])
    ledger["entries"].append(
        dict(
            job_id=job_id,
            status="reserved",
            upper_CPU=upper,
            scope=scope,
            registered_at=datetime.now(UTC).isoformat(),
        )
    )
    assert snapshot_from_ledger(ledger)["remaining_uncommitted_CPU"] >= 0
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")


def snapshot_from_ledger(ledger):
    # Same tally used before an atomic on-disk reservation update.
    used = ledger["base_conservative_CPU"] + sum(
        r["charge_CPU"] for r in ledger["entries"] if r["status"] == "closed"
    )
    commitments = sum(r["upper_CPU"] for r in ledger["entries"] if r["status"] == "reserved")
    return dict(remaining_uncommitted_CPU=ledger["cap_CPU"] - used - commitments)


def settle(job_id, receipt, allowance=0):
    ledger = json.loads(LEDGER.read_text())
    row = next(r for r in ledger["entries"] if r["job_id"] == job_id)
    assert row["status"] == "reserved", "cannot settle or charge the same job twice"
    text = Path(receipt).read_text()
    times = [
        float(re.search(k + r" time \(seconds\): ([\d.]+)", text).group(1))
        for k in ["User", "System"]
    ]
    measured = round(sum(times), 2)
    row.update(
        status="closed",
        measured_CPU=measured,
        nonzero_unmetered_allowance_CPU=allowance,
        charge_CPU=measured + allowance,
        receipt=dict(path=str(Path(receipt)), sha256=hashlib.sha256(text.encode()).hexdigest()),
        actual_exceeds_original_reservation=measured + allowance > row["upper_CPU"],
        settled_at=datetime.now(UTC).isoformat(),
    )
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    return snapshot()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    r = sub.add_parser("reserve")
    r.add_argument("job_id")
    r.add_argument("upper", type=float)
    r.add_argument("scope")
    s = sub.add_parser("settle")
    s.add_argument("job_id")
    s.add_argument("receipt")
    s.add_argument("--allowance", type=float, default=0)
    sub.add_parser("status")
    args = parser.parse_args()
    if args.action == "reserve":
        reserve(args.job_id, args.upper, args.scope)
    elif args.action == "settle":
        settle(args.job_id, args.receipt, args.allowance)
    print(json.dumps(snapshot()))
