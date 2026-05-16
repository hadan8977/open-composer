# Open Composer

Open Composer is a file-first AI strategy workbench for Codex-assisted
quantitative research, deterministic backtests, review cards, Dashboard
monitoring, and Alpaca Paper safety workflows.

`StrategySpec` is the source of truth. The in-repo Python engine is the
deterministic reference runtime. NautilusTrader is the intended event-driven
execution path. TradingView Pine is a compatibility export, not the main
runtime.

## Product Shape

- CLI plus files are the primary product surface.
- The Dashboard is a read model over local artifacts with three top-level views:
  Monitor, Strategies, and Activity.
- Remote Dashboard mode uses Vercel only as a password-session BFF. The VPS
  daemon is the only command executor.
- Vercel must not run backtests, scans, pytest, dashboard builds, file writes,
  or shell commands; long work is handed off through `reports/agent_requests/`.
- Real-money broker writes are outside the MVP boundary. Automated broker writes
  are limited to Alpaca Paper with explicit confirmations and readiness gates.

## Quick Start

Local setup:

```bash
cp .env.example .env
cp .codex/config.example.toml .codex/config.toml
make bootstrap
make verify
make dashboard-serve
```

Or use the idempotent setup script:

```bash
./scripts/setup-local.sh --skip-serve
make dashboard-serve
```

Open the Dashboard at `http://127.0.0.1:8000`.

`.env` holds secrets and broker settings. `.codex/config.toml` holds non-secret
Codex model and MCP settings. The project also reads `AGENTS.md` and skills
under `.agents/skills/`.

`OPENAI_BASE_URL` is optional and may point to OpenAI or a trusted
OpenAI-compatible Responses API gateway. The project does not reject a
configured review or drafting endpoint solely because it is not an official
OpenAI domain.

## VPS Mode

When Codex or an operator is already on the target VPS, deployment is a single
script after `VERCEL_TOKEN` is set:

```bash
export VERCEL_TOKEN=<vercel-token>
./scripts/deploy-vps.sh
```

Equivalent Make target:

```bash
VERCEL_TOKEN=<vercel-token> make remote-deploy
```

The script runs `oc remote bootstrap-vps --apply`, which generates secrets,
merges `.env`, writes the generated Dashboard password to an owner-only file,
installs or refreshes systemd/Caddy, configures Vercel environment variables,
deploys the production Dashboard BFF, verifies the daemon and BFF, and prints
the Dashboard URL, daemon URL, deployment URL, and password path.

Useful variants:

```bash
./scripts/deploy-vps.sh --plan
./scripts/deploy-vps.sh --sudo
./scripts/deploy-vps.sh --daemon-url https://oc-api.example.com
./scripts/deploy-vps.sh --rotate-secrets
./scripts/deploy-vps.sh --skip-vercel
```

If no `--daemon-url` is supplied during apply mode, the bootstrap command
detects the VPS public IPv4 and uses `https://<ip>.nip.io`; when 443 is already
occupied it falls back to `https://<ip>.nip.io:8443`.

Stop a remote Dashboard:

```bash
./scripts/stop-remote-dashboard.sh --remove-systemd --disable-caddy --remove-caddyfile
```

Use `--sudo` when system paths are owned by root. Caddy changes are guarded by a
check for the Open Composer reverse proxy unless `--force-caddy` is passed.

## Core Workflow

```bash
uv run oc capability test
uv run oc spec validate strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc spec capabilities strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc backtest strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy promotion-report strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc scan strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc compile pine-strategy strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc dashboard html
```

Before a strategy can be trusted, compare it with same-symbol buy-and-hold,
equal-weight universe, market proxy, sector/theme proxy, cash proxy, and ex-post
best symbol when available. Treat sample, fixture, cache fallback, and
trial/research-only data as workflow evidence only.

When Codex designs a strategy, ask for a draft `StrategySpec`, adjustable
parameter ranges, method variants, factor variants, a bounded search space, a
ranked sweep, and a promotion report. Do not ask for one fixed parameter set.

The promotion path keeps these gates separate:

- `workflow_pass`
- `research_pass`
- `llm_contribution_pass`
- `paper_ready_pass`
- code correctness

## Research Iteration

Use bounded search commands when parameters, factors, or methods are adjustable:

```bash
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
  --walk-forward-folds 3 \
  --walk-forward-top-k 8
uv run oc strategy llm-exposure-switch strategy_specs/drafts/qqq_pullback_15m.yaml \
  --fast 5 --fast 8 \
  --slow 21 --slow 34 \
  --validation-folds 3
uv run oc strategy rotate-universe strategy_specs/drafts/qqq_pullback_15m.yaml \
  --symbols QQQ,SPY,IWM \
  --lookback 20 --lookback 40 \
  --walk-forward-folds 3 \
  --walk-forward-top-k 8
uv run oc strategy market-time strategy_specs/drafts/qqq_pullback_15m.yaml \
  --profile risk_control_hold --profile breakout_hold \
  --fast 5 --fast 8 \
  --slow 21 \
  --walk-forward-folds 3 \
  --walk-forward-top-k 8
```

Parameter sweeps write ranked JSON and Markdown under `reports/research/`.
Sweep results are in-sample research evidence; rerun out-of-sample,
walk-forward, cost sensitivity, and data-source comparison before promotion.

