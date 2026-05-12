# Open Composer

Open Composer is a file-first strategy workbench for drafting, testing, reviewing,
and paper-monitoring trading ideas with Codex.

`StrategySpec` is the source of truth. Python is the deterministic reference.
NautilusTrader is the event-driven execution path. TradingView Pine is a
compatibility export, not the main runtime.

## Setup

```bash
cp .env.example .env
cp .codex/config.example.toml .codex/config.toml
make bootstrap
uv run oc doctor
make deploy-prepare
```

`.env` holds API keys and broker settings. `.codex/config.toml` holds non-secret
Codex model and MCP settings. The project also reads `AGENTS.md` and repo skills
under `.agents/skills/`.

## Core Workflow

```bash
uv run oc capability test
uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc spec capabilities strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc scan strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc dashboard html
uv run ruff check .
uv run pytest
```

One-command local verification:

```bash
make deploy-prepare
make verify
make readiness
```

`make deploy-prepare` rebuilds the local deployment surface: Dashboard catalog,
static Dashboard HTML, feature validation, paper monitor artifacts, and
readiness reports. `make readiness` writes `reports/readiness/readiness.json`
and `.md`, covering Dashboard bundle/catalog, feature packets, paper monitor
state, and strategy capability readiness.

TradingView export:

```bash
uv run oc compile pine strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_pullback_15m.yaml
```

Only deterministic OHLCV-compatible rules are exported. Pine is for charting and
Strategy Tester compatibility, not full strategy execution.

## Control Surface

Codex follows this repo in a fixed order:

1. `AGENTS.md`
2. the relevant skill in `.agents/skills/`
3. `capabilities/registry.yaml`
4. the strategy spec and generated artifacts

The important local gates are:

- `uv run oc capability test` before adding a new required capability
- `uv run oc spec validate <spec>` before code or Pine generation
- `uv run oc backtest <spec>` before promotion
- `uv run oc dashboard html` after new artifacts land
- `make dashboard-build` before using the React Dashboard bundle

Generated reports, signal logs, cache files, strategy versions, and paper state
are local runtime outputs. They are intentionally ignored by git; checked-in
files are limited to source code, docs, fixtures, and a small example set.

## Data

Open Composer records provenance in manifests and reports. When live data is
available, use it. When not, the workflow falls back to local cache, sample, or
fixture data and labels that clearly.

Useful commands:

```bash
uv run oc data fetch --source alpaca --symbol MU --timeframe 15m --feed iex
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
uv run oc feature validate
```

Current data sources:

- Alpaca IEX: implemented for bars and Alpaca Paper context.
- Longbridge: trial market-data adapter and comparison reports.
- SEC, FRED, Alpha Vantage, GDELT: registered context sources for review and replay.

Reports marked `sample fallback` or fixture replay are workflow evidence, not
market evidence.

Feature logs under `feature_logs/*.jsonl` are replay inputs for `llm_feature`
factors. Validate them before depending on them in a strategy:

```bash
uv run oc feature validate --output reports/features/validation.json
```

Write a point-in-time feature packet manually or derive one from a signal
context:

```bash
uv run oc feature write --symbol QQQ --timestamp 2026-01-01T00:00:00Z --source llm -f event_risk_score=0.8 -f regime=risk_on
uv run oc feature from-context <signal-id>
```

Makefile shortcuts:

```bash
make feature-validate
```

## Paper Safety

Alpaca Paper is the only automated order path in the MVP. A paper order requires:

- a spec under `strategy_specs/active/`
- `lifecycle=active`
- `execution.mode=paper_auto`
- `execution.broker=alpaca_paper`
- `data.source=alpaca` or `data.source=longbridge` for automated order runs
- paper environment variables
- a passing `oc paper readiness` report
- an explicit command flag such as `--allow-paper-orders`

Example:

```bash
uv run oc strategy approve strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy activate qqq_pullback_15m --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness
uv run oc paper readiness qqq_pullback_15m
uv run oc run paper qqq_pullback_15m --max-cycles 1 --no-review
uv run oc paper submit <signal-id> --allow-paper-orders
uv run oc strategy disable qqq_pullback_15m
```

Sample-data strategies can still be activated and previewed for local smoke tests,
but `oc run paper ... --allow-paper-orders` blocks them with
`blocked_by_readiness` instead of submitting an Alpaca Paper order.

