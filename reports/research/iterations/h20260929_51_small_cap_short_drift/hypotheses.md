# Hypotheses: h20260929_51_small_cap_short_drift

## Hypothesis

A monthly-rebalanced short of a small-cap ETF hedged with trailing-beta SPY has an offset-median Sharpe >= 0.6 in 2024-01-08..2026-09-17 after 10 bp per side and 0.5%/yr borrow, i.e. the 2023-26 small-cap drift is tradable at ETF level; otherwise it is a single-beta benchmark artifact of mega-cap leadership.

## Failure mode

IWM/SPY beta-hedged short Sharpe after borrow < 0.6 in the anchor window, or mirror long placebo not negative, or stress window negative.

## Measurement

Median over all rebalance offsets (21 monthly / 5 weekly) of the after-borrow 10 bp Sharpe in anchor 2024-01-08..2026-09-17, stress 2016-05-02..2023-09-15, select 2023-09-18..2025-12-31; 20 bp CAGR; K2 edge with S3; DSR with 9 trials.

## Stop/Pivot criterion

Anchor median Sharpe of SSD_IWM_M252 after borrow < 0.6: reject the whole direction, no step 2. K1 needs anchor >= 1.1882 and stress >= 0.6447 and positive 20 bp CAGR in both.

## Result (recorded after the run)

H1 refuted: SSD_IWM_M252 anchor median Sharpe after borrow 0.3903 < 0.6, see report.md and results.json.
