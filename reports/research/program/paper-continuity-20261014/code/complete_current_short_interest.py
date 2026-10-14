"""Original FINRA features, bounded source projection only; complete carry-in."""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('si_builder', WT / 'scripts/build_short_interest_features.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
universe = m.load_universe_panel(m.UNIVERSE_ROOT)
symbols = set(universe.loc[universe.adv_rank <= 1000, 'symbol'])
c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='100MB'; SET max_temp_directory_size='32MB'")
c.register('wanted', pd.DataFrame({'symbol': sorted(symbols)}))
source = P / 'normalized-current/short-interest-combined.parquet'
projection = P / 'normalized-current/short-interest-feature-projection.parquet'
cols = ','.join('x.' + name for name in m.READ_COLUMNS)
c.execute("COPY (SELECT " + cols + " FROM read_parquet($1) x JOIN wanted USING(symbol)) TO '" + str(projection) + "' (FORMAT PARQUET)", [str(source)])
c.close()
m.PARSED_PATH = projection
sessions = pd.DatetimeIndex([pd.Timestamp(d) for d in m.us_equity_session_dates(date(2018, 1, 1), date(2026, 10, 13))])
records = m.load_records(symbols=symbols, sessions=sessions, shift_days=0, seed=m.DEFAULT_PLACEBO_SEED)
frame = m.build_year(2026, records=records, sessions=sessions, universe_panel=universe, top_n=1000)
out = WT / 'data/features/_current_components/short_interest/2026.parquet'
out.parent.mkdir(parents=True, exist_ok=True)
frame.to_parquet(out, index=False)
result = {'rows': len(frame), 'max_trade_date': str(frame.trade_date.max()), 'max_source_settlement': str(records.settlement_date.max()), 'max_visible_date': str(records.visible_date.max()), 'formulas_changed': False, 'calendar_start': '2018-01-01', 'source_requests': 0, 'output': str(out)}
(P / 'current-short-interest-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(result, flush=True)
