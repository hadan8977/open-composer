"""Independent daily-open, whole-share reference from the Oct21 observed books.

Uses unchanged saved signals, the accepted after-cost root and T+1 cashbook.
Daily-open fills are a reference assumption, not replayed intraday limit fills.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from open_composer.intraday_runner.source_method_bindings import source_module
from open_composer.lab.metrics import return_metrics
from open_composer.market_sessions import us_equity_session_dates

OUT=ROOT/'reports/owner/paper-recovery-20261103'
POLICIES=['BASE','H5','LSTM','BASE_STATE_BUDGET','MULTI_EQUAL','MULTI_HIERARCHICAL']


def main():
    actual=json.loads((OUT/'actual.json').read_text())
    signal=json.loads((OUT/'lstm-frozen-series.json').read_text())
    cash=source_module(ROOT,'cash')
    calendar=cash.settlement_calendar()
    bindings={};targets={};target_inventory=[]
    def read(path):
        b=path.read_bytes();bindings[str(path.relative_to(ROOT))]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
        return json.loads(b)
    directories=[ROOT/'reports/paper/diagnostics/resume-20261022/target-refresh/live-targets-before-integration',ROOT/'reports/paper/diagnostics/resume-20261022/target-refresh/targets']
    for directory in sorted((ROOT/'reports/paper/diagnostics/dated-target-refresh').glob('*')):
        directories += [directory/'targets',directory/'predecessor-targets']
    for directory in directories:
        for path in directory.glob('*.json'):
            d=read(path)
            if d.get('policy') not in POLICIES or not d.get('application_day'):continue
            app=d['application_day'];policy=d['policy']
            if app<'2026-10-21' or app>'2026-11-02':continue
            d['_path']=str(path.relative_to(ROOT))
            old=targets.get((policy,app))
            if old:
                assert old['symbols']==d['symbols'] and old['weights']==d['weights'], f'Conflicting same-day signals: {policy} {app}'
            else:targets[policy,app]=d
    # The Oct26 LSTM producer stopped before emitting targets. Recompute only
    # that missing historical forecast from its immutable recurrent prefix.
    ref='2026-10-23';i=signal['reference_dates'].index(ref)
    targets['LSTM','2026-10-26']={'policy':'LSTM','application_day':'2026-10-26','reference_day':ref,'symbols':signal['symbols'],'weights':signal['weights'][i],'portfolio_action':'rebalance','_path':'reports/owner/paper-recovery-20261103/lstm-frozen-series.json','_historical_only':True}
    observed_forecast_errors=[]
    for (policy,app),d in targets.items():
        if policy!='LSTM':continue
        j=signal['reference_dates'].index(d['reference_day'])
        saved=dict(zip(d['symbols'],d['weights'],strict=True));derived=dict(zip(signal['symbols'],signal['weights'][j],strict=True))
        err=max(abs(saved.get(s,0)-derived.get(s,0))for s in derived)
        assert err<=2e-6
        observed_forecast_errors.append({'application_day':app,'max_error':err})
    # All six child signals were saved on Oct26, although no complete parent
    # publication occurred. Reassemble their existing declarations offline.
    constituents=read(ROOT/'reports/paper/diagnostics/dated-target-refresh/2026-10-26/current-constituents.json')
    assert set(constituents)=={'S1','S2','S3','C2','BASE','H5'}
    for parent in ['MULTI_EQUAL','MULTI_HIERARCHICAL']:
        if (parent,'2026-10-26') not in targets:
            targets[parent,'2026-10-26']={'policy':parent,'application_day':'2026-10-26','reference_day':'2026-10-23','children':constituents,'_historical_only':True,'_path':'reports/paper/diagnostics/dated-target-refresh/2026-10-26/current-constituents.json'}
    bars={}
    for p in sorted((OUT/'evidence/market').glob('raw-*.json')):
        if p.name.endswith('receipt.json'):continue
        for symbol,rows in read(p).get('bars',{}).items():
            for row in rows:bars[symbol,row['t'][:10]]=row
    dividends={}
    for p in [ROOT/'reports/paper/diagnostics/dated-target-refresh/2026-11-03/source/core-actions-000.raw',ROOT/'reports/paper/diagnostics/dated-target-refresh/2026-11-03/source/ETF-actions-000.raw']:
        for row in read(p).get('corporate_actions',{}).get('cash_dividends',[]):dividends[row['id']]=row
    histories={h['id']:h for h in actual['histories']}
    results=[];daily=[];sim_orders=[]
    for policy in POLICIES:
        end='2026-11-02' if policy in ['H5','LSTM'] else '2026-10-30'
        sessions=[str(d)for d in us_equity_session_dates(date(2026,10,22),date.fromisoformat(end))]
        child_names=([policy] if not policy.startswith('MULTI_') else [h['id'].removeprefix('six/')for h in actual['histories'] if h['id'].startswith('six/'+policy+'/')])
        baseline=sum(float(next(p for p in histories['six/'+n]['points']if p['day']=='2026-10-21')['nav_before_unverified_items_usd'])for n in child_names)
        for cost_bps in [10.,20.]:
            rate=cost_bps/10000
            states={};peaks={};stopped={}
            for n in child_names:
                p=next(p for p in histories['six/'+n]['points']if p['day']=='2026-10-21')
                state=cash.CashState(cash=float(p['cash_from_principal_usd']))
                state.lots={s:[{'quantity':float(q),'funded':'2026-10-21'}]for s,q in p['quantity'].items()}
                states[n]=state;peaks[n]=float(p['nav_before_unverified_items_usd']);stopped[n]=False
            rows=[]
            for ds in sessions:
                target=targets[policy,ds]
                for n,state in states.items():
                    state.settle(ds)
                    for div in dividends.values():
                        if div['ex_date']==ds and state.quantity(div['symbol']):
                            state.dividends.append({'id':div['id'],'due':cash.cash_due_date(div['payable_date'],calendar,dividend=True),'amount':state.quantity(div['symbol'])*div['rate'],'kind':'dividend'})
                    if policy.startswith('MULTI_'):
                        children=target['children'];children={x['name']:x for x in children}if isinstance(children,list)else children
                        instruction=children[n.split('/')[1]]
                        cap=float(next(p for p in histories['six/'+n]['points']if p['day']=='2026-10-21')['capital_usd'])
                    else:instruction=target;cap=20000.
                    names=sorted(set(state.lots)|set(instruction['symbols']))
                    held=np.array([state.quantity(s)for s in names])
                    price=np.array([bars[s,ds]['o']for s in names])
                    nav=state.nav_cash()+float(held@price)
                    stop_limit={'S1':.12,'S2':.15,'S3':.25,'C2':.12}.get(n.split('/')[-1],.25)
                    peaks[n]=max(peaks[n],nav);stopped[n]=stopped[n]or nav<=peaks[n]*(1-stop_limit)
                    if instruction['portfolio_action']=='hold' and not stopped[n]:continue
                    weight=dict(zip(instruction['symbols'],instruction['weights'],strict=True))
                    weights=np.zeros(len(names))if stopped[n]else np.array([weight.get(s,0)for s in names])
                    receivable=sum(v['amount']for v in state.dividends)
                    desired,_=cash.target_quantities(min(cap,nav)-receivable,held,price,weights,rate,True)
                    due=cash.cash_due_date(ds,calendar)
                    for j,s in enumerate(names):
                        q=math.floor(max(0,held[j]-desired[j])+1e-9)
                        if q:
                            got=state.sell(s,q,float(price[j]),rate,ds,due)
                            assert got==q
                            sim_orders.append({'policy':policy,'book':n,'cost_bps':cost_bps,'day':ds,'side':'sell','symbol':s,'qty':got,'price':price[j],'cost_usd':got*price[j]*rate})
                    now=np.array([state.quantity(s)for s in names]);buys=np.maximum(0,desired-now)
                    needed=float(buys@price*(1+rate));scale=min(1,state.available(due)/needed)if needed else 1
                    buys=np.floor(buys*scale+1e-10)
                    for j,s in enumerate(names):
                        q=float(buys[j])
                        if q:
                            state.buy(s,q,float(price[j]),rate,ds,due)
                            sim_orders.append({'policy':policy,'book':n,'cost_bps':cost_bps,'day':ds,'side':'buy','symbol':s,'qty':q,'price':price[j],'cost_usd':q*price[j]*rate})
                nav=sum(st.nav_cash()+sum(st.quantity(s)*bars[s,ds]['c']for s in st.lots if st.quantity(s))for st in states.values())
                rows.append({'policy':policy,'cost_bps':cost_bps,'day':ds,'equity_usd':nav})
            navs=[baseline]+[r['equity_usd']for r in rows]
            returns=pd.Series([navs[i+1]/navs[i]-1 for i in range(len(rows))],index=pd.to_datetime(sessions))
            met=return_metrics(returns,baseline)
            a=next(p for p in histories['six/'+policy]['points']if p['day']==end)
            actual_pnl=float(a['nav_before_unverified_items_usd'])-baseline
            results.append({'policy':policy,'cost_bps':cost_bps,'baseline_day':'2026-10-21','baseline_usd':baseline,'start':'2026-10-22','end':end,'sessions':len(rows),'end_equity_usd':navs[-1],'net_profit_usd':navs[-1]-baseline,'return_pct':met['total_return']*100,'max_drawdown_pct':met['max_drawdown']*100,'modeled_cost_usd':sum(o['cost_usd']for o in sim_orders if o['policy']==policy and o['cost_bps']==cost_bps),'actual_matched_interval_trading_profit_usd':actual_pnl,'actual_matched_interval_return_pct':actual_pnl/baseline*100,'through_nov02_available':end=='2026-11-02','nov02_gap':None if end=='2026-11-02'else'Original monthly receiver requires November BASE model; no late-fit or carried October replacement.'})
            daily+=rows
    pd.DataFrame(daily).to_csv(OUT/'replay_six_daily.csv',index=False)
    pd.DataFrame(sim_orders).to_csv(OUT/'replay_six_orders.csv',index=False)
    inventory=[{'policy':p,'application_day':d,'action':t.get('portfolio_action'),'symbols':t.get('symbols'),'historical_only':t.get('_historical_only',False),'source':t['_path']}for (p,d),t in sorted(targets.items())]
    payload={'results':results,'targets':inventory,'saved_forecast_crosschecks':observed_forecast_errors,'source_bindings':bindings,'assumptions':['Start from the actual Oct21 closing own quantities and economic cash; costs before this date remain in baseline.','Use original unchanged saved targets and frozen recurrent models; only Oct26 missing LSTM forecast and parent assembly are produced independently.','Assume complete daily-open execution, charge 10bp/20bp per side separately, use original whole-share after-cost root and original T+1 CashState buy/sell/settle funding.','No intraday price-protection, partial-fill or quote replay; production submits from 09:40 ET and intraday protection can differ. Treat all figures as a reference backtest, not certified missed broker profit.','Accrue actual declared dividends when earned; they cannot fund buys until payable/settled.','Preserve missing November BASE: affected four policies end Oct30. H5 K=0 is a valid empty target.'],'new_fit_count':0,'parameter_search_count':0}
    (OUT/'replay_six.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
