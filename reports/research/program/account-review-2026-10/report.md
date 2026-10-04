# Account review 2026-10 (T-20261002-30, numbers only, awaiting lead review) generated 2026-10-04T09:56:26Z. Details: account-review.json. Windows: anchor 2024-01-08..09-17, ytd 2026-01-02..09-17, stress_common 2018-02-01..2023-08-31 (the 2016-05 stress window is null for every series except C2). S1-S3 from 2017-02-01, C2 from 2016-02-29, F1/F2 2017-10-04..2026-09-15 (v1.2 realization-dated, lag 2). SIP restated 2026-10-02: stored C2 differs from recompute (max abs 0.010).
## Correlation (daily D / weekly W; rolling-63d median/p90 on anchor daily)
| pair | anchor D | anchor W | ytd D | ytd W | s-common D | s-common W | roll63 med/p90 |
|---|---|---|---|---|---|---|---|
| S1-C2 | 0.66 | 0.69 | 0.43 | 0.31 | 0.74 | 0.72 | 0.74/0.83 |
| S2-S3 | 0.79 | 0.78 | 0.81 | 0.78 | 0.82 | 0.82 | 0.89/0.98 |
| S2-C2 | 0.46 | 0.54 | 0.53 | 0.55 | 0.50 | 0.48 | 0.61/0.74 |
| S3-C2 | 0.44 | 0.52 | 0.47 | 0.57 | 0.42 | 0.42 | 0.54/0.70 |
| S3-F1 | -0.11 | -0.06 | -0.20 | -0.15 | -0.01 | -0.04 | -0.05/0.21 |
| S3-F2 | 0.54 | 0.58 | 0.70 | 0.68 | 0.51 | 0.51 | 0.72/0.83 |
| C2-F2 | 0.77 | 0.79 | 0.65 | 0.64 | 0.89 | 0.88 | 0.81/0.87 |
## Risk (4 sleeves x $15,000, 63d to 2026-09-30): contribution S1 24%, S2 23%, S3 43%, C2 10%; effective bets 3.29; book ann vol 7,256 USD
T-43 weights, 63d to 2026-09-15: S3 89%, C2 7%, F2 4%, F1 -0%; effective bets 1.25
Overlap at 2026-10-02 close (USD, total 59,994): XLK 12,788, TECL 7,636, UPRO 7,544, XLE 7,287, SPY 6,927, SHY 5,349 (XLK held by S1+S2)
## Account Sharpe, combo/same-vol S3 control (10 bp; last col 20 bp anchor)
| combo | anchor | ytd | s-common | 20bp anchor |
|---|---|---|---|---|
| EQ4 | 1.96/1.81 | 2.49/2.13 | 0.52/0.49 | 1.90/1.79 |
| DROP_S1 | 1.97/1.82 | 2.39/2.15 | 0.51/0.49 | 1.92/1.80 |
| DROP_S2 | 1.91/1.82 | 2.57/2.14 | 0.56/0.49 | 1.85/1.79 |
| DROP_S3 | 1.88/1.78 | 2.52/2.03 | 0.45/0.48 | 1.79/1.75 |
| DROP_C2 | 1.91/1.82 | 2.36/2.17 | 0.49/0.49 | 1.87/1.80 |
| IV4 | 2.24/1.79 | 2.64/2.05 | 0.47/0.49 | 2.16/1.77 |
| IV4_F1 | 2.49/1.74 | 2.92/1.85 | 0.33/0.46 | 2.42/1.72 |
| IV4_F2 | 2.13/1.80 | 2.36/2.04 | 0.48/0.49 | 2.07/1.77 |
| T43 | 1.89/1.84 | 2.34/2.20 | 0.54/0.50 | 1.85/1.81 |
EQ4 equal 4 sleeves; DROP_x equal 3; IV4* inverse-63d-vol monthly; T43 S3 .60 C2 .335 F2 .12 F1 .025 borrow .08.
## Joint losses (worst per span; 5 each in JSON)
EQ4 worst_21d: 2020-02-21..2020-03-20 -20.2% (S1 -28.6%, S2 -11.5%, S3 -19.1%, C2 -22.1%)
EQ4 worst_63d: 2020-01-24..2020-04-23 -17.1% (S1 -25.7%, S2 -6.0%, S3 -23.3%, C2 -13.1%)
IV4_F1 worst_21d: 2022-11-29..2022-12-28 -11.8% (S1 -1.5%, S2 +0.1%, S3 -23.9%, C2 -0.5%, F1 +0.7%)
IV4_F1 worst_63d: 2022-11-21..2023-02-22 -10.1% (S1 -5.9%, S2 +0.1%, S3 -8.1%, C2 +1.5%, F1 -0.7%)
## Forward paper vs backtest (first fill..2026-10-02; paper = ledger P&L on SIP closes)
| sleeve | days | cum diff | from day 2 | daily sd | slip bp med/worst | unfilled/part |
|---|---|---|---|---|---|---|
| S1 | 10 | -0.35% | -0.05% | 0.09% | 27.0/65.5 | 0/0 |
| S2 | 10 | -0.76% | -0.16% | 0.24% | 3.4/30.9 | 0/0 |
| S3 | 10 | -1.23% | -3.75% | 1.31% | 8.3/30.9 | 0/0 |
| C2 | 2 (sample too short) | -0.09% | -0.03% | 0.02% | -4.1/2.9 | 0/0 |
S3: backtest held SHY 100% 09-01..09-30 (month-end signal chose cash); paper held UPRO from 09-21; TECL+UPRO in both from 10-01.
