# Options Overlay Backtest: memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold_options_debit_spread_otm_30d

- Symbol: `SNDK`
- Underlying strategy: `memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold`
- Overlay: `debit_call_spread`
- Trades: 2
- Skipped trades: 19
- Start equity: 100000.00
- End equity: 97841.40
- Total return: -2.16%
- Underlying equity return: 4.43%
- Underlying equity trades: 21

## Option Parameters

- DTE: 30
- Long moneyness: 2.00%
- Short moneyness: 10.0
- IV assumption: 0.70
- Spread assumption: 0.12
- Max premium weight: 0.03

## Assumptions

- Underlying entry/exit signals come from the equity StrategySpec backtest.
- Option prices use a Black-Scholes approximation, not historical option quotes.
- Entry buys at approximate ask and exit sells at approximate bid using spread_pct.
- Implied volatility is held constant through each option trade.
- Contracts are whole-number only; premium at risk is capped by max_premium_weight.
- This is paper/research output, not live options execution.

## Trades

- 2026-04-09T15:45:00+00:00 -> 2026-04-09T19:45:00+00:00 contracts=1 PnL=-939.66 option_return=-32.33% underlying_return=3.09%
- 2026-04-10T13:45:00+00:00 -> 2026-04-10T15:15:00+00:00 contracts=1 PnL=-1218.95 option_return=-42.28% underlying_return=-0.48%
