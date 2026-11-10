from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

import pytest
from test_agent_workflow import fake_agent, save
from test_agent_workflow import root as workflow_root

from open_composer.research import agent_workflow as workflow
from open_composer.research.event_wait import WaitSpec, bind_wait, checkpoint_status, wait_event
from open_composer.research.process_identity import identity, process_state


@pytest.fixture
def root(tmp_path):
    return workflow_root.__wrapped__(tmp_path)


def event_agent(root, calls, *, marker=True, repeat=False, crash=False):
    normal = fake_agent(calls)

    def run(command, prompt, folder, timeout):
        transport = normal(command, prompt, folder, timeout)
        if folder.name == "worker" or (repeat and folder.name.startswith("worker_resume")):
            checkpoint = folder.parent / "checkpoint.json"
            save(
                checkpoint,
                {
                    "kind": "research_checkpoint",
                    "schema_version": 1,
                    "session": "fixture-worker",
                    "inputs": [],
                    "completed": ["fixture"],
                    "remaining": ["receive marker"],
                    "native_resumable": False,
                },
            )
            spec = WaitSpec(
                session="fixture-worker",
                completion_marker=str((folder.parent / "done.json").relative_to(root)),
                failure_marker=str((folder.parent / "failed.json").relative_to(root)),
            )
            reply = json.loads((folder / "reply.json").read_text())
            reply.update(
                status="blocked",
                decision="none",
                results=None,
                checkpoint=str(checkpoint.relative_to(root)),
                wait=spec.model_dump(),
            )
            save(folder / "reply.json", reply)
            if marker:
                (folder.parent / "done.json").write_text("{}")
        elif folder.name.startswith("worker_resume") and crash:
            raise RuntimeError("fixture crash after dispatch; no receipt")
        return transport

    return run


def test_real_process_wait_resumes_original_session_once_and_zero_calls_while_waiting(root):
    calls, waiting_calls, jobs = [], [], []
    provider = event_agent(root, calls, marker=False)

    def controlled(command, prompt, folder, timeout):
        result = provider(command, prompt, folder, timeout)
        if folder.name == "worker":
            marker = folder.parent / "done.json"
            jobs.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        "import time;from pathlib import Path;time.sleep(.35);"
                        f'Path({str(marker)!r}).write_text("{{}}")',
                    ]
                )
            )
            timer = threading.Timer(0.15, lambda: waiting_calls.append(len(calls)))
            timer.start()
        return result

    state = workflow.run_round(root, "example", "events", 5, execute_fn=controlled)
    for job in jobs:
        job.wait(timeout=3)
    assert calls == ["worker", "worker_resume_1", "lead"]
    assert waiting_calls == [1]  # no provider dispatch during scripted wait
    assert state["status"] == "round_finished"
    assert state["phases"]["worker_resume_1"]["session"] == "fixture-worker"
    assert state["phases"]["worker"]["wait_state"]["state"] == "received"
    assert state["phases"]["worker_resume_1"]["event_attempt"]["state"] == "received"
    assert state["phases"]["worker"]["resolved_by"] == "worker_resume_1"
    assert not workflow.has_checkpoint(state)
    workflow.run_round(root, "example", "events", 5, execute_fn=controlled, resume=True)
    assert calls == ["worker", "worker_resume_1", "lead"]


def test_timeout_duplicate_and_failure_events_do_not_dispatch_lead(root):
    calls = []
    state = workflow.run_round(
        root, "example", "timeout", 0.12, execute_fn=event_agent(root, calls, marker=False)
    )
    assert calls == ["worker"] and state["status"] == "worker_checkpoint"
    assert state["phases"]["worker"]["wait_state"]["state"] == "timeout"
    run = root / "research/example/runs/timeout"
    (run / "failed.json").write_text("{}")
    state = workflow.run_round(
        root, "example", "timeout", 1, resume=True, execute_fn=event_agent(root, calls)
    )
    assert calls == ["worker"] and state["phases"]["worker"]["wait_state"]["state"] == "failed"


