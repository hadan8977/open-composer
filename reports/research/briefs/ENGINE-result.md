# ENGINE result -- giants sweep, 2026-09-22

Engine `scripts/run_giants_sweep.py`, manifest `config/giants_sweep/manifest.yaml`,
iteration `reports/research/iterations/giants_sweep_20260922/`. `oc research
direction-check` ok, `oc research iteration validate` ok. Regression: the three
live sleeves reproduce `rotation_cell` to 0.0000 Sharpe on the same panel (worst
gap vs the card as printed is 0.0415 on S1's holdout, which the reference
implementation also shows today -- SIP archive drift since 09-18).

**24 cells ran in 66 s. 0 pass all gates.** G1 0/24, G1' 0/24, G2 7/24, G3 4/24,
G4 0/24. Anchor-window benchmarks (CAGR / Sharpe): SPY 20.9% / 1.02, MTUM 30.0% /
1.05, SPMO 35.8% / 1.27, QQQ 24.7% / 0.96, TQQQ 53.5% / 0.93.

| # | cell | anchor CAGR | anchor DD | anchor Sh | holdout Sh | placebo beat |
|---|---|---|---|---|---|---|
| 1 | `f1_tqqq_rsi_no_hedge_ablation` | 15.9% | -5.2% | 1.37 | 1.50 | 0% |
| 2 | `f1_composer_tqqq_safe` | 35.8% | -24.0% | 0.93 | 0.65 | 10% |
| 3 | `f1_sp500_2x_leverage` | 26.9% | -21.1% | 0.95 | 0.75 | 60% |

No census headline survives our windows, our next-open fills and 10 bp per side.
The only placebo-clean cell is the Composer RSI tree with its UVXY/TECL hedges
replaced by cash: a low-exposure, high-Sharpe book that beats every benchmark on
vol-matched excess (+12.0% vs SPY, +14.2% vs SPMO) and fails only the 50% return
bar. Putting the hedges back cuts its Sharpe to 0.79. F2's "2.46 Sharpe" two-leg
structure returns 4.8% here and loses to its own random-pick placebo on 100% of
seeds; so does every F5 canary cell; F7 loses 20%+ a year to costs alone.

Skipped: F3 (refuted by H-20260922-04), VIX term structure (no VX futures) and the
census second batch -- see the iteration's `unrunnable.md`. Next step is not a wider
grid: can the frozen H-20260922-02 volatility target scale cell 1 to the return bar?
