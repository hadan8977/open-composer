# Strategy Iteration Progress - 2026-07-01

## Current State

- Step 7.A ML training backend is available and has been smoke-tested through `oc research auto --model lightgbm`, `oc strategy train`, `oc strategy backtest-walk-forward`, `oc strategy promotion-report`, `oc harness verify`, and `oc repo check --strict`.
- Latest repository check passed: `oc repo check --strict` returned `status=ok ready=yes`.
- Five real-data QQQ daily theses were run with Alpaca/IEX and LightGBM:
  - risk-managed trend
  - mean reversion
  - volatility breakout
  - overnight gap
  - risk regime
- Best current candidate:
  - Spec: `strategy_specs/drafts/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_.yaml`
  - Thesis: QQQ short-term oversold mean reversion with trend and volatility filters.
  - ML result: return `16.31%`, annualized `7.58%`, Sharpe `1.88`, max drawdown `-3.45%`, trades `20`.
  - Linear baseline: Sharpe `-0.36`, return `-5.85%`.

## Current Blockers

- Promotion is still `blocked`; this is not paper-ready.
- `strict_data` blocks paper readiness because the promotion run used Alpaca/IEX replay cache evidence.
- OOS and lightweight promotion walk-forward slices produced `0` trades.
- Full-window trade count is only `20`, below the 30-trade adequacy threshold.
- Strategy underperformed QQQ buy-and-hold over the same period.
- Factor Lab warned about high correlation between RSI reversal and Bollinger location, plus low coverage for the underlying moving-average leverage gate.
- Daily-open execution has source cards and an execution policy artifact, but missed-fill behavior is not yet replayed in the backtest.

## Artifacts Added For Best Candidate

- `reports/harness/source_cards/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_.jsonl`
- `reports/harness/execution/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_-execution-policy.json`
- `reports/harness/execution/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_-execution-reality.json`
- `reports/harness/execution/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_-execution-reality.md`
- `reports/harness/forensics/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_-backtest-forensics.json`
- `reports/harness/forensics/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_-backtest-forensics.md`

## Next Iteration Plan

Use a small, controlled iteration rather than a broad search.

1. Preserve the best candidate's thesis, data source, execution mode, and ML backend.
2. Change at most two strategic variables:
   - Reduce factor crowding by removing one of the highly correlated mean-reversion features.
   - Loosen ML signal selection slightly to test whether OOS zero-trade behavior is threshold-related.
3. Validate the candidate with:
   - `oc spec validate`
   - `oc harness plan`
   - `oc spec capabilities --json`
   - `oc strategy train`
   - `oc strategy backtest-walk-forward`
   - `oc strategy promotion-report`
   - `oc harness check`
4. Compare against the current best candidate on:
   - ML Sharpe and return
   - max drawdown
   - trade count
   - OOS / walk-forward activity
   - cost sensitivity
   - Factor Lab warnings
5. Keep lifecycle as `draft`, execution as `manual_signal`, broker as `none`.

## Current Decision

Continue optimization, but do not promote. The product can now generate and train research-grade strategies, but the current best strategy still needs stronger OOS activity, better data tier evidence, and less factor crowding before it is worth paper-readiness work.

## Iteration Results - 2026-07-01

Champion remains the original five-factor candidate:

- `auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_`
- Return `16.31%`, annualized `7.58%`, Sharpe `1.88`, max drawdown `-3.45%`, trades `20`.
- Weakness: OOS and lightweight promotion walk-forward still have `0` trades.

Controlled variants tested:

| Candidate | Change | Return % | Sharpe | Max DD % | Trades | OOS activity | Decision |
|---|---|---:|---:|---:|---:|---|---|
| original | 5 factors, gate SMA 150, threshold 0 | 16.31 | 1.88 | -3.45 | 20 | 0 trades | champion, research-only |
| iter1 | remove Bollinger location, threshold -0.001 | 2.42 | 0.31 | -8.97 | 28 | 0 trades | reject |
| iter2 | original factors, threshold -0.001 | 16.08 | 1.86 | -3.65 | 20 | 0 trades | near-champion but no improvement |
| iter3 | original factors, gate SMA 50 | 6.88 | 0.73 | -5.83 | 20 | OOS 4 signals / 2 trades | diagnostic only |
| iter4 | original factors, gate SMA 100 | -2.52 | -0.28 | -9.08 | 20 | 0 trades | reject |

Interpretation:

- OOS zero-trade behavior is not fixed by a small ML threshold change.
- Removing the correlated Bollinger-location feature improves diagnostics but destroys most of the edge.
- Shortening the moving-average gate to 50 days improves OOS activity, but the full-window model edge degrades too much.
- The likely next productive work is not more blind parameter tuning. It is:
  1. upgrade/refresh data evidence so `strict_data` is not blocked by replay cache;
  2. add a promotion mode that evaluates ML OOS on the existing purged ML prediction stream instead of short slices that can be dominated by warm-up;
  3. then rerun a small gate-SMA search with a real trial ledger and forensics.

## Step 9 Pivot - 2026-07-10

