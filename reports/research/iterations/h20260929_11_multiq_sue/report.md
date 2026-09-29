# Report: h20260929_11_multiq_sue (T-20260929-11)

Sources: `reports/research/screens/h20260929_11_multiq_sue/leaderboard.json` (screen_lane, commit of the batch module 73e99f4, n_trials=8), `results.json`, `model-fits.json`, `price-hygiene.json` in this directory.

## Verdict

**Refuted. No keep-eligible candidate clears K1, K2 or watch_recent, and the increment criterion fails for all three.** ENET_TOP50: anchor median-offset net-10bp Sharpe 0.60 (K1 needs 1.1882), stress (2019-01..2023-09 only) 0.38 (needs 0.6447), K2 edge -0.11 / -0.29 (needs +0.05 both), DSR 0.32. The model did not beat the single-quarter SUE baseline (0.88), the 12-1 momentum baseline (1.10) or the label-shuffle placebo (0.68); it beat only the random-pick placebo (0.51).

## Candidates (median over 21 monthly offsets, net 10bp unless noted)

| id | anchor Sharpe | stress Sharpe (2019+) | select Sharpe | net-20bp CAGR anchor / stress (median offset) | K2 edge anchor / stress | DSR anchor (n=8) | corr S3 anchor |
|---|---|---|---|---|---|---|---|
| ENET_TOP50 | 0.60 | 0.38 | 0.65 | 11.7% / 6.6% | -0.11 / -0.29 | 0.32 | 0.34 |
| ENET_TOP20 | 0.37 | 0.47 | 0.42 | 8.4% / 9.4% | -0.33 / -0.25 | 0.19 | 0.41 |
| ENET_MOM_TOP50 | 0.83 | 0.32 | 0.64 | 18.6% / 4.9% | -0.17 / -0.34 | 0.46 | 0.61 |
| SUE1_TOP50 | 0.88 | 0.59 | 0.71 | 16.6% / 12.4% | 0.04 / -0.20 | 0.49 | 0.43 |
| MOM12_1_TOP50 | 1.10 | 0.43 | 0.91 | 32.9% / 8.5% | -0.15 / -0.31 | 0.63 | 0.66 |
| EW_POOL | 0.72 | 0.55 | 0.68 | 14.4% / 12.2% | -0.01 / -0.20 | 0.39 | 0.34 |
| RAND_TOP50 | 0.51 | 0.50 | 0.48 | 8.8% / 8.6% | -0.10 / -0.23 | 0.27 | 0.31 |
| ENET_SHUF_TOP50 | 0.68 | 0.36 | 0.72 | 11.7% / 5.7% | -0.03 / -0.30 | 0.36 | 0.32 |

All candidates trade only from 2019-01-02 (first out-of-sample score); "stress sample short": the stress window is 2019-01..2023-09, not 2016-05..2023-09.

## Increment criterion for ENET_TOP50 (anchor median Sharpe strictly greater than)

| comparator | ENET_TOP50 | comparator value | ENET_TOP50 greater |
|---|---|---|---|
| SUE1_TOP50 | 0.60 | 0.88 | False |
| MOM12_1_TOP50 | 0.60 | 1.10 | False |
| ENET_SHUF_TOP50 | 0.60 | 0.68 | False |
| RAND_TOP50 | 0.60 | 0.51 | True |

increment_criterion = False. ENET_TOP20 and ENET_MOM_TOP50 also fail (see results.json verdicts).

## Model fits and monthly RankIC (score vs open[t+22]/open[t+1]-1, month-ends of the test year)

| test year | train rows | alpha / l1_ratio | nonzero coefs | ENET RankIC | SUE1 RankIC | MOM12-1 RankIC |
|---|---|---|---|---|---|---|
| 2019 | 11285 | 0.1 / 0.1 | 0 | n/a | 0.0137 (t 0.45) | -0.0131 (t -0.15) |
| 2020 | 16222 | 0.1 / 0.1 | 0 | n/a | -0.0234 (t -0.60) | -0.0145 (t -0.21) |
| 2021 | 21806 | 0.003 / 0.5 | 3 | 0.0023 (t 0.05) | -0.0144 (t -0.46) | -0.0911 (t -1.53) |
| 2022 | 27094 | 0.003 / 0.5 | 2 | -0.0132 (t -0.64) | 0.0097 (t 0.43) | 0.0048 (t 0.06) |
| 2023 | 32081 | 0.003 / 0.5 | 0 | n/a | 0.0361 (t 1.52) | 0.0513 (t 0.91) |
| 2024 | 37672 | 0.01 / 0.1 | 4 | 0.0297 (t 0.79) | 0.0254 (t 1.08) | 0.0628 (t 1.29) |
| 2025 | 43357 | 0.001 / 0.9 | 4 | -0.0474 (t -1.28) | 0.0058 (t 0.28) | -0.0293 (t -0.56) |
| 2026 | 49615 | 0.003 / 0.5 | 0 | n/a | -0.0085 (t -0.32) | 0.0113 (t 0.18) |

ENET RankIC 2019-2023: 24 months, mean -0.0055, t -0.21; 2024+: 24 months, mean -0.0089, t -0.33. SUE1: 2019-2023 60 months, mean 0.0043, t 0.33; 2024+ 31 months, mean 0.0101, t 0.77. MOM12-1: 2019-2023 60 months, mean -0.0125, t -0.40; 2024+ 31 months, mean 0.0155, t 0.50.
Years with an all-zero coefficient vector (constant score, RankIC undefined, months not counted above; ties broken by the seeded random key, i.e. the model behaves like a random pick): 2019, 2020, 2023, 2026. The cross-validated elastic net therefore found no usable SUE-history signal in 4 of 8 years and only a handful of nonzero coefficients (sue_rev_lag1, sue_rev_lag5, sue_eps_lag5/6) in the others; the 2021-2022 and 2024-2025 IC values are indistinguishable from zero.

## Beta and alpha (ENET_TOP50, anchor window 2024-01-08..2026-09-17, average of all 21 offsets, net 10bp, excess of BIL)

SPY: beta 0.79, alpha -4.0%/yr (t -0.87), correlation 0.86. QQQ: beta 0.51, alpha -1.5%/yr (t -0.25), correlation 0.73. Correlation with S3 (anchor, judged offset): 0.34. DSR with n_trials=9 (adds ENET_LS): 0.30.

## ENET_LS (information only, offset 0, 10bp/side, 0.5%/yr borrow, top-50 long / bottom-50 short)

anchor: annualized net return -4.2%, net Sharpe -0.46 (gross -0.22), 31 months; stress (2019-2023): -4.5%, net Sharpe -0.56 (gross -0.16), 56 months. Not part of K1/K2.

## Data and caveats

- Pool: point-in-time S&P 500 (fja05680 membership), 736 tickers with prices; prices passed `sanitize_price_matrices` defaults (62 breaks, 32 symbols masked, 22623 price cells blanked; renamed or reused tickers such as FB lose their pre-break history, so early pool coverage is incomplete). Signal-day split-like exclusion applied; residual unadjusted 2:1 splits inside holding windows are not removed.
- SUE events are visible from the first session after the 10-Q/10-K filing (after the press release), history starts 2016, so early lags are missing and the model trains on 29 to 114 months.
- The primary paper's full text was not readable (403), so the label horizon, cost treatment and out-of-sample design of the original are unverified; this test used the project's frozen contract. The Wang et al. OR Spectrum 2025 paper was not found.
- Tie rule for constant scores (random per-month key) was fixed before the batch ran, after the scores step had shown that some years' models are all-zero.
