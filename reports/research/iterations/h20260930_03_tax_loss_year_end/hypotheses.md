# Hypotheses: h20260930_03_tax_loss_year_end

Design source: queue task `T-20260930-03` in `reports/research/control/autonomous-queue.md`
(plan and done_when written 2026-09-30 01:07 and committed before this dossier).
Everything below the line "Frozen from the queue plan" restates that plan without
changing a number. The section "Implementation definitions" only fills gaps the plan
leaves open; it was written before any result was computed and is not changed after.

## Frozen from the queue plan

- Data: `data/sip/daily` (US daily bars, 2016-01-04 to 2026-09-29). Ten signal windows,
  15 December 2016 to 15 December 2025; the latest exit (2026-01-30) is inside the data.
  Price matrices pass `sanitize_price_matrices` with default parameters first.
- Pool: ADV top 1,500 on the signal day, price >= 5 USD, funds excluded (the fund/non-common
  name filter of T-21: `is_probable_fund_or_etf` plus `load_non_common_stock_symbols`).
- Signal: YTD = close on 15 December / close on the last trading day of the prior year - 1.
- Main window W2: signal on the 15 December close; entry at the 16 December open (or the
  first trading day after); exit at the close of 15 January or 31 January (or the previous
  trading day).
- Candidates (6): {YTD lowest decile} x {pool ADV top 1,500, pool ADV rank 500-1,500} x
  {exit 15 Jan, 31 Jan} (4), plus {YTD <= -30%} x {pool ADV top 1,500} x {exit 15 Jan,
  31 Jan} (2). The -30% threshold is not tuned.
- Benchmark: equal-weight pool. IWM hedge reported separately. Costs per side by ADV
  rank: 1-500 3 bp, 500-1000 6 bp, 1000-1500 12 bp (`SPREAD_BPS_TIERS` in
  `scripts/run_h20260929_21_lockup_books.py`).
- Diagnostic window W1: signal 15 November, exit 15 December. Direction only, not a
  candidate; no short side (borrow not checked).
- Placebo windows (not candidates): same construction with signal 15 February -> 31 March
  and 15 June -> 31 July, ten years each.
- Cheapest negative test (before any ledger): ten annual W2 equal-weight excess returns,
  mean after costs, year-clustered t, count of positive years, mean without the best
  year, Dec 2024 and Dec 2025 separately, compared with the two placebo windows.
- Continue conditions (numbers frozen). For the 16 Dec -> 31 Jan window, mean excess
  after tiered costs >= +1.5%; >= 7 of 10 years positive; year-clustered t >= 2.0; the two
  placebo-window means sum to at most half of the real mean; both 2024-onward windows
  (Dec 2024, Dec 2025) positive. Any condition failing closes the direction as
  "tax-loss rebound closed" (refuted): no ledger, no threshold change. A pass is only a
  ten-observation "recent observation": the 2026-12-15 window is the true out-of-sample
  test and becomes a forward-tracking task with not_before 2026-12-15; no paper trading.

## Implementation definitions (gap filling, frozen before results)

1. Applying the five conditions: each of the six candidates is checked against all five
   conditions on its own window (the 15 January candidates use the same numeric thresholds;
   their placebo windows use the same offset, 15 March and 15 July; the 31 January
   candidates use 31 March and 31 July). Overall verdict: `refuted` unless at least one
   candidate passes all five, in which case `watch_recent_forward_only` (six candidates
   tested, so a lone pass is weak evidence). "Sum of the two placebo means <= half of the
   real mean" is implemented literally as sum, and requires a positive real mean; the
   average-based reading of the registry text is also printed but not used.
2. Dates: signal day = last trading day on or before the 15th (calendar day); entry = first
   trading day on or after the 16th; exit = last trading day on or before the target day.
   YTD baseline = last close of the prior year; for 2016 the data start on 2016-01-04, so
   the 2016-01-04 open is the baseline proxy (flagged; a 2017-2025 nine-year cut is
   reported but is not a verdict input).
3. ADV = median of close x volume over the 21 sessions ending on the signal day (at least
   15 valid sessions), ranked among symbols passing the fund filter, price >= 5 and having
   a baseline close, a signal-day close and an entry-day open. Pool A = ranks 1-1,500;
   pool B = ranks 501-1,500 (its benchmark is the equal-weight pool B).
4. Selection: lowest decile = YTD <= 10th percentile (linear interpolation) of the pool's
   YTD; the -30% rule is YTD <= -0.30 inside pool A.
5. Return of a name = exit close / entry open - 1; if the symbol stops printing before the
   exit day its last valid close inside the window is used and the count is reported.
   Basket = equal weight. Net = gross - mean over names of 2 x tier bp; excess = net basket
   - equal-weight pool gross (costless benchmark, conservative). IWM version: net basket
   - IWM open-to-close over the same days.
6. Data hygiene applied to pool and candidates alike: after `sanitize_price_matrices`,
   symbols with any one-day close ratio within 3% (log) of a common split multiple
   (`is_split_like_ratio`) between the baseline day and the exit day are excluded. Unadjusted
   splits otherwise create fake losers (forward split) or fake winners; counts are reported.
7. Statistics: year-clustered t = mean / (sample std / sqrt(10)) of the ten annual net
   excess returns; "mean without best year" drops the largest annual excess.

## Hypothesis

US stocks with the lowest year-to-date return on 15 December (tax-loss candidates, ADV top
1,500) outperform the equal-weight pool from the next open to 15 or 31 January by at least
1.5% after tiered costs, in at least 7 of 10 Decembers, with year-clustered t >= 2, with the
two off-season placebo windows adding at most half of that, and positive in both Dec 2024 and
Dec 2025. Support: Ivkovic-Poterba-Weisbenner (tax-loss selling in December, trade data) and
Grinblatt-Keloharju (net tax-loss buying pressure negative before, positive after the turn of
the year); no opened source gives a 2016-onward US price effect size, so the prior is low.

## Failure mode

The effect is weakened or gone after 2016 (more tax-sheltered accounts, arbitrage, McLean-
Pontiff post-publication decay), is concentrated in illiquid stocks outside the ADV top
1,500 (Kaul et al.), is not distinguishable from the generic loser-rebound / low-price
mean reversion present in every window (placebo windows), or is carried by one year.

## Measurement

Ten annual net excess returns per candidate (2016-2025), mean, year-clustered t, positive
year count, mean without the best year, Dec 2024 and Dec 2025 separately, February and June
placebo means, W1 diagnostic, IWM-hedged version; all written to
`reports/research/iterations/h20260930_03_tax_loss_year_end/results.json` by
`scripts/run_h20260930_03_tax_loss_year_end.py`.

## Stop/Pivot criterion

Any of the five continue conditions failing for a candidate leaves that candidate closed;
if no candidate passes all five the direction is closed as "tax-loss rebound closed"
(refuted): no ledger, no threshold change, no re-window. A pass only opens a forward-only
tracking task with not_before 2026-12-15; no paper trading without the owner.
