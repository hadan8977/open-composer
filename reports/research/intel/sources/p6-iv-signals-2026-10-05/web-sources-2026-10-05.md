# P6 IV signals: web sources read on 2026-10-05 (lead round 13:07, Opus)

Fetched at about 2026-10-05T13:23:51Z with the WebSearch/WebFetch tools (the fetch tool returns a model-extracted page summary; quotes below are what it returned as verbatim abstract text).

## 1. Neuhierl, Tang, Varneskov, Zhou, "Do Option Characteristics Predict the Underlying Stock Returns in the Cross-Section?", Management Science 72(4):2742-2760, April 2026 (SSRN 3795486)

- Query: Neuhierl Tang Varneskov Zhou "Option Characteristics as Cross-Sectional Predictors" stock returns
- Opened: https://ideas.repec.org/a/inm/ormnsc/v72y2026i4p2742-2760.html (abstract page). Full text not read.
- Abstract (as returned): "We provide a comprehensive analysis of option-implied information for predicting the cross-section of stock returns. Based on large sets of firm and option characteristics and using traditional portfolio sorts and modern high-dimensional methods, we find that option information matters. However, in contrast to existing studies, there are only a few option characteristics that have significant incremental predictive power after controlling for the large set of firm characteristics. Further analysis reveals that the strongest option characteristics are associated with asset mispricing, future tail return realizations, and short-selling costs. Our findings are consistent with models of informed trading and limits to arbitrage."
- Use: lowers the prior that IV-RV or IV changes add information beyond a firm-characteristic composite; which characteristics survive is not in the abstract.

## 2. Walter, Zimmer, Ulrich, "Taming the Option Factor Zoo: A High-Dimensional Analysis", arXiv 2609.31263v1, 2026-09-25

- Opened: https://arxiv.org/html/2609.31263v1 (HTML full text, read through the fetch tool's extraction).
- Abstract (as returned): "Option-implied factors are largely, but not entirely, spanned by the equity factor zoo. We construct 137 option-implied characteristics for optionable U.S. stocks from 2004 to 2023, screen them to 20 representative long-short factors, and test each against 160 equity factors with the double-selection LASSO of Feng, Giglio, and Xiu (2020). In-sample, the equity factors account for about 91% of the option factors' variance, and adding the option factors does not significantly raise the maximum Sharpe ratio. Individually, however, 8 of the 20 option factors, mainly measures of jump tails, kurtosis, and implied-volatility convexity, have non-zero SDF loadings after controlling for the equity zoo, and 4 remain significant after a Bonferroni correction. Options thus add a few pricing-relevant dimensions rather than a new factor zoo."
- Bonferroni survivors (Feb 2004-Jul 2023, 234 months, stock returns): ivs_convexity (t 3.92), BTX_EQV_relTail_k (t 3.65), BTX_LJV_7_5 (t 3.59), bakshiKurt (t 3.15). ivs_smirk t -0.88. IV-RV spread, dVolCall/dVolPut and the call-put IV spread are not among the survivors.
- Limitation stated by the authors: "All results are in-sample ... we do not evaluate the selected factors on a hold-out period."
- Use: the surviving dimensions need the full smile (convexity, kurtosis, jump tails), which DoltHub volatility_history cannot give; the T-20261005-33 recorder (two monthly expiries, strikes +-25%) can, forward only.
