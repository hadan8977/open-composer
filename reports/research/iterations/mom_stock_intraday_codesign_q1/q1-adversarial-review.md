# Q.1 Adversarial Review: mom_stock_intraday_codesign_q1

## Scope

- Review target: current-snapshot universe construction, daily and intraday market-data integrity, event/news/macro PIT semantics, rights metadata, Q.2 candidate authorization, and pre-backtest enforcement.
- Safety boundary: no active spec, broker, paper-order, credential, model training, or backtest changes.
- Acceptance: exact candidate accounting, immutable evidence bindings, fail-closed Q.2 execution contracts, no unresolved P0/P1 implementation finding, focused and full tests passing, and the pre-backtest dossier validating.

## Adversarial Findings And Resolutions

1. Intraday diagnostics could be authorized despite acquisition-manifest drift and incomplete cross-symbol slots.
   Resolution: all required source manifests must match and the post-exclusion common timestamp ratio must equal `1.0`. The frozen panel has `0/10` matching source manifests and ratio `0.9885031`, so `I01-I12` are dependency-skipped.
2. Symbol-local malformed daily bars were expanded into a global session exclusion.
   Resolution: anomaly cleaning removes no daily session. The 13 bounded anomalies affect only unused `high`/`low` fields; Q.2 is restricted to `open`, `close`, and `volume`, with no forward fill, zero-return substitution, or high/low-dependent candidate. Runtime alignment is separately fixed to the exact common timestamp intersection rather than filling stale tails.
3. Provider publication timestamps could be mistaken for collector visibility, and revision or rights provenance was not explicit.
   Resolution: live event adapters record collector fetch/first-seen visibility, acquisition mode, revision/version identity, availability basis, and rights scope. Missing rights, historical membership, vintage, or first-seen evidence remains a blocker rather than being inferred from fixture or backfill timestamps.
4. Feature packets could report PIT completeness with invalid timestamp ordering or inferred visibility.
   Resolution: packet validation requires explicit `visible_at` and enforces `published_at <= fetched_at <= visible_at`; the dashboard reuses the canonical inspector.
5. Q.2 authorization trusted coarse path booleans and incompletely bound feasibility artifacts.
   Resolution: the validator derives exact ID-level accounting from the 48-candidate manifest, verifies candidate/evidence/spec/artifact hashes, and requires `28` runnable plus `20` dependency-skipped with no unresolved candidates.
6. The initial Q.2 execution map did not fully specify or validate model and control semantics.
   Resolution: all 28 runnable candidates now bind exact feature formulas, task, estimator grid, target encoding, score or parent IDs, inner/outer fold rules, label horizon, embargo, tie breaks, portfolio mapping, costs, fallbacks, regime algorithms, train-only artifacts, and placebo outcomes. The validator rebuilds the canonical map and rejects any semantic mutation, including score, feature/label/cost/benchmark contract, primitive-field, or safety-flag drift.
7. Iteration validation was available as a manual command but could be omitted from common execution commands.
   Resolution: `oc backtest`, `oc strategy optimize`, and `oc strategy parameter-sweep` automatically enforce the declared iteration's pre-backtest gate.
8. The 62 selected stocks had stale tails, and required SPY/XLK/BIL inputs were named but not bound.
   Resolution: the daily manifest binds every benchmark cache and acquisition-manifest SHA-256 and fixes all ranks, breadth, dispersion, labels, and benchmarks to the exact 65-series common intersection. That window has 967 sessions from 2022-07-18 through 2026-05-22; XLK/BIL manifest lineage remains explicitly incomplete.
9. The formal forward epoch could be mistaken for available forward evidence.
   Resolution: the alignment artifact records `formal_forward_observation_count=0`; Q.2 is historical diagnostic rejection only and cannot produce forward or virtual-paper evidence.
