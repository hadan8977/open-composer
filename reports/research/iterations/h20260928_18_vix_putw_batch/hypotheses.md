# Hypotheses: h20260928_18_vix_putw_batch

## H1

- Hypothesis: PUTW_HOLD (buy-and-hold PUTW, monthly), an honest proxy for
  dir:put_credit_spread_income's weekly SPY cash-secured put-writing claim,
  can be fetched and screened once VIX and PUTW data are added, per
  T-20260928-18's brief.
- Failure mode: PUTW is not fetchable at all through this project's only
  market-data/broker vendor (Alpaca), independent of any local shard-layout
  or ingestion-script limitation.
- Measurement: `TradingClient(paper=True).get_asset('PUTW')` and
  `StockHistoricalDataClient.get_stock_bars(symbol='PUTW', feed='sip')`
  (most recent 10 trading days), both run 2026-09-28, with XYLD/QYLD/JEPI/
  JEPQ/DIVO as known-tradable controls using the identical calls.
- Result: Failure mode confirmed. `get_asset('PUTW')` raised
  `APIError 40410000 "asset not found for PUTW"`; `get_stock_bars` returned
  0 rows for PUTW over the control window while all five control ETFs
  resolved correctly (`tradable: True`, rows returned) with the same calls.
  PUTW_HOLD is preregistered in `candidate-manifest.json` for the record and
  marked `not_executable`; no `scripts/screen_batch.py` run occurs against
  it in this iteration.
- Stop/Pivot criterion: This is a vendor-data-availability blocker, not a
  refutation of the underlying claim (dir:put_credit_spread_income's CBOE
  PUT-index-level evidence is untouched). Reopen only if a data-ingestion
  owner decision adds a PUTW-serving vendor, or if a different
  Alpaca-tradable put-write proxy (e.g. a covered-call/put-write ETF Alpaca
  does carry) is identified and proposed as a fresh candidate.

## H2 (out of scope this round, recorded for the audit trail)

- Hypothesis: VIX_REGIME_SPY_SSO_TLT (Alvarez's SPY/SSO/TLT VIX-gated 200dma
  regime rotation) could be screened once VIX data is added.
- Result: VIX data was successfully added (`data/research/vix/VIXCLS.csv`,
  FRED VIXCLS, 1990-01-02 through 2026-09-22). The candidate itself is
  dropped from this iteration's manifest per a mid-task scope correction
  from the interactive session (owner, 2026-09-28): no cross-asset
  strategies (this rule's bear leg holds TLT). Not a data or evidence
  failure -- an owner scope decision. Tracked in the registry as
  `dir:spy_sso_tlt_vix_regime_rotation`, status `parked`.