- Decision: stop treating `nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate` as the target strategy for the current user objective.
- Reason: the active PDR route is intentionally defensive and currently targets GLD (`defGLD`). That behavior is consistent with the route design, but it is too conservative for the user's requested performance-seeking momentum strategy.
- Execution-chain status: Step 9.0 proved the Alpaca Paper path can reach `paper_order_submitted`, but account alignment remained blocked by an open/accepted order and state drift. This is retained as paper execution evidence, not as alpha evidence.
- New target: rebuild around `mom_minute_r1`, a fresh US minute-momentum research iteration with external brief, minute-data feasibility, bounded non-ML search, benchmark family, cost stress, and a decision record.
- Safety boundary: no active StrategySpec changes, no promotion, no paper readiness, and no live broker writes for the new momentum line until the iteration dossier and research evidence pass their gates.

Current next action:

- Keep the original candidate as the champion.
- Do not promote or paper-test it.
- Next iteration should focus on validation harness/data evidence before more strategy parameter changes.

## Status Update - 2026-07-02

Step 7 hardening fixed the validation-harness issues that were blocking useful
ML strategy iteration:

- ML promotion OOS now uses `ml_purged_stitched_oos` evidence from the purged
  walk-forward prediction stream.
- ML promotion walk-forward now uses `MLTrainingRun` folds and window metadata.
- `strict_data` is `ok` when a fresh Alpaca fetch earns `research_strict`.

Latest champion smoke:

- Spec: `strategy_specs/drafts/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_.yaml`
- Promotion status: `warning`, ready: `no`.
- OOS: `ok`, fold count `7`, OOS predictions `138`.
- Walk-forward: `ok`, validation policy `ml_purged_embargo_walk_forward`.
- Strict data: `ok`, acquisition tier `research_strict`.
- ML vs linear baseline: `ok`.

Current strategy-level issues to record, not project-fix yet:

- Benchmark family is incomplete: missing `market_proxy` and
  `sector_theme_proxy`.
- Factor Lab warning: high correlation between
  `alpha101_015_rsi_reversal_14d_signal` and
  `alpha101_018_bollinger_location_20d_signal`.
- Factor Lab warning: `underlying_moving_average_leverage_gate_signal` has low
  coverage.
- Trade count remains `20`, below the 30-trade adequacy target.
- The strategy has strong Sharpe and low drawdown, but underperforms QQQ
  buy-and-hold in absolute return over the same window.

Current iteration target:

- Stay in `draft`, `manual_signal`, `broker: none`.
- Keep Alpaca QQQ daily and LightGBM.
- Prefer research-grade target before paper-readiness work:
  - ML OOS/WF gates stay `ok`.
  - `strict_data` stays `ok` when refreshed.
  - Sharpe remains at least `1.5`.
  - Max drawdown stays below `6%`.
  - Trade count improves toward or above `30`.
  - Factor Lab warnings improve if possible without destroying the edge.
- Do not fix benchmark-family plumbing or Factor Lab project behavior in this
  loop; only adjust strategy specs and training choices unless a tiny harness
  change becomes strictly necessary.

## Iteration Log - 2026-07-02

### Factor Window Sweep

Command:

`oc strategy parameter-sweep ... --from-spec --search-strategy random --random-seed 77 --max-candidates 24 --top-n 10 --write-top 3 --min-return-pct 0 --min-sharpe 0.5 --min-signals 35`

Result:

- Trial count: `24`.
- Best written candidate:
  `strategy_specs/drafts/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with__sweep_020.yaml`
- Best sweep metrics: return `4.29%`, annualized `2.05%`, Sharpe `0.54`,
  signals `47`, trades `23`.
- This did not beat the champion: return `15.96%`, Sharpe `1.84`, trades `20`.

Decision:

- Reject factor-window sweep candidates as champion replacements.
- Keep the original champion.
- Next test should change model training choices, not catalog factor windows.

### Controlled ML Selection / Horizon Variants

Artifact:

`reports/research/control/qqq-ml-controlled-iterations-2026-07-02.json`

Result:

- `top_quantile` variants preserved acceptable Sharpe but reduced trades and
  return.
- Shorter horizon variants increased activity but destroyed the edge.
- Best ML-selection variant:
  `..._mliter_h5_q55`, return `12.49%`, Sharpe `1.66`, max drawdown `-3.59%`,
  trades `16`.

Decision:

- Reject as champion replacements.
- Do not continue threshold-only tuning; it is not solving the trade-count issue
  without degrading edge.

### Risk / Hyperparameter / Feature-Drop Variants

Artifact:

`reports/research/control/qqq-risk-model-feature-iterations-2026-07-02.json`

Result:

- Best variant:
  `strategy_specs/drafts/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_risk075.yaml`
- Change: `risk.max_position_weight` from `0.50` to `0.75`.
- Metrics: return `24.57%`, annualized `11.21%`, Sharpe `1.83`, max drawdown
  `-5.15%`, signals `41`, trades `20`.
- `risk100` raised return to `33.60%` but max drawdown worsened to `-6.84%`;
  reject for now because it exceeds the current drawdown preference.
- Classifier, stronger regularization, flexible LightGBM, and factor-drop
  variants did not beat `risk075`.

Decision:

- Promote `risk075` to current draft research champion.
- Keep `risk100` as a diagnostic only.

### Frequency Variants

Artifact:

