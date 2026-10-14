import json
import sys
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
from prepare_host_forward_version import compose, sha256

old = ROOT / 'data/features/nsi/nsi.parquet'
candidate = WT / 'data/features/_current_components/nsi/nsi.parquet'
schema = pq.ParquetFile(old).schema_arrow
reader = pq.ParquetFile(candidate)
if not reader.schema_arrow.equals(schema):
    aligned = candidate.with_name('nsi.clock-aligned.parquet')
    with pq.ParquetWriter(aligned, schema) as writer:
        for batch in reader.iter_batches(batch_size=32768, use_threads=False):
            table = batch.cast(schema, safe=True)
            for field in batch.schema:
                assert pc.cast(table.column(field.name), field.type, safe=True).equals(batch.column(field.name))
            writer.write_batch(table)
    candidate = aligned
output = WT / 'data/features/nsi/nsi.parquet'
temporary = output.with_name('nsi.forward-complete.parquet')
import duckdb
c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='80MB'")
cut = str(c.execute('SELECT max(trade_date)::DATE FROM read_parquet(?)', [str(old)]).fetchone()[0])
c.close()
r = compose(old, candidate, temporary, expected_baseline_sha256=sha256(old), prefix_end=cut, suffix_end='2026-10-13', source_manifest=P / 'current-feature-input-manifest.json', version_id='paper-continuity-dependencies-forward-20261014')
temporary.replace(output)
r['output']['path'] = str(output)
(P / 'compose-current-nsi.json').write_text(json.dumps(r, indent=2) + '\n')
print({'prefix_rows': r['prefix_verification']['rows'], 'suffix_rows': r['suffix_rows']}, flush=True)
