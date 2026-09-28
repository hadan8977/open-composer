# Search Space: h20260928_18_vix_putw_batch

One path, `vix_putw_batch_screen`, with exactly 1 preregistered candidate:
PUTW_HOLD (buy-and-hold PUTW, monthly), an honest proxy for
dir:put_credit_spread_income's weekly SPY cash-secured put-writing claim.
No parameter is swept -- PUTW_HOLD's weight (1.0) and frequency (M) are
fixed by the fund's own published monthly option-roll cadence, not fit to
any window's return.

VIX_REGIME_SPY_SSO_TLT is deliberately NOT in this search space: it was
dropped mid-task by the owner's 2026-09-28 cross-asset scope decision (its
bear leg holds TLT), independent of the VIX data blocker that previously
stopped it (which was, in fact, successfully resolved this round --
`data/research/vix/VIXCLS.csv`).

This search space's single candidate is `dependency_skipped`, not
`evaluate`: a direct Alpaca API probe (`TradingClient.get_asset('PUTW')` and
`StockHistoricalDataClient.get_stock_bars(feed='sip')`, both 2026-09-28)
confirms PUTW is not served by Alpaca at all (neither the trading-asset list
nor the SIP market-data API), sanity-checked against five known-tradable
control ETFs (XYLD/QYLD/JEPI/JEPQ/DIVO) using the identical calls. No
`scripts/screen_batch.py` run occurs against this candidate; see
`data-feasibility.json` for the full receipt.

Cost assumption (documented for consistency, not exercised): 10bp per side
primary, 20bp per side stress, next-open fill, per `cost-contract.json`.
Benchmark family (not exercised): the S3 incumbent, a vol-matched
k*S3+(1-k)*SHY control for K2, and SPY/SHY buy-and-hold. Adoption rule
(K1 or K2, owner's 2026-09-28 relaxed keep rule) is documented in
`candidate-manifest.json`'s `adoption_rule` for when/if the data blocker is
ever resolved by a separate vendor decision.
