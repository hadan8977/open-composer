# Decision Record: mom_minute_r1

Wave 9.4 ran on 2026-07-10 with the bounded 28-trial non-ML matrix. Artifacts:

- Trial ledger: `reports/research/iterations/mom_minute_r1/trial-ledger.jsonl`
- Evaluation: `reports/research/iterations/mom_minute_r1/evaluation-report.md`
- Forensics: `reports/harness/forensics/us_minute_momentum-backtest-forensics.md`

Overall decision: no path reached `continue`. P1 and P3 produced positive
research evidence but failed the recent-fold gate, so the round is a `pivot`,
not a promotion, paper, or ML-training trigger.

## P1

- Path: P1_time_series_etf_momentum
- Decision: pivot
- Reason: best trial `mom_minute_r1_p1_008` used QQQ signal / TQQQ exposure,
  `30m`, `lookback_bars=96`, `exit_style=atr_trail`, and produced total return
  `88.93%`, annualized return `36.71%`, Sharpe `1.33`, MaxDD `-20.86%`, and
  `158` entries after base costs. It still failed the recent-fold gate because
  fold 4 was positive but slightly below the naive baseline (`33.9957%` vs
  `34.9662%`), so it cannot continue under the Wave 9.4 rules.
- Next iteration suggestion: pivot toward lower-turnover/risk-shaped variants
  around the P1-008 idea: keep QQQ signal / TQQQ exposure, test fewer exit
  degrees of freedom, add a non-optimized volatility kill layer, and require the
  last two folds to beat the naive baseline before any ML work.

## P2

- Path: P2_cross_sectional_etf_rotation
- Decision: stop
- Reason: pre-backtest stop/defer because Wave 9.2 found insufficient same-
  timeframe ETF coverage for an honest cross-sectional run.
- Next iteration suggestion: reopen only after broader ETF minute history is
  materialized with PIT universe caveats.

## P3

- Path: P3_overnight_intraday_decomposition
- Decision: pivot
- Reason: best trial `mom_minute_r1_p3_024` used `1h`, overnight threshold
  `0.0%`, first-bar same-sign confirmation, and same-day flat exposure. It
  produced total return `19.03%`, annualized return `8.94%`, Sharpe `0.83`,
  MaxDD `-8.41%`, and `138` entries, but failed the recent-fold gate and had
  an incomplete BIL `1h` benchmark proxy.
- Next iteration suggestion: do not expand this path now. Revisit only after
  P1 is simplified or after BIL `1h` benchmark data is materialized cleanly.

## P4

- Path: P4_volatility_adjusted_momentum
- Decision: stop
- Reason: deferred as a separate path to keep the first round at 28 combinations
  and avoid adding regime parameters before base evidence exists.
- Next iteration suggestion: use only as a follow-up risk-control layer if P1 or
  P3 produces a stable base-cost candidate.

## Later Entry Conditions

- Path: ML_round_candidate
- Decision: stop
- Reason: Step 9 requires ML eventually, but this round has no non-ML path that
  passed the full gate. Training now would optimize a failed decision surface.
- Next iteration suggestion: only open `mom_minute_r2_ml` after a simplified P1
  or another non-ML path passes recent-fold and benchmark gates with enough OOS
  decisions.

- Path: AI_information_candidate
- Decision: stop
- Reason: news/LLM features need point-in-time packets and marginal-lift
  evidence before they affect trading, and no quant candidate survived this
  round.
- Next iteration suggestion: keep AI/news advisory-only until a quant candidate
  survives and capability evaluation for news/event sources passes.

## Later Entry Design

- ML entry condition: at least one non-ML path passes the full Wave 9.4 gate,
  has enough OOS decisions, and can be trained with purged/embargoed splits.
- AI information entry condition: a surviving quant path exists; news/event
  capability evaluation passes; PIT feature packets include `visible_at`,
  `published_at`, `fetched_at`, source, input hash, and prompt hash; first use is
  advisory-only.
