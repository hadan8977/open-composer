# Backtest Forensics: us_spy_dual_trend_core_r8

- Lookahead: pass; the completed close at `t` first affects the open target at `t+1`.
- Future leakage: pass; no model, event, news, filing, call, or forward feature is used.
- Multiple testing: high risk; primary DSR uses the preregistered global lower bound `N=8002`.
- DSR: `0.075204`, below the `0.95` gate.
- PBO: not identifiable for one fixed R8 candidate; this does not waive cumulative selection risk.
- Sample: 2,522 evaluation sessions and 108 orders with four independent fold liquidations.
- Conclusion: blocked. Historical SIP is exposed robustness evidence and R8D01 must not be tuned or promoted.
