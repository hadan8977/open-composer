# H-20260922-05 report: does the volatility target transfer, and does the dip boost pay?

Iteration `h20260922_05_salvage`, 12 cells (3 unoverlaid baselines + the frozen
S3-vt40 reference + 4 transfer + 4 boost), each at 10 and 20 bp per side, plus
240 random-pick placebo runs and 80 calendar-shift placebo runs. Engine identity:
`s3_novt_baseline` reproduces the published S3 at 145.4% / -56.4% / 1.48 and
`s3_vt40_frozen` reproduces H-20260922-02 at 98.3% / -30.2% / 1.66 exactly.
Targets for the transfer path were frozen from each book's own selection-window
volatility before any metric was computed (`candidate-manifest.json`).

## Every cell, anchor window 2024-01-08 .. 2026-09-19, 10 bp per side

| cell | anchor CAGR | anchor DD | anchor Sharpe | holdout Sharpe | turnover/yr | 20 bp CAGR | placebo |
|---|---|---|---|---|---|---|---|
| `s1_novt_baseline` | 27.7% | -16.9% | 1.35 | 2.18 | 14.2 | 25.9% | — |
| `s1_vt9` | 14.7% | -10.8% | 1.05 | 2.02 | 14.8 | 13.0% | pick 0% |
| `s1_vt11` | 19.0% | -13.5% | 1.13 | 2.11 | 18.0 | 16.9% | pick 0% |
| `s2_novt_baseline` | 49.1% | -20.3% | 1.49 | 1.36 | 3.7 | 48.5% | — |
| `s2_vt12` | 31.0% | -7.7% | 1.75 | 1.82 | 5.8 | 30.3% | pick 25.0% |
| **`s2_vt16`** | **39.7%** | **-10.2%** | **1.80** | **1.88** | 6.3 | 38.8% | pick 23.3% |
| `s3_novt_baseline` | 145.4% | -56.4% | 1.48 | 1.80 | 10.1 | 143.0% | — |
| `s3_vt40_frozen` | 98.3% | -30.2% | 1.66 | 2.04 | 9.4 | 96.5% | — |
| `s3_vt40_boost55_h5` | 109.7% | -31.1% | 1.78 | 2.16 | 11.5 | 107.3% | shift 0% / 5% |
| `s3_vt40_boost55_h10` | 112.3% | -31.4% | 1.80 | 2.18 | 11.3 | 109.9% | shift 0% / 5% |
| `s3_vt40_boost60_h5` | 112.4% | -31.8% | 1.80 | 2.18 | 12.0 | 109.9% | shift 0% / 0% |
| **`s3_vt40_boost60_h10`** | **116.3%** | **-32.3%** | **1.82** | **2.21** | 11.7 | 113.7% | shift 0% / 5% |

Benchmarks, same window: SPY 20.9% / -18.6% / 1.02, MTUM 30.0% / -21.0% / 1.05,
SPMO 35.8% / -20.3% / 1.27, QQQ 24.7% / -22.6% / 0.96, TQQQ 53.5% / -57.2% / 0.93.

## Path A: the mechanism does not transfer by itself. It transfers where the book is too volatile for its own return.

**S1, reject.** The sector sleeve already runs at 14.3% median realized
volatility. Targeting 8.6% or 11.4% of it removes exposure the book was being
paid for: Sharpe falls 1.35 -> 1.05 / 1.13 and annualized return falls 27.7% ->
14.7% / 19.0% while drawdown only improves from -16.9% to -10.8% / -13.5%. A
volatility target is not free risk reduction; on a book whose volatility is
already near its return-per-unit-risk optimum it is a return tax. S1 keeps no
overlay.

**S2, accept as a risk overlay, not as alpha.** `s2_vt16` raises Sharpe 1.49 ->
1.80, halves drawdown -20.3% -> -10.2%, holds annualized return at 39.7%, still
above SPMO's 35.8%, and survives 20 bp (38.8% / 1.77). It fails the preregistered
transfer criterion on one leg only: 23.3% of random-pick seeds beat its holdout
Sharpe. That number is inherited, not caused -- H-20260918-05 already recorded
S2's own random-pick placebo at 20% and labelled the sleeve "a tech/growth basket
whose ranking contributes little". The overlay does not fix that and was never
asked to. Honest statement: this is a strictly better-sized version of a known
beta basket, so it may replace the live S2 rule, but it may not be presented as
a new selection edge.

## Path B: the dip boost pays, and it pays by removing a brake rather than adding leverage.

`s3_vt40_boost60_h10` reaches 116.3% / -32.3% / 1.82 against the frozen
98.3% / -30.2% / 1.66: +18.0pp of annualized return for 2.1pp more drawdown, with
holdout Sharpe up 2.04 -> 2.21 and 113.7% still standing at 20 bp. All four boost
variants improve on the frozen cell and the ordering is monotone in both the
target and the hold, which is what a real exposure effect looks like rather than a
lucky corner of a grid. The calendar-shift placebo -- the test that killed the
Composer RSI family in H-20260922-04 -- beats this cell on 0 of 20 offsets for
anchor return and 1 of 20 for holdout Sharpe.

The safety property that makes this shippable: the overlay multiplier is
`min(1.0, target / realized_vol)`, so a higher target can only move the multiplier
closer to 1.0. The boost can never hold more than the unscaled S3 book, which is
exactly the rule running in the live paper sleeve today at 145.4% / -56.4%. Every
cell in this table is therefore strictly less risky than the authorized position.

## What limits the claim

* The dip signal fires on 14 sessions in the whole panel; 72 of roughly 670 anchor
  sessions are boosted at hold 10. The effect rests on few episodes.
* Every window here is a bull market with shallow dips. The boost adds exposure
  into a fall; in a dip that keeps going it gives back more than it gains. The
  -32.3% figure is the worst this sample produced, not a bound.
* S2's selection edge remains unproven and is not improved by this work.
* The top-50 rule-momentum book was in the brief's path A but is not reproducible
  in this engine: it is a `model_ranking_portfolio` over a dynamic point-in-time
  universe, so its weight history cannot be regenerated from the ETF panel. No
  overlay result is claimed for it.
