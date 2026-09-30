# Report: h20260930_03_tax_loss_year_end

Task T-20260930-03 (coordinator code R0930-0707-TL). Design frozen in `hypotheses.md` before any
result; numbers below are copied from `results.json` (script
`scripts/run_h20260930_03_tax_loss_year_end.py`, log `logs/h20260930_03.log`, 105 s, run under
`scripts/run_capped.sh --mem 1.2G` and the shared lock).

## Verdict

**refuted -- "tax-loss rebound closed"** (`results.json` -> `verdict`). 0 of 6 candidates pass all
five frozen continue conditions; no candidate passes the +1.5% mean condition or the t >= 2 condition.
`workflow_pass` true; `research_pass` false; no ledger, no paper, no threshold change.

## Ten-window results, net of ADV-tiered costs, excess versus the equal-weight pool

Source: `results.json` -> `candidates.<id>` (`stats`, `recent_windows`, `placebo_*`, `iwm_hedged_stats`,
`failed_conditions`). Conditions: c1 mean >= +1.5%, c2 >= 7 of 10 positive years, c3 year-clustered t >= 2,
c4 placebo sum <= half of the real mean, c5 Dec 2024 and Dec 2025 both positive.

| candidate | mean net excess | t (10 years) | positive years | mean w/o best year | Dec 2024 / Dec 2025 | Feb / Jun placebo mean | placebo sum | IWM-hedged mean | failed |
|---|---|---|---|---|---|---|---|---|---|
| D10_A_X0115 | +0.54% | 0.47 | 7/10 | -0.01% | -0.24% / +0.98% | -1.30% / -0.27% | -1.57% | +0.91% | c1, c3, c5 |
| D10_A_X0131 | -0.31% | -0.19 | 5/10 | -1.26% | -1.03% / -1.91% | -0.64% / -0.16% | -0.80% | +0.65% | c1, c2, c3, c4, c5 |
| D10_B_X0115 | +0.60% | 0.48 | 7/10 | -0.04% | -0.47% / +2.18% | -1.42% / -0.60% | -2.01% | +1.15% | c1, c3, c5 |
| D10_B_X0131 | -0.15% | -0.10 | 5/10 | -1.03% | -0.57% / -0.24% | -0.66% / -0.51% | -1.16% | +0.76% | c1, c2, c3, c4, c5 |
| L30_A_X0115 | +0.94% | 0.69 | 7/10 | +0.30% | -0.25% / +1.99% | -1.16% / -1.58% | -2.74% | +1.31% | c1, c3, c5 |
| L30_A_X0131 | -0.67% | -0.43 | 5/10 | -1.37% | -0.61% / -0.69% | -3.94% / -1.78% | -5.72% | +0.28% | c1, c2, c3, c4, c5 |

Annual net excess (`candidates.<id>.annual_net_excess`, signal year; year Y = 15 Dec Y -> January Y+1):

| candidate | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|
| D10_A_X0115 | +1.79% | +4.03% | +5.46% | +1.32% | +0.25% | -7.89% | +1.46% | -1.75% | -0.24% | +0.98% |
| D10_A_X0131 | +0.86% | +0.23% | +7.01% | -3.90% | +0.28% | -8.22% | +8.25% | -4.64% | -1.03% | -1.91% |
| D10_B_X0115 | +1.35% | +3.92% | +6.33% | +1.06% | +0.21% | -8.92% | +1.32% | -0.97% | -0.47% | +2.18% |
| D10_B_X0131 | +0.90% | +0.61% | +7.73% | -5.16% | +1.67% | -9.00% | +6.65% | -4.14% | -0.57% | -0.24% |
| L30_A_X0115 | +1.78% | +6.73% | +4.35% | +3.25% | +2.14% | -8.43% | +1.56% | -3.73% | -0.25% | +1.99% |
| L30_A_X0131 | +0.14% | +1.29% | +5.63% | -3.54% | +2.09% | -8.76% | +5.59% | -7.88% | -0.61% | -0.69% |

Baskets are about 10% of the pool (`tables.W2.X31.D10_A`, selected/pool by year: 2016: 148/1474, 2017: 149/1488, 2018: 149/1489, 2019: 149/1487, 2020: 143/1426, 2021: 148/1473, 2022: 148/1479, 2023: 148/1477, 2024: 147/1468, 2025: 146/1459).

