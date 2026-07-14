# Hypotheses: mom_multiasset_ai_r2

## AI-H1
- Hypothesis: Expanded price-volume, residual and trend-quality characteristics improve 21-day cross-sectional rank IC over the original 12-feature contract.
- Failure mode: Added factors are redundant, unstable or merely encode the current mega-cap winners.
- Measurement: Four purged chronological development folds; compare the same model with core-only and expanded-quant features.
- Stop/Pivot criterion: Stop if expanded features fail to improve at least three folds or recent-fold net portfolio metrics deteriorate materially.

## AI-H2
- Hypothesis: Static LLM-compiled nonlinear formulas add marginal information beyond conventional expanded factors.
- Failure mode: Formulas are algebraic duplicates, data-mined noise or transformations of the deterministic 12-1 score.
- Measurement: Fold-local selection, pairwise correlation pruning, same-model ablation and missing-AI-factor fallback.
- Stop/Pivot criterion: Set llm_contribution_pass=false unless AI formulas beat the matched expanded-quant model in at least three folds and aggregate rank IC or cost-adjusted return.

## AI-H3
- Hypothesis: Date-grouped LambdaRank aligns training more closely with top-5 portfolio selection than point regression.
- Failure mode: Too few independent market regimes cause ranking trees to overfit weekly overlapping samples.
- Measurement: Five-day training cross sections, 21-day label purge plus 21-day embargo, and monthly test portfolios.
- Stop/Pivot criterion: Stop if LambdaRank does not beat deterministic 12-1 in at least three folds or if recent two folds both lose.

## AI-H4
- Hypothesis: A low-weight ML blend or disagreement abstention improves robustness without discarding the deterministic momentum edge.
- Failure mode: Blending dilutes the strong baseline, and abstention becomes an ex-post timing rule.
- Measurement: Preregistered blend weights and agreement thresholds evaluated only on stitched OOS predictions.
- Stop/Pivot criterion: Keep only a blend that improves aggregate cost-adjusted return or max drawdown while preserving rank IC and fold stability.
