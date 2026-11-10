from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_composer.remote import windows_worker


def _ready_status(**overrides) -> dict:
    return {
        "status": "ready",
        "usage_ok": True,
        "usage_bytes": 4 * (1 << 30),
        "usage_gib": 4.0,
        "root": r"C:\paseo",
        "paused": False,
        "hard_off": False,
        **overrides,
    }


def _mock_remote(monkeypatch, status, workspaces=None) -> None:
    monkeypatch.setattr(windows_worker, "read_worker_status", lambda root: status)
    monkeypatch.setattr(
        windows_worker,
        "_json_command",
        lambda *args: (
            None,
            [{"workspaceId": "wks", "cwd": r"C:\paseo"}] if workspaces is None else workspaces,
        ),
    )


def _write_contract(root: Path, *, remote_root: str = r"C:\paseo") -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    wrapper = root / "scripts" / "paseo-windows"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o755)
    (root / "config" / "windows-paseo-worker.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "transport": "paseo-relay",
                "wrapper": "scripts/paseo-windows",
                "offer_file": str(root / "offer"),
                "remote_root": remote_root,
                "max_usage_gib": 50,
                "scratch_root": r"C:\paseo\scratch",
                "workspace_id": "wks",
            }
        ),
        encoding="utf-8",
    )
    offer = root / "offer"
    offer.write_text("placeholder\n", encoding="utf-8")
    offer.chmod(0o600)


def test_contract_and_local_preflight_are_small_and_fixed(tmp_path: Path) -> None:
    _write_contract(tmp_path)

    payload = windows_worker.worker_preflight(tmp_path)

    assert payload["ok"] is True
    assert windows_worker.load_worker_contract(tmp_path)["remote_root"] == r"C:\paseo"
    _write_contract(tmp_path, remote_root=r"D:\worker")
    with pytest.raises(ValueError, match="root"):
        windows_worker.load_worker_contract(tmp_path)


def test_wrapper_redacts_offer_and_rejects_endpoint_override(tmp_path: Path, monkeypatch) -> None:
    _write_contract(tmp_path)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="https://app.paseo.sh/#offer=secret-value",
            stderr="",
        )

    monkeypatch.setattr(windows_worker.subprocess, "run", fake_run)
    result = windows_worker.run_worker_command(tmp_path, ["status"])
    assert result.ok and "secret-value" not in result.stdout and "[redacted]" in result.stdout
    with pytest.raises(ValueError, match="endpoint"):
        windows_worker.run_worker_command(tmp_path, ["--host", "other:1234"])


def test_remote_preflight_checks_worker_and_workspace(tmp_path: Path, monkeypatch) -> None:
    _write_contract(tmp_path)
    _mock_remote(monkeypatch, _ready_status())

    payload = windows_worker.worker_preflight(tmp_path, remote=True)

    assert payload["ok"] is True


@pytest.mark.parametrize(
    "usage",
    [
        None,
        True,
        False,
        -1,
        1.0,
        "1",
        float("nan"),
        float("inf"),
        windows_worker.MAX_USAGE_BYTES,
        windows_worker.MAX_USAGE_BYTES + 1,
    ],
)
def test_remote_preflight_rejects_unknown_or_at_limit_exact_bytes(
    tmp_path: Path, monkeypatch, usage
) -> None:
    _write_contract(tmp_path)
    _mock_remote(monkeypatch, _ready_status(usage_bytes=usage))

    result = windows_worker.worker_preflight(tmp_path, remote=True)

    assert result["ok"] is False
    assert not next(
        check["ok"] for check in result["checks"] if check["name"] == "remote_worker_usage"
    )


def test_remote_preflight_rejects_missing_usage_even_with_rounded_display(
    tmp_path: Path, monkeypatch
) -> None:
    _write_contract(tmp_path)
    status = _ready_status()
    del status["usage_bytes"]
    _mock_remote(monkeypatch, status)

    assert windows_worker.worker_preflight(tmp_path, remote=True)["ok"] is False


