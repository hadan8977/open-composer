# Hypotheses: h20260929_10_vix_vrp_etp

Source: Zarattini/Aziz/Mele (2025, SSRN 5316487 / SFI RP 25-91), per the
independent QuantConnect replication (`quantconnect_dual_vix_signal_replication`)
-- see `direction-review.json`/`external-brief.json` for the full citation
chain and reflections.

## H1

- Hypothesis: A long-only-ETP version of the dual-VIX-signal volatility risk
  premium rule (eVRP = VIX minus annualized realized SPY vol; term structure
  = VIX vs VIX3M; short-vol state holds SVXY sized at VIX/100 or half; else
  holds SPY or SHY) captures a real edge, i.e. at least one of the 10 primary
  `VVRP_*` candidates clears K1 or K2 against S3 in both the anchor and
  stress windows.
- Failure mode: dir:vix_term_structure_short_vol's prior verdict flagged the
  underlying "short vol most of the time" mechanism family as untested
  locally for lack of data, not as refuted; but an adjacent local campaign
  (mom_vix_term_structure_overlay_r1_implfix1, a VIX/VIX3M-gated TQQQ/QQQ/BIL
  exposure ladder, a different mechanism) found research_pass=false with DSR
  promotion probabilities of 0.0018-0.0058 across 4 candidates -- weak but
  real evidence that VIX/VIX3M-conditioned timing overlays broadly struggle
  under this project's specific contract. SVXY's 2018-02-27 multiplier
  change (-1x to -0.5x) inside the stress window is a further confound this
  rule must survive.
- Measurement: `scripts/screen_batch.py --batch h20260929_10_vix_vrp_etp
  --iteration h20260929_10_vix_vrp_etp`, judged Sharpe (10bp) and 20bp CAGR
  in the frozen anchor (2024-01-08..2026-09-17) and stress
  (2016-05-02..2023-09-15) windows, against S3's own reference (anchor
  1.4853, stress 0.8059).
- Stop/Pivot criterion: per `candidate-manifest.json`'s `keep_rule` -- K1
  (Sharpe >=1.1882 anchor / >=0.6447 stress, positive 20bp CAGR both
  windows) or K2 (>=0.05 Sharpe edge vs a vol-matched S3 control, both
  windows). If none of the 10 primary candidates clears either, or every
  apparent pass is beaten by VVRP_RAND_PLACEBO or STATIC5050_SMH_QQQ, stop:
  refute this reopening of `dir:vix_term_structure_short_vol` for the
  long-only-ETP scope tested here (the registry's original "needs VX
  futures curve" verdict would remain moot -- refuted for a different,
  newer reason: the ETP-only mechanism itself does not clear the bar, not
  that it is inexecutable).
- Result: Failure mode confirmed. All 10 primary candidates failed K1
  (best anchor Sharpe 0.42, need >=1.19) and K2 (all anchor-window edges
  negative, -0.41 to -0.06, need >=0.05 both windows). Registry updated to
  `refuted`. See `report.md`/`results.json`.

## H2

- Hypothesis: The eVRP/term-structure conditioning is doing real work,
  distinct from simply being short-vol (SVXY) at an arbitrary frequency of
  the same average magnitude -- i.e. VVRP_COMBO_RV10_SHY's anchor-window
  Sharpe exceeds VVRP_RAND_PLACEBO's anchor-window Sharpe, and both signal
  ablations (VVRP_SIG1ONLY, VVRP_SIG2ONLY) are compared against the full
  combo to see whether either single signal alone carries the edge.
- Failure mode: any apparent edge is actually just "being short SVXY most
  of the time in a period when realized vol exceeded implied vol on
  average," indistinguishable from a frequency-matched random short-vol
  day, or carried entirely by one signal with the other adding nothing (or
  net-subtracting) once costs are applied.
- Measurement: same batch run; compare VVRP_COMBO_RV10_SHY's judged anchor
  Sharpe against VVRP_RAND_PLACEBO's and against VVRP_SIG1ONLY_SHY's /
  VVRP_SIG2ONLY_SHY's.
- Stop/Pivot criterion: per `candidate-manifest.json`'s
  `placebo_and_benchmark_internal_falsification` rule -- if
  VVRP_RAND_PLACEBO's anchor Sharpe is >= a primary candidate's own anchor
  Sharpe, demote that primary candidate to "not kept (placebo replication)"
  regardless of K1/K2. Signal-ablation comparisons are reported (which
  signal, if either, carries the edge) but do not themselves gate keep/not
  keep -- only the RAND placebo and the static 50/50 control do.
- Result: VVRP_COMBO_RV10_SHY's anchor Sharpe (-0.04) was actually BELOW
  VVRP_RAND_PLACEBO's (0.07) -- the full 2-signal combo did not beat the
  random-day placebo on anchor Sharpe. Several other primaries (e.g.
  VVRP_SIG1ONLY_SHY at 0.42) did beat the placebo, weakly suggesting the
  eVRP signal alone carries more of whatever small edge exists than the
  term-structure signal or the full combo -- but since no primary cleared
  K1/K2 regardless, this ablation finding does not change the overall
  refutation.

## H3

- Hypothesis: This project's long-only-ETP simplification (SVXY 1x weight
  = VIX/100, no long-vol leg, no 2%-no-trade band, next-open fill) produces
  a Sharpe in the same ballpark as the QuantConnect replication's own
  2016-01..2026-07 Sharpe 0.729 for the closest faithful-parameter analog
  (VVRP_COMBO_RV10_SPY), once methodology differences (SVXY vs VIXY, cost/
  fill convention, no-trade band) are accounted for.
- Failure mode: the differences (SVXY's -0.5x/-1x structural mismatch vs
  VIXY's 1x, this project's daily-rebalance-every-signal-day convention vs
  QC's 2%-threshold-gated live trading, and cost/fill timing) could produce
  a Sharpe far from 0.729 in either direction without that gap itself
  being evidence against the underlying mechanism.
- Measurement: compute VVRP_COMBO_RV10_SPY's own Sharpe over 2016-01-04
  (earliest local data) through the panel's last available date (2026-09),
  the closest achievable analog to QC's 2016-01..2026-07 window, and report
  it alongside 0.729 with the methodology differences stated explicitly.
- Stop/Pivot criterion: This is a reconciliation/context check, not a
  keep/not-keep gate on its own -- reported in `report.md`, does not
  override the K1/K2/placebo verdict from H1/H2.
- Result: naive full-history Sharpe (no risk-free subtraction) for
  VVRP_COMBO_RV10_SPY was ~0.59 over 2016-01..2026-07 and ~0.59 over the
  full available range through 2026-09 -- in the same ballpark as QC's
  0.729 but noticeably below it, consistent with the stated methodology
  differences (SVXY vs VIXY, no no-trade band, idle-capital handling).
  Reconciliation confirmed as plausible; does not change the H1/H2
  refutation verdict.
