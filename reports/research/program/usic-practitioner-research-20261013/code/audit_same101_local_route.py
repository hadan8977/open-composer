"""Read only frozen cohort symbol/time columns; retain file-level audit checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
import resource
import struct
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from datetime import time as clocktime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from open_composer.market_sessions import us_equity_session_close, us_equity_session_dates

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
ROUTE = BASE / "revisions/v3-finite-qqq/full-cohort-route"
OUT = ROUTE / "decisive-local-route-audit"
NY = ZoneInfo("America/New_York")
MINUTE = 60_000_000_000


def bind(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def save(path, obj):
    assert not path.exists(), "preserve_existing_audit_evidence"
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def main():
    assert os.sched_getaffinity(0) == {0}
    resource.setrlimit(resource.RLIMIT_CPU, (900, 901))
    started_cpu = time.process_time()
    hold = json.loads((ROOT / "reports/research/control/owner-compute-hold.json").read_text())
    assert hold["research_paused"] is False
    admitted = json.loads((ROOT / "reports/research/control/day-goal.json").read_text())
    task = next(t for t in admitted["tasks"] if t["id"] == "USIC-PRACTITIONER-RESEARCH")
    assert task["active_owner"] == "f9add224-744b-471c-b812-c43cc179fa38"
    assert not task["economic_execution_admitted"]
    (OUT / "files").mkdir(parents=True, exist_ok=True)
    identity_path = ROUTE / "identity-candidates.json"
    inventory_path = ROUTE / "cache-route-inventory.json"
    frozen_path = ROUTE / "source-link-probes/independent-current-layout-snapshot.json"
    producer = BASE / "continuity-source-locator/producer-snapshots/fetch_sip_universe.py"
    roster = json.loads(identity_path.read_text())["records"]
    inventory = json.loads(inventory_path.read_text())["records"]
    layout = json.loads(frozen_path.read_text())["shard_symbols"]
    assert len(roster) == len(inventory) == 101
    routes, targets = {}, defaultdict(set)
    for item in inventory:
        symbol = item["symbol_candidate"]
        shards = sorted(k for k, v in layout.items() if symbol in v)
        assert shards == item["shards"], "frozen_locator_mapping_diff_requires_explicit_evidence"
        assert len(shards) <= 1, "multiple_shard_crossfile_duplicate_audit_needed"
        routes[symbol] = {"issue_key": item["issue_key"], "shards": shards}
        for f in item["exact_file_metadata"]:
            targets[f["path"]].add(symbol)
    assert len(routes) == 101
    sessions = us_equity_session_dates(date(2024, 1, 1), date(2025, 12, 31))
    opens = np.array(
        [
            int(datetime.combine(d, clocktime(9, 30), NY).timestamp()) * 1_000_000_000
            for d in sessions
        ],
        dtype=np.int64,
    )
    ends = np.array(
        [
            int(datetime.combine(d, us_equity_session_close(d), NY).timestamp()) * 1_000_000_000
            for d in sessions
        ],
        dtype=np.int64,
    )
    expected = (ends - opens) // MINUTE
    calendar = {
        "binding": bind(ROOT / "open_composer/market_sessions.py"),
        "sessions": [
            {
                "date": d.isoformat(),
                "open_ns": int(o),
                "close_ns_exclusive": int(e),
                "expected_real_RTH_minutes": int(n),
            }
            for d, o, e, n in zip(sessions, opens, ends, expected, strict=True)
        ],
    }
    if (OUT / "calendar.json").exists():
        assert json.loads((OUT / "calendar.json").read_text()) == calendar
    else:
        save(OUT / "calendar.json", calendar)
    by_symbol = defaultdict(dict)
    totals = Counter()
    checkpoints = []

    def absorb(item):
        if item["status"] == "missing_exact_locator_file":
            totals["missing_files"] += 1
            return
        totals["files_read"] += 1
        totals["unique_file_bytes"] += item["bytes"]
        for rec in item["records"]:
            symbol = rec["symbol_candidate"]
            for day, values in rec["session_counts"].items():
                assert day not in by_symbol[symbol], "duplicate_file_month_per_symbol"
                by_symbol[symbol][day] = values
            totals.update(
                {
                    "target_rows": rec["actual_rows"],
                    "unique_keys": rec["nonnull_unique_timestamp_keys"],
                    "duplicate_keys": rec["duplicate_keys"],
                    "null_timestamp_rows": rec["null_timestamp_rows"],
                    "unique_RTH_minute_keys": rec["unique_RTH_minute_keys"],
                    "non_RTH_unique_timestamp_keys": rec["non_RTH_unique_timestamp_keys"],
                    "RTH_nonminute_aligned_keys": rec["RTH_nonminute_aligned_keys"],
                }
            )

    def read_one(pair):
        ordinal, (relative, symbols) = pair
        path = ROOT / relative
        checkpoint = OUT / "files" / f"{ordinal:04d}.json"
        if checkpoint.exists():
            item = json.loads(checkpoint.read_text())
            assert item["path"] == relative and item["selected_symbols"] == sorted(symbols)
            if item["status"] != "missing_exact_locator_file":
                stat = path.stat()
                assert stat.st_size == item["bytes"] and stat.st_mtime_ns == item["mtime_ns"]
            return checkpoint, item
        item = {
            "path": relative,
            "selected_symbols": sorted(symbols),
            "columns_read": ["symbol", "timestamp"],
            "price_or_volume_columns_read": False,
        }
        if not path.exists():
            item["status"] = "missing_exact_locator_file"
        else:
            before = path.stat()
            assert before.st_size <= 16 * 1024 * 1024, "bounded_file_bytes"
            with path.open("rb") as handle:
                handle.seek(-8, 2)
                ending = handle.read(8)
                assert ending[-4:] == b"PAR1"
                footer_size = struct.unpack("<I", ending[:4])[0]
                assert footer_size <= 2 * 1024 * 1024
                handle.seek(-8 - footer_size, 2)
                footer = handle.read(footer_size + 8)
            pf = pq.ParquetFile(path)
            item.update(
                {
                    "bytes": before.st_size,
                    "mtime_ns": before.st_mtime_ns,
                    "sha256": None,
                    "hash_scope": "footer_and_selected_symbol_sorted_unique_time_keys",
                    "footer_sha256": hashlib.sha256(footer).hexdigest(),
                    "physical_schema": str(pf.schema_arrow),
                    "source_basis": "ALL_per_bound_producer_not_raw",
                    "fetched_at": None,
                    "historical_first_visible": None,
                }
            )
            schema = pf.schema_arrow
            assert "symbol" in schema.names and "timestamp" in schema.names
            assert pa.types.is_timestamp(schema.field("timestamp").type)
            assert schema.field("timestamp").type.tz == "UTC"
            table = pf.read(columns=["symbol", "timestamp"], use_threads=False)
            table = table.filter(pc.is_in(table["symbol"], value_set=pa.array(sorted(symbols))))
            item["actual_target_rows"] = len(table)
            records = []
            for symbol in sorted(symbols):
                column = table.filter(pc.equal(table["symbol"], symbol))[
                    "timestamp"
                ].combine_chunks()
                invalid = column.null_count
                column = pc.drop_null(column).cast(pa.timestamp("ns", tz="UTC"))
                ns = column.cast(pa.int64()).to_numpy(zero_copy_only=False)
                unique = np.unique(ns)
                duplicates = len(ns) - len(unique)
                idx = np.searchsorted(opens, unique, side="right") - 1
                safe = np.clip(idx, 0, len(sessions) - 1)
                rth = (idx >= 0) & (unique < ends[safe])
                minute_aligned = (unique - opens[safe]) % MINUTE == 0
                proper = rth & minute_aligned
                counts = np.bincount(idx[proper], minlength=len(sessions))
                opening_hour = proper & (unique < opens[safe] + 90 * MINUTE)
                earlycounts = np.bincount(idx[opening_hour], minlength=len(sessions))
                year, month = (int(part) for part in path.parts[-3:-1])
                dates = {}
                for i, day in enumerate(sessions):
                    if day.year != year or day.month != month:
                        continue
                    d = day.isoformat()
                    dates[d] = {
                        "unique_real_RTH_minute_keys": int(counts[i]),
                        "unique_0930_1100_minute_keys": int(earlycounts[i]),
                        "missing_grid_keys_not_filled": int(expected[i] - counts[i]),
                    }
                rec = {
                    "symbol_candidate": symbol,
                    "actual_rows": len(ns) + invalid,
                    "nonnull_unique_timestamp_keys": len(unique),
                    "duplicate_keys": duplicates,
                    "null_timestamp_rows": invalid,
                    "first_UTC": str(np.datetime64(int(unique[0]), "ns")) + "Z"
                    if len(unique)
                    else None,
                    "last_UTC": str(np.datetime64(int(unique[-1]), "ns")) + "Z"
                    if len(unique)
                    else None,
                    "sorted_unique_ns_le_sha256": hashlib.sha256(
                        unique.astype("<i8").tobytes()
                    ).hexdigest(),
                    "unique_RTH_minute_keys": int(proper.sum()),
                    "non_RTH_unique_timestamp_keys": int((~rth).sum()),
                    "RTH_nonminute_aligned_keys": int((rth & ~minute_aligned).sum()),
                    "session_counts": dates,
                }
                records.append(rec)
            item["records"] = records
            after = path.stat()
            assert before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
            item["status"] = "actual_selected_keys_verified_stable_file"
        save(checkpoint, item)
        return checkpoint, item

    # IO overlap only: all threads inherit taskset CPU0, Arrow data read has threads=False.
    with ThreadPoolExecutor(max_workers=4) as readers:
        outputs = readers.map(read_one, enumerate(sorted(targets.items())))
        for ordinal, (checkpoint, item) in enumerate(outputs):
            absorb(item)
            checkpoints.append(bind(checkpoint))
            if (ordinal + 1) % 100 == 0:
                print(
                    json.dumps(
                        {
                            "files_done": ordinal + 1,
                            "files_total": len(targets),
                            "CPU": round(time.process_time() - started_cpu, 3),
                        }
                    ),
                    flush=True,
                )
    summary = []
    for symbol, route in sorted(routes.items()):
        counts = by_symbol.get(symbol)
        summary.append(
            {
                "symbol_candidate": symbol,
                **route,
                "locator_status": "located"
                if route["shards"]
                else "not_in_frozen_locator_retained",
                "actual_session_counts": counts,
                "queried_calendar_sessions": len(counts) if counts is not None else None,
                "sessions_with_RTH_keys": sum(
                    v["unique_real_RTH_minute_keys"] > 0 for v in counts.values()
                )
                if counts is not None
                else None,
                "complete_RTH_key_sessions": sum(
                    v["missing_grid_keys_not_filled"] == 0 for v in counts.values()
                )
                if counts is not None
                else None,
                "missing_grid_keys_not_filled": sum(
                    v["missing_grid_keys_not_filled"] for v in counts.values()
                )
                if counts is not None
                else None,
                "raw_basis_certified": False,
                "episode_initialization_certified": False,
                "source_first_row_not_episode_birth": True,
            }
        )
    totals["roster_issues"] = len(routes)
    totals["with_locator"] = sum(bool(r["shards"]) for r in routes.values())
    totals["without_locator_retained"] = len(routes) - totals["with_locator"]
    totals["original_file_refs"] = sum(len(t) for t in targets.values())
    totals["unique_file_refs"] = len(targets)
    save(
        OUT / "actual-coverage.json",
        {
            "as_of_UTC": datetime.now(UTC).isoformat(),
            "counts": dict(totals),
            "records": summary,
            "selected_key_columns_only": True,
            "IO_readers": 4,
            "CPU_affinity_all_readers": [0],
            "partial_checkpoints_reused_without_quota_reset": True,
            "coverage_not_raw_cash_basis_or_historical_class_certificate": True,
            "missing_grid_keys_are_not_necessarily_missing_executed_trades": True,
            "no_filled_rows_no_removed_roster_members": True,
            "new_HTTP_requests": 0,
            "economic_trials": 0,
            "CPU_inner_not_additive": time.process_time() - started_cpu,
            "bindings": [bind(p) for p in [identity_path, inventory_path, frozen_path, producer]],
            "file_checkpoints": checkpoints,
        },
    )
    print(json.dumps(dict(totals)), flush=True)


if __name__ == "__main__":
    main()
