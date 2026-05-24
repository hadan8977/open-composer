# Backtest Forensics: nasdaq_long_short_event_router_15m_sweep_001

- Conclusion: `warning`
- Overfit risk: `high`
- Multiple-testing count: `576`
- Estimated research passes in latest run: `4618`
- Latest window: `2025-11-03` to `2026-05-22`
- OOS annualized return: `-27.10%`
- OOS Sharpe: `-1.32`
- OOS equal-weight alpha annualized: `-161.26%`
- Walk-forward positive alpha folds: `2 / 5`

## Findings

- Lookahead: `warning`. The route uses prior closes and confirmed opening bars, then enters the next bar, but this remains a custom intraday router and should be kept under parity review.
- Future leak: `warning`. Chronological train/OOS and walk-forward splits are present, but the selected route changed materially when the validation window expanded.
- Overfit: `high`. The earlier short-window result looked strong, but the longer-window run failed OOS and walk-forward consistency.
- Sample adequacy: `warning`. The latest validation still has fewer than 252 trading days.
- Data: Alpaca IEX is live provider data, but it is not consolidated SIP and has not been cross-checked against a second provider for this research window.
- Capacity: not yet proven. The observation-only target-weight artifact respects exposure caps, but short-sale locate/borrow/dividend/squeeze constraints remain paper blockers.

## Action

Do not promote to paper. The next useful iteration is a more conservative model selection policy: require positive alpha in most walk-forward folds, test a narrower route family around the candidates that do not fail OOS equal-weight alpha, and add cross-source data comparison before any paper-ready claim.
