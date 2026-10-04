# Decision Record: h20261004_pm_midterm_odds_leadlag

Status: paperwork frozen 2026-10-04T08:32:01Z; no strategy return computed. The decision rules (continue, pivot to the forward shadow, stop) are those of hypotheses.md. Verdict pending the test run (`scripts/run_h20261004_pm_midterm_odds_leadlag.py`).

## P1

- Path: midterm_control_odds_trump_trades (H-M decision candidate, M-CAT and M-KAL report only)
- Reason: the claim is the only published test that trades a prediction-market price, and a different election tests it without new parameters; cheapest decisive test is one pass of the frozen script.
- Next iteration suggestion: none until the verdict; if inconclusive, the 2026-11-05 combined re-test, if refuted, no further midterm-odds variants without a new mechanism.
- Decision: proceed to data collection and the test as frozen in `hypotheses.md` (6f6bd6c); direction check and pre-backtest validation precede any return.
- Directions source: paper Internet Appendix Table A.1, verbatim, from the paper snapshot (`reports/research/intel/sources/prediction-markets-round2-2026-10-04/wang-learning-from-prediction-markets.txt`); identical to the frozen fallback.
- Rulings made before any return (see `data-feasibility.json`): TSLA costed at 2 bp per side; EMA convention `adjust=False`; percentile ties by average rank.
