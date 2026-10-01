# Risk model v1: validation (design section 6)

Generated 2026-10-01 07:13 UTC by `scripts/validate_equity_book_risk.py`; model files `data/research/equity_book/risk/`; numbers copied from `results.json`.

## 1. Bias statistics (realised / predicted volatility, next 21 sessions)

Portfolios are held at constant weights for the 21 sessions after each month-end. Target band 0.8 - 1.2 on the mean ratio. Random: 100 dollar-neutral portfolios (30 long / 30 short equal weight, drawn from the U3000 cohort) per month-end. Stage 0 books: P1000 deciles, $1 long / $1 short.

| set | window | n | mean | median | rms | in band | share in band |
|---|---|---|---|---|---|---|---|
| random_dollar_neutral | anchor | 3100 | 1.059 | 1.006 | 1.112 | True | 0.58 |
| random_dollar_neutral | gap | 400 | 0.972 | 0.945 | 0.999 | True | 0.62 |
| random_dollar_neutral | stress | 7100 | 1.037 | 0.964 | 1.124 | True | 0.57 |
| random_dollar_neutral | all | 10600 | 1.041 | 0.977 | 1.116 | True | 0.58 |
| stage0_COMP4 | anchor | 31 | 1.345 | 1.281 | 1.398 | False | 0.35 |
| stage0_COMP4 | gap | 4 | 0.878 | 0.845 | 0.893 | True | 0.75 |
| stage0_COMP4 | stress | 71 | 1.132 | 1.025 | 1.191 | True | 0.48 |
| stage0_COMP4 | all | 106 | 1.185 | 1.137 | 1.245 | True | 0.45 |
| stage0_MOM_12_1 | anchor | 31 | 1.344 | 1.256 | 1.390 | False | 0.42 |
| stage0_MOM_12_1 | gap | 4 | 0.999 | 1.041 | 1.014 | True | 0.75 |
| stage0_MOM_12_1 | stress | 71 | 1.145 | 1.094 | 1.204 | True | 0.46 |
| stage0_MOM_12_1 | all | 106 | 1.197 | 1.145 | 1.255 | True | 0.46 |

## 2. Beta prediction (mean absolute realised 21-session beta to SPY)

