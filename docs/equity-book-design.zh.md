# Multi-signal equity book: frozen v1 design

This is the English operational rendering of the 2026-10-01 design: mathematical framework, module interfaces, preregistered grid and success gates. It does not create a new experiment or change the frozen study. Sections 9-10 were fixed at 2026-10-01 06:32 UTC before Stage 2 results; changes require a separate contract. Stage 0 used already-observed history for diagnosis and design, not acceptance.

Evidence: [program review](../reports/research/program/review-2026-10-01.zh.md), [external evidence](../reports/research/intel/pro-equity-evidence-2026-10-01.md), [tool investigation](../reports/research/intel/pro-equity-2026-10-01.md), [Stage 0 diagnostics](../reports/research/program/stage0-hedged-books-2026-10-01/), and [the research program](research-program.zh.md). Provider terms, costs and capability claims below are the study's documented assumptions, not freshly verified current account rules.

## 0. Economic context retained from the design

The cited systematic long/short fund evidence had net Sharpe median 0.51, 75th percentile 0.87 and 90th percentile 1.18 (AQR/HFR, 1996-2023). JKMP's 2022 Portfolio-ML study reported 1.38 under a large-cap, $10B, impact-only, 1981-2020 setup; Chen-Velikov reported about 4 bp/month after costs for anomalies published after 2005. These contexts motivated a 0.5-1.0 book expectation, not a promise or a replacement for owner goals.

The original mental K2 calculation was corrected on 2026-10-01. Synthetic 5%-volatility, zero-S3-correlation books evaluated by the actual `screen_lane` K2 function required approximately 0.75 stress-period Sharpe under frozen accounting (0.85 cash-aligned), versus 0.13 benchmark-window Sharpe (0.26 cash-aligned). Earlier 0.69/0.41 estimates were wrong, including reversed window interpretation. Inverse-volatility combination weights and SHY-versus-BIL cash accounting matter. The preregistration recorded an approximately 8% pass prior; K1 was not the expected route. Calibrate gate difficulty with the actual code rather than mental algebra.

Stage 0 found weak liquid P1000 hedged books: an eight-book equal-risk combination had benchmark/stress Sharpe 0.58/-0.23; model books had 1.1-1.3/-0.4 to -0.6. Stronger ADV-rank 1001-3000 results largely came from shorting dilutive microcaps, whose short legs lagged SPY by 200-440 bp/month without adequate borrow modeling. This was not credible executable alpha. A 252-day beta hedge still realized beta 0.5-0.9, while simple top-N long books exceeded beta 2: a proper risk model and exposure attribution were necessary.

## 1. Product and financing structure

Let equity be E, long equity exposure L, absolute short exposure S (stocks/ETFs), and short-bond ETF exposure Q (SGOV/BIL). Frozen Alpaca assumptions from the cited 2026-09-17 documentation:

- Overnight Reg T: `L + S + Q <= 2E`, 50% initial margin.
- Cash balance: `C = E - L - Q + S`; negative cash accrues at 6.5%/360 daily (Elite 5.0%).
- Positive cash and short proceeds earn zero in this model.

The zero-financing layout is `L = S <= 0.5E`, `Q = E`, so `C = 0`, total exposure 2E and excess return approximately `0.5 * (r_L - r_S)`. A 100/100 long/short book leaves no bond allocation and has non-interest-bearing short cash; its opportunity cost is about rf. Therefore the long/short sleeve's gross is fixed at 1.0E.

| Form | Structure and role |
|---|---|
| F1 neutral | 0.5E long, 0.5E short, 1.0E short bonds; about 5% annual volatility. Research acceptance uses F1. |
| F2 core plus overlay | Replace the bond allocation with 1.0E SPY; derives from F1 rather than receiving separate acceptance. |
| F1b ETF hedge | Short only SPY/IWM/IJR/sector SPDRs; tests the value available without single-stock borrow. The design assumed easy-to-borrow ETFs at zero broker fee, subject to the modeled cushion below. |

Shorts must be whole shares under the cited 2025-09-24 fractional-share terms. Round optimized holdings and enforce the single-name whole-share affordability limit in section 8. Reverify current rules before a new adaptation; do not rewrite this study's accounting retrospectively.

## 2. Universe and information clock

