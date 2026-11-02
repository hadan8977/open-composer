from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from open_composer.research import agent_workflow
from open_composer.research.agent_workflow import (
    codex_command,
    direction_lock,
    execute,
    run_round,
    run_series,
    validate_results,
)


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def root(tmp_path):
    save(tmp_path / "control.json", {"draft": False, "research": True})
    roles = {
        role: {
            "provider": "codex",
            "model": "test-model",
            "effort": "high",
            "prompt": f"prompts/{role}.md",
        }
        for role in ("worker", "reviewer", "lead")
    }
    save(tmp_path / "research/workflow.json", {"agent_memory": "900M", "roles": roles})
    (tmp_path / "research/example").mkdir()
    (tmp_path / "research/example/brief.md").write_text(
        "Check a deterministic fixture. No market claim."
    )
    (tmp_path / "prompts").mkdir()
    for role in roles:
        (tmp_path / f"prompts/{role}.md").write_text(role)
    (tmp_path / "research/example/raw.json").write_text('{"fixture_profit": 2}')
    save(
        tmp_path / "research/example/results.json",
        {
            "direction": "example",
            "kind": "diagnostic",
            "engine": "test fixture",
            "source_artifacts": ["research/example/raw.json"],
            "data_and_exposure": "fixture only",
            "costs": "not a financial result",
            "baseline": "fixture",
            "n_trials": 0,
            "net_profit_usd": None,
            "baseline_net_profit_usd": None,
            "dsr": None,
            "dsr_note": "not applicable to a fixture",
            "limitations": ["No economic evidence"],
        },
    )
    return tmp_path


def fake_agent(calls, replies=None, after=None):
    def run(command, prompt, folder, timeout):
        phase = folder.name
        calls.append(phase)
        assert command[0].endswith("scripts/run_capped.sh")
        assert timeout > 0 and "Brief:" in prompt
        reply = {
            "status": "complete",
            "summary": "Fixture completed; no research claim",
            "decision": "accept" if phase in ("reviewer", "plan_review") else "park",
            "results": "research/example/results.json",
            "next_brief": None,
            "checkpoint": None,
        }
        reply.update((replies or {}).get(agent_workflow.phase_kind(phase), {}))
        save(folder / "reply.json", reply)
        if after:
            after(phase)
        session = command[-2] if "resume" in command else f"fixture-{phase}"
        return {"session": session, "usage": {"input_tokens": 3}, "exit_code": 0}

    return run


@pytest.mark.parametrize("review_plan,review_result", [(False, False), (True, True)])
def test_finite_round_uses_neutral_files_and_separate_sessions(root, review_plan, review_result):
    calls = []
    state = run_round(
        root,
        "example",
        "r1",
        10,
        review_plan=review_plan,
        review_result=review_result,
        execute_fn=fake_agent(calls),
    )
    expected = ["plan_review", "worker", "reviewer", "lead"] if review_plan else ["worker", "lead"]
    assert calls == expected
    assert state["status"] == "round_finished"
    assert state["phases"]["worker"]["session"] != state["phases"]["lead"]["session"]
    assert state["phases"]["worker"]["requested_runtime"]["provider"] == "codex"
    assert "research/example/runs/r1/run.json" in (root / "board.md").read_text()
    assert len((root / "board.md").read_bytes()) <= 400
    with pytest.raises(FileExistsError):
        run_round(root, "example", "r1", 10, execute_fn=fake_agent(calls))
    assert len(calls) == len(expected)
    assert state["efficiency"]["tokens"]["observed_total_tokens"] == 3 * len(expected)
    assert state["efficiency"]["tokens"]["total_tokens"] is None
    assert state["efficiency"]["counts"]["economic_comparisons"] is None


@pytest.mark.parametrize(
    "control", [{"draft": True, "research": True}, {"draft": False, "research": False}]
)
def test_draft_or_paused_authority_launches_nothing(root, control):
    save(root / "control.json", control)
    calls = []
    with pytest.raises(ValueError, match="not been enabled"):
        run_round(root, "example", "r1", 10, execute_fn=fake_agent(calls))
    assert not calls and not (root / "research/example/runs").exists()


