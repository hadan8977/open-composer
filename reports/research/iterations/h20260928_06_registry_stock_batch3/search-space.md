# Search space: h20260928_06_registry_stock_batch3

One path, `stock_batch3_screen`, ten preregistered candidates, no tuning: k and
holding length are taken from each candidate's own primary source (or T1's
k=30/h=20 default only when the source discloses neither, which none of these
ten needed).

| candidate_id | mechanism | k | h (sessions) |
|---|---|---:|---:|
| momentum_concentrated_k37 | cross-sectional momentum_252_21 top-k | 37 | 21 |
| skew_52wk_high_k95 | dist_from_252d_high top-k (nearest 52wk high) | 95 | 21 |
| vam_momentum_k50 | momentum_252_21 / vol_63 top-k (AEGIS step 1 only) | 50 | 21 |
| a13d_item4_h6 | 13D item4 new-filing calendar-time hold | n/a (event) | 126 |
| a13d_item4_h12 | 13D item4 new-filing calendar-time hold | n/a (event) | 252 |
| a13d_item4_h24 | 13D item4 new-filing calendar-time hold | n/a (event) | 504 |
| monday_afternoon_spy | Monday close-vs-open direction, hold the week | n/a (1 asset) | ~4 (weekly) |
| monday_afternoon_qqq | Monday close-vs-open direction, hold the week | n/a (1 asset) | ~4 (weekly) |
| overnight_only_spy | static long-overnight/flat-intraday | n/a (1 asset) | 1 (daily round trip) |
| overnight_only_qqq | static long-overnight/flat-intraday | n/a (1 asset) | 1 (daily round trip) |

No ranking or selection among the ten: each is judged independently against the
owner's absolute K1/K2 bars (see `candidate-manifest.json`'s `keep_rule`).
Overlapping daily cohorts (the first three, plus the 13D calendar-time books)
are date-neutral by construction (`n_offsets: 1`); the single-index and
overnight candidates are static/one-version-only, also `n_offsets: 1`, since
they have no periodic-rebalance-date ambiguity to sweep.

Benchmark family: S3 incumbent (`screen_lane.s3_incumbent`, offset 0), the
vol-matched `k*S3+(1-k)*SHY` control per window, SPY buy-and-hold, and the
universe equal weight where a cross-sectional book applies.

Cost, validation windows and DSR conventions are in `cost-contract.json`,
`candidate-manifest.json`'s `contracts.validation`, and `hypotheses.md`.
