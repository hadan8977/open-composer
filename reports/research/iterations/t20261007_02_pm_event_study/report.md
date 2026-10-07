# Report: t20261007_02_pm_event_study (prediction-market odds and ETF returns)

Source of every number: `results.json` (24 frozen variants, generated after the pre-backtest validation stamp in `prebacktest-validated-at.txt`), `j_contemporaneous_diag.json` (post-run, descriptive). `results_R.json` is an earlier R-only run of the same code (DSR counted over 6 variants); `results.json` supersedes it.

## Verdict (plain language)

**Not holding, in both parts.** Prediction-market odds do carry news: after a one-hour jump in odds the mapped ETF has already moved the same way (+6.3 bp on average in the hour before the odds point, t 6.1, 1,054 episodes; Fed-cut odds +10.3 bp, t 5.8), and after a release the realised surprise moves TLT by +18 bp in 30 minutes (t 4.4, 129 events). But nothing usable is left after the odds are visible: trading the pre-release lean (R) or the jump (J) gives gross returns of about zero (R: -8 to 0 bp per trade, J: -2.8 to +1.4 bp) against costs of 7.4 bp (R, release minute in pre-market) and 3.7 bp (J) per round trip. Best selected net Sharpe: R -0.75 (placebo 0.42, DSR 0.00), J -0.97 (placebo 0.58, DSR 0.00). Neither reaches P1; no paper sleeve is written, no orders, no Modal spend.
What stays open (leads, not results): tariff de-escalation jumps followed in the same direction (net +2.2 bp, gross about +6 bp per trade, n 151, t 0.85, report-only, gross t about 2.2 derived from the net t and the mean cost, Holm over 48 rows far from significant); and R's sign is wrong or flat, so a contrarian reading is not supported either (mirror of a noise result).
Not done: the V4 crash diagnostic (2017-2023 minute data) and the live-feed consistency check were not run because no part is close to a tier; both are required before any future tier.

## Events (how many)

- R (Kalshi): 8 classes with a valid pre-release distribution since 2024-01-08; 4 classes meet the 20-event rule and enter the pooled set (CLAIMS 55, CPI 32, NFP 32, PCE 20 = 139 events; FOMC 16, ADP 17, GDP 10, ISM 13, JOLTS 2 stay out). Traded after warm-up and the median size filter: 63 trades (R1), 59 (R2). Positive-control events: 129.
- J (Polymarket, 179 markets): 6,442 raw one-hour jumps >= 3 pp, 3,247 inside tradable hours (08:00-19:30 ET weekdays), 1,125 episodes at 3 pp, 622 at 5 pp, 346 at 8 pp (FED_EASE 413, TARIFF_ESC 215, SHUTDOWN 163, TARIFF_DEESC 156, FED_HIKE 103, RECESSION 36, ELECTION_DEM 25, ELECTION_GOP 14 at 3 pp). Traded (one position per ETF at a time, bars available): 284-997 per variant.
- Total distinct events examined: about 1,260 (139 + 1,125), counting the three-per-class rule as written; macro release moments from 2024-01-08 are about 120 (not hundreds): the hundreds come from J.

## R: scheduled releases (net of costs, TLT, hawkish lean -> short)

| variant | trades | mean gross bp | mean net bp | net Sharpe | gross Sharpe | net placebo pct | gross placebo pct |
|---|---|---|---|---|---|---|---|
| R1 h5 | 63 | -7.97 | -15.40 | -1.34 | -0.72 | 0.15 | 0.15 |
| R1 h30 | 63 | -4.45 | -11.88 | -0.98 | -0.37 | 0.29 | 0.34 |
| R1 h120 | 63 | -0.23 | -4.66 | -0.34 | -0.02 | 0.42 | 0.49 |
| R2 h5 | 59 | -0.27 | -7.71 | -1.04 | -0.04 | 0.54 | 0.47 |
| R2 h30 | 59 | -2.83 | -10.26 | -1.20 | -0.35 | 0.26 | 0.29 |
| R2 h120 | 59 | -1.87 | -6.30 | -0.75 | -0.23 | 0.42 | 0.38 |

