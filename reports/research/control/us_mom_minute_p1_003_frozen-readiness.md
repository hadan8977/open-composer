# Momentum Shadow Readiness

Date: 2026-07-13

| Gate | Status | Current evidence |
|---|---|---|
| Frozen StrategySpec | pass | `mom_minute_r2_p1_003`, QQQ to TQQQ, 72/2.5 |
| Research parity | pass | shared position function and route-label tests |
| Observation adapter | pass | stable signal IDs, target weights, no broker writes |
| Fresh shadow data | blocked | latest effective bar 2026-05-29; stale by 1064.5 hours at review |
| Shadow duration | blocked | requires >=20 new trading days and >=30 new intents |
| Fill-quality evidence | blocked | no bid/ask, arrival, VWAP, missed/late fill ledger |
| Gap calibration | blocked | -48.47% local outlier requires adjustment/provenance diagnosis |
| Capacity | blocked | account notional and volume participation evidence absent |
| Cross-source replay | blocked | requires >=60 days, >=95% coverage, >=99% state agreement, 100% direction agreement |
| Alpaca Paper order authorization | blocked | draft/manual/broker none; no authorization artifact |
| ML training | blocked | requires >=800 genuine OOS decisions and rule/linear/LightGBM comparison |

Next action: refresh or append strict QQQ/TQQQ data without changing parameters,
then run `oc strategy shadow-observe` on schedule. Do not optimize against the
new observations.
