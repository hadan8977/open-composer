"""Finite invented clock/control cases; no authenticated rehearsal or latency claim."""

import ast
import hashlib
import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from open_composer.intraday_runner import source_runtime_entry as entry

WAVE = datetime(2026, 11, 3, 14, 35, tzinfo=UTC)


def binding(path):
    data = path.read_bytes()
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a, **k):
        raise AssertionError("no source/account/network authorized in fixture")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def artifact(path, value):
    path.write_text(json.dumps(value))
    return binding(path)


@pytest.fixture
def package(tmp_path, monkeypatch):
    output = tmp_path / "one-output"
    codes = [binding(p) for p in sorted(Path(entry.__file__).parent.glob("source_*.py"))]
    authority = artifact(tmp_path / "authority.json", dict(only="invented"))
    native = dict(
        accepted=True,
        scope="dia_base_complete_entry_v1",
        allowed_phases=["sell"],
        authority=authority,
        code_bindings=codes,
        output=str(output),
        invocation_id="one-prepared-fixture",
        prepare_not_before=(WAVE - timedelta(seconds=2)).isoformat(),
    )
    job = dict(
        active=True,
        phase="sell",
        not_before=WAVE.isoformat(),
        expires_at=(WAVE + timedelta(seconds=5)).isoformat(),
        quote_cutoff=WAVE.isoformat(),
        prepare_not_before=native["prepare_not_before"],
        native_acceptance=artifact(tmp_path / "native.json", native),
        authority=authority,
        code_bindings=codes,
        output=str(output),
        invocation_id=native["invocation_id"],
        disk_admission=artifact(
            tmp_path / "disk.json",
            dict(accepted=True, invocation_id=native["invocation_id"], required_free_bytes=1),
        ),
        timeout_seconds=10,
    )
    b = artifact(tmp_path / "job.json", job)
    artifact(output.with_suffix(".launch-consumed.json"), dict(job=b))
    monkeypatch.setattr(entry, "kernel_evidence", lambda: {"synthetic": True})
    return tmp_path, output, job, native, b


class Clock:
    def __init__(self, at):
        self.at, self.mono = at, 100.0

    def utc(self):
        return self.at

    def monotonic(self):
        return self.mono

    def sleep(self, seconds):
        assert 0 < seconds <= 0.05
        self.at += timedelta(seconds=seconds)
        self.mono += max(seconds, 0.000001)


def test_preparation_then_immediate_live_gate_no_reusable_snapshot(package, monkeypatch):
    root, output, job, native, b = package
    clock = Clock(WAVE - timedelta(seconds=1))
    imports = []
    monkeypatch.setattr(
        entry.importlib, "import_module", lambda name: imports.append((name, clock.utc()))
    )
    with pytest.raises(ValueError, match="inactive"):
        entry.entry_gate(root, b, clock.utc(), requested_output=output)
    entry.prepare_entry(
        root, b, output, clock=clock.utc, monotonic=clock.monotonic, sleep=clock.sleep
    )
    assert [x[0] for x in imports] == list(entry.PREPARATION_MODULES)
    assert all(t < WAVE for _, t in imports)
    assert clock.utc() == WAVE
    assert not output.exists()  # no financial runtime, account client or source output
    prepared = json.loads(output.with_suffix(".preparation.json").read_text())
    assert prepared["imports_wait_completed_at"] == WAVE.isoformat()
    assert prepared["reusable_financial_snapshot"] is False
    assert prepared["source_account_order_calls"] == 0
    assert entry.entry_gate(root, b, clock.utc(), requested_output=output)[0] == job
    with pytest.raises(ValueError, match="inactive"):
        entry.entry_gate(root, b, WAVE + timedelta(seconds=5), requested_output=output)


