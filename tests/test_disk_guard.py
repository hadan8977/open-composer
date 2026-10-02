"""Safety rules of scripts/disk_guard.py, on synthetic trees only (nothing real is deleted,
no Drive or rclone call is made)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts import disk_guard as G

DAY = 86400.0


def _policy(tmp_path: Path, **extra) -> dict:
    pol = {
        "thresholds": {
            "act_pct": 80,
            "target_pct": 75,
            "emergency_pct": 90,
            "backup_max_age_days": 7,
            "tmp_max_age_days": 7,
            "report_unregistered_gb": 1.0,
        },
        "drive": {
            "remote_root": "gdrive:agent-data",
            "mount_root": "/mnt/gdrive",
            "archive_prefix": "archive/test",
        },
        "allowed_roots": [str(tmp_path / "data"), str(tmp_path / "tmp")],
        "protected": [str(tmp_path / "data/research/equity_book"), str(tmp_path / "tmp/claude-0")],
    }
    pol.update(extra)
    return pol


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every repo path of the module at ``tmp_path``."""
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "LEDGER_PATH", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(G, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(G, "QUEUE_PATH", tmp_path / "queue.md")
    (tmp_path / "queue.md").write_text("### T-HOLD x\n- status: running\n")
    return tmp_path


def _usage(monkeypatch: pytest.MonkeyPatch, pct: float) -> None:
    fake = {"total_gb": 100.0, "used_gb": pct, "free_gb": 100.0 - pct, "pct": pct}
    monkeypatch.setattr(G, "disk_usage", lambda path="/": dict(fake))


def _ledger_actions(root: Path) -> list[str]:
    path = root / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line)["action"] for line in path.read_text().splitlines()]


def _fake_drive(verified: set[str]):
    """gdrive upload always succeeds; rclone check passes only for names in ``verified``."""

    def run(cmd, env=None, timeout=0):
        if cmd[0] == "gdrive":
            return 0, "{}"
        ok = any(name in cmd[2] for name in verified)  # rclone check SRC DST ...
        return (0, "NOTICE: x: 0 differences found") if ok else (1, "ERROR: 2 differences found")

    return run


