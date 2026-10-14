import ast,copy,hashlib,json,os,resource,sys
from pathlib import Path
from datetime import date,datetime,timedelta
from decimal import Decimal,localcontext
resource.setrlimit(resource.RLIMIT_CPU,(105,110));assert os.sched_getaffinity(0)=={0}
P=Path(__file__).resolve().parent;ROOT=Path.cwd();sys.path.insert(0,str(P/'code'))
from build_case_inputs import minute_grid
from case_replay import replay
checked={}
def load(p,dec=False):return json.loads(Path(p).read_bytes(),**({'parse_float':Decimal} if dec else {}))
def verify(b):
 p=Path(b['path']);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==b['sha256'],str(p)
 checked[str(p)]=dict(sha256=b['sha256'],bytes=len(raw))
def norm(x):return json.loads(json.dumps(x,default=str))
packet=load(P/'actual-input-implementation-review-packet.json')
for b in packet['bindings']:verify(b)
im=load(P/'implementation-manifest.json');am=load(P/'acquisition/actual-input-manifest.json')
for b in im['files']+am['bindings']:verify(b)
ledger=load(P/'acquisition/market/request-ledger.json');assert ledger['requests_used']==17 and ledger['complete_entity_bytes']==11249925 and ledger['incomplete_response_reserved_bytes']==0
byid={}
for a in ledger['attempts']:
 assert a['http_status']==200 and a['entity_complete'];byid.setdefault(a['id'],[]).append(a)
for rows in byid.values():
 assert rows[-1]['next_page_token'] is None
 for a,b in zip(rows,rows[1:]):assert a['next_page_token']==b['params']['page_token']
assert len(byid)==7
registry=load(P/'acquisition/components/entity-registry.json');sourcecache={}
def deref(ref):
 i=ref['entity_index']
 if i not in sourcecache:sourcecache[i]=load(registry[i]['path'],True)
 x=sourcecache[i]
 for k in ref['json_pointer'].split('/')[1:]:x=x[int(k)] if isinstance(x,list) else x[k]
 return x
actions=load(P/'acquisition/components/actions.json')
for a in actions:assert norm(deref(a['ref']))==a['row']
rename=[a for a in actions if a['action_type']=='name_changes' and a['row'].get('old_symbol')=='SBE' and a['row'].get('new_symbol')=='CHPT']
assert len(rename)==1 and rename[0]['row']['old_cusip']==rename[0]['row']['new_cusip']=='15961R105'
assert rename[0]['economic_effective_date'] is None and rename[0]['row']['process_date']=='2021-03-01'
summary=load(P/'acquisition/components/component-result.json');inputchecks=[];pointercount=0
with localcontext() as ctx:
 ctx.prec=60
 for entry in summary['cases']:
  report=load(entry['binding']['path']);verify(entry['binding']);case=report['clock']['date_candidate'];prior=report['clock']['prior_session']
  for symbol,comp in report['symbol_components'].items():
   times={}
   for item in comp['RTH_minutes']:
    assert norm(deref(item['ref']))==item['row'];pointercount+=1
    when=datetime.fromisoformat(item['timestamp_NY']);assert when not in times;times[when]=item
    rawtime=datetime.fromisoformat(item['row']['t'].replace('Z','+00:00'));assert when==rawtime
   assert len(times)==comp['RTH_minutes_retained']
   rebuilt=[]
   for sess in comp['sessions']:
    grid=minute_grid(date.fromisoformat(sess['day']));missing=[t.isoformat() for t in grid if t not in times or not times[t]['valid']]
    assert missing==sess['missing_or_invalid_minutes'] and sess['complete_RTH']==(not missing)
    for start in range(0,len(grid),60):
     interval=grid[start:start+60];rows=[times[t]['row'] for t in interval if t in times and times[t]['valid']]
     good=len(rows)==len(interval)
     rebuilt.append(dict(start=interval[0].isoformat(),end=(interval[-1]+timedelta(minutes=1)).isoformat(),complete=good,rows=rows,duration=len(interval)))
   assert len(rebuilt)==len(comp['chartbars'])
   for c,b in zip(comp['chartbars'],rebuilt,strict=True):
    assert c['start_NY']==b['start'] and c['end_NY']==b['end'] and c['complete']==b['complete'] and c['duration_minutes']==b['duration']
    if b['complete']:
     rr=b['rows'];assert Decimal(str(c['h']))==max(Decimal(str(r['h'])) for r in rr) and Decimal(str(c['l']))==min(Decimal(str(r['l'])) for r in rr)
     assert str(c['c'])==str(rr[-1]['c'])
   priorgrid=minute_grid(date.fromisoformat(prior));complete=all(t in times and times[t]['valid'] for t in priorgrid)
   assert complete==comp['prior_RTH_complete']
   if complete:assert Decimal(str(comp['prior_RTH_low']))==min(Decimal(str(times[t]['row']['l'])) for t in priorgrid)
   else:assert comp['prior_RTH_low'] is None
   last=[c for c in comp['chartbars'] if c['start_NY'][:10]==prior][-1];assert last==comp['prior_last_chartbar']
   prefix=[c for c in comp['chartbars'] if c['complete'] and c['start_NY'][:10]<case]
   for sensitivity in comp['EMA_finite_window_sensitivity']:
    n=sensitivity['window_completed_chartbars'];enough=len(prefix)>=n;assert sensitivity['available']==enough
    if enough:
     window=prefix[-n:];assert sensitivity['first_seed_bar']==window[0]['start_NY']
     for period in [21,50]:
      value=Decimal(str(window[0]['c']));alpha=Decimal(2)/Decimal(period+1)
      for c in window[1:]:value+=alpha*(Decimal(str(c['c']))-value)
      assert value==Decimal(sensitivity[f'EMA{period}'])
    else:assert sensitivity['EMA21'] is None and sensitivity['EMA50'] is None
   # Prepare price-only source-alignment witnesses, never call replay on real data.
   firsthour=next(c for c in comp['chartbars'] if c['start_NY'][:10]==case)
   inputchecks.append(dict(case=entry['case_id'],symbol=symbol,source_records=comp['observed_source_records'],RTH_source_pointers=len(times),prior_RTH_complete=complete,lastbar_complete=last['complete'],lastbar_high_low=[last.get('h'),last.get('l')],case_firsthour_OHLC=[firsthour.get(k) for k in ['o','h','l','c']],EMA_windows=[x['available'] for x in comp['EMA_finite_window_sensitivity']],economic_replay_invoked=False))
  del report

