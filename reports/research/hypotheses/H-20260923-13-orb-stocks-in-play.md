---
card_id: H-20260923-13
status: preregistered, not executed, 2026-09-23
lane: preregistered
previous: null
direction_id: dir:orb_stocks_in_play_relative_volume
iteration: h20260923_13_orb_stocks_in_play
brief: reports/research/briefs/B-8-orb-stocks-in-play-2026-09-23.md
criteria:
  - name: design_beats_equal_weight_eligible_universe
    threshold: 0
    direction: ">"
  - name: design_beats_rd_placebo_median
    threshold: 0
    direction: ">"
  - name: design_beats_rl_placebo_median
    threshold: 0
    direction: ">"
  - name: design_positive_net_of_20bp_plus_commission
    threshold: 0
    direction: ">"
  - name: select_window_cagr_10bp
    threshold: 0.50
    direction: ">="
  - name: select_window_max_drawdown_10bp
    threshold: -0.35
    direction: ">="
  - name: select_window_placebo_beat_rate
    threshold: 0.90
    direction: ">="
---

# H-20260923-13 Individual-stock opening-range breakout on "Stocks in Play" (relative-volume selection)

- Status: **preregistered, not executed** (round 1) -- hypothesis family: `opening_range_breakout`
  -- layer: individual-stock intraday selection + timing (not a fixed-symbol ETF simplification,
  which is already refuted, see below) -- data tier: **tier 2** (intraday OHLCV + volume across the
  full eligible US-equity universe, cross-sectional)
- Previous link: none (first round of this direction; registry row `dir:orb_stocks_in_play_
  relative_volume` was `harvested`, not yet triaged into a candidate manifest, before this pass)
- Iteration dossier: `reports/research/iterations/h20260923_13_orb_stocks_in_play/` (direction-
  review, external-brief, candidate-manifest with 3 candidates, search-space, cost-contract, data-
  feasibility, decision-record placeholder, engine-design note, sources/; passed
  `oc research direction-check` and `oc research iteration validate --stage pre-backtest`)
- One-line hypothesis: does ranking eligible US stocks by opening relative volume and trading only
  the top 20 with a 5-minute opening-range-breakout stop order, long-only, clear a placebo bar
  (random direction, random non-in-play liquid stocks) and the frozen G1/G3-style gates on this
  project's own minute data and cost conventions -- and is that minute data even survivorship-bias-
  free and adjustment-consistent enough to ask the question honestly?

## Why

Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market" (SSRN
4729284, first version 2024-02-16), read in full this pass (not just the abstract): ~7,000 NYSE+
Nasdaq stocks, 2016-2023, survivorship-bias-free, filtered to price>$5 / 14-day avg volume>=
1,000,000 sh/day / 14-day ATR>$0.50, then further filtered to the top 20 by opening relative volume
(first-5-minute volume over the trailing-14-day same-window average, >=100%). Entry is a **stop
order** (not a walk-in) at the 5-minute opening range's own extreme; stop-loss at 10% of 14-day
ATR; exit at end of day if not stopped; **no profit target**. Reported (long+short combined, no
split ever published): 1,637% total / 41.6% annualized / Sharpe 2.81 / max drawdown 12%, versus a
Base (no relative-volume filter) result of only 29% total / Sharpe 0.48, and S&P 500 buy-and-hold
at 198% total / Sharpe 0.78. QuantConnect's independent replication confirms the mechanism's shape
on a narrower, single-year test (2016 only, top-1,000-liquid universe, Sharpe 2.396 vs SPY 0.836)
and surfaces, in its own comment thread, a community-reported one-bar-late stop-fill discrepancy
between minute-resolution backtests and live trading, plus an Alpaca-specific stop-order rejection
report.

This project has already refuted the single-ETF simplification of this exact author lineage
(`dir:orb_etf_opening_range_breakout`, H-20260918-02/L-20260918-02): OOS 2024-01-02..2026-09-17
failed at every leverage/cost/stop-fill cell, a random-direction placebo captured 92.7-92.9% of the
real return, and shifting the entry time by 30-60 minutes matched or beat the real 09:35 entry --
the residual was intraday beta, not an opening-range signal. The registry row for this direction
explicitly distinguishes it: reopen only if "the individual-stock 'Stocks in Play' relative-volume
selection layer clears its own placebos first," and separately flags its own status as
"feasibility unresolved -- needs a small dev-period check (historical eligibility, bar
completeness, adjustment reconciliation) before scaling to a full backtest." This round is that
check, plus the preregistration it unblocks -- not a claim that the mechanism works.

## Design

