import hashlib,json,math,os,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
R=Path('/root/codex-test/open-composer');E=R/'reports/research/program/day-goal-20261013/equity-role';I=R/'reports/research/iterations/eq_role_source_20261013'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc)
def atomic(p,d):
 t=p.with_suffix('.tmp');t.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
 with t.open('rb') as f:os.fsync(f.fileno())
 os.replace(t,p)
statep=E/'current-state.json';s=json.load(open(statep));a=json.load(open(E/'root-source-full-fit-admission.json'))
assert a['verdict']=='admit_source_full_fits'
assert a['implementation_sha256']==sha(E/'source-implementation-manifest.json')
assert a['qualified_input_sha256']==sha(E/'qualified-source.npz')
for p in (E/'campaign-admitted-gate.json',E/'knowledge-admitted-gate.json',E/'iteration-admitted-gate.json'):
 assert json.load(open(p))['status']=='ok',str(p)
assert not (E/'source-results.json').exists() and not (E/'source-evaluation-arrays.npz').exists()
mem=subprocess.run(['python3','scripts/memory_budget.py','admit','--kind','job','--mem','900'],cwd=R,capture_output=True,text=True)
(E/'source-memory-admission.txt').write_text(mem.stdout+mem.stderr)
if mem.returncode:raise SystemExit('fresh memory admission refused; no fit reservation made')
clock=datetime.fromisoformat(s['continuation_resource_clock_utc'].replace('Z','+00:00'))
charged=240.807+(now()-clock).total_seconds();remaining=math.floor(2700-charged)
if remaining<=0:raise SystemExit('cumulative source wall cap exhausted before launch')
cpu=min(os.sched_getaffinity(0));start={'owner':s['owner'],'started_at_utc':now().isoformat(),'reserved_OLS_fit_attempts':1902,'reserved_total':1902,'new_full_evaluation_launches':1,'implementation_sha256':a['implementation_sha256'],'qualified_input_sha256':a['qualified_input_sha256'],'cpu_affinity':[cpu],'thread_limits':1,'memory_MiB_limit':900,'qualification_wall_seconds_cumulative':240.807,'conservative_wall_charged_before_launch':charged,'remaining_timeout_seconds':remaining,'automatic_replay_allowed':False,'on_unknown_failure':'Retain1902 reservation; no automatic whole-run replay.'}
marker=E/'evaluate-start.json';fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(json.dumps(start,indent=2)+'\n');f.flush();os.fsync(f.fileno())
dirfd=os.open(E,os.O_DIRECTORY);os.fsync(dirfd);os.close(dirfd)
s.update(status='source_unique_evaluation_running',updated_at_utc=now().isoformat(),source_fit_attempts_reserved=1902,source_fit_attempts_actual=None,source_fit_attempts_charge=1902,source_full_evaluation_launches=1,source_evaluate_start_marker=str(marker.relative_to(R)),native_direction_gate='ok',native_campaign_gate='ok',native_knowledge_gate='ok',native_iteration_gate='ok',source_memory_admission=mem.stdout.strip(),source_conservative_wall_charged_before_launch=charged,next_action='Unique approved S0-S6 evaluation; no whole-run automatic replay on unknown failure.')
atomic(statep,s)
env=os.environ.copy();env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
cmd=['scripts/run_capped.sh','--mem','900M','--wait-min','0','--','/usr/bin/time','-v','-o',str(E/'source-evaluate-resource.txt'),'timeout','--signal=TERM',str(remaining)+'s','taskset','-c',str(cpu),str(R/'.venv/bin/python'),str(E/'source_method.py'),'evaluate','--admission',str(E/'root-source-full-fit-admission.json')]
begin=time.monotonic()
with (E/'source-evaluate.stdout.txt').open('w') as out,(E/'source-evaluate.stderr.txt').open('w') as err:
 r=subprocess.run(cmd,cwd=R,env=env,stdout=out,stderr=err)
elapsed=time.monotonic()-begin
usage={'returncode':r.returncode,'finished_at_utc':now().isoformat(),'launcher_wall_seconds':elapsed,'qualification_wall_seconds_cumulative':240.807,'continuation_wall_upper_including_metadata_and_owner_work':(now()-clock).total_seconds(),'source_cumulative_conservative_wall_upper':240.807+(now()-clock).total_seconds(),'source_reserved_OLS_fit_attempts':1902,'cloud_USD':0,'resource_log':str((E/'source-evaluate-resource.txt').relative_to(R))}
s=json.load(open(statep))
if r.returncode==0:
 result=json.load(open(E/'source-results.json'));assert result['resource_use']['OLS_fit_attempts']==1902
 usage['source_actual_OLS_fit_attempts']=1902;s.update(status='source_results_ready_interpreting',source_fit_attempts_actual=1902,source_economic_evaluations=7,new_model_fits=1902,new_backtests=7,source_evaluation_results=str((E/'source-results.json').relative_to(R)))
else:
 usage['source_actual_OLS_fit_attempts']='unknown_reserved1902';s.update(status='source_unique_evaluation_failed_no_automatic_replay',source_fit_attempts_actual='unknown_reserved1902')
usage['results_fresh']=r.returncode==0
atomic(E/'source-evaluate-usage.json',usage);s.update(updated_at_utc=now().isoformat(),source_evaluate_usage=str((E/'source-evaluate-usage.json').relative_to(R)),source_cumulative_conservative_wall_upper=usage['source_cumulative_conservative_wall_upper']);atomic(statep,s)
print(json.dumps(usage,indent=2));raise SystemExit(r.returncode)
