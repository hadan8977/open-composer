# Universe Optimization: memory_storage_momentum_15m

- Symbols: MU, SNDK, WDC, STX
- Minimum return target: 1.00%
- Minimum signal target: 1
- Max preferred closed trades: 45
- Return metric: period account-level return, not annualized.
- Score penalizes excessive trades/signals for paper/live executability.

## Selected Per Symbol

### MU: memory_storage_momentum_15m_mu_alpaca_optimized_opening_continuation

- Score: 7.80
- Bars: 648
- Return: 7.81%
- Signals: 83
- Closed trades: 41
- Entry: `close > ema(close, 5); rsi(close, 6) > 50; volume > sma(volume, 5)`
- Exit: `close < ema(close, 13); rsi(close, 6) > 96`

### SNDK: memory_storage_momentum_15m_sndk_alpaca_optimized_trend_hold

- Score: 4.43
- Bars: 618
- Return: 4.43%
- Signals: 42
- Closed trades: 21
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); rsi(close, 6) > 52; volume > sma(volume, 5)`
- Exit: `close < ema(close, 13); rsi(close, 6) > 98`

### WDC: memory_storage_momentum_15m_wdc_alpaca_optimized_volume

- Score: 2.13
- Bars: 610
- Return: 2.13%
- Signals: 88
- Closed trades: 44
- Entry: `close > ema(close, 5); rsi(close, 3) > 58; volume > sma(volume, 3)`
- Exit: `close < ema(close, 5); rsi(close, 3) > 94`

### STX: memory_storage_momentum_15m_stx_alpaca_optimized_opening_continuation

- Score: 1.68
- Bars: 577
- Return: 1.68%
- Signals: 78
- Closed trades: 39
- Entry: `close > ema(close, 5); rsi(close, 6) > 50; volume > sma(volume, 5)`
- Exit: `close < ema(close, 13); rsi(close, 6) > 96`