def test_legacy_hold_is_not_overridden_by_new_control(root):
    save(root / "reports/research/control/owner-compute-hold.json", {"research_allowed": False})
    with pytest.raises(ValueError, match="Legacy research hold"):
        run_round(root, "example", "r1", 10, execute_fn=fake_agent([]))


def test_rejected_new_scope_never_reaches_worker(root):
    calls = []
    state = run_round(
        root,
        "example",
        "r1",
        10,
        review_plan=True,
        execute_fn=fake_agent(calls, {"plan_review": {"decision": "revise", "results": None}}),
    )
    assert state["status"] == "scope_needs_revision" and calls == ["plan_review"]


def test_blocked_worker_goes_directly_to_lead(root):
    calls = []
    state = run_round(
        root,
        "example",
        "r1",
        10,
        execute_fn=fake_agent(calls, {"worker": {"status": "blocked", "results": None}}),
    )
    assert calls == ["worker", "lead"]
    assert state["phases"]["worker"]["status"] == "blocked"


def test_missing_raw_evidence_cannot_reach_result_review(root):
    (root / "research/example/raw.json").unlink()
    calls = []
    with pytest.raises(ValueError, match="engine artifact"):
        run_round(root, "example", "r1", 10, execute_fn=fake_agent(calls))
    assert calls == ["worker"]
    state = json.loads((root / "research/example/runs/r1/run.json").read_text())
    assert state["status"] == "interrupted_or_failed"
    assert state["phases"]["worker"]["session"] == "fixture-worker"


def test_permission_is_rechecked_between_agents(root):
    def pause_after_worker(phase):
        if phase == "worker":
            save(root / "control.json", {"draft": False, "research": False})

    calls = []
    with pytest.raises(ValueError, match="not been enabled"):
        run_round(root, "example", "r1", 10, execute_fn=fake_agent(calls, after=pause_after_worker))
    assert calls == ["worker"]


def test_direction_lock_rejects_concurrent_round(root):
    with direction_lock(root / "research/example/.round.lock"):
        with pytest.raises(ValueError, match="already has"):
            run_round(root, "example", "r2", 10, execute_fn=fake_agent([]))