@pytest.mark.parametrize("mutation", ["authority", "job", "native", "disk"])
def test_changed_binding_during_preparation_refuses_at_live_gate(package, monkeypatch, mutation):
    root, output, job, native, b = package
    clock = Clock(WAVE - timedelta(seconds=0.1))
    monkeypatch.setattr(entry.importlib, "import_module", lambda name: None)
    changed = False

    def sleep(seconds):
        nonlocal changed
        clock.sleep(seconds)
        if not changed:
            (root / (mutation + ".json")).write_text('{"drift":true}')
            changed = True

    entry.prepare_entry(root, b, output, clock=clock.utc, monotonic=clock.monotonic, sleep=sleep)
    with pytest.raises(ValueError, match="hash"):
        entry.entry_gate(root, b, clock.utc(), requested_output=output)


@pytest.mark.parametrize(
    "fault", ["phase", "naive", "more_than120", "zero", "cutoff", "expiry", "native_mismatch"]
)
def test_preparation_metadata_refuses_before_imports(package, monkeypatch, fault):
    root, output, job, native, b = package
    if fault == "phase":
        job["phase"] = "cash"
    elif fault == "naive":
        job["prepare_not_before"] = "2026-11-03T14:34:58"
    elif fault == "more_than120":
        job["prepare_not_before"] = (WAVE - timedelta(seconds=121)).isoformat()
    elif fault == "zero":
        job["prepare_not_before"] = WAVE.isoformat()
    elif fault == "cutoff":
        job["not_before"] = (WAVE - timedelta(seconds=1)).isoformat()
    elif fault == "expiry":
        job["expires_at"] = (WAVE + timedelta(seconds=6)).isoformat()
    else:
        job["prepare_not_before"] = (WAVE - timedelta(seconds=1.5)).isoformat()
    b = artifact(root / "job.json", job)
    monkeypatch.setattr(
        entry.importlib, "import_module", lambda _: pytest.fail("unexpected import")
    )
    with pytest.raises(ValueError):
        entry.prepare_entry(root, b, output, clock=lambda: WAVE - timedelta(seconds=1))


@pytest.mark.parametrize("marker", ["missing", "wrong_job"])
def test_consumed_launcher_required(package, monkeypatch, marker):
    root, output, job, native, b = package
    path = output.with_suffix(".launch-consumed.json")
    path.unlink()
    if marker == "wrong_job":
        artifact(path, dict(job={"different": True}))
    monkeypatch.setattr(
        entry.importlib, "import_module", lambda _: pytest.fail("unexpected import")
    )
    with pytest.raises((ValueError, FileNotFoundError)):
        entry.prepare_entry(root, b, output, clock=lambda: WAVE - timedelta(seconds=1))


def test_late_import_does_not_extend_wave(package, monkeypatch):
    root, output, job, native, b = package
    clock = Clock(WAVE - timedelta(seconds=1))

    def slow_import(name):
        clock.at = WAVE + timedelta(seconds=6)
        clock.mono += 7

    monkeypatch.setattr(entry.importlib, "import_module", slow_import)
    with pytest.raises(ValueError, match="import clock"):
        entry.prepare_entry(
            root, b, output, clock=clock.utc, monotonic=clock.monotonic, sleep=clock.sleep
        )
    with pytest.raises(ValueError, match="inactive"):
        entry.entry_gate(root, b, clock.utc(), requested_output=output)
    assert not output.exists()


def test_backward_utc_has_finite_monotonic_wait(package, monkeypatch):
    root, output, job, native, b = package
    clock = Clock(WAVE - timedelta(seconds=0.1))
    monkeypatch.setattr(entry.importlib, "import_module", lambda _: None)

    def sleep(seconds):
        clock.mono += max(seconds, 0.000001)
        clock.at -= timedelta(seconds=1)

    with pytest.raises(ValueError, match="discontinuity"):
        entry.prepare_entry(
            root, b, output, clock=clock.utc, monotonic=clock.monotonic, sleep=sleep
        )
    assert clock.mono < 101
    assert not output.exists()


