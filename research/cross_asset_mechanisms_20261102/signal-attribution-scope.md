# M1/W4 incremental signal value and calendar robustness

## Decision and accepted lineage

Does changing the original D1 signal to slow momentum (M1) or concentrating its
passing ranks (W4) add enough costed account value to warrant further investment,
after controlling ordinary D1 exposure and the rebalance calendar?

This task retires the A4 timing-refinement branch. It retains the original D1,
fixed-allocation and M1/W4 evidence in the same direction and cumulative ledger.
Read `runs/mechanisms-20261102-2/lead/review.zh.md`, its `raw-audit.json`, the
accepted `scope.md`, and the preceding worker's immutable results. A4's remaining
same-risk increment is positive but inconclusive, with most dollars concentrated
in 2025; that does not reject the parent signal mechanism.

The prior 10bp M1/W4 profits are $34,337.75/$33,930.09, at 24.95%/24.70% volatility.
Their improvements over original 50/50 D1/S3 are only $1,643.09/$1,235.43, with
different risk. Their roughly $4,900 increments over normalized S3/SHY cannot all
be credited to the signal changes: original D1 exposure already contributes.
Moreover, the prior normalized S3/SHY accounts rebalance daily, while these
candidates have 36 trading sessions. Those are valid frozen comparisons but do
not isolate the signal. The next task separates both alternatives explicitly.

Use the existing original source cards, source snapshots and implementations
listed in `scope.md`, including `scripts/screen_batches/h20260928_02_cross_asset.py`,
`scripts/screen_lane.py` and `implementation/mechanisms.py`. This is a local
adaptation; missing Carlson full text still prevents a faithful-replication claim.
No new external factual claim is needed. Native K1 pass and K2 stress Sharpe edge
+0.037 below +0.05, old offset evidence and all seen windows remain unchanged.

Fresh plan review applies to the new matching controls and the new account-level
offset comparison below. This proposal is not its own acceptance. One worker then
owns implementation, admitted calculation, any repairs and economic interpretation.
Do not add another review for preparation or same-semantics repair.

## Frozen comparisons

Use only the saved sanitized prices and source S3 decisions. Development remains
2023-09-18..2025-12-31, 575 seen sessions, with $20,000 starting equity in each
book. Each close decision first trades at the next open; previous holdings earn
the overnight return. Combine asset targets, net internal sleeve trades, charge
actual 10/20bp per-side account orders including entry, and retain native negative
cash financing. Use actual share/cash books, never blended sleeve return curves.

Keep exactly the original D1, M1 (12-calendar-month score, including BIL hurdle)
and W4 (top two passing ranks, original defensive total and fallback) definitions.
M1/W4 always have 50% D1-side and 50% unchanged S3 targets. No hybrid, new lookback,
threshold, allocation search or adaptive rule is authorized. Reuse every equivalent
completed account. Preserve the original fixed 25/50/75% D1, pure S3, EW50 and cash
controls as practical alternatives, displaying their risk gaps and dollar costs.

At primary offset zero, for each cost scenario:

1. Reuse M1, W4 and original50 accounts and their common event union. Report M1/W4
   minus original50 and EW50 with risk gaps and the accepted paired uncertainty.
2. For M1 and W4 separately, normalize the unchanged original D1/S3 fixed mix to
   the candidate's volatility: solve D1 share a in [0.25,0.75] on the common event
   schedule. Reuse the accepted attribution bracketing procedure and its cache:
   nodes .25/.375/.5/.625/.75, deterministic solve, absolute annual-vol gap <=1e-6.
   No root or multiple roots means unmatched evidence, without leverage or
   profit-based root selection. This is an ex-post descriptive control.
3. For M1, W4 and original50 separately, solve S3 share k in [0,1] with SHY
   remainder for the same realized volatility, using that same common event union
   instead of daily rebalancing. Use nodes 0/.25/.5/.75/1 and the same tolerance
   and unmatched/multiple-root policy. Compare these profits with the already
   saved daily-rebalanced normalization, preserving both definitions. The
   difference is a conditional accounting comparison, not unique causal mediation.

These controls distinguish signal-specific increment, ordinary D1 allocation and
the normalization calendar. Coefficients use development only, independently at
each cost; none is a historical forecast or selectable allocation.

## Calendar robustness without choosing a trading day

Use the existing native monthly offsets 0..20, defined by
`screen_lane.signal_dates(index, "M", offset)` (month-end shifted forward by that
many observed sessions). At each offset calculate original D1, M1 and W4 signals
from information available at the shifted decision close. Keep S3's source
offset-zero decisions and dip behavior fixed. The full account event union is the
chosen D1 calendar plus source S3 events, identical across all three signal books
at that offset. Restore both sleeve targets on each event and let shares drift
between them. All 21 offsets must have the same development start/end and costed
initial open; derive the initial D1 target from its available prewindow history.

