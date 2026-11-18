"""Cross-process locks, UTF-8 transport and the real nested Windows entry point."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from open_composer.research.agent_workflow import execute
from open_composer.research.file_lock import lock_file
from open_composer.research.windows_runtime import WindowsProcess

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows integration")
ROOT = Path(__file__).resolve().parents[1]


def test_file_lock_excludes_other_process_and_releases_after_death(tmp_path):
    path, ready = tmp_path / "锁.lock", tmp_path / "ready"
    source = (
        "import sys,time;from pathlib import Path;"
        "from open_composer.research.file_lock import lock_file;"
        "f=Path(sys.argv[1]).open('a');lock_file(f);"
        "Path(sys.argv[2]).write_text('ready');time.sleep(30)"
    )
    with WindowsProcess(
        [sys.executable, "-c", source, str(path), str(ready)], memory_bytes=64 * 1048576
    ) as process:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        with path.open("a") as other:
            with pytest.raises(BlockingIOError):
                lock_file(other, blocking=False)
        process.kill()
        process.wait(timeout=5)
    with path.open("a") as other:
        lock_file(other, blocking=False)


def test_utf8_transport_and_chinese_artifact_path(tmp_path):
    folder = tmp_path / "中文回合"
    folder.mkdir()
    program = (
        "import json,sys;value=sys.stdin.read();"
        "print(json.dumps({'type':'thread.started','thread_id':value},ensure_ascii=False))"
    )
    result = execute([sys.executable, "-c", program], "中文断点", folder, 5)
    assert result["session"] == "中文断点"
    assert "中文断点" in (folder / "events.jsonl").read_text(encoding="utf-8")


def test_bounded_agent_can_launch_native_numeric_entry(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/memory-budget.json").write_text(
        json.dumps(
            {
                "oc_max_mb": 256,
                "job_max_mb": 256,
                "reserve_mb": 500,
                "heavy_job_mb": 200,
            }
        )
    )
    runner = ROOT / "scripts/run_capped.py"
    target = tmp_path / "result.json"
    numeric = (
        "import json,sys;from pathlib import Path;"
        "Path(sys.argv[1]).write_text(json.dumps(sum(i*i for i in range(10000))))"
    )
    command = [
        sys.executable,
        str(runner),
        "--root",
        str(tmp_path),
        "--mem",
        "128M",
        "--",
        sys.executable,
        "-c",
        numeric,
        str(target),
    ]
    controller = (
        "import json,subprocess,sys;raise SystemExit(subprocess.call(json.loads(sys.argv[1])))"
    )
    with WindowsProcess(
        [sys.executable, "-c", controller, json.dumps(command)],
        memory_bytes=192 * 1048576,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        _, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
    assert json.loads(target.read_text()) == 333283335000
