"""Explicit forward checks; never relabel a failed legacy whole-panel predicate."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from forward_publication import commit_output
from prepare_host_forward_version import compose, sha256


def publish_forward_table(
    root: Path,
    table_name: str,
    old: Path,
    candidate: Path,
    output: Path,
    day: date,
    config: dict,
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
        if (
            previous["version_id"] != config["version_id"]
            or previous["output"]["sha256"] != old_hash
        ):
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
    attempt = table_name + "-" + datetime.now(UTC).strftime("%H%M%S%f")
    receipt_path = directory / (attempt + ".json")
    combined = directory / (attempt + ".forward.parquet")
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
        actual = Path(item.get("source_path", item["path"]))
        if sha256(actual) != item["sha256"]:
            raise ValueError("producer consumed dependency changed during feature build")
    retained = version_root / "natural-candidates" / day.isoformat() / (table_name + ".parquet")
    if retained.exists():
        retained = retained.with_name(attempt + ".parquet")
    retained.parent.mkdir(parents=True, exist_ok=True)
    if retained.exists():
        raise ValueError("prior natural candidate retained; inspect consumed attempt")
    # Retain the produced bytes without making a second physical copy. The
    # builder is finished; future writes use a fresh attempt or atomic replacement.
    os.link(candidate, retained)
    result = compose(
        old,
        retained,
        combined,
        expected_baseline_sha256=old_hash,
        prefix_end=prefix_end,
        suffix_end=day.isoformat(),
        source_manifest=source_manifest,
        version_id=config["version_id"],
        key_columns=tuple(definition.get("keys", ["symbol", "trade_date"])),
    )
    result["output"]["path"] = output.relative_to(root).as_posix()
    journal = version_root / "transactions" / (attempt + ".json")
    return commit_output(
        combined, output, old, retained, source_manifest, latest_path, receipt_path, journal, result
    )
