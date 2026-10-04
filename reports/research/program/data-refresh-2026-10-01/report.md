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

## T-20261001-22 组合线 live 目录 (R1004-T22, D = 2026-10-02; 待主审)

Status: **partial**. The live root is built to D and fresh; the parity gates of step 4 fail (details and attribution below, `live-parity.json`). No build logic was changed to make them pass.

### Code (two small edits, one fix, new files)
- `panel.py` `DEFAULT_DIR` and `build_equity_book_panel.py` `OUT`: `OC_EQUITY_BOOK_DIR` override (empty counts as unset). Test `tests/test_equity_book_live_root.py` (3 subprocess cases): unset, `DEFAULT_DIR`, `risk.RISK_DIR`, `signals.SIGNALS_DIR`, `build_book_v1_alpha.OUT_DIR`, `build_equity_book_panel.OUT` equal the snapshot paths; set, all fall under the given directory.
- `risk.py` `RiskModel.resolve()`: when the year has no saved date <= d (or no file), fall back to the previous year's last saved date if that file exists and `exact=False`. Tests in `tests/test_equity_book_risk.py` (two-year synthetic dir, `exact=True` still raises, no previous-year file still `KeyError`).
- **Module hashes changed** (v1 A1 binding is history, v1.1 must bind the new ones): panel.py sha256 `a023e2b1b5dc4ba2…` (was `4d5242ed635ff14b…`), risk.py `d92bf0320193189f…` (was `586c2620be11e6ac…`), build_equity_book_panel.py `613b54e976bf0377…`.
- `scripts/check_feature_invariance.py` unchanged: it already has a relative `--tol`, so no `--rtol` was added.
- New: `scripts/refresh_equity_book_live.py` (driver), `scripts/check_live_parity.py` (step 4), `tests/test_refresh_equity_book_live.py` (12 tests).
- Tests: `tests/test_equity_book_*.py tests/test_book_v1_stage2.py tests/test_eval_book_v1_stage2.py tests/test_book_postmortem.py tests/test_refresh_equity_book_live.py tests/test_check_feature_invariance.py`: all pass except `test_equity_book_backtest.py::test_stage0_ls_raw_mom_12_1_p1000_parity` (max abs diff 3.97e-3, mean 4.1e-4, 106 months). That test rebuilds the stage-0 monthly returns from the current `data/features/daily_broad`, which T-02 swapped on 10-04; it does not touch `resolve`, `DEFAULT_DIR` or the env override. Not verified by a counterfactual run; needs a lead decision (freeze the old file for that test or re-baseline stage 0).

### Risk-model repair on real data
- `resolve("2026-01-02")` returns **2026-01-02 itself**, not a 2025 date: the snapshot's 2026 risk file already has 2026-01-02 as its first saved date, so the brief's expected value does not apply. The fallback is shown by `resolve("2025-01-02")` = 2024-12-31 and `resolve("2024-01-02")` = 2023-12-29.
- Trading days before the first saved date of the year (all raised `no_risk_model` before): 2018: 3, 2019: 2, 2020: 1, 2021: 4, 2022: 4, 2023: 3, 2024: 3, 2025: 1, 2026: 0, total 21 for 2018-2026. After the fix: 0 failures for 2018-2026. 2017 (128 days before 2017-07-07) stays unresolvable, there is no 2016 file.

### Live root build (all with `OC_EQUITY_BOOK_DIR=data/live/equity_book`, `run_capped.sh --mem 1.8G`, logs `logs/t22_*.log`)
- Copied with `cp` (no symlinks): small files, 2025 partitions of panel/prices/signals, and (for the 2017 risk start) panel 2016-2024.
- hygiene 41 s; panel 2026 102 s (530,334 rows to 2026-10-02); prices 33 s (all years, the stage has no `--years`); etf 4.5 s; **risk 2025 start 51 s, rerun 2017 start 3 min 32 s**; signals 2026 about 2 min; themes 30 s; formation_ic merged (snapshot <= 2024-12-31 plus live >= 2025-01-01; `formation_ic_live_only.parquet` kept, marker `formation_ic_merge.json`).
- **Order finding**: signals read `risk/residuals_<y>.parquet` for `resid_mom_12_1` (`build_equity_book_signals.py` `RISK_RES`). Built before the risk model they silently fall back to industry-demeaned returns (resid_mom rho 0.80 vs the snapshot). The first signals run was therefore redone after the risk model; the driver order is hygiene, panel, prices, etf, **risk, signals**, alpha.
- Risk start: with 2025 the 2026 spec_var rank parity was 0.14 of dates, with 2017 it is 0.84; the driver uses 2017-01-01 (3.5 min).
- Fast-alpha signals: no error, `a101_*`/`g191_*` coverage flags are 0 from 2026-09-18 (old alpha tables). `news_attention` and `cmp_opp_buy_60d` (insider) coverage is 0 on 2026-10-02: `news_attention` and `insider_broad` end 2026-10-01 (`_freshness.json` `upstream`). The 20 intraday columns are empty after 09-17 (M0 does not use them).

