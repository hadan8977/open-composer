# h20260923_12_s3_defense_first: S3's remainder in Defense First instead of SHY (H-20260923-12)

Verdict: **keep SHY** -- passed: none.

S3 as renewed, unchanged; only the remainder it keeps in SHY moves. Design window 2016-01-04..2023-09-15; anchor 2024-01-08..2026-09-16 is a do-no-harm check; no holdout claim. 10 bp per side on the whole weight vector, 20 bp stress.

S3 first holds risk 2016-05-02. The remainder first leaves SHY on: EW 2016-05-02, DF01 2017-02-01, DF02 2017-02-01. DF00 reproduces the salvage engine and the published 2016-2023 stress replay (CAGR, Sharpe and max DD within 1e-9). No cell applies the 25% drawdown exit; it is an account-level rule outside this comparison.

| cell | rule | design CAGR | design Sharpe | design maxDD | anchor CAGR | anchor maxDD | 20 bp anchor CAGR |
|---|---|---|---|---|---|---|---|
| DF00 | S3 as renewed, remainder in SHY | 30.7% | 0.83 | -48.0% | 116.3% | -32.3% | 113.7% |
| EW | 25/25/25/25 TLT GLD DBC UUP | 32.6% | 0.86 | -45.8% | 122.6% | -32.8% | 120.0% |
| SPY | SPY buy and hold | 12.7% | 0.68 | -33.9% | 20.9% | -18.6% | 20.9% |
| SHY | SHY buy and hold | 0.7% | -0.34 | -5.7% | 3.4% | -1.0% | 3.4% |
| DF01 | Defense First, failing slots to SPY | 35.3% | 0.90 | -49.1% | 131.6% | -32.9% | 128.6% |
| DF02 | Defense First, failing slots to SHY | 33.9% | 0.88 | -46.9% | 127.4% | -32.7% | 124.4% |

| candidate | (a) Sharpe +0.10 | (b) DD not worse | (c) random ranks beaten | (d) > static basket | (e) anchor G1 10/20 bp | pass |
|---|---|---|---|---|---|---|
| DF01 | False | False | 34/40 (median 0.89) | True | True/True | False |
| DF02 | False | True | 40/40 (median 0.86) | True | True/True | False |

Calendar-year returns, 10 bp:

| year | DF00 | EW | SPY | SHY | DF01 | DF02 |
|---|---|---|---|---|---|---|
| 2016 | 74.8% | 73.3% | 13.2% | 0.5% | 74.8% | 74.8% |
| 2017 | 78.1% | 79.0% | 21.7% | 0.3% | 78.7% | 78.0% |
| 2018 | -22.0% | -22.0% | -4.9% | 1.5% | -25.2% | -21.6% |
| 2019 | 35.1% | 40.3% | 31.1% | 3.4% | 37.3% | 35.8% |
| 2020 | 43.6% | 44.7% | 18.1% | 3.0% | 57.9% | 51.7% |
| 2021 | 63.8% | 67.7% | 28.5% | -0.7% | 74.5% | 68.8% |
| 2022 | -33.6% | -31.2% | -18.2% | -3.9% | -25.4% | -26.8% |
| 2023 | 73.2% | 74.9% | 26.3% | 4.2% | 74.7% | 69.2% |
| 2024 | 57.2% | 61.0% | 24.9% | 3.9% | 66.2% | 63.7% |
| 2025 | 129.1% | 131.5% | 18.0% | 4.9% | 146.0% | 139.6% |
| 2026 | 92.6% | 101.3% | 12.2% | 0.3% | 104.0% | 102.3% |
