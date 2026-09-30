# Decision Record: t20260930_16_overnight_lo20_execution

## P1

- Path: ON252_P500_LO20 overnight-only book, paper-executable path (15:59 buy at the ask, next-day 09:31 sell at the bid) and its K1/K2/DSR ledger.
- Decision: Stop, cancelled before any data was fetched (lead review, 19:07 UTC round, 2026-09-30).
- Reason: the precondition written at 13:25 ("gate_a、gate_b 都过就把 T-16 改成 ready……任一不过就把 T-16 标 cancelled") failed. T-20260930-14 `results.json` has `gate_b` false: delta_lo20 -5.88 bp/night against a -4 bp bar; the standard error across the 20 seed days is 2.18 bp (lead check). See `t20260930_14_overnight_persistence_12m/decision-record.md`. No stage A quote request and no ledger number exist for this iteration.
- Next iteration suggestion: none on this line. The overnight single-stock path is closed with T-14. ML and AI-information round entry conditions are not met.
