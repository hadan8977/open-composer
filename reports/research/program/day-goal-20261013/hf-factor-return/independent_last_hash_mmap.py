import hashlib,json,mmap,os,resource,signal,sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(4,5))
assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent
out={'status':'partial','bytes_consumed_complete_chunks':0,'inflight_chunk_bytes':0,'method':'read-only mmap; 32MiB memoryview update; release and MADV_DONTNEED after every chunk','affinity':[0],'soft_hard_CPU':[4,5]}
def usage():
 u=resource.getrusage(resource.RUSAGE_SELF);return {'CPU_seconds':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss}
def save(sig=None,frame=None):
 out['resource']=usage();(P/'independent-last-hash-mmap-receipt.json').write_text(json.dumps(out,indent=2)+'\n')
 if sig:sys.exit(90)
signal.signal(signal.SIGXCPU,save)
def main():
 manifest=P/'implementation-manifest.json';data=manifest.read_bytes();mh=hashlib.sha256(data).hexdigest();assert mh=='5ff67d4897f08c8b8bb85431fd6f72699f32de515c9da39f335d7dd52668e5ec'
 b=next(b for b in json.loads(data)['files'] if Path(b['path']).name=='HAR-IDX.npy');out['manifest_sha256']=mh;out['binding']=b
 p=Path(b['path']);before=p.stat();out['before']={k:getattr(before,k) for k in ['st_size','st_mtime_ns','st_ino','st_dev']};assert before.st_size==904062848
 h=hashlib.sha256()
 with p.open('rb') as f:
  with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mapped:
   for offset in range(0,before.st_size,32*1024*1024):
    length=min(32*1024*1024,before.st_size-offset);out['inflight_chunk_bytes']=length
    view=memoryview(mapped)[offset:offset+length]
    try:h.update(view)
    finally:view.release()
    out['bytes_consumed_complete_chunks']+=length;out['inflight_chunk_bytes']=0
    mapped.madvise(mmap.MADV_DONTNEED,offset,length)
 after=p.stat();out['after']={k:getattr(after,k) for k in ['st_size','st_mtime_ns','st_ino','st_dev']}
 assert out['before']==out['after'] and out['bytes_consumed_complete_chunks']==b['bytes']
 out['actual_sha256']=h.hexdigest();assert out['actual_sha256']==b['sha256'];out['status']='pass';save();print(json.dumps(out),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:
  save();raise
