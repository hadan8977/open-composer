# T-20261004-54 PIT audit of the research snapshot (#62, #63): report (R1004-T54, 待主审)

Verdict: **immaterial for the v1.2 M0 evidence. The frozen gate (`gate.json`, commit ad834a4, set before any number) did not open; step 4 was not run.**

## Method (scripts/pit_audit_20261004.py, tests/test_pit_audit_20261004.py, 9 tests)
- Inputs: own copy of `facts.parquet` (09:39 UTC); snapshot read-only; all output in `data/research/pit_audit_20261004/` (not committed).
- #62: `sue_series` and `asset_growth_events` (production functions) called on the ladder subset `usable_session <= s` at each of an issuer's own sessions; an entry computable only at `s` takes effect at `s`.
  All other `compute_cik_table` columns are event-driven (event set identical, 186,411 events). 5,229 issuers, 2016-2026.
- #63: trailing median of `close*shares/dollar_adv_21` per adv-rank bucket over the previous 252 sessions (expanding if shorter), replacing the year median.
  Bucket = round-half-even(adv_rank/250), not floor (DuckDB float division; boundaries 126/375/626/875 verified on the snapshot). The replicated year rule reproduces the snapshot mcap on 100% of U3000 rows 2016-2025, 97.2% in 2026.
- Rebuilt with the production `signals` functions: bm, ep, sp, cfp, gp_at, roe, op_at, neg_accruals, neg_asset_growth, sue_eps, sue_rev, nonplan_buy_mcap_60d, neg_beta_252; then the nine themes and M0 (same `theme_scores`, `rank_normal`, `rank_ic`, target y of `build_book_v1_alpha`). U3000, snapshot vs PIT, 2,440 dates.

## Stage 1 numbers (`stage1.json`; windows from the v1.2 hypotheses: recent 2024-01-08..2026-09-15, 31 formation dates; stress 2017-10-02..2023-08-31, 71)
| | snapshot | PIT | change |
|---|---|---|---|
| M0 mean formation IC, recent | 0.01095 | 0.01092 | -0.00003 (0.3% rel; gate 0.003 / 10%) |
| M0 mean formation IC, stress | 0.01544 | 0.01545 | +0.00001 |
| largest theme change (value, recent) | 0.01537 | 0.01498 | -0.00039 (gate 0.005) |
| other themes | | | all within 0.00011 |
- M0 composite per-date Spearman, PIT vs snapshot: median 0.9998, p5 0.9990, min 0.9744 (gate: p5 < 0.98). Value theme: median 0.997, p5 0.9885, min 0.971.
- #62 (sec_final_vs_pit_counts.json): final vs as-of ladder differ in 30-1,211 `sue_eps` rows per year, 1-13 symbols per year (<= 0.12% of rows); asset_growth 25-814 rows/year. In the snapshot signals, sue_eps/sue_rev change on <= 0.1% of rows (max 7 symbols/year), per-date rank corr of the earnings theme p5 0.9977.
  The "ladder-derived non-sue columns" seen in T-22 (EL, APLD, CALM, GURE) are not look-ahead of this ladder: gp_at, op_at, roe, neg_accruals change on <= 0.1% of rows, and my as-of rebuild leaves them equal to the final-ladder values (they are event-driven).
- #63: the trailing rule changes mcap on 16-43% of U3000 rows per year (the fallback rows; fallback share 43% in 2017 falling to 16% in 2026), the source label on <= 0.6%.
  Signals: ep/bm/sp/cfp change on 6-12% of rows, nonplan_buy_mcap 8-22%, neg_beta_252 on ~99% (Vasicek shrink uses mcap, tiny moves). Per-date rank corr of the z scores: ep p5 0.991, bm 0.988, sp 0.986, cfp 0.990.
- The snapshot-to-PIT comparison includes both fixes and the drift of the refreshed facts/shares vs the snapshot build; I did not split them (fin/sec variants were built for 2017-2018 only and discarded).

## Caveats
- Not re-derived: `select_first_filed`, `apply_concept_fallback`, `derive_q4` are baked into `facts.parquet`; only the ladder consumers were redone. Derived-Q4 values that use a later-filed Q1-Q3 are a possible residual leak (rare).
- The risk model (size exposure uses mcap), the residual-momentum signals and the optimizer were not rebuilt; y (target) uses the snapshot risk model for both sides.
- `validate-sec` (brute-force prefix check of the non-override columns) was not run; unit tests cover the ladder and NaN logic. Step 4 (account layer) not run because the gate stayed closed.
- A first PIT build forward-filled over genuine NaNs (accruals); found from the counts, fixed in code (test) and data, and the signals/IC were rebuilt after the fix.

## Live-builder proposal (no code changed; details in live-builder-proposal.md)
- #63: use the trailing 252-session bucket median in `build_equity_book_panel.py`: live D values are already point-in-time but drift as the year grows; trailing makes them stable and history reproducible. Cost: low; effect on M0 is immaterial per this audit.
- #62: build SEC ladder events as of the filing date (`pit_cik_table`): effect on live values none at D; only stops history rewriting (<= 0.12% of rows). Recommend doing it only when the SEC builder is next touched.
