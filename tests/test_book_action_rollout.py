"""Anchored actions preserve native fills, missing marks and pre-action clocks."""
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from open_composer.lab.adapters import book_action_rollout
from open_composer.lab.book_funding import fund_long_only_trades
from open_composer.research.equity_book.backtest import BookCloseAnchor, BookConfig, run_book
from open_composer.research.equity_book.costfn import make_cost_fn
from open_composer.research.equity_book.panel import PricePanel


def test_anchor_matches_full_history_with_funding_and_release():
    dates = pd.bdate_range('2024-01-02', periods=12)
    close = pd.DataFrame({'A': np.arange(100.,112.), 'B': [50.,51.,52.,53.,54.,55.,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan]}, index=dates)
    op = close * 1.003
    op.iloc[5,0] = np.nan
    panel = PricePanel.from_frames(op,close)
    captured, orders = {}, []
    def decide(date,state):
        if date == dates[3]: captured['anchor'] = BookCloseAnchor(date,state.equity,state.holdings.to_dict())
        return {'A': .55,'B':.45} if date in [dates[0],dates[3],dates[8]] else None
    cost = make_cost_fn('open')
    def observe(q,st,parts): orders.append((st.date,q.copy(),parts))
    cfg = BookConfig(freq='D',initial_equity=20000.,cost_fn=cost,trade_funding=fund_long_only_trades,trade_observer=observe,tbill_symbols=())
    full = run_book(panel,decide,cfg)
    saved = orders.copy(); orders.clear()
    rolled = book_action_rollout(panel,captured['anchor'],{'A':.55,'B':.45},endpoint=dates[9],config=replace(cfg,start=str(dates[4].date()),end=str(dates[9].date())))
    pd.testing.assert_frame_equal(rolled.daily,full.daily.loc[dates[4]:dates[8]])
    assert rolled.info['terminal_open_pre_action']['equity'] == pytest.approx(full.daily.loc[dates[9],'equity_open_pre'],abs=1e-9)
    assert len(orders)==1
    pd.testing.assert_frame_equal(orders[0][1],saved[1][1])
    assert orders[0][2]==saved[1][2]
    assert rolled.info['delist_exits']==1
    assert rolled.info['terminal_open_pre_action']['holdings'].get('B',0.)==0.


def test_prepared_native_costs_match_all_funding_probes():
    dates=pd.to_datetime(['2025-01-02']*3)
    q=pd.DataFrame(dict(symbol=['A','SPY','B'],dollar_trade=[-500.,300.,200.],price=[100.,500.,30.],trade_date=dates,prior_close=[99.,499.,np.nan],dollar_adv_21=[1e7,1e9,np.nan],vol_21=[.03,.01,np.nan]))
    cost=make_cost_fn('open'); prepared=cost.prepare(q)
    for scale in [0.,.1,.5,1.]:
        probe=q.copy();probe['dollar_trade']=np.minimum(q.dollar_trade,0)+scale*np.maximum(q.dollar_trade,0)
        assert prepared(probe.dollar_trade)==cost(probe)