Stage-0 decile books hedged with SPY so that the predicted beta is zero, one hedge per beta estimator: naive = Stage 0's 252-day OLS beta; ewma63 = exponentially weighted (half-life 63, 252-session window) beta; vasicek = ewma63 shrunk toward the cross-sectional mean (the beta style input); model-implied = `x_i' F x_m / var_m` from the factor model. The brief's target is a mean absolute realised beta < 0.15. `noise floor` = sqrt(2/pi) x the mean standard error of a 21-session beta of the same book, i.e. what a *perfect* hedge would still show.

| signal | window | n | noise floor | unhedged | naive | ewma63 | vasicek | model-implied |
|---|---|---|---|---|---|---|---|---|
| COMP4 | anchor | 31 | 0.394 | 1.273 | 0.611 | 0.547 | 0.667 | 0.824 |
| COMP4 | gap | 4 | 0.219 | 0.232 | 0.168 | 0.175 | 0.178 | 0.195 |
| COMP4 | stress | 71 | 0.296 | 0.626 | 0.412 | 0.396 | 0.396 | 0.412 |
| COMP4 | all | 106 | 0.322 | 0.800 | 0.461 | 0.432 | 0.467 | 0.524 |
| MOM_12_1 | anchor | 31 | 0.483 | 1.293 | 0.787 | 0.707 | 0.809 | 0.923 |
| MOM_12_1 | gap | 4 | 0.313 | 0.344 | 0.291 | 0.285 | 0.299 | 0.304 |
| MOM_12_1 | stress | 71 | 0.387 | 0.795 | 0.546 | 0.532 | 0.542 | 0.572 |
| MOM_12_1 | all | 106 | 0.412 | 0.924 | 0.607 | 0.574 | 0.611 | 0.665 |
| both | anchor | 62 | 0.439 | 1.283 | 0.699 | 0.627 | 0.738 | 0.873 |
| both | gap | 8 | 0.266 | 0.288 | 0.229 | 0.230 | 0.239 | 0.249 |
| both | stress | 142 | 0.341 | 0.710 | 0.479 | 0.464 | 0.469 | 0.492 |
| both | all | 212 | 0.367 | 0.862 | 0.534 | 0.503 | 0.539 | 0.595 |

Signed mean realised beta after the hedge (the bias):

| signal | window | unhedged | naive | ewma63 | vasicek | model-implied |
|---|---|---|---|---|---|---|
| COMP4 | anchor | 1.268 | 0.449 | 0.338 | 0.524 | 0.735 |
| COMP4 | gap | 0.134 | -0.093 | -0.092 | -0.063 | 0.148 |
| COMP4 | stress | -0.014 | -0.004 | -0.013 | 0.010 | -0.007 |
| COMP4 | all | 0.366 | 0.125 | 0.087 | 0.158 | 0.216 |
| MOM_12_1 | anchor | 1.217 | 0.595 | 0.461 | 0.619 | 0.755 |
| MOM_12_1 | gap | 0.018 | -0.239 | -0.188 | -0.184 | 0.065 |
| MOM_12_1 | stress | -0.127 | -0.000 | -0.008 | 0.001 | -0.081 |
| MOM_12_1 | all | 0.271 | 0.165 | 0.122 | 0.175 | 0.169 |
| both | anchor | 1.243 | 0.522 | 0.400 | 0.571 | 0.745 |
| both | gap | 0.076 | -0.166 | -0.140 | -0.124 | 0.107 |
| both | stress | -0.071 | -0.002 | -0.011 | 0.006 | -0.044 |
| both | all | 0.319 | 0.145 | 0.104 | 0.166 | 0.193 |

## 3. Cross-check: residual PCA and variance explained

Correlation-matrix PCA of the model residuals (names with >= 90% coverage in the year) against the same matrix with every column shuffled in time (null). Variance explained = 1 - sum(e^2)/sum(r^2), pooled over the year's name-days.

| year | days | names | var explained | weighted R2 (mean daily) | top1 | top5 | top20 | null top20 | excess top20 |
|---|---|---|---|---|---|---|---|---|---|
| 2017 | 250 | 1962 | 0.206 | 0.165 | 0.029 | 0.093 | 0.239 | 0.133 | 0.106 |
| 2018 | 251 | 1955 | 0.299 | 0.187 | 0.026 | 0.093 | 0.244 | 0.134 | 0.109 |
| 2019 | 252 | 1946 | 0.278 | 0.201 | 0.025 | 0.085 | 0.229 | 0.134 | 0.095 |
| 2020 | 253 | 1797 | 0.494 | 0.263 | 0.045 | 0.179 | 0.399 | 0.136 | 0.264 |
| 2021 | 252 | 1804 | 0.313 | 0.282 | 0.048 | 0.132 | 0.297 | 0.136 | 0.160 |
| 2022 | 251 | 1846 | 0.477 | 0.313 | 0.037 | 0.115 | 0.280 | 0.136 | 0.144 |
| 2023 | 250 | 1949 | 0.306 | 0.212 | 0.029 | 0.096 | 0.253 | 0.134 | 0.119 |
| 2024 | 252 | 1922 | 0.246 | 0.220 | 0.034 | 0.113 | 0.265 | 0.134 | 0.131 |
| 2025 | 250 | 1834 | 0.323 | 0.242 | 0.034 | 0.107 | 0.275 | 0.135 | 0.140 |
| 2026 | 178 | 1820 | 0.324 | 0.314 | 0.037 | 0.132 | 0.319 | 0.174 | 0.145 |

## 4. Runtime and peak memory

- model build: 164 s, peak RSS 985 MB (under `run_capped.sh --mem 1.8G`)
- this validation: 43 s, peak RSS 692 MB
- factors 47 (market, 37 industry groups, 9 styles)

## Notes

- Realised vol = std (ddof 1) of the 21 daily returns of a constant-weight portfolio; names without a price on a day contribute 0.
- Stage-0 books use only names present in the model cohort (U3000 with mcap > 0); mean coverage {'coverage_long': 0.9936638890540272, 'coverage_short': 0.9968371726393194}. Legs are re-equal-weighted over the covered names.
- Model beta is the beta to the cap-weighted U3000 portfolio, used as the SPY beta proxy.
