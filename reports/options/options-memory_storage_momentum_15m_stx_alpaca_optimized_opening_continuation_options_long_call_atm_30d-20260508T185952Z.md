# Options Overlay Backtest: memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation_options_long_call_atm_30d

- Symbol: `STX`
- Underlying strategy: `memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation`
- Overlay: `long_call`
- Trades: 0
- Skipped trades: 39
- Start equity: 100000.00
- End equity: 100000.00
- Total return: 0.00%
- Underlying equity return: 1.68%
- Underlying equity trades: 39

## Option Parameters

- DTE: 30
- Long moneyness: 0.00%
- Short moneyness: None
- IV assumption: 0.65
- Spread assumption: 0.08
- Max premium weight: 0.03

## Assumptions

- Underlying entry/exit signals come from the equity StrategySpec backtest.
- Option prices use a Black-Scholes approximation, not historical option quotes.
- Entry buys at approximate ask and exit sells at approximate bid using spread_pct.
- Implied volatility is held constant through each option trade.
- Contracts are whole-number only; premium at risk is capped by max_premium_weight.
- This is paper/research output, not live options execution.

## Trades

- No option trades.
