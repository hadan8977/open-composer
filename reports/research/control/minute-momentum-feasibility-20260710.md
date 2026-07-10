# Minute Momentum Feasibility

- Generated at: `2026-07-10T09:48:02.612370+00:00`
- Provider/feed: `alpaca/iex`
- JSON: `/root/codex-test/open-composer/reports/research/control/minute-momentum-feasibility-20260710.json`
- Manifest: `/root/codex-test/open-composer/reports/research/control/minute-momentum-feasibility-20260710-manifest.json`
- Output dir: `data/research/alpaca_minute`
- Fetch missing: `False`
- Minimum history months: `18.0`
- IEX caveat: Alpaca IEX minute bars are research evidence, not consolidated SIP/full-market paper-ready market evidence unless account entitlements prove otherwise.
- Static stock caveat: Any current large-cap stock subset is static and survivorship-prone; ETF paths are preferred for mom_minute_r1.

## Frequency Bands

| band | go | go timeframes |
|---|---:|---|
| `high_frequency_1m_5m` | `True` | 1m, 5m |
| `medium_frequency_15m_30m` | `True` | 15m, 30m |
| `lower_frequency_1h` | `True` | 1h |

## Path Suitability

| path | go | go timeframes | reason |
|---|---:|---|---|
| `P1_time_series_etf_momentum` | `True` | 15m, 30m, 1h | requires QQQ history on 15m/30m/1h |
| `P2_cross_sectional_etf_rotation` | `False` | none | requires at least 8 ETF symbols with >=18 months in the same timeframe |
| `P3_overnight_intraday_decomposition` | `True` | 30m, 1h | requires QQQ history on 30m/1h plus daily/overnight decomposition |

## Timeframes

| timeframe | go | ok/error | max months |
|---|---:|---:|---:|
| `1m` | `True` | 2/2 | 24.42 |
| `5m` | `True` | 2/2 | 24.42 |
| `15m` | `True` | 2/18 | 24.42 |
| `30m` | `True` | 2/18 | 24.42 |
| `1h` | `True` | 2/18 | 24.42 |

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
| `QQQ` | `1m` | `ok` | 192058 | 24.42 | `True` | history_months>=18.0 |
| `SPY` | `1m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TQQQ` | `1m` | `ok` | 186905 | 24.42 | `True` | history_months>=18.0 |
| `XLK` | `1m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `QQQ` | `5m` | `ok` | 45237 | 24.42 | `True` | history_months>=18.0 |
| `SPY` | `5m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TQQQ` | `5m` | `ok` | 46365 | 24.42 | `True` | history_months>=18.0 |
| `XLK` | `5m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `QQQ` | `15m` | `ok` | 16305 | 24.42 | `True` | history_months>=18.0 |
| `SPY` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `IWM` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `DIA` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLB` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLC` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLE` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLF` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLI` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLK` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLP` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLRE` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLU` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLV` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLY` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TQQQ` | `15m` | `ok` | 16676 | 24.42 | `True` | history_months>=18.0 |
| `SQQQ` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `GLD` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TLT` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `BIL` | `15m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `QQQ` | `30m` | `ok` | 8501 | 24.42 | `True` | history_months>=18.0 |
| `SPY` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `IWM` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `DIA` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLB` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLC` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLE` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLF` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLI` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLK` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLP` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLRE` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLU` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLV` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLY` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TQQQ` | `30m` | `ok` | 8640 | 24.42 | `True` | history_months>=18.0 |
| `SQQQ` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `GLD` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TLT` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `BIL` | `30m` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `QQQ` | `1h` | `ok` | 4442 | 24.42 | `True` | history_months>=18.0 |
| `SPY` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `IWM` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `DIA` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLB` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLC` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLE` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLF` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLI` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLK` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLP` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLRE` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLU` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLV` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `XLY` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TQQQ` | `1h` | `ok` | 4481 | 24.42 | `True` | history_months>=18.0 |
| `SQQQ` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `GLD` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `TLT` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
| `BIL` | `1h` | `error` | 0 | 0.00 | `False` | data_unavailable |
