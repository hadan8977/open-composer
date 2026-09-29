# h20260929_70_net_share_issuance report

Question: does net share issuance NSI252 = ln(shares_t / shares_{t-252}) (low issuance long) rank returns in the ADV top-1500 pool (price >= 5), after next-open entry, since 2024?

Result: refuted at the stage-1 IC gate. Source files: `ic_table.json`, `results.json`, `reports/research/signal-cards/net_share_issuance_252{,_h60}.json`, `net_share_issuance_126_control.json`.

| horizon | full mean IC | full NW t | 2024+ mean IC | 2024+ NW t | residual retention 2024+ | NSI126 2024+ IC (NW t) |
|---|---|---|---|---|---|---|
| 20d | 0.0190 | 2.06 | 0.0106 | 0.81 | 1.00 | 0.0083 (0.58) |
| 60d | 0.0329 | 2.13 | 0.0048 | 0.25 | 1.30 | 0.0022 (0.12) |

Continue conditions: 2024+ sign positive (met), 2024+ NW |t| >= 2.0 (not met at either horizon), full-sample same sign (met), distinct_from_controls (met), residual retention >= 50% (met). All must hold at one horizon, so the gate fails. Card flags: predictive false, stable_years false, timely false; beats_shuffle true.

Signal build (`scripts/build_nsi_signal.py`): 6.1M valid 252-session pairs; 564,807 (9.3%) dropped as |dlog| >= ln 1.5, 22,667 by split-like price break, 19,809 by swing-and-return; 5.50M kept. No books, tiers, DSR or borrow tiers were run.
