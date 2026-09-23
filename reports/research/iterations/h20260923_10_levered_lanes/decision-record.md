# Decision record: h20260923_10_levered_lanes

## Path
levered_industry_second_bet_lane_screen, five preregistered candidates (LN01..LN05) run
through the frozen S3 overlay machine, plus three never-ranked diagnostics.

## Decision
Stop. The direction is refuted per its preregistered stop condition: no lane passes G1-G5 plus the
correlation cap (report.md). NUGT and JNUG pass G1/G4 and the correlation cap but fail the 2026
holdout (Sharpe 0.53 / 0.57) and the generic-leverage pool placebo (39-44%); FAS, DPST and DFEN fail
every gate. Rejected variants: none were run beyond the manifest; no threshold was moved.

## Reason
The overlay machine already cleared its own gates on the live S3 book and is not being
re-tested here; the only open question is whether a second, independently-trending industry
(chosen from published industry-momentum evidence and the local I-20260923-01 census, not from
scanning the levered-ETF universe for the best backtest) can clear the same gates while staying
weakly correlated with the live book. The cheapest decisive test reuses the existing daily
panel, the existing frozen overlay implementation, and the existing placebo protocol from
H-20260922-02 and H-20260923-09, so the marginal compute is minutes, and the untouched 2026
holdout plus the correlation check give an honest read that has not been produced before.

## Next iteration suggestion
No second round on this family. Reopen only with a mechanism that forecasts which sector trends next
(a regime or sector-rotation model) or new data (options-implied or news-driven industry signals).
The meta question it leaves -- how to combine the live sleeves -- belongs to
dir:meta_strategy_trailing_return_rotation, not to more levered lanes. ML/AI entry conditions: not met
by this round.
