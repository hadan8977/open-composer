# Step 9 Wave 9.0 Paper Alignment Blocked

- Date: 2026-07-09
- Strategy: `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate`
- Status: blocked
- Blocking condition: Alpaca Paper rejected the supervised alignment order because the LOO/OPG order was submitted outside Alpaca's OPG submission window.
- Evidence: `reports/paper/daily_cycle/20260709.json`
- Broker message: `opg orders must be submitted after 7:00pm and before 9:28am`
- Completed before block: readiness artifacts, source cards, execution policy, gap stress, leveraged ETF risk note, paper safety review, router order authorization, daily-cycle allow flag selection, remediation enforcement code, and focused tests.
- Required next action: rerun `uv run python scripts/run_daily_paper_cycle.py` inside the Alpaca Paper OPG submission window; then run `uv run oc paper validation-report` and confirm the next counted trading day passes without `state_drift_warning`.
- Scope guard: no live-money broker writes were enabled; authorization scope remains `alpaca_paper_only`.
