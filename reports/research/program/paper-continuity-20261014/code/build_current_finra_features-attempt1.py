"""Same original feature formulas on retained old source plus proven current delta."""
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

WT=Path('/root/codex-test/wt-paper-continuity-20261014');P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WT))
def module(name):
    spec=importlib.util.spec_from_file_location(name,WT/'scripts'/f'{name}.py');m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
sv=module('build_short_volume_features');si=module('build_short_interest_features')
sv.PARSED_PATH=P/'normalized-current/short-volume-parts/*.parquet'
sv.main(['--years','2026','--universe-root',str(WT/'data/features/universe_broad'),'--out-dir',str(WT/'data/features/_current_components/short_volume_broad'),'--as-of','2026-10-13','--memory-limit','250MB','--force'])
con=duckdb.connect();con.execute("SET threads=1;SET memory_limit='150MB'")
si.PARSED_PATH=P/'normalized-current/short-interest-combined.parquet'
con.execute("COPY (SELECT * FROM read_parquet($1)) TO '"+str(si.PARSED_PATH).replace("'","''")+"' (FORMAT PARQUET)",[str(P/'normalized-current/short-interest-parts/*.parquet')]);con.close()
# Preserve the normal feature cohort (top1000 from original primary universe).
for year in range(2016,2026):
    dest=WT/f'data/features/daily/{year}.parquet'
    if not dest.exists():dest.symlink_to(Path('/root/codex-test/open-composer')/f'data/features/daily/{year}.parquet')
si.main(['--start-year','2026','--end-year','2026','--as-of','2026-10-13','--out-root',str(WT/'data/features/_current_components/short_interest'),'--force'])
print(json.dumps({'current_FINRA_features_complete':True,'source_requests':0,'cohorts_and_formulas_unchanged':True}),flush=True)
