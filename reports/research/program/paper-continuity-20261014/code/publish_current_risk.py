"""Preserve observed risk checkpoints; original complete-history new suffix only."""
import json
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
from prepare_host_forward_version import sha256, verify_prefix

LIVE = WT / 'data/live/equity_book/risk'
retained = P / 'natural-risk-candidates'
retained.mkdir(exist_ok=True)
for name, keys in [('factor_returns', ['factor', 'trade_date']), ('residuals', ['symbol', 'trade_date']), ('exposures', ['symbol', 'trade_date']), ('cov', ['factor_i', 'factor_j', 'trade_date'])]:
    output = LIVE / f'{name}_2026.parquet'
    candidate = retained / output.name
    assert not candidate.exists()
    output.replace(candidate)
    old = ROOT / 'data/live/equity_book/risk' / output.name
    old_reader = pq.ParquetFile(old)
    schema = old_reader.schema_arrow
    fresh = pq.ParquetFile(candidate)
    assert schema.equals(fresh.schema_arrow)
    cut = pa.scalar('2026-10-07').cast(schema.field('trade_date').type)
    end = pa.scalar('2026-10-13').cast(schema.field('trade_date').type)
    temp = output.with_suffix('.complete.tmp')
    seen = set()
    count = 0
    with pq.ParquetWriter(temp, schema) as writer:
        for batch in old_reader.iter_batches(batch_size=32768, use_threads=False):
            assert not pc.any(pc.greater(batch.column('trade_date'), cut)).as_py()
            writer.write_batch(batch)
        for batch in fresh.iter_batches(batch_size=32768, use_threads=False):
            dates = batch.column('trade_date')
            part = batch.filter(pc.and_(pc.greater(dates, cut), pc.less_equal(dates, end)))
            if not part.num_rows:
                continue
            for key in zip(*(part.column(k).to_pylist() for k in keys), strict=True):
                assert key not in seen
                seen.add(key)
            writer.write_batch(pa.RecordBatch.from_arrays(list(part.columns), schema=schema))
            count += part.num_rows
    assert count > 0
    prefix = verify_prefix(old, temp)
    temp.replace(output)
    r = {'baseline': {'path': str(old), 'sha256': sha256(old)}, 'natural_candidate': {'path': str(candidate), 'sha256': sha256(candidate)}, 'output': {'path': str(output), 'sha256': sha256(output)}, 'prefix_verification': prefix, 'suffix_rows': count, 'key_columns': keys, 'suffix_duplicate_keys': 0, 'prefix_end': '2026-10-07', 'suffix_end': '2026-10-13', 'full_risk_compute_start': '2017-01-01', 'risk_math_or_parameters_changed': False, 'old_partial_week_observations_preserved': True}
    (P / f'compose-current-risk-{name}.json').write_text(json.dumps(r, indent=2) + '\n')
    print({'risk_reader': name, 'prefix_rows': prefix['rows'], 'suffix_rows': count}, flush=True)
