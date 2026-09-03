# W7: Execution Reality — Why the Champion's Exit Orders Never Filled

Scope: read-only analysis of `reports/paper/sync.jsonl` (the broker-observed order
ledger). No order was submitted as part of this analysis, per the user's 2026-09-02
decision to defer all paper-account actions until a strategy is ready to connect.

## The pattern

Every order in the ledger with `time_in_force=opg` (opening-auction limit order) has
**never filled** — 4 attempts, 4 non-fills (2 `expired`, 2 `canceled`). Every order
with `order_type=market, time_in_force=day` has **always filled** — 6 attempts, 6
fills. This is the entire population of `oc-`-prefixed orders in the ledger; there is
no order type in between.

| Date | Symbol | Side | Limit | Actual open | Price would permit fill? | Status |
|---|---|---|---:|---:|---|---|
| 2026-06-01 | TQQQ | sell | 84.33 | 83.95 | no (open below limit) | canceled |
| 2026-06-01 | SOXL | buy | 224.63 | 217.26 | **yes** (open well below limit) | canceled |
| 2026-06-03 | TQQQ | sell | 87.05 | 87.48 | **yes** (open above limit) | expired |
| 2026-07-10 | TQQQ | sell | 75.67 | 75.53 | no (open below limit) | expired |
| 2026-05-08..05-26 | QQQ/TQQQ | buy/sell | — | — | — (market order) | filled (6/6) |

A sell limit fills at or above its limit price; a buy limit fills at or below its
limit price. **Two of the four OPG orders had a price relationship at the actual
opening print that should have produced a fill** (SOXL buy at 217.26 against a
224.63 limit; TQQQ sell at 87.48 against an 87.05 limit) — these are not explained
by "the market didn't reach my price." The other two are individually explainable
by price alone, but sit inside the same 0-for-4 pattern.

`accepted_at` is `null` on every order in the ledger, **including every
successfully filled market order** — so its absence on the OPG orders is a gap in
what this integration records, not evidence either way, and should not be read as
a signal.

## Why this matters for the plan's OPG hypothesis

Per the capability gap analysis, Alpaca's own learn-center content states OPG/CLS
orders are only available to Elite Smart Router users, while the primary API
reference docs do not mention that restriction. A 0-for-4 OPG fill rate, including
two cases where the actual opening price should have triggered a fill under normal
limit-order semantics, against a 6-for-6 market-order fill rate on the same
account, is consistent with OPG orders being accepted by the API but never
actually routed into the opening auction on this account. It is not conclusive:
four data points, no direct broker error message captured, and this analysis
found no diagnostic field in the ledger that distinguishes "rejected before the
auction" from "entered the auction and did not trade." The only way to get a
definitive answer is a live test order on this account, which per the user's
decision is deferred until a strategy is ready to connect — this analysis does
not submit one.

## What would need to change if OPG is confirmed unavailable

`open_composer/paper_authorization.py`'s canary order styles
(`CANARY_ALLOWED_ORDER_STYLES = {"opg_limit", "loo_limit"}`) and any strategy's
`execution_policy.order_style` that resolves to an `opg` time-in-force (see
`open_composer/execution_policy.py`) would both need a non-OPG default —
`loo_limit` alone, or a `day_market` style with an explicit
`naked_market_justification` (`StrategySpec.execution_policy` field, required by
`open_composer/models/strategy_spec.py`'s own validator whenever `day_market` is
used without price protection). Given every historical fill in this ledger is a
plain day-market order, that is also the path with actual fill evidence behind
it, not just a fallback.

## Disposition

**Resolved 2026-09-03 by the user: OPG orders are usable on the account that
will be connected going forward.** The 0-for-4 pattern above is not explained
by an account-level OPG restriction, per the user. The stranded position and
the four non-fills documented here belong to the paper account being retired
alongside the champion route (see the goal-first conclusion, section on the
2026-09-03 decisions) rather than to the new account a future candidate will
connect through, so this analysis is retained as a historical record, not as
a live blocker for the next candidate.
