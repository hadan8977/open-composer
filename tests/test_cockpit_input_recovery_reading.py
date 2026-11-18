"""A successful separate recovery must replace stale display, not old evidence."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from open_composer.cockpit.data.paper_trials import _session_inputs

NOW = datetime(2026, 10, 27, 4, tzinfo=UTC)


def put(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture
def recovery(tmp_path):
    folder = tmp_path / "reports/paper/diagnostics/dated-target-refresh/2026-10-27"
    record = folder.with_name(folder.name + "-runtime-recovery-01")
    original = put(
        folder / "refresh-exit.json",
        dict(
            exit_code=1,
            at="2026-10-27T00:20:49Z",
            stages=[
                dict(phase="source", exit_code=0),
                dict(phase="prepare", exit_code=0),
                dict(phase="inference", exit_code=127),
            ],
        ),
    )
    target = dict(
        policy="BASE",
        reference_day="2026-10-26",
        application_day="2026-10-27",
        as_of="2026-10-26T20:00:00Z",
        valid_until="2026-10-27T19:30:00Z",
    )
    installed = tmp_path / "reports/research/program/paper-launch-20min-20261021/targets/BASE.json"
    decision = put(installed, target)
    staged = put(folder / "targets/BASE.json", target)
    produced = put(
        folder / "target-production-result.json",
        dict(
            application_day="2026-10-27",
            reference_day="2026-10-26",
            at_utc="2026-10-27T03:08:00Z",
            targets={"BASE": staged},
            blocked_policies={},
        ),
    )
    put(folder / "publication.json", dict(at="2026-10-27T03:09:00Z", targets={"BASE": decision}))
    manifest = put(
        tmp_path
        / "reports/paper/diagnostics/inference-runtime-repair-20261027/recovery-inputs.json",
        dict(
            prepared_root=str(folder),
            purpose="same_day_exec127_saved_stage_recovery_v1",
            historical_failure_prefix_immutable=True,
            immutable_inputs=[original],
        ),
    )
    worker = (
        tmp_path / "reports/research/program/paper-launch-20min-20261021/recover_dated_refresh.py"
    )
    worker.parent.mkdir(parents=True, exist_ok=True)
    worker.write_text("raise RuntimeError('a read-only dashboard must never execute this worker')")
    worker_binding = dict(
        path=str(worker),
        bytes=worker.stat().st_size,
        sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),
    )
    put(
        folder / "runtime-recovery-claim.json",
        dict(
            record=str(record), manifest=manifest, worker=worker_binding, at="2026-10-27T03:00:00Z"
        ),
    )
    put(
        record / "recovery-exit.json",
        dict(
            exit_code=0,
            targets_published=True,
            status="current_input_recovery_published",
            at="2026-10-27T03:10:00Z",
            stages=[dict(phase="inference", exit_code=0), dict(phase="postprocess", exit_code=0)],
            target_result=produced,
            published={"BASE": decision},
        ),
    )
    return tmp_path, folder, record, {"decision": decision}, original


def test_bound_recovery_updates_display_and_preserves_original_failed_attempt(recovery):
    root, folder, _, sources, original = recovery
    result = _session_inputs(root, "BASE", sources, NOW)
    assert result["next_input_status"] == "publication_recorded_not_operating_acceptance"
    assert result["input_attempt_status"] == "original_failed_then_recovery_published"
    assert result["instruction_status"] == "within_time_bounds"
    assert (
        hashlib.sha256((folder / "refresh-exit.json").read_bytes()).hexdigest()
        == original["sha256"]
    )


@pytest.mark.parametrize(
    "flaw",
    ["failed", "publication_hash", "unconfined_record", "future_terminal", "wrong_prepared_day"],
)
def test_invalid_recovery_cannot_manufacture_current_publication(recovery, flaw):
    root, folder, record, sources, _ = recovery
    if flaw in {"failed", "future_terminal"}:
        path = record / "recovery-exit.json"
        data = json.loads(path.read_text())
        data["exit_code" if flaw == "failed" else "at"] = (
            1 if flaw == "failed" else "2026-10-28T03:10:00Z"
        )
    elif flaw == "publication_hash":
        path = folder / "publication.json"
        data = json.loads(path.read_text())
        data["targets"]["BASE"]["sha256"] = "0" * 64
    elif flaw == "unconfined_record":
        path = folder / "runtime-recovery-claim.json"
        data = json.loads(path.read_text())
        data["record"] = str(root / "outside")
    else:
        path = Path(
            json.loads((folder / "runtime-recovery-claim.json").read_text())["manifest"]["path"]
        )
        data = json.loads(path.read_text())
        data["prepared_root"] = str(folder.with_name("2026-10-28"))
    path.write_text(json.dumps(data))
    result = _session_inputs(root, "BASE", sources, NOW)
    assert result["next_input_status"] == "recovery_record_unavailable_or_invalid"
    assert result["input_attempt_status"] == "original_producer_failed"


@pytest.mark.parametrize("flaw", ["wrong_reference", "expired_target"])
def test_hash_consistent_but_wrong_market_clock_is_not_current_recovery(recovery, flaw):
    root, folder, record, sources, _ = recovery
    installed = Path(sources["decision"]["path"])
    target = json.loads(installed.read_text())
    if flaw == "wrong_reference":
        target["reference_day"] = "2026-10-23"
    else:
        target["valid_until"] = "2026-10-27T03:30:00Z"
    decision = put(installed, target)
    staged = put(folder / "targets/BASE.json", target)
    produced = json.loads((folder / "target-production-result.json").read_text())
    produced["reference_day"] = target["reference_day"]
    produced["targets"]["BASE"] = staged
    produced_binding = put(folder / "target-production-result.json", produced)
    publication = json.loads((folder / "publication.json").read_text())
    publication["targets"]["BASE"] = decision
    put(folder / "publication.json", publication)
    terminal = json.loads((record / "recovery-exit.json").read_text())
    terminal["target_result"] = produced_binding
    terminal["published"]["BASE"] = decision
    put(record / "recovery-exit.json", terminal)
    result = _session_inputs(root, "BASE", {"decision": decision}, NOW)
    assert result["next_input_status"] == "recovery_record_unavailable_or_invalid"
