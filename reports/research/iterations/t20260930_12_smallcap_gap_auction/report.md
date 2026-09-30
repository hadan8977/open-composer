# t20260930_12_smallcap_gap_auction — report (C1b)

Verdict (frozen reading in `hypotheses.md`): **closed_unstable** (`results.json` `verdict`). Book not run (`book: not_run_gate_failed`).
`workflow_pass` true; `research_pass` false; `llm_contribution_pass`, `ml_contribution_pass`, `paper_ready_pass` false / not applicable.

## Decision cells (`results.json` `decision_cells`, `screen.<caliber>.K10_EW`)

| condition | X15_K10_EW (free plan, bars to 09:11 ET) | X0_K10_EW (paid real-time SIP, bars to 09:26 ET) | threshold |
|---|---|---|---|
| main 2024-01-08..2026-09-29 mean | -5.37 bp/day (t -1.03, NW t -1.04, 683 days) | -4.80 bp/day (t -0.94) | >= +20 bp and t >= 2.0: FAIL both |
| main placebo beat fraction (100 seeds) | 0.40 | 0.53 | >= 0.90: FAIL both |
| short 2023-02-01..2024-01-05 mean | -4.15 bp/day (234 days) | +0.07 bp/day | >= +10 bp: FAIL both |

LA control (daily open, C1 caliber), K10_EW: main -3.96 bp/day (t -0.57), short +8.78, stress 2016-05..2023-08 daily-only +9.0 bp (t 2.56, 1847 days). LA main is below 20 bp, so the frozen reading gives "edge itself unstable", not "look-ahead".
Same-pool equal-weight baseline (main): X15 pool -4.8 bp/day, X0 -4.4, LA -1.7; X15_K10_EW excess -0.6 bp. Other windows for X15_K10_EW: select 2023-09-18..2025-12-31 +0.6 bp (beat 0.91), 2026-01-01..09-17 -25.9 bp (t -2.97, beat 0.00), 2026-09-18..29 -1.7 bp over 7 days (too short).
All 12 cells x all windows are in `results.json` `screen.<caliber>.<cell>.<window>` (mean_bp, t, nw_t, n_days, n_empty_days, placebo_beat_frac, pool_mean_bp, excess_bp); no day was empty.
Non-decision cells (reported only, not gates): X15_K5_EW main +11.4 bp (t 1.46, beat 1.00, short +1.4); LA_K5_IV main +17.1 bp (t 1.92). None reaches the frozen bar and K5 is not the decision cell.

## Why the C1 +42.5 bp did not carry over (`c1_reconciliation.json`)

The C1 T1 long number is a different object from this step's pool-restricted design: C1 picked the 10 lowest z over the whole >= $1M pool and kept the picks whose dv21 fell in $5-20M (1,535 rows, E_bar +42.17 bp). This step restricts the pool to dv21 in [$5M, $20M) first and takes the 10 lowest z inside it (6,830 rows in the main window). Reconciliation: all 1,535 C1 T1 rows sit inside this step's LA K10 picks and reproduce +42.17399 bp exactly (pipeline check), but the other 5,295 picks average -17.33 bp; median z is -3.74 for the C1 rows versus -1.58 for the rest. So the C1 edge lives in the few market-wide extreme gap-downs (about 2.2 per day), and taking ten names per day inside the small-cap pool dilutes it to -4 bp. This is a property of the frozen selection rule, not a data error. It is also not evidence about the look-ahead question, which this design could not isolate because LA itself is negative.

## Pre-market data quality (X15 / X0)

- Only 35% of pool rows since 2023-02-01 have any pre-market bar by 09:11 ET (638,184 of 985,950 rows have none, `exclusions.X15.no_price_in_window`); 37% for X0. Selected X15_K10 rows (main): median last bar 08:31 ET, median 04:00-09:11 dollar volume $27.7K, median 2 bars (`selected_row_premarket.X15_K10`). The X0 pm dollar volume is still summed over 04:00-09:11 only. The pre-market price of these names is a thin print.
- X15 vs LA selection overlap, K10: 28.0% of X15 rows (1,912 of 6,830) in the main window, 33.4% in the short window; K5: 22.1% / 34.9% (`overlap_x15_la`).
- Excluded rows since 2023-02-01 (`exclusions`): adjustment mismatch (minute prev close vs daily prev_close, |ln| > 0.10) X15 48, X0 56; split-like trigger X15 51, X0 60, LA 71; consistency check unavailable (kept) X15 131, X0 136.
- Pool dv21 is `build_signal_panel`'s 21-session rolling median of close x volume (T-32 code imported unchanged); the design text says "average" and the executor followed the imported implementation.

## Process notes

- The first full screen run had a join defect: month cache files contain after-hours-only groups (bars after 20:00 ET fall on the next UTC day, hence the next month file) that duplicated 44 pool rows at month ends. Found through the reconciliation row count (6,874 vs 10 x 683), fixed (drop null ghost rows at load, assert unique keys and unchanged row count, aggregate now restricted to 04:00-15:59 ET), and the screen was rerun. Numbers above are from the fixed run; the discarded run differed by at most 1 bp per cell and had the same verdict. The design, gates and windows were not changed.
- Placebo: 100 seeds of a random K-basket drawn from the same qualified pool and weight rule; beat fraction = share of seeds whose window mean is below the real mean. Ordinary t and Newey-West 5-lag t are both in `results.json`.

## Caveats

Survivorship bias (no delisted names in `data/sip/daily`) flatters the small-cap gap-down long; here the result is negative anyway. 2024-2026 was already seen by C1 (contaminated). No costs charged in this stage. Nothing here licenses trading, a forward shadow task or a paid-SIP purchase: X0 fails as well, so the paid feed would not rescue this design.

## Files

`results.json`, `c1_reconciliation.json`, `trial-ledger.jsonl` (12 cells), `candidate-manifest.json`, `search-space.json`, `data-feasibility.json`, `direction-review.json`, `external-brief.json`, `cache/premarket/*.parquet`, `cache/daily_{X15,X0,LA}.parquet`; script `scripts/run_t20260930_12_smallcap_gap_auction.py`; tests `tests/test_t20260930_12_smallcap_gap_auction.py`.
