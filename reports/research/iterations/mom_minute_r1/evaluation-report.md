# mom_minute_r1 Evaluation

- Generated at: `2026-07-10T10:54:16.310908+00:00`
- Trial count: `28`
- Workflow pass: `True`
- Research pass: `False`
- Paper-ready pass: `False`
- Acceptance passed: `False`
- Failed gates: at_least_one_path_continue

## Path Summary

| path | decision | trials | best trial | entries | total % | sharpe | max DD % | flags |
|---|---|---:|---|---:|---:|---:|---:|---|
| `P1_time_series_etf_momentum` | `pivot` | 16 | `mom_minute_r1_p1_008` | 158 | 88.93 | 1.33 | -20.86 | recent_fold_gate_failed |
| `P3_overnight_intraday_decomposition` | `pivot` | 12 | `mom_minute_r1_p3_024` | 138 | 19.03 | 0.83 | -8.41 | recent_fold_gate_failed, benchmark_family_incomplete |

## Top Trials

| rank | trial | path | entries | params | total % | ann % | sharpe | max DD % | x2 total % | flags |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `mom_minute_r1_p1_008` | `P1_time_series_etf_momentum` | 158 | `{"exit_style": "atr_trail", "lookback_bars": 96, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 88.93 | 36.71 | 1.33 | -20.86 | 71.90 | recent_fold_gate_failed |
| 2 | `mom_minute_r1_p1_010` | `P1_time_series_etf_momentum` | 156 | `{"exit_style": "atr_trail", "lookback_bars": 12, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 162.29 | 60.64 | 1.34 | -34.63 | 146.49 | recent_fold_gate_failed, benchmark_family_incomplete |
| 3 | `mom_minute_r1_p1_007` | `P1_time_series_etf_momentum` | 135 | `{"exit_style": "ema_cross", "lookback_bars": 96, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 88.09 | 36.42 | 1.05 | -37.66 | 73.50 | recent_fold_gate_failed |
| 4 | `mom_minute_r1_p1_014` | `P1_time_series_etf_momentum` | 107 | `{"exit_style": "atr_trail", "lookback_bars": 48, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 78.96 | 33.12 | 1.09 | -36.00 | 71.49 | benchmark_family_incomplete |
| 5 | `mom_minute_r1_p1_002` | `P1_time_series_etf_momentum` | 409 | `{"exit_style": "atr_trail", "lookback_bars": 12, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 29.54 | 13.56 | 0.51 | -45.30 | 1.38 | recent_fold_gate_failed |
| 6 | `mom_minute_r1_p1_009` | `P1_time_series_etf_momentum` | 178 | `{"exit_style": "ema_cross", "lookback_bars": 12, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 72.14 | 30.60 | 0.91 | -38.86 | 60.34 | recent_fold_gate_failed, benchmark_family_incomplete |
| 7 | `mom_minute_r1_p1_003` | `P1_time_series_etf_momentum` | 310 | `{"exit_style": "ema_cross", "lookback_bars": 24, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 22.73 | 10.59 | 0.46 | -45.01 | 1.92 | recent_fold_gate_failed |
| 8 | `mom_minute_r1_p1_015` | `P1_time_series_etf_momentum` | 61 | `{"exit_style": "ema_cross", "lookback_bars": 96, "overnight_policy": "hold", "signal_symbol": "QQQ", "traded_symbol": "TQQQ"}` | 67.77 | 28.96 | 0.91 | -38.22 | 63.75 | benchmark_family_incomplete |

## Caveats

- Alpaca/IEX minute bars are research-only evidence, not SIP/full-market paper-ready evidence.
- The benchmark family is diagnostic because SPY/BIL minute coverage was materialized from local research cache only.
- No promotion, paper readiness, or live-trading claim is made from this round.
- This is not a promotion report and does not change active or paper behavior.
- ML and AI-information rounds remain blocked until a non-ML path survives the full gate.
