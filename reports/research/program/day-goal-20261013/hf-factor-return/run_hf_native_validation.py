"""Actual full native validation; report same native guards and their real CPU use."""
import json,os,resource,signal,sys,traceback
from pathlib import Path
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
P=Path(__file__).parent;ROOT=Path.cwd();IT='t20261013_hf_factor_conditional_method';D=ROOT/'reports/research/iterations'/IT
limit=int(sys.argv[1]);resource.setrlimit(resource.RLIMIT_CPU,(limit,limit+1))
def cpu():
 r=resource.getrusage(resource.RUSAGE_SELF);return r.ru_utime+r.ru_stime
hashlog=[]
def partial(sig,frame):
 (P/'extension-native-partial.json').write_text(json.dumps({'status':'partial','completed_hash_calls':hashlog,'CPU':cpu(),'exit':90,'economic_execution_admitted':False},indent=2)+'\n');traceback.print_stack(frame);sys.exit(90)
signal.signal(signal.SIGXCPU,partial)
# Measurement wrapper only: every original streaming SHA call really executes, no cache/skip.
import open_composer.research.market_component as component
orig=component._sha256_file
def hashed(path):
 before=cpu();digest=orig(path);hashlog.append({'path':str(path),'bytes':path.stat().st_size,'CPU':cpu()-before,'sha256':digest});return digest
component._sha256_file=hashed
from open_composer.research.iteration_dossier import validate_iteration_dossier
r=validate_iteration_dossier(IT,ROOT,stage='pre-backtest')
out={'native_function':'validate_iteration_dossier','iter_id':IT,'stage':'pre-backtest','status':r.status,'blocked':r.blocked,'warnings':r.warnings,'info':r.info,'actual_hash_calls':len(hashlog),'actual_hash_bytes':sum(r['bytes'] for r in hashlog),'hash_calls':hashlog,'CPU':cpu(),'memory_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'guard_cache_or_skip':False,'economic_runs':0}
(P/'extension-native-gate.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':r.status,'blocked':r.blocked,'actual_hash_calls':len(hashlog),'actual_hash_bytes':out['actual_hash_bytes'],'CPU':cpu()}));assert r.status=='ok',r.blocked
