# mom_minute_r2 Lockbox Evaluation

- Verdict: `continue`
- Candidates: `9`
- Selected: `mom_minute_r2_p1_003`
- Selection used lockbox: `false`
- Data: Alpaca IEX research-only; no paper/promotion claim.

## Chronological Split

- `development`: 2024-05-16 to 2025-08-06 (305 sessions)
- `validation`: 2025-08-07 to 2025-12-31 (102 sessions)
- `lockbox`: 2026-01-02 to 2026-05-29 (102 sessions)

## Lockbox

Return `26.5356%`, Sharpe `1.8838`, MaxDD `-22.049%`, x2-cost return `24.0192%`.

| Gate | Pass |
|---|---:|
| `positive_net_return` | `True` |
| `sharpe_at_least_0_8` | `True` |
| `maxdd_not_worse_than_tqqq` | `True` |
| `x2_cost_positive` | `True` |
| `beats_naive_or_qqq` | `True` |
