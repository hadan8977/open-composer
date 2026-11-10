"""Offline launch-boundary tests; the systemd substitute never executes a command."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def capped_stub(tmp_path: Path) -> tuple[Path, Path, Path]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    wrapper = scripts / "run_capped.sh"
    shutil.copy2(ROOT / "scripts/run_capped.sh", wrapper)
    (scripts / "memory_budget.py").write_text(
        "import os, sys\n"
        "if sys.argv[1] == 'config':\n print(2458)\n sys.exit(0)\n"
        "print('fixture memory admission', file=sys.stderr)\n"
        "sys.exit(int(os.environ['TEST_ADMISSION_RC']))\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "systemd-inert.json"
    systemd = bin_dir / "systemd-run"
    systemd.write_text(
        "#!/usr/bin/python3\nimport json, os, sys\n"
        "open(os.environ['TEST_SYSTEMD_MARKER'], 'w').write(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    systemd.chmod(0o755)
    return wrapper, bin_dir, marker


def _run(
    capped_stub: tuple[Path, Path, Path], code: int, klass: str
) -> subprocess.CompletedProcess:
    wrapper, bin_dir, marker = capped_stub
    env = dict(os.environ)
    env.update(
        PATH=str(bin_dir) + os.pathsep + env["PATH"],
        TEST_ADMISSION_RC=str(code),
        TEST_SYSTEMD_MARKER=str(marker),
    )
    return subprocess.run(
        [
            "bash",
            str(wrapper),
            "--class",
            klass,
            "--mem",
            "900M",
            "--wait-min",
            "0",
            "--",
            "fixture-command-never-executed",
            "literal-argument",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


@pytest.mark.parametrize("code", [1, 2, 3, 124, 127])
def test_research_requires_successful_memory_admission(capped_stub, code: int) -> None:
    result = _run(capped_stub, code, "research")
    assert result.returncode == 75
    assert not capped_stub[2].exists()
    if code != 2:
        assert f"memory check failed (rc={code})" in result.stderr


def test_admitted_research_keeps_kernel_limits_and_command(capped_stub) -> None:
    result = _run(capped_stub, 0, "research")
    assert result.returncode == 0, result.stderr
    args = json.loads(capped_stub[2].read_text())
    assert "--slice=oc-research-capped" in args
    assert "MemoryMax=900M" in args and "MemorySwapMax=1G" in args
    assert args[-2:] == ["fixture-command-never-executed", "literal-argument"]


def test_paper_keeps_independent_launch_semantics_on_admission_error(capped_stub) -> None:
    result = _run(capped_stub, 1, "paper")
    assert result.returncode == 0, result.stderr
    args = json.loads(capped_stub[2].read_text())
    assert "--slice=paper-capped" in args
    assert "MemoryMax=900M" in args and "MemorySwapMax=1G" in args
    assert args[-2:] == ["fixture-command-never-executed", "literal-argument"]
