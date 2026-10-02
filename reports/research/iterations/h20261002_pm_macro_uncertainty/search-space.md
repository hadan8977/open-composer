# Search Space: h20261002_pm_macro_uncertainty

One path (`release_day_overlay`), nine preregistered candidates, no parameter search and no model training.

- U1-U7: long QQQ, SPY, IWM or TQQQ (or a U_rel weight, or FOMC days included) around the release day, MOC T-1 to MOC T, on days when the Kalshi-implied U_rel is above 1; U4 is the unconditional baseline on the same days.
- G1-G2: sign of Kalshi implied mean minus the Cleveland Fed CPI nowcast, TLT or QQQ, MOC T-1 to MOO T, CPI days only (no free payrolls consensus exists).
- Signal: U = standard deviation of the middle-out cleaned implied distribution from the last hourly candle ending at or before 15:00 ET on T-1; U_rel = U over the median of the previous 12 events of the series; 6 prior events needed; 4 usable strikes needed.
- Samples: full from the first valid U_rel event (2023-07-12) to 2026-09-17, anchor 2024-01-08 to 2026-09-17.
- Costs: QQQ, SPY, TLT 2 bp, IWM 3 bp, TQQQ 5 bp per side, stress doubles, shorts 0.5 percent per year borrow.
- Statistics: D with a 1000-shuffle within-series permutation p (seed 20261002), three placebos, DSR over the 9 candidates.
- Continue rule frozen in `candidate-manifest.json` before any return grouped by U_rel or by the gap was computed. Total budget 9 (limit 24 per path, 80 per round).
