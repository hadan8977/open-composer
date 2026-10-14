"""Compose an immutable feature prefix and a separately identified forward suffix.

This does not certify the original whole-panel invariance predicate. The
natural current-vintage candidate remains a separate restatement artifact.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import struct
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _batch_bytes(batch: pa.RecordBatch, schema: pa.Schema) -> bytes:
    # Ignore allocation padding and undefined values under nulls. Preserve all
    # valid float bits, including signed zero and NaN payloads, and row order.
    parts = [struct.pack("<Q", batch.num_rows)]
    for array, field in zip(batch.columns, schema, strict=True):
        parts.append(pc.is_null(array).to_numpy(zero_copy_only=False).tobytes())
        if pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
            for value in array.to_pylist():
                text = b"" if value is None else value.encode("utf-8")
                parts.extend((struct.pack("<Q", len(text)), text))
        else:
            values = array
            if pa.types.is_timestamp(field.type) or pa.types.is_duration(field.type):
                values = array.cast(pa.int64())
            if not (
                pa.types.is_floating(values.type)
                or pa.types.is_integer(values.type)
                or pa.types.is_boolean(values.type)
            ):
                raise ValueError(f"unsupported exact-prefix field type: {field}")
            values = pc.fill_null(
                values,
                pa.scalar(False if pa.types.is_boolean(values.type) else 0, type=values.type),
            )
            parts.append(values.to_numpy(zero_copy_only=False).tobytes())
    return b"".join(parts)


def verify_prefix(old: Path, combined: Path) -> dict:
    original = pq.ParquetFile(old)
    new = pq.ParquetFile(combined)
    if not original.schema_arrow.equals(new.schema_arrow, check_metadata=True):
        raise ValueError("prefix schema or metadata changed")
    reader = iter(new.iter_batches(batch_size=32768))
    digest = hashlib.sha256()
    checked = 0
    for batch in original.iter_batches(batch_size=32768):
        got = next(reader).slice(0, batch.num_rows)
        expected_bytes = _batch_bytes(batch, original.schema_arrow)
        if _batch_bytes(got, original.schema_arrow) != expected_bytes:
            raise ValueError(f"prefix typed/null/float/occurrence mismatch at row {checked}")
        digest.update(expected_bytes)
        checked += batch.num_rows
    if checked != original.metadata.num_rows:
        raise ValueError("prefix incomplete")
    return {"rows": checked, "typed_occurrence_sha256": digest.hexdigest()}


def compose(
    baseline: Path,
    candidate: Path,
    output: Path,
    *,
    expected_baseline_sha256: str,
    prefix_end: str,
    suffix_end: str,
    source_manifest: Path,
    version_id: str,
    key_columns: tuple[str, ...] = ("symbol", "trade_date"),
) -> dict:
    if output.exists() or output.with_suffix(".parquet.tmp").exists():
        raise ValueError("output already exists; preserve prior attempt")
    baseline_hash = sha256(baseline)
    if baseline_hash != expected_baseline_sha256:
        raise ValueError("immutable baseline binding changed")
    baseline_file = pq.ParquetFile(baseline)
    candidate_file = pq.ParquetFile(candidate)
    schema = baseline_file.schema_arrow
    if not schema.equals(candidate_file.schema_arrow):
        raise ValueError("candidate field names/types differ from accepted baseline")
    start_scalar = pa.scalar(prefix_end).cast(schema.field("trade_date").type)
    end_scalar = pa.scalar(suffix_end).cast(schema.field("trade_date").type)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    suffix_rows = 0
    suffix_keys: set[tuple] = set()
    prefix_duplicates = 0
    prefix_max = None
    with pq.ParquetWriter(temporary, schema) as writer:
        for batch in baseline_file.iter_batches(batch_size=32768):
            dates = batch.column(schema.get_field_index("trade_date"))
            if pc.any(pc.greater(dates, start_scalar)).as_py():
                raise ValueError("baseline extends past frozen prefix boundary")
            maximum = pc.max(dates).as_py()
            if maximum is not None:
                prefix_max = max(prefix_max, maximum) if prefix_max is not None else maximum
            writer.write_batch(batch)
        if prefix_max != start_scalar.as_py():
            raise ValueError("baseline maximum does not equal prefix boundary")
        for batch in candidate_file.iter_batches(batch_size=32768):
            dates = batch.column(schema.get_field_index("trade_date"))
            suffix = batch.filter(
                pc.and_(pc.greater(dates, start_scalar), pc.less_equal(dates, end_scalar))
            )
            if not suffix.num_rows:
                continue
            dates = suffix.column(schema.get_field_index("trade_date"))
            for key in zip(
                *(suffix.column(schema.get_field_index(k)).to_pylist() for k in key_columns),
                strict=True,
            ):
                # Date boundaries already prove disjointness from the prefix.
                if key in suffix_keys:
                    raise ValueError(f"suffix duplicate or prefix overlap: {key}")
                suffix_keys.add(key)
            suffix_rows += suffix.num_rows
            writer.write_batch(pa.RecordBatch.from_arrays(list(suffix.columns), schema=schema))
    if (
        not suffix_rows
        or max(key[key_columns.index("trade_date")] for key in suffix_keys) != end_scalar.as_py()
    ):
        raise ValueError("suffix does not reach required closed session")
    # Count the same exact key occurrences with projected scalar aggregates,
    # instead of retaining millions of Python string keys in memory.
    import duckdb

    con = duckdb.connect()
    con.execute("SET threads=1; SET memory_limit='240MB'; SET max_temp_directory_size='96MB'")
    fields = ",".join('"' + key + '"' for key in key_columns)
    nulls = " OR ".join('"' + key + '" IS NULL' for key in key_columns)
    invalid = con.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE " + nulls,
        [str(baseline)],
    ).fetchone()[0]
    if invalid:
        raise ValueError("baseline contains invalid null keys")
    prefix_duplicates = int(
        con.execute(
            "SELECT sum(n-1) FROM (SELECT count(*) n FROM read_parquet(?) GROUP BY " + fields + ")",
            [str(baseline)],
        ).fetchone()[0]
        or 0
    )
    con.close()
    gc.collect()
    prefix_verification = verify_prefix(baseline, temporary)
    if sha256(baseline) != baseline_hash:
        raise ValueError("baseline changed during composition")
    temporary.replace(output)
    return {
        "version_id": version_id,
        "built_at_UTC": datetime.now(UTC).isoformat(),
        "prefix_end": prefix_end,
        "suffix_end": suffix_end,
        "baseline": {"path": str(baseline), "sha256": baseline_hash},
        "natural_candidate": {"path": str(candidate), "sha256": sha256(candidate)},
        "source_manifest": {"path": str(source_manifest), "sha256": sha256(source_manifest)},
        "output": {"path": str(output), "sha256": sha256(output), "bytes": output.stat().st_size},
        "prefix_verification": prefix_verification,
        "legacy_duplicate_occurrences_preserved": prefix_duplicates,
        "suffix_rows": suffix_rows,
        "suffix_duplicate_keys": 0,
        "prefix_suffix_overlap": 0,
        "historical_availability_certified": False,
        "original_whole_panel_invariance_pass": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "candidate", "output", "source-manifest", "receipt"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("baseline-sha256", "prefix-end", "suffix-end", "version-id"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise ValueError("receipt already exists")
    receipt = compose(
        args.baseline,
        args.candidate,
        args.output,
        expected_baseline_sha256=args.baseline_sha256,
        prefix_end=args.prefix_end,
        suffix_end=args.suffix_end,
        source_manifest=args.source_manifest,
        version_id=args.version_id,
    )
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
