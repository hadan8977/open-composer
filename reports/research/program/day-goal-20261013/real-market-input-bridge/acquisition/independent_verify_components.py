import json,pathlib,hashlib,datetime,resource,sys,re
from decimal import Decimal,localcontext
resource.setrlimit(resource.RLIMIT_CPU,(30,30))
sys.path.insert(0,str(pathlib.Path.cwd()))
from open_composer.market_sessions import us_equity_session_dates
P=pathlib.Path('reports/research/program/day-goal-20261013/real-market-input-bridge/acquisition');load=lambda n:json.loads((P/n).read_text());lines=lambda n:[json.loads(s)for s in (P/n).read_text().splitlines()]
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest();assert sha(P/'package-manifest.json')=='dff627b8721a77e09e9f4c48e7fc9a3eff53aaa411512e981e0fb7ce74397f2d'
m=load('package-manifest.json');checked={}
def binding(b,base=pathlib.Path('.')):
 q=base/b['path'];raw=q.read_bytes();assert hashlib.sha256(raw).hexdigest()==b['sha256'],str(q)
 if 'bytes'in b:assert len(raw)==b['bytes']
 checked[str(q)]=b['sha256']
for b in m['files']:binding(b,P)
for k in ['request_manifest','scope_acceptance','model_interface','authority','parent_accepted_v2','parent_accepted_partial','independent_H5_receipt']:binding(m[k])
for b in m['reused_prior_evidence']:binding(b)
ledger=load('data-request-ledger.json');assert len(ledger['attempts'])==13;assert sum(r['response_bytes']for r in ledger['attempts'])==44098;assert all(r['http_status']==200 for r in ledger['attempts']);assert ledger['automatic_retries']==0
manifest_by={r['id']:r for r in load('request-manifest.json')['requests']};entities={};nrows=0;recordcounts={}
for a in ledger['attempts']:
 assert a['page']==1 and a['params']==manifest_by[a['input_id']]['params'];assert sha(a['entity_path'])==a['entity_sha256'];o=json.loads(pathlib.Path(a['entity_path']).read_text());entities[a['entity_path']]=o
 count=sum(map(len,o.get('corporate_actions',{}).values())) if 'corporate_actions'in o else sum(map(len,o.get('bars',o.get('quotes',{})).values()))
 nrows+=count;recordcounts[a['input_id']]=count
assert nrows==392
rh=lambda r:hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
for row in lines('normalized-source-records.jsonl'):
 o=entities[row['entity_path']];seq=o['corporate_actions'][row['category']]if row['kind']=='action'else o[row['kind']].get(row['symbol'],[])
 assert seq[row['source_ordinal']]==row['raw'] and rh(row['raw'])==row['source_row_sha256'];assert row['historical_first_published_at']is None and row['historical_first_visible_at']is None
# Source-derived regular-session returns with no all-adjusted input dependency.
actions=load('normalized-actions.json');outreturns={};sessions={};D=lambda x:Decimal(str(x));validfeatures=0;usable=0;closeby={};daily_by={(r['symbol'],r['session']):r for r in lines('daily-return-inputs.jsonl')};priceby={(r['symbol'],r['decision_session']):r for r in lines('price3-candidates.jsonl')}
for sym,start,end in [('AAPL','2020-07-01','2020-09-04'),('ATVI','2023-09-01','2023-10-20')]:
 ss=[d.isoformat()for d in us_equity_session_dates(datetime.date.fromisoformat(start),datetime.date.fromisoformat(end))];sessions[sym]=ss;raw=load(f'entities/{sym}_bars_raw-p01.json')['bars'][sym];rb={r['t'][:10]:r for r in raw};closeby[sym]=rb;rets={}
 with localcontext() as ctx:
  ctx.prec=60
  for i,day in enumerate(ss):
   row=daily_by[(sym,day)];todays=[a for a in actions if a['symbol']==sym and a['effective_date']==day];split=Decimal(1);cash=Decimal(0);terminal=False
   for a in todays:
    if a['category']=='forward_splits':split*=D(a['raw']['new_rate'])/D(a['raw']['old_rate'])
    elif a['category']=='cash_dividends':cash+=D(a['raw']['rate'])
    elif a['category']=='cash_mergers':terminal=True
   current=rb.get(day);prev=rb.get(ss[i-1])if i else None
   ghost=lambda r:r is None or (r.get('v')==0 and r.get('n',0)==0)
   val=None if terminal or ghost(current)or ghost(prev)else(split*D(current['c'])+cash)/D(prev['c'])-1
   rets[day]=val
   if val is None:assert row['r_t']is None
   else:assert abs(float(val)-row['r_t'])<2e-14
   f=priceby[(sym,day)];vals=[rets[d]for d in ss[max(0,i-4):i+1]];ready=len(vals)==5 and all(v is not None for v in vals)
   if ready:
    product=Decimal(1)
    for v in vals:product*=1+v
    mu=sum(vals)/5;std=(sum((v-mu)**2 for v in vals)/5).sqrt()
    for k,v in [('Ret_D1',vals[-1]),('Ret_W1',product-1),('STD_W1',std)]:assert abs(float(v)-f[k])<2e-14,(sym,day,k,v,f[k])
    assert f['six_consecutive_endpoint_sessions']==ss[i-5:i+1];validfeatures+=1
   else:assert f['Ret_D1']is f['Ret_W1']is f['STD_W1']is None
   split_trigger=split!=1;assert f['split_trigger_signal_excluded']==split_trigger;assert f['source_component_usable_conditionally']==(ready and not split_trigger);usable+=f['source_component_usable_conditionally']
   assert f['historical_first_visible_at']is None and f['historical_first_published_at']is None and f['strict_APP_input_ready']is False and f['full7_ready']is False
 outreturns[sym]=rets
