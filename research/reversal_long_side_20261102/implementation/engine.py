"""Finite accepted long-side comparison, actual native funded books and durable trials."""
from pathlib import Path
from datetime import datetime, UTC
import sys,json,time,math
import numpy as np
import pandas as pd
from scipy.optimize import brentq
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts import t22_run as R
from open_composer.lab.adapters import book_engine
from open_composer.lab.book_funding import fund_long_only_trades
from open_composer.lab.ledger import TrialLedger
from open_composer.lab.metrics import return_metrics
from open_composer.lab.models import EngineResult
from open_composer.lab.batch import write_evidence
from open_composer.research.agent_workflow import require_research,Results,Counts
from open_composer.research.equity_book.backtest import BookConfig
from open_composer.research.equity_book.costfn import make_cost_fn
BASE=ROOT/'research/reversal_long_side_20261102';OUT=BASE/'runs/mechanisms-20261102-6/worker/evidence'
CAP=20000.;START='2024-01-08';END='2026-09-15'
ARMS=['LGBM_LONG','RIDGE_LONG','RULE_LONG','LIQUID100','SPY','CASH']
STOCKS=ARMS[:4]
CONTRASTS=[(m,c) for m in ARMS[:2] for c in ['RULE_LONG','LIQUID100','SPY']]
LIMITS=['Seen 2024-01-08..2026-09-15 window, 674 sessions, inherited model/universe selection and incomplete historical trials','Conditional native adjusted economic units, no certified physical entitlement/PIT permanent identity or broker fractional execution','Open spread snapshot 09:35-09:45, year-calibrated; modeled costs, not realized opening fills','No new model fits, no threshold/window/universe/score search; news and algorithm effects not separately identified','Ex-post funded volatility matching is descriptive; target-filter jumps may prevent matching']
def save(name,value):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);write_evidence(p,value)
def read(p):return json.loads(p.read_text())
def rel(p):return str(p.relative_to(ROOT))
def risk(b):return float(b.net_returns.std(ddof=1)*np.sqrt(252))

