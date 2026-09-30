# T-20260930-15 measured-quote check (2026-09-30T12:16:39Z)

Design: A1 sampling + A2 formulas, `amendment-2026-09-30-a2-executable-quotes.md`. Numbers: `quote-check.json`. Tiers are the mechanical A2 output; the verdict is the lead review's.
Sample: 30 seeded days (2024-02-01 .. 2026-08-13), 0 requests in the final invocation (quote and raw-close responses are cached in cache/quotes; the first invocation made 336 quote requests, the second 150 raw-close requests), 0 HTTP 429.

| cell | m bp | t_nw5 | placebo | s_long | s_short | s | h_long | h_short | net 1x | net 2x | missing quote | tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C_L20_P1500 | 17.13 | 15.68 | 1.00 | 18.53 | 6.67 | 25.20 | 6.94 | 6.62 | -16.07 | -49.27 | 0.81% | closed |
| O_L20_P1500 | 14.60 | 4.84 | 1.00 | 17.43 | 24.56 | 41.99 | 17.74 | 16.22 | -35.39 | -85.38 | 1.17% | closed |

net 1x = m - s - 8, net 2x = m - 2s - 16 (bp per day). h = A1 half-spread (ask-bid)/(ask+bid), bp.

## C_L20_P1500
- sample gross (trade-price) 11.55 bp, executable -13.65 bp over the 30 days (report only; the decision `m` is the full main window).
- long: pairs 4148/4181 (missing price 0, missing quote 33, 60s fallback 1285); s mean 18.53 median 6.80 p95 85.63 max 168.66 winsor1/99 18.46 bp; trade-price position mean -1.975 (q05 -14.24, q50 0.50, q95 1.00, outside [0,1] 0.326).
- short: pairs 4146/4181 (missing price 0, missing quote 35, 60s fallback 1298); s mean 6.67 median 4.42 p95 19.83 max 228.18 winsor1/99 6.46 bp; trade-price position mean 0.551 (q05 -0.00, q50 0.50, q95 1.00, outside [0,1] 0.139).
- basis mismatch (report only): 23/1802 symbols, 6.5% of picks; excluding them s 16.46 bp, net 1x -7.33, net 2x -31.79, tier closed (with the full-window m); sample gross trade 2.38 / executable -14.08 bp.
- adjusted/raw close factor: 3751/8362 rows differ from 1 by >0.1%, 2778 by >1%, no factor 0.
- close / mid_1550 - 1 (long): day-mean -3.99 bp, pooled mean -4.04, q05 -89.09, q50 -2.71, q95 76.08; quotes 4168/4181.
- p_1549 position in the 15:50 spread (long): mean -2.068, q05 -14.31, q25 -0.00, q50 0.49, q75 0.54, q95 1.00, outside [0,1] 0.325.

## O_L20_P1500
- sample gross (trade-price) 15.58 bp, executable -26.41 bp over the 30 days (report only; the decision `m` is the full main window).
- long: pairs 4078/4130 (missing price 0, missing quote 52, 60s fallback 658); s mean 17.43 median 10.58 p95 58.12 max 556.73 winsor1/99 17.07 bp; trade-price position mean 0.519 (q05 -0.00, q50 0.50, q95 1.00, outside [0,1] 0.115).
- short: pairs 4085/4130 (missing price 0, missing quote 45, 60s fallback 639); s mean 24.56 median 12.60 p95 91.40 max 300.55 winsor1/99 24.24 bp; trade-price position mean -0.481 (q05 -5.80, q50 0.50, q95 1.00, outside [0,1] 0.240).
- basis mismatch (report only): 23/1762 symbols, 5.4% of picks; excluding them s 35.15 bp, net 1x -28.54, net 2x -71.69, tier closed (with the full-window m); sample gross trade 8.69 / executable -26.45 bp.
- adjusted/raw close factor: 3503/8260 rows differ from 1 by >0.1%, 2661 by >1%, no factor 0.
