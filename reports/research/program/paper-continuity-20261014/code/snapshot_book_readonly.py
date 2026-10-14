"""Normal quant1 paper client reads; no account IDs or credentials persisted."""
from __future__ import annotations

import json
import resource
from datetime import UTC, datetime
from pathlib import Path

from open_composer.book_paper.accounts import make_trading_client

OUT=Path('reports/research/program/paper-continuity-20261014/account-snapshot.json')


def scalar(x):
    if x is None or isinstance(x,(bool,int,float,str)):
        return x
    if hasattr(x,'isoformat'):
        return x.isoformat()
    return str(getattr(x,'value',x))


def fields(obj,names):
    return {name:scalar(getattr(obj,name,None)) for name in names}


def main():
    resource.setrlimit(resource.RLIMIT_CPU,(60,61))
    assert not OUT.exists(),'immutable_once_snapshot'
    start=datetime.now(UTC).isoformat()
    client=make_trading_client('quant1')
    try:
        account=client.get_account()
        positions=client.get_all_positions()
        clock=client.get_clock()
        report={'account_alias':'quant1','readonly':True,'broker_calls':['get_account','get_all_positions','get_clock'],
                'request_started_at_UTC':start,'request_finished_at_UTC':datetime.now(UTC).isoformat(),
                'account':fields(account,('status','equity','last_equity','cash','buying_power','long_market_value','short_market_value','portfolio_value','initial_margin','maintenance_margin','trading_blocked','account_blocked','shorting_enabled')),
                'clock':fields(clock,('timestamp','is_open','next_open','next_close')),
                'positions':[fields(p,('symbol','asset_class','side','qty','market_value','cost_basis','avg_entry_price','current_price','unrealized_pl','unrealized_plpc','lastday_price','change_today')) for p in positions],
                'position_count':len(positions),'strategy_current_day_attribution':'N/A no currentstrategyplan; snapshot is currentbrokeraccount/holdings valuation, no historicalfillsfabricated',
                'sensitive_fields_omitted':True,'submit_cancel_close_calls':0}
        OUT.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'account_alias':'quant1','equity':report['account']['equity'],'clock':report['clock'],'position_count':len(positions),'submit_cancel_close_calls':0}))
    finally:
        close=getattr(client,'close',None)
        if close:close()


if __name__=='__main__':
    main()
