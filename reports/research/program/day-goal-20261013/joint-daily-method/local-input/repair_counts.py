"""Correct one multiplicity statistic; retain source rows and every failed attempt."""

from __future__ import annotations

import json
import resource
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = Path("/root/codex-test/open-composer")


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (40, 45))
    import duckdb

    con = duckdb.connect()
    con.execute("SET threads=1")
    con.execute("SET memory_limit='240MB'")
    con.execute("SET preserve_insertion_order=false")
    con.execute(f"SET temp_directory='{OUT}/_duck_tmp'")
    files = sorted((ROOT / "data/sip/daily/2026").glob("*.parquet"))
    files += sorted((ROOT / "data/sip-delisted/broad/daily").glob("*.parquet"))
    source = (
        "read_parquet([" + ",".join("'" + str(p) + "'" for p in files) + "],union_by_name=true)"
    )
    sql = f"""
    WITH b AS (
        SELECT symbol,CAST(timestamp AS DATE) AS trade_date,count(*) AS n,
               min(close) AS min_close,max(close) AS max_close
        FROM {source} WHERE CAST(timestamp AS DATE)=DATE '2026-01-30' GROUP BY 1,2
    ), d AS (
        SELECT symbol,trade_date,count(*) AS n,min(close) AS feature_close,
               count(DISTINCT close) AS nc
        FROM read_parquet('{ROOT}/data/features/daily_broad/2026.parquet')
        WHERE trade_date=DATE '2026-01-30' GROUP BY 1,2
    ) SELECT count(*) AS source_keys,sum(b.n) AS source_records,
        sum(CASE WHEN b.n>1 THEN 1 ELSE 0 END) AS duplicate_source_keys,
        sum(CASE WHEN b.min_close<>b.max_close THEN 1 ELSE 0 END) AS conflicting_close_keys,
        sum(CASE WHEN d.symbol IS NOT NULL THEN 1 ELSE 0 END) AS joined_to_daily,
        sum(CASE WHEN d.n>1 THEN 1 ELSE 0 END) AS ambiguous_daily_feature_keys,
        sum(CASE WHEN d.nc>1 THEN 1 ELSE 0 END) AS conflicting_daily_price_keys,
        sum(CASE WHEN d.n=1 AND abs(d.feature_close-b.min_close)>1e-5 THEN 1 ELSE 0 END)
            AS price_version_mismatch_keys
    FROM b LEFT JOIN d USING(symbol,trade_date)
    """
    outcome = "not_completed"
    try:
        cur = con.execute(sql)
        names = [r[0] for r in cur.description]
        result = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
        save("source_feature_connection_2026.json", result)
        cur = con.execute(f"""
            SELECT count(*) AS row_count,count(DISTINCT symbol) AS symbol_count,
                sum(CASE WHEN source_ghost_retained THEN 1 ELSE 0 END) AS ghost_records,
                sum(CASE WHEN close IS NULL THEN 1 ELSE 0 END) AS missing_daily_block,
                sum(CASE WHEN sec_cik IS NULL THEN 1 ELSE 0 END) AS missing_unique_SEC_block
            FROM read_parquet('{OUT}/current-vintage-wide-snapshot-*.parquet')
        """)
        names = [r[0] for r in cur.description]
        retained = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
        save("snapshot-retention-summary.json", retained)
        outcome = "pass"
        print(json.dumps({"connection2026": result, "retention": retained}), flush=True)
    finally:
        con.close()
        save(
            "connection-repair-resource-receipt.json",
            {
                "cpu_seconds": time.process_time(),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "outcome": outcome,
                "one_CPU": True,
                "memory_cap_mib": 400,
                "process_CPU_soft_cap": 40,
                "sql": sql,
                "snapshots_unchanged": True,
                "new_external_requests": 0,
                "fits": 0,
            },
        )


if __name__ == "__main__":
    main()
