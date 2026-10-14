import pathlib,json,hashlib,datetime,resource,re,bisect,math
resource.setrlimit(resource.RLIMIT_CPU,(25,25))
import numpy as np
import pandas as pd
P=pathlib.Path('reports/research/program/day-goal-20261013/primary-return-breadth');R=P/'results';load=lambda f:json.loads((P/f).read_text());out={};checked={}
def bindcheck(b):
 q=pathlib.Path(b['path']);data=q.read_bytes();assert hashlib.sha256(data).hexdigest()==b['sha256'],str(q)
 if 'bytes'in b:assert len(data)==b['bytes']
 checked[str(q)]=b['sha256']
fm=load('final-result-manifest.json');im=load('implementation-manifest.json')
for b in fm['files']+im['files']:bindcheck(b)
res=load('result.json');er=load('results/empirical-report.json');ids=er['fixed_primary_ids'];assert len(ids)==6
for b in res['bindings'].values():bindcheck(b)
for f in ['native-gate.json','native-final-gate.json']:assert load(f)['status']=='ok'and not load(f)['blocked']
assert res['status_flags']['research_pass'] is False and res['status_flags']['paper_ready_pass']is False
nav=pd.read_csv(R/'full-NAV-matrix.csv',index_col=0,parse_dates=True);ret=pd.read_csv(R/'daily-return-matrix.csv',index_col=0,parse_dates=True)
assert nav.shape==(1703,75) and ret.shape==(1702,75)
assert ret.index.equals(nav.index[1:]);np.testing.assert_allclose(ret,nav.pct_change(fill_method=None).iloc[1:],atol=1e-12,rtol=1e-10)
raw=load('inputs/bars_raw-01.json')['bars'];adj=load('inputs/bars_all-01.json')['bars'];actions=load('inputs/normalized-actions.json')['actions'];cashdays=np.array(load('cash-calendar.json')['eligible_dates'],dtype='datetime64[D]')
def series(rows,key='c'):return pd.Series({pd.Timestamp(r['t'][:10]):r[key]for r in rows}).sort_index()
prices={s:series(raw[s])for s in raw};opens={s:series(raw[s],'o')for s in raw};bil=series(adj['BIL']).pct_change(fill_method=None);spy=series(adj['SPY']).pct_change(fill_method=None)
def due(day,div=False):
 d=np.datetime64(day,'D');n=1 if div else 4 if str(day)[:4]<='2017' else 3 if str(day)<'2024-05-28' else 2
 return cashdays[np.searchsorted(cashdays,d,side='right')+n-1]
def near(a,b,atol=2e-7):np.testing.assert_allclose(a,b,rtol=1e-10,atol=atol)
books={};maxerr=0.;rowschecked=0
for file in sorted(R.glob('*-cash-ledger.csv')):
 b=pd.read_csv(file,index_col=0,parse_dates=True);assert b.index.is_unique and b.index.is_monotonic_increasing and b.notna().all().all();label=file.name[:-len('-cash-ledger.csv')];sym=re.search(r'(SPY|SSO|BIL)',label).group(1);bps=int(re.search(r'__(\d+)',label).group(1));cost=bps/10000
 assert b.index.equals(nav.index[(nav.index>=b.index[0])&(nav.index<=b.index[-1])])
 near(b.nav,b[['proxy_available_cash','unavailable_sales_credit','dividend_receivable','position_value']].sum(axis=1));near(b.position_value,b.shares*prices[sym].reindex(b.index));near(b.shares,np.rint(b.shares));assert min(b.proxy_available_cash)>=-1e-7 and min(b.shares)>=0 and b.iloc[0].shares==0
 n=len(b);dates=b.index.values.astype('datetime64[D]');sp=np.ones(n);ent=np.zeros(n);recv=np.zeros(n);pay=np.zeros(n);unsettled=np.zeros(n);cashdelta=np.zeros(n)
 for a in actions:
  if a['symbol']!=sym or a['type']=='cash_dividends':continue
  i=np.searchsorted(dates,np.datetime64(a['ex_date']));
  if i<n and str(b.index[i].date())==a['ex_date']:sp[i]*=a['ratio']
 prev=np.r_[0,b.shares.to_numpy()[:-1]]*sp
 for a in actions:
  if a['symbol']!=sym or a['type']!='cash_dividends':continue
  i=np.searchsorted(dates,np.datetime64(a['ex_date']));
  if i>=n or str(b.index[i].date())!=a['ex_date']:continue
  amount=prev[i]*a['amount'];j=np.searchsorted(dates,due(a['payable_date'],True));recv[i:j]+=amount;ent[i]+=amount
  if j<n:pay[j]+=amount
 delta=b.shares.to_numpy()-prev;op=opens[sym].reindex(b.index).to_numpy()
 cashdelta[delta>0]=-delta[delta>0]*op[delta>0]*(1+cost)
 for i in np.flatnonzero(delta<0):
  amount=-delta[i]*op[i]*(1-cost);j=np.searchsorted(dates,due(str(b.index[i].date())));unsettled[i:j]+=amount
  if j<n:cashdelta[j]+=amount
 expected=b.iloc[0].nav+np.cumsum(cashdelta+pay)
 near(b.dividend_receivable,recv);near(b.unavailable_sales_credit,unsettled);near(b.proxy_available_cash,expected)
 maxerr=max(maxerr,float(np.max(np.abs(b.proxy_available_cash-expected))));rowschecked+=n;books[label]=b
 if label in nav:near(b.nav,nav[label])
