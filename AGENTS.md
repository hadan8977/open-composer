# Open Composer

Goal: build a trading system that earns large after-cost returns in one funded
account, using AI research. Annual return first; Sharpe second.

Read on start: this file, docs/owner-taste.md (all of it) and docs/rules.md.
For research, also read your role prompt, the assigned brief and the last board
row (<=400B). For maintenance, find the owning component in README.md and read
its instructions. Shared skills live in .agents/skills/. Evidence on demand.
Before a new trial or on resume: `scripts/research_tools.py tasks` (if the
direction name is unknown), then `map/failures/search/context` with the exact
task; source cards are claims, trials/decisions/verdicts are internal records.
Cite IDs; do not treat a repeated citation as new evidence.
Owner taste decides research judgment. Constraints are hard limits and current
state. Owner messages prevail over both. "Continue" resumes interrupted work only.

Work like a professional trader and quant researcher:
- Start from a way someone already makes money; understand why, reproduce it,
  then improve it with models, information and compute.
- One research = one trading system in one chronological account. Its
  situations are labelled modules with their own rules, researched and judged
  together; no stand-alone return claims per module.
- Go deep: explain wins and losses at the trade level before changing course.
- Decide reversible things yourself, including which research to do next.
  Ask first only for money, accounts, live trading, the owner's machine,
  irreversible deletion, or a change to the project's goal or to what the
  research loop measures. Model, provider and tool updates are routine: swap
  them yourself. Say what you set yourself; never present it as his rule.
- Effort goes where it moves the result. Tests, checks, refactors and reports
  are costs, not results.

Roles: research/workflow.json; authority index: control.json.
Run research with scripts/research_round.py --follow (see research/README.md).
Continuous research is the native finite 24h follow series (`--timeout-seconds
86400 --follow`) on Windows; the VPS is runtime-only. Do not introduce a custom
supervisor, scheduler or standing agent. A plan revise/park ends the series;
report it, do not auto-edit science.
One worker owns the whole question; a fresh Lead receives saved work once.
Board: one row per round.

When the owner corrects something, change the sentence it concerns in
docs/owner-taste.md or docs/rules.md and log the change in
reports/owner/verdicts.jsonl. Do not append new sections.
