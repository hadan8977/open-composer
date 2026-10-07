# Addendum 1 to hypotheses.md (T-20261006-18, 2026-10-06T23:40:39Z)

Written at 2026-10-06T23:40:39Z, after the preregistration was frozen and validated (2026-10-06T23:30:51Z, hypotheses.md
unchanged) and **before any backtest, IC or Sharpe of this batch exists**: the only computation done so far is the
parse of extra XBRL concepts from the local companyfacts.zip (no returns involved). Source: the coordinator's
"Additional instruction 1" (2026-10-06 23:32 UTC) in `reports/research/control/briefs/T-20261006-18.md`.

1. **Data correctness (not a rule change)**: for the same fiscal period the XBRL value is taken from the *earliest*
   filing only, never from a later report that restates it. The frozen code already does this
   (`scripts/t18_extra_xbrl.py` keeps `select_first_filed` rows; `t18_factors.build_events` drops every row with
   `restated = True`); the addendum records it as a requirement and a check: the report lists, per concept, the share
   of rows dropped as restated.
2. **One more reported number (no rule change)**: for every factor (main spec) the intercept t-value of its monthly
   long-short return regressed on the market and five style factors (Fama-French five-factor monthly file
   `data/raw/factor_libraries/french/ff5_extract/F-F_Research_Data_5_Factors_2x3.csv`: Mkt-RF, SMB, HML, RMW, CMA;
   the file ends 2026-07). Reported for the recent window and the full sample, OLS with Newey-West (lag 2).
   It does not enter any decision rule of hypotheses.md section 5.
3. **Judgement**: tier labels follow evaluation standard v2.1 section 5 (P1) and section 5b where applicable; the
   "own paper sleeve" and "into the book" rules of hypotheses.md are reported next to the P1 outcome, as reference.
   A candidate is called P1 only if the scorecard conditions of section 5 (DSR >= 0.70, net placebo >= 0.90,
   robustness >= 3, no veto) are computed and met; conditions that this batch cannot compute are listed as such.
4. **Compute gate**: heavy commands run through `scripts/heavy_run.sh --mem 0.8G -- <cmd>` (quiet window 18:00-00:45
   UTC, one heavy job at a time, SIGTERM 17:55 UTC), so the stages are resumable (per-series parquet files).
5. Wording: where a result is labelled "not at depth" the report states the achieved power (minimum detectable Sharpe
   or Sharpe improvement) next to it.
