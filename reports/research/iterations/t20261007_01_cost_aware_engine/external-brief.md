# External Brief: t20261007_01_cost_aware_engine

Written 2026-10-07 by the T-20261007-01 execution agent. Source snapshots and what was actually opened: `reports/research/intel/sources/cost-aware-engine-2026-10-07/README.md`; verified cards: `reports/harness/source_cards/t20261007_01_cost_aware_engine.jsonl` (9 cards, 9 papers or broker docs).

## Objective

Put three existing increments into one equity book and see whether the recent-window net Sharpe rises at the same volatility: the ML slow score (m0m2), the fast composite FC_EW (P1 stage 0), and cost-controlled trading speed (v1.3). Stage 0 showed the fast composite cannot be its own leg: blended with M0 at inverse volatility it lowers the recent Sharpe from 0.80 to 0.75 because 79% of capital sits in the weaker leg.

## How others do it, which one we follow, what we change

| Source | What it does | We follow | We change |
|---|---|---|---|
| Garleanu-Pedersen 2013 | Trade partially to an aim portfolio; aim = exponential average of current and expected future Markowitz portfolios, so fast-decaying signals get less weight | I3: daily aim book, weight b_k / (1 + phi_k / kappa), partial trade at kappa | Weights use P1 stage-0 stress-window IC and half-lives; no covariance term (rank weights, industry-demeaned); v1.3 only tested the static fixed rate |
| Novy-Marx-Velikov 2016 | Buy/hold spread is the best cost mitigation | Kept as the comparison idea (v1.3 N50, net +0.158, frozen) | Not re-run; B0 full rebalance is the baseline |
| Frazzini-Israel-Moskowitz (NBER 2012 draft; 2018 paper) | Square-root impact; cost-aware optimisation cuts a value-momentum book's turnover about 2/3 and impact about half, more than for each alone | Same cost-function form (cost model v1); signals traded in one book rather than as separate legs | Rank-weighted U3000 with simple rules, no optimiser |
| Jensen-Kelly-Malamud-Pedersen | Learn weights with trading costs in the objective | Motivation for judging the ML slow score net, inside the book | Abstract page and the 2026-10-01 full-text snapshot only; no public code found, nothing reimplemented |
| DeMiguel et al. 2020 | Trades of different characteristics cancel when combined, so more characteristics are worth holding | Same mechanism as FIM | Abstract only; not bound as evidence |
| Supit 2020 | Short-term signal times a decided trade; gain up to 32 bp per trade with a neural net, but about -9 bp with simple predictors | I2: postpone a trade while the fast score contradicts it, at most 4 sessions | Portfolio-level, per name, c = 0, 0.5, 1.0; a fast-only placebo is mandatory because the gain depends on the predictor |
| Barroso-Saxena-Wang 2022, Chen-Velikov 2023 | Nonlinear forecasts turn over more and lose after costs; single anomalies do not survive costs | Judge m0m2 and the fast signal net, in the book | None |

Not found: a primary source that uses a fast equity signal to schedule the trades of a slower signal's target at the portfolio level. The closest is Supit (execution level, one broker). Blitz et al. 2023 (alpha from short-term signals) was not read and is not used.

## Scope

Single mechanism, lightweight path: 23 preregistered points on one construction (v1.2 unchanged). Evidence backs this grid only, not promotion.
