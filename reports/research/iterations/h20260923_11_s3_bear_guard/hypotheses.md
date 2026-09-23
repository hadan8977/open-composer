# Hypotheses: h20260923_11_s3_bear_guard

## Hypothesis H-20260923-11
On the frozen S3 vt40+boost book (63-session absolute momentum vs SHY over TQQQ/SOXL/UPRO/USD/
TECL, top 2, monthly, 21-session realized-volatility target at 0.40 with a QQQ-oversold dip
boost to 0.60, 1.0 leverage cap), at least one of four bear-regime gates -- BG01 (QQQ close
below its own 200-session SMA), BG02 (SMH close below its own 200-session SMA), BG03 (the
HYG/IEF close-price ratio below its own 100-session SMA), or BG04 (the unscaled S3 book's own
equity curve below its own 200-session SMA) -- moving all of S3's risk weight to SHY while the
gate is on (signal on a completed close, applied at the next open, gate state checked daily),
cuts the pre-window (2016-01-04..2023-09-15) drawdown by more than an exposure-matched lower
volatility target (EM-k) would, beats a circular-shift placebo (CS-k, 20 within-window offsets),
and does not break the frozen anchor-window (2024-01-08..2026-09-16) return bar at 10 or 20 bp.
BG00 (S3 exactly as renewed, no gate) is the reference all four are compared against. No gate is
selected or ranked against the others; each is a separate, independent pass/fail comparison
against the same preregistered adoption rule.

## Failure mode
The gate mechanism (price or index below its own moving average moves risk to cash) is a
published, decades-old, independently-replicated class (Gayed and Bilello 2016; Faber 2007) with
a currently-live real-money instance (Gehrman, r/LETFs) on a related instrument, but none of that
evidence shows the mechanism adds value net of costs on S3's specific menu, gate assets, and
30-minute-cheap compute budget, nor that its timing (not merely its average exposure reduction)
carries information. The prior drawdown-brake experiment on this exact book (H-20260922-02)
already failed for precisely this reason -- it lost to a calendar-shift placebo -- so the two
most likely failure modes here are the same: (1) a gate cuts the design-window drawdown only
because it is de-risked more often on average, a pattern EM-k is designed to catch by holding
average exposure constant; and (2) a gate's apparent drawdown improvement is not specific to its
actual crossing dates, a pattern CS-k is designed to catch by testing 20 within-window
circular-shifted versions of the same on/off schedule. A third, narrower failure mode is data
warmup: the local SIP daily archive's earliest bar for every symbol needed (QQQ, SMH, HYG, IEF,
SHY, BIL and the five S3 menu ETFs) is 2016-01-04, not the requested 2015-01-02, so BG01/BG02
and the dip boost are not valid until 2016-10-17, BG03 until approximately 2016-05, and BG04
until approximately 2017-02 (200 sessions after S3 itself first holds risk on 2016-05-02); before
its valid date each gate reads as off, identical to BG00, which precedes and therefore does not
compromise the 2018 (-22.0%) or 2022 (-33.6%) drawdown episodes the design window exists to test,
but does shrink the effective design window for the earliest few months.

## Measurement
Design window 2016-01-04..2023-09-15 carries all four adoption-rule design-window criteria
(a)-(d): (a) max drawdown improvement >=10 percentage points vs BG00, (b) Sharpe >= BG00 Sharpe +
0.10, (c) Sharpe > the gate's own EM-k control, (d) Sharpe beats >=18 of the gate's own 20 CS-k
placebos. Frozen anchor window 2024-01-08..2026-09-16 carries only the do-no-harm check (e):
CAGR >=50% and max drawdown >=-35% (gate G1) at both 10 and 20 bp per side. The 2026 holdout
(2026-01-02..2026-09-17) is not scored for any gate in this round -- it was already spent
evaluating the live S3 book at the 2026-09-23 renewal, so no out-of-sample claim is made here.
Reported per gate: design-window CAGR, Sharpe, max drawdown, turnover; EM-k's own metrics and the
bisected scale factor c; the full 20-value CS-k Sharpe distribution and beat-count; anchor-window
CAGR/Sharpe/max drawdown at 10 and 20 bp. BG00's numbers are not recomputed: its design-window
metrics come from the existing stress replay (reports/paper/renewal/2026-09-23-s3-stress-2016-2023.json)
and its anchor-window metrics from the authorized 2026-09-23 renewal record. All four gates are
reported in full regardless of outcome -- this is a 4-way multiple comparison, not a
pick-the-winner search.

## Stop/Pivot criterion
If no gate (BG01-BG04) passes all of (a)-(e), the verdict is "no guard; keep the 25% exit" and
the direction is not reopened except with a new gate mechanism (for example a model that forecasts
regime transitions rather than reacting to a crossed moving average) or new data (for example an
options-implied or macro/credit series with a disclosed, replicable construction, unlike the
still-unspecified dir:macro_credit_drawdown_probability_gate post) -- not by re-tuning these four
gates' windows, SMA lengths, or thresholds, and not by widening the candidate list. This is round
1 of this direction (dir:s3_bear_regime_guard). Compute budget for the decisive test: 88
simulations (4 gates + 4 EM-k controls + 80 CS-k placebos), fixed; BG00 requires no new
simulation. Total compute budget including overhead: 30 minutes.