`exposure-switch`, `rotate-universe`, and `market-time` reports include
`research_cost`, candidate count, walk-forward candidate count, `estimated backtest passes`,
`runtime_seconds`, and stage timing. Use `--walk-forward-top-k` during
exploration to limit fold-level rescoring, then rerun without it for full
validation. Research reports also write
`data_profile` with data as-of, feed, source mode, strict-live/cache fallback
state, and warnings. Dashboard research records surface the same freshness,
source, fallback, and warning fields.

Every bounded research run writes `research_brief`, `search_space`, and
`hypothesis_ledger`. `llm-exposure-switch` also records `llm_contribution`,
`llm_contribution_ok`, `llm_contribution_level`, and
`strategy_distinctiveness_ok`. Fallback or local choices, and choices identical
to the deterministic top candidate, are labeled `llm_assisted_selection_only`,
not independent LLM Alpha. The report saves the exact prompt artifact and hides
final out-of-sample metrics from the model until after selection. If the model
call falls back because of a missing key, network failure, or gateway error, the
acceptance gate stays failed. When an external gateway is unavailable, Codex may
use `--local-choice-label` only by selecting from prompt-visible candidates; the
report records `codex_local_choice`.

## Data And Features

```bash
uv run oc data fetch --source alpaca --symbol MU --timeframe 15m --feed iex
uv run oc data fetch --source alpaca --symbol MU --timeframe 15m --feed iex --strict-live
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m
uv run oc data longbridge-check --symbol QQQ --timeframe 15m
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
uv run oc feature validate --strict
```

Choose data, event, macro, and news sources through
`capabilities/registry.yaml`. Run capability evaluation before adding a required
strategy capability. LLM/news/event/macro packets must be point-in-time replay
packets with `visible_at`, `published_at`, `fetched_at`, `source`, input hash,
and prompt hash before they affect trading.

The expression language is AST-checked and restricted to OHLCV names,
registered factor names, supported indicator functions, boolean logic,
comparisons, and basic arithmetic. Imports, attribute access, comprehensions,
`eval`, `open`, and other runtime escapes are rejected before evaluation.

## Paper Safety

Alpaca Paper is the only automated order path. A paper order requires:

- a spec under `strategy_specs/active/`
- `lifecycle=active`
- `execution.mode=paper_auto`
- `execution.broker=alpaca_paper`
- `data.source=alpaca` or `data.source=longbridge`
- paper environment variables
- a passing `oc paper readiness` report
- an explicit flag such as `--allow-paper-orders`

Example:

```bash
uv run oc strategy approve strategy_specs/drafts/qqq_pullback_15m.yaml
uv run oc strategy activate qqq_pullback_15m --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness
uv run oc paper readiness qqq_pullback_15m
uv run oc run paper qqq_pullback_15m --max-cycles 1 --no-review
uv run oc paper submit <signal-id> --allow-paper-orders
uv run oc strategy disable qqq_pullback_15m
```

Sample-data strategies can be activated for local smoke tests, but paper order
submission blocks them with `blocked_by_readiness`.

## Dashboard

Build the Dashboard read model before using the UI:

```bash
make dashboard-catalog
make dashboard-build
make dashboard-serve
```

When launched with `make dashboard-serve`, the UI syncs the runtime catalog from
`/api/dashboard/catalog` so Monitor, Strategies, and Activity follow local paper
and audit updates. Local browser API calls can be protected with:

```bash
OPEN_COMPOSER_DASHBOARD_TOKEN=<long-random-token> make dashboard-serve
```

Remote Dashboard deployments must use password session, Vercel BFF, HMAC,
async jobs, backups, audit, and double confirmation for Red actions. Vercel
signs daemon requests with `X-OC-Timestamp`, `X-OC-Nonce`, `X-OC-Actor`,
`X-OC-Body-SHA256`, and `X-OC-Signature`. Yellow and Red actions create
`reports/backups/remote/<job_id>/manifest.json`; Red actions require the normal
confirmation phrase plus `CONFIRM REMOTE STRATEGY MUTATION` or
`CONFIRM REMOTE PAPER CONTROL`.

Long-running local agent work uses file-backed requests:

```bash
uv run oc agent request-create --title "Review sweep" --prompt "Review reports/research/example.json"
uv run oc agent request-list
uv run oc agent request-complete <request-id> --result-link reports/research/example.md
```

## Notifications

Outbound notifications are configured file-first. Copy
`config/notifications.yaml.example` to `config/notifications.yaml`, set
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`, then verify without
sending:

```bash
uv run oc notify status
uv run oc notify test --dry-run
```

Telegram is outbound-only. Open Composer does not consume Telegram webhooks,
polling updates, callbacks, or chat commands.

## Quality Gates

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run oc repo check --strict
make deploy-prepare
make verify
```

`make deploy-prepare` rebuilds the Dashboard catalog, static Dashboard HTML,
feature validation, paper monitor artifacts, and readiness reports. `make
readiness` writes `reports/readiness/readiness.json` and `.md`.

## Project Docs

- [docs/product-golden-path-codex-quant-review-2026-05-13.zh.md](docs/product-golden-path-codex-quant-review-2026-05-13.zh.md) - no-context Codex starting review document
- [AGENTS.md](AGENTS.md)
- [docs/remote-dashboard-deploy.zh.md](docs/remote-dashboard-deploy.zh.md)
- [docs/setup-local.zh.md](docs/setup-local.zh.md)
- [docs/longbridge-integration.md](docs/longbridge-integration.md)
