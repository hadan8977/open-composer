# t20260930_14_overnight_persistence_12m: ON252 out-of-sample band and official-price check

Generated 2026-09-30T16:56:37Z (pre-backtest gate stamp 2026-09-30T16:09:39Z). Every number below is read from `results.json`. Design: `hypotheses.md` (frozen before any pool B or official-price number).

**gate_a = true, gate_b = false** (computed mechanically by the script).

## Test A: pool B (dv21 rank 1501-3000), ON252 decile long/short, close to next open (gross)

| window | mean bp/night | NW t (5) | plain t | n nights | placebo beat | placebo mean bp | long bp | short bp | pool EW bp | mean names | k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main 2024-01-08..2026-09-29 | 13.69 | 5.19 | 4.68 | 683 | 1.00 | -0.05 | 13.42 | -0.27 | 6.13 | 1,257 | 125.2 |
| stress 2016-05-02..2023-08-31 | 17.35 | 12.02 | 11.93 | 1,729 | 1.00 | 0.03 | 19.13 | 1.78 | 7.03 | 1,279 | 127.5 |

Next-day intraday leg of the same book: main -15.72 bp (t -3.82), stress -20.74 bp (t -8.09).

By year (mean bp, NW t, n):

| year | mean bp | NW t | n |
|---|---|---|---|
| 2016 | 10.30 | 2.99 | 52 |
| 2017 | 19.24 | 8.89 | 251 |
| 2018 | 18.48 | 7.19 | 251 |
| 2019 | 14.33 | 4.70 | 252 |
| 2020 | 25.36 | 4.80 | 253 |
| 2021 | 18.08 | 3.44 | 252 |
| 2022 | 13.33 | 3.84 | 251 |
| 2023 | 14.17 | 4.65 | 250 |
| 2024 | 11.79 | 4.19 | 252 |
| 2025 | 13.71 | 2.70 | 250 |
| 2026 | 16.11 | 2.82 | 185 |

Data: mean 1,332 names per night in pool B, 6,166 symbols in total, delisted share 0.229 of pool rows and 0.344 of pool symbols; candidates ever in dv21 top 3,200: 8,759; split-like rows filtered 2,477.

## Test B: official auction prices on 20 seeded days (ON252_P500)

Sampled days (20, default_rng(20260930) over main-window dates with a valid ON252_P500 night): 2024-06-07, 2024-10-25, 2024-11-21, 2024-12-26, 2025-01-03, 2025-01-23, 2025-02-14, 2025-04-03, 2025-04-15, 2025-06-30, 2025-07-25, 2025-08-19, 2025-10-29, 2025-11-18, 2025-11-25, 2026-01-12, 2026-01-13, 2026-01-15, 2026-02-20, 2026-03-24.

- rows (symbol, day): 1,958; valid pairs 1,958; missing 0 = **0.0000** (missing official close 0, missing official open 0, missing adjustment factor 0).
- delta LS = mean(delta long decile) - mean(delta short decile): **-2.72 bp/night** over 20 days (long -3.70 bp, short -0.98 bp).
- delta LO top 20: **-5.88 bp/night** over 20 days.
- delta quantiles over all valid rows (bp): {"p05": -43.80886137799356, "p25": -2.6823530412328767, "p50": -7.194167095381232e-05, "p75": 0.33353680698539057, "p95": 29.677622124978406}; rows with |delta| > 50 bp: 128.
- adjustment: nights with f_(t+1)/f_t differing from 1 by > 1e-3: 10 of 1,958 (by > 1e-2: 4). Basis: official (Q/O open, M/6 close, listing exchange) prices multiplied by adjusted-close/raw-close factors of the same sessions; Delta = r_official - r_daily (panel).
- API requests in the final invocation: 4,377.

## Diagnostics (contaminated P500/P1500 panel, report only)

### P500

Baseline ON252 LS: main 17.01 bp (t 3.24), stress 7.67 bp (t 3.33).