# Synthetic only: fixed dollar levels have no relationship to the actual case prices.
tests=[];day='2025-02-20';grid=minute_grid(date.fromisoformat(day))
def fixture():
 return dict(prior_last_chartbar=dict(complete=True,l='10.01',h='10.99',start_NY='2025-02-19T15:30:00-05:00',end_NY='2025-02-19T16:00:00-05:00',source_refs=[]),prior_RTH_complete=True,prior_RTH_low='9.5',RTH_minutes=[dict(timestamp_NY=t.isoformat(),valid=True,row=dict(o='10.5',h='10.8',l='10.2',c='10.5',v=100000),ref={'synthetic':i}) for i,t in enumerate(grid)])
def run(c,method='PREVH',delay=1):return replay(c,day,method,delay)
c=fixture();c['RTH_minutes'][2]['row'].update(o='9.8',l='9.7',h='11.5');c['RTH_minutes'][3]['row'].update(o='11.4',h='11.5')
x=run(c);tr=x['trajectory'];assert tr['entry']['price']=='9.8' and tr['exit']['price']=='11.4' and tr['q0']==100 and tr['R0']=='100.00';assert tr['entry']['entry_bar_crosses_stop_while_unprotected'];tests.append('later_pending_gap_frozen_q_nextminute_protection')
with localcontext() as ctx:
 ctx.prec=60
 assert Decimal(x['transaction_costs'][2]['transaction_adjusted_R'])==Decimal('-1.6424')
 assert Decimal(x['mandatory_borrow_stress'][5]['stress_R'])==(Decimal('-160')-Decimal('4.24')-Decimal(980)*Decimal('.2')/365)/100
