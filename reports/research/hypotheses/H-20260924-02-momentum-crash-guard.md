---
card_id: H-20260924-02
status: refuted -- 0/5 candidates pass G1-or-G1'/G2/G3/G4 (2026-09-24, see report.md and decision-record.md)
lane: preregistered
previous: H-20260918-01
direction_id: dir:momentum_crash_guard_t1_daily
iteration: h20260924_02_momentum_crash_guard
brief: reports/research/hypotheses/H-20260924-02-momentum-crash-guard.md
criteria:
  - name: g1_anchor_cagr
    threshold: 0.50
    direction: ">="
  - name: g1_anchor_max_drawdown
    threshold: -0.35
    direction: ">="
  - name: g1_alt_anchor_sharpe
    threshold: 2.0
    direction: ">="
  - name: g1_alt_anchor_cagr
    threshold: 0.30
    direction: ">="
  - name: g2_holdout_sharpe
    threshold: 1.0
    direction: ">="
  - name: g2_holdout_return
    threshold: 0.0
    direction: ">"
  - name: g3_placebo_beat_frac
    threshold: 0.10
    direction: "<="
  - name: g4_stress20bp_g1_or_g1alt
    threshold: 1
    direction: ">="
---

# H-20260924-02 Daily crash guard for the T1 12-1 momentum book

