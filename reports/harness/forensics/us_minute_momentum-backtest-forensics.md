# Backtest Forensics: us_minute_momentum

Conclusion: `warning`, research-only minute momentum round.

Checks:

- Lookahead: pass. Signals are computed from bar-close data and applied to the next bar return.
- Future leak: pass. No fitted model or future-window feature is used.
- Multiple testing: 28 fixed-grid trials, capped at 28.
- Overfit risk: medium. Results require forward paper observation before any promotion.
- Data caveat: Alpaca/IEX minute cache is research-only and not paper-ready full-market evidence.

Path decisions:

- `P1_time_series_etf_momentum`: `pivot` - best candidate had positive return but failed at least one 9.4 gate
- `P3_overnight_intraday_decomposition`: `pivot` - best candidate had positive return but failed at least one 9.4 gate