tests.append('exact_fees_and_one_day_borrow_original_R0')
c=fixture();c['RTH_minutes']=[r for i,r in enumerate(c['RTH_minutes']) if i not in [0,*range(375,390)]];assert run(c)['trajectory']['status']=='no_fill';tests.append('inactive_and_expiry_missing_do_not_corrupt_clean_nofill')
c=fixture();del c['RTH_minutes'][1];assert run(c)['trajectory']['status']=='missing';tests.append('pending_gap_unknown')
c=fixture();c['RTH_minutes'][1]['row'].update(o='9.8',l='9.7');del c['RTH_minutes'][2];z=run(c)['trajectory'];assert z['status']=='missing' and z['entry'] and z['contingent_protection_scheduled_NY']==grid[2].isoformat();tests.append('holding_gap_scheduled_protection_unknown')
c=fixture();c['prior_RTH_complete']=False;c['prior_RTH_low']=None;assert run(c,'PDL')['trajectory']['status']=='invalid_input' and run(c)['trajectory']['status']=='no_fill';tests.append('PDL_missing_range_no_daily_fallback_PREVH_independent')
c=fixture();c['RTH_minutes'][374]['row'].update(o='9.8',l='9.7');c['RTH_minutes'][-1]['row'].update(h='11.5',c='10.4');z=run(c)['trajectory'];assert z['entry']['minute_start_NY']==grid[374].isoformat() and z['exit']['exit_reason']=='protective_touch_proxy';tests.append('last_entry_and_stop_precedes_EOD')
c=fixture();c['RTH_minutes'][375]['row'].update(o='9.8',l='9.7');assert run(c)['trajectory']['status']=='no_fill';tests.append('expiry_precedes_trigger')
c=fixture();c['RTH_minutes'][1]['row'].update(o='9.8',l='9.7');z=run(c)['trajectory'];assert z['exit']['exit_reason']=='EOD_research_convention';tests.append('EOD_closed_once')
for status_comp in [fixture(),{**fixture(),'prior_RTH_complete':False,'prior_RTH_low':None}]:
 z=run(status_comp,'PDL');assert len(z['transaction_costs'])==3 and len(z['mandatory_borrow_stress'])==6 and all(q['transaction_adjusted_R'] is None for q in z['transaction_costs'])
tests.append('invalid_and_nofill_all_cost_stress_cells_retained')

# Native applicability proposal: isolate functions; do not modify shared source.
probe=load(P/'native-entry-probe-definition.json');native=ROOT/'open_composer/research/iteration_dossier.py';raw=native.read_bytes();assert hashlib.sha256(raw).hexdigest()==probe['native_original_source_sha']
tree=ast.parse(raw);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_external_brief_blockers');assert ast.dump(node,include_attributes=False)==ast.dump(ast.parse(probe['original_function']).body[0],include_attributes=False)
functions=[]
for key in ['original_function','proposed_function']:
 ns={'Any':object,'REQUIRED_SOURCE_FIELDS':set(probe['constants']['REQUIRED_SOURCE_FIELDS']),'PAPER_SOURCE_TYPES':set(probe['constants']['PAPER_SOURCE_TYPES'])};exec(probe[key],ns);functions.append(ns['_external_brief_blockers'])
def source(kind='practitioner_first_person',role='authored_public_method'):
 return {**{k:'synthetic-required-value' for k in probe['constants']['REQUIRED_SOURCE_FIELDS']},'source_type':kind,'source_kind':role}
payload=dict(schema_version=3,current_source_card_paths=['synthetic'],source_evidence_bindings=['synthetic'],sources=[source(),source('provider_docs','data_documentation')],topic_coverage=list('abcdef'),candidate_matrix_revisions=['fixed'])
cases=[]
for name,p,flags,expect_exception in [('authored_component',payload,{'market_component':True},True),('ordinary_strategy',payload,{},False),('public_method',payload,{'public_method':True},False),('docs_component',{**payload,'sources':[source('platform_docs','docs'),source('provider_docs','docs')]},{'market_component':True},False),('paper_component',{**payload,'sources':[source('academic_paper','paper'),source('provider_docs','docs')]},{'market_component':True},False)]:
 a,b=(fn(p,**flags) for fn in functions)
 if expect_exception:assert [x for x in a if 'paper_sources' not in x]==b and any('paper_sources' in x for x in a)
 else:assert a==b
 cases.append(dict(name=name,old=a,new=b))
for modified in [{**payload,'sources':[source()]},{**payload,'sources':[{**source(),'core_claim':''},source()]},{**payload,'current_source_card_paths':[]}]:
 assert functions[1](modified,market_component=True)
tests.append('native_sourcecount_requiredfields_and_evidence_presence_retained')
out=dict(status='pass',bindings_checked=checked,actual_input_cases=inputchecks,actual_RTH_source_pointers_verified=pointercount,all_action_pointers_checked=len(actions),sameCUSIP_rename=rename,synthetic_tests=tests,native_isolated_cases=cases,native_shared_source_unchanged=True,actual_case_PnL_R_or_orders_called=False,new_source_market_fits=0,resource=dict(CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,affinity=[0]))
(P/'independent-input-implementation-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['bindings_checked','sameCUSIP_rename','native_isolated_cases']}))
