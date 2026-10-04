# T-20261004-54 breakpoint (R1004-T54), 2026-10-04 ~14:15 UTC

Lead instruction 14:10 UTC: let the running signals step finish; after it, start nothing above 500 MB; wait until the lead
messages or 16:30 UTC with no other python above 500 MB. Budget of 4 h (09:36-13:36) already exceeded because the box was swapping.

## Done (data under `data/research/pit_audit_20261004/`, not committed)
- `facts.parquet` copy (taken 09:39). Gate frozen in `gate.json` (commit ad834a4) before any number.
- `sec` stage (#62): `sec_daily_final/` (production rules on current facts) and `sec_daily_pit/` (sue_eps, sue_rev, asset_growth as of the filing date;
  all other columns = final, because compute_cik_table's other streams are event-driven and the event set is identical, 186,411 events in both).
  A first version of `sec_daily_pit` overwrote genuine NaNs by ffill (accruals); fixed in code (test added) and the data re-joined from `sec_daily_final`.
- `sec_final_vs_pit_counts.json`: final vs as-of rows changed per year: sue_eps 30-1211 rows/year, 1-13 symbols/year (of ~0.7-1.2 M rows); asset_growth 25-814 rows/year.
  So #62 is tiny on the snapshot's SEC columns.
- `panel` stage (#63): `panel_mcap/<year>.parquet` (mcap_snap, mcap_year = snapshot rule replicated, mcap_trail = trailing 252-session bucket median) and
  `panel_stage_meta.json`. The year rule reproduces the snapshot mcap on 100% of U3000 rows 2016-2025 and 97.2% in 2026 (shares drift after the refresh).
  Bucket = round-half-even(adv_rank/250) (DuckDB float division + cast), not floor; checked on the snapshot.
  Trailing rule changes mcap on 16-43% of U3000 rows per year (= the fallback rows), source label on <=0.6%.
- `signals --variants pit` (themes for the 13 affected signals + 9 themes + M0 from PIT inputs): running at 14:10; log `logs/t54_signals.log`.

## To do after the wait (each one heavy step at a time, `scripts/run_capped.sh --mem 1.8G -- .venv/bin/python scripts/pit_audit_20261004.py <stage>`)
1. `ic` (formation IC snapshot vs pit, U3000; needs RiskModel + PricePanel, ~1 GB)
2. `corr` (per-date Spearman, changed-row counts)
3. `stage1` (writes `stage1.json`, gate verdict from gate.json rules)
4. only if the gate opens: step 4 (`book_v12_account.py --out-data` + test) -- not started.
5. `validate-sec` (brute-force prefix check of non-override columns on a sample) -- not run; unit tests cover the ladder logic.
6. report.md (<= 60 lines), live-builder proposal, commit, send report.
