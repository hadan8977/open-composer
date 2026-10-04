# Search Space: h20261004_pm_midterm_odds_leadlag

One path (`midterm_control_odds_trump_trades`), three preregistered candidates, no parameter search and no model training.

- H-M (decision-eligible): Polymarket House and Senate Republican-control probabilities, 4pm-to-4pm change, mean of the two; 5-session EMA (span 5), 60-session rolling percentile rank, map to [-1, 1], lag one session; times the paper Table A.1 direction per asset; equal-weighted over the kept assets; MOC execution.
- M-CAT (report only): the same strategy per category (stock ETFs, bonds, banks, connected).
- M-KAL (report only): the same strategy with the Kalshi CONTROLH-2026-R and CONTROLS-2026-R prices as the signal.
- Assets: 27 US-listed tickers of the paper Table 1 (FX, gold, BTC, ETH excluded); an asset with bars for fewer than 80 percent of sessions is dropped and counted.
- Costs: 2 bp per side (10 bp for DJT and PHUN), doubled as a stress.
- Statistics: net Sharpe, Newey-West (5 lags) t, 1000 circular shifts (seed 20261004), the paper's predictive regression, day-2 reversal, same-day relation, gross Sharpe, sign-flip and unrelated-market placebos.
- Continue, stop and inconclusive rules are frozen in `hypotheses.md` and `candidate-manifest.json`. Total budget 3.
