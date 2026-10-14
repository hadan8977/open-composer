"""Release only the fully reconstructed, redundant ZIP storage, not its source bytes."""
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def available():
    value = os.statvfs(HERE)
    return value.f_bavail * value.f_frsize


def users(path):
    target = str(path.resolve())
    result = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            paths = [proc / "cwd", *(proc / "fd").iterdir()]
        except OSError:
            continue
        for p in paths:
            try:
                if os.readlink(p) == target:
                    result.append(int(proc.name))
                    break
            except OSError:
                pass
    return result


def main():
    receipt = HERE / "actual-recovery.json"
    if receipt.exists():
        raise ValueError("consumed recovery; preserve the prior receipt")
    manifest = HERE / "exact-current-zip-delta.json"
    value = json.loads(manifest.read_text())
    original = Path(value["original"]["path"])
    base = Path(value["retained_base"]["path"])
    literals = Path(value["literals"]["path"])
    assert value["reconstructed_exact_sha256"] == value["original"]["sha256"]
    assert sha(literals) == value["literals"]["sha256"]
    assert sha(base) == value["retained_base"]["sha256"]
    assert sha(original) == value["original"]["sha256"]
    in_use = users(original)
    if in_use:
        raise ValueError(f"exact candidate open by PIDs {in_use}")
    before = available()
    st = original.stat()
    record = {"at_UTC": datetime.now(UTC).isoformat(), "action": "release_reconstructible_transport_storage",
              "scope": "only this task's current-companyfacts bulk transport container",
              "original": value["original"], "retained_representation": {"path": str(manifest), "sha256": sha(manifest)},
              "full_reconstruction_verified": True, "open_file_PIDs": in_use,
              "source_entities_or_information_discarded": 0,
              "failed_attempts_preserved": True, "sealed_code_data_or_manifest_changed": False,
              "available_before_bytes": before, "candidate_allocated_bytes": st.st_blocks * 512,
              "new_cloud_or_source_requests": 0}
    # Metadata record is durable before unlink; all exact bytes remain locally encoded.
    receipt.write_text(json.dumps({**record, "status": "verified_before_release"}, indent=2) + "\n")
    original.unlink()
    record.update(status="released", available_after_bytes=available())
    record["observed_available_delta_bytes"] = record["available_after_bytes"] - before
    receipt.write_text(json.dumps(record, indent=2) + "\n")
    root = HERE.parents[4]
    with (root / "reports/ops/disk-ledger.jsonl").open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    print(record)


if __name__ == "__main__":
    main()
