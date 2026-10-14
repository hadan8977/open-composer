"""Bound existing input entities and timestamp coverage; never read price columns."""

import hashlib
import json
import resource
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb

P = Path(__file__).resolve().parents[1]
ROOT = Path.cwd()
SYMBOLS = ["COIN", "GME", "LMND", "SMCI", "SOFI", "SOUN"]


def bind(path):
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return dict(path=str(path.relative_to(ROOT)), sha256=digest, bytes=path.stat().st_size)


def main():
    start = time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU, (60, 65))
    old = P.parent / "acquisition/request-ledger.json"
    ledger = json.loads(old.read_text())
    entities = []
    for a in ledger["attempts"]:
        if a.get("http_status") != 200 or a.get("status") != "complete_bounded_source_response":
            continue
        b = a.get("entity", {})
        path = ROOT / b.get("path", "")
        if not path.is_file():
            continue
        actual = bind(path)
        assert actual["sha256"] == b["sha256"]
        obj = json.loads(path.read_text())
        coverage = {
            s: dict(
                rows=len(v),
                first=min((r.get("t", "") for r in v), default=None),
                last=max((r.get("t", "") for r in v), default=None),
            )
            for s, v in obj.get("bars", {}).items()
            if s in SYMBOLS
        }
        if coverage or obj.get("corporate_actions"):
            entities.append(
                dict(
                    id=a.get("id"),
                    entity=actual,
                    params=a["params"],
                    coverage=coverage,
                    next_page_token=obj.get("next_page_token"),
                    action_counts={k: len(v) for k, v in obj.get("corporate_actions", {}).items()},
                    fetched_at=a.get("current_fetched_at"),
                    historical_visible_at=None,
                )
            )
    layout = json.loads((ROOT / "data/sip/minute/_LAYOUT.json").read_text())["shard_symbols"]
    symbols = sorted({s for v in layout.values() for s in v})
    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='400MB'")
    minute = []
    for s in SYMBOLS:
        shards = {int(k) for k, v in layout.items() if s in v} | {symbols.index(s) // 40}
        for year in (2024, 2025):
            for month in range(1, 13):
                found = []
                for shard in sorted(shards):
                    path = ROOT / f"data/sip/minute/{year}/{month:02}/shard-{shard:04}.parquet"
                    if not path.exists():
                        continue
                    # No OHLCV/returns/features/labels. No economic trial.
                    count, first, last, days = con.execute(
                        (
                            "SELECT count(*),min(timestamp),max(timestamp),count(distinct timezon"
                            "e('America/New_York',timestamp)::date) FROM read_parquet(?) WHERE sy"
                            "mbol=?"
                        ),
                        [str(path), s],
                    ).fetchone()
                    if count:
                        found.append(
                            dict(
                                entity=bind(path),
                                rows=count,
                                first=str(first),
                                last=str(last),
                                days=days,
                            )
                        )
                minute.append(
                    dict(
                        symbol=s,
                        year=year,
                        month=month,
                        observed=found,
                        duplicate_source_files=len(found) > 1,
                        status="actual_clock_coverage" if found else "missing",
                    )
                )
    result = dict(
        at_utc=datetime.now(UTC).isoformat(),
        cohort_selection=(
            "Predetermined six source long examples, continuous seen controls; ne"
            "ver PIT opportunity set"
        ),
        entity_ledger=bind(old),
        entities=entities,
        minute_clock_coverage=minute,
        layout=bind(ROOT / "data/sip/minute/_LAYOUT.json"),
        prices_read=False,
        features_built=False,
        adjustments=(
            "Local producer=adjustment all; raw normalization/action proof requir"
            "es independent preprocessing admission"
        ),
        historical_identity="Not certifiedPIT; no reconstructed membership or delist claim",
        historical_visible_at=None,
        coverage_is_not_input_acceptance=True,
        market_requests=0,
        CPU=time.process_time() - start,
        max_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    )
    (P / "input-inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                actual_entities=len(entities),
                months_with_clocks=sum(bool(x["observed"]) for x in minute),
                expected_months=len(minute),
                CPU=result["CPU"],
                max_RSS_KiB=result["max_RSS_KiB"],
            )
        )
    )


if __name__ == "__main__":
    main()
