# Intraday paper runner

The runner in `open_composer/intraday_runner/`, entered through `scripts/run_intraday_runner.py`, shares Alpaca Paper account quant2 across strategy sub-books. It supports shadow and authorized paper operation. Code changes follow the live-paper isolation rules in [AGENTS.md](../AGENTS.md); this runbook does not authorize deployment or orders.

## Decision and accounting model

A decision boundary occurs each minute, five seconds after bar close. Plugins run only on their configured 1/5/15/30-minute boundaries. Live input is closed IEX minute bars; replay uses local SIP history.

The runner logs a signal to `signal_logs/paper-intraday-runner-quant2.jsonl` before risk review, computes each strategy's delta from its virtual position, then nets same-symbol deltas into at most one account order per boundary. Zero-net changes cross internally without a broker order. Submitted orders are regular-hours DAY market orders; multi-strategy mode has no broker bracket, stop or limit orders. Deterministic IDs follow `paper_intraday._client_order_id`, binding account, date, symbol, side and decision time.

Broker fills are allocated to strategy deltas proportionally in whole shares by largest remainder. Every participating strategy receives the same broker average fill price (incremental average for partial fills), keeping allocation PnL consistent with the broker account. Internal crosses still incur each strategy's `assumed_cost_bps`, including fully offset orders filled at the plan price. This modeled charge is absent from broker equity; reconciliation separately reports `internal_cross_cost_usd` and the difference after accounting for it.

Non-overnight strategies flatten at their configured time, default 15:55 ET, adjusted for early closes. After close, the runner reconciles, writes a per-strategy summary and replays the day's decisions with SIP to quantify feed differences.

## Shadow and paper modes

Without `--allow-paper-orders`, `run` uses the shadow book and writes `<date>-plan/`. It logs signals/intents/net orders and models fills at plan price plus/minus `shadow_slippage_bps` (default 1 bp). Positions, PnL, stops and summaries evolve in that separate book. It does not read broker positions for reconciliation; asset shortability lookup is read-only. Shadow mode needs no order authorization, but still uses its configured data access.

With `--allow-paper-orders`, a valid config/account-bound authorization is required. A read-only first-start preflight checks expected opening positions and open orders; failure returns `preflight_failed`, writes `preflight-<date>.json` and does not trade. Neither preflight mode automatically flattens positions or cancels orders.

## Plugin contract

```python
from open_composer.intraday_runner.plugins import (
    IntradayPlugin, PluginContext, PluginDecision, Target, register_plugin,
)

@register_plugin("my_strategy")
class MyStrategy(IntradayPlugin):
    history_days = 14  # Prior sessions only; excludes today.

    def decide(self, ctx: PluginContext) -> PluginDecision:
        # ctx.bars: today's closed strategy-period bars, including feed.
        # ctx.history: prior minute bars; positions, last_prices, state and
        # day_pnl_usd are also available on ctx.
        return PluginDecision(
            targets={"SPY": Target(notional_usd=100_000)}, state={"side": 1}
        )
```

Omitted symbols keep their standing targets; `Target(shares=0)` explicitly flattens. `assert_point_in_time` rejects bars closing after the decision or historical input containing today. Plugin exceptions skip only that strategy/boundary (`plugin_error`). Persisted signal events restore `state` after restart. Dotted plugin paths must begin `open_composer.`; strategy implementations live under `open_composer/intraday_runner/strategies/`. `noise_band_example` and `timed_trade` are examples/test fixtures, not accepted research specifications.

## Risk behavior

