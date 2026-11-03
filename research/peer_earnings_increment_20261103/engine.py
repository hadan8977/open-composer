"""Actual independently funded native accounts for the accepted information roles."""
from pathlib import Path
import sys, time, json, math
import numpy as np
import pandas as pd
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.peer_earnings_increment_20261103.prepare import BASE, OUT, STOCKS, ROLES, START, END, DECISION, save, rel
from scripts import t22_run as R
from open_composer.lab.adapters import book_engine
from open_composer.lab.book_funding import fund_long_only_trades
from open_composer.lab.ledger import TrialLedger
from open_composer.lab.models import EngineResult
from open_composer.lab.metrics import return_metrics
from open_composer.research.agent_workflow import require_research, Results, Counts
from open_composer.research.equity_book.backtest import BookConfig
from open_composer.research.equity_book.costfn import make_cost_fn
from open_composer.research.equity_book.returns import day_legs, delist_positions
from research.reversal_long_side_20261102.implementation.engine import Study as PriorStudy
from research.peer_earnings_increment_20261103.funding_cost import FundingCost

CAP = 20000.
ARMS = ['SPY', 'CASH', *STOCKS]
CONTRASTS = [('ME','MP'), ('ME','M'), ('E','P'), ('E','L'), ('ME','MX')]
LIMITS = ['Seen 674-session 2024-01-08..2026-09-15 window; inherited industry/momentum signal-library exposure and incomplete broader trial inventory',
    'Current 2026-10-01 SIC/FF48, conditional unbounded links; not certified historical PIT identity or first public earnings news',
    'Native adjusted economic fractional units, last-mark/freeze/delist release; physical entitlements and fractional broker fills uncertified',
    'Open spread model uses 09:35-09:45 quote snapshot and year calibration; 40bp missing-stock spread fallback, zero missing-input impact; not realized opening costs',
    'Ex-post funded volatility matching is descriptive, scale down only; no interpolation across 0.1 target-filter jump',
    'Only about 10.7 independent 63-session blocks; fixed industry rotation is a descriptive falsifier, not a permutation test']

def read(path):
    return json.loads(path.read_text())

def risk(book):
    return float(book.net_returns.std(ddof=1)*np.sqrt(252))

