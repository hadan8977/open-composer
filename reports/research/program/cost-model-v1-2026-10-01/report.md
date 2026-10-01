# Cost model v1 (D4): measured half spreads, 2026-10-01

Source files: `results.json` (this directory), `open_composer/research/equity_book/cost_model_v1.json`, sample `data/research/equity_book/quotes/`. Code: `scripts/sample_equity_book_spreads.py`, `scripts/fit_equity_book_cost_model.py`, `open_composer/research/equity_book/costs.py`.

Sample: 60 random NYSE sessions (stratified by year, seed 20261001), 18000 symbol-days, 30 random symbols per liquidity decile of the U3000 pool of each day (the pool is about 2,200 names after the close >= $5 / not-fund / 252-session filters; deciles are equal-count within it). Half spread in bp = (ask - bid) / 2 / mid x 1e4 on SIP NBBO, valid quotes only (bid > 0, ask > bid). open = median over valid quotes 09:35-09:45 ET; mid = last valid quote before 12:00 (<= 60 s); close = last valid quote before 15:45 (<= 60 s).

## Summary

- Open-window half spread (what a next-open fill faces) averages 22.7 bp over the pool (median 14.0 bp): 2.6x the 12:00 value and 4.1x the 15:45 value.
- The flat 10 bp per side covers the realized mean open half spread only up to decile 1 (0 = most liquid); beyond that it understates it (decile 9: 42.5 bp). It overstates mid-day and close costs for most deciles. The 3/6/12/25 tiers are 0.39x to 0.90x the realized open mean by decile (below it where under 1) and 0.97x to 2.81x the mid-day mean.
- Holdout median absolute log error: open 0.44, mid 0.40, close 0.42 (constant baseline 0.78 / 0.60 / 0.59): i.e. a typical name is predicted within a factor of about 1.55 at the open. The model prices the liquidity ladder, not individual-name spreads.
- Measured on NBBO quotes in a 10-minute window after the open, not on auction fills: a market-on-open or opening-auction fill may be tighter or wider; this is the quote cost of trading just after 09:35.

## Coefficients

log(hs_bp) = a + b log(price) + c log(dollar_adv_21) + d log(vol_21) + year effects

| snapshot | n | a | b price | c dollar_adv_21 | d vol_21 | R2 | resid sd |
|---|---|---|---|---|---|---|---|
| open | 17995 | 12.717 | 0.531 | -0.577 | 0.567 | 0.570 | 0.732 |
| mid | 17422 | 10.596 | 0.323 | -0.447 | 0.615 | 0.551 | 0.598 |
| close | 17825 | 9.851 | 0.196 | -0.405 | 0.593 | 0.498 | 0.629 |

Year effects (baseline 2018): 
- open: 2019: +0.077, 2020: +0.090, 2021: +0.203, 2022: +0.083, 2023: +0.060, 2024: +0.214, 2025: +0.668, 2026: +0.800
- mid: 2019: -0.113, 2020: +0.070, 2021: +0.153, 2022: -0.068, 2023: -0.013, 2024: +0.135, 2025: +0.469, 2026: +0.503
- close: 2019: -0.247, 2020: -0.036, 2021: +0.182, 2022: -0.139, 2023: +0.000, 2024: +0.147, 2025: +0.426, 2026: +0.642

## Holdout (20% of days, train-only fit)

| snapshot | holdout days | holdout rows | median abs log error | constant baseline | decile-median baseline | median pred / realized |
|---|---|---|---|---|---|---|
| open | 12 | 3598 | 0.439 | 0.776 | 0.647 | 0.932 |
| mid | 12 | 3499 | 0.403 | 0.600 | 0.521 | 1.015 |
| close | 12 | 3559 | 0.415 | 0.585 | 0.474 | 1.062 |

## Calibration by liquidity decile on the holdout (median bp; 0 = most liquid)

### open

| decile | n | realized median | predicted median | pred / realized | median abs log err |
|---|---|---|---|---|---|
| 0 | 360 | 4.79 | 4.59 | 0.958 | 0.384 |
| 1 | 360 | 7.72 | 6.88 | 0.891 | 0.328 |
| 2 | 360 | 9.78 | 8.88 | 0.909 | 0.425 |
| 3 | 360 | 12.06 | 10.56 | 0.875 | 0.461 |
| 4 | 360 | 15.40 | 12.88 | 0.837 | 0.447 |
| 5 | 360 | 20.45 | 15.67 | 0.766 | 0.431 |
| 6 | 360 | 22.32 | 16.73 | 0.749 | 0.555 |
| 7 | 360 | 23.22 | 19.99 | 0.861 | 0.460 |
| 8 | 359 | 24.62 | 21.12 | 0.858 | 0.465 |
| 9 | 359 | 30.36 | 26.86 | 0.885 | 0.452 |

