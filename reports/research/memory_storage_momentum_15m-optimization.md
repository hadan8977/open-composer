# Strategy Optimization: memory_storage_momentum_15m

- Minimum return target: 1.00%
- Minimum signal target: 1
- Objective: choose the highest-scoring candidate without using future bars.

## Candidates

### memory_storage_momentum_15m_optimized_balanced

- Score: 3.94
- Return: 2.84%
- Signals: 7
- Closed trades: 3
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); rsi(close, 6) > 55; volume > sma(volume, 8)`
- Exit: `close < ema(close, 8); rsi(close, 6) > 92`

### memory_storage_momentum_15m_optimized_fast

- Score: 3.42
- Return: 2.02%
- Signals: 8
- Closed trades: 4
- Entry: `close > ema(close, 5); ema(close, 5) > ema(close, 13); rsi(close, 6) > 55; volume > sma(volume, 5)`
- Exit: `close < ema(close, 5); rsi(close, 6) > 90`

### memory_storage_momentum_15m_optimized_volume

- Score: 2.60
- Return: 1.20%
- Signals: 8
- Closed trades: 4
- Entry: `close > ema(close, 5); rsi(close, 3) > 58; volume > sma(volume, 3)`
- Exit: `close < ema(close, 5); rsi(close, 3) > 94`

## Selected

- Strategy: `memory_storage_momentum_15m_optimized_balanced`
- Return: 2.84%
- Signals: 7
