# Hypotheses: h20260928_02_cross_asset_sleeve

Question: does adding one cross-asset defensive-trend sleeve (D1 Defense First,
D2 absolute-momentum/inverse-vol) to S3, combined by trailing-63-session
inverse-volatility monthly weighting, beat delevering S3 alone to the same
realized volatility on Sharpe, in both the anchor and stress windows, without
cherry-picking a rebalance-day offset?

## H1 (D1 Defense First TAA)

- Hypothesis: Carlson's published Defense First rotation over TLT/GLD/DBC/UUP
  (rank by 1/3/6/12-month blended momentum, weight 40/30/20/10, redirect any
  tier below BIL's momentum to SPY), combined with S3 by trailing-63-session
  inverse volatility, beats its vol-matched delevered-S3 control by >=0.05
  Sharpe (K2) in both the anchor and stress windows, because bonds/gold/
  commodities/dollar are a mechanistically different basket from S3's
  leveraged-tech/semis book and should be less correlated with it than S1/S2
  were (H-20260927-01 found S1/S2 too correlated with S3, 0.79-0.83).
- Failure mode: Defense First's own fallback (SPY) reintroduces equity beta
  exactly when the hurdle screen fails (typically a drawdown, when SPY itself
  is falling), which could raise D1's correlation with S3 in the stress
  period specifically and erase the diversification benefit the K2 test
  requires.
- Measurement: candidate-manifest.json adoption_rule K1/K2 conditions for D1,
  computed by scripts/screen_batch.py via scripts/screen_batches/h20260928_02_cross_asset.py;
  reported in leaderboard.json/leaderboard.md and this dossier's results.json/report.md.
- Stop/Pivot criterion: if H1 fails K2, check whether it still clears K1
  standalone and whether the SPY-fallback correlation-with-S3 diagnostic
  (stress/anchor/2022) explains the failure; if it does, a future round
  could preregister a SHY-fallback variant instead (distinguishing this from
  H-20260923-12's DF02, which tested that fallback only as an S3
  sub-allocation, not as an independent combined sleeve).

## H2 (D2 absolute momentum vs SHY, inverse-vol sized)

- Hypothesis: Holding TLT/GLD/DBC/UUP only when trailing-12-month return beats
  SHY's, sized by inverse 63-session volatility (otherwise 100% SHY),
  combined with S3 the same way as D1, beats its own vol-matched control by
  >=0.05 Sharpe (K2) in both windows, because the strict SHY-only fallback
  (no equity beta reintroduced) should keep D2 less correlated with S3 in
  drawdowns than D1's SPY-fallback variant.
- Failure mode: with no rank-based diversification requirement (D2 can go to
  0, 1, 2, 3 or 4 names, or all-SHY), D2's exposure can concentrate in a
  single asset or sit fully in cash for long stretches, reducing its own
  standalone Sharpe and diluting the combination's ability to add
  risk-adjusted return even if correlation with S3 is low.
- Measurement: same K1/K2 conditions for D2, computed by the same batch run.
- Stop/Pivot criterion: if H2 also fails, and H1's failure was specifically a
  correlation problem (not a return problem), the joint conclusion is that
  this four-asset defensive basket (regardless of the exact rank/threshold
  rule) does not diversify S3 enough to clear the combination bar, and a
  future round should look for a sleeve with a fundamentally different risk
  driver (e.g. short-vol, market-neutral, or a truly uncorrelated factor)
  rather than re-testing more defensive-asset trend variants.
