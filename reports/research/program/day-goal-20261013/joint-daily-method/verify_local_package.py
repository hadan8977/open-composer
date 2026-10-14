"""Independent package and snapshot checks; no strategy or model calculation."""
import hashlib
import json
import resource
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
P = ROOT / "local-input"
start = time.process_time()
resource.setrlimit(resource.RLIMIT_CPU, (45, 50))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(262144), b""):
            h.update(chunk)
    return h.hexdigest()


manifest = P / "package-manifest.json"
assert digest(manifest) == "82f8b3c5f21fef816e8d0f852e293125636279b86294ca6d5319f4b8cc083912"
m = json.loads(manifest.read_text())
for entry in m["files"]:
    path = P / entry["path"]
    assert path.stat().st_size == entry["bytes"], str(path)
    assert digest(path) == entry["sha256"], str(path)

import duckdb
import pyarrow.parquet as pq

con = duckdb.connect()
con.execute("SET threads=1")
con.execute("SET memory_limit='220MB'")
pattern = str(P / "current-vintage-wide-snapshot-*.parquet")
stats = con.execute(
    "SELECT count(*),count(DISTINCT symbol),"
    "sum(source_ghost_retained::int),sum((close IS NULL)::int),"
    "sum((sec_cik IS NULL)::int),sum(permanent_security_link_certified::int),"
    "sum(complete_terminal_action_chain_certified::int) FROM read_parquet(?)", [pattern]
).fetchone()
assert stats == (37170, 16108, 1613, 17039, 21720, 0, 0), stats
day_stats = con.execute(
    "SELECT trade_date,count(*),count(DISTINCT symbol),"
    "count(DISTINCT CASE WHEN close IS NOT NULL AND "
    "abs(close-source_current_adjusted_close)>1e-5 THEN symbol END) "
    "FROM read_parquet(?) GROUP BY trade_date ORDER BY trade_date", [pattern]
).fetchall()
assert [r[1:] for r in day_stats] == [
    (6991, 6991, 765), (8298, 8298, 875), (9887, 9887, 81), (11994, 11992, 63)
], day_stats

# Re-read deterministic actual source rows using retained row lineage, not author aggregates.
examples = con.execute(
    "SELECT source_file,symbol,source_bar_timestamp,source_current_adjusted_close "
    "FROM read_parquet(?) QUALIFY row_number() OVER "
    "(PARTITION BY trade_date ORDER BY source_file,symbol,source_bar_timestamp)<=3 "
    "ORDER BY source_file,symbol,source_bar_timestamp", [pattern]
).fetchall()
for filename, symbol, timestamp, close in examples:
    table = pq.read_table(filename, columns=["symbol", "timestamp", "close"],
                         filters=[("symbol", "=", symbol), ("timestamp", "=", timestamp)])
    assert close in table.column("close").to_pylist(), (filename, symbol, timestamp)

summary = json.loads((P / "panel-wide-summary.json").read_text())
assert sum(x["rows"] for x in summary) == 8029213
assert sum(x["dates"] for x in summary) == 2688
assert min(x["names_per_date_min"] for x in summary) == 2772
assert max(x["names_per_date_max"] for x in summary) == 3241
out = {
    "package_sha256": digest(manifest), "manifest_files_verified": len(m["files"]),
    "mismatches": [], "independent_snapshot_counts": list(stats),
    "independent_date_counts": [[str(r[0]), *r[1:]] for r in day_stats],
    "actual_source_price_rows_rechecked": len(examples),
    "panel_year_aggregates_sum_checked_not_entire_history_rerun": True,
    "all_2678_source_payloads_independently_rehashed": False,
    "acceptance_scope": "source feasibility and actual candidate snapshots, not economic input",
    "CPU_coreseconds": time.process_time()-start,
    "peak_RSS_KiB": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    "fits": 0, "economic_runs": 0, "source_or_market_requests": 0,
}
(ROOT / "independent-local-verification.json").write_text(json.dumps(out, indent=2)+"\n")
print(json.dumps(out))
