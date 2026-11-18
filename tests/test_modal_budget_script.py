"""Modal usage estimates and ledger accounting under the owner credit policy."""

from __future__ import annotations

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


def test_owner_allows_usage_beyond_former_monthly_cap() -> None:
    decision = mb.decide(20.0, 2.0, 8.0)
    assert decision["allowed"] and decision["cap_usd"] is None
    assert decision["projected_usd"] == 30.0


def test_cost_parser_accepts_dollar_strings() -> None:
    assert mb._cost("$1,234.50") == 1234.5
    assert mb._cost(0.25) == 0.25
    assert mb._cost(None) == 0.0


def _check_args(job: str) -> list[str]:
    return ["check", "--job", job, "--cpu", "8", "--memory-gib", "32", "--timeout-min", "60"]


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


def test_concurrent_process_reservations_are_both_recorded(tmp_path: Path) -> None:
    assert _concurrent_guards(tmp_path, _check_args("first"), _check_args("second")) == [0, 0]
    rows = mb.read_ledger(tmp_path / "ledger.jsonl")
    assert len(rows) == 2
    assert rows[0]["worst_case_usd"] == 0.6344
    assert mb.decide(24, mb.unbilled_worst_case(rows, datetime.now(UTC)), 0)["allowed"]


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
