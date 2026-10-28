# Simultaneous allocation within native rank admission — proposed v1

Status: plan preparation, pending independent review. No candidate account has
started. The [handoff](../martin_research_restart_20261028/runs/opportunity-audit-retry-20261028/lead/allocation-plan-handoff.md)
authorizes this preparation, not financial execution. The original
[protocol](../martin_research_restart_20261028/protocol.md), accepted code,
controls and learning checkpoints remain immutable. The machine-readable
[contract](allocation-contract.json) and this document form one proposed package.

## Decision, source and alternative explanation

The question is whether proportional funding of genuinely simultaneous,
native-rank-admitted entries improves whole-account net dollars. Candidate A
changes only their quantities and reservations. Its primary mechanism control
is saved R (cap-three submitted intents), net $2,993.36. Saved B (cap-one), net
$4,099.75, is the economic incumbent; cash is $0. A−R and A−B answer different
questions. Passing A−R alone only repairs a weaker policy.

The retained [first-person source](../../reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/sources/guest2024.txt)
P0055–P0061 supports predefined modest risk and potentially useful but costly
reentry; P0078 and P0131–P0136 support trend management and hard protection.
P0087–P0097 describes context/watchlist selection. It does not prescribe this
allocation formula. A is a local financing adaptation motivated by the accepted
[cash-path diagnosis](../martin_research_restart_20261028/runs/opportunity-audit-retry-20261028/reviewer/review.json),
not a replication of Martin's account or a rule fitted to six reentry outcomes.

The strongest competing explanation is that ranking already concentrates scarce
cash efficiently: spreading it can dilute large winners and increase fee or
rounding burden. Prior [strict-firstbreak reentry](../../reports/research/program/martin-quantization-plan-20261021/resume-20261022/f2/firstbreak-reentry/result.zh.md)
and [parent-first comparison](../../reports/research/program/martin-parent-first-pullback-20261025/accepted-completion.json)
remain negative evidence on their own supports. None is erased or generalized
to a rejection of Martin's entire learning question.

## Population and invariant behavior

Any later admitted account uses the complete seen 2024-01-02 through 2024-03-28
calendar (61 sessions), all 29 names / 28 issuers, and all 1,754 legal
confirmations, including 1,713 feature-valid and 41 feature-missing records.
Missing model features are diagnostic tags, not an exclusion: this component
always chooses native action A without a model. Keep 1,769 scheduled name-days,
invalid/ineligible days, all refusals, winners and losses. The survivor cohort is
retrospectively selected, not a PIT watchlist. GOOG and GOOGL stay separate names;
report shared-issuer exposure without inventing an issuer cap.

Retain $20,000 initial cash, cap-three intents/name/session, actual-stop/fresh
structure requirement, first 120 entry minutes, inherited 1-minute then
5-minute confirmation clock, 0.5% entry risk, 2% aggregate planned risk, 25%
per-name, 100% gross, four concurrent names, whole shares, T+1, 50bp entry-price
guard, previous-minute 1% participation, stop-width eligibility, hard stops,
+3R floor(15% initial shares) partial, original risk denominator, trend runner,
prior completed daily EMA exit, 20-session exit and terminal liquidation. Keep
10bp per side and the accepted tick/depth/ACK/received O-L-H-C conventions.
Native compatibility feedback remains observational and does not enable a new
pause, probe, monthly-risk filter or resizing rule.

No entry is screened on later held-path completeness or outcomes. A's later
funding, stops, holdings and eligibility are its own realized account state; do
not force the original R trade list or settlements into it.

## Causal batch clock

The implemented received-tape clock is established by
[native_events.py](../../reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/code/native_events.py),
[execution_feed_v3.py](../../reports/research/program/martin-learned-payoff-state-20261026/execution_feed_v3.py),
the [close consumer](../../reports/research/program/usic-practitioner-research-20261013/complete-decision-system-20261014/code/nautilus_policy_adapter.py),
and the accepted [clock amendment](../../reports/research/program/martin-decision-loop-model-continuation-20261026/source-clock-amendment.md).
For a completed minute ending T:

