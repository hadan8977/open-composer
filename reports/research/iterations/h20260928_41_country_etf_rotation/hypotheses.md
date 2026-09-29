# Hypotheses: h20260928_41_country_etf_rotation

Source: Quantpedia "Momentum Factor Effect in Country Equity Indexes"
(mechanism only, not its 1975-2014 sample numbers) -- see
`direction-review.json`/`external-brief.json` for the full citation.

## H1

- Hypothesis: Cross-sectional momentum rotation (rank by {63,252}-day
  lookback return, top {1,2}, absolute-momentum filter vs SHY,
  equal-weight, monthly or weekly rebalance) across the 9-ticker COUNTRY
  menu (EWJ/EWG/EWU/EWA/EWC/EWZ/INDA/EWY/EWT) clears K1 or K2 against S3 in
  both the anchor and stress windows, i.e. the same mechanism that
  (allegedly) works for FACTOR/INDUSTRY menus and S1-S3's own sector menu
  also works for single-country equity ETFs.
- Failure mode: single-country ETFs are more idiosyncratic (currency,
  local-market, geopolitical) than sector/factor ETFs, and their momentum
  may be weaker or noisier over 2016-2026 than either the Quantpedia
  1975-2014 sample or this project's own sector/factor menus; the sibling
  h20260928_40 batch's own K1/K2 outcome for FACTOR/INDUSTRY sets the
  nearest available base rate for whether this mechanism generally
  survives this project's contract.
- Measurement: `scripts/screen_batch.py --batch h20260928_41_country_etf_rotation --iteration h20260928_41_country_etf_rotation`,
  judged Sharpe (10bp) and 20bp CAGR in the frozen anchor
  (2024-01-08..2026-09-17) and stress (2016-05-02..2023-09-15) windows,
  against S3's own reference (anchor 1.4853, stress 0.8059).
- Stop/Pivot criterion: per `candidate-manifest.json`'s `keep_rule` -- K1
  (>=80% of S3 both windows, positive 20bp CAGR both windows) or K2 (>=0.05
  Sharpe edge vs a vol-matched S3 control, both windows). If none of the 8
  candidates clears either, or none reaches watch_recent, stop: refute
  `dir:international_country_etf_momentum_rotation` for this scope.
