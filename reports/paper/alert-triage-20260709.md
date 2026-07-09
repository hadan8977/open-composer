# Paper Alert Triage: 2026-07-09

- Strategy: `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate`
- Scope: Step 8.0 operational baseline refresh.
- Paper order authorization: not granted; runner remains observation-only for router orders.

## Commands

- `uv run oc data verify-research-cache`
- `uv run oc paper sync`
- `uv run oc paper sync-account`
- `uv run oc paper monitor --sync-broker`
- `uv run oc paper status`
- `uv run oc paper readiness nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate --strict`
- `uv run oc strategy target-weights strategy_specs/active/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml --data-source alpaca --refresh-data`

## Resolved Alerts

- `stale_paper_account_snapshot`: resolved by `oc paper sync-account`.
- `stale_paper_positions_snapshot`: resolved by `oc paper sync-account`.
- `paper_open_orders`: resolved after broker sync; current `open_order_count=0`.

## Remaining Warning

- `paper_reconciliation_issues`: one `position_without_local_order` warning remains for `TQQQ`.
- Interpretation: Alpaca Paper currently has a TQQQ position without a matching local paper order record. This is a local audit lineage gap, not a fresh broker order request.
- Decision: do not waive silently. Keep Step 8 paper cycle observation-only until the position lineage is reconciled or manually journaled. This warning blocks any claim of fully automated paper execution readiness, but it does not block target-weight observation and daily monitoring.

## Readiness

- `oc paper readiness ... --strict` exited 0 with `ready=yes`.
- Readiness status remains `warning`, with `execution_substate=observation_only`.
- Warnings include missing router order authorization and legacy harness review artifacts.

## Target Weights

- Artifact: `reports/execution/nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate-target-weights.md`
- Data source: Alpaca IEX live fetch.
- Data caveat: IEX is not consolidated full-market SIP data.
- Summary: `rebalance_sessions=273`, `target_weight_rows=3003`, `nonzero_targets=273`.
