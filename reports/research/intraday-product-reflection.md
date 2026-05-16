# Intraday Strategy Product Reflection

- Pure quant report: `/root/codex-test/open-composer/reports/research/nasdaq_intraday_cycle_reversal_1m-intraday-daily-rotation.md`
- LLM meta-selection report: `/root/codex-test/open-composer/reports/research/nasdaq_intraday_cycle_reversal_1m_llm-llm-intraday-selection.md`

## What Worked

- File-first reports make leakage boundaries visible: training, validation, OOS, and walk-forward are separate artifacts.
- The LLM path is constrained to prompt-visible candidate summaries and cannot see final OOS/full-window metrics before selection.
- Daily intraday open/close logic avoids overnight leverage and makes TQQQ buy-and-hold a stress benchmark rather than the only acceptance gate.
- Alpaca cache coverage checks now prevent a short diagnostic fetch from contaminating a longer research window.

## Product Gaps

- The core StrategySpec model cannot yet express portfolio-level daily stock selection and same-day liquidation directly; this research module bridges that gap.
- Alpaca IEX is convenient but not consolidated SIP data, so fill and volume evidence must stay research-only until a stronger feed is compared.
- LLM contribution is currently meta-selection, not independent per-symbol Alpha; future work should add replayable feature packets with visible_at/published_at hashes.
- Intraday risk controls should support explicit end-of-day flatten, hard stop/take ordering assumptions, and liquidity/borrow filters.
- Two-year 1m research still needs a persisted daily feature cache and stage progress telemetry; raw CSV grouping is too opaque for long-running dashboard jobs.

## Next Improvements

- Promote daily portfolio strategies into first-class StrategySpec semantics.
- Add a benchmark suite with QQQ, TQQQ buy-and-hold, TQQQ intraday-only, equal-weight universe, and ex-post best symbol in one common schema.
- Add data-source comparison between Alpaca IEX, Alpaca SIP when available, and Longbridge Nasdaq Basic before any paper-readiness claim.
- Add walk-forward parameter freezing and model-card style LLM prompt auditing to the Dashboard research records.
- Add a blind forward-test artifact that is created only after a candidate family is locked, so OOS discovery does not become accidental future leakage.
