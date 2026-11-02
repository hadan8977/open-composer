from __future__ import annotations

import fcntl
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "research_usage", Path(__file__).resolve().parents[1] / "scripts/research_usage.py"
)
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


def limits():
    return {
        "rateLimits": {
            "limitId": "codex",
            "primary": {"usedPercent": 25, "windowDurationMins": 300, "resetsAt": 1900000000},
            "secondary": {"usedPercent": 40, "windowDurationMins": 10080, "resetsAt": 1900000000},
        }
    }


@pytest.fixture
def run_folder(tmp_path):
    root = tmp_path / "repo"
    folder = root / "research/example/runs/r1"
    folder.mkdir(parents=True)
    (root / "control.json").write_text('{"research":true,"unchanged":"authority"}')
    state = {
        "direction": "example",
        "run_id": "r1",
        "phases": {
            "worker": {
                "status": "complete",
                "exit_code": 0,
                "usage": {"input_tokens": 10, "cached_input_tokens": 3, "output_tokens": 4},
            },
            "reviewer": {"status": "complete", "exit_code": 0, "usage": None},
            "lead": {"status": "starting", "usage": {"input_tokens": 99}},
        },
    }
    (folder / "run.json").write_text(json.dumps(state))
    return root, folder


def test_account_snapshot_is_immutable_while_all_phase_tokens_refresh(run_folder):
    root, folder = run_folder
    before = (root / "control.json").read_bytes()
    calls = []

    def reader(timeout):
        calls.append(timeout)
        return limits()

    result = usage.record_usage(root, folder, reader=reader)
    body = (folder / "usage.json").read_bytes()
    assert result["account_usage"]["available"] is True
    assert result["account_usage"]["weekly_windows"][0]["used_percent"] == 40
    assert "Shared authenticated account" in result["account_usage"]["scope"]
    tokens = result["completed_phase_tokens"]
    assert tokens["observed_totals"] == {
        "input_tokens": 109,
        "cached_input_tokens": 3,
        "output_tokens": 4,
    }
    assert tokens["phases_with_missing_fields"] == ["reviewer", "lead"]
    assert "lead" in tokens["by_phase"]
    assert tokens["unfinished_phases"] == ["lead"]
    assert tokens["total_tokens"] is None
    assert result["authority_changed"] is False and result["automatic_stop"] is False
    assert usage.record_usage(root, folder, reader=reader) == result
    assert calls == [20] and (folder / "usage.json").read_bytes() == body
    assert (root / "control.json").read_bytes() == before
    state = json.loads((folder / "run.json").read_text())
    state["phases"]["lead"].update(
        status="complete",
        exit_code=0,
        usage={"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
    )
    (folder / "run.json").write_text(json.dumps(state))
    refreshed = usage.record_usage(root, folder, reader=reader)
    assert calls == [20] and refreshed["account_usage"] == result["account_usage"]
    assert refreshed["completed_phase_tokens"]["observed_total_tokens"] == 124
    assert refreshed["completed_phase_tokens"]["phases_with_missing_fields"] == ["reviewer"]


def test_unavailable_reading_is_saved_and_not_retried(run_folder):
    root, folder = run_folder
    calls = []

    def reader(_timeout):
        calls.append(True)
        raise TimeoutError("do not expose provider/auth details")

    result = usage.record_usage(root, folder, reader=reader)
    assert result["account_usage"]["available"] is False
    assert result["account_usage"]["unavailable_reason"] == "TimeoutError"
    assert "provider/auth" not in (folder / "usage.json").read_text()
    assert usage.record_usage(root, folder, reader=reader) == result and len(calls) == 1


def test_crashed_measurement_marker_prevents_a_second_request(run_folder):
    root, folder = run_folder
    (folder / "usage-attempt.json").write_text('{"helper_pid":123}')

    def forbidden(_timeout):
        pytest.fail("An interrupted measurement must not trigger another account read")

    result = usage.record_usage(root, folder, reader=forbidden)
    assert result["account_usage"]["unavailable_reason"] == "previous_measurement_incomplete"


def test_concurrent_measurement_does_not_duplicate_request(run_folder):
    root, folder = run_folder
    with (folder / ".usage.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="already running"):
            usage.record_usage(root, folder, reader=lambda _: pytest.fail("No duplicate request"))


@pytest.mark.parametrize("where", ["outside", "wrong_shape", "missing", "wrong_identity"])
def test_only_existing_matching_repository_rounds_are_allowed(run_folder, where):
    root, folder = run_folder
    if where == "outside":
        folder = root.parent / "outside"
        folder.mkdir()
    elif where == "wrong_shape":
        folder = root / "research/example"
    elif where == "missing":
        folder = root / "research/example/runs/missing"
    else:
        (folder / "run.json").write_text('{"direction":"wrong","run_id":"r1"}')
    with pytest.raises(ValueError):
        usage.record_usage(
            root, folder, reader=lambda _: pytest.fail("Invalid run cannot read quota")
        )


def test_multi_bucket_windows_are_separate_and_reset_can_be_unknown():
    result = limits()
    result["rateLimitsByLimitId"] = {
        "codex": result["rateLimits"],
        "another_bucket": {
            "primary": {"usedPercent": 60, "windowDurationMins": 10080, "resetsAt": None}
        },
    }
    windows = usage.weekly_windows(result)
    assert [row["used_percent"] for row in windows] == [40, 60]
    assert windows[1]["resets_at_utc"] is None


@pytest.mark.parametrize("mutate", ["no_weekly", "invalid_percent"])
def test_non_weekly_or_invalid_measurements_remain_unavailable(run_folder, mutate):
    root, folder = run_folder
    result = limits()
    if mutate == "no_weekly":
        result["rateLimits"]["secondary"] = None
    else:
        result["rateLimits"]["secondary"]["usedPercent"] = True
    snapshot = usage.record_usage(root, folder, reader=lambda _: result)
    assert snapshot["account_usage"]["available"] is False
    assert "weekly_windows" not in snapshot["account_usage"]


def fake_server(tmp_path, *, fail=False, silent=False):
    processes = []
    messages = tmp_path / "rpc-methods.jsonl"
    program = (
        "import json,sys,time; from pathlib import Path\n"
        f"messages=Path({str(messages)!r})\n"
        + ("time.sleep(30)\n" if silent else "")
        + "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " with messages.open('a') as stream:stream.write(request['method']+'\\n')\n"
        " if request['method']=='initialize':\n"
        + (
            "  print(json.dumps({'id':1,'error':{'code':1}}),flush=True)\n"
            if fail
            else "  print(json.dumps({'id':1,'result':{}}),flush=True)\n"
            "  print(json.dumps({'id':1,'result':{}}),flush=True)\n"
        )
        + " if request['method']=='account/rateLimits/read':\n"
        f"  print(json.dumps({{'id':2,'result':{limits()!r}}}),flush=True)\n"
        "time.sleep(30)\n"
    )

    def popen(command, **kwargs):
        assert command == ["codex", "app-server"]
        process = subprocess.Popen([sys.executable, "-u", "-c", program], **kwargs)
        processes.append(process)
        return process

    return popen, processes, messages


def test_transport_issues_only_one_read_and_cleans_up_offline_server(tmp_path):
    popen, processes, messages = fake_server(tmp_path)
    result = usage.read_account_limits(timeout=3, popen=popen)
    assert result == limits()
    methods = messages.read_text().splitlines()
    assert methods == ["initialize", "initialized", "account/rateLimits/read"]
    assert processes[0].poll() is not None


@pytest.mark.parametrize("failure", ["rpc_error", "timeout"])
def test_transport_failure_cleans_up_offline_server(tmp_path, failure):
    popen, processes, _ = fake_server(
        tmp_path, fail=failure == "rpc_error", silent=failure == "timeout"
    )
    with pytest.raises((RuntimeError, TimeoutError)):
        usage.read_account_limits(timeout=0.2, popen=popen)
    assert processes[0].poll() is not None