Real-money broker writes are out of scope for this MVP.

Useful paper-monitoring make targets:

```bash
make paper-readiness PAPER_STRATEGY=qqq_pullback_15m
make paper-sync
make paper-sync-account
make paper-status
make paper-reconcile
make paper-alerts
make paper-monitor
make paper-monitor-sync
make paper-monitor-loop MONITOR_MAX_CYCLES=0
make paper-monitor-loop-sync MONITOR_MAX_CYCLES=0
```

Use the `*-sync` targets only when Alpaca Paper credentials are configured; they
pull broker order/account/position snapshots before rebuilding local monitor
reports.

## Dashboard

The React Dashboard is a read-model surface over `reports/dashboard/catalog.json`.
When served locally, the Paper page also exposes a paper-only command center
backed by the same command-plan / confirmation gate as the CLI. Strategy edits,
order submission, and real-money broker writes are still not browser actions.
Build the catalog before launching or bundling the UI:

```bash
make dashboard-catalog
make dashboard-build
make dashboard-dev
make dashboard-serve
```

Dashboard paper actions can be run from the local Paper command center or from
the CLI. They create a command plan first and require the exact confirmation
phrase before execution:

When launched with `make dashboard-serve`, the UI also syncs the runtime catalog
from `/api/dashboard/catalog`, so the visible read model follows local paper and
audit updates without a manual rebuild.

```bash
uv run oc dashboard command-plan paper.status.refresh --reason "operator check"
uv run oc dashboard command-run reports/dashboard/commands/<plan>.json --confirm "CONFIRM PAPER COMMAND"
uv run oc dashboard command-plan paper.sync.orders --reason "sync broker orders"
uv run oc dashboard command-plan paper.sync.account --reason "sync paper account"
uv run oc dashboard command-plan system.prepare_workspace --reason "local deploy prep"
uv run oc dashboard command-plan strategy.draft --idea "Create a QQQ 15m breakout strategy with volume expansion and volatility filter."
uv run oc dashboard command-plan strategy.workflow.verify --strategy-path strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc dashboard command-plan strategy.validate --strategy-path strategy_specs/drafts/qqq_pullback_15m.yaml
```

Supported Dashboard command actions are `paper.status.refresh`,
`paper.monitor.refresh`, `paper.sync.orders`, `paper.sync.account`,
`paper.kill_switch.enable`, `paper.kill_switch.clear`,
`system.prepare_workspace`, `system.readiness.refresh`, `strategy.draft`,
`strategy.workflow.verify`, `strategy.validate`, `strategy.capabilities.refresh`,
`strategy.approve`, `strategy.activate.manual`, `strategy.activate.paper_auto`,
`strategy.backtest.rerun`, `strategy.scan.rerun`, and `strategy.disable`.
They never submit real-money orders.

For anything beyond local-only use, set a Dashboard API token before serving:

```bash
OPEN_COMPOSER_DASHBOARD_TOKEN=<long-random-token> make dashboard-serve
```

Then open the UI once with `?token=<long-random-token>` so browser API calls send
`X-Open-Composer-Token`. The token protects `/api/dashboard/*`; static files are
still served normally.

## Example Benchmark

- `mu_breakout_volume_15m_optimized_volume_plus`
  - sample data, 52 bars
  - annualized return `1089.90%`
  - Sharpe `45.78`
  - research-only, not production evidence

The current research audit is documented in [docs/review-optimization-completion-audit.zh.md](docs/review-optimization-completion-audit.zh.md).

## Project Docs

- [AGENTS.md](AGENTS.md)
- [OPEN-COMPOSER-BUILD-HANDOFF.md](OPEN-COMPOSER-BUILD-HANDOFF.md)
- [OPEN-COMPOSER-PRODUCT-MVP.md](OPEN-COMPOSER-PRODUCT-MVP.md)
- [docs/quant-capability-expansion-plan.zh.md](docs/quant-capability-expansion-plan.zh.md)
- [docs/quant-capability-expansion-review.zh.md](docs/quant-capability-expansion-review.zh.md)
- [docs/product-maturation-plan.zh.md](docs/product-maturation-plan.zh.md)
- [docs/review-methodology.zh.md](docs/review-methodology.zh.md)
