# Hypotheses: h20260929_01_letf_flow_reversal

Source: Lenkey (2024, AIMSPress Quantitative Finance and Economics survey,
open access) -- see `direction-review.json`/`external-brief.json` for the
full citation and reflection.

## H1

- Hypothesis: A large one-day close-to-close DOWN move in SPY/QQQ/SMH forces
  same-day leveraged-ETF close-rebalancing that buys the underlying near the
  close; buying the underlying at the next session's open and holding 1 or 3
  trading days captures a next-day mean-reversion edge, i.e. at least one of
  the 12 primary `LETF_{TICKER}_D{2,3}_H{1,3}` candidates clears K1 or K2
  against S3 in both the anchor and stress windows.
- Failure mode: Lenkey (2024)'s own synthesis reads the class-level economic
  magnitude as small despite statistically-significant individual-paper
  associations; this project's prior batch-screening rounds (opex_week,
  dip_reversion) show published flow/reversal mechanisms repeatedly failing
  the 10bp/20bp next-open-fill K1/K2 contract even where the academic
  mechanism is judged real.
- Measurement: `scripts/screen_batch.py --batch h20260929_01_letf_flow_reversal
  --iteration h20260929_01_letf_flow_reversal`, judged Sharpe (10bp) and 20bp
  CAGR in the frozen anchor (2024-01-08..2026-09-17) and stress
  (2016-05-02..2023-09-15) windows, against S3's own reference (anchor
  1.4853, stress 0.8059).
- Stop/Pivot criterion: per `candidate-manifest.json`'s `keep_rule` -- K1
  (>=80% of S3 both windows, positive 20bp CAGR both windows) or K2 (>=0.05
  Sharpe edge vs a vol-matched S3 control, both windows). If none of the 12
  primary candidates clears either, or every apparent pass is beaten by its
  own same-ticker RAND placebo, stop: refute
  `dir:letf_close_rebalancing_flow_reversal` for this scope.

## H2

- Hypothesis: The drop-conditioned entry (real trigger days) is
  mechanistically distinct from an arbitrary entry day of the same
  frequency -- i.e. a `LETF_{TICKER}_D2_H1` candidate's anchor-window Sharpe
  exceeds its own same-ticker `LETF_{TICKER}_RAND` placebo's anchor Sharpe.
- Failure mode: the apparent edge (if any) is actually generic "being long
  the underlying after any single-day move of typical size," not a
  rebalancing-flow-specific timing effect -- indistinguishable from a
  frequency-matched random entry.
- Measurement: same batch run; compare each `LETF_{TICKER}_D2_H1` candidate's
  anchor-window judged Sharpe against its own `LETF_{TICKER}_RAND` placebo's
  anchor-window judged Sharpe.
- Stop/Pivot criterion: per `candidate-manifest.json`'s
  `placebo_internal_falsification` rule -- if the RAND placebo's anchor
  Sharpe is >= the primary candidate's own anchor Sharpe, demote that
  primary candidate to "not kept (placebo replication)" regardless of K1/K2.
