"""Private immutable accepted prefixes plus current-vintage original-formula suffixes."""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
from prepare_host_forward_version import compose, sha256

ap = argparse.ArgumentParser()
ap.add_argument('tables', nargs='+')
args = ap.parse_args()
c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='80MB'; SET max_temp_directory_size='32MB'")
for name in args.tables:
    relative = f'data/features/{name}/2026.parquet'
    old = ROOT / relative
    candidate = WT / f'data/features/_current_components/{name}/2026.parquet'
    out = WT / relative
    receipt = P / f'compose-current-{name}.json'
    assert not receipt.exists(), 'consumed publication receipt'
    cutoff = str(c.execute('SELECT max(trade_date)::DATE FROM read_parquet(?)', [str(old)]).fetchone()[0])
    combined = candidate.with_suffix('.forward.parquet')
    result = compose(old, candidate, combined, expected_baseline_sha256=sha256(old), prefix_end=cutoff, suffix_end='2026-10-13', source_manifest=P / 'current-source-request-manifest.json', version_id='paper-continuity-dependencies-forward-20261014')
    out.parent.mkdir(parents=True, exist_ok=True)
    # rename replaces the private symlink itself, never writes through to ROOT.
    combined.replace(out)
    result['output']['path'] = str(out)
    result['private_only'] = True
    result['scope_basis'] = 'Root task.json versioned forward principle; exact old published prefix and old duplicates retained; producer formulas unchanged; whole-history invariance not relabelled'
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print({'table': name, 'prefix_end': cutoff, 'prefix_rows': result['prefix_verification']['rows'], 'suffix_rows': result['suffix_rows']}, flush=True)
c.close()
