# External brief: h20260930_10_industry_seasonality

Eight sources were opened and snapshotted under `sources/`; each has a verified claim card in `reports/harness/source_cards/h20260930_10_industry_seasonality.jsonl` (quote matched against the snapshot). Detail per source is in `external-brief.json` and `direction-review.json`.

- Mechanism (papers): Keloharju-Linnainmaa-Nyberg (AQR working paper and JF 2016 record) report industry same-calendar-month long-short 0.70% per month, t 3.79, 1963-2011; Heston-Sadka find the stock-level pattern but say it is independent of industry. Moskowitz-Grinblatt show industry momentum, a competing explanation for a shift-1 score.
- Rule: Quantpedia's top-2 front-running on 9 sector SPDRs is the parent rule; the extension changes only the universe (23 industry ETFs) and the grid (top_n 2/3/5, avg_years 1/5).
- Negative and decay evidence: Allocate Smartly's country and commodity extended tests found the front-running family inconsistent outside the author's sample; McLean-Pontiff report about 35% post-publication decay in published predictors.
- Consequence for design: judged by a random-shift placebo (beat fraction <= 10%), 20bp anchor CAGR > 0 and a C2 combination increment on both anchor and stress windows, not by the recent Sharpe alone.
