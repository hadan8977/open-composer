# Hypotheses: mom_minute_r3_ml

## H1

- Hypothesis: lagged momentum, volatility, and TQQQ gap features can identify a subset of frozen-rule entries with better net episode outcomes.
- Failure mode: the classifier learns sample-specific regimes, rejects most profitable entries, or only reduces exposure without improving return and risk together.
- Measurement: compare eight fixed Logistic and LightGBM trials on three episode-purged expanding validation folds using index-minus-one features and reference-engine costs.
- Stop/Pivot criterion: stop holdout evaluation unless a family wins at least two of three folds with complete OOS coverage.

## H2

- Hypothesis: a nonlinear LightGBM gate provides incremental value over a regularized linear gate.
- Failure mode: nonlinear capacity overfits 138 development episodes and produces unstable probabilities.
- Measurement: use the same folds, event identities, features, and thresholds for both families; compare fold wins and validation episode return.
- Stop/Pivot criterion: keep both as diagnostic shadow only when neither family reaches the preregistered validation gate; do not enlarge the search.
