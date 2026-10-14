import pathlib,json,hashlib,resource,math
resource.setrlimit(resource.RLIMIT_CPU,(8,8))
import numpy as np
import pandas as pd
P=pathlib.Path('reports/research/program/day-goal-20261013/primary-return-breadth');R=P/'results';load=lambda f:json.loads((P/f).read_text());fm=load('final-result-manifest.json');im=load('implementation-manifest.json');res=load('result.json');er=load('results/empirical-report.json');ids=er['fixed_primary_ids'];checked=set()
for row in fm['files']+im['files']:
 p=pathlib.Path(row['path']);b=p.read_bytes();assert hashlib.sha256(b).hexdigest()==row['sha256']and len(b)==row['bytes'];checked.add(str(p))
ret=pd.read_csv(R/'daily-return-matrix.csv',index_col=0,parse_dates=True)
def near(a,b,atol=2e-7):np.testing.assert_allclose(a,b,rtol=1e-10,atol=atol)
adj=load('inputs/bars_all-01.json')['bars'];bs=pd.Series({pd.Timestamp(r['t'][:10]):r['c']for r in adj['BIL']}).sort_index().pct_change(fill_method=None)
host=pd.read_parquet('data/research/account_review_2026_10/returns.parquet');host.index=pd.to_datetime(host.index).tz_localize(None).normalize();hr=load('results/host-comparisons.json');hchecks=0;exceptions=[]
for hn,cols in [('F1',['F1__net10']),('HOST_EW',['F1__net10','S1__net10','S2__net10','S3__net10','C2__net10'])]:
 for cost in [20,40]:
  names=ids+[n.replace('FEDPUT','GENERIC')for n in ids]+['BH_SPY','BH_BIL'];books={n:pd.read_csv(R/f'{hn}_{n}__{cost}-host4k-cash-ledger.csv',index_col=0,parse_dates=True,usecols=['date','nav']) for n in names};ix=books[ids[0]].index
  hh=host[cols].reindex(ix).to_numpy(copy=True);assert np.isfinite(hh).all();hh[0]=0;base=np.prod(1+hh,axis=0) # below fullcontinuouscumprod
  base=np.cumprod(1+hh,axis=0).sum(axis=1)*(16000/len(cols));bil=bs.reindex(ix[1:]).to_numpy();assert np.isfinite(bil).all()
  def met(v):
   v=np.asarray(v);r=v[1:]/v[:-1]-1;ex=r-bil
   return {'final_NAV':v[-1],'dollar_gain':v[-1]-v[0],'CAGR':(v[-1]/v[0])**(365.25/(ix[-1]-ix[0]).days)-1,'Sharpe_ex_BIL':ex.mean()/ex.std(ddof=1)*np.sqrt(252),'max_drawdown':np.min(v/np.maximum.accumulate(v)-1)}
  metrics={n:met(base+b.nav.to_numpy())for n,b in books.items()};metrics['CASH']=met(base+4000)
  for n in ids:
   for c,row in hr[f'{hn}__{cost}'][n].items():
    sm,cm=metrics[n],metrics[c]
    for k in sm:near(sm[k],row['strategy_metrics'][k]);near(cm[k],row['control_metrics'][k])
    near(sm['final_NAV']-cm['final_NAV'],row['dollar_gain_increment']);assert sm['final_NAV']<cm['final_NAV']
    if sm['Sharpe_ex_BIL']>=cm['Sharpe_ex_BIL']:exceptions.append({'host':hn,'cost_bps':cost,'candidate':n,'control':c,'dollar_increment':row['dollar_gain_increment'],'strategy_Sharpe':sm['Sharpe_ex_BIL'],'control_Sharpe':cm['Sharpe_ex_BIL'],'Sharpe_difference':sm['Sharpe_ex_BIL']-cm['Sharpe_ex_BIL']})
    else:assert sm['Sharpe_ex_BIL']<cm['Sharpe_ex_BIL']
    hchecks+=1
exec(pathlib.Path('/tmp/breadth-result-stat-tail.py').read_text())
orders=load('results/orders.json');orderchecks=0
for label,acct in er['primary_and_control_accounts'].items():
 if not (label.endswith('__20')or label.endswith('__40')):continue
 name,bps=label.rsplit('__',1);os=[o for o in orders if o['candidate']==name and o['cost_bps']==int(bps)]
 near(sum(o.get('cost',0)for o in os if o['accepted']),acct['funding']['side_cost_dollars']);assert sum(o['accepted']and o['side']=='buy'for o in os)==acct['funding']['entries'];orderchecks+=1
out={'status':'numerical_results_pass_report_correction_required','final_manifest_sha256':hashlib.sha256((P/'final-result-manifest.json').read_bytes()).hexdigest(),'final_manifest_files':len(fm['files']),'approved_implementation_files':len(im['files']),'unique_bound_paths':len(checked),'completed_prior_checkpoints':{'v1_before_schema_error':'131ledgers fullcash/receivable/unsettled/holdings reconstruction and75column matrix identities passed','v2_before_report_assertion':'same131checks, all18primarycostmetrics,12beta values,6costtables andgeneric/placebo terminal dominance passed'},'host_pairs_independently_recombined':hchecks,'host_all_terminal_increments_negative':True,'host_Sharpe_exceptions_to_author_summary':exceptions,'host_cash_BIL_SPY_Sharpe_all_lower':all(e['control'].startswith('GENERIC')for e in exceptions),'six_paired_HAC_and_2000draw_maxT_bootstrap':'matched_exact_fixedseed_and_calendar','French_OLS_fullweekday_HAC_matched_contrasts':fchecks,'French_NA_contrasts':1,'reported_account_order_fee_entry_counts_checked':orderchecks,'orders_in_file':len(orders),'final_check_process_CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime,'new_strategy_simulations':0,'new_source_or_market_requests':0}
(P/'independent-result-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