@pytest.mark.parametrize(
    "override",
    [
        {"root": r"D:\other"},
        {"root": None},
        {"root": True},
        {"status": "unknown"},
        {"status": "paused"},
        {"usage_ok": "true"},
        {"paused": True},
        {"paused": None},
        {"hard_off": True},
        {"hard_off": "false"},
    ],
)
def test_remote_preflight_rejects_root_and_status_conflicts(
    tmp_path: Path, monkeypatch, override
) -> None:
    _write_contract(tmp_path)
    _mock_remote(monkeypatch, _ready_status(**override))

    assert windows_worker.worker_preflight(tmp_path, remote=True)["ok"] is False


@pytest.mark.parametrize("usage", [0, windows_worker.MAX_USAGE_BYTES - 1])
def test_remote_preflight_accepts_exact_below_limit_bytes_and_windows_case(
    tmp_path: Path, monkeypatch, usage
) -> None:
    _write_contract(tmp_path)
    _mock_remote(monkeypatch, _ready_status(usage_bytes=usage, usage_gib=50.0, root=r"c:\PASEO"))

    assert windows_worker.worker_preflight(tmp_path, remote=True)["ok"] is True


@pytest.mark.parametrize(
    "workspaces", [{"error": "unknown"}, [None], [{"workspaceId": "wks", "cwd": False}]]
)
def test_remote_preflight_unknown_workspace_fails_without_accepting_status(
    tmp_path: Path, monkeypatch, workspaces
) -> None:
    _write_contract(tmp_path)
    _mock_remote(monkeypatch, _ready_status(), workspaces)

    assert windows_worker.worker_preflight(tmp_path, remote=True)["ok"] is False


