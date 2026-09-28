# H-20260928-04: S3 alt-diversifier batch 1 (19 candidates) vs S3

Batch: `scripts/screen_batches/h20260928_04_batch1.py`, run via
`scripts/screen_batch.py --batch h20260928_04_batch1 --iteration h20260928_04_s3_alt_div_batch1`.
Raw leaderboard: `reports/research/screens/h20260928_04_batch1/leaderboard.json`
(`.md` alongside). This dossier's `results.json` recomputes the K1/K2/watch_recent
tiers field by field from that leaderboard plus S3's own offset-median Sharpe
(`reports/research/iterations/h20260928_01_s3_rebalance_tranching/results.json`
`offset_distribution_net10`; same reference numbers as
`h20260928_02_cross_asset_sleeve/results.json`'s `s3_reference`).

## Verdict

**0/19 kept (K1 or K2), 0/19 watch_recent, 19/19 refuted.** No candidate's
date-neutral (offset-median) 10bp anchor Sharpe reaches the K1 bar of
1.1882 (80% of S3's own anchor median 1.4853); the closest are F2_GEM
(0.9570), F3_TRTY (0.9203) and F2_GTAA (0.9019), all short of the bar. No
candidate clears the K2 combination-edge bar (>=0.05 Sharpe in both anchor
and stress) -- the largest anchor-only edges (F1_DBMF +0.091, F3_TRTY +0.136,
F2_GTAA +0.145) all turn sharply negative in the stress window.

## K1 -- standalone Sharpe vs S3 (bars: anchor >=1.1882, stress >=0.6447, 20bp CAGR>0 both)

| id | anchor Sharpe (10bp) | stress Sharpe (10bp) | 20bp CAGR anchor | 20bp CAGR stress | K1 | stress coverage |
|---|---:|---:|---:|---:|:---:|---|
| F1_DBMF | 0.8157 | 0.3733 | 13.43% | 5.58% | fail | 4.29/7.37yr (partial) |
| F1_KMLM | 0.1128 | 0.5165 | 4.95% | 9.23% | fail | 2.70/7.37yr (partial) |
| F1_CTA | 0.5654 | 0.5734 | 13.60% | 12.44% | fail | 1.46yr (<2yr, 待补压力期) |
| F1_WTMF | 0.6819 | 0.0109 | 10.54% | 1.07% | fail | full |
| F1_FMF | 0.5628 | 0.1908 | 9.12% | 2.93% | fail | full |
| F2_VAA_G4 | 0.2129 | 0.3981 | 4.58% | 4.13% | fail | 6.62/7.37yr (partial) |
| F2_DAA_G12 | 0.5840 | 0.4530 | 9.37% | 4.49% | fail | 6.62/7.37yr (partial) |
| F2_PAA | 0.8472 | 0.4802 | 12.90% | 4.41% | fail | 6.62/7.37yr (partial) |
| F2_HAA | 0.6814 | 0.6487 | 11.92% | 7.39% | fail (anchor) | 6.62/7.37yr (partial) |
| F2_GPM | 0.6825 | 0.4839 | 11.23% | 4.16% | fail | 6.62/7.37yr (partial) |
| F2_GEM | 0.9570 | 0.3324 | 20.72% | 4.79% | fail | 6.62/7.37yr (partial) |
| F2_GTAA | 0.9019 | 0.4245 | 10.71% | 4.08% | fail | 6.87/7.37yr (partial) |
| F2_ADM | 0.7174 | 0.3672 | 13.62% | 5.19% | fail | 7.13/7.37yr (partial) |
| F2_BAA_BAL | 0.5853 | 0.7098 | 9.52% | 7.83% | fail (anchor) | 6.62/7.37yr (partial) |
| F3_RPAR | 0.4740 | -0.0463 | 9.18% | -0.19% | fail | 3.71/7.37yr (partial) |
| F3_UPAR | 0.4697 | -1.0243 | 10.70% | -18.67% | fail | 1.62yr (<2yr, 待补压力期) |
| F3_NTSX | 0.9117 | 0.2909 | 18.70% | 5.43% | fail | 5.04/7.37yr (partial) |
| F3_QAI | 0.7115 | 0.1309 | 9.07% | 1.91% | fail | full |
| F3_TRTY | 0.9203 | 0.1690 | 13.35% | 2.81% | fail | 4.96/7.37yr (partial) |

K1 bar: anchor >=1.1882, stress >=0.6447 (both from S3's own anchor 1.4853 /
stress 0.8059 median-offset Sharpe x 0.80). No candidate clears both; F2_HAA
and F2_BAA_BAL clear the stress leg alone (0.6487, 0.7098) but fail anchor.

## K2 -- combination edge vs vol-matched S3 (bar: >=0.05 both windows)

| id | anchor edge | stress edge | K2 |
|---|---:|---:|:---:|
| F1_DBMF | +0.0910 | -0.2208 | fail (stress) |
| F1_KMLM | -0.1185 | -0.2634 | fail |
| F1_CTA | +0.2035 | -0.4641 | fail (stress) |
| F1_WTMF | -0.0634 | -0.2579 | fail |
| F1_FMF | +0.0810 | -0.0975 | fail (stress) |
| F2_VAA_G4 | -0.4554 | -0.1490 | fail |
| F2_DAA_G12 | -0.1438 | -0.1662 | fail |
| F2_PAA | -0.0953 | -0.1649 | fail |
| F2_HAA | -0.1915 | -0.0768 | fail |
| F2_GPM | -0.1088 | -0.1442 | fail |
| F2_GEM | -0.0464 | -0.2465 | fail |
| F2_GTAA | +0.1450 | -0.2020 | fail (stress) |
| F2_ADM | -0.1899 | -0.1624 | fail |
| F2_BAA_BAL | -0.1499 | +0.0136 | fail |
| F3_RPAR | -0.0514 | -0.4795 | fail |
| F3_UPAR | -0.1395 | -0.8647 | fail |
| F3_NTSX | -0.0935 | -0.2898 | fail |
| F3_QAI | +0.0180 | -0.3413 | fail |
| F3_TRTY | +0.1359 | -0.3651 | fail (stress) |

Every candidate fails K2 in the stress window; several (F1_DBMF, F1_CTA,
F1_FMF, F2_GTAA, F3_TRTY) have a positive anchor-window edge that flips
sharply negative in stress, the same anchor-window-is-not-a-hard-enough-test
pattern H-20260928-02 found for D1/D2.

## Conclusion (5 lines)

1. All 19 published/live-tracked alt-diversifier and TAA rules fail both K1
   and K2 against S3's frozen reference (anchor Sharpe 1.4853, stress
   0.8059) -- none is Sharpe-competitive with a levered semiconductor-momentum
   sleeve in either window, and none adds combination value once blended.
2. The failure mode is uniform: every family's anchor-window combination
   edge (where positive) collapses in the stress window (2016-05..2023-09,
   includes 2018Q4/2020/2022) -- the same pattern H-20260928-02 found for
   Defense First and absolute-momentum sleeves.
3. F1_CTA (1.46yr) and F3_UPAR (1.62yr) have under 2 years of stress-window
   coverage (pending stress, "待补压力期" per the runbook rule) but both
   already fail on anchor Sharpe alone, so the missing stress evidence does
   not change either verdict.
4. No candidate reaches even the K1 anchor-only watch_recent bar (needs
   anchor Sharpe >=1.1882); the closest, F2_GEM at 0.9570, is still 0.23
   below the bar, so this batch contributes 0 watch_recent lines.
5. Per the batch-1 decision record's stop condition, all three families
   (managed-futures-ETF hold, Keller/Antonacci/Faber TAA, other
   alt-diversifier hold) are refuted for this batch; do not re-tune
   published/round-number parameters inside this manifest without a new
   mechanism, longer live record, or new disclosed data.
