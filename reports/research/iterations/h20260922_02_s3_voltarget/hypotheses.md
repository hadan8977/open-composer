# Hypotheses: h20260922_02_s3_voltarget

## Hypothesis H-20260922-02
A volatility target of 40% or 60% annualized, estimated from a 21-session realized volatility
of the sleeve's own book and applied with a hard 1.0 leverage cap (excess weight into SHY),
together with an equity-curve drawdown brake that halves exposure once the sleeve is 25% below
its running peak and restores it on a new high or after 21 sessions, compresses the S3 sleeve's
anchor-window maximum drawdown from -56.4% to -35% or better while keeping anchor annualized
return at or above 50% and holdout Sharpe at or above 1.0.

## Failure mode
The overlay is a lagged risk estimate. In a fast drawdown it reduces exposure after the loss
and restores it after the rebound, so it can cost more return than drawdown it saves. This is
the documented out-of-sample failure in Cederburg et al. (2020). The brake has the same defect
in a sharper form: a 25% trigger on a sleeve whose normal volatility is very high may fire on
noise. A second failure mode is cost: the overlay adds turnover, and Barroso and Detzel (2021)
show that volatility management generally does not survive transaction costs.

## Measurement
Selection window 2023-09-18..2025-12-31 ranks cells by Sharpe at 10 bp per side. Holdout
2026-01-02..2026-09-17 is scored once and never ranks. Anchor 2024-01-08..2026-09-16 carries
the gates. Reported per cell: annualized return, volatility, Sharpe, maximum drawdown and
turnover per year in each window, at 10 and at 20 bp per side. Benchmark family: SPY, MTUM,
SPMO, TQQQ buy and hold, the A4 menu equal weighted monthly, the unmodified S3 cell, and a
volatility-matched excess over SPY. Placebos: 60 random-pick seeds on the same menu and
calendar, and 20 brake-calendar-shift seeds for the brake cells.

## Stop/Pivot criterion
Stop and write lesson card L-20260922-02 if no cell reaches anchor drawdown of -35% or better
with annualized return at or above 50% (or Sharpe at or above 2.0 with return at or above 30%),
or if the winner's holdout Sharpe is below 1.0 or its holdout return is negative, or if more
than 10% of the 60 random-pick seeds beat it, or if the brake cannot beat its own
calendar-shift placebo. Pivot to a second and final round only with variants already named in
brief B-2. This is round 1 of at most 2.
