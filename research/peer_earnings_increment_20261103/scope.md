# Fixed peer earnings information comparison

## Decision and ancestry

Does the observed market reaction to a peer's earnings filing add usable long-side
account value beyond ordinary industry prices and a stock's own momentum? Test
the information contribution at $20,000 after actual transaction costs. This is
a new finite component comparison, not standalone discovery, a faithful paper
replication or promotion. Independent plan reception precedes economic computation.
The preceding reversal mapping is retired; its scores, thresholds and allocation
policies are not candidates here.

Hou (2007), *Industry Information Diffusion and the Lead-lag Effect in Stock
Returns*, motivates within-industry diffusion, particularly negative information.
Its publisher abstract was retrieved; full methods were inaccessible in this
Lead turn. Do not claim its magnitude or big-to-small result has been replicated:
this task uses liquid-stock peers, a saved industry map, filing timestamps and
long/cash books. Source-notes.json records both access failures and primary
counterevidence: Toth and Kertesz find historical daily lead-lag decay. The latter
is not a direct test of earnings-conditioned diffusion. The alternative hypotheses
are instantaneous price adjustment, ordinary industry exposure, own momentum and
event coverage selection. They determine the controls below.

The old T-20260930-02 industry proposal was superseded on 2026-10-01 by the
signal-library route, not completed as a standalone book. Carry its source and
exposure lineage from reports/research/control/autonomous-queue.md and
docs/research-program.zh.md (candidate library v2), reports/research/harvest/
directions.jsonl and reports/research/knowledge/index.json. Inspect any saved
industry/peer-earnings feature, native result and trial entry before computation.
Do not replay an exact completed comparison or silently reset an old native gate.
If a required native reception already exists, reuse it. A superseded queue entry
does not authorize its old ten-cell grid or restore old administrators.

## Inputs, clocks and evaluation support

Use only saved local data. Observed inputs on 2026-11-03: earnings_events has
three yearly parquet files, 16,089 rows and 15,991 distinct accession values;
coverage reaches October 2026, so explicitly restrict the experiment. SIC map
has 9,222 rows with symbol/CIK, link dates, SIC, FF48 and fetch time. These counts
prove existence, not historical identity or announcement availability. Reuse the
existing capability/data review for this actual modality; bind relevant changes,
not a fresh generic data checklist.

Freeze the common seen evaluation calendar at 2024-01-08..2026-09-15. Earlier
prices establish causal histories only. Do not read later price/return rows or
open any ancestor held partition. The worker binds a common continuous calendar
before returns; missing signals leave cash, never remove a bad evaluation date.
Reuse then-eligible stock and ADV inputs through the native panel; target universe
is the historical U500 by trailing 21-session dollar ADV with native common-stock
and price eligibility. Keep inactive names and native identity/action evidence.
Do not substitute today's roster or use the reversal study's selected-name union
as the universe. Reuse sanitize_price_matrices defaults and split-trigger exclusions.
Never choose membership using later holding returns.

The saved SIC/FF48 mapping is not automatically PIT. Report vintage, ambiguous
links, uncovered names and industry membership. Conditional mapping can support
only a labeled initial component diagnostic if accepted by the reviewer; missing
identity/price/entitlement information that invalidates the actual comparison
blocks affected accounts. Preserve the original last-mark/freeze conventions and
their uncertified rights; do not turn a missing holding value into zero return.

Use item 2.02 SEC filings with a documented actual acceptance timestamp and
unambiguous issuer link; text fetch success is not itself an eligibility filter
because no filing text or LLM extraction is used. Deduplicate accessions and
retain one latest event per issuer in each five-session information window. An
amendment is not a fresh earnings event unless the saved event construction
identifies a different earnings release. Resolve this from metadata before scores.

An event's reaction session is the first actual exchange close strictly after
acceptance_utc, including early closes. Its reaction is the issuer's previous-close
to reaction-close return minus SPY on those same endpoints. It becomes available
only after that reaction close; entry is the next open. An 8-K may follow an
earlier press release: call this filing-conditioned price information, not first
public news or an earnings-surprise measure. No future press-release timestamp,
future industry mapping or completed future return enters a decision.

At a decision close t, each recipient must have at least two distinct other
eligible issuers in its FF48 industry with reaction sessions in t-4..t, and at
least 15 eligible stocks in that industry. Exclude recipients with their own
reaction event in t-4..t from every stock arm. This isolates peer effects from
direct own-event drift. Missing/ambiguous peer observations are unavailable, not
zero news. Preserve coverage by date, industry, issuer and year; do not tune
these requirements after seeing returns.

## Fixed roles and accounts

Compute cross-sectional percentile ranks on the identical covered recipient set
at each decision. Equal values use average ranks; final selection ties use symbol.
All signals have the published continuation sign. Six roles:

1. E: mean reaction excess return of the eligible peer events above.
2. P: equally weighted five-session excess return of all eligible same-industry
   peers excluding the recipient, whether or not they had an earnings event.
