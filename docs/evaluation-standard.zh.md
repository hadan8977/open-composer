# Evaluation standard v2.1

This is an English reference for the existing versioned evaluation contract, not a new universal experiment template. v2 took effect2026-10-01; v2.1 on2026-10-04, with the intraday supplement on2026-10-06. Preserve each study's frozen version and the later applicable promotion gate. Current owner goals and actual trading authority still control; an L1/L2 proposal is never permission to trade live.

Machine-readable thresholds: `config/evaluation-standard-v2.json`. Calibration: `scripts/calibrate_evaluation_standard.py` and `reports/research/program/evaluation-standard-2026-10-01/calibration.json`. Sources: `reports/research/intel/sources/evaluation-standard-2026-10-01/`. The original narrative/calibration examples remain in the guidance-consolidation before snapshot.

## Evidence layers

Evaluate predictive signal, attainable constrained net portfolio return, and current applicability/execution separately. Weight information rather than making a short noisy interval a standalone veto. Existing historical contracts are not retrospectively relaxed; new methodological changes need a prospective version.

## Hard vetoes for contracts adopting this standard

- **V1: data and reproducibility.** Causal/PIT inputs, bound versions, reproducible outputs and complete trial registration.
- **V2: execution and capacity.** Supported order types/windows, easy-to-borrow shorts, whole shares and applicable RegT. At sleeve capital, achieved integer short exposure/target>=0.90, relativeL1 error<=30%, net dollar deviation<=5%NAV. Median proposed per-name trading notional<=1% of20day average dollar volume.
- **V3: doubled cost.** Veto when recent-window annualized net excess return at2x cost<=0.
- **V4: crash behavior.** For the frozen2017-10..2023-08 stress window, veto any21session loss exceeding5x corresponding monthly realized volatility, or63session loss exceeding4x quarterly realized volatility. Exceeding4x monthly or3x quarterly is a warning requiring a state-exit rule, not this veto.
- **V5: recent structural break.** Veto when the last63sessions or current-regime Sharpe has z<-3 relative to the primary estimate. Combine standard errors; compute the short-window error under the primary/null Sharpe, not the observed short-window Sharpe.

These are stage criteria where contracted. Do not impose final execution requirements on a narrower authorized method study or invent missing values to pass them.

## Primary estimates and controls

For the original cross-sectional contract, use2024-01-08 through the latest allowed date, equal-mixing five rebalance offsets, daily net excess over BIL.2017–2023 is stress evidence, not part of this primary estimate. Compute Sharpe, PSR and DSR with skew/kurtosis and selection adjustment. Effective trial count is `1 + (N - 1) * (1 - mean_pairwise_correlation)`; estimate expected maximum-null Sharpe from variant Sharpe variance.

Report the recent long/short signal t-statistic separately from constrained portfolio performance. Short windows (last63sessions, current regime and the specified July-onward comparison) contribute consistency evidence through the z-statistic rather than a standalone positive-return rule.

The original placebo design uses100seeds with matched construction and costs:

- Gross:shuffle scores within the eligible universe on each rebalance date.
- Net, fromv2.0.2:seed/security-hash ranks remain fixed within each calendar quarter; assign sorted real scores by those ranks, inserting newcomers by hash. Daily reshuffling artificially increases random turnover and is not the accepted net control.

Combine valid forward and backtest estimates using inverse-variance weights, with the backtest side adjusted for selection through DSR. The record from2026-09-01 must label design-seen, unseen shadow and actual paper-fill segments; only the latter two count as out-of-sample evidence. Preserve the original forward segment dates rather than relabelling seen history.

## Robustness score

One point each; score jointly rather than six separate vetoes:

| Item | Condition |
|---|---|
| Cost | Sharpe at2x cost >= half the base-cost Sharpe |
| Current state | Conditional Sharpe>0 on ex-ante states matching the current state |
| No single-state dependence | Removing any state retains at least half recent-window return |
| Rebalance offsets | At least4 of5 offsets have positive net Sharpe |
| Recent consistency | Both last63sessions and current-state z>=-2 |
| Gross placebo | Percentile>=0.95 |

## 5. Stage decisions