assert len(books)==131
for bps in [0,20,40]:near(nav[f'EW_SPY_SSO__{bps}'],books[f'EW_SPY__{bps}-10k'].nav+books[f'EW_SSO__{bps}-10k'].nav)
def metrics(v):
 rr=v.pct_change(fill_method=None).iloc[1:];ex=rr-bil.reindex(rr.index);dd=v/v.cummax()-1
 return {'dollar_gain':float(v.iloc[-1]-v.iloc[0]),'final_NAV':float(v.iloc[-1]),'CAGR':float((v.iloc[-1]/v.iloc[0])**(365.25/(v.index[-1]-v.index[0]).days)-1),'Sharpe_ex_BIL':float(ex.mean()/ex.std(ddof=1)*np.sqrt(252)),'max_drawdown':float(dd.min())}
primary={};bet=load('results/descriptive-beta.json')['rows'];bec=json.loads(pathlib.Path('reports/research/iterations/t20261013_conditional_fedput_application/breakeven-costs.json').read_text())['candidates']
for name in ids:
 primary[name]={}
 for cost,key in [(0,'funded_0bp_diagnostic'),(20,'primary_20bp'),(40,'funded_40bp_stress')]:
  m=metrics(nav[f'{name}__{cost}']);primary[name][str(cost)]=m
  for k,v in m.items():near(v,res['all_fixed_primary_results'][name][key]['metrics'][k])
  near(m['dollar_gain'],bec[name]['observed_dollar_gain_by_side_bps'][str(cost)])
  if cost:
   y=ret[f'{name}__{cost}'];x=spy.reindex(y.index);rf=bil.reindex(y.index)
   near(np.cov(x-rf,y-rf)[0,1]/(x-rf).var(),bet[name][str(cost)]['beta_ex_BIL']);near(np.cov(x,y)[0,1]/x.var(),bet[name][str(cost)]['beta_raw_return'])
 assert primary[name]['20']['dollar_gain']<0 and primary[name]['20']['Sharpe_ex_BIL']<0
 for family in ['GENERIC','PLACEBO']:assert nav[f'{name}__20'].iloc[-1]<nav[f'{name.replace("FEDPUT",family)}__20'].iloc[-1]
 assert bec[name]['breakeven_cost_bps_per_side']is None
 if bec[name]['zero_cost_positive']:near(20*primary[name]['0']['dollar_gain']/(primary[name]['0']['dollar_gain']-primary[name]['20']['dollar_gain']),bec[name]['straight_line_0_to_20_terminal_gain_root_bps_diagnostic'])
# Recombine storedhost and independently persisted4k ledgers, not strategy resimulation.
host=pd.read_parquet('data/research/account_review_2026_10/returns.parquet');host.index=pd.to_datetime(host.index).tz_localize(None).normalize();hr=load('results/host-comparisons.json');hchecks=0
for hn,cols in [('F1',['F1__net10']),('HOST_EW',['F1__net10','S1__net10','S2__net10','S3__net10','C2__net10'])]:
 for cost in [20,40]:
  for name in ids:
   book=books[f'{hn}_{name}__{cost}-host4k'];hh=host[cols].reindex(book.index).copy();assert hh.notna().all().all();hh.iloc[0]=0;base=(1+hh).cumprod().sum(axis=1)*(16000/len(cols));v=base+book.nav;sm=metrics(v)
   for ctrl,row in hr[f'{hn}__{cost}'][name].items():
    cv=base+ (4000 if ctrl=='CASH'else books[f'{hn}_{ctrl}__{cost}-host4k'].nav);cm=metrics(cv)
    near(v.iloc[-1]-cv.iloc[-1],row['dollar_gain_increment'])
    for k in sm:near(sm[k],row['strategy_metrics'][k]);near(cm[k],row['control_metrics'][k])
    assert sm['final_NAV']<cm['final_NAV'] and sm['Sharpe_ex_BIL']<cm['Sharpe_ex_BIL'];hchecks+=1