def test_same_event_cannot_launch_second_resume(root):
    calls = []
    state = workflow.run_round(
        root, "example", "repeat", 2, execute_fn=event_agent(root, calls, repeat=True)
    )
    assert calls == ["worker", "worker_resume_1"]
    assert state["phases"]["worker_resume_1"]["wait_state"]["state"] == "duplicate_event"
    workflow.run_round(
        root, "example", "repeat", 2, resume=True, execute_fn=event_agent(root, calls, repeat=True)
    )
    assert calls == ["worker", "worker_resume_1"]


def test_dispatch_crash_without_receipt_never_redispatches(root):
    calls = []
    with pytest.raises(RuntimeError, match="fixture crash"):
        workflow.run_round(
            root, "example", "crash", 2, execute_fn=event_agent(root, calls, crash=True)
        )
    with pytest.raises(ValueError, match="Uncertain event dispatch"):
        workflow.run_round(
            root, "example", "crash", 2, resume=True, execute_fn=event_agent(root, calls)
        )
    assert calls == ["worker", "worker_resume_1"]


def test_receipt_on_disk_recovered_without_duplicate_worker(root, monkeypatch):
    calls = []
    write = workflow.write_json
    fail = [True]

    def broken(path, value):
        phase = value.get("phases", {}).get("worker_resume_1", {})
        if path.name == "run.json" and phase.get("exit_code") == 0 and fail[0]:
            fail[0] = False
            raise OSError("fixture driver crash after transport receipt")
        write(path, value)

    monkeypatch.setattr(workflow, "write_json", broken)
    with pytest.raises(OSError, match="driver crash"):
        workflow.run_round(root, "example", "receipt", 3, execute_fn=event_agent(root, calls))
    state = workflow.run_round(
        root, "example", "receipt", 3, resume=True, execute_fn=event_agent(root, calls)
    )
    assert calls == ["worker", "worker_resume_1", "lead"]
    assert state["status"] == "round_finished"


def test_observed_event_crash_before_dispatch_and_direction_lock(root, monkeypatch):
    calls = []
    write = workflow.write_json
    fail = [True]

    def broken(path, value):
        record = value.get("phases", {}).get("worker", {}).get("wait_state", {})
        write(path, value)
        if record.get("state") == "observed" and fail[0]:
            fail[0] = False
            raise OSError("fixture observed before dispatch")

    monkeypatch.setattr(workflow, "write_json", broken)
    with pytest.raises(OSError, match="observed before dispatch"):
        workflow.run_round(root, "example", "observed", 3, execute_fn=event_agent(root, calls))
    assert calls == ["worker"]
    with workflow.direction_lock(root / "research/example/.round.lock"):
        with pytest.raises(ValueError, match="already has"):
            workflow.run_round(
                root, "example", "observed", 3, resume=True, execute_fn=event_agent(root, calls)
            )
    state = workflow.run_round(
        root, "example", "observed", 3, resume=True, execute_fn=event_agent(root, calls)
    )
    assert calls == ["worker", "worker_resume_1", "lead"]
    assert state["status"] == "round_finished"


def test_pid_reuse_boot_group_and_legacy_are_not_launch_identity():
    saved = identity(os.getpid())
    assert process_state(saved) == "running"
    assert process_state({"pid": os.getpid(), "started": "now"}) == "legacy_unknown"
    for key in ("start_ticks", "pgid", "boot_id"):
        changed = {**saved, key: "different" if key == "boot_id" else saved[key] + 1}
        assert process_state(changed) == "identity_mismatch"
    assert process_state({**saved, "pid": 999999999, "boot_id": "old-boot"}) == "identity_mismatch"
    assert process_state({**saved, "pid": -1}) == "unknown"


