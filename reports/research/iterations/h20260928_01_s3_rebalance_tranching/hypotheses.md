# Hypotheses: h20260928_01_s3_rebalance_tranching

## H-20260928-01 (T4 four-tranche S3)

- Hypothesis: splitting S3 into four tranches that signal 0, 5, 10 and 15 sessions after month
  end gives a shallower max drawdown than the live month-end rule in both the anchor and the
  2016-2023 stress window, gives up at most 0.05 Sharpe in each, and still clears G1 or G1' at
  10 and 20 bp in the anchor window.
- Failure mode: month-end is a lucky date for S3 in one of the windows, or the slower reaction
  of a tranched book (only a quarter switches to SHY at each date) deepens a fast crash.
- Measurement: adoption conditions (a)-(d) in candidate-manifest.json, computed by
  scripts/run_h20260928_01_s3_rebalance_tranching.py into results.json.
- Stop/Pivot criterion: if any condition fails, keep month-end execution; no offset is adopted.

## Descriptive (not a hypothesis test)

- Where O00 sits among the 21 offsets for CAGR, Sharpe and max drawdown per window, and the
  best-worst CAGR spread (S3's own rebalance timing luck).