### mid

| decile | n | realized median | predicted median | pred / realized | median abs log err |
|---|---|---|---|---|---|
| 0 | 359 | 2.09 | 2.14 | 1.027 | 0.465 |
| 1 | 360 | 2.81 | 2.95 | 1.052 | 0.407 |
| 2 | 359 | 3.71 | 3.68 | 0.992 | 0.396 |
| 3 | 354 | 4.31 | 4.38 | 1.016 | 0.384 |
| 4 | 351 | 5.05 | 5.15 | 1.019 | 0.384 |
| 5 | 350 | 6.01 | 6.03 | 1.003 | 0.379 |
| 6 | 354 | 6.72 | 6.70 | 0.998 | 0.420 |
| 7 | 346 | 7.88 | 7.79 | 0.989 | 0.416 |
| 8 | 338 | 8.54 | 8.51 | 0.997 | 0.378 |
| 9 | 328 | 9.53 | 9.93 | 1.042 | 0.415 |

### close

| decile | n | realized median | predicted median | pred / realized | median abs log err |
|---|---|---|---|---|---|
| 0 | 360 | 1.44 | 1.43 | 0.998 | 0.444 |
| 1 | 360 | 1.76 | 1.95 | 1.113 | 0.470 |
| 2 | 360 | 2.18 | 2.36 | 1.081 | 0.439 |
| 3 | 358 | 2.65 | 2.94 | 1.110 | 0.448 |
| 4 | 359 | 3.03 | 3.42 | 1.128 | 0.424 |
| 5 | 359 | 3.65 | 4.01 | 1.098 | 0.421 |
| 6 | 359 | 4.10 | 4.51 | 1.100 | 0.414 |
| 7 | 351 | 4.95 | 5.21 | 1.052 | 0.369 |
| 8 | 351 | 5.36 | 5.68 | 1.060 | 0.381 |
| 9 | 342 | 6.32 | 6.62 | 1.048 | 0.380 |

## Realized half spread by decile and comparison with the flat and tiered costs

Realized mean = mean over the sample of the per-name half spread (what a trade pays on average); model mean = Duan-smeared mean prediction. Per-side cost = half spread (+ fee 0.5 bp in the model column). Flat = 10 bp per side; tiered = 3/6/12/25 bp for adv_rank <= 500/1000/1500/beyond (`run_h20260929_21_lockup_books.py`). AR = trailing 21-session daily-bar Abdi-Ranaldo half spread (0.5 x spread), the estimator data pitfall #58 calls 20-60x too high for large caps.

### open (all in bp)

| decile | n | median adv_rank | realized median | realized mean | model mean | model per side (+0.5 fee) | flat | flat / realized mean | tiered mean | tiered / realized mean | AR half (median) | AR / realized median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 1800 | 152 | 4.56 | 6.44 | 6.96 | 7.46 | 10.0 | 1.55x | 3.0 | 0.47x | 16.75 | 3.7x |
| 1 | 1800 | 428 | 6.94 | 9.43 | 10.52 | 11.02 | 10.0 | 1.06x | 3.7 | 0.39x | 16.75 | 2.4x |
| 2 | 1800 | 711 | 9.19 | 12.83 | 13.07 | 13.57 | 10.0 | 0.78x | 6.0 | 0.47x | 17.27 | 1.9x |
| 3 | 1800 | 982 | 11.72 | 16.60 | 16.62 | 17.12 | 10.0 | 0.60x | 8.7 | 0.52x | 18.81 | 1.6x |
| 4 | 1800 | 1268 | 14.25 | 20.00 | 19.21 | 19.71 | 10.0 | 0.50x | 12.0 | 0.60x | 19.55 | 1.4x |
| 5 | 1800 | 1560 | 17.73 | 23.39 | 23.47 | 23.97 | 10.0 | 0.43x | 21.2 | 0.90x | 20.62 | 1.2x |
| 6 | 1800 | 1857 | 20.57 | 28.32 | 28.01 | 28.51 | 10.0 | 0.35x | 25.0 | 0.88x | 20.81 | 1.0x |
| 7 | 1800 | 2162 | 23.43 | 31.56 | 30.13 | 30.63 | 10.0 | 0.32x | 25.0 | 0.79x | 21.63 | 0.9x |
| 8 | 1798 | 2479 | 26.76 | 36.28 | 40.36 | 40.86 | 10.0 | 0.28x | 25.0 | 0.69x | 22.26 | 0.8x |
| 9 | 1797 | 2819 | 31.19 | 42.53 | 49.80 | 50.30 | 10.0 | 0.24x | 25.0 | 0.59x | 22.17 | 0.7x |

