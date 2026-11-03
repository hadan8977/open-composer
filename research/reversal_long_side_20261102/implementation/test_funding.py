"""One affected fixture: small differences/exits and fee-funded variable-cost books."""
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from open_composer.lab.adapters import book_engine
from open_composer.lab.book_funding import fund_long_only_trades
from open_composer.research.equity_book.backtest import BookConfig
from open_composer.research.equity_book.costfn import make_cost_fn


def test_long_cash_funding_small_orders_sales_and_two_costs():
 raw=make_cost_fn('open')
 def attrs(date,symbols):
  return pd.DataFrame({'dollar_adv_21':1e7,'vol_21':.02,'prior_close':100.},index=symbols)
 # Exact $20 difference and sub-$100 full exit are executed, never order-filtered.
 st=SimpleNamespace(holdings=pd.Series({'AAA':180.,'BBB':60.}),cash=19760.)
 q=pd.DataFrame({'symbol':['AAA','BBB'],'dollar_trade':[20.,-60.],'price':[100.,100.],'trade_date':pd.Timestamp('2024-01-08'),'dollar_adv_21':[1e7]*2,'vol_21':[.02]*2,'prior_close':[100.]*2})
 out=fund_long_only_trades(q,st,raw)
 assert out.dollar_trade.tolist()==[20.,-60.]
 dates=pd.bdate_range('2024-01-05',periods=5)
 c=pd.DataFrame(100.,index=dates,columns=['AAA','BBB','SPY'])
 for mult in [1,2]:
  cost=lambda t,s:{k:mult*v for k,v in raw(t,s).items()}
  rows=[]
  def observe(t,s,comps):rows.append((t.copy(),s.cash,sum(comps.values())))
  def decide(date,state):
   return {dates[0]:{'SPY':1.},dates[1]:{'AAA':.5,'BBB':.5},dates[2]:{'AAA':.009},dates[3]:{}}[date]
  cfg=BookConfig(freq='D',initial_equity=20000.,tbill_symbols=(),cost_fn=cost,trade_attrs=attrs,trade_funding=fund_long_only_trades,trade_observer=observe)
  book=book_engine(c,c,decide,config=cfg)
  first=rows[0][0]
  assert float(first.dollar_trade.iloc[0])==pytest.approx(20000/(1+mult*.00015))
  assert (book.ledger.cash_exp*book.ledger.equity).min()>=-1e-8
  assert book.ledger.cost_margin.sum()==0
  sale_buy=rows[1][0]
  assert sale_buy.loc[sale_buy.symbol=='SPY','dollar_trade'].iloc[0]<0
  assert sale_buy.loc[sale_buy.symbol!='SPY','funding_lambda'].iloc[0]<1
  for t,cash,fees in rows:
   assert cash-t.dollar_trade.sum()-fees>=-1e-8
   assert t.cash_after_execution.iloc[0]==pytest.approx(cash-t.dollar_trade.sum()-fees,abs=1e-8)
  assert rows[-1][0].dollar_trade.sum()<0
 # Default first-SPY account retains its legacy debt behavior.
 legacy=book_engine(c,c,lambda d,s:{'SPY':1.} if d==dates[0] else None,config=BookConfig(freq='D',initial_equity=20000,cost_fn=raw,tbill_symbols=()))
 assert legacy.ledger.cash_exp.min()<0
