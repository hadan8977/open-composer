"""Original native readers, explicit private output and bounded working memory."""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import duckdb

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
LIVE = WT / 'data/live/equity_book'
os.environ['OC_EQUITY_BOOK_DIR'] = str(LIVE)
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / 'scripts'))


def module(name):
    spec = importlib.util.spec_from_file_location(name, WT / 'scripts' / (name + '.py'))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def bounded(mem='280MB'):
    c = duckdb.connect()
    c.execute("SET threads=1; SET memory_limit='280MB'; SET max_temp_directory_size='128MB'; SET TimeZone='UTC'")
    return c


def readonly_prior(directory, names):
    directory.mkdir(parents=True, exist_ok=True)
    for old in names:
        target = directory / old.name
        if not target.exists():
            target.symlink_to(old)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['panel_prices', 'risk', 'signals', 'alpha'])
    args = ap.parse_args()
    if args.stage == 'panel_prices':
        m = module('build_equity_book_panel')
        m._duck = bounded
        readonly_prior(LIVE / 'prices', [p for p in (ROOT / 'data/live/equity_book/prices').glob('20*.parquet') if int(p.stem) < 2026])
        result = {'panel': m.stage_panel([2026]), 'prices': m.stage_prices([2026]), 'etf': m.stage_etf(), 'prior_reader_versions_retained': True}
        (P / 'private-panel-prices-result.json').write_text(json.dumps(result, indent=2) + '\n')
    elif args.stage == 'risk':
        m = module('build_equity_book_risk')
        m._duck = bounded
        mapping, groups, members = m.group_table(bounded())
        old_meta = json.loads((ROOT / 'data/live/equity_book/risk/meta.json').read_text())
        assert old_meta['ff48_to_group'] == {str(k): v for k, v in mapping.items()}, 'old/new factor basis differs; cannot mix prior risk artifacts'
        assert old_meta['groups'] == groups
        readonly_prior(LIVE / 'risk', [p for p in (ROOT / 'data/live/equity_book/risk').glob('*.parquet') if not p.name.endswith('_2026.parquet')])
        sys.argv = ['risk', '--start', '2017-01-01', '--end', '2026-10-13', '--out', str(LIVE / 'risk'), '--write-from-year', '2026']
        m.main()
    elif args.stage == 'signals':
        m = module('build_equity_book_signals')
        m._duck = bounded
        m.stage_build([2026], 1, False)
    else:
        m = module('build_book_v1_alpha')
        sys.argv = ['alpha']
        m.main()


if __name__ == '__main__':
    main()
