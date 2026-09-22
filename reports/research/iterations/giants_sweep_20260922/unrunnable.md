# Unrunnable and deliberately skipped candidates

## Skipped because the evidence already exists

| candidate | reason |
|---|---|
| F3, 3x sector momentum + hedge (census A group: v6 Symphony Sorter, angarey sector 3x v2, SOXL Growth v2.4.5) | H-20260922-04 ran this family under the identical protocol and it was refuted. Re-running it would spend compute to re-derive a negative result and would add multiple-testing exposure on the same holdout for nothing. |
| Volatility target and drawdown brake overlays | Already frozen and answered by H-20260922-02 (a 40% volatility target rescues the S3 levered sleeve; the drawdown brake loses to its own calendar-shift placebo). No overlay is re-searched here. |

## Unrunnable on this box

| candidate | blocker |
|---|---|
| VIX term-structure four-quadrant short volatility (Concretum) | Requires VIX, VIX3M and VX futures term structure. `data/sip/` holds equity and ETF daily bars only; there is no VX futures feed and no authorization to add one. Approximating the term structure from VIXY/UVXY prices would be a different strategy, so it is recorded here rather than guessed. |
| Logical Invest UISX3 | Rules are not public (commercial subscription). Nothing to replicate. |
| Kethan predictive order-flow imbalance | Needs tick data; and the source itself reports a -1.73 Sharpe after spreads. |
| Heitz et al. pre-earnings-announcement premium | The source's own title is "Disappearing"; excluded by the census. |
| Keller LAA | Needs the FRED unemployment series as a point-in-time macro input. That is a capability this iteration does not declare, so it is deferred rather than approximated with a revised series. |
| Zarattini/Maroy SPY intraday momentum, ORB | Minute bars, not daily. Belongs to the minute-bar engine (H-20260918-02 second half). |
| Kipnis KDA, Varadi minimum correlation, Harvey rebalancing flows, Chen MAX reversal | Census second batch; each needs either a covariance/weighting layer or a single-stock universe with its own cost model. Not in this manifest and not silently approximated. |

## Ran, but with a caveat that limits what the number means

| cell | caveat |
|---|---|
| `f7_overnight_*` | The source paper states no cost assumption and the census recorded a Sharpe of 7.75. The frozen protocol charges 10 and 20 bp per side, which at two round trips per night is roughly 20 bp a night. All three cells lose 20%+ annualized. This is a verdict on the family's cost sensitivity, not on the existence of the overnight seasonality. Re-testing it honestly needs an authorized cost tier, which the frozen protocol does not provide. |
| `f4_nine_sig_tqqq_agg` | Implements the published quarterly 9% signal line and the 10% bond floor. The thread's later discretionary overrides ("30 down, stick around") are not modelled. |
| `f1_composer_tqqq_rsi`, `f1_composer_tqqq_safe`, `f1_composer_ftlt20` | The Composer pages disclose the 200-day trend filter and the RSI thresholds but not the PPO parameters or the exact "strong vs softer" split. Those branches use the disclosed RSI(10) rules only, so these are faithful to what is published, not to what is running on the platform. |
| All F5 monthly cells | A 1-20 session calendar shift on a month-end signal lands on the previous month-end feature, so the placebo tests "last month's signal" rather than fine timing jitter. |
