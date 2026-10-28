"""Invented slot publications only; no broker, native entry or financial state."""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.intraday_runner.current_initialization_storage import CaptureSlots, NativeStorage


@pytest.fixture
def slots(tmp_path, monkeypatch):
    checks = []

    def save_manifest(path, value):
        path.write_text(json.dumps(value))
        raw = path.read_bytes()
        return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

    storage = SimpleNamespace(
        root=tmp_path,
        job={"protected_normal_bytes": 10918947664, "whole_route_bytes": 94044160},
        check=lambda *a, **kw: checks.append((a, kw)),
        save=save_manifest,
    )
    storage.physical = lambda: NativeStorage.physical(storage)
    trace = tmp_path / "transport"
    trace.mkdir()
    result = CaptureSlots(storage, tmp_path / "account", trace, {"AAPL"}, 0)
    assert len(checks) == 2 + len(result.files)
    monkeypatch.setattr(os, "statvfs", lambda p: SimpleNamespace(f_bavail=20000000000, f_frsize=1))
    return result, tmp_path, checks


def test_exact_publication_no_allocation_or_second_use(slots):
    s, root, checks = slots
    path = root / "account/account.json"
    before = path.stat()
    payload = b'{"invented": true}\n'
    result = s.publish(path, payload)
    actual = path.read_bytes()
    assert json.loads(actual) == {"invented": True}
    assert result == dict(
        path=str(path), bytes=len(actual), sha256=hashlib.sha256(actual).hexdigest()
    )
    after = path.stat()
    assert (before.st_ino, before.st_blocks, before.st_size) == (
        after.st_ino,
        after.st_blocks,
        after.st_size,
    )
    assert len(checks) == 2 + len(s.files)
    with pytest.raises(ValueError, match="consumed"):
        s.publish(path, payload)


@pytest.mark.parametrize("defect", ["replace", "hardlink", "truncate", "ancestor"])
def test_inode_extent_and_ancestor_drift_refuse(slots, defect):
    s, root, _ = slots
    path = root / "account/account.json"
    if defect == "replace":
        old = path.with_suffix(".retained")
        path.rename(old)
        path.write_bytes(old.read_bytes())
    elif defect == "hardlink":
        os.link(path, root / "alias")
    elif defect == "truncate":
        with path.open("r+b") as f:
            f.truncate(1)
    else:
        parent = path.parent
        parent.rename(root / "retained")
        parent.mkdir()
        path.write_bytes((root / "retained/account.json").read_bytes())
    with pytest.raises((ValueError, FileNotFoundError)):
        s.publish(path, b"{}\n")


def test_foreign_growth_refuses_without_consuming_slot(slots, monkeypatch):
    s, root, _ = slots
    monkeypatch.setattr(os, "statvfs", lambda p: SimpleNamespace(f_bavail=1, f_frsize=1))
    path = root / "account/account.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="physical"):
        s.publish(path, b"{}\n")
    assert path.read_bytes() == before
    assert path not in s.used


def test_partial_write_failure_stays_consumed_and_retained(slots, monkeypatch):
    s, root, _ = slots
    real = os.pwrite
    path = root / "account/positions.json"
    calls = []

    def failed(fd, data, offset):
        calls.append(offset)
        if len(calls) == 2:
            raise OSError("invented storage failure")
        return real(fd, data[:1024], offset)

    monkeypatch.setattr(os, "pwrite", failed)
    with pytest.raises(OSError):
        s.publish(path, b"[]\n")
    assert path in s.used and path.exists()
    with pytest.raises(ValueError, match="consumed"):
        s.publish(path, b"[]\n")


def test_oversize_and_unreserved_path_never_write(slots):
    s, root, _ = slots
    path = root / "account/account.json"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="overflow"):
        s.publish(path, b"x" * (len(before) + 1))
    assert before == path.read_bytes()
    with pytest.raises(ValueError, match="unknown"):
        s.publish(root / "outside.json", b"{}\n")
    assert not (root / "outside.json").exists()


def test_runtime_overflow_preserves_complete_value_and_original_extent(slots):
    from open_composer.intraday_runner.current_initialization_runtime import (
        CurrentInitializationRuntime,
    )

    s, root, _ = slots
    runtime = CurrentInitializationRuntime.__new__(CurrentInitializationRuntime)
    runtime.capture_slots = s
    events = []
    runtime.read_guard = lambda **kw: events.append(("authority", kw))
    runtime.guard_write = lambda path, size: events.append(("full_write", str(path), size))
    path = root / "account/account.json"
    value = {"invented": "x" * 20000}
    before = path.read_bytes()
    binding = runtime.save_capture(path, value)
    assert events[0] == ("authority", {"preparation_only": True})
    assert events[1][0] == "full_write"
    assert json.loads(Path(binding["path"]).read_text()) == value
    assert binding["path"] == str(path) + ".overflow.json"
    assert path.read_bytes() == before and path in s.used


