# Hypotheses: mom_multiasset_multimodal_r3

## MM-H1

- Hypothesis: Grounded SEC filing, earnings-release and timestamped news features can distinguish catalyst-supported momentum from price-only momentum and improve cross-sectional ranking after costs.
- Failure mode: Text features merely restate price moves, have sparse/late coverage, or appear predictive only because retrospective LLM outputs contain later knowledge.
- Measurement: Four chronological folds with full purge and embargo; compare quant-only, text-only, quant-plus-text, missing-text fallback, shuffled-text and stale-text variants against deterministic 12-1.
- Stop/Pivot criterion: Stop historical Alpha claims if grounded text coverage is insufficient or placebos match the lift; keep only forward observation packets.

## MM-H2

- Hypothesis: Model disagreement, market regime and textual risk evidence can identify dates when an ML ranking should be accepted, shrunk or rejected.
- Failure mode: The gate learns a bull-market proxy, raises turnover, or selects thresholds from challenge outcomes.
- Measurement: Train-only gate calibration, four chronological folds, regime attribution, exact fallback parity and 5/10/20 bps cost stress.
- Stop/Pivot criterion: Stop the meta-gate if it does not beat always-champion and always-ML policies in at least three folds or the last two folds both fail.

## MM-H3

- Hypothesis: Cost-aware shrinkage from ML weights toward deterministic Top-5 weights improves net performance and stability relative to raw Top-K ML selection.
- Failure mode: Estimated costs do not resemble forward execution or shrinkage only reduces gross return without improving drawdown/turnover.
- Measurement: Same-date net returns, one-way turnover, drawdown, Sharpe, rank IC and full benchmark family under 5/10/20 bps assumptions.
- Stop/Pivot criterion: Stop if no shrinkage variant improves net return or risk-adjusted return without worsening both recent folds.

## KM-H1

- Hypothesis: Canonical source/claim/model memory reduces duplicate research and inference while preserving stale-source refreshes, negative findings and holdout isolation.
- Failure mode: URL normalization merges distinct claims, failed models are silently reused, or challenge results enter train-only research context.
- Measurement: Duplicate fixtures, stale/contradictory cards, model hash reuse, cache hits, source novelty report and visibility-partition tests.
- Stop/Pivot criterion: Block P.1/P.2 if knowledge assessment cannot distinguish reuse, refresh, new evidence and challenge-only memory.