| Time | Available event or action |
|---|---|
| T−5ns / T−4ns | Previous minute's own close L2 / paired quote; standing-order callbacks use actual applied books. |
| T−2ns | Existing account mark snapshot. |
| T | Completed history boundary; completed confirmation and prior-only context can enter the close payload. |
| T+1ns | One `close` callback carries the complete cross-sectional frame list. Native expiry cancellations/ACKs finish first. Sort by descending prior ret30, descending prior dollar ADV, then symbol. Preview admission and allocate before returning. |
| T+2ns | Completed-minute missing/GAP, nonconfirmation and cutoff notices arrive; they cannot influence the earlier batch. |
| T+3ns / T+4ns | Next minute's own open L2 / paired quote, if actually received. |
| T+6ns | Previously staged exits use native cancel-before-sell and real ACKs. Sale proceeds stay blocked by T+1. |
| T+7ns | Staged buys dispatch in retained rank/insertion order, with the native own-quote/price guard. Later fill/cancel callbacks release reservation balances. |

The final session's unsubmitted-entry expiry is at final T+3ns; it is not a venue
cancel ACK. Session management/settlement uses the inherited calendar boundary
(09:29 for normal daily management) and final management boundary, unchanged.
Protection can react at intervening actual source events; its callbacks are
processed when received, never moved across the close snapshot.

A batch is exactly one received `close` payload at T+1ns, not all records sharing
a nominal bar timestamp. No cross-callback buffering, later notice, later quote,
future missingness or future return enters it. All payload rows are already
decoded/available before the first reservation in R. Therefore the proposed
two-pass in-callback calculation adds no model-clock latency. Real wall-clock
latency is unmeasured; this is a model-market claim only. If the implementation
needs to wait beyond this callback, R dollars cease to be a matched control:
stop and independently review a matched-latency comparison before any account.

## Eligibility and identical rank admission

Process native expiries, non-buy management/state bookkeeping and received prior
callbacks exactly as before. Preserve per-symbol monotonic frame state and
notice processing. No sell signal releases a holding, slot, risk or T+1 cash
before its actual native callback. Existing holdings, pending exits, pending
buys, sticky unknown paths, exhausted cap, flat waits, invalid frames/events and
nonfresh post-stop structure retain the native refusal behavior. Freshness uses
`structure_started_at >= actual_stop_ns` and `end_ns > actual_stop_ns`, preserving
the accepted nanosecond predicate; do not round the actual stop timestamp.

Take the common pre-buy Book after existing expiry ACKs. On a private preview of
this Book and current eligibility, scan all rows in the original native rank.
For each eligible buy, compute exactly the original sequential native quantity,
including cash, gross, aggregate risk and prior-minute volume. A positive
preview quantity consumes a preview name, cash and risk reservation. A zero
quantity does not consume a slot and the scan proceeds. Preview changes no
actual account, policy counter, intent, ID or order. Denote its positive names S
and quantities q_seq. This is the **same native rank admission**, evaluated on
A's current account path. At most 4−existing held/reserved names enter S.

A reallocates only within S; it never recruits a name rejected by that sequential
preview. This deliberately excludes a larger admission-policy experiment. With
one free slot it cannot diversify into a fifth name. With a single member it
must equal native sequential sizing. Later A paths can produce different S
because earlier quantities/settlements differed; retain that divergence.

## Funding formula, rounding and commit

Let E be common conditional native equity, C=max(0, cash−unsettled−existing
reserved cash), G be held marked notional plus existing reserved worst-price
notional, and I be native held original planned risk plus existing reserved risk.
Define available gross H=max(0,E−G) and risk J=max(0,0.02E−I). Stale holdings use
their last actually received mark with explicit stale tags, as in accepted R;
this does not certify physical current risk. No cancellation/rotation creates
capacity.

For each i in S, at that same snapshot define fee f=0.001,
p_i=reference_i×1.005, c_i=p_i×(1+f), and
u_i=p_i−stop_i+f×(p_i+stop_i). Use the native reference/cap arithmetic and
whole-share floor convention; reject nonfinite inputs as an unknown-path fault.
Use the actual accepted previous completed minute's volume V_i, not the
triggering bar's volume or future depth. The standalone native request is

```
q_req[i] = min(floor(0.005*E/u_i), floor(J/u_i),
               floor(0.25*E/p_i), floor(H/p_i), floor(C/c_i),
               floor(0.01*V_i))
```

