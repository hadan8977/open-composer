"""Snapshot the two-year raw context with only the accepted exact corrections."""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_context(root: Path, config: dict, destination: Path, year: int) -> dict:
    if config.get("year") != year or year != 2026:
        raise ValueError("this accepted forward epoch is scoped to 2026")
    if destination.exists():
        raise ValueError("source context exists; retain the prior attempt")
    destination.mkdir(parents=True)
    bindings = []
    for group in ("data/sip/daily", "data/sip-delisted/by_year"):
        for source_year in (year - 1, year):
            for source in sorted((root / group / str(source_year)).glob("*.parquet")):
                relative = source.relative_to(root)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                before = sha256(source)
                shutil.copyfile(source, target)
                if sha256(target) != before or sha256(source) != before:
                    raise ValueError(f"source changed during snapshot: {relative}")
                bindings.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": before})
    correction = config["source_corrections"]
    quarantine_manifest = root / correction["AZN_manifest"]
    if sha256(quarantine_manifest) != correction["AZN_manifest_sha256"]:
        raise ValueError("approved quarantine definition changed")
    q = json.loads(quarantine_manifest.read_text())
    source = destination / "data/sip/daily" / q["target_shard"]
    table = pq.read_table(source)
    wanted = {tuple(k) for k in q["quarantine_keys"]}
    keys = list(zip(table["symbol"].to_pylist(), [str(d)[:10] for d in table["timestamp"].to_pylist()], strict=True))
    mask = pa.array([k in wanted for k in keys])
    if sum(mask.to_pylist()) != len(wanted):
        raise ValueError("approved twenty keys do not occur exactly once")
    pq.write_table(table.filter(mask), destination / "AZN-quarantine.parquet")
    pq.write_table(table.filter(pc.invert(mask)), source)
    canonical_source = root / correction["canonical69"]
    if sha256(canonical_source) != correction["canonical69_sha256"]:
        raise ValueError("approved exact canonical observations changed")
    canonical = pq.read_table(canonical_source)
    ckeys = list(zip(canonical["symbol"].to_pylist(), canonical["timestamp"].to_pylist(), strict=True))
    if len(set(ckeys)) != len(ckeys) or len(ckeys) != 69:
        raise ValueError("canonical identity/multiplicity differs")
    for relative in correction["canonical_input_paths"]:
        target = destination / relative
        table = pq.read_table(target)
        keys = list(zip(table["symbol"].to_pylist(), table["timestamp"].to_pylist(), strict=True))
        indices = []
        for key in ckeys:
            positions = [i for i, value in enumerate(keys) if value == key]
            if len(positions) != 1:
                raise ValueError(f"canonical key multiplicity changed: {key}")
            indices.append(positions[0])
        if not table.take(pa.array(indices)).equals(canonical, check_metadata=False):
            raise ValueError("current raw fields differ from the approved exact observations")
        pq.write_table(table.filter(pa.array([k not in set(ckeys) for k in keys])), target)
    canonical_target = destination / "data/sip/daily/2026/shard-forward-worx-canonical.parquet"
    shutil.copyfile(canonical_source, canonical_target)
    result = {
        "built_at_UTC": datetime.now(UTC).isoformat(), "year": year,
        "original_bindings": bindings,
        "corrected_bindings": [{"path": p.relative_to(destination).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(destination.glob("data/*/*/*/*.parquet"))],
        "quarantine_sha256": sha256(destination / "AZN-quarantine.parquet"),
        "canonical69_references_each": 2, "source_requests": 0,
        "historical_first_visible_certified": False,
    }
    (destination / "source-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
