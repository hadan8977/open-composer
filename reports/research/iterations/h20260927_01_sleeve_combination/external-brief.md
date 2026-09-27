# External brief: H-20260927-01 sleeve combination vs delevered control

## Objective

Test whether combining S1/S2/S3 at a fixed proportion (or trailing inverse-volatility weight) beats delevering S3 alone to the same realized volatility, using the volatility-matched comparison methodology documented in the risk-parity / portable-beta literature.

## Sources (8)

- [industry_standard] https://blog.thinknewfound.com/2017/12/portable-beta-making-returns-youre-already-getting/ (2017-12-04): A levered 60/40 portfolio scaled to match equities' own volatility level beat the S&P 500 on return, because matching risk lets the diversified portfolio's higher risk-efficiency show through.
- [paper] https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Understanding-Risk-Parity.pdf (2010-01-01): By changing the amount of leverage applied to a diversified portfolio, one can construct portfolios of an arbitrary target volatility, making volatility-matched comparison the correct way to judge whether diversification (not just leverage) adds value.
- [paper] https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Leverage-Aversion-and-Risk-Parity.pdf (2012-01-01): A risk-parity (diversified, leverage-adjusted) portfolio realized a 0.27 higher Sharpe ratio than the market portfolio over 1926-2010, a comparison methodology built entirely on matching risk before comparing return.
- [practitioner_perspective] https://www.aqr.com/Insights/Perspectives/Risk-Parity-Why-We-Fight-Lever (2014-09-24): Investors face a choice between levering a diversified portfolio or concentrating in the riskiest asset; the two are the same risk level, so their return should be judged at that matched risk level.
- [industry_standard] https://alphaarchitect.com/digging-deeper-into-adaptive-asset-allocation/ (2015-01-01): Inverse-volatility weighting -- weighting assets or strategies by the reciprocal of their trailing realized volatility -- is a standard, simple way to combine multiple return streams when their expected Sharpe ratios and pairwise correlations are similar.
- [industry_standard] https://alphaarchitect.com/the-performance-of-volatility-managed-portfolios/ (2018-01-01): Volatility targeting reduces exposure when realized volatility rises, which is the same direction of adjustment as inverse-volatility weighting across multiple return streams.
- [paper] https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461 (2013-03-01): A simple tactical asset allocation model combining multiple asset classes achieved equity-like returns with bond-like volatility and drawdowns, evaluated in real time out of sample.
- [industry_standard] https://quantpedia.com/risk-parity-asset-allocation/ (2020-01-01): Risk parity allocates capital so each component contributes equal risk, typically via inverse-volatility or inverse-variance weighting, and is widely used to combine uncorrelated or partially correlated return streams.

## Candidate matrix revisions driven by evidence

- newfound2017_portable_beta_vol_matched_leverage_comparison: Fixed the control design as Ci = k*S3+(1-k)*SHY with k solved per window to match Mi's realized volatility, instead of comparing Mi to S3 at S3's own (higher) risk level, which would make any combination look artificially better just from running at lower average risk.
- alphaarchitect_inverse_volatility_and_quantpedia_risk_parity: Set M3's weight rule to trailing-63-session inverse volatility with an equal-weight fallback for insufficient history, matching established risk-parity/inverse-vol combination practice rather than inventing a bespoke weighting scheme.

## Topic coverage

- volatility_matched_comparison_methodology
- leverage_vs_concentration_equivalence
- risk_parity_diversification_evidence
- inverse_volatility_weighting_precedent
- tactical_multi_asset_combination_precedent
- volatility_targeting_and_vol_managed_portfolios
