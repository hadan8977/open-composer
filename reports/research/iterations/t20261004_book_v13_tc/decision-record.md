# Decision Record: t20261004_book_v13_tc

## Path

cost_aware_trading_rules_book_v13

## Decision

Stop (frozen stage gate of hypotheses.md section 5): no rule meets E1-E4, so Stage 2 is not run and v1.2 keeps full rebalancing to the target at every tranche refresh. The production target generator and the order engine are unchanged. Reviewed by the 2026-10-04 07:07 UTC lead round (Opus) against `results.json`, `identity.json`, `diagnostics.json` and the hypotheses.md hash (`contract.unchanged = true`).

## Verified numbers (results.json, offset medians, M0_U3000, net of modelled cost and borrow)

| rule | recent net Sharpe | delta recent | stress net Sharpe | delta stress | E1 | E2 (offsets improved) | E3 full-sample NW t (raw daily difference) | E4 | eligible |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 1.485 | - | 0.598 | - | - | - | - | - | baseline |
| P2 | 1.597 | +0.112 | 0.634 | +0.036 | no | 5/5, 5/5 | 1.02 | yes | no |
| P3 | 1.638 | +0.154 | 0.654 | +0.056 | no | 5/5, 5/5 | 0.48 | yes | no |
| P2V | 1.522 | +0.038 | 0.668 | +0.071 | no | 5/5, 5/5 | 1.07 | yes | no |
| N25 | 1.557 | +0.073 | 0.681 | +0.083 | no | 5/5, 5/5 | 2.94 | yes | no |
| N50 | 1.642 | +0.158 | 0.722 | +0.124 | yes | 5/5, 5/5 | 1.76 | yes | no (E3) |

- Identity: B0 through the new code path equals T-25 R6 for offsets 0 and 3 with max abs difference 0.0 (tolerance 1e-12).
- Cost frontier (D3, recent / stress): B0 221 / 152 bp a year at one-sided turnover 15.9 / 12.9; N50 80 / 52 bp at 4.8 / 3.7. Gross Sharpe does not fall (N50 1.744 vs 1.721 recent, 0.798 vs 0.775 stress). The frontier is monotone in slowness for both rule families (P2 < P3, N25 < N50) at 1x and 2x cost, so the cost-optimal speed lies beyond the preregistered grid.
- D1 turnover source (recent): VIX flips 25.9% of turnover and 25.7% of cost; drift is 4.2 a year per tranche against a target change of 31.0, so turnover comes from target changes, not from drift.
- D2 persistence: weekly rank autocorrelation of every theme is 0.93-1.00 (insider 0.93 lowest, seasonality 1.00), M0 composite 0.983, in both windows.

## Reason

- Death cause: N50 clears the runbook optimization rule (E1) with all offsets improved in both windows, but its full-sample paired Newey-West t of the raw daily net difference is 1.76 < 2.0. N25 clears E3 (2.94) but not E1.
- Review finding on the contract itself (written by the 01:07 lead round, my error): E3 tests the raw mean difference, which is not scale-free, while section 3 of hypotheses.md says the decision is made on Sharpe. N50 runs at 0.966 of B0's volatility (gross exposure 1.43 vs 1.68 full sample), so the raw difference understates its Sharpe gain. Post-hoc diagnostic, computed at 07:20 UTC from `data/research/book_v13/` after the verdict and NOT used for it: the vol-matched paired NW t (candidate scaled to B0's window volatility) is 2.50 for N50 and 3.59 for N25 over the full sample (N50 recent 1.55, stress 1.94). The frozen verdict stands; changing E3 now would be a post-result relaxation.
- No look-ahead found: rules use the target of the decision date and the drifted holdings at the D+1 close fill, the same information set as B0; survivorship affects B0 and the rules identically (same members, same delisting handling); no rebalancing day is picked (all 5 offsets, offset medians).
- The GP Proposition 3 follow-up named in section 10 is conditional on fast themes driving turnover. D2 shows no fast theme, so that follow-up is not opened.
- External evidence read in the 07:07 round agrees with the direction (Barroso, Saxena and Wang 2022: turnover-penalised portfolios reach net Sharpe 1.10-1.20 in the 500 largest stocks while unmanaged ones do not beat the passive portfolio; snapshot `reports/research/intel/sources/book-v14-ml-2026-10-04/`). This is prior support, not a pass.

## Next iteration suggestion

- Keep v1.2 B0 for the paper incubation. N50 is frozen as the single challenger; it is not re-tested on the 2017-10..2026-09 windows. Reopen only with new information, in a new contract written before that information is looked at: (a) at least 252 sessions after 2026-09-17, recomputed offline from the live directory (no production change), with E1, E2, E4 and a vol-matched E3; or (b) measured execution costs at least equal to the model from a live pilot.
- Contract lesson for every later paired test: use the vol-matched (scale-free) difference and state a power estimate (t about dSR x sqrt(years) / sqrt(2(1 - rho))) before freezing. Applied first in `t20261004_book_v14_ml`.
- D1's construction finding (a dense linear book over about 2,200 names re-trades every name each week; VIX flips are a quarter of cost) goes to the v2 construction design, not to another rule search on these windows.
