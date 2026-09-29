# Snapshot: NANC fund methodology (primary source, via WebSearch synthesis)

Intended URL: https://subversiveetfs.com/nanc/ (direct WebFetch to
subversivetrading.com and subversiveetfs.com failed with a DNS/network error
in this sandboxed session; reconstructed via WebSearch, corroborated by
etf.com/NANC, TipRanks and Trackinsight fund pages in the same result set).
Fetched: 2026-09-29T01:54:00+00:00

## Structure
NANC is actively managed, NOT index-tracking. It invests in equity
securities that sitting Democratic members of Congress (or family) have
reported buying, per STOCK Act Periodic Transaction Reports (PTRs). Initial
portfolio uses ~3 years of trailing PTRs.

## Weighting rule
Individual holdings are weighted based on the level of reported trading in a
security by Democratic U.S. Congresspeople, with securities with large
purchases, recurring purchases and purchases from multiple Democratic U.S.
Congresspeople being overweighted. Securities with small purchases, recent
sales and one-off trades by Democratic U.S. Congresspeople are excluded or
underweighted. Options-underlying transactions and pre-term holdings are
excluded.

## Size
Typically 100-200 holdings; TER 0.72%; non-diversified.

## Relevance to this batch
Confirms the fund's own construction is a disclosure-weighted active
strategy, not a price-momentum rule. This batch's rotation_cell mechanism
(cross-sectional price momentum ACROSS the 4 political ETFs, monthly/weekly)
is a second-order overlay on top of each fund's own first-order
disclosure-replica construction -- it tests whether picking among these 4
funds by trend adds anything, not whether the funds' underlying
congressional-copy-trade thesis itself works.
