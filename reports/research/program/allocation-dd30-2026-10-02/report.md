# Program allocation under a ~30% drawdown budget, return first (T-20261002-43)

Run 2026-10-02 at about 13:35 UTC on the repaired SIP archive (T-20261002-01 swap at 13:19:55Z). The preregistration is `prereg.md` (commit 469ae13). Numbers come from `results.json`; the script is `scripts/run_program_dd30_allocation.py` and its tests are in `tests/test_program_dd30_allocation.py`.

## Decision (mechanical, prereg rules 3–5)

| | S3 | C2 | F2 | F1 | cash | borrowed |
|---|---|---|---|---|---|---|
| **chosen weights** (grid B, robust top-10 average) | **0.60** | **0.335** | **0.12** | **0.025** | 0 | **0.08** |
| control: S3 delevered to the same drawdown | 0.60 | 0 | 0 | 0 | 0.40 | 0 |

- **Guard (i) passes.** W\* beats the control by 11.6 points of anchor CAGR; the bar is 3.
- **Guard (ii) passes.** Weights chosen on the select window (S3 0.6, C2 0.1, F2 0.3) earned 95.2% annualized in 2026 YTD, against 84.9% for the control.
- **Guard (iii) fails, so rule 5 applies.**
  - One neighbour of W\* deviates by 6.2 points; the limit is 5.
  - That neighbour is S3 0.65. It earns 83.7% but has a -32.1% drawdown, so the drawdown limit is what binds; this is not fragility.
  - The four rebalance offsets move anchor CAGR by only 1.6 points.
  - The rule therefore uses the average of the 10 best feasible points. All 10 have S3 = 0.60.

## The chosen program versus the control

| window | program CAGR | program max DD | program Sharpe (excess) | control CAGR | control max DD |
|---|---|---|---|---|---|
| full 2017-10..2026-09 | 32.6% | **-29.9%** | 1.02 | — | -28.3% |
| stress 2017-10..2023-09 | 18.0% | -29.9% | 0.66 | 14.7% | |
| select 2023-09..2025-12 | 58.4% | -21.4% | 1.55 | | |
| anchor 2024-01..2026-09 | **77.2%** | -21.4% | 1.89 | 66.0% | |
| 2026 YTD (annualized) | 99.4% | -11.8% | 2.34 | 84.9% | |

- **Calendar years:** 2018 -14.7%, 2019 +34.0%, 2020 +29.4%, 2021 +47.5%, 2022 -22.2%, 2023 +51.9%, 2024 +44.7%, 2025 +78.8%, 2026 YTD +61.9%.
- **Risk:** worst month -21.8% (stress window); volatility about 30%/yr.
- **Stress costs:** at 20 bp per side for S3 and C2, W\* earns full 30.7% with DD -30.9%, and anchor 75.3% with DD -21.1%.

**Frontier (grid B, best anchor CAGR at each drawdown limit):**

| drawdown limit | weights | anchor CAGR |
|---|---|---|
| -25% | S3 0.50, C2 0.45, cash 0.05 | 64.2% |
| -30% | S3 0.60, C2 0.45, F2 0.05, borrowed 0.10 | 77.5% |
| -35% | S3 0.70, C2 0.55, borrowed 0.25 | 90.8% |

**Correlations** (daily, realization-dated):

| pair | stress | anchor |
|---|---|---|
| C2–S3 | 0.42 | 0.44 |
| F2–S3 | 0.51 | 0.54 |
| C2–F2 | 0.88 | 0.77 |
| F1 with S3 | about 0 | about 0 |
| F1 with C2 | 0.16 | 0.07 |
| F1 with F2 | 0.24 | 0.25 |

**Inverse-volatility, unlevered (for comparison):** full 11.0% (DD -16.5%), anchor 27.1%.

## What the numbers mean

- **S3 sets the program; the drawdown limit sets S3.** Every top-10 point holds S3 at 0.60. Above that, the 2022 drawdown breaks -30%.
- **The remaining capital goes to C2 and F2 rather than cash.** This adds about 11 points a year in the anchor window at the same full-history drawdown. The gain is real diversification in the bad years: C2 returned +1.4% in 2022 while S3 lost 33.6%.
- **F1 gets almost nothing under return-first.** It returns 9.8% a year with no correlation to the rest. It keeps running on quant1 for its own forward evidence and for the day the owner wants a lower drawdown.

## Caveats (written in the prereg before results; still true)

1. **The backtest headline is optimistic.** S3's anchor CAGR (118.8% alone) comes from a salvage design that saw part of 2023–2025. Its paper record is about two weeks (-1.8%). The 77% program figure is a backtest, not a forecast. The forward record decides.
2. **-30% is the worst of 2017–2026.** A longer bear market for levered tech (2000–2002 style) would breach it.
3. **Grid B assumes one Reg T account.** The margin filter is approximate: 3x ETFs at 75% maintenance, per FINRA 4210; Alpaca's exact requirement is 待核对 (to be checked).
4. **F1 and F2 have no separate stress-cost series.**

## Void first run

The first official run, a few minutes earlier, indexed F1/F2 by decision date. Data pitfall #60: the v1.2 files' row t is realized at t+2. That made F2–S3 correlation -0.01 and C2–F2 0.08, and its decision (S3 0.60, C2 0.27, F2 0.18, F1 0.02, borrowed 0.07) is void. `realization_dated()` fixes this; it was verified with the file's `spy_ret` ≡ SIP SPY at t+2 (correlation 1.000) and is covered by a test. The void results are kept outside the repo at `/tmp/lead/alloc_void_misaligned/results.json`.

## How this is used

- **Paper.**
  - Each engine keeps running at its own size: S3 and C2 sleeves on the old account, F1 on quant1, F2 on quant2 once the v1.2 crons start.
  - Program-level forward P&L = these weights × each engine's daily paper return, minus 6.50%/yr on the 8% borrowed.
  - No paper sleeve is resized; returns do not depend on scale.
- **Operating guards for the program.** These are review triggers, not backtested rules:
  - forward program drawdown -20%: review, and halve S3 if S3's own stop rules also fire;
  - -30%: stop the S3 weight and review.
- **Live.** These weights are the capital split for the eventual live proposal, after paper evidence.
