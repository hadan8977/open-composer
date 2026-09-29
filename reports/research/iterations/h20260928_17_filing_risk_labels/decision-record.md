# Decision Record: h20260928_17_filing_risk_labels

## P1: filing_risk_label_ic_screen (RISK01)

- Path: filing_risk_label_ic_screen
- Decision: stop
- Reason: Real standalone rank IC (risk_score vs forward 20-trading-day return, 400 filing-quarters,
  8 quarters) is negative (mean -0.0565, t=-1.67, not significant at conventional 95% for n=8) and
  sign-stable across 75% of quarters, clearing the stability bar alone. But the mismatched-filings-
  within-quarter placebo has the OPPOSITE sign (+0.0423) and a magnitude (74.9% of the real IC's)
  too close to the real result to call it clearly distinct from noise on only 8 quarterly
  observations. The preregistered keep_rule (candidate-manifest.json) requires the placebo to be
  BOTH same-signed AND <50% of the real magnitude to pass; it is neither. Zoo-integration IC lift
  was not attempted (existing ranking pipeline not quick to adapt to this pilot's disjoint 50-ticker
  sample within budget) -- standalone-only, disclosed per the brief's escape hatch. See results.json
  for the full numeric breakdown and the note on a wording tension between direction-review.json's
  prose stop_condition and the manifest's literal AND-structured gate (the stricter manifest reading
  controls).
- Next iteration suggestion: If this direction is reopened, it needs either (a) a materially larger
  sample (more tickers/quarters) to get enough quarterly IC observations for the placebo comparison
  to be decisive, or (b) real 10-K Item 1A risk-factor text (not 8-K press releases) per the
  original plan, which was not available locally this pass. Not reopened without new disclosed data
  or a different construction.
