# Open Composer

Open Composer is a file-first AI strategy workbench for Codex-assisted quantitative research,
backtesting, review, Dashboard monitoring, and Alpaca Paper safety workflows.

`StrategySpec` is the source of truth. Python is the deterministic reference runtime.
NautilusTrader is the event-driven execution path. TradingView Pine is a compatibility export,
not the main runtime.

## Quick Start

```bash
cp .env.example .env
cp .codex/config.example.toml .codex/config.toml
make bootstrap
uv run oc doctor
make deploy-prepare
make dashboard-serve
```

`.env` holds API keys and broker settings. `.codex/config.toml` holds non-secret
Codex model and MCP settings. The project also reads `AGENTS.md` and repo skills
under `.agents/skills/`.

`OPENAI_BASE_URL` is optional and may point to OpenAI or a trusted
OpenAI-compatible Responses API gateway. The project does not reject a configured
review/drafting endpoint solely because it is not an official OpenAI domain.

Open the Dashboard at `http://127.0.0.1:8000` after `make dashboard-serve`.

## User Workflow

```bash
uv run oc capability test
uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc spec capabilities strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy promotion-report strategy_specs/drafts/qqq_pullback_15m.yaml
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

Backtest and research reports always need context before they are trusted:

- compare strategy return with buy-and-hold and Alpha in the same data window
- inspect bar count, signal count, closed trades, fees, slippage, and data sanity
- treat parameter sweeps as in-sample research only
- require promotion evidence before paper use: out-of-sample, walk-forward, cost sensitivity,
  and data-source comparison

TradingView export:

```bash
uv run oc compile pine strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_pullback_15m.yaml
```

Only deterministic OHLCV-compatible rules are exported. Pine is for charting and
Strategy Tester compatibility, not full strategy execution.

## Codex Control Surface

Codex follows this repo in a fixed order:

1. `AGENTS.md`
2. the relevant skill in `.agents/skills/`
3. `capabilities/registry.yaml`
4. the strategy spec and generated artifacts

The important local gates are:

- `uv run oc capability test` before adding a new required capability
- `uv run oc spec validate <spec>` before code or Pine generation
- `uv run oc backtest <spec>` before promotion
- `uv run oc strategy parameter-sweep <spec> --param ...` when parameters are adjustable
- `uv run oc strategy promotion-report <spec>` before paper promotion
- `uv run oc dashboard html` after new artifacts land
- `make dashboard-build` before using the React Dashboard bundle

When Codex designs a strategy, do not ask it to return one fixed parameter set. Ask it to:

1. draft a `StrategySpec`
2. list adjustable parameter ranges and factor alternatives
3. run a bounded `parameter-sweep` over those ranges
4. summarize the ranked grid with buy-and-hold, Alpha, quality flags, and data sanity
5. choose the next iteration at the method/data/factor level before tuning more parameters
6. run `promotion-report` before any paper candidate is considered

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
uv run oc data fetch --source alpaca --symbol MU --timeframe 15m --feed iex --strict-live
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m --strict-live --count 1000
uv run oc data longbridge-check --symbol QQQ --timeframe 15m
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
uv run oc feature validate
```

Current data sources:

- Alpaca IEX: implemented for bars and Alpaca Paper context.
- Longbridge: trial market-data adapter, live quote checks, and comparison reports.
- SEC, FRED, Alpha Vantage, GDELT: registered context sources for review and replay.

Longbridge live access uses the official Python SDK with API Key authentication.
Set `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`, and
`LONGBRIDGE_ACCESS_TOKEN`; app key/secret alone are not enough. The adapter
maps bare US tickers like `QQQ` to Longbridge security codes like `QQQ.US` and
supports `1m`, `5m`, `15m`, `1h`, `daily`, and `weekly` periods at the adapter
level. `StrategySpec.timeframe` now allows `1m`, `5m`, `15m`, `30m`, `1h`,
`4h`, `daily`, and `weekly`, but provider support is checked through the
timeframe matrix before fetching. Longbridge currently rejects unsupported
`30m` and `4h` requests instead of falling back. Longbridge candlestick
requests are capped at 1000 bars per
request; account quote cards, monthly symbol quotas, minute-history start dates,
and extended-hours access determine the usable range. Use `--trade-sessions all`
only when extended-hours data is intended; US overnight quotes require the
proper quote card plus `LONGBRIDGE_ENABLE_OVERNIGHT=true`.

