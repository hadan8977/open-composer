# Report: h20260929_37_ls_short_unlocked (T-20260929-37)

Generated from `results.json` (run 2026-09-29, script `scripts/run_h20260929_37_ls_short_unlocked.py`, capped at 1.8 GB, 171 s). All numbers below are copied from that file; the same numbers are in `trial-ledger.jsonl`.

## Verdict

**0 of 16 preregistered candidates reach K1, K2 or watch_recent; all 16 are `reject`.** Best net result in each direction: A dual-class pairs DC_M252_ALWAYS anchor -0.015 / stress -0.065; B ETF-crash laggards LL_SOXX_K3_H5 anchor 0.758 / stress -0.223; C sector intramonth SIM_ABL_LS_K3_MONTHLY anchor 0.119 / stress -0.012 (best of the Quantpedia calendar composites SIM_LS_K2 -1.040 / -0.712). No K2 edge reaches 0.05 in both windows (the stress-window edge is negative for all 16). `workflow_pass` true; `research_pass` false; `llm_contribution_pass`, `ml_contribution_pass`, `paper_ready_pass` not applicable / false.

## Contract (frozen in cost-table.json and direction-review.json before the run)

Windows: anchor 2024-01-08..2026-09-17 (judged), stress 2016-05-02..2023-09-15 (252-day signals start 2017-01/02, actual start in results.json), select 2023-09-18..2025-12-31, holdout 2026-01-02..2026-09-17 reference only. Close signal, next-open fill. Judged cost = frozen 10 bp per side per leg plus borrow (ADV-tier 0.5% / 2% per year, ETF 0.5%). Also reported: main cost 5 bp + half trailing-21d Abdi-Ranaldo spread, stress 10 bp + full spread, frozen 20 bp. Judged value = median over 21 monthly / 5 weekly rebalance offsets (A, C ablation), entry delays 0/1/2 (B), the single calendar version (C composite). K1: anchor >= 1.1882, stress >= 0.6447, median 20 bp CAGR > 0 in both windows. K2: S3 inverse-vol blend edge >= 0.05 in both windows. Strong: K2 >= 0.10 both or K1 with anchor >= 1.4853 / stress >= 0.8059. Watch: anchor >= 1.1882 without K1. Keep/watch tiers also need the candidate anchor Sharpe above the max of its 20 random placebos. DSR uses 22 trials (16 candidates + 3 mirrors + 3 placebo families).

## Results (medians over variants; Sharpe of the cash-financed overlay)

Columns: gross Sharpe with no cost and no borrow (anchor / stress, diagnostic) | anchor and stress Sharpe at 10 bp after borrow (judged) | anchor Sharpe at 20 bp | anchor Sharpe under main cost / 2x-spread stress cost | 20 bp after-borrow CAGR anchor / stress | K2 edge vs S3 anchor / stress | turnover per year (gross units) | borrow drag per year (anchor) | mirror (sign-flipped book) anchor / stress Sharpe | random-placebo anchor mean / max over 20 seeds | DSR (anchor, judged variant) | tier.

