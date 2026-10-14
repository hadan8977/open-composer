"""Use the original collector's ID/update consolidation after retained overlap check."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from open_composer.research.news import collector as news

ROOT=Path.cwd();WT=Path('/root/codex-test/wt-paper-continuity-20261014');P=ROOT/'reports/research/program/paper-continuity-20261014'
rows=json.loads((P/'current-source-intake/ledger.json').read_text())['requests']+json.loads((P/'current-source-continuation/ledger.json').read_text())['requests']
packets=[]
for row in rows:
    if not row['label'].startswith('news-'):continue
    payload=Path(row['entity_path']).read_bytes();assert row['complete'] and row['http_status']==200 and hashlib.sha256(payload).hexdigest()==row['entity_sha256']
    for article in json.loads(payload)['news']:
        packet=news._article_to_packet(article,fetched_at=datetime.fromisoformat(row['attempted_at']),historical=True)
        if packet is not None:packets.append(packet)
nf=news._packets_to_frame(packets);old=pd.read_parquet(ROOT/'data/features/news_packets/2026.parquet')
overlap=sorted(set(old.id)&set(nf.id));report=[]
for oid in overlap:
    before=old.loc[old.id.eq(oid)].iloc[-1];after=nf.loc[nf.id.eq(oid)].iloc[-1]
    report.append({'id':oid,'old_created_at':str(before.created_at),'new_created_at':str(after.created_at),'old_updated_at':str(before.updated_at),'new_updated_at':str(after.updated_at),'headline_changed':before.headline!=after.headline,'old_fetched_at':str(before.fetched_at),'new_fetched_at':str(after.fetched_at)})
combined=pd.concat([old,nf],ignore_index=True).sort_values(['created_at','id']).drop_duplicates(subset=['id'],keep='last')
target=WT/'data/features/news_packets/2026.parquet';tmp=target.with_suffix('.parquet.part');combined.to_parquet(tmp,index=False);tmp.replace(target)
for year in (2024,2025):
    dest=target.with_name(f'{year}.parquet')
    if not dest.exists():dest.symlink_to(ROOT/f'data/features/news_packets/{year}.parquet')
vol=pd.read_parquet(P/'normalized-current/short-volume-parts/delta.parquet',columns=['trade_date']);ix=pd.read_parquet(P/'normalized-current/short-interest-parts/delta.parquet',columns=['symbol'])
r={'status':'normalized_actual_current_entities','short_volume_delta_rows':len(vol),'short_volume_dates':[str(pd.Timestamp(x).date())for x in sorted(vol.trade_date.unique())],'short_interest_delta_rows':len(ix),'news_new_packets':len(nf),'old_news_rows':len(old),'combined_news_rows':len(combined),'overlap_ids':report,'normal_consolidation_rule':'unchanged sort(created_at,id), deduplicate id keep last','visibility_rule':'unchanged historical collector created_at+15min; current fetched_at retained; not historical local first-seen proof','failed_normalization_attempt_retained':True,'new_source_requests':0,'shared_writes':0}
(P/'normalized-current-result.json').write_text(json.dumps(r,indent=2)+'\n');print({k:v for k,v in r.items()if k!='overlap_ids'})
