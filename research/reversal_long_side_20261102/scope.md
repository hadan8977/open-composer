# Proposed fixed long-side model comparison

## Economic decision and ancestry

Can the already trained short-horizon reversal rankings produce useful long/cash
account dollars at $20,000, beyond deterministic reversal, a liquidity ranking and
market exposure? This is a new finite component question within the existing
short-horizon reversal lineage. It is not another residual-momentum experiment,
a fresh independent alpha family, or resumption of the unfinished close-execution
proposal. Independent plan acceptance is required before economic computation.

The completed predecessor is
`reports/research/iterations/t20261006_22_st_reversal/`: read `contract.md`,
`trial-grid.json`, `report.md`, `artifacts/selected.json`, `artifacts/attribution.json`
and both `artifacts/ml/*_ml_recent.json` on demand. Preserve its original decisions.
The 24-rule grid had no positive recent net Sharpe. Saved U500/H5 LightGBM had
gross Sharpe 1.37 and net excess Sharpe -0.085 at original costs; Ridge was also
negative. A rule-level descriptive attribution reported positive large-liquid
long-side gross returns and a losing short side. That is a reason to test the
component, not evidence that the learned long side is profitable. The later
close-fill explorations remain post hoc, with weak stressed performance.

The primary mechanism source is Da, Liu and Schaumburg, *Decomposing Short-Term
Return Reversal*, NY Fed Staff Report 513 (2011), pp. 1-5 and its long/short-side
discussion: https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr513.pdf .
The Lead opened the original PDF on 2026-11-02. Its distinction between liquidity
shocks among losers and sentiment among winners motivates separating the legs.
It does not establish this modern daily model's net returns. The paper uses
analyst revisions to distinguish cash-flow news; this local model lacks that
replication input and must not be called a faithful replication. Reuse the
actual saved source text and counterevidence indexed in
`reports/harness/source_cards/t20261006_22_st_reversal.jsonl` and the new source
card for this task. Source claims do not override native execution constraints.

Inspect the later read-only proposals
`reports/research/program/continuous-alpha-2026-10-10/residual-close-execution-brief.md`
and `reports/research/program/residual-close-readiness-20261010-1437/plan-review-request.md`
for duplicate scope and retained missing inputs. They proposed a close-fill,
cost-aware training experiment; this task holds the saved scores and open clock
fixed. Do not revive their old quota manager, obsolete microbudgets or deployment
requirements as authority. An exact completed duplicate, if discovered, should
be received from raw evidence rather than recomputed.

## Fixed inputs and arms

Observed local inputs: `data/research/t22_streversal/meta.json` and saved scores
`data/research/t22_ml_scores/{ridge,lgbm}_U500_H5.npy` exist (each score file
81,363,136 bytes). Existence is not proof of provenance or usable coverage.
Bind their actual date/symbol order, completed-label training clocks, saved annual
training provenance and news availability before using them. Inspect
`scripts/t22_ml.py`, `scripts/t22_run.py`, `scripts/t22_stage2.py` and the native
price/cost inputs. Preserve the original training's clipped-label convention as
a limitation; do not refit, recreate missing scores or silently repair historical
model science under this brief. Missing required evidence is a specific input
boundary, not permission to substitute another model, roster or window.

Primary reporting calendar is the original 2024-01-08..2026-09-15 recent window,
already seen. Reconcile the old reported 685-session calendar with the model's
674 observations explicitly. Use one continuous common evaluation calendar for
all arms; insufficient model history means the prespecified cash fallback on that
date, never deletion of a losing date. Do not open 2026-09-16..30 or another held
reference window. Older data can establish causal histories/provenance but do
not select this experiment's definitions. No market-data refresh is assigned.

Retain historical U500 eligibility, price bounds, permanent identity, inactive
names and corporate-action evidence. Reuse the accepted matrix sanitizer and
split exclusions, checking compatibility before dependent work. A held missing
return or unresolved entitlement cannot be zero-filled or dropped on its outcome.
Apply the native conditional economic-unit interpretation wherever raw physical
shares, distribution cash or PIT membership are not certified.

Freeze six long/cash arms, each independently funded at $20,000:

1. **LGBM_LONG**: the original saved U500/H5 LightGBM ranking; take its original
   long stock selections before short/hedge netting, with the original five-day
   overlapping cohorts. Multiply the original 0.5 long-side target by two.
2. **RIDGE_LONG**: exactly the same mapping for the saved Ridge ranking.
3. **RULE_LONG**: the predecessor's selected rule, U500 industry residual L21/H5,
   with the same long-side mapping, cohorts and capital.
