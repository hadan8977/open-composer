# Decision Record: h20260928_02_cross_asset_sleeve

## P1

- Path: cross_asset_sleeve_vs_delevered_s3_control (D1, D2)
- Decision: pivot (D1 kept for shadow-tracking, not promoted; D2 stop)
- Reason: Per results.json's `adoption` block, checked against
  candidate-manifest.json's adoption_rule: D1 (Defense First TAA) clears K1
  (standalone judged offset-median 10bp Sharpe 1.4819 anchor / 0.7292 stress,
  both above the 80%-of-S3 bars 1.1882 / 0.6447, and 20bp CAGR positive in
  both windows: +22.80% anchor, +7.68% stress) but fails K2 (combination
  Sharpe edge over vol-matched S3 is +0.575 anchor but only +0.037 stress,
  below the 0.05 bar required in both windows). D2 (absolute momentum vs
  SHY, inverse-63-session-vol sized) fails both K1 (anchor median Sharpe
  1.1294 < 1.1882 bar) and K2 (stress combination edge is negative,
  -0.227). Neither reaches strong-kept. Both are far less correlated with
  S3 (0.03-0.30 across stress/anchor/2022) than S1/S2 were in
  H-20260927-01 (0.79-0.83) -- the lower correlation shows clearly in the
  anchor-window combination edge for both candidates, but the stress
  period (2016-05..2023-09, the harder test K2 requires both windows to
  pass) still does not convert that decorrelation into a durable
  combination edge for either sleeve.
- Next iteration suggestion: do not build a combined-account live pilot on
  this evidence (K2 failed for both). D1 alone is preregistered as kept
  (K1) and can be added to `reports/research/screens/kept.jsonl` for
  forward shadow-tracking (T-20260928-07's mechanism), since it is
  standalone-competitive with S3 even though it does not add combination
  value. If a future round wants to revisit the combination question, it
  should look for a sleeve whose stress-period combination edge (not just
  anchor-window edge or standalone Sharpe) clears +0.05 -- correlation
  with S3 is evidently not the binding constraint for either D1 or D2, so
  a lower-correlation basket alone is not sufficient; the specific driver
  of the stress-period shortfall (D1: fallback reintroducing equity beta
  during drawdowns; D2: weak standalone stress Sharpe) should inform the
  next candidate's design.
