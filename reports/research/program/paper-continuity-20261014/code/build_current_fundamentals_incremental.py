"""Original issuer formulas; reuse exact unchanged source groups' checkpoints."""
import gc
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT=Path(__file__).resolve().parents[5];WT=Path('/root/codex-test/wt-paper-continuity-20261014');P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WT/'scripts'))
import build_sec_xbrl_fundamentals as f

def sha(path):
    with path.open('rb')as s:return hashlib.file_digest(s,'sha256').hexdigest()

def main():
    oldfacts=ROOT/'data/features/sec_fundamentals/facts.parquet';newfacts=f.FACTS_PATH
    assert not newfacts.is_symlink() and newfacts.exists()
    original=P/'fundamental-checkpoints';binding=json.loads((original/'binding.json').read_text())
    assert sha(oldfacts)==binding['source_sha256'] and sha(Path(f.__file__))==binding['code_sha256']
    con=duckdb.connect();con.execute("SET threads=1;SET memory_limit='180MB'")
    con.execute("CREATE VIEW oldfacts AS SELECT * FROM read_parquet('"+str(oldfacts).replace("'","''")+"')")
    con.execute("CREATE VIEW newfacts AS SELECT * FROM read_parquet('"+str(newfacts).replace("'","''")+"')")
    changed=con.execute('SELECT DISTINCT cik FROM ((SELECT * FROM newfacts EXCEPT ALL SELECT * FROM oldfacts) UNION ALL (SELECT * FROM oldfacts EXCEPT ALL SELECT * FROM newfacts)) ORDER BY cik').fetchdf()
    con.register('changed',changed)
    current=con.execute('SELECT f.* FROM newfacts f JOIN changed c USING(cik) ORDER BY cik').fetchdf()
    mapping=f.build_cik_symbol_map(None);symbol_to_cik=dict(zip(mapping.symbol,mapping.cik,strict=True))
    sessions=pd.DatetimeIndex([pd.Timestamp(d)for d in f.us_equity_session_dates(date(2000,1,1),date(2026,10,13))]);position={d:i for i,d in enumerate(sessions)}
    fresh=P/'current-issuer-event-checkpoints';fresh.mkdir(exist_ok=True)
    paths=[];modified=set(map(int,changed.cik));existing=set(con.execute('SELECT DISTINCT cik FROM newfacts').fetchnumpy()['cik'])
    for i,(cik,group)in enumerate(current.groupby('cik')):
        table=f.compute_cik_table(int(cik),group)
        if not table.empty:
            events=f.build_all_events({int(cik):table},position)
            path=fresh/f'{int(cik):010d}.parquet';events.to_parquet(path,index=False);paths.append(path)
        if (i+1)%100==0:print(f'changed issuer formulas {i+1}/{len(changed)}',flush=True)
    for path in original.glob('[0-9]*.parquet'):
        cik=int(path.stem)
        if cik in existing and cik not in modified:paths.append(path)
    del current;gc.collect()
    events=con.execute('SELECT * FROM read_parquet(?)',[[str(p)for p in paths]]).fetchdf()
    price=f.DAILY_BROAD_ROOT/'2026.parquet';parts=fresh/'price-chunks';parts.mkdir(exist_ok=True);total=0
    symbols=sorted(symbol_to_cik)
    for i in range(0,len(symbols),200):
        selected=pd.DataFrame({'symbol':symbols[i:i+200]});con.register('selected',selected)
        df=con.execute('SELECT p.symbol,p.trade_date FROM read_parquet(?) p JOIN selected s USING(symbol)',[str(price)]).fetchdf()
        frame=f.merge_daily_prices(df,events,symbol_to_cik,position)
        if len(frame):frame.to_parquet(parts/f'{i:05d}.parquet',index=False);total+=len(frame)
        del df,frame;gc.collect()
    output=f.DAILY_ROOT/'2026.parquet';tmp=output.with_suffix('.parquet.current.tmp')
    con.execute("COPY (SELECT * FROM read_parquet($1) ORDER BY trade_date,symbol) TO '"+str(tmp).replace("'","''")+"' (FORMAT PARQUET)",[str(parts/'*.parquet')]);con.close();tmp.replace(output)
    r={'output':str(output),'sha256':sha(output),'rows':total,'source_facts_sha256':sha(newfacts),'baseline_facts_sha256':binding['source_sha256'],'changed_CIKs':sorted(modified),'unchanged_CIK_checkpoint_reuse':'all-column typed semantic multiset equality via EXCEPT ALL; same original formula code SHA; not a physical file/float-bit identity claim','new_source_requests':0,'formula_changes':False,'source_vintage':'current SEC bulk retained in current-companyfacts-bulk/ledger.json'}
    (P/'current-fundamentals-result.json').write_text(json.dumps(r,indent=2)+'\n');print({'rows':total,'changed_CIKs':len(modified),'output_sha256':r['sha256']},flush=True)

if __name__=='__main__':main()
