"""Actual original consumer hygiene; prior-reader equivalence is checked, not assumed."""
import importlib.util
import json
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
os.environ['OC_EQUITY_BOOK_DIR'] = str(WT / 'data/live/equity_book')
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('panel_builder', WT / 'scripts/build_equity_book_panel.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
def bounded(mem='300MB'):
    c = duckdb.connect()
    c.execute("SET threads=1; SET memory_limit='240MB'; SET max_temp_directory_size='128MB'; SET TimeZone='UTC'")
    return c
m._duck = bounded
for name in ('_calendar.parquet', '_hygiene.parquet', '_manifest.json'):
    target = m.PANEL_DIR / name
    if target.is_symlink():
        target.unlink()
result = m.stage_hygiene(chunk=180)
current = pd.read_parquet(m.PANEL_DIR / '_hygiene.parquet').set_index('symbol')
old = pd.read_parquet(ROOT / 'data/live/equity_book/panel/_hygiene.parquet').set_index('symbol')
joined = current.join(old, lsuffix='_new', rsuffix='_old', how='outer')
changed = []
for symbol, row in joined.iterrows():
    for name in ('cutoff_date', 'first_valid_date', 'first_valid_pos'):
        a, b = row[name + '_new'], row[name + '_old']
        if pd.isna(a) and pd.isna(b):
            continue
        if a != b:
            changed.append(str(symbol))
            break
cal = pd.read_parquet(m.PANEL_DIR / '_calendar.parquet')
before = pd.read_parquet(ROOT / 'data/live/equity_book/panel/_calendar.parquet')
prefix_equal = cal.iloc[:len(before)].reset_index(drop=True).equals(before.reset_index(drop=True))
c = bounded()
coverage = {}
for name in ('universe', 'universe_broad'):
    coverage[name] = str(c.execute('SELECT max(month_end)::DATE FROM read_parquet(?)', [str(WT / f'data/features/{name}/2026.parquet')]).fetchone()[0])
c.close()
report = {'hygiene': result, 'changed_symbols': changed, 'hygiene_fields_same_for_shared_names': not changed, 'calendar_prefix_exact': prefix_equal, 'calendar_max': str(cal.trade_date.max()), 'monthly_cohort_max': coverage, 'shared_writes': 0}
(P / 'private-hygiene-and-calendar-result.json').write_text(json.dumps(report, indent=2) + '\n')
print(report, flush=True)
