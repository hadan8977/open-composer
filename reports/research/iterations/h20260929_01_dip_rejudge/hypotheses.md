# Hypotheses: h20260929_01_dip_rejudge

Source: H-20260924-01's own external-brief.json (Pagonidis 2014, Connors/
Alvarez RSI(2), Lehmann 1990, Klossner 2012, Pandey & Joshi 2023, plus the
three FMZ Pine-source cards), reused verbatim -- see `direction-review.json`.

## H1

- Hypothesis: At least one of H-20260924-01's 6 published ETF dip-reversion
  rules (D1-D6), run on SPY/QQQ 1x with next-open fill, clears K1 or K2
  against S3 under this project's screening-lane contract, in both the
  frozen anchor (2024-01-08..2026-09-17) and stress (2016-05-02..2023-09-15)
  windows -- a materially different, S3-relative bar than the giants-sweep
  G1/G1' bar H-20260924-01 tested against (0/24 pass).
- Failure mode: H-20260924-01's own 2016-2026 persistence table and D1's
  placebo failure (real percentile 58-92 across cells, needs >=95) already
  suggest most of the apparent edge is "being long in an uptrend," not a
  dip-timing-specific effect; K1/K2's S3-relative framing may simply
  re-confirm the same underlying weakness in different units.
- Measurement: `scripts/screen_batch.py --batch h20260929_01_dip_rejudge
  --iteration h20260929_01_dip_rejudge`, judged Sharpe (10bp) and 20bp CAGR
  in both frozen windows, against S3's own reference (anchor 1.4853, stress
  0.8059).
- Stop/Pivot criterion: per `candidate-manifest.json`'s `keep_rule` -- K1
  (>=80% of S3 both windows, positive 20bp CAGR both windows) or K2 (>=0.05
  Sharpe edge vs a vol-matched S3 control, both windows). If none of the 12
  candidates clears either, reaffirm `dir:etf_dip_reversion_ibs_connors`'s
  refutation under the K1/K2 bar too.

## H2

- Hypothesis: D1 (IBS-Algotradekit with EMA trend filter) -- the one rule
  H-20260924-01 flagged as distinct from the pack on its own placebo and
  persistence evidence -- performs relatively better than the other 5 rules
  under K1/K2 too, even if it does not clear the keep bar outright.
- Failure mode: D1's advantage under the old G1/G1' framing (positive
  per-trade mean, cross-timing consistency) does not translate to a Sharpe
  advantage under the S3-relative K1/K2 framing, e.g. because D1's low
  trade frequency (7-9/year) makes it a poor Sharpe competitor against a
  daily-rebalanced S3 reference regardless of per-trade edge.
- Measurement: same batch run; compare `DIP_D1_{SPY,QQQ}`'s judged anchor/
  stress Sharpe against the other 5 rules' `DIP_{D2..D6}_{SPY,QQQ}` cells.
- Stop/Pivot criterion: report the relative ranking in `report.md` regardless
  of outcome; no separate threshold beyond the shared K1/K2 keep_rule.
