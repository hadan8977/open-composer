# Decision Record: h20260924_02_momentum_crash_guard

Preregistered 2026-09-24 before any guarded return was computed; closed out
2026-09-24 after Step 2 (base-book reproduction, 5 guard backtests) and
Step 3 (placebos, gates) ran to completion. Full numeric results:
`report.md`, `results.json`, `trial-ledger.jsonl`, `cache/*.parquet`.

## P1 (single path: momentum_crash_guard_t1_daily, 5 candidates)

- Path: momentum_crash_guard_t1_daily (cg_dm, cg_bsc_daily, cg_stop,
  cg_dm_bsc, cg_mkt_stop)
- Decision: **stop.** 0 of 5 candidates pass (G1-or-G1') and G2 and G3 and
  G4 together; every candidate fails G2 (holdout Sharpe, best 0.87 of a
  required 1.0) and G3 (placebo beat-fraction 0.70-1.00 against a required
  <=0.10) simultaneously. This is not a pivot to a 6th candidate within the
  same mechanism family: all 3 required published families (bear/panic
  regime, realized-vol scaling, market-or-book-level stop) and both natural
  extensions (their product; a market-level counterpart to the book-level
  stop) were tested, per the card's up-to-6 budget, and none clears the
  bar.
- Reason: card H-20260924-02 asked whether a daily crash guard, built from
  published momentum-crash literature, can bring the T1 book's anchor max
  drawdown to <=35% while keeping CAGR>=50% and beating a calendar-shift
  placebo; this had not been tested locally before (H-20260918-01 tested a
  different, monthly-cadence gate on a different book construction, and was
  itself refuted). The result here is a genuine negative, not a workflow
  failure: CG-DM and CG-MKT-STOP are verified to work mechanically (both
  fire correctly around the 2020 COVID crash, in-sample) but never trigger
  in 2024-2026 because that window never met their published bear/high-vol
  or single-day-7% criteria; CG-BSC-daily reproduces L-20260918-01's
  "vol targeting slides along the same risk-return line, and the
  improvement doesn't beat a calendar-shift placebo" finding on a new book
  at a new (daily) cadence; CG-STOP is actively harmful (worse anchor
  drawdown than unguarded, and wrecks holdout Sharpe/return) because its
  fixed threshold and SMA re-entry whipsaw when the book's drawdown hovers
  near the trigger while equity is already above its own trailing SMA.
- Next iteration suggestion: do not re-tune these 5 candidates' thresholds
  against the anchor or holdout windows -- that would be exactly the kind
  of post-hoc fitting `docs/research-mission.zh.md` prohibits. If this
  direction is reopened, it needs one of: (a) a genuinely different
  published mechanism not covered here (e.g. a full regime switch to
  short-term reversal in high-vol months, per Butt, Kolari & Sadaqat 2024
  via claim `tommijohnsen2025_75th_percentile_rule` -- out of this round's
  long-only [0,1]-multiplier scope, would need explicit user sign-off to
  add shorting); (b) new disclosed data (e.g. an options-based tail hedge,
  also out of this round's scope); or (c) evidence the 2024-2026 regime has
  materially changed. Absent one of those, the honest conclusion is that
  the T1 book's drawdown is not fixable within a long-only daily-guard
  framework built from these three mechanisms, and effort is better spent
  elsewhere (per L-20260918-01's own suggestion: intraday strategies, a
  wider factor screen, or genuinely raising the book's Sharpe rather than
  reshaping its risk).
- reopen_if: a new published, long-only-compatible crash-mitigation
  mechanism is found with post-2020 evidence it fires on sector-rotation-
  driven (not broad-single-day) momentum crashes like March 2025 or the
  2026 Goldman Sachs Momentum Basket drawdown; or the user explicitly
  authorizes a short-leg/regime-switch or options-hedge candidate family
  that falls outside this round's long-only [0,1]-multiplier scope.

## Timing-lag derivation (recorded before backtesting, referenced by the
unit tests)

The T1 book's own return series (`open_composer.research.signal_card`'s
`next_open_returns`/`book_returns`) is open-to-open: `ret[i] =
open[i+1]/open[i]-1`, and `held[i]` (the position entered at open `i`, per
`hold()`'s own docstring) is multiplied by `ret[i]` inside `book_returns`.
This means the book's own daily P&L at index `i` is not actually fully
determined until `open[i+1]` -- one session later than a naive reading of
"row i" would suggest. A guard multiplier `m[s]` must be decided using
information available strictly before `open[s]` (i.e. through `close[s-1]`).
Since `ret[i]` (and hence `gross[i] = held[i]*ret[i]`) only becomes known at
`open[i+1]`, the latest book-return observation safely known by `close[s-1]`
is `gross[s-2]`, not `gross[s-1]`. Every guard statistic derived from the
book's OWN return series (CG-BSC-daily's realized vol, CG-STOP's drawdown)
therefore uses a 2-session settlement lag. Guard statistics derived from an
independent, standard close-to-close series (SPY's own returns, for CG-DM
and CG-MKT-STOP) use the ordinary 1-session lag, since `close[s-1]` is by
definition known at `close[s-1]`. `tests/test_run_h20260924_02_momentum_crash_guard_script.py`
asserts both lags directly (changing the most recent not-yet-settled
observation must not change the multiplier that is about to be applied).
