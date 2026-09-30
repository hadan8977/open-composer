# Decision Record: t20260930_11_gap_fade_auction

## Path

gap_fade_auction_pairing (C1): paired official auction price versus daily-bar open/close for the T-20260929-32 gap-fade picks, candidate E_off_T2T3.

## Decision

Stop. Verdict close under the frozen rule: E_off_T2T3 = 7.09 bp/day per unit position < 8 bp (`results.json` `e_off_T2T3_bp`, 90% bootstrap interval [-2.13, 15.96], `verdict` close, `conclusion_status` conclusive). The intraday single-stock gap-fade line is closed at the registered bar. This is the rule's outcome, not a rejection with statistical force: 41.7% of bootstrap draws reach 8 bp (`bootstrap_share_e_off_ge_threshold_reference`, reference only) and the E_bar half of E_off has its own standard error of about 6.4 bp that the interval does not include.

## Reason

- Cause is the thin margin, not the price definition. E_bar (daily bars, all 2024-01-08 to 2026-09-28 picks, T2+T3 pooled by population rows, legs equal weight) is 6.00 bp; the mean paired difference is +1.09 bp (`mean_delta_T2T3_bp`). The official prices barely move the edge: 398 of 400 official opens are the listing-exchange Q print (2 fall back to the listing-exchange O print) and 398 official closes are the listing-exchange M print (2 early-close days have none) (`condition_code_stats`); the close part of the paired difference is 0.0 bp in every cell (`mean_delta_close_bp`), so the whole effect is the open part, concentrated in a few delayed-opening names (Delta quantiles are median 0, p05/p95 of -111/+161 bp in T2 long).
- By cell (`tiers`): T2 long E_off 34.45 bp, T2 short 5.69, T3 long -16.88, T3 short 2.04. Only the T2 long leg is comfortably above 8 bp and its interval is [9.9, 55.8] on 79 usable rows; the other three cells are at or below the bar.
- Missing rates T2 0.6% and T3 0.6% (two early-close days), so no tier is no_conclusion.
- Stress window 2016-05-02 to 2023-08-31, daily bars only: E_bar T2+T3 pooled 10.38 bp (`stress_E_bar_T2T3_pooled_bp`); the older window was better, the recent window is the one that matters and it is below the bar.
- Not measured here and not needed for the verdict: opening-auction impact (Goyal-Jegadeesh-Wu), borrow, fees. They can only lower the 7.09 bp.

## Rejected variants

None added after results. The pairing, the tier and sample sizes, the 8 bp bar and the pooling rule (population row weights, legs equal) were frozen before any official price was fetched; the sample-row-weighted pooling (6.25 bp) is reference only.

## Next iteration suggestion

Do not reopen the daily-turnover single-stock gap fade at a $20M+ liquidity floor. Reopen only with a different holding period long enough to amortize spread, or with a live-fill measurement of auction slippage (the Alpaca paper opening-auction leg is unreliable: 45 of 50 orders expired on 2026-09-15). The closing-auction-only exit variant named in the design is not licensed by this verdict. ML and AI-information round entry conditions are not met.