4. **LIQUID100**: rank the same then-eligible U500 stocks by decision-time ADV,
   select the top 100 with deterministic symbol tie breaks, and apply the same
   equal-weight, five-cohort construction. It controls for liquid-stock exposure.
5. **SPY**: funded buy/hold with the same available starting clock and costs.
6. **CASH**: idle cash at the native documented cash-credit convention. Do not
   invent interest, swept collateral, short proceeds or synthetic BIL holdings.

No short-stock or SPY hedge remains in these new arms. Target gross is at most
one; missing slots stay cash. No adaptive renormalization beyond the fixed doubling
above. The original short-stock and hedge contributions are historical context,
not a dollar subtraction from the new independently funded book. This is not a
causal estimate of deleting the short leg alone, since funding and target scale
change. Record exactly those changes in the result.

### Affected execution clarification (2026-11-03, before new accounts)

Retain the predecessor's **target-position filter**, not a minimum order size.
After combining the five cohorts and the fixed long-side doubling, retain a
stock target iff abs(target_weight) * 20,000 >= $100. The reference is the fixed
initial account capital, never changing NAV. Apply the same filter to all four
stock arms; SPY retains its original explicit exemption and CASH has no orders.
For descriptive scaled accounts apply the prescribed risk scale before this
filter. A removed or absent target becomes zero, including full exits; execute
every nonzero difference against current holdings even if its dollar size is
below $100. For example a $180 holding moving to a $200 target buys $20.
Never filter an exit by order size. Missing/unpriceable holdings retain the
native mark/freeze treatment, with unresolved rights reported explicitly.

Filtering precedes conversion of retained weights into targets at actual
pre-trade equity, then the funding adjustment below. Funding can reduce an
accepted target below $100; do not filter again or renormalize. Preserve native
fractional economic units without certifying broker fractional-share capability.
Show desired and funded targets, target-filter exclusions, actual small orders,
funding reduction, cash and drift. The capital adaptation may leave substantial
cash; it does not by itself refute the models' forecasting. Do not change the
threshold or name count after seeing results.

## Execution, costs and comparisons

Keep the decision-after-close / next-session-open convention; existing holdings
earn the overnight move before the new trade. Use the native share/cash engine
through `open_composer.lab.adapters` and its actual shared accounting, cost,
metric and trial consumers. Do not make another daily engine or merely import
saved summaries. Audit any consequential bridge with one affected fixture.
Validate a StrategySpec only if the actual chosen consumer requires one.

Keep the original variable spread/impact/fee model and its explicit missing-input
cost fallback. Use the original open-cost snapshot with its known quote-time and
year-calibration limitations; do not call it historical realized slippage. Each
arm gets separate 1x and 2x transaction-cost funded paths, including first entry.
Do not reuse the old linear gross-minus-multiplied-cost approximation as a funded
stress account. At this capital, impact and dollars must be recomputed from actual
orders. No borrowing, margin financing or terminal liquidation is introduced.

Freeze a deterministic long-only, fee-funded execution adjustment for every
stock arm, SPY, both cost multipliers and all scaled matching accounts. With
current executable holdings h and filtered requested dollar targets d, keep
all requested sales s=min(d-h,0), and scale all requested purchases
b=max(d-h,0) by one common lambda in [0,1]. Frozen holdings are unchanged.
Evaluate the original pure variable spread/impact/fee function on actual net
orders q(lambda)=s+lambda*b, using the same decision-time attributes. Choose
lambda=1 when affordable; otherwise choose the largest feasible lambda with
cash_after = cash_before - sum(q(lambda)) - costs(q(lambda)) >= 0. Use 64
bisection iterations with feasible lower endpoint and nonnegative native costs;
retain the feasible endpoint, never rounding a negative cash balance to zero.
The native cost model's nondecreasing purchase-plus-cost function must hold on
this domain. If even lambda=0 cannot fund sales and fees, or inputs/root are
invalid, stop the affected account with explicit evidence rather than borrow,
change the clock or waive fees. No original account or default engine behavior
is retrospectively changed.

Cost probes must record only executed orders, not root-evaluation attempts.
Persist requested/actual orders, each cost component and cash/equity identities.
Require nonnegative funded cash (only floating-error tolerance $1e-8 in checks),
zero financing charges and identity residual <=$1e-6; keep the native financing
rate configured so it cannot conceal debt. Use the shared native engine through
an explicit opt-in funding adapter/hook, with legacy behavior unchanged. One
affected fixture covers the $20 rebalance, sub-$100 full exit, initial full SPY
entry, sale-funded purchases and 1x/2x variable costs; reuse it for the matching
path. Ordinary fixes remain with the complete-task worker.

