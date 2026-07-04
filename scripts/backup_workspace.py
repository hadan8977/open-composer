from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_BACKUP_ROOT = Path("/root/codex-test/open-composer-backups")


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up Open Composer git refs and artifacts.")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--verify", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    backup_root = args.backup_root.resolve()
    if args.verify is not None:
        verify_backup(args.verify.resolve(), repo_root=repo_root)
        print(f"backup verified: {args.verify}")
        return

    manifest_path = create_backup(repo_root=repo_root, backup_root=backup_root)
    print(f"backup manifest: {manifest_path}")


def create_backup(*, repo_root: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    bundle_path = backup_root / f"oc-git-{stamp}.bundle"
    artifact_path = backup_root / f"oc-artifacts-{stamp}.tar.gz"
    manifest_path = backup_root / f"oc-backup-manifest-{stamp}.json"

    _run(["git", "bundle", "create", str(bundle_path), "--all"], cwd=repo_root)
    _write_artifact_tar(repo_root, artifact_path)
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repo_root": str(repo_root),
        "head": _git_output(["git", "rev-parse", "HEAD"], cwd=repo_root),
        "branches": _git_refs(repo_root),
        "artifacts": [
            _artifact_payload("git_bundle", bundle_path),
            _artifact_payload("research_artifacts_tar", artifact_path),
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def verify_backup(manifest_path: Path, *, repo_root: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    bundle_paths: list[Path] = []
    for artifact in artifacts:
        path = Path(str(artifact["path"]))
        if not path.exists():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        digest = _sha256(path)
        if int(artifact["bytes"]) != size:
            raise ValueError(f"size mismatch for {path}: {size} != {artifact['bytes']}")
        if str(artifact["sha256"]) != digest:
            raise ValueError(f"sha256 mismatch for {path}: {digest} != {artifact['sha256']}")
        if artifact.get("kind") == "git_bundle":
            bundle_paths.append(path)
    for bundle_path in bundle_paths:
        _run(["git", "bundle", "verify", str(bundle_path)], cwd=repo_root)


def _write_artifact_tar(repo_root: Path, artifact_path: Path) -> None:
    paths = [
        repo_root / "data" / "research" / "longbridge_adjusted_daily",
        repo_root / "reports" / "research",
    ]
    with tarfile.open(artifact_path, "w:gz") as tar:
        for path in paths:
            if path.exists():
                tar.add(path, arcname=path.relative_to(repo_root).as_posix(), recursive=True)


def _git_refs(repo_root: Path) -> list[dict[str, str]]:
    raw = _git_output(
        ["git", "for-each-ref", "--format=%(refname)|%(objectname)|%(upstream:short)"],
        cwd=repo_root,
    )
    refs: list[dict[str, str]] = []
    for line in raw.splitlines():
        name, object_name, upstream = line.split("|", maxsplit=2)
        refs.append({"ref": name, "object": object_name, "upstream": upstream})
    return refs


def _artifact_payload(kind: str, path: Path) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(args: list[str], *, cwd: Path) -> str:
    return _run(args, cwd=cwd).stdout.strip()


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


if __name__ == "__main__":
    main()
