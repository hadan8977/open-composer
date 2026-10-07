# Decision Record: t20261006_18_library_batch1_lane

## Path

etf_calendar_rules_library_batch1

## Decision

stop for this batch: no ETF or calendar rule reaches the incubation proxy (P1-style); no paper sleeve is proposed. OPEX_SPY_WEEK, PREHOL_SPY_H1 and TOM_SPY_H4 are unfounded in the recent window only; DYNBRK, ICHI, JANBAR and OILEQ are not at depth (33 months, minimum detectable Sharpe about 1.5); CAPM alpha ranking is data-insufficient (point-in-time top-30 names that were delisted are missing from the local daily data).

## Reason

63 trials under the lane contract (next open, 10/20 bp, excess over BIL, vol-matched S3 control, circular-shift placebo). Best primary: JANBAR_SPY anchor Sharpe 1.04, edge over the control -0.05, DSR 0.25, placebo 0.77. Details in the main dossier's report.md, lane-results.json and leaderboard.md.

## Next iteration suggestion

Revisit only with new members and more recent months, not as the same rules; obtain delisted-stock daily prices to run the CAPM ranking.
