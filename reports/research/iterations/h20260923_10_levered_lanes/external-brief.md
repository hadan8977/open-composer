# External brief: h20260923_10_levered_lanes

Giants first, on the new question. Moskowitz and Grinblatt (Journal of Finance, 1999) showed
that industry components of stock returns carry a strong, prevalent momentum effect that
explains much of individual-stock momentum: buying past-winning industries and selling
past-losing industries is highly profitable even after controlling for size, book-to-market,
individual momentum and microstructure effects. That is the economic reason a second trending
industry is a defensible bet rather than an ETF pick chosen after seeing its own backtest.
Locally, I-20260923-01 (a first-party computation on Ken French's official 49-industry files,
methodology verified in this round) ranks Gold, Chips, Banks and Aero as the top four
select-window (2023-09-18..2025-12-31) value-weighted industries; Chips is already the live S3
book, so Gold, Banks and Aero (mapped to NUGT/JNUG, FAS/DPST, and DFEN) are the natural second
bets.

The overlay this round reuses, unchanged, is the same Moreira-Muir-style volatility target plus
QQQ-oversold dip boost already authorized for the live S3 book (H-20260923-09: 116.3% anchor
return, -32.3% max drawdown, Sharpe 1.82 anchor, holdout Sharpe 2.21) -- its own giants
(Moreira-Muir 2017, Man Group 2017) and negative evidence (Cederburg et al. 2020, Barroso and
Detzel 2021, the 2025 international replication) were verified in H-20260922-02 and are reused
here rather than re-fetched, because the overlay's own parameters are not being changed or
re-tested.

What is new here is instrument-level: Hsieh et al. (arXiv 2504.20116, April 2025) show that
leveraged-ETF compounding depends on return autocorrelation and return dynamics, not only
volatility drag -- trending regimes enhance daily-rebalanced LETF returns, mean reversion hurts
them. That is the mechanism behind H-20260923-09's own finding that the live S3 book's return is
concentrated in trending SOXL+USD (58.5% anchor / 69.4% holdout average weight) rather than
coming from menu diversification, and it is why this round tests industries with their own
independent trend driver instead of assuming any leveraged sector ETF would compound the same
way. Direxion's own product pages for DPST and NUGT/DUST confirm, in the issuer's own words,
that each fund's 200%/300% objective holds for a single day only and should not be expected to
hold over multi-day periods -- the daily-reset caveat that the spec's notes and the eventual
report must carry for every lane, not only for the ETFs already in the live book.

What none of this literature answers is the only question this round is designed to settle: on
our own frozen overlay machine, on our recent windows, with 10 and 20 bp per side and next-open
fills, does any of NUGT, JNUG, FAS, DPST or DFEN clear the same gates the live S3 book cleared,
survive the pool-rank and calendar-shift placebos, and stay weakly correlated (<=0.5) with that
live book on the anchor window. That is what the five preregistered candidates measure, with no
ranking or selection among them.
