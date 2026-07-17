# Minute Momentum Feasibility

- Generated at: `2026-07-17T12:44:21.494973+00:00`
- Provider/feed: `alpaca/iex`
- JSON: `/root/codex-test/open-composer/reports/research/control/minute-momentum-feasibility-mom_stock_intraday_codesign_q1-q1.json`
- Manifest: `/root/codex-test/open-composer/reports/research/control/minute-momentum-feasibility-mom_stock_intraday_codesign_q1-q1-manifest.json`
- Output dir: `data/research/alpaca_minute`
- Fetch missing: `False`
- Minimum history months: `18.0`
- IEX caveat: Alpaca IEX minute bars are research evidence, not consolidated SIP/full-market paper-ready market evidence unless account entitlements prove otherwise.
- Static stock caveat: Any current large-cap stock subset is static and survivorship-prone; ETF paths are preferred for mom_minute_r1.

## Frequency Bands

| band | go | go timeframes |
|---|---:|---|
| `high_frequency_1m_5m` | `False` | none |
| `medium_frequency_15m_30m` | `True` | 15m |
| `lower_frequency_1h` | `False` | none |

## Path Suitability

| path | go | go timeframes | reason |
|---|---:|---|---|
| `P1_time_series_etf_momentum` | `False` | none | requires QQQ history on 15m/30m/1h |
| `P2_cross_sectional_etf_rotation` | `False` | none | requires at least 8 requested ETF symbols and the explicit symbol coverage threshold (100%) with >=18 months in one timeframe |
| `P3_overnight_intraday_decomposition` | `False` | none | requires QQQ history on 30m/1h plus daily/overnight decomposition |

## Timeframes

| timeframe | go | ok/error | max months |
|---|---:|---:|---:|
| `15m` | `True` | 10/0 | 24.41 |

## Cost Table (bps)

| timeframe | base | x2 | x4 |
|---|---:|---:|---:|
| `1m` | 8.0 | 16.0 | 32.0 |
| `5m` | 6.0 | 12.0 | 24.0 |
| `15m` | 4.0 | 8.0 | 16.0 |
| `30m` | 3.0 | 6.0 | 12.0 |
| `1h` | 2.0 | 4.0 | 8.0 |

## Symbol Rows

| symbol | timeframe | status | records | months | go | note |
|---|---|---|---:|---:|---:|---|
| `AAPL` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `AMD` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `AMZN` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `AVGO` | `15m` | `ok` | 13115 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `GOOGL` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `META` | `15m` | `ok` | 13124 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `MSFT` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `NFLX` | `15m` | `ok` | 12986 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `NVDA` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
| `TSLA` | `15m` | `ok` | 13125 | 24.41 | `True` | history_and_session_grid_pass;boundary_sessions_dropped=1 |