It is the original native request with each candidate evaluated against the
common pre-buy Book, including all original individual bounds. It is not an
equal-dollar target, a maturity score or an outcome weight. Missing physical
volume stays unknown; the inherited absent prior-bar case retains native zero
participation, without imputing a liquid bar. The prep evidence recovers only
nine observed prior-minute bounds for four existing contention witnesses; other
unsaved exact bounds remain unknown here.

```
if S empty: return no new buys
lambda = min(1, C/sum(q_req*c), H/sum(q_req*p), J/sum(q_req*u))
x[i] = lambda*q_req[i]
q[i] = floor(x[i])
residual_order = descending(x[i]-floor(x[i])), then original native rank
for i in residual_order:                         # exactly one pass
    if q[i] < q_req[i] and one additional share fits C, H and J:
        q[i] += 1
```

Zero denominators/empty positive requests mean no buys, never division by zero.
All aggregate checks include unchanged existing reservations. Before accepting
a floor or extra share, enforce native-cash fee/cent allowance and the exact
three aggregate limits; use conservative native representable amounts, no
economic tolerance that could add a share. The native floating formula remains
the ceiling; directed representational rounding can only reduce quantity.
An ordinary arithmetic boundary discrepancy is repaired before execution and
logged; it is not a new policy parameter. The implementation review must bind
the actual numeric representation and cent-rounding checks.

This common factor preserves proportions of requested capital before rounding
while respecting the tightest shared resource. Flooring loses less than one
share of each ideal; one deterministic largest-fractional-share pass can restore
at most one per name without exceeding its request. No iterative cash sweep,
minimum trade size, reserved fraction or tuned cutoff is introduced. Any
unallocatable balance remains ordinary available cash for the next native
decision callback; it does not create an extra same-batch entry round. A zero
rounded name receives no intent and is not replaced within this batch.

Validate the entire allocation atomically, then commit positive quantities in
native rank: create the normal buy intent and original submitted-risk record,
reserve c_i*q_i and u_i*q_i, stage it, and increment the intent counter exactly
once. The accepted cap counts a positive `buy_intent_created` at policy close,
including intents later guarded out, unfilled/cancelled or expired before venue
submission. It does not wait for an ACK/fill; zero quantities do not count.
Protective and sell orders do not count. No outcome or future ACK can refund an
attempt. Whole-share partials retain the original submitted initial quantity
and risk denominator after allocation.

Once committed, reservations release only on the existing native terminal
fill/cancel/guard callback or documented unsubmitted session expiry, with actual
partial-fill handling unchanged. There is no early refund of unused fee/cap
headroom, held capital or unsettled proceeds. Freeze downstream staged ordering,
price guards, IOC/ACK/protection, market matching and gap behavior unchanged.

## Support and comparator reuse gates

The preparation engine groups all 1,754 saved R state receipts by the actual
close callback, checks their proposal indices and reservation deltas, and reports
all multi-confirmation groups and all same-batch cash-bound groups. It does not
filter on PnL. Nine exact prior-minute observed-volume rows are a bounded read
from the three already declared Q1 cache files, only symbol/timestamp/volume.
They resolve whether the four candidate cash-contention witnesses are volume
ties, without computing A quantities, returns or unfilled labels. Raw per-group
receipts and input hashes remain under this run's `preparation-01/`.

Before a later account, independent implementation review must establish:

1. Actual payload/receipt ordering supports the common snapshot and atomic
   commit. No future read or new callback latency is added.
2. Native sequential preview reproduces every saved native positive/zero
   quantity and rank admission on saved R states. Its proposed-member set does
   not use A quantities or later paths. Recover missing eligible-row volume
   only from declared then-received inputs; never infer it from later outcomes.
3. Empty/singleton/unconstrained batches are identity cases; resource, whole-share,
   zero-share, slot saturation, fee rounding and T+1 cases satisfy invariants.
   These are informative implementation checks, not new funded controls.
4. Source notice bytes, complete calendar/universe, active parameters, all
   unaffected engine bindings, feed, management/ACK/cost/terminal semantics
   match the accepted B/R package. Prior independent acceptance is reused only
   for these unchanged components. Inspect the decisive diff and receipt parity.

