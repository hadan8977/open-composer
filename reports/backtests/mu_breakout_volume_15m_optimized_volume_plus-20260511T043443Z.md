# Backtest Report: mu_breakout_volume_15m_optimized_volume_plus

- Run ID: `mu_breakout_volume_15m_optimized_volume_plus-20260511T043443Z`
- Strategy ID: `mu_breakout_volume_15m_optimized_volume_plus`
- Version ID: `ver_aa996a2c5685`
- Spec hash: `aa996a2c5685c8800e1b61adb3b8368838b7d84f897e64466e3f1d5244159e67`
- Strategy backend: `python_reference`
- Execution backend: `python_reference`
- Backend plan path: `none`
- Symbol: `MU`
- Timeframe: `15m`
- Bars: 52
- Signals: 7
- Closed trades: 3
- Start equity: 100000.00
- End equity: 101984.88
- Total return: 1.98%
- Annualized return: 1089.90%
- Sharpe ratio: 45.78
- Total fees: 0.00

## Assumptions

- Signals are confirmed on bar close.
- Backtest fills use next bar open.
- Total return is period account-level return, not annualized.
- Position size uses max_position_weight; it is not all-in unless configured.
- Open positions are marked to the final close and not counted as closed trades.
- Commission is 0% per fill.
- Slippage is 0 bps per fill.
- NautilusTrader-compatible strategies may also emit a backend plan artifact.
- MVP examples are long-only and do not model dividends or corporate actions.

## Strategy Rules

Factors:
- `breakout_level` (expression): `lag(highest(close, 6), 1)`
- `volatility_range` (expression): `atr(5)`
- `bear_cross` (expression): `crossunder(ema(close, 3), ema(close, 8))`

Entry:
- `close > ema(close, 5)`
- `rsi(close, 4) > 56`
- `volume > sma(volume, 5)`

Exit:
- `close < ema(close, 8)`
- `rsi(close, 4) > 94`

## Signals

- `sig_be90a06727e45f3a` 2026-05-04T14:30:00+00:00 entry MU @ 128.40
- `sig_1325daa899d28c1a` 2026-05-04T17:00:00+00:00 exit MU @ 133.90
- `sig_7d8baf28815d609c` 2026-05-04T17:30:00+00:00 entry MU @ 134.60
- `sig_3ca932cd78eab2f0` 2026-05-05T13:30:00+00:00 exit MU @ 141.10
- `sig_c2e06838772a7792` 2026-05-05T13:45:00+00:00 entry MU @ 142.00
- `sig_abbad44039d49453` 2026-05-05T16:30:00+00:00 exit MU @ 147.70
- `sig_b4f25fcb3dc29d1a` 2026-05-05T16:45:00+00:00 entry MU @ 148.80

## Trades

- 2026-05-04T14:45:00+00:00 -> 2026-05-04T17:15:00+00:00 PnL 514.02 (4.28%) fees 0.00
- 2026-05-04T17:45:00+00:00 -> 2026-05-05T13:45:00+00:00 PnL 582.47 (4.83%) fees 0.00
- 2026-05-05T14:00:00+00:00 -> 2026-05-05T16:45:00+00:00 PnL 486.97 (4.01%) fees 0.00