3. M: the recipient's standard 252-to-21-session own momentum.
4. ME: equal average of E and M percentile ranks.
5. L: decision-time ADV ranking on exactly the same recipient set.
6. MX: M combined equally with a deterministic permutation of E. Sort present
   FF48 group codes and rotate their E values by one group at each decision;
   preserve the recipient set and missing mask. One group means the placebo is
   uninformative, reported as such. No seed or permutation selection.

E and P are industry information; M is a stronger distinct price control; L
controls coverage/liquidity; MX checks whether assigning the event information to
the correct industry matters. The constant permutation is a descriptive falsifier,
not a randomization p-value. No future performance is used in signal construction.
For any missing required own-momentum history, keep the stock outside the shared
recipient set for all roles. On zero-coverage dates all roles target cash; that
does not establish a zero event effect. Report the cash/coverage contribution.

Each role chooses up to 20 highest-ranked recipients, each at fixed 1/20 target
weight; absent slots remain cash. Evaluate two fixed non-overlapping rebalance
clocks, every 5 and every 20 exchange sessions starting at the 2024-01-05 close.
Hold targets between decisions; do not select an offset. These are 12 allocation
policies, not 12 independent hypotheses. Add independently funded SPY buy/hold
and idle-cash accounts as opportunity-cost references, shared across clocks.

Each policy and each cost setting starts with $20,000 and at most 1x long gross.
Use next-open native share/cash accounting through open_composer.lab.adapters.
Existing holdings earn the overnight move before trades. Preserve fractional
economic units as a conditional convention, not a broker capability claim.
Use the original open variable spread/impact/fee function on actual orders and
decision-time attributes, explicitly disclose its snapshot/year calibration and
fallback. Compute separate funded paths at 1x and 2x costs, including initial
entry. Cash earns the native zero credit; no shorting, borrowing, margin financing
or terminal liquidation. The fixed $100 initial-capital target-position filter
applies once after scaling; all nonzero differences and full exits execute.
Reuse the accepted opt-in fee-funded purchase adjustment and its fixture: retain
sales, scale buys by a common feasible coefficient, evaluate original costs, 64
bisections, no negative cash or cost waiver. Default production code is untouched.

## Comparisons and stopping

Primary within each clock/cost: ME-M, E-P, E-L and ME-MX. Report every arm,
1x/2x full-window and trailing-250-session net dollars, actual fees, turnover,
cash, beta, drawdown, recovery, concentration, issuer/industry/year contributions,
missing marks, entitlement bridges and order/ADV. Trailing dollars follow the
same wealth path without recapitalization. Attribute any gross/cost difference
as accounting, not causal alpha. Also report absolute SPY/cash opportunity costs.

For ME-M only, use the existing independently funded cash-mixture volatility
matching method, scale down only, smallest feasible root, tolerance 1e-6 annual
volatility. Freeze brackets before inspecting results; respect the target filter's
scale discontinuity at 0.1. No root is unmatched, not an interpolated profit.
These at most four pair matches are descriptive ex-post controls, not tradable
risk forecasts or another candidate search.

Use one common 63-session circular bootstrap index matrix, 1,999 draws,
seed 20261103. Center paired daily returns and use simultaneous maxT 95%
intervals across all eight primary clock/contrast pairs per cost. Keep 1x/2x
dependent, intervals on mean daily rates, and the limited independent blocks
visible. HAC5 is diagnostic. DSR/PBO stay N/A absent a defensible complete
historical candidate distribution and actual selection experiment.

The 20-50 distinct-variant direction reference is not a requirement to pad this
finite information comparison. Twelve fixed role/clock policies cover the
declared information controls and short/monthly transmission horizons; adding
thresholds, name counts or seeds would change the question. Reconcile broader
prior starts and register all twelve conservatively before evaluation; count
benchmarks, cost sensitivities, root probes and failed accounts separately.
Stop this task when all valid accounts and comparisons are received, or preserve
an exact input checkpoint if a valid comparison is impossible. Weak results stop
this construction, not the general information-diffusion mechanism. Material
recent net contribution robust to costs and the price/placebo controls can earn
a separately defined next question; no automatic grid extension or deployment.

## Ownership and resources

One worker completes preparation, necessary repairs, native computation and
interpretation. A fresh Lead receives raw results; next_review=plan is for this
new scope. Reuse unchanged reviews and retain actual applicable native contracts.
No extra result role unless an existing native contract requires it. Output the
engine Results schema, trial ledger and concise Chinese economic report.

Carry docs/rules.md, control.json and unsuperseded owner constraints in
docs/archive/owner-rules-register-20261028.zh.md: recent whole-account net dollars
and high Sharpe jointly, same-risk comparison, approximately $20k capital,
drawdown/leverage/opportunity costs, source-led depth, no scientific refutation
from a shallow failure. Current research authorization does not permit new paid
data/budget, real-money orders, a paper change or a schedule. DS remains parked.
Martin jobs keep priority. Use capped local memory with the 500MiB reserve;
no remote launch is needed by this initial scope. Reconcile any jobs/checkpoints
before resuming, preserve failures and unknown actual costs, count all-role
research token/time from existing logs, and exclude restructuring costs. No
quota manager, payback study or standing coordinator.