10. A final schema-v2 adversary found undefined raw aliases, unclear regime-state use, a conflict between 62-name ranks and symbol-local missing rows, an unscoped risk q20 threshold, and incomplete benchmark turnover conventions.
    Resolution: raw aliases are defined, D11 excludes regime state, M05-M10 bind train-only regime behavior, any incomplete 62-name decision is skipped, the q20 is global over fitted outer-train row predictions, and every benchmark now specifies fold-start, rebalance, cost, and terminal-turnover behavior.
11. Nested selection could fit preprocessing and label thresholds on all outer-train rows; composite parent cadence, fallback recursion, and the ex-post benchmark identity were also ambiguous.
    Resolution: imputation, scaling, bins, thresholds, and regime state fit only on purged inner-train during selection, then refit on purged full outer-train. M09/M10 refit their 21-stride risk parents inside each five-bar composite fold without carry. Failed candidates remain failed while cycle-safe fallbacks are comparison-only, and each outer fold uses one fixed ex-post-best symbol.
12. Future label windows did not explicitly require complete selected-62 opens, and intraday panel quality could be confused with Q.2 authorization.
    Resolution: five-day labels require all 62 opens at offsets 0 and 5; downside labels require all offsets 0 through 21. Incomplete windows are excluded from labelled training/evaluation without changing features, scores, or weights. The feasibility report now separates `panel_quality_go` from the always-false intraday `q2_diagnostic_go`.

## Frozen Verdict

- Authorized diagnostic IDs: `D01-D12`, `M01-M16`.
- Dependency-skipped IDs: `I01-I12`, `E01-E08`.
- Candidate accounting: `48 = 28 runnable + 20 dependency-skipped + 0 unresolved`.
- Daily evidence: 62 current-snapshot stocks, 13 quarantined high/low anomalies, zero anomaly-driven session exclusions, and a 967-session exact runtime intersection through 2026-05-22.
- Intraday evidence: blocked on `0/10` source-manifest matches and incomplete timestamp intersection.
- Status: `workflow_pass=true`, `research_pass=false`, `llm_contribution_pass=false`, `paper_ready_pass=false`.

## External Blockers

- Historical stock membership, delistings, and permanent symbol mapping are unavailable.
- Provider storage, replay, model-input, audit-retention, and redistribution rights are not verified.
- Market feeds are not proven consolidated SIP data.
- Corporate-action lineage is not immutable and point-in-time.
- No real authorized event/news/macro corpus satisfies the required PIT replay contract.
- XLK/BIL runtime content is hash-frozen, but their acquisition manifests do not bind those runtime cache files.
- The frozen panel contains zero observations after the formal 2026-07-15 forward epoch.

These blockers prevent positive research, LLM contribution, promotion, paper readiness, and order authority. Q.2 may use the frozen daily panel only for survivorship-labelled diagnostic rejection tests.

## Verification

- `uv run pytest -q tests/test_iteration_dossier.py tests/test_stock_momentum_data_feasibility.py`: 20 focused tests passed.
- `uv run oc research iteration validate mom_stock_intraday_codesign_q1 --stage pre-backtest --json`: `status=ok`, no blockers or warnings.
- `uv run ruff format .`: 347 files unchanged after formatting.
- `uv run ruff check .`: passed.
- `uv run pytest -q`: full suite passed.
- `uv run oc repo check --strict`: `status=ok`, `ready=yes`.
- `make verify`: 735 tests passed; composite gate exited `0`. Deployment/readiness warnings remain limited to intentionally unsynced broker state and two partial draft backends.

## Verdict

`GO` for Q.2 runner implementation only. Candidate execution remains blocked until the declared `stock_momentum_codesign_q2` entrypoint exists, consumes and verifies the canonical map, and passes its leakage and accounting tests. Once that implementation gate passes, the bounded historical diagnostic scope may run. No fixture, sample, fallback, or current-snapshot result may be represented as strategy alpha, historical research qualification, LLM contribution, paper readiness, forward evidence, or trading authority.
