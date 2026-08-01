from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

CUSTODY_CONTRACT = "open_composer_external_content_addressed_custody_v1"


@dataclass(frozen=True)
class ExternalCustodyRecord:
    receipt_path: Path
    receipt_sha256: str
    bundle_path: Path
    bundle_sha256: str
    payload: dict[str, Any]


def write_external_custody_bundle(
    *,
    project_root: Path,
    custody_root: Path,
    namespace: str,
    record_kind: str,
    subject_sha256: str,
    entries: Mapping[str, bytes],
    subject: Mapping[str, Any],
) -> ExternalCustodyRecord:
    root = _external_custody_root(project_root, custody_root, create=True)
    normalized = _normalize_entries(entries)
    if not _is_sha256(subject_sha256):
        raise ValueError("custody subject_sha256 must be a lowercase SHA-256")
    if not namespace or not record_kind:
        raise ValueError("custody namespace and record_kind are required")

    bundle_bytes = _deterministic_tar(normalized)
    bundle_sha256 = hashlib.sha256(bundle_bytes).hexdigest()
    relative_dir = Path(_safe_component(namespace)) / _safe_component(record_kind) / subject_sha256
    bundle_path = root / relative_dir / "bundle.tar"
    receipt_path = root / relative_dir / "receipt.json"
    manifest = [
        {
            "path": path,
            "sha256": hashlib.sha256(contents).hexdigest(),
            "size_bytes": len(contents),
        }
        for path, contents in normalized.items()
    ]
    payload = {
        "schema_version": 1,
        "custody_contract": CUSTODY_CONTRACT,
        "namespace": namespace,
        "record_kind": record_kind,
        "subject_sha256": subject_sha256,
        "subject": _json_round_trip(dict(subject)),
        "bundle": {
            "path": bundle_path.relative_to(root).as_posix(),
            "sha256": bundle_sha256,
            "size_bytes": len(bundle_bytes),
            "format": "deterministic_ustar",
        },
        "entries": manifest,
        "entry_count": len(manifest),
        "publication_rule": "exclusive_content_addressed_write_before_local_publication",
    }
    receipt_bytes = _canonical_json_bytes(payload) + b"\n"
    _write_exclusive_or_verify(bundle_path, bundle_bytes)
    _write_exclusive_or_verify(receipt_path, receipt_bytes)
    return verify_external_custody_record(
        project_root=project_root,
        custody_root=root,
        receipt_path=receipt_path,
        expected_namespace=namespace,
        expected_record_kind=record_kind,
        expected_subject_sha256=subject_sha256,
    )


