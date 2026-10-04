# Search Space: h20261004_pm_earnings_beat_odds

One path (`earnings_beat_odds_cross_section`), two preregistered candidates, no parameter search and no model training.

- A1 (primary, decision-eligible): within-week percentile rank of P, the last CLOB Yes price at or before 15:00 ET on the signal day S; long the top tercile and short the bottom tercile each ISO week of the reaction session R.
- A3 (secondary, decision-ineligible): within-week rank of P minus P7 (price seven calendar days earlier); Holm adjustment over A1 and A3.
- Sample: resolved Polymarket earnings events with matched 8-K 2.02 time, SIP close of at least 5 USD on S, contract volume of at least 5000 USD, non-stale price; weeks with fewer than 6 events pooled with the next week of the same season.
- Costs: 10 bp per side, stress 20 bp, 1 percent per year borrow on shorts.
- Statistics: weekly IC mean and t, pooled IC clustered by week, tercile spread gross and net, 1000 within-week shuffles (seed 20261004), three placebos, sub-periods before and from 2026-03-01, minimum detectable effect.
- Continue, stop and inconclusive rules are frozen in `hypotheses.md` and `candidate-manifest.json`. Total budget 2.
