# Hypotheses: h20260929_21_ipo_lockup_expiry

## H1: Shorting recent-IPO common stock around its ~180-day share-lockup expiration date earns a positive, cost-net Sharpe in the 2024-2026 TEST window

- Hypothesis: Field & Hanka (2001) document a statistically significant
  3-day CAR of approximately -1.5% to -1.8% at IPO lockup expiration, stable
  across their decade-long sample and not quickly reversed, with +40%
  permanent volume rise. A calendar-time short book entered a few sessions
  before L and covering a few sessions after, costed with ADV-tiered
  spread and borrow, capped at 15 concurrent positions / 10% of capital
  each, should show a positive Sharpe if the mechanism is still present in
  2024-2026 U.S. IPO activity and survives realistic costs.
- Failure mode: (a) the effect has decayed or been arbitraged away since
  the 2020s (no independent replication was found for this exact window);
  (b) Damodaran's practitioner verdict is correct and the population mean
  is too small relative to real transaction costs once ADV-tiered spread
  and borrow are applied; (c) cross-sectional variance (Gibbs & Hao: PE-backed
  no effect, named short-squeeze tail risk) swamps the average in a
  concentrated 15-name book; (d) too few genuine 2024-2026 IPO events pass
  the PIT construction to reach the 40-event minimum, in which case TEST
  is inconclusive by design and STRESS decides status instead.
- Measurement: calendar-time daily portfolio Sharpe (close-to-close,
  `simulate_book`/`stock_legs`, verified against `run_h20260922_05_salvage`'s
  own engine), and `screen_lane.diversifier_edge_for_offset` combo edge vs
  S3 (vol-matched control), in TEST (2024-01-08..2026-09-17).
- Benchmark family: S3 vol-matched control (combo-edge form of the pass
  bar); a same-symbol-set long-only benchmark (info-only avoid_long_info
  candidate: what a long-only holder would have earned by NOT avoiding
  these names); date-shift (+/-60 session) and random-date placebos on the
  same event set.
- Stop/Pivot criterion: continue only if the best tradeable TEST cell has
  calendar Sharpe >= 1.19 OR combo edge with S3 >= +0.05, beats the
  date-shift placebo at t>=2 (event-date-clustered), AND survives a 2x-cost
  rerun without sign-flipping. If TEST has <40 counted events for the
  judged cell, the verdict is "insufficient events" and STRESS
  (2016-05-02..2023-09-15) decides status instead. No threshold is relaxed
  after seeing the numbers.

## H2 (info only, not gating): the ADV-tier and IPO-to-L momentum filters segment the population the way Gibbs & Hao's PE-vs-VC heterogeneity finding predicts

- Hypothesis: since sponsor-type (VC/PE) classification is not available
  locally, the ADV-tier (a liquidity/size proxy) and the IPO-to-L momentum
  filter (a "how aggressively have insiders' paper gains grown" proxy) are
  cheap substitutes that should show the short signal concentrated in
  smaller/lower-ADV, higher prior-return names if the VC-aggressive-selling
  mechanism Field & Hanka describe is the right explanation.
- Failure mode: no filter meaningfully separates cell performance, which
  would suggest either the mechanism is not present at all in this window,
  or that these two filters are poor proxies for the true segmentation
  variable (sponsor type).
- Measurement: per-cell Sharpe/CAR spread across the 12 tradeable
  (window x ADV-filter x momentum-filter) cells, reported in results.json.
- Stop/Pivot criterion: informational only; does not gate the H1 decision,
  reported alongside it.

## H3 (info only, not gating): avoiding a long position through the lockup window would have saved a long-only holder real return

- Hypothesis: the same CAR that makes a short position profitable (net of
  costs) should, symmetrically, mean that simply not holding (or
  underweighting) these names through L would have improved a long-only
  book's realized return -- a lower-cost, no-short-leg-required version of
  the same information, executable even if the short book itself fails the
  frozen gate.
- Failure mode: n/a (not gating; computed and reported for context only,
  per the task brief's explicit instruction that this candidate does not
  count toward the short-book decision gate).
- Measurement: `avoid_long_info` candidate in candidate-manifest.json;
  equal-weight long exposure over the same event windows, no cost
  tiering applied (diagnostic only).
- Stop/Pivot criterion: n/a (informational row only, reported in report.md
  but never used to pass/fail the frozen decision rule).
