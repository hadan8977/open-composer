"""Full original insider history, bounded issuer-local output partitions."""
import gc
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('insider_builder', WT / 'scripts/build_insider_features.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
ledger = json.loads((P / 'current-insider-tail-continuation/ledger.json').read_text())
assert ledger['all_original_requests_attempted'] and not ledger['ownership_component_missing_ordinals']
view = P / 'current-insider-source-view'
view.mkdir(exist_ok=True)
for old in (ROOT / 'data/raw/insider/tail/parsed').glob('*.parquet'):
    target = view / old.name
    if not target.exists():
        target.symlink_to(old)
for fresh in (P / 'current-insider-tail-continuation/parsed').glob('*.parquet'):
    target = view / fresh.name
    if target.exists():
        assert target.resolve() == fresh.resolve()
    else:
        target.symlink_to(fresh)
m.TAIL_PARSED_ROOT = view
sessions, positions = m.build_session_index(date(2016, 1, 1), date(2026, 10, 13))
universe = m.load_universe_panel(WT / 'data/features/universe_broad')
dates = sessions[sessions.year == 2026]
symbols = sorted(set().union(*(m.universe_as_of_calendar_month(universe, d, top_n=1000000) for d in dates)))
out = WT / 'data/features/_current_components/insider_broad/2026.parquet'
out.parent.mkdir(parents=True, exist_ok=True)
parts = out.parent / 'native-parts'
parts.mkdir(exist_ok=True)
completed = set()
if out.exists():
    existing = pq.read_table(out, columns=['symbol'])
    completed = set(existing['symbol'].to_pylist())
    assert completed == set(symbols[:len(completed)])
    retained = parts / f'prefix-{len(completed):05d}.parquet'
    assert not retained.exists()
    out.replace(retained)
else:
    for piece in parts.glob('*.parquet'):
        completed.update(pq.read_table(piece, columns=['symbol'])['symbol'].to_pylist())
    assert completed == set(symbols[:len(completed)])
total = sum(pq.ParquetFile(piece).metadata.num_rows for piece in parts.glob('*.parquet'))
for start in range(len(completed), len(symbols), 180):
    selected = set(symbols[start:start + 180])
    try:
        transactions = m.load_transactions(symbols=selected)
    except ValueError as error:
        if str(error) != 'No objects to concatenate':
            raise
        transactions = m.pd.DataFrame(columns=list(m.READ_COLUMNS))
        transactions['trans_code'] = transactions['trans_code'].astype('string')
        transactions['acquired_disposed'] = transactions['acquired_disposed'].astype('string')
        transactions['owner_cik'] = m.pd.Series(dtype='Int64')
        transactions = transactions.drop(columns=['reporting_owner_cik','document_type'])
    transactions = m.attach_visible_index(transactions, positions, shift_days=0, seed=m.DEFAULT_PLACEBO_SEED)
    transactions = m.classify_transactions(transactions)
    transactions = m.pd.concat([transactions, m.label_buy_routineness(transactions)], axis=1)
    transactions = transactions.drop(columns=['accession', 'trans_code', 'acquired_disposed', 'shares', 'price_per_share', 'is_director', 'is_officer', 'is_ten_percent_owner', 'is_10b5_1'])
    frame = m.build_year(2026, transactions=transactions, sessions=sessions, universe_panel=universe, top_n=1000000, output_symbols=selected)
    if not frame.empty:
        table = pa.Table.from_pandas(frame, preserve_index=False)
        target = parts / f'{start:05d}.parquet'
        assert not target.exists()
        temporary = target.with_suffix('.tmp')
        pq.write_table(table, temporary, compression='zstd')
        temporary.replace(target)
        total += len(frame)
    del transactions, frame
    gc.collect()
    print(f'original insider partition {start + len(selected)}/{len(symbols)}, rows {total}', flush=True)
writer = None
for piece in sorted(parts.glob('*.parquet')):
    parquet = pq.ParquetFile(piece)
    if writer is None:
        writer = pq.ParquetWriter(out, parquet.schema_arrow, compression='zstd')
    for batch in parquet.iter_batches(batch_size=32768, use_threads=False):
        writer.write_batch(batch)
if writer is not None:
    writer.close()
r = {'rows': total, 'output': str(out), 'asof': '2026-10-13', 'calendar_start': '2016-01-01', 'normal_cohort_guard_evaluated_before_partition': True, 'partition_rule': 'issuer-local symbols only, full owner/issuer routine and CMP history retained', 'new_source_requests': 0, 'formula_changes': False}
(P / 'current-insider-features-result.json').write_text(json.dumps(r, indent=2) + '\n')
print(r, flush=True)
