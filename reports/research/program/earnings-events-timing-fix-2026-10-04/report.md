# T-20261004-52 — earnings_events acceptance_utc timing fix (data pitfall #61)

Coordinator code R1004-T52. Executed 2026-10-04 (rebuild 08:38–10:02 UTC). Status: fixed and checked; downstream tables **not** rebuilt, awaiting lead decision (section 4).

## 1. What changed
- `scripts/build_earnings_events.py`
  - `acceptance_utc` now comes from the EDGAR filing-index "Accepted" field (US/Eastern wall-clock, converted once to UTC, DST via zoneinfo). Every row of this rebuild got `acceptance_source = edgar_index`.
  - Fallback when the index page fails: the submissions-API `acceptanceDateTime` read as true UTC (identical to undoing the double shift), `acceptance_source = formula`. The fallback was never used (index fetched for 16089 of 16089 filings, 0 HTTP errors).
  - New column `acceptance_source`. Old rows that a rebuild does not touch would be marked `legacy_double_shifted` (none remained).
  - Discipline: 1 serialized client, ≥0.25 s between requests (≤4/s), User-Agent `open-composer research hzc43021@gmail.com`, retry with linear backoff on 403/429/5xx, per-company checkpoint `data/raw/earnings_text/_cache/build_checkpoint.jsonl` (resume; removed after a complete run). A filing moved across a year boundary by the correction is removed from the old partition.
  - `undo_double_shift()` added for audits: inverts the old map exactly (DST decided by the raw wall-clock, which differs from DST at the true instant only in the hours around the two switches; the brief said "at the true instant" — the exact inverse is what reproduces the old bug).
- Tests: `tests/test_build_earnings_events.py` (35 pass): Accepted parsing, DST either side of 2025-03-09 and 2025-11-02, fallback, index-vs-API disagreement, crash+resume (finished company not re-requested), year-boundary move. Existing `to_utc_iso` tests were rewritten (its meaning changed: API value is UTC).
- Check script: `scripts/check_earnings_events_timing_fix.py` → `checks.json`.

## 2. Rebuild
- Backup (cp -a, sha256 verified): `data/live/backup-features-20261004/earnings_events/` (2024/2025/2026 parquet + `unresolved_tickers.json`).
- Run: `scripts/run_capped.sh --mem 1.2G`, log `logs/build_earnings_events_fix.log`. 1709 companies, 16089 filings, ~3.4 requests/s. `index_formula_mismatch = 0`: the API value equals the index time for all 16089 filings, which confirms the API value is true UTC.
- Side effect: `data/features/earnings_events/unresolved_tickers.json` was rewritten by the builder (2030 bytes vs 385 bytes in the backup; it lists tickers not in SEC's current ticker map). Not used for timing.

## 3. Acceptance (see `checks.json`)
- (a) old − new, per (accession, ticker) row: **15986 of 16041 = 99.66 %** equal the exact old-bug shift (10386 rows +4 h, 5600 rows +5 h). Gate ≥ 99.5 %: pass.
  - The other 55 rows (0.34 %) have old − new = 0 h: 11 filings each of SIRI, VRNS, TTWO, COCO, CIEN (2024-02 … 2026-09). Their old value was already the true UTC instant and equals the index time. Their origin (a different earlier writer) was not traced; the new value is index-sourced for all of them. These five tickers were the only ones the old build handled differently.
- (b) 20 random accessions (seed 20261004), separate fetch from the index page by a fresh client: **20 of 20** match.
- (c) Rows 16041 → 16089; **0 accessions removed**, 48 added (filings accepted after the old build or newly covered; list in `checks.json`, earliest 2024-02-07 PAG, latest 2026-10-02). 98 accessions appear twice (dual-class tickers, e.g. MCHP/MCHPP) — same 98 as in the old table, unchanged.

## 4. Downstream (grep of the repo; nothing rebuilt)
Counts below use all 16041 old rows with Item 2.02 and compare old vs new Eastern time: 268 rows (1.7 %) change side of the 16:00 ET cut, 125 change ET calendar date, 7318 (46 %) change membership of the (16:00 ET, 09:30 ET] overnight window.

| Reader | Uses | Change after the fix |
|---|---|---|
| `scripts/build_pm_earnings_events.py` (`eastern_from_double_shifted`, `match_announcements` mode "corrected") | undoes the double shift on the table | **Would now double-undo (4–5 h too early) on the fixed table.** Needs a code change (read `acceptance_utc` as true UTC) before it is rerun. Its existing output (T-20261004-51) was built from the old table and is correct as it stands; T-51's `edgar_accepted_cache.json` is unaffected. |
| `scripts/run_h20261004_pm_earnings_beat_odds.py` | reads the table built above, report text cites the defect | no rerun needed; its note about the defect is now resolved at the source. |
| `scripts/build_sue_8k_visible.py` → `data/features/sue_8k_visible/{year}.parquet` | `acceptance_utc` as true UTC, converted to ET, 16:00 ET cutoff | Script already assumed true UTC; its table was built from late timestamps. 268 filings (1.7 %) would get a different usable session; feeds the equity book / sleeves → **lead decision before rebuild**. |
| `scripts/run_t20260930_14_overnight_12m.py` | overnight window (16:00 ET, 09:30 ET] on `acceptance_utc` | 46 % of events change window membership; the T-14 overnight result was computed on shifted times. Lead decision on rerun. |
| `scripts/score_h20260928_17_filing_risk_labels.py` → `data/features/h20260928_17_filing_risk_labels_scores/items.parquet`; `scripts/build_h20260928_17_filing_risk_labels_feature.py` | `visible_at = acceptance_utc + latency`; trading-day attribution at 16:00 ET | LLM scores unaffected (item_hash = accession + prompt + text hash); stored `acceptance_utc`/`visible_at` and entry attribution are 4–5 h late. Recompute columns/feature only. |
| `scripts/score_h20260928_16_sentiment_accel.py` → `data/features/h20260928_16_sentiment_accel_scores/items.parquet` | 8-K source timestamp for acceleration windows | Task was cancelled; stored timestamps late by 4–5 h; scores unaffected. |
| `scripts/score_earnings_text.py` → `data/features/earnings_text_scores`; `scripts/eval_earnings_text.py` | copies `acceptance_utc`; eval uses it for entry (acceptance + 60 min) | Scores unaffected; stored column stale; `h20260922_01_earnings_text` evaluation entry times were 4–5 h late (re-evaluation only). |
| `scripts/build_h20260929_20_events.py` → `data/research/h20260929_20_news_nonews_drop_reversal` | `visible_at = acceptance_utc` (8-K events) | event `visible_at` 4–5 h late; the 8-K/news overlap classification may change. Rerun after lead decision. |
| `scripts/collect_sec_ma_target_announcements.py` | own `<ACCEPTANCE-DATETIME>` header, only cites the builder | not affected. |
| `scripts/build_h20260928_15_claude_factors.py`, `scripts/run_t20260928_10_ml_killtest.py` | mention the table in text only | not affected. |

## 5. Not done / caveats
- Downstream tables and results were not rebuilt (brief). Anything already computed from the old `acceptance_utc` should be treated as built on 4–5 h late timestamps until rebuilt; the direction of the error is "too late", so past results are not outcome leaks but entries/classification were shifted.
- Root cause of the 55 already-correct legacy rows is unknown.
- Commit covers code, tests, check script and this report; data stays uncommitted.
