# Open Composer

Open Composer is a personal AI strategy workbench for turning trading ideas
into auditable `StrategySpec` files, deterministic backtests, research reports,
Dashboard views, and paper-trading readiness checks.

It is built for a file-first workflow: Codex edits specs and code, the Python
engine provides the deterministic reference runtime, NautilusTrader is the
event-driven execution path, and TradingView Pine is an export target.

## Why It Exists

Most strategy experiments fail because the workflow mixes prompts, notebooks,
untracked data, undocumented parameter searches, and execution assumptions.
Open Composer keeps those parts explicit:

- `StrategySpec` is the source of truth for strategy behavior.
- Research runs write JSON and Markdown artifacts under `reports/`.
- Data, event, macro, and news sources are selected through
  `capabilities/registry.yaml`.
- LLM, news, event, and macro features must be point-in-time replay packets
  before they can affect promotion or paper readiness.
- Real-money broker writes are out of scope for this MVP.

## Quick Start

Linux or macOS:

```bash
make start
```

Windows PowerShell:

```powershell
.\scripts\setup-local.ps1
```

Then open `http://127.0.0.1:8000`.

The setup path is idempotent. It installs Python and Dashboard dependencies,
creates `.env` from `.env.example` when needed, builds the Dashboard read model,
and starts the local Dashboard. External API keys are optional; sample data and
fixtures are enough for a local smoke test.

## Product Map

| Area | What it does |
|---|---|
| Strategy specs | YAML `StrategySpec` drafts, approvals, activation state, version diffs, and rollback. |
| Research reports | Backtests, promotion gates, research contracts, factor diagnostics, execution reality, cost sensitivity, and data quality. |
| Data capabilities | Sample OHLCV, Alpaca, Longbridge, SEC filings, FRED macro, Alpha Vantage news, and GDELT through a registry. |
| Dashboard | Local or VPS-hosted artifact read model with Monitor, Strategies, Activity, Settings, and Cloudflare Access-ready auth views. |
| Paper safety | Alpaca Paper-only automation with explicit confirmation, readiness gates, kill switch, and audit artifacts. |
| Deployment | One normal path: VPS serves Dashboard from local files; Cloudflare Access is the recommended mobile-friendly remote gate. |

## Two Ways To Use Open Composer

| Audience | Primary interface |
|---|---|
| Day-to-day user | Dashboard at `http://127.0.0.1:8000`; create, continue, review, promote, and monitor strategies without opening a terminal. |
| Agent (Codex / Claude Code) | CLI plus file contracts: `oc strategy ...`, `projects/{id}/queue.jsonl`, `projects/{id}/trace.jsonl`, and `projects/{id}/context.md`. |
| Advanced user | Both: Dashboard for status and controlled actions, CLI for batch work and debugging. |

Every Dashboard action writes an audit or trace entry with `via=dashboard`.
Agent and CLI paths write the same project files, so browser sessions can close
without losing strategy context.

## Typical Workflow

1. Open the Dashboard and use Build to create a Strategy Project from a natural-language idea.
2. Work from Strategy Detail: continue research, inspect trace, review spec diff, and queue evidence or LLM-factor materialization.
3. Review factor, execution, data, benchmark, LLM contribution, and paper readiness gates.
4. Promote only when the report evidence is sufficient.
5. Use paper automation only for active `paper_auto` specs that pass readiness.

For command-level usage, see [docs/user-guide.md](docs/user-guide.md).

## AI-Driven Research

When you do not know which indicator or parameter set to start with, describe
the thesis and let the catalog workflow draft the first research pass:

```bash
uv run oc research auto "Find a TQQQ trend strategy that exits in high-volatility regimes" \
  --universe TQQQ --timeframe daily
```

The pipeline selects candidate factors from the catalog, runs single-factor IC
diagnostics, drafts a `StrategySpec` with `source: factor_library`, runs the
strategy evidence workflow, and writes a report under `reports/research/auto/`.
Browse the catalog with `oc factor list`, inspect one factor with
`oc factor show <factor_id>`, and add a catalog factor to an existing spec with
`oc factor use-in`.

## Data And Integrations

Open Composer runs without credentials by using sample data and fixtures.
Optional credentials unlock live or cached provider workflows:

| Provider | Environment variables | Purpose |
|---|---|---|
| OpenAI or compatible gateway | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Review cards and LLM-assisted research. |
| Alpaca Paper | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `ALPACA_PAPER=true` | Paper account snapshots, market data, and paper-only order submission. |
| Longbridge | `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`, `LONGBRIDGE_ACCESS_TOKEN` | Market data through the Longbridge SDK. |
| FRED | `FRED_API_KEY` | Macro capability. |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | News sentiment capability. |

