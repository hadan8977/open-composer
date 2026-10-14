"""Bounded independent feature guards and input mathematics; no market fitting."""
import hashlib,json,mmap,os,resource,signal,sys,time
from pathlib import Path
from collections import deque
from datetime import datetime,timedelta

os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
resource.setrlimit(resource.RLIMIT_CPU,(68,70))
P=Path(__file__).parent;ROOT=Path('/root/codex-test/open-composer');checks=[];phase='init'
def usage():
 u=resource.getrusage(resource.RUSAGE_SELF);return dict(CPU_seconds=u.ru_utime+u.ru_stime,max_RSS_KiB=u.ru_maxrss)
def savepartial(signum=None,frame=None):
 (P/'independent-implementation-verification-partial.json').write_text(json.dumps({'phase':phase,'bindings_passed':checks,'resource':usage()},indent=2)+'\n')
 if signum is not None:sys.exit(90)
signal.signal(signal.SIGXCPU,savepartial)
def load(p):return json.loads(Path(p).read_text())
def check(b):
 path=Path(b['path']);path=path if path.is_absolute() else ROOT/path
 with path.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
 assert h==b['sha256'] and path.stat().st_size==b['bytes'],str(path)
 checks.append(b)
def main():
 global phase
 manifest=load(P/'implementation-manifest.json')
 assert hashlib.sha256((P/'implementation-manifest.json').read_bytes()).hexdigest()=='0c297b1c0ed87e9a83d5cee986c9357cc7aff47a5181f7e8006064ee14514e08'
 phase='fresh_manifest_and_feature_hash'
 for i,b in enumerate(manifest['files']):
  check(b)
  if b['bytes']>100000000:
   print(json.dumps({'hashed':Path(b['path']).name,**usage()}),flush=True);savepartial()
 assert len(checks)==62
 phase='feature_clock_and_math'
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
 chosen.update(i for i,r in enumerate(rows) if not r['target_mature'])
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
 # Two actual source days, three fixed columns; no rehash/re-scan of original300 months.
 source_manifest=load(P/'complete-source-input-manifest.json');files={r['month']:r for r in source_manifest['files']};raw_checks=[]
 cols=[meta['factors'][0],meta['factors'][mkt],meta['factors'][meta['key5_columns'][0]]]
 colidx=[meta['factors'].index(c) for c in cols]
 for ds in ['1996-01-02','2020-12-31']:
  start=datetime.fromisoformat(ds);path=files[ds[:4]+ds[5:7]]['path'];table=pq.read_table(path,columns=cols+['datetime'],filters=[('datetime','>=',start),('datetime','<',start+timedelta(days=1))],use_threads=False)
  ts=table['datetime'].to_numpy();minutes=((ts-ts.astype('datetime64[D]'))/np.timedelta64(1,'m')).astype(int);vv=np.column_stack([table[c].to_numpy() for c in cols]);i=days.index(ds)
  for k in range(1,int(nominal[i])+1):
   take=(minutes>=571+15*(k-1))&(minutes<=570+15*k)
   if take.sum()==15:
    np.testing.assert_allclose(sums[i,k,colidx],vv[take].sum(0),rtol=1e-13,atol=1e-15)
    np.testing.assert_allclose(src[i,k,colidx],np.log1p(vv[take]).sum(0),rtol=1e-13,atol=1e-15)
  raw_checks.append({'date':ds,'columns':cols,'rows':len(ts)})
 # Independent lag-BV/tau market scalar replay to target labels (no forecasts or return metrics).
 selected={ (r['source_day_index'],(r['minute']-570)//15+1):r['row'] for r in rows }
 full=deque(maxlen=252);last=deque(maxlen=2);history=deque(maxlen=26);ew=None;alpha=1-np.exp(-np.log(2)/26);label_checks=0;ar_checks=0
 packet_by_day={r['source_day_index']:[] for r in rows}
 for r in rows:packet_by_day[r['source_day_index']].append(r)
 for num,i in enumerate(active):
  tau=None
  if len(full)>=52:
   ms=np.square(np.array(full)).mean(0);tau=ms/ms.mean() if ms.mean()>0 else None
  rr={ (r['minute']-570)//15:r for r in packet_by_day.get(i,[]) }
  for k in range(1,int(nominal[i])+1):
   if valid[i,k]:
    value=float(src[i,k,mkt])
    if len(last)==2:
     product=abs(last[-1]*last[-2]);ew=product if ew is None else alpha*product+(1-alpha)*ew
    threshold=3.5*np.sqrt(np.pi/2*26*ew*tau[k-1])*(1/26)**.49 if tau is not None and ew is not None else None
    target=value if threshold is not None and abs(value)<=threshold else (0 if threshold is not None else np.nan)
    if (i,k) in selected:
     j=selected[i,k];np.testing.assert_allclose(labels[j], [value,target],rtol=1e-12,atol=1e-15,equal_nan=True);label_checks+=1
    last.append(value);history.append(value)
   if k in rr:
    np.testing.assert_array_equal(ar[rr[k]['row']],list(reversed(history)));ar_checks+=1
  if nominal[i]==26 and valid[i,1:27].all():full.append(np.array(src[i,1:27,mkt],copy=True))
  if num%64==0:src._mmap.madvise(mmap.MADV_DONTNEED)
 phase='done'
 out={'status':'ok','manifest_bindings_verified':62,'hashed_total_bytes':sum(b['bytes'] for b in checks),'source300_market361_nested_raw_rehashed':False,'metadata_actual_rows':n,'allocated_rows_not_consumed':138490,'HAR_samples':samples,'raw_source_day_checks':raw_checks,'independent_scalar_market_label_checks':label_checks,'independent_AR26_checks':ar_checks,'views':meta['views'],'no_market_fit_or_economics':True,'resource':usage()}
 (P/'independent-implementation-feature-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'status':'ok',**usage(),'label_checks':label_checks,'ar_checks':ar_checks}),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:
  savepartial();raise
