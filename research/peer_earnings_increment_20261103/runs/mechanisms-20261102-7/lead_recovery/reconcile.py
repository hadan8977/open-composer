"""Fresh Lead reception: read saved accounts, no simulator/account execution."""
from pathlib import Path
from datetime import datetime, timezone
import json, sys, math, time
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT))
from open_composer.market_sessions import us_equity_session_close, NEW_YORK
from open_composer.research.equity_book.costfn import make_cost_fn
from open_composer.research.equity_book.returns import day_legs,delist_positions
from scripts import t22_run as R
HERE=Path(__file__).parent
OUT=HERE.parent/'worker/evidence'
read=lambda p:json.loads(p.read_text())
def check(a,b,tol=1e-7):
    assert np.allclose(a,b,rtol=0,atol=tol,equal_nan=True), f'max gap {np.nanmax(np.abs(np.asarray(a)-np.asarray(b)))}'
begun=time.monotonic()
c=pd.read_parquet(OUT/'close.parquet');o=pd.read_parquet(OUT/'open.parquet')
hist=pd.read_parquet(OUT/'history-close.parquet')
ev=pd.read_parquet(OUT/'events.parquet');scores=pd.read_parquet(OUT/'scores.parquet')
defs=read(OUT/'definitions.json'); matches=read(OUT/'matching-summary.json')
idx=c.index[1:];assert len(idx)==674 and str(idx[-1].date())=='2026-09-15'
# Calendar and input timing reconstructed from actual exchange closes.
closes=pd.DatetimeIndex([pd.Timestamp(datetime.combine(t.date(),us_equity_session_close(t.date())),tz=NEW_YORK).tz_convert('UTC') for t in hist.index])
check(closes.searchsorted(pd.DatetimeIndex(ev.accepted),side='right'),ev.reaction_pos,0)
us=ev[ev.reason.isna()];j=hist.columns.get_indexer(us.ticker);i=us.reaction_pos.to_numpy(int)
check(hist.to_numpy()[i,j]/hist.to_numpy()[i-1,j]-hist.SPY.to_numpy()[i]/hist.SPY.to_numpy()[i-1],us.reaction_excess)
assert ev.accession.is_unique and set(ev.source)=={'edgar_index'}
# Reconstruct every covered decision from saved prices, native eligibility and conditional SIC.
store=R.Store();sic=pd.read_parquet(ROOT/'data/features/sic_map/sic_map.parquet')
expected_scores=0;expected_targets=0
for date in pd.read_parquet(OUT/'targets-ME_H5.parquet').index:
    t=hist.index.get_loc(date);st=store.pos(date)
    adv=np.asarray(store.m('dollar_adv_21')[st],float)
    eligible=set(store.symbols[R.candidates(store,st,500,'none',adv)&(adv>0)])
    links=sic[(sic.link_first_date.isna()|sic.link_first_date.le(date))&(sic.link_last_date.isna()|sic.link_last_date.ge(date))]
    unique=links[['symbol','cik','sic','ff48']].drop_duplicates()
    good=unique[unique.symbol.map(unique.symbol.value_counts()).eq(1)&unique.sic.notna()].set_index('symbol')
    names=sorted(eligible&set(good.index)&set(hist.columns[hist.loc[date].notna()]))
    f=good.loc[names,['cik','ff48']].copy()
    f['M']=hist.iloc[t-21].reindex(names)/hist.iloc[t-252].reindex(names)-1
    p5=hist.iloc[t].reindex(names)/hist.iloc[t-5].reindex(names)-hist.SPY.iloc[t]/hist.SPY.iloc[t-5]
    f['L']=pd.Series(adv,index=store.symbols).reindex(names)
    window=ev[ev.reaction_pos.between(t-4,t)].sort_values(['accepted','accession']).drop_duplicates('cik',keep='last')
    peers=window[window.reason.isna()&window.ticker.isin(names)].copy()
    peers=peers[peers.cik.eq(peers.ticker.map(f.cik))]
    peers['group']=peers.ticker.map(f.ff48)
    groups=peers.groupby('group').agg(E=('reaction_excess','mean'),peer_issuers=('cik','nunique'))
    f['E']=f.ff48.map(groups.E);f['peer_issuers']=f.ff48.map(groups.peer_issuers)
    f['industry_n']=f.ff48.map(f.ff48.value_counts())
    f['P']=(p5.groupby(f.ff48).transform('sum')-p5.fillna(0))/(p5.groupby(f.ff48).transform('count')-p5.notna().astype(int))
    f=f[(f.industry_n>=15)&(f.peer_issuers>=2)&~f.cik.isin(window.cik)&np.isfinite(f[['E','P','M','L']]).all(axis=1)]
    actual=scores[scores.decision_date.eq(date)].set_index('symbol').sort_index()
    assert list(f.index)==list(actual.index)
    for col in ['cik','ff48','E','P','M','L','peer_issuers','industry_n']:check(f[col],actual[col])
    ranks=f[['E','P','M','L']].rank(method='average',pct=True)
    values=f.groupby('ff48').E.first().sort_index()
    perm=dict(zip(values.index,np.roll(values.to_numpy(),1)))
    ranks['ME']=(ranks.M+ranks.E)/2;ranks['MP']=(ranks.M+ranks.P)/2
    ranks['MX']=(ranks.M+f.ff48.map(perm).rank(method='average',pct=True))/2
    for role in defs['roles']:
        check(ranks[role],actual[role+'_rank'])
        for h in [5,20]:
            target=pd.read_parquet(OUT/f'targets-{role}_H{h}.parquet')
            if date not in target.index:continue
            want=pd.DataFrame({'symbol':ranks.index,'value':ranks[role].values}).sort_values(['value','symbol'],ascending=[False,True]).symbol.head(20)
            got=target.loc[date];assert set(got.index[got>0])==set(want)
            assert (got[got>0]==.05).all();expected_targets+=1
    expected_scores+=len(f)
