# Branch Reconciliation Map - 2026-07-03

Scope: read-only reconnaissance for Step 7.S Wave S.1.

Hard boundary honored: no `git merge`, no `git rebase`, no `git push`, no branch
deletion, no backup deletion, no active spec edits, no data refresh, and no
training. The merge evidence below comes from `git merge-tree` output written
only under `/tmp`.

## Topology Snapshot

Common base for the deployment line and `origin/main`:
`c1e1351efa0cc49336732c0d61794280ef37cf43`.

| Line | Ref | Commit | Worktree | Commits since base | Touched files since base |
|---|---|---:|---|---:|---:|
| Deployment line | `step-7r-pdr-router-ml-gate-2026-07-03` | `a1a1af2573e9c16ba25fef19151a3366f69df1a6` | `/root/codex-test/open-composer` | 25 | 290 |
| `origin/main` | `origin/main` / `main` | `7e7ac3fa360e5e311c1ec1579073c869540679a3` | `/root/.paseo/worktrees/229b4rkt/aquatic-koala` | 1 | 46 |
| Non-ML hardening | `feature/non-ml-research-hardening` | `7e7ac3fa360e5e311c1ec1579073c869540679a3` | `/root/codex-test/open-composer-non-ml-exec` | 1 | 46 |
| Strategy hardening | `feature/strategy-research-hardening-20260529` | `5aeb8f2f6338ade962b5b59d3d33bc86926936b0` | `/root/codex-test/open-composer-strategy-hardening` | 3 | 64 |

`origin/main` and `feature/non-ml-research-hardening` are currently the same
commit. `feature/strategy-research-hardening-20260529` is based on
`origin/main`, so the safest mental model is:

1. `c1e1351` forked into the current Step 6/7 deployment line.
2. `origin/main` added non-ML research hardening.
3. `strategy-hardening` added further strategy research hardening on top of
   `origin/main`.

## Read-Only Commands Used

```bash
git worktree list --porcelain
git merge-base HEAD origin/main
git merge-base HEAD feature/strategy-research-hardening-20260529
git merge-base origin/main feature/strategy-research-hardening-20260529
git rev-list --count c1e1351efa0cc49336732c0d61794280ef37cf43..HEAD
git rev-list --count c1e1351efa0cc49336732c0d61794280ef37cf43..origin/main
git rev-list --count c1e1351efa0cc49336732c0d61794280ef37cf43..feature/strategy-research-hardening-20260529
git diff --name-only c1e1351efa0cc49336732c0d61794280ef37cf43..HEAD
git diff --name-only c1e1351efa0cc49336732c0d61794280ef37cf43..origin/main
git diff --name-only c1e1351efa0cc49336732c0d61794280ef37cf43..feature/strategy-research-hardening-20260529
git merge-tree c1e1351efa0cc49336732c0d61794280ef37cf43 HEAD origin/main
git merge-tree c1e1351efa0cc49336732c0d61794280ef37cf43 HEAD feature/strategy-research-hardening-20260529
```

Temporary merge-tree files:

- `/tmp/oc-merge-tree-origin-main.txt`
- `/tmp/oc-merge-tree-strategy-hardening.txt`

## Touched-File Sets

The full deployment-line touched set is 290 files, so the action-relevant set for
reconciliation is the intersection with each candidate line.

### Deployment Line x `origin/main`

15 files changed in both:

- `dashboard/src/app/components/data.ts`
- `docs/user-guide.md`
- `harness/artifact_contracts.yaml`
- `open_composer/cli.py`
- `open_composer/dashboard/catalog.py`
- `open_composer/engines/backtest_engine.py`
- `open_composer/models/dashboard.py`
- `open_composer/models/strategy_spec.py`
- `open_composer/repo_check.py`
- `open_composer/research/__init__.py`
- `open_composer/research/parameter_sweep.py`
- `open_composer/research/promotion.py`
- `tests/test_intraday_daily_rotation.py`
- `tests/test_promotion_report.py`
- `tests/test_repo_check.py`

### Deployment Line x Strategy Hardening

24 files changed in both:

- `.agents/skills/data-capability-reviewer/SKILL.md`
- `.agents/skills/strategy-research-orchestrator/SKILL.md`
- `.claude/skills/data-capability-reviewer/SKILL.md`
- `.claude/skills/strategy-research-orchestrator/SKILL.md`
- `dashboard/src/app/components/data.ts`
- `docs/user-guide.md`
- `harness/artifact_contracts.yaml`
- `open_composer/cli.py`
- `open_composer/dashboard/catalog.py`
- `open_composer/engines/backtest_engine.py`
- `open_composer/models/dashboard.py`
- `open_composer/models/strategy_spec.py`
- `open_composer/repo_check.py`
- `open_composer/research/__init__.py`
- `open_composer/research/adaptive_intraday_router_core.py`
- `open_composer/research/intraday_daily_rotation.py`
- `open_composer/research/parameter_sweep.py`
- `open_composer/research/promotion.py`
- `open_composer/research/router_promotion.py`
- `open_composer/strategy_capabilities.py`
- `tests/test_intraday_daily_rotation.py`
- `tests/test_promotion_report.py`
- `tests/test_repo_check.py`
- `tests/test_strategy_capabilities.py`

