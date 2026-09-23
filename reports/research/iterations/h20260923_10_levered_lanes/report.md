# h20260923_10_levered_lanes: second levered sector lane (H-20260923-10)

Verdict: **refuted** -- passed: none.

Machine (frozen, from H-20260922-05): one-ETF lane, 63-session absolute momentum against SHY at month-end, vt40 on 21-session realized volatility, dip boost 60/10, cap 1.0, next-open fills, 10 bp per side (20 bp stress). Windows: selection 2023-09-18..2025-12-31, holdout 2026-01-02..2026-09-17 (scored once), anchor 2024-01-08..2026-09-16.

| lane | anchor CAGR | anchor Sharpe | anchor maxDD | holdout CAGR | holdout Sharpe | 20 bp anchor CAGR | corr S3 | pool beat | shift beat | G1 | G2 | G3 | G4 | pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LN01 NUGT | 54.2% | 1.16 | -26.4% | 17.0% | 0.53 | 53.2% | 0.20 | 43.5% | 5.0% | True | False | False | True | **False** |
| LN02 JNUG | 57.6% | 1.19 | -30.1% | 19.3% | 0.57 | 56.4% | 0.21 | 39.1% | 5.0% | True | False | False | True | **False** |
| LN03 FAS | 11.1% | 0.36 | -38.3% | -24.1% | -0.74 | 10.3% | 0.20 | 82.6% | 90.0% | False | False | False | False | **False** |
| LN04 DPST | 2.4% | 0.19 | -41.2% | 23.0% | 0.61 | 1.4% | 0.21 | 34.8% | 35.0% | False | False | False | False | **False** |
| LN05 DFEN | 30.5% | 0.60 | -63.6% | -10.9% | -0.13 | 29.2% | 0.09 | 79.2% | 0.0% | False | False | False | False | **False** |

Reference, live S3 book (vt40 + boost): anchor 116.3% / Sharpe 1.82 / -32.3%, holdout Sharpe 2.21.

Diagnostics (never ranked): each lane raw and with vt40 only; the pool of 24 liquid levered ETFs under the same machine is the generic-leverage placebo (holdout Sharpe of each is in cells.parquet).

| diagnostic | anchor CAGR | anchor Sharpe | anchor maxDD | holdout Sharpe |
|---|---|---|---|---|
| LN01_raw | 56.5% | 0.95 | -53.9% | 0.23 |
| LN01_vt40 | 45.6% | 1.04 | -26.4% | 0.44 |
| LN02_raw | 53.8% | 0.91 | -57.4% | 0.40 |
| LN02_vt40 | 47.5% | 1.05 | -30.1% | 0.49 |
| LN03_raw | 9.5% | 0.32 | -39.1% | -0.76 |
| LN03_vt40 | 13.4% | 0.41 | -36.6% | -0.68 |
| LN04_raw | -2.2% | 0.21 | -41.6% | 0.46 |
| LN04_vt40 | 6.6% | 0.28 | -41.2% | 0.83 |
| LN05_raw | 17.3% | 0.54 | -64.7% | -0.36 |
| LN05_vt40 | 28.2% | 0.59 | -63.6% | -0.37 |

Pool under the same machine, best holdout Sharpe first: SOXL 2.16, TECL 1.86, LABU 1.36, GUSH 1.12, BULZ 1.11, TQQQ 1.09, QLD 0.73, ERX 0.67, DPST 0.61, JNUG 0.57, NUGT 0.53, AGQ 0.44, UWM 0.25, SPXL 0.21, UPRO 0.20, SSO 0.15, TNA 0.05, URTY 0.04, UDOW -0.04, FAS -0.74, BOIL -1.40, TMF -1.47, YINN -1.89, NAIL -2.27

