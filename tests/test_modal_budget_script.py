"""Modal spend guard: worst-case pricing, unbilled window and the cap decision."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import modal_budget as mb  # noqa: E402

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def test_worst_case_prices_cpu_memory_and_gpu() -> None:
    assert mb.worst_case_usd(8, 32, 120, None) == round((8 * 0.0473 + 32 * 0.008) * 2, 4)
    assert mb.worst_case_usd(2, 8, 60, "T4") == round(2 * 0.0473 + 8 * 0.008 + 0.59, 4)


def test_worst_case_count_multiplies_for_parallel_shards() -> None:
    one = mb.worst_case_usd(2, 4, 30, None, count=1)
    three = mb.worst_case_usd(2, 4, 30, None, count=3)
    assert three == round(one * 3, 4)
    assert mb.worst_case_usd(2, 4, 30, None) == one, "count defaults to 1"


def test_recent_jobs_count_until_billing_catches_up() -> None:
    rows = [
        {"at": (NOW - timedelta(hours=1)).isoformat(), "timeout_min": 60, "worst_case_usd": 1.5},
        {"at": (NOW - timedelta(hours=10)).isoformat(), "timeout_min": 60, "worst_case_usd": 9.0},
    ]
    assert mb.unbilled_worst_case(rows, NOW) == 1.5


def test_cap_refuses_a_job_that_could_cross_it() -> None:
    assert mb.decide(20.0, 2.0, 2.9)["allowed"]
    assert not mb.decide(20.0, 2.0, 3.1)["allowed"]


def test_cost_parser_accepts_dollar_strings() -> None:
    assert mb._cost("$1,234.50") == 1234.5
    assert mb._cost(0.25) == 0.25
    assert mb._cost(None) == 0.0


def _check_args(job: str) -> list[str]:
    return ["check", "--job", job, "--cpu", "8", "--memory-gib", "32", "--timeout-min", "60"]


def _terminal_packet(tmp_path: Path) -> tuple[dict, Path]:
    """A failed, stopped job can settle only the exact unchanged reservation."""
    now = datetime.now(UTC)
    at = now - timedelta(minutes=5)
    row = {
        "at": at.isoformat(),
        "job": "same-job",
        "cpu": 8.0,
        "memory_gib": 32.0,
        "gpu": None,
        "count": 1,
        "timeout_min": 60.0,
        "worst_case_usd": mb.worst_case_usd(8, 32, 60, None),
        "billed_before_usd": 24.0,
    }

    def bind(path: Path) -> dict:
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def write(name: str, value: dict) -> dict:
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return bind(path)

    driver_path = tmp_path / "driver.log"
    driver_path.write_text("https://modal.com/apps/fixture/main/ap-fixture\n", encoding="utf-8")
    driver = bind(driver_path)
    evidence = {
        "schema_version": 1,
        "event_type": "completed_reservation_terminal_evidence",
        "reviewer": "/root",
        "verdict": "accept_completed_reservation_billing_upper_bound",
        "reservation": {
            "job": row["job"],
            "at": row["at"],
            "canonical_sha256": mb.reservation_sha256(row),
        },
        "app_id": "ap-fixture",
        "driver_log": driver,
        "completed_wall_seconds_upper_bound": 120,
        "provider_observation": write(
            "provider.json",
            {
                "app": "ap-fixture",
                "utc": now.isoformat(),
                "actual_cli_rows": [
                    {
                        "app_id": "ap-fixture",
                        "state": "stopped",
                        "tasks": "0",
                        "created_at": (at + timedelta(seconds=2)).isoformat(),
                        "stopped_at": (at + timedelta(seconds=55)).isoformat(),
                    }
                ],
            },
        ),
        "runtime_receipt": write(
            "runtime.json",
            {
                "run_id": row["job"],
                "runtime_manifest_sha256": "fixture-definition",
                "status": "failed_retained",
                "wall_seconds": 41.64,
                "resources_declared": {
                    "cpu_limit": 8.0,
                    "memory_limit_MiB": 32768,
                    "gpu": None,
                    "max_containers": 1,
                    "timeout_seconds": 3600,
                    "retries": 0,
                },
            },
        ),
        "operator_receipt": write(
            "operator.json",
            {
                "run_id": row["job"],
                "runtime_manifest_sha256": "fixture-definition",
                "driver_returncode": 1,
                "driver_log_sha256": driver["sha256"],
                "operator_wall_seconds": 61.32,
            },
        ),
    }
    write("evidence.json", evidence)
    return row, tmp_path / "evidence.json"


_OFFLINE_GUARD = """
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import modal_budget as budget
config = json.loads(sys.argv[2])
budget.LEDGER = Path(config['ledger'])
budget.billed_this_month = lambda: config['billed']
original_read = budget.read_ledger
def read(path):
    rows = original_read(path)
    Path(config['read_marker']).touch()
    if config.get('pause'):
        deadline = time.monotonic() + 5
        while not Path(config['release']).exists():
            if time.monotonic() > deadline:
                raise TimeoutError('test read was not released')
            time.sleep(.01)
    return rows
