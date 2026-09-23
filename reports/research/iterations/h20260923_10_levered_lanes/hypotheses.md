# Hypotheses: h20260923_10_levered_lanes

## Hypothesis H-20260923-10
At least one of five single-ETF levered sector lanes -- LN01 NUGT (2x gold miners), LN02
JNUG (2x junior gold miners), LN03 FAS (3x financials), LN04 DPST (3x regional banks), LN05
DFEN (3x aerospace and defense) -- run through the frozen S3 overlay machine (63-session
absolute momentum vs SHY, down-only 21-session realized-volatility target at 0.40 with a
QQQ-oversold dip boost to 0.60, 1.0 leverage cap, monthly rebalance) clears every frozen gate
(G1 or G1', G2, G3, G4, G5) and has anchor-window daily-return correlation with the live S3
book (TQQQ/SOXL/UPRO/USD/TECL, vt40+boost) of 0.5 or less, so it could run as a separate,
genuinely diversifying sleeve rather than a relabeled semiconductor trade. No lane is selected
or ranked against the others; each of the five is a separate pass/fail comparison against the
same fixed gates.

## Failure mode
The mechanism this round leans on -- Moskowitz and Grinblatt's industry momentum, and Hsieh et
al.'s finding that leveraged-ETF compounding depends on return autocorrelation -- explains why
the live S3 book worked (H-20260923-09: concentrated in trending semiconductors, not
diversified), but it does not guarantee any of the other four recently-strong Ken French
industries (Gold, Banks, Aero) is still trending once mapped onto its specific single-name
leveraged ETF, sized under the frozen overlay, and scored on the untouched 2026 holdout. The
select-window industry ranking (I-20260923-01) was read before these five lanes were chosen,
so it can only be confirmed, not discovered, by the holdout; a lane could also fail only the
new correlation criterion by passing the return/risk gates while simply re-expressing the same
"trending mega-cap growth" factor that already drives the live S3 book (financials and
aerospace both carry meaningful market and growth beta). A second failure mode is instrument-
specific: daily-reset compounding (verified for DPST and NUGT/DUST in this round's Direxion
source cards) means a choppy, non-trending period in gold, banks or defense could decay the
lane's NAV even while the underlying industry index is flat, which the overlay's monthly
recompute cadence may not catch quickly enough.

## Measurement
Selection window 2023-09-18..2025-12-31 is used only to build the two placebo distributions
(pool-rank and dip-signal calendar-shift); it does not rank or pick among the five lanes, since
there is no ranking step in this design. Holdout 2026-01-02..2026-09-17 is scored once per lane
and never ranks. Anchor 2024-01-08..2026-09-16 carries gates G1/G1' and G4. Reported per lane:
annualized return, volatility, Sharpe, maximum drawdown and turnover per year in each window, at
10 and 20 bp per side; the pool-rank placebo beat-fraction against the 24-ETF levered pool; the
dip-signal calendar-shift placebo beat-fraction over 20 offsets (plus the strict family-wise
10%/5=2% read); and anchor-window daily-return correlation with the live S3 book. Diagnostics,
never ranked and not counted as candidates: each lane raw (no overlay), each lane with vt40 only
(no boost), and the live S3 book itself as the correlation reference.

## Stop/Pivot criterion
Stop and treat the direction as refuted if no lane passes all of G1-or-G1', G2, both G3
placebos (<=10% each), G4, G5, and the <=0.5 correlation criterion. Reopen only with a new
mechanism (for example a regime model that forecasts which industry will trend next) or new
data (for example an options-implied or news-driven industry signal), not by re-tuning the
overlay parameters or widening the candidate list to more ETFs inside the same five industries.
This is round 1 of this direction; the compute budget for the decisive test is 15 minutes.
