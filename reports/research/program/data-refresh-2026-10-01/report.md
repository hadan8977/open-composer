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
