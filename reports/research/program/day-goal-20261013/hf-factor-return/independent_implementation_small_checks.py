import ast,hashlib,json,os,resource,mmap,math,xml.etree.ElementTree as ET
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(4,5))
assert os.sched_getaffinity(0)=={0}
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
P=Path(__file__).parent
load=lambda p:json.loads(Path(p).read_text())
a=load(P/'native-large-binding-hash-repair.json')
for key in ['old_reader','new_native_reader','synthetic_tests','test_code','resource_receipt']:
 b=a[key];q=Path(b['path']);assert hashlib.sha256(q.read_bytes()).hexdigest()==b['sha256'] and q.stat().st_size==b['bytes']
new=Path(a['new_native_reader']['path']).read_text();old=Path(a['old_reader']['path']).read_text()
start=new.index('def _sha256_file(');end=new.index('def _load_binding(',start)
reconstructed=(new[:start]+new[end:]).replace('_sha256_file(path)','hashlib.sha256(path.read_bytes()).hexdigest()')
assert reconstructed==old
node=next(x for x in ast.parse(new).body if isinstance(x,ast.FunctionDef) and x.name=='_sha256_file')
assert new.count('_sha256_file(path)')==2
junit={}
for filename in ['features-tests.xml','models-tests.xml','accounts-tests.xml','evaluation-tests.xml','native-hash-repair-tests.xml']:
 root=ET.parse(P/filename).getroot();suites=list(root) if root.tag=='testsuites' else [root]
 junit[filename]={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','errors','failures']}
 assert junit[filename]['errors']==junit[filename]['failures']==0
fn=next(x for x in ast.parse((P/'hf_diagnostics.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='desired')
namespace={'math':math};exec(compile(ast.Module(body=[fn],type_ignores=[]),'diagnostic-function','exec'),namespace)
assert namespace['desired'](.001,.002,False,0)==0
import numpy as np
import pyarrow.parquet as pq
F=P/'features';meta=load(F/'feature-metadata.json');rows=load(F/'packet-row-clock.json');n=meta['n_rows']
assert n==len(rows)==136597 and meta['allocated_rows']==138490
maps={s:np.load(F/f'HAR-{s}.npy',mmap_mode='r') for s in meta['views']}
src=np.load(F/'source-IDX.npy',mmap_mode='r');sums=np.load(F/'source-SUM.npy',mmap_mode='r');valid=np.load(F/'source-valid.npy',mmap_mode='r');nominal=np.load(F/'source-nominal.npy',mmap_mode='r');labels=np.load(F/'labels.npy',mmap_mode='r');ar=np.load(F/'AR26.npy',mmap_mode='r')
dq=load(F/'source-day-QA.json');days=[d['date'] for d in dq];active=[i for i,d in enumerate(dq) if d['activated']];mkt=meta['market_column'];assert meta['factors'][mkt]=='ff__mkt'
assert all(m.shape==(138490,816) and m.dtype==np.float64 for m in maps.values())
assert all(r['row']==i for i,r in enumerate(rows))
chosen={0,n-1,n//2}
for year in ['2004','2008','2016','2019','2020']:
 chosen.add(next(i for i,r in enumerate(rows) if r['date'].startswith(year)))
chosen.add(next(i for i,r in enumerate(rows) if not r['target_mature']))
def previous(ix,view):
 done=np.flatnonzero(valid[ix,1:])+1
 if view=='IDX':return src[ix,done].sum(0)+src[ix,0]
 if view=='SUM':return sums[ix,done].sum(0)+sums[ix,0]
 return (sums[ix,done]-sums[ix,1]).sum(0)
def make(i,k,prev,view):
 if view=='IDX':return np.r_[src[i,k],src[i,k-3:k+1].mean(0),previous(prev,view)]
 if view=='SUM':return np.r_[sums[i,k],sums[i,k-3:k+1].mean(0),previous(prev,view)]
 values=sums[i,k-3:k+1]-sums[i,1]
 return np.r_[values[-1],values.mean(0),previous(prev,view)]
samples=[]
for j in sorted(chosen):
 r=rows[j];i=r['source_day_index'];p=r['packet_index'];k=(r['minute']-570)//15
 assert days[i]==r['date'] and active[p]==i and k>=4 and k<nominal[i]
 for view in ['IDX','SUM','INV']:
  np.testing.assert_allclose(maps[view][j],make(i,k,active[p-1],view),rtol=1e-13,atol=1e-15)
 for view in ['IDX','INV']:
  expected=make(active[p-20],k,active[p-21],view)
  for ch in range(3):expected[ch*272+mkt]=maps[view][j,ch*272+mkt]
  np.testing.assert_allclose(maps[view+'_STALE'][j],expected,rtol=1e-13,atol=1e-15)
 if not r['target_mature']:assert np.isnan(labels[j,0])
 samples.append({'row':j,'date':r['date'],'minute':r['minute'],'target_mature':r['target_mature']})
for a in [src,sums,*maps.values()]:a._mmap.madvise(mmap.MADV_DONTNEED)
u=resource.getrusage(resource.RUSAGE_SELF)
(P/'independent-implementation-small-checks.json').write_text(json.dumps(dict(native_inverse_exact=True,native_hash_sites=2,junit_author_receipts=junit,feature_samples=samples,feature_scope='5 HAR views sampled mathematically from existing source tensors; no full feature acceptance, no original300 source or full labels replay',plain_positive_counterexample=dict(score=.001,cost=.002,held=0,actual_threshold_target=0,plain_target=1),cpu_seconds=u.ru_utime+u.ru_stime,max_RSS_KiB=u.ru_maxrss,affinity=list(os.sched_getaffinity(0))),indent=2)+'\n')
print('small checks passed',u.ru_utime+u.ru_stime,u.ru_maxrss)
