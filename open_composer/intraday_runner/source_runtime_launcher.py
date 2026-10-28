"""Finite capped parent: actual child exit, preserved failure, no retry/schedule.

Invoke inside existing run_capped + CPU0. It never reports a child as complete
from an output file alone, and never creates authorization or orders itself.
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from open_composer.intraday_runner.source_activity_reception import bind, save
from open_composer.intraday_runner.source_dispatch_journal import _ensure_durable_directory, _hash
from open_composer.intraday_runner.source_runtime_entry import entry_gate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--job-binding", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root, output = a.root.resolve(), a.output.absolute()
    binding = json.loads(a.job_binding.read_text())
    job, admission = entry_gate(
        root, binding, datetime.now(UTC), requested_output=output, allow_preparation=True
    )
    wall = job["timeout_seconds"]
    if type(wall) is not int or not 1 <= wall <= 900:
        raise ValueError("proportionate finite <=900 second native guard required")
    _ensure_durable_directory(output.parent)
    marker = output.with_suffix(".launch-consumed.json")
    with marker.open("x") as f:
        import os

        f.write(json.dumps(dict(job=binding, admission=admission)) + "\n")
        f.flush()
        os.fsync(f.fileno())
    _ensure_durable_directory(marker.parent)
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    with output.with_suffix(".native.log").open("xb") as log:
        completed = subprocess.run(
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=1s",
                str(wall),
                sys.executable,
                "-m",
                "open_composer.intraday_runner.source_runtime_entry",
                "--root",
                str(root),
                "--job-binding",
                str(a.job_binding.absolute()),
                "--output",
                str(output),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt = dict(
        exit_code=completed.returncode,
        completed_at=datetime.now(UTC).isoformat(),
        actual_child_cpu_seconds=(
            after.ru_utime + after.ru_stime - usage.ru_utime - usage.ru_stime
        ),
        child_maxrss_KiB=after.ru_maxrss,
        parent_overhead="UNKNOWN; measure outer launcher separately",
        job=binding,
        success=completed.returncode == 0,
    )
    if completed.returncode == 0:
        receipt["result"] = bind(output / "result.json")
    if completed.returncode == 0 and job["phase"] == "quantity":
        commit = json.loads((output / "commit.json").read_text())
        receipt["commit_sha256"] = _hash(commit)
        if datetime.fromisoformat(receipt["completed_at"]) > datetime.fromisoformat(
            commit["committed_at"]
        ):
            receipt.update(
                success=False, reason="actual native completion after nominal commitment"
            )
    save(output.with_suffix(".completion.json"), receipt)
    raise SystemExit(0 if receipt["success"] else (completed.returncode or 1))


if __name__ == "__main__":
    main()