Pool: median realized 13.99 bp, mean 22.73 bp, model mean 23.81 bp, tiered mean 15.45 bp, flat 10.0 bp.

### mid (all in bp)

| decile | n | median adv_rank | realized median | realized mean | model mean | model per side (+0.5 fee) | flat | flat / realized mean | tiered mean | tiered / realized mean | AR half (median) | AR / realized median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 1797 | 152 | 2.09 | 2.97 | 2.78 | 3.28 | 10.0 | 3.36x | 3.0 | 1.01x | 16.75 | 8.0x |
| 1 | 1799 | 428 | 2.82 | 3.79 | 3.90 | 4.40 | 10.0 | 2.64x | 3.7 | 0.97x | 16.75 | 5.9x |
| 2 | 1789 | 710 | 3.55 | 5.02 | 4.78 | 5.28 | 10.0 | 1.99x | 6.0 | 1.20x | 17.27 | 4.9x |
| 3 | 1779 | 982 | 4.20 | 5.85 | 5.79 | 6.29 | 10.0 | 1.71x | 8.7 | 1.48x | 18.88 | 4.5x |
| 4 | 1765 | 1267 | 5.10 | 6.82 | 6.90 | 7.40 | 10.0 | 1.47x | 12.0 | 1.76x | 19.66 | 3.9x |
| 5 | 1755 | 1560 | 5.82 | 7.94 | 8.04 | 8.54 | 10.0 | 1.26x | 21.2 | 2.67x | 20.71 | 3.6x |
| 6 | 1738 | 1856 | 6.59 | 8.89 | 9.32 | 9.82 | 10.0 | 1.12x | 25.0 | 2.81x | 20.79 | 3.2x |
| 7 | 1716 | 2160 | 7.59 | 10.26 | 9.91 | 10.41 | 10.0 | 0.97x | 25.0 | 2.44x | 21.71 | 2.9x |
| 8 | 1652 | 2479 | 8.33 | 11.87 | 12.50 | 13.00 | 10.0 | 0.84x | 25.0 | 2.11x | 22.25 | 2.7x |
| 9 | 1632 | 2817 | 10.14 | 13.68 | 15.94 | 16.44 | 10.0 | 0.73x | 25.0 | 1.83x | 22.22 | 2.2x |

Pool: median realized 5.16 bp, mean 7.61 bp, model mean 7.86 bp, tiered mean 15.21 bp, flat 10.0 bp.

### close (all in bp)

| decile | n | median adv_rank | realized median | realized mean | model mean | model per side (+0.5 fee) | flat | flat / realized mean | tiered mean | tiered / realized mean | AR half (median) | AR / realized median |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 1800 | 152 | 1.33 | 2.02 | 1.84 | 2.34 | 10.0 | 4.96x | 3.0 | 1.49x | 16.75 | 12.6x |
| 1 | 1800 | 428 | 1.73 | 2.45 | 2.55 | 3.05 | 10.0 | 4.08x | 3.7 | 1.50x | 16.75 | 9.7x |
| 2 | 1799 | 711 | 2.14 | 3.16 | 3.13 | 3.63 | 10.0 | 3.17x | 6.0 | 1.90x | 17.27 | 8.1x |
| 3 | 1797 | 982 | 2.67 | 3.85 | 3.81 | 4.31 | 10.0 | 2.59x | 8.7 | 2.25x | 18.81 | 7.1x |
| 4 | 1789 | 1268 | 3.12 | 4.32 | 4.42 | 4.92 | 10.0 | 2.32x | 12.0 | 2.78x | 19.56 | 6.3x |
| 5 | 1789 | 1561 | 3.65 | 5.27 | 5.21 | 5.71 | 10.0 | 1.90x | 21.2 | 4.02x | 20.64 | 5.6x |
| 6 | 1782 | 1857 | 4.12 | 6.09 | 6.11 | 6.61 | 10.0 | 1.64x | 25.0 | 4.10x | 20.81 | 5.1x |
| 7 | 1775 | 2162 | 4.82 | 6.84 | 6.60 | 7.10 | 10.0 | 1.46x | 25.0 | 3.66x | 21.43 | 4.4x |
| 8 | 1761 | 2479 | 5.59 | 8.37 | 7.94 | 8.44 | 10.0 | 1.19x | 25.0 | 2.99x | 22.20 | 4.0x |
| 9 | 1733 | 2819 | 6.47 | 9.29 | 9.30 | 9.80 | 10.0 | 1.08x | 25.0 | 2.69x | 22.10 | 3.4x |

