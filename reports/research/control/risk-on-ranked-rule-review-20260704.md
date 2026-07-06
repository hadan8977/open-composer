# PDR risk_on_ranked Rule Review

- Strategy: `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive`
- Route: `defensive_overlay:transition_TQQQ_replacement_mom_positive_lb20_min0_delay30_base[pdr:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10]`
- risk_on_ranked days: `906`
- Decision: `evidence_insufficient`
- Variant: `tie_bias_TQQQ_eps2`
- Rationale: same-day substitution found some lift, but it did not meet the fold2/fold3 and no-broad-degradation threshold for route replay

## Same-Day Substitution

| window | variant | days | arithmetic delta pp | segment compound delta pp |
| --- | --- | ---: | ---: | ---: |
| full_window | fixed_TQQQ | 906 | -42.978 | -44.135 |
| full_window | fixed_QLD | 906 | -98.168 | -101.441 |
| full_window | fixed_QQQ | 906 | -149.744 | -154.308 |
| full_window | smooth_k3 | 906 | 6.472 | 9.270 |
| full_window | smooth_k5 | 906 | -2.306 | -0.452 |
| full_window | tie_bias_TQQQ_eps2 | 906 | 8.989 | 10.224 |
| fold1 | fixed_TQQQ | 198 | -4.056 | -4.273 |
| fold1 | fixed_QLD | 198 | -9.008 | -8.500 |
| fold1 | fixed_QQQ | 198 | -13.294 | -12.343 |
| fold1 | smooth_k3 | 198 | 1.589 | 1.727 |
| fold1 | smooth_k5 | 198 | 3.866 | 3.957 |
| fold1 | tie_bias_TQQQ_eps2 | 198 | 0.308 | 0.310 |
| fold2 | fixed_TQQQ | 155 | 13.633 | 15.296 |
| fold2 | fixed_QLD | 155 | 8.164 | 9.490 |
| fold2 | fixed_QQQ | 155 | 2.728 | 3.793 |
| fold2 | smooth_k3 | 155 | -9.051 | -8.720 |
| fold2 | smooth_k5 | 155 | -1.353 | -1.116 |
| fold2 | tie_bias_TQQQ_eps2 | 155 | 0.590 | 0.551 |
| fold3 | fixed_TQQQ | 119 | 22.089 | 22.961 |
| fold3 | fixed_QLD | 119 | 25.016 | 25.937 |
| fold3 | fixed_QQQ | 119 | 28.975 | 29.949 |
| fold3 | smooth_k3 | 119 | 10.135 | 10.435 |
| fold3 | smooth_k5 | 119 | 11.720 | 12.225 |
| fold3 | tie_bias_TQQQ_eps2 | 119 | 2.801 | 2.887 |
| fold4 | fixed_TQQQ | 203 | 6.417 | 11.952 |
| fold4 | fixed_QLD | 203 | -15.890 | -12.664 |
| fold4 | fixed_QQQ | 203 | -36.998 | -35.125 |
| fold4 | smooth_k3 | 203 | 3.145 | 3.285 |
| fold4 | smooth_k5 | 203 | -14.336 | -14.485 |
| fold4 | tie_bias_TQQQ_eps2 | 203 | 6.960 | 8.380 |
| fold5 | fixed_TQQQ | 111 | -30.120 | -37.233 |
| fold5 | fixed_QLD | 111 | -47.528 | -55.552 |
| fold5 | fixed_QQQ | 111 | -64.674 | -73.248 |
| fold5 | smooth_k3 | 111 | 3.681 | 5.842 |
| fold5 | smooth_k5 | 111 | 4.632 | 6.552 |
| fold5 | tie_bias_TQQQ_eps2 | 111 | -1.669 | -1.904 |
| fold6 | fixed_TQQQ | 120 | -50.942 | -52.838 |
| fold6 | fixed_QLD | 120 | -58.922 | -60.152 |
| fold6 | fixed_QQQ | 120 | -66.482 | -67.335 |
| fold6 | smooth_k3 | 120 | -3.026 | -3.300 |
| fold6 | smooth_k5 | 120 | -6.835 | -7.586 |
| fold6 | tie_bias_TQQQ_eps2 | 120 | 0.000 | 0.000 |

## Full Route Replays

| variant | total delta pp | baseline % | variant % | baseline max dd % | variant max dd % |
| --- | ---: | ---: | ---: | ---: | ---: |
| none | n/a | n/a | n/a | n/a | n/a |

## Boundaries

- This review did not modify any StrategySpec.
- This review did not modify `post_drawdown_reentry_router.py` behavior.
- Full route replay, if present, is validation of at most two variants, not search.
