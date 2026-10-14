from pathlib import Path
import json,hashlib,time,datetime
b=Path('reports/research/program/paper-continuity-20261014');m=json.loads((b/'result-manifest.json').read_text());begin=time.process_time();checked=[];mismatches=[]
for kind in ['code','data','proofs']:
 for r in m[kind]:
  p=Path(r['path'])
  if not p.exists():mismatches.append({'kind':kind,'path':str(p),'error':'missing'});continue
  with p.open('rb') as h:s=hashlib.file_digest(h,'sha256').hexdigest()
  actual={'kind':kind,'path':str(p),'bytes':p.stat().st_size,'sha256':s}
  if actual['bytes']!=r['bytes'] or s!=r['sha256']:mismatches.append({'expected':r,'actual':actual})
  checked.append(actual)
for r in json.loads((b/'shared-production-isolation-verification.json').read_text())['files']:
 p=Path(r['path']);s=hashlib.sha256(p.read_bytes()).hexdigest()
 if s!=r['sha256']:mismatches.append({'shared_baseline_changed':str(p),'actual_sha256':s,'expected':r['sha256']})
report={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verified':checked,'mismatches':mismatches,'CPU_seconds':time.process_time()-begin,'production_changed':False}
(b/'root-acceptance/package-hash-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'verified_files':len(checked),'verified_bytes':sum(r['bytes'] for r in checked),'mismatches':mismatches,'CPU_seconds':report['CPU_seconds']}))
raise SystemExit(bool(mismatches))