assert sum(map(len,sessions.values()))==82 and validfeatures==66 and usable==65
# No timezone/float precision loss: compare exact nanosecond event stamps.
def ns(t):
 match=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z',t);assert match,t
 sec=int(datetime.datetime.fromisoformat(match[1]+'+00:00').timestamp());return sec*10**9+int((match[2]or'').ljust(9,'0'))
selected={r['request_id']:r for r in lines('selected-quotes.jsonl')};assert len(selected)==6
for req in manifest_by.values():
 if req['kind']!='quotes':continue
 sym=req['params']['symbols'];rows=load(f"entities/{req['id']}-p01.json").get('quotes',{}).get(sym,[]);eligible=[(ns(r['t']),i,r)for i,r in enumerate(rows)if ns(req['params']['start'])<=ns(r['t'])<=ns(req['params']['end']) and 0<r['bp']<=r['ap']and r['bs']>0 and r['as']>0]
 if not eligible:assert req['id']not in selected;continue
 _,i,r=min(eligible,key=lambda q:(q[0],q[1]));chosen=selected[req['id']];assert chosen['source_ordinal']==i and chosen['raw']==r
labels=load('quote-label-candidates.json');checkedlabels=[]
for lab in labels:
 assert lab['historical_first_visible_at']is None and lab['strict_APP_input_ready']is False and lab['NBBO_fill_or_size_units_certified']is False
 if lab['exit_quote']is None:
  assert lab['case_id']=='ATVI_terminal_noquote'and lab['gross_quote_entitlement_label']is None and lab['terminal_cash_receivable_per_eligible_old_share']==95 and lab['actual_spendable_at']is None;continue
 with localcontext()as ctx:
  ctx.prec=60;entry=lab['entry_quote']['raw'];exit=lab['exit_quote']['raw'];em=(D(entry['bp'])+D(entry['ap']))/2;xm=(D(exit['bp'])+D(exit['ap']))/2
  ratio=Decimal(1);cash=Decimal(0)
  for a in actions:
   if a['symbol']!=lab['symbol']or not a['effective_date']or not(lab['entry_session']<a['effective_date']<=lab['scheduled_exit_session']):continue
   if a['category']=='forward_splits':ratio*=D(a['raw']['new_rate'])/D(a['raw']['old_rate'])
   elif a['category']=='cash_dividends':cash+=ratio*D(a['raw']['rate'])
  value=(ratio*xm+cash)/em-1;assert abs(float(value)-lab['gross_quote_entitlement_label'])<2e-14
  assert lab['retrospective_hypothetical_endpoint_mature_at']==exit['t'];assert lab['actual_current_candidate_mature_at'][:10]=='2026-10-13'
  checkedlabels.append({'case_id':lab['case_id'],'gross_input_label':float(value),'share_ratio':float(ratio),'entry_condition':entry['c'],'exit_condition':exit['c']})
assert len(checkedlabels)==3
cash=next(a for a in actions if a['symbol']=='AAPL'and a['ex_date']=='2020-08-07');assert cash['cash_per_old_share']==.82 and cash['record_date']=='2020-08-10'and cash['payable_date']==cash['process_date']=='2020-08-13'and cash['actual_spendable_at']is None
split=next(a for a in actions if a['category']=='forward_splits');assert split['ex_date']=='2020-08-31'and split['new_shares_per_old_share']==4
h=load('held-asset-obligations.json');assert h['no_account_cash_receipts_available']and h['missing_inputs_never_zero_or_cancel_holdings']and not h['actual_account_positions_assumed']
terminal=h['terminal_case'];assert terminal['terminal_cash_receivable_per_eligible_old_share']==95 and terminal['actual_spendable_at']is None
account=load('continuation-accounting.json');assert abs(7200-account['cumulative_measured_CPU_seconds']-sum(account['unknown_CPU_charges_seconds'].values())-account['remaining_original_CPU_seconds_conservative'])<1e-8
out={'status':'pass_current_vintage_component_arithmetic_not_strict_APP','manifest_files_checked':len(m['files']),'unique_bindings_checked':len(checked),'actual_request_count':13,'actual_bytes':44098,'source_records_matched':nrows,'calendar_rows':82,'price3_recomputed_Decimal60':validfeatures,'non_split_trigger_rows':usable,'actual_selected_quote_observations':6,'labels':checkedlabels,'terminal_quote_label_NA_right95_retained':True,'quote_condition_and_size_certification':False,'historical_first_visible_certified':False,'strict_APP_ready':False,'source_universe_ready':False,'economic_evaluations':0,'model_fits':0,'new_requests':0,'process_CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime}
(P/'independent-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
