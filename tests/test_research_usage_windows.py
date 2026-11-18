from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows anonymous pipes and Jobs")

SPEC = importlib.util.spec_from_file_location(
    "research_usage_windows", Path(__file__).resolve().parents[1] / "scripts/research_usage.py"
)
usage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(usage)


def offline_factory(tmp_path, *, failure=None, descendant=False):
    from open_composer.research.windows_runtime import WindowsProcess

    methods = tmp_path / "rpc-methods.jsonl"
    child_file = tmp_path / "child.pid"
    result = {"rateLimits": {"secondary": {"usedPercent": 40, "windowDurationMins": 10080}}}
    script = (
        "import json,sys,time,subprocess; from pathlib import Path\n"
        f"methods=Path({str(methods)!r})\n"
    )
    if descendant:
        child = (
            "import os,time; from pathlib import Path; "
            f"Path({str(child_file)!r}).write_text(str(os.getpid())); time.sleep(30)"
        )
        script += (
            f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
            f"while not Path({str(child_file)!r}).exists():time.sleep(.01)\n"
        )
    if failure == "silent":
        script += "time.sleep(30)\n"
    else:
        script += (
            "for line in sys.stdin:\n"
            " request=json.loads(line)\n"
            " with methods.open('a') as stream:stream.write(request['method']+'\\n')\n"
            " if request['method']=='initialize':\n"
            "  body=json.dumps({'id':1,'result':{}}).encode()+b'\\n'\n"
            "  sys.stdout.buffer.write(body[:7]);sys.stdout.buffer.flush()\n"
            "  time.sleep(.02);sys.stdout.buffer.write(body[7:]);sys.stdout.buffer.flush()\n"
            " if request['method']=='account/rateLimits/read':\n"
            f"  print(json.dumps({{'id':2,'result':{result!r}}}),flush=True)\n"
            "time.sleep(30)\n"
        )
    processes = []

    def factory(command, **kwargs):
        assert command == ["codex", "app-server"]
        process = WindowsProcess(
            [sys.executable, "-u", "-c", script],
            memory_bytes=64 * 1024**2,
            **kwargs,
        )
        processes.append(process)
        return process

    return factory, processes, methods, child_file, result


def test_fragmented_read_only_rpc_cleans_its_descendant_and_reader(tmp_path):
    from open_composer.research.process_identity import identity, process_state

    factory, processes, methods, child_file, result = offline_factory(tmp_path, descendant=True)
    assert usage.read_account_limits(timeout=5, popen=factory) == result
    assert methods.read_text().splitlines() == [
        "initialize",
        "initialized",
        "account/rateLimits/read",
    ]
    assert processes[0].poll() is not None
    child, deadline = int(child_file.read_text()), time.monotonic() + 5
    while True:  # the job kill is asynchronous
        try:
            if process_state(identity(child)) == "exited":
                break
        except ProcessLookupError:
            break
        assert time.monotonic() < deadline, "descendant survived the job"
        time.sleep(0.01)
    assert not any(t.name == "oc-account-usage-reader" for t in threading.enumerate())


def test_timeout_closes_job_and_reader(tmp_path):
    factory, processes, _, _, _ = offline_factory(tmp_path, failure="silent")
    with pytest.raises(TimeoutError):
        usage.read_account_limits(timeout=0.3, popen=factory)
    assert processes[0].poll() is not None
    assert not any(t.name == "oc-account-usage-reader" for t in threading.enumerate())


def test_real_factory_applies_memory_admission_before_launch(monkeypatch, tmp_path):
    from open_composer.research import windows_runtime

    budget = {"job_max_mb": 2458, "oc_max_mb": 2200, "reserve_mb": 500, "heavy_job_mb": 200}
    config = tmp_path / "config"
    config.mkdir()
    (config / "memory-budget.json").write_text(json.dumps(budget))
    monkeypatch.setattr(usage, "ROOT", tmp_path)
    monkeypatch.setattr(
        windows_runtime, "global_memory",
        lambda: {"available_mb": 500, "available_commit_mb": 500},
    )
    monkeypatch.setattr(
        windows_runtime, "WindowsProcess", lambda *_a, **_kw: pytest.fail("No headroom")
    )
    with pytest.raises(MemoryError, match="headroom"):
        usage.read_account_limits(timeout=1)
