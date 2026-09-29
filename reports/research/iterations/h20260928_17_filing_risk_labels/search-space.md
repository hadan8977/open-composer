# Search Space: h20260928_17_filing_risk_labels

One path, one candidate (RISK01), total budget 1. No parameter grid -- the horizon (20 trading
days) is fixed from the brief, and the universe (fixed-seed 50-ticker x 8-quarter = 400
filing-quarter panel) is fixed before any DeepSeek score exists. Benchmark family:
mismatched-filings-across-tickers-within-quarter placebo (no backtest benchmark, since no
portfolio is built in this pilot). Cost assumptions: none -- this is a feature/IC-only pilot, not
a backtest. Continue/stop decision: see `direction-review.json` `stop_condition` and
`candidate-manifest.json` `keep_rule`. Single-mechanism, non-campaign iteration
(`single_mechanism_no_campaign_attestation: true`), consistent with the direction's own
"small-sample pilot" framing -- a larger scale-up (and any 10-K-text acquisition) is explicitly
deferred, not part of this round's budget.