def test_binding_cancel_pause_remote_launcher_exit_and_checkpoint(root):
    run = root / "research/example/runs/wait"
    run.mkdir(parents=True)
    process = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(.15)"])
    saved = identity(process.pid)
    save(run / "process.json", saved)
    process.wait(timeout=3)
    spec = WaitSpec(
        session="session",
        completion_marker=str((run / "remote.done").relative_to(root)),
        process=str((run / "process.json").relative_to(root)),
        cancel_marker=str((run / "cancel").relative_to(root)),
    )
    record = bind_wait(root, run, spec, "session")
    result = wait_event(root, run, record, time.monotonic() + 0.05, workflow.require_research)
    assert result["state"] == "timeout"  # local launcher exit is not remote completion
    (run / "cancel").write_text("cancel")
    assert (
        wait_event(root, run, record, time.monotonic() + 1, workflow.require_research)["state"]
        == "cancelled"
    )
    save(root / "control.json", {"draft": False, "research": False})
    assert (
        wait_event(root, run, record, time.monotonic() + 1, workflow.require_research)["state"]
        == "paused"
    )
    with pytest.raises(ValueError, match="original worker session"):
        bind_wait(root, run, spec, "wrong")
    with pytest.raises(ValueError):
        bind_wait(root, run, WaitSpec(session="s", completion_marker="../secret"), "s")
    assert checkpoint_status(root, run, None, "s")["state"] == "absent"
    cp = run / "checkpoint.json"
    save(cp, {"completed": ["ordinary progress"]})
    assert checkpoint_status(root, run, str(cp.relative_to(root)), "s")["native_resumable"] is False
    save(
        cp,
        {
            "kind": "research_checkpoint",
            "schema_version": 1,
            "session": "s",
            "native_resumable": True,
            "engine_snapshot": str((run / "missing").relative_to(root)),
            "inputs": [{"path": "research/example/raw.json", "type": "file"}],
            "completed": [],
            "remaining": ["restore snapshot"],
        },
    )
    assert (
        checkpoint_status(root, run, str(cp.relative_to(root)), "s")["state"]
        == "dependency_unavailable"
    )
    assert (
        checkpoint_status(root, run, str(cp.relative_to(root)), "wrong")["state"]
        == "binding_mismatch"
    )


def test_live_dispatched_attempt_is_waited_and_received_without_resending(root):
    calls, jobs = [], []
    provider = event_agent(root, calls)

    def orphaned(command, prompt, folder, timeout):
        result = provider(command, prompt, folder, timeout)
        if folder.name == "worker_resume_1":
            receipt = folder / "transport.json"
            code = (
                "import time;from pathlib import Path;time.sleep(.25);"
                f"Path({str(receipt)!r}).write_text({json.dumps(result)!r})"
            )
            process = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
            jobs.append(process)
            save(folder / "process.json", identity(process.pid))
            raise RuntimeError("fixture driver disappeared while transport lives")
        return result

    with pytest.raises(RuntimeError, match="transport lives"):
        workflow.run_round(root, "example", "live", 3, execute_fn=orphaned)
    assert calls == ["worker", "worker_resume_1"]
    state = workflow.run_round(
        root, "example", "live", 3, resume=True, execute_fn=event_agent(root, calls)
    )
    for process in jobs:
        process.wait(timeout=2)
    assert calls == ["worker", "worker_resume_1", "lead"]
    assert state["status"] == "round_finished"


def test_owner_pause_while_driver_waits_keeps_checkpoint_and_calls_no_lead(root):
    calls = []
    provider = event_agent(root, calls, marker=False)

    def pause(command, prompt, folder, timeout):
        result = provider(command, prompt, folder, timeout)
        if folder.name == "worker":
            threading.Timer(
                0.1, lambda: save(root / "control.json", {"draft": False, "research": False})
            ).start()
        return result

    state = workflow.run_round(root, "example", "pause", 2, execute_fn=pause)
    assert calls == ["worker"]
    assert state["phases"]["worker"]["wait_state"]["state"] == "paused"
    assert workflow.has_checkpoint(state)


def test_known_failed_event_transport_is_diagnosed_and_not_received(root):
    calls = []
    provider = event_agent(root, calls)

    def failed(command, prompt, folder, timeout):
        result = provider(command, prompt, folder, timeout)
        if folder.name == "worker_resume_1":
            result["exit_code"] = 7
        return result

    with pytest.raises(RuntimeError, match="exited 7"):
        workflow.run_round(root, "example", "failedtransport", 3, execute_fn=failed)
    state = json.loads((root / "research/example/runs/failedtransport/run.json").read_text())
    assert calls == ["worker", "worker_resume_1"]
    assert state["phases"]["worker"]["wait_state"]["state"] == "failed"
    assert state["phases"]["worker_resume_1"]["event_attempt"]["state"] == "failed"
    assert workflow.has_checkpoint(state)