class Study:
    # Reuse the already accepted dollar/cash and metric checks; no second simulator.
    validate_account = PriorStudy.validate_account
    metrics = PriorStudy.metrics

    def __init__(self):
        require_research(ROOT)
        assert (OUT/'inputs-complete.json').exists()
        self.s = R.Store()
        self.c = pd.read_parquet(OUT/'close.parquet')
        self.o = pd.read_parquet(OUT/'open.parquet')
        self.idx = self.c.index[1:]
        assert len(self.idx) == 674 and self.idx[-1] == pd.Timestamp(END)
        self.attrs = R.make_attrs(self.s, R.PricePanel.from_frames(self.o, self.c))
        self.targets = {arm: pd.read_parquet(OUT/f'targets-{arm}.parquet') for arm in STOCKS}
        self.rawcost = make_cost_fn('open')
        self.books = {}
        self.ledger = TrialLedger(BASE/'trials.jsonl')
        self.scores = pd.read_parquet(OUT/'scores.parquet').set_index(['decision_date','symbol'])

    def account(self, arm, mult, scale=1.):
        scale = float(scale)
        key = (arm, mult, scale.hex())
        if key in self.books:
            return self.books[key]
        name = f'{arm}-c{mult}-s{scale.hex().replace(".","_").replace("+","")}'
        folder = OUT/'accounts'/name
        if (folder/'interrupted.json').exists():
            interruption = read(folder/'interrupted.json')
            attempt = interruption.get('repair_attempt', name+'-funding-probe-repair1')
            assert Path(attempt).name == attempt and attempt.startswith(name+'-')
            name = attempt
            folder = OUT/'accounts'/name
        meta = {'arm': arm, 'cost_multiplier': mult, 'scale': scale, 'account_folder': rel(folder)}
        if (folder/'complete.json').exists():
            d = pd.read_parquet(folder/'daily.parquet')
            b = EngineResult(engine='equity_book.run_book', initial_equity_usd=CAP,
                end_equity_usd=float(d.equity.iloc[-1]), ledger=d, net_returns=d.net, native={}, metadata=meta)
            self.books[key] = b
            return b
        if folder.exists():
            raise RuntimeError(f'Incomplete account {name}; preserve exact checkpoint, no replay')
        folder.mkdir(parents=True)
        tid = 'account:'+name
        self.ledger.start(tid, batch='funded-accounts', candidate=name,
            parameters={'arm':arm, 'mult':mult, 'scale':scale, 'scale_hex':scale.hex()},
            counts_as_trial=False, note='Independent funded primary/cost/benchmark/risk-root accounting view')
        begun = time.monotonic()
        orders, executions, decisions = [], [], []
        cost = FundingCost(mult)
        def observe(q, state, parts):
            q = q.copy()
            q['decision_date'] = state.decision_date
            q['held_before_dollars'] = state.holdings.reindex(q.symbol,fill_value=0).to_numpy()
            orders.append(q)
            cash_after = state.cash-float(q.dollar_trade.sum())-sum(parts.values())
            executions.append({'trade_date':state.date, 'decision_date':state.decision_date,
                'cash_before':state.cash, 'cash_after':cash_after, 'net_orders':float(q.dollar_trade.sum()),
                'equity_before':state.equity, 'equity_after':state.equity-sum(parts.values()),
                'identity_residual':state.equity-sum(parts.values())-(state.holdings.sum()+q.dollar_trade.sum()+cash_after),
                'funding_lambda':float(q.funding_lambda.iloc[0]),
                'funding_reduction':float((q.requested_dollar_trade-q.dollar_trade).sum()), **parts})
        def decide(date,state):
            if arm == 'SPY':
                return {'SPY':scale}
            if arm == 'CASH':
                return {}
            w = self.targets[arm].loc[date]*scale
            keep = w*CAP >= 100
            decisions.append({'date':date, 'raw_target_gross':float(w.sum()), 'retained_target_gross':float(w[keep].sum()),
                              'excluded_names':int(((w>0)&~keep).sum()), 'excluded_weight':float(w[~keep].sum())})
            return w[keep].to_dict()
        try:
            sig = list(self.targets[arm].index) if arm in STOCKS else [self.c.index[0]]
            cfg = BookConfig(freq='D', signal_dates=sig, exec_price='open', cost_fn=cost,
                borrow_bp_per_year=0., margin_rate=.065, tbill_symbols=(), initial_equity=CAP,
                start=DECISION, end=END, trade_attrs=self.attrs, trade_funding=fund_long_only_trades,
                trade_observer=observe, snapshots=True)
            full = book_engine(self.c,self.o,decide,config=cfg)
            d = full.ledger.loc[START:END].copy()
            assert d.index.equals(self.idx)
            b = EngineResult(engine=full.engine, initial_equity_usd=CAP, end_equity_usd=float(d.equity.iloc[-1]),
                ledger=d, net_returns=d.net, native=full.native, metadata=meta)
            q = pd.concat(orders,ignore_index=True) if orders else pd.DataFrame(columns=['trade_date','symbol','dollar_trade','requested_dollar_trade','price'])
            ex = pd.DataFrame(executions)
            dec = pd.DataFrame(decisions)
            d.to_parquet(folder/'daily.parquet')
            q.to_parquet(folder/'orders.parquet',index=False)
            ex.to_parquet(folder/'executions.parquet',index=False)
            dec.to_parquet(folder/'decisions.parquet',index=False)
            checks = self.validate_account(b,q,ex)
            assert d.long_exp.max() <= 1.+1e-8
            stats = self.metrics(b,q,ex,dec)
            stats['turnover_one_sided_sum'] = float(d.turnover.sum())
            stats['turnover_dollars'] = float(q.dollar_trade.abs().sum())
            stats['trailing250_transaction_cost_usd'] = float(d[['cost_spread','cost_impact','cost_fees']].sum(axis=1).mul(d.equity.shift().fillna(CAP)).iloc[-250:].sum())
            stats['gross_max'] = float(d.long_exp.max())
            save(Path('accounts')/name/'metrics.json',stats)
            save(Path('accounts')/name/'native.json',full.native)
            save(Path('accounts')/name/'complete.json',{'seconds':time.monotonic()-begun,'checks':checks})
            self.ledger.finish(tid,status='complete',evidence=[rel(folder/'complete.json')])
            b.native = {}
            self.books[key] = b
            print('ACCOUNT',name,'pnl',round(b.net_profit_usd,2),'vol',round(risk(b),6),'sec',round(time.monotonic()-begun,2),flush=True)
            return b
        except BaseException as error:
            save(Path('accounts')/name/'failure.json',{'error':repr(error),'seconds':time.monotonic()-begun})
            self.ledger.finish(tid,status='failed',evidence=[rel(folder/'failure.json')])
            raise

    def match(self, model, control, mult):
        receipt = OUT/f'matches/{model}-{control}-c{mult}.json'
        if receipt.exists():
            return read(receipt)
        lo, hi = self.account(model,mult), self.account(control,mult)
        if risk(lo)>risk(hi):
            lo,hi = hi,lo
        target = risk(lo)
        arm = hi.metadata['arm']
        evaluations, roots, jumps = [], [], []
        def gap(x):
            b = self.account(arm,mult,float(x))
            value = risk(b)-target
            evaluations.append({'scale':float(x),'volatility':risk(b),'gap':value,'account':b.metadata['account_folder']})
            return value
        segments = read(OUT/'definitions.json')['matching']['segments']
        for left,right in segments:
            grid = np.linspace(left,right,5)
            gs = [gap(x) for x in grid]
            roots.extend(float(x) for x,g in zip(grid,gs) if abs(g)<=1e-12)
            for x,y,gx,gy in zip(grid[:-1],grid[1:],gs[:-1],gs[1:]):
                if gx*gy<0:
                    root = float(brentq(gap,x,y,xtol=1e-10))
                    if abs(gap(root))<=1e-6:
                        roots.append(root)
        a,b = segments[0][1],segments[1][0]
        if gap(a)*gap(b)<0:
            jumps.append([a,b])
        roots = sorted(set(roots))
        r = {'model':model,'control':control,'cost_multiplier':mult,'scaled_arm':arm,
             'lower_unscaled_arm':lo.metadata['arm'],'target_volatility':target,'roots':roots,
             'matched':bool(roots),'scale':roots[0] if roots else None,'jump_crossings':jumps,'evaluations':evaluations}
        if roots:
            matched = self.account(arm,mult,roots[0])
            ma = matched if arm==model else lo
            co = matched if arm==control else lo
            r.update({'model_net_profit_usd':ma.net_profit_usd,'control_net_profit_usd':co.net_profit_usd,
                'increment_usd':ma.net_profit_usd-co.net_profit_usd,'model_account':ma.metadata['account_folder'],
                'control_account':co.metadata['account_folder'],'vol_gap':risk(matched)-target,
                'trailing250_increment_usd':float((ma.ledger.equity.diff().fillna(ma.ledger.equity.iloc[0]-CAP).iloc[-250:]).sum() -
                                                (co.ledger.equity.diff().fillna(co.ledger.equity.iloc[0]-CAP).iloc[-250:]).sum())})
        save(f'matches/{model}-{control}-c{mult}.json',r)
        print('MATCH',model,control,mult,r['matched'],r.get('increment_usd'),flush=True)
        return r

    def attribution(self, arm, mult):
        """Replay only the native price legs on the ACTUAL saved fills, never a new account."""
        book = self.account(arm,mult)
        folder = ROOT/book.metadata['account_folder']
        if (folder/'attribution.json').exists():
            return read(folder/'attribution.json')
        q = pd.read_parquet(folder/'orders.parquet')
        fills = {date:g for date,g in q.groupby('trade_date')}
        cols = self.c.columns
        h = np.zeros(len(cols))
        last = self.c.iloc[0].to_numpy().copy()
        dl = delist_positions(np.isfinite(self.c.to_numpy()))
        accum = np.zeros(len(cols))
        details, holes, bridges, stale, classified = [], [], [], [], {}
        cumulative_by_issuer, cumulative_by_industry = {}, {}
        for i,date in enumerate(self.c.index[1:],1):
            for k in np.flatnonzero((dl==i)&(h!=0)):
                bridges.append({'date':str(date.date()),'symbol':str(cols[k]),'last_mark_cash_release_usd':float(h[k]),'certified_entitlement':False})
                h[k]=0
            oo,cc = self.o.iloc[i].to_numpy(),self.c.iloc[i].to_numpy()
            for k in np.flatnonzero((h!=0)&~np.isfinite(cc)):
                holes.append({'date':str(date.date()),'symbol':str(cols[k]),'frozen_dollars':float(h[k])})
            ov,intra,_,priced = day_legs(oo,cc,last)
            pnl = h*ov
            h *= 1+ov
            if date in fills:
                g = fills[date]
                for row in g.itertuples():
                    k = cols.get_loc(row.symbol)
                    if not np.isfinite(oo[k]):
                        stale.append({'date':str(date.date()),'symbol':row.symbol,'dollar_trade':row.dollar_trade})
                    assert abs(h[k]-row.held_before_dollars)<1e-6
                    h[k] += row.dollar_trade
                    if arm in STOCKS and row.dollar_trade>0:
                        ident = self.scores.loc[(row.decision_date,row.symbol)]
                        classified[k] = (int(ident.cik), int(ident.ff48))
            pnl += h*intra
            h *= 1+intra
            last = np.where(priced,cc,last)
            accum += pnl
            for k in np.flatnonzero(pnl):
                issuer,industry = classified.get(k,(str(cols[k]),'ETF'))
                cumulative_by_issuer[str(issuer)] = cumulative_by_issuer.get(str(issuer),0.)+float(pnl[k])
                cumulative_by_industry[str(industry)] = cumulative_by_industry.get(str(industry),0.)+float(pnl[k])
            costs = book.ledger.loc[date,['cost_spread','cost_impact','cost_fees']].sum()
            before = CAP if i==1 else book.ledger.equity.iloc[i-2]
            expected = book.ledger.equity.iloc[i-1]-before+costs*before
            details.append({'date':date,'gross_pnl_usd':float(pnl.sum()),'gross_residual_usd':float(pnl.sum()-expected),
                            'max_name_weight':float(h.max()/book.ledger.equity.iloc[i-1]),'positions':int((h>0).sum())})
        detail = pd.DataFrame(details)
        assert detail.gross_residual_usd.abs().max()<1e-6
        detail.to_csv(folder/'gross-attribution-daily.csv',index=False)
        symbols = {str(s):float(v) for s,v in zip(cols,accum) if v!=0}
        result = {'gross_pnl_by_symbol_usd':symbols,'gross_pnl_by_issuer_usd':cumulative_by_issuer,
            'gross_pnl_by_entry_industry_usd':cumulative_by_industry,
            'cost_attribution':'Actual aggregate/year cost dollars in metrics.json; issuer/industry contributions are gross, never labeled net alpha',
            'gross_reconciliation_max_usd':float(detail.gross_residual_usd.abs().max()),
            'max_drifted_name_weight':float(detail.max_name_weight.max()),'missing_marks':holes,
            'stale_open_orders':stale,'uncertified_entitlement_bridges':bridges}
        save(Path('accounts')/folder.name/'attribution.json',result)
        return result