# Independent HAC and exact fixed bootstrap replay from existing matrix only.
x=np.column_stack([(ret[f'{name}__20']-ret[f'{name.replace("FEDPUT","GENERIC")}__20']).to_numpy()for name in ids]);n=len(x);mu=x.mean(axis=0);u=x-mu;var=(u*u).mean(axis=0)
for k in range(1,6):var+=2*(1-k/6)*(u[k:]*u[:-k]).sum(axis=0)/n
se=np.sqrt(var/n);rng=np.random.default_rng(20261013);samp=[];maxt=[]
for _ in range(2000):
 starts=rng.integers(0,n,size=math.ceil(n/20));idx=((starts[:,None]+np.arange(20))%n).ravel()[:n];means=x[idx].mean(axis=0);samp.append(means);maxt.append(np.max(np.abs((means-mu)/se)))
crit=np.quantile(maxt,.95);paired=load('results/paired-inference.json');near(crit,paired['maxT_critical'],1e-10)
for j,name in enumerate(ids):
 t=paired['comparisons'][name];near(mu[j]*10000,t['mean_daily_bp']);near(se[j]*10000,t['HAC_se_bp']);near(np.quantile(np.array(samp)[:,j],[.025,.975])*10000,t['blockbootstrap95_mean_bp']);near((mu[j]+np.array([-1,1])*crit*se[j])*10000,t['family_maxT95_mean_bp'])
# Verify source-form contrast coefficients/HAC against exported primitive rows; no source intake.
f=pd.read_csv(R/'french-descriptive-primitives.csv',index_col=0,parse_dates=True);fs=load('results/french-source-form-diagnostic.json')['results'];fchecks=0
for seg,mask in [('full2015_2026Aug',np.ones(len(f),bool)),('2017_2021',(f.index.year>=2017)&(f.index.year<=2021)),('2020_2021',(f.index.year>=2020)&(f.index.year<=2021)),('2022_2026Aug',f.index.year>=2022)]:
 for d in ['D1','D2','D3']:
  sel=f.loc[mask&f[d]&(f.late|f.odd)];want=fs[seg][d];assert len(sel)==want['N']
  if len(sel)<10:assert want['contrast']is None;continue
  xx=np.column_stack([np.ones(len(sel)),sel.late.to_numpy(dtype=float)]);yy=sel.MktRF.to_numpy();coef=np.linalg.lstsq(xx,yy,rcond=None)[0];scores=pd.DataFrame(xx*(yy-xx@coef)[:,None],index=sel.index).reindex(f.index[mask],fill_value=0).to_numpy();meat=scores.T@scores
  for k in range(1,6):cv=scores[k:].T@scores[:-k];meat+=(1-k/6)*(cv+cv.T)
  br=np.linalg.inv(xx.T@xx);near(coef[1]*10000,want['late_minus_odd_daily_bp']);near(np.sqrt((br@meat@br)[1,1])*10000,want['HAC5_se_bp']);fchecks+=1
out={'verdict':'checks_pass','final_manifest_sha256':hashlib.sha256((P/'final-result-manifest.json').read_bytes()).hexdigest(),'final_manifest_files':len(fm['files']),'implementation_files':len(im['files']),'unique_verified_paths':len(checked),'cash_ledgers_independently_reconstructed':len(books),'ledger_rows_checked':rowschecked,'max_available_cash_reconstruction_error_USD':maxerr,'matrix_shape':list(nav.shape),'return_matrix_shape':list(ret.shape),'primary_metrics':primary,'beta_rows_recomputed':12,'host_pairs_recombined':hchecks,'paired_HAC_and_bootstrap':'6differences,2000draws,20session,seed20261013 matched','French_OLS_HAC_contrasts_matched':fchecks,'French_lowcount_NA_preserved':1,'new_strategy_runs':0,'new_market_requests':0,'new_source_requests':0,'process_CPU_seconds':resource.getrusage(resource.RUSAGE_SELF).ru_utime+resource.getrusage(resource.RUSAGE_SELF).ru_stime}
(P/'independent-result-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='primary_metrics'},indent=2))
