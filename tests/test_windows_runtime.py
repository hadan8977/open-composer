"""Physical Windows process-tree and committed-memory enforcement checks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from open_composer.research import windows_runtime as runtime
from open_composer.research.process_identity import identity, process_state

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows kernel Job Objects")
MIB = 1048576


def _python(source, *args):
    return [sys.executable, "-X", "utf8", "-c", source, *map(str, args)]


def _wait_file(path, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if path.exists() and path.stat().st_size:
            return path.read_text(encoding="utf-8")
        time.sleep(0.01)
    raise AssertionError(f"Child did not create {path}")


def _wait_exited(saved, timeout=5):
    until = time.monotonic() + timeout
    while process_state(saved) == "running":
        assert time.monotonic() < until, f"Process {saved['pid']} survived job cleanup"
        time.sleep(0.01)


def test_real_job_preserves_literal_arguments_and_records_identity():
    args = ["space here", 'a"b', "中文", "& echo bad", "%PATH%", "$(whoami)", "`x"]
    with runtime.WindowsProcess(
        _python("import sys,json;print(json.dumps(sys.argv[1:],ensure_ascii=False))", *args),
        memory_bytes=100 * MIB,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as process:
        saved = identity(process.pid)
        stdout, _ = process.communicate(timeout=5)
        assert json.loads(stdout) == args
    assert saved["start_ticks"] > 0
    assert process_state(saved) == "exited"


def test_timeout_closes_entire_real_process_tree(tmp_path):
    marker = tmp_path / "grandchild.json"
    source = (
        "import subprocess,sys,time,json,pathlib;"
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid}));time.sleep(60)"
    )
    with runtime.WindowsProcess(_python(source, marker), memory_bytes=150 * MIB) as process:
        child = identity(json.loads(_wait_file(marker))["pid"])
        leader = identity(process.pid)
        assert process_state(child) == "running"
        with pytest.raises(subprocess.TimeoutExpired):
            process.communicate(timeout=0.05)
    _wait_exited(child)
    _wait_exited(leader)


def test_leader_exit_does_not_leave_descendants_running(tmp_path):
    marker = tmp_path / "orphan.txt"
    source = (
        "import subprocess,sys,pathlib;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
    )
    with runtime.WindowsProcess(_python(source, marker), memory_bytes=150 * MIB) as process:
        child = identity(int(_wait_file(marker)))
        assert process.wait(timeout=5) == 0
    _wait_exited(child)


def test_kill_on_close_survives_controller_crash(tmp_path):
    marker = tmp_path / "tree.json"
    root = Path(__file__).resolve().parents[1]
    controller_source = (
        "import sys,json,pathlib,time;sys.path.insert(0,sys.argv[1]);"
        "from open_composer.research.windows_runtime import WindowsProcess;"
        "from open_composer.research.process_identity import identity;"
        "p=WindowsProcess([sys.executable,'-c','import time;time.sleep(60)'],"
        "memory_bytes=104857600);"
        "pathlib.Path(sys.argv[2]).write_text(json.dumps(identity(p.pid)));time.sleep(60)"
    )
    controller = subprocess.Popen(_python(controller_source, root, marker))
    try:
        saved = json.loads(_wait_file(marker))
        assert process_state(saved) == "running"
        controller.kill()
        controller.wait(timeout=5)
        _wait_exited(saved)
    finally:
        if controller.poll() is None:
            controller.kill()
            controller.wait(timeout=5)


def test_kernel_rejects_committed_memory_over_job_limit():
    source = (
        "import sys\ntry:\n x=bytearray(256*1048576)\n"
        "except MemoryError:\n print('memory-denied',flush=True);sys.exit(23)\n"
        "raise RuntimeError('memory limit did not hold')"
    )
    with runtime.WindowsProcess(
        _python(source), memory_bytes=64 * MIB, stdout=subprocess.PIPE, text=True
    ) as process:
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 23
        assert output.strip() == "memory-denied"


def test_reused_pid_is_not_the_saved_process():
    saved = identity(os.getpid())
    assert process_state(saved) == "running"
    assert process_state({**saved, "start_ticks": saved["start_ticks"] + 1}) == "exited"


def test_node_shim_resolution_bypasses_shell_and_preserves_arguments(tmp_path, monkeypatch):
    shim = tmp_path / "codex.cmd"
    shim.write_text("do not execute this shell file")
    node = tmp_path / "node.exe"
    node.touch()
    script = tmp_path / "node_modules/@openai/codex/bin/codex.js"
    script.parent.mkdir(parents=True)
    script.touch()
    monkeypatch.setattr(runtime.shutil, "which", lambda value: str(shim))
    args = ["codex", "a & b", "%x%", 'quoted"argument']
    assert runtime.executable_argv(args) == [str(node), str(script), *args[1:]]
