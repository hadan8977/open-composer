# Longbridge Integration

Open Composer uses Longbridge as a trial market-data source for OHLCV research,
source comparison, and paper-context data. It does not place Longbridge orders.

## Credentials

The official Longbridge Python SDK API Key flow requires all three values:

- `LONGBRIDGE_APP_KEY`
- `LONGBRIDGE_APP_SECRET`
- `LONGBRIDGE_ACCESS_TOKEN`

`LONGBRIDGE_LANGUAGE`, `LONGBRIDGE_ENABLE_OVERNIGHT`,
`LONGBRIDGE_HTTP_URL`, `LONGBRIDGE_QUOTE_WS_URL`, and
`LONGBRIDGE_TRADE_WS_URL` are optional SDK settings. For US overnight quotes,
set `LONGBRIDGE_ENABLE_OVERNIGHT=true` and verify the account has the required
LV1 OpenAPI quote card.

## Commands

```bash
uv run oc doctor
uv run oc data longbridge-check --symbol QQQ --timeframe 15m
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m --strict-live --count 1000
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
uv run oc capability test
```

Use `--strict-live` when validating credentials or refreshing research data. The
plain `oc data fetch` path may fall back to local cache, sample, or fixture data
and labels that fallback in the manifest.

## Supported Surface

- Live credential and quote-permission check through `oc data longbridge-check`.
- Latest OHLCV pull through the SDK `candlesticks` API.
- Date-range OHLCV pull through the SDK `history_candlesticks_by_date` API.
- Local CSV cache under `data/cache/`.
- Provenance manifests under `data/cache/manifests/`.
- Alpaca/Longbridge source comparison reports under `reports/data/comparisons/`.
- Strategy data source value `data.source=longbridge` for scan, backtest, and
  paper-context workflows.

## Levels, Ranges, And Caveats

- Default feed label: `nasdaq_basic`.
- Adapter periods: `1m`, `5m`, `15m`, `1h`, `daily`, `weekly`.
- `StrategySpec.timeframe`: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `daily`,
  `weekly`.
- Longbridge provider support: `1m`, `5m`, `15m`, `1h`, `daily`, `weekly`;
  unsupported `30m` and `4h` requests fail fast rather than falling back.
- Per-request candlestick count: 1 to 1000 bars.
- Trade sessions: `intraday` by default, or `all` for extended sessions.
- US free/basic data is not consolidated SIP data.
- Historical candlestick symbol quotas and minute-history start dates depend on
  Longbridge account tier, quote card, market, and product rules.
- The capability remains `trial` in `capabilities/registry.yaml` until live
  coverage, delay, quota, and source-comparison evidence are stable.
