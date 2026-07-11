# Backtest Forensics: us_minute_momentum_r2

Conclusion: `warning`. The methodology-corrected round is usable research
evidence, not promotion, ML, or paper evidence.

- Lookahead: `pass`; close-derived features are applied from the next TQQQ bar
  open to the following bar open.
- Future leak: `pass`; the split is chronological, selection uses development
  and validation only, and the lockbox is opened once for one selected trial.
- Multiple testing: nine fixed combinations, all recorded in the trial ledger.
- Sample adequacy: `short_sample=true`; the lockbox has 102 trading sessions and
  173 entries. It does not provide a full-year independent regime sample.
- Data: Alpaca IEX is research-only and not consolidated SIP/full-market evidence.
- Benchmark interpretation: the candidate passed the registered `beats naive or
  QQQ` disjunct by beating QQQ, but it underperformed naive momentum and TQQQ
  buy-and-hold. This is a material limitation, not a promotion success.
- Capacity: personal-size research only; next-open TQQQ spread, gap, ADV, and
  fill behavior still require execution-reality review.

Decision: continue only with frozen parameters and new OOS/forward evidence.
Do not optimize against this lockbox and do not start ML to rescue benchmark
underperformance.

