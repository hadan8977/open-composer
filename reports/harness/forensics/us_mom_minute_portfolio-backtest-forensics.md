# Backtest Forensics: us_mom_minute_portfolio

Conclusion: `warning`. The six-sleeve portfolio is ready to collect isolated
forward virtual observations, but historical comparisons do not prove a new
champion.

- Lookahead: `pass`; current targets use the latest raw aligned QQQ/TQQQ bar,
  while historical return evaluation uses a separate next-open frame.
- Selection bias: `warning`; R1-R3 were introduced after the 102-session window
  was visible, and M1-M2 failed their ML validation gate.
- Forward evidence: zero completed fresh sessions. The local cache ends on
  `2026-05-29`, so stale cycles do not change equity or enter valid ledgers.
- Virtual accounting: each sleeve has an isolated definition-bound epoch. The
  first fresh observation is a zero-return anchor; subsequent observations use
  incremental per-bar positions, returns, turnover, and costs.
- Broker safety: no Alpaca orders are authorized. Six independent TQQQ sleeves
  must not share one broker position owner.

Decision: collect new forward data without retuning. Do not promote historical
R1-R3 results or failed-model diagnostics as independent Alpha.
