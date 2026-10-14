"""Scope the price mismatch diagnostic and check missing SEC clock values."""
import json
import resource
import time
from pathlib import Path

import duckdb

start = time.process_time()
resource.setrlimit(resource.RLIMIT_CPU, (30, 35))
p = Path(__file__).resolve().parent
c = duckdb.connect()
c.execute("SET threads=1")
c.execute("SET memory_limit='200MB'")
sql = """
SELECT trade_date,count(*) AS compared,
sum((abs(close-source_current_adjusted_close)>1e-5)::int) AS abs_threshold_rows,
sum((abs(close/source_current_adjusted_close-1)>0.0001)::int) AS over_1bp_rows,
sum((abs(close/source_current_adjusted_close-1)>0.01)::int) AS over_100bp_rows,
max(abs(close/source_current_adjusted_close-1)) AS maximum_relative_price_difference
FROM read_parquet(?)
WHERE close IS NOT NULL AND source_current_adjusted_close>0
GROUP BY trade_date ORDER BY trade_date
"""
cur = c.execute(sql, [str(p/'local-input/current-vintage-wide-snapshot-*.parquet')])
names = [r[0] for r in cur.description]
prices = [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
cur = c.execute("""
SELECT count(*) AS rows,sum((filed IS NULL)::int) AS null_filed,
sum((usable_session IS NULL)::int) AS null_usable,
sum((usable_session<=filed)::int) AS nonlater_usable
FROM read_parquet('data/features/sec_fundamentals/facts.parquet')
""")
names = [r[0] for r in cur.description]
clocks = dict(zip(names,cur.fetchone(),strict=True))
out = {
    'prices':prices,'SEC_clock':clocks,
    'interpretation':'Price discrepancies are source diagnostics, not returns or trading exclusions. Threshold count alone does not identify the cause. No price-difference row is removed.',
    'CPU_coreseconds':time.process_time()-start,
    'peak_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    'fits':0,'economic_runs':0,'source_or_market_requests':0,
}
(p/'independent-local-semantics.json').write_text(json.dumps(out,indent=2,default=str)+'\n')
print(json.dumps(out,default=str))
