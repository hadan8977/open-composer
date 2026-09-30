# Protocol preregistration: h20260929_81_ipo_aftermarket (T-20260929-81)

Frozen before any return is computed. Numbers below come from the queue block
`### T-20260929-81` and are not changed after results. Operational details that
the queue text leaves open are fixed here.

## Sample
- Events: `reports/research/iterations/h20260929_21_ipo_lockup_expiry/events.parquet`,
  `method == "424b4_confirmed"` and `is_despac == False`. The T-21 non-common-stock name
  filter (preferred, debentures, notes, warrants, rights, tangible equity units, depositary
  shares) was already applied when that table was built (3,916 candidates -> 3,577 events,
  339 removed, `build_summary.json`); this task does not modify the table and reports the
  counts before/after each additional filter. Fallback-method events (where the T-21 hand check
  found 6/17 = 35% mismatches) are excluded by the `424b4_confirmed` restriction.
- First trading day `f`: first session on or after `ipo_date` with finite sanitized open and close in
  `data/features/daily_broad`, required within 7 calendar days of `ipo_date`.
- Eligible: first close >= $5 and median over the first 10 sessions (from `f`) of close x volume
  >= $5,000,000 (volume from `data/sip/daily`).
- Prices: `daily_broad` open/close pass `sanitize_price_matrices` defaults (T-21
  `load_event_stock_panel`); QQQ and IWM open/close from `data/sip/daily` via `base.load_panel`
  and the same sanitizer. Events with a masked (NaN) entry or exit price are dropped and counted.
  Sessions come from the `daily_broad` calendar.

## Dates
- QP = first session with date >= date(f) + 26 calendar days (Bradley-Jordan-Ritter: day 0 is the 26th
  calendar day or the first trading day thereafter; day 0 = the queue's "first trading day after 25 calendar days").
- A window (k in {2,5}): signal = close of QP-3, entry = open of QP-2, exit = close of QP+k.
  Control window: signal QP-2, entry open of QP-1, exit close of QP+2 (not decision-eligible).
- Non-gating diagnostic D10: QP10 = first session >= date(f) + 11 calendar days (FINRA 2241 minimum quiet
  period of 10 days), window as A with k=2.
- R5 = close(f+4) / open(f) - 1. B: R5 >= +20%, signal = close(f+4), short entry = open(f+5), exit = close(f+5+h-1),
  h in {20, 40}. C mirror (not a candidate): R5 <= -10%, long, same windows.

## Pools, costs
- ADV proxy at the signal date: median close x volume over the trailing <= 21 sessions since `f`
  (inclusive of the signal day); rank = 1 + number of `daily_broad` symbols whose `dollar_adv_21` on that date is
  larger. Pool `adv1500`: rank <= 1500. Pool `all`: every eligible event.
- Cost per side: rank <= 500: 3 bp, <= 1000: 6, <= 1500: 12, else or unranked: 25. Round trip = 2 x side cost.
- Short borrow: 3%/yr if rank <= 1500 else 25%/yr, x calendar days from entry date to exit date / 360.
- Market adjustment: stock return minus the mean of QQQ and IWM returns over the same open(entry) -> close(exit)
  window. Hedge cost is not charged (favours the strategy).

## Statistics
- A: net CAR = market-adjusted return - round-trip cost. t = cluster-robust t of the mean, clusters = calendar `ipo_date`.
  Groups: by entry year, pooled 2016-2026, entries from 2024-01-01.
- B: net short return (raw, gate) = -(exit close / entry open - 1) - round-trip cost - borrow; the
  benchmark-hedged version is reported as secondary. Leave-out: drop the 3 events with the largest net short returns.
- Placebos (A, pooled): QP index shifted by +10, -10, +60, -60 sessions (net CAR with the real event's cost);
  200 random-date draws (QP replaced by a uniform random session in [f+12, f+250], seed 20260930); report
  mean, 95th percentile and the fraction of draws >= the real pooled mean.
- Non-decision baselines: all eligible events shorted for 20/40 sessions from session 6 (no R5 filter); family C.

## Gates (frozen)
- A passes if some QP-3 window candidate (4 of them) has: pooled net mean >= +1.0% and t >= 2.5; entries from 2024
  n >= 100 and net mean >= +1.0%; both the +10 and -10 placebo net means <= 0.5 x the real pooled net mean.
- B passes if a 20-session candidate (2 of them) has: entries from 2024 net raw short mean >= +3% with t >= 2, and the mean after
  removing the top-3 winners > 0.
- Both fail: "IPO aftermarket calendar windows closed", registry refuted, no ledger. One passes: screen that family only
  (runbook section 5; DSR trials = 12 as stated in the queue; the registered count is 10 = 6 A + 4 B).
