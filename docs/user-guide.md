# Open Composer User Guide

This guide keeps command-level usage out of the README. Start with
`make start`; use this page when you need the underlying workflow.

## Local Setup

Linux or macOS:

```bash
./scripts/setup-local.sh
```

Windows PowerShell:

```powershell
.\scripts\setup-local.ps1
```

Manual equivalent:

```bash
cp .env.example .env
make bootstrap
make verify
make dashboard-serve
```

The Dashboard is available at `http://127.0.0.1:8000` by default.

## Core Strategy Workflow

Validate a draft, inspect capabilities, run research, and build Dashboard
artifacts:

```bash
uv run oc spec validate strategy_specs/drafts/<strategy>.yaml
uv run oc spec capabilities strategy_specs/drafts/<strategy>.yaml
uv run oc strategy evidence strategy_specs/drafts/<strategy>.yaml
uv run oc strategy promotion-report strategy_specs/drafts/<strategy>.yaml
uv run oc dashboard html
```

`strategy evidence` is the preferred first evidence artifact. It brings together
spec validation, capability status, reference backtest, Factor Lab, promotion,
paper-readiness summary, and research-contract checks.

## Strategy Work Sessions

StrategyProject iteration is durable at the project level. `continue` writes a
command into `projects/{project}/queue.jsonl`, refreshes
`projects/{project}/context.md`, and records control events in
`projects/{project}/trace.jsonl`.

```bash
uv run oc project continue <project-id> --advice "focus on execution reality"
uv run oc agent status <project-id>
uv run oc agent stop <project-id>
```

The default backend is `file_queue`, which is always available. Set
`OPEN_COMPOSER_AGENT_BACKEND=codex_sdk` to use the optional Codex backend when
the SDK is installed. File artifacts remain the audit source either way.

## Bounded Research

Use bounded search when parameters, factor variants, or method variants are
adjustable:

```bash
uv run oc strategy parameter-sweep strategy_specs/drafts/<strategy>.yaml \
  --param risk.stop_loss_pct=0.8,1.0,1.2 \
  --param risk.take_profit_pct=1.5,2.0,3.0 \
  --param costs.slippage_bps=0,5 \
  --max-candidates 27 \
  --top-n 10 \
  --write-top 2
```

Other research commands:

```bash
uv run oc strategy factor-lab strategy_specs/drafts/<strategy>.yaml
uv run oc strategy exposure-switch strategy_specs/drafts/<strategy>.yaml --walk-forward-folds 3 --walk-forward-top-k 8
uv run oc strategy rotate-universe strategy_specs/drafts/<strategy>.yaml --symbols QQQ,SPY,IWM --walk-forward-folds 3
uv run oc strategy market-time strategy_specs/drafts/<strategy>.yaml --profile risk_control_hold --walk-forward-folds 3
uv run oc strategy llm-exposure-switch strategy_specs/drafts/<strategy>.yaml --validation-folds 3
uv run oc strategy blind-test strategy_specs/drafts/<strategy>.yaml
uv run oc strategy cost-grid strategy_specs/drafts/<strategy>.yaml
uv run oc strategy regime-search strategy_specs/drafts/<strategy>.yaml
```

Research reports write `research_brief`, `search_space`,
`hypothesis_ledger`, `research_cost`, candidate counts, estimated backtest passes,
`runtime_seconds`, `data_profile`, source mode, fallback warnings, and Dashboard research records
where applicable.

LLM selection reports must expose `llm_contribution`,
`llm_contribution_ok`, `llm_contribution_level`,
`strategy_distinctiveness_ok`, the prompt artifact, and fallback status.
Fallback, local choices, or choices identical to the deterministic top
candidate are labeled `llm_assisted_selection_only`; if an external gateway is
unavailable, the acceptance gate stays failed. `--local-choice-label` records
`codex_local_choice` and must select from prompt-visible candidates.

### Persistent Research Knowledge

AI/ML and new-modality rounds should reuse prior source, experiment, and model
evidence before opening a new search:

```bash
uv run oc research knowledge build
uv run oc research knowledge scout <iter-id>
uv run oc research knowledge assess <iter-id>
uv run oc research iteration validate <iter-id> --stage pre-backtest
```

The scout reads the iteration's versioned query manifest and separates known
sources from new, unvalidated candidates. The assessment records reused,
refreshed, duplicate, conflicting, and new evidence. Search hits do not become
validated knowledge until strategy experiments support them.

Knowledge is partitioned into public literature, train-only empirical results,
challenge results, and forward observations. Candidate generation must not read
challenge or forward verdicts. Frozen model memory includes model, data,
feature, prompt, validation, and status provenance; a model is reused or
retrained only with a recorded data, drift, calibration, or cadence reason.

Multimodal strategies must also declare a role matrix and matched quant-only,
modality-only, combined, missing-modality, shuffled, and stale-modality
controls. Grounded document features are materialized before replay:

```bash
uv run oc research momentum-multimodal-capability
uv run oc research momentum-sec-collect --symbols NVDA,AMD --since 2023-01-01
uv run oc research momentum-multimodal-materialize --input <documents.jsonl>
```

SEC collection requires an explicit contact-bearing `SEC_USER_AGENT`. Missing
provider credentials, transcript licenses, or real PIT history remain blockers;
fixtures never authorize historical multimodal training.

## AI-Driven Auto Research

Use `oc research auto` when you want the catalog workflow to turn a thesis into
candidate factors, single-factor IC diagnostics, a draft StrategySpec, strategy
evidence, and an auto research report:

