# Horizon Optimization: memory_storage_momentum_15m

- Experiment: compare higher scan frequency against lower turnover and longer holds.
- Symbols: MU, SNDK, STX, WDC
- Minimum return target: 1.00%
- Minimum closed trades: 1
- Max preferred closed trades: 18
- Return metric: period account-level return, not annualized.
- Scoring penalizes excessive trades/signals because options overlays are spread/theta sensitive.

## Selected Per Symbol

### MU: memory_storage_momentum_15m_mu_alpaca_1h_trend_hold

- Profile: `lower_frequency_trend`
- Timeframe: `1h`
- Score: 7.62
- Bars: 180
- Window: 2026-04-09T13:00:00+00:00 -> 2026-05-08T19:00:00+00:00
- Return: 7.64%
- Signals: 13
- Closed trades: 6
- Max trades/day: 1
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); ema(close, 13) > ema(close, 21); rsi(close, 14) > 54; volume > sma(volume, 8)`
- Exit: `close < ema(close, 21); rsi(close, 14) > 98`

### SNDK: memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold

- Profile: `lower_turnover_hold`
- Timeframe: `15m`
- Score: 3.19
- Bars: 618
- Window: 2026-04-08T19:15:00+00:00 -> 2026-05-08T19:00:00+00:00
- Return: 3.21%
- Signals: 29
- Closed trades: 14
- Max trades/day: 1
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); ema(close, 13) > ema(close, 21); rsi(close, 6) > 55; volume > sma(volume, 8)`
- Exit: `close < ema(close, 21); rsi(close, 6) > 98`

### STX: memory_storage_momentum_15m_stx_alpaca_1h_trend_hold

- Profile: `lower_frequency_trend`
- Timeframe: `1h`
- Score: 2.59
- Bars: 158
- Window: 2026-04-09T13:00:00+00:00 -> 2026-05-08T19:00:00+00:00
- Return: 2.59%
- Signals: 14
- Closed trades: 7
- Max trades/day: 1
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); ema(close, 13) > ema(close, 21); rsi(close, 14) > 54; volume > sma(volume, 8)`
- Exit: `close < ema(close, 21); rsi(close, 14) > 98`

### WDC: memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold

- Profile: `lower_frequency_trend`
- Timeframe: `1h`
- Score: -4.24
- Bars: 170
- Window: 2026-04-09T13:00:00+00:00 -> 2026-05-08T19:00:00+00:00
- Return: 0.77%
- Signals: 13
- Closed trades: 6
- Max trades/day: 1
- Entry: `close > ema(close, 8); ema(close, 5) > ema(close, 13); ema(close, 13) > ema(close, 21); rsi(close, 14) > 54; volume > sma(volume, 8)`
- Exit: `close < ema(close, 21); rsi(close, 14) > 98`

## All Candidates

- `memory_storage_momentum_15m_mu_alpaca_1h_trend_hold` MU profile=lower_frequency_trend timeframe=1h return=7.64% signals=13 trades=6 bars=180 score=7.62
- `memory_storage_momentum_15m_mu_alpaca_15m_swing_hold` MU profile=lower_turnover_hold timeframe=15m return=4.85% signals=29 trades=14 bars=648 score=4.83
- `memory_storage_momentum_15m_mu_alpaca_15m_trend_hold` MU profile=lower_turnover_hold timeframe=15m return=5.19% signals=40 trades=20 bars=648 score=4.43
- `memory_storage_momentum_15m_sndk_alpaca_15m_trend_hold` SNDK profile=lower_turnover_hold timeframe=15m return=3.21% signals=29 trades=14 bars=618 score=3.19
- `memory_storage_momentum_15m_stx_alpaca_1h_trend_hold` STX profile=lower_frequency_trend timeframe=1h return=2.59% signals=14 trades=7 bars=158 score=2.59
- `memory_storage_momentum_15m_sndk_alpaca_15m_swing_hold` SNDK profile=lower_turnover_hold timeframe=15m return=2.43% signals=29 trades=14 bars=618 score=2.42
- `memory_storage_momentum_15m_stx_alpaca_15m_swing_hold` STX profile=lower_turnover_hold timeframe=15m return=1.38% signals=26 trades=13 bars=577 score=1.38
- `memory_storage_momentum_15m_stx_alpaca_15m_trend_hold` STX profile=lower_turnover_hold timeframe=15m return=0.80% signals=36 trades=18 bars=577 score=-4.20
- `memory_storage_momentum_15m_wdc_alpaca_1h_trend_hold` WDC profile=lower_frequency_trend timeframe=1h return=0.77% signals=13 trades=6 bars=170 score=-4.24
- `memory_storage_momentum_15m_sndk_alpaca_1h_trend_hold` SNDK profile=lower_frequency_trend timeframe=1h return=-0.94% signals=19 trades=9 bars=168 score=-10.95
- `memory_storage_momentum_15m_wdc_alpaca_15m_swing_hold` WDC profile=lower_turnover_hold timeframe=15m return=-1.17% signals=29 trades=14 bars=610 score=-11.18
- `memory_storage_momentum_15m_wdc_alpaca_15m_trend_hold` WDC profile=lower_turnover_hold timeframe=15m return=-1.01% signals=40 trades=20 bars=610 score=-11.77
- `memory_storage_momentum_15m_sndk_alpaca_5m_opening_continuation` SNDK profile=higher_frequency_scan timeframe=5m return=2.37% signals=126 trades=63 bars=1759 score=-14.73
- `memory_storage_momentum_15m_wdc_alpaca_5m_opening_continuation` WDC profile=higher_frequency_scan timeframe=5m return=1.90% signals=128 trades=64 bars=1740 score=-15.58
- `memory_storage_momentum_15m_mu_alpaca_5m_opening_continuation` MU profile=higher_frequency_scan timeframe=5m return=2.26% signals=130 trades=65 bars=1839 score=-15.60
- `memory_storage_momentum_15m_stx_alpaca_5m_opening_continuation` STX profile=higher_frequency_scan timeframe=5m return=0.05% signals=130 trades=65 bars=1645 score=-22.81
- `memory_storage_momentum_15m_sndk_alpaca_5m_fast_scan` SNDK profile=higher_frequency_scan timeframe=5m return=1.65% signals=178 trades=89 bars=1759 score=-25.33
- `memory_storage_momentum_15m_mu_alpaca_5m_fast_scan` MU profile=higher_frequency_scan timeframe=5m return=1.49% signals=178 trades=89 bars=1839 score=-25.49
- `memory_storage_momentum_15m_wdc_alpaca_5m_fast_scan` WDC profile=higher_frequency_scan timeframe=5m return=-0.39% signals=176 trades=88 bars=1740 score=-36.99
- `memory_storage_momentum_15m_stx_alpaca_5m_fast_scan` STX profile=higher_frequency_scan timeframe=5m return=-0.40% signals=178 trades=89 bars=1645 score=-37.38

## Interpretation

- If 5m candidates win only through many short trades, they are scanner candidates, not options candidates.
- If 15m or 1h candidates have fewer trades with comparable return, prefer them for option overlays.
- If all candidates underperform the existing equity strategy, keep the current equity strategy and change the options thesis before paper execution.
