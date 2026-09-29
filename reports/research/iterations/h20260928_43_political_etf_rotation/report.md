# Report: h20260928_43_political_etf_rotation

Batch-screening pass for T-20260928-43: 24 candidates (12 POLITICAL + 12
PLACEBO_BIGTECH), the same cross-sectional momentum rotation mechanism
already live on S1-S3 (`run_h20260918_05_recent_menu.py:rotation_cell`,
unedited), applied to a menu of 4 publicly-disclosed political/congressional-
trade-replica ETFs (NANC, GOP, MAGA, DEMZ) and a matched big-tech placebo
menu (QQQ, XLK, SPY, DIA), grid = lookback {63,126,252} trading days x top_n
{1,2} x rebalance {monthly, weekly}. Run via `scripts/screen_batch.py --batch
h20260928_43_political_etf_rotation --iteration
h20260928_43_political_etf_rotation`; raw output at
`reports/research/screens/h20260928_43_political_etf_rotation/leaderboard.json`.
Every number below is read directly from that file and
`reports/research/iterations/h20260928_43_political_etf_rotation/results.json`,
checked candidate-by-candidate against `candidate-manifest.json`'s
preregistered K1/K2/watch_recent/placebo-dominance thresholds -- no
candidate, grid point, or threshold was changed after seeing a result.

## Judgment protocol actually used

The 2016-05-02..2023-09-15 stress window is **not** part of the K1/K2
pass/fail decision for this batch: NANC and GOP launched 2023-02-07 and have
zero coverage of it (see `data-feasibility.json`). Candidates are judged on
the select (2023-09-18..2025-12-31) and anchor (2024-01-08..2026-09-17)
windows only, which structurally caps every candidate at `watch_recent`
(anchor-window date-neutral Sharpe >= 1.1882, the 80%-of-S3 bar) -- a full
K1 keep, which needs both anchor and stress, is unreachable this round by
design, not by a failed computation.

The generic screening engine still computed a "stress" diversifier edge from
each candidate's own `first_valid_signal_date` onward (driven mostly by
MAGA, which has data since 2017-09, and DEMZ since 2020-11); those numbers
are reported in `results.json` as `k2_edge_stress_reference_only` but are
**not** used for any pass/fail decision here.

## Result: 0 kept, 0 strong_keep, 0 watch_recent, 24 refuted

No POLITICAL candidate reaches the anchor-only watch_recent bar (median-offset
anchor Sharpe >= 1.1882, 10bp). The closest is `POLITICAL_L252_N1_MO` at
anchor Sharpe **0.9015** (select Sharpe 0.886), 76% of the bar, still 24%
short. Every other POLITICAL candidate is further below.

| id | select Sharpe (10bp) | anchor Sharpe (10bp) | anchor CAGR (10bp) | K2 edge (anchor) | DSR (anchor) |
|---|---|---|---|---|---|
| POLITICAL_L252_N1_MO | 0.886 | **0.902** | 19.9% | -0.180 | 0.308 |
| POLITICAL_L252_N2_WK | 0.821 | 0.846 | 17.0% | -0.210 | 0.280 |
| POLITICAL_L252_N1_WK | 0.776 | 0.817 | 17.1% | -0.239 | 0.263 |
| POLITICAL_L252_N2_MO | 0.722 | 0.794 | 17.0% | -0.212 | 0.248 |
| POLITICAL_L63_N2_MO  | 0.451 | 0.640 | 13.4% | -0.316 | 0.176 |
| POLITICAL_L126_N2_WK | 0.716 | 0.636 | 12.4% | -0.292 | 0.176 |
| ... (remaining 6 POLITICAL cells all lower; full numbers in results.json) |

Every candidate's K2 diversifier edge with S3 is strongly **negative** in the
anchor window (range -0.18 to -0.45 across POLITICAL, -0.29 to -0.58 across
PLACEBO_BIGTECH) -- both menus track S3's own equity-momentum exposure too
closely (or simply have too little dispersion/edge) to add diversification
value; K2 fails for all 24 regardless of the anchor Sharpe level.

## Placebo comparison (big-tech momentum disqualifier)

Because no POLITICAL candidate reached watch_recent or better, the
preregistered placebo-dominance disqualifier (`candidate-manifest.json`
`keep_rule.placebo_dominance_disqualifier`) never triggers -- it is a
downgrade rule for candidates that already cleared the bar, and none did.
For context, `results.json`'s `placebo_dominance_comparison_by_grid_cell`
shows a mixed picture across the 12 grid cells: PLACEBO_BIGTECH's anchor
Sharpe is higher in 5 cells (L63_N1_MO, L63_N1_WK, L63_N2_WK, L126_N1_WK
tie, L252_N2_MO) and POLITICAL is higher in 7 cells, including the
best-performing cell (L252_N1_MO: POLITICAL 0.902 vs PLACEBO_BIGTECH 0.873).
The best PLACEBO_BIGTECH candidate overall, `PLACEBO_BIGTECH_L252_N2_MO`
(anchor Sharpe 0.907, DSR 0.309), is essentially tied with the best
POLITICAL candidate and also fails the watch_recent bar. This is *not*
strong evidence either way on the "is it just tech momentum" question --
both menus fail the bar by a similar margin, so the batch is refuted before
that question becomes decisive.

## 40bp wide-spread sensitivity: not computed

Per `candidate-manifest.json`'s preregistered trigger condition ("For any
POLITICAL candidate reaching watch_recent or better..."), the 40bp-per-side
illiquidity-adjusted sensitivity check was not run: no POLITICAL candidate
met the trigger (`results.json.wide_spread_40bp_sensitivity.computed =
false`). `scripts/analyze_h20260928_43_wide_spread.py` was not written this
round because there was nothing to feed it.

## Data-coverage note (first_valid_signal_date)

Actual first bars (DuckDB scan, `data-feasibility.json`): NANC/GOP
2023-02-07, MAGA 2017-09-07, DEMZ 2020-11-03 -- not "~2024-01" as the queue
task assumed. Because `first_valid_signal_date` is triggered by *any* menu
member (not all four), POLITICAL candidates show an early
`first_valid_signal_date` (2017-12 for L63, 2018-09 for L252) driven by
MAGA/DEMZ alone; GOP and NANC (the two tickers the source evidence is
actually about) only enter the rotation set once their own lookback is
satisfied from 2023-02-07 (~2023-05 for L63, ~2024-02 for L252). This does
not change the verdict (the select/anchor windows both postdate GOP/NANC's
L63/L126 validity, and L252's ~1-month gap is a minor fraction of the
anchor window) but is disclosed per the queue task's requirement.

## Verdict

`dir:congressional_political_trade_replica_etf_rotation` is **refuted** for
this scope: none of the 12 POLITICAL candidates reaches even the
anchor-only watch_recent bar under the same rotation_cell mechanism already
validated live on S1-S3, and K2's diversification edge is negative
everywhere. The direction is refuted on its own numbers (best anchor Sharpe
0.902 vs the 1.1882 bar) before the placebo-dominance question becomes the
deciding factor. See `decision-record.md` for the stop decision and
`registry-update.json` / `coverage-update.json` for the registry/coverage
updates (applied by the coordinator, per this task's restrictions).