```bash
uv run oc research auto "Trend continuation on QQQ daily."
```

The default is `--universe QQQ --timeframe daily --data-source alpaca`. If
Alpaca credentials are not configured, the command falls back to sample
synthetic data and writes `data_source_fallback.txt` into the run directory.
Sample fallback output is workflow evidence only and remains not paper-ready.

For explicit sample-only research:

```bash
uv run oc research auto "Trend continuation on SYN daily." \
  --universe SYN --timeframe daily \
  --data-source sample --data-path data/sample/syn_daily.csv
```

After multiple theses, generate a cross-thesis factor view:

```bash
uv run oc research compare
```

The output at `reports/research/auto/_compare/cross_thesis_compare.md` shows
factor appearances, selection rate, mean/min/max rank IC, and diagnosis
breakdowns such as `insufficient_observations`, `zero_variance_signal`, and
`all_nan_signal`.

## Data And Feature Packets

```bash
uv run oc capability test
uv run oc data fetch --source alpaca --symbol MU --timeframe 15m --feed iex
uv run oc data fetch --source longbridge --symbol QQQ --timeframe 15m
uv run oc data longbridge-check --symbol QQQ --timeframe 15m
uv run oc data compare --symbol QQQ --timeframe 15m --left alpaca --right longbridge
uv run oc feature validate --strict
uv run oc feature materialize strategy_specs/drafts/<strategy>.yaml --backend local_test_stub
```

Choose data, event, macro, and news sources through
`capabilities/registry.yaml`. Run capability evaluation before adding a new
required strategy capability.

Feature packets must be point-in-time replay data with `visible_at`,
`published_at`, `fetched_at`, `source`, input hash, and prompt hash before
they affect trading. Promotion and paper readiness require evidence for
single-modality baseline, marginal lift, and missing-modality robustness.

For `source=llm_feature`, the preferred flow is prompt design, materialization,
replay, and marginal contribution review. Backtests do not call live LLMs; they
read `reports/features/{strategy}/{factor}/packets.jsonl` or an explicit
feature packet path.

The expression language is an AST-checked subset: OHLCV names, registered
factor names, supported indicator functions, boolean logic, comparisons, and
basic arithmetic. Imports, attribute access, comprehensions, `eval`, `open`,
and runtime escapes are rejected before evaluation.

## StrategyDAG And Alternative Data

Validate replay-only StrategyDAG files with:

```bash
uv run oc strategy dag-validate path/to/strategy_dag.yaml
```

Backtests must not call live LLMs. Live or paper LLM decisions must first be
written as decision packets with `visible_at`, `input_hash`, `prompt_hash`,
`model`, and `schema_version`.

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

Typical flow:

```bash
uv run oc strategy approve strategy_specs/drafts/<strategy>.yaml
uv run oc strategy activate <strategy> --paper-auto --allow-paper-auto --data-source alpaca --enforce-paper-readiness
uv run oc paper readiness <strategy>
uv run oc run paper <strategy> --max-cycles 1 --no-review
uv run oc paper submit <signal-id> --allow-paper-orders
uv run oc strategy disable <strategy>
```

Sample-data strategies can be activated for local smoke tests, but paper order
submission blocks them with `blocked_by_readiness`.

## Dashboard

```bash
make dashboard-catalog
make dashboard-build
make dashboard-serve
```

When launched with `make dashboard-serve`, the UI syncs the runtime catalog
from `/api/dashboard/catalog`. Local browser API calls can be protected with:

```bash
OPEN_COMPOSER_DASHBOARD_TOKEN=<long-random-token> make dashboard-serve
```

The normal remote deployment is VPS-hosted Dashboard behind Cloudflare Tunnel
and Cloudflare Access. The Dashboard process still listens on
`127.0.0.1:8000`; Cloudflare is only the remote access gate.

```bash
./scripts/deploy-vps.sh --cloudflare-access --dashboard-url https://dashboard.example.com
```

Set these on the VPS, or pass the matching CLI options:

```bash
OPEN_COMPOSER_DASHBOARD_AUTH_MODE=cloudflare_access
OC_DASHBOARD_ALLOWED_ORIGIN=https://dashboard.example.com
OC_CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
OC_CLOUDFLARE_ACCESS_AUD=<Access application AUD tag>
OC_DASHBOARD_ALLOWED_EMAILS=you@example.com
```

`cloudflare_access_or_token` is available for migration/debug fallback.
Strategy work remains CLI/file/agent driven. See
`docs/remote-dashboard-deploy.zh.md`.

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

## Workspace Cache And Artifacts

Inspect local dependency, cache, report, and log size without deleting anything:

```bash
uv run oc cache status
```

Preview the default clean set, which includes `data/cache` and generated
`reports` while preserving tracked example research reports:

```bash
uv run oc cache clean --dry-run
```

Apply that cleanup explicitly:

```bash
uv run oc cache clean --data-cache --reports --apply
```

Evidence logs are not selected by default. Use `--signal-logs`,
`--feature-logs`, `--event-logs`, or `--all-runtime --apply` only when you
intentionally reset local run evidence. Dependency folders such as `.venv` and
`dashboard/node_modules` are status-only in this command.

## Quality Gates

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run oc repo check --strict
make verify
```

`make verify` runs the local closure: format, lint, tests, repo check,
capability test, agent parity, deployment prepare, Dashboard check, feature
validation, and readiness.
