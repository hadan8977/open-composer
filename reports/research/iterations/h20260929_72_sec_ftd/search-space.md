# Search Space: h20260929_72_sec_ftd

One path, `ftd_book_screen`, 4 candidate books (limit 24), built only if the stage-1 IC gate passes.

- Signals: FTDSH = fails / PIT cover-page shares; FTDADV = fails x price / 21-session dollar ADV. Balance of each file's last settlement date, absent = 0, PIT-usable from the first session after the file cutoff (a-file: after month end; b-file: after the 16th of the next month), held at most 25 sessions. Sign preregistered: high FTD -> lower return.
- Portfolios: avoid the top decile inside the ADV top-1500 (price >= 5) equal-weight pool; short the top decile inside ADV top 500 with a 252d SPY beta hedge (easy-to-borrow proxy).
- Rebalance: monthly (21 offsets), median across offsets decides. Costs 10/20 bp per side, borrow 3%/yr on the short leg.
- Stage-1 IC gate: signal_card rank cards (20d, 60d, `--lag 0` because availability is already in the dates) + scripts/ftd_ic_test.py (Newey-West t); books skipped if it fails. FTD>0 dummy is a control, not a candidate.
