# Hypotheses: mom_multiasset_ml_r1

## ML-H1
- Hypothesis: A grouped factor panel can rank future 21-day stock excess returns more consistently than the fixed 12-1 score.
- Failure mode: Models memorize recent mega-cap winners or exploit unstable nonlinear interactions.
- Measurement: Four date-grouped expanding folds, rank IC/ICIR, top-5 excess return, turnover and three-of-four fold wins.
- Stop/Pivot criterion: Stop any family that fails the three-of-four gate; do not open its lockbox.

## ML-H2
- Hypothesis: A downside classifier can reduce severe 21-day drawdown exposure without destroying the deterministic portfolio's net return.
- Failure mode: Rare-event imbalance or poor calibration filters nearly every position and creates a cash strategy.
- Measurement: AUC, Brier, calibration, accepted-position coverage, drawdown-event rate and matched portfolio return.
- Stop/Pivot criterion: Stop if coverage falls below 30 percent, Brier is worse than the base rate, or return reduction exceeds drawdown improvement.

## ML-H3
- Hypothesis: Discrete sizing based on rank and downside probability can improve risk-adjusted performance over equal-weight top-5 selection.
- Failure mode: Sizing amplifies noisy predictions and raises turnover.
- Measurement: Fold Sharpe, IR, MaxDD, concentration and 5/10/20 bps cost stress.
- Stop/Pivot criterion: Keep equal weights unless sizing wins at least three folds and does not violate concentration limits.