- Selected (median of top three by net Sharpe, rule 5b.6): R2 h120. DSR 0.00 (N 24, N_eff 23.9), robustness 1 of 6, shifted-fill Sharpes -0.75 / -1.17 / -0.96, cost-2x Sharpe negative.
- Positive control (realised surprise, not tradable): TLT +18.2 bp at 5 minutes (t 5.07) and +18.3 bp at 30 minutes (t 4.35), 129 events, SE clustered by date. The test can see a release reaction when it is told the surprise.
- Power: realised per-trade sd 33-66 bp, so the minimum detectable net mean at 80 percent power is 10.6-20.6 bp. A rule that nets 5 bp after a 7.4 bp cost needs about 12 bp gross, which is inside this range, so R is called not holding at tradable size; edges below about 10 bp gross cannot be excluded but could not pay the cost anyway.
- Report-only: per class at 30 minutes TLT net: CLAIMS -7.1 / -9.5 bp (t -1.9 / -1.7), CPI -5.2 / +2.6, NFP -38.3 / -18.6 (t -1.6), PCE +2.8 / -10.2; pooled SPY, QQQ, IWM at 30 minutes net -1.7 to -4.7 bp (t -0.15 to -1.30). Nothing survives Holm.
- Why the lean has no information: Kalshi pre-release expectations equal consensus except headline CPI and the policy rate (Diercks, Katz, Wright 2026); here the hourly candles are often stale (median age 3-5 hours), and FOMC events were mostly illiquid (16 valid of 32 after the age filter).

## J: Polymarket odds jumps (net of costs)

| variant | trades | mean gross bp | mean net bp | net Sharpe | gross Sharpe | net placebo pct | gross placebo pct |
|---|---|---|---|---|---|---|---|
| t3_h15_continue | 997 | 0.53 | -3.18 | -3.67 | 0.63 | 0.76 | 0.80 |
| t3_h15_reverse | 997 | -0.53 | -4.24 | -4.65 | -0.63 | 0.16 | 0.10 |
| t3_h60_continue | 946 | 0.66 | -2.86 | -2.27 | 0.53 | 0.82 | 0.78 |
| t3_h60_reverse | 946 | -0.66 | -4.18 | -3.32 | -0.53 | 0.15 | 0.23 |
| t3_h240_continue | 822 | 0.85 | -3.11 | -1.22 | 0.33 | 0.65 | 0.72 |
| t3_h240_reverse | 822 | -0.85 | -4.81 | -1.88 | -0.33 | 0.22 | 0.23 |
| t5_h15_continue | 569 | 0.14 | -3.77 | -2.73 | 0.11 | 0.75 | 0.45 |
| t5_h15_reverse | 569 | -0.14 | -4.06 | -3.03 | -0.11 | 0.63 | 0.39 |
| t5_h60_continue | 544 | 1.35 | -2.29 | -1.26 | 0.75 | 0.85 | 0.89 |
| t5_h60_reverse | 544 | -1.35 | -4.99 | -2.70 | -0.75 | 0.11 | 0.10 |
| t5_h240_continue | 488 | 0.58 | -3.43 | -0.97 | 0.17 | 0.58 | 0.59 |
| t5_h240_reverse | 488 | -0.58 | -4.60 | -1.29 | -0.17 | 0.40 | 0.43 |
| t8_h15_continue | 325 | -0.21 | -4.31 | -2.38 | -0.12 | 0.53 | 0.42 |
| t8_h15_reverse | 325 | 0.21 | -3.90 | -2.16 | 0.12 | 0.69 | 0.52 |
| t8_h60_continue | 311 | 1.02 | -2.70 | -1.04 | 0.40 | 0.84 | 0.70 |
| t8_h60_reverse | 311 | -1.02 | -4.75 | -1.82 | -0.40 | 0.31 | 0.22 |
| t8_h240_continue | 284 | -2.75 | -6.87 | -1.56 | -0.63 | 0.10 | 0.17 |
| t8_h240_reverse | 284 | 2.75 | -1.38 | -0.32 | 0.63 | 0.82 | 0.89 |

