# PDR Router ML Gate Evaluation: nasdaq_tqqq_pdr_router_mlgate_iter1

- Verdict: `ml_gate_beats_fixed_route=False`
- Data: `longbridge` / `materialized_history_cache`
- Paper-ready evidence: `False`
- Trial ledger: `/root/codex-test/open-composer/reports/research/ml/nasdaq_tqqq_pdr_router_mlgate_iter1/pdr_mlgate_trial_ledger.jsonl`

## Acceptance

| gate | passed | actual | threshold |
|---|---:|---|---|
| `wf_beats_tqqq_at_least_4_of_6` | `False` | `2.000` | `4.000` |
| `full_window_annualized_return_at_least_33` | `True` | `37.299` | `33.000` |
| `full_window_sharpe_at_least_1_1` | `False` | `0.931` | `1.100` |
| `full_window_maxdd_not_worse_than_baseline` | `False` | `-66.700` | `-43.236` |
| `crisis_windows_all_beat_tqqq` | `True` | `["q4_2018", "covid_crash", "calendar_2022"]` | `["q4_2018", "covid_crash", "calendar_2022"]` |
| `current_oos_sharpe_and_total_gate` | `False` | `{"sharpe_ratio": 1.3948899738322895, "total_return_pct": 142.83763200882618, "tqqq_total_return_pct": 119.5019553715206}` | `{"sharpe_ratio": 1.7, "total_vs_tqqq_multiple": 1.5}` |

## Full Window

| path | total % | ann % | sharpe | max dd % | TQQQ bh % |
|---|---:|---:|---:|---:|---:|
| baseline | 5643.759 | 35.722 | 1.014 | -43.236 | 13862.685 |
| gated | 6594.612 | 37.299 | 0.931 | -66.700 | 13862.685 |

## Walk Forward

| fold | gated total % | TQQQ bh % | beats TQQQ | gated sharpe | gated max dd % |
|---|---:|---:|---:|---:|---:|
| fold1 | 91.357 | 272.965 | `False` | 1.095 | -26.040 |
| fold2 | 43.379 | 92.731 | `False` | 0.611 | -41.137 |
| fold3 | -0.924 | 95.890 | `False` | 0.200 | -46.380 |
| fold4 | 304.823 | 373.592 | `False` | 1.457 | -48.949 |
| fold5 | 93.164 | -25.494 | `True` | 0.839 | -60.824 |
| fold6 | 214.837 | 160.837 | `True` | 1.308 | -50.027 |

## Attribution

- ML release days: `374`
- Non-hard-stress state/weight changes: `0`
- ML release net delta arithmetic pp: `62.722`

## Pass Status

- workflow_pass: `True`
- research_pass: `False`
- llm_contribution_pass: `False`
- paper_ready_pass: `False`