# All completed ledger cash, wealth, cost and order clocks; never call book_engine.
accounts={};ledger_min_cash=0.;max_gross=0.;max_equity_gap=0.
primary={}
for cp in sorted((OUT/'accounts').glob('*/complete.json')):
    p=cp.parent;d=pd.read_parquet(p/'daily.parquet');q=pd.read_parquet(p/'orders.parquet')
    assert d.index.equals(idx)
    prior=d.equity.shift(fill_value=20000.)
    check(d.equity,prior*(1+d.net));check(d.net,d.gross-d[['cost_spread','cost_impact','cost_fees','cost_borrow','cost_margin']].sum(axis=1))
    assert d.short_exp.abs().max()==0 and d.cost_borrow.abs().max()==0 and d.cost_margin.abs().max()==0
    cash=(d.cash_exp*d.equity).min();ledger_min_cash=min(ledger_min_cash,float(cash));max_gross=max(max_gross,float(d.long_exp.max()))
    assert cash>=-1e-8 and d.long_exp.max()<=1+1e-8
    m=read(p/'metrics.json');check(d.equity.iloc[-1]-20000,m['net_profit_usd'])
    check(d.equity.diff().fillna(d.equity.iloc[0]-20000).iloc[-250:].sum(),m['trailing250_net_profit_usd'])
    if len(q):assert np.all(c.index.get_indexer(q.trade_date)==c.index.get_indexer(q.decision_date)+1)
    accounts[str(p.relative_to(ROOT))]=(p,d,q,m)
    if '-s0x1_0000000000000p0' in p.name:
        arm=p.name.split('-c')[0];mult=int(p.name.split('-c')[1][0]);primary[(arm,mult)]=(p,d,q,m)