The plan needs at least one identifiable simultaneous resource-contention batch;
no arbitrary minimum event count or significance threshold is invented. If
support is absent or cannot be established, park the economic comparison with
that precise insufficiency. Sparse support limits inference even if a witness
exists. If any reuse condition fails, saved dollars become historical references
only; do not quietly run an unmatched A or new control. Repair the affected
definition and obtain independent acceptance of comparability before an account.

## Frozen evidence and interpretation

Any later account must finish natively, flat with no unresolved orders,
reservations or unknown joint paths, reconcile all fills/fees/cash using actual
per-callback cent-rounding bounds, and preserve unsettled final proceeds. A
positive stale-book fill or an unresolved terminal obligation is incomplete,
not a losing/zero account. Do not replay an unfinished account to obtain a reply.

Report full-account A, R, B, cash net dollars and both deltas; turnover, paid fees,
fixed-fill gross, all losses/winners/refusals and concentration. Build common
and arm-only root / decision / entry-time / quantity / exit-time bridges and a
raw-cashflow-to-native-cent residual term. Record initial and changed
reservations, settlements, stopped/unfilled attempts and later eligibility.
Decompose displaced opportunities only using actual funded paths. Never value
unfunded candidates or call the prior three cash-chain losses recoverable profit.

For risk comparisons, use the intersection of supported account observations
on the **same scheduled calendar** for A/R/B, not separate observed sets. Tag
stale-inclusive series separately and disclose per-arm/intersection coverage.
Keep per-arm observed-only DD as supplementary; shared-minute DD, cash/gross,
planned-risk trajectories, mean/peak exposure and longest observed closing
underwater spell are matched. An absent scheduled observation breaks duration
and return support; do not compress calendar gaps or interpolate marks.

Realized session-close volatility is sample std(ddof=1) of simple daily account
returns times sqrt(252), using identical consecutive supported session endpoints
and the known common initial capital endpoint. Report overnight/gap effects and
the number of available returns. Also report within-session adjacent supported
minute-return std times sqrt(252*390), without bridging missing minutes or
overnights; this is a conditional received-tape diagnostic, not physical realized
volatility. Frozen fees remain included in the account curves.

For the owner's same-volatility requirement, disclose sigma_A, sigma_R, sigma_B
and their ratios first. Provide a descriptive cash-blend normalization at
sigma*=min(sigma_A,sigma_R,sigma_B), scaling each supported daily return by
k_i=sigma*/sigma_i (0<=k_i<=1) and compounding $20,000 over the same endpoints.
If any sigma is zero, support is discontinuous, or returns are insufficient,
report normalization unavailable. This ex-post calculation is not a funded
account, a causal sizing rule, new trial or proof of executable equal-risk
superiority. Do not rescale actual orders or tune caps to equalize results.

Apply these interpretations before viewing A's economics:

- Workflow/causal validity is distinct from economic support and readiness.
- Component economic support requires complete comparable A, identifiable
  mechanism activity, net_A>0, net_A>net_R and net_A>net_B. Nonpositive dollars
  fail support even if exposure/drawdown is lower. A>R but A<=B is a repair only.
- A candidate whose raw dollars improve but whose matched normalized dollars
  fail to exceed either comparator has no evidence of improvement beyond risk
  scaling. Higher realized volatility, greater DD/underwater, gross/planned-risk
  exposure or unresolved gaps require an explicit tradeoff/unresolved verdict;
  they cannot be labelled same-risk superiority. Report every metric, without
  selecting the favorable frequency or deleting a large winner/loss.
- Positive raw and descriptive normalized deltas with no worse matched risk
  make this a promising **seen-Q1 component**. If realized volatilities differ,
  executable same-volatility superiority remains unproven and requires a later
  independently accepted comparison; normalization alone never grants it.
- No observed effect/too few affected batches means limited or uninformative
  mechanism support. Stop redundant reruns rather than claiming broad refutation.
  Negative/uncertain results cannot trigger a nearby cap, cost, size, allocation
  variant, threshold or window rescue. A new alternative needs a distinct
  unresolved explanation and its own accepted scope.

Q1 cannot demonstrate recent usefulness, generalization, model/LLM contribution,
portfolio complementarity or promotion. There is no new OOS release, fit, grid,
effective-trial estimate, DSR or PBO in this plan. A statistical measure cannot
be manufactured from an account-start floor.

## Native gates, resource estimate and recovery