### `origin/main` Touched Set

`origin/main` touched 46 files. The highest-value files to preserve are the
non-ML research hardening modules and their tests:

- `open_composer/research/regime_performance.py`
- `open_composer/research/alpha_decay.py`
- `open_composer/research/evaluation_policy.py`
- `open_composer/research/execution_sim.py`
- `open_composer/research/factor_lab_v2.py`
- `open_composer/research/factor_panel.py`
- `open_composer/research/research_mode.py`
- `open_composer/research/search_policy.py`
- `open_composer/research/series_io.py`
- `tests/test_regime_decay.py`
- `tests/test_execution_simulation.py`
- `tests/test_factor_lab_v2.py`
- `tests/test_market_data_contracts.py`

### Strategy-Hardening-Only Additions

Relative to `origin/main`, strategy hardening adds strategy workflow material
that is likely useful but needs semantic review before integration:

- `open_composer/research/adaptive_factor_attribution.py`
- `open_composer/research/run_progress.py`
- `open_composer/research/strategy_data_compare.py`
- `open_composer/research/universe_audit.py`
- `tests/test_spec_validation.py`
- `tests/test_strategy_data_compare.py`
- `tests/test_universe_audit.py`

## Conflict Matrix: Deployment Line x `origin/main`

`git merge-tree` reports 15 changed-in-both files and 12 textual conflict blocks.

| File | Conflict blocks | Classification | Review note |
|---|---:|---|---|
| `dashboard/src/app/components/data.ts` | 0 | Semantic-adjacent | Dashboard schema fields evolved on both lines; verify JSON model compatibility before accepting either side. |
| `docs/user-guide.md` | 0 | Mechanical | Documentation ordering/content drift; resolve after code semantics are known. |
| `harness/artifact_contracts.yaml` | 0 | Semantic | Artifact contracts are product API; compare new required fields against Step 7.R/S reports. |
| `open_composer/cli.py` | 4 | Semantic | Both lines added command surfaces. Resolve by preserving all Typer apps/commands without changing command meanings. |
| `open_composer/dashboard/catalog.py` | 1 | Semantic | Dashboard catalog readiness/status fields overlap; confirm pass-status and artifact-count semantics. |
| `open_composer/engines/backtest_engine.py` | 0 | Semantic | No textual markers, but both touched the deterministic engine. Require focused backtest regression tests. |
| `open_composer/models/dashboard.py` | 0 | Semantic-adjacent | Model schema drift; must stay compatible with dashboard TypeScript shape. |
| `open_composer/models/strategy_spec.py` | 0 | Semantic | StrategySpec is source of truth; validate schema migrations and no accidental active-spec behavior changes. |
| `open_composer/repo_check.py` | 1 | Mechanical with strict gate risk | CURRENT_DOCS and repo inventory lists conflict. Merge all required docs deliberately. |
| `open_composer/research/__init__.py` | 0 | Mechanical | Export-list drift; preserve exports for all surviving modules. |
| `open_composer/research/parameter_sweep.py` | 0 | Semantic | Search/evaluation semantics changed on both lines; run parameter-sweep tests and inspect report contracts. |
| `open_composer/research/promotion.py` | 6 | Semantic | Promotion gates are safety-critical. Resolve manually; do not auto-accept either side. |
| `tests/test_intraday_daily_rotation.py` | 0 | Mechanical/Semantic | Test fixtures encode behavior; update only after deciding router semantics. |
| `tests/test_promotion_report.py` | 0 | Mechanical/Semantic | Promotion report expectations must match final promotion schema. |
| `tests/test_repo_check.py` | 0 | Mechanical | Keep docs inventory counts synchronized with `repo_check.py`. |

## Conflict Matrix: Deployment Line x Strategy Hardening

`git merge-tree` reports 24 changed-in-both files and 25 textual conflict blocks.

