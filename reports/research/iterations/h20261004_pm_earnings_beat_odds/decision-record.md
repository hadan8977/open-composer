# Decision Record: h20261004_pm_earnings_beat_odds

Verdict (mechanical, pending lead review): **stop_refuted**. The stop rule (mean weekly IC <= 0 or t < 1.0) fired: A1 mean weekly IC +0.019, t 0.43 over 30 weeks. H-A is refuted for effects of the size this sample can detect (minimum detectable mean weekly IC 0.110, spread 227 bp per pair). Numbers come from `results.json` (`continue_rule`, `H_A`, `placebos`, `sub_periods`, `minimum_detectable_effect`) and `report.md`.

## P1

- Path: earnings_beat_odds_cross_section (A1 primary, A3 secondary and decision-ineligible)
- Decision: stop; no candidate is scored or promoted, no overlay scoring, no shadow log. The direction is registered as refuted for effects of that size; weaker effects cannot be excluded.
- Rulings that shaped the test (both made by the lead on 2026-10-04 before any H-A statistic was seen):
  - Announcement time is the EDGAR filing-index "Accepted" time. The 8-K table's `acceptance_utc` is true UTC converted a second time (+4 h EDT, +5 h EST); the literal Eastern reading leaked the outcome into P (`timing-deviation-note.md`, `results-literal-timing.json`).
  - The positive-control t is the event-level pooled t with week-clustered SE: 4.59 on 584 events, which passes the gate of 3. The weekly-IC reading (t 2.80 over 27 weeks) is reported only.
- Reason:
  - Leakage check after the correction (P >= 0.97 or <= 0.03 at the cut): pre-market 1.2% (n=323), after close 5.4% (n=294), intraday 0.0% (n=3). After close is above the 5% flag, so a robustness line without the 16 extreme-P after-close events is reported (A1 IC +0.020, t 0.42, shuffle percentile 62.9, net spread -128 bp); it is not part of the verdict and says the same thing.
  - A1: 620 events, 30 weeks; mean weekly IC +0.0191, t 0.43; pooled IC +0.0126 (clustered t 0.31). Real IC sits at the 64.2nd percentile of 1000 within-week shuffles (p95 0.0836; seed 20261004).
  - Tercile spread per pair: gross -57.0 bp (t -0.63), net -97.4 bp at 10 bp per side, -137.4 bp at 20 bp per side.
  - A3 (P minus P7): 481 events, 27 weeks; IC +0.0545, t 1.25; raw one-sided p 0.112, Holm 0.223 (A1 Holm 0.334). Decision-ineligible.
  - Placebos: P7 as signal IC +0.0227 (t 0.41); signal on the session after R IC +0.0086 (t 0.17); shuffle percentile 64.2. Nothing works and nothing falsely works.
  - Sub-periods: before 2026-03-01 IC -0.0140 (t -0.22, 18 weeks, 421 events); from 2026-03-01 IC +0.0689 (t 1.16, 12 weeks, 199 events).
  - Secondary: all valid P (1035 events, no volume or staleness filter) IC +0.0418 (t 1.11); exit at the open after R IC -0.0081 (t -0.17).
  - The contract prices themselves are informative (AUC 0.81, Brier 0.137 against 0.183 for the base rate, monotone deciles); the stock market evidently prices that information by 15:00 ET on S. The beat/miss outcome moves the stock (beat +0.75%, miss -2.17% excess), but P does not predict the move.
- Caveats:
  - Power is limited: 30 weeks, so effects below IC 0.11 per week are not excluded. The point estimate is near zero, not negative enough to suggest a reversal.
  - Thin contracts (median volume about 6.3k USD; 627 of 1353 events pass the 5k filter); one year of one young market; GAAP-basis contracts kept (485 of 1353 events).
  - Not run: sector-adjusted secondary (no SIC-to-SPDR map in the repo); the end-time timing proxy for events without an 8-K; overlay scoring.
  - Data-layer defect found on the way (`data/features/earnings_events/` `acceptance_utc`) is written up in `report.md`; the table and its builder were not edited.
- Next iteration suggestion: none from this contract. Reopen only with a new, preregistered contract after about 450 new events, or with a different information channel (not P at 15:00 ET on S, e.g. intraday odds changes on the announcement day or revisions after the print).
- ML or AI-information round entry conditions: not met, no model involved.