def summarize(s, begun):
    n = len(s.idx)
    index_path = OUT/'bootstrap-index.npy'
    if index_path.exists():
        indices = np.load(index_path)
    else:
        rng = np.random.default_rng(20261103)
        starts = rng.integers(0,n,size=(1999,math.ceil(n/63)))
        indices = ((starts[:,:,None]+np.arange(63))%n).reshape(1999,-1)[:,:n]
        np.save(index_path,indices)
    contrasts, table = [], []
    for mult in [1,2]:
        matrix = pd.DataFrame({arm:s.account(arm,mult).net_returns for arm in ARMS})
        matrix.to_csv(OUT/f'daily-returns-c{mult}.csv',index_label='date')
        pairs = [(f'{a}_H{h}',f'{b}_H{h}') for h in [5,20] for a,b in CONTRASTS]
        diff = np.column_stack([(matrix[a]-matrix[b]).to_numpy() for a,b in pairs])
        means = diff.mean(axis=0)
        boot = diff[indices].mean(axis=1)-means
        se = boot.std(axis=0,ddof=1)
        assert (se>0).all()
        maxima = np.max(np.abs(boot/se),axis=1)
        critical = float(np.quantile(maxima,.95))
        for i,(a,b) in enumerate(pairs):
            x = diff[:,i]
            u = x-x.mean()
            v = float(u@u/n)
            for lag in range(1,6):
                v += 2*(1-lag/6)*float(u[lag:]@u[:-lag]/n)
            contrasts.append({'model':a,'control':b,'cost_multiplier':mult,
                'increment_usd':s.account(a,mult).net_profit_usd-s.account(b,mult).net_profit_usd,
                'trailing250_increment_usd':read(ROOT/s.account(a,mult).metadata['account_folder']/'metrics.json')['trailing250_net_profit_usd']-read(ROOT/s.account(b,mult).metadata['account_folder']/'metrics.json')['trailing250_net_profit_usd'],
                'mean_daily_rate_difference':float(means[i]),'simultaneous95_daily_low':float(means[i]-critical*se[i]),
                'simultaneous95_daily_high':float(means[i]+critical*se[i]),'annualized_mean_difference':float(means[i]*252),
                'simultaneous95_annualized_low':float((means[i]-critical*se[i])*252),
                'simultaneous95_annualized_high':float((means[i]+critical*se[i])*252),'maxT_critical':critical,
                'maxT_two_sided_p':float((1+(maxima>=abs(means[i]/se[i])).sum())/2000),
                'HAC5_t':float(means[i]/math.sqrt(max(v,0)/n)),'effective_blocks':n/63})
        for arm in ARMS:
            b = s.account(arm,mult)
            metrics = read(ROOT/b.metadata['account_folder']/'metrics.json')
            attr = s.attribution(arm,mult)
            table.append({'arm':arm,'cost_multiplier':mult, **metrics,
                'missing_mark_days':len(attr['missing_marks']),'uncertified_entitlement_bridges':len(attr['uncertified_entitlement_bridges']),
                'stale_open_orders':len(attr['stale_open_orders']),'max_drifted_name_weight':attr['max_drifted_name_weight']})
    save('contrasts.json',contrasts)
    save('primary-summary.json',table)
    ev = s.ledger.events()
    accounts = [e for e in ev if e.event=='started' and e.trial_id.startswith('account:')]
    failed = [e.trial_id for e in ev if e.event=='finished' and e.status in ['failed','interrupted']]
    counts = Counts(economic_comparisons=20,financial_accounts=len(accounts),model_fits=0,
                    variants=14,paper_candidates=0,diagnostic_steps=28)
    save('counts.json',{'counts':counts.model_dump(),'primary_accounts':32,'risk_probe_accounts':len(accounts)-32-len(failed),
        'failed_accounts':failed,'n_trials_known_floor':s.ledger.n_trials,'current_engine_active_seconds':time.monotonic()-begun,
        'definitions':{'economic_comparisons':'five paired contrasts x two clocks x two dependent cost views',
            'financial_accounts':'All actual independent starts including funded risk-root probes, excluding saved-result imports',
            'diagnostic_steps':'eight risk matches plus twenty paired maxT/HAC summaries; bootstrap draws and funding bisections are not variants'}})
    if not (OUT/'trials.snapshot.jsonl').exists():
        s.ledger.snapshot(OUT/'trials.snapshot.jsonl')
    first,control = s.account('ME_H5',1),s.account('MP_H5',1)
    result = Results(direction=BASE.name,kind='financial',
        engine='open_composer.lab.adapters.book_engine / native equity_book.run_book / book_funding.fund_long_only_trades / shared return_metrics and TrialLedger',
        source_artifacts=[rel(OUT/name) for name in ['primary-summary.json','contrasts.json','matching-summary.json','counts.json','inputs.json','definitions.json','coverage.csv','industry-coverage.csv','events.parquet','scores.parquet','hygiene.json','trial-reconciliation.json','trials.snapshot.jsonl']],
        data_and_exposure='Saved historical U500, current SIC/FF48 conditional links, SEC Item 2.02 actual acceptance -> strictly next exchange close reaction -> next-open entry. Seven roles x fixed 5/20-session clocks, up to twenty 5% slots, common 674 seen sessions. No future return rows, new fits, held-window reads or source refresh.',
        costs='Independent $20k long/cash paths at native open spread/impact/0.5bp fees and 2x all transaction components, including entry; fixed $100 initial-capital position filter applied once after risk scale; 64-bisection fee-funded buys, fixed sales; cash credit zero, no borrow/margin/terminal liquidation.',
        baseline='MP_H5 at 1x costs; scalar ME_H5 is prespecified first contrast, never a selected winner. All fourteen policies, SPY and cash, both costs and risk matches retained.',
        n_trials=s.ledger.n_trials, net_profit_usd=first.net_profit_usd,baseline_net_profit_usd=control.net_profit_usd,
        dsr=None,dsr_note='N/A: historical candidate distribution and broader selection exposure incomplete; no actual candidate-selection experiment for PBO. Registered ancestor/new-policy count is a known floor, not independent tests.',
        limitations=LIMITS,counts=counts,counts_artifact=rel(OUT/'counts.json'))
    save('results.json',result.model_dump())
    (BASE/'results.json').write_text(result.model_dump_json(indent=2)+'\n')
    (OUT.parent/'results.json').write_text(result.model_dump_json(indent=2)+'\n')
    save('engine-complete.json',{'seconds':time.monotonic()-begun,'counts':counts.model_dump()})
    print('DONE',counts.model_dump(),flush=True)

def main():
    begun = time.monotonic()
    s = Study()
    for mult in [1,2]:
        for arm in ARMS:
            s.account(arm,mult)
    for arm in STOCKS:
        if not any(e.event=='finished' and e.trial_id=='policy:'+arm for e in s.ledger.events()):
            s.ledger.finish('policy:'+arm,status='complete',evidence=[s.account(arm,c).metadata['account_folder']+'/complete.json' for c in [1,2]])
    save('primary-complete.json',{'accounts':32,'n_sessions':len(s.idx)})
    matches = [s.match(f'ME_H{h}',f'{control}_H{h}',mult) for mult in [1,2] for h in [5,20] for control in ['MP','M']]
    save('matching-summary.json',matches)
    summarize(s,begun)

if __name__ == '__main__':
    main()
