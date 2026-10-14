"""One bounded ignored-path metadata lookup, never a market row or return scan."""

from __future__ import annotations

import hashlib
import json
import re
import resource
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[3]
OUT = BASE / "continuity-source-locator"
MAX_LIST_BYTES = 8 * 1024 * 1024
MAX_METADATA_FILES = 96
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_TOTAL_JSON_BYTES = 8 * 1024 * 1024
START_CPU = time.process_time()
resource.setrlimit(resource.RLIMIT_CPU, (60, 61))


def bound(path):
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, default=str) + "\n")


def describe(value, prefix="", depth=0):
    """Only provenance/coverage/schema attributes, not arbitrary body or authentication."""
    wanted = re.compile(
        r"symbol|ticker|universe|cohort|episode|asof|as_of|asset_class|security|"
        r"adjustment|provider|feed|timeframe|timestamp|period|start|end|first|last|"
        r"row_count|rows|source|provenance|captured|created|fetched|visible|published|"
        r"membership|constituent|schema|version|layout|date|contract|snapshot"
    )
    result = []
    if not isinstance(value, dict) or depth > 4:
        return result
    for key, child in value.items():
        path = prefix + str(key)
        if isinstance(child, dict):
            result.extend(describe(child, path + ".", depth + 1))
        elif wanted.search(str(key).lower()):
            if isinstance(child, list):
                result.append({"field": path, "count": len(child), "first_items": child[:6]})
            elif isinstance(child, (str, int, float, bool)) or child is None:
                result.append({"field": path, "value": str(child)[:400]})
    return result