Pool: median realized 3.33 bp, mean 5.14 bp, model mean 5.07 bp, tiered mean 15.37 bp, flat 10.0 bp.

## Open vs mid vs close

Paired rows (all three snapshots valid): 17310. Median of per-name ratios: open/mid 2.51, open/close 4.13, mid/close 1.46. Ratio of pooled medians: open/mid 2.61, open/close 4.10. Geometric means: open/mid 2.46, open/close 3.78.

| decile | n | open median | mid median | close median | open/mid (median ratio) | open/close |
|---|---|---|---|---|---|---|
| 0 | 1797 | 4.54 | 2.09 | 1.33 | 2.01 | 3.10 |
| 1 | 1799 | 6.94 | 2.82 | 1.73 | 2.34 | 4.02 |
| 2 | 1788 | 9.11 | 3.55 | 2.13 | 2.44 | 4.06 |
| 3 | 1777 | 11.69 | 4.20 | 2.66 | 2.52 | 4.33 |
| 4 | 1757 | 14.04 | 5.08 | 3.10 | 2.70 | 4.49 |
| 5 | 1745 | 17.57 | 5.82 | 3.65 | 2.72 | 4.46 |
| 6 | 1725 | 19.84 | 6.57 | 4.06 | 2.80 | 4.59 |
| 7 | 1700 | 22.68 | 7.55 | 4.76 | 2.75 | 4.58 |
| 8 | 1633 | 25.18 | 8.29 | 5.44 | 2.67 | 4.27 |
| 9 | 1589 | 29.93 | 10.01 | 6.29 | 2.70 | 4.35 |

## Trend by year (median half spread, bp, all deciles pooled)

| year | days | n | open | mid | close | open/mid |
|---|---|---|---|---|---|---|
| 2018 | 7 | 1964 | 10.33 | 4.44 | 2.85 | 2.06 |
| 2019 | 7 | 1977 | 12.58 | 4.36 | 2.48 | 2.92 |
| 2020 | 7 | 2023 | 13.99 | 5.48 | 3.39 | 2.22 |
| 2021 | 7 | 2041 | 14.53 | 5.70 | 3.64 | 2.47 |
| 2022 | 7 | 2033 | 13.83 | 5.09 | 3.09 | 2.72 |
| 2023 | 7 | 2049 | 11.50 | 4.67 | 3.08 | 2.50 |
| 2024 | 7 | 2049 | 13.16 | 5.00 | 3.32 | 2.62 |
| 2025 | 7 | 2010 | 15.87 | 6.00 | 3.80 | 2.59 |
| 2026 | 4 | 1164 | 18.04 | 6.31 | 4.78 | 2.73 |

## Sensitivity: as-printed price instead of the adjusted close

| snapshot | b price (adjusted, main) | b price (printed) | R2 printed | holdout median abs log error printed |
|---|---|---|---|---|
| open | 0.531 | 0.702 | 0.662 | 0.398 |
| mid | 0.323 | 0.371 | 0.563 | 0.397 |
| close | 0.196 | 0.187 | 0.488 | 0.421 |

## Caveats

- The `price` regressor is the split-adjusted `daily_broad` close of the prior session (the field the backtest panel will carry; it is back-adjusted (splits, and with the vendor's adjustment=all also dividends), so for old sessions it sits below the as-printed price). Median open-window quote mid / that close = 1.026; share of rows more than 10% apart (later splits, overnight gaps): 0.323.
- Seven to eight sessions per year, 300 names per session: year effects and the 2026 level rest on 4 sessions. Spreads are measured on NBBO quotes, not on fills; no queue/adverse-selection effect, no auction fills.
- AR comparison: the sample's most liquid decile has median adv_rank about 150, so the ratios above (about 1x to 12.6x) are for mid-caps and large-caps outside the top 100; the 20-60x of data pitfall #58 refers to mega-caps and is not tested here.
- Open-window raw quotes (10^5 to 10^6 per batch) are not stored; per-name aggregates are.
