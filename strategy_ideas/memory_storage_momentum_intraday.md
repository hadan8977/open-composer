# Memory/Storage Momentum Intraday Prompt

## Original User Intent

针对最近的内存存储的动能做一个日内的策略。

## Optimized Product Prompt

Create an intraday long-only strategy for the current memory/storage momentum theme.

Use `MU` as the primary executable symbol and keep `WDC` and `STX` as related watchlist context. The strategy should trade 15-minute bars, use only deterministic technical entry/exit rules for signal generation, and attach SEC filings, FRED macro context, Alpha Vantage watchlist news, and GDELT broad-event context before any manual or paper-trading action.

Constraints:

- Real-money trading remains manual signal only.
- Alpaca Paper can be used later only after the strategy is promoted to active and explicitly allowed.
- Use registered capabilities only: `market.memory_storage_sample`, `events.sec_filings`, `macro.fred_series`, `news.alpha_vantage`, and `news.gdelt`.
- Confirm signals on bar close and assume next-bar-open fills in backtests.
- Optimize candidate technical rules against the deterministic MU 15m fixture and write an optimization report.
- Prefer a strategy with at least one signal and at least 1% sample backtest return, while recording all assumptions and caveats.

## Iteration 2 User Feedback

The first optimized sample returned 2.84% over the fixture window. The user asked whether the return was annualized and requested a continued interaction loop to try more strategy families for higher return.

## Iteration 2 Optimized Product Prompt

Continue optimizing the memory/storage intraday momentum strategy, but do not improve results by simply increasing position size or using future data.

Search a broader set of explainable intraday momentum families:

- balanced EMA/RSI/volume continuation;
- opening continuation with looser RSI confirmation and slower EMA exit;
- trend-hold continuation with fewer daily entries;
- fast re-entry momentum with tighter exits.

Use the same deterministic MU 15m sample fixture, keep `max_position_weight` at 0.20, preserve bar-close signal confirmation and next-bar-open fills, and target at least 3.0% period account-level return if available. Record that the return metric is not annualized.