Secrets belong in `.env`; `.env` is ignored by Git. Do not commit broker,
OpenAI, Longbridge, Dashboard, or legacy remote secrets.

## Dashboard And Deployment

Local Dashboard is part of the normal setup flow. For a remote personal control
plane, use the VPS deployment script:

```bash
make vps-deploy VPS_DEPLOY_ARGS="--cloudflare-access --dashboard-url https://dashboard.example.com"
```

The VPS hosts the Dashboard as a local service. For mobile-friendly remote
access, keep the Dashboard bound to `127.0.0.1:8000` and publish it through
Cloudflare Tunnel + Cloudflare Access rather than exposing a raw port. Strategy
research, backtests, scans, tests, and file edits remain CLI/file/agent driven.
See [docs/remote-dashboard-deploy.zh.md](docs/remote-dashboard-deploy.zh.md).

## Safety Boundaries

Open Composer is research software, not financial advice.

- Real-money broker writes are outside the MVP boundary.
- Alpaca Paper is the only automated broker write path.
- LLM review is advisory and must be structured.
- Sample, fixture, cache fallback, and trial/research-only data are workflow
  evidence only.
- Promotion and paper readiness require explicit evidence for data quality,
  execution reality, benchmarks, and LLM or alternative-data contribution.

## Development

Use the local verification closure before publishing changes:

```bash
make verify
```

For a lighter Python-only pass:

```bash
make check
```

Use `uv run oc cache status` when you need to inspect local cache and runtime
artifact size without deleting anything.

## Project Docs

- [docs/user-guide.md](docs/user-guide.md) - command-level user guide
- [docs/setup-local.zh.md](docs/setup-local.zh.md) - local setup details and troubleshooting
- [docs/remote-dashboard-deploy.zh.md](docs/remote-dashboard-deploy.zh.md) - VPS Dashboard deployment
- [docs/longbridge-integration.md](docs/longbridge-integration.md) - Longbridge configuration and data scope
- [docs/product-golden-path-codex-quant-review-2026-05-13.zh.md](docs/product-golden-path-codex-quant-review-2026-05-13.zh.md) - no-context Codex starting review document
- [docs/strategy-research-product-remediation-plan-2026-05-26.zh.md](docs/strategy-research-product-remediation-plan-2026-05-26.zh.md) - strategy research workflow remediation plan for no-context agent review
- [docs/plan-step-1-simplification-2026-05-22.zh.md](docs/plan-step-1-simplification-2026-05-22.zh.md) - Step 1 simplification and legacy cleanup plan
- [docs/plan-step-2-worksession-llm-factor-2026-05-22.zh.md](docs/plan-step-2-worksession-llm-factor-2026-05-22.zh.md) - Step 2 long-lived worksession and LLM factor plan
- [docs/plan-step-3-dashboard-first-2026-05-22.zh.md](docs/plan-step-3-dashboard-first-2026-05-22.zh.md) - Step 3 Dashboard-first interaction plan
- [docs/local-product-optimization-plan-2026-05-25.zh.md](docs/local-product-optimization-plan-2026-05-25.zh.md) - local-first product optimization plan
- [docs/plan-step-6-factor-catalog-and-ai-research-2026-05-26.zh.md](docs/plan-step-6-factor-catalog-and-ai-research-2026-05-26.zh.md) - Step 6 factor catalog and auto research plan
- [docs/plan-step-6-5-auto-research-fixes-2026-06-08.zh.md](docs/plan-step-6-5-auto-research-fixes-2026-06-08.zh.md) - Step 6.5 auto research fixes
- [docs/plan-step-6-6-pre-step7-research-hardening-2026-06-08.zh.md](docs/plan-step-6-6-pre-step7-research-hardening-2026-06-08.zh.md) - Step 6.6 pre-Step 7 research evidence hardening
- [docs/plan-step-6-7-tradeable-signal-generation-2026-06-16.zh.md](docs/plan-step-6-7-tradeable-signal-generation-2026-06-16.zh.md) - Step 6.7 tradeable auto research signal generation fix
- [docs/plan-step-7-conditional-ml-decay-llm-2026-05-26.zh.md](docs/plan-step-7-conditional-ml-decay-llm-2026-05-26.zh.md) - Step 7 conditional ML, decay, and LLM plan

## License

MIT. See [LICENSE](LICENSE).
