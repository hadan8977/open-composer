# Open Composer Claude Code Rules

@docs/research-mission.zh.md

Read `docs/research-mission.zh.md` and the latest dated section of `docs/current-view.zh.md` before choosing work. The user's priority is time to credible near-term profit after costs, including regime-specific opportunities. Search and open primary sources first; reuse existing implementations and negative evidence before allocating compute. Routine research is delegated: superseded per-card approval proposals must not stall it. Unknown background budgets and new broker authorizations remain separate decisions. New v3 iterations require `oc research direction-check <path>` and the existing iteration gate.

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
- Cockpit is read-only and exposes no command entry point; remote access is authenticated at the edge by Cloudflare Access; commands are issued through a Paseo session.
- Do not expose `.env`, private keys, remote shared secrets, broker secrets, or access tokens in artifacts.
- Research scope (owner, 2026-09-29): everything Alpaca Paper can trade -- US stocks and ETFs long AND short (short only easy-to-borrow names, with borrow cost modeled), margin within Alpaca limits, any frequency including intraday, overnight and extended hours, options Levels 1-3 where historical data allows, and crypto spot. Do not narrow research to ETFs, long-only or low frequency by habit. Running any new strategy on the paper account still needs the owner's authorization; live trading stays out of scope.
- Cloud compute: work that does not fit this box (3.9 GB RAM, 6 old cores, no GPU) -- large stock/factor panels, model training, wide parallel backtests, anything needing a GPU -- runs on Modal first (owner-approved 2026-09-28, free $30/month credit only; token in `~/.modal.toml`). Every launch must first pass `python3 scripts/modal_budget.py check --job <name> --cpu <cores> --memory-gib <GiB> --timeout-min <min> [--gpu T4]` (month cap $25; exit 2 means do not launch) and the function `timeout=` must equal the checked minutes. Never upload `.env`, broker/API keys or Drive credentials. Paying beyond the free credit or adding another provider is an owner decision. Details: `docs/runbook-autonomous-round.zh.md` section 5.
- Disk: `scripts/disk_guard.py` runs hourly from cron at lowest priority and cleans caches, old `/tmp` entries and expired backups (only after a verified Drive copy). Research tasks and rounds have no disk steps (owner 2026-10-02: keep it light). Details: `docs/runbook-disk.zh.md`.
- Run `uv run ruff format .`, `uv run ruff check .`, and `uv run pytest` after code changes. Run `uv run oc repo check --strict` and `make verify` for product-surface changes.

Skills are mirrored from `.agents/skills/` into `.claude/skills/` by `uv run python scripts/sync-agent-skills.py`. Do not hand-edit a second skill corpus.
