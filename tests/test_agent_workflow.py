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
    agent_command,
    claude_command,
    direction_lock,
    execute,
    run_round,
    run_series,
    validate_results,
)
from open_composer.research.process_identity import identity, process_state


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_board_update_preserves_existing_row_bytes(tmp_path, ending):
    board = tmp_path / "board.md"
    original = b"| old | example | received | old/run.json |" + ending
    board.write_bytes(original)
    agent_workflow.update_board(
        tmp_path, "| new | example | running | new/run.json |\n", "new/run.json"
    )
    agent_workflow.update_board(
        tmp_path, "| new | example | done | new/run.json |\n", "new/run.json"
    )
    assert board.read_bytes() == original + b"| new | example | done | new/run.json |\n"


@pytest.fixture
def root(tmp_path):
    save(tmp_path / "control.json", {"draft": False, "research": True})
    save(
        tmp_path / "config/memory-budget.json",
        {"oc_max_mb": 2200, "job_max_mb": 2458, "reserve_mb": 500, "heavy_job_mb": 200},
    )
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
        assert any(Path(part).name in ("run_capped.sh", "run_capped.py") for part in command[:2])
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


@pytest.mark.parametrize("science_decision", [False, True])
def test_blocked_worker_only_reaches_lead_for_material_science(root, science_decision):
    (root / "research/example/next.md").write_text("Decide the changed economic scope.")
    worker = {"status": "blocked", "results": None}
    if science_decision:
        worker.update(decision="revise", next_brief="research/example/next.md", next_review="plan")
    calls = []
    state = run_round(
        root,
        "example",
        "r1",
        10,
        execute_fn=fake_agent(calls, {"worker": worker}),
    )
    assert calls == (["worker", "lead"] if science_decision else ["worker"])
    assert state["status"] == ("round_finished" if science_decision else "worker_checkpoint")
    assert state["phases"]["worker"]["status"] == "blocked"


@pytest.mark.parametrize("old_provider", ["codex", "claude"])
def test_checkpoint_resume_keeps_worker_session_and_uses_current_codex_model(root, old_provider):
    calls = []
    state = run_round(
        root,
        "example",
        "r1",
        10,
        execute_fn=fake_agent(calls, {"worker": {"status": "blocked", "results": None}}),
    )
    prior = state["phases"]["worker"]["requested_runtime"]
    prior.update(provider=old_provider, model="old-model", effort="xhigh")
    save(root / "research/example/runs/r1/run.json", state)

    def transport(command, prompt, folder, timeout):
        reply = fake_agent(calls)(command, prompt, folder, timeout)
        if folder.name == "worker_resume_1":
            if old_provider == "claude":
                reply["session"] = command[command.index("--resume") + 1]
            else:
                assert command[command.index("--model") + 1] == "test-model"
        return reply

    resumed = run_round(root, "example", "r1", 10, resume=True, execute_fn=transport)
    assert calls == ["worker", "worker_resume_1", "lead"]
    worker = resumed["phases"]["worker_resume_1"]
    assert worker["session"] == worker["resumes_session"] == "fixture-worker"
    assert worker["requested_runtime"]["effort"] == "high"
    assert worker["requested_runtime"]["provider"] == old_provider
    assert worker["requested_runtime"]["model"] == ("test-model" if old_provider == "codex" else "old-model")
    assert resumed["phases"]["worker"]["requested_runtime"]["effort"] == "xhigh"
    assert resumed["phases"]["worker"]["requested_runtime"]["model"] == "old-model"
    assert resumed["phases"]["worker"]["resolved_by"] == "worker_resume_1"
    assert resumed["status"] == "round_finished"


