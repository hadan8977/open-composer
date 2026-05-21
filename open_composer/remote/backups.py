from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from open_composer.config import ensure_dir
from open_composer.models.dashboard_command import DashboardCommandPlan
from open_composer.remote.schemas import remote_risk_level
from open_composer.storage import write_json


class RemoteBackupError(RuntimeError):
    pass


def create_remote_backup(
    root: Path,
    *,
    job_id: str,
    plan: DashboardCommandPlan,
    actor: str,
) -> Path:
    backup_dir = root / "reports" / "backups" / "remote" / job_id
    if backup_dir.exists():
        raise RemoteBackupError(f"backup directory already exists: {backup_dir}")
    ensure_dir(backup_dir)

    _copy_tree_if_exists(root / "strategy_specs", backup_dir / "strategy_specs")
    if plan.plan_path:
        plan_path = _resolve_workspace_path(root, plan.plan_path)
        if plan_path.exists():
            destination = backup_dir / "reports" / "dashboard" / "commands" / plan_path.name
            ensure_dir(destination.parent)
            shutil.copy2(plan_path, destination)

    red_before_paths: list[str] = []
    if remote_risk_level(plan.action) == "red":
        for binding in plan.target_strategy_bindings:
            source = _resolve_workspace_path(root, binding.source_path)
            if source.exists():
                destination = backup_dir / f"{source.stem}.before{source.suffix}"
                shutil.copy2(source, destination)
                red_before_paths.append(_relpath(destination, root))

    git_status = _git_output(root, ["git", "status", "--short"])
    git_diff = _git_output(root, ["git", "diff", "--binary"])
    git_commit = _git_output(root, ["git", "rev-parse", "HEAD"]).strip() or "unavailable"
    (backup_dir / "git-status.txt").write_text(git_status, encoding="utf-8")
    (backup_dir / "git-diff.patch").write_text(git_diff, encoding="utf-8")

    affected_paths = [
        binding.source_path for binding in plan.target_strategy_bindings if binding.source_path
    ]
    if plan.plan_path:
        affected_paths.append(plan.plan_path)
    manifest = {
        "actor": actor,
        "action": plan.action,
        "job_id": job_id,
        "command_id": plan.command_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "dirty": bool(git_status.strip()),
        "risk_level": remote_risk_level(plan.action),
        "affected_paths": sorted(dict.fromkeys(affected_paths)),
        "spec_hashes": {
            binding.source_path: binding.spec_hash for binding in plan.target_strategy_bindings
        },
        "backup_dir": _relpath(backup_dir, root),
        "red_before_paths": red_before_paths,
    }
    return write_json(backup_dir / "manifest.json", manifest)


def _copy_tree_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copytree(source, destination)


def _resolve_workspace_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise RemoteBackupError("backup source path must stay within the workspace")
    return resolved


def _git_output(root: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {exc}\n"
    output = completed.stdout or ""
    if completed.stderr:
        output += completed.stderr
    return output


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
