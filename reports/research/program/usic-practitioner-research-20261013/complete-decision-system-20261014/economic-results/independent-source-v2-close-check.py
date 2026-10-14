import ast
import dataclasses
import hashlib
import importlib.util
import json
import os
import resource
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

E=Path(__file__).resolve().parent
P=E.parent
ROOT=Path('/root/codex-test/open-composer')
resource.setrlimit(resource.RLIMIT_CPU,(40,45))
packet=json.loads((E/'source-v2-close-affected-review-packet.json').read_text())
verified={}; inherited=[]
march=packet['bindings']['March_source_inventory']
def check(obj):
    if isinstance(obj,dict):
        if 'path' in obj and 'sha256' in obj:
            if obj['path']==march['path']:
                assert obj==march
                inherited.append(obj)
                return
            p=ROOT/obj['path']
            assert p.stat().st_size<2_000_000,str(p)
            with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
            assert digest==obj['sha256'],str(p)
            assert 'bytes' not in obj or p.stat().st_size==obj['bytes'],str(p)
            verified[str(p)]=digest
        else:
            for v in obj.values(): check(v)
    elif isinstance(obj,list):
        for v in obj: check(v)
check(packet)
for name in ['source-v2-close-implementation-manifest.json','source-close-prototype/integration-manifest.json']:
    check(json.loads((E/name).read_text()))
frame_result=json.loads((P/'frame-preparation-result.json').read_text())
assert march in frame_result['outputs']
native_proof=json.loads((E/'source-close-prototype/native-inert-verification.json').read_text())
assert native_proof['native_engines']==16 and len(native_proof['tests'])==4
for case in native_proof['tests']:
    assert case['reference']==case['reuse'] and case['source_unchanged'] and case['accounts_independent']
assert sum(c['cache_hits'] for c in native_proof['source_cache_counts'])>0
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod
sc=load('review_source_clock',E/'source_clock.py')
old=json.loads((E/'source-clock-v1-final/fixture-contract.json').read_text())
new=json.loads((E/'source-clock-v2/fixture-contract.json').read_text())
assert len(old['fixtures'])==len(new['fixtures'])==12
quote_cache={}; observations=[]
for a,b in zip(old['fixtures'],new['fixtures'],strict=True):
    assert b['id']==a['id'].replace('SOURCE_CLOCK_V1','SOURCE_CLOCK_V2')
    allowed={'id','expected_initial_fill_price','expected_initial_fill_quote'}
    assert {k:v for k,v in a.items() if k not in allowed}=={k:v for k,v in b.items() if k not in allowed},b['id']
    source=next(s for s in b['source_versions'] if '_quotes.bin' in s['path'])
    check(source)
    if source['path'] not in quote_cache:
        quote_cache[source['path']]=sc.parse_source((ROOT/source['path']).read_bytes(),'quotes',source['sha256'])[0]
    prior=[q for q in quote_cache[source['path']] if q.event_ns<b['entry_submit_ns']]
    latest=max(prior,key=lambda q:(q.event_ns,q.source_ordinal))
    # Check actual latest message is valid; do not skip a bad last message for an older quote.
    assert latest.quote_problem() is None
    expected=b['expected_initial_fill_quote']
    assert expected['event_ns']==latest.event_ns and expected['source_ordinal']==latest.source_ordinal
    assert Decimal(b['expected_initial_fill_price'])==latest.ask
    assert expected['age_ns_at_submit']==b['entry_submit_ns']-latest.event_ns
    observations.append({'id':b['id'],'quote_ordinal':latest.source_ordinal,'age_ns':expected['age_ns_at_submit'],'ask':str(latest.ask),'old_failed_fill_recovered':False})
