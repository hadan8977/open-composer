# Hypotheses: h20260928_17_filing_risk_labels

## H1: DeepSeek-extracted 8-K risk_score carries next-20-day cross-sectional information

- Hypothesis: `risk_score` (DeepSeek-extracted, 0-1, higher=more risk/uncertainty disclosed) computed
  per (ticker, filing-quarter) from 8-K text on the preregistered 50-ticker x 8-quarter panel has a
  stable-signed rank IC against forward 20-trading-day returns, and (if the integration is quick)
  a positive IC lift when added to the existing factor-zoo ranking pipeline.
- Source support: Dolphin et al. (arxiv 2601.15247, structured risk-label extraction carries real
  economic structure); Choi et al. (arxiv 2510.03195, LLM-structured disclosure features beat an NER
  baseline by >2x risk-adjusted alpha); Campbell et al. (2014, raw risk-factor text already carries
  information content) -- see external-brief.json.
- Failure mode: IC sign flips across quarters (no stable cross-sectional information), or a
  mismatched-filings-across-tickers-within-quarter placebo reproduces the same IC magnitude and sign.
- Measurement: mean rank IC across the panel, t-stat, fraction of positive-sign observations, real
  vs placebo, standalone IC and (if computed) zoo-added IC lift.
- Stop/Pivot criterion: per direction-review.json `stop_condition` -- stop before scaling if IC sign
  is unstable (<60% share the mean's sign) or placebo reproduces >=50% of the real IC's magnitude
  with the same sign.
