# Manual live-execution reference

This document describes a manual mapping for a specific router; it grants no live-trading permission or live API access. Activation remains an owner decision. The existing prerequisites are:

- `reports/paper/validation/paper-validation-report-<date>.json`: `paper_validation_pass=true`.
- `reports/research/control/route-cross-source-validation-<date>.json`: `route_cross_source_pass=true`.
- `uv run oc paper readiness nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate --strict` passes.
- `uv run oc paper status` shows the kill switch disabled.

The historical deferral of cross-source data-depth work did not waive any launch prerequisite or the requirement for explicit owner approval.

## Daily procedure if separately authorized

Read notifications and `reports/paper/review_cards/YYYYMMDD.md` before open. `Action: No operation.` means no live action. Otherwise follow the card's `50% live weight` column manually, with the balance in BIL/cash, then append the actual fill to `reports/live/manual_journal.jsonl`. Any unexplained paper-cycle, state-drift, data or reconciliation warning/error blocks that day's new live action.

```json
{"date":"2026-07-09","symbol":"GLD","action":"buy","qty":100,"price":350.12,"source_review_card":"reports/paper/review_cards/20260709.md","note":"manual 50pct mapping"}
```

The paper validation cycle first checks readiness. It passes `--allow-paper-orders` only with an existing router-order authorization, readiness `status=ok`, execution substate `order_authorized` and a clear kill switch; otherwise it stays observation-only. A failed counted trading day requires `reports/paper/validation/remediations/YYYYMMDD.md` before the next day's cycle.

## Initial 50% mapping

The current review card governs execution; use this table only as a consistency check.

| Router state | Card target | Initial manual allocation |
|---|---|---|
| `confirmation_transition_overlay_TQQQ` | TQQQ | 50% TQQQ, 50% BIL/cash |
| `post_drawdown_reentry` | TQQQ | 50% TQQQ, 50% BIL/cash |
| `risk_on_ranked` | Selected symbol | 50% selected symbol, 50% BIL/cash |
| `confirmation_transition` | QLD | 50% QLD, 50% BIL/cash |
| `early_deterioration_downshift` | QQQ | 50% QQQ, 50% BIL/cash |
| `hard_stress_defensive` | GLD | 50% GLD, 50% BIL/cash |
| `cooldown_transition_overlay_TQQQ` | TQQQ | 50% TQQQ, 50% BIL/cash |
| `soft_stress` | QQQ | 50% QQQ, 50% BIL/cash |
| `cooldown_transition` | QLD | 50% QLD, 50% BIL/cash |
| `selected_asset_blocked` | QLD | 50% QLD, 50% BIL/cash |
| `melt_up_peak_guard` | QLD | 50% QLD, 50% BIL/cash |

## Stop conditions and monthly audit

Two consecutive failed trading-day cycles stop new live actions, permit only risk reduction and require `uv run oc paper kill-switch --enable --reason "daily cycle failed twice"`. Drawdown worse than -25% since live inception requires moving entirely to BIL/cash and review before resuming. A data/reconciliation/state-drift anomaly means no live action that day. Either validation flag false prevents launch.

Monthly audit commands:

```bash
uv run oc data verify-research-cache
uv run oc strategy router-replay-audit
uv run oc paper validation-report
```

On replay drift, inspect research-cache manifest hashes before comparing strategy numbers. Parameter tuning is not an audit-drift repair.
