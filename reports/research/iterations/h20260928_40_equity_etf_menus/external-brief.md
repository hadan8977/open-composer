# External Brief: h20260928_40_equity_etf_menus

Eight sources ground this batch. Two are fresh WebFetch reads this session
(Quantpedia's FACTOR-menu mechanism description; an attempted, blocked read of
Molchanov & Stangl's sector-rotation counter-evidence). One is reused,
unmodified, from a prior verified source card in this repository (Antonacci's
dual-momentum absolute-momentum-filter mechanism, the same family as
`rotation_cell`'s own absolute-momentum-vs-SHY filter). Three are carried
forward from the pre-existing direction registry entries for both menus
(iShares factor-rotation post, d/rksci sector-rotation post, a GitHub
replication repo), not independently re-fetched this session. Two are fresh
factsheet-level confirmations (via stockanalysis.com, since the issuers' own
product pages returned HTTP 403 or redirect-looped) that MTUM and SMH are
real, liquid, long-only, US-listed ETFs representative of each menu.

No source grounds a new momentum formula, weighting scheme, or absolute-
momentum rule -- every candidate in this batch reuses
`run_h20260918_05_recent_menu.py:rotation_cell`'s mechanism unedited, imported
directly rather than reimplemented, so the lookback-return definition is
guaranteed identical to S1-S3's own live engine. The only new degrees of
freedom are the two menus (ticker lists) and the preregistered
lookback/top_n/rebalance grid, which was fixed before any backtest ran.
