# Open Composer

Open Composer is a personal AI strategy workbench for turning trading ideas
into auditable `StrategySpec` files, deterministic backtests, research
reports, and paper-trading readiness checks.

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

The setup path is idempotent. It installs Python dependencies, creates `.env`
from `.env.example` when needed, and builds the read-only cockpit catalog
under `reports/dashboard/`. The read-only Cockpit runs from `open_composer/cockpit/`; its React view is built from `frontend/cockpit-v2/`.
External API keys are optional; sample data and fixtures are enough for a
local smoke test. Day-to-day work happens through the CLI (`uv run --no-sync oc ...`)
and Codex/Claude Code work sessions.

## Product Map

| Area | What it does |
|---|---|
| Strategy specs | YAML `StrategySpec` drafts, approvals, activation state, version diffs, and rollback. |
| Research reports | Backtests, promotion gates, research contracts, factor diagnostics, execution reality, cost sensitivity, and data quality. |
| Data capabilities | Sample OHLCV, Alpaca, Longbridge, SEC filings, FRED macro, Alpha Vantage news, and GDELT through a registry. |
| Cockpit catalog | Read-only artifact aggregation (`oc cockpit index`) over strategies, runs, signals, orders, and reviews; native and React browser views over the same read-only API. |
| Paper safety | Alpaca Paper-only automation with explicit confirmation, readiness gates, kill switch, and audit artifacts. |
| Deployment | CLI/file/agent driven; remote access uses Cloudflare Access. |

## Two Ways To Use Open Composer

| Audience | Primary interface |
|---|---|
| Day-to-day user | CLI (`uv run --no-sync oc ...`); create, continue, review, promote, and monitor strategies from the terminal. |
| Agent (Codex / Claude Code) | CLI plus file contracts: `oc strategy ...`, `projects/{id}/queue.jsonl`, `projects/{id}/trace.jsonl`, and `projects/{id}/context.md`. |

Agent and CLI paths write the same project files, so sessions can close
without losing strategy context.

## Typical Workflow

1. Use `oc strategy draft` (or a Codex/Claude Code work session) to create a Strategy Project from a natural-language idea.
2. Continue research from the CLI: inspect trace, review spec diff, and queue evidence or LLM-factor materialization.
3. Review factor, execution, data, benchmark, LLM contribution, and paper readiness gates.
4. Promote only when the report evidence is sufficient.
5. Use paper automation only for active `paper_auto` specs that pass readiness.

For command-level usage, see [docs/user-guide.md](docs/user-guide.md).

## AI-Driven Research

When you do not know which indicator or parameter set to start with, describe
the thesis and let the catalog workflow draft the first research pass:

```bash
uv run --no-sync oc research auto "Find a TQQQ trend strategy that exits in high-volatility regimes" \
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

## Cockpit And Deployment

The Cockpit exposes read-only views of research and paper activity. Remote access
uses Cloudflare Access. Commands use the CLI or an authorized agent session.
Pure-Codex research runs through `scripts/research_round.py`; role bindings are
in `research/workflow.json`, while financial evidence remains provider-neutral.

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

Use `uv run --no-sync oc cache status` when you need to inspect local cache and runtime
artifact size without deleting anything.

## Project Docs

- [research/README.md](research/README.md) — no-context Codex entry: file contracts, finite research rounds and recovery.
- [docs/user-guide.md](docs/user-guide.md) — CLI reference.
- [docs/research-mission.zh.md](docs/research-mission.zh.md) — investment objectives.
- [docs/rules.md](docs/rules.md) — current research, execution and resource rules.
- [docs/restructure-progress.zh.md](docs/restructure-progress.zh.md) — implementation and validation status.
- [docs/archive/](docs/archive/) — historical plans and retired agent material; not startup instructions.

## License

MIT. See [LICENSE](LICENSE).
