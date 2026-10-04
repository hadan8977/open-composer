# T-20261001-21 data refresh to D = 2026-10-01: report

Status: partial. D = 2026-10-01, the largest session in data/sip/daily/2026 (12,564 rows against about 13,230 on earlier days: zero-volume placeholder rows are missing for the newest day, volume totals are in line). Numbers below come from `invariance.json` and `freshness.json` in this directory. Research snapshot `data/research/equity_book/`: 2,511 files hashed before and after, identical (`snapshot_sha_before.txt`, `snapshot_sha_after.txt`).

Rule applied (from the brief): a table passes when `keys_equal` and `max_changed_share <= 0.001` on rows up to the old last date; otherwise it is `restated`, nothing is swapped in, and tables that read it are not rebuilt. All builds wrote to `data/features/_t21_tmp/` first; only passing 2026 partitions were copied in. Backups with sha256: `data/live/backup-20261001/`, `backup_sha256.json`, `sha_after.json`.

| table | refreshed to | invariance | time |
|---|---|---|---|
| universe_narrow (aux, read by news and short_interest) | month_end 2026-09-30 | pass (2026: max 0.0, 1 new month, coverage 1.006) | 22 s |
| universe_broad | stays 2026-08-31 | restated: 2 new keys (FGC, Jan and Feb 2026), adv_rank shifted for 1.1% of 2026 rows; close and dollar_adv unchanged | 65 s |
| daily_narrow (aux) | stays 2026-09-16 | restated: max 1.70%; rows up to 09-09 identical, 09-14..09-16 changed | 30 s |
| daily_broad | stays 2026-09-17 | restated: max 1.68%; rows up to 09-10 identical, 09-15..09-17 changed | 90 s |
| sec_fundamentals facts | stays (restored, sha equal) | restated: no value changed, 17 of 2.14M old keys disappeared from the SEC bulk file | 416 s |
| sec_fundamentals_daily | stays 2026-09-17 | skipped (needs daily_broad) | |
| nsi | stays 2026-09-17 | skipped (needs daily_broad, sec daily) | |
| insider_broad | 2026-10-01 | pass (max 0.0, 11 new dates, coverage 0.9996) | 160 s |
| short_volume_broad | 2026-10-02 (visible-date row for the 10-01 file) | pass (max 0.0, 11 new dates, coverage 1.0) | 24 s |
| short_interest | stays 2026-09-16 | skipped (needs narrow daily); raw refreshed to settlement 2026-09-15 | |
| news_attention | 2026-10-01 | pass (max 0.0, 16 new dates, coverage 1.006) | 140 s |
| alpha101_broad | stays 2026-09-17 | restated: max 4.1% (178 extra keys of one new symbol, 226 rows changed per date on all 178 dates) | 300 s (one run) |
| alpha191_broad | stays 2026-09-17 | restated: max 0.66%; rows up to 09-10 identical | same run |

Restored: sec_fundamentals/facts.parquet and data/raw/sec_xbrl/companyfacts.zip (sha256 equal to `sha256_before`). The other restated tables were never swapped, so the in-place files are untouched (sha equal). The new raw data (FINRA short volume and short interest, Form 4 tail files, Alpaca news packets) was kept.

## What the failures are (diagnosis, not a verdict)

1. Price tables (daily_*, alpha*): the last 3 sessions before the cut differ, consistent with the archive cron refreshing the trailing sessions on a new dividend-adjustment basis (inferred, not verified) (BBY 93.85 vs 94.83 on 09-14, SPY included, which moves beta, idio_vol and every `_rel` column for all symbols on those dates). Leaving out the last 5 sessions the changed share is 0.0 (`settled_max_changed_share`) for daily_narrow, daily_broad, alpha191 and facts. alpha101 stays at 3.5% because of the extra symbol (cross-sectional ranks).
2. Universe growth: building daily_narrow with the refreshed universe adds 2 symbols to the union and changes 98.7% of `*_rel` cells, because the cross-section changed. A frozen-union rebuild (`data/features/_t21_tmp/universe_frozen`, the universe files that produced the old table) is the one in the daily_narrow row above.
3. FGC and the alpha extra symbol are names whose history entered the archive after 09-17 (renames or new listings backfilled), which gives extra keys for old dates.

## Decision needed from the lead (not made here)

Either accept an append-only policy (keep rows <= old last date, append only rows after it, with the rebuilt rows as candidates in `data/features/_t21_tmp/`: `daily_broad/2026.parquet`, `daily/2026.parquet`, `alpha101_broad`, `alpha191_broad`, `universe_broad/2026.parquet`), or a gate that ignores the last 3 sessions. The frozen gate cannot pass for any price-derived table while the archive cron keeps refreshing the trailing window. Until then sec_fundamentals_daily, nsi and short_interest cannot be extended past 09-17/09-16 without building on unswapped inputs.

