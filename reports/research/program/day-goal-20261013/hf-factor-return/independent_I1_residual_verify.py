import ast,hashlib,json,math,mmap,os,resource,signal,sys
from pathlib import Path
from collections import deque
from datetime import datetime,timedelta
resource.setrlimit(resource.RLIMIT_CPU,(16,17))
assert os.sched_getaffinity(0)=={0}
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
P=Path(__file__).parent;F=P/'features';out={'status':'partial','stage':'bindings','fresh_bindings':[]}
def load(p):return json.loads(Path(p).read_text())
def save(signum=None,frame=None):
 u=resource.getrusage(resource.RUSAGE_SELF);out['resource']={'CPU':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss,'affinity':list(os.sched_getaffinity(0))}
 (P/'independent-I1-residual-verification.json').write_text(json.dumps(out,indent=2)+'\n')
 if signum:sys.exit(90)
signal.signal(signal.SIGXCPU,save)
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(b):
 p=Path(b['path']);assert p.stat().st_size==b['bytes'] and digest(p)==b['sha256'],str(p)
 out['fresh_bindings'].append(b)
def main():
 assert digest(P/'implementation-manifest.json')=='5ff67d4897f08c8b8bb85431fd6f72699f32de515c9da39f335d7dd52668e5ec'
 assert digest(P/'implementation-I1-revision.json')=='4bbf13f90e3ca59d6152e69f8d7b82339cf44af43e6fb98587fd4b30c4d3d53c'
 rev=load(P/'implementation-I1-revision.json')
 for k in ['M0','M0_review']:check(rev[k])
 m=load(P/'implementation-manifest.json');old=load(P/'implementation-M0-archive/implementation-manifest.json')
 ix=lambda bs:{str(Path(b['path']).resolve()):b for b in bs}
 prior=ix(load(P/'independent-implementation-verification-partial.json')['bindings_passed']);before=ix(old['files']);now=ix(m['files'])
 assert set(before)<=set(now)
 changed=[Path(b['path']).name for k,b in now.items() if k in before and (b['sha256'],b['bytes'])!=(before[k]['sha256'],before[k]['bytes'])]
 assert set(changed)==set(rev['changed_prior_files'])
 inherited=[];large=[]
 for k,b in now.items():
  if k in prior and (b['sha256'],b['bytes'])==(prior[k]['sha256'],prior[k]['bytes']):
   assert Path(b['path']).stat().st_size==b['bytes'];inherited.append(b)
  elif b['bytes']>100000000:large.append(b)
  else:check(b)
 assert [Path(b['path']).name for b in large]==['HAR-IDX.npy']
 out.update(inherited_bindings=inherited,changed_prior_files=changed,manifest_file_count=len(now))
 # Independent pure rule checks, not economic account runs.
 tree=ast.parse((P/'hf_diagnostics.py').read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['desired','diagnostic_inventory']]
 ns={'math':math,'RULES':('Sign','Positive','SSign','SPositive')};exec(compile(ast.Module(body=nodes,type_ignores=[]),'rules','exec'),ns)
 desire=ns['desired'];assert desire(.001,.002,'Positive',0)==1 and desire(.001,.002,'SPositive',0)==0
 for rule in ns['RULES']:
  assert desire(float('nan'),.002,rule,1)==0
 for rule in ['SSign','SPositive']:
  assert desire(.002,.002,rule,0)==0 and desire(-.002,.002,rule,1)==1
 assert desire(0,.002,'Sign',0)==desire(0,.002,'Positive',0)==1
 inv=ns['diagnostic_inventory']([str(i) for i in range(20)]);assert len(inv)==len(set(inv))==800
 out['rule_checks']='plain/threshold nonzero cost, zero, inclusive threshold band, missing fallback, 800 unique';save()
 out['stage']='source_and_scalar_spots'
 import numpy as np
 import pyarrow as pa
 import pyarrow.parquet as pq
 pa.set_cpu_count(1);pa.set_io_thread_count(1)
 meta=load(F/'feature-metadata.json');dq=load(F/'source-day-QA.json');rows=load(F/'packet-row-clock.json');n=meta['n_rows'];assert n==len(rows)==136597
 src=np.load(F/'source-IDX.npy',mmap_mode='r');sums=np.load(F/'source-SUM.npy',mmap_mode='r');valid=np.load(F/'source-valid.npy',mmap_mode='r');nominal=np.load(F/'source-nominal.npy',mmap_mode='r');labels=np.load(F/'labels.npy',mmap_mode='r');ar=np.load(F/'AR26.npy',mmap_mode='r')
 mkt=meta['market_column'];days=[d['date'] for d in dq];active=[i for i,d in enumerate(dq) if d['activated']]
 # Only the scalar market source series; evict pages in small blocks.
 market=np.empty(src.shape[:2])
 for i in range(0,len(days),32):
  market[i:i+32]=src[i:i+32,:,mkt];src._mmap.madvise(mmap.MADV_DONTNEED)
 source={b['month']:b for b in load(P/'complete-source-input-manifest.json')['files']};cols=[meta['factors'][0],meta['factors'][mkt],meta['factors'][meta['key5_columns'][0]]];colidx=[meta['factors'].index(c) for c in cols]
 rawchecks=[]
 for ds in ['1996-01-02','2020-12-31']:
  start=datetime.fromisoformat(ds);path=source[ds[:4]+ds[5:7]]['path'];t=pq.read_table(path,columns=cols+['datetime'],filters=[('datetime','>=',start),('datetime','<',start+timedelta(days=1))],use_threads=False)
  ts=t['datetime'].to_numpy();mins=((ts-ts.astype('datetime64[D]'))/np.timedelta64(1,'m')).astype(int);vv=np.column_stack([t[c].to_numpy() for c in cols]);i=days.index(ds);windows=0
  for k in range(1,int(nominal[i])+1):
   take=(mins>=571+15*(k-1))&(mins<=570+15*k)
   if take.sum()==15:
    assert np.allclose(sums[i,k,colidx],vv[take].sum(0),rtol=1e-13,atol=1e-15)
    assert np.allclose(src[i,k,colidx],np.log1p(vv[take]).sum(0),rtol=1e-13,atol=1e-15);windows+=1
  rawchecks.append({'date':ds,'columns':cols,'source_rows':len(ts),'complete_windows_compared':windows})
  src._mmap.madvise(mmap.MADV_DONTNEED);sums._mmap.madvise(mmap.MADV_DONTNEED)
 out['actual_source_spots']=rawchecks;save()
 chosen={0,n-1,next(i for i,r in enumerate(rows) if not r['target_mature']),next(i for i,r in enumerate(rows) if r['cts_target_available'])}
 for year in ['2004','2019','2020']:
  j=next(i for i,r in enumerate(rows) if r['date'].startswith(year));chosen.update(range(j,j+4))
 selected=[rows[j] for j in sorted(chosen)];targets={(r['source_day_index'],(r['minute']-570)//15+1):r for r in selected};features={(r['source_day_index'],(r['minute']-570)//15):r for r in selected}
 full=deque(maxlen=252);sqsum=np.zeros(26);last=deque(maxlen=2);hist=deque(maxlen=26);ew=None;alpha=1-math.exp(-math.log(2)/26);lc=[];ac=[];observed=0
 for i in active:
  tau=None
  if len(full)>=52:
   ms=sqsum/len(full);tau=ms/ms.mean() if ms.mean()>0 else None
  for k in range(1,int(nominal[i])+1):
   if valid[i,k]:
    value=float(market[i,k]);observed+=1
    if len(last)==2:
     product=abs(last[-1]*last[-2]);ew=product if ew is None else alpha*product+(1-alpha)*ew
    threshold=3.5*math.sqrt(math.pi/2*26*ew*tau[k-1])*(1/26)**.49 if tau is not None and ew is not None else None
    target=value if threshold is not None and abs(value)<=threshold else (0 if threshold is not None else np.nan)
    if (i,k) in targets:
     r=targets[i,k];j=r['row'];assert np.allclose(labels[j],[value,target],rtol=1e-11,atol=1e-15,equal_nan=True)
     if threshold is None:assert r['target_threshold'] is None
     else:assert math.isclose(r['target_threshold'],threshold,rel_tol=1e-10,abs_tol=1e-15)
     lc.append({'row':j,'date':r['date'],'minute':r['minute'],'threshold_from_prior_history':threshold})
    last.append(value);hist.append(value)
   elif (i,k) in targets:
    r=targets[i,k];assert not r['target_mature'] and np.isnan(labels[r['row']]).all();lc.append({'row':r['row'],'date':r['date'],'future_target_missing_preserved':True})
   if (i,k) in features:
    r=features[i,k];assert np.array_equal(ar[r['row']],list(reversed(hist)));ac.append(r['row'])
  if nominal[i]==26 and valid[i,1:27].all():
   sq=market[i,1:27]**2
   if len(full)==252:sqsum-=full[0]
   full.append(sq);sqsum+=sq
 assert len(lc)==len(ac)==len(chosen)
 out.update(scalar_state_history_completed_returns=observed,label_spots=lc,AR26_spot_rows=ac,label_scope='Full past scalar history reconstructed; comparisons only selected initial, first Cts, missing-future, 2004/2019/2020 and last packets; not full label replay parity')
 out['stage']='remaining_HAR_IDX_hash';save();print('source/scalar checks complete',out['resource'],flush=True)
 for b in large:check(b)
 out['status']='ok';out['stage']='complete';save();print('all residual checks passed',out['resource'],flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:
  save();raise
