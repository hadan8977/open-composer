# Momentum Strategy-Specific ML Comparison

- Status: `holdout_not_opened_keep_rule_champion`
- Research pass: `False`
- Execution behavior changed: `False`

| Trial | Family | Validation Return % | Episode Sharpe | AUC | Fold wins |
|---|---|---:|---:|---:|---:|
| logistic_c0.1_t0.5 | regularized_logistic | -8.6894 | -1.6048 | 0.430909 | 1/3 |
| logistic_c0.1_t0.6 | regularized_logistic | -9.1607 | -1.7087 | 0.430909 | 1/3 |
| logistic_c1_t0.5 | regularized_logistic | -9.1607 | -1.7087 | 0.355152 | 1/3 |
| logistic_c1_t0.6 | regularized_logistic | -9.1607 | -1.7087 | 0.355152 | 1/3 |
| lightgbm_l7_t0.5 | lightgbm_challenger | 7.5923 | 0.8036 | 0.493636 | 1/3 |
| lightgbm_l7_t0.6 | lightgbm_challenger | -0.3398 | -0.2081 | 0.493636 | 1/3 |
| lightgbm_l15_t0.5 | lightgbm_challenger | 7.5923 | 0.8036 | 0.493636 | 1/3 |
| lightgbm_l15_t0.6 | lightgbm_challenger | -0.3398 | -0.2081 | 0.493636 | 1/3 |

## ML-Family Holdout


No model is connected to execution, target weights, Paper, or broker writes.
