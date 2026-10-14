import ast
import hashlib
import json
import math
import os
import resource
import types
from pathlib import Path

E=Path(__file__).resolve().parent
ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(40,45))
packet=json.loads((E/'source-clock-G1-review-packet.json').read_text())
verified={}
def check(x):
    if isinstance(x,dict):
        if 'path' in x and 'sha256' in x:
            p=ROOT/x['path']
            assert p.stat().st_size<2_000_000, f'Not a small binding: {p}'
            with p.open('rb') as f:
                digest=hashlib.file_digest(f,'sha256').hexdigest()
            assert digest==x['sha256'], str(p)
            if 'bytes' in x:
                assert p.stat().st_size==x['bytes'], str(p)
            verified[str(p)]=digest
        else:
            for y in x.values(): check(y)
    elif isinstance(x,list):
        for y in x: check(y)
check(packet)
manifest=json.loads((E/'source-clock-implementation-manifest.json').read_text())
check(manifest)
prior=json.loads((ROOT/packet['bindings']['prior_component_review']['path']).read_text())
assert prior['implementation_semantics_accepted'] is True
assert [x['id'] for x in prior['required_corrections']]==['G1']
def tree(path): return ast.parse(Path(path).read_text())
def functions(t): return {n.name:n for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def normalized(t): return ast.dump(t,include_attributes=False)
def remove_rearm(fn):
    fn.body=[n for n in fn.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='empirical_limit')]
    return fn
oldlib=functions(tree(ROOT/packet['bindings']['old_library']['path']))
newlib=functions(tree(ROOT/packet['bindings']['library']['path']))
assert oldlib.keys()==newlib.keys()
for name in oldlib:
    current=newlib[name]
    if name=='real_source_admission': current=remove_rearm(current)
    assert normalized(oldlib[name])==normalized(current),name
driver=tree(ROOT/packet['bindings']['driver']['path'])
assert not any(isinstance(n,ast.ImportFrom) and n.module=='source_clock_native' for n in driver.body)
main=functions(driver)['main']
trybody=next(n for n in main.body if isinstance(n,ast.Try)).body
def callname(n):
    return n.value.func.id if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) else None
order=[callname(n) for n in trybody]
native=order.index('native_admission'); phase=order.index('phase_admission'); rearm=order.index('empirical_limit')
heavy=next(i for i,n in enumerate(trybody) if isinstance(n,ast.ImportFrom) and n.module=='source_clock_native')
assert native<phase<rearm<heavy
oldmain=functions(tree(ROOT/packet['bindings']['old_driver']['path']))['main']
trybody[:]=[n for n in trybody if callname(n)!='empirical_limit' and not(isinstance(n,ast.ImportFrom) and n.module=='source_clock_native')]
assert normalized(main)==normalized(oldmain),'driver mathematical/control code changed beyond G1'
guard=functions(tree(ROOT/packet['bindings']['library']['path']))['real_source_admission']
guardcalls=[callname(n) for n in guard.body]
assert guardcalls.index('phase_admission')<guardcalls.index('empirical_limit')
helper=functions(tree(E.parent/'code/consumer_admission.py'))['empirical_limit']
limits=[]; child=[0]
fake_resource=types.SimpleNamespace(RLIMIT_CPU=0,setrlimit=lambda kind,value:limits.append(value))
fake_signal=types.SimpleNamespace(SIGXCPU=24,signal=lambda *a:None)
ns={'receipt':lambda job:dict(empirical_CPU_upper=180,launcher_unknown_CPU=5,runtime_actual_CPU=0),'usage':lambda:(1.,child[0]),'math':math,'resource':fake_resource,'signal':fake_signal}
exec(compile(ast.Module(body=[helper],type_ignores=[]),'actual-helper-AST','exec'),ns)
ns['empirical_limit']('INERT_NOT_PERMISSION')
child[0]=30
ns['empirical_limit']('INERT_NOT_PERMISSION')
assert limits==[(165,173),(135,143)]
bindings=prior['bindings'].copy()
bindings.pop('postpacket_noncomponent_settlement',None)
bindings.update(review_packet={'path':str((E/'source-clock-G1-review-packet.json').relative_to(ROOT)),'sha256':hashlib.sha256((E/'source-clock-G1-review-packet.json').read_bytes()).hexdigest()},implementation_manifest=packet['bindings']['implementation_manifest'],driver=packet['bindings']['driver'],component_files=manifest['component_files'],fixtures=manifest['fixtures'],prior_component_review=packet['bindings']['prior_component_review'],G1_inert_proof=packet['bindings']['G1_inert_proof'])
check(bindings)
verification={'verified_small_bindings':verified,'driver_order':['native_admission','phase_admission','empirical_limit','lazy source_clock_native import'],'library_order':['phase_admission','empirical_limit','source/fixture validation'],'actual_helper_fake_usage_limits':limits,'all_nonadmission_library_AST_equal':True,'driver_main_AST_equal_after_removing_exact_G1_statements':True,'affinity':sorted(os.sched_getaffinity(0)),'maximum_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'native_CLI':0,'engines':0,'HTTP':0,'large_input_scans':0}
(E/'source-clock-G1-independent-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
(E/'source-clock-G1-independent-current-bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
print(json.dumps({k:v for k,v in verification.items() if k!='verified_small_bindings'}))
