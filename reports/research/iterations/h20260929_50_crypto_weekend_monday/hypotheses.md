# Hypotheses: h20260929_50_crypto_weekend_monday

## H1

- Hypothesis: Weekend crypto return W (Friday 16:00 America/New_York to Sunday 24:00 UTC) predicts Monday SPY/QQQ equity returns asymmetrically: the Monday return after W<0 is lower than after W>=0. Source: Mourey, Shahrour, Soiman, Finance Research Letters 86 (2025).
- Failure mode: The difference exists only in the Friday-close to Monday-open gap (priced at the futures reopen and the Monday open before any Monday-open fill), or it is a chance result of about 20 percent of trading days, or it is absent after 2022-06.
- Measurement: Split table on SIP daily SPY/QQQ/IWM: gap, oc (Monday open to close) and o2o (Monday open to Tuesday open) mean differences in bp, Welch t, group sizes; samples 2016-05+, 2022-06+, 2024-01-08+; 500-shuffle placebo (seed 20260929); signals BTC, ETH, equal-weight of available coins among 10.
- Stop/Pivot criterion: Continue to the batch only if one (signal, QQQ or SPY, oc or o2o) cell has W<0 mean below W>=0 mean, |t|>=2.0 and |t| above placebo p90 in both 2022-06+ and 2024-01-08+; otherwise refuted (in the gap and priced before the fill, or no predictive power). Frozen before any result.

## H2

- Hypothesis: The published effect, if it replicates in our data at all, is concentrated in the gap segment, because index futures reopen Sunday 18:00 ET and weekend prices already capture most of the Monday gap (Binance Research: median 92 percent).
- Failure mode: The gap difference is zero or has the wrong sign in our data, in which case the paper's effect does not replicate on these ETFs and windows.
- Measurement: Same table; gap-segment W<0 minus W>=0 mean and t on QQQ and SPY for the 2022-06+ and 2024-01-08+ samples.
- Stop/Pivot criterion: Informational; determines the refutation label (in-gap versus no predictive power) but never enters the continue rule.

## Outcome (appended after the run; preregistration above unchanged)

- H1: not supported for the tradable segments. 0 of 12 gating cells pass; the QQQ/SPY oc and o2o differences are near zero or positive (see decision-record.md and results.json continue_rule).
- H2: supported. The gap difference is -36 to -62 bp with |t| 2.7 to 4.6 in both recent samples for all three signals.
