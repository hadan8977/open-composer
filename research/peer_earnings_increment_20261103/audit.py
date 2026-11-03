"""Affected data-clock, account and actual-count checks. Never executes a book."""
from pathlib import Path
from datetime import datetime
import json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from research.peer_earnings_increment_20261103.prepare import BASE,OUT,STOCKS,DECISION,START,END,rel
from open_composer.market_sessions import us_equity_session_close,NEW_YORK
from open_composer.lab.ledger import TrialLedger
from open_composer.research.agent_workflow import Results

def main():
    result=Results.model_validate_json((OUT/'results.json').read_text())
    assert result.counts.variants==14 and result.counts.model_fits==0
    c=pd.read_parquet(OUT/'history-close.parquet')
    closes=pd.DatetimeIndex([pd.Timestamp(datetime.combine(d.date(),us_equity_session_close(d.date())),tz=NEW_YORK).tz_convert('UTC') for d in c.index])
    ev=pd.read_parquet(OUT/'events.parquet')
    rp=ev.reaction_pos.to_numpy(int)
    assert np.all(ev.accepted.to_numpy() < closes[rp].to_numpy())
    assert np.all(ev.accepted.to_numpy() >= closes[rp-1].to_numpy())
    assert ev.accession.is_unique and set(ev.source)=={'edgar_index'}
    scores=pd.read_parquet(OUT/'scores.parquet')
    score_ids=scores.set_index(['decision_date','symbol'])[['cik','ff48']]
    assert (scores.peer_issuers>=2).all() and (scores.industry_n>=15).all()
    assert not scores.own_event.any()
    # Independently test recipient issuer exclusion from the saved SEC event clocks.
    lookup={int(cik):np.sort(g.reaction_pos.to_numpy()) for cik,g in ev.groupby('cik')}
    for cik,g in scores.groupby('cik'):
        t=c.index.get_indexer(g.decision_date)
        event_pos=lookup.get(int(cik),np.array([],dtype=int))
        hi=np.searchsorted(event_pos,t,side='right')
        lo=np.searchsorted(event_pos,t-4,side='left')
        assert (hi==lo).all()
    clock_checks=[]
    for arm in STOCKS:
        h=int(arm.split('_H')[1])
        target=pd.read_parquet(OUT/f'targets-{arm}.parquet')
        origin=c.index.get_loc(pd.Timestamp(DECISION))
        assert ((c.index.get_indexer(target.index)-origin)%h==0).all()
        assert np.isin(target.to_numpy(),[0.,.05]).all()
        assert (target.sum(axis=1)<=1+1e-12).all()
        for date,row in target.iterrows():
            names=row.index[row>0]
            valid=set(scores.loc[scores.decision_date==date,'symbol'])
            assert set(names)<=valid
        clock_checks.append({'arm':arm,'decisions':len(target),'cash_decisions':int(target.sum(axis=1).eq(0).sum())})
    account_checks=[];concentration=[]
    for p in sorted((OUT/'accounts').glob('*/complete.json')):
        folder=p.parent
        d=pd.read_parquet(folder/'daily.parquet')
        q=pd.read_parquet(folder/'orders.parquet')
        metrics=json.loads((folder/'metrics.json').read_text())
        assert len(d)==674 and d.index[0]==pd.Timestamp(START) and d.index[-1]==pd.Timestamp(END)
        assert abs(d.equity.iloc[-1]-20000-metrics['net_profit_usd'])<1e-6
        assert (d.cash_exp*d.equity).min()>=-1e-8 and d.long_exp.max()<=1+1e-8
        assert d.cost_borrow.sum()==0 and d.cost_margin.sum()==0
        if not q.empty:
            before=c.index.get_indexer(pd.DatetimeIndex(q.decision_date))
            after=c.index.get_indexer(pd.DatetimeIndex(q.trade_date))
            assert (after==before+1).all()
        account_checks.append({'account':folder.name,'actual_orders':int((q.dollar_trade!=0).sum()),'net_profit_usd':metrics['net_profit_usd']})
        arm=folder.name.split('-c')[0]
        if arm in STOCKS and '-s0x1_0000000000000p0' in folder.name:
            native=json.loads((folder/'native.json').read_text())
            fills={str(date):g for date,g in q.groupby('trade_date')}
            identities={};max_issuer=max_industry=unknown=0.
            for date,weights in native['holdings'].items():
                for row in fills.get(date,pd.DataFrame()).itertuples():
                    if row.dollar_trade>0:
                        r=score_ids.loc[(row.decision_date,row.symbol)]
                        identities[row.symbol]=(str(int(r.cik)),str(int(r.ff48)))
                issuer_weights={};industry_weights={}
                for symbol,w in weights.items():
                    if symbol not in identities:
                        unknown=max(unknown,w);continue
                    issuer,industry=identities[symbol]
                    issuer_weights[issuer]=issuer_weights.get(issuer,0.)+w
                    industry_weights[industry]=industry_weights.get(industry,0.)+w
                max_issuer=max(max_issuer,max(issuer_weights.values(),default=0.))
                max_industry=max(max_industry,max(industry_weights.values(),default=0.))
            assert unknown==0,'Held risk cannot be classified from actual purchase clock'
            concentration.append({'arm':arm,'cost_multiplier':int(folder.name.split('-c')[1][0]),
                'max_issuer_weight_at_fill':max_issuer,'max_entry_industry_weight_at_fill':max_industry,
                'source':rel(folder/'native.json'),'unclassified_weight':unknown})
    rows=TrialLedger(BASE/'trials.jsonl').events()
    starts=[e for e in rows if e.event=='started' and e.trial_id.startswith('account:')]
    finishes=[e for e in rows if e.event=='finished' and e.trial_id.startswith('account:')]
    assert len(starts)==len(finishes)==result.counts.financial_accounts
    complete=sum(e.status=='complete' for e in finishes)
    assert complete==len(account_checks)
    assert len([e for e in rows if e.event=='finished' and e.trial_id.startswith('policy:') and e.status=='complete'])==14
    matches=json.loads((OUT/'matching-summary.json').read_text())
    assert len(matches)==8
    for m in matches:
        if m['matched']:
            assert abs(m['vol_gap'])<=1e-6 and m['scale']==min(m['roots']) and 0<=m['scale']<=1
    receipt={'conclusion':'pass for accepted conditional component; historical SIC/PIT and entitlement caveats remain',
        'strict_reaction_clock_rows':len(ev),'own_event_exclusion_rows':len(scores),
        'policy_clocks':clock_checks,'account_checks':account_checks,'actual_account_starts':len(starts),
        'completed_accounts':complete,'failed_or_interrupted_accounts':len(starts)-complete,
        'matches':len(matches),'matched_pairs':sum(m['matched'] for m in matches),
        'source':rel(OUT/'results.json'),'no_economic_accounts_executed_by_audit':True}
    (OUT/'affected-scientific-audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    pd.DataFrame(concentration).to_csv(OUT/'concentration.csv',index=False)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['account_checks','policy_clocks']},ensure_ascii=False))

if __name__=='__main__':main()
