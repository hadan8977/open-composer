# Report: h20260928_41_country_etf_rotation

T-20260928-41: single-country developed/emerging-market equity ETF cross-sectional
momentum rotation. 8 candidates (`COUNTRY_L{63,252}_N{1,2}_{MO,WK}`), reusing
`h20260928_40_equity_etf_menus.make_rotation_fn` unedited (identical mechanism to
S1-S3's `rotation_cell`). Run via `scripts/screen_batch.py --batch
h20260928_41_country_etf_rotation --iteration h20260928_41_country_etf_rotation`. All numbers below are read directly from
`reports/research/screens/h20260928_41_country_etf_rotation/leaderboard.json` (n_trials=8).

## S3 reference (frozen, from h20260928_01_s3_rebalance_tranching/results.json)

- Anchor Sharpe: 1.4853
- Stress Sharpe: 0.8059
- K1 bars (0.80x S3): anchor >= 1.1882, stress >= 0.6447
- K2 bar: judged inverse-vol-blend Sharpe edge vs vol-matched S3 control >= 0.05 in BOTH windows

## Per-candidate results (median-offset Sharpe, net10)

| candidate | anchor Sharpe | stress Sharpe | K2 anchor edge | K2 stress edge | DSR (anchor) | verdict |
|---|---|---|---|---|---|---|
| COUNTRY_L63_N1_MO | 1.2131 | 0.0422 | 0.0301 | -0.1827 | 0.6971 | watch_recent |
| COUNTRY_L63_N1_WK | 0.9977 | 0.0487 | -0.1515 | -0.2008 | 0.5676 | not_kept |
| COUNTRY_L63_N2_MO | 1.0592 | -0.0151 | -0.0831 | -0.2418 | 0.6066 | not_kept |
| COUNTRY_L63_N2_WK | 1.0293 | 0.0393 | -0.0749 | -0.2320 | 0.5875 | not_kept |
| COUNTRY_L252_N1_MO | 1.0325 | -0.0663 | -0.0921 | -0.4029 | 0.5901 | not_kept |
| COUNTRY_L252_N1_WK | 1.0005 | -0.1485 | -0.1222 | -0.4198 | 0.5699 | not_kept |
| COUNTRY_L252_N2_MO | 1.2107 | -0.1380 | 0.0215 | -0.4372 | 0.6955 | watch_recent |
| COUNTRY_L252_N2_WK | 1.2154 | -0.1770 | 0.0086 | -0.4633 | 0.6985 | watch_recent |

## Verdict counts

- strong_keep: 0
- keep (K1 or K2, not strong): 0
- watch_recent: 3
- not_kept: 5

## Reading

0/8 candidates clear K1 (all 8 fail the stress-window bar of >=0.6447; the best stress
Sharpe across all 8 candidates is 0.0487, far below the bar, and 5/8 have a NEGATIVE
stress-window Sharpe). 0/8 clear K2 (no candidate reaches a >=0.05 Sharpe edge in BOTH
windows; every stress-window K2 edge is negative, several sharply so, e.g. -0.46).

3/8 candidates reach `watch_recent` (anchor Sharpe clears the 1.1882 bar -- COUNTRY_L63_N1_MO 1.2131, COUNTRY_L252_N2_MO 1.2107, COUNTRY_L252_N2_WK 1.2154 -- but
all three fail the stress bar badly, 0.0422/-0.1380/-0.1770). This anchor-vs-stress split
(decent 2024-2026 recent-window performance, weak-to-negative 2016-2023 stress-window
performance) is directly consistent with the Du & Jiang (2024) decay note quoted on the
Quantpedia source page itself (see `direction-review.json`): 'The efficacy of ETF momentum
strategies, while robust until around 2010, began to show signs of waning in subsequent
years.' The mechanism that (per the sibling h20260928_40 batch) works reasonably for
FACTOR/INDUSTRY equity-ETF menus does not clear this project's keep bar for the
single-country-equity-ETF menu once the older, weaker stress window is included.

## Verdict

`dir:international_country_etf_momentum_rotation` -- REFUTED for K1/keep at this grid;
3 of 8 candidates (COUNTRY_L63_N1_MO, COUNTRY_L252_N2_MO, COUNTRY_L252_N2_WK) are
tracked forward-only as `watch_recent` (recorded in `kept.jsonl`), not as a keep. No
candidate reaches `strong_keep` or plain `keep`.
