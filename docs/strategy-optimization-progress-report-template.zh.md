# Strategy progress: measurement appendix

Use `docs/owner-reporting.zh.md` for the owner-facing structure and cadence. This file defines the evidence and counts behind a strategy-progress answer; it adds no second report format or research gate.

## Scope and performance

State the as-of time, counting window, claim, sample dates, cost/execution/funding basis and evidence. Report the actual current result against its own frozen criteria; another strategy or earlier version is only a labelled historical baseline. A result does not need a particular filename to be valid, and paper-readiness failure does not erase useful conditional method measurements.

Keep `workflow_pass`, `research_pass`, `ml_contribution_pass`, `llm_contribution_pass` and `paper_ready_pass` distinct. Explicitly distinguish historical simulation, forward observation, paper orders and live activity. Missing current evaluation is N/A with the cause.

For each relevant comparison include net return/CAGR, Sharpe, drawdown and recovery time; contract-specific risk/capture/statistical gates; realistic and pressure costs; positive folds and uncertainty; matched baseline and contribution. State the exact gate and operator rather than inventing a threshold. The applicable selectable-candidate20bps OOS gate is documented once in `docs/research-plan-review-standard.zh.md`; it is not a universal actual-cost estimate.

ML/LLM claims need the role, uniquefits/updates, prediction coverage, calibration, exact fallback, matched deterministic/price-only increment, missing-modality/placebo results and uncertainty. Model Sharpe alone does not show model contribution.

## Portfolio dependence and account contribution

Use a lightweight sequence: consider likely economic overlap when selecting directions, run the useful experiment, then check a simple return correlation against existing paper strategies and relevant candidates after useful results. This is not a test required before starting, for every variant, or in every report, and it adds no approval step or universal threshold.

For an actual comparison, use aligned common dates and after-cost returns, state the sample, and keep missing history missing. Signal/holding similarity can help interpretation but is not measured return correlation. Add rolling/downside checks or account-addition comparisons only when they answer a real question; a full diagnostic suite is not a routine prerequisite. When considering a combination, focus on useful net account return and risk after its costs. Unmeasured dependence stays unknown. Preserve frozen studies and distinguish historical simulation from forward evidence; no paper-order authority is added.

## Count definitions

Report cumulative values and the current increment separately. Do not combine these into an ambiguous attempt count:

| Count | Meaning |
|---|---|
| Iteration directories | Actual directories, including research/forward/control iterations |
| Manifest-backed rounds | Rounds with an actual candidate manifest |
| Locked rounds | Actual historical-evaluation locks |
| Evaluation rounds and files | Distinct evaluated rounds and report files separately; neither implies a pass |
| Preregistered candidates | Manifest rows, not necessarily evaluated candidates |
| Unique trial records | Normalized, deduplicated ledger rows |
| Skipped/invalid/unrun rows | Explicit statuses, separate from actual exposure |
| Persisted models | Unique persisted model IDs; report duplicate ledger rows separately |
| Unpersisted exposure | Known training without reliable persisted records, as bounds/unknowns |
| Automatic factor screens | Actual IC files and factor rows, separate from formal trials |

Unknown statuses are not successful runs. Preparation, fixtures, repeated publishing and ordinary checks are not new economic trials. Reuse a recent unchanged inventory with its date instead of rescanning the whole repository for every round report.

## Knowledge and data inventory

When relevant, report verified/stale source claims, experiment/model memories, registered and executable factors, signal coverage/IC and flags, and data capability approval/visibility limitations. Inventory is preparation evidence, not profitability or live readiness.

Finish with the decisive completed finding, remaining claim-level gap and the next falsifiable action with owner/date. Include actual commands and validation limits in the appendix. Historical August2026 example metrics were removed from this active template and remain in `reports/research/program/guidance-consolidation-20261015/before/docs/strategy-optimization-progress-report-template.zh.md`; they are not current performance.
