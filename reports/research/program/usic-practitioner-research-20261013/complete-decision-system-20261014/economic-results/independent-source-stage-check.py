import ast
import gzip
import hashlib
import importlib.util
import json
import os
import resource
import sys
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

E=Path(__file__).resolve().parent;P=E.parent;ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(35,40))
from nautilus_trader.model.objects import Money
from nautilus_trader.model.currencies import USD
assert str(Money(Decimal('.905'),USD))=='0.91 USD'
packet_path=E/'source-stage-actual-result-affected-review-packet.json'
assert hashlib.sha256(packet_path.read_bytes()).hexdigest()=='b2af1a4b36d2bab9049423d42483e724d69596c4f743ea43e28fc647d946f434'
packet=json.loads(packet_path.read_text()); b=packet['bindings']; verified={}
def check(x):
    if isinstance(x,dict):
        if 'path' in x and 'sha256' in x:
            if x['path']==b['March_source']['path']:
                assert x==b['March_source']; return
            p=ROOT/x['path']; assert p.stat().st_size<2_000_000,str(p)
            with p.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
            assert h==x['sha256'],str(p)
            if 'bytes' in x: assert x['bytes']==p.stat().st_size,str(p)
            verified[str(p)]=h
        else:
            for v in x.values(): check(v)
    elif isinstance(x,list):
        for v in x: check(v)
def read(binding): return json.loads((ROOT/binding['path']).read_text())
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
check(packet)
for key in ('source_receipt','March_receipt','offline_entry_receipt'):
    r=read(b[key]); assert r['status']=='settled'
    if 'inclusive_profile' in r: check(r['inclusive_profile'])
