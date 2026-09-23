# h20260923_11_s3_bear_guard: bear-regime gate on S3 (H-20260923-11)

Verdict: **no guard; keep the 25% exit** -- passed: none.

S3 as renewed, unchanged; a gate moves its risk weight to SHY from the open after a risk-off close. Design window 2016-01-04..2023-09-15 (before any window used to select S3); anchor 2024-01-08..2026-09-16 is a do-no-harm check. The 2026 holdout was already seen for S3: no holdout claim is made. 10 bp per side, 20 bp stress.

| cell | rule | design CAGR | design Sharpe | design maxDD | exposure | time gated | anchor CAGR | anchor maxDD | 20 bp anchor CAGR |
|---|---|---|---|---|---|---|---|---|---|
| BG00 | S3 as renewed, no gate | 30.7% | 0.83 | -48.0% | 0.61 | n/a | 116.3% | -32.3% | 113.7% |
| BG01 | QQQ close < SMA200(QQQ) | 25.6% | 0.74 | -61.1% | 0.59 | 17.9% | 108.0% | -32.3% | 105.5% |
| EM-BG01 | vt scaled | 28.9% | 0.81 | -48.0% | 0.59 | n/a | 109.1% | -30.0% | 106.7% |
| BG02 | SMH close < SMA200(SMH) | 30.9% | 0.85 | -41.1% | 0.59 | 17.7% | 105.4% | -32.3% | 102.4% |
| EM-BG02 | vt scaled | 28.9% | 0.81 | -47.9% | 0.59 | n/a | 109.0% | -30.0% | 106.7% |
| BG03 | HYG/IEF < SMA100(HYG/IEF) | 6.9% | 0.34 | -58.9% | 0.49 | 26.1% | 74.7% | -31.6% | 71.3% |
| EM-BG03 | vt scaled | 23.8% | 0.78 | -44.2% | 0.49 | n/a | 84.8% | -22.8% | 83.0% |
| BG04 | unscaled S3 book equity < its SMA200 | 26.6% | 0.80 | -42.6% | 0.50 | 30.5% | 90.2% | -32.3% | 87.3% |
| EM-BG04 | vt scaled | 24.2% | 0.78 | -44.8% | 0.50 | n/a | 86.9% | -23.4% | 85.1% |

| gate | (a) DD +10pt | (b) Sharpe +0.10 | (c) > exposure match | (d) shifts beaten | (e) anchor G1 10/20 bp | pass |
|---|---|---|---|---|---|---|
| BG01 | False | False | False (c=0.92) | 10/20 | True/True | False |
| BG02 | False | False | True (c=0.92) | 17/20 | True/True | False |
| BG03 | False | False | False (c=0.69) | 1/20 | True/True | False |
| BG04 | False | False | True (c=0.71) | 14/20 | True/True | False |

Calendar-year returns, 10 bp:

| year | BG00 | BG01 | BG02 | BG03 | BG04 |
|---|---|---|---|---|---|
| 2016 | 74.8% | 74.8% | 74.8% | 60.0% | 74.8% |
| 2017 | 78.1% | 78.1% | 78.1% | 36.0% | 78.1% |
| 2018 | -22.0% | -23.6% | -9.6% | -37.2% | -11.3% |
| 2019 | 35.1% | 3.2% | 32.4% | 17.8% | 8.9% |
| 2020 | 43.6% | 43.6% | 43.6% | 42.0% | 13.4% |
| 2021 | 63.8% | 63.8% | 63.8% | 4.0% | 63.8% |
| 2022 | -33.6% | -19.5% | -36.6% | -42.4% | -12.3% |
| 2023 | 73.2% | 40.3% | 61.0% | 37.9% | 32.3% |
| 2024 | 57.2% | 57.2% | 49.3% | 35.6% | 42.3% |
| 2025 | 129.1% | 129.1% | 110.1% | 48.9% | 85.2% |
| 2026 | 92.6% | 73.6% | 92.6% | 94.1% | 83.0% |