- Status: **Final, round 1, closed 2026-09-24: refuted.** 0 of 5 candidates
  pass (G1-or-G1') and G2 and G3 and G4 together. CG-DM and CG-MKT-STOP
  never triggered in 2024-2026 (verified working elsewhere: both fire
  correctly around the 2020 COVID crash) because that window never met
  their published bear/high-vol or single-day -7% criteria. CG-BSC-daily
  (and CG-DM-BSC, identical to it here) cuts anchor max DD to -27.4% (under
  the 35% gate) but drags CAGR to 37.0% (under the 50% floor) and fails its
  own calendar-shift placebo (70% of shifts match or beat it) -- the same
  "slides along the risk-return line, doesn't beat a shift placebo" pattern
  L-20260918-01 already found on a different book. CG-STOP is actively
  harmful: worse anchor max DD than unguarded (-41.9% vs -41.5%) and wrecks
  holdout Sharpe (0.15 vs 0.87 unguarded) via threshold-hugging whipsaw. See
  `reports/research/iterations/h20260924_02_momentum_crash_guard/report.md`
  and `decision-record.md` (continue/pivot/stop call and `reopen_if`).
  hypothesis family: momentum_crash_guard --
  data tier: **tier 1** (OHLCV-derived: prices only, no new data source)
- Iteration dossier: `reports/research/iterations/h20260924_02_momentum_crash_guard/`
  (direction-review, external-brief, candidate-manifest with up to 6
  candidates, search-space; passed `oc research direction-check` and
  `oc research iteration validate --stage pre-backtest`)
- One-line hypothesis: does a DAILY exposure guard, built from the published
  momentum-crash literature (Daniel & Moskowitz 2016 bear/panic state;
  Barroso & Santa-Clara 2015 realized-vol scaling; a market-crash circuit
  breaker and/or book-level stop), bring the T1 12-1 momentum book's anchor
  max drawdown to <=35% while keeping CAGR>=50%, and beat a calendar-shift
  placebo of its own multiplier series?

## Why

The T1 book (`reports/research/signal-cards/mom_12_1.md`: top 30 of the
largest 500 names by 12-1 momentum, overlapping 20-session cohorts) clears
this repo's recent-window return bar but not the drawdown bar: the signal
card's full-window (2017-2026) number is 26.5%/yr, max DD -50.2%; our notes
claim roughly 59.8%/yr and -41.6% max DD on the anchor window specifically
(2024-01-08..2026-09-16), which Step 2 of this round verifies directly
before anything else runs.

Earlier local work on a DIFFERENT (monthly, kernel-loop) momentum book
(`H-20260918-01`, refuted, see `reports/research/lessons/L-20260918-01.md`)
found that a volatility target and a trend gate applied at the book's own
(monthly) rebalance cadence only slid along the same risk-return line and
did not beat a +/-21-session calendar-shift placebo. That leaves one
untested variant: a guard updated DAILY (not at the book's own slower
cadence), built from a genuinely different, published mechanism rather than
a home-grown SMA gate. `docs/research-mission.zh.md` requires searching
primary sources before spending compute; see `external-brief.md` for the
full source list. Key findings: Daniel & Moskowitz's (2016) crash mechanism
is concentrated in momentum's short (past-loser) leg, which this long-only
book does not hold, so a null or weak result for the bear/panic gate is a
real, pre-registered possibility, not a bug. Even the best published
combined crash indicator (Dierkes & Krupski 2022, via Alpha Architect) only
cuts crash magnitude by about two-thirds, not to zero. Two real, dated
2025-2026 momentum-factor drawdowns (a fast, deleveraging-driven March 2025
crash; a >=24%-from-peak 2026 Goldman Sachs Momentum Basket drawdown) fall
inside this round's own select/holdout windows and are checked directly
against the book's own return series rather than assumed.

## Design

Up to 6 candidates, each a daily exposure multiplier in [0,1] applied to the
unchanged T1 20-session book (held-weight matrix scaled row-wise by the
multiplier, so turnover cost is charged on the scaled matrix, not assumed
away), remainder in SHY (next-open return, matching this repo's other
sleeves' cash convention). Every guard reads information only through the
prior session's close and applies at the next open; guard statistics that
use the book's own (open-to-open) daily return series use a 2-session
settlement lag, not 1 (see decision-record.md for the derivation: the
book's own `ret[i]` return is not actually known until `open[i+1]`, the
same moment a naive 1-lag guard would apply it). Every threshold is either
a published value or computed only on 2016-01-04..2023-09-15 (development
window, intersected with the book's actual return history, which starts
2017-01-03 per `data/features/daily_broad` momentum coverage -- disclosed,
never extended into select/holdout/anchor).

- **CG-DM**: Daniel-Moskowitz bear/panic state. Bear = SPY trailing 504-
  session (24-month) cumulative return < 0. High-vol = SPY trailing 126-
  session realized annualized vol > its own development-window median.
  Panic = bear AND high-vol -> multiplier 0, else 1.
- **CG-BSC-daily**: Barroso-Santa-Clara realized-vol scaling, updated daily
  on the book's own (10bp-net) daily returns, 126-session trailing window,
  target = the book's own median realized vol over the development window,
  cap 1.0.
- **CG-STOP**: book-level drawdown circuit breaker. Trigger threshold from
  the book's own development-window max drawdown via the repo's existing
  kill-switch formula (`docs/plan-strategy-factory-2026-09-22.zh.md`
  section 1: 1.5x(dd)x0.5, clipped to [12%,30%], development window
  substituted for the anchor window the formula normally reads). Fixed
  re-entry: the underlying (unguarded) book's own equity crosses back above
  its own trailing 50-session SMA.
- **CG-DM-BSC**: CG-DM multiplier x CG-BSC-daily multiplier (belt-and-
  suspenders combination of the two required published families).
- **CG-MKT-STOP**: market-crash circuit breaker using the SEC's actual
  published Level-1 market-wide circuit breaker (7% single-session S&P 500
  decline, proxied by SPY) -> de-risk to cash for a fixed re-entry window
  (computed from development-window recovery behavior where enough events
  exist, else a disclosed round number).

Frozen protocol, unchanged: select 2023-09-18..2025-12-31 (ranking window,
never used to fit a threshold), holdout 2026-01-02..2026-09-17 (scored
once), anchor 2024-01-08..2026-09-16. Costs 10bp primary / 20bp stress per
side.

## Gates (adoption rule)

Per candidate, independently: **G1** anchor CAGR>=50% and max DD<=35%;
**G1'** anchor Sharpe>=2.0 and CAGR>=30%; **G2** holdout Sharpe>=1.0 and
holdout return>0; **G3** <=10% of 20 calendar-shifted (1-20 session)
multiplier placebos match or beat the real guard's anchor Sharpe; **G4** G1
or G1' still holds at 20bp; **G5** long-only, Alpaca-executable (the guard
changes aggregate exposure/cash split on top of the existing tradable
top-30 book). A candidate passes only if G1-or-G1', G2, G3 and G4 all hold
simultaneously. Each candidate's 2016-01-04..2023-09-15 stress-window
result is reported as disclosure, never a gate.

## Placebos

The guard's own daily multiplier series shifted by each of 1..20 sessions
(20 seeds), non-circular with edge sessions padded at full exposure
(multiplier 1.0, i.e. no guard), matching the frozen recent-menu calendar-
shift convention's spirit while operating on the multiplier series directly
per this card's own text.

## Stop condition

A candidate that fails any of G1-or-G1', G2, G3, G4 is refuted for this
parameterization. If none of the up to 6 candidates passes, the direction
is refuted; reopening requires a new published mechanism, new disclosed
data (e.g. options-based tail hedges, out of this round's long-only
[0,1]-multiplier scope), or evidence the 2024-2026 regime has changed
enough to revisit development-window thresholds -- not re-tuning the
frozen thresholds against the anchor or holdout windows. Fixed budget: up
to 6 preregistered candidates, no added cells. This is round 1 of this
direction.
