---
name: ultracode-reviewer
description: >
  Use for Open Composer codebase review, project optimization, architecture review,
  implementation planning, or broad bug/risk assessment. Trigger whenever the user
  asks to review, audit, evaluate, optimize, harden, fix a plan for, or improve
  Open Composer project code or research workflow, even if the user does not say
  "ultracode". Applies an UltraCode-style task-graph workflow with bounded subagents,
  adversarial review, evidence-based integration, and explicit acceptance gates.
---

# UltraCode Reviewer V2

Use this skill to prevent broad Open Composer work from collapsing into one shallow
pass. It is a controller protocol, not a requirement to maximize agent count.

## Trigger

Use by default for project review, architecture, optimization, hardening, broad bug
assessment, research-workflow changes, and any plan spanning multiple product
boundaries. For a tiny local edit, keep the same protocol but execute it serially.

## 1. Objective, Boundaries, Acceptance

Before deep work, record:

- the user outcome and current evidence;
- affected boundaries such as `StrategySpec`, data, research, execution, paper,
  dashboard, or repository governance;
- non-negotiables from `AGENTS.md` and user instructions;
- exact commands, artifacts, or behavioral checks that prove completion;
- external or time-dependent evidence that implementation cannot manufacture.

Do not call a workflow complete merely because code or an agent response exists.

## 2. Dependency Graph

Build a small task DAG before delegation. Each node should define:

- `id`, objective, and bounded context;
- `depends_on` and whether it is on the critical path;
- owner role, read set, and exclusive write set;
- expected evidence and acceptance checks;
- stop condition and intentionally unverified scope.

Only ready nodes with no unresolved dependencies may start. Preserve hard wave order.

## 3. Critical Path and Concurrency

Keep architecture decisions, conflict arbitration, integration, and final acceptance
with the parent integrator. Use subagents for bounded exploration, domain review,
implementation with disjoint ownership, tests, or triage.

Parallelize only independent ready nodes. Choose concurrency dynamically from useful
parallel work and platform limits; never use a fixed sidecar count. Do not delay the
critical path for optional investigation, and do not delegate work whose result is
required for the parent's immediate next action.

If subagents are unavailable, execute the same DAG serially rather than weakening it.

## 4. Role Selection

- `explorer`: read-only code and artifact location.
- `domain-specialist`: quant, data, execution, safety, or product judgment.
- `implementer`: bounded changes with an exclusive write set.
- `verifier`: independent reproduction and acceptance checks.
- `adversary`: tries to disprove high-risk success claims and find regressions.
- `integrator`: parent agent; owns interfaces, conflicts, scope, and final verdict.

Subagents receive only the context needed for their node. Do not leak the preferred
answer to an independent adversary before its first pass.

## 5. Write Ownership

Subagents are read-only unless implementation ownership is explicit. A writable node
must state its files or module boundary and remind the worker that other changes may
exist. One file has one writer at a time. Overlapping write sets run serially or in
isolated worktrees and are integrated by the parent. Reviewers must not modify the
implementation they review.

Unknown dirty-worktree changes are preserved and excluded from commits until their
ownership is understood.

## 6. Agent Contract

Every delegated prompt includes objective, scope, prohibited actions, known facts,
expected output, and acceptance. Every handoff returns:

- verdict and prioritized findings;
- evidence with file/line references, commands, or artifacts;
- assumptions and confidence;
- unverified scope;
- recommended actions and tests;
- changed files, when write ownership was assigned.

An agent finishing does not mark the DAG node complete; evidence must satisfy the
node's acceptance.

## 7. Adversarial Review

Assign an independent adversary for P0 changes, trading execution, broker safety,
data provenance, ML leakage, promotion, and broad architectural success claims.
The adversary should test counterexamples, stale or missing evidence, failure modes,
and whether a warning is being reported as success.

## 8. Conflict Resolution

Resolve conflicting findings using this evidence order:

1. reproducible experiment or command;
2. focused test or fixture;
3. executable code path;
4. structured artifact with provenance;
5. current documentation;
6. inference or recollection.

Conflicting P0 findings require reproduction or an independent verifier. Until then,
the affected acceptance remains blocked. The integrator records the ruling and why.

## 9. Evidence and Acceptance

Verify high-impact claims locally. Prefer `rg`, focused pytest, CLI help, deterministic
smoke runs, artifact schema checks, and final repository gates. Inspect artifact churn
and `git status --short --untracked-files=all` before committing.

For Open Composer, treat `StrategySpec` as source of truth and keep
`workflow_pass`, `research_pass`, `llm_contribution_pass`, and `paper_ready_pass`
separate. Parameter search requires bounded trials, a ledger, OOS/walk-forward
evidence, the full benchmark family, costs, and backtest forensics. Sample, fallback,
trial-only, or stale data is not paper-ready evidence.

## 10. Stop Conditions

Stop or re-plan a node when:

- a hard boundary would be violated;
- an unresolved dependency or P0 conflict remains;
- write ownership overlaps or dirty-worktree provenance is unknown;
- required evidence is absent and cannot be produced locally;
- the same blocker repeats without new information;
- investigation escapes its bounded context.

Finish only when all in-scope acceptance checks pass, no unresolved P0 remains, and
external/time-dependent requirements are represented by automatic collection and
machine-readable gates rather than hidden as unfinished code.

## Output

Review-only work: verdict, findings by priority, integrated plan, and at most three
open questions. Implementation work: wave commits, changed behavior, verification,
negative results, external gates, and remaining risks.
