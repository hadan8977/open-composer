# Decision Record: t20261006_15_intraday_rules

## P1 intraday_rules_scale_curve

- Path: intraday_rules_scale_curve (groups A noise band, B market intraday momentum; C and D pending)
- Decision: pivot (A = not at depth, QQQ shadow candidate only (P1 not met, DSR 0.17); B = stop, not holding (published-size effect absent out of sample); C, D = continue, pending, due 2026-10-12)
- Reason: A reproduces the paper's relative conclusions on SPY (0.76/1.11 vs 1.24/1.33) and the old 0.30 was a different rule (every-minute checks); the recent edge sits in QQQ only, DSR 0.17 after counting 98 main points and 3,825 robustness versions, power at 689 sessions is 1.50 Sharpe. B: SPY 2016-2022 R2 0.0008 vs 1.6 percent in the paper, gross edge zero recently. See report.md.
- Next iteration suggestion: forward shadow on QQQ (cap 1), SIP NBBO sampling for ETF spreads, C after the 5-minute panel, D 1-minute and long-short hourly; recompute DSR with C and D included.
