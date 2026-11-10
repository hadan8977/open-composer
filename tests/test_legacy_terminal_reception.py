from __future__ import annotations

import hashlib
import json
import signal

import pytest

from open_composer.research import agent_workflow as workflow
from open_composer.research import process_identity as processes


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    run = tmp_path / "run"
    folder = run / "worker"
    folder.mkdir(parents=True)
    record = folder / "process.json"
    record.write_bytes(b'{ "pid": 43210, "started": "original wall clock" }\n')
    original = record.read_bytes()
    proc = tmp_path / "proc"
    boot = proc / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("current-boot\n")
    summary = "Stopped fixture.scope; original launcher used start_new_session=True."
    evidence = folder / "scope-stop.log"
    evidence.write_text(summary + "\n")
    sidecar = folder / "legacy-terminal-reception.json"
    receipt = {
        "schema_version": 1,
        "kind": "legacy_terminal_reception",
        "process_sha256": hashlib.sha256(original).hexdigest(),
        "received_boot_id": "current-boot",
        "pid": 43210,
        "pgid": 43210,
        "pgid_basis": "launcher_start_new_session",
        "stopped_scope": "fixture.scope",
        "evidence_path": evidence.name,
        "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "evidence_summary": summary,
    }
    state = {"phases": {"worker": {"status": "interrupted_or_failed", "exit_code": -15}}}
    monkeypatch.setattr(
        workflow, "legacy_terminal_received",
        lambda path: processes.legacy_terminal_received(path, proc=proc),
    )
    return run, record, original, proc, evidence, sidecar, receipt, state


@pytest.mark.parametrize("invalid", ["absent", "record_hash", "boot", "evidence", "summary"])
def test_missing_or_bad_legacy_reception_stays_blocked(legacy, invalid):
    run, record, original, _, _, sidecar, receipt, state = legacy
    if invalid == "record_hash":
        receipt["process_sha256"] = "0" * 64
    elif invalid == "boot":
        receipt["received_boot_id"] = "another-boot"
    elif invalid == "evidence":
        receipt["evidence_sha256"] = "0" * 64
    elif invalid == "summary":
        receipt["evidence_summary"] = "Unrelated fixture.scope terminal claim"
    if invalid != "absent":
        sidecar.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="identity needs reconciliation"):
        workflow.require_local_stopped(run, state)
    assert record.read_bytes() == original


def test_dead_reception_keeps_original_record_and_legacy_signals_refused(legacy, monkeypatch):
    run, record, original, _, _, sidecar, receipt, state = legacy
    sidecar.write_text(json.dumps(receipt))
    workflow.require_local_stopped(run, state)
    assert record.read_bytes() == original
    saved = json.loads(original)
    assert processes.process_state(saved) == "legacy_unknown"

    def forbidden_signal(*_args):
        pytest.fail("Legacy reception must not make an old PID a signal identity")

    monkeypatch.setattr(processes.os, "killpg", forbidden_signal)
    monkeypatch.setattr(processes.os, "kill", forbidden_signal)
    assert processes.signal_group(saved, signal.SIGTERM) is False
    processes.signal_members([saved], signal.SIGTERM)


@pytest.mark.parametrize("presence", ["leader", "remaining_group"])
def test_live_pid_or_remaining_group_still_blocks_legacy_reception(legacy, presence):
    run, record, original, proc, _, sidecar, receipt, state = legacy
    sidecar.write_text(json.dumps(receipt))
    member = proc / ("43210" if presence == "leader" else "43211")
    member.mkdir()
    (member / "stat").write_text(f"{member.name} (survivor) S 1 43210 0\n")
    with pytest.raises(ValueError, match="identity needs reconciliation"):
        workflow.require_local_stopped(run, state)
    assert record.read_bytes() == original


@pytest.mark.parametrize("other", ["blocked_phase", "modern_unknown", "modern_mismatch"])
def test_reception_does_not_widen_other_phase_or_identity_cases(legacy, other):
    run, record, original, _, _, sidecar, receipt, state = legacy
    if other == "blocked_phase":
        state["phases"]["worker"]["status"] = "blocked"
    else:
        saved = json.loads(original)
        saved.update(boot_id="another-boot", start_ticks=1, pgid=43210)
        if other == "modern_unknown":
            saved["start_ticks"] = -1
        record.write_text(json.dumps(saved))
        receipt["process_sha256"] = hashlib.sha256(record.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="identity needs reconciliation"):
        workflow.require_local_stopped(run, state)
