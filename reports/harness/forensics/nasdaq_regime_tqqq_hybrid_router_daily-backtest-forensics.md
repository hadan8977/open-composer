# Backtest Forensics: nasdaq_regime_tqqq_hybrid_router_daily

- Conclusion: `warning`
- Lookahead check: `pass`
- Future leak check: `pass`
- Overfit risk: `medium`
- Multiple-testing count: `32`
- Trading days / round trips: `1362/1269`
- OOS annualized / Sharpe: `16.00% / 1.28`
- OOS alpha vs TQQQ: `11.78%`

## Findings

- Lookahead: pass. Route selection uses prior confirmed close and applies target weights at the next regular-session open.
- Future leak: pass. Train/OOS split and walk-forward folds are chronological.
- Overfit: medium. The selected route was chosen from 32 candidates, and 3/5 walk-forward folds were positive; warnings remain because factor diagnostics and best-symbol comparison are weak.
- Data: strict-live Alpaca IEX daily bars were refreshed for 2020-07-27 through 2026-05-21, but IEX is not consolidated SIP.
- Capacity: target weights cap gross and single-name exposure at 25%; paper_auto still needs account-specific TCA and whole-share LOO sizing.

## Decision

Research pass is acceptable for observation/manual-signal simulation. Do not activate paper_auto until promotion readiness, account snapshot, explicit user approval, and paper safety review pass.
