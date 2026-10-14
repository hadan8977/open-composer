"""Normalize retained current entities using original parsers; no source requests."""
import gzip
import json
import sys
from datetime import UTC,datetime,date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path.cwd();WT=Path('/root/codex-test/wt-paper-continuity-20261014');P=ROOT/'reports/research/program/paper-continuity-20261014'
sys.path.insert(0,str(ROOT/'scripts'))
import collect_finra_short_volume as sv
import collect_finra_short_interest as si
from open_composer.research.news import collector as news

out=P/'normalized-current';out.mkdir(exist_ok=True)
rows=json.loads((P/'current-source-intake/ledger.json').read_text())['requests']+json.loads((P/'current-source-continuation/ledger.json').read_text())['requests']
def blob(row):
    import hashlib
    payload=Path(row['entity_path']).read_bytes()
    assert hashlib.sha256(payload).hexdigest()==row['entity_sha256'] and row['complete'] and row['http_status']==200
    return payload

vol=out/'volume';vol.mkdir(exist_ok=True)
for row in rows:
    if row['label'].startswith('finra-volume-'):
        stamp=row['label'].split('-')[-1];day=date(int(stamp[:4]),int(stamp[4:6]),int(stamp[6:]))
        path=vol/(day.isoformat()+'.txt.gz')
        with gzip.open(path,'wb')as stream:stream.write(blob(row))
vparts=out/'short-volume-parts';vparts.mkdir(exist_ok=True)
(vparts/'old-parsed.parquet').symlink_to(ROOT/'data/raw/finra_short_volume/parsed.parquet')
vframes=[]
paths=sorted((ROOT/'data/raw/finra_short_volume/cnms').glob('2026-10-*.txt.gz'))+sorted(vol.glob('*.txt.gz'))
for path in paths:
    day=date.fromisoformat(path.name[:10])
    if day<=date(2026,10,1):continue
    assert sv._raw_row_count(path)>=0,'missing or truncated CNMS trailer'
    vframes.append(sv.parse_raw_file(path))
vf=pd.concat(vframes,ignore_index=True);assert not vf.duplicated(['trade_date','symbol']).any()
vf.to_parquet(vparts/'delta.parquet',index=False)

iparts=out/'short-interest-parts';iparts.mkdir(exist_ok=True)
(iparts/'old-parsed.parquet').symlink_to(ROOT/'data/raw/finra_short_interest/parsed.parquet')
pages=[r for r in rows if r['label'].startswith('finra-interest-') and r['label']!='finra-interest-probe']
text=None;body=[]
for row in pages:
    lines=blob(row).decode().splitlines()
    if text is None:text=lines[0]
    else:assert lines[0]==text
    body.extend(lines[1:])
expected=json.loads((P/'current-source-intake/ledger.json').read_text())['finra_interest_expected_records']
assert len(body)==expected
ipath=out/'2026-09-30.csv.gz'
with gzip.open(ipath,'wt')as stream:stream.write(text+'\n'+'\n'.join(body)+'\n')
schedule,_=si.load_schedule()
ix=si.parse_raw_file(ipath,publication_schedule=schedule,lag_sessions=7)
ix.to_parquet(iparts/'delta.parquet',index=False)

nroot=WT/'data/features/news_packets';nroot.mkdir(exist_ok=True)
packets=[]
for row in rows:
    if row['label'].startswith('news-'):
        data=json.loads(blob(row));fetched=datetime.fromisoformat(row['attempted_at'])
        for article in data['news']:
            packet=news._article_to_packet(article,fetched_at=fetched,historical=True)
            if packet is not None:packets.append(packet)
assert json.loads((P/'current-source-continuation/ledger.json').read_text())['news_complete_window']
nf=news._packets_to_frame(packets)
old=ROOT/'data/features/news_packets/2026.parquet'
schema=pq.ParquetFile(old).schema_arrow
target=nroot/'2026.parquet';tmp=target.with_suffix('.parquet.part')
oldids=set(pq.read_table(old,columns=['id'])['id'].to_pylist())
assert not oldids.intersection(nf['id']),'overlapping old news IDs require explicit original-consolidation diff'
with pq.ParquetWriter(tmp,schema,compression='zstd')as writer:
    for batch in pq.ParquetFile(old).iter_batches(batch_size=32768,use_threads=False):writer.write_batch(batch)
    writer.write_table(pa.Table.from_pandas(nf,schema=schema,preserve_index=False))
tmp.replace(target)
for relative in ['data/features/news_packets/2024.parquet','data/features/news_packets/2025.parquet']:
    a=WT/relative
    if not a.exists():a.parent.mkdir(parents=True,exist_ok=True);a.symlink_to(ROOT/relative)
r={'short_volume_delta_rows':len(vf),'short_volume_dates':[str(x.date())for x in sorted(vf.trade_date.unique())],'short_interest_delta_rows':len(ix),'news_new_packets':len(nf),'news_generated_visibility_rule':'Original historical collector created_at+15min. fetched_at retained separately; not a claim of local historical first visibility.','new_source_requests':0,'shared_writes':0,'original_parsers_used':True}
(P/'normalized-current-result.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
