# Decision Record: h20260930_01_rebalancing_front_run

## P1

- Path: `rebalancing_front_run` (8 candidates R1-R8; R1, R2, R7 bond-leg diagnostics).
- Decision: **stop (refuted at the regression gate)**. Direction `dir:pension_rebalancing_front_run_equity_leg` closed as refuted; `dir:index_rebalance_flow_prediction` stays not_executable for its calendar reason and is now also covered by this test.
- Reason: preregistered gate G1-G3 (results.json gate_checks). G1 and G2 pass: SPY open-to-close Threshold coefficient -0.520, HC3 t -2.84 (full sample). G3 fails: in 2024-01-08..2026-09-29 the coefficient is -0.400 but t is -0.84 against the required |t| >= 2.0. The overnight leg is not the source (full t -1.82). Regression-implied gross for an R3-style book is 1.36 bp per day versus 2.47 bp per day of cost at 10 bp per side (informational). No ledger was run, no candidate Sharpe exists, nothing added to kept.jsonl. The SPY-IEF spread diagnostic also fails the anchor bar (t -1.15).
- Next iteration suggestion: none for daily timing. Reopen only with new information, for example a longer live record after 2026-09 showing the Threshold intraday t recovering, or a month-end/quarter-end-only test with a different pre-registered claim (the anchor W and CALMOD intraday t of about 2.0 are post-hoc observations, not evidence). Bond-leg spreads need an owner decision on cross-asset trading before any use.

Status: workflow_pass true, research_pass false, llm_contribution_pass false, paper_ready_pass false. No orders and no paper authorization were touched.
