# External brief: H-20260928-02 cross-asset trend sleeve vs delevered S3 control

## Objective

Test whether adding one cross-asset defensive-trend sleeve (D1 Carlson Defense First TAA, D2 12-month-vs-SHY absolute momentum with inverse-63-session-vol sizing) to S3, combined by trailing-63-session inverse-volatility monthly weighting, beats delevering S3 alone to the same realized volatility on Sharpe, in both the anchor and stress windows.

## Sources (8)

- [paper] https://doi.org/10.2139/ssrn.5334772 (2025-01-01): Carlson (2025) 'Defense First' is a 2025 SSRN preprint; primary text not retrievable, rules pinned from independent replications.
- [industry_standard] https://allocatesmartly.com/carlsons-defense-first/ (2025-07-20): Defense First's exact momentum definition, rank-weight table (40/30/20/10) and BIL hurdle / SPY fallback rule.
- [industry_standard] https://www.linkedin.com/posts/thomasdcarlson_defense-first-a-multi-asset-tactical-model-activity-7349155637907333120-INqK (2025-07-10): Author's own confirmation of the TLT/GLD/DBC/UUP menu and SPY fallback.
- [industry_standard] https://www.quantitativo.com/p/from-defense-to-offense-a-tactical (2025-07-26): Second independent replication of Defense First; triangulates the mechanism is real.
- [paper] https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum (2012-05-01): Moskowitz, Ooi and Pedersen (2012) document time-series momentum across 58 futures/forward contracts, grounding D2's own-asset absolute-momentum mechanism.
- [paper] https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing (2017-10-31): Hurst, Ooi and Pedersen (2017) extend trend-following evidence to 1880-2016, motivating the full stress-period and 2022-correlation reporting.
- [industry_standard] https://alphaarchitect.com/digging-deeper-into-adaptive-asset-allocation/ (2015-01-01): Inverse-volatility weighting precedent for D2's sizing rule and the S3+D combination weight.
- [industry_standard] https://blog.thinknewfound.com/2017/12/portable-beta-making-returns-youre-already-getting/ (2017-12-04): Volatility-matched-comparison methodology precedent, reused from H-20260927-01 for the vol-matched delevered-S3 control.

## Candidate matrix revisions driven by evidence

- carlson_defense_first_rank_weights_allocatesmartly: D1 uses Carlson's published rank weights (40/30/20/10), momentum blend (1/3/6/12-month), BIL hurdle and SPY fallback unchanged, generalized to evaluate at any signal date so the 21 rebalance-day offsets can each be swept without look-ahead.
- moskowitz_ooi_pedersen_2012_time_series_momentum: D2's rule uses the queue task's stated round-number thresholds, not tuned to this paper's own parameters; the paper only grounds the mechanism as peer-reviewed.

## Topic coverage

- defense_first_taa_published_rules
- time_series_momentum_academic_evidence
- century_scale_trend_following_evidence
- cross_asset_defensive_basket_precedent
- volatility_matched_combination_methodology_reuse
- inverse_volatility_sizing_precedent