def test_manifest_checks_hash_and_scratch(tmp_path: Path) -> None:
    _write_contract(tmp_path)
    source = tmp_path / "fixture.txt"
    source.write_text("fixture-data\n", encoding="utf-8")
    manifest = {
        "job_id": "fixture-001",
        "iteration_id": "iter-fixture",
        "remote_root": r"C:\paseo",
        "remote_scratch": r"C:\paseo\scratch\fixture-001",
        "inputs": [
            {
                "local_path": "fixture.txt",
                "bytes": source.stat().st_size,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ],
        "cleanup": {"required": True},
    }

    result = windows_worker.validate_task_manifest(tmp_path, manifest)
    assert result["ok"] is True
    assert result["dynamic_headroom_checked"] is False
    assert result["expected_added_bytes"] is None
    manifest["expected_added_bytes"] = source.stat().st_size + 1024
    result = windows_worker.validate_task_manifest(tmp_path, manifest)
    assert result["expected_added_bytes"] == source.stat().st_size + 1024
    assert result["dynamic_headroom_checked"] is False
    for footprint in (
        None,
        True,
        -1,
        1.0,
        float("nan"),
        source.stat().st_size - 1,
        windows_worker.MAX_USAGE_BYTES,
        60 * (1 << 30),
    ):
        manifest["expected_added_bytes"] = footprint
        with pytest.raises(ValueError, match="expected_added_bytes"):
            windows_worker.validate_task_manifest(tmp_path, manifest)
    manifest["expected_added_bytes"] = source.stat().st_size
    manifest["inputs"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash/size"):
        windows_worker.validate_task_manifest(tmp_path, manifest)


def test_status_ignores_echoed_command_and_old_ready_status(tmp_path: Path, monkeypatch) -> None:
    _write_contract(tmp_path)
    monkeypatch.setattr(windows_worker, "_terminal_id", lambda: "control-terminal")
    monkeypatch.setattr(windows_worker.uuid, "uuid4", lambda: SimpleNamespace(hex="fresh"))
    monkeypatch.setattr(windows_worker.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        windows_worker, "run_worker_command", lambda *a, **kw: SimpleNamespace(ok=True)
    )
    old = '{"status":"ready","usage_ok":true,"usage_gib":0}'
    echo = "powershell -Command Write-Output 'OC_STATUS_fresh_BEGIN'; status; OC_STATUS_fresh_END"
    captures = iter(
        [
            {"lines": [old, echo]},
            {
                "lines": [
                    old,
                    echo,
                    "OC_STATUS_fresh_BEGIN",
                    '{"status":"paused","usage_ok":true,"usage_gib":6}',
                    "OC_STATUS_fresh_END",
                ]
            },
        ]
    )
    monkeypatch.setattr(windows_worker, "_json_command", lambda *a, **kw: (None, next(captures)))

    status = windows_worker.read_worker_status(tmp_path)

    assert status["status"] == "paused"
    assert status["usage_gib"] == 6


def test_missing_current_status_never_falls_back_to_scrollback(tmp_path: Path, monkeypatch) -> None:
    _write_contract(tmp_path)
    monkeypatch.setattr(windows_worker, "_terminal_id", lambda: "control-terminal")
    monkeypatch.setattr(windows_worker.uuid, "uuid4", lambda: SimpleNamespace(hex="fresh"))
    monkeypatch.setattr(
        windows_worker, "run_worker_command", lambda *a, **kw: SimpleNamespace(ok=True)
    )
    captured = {
        "lines": [
            '{"status":"ready"}',
            "OC_STATUS_fresh_BEGIN",
            "status command failed",
            "OC_STATUS_fresh_END",
        ]
    }
    monkeypatch.setattr(windows_worker, "_json_command", lambda *a, **kw: (None, captured))

    with pytest.raises(json.JSONDecodeError):
        windows_worker.read_worker_status(tmp_path)


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not installed")
def test_powershell_status_publishes_exact_bytes_and_refuses_equality() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "deploy/windows/open-composer-worker.ps1"
    ).read_text()
    functions = []
    for name in ("Get-EffectiveStatus", "Write-State"):
        match = re.search(rf"(?ms)^function {name}\b.*?^\}}", source)
        assert match, name
        functions.append(match.group())
    # Evaluate the actual status functions with inert filesystem functions.
    # No worker script action, directory or switch is touched.
    script = r"""
$root = 'C:\paseo'
$scratch = 'C:\paseo\scratch'
$pauseFile = 'offline.pause'
$hardOffFile = 'offline.hard-off'
$stateFile = 'offline.state'
$maxUsageBytes = [int64](50 * 1GB)
$maxUsageGiB = 50
function Ensure-Directories {}
function Test-Path { param($LiteralPath); return $false }
function Get-UsageBytes { return $script:testUsageBytes }
function Get-FreeGiB { return 100 }
function Set-Content {
    param([Parameter(ValueFromPipeline=$true)]$Value, $Encoding, $Path)
    process { $script:capturedState = $Value }
}
"""
    script += "\n".join(functions)
    script += r"""
$rows = foreach ($usage in @(0, ($maxUsageBytes - 1), $maxUsageBytes, ($maxUsageBytes + 1))) {
    $script:testUsageBytes = [int64]$usage
    Write-State (Get-EffectiveStatus)
    $script:capturedState | ConvertFrom-Json
}
$rows | ConvertTo-Json -Depth 4 -Compress
"""
    result = subprocess.run(
        [shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    rows = json.loads(result.stdout)
    assert [row["status"] for row in rows] == ["ready", "ready", "over_limit", "over_limit"]
    assert [row["usage_ok"] for row in rows] == [True, True, False, False]
    assert [row["usage_bytes"] for row in rows] == [
        0,
        windows_worker.MAX_USAGE_BYTES - 1,
        windows_worker.MAX_USAGE_BYTES,
        windows_worker.MAX_USAGE_BYTES + 1,
    ]
