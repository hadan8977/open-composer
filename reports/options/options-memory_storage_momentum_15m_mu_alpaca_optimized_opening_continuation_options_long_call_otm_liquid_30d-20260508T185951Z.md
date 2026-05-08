# Options Overlay Backtest: memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation_options_long_call_otm_liquid_30d

- Symbol: `MU`
- Underlying strategy: `memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation`
- Overlay: `long_call`
- Trades: 6
- Skipped trades: 35
- Start equity: 100000.00
- End equity: 100016.99
- Total return: 0.02%
- Underlying equity return: 7.83%
- Underlying equity trades: 41

## Option Parameters

- DTE: 30
- Long moneyness: 3.00%
- Short moneyness: None
- IV assumption: 0.70
- Spread assumption: 0.06
- Max premium weight: 0.03

## Assumptions

- Underlying entry/exit signals come from the equity StrategySpec backtest.
- Option prices use a Black-Scholes approximation, not historical option quotes.
- Entry buys at approximate ask and exit sells at approximate bid using spread_pct.
- Implied volatility is held constant through each option trade.
- Contracts are whole-number only; premium at risk is capped by max_premium_weight.
- This is paper/research output, not live options execution.

## Trades

- 2026-04-09T13:45:00+00:00 -> 2026-04-09T14:00:00+00:00 contracts=1 PnL=-414.26 option_return=-13.89% underlying_return=-1.24%
- 2026-04-09T15:45:00+00:00 -> 2026-04-09T19:45:00+00:00 contracts=1 PnL=603.07 option_return=21.16% underlying_return=3.77%
- 2026-04-10T17:45:00+00:00 -> 2026-04-13T13:30:00+00:00 contracts=1 PnL=-565.94 option_return=-19.33% underlying_return=-1.22%
- 2026-04-13T17:30:00+00:00 -> 2026-04-13T18:15:00+00:00 contracts=1 PnL=-217.53 option_return=-7.50% underlying_return=-0.24%
- 2026-04-13T18:45:00+00:00 -> 2026-04-13T19:45:00+00:00 contracts=1 PnL=115.43 option_return=3.89% underlying_return=1.42%
- 2026-04-14T13:45:00+00:00 -> 2026-04-14T16:45:00+00:00 contracts=1 PnL=496.23 option_return=16.73% underlying_return=3.16%