`reports/research/control/qqq-frequency-iterations-2026-07-02.json`

Result:

- Shorter training windows and horizon-1 variants increased trades to `31-43`,
  but Sharpe fell to `0.14-0.80` and drawdown worsened.

Decision:

- Reject frequency variants.
- Trade-count improvement cannot be solved by more frequent retraining/horizon
  changes inside this factor family without destroying edge.

### Low-Correlation Feature Mining

Artifact:

`reports/research/control/qqq-feature-mining-iterations-2026-07-02.json`

Result:

- Added/replaced overnight gap, volume reversal, ATR/range, drawdown, and
  position features.
- No low-correlation feature variant beat `risk075`.
- Some variants improved trade count toward 29-32, but Sharpe dropped below
  `1.0`.

Decision:

- Reject feature-mining variants as champion replacements.
- Current factor family likely has a structural trade-off: the high-quality edge
  is sparse.

### Current Champion After Iteration

- Spec:
  `strategy_specs/drafts/auto_20260701t160510z_mean_reversion_buy_qqq_short_term_oversold_with_risk075.yaml`
- ML training: folds `7`, OOS predictions `138`.
- ML vs linear baseline: `ok`; ML Sharpe `1.83`, linear baseline Sharpe `-0.38`.
- Promotion: `warning`, ready `no`.
- OOS gate: `ok`, `ml_purged_stitched_oos`.
- Walk-forward gate: `ok`, `ml_purged_embargo_walk_forward`.
- Strict data: `ok`, `research_strict`.
- Remaining recorded issues:
  - trade count `20`;
  - Factor Lab high correlation and low coverage warnings;
  - benchmark family missing market and sector/theme proxies;
  - absolute return still below QQQ buy-and-hold.

### New Thesis Mining

Commands:

- `oc research auto "QQQ pullback in an established uptrend with volatility compression and volume confirmation daily." --universe QQQ --timeframe daily --data-source alpaca --refresh-data --max-factors 6 --model lightgbm`
- `oc research auto "QQQ volatility compression breakout after quiet range with risk-on trend filter daily." --universe QQQ --timeframe daily --data-source alpaca --refresh-data --max-factors 6 --model lightgbm`
- `oc research auto "QQQ overnight gap reversal with volume capitulation and drawdown guard daily." --universe QQQ --timeframe daily --data-source alpaca --refresh-data --max-factors 6 --model lightgbm`

Results:

| Spec | Return | Sharpe | Max DD | Trades | Decision |
|---|---:|---:|---:|---:|---|
| `auto_20260702t130939z_qqq_pullback_in_an_established_uptrend_with_vola` | -0.63% | -0.06 | -6.45% | 19 | reject |
| `auto_20260702t131103z_qqq_volatility_compression_breakout_after_quiet_` | 9.43% | 1.05 | -4.87% | 15 | reject, diagnostic |
| `auto_20260702t131222z_qqq_overnight_gap_reversal_with_volume_capitulat` | -1.92% | -0.18 | -7.52% | 15 | reject |

Decision:

- New thesis mining did not beat `risk075`.
- The current best QQQ daily research candidate remains `risk075`.
- Do not keep opening near-synonym theses in this same daily-QTD factor space
  unless the next thesis introduces a genuinely different data modality,
  universe, timeframe, or portfolio construction rule.

### 1h Timeframe Probe

Command:

`oc research auto "QQQ 1h intraday mean reversion after sharp selloff with trend filter and volume confirmation." --universe QQQ --timeframe 1h --data-source alpaca --refresh-data --max-factors 6 --model lightgbm`

Result:

- Spec:
  `strategy_specs/drafts/auto_20260702t131456z_qqq_1h_intraday_mean_reversion_after_sharp_sello.yaml`
- Data: Alpaca/IEX live fetch, `187` one-hour bars from `2026-06-02` through
  `2026-07-02`.
- ML vs linear baseline: `ok`.
- ML metrics: return `0.83%`, annualized `7.55%`, Sharpe `3.03`, max drawdown
  `-0.53%`, trades `7`, folds `2`.
- Baseline metrics: return `0.72%`, Sharpe `1.05`, trades `1`.
- Promotion/evidence status: blocked by execution reality because some bars have
  very low dollar volume and conservative participation checks fail.

Decision:

- Do not promote or compare this as equal evidence to the daily champion.
- Keep it as a promising but under-sampled research direction.
- Required before more 1h work: longer intraday history and execution modeling
  for partial fills / low-liquidity bars. This is a later data/harness task, not
  a strategy tweak for this loop.

## Step 7.R PDR Router ML Gate Negative Result

Artifact:

`reports/research/control/pdr-router-ml-gate-eval-20260703.md`

Spec:

`strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter1.yaml`

Result:

- Lifecycle: draft only; not upgraded, not promoted, and active paper behavior
  stayed unchanged.
- Data: Longbridge materialized adjusted daily cache at
  `data/research/longbridge_adjusted_daily/`, window `2012-01-03` through
  `2026-05-22`.
- Same-data baseline full window: total return `5643.76%`, Sharpe `1.014`,
  MaxDD `-43.24%`.
