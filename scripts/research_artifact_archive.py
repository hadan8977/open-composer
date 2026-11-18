"""Explicit cold-research archiving through the existing disk guard; never a scheduler.

Prepare is local/read-only for payloads. Execute uploads through disk_guard, verifies
remote identity/hashes, and optionally replaces frozen sources with mount links.
Catalog/legacy-scan inspect local metadata only; they never read archived payloads.
"""

from __future__ import annotations

import argparse
import csv
import fcntl
import fnmatch
import hashlib
import html
import io
import json
import os
import re
import shlex
import stat
import sys
import tarfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import disk_guard as G

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/research-archive-policy.json"
ALLOWED_ROOTS = ("reports/research/program", "reports/research/iterations")
PREFIX = "archive/open-composer/research/v1"
IDENTITY = ("device", "inode", "bytes", "mtime_ns", "nlink")


class ArchiveError(RuntimeError):
    """Fail closed while retaining the local source."""


def utc() -> str:
    return datetime.now(UTC).isoformat()


def absolute(path: str | Path) -> Path:
    p = Path(path)
    return Path(os.path.abspath(p if p.is_absolute() else ROOT / p))


def under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def no_links(path: Path) -> None:
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ArchiveError(f"Symlink or symlink ancestor: {p}")


def load_policy() -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text())
    if tuple(policy["allowed_roots"]) != ALLOWED_ROOTS:
        raise ArchiveError("Archive roots must be the two fixed research payload roots")
    if policy["archive_prefix"] != PREFIX or policy.get("expiry") is not None:
        raise ArchiveError("Immutable archive prefix and indefinite retention are required")
    if policy.get("automatic_age_deletion") or policy.get("schedules"):
        raise ArchiveError("Automatic deletion and schedules are not supported")
    return policy


def digest_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def identity(path: Path) -> dict[str, int]:
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        raise ArchiveError(f"Expected one-link regular file: {path}")
    return {
        "device": s.st_dev,
        "inode": s.st_ino,
        "bytes": s.st_size,
        "mtime_ns": s.st_mtime_ns,
        "nlink": s.st_nlink,
        "allocated_bytes": s.st_blocks * 512,
    }


