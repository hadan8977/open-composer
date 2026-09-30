# Decision Record: h20260929_81_ipo_aftermarket

## P1 ipo_aftermarket_calendar (A: QP-3 to QP+2/+5 long window; B: short after R5 >= +20%; 10 registered candidates)

- Path: IPO aftermarket calendar event study on the T-21 424B4-confirmed non-de-SPAC event table (399 eligible events after price and volume filters), QQQ/IWM equal-weight adjustment, tiered spread and borrow.
- Decision: stop, verdict refuted. IPO aftermarket calendar windows closed (新股日历窗口收口). No keeper, no ledger beyond the 10 event-study rows, no kept.jsonl entry.
- Reason (`results.json` gate_checks): A fails on every numeric condition: pooled net CAR -1.40% (k=2, all pool, clustered t -2.21) and -0.77% (k=5, t -0.98), best ADV top-1,500 pooled net -1.25%; 2024+ n 88 (< 100) with net -3.84% (k=2) and -3.09% (k=5); the QP-2 control is more negative (-2.01%, t -3.47) and random-date placebos are negative, so newly listed stocks lag QQQ/IWM in any window. B: 2024+ 20-session net short +10.55% (all, n 13, t 0.70) and +22.30% (ADV top-1,500, n 6, t 0.96) clear the +3% mean but fail t >= 2 and the leave-out-top-3 test (-11.75%, -22.49%). Mechanism note: mandatory quiet period is a 10-day minimum since 2015-12-24 (FINRA Rule 2241), so day 25 is no longer a rule date; day-11 diagnostic also shows nothing (pooled +0.67%, t 0.92).
- Rejected variants: none added after results. The queue text says 12 candidates; the plan defines 10 (6 A + 4 B) and 12 is kept only as the DSR trial count if a family had passed.
- Next iteration suggestion: do not reopen without an analyst-initiation date feed (test day-25 clustering directly) or offer prices (measure the pop properly). ML and AI-information round entry conditions are not met.
