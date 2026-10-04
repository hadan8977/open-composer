# Decision Record: h20261004_pm_midterm_odds_leadlag

Verdict (mechanical, pending lead review): **stop_refuted**. Numbers come from `results.json` (`H_M`, `continue_rule`, `regressions`, `placebos`) and `report.md`.

## P1

- Path: midterm_control_odds_trump_trades (H-M decision candidate; M-CAT and M-KAL report only)
- Decision: stop: net Sharpe <= 0 on the backtest window; refuted for the midterm setting.
- Reason: net Sharpe -1.20, NW t -1.24, real mean at the 16.7th percentile of 1000 circular shifts (p95 gate False); gross Sharpe -0.91; predictive regression 4.99 bp per pp (t 0.91) against the paper's 13. Window 2025-10-08 to 2026-10-02, 248 sessions.
- Directions source: paper Internet Appendix Table A.1, verbatim (identical to the frozen fallback).
- Caveats: window about 0.984 years, shorter than the 1.4 years assumed in hypotheses.md; power: expected t 0.99 at a true Sharpe of 1.0; no borrow charge on shorts; Republican-control odds stand in for the Trump-win probability.
- Next iteration suggestion: No further midterm-odds variants without a new mechanism; the forward shadow keeps running to 2026-11-04 because it is preregistered, but cannot revive the line alone.
