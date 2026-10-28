"""Prospective fixed-source lifecycle; import is inert and grants no entry."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import uuid

import next_session_capacity_M3 as capacity

ROOT=Path(__file__).resolve().parent
T=ROOT.parent
REPO=capacity.REPO
TASK=capacity.TASK
SESSION=capacity.SESSION
PEER=capacity.PEER
STAGES={'core':'core-source-02','ETF':'ETF-source-01'}
binding,checked,load,canonical,now,clock=capacity.binding,capacity.checked,capacity.load,capacity.canonical,capacity.now,capacity.clock


def clean(value):
    if type(value).__module__.startswith('numpy'):
        return clean(value.tolist())
    if type(value) is float:
        assert math.isfinite(value)
    if type(value) is dict:
        assert all(type(k) is str for k in value)
        return {k:clean(v) for k,v in value.items()}
    if type(value) in [list,tuple]:
        return [clean(v) for v in value]
    assert value is None or type(value) in [str,int,float,bool]
    return value


def receive_definition():
    contract_path=ROOT/'next-session-contract-and-storage-M1.json'
    plan_path=ROOT/'next-session-source-plan-M1.json'
    contract,plan=load(contract_path),load(plan_path)
    for path,target,verdict,flag in [
        (ROOT/'independent-next-session-definition-review-M1.json',contract_path,'approve_prospective_application_definition','prospective_application_definition_accepted'),
        (ROOT/'independent-next-session-source-contract-review-M1.json',plan_path,'approve_source_contract','source_basis_branch_accepted')]:
        review=load(path)
        assert review['task_id']==TASK and review['session_id']==SESSION
        assert review['reviewer']==PEER and review['independent'] is True
        assert review['target']==binding(target) and review['verdict']==verdict and review[flag] is True
    assert contract['task_id']==plan['task_id']==TASK and contract['session_id']==plan['session_id']==SESSION
    assert contract['reference_day']==plan['reference_day']=='2026-10-20'
    assert contract['application_day']==plan['application_day']=='2026-10-21'
    checked(contract['Main'],REPO/'reports/research/program/owner-profit-delivery-plan-20261017/paper-delivery/preopen-20261020/main-next-eligible-session-continuation-decision.json')
    assert contract['Main']['sha256']=='5b04ca3927be6ec215450e915630dd0ca0feffe2a558b141cd8efcd7a5391180'
    assert plan['source_window']==contract['calendar']['proposed_source_window']==['2026-10-21T00:00:00Z','2026-10-21T12:45:00Z']
    return contract,plan


def authority():
    contract,plan=receive_definition()
    hold=load(REPO/'reports/research/control/owner-compute-hold.json')
    assert hold['paper_deployment_allowed'] is True
    assert clock(plan['source_window'][0])<=clock(now())<clock(plan['source_window'][1]), 'Actual next-session source window inactive/expired'
    return contract,plan


def code(proof=None):
    if proof is None:
        pointer=load(ROOT/'source-implementation-pointer.json')
        assert pointer['task_id']==TASK and pointer['session_id']==SESSION
        proof=dict(manifest=pointer['manifest'],review=pointer['review'])
    mp,rp=checked(proof['manifest']),checked(proof['review'])
    assert mp.parent==rp.parent==ROOT
    mf,review=load(mp),load(rp)
    assert mf['task_id']==review['task_id']==TASK and mf['session_id']==review['session_id']==SESSION
    assert review['reviewer']==PEER and review['independent'] is True
    assert review['verdict']=='approve_source_implementation' and review['source_implementation_accepted'] is True
    assert review['native_launcher_accepted'] is True and review['target']==proof['manifest']
    assert review['source_plan']==mf['source_plan']==binding(ROOT/'next-session-source-plan-M1.json')
    assert mf['contract']==binding(ROOT/'next-session-contract-and-storage-M1.json')
    rows=mf['files'];assert rows and len({r['path'] for r in rows})==len(rows)
    for row in rows:checked(row)
    assert binding(__file__) in rows
    return proof


def reserve():
    available=int(next(v.split()[1] for v in Path('/proc/meminfo').read_text().splitlines() if v.startswith('MemAvailable:')))*1024
    assert available>=524288000, 'Preserve owner500MiB reserve'
    return available


def kernel():
    group=Path('/sys/fs/cgroup')/Path('/proc/self/cgroup').read_text().split('::',1)[1].strip().lstrip('/')
    result={k:(group/k).read_text().strip() for k in ['memory.max','memory.swap.max','cpu.max']}
    result['cpu_affinity']=sorted(os.sched_getaffinity(0))
    result['threads']={k:os.environ.get(k) for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','PYTHONDONTWRITEBYTECODE']}
    assert result['memory.max']=='419430400' and result['memory.swap.max']=='0'
    assert result['cpu.max'].split()[0]=='max' and result['cpu_affinity']==[0]
    assert all(v=='1' for v in result['threads'].values())
    return result


def process_identity():
    tail=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=os.getpid(),start_ticks=int(tail[19]))


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,canonical(path))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def save_bytes(path,payload,*,capacity_rows=None):
    path=canonical(path);assert path.is_relative_to(ROOT) and type(payload) is bytes
    assert not path.exists(), 'Never replace/truncate retained source evidence'
    missing=[];parent=path.parent
    while not parent.exists():
        assert parent.is_relative_to(ROOT)
        missing.append(parent);parent=parent.parent
    fs=os.statvfs(REPO);unit=fs.f_frsize
    bound=((len(payload)+unit-1)//unit+len(missing)+1)*unit
    kwargs={} if capacity_rows is None else dict(context_row=capacity_rows['context'],review_row=capacity_rows['review'])
    capacity.guard_write(bound,bound,**kwargs)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:
        f.write(payload);f.flush();os.fsync(f.fileno())
    sync_directories([path.parent,*missing,*[p.parent for p in missing]])
    capacity.guard_write(0,0,**kwargs)
    return binding(path)


def sync_directories(paths):
    """Persist file names and every newly created ancestor entry before use."""
    for path in dict.fromkeys(paths):
        fd=os.open(canonical(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)


def save(path,value,*,capacity_rows=None):
    # JSON serialization detaches every nested mutable control before writing.
    return save_bytes(path,(json.dumps(clean(value),indent=2,allow_nan=False)+'\n').encode(),capacity_rows=capacity_rows)


def registry():
    path=REPO/'capabilities/registry.yaml';before=binding(path)
    argv=[str(REPO/'.venv/bin/python'),'-c','import json; from pathlib import Path; from open_composer.capabilities.registry import get_capability; print(json.dumps(get_capability("market.alpaca_bars",Path.cwd()).model_dump(mode="json")))']
    result=subprocess.run(argv,cwd=REPO,capture_output=True,text=True,timeout=30,check=True)
    actual=json.loads(result.stdout)
    assert binding(path)==before and actual==load(T/'capability-snapshot.json')['capability']
    return dict(argv=argv,registry=before,actual_capability=actual,received_at=now(),provider_calls=0,unmodified_registered_receiver=True)


def start(group):
    assert group in STAGES
    authority();k=kernel();reserve();proof=code();stage=STAGES[group];d=ROOT/stage
    assert not d.exists(), 'Existing complete/partial source needs factual reception/recovery; never a replay'
    receive_recovery(group)
    reg=registry();reserve();authority();k=kernel()
    cap=capacity.guard_write();rows={key:cap[key] for key in ['context','review']}
    native=dict(task_id=TASK,session_id=SESSION,stage=stage,group=group,invocation=uuid.uuid4().hex,
        process=process_identity(),at=now(),kernel=k,registry=reg,code=proof,capacity=cap,
        contract=binding(ROOT/'next-session-contract-and-storage-M1.json'),source_plan=binding(ROOT/'next-session-source-plan-M1.json'),
        source_only=True,model_fit_account_or_operating_go=False,recovery=receive_recovery(group))
    save(d/'native-go.json',native,capacity_rows=rows)
    save(d/'started.json',dict(task_id=TASK,session_id=SESSION,stage=stage,native=binding(d/'native-go.json'),started_at=now()),capacity_rows=rows)
    claim=dict(task_id=TASK,session_id=SESSION,stage=stage,invocation=native['invocation'],process=native['process'],native=binding(d/'native-go.json'),started=binding(d/'started.json'),claimed_at=now())
    save(d/'worker-started.json',claim,capacity_rows=rows)
    return native,claim


def receive_native(group):
    stage=STAGES[group];d=ROOT/stage
    start=load(d/'started.json');native=load(checked(start['native'],d/'native-go.json'));claim=load(d/'worker-started.json')
    assert all(v['task_id']==TASK and v['session_id']==SESSION and v['stage']==stage for v in [start,native,claim])
    assert native['group']==group and native['source_only'] is True and native['model_fit_account_or_operating_go'] is False
    if group=='core':
        assert native['recovery']==binding(ROOT/'core-source-recovery-plan-02.json')
        checked(native['recovery'])
    assert claim['started']==binding(d/'started.json') and claim['native']==start['native']
    assert claim['process']==native['process'] and claim['invocation']==native['invocation']
    assert type(native['invocation']) is str and len(native['invocation'])==32 and all(v in '0123456789abcdef' for v in native['invocation'])
    assert all(type(native['process'][k]) is int and native['process'][k]>0 for k in ['pid','start_ticks'])
    k=native['kernel']
    assert k['memory.max']=='419430400' and k['memory.swap.max']=='0'
    assert k['cpu.max'].split()[0]=='max' and k['cpu_affinity']==[0]
    assert k['threads']=={v:'1' for v in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','PYTHONDONTWRITEBYTECODE']}
    code(native['code'])
    assert native['contract']==binding(ROOT/'next-session-contract-and-storage-M1.json') and native['source_plan']==binding(ROOT/'next-session-source-plan-M1.json')
    capacity.receive_capacity_context(native['capacity']['context'],native['capacity']['review'])
    assert native['capacity']['receipt']['sha256']==capacity.RECEIPT_SHA
    checked(native['registry']['registry'],REPO/'capabilities/registry.yaml')
    assert native['registry']['actual_capability']==load(T/'capability-snapshot.json')['capability']
    assert native['registry']['unmodified_registered_receiver'] is True and native['registry']['provider_calls']==0
    assert native['registry']['argv']==[str(REPO/'.venv/bin/python'),'-c','import json; from pathlib import Path; from open_composer.capabilities.registry import get_capability; print(json.dumps(get_capability("market.alpaca_bars",Path.cwd()).model_dump(mode="json")))']
    _,plan=receive_definition()
    assert clock(plan['source_window'][0])<=clock(native['at'])<clock(plan['source_window'][1])
    assert clock(native['registry']['received_at'])<=clock(native['at'])<=clock(start['started_at'])<=clock(claim['claimed_at'])<=clock(now())
    return native,claim


def computing(group):
    authority();kernel();reserve();native,claim=receive_native(group)
    assert native['process']==process_identity()
    d=ROOT/STAGES[group]
    assert not any((d/v).exists() for v in ['output.json','seal.json','completed.json'])
    capacity.guard_write(context_row=native['capacity']['context'],review_row=native['capacity']['review'])
    return native,claim


def finish(group,output):
    native,claim=computing(group);d=ROOT/STAGES[group];rows={k:native['capacity'][k] for k in ['context','review']}
    same_group(group,output,native,claim)
    assert clock(claim['claimed_at'])<=clock(output['computed_started_at'])<=clock(output['computed_completed_at'])<=clock(now())
    save(d/'output.json',dict(clean(output),task_id=TASK,session_id=SESSION,stage=STAGES[group]),capacity_rows=rows)
    save(d/'seal.json',dict(started=binding(d/'started.json'),worker=binding(d/'worker-started.json'),output=binding(d/'output.json'),sealed_at=now()),capacity_rows=rows)
    save(d/'completed.json',dict(started=binding(d/'started.json'),worker=binding(d/'worker-started.json'),seal=binding(d/'seal.json'),completed_at=now()),capacity_rows=rows)
    return receive_stage(group)


def receive_stage(group):
    native,claim=receive_native(group);d=ROOT/STAGES[group]
    seal,done=load(d/'seal.json'),load(d/'completed.json')
    assert seal['started']==done['started']==claim['started']==binding(d/'started.json')
    assert seal['worker']==done['worker']==binding(d/'worker-started.json') and done['seal']==binding(d/'seal.json')
    out=load(checked(seal['output'],d/'output.json'))
    assert out['task_id']==TASK and out['session_id']==SESSION and out['stage']==STAGES[group]
    same_group(group,out,native,claim)
    _,plan=receive_definition()
    assert clock(claim['claimed_at'])<=clock(out['computed_started_at'])<=clock(out['computed_completed_at'])<=clock(seal['sealed_at'])<=clock(done['completed_at'])<=clock(plan['source_window'][1])
    assert clock(done['completed_at'])<=clock(now())
    return out


def same_group(group,output,native,claim):
    """One outer source group, native claim and canonical context, both paths."""
    assert group in STAGES and output['group']==group
    stage=STAGES[group];d=ROOT/stage
    assert output.get('stage',stage)==native['stage']==claim['stage']==stage
    assert native['group']==group
    context=load(checked(output['context'],d/'context.json'))
    assert context['group']==group and context['task_id']==TASK and context['session_id']==SESSION
    assert context['started']==claim['started']==binding(d/'started.json')
    assert context['worker']==binding(d/'worker-started.json')
    assert context['invocation']==native['invocation']==claim['invocation']
    assert context['code']==output['code']==native['code']
    assert context['source_plan']==output['source_plan']==native['source_plan']
    assert context['contract']==native['contract']
    assert context['capacity']=={k:native['capacity'][k] for k in ['context','review']}
    assert context['local_projection']==output['local_projection']
    if group=='core':checked(context['local_projection'],d/'local-projection.json')
    else:assert context['local_projection'] is None
    return context


def receive_recovery(group):
    """Exact failed prior scope; no completed request is eligible for replay."""
    if group!='core':return None
    row=binding(ROOT/'core-source-recovery-plan-02.json')
    proof=code();mf=load(checked(proof['manifest']));assert row in mf['files']
    rr=load(checked(proof['review']));assert rr['source_recovery_accepted'] is True
    plan=load(row['path']);assert plan['task_id']==TASK and plan['session_id']==SESSION
    assert plan['prior_stage']=='core-source-01' and plan['successor_stage']==STAGES[group]=='core-source-02'
    assert plan['completed_requests']==0 and plan['physical_HTTP_requests']==0 and plan['unchanged_retry_permitted'] is False
    for item in plan['prior_bindings']:checked(item)
    event=load(checked(plan['prior_exit']));assert event['exit_code']==1 and event['completed'] is None and event['completion_received'] is False
    worker=load(checked(plan['prior_worker']));process=worker['process'];pid=Path('/proc')/str(process['pid'])/'stat'
    if pid.exists():assert int(pid.read_text().rsplit(')',1)[1].split()[19])!=process['start_ticks'], 'Original worker remains live'
    prior=ROOT/plan['prior_stage']
    assert not any((prior/x).exists() for x in ['context.json','captures','output.json','seal.json','completed.json'])
    actual=[binding(p)for p in sorted(prior.rglob('*'))if p.is_file()]
    assert actual==plan['prior_stage_files'], 'Prior partial inventory changed; receive actual difference'
    assert plan['not_before']=='2026-10-21T00:20:00Z' and clock(plan['not_before'])<=clock(now())
    assert plan['source_plan']==binding(ROOT/'next-session-source-plan-M1.json')
    return row
