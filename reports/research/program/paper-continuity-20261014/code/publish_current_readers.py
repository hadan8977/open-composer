"""Private accepted reader prefix plus explicitly current new-session rows."""
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
from prepare_host_forward_version import compose, sha256

c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='80MB'; SET max_temp_directory_size='32MB'")
for name, relative in [('panel', 'panel/2026.parquet'), ('prices', 'prices/2026.parquet'), ('etf', 'etf_daily.parquet')]:
    source = ROOT / 'data/live/equity_book' / relative
    output = WT / 'data/live/equity_book' / relative
    retained = output.with_name(output.stem + '.current-natural.parquet')
    assert not retained.exists()
    output.replace(retained)
    cutoff = str(c.execute('SELECT max(trade_date)::DATE FROM read_parquet(?)', [str(source)]).fetchone()[0])
    r = compose(source, retained, output, expected_baseline_sha256=sha256(source), prefix_end=cutoff, suffix_end='2026-10-13', source_manifest=P / 'current-feature-input-manifest.json', version_id='paper-continuity-reader-forward-20261014')
    r['scope'] = 'immutable published reader history retained; new-session natural original producer rows only; no historical order/fill rewrite'
    (P / f'compose-current-reader-{name}.json').write_text(json.dumps(r, indent=2) + '\n')
    print({'reader': name, 'prefix_rows': r['prefix_verification']['rows'], 'suffix_rows': r['suffix_rows']}, flush=True)
c.close()
