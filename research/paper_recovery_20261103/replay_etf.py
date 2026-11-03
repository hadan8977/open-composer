"""Fixed-rule historical replay using native ETF rules and shared return accounting.

No parameter search, model fit, broker call, order or production write.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from open_composer.adapters.execution import rotation_target_weights as rot
from open_composer.lab.accounting import open_close_step
from open_composer.lab.metrics import return_metrics
from open_composer.market_sessions import us_equity_session_dates
from open_composer.models.strategy_spec import load_strategy_spec

OUT=ROOT/'reports/owner/paper-recovery-20261103'
SOURCE=ROOT/'reports/paper/diagnostics/dated-target-refresh/2026-11-03/source'
NAMES={
 'S1':'us_etf_sector_rotation_252_top2_weekly',
 'S2':'us_etf_growth_rotation_blend_top2_monthly',
 'S3':'us_etf_levered_rotation_63_top2_monthly',
 'C2':'us_etf_eom_sector_blend_monthly',
}


def main():
    bindings={}
    def read(p):
        b=p.read_bytes();bindings[str(p.relative_to(ROOT))]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
        return json.loads(b)
    actual=read(OUT/'actual.json')
    cells={}
    for p in sorted(SOURCE.glob('ETF-adjusted-history-*.raw')):
        raw=read(p)
        target=OUT/'evidence'/p.name
        if not target.exists():target.write_bytes(p.read_bytes())
        for symbol,bars in raw['bars'].items():
            for bar in bars:
                key=(symbol,bar['t'][:10]);assert key not in cells
                cells[key]=bar
    # Compare the vintage actually used on Nov2 for every preexisting ETF cell.
    revisions=[]
    signal_cells={}
    for p in sorted((SOURCE.parent.parent/'2026-11-02/source').glob('ETF-adjusted-history-*.raw')):
        raw=read(p)
        for symbol,bars in raw['bars'].items():
            for bar in bars:
                signal_cells[symbol,bar['t'][:10]]=bar
                newer=cells[symbol,bar['t'][:10]]
                for field in ['o','c']:
                    if bar[field]!=newer[field]:revisions.append({'symbol':symbol,'day':bar['t'][:10],'field':field,'before':bar[field],'after':newer[field]})
    # Nov2 bond distributions revise the total-return history. Keep all actual
    # pre-Nov2 signal decisions on the immutable Nov2 capture; use the later
    # total-return vintage solely to measure earned return, never rerank signals.
    assert {r['symbol'] for r in revisions} <= {'SHY','TLT'}
    actions=read(SOURCE/'ETF-actions-000.raw')['corporate_actions']['cash_dividends']
    assert all(any(a['symbol']==s and a['ex_date']=='2026-11-02' for a in actions) for s in {r['symbol'] for r in revisions})
    panel=pd.DataFrame([{'symbol':s,'trade_date':date.fromisoformat(d),'open':r['o'],'close':r['c']} for (s,d),r in signal_cells.items()])
    dates=us_equity_session_dates(date(2024,1,2),date(2026,11,2))
    use=us_equity_session_dates(date(2026,10,1),date(2026,11,2))
    all_results=[];all_daily=[];decisions=[];saved_decision_crosschecks=[]
    for label,name in NAMES.items():
        path=ROOT/'strategy_specs/drafts'/f'{name}.yaml'
        read_bytes=path.read_bytes();bindings[str(path.relative_to(ROOT))]={'sha256':hashlib.sha256(read_bytes).hexdigest(),'bytes':len(read_bytes)}
        spec=load_strategy_spec(path);cfg=spec.portfolio.etf_rotation
        plan_by_day={}
        for plan_path in (ROOT/'reports/paper/rehearsal').glob(name+'-2026-*.json'):
            plan=read(plan_path);session=plan.get('session')
            if session not in {str(d)for d in use} or not plan.get('orders'):continue
            candidate=(plan['generated_at'],str(plan_path.relative_to(ROOT)),plan)
            if session not in plan_by_day or candidate[0]<plan_by_day[session][0]:plan_by_day[session]=candidate
        symbols=sorted(set(cfg.menu)|{cfg.cash_symbol})
        series={s:rot._symbol_series(panel,s) for s in set(symbols)|{'QQQ'}}
        hist=next(h for h in actual['histories'] if h['id']=='legacy/'+name)
        orig=next(s for s in actual['summaries'] if s['id']=='legacy/'+name)
        baseline=float(orig['baseline_nav_usd'])
        pre=next((p for p in hist['points'] if p['day']=='2026-09-30'),None)
        initial_weights=np.array([float(pre['quantity'].get(s,0))*float(pre['marks'][s]['price'])/baseline if pre and pre['quantity'].get(s) else 0 for s in symbols])
        initial_high=max([baseline,float(hist['initial'])]+[float(p['nav_before_unverified_items_usd']) for p in hist['points'] if p['day']<'2026-10-01' and p['nav_before_unverified_items_usd'] is not None])
        native=[]
        for today in use:
            idx=dates.index(today);ref=dates[idx-1]
            formation=rot.resolve_signal_session(series[cfg.cash_symbol][0],str(cfg.rebalance),ref)
            overlay=None
            if cfg.eom_sector_blend is not None:
                r=rot.eom_sector_blend_book(series,formation,menu=list(cfg.menu),cash_symbol=cfg.cash_symbol,reversal_symbol=cfg.eom_sector_blend.reversal_symbol,reversal_weight=float(cfg.eom_sector_blend.reversal_weight),top_n=cfg.top_n)
                assert not r.ineligible and r.reversal_reason is None
                weights=dict(r.weights)
            else:
                scores={s:rot.score_symbol(*series[s],signal_session=formation,lookbacks=list(cfg.lookbacks),min_history_sessions=cfg.min_history_sessions) for s in cfg.menu}
                assert all(v.reason is None for v in scores.values())
                cash=rot.score_symbol(*series[cfg.cash_symbol],signal_session=formation,lookbacks=list(cfg.lookbacks),min_history_sessions=cfg.min_history_sessions)
                picks,_=rot.select_book({s:v.score for s,v in scores.items()},top_n=cfg.top_n,cash_score=cash.score,absolute_momentum_filter=cfg.absolute_momentum_filter)
                weights=rot.build_weights(picks,top_n=cfg.top_n,cash_symbol=cfg.cash_symbol,unfilled_slot_policy=str(cfg.unfilled_slot_policy))
                if cfg.vol_target is not None:
                    d=rot._decide_overlay(panel,series,menu=list(cfg.menu),cash_symbol=cfg.cash_symbol,latest_session=ref,lookbacks=list(cfg.lookbacks),top_n=cfg.top_n,rebalance=str(cfg.rebalance),absolute_momentum_filter=cfg.absolute_momentum_filter,min_history_sessions=cfg.min_history_sessions,unfilled_slot_policy=str(cfg.unfilled_slot_policy),vol_cfg=cfg.vol_target)
                    weights=rot.apply_multiplier(weights,d.multiplier,cfg.cash_symbol)
                    overlay=d.multiplier
            saved_source=None
            if str(today) in plan_by_day:
                _,saved_source,plan=plan_by_day[str(today)]
                recorded={r['symbol']:float(r['target_weight'])for r in plan['orders']if 'target_weight'in r}
                error=max(abs(recorded.get(s,0)-weights.get(s,0))for s in set(recorded)|set(weights))
                saved_decision_crosschecks.append({'strategy':label,'day':str(today),'recipe_vs_original_max_weight_error':error,'original_plan':saved_source,'adoption':'Preserve original dated weights; never silently replace a historical instruction with later adjusted-history recomputation.'})
                assert abs(sum(recorded.values())-1)<1e-8
                weights=recorded
            native.append(np.array([weights.get(s,0) for s in symbols]))
            decisions.append({'strategy':label,'day':str(today),'reference_day':str(ref),'formation_day':str(formation),'weights':weights,'overlay':overlay,'original_dated_signal':saved_source})
        for cost_bps in [10.,20.]:
            nav=baseline;peak=initial_high;previous=initial_weights.copy();stopped=False;stop_day=None;stop_fill_day=None;rows=[]
            for today,w in zip(use,native,strict=True):
                idx=dates.index(today);ref=dates[idx-1]
                current=np.zeros(len(symbols)) if stopped else w
                overnight=np.array([cells[s,str(today)]['o']/cells[s,str(ref)]['c']-1 for s in symbols])
                intraday=np.array([cells[s,str(today)]['c']/cells[s,str(today)]['o']-1 for s in symbols])
                ret,turnover=open_close_step(previous,current,overnight,intraday,cost_bps)
                cost_usd=nav*turnover*cost_bps/10000
                nav*=1+ret;peak=max(peak,nav)
                if stopped and stop_fill_day is None:stop_fill_day=str(today)
                if not stopped and nav<=peak*(1-float(cfg.drawdown_exit_pct)):
                    stopped=True;stop_day=str(today)
                rows.append({'strategy':label,'cost_bps':cost_bps,'day':str(today),'net_return':ret,'turnover':turnover,'cost_usd':cost_usd,'equity_usd':nav,'halted_for_next_open':stopped})
                previous=current.copy()
            returns=pd.Series([r['net_return']for r in rows],index=pd.to_datetime([r['day']for r in rows]))
            met=return_metrics(returns,baseline)
            all_results.append({'strategy':label,'name':name,'cost_bps':cost_bps,'window':['2026-10-01','2026-11-02'],'baseline_usd':baseline,'end_equity_usd':nav,'net_profit_usd':nav-baseline,'return_pct':(nav/baseline-1)*100,'max_drawdown_pct':met['max_drawdown']*100,'modeled_cost_usd':sum(r['cost_usd']for r in rows),'drawdown_exit_pct':float(cfg.drawdown_exit_pct)*100,'stop_signal_day':stop_day,'stop_fill_day':stop_fill_day,'actual_profit_before_unattributed_costs_usd':float(orig['profit_before_unattributed_costs_usd']),'actual_minus_replay_profit_usd':float(orig['profit_before_unattributed_costs_usd'])-(nav-baseline)})
            all_daily+=rows
    pd.DataFrame(all_daily).to_csv(OUT/'replay_etf_daily.csv',index=False)
    (OUT/'replay_etf.json').write_text(json.dumps({'results':all_results,'decisions':decisions,'saved_decision_crosschecks':saved_decision_crosschecks,'source_bindings':bindings,'vintage_revisions':revisions,'accounting':'Shared open_close_step, original screening linear overnight/intraday legs. Starting overnight weights from actual 09-30 holdings. Daily target-weight convention, not exact whole-share funding or broker fill replication. Literal cash after each original spec exit (S1/C2 12%, S2 15%, S3 25%); initial peak retained from actual inception. Preserve 88 actual dated instructions, including the two early-growth weights which differ slightly from later historical recomputation; only missing Oct22 decisions use the native recipe. Nov2 adjusted data enter earned returns only, never historical reranking. Costs are assumed incremental friction on theoretical open fills, never deducted from actual broker fills.','parameter_search_count':0,'new_fit_count':0},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(all_results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
