# Report: h20260929_51_small_cap_short_drift (T-20260929-51, step 1)

Question: is 'short small caps, hedge with trailing-beta SPY' (Kargarzadeh et al., arXiv 2608.14014: Sharpe 1.35 gross, 0.78 at 20 bp per side, 2023-2026, no borrow fee) tradable since 2024-01 after 10 bp per side and a 0.5%/yr borrow fee, or a single-beta benchmark artifact?

Source of every number: `reports/research/iterations/h20260929_51_small_cap_short_drift/results.json` (produced by `scripts/run_h20260929_51_small_cap_short_drift.py`, log `logs/t51.log`). Sharpe = overlay excess Sharpe, median over all rebalance offsets (21 monthly, 5 weekly). Windows: anchor 2024-01-08..2026-09-17, stress 2016-05-02..2023-09-15 (shortened to 2017-02..2023-09 for 252-day-beta candidates because `data/sip/daily` starts 2016-01), select 2023-09-18..2025-12-31.

## Verdict: reject; step 2 (stock baskets) not run

Step-1 gate: SSD_IWM_M252 anchor median Sharpe after borrow at 10 bp = 0.3903 < 0.6 (`step1_gate`). No candidate reaches K1 (anchor >= 1.1882 and stress >= 0.6447), K2 (S3 blend edge >= 0.05 in both windows) or watch_recent (anchor >= 1.1882). The mirror-long placebo is negative (anchor -0.484), as expected. Borrow fee lowers the anchor Sharpe by about 0.03-0.07. The paper's stock-level 1.35 is not reproduced at ETF level: the beta-adjusted IWM drift in the anchor is about -0.53%/month against the paper's -0.92%/month for small-cap stocks.

| candidate | anchor Sharpe before/after borrow | stress Sharpe before/after | select Sharpe after | anchor 20bp CAGR | stress 20bp CAGR | anchor max DD | K2 edge anchor/stress | DSR (9 trials) | tier |
|---|---|---|---|---|---|---|---|---|---|
| SSD_IWM_M252 | 0.431 / 0.390 | 0.598 / 0.554 | 0.528 | 4.1% | 5.8% | -17.2% | +0.030 / -0.033 | 0.190 | reject |
| SSD_RSP_M252 | 0.470 / 0.400 | 0.476 / 0.395 | 0.574 | 2.6% | 2.3% | -9.2% | -0.052 / -0.247 | 0.194 | reject |
| SSD_IJR_M252 | 0.626 / 0.585 | 0.448 / 0.409 | 0.719 | 6.6% | 4.5% | -15.7% | +0.019 / -0.116 | 0.289 | reject |
| SSD_XRT_M252 | 0.673 / 0.644 | 0.127 / 0.103 | 0.279 | 9.9% | -0.1% | -15.0% | -0.002 / -0.232 | 0.322 | reject |
| SSD_KRE_M252 | 0.282 / 0.259 | 0.532 / 0.512 | 0.119 | 3.3% | 10.0% | -28.8% | -0.368 / +0.013 | 0.136 | reject |
| SSD_IWM_W252 | 0.443 / 0.403 | 0.614 / 0.571 | 0.521 | 4.2% | 6.0% | -16.9% | +0.034 / -0.007 | 0.196 | reject |
| SSD_IWM_M63 | 0.575 / 0.534 | 0.562 / 0.517 | 0.641 | 5.8% | 5.2% | -14.8% | +0.049 / +0.067 | 0.260 | reject |
| SSD_IWM_M_NOHEDGE | -0.862 / -0.886 | -0.454 / -0.476 | -0.794 | -18.8% | -12.9% | -47.3% | -0.398 / -0.411 | 0.001 | reject |
| SSD_PLACEBO_LONG_IWM_M252 | -0.437 / -0.484 | -0.603 / -0.653 | -0.615 | -6.5% | -7.8% | -21.1% | -0.409 / -0.835 | 0.011 | placebo |

Notes
- XRT/SPY has the highest anchor Sharpe after borrow (0.644) but a stress Sharpe of 0.103 (20 bp CAGR about 0%) and 2023-09..2025-12 Sharpe 0.279; IWM_M63 K2 anchor edge is 0.049 (< 0.05). These are not tiers; the gate is on SSD_IWM_M252.
- Unhedged short IWM is strongly negative (anchor -0.886): the whole positive part of the spread is the SPY-beta hedge, i.e. small caps trailing SPY, not a short-side alpha.
- Weekly (5 offsets) and monthly IWM spreads agree (0.403 vs 0.390), so rebalance timing is not driving the result.
- Borrow assumption 0.5%/yr for ETB index ETFs is preregistered, not a historical quote. Stock-level shorts of small caps would face higher fees (Drechsler and Drechsler; QuantRocket; Verdad), so they cannot beat this ETF-level baseline.
- Unconditional small-cap short baseline for later short-event tests: IWM/SPY beta-hedged short, anchor median Sharpe 0.39 after borrow (0.43 before), IJR/SPY 0.585, RSP/SPY 0.40; stress 0.55 / 0.41 / 0.40.
