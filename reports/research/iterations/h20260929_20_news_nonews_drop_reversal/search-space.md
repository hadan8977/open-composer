# Search Space: h20260929_20_news_nonews_drop_reversal

One path, 12 candidates, well under the 24-per-path / 80-per-round caps.

## Path P1: news-vs-no-news drop reversal/drift

- Universe: top-1500 PIT-ADV tier (`data/features/universe_broad`) for the
  long no-news leg; top-1000 PIT-ADV tier (easy-to-borrow proxy) for the
  short news-drift leg.
- Event trigger: market-adjusted (stock close-to-close minus SPY
  close-to-close) one-day return <= -D.
- Grid: D in {0.05, 0.08} x h (hold sessions) in {1, 3, 5} x leg in
  {no_news_long, news_short} = 2 x 3 x 2 = 12 candidates
  (`DROP_NN_D{5,8}_H{1,3,5}`, `DRIFT_NEWS_D{5,8}_H{1,3,5}`).
- Costs: ADV-tiered spread per side (top-500 3bp, 500-1000 6bp, 1000-1500
  12bp) on turnover, plus a 1%/year borrow fee on held short notional for
  the news-drift leg; every cell also reported at 2x costs.
- Benchmark family: S3 incumbent (`screen_lane.s3_incumbent`, reused
  unedited), vol-matched S3 combo control (`diversifier_edge_for_offset`),
  calendar Sharpe/CAGR/max DD vs. BIL risk-free.
- Placebos (internal falsification, not separate manifest candidates):
  (i) news/no-news labels shuffled across each day's qualifying drop events;
  (ii) the same stocks redated to random non-event trading dates. Both
  computed at the trade level per the brief's own decision rule.
- Windows: TEST 2024-01-08..2026-09-17 (decisive, per direction-review.json
  target_regime_and_horizon); STRESS 2016-05-02..2023-09-15 is documented as
  data-infeasible for this mechanism (PIT news/earnings coverage starts only
  in 2024) and is not computed as a decision window -- see
  `data-feasibility.json`.
- Wave/band: this is a single-path direction test (dir:
  no_news_price_shock_reversal_chan), not part of a Wave 9.2-style breadth
  campaign; no campaign contract is bound.

Total candidate budget: 12 (path P1) = 12 (round total), both well under the
24-per-path and 80-per-round caps.