1. ADR: share in long decile 0.0219, short decile 0.0559, pool 0.0214 (main window); LS ex-ADR main 17.12 bp (t 3.20), stress 7.64 bp (t 3.42). Metadata covers 0.821 of pool symbols.
2. Momentum (daily-bar close, same loader and price_hygiene defaults as the T-35 panel (not derived from panel returns)): mean rank corr ON252 vs 12-1 main 0.567, stress 0.484; 12-1 decile LS next night main 20.83 bp (t 3.96), stress 5.69 bp; double sort ON252 LS within momentum terciles (main): low -1.75, mid 3.48, high 19.33 bp (stress: 7.20 / 3.14 / 6.55).
3. Earnings nights (16015 events, 1448 tickers): flagged share of book positions main 0.0088 (pool rows 0.0071); LS ex-earnings main 16.24 bp (t 3.20) versus baseline 17.01 bp.
4. Concentration: top-10 symbols carry 0.322 of LS PnL in the main window (APLD, WULF, IREN, MSTR, APP, MP, LITE, OKLO, CRDO, ONDS) and 0.369 in the stress period.
5. LO top 20: gross main 25.25 bp (t 3.32), excess over pool EW 18.12 bp (t 3.23); pool EW 7.13 bp; SPY close-to-open 5.91 bp (stress: LO 12.03, SPY 3.41).
6. Easy-to-borrow proxy on the short leg: LS main 16.62 bp (t 3.18), stress 7.88 bp (t 2.84); borrow tier cost of the baseline short leg main 0.20 bp/night.

### P1500

Baseline ON252 LS: main 11.99 bp (t 3.08), stress 8.63 bp (t 5.37).

1. ADR: share in long decile 0.0631, short decile 0.0612, pool 0.0320 (main window); LS ex-ADR main 11.48 bp (t 2.93), stress 8.34 bp (t 5.24). Metadata covers 0.794 of pool symbols.
2. Momentum (daily-bar close, same loader and price_hygiene defaults as the T-35 panel (not derived from panel returns)): mean rank corr ON252 vs 12-1 main 0.498, stress 0.451; 12-1 decile LS next night main 14.59 bp (t 3.81), stress 6.57 bp; double sort ON252 LS within momentum terciles (main): low -0.93, mid 3.38, high 15.34 bp (stress: 4.50 / 4.90 / 8.52).
3. Earnings nights (16015 events, 1448 tickers): flagged share of book positions main 0.0075 (pool rows 0.0069); LS ex-earnings main 11.43 bp (t 2.97) versus baseline 11.99 bp.
4. Concentration: top-10 symbols carry 0.190 of LS PnL in the main window (WULF, IREN, HUT, OKLO, MP, AAOI, APLD, FFAI, LITE, SMR) and 0.148 in the stress period.
5. LO top 20: gross main 20.20 bp (t 2.49), excess over pool EW 13.50 bp (t 2.06); pool EW 6.70 bp; SPY close-to-open 5.91 bp (stress: LO 13.91, SPY 3.41).
6. Easy-to-borrow proxy on the short leg: LS main 12.19 bp (t 3.02), stress 8.02 bp (t 3.98); borrow tier cost of the baseline short leg main 0.46 bp/night.

T-35 parity (same ON252 LS, main window): P500: mine 17.01 bp vs T-35 results.json 17.01 bp (abs diff 0.000); P1500: mine 11.99 bp vs T-35 results.json 11.99 bp (abs diff 0.000).

## Conventions and limits

- Costs do not enter the gates (gross measurement); the 2 bp/side auction contract of the design applies later.
- Sample days: main-window dates on which the ON252_P500 book has a valid night (the last panel date has no next open).
- Official price adjustment: r_official = official open_(t+1) x f_(t+1) / (official close_t x f_t) - 1 with f_d = local daily close / raw SIP daily close.
- Momentum, ADR, earnings and concentration diagnostics use the contaminated P500/P1500 panel and do not enter the gates.
