"""Independent read-only reception of saved accounts; no engine/signal replay."""
from pathlib import Path
from datetime import datetime, UTC
import json, sys, time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from open_composer.research.equity_book.costfn import make_cost_fn

HERE = Path(__file__).resolve().parent
E = HERE.parent / 'worker/evidence'
read = lambda p: json.loads(p.read_text())

def main():
    began = time.monotonic()
    close = pd.read_parquet(E / 'close-with-spy.parquet')
    opening = pd.read_parquet(E / 'open-with-spy.parquet').reindex_like(close)
    prices = close.ffill()
    marks = close.notna() & (close > 0)
    last = {s: np.flatnonzero(marks[s].to_numpy())[-1] for s in close if marks[s].any()}
    summaries = read(E / 'primary-summary-audited.json')
    matches = read(E / 'matching-summary-audited.json')
    folders = {}
    for row in summaries:
        arm, cost = row['arm'], row['cost_multiplier']
        fs = list((E/'accounts').glob(f'{arm}-c{cost}-s0x1_0000000000000p0*'))
        fs = [f for f in fs if (f/'complete.json').exists() and not read(f/'native.json')['info']['unknown_symbols']]
        assert len(fs) == 1
        folders[fs[0]] = (arm, cost, 1., row)
    for m in matches:
        if m['matched']:
            p = ROOT/m['control_account']
            folders.setdefault(p, (m['control'],m['cost_multiplier'],m['scale'],None))
    rawcost = make_cost_fn('open')
    rows = []; books = {}; arrays = {}
    for folder, (arm, cost, scale, published) in folders.items():
        d = pd.read_parquet(folder/'daily.parquet')
        q = pd.read_parquet(folder/'orders.parquet')
        ex = pd.read_parquet(folder/'executions.parquet')
        dates, symbols = close.index, close.columns
        order_dollars = pd.Series(0., index=dates)
        fees = pd.Series(0., index=dates)
        increments = pd.DataFrame(0., index=dates, columns=symbols)
        cost_gap = 0.; target_gap = 0.; small_orders = 0
        if len(q):
            assert (q.decision_date < q.trade_date).all()
            assert (q.price > 0).all()
            xx = ex.set_index('trade_date')
            for date, g in q.groupby('trade_date', sort=False):
                parts = rawcost(g)
                for k,v in parts.items():
                    cost_gap = max(cost_gap,abs(cost*v-float(xx.loc[date,k])))
                fees.loc[date] = sum(parts.values())*cost
            order_dollars = q.groupby('trade_date').dollar_trade.sum().reindex(dates,fill_value=0.)
            increments = q.assign(units=q.dollar_trade/q.price).pivot_table(index='trade_date',columns='symbol',values='units',aggfunc='sum').reindex(index=dates,columns=symbols).fillna(0.)
            assert np.max(np.abs(q.dollar_trade-np.where(q.requested_dollar_trade<0,q.requested_dollar_trade,q.requested_dollar_trade*q.funding_lambda))) < 1e-7
            assert ((q.funding_lambda >= 0)&(q.funding_lambda<=1)).all()
            if arm not in ('SPY','CASH'):
                targets = pd.read_parquet(E/f'targets-{arm}.parquet')*scale
                targets = targets.where(targets*20000>=100,0.)
                ri = targets.index.get_indexer(q.decision_date)
                ci = targets.columns.get_indexer(q.symbol)
                assert (ri>=0).all() and (ci>=0).all()
                desired = targets.to_numpy()[ri,ci]*xx.loc[q.trade_date,'equity_before'].to_numpy()
                target_gap = float(np.max(np.abs(desired-q.desired_dollars)))
            small_orders = int(((q.dollar_trade.abs()<100)&(q.dollar_trade!=0)).sum())
        # Reconstruct units by cumulative executed orders; explicitly remove each
        # last-mark entitlement at the native final-price boundary.
        cash_release = pd.Series(0.,index=dates); bridges=[]
        for symbol,j in last.items():
            if j+1 < len(dates):
                units = increments[symbol].iloc[:j+1].sum()
                dollars = units*float(prices[symbol].iloc[j])
                increments.loc[dates[j+1],symbol] -= units
                cash_release.iloc[j+1] += dollars
                if abs(dollars)>1e-8: bridges.append({'symbol':symbol,'date':str(dates[j+1].date()),'dollars':float(dollars)})
        units = increments.cumsum()
        cash = 20000+(cash_release-order_dollars-fees).cumsum()
        equity = cash+(units*prices).sum(axis=1)
        eqgap=float((equity.loc[d.index]-d.equity).abs().max())
        cashgap=float((cash.loc[d.index]-d.equity*d.cash_exp).abs().max())
        heldgap=0.
        if len(q):
            before=units.shift(fill_value=0.)
            # On an entitlement release day the native engine removes holdings before orders.
            for b in bridges: before.loc[pd.Timestamp(b['date']),b['symbol']]=0.
            ri=dates.get_indexer(q.trade_date);ci=symbols.get_indexer(q.symbol)
            heldgap=float(np.max(np.abs(before.to_numpy()[ri,ci]*q.price.to_numpy()-q.held_before_dollars.to_numpy())))
            execprices=opening.where(opening>0).fillna(prices.shift())
            assert np.max(np.abs(execprices.to_numpy()[ri,ci]-q.price))<1e-8
        eq=equity.loc[d.index]; prev=eq.shift(fill_value=20000.)
        returns=eq/prev-1
        returngap=float(np.max(np.abs(returns-d.net)))
        costrate=fees.loc[d.index]/prev
        assert np.max(np.abs(costrate-d[['cost_spread','cost_impact','cost_fees']].sum(axis=1)))<1e-10
        assert (d.cost_borrow==0).all() and (d.cost_margin==0).all() and (d.short_exp==0).all()
        assert cash.min()>=-1e-8
        assert max(eqgap,cashgap,heldgap,cost_gap,target_gap)<1e-6,(folder.name,eqgap,cashgap,heldgap,cost_gap,target_gap)
        assert returngap<1e-10
        peaks=eq.cummax().clip(lower=20000);dd=eq/peaks-1
        streak=0;longest=0
        for v in (eq<peaks-1e-8):
            streak=streak+1 if v else 0;longest=max(longest,streak)
        stats={'arm':arm,'cost_multiplier':cost,'scale':scale,'account':str(folder.relative_to(ROOT)),
          'profit':float(eq.iloc[-1]-20000),'recent250':float(eq.iloc[-1]-eq.iloc[-251]),
          'transaction_cost':float(fees.sum()),'gross_path_pnl':float(eq.iloc[-1]-20000+fees.sum()),
          'volatility':float(returns.std(ddof=1)*np.sqrt(252)), 'sharpe':float(returns.mean()/returns.std(ddof=1)*np.sqrt(252)) if returns.std()>0 else None,
          'drawdown':float(dd.min()),'mean_cash_fraction':float((cash.loc[d.index]/eq).mean()),'underwater_max':longest,
          'minimum_cash':float(cash.min()),'equity_gap':eqgap,'cash_gap':cashgap,'held_gap':heldgap,'cost_gap':cost_gap,'target_gap':target_gap,
          'small_orders':small_orders,'conditional_entitlements':bridges}
        if published:
            for own,old in [('profit','net_profit_usd'),('recent250','trailing250_net_profit_usd'),('volatility','annual_volatility'),('drawdown','max_drawdown')]:
                assert abs(stats[own]-published[old])<1e-7
        rows.append(stats);books[str(folder.relative_to(ROOT))]=stats
        if published: arrays[arm,cost]=returns
        print(arm,cost,scale,'profit',round(stats['profit'],2),'cost',round(stats['transaction_cost'],2),flush=True)
    checked_matches=[]
    for m in matches:
        if not m['matched']:
            assert m['scale'] is None and m['jump_crossings']
            checked_matches.append({'model':m['model'],'control':m['control'],'cost':m['cost_multiplier'],'matched':False})
            continue
        a,b=books[m['model_account']],books[m['control_account']]
        assert abs(a['volatility']-b['volatility'])<1e-6
        assert abs(a['profit']-b['profit']-m['increment_usd'])<1e-6
        assert abs(a['recent250']-b['recent250']-m['trailing250_increment_usd'])<1e-6
        checked_matches.append({'model':m['model'],'control':m['control'],'cost':m['cost_multiplier'],'matched':True,'increment':a['profit']-b['profit'],'recent250_increment':a['recent250']-b['recent250'],'vol_gap':a['volatility']-b['volatility']})
    n=674;rg=np.random.default_rng(20261102)
    starts=rg.integers(n,size=(1999,(n+62)//63))
    ix=((starts[:,:,None]+np.arange(63))%n).reshape(1999,-1)[:,:n]
    assert np.array_equal(ix,np.load(E/'bootstrap-index.npy'))
    contrasts=read(E/'contrasts.json');intervalgap=0.
    for cost in (1,2):
        pub=[x for x in contrasts if x['cost_multiplier']==cost]
        diff=np.stack([(arrays[x['model'],cost]-arrays[x['control'],cost]).to_numpy() for x in pub],axis=1)
        mean=diff.mean(axis=0);draw=diff[ix].mean(axis=1);se=draw.std(axis=0,ddof=1)
        crit=np.quantile(np.max(np.abs((draw-mean)/se),axis=1),.95)
        for i,x in enumerate(pub):
            for val,k in [((mean[i]-crit*se[i])*252,'simultaneous95_annualized_low'),((mean[i]+crit*se[i])*252,'simultaneous95_annualized_high')]:
                intervalgap=max(intervalgap,abs(val-x[k]));assert abs(val-x[k])<1e-9
            assert x['simultaneous95_annualized_low']<0<x['simultaneous95_annualized_high']
    result={'at':datetime.now(UTC).isoformat(),'accounts_independently_reconstructed':len(rows),'accounts':rows,'matched_pairs':checked_matches,'max_interval_gap':intervalgap,'seconds':time.monotonic()-began,'scope':'Saved 12 primary and six selected funded controls; original cost function, actual orders, unit/cash reconstruction, target filter and all 12 paired intervals. No signal replay or new accounts. Conditional last-mark entitlements remain uncertified.'}
    (HERE/'raw-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',len(rows),'accounts',flush=True)

if __name__=='__main__':main()