def test_timeout_stops_local_process_and_keeps_identity(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        execute([sys.executable, "-c", "import time; time.sleep(30)"], "", tmp_path, 0.1)
    pid = json.loads((tmp_path / "process.json").read_text())["pid"]
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert (tmp_path / "events.jsonl").exists()


def test_failed_transport_keeps_session_for_same_session_recovery(tmp_path):
    program = (
        'import json; print(json.dumps({"type":"thread.started","thread_id":"old-session"})); '
        "raise SystemExit(7)"
    )
    actual = execute([sys.executable, "-c", program], "", tmp_path, 5)
    assert actual == {"session": "old-session", "usage": None, "exit_code": 7}


def test_provider_switch_is_explicit_and_does_not_rewrite_science(root):
    config = json.loads((root / "research/workflow.json").read_text())["roles"]["lead"]
    config["provider"] = "claude"
    with pytest.raises(ValueError, match="adapter"):
        codex_command(root, config, root / "out", root / "schema")
    result = validate_results(root, "research/example/results.json", "example")
    assert "provider" not in result.model_dump() and "model" not in result.model_dump()


def test_lead_cannot_finish_with_empty_continuation(root):
    with pytest.raises(ValueError, match="concrete next brief"):
        run_round(
            root, "example", "r1", 10, execute_fn=fake_agent([], {"lead": {"decision": "continue"}})
        )


def test_series_follows_concrete_repair_without_fixed_variant_count(root):
    calls = []
    save(root / "research/example/checkpoint.json", {"fixture": True})
    (root / "research/next_direction").mkdir()
    (root / "research/next_direction/next.md").write_text("Continue the accepted scope elsewhere.")
    next_result = json.loads((root / "research/example/results.json").read_text())
    next_result["direction"] = "next_direction"
    save(root / "research/next_direction/results.json", next_result)

    def run(command, prompt, folder, timeout):
        number = folder.parent.name.rsplit("-", 1)[1]
        replies = (
            {"lead": {"decision": "park", "next_brief": "research/next_direction/next.md"}}
            if number == "1"
            else {
                phase: {"results": "research/next_direction/results.json"}
                for phase in ("worker", "lead")
            }
        )
        return fake_agent(calls, replies)(command, prompt, folder, timeout)

    result = run_series(root, "example", "series", 10, execute_fn=run)
    assert calls == ["worker", "lead"] * 2
    assert len(result["rounds"]) == 2 and result["status"] == "decision_handoff"
    first = root / "research/example/runs/series-1"
    assert (first / "brief.md").read_text() != (
        root / "research/next_direction/next.md"
    ).read_text()
    assert result["rounds"][1].startswith("research/next_direction/")
    assert (first / "worker/results.json").is_file()


def test_series_does_not_relaunch_a_blocked_worker(root):
    calls = []
    (root / "research/example/next.md").write_text("Diagnose the existing job.")
    result = run_series(
        root,
        "example",
        "series",
        10,
        execute_fn=fake_agent(
            calls,
            {
                "worker": {"status": "blocked", "results": None},
                "lead": {"decision": "repair", "next_brief": "research/example/next.md"},
            },
        ),
    )
    assert calls == ["worker", "lead"] and result["status"] == "blocked_checkpoint"


@pytest.mark.parametrize("status", ["running", "interrupted_or_failed"])
def test_new_id_cannot_bypass_an_unresolved_crashed_run(root, status):
    save(
        root / "research/example/runs/old/run.json",
        {
            "status": status,
            "active_phase": "worker",
            "phases": {"worker": {"session": "old-session", "exit_code": 1}},
        },
    )
    calls = []
    with pytest.raises(ValueError, match="unfinished job"):
        run_round(root, "example", "new-id", 10, execute_fn=fake_agent(calls))
    assert not calls


def test_checkpoint_is_saved_even_when_result_validation_fails(root):
    save(root / "research/example/remote-job.json", {"remote_id": "fixture-job"})
    (root / "research/example/raw.json").unlink()
    with pytest.raises(ValueError, match="engine artifact"):
        run_round(
            root,
            "example",
            "r1",
            10,
            execute_fn=fake_agent(
                [],
                {
                    "worker": {"checkpoint": "research/example/remote-job.json"},
                },
            ),
        )
    state = json.loads((root / "research/example/runs/r1/run.json").read_text())
    assert state["phases"]["worker"]["checkpoint"] == "research/example/remote-job.json"
    with pytest.raises(ValueError, match="unfinished job"):
        run_round(root, "example", "r2", 10, execute_fn=fake_agent([]))


def test_timeout_also_stops_descendant_that_ignores_term(tmp_path):
    child_pid = tmp_path / "child.pid"
    child_code = (
        "import os,signal,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        f"Path({str(child_pid)!r}).write_text(str(os.getpid())); time.sleep(30)"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child_code!r}]); time.sleep(30)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        execute([sys.executable, "-c", parent_code], "", tmp_path, 1)
    pid = int(child_pid.read_text())
    stat = Path(f"/proc/{pid}/stat")
    for _ in range(50):
        if not stat.exists() or stat.read_text().split()[2] == "Z":
            break
        time.sleep(0.02)
    else:
        pytest.fail("Descendant survived timeout cleanup")


def test_metadata_write_failure_cleans_up_launched_process(tmp_path, monkeypatch):
    processes = []
    popen = subprocess.Popen

    def tracked_popen(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    def cannot_write(*_args):
        raise OSError("fixture disk write failure")

    monkeypatch.setattr(agent_workflow.subprocess, "Popen", tracked_popen)
    monkeypatch.setattr(agent_workflow, "write_json", cannot_write)
    with pytest.raises(OSError, match="disk write"):
        execute([sys.executable, "-c", "import time; time.sleep(30)"], "", tmp_path, 5)
    assert len(processes) == 1 and processes[0].poll() is not None