def test_plan_reviewer_resume_uses_current_codex_model(root):
    calls = []
    state = run_round(
        root, "example", "r1", 10, review_plan=True,
        execute_fn=fake_agent(calls, {"plan_review": {"decision": "revise", "results": None}}),
    )
    state["phases"]["plan_review"]["requested_runtime"]["model"] = "old-reviewer"
    save(root / "research/example/runs/r1/run.json", state)
    resumed = run_round(
        root, "example", "r1", 10, resume=True,
        execute_fn=fake_agent(calls, {"plan_review": {"decision": "accept"}}),
    )
    assert resumed["phases"]["plan_review"]["requested_runtime"]["model"] == "old-reviewer"
    reviewer = resumed["phases"]["plan_review_resume_1"]
    assert reviewer["requested_runtime"]["model"] == "test-model"
    assert reviewer["resumes_session"] == "fixture-plan_review"


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


def test_agent_admission_waits_in_place_and_preserves_other_stops(root, monkeypatch):
    run = root / "research/example/runs/admission"
    run.mkdir(parents=True)
    clock, attempts, waits = [0.0], [], []
    scenario = ["recover"]
    state = {"status": "running", "phases": {"plan_review": {"status": "starting"}}}

    def admission(command, **kwargs):
        assert command[-3:] == ["admit", "--kind", "agent"]
        attempts.append(clock[0])
        if scenario[0] == "other":
            return subprocess.CompletedProcess(command, 2, "", "unauthorized")
        refused = clock[0] < 30
        return subprocess.CompletedProcess(
            command,
            2 if refused else 0,
            "",
            "refuse: headroom 180 MB < 200 MB for a new agent\n" if refused else "admit: ok\n",
        )

    def wait(seconds):
        observed = json.loads((run / "run.json").read_text())
        assert observed["status"] == observed["phases"]["plan_review"]["status"] == "resource_wait"
        waits.append(seconds)
        clock[0] += seconds
        if scenario[0] == "pause":
            save(root / "control.json", {"draft": False, "research": False})

    monkeypatch.setattr(agent_workflow.subprocess, "run", admission)
    monkeypatch.setattr(agent_workflow.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(agent_workflow.time, "sleep", wait)
    agent_workflow.await_agent_admission(root, run, state, "plan_review", 60)
    assert attempts == [0, 30] and sum(waits) == pytest.approx(30)
    phase = state["phases"]["plan_review"]
    assert phase["resource_wait"]["state"] == "admitted" and phase["status"] == "starting"
    assert [item["exit_code"] for item in phase["admission_attempts"]] == [2, 0]
    assert "session" not in phase and not (run / "plan_review").exists()
    scenario[0] = "other"
    with pytest.raises(subprocess.CalledProcessError):
        agent_workflow.await_agent_admission(root, run, state, "plan_review", 60)
    scenario[0], clock[0] = "pause", 0
    attempts.clear()
    with pytest.raises(ValueError, match="not been enabled"):
        agent_workflow.await_agent_admission(root, run, state, "plan_review", 60)
    assert attempts == [0] and phase["resource_wait"]["state"] == "paused"


def test_direction_lock_rejects_concurrent_round(root):
    with direction_lock(root / "research/example/.round.lock"):
        with pytest.raises(ValueError, match="already has"):
            run_round(root, "example", "r2", 10, execute_fn=fake_agent([]))


def test_timeout_stops_local_process_and_keeps_identity(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        execute([sys.executable, "-c", "import time; time.sleep(30)"], "", tmp_path, 0.1)
    saved = json.loads((tmp_path / "process.json").read_text())
    if os.name == "nt":
        assert agent_workflow.process_state(saved) == "exited"
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(saved["pid"], 0)
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
    unknown = dict(config, provider="gemini")
    with pytest.raises(ValueError, match="adapter"):
        agent_command(root, unknown, root / "out", root / "schema")
    result = validate_results(root, "research/example/results.json", "example")
    assert "provider" not in result.model_dump() and "model" not in result.model_dump()


def test_reply_dispatch_schema_requires_every_field():
    schema = agent_workflow.reply_dispatch_schema()
    assert schema["required"] == list(schema["properties"])
    assert "default" not in schema["properties"]["next_review"]


def test_claude_command_matches_the_documented_print_boundary(root):
    schema = agent_workflow.reply_dispatch_schema()
    role = {
        "provider": "claude",
        "model": "claude-test-model",
        "effort": "xhigh",
        "prompt": "prompts/worker.md",
    }
    command = claude_command(root, role, root / "out", schema)
    assert command[:4] == ["env", "-C", str(root), "claude"]
    assert command[4:6] == ["-p", "--output-format"] and "stream-json" in command
    assert "--verbose" in command and "bypassPermissions" in command
    assert command[command.index("--effort") + 1] == "xhigh"
    schema_argument = json.loads(command[command.index("--json-schema") + 1])
    assert schema_argument["required"] == list(schema_argument["properties"])
    session = command[command.index("--session-id") + 1]
    assert len(session) == 36 and "--resume" not in command
    resumed = claude_command(root, role, root / "out", schema, session="saved-session")
    assert resumed[resumed.index("--resume") + 1] == "saved-session"
    assert "--session-id" not in resumed
    assert agent_command(root, role, root / "out", schema)[3] == "claude"


def test_claude_round_reads_structured_reply_and_normalizes_usage(root):
    workflow = json.loads((root / "research/workflow.json").read_text())
    for role in workflow["roles"].values():
        role.update(provider="claude", model="claude-test-model")
    save(root / "research/workflow.json", workflow)
    reply = {
        "status": "complete",
        "summary": "Synthetic Claude transport; no model or research execution",
        "decision": "continue",
        "results": "research/example/results.json",
        "next_brief": None,
        "checkpoint": None,
    }

    def transport(command, prompt, folder, _timeout):
        assert any(Path(part).name in ("run_capped.sh", "run_capped.py") for part in command[:2])
        assert command[command.index("--") + 4] == "claude" and "--json-schema" in command
        phase = folder.name
        session = command[command.index("--session-id") + 1]
        payload = dict(reply, decision="park", results=None) if phase == "lead" else reply
        events = [
            {"type": "system", "subtype": "init", "session_id": session},
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": session,
                "usage": {
                    "input_tokens": 10,
                    "cache_read_input_tokens": 7,
                    "cache_creation_input_tokens": 3,
                    "output_tokens": 5,
                },
                "structured_output": payload,
            },
        ]
        (folder / "events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n"
        )
        return {"exit_code": 0}

    state = run_round(root, "example", "r1", 10, execute_fn=transport)
    assert state["status"] == "round_finished"
    assert state["phases"]["worker"]["requested_runtime"]["provider"] == "claude"
    assert state["phases"]["worker"]["session"] != state["phases"]["lead"]["session"]
    worker = state["phases"]["worker"]
    assert (root / "research/example/runs/r1/worker/reply.json").exists()
    assert worker["status"] == "complete" and worker["results"] == "research/example/results.json"
    assert worker["usage"] == {"input_tokens": 20, "cached_input_tokens": 10, "output_tokens": 5}
    assert state["efficiency"]["tokens"]["observed_total_tokens"] == 2 * 25


def test_claude_error_result_stops_without_a_reply_repair(root):
    workflow = json.loads((root / "research/workflow.json").read_text())
    for role in workflow["roles"].values():
        role.update(provider="claude", model="claude-test-model")
    save(root / "research/workflow.json", workflow)
    calls = []

    def transport(command, prompt, folder, _timeout):
        calls.append(folder.name)
        session = command[command.index("--session-id") + 1]
        events = [
            {"type": "system", "subtype": "init", "session_id": session},
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "result": "API Error: Request rejected (429)",
            },
        ]
        (folder / "events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n"
        )
        return {"exit_code": 0}

    with pytest.raises(RuntimeError, match="Claude invocation failed"):
        run_round(root, "example", "r1", 10, execute_fn=transport)
    assert calls == ["worker"]
    state = json.loads((root / "research/example/runs/r1/run.json").read_text())
    assert state["status"] == "interrupted_or_failed"
    assert state["phases"]["worker"]["status"] == "interrupted_or_failed"
    assert not (root / "research/example/runs/r1/worker/reply.json").exists()


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
    assert calls == ["worker"] and result["status"] == "blocked_checkpoint"