| Stage | Existing conditions | Action within actual authority |
|---|---|---|
| P1 paper incubation | No veto;DSR>=0.70;net-placebo percentile>=0.90;robustness>=3 | Start planned paper observation only under valid sleeve authorization |
| P2 live candidate | No veto;DSR>=0.80;signal t>=3;net/gross placebo percentiles>=0.95;robustness>=5 | Prepare evidence; not live permission |
| L1 proposed live pilot | P1;>=10actual paper sessions;execution acceptance;segmented forward z>=-2;section5a review;no invalidation | Propose10–20% of target scale or owner-specified amount, with stop/reduction rules; owner decides |
| L2 proposed target scale | L1 andP2;>=6months forward;combined P(Sharpe>0)>=0.9 | Each capital increase requires owner approval |

Later owner restrictions on live deployment remain binding even if an older stage table is satisfied. Apply the exact stage version frozen for the study; do not copy these thresholds into every component.

## 5a. Balanced evidence and execution review

Report recent, stress and full-period Sharpe using the median across rebalance offsets, with2x cost. Explain weak stress results (for example<0.3), why the current state differs, and the state-exit rule; this example is not a new veto.

Regress against SPY, QQQ and the relevant theme proxy (for exampleSMH), report R-squared/beta, attribute theme contributions and assess removal of theme holdings. If more than half recent return comes from one theme, require a stress-tested timing/exit rule for scaling; otherwise keep any proposal at pilot size. Describe who pays the strategy, the mechanism, effective/ineffective regimes, failure signals and relation to existing holdings. A proposal lacking a plausible mechanism starts at half pilot scale under this historical rule.

Portfolio inclusion must improve same-volatility Sharpe and respect the actual sleeve risk allocation. Before an L1 proposal:100%order acceptance and reconciliation; actual cost within0.5–1.5x modeled cost; modeled shadow impact/borrow shown separately because paper fills omit them; tracking error<=25%of target volatility; no data-staleness fault.

## 5b. Existing intraday/timing supplement

For same-day-flat or few-instrument timing contracts adopting this supplement:

- Timing placebos preserve entry time, holding, size and costs, randomizing direction;100seeds, gross and net.
- Intraday cross-sectional gross placebos shuffle at each decision. Net ranks are fixed per trading day by seed/security hash, with sorted actual scores assigned to those ranks.
- Replace five rebalance offsets with check/bar-phase offsets0,+1,+2minutes; at least2positive phases.
- V4 uses actual minute data for the frozen stress period and daily PnL21/63day tails.
- Count primary-grid trials for DSR; the original suggestion was about30variants, with most axes source-fixed. Robustness variants are separately exposed and do not select the winner. The original selection rule used the median specification among the three highest recent-net-Sharpe points, preregistered before results. These inherited rules are not mandatory templates for newly authorized distinct method studies.
- Contracts frozen under the original supplement use its P1 stage. Future versions apply prospectively.
- Before IEX-based paper operation, recompute at least20historical IEX sessions and compare SIP feature ranks/signals. Freeze acceptance before observing it; original suggested rank correlation>=0.8 and direction agreement>=90%. If unsupported, use inputs/instruments whose declared coverage can support the strategy, not invented equivalence.

## Forward monitoring and exits

Under the contracted default, simulate a drawdown distribution for elapsed forward duration using selection-adjusted Sharpe and realized volatility. Reduce by half above its95th percentile, if absolute21session beta>0.25, or actual costs exceed2x model for two consecutive weeks. Stop and review above99th percentile, if combined P(Sharpe>0)<0.5, or when data/execution faults cannot be repaired. Respect the actual account authorization and stricter frozen contract rules; this reference does not issue orders.

## Pass fields and changes

For this standard, workflow corresponds toV1/V2; research toP2; paper readiness toP1 plus actual execution dry-run acceptance. ML/LLM contribution requires higher recent matched DSR and Newey–West t>=2 on the paired daily-net-return difference. Report the identity and scope rather than equating these flags with realized Alpha.

Use actual computed scorecards, versions and evidence. Threshold changes are prospective and documented, never a retrospective rescue of a failed candidate. Historical corrections toV5 and net-placebo construction remain in the original calibration/source records.