- Selected (median of top three): J t5 h240 continue, net Sharpe -0.97, net placebo 0.58, DSR 0.00, robustness 1 of 6, cost-2x negative. Best single net placebo percentile in the grid: 0.85 (t5 h60 continue), still below 0.90 and with net mean -2.29 bp.
- Continuation versus reversal: gross continuation is slightly positive (+0.5 to +1.4 bp at the 3 and 5 pp thresholds, about 0 to -2.8 at 8 pp 240 minutes), mirror image for reversal; the sizes are below the 3.7 bp cost, whichever sign. Both signs were counted as trials.
- Contemporaneous check (post-run, descriptive, `j_contemporaneous_diag.json`): signed ETF return in the hour before the odds point is +6.3 bp (t 6.1, 1,054 episodes), FED_EASE +10.3 (t 5.8), TARIFF_DEESC +7.6 (t 1.5), RECESSION +7.3, ELECTION_GOP +7.2, FED_HIKE +4.6, TARIFF_ESC +2.9, SHUTDOWN +1.9, ELECTION_DEM -0.8. The theme sign mapping is right; the ETF moves with the odds, leaving no drift after the odds point. The hourly odds grid cannot tell which moved first.
- Report-only by theme at 60 minutes, 3 pp: FED_EASE continue -3.8 / reverse -3.7 (t -3.3 / -3.2: costs, not signal); TARIFF_DEESC continue +2.2 (t 0.85) / reverse -9.4 (t -3.6); RECESSION continue +5.9 (n 36); ELECTION themes n 14-25, no power.
- Power: realised per-trade sd 17-47 bp, minimum detectable net mean 1.3-6.9 bp. Checks required for "not holding" are met: rules as written, three thresholds, three horizons, both modes, all 24 variants run, power adequate for the economically relevant size.

## Checks against the frozen contract

- Pre-registration: direction-check ok, `iteration validate --stage pre-backtest` ok at 2026-10-07T04:49:34Z; rules in `scripts/t0702_pm_grid.py` (sha256 in the manifest). Odds-side data were downloaded before the freeze; no ETF return for any event had been computed.
- Data adaptations disclosed: Kalshi claims and ISM strikes are `greater_or_equal` (treated as the same curve as `greater`; fetched with `scripts/t0702_fetch_kalshi_ext.py`); sector SPDR minute bars are sparse in extended hours (sectors only in report-only runs); FOMC and GDP had few valid events after the 48-hour candle-age filter.
- 5b items: timing placebo (100 seeds, gross and net) done; median-of-top-three selection done; d replaced by 0/+1/+2 minute fill shifts (done: 0 of 3 positive for both parts); V4 not run (see Verdict); live-feed consistency not run (no sleeve).
- Multiple testing: 24 main variants counted (DSR); report-only rows (6 R class, 6 R asset, 48 J theme, plus the diagnostic) use no selection.

## What would change the answer (next steps if the owner wants more depth)

1. Minute or trade-level odds (Polymarket Data API trades, Kalshi 1-minute candles) around each jump to measure who moves first; the hourly grid cannot. Cost: heavy download, about half a day of fetching, no new compute cost.
2. A consensus series for R (Bloomberg-like), only if free: without it the lean has no information beyond consensus. Not planned.
3. Tariff de-escalation continuation as a single, pre-registered follow-up on fresh data (forward observation from now): effect +6 bp gross against 3.7 bp cost, n 151, t 0.85 net; it needs about 600 episodes to confirm at this size, so forward shadow logging is the cheap way (odds feed is already collected by `scripts/collect_prediction_markets.py`).
