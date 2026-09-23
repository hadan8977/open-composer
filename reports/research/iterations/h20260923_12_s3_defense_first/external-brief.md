# External brief: h20260923_12_s3_defense_first

Giants first, on the new question. Moreira and Muir (2017, NBER w22208) and Man Group (2017)
establish that scaling exposure down when realized volatility is high raises Sharpe ratios for
risk assets, with the negative-evidence side (Cederburg et al. 2020; Barroso and Detzel 2021; the
2025 international replication; the 2026 closed-loop preprint) already verified in H-20260922-02.
None of that is re-tested here: it grounds why the S3 vt40+boost overlay -- and therefore the
remainder it produces (1 minus the risk-sleeve weight) -- is itself a defensible, published sizing
mechanism, reused unchanged. This round's own question is what that remainder should be *held in*
while it is not in risk assets.

Thomas Carlson's 2025 SSRN preprint, "Defense First: A Multi-Asset Tactical Model for Adaptive
Downside Protection" (DOI 10.2139/ssrn.5334772), was located and bibliographically confirmed this
pass -- title, author, 2025 date, SSRN Electronic Journal, preprint status -- but its full
abstract and methodology text were not retrievable through the available fetch tooling (both
papers.ssrn.com/sol3/papers.cfm?abstract_id=5334772 and ssrn.com/abstract=5334772 returned 0
chars; only the doi.org redirect rendered a short bibliographic stub). This is different from
h20260923_11's experience fetching Gayed and Bilello's older, more-cached SSRN page in full; not
every SSRN page renders through this tooling. Per this task's own fallback instruction, the exact
rules are therefore pinned from AllocateSmartly's independent, rule-by-rule test of the paper
("Strategy rules tested:", read in full this pass) cross-checked against the author's own LinkedIn
announcement and the Quantitativo replication already logged in this repo's registry (row
dir:defense_first_taa_carlson_concretum, found before this task was scoped). All three agree on
the mechanism shape: rank four defensive assets (TLT, GLD, a commodities ETF, UUP) monthly by a
blended multi-horizon momentum score, weight 40/30/20/10 by rank, screen each asset against a
T-bill momentum hurdle, and replace a failing asset with a fallback. AllocateSmartly is the most
precise on the exact formula (mean of 1/3/6/12-month dividend-adjusted returns) and on rebalance
timing (decide at the last trading day of the month's close, hold to the following month-end,
rebalance unconditionally). One concrete discrepancy surfaced: AllocateSmartly and BestFolio's
replications substitute PDBC for the commodities leg, while the author's own LinkedIn post and
Quantitativo both say DBC. This iteration follows DBC -- the author's own stated ticker, and what
is available in the local SIP daily archive -- and records the difference rather than silently
picking one.

Two independent replicators beyond Quantitativo were found and read this pass. AllocateSmartly
tests the strategy from 1971 and reports benchmark-like returns after ~1980 with better downside
protection and low correlation to other tactical strategies they track. BestFolio's snippet-level
numbers (1986-2026, 10.7% CAGR, 1.15 Sharpe, -20.3% max drawdown) are broadly consistent in shape.
Three independent replicators, three different start dates, all describing the same rule and
landing in the same rough performance neighborhood -- exactly the kind of "reuse fresh verified
knowledge" this project's mission asks for before spending local compute.

What none of this literature or any prior iteration in this repo answers is the only question this
round is designed to settle: on our own frozen S3 remainder specifically (not a standalone
portfolio, not S3's risk sleeve, not a broad ETF universe), at 10 and 20 bp, does redirecting that
remainder into Defense First (DF01 with the paper's own SPY fallback, or DF02 with an SHY fallback
that keeps the remainder free of equity beta) raise the design-window Sharpe and cut the drawdown
by more than a same-cost, momentum-free diversification control (EW, static 25/25/25/25) and 40
random-ranking placebos per candidate (RR-k) would, while still clearing the frozen anchor-window
return bar -- without ever claiming the already-spent 2026 holdout as new evidence. That is what
DF01 and DF02 measure, each independently against DF00, with no ranking between them.
