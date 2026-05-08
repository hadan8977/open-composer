# Backtest Report: memory_storage_momentum_15m_optimized_balanced

- Run ID: `memory_storage_momentum_15m_optimized_balanced-20260508T161746Z`
- Symbol: `MU`
- Timeframe: `15m`
- Bars: 52
- Signals: 7
- Closed trades: 3
- Start equity: 100000.00
- End equity: 102837.49
- Total return: 2.84%

## Assumptions

- Signals are confirmed on bar close.
- Backtest fills use next bar open.
- MVP examples are long-only and do not model commissions or slippage.

## Strategy Rules

Entry:
- `close > ema(close, 8)`
- `ema(close, 5) > ema(close, 13)`
- `rsi(close, 6) > 55`
- `volume > sma(volume, 8)`

Exit:
- `close < ema(close, 8)`
- `rsi(close, 6) > 92`

## Signals

- `sig_116c1fab7ae4412e` 2026-05-04T16:30:00+00:00 entry MU @ 132.50
- `sig_62cac368f2afacb9` 2026-05-04T18:45:00+00:00 exit MU @ 137.80
- `sig_739029b276fb5208` 2026-05-04T19:00:00+00:00 entry MU @ 138.10
- `sig_973c0f544a0f0374` 2026-05-05T14:15:00+00:00 exit MU @ 142.90
- `sig_15303a5c48c8b79f` 2026-05-05T14:30:00+00:00 entry MU @ 143.80
- `sig_c4760534b32cb674` 2026-05-05T17:00:00+00:00 exit MU @ 149.10
- `sig_1e5adcdc27a57db6` 2026-05-05T17:30:00+00:00 entry MU @ 149.40

## Trades

- 2026-05-04T16:45:00+00:00 -> 2026-05-04T19:00:00+00:00 PnL 800.00 (4.00%)
- 2026-05-04T19:15:00+00:00 -> 2026-05-05T14:30:00+00:00 PnL 700.71 (3.48%)
- 2026-05-05T14:45:00+00:00 -> 2026-05-05T17:15:00+00:00 PnL 748.20 (3.69%)
