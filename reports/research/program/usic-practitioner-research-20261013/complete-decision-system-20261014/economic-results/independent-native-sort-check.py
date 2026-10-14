import ast
import gzip
import hashlib
import json
import os
import resource
from pathlib import Path
from types import SimpleNamespace

E=Path(__file__).resolve().parent;ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(20,23))
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
packet_path=E/'native-sort-affected-review-packet.json'
assert bind(packet_path)['sha256']=='ad549440aa2d2222ec2181c2b058b0cfd75f10557dedf05e7c6a9b6e1c00433c'
packet=json.loads(packet_path.read_text());b=packet['bindings'];verified={}
prior=json.loads((ROOT/b['prior_grant']['path']).read_text()); march=prior['bindings']['March_source']
def check(obj):
    if isinstance(obj,dict):
        if 'path' in obj and 'sha256' in obj:
            if obj['path']==march['path']:
                assert obj==march;return
            p=ROOT/obj['path'];assert p.stat().st_size<2_000_000,str(p)
            actual=bind(p);assert actual['sha256']==obj['sha256'],str(p)
            assert 'bytes' not in obj or actual['bytes']==obj['bytes'],str(p)
            verified[str(p)]=actual['sha256']
        else:
            for x in obj.values():check(x)
    elif isinstance(obj,list):
        for x in obj:check(x)
check(packet);check(prior['bindings']['native_dependencies']);check(prior['bindings']['frame_result'])
assert json.loads((ROOT/'reports/research/control/owner-compute-hold.json').read_text())['research_paused'] is False
task=next(t for t in json.loads((ROOT/'reports/research/control/day-goal.json').read_text())['tasks'] if t['id']=='MARTIN-COMPLETE-DECISION-SYSTEM-20261014')
assert task['owner']==packet['author'] and task['status']=='running_complete_task'
old=(ROOT/b['old']['path']).read_text();new=(ROOT/b['candidate']['path']).read_text()
assert new==old.replace('engine.add_data(books)','engine.add_data(books, sort=False)',1).replace('engine.add_data(quotes)','engine.add_data(quotes, sort=False)',1)
engine_source=ROOT/'.venv/lib/python3.11/site-packages/nautilus_trader/backtest/engine.pyx'
source=engine_source.read_text();add=source[source.index('    def add_data('):source.index('    cdef void _add_data(',source.index('    def add_data('))]
assert 'bint validate = True' in add and 'bint sort = True' in add
assert 'self._data.extend(data)' in add and 'self._data = sorted(self._data, key=lambda x: x.ts_init)' in add
assert add.index('if validate:')<add.index('self._data.extend(data)')<add.index('if sort:')<add.index('self._data_iterator.add_data("backtest_data", self._data)')
assert 'self._data[data_priority] = sorted(data_list, key=lambda data: data.ts_init)' in source
def function(text,name):return next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.FunctionDef) and n.name==name)
groups=[[SimpleNamespace(ts_init=t,identity=(g,i)) for i,t in enumerate(times)] for g,times in enumerate(([2,1,2,1],[1,2,1],[2,1,2]))]
class InertEngine:
    def __init__(self):self.items=[];self.calls=[];self.ran=None
    def add_data(self,data,client_id=None,validate=True,sort=True):
        self.calls.append({'group':data[0].identity[0],'client':client_id,'validate':validate,'sort':sort})
        self.items.extend(data)
        if sort:self.items=sorted(self.items,key=lambda x:x.ts_init)
        # Existing iterator also sorts per add; no consumption until run.
        self.iterator=sorted(self.items,key=lambda x:x.ts_init)
    def run(self,streaming):assert streaming;self.ran=[x.identity for x in self.iterator]
    def clear_data(self):self.items=[]
observed=[]
for text in (old,new):
    ns={'causal_activity':lambda *a,**k:{'A'},'native_month':lambda *a,**k:(*groups,{'A':1}),'ClientId':lambda name:name}
    exec(compile(ast.Module(body=[function(text,'feed')],type_ignores=[]),'actual-feed-AST','exec'),ns)
    accounts=[(InertEngine(),SimpleNamespace()),(InertEngine(),SimpleNamespace())]
    values=ns['feed'](accounts,[{}],'O-H-L-C',{},None,afternoon=False)
    observed.append({'accounts':[{'calls':e.calls,'order':e.ran,'active':sorted(s.runtime_active_symbols)} for e,s in accounts],'return':values})
