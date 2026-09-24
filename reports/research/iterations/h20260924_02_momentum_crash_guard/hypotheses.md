# Hypotheses: h20260924_02_momentum_crash_guard

Card: `reports/research/hypotheses/H-20260924-02-momentum-crash-guard.md`.
Five falsifiable hypotheses, one per candidate guard, all sharing the same
benchmark family (the unguarded T1 book at 10bp/20bp) and the same stop/pivot
rule (fails any of G1-or-G1', G2, G3, G4 -> refuted for this parameterization).

## H1 (CG-DM)

- Hypothesis: a binary multiplier that goes to 0 exposure when SPY's trailing
  24-month return is negative AND its trailing 126-day realized vol exceeds
  its own development-window median (Daniel & Moskowitz 2016's published
  panic-state definition) reduces the T1 book's anchor max drawdown enough to
  clear G1/G1' without breaking G2/G3/G4.
- Failure mode: the panic state never triggers in 2024-2026 (no 24-month SPY
  decline in this bull-market window), so the guard is numerically identical
  to the unguarded book and does not change any metric -- pre-registered as
  an honest, expected possible outcome per external-brief.md, not evidence of
  an implementation bug if observed. A second failure mode: the book's crash
  mechanism (long-only, no short leg) does not resemble DM's short-leg-driven
  crash mechanism, so even a correctly-triggering gate adds little.
  A third failure mode: even if it reduces drawdown, the reduction does not
  beat the calendar-shift placebo (G3), the same failure mode that refuted
  H-20260918-01's trend gate.
- Measurement: anchor/holdout/select-derived G1, G1', G2, G3, G4 at 10bp and
  20bp; 2016-01-04..2023-09-15 stress disclosure.
- Stop/Pivot criterion: refuted if any of G1-or-G1', G2, G3, G4 fails.

## H2 (CG-BSC-daily)

- Hypothesis: scaling the book daily by target_vol / trailing-126-session
  realized vol (Barroso & Santa-Clara 2015's formula, updated daily instead
  of monthly, target = the book's own development-window median vol, capped
  at 1.0) reduces max drawdown enough to clear G1/G1' without breaking
  G2/G3/G4.
- Failure mode: per L-20260918-01, pure vol targeting (no leverage) mostly
  slides along the same risk-return line (lower vol, proportionally lower
  CAGR) rather than improving risk-adjusted return -- expected to be hard to
  pass G1's CAGR>=50% floor even if it clears the drawdown side. Also fails
  if the daily-update turnover cost erodes returns more than the monthly
  cadence BSC actually tested.
- Measurement: same as H1.
- Stop/Pivot criterion: same as H1.

## H3 (CG-STOP)

- Hypothesis: a book-level drawdown circuit breaker (threshold from
  development-window drawdown behavior via the repo's existing kill-switch
  formula, fixed SMA-50 re-entry) cuts the worst of the anchor-window
  drawdown enough to clear G1/G1' without breaking G2/G3/G4.
- Failure mode: a reactive (already-in-drawdown) trigger locks in losses
  without preventing them (buys back in only after a slow SMA-based
  re-entry, potentially missing the rebound that historically follows
  momentum crashes per DM's own "contemporaneous with market rebounds"
  finding), which could hurt CAGR more than it helps drawdown.
- Measurement: same as H1.
- Stop/Pivot criterion: same as H1.

## H4 (CG-DM-BSC)

- Hypothesis: the product of CG-DM's and CG-BSC-daily's multipliers performs
  better (higher anchor Sharpe, smaller drawdown) than either alone, since
  DM's own dynamic strategy combines a regime signal with a variance
  forecast.
- Failure mode: multiplying two partial or non-triggering guards compounds
  their individual weaknesses (e.g. BSC's CAGR drag plus DM's rare
  triggering) without combining their strengths.
- Measurement: same as H1, plus a direct comparison to H1 and H2's own
  metrics in report.md.
- Stop/Pivot criterion: same as H1.

## H5 (CG-MKT-STOP)

- Hypothesis: a fixed-duration flat-to-cash response to the SEC's published
  7% single-session S&P 500 (SPY) decline (Level-1 market-wide circuit
  breaker) catches fast, deleveraging-driven crashes (like March 2025, per
  Joseph Pach's account) that a slow 24-month bear indicator (CG-DM) would
  miss, reducing anchor max drawdown enough to clear G1/G1' without breaking
  G2/G3/G4.
- Failure mode: single-day 7%+ declines are rare even in 2024-2026 (fewer
  events than monthly-frequency schemes assume), so the guard rarely fires
  and changes little; or the fixed re-entry duration re-enters into a
  continuing decline and adds turnover cost without reducing drawdown.
- Measurement: same as H1.
- Stop/Pivot criterion: same as H1.

## Overall

If none of H1-H5 clears every required gate, the direction is refuted for
this parameterization per the card's stop condition, and the honest
conclusion (per docs/research-mission.zh.md) is that the T1 book's drawdown
problem is not solvable within a long-only [0,1]-exposure-multiplier
daily-guard framework built from these published mechanisms -- not that no
guard of any kind could ever help (e.g. a full regime switch to reversal,
per Butt/Kolari/Sadaqat 2024, remains untested and out of this round's
scope).
