---
name: ultracode-reviewer
description: >
  Use for Open Composer codebase review, project optimization, architecture review,
  implementation planning, or broad bug/risk assessment. Trigger whenever the user
  asks to review, audit, evaluate, optimize, harden, fix a plan for, or improve
  Open Composer project code or research workflow, even if the user does not say
  "ultracode". Applies an UltraCode-style workflow: define objective and acceptance,
  decompose into independent review lanes, use subagents when explicitly available
  or already authorized, integrate findings, and produce a prioritized solution plan.
---

# UltraCode Reviewer

Use this skill for Open Composer project reviews and optimization work. The goal is
not to add ceremony; it is to avoid shallow single-pass conclusions when the task
spans code, quant research, data evidence, execution safety, and product workflow.

## Trigger

Use this skill by default when the user asks to:

- review, audit, evaluate, or assess Open Composer code or workflows;
- optimize, harden, improve, or refactor project code;
- diagnose broad failures across research, backtest, promotion, paper readiness, or CLI;
- propose a professional implementation plan before coding.

If the task is a tiny local edit with an obvious fix, keep the workflow lightweight:
state the objective, inspect the relevant files, patch, and verify.

## Workflow

### 1. Frame

Write down the concrete objective and acceptance criteria before deep work:

- user goal;
- product boundary affected: `StrategySpec`, research workflow, data capability,
  execution, paper safety, dashboard, or repo hygiene;
- non-negotiables from `AGENTS.md`;
- what counts as fixed or adequately reviewed.

### 2. Decompose

Split broad work into review lanes. Choose only lanes relevant to the request:

- Code path and tests: CLI, function signatures, error handling, regression tests.
- Quant method: IC/OOS, train/test separation, overfit risk, benchmark family,
  factor concentration, parameter search.
- Data capability: source tier, fallback/cache/sample handling, provenance,
  `capabilities/registry.yaml`.
- Execution and paper safety: signal logs, target weights, order windows, broker
  boundaries, readiness gates.
- Product UX: command output, report clarity, stale artifacts, recovery after failure.

### 3. Use Sidecar Review When Authorized

If subagents are available and this skill has triggered, use 2-4 independent
sidecar reviews for broad tasks. Keep the parent session responsible for
integration and final judgment. For tiny or tightly scoped edits, skip sidecars.

Good sidecar prompts are concrete and read-only unless implementation ownership is
explicitly assigned. Give each sidecar one lane, for example:

- "Review `oc research auto` evidence path. Return blockers, line refs, tests."
- "Review quant methodology for leakage and overfit. Return risks and acceptance."
- "Review data/paper readiness gates. Return hard blockers before paper trading."

Do not delegate the immediate blocking task if the parent can fix it faster. While
sidecars run, inspect non-overlapping files locally.

### 4. Verify Claims Locally

Do not rely only on text review. Use local commands where practical:

- `rg` for call paths and tests;
- focused pytest for the affected module;
- `oc ... --help` to verify command shape;
- small smoke runs only when they do not create unacceptable artifact churn.

If a smoke run writes artifacts, inspect `git status --short` and clean, stash, or
report generated files according to the user's cleanup preference.

### 5. Synthesize

Merge sidecar and local findings into:

- P0 blockers: current failures, incorrect success states, safety violations.
- P1 method/product risks: likely wrong conclusions, weak gates, misleading reports.
- P2 polish/scale items: ergonomics, performance, cleanup, docs.

Every high-severity finding should include file/line references and the concrete
behavior it causes.

### 6. Plan Before Editing

For non-trivial fixes, propose an execution plan with waves:

- scope and files;
- expected tests;
- acceptance checks;
- what is intentionally not touched.

When the user has already authorized execution, start implementing after the plan.
When the user asked for review first, stop at the plan.

## Open Composer Review Biases

- Treat `StrategySpec` as the source of truth.
- Separate workflow pass, research pass, LLM contribution pass, and paper-ready pass.
- Sample, fixture, cache fallback, and trial-only data are not paper-ready evidence.
- Real-money broker write access is out of scope.
- Paper automation needs explicit readiness gates, signal logs, audit links, and
  broker-scope checks.
- Optimization must include bounded search space, trial ledger, OOS/walk-forward
  evidence, benchmark family, cost stress, and overfit risk notes.
- Do not promote a strategy because a single backtest looks good.

## Output Shape

For review-only tasks, answer in this order:

1. Overall verdict.
2. Findings by priority with file/line references.
3. Recommended plan with acceptance checks.
4. Open questions, maximum three.

For implementation tasks, after edits include:

- changed files;
- verification commands and results;
- remaining risks.