Reports marked `sample fallback` or fixture replay are workflow evidence, not
market evidence.

Feature logs under `feature_logs/*.jsonl` are replay inputs for `llm_feature`
factors. Validate them before depending on them in a strategy; validation also
writes a replay manifest at `reports/features/manifest.json`:

```bash
uv run oc feature validate --output reports/features/validation.json
```

Write a point-in-time feature packet manually or derive one from a signal
context:

```bash
uv run oc feature write --symbol QQQ --timestamp 2026-01-01T00:00:00Z --source llm --input-hash input_sha256 --prompt-hash prompt_sha256 -f event_risk_score=0.8 -f regime=risk_on
uv run oc feature from-context <signal-id>
```

Makefile shortcuts:

```bash
make feature-validate
```

## Research Iteration

Use the fixed candidate optimizer for the existing strategy family, or use
parameter sweep when you want to test many combinations from one spec:

```bash
uv run oc strategy optimize strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy parameter-sweep strategy_specs/drafts/qqq_pullback_15m.yaml \
  --param risk.stop_loss_pct=0.8,1.0,1.2 \
  --param risk.take_profit_pct=1.5,2.0,3.0 \
  --param costs.slippage_bps=0,5 \
  --max-candidates 27 \
  --top-n 10 \
  --write-top 2
uv run oc strategy exposure-switch strategy_specs/drafts/qqq_pullback_15m.yaml \
  --fast 5 --fast 8 \
  --slow 21 --slow 34 \
  --risk-on-exposure 1.25 --risk-on-exposure 1.5 \
  --risk-off-exposure 0.75 --risk-off-exposure 1.0 \
  --walk-forward-folds 3 \
  --walk-forward-top-k 8
uv run oc strategy llm-exposure-switch strategy_specs/drafts/qqq_pullback_15m.yaml \
  --fast 5 --fast 8 \
  --slow 21 --slow 34 \
  --risk-on-exposure 1.25 --risk-on-exposure 1.5 \
  --risk-off-exposure 0.75 --risk-off-exposure 1.0 \
  --validation-folds 3
uv run oc strategy rotate-universe strategy_specs/drafts/qqq_pullback_15m.yaml \
  --symbols QQQ,SPY,IWM \
  --lookback 20 --lookback 40 \
  --rebalance-bars 5 \
  --walk-forward-folds 3 \
  --walk-forward-top-k 8
uv run oc strategy market-time strategy_specs/drafts/qqq_pullback_15m.yaml \
  --profile risk_control_hold --profile breakout_hold \
  --fast 5 --fast 8 \
  --slow 21 \
  --walk-forward-folds 3 \
  --walk-forward-top-k 8
```

Parameter sweeps write ranked JSON/Markdown reports under `reports/research/`
and only write top draft specs when requested. Sweep results are in-sample
research evidence; run out-of-sample, walk-forward, cost sensitivity, and data
source comparisons before promotion. `exposure-switch`, `rotate-universe`, and
`market-time` reports include `research_cost`, candidate count, walk-forward
candidate count, estimated backtest passes, `runtime_seconds`, and stage timing;
use `--walk-forward-top-k` during exploration to limit expensive fold-level
re-scoring, then rerun without it for full validation. Research reports also
write `data_profile` with data as-of, feed, source mode, strict-live/cache
fallback state, and data warnings. Dashboard research records surface the same
data as-of, feed, source mode, cache fallback, and warning fields.

