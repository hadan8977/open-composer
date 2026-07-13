# Backtest Forensics: us_mom_minute_p1_003_frozen_ml_diagnostics

Conclusion: `warning`. The eight-trial ML round is a valid negative development
experiment, not successful ML Alpha.

- Lookahead: `pass`; all six features are shifted to index-minus-one and labels
  start from the next aligned TQQQ execution open.
- Future leak: `pass` in the corrected run; training is chronological and uses
  episode-end purge plus a 13-bar embargo.
- Multiple testing: eight fixed Logistic/LightGBM trials, all in the ledger.
- Selection: neither family passes the full pre-holdout contract. The reserved
  holdout is not evaluated by the corrected run.
- Historical deviation: an earlier implementation opened the holdout after only
  one fold win. Those results are explicitly invalidated and cannot be reused.
- Data: Alpaca IEX remains research-only evidence.

Decision: keep the frozen rule champion. The two hashed models may collect new
forward diagnostic observations but cannot control orders or claim research pass.