## Other notes

- The Form 4 tail fetch keeps the earlier restriction to issuers of the narrow top-1000 universe; the 2026q2 quarterly dataset was not downloaded (it would add filings for April to June and change old rows).
- `data/sip-delisted/by_year` is static (last refreshed 2026-09-18); delistings after that are not in the broad tables. New listings without asset metadata (no ETF/fund flag after the cached 2026-09-18 snapshot) were kept by the builder; not counted separately.
- First insider build at `--swap 1G` was OOM-killed at 1.8 GB; rerun with `--swap 3G` (160 s).
- `scripts/_t21_inv_driver.py` merges per-year comparisons into `invariance.json`; `scripts/check_feature_invariance.py` is the checker (tests in `tests/test_check_feature_invariance.py`, 8 passing).

## T-20261002-01 archive repair (status partial, archive restored; pending lead review)

- Code: `scripts/update_sip_archive.py` (detect_restated_symbols, rewrite_full_history, process_restatements with `--rewrite-budget-min` 25 and `_restatements_pending.jsonl`, repair_full_window / `--repair-full-window`, minute detect-only), `scripts/check_sip_seams.py`, `scripts/verify_sip_repair.py`; 29 tests in `tests/test_update_sip_archive.py` pass, ruff clean. Order differs from the brief only in that the tail window is merged first and the full-history rewrite follows (same result, newest bar is always in).
- Run: backup `data/live/backup-sip-daily-20261002` (3741 files, sha256 in `sip-daily-backup-sha256.json`); repair run 29 min, 949 API calls, 6946 symbols found restated by the whole-year compare (+7 in the following update), 49906 symbol-years rewritten, 27107 rows without a shard, 0 empty refetches.
- Seams (`seams-before.json`, `seams-after.json`): 2026-09 22 -> 6 (Jan-Aug max 9); APH 08-26->08-27 ratio 0.5001 -> 1.0002; VRME, KUST, ZCSH, UNX, TANH no longer listed.
- V1 failed as specified (11,513,316 violations at 2.5e-4/price): vendor prices are 2-decimal, so old and new bases differ by rounding (AAA 22.63 vs 22.55). With a 0.02/price allowance on two shard slices (about 2,500 symbols) 188 violations remain (vendor history changes, ticker reuse such as NIVF). V2 strict 1e-6 failed for the same reason (7,779 symbol-fields).
- V4 failed as specified: 116 of 200 unrestated symbols differ; the 20 inspected differ only in the last row (2026-10-01) volume and trade_count, which is the normal tail correction.
- Per the brief the archive was restored from the backup (sha256 verified, 0 mismatches) and the repaired tree kept in `data/live/failed-sip-daily-20261002`; `_restatements.jsonl` is there too.
- Sleeve shifts (63d / 252d, pp): see `archive-repair.json` `sleeve_return_shift`; for example SHY +0.60 / +0.59, QQQ +0.11 / +0.13, SPY +0.25 / +0.29, GLD and SMH 0.
- Nightly cost: 0.21 s per symbol rewritten, plus about 160 s fixed shard-map build; estimate 0.9 min on an average night, 4.1 min for the peak September week (1,175 symbols), below the 25 min budget. Minute archive restatements are only logged (known limit).
- Needs the lead: V1 tolerance (rounding) and V4 definition (exclude the last session), then a repeat of the repair (about 35 min) or acceptance of the current verdict.

## T-20261002-01 swap after precision verification (R1002-1253-T01; pending lead review)

- Precondition: `data/sip/daily` matched `sip-daily-backup-sha256.json` exactly (3741 files, 0 missing/extra/different), so the repair was not rerun.
- Verifier: `scripts/verify_sip_repair.py --tol-mode precision` (tests: `tests/test_verify_sip_repair.py`, 11 pass). Tolerance 1e-6 + sum 0.5*10^-d(p)/p over the four prices (d = 2/3/4 by price). Classes in order: date_set, bar_correction, factor_revision, unexplained. V4' compares rows before 2026-09-29 (last date 2026-10-01 minus 2 sessions) column by column.
- Run: 8 scan segments of 50 shards under `run_capped.sh --mem 1.8G` (log `logs/t20261002_01_verify_v2.log`), merged; 6952 restated symbols checked.
- V1': unexplained 0 rows / 0 symbols (limit 69); factor_revision 55 rows / 53 symbols (limit 695); bar_correction 6 rows / 6 symbols; date_set 1 row / 1 symbol. V2' unexplained 0 (4 factor_revision, 3 bar_correction at the 2025/2026 boundary). V4' identical before the window: true (200 symbols; window-only differences: volume 116 rows, trade_count 116 rows, others 0).
- `verify_v2_pass` true. Swapped at 2026-10-02T13:19:55Z: `data/sip/daily` is the repaired tree (3743 files, sha256 equal to `data/live/failed-sip-daily-20261002`); the pre-swap archive is `data/live/backup-sip-daily-preswap-20261002`.
- V3 after the swap (`seams-after-swap.json`): APH 08-27/08-26 close ratio 1.00025; 2026-09 seams 6 (Jan-Aug max 9); VRME, KUST, ZCSH, UNX, TANH not listed; 8 seams since 08-20, none a named symbol (warrants and low-priced names).
- Not rerun: the repair. The 22:00 cron runs the new update code on the repaired archive.