- Gated verdict: `ml_gate_beats_fixed_route=False`.
- Failed hard gates: walk-forward wins `2/6` vs required `>=4/6`; Sharpe
  `0.931` vs required `>=1.1`; MaxDD `-66.70%` worse than baseline `-43.24%`;
  current OOS Sharpe `1.395` vs required `>=1.7` and total multiple `1.20`
  vs required `>=1.5`.
- Passed gates: annualized return `37.30%` vs required `>=33%`; q4_2018,
  covid_crash, and calendar_2022 still beat TQQQ.
- Crisis protection materially degraded despite that pass: q4_2018 moved from
  `-16.01%` baseline to `-36.75%` gated.

Mechanism diagnosis:

- The cheap label, "future 10-day TQQQ return greater than +2%", detected
  rebounds, not safe re-entry.
- The model released during crash rebounds and during the 2022 slow bear market,
  where staying in GLD was the route's main protection.
- R.1 fail-safe discipline worked: non-hard-stress state or weight changes were
  `0`; the negative result is from the intended `hard_stress_defensive` gate,
  not route drift.

Decision:

- Archive the negative result as evidence.
- Do not widen the 12-combination search space just because this variant failed.
- Next ML attempt requires path-dependent labels and a regime/macro feature
  capability assessment first.
- Candidate labels should target safe leveraged re-entry, for example forward
  TQQQ path MaxDD above a threshold plus non-negative terminal return, rather
  than simple forward return.

## Step 7.T PDR Router Path-Survival ML Gate Negative Result

Artifacts:

- `reports/research/control/risk-on-ranked-rule-review-20260704.md`
- `reports/research/control/pdr-router-ml-gate-eval-20260704.md`
- `reports/research/ml/nasdaq_tqqq_pdr_router_mlgate_iter2/pdr_mlgate_trial_ledger.jsonl`

Spec:

`strategy_specs/drafts/nasdaq_tqqq_pdr_router_mlgate_iter2.yaml`

Result:

- Lifecycle: draft only; not upgraded, not promoted, and active paper behavior
  stayed unchanged.
- T.0 risk_on_ranked rule review concluded `evidence_insufficient`; no non-ML
  ranked replacement was applied to the route.
- T.1 trained exactly 8 bounded path-survival ML-gate combinations:
  `horizon_bars={10,20}` x `max_drawdown_pct={8,12}` x
  `probability_threshold={0.6,0.7}`.
- T.2 verdict: `ml_gate_beats_fixed_route=False`.
- Same-data baseline full window: total return `5643.76%`, Sharpe `1.014`,
  MaxDD `-43.24%`.
- Gated full window: total return `7441.82%`, Sharpe `0.982`, MaxDD `-47.61%`.
- Failed hard gates: walk-forward wins `1/6` vs required `>=4/6`; Sharpe
  `0.982` vs required `>=1.1`; MaxDD worse than same-data baseline; crisis
  windows not worse than baseline; current OOS Sharpe/total gate.
- Passed hard gate: annualized return `38.54%` vs required `>=33%`.

Mechanism diagnosis:

- The path-survival label improved full-window return but still released GLD
  protection too often in crisis windows.
- q4_2018 moved from `-16.01%` baseline to `-35.38%` gated; covid_crash moved
  from `-13.13%` to `-28.51%`; calendar_2022 moved from `-8.76%` to `-15.36%`.
- The tightened crisis gate caught the Step 7.R failure mode: the gated route
  still beat TQQQ in all three crises, but materially degraded the fixed route's
  defensive protection.
- Fail-safe/isolation discipline worked: non-hard-stress state or weight changes
  were `0`.

Decision:

- Archive the negative result as evidence.
- Keep `nasdaq_tqqq_pdr_router_mlgate_iter2` as a draft research artifact only.
- Do not widen the 8-combination search space, change features, or introduce
  macro/FRED data in this round.
- Before any future defensive-exit ML iteration, require a stronger hypothesis
  for crisis-context discrimination and review whether the fixed route should
  remain the champion without ML gating.

## Step 9 mom_minute_r1 Non-ML Minute Momentum Round

Artifacts:

- `reports/research/iterations/mom_minute_r1/evaluation-report.md`
- `reports/research/iterations/mom_minute_r1/trial-ledger.jsonl`
- `reports/harness/forensics/us_minute_momentum-backtest-forensics.md`
- Draft specs:
  `strategy_specs/drafts/us_mom_minute_p1_time_series_qr1.yaml` and
  `strategy_specs/drafts/us_mom_minute_p3_overnight_intraday_qr1.yaml`

Result:

- Lifecycle: draft/research only; no active spec, paper behavior, broker path, or
  ML training changed.
- Data: isolated Alpaca/IEX minute research materialization under
  `data/research/alpaca_minute/`; evidence remains research-only and not
  SIP/full-market paper-ready.
- Search: exactly 28 fixed non-ML trials, P1 `16` and P3 `12`; no widened search.
- Verdict: `acceptance_gate.passed=false`; failed gate =
  `at_least_one_path_continue`.
- P1 best: `mom_minute_r1_p1_008`, QQQ signal / TQQQ exposure, `30m`,
  `lookback_bars=96`, `atr_trail`; total return `88.93%`, annualized `36.71%`,
  Sharpe `1.33`, MaxDD `-20.86%`, entries `158`, x2-cost total `71.90%`.
