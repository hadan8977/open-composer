"""Task-local pure funding probes; actual fills use the original native cost callable."""
import numpy as np
import pandas as pd
from open_composer.research.equity_book.costfn import make_cost_fn, _col, ETF_HALF_SPREAD_BP, MISSING_HALF_SPREAD_BP
from open_composer.research.equity_book.costs import half_spread_bp, impact_bp, load_model, FEES_BP_PER_SIDE
from open_composer.research.equity_book.panel import HEDGE_ETFS

class FundingCost:
    def __init__(self, multiplier):
        self.multiplier=multiplier
        self.model=load_model()
        self.original=make_cost_fn('open',model=self.model)

    def __call__(self,trades,state):
        return {k:self.multiplier*v for k,v in self.original(trades,state).items()}

    def prepare(self,trades,state):
        # Fixed quote regressors exactly as costfn.make_cost_fn; order sizes remain
        # variable and impact still calls the native square-root implementation.
        n=len(trades)
        etf=trades.symbol.isin(HEDGE_ETFS).to_numpy()
        adv,vol=_col(trades,'dollar_adv_21',n),_col(trades,'vol_21',n)
        price=_col(trades,'prior_close',n)
        price=np.where(np.isfinite(price),price,_col(trades,'price',n))
        year=pd.to_datetime(trades.trade_date).dt.year.to_numpy()
        with np.errstate(invalid='ignore',divide='ignore'):
            hs=half_spread_bp(price,adv,vol,year,'open',self.model)
        hs=np.where(np.isfinite(hs),hs,MISSING_HALF_SPREAD_BP)
        hs=np.where(etf,ETF_HALF_SPREAD_BP,hs)
        def evaluate(dollar_trade):
            notional=np.abs(np.asarray(dollar_trade,dtype='float64'))
            raw=impact_bp(notional,adv,vol)
            imp=np.where(etf | ~np.isfinite(raw),0.,raw)
            return {'spread':self.multiplier*float(np.sum(notional*hs/1e4)),
                    'impact':self.multiplier*float(np.sum(notional*imp/1e4)),
                    'fees':self.multiplier*float(np.sum(notional)*FEES_BP_PER_SIDE/1e4)}
        return evaluate