assert observed[0]['return']==observed[1]['return']
for ref,candidate in zip(observed[0]['accounts'],observed[1]['accounts'],strict=True):
    assert ref['order']==candidate['order'] and ref['active']==candidate['active']
    assert [x['sort'] for x in candidate['calls']]==[False,False,True]
    assert all(x['validate'] is True for x in candidate['calls'])
    assert [x['client'] for x in ref['calls']]==[x['client'] for x in candidate['calls']]
proof=json.loads((ROOT/b['native16proof']['path']).read_text())
assert proof['native_engines']==16 and len(proof['tests'])==4
for case in proof['tests']:
    assert case['reference']==case['bulk'] and case['events'][0]==case['events'][1]
    assert case['source_immutable'] and case['all_fields_equal']
prefix=json.loads((ROOT/b['stage_prefix']['path']).read_text());check(prefix['profile'])
metrics=json.loads((ROOT/prefix['profile']['path']).read_text());v=metrics['variants'][0]
assert v['minutes']==5070 and v['known'] and not v['complete']
timing=v['stage_timing'];close=sum(x['CPU'] for k,x in timing.items() if k.endswith(':on_data:close'))
decode=sum(x['CPU'] for k,x in timing.items() if k.endswith(':Frame_decode'))
all_callback=sum(x['CPU'] for k,x in timing.items() if ':on_data:' in k)
encoding=timing['source:native_month_encoding']['CPU']
for got,want in [(close,prefix['close_callback_inclusive_CPU']),(decode,prefix['frame_decode_nested_in_close_CPU']),(all_callback,prefix['all_on_data_callbacks_inclusive_CPU']),(encoding,prefix['source_encoding_CPU']),(v['CPU']-all_callback-encoding,prefix['feed_and_other_residual_CPU'])]:assert abs(got-want)<1e-9
partial_accounts=[]
for policy in ('P_SYSTEM','P_EMA'):
    p=(ROOT/prefix['profile']['path']).parent/('reference__'+policy+'.json.gz')
    with gzip.open(p,'rt') as f:obj=json.load(f)
    assert obj['full_month_clock_executed'] is False and obj['known_complete_month'] is False and obj['unknown'] is None
    partial_accounts.append(bind(p))
receipt=json.loads((ROOT/b['stage_receipt']['path']).read_text());assert receipt['status']=='settled' and receipt['charged_CPU']==73.54
check(receipt['inclusive_profile'])
costs=[]
for x in b['all_new_receipts']:
    r=json.loads((ROOT/x['path']).read_text());assert r['status']=='settled';costs.append(r['charged_CPU'])
assert abs(sum(costs)-43.59)<1e-8
driver=(ROOT/b['driver']['path']).read_text()
assert driver.index('empirical_limit(job)')<driver.index('import native_engine')<driver.index('module_spec.loader.exec_module(candidate_module)')
assert 'candidate_module.feed(' in driver and 'assert results["bulk__" + policy] == previous' in driver
assert 'partial_or_unknown_month_not_a_throughput_gate' in driver
old_driver=(E/'measure_reference_stages.py').read_text()
assert ast.dump(function(driver,'interpreted'),include_attributes=False)==ast.dump(function(old_driver,'interpreted'),include_attributes=False)
out={'verified_bindings':verified,'exact_two_keyword_diff':True,'actual_feed_AST_inert_calls':observed,'installed_engine_source':bind(engine_source),'validation_and_final_stable_sort_retained':True,'iterator_sort_still_present':True,'saved16engine_proof_deep_equal':True,'stage_prefix_minutes':5070,'stage_prefix_fullmonth_gate':False,'stage_partial_accounts':partial_accounts,'stage_timer_totals_recomputed':True,'stage_charge':73.54,'new_offline_charges':costs,'interpretation_AST_unchanged':True,'March_source_inherited_not_read':march,'current_review_native_engines':0,'current_review_native_CLI':0,'HTTP':0,'affinity':sorted(os.sched_getaffinity(0)),'maximum_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(E/'native-sort-independent-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in {'verified_bindings','actual_feed_AST_inert_calls'}}))