Universe and filters: SIP01 (long-only, the paper's own eligibility parameters: price>$5, 14-day
avg volume>=1,000,000 sh/day, 14-day ATR>$0.50, relative volume>=100%, top 20 by relative volume).
SIP02 (long-only, a deliberately stricter, independently-chosen liquidity floor: price>=$10, 14-day
avg volume>=5,000,000 sh/day, 14-day ATR>=$1.00, relative volume>=150%, top 20). SIP03 (long-short,
the paper's own parameters exactly, both directions active, the paper's own 4x leverage cap for
fidelity-checking purposes only -- **never eligible for promotion**, since the published headline
is a combined long+short number with no long-only split ever reported, so SIP01/SIP02 are not
expected to reproduce it and SIP03 exists only to sanity-check implementation fidelity against that
magnitude). Mechanics (all three, fixed, pinned from the primary paper with quotes -- see
direction-review.json): 5-minute opening range (09:30-09:34:59 ET); stop order at the range's own
extreme; exact-open-equals-close doji skips the day; stop-loss at 10% of 14-day ATR from entry; exit
at the stop or end of session (16:00 ET), **no profit target** (a disclosed correction of this
project's own ETF-proxy script, which added a 10R target by analogy from a different paper); sizing
1% of equal-split slot capital (equity/20) per trade at the stop, capped at 1/20 portfolio weight
(resolves the paper's own less explicit sizing language via QuantConnect's published formula);
house leverage cap 1.0x for SIP01/SIP02 (disclosed departure from the paper's 4x, pending an
explicit broker-authorization decision on margin/PDT eligibility). Cost model: 5/10/20bp per side on
notional (all reported), plus a separate, not-blended $0.0035/share commission cross-check column.
Two stop-fill variants reported for every cell: conservative (gap-through fills at bar open) and
one-bar-late (per the QuantConnect forum's reported backtest/live discrepancy).

Windows: design 2016-01-04..2022-12-30 (`data/sip-hist/minute`, older years, mechanism sanity-
checking and data-feasibility development). Frozen select window 2023-09-18..2025-12-31 (`data/sip/
minute`), reused unchanged from this project's existing convention (first established for the daily
ETF-rotation family in H-20260918-05) -- the only window that will ever rank a candidate.
2026-01-02..2026-09-17 reported for continuity only, **no out-of-sample claim**: per
`docs/plan-research-coverage-2026-09-23.zh.md` section 1.6, this window has already been spent by
several other directions this month, including the sibling ETF-ORB study's own OOS window.

## Gates (adoption rule)

All must hold, per candidate, independently, for SIP01 or SIP02 to be considered (SIP03 is never
eligible regardless of outcome): design window -- (a) beats the equal-weight-eligible-universe
control, (b) beats its own RD placebo median, (c) beats its own RL placebo median, (d) positive net
of 20bp/side plus the commission cross-check. Frozen select window, at 10bp -- (e) CAGR>=50% and
max drawdown>=-35% (gate G1, this project's standing "exploded and survived" bar, per
`docs/plan-strategy-factory-2026-09-22.zh.md`), (f) beats >=90% of its own combined RD+RL placebo
draws (gate G3, <=10% placebo win rate). If neither SIP01 nor SIP02 passes all of (a)-(f): "keep
refuted."

## Placebos

**RD** (random direction, 10 seeds x {SIP01, SIP02}): same daily top-20-by-relative-volume
selection, direction drawn randomly instead of read from the opening candle -- repeats the already-
refuted ETF study's own successful placebo at the individual-stock, selection-preserving level.
**RL** (random non-in-play liquid stocks, 10 seeds x {SIP01, SIP02}): same mechanics and
eligibility filters, but 20 stocks drawn at random from the eligible-but-not-actual-top-20 set
instead of ranked by relative volume -- the one control the ETF study could not run, targeting this
mechanism's own added ingredient directly. **ETF-ORB known negative** (0 new simulations):
`dir:orb_etf_opening_range_breakout`'s already-refuted numbers, reused as a reference floor.

## Stop condition

If neither SIP01 nor SIP02 passes all of (a)-(f) at the next (backtest) step, the direction is
refuted for this mechanism; reopen only with new disclosed data, a new published selection rule, or
a materially resolved feasibility gap -- not by re-tuning SIP01/SIP02's filters, windows, or weights
after seeing a partial result, and not by widening the candidate list. Fixed budget for that step:
43 core simulations (SIP01 + SIP02 + SIP03 + 20 RD seeds + 20 RL seeds). This dossier-only pass
(no backtest) is complete when `oc research direction-check`, `oc research iteration validate
--stage pre-backtest`, `oc spec validate`, and `oc research directions validate` all return `ok`,
and the registry row for `dir:orb_stocks_in_play_relative_volume` is updated to `queued`.

## Results

Not executed. This card will be updated (status, per-candidate pass/fail, refuted-or-not, next
step) after the next (backtest) pass runs the preregistered grid in `candidate-manifest.json`.
