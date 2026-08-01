# Hypotheses: mom_multiasset_forward_multimodal_r5

## Hypothesis R5-H1: deterministic ETF momentum remains a viable control

The fixed 12-1 and 6-1 trend rules should produce positive net results in at least three chronological folds without breaching the drawdown, turnover or stress-cost gates.

- Failure mode: performance is concentrated in one regime, reserve transitions dominate, or matched balanced and market benchmarks explain the result.
- Measurement: fold and transfer-holdout return, Sharpe, drawdown, turnover, benchmark deltas, DSR and PBO under the common cost engine.
- Stop/Pivot criterion: stop any deterministic candidate that fails the frozen family gates; do not retune horizons or Top-K inside R5.

## Hypothesis R5-H2: a small fold-local trained ranker adds stable lift

R5M01 should improve net ranking performance over R5D01 using only seven market features, while R5M02 may reject fragile selections only if its probability calibration beats the fold base rate.

- Failure mode: the model learns period or symbol identity, loses to the deterministic control, has unstable feature importance, or fails calibration.
- Measurement: fold-local rank IC, net target returns, three-of-four fold wins, transfer-holdout delta, Brier score and calibration slope.
- Stop/Pivot criterion: stop the trained role if the matched gates fail; retain serialized outputs only as negative evidence and never warm-start the next round.

## Hypothesis R5-H3: frozen LLM-derived formulas add non-placebo information

Four formula structures generated and frozen in R2 may transfer to ETFs as cross-sectional factor combinations. L01 and C01 must demonstrate lift beyond D01/M01 and beyond the seeded P01 shuffled mapping.

- Failure mode: formula performance is explained by core momentum, the shuffled placebo performs as well, or lift disappears under 20 bps costs or the transfer holdout.
- Measurement: matched formula-only, quant-only, combined and placebo fold deltas with unchanged data, model and costs, plus the preregistered paired non-circular moving-block bootstrap on the 384 TRANSFER 10 bps intervals. The bootstrap compares annualized Sharpe differences for C01-M01 and C01-P01 using shared 21-session blocks, 2,000 PCG64 seed-4201 resamples, and Bonferroni-adjusted one-sided 2.5% lower bounds after restoring each candidate's boundary costs exactly once.
- Stop/Pivot criterion: set llm_contribution_pass false unless C01 wins the fold and transfer point gates, each observed transfer Sharpe delta is at least 0.05, and both sorted-index-49 lower bounds are strictly positive. A pass means only historical contribution from the frozen formula mappings, never independent LLM Alpha; do not generate replacement formulas.

## Hypothesis R5-H4: path-survival rejection improves risk without hidden leverage

R5M02 may reduce drawdown while preserving sufficient return only when its fold-local classifier is better calibrated than a constant base-rate forecast.

- Failure mode: poor Brier score, unstable threshold behavior, excessive reserve allocation, or lower risk caused only by materially lower exposure.
- Measurement: Brier score, calibration slope, exposure-matched return, drawdown and opportunity-cost decomposition.
- Stop/Pivot criterion: disable the risk gate and fall back to M01 then D01 if calibration or exposure-matched performance fails.

## Hypothesis R5-H5: missing modality and placebo controls fail safely

R5F01 must be exactly target-identical to R5M01, while R5P01 must remain selection prohibited regardless of apparent performance.

- Failure mode: missing formulas alter targets, model loading changes the deterministic fallback, or placebo outcomes influence candidate selection.
- Measurement: byte-level target-ledger identity for F01/M01 and deterministic permutation audit for P01.
- Stop/Pivot criterion: block the entire family on any fallback identity failure; report placebo results without promotion authority.
