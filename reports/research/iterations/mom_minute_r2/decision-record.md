# Decision Record: mom_minute_r2

- Path: P1_time_series_etf_momentum
- Decision: continue research, but do not promote, train ML, or enter paper.
- Reason: `mom_minute_r2_p1_003` was selected without lockbox access from the
  fixed nine-trial matrix. On the untouched 2026-01-02 through 2026-05-29
  lockbox it returned `26.5356%`, Sharpe `1.8838`, MaxDD `-22.0490%`, and
  `24.0192%` at two-times cost. It passed the five pre-registered gates. However,
  it lagged naive momentum (`39.7480%`) and TQQQ buy-and-hold (`54.8109%`), the
  lockbox contains only 102 trading sessions, and Alpaca IEX remains
  research-only evidence.
- Next iteration suggestion: freeze these parameters and gather a second
  chronological OOS segment or forward observation. Do not rerun selection on
  the current lockbox. Before ML, require broader regime evidence and an
  execution/capacity review; ML must not be used merely to close the benchmark
  gap.

## Later Entry Conditions

- Path: ML_round_candidate
- Decision: stop for now.
- Reason: a technical lockbox pass is not enough to justify training on a short,
  IEX-only sample that still trails the strongest simple benchmarks.
- Next iteration suggestion: reopen only after frozen-parameter OOS evidence,
  purged/embargoed training design, and a linear baseline contract are recorded.

- Path: AI_information_candidate
- Decision: stop for now.
- Reason: no information modality is required to evaluate this base signal, and
  PIT/marginal-lift evidence has not been produced.
- Next iteration suggestion: keep news/LLM advisory-only until a durable quant
  candidate and capability review exist.