### Parity (step 4, `live-parity.json`; strict <= 2026-08-21, diagnostic 08-24..09-17)
| check | gate | result |
|---|---|---|
| panel returns (cc, oo; price-aware, 60 vendor-revision symbols excluded) | max_changed_share <= 0.001 | **0.00136**, keys fail |
| prices returns | same | **0.00104**, keys fail |
| signals (164 numeric columns) | rank_parity_share >= 0.99 | **0.934** (28 columns < 0.99), keys fail |
| risk exposures | same | **0.886** (spec_var 0.84, momentum 0.38, profitability 0.54, reversal 0.86, value 0.95), keys fail |
| themes 2026 | same | **0.929** (momentum 0.81, value 0.71, quality 0.85) |
| themes 2025 | same | 1.000, pass |
| formation_ic overlap (380 rows, M1 excluded) | abs diff <= 1e-6 | all joined, **max 0.0118**, fail |
| risk cov / factor_returns / residuals (diagnostic, rtol 1e-2) | none | changed share 0 / 0.00013 / 0.00058 (diag window 0 / 0.0012 / 0.0033) |

Attribution (`live-parity.json` `attribution`, strict zone):
- **Keys**: every only-live and only-snapshot key in panel and prices is explained by the archive one-sided keys (T-02 `archive_only_*_keys.txt`, my reading of "T-01 date_set") or by 79 symbols whose price-hygiene cutoff changed on the restated archive (panel: 59 only-live all hygiene; 250 only-snapshot = 160 archive + 90 hygiene; prices: 4313 = 155 + 4158; 825 = 160 + 665); 0 unexplained. The strict `keys_ok` is false only because the T-02 allow files do not list the hygiene symbols.
- **Price re-basing**: 21.1% of panel rows have a close that moved by more than 1e-3, all in restated symbols (0 outside). `mom_12_1`, `on252` changes are 100% in restated symbols (22% and 25% of rows). Rank parity on a date falls below 0.999 as soon as that many names move.
- **Panel fallback mcap** (new, not in the lead's exception list): `mcap_source` adv_fallback / adv_fallback_outlier use the median of close*shares/dollar_adv_21 over the whole year (`stage_panel`). Rows earlier in the year move when the year grows: 62% of adv_fallback rows of price-unchanged, non-restated symbols changed mcap by > 1e-3 (SEC-sourced rows: 0.01%). That is about 20% of rows and carries into ep/bm/sp/cfp (ep: 12,540 changed rows in 138 non-restated symbols with unchanged price). This is also a within-year look-ahead of the panel build and means a live append can never reproduce earlier mcap for those rows; candidate data pitfall.
- **SEC daily changes <= 08-21: 5 symbols**, 755 rows: SHPH sue_eps 67 rows (pitfall #62, filed 09-24), EL roe 320 / accruals 139 / net_income, APLD (same columns), CALM revenue 26, GURE eps_diluted 4. For all five, the new `facts.parquet` has facts filed after 09-17 (SHPH 13 from 09-24, APLD 2 from 09-25, GURE 30 from 09-29, EL 5 from 09-30, CALM 10 from 09-30) and the old one has 0, so the mechanism is the same late-filing/amendment entry as #62. Only SHPH sue_eps is inside the lead's literal exception; EL, APLD, CALM, GURE changes in roe/accruals/net_income/revenue/eps_diluted are not sue columns and are listed here for the lead.
- `resid_mom_12_1` changes in 99% of rows at 1e-6 (rank parity 0.875): residuals come from a risk regression over the whole cross-section, so any restated name moves all of them. `rev_21_ind` (91.6%) changes through the industry mean. Neither is a build fault.
- Reading for the lead: the `rank_min 0.999` per-date gate is dominated by a few moved names (roe: 2 symbols moved, per-date rho 0.9975), so ranks fail even where almost all values are identical; the failures are all attributable (restated prices, hygiene cutoffs, fallback mcap, five late SEC filers), none to the live builds. Unattributed under the stated exceptions: the EL/APLD/CALM/GURE SEC rows and the fallback-mcap drift. The decision whether the live root is acceptable for v1.2 stage 1 is the lead's.

### Research snapshot guard
- sha256 of the 2637 files under `data/research/equity_book/` (without `duck_tmp/`): before `research-snapshot-sha256-before.json` (2026-10-04T08:39Z), after `research-snapshot-sha256-after.json` (09:20Z): **identical**. Nothing under the snapshot was written; the live root has no symlinks.

### Freshness and driver
- `data/live/equity_book/_freshness.json` (written by `--check`, 09:19Z): panel, prices, etf, signals, risk, alpha last date 2026-10-02 = SIP last date, `fresh: true`. Table level (`upstream`): `insider_broad` and `news_attention` end 2026-10-01, `sec_fundamentals_facts` 2026-10-01, the rest 2026-10-02 (universe month_end 09-30). `alpha101/191` are not refreshed (disabled in the driver, reason in the table spec).
- `scripts/refresh_equity_book_live.py`: default run, `--dry-run` (prints the 51-step plan; verified for today and for 2027-01-04), `--check`; exit 2 when the SIP archive has not reached the last closed session (nothing done), 3 upstream comparison failed (backup restored), 4 command failed, 6 lock held; lock `data/live/.refresh.lock`; log `logs/refresh_equity_book_live.log`; split-type restatements (max_rel_diff >= 0.2, symbol in the panel universe) also rebuild earlier `daily_broad` years; price tables use the two-zone rule (return-like columns before last date minus 3 sessions). It does not duplicate `scripts/run_book_v12_daily.py` (targets/plan/submit/reconcile); that script's `--targets` needs a fresh live root, which this driver produces. No conflict found.
- **Never run end to end**: the upstream path (network fetches, ~1 h of builds) was only exercised by unit tests with a fake runner (restore on failed check, swap on pass); the live-layer commands are the ones run by hand above. First scheduled run should be watched.
- Suggested cron (not installed; UTC, after the 22:00 SIP update and the 22:30 freshness check): `45 22 * * 1-5 cd /root/codex-test/open-composer && uv run python scripts/refresh_equity_book_live.py >> logs/refresh_equity_book_live.cron.log 2>&1`. Run `run_book_v12_daily.py --targets` after it finishes (the live layer alone takes about 9.5 minutes measured above; the upstream part is unmeasured, so the offset is the lead's to set).

### Not done / open
- Parity gates fail (above); status partial. Lead decides acceptance, fallback-mcap handling and the EL/APLD/CALM/GURE rows.
- `test_stage0_ls_raw_mom_12_1_p1000_parity` fails on the swapped data (above).
- Driver upstream path unrun live; `alpha101/191` and the 20 intraday columns stay old/empty; `news_attention` and `insider_broad` reach only 10-01.
- Data under `data/live/` is not committed.

### T-22 续作 R1004-T22 (2026-10-04 09:44–16:13 UTC): first real runs of the driver, fixes, green run (待主审)

Result: the driver ran end to end with exit 0 (15:00:22–16:12:17, 72 min, uncontended apart from short waits) at D = 2026-10-02; `_freshness.json` (`--check` 16:13Z) `fresh: true`, every live stage 2026-10-02, `insider_broad` and `news_attention` 2026-10-02. Research snapshot sha256 (2637 files) before = after (rechecked 16:15Z). Log `logs/refresh_equity_book_live.log`.

**Incident, my driver's fault (09:34–09:36Z, lead's first real run)**: the staging directory held symlinks to the prior-year partitions; `build_feature_universe.py` wrote through them and rewrote `data/features/universe/2016..2025.parquet` (narrow universe; the portfolio layer reads `universe_broad`). No byte-identical original exists locally (10-02 backup holds 2026 only; `_t02_stage/universe` is a T-02 rebuild). Restored 09:5xZ from the Drive copy of the T-21 rebuild (`archive/open-composer/data/features/_t21_tmp/universe/<y>.parquet`, 10-01 22:53Z). T-21's invariance check had that rebuild equal to the then-current files on keys for every year with changed-row share 0 for 2018-2020 and 2022-2025, 0.00035 (2016), 0.00028 (2017), 0.00054 (2021); the 2026 file was not touched (T-02 composed, 10-02 13:39Z). The overwritten versions are in `data/live/backup-refresh/overwritten-universe-20261004/` (10 files). Staging now copies prior years, never links.

**Design defects found by the real runs, all fixed (commits 65f1c36 base, 07e010c, final)**
1. `universe`, `universe_broad`: rebuilding the year and comparing it with the file is the wrong design (T-02 composes them: old months frozen, closed month ends appended). Now append-only by `month_end`; with no closed month end after the stored last one the table is skipped ("no new month end after 2026-09-30"); with one, only the new month is composed onto the old rows and the old rows are checked unchanged.
2. Restatement cursor: no cursor means no automatic rebuild; `--init-cursor` (used once, 7326 lines) sets it; only new records are processed afterwards.
3. Staging directory cleaned after a failed check and after a swap.
4. **Membership-aware gate**: universe-keyed tables take membership from the newest `universe_broad` month end <= row date, so a month end appended since the previous run re-members the rows from that date on. When the state file (`universe_month_end`) is behind the universe, the gate stops the day before that month end (`gate stops at 2026-09-29`). What it avoided, run 2 of `insider_broad` (check JSON of that run): value changes 0 over 745,056 joined rows (`max_changed_share` 0.0); key differences only-new 272 / only-old 372 rows, all dated 09-30 or 10-01 (the old table had been built with the 08-31 membership, 3947 symbols on those dates, the 09-30 universe has 3897). With the gate stopped at 09-29 the table passed. In the green run the state was current, no gate stop was needed, and all eight checks passed on the full range (`max_changed_share` 0.0, keys equal).
5. New-entrant symbols: the builders backfill the history of symbols that entered the universe at a month end (short_volume_broad: 8,742 only-new rows = 47 symbols, `max_changed_share` 0.0). Symbols absent from the old table are allowed as new keys (`allow_new_<table>.txt`), logged per table; nothing else about the gate changed.
6. `news_attention` needs the `articles` stage before `features` (new `pre_build`); `--tables` selects tables; the driver waits (up to 3 h) while another process holds more than 600 MB RSS (two builds at once swapped for over an hour; no step starts while another agent's job is large).
7. Tests: `tests/test_refresh_equity_book_live.py` 21 pass (month ends, monthly append keeps old rows, skip case, cursor, membership cut, new entrants, heavy-process wait, staging cleanup).

**Timings of the green run** (uncontended): universe x2 skipped; daily 1.6 min; daily_broad 5.6; SEC facts fetch+build 10.9; SEC daily 18.4; nsi 4.5; insider_broad 11.1 (fetch included); short_volume_broad 2.7; short_interest 1.2; news_attention 3.3 (fetch of 10,804 articles included); live layer 12.5 (hygiene 1.1, panel 3.5, prices 1.1, etf 0.2, risk 3.8, signals 1.9, alpha 0.5); total 72 min. Under contention the same insider step took 26 min (run 1) and over an hour without finishing (killed, rerun). Cron suggestion unchanged; budget about 75 min before the targets step, longer if other jobs hold memory.

Run history: run 1 (09:44) swapped daily, daily_broad, SEC facts, SEC daily, nsi and failed on insider (gate design, item 4); runs 2-3 (11:07, 12:20) were killed by me while swapping against another agent's job; run 4 (12:47) swapped insider and failed on short_volume_broad (item 5); run 5 swapped short_volume, short_interest, news and the live layer; run 6 (15:00) is the green full run above.

Unchanged and open: `alpha101/191` still old (fast-alpha coverage 0 after 09-17), 20 intraday columns empty, parity of the live layer vs the snapshot was not re-run after the refresh (the lead's book-level parity is the acceptance), the ~72 min refresh plus the 22:45 cron start leaves the targets step after midnight UTC unless it starts earlier.
