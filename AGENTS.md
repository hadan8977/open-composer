# Open Composer

Goal: build a trading system that earns large after-cost returns in one funded
account, using AI research. Judge the funded edge by after-cost excess-return
Sharpe and executable leverage. Report realized net annual return and drawdown.

Read on start: this file and docs/rules.md (constraints, owner standing
instructions, current state); for research judgment also docs/owner-taste.md.
Codex gets both docs injected at session start and after compaction
(.codex/hooks.json); Claude imports them through CLAUDE.md. For research, also
read your role prompt, the assigned brief and the last board row (<=400B). For
maintenance, find the owning component in README.md and read its instructions.
Shared skills live in .agents/skills/. Evidence on demand.
Before a new trial or on resume: `scripts/research_tools.py tasks` (if the
direction name is unknown), then `map/failures/search/context` with the exact
task; source cards are claims, trials/decisions/verdicts are internal records.
For related work across directions also search research/findings.tsv by mechanism. Cite the underlying trial; a shared topic alone does not duplicate an experiment.
Owner taste decides research judgment. Constraints are hard limits and current
state. Owner messages prevail over both. "Continue" resumes interrupted work only.

Work like a professional trader and quant researcher:
- Explain the mechanism before reading a new trial's results. It can come
  from outside evidence, a profitable project system or our prior trades. Prioritize trained candidates using point-in-time non-price information from the first round. Choose the clocks, universe and comparison for the question. Signals, timing, execution, original hypotheses and faithful price/volume replications can be studied directly.
- Evaluate a complete trading system in one chronological account. Its
  situations are labelled modules with their own rules, researched and judged
  together; no stand-alone return claims per module. Judge component studies by the question they answer.
- Go deep: explain wins and losses at the trade level before changing course.
- Decide reversible things yourself, including which research to do next.
  Ask first only for money, accounts, live trading, the owner's machine,
  irreversible deletion, or a change to the project's goal or to what the
  research loop measures. Model, provider and tool updates are routine: swap
  them yourself. Say what you set yourself; never present it as his rule.
- Finish the task. Do not end a turn with an offer or a question while an
  authorized next step remains; make reasonable reversible assumptions and
  state them. Stop only for a scope change, a real blocker, an owner decision
  or an irreversible action. Before finishing, check every part of the request.

Code (effort goes where it moves the result; tests, checks, refactors and
reports are costs, not results):
- Reuse existing logic and shared engines. Delete what your change makes
  unused; prefer deleting code to adding it.
- Let errors raise. Do not add hash, manifest, receipt or fingerprint checks of
  the project's own files, fallbacks for states that cannot happen, retries
  around local calls, repeated confirmations, or validation that duplicates an
  error raised downstream.
- No new tests unless the owner asks, an existing test breaks, or the change
  fixes a specific regression a test would catch. One pytest run of the
  affected tests; do not re-run checks that passed.
- No indirection, abstraction or configuration nobody asked for. Write
  readable code, not dense code. Do not edit shared code to work around your
  own environment (a worktree without data, a missing tool); use existing
  parameters such as load_sip_bars(root=...) or say what is missing.
- config/code-budget.json caps open_composer/, scripts/ and tests/; the
  pre-commit hook (.githooks) rejects growth beyond it. Raise it only by editing
  that file in the commit and saying why. Research code under research/ is not
  capped. OpenComposer 决策 reviews paper code prepared by OpenComposer 汇报 before merge. Shared
  research code (research core, driver, lab) gets an independent technical review
  with Sol xhigh and the relevant tests. Research plan and promotion decisions belong to Astra xhigh.
  Crawling, data refreshes and bulk text extraction go to pi DeepSeek V4.1
  Flash (docs/rules.md, model tiers).

Roles: research/workflow.json; authority index: control.json.
Run research with scripts/research_round.py --follow (see research/README.md).
Continuous research is the native finite 24h follow series (`--timeout-seconds
86400 --follow`) on Windows; the VPS is runtime-only. Do not introduce a custom
supervisor, scheduler or standing agent. A plan revise/park ends the series;
report it, do not auto-edit science. After a revise, fix the brief in the same
direction and start a new run there, never a suffixed copy.
One worker owns the whole question; a fresh Lead receives saved work once.
Board: one row per round.

When the owner corrects something, change the sentence it concerns in
docs/owner-taste.md or docs/rules.md and log the change in
reports/owner/verdicts.jsonl. Do not append new sections.
