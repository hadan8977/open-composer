"""Finite storage repair witnesses; no provider, account or strategy invocation."""

import ast
import json
import os
import socket
import stat
from pathlib import Path

import pytest

from open_composer.intraday_runner import current_initialization_entry as entry
from open_composer.intraday_runner import current_initialization_storage as storage


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def original_inventory(roots):
    allocated, seen = 0, set()
    for root in roots:
        for base, _, names in os.walk(root, followlinks=False):
            for path in [Path(base), *(Path(base) / n for n in names)]:
                item = path.lstat()
                key = item.st_dev, item.st_ino
                if key in seen or stat.S_ISLNK(item.st_mode):
                    continue
                seen.add(key)
                if stat.S_ISDIR(item.st_mode) or (
                    stat.S_ISREG(item.st_mode) and item.st_nlink == 1
                ):
                    allocated += item.st_blocks * 512
    return allocated


def test_complete_inventory_parity_and_fresh_growth(tmp_path):
    root = tmp_path / "root"
    child = root / "nested"
    child.mkdir(parents=True)
    (root / "exclusive").write_bytes(b"a" * 9000)
    (child / "file").write_bytes(b"b" * 14000)
    os.link(child / "file", root / "hardlink")
    (tmp_path / "outside").write_bytes(b"c" * 9000)
    os.link(tmp_path / "outside", child / "external-hardlink")
    (root / "file-link").symlink_to(tmp_path / "outside")
    (root / "dir-link").symlink_to(child, target_is_directory=True)
    (root / "broken").symlink_to(tmp_path / "absent")
    os.mkfifo(root / "fifo")
    roots = [str(root), str(child), str(root), str(tmp_path / "missing")]
    before = storage.allocated_bytes(roots)
    assert before == original_inventory(roots)
    (child / "new").write_bytes(b"d" * 19000)
    after = storage.allocated_bytes(roots)
    assert after == original_inventory(roots) and after > before
    (child / "new").unlink()
    assert storage.allocated_bytes(roots) == original_inventory(roots)


def test_alias_and_unreadable_or_replaced_directory_refuse(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="alias"):
        storage.allocated_bytes([str(alias)])
    with pytest.raises(ValueError, match="alias"):
        storage.allocated_bytes(["relative"])
    original = os.scandir

    def refuse(fd):
        raise PermissionError("invented unavailable tree")

    monkeypatch.setattr(os, "scandir", refuse)
    with pytest.raises(PermissionError):
        storage.allocated_bytes([str(target)])
    monkeypatch.setattr(os, "scandir", original)
    (target / "regular-root").write_text("x")
    with pytest.raises(NotADirectoryError):
        storage.allocated_bytes([str(target / "regular-root")])


def extracted_check(monkeypatch, tmp_path):
    tree = ast.parse(Path(entry.__file__).read_text())
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    check = next(n for n in run.body if isinstance(n, ast.FunctionDef) and n.name == "check")
    job = {"code_bindings": [{"path": "reader"}], "phase": "session"}
    calls = []

    class Fresh:
        def __init__(self, root, current):
            assert current == job

        def check(self, extra, *, path=None):
            calls.append(("capacity", extra, path))
            if type(extra) is not int or extra < 0 or extra > 100:
                raise ValueError("refuse")
            return {"remaining_current": 100}

    def bound(root, binding):
        calls.append(("binding", binding))
        return json.dumps(job).encode()

    ns = dict(vars(entry), root=tmp_path, job=job, binding={"path": "job"})
    ns.update(
        NativeStorage=Fresh,
        bound_bytes=bound,
        kernel_evidence=lambda: calls.append(("kernel",)),
        gate=lambda *a, **kw: (
            job,
            {},
            {"capacity": Fresh(tmp_path, job).check(0)},
        ),
    )
    exec(compile(ast.Module(body=[check], type_ignores=[]), "<exact-check>", "exec"), ns)
    return ns["check"], calls


def test_one_scan_per_local_boundary_never_cached(tmp_path, monkeypatch):
    check, calls = extracted_check(monkeypatch, tmp_path)
    for _ in range(2):
        check(local_only=True, extra_write_bytes=20, write_path=str(tmp_path / "output"))
    assert len([c for c in calls if c[0] == "capacity"]) == 2
    assert len([c for c in calls if c[0] == "kernel"]) == 2
    assert len([c for c in calls if c[0] == "binding"]) == 4
    check()  # A later physical boundary still runs its own fresh gate.
    assert len([c for c in calls if c[0] == "capacity"]) == 3
    with pytest.raises(ValueError):
        check(local_only=True, write_method="POST")
    with pytest.raises(ValueError):
        check(local_only=True, extra_write_bytes=101)


def test_failure_trace_has_only_code_locations():
    import traceback

    try:
        secret_local = "credential-never-log"
        raise ValueError(secret_local)
    except ValueError as exc:
        tree = ast.parse(Path(entry.__file__).read_text())
        location = next(
            k.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "dict"
            for k in n.keywords
            if k.arg == "locations"
        )
        result = eval(
            compile(ast.Expression(location), "<trace-fields>", "eval"),
            {"traceback": traceback, "exc": exc},
        )
    assert result and all(set(row) == {"file", "line", "function"} for row in result)
    assert secret_local not in json.dumps(result)
    assert traceback is not None
