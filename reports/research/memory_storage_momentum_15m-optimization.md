# Strategy Optimization: memory_storage_momentum_15m

- Minimum return target: 3.00%
- Minimum signal target: 1
- Objective: choose the highest-scoring candidate without using future bars.
- Return metric: period account-level return, not annualized.

## Candidates

### memory_storage_momentum_15m_optimized_opening_continuation

- Score: 4.15
- Return: 3.05%
- Signals: 7
- Closed trades: 3
- Entry: `close > ema(close, 5); rsi(close, 6) > 50; volume > sma(volume, 5)`
- Exit: `close < ema(close, 13); rsi(close, 6) > 96`

### memory_storage_momentum_15m_optimized_trend_hold

- Score: 3.42
- Return: 3.02%
- Signals: 3
- Closed trades: 1
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); rsi(close, 6) > 52; volume > sma(volume, 5)`
- Exit: `close < ema(close, 13); rsi(close, 6) > 98`

### memory_storage_momentum_15m_optimized_fast_reentry

- Score: -4.97
- Return: 2.23%
- Signals: 16
- Closed trades: 8
- Entry: `close > ema(close, 3); rsi(close, 3) > 52; volume > sma(volume, 3)`
- Exit: `close < ema(close, 3); rsi(close, 3) > 88`

### memory_storage_momentum_15m_optimized_balanced

- Score: -6.06
- Return: 2.84%
- Signals: 7
- Closed trades: 3
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); rsi(close, 6) > 55; volume > sma(volume, 8)`
- Exit: `close < ema(close, 8); rsi(close, 6) > 92`

### memory_storage_momentum_15m_optimized_fast

- Score: -6.58
- Return: 2.02%
- Signals: 8
- Closed trades: 4
- Entry: `close > ema(close, 5); ema(close, 5) > ema(close, 13); rsi(close, 6) > 55; volume > sma(volume, 5)`
- Exit: `close < ema(close, 5); rsi(close, 6) > 90`

### memory_storage_momentum_15m_optimized_volume

- Score: -7.40
- Return: 1.20%
- Signals: 8
- Closed trades: 4
- Entry: `close > ema(close, 5); rsi(close, 3) > 58; volume > sma(volume, 3)`
- Exit: `close < ema(close, 5); rsi(close, 3) > 94`

## Selected

- Strategy: `memory_storage_momentum_15m_optimized_opening_continuation`
- Return: 3.05%
- Signals: 7
