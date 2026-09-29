# Report: h20260928_44_etf_pair_switch

Batch-screening pass for T-20260928-44: 18 candidates -- 12 `PAIR_*`
long-only binary relative-strength switches between the two legs of six
highly correlated ETF pairs (QQQ/SPY, SMH/QQQ, XLE/XOP, KRE/XLF, IWM/SPY,
ARKK/QQQ) at lookback {63,126} trading days, monthly rebalance, using
`run_h20260918_05_recent_menu.py:rotation_cell`'s mechanism unedited at menu
size 2 / top_n=1 -- plus 6 `STATIC5050_*` placebo controls (fixed 50/50
blend of the same two legs, no ranking, no cash filter). Run via
`scripts/screen_batch.py --batch h20260928_44_etf_pair_switch --iteration
h20260928_44_etf_pair_switch`; raw output at
`reports/research/screens/h20260928_44_etf_pair_switch/leaderboard.json`
(all 18 candidates completed, none skipped, `n_trials=18`). Every number
below is read directly from that file and
`reports/research/iterations/h20260928_44_etf_pair_switch/results.json`,
checked candidate-by-candidate against `candidate-manifest.json`'s
preregistered K1/K2/watch_recent/strong_keep thresholds and the
preregistered STATIC5050 counter-evidence downgrade rule -- no candidate,
grid point, or threshold was changed after seeing a result.

## S3 reference (from `h20260928_01_s3_rebalance_tranching/results.json`)

Anchor median Sharpe (net10) 1.4853, K1 anchor bar (80%) 1.1882. Stress
median Sharpe (net10) 0.8059, K1 stress bar (80%) 0.6447.

## Result: 0 kept, 0 strong_keep, 0 watch_recent, 1 downgraded (no switching increment), 11 refuted outright

Exactly one of the 12 `PAIR_*` candidates, `PAIR_SMHQQQ_L63_MO`, clears full
K1 in both windows on its own numbers -- and is then downgraded to **"not
kept (no switching increment)"** by the preregistered STATIC5050
counter-evidence rule, because its own paired static-blend control beats it
in the stress window. No candidate clears K2 (every `PAIR_*` candidate's
`diversifier_edge_anchor` is negative, and no `PAIR_*` candidate clears 0.05
in both windows). No other `PAIR_*` candidate reaches even the anchor-only
watch_recent bar.

### The one near-pass: `PAIR_SMHQQQ_L63_MO`, downgraded

| window | PAIR_SMHQQQ_L63_MO judged Sharpe (net10) | K1 bar | passes K1 leg? | STATIC5050_SMHQQQ_MO judged Sharpe (net10) | PAIR beats control? |
|---|---|---|---|---|---|
| anchor | 1.2848 | 1.1882 | yes | 1.2041 | yes |
| stress | 0.7679 | 0.6447 | yes | 0.8882 | **no** |

`PAIR_SMHQQQ_L63_MO` clears both K1 legs on its own numbers (anchor Sharpe
1.2848 >= 1.1882; stress Sharpe 0.7679 >= 0.6447; 20bp CAGR positive both
windows: anchor 49.4%, stress 16.6%). Per the preregistered
counter-evidence rule in `candidate-manifest.json`'s `keep_rule`, a PAIR
candidate that clears K1/K2/watch_recent is downgraded to "not kept (no
switching increment)" if its judged Sharpe does not exceed its own paired
STATIC5050 control's judged Sharpe in every window it passed on.
`PAIR_SMHQQQ_L63_MO` beats `STATIC5050_SMHQQQ_MO` in the anchor window
(1.2848 vs 1.2041) but loses to it in the stress window (0.7679 vs 0.8882)
-- so the rule fires and the candidate is downgraded to **not kept (no
switching increment)**. DSR (anchor, n_trials=18): 0.597 for the PAIR
candidate, 0.547 for its static control -- both moderate, and largely moot
given the counter-evidence downgrade.

The nearby `PAIR_SMHQQQ_L126_MO` (anchor Sharpe 1.1722, stress Sharpe
0.7844) fails K1's anchor leg by a hair (1.1722 < 1.1882 bar) and does not
qualify for watch_recent either (which requires the anchor leg to clear).

### All other 10 `PAIR_*` candidates: refuted outright

No other pair/lookback combination comes close to either K1 leg. The
best of the rest by anchor Sharpe is `PAIR_QQQSPY_L63_MO` at 0.582 (K1
anchor bar 1.1882) -- well below both bars. `PAIR_KREXLF_L63_MO` and
`PAIR_XLEXOP_L63_MO` have slightly negative anchor Sharpe (-0.051 and
-0.018 respectively). Every `PAIR_*` candidate's `diversifier_edge_anchor`
is negative (range -0.169 to -0.597), so K2 fails everywhere on the PAIR
side as well.

### Why the counter-evidence check matters: switching underperforms holding both, in the stress window

Across all six pairs, most `STATIC5050_*` controls' judged stress-window
Sharpe is higher than their corresponding `PAIR_*_L63_MO` candidate's
(e.g. SMH/QQQ: 0.888 static vs 0.768 pair at L63; QQQ/SPY: 0.778 static vs
0.629 pair at L63; the exception is ARKK/QQQ: 0.636 static vs 0.669 pair at
L63). This is consistent with the negative-evidence check performed
before this batch ran (Robot Wealth's dual-momentum review, source card
`robotwealth_dual_momentum_review_whipsaw_2026`): binary switching between
two highly correlated names pays a whipsaw/turnover cost in choppy periods
that a static blend avoids, and the concentration benefit of picking the
"stronger" leg is too small within a highly correlated pair to
consistently outweigh that cost -- exactly the failure mode this batch's
placebo design was built to test for.

## Best-DSR candidate reported for context

`PAIR_SMHQQQ_L63_MO` has the highest DSR (0.597, n_trials=18) among all 18
candidates -- the same candidate that clears K1 on its own numbers and is
then downgraded by the counter-evidence rule.

## Verdict

`dir:etf_pair_relative_strength_switch` is refuted for this scope: no
`PAIR_*` candidate is kept, strong_keep, or watch_recent after applying the
preregistered STATIC5050 counter-evidence downgrade. The coverage-map gap
`relative_value.pairs_stat_arb`'s long-only leg is resolved with a negative
result -- see `registry-update.json` and `coverage-update.json`. See
`decision-record.md` for the stop decision.
