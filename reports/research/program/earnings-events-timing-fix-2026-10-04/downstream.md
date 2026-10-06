# T-20261004-56 downstream of the 8-K acceptance-time fix (facts only, 2026-10-06, pending lead review)

## 1. `scripts/build_pm_earnings_events.py`
- New `eastern_from_true_utc` (reads `acceptance_utc` as true UTC). `match_announcements` default mode "corrected" now uses it; mode "double_shifted" keeps the old recovery for the pre-fix backup; "literal" unchanged.
- Tests added in `tests/test_build_pm_earnings_events.py` (fixed-table rows, EDT and EST; match on a fixed row). 25 tests pass in that file. PM pipeline not rerun.

## 2. `data/features/sue_8k_visible` rebuild
- Backup: `data/live/backup-features-20261004/sue_8k_visible/` (cp -a, sha256 equal for 2024/2025/2026). Rebuilt with `scripts/build_sue_8k_visible.py` under `run_capped.sh --mem 1.2G`.
- Rows: old 11556 -> new 11605 (2024 3857, 2025 4340, 2026 3408). Paired by (symbol, value, k-th by date): 11553 pairs, 3 only in old, 52 only in new.
- **`trade_date` changed in 95 paired rows** (87 earlier, 8 later; shifts -4 to +60 days, median -1 day; old dates 2024-01-24 .. 2026-08-05). Source: `sue_compare.json` (`paired_trade_date_changed`), script `compare_sue_8k.py`.
- Controlled check (same left table, old backup earnings table vs new): also 95 changed, 0 only-old, 34 only-new (the 48 new filings). So the 95 are timing effects, the extra rows are new filings.
- The 268 in T-52 section 4 counts all 16041 Item 2.02 filings crossing the 16:00 ET cut; only 95 of them reach a matched SUE row.
- The stored old table (11556 rows) is not identical to a rebuild from the backup earnings table (11571 rows): the old table predates later left-table rows. Not traced further.

## 3. T-20260930-14 (overnight persistence 12m), gate_b: unaffected
- `scripts/run_t20260930_14_overnight_12m.py`: `earnings_events` is read only in `earnings_night_keys` (def l.875, glob l.84, read l.878-885), called only from `diag_stage` (l.967); the diagnostic block is stated not to enter the gates (l.1326).
- gate_b = `gate_b()` (l.191) fed by `analyze_official` (l.684; call l.800) from `build_picks` (l.504-548) plus official-price files; no earnings reference there.
- `iterations/t20260930_14_overnight_persistence_12m/results.json`: gate_a true, gate_b false (delta_ls -2.72 bp, delta_lo20 -5.88 bp, missing 0.0). No rerun needed; `rerun-20261004/` not created.
- Only diagnostic d3 (ex-earnings-night LS, hypotheses.md l.75) used the stale times.

## 4. Stored late timestamps (not rebuilt; lines closed or cancelled)
| Table | Column | Check vs fixed table |
|---|---|---|
| `data/features/h20260928_17_filing_risk_labels_scores/items.parquet` (436 rows) | `acceptance_utc`, `visible_at` | stored minus new: +4 h 281 rows, +5 h 155 rows |
| `data/features/h20260928_16_sentiment_accel_scores/items.parquet` (2092; 50 are item_kind 8k) | `source_timestamp`, `visible_at` (8k rows) | 8k rows: +4 h 49, 0 h 1 (news rows unaffected) |
| `data/features/earnings_text_scores/{2024,2025}.parquet` (2149, 140 rows; `unknown.parquet` 200 rows has null acceptance_utc) | `acceptance_utc` | +5 h 1414, +4 h 868, 0 h 7 |
| `data/research/h20260929_20_news_nonews_drop_reversal/events.parquet` (35499) | no timestamp stored; derived flag `has_earnings8k` built from the stale `visible_at` | flag not recomputed |
LLM scores and item hashes are unaffected in all four.
