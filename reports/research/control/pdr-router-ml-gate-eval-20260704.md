# PDR Router ML Gate Evaluation: nasdaq_tqqq_pdr_router_mlgate_iter2

- Verdict: `ml_gate_beats_fixed_route=False`
- Data: `longbridge` / `materialized_history_cache`
- Paper-ready evidence: `False`
- Trial ledger: `/root/codex-test/open-composer/reports/research/ml/nasdaq_tqqq_pdr_router_mlgate_iter2/pdr_mlgate_trial_ledger.jsonl`

## Acceptance

| gate | passed | actual | threshold |
|---|---:|---|---|
| `wf_beats_tqqq_at_least_4_of_6` | `False` | `1.000` | `4.000` |
| `full_window_annualized_return_at_least_33` | `True` | `38.538` | `33.000` |
| `full_window_sharpe_at_least_1_1` | `False` | `0.982` | `1.100` |
| `full_window_maxdd_not_worse_than_baseline` | `False` | `-47.612` | `-43.236` |
| `crisis_windows_not_worse_than_baseline` | `False` | `[{"gated_beats_tqqq": true, "max_drawdown_pct": {"baseline": -21.185401345902356, "floor": -23.185401345902356, "gated": -42.78112947712485, "passed": false}, "name": "q4_2018", "passed": false, "total_return_pct": {"baseline": -16.013475335393867, "floor": -18.013475335393867, "gated": -35.37852539808731, "passed": false}, "tqqq_buy_hold_return_pct": -50.0}, {"gated_beats_tqqq": true, "max_drawdown_pct": {"baseline": -16.355835498634985, "floor": -18.355835498634985, "gated": -33.49797106264113, "passed": false}, "name": "covid_crash", "passed": false, "total_return_pct": {"baseline": -13.132635417240103, "floor": -15.132635417240103, "gated": -28.50785796267157, "passed": false}, "tqqq_buy_hold_return_pct": -69.60178263369752}, {"gated_beats_tqqq": true, "max_drawdown_pct": {"baseline": -21.25871167950788, "floor": -23.25871167950788, "gated": -30.688397451491667, "passed": false}, "name": "calendar_2022", "passed": false, "total_return_pct": {"baseline": -8.76361220569235, "floor": -10.76361220569235, "gated": -15.35678541652057, "passed": false}, "tqqq_buy_hold_return_pct": -79.27058058383571}]` | `{"also_requires_gated_beats_tqqq": true, "baseline_tolerance_pct_points": 2.0}` |
| `current_oos_sharpe_and_total_gate` | `False` | `{"sharpe_ratio": 1.216218868772607, "total_return_pct": 94.92573080599544, "tqqq_total_return_pct": 119.5019553715206}` | `{"sharpe_ratio": 1.7, "total_vs_tqqq_multiple": 1.5}` |

## Full Window

| path | total % | ann % | sharpe | max dd % | TQQQ bh % |
|---|---:|---:|---:|---:|---:|
| baseline | 5643.759 | 35.722 | 1.014 | -43.236 | 13862.685 |
| gated | 7441.822 | 38.538 | 0.982 | -47.612 | 13862.685 |

## Walk Forward

| fold | gated total % | TQQQ bh % | beats TQQQ | gated sharpe | gated max dd % |
|---|---:|---:|---:|---:|---:|
| fold1 | 91.357 | 272.965 | `False` | 1.095 | -26.040 |
| fold2 | 43.617 | 92.731 | `False` | 0.607 | -39.213 |
| fold3 | 15.573 | 95.890 | `False` | 0.370 | -45.215 |
| fold4 | 301.471 | 373.592 | `False` | 1.505 | -33.498 |
| fold5 | 185.741 | -25.494 | `True` | 1.335 | -38.368 |
| fold6 | 106.916 | 160.837 | `False` | 0.963 | -45.314 |

## Crisis Windows

| window | baseline total % | gated total % | baseline max dd % | gated max dd % | beats TQQQ |
|---|---:|---:|---:|---:|---:|
| q4_2018 | -16.013 | -35.379 | -21.185 | -42.781 | `True` |
| covid_crash | -13.133 | -28.508 | -16.356 | -33.498 | `True` |
| calendar_2022 | -8.764 | -15.357 | -21.259 | -30.688 | `True` |

## Current OOS

| path | total % | sharpe | max dd % | TQQQ bh % |
|---|---:|---:|---:|---:|
| baseline | 189.000 | 1.903 | -32.643 | 119.502 |
| gated | 94.926 | 1.216 | -40.909 | 119.502 |

## Attribution

- ML release days: `336`
- Non-hard-stress state/weight changes: `0`
- ML release net delta arithmetic pp: `59.546`

## Pass Status

- workflow_pass: `True`
- research_pass: `False`
- llm_contribution_pass: `False`
- paper_ready_pass: `False`
