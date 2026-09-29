# Report: h20260929_02_pre_holiday_etf

T-20260929-02, `dir:pre_holiday_effect_small_cap_tier`. Source: Ariel (1990)
pre-holiday premium; Ko & Yang (2021, full text) find it now survives "only
among small firms" out of sample (1983-2019), with the large-firm premium
"essentially disappeared, especially after 1990". Tested here at the ETF
level: 12 primary candidates `PREHOL_{IWM,IJR,IWC,VB,SPY,QQQ}_H{1,2}` (buy
the last trading day before a federal-market-holiday closure, hold 1 or 2
sessions, else SHY) plus 6 `PREHOL_{ticker}_RAND` per-ticker frequency-
matched placebos, via `scripts/screen_batch.py --batch
h20260929_02_pre_holiday_etf --iteration h20260929_02_pre_holiday_etf`.
Source: `reports/research/screens/h20260929_02_pre_holiday_etf/leaderboard.json`,
`reports/research/iterations/h20260929_02_pre_holiday_etf/results.json`.

## K1 / K2 (primary candidates only)

0 of 12 primary candidates clear K1 (net-10bp anchor Sharpe >=1.1882 and
stress Sharpe >=0.6447, positive 20bp CAGR both windows) or K2 (diversifier
judged_edge >=0.05 both windows, vs a vol-matched S3 control). Every primary
candidate's judged anchor and stress Sharpe is **negative**:

| candidate | anchor Sharpe (10bp) | stress Sharpe (10bp) | K2 edge anchor | K2 edge stress | DSR (n=18, harness) | DSR (n=12, manual) |
|---|---|---|---|---|---|---|
| PREHOL_IWC_H1 | -0.81 | -0.64 | -0.42 | -0.59 | 0.0008 | 0.065 |
| PREHOL_VB_H1 | -1.19 | -0.95 | -0.49 | -0.69 | 0.0001 | 0.047 |
| PREHOL_IWM_H1 | -1.03 | -0.88 | -0.49 | -0.67 | 0.0002 | 0.046 |
| PREHOL_IJR_H1 | -1.30 | -0.95 | -0.57 | -0.70 | 0.0000 | 0.021 |
| PREHOL_SPY_H1 | -1.63 | -1.24 | -0.60 | -0.82 | 0.0000 | 0.019 |
| PREHOL_QQQ_H1 | -1.33 | -1.14 | -0.61 | -0.83 | 0.0000 | 0.018 |
| PREHOL_IWC_H2 | -1.26 | -0.87 | -0.91 | -0.71 | 0.0000 | 0.003 |
| PREHOL_VB_H2 | -1.46 | -1.02 | -0.83 | -0.74 | 0.0000 | 0.003 |
| PREHOL_IWM_H2 | -1.35 | -1.04 | -0.85 | -0.78 | 0.0000 | 0.003 |
| PREHOL_IJR_H2 | -1.64 | -1.03 | -0.93 | -0.76 | 0.0000 | 0.001 |
| PREHOL_SPY_H2 | -1.76 | -0.88 | -0.93 | -0.70 | 0.0000 | 0.001 |
| PREHOL_QQQ_H2 | -1.56 | -0.43 | -1.04 | -0.52 | 0.0000 | 0.001 |

Best-in-class is `PREHOL_IWC_H1` (IWC: iShares Micro-Cap ETF, hold 1
session): anchor Sharpe -0.81, stress Sharpe -0.64, both deeply below the
K1 anchor/stress bars (1.1882 / 0.6447). Its DSR (manual 12-candidate
family, `open_composer.research.campaign_statistics.deflated_sharpe_probability`
on net-10bp anchor daily returns, trial_count=12, hac_lag=5) is 0.065 -- not
close to a publishable/promotable threshold, and this is the *best* of 12.
No candidate reaches `watch_recent` (needs anchor Sharpe >=1.1882 -- none
is even positive).

## Placebo internal falsification

10 of 12 primary candidates have a judged anchor Sharpe **worse than** their
own ticker's `PREHOL_{ticker}_RAND` placebo (e.g. `PREHOL_IWM_H1` -1.03 vs
`PREHOL_IWM_RAND` -0.29; `PREHOL_SPY_H1` -1.63 vs `PREHOL_SPY_RAND` -0.37).
The 2 exceptions (`PREHOL_IWC_H1` -0.81 > `PREHOL_IWC_RAND` -0.92,
`PREHOL_VB_H1` -1.19 > `PREHOL_VB_RAND` -1.25) still fail K1/K2 outright by
a wide margin, so the placebo-demotion rule changes no verdict: every
primary candidate is refuted on K1/K2 alone.

## Small-cap vs large-cap (report only, per direction-review.json)

Source: `results.json`'s `small_cap_vs_large_cap_report_only` field.

| window | small-cap median Sharpe (IWM/IJR/IWC/VB, H1+H2 pooled) | large-cap median Sharpe (SPY/QQQ, H1+H2 pooled) | difference (small - large) |
|---|---|---|---|
| anchor | -1.276 | -1.597 | +0.321 |
| stress | -0.949 | -1.007 | +0.058 |

The small-cap tier's median judged Sharpe is *less negative* than the
large-cap tier's in both windows (+0.32 anchor, +0.06 stress), the same
*direction* as Ko & Yang (2021)'s own small-firm-only pattern. But both
tiers are deeply unprofitable and fail K1/K2 by a wide margin -- this is a
"less bad" relative difference between two failing groups, not evidence of
a tradable small-cap edge. Reported honestly per the preregistered
instruction, but it does not change the refutation verdict.

## Magnitude sanity check (preregistered expectation)

`direction-review.json`'s `target_regime_and_horizon` preregistered that
Sharpe would likely run low given ~9-10 events/year and Ko & Yang's own
0.14-0.37pp single-session premium (1983-2019). The actual result went
further than "low Sharpe" -- it is *negative* across all 18 candidates,
including placebos, in the anchor window. Combined with the near-zero (or
negative) correlation-to-S3 and the low-hundreds trade count per candidate,
the most likely explanation is that being invested for only ~1-2 sessions/
holiday (roughly 5-6% of trading days) captures too little of the market's
generally positive 2024-2026 drift to overcome round-trip cost drag (10bp
per side, ~9-10x/year = ~2bp/year direct cost, small in isolation but the
gross exposure itself is too sparse to generate a positive risk-adjusted
return under this project's next-open-fill convention), not a sign the
pre-holiday mechanism is actively harmful.

## Verdict

**Refuted** (small-cap tier and large-cap tier both). 0/12 primary
candidates clear K1 or K2; the best DSR (12-candidate family) is 0.065.
Ko & Yang (2021)'s small-firm-only out-of-sample *direction* weakly
reproduces at the ETF level (small-cap group less negative than large-cap
group in both windows), but neither tier is anywhere close to tradable
under this project's frozen cost/fill contract. No candidate reaches
`watch_recent`. See `decision-record.md` for the formal stop decision and
`reports/research/harvest/directions.jsonl`'s updated
`dir:pre_holiday_effect_small_cap_tier` row for the registry verdict.

Status separation: `workflow_pass=true`, `research_pass=false` (refuted),
`llm_contribution_pass=false`, `paper_ready_pass=false`. No paper orders,
broker writes, or simulation activity occurred.
