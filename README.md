# Open Composer

Open Composer turns trading ideas into strategy specifications, costed account
comparisons and reproducible research. The primary workspace runs on native
Windows. The VPS runs the authorized paper strategies, their input refresh
and reconciliation, and the read-only Cockpit.

| Work | Entry |
|---|---|
| Project authority | [AGENTS.md](AGENTS.md), [owner preferences](docs/owner-taste.md), [rules](docs/rules.md), [switches](control.json) |
| Research | [Workflow](research/README.md), [priorities](docs/research-mission.zh.md), [research tools](docs/research-tools.md), [evaluation](docs/evaluation-standard.zh.md) |
| Code and strategy definitions | `open_composer/`, `scripts/`, `tests/`, `strategy_specs/` |
| Evidence and inputs | `research/`, `reports/`, [market data](docs/local-data-catalog.zh.md), `data/` |
| Configuration and review contracts | `config/`, `capabilities/`, `schemas/`, `harness/`, `prompts/`, `.agents/skills/` |
| Paper and website | [Operations](docs/local-vps-migration.zh.md), `deploy/`, `frontend/cockpit-v2/` |
| Setup and CLI | [Local setup](docs/setup-local.zh.md), [user guide](docs/user-guide.md) |

Run `uv run --no-sync oc --help` for the CLI, or start from the [research
workflow](research/README.md) to resume an assigned direction.
