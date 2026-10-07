# Library batch 1 leaderboard (T-20261006-18)

Base v1.2 M0_U3000, recent window 2024-01-08..2026-09-17, five-offset blend: Sharpe over BIL 1.11, net without BIL subtraction 1.51.

## Stock factors (19 computed + 6 data-insufficient)

| first-batch id | label | IC recent (NW t) | net Sharpe U3000 / P1000 (recent) | FF5 alpha t (recent) | Delta Sharpe w0.5 / w1 / w2 / merge | MDE 80% | coverage |
|---|---|---|---|---|---|---|---|
| osap-ReturnSkew | 未到深度 | +0.013 (1.0) | -0.08 / -0.31 | -1.2 | +0.03 / +0.03 / -0.02 / -0.01 | 0.29 | 100% |
| osap-BetaTailRisk | 不成立（近期窗口） | +0.014 (0.4) | -1.21 / -1.09 | -1.8 | -0.00 / -0.02 / -0.13 / -0.06 | 0.45 | 86% |
| osap-GrAdExp | 未到深度 | +0.012 (1.5) | 0.23 / 0.57 | 0.1 | +0.03 / +0.06 / +0.09 / +0.05 | 0.13 | 28% |
| osap-RDAbility | 未到深度 | -0.017 (-0.9) | -0.92 / -0.63 | -3.6 | -0.01 / -0.01 / -0.03 / +0.00 | 0.05 | 6% |
| osap-OrgCap | 不成立（近期窗口） | -0.019 (-2.1) | -2.42 / -1.23 | -2.3 | -0.02 / -0.04 / -0.12 / -0.00 | 0.17 | 40% |
| osap-IntMom | 未到深度 | +0.042 (2.5) | 0.43 / -0.02 | 1.8 | +0.08 / +0.13 / +0.14 / +0.01 | 0.66 | 100% |
| osap-InvGrowth | 不成立（近期窗口） | -0.010 (-1.3) | -0.79 / -0.04 | -0.6 | -0.02 / -0.04 / -0.08 / -0.00 | 0.15 | 35% |
| osap-Cash | 未到深度 | -0.007 (-0.4) | -1.08 / -0.58 | -1.0 | +0.06 / +0.09 / +0.15 / +0.04 | 0.4 | 73% |
| osap-PctAcc | 未到深度 | +0.003 (0.3) | -1.01 / -0.29 | -1.3 | +0.00 / -0.02 / -0.07 / +0.01 | 0.22 | 82% |
| osap-ChTax | 不成立（近期窗口） | +0.006 (0.9) | -1.25 / -1.31 | -0.4 | -0.02 / -0.05 / -0.15 / -0.02 | 0.23 | 77% |
| osap-OPLeverage | 未到深度 | +0.007 (0.8) | -0.63 / -0.21 | 0.3 | +0.00 / -0.00 / -0.05 / +0.01 | 0.21 | 56% |
| osap-ChEQ | 未到深度 | -0.001 (-0.1) | -0.42 / 0.52 | -0.6 | +0.00 / -0.00 / -0.08 / +0.02 | 0.33 | 77% |
| osap-roaq | 未到深度 | +0.025 (1.5) | 0.92 / 0.15 | 1.1 | +0.01 / +0.00 / -0.01 / +0.01 | 0.22 | 81% |
| osap-MomOffSeason06YrPlus | 未到深度 | -0.002 (-0.2) | -0.66 / 0.25 | -1.0 | +0.00 / -0.01 / -0.06 / +0.01 | 0.19 | 76% |
| osap-MomSeason06YrPlus | 未到深度 | -0.012 (-0.7) | -2.11 / -2.38 | -3.9 | -0.03 / -0.06 / -0.16 / -0.01 | 0.2 | 73% |
| osap-CompositeDebtIssuance | 未到深度 | +0.001 (0.2) | -0.69 / 0.53 | -0.5 | -0.01 / -0.02 / -0.04 / +0.01 | 0.11 | 36% |
| osap-BPEBM | 未到深度 | +0.007 (0.6) | -1.01 / -0.79 | -0.6 | +0.01 / +0.01 / -0.00 / -0.04 | 0.18 | 72% |
| osap-EBM | 未到深度 | +0.018 (1.4) | -0.50 / -0.54 | -1.0 | -0.01 / -0.04 / -0.12 / +0.00 | 0.29 | 72% |
| qc-standardized-unexpected-earnings | 未到深度 | +0.019 (2.4) | 0.18 / -0.05 | 1.2 | +0.01 / +0.01 / -0.01 / +0.01 | 0.2 | 66% |
| osap-ReturnSkew3F | 数据不足 | - | - | - | - | - | Fama-French daily factors mktrf/smb/hml (only monthly FF5 and industry files are local) |
| osap-EarningsStreak | 数据不足 | - | - | - | - | - | IBES analyst consensus mean estimate and announcement dates (no analyst-estimate data local) |
| osap-MomOffSeason16YrPlus | 数据不足 | - | - | - | - | - | monthly returns 16-20 years back (need prices from 1996-2010; local history starts 2016) |
| osap-MomSeason11YrPlus | 数据不足 | - | - | - | - | - | monthly returns 11-15 years back (need prices from 2001-2015; local history starts 2016) |
| osap-MomSeason16YrPlus | 数据不足 | - | - | - | - | - | monthly returns 16-20 years back (need prices from 1996-2010; local history starts 2016) |
| osap-ConvDebt | 数据不足 | - | - | - | - | - | Compustat dc (deferred charges) and cshrc (shares reserved for conversion); no comparable XBRL tag, a convertible-note tag would be a different signal |

## ETF and calendar rules (primary member)

| first-batch id | label | primary | anchor Sharpe 10bp / 20bp | edge vs vol-matched S3 | DSR (63 trials) | circular-shift placebo | stress V4 veto |
|---|---|---|---|---|---|---|---|
| qc-option-expiration-week-effect | 不成立（近期窗口） | OPEX_SPY_WEEK | -0.62 / -1.34 | -0.56 | 0.0 | 0.225 | False |
| qc-pre-holiday-effect | 不成立（近期窗口） | PREHOL_SPY_H1 | -1.63 / -2.70 | -0.61 | 0.0 | 0.25 | True |
| qc-turn-of-the-month-in-equity-indexes | 不成立（近期窗口） | TOM_SPY_H4 | -0.65 / -1.20 | -0.68 | 0.0 | 0.24 | False |
| qc-the-dynamic-breakout-ii-strategy | 未到深度 | DYNBRK_SPY | 0.07 / -0.14 | -0.63 | 0.01 | 0.25 | True |
| qc-ichimoku-clouds-in-the-energy-sector | 未到深度 | ICHI_XLE | 0.12 / 0.03 | -0.09 | 0.02 | 0.225 | True |
| qc-capm-alpha-ranking-strategy-on-dow-30-companies | 数据不足 | CAPM_TOP2 | - | - | - | - | - |
| qc-january-barometer | 未到深度 | JANBAR_SPY | 1.04 / 1.04 | -0.05 | 0.25 | 0.77 | False |
| qc-can-crude-oil-predict-equity-returns | 未到深度 | OILEQ_USO | 0.67 / 0.62 | -0.16 | 0.1 | 0.36 | False |
