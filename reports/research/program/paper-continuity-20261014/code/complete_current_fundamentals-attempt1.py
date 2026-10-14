"""Bounded exact issuer-source comparison, unchanged original SEC formulas."""
import gc
import hashlib
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
import build_sec_xbrl_fundamentals as f


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    old = ROOT / 'data/features/sec_fundamentals/facts.parquet'
    fresh = f.FACTS_PATH
    original = P / 'fundamental-checkpoints'
    binding = json.loads((original / 'binding.json').read_text())
    assert sha(old) == binding['source_sha256']
    assert sha(Path(f.__file__)) == binding['code_sha256']
    cache = P / 'current-issuer-exact-checkpoints'
    cache.mkdir(exist_ok=True)
    bound = {'old': sha(old), 'new': sha(fresh), 'code': sha(Path(f.__file__))}
    anchor = cache / 'binding.json'
    if anchor.exists():
        assert json.loads(anchor.read_text()) == bound
    else:
        anchor.write_text(json.dumps(bound, indent=2) + '\n')
    con = duckdb.connect()
    con.execute("SET threads=1; SET memory_limit='140MB'; SET max_temp_directory_size='64MB'")
    temp = cache / 'tmp'
    temp.mkdir(exist_ok=True)
    con.execute("SET temp_directory='" + str(temp) + "'")
    current_ciks = list(map(int, con.execute('SELECT DISTINCT cik FROM read_parquet(?) ORDER BY cik', [str(fresh)]).fetchnumpy()['cik']))
    sessions = pd.DatetimeIndex([pd.Timestamp(d) for d in f.us_equity_session_dates(date(2000, 1, 1), date(2026, 10, 13))])
    pos = {d: i for i, d in enumerate(sessions)}
    paths, changed, unchanged = [], [], []
    for start in range(0, len(current_ciks), 200):
        selected = pd.DataFrame({'cik': current_ciks[start:start + 200]})
        con.register('selected', selected)
        # Single-thread scans preserve each issuer's source-row sequence. Equality is
        # stricter than unordered equality: no approximate hash or numeric tolerance.
        new = con.execute('SELECT x.* FROM read_parquet(?) x JOIN selected USING(cik)', [str(fresh)]).fetchdf()
        previous = con.execute('SELECT x.* FROM read_parquet(?) x JOIN selected USING(cik)', [str(old)]).fetchdf()
        old_groups = {int(cik): group.reset_index(drop=True) for cik, group in previous.groupby('cik', sort=False)}
        for cik, group in new.groupby('cik', sort=False):
            cik = int(cik)
            same = cik in old_groups and group.reset_index(drop=True).equals(old_groups[cik])
            prior = original / f'{cik:010d}.parquet'
            prior_empty = original / f'{cik:010d}.empty'
            if same and (prior.exists() or prior_empty.exists()):
                unchanged.append(cik)
                if prior.exists():
                    paths.append(prior)
                continue
            changed.append(cik)
            target = cache / f'{cik:010d}.parquet'
            empty = cache / f'{cik:010d}.empty'
            if not target.exists() and not empty.exists():
                table = f.compute_cik_table(cik, group)
                if not table.empty:
                    events = f.build_all_events({cik: table}, pos)
                    temporary = target.with_suffix('.tmp')
                    events.to_parquet(temporary, index=False)
                    temporary.replace(target)
                else:
                    empty.touch()
            if target.exists():
                paths.append(target)
        del new, previous, old_groups
        gc.collect()
        print(f'issuer exact comparisons {start + len(selected)}/{len(current_ciks)}, changed {len(changed)}', flush=True)
    mapping = f.build_cik_symbol_map(None)
    symbol_to_cik = dict(zip(mapping.symbol, mapping.cik, strict=True))
    # Only one bounded symbol chunk and its own issuer events enter pandas.
    con.execute("CREATE VIEW events AS SELECT * FROM read_parquet(" + repr([str(p) for p in paths]).replace('"', '"') + ")")
    prices = f.DAILY_BROAD_ROOT / '2026.parquet'
    price_sha = sha(prices)
    parts = cache / 'price-parts'
    parts.mkdir(exist_ok=True)
    symbols = sorted(symbol_to_cik)
    total = 0
    for start in range(0, len(symbols), 200):
        assert shutil.disk_usage(P).free > 384 * 1024**2
        selected = pd.DataFrame({'symbol': symbols[start:start + 200]})
        con.register('selected', selected)
        df = con.execute('SELECT x.symbol,x.trade_date FROM read_parquet(?) x JOIN selected USING(symbol)', [str(prices)]).fetchdf()
        ciks = pd.DataFrame({'cik': sorted({symbol_to_cik[s] for s in selected.symbol})})
        con.register('wanted_ciks', ciks)
        events = con.execute('SELECT x.* FROM events x JOIN wanted_ciks USING(cik)').fetchdf()
        frame = f.merge_daily_prices(df, events, symbol_to_cik, pos)
        if not frame.empty:
            frame.to_parquet(parts / f'{start:05d}.parquet', index=False)
            total += len(frame)
        del df, frame, events
        gc.collect()
        print(f'price join {start + len(selected)}/{len(symbols)}, rows {total}', flush=True)
    output = WT / 'data/features/_current_components/sec_fundamentals_daily/2026.parquet'
    output.parent.mkdir(parents=True, exist_ok=True)
    con.execute("COPY (SELECT * FROM read_parquet($1) ORDER BY trade_date,symbol) TO '" + str(output) + "' (FORMAT PARQUET)", [str(parts / '*.parquet')])
    con.close()
    assert sha(fresh) == bound['new'] and sha(prices) == price_sha
    result = {'source_bindings': bound, 'price_sha256': price_sha, 'rows': total, 'output': str(output), 'output_sha256': sha(output), 'changed_CIKs': changed, 'unchanged_CIKs': unchanged, 'checkpoint_reuse': 'all-column pandas exact sequence equality; same original formula code', 'formula_changes': False, 'source_requests': 0}
    (P / 'current-fundamentals-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print({'rows': total, 'changed_CIKs': len(changed), 'unchanged_CIKs': len(unchanged)}, flush=True)


if __name__ == '__main__':
    main()