def hashes(path: Path) -> dict[str, str]:
    no_links(path)
    before = identity(path)
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024**2), b""):
            sha.update(chunk)
            md5.update(chunk)
    if identity(path) != before:
        raise ArchiveError(f"File changed while hashing: {path}")
    return {"sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def snapshot(path: Path) -> dict[str, Any]:
    before = identity(path)
    result = hashes(path)
    if identity(path) != before:
        raise ArchiveError(f"File changed during preparation: {path}")
    return {"path": str(path), **before, **result}


def sensitive_name(name: str, policy: dict[str, Any]) -> bool:
    return any(
        fnmatch.fnmatch(part.lower(), pattern.lower())
        for part in Path(name).parts
        for pattern in policy["protected_path_patterns"]
    )


def validate_source(path: Path, policy: dict[str, Any]) -> None:
    no_links(path)
    roots = [ROOT / r for r in ALLOWED_ROOTS]
    if not any(under(path, root) and path != root for root in roots):
        raise ArchiveError(f"Outside fixed research roots: {path}")
    if any(under(path, absolute(p)) for p in policy["protected_roots"]):
        raise ArchiveError(f"Protected task: {path}")
    if sensitive_name(str(path.relative_to(ROOT)), policy):
        raise ArchiveError(f"Protected credential/checkpoint/paper path: {path}")
    if path.suffix.lower() not in policy["allowed_suffixes"]:
        raise ArchiveError(f"Not an approved binary payload suffix: {path}")
    identity(path)
    guard = G.load_policy()
    guard["allowed_roots"] = [str(ROOT / p) for p in ALLOWED_ROOTS]
    ok, reason = G.safe_to_delete(path, guard)
    if not ok:
        raise ArchiveError(reason)


def validate_evidence(path: Path) -> None:
    no_links(path)
    if not under(path, ROOT / "reports/research"):
        raise ArchiveError("Completion evidence must be local research evidence")
    identity(path)


def slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not value:
        raise ArchiveError("Empty classification component")
    return value[:100]


def remote_key(row: dict[str, Any]) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}", row["year_month"]) or not re.fullmatch(
        r"[0-9a-f]{64}", row["sha256"]
    ):
        raise ArchiveError("Invalid frozen hash/date classification")
    category = "/".join(slug(p) for p in row["category"].split("/") if p)
    return (
        f"{PREFIX}/{category}/{slug(row['task_id'])}/{row['year_month']}/"
        f"{row['sha256']}/{Path(row['path']).name}"
    )


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_text(path: Path, text: str) -> None:
    no_links(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    no_links(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.pending")
    try:
        with temporary.open("x", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def save(path: Path, obj: Any) -> None:
    atomic_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def catalog_root(policy: dict[str, Any]) -> Path:
    path = absolute(policy["catalog_root"])
    if path != ROOT / "reports/research/archive":
        raise ArchiveError("Catalog must remain in reports/research/archive")
    no_links(path)
    return path


@contextmanager
def global_lock():
    G.LOCK_PATH.touch(exist_ok=True)
    with G.LOCK_PATH.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ArchiveError("The existing disk guard lock is busy; retry later") from exc
        yield


def event(policy: dict[str, Any], action: str, **values: Any) -> dict[str, Any]:
    row = {"at_utc": utc(), "action": action, **values}
    path = catalog_root(policy) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    no_links(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    fsync_dir(path.parent)
    G.ledger({"action": f"research_archive_{action}", **values})
    with G.LEDGER_PATH.open("rb") as f:
        os.fsync(f.fileno())
    return row


def read_events(policy: dict[str, Any]) -> list[dict[str, Any]]:
    path = catalog_root(policy) / "events.jsonl"
    no_links(path)
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ArchiveError(f"Damaged event log at line {number}; retain sources") from exc
    return rows


def prepare(selection_path: Path, policy: dict[str, Any]) -> Path:
    no_links(selection_path)
    selection_raw = selection_path.read_bytes()
    selection = json.loads(selection_raw)
    groups = selection.get("recommended_first_batch", [])
    if not groups:
        raise ArchiveError("Selection has no recommended_first_batch")
    rows = []
    seen = set()
    for group in groups:
        if not group.get("completion", "").startswith("accept"):
            raise ArchiveError("Cold selection needs an explicit accepted completion outcome")
        if not group.get("summary_zh") or not group.get("authoritative_evidence"):
            raise ArchiveError("Chinese task summary and local completion evidence are required")
        evidence = []
        for name in group["authoritative_evidence"]:
            proof = absolute(name)
            validate_evidence(proof)
            evidence.append(snapshot(proof))
        for source in group["files"]:
            path = absolute(source["path"])
            validate_source(path, policy)
            if path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path) as archive:
                    credential_patterns = (
                        ".env*",
                        "*credential*",
                        "*secret*",
                        "*token*",
                        "*.pem",
                        "*.key",
                    )
                    if any(
                        fnmatch.fnmatch(part.lower(), pattern)
                        for name in archive.namelist()
                        for part in Path(name).parts
                        for pattern in credential_patterns
                    ):
                        raise ArchiveError("Credential-looking ZIP member; retain package")
            if str(path) in seen:
                raise ArchiveError(f"Duplicate selection: {path}")
            seen.add(str(path))
            frozen = snapshot(path)
            for key in ("inode", "bytes", "mtime_ns"):
                if key in source and frozen[key] != source[key]:
                    raise ArchiveError(f"Selection metadata changed ({key}): {path}")
            scope = Path(os.path.commonpath([str(path.parent), *[p["path"] for p in evidence]]))
            if not under(scope, ROOT / "reports/research"):
                raise ArchiveError("Activity scope escaped research")
            if G.in_use(scope):
                raise ArchiveError(f"Task scope is active: {scope}")
            row = {
                **frozen,
                "item_id": digest_bytes((str(path) + frozen["sha256"]).encode())[:24],
                "group_id": group["id"],
                "category": group["category"],
                "task_id": group.get("task_id", group["id"]),
                "task_outcome": group["completion"],
                "summary_zh": group["summary_zh"],
                "storage_tier": "cold",
                "year_month": datetime.fromtimestamp(frozen["mtime_ns"] / 1e9, UTC).strftime(
                    "%Y-%m"
                ),
                "completion_evidence": evidence,
                "activity_scope": str(scope),
                "expiry": None,
            }
            row["remote"] = remote_key(row)
            row["restore_download_command"] = [
                "gdrive",
                "download",
                row["remote"],
                "--local",
                str(path) + ".restore-local",
            ]
            rows.append(row)
    body = {
        "schema_version": 1,
        "selection_path": str(selection_path),
        "selection_sha256": digest_bytes(selection_raw),
        "policy_sha256": digest_bytes(POLICY_PATH.read_bytes()),
        "files": rows,
    }
    batch_id = digest_bytes(json.dumps(body, sort_keys=True).encode())[:24]
    batch = {"batch_id": batch_id, "prepared_at_utc": utc(), **body}
    target = catalog_root(policy) / "batches" / f"{batch_id}.json"
    if target.exists():
        old = json.loads(target.read_text())
        if {k: v for k, v in old.items() if k != "prepared_at_utc"} != {
            k: v for k, v in batch.items() if k != "prepared_at_utc"
        }:
            raise ArchiveError("Immutable batch collision")
    else:
        save(target, batch)
    event(policy, "prepared", batch_id=batch_id, batch_path=str(target), files=len(rows))
    return target


def check_evidence(row: dict[str, Any]) -> None:
    for evidence in row["completion_evidence"]:
        path = Path(evidence["path"])
        validate_evidence(path)
        if snapshot(path) != evidence:
            raise ArchiveError(f"Frozen completion evidence changed: {path}")


def check_source(row: dict[str, Any], policy: dict[str, Any], *, hash_content: bool) -> None:
    path = Path(row["path"])
    validate_source(path, policy)
    current = identity(path)
    if any(current[key] != row[key] for key in IDENTITY):
        raise ArchiveError(f"Frozen source identity changed: {path}")
    if hash_content and hashes(path) != {key: row[key] for key in ("sha256", "md5")}:
        raise ArchiveError(f"Frozen source bytes changed: {path}")
    check_evidence(row)
    if G.in_use(Path(row["activity_scope"])):
        raise ArchiveError(f"Task became active: {row['activity_scope']}")


def remote_metadata(row: dict[str, Any], drive: dict[str, Any]) -> dict[str, Any] | None:
    code, text = G.run_cmd(
        ["rclone", "lsjson", "--stat", "--hash", drive["remote_root"] + "/" + row["remote"]],
        timeout=120,
    )
    if code in (3, 4) and re.search(r"not found|doesn't exist|does not exist", text, re.I):
        return None
    if code:
        raise ArchiveError(f"Remote metadata unavailable ({code}); retain source")
    try:
        meta = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArchiveError("Invalid remote metadata; retain source") from exc
    if not isinstance(meta, dict):
        raise ArchiveError("Expected one remote object")
    known = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in meta.get("Hashes", {}).items()}
    matching = any(known.get(k) == row[k] for k in ("sha256", "md5"))
    contradictory = any(known.get(k) and known[k] != row[k] for k in ("sha256", "md5"))
    if meta.get("Size") != row["bytes"] or not meta.get("ID") or not matching or contradictory:
        raise ArchiveError("Remote hash/size/identity mismatch; immutable object not overwritten")
    return meta


def mount_available(mount: Path) -> bool:
    return mount.is_dir() and os.path.ismount(mount)


def mount_target(row: dict[str, Any], drive: dict[str, Any]) -> Path:
    mount = Path(drive["mount_root"])
    target = mount / row["remote"]
    if not mount_available(mount) or not target.is_file() or target.stat().st_size != row["bytes"]:
        raise ArchiveError("Verified object unavailable in existing mount; retain source and retry")
    return target


def release(row: dict[str, Any], policy: dict[str, Any], meta: dict[str, Any], drive: dict) -> None:
    source = Path(row["path"])
    target = mount_target(row, drive)
    check_source(row, policy, hash_content=True)
    # Durable original-path/hash/remote-ID recovery record precedes replacing any source.
    event(policy, "release_intent", item=row, remote_metadata=meta, target=str(target))
    temporary = source.with_name(f".{source.name}.{uuid.uuid4().hex}.archive-link")
    try:
        temporary.symlink_to(target)
        # Final identity/proof/activity check after preparing the link; no unlink/copy gap.
        check_source(row, policy, hash_content=False)
        os.replace(temporary, source)
        fsync_dir(source.parent)
    finally:
        temporary.unlink(missing_ok=True)
    event(policy, "released", item=row, remote_metadata=meta, target=str(target))


def load_batch(
    path: Path, policy: dict[str, Any], *, current_policy_required: bool = True
) -> dict[str, Any]:
    no_links(path)
    if not under(path, catalog_root(policy) / "batches"):
        raise ArchiveError("Execute only an immutable prepared batch from the catalog")
    batch = json.loads(path.read_text())
    body = {k: v for k, v in batch.items() if k not in ("batch_id", "prepared_at_utc")}
    if digest_bytes(json.dumps(body, sort_keys=True).encode())[:24] != batch.get("batch_id"):
        raise ArchiveError("Prepared batch has been edited")
    if current_policy_required and batch["policy_sha256"] != digest_bytes(POLICY_PATH.read_bytes()):
        raise ArchiveError("Policy changed; prepare and review a new batch")
    for row in batch["files"]:
        if row["remote"] != remote_key(row) or row["storage_tier"] != "cold":
            raise ArchiveError("Invalid frozen remote key or tier")
    return batch


def execute(batch_path: Path, policy: dict[str, Any], *, release_local: bool = False) -> dict:
    batch = load_batch(batch_path, policy)
    drive_policy = G.load_policy()
    drive = drive_policy["drive"]
    prior = read_events(policy)
    results = []
    for row in batch["files"]:
        source = Path(row["path"])
        try:
            no_links(source.parent)
            if source.is_symlink():
                intents = [
                    e
                    for e in prior
                    if e["action"] in ("release_intent", "released")
                    and e.get("item", {}).get("item_id") == row["item_id"]
                ]
                target = mount_target(row, drive)
                if not intents or os.readlink(source) != str(target):
                    raise ArchiveError("Unexpected source symlink; do not follow or replace")
                check_evidence(row)
                meta = remote_metadata(row, drive)
                if meta is None or meta["ID"] != intents[-1]["remote_metadata"]["ID"]:
                    raise ArchiveError("Previously released remote identity changed")
                event(policy, "released", item=row, remote_metadata=meta, target=str(target))
                results.append({"item_id": row["item_id"], "status": "already_released"})
                continue
            check_source(row, policy, hash_content=True)
            meta = remote_metadata(row, drive)
            if meta is None:
                ok, note = G.upload_and_verify(
                    G.Item(kind="backup", path=source, remote=row["remote"], verify="hash"),
                    drive_policy,
                    False,
                )
                if not ok:
                    raise ArchiveError(f"Native upload verification failed: {note}")
                meta = remote_metadata(row, drive)
                if meta is None:
                    raise ArchiveError("Uploaded object not visible; retain source")
            check_source(row, policy, hash_content=True)
            event(policy, "verified_local_retained", item=row, remote_metadata=meta)
            if release_local:
                release(row, policy, meta, drive)
            results.append(
                {
                    "item_id": row["item_id"],
                    "status": "released" if release_local else "verified_local_retained",
                }
            )
        except (ArchiveError, OSError, ValueError) as exc:
            status = "retained_retryable"
            if source.is_symlink() and os.readlink(source) == str(
                Path(drive["mount_root"]) / row["remote"]
            ):
                status = "release_receipt_pending"
            event(policy, status, item=row, error=str(exc))
            results.append({"item_id": row["item_id"], "status": status, "error": str(exc)})
    catalog(policy)
    return {"batch_id": batch["batch_id"], "files": results}


def local_metadata_entries(root: Path, excluded_directories: frozenset[str] = frozenset()):
    """Yield non-directory entries without dereferencing links during classification."""
    pending = [root]
    while pending:
        directory = pending.pop()
        no_links(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in excluded_directories:
                        pending.append(path)
                    continue
                yield path, entry.stat(follow_symlinks=False)


def legacy_scan(policy: dict[str, Any]) -> dict[str, Any]:
    """lstat/readlink only: never stat, open, or walk any archived remote target."""
    managed_paths = {
        row["path"]
        for batch_path in (catalog_root(policy) / "batches").glob("*.json")
        for row in load_batch(batch_path, policy, current_policy_required=False)["files"]
    }
    mount = Path(G.load_policy()["drive"]["mount_root"])
    prefix = mount / "archive/open-composer"
    rows = []
    for path, metadata in local_metadata_entries(ROOT / "reports/research"):
        if not stat.S_ISLNK(metadata.st_mode) or str(path) in managed_paths:
            continue
        raw = os.readlink(path)
        target = Path(os.path.normpath(raw if os.path.isabs(raw) else path.parent / raw))
        if not under(target, prefix):
            continue
        relative = path.relative_to(ROOT / "reports/research")
        depth = 3 if len(relative.parts) > 3 and relative.parts[1].startswith("day-goal-") else 2
        task = "/".join(relative.parts[:depth])
        rows.append(
            {
                "original_path": str(path),
                "remote": target.relative_to(mount).as_posix(),
                "task_group": task,
                "verification": "historical_link_only_not_newly_verified",
                "expiry": None,
            }
        )
    # Prior ledger metadata is evidence, not a claim that old objects were reverified now.
    receipts: dict[tuple[str, str], dict] = {}
    if G.LEDGER_PATH.exists():
        with G.LEDGER_PATH.open() as f:
            for line in f:
                try:
                    old = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if old.get("path") and old.get("remote"):
                    receipts[(old["path"], old["remote"])] = {
                        k: old[k]
                        for k in ("ts", "action", "remote_id", "sha256", "bytes")
                        if k in old
                    }
    for row in rows:
        receipt = receipts.get((row["original_path"], row["remote"]))
        if receipt:
            row["historical_receipt"] = receipt
            row["verification"] = "historical_link_and_receipt_not_newly_verified"
    result = {"generated_at_utc": utc(), "remote_payload_reads": 0, "files": rows}
    save(catalog_root(policy) / "legacy-catalog.json", result)
    return result


def backup_catalog(policy: dict[str, Any]) -> dict[str, Any]:
    """Copy-only metadata snapshot through the existing uploader; never release it."""
    catalog(policy)
    root = catalog_root(policy)
    directory = root / "_snapshots"
    no_links(directory)
    directory.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    package = directory / f"catalog-{stamp}.tar.gz"
    frozen = []
    # Only this operator's metadata, never source payloads or recursive old snapshots.
    with tarfile.open(package, "x:gz") as archive:
        for path, metadata in local_metadata_entries(root, frozenset({"_snapshots"})):
            if not stat.S_ISREG(metadata.st_mode) or path.suffix not in (
                ".json",
                ".jsonl",
                ".csv",
                ".html",
                ".md",
            ):
                continue
            no_links(path)
            proof = snapshot(path)
            archive.add(path, arcname=str(path.relative_to(root)), recursive=False)
            if snapshot(path) != proof:
                raise ArchiveError("Catalog changed during metadata snapshot; retry")
            frozen.append(proof)
    with package.open("rb") as f:
        os.fsync(f.fileno())
    row = snapshot(package)
    row["remote"] = f"{PREFIX}/_catalog/{stamp}/{row['sha256']}/{package.name}"
    drive_policy = G.load_policy()
    meta = remote_metadata(row, drive_policy["drive"])
    if meta is None:
        ok, note = G.upload_and_verify(
            G.Item(kind="backup", path=package, remote=row["remote"], verify="hash"),
            drive_policy,
            False,
        )
        if not ok:
            raise ArchiveError(
                f"Metadata snapshot verification failed; local snapshot retained: {note}"
            )
        meta = remote_metadata(row, drive_policy["drive"])
    if meta is None or hashes(package) != {key: row[key] for key in ("sha256", "md5")}:
        raise ArchiveError("Metadata snapshot verification incomplete; local snapshot retained")
    receipt = {
        "at_utc": utc(),
        "local_snapshot": str(package),
        "remote": row["remote"],
        "remote_id": meta["ID"],
        "bytes": row["bytes"],
        "sha256": row["sha256"],
        "md5": row["md5"],
        "metadata_files": len(frozen),
        "expiry": None,
        "mode": "copy_only_no_local_or_remote_deletion",
        "restore_download_command": [
            "gdrive",
            "download",
            row["remote"],
            "--local",
            str(package) + ".restore-local",
        ],
    }
    save(package.with_suffix(".receipt.json"), receipt)
    save(root / "catalog-backup-latest.json", receipt)
    event(policy, "catalog_backup_verified", **receipt)
    return receipt


def catalog(policy: dict[str, Any]) -> dict[str, Any]:
    root = catalog_root(policy)
    latest: dict[str, dict] = {}
    for path in sorted((root / "batches").glob("*.json")):
        batch = load_batch(path, policy, current_policy_required=False)
        for row in batch["files"]:
            latest[row["item_id"]] = {
                "action": "prepared",
                "at_utc": batch["prepared_at_utc"],
                "item": row,
            }
    for entry in read_events(policy):
        if "item" in entry:
            old = latest.get(entry["item"]["item_id"], {})
            if "remote_metadata" not in entry and "remote_metadata" in old:
                entry = {**entry, "remote_metadata": old["remote_metadata"]}
            latest[entry["item"]["item_id"]] = entry
    rows = []
    for e in latest.values():
        row = {**e["item"], "status": e["action"], "updated_at_utc": e["at_utc"]}
        row["remote_id"] = e.get("remote_metadata", {}).get("ID")
        row["verification"] = "remote_hash_size_id_verified" if row["remote_id"] else "pending"
        if e["action"] in ("retained_retryable", "release_receipt_pending") and row["remote_id"]:
            row["verification"] = "prior_verification_retained_retry_pending"
        if e.get("error"):
            row["last_error"] = e["error"]
        rows.append(row)
    legacy_path = root / "legacy-catalog.json"
    no_links(legacy_path)
    legacy = json.loads(legacy_path.read_text()) if legacy_path.exists() else {"files": []}
    result = {
        "schema_version": 1,
        "generated_at_utc": utc(),
        "expiry": None,
        "remote_retention": "indefinite",
        "files": rows,
        "legacy_catalog": str(legacy_path),
        "legacy_link_count": len(legacy["files"]),
        "legacy_verification": "historical metadata only; not newly reverified",
    }
    save(root / "catalog.json", result)
    fields = [
        "item_id",
        "task_id",
        "category",
        "storage_tier",
        "status",
        "bytes",
        "path",
        "remote",
        "remote_id",
        "sha256",
        "summary_zh",
        "expiry",
    ]
    out = io.StringIO()
    writer = csv.DictWriter(out, fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(root / "catalog.csv", out.getvalue())
    table_rows = []
    labels = {
        "released": "已校验并释放本地空间",
        "verified_local_retained": "已校验，仍保留本地文件",
        "prepared": "已选定，等待上传",
        "retained_retryable": "待处理，保留本地文件",
        "release_receipt_pending": "链接已替换，待补齐完成记录",
    }
    for row in rows:
        proof = "".join(
            f"<dt>{html.escape(label)}</dt><dd><code>{html.escape(str(value))}</code></dd>"
            for label, value in (
                ("原路径", row["path"]),
                ("云盘位置", row["remote"]),
                ("远端对象 ID", row["remote_id"]),
                ("SHA-256", row["sha256"]),
                ("恢复到旁路文件", shlex.join(row["restore_download_command"])),
            )
        )
        table_rows.append(
            "<tr><td>"
            f'<a href="tasks/{slug(row["task_id"])}/summary.md">'
            f"{html.escape(row['task_id'])}</a><br><small>{html.escape(row['category'])}</small>"
            f"</td><td>{html.escape(row['summary_zh'])}</td>"
            f"<td>{row['bytes'] / 1024**2:.1f} MiB</td>"
            f"<td>{html.escape(labels.get(row['status'], row['status']))}</td>"
            f"<td><details><summary>位置、校验与恢复</summary><dl>{proof}</dl></details></td></tr>"
        )
    atomic_text(
        root / "catalog.html",
        "<!doctype html><meta charset='utf-8'>"
        "<title>研究归档索引</title><style>body{font:15px/1.6 sans-serif;margin:24px;color:#233044}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #dce1e8;padding:12px;"
        "vertical-align:top;word-break:break-word}th{background:#eef3f8;text-align:left}"
        "small{color:#596579}input{padding:10px;width:min(90%,700px);margin:12px 0}"
        "dd{margin:0 0 12px}dt{font-weight:bold}a{color:#176a99}summary{cursor:pointer}</style>"
        "<h1>研究归档索引</h1><p>长期保留，无自动到期清理；保留原研究结论与试验暴露。</p>"
        '<p><a href="README.zh.md">管理说明</a> · <a href="catalog.csv">下载表格</a> · '
        '<a href="legacy-task-summaries.json">历史任务索引</a> · '
        '<a href="legacy-research-outcomes.html">历史研究结论简述</a></p>'
        f"<p>本工具管理 {len(rows)} 个文件；另登记 {len(legacy['files'])} 个历史链接。"
        "历史链接只登记原有证据，未重新读取或校验远端大文件。</p>"
        "<input placeholder='搜索任务、路径、分类或结论' oninput=\"for(const r of "
        "document.querySelectorAll('tbody tr'))r.hidden=!r.textContent.toLowerCase()."
        'includes(this.value.toLowerCase())"><table><thead><tr><th>任务与分类</th>'
        "<th>结论与范围</th><th>文件大小</th><th>状态</th><th>恢复信息</th></tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table>",
    )
    tasks: dict[str, list[dict]] = {}
    for row in rows:
        tasks.setdefault(row["task_id"], []).append(row)
    for task, task_rows in tasks.items():
        lines = [
            f"# {task}\n",
            task_rows[0]["summary_zh"],
            "\n实际任务结论：" + task_rows[0]["task_outcome"],
            "\n远端保留期：永久；无自动删除。\n",
        ]
        for row in task_rows:
            lines.extend(
                [
                    f"- 原路径：`{row['path']}`",
                    f"  状态：{row['status']}",
                    f"  Drive：`{row['remote']}`（ID：{row['remote_id']}）",
                    f"  SHA-256：`{row['sha256']}`",
                    "  恢复到旁路文件：`" + shlex.join(row["restore_download_command"]) + "`",
                ]
            )
        lines.append(
            "\n恢复后核对 SHA-256、容量和当前依赖，再用本地文件替换原挂载链接；"
            "禁止直接写入挂载链接。详见 docs/research-artifact-archive.md。\n"
        )
        atomic_text(root / "tasks" / slug(task) / "summary.md", "\n".join(lines))
    legacy_groups: dict[str, list[dict]] = {}
    for row in legacy["files"]:
        legacy_groups.setdefault(row["task_group"], []).append(row)
    save(
        root / "legacy-task-summaries.json",
        [
            {
                "task_group": k,
                "archived_links": len(v),
                "summary_zh": "历史归档链接组；保留原目录分类。此索引只读取本地链接元数据，"
                "不补造科学结论，也不表示远端内容已重新验证。",
                "original_paths": [r["original_path"] for r in v],
            }
            for k, v in sorted(legacy_groups.items())
        ],
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="Freeze local selection; no upload or payload deletion")
    p.add_argument("--selection", required=True, type=Path)
    p = sub.add_parser("execute", help="Upload/verify; --release also replaces local source")
    p.add_argument("--batch", required=True, type=Path)
    p.add_argument("--release", action="store_true")
    sub.add_parser("catalog", help="Rebuild local searchable catalog without remote reads")
    sub.add_parser("legacy-scan", help="Index local historical archive links without following")
    sub.add_parser(
        "backup-catalog", help="Copy-only metadata snapshot with native Drive verification"
    )
    args = parser.parse_args(argv)
    try:
        policy = load_policy()
        with global_lock():
            if args.command == "prepare":
                result: Any = {"batch_path": str(prepare(absolute(args.selection), policy))}
            elif args.command == "execute":
                result = execute(absolute(args.batch), policy, release_local=args.release)
            elif args.command == "legacy-scan":
                legacy_scan(policy)
                result = catalog(policy)
            elif args.command == "backup-catalog":
                result = backup_catalog(policy)
            else:
                result = catalog(policy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "execute" and any(
            r["status"] in ("retained_retryable", "release_receipt_pending")
            for r in result["files"]
        ):
            return 2
        return 0
    except (ArchiveError, OSError, ValueError, KeyError) as exc:
        print(f"Archive stopped; inspect the local recovery index: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