Offset zero is the primary estimate and must reproduce the saved accounts. Reuse
those six books. The remaining offsets require at most 120 new full books
(three unchanged signal definitions x twenty offsets x two cost views), apart
from explicitly recorded diagnostic repairs. These are predetermined calendar
robustness views, not 120 new mechanisms or a search for the best offset.

Report paired M1-minus-original and W4-minus-original dollars at each offset, with
both volatilities, drawdowns and underwater duration. Summarize the complete
distribution (median, min/max and positive-offset share). Do not combine different
accounts into a synthetic tradable median curve, fit new controls at every offset,
pick a favorable day or treat overlapping offsets as independent observations.
Offset differences are unmatched-risk diagnostics; the primary same-risk controls
above carry the normalized economic comparison.

For primary pairs reuse the 21-session, 1,000-draw, seed-20261102 moving-block
diagnostic; hold fitted coefficients fixed. Intervals are conditional on known
selection and fitted normalization. Use exact daily dollar changes for calendar
year contributions without resetting capital. Where useful, reconstruct per-asset
mark-to-market P&L and actual fees to explain whether a few assets/months account
for the signal change. Sum this attribution back to the account; do not infer
causal mechanisms from correlation alone or choose subsequent windows from it.

## Completion and stopping

The direction already has 25 distinct mechanisms, within its 20-50 reference.
This task adds no selectable mechanism; retain 54 known starts including 24 failed
publications and four ancestor candidates. Record any genuinely new selectable
starts, failed jobs and diagnostic-account costs honestly. Roots, predetermined
offsets, costs and bootstrap draws are not additional free trials. Broader S3
ancestry remains unknown. Use aligned BIL excess returns and existing conditional
DSR conventions if reported; do not manufacture a small-study PBO or promotion gate.

Finish the complete paired economic question and choose retain/change-method/stop.
If the signal-specific increment remains small or unstable, stop spending on
nearby price-rule variants and retain the simple fixed mixture as the benchmark.
If an increment survives cost pressure and calendar counterevidence, identify the
actual exposure/holding mechanism and the next decisive evidence it warrants.
Positive point estimates or intervals alone do not grant promotion. A weak member
does not refute its parent. Do not automatically combine M1/W4 or reopen A4 timing.

The Chinese report must compare whole-account net dollars, risks, fees, turnover,
capital/leverage, underwater time and uncertainty, including the higher-return
S3/A1 alternatives. Engine Results and counts must distinguish new accounts,
reused evidence, economic comparisons, zero new variants/fits and zero paper
candidates. Return the immutable run result and raw ledgers to a fresh Lead;
ordinary reception uses reuse, with native decisive/paper gates still applicable.

## Authority and resources carried forward

Apply `docs/rules.md`, `control.json`, `config/memory-budget.json` and applicable
unsuperseded owner-register entries. The intended account is about $20k; recent
net returns and Sharpe are jointly valued, with high-double-digit returns a goal.
Low-risk components must earn their capital through account contribution. Around
30% drawdown is a reference; deeper losses require an explicit payoff comparison,
not silent new trading authority. This finite follow-up must not crowd out the
separate Martin model work or create a standing ETF parameter search.

2026, anchor and stress stay seen reference evidence, excluded from selection,
root fitting and new account batches. Retain the two old stress normalization
books' two price-unavailable frozen attempts each. There is no data refresh, new
provider, paid data, new unseen window, paper activation, broker-account change or
live-order authority. Existing independent paper operations and schedules persist.
Whole-share, capacity, opening execution and real broker charges remain deployment
dependencies. Source authorizations and native contracts prevail; DS stays parked.

Use shared lab accounting, costs and trial ledger in the actual computation.
Run local work sequentially under the existing admission/cap with a 500 MiB
reserve. Preserve actual running jobs and checkpoints; no duplicate driver or
account replay. No remote job is needed for this saved ETF panel. Hadan access,
if ever justified, remains Paseo-only, fresh ready/usage_ok, C:\paseo and <50 GiB,
with pause/hard-off honored. Modal still requires an exact-resource budget check
inside the existing $25/month free-credit ceiling. One affected pytest only if
the changed offset or control behavior needs it; no concurrent/full-suite tests.

Record actual ordinary all-role research token/time, including this plan review,
worker, failures and Lead, from existing logs. Cached input is already input;
preserve missing fields and unknown provider dollars. Exclude restructuring,
avoid adding nested calculation time twice and never turn shared quota into task
cost. Current accepted result and cost records live in run 2's `lead/` directory.
