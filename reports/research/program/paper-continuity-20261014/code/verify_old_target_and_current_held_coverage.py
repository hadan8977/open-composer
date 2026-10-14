"""Actual target and held-price facts; no orders, strategy returns or historical fills."""
import json
import os
import sys
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
os.environ['OC_EQUITY_BOOK_DIR'] = str(WT / 'data/live/equity_book')
sys.path.insert(0, str(WT))
from open_composer.book_paper import v12_targets as v12
from open_composer.book_paper.targets import load_target_file

old = load_target_file(ROOT / 'reports/paper/book/quant1/targets/2026-10-07.json')
bundle = v12.build_v12_bundle(date(2026, 10, 7), variant=v12.primary_variant(), data_root=WT / 'data/live/equity_book', logged_at_utc='2026-10-14T00:00:00Z')
rebuilt = bundle.targets['quant1']
a = pd.Series(old.weights, dtype=float)
b = pd.Series(rebuilt.weights, dtype=float)
symbols = a.index.union(b.index)
a, b = a.reindex(symbols, fill_value=0), b.reindex(symbols, fill_value=0)
report = {'old_decision': '2026-10-07', 'old_target_path': str(ROOT / 'reports/paper/book/quant1/targets/2026-10-07.json'), 'names_old': len(old.weights), 'names_rebuilt': len(rebuilt.weights), 'weight_correlation': float(a.corr(b)), 'max_abs_weight_difference': float((a-b).abs().max()), 'gross_weight_difference': float(abs(a.abs().sum()-b.abs().sum())), 'historical_target_written': False, 'actual_historical_orders_reconstructed': False}
snapshot = json.loads((P / 'account-snapshot.json').read_text())
held = pd.DataFrame({'symbol': [r['symbol'] for r in snapshot['positions']]})
c = duckdb.connect()
c.execute("SET threads=1; SET memory_limit='160MB'; SET max_temp_directory_size='64MB'")
c.register('held', held)
prices = c.execute("SELECT h.symbol,p.close FROM held h LEFT JOIN (SELECT symbol,close FROM read_parquet(?) WHERE trade_date::DATE=DATE '2026-10-13' UNION ALL SELECT symbol,close FROM read_parquet(?) WHERE trade_date::DATE=DATE '2026-10-13') p USING(symbol)", [str(WT / 'data/live/equity_book/prices/2026.parquet'), str(WT / 'data/live/equity_book/etf_daily.parquet')]).fetchdf()
duplicates = prices.loc[prices.symbol.duplicated(False), 'symbol'].unique().tolist()
missing = prices.loc[~(prices.close > 0), 'symbol'].tolist()
report['held_price_coverage'] = {'held_names': len(held), 'covered_unique_names': int(prices.loc[prices.close>0,'symbol'].nunique()), 'missing_names': missing, 'duplicate_join_names': duplicates, 'broker_observed_valuation_remains_available_for_missing_daily_names': True}
(P / 'actual-target-parity-and-held-coverage.json').write_text(json.dumps(report, indent=2) + '\n')
print(report, flush=True)