| File | Conflict blocks | Classification | Review note |
|---|---:|---|---|
| `.agents/skills/data-capability-reviewer/SKILL.md` | 1 | Mechanical/Semantic | Skill instructions changed in both mirrored skill trees; resolve `.agents` and `.claude` consistently. |
| `.agents/skills/strategy-research-orchestrator/SKILL.md` | 1 | Mechanical/Semantic | Same mirror discipline; preserve current UltraCode/product gating language if stricter. |
| `.claude/skills/data-capability-reviewer/SKILL.md` | 1 | Mechanical/Semantic | Mirror of `.agents`; no independent product logic. |
| `.claude/skills/strategy-research-orchestrator/SKILL.md` | 1 | Mechanical/Semantic | Mirror of `.agents`; no independent product logic. |
| `dashboard/src/app/components/data.ts` | 0 | Semantic-adjacent | Dashboard schema fields evolved on all lines. |
| `docs/user-guide.md` | 0 | Mechanical | Resolve after code command surface settles. |
| `harness/artifact_contracts.yaml` | 0 | Semantic | Artifact contract drift; reconcile with current harness reports. |
| `open_composer/cli.py` | 4 | Semantic | Multiple CLI additions compete. Preserve command names and help text intentionally. |
| `open_composer/dashboard/catalog.py` | 2 | Semantic | Dashboard catalog readiness and strategy detail fields overlap. |
| `open_composer/engines/backtest_engine.py` | 0 | Semantic | Shared deterministic engine path; require full tests. |
| `open_composer/models/dashboard.py` | 0 | Semantic-adjacent | Backend/frontend schema compatibility. |
| `open_composer/models/strategy_spec.py` | 1 | Semantic | Source-of-truth schema conflict; manual review required. |
| `open_composer/repo_check.py` | 1 | Mechanical with strict gate risk | Docs/current inventory must include all retained plan docs. |
| `open_composer/research/__init__.py` | 0 | Mechanical | Export-list drift. |
| `open_composer/research/adaptive_intraday_router_core.py` | 0 | Semantic | Router logic touched; compare to Step 7.R active-route boundaries. |
| `open_composer/research/intraday_daily_rotation.py` | 1 | Semantic | Strategy behavior logic conflict. |
| `open_composer/research/parameter_sweep.py` | 0 | Semantic | Search semantics and evaluation reporting overlap. |
| `open_composer/research/promotion.py` | 6 | Semantic | Safety-critical promotion gates. |
| `open_composer/research/router_promotion.py` | 3 | Semantic | Router promotion gate overlaps with current PDR/router evidence work. |
| `open_composer/strategy_capabilities.py` | 0 | Semantic | Capability evaluation surface must match registry and CLI names. |
| `tests/test_intraday_daily_rotation.py` | 1 | Mechanical/Semantic | Tests encode selected router behavior. |
| `tests/test_promotion_report.py` | 0 | Mechanical/Semantic | Report contract expectations. |
| `tests/test_repo_check.py` | 0 | Mechanical | Inventory synchronization. |
| `tests/test_strategy_capabilities.py` | 2 | Mechanical/Semantic | Capability command semantics and expected reports differ. |

## Recommended Reconciliation Strategy

This is a recommendation only; no merge was performed.

1. Preserve the current Step 7.R/S deployment line as the product evidence line
   until Step 7.S is complete and verified.
2. In a temporary rehearsal branch, integrate `origin/main` /
   `feature/non-ml-research-hardening` into the deployment line first. It is the
   smaller delta, and strategy hardening is already based on it.
3. Resolve `open_composer/promotion.py`, `open_composer/cli.py`,
   `open_composer/models/strategy_spec.py`, `open_composer/research/parameter_sweep.py`,
   and `harness/artifact_contracts.yaml` manually. These are semantic conflicts,
   not formatting conflicts.
4. Run the full Step 7.S verification chain on the rehearsal branch before
   deciding whether to make it the product trunk.
5. Only after that, review `feature/strategy-research-hardening-20260529`.
   Its unique additions look useful for workflow discipline, but it has more
   conflicts in skills, capabilities, router promotion, and intraday rotation.

## User Decision Checklist

Decisions required before any future reconciliation work:

- Whether the deployment line should be pushed and set as the remote product
  evidence branch after Step 7.S completes. Current instruction says not to push
  during Step 7.S.
- Merge direction: `main <- deployment line`, or `deployment line <- main`, or a
  new integration branch that later becomes product trunk.
- Whether `feature/non-ml-research-hardening` should be retained as a branch,
  given it currently equals `origin/main`.
- Whether `feature/strategy-research-hardening-20260529` should be preserved as
  a separate review branch or folded into a future integration branch.
- Whether all `reports/research/control/*-memory.md` files should remain tracked
  after S.0's broad markdown whitelist, or whether a later curation pass should
  keep only curated memory documents.
- Whether `main` should become the protected product trunk once Step 7.S and the
  branch reconciliation decision are complete.

## S.1 Verdict

The existing lines contain useful work, especially `origin/main`'s non-ML
research hardening and `strategy-hardening`'s strategy workflow audits. The
current deployment line should not be overwritten or fast-forwarded blindly:
promotion, CLI, StrategySpec, artifact contracts, and router-related modules
all need semantic reconciliation. The immediate next step remains Step 7.S S.2,
not branch integration.
