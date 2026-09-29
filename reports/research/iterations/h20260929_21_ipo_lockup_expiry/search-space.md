# Search Space: h20260929_21_ipo_lockup_expiry

One path, `ipo_lockup_expiry_screen`, 13 candidate cells (<=24 budget).

## Event construction (PIT, no lookahead)

`scripts/build_h20260929_21_lockups.py`: SEC EDGAR 424B4 filings (2015Q1-
2026Q3 quarterly `form.idx`), mapped CIK->ticker via the current
`company_tickers.json` snapshot, cross-checked against the ticker's first
trade date in `data/features/daily_broad` (-3..+5 calendar days) to confirm
a genuine IPO rather than a follow-on offering ("424b4_confirmed"); symbols
not claimed this way, with a first trade date at least 180 days after the
panel start and passing the SPAC-unit-suffix / min-price exclusion
heuristics, are added via a first-trade-date fallback
("first_trade_fallback"). Lockup date L = IPO date + 180 calendar days
(or an explicitly parsed lock-up-period length from the 424B4 text where
found), rolled forward to the next date present in the daily panel's own
trading-day index. de-SPAC filings are tagged `is_despac` (text keyword
and/or flat-$10-price heuristic), not separately modeled.

## Event windows (2 tradeable + 1 info-only)

- **short_L5_L1**: short from close of L-5 (trading days) to close of L+1.
- **short_L1_L5**: short from close of L-1 to close of L+5.
- **avoid_long_info**: INFO ONLY, equal-weight LONG over the same
  short_L5_L1 window (what a long-only holder saves by avoiding); no
  decision weight, per the task brief.

## Filters (crossed with the 2 tradeable windows)

- **ADV filter**: {`adv1500`: ADV rank at L-10 <= 1500 (easy-to-borrow
  proxy; beyond 1500 is a separate, higher-cost tier below, not excluded),
  `unrestricted`: no ADV filter}.
- **Momentum filter**: {`all`: no filter, `pos`: IPO-to-(L-10) cumulative
  return > 0, `neg`: IPO-to-(L-10) cumulative return <= 0} -- a cheap local
  proxy for the VC-aggressive-selling / PE-no-effect heterogeneity Gibbs &
  Hao (2018) document, since sponsor-type is not available locally.

2 windows x 2 ADV filters x 3 momentum filters = 12 tradeable cells +
1 info-only row = 13 total.

## Costs (frozen, preregistered before any return is computed)

Spread by ADV rank at L-10: top-500 3bp/side, 500-1000 6bp/side, 1000-1500
12bp/side, beyond-1500/unranked 25bp/side. Borrow: 3%/year (360-day
convention, matches Alpaca's own HTB fee formula) for the top-1500 ADV
tier, 25%/year beyond, charged every trading day the short is held on the
short notional. A 2x-costs variant (both spread and borrow doubled) is
computed for every kept candidate as part of the frozen decision rule.

## Portfolio construction

Calendar-time, equal-weight open short positions, capped at 15 concurrent
and 10% of capital each (first-come priority beyond 15 simultaneously
signal-active events), remainder in BIL (actual daily BIL prices via
`scripts/screen_lane.py`'s own `base.load_panel`/duckdb path, reused).
Signal at close, fill at next session's open -- implemented as the same
old-weight-earns-overnight / new-weight-earns-intraday leg-mixing formula
as `screen_lane.s3_incumbent` (`simulate_book`/`stock_legs`, verified
against the actual frozen `run_h20260922_05_salvage` engine in
`tests/test_h20260929_21_lockup.py`, not assumed to match).

## Judged benchmark family

`s3_incumbent` (vol-matched control) for the combo-edge form of the pass
bar; a raw calendar-Sharpe form of the same pass bar; the `avoid_long_info`
row as a same-symbol-set long-only benchmark; date-shift (+/-60 session)
and random-date placebos (both required, both reported with an
event-date-clustered t-stat); DSR with trial_count = 13 (the full
preregistered candidate count, including the info-only row).
