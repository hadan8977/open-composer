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
symbols=sorted(sv.universe_union_symbols(WT/'data/features/universe_broad'))
vf=sv.build_year(2026,universe_symbols=symbols,as_of=date(2026,10,13),memory_limit='250MB')
vout=WT/'data/features/_current_components/short_volume_broad/2026.parquet';vout.parent.mkdir(parents=True,exist_ok=True);vf.to_parquet(vout,index=False)
del vf,symbols
con=duckdb.connect();con.execute("SET threads=1;SET memory_limit='150MB'")
si.PARSED_PATH=P/'normalized-current/short-interest-combined.parquet'
con.execute("COPY (SELECT * FROM read_parquet($1)) TO '"+str(si.PARSED_PATH).replace("'","''")+"' (FORMAT PARQUET)",[str(P/'normalized-current/short-interest-parts/*.parquet')]);con.close()
# Preserve the normal feature cohort (top1000 from original primary universe).
for year in range(2016,2026):
    dest=WT/f'data/features/daily/{year}.parquet'
    if not dest.exists():dest.symlink_to(Path('/root/codex-test/open-composer')/f'data/features/daily/{year}.parquet')
sessions=pd.DatetimeIndex([pd.Timestamp(d)for d in si.us_equity_session_dates(date(2018,1,1),date(2026,10,13))])
universe=si.load_universe_panel(si.UNIVERSE_ROOT)
symbols=set(universe.loc[universe.adv_rank<=1000,'symbol'])
records=si.load_records(symbols=symbols,sessions=sessions,shift_days=0,seed=si.DEFAULT_PLACEBO_SEED)
frame=si.build_year(2026,records=records,sessions=sessions,universe_panel=universe,top_n=1000)
target=WT/'data/features/_current_components/short_interest/2026.parquet';target.parent.mkdir(parents=True,exist_ok=True);frame.to_parquet(target,index=False)
print(json.dumps({'current_FINRA_features_complete':True,'source_requests':0,'cohorts_and_formulas_unchanged':True}),flush=True)
