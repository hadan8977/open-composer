# Hypotheses: h20260929_12_hedged_factor_ensemble

## H1: Hedging a correlated long-only factor ensemble with a real inverse ETF can decorrelate it from S3 enough to add Sharpe

- Hypothesis: every long-only stock candidate tried so far in this registry is
  correlated 0.5-0.8 with S3 and none add Sharpe when combined with it
  (dir:equity_momentum_concentrated_pwb, dir:factor_style_etf_momentum_rotation).
  A prior SPY-beta-neutral hedge attempt (dir:baseline_chain_b0_b1_b2_market_neutral_vs_long)
  was a systematic drag, not a fix, at weekly rebalance. This task tests
  whether a materially different hedge construction -- actual long SH/PSQ
  shares, capped partial-beta sizing (beta/(1+beta), not full beta-neutral),
  monthly rebalance -- can achieve correlation with S3 < 0.3 while keeping
  standalone Sharpe positive, which would let it add Sharpe to the S3
  combination via screen_lane's diversifier-edge test.
- Source support: dir:ml_ranking_liquid500_recent_vs_momentum_rule and
  dir:baseline_chain_b0_b1_b2_market_neutral_vs_long (registry rows, read in
  full); AlphaAgent and R&D-Agent(Q) (already-verified papers establishing a
  real but small post-2023 US factor-ensemble IC); ProShares' own inverse-ETF
  decay/tactical-use guidance (this task's new source).
- Failure mode: the hedge either (a) does not reduce correlation with S3
  below 0.3 (the ensemble and S3 both key off momentum/quality factors that
  move with the broad market in the same phases), or (b) reduces correlation
  but the SH/PSQ decay plus the ensemble's own weak standalone alpha leaves
  standalone Sharpe <= 0, so there is nothing left to diversify with.
- Measurement: screen_lane.diversifier_edge_for_offset (combined S3+candidate
  Sharpe, inverse-vol weighted, vs a vol-matched k*S3+(1-k)*SHY control),
  median over rebalance offsets {0,5,10,15}, in 2024-01-02..2026-09-08.
- Benchmark family: S3 vol-matched control (primary judged benchmark);
  SHY cash proxy; the long-only form (a) of the same ensemble (does hedging
  help vs not hedging); across-ensemble comparison (E10/E20/E40/E20D/R40).
- Stop/Pivot criterion: if no hedged form (b/bp) clears edge >= +0.05,
  standalone Sharpe > 0 and correlation with S3 < 0.3 in Stage 1, the
  direction is refuted for this scope and Stage 2 (2018-2023 walk-forward
  re-selection) is not run. If Stage 1 passes, Stage 2 must also clear
  edge >= +0.05 in 2018-01-02..2023-09-15 before any forward shadow is
  proposed (none is created by this iteration regardless of outcome).

## H2 (info only, not gating): a long/short top-decile-minus-bottom-decile spread of the same ensembles would show more standalone alpha than the long-only or hedged forms

- Hypothesis: form (c)'s spread isolates the ensemble's actual cross-sectional
  ranking skill without market beta contamination, so it should show the
  cleanest standalone Sharpe of the four forms if the ensemble has real
  alpha -- but it cannot be adopted (no short-selling authorization for this
  account) and borrow costs are not modeled, so it is reported for
  diagnostic value only, never as a decision candidate.
- Failure mode: n/a (not gating).
- Measurement: same offset/cost convention as (a)/(b)/(bp), both legs
  costed, borrow costs explicitly flagged as unmodeled in the report.
- Stop/Pivot criterion: n/a (informational row only).
