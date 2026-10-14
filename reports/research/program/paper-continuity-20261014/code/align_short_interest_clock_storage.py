"""Restore old millisecond date storage only after exact timestamp round trips."""
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
old = pq.ParquetFile(ROOT / 'data/features/short_interest/2026.parquet').schema_arrow
source = WT / 'data/features/_current_components/short_interest/2026.parquet'
retained = source.with_name('2026.original-clock-storage.parquet')
assert not retained.exists()
source.replace(retained)
table = pq.read_table(retained)
aligned = table.cast(old, safe=True)
for field in table.schema:
    restored = pc.cast(aligned[field.name], field.type, safe=True)
    assert restored.equals(table[field.name]), field.name
pq.write_table(aligned, source)
(P / 'short-interest-clock-storage-alignment.json').write_text(json.dumps({'type_change_only': ['settlement_date us to ms', 'publication_date us to ms', 'visible_date us to ms'], 'all_column_exact_roundtrip': True, 'retained_original': str(retained), 'aligned': str(source), 'rows': len(table), 'date_or_visibility_value_change': False}, indent=2) + '\n')
print({'rows': len(table), 'all_column_exact_roundtrip': True}, flush=True)
