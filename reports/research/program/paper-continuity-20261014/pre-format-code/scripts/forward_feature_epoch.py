"""Explicit forward checks; never relabel a failed legacy whole-panel predicate."""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from prepare_host_forward_version import compose, sha256


def publish_forward_table(
    root: Path, table_name: str, old: Path, candidate: Path, output: Path,
    day: date, config: dict,
) -> dict:
    definition = config["tables"][table_name]
    version_root = root / config["version_directory"]
    if not version_root.resolve().is_relative_to(root.resolve()):
        raise ValueError("forward version must remain inside the private/project root")
    if day.year != config["year"]:
        raise ValueError("forward epoch year mismatch")
    old_hash = sha256(old)
    latest_path = version_root / "latest" / (table_name + ".json")
    if latest_path.exists():
        previous = json.loads(latest_path.read_text())
        if previous["version_id"] != config["version_id"] or previous["output"]["sha256"] != old_hash:
            raise ValueError("published-prefix receipt/hash mismatch")
        prefix_end = previous["suffix_end"]
    else:
        if old_hash != definition["anchor_sha256"]:
            raise ValueError("first forward update does not match the accepted anchor")
        prefix_end = definition.get("anchor_end", config["anchor_end"])
    if date.fromisoformat(prefix_end) >= day:
        raise ValueError("no new completed suffix; preserve the already published prefix")
    directory = version_root / "receipts" / day.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = directory / (table_name + ".json")
    if receipt_path.exists():
        raise ValueError("consumed forward receipt exists; inspect prior publication")
    combined = candidate.with_name(candidate.stem + ".forward.parquet")
    source_manifest = Path(config["runtime_source_manifest"])
    source = json.loads(source_manifest.read_text())
    for item in source.get("corrected_bindings", []):
        path = source_manifest.parent / item["path"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError("frozen raw context changed during feature build")
    for item in source.get("producer_dependencies", []):
        path = Path(item["path"])
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError("producer input/code changed during feature build")
    retained = version_root / "natural-candidates" / day.isoformat() / (table_name + ".parquet")
    retained.parent.mkdir(parents=True, exist_ok=True)
    if retained.exists():
        raise ValueError("prior natural candidate retained; inspect consumed attempt")
    shutil.copyfile(candidate, retained)
    result = compose(
        old, retained, combined, expected_baseline_sha256=old_hash,
        prefix_end=prefix_end, suffix_end=day.isoformat(),
        source_manifest=source_manifest, version_id=config["version_id"],
    )
    receipt_path.write_text(json.dumps(result, indent=2) + "\n")
    # Original candidate and failed/check artifacts remain dereferenceable.
    combined.replace(output)
    result["output"]["path"] = str(output)
    receipt_path.write_text(json.dumps(result, indent=2) + "\n")
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = latest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(latest_path)
    return result
