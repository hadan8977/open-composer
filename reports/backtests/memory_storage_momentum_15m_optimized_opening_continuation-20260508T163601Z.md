# Backtest Report: memory_storage_momentum_15m_optimized_opening_continuation

- Run ID: `memory_storage_momentum_15m_optimized_opening_continuation-20260508T163601Z`
- Symbol: `MU`
- Timeframe: `15m`
- Bars: 52
- Signals: 7
- Closed trades: 3
- Start equity: 100000.00
- End equity: 103048.95
- Total return: 3.05%

## Assumptions

- Signals are confirmed on bar close.
- Backtest fills use next bar open.
- Total return is period account-level return, not annualized.
- Position size uses max_position_weight; it is not all-in unless configured.
- Open positions, if any, are marked to the final close and are not counted as closed trades.
- MVP examples are long-only and do not model commissions or slippage.

## Strategy Rules

Entry:
- `close > ema(close, 5)`
- `rsi(close, 6) > 50`
- `volume > sma(volume, 5)`

Exit:
- `close < ema(close, 13)`
- `rsi(close, 6) > 96`

## Signals

- `sig_3f84f340d56b1ed8` 2026-05-04T14:30:00+00:00 entry MU @ 128.40
- `sig_ead6056d734e8e14` 2026-05-04T14:45:00+00:00 exit MU @ 129.20
- `sig_b59465a462b6304c` 2026-05-04T15:00:00+00:00 entry MU @ 129.80
- `sig_452052d1beb0dca9` 2026-05-04T18:45:00+00:00 exit MU @ 137.80
- `sig_50d925bede567d2d` 2026-05-05T13:30:00+00:00 entry MU @ 141.10
- `sig_4be62e735697e244` 2026-05-05T17:45:00+00:00 exit MU @ 150.50
- `sig_115e202ae8038d6d` 2026-05-05T18:00:00+00:00 entry MU @ 151.20

## Trades

- 2026-05-04T14:45:00+00:00 -> 2026-05-04T15:00:00+00:00 PnL 124.61 (0.62%)
- 2026-05-04T15:15:00+00:00 -> 2026-05-04T19:00:00+00:00 PnL 1234.20 (6.16%)
- 2026-05-05T13:45:00+00:00 -> 2026-05-05T18:00:00+00:00 PnL 1350.49 (6.66%)