## T-20261002-02 价格类表重建 (R1004-0741-T02 continuation, D = 2026-10-02; pending lead review)

- Replaced to D: universe_broad and universe (month_end 09-30, 10-02 first swap), daily_broad and daily (second swap 10-04; coverage_ratio 1.0008 / 0.9971, 11 new dates). Strict zone passes only with the price-ratio-aware bound (max_changed_share 4.07e-5 / 0); the brief-literal 0.04/close bound gives 0.00122 / 0.00207 at ret_252 and fails. Same bound as the 10-02 swap; backups kept (`backup-features-20261002/daily*_to_d1002/`).
- Not replaced (partial): alpha101_broad, alpha191_broad. Kept-column rank_parity_share 0.751 / 0.906 (< 0.99); failures are alpha003/004/013/016 and gtja006/123/161. A control build with the old union's 300-symbol batches gives 0.789 / 0.969, so batch shift (47 new union symbols) is part of it, the price-basis repair the rest (T-21 pre-repair builder noise was 4.1% / 0.7%). Candidates: `data/features/_t02_stage/alpha{101,191}_broad` (new union) and `alpha{101,191}_ctrl`.
- The 160 unallowed only-new keys per table are 2 symbols: OIG (09-30 member, first 2026 bar 09-18, after the old 09-18 09:06 build) and MN (not a 2026 member, one archive bar on 10-02; the builder pads all window dates). MN fits neither accepted category, so it stays listed.
- SEC facts: kept (built in place 10-02). 3470 new keys: 2698 from the 13 new CIKs, 771 filed 09-23..10-01, 1 from an existing CIK filed <= 09-17 (0.029%, CIK 885462 eps_diluted 10-K 08-17); 2,203,471 shared rows, 0 changed. The 23 old-only keys (7 CIKs) are not SEC deletions: the raw zips agree, the builder's tag/derived-Q4 choice moved after new filings 09-23..09-30.
- SEC daily: rebuilt to 10-02, coverage 1.0044, pass. 67 changed rows of one symbol (SHPH, sue_eps) trace to a late 10-Q filed 09-24 entering the quarterly ladder; `sue_series` uses the final ladder, which is a point-in-time leak in the builder (needs the lead).
- NSI and short interest: not replaced, old files restored (sha256 equal). NSI keys differ for 22 symbols (21 restated; ESQ cause not found). Short interest: 38 unattributed rows, INHD only (adv_shares_63, up to 1.8%). The brief's `--start-year 2026` build drops pre-2026 carry-in records (visible 95.99% vs 99.80% with `--start-year 2018`); candidate is the 2018-start build, 2018-2025 partitions restored from backup. Candidates in `_t02_stage/nsi_new`, `short_interest_new`.
- Research snapshot sha256 before = after (2637 files). Data under `data/features/`, not committed. Details: `t02-checks.json`, `t02-swap.json`, `freshness.json`.

### T-20261002-02 lead rulings 2026-10-04 (applied)

- NSI and short interest swapped (before/after sha256 in `t02-swap.json`, entries `nsi_second_swap`, `short_interest_second_swap`), last date 2026-10-02. NSI: 22 key mismatches, 21 restated symbols, ESQ unattributed. Short interest: 2018-start build (visible record 99.80%); INHD 38 rows of adv_shares_63 (max 1.8%) unattributed. The script `pass` for both stays false; they are accepted by ruling.
- Strict-zone tolerance: the price-ratio-aware bound is confirmed; the literal 0.04/close bound is a record only.
- alpha101_broad and alpha191_broad stay old (candidates in `_t02_stage`). They feed only the ML fast signal, not the M0 composite; the fast-alpha columns are empty on the new dates, with no effect on M0.
- The 20 intraday columns are empty on the new dates; M0 does not use them; not fixed.
- SEC daily new version kept for live. The SHPH `sue_series` point-in-time leak is data pit #62, audited separately.
- Research snapshot sha256 before = after (2637 files), rechecked after the swaps.
