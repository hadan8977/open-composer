# Multi-Asset Momentum ML Comparison

- Run: `20260714T072339Z`
- Dataset rows: `1400`
- Decision dates: `35`
- Lockbox opened: `true`

## Return Ranking

| Trial | Family | Fold wins | Rank IC | Return | Qualified |
|---|---|---:|---:|---:|---|
| rank_elastic_a0005 | elastic_net | 0/4 | 0.063 | -6.70% | false |
| rank_elastic_a005 | elastic_net | 1/4 | 0.081 | 11.30% | false |
| rank_lgbm_l7 | lightgbm | 1/4 | 0.070 | 38.01% | false |
| rank_lgbm_l15 | lightgbm | 3/4 | 0.061 | 35.30% | true |
| rank_extra_leaf5 | extra_trees | 0/4 | 0.074 | 13.88% | false |
| rank_extra_leaf15 | extra_trees | 0/4 | 0.091 | 2.56% | false |
| rank_hist_leaf7 | hist_gradient | 2/4 | 0.042 | 43.64% | false |
| rank_hist_leaf15 | hist_gradient | 3/4 | 0.052 | 54.59% | true |

## Downside Risk

| Trial | Family | Fold wins | AUC | Brier | Coverage | Qualified |
|---|---|---:|---:|---:|---:|---|
| risk_logistic_t04 | logistic | 0/4 | 0.679 | 0.216 | 0.23 | false |
| risk_logistic_t06 | logistic | 3/4 | 0.679 | 0.216 | 0.59 | false |
| risk_lgbm_t04 | lightgbm_classifier | 1/4 | 0.623 | 0.200 | 0.33 | false |
| risk_lgbm_t06 | lightgbm_classifier | 3/4 | 0.623 | 0.200 | 0.69 | false |

## Limitations

- The current stock universe is survivorship-biased before its 2026-07-14 freeze date.
- Monthly cross-sectional rows share market regimes and are not independent iid samples.
- Model qualification is research evidence for isolated virtual paper, not broker authorization.
- No LLM-generated text or live model call participates in prediction or routing.
