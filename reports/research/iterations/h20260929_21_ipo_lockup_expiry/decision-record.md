# Decision Record: h20260929_21_ipo_lockup_expiry

## P1: event-list construction and the 20-sample hand-check

Two methods build the PIT event list (`scripts/build_h20260929_21_lockups.py`):
`424b4_confirmed` (SEC EDGAR 424B4 filing, CIK mapped to ticker via the
current `company_tickers.json`, cross-checked against the ticker's first
trade date in `data/features/daily_broad` within a -3..+5 calendar-day
window) and `first_trade_fallback` (a symbol's first trading day in the
panel, restricted to at least 180 days after the panel's own start and
passing a SPAC-unit/warrant-suffix and minimum-price exclusion).

A first 20-event random hand-check (seed 20260929, before the
non-common-stock filter below) found 6/20 (30%) events that were not
genuine common-stock IPOs with employee/VC-lockup dynamics: EIC (a
closed-end fund), BPYPO (a Brookfield Property Partners preferred-unit
series, not common stock), RZC (a Reinsurance Group of America
subordinated-debenture debt security), CCRD (a same-week ticker rename of
an already-public company, Intelligent Systems -> CoreCard, not a new
IPO), BSLK (the first-trade date found, 2021-05-07, does not match Bolt
Threads/Bolt Projects Holdings' actual August 2024 de-SPAC listing --
unresolved data anomaly), and DCX (unable to independently confirm a
matching 2022 Nasdaq IPO in this pass's search; treated as an error absent
confirmation). All 6 errors were in the `first_trade_fallback` method
(6/17 fallback-method samples = 35%); the 3 `424b4_confirmed`-method
samples in that draw (DRIO, FTHM, ULCC) were all correct. Four additional
sampled events were de-SPAC shells (TPGS, RGTI, TGE, PSQL) correctly
tagged `is_despac=True` by this iteration's own heuristic -- counted as
working as intended (a documented, accepted limitation of the 180-day
convention for that subgroup), not as blind errors.

Decision: adjust the method, not just discount confidence. A
preferred/debt-security name-keyword filter (`_NON_COMMON_STOCK_NAME_RE` in
`scripts/build_h20260929_21_lockups.py`) was added, reusing the `name`
field already cached in `data/features/universe/_asset_metadata.parquet`
(the same file `open_composer.research.features.asset_metadata` builds for
ETF/fund exclusion) -- this structurally excludes BPYPO- and RZC-style
securities by name (2 of the 6 found errors). It removed 339 of 3,897
candidate events (8.7%) in the rerun. It does NOT catch a closed-end fund
with a fund-silent legal name (EIC), a same-week ticker rename (CCRD), or
data-source anomalies (BSLK) -- these residual gaps are real and are
reported honestly rather than papered over. Given the time budget for this
iteration, a second independent 20-sample hand-check was NOT performed on
the post-filter event list; the reported error rate is the original,
pre-filter 30% (6/20), explicitly flagged as an upper bound now that 2 of
the 6 known error types are structurally excluded. Confidence in
`first_trade_fallback`-method events is discounted accordingly in
report.md; `424b4_confirmed`-method events are the higher-confidence
subset (0 errors in a small n=3 sample, not independently re-validated at
larger scale either).

- Path: `ipo_lockup_expiry_screen` (13 candidates, 2 windows x 2 ADV
  filters x 3 momentum filters + 1 info-only avoid-long row).
- Decision: proceed to backtest with the event list as built (post-filter),
  the hand-check error rate reported as an honest caveat rather than
  silently treated as resolved.
- Reason: the residual error modes (CEF, ticker-rename, one data anomaly)
  are a minority of events overall and do not invalidate the exercise, but
  they do mean the `first_trade_fallback` subset's results should be read
  with materially lower confidence than the `424b4_confirmed` subset's.
- Next iteration suggestion: if this direction is kept (`watch` or
  stronger), build a proper corporate-action/ticker-history table (or a
  security-type field from a vendor that actually classifies common vs.
  preferred vs. debt) before trusting the fallback method at full weight.

## Final evaluation decision

**Stop.** The backtest (`results.json`, TEST window 2024-01-08..2026-09-17,
13 preregistered candidates) shows `overall_verdict=refuted`: the best
candidate by TEST Sharpe (`L1L5_adv1500_pos`, TEST Sharpe 0.419) misses the
1.19 threshold and the diversifier-edge alternative (-0.274 vs the +0.05
bar), and fails the placebo gate (date-shift +60 and random-date t-stats
both below 2 in absolute value; only date-shift -60 alone clears it).
DSR = 0.159 on trial_count=13. Do not pivot into a variant of this same
mechanism without new information (a different event source, a corrected
lockup-length model, or a materially cleaner event list) — see the "Next
iteration suggestion" above for what a reopen would need.