v2ast=ast.parse((E/'probe_source_clock_v2.py').read_text())
source_text=(E/'probe_source_clock_v2.py').read_text()
assert source_text.index('native_path.write_text')<source_text.index('assert fill_ns ==')
assert source_text.index('empirical_limit(job)')<source_text.index('from source_clock_native import')
measure=(E/'measure_close_source_reuse.py').read_text()
assert measure.index('empirical_limit(job)')<measure.index('import native_engine')
assert 'partial_or_unknown_month_not_a_throughput_gate' in measure
assert 'results["reference__" + p] == results["reuse__" + p]' in measure
assert measure.index('with gzip.open(folder / (label')<measure.index('if not complete or count != 7800 or not known:')
# Exercise only actual immutable classes/decoders and candidate source cache; no Nautilus import.
ns={'dataclass':dataclasses.dataclass,'datetime':datetime}
classes=[n for n in ast.parse((P/'code/decision_system.py').read_text()).body if isinstance(n,ast.ClassDef) and n.name in {'Frame','Support','Anchor'}]
exec(compile(ast.Module(body=classes,type_ignores=[]),'actual_immutable_Frame_AST','exec'),ns)
decode=[n for n in ast.parse((P/'code/nautilus_policy_adapter.py').read_text()).body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in {'decode_frame','FrameDecoder'}]
exec(compile(ast.Module(body=decode,type_ignores=[]),'actual_decoder_AST','exec'),ns)
helper=load('independent_shared_close_frames',E/'source-close-prototype/candidate/shared_close_frames.py')
base=dict(symbol='A',end='2024-03-01T14:31:00+00:00',start='2024-03-01T14:30:00+00:00',session='2024-03-01',epoch='E',minute=1,duration=1,close=10.1,low=10.,previous_high=10.2,previous_low=9.9,day_low=9.8,adr=5.,ema9=10.,ema21=9.9,previous_daily_close=10.,context_available_at='2024-02-29T21:00:00+00:00',leadership=True,market='strong',shape_ok=True,first_retest=True,supports=[dict(measure_id='S',price=9.8,available_at='2024-02-29T21:00:00+00:00')],anchors=[])
payload=json.dumps([dict(frame=base,leadership_score=1.,prior_dollar_volume=100.)])
cache=helper.SharedCloseFrames(ns['FrameDecoder']().decode)
rows=cache.rows(payload); frame=cache.frame(rows[0]); again=cache.frame(cache.rows(payload)[0])
assert frame is again and dataclasses.asdict(frame)==dataclasses.asdict(ns['decode_frame'](base))
one=ns['Frame'](**dict(vars(frame),sessions_since_risk_pause=2))
two=ns['Frame'](**dict(vars(frame),sessions_since_risk_pause=3))
assert one.sessions_since_risk_pause==2 and two.sessions_since_risk_pause==3 and frame.sessions_since_risk_pause==0
errors=[]
for kind in ('bad_clock','missing_low','extra_field'):
    bad=dict(base)
    if kind=='bad_clock': bad['end']='BAD'
    elif kind=='missing_low': bad.pop('low')
    else: bad['unexpected_future']=1
    text=json.dumps([dict(frame=base,leadership_score=2.,prior_dollar_volume=100.),dict(frame=bad,leadership_score=1.,prior_dollar_volume=100.)])
    c=helper.SharedCloseFrames(ns['FrameDecoder']().decode); hs=c.rows(text)
    assert c.frame_decodes==0
    c.frame(hs[0]); assert c.frame_decodes==1
    got=[]
    for f in (lambda:ns['decode_frame'](bad),lambda:c.frame(hs[1])):
        try: f()
        except Exception as exc: got.append((type(exc).__name__,str(exc)))
    assert len(got)==2 and got[0]==got[1],kind
    errors.append({'case':kind,'same_error':got[0],'earlier_frame_preserved':True})
cache.clear_interval(); assert not cache._source and not cache._frames
verification={'small_bindings_verified':verified,'March_source_inherited_not_read_or_rehashed':march,'V2_12_expectations':observations,'all_other_fixture_fields_unchanged':True,'before_assert_persistence':True,'actual16_author_synthetic_results_deep_equal':True,'independent_lazy_errors':errors,'all_Frame_fields_exact':True,'independent_account_overrides':True,'interval_clear':True,'current_review_native_engines':0,'current_review_native_CLI':0,'actual_market_Frame_reads':0,'HTTP':0,'affinity':sorted(os.sched_getaffinity(0)),'maximum_RSS_KiB':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
(E/'source-v2-close-independent-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
print(json.dumps({'checked_bindings':len(verified),'V2_fixture_count':len(observations),'lazy_errors':errors,'RSS_KiB':verification['maximum_RSS_KiB']}))