- P1 blocker: recent fold gate failed because the last fold was positive but did
  not beat the naive baseline (`33.9957%` vs `34.9662%`).
- P3 best: `mom_minute_r1_p3_024`, `1h`, overnight threshold `0.0%`,
  first-bar same-sign confirmation, same-day flat; total return `19.03%`,
  Sharpe `0.83`, MaxDD `-8.41%`, entries `138`.
- P3 blockers: recent fold gate failed and BIL `1h` benchmark proxy was
  incomplete.

Decision:

- P1: pivot, not continue. This is the first useful momentum lead, but it needs
  a simpler lower-overfit follow-up that beats the naive baseline in recent
  folds.
- P2: stop/defer until broader ETF minute data is available.
- P3: pivot/defer; do not expand before P1 is simplified.
- ML and AI-information rounds: blocked for now. Training or news features before
  a non-ML path survives would optimize a failed decision surface.

### 2026-07-11 Methodology Correction

The Step 9.R UltraCode audit found that the original performance evidence is
methodology-invalid. The bar-close signal was applied to a close-to-next-close
return instead of the spec's next-bar-open fill, the four folds were ordinary
post-selection slices rather than walk-forward OOS, and 1h aggregation was not
anchored to the 09:30 US session open. The original artifacts remain historical,
but the quoted metrics and path rankings are withdrawn from strategy selection,
ML entry, promotion, and paper-readiness decisions.

Superseding audit:
`reports/research/control/mom-minute-r1-methodology-audit-20260711.md`.

Decision: repair the harness, then run one fixed nine-combination P1-only round
with development/validation selection and an untouched final lockbox. Do not
expand the search or train ML if that round fails.

## Step 9.R mom_minute_r2 Methodology-Corrected Lockbox Round

Artifacts:

- `reports/research/iterations/mom_minute_r2/evaluation-report.md`
- `reports/research/iterations/mom_minute_r2/trial-ledger.jsonl`
- `reports/harness/forensics/us_minute_momentum_r2-backtest-forensics.md`
- `reports/research/control/step-9-status-matrix-20260711.md`

Result:

- Search remained fixed at nine P1 combinations; no P3, ML, macro, news, or new
  feature was added.
- Selection used 305 development and 102 validation sessions. The final 102
  sessions were not used for selection and opened once for the chosen trial.
- Selected `mom_minute_r2_p1_003`: QQQ signal, TQQQ exposure, 30m, lookback 72,
  rolling ATR filter multiplier 2.5, next-bar-open execution.
- Lockbox: return `26.5356%`, Sharpe `1.8838`, MaxDD `-22.0490%`, two-times-cost
  return `24.0192%`, 173 entries. All five pre-registered gates passed.
- Important limitation: it lagged naive momentum (`39.7480%`) and TQQQ B&H
  (`54.8109%`); IEX data and the 102-session lockbox remain short research-only
  evidence.

Decision:

- Continue research with frozen parameters and new OOS/forward evidence.
- Do not optimize against the current lockbox, start ML, promote, or enter paper.
- Active specs, paper behavior, broker code, dependencies, and credentials were
  unchanged.

## Step 9.O Frozen Momentum Shadow Observation

- Frozen `mom_minute_r2_p1_003` as
  `strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml`.
- Added a QQQ-signal/TQQQ-target `momentum_signal_router` and an observation-only
  `oc strategy shadow-observe` path with stable signal IDs, target weights,
  rebalance intents, deterministic review cards, and no broker I/O.
- Real local run produced 6,565 target rows and 345 historical state-change
  signals, but correctly returned `blocked`: the latest effective bar is
  2026-05-29 and was stale by 1,064.5 hours on 2026-07-13.
- Common aligned history coverage is high, but IEX-only and partial timestamp
  alignment remain warnings; no missing bar is filled forward.
- Execution policy, gap stress, leveraged ETF risk, shadow duration, capacity,
  cross-source, paper, and ML gates are recorded. The -48.47% local overnight
  gap observation is a data-quality blocker requiring provenance diagnosis.

Decision: begin fresh observation only after strict data is updated. Parameters
remain frozen; no paper order or ML training is authorized.

## Step 9.F Final Momentum Product Loop

- Upgraded UltraCode to a DAG-based V2 controller with explicit ownership,
  adversarial review, evidence arbitration, and stop conditions.
- Added strict append-only Alpaca/IEX materialization, immutable historical prefix
  verification, `as_of` truncation, and an epoch-separated forward ledger.
- Added an idempotent broker-free observation cycle, theoretical execution proxy,
  remediation receipts, freshness-aware readiness, and a manual cron example.
- Added an advisory-only ML challenger preflight and baseline-identical failure
  contract. No model was trained and no execution target can be changed by ML.

Final product verdict: capability complete; external certification remains blocked
on future sessions, cross-source evidence, and explicitly authorized Paper fills.

## goal-first W3: Champion Route Re-evaluated on Clean SIP Data