def main():
    assert ROOT == Path.cwd()
    assert not (OUT / "locator-result.json").exists(), "Do not repeat this source-pool lookup"
    OUT.mkdir(exist_ok=True)
    command = ["rg", "--files", "-uu", "data"]
    with (OUT / "data-file-locator.txt").open("wb") as handle:
        process = subprocess.Popen(command, stdout=subprocess.PIPE)
        size, truncated = 0, False
        for line in process.stdout:
            if size + len(line) > MAX_LIST_BYTES:
                truncated = True
                process.terminate()
                break
            handle.write(line)
            size += len(line)
        process.wait()
    data_paths = (OUT / "data-file-locator.txt").read_text().splitlines()
    list_bytes = (OUT / "data-file-locator.txt").stat().st_size
    report_command = [
        "rg",
        "--files",
        "-uu",
        "--glob",
        "*manifest*.json",
        "--glob",
        "*universe*.json",
        "--glob",
        "*cohort*.json",
        "--glob",
        "*membership*",
        "reports/research/program",
        "reports/research/iterations",
    ]
    report_names = subprocess.run(report_command, capture_output=True, check=False)
    report_truncated = len(report_names.stdout) > 2 * 1024 * 1024
    report_bytes = report_names.stdout[: 2 * 1024 * 1024]
    if report_truncated:
        report_bytes = report_bytes.rsplit(b"\n", 1)[0] + b"\n"
    (OUT / "report-metadata-file-locator.txt").write_bytes(report_bytes)
    report_paths = report_bytes.decode().splitlines()
    # Report candidates are source/coverage artifacts only; never evaluated-return reports.
    report_paths = [
        p
        for p in report_paths
        if any(
            x in Path(p).name.lower()
            for x in (
                "snapshot-manifest",
                "source-manifest",
                "data-manifest",
                "universe",
                "membership",
                "cohort",
            )
        )
    ]
    paths = data_paths + report_paths
    raw_manifests = [
        p for p in paths if p.endswith("raw.manifest.json") or p.endswith("snapshot-manifest.json")
    ]
    anchor_pattern = re.compile(
        (
            "(membership|constituent|cohort|episode|security.?master"
            "|universe|assets|company.?tickers|permno|crsp|wrds|mani"
            "fest)"
        ),
        re.I,
    )
    anchors = [
        p
        for p in paths
        if anchor_pattern.search(Path(p).name)
        and p.endswith((".json", ".jsonl", ".csv", ".parquet"))
    ]
    priority = [
        "data/sip/minute/_COMPLETE_2023_2026.json",
        "data/sip/minute/_LAYOUT.json",
        "data/sip/daily/_LAYOUT.json",
        "data/sip-delisted/by_year/_MANIFEST.json",
        "data/sip-delisted/broad/_manifest.json",
        "data/live/equity_book/panel/_manifest.json",
    ]
    dated_anchors = [
        p
        for p in anchors
        if re.search(
            (
                "membership|constituent|cohort|episode|security.?master|"
                "universe|assets|company.?tickers|permno|crsp|wrds"
            ),
            Path(p).name,
            re.I,
        )
    ]
    raw_families = {}
    for name in sorted(raw_manifests):
        raw_families.setdefault(str(Path(name).parent), name)
    # Avoid letting manyETFexports consume the inspection budget before datedcoverage sources.
    candidates = list(
        dict.fromkeys(
            priority
            + sorted(dated_anchors)
            + list(raw_families.values())
            + sorted(raw_manifests)
            + sorted(anchors)
        )
    )
    ignored = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        input="\n".join(candidates) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    ignored_set = set(ignored.stdout.splitlines())
    save(
        "candidate-paths.json",
        {
            "raw_snapshot_manifest_candidates": raw_manifests,
            "coverage_anchor_candidates": anchors,
            "gitignored_candidate_paths": sorted(ignored_set),
            "all_candidates": candidates,
            "enumeration_truncated": truncated,
        },
    )
    summaries, read_bytes = [], 0
    for name in candidates:
        if len(summaries) >= MAX_METADATA_FILES:
            break
        path = ROOT / name
        if not path.exists():
            summaries.append({"path": name, "status": "missing_declared_metadata_path"})
            continue
        if path.suffix != ".json":
            continue
        size = path.stat().st_size
        if size > MAX_JSON_BYTES or read_bytes + size > MAX_TOTAL_JSON_BYTES:
            summaries.append(
                {
                    "path": name,
                    "bytes": size,
                    "status": "metadata_content_not_read_guard",
                    "gitignored": name in ignored_set,
                }
            )
            continue
        try:
            payload = json.loads(path.read_bytes())
        except (ValueError, UnicodeError) as exc:
            summaries.append(
                {
                    "path": name,
                    "status": "metadata_parse_failure",
                    "exception_type": type(exc).__name__,
                }
            )
            continue
        read_bytes += size
        rec = {
            "binding": bound(path),
            "gitignored": name in ignored_set,
            "top_level_keys": list(payload)[:35] if isinstance(payload, dict) else "list",
            "coverage_provenance_fields": describe(payload),
            "status": "metadata_read",
        }
        if name.endswith("/_LAYOUT.json"):
            layout = payload.get("shard_symbols", {})
            rec["declared_symbols"] = len({s for values in layout.values() for s in values})
            rec["declared_shards"] = len(layout)
            rec["stock_type_and_historical_membership_supplied"] = False
        summaries.append(rec)
    save("metadata-summaries.json", summaries)

    # Six deterministic footer/header examples, no column data or bar row access.
    footer_paths = []
    for period in ("2024/01", "2024/12", "2025/01", "2025/12"):
        options = sorted(
            p
            for p in paths
            if p.startswith(f"data/sip/minute/{period}/") and p.endswith(".parquet")
        )
        if options:
            footer_paths.append(options[0])
    footer_paths += [p for p in anchors if p.endswith(".parquet")][:2]
    footers = []
    for name in footer_paths:
        path = ROOT / name
        meta = pq.ParquetFile(path)
        metadata = meta.metadata
        serialized_size = metadata.serialized_size
        with path.open("rb") as handle:
            handle.seek(-(serialized_size + 8), 2)
            footer = handle.read(serialized_size + 8)
        stamps = []
        for group in range(metadata.num_row_groups):
            for column in range(metadata.num_columns):
                col = metadata.row_group(group).column(column)
                if (
                    col.path_in_schema in ("timestamp", "date", "filing_date", "as_of")
                    and col.statistics
                    and col.statistics.has_min_max
                ):
                    stamps.append(
                        {
                            "field": col.path_in_schema,
                            "min": str(col.statistics.min),
                            "max": str(col.statistics.max),
                        }
                    )
        footers.append(
            {
                "path": name,
                "file_bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "hash_scope": "Footer only; wholedatahash not claimed",
                "footer_sha256": hashlib.sha256(footer).hexdigest(),
                "schema": str(meta.schema_arrow),
                "row_count_metadata": metadata.num_rows,
                "timestamp_statistic_ranges": stamps,
                "market_rows_read": 0,
                "range_is_not_per_symbol_continuous_coverage": True,
            }
        )
    save("bounded-parquet-footers.json", footers)
    minute_files = [p for p in paths if p.startswith("data/sip/minute/") and p.endswith(".parquet")]
    period_counts = Counter("/".join(Path(p).parts[3:5]) for p in minute_files)
    producer = ROOT / "scripts/fetch_sip_universe.py"
    lines = producer.read_text().splitlines()
    evidence = [
        {"line": i + 1, "text": line}
        for i, line in enumerate(lines)
        if any(
            t in line
            for t in (
                "GetAssetsRequest(status=AssetStatus.ACTIVE",
                "adjustment=",
                "tradable",
                "_COMPLETE",
                "_LAYOUT",
            )
        )
    ]
    result = {
        "as_of_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "One bounded metadata/source connection lookup, includin"
            "gignored paths; no wide row scan"
        ),
        "filename_locator": {
            "command": command,
            "files_listed": len(data_paths),
            "bytes": list_bytes,
            "truncated": truncated,
            "market_rows_read": 0,
        },
        "report_metadata_locator": {
            "command": report_command,
            "candidate_paths": len(report_paths),
            "bytes": len(report_bytes),
            "truncated": report_truncated,
            "no_economic_report_values_read": True,
        },
        "raw_snapshot_manifest_candidates": len(raw_manifests),
        "anchor_candidate_paths": len(anchors),
        "metadata_objects_inspected": len(summaries),
        "metadata_content_bytes": read_bytes,
        "metadata_limit": MAX_METADATA_FILES,
        "metadata_candidates_not_inspected": max(0, len(candidates) - len(summaries)),
        "minute_archive_file_counts_2024_2025": {
            p: n for p, n in period_counts.items() if p.startswith(("2024/", "2025/"))
        },
        "producer": bound(producer),
        "producer_semantic_evidence": evidence,
        "old_daily_wide_evidence_reused": (
            "reports/research/program/day-goal-20261013/joint-daily-"
            "method/local-input/archive-inventory.json; no repeated "
            "numericalscan"
        ),
        "raw_manifest_population": {
            "must_inspect_summary_before_claim": True,
            "not_equity_cohort_from_filename": True,
        },
        "dated_cohort_connection_status": (
            "Inspect actualsource/period/type metadata; file dates/m"
            "inmax andcurrenttickers are not historicalmembership ce"
            "rtificates"
        ),
        "source_market_requests_new": 0,
        "fit_strategy_return_orders": 0,
        "resource": {
            "CPU_seconds": time.process_time() - START_CPU,
            "max_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }
    save("locator-result.json", result)
    print(
        json.dumps(
            {
                "metadata_objects": len(summaries),
                "filename_count": len(paths),
                "raw_manifests": len(raw_manifests),
                "anchors": len(anchors),
                "footer_samples": len(footers),
                "metadata_limit_reached": len(summaries) == MAX_METADATA_FILES,
                "list_truncated": truncated,
                "CPU_seconds": result["resource"]["CPU_seconds"],
                "rows_read": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
