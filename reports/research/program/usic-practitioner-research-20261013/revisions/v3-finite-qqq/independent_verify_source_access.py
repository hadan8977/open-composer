import hashlib,json,os,resource
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(4,5));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent
load=lambda p:json.loads(Path(p).read_text())
def bind(p):
 p=Path(p);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
l=load(P/'source-request-ledger.json');r=load(P/'source-result.json');e=load(P/'actual-source-access-evidence.json')
assert bind(P/'source-request-ledger.json')['sha256']=='b44304f943cd945ca0f740a5da7365b36cfe55e032d51a8893f496f7cf2d008d'
assert len(l['attempts'])==1 and l['prior_units']==35 and l['public_units_cumulative']==36
x=l['attempts'][0];assert x['http_status']==403 and x['entity_complete'] is True and x['status']=='source_stop_no_retry'
assert x['url']=='https://www.sec.gov/Archives/edgar/data/1067839/000175272423269960/primary_doc.xml'
p=Path(x['entity']['path']);b=bind(p);assert b['sha256']=='1857abfd9aa871de9b3b7f6a5c9e229ad1627569d9fb6e82d0af1f978e7a0c43' and b['bytes']==4819
assert 'Your Request Originates from an Undeclared Automated Tool' in p.read_text()
assert l['direct_entity_bytes']==4819 and l['unknown_reserved_bytes']==0 and l['complete_roster'] is False
assert r['ledger']['sha256']==bind(P/'source-request-ledger.json')['sha256']
absent=['frozen-historical-roster.json','identity-candidates.json','exact-materialized-request-manifest.json','market/request-ledger.json']
assert all(not (P/f).exists() for f in absent)
u=resource.getrusage(resource.RUSAGE_SELF)
out={'status':'pass','source_ledger':bind(P/'source-request-ledger.json'),'response':b,'source_result':bind(P/'source-result.json'),'source_access_evidence':bind(P/'actual-source-access-evidence.json'),'source_attempts':1,'http_status':403,'actual_response_is_denial_not_roster':True,'downstream_artifacts_absent':absent,'rate_limit_breach_inferred':False,'new_reviewer_HTTP_market_fit':0,'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':[0]}
(P/'independent-source-access-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
