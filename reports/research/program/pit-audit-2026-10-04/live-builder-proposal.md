# Live-builder proposal (draft, no code changed; the lead decides)

## #62 SEC daily stage (`scripts/build_sec_xbrl_fundamentals.py`, `compute_cik_table`)
- Change: derive `sue_eps`, `sue_rev`, `asset_growth` with the as-of rule (`pit_cik_table` in `scripts/pit_audit_20261004.py`): call `sue_series` /
  `asset_growth_events` on the ladder subset with `usable_session <= s` at each of the issuer's own sessions `s`; an entry that becomes computable at `s` takes effect at `s`.
  The other columns need no change (event-driven already; event set identical in the audit).
- Effect on live values at D: none for values already visible at D; history stops being rewritten when a late 10-Q or a comparative arrives.
  Snapshot effect measured: 30-1211 sue_eps rows/year (1-13 symbols/year, <=0.12% of rows) differ between final and as-of ladder.
- Cost: about 0.5 s/issuer on a loaded box (about 40 min for 5,229 issuers); a live run only needs issuers with new facts since the last run.

## #63 panel fallback mcap (`scripts/build_equity_book_panel.py`, `stage_panel`)
- Change: replace the per-year `ratio` temp table by a per-session trailing median of `close*shares/dollar_adv_21` per adv-rank bucket
  (252 sessions up to t-1, expanding when shorter; bucket = round-half-even(adv_rank/250), as now). See `trailing_bucket_median`, `fallback_mcap` in the audit script.
- Effect on live values: the live year-to-date median already uses only past rows, so D's value is point-in-time, but it moves as the year grows
  (62% of fallback rows moved, T-22). A trailing median fixes the value at D forever; level shifts versus the year rule are what stage 1 measures (see report.md).
- Side effects to check: `ep`, `bm`, `sp`, `cfp`, `nonplan_buy_mcap_60d`, the Vasicek beta shrinkage, and the risk model's size exposure all read `mcap`; the risk model and the optimizer were not rebuilt in this audit.
