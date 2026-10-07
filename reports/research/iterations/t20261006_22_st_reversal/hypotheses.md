# Hypotheses: t20261006_22_st_reversal

## Hypothesis

Residual returns of liquid US stocks reverse over 1-10 sessions, and a daily many-bet book that trades the reversal in overlapping batches earns a net Sharpe in 2024-2026 that survives measured spreads, impact and borrow, with low correlation to the monthly stock long-short book.

## Failure mode

The reversal has decayed to near zero gross in liquid names (equity-statarb repo: OOS 2019-2024 gross 0.23, net -0.15), the edge is concentrated in illiquid or hard-to-borrow names that the cost and borrow rules exclude, or daily turnover consumes the gross edge.

## Measurement

contract.md: Stage A 24 main cells on 2024-01-08..2026-09-15 through run_book with cost_model_v1; Stage B diagnostic window, placebo, six robustness checks and scorecard_v2 tier for the top cells.

## Stop/Pivot criterion

If every cell has recent gross Sharpe below 0.3 the family is closed at this depth (not at depth if any of the five depth conditions in contract.md section 12 is missing); if a cell reaches tier P1 write paper-sleeve-spec.md.

## Spec selection rule (standard 5b item 6, written before any result)

Among the 24 main-grid cells rank by recent (2024-01-08..2026-09-15) net Sharpe at 1x cost; take the three highest and use the middle-ranked one (second highest) as the selected spec. Robustness cells (condition lowturn / nonews / vixscale, execution at the close of t+1) and the ridge / LightGBM cells run on that spec only and do not take part in selection. Tier by P1 (standard section 5) with N = 24 for the DSR. Full contract: `contract.md` (sections 0-15 frozen 2026-10-06T23:23Z; section 16 addendum 2 supersedes the grid and book, written before any result).
