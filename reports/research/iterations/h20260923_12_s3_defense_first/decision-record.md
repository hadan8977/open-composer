# Decision record: h20260923_12_s3_defense_first

## Path
s3_defense_first_remainder_screen, three preregistered candidates (DF00 reference plus DF01, DF02
Defense First remainder variants) run through the frozen S3 vt40+boost overlay machine's own
remainder, plus one shared EW control and eighty RR-k random-ranking placebos (not candidates).

## Decision
**Stop: keep SHY.** Neither candidate passes all of (a)-(e), so the preregistered verdict is "keep
SHY" and `dir:s3_defense_first_remainder` is refuted for this mechanism. Run 2026-09-23 with
`scripts/run_h20260923_12_s3_defense_first.py` (83 simulations as budgeted; DF00 recomputed and
checked against both the salvage engine and the published stress replay, all within 1e-9).

| cell | design CAGR | design Sharpe | design max DD | anchor CAGR 10 / 20 bp | anchor max DD |
|---|---|---|---|---|---|
| DF00 S3 as renewed, remainder in SHY | 30.7% | 0.83 | -48.0% | 116.3% / 113.7% | -32.3% |
| EW static 25/25/25/25 | 32.6% | 0.86 | -45.8% | 122.6% / 120.0% | -32.8% |
| DF01 Defense First, SPY fallback | 35.3% | 0.90 | -49.1% | 131.6% / 128.6% | -32.9% |
| DF02 Defense First, SHY fallback | 33.9% | 0.88 | -46.9% | 127.4% / 124.4% | -32.7% |
| SPY buy and hold (scale) | 12.7% | 0.68 | -33.9% | 20.9% | -18.6% |
| SHY buy and hold (scale) | 0.7% | -0.34 | -5.7% | 3.4% | -1.0% |

| candidate | (a) Sharpe >= DF00 + 0.10 | (b) max DD not worse | (c) >= 36/40 random ranks | (d) > EW | (e) anchor G1 10/20 bp |
|---|---|---|---|---|---|
| DF01 | fail (+0.07) | fail (-49.1% vs -48.0%) | fail (34/40, median 0.889) | pass | pass / pass |
| DF02 | fail (+0.05) | pass | pass (40/40, median 0.865, max 0.880) | pass | pass / pass |

At 20 bp the design Sharpes are DF00 0.80, DF01 0.87, DF02 0.86: same conclusion.

## Reason
- Most of the lift is diversification, not the ranking. Holding the four defensive assets in
  equal weight (EW) already adds +0.03 Sharpe; the Defense First ranking adds about +0.02 more.
  With the SHY fallback the ranking beats all 40 random rankings, so it carries some information;
  with the paper's SPY fallback it does not (34/40), because a failing slot moves into equities
  exactly when defensive assets are weak, which deepens 2018 (-25.2% vs -22.0%) and the
  2018-2019 drawdown (-49.1%).
- The help is concentrated in 2022 (DF01 -25.4%, DF02 -26.8% vs DF00 -33.6%), when commodities
  and the dollar trended. The deepest episode of the design window (2018-2019, -48%) is not
  reduced, which was the point of the test.
- The anchor-window gains (DF02 127% vs 116%) are on a window already seen at the renewal; they
  only show the change does no harm, not that it helps out of sample.

## Deviations and notes
- Defense First first trades on 2017-02-01, the session after the 2017-01-31 decision close (the
  dossier's warmup note said 2017-02-03; the engine follows the rule "next session"). EW starts
  2016-05-02, the first session S3 holds risk; before those dates every remainder is SHY.
- As in every cell of this engine, the remainder's split is a target held between decisions,
  not a drifting position; the preregistration described EW as "rebalanced monthly".
- No cell applies the 25% drawdown exit; it is an account-level rule outside this comparison.

## Next iteration suggestion
None for this family. Reopen only with a new defensive-asset set, a new published
remainder-allocation rule, or new disclosed data -- not by re-tuning windows, weights, the
momentum blend, or by switching the fallback after seeing these results. S3's 2016-2023 risk
(-48%) stays with the 25% exit and the owner's sizing; per
`docs/plan-research-coverage-2026-09-23.zh.md`, compute moves to per-stock signals.
