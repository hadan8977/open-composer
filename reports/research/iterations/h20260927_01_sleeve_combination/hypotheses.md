# Hypotheses: h20260927_01_sleeve_combination

Question: does combining S1/S2/S3 at a fixed (or trailing inverse-volatility)
proportion beat delevering S3 alone to the same realized volatility, on Sharpe
and stress-period drawdown, while still clearing the frozen anchor-window bar?

## H1 (M1 equal-thirds)

- Hypothesis: Equal-thirds S1/S2/S3, rebalanced monthly with intra-month
  drift, beats its volatility-matched control C1 (k*S3+(1-k)*SHY) on Sharpe by
  >=0.10 in both the anchor and stress windows, has a shallower stress-period
  max drawdown than C1, and still clears G1/G1' at 10bp and 20bp in the
  anchor window.
- Failure mode: S1/S2/S3 are highly correlated in the stress period (2018,
  2022 drawdowns hit leveraged-tech, growth and sector rotation sleeves
  together), so equal-thirds carries the same drawdown risk as S3 alone at
  lower average return, and Sharpe(M1) - Sharpe(C1) < 0.10 or the drawdown
  is not shallower.
- Measurement: candidate-manifest.json adoption_rule conditions (a)-(d) for
  M1 vs C1, computed by scripts/run_h20260927_01_sleeve_combination.py;
  reported in results.json and report.md.
- Stop/Pivot criterion: if H1 fails, do not adopt equal-thirds combination
  for the live pilot; check pairwise correlation to see whether S2's
  inclusion (the weakest sleeve) is the specific drag.

## H2 (M2 half S1 half S3)

- Hypothesis: Dropping S2 and blending only S1 (sector rotation) and S3
  (leveraged momentum) 50/50 beats its control C2 on the same four
  conditions, because S1 and S3 hold different underlying assets (sector
  ETFs vs leveraged tech/semis) and may be less correlated than S2 (growth
  rotation, which overlaps with S3's tech tilt) is with S3.
- Failure mode: S1 and S3 both de-risk to cash/SHY in the same regimes
  (absolute-momentum filters trigger together), so the correlation benefit
  does not materialize in the stress period specifically.
- Measurement: same adoption-rule conditions (a)-(d) for M2 vs C2.
- Stop/Pivot criterion: if H2 passes but H1 fails, the live-pilot
  recommendation should exclude S2 from any combined account rather than
  rejecting combination outright.

## H3 (M3 trailing-63-session inverse-volatility)

- Hypothesis: Weighting S1/S2/S3 inversely to their own trailing 63-session
  daily-return volatility (equal weight before 63 sessions of sleeve
  history exist) beats its control C3 on the same four conditions, because
  it structurally underweights S3 exactly when S3's own volatility is
  elevated (e.g. entering a drawdown), which a fixed proportion cannot do.
- Failure mode: because S3 already carries its own vt40 overlay, S3's
  realized volatility rarely spikes above S1/S2's, so the inverse-vol
  weights stay close to fixed proportions most of the time and add no real
  adaptivity, while still not fixing a correlated-drawdown failure mode.
- Measurement: same adoption-rule conditions (a)-(d) for M3 vs C3, plus the
  reported weight-path summary (how often M3's weights differ materially
  from M1's equal-thirds).
- Stop/Pivot criterion: if H3 also fails, the conclusion is that none of the
  tested combination rules add value over delevering S3 alone for these
  three specific sleeves, and the live pilot should not move to a combined
  account on this evidence (see decision-record.md).
