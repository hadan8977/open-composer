"""Finish retained complete price chunks, without repeating issuer calculations."""
import hashlib
import json
from pathlib import Path

import duckdb

WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
cache = P / 'current-issuer-exact-checkpoints'
binding = json.loads((cache / 'binding.json').read_text())
def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
assert sha(WT / 'data/features/sec_fundamentals/facts.parquet') == binding['new']
assert sha(WT / 'scripts/build_sec_xbrl_fundamentals.py') == binding['code']
log = (P / 'current-fundamentals-exact03-log.txt').read_text()
assert 'issuer exact comparisons 5230/5230, changed 64' in log
assert 'price join 5444/5444, rows 1011257' in log
parts = cache / 'price-parts'
assert len(list(parts.glob('*.parquet'))) == 28
c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='220MB'; SET max_temp_directory_size='128MB'")
c.execute("SET temp_directory='" + str(cache / 'tmp') + "'")
assert c.execute('SELECT count(*) FROM read_parquet(?)', [str(parts / '*.parquet')]).fetchone()[0] == 1011257
out = WT / 'data/features/_current_components/sec_fundamentals_daily/2026.parquet'
tmp = out.with_suffix('.parquet.complete.tmp')
c.execute("COPY (SELECT * FROM read_parquet($1) ORDER BY trade_date,symbol) TO '" + str(tmp) + "' (FORMAT PARQUET)", [str(parts / '*.parquet')])
c.close()
tmp.replace(out)
r = {'source_bindings': binding, 'rows': 1011257, 'output': str(out), 'output_sha256': sha(out), 'changed_CIKs': 64, 'unchanged_CIKs': 5166, 'checkpoint_reuse': 'all-column exact ordered issuer source equality; same original formula code; full calculation logs retained', 'formula_changes': False, 'source_requests': 0, 'price_sha256': sha(WT / 'data/features/daily_broad/2026.parquet'), 'recovery': 'complete 28 native chunks retained after bounded final COPY failure; no formula rerun'}
(P / 'current-fundamentals-result.json').write_text(json.dumps(r, indent=2) + '\n')
print(r, flush=True)
