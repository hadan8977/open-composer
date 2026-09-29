# Search Space: h20260928_16_8k_sentiment_accel

One path, one candidate (SENT01), total budget 1. No parameter grid -- the window lengths
(short=5, long=20 trading days) and horizon (5 trading days) are fixed from the LLM_Alpha
source construction, not searched. Benchmark family: shuffled-news-within-date placebo (no
backtest benchmark, since no portfolio is built in this pilot). Cost assumptions: none -- this
is a feature/IC-only pilot, not a backtest. Continue/stop decision: see
`direction-review.json` `stop_condition` and `candidate-manifest.json` `keep_rule`. This is a
single-mechanism, non-campaign iteration (`single_mechanism_no_campaign_attestation: true`),
consistent with the direction's own "cheapest possible falsification test" framing -- a full
purge(5)+embargo(5) walk-forward round is explicitly deferred, not part of this round's budget.
