"""Offline, copy-only migration of the existing six-policy ledger and targets."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import ExitStack
from datetime import UTC, datetime, time
from pathlib import Path

from open_composer.paper_runtime.paths import LEGACY, RUNTIME

SERVICE = "oc-six-paper-validation.service"
REQUIRED = ("runtime-state.json", "owner-authorization.json")
POLICIES = ("BASE", "H5", "LSTM", "BASE_STATE_BUDGET", "MULTI_EQUAL", "MULTI_HIERARCHICAL")


def digest(path):
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def inventory(root):
    source = Path(root) / LEGACY
    files = [*REQUIRED, *(f"targets/{p}.json" for p in POLICIES)]
    if (source / "runtime-state.events.jsonl").exists():
        files.append("runtime-state.events.jsonl")
    result = {}
    for name in files:
        path = source / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing or noncanonical migration input: " + name)
        result[name] = digest(path)
    # Parse only; preserve the exact ledger and all IDs/positions/signals as bytes.
    state = json.loads((source / "runtime-state.json").read_text())
    if not {"books", "orders", "baseline"} <= state.keys():
        raise ValueError("unexpected six-policy state schema")
    if json.loads((source / "owner-authorization.json").read_text()).get("paper_only") is not True:
        raise ValueError("migration requires the existing paper-only authority")
    return result


def require_stopped():
    result = subprocess.run(
        ["systemctl", "show", SERVICE, "--property=ActiveState", "--value"],
        check=True,
        text=True,
        capture_output=True,
    )
    if result.stdout.strip() not in {"inactive", "failed"}:
        raise ValueError("stop the existing service and its children before applying migration")


def require_maintenance_window(now):
    now = now.astimezone(UTC)
    if time(13, 30) <= now.time().replace(tzinfo=None) < time(21):
        raise ValueError("apply migration outside 13:30–21:00 UTC")


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def migrate(root, *, apply=False, now=None, stopped_check=require_stopped):
    root = Path(root).resolve()
    source, destination = root / LEGACY, root / RUNTIME
    marker = destination / "migration.json"
    if not apply:
        return dict(
            status="plan_only", source=str(LEGACY), destination=str(RUNTIME), files=inventory(root)
        )
    require_maintenance_window(datetime.now(UTC) if now is None else now)
    stopped_check()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        # Same source lock as the live service; a second guard serializes migrations.
        for lock in [source / "runtime-state.lock", destination.parent / ".six-migration.lock"]:
            stream = stack.enter_context(lock.open("a+"))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stopped_check()
        if marker.exists():
            saved = json.loads(marker.read_text())
            if saved.get("source") != str(LEGACY) or saved.get("destination") != str(RUNTIME):
                raise ValueError("another runtime migration owns this destination")
            if any(not (destination / name).is_file() for name in saved["files"]):
                raise ValueError("migration destination is incomplete; preserve it for repair")
            return dict(status="already_migrated_no_overwrite", files=saved["files"])
        if destination.exists():
            raise ValueError("unmarked runtime destination exists; preserve it for inspection")
        files = inventory(root)
        staging = Path(tempfile.mkdtemp(prefix=".six-migration-", dir=destination.parent))
        try:
            for name, expected in files.items():
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, target)
                if digest(target) != expected:
                    raise ValueError("migration copy differs: " + name)
                with target.open("rb") as stream:
                    os.fsync(stream.fileno())
            if inventory(root) != files:
                raise ValueError("legacy state or targets changed during migration")
            saved = dict(
                schema_version=1,
                source=str(LEGACY),
                destination=str(RUNTIME),
                files=files,
                applied_at=(datetime.now(UTC) if now is None else now).isoformat(),
                source_retained=True,
                contents_rewritten=False,
            )
            with (staging / "migration.json").open("x") as stream:
                json.dump(saved, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(staging / "targets")
            sync_directory(staging)
            stopped_check()
            os.rename(staging, destination)
            sync_directory(destination.parent)
        except BaseException:
            # Retain a partial attempt as diagnostic evidence; never touch legacy files.
            raise
    return dict(status="copied_and_verified", files=files, source_retained=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
