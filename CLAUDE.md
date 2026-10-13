机主2026-10-13现行方法入口（优先于下文旧模型默认、固定研究轮与逐次复核要求）：先读 `docs/task-owned-research.zh.md`，角色单处配置为 `config/research-agent-roles.json`；Astra/xhigh 写详细完整 brief 与最终判断，Sol/xhigh 独立拥有完整执行任务，Sol 整理既有证据并按原路线汇报。旧固定 Astra 研究轮退役，恢复也不按旧周期重启。

首先核对 `reports/research/control/owner-compute-hold.json`。当前全部研究、训练、代理、自动研究与报告生成暂停；缺失或不可读不能自动启动，仅机主明确恢复的范围可继续。本次明确授权的方法维护与 GitHub 发布不解除暂停、不启动经济工作或设备；已完成结果、原生断点、累计预算/试验、冻结标准和既有模拟盘授权保留。历史正文保留供追溯，冲突时以此入口和现行方法为准。

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
- Run `uv run ruff format .`, `uv run ruff check .`, and `uv run pytest` after code changes. Run `uv run oc repo check --strict` and `make verify` for product-surface changes.

Skills are mirrored from `.agents/skills/` into `.claude/skills/` by `uv run python scripts/sync-agent-skills.py`. Do not hand-edit a second skill corpus.
