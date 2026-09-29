# Report: h20260929_34_levered_single_stock (T-20260929-34)

Source: `reports/research/screens/h20260929_34_levered_single_stock/leaderboard.json`
(also `results.json`/`trial-ledger.jsonl` in this directory, derived from the
same leaderboard). 14 candidates, n_trials=14, commit
`4a0775a9f4761968f0651b990b04ac07d6a5a0fa`.

## Verdict

**No candidate clears K1 or K2.** 5 of the 12 mechanism candidates clear
K1's anchor-only bar (median-offset net-10bp anchor Sharpe >= 1.1882) but
none clears the stress bar (>= 0.6447) -> **watch_recent**, not keep. K2
(diversifier edge >= 0.05 both windows vs a vol-matched S3+SHY control)
fails for every candidate: the best edge anywhere is +0.0363 (stress only,
LSS_N50_K3_2X), every anchor-window edge is negative.

## K1 check (S3 reference: anchor 1.4853, stress 0.8059; bars 1.1882 / 0.6447)

| candidate | anchor Sharpe | stress Sharpe | anchor net20 CAGR | stress net20 CAGR | stress max_dd | DSR(anchor, n=14) |
|---|---|---|---|---|---|---|
| LSS_N50_K3_1X | 1.4415 | 0.5729 | 69.7% | 13.5% | -38.6% | 0.732 |
| LSS_N50_K2_2X | 1.3894 | 0.5788 | 80.2% | 16.9% | -66.7% | 0.709 |
| LSS_N50_K2_1X | 1.3863 | 0.4910 | 69.3% | 11.1% | -56.8% | 0.700 |
| LSS_N50_K3_2X | 1.3451 | 0.6425 | 68.8% | 20.1% | -54.0% | 0.682 |
| LSS_N50_K1_1X | 1.2256 | 0.4231 | 66.1% | 8.9% | -79.1% | 0.615 |
| LSS_N50_K1_2X | 1.1762 | 0.4768 | anchor 1.1762 < 1.1882 bar -- does not clear watch_recent | | | 0.581 |
| (best N20 cell) LSS_N20_K3_1X | 1.1561 | 0.6653 | anchor < 1.1882 bar -- does not clear watch_recent | | | 0.560 |

All 5 N50 watch_recent candidates beat both falsification controls on judged
anchor Sharpe (LSS_N20_EW_2X 0.975, LSS_RAND_K2_2X 0.7181), so none is
demoted for replicating a control.

LSS_N20_K3_1X is the closest N20 cell to the bar (stress 0.6653 actually
clears the stress bar on its own, but anchor 1.1561 falls short of 1.1882)
-- illustrating that concentration alone (top-3 of a top-20 menu) is not
enough; only the wider top-50 menu clears the anchor bar at all.

## K2 check (edge >= 0.05 both windows)

Every anchor-window edge is negative (range -0.34 to -0.0002); the least-bad
is LSS_N50_K2_2X / LSS_N50_K3_1X at essentially 0.00. No candidate is close
to K2 in the anchor window regardless of the stress-window number. S3
itself is not diversified by any of these individual-stock leveraged
sleeves in this design.

## Stock-picking increment (best mechanism vs equal-weight control vs random placebo, judged anchor Sharpe)

| | anchor Sharpe |
|---|---|
| best mechanism cell (LSS_N50_K3_1X) | 1.4415 |
| LSS_N20_EW_2X (equal-weight, no picking, top-20/2x/vt40) | 0.9750 |
| LSS_RAND_K2_2X (random pick k=2, top-20/2x/vt40, placebo) | 0.7181 |

The momentum-ranking signal itself does add real anchor-window value over
both controls (+0.47 vs equal-weight, +0.72 vs random) -- the mechanism is
not just "leverage + vt40 alone looks good" or pure noise. It simply does
not survive into the stress window at the required magnitude (best stress
Sharpe 0.64, vs the 0.6447 bar and S3's own 0.81).

## Relation to prior local evidence

Consistent with dir:equity_momentum_concentrated_pwb (unlevered top-37,
anchor 1.03/stress 0.51, both K1 and K2 failed): narrowing k to 1-3,
restricting the universe to a megacap-by-liquidity top-20/50 menu, and
adding 2x leverage + vt40 raises the anchor Sharpe (up to 1.44 here vs 1.03
there) enough to newly clear K1's *anchor-only* bar for the N50 cells, but
the stress-window Sharpe is still short of the bar in every case (best 0.64
vs 0.51 there) -- the concentration/leverage combination helps the recent
window without fixing the older-regime shortfall the unlevered design
already had. No K2 diversification value in either design.

## Decision

Not kept (no candidate clears K1 or K2). 5 N50-menu candidates qualify for
**watch_recent** per the 2026-09-28 owner rule (anchor bar cleared, stress
not, beats both controls): LSS_N50_K1_1X, LSS_N50_K2_1X, LSS_N50_K2_2X,
LSS_N50_K3_1X, LSS_N50_K3_2X. Per the runbook, `kept.jsonl` rows are written
by the coordinator after this batch module is committed (commit hash for
`scripts/screen_batches/h20260929_34_levered_single_stock.py` to be filled
in at that point, not the current HEAD).