# ----------------------------------------------------------------------------- path safety
def test_safe_to_delete_allowed_root_only(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    (tmp_path / "data/x").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    assert G.safe_to_delete(tmp_path / "data/x", pol)[0]
    assert not G.safe_to_delete(tmp_path / "elsewhere", pol)[0]
    assert not G.safe_to_delete(tmp_path / "data", pol)[0]  # an allowed root itself


def test_safe_to_delete_refuses_protected_and_their_parents(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    snap = tmp_path / "data/research/equity_book"
    snap.mkdir(parents=True)
    assert not G.safe_to_delete(snap, pol)[0]
    assert not G.safe_to_delete(tmp_path / "data/research", pol)[0]


def test_safe_to_delete_never_deletes_symlinks(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    (tmp_path / "outside").mkdir()
    (tmp_path / "data").mkdir()
    link = tmp_path / "data/link"
    link.symlink_to(tmp_path / "outside")
    ok, why = G.safe_to_delete(link, pol)
    assert not ok and "symlink" in why


# ----------------------------------------------------------------------------- task holds
def test_task_status_and_hold() -> None:
    queue = (
        "### T-1 something\n- status: done（ok）\n- priority: 1\n\n"
        "### T-10 other\n- status: partial（pending review）\n\n"
        "### T-3 third\n- status: cancelled\n"
    )
    assert G.task_status("T-1", queue).startswith("done")  # not confused with T-10
    assert G.task_status("T-10", queue).startswith("partial")
    assert not G.held("T-1", queue)
    assert G.held("T-10", queue)
    assert not G.held("T-3", queue)
    assert G.held("T-9", queue)  # unknown task: hold (fail safe)
    assert not G.held(None, queue)


# ----------------------------------------------------------------------------- /tmp by age
def test_tmp_candidates_age_and_keep_patterns(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    base = tmp_path / "tmp"
    for name in ("job_a", "claude-0", "uv.lock", ".X11-unix"):
        (base / name).mkdir(parents=True)
        (base / name / "f.txt").write_text("x")
    spec = {"path": str(base), "max_age_days": 7, "keep_patterns": ["claude-*", "*.lock", ".X*"]}
    assert G.tmp_candidates(spec, pol, time.time()) == []  # just written
    later = time.time() + 10 * DAY
    assert [it.path.name for it in G.tmp_candidates(spec, pol, later)] == ["job_a"]


def test_tmp_candidates_newer_file_deep_inside_keeps_entry(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    base = tmp_path / "tmp"
    deep = base / "job/a/b"
    deep.mkdir(parents=True)
    f = deep / "out.txt"
    f.write_text("y")
    later = time.time() + 10 * DAY
    spec = {"path": str(base), "max_age_days": 7, "keep_patterns": []}
    os.utime(f, (later - 2 * DAY, later - 2 * DAY))  # written 2 days before "later"
    assert G.tmp_candidates(spec, pol, later) == []
    os.utime(f, (later - 9 * DAY, later - 9 * DAY))
    assert [it.path.name for it in G.tmp_candidates(spec, pol, later)] == ["job"]


# ----------------------------------------------------------------------------- discovery
def test_find_dirs_does_not_follow_symlinks(sandbox: Path) -> None:
    (sandbox / "data/features/daily_backup_x").mkdir(parents=True)
    (sandbox / "mount/backup-inside-mount").mkdir(parents=True)
    (sandbox / "data/sip-hist").symlink_to(sandbox / "mount")
    assert [p.name for p in G.find_dirs("data/**/*_backup_*")] == ["daily_backup_x"]
    assert G.find_dirs("data/**/backup-*") == []


def test_backup_items_expiry_and_holds(sandbox: Path) -> None:
    for name in ("backup-a", "backup-b"):
        (sandbox / f"data/live/{name}").mkdir(parents=True)
        (sandbox / f"data/live/{name}/x.parquet").write_text("x")
    pol = _policy(
        sandbox,
        backups=[
            {"path": "data/live/backup-b", "hold_task": "T-HOLD", "owner": "T-HOLD"},
            {"glob": "data/**/backup-*"},
        ],
    )
    now = {it.name: it for it in G.backup_items(pol, time.time())}
    assert set(now) == {"data/live/backup-a", "data/live/backup-b"}  # listed once each
    assert not any(it.expired for it in now.values())
    assert now["data/live/backup-b"].hold_task == "T-HOLD"
    assert now["data/live/backup-a"].remote == "archive/test/data/live/backup-a"
    later = G.backup_items(pol, time.time() + 8 * DAY)
    assert all(it.expired for it in later)


def test_warm_items_skip_recent_years_and_symlinks(sandbox: Path) -> None:
    for y in (2023, 2024, 2025, 2026):
        (sandbox / f"data/sip/minute/{y}").mkdir(parents=True)
    (sandbox / "data/sip/minute/2022").symlink_to(sandbox)
    pol = _policy(
        sandbox,
        warm=[
            {
                "path": "data/sip/minute/{year}",
                "remote": "datasets/sip/minute/{year}",
                "years_back_min": 2,
            }
        ],
    )
    items = G.warm_items(pol, year_now=2026)
    assert [it.path.name for it in items] == ["2023", "2024"]
    assert str(items[0].symlink_to) == "/mnt/gdrive/datasets/sip/minute/2023"


# ----------------------------------------------------------------------------- deletion
def test_delete_path_dry_run_then_real(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    d = tmp_path / "data/scratch_tmp"
    d.mkdir(parents=True)
    (d / "f.bin").write_bytes(b"0" * 1000)
    it = G.Item(kind="backup", path=d, name="data/scratch_tmp")
    ok, why, size = G.delete_path(it, pol, dry=True)
    assert ok and why == "dry-run" and size >= 1000 and d.exists()
    ok, why, _ = G.delete_path(it, pol, dry=False)
    assert ok and why == "deleted" and not d.exists()


def test_delete_path_refuses_when_in_use(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    d = tmp_path / "data/busy"
    d.mkdir(parents=True)
    with (d / "open.txt").open("w"):
        ok, why, _ = G.delete_path(G.Item(kind="tmp", path=d), pol, dry=False)
    assert not ok and "in use" in why and d.exists()


def test_warm_delete_leaves_symlink(tmp_path: Path) -> None:
    pol = _policy(tmp_path)
    d = tmp_path / "data/sip/minute/2023"
    d.mkdir(parents=True)
    (d / "x.parquet").write_text("x")
    it = G.Item(kind="warm", path=d, symlink_to=Path("/mnt/gdrive/datasets/sip/minute/2023"))
    assert G.delete_path(it, pol, dry=False)[0]
    assert d.is_symlink() and os.readlink(d) == "/mnt/gdrive/datasets/sip/minute/2023"


# ----------------------------------------------------------------------------- archive gate
def test_upload_failure_is_not_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(G, "run_cmd", lambda cmd, env=None, timeout=0: (1, "boom"))
    it = G.Item(kind="backup", path=tmp_path, name="x", remote="archive/x")
    ok, note = G.upload_and_verify(it, _policy(tmp_path), dry=False)
    assert not ok and "upload failed" in note


@pytest.mark.parametrize(
    ("code", "out", "expect"),
    [
        (0, "NOTICE: x: 0 differences found\nNOTICE: x: 12 matching files", True),
        (0, "NOTICE: x: 10 differences found", False),
        (0, "NOTICE: x: 3 differences found", False),
        (1, "NOTICE: x: 0 differences found", False),
        (0, "", False),
    ],
)
def test_verify_needs_exit_zero_and_exactly_zero_differences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, out: str, expect: bool
) -> None:
    calls: list[str] = []

    def fake(cmd, env=None, timeout=0):
        calls.append(cmd[0])
        return (0, "{}") if cmd[0] == "gdrive" else (code, out)

    monkeypatch.setattr(G, "run_cmd", fake)
    it = G.Item(kind="backup", path=tmp_path, name="x", remote="archive/x")
    ok, _ = G.upload_and_verify(it, _policy(tmp_path), dry=False)
    assert calls == ["gdrive", "rclone"] and ok is expect


# ----------------------------------------------------------------------------- run
def _three_backups(root: Path) -> tuple[Path, Path, Path]:
    dirs = tuple(root / f"data/live/backup-{n}" for n in ("good", "bad", "held"))
    for d in dirs:
        d.mkdir(parents=True)
        (d / "a.bin").write_bytes(b"1" * 10)
    return dirs  # type: ignore[return-value]


def _run_policy(root: Path) -> dict:
    return _policy(
        root,
        backups=[
            {"path": "data/live/backup-good", "expired": True},
            {"path": "data/live/backup-bad", "expired": True},
            {"path": "data/live/backup-held", "expired": True, "hold_task": "T-HOLD"},
        ],
    )


def test_run_deletes_only_verified_unheld_backups(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good, bad, kept = _three_backups(sandbox)
    _usage(monkeypatch, 85.0)
    monkeypatch.setattr(G, "run_cmd", _fake_drive({"backup-good"}))
    assert G.cmd_run(_run_policy(sandbox), force=False, dry=False) == 0
    assert not good.exists() and bad.exists() and kept.exists()
    assert _ledger_actions(sandbox) == ["delete_verified_backup", "archive_failed"]
    assert (sandbox / "status.json").exists()


def test_run_below_threshold_does_nothing_unless_all(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good, _, _ = _three_backups(sandbox)
    _usage(monkeypatch, 50.0)
    monkeypatch.setattr(G, "run_cmd", _fake_drive({"backup-good"}))
    assert G.cmd_run(_run_policy(sandbox), force=False, dry=False) == 0
    assert good.exists() and _ledger_actions(sandbox) == []
    assert G.cmd_run(_run_policy(sandbox), force=False, dry=False, all_items=True) == 0
    assert not good.exists()


def test_run_dry_run_changes_nothing(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dirs = _three_backups(sandbox)
    _usage(monkeypatch, 95.0)

    def never(cmd, env=None, timeout=0):
        raise AssertionError(f"dry run must not call {cmd[0]}")

    monkeypatch.setattr(G, "run_cmd", never)
    assert G.cmd_run(_run_policy(sandbox), force=True, dry=True) == 0
    assert all(d.exists() for d in dirs) and _ledger_actions(sandbox) == []


def test_upload_strategy_is_always_a_mirror(tmp_path: Path) -> None:
    small = tmp_path / "small"
    small.mkdir()
    for i in range(3):
        (small / f"{i}.txt").write_text("x")
    assert G.upload_strategy(small) == "direct-small"
    assert G.upload_strategy(tmp_path / "empty_or_missing") == "direct-small"


def test_backup_like_tmp_entries_are_archived_before_deletion(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = sandbox / "tmp"
    base.mkdir()
    for name in ("state-backup", "scratch"):
        (base / name).mkdir()
        (base / name / "f").write_text("x")
    (base / "refs.tar.gz").write_text("x")
    spec = {
        "name": "tmp-old",
        "path": str(base),
        "max_age_days": 0,
        "keep_patterns": [],
        "archive_patterns": ["*backup*", "*.tar.gz"],
    }
    pol = _policy(sandbox, caches=[spec])
    items = {it.path.name: it for it in G.tmp_candidates(spec, pol, time.time() + DAY)}
    assert items["state-backup"].remote == "archive/test/tmp/state-backup"
    assert items["refs.tar.gz"].remote == "archive/test/tmp/refs.tar.gz"
    assert items["scratch"].remote is None
    checks: list[str] = []

    def drive(cmd, env=None, timeout=0):
        if cmd[0] == "rclone":
            checks.append(cmd[3])
            ok = "state-backup" not in cmd[2]  # the directory archive fails verification
            return (0, "0 differences found") if ok else (1, "1 differences found")
        return 0, "{}"

    monkeypatch.setattr(G, "run_cmd", drive)
    monkeypatch.setattr(G, "newest_mtime", lambda p, cap=0: 0.0)  # everything is old
    _usage(monkeypatch, 85.0)
    G.cmd_run(pol, force=False, dry=False)
    assert (base / "state-backup").exists()  # unverified archive: kept
    assert not (base / "refs.tar.gz").exists() and not (base / "scratch").exists()
    # a single file is checked against its parent directory on the remote
    assert "gdrive:agent-data/archive/test/tmp" in checks
    assert "gdrive:agent-data/archive/test/tmp/state-backup" in checks


def test_daily_hygiene_keeps_small_caches(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    small = sandbox / "cache_small"
    big = sandbox / "cache_big"
    for d in (small, big):
        d.mkdir()
    sizes = {str(small): int(0.2e9), str(big): int(3e9)}
    monkeypatch.setattr(G, "du_bytes", lambda p, timeout=0: sizes.get(str(p), 0))
    ran: list[str] = []
    monkeypatch.setattr(
        G, "run_cmd", lambda cmd, env=None, timeout=0: (ran.append(cmd[0]), (0, ""))[1]
    )
    pol = _policy(
        sandbox,
        caches=[
            {"name": "small", "path": str(small), "command": ["clean-small"]},
            {"name": "big", "path": str(big), "command": ["clean-big"]},
        ],
    )
    _usage(monkeypatch, 50.0)
    G.cmd_run(pol, force=False, dry=False, all_items=True)
    assert ran == ["clean-big"]
    ran.clear()
    _usage(monkeypatch, 85.0)  # above the action threshold every cache is cleaned
    G.cmd_run(pol, force=False, dry=False)
    assert ran == ["clean-small", "clean-big"]


def test_path_matches_keeps_basename_semantics() -> None:
    assert G.path_matches("data/_duckdb_tmp", "data/**/_*_tmp")
    assert G.path_matches("data/features/_t21_tmp", "data/**/_*_tmp")
    assert not G.path_matches("data/research/equity_book/duck_tmp", "data/**/_*_tmp")
    assert G.path_matches("data/features/daily_backup_2026-09-17", "data/**/*_backup_*")
    assert not G.path_matches("other/backup-x", "data/**/backup-*")
    assert G.path_matches("data/live/backup-20261001", "data/live/backup-20261001")
    with pytest.raises(ValueError):
        G.path_matches("data/a/b", "data/**/a/b")


def test_status_checks_inside_parents_of_hot_paths(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for d in ("data/sip/minute", "data/sip/daily", "data/sip/stray", "data/loose"):
        (sandbox / d).mkdir(parents=True)
    monkeypatch.setattr(G, "du_bytes", lambda p, timeout=0: int(5e9))
    _usage(monkeypatch, 50.0)
    pol = _policy(sandbox, hot=["data/sip/minute", "data/sip/daily"])
    paths = {u["path"] for u in G.cmd_status(pol, write=False)["unregistered_large"]}
    assert paths == {"data/sip/stray", "data/loose"}
