"""Bounded record intake for the real-input bridge; never fits or computes P&L."""

import hashlib
import json
import resource
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
EXPECTED = {
    "attention-complete/scientific-plan.json": (
        "d48ffd6be6a56818fac0dcecd28f6ab157d4e9fe684c875a928f6c9bbbeb373f"
    ),
    "dlsa/deepening/real-market-B-feasibility.json": (
        "3bb467db9df750901b25c0d1270238b52d698b5960ed9364dc870b3677323156"
    ),
}
PROGRAM = OUT.parent


def now():
    return datetime.now(UTC).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n")


def bind(path):
    p = ROOT / path
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"path": path, "bytes": p.stat().st_size, "sha256": h.hexdigest()}


def main():
    started = time.monotonic()
    budget = json.loads((OUT / "frozen-selection.json").read_text())
    cases = budget["cases"]
    for path, expected in EXPECTED.items():
        assert digest((PROGRAM / path).read_bytes()) == expected, path
    base = json.loads((PROGRAM / "dlsa/deepening/real-market-B-feasibility.json").read_text())
    inherited = []
    for b in base["bindings"]:
        actual = bind(b["path"])
        assert actual["sha256"] == b["sha256"], b["path"]
        inherited.append(actual)
    write(
        "inherited-binding-verification.json",
        {"at_utc": now(), "bindings": inherited, "all_match": True},
    )

    # Binary lookup of sorted-symbol SIP shards, checking neighbours at each hit.
    # No whole-panel values, directory-wide parquet scans or derived panel reads.
    footer_cache = {}
    footer_limit = 160
    inputs = {}
    bars = []
    reads = []

    def symbol_bounds(p):
        if p not in footer_cache:
            assert len(footer_cache) < footer_limit, "footer bound"
            f = pq.ParquetFile(p)
            n = f.schema_arrow.names.index("symbol")
            ranges = []
            for i in range(f.metadata.num_row_groups):
                stat = f.metadata.row_group(i).column(n).statistics
                assert stat and stat.has_min_max, "missing symbol statistics"
                ranges.append((str(stat.min), str(stat.max)))
            footer_cache[p] = (min(x[0] for x in ranges), max(x[1] for x in ranges))
        return footer_cache[p]

    def locate(year, symbol):
        paths = sorted((ROOT / f"data/sip/daily/{year}").glob("shard-*.parquet"))
        lo, hi = 0, len(paths)
        while lo < hi:
            mid = (lo + hi) // 2
            lower, upper = symbol_bounds(paths[mid])
            if upper < symbol:
                lo = mid + 1
            elif lower > symbol:
                hi = mid
            else:
                found = []
                for k in range(max(0, mid - 1), min(len(paths), mid + 2)):
                    a, b = symbol_bounds(paths[k])
                    if k < mid:
                        assert b <= lower, "unsorted/overlapping shard ordering"
                    if k > mid:
                        assert a >= upper, "unsorted/overlapping shard ordering"
                    if a <= symbol <= b:
                        found.append(paths[k])
                return found
        return []

    manifest = json.loads((ROOT / "data/sip-delisted/broad/_manifest.json").read_text())
    for case in cases:
        year = case["start"][:4]
        candidates = []
        for symbol in case["symbols"]:
            candidates.extend((p, "sip", None) for p in locate(year, symbol))
            for key, item in manifest["batches"].items():
                if symbol in item["symbols"]:
                    p = ROOT / f"data/sip-delisted/broad/daily/batch-{key}.parquet"
                    candidates.append((p, "delisted_backfill", item.get("fetched_at")))
        if case["id"] in {"rename_ELV_2022", "terminal_ATVI_2023"}:
            # The original S&P-removed batches are explicitly an existing
            # source of the by-year builder, separate from the broad manifest.
            candidates.extend(
                (p, "initial_delisted_backfill", None)
                for p in sorted((ROOT / "data/sip-delisted/daily").glob("batch-*.parquet"))
            )
        for p, kind, fetched in dict.fromkeys(candidates):
            assert len(inputs) < 24 or str(p.relative_to(ROOT)) in inputs, "value file cap"
            f = pq.ParquetFile(p)
            cols = f.schema_arrow.names
            ts = pa.scalar(
                pd.Timestamp(case["start"], tz="UTC").to_pydatetime(),
                type=f.schema_arrow.field("timestamp").type,
            )
            end = pa.scalar(
                (pd.Timestamp(case["end"], tz="UTC") + pd.Timedelta(days=1)).to_pydatetime(),
                type=f.schema_arrow.field("timestamp").type,
            )
            table = pq.read_table(
                p,
                filters=[
                    ("symbol", "in", case["symbols"]),
                    ("timestamp", ">=", ts),
                    ("timestamp", "<", end),
                ],
                use_threads=False,
            )
            df = table.to_pandas()
            path = str(p.relative_to(ROOT))
            inputs[path] = bind(path)
            reads.append(
                {
                    "case_id": case["id"],
                    "path": path,
                    "source_kind": kind,
                    "rows_selected": len(df),
                    "columns": cols,
                    "source_fetched_at": fetched,
                    "historical_first_available_at": None,
                }
            )
            df["case_id"] = case["id"]
            df["source_kind"] = kind
            df["source_path"] = path
            df["source_fetched_at"] = fetched
            df["bar_session"] = (
                pd.to_datetime(df["timestamp"], utc=True)
                .dt.tz_convert("America/New_York")
                .dt.strftime("%Y-%m-%d")
            )
            df["source_row_sha256"] = [
                digest(json.dumps(r, sort_keys=True, default=str).encode())
                for r in df[cols].to_dict("records")
            ]
            bars.append(df)
    df = pd.concat(bars, ignore_index=True) if bars else pd.DataFrame()
    assert len(df) <= budget["local_read_caps"]["price_output_rows"]
    df.sort_values(["case_id", "symbol", "bar_session", "source_kind"]).to_parquet(
        OUT / "selected-bars.parquet", index=False
    )
    write(
        "price-intake.json",
        {
            "at_utc": now(),
            "footer_files_read": len(footer_cache),
            "footer_paths": [str(p.relative_to(ROOT)) for p in footer_cache],
            "value_files": len(inputs),
            "rows": len(df),
            "reads": reads,
            "inputs": list(inputs.values()),
            "adjustment": "all",
            "bar_timestamp_semantics": (
                "session marker at midnight US Eastern, not close/publication/quote time"
            ),
            "retrieval_vintage": (
                "archive/backfill vintage; historical correction-free daily bar clock unverified"
            ),
        },
    )

    symbols = sorted({s for c in cases for s in c["symbols"]})
    for path in [
        "data/raw/sec_ma/cik_symbol_history.parquet",
        "data/sip-delisted/broad/_alias_exclusions.parquet",
        "data/sip-delisted/broad/_aliases.parquet",
    ]:
        p = ROOT / path
        cols = pq.ParquetFile(p).schema_arrow.names
        key = "symbol" if "symbol" in cols else "backfill_symbol"
        selected = pq.read_table(p, filters=[(key, "in", symbols)], use_threads=False).to_pandas()
        write(
            f"records/{p.stem.lstrip('_')}.json",
            {"input": bind(path), "selected_rows": selected.to_dict("records"), "schema": cols},
        )

    ciks = {x for c in cases for x in c["ciks"]}
    doc_records = []
    read_bytes = 0
    for month in budget["local_read_caps"]["sec_docs_months"]:
        p = ROOT / f"data/raw/sec_ma/docs/{month}.jsonl"
        if not p.exists():
            continue
        read_bytes += p.stat().st_size
        assert read_bytes <= budget["local_read_caps"]["sec_docs_read_bytes"]
        for n, line in enumerate(p.open()):
            row = json.loads(line)
            if row.get("cik") in ciks:
                doc_records.append(
                    {
                        "source_path": str(p.relative_to(ROOT)),
                        "source_line": n + 1,
                        "line_sha256": digest(line.encode()),
                        "record": row,
                    }
                )
        inputs[str(p.relative_to(ROOT))] = bind(str(p.relative_to(ROOT)))
    write(
        "records/sec-doc-records.json",
        {
            "selected_records": doc_records,
            "bytes_read": read_bytes,
            "inputs": [v for k, v in inputs.items() if "/sec_ma/docs/" in k],
            "caveat": (
                "Existing downloaded text packets can be partial HTTP206 and omit tables/exhibits; "
                "only visible included text is evidence, no completeness claim."
            ),
        },
    )

    zpath = ROOT / "data/raw/sec_submissions/submissions.zip"
    zrows = []
    extracted_bytes = 0
    for cik in sorted(ciks):
        member = f"CIK{cik:010d}.json"
        data = subprocess.check_output(["unzip", "-p", str(zpath), member])
        extracted_bytes += len(data)
        assert extracted_bytes <= budget["local_read_caps"]["selected_submission_json_bytes"]
        p = OUT / "records" / member
        p.write_bytes(data)
        sub = json.loads(data)
        recent = sub.get("filings", {}).get("recent", {})
        dates = recent.get("filingDate", [])
        rows = []
        windows = [c for c in cases if cik in c["ciks"]]
        for i, d in enumerate(dates):
            if any(c["start"] <= d <= c["end"] for c in windows):
                row = {
                    k: v[i]
                    for k, v in recent.items()
                    if isinstance(v, list) and len(v) == len(dates)
                }
                rows.append(row)
        zrows.append(
            {
                "cik": cik,
                "current_snapshot_name": sub.get("name"),
                "current_tickers_not_historical_identity": sub.get("tickers"),
                "source": "data/raw/sec_submissions/submissions.zip::" + member,
                "container_bytes": zpath.stat().st_size,
                "member_bytes": len(data),
                "member_sha256": digest(data),
                "selected_filings": rows,
                "older_history_files_not_read": sub.get("filings", {}).get("files", []),
                "provenance_caveat": (
                    "Member SHA binds exact selected content, unzip validates CRC; "
                    "full archive hash deliberately not computed; "
                    "snapshot current tickers/name are not historical class identity."
                ),
            }
        )
    write(
        "records/submission-evidence.json",
        {"members": zrows, "selected_member_bytes": extracted_bytes},
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt = {
        "at_utc": now(),
        "command": "intake.py",
        "cpu_seconds": usage.ru_utime + usage.ru_stime + child.ru_utime + child.ru_stime,
        "wall_seconds": time.monotonic() - started,
        "max_rss_kib": usage.ru_maxrss,
        "child_max_rss_kib": child.ru_maxrss,
        "threads": 1,
        "new_source_requests": 0,
        "economic_computations": 0,
        "fits": 0,
        "rows": len(df),
    }
    write("intake-receipt.json", receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        with (OUT / "failed-prep-attempts.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    {
                        "at_utc": now(),
                        "command": "intake.py",
                        "cpu_seconds": usage.ru_utime + usage.ru_stime,
                        "max_rss_kib": usage.ru_maxrss,
                        "error": repr(exc),
                        "economic_computations": 0,
                    }
                )
                + "\n"
            )
        raise
