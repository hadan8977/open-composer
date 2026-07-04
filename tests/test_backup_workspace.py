from __future__ import annotations

from pathlib import Path

from scripts.backup_workspace import create_backup, verify_backup


def test_backup_workspace_bundle_and_verify_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    backup_root = tmp_path / "backups"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.name", "Open Composer Test"], repo)
    _git(["config", "user.email", "test@example.invalid"], repo)
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    data_dir = repo / "data" / "research" / "longbridge_adjusted_daily"
    report_dir = repo / "reports" / "research"
    data_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    (data_dir / "qqq_daily_longbridge_adjusted.csv").write_text(
        "timestamp,open,high,low,close,volume\n2026-01-01,1,1,1,1,1\n",
        encoding="utf-8",
    )
    (report_dir / "control.md").write_text("# control\n", encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-m", "fixture"], repo)

    manifest = create_backup(repo_root=repo, backup_root=backup_root)

    assert manifest.exists()
    verify_backup(manifest, repo_root=repo)
    assert list(backup_root.glob("oc-git-*.bundle"))
    assert list(backup_root.glob("oc-artifacts-*.tar.gz"))


def _git(args: list[str], cwd: Path) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)