Primary model contrasts are LGBM_LONG minus RULE_LONG and RIDGE_LONG minus
RULE_LONG. Also retain both models versus LIQUID100 and SPY (six contrasts per
cost), plus cash and absolute net-profit context. Report all arms and costs;
there is no winner-selection step. Record full and trailing-250-session net
dollars without resetting wealth, annual contributions, fees and gross PnL,
volatility, beta, drawdown, recovery/underwater time, concentration and ADV use.

Where useful for the owner's same-risk decision, reuse the existing deterministic
funded cash-mixture matching method on each model/RULE and model/SPY pair. Scale
down only, with no leverage, and charge the actual induced orders and idle cash.
Freeze root convention and numeric tolerance before outputs: match the lower
unscaled realized volatility, choose the smallest feasible scale, and report
discrete $100 target-filter jumps or absent roots as unmatched. Cash-mixture fits are
descriptive ex-post controls, not new tradable strategies or evidence of causal
alpha. Never present rescaled old profits as independently funded matched dollars.
At most four matched pairs per cost; reuse identical controls. This finite
comparison does not authorize a portfolio allocator or optimal-risk search.

Use paired daily net returns for uncertainty, one common date index matrix with
63-session circular blocks, 1,999 draws and seed 20261102, maxT over the six
primary rate contrasts per cost; report HAC5 as a diagnostic. Costs are dependent
sensitivities, not two independent successes. Intervals concern mean daily rate
differences, not terminal dollar differences. Risk matching remains descriptive.
Preserve limited effective blocks, overlapping cohorts, inherited score selection
and seen-window status. DSR is N/A unless the full appropriate trial distribution
is defensible; do not copy the old count or compute PBO without an actual
candidate-selection experiment.

## Native reception, stopping and resources

Use the existing component/method route in `docs/research-plan-review-standard.zh.md`.
Bind changed science, execution and cost semantics before new accounts. The
original plan review accepted the other economic design and required the two
execution corrections above. Resume that review only for these affected changes; the
runner's fresh Lead then checks the resulting raw accounts and economic decision.
The old report's missing second-person verification is not silently upgraded by
reuse of its scores. Preserve any applicable native contract and identify an
actual required separate reception if one exists; do not invent another result
gate merely because the directory is new. The same worker owns preparation,
fixes, actual books, interpretation and native evidence. No per-arm peers or manager.

The 20-50 reference is already represented by the predecessor's 24 main rules,
two trained ranks, four robustness cells and five post-hoc explorations. Those
categories are not interchangeable counts: reconcile actual starts with the
global ledger and retain withdrawn/failed/unknown exposure. Do not claim all 35
are independent candidates or that this directory resets the budget. Register
the four new stock allocation policies conservatively before evaluation; pure
cash/market benchmarks, cost views, risk-matching root evaluations and reused
predictions are separate diagnostics, not extra model fits or selectable scores.

This finite question stops once the six arms, cost sensitivity and applicable
risk comparisons are complete. A model can earn further investment only from
material recent net dollars with its rule/liquidity/market opportunity costs and
small-ticket limitations visible. Mixed or weak evidence retires this specific
long-side translation; it does not refute residual reversal or authorize close
execution, cost-aware retraining, thresholds, name counts or nearby searches.
Preparation alone is not a completed economic result. A genuine input blocker
must preserve useful checkpoints and identify the exact missing evidence.

Carry `docs/rules.md`, `control.json` and unsuperseded owner rules: meaningful recent
whole-account profit and high Sharpe jointly, same-risk comparison, ~$20k intent,
source-led model/data contributions and distinct mechanisms. A roughly 30%
drawdown is a reference, not a new hard cap; compare deeper drawdown payoffs.
Preserve old gates, standards and any unobserved partitions. No new provider,
paid data, real-money action, paper activation, production change or schedule.
DS remains parked. Existing Martin native account and continuation jobs have
priority: do not interrupt, duplicate, take ownership of or coordinate them.
Use sequential capped jobs with fresh memory admission and the 500 MiB reserve.
No remote job is currently needed; any later use must satisfy current Paseo or
exact Modal free-credit admission, not the old task's dollar reservation.

Record actual ordinary all-role token/time and failed work from existing logs,
excluding restructuring. Keep old reversal lineage costs and missing overhead
separate from the completed residual-momentum attribution costs. Shared account
quota is only pacing under control.json, with no manager or efficiency gate.
Finish with immutable engine Results, orders/cash/daily accounts and a Chinese
retain/change-method/stop conclusion, plus one concrete next economic decision.