def test_invalid_event_reply_uses_existing_reply_only_repair_and_stays_recoverable(root):
    calls = []
    provider = event_agent(root, calls)

    def malformed(command, prompt, folder, timeout):
        result = provider(command, prompt, folder, timeout)
        if folder.name == "worker_resume_1":
            reply = json.loads((folder / "reply.json").read_text())
            reply["checkpoint"] = "research/example/does-not-exist.json"
            save(folder / "reply.json", reply)
        if folder.name == "worker_resume_2":
            assert "Correct Reply only" in prompt
        return result

    state = workflow.run_round(root, "example", "invalidreply", 3, execute_fn=malformed)
    assert calls == ["worker", "worker_resume_1", "worker_resume_2", "lead"]
    assert state["phases"]["worker_resume_1"]["event_attempt"]["state"] == "invalid_reply"
    workflow.run_round(root, "example", "invalidreply", 3, resume=True, execute_fn=malformed)
    assert calls == ["worker", "worker_resume_1", "worker_resume_2", "lead"]


def test_exited_fork_leader_with_live_group_never_allows_wait_or_second_worker(root):
    # A separate supervisor adopts/reaps the orphan, keeping pytest and existing
    # jobs untouched. The controlled child is killed by its captured identity.
    code = r"""
import ctypes,json,os,signal,subprocess,sys,time
from pathlib import Path
from open_composer.research import agent_workflow as workflow
from open_composer.research.event_wait import WaitSpec,bind_wait,wait_event
from open_composer.research.process_identity import (
 identity,process_state,signal_members,signal_group)
root=Path(sys.argv[1]);run=root/'research/example/runs/fork';run.mkdir(parents=True)
assert ctypes.CDLL(None).prctl(36,1,0,0,0)==0
childfile=run/'child.pid'
parent_code=('import os,time;from pathlib import Path;pid=os.fork();'
 +f'Path({str(childfile)!r}).write_text(str(os.getpid())) if pid==0 else None;'
 +'time.sleep(30 if pid==0 else .4)')
parent=subprocess.Popen([sys.executable,'-c',parent_code],start_new_session=True)
child=None;child_launch=None
try:
 launch=identity(parent.pid);(run/'worker').mkdir()
 process=run/'worker/process.json';process.write_text(json.dumps(launch))
 spec=WaitSpec(session='fixture-worker',process=str(process.relative_to(root)),local_only=True)
 record=bind_wait(root,run,spec,'fixture-worker')
 limit=time.monotonic()+2
 while time.monotonic()<limit:
  if childfile.exists() and childfile.read_text().strip():
   child=int(childfile.read_text());break
  time.sleep(.01)
 assert child is not None
 child_launch=identity(child)
 parent.wait(timeout=2)
 assert process_state(child_launch)=='running'
 assert process_state(launch)=='unknown'
 assert not signal_group(launch,signal.SIGTERM)
 observed=wait_event(root,run,record,time.monotonic()+.1,workflow.require_research)
 assert observed['state']=='unknown'
 state={'direction':'example','run_id':'fork','status':'interrupted_or_failed',
        'review_plan':False,'review_result':False,'phases':{'worker':{'status':'starting','session':'fixture-worker'}}}
 (run/'brief.md').write_text('Controlled orphan group fixture')
 (run/'run.json').write_text(json.dumps(state))
 calls=[]
 try:
  workflow.run_round(root,'example','fork',1,resume=True,execute_fn=lambda *a:calls.append(a))
  raise AssertionError('live group incorrectly permitted recovery')
 except ValueError as error:
  assert 'reconciliation' in str(error)
 assert not calls
 state['phases']['worker']['event_attempt']={'state':'dispatching'}
 try:
  workflow.reconcile_event_attempts(root,run,state,time.monotonic()+.1)
  raise AssertionError('live group incorrectly received as exited')
 except ValueError as error:
  assert 'reconciliation' in str(error)
 print(json.dumps({'leader_state':'unknown','child_state':'running','new_worker_calls':len(calls),'local_only_wait':'unknown'}))
finally:
 if child_launch is not None:
  signal_members([child_launch],signal.SIGKILL)
 if child is not None:
  os.waitpid(child,0)
 if parent.poll() is None:
  parent.kill()
 parent.wait(timeout=2)
assert process_state(launch)=='exited'
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    observed = json.loads(result.stdout)
    assert observed["new_worker_calls"] == 0
    assert observed["leader_state"] == observed["local_only_wait"] == "unknown"
