# Hypotheses: h20260929_71_wikipedia_pageviews

## Hypothesis

Stocks whose English Wikipedia page views over the last 7 days rose the most relative to the prior 28-day daily mean (VC7_28) earn a higher return in the following week (open of d+1 to open of d+6, excess over SPY) than stocks whose views fell, in the S&P 500 cross-section.

## Failure mode

(a) Page-view spikes mostly mark earnings weeks and news that are already priced (Zhu 2019), so the IC is zero after the fill; (b) attention effects reverse within a week (Da et al. 2011), giving the wrong sign; (c) search-attention predictability is mostly price-return predictability (Challet 2014), so a raw IC could be short-term reversal in disguise; (d) survivorship of current constituents inflates 2016-2023; (e) article renames and bot traffic break series.

## Measurement

Weekly Spearman RankIC of VC7_28 (signal = ln((views d-6..d + 1) / (7 x mean views d-34..d-7 + 1)), needs prior-28d mean >= 20 views/day) vs next-week open-to-open return minus SPY, formation every 5th trading day at 5 offsets, signal lag 0 and 1; Newey-West t with 4 Bartlett lags per offset, median across offsets; segments by formation date (2016-07 to 2023-12; 2024-01-08 onward); 500 title-shuffle placebos with fixed seed 20260929; drop list = series with a >90% fall of the 28-day mean views within 90 days; prices through sanitize_price_matrices defaults.

## Stop/Pivot criterion

IC gate (frozen, lag 0 is the gating lag; lag 1 is reported): (a) 2024-01-08-onward weekly RankIC mean > 0 with Newey-West (Bartlett, 4 lags) |t| >= 2.5, (b) 2016-07-to-2023-12 IC mean has the same sign (>0), (c) the real 2024-onward IC exceeds the 95th percentile of 500 title-shuffle placebo ICs. Each statistic is the median across the five weekday rebalance offsets. Any failure -> refuted, no ledger, no candidates. If the gate passes, run the 4 candidates through scripts/screen_batch.py with the K1/K2/watch_recent tiers, DSR and 20 bp. Nothing is changed after results.