- `U3000_t`: latest `universe_broad` month-end at or before t, `adv_rank <= 3000`, close at least $5, not `is_probable_fund_or_etf`, at least 252 sessions of history.
- `P1000_t`: U3000 members with `adv_rank <= 1000`; report separately.
- Short-eligibility proxy `SE_t`: `adv_rank <= 2000`, price at least $10, no reverse-split-like open/previous-close ratio in 252 sessions, and short-interest/share ratio outside the top 5% where available. D7 calibrates against dated Alpaca `easy_to_borrow` flags and reports false eligibility; forward use takes that day's actual flag.
- FF48 industry mapping: `data/features/sic_map/sic_map.parquet`. Prefer `date_verified`; otherwise flag use of the latest mapping (the design reported 99.1% P1000 coverage). Industries with fewer than five members merge into the corresponding FF12 group.
- Decide after t close using only data visible by that close. Fundamentals become usable from the session after filing, matching the intended `sec_fundamentals_daily` alignment.

The price/PIT caveats in [the data inventory](data-layer-pitfalls-and-capabilities.zh.md) still apply; a declared timing rule is not proof that every stored feature satisfies it.

## 3. Return accounting (D2 reference)

Use `daily_broad` open/close with Alpaca `adjustment=all`; SPY comes from `data/sip/daily`. Dividends are embedded in adjusted prices, credited long and paid short. Stage 0 checked AAPL against SIP source values.

Signals at t close fill at t+1 open (the daily opening price is the first trade); test t+1 close as a timing sensitivity. Non-rebalance holdings drift close-to-close. On a rebalance date, drift old holdings from prior close to open, trade at open and deduct costs, then drift new holdings open-to-close. Produce session-indexed daily returns compatible with S3 and `screen_lane.diversifier_edge_for_offset`.