@pytest.mark.parametrize("resume", [False, True])
def test_series_follows_received_science_handoff_without_replaying_worker(root, resume):
    calls = []
    next_brief = "research/example/repair.md"
    (root / next_brief).write_text("Review the material scientific revision before repair.")
    blocked = {
        "worker": {
            "status": "blocked",
            "decision": "revise",
            "next_brief": next_brief,
            "next_review": "plan",
        },
        "lead": {
            "decision": "repair",
            "next_brief": next_brief,
            "next_review": "plan",
        },
    }

    def provider(command, prompt, folder, timeout):
        replies = blocked if folder.parent.name == "science-1" else {}
        return fake_agent(calls, replies)(command, prompt, folder, timeout)

    original = root / "research/example/runs/science-1/run.json"
    if resume:
        run_round(root, "example", "science-1", 10, execute_fn=provider)
        save(
            root / "research/example/runs/science-series.json",
            {
                "status": "blocked_checkpoint",
                "active_round": None,
                "rounds": [str(original.relative_to(root))],
                "next_brief": next_brief,
            },
        )
        before = original.read_bytes()
        calls.clear()
    result = run_series(root, "example", "science", 10, resume=resume, execute_fn=provider)
    assert calls == ([] if resume else ["worker", "lead"]) + ["plan_review", "worker", "lead"]
    assert result["status"] == "decision_handoff" and len(result["rounds"]) == 2
    first = json.loads(original.read_text())
    assert first["phases"]["worker"]["status"] == "blocked"
    assert agent_workflow.has_checkpoint(first)
    assert "resolved_by" not in first["phases"]["worker"]
    assert (original.parent / "worker/results.json").is_file()
    if resume:
        assert original.read_bytes() == before
        assert not list(original.parent.glob("worker_resume_*"))