def test_get_coverage_requires_published_intent_and_reserved_body(slots):
    s, root, _ = slots
    path = root / "transport/0000.prepared.json"
    binding = {"path": str(path)}
    assert not s.covers_get("account", binding)
    binding = s.publish(path, b'{"invented":true}\n')
    assert s.covers_get("account", binding)
    assert not s.covers_get("activities-001", binding)
    s.guard_get()
    with (root / "account/positions.json").open("r+b") as stream:
        stream.truncate(1)
    with pytest.raises(ValueError, match="extent"):
        s.guard_get()


def test_preallocated_native_partial_is_complete_and_blocks_further_get(tmp_path):
    from open_composer.intraday_runner.current_initialization_storage import (
        SLOTS,
        require_partial_room,
        retain_partial,
    )

    output = tmp_path / "invocation"
    launcher = Path(str(output) + ".launcher")
    launcher.mkdir()
    path = launcher / "capture-partial.json"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        os.posix_fallocate(fd, 0, SLOTS[path.name])
        os.fsync(fd)
    finally:
        os.close(fd)
    storage = SimpleNamespace(job={"output": str(output)})
    require_partial_room(storage)
    value = {"usable": False, "invented_received_prefix": "x" * 2100000}
    retain_partial(storage, value)
    assert json.loads(path.read_bytes()) == value
    before = path.read_bytes()
    with pytest.raises(ValueError, match="partial"):
        require_partial_room(storage)
    with pytest.raises(ValueError, match="partial"):
        retain_partial(storage, {"usable": False})
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "filename,whole,normal",
    [
        (
            "capacity-six-current-session-whole256MiB-admission-20261020.json",
            268435456,
            10919240084,
        ),
        (
            "capacity-six-current-session-whole320MiB-M2-admission-20261020.json",
            335544320,
            10919249663,
        ),
        (
            "capacity-six-current-session-whole384MiB-M3-corrected-admission-20261020.json",
            402653184,
            10919282270,
        ),
    ],
)
def test_actual_receipt_full_physical_and_logical_bounds(monkeypatch, filename, whole, normal):
    from open_composer.intraday_runner import current_initialization_storage as storage

    root = Path("/root/codex-test/open-composer")
    folder = (
        root
        / "reports/research/program/owner-profit-delivery-plan-20261017"
        / "paper-delivery/preopen-20261020"
    )
    job = json.loads((folder / "BASE-native-session-01/job.json").read_text())
    receipt_path = root / "reports/ops/disk-audit-20261015" / filename
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    job.update(
        capacity_receipt=dict(
            path=str(receipt_path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()
        ),
        whole_route_bytes=whole,
        protected_normal_bytes=normal,
        current_normal_forecast=(
            receipt["request_bindings"]["postpublication_complete_normal"]
            if whole == 402653184
            else receipt["concurrent_protected_commitments"]["complete_normal"]["receipt"]
        ),
    )
    monkeypatch.setattr(storage, "allocated_bytes", lambda roots: 60000000)
    floor = normal + whole + 12582912 + 1073741824 + 65536 + 12288
    monkeypatch.setattr(os, "statvfs", lambda p: SimpleNamespace(f_bavail=floor, f_frsize=1))
    result = storage.capacity(root, job)
    assert result["remaining_current"] == whole - 60000000 - 3 * 1048576
    assert result["full_uncredited_physical_guard"] is True
    monkeypatch.setattr(os, "statvfs", lambda p: SimpleNamespace(f_bavail=floor - 1, f_frsize=1))
    with pytest.raises(ValueError, match="protected"):
        storage.capacity(root, job)
    monkeypatch.setattr(
        os, "statvfs", lambda p: SimpleNamespace(f_bavail=floor + 1000000000, f_frsize=1)
    )
    monkeypatch.setattr(storage, "allocated_bytes", lambda roots: whole - 3 * 1048576 + 1)
    with pytest.raises(ValueError, match="overflow"):
        storage.capacity(root, job)


def test_same_call_authority_result_is_fresh_and_false_never_authorizes(monkeypatch):
    from datetime import UTC, datetime

    from open_composer.intraday_runner import current_initialization_runtime as module

    r = module.CurrentInitializationRuntime.__new__(module.CurrentInitializationRuntime)
    r._operation_held = True
    r.secure_snapshot = None
    r.auth = dict(authorized_at="2026-10-20T00:00:00Z", expires_at="2026-10-20T20:10:00Z")
    r.clock = lambda: datetime(2026, 10, 20, 15, tzinfo=UTC)
    calls = []

    def check(**kwargs):
        calls.append(kwargs)
        return dict(r.auth)

    check.receives_authority = True
    r.entry_guard = check
    monkeypatch.setattr(
        module, "load_authority", lambda *a: pytest.fail("duplicate authority reception")
    )
    r.read_guard(preparation_only=True)
    r.read_guard()
    assert calls == [
        dict(preparation_only=True, receive_authority=True),
        dict(preparation_only=False, receive_authority=True),
    ]
    for value in (False, None, {}, {"authorized_at": "invented"}):

        def refused(_value=value, **kwargs):
            return _value

        refused.receives_authority = True
        r.entry_guard = refused
        with pytest.raises(ValueError, match="scope drift"):
            r.read_guard()