def verify_external_custody_record(
    *,
    project_root: Path,
    custody_root: Path,
    receipt_path: Path,
    expected_namespace: str,
    expected_record_kind: str,
    expected_subject_sha256: str,
) -> ExternalCustodyRecord:
    root = _external_custody_root(project_root, custody_root, create=False)
    receipt = _regular_external_file(root, receipt_path, label="custody receipt")
    raw = receipt.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("custody receipt is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("custody receipt must be a JSON object")
    if raw != _canonical_json_bytes(payload) + b"\n":
        raise ValueError("custody receipt bytes are not canonical")
    expected = {
        "schema_version": 1,
        "custody_contract": CUSTODY_CONTRACT,
        "namespace": expected_namespace,
        "record_kind": expected_record_kind,
        "subject_sha256": expected_subject_sha256,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("custody receipt identity does not match the expected subject")
    bundle = payload.get("bundle")
    if not isinstance(bundle, dict):
        raise ValueError("custody bundle binding is missing")
    bundle_path = _regular_external_file(
        root,
        root / str(bundle.get("path") or ""),
        label="custody bundle",
    )
    bundle_bytes = bundle_path.read_bytes()
    if (
        bundle.get("format") != "deterministic_ustar"
        or bundle.get("sha256") != hashlib.sha256(bundle_bytes).hexdigest()
        or bundle.get("size_bytes") != len(bundle_bytes)
    ):
        raise ValueError("custody bundle binding does not match stored bytes")
    entries = payload.get("entries")
    if not isinstance(entries, list) or payload.get("entry_count") != len(entries):
        raise ValueError("custody entry manifest is invalid")
    archive_entries = _read_deterministic_tar(bundle_bytes)
    expected_entries: dict[str, dict[str, Any]] = {}
    for binding in entries:
        if not isinstance(binding, dict):
            raise ValueError("custody entry binding is invalid")
        path = _normalize_entry_path(str(binding.get("path") or ""))
        if path in expected_entries:
            raise ValueError("custody entry manifest contains duplicate paths")
        expected_entries[path] = binding
    if set(archive_entries) != set(expected_entries):
        raise ValueError("custody archive entry inventory differs from its manifest")
    for path, contents in archive_entries.items():
        binding = expected_entries[path]
        if binding.get("sha256") != hashlib.sha256(contents).hexdigest() or binding.get(
            "size_bytes"
        ) != len(contents):
            raise ValueError(f"custody archive entry binding mismatch: {path}")
    return ExternalCustodyRecord(
        receipt_path=receipt,
        receipt_sha256=hashlib.sha256(raw).hexdigest(),
        bundle_path=bundle_path,
        bundle_sha256=hashlib.sha256(bundle_bytes).hexdigest(),
        payload=payload,
    )


def _external_custody_root(
    project_root: Path,
    custody_root: Path,
    *,
    create: bool,
) -> Path:
    if not custody_root.is_absolute():
        raise ValueError("external custody directory must be an absolute path")
    candidate = Path(os.path.abspath(custody_root))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.exists() and current.is_symlink():
            raise ValueError("external custody directory cannot traverse symlinks")
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    if not candidate.is_dir() or candidate.is_symlink():
        raise ValueError("external custody directory must be a regular directory")
    root = candidate.resolve(strict=True)
    project = project_root.resolve(strict=True)
    try:
        root.relative_to(project)
    except ValueError:
        pass
    else:
        raise ValueError("external custody directory must be outside the project worktree")
    try:
        project.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("external custody directory cannot contain the project worktree")
    return root


def _normalize_entries(entries: Mapping[str, bytes]) -> dict[str, bytes]:
    if not entries:
        raise ValueError("custody bundle requires at least one entry")
    normalized: dict[str, bytes] = {}
    for raw_path, raw_contents in entries.items():
        path = _normalize_entry_path(raw_path)
        if path in normalized:
            raise ValueError("custody bundle contains duplicate entry paths")
        if not isinstance(raw_contents, bytes):
            raise ValueError(f"custody entry must be bytes: {path}")
        normalized[path] = raw_contents
    return dict(sorted(normalized.items()))


def _normalize_entry_path(raw_path: str) -> str:
    path = PurePosixPath(raw_path)
    if not raw_path or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"invalid custody entry path: {raw_path!r}")
    return path.as_posix()


def _deterministic_tar(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path, contents in entries.items():
            info = tarfile.TarInfo(path)
            info.size = len(contents)
            info.mode = 0o400
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(contents))
    return buffer.getvalue()


def _read_deterministic_tar(contents: bytes) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(contents), mode="r:") as archive:
        for member in archive.getmembers():
            path = _normalize_entry_path(member.name)
            if not member.isfile() or member.issym() or member.islnk() or path in result:
                raise ValueError("custody archive contains an invalid entry")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError("custody archive entry cannot be read")
            result[path] = extracted.read()
    return result


def _write_exclusive_or_verify(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("custody artifact cannot be a symlink")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != contents:
            raise ValueError(
                "content-addressed custody artifact already exists with different bytes"
            ) from None
        if path.stat().st_mode & 0o222:
            raise ValueError("existing custody artifact is writable") from None
        return
    try:
        view = memoryview(contents)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("failed to write external custody artifact")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _regular_external_file(root: Path, path: Path, *, label: str) -> Path:
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} must be inside the external custody root") from exc
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    if resolved.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")
    return resolved


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def _json_round_trip(value: Any) -> Any:
    return json.loads(_canonical_json_bytes(value))


def _safe_component(value: str) -> str:
    if not value or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in value
    ):
        raise ValueError(f"invalid custody path component: {value!r}")
    return value


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