| candidate | gross A / S | A 10bp | S 10bp | A 20bp | A main / 2x | CAGR20 A / S | K2 edge A / S | turnover | borrow | mirror A / S | placebo mean / max | DSR | tier |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| DC_M252_ALWAYS | 0.825 / 0.544 | -0.015 | -0.065 | -0.442 | -0.571 / -1.398 | -1.0% / -1.1% | 0.177 / -0.443 | 9.0 | 0.87% | -1.218 / -1.432 | -0.993 / -0.783 | 0.025 | reject |
| DC_M63_ALWAYS | 0.760 / 0.590 | -0.278 | -0.120 | -0.858 | -1.062 / -1.990 | -2.0% / -1.8% | 0.014 / -0.253 | 14.2 | 0.84% | -1.518 / -1.547 | -1.036 / -0.857 | 0.008 | reject |
| DC_M252_THR1 | 0.496 / 0.526 | -0.231 | 0.022 | -0.657 | -0.848 / -1.686 | -1.0% / -0.7% | 0.194 / -0.356 | 6.9 | 0.44% | -0.863 / -1.347 | -0.953 / -0.641 | 0.011 | reject |
| DC_M63_THR1 | 0.653 / 0.668 | -0.335 | -0.009 | -0.994 | -1.211 / -2.155 | -1.7% / -1.2% | 0.084 / -0.209 | 11.6 | 0.40% | -1.464 / -1.380 | -1.029 / -0.710 | 0.007 | reject |
| DC_W252_ALWAYS | 1.046 / 1.113 | -0.050 | 0.133 | -0.843 | -1.113 / -2.524 | -2.1% / -1.6% | 0.086 / -0.338 | 18.7 | 0.86% | -1.576 / -2.400 | -3.048 / -2.468 | 0.022 | reject |
| DC_W63_THR1 | 0.958 / 1.308 | -0.942 | -0.242 | -2.346 | -2.907 / -4.897 | -4.2% / -3.3% | -0.144 / -0.260 | 27.3 | 0.40% | -2.241 / -2.601 | -2.768 / -2.313 | 0.000 | reject |
| LL_XLK_K3_H5 | -1.330 / 0.497 | -1.954 | -0.182 | -2.539 | -2.823 / -4.018 | -26.1% / -7.2% | -1.680 / -0.596 | 70.1 | 0.19% | 0.698 / -1.192 | -0.885 / -0.086 | 0.000 | reject |
| LL_XLK_K5_H5 | -0.460 / 0.619 | -1.180 | -0.326 | -1.854 | -2.092 / -3.400 | -17.4% / -7.3% | -1.065 / -0.691 | 69.3 | 0.19% | -0.262 / -1.544 | -0.983 / -0.663 | 0.000 | reject |
| LL_XLK_K3_H10 | -0.733 / 0.271 | -1.094 | -0.143 | -1.428 | -1.575 / -2.305 | -19.8% / -5.7% | -1.234 / -0.502 | 50.2 | 0.27% | 0.369 / -0.681 | -0.729 / -0.125 | 0.000 | reject |
| LL_XLK_K5_H10 | -0.092 / 0.300 | -0.551 | -0.290 | -0.962 | -1.086 / -1.991 | -11.2% / -6.0% | -0.712 / -0.650 | 49.8 | 0.27% | -0.379 / -0.886 | -0.817 / -0.208 | 0.002 | reject |
| LL_SOXX_K3_H5 | 1.289 / 0.515 | 0.758 | -0.223 | 0.247 | -0.529 / -1.978 | 2.6% / -8.4% | 0.143 / -0.566 | 73.8 | 0.19% | -1.818 / -1.220 | -0.458 / 0.198 | 0.236 | reject |
| SIM_LS_K3 | 0.261 / 0.374 | -1.394 | -0.954 | -2.893 | -2.332 / -4.329 | -23.4% / -22.7% | -1.116 / -1.030 | 141.7 | 0.21% | -1.866 / -1.671 | -1.789 / -0.817 | 0.000 | reject |
| SIM_LS_K2 | 0.256 / 0.342 | -1.039 | -0.712 | -2.263 | -1.820 / -3.587 | -23.2% / -22.5% | -0.996 / -0.870 | 141.7 | 0.21% | -1.515 / -1.380 | -1.420 / -0.196 | 0.000 | reject |
| SIM_MN_K3 | 0.757 / 0.260 | -1.664 | -2.123 | -3.683 | -2.859 / -5.107 | -21.6% / -24.3% | -0.994 / -1.539 | 141.7 | 0.21% | -3.006 / -2.547 | -1.771 / -1.091 | 0.000 | reject |
| SIM_MN_K2 | 0.914 / 0.190 | -1.232 | -1.704 | -3.110 | -2.355 / -4.630 | -20.3% / -24.5% | -0.828 / -1.354 | 141.7 | 0.21% | -2.913 / -2.022 | -1.362 / -0.299 | 0.000 | reject |
| SIM_ABL_LS_K3_MONTHLY | 0.232 / 0.077 | 0.119 | -0.012 | 0.041 | 0.071 / -0.056 | -0.3% / -2.6% | -0.437 / -0.457 | 10.4 | 0.50% | -0.346 / -0.165 | -0.312 / 0.026 | 0.040 | reject |

