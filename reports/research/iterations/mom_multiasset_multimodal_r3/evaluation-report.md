# Multiasset Multimodal Momentum R3

- Workflow pass: `True`
- Research pass: `False`
- LLM contribution pass: `False`
- Paper ready pass: `False`
- Candidates: `24/24`
- Completed/skipped: `14/10`
- Best development diagnostic: `regime_train_median`

## Trial Summary

| Trial | Path | Status | Fold wins | Qualified |
|---|---|---|---:|---|
| deterministic_12_1 | champion_and_text_ablations | validation_complete | 0 | False |
| quant_ranker_daynight | champion_and_text_ablations | validation_complete | 1 | False |
| text_only | champion_and_text_ablations | skipped_dependency | - | False |
| quant_plus_text | champion_and_text_ablations | skipped_dependency | - | False |
| shuffled_text_placebo | champion_and_text_ablations | skipped_dependency | - | False |
| stale_text_placebo | champion_and_text_ablations | skipped_dependency | - | False |
| catalyst_confirm_low | catalyst_and_risk_roles | skipped_dependency | - | False |
| catalyst_confirm_high | catalyst_and_risk_roles | skipped_dependency | - | False |
| false_momentum_veto_low | catalyst_and_risk_roles | skipped_dependency | - | False |
| false_momentum_veto_high | catalyst_and_risk_roles | skipped_dependency | - | False |
| text_risk_gate_low | catalyst_and_risk_roles | skipped_dependency | - | False |
| text_risk_gate_high | catalyst_and_risk_roles | skipped_dependency | - | False |
| regime_train_median | regime_and_disagreement_meta | validation_complete | 2 | False |
| regime_train_upper_quartile | regime_and_disagreement_meta | validation_complete | 2 | False |
| disagreement_train_median | regime_and_disagreement_meta | validation_complete | 0 | False |
| disagreement_train_upper_quartile | regime_and_disagreement_meta | validation_complete | 1 | False |
| agreement_overlap3 | regime_and_disagreement_meta | validation_complete | 1 | False |
| agreement_overlap4 | regime_and_disagreement_meta | validation_complete | 1 | False |
| shrink_025_cost10 | cost_aware_shrinkage | validation_complete | 0 | False |
| shrink_050_cost10 | cost_aware_shrinkage | validation_complete | 1 | False |
| shrink_075_cost10 | cost_aware_shrinkage | validation_complete | 1 | False |
| shrink_025_cost20 | cost_aware_shrinkage | validation_complete | 0 | False |
| shrink_050_cost20 | cost_aware_shrinkage | validation_complete | 1 | False |
| shrink_075_cost20 | cost_aware_shrinkage | validation_complete | 1 | False |

## Verdict

Real historical multimodal packets are not authorized. Text-dependent trials were counted and skipped rather than replaced by fixtures. Quantitative day/night, regime/disagreement and shrinkage variants remain diagnostic because the exposed historical challenge was not reopened.
