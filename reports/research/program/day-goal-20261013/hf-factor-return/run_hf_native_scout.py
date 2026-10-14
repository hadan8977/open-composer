"""Actual native scout, with phase/CPU diagnostics and no external requests."""
import json,os,resource,signal,sys,traceback
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});resource.setrlimit(resource.RLIMIT_CPU,(60,61))
P=Path(__file__).parent;phase='import';start=resource.getrusage(resource.RUSAGE_SELF)
def cpu():
 r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
def fail(sig,frame):
 (P/'extension-scout-partial-002.json').write_text(json.dumps({'phase':phase,'CPU':cpu(),'exit':90,'economic_runs':0},indent=2)+'\n')
 traceback.print_stack(frame);sys.exit(90)
signal.signal(signal.SIGXCPU,fail)
import open_composer.research.knowledge_memory as k
for name in ['_collect_sources','_collect_empirical_memory','_collect_model_memory']:
 fn=getattr(k,name)
 def wrapped(*args,_fn=fn,_name=name,**kwargs):
  global phase
  phase=_name;begin=cpu();print(json.dumps({'phase':phase,'begin_CPU':begin}),flush=True);r=_fn(*args,**kwargs);print(json.dumps({'phase':phase,'CPU':cpu()-begin,'rows':len(r)}),flush=True);return r
 setattr(k,name,wrapped)
def no_fetch(*args):raise RuntimeError('No source requests authorized; existing curated sources only')
r=k.scout_knowledge('t20261013_hf_factor_conditional_method',Path.cwd(),fetcher=no_fetch)
(P/'extension-scout-native-receipt.json').write_text(json.dumps({'native_function':'scout_knowledge','result':r.payload,'path':str(r.report_path),'source_requests':0,'economic_runs':0},ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':'native_scout_finished','path':str(r.report_path),'candidates':r.payload.get('candidate_count'),'sources_fetched':0,'CPU':cpu()}))
