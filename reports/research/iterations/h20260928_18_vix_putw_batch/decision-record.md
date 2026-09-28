# Decision Record: h20260928_18_vix_putw_batch

## P1

- Path: `vix_putw_batch_screen` (1 candidate: PUTW_HOLD).
- Decision: **stop** (not_executable / dependency_skipped -- vendor data
  unavailable, not a K1/K2 refutation).
- Reason: PUTW is not served by Alpaca (this project's only market-data and
  paper-broker vendor) at all. Direct API checks (2026-09-28):
  `TradingClient(paper=True).get_asset('PUTW')` raised
  `APIError 40410000 "asset not found for PUTW"`;
  `StockHistoricalDataClient.get_stock_bars(symbol='PUTW', feed='sip')`
  returned 0 rows for the most recent 10 trading days. Methodology sanity
  check: the identical calls against XYLD, QYLD, JEPI, JEPQ and DIVO all
  resolved correctly (tradable, bars returned). This is a harder blocker
  than batch 2's earlier finding (PUTW simply absent from the local
  `data/sip/daily` archive): `scripts/fetch_sip_universe.py`'s
  `load_universe()` and `scripts/update_sip_archive.py`'s
  `append_new_symbols()` both source their symbol lists from the same
  Alpaca trading-asset endpoint that returns "asset not found" for PUTW, so
  neither the original bulk backfill nor the incremental updater could ever
  have picked it up. No existing or newly-written local ingestion script can
  fetch data a vendor does not serve; per the brief's rule, the shard layout
  under `data/sip/daily/` was not modified or restructured to work around
  this. No `scripts/screen_batch.py` run occurred; no K1/K2 result exists to
  judge.
- Next iteration suggestion: This is a vendor-data-availability question,
  separate from the shard-layout question batch 2 raised -- reopen only if a
  data-ingestion owner decision adds a source that actually serves PUTW (a
  different market-data vendor), or if a different, Alpaca-tradable
  put-write/covered-call-style proxy is proposed and preregistered as a new
  candidate. VIX_REGIME_SPY_SSO_TLT is not part of this path (dropped by the
  owner's 2026-09-28 cross-asset scope decision, tracked in the registry as
  `dir:spy_sso_tlt_vix_regime_rotation`, status `parked`) even though its
  own data blocker (missing VIX) was successfully resolved this round via
  FRED's VIXCLS series (`data/research/vix/VIXCLS.csv`), which remains
  available for a future equity-only VIX-timing rule.
