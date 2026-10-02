# Decision Record: h20261002_pm_macro_uncertainty

Status before the run: design, candidates and continue rules are frozen in `hypotheses.md` and `candidate-manifest.json`; no equity return grouped by U_rel or by the expectation gap has been computed. This record is rewritten with the verdict after the test.

## P1

- Path: release_day_overlay (U1-U7, G1-G2)
- Decision: pending (continue only if the frozen H1 continue rule passes, stop and refute otherwise)
- Reason: pending the preregistered test; data feasibility is recorded in `data-feasibility.json`.
- Next iteration suggestion: pending; the forward collector `scripts/collect_prediction_markets.py` supplies shadow data whatever the backtest says.
