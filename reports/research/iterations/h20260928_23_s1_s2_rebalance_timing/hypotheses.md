# Hypotheses: h20260928_23_s1_s2_rebalance_timing

## Descriptive measurement (not a pass/fail hypothesis test)

- Hypothesis: S2's live single-date rebalance rule, like S3's (H-20260928-01), sits near the
  best of its own offset distribution in the windows that were used to write its headline numbers,
  so part of the headline is rebalance-date luck rather than the ranking rule.
- Failure mode: none in the pass/fail sense -- this is descriptive. The result could instead show
  the live date sitting near the median, which would mean S2's numbers carry little date luck.
- Measurement: for each of 21 signal-date offsets covering one month (O00 = live rule),
  compute CAGR, Sharpe-ex-BIL and max drawdown per window (stress/select/anchor/holdout-2026), then
  report min/median/max across offsets and O00's rank, via
  `scripts/run_h20260928_23_s1_s2_rebalance_timing.py` into `results.json`.
- Stop/Pivot criterion: not applicable -- no offset is adopted regardless of where O00 ranks; the
  live rule is frozen. If the live rank is top 3 of 21 AND the median Sharpe is more than
  20% below O00's, report.md states this explicitly as a "date-neutral expectation" per the queue's
  highlight rule (T-20260928-01).
