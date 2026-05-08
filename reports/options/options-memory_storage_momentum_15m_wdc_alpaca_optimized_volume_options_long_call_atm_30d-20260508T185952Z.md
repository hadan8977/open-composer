# Options Overlay Backtest: memory_storage_momentum_15m_wdc_alpaca_optimized_volume_options_long_call_atm_30d

- Symbol: `WDC`
- Underlying strategy: `memory_storage_momentum_15m_wdc_alpaca_optimized_volume`
- Overlay: `long_call`
- Trades: 14
- Skipped trades: 30
- Start equity: 100000.00
- End equity: 96786.03
- Total return: -3.21%
- Underlying equity return: 2.13%
- Underlying equity trades: 44

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

- 2026-04-09T15:45:00+00:00 -> 2026-04-09T16:00:00+00:00 contracts=1 PnL=-202.92 option_return=-7.71% underlying_return=0.00%
- 2026-04-09T16:15:00+00:00 -> 2026-04-09T16:45:00+00:00 contracts=1 PnL=-139.62 option_return=-5.18% underlying_return=0.38%
- 2026-04-10T15:30:00+00:00 -> 2026-04-10T16:00:00+00:00 contracts=1 PnL=-204.65 option_return=-7.42% underlying_return=0.05%
- 2026-04-10T17:15:00+00:00 -> 2026-04-10T17:30:00+00:00 contracts=1 PnL=-175.38 option_return=-6.21% underlying_return=0.23%
- 2026-04-13T15:15:00+00:00 -> 2026-04-13T15:30:00+00:00 contracts=1 PnL=-214.24 option_return=-7.69% underlying_return=0.00%
- 2026-04-13T16:45:00+00:00 -> 2026-04-13T17:00:00+00:00 contracts=1 PnL=-197.38 option_return=-7.01% underlying_return=0.11%
- 2026-04-14T14:30:00+00:00 -> 2026-04-14T16:00:00+00:00 contracts=1 PnL=-138.19 option_return=-5.03% underlying_return=0.41%
- 2026-04-14T16:30:00+00:00 -> 2026-04-14T16:45:00+00:00 contracts=1 PnL=-216.01 option_return=-7.78% underlying_return=-0.01%
- 2026-04-15T18:00:00+00:00 -> 2026-04-15T18:15:00+00:00 contracts=1 PnL=-119.10 option_return=-4.20% underlying_return=0.52%
- 2026-04-16T17:30:00+00:00 -> 2026-04-16T18:00:00+00:00 contracts=1 PnL=-353.24 option_return=-12.38% underlying_return=-0.71%
- 2026-04-16T19:15:00+00:00 -> 2026-04-16T19:30:00+00:00 contracts=1 PnL=-223.57 option_return=-7.67% underlying_return=0.01%
- 2026-04-17T13:45:00+00:00 -> 2026-04-17T15:00:00+00:00 contracts=1 PnL=-479.84 option_return=-16.55% underlying_return=-1.35%
- 2026-04-20T16:45:00+00:00 -> 2026-04-20T17:30:00+00:00 contracts=1 PnL=-216.74 option_return=-7.68% underlying_return=0.01%
- 2026-04-21T15:15:00+00:00 -> 2026-04-21T15:45:00+00:00 contracts=1 PnL=-333.07 option_return=-11.62% underlying_return=-0.59%