Context: `docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md` section
6.1 found the retired IEX cache backing
`nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate`
carried 20 phantom single-day jumps over 30% across its 11-symbol universe
(unadjusted leveraged-ETF splits). The spec's own `data_assumptions.adjusted`
is `false`. This wave replayed the frozen route -- same
`selected_route_label`, same `spec.costs`, no search, no retuning -- on the
full SIP daily archive (`adjustment=all`) through
`scripts/evaluate_champion_route_sip.py`, using the
`open_composer.research.kernel.mechanism_eval` P1b harness so the verdict is
judged by the same git-committed
`config/promotion/kernel-paper-tier-gates.json` contract a kernel-search
candidate would be.

Artifacts:

- `reports/research/control/champion-route-sip-revalidation-2026-09.json`
- `reports/research/control/champion-route-sip-revalidation-2026-09.md`

Result:

- Full history 2016-01-04 .. 2026-08-31 across all 11 universe symbols is
  available on SIP (2680 common daily sessions); the route's 252-session
  effective lookback leaves a 2017-01-03 .. 2026-08-28 usable window (2427
  sessions).
- **7 of 8 paper-tier gates pass** on the 5-year rolling-origin OOS stream
  (2022-01-03 .. 2026-08-28, 1168 sessions, 4/5 positive folds): CAGR excess
  QQQ +34.3pp, Sharpe-excess-BIL 1.086 (> 1.0 required), DSR probability
  0.5006 (>= 0.50 required -- passes, but by 0.06 percentage points), MaxDD
  -35.6% (>= -65% required), MAR 1.36, QQQ downside capture 0.985 (<= 1.0
  required).
- **`qqq_capture_ratio` fails**: 0.506 vs `>= 1.0` required (QQQ upside
  capture 0.499 / QQQ downside capture 0.985). The route is barely
  defensive on QQQ drawdowns (0.985 downside capture is nearly 1:1 with QQQ)
  while giving up roughly half of QQQ's upside -- a materially worse
  risk/reward shape than the headline absolute-return numbers suggest.
  `qqq_correlation=0.309`, just above the 0.30 orthogonality threshold, so
  this gate is evaluated on its merits rather than exempted.
- **Because one gate fails, `all_gates_pass=False` and
  `promotion_eligible=False`.** No parameter was adjusted to try to clear it,
  per the plan's explicit prohibition.
- **Post-selection collapse**: the 37 sessions since 2026-07-09 (when this
  route's current-OOS evidence was last certified, per Step 7.R) show CAGR
  -58.6% (annualized from a short, noisy window -- treat the sign and
  magnitude as a warning, not a precise rate), Sharpe -2.34, MaxDD -12.1%,
  while QQQ returned +4.9% CAGR over the same span. The spec's own recorded
  `current_oos_annualized_return_pct: 246.7` has not held up going forward.
- Side-by-side against the retired IEX-era fixed-route baseline
  (`reports/research/control/pdr-router-ml-gate-eval-20260703.json`,
  `windows.full_window.baseline`, 2013-01-08 .. 2026-05-20, 3342 sessions):

  | Metric | IEX baseline (2013-2026) | SIP full window (2017-2026) |
  |---|---:|---:|
  | Sharpe | 1.014 | 1.033 |
  | Max drawdown | -43.24% | -42.55% |
  | Annualized return | 35.72% | 38.47% |

  The base deterministic route's shape survived the IEX-to-SIP data
  correction with only small numeric shifts -- unlike the ML-gate overlay
  work in Step 7.R/7.T, where the same data correction produced large
  divergences. This is evidence the underlying route logic itself, as
  opposed to any overlay on top of it, is not an artifact of the IEX defect.
  Crisis-window shapes are likewise close (q4_2018 Sharpe -3.10 vs -3.22
  IEX-baseline; covid_crash Sharpe -1.33 vs -3.96; calendar_2022 Sharpe
  -0.78 vs -0.45, the one window with a larger gap).

Decision:

- **Not promotion-eligible on clean data.** The candidate does not clear
  the preregistered bar as-is; this is a genuine negative result, not an
  artifact of the now-corrected data defect.
- **Do not retune or search around this route to force the capture-ratio
  gate to pass.** Per the plan's hard rule and this project's own repeated
  post-mortem lesson, a threshold cleared by adjustment after seeing the
  result is not a preregistered pass.
- The active spec's `lifecycle: active` state and
  `scripts/run_daily_paper_cycle.py`'s default strategy were **not
  changed** by this wave -- that is a product-level decision (does the
  paper/live pipeline keep pointing at a non-promotion-eligible candidate,
  switch to observation-only, or point at a different candidate) left to
  the goal-first conclusion document, not something a data-correction
  re-evaluation should decide unilaterally.
- The post-selection collapse is the more urgent finding for anyone using
  this candidate's live review cards: the numbers backing its "keep
  running" case are stale by two months and have since gone sharply
  negative.

## goal-first W9 addendum: Base Route (No Overlay) Also Fails

Before concluding no candidate is ready this week, checked whether the champion's
pre-overlay base route -- `post_drawdown_reentry:semi_light_harddd6_v0.65_breadth1_
softQQQ_defGLD_rec104_mom60max20_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10`,
named in the active spec's own `notes.selected_route.base_route_label` -- clears
the gate the overlay-wrapped version failed. This is checking an already-defined
prior candidate from the spec's own recorded lineage, not a new search.

Result (`reports/research/control/champion-route-sip-revalidation-2026-09_base_route_no_overlay.json`):
**also not promotion-eligible, and worse on the failing gate.** `qqq_capture_ratio`
drops to 0.299 (vs 0.506 for the overlay-wrapped version) -- `qqq_upside_capture`
0.291 vs 0.973 `qqq_downside_capture`. The `defensive_overlay:transition_TQQQ_
replacement` wrapper was adding upside participation, not costing it; removing it
makes the risk/reward shape worse, not better.

This closes off the "maybe a known nearby variant passes" question decisively:
both the wrapped and unwrapped versions of this mechanism family fail the same
gate for the same structural reason (downside capture near 1.0, i.e. barely
defensive, while upside capture is well under 1.0). No further variant of this
specific route was checked -- doing so would cross from "checking a named prior
candidate" into "searching," which is out of scope for this wave.

## Step 10 Mechanism Supplementation -- Three Families and a Combination, All Negative

Full plan: `docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md` (v2.0).
Full working ledger with every command, artifact path, and intermediate number:
`reports/research/control/step10-2026-09-04-progress.md`. This section is the
plan's own required closeout ("all candidates fail" branch, section 7): the
honest negative-result record plus next-round direction, appended here per the
plan's explicit instruction rather than left only in the working ledger.

**Context**: after the champion TQQQ router was retired (goal-first W3/W9 above)
and the daily paper cycle stopped, this round asked whether any *unlevered*
mechanism family -- volatility-managed beta exposure, cross-asset ETF trend
following, PIT-liquidity-filtered cross-sectional momentum, or a preregistered
combination of these -- could clear a promotion bar. Doing that honestly first
required fixing the promotion bar itself: `config/promotion/kernel-paper-tier-
gates.json` requires `cagr_excess_qqq >= 5pp` against un-levered QQQ, which was
calibrated for a 3x-leveraged Nasdaq router and auto-fails any un-levered
strategy regardless of merit (QQQ's own trailing CAGR is ~20%/yr, so clearing
+5pp on top of it means beating 25%/yr unlevered). Fixed by preregistering
`config/promotion/unlevered-family-paper-tier-gates.json` *before* any
evaluation ran: same structure, but the benchmark is volatility-matched to the
candidate first (`benchmark_vm = w*benchmark + (1-w)*BIL`,
`w = realized_vol(candidate)/realized_vol(benchmark)`), asking "does this beat
its own risk-matched benchmark by a material margin" instead of "does this beat
an un-levered benchmark by an amount only a levered strategy could plausibly
clear." `max_drawdown_minimum` was also tightened from -65% to -35% (QQQ/SPY's
own ten-year worst drawdown), since a -65% bar made no sense for a family that
never levers up.