assert len(primary)==32 and len(accounts)==139
# Four decisive funded matches and all primary dollar contrasts independently from daily wealth.
match_receipts=[]
for m in matches:
    a=accounts[m['model_account']][1];b=accounts[m['control_account']][1]
    delta=float(a.equity.iloc[-1]-b.equity.iloc[-1]);recent=float(a.equity.diff().iloc[-250:].sum()-b.equity.diff().iloc[-250:].sum())
    gap=float(a.net.std(ddof=1)*np.sqrt(252)-b.net.std(ddof=1)*np.sqrt(252))
    check(delta,m['increment_usd']);check(recent,m['trailing250_increment_usd']);assert abs(gap)<=1e-6
    assert m['scale']==min(m['roots']) and 0<=m['scale']<=1
    match_receipts.append({'model':m['model'],'control':m['control'],'cost':m['cost_multiplier'],'scale':m['scale'],'increment_usd':delta,'trailing250_increment_usd':recent,'model_minus_control_vol_gap':gap})
# Select raw reconstruction: eight ME/MP originals, four scaled ME/MP paths and two SPY paths.
selected={str(primary[(arm,mult)][0].relative_to(ROOT)) for arm in ['ME_H5','MP_H5','ME_H20','MP_H20','SPY'] for mult in [1,2]}
for m in matches:
    if m['control'].startswith('MP_'):selected.update([m['model_account'],m['control_account']])
raw=[];rawcost=make_cost_fn('open');dl=delist_positions(np.isfinite(c.to_numpy()))
for name in sorted(selected):
    p,d,q,metrics=accounts[name];mult=int(p.name.split('-c')[1][0]);ex=pd.read_parquet(p/'executions.parquet').set_index('trade_date')
    fills={t:g for t,g in q.groupby('trade_date')};hold=np.zeros(len(c.columns));cash=20000.;last=c.iloc[0].to_numpy().copy();errs=[];fee_total=0.
    for i,date in enumerate(idx,1):
        gone=(dl==i)&(hold!=0);cash+=hold[gone].sum();hold[gone]=0
        ov,intra,_,priced=day_legs(o.iloc[i].to_numpy(),c.iloc[i].to_numpy(),last);hold*=1+ov
        if date in fills:
            g=fills[date];pos=c.columns.get_indexer(g.symbol);check(hold[pos],g.held_before_dollars)
            check(cash,ex.loc[date,'cash_before']);check(cash+hold.sum(),ex.loc[date,'equity_before'])
            cost={k:mult*v for k,v in rawcost(g).items()}
            for k,v in cost.items():check(v,ex.loc[date,k])
            daycost=sum(cost.values());fee_total+=daycost
            requested=g.requested_dollar_trade.to_numpy();trades=g.dollar_trade.to_numpy();lam=g.funding_lambda.to_numpy()
            check(trades,np.where(requested>0,requested*lam,requested));assert (lam>=0).all() and (lam<=1).all()
            # Decision-time regressors checked directly against the native feature row.
            st=store.pos(g.decision_date.iloc[0]);sj=store.symbols.get_indexer(g.symbol);ok=sj>=0
            for col in ['dollar_adv_21','vol_21','adv_rank']:check(g[col].to_numpy()[ok],np.asarray(store.m(col)[st])[sj[ok]])
            check(g.prior_close.to_numpy(),c.loc[g.decision_date.iloc[0]].reindex(g.symbol).to_numpy())
            cash-=trades.sum()+daycost;hold[pos]+=trades;assert cash>=-1e-8
            check(cash,ex.loc[date,'cash_after'])
        hold*=1+intra;last=np.where(priced,c.iloc[i].to_numpy(),last)
        eq=hold.sum()+cash;errs.append(eq-d.loc[date,'equity']);check(eq,d.loc[date,'equity']);check(cash,d.loc[date,'cash_exp']*d.loc[date,'equity'])
    check(fee_total,sum(metrics['costs_usd'].values()))
    raw.append({'account':p.name,'net_usd':float(d.equity.iloc[-1]-20000),'actual_cost_usd':fee_total,'order_rows':len(q),'max_wealth_gap_usd':max(abs(np.array(errs)))})
