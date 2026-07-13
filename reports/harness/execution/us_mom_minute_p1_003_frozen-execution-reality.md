# Execution Reality: us_mom_minute_p1_003_frozen

Status: `blocked` for paper orders; observation-only code is available.

- 09:30 intents must eventually compare MOO/OPG with LOO/OPG. Alpaca documents
  that OPG orders are auction-only, unfilled orders cancel after the open, and
  the same-opening cutoff is 09:28 ET.
- Intraday 30m intents must compare a marketable limit with a passive limit plus
  timeout/cancel path.
- Paper simulation cannot certify market impact, latency slippage, or queue
  position. IEX-only evidence remains research-only.
- Slippage stress is fixed at 3/6/12/20 bps.
- Historical absolute overnight gaps are P50 1.07%, P90 3.55%, P95 4.59%, P99
  9.90%. A -48.47% observation is a data-quality blocker, not a production risk
  estimate.
- Capacity remains blocked until account notional, intended shares, arrival
  volume, opening-window volume, and 20-day median ADV are recorded. The initial
  participation cap is 1% of conservative volume.

No order style is authorized by this report.