### Best result per family, and exactly how far it is from passing

| Family | Best candidate | `cagr_excess_vol_matched_benchmark` (>= 5pp) | `sharpe_excess_bil` (> 1.0) | Gates passed |
|---|---|---:|---:|---:|
| F1 beta exposure (`beta_exposure_router`) | C12: QQQ, SMA200 trend, -15% drawdown stop, no vol target | **+0.99pp** | **0.589** | 6/8 |
| F2 cross-asset ETF trend (standalone kernel mechanism, not yet routable) | lookback=6mo, top_n=5, equal-weight | **+1.33pp** | **0.648** | 6/8 |
| W2 PIT liquid-500 cross-sectional momentum (research track) | top_fraction=0.10, monthly rebalance | **-3.42pp** | **0.474** | 3/8 |
| Wave 3 combination (inverse-vol, F1+F2, W2 excluded on correlation) | ~54%/F2, ~46%/F1 average weight | **+2.44pp** | **0.743** | 6/8 |

**Root cause, same across every family**: every mechanism this round only ever
*reduces* exposure relative to its benchmark (trend/volatility/drawdown gates,
selecting a top-decile momentum sleeve instead of the whole market, rotating
into cash) -- none of them adds leverage or genuine cross-sectional alpha large
enough to clear a 5-percentage-point CAGR margin once compared at *matched*
realized volatility. De-levering by itself is not a source of excess return;
it just changes which benchmark is the fair comparison. `sharpe_excess_bil`
tells the same story from a different angle: every family's best candidate is
in the 0.47-0.75 range, meaningfully positive but well under the 1.0 bar this
project has used for every strategy frozen after 2026-08-15 (`AGENTS.md`).

**W2 is the one family that is also short on `benchmark_vm_capture_ratio`**
(new capture-ratio definition, see the methodology note below) -- its best
candidate runs at roughly 2x SPY's realized volatility (`vol_match_weight`
1.9-2.2 across its 4 candidates), so its volatility-matched benchmark is
itself close to 2x-levered SPY, and the candidate's own CAGR does not keep up
with that levered benchmark. F1 and F2, by contrast, both cleared the capture
gate for most of their candidates once the definition was fixed (see below) --
their remaining gap is specifically on excess CAGR and Sharpe, not on capture
asymmetry.