@pytest.mark.parametrize(
    "change",
    [
        "wait",
        "remote_unknown",
        "worker_transport",
        "lead_transport",
        "same_session",
        "stale_dependencies",
        "no_plan_review",
        "ordinary_blocker",
        "unfinished_run",
    ],
)
def test_science_handoff_requires_received_independent_plan_dispatch(root, change):
    next_brief = "research/example/repair.md"
    (root / next_brief).write_text("Review a material scientific revision.")
    state = run_round(
        root,
        "example",
        "science",
        10,
        execute_fn=fake_agent(
            [],
            {
                "worker": {
                    "status": "blocked",
                    "decision": "revise",
                    "next_brief": next_brief,
                    "next_review": "plan",
                },
                "lead": {"decision": "repair", "next_brief": next_brief, "next_review": "plan"},
            },
        ),
    )
    worker, lead = state["phases"]["worker"], state["phases"]["lead"]
    if change == "wait":
        worker["wait_state"] = {"state": "waiting"}
    elif change == "remote_unknown":
        worker["remote_status"] = "unknown"
    elif change == "worker_transport":
        worker["exit_code"] = 1
    elif change == "lead_transport":
        lead["exit_code"] = 1
    elif change == "same_session":
        lead["session"] = worker["session"]
    elif change == "stale_dependencies":
        lead["depends_on"] = []
    elif change == "no_plan_review":
        lead["next_review"] = "reuse"
    elif change == "ordinary_blocker":
        worker["decision"] = "none"
    else:
        state["status"] = "interrupted_or_failed"
    run = root / "research/example/runs/science"
    assert not agent_workflow.received_science_handoff(root, run, state)
    save(run / "run.json", state)
    with pytest.raises(ValueError, match="unfinished job/checkpoint"):
        run_round(root, "example", "new", 10, execute_fn=fake_agent([]))