# Shared bootstrap recreated from seed; every family exactly ten paired rates.
rng=np.random.default_rng(20261103);n=len(idx)
starts=rng.integers(0,n,size=(1999,math.ceil(n/63)))
indices=((starts[:,:,None]+np.arange(63))%n).reshape(1999,-1)[:,:n]
assert np.array_equal(indices,np.load(OUT/'bootstrap-index.npy'))
contrasts=read(OUT/'contrasts.json');stat=[]
for mult in [1,2]:
    family=[x for x in contrasts if x['cost_multiplier']==mult];assert len(family)==10
    diff=np.column_stack([primary[(x['model'],mult)][1].net.to_numpy()-primary[(x['control'],mult)][1].net.to_numpy() for x in family])
    means=diff.mean(axis=0);boot=diff[indices].mean(axis=1)-means;se=boot.std(axis=0,ddof=1);maxima=np.max(np.abs(boot/se),axis=1);crit=float(np.quantile(maxima,.95))
    for j,x in enumerate(family):
        a=primary[(x['model'],mult)][1];b=primary[(x['control'],mult)][1]
        check(a.equity.iloc[-1]-b.equity.iloc[-1],x['increment_usd'])
        check(a.equity.diff().iloc[-250:].sum()-b.equity.diff().iloc[-250:].sum(),x['trailing250_increment_usd'])
        check(means[j],x['mean_daily_rate_difference']);check(means[j]-crit*se[j],x['simultaneous95_daily_low']);check(means[j]+crit*se[j],x['simultaneous95_daily_high'])
        check(crit,x['maxT_critical']);check((1+(maxima>=abs(means[j]/se[j])).sum())/2000,x['maxT_two_sided_p'])
    stat.append({'cost':mult,'contrasts':10,'critical':crit,'all_simultaneous_intervals_cross_zero':all(x['simultaneous95_daily_low']<0<x['simultaneous95_daily_high'] for x in family)})
# Recovery preserves complete files and original failure status.
recovery=read(OUT/'quota-recovery-start.json');old=recovery['completed_account_files_before_recovery']
for f,meta in old.items():
    st=(OUT/f).stat();assert st.st_size==meta['size'] and st.st_mtime_ns==meta['mtime_ns']
run=read(HERE.parent/'run.json');assert run['status']=='interrupted_or_failed'
rows=[json.loads(x) for x in (OUT/'trials.snapshot.jsonl').read_text().splitlines()]
starts=[r for r in rows if r['event']=='started' and r['trial_id'].startswith('account:')]
ends=[r for r in rows if r['event']=='finished' and r['trial_id'].startswith('account:')]
assert len(starts)==len(ends)==141 and sum(x['status']=='complete' for x in ends)==139
assert sum(r['count'] for r in rows if r['counts_as_trial'] and r['event'] in ['started','prior_exposure'])==26
receipt={'at_utc':datetime.now(timezone.utc).isoformat(),'conclusion':'pass within accepted conditional component scope','no_new_economic_accounts':True,'scientific_definitions_changed':False,'input_event_clocks':len(ev),'usable_event_reactions':len(us),'score_rows_reconstructed':expected_scores,'role_clock_targets_reconstructed':expected_targets,'completed_ledgers_checked':len(accounts),'raw_paths_reconstructed':raw,'minimum_cash_usd':ledger_min_cash,'maximum_long_gross':max_gross,'matches':match_receipts,'statistics':stat,'old_complete_files_unchanged':len(old),'original_driver_status':run['status'],'account_starts':len(starts),'completed_primary':32,'completed_risk_probes':107,'interrupted_starts':2,'registered_trial_floor':26,'seconds':time.monotonic()-begun}
(HERE/'reconciliation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k not in ['raw_paths_reconstructed','matches']},ensure_ascii=False))
