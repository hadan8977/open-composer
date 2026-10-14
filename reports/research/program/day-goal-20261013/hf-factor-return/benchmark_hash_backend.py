"""Bound a SHA backend alternative on identical retained input bytes, no full retry."""
import hashlib,json,os,resource,subprocess,time
from pathlib import Path
P=Path(__file__).parent
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_CPU,(2,3))
size=16*1024*1024
with (P/'features/HAR-IDX.npy').open('rb') as f:chunk=f.read(size)
def total():
 a=resource.getrusage(resource.RUSAGE_SELF);b=resource.getrusage(resource.RUSAGE_CHILDREN)
 return a.ru_utime+a.ru_stime+b.ru_utime+b.ru_stime
cpu0=total();before=total();expected=hashlib.sha256(chunk).hexdigest();rows=[dict(backend='approved_python_hashlib',CPU=total()-before,sha256=expected)]
for args in [['sha256sum'],['openssl','dgst','-sha256']]:
 before=total();r=subprocess.run(args,input=chunk,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
 text=r.stdout.decode().strip();actual=text.split()[0] if args[0]=='sha256sum' else text.split()[-1]
 assert actual==expected
 rows.append(dict(backend=' '.join(args),CPU=total()-before,sha256=actual))
out=dict(scope='Same16MiB actual retained HAR-IDX prefix; no full file hash acceptance or native weakening.',bytes=size,backends=rows,
 whole_file_bytes=904062848,linear_full_file_CPU_projection={r['backend']:r['CPU']*904062848/size for r in rows},
 CPU=total()-cpu0,full_file_retried=False,old_source_market_fit_economics=0)
(P/'hash-backend-benchmark.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
