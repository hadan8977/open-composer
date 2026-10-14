"""Private bounded execution of unchanged cached SEC issuer calculations."""
from __future__ import annotations

import gc
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

WT = Path('/root/codex-test/wt-paper-continuity-20261014')
OUT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
import build_sec_xbrl_fundamentals as f


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    cache = OUT / 'fundamental-checkpoints'
    cache.mkdir(exist_ok=True)
    source_sha = sha(f.FACTS_PATH)
    code_sha = sha(Path(f.__file__))
    binding = {'source_sha256': source_sha, 'code_sha256': code_sha}
    anchor = cache / 'binding.json'
    if anchor.exists():
        assert json.loads(anchor.read_text()) == binding
    else:
        anchor.write_text(json.dumps(binding, indent=2) + '\n')
    mapping = f.build_cik_symbol_map(None)
    symbol_to_cik = dict(zip(mapping.symbol, mapping.cik, strict=True))
    sessions = pd.DatetimeIndex([pd.Timestamp(d) for d in f.us_equity_session_dates(date(2000, 1, 1), date(2026, 10, 13))])
    session_pos = {d: i for i, d in enumerate(sessions)}
    facts = pd.read_parquet(f.FACTS_PATH)
    paths = []
    for i, (cik, group) in enumerate(facts.groupby('cik')):
        path = cache / f'{int(cik):010d}.parquet'
        if not path.exists() and not (cache / f'{int(cik):010d}.empty').exists():
            table = f.compute_cik_table(int(cik), group)
            if not table.empty:
                events = f.build_all_events({int(cik): table}, session_pos)
                tmp = path.with_suffix('.parquet.tmp')
                events.to_parquet(tmp, index=False)
                tmp.replace(path)
            else:
                (cache / f'{int(cik):010d}.empty').touch()
        if path.exists():
            paths.append(path)
        if (i + 1) % 500 == 0:
            print(f'issuer checkpoints {i + 1}, nonempty {len(paths)}', flush=True)
    del facts
    gc.collect()
    con = duckdb.connect()
    con.execute("SET threads=1; SET memory_limit='150MB'")
    events = con.execute('SELECT * FROM read_parquet(?)', [[str(path) for path in paths]]).fetchdf()
    f.log(f'bounded cached events: {len(events)} rows from {len(paths)} issuers')
    price_path = f.DAILY_BROAD_ROOT / '2026.parquet'
    price_sha = sha(price_path)
    parts = cache / 'price-parts'
    parts.mkdir(exist_ok=True)
    symbols = sorted(symbol_to_cik)
    total = 0
    for i in range(0, len(symbols), 200):
        selected = pd.DataFrame({'symbol': symbols[i:i + 200]})
        con.register('selected', selected)
        price = con.execute('SELECT p.symbol,p.trade_date FROM read_parquet(?) p JOIN selected s USING(symbol)', [str(price_path)]).fetchdf()
        frame = f.merge_daily_prices(price, events, symbol_to_cik, session_pos)
        if frame.empty:
            continue
        frame.to_parquet(parts / f'{i:05d}.parquet', index=False)
        total += len(frame)
        del frame, price
        gc.collect()
        print(f'price chunk {i + len(selected)}/{len(symbols)}, rows {total}', flush=True)
    target = f.DAILY_ROOT / '2026.parquet'
    temporary = target.with_suffix('.parquet.bounded.tmp')
    con.execute("COPY (SELECT * FROM read_parquet($1) ORDER BY trade_date,symbol) TO "
                + "'" + str(temporary).replace("'", "''") + "' (FORMAT PARQUET)", [str(parts / '*.parquet')])
    assert sha(price_path) == price_sha and sha(f.FACTS_PATH) == source_sha
    con.close()
    temporary.replace(target)
    result = {**binding, 'price_sha256': price_sha, 'rows': total, 'issuer_event_files': len(paths), 'output': str(target), 'output_sha256': sha(target), 'asof': '2026-10-13', 'current_fetched_at': datetime.now(UTC).isoformat(), 'new_source_requests': 0, 'formula_change': False, 'cache_source_claim': 'Existing cached facts only; no claim of new SEC filings acquisition.'}
    (OUT / 'fundamental-current-bounded-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
