# External brief: h20260922_04_rsi_branch

Machine-readable version with all eight sources and their reflections is in
`external-brief.json`. Direction receipt, snapshots and verified claim bindings
are in `direction-review.json`, `sources/` and
`reports/harness/source_cards/h20260922_04_rsi_branch.jsonl`.

## What the giants actually published

Two public Composer symphonies run the same rule tree and both carry an
out-of-sample line on their own pages. Snapshots taken 2026-09-22:

| Strategy | Headline (includes in-sample) | Out-of-sample line on the same page |
|---|---|---|
| Sector Rotator MS (CMS update 2025-09-08) | 134.72% annualized, Sharpe 1.7, since 2019-10-30 | ~98% annualized, Sharpe ~1.44, Calmar ~3.37, max drawdown ~29% |
| Portfolio Experiment: Volatility Minimization | 116.11% annualized, Sharpe 3.52, since 2022-04-13 | ~43.7% annualized, Sharpe ~1.92, Calmar ~2.90, max drawdown ~15.1% |

Intel card I-20260922-02 quoted the headlines. The out-of-sample lines are the
honest target and are what this iteration is measured against.

## The rule is not secret

The Sector Rotator page states the whole tree in plain English: it scans the 11
US sector ETFs daily, a 10-day RSI above 80 on a sector sends the book to UVXY,
an RSI below 30 buys a short-term rebound in that sector, and otherwise it holds
the month's strongest sector, in either the 1x or the 3x version. So RSI window,
both thresholds and the hedge asset are given; nothing about them needs to be
searched, and searching them would convert a replication into a fit.

## What the academic literature contributes, and what it does not

Industry momentum (Moskowitz-Grinblatt 1999) is the published mechanism for the
normal branch, but its evidence is at 1-12 month horizons, not the 21 days used
here. Dual momentum (Antonacci) is the closest published structure to a
branch-gated rotation, and its public trackers earn 10-15% annualized -- two
orders below the platform headlines, with the gap being leverage and window
selection. Volatility-managed portfolios (Moreira-Muir, NBER w22208 / JF 2017)
give the economic case for cutting exposure when the market is stretched, but
RSI > 80 is a price-extreme proxy rather than a volatility measure, so this
iteration neither tests nor supports that literature; candidate B-2 does.
Quantpedia's 2026-08 sectoral momentum cycle puts a pure sector ranking at about
6% annualized at Sharpe 0.55, and SSRN 5095447 puts a long-sample cross-asset
ETF rotation at Sharpe ~0.5 over 2007-2026.

Read together: if this replication produces 50%+ annualized, essentially all of
it has to be coming from leverage and from the branch tree, because the ranking
mechanism on its own is worth single digits. That is the statement the two
placebos are designed to confirm or destroy.

## Execution reality of the hedge leg

ProShares states UVXY seeks 1.5x the daily performance of its benchmark for a
single day and that compounding makes longer holds diverge significantly from
that target. The overheat branch holds it for whole sessions, so the report has
to show how many days it was held and what it actually contributed rather than
assuming a VIX ETF is protection.

## Known limits carried into round 1

The original computes RSI per sector; the preregistered proxy computes it on a
single index, which fires the branch less often. The original buys the
washed-out sector itself when oversold; this fixes that branch to TQQQ. Composer
lists winners only and lets authors reset the out-of-sample start after editing
a recipe, so none of the published numbers count as live evidence. The whole
evaluation window is a bull market.