**Wave 3's preregistered combination (F1 + F2, inverse-vol weighted, monthly
rebalanced) is this round's one genuinely interesting result**: it does not
pass either, but it improves on *both* of the two blocking metrics relative to
either single sleeve (Sharpe-ex-BIL 0.743 vs 0.589/0.648; excess CAGR +2.44pp
vs +0.99pp/+1.33pp), and beats both of its own constituent sleeves' own
`max_drawdown` (-9.89% vs C12's -15.58% and F2's own -11.14%) and `mar` (1.206
vs 0.762 and 0.994) -- not the best of every candidate evaluated this round
(several off-sleeve grid points in F1 and F2 have smaller drawdowns on their
own, e.g. F2's `top_n=all` variants sit near -6% to -11% MaxDD, just with lower
Sharpe/CAGR than the candidates actually selected into the combination). W2 was
excluded from the combination purely
on correlation (0.71 with F2, over the 0.5 cap) -- not because it is weak in
isolation. This is the first direct evidence in this project that
diversification moves a candidate toward (not just around) its promotion
gates; it just was not enough, with only two sleeves, this time.

### A methodology lesson worth carrying forward on its own

Mid-round, every single candidate across F1 (24/24) and F2 (12/12) failed
`benchmark_vm_capture_ratio` -- a 100% failure rate across two unrelated
mechanisms and 36 different parameter combinations. That uniformity was itself
the tell that the metric, not the candidates, was broken: the ratio was built
on `campaign._conditional_capture`'s *total compounded return* over the
up-day/down-day subset of a >1,000-row stitched OOS window, which decays
geometrically with sample size for any candidate with beta materially below
1.0 (which every candidate here is, by construction). Fixed by scoring capture
on each side's *per-period geometric mean* return instead (the standard
Morningstar-style definition, invariant to window length) -- full derivation
and before/after numbers in
`reports/research/control/step10-2026-09-04-progress.md`'s "度量修正" section.
After the fix, 24/24 (F1) and 9/12 (F2) candidates pass that specific gate; the
economic conclusion (fails on excess CAGR / Sharpe) is unchanged, since those
metrics never depended on the broken definition. **General lesson for future
rounds**: a promotion gate that fails 100% of a large, diverse candidate set is
worth auditing as a possible measurement artifact before it is read as a
uniform verdict on the mechanism.

### Next-round direction

1. **F2 (cross-asset ETF trend) cannot be routed to the paper cycle today.**
   `core_beta_satellite_router` cannot express a 10-ETF, BIL-overlaid,
   time-series-momentum rotation: its `core_route_label()` hard-codes the core
   leg to QQQ/TQQQ/CASH via an f-string, `universe_mode` is a label
   `_target_snapshot` never reads, and the satellite sleeve is sized as a small
   additive tilt (`satellite_budget` ~10%) rather than the dominant
   construction this mechanism needs. **Making the core leg support an
   arbitrary symbol (and the router read `universe_mode` for something other
   than a label) is the concrete prerequisite** before F2 -- or anything
   shaped like it -- can reach the paper cycle, independent of whether F2
   itself ever clears the promotion bar. This is a router-engine change, not a
   parameter change, and was out of scope to make unilaterally this round.
2. **Intraday momentum, paper-exact entry rule, deferred from this round**:
   full specification already written and not yet built --
   `docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md` section 8.
   Noise band `sigma_t(d)` = trailing-14-day mean of `|close/open_d' - 1|` at
   the same bar-of-day, upper bound `max(open_d, close_{d-1})*(1+sigma_t)`,
   checked at every 5-minute bar close; exit variants {hold to close, band
   reversion stop, profit target x{1.0, 1.5, 2.0}, time stop {6, 12} bars};
   uses `data/sip-hist/minute` (2016-2022, backfill completed 2026-09-04) +
   `data/sip/minute` (2023-2026) read as two separate roots and concatenated,
   never merged on disk. Needs `sip_parquet` to gain minute-timeframe support
   before it can reach the paper cycle even if it passes.
3. **Cross-sectional momentum product mapping** (target-weights identity for
   `cross_sectional_momentum` mode) is still not built -- moot this round
   since W2 did not pass, but still the prerequisite the moment any
   cross-sectional candidate does.
4. **Diversification is worth pursuing further, not abandoned**: Wave 3 showed
   a real (if insufficient) lift from combining two ~0.4-correlated sleeves.
   The natural next step is finding a genuinely different third mechanism
   (not another momentum-flavored one -- F2 and W2 correlate at 0.71 for
   exactly that reason) uncorrelated with both F1 and F2, rather than
   re-combining the same three families.
5. Deferred, unblocked, low-effort items from plan section 8 that remain
   worth doing independent of any candidate passing: `run_daily_paper_cycle.py
   --data-source sip_parquet` (the SIP archive now updates incrementally, so
   research-identical data could drive paper trading directly instead of a
   second Alpaca API read); Telegram alert delivery once the user supplies a
   bot token.

**Bottom line**: no candidate from this round is paper-ready or close to it.
The new unlevered-family gate contract did its job -- it discriminated real
differences (F1/F2 pass 6/8 gates and are within single-digit percentage
points and low tenths of a Sharpe point of the two blocking gates; W2 passes
only 3/8 and is further away) instead of auto-failing everything the way the
old leveraged contract would have. Nothing was activated, no paper order was
placed, and no account was touched.
