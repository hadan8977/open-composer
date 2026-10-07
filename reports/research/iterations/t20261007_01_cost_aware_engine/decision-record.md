# Decision Record: t20261007_01_cost_aware_engine

## Path

cost_aware_engine_book_v2

## Decision

not_deep_enough

## Reason

Preregistered 2026-10-07 by the T-20261007-01 execution agent before any candidate point was run (identity and timing only); contract in hypotheses.md.

## Next iteration suggestion

Established: quant1 second sub-strategy after sub-ledger isolation (T-20261006-07), forward comparison against v1.2. Not established: close the line, keep the fast composite for intraday execution. Not deep enough: name the missing condition and how to fill it.

## Result (2026-10-07, pending lead review)

Selected S0_I3F_k005: recent net Sharpe 1.617 vs B0 1.485 (+0.132), G1/G2/G4 pass, tier P1, but G3 fails (fast-composite-only placebo: same +0.105 increment, percentile 4%). The gain is slow-only daily partial adjustment (turnover 15.9 -> 5.8, cost 221 -> 80 bp/yr), not the fast signal. Label: not deep enough under the frozen rule; see report.md.

## Lead review (2026-10-07 20:18 UTC, 19:37 UTC lead round, Opus)

Accepted: not_deep_enough for the fast composite (G3: the placebo that shuffles only the fast composite also gains about +0.105). Checked in results.json: preregistration validated 14:45:41 UTC before any grid point; B0 net Sharpe (offset median) recent 1.485, stress 0.598, full 0.911; slow-only partial adjustment S0_I3_k005 1.621 / 0.651 / 1.004 and S0_I3_k010 1.606 / 0.668 / 1.006, gross Sharpe not lower (k010 recent 1.752 vs 1.721, stress 0.781 vs 0.775), cost 221 -> 80 / 120 bp per year (stress 152 -> 53 / 80).

Decision: stop the fast-composite route in this construction; pivot the slow-score partial adjustment to an execution-layer change of v1.2 (queue T-20261007-20: worktree, parity at kappa = 1, 10-session log-only shadow of turnover, tracking and whole-share error; switch to kappa = 0.05 with the T-07 capital-base change if turnover ratio <= 0.65, tracking inside the backtest 95% band and whole-share error not worse). No new backtest contract on the windows already seen. Three preregistered measurements agree in sign (v1.3 N50, P1 stage 0, this grid); the paired test is underpowered (t 0.86), the mechanism is the cost saving.

Final validation is blocked only by `breakeven_costs_missing` from the uncommitted gate-additions module (T-20261005-34, not yet an adopted rule); not filled in this round.