This deliverable is a proposed component protocol. The workflow's next
independent reviewer must return `approve_deep_plan`, `revise_plan` with a
concrete material correction, or `stop_or_pivot` with explicit insufficiency.
The author cannot accept it. Plan acceptance is separate from financial_go.

A later execution brief requires a versioned A StrategySpec validated **before**
strategy-code edits; registered `market.alpaca_bars` compatibility; bindings to
accepted received source/transition/feature contracts; affected native-adapter
review and parity above; actual memory/current-authority admission; and the
existing financial lab adapter/trial ledger before launch. Keep applicable
direction/iteration/knowledge/campaign gates if a later change enters those
native contracts. This fixed component is not new family discovery/training;
do not create a dummy campaign or claim an unrelated harness pass as authority.
Any later selectable promotion retains its original frozen gates, including
the applicable continuous terminal-free OOS criterion; this plan is ineligible.

Reuse measured prior accounts for a one-A estimate: B used 1,091.535 CPU seconds,
1,774.460 wall seconds, 397,444KiB peak; R used 1,120.216 CPU seconds, 1,127.232
wall seconds, 398,780KiB peak. Plan approximately 18–25 CPU minutes, 20–35 wall
minutes, 400–650MiB RSS for one serial A after acceptance; 900MiB capped wrapper,
one numeric CPU, 3,600-second finite timeout and 500MiB owner reserve. These are
estimates/envelopes, not paid allowance or measured new costs. Existing B/R need
zero new starts when reuse passes. A necessary matched-control rerun would add
roughly one account's cost but requires review/admission first; it is not
authorized here. Expected evidence storage is below 50MiB/account, estimated
from the prior per-account receipts and minute-account output.

Do not run a heavy test suite alongside an account. Preparation uses only a
bounded read-only engine under the same capped admission. Record its outer
resource receipt, all failures and unprofiled preparation/agent costs as unknown.
No new paid data/provider/device action is needed; the runner owns actual agent
usage reporting. Current shared-account readings are pacing, not project bills.

Future native runs need versioned process/job/session identities, per-session
durable receipts and the existing checkpoint route. The native engine is not
serializable; after interruption reconcile the actual process and partial
artifacts before any same-definition restart/review. Never silently detach,
replay a job, swap a provider or overwrite a failed run. No account exists in
this preparation and no financial checkpoint is claimed.

## Inherited authority and cumulative exposure

Carry the [owner register](../../docs/archive/owner-rules-register-20261028.zh.md),
[rules](../../docs/rules.md) and [research restart](../../reports/ops/restructure-resume-20261028.json):
whole-account net dollars/high returns/Sharpe and recent evidence govern eventual
usefulness; defense or resizing must add account value. Around 30% DD is a
reference, not permission to alter this frozen risk. Report capital, matched
volatility, leverage, DD and opportunity cost before any risk tradeoff decision.

The known financial-start floor remains at least 65, with unknown earlier
exposure. Retain all failed attempts and the actual prior cross-window read of
19,981 symbol/day/ret30/adv rows spanning 2024-01-02..2026-09-30 in the
[exposure receipt](../martin_research_restart_20261028/runs/opportunity-audit-retry-20261028/delivery/costs-and-exposure.json).
A date-filter repair does not erase it; no untouched-window claim without audit.
This prep adds no account, hypothetical label, fit, optimizer update or financial
candidate evaluation. It proposes one rule; there is no candidate grid.

Preserve the full 8,666-root mission, accepted 1,152 prefix, 7,514 remainder,
1,153 current initializations, legacy exposure and original S/T comparisons,
using the [latest continuation record](../../reports/research/program/martin-decision-loop-model-continuation-20261026/actual-cumulative-usage-at-cap70-20261027.json).
No prefix fit, unfinished-root read, withdrawn-definition revival or replacement
of the model-learning task is authorized. Earlier proof02 costs remain unknown
where recorded. No new provider invoice or quota query is made in preparation.

Manager stays off. Preserve control switches, actual research/paper scopes,
paper expiry/caps/stops, read-only cockpit and schedules. Real-money writes,
new accounts, paid budgets/providers, broker operations or paper activation are
outside this plan. Hadan remains Paseo-only with fresh ready/usage_ok, fixed
C:\\paseo, <50GiB and pause/hard-off respected; Modal remains within its existing
free-credit gate; DS stays parked. No device wake or provider action is needed.
