# Report: h20261002_pm_macro_uncertainty

Source of every number: `results.json` in this folder (generated 2026-10-02T13:48:17+00:00 by `scripts/run_h20261002_pm_macro_uncertainty.py`, after the freeze commit e7e6dfc). Rules frozen in `hypotheses.md` and `candidate-manifest.json`.

## Verdict

H1 is **not supported and not refuted**. D = 13.93 bp (QQQ, R_cc excess BIL) is below the +15 bp bar, the one-sided permutation p is 0.413 (bar 0.10), and D is above the +5 bp stop line. The anchor D is 26.1 bp (> 0). Continue rule: fails (1 of 3 conditions met: only the anchor D > 0). Stop rule: not triggered. No candidate is scored for adoption (all `decision_eligible: false`). H2 (CPI days only) also fails its continue rule. The sample is 79 non-FOMC release days (31 with U_rel > 1, 48 with U_rel <= 1), too few to separate +15 bp from noise: the within-series shuffle distribution has a 90th percentile of 51.2 bp.

## H1

| statistic | value |
|---|---|
| D full sample 2023-07-12..2026-09-17 (QQQ R_cc) | 13.93 bp (n 79) |
| permutation p (1000 shuffles, seed 20261002) | 0.413; real D below the placebo p90 (51.2 bp) |
| slope on log U_rel | 38.5 bp per unit, HC1 t 0.41 |
| D anchor 2024-01-08.. | 26.12 bp (n 69) |
| D SPY / IWM | 19.7 / 24.6 bp |
| D with R_co (QQQ), full / anchor | 6.4 / 6.4 bp |
| FOMC days alone | D -9.0 bp (n 23); anchor 11.9 bp |
| D without 2022 | not applicable: the sample starts in July 2023 (no 2022 day) |
| leave-one-year-out D | 2023 out 25.5, 2024 out 19.6, 2025 out -48.1, 2026 out 57.6 (range -48.1 to 57.6) |

The positive D rests on 2025: dropping 2025 gives -48.1 bp.

## Placebos

- Within-series shuffle: real D 13.9 bp vs 90th percentile 51.2 bp (mean 3.6): not above.
- T+1 session, same signal: D -20.2 bp full, -9.4 bp anchor (should be about 0; a negative value of this size is within noise at this n).
- Random non-release sessions matched on weekday and month: mean D 0.04 bp, sd 31.2 bp, share of draws at or above the real D 0.319.

## H0 (context, no gate): announcement-day mean R_cc excess BIL, bp (Welch t) vs other sessions

| set | days | QQQ | SPY | IWM | TLT |
|---|---|---|---|---|---|
| pooled_all | 110 | 2.4 (-0.39) | -6.3 (-1.21) | -8.8 (-0.96) | -13.1 (-1.18) |
| KXCPI | 39 | 25.5 (0.77) | 6.0 (-0.11) | -3.9 (-0.35) | -25.5 (-1.39) |
| KXPAYROLLS | 36 | -14.2 (-0.73) | -15.2 (-0.98) | -17.6 (-0.89) | -16.6 (-0.85) |
| KXGDP | 12 | -8.1 (-0.42) | -5.2 (-0.52) | 13.4 (0.21) | -16.0 (-0.59) |
| KXFED | 25 | 1.0 (-0.26) | -10.3 (-0.83) | -9.8 (-0.53) | 14.6 (0.76) |
| pooled_non_fomc | 87 | 4.4 (-0.23) | -4.3 (-0.92) | -7.2 (-0.76) | -20.5 (-1.67) |

Other sessions: 690. No announcement premium is visible in 2023-07..2026-09 on these ETFs; TLT is weak on announcement days.

## H2 (CPI days only, Cleveland Fed nowcast as consensus proxy)

- Events with a gap: 39; mean gap -0.053 percentage points. 77 percent of the gaps are negative, consistent with the bin-midpoint mean sitting about 0.05 below the published single-decimal value (frozen construction; the mean gap is -0.053), so sign(gap) largely measures that offset rather than a view against the nowcast.
- |gap| >= median: n 20, hit rate 0.55, binomial p 0.412; anchor hit rate 0.625 on 16 events. Continue rule: fails (hit rate < 0.60, p > 0.10).

## Candidates (net of costs; mean per event in bp; DSR over 9 on the full-session series)

| id | asset | n | mean net bp | t | hit | ann. on invested days | stress mean bp | anchor mean bp | DSR | eligible |
|---|---|---|---|---|---|---|---|---|---|---|
| U1 | QQQ | 31 | 11.8 | 0.47 | 0.65 | 30% | 7.8 | 8.4 | 0.153 | no |
| U2 | SPY | 31 | 5.2 | 0.36 | 0.45 | 13% | 1.2 | 2.9 | 0.124 | no |
| U3 | IWM | 31 | -0.1 | -0.00 | 0.52 | -0% | -6.1 | -7.3 | 0.064 | no |
| U4 | QQQ | 79 | 3.3 | 0.18 | 0.62 | 8% | -0.7 | -6.7 | 0.092 | no |
| U5 | TQQQ | 31 | 36.1 | 0.48 | 0.65 | 91% | 26.1 | 25.7 | 0.156 | no |
| U6 | QQQ | 79 | 2.2 | 0.27 | 0.62 | 6% | 0.3 | -2.1 | 0.108 | no |
| U7 | QQQ | 40 | 12.0 | 0.58 | 0.62 | 30% | 8.0 | 9.5 | 0.179 | no |
| G1 | TLT | 39 | 7.5 | 0.60 | 0.51 | 19% | 3.5 | 3.4 | 0.170 | no |
| G2 | QQQ | 39 | 18.0 | 1.20 | 0.69 | 45% | 14.0 | 10.5 | 0.378 | no |

All are reported, none is decision-eligible. Overlay scoring: `not_scored_h1_continue_rule_failed`.

## Caveats

- Sample: 2023-07-12..2026-09-17; Kalshi threshold markets exist only from late 2022 (earlier events are brackets), and six prior events are needed for U_rel.
- U is truncated to the listed strike range; FOMC U_rel moves with the listing, so FOMC is reported only separately.
- One payrolls release (2026-04-03, Good Friday) and two events on FOMC days (CPI 2024-06-12, GDP 2025-07-30) are outside the non-FOMC trading-day set.
- Hit rates and t values on 31 to 79 events: nothing here is evidence of an edge in either direction.
