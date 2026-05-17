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
| Dashboard | Local artifact read model with Monitor, Strategies, and Activity views. |
| Paper safety | Alpaca Paper-only automation with explicit confirmation, readiness gates, kill switch, and audit artifacts. |
| Remote mode | Vercel password-session BFF plus a VPS daemon; browser sessions never receive daemon secrets. |

## Typical Workflow

1. Draft or edit a `StrategySpec`.
2. Run the research report for the spec.
3. Review factor, execution, data, benchmark, LLM contribution, and paper
   readiness gates.
4. Promote only when the report evidence is sufficient.
5. Use paper automation only for active `paper_auto` specs that pass readiness.

For command-level usage, see [docs/user-guide.md](docs/user-guide.md).

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
OpenAI, Longbridge, Vercel, or remote daemon secrets.

## Dashboard And Deployment

Local Dashboard is part of the normal setup flow. For a remote personal control
plane, use the VPS deployment script after setting `VERCEL_TOKEN`:

```bash
make remote-deploy
```

Remote Dashboard mode keeps long-running work on the daemon. Vercel handles the
password session, CSRF, HMAC signing, and proxy layer only. See
[docs/remote-dashboard-deploy.zh.md](docs/remote-dashboard-deploy.zh.md).

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
- [docs/remote-dashboard-deploy.zh.md](docs/remote-dashboard-deploy.zh.md) - VPS and Vercel remote Dashboard deployment
- [docs/longbridge-integration.md](docs/longbridge-integration.md) - Longbridge configuration and data scope
- [docs/product-golden-path-codex-quant-review-2026-05-13.zh.md](docs/product-golden-path-codex-quant-review-2026-05-13.zh.md) - no-context Codex starting review document
- [docs/research-contract-p0-p2-plan-2026-05-17.zh.md](docs/research-contract-p0-p2-plan-2026-05-17.zh.md) - research contract and StrategyDAG execution plan
- [docs/product-structure-efficiency-review-2026-05-17.zh.md](docs/product-structure-efficiency-review-2026-05-17.zh.md) - product structure and redundancy review
- [docs/product-efficiency-optimization-roadmap-2026-05-17.zh.md](docs/product-efficiency-optimization-roadmap-2026-05-17.zh.md) - Dashboard, strategy workflow, and research-kernel optimization plan
- [docs/product-mvp-hardening-research-plan-2026-05-17.zh.md](docs/product-mvp-hardening-research-plan-2026-05-17.zh.md) - MVP hardening plan for Dashboard, strategy iteration, and the shared research kernel
- [docs/harness-engineering-agent-quant-review-2026-05-17.zh.md](docs/harness-engineering-agent-quant-review-2026-05-17.zh.md) - harness engineering plan for stronger agent, skill, workflow, and quant research constraints
- [docs/harness-engineering-expanded-research-log-2026-05-17.zh.md](docs/harness-engineering-expanded-research-log-2026-05-17.zh.md) - expanded research log for agent, quant, financial LLM, data, and risk-control references
- [docs/harness-engineering-expanded-architecture-review-2026-05-17.zh.md](docs/harness-engineering-expanded-architecture-review-2026-05-17.zh.md) - expanded Honest/Harness engineering architecture review and implementation plan

## License

MIT. See [LICENSE](LICENSE).
