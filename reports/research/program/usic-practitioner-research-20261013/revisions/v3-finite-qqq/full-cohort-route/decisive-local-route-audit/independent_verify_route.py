import json,hashlib,resource,os,struct,re
from pathlib import Path
from collections import defaultdict
from decimal import Decimal
resource.setrlimit(resource.RLIMIT_CPU,(75,80));assert os.sched_getaffinity(0)=={0}
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
P=Path(__file__).resolve().parent;checks=[]
def load(p):return json.loads(Path(p).read_bytes())
def verify(b):
 p=Path(b['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==b['sha256'],str(p)
 if 'bytes' in b:assert len(raw)==b['bytes']
 checks.append(dict(path=str(p),sha256=b['sha256'],bytes=len(raw)))
verify(dict(path=P/'review-packet.json',sha256='57f4d20b2c42d541708b8313636bad72b90931bba6004ecc82cddc660696440a'))
packet=load(P/'review-packet.json')
for b in packet['bindings']:verify(b)
m=load(P/'manifest.json')
for b in m['bindings']+m['file_checkpoint_bindings']:verify(b)
coverage=load(P/'actual-coverage.json');proof=load(P/'global-key-verification.json');result=load(P/'result.json');account=load(P/'resource-accounting.json')
items={};by_symbol=defaultdict(list);whole=0;totals=defaultdict(int);sessions={}
for b,witness in zip(m['file_checkpoint_bindings'],m['source_file_witnesses'],strict=True):
 item=load(b['path']);items[item['path']]=item
 assert witness['checkpoint']==b and witness['path']==item['path'] and witness['bytes']==item['bytes']
 assert witness['whole_file_sha256']==item.get('sha256') and witness['footer_sha256']==item['footer_sha256']
 assert item['columns_read']==['symbol','timestamp'] and item['price_or_volume_columns_read'] is False
 whole+=int(item.get('sha256') is not None);totals['unique_file_bytes']+=item['bytes']
 for r in item['records']:
  by_symbol[r['symbol_candidate']].append({**r,'path':item['path']})
  for key in ['actual_rows','nonnull_unique_timestamp_keys','duplicate_keys','null_timestamp_rows','unique_RTH_minute_keys','RTH_nonminute_aligned_keys']:totals[key]+=r[key]
  for day,c in r['session_counts'].items():
   key=(r['symbol_candidate'],day);assert key not in sessions;sessions[key]=c
assert len(items)==2232 and whole==144 and len(items)-whole==2088
assert totals['actual_rows']==totals['nonnull_unique_timestamp_keys']==21755717
assert totals['duplicate_keys']==totals['null_timestamp_rows']==totals['RTH_nonminute_aligned_keys']==0
assert totals['unique_RTH_minute_keys']==18026368 and totals['unique_file_bytes']==1538297359
duplicates=[];per_symbol={}
for s,rows in sorted(by_symbol.items()):
 rows.sort(key=lambda r:r['first_UTC']);n=sum(r['nonnull_unique_timestamp_keys'] for r in rows)
 for a,b in zip(rows,rows[1:]):
  assert a['last_UTC']<=b['first_UTC']
  if a['last_UTC']==b['first_UTC']:
   assert b['first_UTC'][11:]=='00:00:00.000000000Z';n-=1
   duplicates.append(dict(symbol=s,timestamp_UTC=b['first_UTC'],previous_path=a['path'],next_path=b['path'],proof='Sorted unique extrema intersect at exactly one actual endpoint'))
 per_symbol[s]=n
assert duplicates==proof['duplicate_endpoint_evidence'] and len(duplicates)==34
assert per_symbol==proof['per_symbol_actual_unique_keys'] and sum(per_symbol.values())==21755683
assert len(sessions)==48694 and sum(c['unique_real_RTH_minute_keys']>0 for c in sessions.values())==48694
assert sum(c['missing_grid_keys_not_filled']==0 for c in sessions.values())==24861
assert sum(c['missing_grid_keys_not_filled'] for c in sessions.values())==859532
for r in coverage['records']:
 if r['shards']:
  for day,c in r['actual_session_counts'].items():assert c==sessions[r['symbol_candidate'],day]
assert set(r['symbol_candidate'] for r in coverage['records'] if not r['shards'])=={'ANSS','EA','SGEN','WBA'}
assert proof['whole_file_SHA_count']==144 and proof['footer_plus_selected_key_SHA_count']==2088

cal=load(P/'calendar.json')['sessions'];opens=np.array([r['open_ns'] for r in cal],dtype='int64');ends=np.array([r['close_ns_exclusive'] for r in cal],dtype='int64');minute=60_000_000_000
chosen=['data/sip/minute/2024/01/shard-0003.parquet','data/sip/minute/2024/02/shard-0003.parquet','data/sip/minute/2024/02/shard-0995.parquet','data/sip/minute/2024/03/shard-0995.parquet','data/sip/minute/2024/11/shard-0848.parquet','data/sip/minute/2025/12/shard-0407.parquet']
sample=[];arrays={}
for path in chosen:
 item=items[path];p=Path(path);before=p.stat();assert before.st_size==item['bytes'] and before.st_mtime_ns==item['mtime_ns']
 with p.open('rb') as f:
  f.seek(-8,2);tail=f.read(8);assert tail[4:]==b'PAR1';size=struct.unpack('<I',tail[:4])[0];f.seek(-8-size,2);footer=f.read(size+8)
 assert hashlib.sha256(footer).hexdigest()==item['footer_sha256']
 if item.get('sha256'):assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
 table=pq.ParquetFile(path).read(columns=['symbol','timestamp'],use_threads=False)
 for r in item['records']:
  s=r['symbol_candidate'];col=table.filter(pc.equal(table['symbol'],s))['timestamp'].combine_chunks();assert col.null_count==r['null_timestamp_rows']
  ns=pc.drop_null(col).cast(pa.timestamp('ns',tz='UTC')).cast(pa.int64()).to_numpy();u=np.unique(ns)
  assert len(ns)==r['actual_rows'] and len(u)==r['nonnull_unique_timestamp_keys']
  assert hashlib.sha256(u.astype('<i8').tobytes()).hexdigest()==r['sorted_unique_ns_le_sha256']
  assert str(np.datetime64(int(u[0]),'ns'))+'Z'==r['first_UTC'] and str(np.datetime64(int(u[-1]),'ns'))+'Z'==r['last_UTC']
  for day,c in r['session_counts'].items():
   ix=next(i for i,d in enumerate(cal) if d['date']==day);selected=u[(u>=opens[ix])&(u<ends[ix])];proper=selected[(selected-opens[ix])%minute==0]
   assert len(proper)==c['unique_real_RTH_minute_keys']
   assert sum(proper<opens[ix]+90*minute)==c['unique_0930_1100_minute_keys']
   assert int((ends[ix]-opens[ix])//minute)-len(proper)==c['missing_grid_keys_not_filled']
  arrays[path,s]=u;sample.append(dict(path=path,symbol=s,actual_selected_keys=len(u),session_counts_checked=len(r['session_counts']),hash_scope='sourcefooter and actual selectedkeySHA; wholefile additionally only where supplied'))
 after=p.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
for s,a,b in [('AAPL',chosen[0],chosen[1]),('TSLA',chosen[2],chosen[3])]:
 intersection=np.intersect1d(arrays[a,s],arrays[b,s]);assert len(intersection)==1
 assert str(np.datetime64(int(intersection[0]),'ns'))[11:]=='00:00:00.000000000'
assert next(c for c in cal if c['date']=='2024-11-29')['expected_real_RTH_minutes']==210
jobtotal=Decimal('0')
for job in account['jobs']:
 verify(job);t=Path(job['path']).read_text();value=sum(Decimal(re.search(k+r' time \(seconds\): ([\d.]+)',t)[1]) for k in ['User','System']);assert value==Decimal(job['CPU']);jobtotal+=value
assert jobtotal==Decimal('61.26')
assert Decimal(account['prior_cumulative_CPU'])+jobtotal+Decimal('10')==Decimal('425.66')
assert sum(j['actual_unified_exit']==143 for j in account['jobs'])==2
out=dict(status='pass',bindings_checked_count=len(checks),bindings=checks,all_checkpoint_files_hashed=2232,all_source_files_rehashed=False,all_source_keys_or_prices_replayed=False,author_source_hash_scopes={'whole_file':144,'footer_selected_keys':2088},all_checkpoint_summaries_reconciled=True,global_unique_keys=21755683,midnight_duplicate_occurrences=34,RTH_keys=18026368,queried_cells=48694,complete_cells=24861,missing_RTH_keys=859532,actual_source_samples=sample,actual_crossfile_intersections=2,actual_earlyclose_RTH_check='ROST2024-11-29,210minute expectedgrid',source_sample_price_columns_read=False,actual_author_job_CPU='61.26',interrupted143_jobs_retained=2,author_cumulative='425.66',new_network_economics_fits=0,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['bindings','actual_source_samples']}))