assert Decimal(str(read(b['source_receipt'])['charged_CPU']))==Decimal('35.03')
assert Decimal(str(read(b['March_receipt'])['charged_CPU']))==Decimal('125.73')
source_review=read(b['source_V2_review']);check(source_review['bindings']['fixtures'])
fixtures={f['id']:f for f in read(source_review['bindings']['fixtures'])['fixtures']}
source=load('stage_review_source_clock',E/'source_clock.py')
raw={}; rows=[]; engines=0; valid_closed=0
interpret={r['id']:r for r in read(b['source_V2_interpretation'])['rows']}
native_by_id={read(x)['fixture']:read(x)['native'] for x in b['source_V2_native_files']}
for binding in b['source_V2_results']:
    result=read(binding); f=fixtures[result['fixture']]; n=result['native_quote_research_proxy']
    assert n==native_by_id[f['id']]
    engines+=n['native_engines']
    reports=n.get('native_reports',[])
    entry=[r for r in reports if r['order_id']==f['id']+'-entry']
    exits=[r for r in reports if r['order_id']==f['id']+'-entry-protect']
    protection=[a for a in n.get('audit',[]) if a['action']=='native_submission' and a['intent_id']==f['id']+'-entry-protect']
    if f['initial_R0_status']=='positive':
        assert n['native_engines']==1 and len(entry)==1 and protection
        e=entry[0]
        assert e['ns']==f['entry_submit_ns']==f['expected_terminal_fill_ns']
        assert Decimal(e['price'])==Decimal(f['expected_initial_fill_price'])
        assert Decimal(e['quantity'])==f['quantity']
        R0=Decimal(f['quantity'])*(Decimal(f['initial_reference'])-Decimal(f['stop']))
        assert abs(Decimal(str(n['initial_R0']))-R0)<Decimal('1e-10')
    else:
        assert n['native_engines']==0 and n['R'] is None and not reports
    for r in reports:
        expected=(Decimal(r['price'])*Decimal(r['quantity'])*Decimal('.002')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        assert Decimal(r['commission'].split()[0])==expected,(f['id'],r)
    if exits and not n.get('unknown'):
        assert len(exits)==1
        q=Decimal(f['quantity']);fees=sum(Decimal(r['commission'].split()[0]) for r in reports)
        net=(Decimal(exits[0]['price'])-Decimal(entry[0]['price']))*q-fees
        assert len(n['closed_R'])==1 and abs(Decimal(str(n['closed_R'][0]))-net/R0)<Decimal('1e-9')
        valid_closed+=1
    data={}
    for s in f['source_versions']:
        check(s)
        kind='quotes' if '_quotes.bin' in s['path'] else 'trades'
        if s['path'] not in raw: raw[s['path']]=source.parse_source((ROOT/s['path']).read_bytes(),kind,s['sha256'])[0]
        data[kind]=raw[s['path']]
    setup=source.StopSetup(Decimal(f['stop']),entry[0]['ns'] if entry else None,protection[0]['native_at_ns'] if protection else None,f['quantity'],f['maximum_observed_quote_age_ns'])
    annotations=json.loads(json.dumps([asdict(r) for r in source.stop_reference(data['quotes'],data['trades'],setup)]))
    assert annotations==result['necessary_observed_price_reference']
    if n.get('unknown'):
        assert n['closed_R']==n['firstunknown']['known_prefix_closed_R']
        assert n['feedback_after']==n['firstunknown']['feedback']
        assert n['R'] is None and n['native_cash'] is None
    trues=[r['event_ns'] for r in annotations if r['observed_price_reference'] is True]
    declared=interpret[f['id']]
    assert declared['observed_necessary_true_count']==len(trues)
    assert declared['first_observed_necessary_true_ns']==(trues[0] if trues else None)
    assert result['full_strategy_PnL'] is None and result['broker_stop_election']=='unknown'
    assert result['continuous_price_coverage_certified'] is False
    rows.append({'id':f['id'],'engines':n['native_engines'],'unknown':n.get('unknown'),'entry_ns':entry[0]['ns'] if entry else None,'exit_ns':exits[0]['ns'] if exits else None,'first_necessary_true_ns':trues[0] if trues else None,'closed_R_only_known_prefix':n.get('closed_R')})
assert engines==10 and len(rows)==12
accept=read(b['original_March_acceptance']);assert accept['full_fixed_clock_per_account_minutes']==7800
assert accept['variants'][0]['events']==accept['variants'][1]['events']
for v in accept['variants']: assert v['minutes']==7800 and v['complete'] and v['known']
persisted={Path(x['path']).name:x for x in b['March_persisted_accounts']}
march_checks=[]
for policy in ('P_SYSTEM','P_EMA'):
    values=[]
    for name in ('reference','reuse'):
        path=ROOT/persisted[name+'__'+policy+'.json.gz']['path']
        with gzip.open(path,'rt') as f: values.append(json.load(f))
    assert values[0]==values[1]
    assert values[0]['full_month_clock_executed'] and values[0]['known_complete_month']
    march_checks.append({'policy':policy,'all_persisted_fields_equal':True,'fields':sorted(values[0]),'native_order_count':len(values[0]['native_orders'])})
    del values
ratio=accept['variants'][1]['CPU']/accept['variants'][0]['CPU']
assert ratio>1 and abs(ratio-read(b['measured_cost'])['candidate_ratio'])<1e-12
meter_mod=load('independent_stage_meter',ROOT/b['meter']['path']); meter=meter_mod.StageMeter()
token=object(); seen=[]
def fn(*args,**kw): seen.append((args,kw));return token
wrapped=meter.wrap(fn,'success'); assert wrapped(token,x=token) is token and seen==[((token,),{'x':token})]
error=RuntimeError('same-object')
def fail(): raise error
try: meter.wrap(fail,'failure')()
except RuntimeError as e: assert e is error
else: raise AssertionError('lost exception')
inner=meter.wrap(fn,'inner');outer=meter.wrap(lambda:inner(token),'outer');assert outer() is token
report=meter.report();assert report['failure']['raised']==1 and report['success']['calls']==1
assert report['outer']['CPU']>=report['inner']['CPU'] and all(v['inclusive_nested'] for v in report.values())
driver=(ROOT/b['driver']['path']).read_text()
assert driver.index('empirical_limit(job)')<driver.index('import native_engine')
assert 'for reuse in (False,):' in driver and 'assert results["reference__" + policy] == previous' in driver
assert 'partial_or_unknown_month_not_a_throughput_gate' in driver
def nested_fn(path,name):
    return next(n for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.FunctionDef) and n.name==name)
assert ast.dump(nested_fn(ROOT/b['driver']['path'],'interpreted'),include_attributes=False)==ast.dump(nested_fn(E/'measure_close_source_reuse.py','interpreted'),include_attributes=False)
out={'verified_small_bindings':verified,'March_source_reused_not_read_or_rehashed':b['March_source'],'source_outcomes':rows,'source_native_engines':engines,'source_invalid_R0':2,'known_closed_R_Decimal_checks':valid_closed,'native_fee_Decimal_checks':True,'all_saved_native_objects_equal':True,'all_observed_necessary_annotations_recomputed':True,'March_persisted_checks':march_checks,'March_variant_events_equal':True,'candidate_runtime_ratio':ratio,'candidate_core_applied':False,'meter_argument_return_exception_identity':True,'meter_nested_not_additive':report,'interpreted_function_AST_identical':True,'review_engines':0,'review_native_CLI':0,'HTTP':0,'affinity':sorted(os.sched_getaffinity(0)),'max_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(E/'source-stage-independent-verification.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in {'verified_small_bindings','source_outcomes','meter_nested_not_additive'}}))