def test_remote_science_handoff_requires_explicit_bound_terminal_receipt(root):
    next_brief = "research/example/repair.md"
    (root / next_brief).write_text("Review a material scientific revision.")
    state = run_round(
        root,
        "example",
        "remote-science",
        10,
        execute_fn=fake_agent(
            [],
            {
                "worker": {
                    "status": "blocked",
                    "decision": "revise",
                    "next_brief": next_brief,
                    "next_review": "plan",
                },
                "lead": {"decision": "repair", "next_brief": next_brief, "next_review": "plan"},
            },
        ),
    )
    run = root / "research/example/runs/remote-science"
    latest = state["phases"]["worker"]
    old = {**latest, "wait": {"local_only": False}, "wait_state": {"remote_status": "unknown"}}
    latest["resumes_phase"] = "worker"
    checkpoint = str((run / "checkpoint.json").relative_to(root))
    receipt = str((run / "jobs.json").relative_to(root))
    latest["checkpoint"] = checkpoint
    reply = json.loads((run / "worker/reply.json").read_text())
    save(run / "worker/reply.json", {**reply, "checkpoint": checkpoint})
    save(
        root / checkpoint,
        {
            "kind": "research_checkpoint",
            "schema_version": 1,
            "session": latest["session"],
            "inputs": [{"path": receipt}],
            "completed": [],
            "remaining": ["Scientific revision"],
        },
    )
    lead = state["phases"]["lead"]
    lead["depends_on"] = ["worker_resume_1"]
    state["phases"] = {"worker": old, "worker_resume_1": latest, "lead": lead}
    for evidence in [
        {"remote_status": "unknown", "controller_process_state": "exited"},
        {
            "controller_process_state": "exited",
            "explicit_remote_terminal": "App completed",
            "shards": 2,
            "returned_shards": 1,
        },
        {
            "remote_status": "unknown",
            "controller_process_state": "exited",
            "explicit_remote_terminal": "App completed",
            "shards": 2,
            "returned_shards": 2,
        },
    ]:
        save(root / receipt, evidence)
        assert not agent_workflow.received_science_handoff(root, run, state)
    save(
        root / receipt,
        {
            "controller_process_state": "exited",
            "explicit_remote_terminal": "App completed",
            "shards": 2,
            "returned_shards": 2,
        },
    )
    assert agent_workflow.received_science_handoff(root, run, state)
    assert agent_workflow.has_checkpoint(state) and old["wait_state"]["remote_status"] == "unknown"


@pytest.mark.parametrize("role", ["plan_review", "worker", "lead"])
def test_completed_report_does_not_block_series(root, role):
    report = root / "research/example/review.md"
    report.write_text("Accept scope; completed independent review.")
    calls = []
    result = run_series(
        root,
        "example",
        "accepted_review",
        10,
        review_plan=True,
        execute_fn=fake_agent(
            calls,
            {
                role: {"checkpoint": "research/example/review.md"},
            },
        ),
    )
    assert calls == ["plan_review", "worker", "lead"]
    assert result["status"] == "decision_handoff"
    state = json.loads((root / result["rounds"][0]).read_text())
    assert state["phases"][role]["checkpoint"] == "research/example/review.md"
    state["phases"][role]["status"] = "blocked"
    assert agent_workflow.has_checkpoint(state)
    if role == "plan_review":
        state["phases"][role].update(status="complete", decision="revise", checkpoint=None)
        assert agent_workflow.has_checkpoint(state)


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
    for _ in range(250):
        try:
            if process_state(identity(pid)) == "exited":
                break
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("Descendant survived timeout cleanup")


def test_metadata_write_failure_cleans_up_launched_process(tmp_path, monkeypatch):
    processes = []
    start = subprocess.Popen.__init__

    def tracked(self, *args, **kwargs):
        start(self, *args, **kwargs)
        processes.append(self)

    def cannot_write(*_args):
        raise OSError("fixture disk write failure")

    monkeypatch.setattr(subprocess.Popen, "__init__", tracked)
    monkeypatch.setattr(agent_workflow, "write_json", cannot_write)
    with pytest.raises(OSError, match="disk write"):
        execute([sys.executable, "-c", "import time; time.sleep(30)"], "", tmp_path, 5)
    assert len(processes) == 1 and processes[0].poll() is not None