The first failing condition of every candidate is in `results.json` (`candidates[].failed_conditions`): for all 16 it is K1 anchor below 1.1882 (the best is LL_SOXX_K3_H5 at 0.7578) and K2 stress-window edge below 0.05.

## Reading

* **A. Dual-class share pairs (GOOG/GOOGL, FOX/FOXA, NWS/NWSA, LEN, HEI, BF, UA, Z, MKC, GEF).** The price-ratio z-score has a gross edge (anchor / stress gross Sharpe 0.50-1.05 / 0.53-1.31) that is consumed by costs: at 10 bp per side the Sharpe is -0.94..-0.02 in the anchor and -0.24..0.13 in the stress window; 20 bp turns every CAGR negative. Borrow is a small part (0.4%-0.9% per year). The main-cost model (5 bp + half Abdi-Ranaldo spread) is worse than flat 10 bp because daily high/low spreads of the thin classes are wide. Mirror and random-sign placebos are all clearly negative, so the sign of the rule is right but the edge is below the cost of trading two legs. Correction to the registry: the paperswithbacktest page says "No backtest"; the 5.20% / Sharpe 1.68 in the registry does not exist there, and the paper's own rule is a short-interest double sort, so this direction never had a published pair-trade result.
* **B. ETF crash -> constituent laggards vs short ETF.** XLK versions lose gross in the anchor window (gross Sharpe -1.33..-0.09): after the ETF's worst-decile days, the ETF itself rebounds (the mirror, long ETF / short laggards, is 0.698 for K3_H5 and 0.369 for K3_H10 at the anchor but -1.192 / -0.681 in the stress window), consistent with the earlier local finding that index-ETF dip buying has a real but non-tradable signal. The laggard-minus-ETF spread does not pay. LL_SOXX_K3_H5 is positive in the anchor (0.758 after 10 bp and borrow, DSR 0.236, above its placebo maximum 0.198) but stress -0.223, K2 stress edge -0.566, and 0.247 at 20 bp; it fails K1 and K2 and is not a watch tier.
* **C. Sector SPDR intramonth momentum.** The Quantpedia rule rebuilt exactly (D+1 momentum, D+2/D+3 reversal, D-10..D-5 momentum, nine sector SPDRs, 252-day ranking) has a gross Sharpe of only 0.26 / 0.37 (long-short K3) and 0.76 / 0.26 (long top-3 vs short SPY K3) in anchor / stress, versus the published 0.55 / 0.54 over 1998-2026. It trades 141.7 gross units per year, so 10 bp per side costs about 14% a year; net Sharpe is -1.04..-1.66 in the anchor. The plain monthly ablation (no calendar windows, 21 offsets) is 0.119 / -0.012. The Quantpedia article was opened and its rules extracted; the underlying Nathan-Suominen-Tasa paper was seen only as a search summary. That paper reports that the window moved by one day after the May 2024 T+1 settlement change, so the fixed D+1 / D-10 calendar may be one day off in the anchor window; the rule was not altered after the fact.

## Caveats

* K2 reference: a pure T-bill sleeve (zero overlay) scores a K2 edge of +2.300 (anchor) / +0.765 (stress) in this machinery (`diagnostics_added_before_final_run.null_sleeve_k2_edge`), because inverse-volatility weighting puts almost all weight on a near-zero-volatility sleeve. K2 edges of low-volatility overlays (all DC rows, anchor 0.014-0.194) are therefore not evidence by themselves; all 16 fail the stress-window edge anyway.
* Gross-Sharpe and null-sleeve diagnostics were added after a first complete run showed all rejects; the judged fields reproduce that first run exactly (checked).
* Constituent lists for B are fixed, approximate early-2016 top-10 holdings written from memory (not point-in-time, survivor bias). UA/UAA and FOX/FOXA class identities changed during the sample. Borrow tiers are a preregistered assumption; days-to-cover exclusion was not applied (reason in cost-table.json). Alpaca paper does not charge borrow, so paper results would look better than this backtest.
* The stress window starts 2017-01/02 for 252-day signals (data starts 2016-01-04), as in h20260929_51.
* No candidate reached a keep tier, so nothing is written to `reports/research/screens/kept.jsonl`.
