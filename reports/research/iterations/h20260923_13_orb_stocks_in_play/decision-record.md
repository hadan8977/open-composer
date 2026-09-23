# Decision record: h20260923_13_orb_stocks_in_play

## Path

`orb_stocks_in_play_screen`, three preregistered candidates (SIP01 long-only at the paper's own
parameters, SIP02 long-only at a stricter liquidity floor, SIP03 a long-short diagnostic never
eligible for promotion), plus two preregistered controls (RD random-direction, RL random-non-in-
play-liquid-stock) and one reused reference (the already-refuted ETF-ORB simplification).

## Decision

**Not executed.** This pass is scoped to the dossier, a data-feasibility check, and an
engine-design note only -- no backtest and no engine/evaluation code were written or run, per the
task's explicit hard rule. `direction-review.json`, `search-space.json`, `candidate-
manifest.json`, `cost-contract.json`, and `data-feasibility.json` are all preregistered and gate-
checked (`oc research direction-check` -> ok; `oc research iteration validate --stage pre-
backtest` -> ok). `data-feasibility.json` sets `historical_evaluation_authorized: false` and marks
all three candidates `dependency_skipped`, with the concrete reason recorded in its `path_gates`
entry: this project's minute archives were built from a current-active-asset snapshot with no
minute-bar counterpart to the daily-only delisted-name archive, `data/sip/minute` discloses its own
shard-index staleness for shards <=316/year, `data/sip-hist/minute` has no shard index at all, and
the archive's `adjustment=all` convention conflicts with the paper's own unadjusted data -- none of
which are resolved by this pass.

## Reason

The task scope is explicit: build and gate-check the preregistration, not run it. Running a grid
before the shard-index and survivorship questions are bounded would risk silently biasing the
design-window sample (toward whichever names happen to be easiest to locate in the current shard
layout) without disclosing it -- exactly the kind of undisclosed data-source sensitivity the
project's promotion checklist (AGENTS.md) requires to be checked before, not after, a backtest is
trusted.

## Deviations and notes

- The individual-stock paper describes no profit target; this dossier removes the 10R target this
  project's own ETF-proxy script (`scripts/run_h20260918_02_orb_etf.py`) added by analogy from a
  different paper -- a disclosed correction, not a departure from the primary source.
- Leverage cap is preregistered at a house default of 1.0x for SIP01/SIP02 (a disclosed departure
  from the paper's own 4x), pending an explicit broker-authorization decision on margin/PDT
  eligibility for the account this would eventually paper-trade from; SIP03 uses the paper's own
  4x for fidelity-checking purposes only.
- The published 2.81 Sharpe headline is a combined long+short number with no long-only split ever
  reported; SIP01/SIP02 (long-only, the primary candidates) are explicitly not expected to
  reproduce it, and SIP03 (long-short) exists only to sanity-check implementation fidelity, never
  for promotion.

## Next iteration suggestion

The next step is the cheapest_decisive_test named in `direction-review.json`: (1) verify or rebuild
a trustworthy symbol-to-shard index for both minute archives (reading actual `symbol` columns
directly, not trusting footer stats, following `scripts/run_h20260918_02_orb_etf.py`'s own
verification discipline); (2) bound the survivorship gap with a small, named sample of known
2016-2022 delisted/acquired tickers checked against local minute coverage; (3) only after those two
checks either scope the design-window grid to a disclosed, bounded universe or defer it with a
named blocking reason -- then, and only then, run the 43-simulation core budget (SIP01/SIP02/SIP03
plus 20 RD + 20 RL seeds) named in `search-space.json`. Engine design for that step is in
`engine-design.md`. If neither SIP01 nor SIP02 clears the adoption rule once run, the verdict is
"keep refuted" and this direction closes again, not reopened by re-tuning after a partial result.