def test_pi_command_matches_the_print_boundary(root):
    schema = agent_workflow.reply_dispatch_schema()
    role = {
        "provider": "pi",
        "model": "command-code-2/deepseek/deepseek-v4.1-flash",
        "effort": "high",
        "prompt": "prompts/worker.md",
    }
    command = agent_workflow.pi_command(root, role, root / "out", schema)
    assert command[:5] == ["env", "-C", str(root), "pi", "-p"]
    assert command[command.index("--mode") + 1] == "json"
    assert command[command.index("--model") + 1] == role["model"]
    assert command[command.index("--thinking") + 1] == "high"
    assert "--no-mcp" in command and "--approve" in command
    appended = command[command.index("--append-system-prompt") + 1]
    assert "final message" in appended and '"required"' in appended
    session = command[command.index("--session-id") + 1]
    assert len(session) == 36
    resumed = agent_workflow.pi_command(root, role, root / "out", schema, session="saved-session")
    assert resumed[resumed.index("--session-id") + 1] == "saved-session"
    assert agent_command(root, role, root / "out", schema)[3] == "pi"


def test_pi_structured_reply_accepts_fenced_json(tmp_path):
    events = [
        {"type": "session", "id": "s1"},
        {"type": "agent_start"},
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": '```json\n{"status": "blocked"}\n```'}],
            },
        },
        {"type": "agent_end"},
    ]
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    assert agent_workflow.pi_structured_reply(tmp_path) == {"status": "blocked"}


def test_pi_round_reads_structured_reply_and_normalizes_usage(root):
    workflow = json.loads((root / "research/workflow.json").read_text())
    for role in workflow["roles"].values():
        role.update(
            provider="pi",
            model="command-code-2/deepseek/deepseek-v4.1-flash",
        )
    save(root / "research/workflow.json", workflow)
    reply = {
        "status": "complete",
        "summary": "Synthetic pi transport; no model or research execution",
        "decision": "continue",
        "results": "research/example/results.json",
        "next_brief": None,
        "checkpoint": None,
    }

    def transport(command, prompt, folder, _timeout):
        assert any(Path(part).name in ("run_capped.sh", "run_capped.py") for part in command[:2])
        assert "pi" in command and "--mode" in command
        phase = folder.name
        session = command[command.index("--session-id") + 1]
        payload = dict(reply, decision="park", results=None) if phase == "lead" else reply
        events = [
            {"type": "session", "id": session},
            {"type": "agent_start"},
            {"type": "message_start", "message": {"role": "assistant"}},
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": json.dumps(payload)}],
                    "usage": {
                        "input": 10,
                        "output": 5,
                        "cacheRead": 7,
                        "cacheWrite": 3,
                        "reasoning": 4,
                    },
                },
            },
            {"type": "agent_end"},
        ]
        (folder / "events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n"
        )
        return {"exit_code": 0}

    state = run_round(root, "example", "r1", 10, execute_fn=transport)
    assert state["status"] == "round_finished"
    assert state["phases"]["worker"]["requested_runtime"]["provider"] == "pi"
    assert state["phases"]["worker"]["session"] != state["phases"]["lead"]["session"]
    worker = state["phases"]["worker"]
    assert (root / "research/example/runs/r1/worker/reply.json").exists()
    assert worker["status"] == "complete" and worker["results"] == "research/example/results.json"
    assert worker["usage"] == {"input_tokens": 20, "cached_input_tokens": 10, "output_tokens": 5}
    assert state["efficiency"]["tokens"]["observed_total_tokens"] == 2 * 25


def test_pi_error_event_stops_without_a_reply_repair(root):
    workflow = json.loads((root / "research/workflow.json").read_text())
    for role in workflow["roles"].values():
        role.update(
            provider="pi",
            model="command-code-2/deepseek/deepseek-v4.1-flash",
        )
    save(root / "research/workflow.json", workflow)
    calls = []

    def transport(command, prompt, folder, _timeout):
        calls.append(folder.name)
        session = command[command.index("--session-id") + 1]
        events = [
            {"type": "session", "id": session},
            {"type": "agent_start"},
            {"type": "error", "error": "429 weekly quota exhausted"},
        ]
        (folder / "events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in events) + "\n"
        )
        return {"exit_code": 0}

    with pytest.raises(RuntimeError, match="pi invocation failed"):
        run_round(root, "example", "r1", 10, execute_fn=transport)
    assert calls == ["worker"]
    state = json.loads((root / "research/example/runs/r1/run.json").read_text())
    assert state["status"] == "interrupted_or_failed"