Every bounded research run writes `research_brief`, `search_space`, and
`hypothesis_ledger` so parameter scans are tied to an explicit hypothesis,
candidate count, visible evidence, hidden evidence, and counterevidence. The
`llm-exposure-switch` report adds `llm_contribution`, `llm_contribution_ok`,
`llm_contribution_level`, and `strategy_distinctiveness_ok`; fallback/local
choices or selections identical to the deterministic top candidate are labeled
`llm_assisted_selection_only`, not independent LLM Alpha. It also saves the
exact prompt artifact and hides final out-of-sample/full-window metrics from the
model until after selection. If the model call falls back because of a missing
key, network failure, or gateway error, the acceptance gate stays failed.
When an external gateway is unavailable, Codex may use
`--local-choice-label` only by selecting from the saved prompt-visible
candidates; the report records `codex_local_choice` and still computes OOS only
after selection.

Promotion gate:

```bash
uv run oc strategy promotion-report strategy_specs/drafts/qqq_pullback_15m.yaml \
  --oos-ratio 0.3 \
  --walk-forward-folds 3 \
  --cost-slippage-bps 0 \
  --cost-slippage-bps 5 \
  --cost-slippage-bps 10
```

The promotion report writes full-window, out-of-sample, walk-forward, cost sensitivity,
data comparison, buy-and-hold, and Alpha evidence. It is still research evidence, not a
promise of live returns.

## Paper Safety

Alpaca Paper is the only automated order path in the personal local workflow. A paper order requires:

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

Real-money broker writes are out of scope for this product boundary.

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

For local-only browser use, set a Dashboard API token before serving:

```bash
OPEN_COMPOSER_DASHBOARD_TOKEN=<long-random-token> make dashboard-serve
```

Then open the UI once with `?token=<long-random-token>` so browser API calls send
`X-Open-Composer-Token`. The token protects `/api/dashboard/*`; static files are
still served normally. Remote deployments must not use query tokens or
`localStorage` tokens.

Remote Dashboard deployments use Vercel as a password-session BFF and the
Open Composer daemon as the only command executor:

```bash
uv run oc remote doctor
uv run oc remote serve --host 127.0.0.1 --port 8787
uv run oc remote job-list
uv run oc remote job-status <job-id>
```

Vercel signs daemon requests with `X-OC-Timestamp`, `X-OC-Nonce`,
`X-OC-Actor`, `X-OC-Body-SHA256`, and `X-OC-Signature`. Remote command-run is
always an async job. Yellow and Red actions create
`reports/backups/remote/<job_id>/manifest.json` before execution, and Red
actions require the normal confirmation phrase plus `CONFIRM REMOTE STRATEGY
MUTATION` or `CONFIRM REMOTE PAPER CONTROL`.

Long-running work can be handed to local agents through file-backed requests:

```bash
uv run oc agent request-create --title "Review sweep" --prompt "Review reports/research/example.json"
uv run oc agent request-list
uv run oc agent request-complete <request-id> --result-link reports/research/example.md
```

## Project Docs

- [docs/product-golden-path-codex-quant-review-2026-05-13.zh.md](docs/product-golden-path-codex-quant-review-2026-05-13.zh.md) — no-context Codex starting review document
- [AGENTS.md](AGENTS.md)
- [docs/claude-code-vercel-remote-dashboard-plan-2026-05-14.zh.md](docs/claude-code-vercel-remote-dashboard-plan-2026-05-14.zh.md)
- [docs/current-unfinished-work-check.zh.md](docs/current-unfinished-work-check.zh.md)
- [docs/goal-retrospective-llm-quant-workflow-2026-05-14.zh.md](docs/goal-retrospective-llm-quant-workflow-2026-05-14.zh.md)
- [docs/gstack-audit-verified-optimization-plan-2026-05-14.zh.md](docs/gstack-audit-verified-optimization-plan-2026-05-14.zh.md)
- [docs/product-maturation-plan.zh.md](docs/product-maturation-plan.zh.md)
- [docs/review-methodology.zh.md](docs/review-methodology.zh.md)
- [docs/remote-dashboard-deploy.zh.md](docs/remote-dashboard-deploy.zh.md)
- [docs/longbridge-integration.md](docs/longbridge-integration.md)
