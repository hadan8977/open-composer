# Search Space: giants_sweep_20260922

Single-mechanism lightweight path (no campaign contract; see
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 3.1).
One path, `giants_replication_sweep`, with 24 preregistered candidates
sharing spec `strategy_specs/drafts/giants_sweep_20260922_family.yaml`. Benchmark family: buy_and_hold_spy, buy_and_hold_mtum, buy_and_hold_spmo, buy_and_hold_qqq, buy_and_hold_tqqq, live_sleeve_s1_s2_s3_of_h20260918_05.
Costs: `reports/research/iterations/giants_sweep_20260922/cost-table.json`. The candidate manifest at
`reports/research/iterations/giants_sweep_20260922/candidate-manifest.json` is the authoritative per-candidate parameter
binding; this file is descriptive only.

## Why 24 published specifications and not the census's ~156 grid points

`reports/research/intel/I-20260922-03-giants-census.md` sketches roughly 156 grid
points across families F1, F2, F3, F4, F5, F6 and F7. Three things cut that down,
in this order:

1. **F3 is not re-run.** H-20260922-04 already ran the 3x-sector RSI-branch family
   and refuted it. The VIX term-structure family is unrunnable on this box (no VX
   futures). Both are recorded in `unrunnable.md`.
2. **Every searched dimension is dropped.** The census's grids multiplied out
   thresholds (RSI 70 vs 80), rebalance cadences and hedge assets. This iteration
   keeps only values the cited primary source actually publishes. That is why F1 is
   five named symphonies rather than 72 combinations. Two cells are explicitly
   labelled ablations (`f1_tqqq_rsi_no_hedge_ablation`,
   `f2_sector_leg_only_ablation`) and one F4 cell is a cadence variant; everything
   else is a verbatim published rule.
3. **The gate caps it at 24.** `oc research iteration validate` caps a
   single-mechanism iteration that is not bound to a campaign contract at 24
   candidates in one path (`_lightweight_single_mechanism_exempt`), and any
   iteration at 80. A grid wider than 24 belongs in a real breadth campaign
   contract with hypothesis tree, branch quotas and a sealed archive; that
   machinery is the right home if this sweep is ever widened, and this iteration
   does not pretend to be it.

This is a narrowing, never a widening. No window, cost, fill assumption, placebo
or gate threshold from `reports/research/briefs/ENGINE-giants-sweep-2026-09-22.md`
was relaxed.

## What "single mechanism" means here

The mechanism is the replication procedure itself: *take a rule that already has a
public record, express it in the engine's primitives without changing a parameter,
and measure it under the frozen protocol*. There is no parameter search, no
branching optimiser and no archive. The 24 candidates are six source families'
published specifications, not 24 points of one optimiser's search space. The
attestation in `search-space.json` is filed on that basis and this paragraph is
the audit trail for it.

## Placebos per cell (frozen before the run)

| cell kind | placebo | seeds |
|---|---|---|
| gate / canary branch (F1, F5, F6, and the F2 overheat gate) | signal calendar-shifted by a random 1-20 sessions | 20 |
| ranked selection (F2 legs, F5 offensive/defensive baskets) | random pick of the same size from the same menu | 60 |
| fixed weights (F4) | random Dirichlet weights over the same assets, same cadence; 9-sig draws a random start weight and growth rate | 60 |
| overnight (F7) | a random subset of sessions with the same number of nights | 60 |

G3 uses the **worst** beat fraction across a cell's declared placebos, so a cell
with two placebos faces the stricter bar.

## Engine regression lock

`scripts/run_giants_sweep.py --regress` re-expresses the three live sleeves
S1/S2/S3 as manifest specs and refuses to run the sweep unless every window Sharpe
matches `run_h20260918_05_recent_menu.rotation_cell` recomputed on the same panel
to within 0.01. It matches to 0.0000 on all nine numbers. Against
H-20260918-05 section 5 as printed, S2 and S3 agree to 0.006 and S1's holdout
Sharpe reads 2.18 against the card's 2.22; the reference implementation reproduces
2.18 today as well, so that gap is SIP archive drift since 2026-09-18, not an
engine difference. `regression-check.json` records both comparisons.

## Order of operations, stated plainly

`config/giants_sweep/manifest.yaml` (the frozen cell list) was written first, then
`scripts/run_giants_sweep.py`, then the regression gate, then the sweep. The JSON
dossier files in this directory were generated from that already-frozen manifest
afterwards in the same session; the candidate list they contain is identical to
the one that existed before the engine read a price, and `candidate-manifest.json`
carries no metric.
