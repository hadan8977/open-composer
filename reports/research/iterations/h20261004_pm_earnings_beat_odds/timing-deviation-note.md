# Timing deviation note (written before any H-A statistic was computed)

Written 2026-10-04 by the T-20261004-51 execution agent (coordinator code R1004-0741-T51).

## What happened

1. The data build followed hypotheses.md literally: `acceptance_utc` from `data/features/earnings_events/` read as US/Eastern wall-clock time. Result: 1054 timed events, 622 in the primary sample.
2. The frozen positive control then failed its gate: weekly-IC t 2.34 (< 3; pooled week-clustered t 3.58). The literal run is kept in `results-literal-timing.json` and `report-literal-timing.md`, verdict `pipeline_suspect`. H-A was not computed.
3. Calibration (P and outcome only, no returns) showed the cause: in the 177 events the literal reading calls "after close", 98.3% have P above 0.97 or below 0.03 at the 15:00 ET cut on S; in intraday and pre-market events the share is 1.3% and 4.8%. The cut was after the outcome was already known, so S was too late.
4. Check against the source: the EDGAR filing-index "Accepted" time (Eastern wall-clock) for 11 filings (GIS, JPM, MU, NKE, AAPL and six sampled by hour, summer and winter) equals the table value minus 8 h in EDT and minus 10 h in EST in every case. The table holds the true UTC instant read as Eastern and converted to UTC a second time. The T-03 finding (Eastern wall-clock) applies to the 10-K submissions data, not to this 8-K table.

## Rule applied from here (the only change to the frozen design)

- Announcement time = the EDGAR filing-index "Accepted" time of the matched accession, fetched for every matched accession at no more than 4 requests per second; where EDGAR returns nothing, the formula "undo the double shift" is used and flagged. The ±2 calendar day match, the 09:30/16:00 ET classification, S, R, P, P7, sample filters, statistics, gates, shuffles and costs are unchanged.
- The control gate uses the same statistic (weekly-IC t >= 3) on the corrected table.
- I did not look at any return grouped by P, P7 or A3 under either reading. The only returns computed so far are the positive control (beat vs excess return) and its cuts by timing kind, period and exit variant, all in `results-literal-timing.json`.

## For the lead

This is a deviation from the literal wording of hypotheses.md, made because the literal reading leaks the outcome into P. The lead decides whether the corrected run counts as the frozen test. If not, the literal result stands as `pipeline_suspect`.
