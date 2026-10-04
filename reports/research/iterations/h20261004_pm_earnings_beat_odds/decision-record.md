# Decision Record: h20261004_pm_earnings_beat_odds

Verdict: `pipeline_suspect` (mechanical, pending lead review). The frozen positive control failed its gate (weekly-IC t 2.80 < 3.0), so H-A (A1, A3, placebos, sub-periods) was not computed. No statement about whether Polymarket earnings odds predict announcement returns follows from this record. Numbers come from `results.json`, `report.md`, `results-literal-timing.json` and `timing-deviation-note.md`.

## P1

- Path: earnings_beat_odds_cross_section (A1 primary, A3 secondary and decision-ineligible)
- Decision: stop before H-A as the design requires; the lead decides whether to re-contract (more events, or a different control statistic) or park.
- Reason:
  - First run, literal timing (8-K `acceptance_utc` read as Eastern wall-clock): control weekly-IC t 2.34, pooled t 3.58, `pipeline_suspect`. Calibration exposed a leak: 98.3% of the "after close" events had P above 0.97 or below 0.03 at the 15:00 ET cut. The EDGAR index "Accepted" time for 11 of 11 sampled filings equals the table value minus 8 h (EDT) or 10 h (EST): the table was double-shifted.
  - Second run, EDGAR-verified timing (all 1055 matched accessions fetched; the double-shift formula agrees with EDGAR in 1055 of 1055): 620 primary events, 30 week groups, 27 with enough variation. Control IC 0.165, weekly-IC t 2.80, pooled week-clustered t 4.59. Mean excess return after a miss -2.17%, after a beat +0.75%. By timing: pre-market IC 0.233 (t 3.02), after close 0.101 (t 1.31). Before 2026-03-01 IC 0.140 (t 1.67), from 2026-03-01 IC 0.201 (t 2.48).
  - Calibration on the corrected table is sensible: base rate 0.758, mean P 0.750, AUC 0.810, Brier 0.137 against 0.183 for the base rate, deciles monotone from 0.25 to 0.97.
  - The control is a pipeline check with only 27 weeks; its failure at t 2.80 is a power or threshold question, not clear evidence of a broken pipeline. The pooled t is 4.59.
- Caveats:
  - The timing correction is a deviation from the literal text of hypotheses.md, made before any H-A statistic and recorded in `timing-deviation-note.md`; the lead decides whether the corrected run counts.
  - The control gate uses the weekly-IC t (fixed in the script before the first run); the pooled t would have passed.
  - Contract data are thin (median volume about 6.3k USD), 628 of 1353 events pass the 5k filter; GAAP-basis contracts are kept (485 of 1353 events); the sector-adjusted secondary was not run (no sector ETF map in the repo); the end-time timing proxy for events without an 8-K was not built.
  - Overlay scoring: not run.
- Next iteration suggestion: lead to decide. Options: (a) accept the control on the pooled statistic and run H-A once; (b) wait for about 450 more events, as the inconclusive rule already plans, and re-run under a new contract. Nothing was registered in the direction registry because `pipeline_suspect` has no matching status.
- ML or AI-information round entry conditions: not met, no model involved.
