"""Bounded existing input clocks, separate from generated feature-grid dates."""
import hashlib
import json
from pathlib import Path

import duckdb

ROOT = Path.cwd()
OUT = ROOT / 'reports/research/program/paper-continuity-20261014'
con = duckdb.connect()
con.execute("SET threads=1; SET memory_limit='180MB'")
items = []
for relative in ['data/features/sec_fundamentals/facts.parquet', 'data/raw/finra_short_interest/parsed.parquet', 'data/raw/finra_short_volume/parsed.parquet', 'data/raw/insider/tail/parsed/*.parquet', 'data/features/news_packets/2026.parquet']:
    paths = sorted(ROOT.glob(relative))
    if not paths:
        items.append({'path': relative, 'status': 'not_at_this_path'})
        continue
    names = [str(p) for p in paths]
    schema = con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [names]).fetchall()
    clocks = [name for name, kind, *_ in schema if name in ('filed', 'filing_date', 'visible_date', 'visible_at', 'publication_date', 'trade_date', 'settlement_date', 'created_at', 'updated_at', 'usable_session', 'fetched_at')]
    counts = con.execute('SELECT COUNT(*) FROM read_parquet(?)', [names]).fetchone()[0]
    values = {}
    for name in clocks:
        row = con.execute(f'SELECT MIN("{name}"),MAX("{name}") FROM read_parquet(?)', [names]).fetchone()
        values[name] = [str(v) if v is not None else None for v in row]
    bindings = []
    for path in paths:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        bindings.append({'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest})
    items.append({'source_pattern': relative, 'rows': counts, 'schema': schema, 'clocks': values, 'bindings': bindings})
con.close()
index = ROOT / 'data/features/news_attention/_articles_index.json'
payload = {'sources': items, 'news_articles_index': json.loads(index.read_text()) if index.exists() else None, 'new_source_requests': 0, 'sourceclock_is_not_generated_grid_date': True}
(OUT / 'cached-dependency-source-clocks.json').write_text(json.dumps(payload, indent=2) + '\n')
print(json.dumps({'sources': [{k: v for k,v in item.items() if k not in ('schema','bindings')} for item in items], 'news_index_keys': list(payload['news_articles_index'] or {})}))