Delisting exits use the last valid close. Sensitivity adds -30% for delisted longs (Shumway's performance-delisting scale), zero additional adjustment for shorts; report the difference.

The implementation's meaningful acceptance cases are: SPY-only equals SPY close-to-close; a two-stock rebalance agrees with hand accounting; cash/bonds/margin match section 1; and forward labels equal realized returns for the identical trade. The last mismatch invalidated H-20260929-12.

## 4. Signal library v1 (S1)

Each signal records its timing source, formula, literature direction and coverage. At each date inside U3000: winsorize at 1%/99%, rank-normalize, demean value/quality signals within FF48, then fill missing scores with zero.

| Theme | Inputs/formula | Direction |
|---|---|---|
| Value | `bm`, `ep`, `sp`, `cfp`: equity, annual net income, revenue and operating cash flow divided by market cap (`close * shares_outstanding`) from `sec_fundamentals_daily`. | Positive |
| Quality/profitability | `gp_at`, `roe`, `op_at`, negative accruals. | Positive |
| Investment/issuance | Negative `asset_growth` from `sec_fundamentals_daily`, negative `nsi_12m` from `nsi`. | Positive |
| Momentum | `mom_12_1`, FF48 equal-weight `ind_mom_12_1`, and `resid_mom_12_1`: cumulative market/industry residual return divided by residual volatility (Blitz et al.). | Positive |
| Low risk | Negative shrunk `beta_252`, negative `idio_vol_63` from `daily_broad`. | Positive |
| Earnings | `sue_eps`, `sue_rev` from `sec_fundamentals_daily`. | Positive |
| Insider | `cmp_opportunistic_buy_60d`, `net_buy_usd_nonplan_60d / market_cap` from `insider_broad` (Cohen-Malloy-Pomorski). | Positive |
| Short information | Negative `short_volume_ratio_mean_21` from `short_volume_broad`, negative short interest/shares from `short_interest` (recorded coverage 1,816 names). | Positive |
| Seasonality | Mean return in the same calendar month over five prior years (Heston-Sadka). | Positive |
| Fast signals, ML only | Industry-adjusted 21-day reversal, ON252, selected alpha101/191 columns, news attention from 2024. | Learned |

The cited evidence favored slow signals after costs: value, quality, momentum and investment/issuance. Reversal/overnight signals stay outside equal-theme M0 and enter models where costs determine usefulness.

## 5. Target and combination models

Target: next-21-session residual return, `r_(i,t+1 -> t+22)` open-to-open, less risk-factor contribution using t exposures and realized holding-period factor returns.

| Model | Frozen specification |
|---|---|
| M0 | Average signals within each theme, then equal-weight themes with fixed directions; required matched baseline. |
| M1 | Rolling 60-month IC weighting using Fama-MacBeth on the residual target; weight proportional to mean IC / IC standard deviation, negative values clipped to zero; one-month gap. |
| M2 | LightGBM/XGBoost/CatBoost ensemble; all features including fast signals; cross-sectional rank of residual return as target; annual retraining with at least 21-session separation; reuse the T-17 pipeline. |
| M3 | Random-Fourier-feature ridge (DKKM/JKMP/AQR 2024): about 100 inputs expanded to P=4,000 features; validation selects ridge penalty from `{10^-3, ..., 10^3}`. |

Expected returns use Grinold-Kahn scaling: `alpha_i = IC * sigma_res_i * score_i`. Shrink trailing 36-month realized IC halfway toward 0.03; residual sigma is the risk model's 21-day estimate.

`ml_contribution_pass` requires M2 or M3 to beat M0 net portfolio Sharpe in both windows with the same data, costs and construction. The original design planned Modal execution for M2/M3; current compute routing follows the existing admitted resource policy without changing these scientific definitions.

## 6. Risk model (D3)

A simplified in-repo Barra-style implementation avoids the measured skfolio memory cost (1.38 GB for 1,000 x 1,500 with three factors); use skfolio only as a cross-check.

- Daily WLS on U3000 close-to-close returns, weighted by square-root market cap. Factors: market, FF48 industries merged to about 30 with a cap-weighted zero-sum constraint, and styles.
- Styles: size, beta, 12-1 momentum, 63-session residual volatility, liquidity, `bm`, `gp_at`, `asset_growth`, 21-day reversal. Winsorize exposures at +/-3, cap-weighted mean zero, equal-weight standard deviation one.
- Factor covariance: EWMA variance half-life 126 days, correlation half-life 252 days, Newey-West lag 2.
- Specific variance: residual-square EWMA half-life 63 days, 0.3 shrinkage toward size-decile mean, with a floor.
- Write annual parquet blocks: rebalance-date X/F/D, plus daily factor returns f and residuals e; do not retain the entire history in memory.

Acceptance: realized/predicted volatility between 0.8 and 1.2 for random and optimized books, reported by window; mean absolute next-21-session realized beta below 0.15 after predicted-beta neutralization; residual 20-factor PCA cross-check.

## 7. Costs and financing (D4)

Calibrate half-spreads from historical Alpaca NBBO using the valid-quote rules in `scripts/run_t20260930_15_quote_check.py`. Sample 60 random sessions in 2018-2026, 30 names per liquidity decile, at 09:35-09:45, noon and 15:45. Fit `log(hs) = a + b*log(price) + c*log(dollar_ADV) + d*log(volatility) + year_effect`, with separate open-period coefficients. Do not use daily Abdi-Ranaldo spread estimates shown to overstate spreads 20-60x (#58 in the data inventory).

Impact: `delta = Y * daily_sigma * sqrt(Q/V)`, `Y=0.5` (Toth-Bouchaud/FIM 2018 scale), mainly a capacity measure at this size. Fees use 0.5 bp per side as a cushion over the cited roughly 0.3 bp SEC/TAF sell-side rate. These are frozen modeling assumptions, not current fee verification.

Borrow inside `SE_t` costs 25 bp/year despite the then-assumed zero easy-to-borrow broker charge; outside `SE_t` stock shorts are forbidden. Stress all shorts at 100 bp/year. Financing follows section 1 (`C=0` for F1/F2). Also report the frozen fixed 10/20 bp-per-side cost views for comparison with older results.

## 8. Optimizer (D5)

Use cvxpy/Clarabel with a custom loop; the recorded 1,500-name full-constraint solve used about one second and 150 MB peak.

```text
max_w alpha'w - (gamma/2) * [w'XFX'w + sum_i D_i*w_i^2]
      - sum_i [hs_i*abs(delta_w_i) + imp_i*abs(delta_w_i)^(3/2)]
      - sum_i borrow_i*max(-w_i, 0)*h/252

delta_w = w - w0; w0 is the drifted previous portfolio.
```

F1 constraints:

| Constraint | Frozen bound |
|---|---|
| Dollar neutral, including ETF hedges | `sum(w)=0` |
| Predicted beta | `abs(beta'w) <= 0.02` |
| Each industry | Absolute exposure <=0.01 |
| Size / other styles | Absolute exposure <=0.10 / <=0.25 |
| Single name / long-short gross | 1% E / 1.0 E |
| Short eligibility | `SE_t` stocks or hedge ETFs; F1b permits only ETFs |
| Whole-share short affordability | Price <=0.01E; at E=$100,000, price <=$1,000 for at least one share |
| Participation at E=$1 million | Order <=1% ADV |
| Ex-ante risk budget | `w' Sigma w <= 0.05^2 / 252`, fixing annual volatility at 5% rather than hand-tuning gamma |

Rebalance weekly, report all five weekday offsets and decide by their median. Daily small-step trading is a later variant with roughly five times the compute. On solver failure, hold the prior portfolio, log the failure and report the failure rate.

## 9. Frozen Stage 2 grid

Twelve variants: four combination models (M0/M1/M2/M3) times three universe/short branches, all weekly:

- A: U3000, `SE_t` stock shorts plus ETF shorts.
- B: U3000, ETF shorts only (F1b).
- C: P1000 only.

Fixed: risk model v1, cost model v1, ex-ante volatility 5%, long/short gross 1.0, single-name 1%.

| Partition | Frozen dates and interpretation |
|---|---|
| Stress | 2017-10-02 through 2023-08-31; common start for every model. |
| Gap | September-December 2023, reported separately. |
| Benchmark window | 2024-01-08 through 2026-09-17. |
| Forward | From 2026-09-18. January through September 17, 2026 had already been repeatedly observed and is contaminated holdout. |

DSR trial exposure is `12 + 65 Stage 0 cells = 77`. Preserve the historical exposure and partition status.

## 10. Frozen acceptance gates

For each variant, judge the median across offsets. `research_pass` requires a retention route and every necessary condition below. Use modeled costs aligned with the existing retention accounting in [the autonomous-round runbook](runbook-autonomous-round.zh.md); cleanup does not replace these gates with newer generic thresholds.

| Retention route | Required result |
|---|---|
| K1 | Benchmark-window net Sharpe >=1.19 and stress >=0.65; positive annual excess return in both windows at 2x costs. |
| K2 | Combined with S3, Sharpe improvement over same-volatility S3 >=0.05 in both windows; >=0.10 is strong retention. |

All necessary conditions:

- Within-date shuffled-alpha placebo, 100 seeds and identical construction: win fraction >=0.95 over October 2017-September 2026 and >=0.80 separately in stress and benchmark windows.
- F1 realized beta in `[-0.15, 0.15]` in both windows.
- Optimizer failure rate strictly below 2%.
- Annual excess return strictly positive in both windows at 2x costs.

Judge `ml_contribution_pass` separately using section 5. If no variant passes, retain infrastructure and mark this frozen v1 book negative; the original next step is the signal expansion in section 12, not tuning this grid after its results.

## 11. Forward shadow and paper boundary

The design's forward pipeline generates next-session targets and signal logs before 23:05, records that day's Alpaca borrow flags, and books next-open shadow fills. Reuse the existing scheduled route rather than adding a new crontab.

After 20 forward sessions without engineering failure, the design calls for an owner paper proposal specifying new-sleeve budget, short authority, and fractional/whole-share handling. Paper remains an execution rehearsal below the existing G1-G5 promotion contract; this design does not authorize an account, orders or a renewal.

## 12. Later layers, outside the frozen grid

Preregister timing variants and accept them only for incremental forward portfolio Sharpe: market-state momentum exposure (Daniel-Moskowitz 2016), factor-momentum theme weights and crowding reductions. Retain the named stress periods: March/November 2020, 2025-01-27, April/June-July/October 2025, June/August 2026.

Text candidates are 10-K/10-Q changes (Lazy Prices, Cohen-Malloy-Nguyen 2020, EDGAR) and 8-K/news model scoring. The historical DeepSeek five-hour rolling quota is not current access or authority; DS remains subject to current owner controls. Cost-aware Portfolio-ML is a later smaller-scale candidate (about 100 features, 1,500 names), not admitted by documenting it here.

## 13. Modules and data interface

Implementation lives in `open_composer/research/equity_book/`; meaningful behavior checks belong with each affected module.

| Work package | Module | Dependency |
|---|---|---|
| D1 industry map | `scripts/build_sec_sic_map.py` | Recorded complete in the original design. |
| D2 panel/returns/backtest/evaluation | `panel.py`, `returns.py`, `backtest.py`, `evaluate.py` | D1 |
| D3 risk | `risk.py` | D2 panel |
| D4 costs | `costs.py` plus quote sampling | Independent input work |
| D5 optimizer | `optimize.py` | D3/D4 |
| D6 forward shadow | `shadow.py` | D2-D5 |
| D7 borrow proxy | `borrow.py` | Read-only Alpaca assets |
| S1 signals | `signals.py` | D2 |

D2's shared wide-panel interface is date x symbol in annual parquet: open, close, tradable flag, U3000/P1000/SE membership, industry, market cap and dollar ADV. Use the capped-job wrapper for reads; choose the allowance from [the memory budget](runbook-memory.zh.md), rather than copying the original fixed 1.8G request to every task.
