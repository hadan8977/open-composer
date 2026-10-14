import hashlib,json,os,resource,struct
from pathlib import Path
from collections import Counter
resource.setrlimit(resource.RLIMIT_CPU,(20,22))
assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent
load=lambda p:json.loads(Path(p).read_text())
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
manifest=P/'package-manifest.json'
assert digest(manifest)=='aee071e570cf194498ab932bc6c0e5652543987f87df4c8204fde125652040df'
m=load(manifest);checks=[]
for b in m['immutable_bindings']+[m['input42file_manifest_unchanged']]:
 q=Path(b['path']);assert q.stat().st_size==b['bytes'] and digest(q)==b['sha256'],str(q);checks.append(b)
s=load(P/'seal-completion-receipt.json');b=s['successful_sealing_process'];assert digest(b['path'])==b['sha256'];assert b['CPU_affinity_or_quota_readback_verified'] is False
assert b['charged_inside_metadata_setup_unknown20_no_doublecharge']
e=load(P/'source-connection-evidence.json');r=load(P/'recovery/source-link-recovery.json')
extra=[]
for x in e['source_basis_and_population']['producer_bindings']:
 for b in [x['original'],x['snapshot']]:
  assert digest(b['path'])==b['sha256'];extra.append(b)
# Only already identified small metadata files, no new locator or price data scan.
for x in e['selected_metadata_bindings_and_fields']:
 b=x['binding'];q=Path(b['path']);assert q.stat().st_size==b['bytes'] and b['bytes']<2000000 and digest(q)==b['sha256'],str(q);extra.append(b)
footers=[]
for b in load(P/'bounded-parquet-footers.json')+r['footers']:
 q=Path(b['path'])
 with q.open('rb') as f:
  f.seek(-8,2);tail=f.read(8);assert tail[4:]==b'PAR1';n=struct.unpack('<I',tail[:4])[0];assert n<1000000
  f.seek(-8-n,2);body=f.read(n)
 candidates={'metadata_only':hashlib.sha256(body).hexdigest(),'metadata_and_trailer':hashlib.sha256(body+tail).hexdigest()}
 matched=[k for k,v in candidates.items() if v==b['footer_sha256']];assert matched,str(q)
 assert q.stat().st_size==b['file_bytes']
 footers.append({'path':str(q),'bytes_read':n+8,'footer_sha256':b['footer_sha256'],'hash_scope':matched[0]})
paths24=(P/'recovery/2024-alias-file-locator.txt').read_text().splitlines();paths25=(P/'data-file-locator.txt').read_text().splitlines()
counts={}
for yr,paths in [('2024',paths24),('2025',paths25)]:
 relevant=[x for x in paths if x.startswith('data/sip/minute/'+yr+'/') and x.endswith('.parquet')]
 c=Counter(x.split('/')[4] for x in relevant);assert len(relevant)==13416 and len(c)==12 and set(c.values())=={1118}
 counts[yr]=dict(c)
u=resource.getrusage(resource.RUSAGE_SELF)
out=dict(manifest_sha256=digest(manifest),direct_bindings_passed=len(m['immutable_bindings']),old42_manifest_only_hash_passed=True,extra_small_metadata_checks=len(extra),footer_checks=footers,artifact_filename_month_counts=counts,source_seal_CPU_affinity_verified=False,new_review_affinity=list(os.sched_getaffinity(0)),CPU_seconds=u.ru_utime+u.ru_stime,max_RSS_KiB=u.ru_maxrss,market_rows_read=0,new_external_requests=0,whole_large_price_hashes=False)
(P/'independent-source-connection-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['direct_bindings_passed','extra_small_metadata_checks','CPU_seconds','max_RSS_KiB','new_review_affinity']}))
