# Decision Record: h20260927_01_sleeve_combination

## P1

- Path: sleeve_combination_vs_delevered_control (M0-M3, C1-C3)
- Decision: stop
- Reason: none of M1 (equal-thirds), M2 (half S1 half S3) or M3
  (trailing-63-session inverse-volatility) clears all four preregistered
  adoption-rule conditions in candidate-manifest.json against its paired
  volatility-matched control (results.json `adoption`). All three pass (a)
  and (b) -- they still clear G1/G1' in the anchor window at 10bp and 20bp
  -- and all three pass (d) -- each Mi's stress-period max drawdown is
  slightly shallower than its control's. But all three fail (c): the
  Sharpe edge over the control is positive and >=0.10 in the anchor window
  for M1 (+0.086, just under the bar) and M3 (+0.294), and marginal for M2
  (+0.018), but the stress-period edge collapses to roughly zero or
  negative for every candidate (M1 -0.001, M2 +0.023, M3 -0.047). In the
  stress period (2017-02-01..2023-09-15, common start to just before the
  select window, covering the 2018 and 2022 drawdowns), combining the three
  sleeves earns essentially the same Sharpe as simply delevering S3 alone
  to the same realized volatility -- the diversification benefit shows up
  only in the easier, already-seen anchor window, not in the harder
  historical stress window the control design exists to test. Sleeve
  pairwise correlations (S2/S3 0.83 in stress, 0.79 in anchor; S1/S3 0.48
  in stress, 0.60 in anchor) show S2 and S3 in particular move together
  closely enough that blending them adds little independent risk
  reduction versus just running S3 at lower volatility.
- Next iteration suggestion: do not build a combined-account live pilot on
  this evidence; S3 alone (M0, already the highest-conviction sleeve)
  remains the reference. If a future round wants to revisit combination, it
  should look for sleeves with lower stress-period correlation to S3 than
  S1/S2 have (0.48-0.83 range here), since the failure mode identified is
  correlated drawdowns, not a flaw in the weight rule itself (M3's
  inverse-volatility rule had the largest anchor-window edge of the three,
  suggesting the weight rule is not the binding constraint).
