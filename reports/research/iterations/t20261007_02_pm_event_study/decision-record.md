# Decision Record: t20261007_02_pm_event_study

## P1

- Path: pm_odds_event_study (R scheduled releases via Kalshi, J odds jumps via Polymarket); decided 2026-10-07 after the frozen run, rules unchanged since the pre-backtest stamp.
- Decision: stop for both parts as trading rules (does not hold at tradable size). No P1, no paper sleeve, no orders. Direction `prediction_market_*` stays as: odds carry news, ETFs price it inside the odds window.
- Reason: R selected net Sharpe -0.75, placebo 0.42, DSR 0.00, robustness 1 of 6, gross about zero against 7.4 bp cost; positive control with the realised surprise passes (t 4.35), so the test could see a reaction. J selected net Sharpe -0.97, placebo 0.58, DSR 0.00, robustness 1 of 6, gross +0.5 to +1.4 bp against 3.7 bp cost; the mapped ETF already moved +6.3 bp (t 6.1) in the hour before the odds point (descriptive). Power adequate for the economically relevant size (R MDE 10.6-20.6 bp, J 1.3-6.9 bp net per trade). Evidence: results.json, report.md, j_contemporaneous_diag.json.
- Next iteration suggestion: do not reopen R. Open J only with minute or trade-level odds timing (who moves first) or as forward shadow logging of tariff de-escalation continuation (gross about +6 bp, n 151, report-only lead). V4 crash diagnostic and live-feed consistency were not run (no tier in question); required before any future tier. ML/AI-information entry conditions: not met.