def closed_round(root, run_id="series-1"):
    run = root / "research/example/runs" / run_id
    save(
        run / "run.json",
        {
            "direction": "example",
            "run_id": run_id,
            "status": "closed_after_recovery",
            "recovery": {
                "at_utc": "2026-11-17T01:22:54+00:00",
                "reason": "Received saved evidence; this arm is parked, not a completed account.",
            },
            "phases": {"worker": {"status": "interrupted_or_failed", "exit_code": 143}},
        },
    )
    (run / "brief.md").write_text("Original closed question; do not replay.", encoding="utf-8")
    return run


def failed_series(root, run):
    path = root / "research/example/runs/series-series.json"
    relative = (run / "run.json").relative_to(root).as_posix()
    save(
        path,
        {
            "status": "interrupted_or_failed",
            "rounds": [relative],
            "active_round": relative,
            "pending_dispatch": {"run": relative, "brief_text": "Original failed dispatch"},
            "next_brief": "research/example/brief.md",
            "error": "Original worker exit143",
        },
    )
    return path


def test_closed_round_cannot_resume_or_change_its_evidence(root, monkeypatch):
    run = closed_round(root)
    before = (run / "run.json").read_bytes()
    monkeypatch.setattr(
        agent_workflow, "reconcile_event_attempts", lambda *_: pytest.fail("No event reception")
    )
    monkeypatch.setattr(
        agent_workflow, "require_local_stopped", lambda *_: pytest.fail("No PID upgrade")
    )
    calls = []
    with pytest.raises(ValueError, match="closed_after_recovery"):
        run_round(root, "example", run.name, 10, resume=True, execute_fn=fake_agent(calls))
    assert calls == []
    assert (run / "run.json").read_bytes() == before
    assert list(run.glob("before-resume-*.json")) == []
    assert not (run / "reply.schema.json").exists()


@pytest.mark.parametrize("status", ["interrupted_or_failed", "running"])
def test_closed_round_stops_series_and_retains_original_failed_dispatch(root, monkeypatch, status):
    run = closed_round(root)
    record = failed_series(root, run)
    series = json.loads(record.read_text())
    save(record, {**series, "status": status})
    before_run, before_series = (run / "run.json").read_bytes(), record.read_bytes()
    monkeypatch.setattr(agent_workflow, "run_round", lambda *_a, **_kw: pytest.fail("No replay"))
    monkeypatch.setattr(
        agent_workflow, "require_local_stopped", lambda *_: pytest.fail("No PID upgrade")
    )
    result = run_series(root, "example", "series", 10, resume=True)
    assert result["status"] == "closed_after_recovery"
    assert result["active_round"] is None and result["next_brief"] is None
    assert "pending_dispatch" not in result and "error" not in result
    [archive] = record.parent.glob("series-series-resume-*.json")
    assert json.loads(archive.read_text()) == json.loads(before_series)
    assert (run / "run.json").read_bytes() == before_run
    assert json.loads(record.read_text()) == result
    assert not (root / "board.md").exists()


def test_nonclosed_interruption_refuses_resume_while_its_process_runs(root, monkeypatch):
    run = closed_round(root)
    state = json.loads((run / "run.json").read_text())
    state["status"] = "interrupted_or_failed"
    save(run / "run.json", state)
    save(run / "worker/process.json", {"pid": 12345})
    record = failed_series(root, run)
    before = record.read_bytes()
    monkeypatch.setattr(agent_workflow, "process_state", lambda _: "running")
    monkeypatch.setattr(agent_workflow, "run_round", lambda *_a, **_kw: pytest.fail("No dispatch"))
    with pytest.raises(ValueError, match="still running"):
        run_series(root, "example", "series", 10, resume=True)
    assert record.read_bytes() == before
    assert list(record.parent.glob("series-series-resume-*.json")) == []
