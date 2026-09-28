# Decision Record: h20260928_01_s3_rebalance_tranching

## P1

- Path: s3_rebalance_timing (O00-O20, T4)
- Decision: stop
- Reason: T4 (four tranches at offsets 0/5/10/15) fails all four preregistered
  conditions against the live month-end rule O00 (results.json `adoption`):
  anchor max DD -35.2% vs -32.3% (a false), stress -52.0% vs -48.0% (b false),
  anchor Sharpe 1.52 vs 1.82 (c false, give-up 0.30 > 0.05; stress +0.03),
  anchor CAGR 87.0% with DD -35.2% misses G1 by 0.2 pp and Sharpe < 2 misses
  G1' (d false). The reason is not that tranching hurts: T4 lands on the
  median of the 21 single-date versions, as the literature predicts. It is
  that O00 is the single best of 21 offsets in both the select window
  (CAGR 85.0% vs median 57.3%) and the anchor window (116.3% vs median 85.8%,
  Sharpe 1.82 vs 1.49). Only 10 of 21 offsets pass G1/G1' in the anchor
  window. In the 2016-2023 stress window O00 is ordinary (CAGR rank 9 of 21),
  and in the contaminated 2026 window all 21 offsets pass G1/G1'.
- Reading: S3's headline anchor numbers contain a large rebalance-date luck
  component. A date-neutral expectation for S3 over 2024-01..2026-09 is about
  86% CAGR, Sharpe 1.5, max drawdown about -35%, not 116% / 1.82 / -32%.
  This does not change the live rule (frozen to 2026-11-01) and does not
  refute S3, which still clears G1/G1' on half the dates and on every date in
  2026, but any live-pilot sizing should use the date-neutral numbers.
- Next iteration suggestion: none for tranching (no reopen without a new
  mechanism). Run the same 21-offset timing-luck check on S2 (monthly) and S1
  (weekly, 5 offsets) so every paper sleeve's expectation is date-neutral;
  queue task T-20260928-01.
