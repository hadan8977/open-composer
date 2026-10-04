# Report: h20261004_pm_earnings_beat_odds

Verdict (mechanical, pending lead review): **stop_refuted**. Primary events 620 (2025-09-30 to 2026-10-01), 30 week groups.
- Positive control (gate: pooled event-level t, week-clustered SE, >= 3): t 4.59 on 584 events; weekly-IC 0.165, t 2.80 over 27 weeks (reported only). Lead ruling 2026-10-04 (Opus, interactive session), made before any H-A statistic was seen: the positive-control t is the event-level pooled t with week-clustered SE; the weekly-IC t was the implementer's reading and is reported only. Corrected EDGAR timing is the frozen test.
- Leakage check (P >= 0.97 or <= 0.03 at the cut, share of events): after_close 5.4% (n=294); intraday 0.0% (n=3); pre_market 1.2% (n=323).
- Calibration: base rate 0.758, mean P 0.750, AUC 0.810, Brier P 0.1368 vs base-rate 0.1834.
- A1: mean weekly IC 0.0191, t 0.43, 30 weeks, shuffle percentile 64.2 (p95 0.0836); pooled IC 0.0126 (clustered t 0.31).
- A1 tercile spread: gross -57.0 bp, net -97.4 bp (stress -137.4 bp) per pair.
- A3: IC 0.0545, t 1.25, 27 weeks; raw one-sided p 0.112, Holm 0.223.
- MDE (IC): 0.1101; spread 226.8 bp.
- before_2026-03-01: IC -0.0140, t -0.22, 18 weeks, 421 events.
- from_2026-03-01: IC 0.0689, t 1.16, 12 weeks, 199 events.
- Placebos: P7 signal IC 0.0227 (t 0.41); R+1 return IC 0.0086 (t 0.17).
- Continue rule: IC>0 and t>=2 False; net spread>0 False; above shuffle p95 False; stop rule triggered True.
- Robustness (reference only, not in the verdict), excluding 16 extreme-P events in ['after_close']: A1 IC 0.0198, t 0.42, 30 weeks, shuffle percentile 62.9, net spread -128.4 bp.
- Overlay scoring: not_run_continue_rule_not_passed.

## Data-layer defect: `data/features/earnings_events/` acceptance_utc

- Finding (2026-10-04): `acceptance_utc` is later than the true UTC acceptance instant by 4 h in daylight time and 5 h in standard time. The source value was already UTC and was converted once more as if it were Eastern wall-clock. Against EDGAR filing-index Accepted times: 11 of 11 hand-checked filings, and 1055 of 1055 matched accessions agree with the formula below (`data/research/prediction_markets/polymarket_earnings/edgar_accepted_cache.json`).
- Affected: the `acceptance_utc` column of `earnings_events/{2024,2025,2026}.parquet` and every consumer that reads it as a true UTC instant (`scripts/build_sue_8k_visible.py` documents it that way and converts it to Eastern again). Dates near midnight and after-close classification shift; the `text_path`, `ex99_url` and accession fields are unaffected.
- Cause: `scripts/build_earnings_events.py` treats the submissions API `acceptanceDateTime` as Eastern wall-clock (its `_EASTERN` comment). For these filings the API value is true UTC.
- Suggested fix: in the builder, parse `acceptanceDateTime` as UTC; for the existing tables recover with `pd.to_datetime(x, utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.tz_localize('UTC')` (see `eastern_from_double_shifted` in `scripts/build_pm_earnings_events.py`). Check rows from other sources in the same table (10-K note: mixed conventions) before rewriting, and re-run the consumers that depend on the timestamp (`build_sue_8k_visible.py`, the earnings-text forward test).
- Not changed here: neither the table nor its builder was edited; the lead schedules the repair.
