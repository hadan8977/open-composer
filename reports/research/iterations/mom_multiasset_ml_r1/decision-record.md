# Decision Record: mom_multiasset_ml_r1

The ML round is preregistered before training. No family is selected in advance.

## M1
- Path: return ranking
- Decision: stop
- Reason: LightGBM and HistGradient passed three of four development folds, but both lost to the frozen deterministic 12-1 baseline on lockbox return and rank IC.
- Next iteration suggestion: Keep both as diagnostic virtual-paper shadows only; do not promote or retune from the opened lockbox.

## M2
- Path: downside-risk filtering
- Decision: stop
- Reason: Logistic and LightGBM risk models did not pass the preregistered calibration gate; their Brier scores were worse than the base-rate forecast despite some AUC signal.
- Next iteration suggestion: Preserve deterministic behavior and do not allocate a risk-gate sleeve in this round.

## M3
- Path: position sizing
- Decision: stop
- Reason: Prediction-weighted and risk-capped sizing did not establish independent, stable marginal lift over equal-weight top-5 selection.
- Next iteration suggestion: Use equal weights in all forward sleeves and require a new iter-id before testing a different sizing hypothesis.

## Portfolio
- Path: isolated virtual-paper comparison
- Decision: continue
- Reason: D1, D2 and D3 are retained as deterministic forward sleeves; D4 is diagnostic; M1 and M2 are lockbox-failed diagnostic shadows. All six are draft, file-based, and broker-disabled.
- Next iteration suggestion: Append forward observations without tuning against the frozen epoch that begins on 2026-07-14.