| Scope/check | Behavior |
|---|---|
| Strategy `max_notional_usd`, `max_symbol_notional_usd` | Scale only exposure increases; price appreciation alone does not force liquidation. |
| Strategy `max_orders_per_day` | Block exposure increases, permit reductions/closure. |
| Strategy `max_daily_loss_usd` | Realized plus unrealized PnL less charges triggers `halt`, flattening and no new exposure that day. |
| Shorts | Require both `shortable` and `easy_to_borrow`; missing status means unavailable. |
| Client stop | `stop_loss_pct` is off by default. Each boundary checks the latest one-minute close against average cost; `stop` forces target zero via netted market orders. `stop_cooldown_minutes` defaults to 30. No broker stop order exists. |
| Missing latest minute | `bars.missing_latest` blocks opening, adding and resizing; no zero-fill or stale-price entry. Closures/stops still use the latest available close as plan price. |
| Resize deadband | `resize_band=0.05` suppresses small same-direction changes. |
| Account gross cap | `max_gross_notional_usd` scales/blocks added exposure while allowing hedges/reductions. |
| Account daily loss | `halt`, flatten all strategies and stop adding exposure. |
| Global kill switch | `reports/paper/kill_switch.json`, unreadable treated as enabled: blocks all orders, including closures. Human handling of positions is then required. |
| Runner STOP | `reports/paper/intraday/runner/quant2/STOP`: blocks new exposure and permits flattening orders. |
| Position drift | Broker/sub-book mismatch freezes that symbol and appears in reconciliation. |
| Repeated broker rejection | Three rejections stop further symbol orders that day. |

### Open orders and reversals

At each boundary, cancel the runner's unfinished prior orders and poll for confirmation, allocating any partial fills first. A symbol in `pending_cancel` receives no new order. Before submission, check for external opposite orders: do not cancel them or submit against them; log `order_abandoned` with `foreign_opposite_open_order` and retry the standing target later.

A long-to-short or short-to-long reversal has two legs: close to zero, confirm the fill, then open the opposite side at a later minute boundary. Standing targets retry every minute even for a 30-minute plugin. This leaves roughly one minute flat and changes execution costs/price drift relative to a same-price backtest reversal. Do not model it as instantaneous.

## Files and crash recovery

Append-only events live at `reports/paper/intraday/runner/quant2/<date>/events.jsonl`; shadow events use `<date>-plan/` and never mix with paper events. Audit order is:

```text
signal -> intent -> net_order -> submit_result -> fill_sync
```

`net_order` is persisted before submission. On restart:

- Replay positions, PnL, counts, halt/stop and plugin state from the log.
- For a `net_order` lacking `submit_result`, query its deterministic broker ID first. Adopt an existing broker order. If absent, resubmit with the same ID only within 120 seconds or for a closing order; abandon stale exposure increases and recompute later.
- Synchronize submitted orders before new planning. Cancel orders unfinished after 60 seconds, allocate actual partial fills and retry remaining standing targets.
- Reuse an already-logged strategy decision for that boundary. Ignore an incomplete final log line.

A file lock allows one runner process; the watchdog can attempt restart every five minutes. Outputs include `daily-summary.jsonl`, `<date>/report.md`, `bars-live.parquet`, `sip-recheck.json` and `carry.json` for permitted overnight positions. Recovery behavior has unit coverage in `tests/test_intraday_runner.py`; that is not proof of a live broker crash drill. Dry-run reports use `reports/paper/intraday/runner-dryrun-<date>.md`.

## Data, rate limits and previous close

The live runner explicitly requests `feed=iex`, regardless of `ALPACA_DATA_FEED`, and records `feed` on events and summary rows. Credential names are `ALPACA_QUANT2_API_KEY_ID` and `ALPACA_QUANT2_API_SECRET_KEY`, loaded from the file selected by `OC_BOOK_ACCOUNTS_ENV` (default `/root/.config/open-composer/paper-book-accounts.env`). Keep credential values out of code and artifacts.

The shared sliding-window limiter covers broker and market-data calls; `api_calls_per_minute` defaults to 180 against the implementation's assumed 200/minute budget. Calls queue rather than drop. The first fetch reads the session; subsequent fetches merge the latest five minutes, with roughly 10,000 rows per page counted toward calls. The documented 30-symbol free WebSocket limit is separate from REST polling; larger `all_symbols` still increases REST pages. Inspect limiter `waited_seconds` before expanding coverage. These provider assumptions need fresh verification before a material execution change.

Prior-session minute history comes from `data/sip/minute` and needs the overnight archive current through the previous session. Startup preload is typically 30-60 seconds; missing history can produce `no_history`. `recheck` compares missing minutes, close differences and volume ratios, then reruns the logged decisions with their original state/positions on SIP bars to count target/direction changes. IEX sparsity and volume differences can materially change signals; earlier successful reads of IEX/SIP do not establish current intraday latency.

