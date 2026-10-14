"""Same lookup's targeted alias/field repair; preserve the first metadata pass."""

from __future__ import annotations

import hashlib
import json
import resource
import subprocess
import time
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "continuity-source-locator/recovery"
START = time.process_time()
resource.setrlimit(resource.RLIMIT_CPU, (40, 41))


def bound(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    assert not (OUT / "source-link-recovery.json").exists()
    OUT.mkdir(exist_ok=True)
    alias = ROOT / "data/sip/minute/2024"
    assert alias.is_symlink() and alias.exists()
    command = ["rg", "--files", "-uu", "--follow", "data/sip/minute/2024"]
    answer = subprocess.run(command, capture_output=True, check=False)
    assert len(answer.stdout) <= 2 * 1024 * 1024, (
        "Targetedyear locator cap; preserve incomplete status"
    )
    (OUT / "2024-alias-file-locator.txt").write_bytes(answer.stdout)
    paths = answer.stdout.decode().splitlines()
    counts = Counter("/".join(Path(p).parts[3:5]) for p in paths if p.endswith(".parquet"))
    selected = []
    for month in ("01", "12"):
        candidates = sorted(
            p
            for p in paths
            if p.startswith(f"data/sip/minute/2024/{month}/") and p.endswith(".parquet")
        )
        if candidates:
            selected.append(candidates[0])
    selected += [
        "data/features/intraday5m/universe.parquet",
        "data/live/equity_book/borrow/alpaca_assets_20261001.parquet",
    ]
    footers = []
    for name in selected:
        path = ROOT / name
        if not path.exists():
            footers.append({"path": name, "status": "metadata_path_absent"})
            continue
        meta = pq.ParquetFile(path)
        size = meta.metadata.serialized_size
        with path.open("rb") as f:
            f.seek(-(size + 8), 2)
            footer = f.read(size + 8)
        ranges = []
        for i in range(meta.metadata.num_row_groups):
            for j in range(meta.metadata.num_columns):
                c = meta.metadata.row_group(i).column(j)
                if (
                    c.path_in_schema in ("timestamp", "date", "month_end", "as_of")
                    and c.statistics
                    and c.statistics.has_min_max
                ):
                    ranges.append(
                        {
                            "field": c.path_in_schema,
                            "min": str(c.statistics.min),
                            "max": str(c.statistics.max),
                        }
                    )
        footers.append(
            {
                "path": name,
                "resolved": str(path.resolve()),
                "file_bytes": path.stat().st_size,
                "footer_hash_scope": "actualfooterbytes only, notwholedatafile",
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
                "row_count_metadata": meta.metadata.num_rows,
                "schema": str(meta.schema_arrow),
                "timestamp_ranges": ranges,
                "market_rows_read": 0,
            }
        )
    # Only metadata already selected in the first pass, extracting missed item-level fields.
    names = [
        "data/research/mom_breadth_qd_r1_development/static/snapshot-manifest.json",
        "data/research/mom_breadth_qd_r1_development/structural/snapshot-manifest.json",
        "data/research/mom_breadth_qd_r1_development/leveraged/snapshot-manifest.json",
        "reports/research/program/day-goal-20261011-2/chinco-modern-adaptation/source-s0/cohort.json",
        "reports/research/program/day-goal-20261011-2/chinco-modern-adaptation/source-s1/cohort50-subset-input-index.json",
    ]
    metadata, inspected_bytes = [], 0
    for name in names:
        path = ROOT / name
        if path.stat().st_size > 512 * 1024 or inspected_bytes + path.stat().st_size > 768 * 1024:
            metadata.append({"path": name, "status": "targeted_metadata_byte_guard"})
            continue
        inspected_bytes += path.stat().st_size
        x = json.loads(path.read_bytes())
        entries = x.get("items", x.get("datasets", x.get("snapshots", [])))
        metadata.append(
            {
                "binding": bound(path),
                "keys": list(x),
                "role": x.get("role"),
                "scope": x.get("scope"),
                "snapshot_path": x.get("snapshot_path"),
                "algorithm": x.get("algorithm"),
                "symbols50": x.get("symbols50"),
                "top_level_symbols": x.get("symbols"),
                "top_level_adjustment": x.get("adjustment"),
                "items_count": len(entries),
                "items_metadata": [
                    {
                        k: item.get(k)
                        for k in (
                            "symbol",
                            "symbols",
                            "timeframe",
                            "adjustment",
                            "row_count",
                            "actual_start",
                            "actual_end",
                            "first_timestamp",
                            "last_timestamp",
                            "output_path",
                        )
                        if k in item
                    }
                    for item in entries
                    if isinstance(item, dict)
                ]
                if isinstance(entries, list)
                else "mapping_not_interpreted",
            }
        )
    result = {
        "purpose": "Targeted recovery of same locator; no repeated93168file/data scan",
        "original_locator": bound(BASE / "continuity-source-locator/locator-result.json"),
        "known_registered_alias": {
            "path": "data/sip/minute/2024",
            "target": str(alias.resolve()),
            "first_rg_default_followed_symlink": False,
            "initial2024count_status": "N/A_not_enumerated, notzero",
        },
        "recovery_command": command,
        "files_listed": len(paths),
        "file_name_bytes": len(answer.stdout),
        "process_exit": answer.returncode,
        "stderr": answer.stderr.decode()[:1000],
        "2024_month_file_counts": dict(counts),
        "footers": footers,
        "source_item_metadata": metadata,
        "targeted_metadata_bytes": inspected_bytes,
        "filesystem_scope": (
            "Existingregisteredprojectalias/archive only; no newmarketclient/"
            "Driveconnector requests. Filesystem mount transport unknown separately."
        ),
        "no_market_rows_or_returns": True,
        "HTTP_source_market_requests": 0,
        "resource": {
            "CPU_seconds": time.process_time() - START,
            "max_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }
    (OUT / "source-link-recovery.json").write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "2024_months": len(counts),
                "2024_files": sum(counts.values()),
                "metadata_bytes": inspected_bytes,
                "footer_samples": len(footers),
                "CPU_seconds": result["resource"]["CPU_seconds"],
                "market_rows_read": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
