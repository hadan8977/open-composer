import hashlib,json,mmap,os,resource,signal,sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(24,25))
assert os.sched_getaffinity(0)=={0}
P=Path(__file__).parent
out={'status':'partial','bytes_consumed_complete_chunks':0,'inflight_chunk_bytes':0,'method':'read-only mmap; 32MiB memoryview update; release and MADV_DONTNEED after every chunk','affinity':[0],'soft_hard_CPU':[24,25], 'fresh_start_from_zero':True, 'prior_partial_not_resumed':True}
def usage():
 u=resource.getrusage(resource.RUSAGE_SELF);return {'CPU_seconds':u.ru_utime+u.ru_stime,'RSS_KiB':u.ru_maxrss}
def save(sig=None,frame=None):
 out['resource']=usage();(P/'independent-final-HAR-IDX-hash.json').write_text(json.dumps(out,indent=2)+'\n')
 if sig:sys.exit(90)
signal.signal(signal.SIGXCPU,save)
def main():
 grant_path=P/'root-preparation-native-extension.json';grant_bytes=grant_path.read_bytes();grant=json.loads(grant_bytes)
 assert grant['decision']=='approve_preparation_native_resource_amendment' and grant['allocation']['combined_preparation_ceiling_CPU']==2300 and grant['independent_reviewer']=='ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3'
 out['new_root_grant']={'path':str(grant_path),'sha256':hashlib.sha256(grant_bytes).hexdigest()}
 manifest=P/'implementation-manifest.json';data=manifest.read_bytes();mh=hashlib.sha256(data).hexdigest();assert mh=='5ff67d4897f08c8b8bb85431fd6f72699f32de515c9da39f335d7dd52668e5ec'
 b=next(b for b in json.loads(data)['files'] if Path(b['path']).name=='HAR-IDX.npy');out['manifest_sha256']=mh;out['binding']=b
 p=Path(b['path']);before=p.stat();out['before']={k:getattr(before,k) for k in ['st_size','st_mtime_ns','st_ino','st_dev']};assert before.st_size==904062848
 h=hashlib.sha256()
 with p.open('rb') as f:
  opened=os.fstat(f.fileno());assert all(getattr(opened,k)==out['before'][k] for k in out['before'])
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