Preload also obtains the previous session's official unadjusted close from Alpaca daily bars with `adjustment=raw`, `feed=sip`, through the shared limiter. `ctx.prev_close_raw` contains only that strategy's symbols. A `prev_close` event records values/source once per session and survives restart. If daily data is missing, use the previous session's final minute close with `prev_close_fallback`; if both are absent, leave it missing for the plugin. Adjusted `data/sip/daily` cannot supply this raw-price field.

Replay can supply `--prev-close-file prices.json` (for example `{"QQQ": 479.12}`) or `replay_session(prev_close_raw=...)`; otherwise it records the minute fallback.

## Deployment within existing paper authority

Before activation, ensure no competing quant2 book planner/submitter/reconciler is managing the same account. The runner does not remove old jobs. Require a readable disabled global kill switch and current overnight SIP history.

Configure `config/intraday/runner-quant2.yaml` using `runner-dryrun.yaml`: plugin, symbols, period, allocation, strategy/account caps, `assumed_cost_bps` and optional client stops. Account caps cannot exceed the authorization. A designated operator may bind existing explicit owner authority to the exact config and account hashes, quoting the owner's authorization in `--basis`; a config change requires a new matching authorization, not an automatic permission extension.

```bash
uv run python scripts/run_intraday_runner.py run --config config/intraday/runner-quant2.yaml
uv run python scripts/run_intraday_runner.py preflight --config config/intraday/runner-quant2.yaml
uv run python scripts/run_intraday_runner.py authorize --config config/intraday/runner-quant2.yaml --authorized-by <operator> --basis "<existing owner authorization>" --days 14 --confirm-paper-only
```

The preflight reports nonempty positions/open orders with exit code 3 unless consistent with permitted opening carry. Only enable `--allow-paper-orders` while authorization is effective. Monitor `status`, STOP, reconciliation, slippage versus `assumed_cost_bps`, `bars.missing_latest` frequency and SIP decision differences. The old rollout dates are not present authorization.

### Cron templates

These UTC examples use a broad window; the program checks New York sessions and DST internally. Research code must not install them. Select one watchdog mode, and use the same shadow/paper mode for `recheck`. Installed paper-feeding chains must follow [the memory runbook's paper class](runbook-memory.zh.md).

```cron
# Shadow watchdog; an existing file lock makes repeated starts exit quietly.
*/5 12-20 * * 1-5 cd /root/codex-test/open-composer && scripts/run_capped.sh --class paper --mem 900M -- /root/.local/bin/uv run python scripts/run_intraday_runner.py run --config config/intraday/runner-quant2.yaml >> logs/intraday-runner.log 2>&1
# Authorized paper alternative: replace the watchdog above; never install both.
# */5 12-20 * * 1-5 cd /root/codex-test/open-composer && scripts/run_capped.sh --class paper --mem 900M -- /root/.local/bin/uv run python scripts/run_intraday_runner.py run --config config/intraday/runner-quant2.yaml --allow-paper-orders >> logs/intraday-runner.log 2>&1
# SIP recheck: too-early calls exit; add --allow-paper-orders only for the paper book.
35 20,21 * * 1-5 cd /root/codex-test/open-composer && scripts/run_capped.sh --class paper --mem 900M -- /root/.local/bin/uv run python scripts/run_intraday_runner.py recheck --config config/intraday/runner-quant2.yaml --source alpaca >> logs/intraday-runner.log 2>&1
```

## Operational limits

Plan price is the last closed minute's close; a fill occurs at least five seconds later. Reported slippage is versus plan price, not a measured arrival quote. Paper fills do not establish live liquidity. SEC/TAF and easy-to-borrow charges are currently modeled as zero pending calibration; shortability in paper does not prove live availability. Whole-share rounding can eliminate small allocations in expensive symbols.

Flatten times range 15:45-15:59 ET, falling back to `session.flatten_et=15:55`; early closes preserve the same minutes-before-close interval. After the flatten time, retry every 30 seconds with an `r1` order-ID suffix, canceling/confirming old orders first; the last attempt is no later than 30 seconds before close. Any residual position appears in reconciliation for manual handling. The runner uses regular-hours market orders rather than `opg`/`cls`; see [recorded auction limitations](data-layer-pitfalls-and-capabilities.zh.md).

Decisions more than 90 seconds late skip plugin invocation but still reconcile, flatten and retry. Missing IEX minutes reduce trading opportunities; check missing-bar rates before interpreting low trade counts as absent signals.
