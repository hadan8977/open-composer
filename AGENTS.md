# Open Composer Agent Rules

## Product
- Open Composer is a personal AI strategy workbench.
- `StrategySpec` is the source of truth for strategy behavior.
- Codex creates specs, Python, Pine, reports, tests, review cards, and journals.

## Workflow
- Create draft strategies first.
- Validate specs before generating code or Pine.
- Generate a report for every backtest.
- Log every signal before review or paper order submission.
- Link journal entries and paper orders to signal IDs.
- Choose data, event, macro, and news sources through `capabilities/registry.yaml`.
- Run capability evaluation before adding a new required strategy capability.

## Safety
- Real-money broker write access is out of scope for this MVP.
- Alpaca Paper orders require explicit command confirmation and active `paper_auto` specs.
- LLM review is advisory and must be structured.
- MCP tools are research and context tools.

## Implementation
- Keep the first product surface as CLI plus files.
- Keep sample-data workflows runnable without external credentials.
- Run `uv run ruff format .`, `uv run ruff check .`, and `uv run pytest` after changes.
