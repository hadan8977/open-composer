# Local setup

Use this guide for single-machine development, offline trials and local research. The default surface is CLI/files plus a read-only Cockpit. Remote viewing uses Cloudflare Access; commands use Paseo. See [the read-only Cockpit design](plan-step-18-readonly-cockpit-2026-09-19.zh.md).

Commands below match the repository setup scripts; this documentation pass did not install dependencies, start services or validate external providers.

## Quick start

Linux/macOS:

```bash
make start
# Or preview the setup commands:
./scripts/setup-local.sh --dry-run
```

Windows PowerShell:

```powershell
.\scripts\setup-local.ps1
```

The six-step scripts install Python dependencies, check the repository, initialize `.env`, inspect environment configuration and build `reports/dashboard/catalog.json`. They print `[N/6] <title> OK/WARN/FAIL/SKIP` and can be rerun. Read warnings: the shell script reports repository-check blocks as warnings rather than treating its final completion message as research/paper readiness.

## 0. Tools

| Tool | Requirement | Installation example |
|---|---|---|
| uv | Python environment/package manager; prior setup baseline was 0.11+ | `winget install astral-sh.uv` on Windows; use the official uv installer on Linux/macOS. |
| Git | Prior setup baseline was 2.30+ | System package manager or existing installation. |
| Python | Project requires 3.11+; uv can provision the interpreter | Follow `pyproject.toml` and the lockfile. |
| Node/pnpm | Only for the optional React Cockpit build; Node 20+ baseline | Install Node LTS and run `corepack enable`. |

The default FastAPI/Jinja Cockpit needs no Node runtime. The deleted `dashboard/` Vite app is not the setup path; the optional current frontend is `frontend/cockpit-v2` and uses pnpm.

## 1. Manual equivalent of the six steps

```bash
uv --version
uv sync --extra workbench
uv run oc repo check
```

`uv sync` creates `.venv`. For network failures, inspect package-index access (`UV_INDEX_URL` if intentionally using another index). Windows hardlink warnings are usually nonfatal; set `UV_LINK_MODE=copy` in the process environment if needed.

Repository check success ends with `status=ok ready=yes`. For blocks, read `reports/repo/repo-check.md` and its `Next action`; `reports/repo/repo-check.json` records `extra_docs`/`allowed_docs`. An intentional document inventory change belongs in the maintained `CURRENT_DOCS` inventory; do not delete useful files merely to clear a check.

Initialize `.env` only if absent; the setup script copies `.env.example` automatically. Manual examples for a new installation:

```bash
cp .env.example .env
chmod 600 .env
```

```powershell
Copy-Item .env.example .env
```

Fill only the optional keys needed for your work. Keep `.env` ignored by Git and `ALPACA_PAPER=true`.

```bash
uv run oc doctor --plain
uv run oc cockpit index
```

Doctor distinguishes available Python/packages from missing optional keys. The index reads `strategy_specs/`, `signal_logs/` and `reports/` into `reports/dashboard/catalog.json`; zero strategies/signals is normal in a new checkout. Fixture-backed capabilities support offline workflows, not paper-ready market evidence.

## 2. Optional Cockpit

```bash
uv run oc cockpit serve --port 8770
```

Open `http://127.0.0.1:8770`. The application has no internal authentication and refuses wildcard bindings (`0.0.0.0`, `::`, `*`). Remote access requires the configured authenticated edge; do not expose the application directly.

For the optional React view at `/v2/`:

```bash
make cockpit-v2
```

This runs pnpm dependency installation, TypeScript checking and Vite build under `frontend/cockpit-v2`. Output is `open_composer/cockpit/static/v2/`, mounted by `oc cockpit serve` when present. The server does not run Node; `/` remains available without the optional build.

## 3. Optional environment configuration

Use [.env.example](../.env.example) and the relevant capability configuration as the maintained source for defaults. No credentials are needed for sample workflows; enabling real integrations requires their own access and applicable task authorization.

| Purpose | Variables | Notes |
|---|---|---|
| LLM reviews/drafts | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` | Model defaults come from configuration; a draft without `--use-llm` does not need a model call. |
| Alpaca Paper/data | `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `ALPACA_PAPER`, `ALPACA_API_BASE_URL`, `ALPACA_DATA_FEED` | Keep paper mode true and the paper endpoint. `iex`/`sip` availability depends on the account; do not infer a subscription from a configured string. |
| News | `ALPHA_VANTAGE_API_KEY` | Missing credentials can leave the capability on fixtures. |
| Macro | `FRED_API_KEY` | Historical/vintage requirements are separate from API access. |
| Longbridge | `LONGBRIDGE_APP_KEY`, `LONGBRIDGE_APP_SECRET`, `LONGBRIDGE_ACCESS_TOKEN` | Market-data integration; not new order authority. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Create a bot through BotFather and configure its destination separately. |
| Email digests | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `SMTP_TO` | See `config/notifications.yaml.example`. |

Provider account portals supply keys; never paste secret values into reports, prompts or Git. Configuring a connector does not grant permission to send notifications or submit orders.

### Remote viewing

The public hostname should terminate at Cloudflare Tunnel/Access and forward to `http://127.0.0.1:8770`. A `cloudflared tunnel run --token-file` systemd service is the established connector shape. Configure the team domain, audience and allowed identities in Cloudflare Zero Trust; there is no one-command deployment in this guide. The Cockpit exposes no command endpoint. Use a Paseo session for commands, under its own permissions.

## 4. Troubleshooting

| Symptom | Check |
|---|---|
| uv absent | Install uv and reopen the shell, then check `uv --version`. |
| `docs_inventory blocked` | Read the reported inventory difference and intended repository scope. |
| Port occupied | `uv run oc cockpit serve --port 8771`. |
| `/v2/` module 404 | Confirm the optional build and `static/v2/` output. |
| `/v2/` API fetch failure | Confirm the Cockpit service and request path; distinguish `/` from `/v2/`. |
| GNU Make absent on Windows | Run the underlying commands directly; installing Make is optional. |
| Verification fails | Inspect the actual failure, including native-library/platform requirements or missing integration credentials. Do not relabel failed tests as passing. |

For a relevant local smoke check, the existing focused command is:

```bash
uv run pytest tests/test_repo_check.py tests/test_cockpit_api.py tests/test_notifications.py tests/test_cockpit_catalog.py -q
```

Run checks appropriate to your change and only one pytest process at a time under [the memory policy](runbook-memory.zh.md). Setup or documentation editing does not itself require a whole-repository test run.

## 5. Next actions

| Task | Entry |
|---|---|
| Draft a strategy | `uv run oc strategy draft --idea "QQQ 15min breakout with volume filter"` |
| Validate a draft | `uv run oc spec validate <spec>` |
| Inspect risk-dependent evidence | `uv run oc harness plan <spec>` |
| Sample backtest | `uv run oc backtest strategy_specs/drafts/<strategy>.yaml` |
| Assess paper readiness | `uv run oc paper readiness <strategy>` |
| Preview notification handling | `uv run oc notify test --dry-run` |

Use the [strategy research skill](../.agents/skills/strategy-research-orchestrator/SKILL.md) for actual economic experiments and lifecycle changes. A locally working catalog, fixture backtest or readiness command does not activate paper trading.
