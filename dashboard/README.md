
# Open Composer Dashboard

This React surface renders the repo-native dashboard read model. Strategy edits
and order submission remain behind CLI safety gates. When served through
`make dashboard-serve`, the Paper page can call the local command API for paper
status refreshes, broker order sync, account / position sync, monitor refreshes,
kill-switch changes, and workspace readiness preparation.

## Data Source

The app reads `reports/dashboard/catalog.json` through a Vite virtual module. If
the catalog is missing, the UI renders an empty state with instructions instead
of falling back to mock strategy data.

When served through `make dashboard-serve`, the dashboard also syncs the latest
catalog from `/api/dashboard/catalog` so the visible read model stays current.

Generate the catalog before launching or building the app:

```bash
make dashboard-catalog
```

## Running

```bash
make bootstrap
make deploy-prepare
make dashboard-dev
make dashboard-build
make dashboard-serve
```

`make dashboard-serve` serves the built Dashboard and exposes local endpoints for
the browser command center:

- `GET /api/dashboard/health`
- `GET /api/dashboard/catalog`
- `POST /api/dashboard/command-plan`
- `POST /api/dashboard/command-run`

The Paper command center reads `/api/dashboard/catalog` on load and after command
execution so its status panel can reflect the latest paper summary, including
account and position snapshot timestamps.

The command center also exposes `system.prepare_workspace` and
`system.readiness.refresh`, which rebuild local deployment artifacts and
readiness reports through the same command-plan / confirmation gate.

The Strategy Library can create a new draft StrategySpec through
`strategy.draft`; the generated YAML stays under `strategy_specs/drafts/` and
is audited like other Dashboard commands.

Strategy Detail can also run `strategy.workflow.verify`, `strategy.validate`,
and `strategy.capabilities.refresh`, writing local validation, capability,
backtest, scan, workflow, and paper readiness reports before approval or paper
activation.

Set `OPEN_COMPOSER_DASHBOARD_TOKEN` or pass `uv run oc dashboard serve
--api-token <token>` to require `X-Open-Composer-Token` on `/api/dashboard/*`.
The browser can store the token by opening `http://127.0.0.1:8000/?token=<token>`
once.

Direct npm commands still work from this folder after the catalog exists:

```bash
npm run dev
npm run build
```