class Study:
 def __init__(self):
  require_research(ROOT);self.s=R.Store();self.a=self.s.pos(pd.Timestamp('2024-01-05'));self.b=self.s.pos(pd.Timestamp(END))
  self.c=pd.read_parquet(OUT/'close-with-spy.parquet').loc['2024-01-05':END];self.o=pd.read_parquet(OUT/'open-with-spy.parquet').reindex_like(self.c)
  self.idx=self.c.index[1:];assert len(self.idx)==674
  self.native_panel=R.PricePanel.from_frames(self.o,self.c);self.attrs=R.make_attrs(self.s,self.native_panel)
  self.ledger=TrialLedger(BASE/'trials.jsonl');self.books={};self.created=[]
  self.rawcost=make_cost_fn('open');self.targets={};self.decisions={}
  self.excluded={pd.Timestamp(x['first_session_after']) for group in read(OUT/'hygiene.json')['native_hygiene']['breaks_by_symbol'].values() for x in group if x['kind']=='jump'}
 def prepare(self):
  if (OUT/'definitions.json').exists():
   if '--resume' not in sys.argv:raise RuntimeError('Frozen definitions exist: explicit --resume required')
   self.targets={arm:pd.read_parquet(OUT/f'targets-{arm}.parquet').reindex(columns=self.c.columns,fill_value=0.) for arm in STOCKS}
   return
  # Known algebraic target-weight discontinuities are fixed before account results.
  jumps=[.5,.625,5/6]
  segments=[(0.,.5-1e-9),(.5,.625-1e-9),(.625,5/6-1e-9),(5/6,1.)]
  save('definitions.json',{'arms':ARMS,'capital_each':CAP,'cost_multipliers':[1,2],'calendar':[START,END],'n_sessions':674,'target_filter':'abs(weight)*fixed initial 20000>=100; risk scale first, filter once, no order minimum or renormalization','cash_credit':0,'funding':'Fixed sales, common buy coefficient, 64 bisections feasible lower endpoint; pure native variable costs; original financing rate retained','matching':{'method':'Same native funded cash-mixture bracket/root procedure, adapted to known target-filter support discontinuities','segments':segments,'nodes_per_continuous_segment':5,'jump_points':jumps,'xtol':1e-10,'max_vol_gap':1e-6,'root_choice':'smallest valid bracketed root; scale down only to lower unscaled volatility; all roots recorded; jump crossing is unmatched, never interpolate profits','costs':'recompute actual independent path per scale; identical controls reused'},'uncertainty':{'contrasts':CONTRASTS,'circular_block':63,'draws':1999,'seed':20261102,'family':'six paired daily rate contrasts per cost; common index matrix across both dependent costs','interval':'simultaneous centered maxT, fixed block bootstrap standard error; annualized daily arithmetic mean difference','HAC':5},'excluded_trigger_dates':sorted(str(x.date()) for x in self.excluded if self.idx[0]<=x<=self.idx[-1]),'limits':LIMITS})
  self.ledger.import_prior('t22_known_exposure_floor',count=35,evidence=['reports/research/iterations/t20261006_22_st_reversal/trial-grid.json','reports/research/iterations/t20261006_22_st_reversal/contract.md','reports/research/trials.jsonl'],note='24 main +4 prespecified robustness +2 trained ranks +5 posthoc allocations; known floor, not independent count. Two further borrow stresses and repeated historical-window views are diagnostics; withdrawn 900-grid/15 registrations never run. Debug starts/failed overhead incomplete; DSR unavailable.')
  for arm in STOCKS:self.ledger.start(f'policy:{arm}',batch='long-side-fixed',candidate=arm,parameters={'capital':CAP,'H':5,'costs':[1,2]},note='Fixed component allocation, counted conservatively before any account')
  save('trial-reconciliation.json',self.lineage())
  for arm in STOCKS:
   print('TARGETS',arm,flush=True)
   raw=[];summary=[];cohorts={}
   if arm in ARMS[:2]:R.SCORE_OVERRIDE=np.load(ROOT/f'data/research/t22_ml_scores/{"lgbm" if arm==ARMS[0] else "ridge"}_U500_H5.npy',mmap_mode='r')
   else:R.SCORE_OVERRIDE=None
   for t in range(self.a-4,self.b):
    if arm=='LIQUID100':
     adv=np.asarray(self.s.m('dollar_adv_21')[t],float);ok=R.candidates(self.s,t,500,'none',adv)&(adv>0)
     ii=np.flatnonzero(ok)
     if len(ii)<150:li=None
     else:
      order=np.lexsort((self.s.symbols[ii].astype(str),-adv[ii]));li=ii[order[:100]]
    else:
     b=R.single_day_book(self.s,t,500,'ind',21,'none');li=None if b is None else b[0][b[1]>0]
    cohorts[t]=li
    if t<self.a:continue
    counts=np.zeros(self.s.shape[1],dtype=np.int8)
    if li is not None:
     for k in range(4,-1,-1):
      vv=cohorts.get(t-k)
      if vv is not None:counts[vv]+=1
    w=pd.Series(counts*.002,index=self.s.symbols).reindex(self.c.columns).fillna(0.)
    assert np.isclose(w.sum(),counts.sum()*.002),'Selected name missing from bound panel'
    raw.append(w)
    summary.append({'decision_date':str(self.s.dates[t].date()),'cohort_missing':li is None,'raw_gross':float(w.sum()),'raw_names':int((w>0).sum()),'filtered_names_1x':int((w*CAP>=100).sum()),'filtered_weight_1x':float(w[w*CAP>=100].sum())})
   self.targets[arm]=pd.DataFrame(raw,index=self.c.index[:-1]);self.targets[arm].to_parquet(OUT/f'targets-{arm}.parquet')
   pd.DataFrame(summary).to_csv(OUT/f'target-diagnostics-{arm}.csv',index=False)
  R.SCORE_OVERRIDE=None
 def lineage(self):
  root=ROOT/'reports/research/iterations/t20261006_22_st_reversal/artifacts'
  globalrows=[json.loads(l) for l in (ROOT/'reports/research/trials.jsonl').read_text().splitlines() if 't20261006_22_st_reversal' in l]
  return {'global_registration_rows':len(globalrows),'global_registration_rows_not_experiment_count':True,'main_recent_outputs':len(list((root/'cells_A').glob('*.json'))),'repeated_stress_outputs':len(list((root/'cells_B').glob('*.json'))),'robustness_outputs':len(list((root/'cells_robust').glob('*.json'))),'model_recent_outputs':len(list((root/'ml').glob('*recent.json'))),'exploration_recent_outputs':len(list((root/'ml_exploratory').glob('*recent.json'))),'known_prior_policy_floor':35,'new_policies':4,'known_prior_model_fits':5,'new_fits':0,'unknown':'debug/failed and withdrawn-vs-start timing details not fully reconstructible; prior provider $0.21 estimate only; no DSR/PBO from survivor summaries'}
 def account(self,arm,mult,scale=1.):
  scale=float(scale);key=(arm,mult,scale.hex());name=f'{arm}-c{mult}-s{scale.hex().replace(".","_").replace("+","")}'
  if key in self.books:return self.books[key]
  if arm=='SPY':name+='-prices-r1'
  folder=OUT/'accounts'/name
  if (folder/'failure.json').exists() and '--repair' in sys.argv:
   name+='-repair1';folder=OUT/'accounts'/name
  if (folder/'complete.json').exists():
   d=pd.read_parquet(folder/'daily.parquet');b=EngineResult(engine='equity_book.run_book',initial_equity_usd=CAP,end_equity_usd=float(d.equity.iloc[-1]),native={},ledger=d,net_returns=d.net,metadata={'account_folder':rel(folder),'arm':arm,'cost_multiplier':mult,'scale':scale})
   self.books[key]=b;return b
  if folder.exists():raise RuntimeError(f'Incomplete account {name}; no silent replay')
  require_research(ROOT);folder.mkdir(parents=True)
  tid=f'account:{name}';self.ledger.start(tid,batch='long-side-accounts',candidate=name,parameters={'arm':arm,'multiplier':mult,'scale_hex':scale.hex()},counts_as_trial=False,note='Funded accounting/cost/risk view of the four registered policies or fixed market/cash benchmark; no new model/selection')
  started=time.monotonic();orders=[];executions=[];decision_rows=[]
  def cost(t,st):return {k:mult*v for k,v in self.rawcost(t,st).items()}
  def observe(t,st,parts):
   tt=t.copy();tt['decision_date']=st.decision_date
   tt['held_before_dollars']=st.holdings.reindex(tt.symbol,fill_value=0).to_numpy()
   tt['desired_dollars']=tt.held_before_dollars+tt.requested_dollar_trade
   tt['funded_dollars']=tt.held_before_dollars+tt.dollar_trade
   orders.append(tt)
   executed=t.dollar_trade.to_numpy();postcash=st.cash-float(executed.sum())-sum(parts.values())
   executions.append({'trade_date':st.date,'decision_date':st.decision_date,'cash_before':st.cash,'net_orders':float(executed.sum()),'cash_after':postcash,'equity_before':st.equity,'equity_after':st.equity-sum(parts.values()),'identity_residual':(st.equity-sum(parts.values()))-(float(st.holdings.sum())+float(executed.sum())+postcash),'funding_lambda':float(t.funding_lambda.iloc[0]),'funding_reduction':float((t.requested_dollar_trade-t.dollar_trade).sum()),**parts})
  def decide(date,st):
   if date in self.excluded:return None
   if arm=='SPY':return {'SPY':scale} if date==self.c.index[0] else None
   if arm=='CASH':return {}
   w=self.targets[arm].loc[date]*scale
   keep=w*CAP>=100
   decision_rows.append({'date':date,'raw_target_gross':float(w.sum()),'retained_target_gross':float(w[keep].sum()),'excluded_names':int(((w>0)&~keep).sum()),'excluded_weight':float(w[~keep].sum())})
   return w[keep].to_dict()
  try:
   cfg=BookConfig(freq='D',exec_price='open',cost_fn=cost,borrow_bp_per_year=0.,margin_rate=.065,tbill_symbols=(),initial_equity=CAP,start='2024-01-05',end=END,trade_attrs=self.attrs,trade_funding=fund_long_only_trades,trade_observer=observe,snapshots=True)
   book=book_engine(self.c,self.o,decide,config=cfg)
   # Jan05 is the flat decision close: the scored continuous calendar begins Jan08.
   d=book.ledger.loc[START:END].copy();assert d.index.equals(self.idx)
   book=EngineResult(engine=book.engine,initial_equity_usd=CAP,end_equity_usd=float(d.equity.iloc[-1]),native=book.native,ledger=d,net_returns=d.net,metadata={'account_folder':rel(folder),'arm':arm,'cost_multiplier':mult,'scale':scale})
   q=pd.concat(orders,ignore_index=True) if orders else pd.DataFrame(columns=['trade_date','symbol','dollar_trade','requested_dollar_trade','price'])
   ex=pd.DataFrame(executions);dec=pd.DataFrame(decision_rows)
   d.to_parquet(folder/'daily.parquet');q.to_parquet(folder/'orders.parquet',index=False);ex.to_parquet(folder/'executions.parquet',index=False);dec.to_parquet(folder/'decisions.parquet',index=False)
   save(Path('accounts')/name/'native.json',book.native)
   checks=self.validate_account(book,q,ex)
   stats=self.metrics(book,q,ex,dec)
   save(Path('accounts')/name/'metrics.json',stats);save(Path('accounts')/name/'complete.json',{'account':name,'seconds':time.monotonic()-started,'checks':checks,'metrics':'metrics.json','identity':'daily native equity, orders, cash and each executed cost component; root probes never logged as fills'})
   self.ledger.finish(tid,status='complete',evidence=[rel(folder/'complete.json')]);self.created.append(rel(folder));book.native={};self.books[key]=book
   print('ACCOUNT',name,'pnl',round(book.net_profit_usd,2),'vol',round(risk(book),6),flush=True)
   return book
  except BaseException as e:
   save(Path('accounts')/name/'failure.json',{'error':repr(e),'seconds':time.monotonic()-started});self.ledger.finish(tid,status='failed',evidence=[rel(folder/'failure.json')]);raise
 def validate_account(self,b,q,ex):
  d=b.ledger;cash=d.cash_exp*d.equity
  assert np.isfinite(d.net).all() and cash.min()>=-1e-8
  assert b.native['info']['unknown_symbols']==0,'Unknown account target symbol'
  assert d.cost_margin.sum()==0 and d.cost_borrow.sum()==0 and (d.short_exp==0).all()
  residual=0 if ex.empty else float(ex.identity_residual.abs().max())
  assert residual<=1e-6
  if not ex.empty:
   assert ex.cash_after.min()>=-1e-8
   prev=d.equity.shift().fillna(CAP)
   for k in ['spread','impact','fees']:
    assert abs(float((d['cost_'+k]*prev).sum())-float(ex[k].sum()))<=1e-6
   for date,g in q.groupby('trade_date'):
    row=ex.loc[ex.trade_date==date].iloc[0];assert abs(g.dollar_trade.sum()-row.net_orders)<=1e-6
  return {'minimum_cash':float(cash.min()),'max_cash_equity_residual':residual,'financing_dollars':0.,'costs_reconcile':True,'finite_continuous_returns':True}
 def metrics(self,b,q,ex,dec):
  d=b.ledger;prev=d.equity.shift().fillna(CAP);costcols=['cost_spread','cost_impact','cost_fees','cost_borrow','cost_margin']
  usd=d[costcols].mul(prev,axis=0);pnl=d.equity-prev;gross=pnl+usd.sum(axis=1)
  peak=d.equity.cummax().clip(lower=CAP);under=d.equity<peak-1e-8;dur=[];streak=0
  for v in under:streak=streak+1 if v else 0;dur.append(streak)
  annual=[]
  for year,g in d.groupby(d.index.year):
   ix=g.index;annual.append({'year':int(year),'net_pnl_usd':float(pnl.loc[ix].sum()),'gross_pnl_usd':float(gross.loc[ix].sum()),'transaction_cost_usd':float(usd.loc[ix].sum().sum())})
  stats=return_metrics(d.net,CAP)
  beta=None
  if ('SPY',int(b.metadata['cost_multiplier']),float(1.).hex()) in self.books:
   spy=self.books[('SPY',int(b.metadata['cost_multiplier']),float(1.).hex())].net_returns;beta=float(d.net.cov(spy)/spy.var()) if spy.var()>0 else None
  participation=(q.dollar_trade.abs()/q.dollar_adv_21) if 'dollar_adv_21' in q else pd.Series(dtype=float)
  maxconc=max((max(v.values()) for v in b.native['holdings'].values() if v),default=0.)
  stats.update({'annual_volatility':risk(b),'beta_to_SPY':beta,'trailing250_net_profit_usd':float(pnl.iloc[-250:].sum()),'annual':annual,'costs_usd':{k:float(usd[k].sum()) for k in costcols},'gross_pnl_usd':float(gross.sum()),'mean_cash_usd':float((d.cash_exp*d.equity).mean()),'mean_cash_fraction':float(d.cash_exp.mean()),'min_cash_usd':float((d.cash_exp*d.equity).min()),'mean_long_names':float(d.n_long.mean()),'max_weight_at_fill':float(maxconc),'underwater_sessions':int(under.sum()),'longest_underwater_sessions':max(dur),'unrecovered_at_end':bool(under.iloc[-1]),'orders_executed':int((q.dollar_trade!=0).sum()),'small_orders_below100':int(((q.dollar_trade.abs()<100)&(q.dollar_trade!=0)).sum()),'funding_reduction_usd':0. if ex.empty else float(ex.funding_reduction.sum()),'max_ADV_fraction':float(participation.max()) if len(participation) else None,'median_ADV_fraction':float(participation.median()) if len(participation) else None,'missing_cost_input_orders':int(q.dollar_adv_21.isna().sum()) if 'dollar_adv_21' in q else 0,'target_excluded_weight_mean':float(dec.excluded_weight.mean()) if not dec.empty else None,'native_info':b.native['info']})
  return stats
 def match(self,model,control,mult):
  receipt=OUT/f'matches/{model}-{control}-c{mult}.json'
  if receipt.exists():return read(receipt)
  low=self.account(model,mult);high=self.account(control,mult)
  if risk(low)>risk(high):low,high=high,low
  target=risk(low);higharm=high.metadata['arm'];evals=[];roots=[]
  def gap(x):
   book=self.account(higharm,mult,float(x));g=risk(book)-target
   evals.append({'scale':float(x),'volatility':risk(book),'gap':g,'account':book.metadata['account_folder']});return g
  segments=read(OUT/'definitions.json')['matching']['segments'] if higharm in STOCKS else [(0.,1.)]
  jumps=[]
  for left,right in segments:
   grid=np.linspace(left,right,5);g=[gap(x) for x in grid]
   roots.extend(float(x) for x,v in zip(grid,g) if abs(v)<=1e-12)
   for x,y,gx,gy in zip(grid[:-1],grid[1:],g[:-1],g[1:]):
    if gx*gy<0:
     xroot=float(brentq(gap,x,y,xtol=1e-10));gg=gap(xroot)
     if abs(gg)<=1e-6:roots.append(xroot)
  for (_,a),(b,_) in zip(segments[:-1],segments[1:]):
   ga,gb=gap(a),gap(b)
   if ga*gb<0:jumps.append({'left_scale':a,'right_scale':b,'left_gap':ga,'right_gap':gb})
  roots=sorted(set(roots));root=roots[0] if roots else None
  matched=self.account(higharm,mult,root) if root is not None else None
  result={'model':model,'control':control,'cost_multiplier':mult,'lower_unscaled_arm':low.metadata['arm'],'scaled_arm':higharm,'target_volatility':target,'roots':roots,'scale':root,'matched':matched is not None,'jump_crossings':jumps,'evaluations':evals,'reason':'Smallest valid root on frozen continuous support segments; ex-post descriptive. No root across a target-filter jump.'}
  if matched:
   ma=matched if higharm==model else low;co=matched if higharm==control else low
   result.update({'model_account':ma.metadata['account_folder'],'control_account':co.metadata['account_folder'],'model_net_profit_usd':ma.net_profit_usd,'control_net_profit_usd':co.net_profit_usd,'increment_usd':ma.net_profit_usd-co.net_profit_usd,'vol_gap':risk(matched)-target})
  save(f'matches/{model}-{control}-c{mult}.json',result)
  print('MATCH',model,control,mult,result['matched'],root,flush=True)
  return result