## Diagnostic window W1 (15 Nov -> 15 Dec), direction only

Source: `results.json` -> `w1_diagnostic`. Expected: losers underperform the pool.

| shape | gross excess mean | net excess mean | positive years (net) | direction |
|---|---|---|---|---|
| D10_A | +0.55% | +0.40% | 6/10 | does not underperform pool |
| D10_B | +0.19% | +0.01% | 6/10 | does not underperform pool |
| L30_A | +1.13% | +0.97% | 6/10 | does not underperform pool |

The expected mid-November to mid-December underperformance of year-to-date losers is not present in this
sample (gross excess is positive for all three shapes), so the tax-loss-selling pressure pattern that
motivates the December entry is not visible in prices here either.

## Sensitivities (not verdict inputs)

- Nine-year cut 2017-2025 (drops the 2016 window whose YTD baseline is the 2016-01-04 open; `sensitivity_2017_2025_stats`):

| candidate | mean net excess | t |
|---|---|---|
| D10_A_X0115 | +0.40% | 0.32 |
| D10_A_X0131 | -0.43% | -0.25 |
| D10_B_X0115 | +0.52% | 0.37 |
| D10_B_X0131 | -0.27% | -0.15 |
| L30_A_X0115 | +0.85% | 0.56 |
| L30_A_X0131 | -0.76% | -0.44 |

- IWM-hedged means and t are in `iwm_hedged_stats` / `iwm_hedged_annual` (best: L30_A_X0115 +1.31%, t 1.02); none reaches t 2.
- Gross (pre-cost) mean excess: `gross_excess_stats` (X0115 candidates +0.70% to +1.10%, X0131 candidates -0.52% to +0.03%); costs are 14-19 bp of the window return (`tables.W2.*.*.cost`) and are not what closes the direction.
- Registry text says placebo windows "average at most half"; the queue plan (used) says the sum. Averages are in `placebo_average`; the verdict is unchanged either way (c1 and c3 fail for every candidate).

## What drove the result

- The 31 January window (the plan's primary) has a negative mean for all three shapes, 5 positive years of 10, and negative Dec 2024 and Dec 2025 for every 31 January candidate.
- The 15 January window is mildly positive on average (+0.5% to +0.9%) but the mean is carried by 2017-2018 and falls to about zero (D10) or +0.3% (L30) after removing the best year; 2021 is -8% to -9% (December 2021 losers kept falling), 2023 negative, Dec 2024 negative.
- The February and June placebo means are negative for every candidate, so seasonal specificity is not what fails; the effect size is simply too small and inconsistent.

## Caveats and data notes

- Data start 2016-01-04: the 2016 YTD baseline is the 2016-01-04 open (proxy, flagged). Valid universe per window 2,233-3,747 stocks (`per_year_meta.<y>.pool_counts.*.n_valid_universe`); pool sizes after hygiene 1,426-1,498.
- Hygiene: `sanitize_price_matrices` defaults per one-year segment (`per_year_meta.<y>.hygiene`), plus removal of symbols with a split-like one-day close ratio between baseline and exit (`n_split_like_excluded`, 2-74 names per window over all years), applied to pool and baskets alike.
- Stocks that stop printing before the exit use the last valid close (`n_early_term_in_pool`, 0-5 per window); no delisting-loss information beyond that.
- ADV pool from daily bars (median close x volume, 21 sessions); costs are the T-21 stylised tiers (3/6/12 bp per side), not measured spreads; the benchmark pool is costless, which is conservative for the baskets.
- Ten annual observations per candidate, six candidates: even a pass would have been a low-power recent observation. This result is a clean negative for the frozen design; it does not test illiquid stocks outside the ADV top 1,500 (Kaul et al. 2025 point there) or a short side (not authorized/borrow not checked).

## Status

`workflow_pass` true; `research_pass` false; `llm_contribution_pass` n/a; `ml_contribution_pass` n/a; `paper_ready_pass` false. No forward-tracking task is created (verdict is refuted; the registry decision belongs to the coordinator).
