"""Hash-bound recovery of the existing single-file publication protocol."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from prepare_host_forward_version import sha256


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _head_hash(path: Path) -> str | None:
    return sha256(path) if path.exists() else None


def atomic_restore(baseline: Path, output: Path, expected_sha256: str | None = None) -> None:
    """Restore through a new inode; retained hardlinks must keep failed bytes."""
    expected = expected_sha256 or sha256(baseline)
    if sha256(baseline) != expected:
        raise ValueError("restore baseline changed")
    space = os.statvfs(output.parent)
    if space.f_bavail * space.f_frsize < baseline.stat().st_size + 512 * 1024**2:
        raise OSError("insufficient disk for atomic restore plus service reserve")
    fd, name = tempfile.mkstemp(prefix=output.name + ".restore-", dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    shutil.copy2(baseline, temporary)
    if sha256(temporary) != expected or sha256(baseline) != expected:
        raise ValueError("restore copy/baseline changed; temporary retained")
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    temporary.replace(output)


def finish_transaction(journal: Path) -> dict:
    value = json.loads(journal.read_text())
    if value["status"] == "committed":
        return value["result"]
    output, head = Path(value["output"]), Path(value["head"])
    old, candidate = Path(value["baseline"]), Path(value["candidate"])
    if sha256(old) != value["old_sha256"] or sha256(candidate) != value["candidate_sha256"]:
        raise ValueError("publication recovery baseline/candidate changed")
    if sha256(Path(value["source_manifest"])) != value["source_manifest_sha256"]:
        raise ValueError("publication recovery source manifest changed")
    result = value["result"]
    current = sha256(output) if output.exists() else None
    head_sha = _head_hash(head)
    already = (
        head.exists()
        and json.loads(head.read_text()).get("output", {}).get("sha256")
        == result["output"]["sha256"]
    )
    if head_sha != value["previous_head_sha256"] and not already:
        raise ValueError("publication recovery head changed independently")
    if current == value["old_sha256"] and not already:
        # No replacement occurred; retain this attempt and allow a new identity.
        value["status"] = "rolled_back"
        atomic_json(journal, value)
        return result
    recorded_inplace = value.get("output_was_candidate_inode")
    if recorded_inplace is None:
        # A v2 prepared journal also has exact candidate witnesses. Recognize
        # that legacy cut point only while its original hardlink still exists.
        recorded_inplace = output.exists() and os.path.samefile(output, candidate)
    if (
        not already
        and recorded_inplace
        and current == value["candidate_sha256"]
        and value.get("output_before_sha256", current) == current
    ):
        atomic_restore(old, output, value["old_sha256"])
        if sha256(candidate) != value["candidate_sha256"]:
            raise ValueError("retained natural candidate changed during rollback")
        value["status"] = "rolled_back"
        value["recovered_from_recorded_natural_output"] = True
        atomic_json(journal, value)
        return result
    if current != result["output"]["sha256"]:
        raise ValueError("publication recovery output matches neither accepted version")
    atomic_json(head, result)
    atomic_json(Path(value["receipt"]), result)
    value["status"] = "committed"
    value["recovered_from_matching_output"] = True
    atomic_json(journal, value)
    return result


def recover_pending(version_root: Path) -> None:
    for journal in sorted((version_root / "transactions").glob("*.json")):
        if json.loads(journal.read_text())["status"] == "prepared":
            finish_transaction(journal)


def commit_output(
    combined: Path,
    output: Path,
    old: Path,
    candidate: Path,
    source_manifest: Path,
    latest: Path,
    receipt: Path,
    journal: Path,
    result: dict,
) -> dict:
    value = {
        "status": "prepared",
        "output": str(output),
        "baseline": str(old),
        "old_sha256": sha256(old),
        "candidate": str(candidate),
        "candidate_sha256": sha256(candidate),
        "output_before_sha256": sha256(output) if output.exists() else None,
        "output_was_candidate_inode": output.exists() and os.path.samefile(output, candidate),
        "head": str(latest),
        "previous_head_sha256": _head_hash(latest),
        "receipt": str(receipt),
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": sha256(source_manifest),
        "result": result,
    }
    atomic_json(journal, value)
    combined.replace(output)
    # A crash/OSError here leaves a durable prepared journal with exact witnesses.
    return finish_transaction(journal)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Recover exact matching retained publication attempts; "
            "acquire existing refresh+book locks first"
        )
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--version-directory", default="data/features/_forward_v1")
    args = parser.parse_args()
    root = args.root.resolve()
    directory = (root / args.version_directory).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("recovery directory outside the accepted root")
    recover_pending(directory)
    from forward_refresh_io import recover_metadata

    recover_metadata(directory)
    print(
        json.dumps(
            {"status": "matching_transactions_reconciled", "version_directory": str(directory)}
        )
    )
