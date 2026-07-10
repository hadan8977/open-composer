# Search Space: mom_minute_r1

Wave 9.2 feasibility uses isolated Alpaca/IEX minute research materialization at
`reports/research/control/minute-momentum-feasibility-20260710.md` with data
files under `data/research/alpaca_minute/`. The usable coverage is QQQ and TQQQ:
raw 1m cache plus isolated 5m/15m/30m/1h resamples from that 1m cache. This is
research evidence only, not SIP or paper-ready market evidence.

## Path Decisions From Feasibility

- P1 time-series ETF momentum: go on QQQ for `30m` and `1h`; `15m` is also
  available but starts as secondary because costs and churn are higher.
- P2 cross-sectional ETF rotation: no-go in this round because fewer than eight
  ETF symbols have >=18 months of usable minute data in the same timeframe.
- P3 overnight/intraday decomposition: go on QQQ for `30m` and `1h`, with daily
  overnight decomposition explicitly separated from RTH intraday confirmation.

## Candidate Budget

Total budget is `28` combinations, below the Step 9 cap of `80`.

P1 uses `16` combinations:

- timeframe: `30m`, `1h`
- lookback_bars: `12`, `24`, `48`, `96`
- exit_style: `ema_cross`, `atr_trail`

P3 uses `12` combinations:

- timeframe: `30m`, `1h`
- overnight_threshold_pct: `0.0`, `0.5`, `1.0`
- intraday_confirm: `none`, `first_bar_same_sign`
- holding_mode: `same_day_flat`

## Benchmark Family

Each surviving candidate must compare against QQQ buy-and-hold, TQQQ
buy-and-hold, SPY market proxy, BIL cash proxy, and a naive same-timeframe
momentum or overnight/intraday split baseline. Results remain research-only
until strict data and execution evidence are separately upgraded.

## Final Artifact References

- Trial ledger: `reports/research/iterations/mom_minute_r1/trial-ledger.jsonl`
- Evaluation JSON: `reports/research/iterations/mom_minute_r1/evaluation-report.json`
- Evaluation markdown: `reports/research/iterations/mom_minute_r1/evaluation-report.md`
- Backtest forensics: `reports/harness/forensics/us_minute_momentum-backtest-forensics.md`
