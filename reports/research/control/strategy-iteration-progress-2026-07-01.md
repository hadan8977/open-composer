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
