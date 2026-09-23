# Hypotheses: h20260923_12_s3_defense_first

## Hypothesis H-20260923-12
On the frozen S3 vt40+boost book (63-session absolute momentum vs SHY over TQQQ/SOXL/UPRO/USD/
TECL, top 2, monthly, 21-session realized-volatility target at 0.40 with a QQQ-oversold dip
boost to 0.60, 1.0 leverage cap, unchanged), redirecting the remainder that currently sits in
SHY (1 minus the risk-sleeve weight) into a published Defense First rotation (Carlson 2025: rank
TLT/GLD/DBC/UUP monthly by the mean of each asset's 1/3/6/12-month return, weight 40/30/20/10 by
rank, replace any asset whose momentum is below T-bill (BIL) momentum) -- DF01 with the paper's
own SPY fallback for a failing slot, or DF02 with an SHY fallback instead -- raises the
pre-select-window (2016-01-04..2023-09-15) Sharpe by at least 0.10 over DF00 (S3 exactly as
renewed, remainder in SHY), leaves the max drawdown no worse than DF00's, beats a momentum-free
diversification control (EW, static 25/25/25/25 TLT/GLD/DBC/UUP) on Sharpe, beats at least 36 of
its 40 random-ranking placebos (RR-k) on Sharpe, and does not break the frozen anchor-window
(2024-01-08..2026-09-16) return bar at 10 or 20 bp. DF00 is the reference both candidates are
compared against. No ranking is made between DF01 and DF02; each is a separate, independent
pass/fail comparison against the same preregistered adoption rule.

## Failure mode
The Defense First mechanism is published, has three independent replications (Quantitativo,
AllocateSmartly, BestFolio) landing in a consistent performance neighborhood, and the author's own
LinkedIn post confirms the asset menu -- but none of that evidence shows the mechanism adds value
net of costs specifically as a remainder-holding rule inside S3's book, nor that its momentum
ranking (rather than simple diversification into bonds/gold/commodities/dollar) carries
information. Two related families in this exact repo, on this exact book, this same day, already
failed for closely analogous reasons: dir:s3_bear_regime_guard (H-20260923-11) found that four
bear-regime gates on S3's risk sleeve all lost to their own exposure-matched and circular-shift
controls, and H-20260918-06 found that mechanical cross-sectional relative-strength selection over
a broad ETF universe underperformed simple buy-and-hold in all 8 preregistered families. The two
most likely failure modes here are structurally the same kind of trap: (1) any apparent
remainder-reallocation edge could come purely from diversifying out of cash into four
non-cash assets, a pattern EW is designed to catch by holding the same four-asset universe with no
ranking; and (2) an apparent edge could come from the specific historical path rather than the
ranking mechanism's actual information content, a pattern RR-k is designed to catch by replacing
the momentum-based rank with 40 seeds of random monthly ranking while holding the cash-hurdle
screen, weights, and fallback fixed. A third, narrower failure mode is warmup: the Defense First
momentum score needs 12 completed calendar month-end closes, so it is not fully valid until the
2017-01-31 decision (applied from the 2017-02-03 open) even though S3 itself starts holding risk
on 2016-05-02 -- before its valid date DF01/DF02/RR-k default to DF00's own behavior (remainder in
SHY), which shrinks the effective test window by about 9 months but precedes, and therefore does
not compromise, the 2018 (-22.0%) or 2022 (-33.6%) drawdown episodes the design window exists to
test. EW has no such warmup gap, a known, disclosed asymmetry in EW's favor for that same 9
months.

## Measurement
Design window 2016-01-04..2023-09-15 carries all four design-window adoption-rule criteria (a)-(d):
(a) Sharpe >= DF00 Sharpe + 0.10, (b) max drawdown no worse than DF00's, (c) Sharpe beats >=36 of
the candidate's own 40 RR-k placebos, (d) Sharpe > EW's. Frozen anchor window 2024-01-08..2026-09-16
carries only the do-no-harm check (e): CAGR >=50% and max drawdown >=-35% (gate G1) at both 10 and
20 bp per side. The 2026 holdout (2026-01-02..2026-09-17) is not scored for either candidate in
this round -- it was already spent evaluating the live S3 book at the 2026-09-23 renewal, so no
out-of-sample claim is made here. Reported per candidate: design-window CAGR, Sharpe, max
drawdown, turnover; EW's own metrics (shared, not per-candidate); the full 40-value RR-k Sharpe
distribution and beat-count; anchor-window CAGR/Sharpe/max drawdown at 10 and 20 bp. DF00's numbers
are not recomputed: its design-window metrics come from the existing stress replay
(reports/paper/renewal/2026-09-23-s3-stress-2016-2023.json) and its anchor-window metrics from the
authorized 2026-09-23 renewal record. Both candidates are reported in full regardless of outcome --
this is a 2-way comparison, not a pick-the-winner search.

## Stop/Pivot criterion
If neither DF01 nor DF02 passes all of (a)-(e), the verdict is "keep SHY" and the direction
(dir:s3_defense_first_remainder) is not reopened except with a new defensive-asset set, a new
published remainder-allocation rule, or new disclosed data -- not by re-tuning DF01/DF02's
windows, weights, or momentum blend, and not by widening the candidate list. This is round 1 of
this direction. Compute budget for the decisive test: 83 simulations (2 candidates + 1 EW control
+ 80 RR-k placebos), fixed; DF00 requires no new simulation. Total compute budget including
overhead: 45 minutes.