def main():
 started=time.monotonic();s=Study();s.prepare()
 # SPY first solely supplies beta denominator; no ranking or winner selection.
 for mult in [1,2]:
  for arm in ['SPY','CASH',*STOCKS]:s.account(arm,mult)
 for arm in STOCKS:
  if not any(e.event=='finished' and e.trial_id==f'policy:{arm}' for e in s.ledger.events()):s.ledger.finish(f'policy:{arm}',status='complete',evidence=[s.account(arm,c).metadata['account_folder']+'/complete.json' for c in [1,2]])
 if not (OUT/'primary-complete.json').exists():save('primary-complete.json',{'accounts':12,'calendar':674,'seconds':time.monotonic()-started})
 matches=[s.match(m,c,mult) for mult in [1,2] for m in ARMS[:2] for c in ['RULE_LONG','SPY']]
 save('matching-summary.json',matches)
 summarize(s,started)


def summarize(s,started):
 # One common circular index matrix across all contrasts and both dependent costs.
 n=674;rng=np.random.default_rng(20261102);starts=rng.integers(0,n,size=(1999,math.ceil(n/63)));idx=((starts[:,:,None]+np.arange(63))%n).reshape(1999,-1)[:,:n]
 np.save(OUT/'bootstrap-index.npy',idx)
 contrasts=[];table=[]
 for mult in [1,2]:
  matrix=pd.DataFrame({arm:s.account(arm,mult).net_returns for arm in ARMS});matrix.to_csv(OUT/f'daily-returns-c{mult}.csv',index_label='date')
  diff=np.column_stack([(matrix[m]-matrix[c]).to_numpy() for m,c in CONTRASTS]);means=diff.mean(axis=0)
  bm=diff[idx].mean(axis=1);se=bm.std(axis=0,ddof=1);mx=np.max(np.abs((bm-means)/se),axis=1);critical=float(np.quantile(mx,.95))
  for i,(m,c) in enumerate(CONTRASTS):
   x=diff[:,i];u=x-x.mean();v=float(u@u/n)
   for lag in range(1,6):v+=2*(1-lag/6)*float(u[lag:]@u[:-lag]/n)
   hacse=math.sqrt(max(v,0)/n)
   contrasts.append({'model':m,'control':c,'cost_multiplier':mult,'increment_usd':s.account(m,mult).net_profit_usd-s.account(c,mult).net_profit_usd,'mean_daily_rate_difference':float(means[i]),'annualized_mean_difference':float(means[i]*252),'simultaneous95_annualized_low':float((means[i]-critical*se[i])*252),'simultaneous95_annualized_high':float((means[i]+critical*se[i])*252),'maxT_critical':critical,'maxT_two_sided_p':float((1+(mx>=abs(means[i]/se[i])).sum())/2000),'HAC5_t':float(means[i]/hacse),'effective_block_lengths':n/63})
  for arm in ARMS:
   folder=ROOT/s.account(arm,mult).metadata['account_folder'];table.append({'arm':arm,'cost_multiplier':mult,**read(folder/'metrics.json')})
 save('contrasts.json',contrasts);save('primary-summary.json',table)
 rows=s.ledger.events();accountstarts=[e for e in rows if e.event=='started' and e.trial_id.startswith('account:')]
 counts=Counts(economic_comparisons=12,financial_accounts=len(accountstarts),model_fits=0,variants=4,paper_candidates=0,diagnostic_steps=8+12)
 save('counts.json',{'counts':counts.model_dump(),'definitions':{'economic_comparisons':'six model/control rate contrasts at each cost; dependent sensitivity views','financial_accounts':'all newly executed independent accounts, including every risk-root probe; no saved receipt import counted as new','variants':'four fixed stock allocation policies, each counted once','diagnostic_steps':'eight matching pair assessments plus twelve HAC/bootstrap paired summaries; index draws/solver iterations are not variants'},'account_starts':len(accountstarts),'failed_accounts':[e.trial_id for e in rows if e.event=='finished' and e.status=='failed'],'seconds':time.monotonic()-started,'prior_floor':35,'n_trials_floor':s.ledger.n_trials})
 s.ledger.snapshot(OUT/'trials.snapshot.jsonl')
 b=s.account('LGBM_LONG',1);baseline=s.account('RULE_LONG',1)
 result=Results(direction=BASE.name,kind='financial',engine='open_composer.lab.adapters.book_engine / native equity_book.run_book; pure native variable costs; opt-in fee-funded purchases',source_artifacts=[rel(OUT/x) for x in ['primary-summary.json','contrasts.json','matching-summary.json','inputs.json','spy-input-addendum.json','affected-input-repair.json','hygiene.json','counts.json','trials.snapshot.jsonl','definitions.json','trial-reconciliation.json']],data_and_exposure='Saved original U500/H5 Ridge and LightGBM, rule industry L21/H5, 674 seen sessions 2024-01-08..2026-09-15; independent $20k, close decisions/next open, five cohorts, fixed $100 target filter. No retraining/new scores/held-reference prices.',costs='Actual funded per-account paths at native variable open spread/impact/0.5bp fees, separately 1x/2x; no margin/borrow/cash interest/terminal liquidation.',baseline='RULE_LONG at 1x cost; result.net_profit_usd denotes prespecified first model LGBM_LONG, not a selected winner. All six arms and both costs in primary-summary.json.',n_trials=s.ledger.n_trials,net_profit_usd=b.net_profit_usd,baseline_net_profit_usd=baseline.net_profit_usd,dsr=None,dsr_note='N/A: incomplete appropriate historical trial distribution and inherited score/model selection; 39 is a conservative known policy floor, not an independent count. No actual new selection experiment for PBO.',limitations=LIMITS,counts=counts,counts_artifact=rel(OUT/'counts.json'))
 save('results.json',result.model_dump());(BASE/'results.json').write_text(result.model_dump_json(indent=2)+'\n')
 print('DONE',counts.model_dump(),flush=True)
if __name__=='__main__':main()