budget.read_ledger = read
Path(config['started']).touch()
sys.exit(budget.main(config['argv']))
"""


def _guard_process(tmp_path: Path, name: str, argv: list[str], *, pause: bool) -> subprocess.Popen:
    config = {
        "ledger": str(tmp_path / "ledger.jsonl"),
        "billed": 24.0,
        "argv": argv,
        "read_marker": str(tmp_path / f"{name}.read"),
        "started": str(tmp_path / f"{name}.started"),
        "pause": pause,
        "release": str(tmp_path / "release"),
    }
    return subprocess.Popen(
        [sys.executable, "-c", _OFFLINE_GUARD, str(Path(mb.__file__).parent), json.dumps(config)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for(path: Path) -> None:
    deadline = time.monotonic() + 4
    while not path.exists():
        assert time.monotonic() < deadline, f"test child did not reach {path.name}"
        time.sleep(0.01)


def _concurrent_guards(tmp_path: Path, first: list[str], second: list[str]) -> list[int]:
    processes = []
    try:
        processes.append(_guard_process(tmp_path, "first", first, pause=True))
        _wait_for(tmp_path / "first.read")
        processes.append(_guard_process(tmp_path, "second", second, pause=False))
        _wait_for(tmp_path / "second.started")
        # An unlocked second reader can consume the old ledger while the first
        # is paused; a locked reader waits, then sees the committed transaction.
        deadline = time.monotonic() + 0.5
        while not (tmp_path / "second.read").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        (tmp_path / "release").touch()
        for process in processes:
            stdout, stderr = process.communicate(timeout=5)
            assert process.returncode in (0, 2), (stdout, stderr)
        return [process.returncode for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


def test_concurrent_process_reservations_cannot_cross_cap(tmp_path: Path) -> None:
    assert _concurrent_guards(tmp_path, _check_args("first"), _check_args("second")) == [0, 2]
    rows = mb.read_ledger(tmp_path / "ledger.jsonl")
    assert len(rows) == 1
    assert rows[0]["worst_case_usd"] == 0.6344
    assert mb.decide(24, mb.unbilled_worst_case(rows, datetime.now(UTC)), 0)["allowed"]


def test_settlement_and_check_use_the_same_atomic_ledger(tmp_path: Path) -> None:
    row, evidence = _terminal_packet(tmp_path)
    original = json.dumps(row) + "\n"
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(original, encoding="utf-8")
    assert _concurrent_guards(
        tmp_path, ["settle", "--evidence", str(evidence)], _check_args("next-job")
    ) == [0, 0]
    assert ledger.read_text(encoding="utf-8").startswith(original)
    rows = mb.read_ledger(ledger)
    assert len(rows) == 3
    assert rows[1]["event_type"] == mb.SETTLEMENT
    assert rows[2]["job"] == "next-job"
    assert mb.unbilled_worst_case(rows, datetime.now(UTC)) == 0.6556


def test_concurrent_settlement_is_idempotent_and_preserves_failed_job(tmp_path: Path) -> None:
    row, evidence = _terminal_packet(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    argv = ["settle", "--evidence", str(evidence)]
    assert _concurrent_guards(tmp_path, argv, argv) == [0, 0]
    rows = mb.read_ledger(ledger)
    assert len(rows) == 2 and rows[0] == row
    assert rows[1]["completed_usage_upper_usd"] == 0.0212


def test_same_job_recheck_retains_all_reservations_and_exact_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row, evidence = _terminal_packet(tmp_path)
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(mb, "LEDGER", ledger)
    monkeypatch.setattr(mb, "billed_this_month", lambda: 0.0)
    assert mb.main(["settle", "--evidence", str(evidence)]) == 0
    assert mb.main(_check_args(row["job"])) == 0
    assert mb.main(_check_args(row["job"])) == 0
    before = ledger.read_bytes()
    assert mb.main(["settle", "--evidence", str(evidence)]) == 0
    assert ledger.read_bytes() == before
    rows = mb.read_ledger(ledger)
    assert len(rows) == 4 and rows[0] == row
    assert mb.unbilled_worst_case(rows, datetime.now(UTC)) == 1.29


def test_persistence_error_does_not_print_launch_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(mb, "LEDGER", ledger)
    monkeypatch.setattr(mb, "billed_this_month", lambda: 0.0)

    def failed_sync(fd: int) -> None:
        raise OSError("fixture disk sync failure")

    with monkeypatch.context() as patch:
        patch.setattr(mb.os, "fsync", failed_sync)
        with pytest.raises(OSError, match="disk sync failure"):
            mb.main(_check_args("same-job"))
    assert capsys.readouterr().out == ""
    # The conservative written reservation remains counted; the failed attempt
    # releases its lock, so another legitimate check can use the remaining cap.
    assert mb.main(_check_args("same-job")) == 0
    assert len(mb.read_ledger(ledger)) == 2


def test_existing_outer_allocation_flock_does_not_deadlock(tmp_path: Path) -> None:
    import shutil

    flock = shutil.which("flock")
    if flock is None:
        pytest.skip("existing DLSA caller uses the Linux flock command")
    config = {
        "ledger": str(tmp_path / "ledger.jsonl"),
        "billed": 24.0,
        "argv": _check_args("outer-lock-job"),
        "read_marker": str(tmp_path / "read"),
        "started": str(tmp_path / "started"),
    }
    result = subprocess.run(
        [
            flock,
            str(tmp_path / "modal-budget-allocation.lock"),
            sys.executable,
            "-c",
            _OFFLINE_GUARD,
            str(Path(mb.__file__).parent),
            json.dumps(config),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert len(mb.read_ledger(tmp_path / "ledger.jsonl")) == 1
