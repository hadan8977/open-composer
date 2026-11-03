from types import SimpleNamespace
import numpy as np
import pandas as pd
from open_composer.lab.book_funding import fund_long_only_trades
from open_composer.research.equity_book.costfn import make_cost_fn
from research.peer_earnings_increment_20261103.funding_cost import FundingCost

def test_prepared_probes_and_64_bisection_results_equal_original_bitwise():
    raw=make_cost_fn('open')
    q=pd.DataFrame({'symbol':['AAA','BBB','SPY','DDD','EEE'],
        'dollar_trade':[-2000.,7000.,5000.,5000.,4000.], 'price':[10.,200.,400.,25.,4.],
        'prior_close':[10.,200.,400.,np.nan,4.], 'dollar_adv_21':[1e7,1e8,1e10,np.nan,-1.],
        'vol_21':[.04,.02,.01,np.nan,.08], 'trade_date':pd.to_datetime(['2024-01-08','2025-01-08','2026-01-08','2024-01-08','2026-01-08'])})
    state=SimpleNamespace(holdings=pd.Series({'AAA':2000.}),cash=18000.)
    rng=np.random.default_rng(17)
    for mult in [1,2]:
        cost=FundingCost(mult)
        original=lambda t,s:{k:mult*v for k,v in raw(t,s).items()}
        prepared=cost.prepare(q,state)
        for scale in [0.,1.,*rng.uniform(size=20)]:
            x=q.copy()
            x.dollar_trade=np.minimum(q.dollar_trade,0)+scale*np.maximum(q.dollar_trade,0)
            assert prepared(x.dollar_trade.to_numpy())==original(x,state)
            assert cost(x,state)==original(x,state)
        pd.testing.assert_frame_equal(fund_long_only_trades(q,state,cost),fund_long_only_trades(q,state,original),check_exact=True)
