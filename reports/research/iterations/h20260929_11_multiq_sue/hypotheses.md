# Hypotheses: h20260929_11_multiq_sue

## H1

- Hypothesis: An elastic net on the last 8 quarters of SUE (eps and revenue) plus streak counts, refit yearly on an expanding window, ranks S&P 500 stocks so that the monthly top-50 book clears K1 (median-offset net-10bp Sharpe >= 1.1882 in the anchor window and >= 0.6447 in the (short) stress window, net-20bp CAGR positive in both) and beats SUE1_TOP50, MOM12_1_TOP50, ENET_SHUF_TOP50 and RAND_TOP50 on anchor Sharpe.
- Source support: kaczmarek_zaremba_2025_frl_multiq_sue (abstract only), chordia_shivakumar_2006_earnings_momentum, hansen_siggaard_2024_dml_pead.
- Failure mode: PEAD is gone in large caps (martineau_2021_rip_pead, ucla_anderson_review_2026_pead_again); our SUE is visible only after the filing, after the announcement reaction (dir:pead_xbrl_sue_filing_date refuted on single-quarter SUE); the model may only proxy momentum (hansen_siggaard_2024_dml_pead).
- Measurement: reports/research/screens/h20260929_11_multiq_sue/leaderboard.json (judged.anchor.sharpe, judged.stress.sharpe, per_window net20 cagr) and reports/research/iterations/h20260929_11_multiq_sue/model-fits.json (RankIC by year).
- Stop/Pivot criterion: keep_rule in candidate-manifest.json; if no keep-eligible candidate clears any tier or the increment criterion fails, H1 is refuted for this data.

## H2

- Hypothesis: Even if not standalone, the ENET_TOP50 book adds K2 value (>= 0.05 Sharpe edge in both windows) when blended with S3.
- Source support: S3 diversification logic (screen_lane K2 machinery).
- Failure mode: a long-only S&P 500 stock book has beta near 1 to the same equity factor S3 loads on, so the blend adds little.
- Measurement: leaderboard.json diversifier.anchor.judged_edge / diversifier.stress.judged_edge.
- Stop/Pivot criterion: as keep_rule K2.

## Result (appended after the run; preregistered text above unchanged)

- H1 refuted: no keep-eligible candidate clears K1/K2/watch_recent; ENET_TOP50 anchor 0.60, stress 0.38; increment criterion False (see report.md).
- H2 refuted: ENET_TOP50 K2 edge -0.11 anchor / -0.29 stress.
