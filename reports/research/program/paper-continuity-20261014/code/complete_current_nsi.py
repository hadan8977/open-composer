"""Same original full-calendar NSI calculations, independent symbol partitions."""
import gc
import importlib.util
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('nsi_builder', WT / 'scripts/build_nsi_signal.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='120MB'; SET max_temp_directory_size='64MB'")
symbols = pd.Index(c.execute(f"SELECT DISTINCT symbol FROM read_parquet('{m.FEATURES}/universe_broad/*.parquet') WHERE adv_rank<=3000 AND close>=5 ORDER BY symbol").fetchdf().symbol)
dates = pd.DatetimeIndex(c.execute(f"SELECT DISTINCT trade_date FROM read_parquet('{m.FEATURES}/daily_broad/*.parquet') ORDER BY 1").fetchdf().trade_date)
c.register('days', pd.DataFrame({'trade_date': dates, 'tid': np.arange(len(dates))}))
out = WT / 'data/features/_current_components/nsi/nsi.parquet'
out.parent.mkdir(parents=True, exist_ok=True)
assert not out.exists(), 'consumed output'
writer = None
total = 0
counts = {252: {}, 126: {}}
for start in range(0, len(symbols), 180):
    selected = symbols[start:start + 180]
    c.register('syms', pd.DataFrame({'symbol': selected, 'sid': np.arange(len(selected))}))
    px = c.execute(f"SELECT d.tid,s.sid,CAST(p.close AS FLOAT) AS close FROM read_parquet('{m.FEATURES}/daily_broad/*.parquet') p JOIN syms s USING(symbol) JOIN days d USING(trade_date)").fetchnumpy()
    close = np.full((len(dates), len(selected)), np.nan, dtype=np.float32)
    close[px['tid'], px['sid']] = px['close']
    del px
    sanitized, opened, report = m.sanitize_price_matrices(pd.DataFrame(close, index=dates, columns=selected))
    del sanitized, opened, close
    breaks = np.zeros((len(dates), len(selected)), dtype=bool)
    for br in report.breaks:
        if br.symbol in selected:
            lo = dates.searchsorted(br.last_session_before)
            hi = dates.searchsorted(br.first_session_after)
            breaks[lo + 1:hi + 1, selected.get_loc(br.symbol)] = True
    raw = c.execute(f"SELECT d.tid,s.sid,q.shares_outstanding AS sh FROM read_parquet('{m.FEATURES}/sec_fundamentals_daily/*.parquet') q JOIN syms s USING(symbol) JOIN days d ON d.trade_date=CAST(q.trade_date AS TIMESTAMP) WHERE q.shares_outstanding IS NOT NULL").fetchnumpy()
    shares = np.full((len(dates), len(selected)), np.nan, dtype=np.float64)
    shares[raw['tid'], raw['sid']] = raw['sh']
    del raw
    shares = m._ffill_limited(shares, m.FFILL_LIMIT)
    signals = {}
    for lag in (252, 126):
        signals[lag], dropped = m.clean_pairs(shares, breaks, lag)
        for k, v in dropped.items():
            counts[lag][k] = counts[lag].get(k, 0) + int(v)
    good = np.isfinite(signals[252]) | np.isfinite(signals[126])
    ti, si = np.nonzero(good)
    frame = pd.DataFrame({'symbol': selected[si], 'trade_date': dates[ti], 'nsi252': signals[252][ti, si], 'nsi126': signals[126][ti, si]})
    table = pa.Table.from_pandas(frame, preserve_index=False)
    if writer is None:
        writer = pq.ParquetWriter(out, table.schema)
    writer.write_table(table)
    total += len(frame)
    del frame, signals, shares, breaks, table
    gc.collect()
    print(f'original NSI partition {start + len(selected)}/{len(symbols)}, rows {total}', flush=True)
if writer:
    writer.close()
c.close()
r = {'rows': total, 'output': str(out), 'calendar_start': str(dates[0]), 'calendar_end': str(dates[-1]), 'lags': [252, 126], 'drop_counts': counts, 'formula_changes': False, 'source_requests': 0, 'hygiene': 'original defaults per symbol; full common session calendar retained'}
(P / 'current-nsi-result.json').write_text(json.dumps(r, indent=2) + '\n')
print(r, flush=True)
