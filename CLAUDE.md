# Open Composer Claude Code Rules

Open Composer is a personal AI strategy workbench. `StrategySpec` is the source of truth for strategy behavior, and CLI plus files remain the first product surface.

Use the same project rules as Codex:

- Read `AGENTS.md` before changing strategy, dashboard, data, paper, or agent workflow files.
- Create draft strategies first, then validate specs before generating Python, Pine, reports, tests, review cards, or paper automation artifacts.
- Choose market, event, macro, and news sources through `capabilities/registry.yaml`; run capability evaluation before adding a new required strategy capability.
- Every strategy design must include parameter ranges, method variants, factor variants, and a bounded search space.
- New research rounds bind verified source cards to a schema-v2 brief and preregister every parameterized/model candidate in a machine-readable manifest before backtests or training.
- Every backtest must produce a report; every signal must be logged before review or paper order submission.
- Promotion must check benchmark family, out-of-sample evidence, walk-forward evidence, costs, data source sensitivity, and sample/fallback caveats.
- Keep `workflow_pass`, `research_pass`, `llm_contribution_pass`, and `paper_ready_pass` separate.
- LLM, news, event, and macro inputs must become point-in-time feature packets before they can affect trading behavior.
- Alpaca Paper is the only automated simulated broker write path; real-money broker write access is out of scope.
- Dashboard commands must use the confirmed command surface. Remote Dashboard commands must go through password session, Vercel BFF, HMAC, async job, backup, audit, and double confirmation for Red actions.
- Do not expose `.env`, private keys, remote shared secrets, broker secrets, or access tokens in artifacts.
- Run `uv run ruff format .`, `uv run ruff check .`, and `uv run pytest` after code changes. Run `uv run oc repo check --strict` and `make verify` for product-surface changes.

Skills are mirrored from `.agents/skills/` into `.claude/skills/` by `uv run python scripts/sync-agent-skills.py`. Do not hand-edit a second skill corpus.
