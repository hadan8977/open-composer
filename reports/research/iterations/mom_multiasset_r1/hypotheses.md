# Hypotheses: mom_multiasset_r1

## H1
- Hypothesis: ETF absolute and relative momentum can improve drawdown-adjusted performance over static QQQ/SPY exposure after costs.
- Failure mode: Whipsaw in sideways regimes or cash gating misses rebounds.
- Measurement: Four chronological folds, BIL/SPY/QQQ and equal-weight ETF benchmarks, 5/10/20 bps one-way costs.
- Stop/Pivot criterion: Stop if both recent folds are negative and OOS Sharpe and maximum drawdown are not better than the benchmark family.

## H2
- Hypothesis: Risk-adjusted six/twelve-month sector rotation with a buffer is more stable than raw short-window sector ROC.
- Failure mode: Sector leadership reverses faster than monthly rebalance or the score concentrates in one macro regime.
- Measurement: Rank IC/ICIR, turnover, top-2/top-3 portfolio OOS metrics and sector equal-weight benchmark.
- Stop/Pivot criterion: Pivot if score IC is unstable but portfolio risk improves; stop if cost-adjusted OOS alpha and ICIR are both non-positive.

## H3
- Hypothesis: A liquid large/mid-cap long-only stock portfolio using six- and twelve-month momentum can outperform an equal-weight frozen universe after realistic costs.
- Failure mode: Survivorship bias, crowding, concentration and turnover erase gross continuation.
- Measurement: Current-universe exploratory history plus frozen-universe forward virtual paper; compare SPY, equal-weight universe and ex-post best symbol.
- Stop/Pivot criterion: Historical results cannot earn research_pass without PIT membership; stop the method if forward rank IC and portfolio alpha remain negative through the observation contract.

## H4
- Hypothesis: 52-week-high proximity and trend consistency add incremental information beyond raw 6/12-month return.
- Failure mode: The factors duplicate momentum or over-select extended, high-volatility stocks.
- Measurement: Single-factor and grouped ablations, cross-sectional correlation, rank IC, drawdown and turnover.
- Stop/Pivot criterion: Stop the factor group if marginal ICIR and cost-adjusted portfolio lift are non-positive in at least three of four folds.

## H5
- Hypothesis: Residual or sector-relative momentum reduces market and industry concentration while preserving stock-selection alpha.
- Failure mode: Noisy beta/sector estimates or missing sector mappings destabilize ranks.
- Measurement: Exposure attribution, sector caps, residual rank IC, OOS IR versus raw momentum.
- Stop/Pivot criterion: Pivot to simple sector-relative ranks if residual estimation is unstable; stop if concentration falls but net performance deteriorates materially.

## H6
- Hypothesis: Strategy-specific ML ranking, downside-risk and sizing roles can add marginal lift after deterministic factors survive.
- Failure mode: Date leakage, symbol memorization, small effective sample, probability miscalibration and regime overfit.
- Measurement: Date-grouped nested chronological CV, 21-day purge/embargo, IC/ICIR, calibration, 3/4 fold lift and cost-adjusted portfolio attribution.
- Stop/Pivot criterion: Keep models diagnostic unless they beat the matched deterministic strategy in at least three of four folds without worsening drawdown or turnover beyond the registered limits.
