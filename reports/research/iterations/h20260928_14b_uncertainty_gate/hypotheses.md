# Hypotheses: h20260928_14b_uncertainty_gate

Card H-20260928-31 / queue task T-20260928-14. Three candidates, one path
(`uncertainty_gate_t1_book`), all counted toward trial exposure (DSR n=3).

## H1 (U1: book-level moderate gate)

- Hypothesis: A trained ensemble-disagreement uncertainty signal z(t), when it
  exceeds its own trailing-252-session 0.80 quantile, flags T1 book days of
  above-median future drawdown well enough (AUROC>=0.60) that cutting exposure
  to 0.5 on those days raises anchor-window Sharpe by >=0.10 over a
  same-realized-vol-matched unguarded control, and this is not explainable by
  a block/circular-shift placebo of the same gate series.
- Failure mode: z(t) is just noise (AUROC<0.60), or the exposure cut merely
  de-levers the book (same failure mode as the already-refuted
  dir:meta_labeling_position_tiers) so a placebo of equivalent on/off share
  matches or beats it, or any Sharpe gain is fully explained by lower realized
  volatility (fails the owner's vol-matched-control rule).
- Measurement: AUROC of z(t) vs. a drawdown-flag label on 2024-01-08..latest;
  >=200-seed block/circular-shift placebo on the anchor window; anchor-window
  Sharpe vs. a same-realized-vol k*book+(1-k)*SHY control.
- Stop/Pivot criterion: any one of AUROC<0.60, placebo failure (drawdown
  improvement <5pp over placebo median, or Sharpe below the placebo 90th
  percentile), or Sharpe-vs-control gain <0.10 stops U1 at stage 1, refuted.

## H2 (U2: book-level severe gate)

- Hypothesis: identical mechanism to H1 but at the paper's own more extreme
  quantile (z>0.90) and full de-risking (exposure to 0.0); tests whether a
  more selective, more aggressive gate clears the bar where the moderate
  gate (H1) does not, or vice versa.
- Failure mode: same three failure modes as H1, evaluated independently
  (U2 is not assumed to pass or fail with U1).
- Measurement: identical to H1, on the same z(t) series (only the trigger
  threshold and multiplier differ).
- Stop/Pivot criterion: identical structure to H1, independently applied.

## H3 (U3: individual-name DEUP-style tail-risk cap)

- Hypothesis: excluding the top 20% most-uncertain names (by ensemble
  disagreement u_i(t)) at each new cohort's formation, backfilled by momentum
  rank, raises anchor-window Sharpe by >=0.10 over the same vol-matched
  control, matching the source paper's own finding that ehat is best used as
  a tail-risk cap on individual names rather than a continuous or book-level
  sizing denominator.
- Failure mode: the exclusion rule is indistinguishable from randomly
  dropping the same number of names each cohort (fails its own
  random-quintile-drop placebo), or any Sharpe gain is fully attributable to
  the resulting lower realized volatility (fails the owner's vol-matched-
  control rule). U3 has no book-level z(t) series, so the AUROC stop
  condition (a) does not apply to it, per the preregistration.
- Measurement: >=200-seed random-quintile-drop placebo on the anchor window;
  anchor-window Sharpe vs. the same vol-matched control.
- Stop/Pivot criterion: placebo failure or Sharpe-vs-control gain <0.10 stops
  U3 at stage 1, refuted.

No hypothesis's stage-1 threshold, quantile, position size, or exclusion
fraction may change after any result is seen (direction-review.json
stop_condition, candidate-manifest.json parameters).
