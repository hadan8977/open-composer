# Product strategy research process memory

This memory records process failures identified in the TQQQ iter5 conversation so
future strategy generation and optimization does not repeat them.

## Problems Observed

- The agent treated user ideas as research direction instead of independently
  validating them through external quantitative literature and platform docs.
- Research moved too quickly into parameter/grid search before writing a
  theory-backed research brief, factor hypotheses, failure modes, and risk
  budget.
- Standards were too reactive to user prompts. Professional strategy standards
  should be proposed by the agent using mature quant practice, then mapped to
  user preferences.
- `workflow_pass`, `research_pass`, `llm_contribution_pass`, and
  `paper_ready_pass` were eventually separated, but the workflow allowed
  research-like artifacts to appear before the proper gates were satisfied.
- Source research was too shallow and too late. Mature methods, data-provider
  constraints, leveraged ETF risks, execution constraints, and backtest
  overfitting controls should be researched before optimization.
- The iteration relied heavily on grid search and route-label combinations
  instead of factor research, single-factor marginal contribution tests, and
  pre-registered search spaces.
- Simple SQQQ/inverse ETF hedging was tested mechanically without enough prior
  theory, term-structure/path-dependency analysis, or alternative risk-defense
  designs.
- The agent did not stop failed method families early enough. Failed branches
  should be recorded and pruned instead of repeatedly recombined.
- Current-symbol high-beta universes created survivorship-bias risk. PIT
  universe evidence or explicit research-only labeling is mandatory.
- New research-only route labels were not integrated into production router
  target-weight parity before any paper-readiness discussion.
- Dashboard and Codex should be equivalent entry points into the same gated
  workflow. Codex direct interaction currently makes it easier for an agent to
  bypass gates unless the agent self-enforces the skills.

## Mandatory Future Practice

- Before optimization, browse and cite mature quant sources, then write a
  research brief with alpha hypothesis, risk hypothesis, factor candidates,
  data assumptions, failure modes, and professional acceptance criteria.
- Use user ideas as preference signals, not as the authority on method validity.
- Start with factor tests and marginal contribution evidence before strategy
  combinations.
- Prefer adaptive, sample-efficient search only after the search space is
  theory-backed and pre-registered.
- Log every trial, including adaptive trials, with seed, generation/iteration,
  parent candidates where relevant, data window, metrics, and rejection reason.
- Treat optimizer output as candidate discovery only; final selection must pass
  chronological walk-forward, benchmark family, forensics, capacity/execution,
  and paper-readiness gates.
