# Research Memory: audit_rsi_reversion_daily
- Objective: RSI(2) < 10 entry, > 70 exit for backtest correctness audit.
- Data tier: sample_smoke
- Next: run a bounded parameter sweep only after defining a small search space; treat overfit, sample, and promotion warnings as diagnostics during exploration
- Control: use evidence first, change <=2 variables, no global factor bans, warn not hard-block early diagnostics.
