# Hypotheses: h20260929_02_pre_holiday_etf

Source: Ariel (1990, original claim, cited via secondary source) and Ko & Yang
(2021, full text read locally, `ko_yang_2021_pre_holiday_small_firm_replication`)
-- see `direction-review.json`/`external-brief.json` for the full citation
chain and reflections.

## H1

- Hypothesis: A calendar-anchored pre-holiday long/cash rule (buy the last
  trading day before a federal-market-holiday closure, hold 1 or 2 sessions,
  else hold SHY) captures a real edge on at least one small/micro-cap ETF
  (IWM, IJR, IWC, VB) -- i.e. at least one of the 4 small-cap-tier
  `PREHOL_{IWM,IJR,IWC,VB}_H{1,2}` candidates clears K1 or K2 against S3 in
  both the anchor and stress windows.
- Failure mode: dir:pre_holiday_effect_small_cap_tier was `queued` (untested
  locally) before this iteration, not previously refuted, but Ko & Yang
  (2021)'s own magnitude (mean pre-holiday return 0.14-0.37pp per session,
  ~9-10 events/year) implies a low expected annualized Sharpe contribution
  even if the direction is confirmed; the adjacent local prior
  dir:turn_of_month_equity_seasonality (a different calendar anchor) failed
  both K1 and K2 with strongly negative Sharpe/edge under this exact frozen
  contract, a realistic prior that single-ETF calendar rules have not
  cleared this project's bar recently.
- Measurement: `scripts/screen_batch.py --batch h20260929_02_pre_holiday_etf
  --iteration h20260929_02_pre_holiday_etf`, judged Sharpe (10bp) and 20bp
  CAGR in the frozen anchor (2024-01-08..2026-09-17) and stress
  (2016-05-02..2023-09-15) windows, against S3's own reference (anchor
  1.4853, stress 0.8059).
- Stop/Pivot criterion: per `candidate-manifest.json`'s `keep_rule` -- K1
  (Sharpe >=1.1882 anchor / >=0.6447 stress, positive 20bp CAGR both
  windows) or K2 (>=0.05 Sharpe edge vs a vol-matched S3 control, both
  windows), for at least one small-cap-tier primary candidate, and it must
  beat its own ticker's RAND placebo on judged anchor Sharpe. If none of the
  4 small-cap-tier candidates clears either gate, or every apparent pass is
  matched/beaten by its own placebo, stop: refute or mark evidence_too_weak
  for the small-cap tier of dir:pre_holiday_effect_small_cap_tier.
- Result: Failure mode confirmed. 0 of the 4 small-cap-tier candidates
  (`PREHOL_{IWM,IJR,IWC,VB}_H{1,2}`) cleared K1 (best anchor Sharpe
  -0.81 for IWC_H1, need >=1.1882) or K2 (all anchor-window edges
  negative, -0.42 to -0.93, need >=0.05 both windows). Registry
  updated to `refuted` for the small-cap tier. See `report.md`/
  `results.json`.

## H2

- Hypothesis: The small-cap-tier group (IWM/IJR/IWC/VB) reproduces Ko & Yang
  (2021)'s own out-of-sample pattern of retaining more of the pre-holiday
  premium than the large-cap-tier group (SPY/QQQ) -- i.e. the small-cap
  group's median judged Sharpe exceeds the large-cap group's median judged
  Sharpe, in both the anchor and stress windows, matching the source's own
  finding that the large-firm premium is "essentially disappeared,
  particularly after 1990."
- Failure mode: an ETF-level test may not reproduce an index-level/
  stock-decile-level pattern at all (IWM/IJR/IWC/VB are themselves liquid,
  easily-arbitraged instruments even though their underlying constituents
  are less liquid individually) -- the small-minus-large difference could
  be flat, negative, or dominated by noise given the small per-candidate
  trade count (~9-10/year).
- Measurement: same batch run; small-cap group median judged Sharpe minus
  large-cap group median judged Sharpe (both {H1,H2} hold lengths pooled
  per ticker, both windows), reported per `candidate-manifest.json`'s
  `keep_rule.small_cap_vs_large_cap_report_only` field. Report only, not a
  gate on its own (per the brief's instruction).
- Stop/Pivot criterion: report-only; does not itself gate keep/not-keep,
  but a negative or near-zero difference is evidence against the source's
  small-firm-only mechanism reproducing at the ETF level even if some
  individual small-cap candidate happens to clear K1/K2 by noise (cross-
  checked against the RAND placebo for that candidate specifically).
- Result: The small-cap tier's median judged Sharpe was less negative
  than the large-cap tier's in both windows (+0.32 anchor, +0.06
  stress -- `results.json`'s `small_cap_vs_large_cap_report_only`),
  the same direction as Ko & Yang (2021)'s own pattern. But both
  tiers are deeply unprofitable (medians -1.28 and -1.60 anchor,
  -0.95 and -1.01 stress respectively) and fail K1/K2 by a wide
  margin -- a "less bad" relative difference between two failing
  groups, not evidence of a tradable small-cap edge. Does not change
  the H1 refutation.

## H3

- Hypothesis: The large-cap-tier group (SPY, QQQ) does NOT clear K1/K2 --
  matching Ko & Yang (2021)'s own finding that the large-firm pre-holiday
  premium has "essentially disappeared" out of sample, this project's local
  test on SPY/QQQ should also fail to find a tradable edge, serving as the
  source's own predicted internal negative control.
- Failure mode: if SPY or QQQ instead clears K1/K2 while beating its own
  RAND placebo, either the source's large-firm-disappearance finding does
  not hold at the ETF/index level in this more recent sample, or the
  candidate's apparent edge is a project-specific artifact (fill/cost
  convention, holiday-set definition) rather than the pre-holiday mechanism
  itself -- worth flagging explicitly either way.
- Measurement: same batch run; PREHOL_SPY_H1/H2 and PREHOL_QQQ_H1/H2's own
  K1/K2/placebo results.
- Stop/Pivot criterion: not itself a keep/not-keep gate (SPY/QQQ candidates
  are still primary and keep-eligible per the manifest, since the source's
  large-firm finding is a prediction being tested, not a preregistered
  exclusion) -- but a large-cap pass is reported as evidence against, not
  for, the small-firm-only mechanism, and a large-cap fail is reported as
  corroborating H2.
- Result: Confirmed. Neither `PREHOL_SPY_H1/H2` nor `PREHOL_QQQ_H1/H2`
  cleared K1 or K2 (anchor Sharpe -1.33 to -1.76, all far below the
  bar), matching Ko & Yang (2021)'s own large-firm-disappeared
  finding -- the large-cap group did not produce a false-positive
  edge that would have complicated the small-firm-only reading.
