# H-20260928-02: cross-asset trend sleeve vs delevered S3 control

Batch: `scripts/screen_batches/h20260928_02_cross_asset.py`, run via
`scripts/screen_batch.py --batch h20260928_02_cross_asset --iteration h20260928_02_cross_asset_sleeve`.
Raw leaderboard: `reports/research/screens/h20260928_02_cross_asset/leaderboard.json`
(`.md` alongside). This dossier's `results.json` recomputes the K1/K2 tiers
field by field from that leaderboard plus S3's own offset-median Sharpe
(`reports/research/iterations/h20260928_01_s3_rebalance_tranching/results.json`
`offset_distribution_net10`).

## Verdict

**1/2 kept, 0/2 cleared K2.** D1 (Carlson's Defense First TAA over
TLT/GLD/DBC/UUP) is **kept via K1** (standalone, judged offset-median Sharpe
clears 80% of S3's own median in both windows, 20bp CAGR positive both
windows) but fails K2 (the combination-with-S3 bar). D2 (12-month-vs-SHY
absolute momentum, inverse-63-session-vol sized) is **refuted**: it fails
both K1 (anchor median Sharpe below the 80% bar) and K2 (negative stress
combination edge).

## D1 -- Defense First TAA (Carlson 2025)

| metric | anchor | stress |
|---|---:|---:|
| judged (offset-median) Sharpe, 10bp | 1.4819 | 0.7292 |
| K1 bar (80% of S3's own median: 1.4853 / 0.8059) | 1.1882 | 0.6447 |
| K1 Sharpe check | pass | pass |
| judged CAGR, 10bp | 23.40% | 8.24% |
| judged CAGR, 20bp | 22.80% | 7.68% |
| judged max drawdown, 10bp | -8.69% | -13.19% |
| combination Sharpe edge over vol-matched S3 (K2, bar >=0.05) | +0.575 | **+0.037** |

- **K1: pass** (both Sharpe conditions clear the 80% bar, both windows'
  20bp CAGR positive). **K2: fail** -- the stress-window combination edge
  (+0.037) is below the 0.05 bar even though the anchor-window edge is large
  (+0.575); the K2 rule requires both windows.
- Not "strong": strong-K1 would need the Sharpe not below S3's own in either
  window (anchor 1.4819 is 0.0034 below S3's 1.4853; stress 0.7292 is 0.077
  below S3's 0.8059) -- narrowly short in both. Strong-K2 needs >=0.10 in
  both windows -- stress edge is only +0.037.
- Correlation with S3: stress 0.272, anchor 0.301, 2022 0.189 -- moderate,
  materially lower than S1/S2's 0.48-0.83 range against S3 found in
  H-20260927-01, consistent with the anchor-window combination edge, but
  evidently not low enough (or not offsetting enough of S3's own stress-
  period risk) to clear the harder stress-window K2 bar.
- DSR at anchor (n_trials=2): 0.9675.
- `first_valid_signal_date`: 2017-01-31 (matches H-20260923-12's DF01
  finding for the same momentum blend).

## D2 -- absolute momentum vs SHY, inverse-63-session-vol sized

| metric | anchor | stress |
|---|---:|---:|
| judged (offset-median) Sharpe, 10bp | 1.1294 | 0.2336 |
| K1 bar (80% of S3's own median) | 1.1882 | 0.6447 |
| K1 Sharpe check | **fail** | fail |
| judged CAGR, 10bp | 18.74% | 3.22% |
| judged CAGR, 20bp | 18.01% | 2.63% |
| judged max drawdown, 10bp | -7.26% | -17.02% |
| combination Sharpe edge over vol-matched S3 (K2, bar >=0.05) | +0.637 | **-0.227** |

- **K1: fail** (anchor median Sharpe 1.1294 is below the 1.1882 bar; stress
  0.2336 is far below 0.6447). **K2: fail** (stress combination edge is
  negative -- adding D2 to S3 makes the combination *worse* than a
  vol-matched delevered-S3 control in the stress period).
- Correlation with S3: stress 0.052, anchor 0.035, 2022 0.038 -- very low,
  essentially decorrelated. This rules out "too correlated with S3" as the
  failure mode (unlike H-20260927-01's S1/S2); D2's problem is a *return*
  problem, not a correlation problem -- its own standalone Sharpe (0.23 in
  stress) is simply too weak for even near-zero correlation to lift the
  combination's stress-period Sharpe above the delevered-S3 control.
- DSR at anchor (n_trials=2): 0.9048.
- The 2026 holdout Sharpe (1.90, contaminated, reference only) is far above
  the anchor/stress readings -- a reminder that D2's apparent 2026 strength
  does not generalize to the stress period and is not evidence for
  either tier.

## Reading against H-20260927-01 and H-20260923-12

- H-20260927-01 found S1/S2 too correlated with S3 (0.79-0.83 in stress) to
  clear K2. D1 and D2 are both far less correlated with S3 (0.05-0.30 range
  across all three reported windows) -- confirming that a defensive
  four-asset basket genuinely diversifies S3's daily return stream better
  than S1/S2 did. That lower correlation shows up clearly in the anchor-
  window combination edge for both D1 (+0.575) and D2 (+0.637) -- but
  neither converts it into a stress-period edge >=0.05: D1's stress edge is
  a thin +0.037, D2's is negative. The anchor window (2024-2026, mostly a
  calm bull market) is not a hard enough test; the stress period
  (2016-05..2023-09, including 2018Q4, 2020 and 2022) is, and it is the one
  K2 requires both windows to clear.
- H-20260923-12 tested Defense First as a *sub-allocation of S3's own idle
  cash* and found it did not beat +0.10 Sharpe over plain SHY. This round
  asked a different, harder question (combination with the full S3 sleeve,
  K2 bar >=0.05) and D1 still fails it -- consistent, not contradictory: a
  rule that cannot even beat plain SHY as a cash sub-allocation (prior
  finding) should not be expected to add a full-sleeve combination edge in
  the stress period either (this finding). D1's *standalone* result (K1
  pass) is new evidence this round did not have before: Defense First on
  its own, at 10-20bp, is competitive with S3's own risk-adjusted return
  (though not additive to it once combined).

## Next step

Per candidate-manifest.json's `fallback_if_none_pass`-adjacent guidance: D1
is kept (K1) for continued observation/shadow-tracking, not promoted to a
combined-account live pilot (K2 did not pass). D2 is refuted. Do not re-tune
D1/D2's published/round-number parameters or cherry-pick a rebalance offset
to try to close the stress-window K2 gap; reopening this direction needs a
new defensive-asset set, a new published combination rule, or new disclosed
data (per direction-review.json's `stop_condition`).
