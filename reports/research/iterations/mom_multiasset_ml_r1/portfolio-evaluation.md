# Multi-Asset Momentum Virtual-Paper Portfolio

- Data as of: `2026-07-13T04:00:00+00:00`
- Forward epoch: `2026-07-14T00:00:00+00:00`
- Broker writes: `false`

| Sleeve | Strategy | Kind | Status | Targets |
|---|---|---|---|---|
| D1 | us_multiasset_etf_trend_d1 | deterministic | primary_deterministic | XLK 50%, SMH 50% |
| D2 | us_multiasset_stock_momentum_d2 | deterministic | primary_deterministic_exploratory_history | MU 20%, AMD 20%, INTC 20%, GOOGL 20%, CAT 20% |
| D3 | us_multiasset_stock_sector_relative_d3 | deterministic | diversification_deterministic_exploratory_history | MU 10%, INTC 10%, CSCO 10%, UNH 10%, CAT 10%, COST 10%, C 10%, KO 10%, MS 10%, MRK 10% |
| D4 | us_multiasset_stock_trend_quality_d4 | deterministic | diagnostic_deterministic | MU 10%, AMD 10%, INTC 10%, UNH 10%, CAT 10%, GS 10%, C 10%, LIN 10%, MS 10%, MRK 10% |
| M1 | us_multiasset_stock_rank_lgbm_m1 | ml_ranking | lockbox_failed_diagnostic_shadow | MU 20%, INTC 20%, CAT 20%, TMO 20%, ANET 20% |
| M2 | us_multiasset_stock_rank_hist_m2 | ml_ranking | lockbox_failed_diagnostic_shadow | MU 20%, INTC 20%, CAT 20%, TMO 20%, VZ 20% |
| A1 | us_multiasset_ai_regime_a1 | ai_ensemble | ai_research_challenger_historical_challenge_failed | TSLA 20%, META 20%, TMO 20%, BA 20%, CAT 20% |
| A2 | us_multiasset_ai_agreement_a2 | ai_ensemble | ai_research_challenger_historical_challenge_failed | MU 20%, AMD 20%, INTC 20%, GOOGL 20%, CAT 20% |

## Limitations

- D2-D4 and M1-M2 use a current frozen stock universe; pre-freeze history is exploratory.
- M1 and M2 passed development folds but failed the deterministic lockbox comparison.
- A1 and A2 passed historical development folds but failed the exposed historical challenge; they are forward diagnostic challengers only.
- All sleeves are file-based virtual paper observations and cannot submit broker orders.
