"""Trade weekly exposure signals with the registered native ETF account."""

from dataclasses import replace
from importlib import import_module

import pandas as pd

from open_composer.lab.book_funding import fund_long_only_trades
from open_composer.lab.exposure_model import weekly_gate

# The original module exposes the pure C3/S3 replay separately from historical jobs and I/O.
native = import_module("research.levered_index_trend_20261119.runs.lt-20261119-4-1.worker.replay")
POLICIES = ("model", "c3", "weekly_c3", "price", "constant", "vol", "s3")
REQUIRED = ("c3", "price", "constant", "vol")
WINDOWS = {
    "support": ("2019", "2021"),
    "middle": ("2022", "2023"),
    "primary": ("2024", "2025"),
    "context": ("2026-01", "2026-08"),
    "sealed": ("2026-09-01", "2026-11-17"),
}


def constant_account(open_, close, start, end, bp):
    panel = native.PricePanel.from_frames(open_[["TQQQ", "BIL"]], close[["TQQQ", "BIL"]])
    anchor = native.BookCloseAnchor(close.index[close.index.get_loc(start) - 1], native.CAPITAL, {})
    fills = []

    def decide(day, state):
        if abs(state.weights.get("TQQQ", 0.0) - 2 / 3) > 0.10:
            return {"TQQQ": 2 / 3, "BIL": 1 / 3}

    def cost(trades, state):
        return native.turnover_cost(trades.dollar_trade.abs().sum(), bp)

    def fund(trades, state, fee):
        if -1e-8 <= state.cash < 0:
            state = replace(state, cash=0.0)
        return fund_long_only_trades(trades, state, fee)

    def record(trades, state, fees):
        for row in trades.itertuples():
            if abs(row.dollar_trade) > 1e-8:
                fills.append(
                    dict(
                        day=state.date,
                        decision=state.decision_date,
                        clock=state.exec_price,
                        symbol=row.symbol,
                        price=row.price,
                        dollars=row.dollar_trade,
                        cost=native.turnover_cost(abs(row.dollar_trade), bp),
                        net_market_notional=abs(row.dollar_trade),
                        equity_pre_fill=state.equity,
                    )
                )

    config = native.BookConfig(
        freq="D",
        start=str(start.date()),
        end=str(end.date()),
        exec_price="close",
        cost_fn=cost,
        tbill_symbols=("BIL",),
        initial_equity=native.CAPITAL,
        trade_funding=fund,
        trade_observer=record,
        require_observed_open=True,
    )
    book = native.run_book(panel, decide, config, initial_close=anchor)
    return book.daily, book.holdings, fills, None


def account(window, open_, close, signals, cfg, weekly, hurdle, costs, output):
    first, last = WINDOWS[window]
    days = close.loc[first:last].index
    start, end = days[0], days[-1]
    anchor = close.index[close.index.get_loc(start) - 1]
    index = close.loc[anchor:end].index
    gates, vol, rotation = signals
    navs, fills = [], []
    for policy in POLICIES:
        gate = gates
        name = {"vol": "tqqq_vol", "s3": "s3"}.get(policy, "qqq_vol_gate")
        if policy in ("model", "price", "weekly_c3"):
            column, threshold = (
                ("qqq_sma200_gap", 0.01) if policy == "weekly_c3" else (policy, hurdle)
            )
            gate = weekly_gate(index, weekly[column], threshold).to_frame("QQQ")
        for bp in costs:
            if policy == "constant":
                result = constant_account(open_, close, start, end, bp)
            else:
                result, _ = native.replay(
                    name, bp, start, end, open_, close, (gate, vol, rotation), cfg, stop_view=False
                )
            daily, trades, _ = native.audited_path(result)
            daily = daily[["equity", "net", "long_exp", "fees_usd"]].copy()
            semi = trades[trades.symbol.isin(["SOXL", "USD"])]
            daily["semiconductor_exp"] = 0.0
            if len(semi):
                qty = semi.assign(units=semi.dollars / semi.price).pivot_table(
                    index="day", columns="symbol", values="units", aggfunc="sum"
                )
                units = qty.reindex(days).fillna(0.0).cumsum()
                daily["semiconductor_exp"] = (units * close.loc[days, units.columns]).sum(
                    axis=1
                ) / daily.equity
            navs.append(daily.assign(policy=policy, bp=bp, window=window))
            fills.append(trades.assign(policy=policy, bp=bp, window=window))
    pd.concat(navs).rename_axis("day").reset_index().to_parquet(
        output / f"nav-{window}.parquet", index=False
    )
    pd.concat(fills, ignore_index=True).to_parquet(output / f"fills-{window}.parquet", index=False)
