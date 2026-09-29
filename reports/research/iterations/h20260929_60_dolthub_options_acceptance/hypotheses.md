# Hypotheses: h20260929_60_dolthub_options_acceptance

Data acceptance task; no trading hypothesis. H1: DoltHub option_chain covers SPY/QQQ/AAPL/NVDA/TSLA well enough (coverage, snapshot time, spread, bad quotes; thresholds in results.json `criteria`) to price option strategies. Failure mode: gaps, undocumented snapshot time. Result: rejected (see decision-record.md).