def test_opt_out_legacy_no_import_wait_or_file(package, monkeypatch):
    root, output, job, native, b = package
    del job["prepare_not_before"]
    b = artifact(root / "job.json", job)
    monkeypatch.setattr(
        entry.importlib, "import_module", lambda _: pytest.fail("unexpected import")
    )
    entry.prepare_entry(root, b, output, clock=lambda: pytest.fail("unexpected wait"))
    assert not output.with_suffix(".preparation.json").exists()


def test_live_run_body_unchanged():
    before = Path(
        "/root/codex-test/open-composer/reports/research/program/owner-profit-delivery-plan-20261017/paper-delivery/execution-clock-preparation/before/source_runtime_entry.py"
    )
    current = Path(entry.__file__)

    def node(path):
        return next(
            n
            for n in ast.parse(path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "run"
        )

    assert ast.dump(node(before)) == ast.dump(node(current))


def test_main_prepares_then_runs_with_identical_arguments(tmp_path, monkeypatch):
    import sys

    b = artifact(tmp_path / "binding.json", {"invented": True})
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps(b))
    output = tmp_path / "output"
    events = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["entry", "--root", str(tmp_path), "--job-binding", str(pointer), "--output", str(output)],
    )
    monkeypatch.setattr(entry, "prepare_entry", lambda *a: events.append(("prepare", a)))
    monkeypatch.setattr(entry, "run", lambda *a: events.append(("run", a)))
    entry.main()
    assert [x[0] for x in events] == ["prepare", "run"]
    assert events[0][1] == events[1][1] == (tmp_path, b, output)


@pytest.mark.parametrize("jump", [-120, 7, None])
def test_P1_started_clock_rechecked_before_any_import(package, monkeypatch, jump):
    root, output, job, native, b = package
    admitted = WAVE - timedelta(seconds=1)
    started = admitted.replace(tzinfo=None) if jump is None else admitted + timedelta(seconds=jump)
    times = iter([admitted, started])
    imports = []
    monkeypatch.setattr(entry.importlib, "import_module", lambda name: imports.append(name))
    with pytest.raises(ValueError, match="start clock"):
        entry.prepare_entry(root, b, output, clock=lambda: next(times), monotonic=lambda: 100.0)
    assert not imports and not output.exists()


@pytest.mark.parametrize("gate_cost", [1.0, 120.5])
def test_P1_gate_marker_time_cannot_create_new_budget(package, monkeypatch, gate_cost):
    root, output, job, native, b = package
    clock = Clock(WAVE - timedelta(seconds=1))
    real_gate = entry.entry_gate
    imports = []

    def gate(*args, **kwargs):
        result = real_gate(*args, **kwargs)
        clock.mono += gate_cost
        return result

    monkeypatch.setattr(entry, "entry_gate", gate)
    monkeypatch.setattr(entry.importlib, "import_module", lambda name: imports.append(name))
    with pytest.raises(ValueError, match="start clock"):
        entry.prepare_entry(root, b, output, clock=clock.utc, monotonic=clock.monotonic)
    assert not imports


def test_P1_gate_import_time_deducted_from_original_wait_budget(package, monkeypatch):
    root, output, job, native, b = package
    clock = Clock(WAVE - timedelta(seconds=1))
    real_gate = entry.entry_gate
    imports, sleeps = [], []

    def gate(*args, **kwargs):
        result = real_gate(*args, **kwargs)
        clock.mono += 0.6  # elapsed gate/marker work, UTC is not resampled into a new budget
        return result

    def load(name):
        imports.append(name)
        clock.mono += 0.04

    def sleep(seconds):
        sleeps.append(seconds)
        clock.mono += max(seconds, 0.000001)  # frozen UTC; must refuse at original mono deadline

    monkeypatch.setattr(entry, "entry_gate", gate)
    monkeypatch.setattr(entry.importlib, "import_module", load)
    with pytest.raises(ValueError, match="discontinuity"):
        entry.prepare_entry(
            root, b, output, clock=clock.utc, monotonic=clock.monotonic, sleep=sleep
        )
    assert len(imports) == len(entry.PREPARATION_MODULES)
    assert 0.19 < sum(sleeps) < 0.201
    assert not output.exists()
